"""One source of truth for "this answer is not an answer".

WHY THIS EXISTS. The ADR-0009 flag eval (2026-09-20) scored 14 of 84 runs as content
FAILURES when the model had never answered at all: `asyncio.wait_for` killed the
generation, the endpoint returned the apology string below, and the harness — which knew
only how to compare an answer against expectations — read that apology as a wrong answer.
Two questions lost every one of their runs that way, and both were questions a feature gate
turned on. The run produced a plausible 60.7% pass rate and a tidy stability table, and both
were fictions.

An empty result from a claimed region is an ERROR, not a wrong answer. A timeout is an empty
result. Scoring it as FAIL is a silent drop wearing a number, which is worse than a crash
because it survives review.

The rule this module enforces: a degraded response is labelled AT THE POINT OF DEGRADATION,
by the code that caused it, in a structured field. Consumers read the field. Nobody
string-matches prose to find out whether the system worked.

`TIMEOUT_FALLBACK_ANSWER` is still exported, and `is_degraded_answer` still matches it,
purely so a consumer talking to an older or mis-deployed backend that lacks the structured
field is not silently mis-scored. That is a compatibility floor, not the contract. The
contract is the field.
"""

from __future__ import annotations

import os

# The user-facing apology returned when generation is killed. Byte-identical to what the
# frontend has always shown; it is period-voiced on purpose and must stay that way.
TIMEOUT_FALLBACK_ANSWER = (
    "The learned Doctor's quill moves slowly, and the ink has dried before a response "
    "could be penned. Please try again."
)

# Values for SearchResponse.degraded. None means "the system did what it claims".
DEGRADED_LLM_TIMEOUT = "llm_timeout"

# The generation raised instead of returning. Three labels, not one, because the causes are not
# interchangeable and a report that merges them cannot act on either:
#
#   DEGRADED_UPSTREAM_RATE_LIMIT  the provider refused to serve. A RUN-LEVEL fault: every later
#                                 question is likely to hit the same wall, so an eval must abort
#                                 rather than bank the rest as results.
#   DEGRADED_ASSERTION            our OWN verification fired. A content event, not an outage --
#                                 worth separating so a bad week for the model is never reported
#                                 as a bad week for the provider.
#   DEGRADED_GENERATION_ERROR     anything else raised on the generation path.
#
# All three are degradations, which means NOT SCOREABLE: whatever the model had produced is gone,
# and the answer field carries a fallback. Scoring that fallback as a wrong answer is the exact
# fault this module was written for.
DEGRADED_UPSTREAM_RATE_LIMIT = "upstream_rate_limit"
DEGRADED_ASSERTION = "assertion_failed"
DEGRADED_GENERATION_ERROR = "generation_error"

# The user-facing text when generation raised. Period-voiced like TIMEOUT_FALLBACK_ANSWER, and
# deliberately carrying NO diagnostics: the exception text used to be pasted into the `answer`
# field ("Error generating answer: litellm.RateLimitError: ..."), where it was read by the user as
# an answer AND mined for [SENTENCE_ID]-shaped substrings by every consumer downstream. The detail
# belongs in `degraded_detail`, which is typed and which nobody renders.
GENERATION_FAILURE_ANSWER = (
    "The learned Doctor's quill was interrupted mid-stroke, and no answer was set down. "
    "Please try again."
)

# NOT A DEGRADATION, and the distinction is the whole point of this module.
#
# bot.py's citation verifier fires when the model cited a sentence id that is not in the retrieved
# context. Nothing broke: the model produced a checkable claim and the check failed. That is a
# CONTENT failure and it must stay IN the scoring denominator -- labelling it `degraded` would pull
# a real model fault out of the measurement, which is the mirror image of the fault in the docstring
# above. `is_degraded_answer` must NOT match this text, and there is a test that says so.
#
# It lives here anyway because this module owns every string the system substitutes for an answer,
# and because it replaces prose that WAS being string-matched: the old text was
# f"Verification Failed: Cited sources not found in context. Missing: {missing_cits}" -- a diagnostic
# shown to users, carrying bracketed sentence ids into an answer field that every consumer scans for
# them. The typed replacement is `verification_failure` + `missing_citations` on the prediction.
VERIFICATION_FAILURE_ANSWER = (
    "The Doctor's hand cites a passage I cannot find among the extracts before me, and I will "
    "not repeat a reference I cannot show you. Please try again, or ask more narrowly."
)

