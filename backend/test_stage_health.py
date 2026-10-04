"""Born-tests for backend/stage_health.py (the per-stage LM health recorder for
GET /health/stages).

    python backend/test_stage_health.py

This file imports backend/stage_health.py directly, by inserting backend/ onto
sys.path and importing the bare module name -- NOT by importing backend/main.py,
which pulls in Weaviate/DSPy and would make this file unusable as a fast unit
check. The source-assertion tests near the bottom read backend/main.py as plain
text instead (the style backend/test_typed_channels.py already uses for the
same reason).

stage_health keeps module-level counters, so tests call the private
stage_health._reset_for_tests() helper (documented in that module, not part of
its production API) at the start of every test to avoid cross-test leakage in
this one process.
"""
from __future__ import annotations

import io
import json
import os
import sys
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import stage_health as sh  # noqa: E402

_MAIN = io.open(os.path.join(_HERE, "main.py"), encoding="utf-8").read()


# --------------------------------------------------------------------------
# 1. Fresh snapshot: shape and zero counters.
# --------------------------------------------------------------------------

def test_fresh_snapshot_shape_and_zero_counters():
    sh._reset_for_tests()
    snap = sh.snapshot()

    assert set(snap.keys()) == {
        "process", "requests_recorded", "expansion", "entity_lookup",
        "answer", "verifier",
    }
    assert set(snap["process"].keys()) == {"pid", "commit_sha", "started_at", "uptime_s"}
    assert set(snap["expansion"].keys()) == {"ok", "errored", "causes", "fallbacks"}
    assert set(snap["entity_lookup"].keys()) == {"modes"}
    assert set(snap["answer"].keys()) == {"ok", "not_run", "unobservable", "degraded"}
    assert set(snap["verifier"].keys()) == {"ok", "not_run", "unobservable", "failures"}

    assert snap["requests_recorded"] == 0
    assert snap["expansion"]["ok"] == 0
    assert snap["expansion"]["errored"] == 0
    assert snap["expansion"]["causes"] == {}
    assert snap["expansion"]["fallbacks"] == {}
    assert snap["entity_lookup"]["modes"] == {}
    assert snap["answer"]["ok"] == 0
    assert snap["answer"]["not_run"] == 0
    assert snap["answer"]["unobservable"] == 0
    assert snap["answer"]["degraded"] == {}
    assert snap["verifier"]["ok"] == 0
    assert snap["verifier"]["not_run"] == 0
    assert snap["verifier"]["unobservable"] == 0
    assert snap["verifier"]["failures"] == {}


# --------------------------------------------------------------------------
# 2. The safety property: a secret + a URL in the raw exception text must
#    never reach the snapshot, only the bucketed cause key.
# --------------------------------------------------------------------------

def test_missing_env_var_bucketing_hides_secret_and_url():
    sh._reset_for_tests()
    apos = chr(39)
    msg = (
        "LLM client " + apos + "LocalRouter" + apos +
        " requires environment variable " + apos + "LITELLM_PROXY_URL" + apos +
        " to be set but it is not (tried http://user:sk-SECRET123@proxy.internal:4000/v1)"
    )
    sh.record_request(
        expansion_error=msg, expansion_fallback=None, entity_lookup_mode=None,
        answer_degraded=None, verification_failure=None,
    )
    snap = sh.snapshot()
    assert snap["expansion"]["causes"] == {"missing_env_var:LITELLM_PROXY_URL": 1}

    dumped = json.dumps(snap)
    assert "sk-SECRET123" not in dumped
    assert "proxy.internal" not in dumped
    assert "http" not in dumped


# --------------------------------------------------------------------------
# 3. An unrecognised expansion error buckets to "other" and is not echoed.
# --------------------------------------------------------------------------

