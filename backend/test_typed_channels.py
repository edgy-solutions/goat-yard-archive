"""Born-tests for the two typed channels added 2026-09-27 (rulings 4 and 5).

    python backend/test_typed_channels.py

`test_degradation.py` already covers the timeout half. This file covers the two paths that
were still reporting themselves IN PROSE, and it is written the same way: the constants and
the pure functions are tested directly, and the WIRING is asserted against the source of
backend/main.py and backend/bot.py, because a constant nothing calls is exactly the defect.

Two measured incidents these tests exist to prevent recurring:

  * nf2_20260927/real_garden_genesis_3_24_misattribution_001.json -- answer field
    "Error generating answer: litellm.RateLimitError: ...", scored overall_pass=False,
    error=None, degraded=None. A provider rate limit banked as a content failure inside a
    harness that has an explicit run-level gate for 429s. The gate was blind: the 429 came
    back as HTTP 200 with the fault in the prose.
  * off_20260927d/report.md logos_001 -- answer field
    "Verification Failed: Cited sources not found in context. Missing: ['[JOHN_1_3_S01]']",
    recorded FAIL but with **refusal correct: True**. The response answered nothing, yet
    `refused` came out False, because `refused` is computed as "the answer contains an inline
    [SENTENCE_ID]" and the diagnostic had one interpolated into it. A machine-readable id in a
    user-facing error string is not a citation, and every consumer downstream read it as one.
"""

from __future__ import annotations

import io
import os
import re
import sys
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import degradation as D  # noqa: E402


def _src(name):
    return io.open(os.path.join(_HERE, name), encoding="utf-8").read()


_MAIN = _src("main.py")
_BOT = _src("bot.py")

# main.py's OWN sid pattern, lifted out of its source rather than restated here: a copy that
# drifted would make every "carries no sid-shaped text" test below pass for the wrong reason.
_SID_LINE = [ln for ln in _MAIN.splitlines() if ln.startswith("_SID_IN_ANSWER_RE = re.compile(")]
assert len(_SID_LINE) == 1, _SID_LINE
_SID_RE = re.compile(eval(_SID_LINE[0][_SID_LINE[0].index("(") + 1:_SID_LINE[0].rindex(")")]))


# Lines of backend source that are not comments. The prose this work removes is quoted in
# several comments ON PURPOSE (a fix whose reason is unrecorded gets undone), so a rot guard
# that greps raw source would either fail on the explanation or force the explanation out.
def _code_lines(src):
    return "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("#"))


_MAIN_CODE = _code_lines(_MAIN)
_BOT_CODE = _code_lines(_BOT)


# ------------------------------------------------- the sid pattern, both directions

def test_the_lifted_sid_pattern_actually_matches_a_sid():
    # Companion assertion. A pattern that matched nothing would make every test below vacuous.
    assert _SID_RE.findall("as [JOHN_1_3_S01] has it") == ["JOHN_1_3_S01"]


def test_no_substituted_answer_carries_sid_shaped_text():
    # Every string this module hands to a user in place of an answer. If one of them carried a
    # bracketed id, main.py would compute refused=False for it and the harness would score a
    # non-answer as an answer that cited something -- which is the logos_001 incident.
    for name in ("TIMEOUT_FALLBACK_ANSWER", "GENERATION_FAILURE_ANSWER",
                 "VERIFICATION_FAILURE_ANSWER"):
        text = getattr(D, name)
        assert not _SID_RE.findall(text), (name, text)
        assert "[" not in text and "]" not in text, (name, text)


# ------------------------------------------------- classify_generation_exception

def test_classify_sees_a_rate_limit_in_the_spellings_litellm_actually_produces():
    cases = [
        ("RateLimitError",
         "litellm.RateLimitError: RateLimitError: OpenAIException - Provider returned error"),
        ("APIError", "Error code: 429 - too many requests"),
        ("Exception", "rate_limit_exceeded for this key"),
    ]
    for exc, detail in cases:
        got = D.classify_generation_exception(exc, detail)
        assert got == D.DEGRADED_UPSTREAM_RATE_LIMIT, (exc, detail, got)


