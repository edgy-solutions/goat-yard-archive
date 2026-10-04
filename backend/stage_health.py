"""Passive, in-process per-stage LM health recorder for the RUNNING backend process.

Why this exists: in production the pod logs carry only uvicorn access lines, and
the only current window into per-stage health (expansion, entity lookup, answer
generation, verification) is debug: true on /api/search, which is not something
a production-safe monitor can turn on globally. This module gives a read-only
snapshot of cumulative per-stage counts for the current process, exposed at
GET /health/stages.

Safety is the entire point of this module, not an afterthought:

  * No raw text is ever stored. record_request takes the RAW exception string
    for expansion_error and immediately buckets it to a fixed cause key before
    anything is written to module state -- the raw string itself is discarded
    at the end of the call. Every other field is matched against a fixed
    allowlist derived from the code that produces it; anything unrecognised
    becomes the literal "other". This bounds memory use AND keeps arbitrary
    text (URLs, secrets, user query fragments) out of a response any operator
    can curl.
  * record_request never raises. A telemetry recorder that can 500 a user
    request is worse than no telemetry, so the whole body is wrapped in a
    broad try/except that swallows.

No I/O, no LM calls. A single threading.Lock guards the module-level counters.
"""

from __future__ import annotations

import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Process identity, fixed once at import time.
# ---------------------------------------------------------------------------

_PID = os.getpid()
_COMMIT_SHA = os.environ.get("COMMIT_SHA", "unknown")
_STARTED_AT = datetime.now(timezone.utc)
_STARTED_MONOTONIC = time.monotonic()


# ---------------------------------------------------------------------------
# Allowlists. Each one is derived from the code that actually produces the
# value, not invented -- see the file:line noted above each set. A value not
# in its allowlist is recorded as "other".
# ---------------------------------------------------------------------------

# backend/main.py -- the fallback_kind / plain-local mirror values set in the
# BAML-expansion except block (ADR-0012 / ADR-0013 Part D dispatch) and the
# ADR-0014 fail-anchored gate:
#   "anchored_manifest_trusted"        backend/main.py:703
#   "poisoned_manifest_suppressed"     backend/main.py:712
#   "dedup_only"                       backend/main.py:732
#   "vector_tier_degraded_suppressed"  backend/main.py:758
EXPANSION_FALLBACK_KINDS = frozenset({
    "anchored_manifest_trusted",
    "poisoned_manifest_suppressed",
    "dedup_only",
    "vector_tier_degraded_suppressed",
})

# backend/gill_search.py:609 -- get_relevant_entities returns exactly one of
# these two modes ("full" when the vector tier executed, "degraded_no_vector"
# when the embedding call failed and the lookup fell back to BM25/substring
# only).
ENTITY_LOOKUP_MODES = frozenset({
    "full",
    "degraded_no_vector",
})

# backend/degradation.py:37,53,54,55 -- the DEGRADED_* constants.
ANSWER_DEGRADED_REASONS = frozenset({
    "llm_timeout",
    "upstream_rate_limit",
    "assertion_failed",
    "generation_error",
})

# A stage can be in a FOURTH state, distinct from ok / degraded / not_run:
# the stage ran, and this build cannot say whether it was healthy. That is the
# case on the 0.3.x production line, which has no backend/degradation.py and no
# verification_failure local at all -- so there is nothing to read, and
# reporting "ok" would be a fabricated pass in the one tool built to detect
# fabricated health. A caller passes this sentinel instead of a reason.
# The retry bound declared by `retry_policy BoundedTransport` in baml_src/main.baml. It is
# restated here because this module must not import baml, and
# test_stage_health.py DERIVES the expected value by parsing baml_src rather than
# restating it again -- so if the policy changes and this constant does not, the suite fails
# instead of silently measuring against a stale bound.
MAX_RETRIES_CONFIGURED = 3


def retries_from_baml_log(log) -> Optional[int]:
    """Attempts-minus-one from a BAML FunctionLog, or None if it cannot be observed.

    Retries are counted as len(log.calls) - 1 and NOT by inspecting LLMCall.selected:
    measured against baml_py 0.211.1, `selected` is True on EVERY call including the three
    that failed, so it cannot identify the winning attempt. Duck-typed on purpose -- this
    module stays importable without baml installed, which is how test_stage_health.py runs
    without pulling in Weaviate/DSPy.

    None is a real answer and the caller must keep it distinct from 0: a missing collector
    means retries were not observed, not that there were none.
    """
    if log is None:
        return None
    calls = getattr(log, "calls", None)
    if not calls:
        return None
    try:
        return max(0, len(calls) - 1)
    except TypeError:
        return None


UNOBSERVABLE = "__unobservable__"

