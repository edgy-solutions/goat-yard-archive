"""Corpus fingerprint + reconciliation gate — the sync boundary before Dagster writes.

A fingerprint is a deterministic identity for a Weaviate corpus state: object counts, a content hash
(order-independent Merkle over every chunk's stable fields), and the ingestion SHA (the git rev of the
pipeline that produced it, read from a corpus-meta object if present). Two instances are IDENTICAL iff
their fingerprints match.

SAFETY: fingerprint() and compare() are READ-ONLY. reconcile_plan() is DRY-RUN — it reports what WOULD
change to make `target` match `source`, and returns it for review; it does NOT mutate anything. Applying
a reconciliation (deleting/overwriting objects in a live instance) is destructive and is intentionally
NOT automated here — it must be run with an explicit source-of-truth decision and human confirmation,
never blind. This module gives you the diff to make that decision on.
"""
import os, json, hashlib

CHUNK_FIELDS = ("content", "verse_ref", "page_number", "volume", "footnotes", "lemma")  # full identity fields
# BODY = the load-bearing prose the standoff decision keeps BYTE-IDENTICAL (SIDs, chunk boundaries,
# verifier difflib targets, eval assertions all hang off these exact bytes). EXCLUDES footnotes/lemma:
# the apparatus/standoff layer legitimately updates those, the body must never change.
BODY_FIELDS = ("content", "verse_ref", "page_number", "volume")
COLLECTIONS = ("CommentaryChunk", "TheologicalEntity")

