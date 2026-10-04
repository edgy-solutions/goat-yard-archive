"""Born-tests for the corpus half of run integrity. Offline: no Weaviate, no network, no httpx.

    python evals/test_corpus_state.py

The load-bearing tests here are the ones that could not pass against a weaker implementation:

  * `test_a_revectorisation_with_identical_text_is_detected` -- a text-only fingerprint passes
    every other test in this file and is blind to the failure the module was written for.
  * `test_corpus_changed_can_actually_return_False` -- an implementation that returned True for
    everything would satisfy each change test and make every run a violation.
  * `test_an_unread_corpus_is_provisional_but_NOT_a_violation` with
    `test_a_changed_corpus_IS_a_violation` -- the asymmetry is the design, so both directions are
    asserted rather than one.
  * `test_resolve_refuses_to_default_to_localhost` -- the silent-success failure. A default would
    make every other test pass while stamping runs with a fingerprint of the wrong instance.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import corpus_state as CS  # noqa: E402

FP = {"counts": {"CommentaryChunk": 7294, "TheologicalEntity": 8433}, "chunk_count": 7294,
      "content_sha256": "6cbb3363" + "a" * 56, "vector_sha256": "dc7968e3" + "b" * 56,
      "n_hashed": 7294, "n_vectors_hashed": 7294}


def _fp(**over):
    d = dict(FP)
    d.update(over)
    return lambda url, include_vectors: d


def _state(**over):
    return CS.corpus_state("192.168.1.54:80", _fingerprint=_fp(**over))


# --- url resolution -------------------------------------------------------------------

def test_normalize_accepts_the_three_forms_this_repo_writes():
    assert CS.normalize_corpus_url("192.168.1.54:80") == "192.168.1.54:80"
    assert CS.normalize_corpus_url("http://192.168.1.54:80") == "192.168.1.54:80"
    assert CS.normalize_corpus_url("http://192.168.1.54:80/") == "192.168.1.54:80"
    assert CS.normalize_corpus_url("weaviate.gya-backend") == "weaviate.gya-backend"


def test_resolve_refuses_to_default_to_localhost():
    # corpus_fingerprint.fingerprint_instance defaults to localhost. Here that default would not
    # fail -- it would fingerprint something no question was asked of, and the run would look
    # stamped. Absence must be reported as absence.
    url, reason = CS.resolve_corpus_url({})
    assert url is None, url
    assert reason == CS.UNAVAILABLE + "WEAVIATE_URL-is-not-set", reason


def test_resolve_finds_a_url_that_IS_set():
    # The companion assertion: a resolver that always refused would pass the test above.
    url, reason = CS.resolve_corpus_url({"WEAVIATE_URL": "http://192.168.1.54:80"})
    assert url == "192.168.1.54:80", url
    assert reason is None


def test_a_state_with_no_url_and_no_env_claims_nothing():
    # Called with url=None the module resolves from the real environment, so drive the refusal
    # through resolve_corpus_url and assert the record it produces instead of mutating os.environ.
    st = CS.unavailable_state(CS.resolve_corpus_url({})[1])
    assert st["available"] is False
    assert set(st) == set(CS.KEYS)


# --- a successful read ----------------------------------------------------------------

def test_a_successful_state_carries_both_hashes_and_the_url():
    st = _state()
    assert st["available"] is True, st
    assert st["chunk_count"] == 7294
    assert st["content_sha256"] == FP["content_sha256"]
    assert st["vector_sha256"] == FP["vector_sha256"], "the vector hash is half the point"
    assert st["n_vectors_hashed"] == 7294
    assert st["weaviate_url"] == "192.168.1.54:80"
    assert st["include_vectors"] is True
    assert st["unavailable_reason"] is None
    assert isinstance(st["seconds"], float)
    assert set(st) == set(CS.KEYS), sorted(set(st) ^ set(CS.KEYS))


def test_a_read_that_raises_is_recorded_not_swallowed():
    def boom(url, include_vectors):
        raise ConnectionError("connect timed out")
    st = CS.corpus_state("192.168.1.54:80", _fingerprint=boom)
    assert st["available"] is False
    assert st["unavailable_reason"].startswith(CS.UNAVAILABLE + "read-failed:ConnectionError"), st
    assert "connect timed out" in st["unavailable_reason"]
    assert st["weaviate_url"] == "192.168.1.54:80", "which instance failed is part of the record"
    assert set(st) == set(CS.KEYS)


def test_an_empty_corpus_is_unavailable_not_a_valid_fingerprint():
    # hashlib is perfectly happy to hash nothing. An empty-corpus fingerprint is stable, comparable
    # and completely uninformative, and two arms against an empty instance would compare identical.
    st = _state(chunk_count=0, n_hashed=0, n_vectors_hashed=0,
                counts={"CommentaryChunk": 0, "TheologicalEntity": 0})
    assert st["available"] is False, st
    assert st["unavailable_reason"] == CS.UNAVAILABLE + "corpus-read-returned-no-chunks", st


def test_vectors_requested_but_absent_downgrades_the_claim_instead_of_lying():
    st = _state(vector_sha256=None, n_vectors_hashed=0)
    assert st["available"] is True, "the text fingerprint is still real and still worth recording"
    assert st["include_vectors"] is False, st
    assert st["unavailable_reason"] == CS.UNAVAILABLE + "vectors-requested-but-none-were-returned"
    # and the comparison must then narrow its own claim rather than quietly comparing None to None
    changed, scope = CS.corpus_changed(st, st)
    assert changed is False
    assert scope.startswith("text-only"), scope


# --- the comparison: three states -----------------------------------------------------

def test_corpus_changed_can_actually_return_False():
    # The companion assertion. An implementation that returned True for everything would pass
    # every change test below and mark every run a violation.
    changed, scope = CS.corpus_changed(_state(), _state())
    assert changed is False, changed
    assert scope == "text+vectors", scope


def test_a_text_change_is_detected():
    changed, _ = CS.corpus_changed(_state(), _state(content_sha256="f" * 64))
    assert changed is True


def test_a_revectorisation_with_identical_text_is_detected():
    # THE test. Same chunk count, byte-identical text, different embeddings: retrieval order moves
    # under a corpus that looks untouched. A text-only fingerprint reports this pair as identical
    # and an arm comparison then attributes the shift to the code change under test.
    a = _state()
    b = _state(vector_sha256="f" * 64)
    assert a["content_sha256"] == b["content_sha256"], "the premise: text is identical"
    assert a["chunk_count"] == b["chunk_count"]
    changed, scope = CS.corpus_changed(a, b)
    assert changed is True, "a re-vectorisation is a corpus change"
    assert scope == "text+vectors"


def test_a_count_change_is_detected_even_if_a_hash_somehow_matched():
    changed, _ = CS.corpus_changed(_state(), _state(chunk_count=7295))
    assert changed is True


def test_an_unread_sample_makes_the_answer_None_never_False():
    bad = CS.unavailable_state("read-failed:ConnectionError")
    for a, b in ((_state(), bad), (bad, _state()), (bad, bad)):
        changed, scope = CS.corpus_changed(a, b)
        assert changed is None, (changed, scope)
        assert scope.startswith("not-compared"), scope


def test_mixed_vector_scope_compares_text_and_SAYS_it_did_only_that():
    a = _state()
    b = _state(vector_sha256=None, n_vectors_hashed=0)
    changed, scope = CS.corpus_changed(a, b)
    assert changed is False, "the text is identical and that is all that was comparable"
    assert "re-vectorisation during this run would NOT have been detected" in scope, scope


# --- the run block --------------------------------------------------------------------

def test_a_clean_block_is_not_provisional_and_raises_nothing():
    b = CS.corpus_run_block(_state(), _state())
    assert b["changed_during_run"] is False
    assert b["provisional"] is False, b
    assert b["violations"] == []
    assert b["skipped"] is False
    assert b["comparison_scope"] == "text+vectors"


def test_a_changed_corpus_IS_a_violation():
    b = CS.corpus_run_block(_state(), _state(content_sha256="f" * 64))
    assert b["changed_during_run"] is True
    assert b["provisional"] is True
    assert len(b["violations"]) == 1, b["violations"]
    v = b["violations"][0]
    assert "CORPUS CHANGED MID-RUN" in v
    # the violation must name the two states, or the reader cannot tell what moved
    assert "chunks=7294" in v and "6cbb3363" in v, v


def test_an_unread_corpus_is_provisional_but_NOT_a_violation():
    # The asymmetry, asserted in both directions. Retrieval reaches Weaviate over gRPC on one host
    # while this fingerprint reads REST on another, so a metadata hiccup must not destroy the exit
    # code of a run whose answers were all really scored.
    bad = CS.unavailable_state("read-failed:ConnectionError")
    b = CS.corpus_run_block(bad, bad)
    assert b["changed_during_run"] is None
    assert b["provisional"] is True, "it cannot be cited"
    assert b["violations"] == [], "but it is not a violation"


def test_skipping_the_fingerprint_is_provisional():
    b = CS.corpus_run_block(_state(), _state(), skipped=True)
    assert b["changed_during_run"] is False, "the samples are still recorded if they were taken"
    assert b["skipped"] is True
    assert b["provisional"] is True, "an unstamped run cannot be cited even if nothing moved"
    assert b["violations"] == []


def test_the_block_records_both_samples_verbatim():
    a, z = _state(), _state(content_sha256="f" * 64)
    b = CS.corpus_run_block(a, z)
    assert b["at_start"] == a and b["at_end"] == z, "a summary that cannot say what it read is worse"


# --- attributed comparison (classify_change wired through corpus_changed / corpus_run_block) ----

def test_corpus_changed_is_None_for_a_read_fault_only_difference_and_names_the_uuid():
    # THE false positive this spec closes: vector_sha256 moved, last_update_ms did not. That is a
    # bad read, not a corpus change, and it must say which uuid -- not just that something moved.
    po_a = {"u1": {"text": "t", "vec": "v1", "dim": 4096, "last_update_ms": 500}}
    po_b = {"u1": {"text": "t", "vec": "v2", "dim": 4096, "last_update_ms": 500}}
    a = _state(per_object=po_a, per_object_complete=True)
    b = _state(per_object=po_b, per_object_complete=True)
    changed, scope = CS.corpus_changed(a, b)
    assert changed is None, changed
    assert scope.startswith("not-compared:"), scope
    assert "bad read" in scope, scope
    assert "u1" in scope, scope


def test_read_fault_only_is_provisional_when_no_reread_was_attempted():
    # The DEFAULT branch, and the one that keeps the narrowing honest: with no
    # post-run re-read, a read fault is unconfirmed and the arm is still uncitable.
    po_a = {"u1": {"text": "t", "vec": "v1", "dim": 4096, "last_update_ms": 500}}
    po_b = {"u1": {"text": "t", "vec": "v2", "dim": 4096, "last_update_ms": 500}}
    a = _state(per_object=po_a, per_object_complete=True)
    b = _state(per_object=po_b, per_object_complete=True)
    block = CS.corpus_run_block(a, b)
    assert block["changed_during_run"] is None, block
    assert block["provisional"] is True, block
    assert block["violations"] == [], block["violations"]
    assert block["read_fault_uuids"] == ["u1"], block["read_fault_uuids"]
    assert "re-read" in block["note"].lower(), block["note"]


def test_corpus_run_block_an_attributable_real_change_is_still_a_violation():
    # The companion assertion: a real (timestamp-moved) change must still trip the SAME violation
    # wording as the old corpus-wide fold, not a quieter one just because it is now attributed.
    po_a = {"u1": {"text": "t", "vec": "v1", "dim": 4096, "last_update_ms": 500}}
    po_b = {"u1": {"text": "t", "vec": "v2", "dim": 4096, "last_update_ms": 999}}
    a = _state(per_object=po_a, per_object_complete=True)
    b = _state(per_object=po_b, per_object_complete=True)
    block = CS.corpus_run_block(a, b)
    assert block["changed_during_run"] is True, block
    assert block["provisional"] is True, block
    assert len(block["violations"]) == 1, block["violations"]
    assert "CORPUS CHANGED MID-RUN" in block["violations"][0]


def test_a_sample_with_dim_anomalies_is_unavailable_with_a_read_fault_reason():
    # Page-level re-fetching in fingerprint_rest already tried to repair this; if an anomaly
    # survives to corpus_state, every attempt failed and the sample cannot be trusted at all.
    st = _state(dim_anomalies=["u9"])
    assert st["available"] is False, st
    assert "read-fault" in st["unavailable_reason"], st["unavailable_reason"]
    assert set(st) == set(CS.KEYS)


def test_the_verdict_and_the_naming_cannot_disagree_about_a_read_fault():
    # corpus_changed decides the verdict and corpus_run_block names the objects. They used to
    # derive attributability independently, which is two copies of one policy; if they ever drift
    # the block can print zero uuids under a None verdict that was caused by named uuids.
    po_a = {"u1": {"text": "t", "vec": "v1", "dim": 4096, "last_update_ms": 500},
            "u2": {"text": "t", "vec": "v9", "dim": 4096, "last_update_ms": 700}}
    po_b = {"u1": {"text": "t", "vec": "v2", "dim": 4096, "last_update_ms": 500},
            "u2": {"text": "t", "vec": "v9", "dim": 4096, "last_update_ms": 700}}
    a = _state(per_object=po_a, per_object_complete=True)
    b = _state(per_object=po_b, per_object_complete=True)
    changed, scope = CS.corpus_changed(a, b)
    block = CS.corpus_run_block(a, b)
    assert changed is None, changed
    assert block["changed_during_run"] is None, block["changed_during_run"]
    assert block["read_fault_uuids"] == ["u1"], block["read_fault_uuids"]
    assert "u1" in scope and "u2" not in scope, scope       # only the object that actually moved


def test_a_long_read_fault_list_is_capped_in_the_prose_and_whole_in_the_field():
    # A reason a human reads must not be hundreds of uuids. The machine-readable field is NOT
    # truncated: capping the attribution itself would be the quiet loss this change exists to end.
    uuids = ["u%02d" % i for i in range(12)]
    po_a = {u: {"text": "t", "vec": "v1", "dim": 4096, "last_update_ms": 500} for u in uuids}
    po_b = {u: {"text": "t", "vec": "v2", "dim": 4096, "last_update_ms": 500} for u in uuids}
    a = _state(per_object=po_a, per_object_complete=True)
    b = _state(per_object=po_b, per_object_complete=True)
    changed, scope = CS.corpus_changed(a, b)
    block = CS.corpus_run_block(a, b)
    assert changed is None, changed
    assert "12 objects differ" in scope, scope
    assert "(+2 more)" in scope, scope
    assert "u11" not in scope, scope
    assert block["read_fault_uuids"] == uuids, block["read_fault_uuids"]
    assert "(+2 more)" in block["note"], block["note"]


# --- the post-run re-read: what lets a read fault become a caveat instead of provisional -------
#
# Ruling (2026-10-04): `provisional` narrows to ATTRIBUTABLE change, on the condition that the
# read-faulted objects are RE-READ after the run and still match the START sample. The tests that
# could not pass against a weaker implementation are marked below; the rest pin the typed
# non-confirmations, which exist so that "we did not check" can never read as "it was fine".


def _rr(per_object, available=True, reason=None):
    return {"available": available, "unavailable_reason": reason,
            "weaviate_url": "192.168.1.54:80", "include_vectors": True,
            "requested": sorted(per_object or {}), "per_object": per_object,
            "read_faults": [], "seconds": 0.1}


_GOOD = {"text": "t", "vec": "v1", "dim": 4096, "last_update_ms": 500}
_BAD = {"text": "t", "vec": "v2", "dim": 4096, "last_update_ms": 500}


def _fault_pair():
    """Start/end samples differing on u1 ONLY by a vector digest at an identical timestamp --
    classify_change's read_fault signature, which is what the run actually produced."""
    return (_state(per_object={"u1": dict(_GOOD)}, per_object_complete=True),
            _state(per_object={"u1": dict(_BAD)}, per_object_complete=True))


