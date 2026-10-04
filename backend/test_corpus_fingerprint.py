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

# --- per_object attribution (closes the "vector_sha256 moved, names nothing" false positive) -----

def test_three_tuple_stream_produces_a_complete_per_object_map():
    items = [(CHUNKS_A[0], [0.1, 0.2], {"id": "u1", "last_update_ms": 1000}),
             (CHUNKS_A[1], [0.3, 0.4], {"id": "u2", "last_update_ms": 2000})]
    fp = CF.fingerprint(iter(items), {"CommentaryChunk": 2})
    assert fp["per_object_complete"] is True, fp
    assert set(fp["per_object"]) == {"u1", "u2"}
    assert fp["per_object"]["u1"]["dim"] == 2
    assert fp["per_object"]["u1"]["last_update_ms"] == 1000
    assert fp["per_object"]["u1"]["vec"] is not None and fp["per_object"]["u1"]["text"] is not None

def test_two_tuple_stream_is_incomplete_and_classify_change_is_not_attributable():
    a = [(CHUNKS_A[0], [0.1, 0.2]), (CHUNKS_A[1], [0.3, 0.4])]     # 2-tuples -> no meta, no id
    fpa = CF.fingerprint(iter(a), {"CommentaryChunk": 2})
    fpb = CF.fingerprint(iter(a), {"CommentaryChunk": 2})
    assert fpa["per_object_complete"] is False, fpa
    assert fpa["per_object"] == {}
    cls = CF.classify_change(fpa, fpb)
    assert cls["attributable"] is False, cls

def test_dim_histogram_and_vector_dim_flag_a_one_element_vector_as_an_anomaly():
    items = [(CHUNKS_A[0], [0.1, 0.2, 0.3, 0.4], {"id": "u1", "last_update_ms": 1}),
             (dict(CHUNKS_A[0], content="dupe"), [0.5, 0.6, 0.7, 0.8], {"id": "u2", "last_update_ms": 1}),
             (CHUNKS_A[1], [0.9], {"id": "u3", "last_update_ms": 1})]    # 1 element -> malformed
    fp = CF.fingerprint(iter(items), {"CommentaryChunk": 3})
    assert fp["dim_histogram"] == {4: 2, 1: 1}, fp["dim_histogram"]
    assert fp["vector_dim"] == 4, fp["vector_dim"]
    assert fp["dim_anomalies"] == ["u3"], fp["dim_anomalies"]

def test_classify_change_the_exact_false_positive_is_a_read_fault_not_a_change():
    # Same uuids, same text, ONE vector digest different, last_update_ms IDENTICAL: a bad read.
    a = [(CHUNKS_A[0], [0.1, 0.2], {"id": "u1", "last_update_ms": 500}),
         (CHUNKS_A[1], [0.3, 0.4], {"id": "u2", "last_update_ms": 500})]
    b = [(CHUNKS_A[0], [0.1, 0.2], {"id": "u1", "last_update_ms": 500}),
         (CHUNKS_A[1], [0.3, 0.999], {"id": "u2", "last_update_ms": 500})]
    fpa = CF.fingerprint(iter(a), {"CommentaryChunk": 2})
    fpb = CF.fingerprint(iter(b), {"CommentaryChunk": 2})
    cls = CF.classify_change(fpa, fpb)
    assert cls["read_fault"] == ["u2"], cls
    assert cls["rewritten"] == [], cls
    assert cls["real_change"] is False, cls

def test_classify_change_a_real_rewrite_has_a_moved_timestamp():
    # The real thing: same uuids, ONE vector digest different, last_update_ms DIFFERENT.
    a = [(CHUNKS_A[0], [0.1, 0.2], {"id": "u1", "last_update_ms": 500}),
         (CHUNKS_A[1], [0.3, 0.4], {"id": "u2", "last_update_ms": 500})]
    b = [(CHUNKS_A[0], [0.1, 0.2], {"id": "u1", "last_update_ms": 500}),
         (CHUNKS_A[1], [0.3, 0.999], {"id": "u2", "last_update_ms": 777})]
    fpa = CF.fingerprint(iter(a), {"CommentaryChunk": 2})
    fpb = CF.fingerprint(iter(b), {"CommentaryChunk": 2})
    cls = CF.classify_change(fpa, fpb)
    assert cls["rewritten"] == ["u2"], cls
    assert cls["read_fault"] == [], cls
    assert cls["real_change"] is True, cls

def test_classify_change_unknowable_timestamp_is_never_benign():
    # last_update_ms None on one side with a digest difference -> rewritten, never read_fault.
    a = [(CHUNKS_A[0], [0.1, 0.2], {"id": "u1", "last_update_ms": None}),
         (CHUNKS_A[1], [0.3, 0.4], {"id": "u2", "last_update_ms": 500})]
    b = [(CHUNKS_A[0], [0.9, 0.9], {"id": "u1", "last_update_ms": None}),
         (CHUNKS_A[1], [0.3, 0.4], {"id": "u2", "last_update_ms": 500})]
    fpa = CF.fingerprint(iter(a), {"CommentaryChunk": 2})
    fpb = CF.fingerprint(iter(b), {"CommentaryChunk": 2})
    cls = CF.classify_change(fpa, fpb)
    assert cls["rewritten"] == ["u1"], cls
    assert cls["read_fault"] == [], cls
    assert cls["real_change"] is True, cls