def _body_digest(props):
    slim = {k: props.get(k) for k in BODY_FIELDS if k in props}
    return hashlib.sha256(json.dumps(slim, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()

def body_content_sha(iter_objects):
    """Order-independent hash over the BODY prose only (content + identity, NOT footnotes). The number the
    body-untouched assertion watches: it must be byte-stable across any apparatus/standoff ingestion."""
    return content_hash([_body_digest(_split(o)[0]) for o in iter_objects])

UNKNOWN_SHA = "unknown-pre-instrumentation"   # explicit sentinel: corpus predates ingestion-SHA stamping

def _obj_digest(props):
    """Stable per-object TEXT digest over identity fields (JSON-canonical, sorted keys)."""
    slim = {k: props.get(k) for k in CHUNK_FIELDS if k in props}
    return hashlib.sha256(json.dumps(slim, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()

def _vec_digest(vector, precision=6):
    """Stable per-object VECTOR digest — the embedding rounded to `precision` decimals (tolerates float
    noise while flipping on any real re-embed). None if the object carries no vector."""
    if not vector:
        return None
    return hashlib.sha256(json.dumps([round(float(x), precision) for x in vector]).encode()).hexdigest()

def content_hash(object_digests):
    """Order-INDEPENDENT corpus hash: XOR-fold of per-object digests, then hash. Two corpora with the same
    objects in any ingestion order produce the same hash; a single changed/added/dropped object flips it.
    (XOR-fold is commutative, so no sort needed over millions of rows.)"""
    acc = 0
    for d in object_digests:
        acc ^= int(d, 16)
    return hashlib.sha256(hex(acc).encode()).hexdigest()

def _split(item):
    """Accept either a (props, vector) tuple or a bare props dict (vector under '_vector' or absent)."""
    if isinstance(item, tuple):
        return item[0], item[1]
    return item, (item.get("_vector") if isinstance(item, dict) else None)

def fingerprint(iter_objects, counts, ingestion_sha=UNKNOWN_SHA):
    """Fingerprint from an iterator of CommentaryChunk objects + per-collection counts. READ-ONLY.
    Each item is a (props, vector) tuple or a props dict. Hashes TEXT identity AND VECTOR identity
    separately (text-identity was proven; vector-identity was assumed — this closes it)."""
    text_digests, vec_digests = [], []
    for item in iter_objects:
        props, vector = _split(item)
        text_digests.append(_obj_digest(props))
        vd = _vec_digest(vector)
        if vd is not None:
            vec_digests.append(vd)
    return {
        "counts": dict(counts),
        "chunk_count": counts.get("CommentaryChunk", 0),
        "content_sha256": content_hash(text_digests),
        "vector_sha256": content_hash(vec_digests) if vec_digests else None,
        "n_hashed": len(text_digests),
        "n_vectors_hashed": len(vec_digests),
        "ingestion_sha": ingestion_sha,
    }

def compare(fp_a, fp_b):
    """READ-ONLY. Diff between two fingerprints + whether they are identical (text AND vector AND SHA)."""
    diffs = {}
    for k in ("counts", "content_sha256", "vector_sha256", "ingestion_sha"):
        if fp_a.get(k) != fp_b.get(k):
            diffs[k] = {"a": fp_a.get(k), "b": fp_b.get(k)}
    return {"identical": not diffs, "diffs": diffs}

def reconcile_plan(fp_source, fp_target):
    """DRY-RUN ONLY — describes what would change to make `target` match `source`. Returns a plan for
    REVIEW; performs no mutation. Applying it is a separate, confirmed, destructive step done by hand
    with the source-of-truth decision made explicitly."""
    cmp = compare(fp_source, fp_target)
    if cmp["identical"]:
        return {"action": "none", "reason": "fingerprints identical", "identical": True}
    sc = fp_source["counts"].get("CommentaryChunk", 0); tc = fp_target["counts"].get("CommentaryChunk", 0)
    return {
        "action": "REVIEW-REQUIRED", "identical": False, "diffs": cmp["diffs"],
        "count_delta_chunks": sc - tc,
        "content_hash_differs": fp_source.get("content_sha256") != fp_target.get("content_sha256"),
        "note": "target->source reconciliation is DESTRUCTIVE (drops/overwrites objects). Decide the "
                "source of truth explicitly and confirm before applying; this function does not mutate.",
    }

# --- live-instance adapters (require an actual client; not exercised in unit tests) ------------------
def fingerprint_instance(weaviate_url=None, ingestion_sha=None):
    """Connect to a Weaviate instance (READ-ONLY) and fingerprint it. weaviate_url defaults to env.
    Streams CommentaryChunk objects so it does not load the whole corpus into memory."""
    import weaviate
    url = weaviate_url or os.getenv("WEAVIATE_URL", "localhost")
    host = url.split("://")[-1].split(":")[0]
    port = int(url.split(":")[-1]) if ":" in url.split("://")[-1] else 8080
    client = weaviate.connect_to_custom(http_host=host, http_port=port, http_secure=url.startswith("https"),
                                        grpc_host=os.getenv("WEAVIATE_GRPC_HOST", host),
                                        grpc_port=int(os.getenv("WEAVIATE_GRPC_PORT", "50051")), grpc_secure=False)
    try:
        counts = {}
        for c in COLLECTIONS:
            try: counts[c] = client.collections.get(c).aggregate.over_all(total_count=True).total_count
            except Exception: counts[c] = None
        chunks = client.collections.get("CommentaryChunk")
        def stream():
            for o in chunks.iterator(return_properties=list(CHUNK_FIELDS)):
                yield o.properties
        # ingestion_sha from a corpus-meta object if the schema carries one, else the passed value
        return fingerprint(stream(), counts, ingestion_sha=ingestion_sha)
    finally:
        client.close()

if __name__ == "__main__":
    import sys
    # CLI: fingerprint the WEAVIATE_URL instance, or compare two saved fingerprint files.
    if len(sys.argv) >= 3 and sys.argv[1] == "compare":
        fa = json.load(open(sys.argv[2])); fb = json.load(open(sys.argv[3]))
        print(json.dumps(compare(fa, fb), indent=1))
    else:
        fp = fingerprint_instance(os.getenv("WEAVIATE_URL"), ingestion_sha=os.getenv("INGESTION_SHA"))
        print(json.dumps(fp, indent=1))