def test_a_read_fault_confirmed_by_a_reread_is_a_caveat_and_NOT_provisional():
    a, b = _fault_pair()
    block = CS.corpus_run_block(a, b, reread=_rr({"u1": dict(_GOOD)}))
    assert block["changed_during_run"] is None, block["changed_during_run"]
    assert block["provisional"] is False, block            # the whole point of the ruling
    assert block["reread_confirmed"] is True, block["reread"]
    assert block["violations"] == [], block["violations"]
    assert block["reread"]["status"] == "confirmed", block["reread"]
    # citable, but never silent: the uuids survive into a caveat a reader sees.
    assert block["read_fault_uuids"] == ["u1"], block["read_fault_uuids"]
    assert len(block["caveats"]) == 1, block["caveats"]
    assert "u1" in block["caveats"][0], block["caveats"][0]
    assert "READ-FAULT CAVEAT" in block["caveats"][0], block["caveats"][0]


def test_the_reread_must_match_the_START_sample_not_the_end_sample():
    # LOAD-BEARING. The end sample is the one suspected of being misread, so an implementation
    # that compared the re-read against it would "confirm" exactly the corrupt value it was
    # supposed to rule out -- and would pass every other test in this section.
    a, b = _fault_pair()
    block = CS.corpus_run_block(a, b, reread=_rr({"u1": dict(_BAD)}))
    assert block["provisional"] is True, block
    assert block["reread_confirmed"] is False, block["reread"]
    assert block["reread"]["status"] == "differs", block["reread"]
    assert block["reread"]["differing"] == ["u1"], block["reread"]