def test_unrecognised_expansion_error_buckets_to_other_and_hides_text():
    sh._reset_for_tests()
    secret_text = "CompletelyUnrecognisedFailureMode_xyz_secret_token_qqq"
    sh.record_request(
        expansion_error=secret_text, expansion_fallback=None, entity_lookup_mode=None,
        answer_degraded=None, verification_failure=None,
    )
    snap = sh.snapshot()
    assert snap["expansion"]["causes"] == {"other": 1}
    assert secret_text not in json.dumps(snap)


# --------------------------------------------------------------------------
# 4. Unrecognised values for every other allowlisted field bucket to "other"
#    and their text is not echoed either. One field per test.
# --------------------------------------------------------------------------

def test_unrecognised_expansion_fallback_buckets_to_other():
    sh._reset_for_tests()
    junk = "totally_unknown_fallback_kind_secret"
    sh.record_request(
        expansion_error=None, expansion_fallback=junk, entity_lookup_mode=None,
        answer_degraded=None, verification_failure=None,
    )
    snap = sh.snapshot()
    assert snap["expansion"]["fallbacks"] == {"other": 1}
    assert junk not in json.dumps(snap)


def test_unrecognised_entity_lookup_mode_buckets_to_other():
    sh._reset_for_tests()
    junk = "totally_unknown_mode_secret"
    sh.record_request(
        expansion_error=None, expansion_fallback=None, entity_lookup_mode=junk,
        answer_degraded=None, verification_failure=None,
    )
    snap = sh.snapshot()
    assert snap["entity_lookup"]["modes"] == {"other": 1}
    assert junk not in json.dumps(snap)


def test_unrecognised_answer_degraded_buckets_to_other():
    sh._reset_for_tests()
    junk = "totally_unknown_degraded_reason_secret"
    sh.record_request(
        expansion_error=None, expansion_fallback=None, entity_lookup_mode=None,
        answer_degraded=junk, verification_failure=None,
    )
    snap = sh.snapshot()
    assert snap["answer"]["degraded"] == {"other": 1}
    assert junk not in json.dumps(snap)


def test_unrecognised_verification_failure_buckets_to_other():
    sh._reset_for_tests()
    junk = "totally_unknown_verification_failure_secret"
    sh.record_request(
        expansion_error=None, expansion_fallback=None, entity_lookup_mode=None,
        answer_degraded=None, verification_failure=junk,
    )
    snap = sh.snapshot()
    assert snap["verifier"]["failures"] == {"other": 1}
    assert junk not in json.dumps(snap)


# --------------------------------------------------------------------------
# 5. Boundedness: 500 distinct junk expansion-error strings (none matching a
#    known bucket pattern) must all collapse to "other", keeping the whole
#    snapshot small regardless of how much distinct raw text is thrown at it.
# --------------------------------------------------------------------------

def _letters_only_junk(i: int) -> str:
    # Base-26, letters only -- no digits anywhere, so this can never
    # accidentally contain "404" or "429" the way a decimal index could
    # (e.g. i=404 or i=429 would otherwise self-sabotage the "other" bucket).
    digits = "abcdefghijklmnopqrstuvwxyz"
    out = []
    n = i
    for _ in range(4):
        out.append(digits[n % 26])
        n //= 26
    return "junk cause " + "".join(out) + " does not match any known bucket"


def test_boundedness_under_500_distinct_junk_causes():
    sh._reset_for_tests()
    for i in range(500):
        sh.record_request(
            expansion_error=_letters_only_junk(i),
            expansion_fallback=None, entity_lookup_mode=None,
            answer_degraded=None, verification_failure=None,
        )
    snap = sh.snapshot()
    total_keys = 0
    for section in ("expansion", "entity_lookup", "answer", "verifier"):
        for sub in snap[section].values():
            if isinstance(sub, dict):
                total_keys += len(sub)
    assert total_keys < 40, total_keys
    assert snap["expansion"]["causes"] == {"other": 500}


# --------------------------------------------------------------------------
# 6. Counts accumulate correctly across a known mixed sequence.
# --------------------------------------------------------------------------

