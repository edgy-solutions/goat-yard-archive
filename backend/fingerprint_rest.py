"""READ-ONLY fingerprint of a Weaviate instance over its REST API (robust across engine versions) —
cursor-pages every CommentaryChunk, feeds the stable fields into corpus_fingerprint's deterministic
hash. No writes. Usage: python fingerprint_rest.py <name> <ip>"""
import sys, json, httpx
import corpus_fingerprint as CF

def _extract_vector(o):
    """The embedding out of one REST object, across the plain and named-vector schema shapes."""
    vec = o.get("vector")
    if vec is None and o.get("vectors"):             # named-vector schema (newer engines)
        vv = o["vectors"]; vec = vv.get("default") or next(iter(vv.values()), None)
    if isinstance(vec, dict):
        vec = vec.get("default") or next(iter(vec.values()), None)
    return vec

def _fetch_page(url, faults=None):
    """The 5-attempt JSON-decode retry (transient truncation / empty body under load -> backoff).
    Every retry (not the final raise) is counted on `faults` -- a retry nobody counts is a
    measurement nobody can audit."""
    import time as _t
    for attempt in range(5):
        try:
            resp = httpx.get(url, timeout=120)
            if not resp.text.strip(): raise ValueError("empty body")
            return resp.json()
        except Exception:
            if attempt == 4: raise
            if faults is not None:
                faults.append({"kind": "json_decode_retry", "url": url, "attempt": attempt})
            _t.sleep(0.5 * (attempt + 1))

def _page_dims(objs, vecs):
    hist = {}
    for v in vecs:
        if v:
            hist[len(v)] = hist.get(len(v), 0) + 1
    return hist

def _anomalous_uuids(objs, vecs, modal_dim):
    if modal_dim is None:
        return []
    return [o.get("id") for o, v in zip(objs, vecs) if v and len(v) != modal_dim]

def stream_chunks(ip, include_vector=True, gentle=0.0, faults=None):
    """Cursor-page CommentaryChunk objects, yielding (props, vector, meta) 3-tuples where meta
    carries the REST object's own 'id' and 'lastUpdateTimeUnix' (read, not synthesised).
    include=vector fetches the embedding so the fingerprint can hash vector-identity too
    (READ-ONLY). Page size is small for 4096-dim vectors; `gentle` adds an inter-page sleep to
    avoid loading a PRODUCTION instance serving live traffic (test is idle; prod is not).

    Page-level structural validation: a running modal vector length is seeded from the first
    page's most common length and updated as pages stream in. If any object on a page has a
    vector length that differs from that modal length, the SAME page URL is re-fetched up to 3
    more times, keeping the first re-fetch that parses with no dim anomaly. If every attempt is
    still anomalous, the last-fetched page is yielded as-is (never silently dropped, never a
    substituted zero vector) and the page URL + offending uuids are appended to `faults`. EVERY
    re-fetch is counted on `faults` (`dim_anomaly_retry`), not only the giving-up: a retry nobody
    counts is how the visible half of this defect stayed invisible in the first place."""
    import time as _t
    after = None
    inc = "&include=vector" if include_vector else ""
    limit = 20 if include_vector else 100
    cumulative_dims = {}
    modal_dim = None
    while True:
        url = f"http://{ip}/v1/objects?class=CommentaryChunk&limit={limit}{inc}"
        if after: url += f"&after={after}"
        r = _fetch_page(url, faults)
        objs = r.get("objects", [])
        if not objs: break
        if gentle: _t.sleep(gentle)

        vecs = [_extract_vector(o) for o in objs]
        page_dims = _page_dims(objs, vecs)
        if modal_dim is None and page_dims:
            modal_dim = max(page_dims, key=page_dims.get)      # seed from the first page

        anomalies = _anomalous_uuids(objs, vecs, modal_dim)
        attempts = 0
        while anomalies and attempts < 3:
            attempts += 1
            if faults is not None:                              # count the retry, not just the giving-up
                faults.append({"kind": "dim_anomaly_retry", "url": url, "attempt": attempts,
                               "uuids": list(anomalies)})
            r2 = _fetch_page(url, faults)
            objs2 = r2.get("objects", [])
            vecs2 = [_extract_vector(o) for o in objs2]
            anomalies2 = _anomalous_uuids(objs2, vecs2, modal_dim)
            objs, vecs, anomalies = objs2, vecs2, anomalies2
            if not anomalies2:
                break
        if anomalies and faults is not None:
            faults.append({"kind": "dim_anomaly", "url": url, "uuids": list(anomalies)})

        for v in vecs:                                          # keep the running dim current
            if v:
                cumulative_dims[len(v)] = cumulative_dims.get(len(v), 0) + 1
        if cumulative_dims:
            modal_dim = max(cumulative_dims, key=cumulative_dims.get)

        for o, vec in zip(objs, vecs):
            yield o.get("properties", {}), vec, {"id": o.get("id"),
                                                  "last_update_ms": o.get("lastUpdateTimeUnix")}
        after = objs[-1]["id"]