def test_a_reread_whose_timestamp_moved_is_a_write_not_a_confirmation():
    # Same digests as at_start but a later last_update_ms: something WROTE between the end sample
    # and the re-read. That is the opposite of the finding being confirmed, so it must not match.
    a, b = _fault_pair()
    moved = dict(_GOOD, last_update_ms=900)
    block = CS.corpus_run_block(a, b, reread=_rr({"u1": moved}))
    assert block["provisional"] is True, block
    assert block["reread"]["status"] == "differs", block["reread"]


def test_a_reread_that_could_not_be_performed_keeps_the_arm_provisional():
    a, b = _fault_pair()
    block = CS.corpus_run_block(a, b, reread=_rr(None, available=False,
                                                 reason=CS.UNAVAILABLE + "reread-failed:ReadError"))
    assert block["provisional"] is True, block
    assert block["reread"]["status"] == "unavailable", block["reread"]
    assert "reread-failed" in block["reread"]["detail"], block["reread"]["detail"]


def test_a_reread_that_does_not_return_the_object_confirms_nothing():
    # An absent object is NOT a match. Treating "not in the response" as "unchanged" is the
    # silent-success shape this module exists to refuse.
    a, b = _fault_pair()
    block = CS.corpus_run_block(a, b, reread=_rr({}))
    assert block["provisional"] is True, block
    assert block["reread"]["status"] == "missing", block["reread"]
    assert block["reread"]["missing"] == ["u1"], block["reread"]