def test_classify_names_our_own_assertion_separately_from_an_outage():
    # A bad week for the model must never be reported as a bad week for the provider.
    assert D.classify_generation_exception(
        "DSPyAssertionError", "citation check failed") == D.DEGRADED_ASSERTION
    assert D.classify_generation_exception("AssertionError", "nope") == D.DEGRADED_ASSERTION


def test_classify_falls_back_to_generation_error_and_never_invents_a_rate_limit():
    # The safe direction, stated as a test: a missed rate limit is still degraded (still out of
    # the scoring denominator, it just fails to abort the run). An invented one aborts a healthy
    # run. So anything unrecognised lands on the generic label.
    assert D.classify_generation_exception("ValueError", "bad index") == D.DEGRADED_GENERATION_ERROR
    assert D.classify_generation_exception("", "") == D.DEGRADED_GENERATION_ERROR
    assert D.classify_generation_exception(None, None) == D.DEGRADED_GENERATION_ERROR


def test_the_four_labels_are_distinct_strings():
    labels = {D.DEGRADED_LLM_TIMEOUT, D.DEGRADED_UPSTREAM_RATE_LIMIT,
              D.DEGRADED_ASSERTION, D.DEGRADED_GENERATION_ERROR}
    assert len(labels) == 4, labels


# ------------------------------------------------- is_degraded_answer, the compatibility floor

def test_the_generation_fallback_is_degraded_by_equality():
    assert D.is_degraded_answer(D.GENERATION_FAILURE_ANSWER)
    assert D.is_degraded_answer("  " + D.GENERATION_FAILURE_ANSWER + "\n")
    assert not D.is_degraded_answer(D.GENERATION_FAILURE_ANSWER[:-10]), "a truncation is not it"


def test_the_legacy_diagnostics_are_degraded_by_prefix():
    # They were f-strings with an exception message interpolated after the colon, so no two are
    # ever byte-identical and equality cannot find them.
    assert D.is_degraded_answer(
        "Error generating answer: litellm.RateLimitError: Provider returned error")
    assert D.is_degraded_answer(
        "Generated answer could not be verified against sources.\nError: x")


def test_a_real_answer_is_not_degraded_by_either_family():
    # Companion assertion in the other direction: a matcher that returned True for everything
    # would pass every test above and empty the scoring denominator.
    assert not D.is_degraded_answer(
        "Gill writes that the covenant of grace is sure. [GENESIS_1_1_S00]")
    assert not D.is_degraded_answer("The error generating answer was the reader, not Gill.")


def test_the_verification_refusal_is_NOT_degraded_because_it_is_scoreable():
    # The carve-out, and the reason this constant lives in degradation.py with a test attached.
    # The citation verifier firing means the model cited something absent from the context:
    # nothing broke, a checkable claim failed its check. Labelling it degraded would pull a real
    # model fault OUT of the measurement -- the mirror image of scoring a timeout as a wrong answer.
    assert not D.is_degraded_answer(D.VERIFICATION_FAILURE_ANSWER), (
        "a content failure must stay in the denominator"
    )


def test_the_legacy_prefixes_are_no_longer_produced_by_this_backend():
    # The rot guard for the compatibility floor. The list exists for OLD backends; if this
    # backend still emitted one of those strings, the floor would be masking a live defect
    # instead of tolerating a stale deployment.
    for pfx in D.LEGACY_DIAGNOSTIC_ANSWER_PREFIXES:
        for name, code in (("main.py", _MAIN_CODE), ("bot.py", _BOT_CODE)):
            assert pfx not in code, (name, pfx)


def test_the_rot_guard_is_looking_at_real_code_not_an_empty_string():
    # Companion assertion: a _code_lines() that stripped everything would pass the guard above
    # while checking nothing. ("A probe that misses passes on nothing.")
    assert "async def search" in _MAIN_CODE, _MAIN_CODE[:200]
    assert "class GroundedGillBot" in _BOT_CODE
    assert len(_MAIN_CODE) > 20000 and len(_BOT_CODE) > 20000, (len(_MAIN_CODE), len(_BOT_CODE))


# ------------------------------------------------- ruling 4: main.py wiring