def test_counts_accumulate_correctly_across_mixed_sequence():
    sh._reset_for_tests()
    apos = chr(39)
    env_msg = "requires environment variable " + apos + "LITELLM_PROXY_URL" + apos

    sh.record_request(
        expansion_error=None, expansion_fallback=None,
        entity_lookup_mode="full", answer_degraded=None,
        verification_failure=None,
    )
    sh.record_request(
        expansion_error=env_msg, expansion_fallback="vector_tier_degraded_suppressed",
        entity_lookup_mode="degraded_no_vector", answer_degraded="llm_timeout",
        verification_failure="cited_sources_not_in_context",
    )
    sh.record_request(
        expansion_error=env_msg, expansion_fallback="vector_tier_degraded_suppressed",
        entity_lookup_mode="degraded_no_vector", answer_degraded="llm_timeout",
        verification_failure="cited_sources_not_in_context",
    )
    sh.record_request(
        expansion_error=None, expansion_fallback="dedup_only",
        entity_lookup_mode="full", answer_degraded="upstream_rate_limit",
        verification_failure=None,
    )

    snap = sh.snapshot()
    assert snap["requests_recorded"] == 4
    assert snap["expansion"]["ok"] == 2
    assert snap["expansion"]["errored"] == 2
    assert snap["expansion"]["causes"] == {"missing_env_var:LITELLM_PROXY_URL": 2}
    assert snap["expansion"]["fallbacks"] == {
        "vector_tier_degraded_suppressed": 2, "dedup_only": 1,
    }
    assert snap["entity_lookup"]["modes"] == {"full": 2, "degraded_no_vector": 2}
    assert snap["answer"]["ok"] == 1
    assert snap["answer"]["degraded"] == {"llm_timeout": 2, "upstream_rate_limit": 1}
    assert snap["verifier"]["ok"] == 2
    assert snap["verifier"]["failures"] == {"cited_sources_not_in_context": 2}


# --------------------------------------------------------------------------
# 7. A fully healthy request increments every ok counter and the full mode.
# --------------------------------------------------------------------------

def test_fully_healthy_request_increments_ok_and_full_mode():
    sh._reset_for_tests()
    sh.record_request(
        expansion_error=None, expansion_fallback=None,
        entity_lookup_mode="full", answer_degraded=None,
        verification_failure=None,
    )
    snap = sh.snapshot()
    assert snap["expansion"]["ok"] == 1
    assert snap["answer"]["ok"] == 1
    assert snap["verifier"]["ok"] == 1
    assert snap["entity_lookup"]["modes"]["full"] == 1


# --------------------------------------------------------------------------
# 8. record_request must never raise, even on garbage (non-string) input.
# --------------------------------------------------------------------------

def test_record_request_does_not_raise_on_garbage_input():
    sh._reset_for_tests()
    sh.record_request(
        expansion_error=object(), expansion_fallback={"a": 1},
        entity_lookup_mode=12345, answer_degraded=["x"],
        verification_failure=3.14,
    )
    snap = sh.snapshot()
    json.dumps(snap)  # must not raise


# --------------------------------------------------------------------------
# 9. snapshot() is JSON-serialisable and process.commit_sha is a string.
# --------------------------------------------------------------------------

def test_snapshot_is_json_serializable_and_commit_sha_is_str():
    sh._reset_for_tests()
    sh.record_request(
        expansion_error=None, expansion_fallback=None,
        entity_lookup_mode="full", answer_degraded=None,
        verification_failure=None,
    )
    snap = sh.snapshot()
    dumped = json.dumps(snap)
    assert isinstance(dumped, str)
    assert isinstance(snap["process"]["commit_sha"], str)


# --------------------------------------------------------------------------
# 10. Source assertions over backend/main.py, read as text (the style
#     backend/test_typed_channels.py uses for the same Weaviate/DSPy reason).
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# 7. not_run is a third state. A request that never reached generation must
#    not be counted as a healthy generation.
# --------------------------------------------------------------------------