# backend/bot.py:1265 -- the only verification_failure= value currently
# emitted by the bot.
VERIFICATION_FAILURE_KINDS = frozenset({
    "cited_sources_not_in_context",
})


# ---------------------------------------------------------------------------
# expansion_error cause bucketing. Mirrors evals/expansion_census.py error_class
# on purpose -- that script and this module are two readers of the same raw
# BAML exception text, and a bucket that drifted between them would make the
# two disagree about what "healthy" means.
# ---------------------------------------------------------------------------

# Built from chr(39) rather than a literal apostrophe character so this source
# file contains no apostrophes; functionally identical to matching the quote
# character the exception text actually wraps the variable name in.
_APOS = chr(39)
_ENV_VAR_EXTRACT_RE = re.compile(_APOS + r"([A-Z0-9_]+)" + _APOS)
_ENV_VAR_SHAPE_RE = re.compile(r"^[A-Z0-9_]{1,64}$")


def _bucket_expansion_error(msg: str) -> str:
    m = msg or ""
    if "requires environment variable" in m:
        tail = m[m.index("requires environment variable"):]
        var = _ENV_VAR_EXTRACT_RE.search(tail)
        if var and _ENV_VAR_SHAPE_RE.match(var.group(1)):
            return "missing_env_var:" + var.group(1)
        return "missing_env_var:unknown"
    if "404" in m:
        return "http_404"
    if "429" in m:
        return "http_429"
    if "timeout" in m.lower():
        return "timeout"
    return "other"


def _allow(value, allowed: frozenset) -> str:
    """Map value to itself if it is a string in allowed, else "other".

    isinstance is checked first so an unhashable garbage value (a dict, a
    list) never reaches the "in" test on a frozenset of strings, which would
    raise TypeError instead of just being an unrecognised value.
    """
    if isinstance(value, str) and value in allowed:
        return value
    return "other"


# ---------------------------------------------------------------------------
# Mutable state. One lock guards every read and write.
# ---------------------------------------------------------------------------

_lock = threading.Lock()


def _fresh_state() -> dict:
    return {
        "requests_recorded": 0,
        # `retries.unobserved` is a THIRD state kept out of the counts on purpose, for the
        # same reason answer/verifier keep "not_run" separate from "ok": a request whose
        # collector was missing says NOTHING about retries, and folding that into 0 would
        # report a healthy transport on no evidence.
        "expansion": {"ok": 0, "errored": 0, "causes": {}, "fallbacks": {},
                      "retries": {"total": 0, "calls_with_retries": 0, "max_observed": 0,
                                  "bound_exhausted": 0, "unobserved": 0}},
        "entity_lookup": {"modes": {}},
        # "not_run" is a THIRD state, kept separate from "ok" on purpose. A
        # request that exits before generation (no retrieval results, or no bot
        # configured) never exercised these stages, and counting that as "ok"
        # would fold "did not run" into "was healthy" -- the exact silence this
        # whole module exists to remove.
        "answer": {"ok": 0, "not_run": 0, "unobservable": 0, "degraded": {}},
        "verifier": {"ok": 0, "not_run": 0, "unobservable": 0, "failures": {}},
    }


_state = _fresh_state()


def _reset_for_tests() -> None:
    """Test-only reset of module state to a fresh snapshot.

    Not part of the production API. backend/test_stage_health.py imports this
    module directly (without importing backend/main.py, which pulls in
    Weaviate/DSPy) and calls this between tests because the counters are
    module-level and otherwise accumulate across tests in the same process.
    """
    global _state
    with _lock:
        _state = _fresh_state()


def _bump(bucket: dict, key: str) -> None:
    bucket[key] = bucket.get(key, 0) + 1