def test_main_no_longer_formats_the_exception_into_the_answer():
    assert 'answer = f"Error generating answer' not in _MAIN_CODE
    assert "could not be verified against sources" not in _MAIN_CODE
    assert "answer = GENERATION_FAILURE_ANSWER" in _MAIN_CODE, "no fallback is substituted at all"


def test_main_labels_the_raised_generation_and_details_it_separately():
    assert "degraded_reason = classify_generation_exception(type(e).__name__, str(e))" in _MAIN_CODE
    assert 'degraded_detail = f"{type(e).__name__}: {e}"' in _MAIN_CODE
    assert "degraded_detail: Optional[str] = None" in _MAIN_CODE, "SearchResponse cannot carry it"
    assert 'degraded_detail=locals().get("degraded_detail", None)' in _MAIN_CODE, "never returned"


def test_main_still_labels_the_timeout_the_old_way():
    # The new handler must not have displaced the branch that already worked.
    assert "degraded_reason = DEGRADED_LLM_TIMEOUT" in _MAIN_CODE
    assert "answer = TIMEOUT_FALLBACK_ANSWER" in _MAIN_CODE


def test_main_does_not_re_raise_from_the_generation_handler():
    # The old handler swallowed the exception and returned prose. The new one swallows it and
    # returns a LABEL. What must not happen is a 500: the harness needs the typed field, and a
    # crashed request produces no field at all.
    tail = _MAIN_CODE[_MAIN_CODE.index("degraded_reason = classify_generation_exception"):][:600]
    assert "raise" not in tail, tail


# ------------------------------------------------- ruling 5: the verification channel

def test_bot_reports_the_verification_failure_on_typed_fields():
    assert "answer=VERIFICATION_FAILURE_ANSWER" in _BOT_CODE
    assert 'verification_failure="cited_sources_not_in_context"' in _BOT_CODE
    assert "missing_citations=sorted(" in _BOT_CODE


def test_main_reads_the_typed_field_and_no_longer_greps_the_prose():
    assert 'if "Verification Failed:" in answer' not in _MAIN_CODE, "the sniff is still in the tree"
    assert 'verification_failure = getattr(pred, "verification_failure", None)' in _MAIN_CODE
    assert "verification_failure: Optional[str] = None" in _MAIN_CODE
    assert 'verification_failure=locals().get("verification_failure", None)' in _MAIN_CODE


def test_main_carries_the_missing_citations_into_unverified_sentence_ids():
    # The ids were the one piece of information the diagnostic string actually carried. They
    # must survive the move to a typed channel, or the fix loses a signal.
    seg = _MAIN_CODE[_MAIN_CODE.index("verification_failure = getattr(pred"):][:900]
    assert "verified = False" in seg, seg
    assert 'getattr(pred, "missing_citations", None)' in seg, seg
    assert "unverified_sentence_ids = sorted(" in seg, seg


def test_every_bot_prediction_return_carries_the_reasoning():
    # Ruling 5's root cause. main.py computes refused as "no inline SIDs in the answer", which is
    # precisely the state the three refusal returns produce -- and they dropped `reasoning`, so
    # `if refused and reasoning_text` was unsatisfiable and partial_match_sids has never once
    # been non-empty in any published run. One return missing this kills the field again.
    n_returns = _BOT_CODE.count("return dspy.Prediction(")
    n_reasoning = _BOT_CODE.count('reasoning=getattr(pred, "reasoning", "") or ""')
    assert n_returns == 4, n_returns
    assert n_reasoning == n_returns, (n_returns, n_reasoning)


def test_the_baml_path_also_carries_reasoning_into_the_prediction():
    # Both arms, or the fix only lands on OFF.
    assert 'reasoning=gill_answer.reasoning or ""' in _BOT_CODE


def test_partial_match_sids_has_a_frontend_consumer_that_has_never_rendered():
    # Why the field is fixed rather than retired: the consumer is built and shipped.
    app = os.path.join(_HERE, os.pardir, "frontend", "src", "App.tsx")
    src = io.open(app, encoding="utf-8").read()
    assert "partial_match_sids" in src, "the panel is gone -- re-open the retire-or-fix question"
    assert "response.partial_match_sids?" in src, "and it is read defensively, so absence never threw"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception:
            failed += 1
            print(f"  FAIL  {name}")
            traceback.print_exc()
    print("")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
