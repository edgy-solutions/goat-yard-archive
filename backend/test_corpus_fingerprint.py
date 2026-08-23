"""corpus_fingerprint born tested — the deterministic hashing (order-independent, change-sensitive), the
identical/diff verdict, and the DRY-RUN reconcile plan that never claims to mutate. Live-instance
adapters are not exercised here (they need a real Weaviate). Run: python test_corpus_fingerprint.py"""
import corpus_fingerprint as CF

CHUNKS_A = [
    {"content": "In the beginning God created", "verse_ref": "GEN_1_1", "volume": 1, "page_number": 90,
     "footnotes": ["a"], "lemma": "bara"},
    {"content": "And the earth was without form", "verse_ref": "GEN_1_2", "volume": 1, "page_number": 90,
     "footnotes": [], "lemma": None},
]

def _fp(chunks, sha="abc123"):
    return CF.fingerprint(iter(chunks), {"CommentaryChunk": len(chunks), "TheologicalEntity": 5}, ingestion_sha=sha)

def test_content_hash_order_independent():
    a = _fp(CHUNKS_A); b = _fp(list(reversed(CHUNKS_A)))
    assert a["content_sha256"] == b["content_sha256"]        # same objects, any order -> same hash

def test_content_hash_change_sensitive():
    changed = [dict(CHUNKS_A[0], content="In the beginning God MADE"), CHUNKS_A[1]]
    assert _fp(CHUNKS_A)["content_sha256"] != _fp(changed)["content_sha256"]   # one edited char flips it

def test_content_hash_count_sensitive():
    dropped = [CHUNKS_A[0]]
    assert _fp(CHUNKS_A)["content_sha256"] != _fp(dropped)["content_sha256"]   # dropped object flips it

def test_compare_identical():
    r = CF.compare(_fp(CHUNKS_A), _fp(CHUNKS_A))
    assert r["identical"] is True and not r["diffs"]

def test_compare_detects_count_and_hash_diff():
    r = CF.compare(_fp(CHUNKS_A), _fp([CHUNKS_A[0]]))
    assert r["identical"] is False and "counts" in r["diffs"] and "content_sha256" in r["diffs"]

def test_compare_detects_ingestion_sha_drift():
    r = CF.compare(_fp(CHUNKS_A, sha="v1"), _fp(CHUNKS_A, sha="v2"))
    assert r["identical"] is False and r["diffs"]["ingestion_sha"] == {"a": "v1", "b": "v2"}

def test_ingestion_sha_defaults_to_explicit_sentinel():
    # blank is not left blank — the corpus that predates stamping says so explicitly
    fp = CF.fingerprint(iter(CHUNKS_A), {"CommentaryChunk": 2})
    assert fp["ingestion_sha"] == "unknown-pre-instrumentation"

def test_vector_hash_present_and_change_sensitive():
    a = [(CHUNKS_A[0], [0.1, 0.2, 0.3]), (CHUNKS_A[1], [0.4, 0.5, 0.6])]
    b = [(CHUNKS_A[0], [0.1, 0.2, 0.3]), (CHUNKS_A[1], [0.4, 0.5, 0.999])]  # one vector value changed
    fpa = CF.fingerprint(iter(a), {"CommentaryChunk": 2})
    fpb = CF.fingerprint(iter(b), {"CommentaryChunk": 2})
    assert fpa["vector_sha256"] and fpa["n_vectors_hashed"] == 2
    assert fpa["vector_sha256"] != fpb["vector_sha256"]                    # vector-identity now checked

def test_vector_identity_with_same_text_differs():
    # SAME text, DIFFERENT vectors -> content_sha matches but vector_sha differs (the gap we're closing)
    a = [(CHUNKS_A[0], [0.1, 0.2]), (CHUNKS_A[1], [0.3, 0.4])]
    b = [(CHUNKS_A[0], [0.9, 0.9]), (CHUNKS_A[1], [0.3, 0.4])]
    fpa, fpb = CF.fingerprint(iter(a), {}), CF.fingerprint(iter(b), {})
    assert fpa["content_sha256"] == fpb["content_sha256"]                  # text identical
    assert fpa["vector_sha256"] != fpb["vector_sha256"]                    # vectors differ -> caught now
    assert CF.compare(fpa, fpb)["identical"] is False                     # compare flags vector drift

def test_vector_hash_none_when_no_vectors():
    fp = CF.fingerprint(iter(CHUNKS_A), {"CommentaryChunk": 2})            # bare dicts, no vectors
    assert fp["vector_sha256"] is None and fp["n_vectors_hashed"] == 0

def test_vector_rounding_tolerates_float_noise():
    a = [(CHUNKS_A[0], [0.1234567])]; b = [(CHUNKS_A[0], [0.12345671])]     # differ past 6 decimals
    assert CF.fingerprint(iter(a), {})["vector_sha256"] == CF.fingerprint(iter(b), {})["vector_sha256"]

def test_reconcile_plan_none_when_identical():
    p = CF.reconcile_plan(_fp(CHUNKS_A), _fp(CHUNKS_A))
    assert p["action"] == "none" and p["identical"] is True

def test_reconcile_plan_is_dry_run_review_required():
    # source has 2 chunks, target has 1 -> plan flags REVIEW-REQUIRED, reports delta, mutates NOTHING
    p = CF.reconcile_plan(_fp(CHUNKS_A), _fp([CHUNKS_A[0]]))
    assert p["action"] == "REVIEW-REQUIRED" and p["count_delta_chunks"] == 1
    assert p["content_hash_differs"] is True and "DESTRUCTIVE" in p["note"]

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed"); raise SystemExit(1 if f else 0)
