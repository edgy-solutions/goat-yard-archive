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
    sys.exit(1 if failed else 0)