# Answer prefixes emitted by backends that PREDATE the typed channel above. Kept so a consumer
# pointed at an older or mis-deployed backend still refuses to score machine prose as content.
#
# Measured incident, and the reason this list is not hypothetical: in
# nf2_20260927/real_garden_genesis_3_24_misattribution_001.json the answer field reads
# "Error generating answer: litellm.RateLimitError: ... Provider returned error" and the harness
# scored it `overall_pass: False, error: None, degraded: None`. A provider rate limit was banked as
# a content failure, in a published run, inside a harness that has an explicit run-level-fault gate
# for 429s -- the gate never saw it, because the 429 arrived as HTTP 200 with the error in the prose.
LEGACY_DIAGNOSTIC_ANSWER_PREFIXES = (
    "Error generating answer:",
    "Generated answer could not be verified against sources.",
    "Verification Failed:",
)

# Generation wall. Raised from 90s per ruling 2026-09-21: the flag-on (typed schema) path
# ran a 25.7s median generation with an observed 81.0s maximum, so a 90s wall sat inside the
# real distribution's tail and cut runs that would have completed. A wall that fires on
# healthy work is not a safety limit, it is a sampling bias.
LLM_WALL_SECONDS = 180.0

# Set to 1/true to disable DSPy's caches for this process. Required for any run that claims
# to sample N times per question: with the in-process memory cache live (default: 1,000,000
# entries), runs 2..N of an identical request are replayed from run 1, so the arm reports
# zero variance because it never sampled twice. The 2026-09-20 flag-OFF arm did exactly this
# and its FLAKY=0 was an artifact of its own harness.
LM_CACHE_DISABLED_ENV = "GILL_DISABLE_LM_CACHE"


def lm_cache_disabled() -> bool:
    """True when this process was asked to run with DSPy caching off."""
    return (os.getenv(LM_CACHE_DISABLED_ENV) or "").strip().lower() in ("1", "true", "yes", "on")


OPENROUTER_PROVIDER_ENV = "OPENROUTER_PROVIDER_ORDER"


def provider_pin() -> dict | None:
    """OpenRouter `provider` routing block for this process, or None when unpinned.

    `deepseek/deepseek-chat` is served by MORE THAN ONE provider, at different numeric
    builds. Measured 2026-09-27 from OpenRouter's own endpoint metadata:

        StreamLake  ctx 128000  quant unknown  status  0  uptime 99.5%
        DeepInfra   ctx 163840  quant fp4      status -2  uptime 94.4%

    Temperature 0 is deterministic within a provider, not across two. An arm that does not
    pin one is measuring provider mix as though it were model behaviour, and the 2026-09-27
    ON arm was observed falling back DeepInfra -> StreamLake mid-run on an upstream 429.
    Providers are logged by OpenRouter only on errors, so a silent split on the successful
    requests cannot be ruled out after the fact - which is the whole reason to pin up front.

    Unpinned by default: production routing is a product decision, not this module's.
    `allow_fallbacks` is FALSE whenever a pin is given, so an unavailable provider fails
    loud instead of quietly serving a different quantization.
    """
    raw = (os.getenv(OPENROUTER_PROVIDER_ENV) or "").strip()
    if not raw:
        return None
    order = [p.strip() for p in raw.split(",") if p.strip()]
    if not order:
        raise ValueError(
            f"{OPENROUTER_PROVIDER_ENV}={raw!r} names no provider. Unset it to run unpinned "
            f"rather than setting it to something empty."
        )
    return {"order": order, "allow_fallbacks": False}


ANSWER_TEMPERATURE_ENV = "GILL_ANSWER_TEMPERATURE"