def test_not_run_is_a_third_state_and_never_counts_as_ok():
    sh._reset_for_tests()
    sh.record_request(
        expansion_error=None, expansion_fallback=None,
        entity_lookup_mode="full", answer_degraded=None,
        verification_failure=None, answer_ran=False, verifier_ran=False,
    )
    snap = sh.snapshot()
    assert snap["requests_recorded"] == 1, snap
    assert snap["answer"]["not_run"] == 1, snap["answer"]
    assert snap["answer"]["ok"] == 0, snap["answer"]
    assert snap["answer"]["degraded"] == {}, snap["answer"]
    assert snap["verifier"]["not_run"] == 1, snap["verifier"]
    assert snap["verifier"]["ok"] == 0, snap["verifier"]
    assert snap["verifier"]["failures"] == {}, snap["verifier"]
    # the stages that DID run on that path are still recorded
    assert snap["entity_lookup"]["modes"] == {"full": 1}, snap["entity_lookup"]
    assert snap["expansion"]["ok"] == 1, snap["expansion"]


def test_not_run_wins_over_a_degraded_reason_passed_alongside_it():
    # Defensive: if a caller ever passes both, "the stage did not run" is the
    # stronger statement and must not be overwritten by a reason the stage
    # could not have produced.
    sh._reset_for_tests()
    sh.record_request(
        expansion_error=None, expansion_fallback=None, entity_lookup_mode=None,
        answer_degraded="llm_timeout", verification_failure="cited_sources_not_in_context",
        answer_ran=False, verifier_ran=False,
    )
    snap = sh.snapshot()
    assert snap["answer"]["degraded"] == {}, snap["answer"]
    assert snap["answer"]["not_run"] == 1, snap["answer"]
    assert snap["verifier"]["failures"] == {}, snap["verifier"]
    assert snap["verifier"]["not_run"] == 1, snap["verifier"]


def test_an_empty_retrieval_exit_still_reports_its_expansion_cause():
    # The shape of the empty-retrieval call site in main.py: expansion failed,
    # nothing was retrieved, generation never ran. The cause must still be
    # visible -- that exit is how a dead expansion stage would hide.
    sh._reset_for_tests()
    sh.record_request(
        expansion_error=(
            "LLM client (LocalRouter) requires environment variable "
            "'LITELLM_PROXY_URL' to be set but it is not"),
        expansion_fallback="dedup_only", entity_lookup_mode="full",
        answer_degraded=None, verification_failure=None,
        answer_ran=False, verifier_ran=False,
    )
    snap = sh.snapshot()
    assert snap["expansion"]["errored"] == 1, snap["expansion"]
    assert snap["expansion"]["causes"] == {"missing_env_var:LITELLM_PROXY_URL": 1}, snap["expansion"]
    assert snap["expansion"]["fallbacks"] == {"dedup_only": 1}, snap["expansion"]
    assert snap["answer"]["not_run"] == 1, snap["answer"]


def test_unobservable_is_a_fourth_state_and_never_counts_as_ok():
    # The 0.3.x production line has no degradation.py and no
    # verification_failure local, so those two stages RAN and cannot be read.
    # "ok" would be a fabricated pass; "not_run" would be a false statement
    # about what happened.
    sh._reset_for_tests()
    sh.record_request(
        expansion_error=None, expansion_fallback="dedup_only",
        entity_lookup_mode="full",
        answer_degraded=sh.UNOBSERVABLE,
        verification_failure=sh.UNOBSERVABLE,
    )
    snap = sh.snapshot()
    assert snap["answer"]["unobservable"] == 1, snap["answer"]
    assert snap["answer"]["ok"] == 0, snap["answer"]
    assert snap["answer"]["not_run"] == 0, snap["answer"]
    assert snap["answer"]["degraded"] == {}, snap["answer"]
    assert snap["verifier"]["unobservable"] == 1, snap["verifier"]
    assert snap["verifier"]["ok"] == 0, snap["verifier"]
    assert snap["verifier"]["failures"] == {}, snap["verifier"]
    # the observable stages are unaffected
    assert snap["expansion"]["ok"] == 1, snap["expansion"]
    assert snap["entity_lookup"]["modes"] == {"full": 1}, snap["entity_lookup"]


