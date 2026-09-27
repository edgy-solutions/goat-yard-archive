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


def is_degraded_answer(answer: str | None) -> bool:
    """Compatibility floor: does this answer text equal a known degradation fallback?

    Prefer the structured `degraded` field. This exists so a consumer pointed at a backend
    that predates the field still refuses to score a non-answer as an answer. Compares on
    stripped text, because that is the only normalisation the transport can introduce.
    """
    return (answer or "").strip() == TIMEOUT_FALLBACK_ANSWER.strip()