def answer_temperature() -> float | None:
    """Explicit sampling temperature for the OFF (DSPy) answer path, or None to send none.

    The two answer paths have never agreed on this field. `dspy.LM(...)` leaves
    `kwargs["temperature"] is None`, litellm omits it, and the PROVIDER's default applies --
    unrecorded, and not necessarily the same default next month. The ON path's BAML client sends
    `temperature: 0` (structured_answer.ANSWER_LM_TEMPERATURE). So every OFF-vs-ON arm ever run
    varied the flag AND the temperature together, and neither arm could tell you which one moved
    the answer. That is the confound this knob exists to remove: hold temperature equal across
    both arms, then the flag is the only difference left.

    None when unset, and unset must stay the default: setting a temperature the product does not
    set would make every eval measure a configuration nobody serves. A value that is present but
    unparseable raises rather than falling back to None -- an arm that asked for temperature 0 and
    silently got the provider default is the exact failure this records against.

    Measured 2026-09-27 (`evals/probe_temperature_determinism.py`, one question, N=3 per arm):
    the unset arm was already 3/3 byte-identical, so temperature is NOT the established source of
    the 13 stochastic questions -- but the two arms produced DIFFERENT text (digests 0f31b7b7 vs
    3e9aed0a), so it is not inert either.
    """
    raw = (os.getenv(ANSWER_TEMPERATURE_ENV) or "").strip()
    if not raw:
        return None
    try:
        t = float(raw)
    except ValueError:
        raise ValueError(
            f"{ANSWER_TEMPERATURE_ENV}={raw!r} is not a number. Unset it to send no temperature "
            f"at all (the provider default, which is what this path has always done) rather than "
            f"setting it to something unparseable."
        )
    if not 0.0 <= t <= 2.0:
        raise ValueError(
            f"{ANSWER_TEMPERATURE_ENV}={raw!r} is outside the accepted 0.0-2.0 range."
        )
    return t


def is_degraded_answer(answer: str | None) -> bool:
    """Compatibility floor: is this answer text a known non-answer rather than content?

    Prefer the structured `degraded` field. This exists so a consumer pointed at a backend
    that predates the field still refuses to score a non-answer as an answer. Compares on
    stripped text, because that is the only normalisation the transport can introduce.

    Two families. The fallbacks are matched by EQUALITY: they are fixed strings this module owns,
    and a prefix test on them would swallow a real answer that happened to open with the same
    sentence. The legacy diagnostics are matched by PREFIX: they were f-strings with an exception
    message interpolated after the colon, so no two are ever byte-identical.
    """
    a = (answer or "").strip()
    if not a:
        return False
    if a in (TIMEOUT_FALLBACK_ANSWER.strip(), GENERATION_FAILURE_ANSWER.strip()):
        return True
    return any(a.startswith(pfx) for pfx in LEGACY_DIAGNOSTIC_ANSWER_PREFIXES)


def classify_generation_exception(exc_type_name: str, detail: str) -> str:
    """Which degradation label a raised generation exception deserves.

    Substring matching on an exception message is normally a smell, and here it is the only
    evidence available: litellm surfaces an upstream 429 as a RateLimitError whose text carries the
    provider's words, and by the time it reaches this process the HTTP status is long gone.

    The asymmetry is deliberate and it is the safe direction. A rate limit MISSED here still comes
    back DEGRADED_GENERATION_ERROR, which still keeps it out of the scoring denominator -- it just
    fails to abort the run. A rate limit invented here would abort a healthy run. So the markers
    stay narrow, and the fallback is the label that costs least when it is wrong.
    """
    hay = f"{exc_type_name or ''} {detail or ''}".lower()
    if any(m in hay for m in ("ratelimiterror", "rate limit", "rate_limit",
                              "429", "too many requests")):
        return DEGRADED_UPSTREAM_RATE_LIMIT
    if "assert" in (exc_type_name or "").lower():
        return DEGRADED_ASSERTION
    return DEGRADED_GENERATION_ERROR
