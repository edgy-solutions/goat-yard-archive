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
import re
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
    assert set(snap["expansion"].keys()) == {"ok", "errored", "causes", "fallbacks",
                                             "retries"}
    assert set(snap["expansion"]["retries"].keys()) == {
        "total", "calls_with_retries", "max_observed", "bound_exhausted", "unobserved",
    }
    assert set(snap["entity_lookup"].keys()) == {"modes"}
    assert set(snap["answer"].keys()) == {"ok", "not_run", "unobservable", "degraded"}
    assert set(snap["verifier"].keys()) == {"ok", "not_run", "unobservable", "failures"}

    assert snap["requests_recorded"] == 0
    assert snap["expansion"]["ok"] == 0
    assert snap["expansion"]["errored"] == 0
    assert snap["expansion"]["causes"] == {}
    assert snap["expansion"]["fallbacks"] == {}
    assert snap["expansion"]["retries"] == {
        "total": 0, "calls_with_retries": 0, "max_observed": 0,
        "bound_exhausted": 0, "unobserved": 0,
    }
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


# --------------------------------------------------------------------------
# 9. Retry accounting for `retry_policy BoundedTransport` (baml_src/main.baml).
#
#    Why these exist: one truncated HTTP response body -- a single request in
#    67 -- voided a 65-run scored arm, because nothing in baml_src retried and
#    the expansion stage therefore failed hard on a transport hiccup. The
#    policy that fixes it is bounded at 3 retries, and a bound that nobody
#    measures is a bound nobody can tell has been hit. These tests are about
#    whether the bound is OBSERVABLE, not whether retrying works (that is
#    backend/test_expansion_retry.py, which drives a real truncating socket).
# --------------------------------------------------------------------------

def test_the_retry_bound_constant_matches_the_policy_declared_in_baml_src():
    # DERIVED, not restated. stage_health cannot import baml, so it carries its own
    # MAX_RETRIES_CONFIGURED; if the policy in baml_src is edited and the constant is
    # not, every bound_exhausted count silently measures against a stale bound. A
    # failure here means the two have drifted -- fix the constant, not this test.
    baml = io.open(os.path.join(os.path.dirname(_HERE), "baml_src", "main.baml"),
                   encoding="utf-8").read()
    assert "retry_policy BoundedTransport" in baml, "the policy itself is gone from baml_src"
    m = re.search(r"retry_policy\s+BoundedTransport\s*\{[^}]*?max_retries\s+(\d+)", baml,
                  re.S)
    assert m is not None, "could not parse max_retries out of the BoundedTransport policy"
    assert sh.MAX_RETRIES_CONFIGURED == int(m.group(1)), (
        sh.MAX_RETRIES_CONFIGURED, int(m.group(1)))


def test_the_expansion_client_actually_carries_the_retry_policy():
    # The policy existing is not the policy being USED. A failure here means the retry was
    # declared and then not attached to the client the expansion call runs on, which looks
    # exactly like a fix and behaves exactly like the defect.
    baml = io.open(os.path.join(os.path.dirname(_HERE), "baml_src", "main.baml"),
                   encoding="utf-8").read()
    m = re.search(r"client<llm>\s+LocalRouter\s*\{(.*?)\n\}", baml, re.S)
    assert m is not None, "LocalRouter client block not found"
    assert "retry_policy BoundedTransport" in m.group(1), m.group(1)


def test_retries_are_summed_and_the_high_water_mark_is_kept():
    sh._reset_for_tests()
    for n in (0, 2, 1):
        sh.record_request(expansion_error=None, expansion_fallback=None,
                          expansion_retries=n, entity_lookup_mode="full",
                          answer_degraded=None, verification_failure=None)
    r = sh.snapshot()["expansion"]["retries"]
    assert r["total"] == 3, r
    assert r["calls_with_retries"] == 2, r      # the 0 does not count as a retried call
    assert r["max_observed"] == 2, r
    assert r["bound_exhausted"] == 0, r
    assert r["unobserved"] == 0, r


