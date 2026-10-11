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
        "expansion": {"ok": 0, "errored": 0, "causes": {}, "fallbacks": {}},
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


def public_snapshot() -> dict:
    """Name and boolean per stage, for a production monitor. No counters.

    0.3.2: this is what GET /health/stages returns. `snapshot()` keeps every
    counter and stays the internal API; nothing exposes it over HTTP.

    healthy == "this stage RAN at least once in this process AND recorded no
    fault". A stage that never ran is therefore false, not true: a monitor
    whose green light means "nothing has happened yet" is the silence this
    module exists to remove, so the ambiguity is resolved toward alarm.

    THE CONFLATION, stated rather than hidden: false means "never ran" OR
    "faulted", and the boolean cannot tell an operator which. That is the price
    of name+boolean. `snapshot()` distinguishes them and is one import away for
    anything running in-process.

    A fault always wins over a pass: a stage with one degraded run and a
    thousand clean ones is false. These are cumulative since process start,
    so a stage that faulted once never goes green again without a restart.
    That is deliberate at this granularity -- a rate belongs in a counter,
    and this response has none.

    "not_observable" is a THIRD outcome, and it exists because of this release
    line. 0.3.x has no backend/degradation.py and no verification_failure to
    read, so main.py records answer and verifier as UNOBSERVABLE on every
    request. A boolean has nowhere to put "the stage ran and this build cannot
    say": false would be an alarm that can never clear, and true would be a
    fabricated pass in the one tool built to detect fabricated health. So the
    stage gets NO boolean and is named here instead. A consumer that reads
    `stages["answer"]` without checking this list gets a KeyError rather than
    a wrong answer, which is the error I want it to make.
    """
    s = snapshot()
    stages, not_observable = {}, []

    exp = s["expansion"]
    # A fallback is only ever recorded in the BAML-expansion except block, so
    # fallbacks without errored should be impossible; it is in the condition
    # anyway because a future caller recording one without an error would
    # otherwise turn a degraded expansion green.
    stages["expansion"] = bool(
        (exp["ok"] + exp["errored"]) > 0 and exp["errored"] == 0 and not exp["fallbacks"])

    modes = s["entity_lookup"]["modes"]
    # "full" is the only healthy mode; "degraded_no_vector" means the embedding
    # call failed and the lookup served BM25/substring only, and "other" means a
    # mode this build does not recognise.
    stages["entity_lookup"] = bool(
        sum(modes.values()) > 0 and all(v == 0 for k, v in modes.items() if k != "full")
        and modes.get("full", 0) > 0)

    for name, fault_key in (("answer", "degraded"), ("verifier", "failures")):
        st = s[name]
        faulted = any(v > 0 for v in st[fault_key].values())
        if faulted:
            stages[name] = False
        elif st["ok"] > 0:
            stages[name] = True
        elif st["unobservable"] > 0:
            not_observable.append(name)
        else:
            stages[name] = False

    return {"stages": stages, "not_observable": not_observable}


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
