"""Born-tests for degradation labelling. Run: python backend/test_degradation.py

Repo convention is a plain script with a __main__ runner (see
pipeline/common/test_endpoint_guard.py); pytest is not in the venv.

The tests that matter are the WIRING tests at the bottom. A constant that nothing calls is
the exact defect this work exists to fix: the timeout fallback was always there, and the
harness scored it as a wrong answer for want of a field saying otherwise. So these assert
against backend/main.py's source that the label is actually emitted, not merely available.
"""

from __future__ import annotations

import io
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import degradation as D

_MAIN = io.open(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py"), encoding="utf-8"
).read()


# ---------------------------------------------------------------- the constant

def test_fallback_constant_is_the_string_the_frontend_has_always_shown():
    assert D.TIMEOUT_FALLBACK_ANSWER == (
        "The learned Doctor's quill moves slowly, and the ink has dried before a response "
        "could be penned. Please try again."
    )
    assert len(D.TIMEOUT_FALLBACK_ANSWER) == 115, len(D.TIMEOUT_FALLBACK_ANSWER)


def test_is_degraded_answer_matches_the_fallback_and_nothing_else():
    assert D.is_degraded_answer(D.TIMEOUT_FALLBACK_ANSWER)
    assert D.is_degraded_answer("  " + D.TIMEOUT_FALLBACK_ANSWER + "\n")
    assert not D.is_degraded_answer("Gill says the covenant of grace is sure.")
    assert not D.is_degraded_answer("")
    assert not D.is_degraded_answer(None)


def test_a_truncated_fallback_is_not_treated_as_the_fallback():
    # Substring matching would make any answer that QUOTES the apology a false positive.
    assert not D.is_degraded_answer(D.TIMEOUT_FALLBACK_ANSWER[:-10])
    assert not D.is_degraded_answer("The user saw: " + D.TIMEOUT_FALLBACK_ANSWER)


# ---------------------------------------------------------------- the switches

def test_wall_is_180_and_above_the_observed_generation_maximum():
    # The 2026-09-20 flag-on arm's slowest COMPLETED generation was 81.0s against a 90s
    # wall, so the wall was inside the live distribution and cut healthy work.
    assert D.LLM_WALL_SECONDS == 180.0
    assert D.LLM_WALL_SECONDS > 81.0 * 2


def test_cache_disable_reads_the_env_var_in_every_truthy_spelling():
    prev = os.environ.get(D.LM_CACHE_DISABLED_ENV)
    try:
        for val in ("1", "true", "TRUE", "yes", "on", " 1 "):
            os.environ[D.LM_CACHE_DISABLED_ENV] = val
            assert D.lm_cache_disabled(), val
        for val in ("", "0", "false", "no", "off"):
            os.environ[D.LM_CACHE_DISABLED_ENV] = val
            assert not D.lm_cache_disabled(), val
        os.environ.pop(D.LM_CACHE_DISABLED_ENV, None)
        assert not D.lm_cache_disabled()
    finally:
        if prev is None:
            os.environ.pop(D.LM_CACHE_DISABLED_ENV, None)
        else:
            os.environ[D.LM_CACHE_DISABLED_ENV] = prev


# ---------------------------------------------------------------- wiring: is it CALLED?

def test_main_has_no_second_copy_of_the_fallback_string():
    # Two copies drift. The point of the module is one source of truth.
    assert "quill moves slowly" not in _MAIN, "main.py still carries its own literal"
    assert "answer = TIMEOUT_FALLBACK_ANSWER" in _MAIN


def test_main_uses_the_named_wall_not_a_bare_number():
    assert "timeout=LLM_WALL_SECONDS" in _MAIN
    assert "timeout=90.0" not in _MAIN, "the 90s wall is still in the tree"


def test_main_sets_the_degraded_reason_in_the_timeout_handler():
    assert "degraded_reason = DEGRADED_LLM_TIMEOUT" in _MAIN
    assert "degraded_reason = None" in _MAIN, "no initialiser; a non-timeout run would NameError"


def test_main_returns_the_degraded_field_to_the_caller():
    # A label set but not returned is invisible to the consumer, which is the whole failure.
    assert 'degraded=locals().get("degraded_reason", None)' in _MAIN
    assert "degraded: Optional[str] = None" in _MAIN, "SearchResponse has no degraded field"


def test_main_reports_cache_state_and_generation_seconds():
    assert "lm_cache_enabled=not lm_cache_disabled()" in _MAIN
    assert "generation_seconds=locals().get" in _MAIN
    assert "generation_seconds = t8 - t7" in _MAIN


def test_main_disables_both_caches_when_asked_not_just_the_disk_one():
    # The disk cache was never the problem; the in-process memory cache was.
    assert "dspy.configure_cache(enable_disk_cache=False, enable_memory_cache=False)" in _MAIN
    assert "if lm_cache_disabled():" in _MAIN


def test_stale_60_second_message_is_gone():
    assert "timed out after 60 seconds" not in _MAIN, "message contradicted the actual wall"


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