def test_classify_change_reports_added_and_removed_uuids():
    a = [(CHUNKS_A[0], [0.1, 0.2], {"id": "u1", "last_update_ms": 500})]
    b = [(CHUNKS_A[0], [0.1, 0.2], {"id": "u1", "last_update_ms": 500}),
         (CHUNKS_A[1], [0.3, 0.4], {"id": "u2", "last_update_ms": 500})]
    fpa = CF.fingerprint(iter(a), {"CommentaryChunk": 1})
    fpb = CF.fingerprint(iter(b), {"CommentaryChunk": 2})
    cls_added = CF.classify_change(fpa, fpb)
    assert cls_added["added"] == ["u2"], cls_added
    assert cls_added["real_change"] is True, cls_added
    cls_removed = CF.classify_change(fpb, fpa)
    assert cls_removed["removed"] == ["u2"], cls_removed
    assert cls_removed["real_change"] is True, cls_removed

def test_classify_change_negative_control_identical_fingerprints():
    items = [(CHUNKS_A[0], [0.1, 0.2], {"id": "u1", "last_update_ms": 500}),
             (CHUNKS_A[1], [0.3, 0.4], {"id": "u2", "last_update_ms": 600})]
    fpa = CF.fingerprint(iter(items), {"CommentaryChunk": 2})
    fpb = CF.fingerprint(iter(items), {"CommentaryChunk": 2})
    cls = CF.classify_change(fpa, fpb)
    assert cls["added"] == [] and cls["removed"] == [] and cls["rewritten"] == [], cls
    assert cls["read_fault"] == [] and cls["dim_anomalies"] == [], cls
    assert cls["real_change"] is False, cls
    assert cls["attributable"] is True, cls

# --- difference_kind: ONE rule for read-vs-write ------------------------------------------

_A = {"text": "t", "vec": "v1", "dim": 4096, "last_update_ms": 500}


def test_difference_kind_names_a_digest_move_at_a_frozen_timestamp_a_bad_read():
    # LOAD-BEARING. This is the whole point of the function. An implementation that reported any
    # difference as a change would pass every other test here and would be the defect that put
    # two clean eval arms on the record as evidence of a write that never happened.
    b = dict(_A, vec="v2")
    assert CF.difference_kind(_A, b) == "digest-only", CF.difference_kind(_A, b)


def test_difference_kind_names_a_digest_move_with_a_moved_timestamp_a_write():
    # The other direction, asserted so the function cannot be "fixed" by always saying bad read.
    b = dict(_A, vec="v2", last_update_ms=900)
    assert CF.difference_kind(_A, b) == "write", CF.difference_kind(_A, b)


def test_difference_kind_treats_an_unknowable_timestamp_as_a_write():
    # No timestamp means no discriminator. Guessing "bad read" here would launder a real write
    # into a caveat, so the unknowable case resolves the strict way.
    b = dict(_A, vec="v2", last_update_ms=None)
    assert CF.difference_kind(_A, b) == "write", CF.difference_kind(_A, b)
    assert CF.difference_kind({"text": "t", "vec": "v1"}, {"text": "t", "vec": "v2"}) == "write"


def test_difference_kind_separates_an_identical_read_from_a_stamp_only_move():
    assert CF.difference_kind(_A, dict(_A)) == "same"
    # Digests agree but the timestamp moved: something touched the object. Whether that matters
    # is the caller policy -- the kind is still not "same".
    assert CF.difference_kind(_A, dict(_A, last_update_ms=900)) == "stamp-only"


def test_difference_kind_raises_when_a_compare_field_is_absent_from_BOTH_reads():
    # A compare list that has drifted from the sampler shape would compare None to None and
    # report "same" forever -- a check that cannot see its own failure. It fails loudly instead.
    try:
        CF.difference_kind(_A, dict(_A), fields=("text", "vec", "nonexistent_field"))
    except KeyError as e:
        assert "diverged" in str(e), str(e)
    else:
        raise AssertionError("a field absent from both reads was compared silently")


def test_a_stamp_only_move_is_still_not_a_change_on_the_start_end_axis():
    # Documents a KNOWN gap rather than hiding it: identical digests with a moved timestamp means
    # identical bytes were rewritten, which is a write, and classify_change has never counted it.
    # Extracting the rule did not widen the gate; closing it is a separate, deliberate decision.
    a = {"per_object": {"u1": dict(_A)}, "per_object_complete": True}
    b = {"per_object": {"u1": dict(_A, last_update_ms=900)}, "per_object_complete": True}
    cls = CF.classify_change(a, b)
    assert cls["real_change"] is False, cls
    assert cls["rewritten"] == [] and cls["read_fault"] == [], cls


# A hand-rolled suite reports what it happened to collect. If a test is renamed out of the
# test_ prefix, deleted, or shadowed by a duplicate name, the run still prints "N passed, 0
# failed" and looks healthy. Assert the COUNT so a silently shrinking suite fails loudly.
EXPECTED_TESTS = 27

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed")
    if len(fns) != EXPECTED_TESTS:
        print(f"FAIL suite: collected {len(fns)} tests, expected {EXPECTED_TESTS} - a test was "
              f"lost or added without updating EXPECTED_TESTS")
        f += 1
    raise SystemExit(1 if f else 0)