def test_a_reread_cannot_rescue_an_ATTRIBUTABLE_change():
    # LOAD-BEARING. The narrowing applies to read faults only. A real (timestamp-moved) change
    # must stay a violation no matter what any re-read says about it.
    po_a = {"u1": {"text": "t", "vec": "v1", "dim": 4096, "last_update_ms": 500}}
    po_b = {"u1": {"text": "t", "vec": "v2", "dim": 4096, "last_update_ms": 999}}
    a = _state(per_object=po_a, per_object_complete=True)
    b = _state(per_object=po_b, per_object_complete=True)
    block = CS.corpus_run_block(a, b, reread=_rr({"u1": dict(_GOOD)}))
    assert block["changed_during_run"] is True, block["changed_during_run"]
    assert block["provisional"] is True, block
    assert block["reread_confirmed"] is False, block["reread"]
    assert len(block["violations"]) == 1, block["violations"]


def test_a_reread_cannot_rescue_an_UNREAD_sample():
    # changed is None for two reasons -- a read fault, and a sample that could not be read at all.
    # Only the first is attributable, so only the first is eligible for the caveat.
    bad = CS.unavailable_state("read-failed:ReadError", "192.168.1.54:80")
    block = CS.corpus_run_block(bad, bad, reread=_rr({"u1": dict(_GOOD)}))
    assert block["changed_during_run"] is None, block["changed_during_run"]
    assert block["provisional"] is True, block
    assert block["read_fault_uuids"] == [], block["read_fault_uuids"]
    assert block["reread"]["status"] == "not-needed", block["reread"]
    assert block["caveats"] == [], block["caveats"]


