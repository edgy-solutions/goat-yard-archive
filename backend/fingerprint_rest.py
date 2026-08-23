"""READ-ONLY fingerprint of a Weaviate instance over its REST API (robust across engine versions) —
cursor-pages every CommentaryChunk, feeds the stable fields into corpus_fingerprint's deterministic
hash. No writes. Usage: python fingerprint_rest.py <name> <ip>"""
import sys, json, httpx
import corpus_fingerprint as CF

def stream_chunks(ip):
    after = None
    props = ",".join(CF.CHUNK_FIELDS)
    while True:
        url = f"http://{ip}/v1/objects?class=CommentaryChunk&limit=100"
        if after: url += f"&after={after}"
        r = httpx.get(url, timeout=30).json()
        objs = r.get("objects", [])
        if not objs: break
        for o in objs:
            yield o.get("properties", {})
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