def test_the_unobservable_sentinel_never_appears_in_the_snapshot_json():
    # It is a wire sentinel, not a bucket label. If it leaked into a degraded
    # reason key it would read as a real degradation reason to an operator.
    sh._reset_for_tests()
    sh.record_request(
        expansion_error=None, expansion_fallback=None, entity_lookup_mode=None,
        answer_degraded=sh.UNOBSERVABLE, verification_failure=sh.UNOBSERVABLE,
    )
    blob = json.dumps(sh.snapshot())
    assert sh.UNOBSERVABLE not in blob, blob
    assert "__" not in blob, blob


def test_not_run_wins_over_unobservable():
    # Both say "no health reading", but "did not run" is the stronger and more
    # specific statement and must not be masked.
    sh._reset_for_tests()
    sh.record_request(
        expansion_error=None, expansion_fallback=None, entity_lookup_mode=None,
        answer_degraded=sh.UNOBSERVABLE, verification_failure=sh.UNOBSERVABLE,
        answer_ran=False, verifier_ran=False,
    )
    snap = sh.snapshot()
    assert snap["answer"]["not_run"] == 1 and snap["answer"]["unobservable"] == 0, snap["answer"]
    assert snap["verifier"]["not_run"] == 1 and snap["verifier"]["unobservable"] == 0, snap["verifier"]


def test_source_has_health_stages_route():
    assert '@app.get("/health/stages")' in _MAIN


def test_source_health_route_unchanged():
    assert 'return {"status": "ok", "service": "goat-yard-archive"}' in _MAIN


def test_source_records_on_every_search_response_exit():
    # Derived, not a pinned snapshot: a search request that returns without
    # recording is invisible in the snapshot, so the number of call sites has
    # to equal the number of SearchResponse exits. Add a third exit without a
    # record call and this fails. It was 1-to-2 when this route was first
    # written -- the empty-retrieval exit returned unrecorded.
    exits = _MAIN.count("return SearchResponse(")
    calls = _MAIN.count("stage_health.record_request(")
    assert exits >= 2, exits
    assert calls == exits, (calls, exits)


def test_source_expansion_error_assigned_outside_stages_capture_guard():
    marker = "_expansion_error = str(e)"
    assert _MAIN.count(marker) == 1

    idx = _MAIN.index(marker)
    line_start = _MAIN.rfind("\n", 0, idx) + 1
    line_end = _MAIN.index("\n", idx)
    assign_line = _MAIN[line_start:line_end]
    assign_indent = len(assign_line) - len(assign_line.lstrip(" "))

    guard_marker = "if stages_capture is not None:"
    guard_idx = _MAIN.rfind(guard_marker, 0, idx)
    assert guard_idx != -1, "no preceding stages_capture guard found"
    guard_line_start = _MAIN.rfind("\n", 0, guard_idx) + 1
    guard_line_end = _MAIN.index("\n", guard_idx)
    guard_line = _MAIN[guard_line_start:guard_line_end]
    guard_indent = len(guard_line) - len(guard_line.lstrip(" "))

    # Same indentation as the guard line itself means a SIBLING statement,
    # not a statement inside the guard's body (which would be indented
    # four spaces deeper).
    assert assign_indent == guard_indent, (assign_indent, guard_indent)


if __name__ == "__main__":
    EXPECTED_TEST_COUNT = 22
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    if len(tests) != EXPECTED_TEST_COUNT:
        print(
            "FAIL  expected %d tests, collected %d -- a test silently disappeared"
            % (EXPECTED_TEST_COUNT, len(tests))
        )
        sys.exit(1)

    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("  ok    %s" % name)
        except Exception:
            failed += 1
            print("  FAIL  %s" % name)
            traceback.print_exc()
    print("")
    print("%d/%d passed" % (len(tests) - failed, len(tests)))
    sys.exit(1 if failed else 0)
