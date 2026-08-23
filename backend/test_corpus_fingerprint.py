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