def test_a_skipped_fingerprint_is_provisional_whatever_a_reread_says():
    unread = CS.unavailable_state("--corpus-fingerprint-skip", include_vectors=False)
    block = CS.corpus_run_block(unread, unread, skipped=True, reread=_rr({"u1": dict(_GOOD)}))
    assert block["provisional"] is True, block


def test_reread_state_records_what_it_asked_for_and_what_came_back():
    st = CS.reread_state(["u1"], url="192.168.1.54:80",
                         _reread=lambda url, uuids, iv: {"u1": dict(_GOOD)})
    assert st["available"] is True, st
    assert st["requested"] == ["u1"], st
    assert st["per_object"] == {"u1": _GOOD}, st
    assert set(st) == set(CS.REREAD_KEYS), sorted(set(st) ^ set(CS.REREAD_KEYS))


def test_reread_state_turns_a_raising_reader_into_a_typed_unavailable():
    def boom(url, uuids, iv):
        raise RuntimeError("connection reset")

    st = CS.reread_state(["u1"], url="192.168.1.54:80", _reread=boom)
    assert st["available"] is False, st
    assert st["unavailable_reason"].startswith(CS.UNAVAILABLE), st
    assert "RuntimeError" in st["unavailable_reason"], st
    assert "connection reset" in st["unavailable_reason"], st
    assert set(st) == set(CS.REREAD_KEYS), sorted(set(st) ^ set(CS.REREAD_KEYS))