def record_request(
    *,
    expansion_error: Optional[str],
    expansion_fallback: Optional[str],
    expansion_retries: Optional[int] = None,
    entity_lookup_mode: Optional[str],
    answer_degraded: Optional[str],
    verification_failure: Optional[str],
    answer_ran: bool = True,
    verifier_ran: bool = True,
) -> None:
    """Record the per-stage outcome of one completed /api/search request.

    expansion_error is the RAW exception string and MUST NOT be stored -- it
    is bucketed to a cause key below and the raw text is discarded before
    this function returns. Every other argument is matched against a fixed
    allowlist; an unrecognised value becomes "other". A None value for
    answer_degraded, verification_failure, or expansion_error means that
    stage was healthy for this request.

    answer_ran / verifier_ran say whether the stage was REACHED on this
    request path at all. False counts into "not_run" and never into "ok" or
    "degraded": a request that exits on empty retrieval, or runs with no bot
    configured, did not exercise generation or verification, and reporting it
    as healthy would be a fabricated pass. They do not assert that every
    internal sub-check inside a reached stage executed -- see the residual
    named in docs/releases/RELEASE_0.3.2.md.

    Passing UNOBSERVABLE for answer_degraded or verification_failure says the
    stage RAN and this build cannot read its health. It counts into
    "unobservable" and never into "ok".

    Never raises: the whole body is wrapped in a broad except so a bug in
    telemetry can never turn into a failed response for a real user request.
    """
    try:
        with _lock:
            _state["requests_recorded"] += 1

            if expansion_error is None:
                _bump(_state["expansion"], "ok")
            else:
                _bump(_state["expansion"], "errored")
                msg = expansion_error if isinstance(expansion_error, str) else str(expansion_error)
                cause = _bucket_expansion_error(msg)
                _bump(_state["expansion"]["causes"], cause)

            # Retry accounting for `retry_policy BoundedTransport`. A retry that can loop
            # silently is the same defect under a new name, so the bound is made observable
            # here rather than merely declared in baml_src: bound_exhausted counts calls that
            # used every retry the policy allows, which means the transport is broken rather
            # than flaky, and the scored-run preflight refuses on it.
            _r = _state["expansion"]["retries"]
            if isinstance(expansion_retries, bool) or not isinstance(expansion_retries, int):
                # bool is excluded explicitly because isinstance(True, int) is True in Python
                # and a flag is not a count.
                _bump(_r, "unobserved")
            else:
                _n = max(0, expansion_retries)
                _r["total"] += _n
                if _n > 0:
                    _bump(_r, "calls_with_retries")
                if _n > _r["max_observed"]:
                    _r["max_observed"] = _n
                if _n >= MAX_RETRIES_CONFIGURED:
                    _bump(_r, "bound_exhausted")

            if expansion_fallback is not None:
                kind = _allow(expansion_fallback, EXPANSION_FALLBACK_KINDS)
                _bump(_state["expansion"]["fallbacks"], kind)

            if entity_lookup_mode is not None:
                mode = _allow(entity_lookup_mode, ENTITY_LOOKUP_MODES)
                _bump(_state["entity_lookup"]["modes"], mode)

            if not answer_ran:
                _bump(_state["answer"], "not_run")
            elif answer_degraded == UNOBSERVABLE:
                _bump(_state["answer"], "unobservable")
            elif answer_degraded is None:
                _bump(_state["answer"], "ok")
            else:
                reason = _allow(answer_degraded, ANSWER_DEGRADED_REASONS)
                _bump(_state["answer"]["degraded"], reason)

            if not verifier_ran:
                _bump(_state["verifier"], "not_run")
            elif verification_failure == UNOBSERVABLE:
                _bump(_state["verifier"], "unobservable")
            elif verification_failure is None:
                _bump(_state["verifier"], "ok")
            else:
                kind = _allow(verification_failure, VERIFICATION_FAILURE_KINDS)
                _bump(_state["verifier"]["failures"], kind)
    except Exception:
        pass


def snapshot() -> dict:
    """Return the current cumulative per-stage health snapshot.

    Returns a plain, JSON-serialisable dict. A fresh copy of every nested
    dict is taken under the lock so the caller cannot mutate module state
    through the returned object, and so a concurrent record_request cannot be
    observed mid-update.
    """
    with _lock:
        expansion = {
            "ok": _state["expansion"]["ok"],
            "errored": _state["expansion"]["errored"],
            "causes": dict(_state["expansion"]["causes"]),
            "fallbacks": dict(_state["expansion"]["fallbacks"]),
            "retries": dict(_state["expansion"]["retries"]),
        }
        entity_lookup = {"modes": dict(_state["entity_lookup"]["modes"])}
        answer = {
            "ok": _state["answer"]["ok"],
            "not_run": _state["answer"]["not_run"],
            "unobservable": _state["answer"]["unobservable"],
            "degraded": dict(_state["answer"]["degraded"]),
        }
        verifier = {
            "ok": _state["verifier"]["ok"],
            "not_run": _state["verifier"]["not_run"],
            "unobservable": _state["verifier"]["unobservable"],
            "failures": dict(_state["verifier"]["failures"]),
        }
        requests_recorded = _state["requests_recorded"]

    return {
        "process": {
            "pid": _PID,
            "commit_sha": _COMMIT_SHA,
            "started_at": _STARTED_AT.isoformat(),
            "uptime_s": time.monotonic() - _STARTED_MONOTONIC,
        },
        "requests_recorded": requests_recorded,
        "expansion": expansion,
        "entity_lookup": entity_lookup,
        "answer": answer,
        "verifier": verifier,
    }