def test_an_unobserved_retry_count_is_not_recorded_as_zero():
    # The whole point. A request whose collector was missing tells us NOTHING about
    # retries. Folding that into total=0 would report a healthy transport on no evidence --
    # the same silence the not_run/unobservable states exist to prevent elsewhere in this
    # module. A failure here means a blind run can pass the preflight.
    sh._reset_for_tests()
    sh.record_request(expansion_error=None, expansion_fallback=None,
                      expansion_retries=None, entity_lookup_mode="full",
                      answer_degraded=None, verification_failure=None)
    r = sh.snapshot()["expansion"]["retries"]
    assert r["unobserved"] == 1, r
    assert r["total"] == 0 and r["calls_with_retries"] == 0, r
    assert r["max_observed"] == 0 and r["bound_exhausted"] == 0, r


def test_exhausting_the_bound_is_counted_separately_from_merely_retrying():
    # Reaching the bound means the transport failed every allowed attempt in a row: broken,
    # not flaky. The scored-run preflight refuses on this count, so it must not be
    # indistinguishable from an ordinary successful retry.
    sh._reset_for_tests()
    sh.record_request(expansion_error=None, expansion_fallback=None,
                      expansion_retries=1, entity_lookup_mode="full",
                      answer_degraded=None, verification_failure=None)
    sh.record_request(expansion_error=None, expansion_fallback=None,
                      expansion_retries=sh.MAX_RETRIES_CONFIGURED,
                      entity_lookup_mode="full",
                      answer_degraded=None, verification_failure=None)
    r = sh.snapshot()["expansion"]["retries"]
    assert r["bound_exhausted"] == 1, r
    assert r["calls_with_retries"] == 2, r
    assert r["max_observed"] == sh.MAX_RETRIES_CONFIGURED, r


def test_a_bool_is_not_a_retry_count():
    # isinstance(True, int) is True in Python, so a flag passed where a count belongs would
    # otherwise be recorded as "1 retry". It is an unobserved count, not a retry.
    sh._reset_for_tests()
    sh.record_request(expansion_error=None, expansion_fallback=None,
                      expansion_retries=True, entity_lookup_mode="full",
                      answer_degraded=None, verification_failure=None)
    r = sh.snapshot()["expansion"]["retries"]
    assert r["unobserved"] == 1, r
    assert r["total"] == 0 and r["calls_with_retries"] == 0, r


def test_retries_from_baml_log_is_attempts_minus_one_and_ignores_selected():
    # Measured against baml_py 0.211.1: LLMCall.selected is True on EVERY call, including
    # the three that failed, so it cannot identify the winning attempt. Counting "calls
    # where not selected" would report 0 retries on a call that retried three times.
    class _Call:
        def __init__(self):
            self.selected = True

    class _Log:
        def __init__(self, n):
            self.calls = [_Call() for _ in range(n)]

    assert sh.retries_from_baml_log(_Log(4)) == 3
    assert sh.retries_from_baml_log(_Log(1)) == 0
    assert all(c.selected for c in _Log(4).calls), "the premise of this test"


def test_retries_from_baml_log_returns_None_when_it_cannot_observe():
    # None is a real answer that the caller keeps distinct from 0 (see the unobserved test).
    class _NoCalls:
        pass

    class _EmptyCalls:
        calls: list = []

    assert sh.retries_from_baml_log(None) is None
    assert sh.retries_from_baml_log(_NoCalls()) is None
    assert sh.retries_from_baml_log(_EmptyCalls()) is None


def test_source_passes_a_per_request_collector_to_the_expansion_call():
    # A module-level collector would accumulate across requests and make len(calls) a
    # running total, so every request after the first would look like it retried. Assert
    # the collector is constructed INSIDE the handler and handed to the expansion call.
    assert "_expansion_collector = baml_py.Collector(" in _MAIN
    assert '"collector": _expansion_collector' in _MAIN
    # and that the count actually reaches the recorder at every exit
    assert _MAIN.count("expansion_retries=stage_health.retries_from_baml_log(") == \
        _MAIN.count("expansion_fallback=locals().get(\"fallback_kind\", None),")


if __name__ == "__main__":
    EXPECTED_TEST_COUNT = 31
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
        except KeyboardInterrupt:
            raise
        # SystemExit is NOT an Exception, so `except Exception` let a test that reaches sys.exit
        # end the WHOLE run silently -- no summary line, which reads as a shorter suite. Witnessed
        # 2026-10-11 in evals/test_gate_paired.py (argparse exits 2 on an unrecognized flag).
        except BaseException:
            failed += 1
            print("  FAIL  %s" % name)
            traceback.print_exc()
    print("")
    print("%d/%d passed" % (len(tests) - failed, len(tests)))
    sys.exit(1 if failed else 0)