def counts(ip):
    q = lambda cls: httpx.post(f"http://{ip}/v1/graphql", json={"query": "{Aggregate{%s{meta{count}}}}" % cls},
                               timeout=30).json()["data"]["Aggregate"][cls][0]["meta"]["count"]
    return {"CommentaryChunk": q("CommentaryChunk"), "TheologicalEntity": q("TheologicalEntity")}

def corpus_health(prod_ip=None, test_ip=None, ingestion_sha=None):
    """READ-ONLY dual-instance fingerprint + compare, for the daily report / trace metadata. Defaults
    to in-cluster service DNS (overridable via env). Returns a compact, JSON-safe health dict."""
    import os
    prod = prod_ip or os.getenv("WEAVIATE_PROD_HOST", "weaviate.gya-backend")
    test = test_ip or os.getenv("WEAVIATE_TEST_HOST", "weaviate.gya-test")
    fp_p = CF.fingerprint(stream_chunks(prod), counts(prod), ingestion_sha=ingestion_sha)
    fp_t = CF.fingerprint(stream_chunks(test), counts(test), ingestion_sha=ingestion_sha)
    cmp = CF.compare(fp_p, fp_t)
    return {
        "identical": cmp["identical"], "diffs": cmp["diffs"], "ingestion_sha": ingestion_sha,
        "prod": {"chunks": fp_p["chunk_count"], "counts": fp_p["counts"], "content_sha": fp_p["content_sha256"]},
        "test": {"chunks": fp_t["chunk_count"], "counts": fp_t["counts"], "content_sha": fp_t["content_sha256"]},
    }

def slack_block(health):
    """A Slack mrkdwn section block summarising corpus fingerprint health (for the daily report)."""
    ok = health["identical"]
    icon = "✅" if ok else "🚨"
    sha = (health["prod"]["content_sha"] or "")[:12]
    line = (f"{icon} *Corpus fingerprint* — prod≡test: *{'IN SYNC' if ok else 'DRIFT'}*\n"
            f"chunks prod/test: {health['prod']['chunks']}/{health['test']['chunks']} · "
            f"content_sha `{sha}` · ingestion `{health.get('ingestion_sha') or 'unstamped'}`")
    if not ok:
        line += f"\n⚠️ diffs: `{json.dumps(health['diffs'])[:300]}`"
    return {"type": "section", "text": {"type": "mrkdwn", "content": line}}

if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    if len(sys.argv) >= 2 and sys.argv[1] == "health":
        print(json.dumps(corpus_health(*sys.argv[2:4] or [None, None]), indent=1))
    else:
        name, ip = sys.argv[1], sys.argv[2]
        fp = CF.fingerprint(stream_chunks(ip), counts(ip), ingestion_sha=None)
        fp["instance"] = name; fp["ip"] = ip
        print(json.dumps(fp, indent=1))
