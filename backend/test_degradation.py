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


# ------------------------------------------------- the provider pin (noise floor, 2026-09-27)

def test_pin_is_none_when_unset():
    os.environ.pop(D.OPENROUTER_PROVIDER_ENV, None)
    assert D.provider_pin() is None, "unpinned must be the default; routing is a product decision"


def test_pin_names_the_provider_and_refuses_fallbacks():
    os.environ[D.OPENROUTER_PROVIDER_ENV] = "StreamLake"
    try:
        pin = D.provider_pin()
    finally:
        os.environ.pop(D.OPENROUTER_PROVIDER_ENV, None)
    assert pin == {"order": ["StreamLake"], "allow_fallbacks": False}, pin
    assert pin["allow_fallbacks"] is False, (
        "a pin that silently falls back to another quantization is not a pin"
    )


def test_pin_accepts_an_ordered_list():
    os.environ[D.OPENROUTER_PROVIDER_ENV] = "StreamLake, DeepInfra"
    try:
        pin = D.provider_pin()
    finally:
        os.environ.pop(D.OPENROUTER_PROVIDER_ENV, None)
    assert pin["order"] == ["StreamLake", "DeepInfra"], pin


def test_empty_pin_fails_loud_rather_than_running_unpinned():
    os.environ[D.OPENROUTER_PROVIDER_ENV] = " , "
    try:
        D.provider_pin()
    except ValueError as e:
        assert D.OPENROUTER_PROVIDER_ENV in str(e), str(e)
    else:
        raise AssertionError("an env var set to nothing must not read as 'unpinned'")
    finally:
        os.environ.pop(D.OPENROUTER_PROVIDER_ENV, None)


# ---------------------------------------------------------------- the pin WIRING

def test_main_puts_the_pin_in_extra_body_for_both_lms():
    assert "provider_pin" in _MAIN, "main.py never calls provider_pin()"
    assert _MAIN.count("extra_body=dict(_extra_body)") == 2, (
        "both lm_auth and lm_anon must carry the pin; one pinned LM is a split arm"
    )


def test_main_reports_the_pin_in_the_response():
    assert "openrouter_provider_pin: Optional[dict]" in _MAIN, (
        "the response model must carry the pin, or the harness cannot record it"
    )
    assert "openrouter_provider_pin=provider_pin()" in _MAIN, (
        "the field must be populated from the live call, not hardcoded"
    )


def test_main_says_out_loud_which_way_it_went():
    assert "PINNED" in _MAIN and "UNPINNED" in _MAIN, (
        "both branches must print; an unpinned arm that looks pinned is the failure mode"
    )


# ------------------------------------------ the explicit answer temperature (2026-09-27)

def test_temperature_is_none_when_unset():
    # Unset must change nothing: this path has always sent no temperature field, and a knob that
    # alters the default configuration makes every eval measure something nobody serves.
    os.environ.pop(D.ANSWER_TEMPERATURE_ENV, None)
    assert D.answer_temperature() is None


def test_ZERO_is_a_temperature_and_not_an_absent_one():
    # The companion assertion, and the whole reason this helper is not a one-line getenv: 0 is
    # falsy. An implementation that treated "0" as unset would send no temperature for the exact
    # value this knob was built to send, and the run would report a setting it never used.
    os.environ[D.ANSWER_TEMPERATURE_ENV] = "0"
    try:
        t = D.answer_temperature()
    finally:
        os.environ.pop(D.ANSWER_TEMPERATURE_ENV, None)
    assert t == 0.0 and t is not None, repr(t)
    assert isinstance(t, float), "litellm sends what it is given; keep the type honest"


def test_a_nonzero_temperature_survives():
    os.environ[D.ANSWER_TEMPERATURE_ENV] = "0.7"
    try:
        assert D.answer_temperature() == 0.7
    finally:
        os.environ.pop(D.ANSWER_TEMPERATURE_ENV, None)


def test_an_unparseable_temperature_fails_loud_rather_than_sending_none():
    # Falling back to None here would mean an arm that asked for 0 silently ran at the provider
    # default and recorded neither -- the same class of fault as an unpinned arm reading as pinned.
    for bad in ("abc", "0.0.1", "zero"):
        os.environ[D.ANSWER_TEMPERATURE_ENV] = bad
        try:
            D.answer_temperature()
        except ValueError as e:
            assert D.ANSWER_TEMPERATURE_ENV in str(e), str(e)
        else:
            raise AssertionError(f"{bad!r} must not read as 'send no temperature'")
        finally:
            os.environ.pop(D.ANSWER_TEMPERATURE_ENV, None)


def test_an_out_of_range_temperature_is_refused():
    for bad in ("-0.5", "3.5"):
        os.environ[D.ANSWER_TEMPERATURE_ENV] = bad
        try:
            D.answer_temperature()
        except ValueError as e:
            assert "range" in str(e), str(e)
        else:
            raise AssertionError(f"{bad!r} must not reach the wire")
        finally:
            os.environ.pop(D.ANSWER_TEMPERATURE_ENV, None)


# --------------------------------------------------- the temperature WIRING

def test_main_puts_the_temperature_on_BOTH_lms():
    assert "answer_temperature()" in _MAIN, "main.py never calls answer_temperature()"
    assert _MAIN.count("**_temp_kwargs") == 2, (
        "lm_auth and lm_anon must both carry it; one LM at 0 and one at the provider default is "
        "a split arm that reports as one measurement"
    )


def test_main_sends_NO_temperature_field_when_unset():
    # Not `temperature=None`: litellm forwards an explicit None as a field on some providers, and
    # the point of unset is that the request body is byte-identical to what it was before.
    assert "_temp_kwargs = {} if _answer_temp is None else" in _MAIN, (
        "unset must contribute no kwarg at all"
    )


def test_main_says_out_loud_which_temperature_it_used():
    assert "Answer temperature UNSET" in _MAIN and "Answer temperature EXPLICIT" in _MAIN, (
        "both branches must print, or a run cannot tell which one it got from the log"
    )


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except KeyboardInterrupt:
            raise
        # SystemExit is NOT an Exception, so `except Exception` let a test that reaches sys.exit
        # end the WHOLE run silently -- no summary line, which reads as a shorter suite. Witnessed
        # 2026-10-11 in evals/test_gate_paired.py (argparse exits 2 on an unrecognized flag).
        except BaseException:
            failed += 1
            print(f"  FAIL  {name}")
            traceback.print_exc()
    print("")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