def test_reread_state_claims_nothing_when_no_url_is_resolvable():
    st = CS.reread_state(["u1"], _reread=lambda url, uuids, iv: {"u1": dict(_GOOD)})
    if st["weaviate_url"] is None:                 # WEAVIATE_URL unset in this environment
        assert st["available"] is False, st
        assert st["unavailable_reason"].startswith(CS.UNAVAILABLE), st


def test_the_live_reread_reuses_the_fingerprint_digest_arithmetic():
    # The re-read must digest objects EXACTLY as the samples were digested; a second copy of that
    # arithmetic would mismatch the stored sample on the arithmetic rather than on the data, and
    # would read as the corruption it is trying to rule out. This asserts the derivation (one
    # digest implementation, fed by fingerprint_rest's own tuples) rather than re-deriving it.
    src = (Path(__file__).resolve().parent / "corpus_state.py").read_text(encoding="utf-8")
    assert "CF.fingerprint(FR.fetch_objects(" in src, "the re-read no longer digests via fingerprint"
    assert "hashlib" not in src, "corpus_state has grown its own digest arithmetic"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("  PASS  " + name)
        except Exception:
            failed += 1
            print("  FAIL  " + name)
            traceback.print_exc()
    print("")
    print(str(len(tests) - failed) + "/" + str(len(tests)) + " passed")
    # A hand-rolled suite reports what it happened to collect. If a test is renamed out of the
    # test_ prefix, deleted, or shadowed by a duplicate name, the run still prints "N passed, 0
    # failed" and looks healthy. Assert the COUNT so a dropped test is caught.
    EXPECTED_TESTS = 37
    if len(tests) != EXPECTED_TESTS:
        print("FAIL suite: collected " + str(len(tests)) + " tests, expected " +
              str(EXPECTED_TESTS) + " - a test was lost or added without updating EXPECTED_TESTS")
        failed += 1
    sys.exit(1 if failed else 0)
