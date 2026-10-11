"""One place for "this backend will not give me stage captures".

Two refusals, for two different moments:

`refuse_if_debug_disabled(response, ...)` turns the gate's 403 on a request
already made into the remedy. It is DELIBERATELY SILENT on every other status:
this module speaks only about the debug gate, and swallowing a 500 or a 404
here would hide a different fault behind a confident message about a flag.

`preflight_debug_capture(endpoint, ...)` is the one Chris's ruling of
2026-10-11 asks for -- "eval preflight refuses a target without stages, naming
the flag". It fires ONE probe request before a run starts, and refuses if the
target cannot produce `stages` at all. The reason it exists: on 2026-09-20 a
scored arm ran to completion against a backend whose structured fields were
absent and the prediction could not be scored -- 65 requests spent to learn
something one request could have said. The scored arm in evals/run_eval.py
posts debug=True precisely because the fields it scores live in `stages`, so
"no stages" is not a degraded run, it is an unscoreable one.

WHY IT CAN TRUST "no stages": with the flag ON, every 200 from /api/search
carries a non-empty `stages` -- including the no-results early return, which
until 2026-10-11 omitted it and so answered a debug caller with 200 and
`stages: null`. That null said "this build has no capture channel" when the
channel was open and the query had simply retrieved nothing. Both return sites
now pass the capture, which is what makes the preflight's discriminator sound
rather than a guess about retrieval luck.

Its refusals are TYPED, because the three causes have three different remedies
and conflating them is how a confident wrong message gets written:

  403                      -> the flag is off on the target. Remedy below.
  200, stages absent/empty -> the backend answered but has no capture channel.
                              Usually an older image than the chart claims.
  anything else            -> abort naming the status, and SAY it is not a
                              flag diagnosis. This module has no evidence
                              about a 502.
"""

from __future__ import annotations

from typing import Optional

import httpx

ENV_VAR = "GYA_DEBUG_STAGES"

REMEDY = (
    "the backend refused debug captures (403). This script needs them: set "
    "GYA_DEBUG_STAGES=1 in the backend environment (the Helm chart sets it for "
    "gya-test; production leaves it 0 on purpose) and restart the pod -- the value "
    "is read from the container environment at start, so a configmap edit alone "
    "does not take effect."
)

# A probe query, not a test case. Short on purpose: it costs one real request
# through the whole pipeline, and it is asked once per run, not per question.
PROBE_QUERY = "What does Gill say about faith?"


# The one text for "a 200 carried no stage captures". Two consumers with two
# dispositions -- refuse_if_no_stages RAISES it before a run, run_eval's
# run_level_fault RETURNS it mid-run -- and a second copy of it would have drifted
# the moment the remedy changed (it already changed once: the leading cause stopped
# being "an older build" the day the capture became gated).
NO_STAGES_REASON = (
    "the target answered 200 but carried no stage captures, so this run produces "
    "nothing to read and, on a scored arm, nothing to score.\n"
    "With %s=1 every 200 from /api/search carries a non-empty `stages`, including "
    "the no-results path -- so an empty one means the flag is not set in the "
    "environment this pod actually started with, or the image predates the capture. "
    "Set %s=1 and roll the pod out (envFrom is read at container start), or point "
    "this script at a backend that has it." % (ENV_VAR, ENV_VAR))

# The names that constitute "this file checks for stage captures". Owned HERE so a
# rename shows up in one place, and asserted to exist by backend/test_debug_gate.py:
# a probe keyed on a symbol that no longer exists passes on nothing.
STAGES_CHECK_SYMBOLS = ("preflight_debug_capture", "refuse_if_no_stages",
                       "NO_STAGES_REASON")


def refuse_if_debug_disabled(response, endpoint: str, consumer: str) -> None:
    """Abort with the remedy if `response` is the gate's 403; otherwise return.

    Deliberately a no-op on every other status: this module speaks only about
    the debug gate, and swallowing a 500 or a 404 here would hide a different
    fault behind a confident message about a flag.
    """
    if getattr(response, "status_code", None) != 403:
        return
    raise SystemExit(REMEDY + "\n" + ("consumer: %s" % consumer) + "\n"
        + ("endpoint: %s" % endpoint) + "\n"
        + ("body: %s" % (getattr(response, "text", "") or "")[:300]))


def refuse_if_no_stages(body, endpoint: str, consumer: str) -> list:
    """The stages half of the preflight, over a response BODY already in hand.

    Separate from preflight_debug_capture because a caller with its own transport
    seam must not be made to open a second one. evals/run_eval.py sends every
    request through its own call_endpoint (timeouts, degraded-answer labelling,
    the 403 refusal, and the stub its end-to-end tests install), so a preflight
    that reached for httpx directly would bypass all of it -- and it did: sixteen
    end-to-end tests in evals/test_run_eval_harness.py started making real
    network calls, which is how this was found. A probe that supplies its own
    input is not probing the thing the caller uses.

    Returns the sorted stage keys. Raises SystemExit naming the flag otherwise.
    """
    where = ("consumer: %s" % consumer) + "\n" + ("endpoint: %s" % endpoint)
    stages = body.get("stages") if isinstance(body, dict) else None
    if not isinstance(stages, dict) or not stages:
        raise SystemExit("PREFLIGHT ABORTED: %s\n(stages=%r)\n%s"
                         % (NO_STAGES_REASON, stages, where))
    return sorted(stages.keys())


def preflight_debug_capture(endpoint: str, consumer: str,
                            headers: Optional[dict] = None,
                            timeout: float = 180.0,
                            probe_query: str = PROBE_QUERY,
                            post=None) -> list:
    """Refuse BEFORE a run if `endpoint` cannot produce stage captures.

    Returns the sorted stage keys the probe got back, so a caller can log what
    the target actually offers. Raises SystemExit otherwise. `post` is injected
    in tests; by default it is httpx.post.
    """
    sender = post or httpx.post
    where = ("consumer: %s" % consumer) + "\n" + ("endpoint: %s" % endpoint)
    try:
        r = sender(endpoint, headers=headers or {},
                   json={"query": probe_query, "debug": True}, timeout=timeout)
    except Exception as exc:
        raise SystemExit(
            ("PREFLIGHT ABORTED: the probe request to the target did not complete "
             "(%s: %s). This is NOT a diagnosis of %s -- the preflight never got "
             "a status back, so it has no evidence about the debug flag.\n%s")
            % (type(exc).__name__, exc, ENV_VAR, where))

    refuse_if_debug_disabled(r, endpoint, "preflight for " + consumer)

    status = getattr(r, "status_code", None)
    if status != 200:
        raise SystemExit(
            ("PREFLIGHT ABORTED: the target answered HTTP %s to the probe. This is "
             "NOT a diagnosis of %s: a non-200 that is not the gate's 403 says "
             "nothing about the debug flag, and this module will not guess.\n%s\n"
             "body: %s") % (status, ENV_VAR, where, (getattr(r, "text", "") or "")[:300]))

    try:
        body = r.json()
    except Exception as exc:
        raise SystemExit(
            ("PREFLIGHT ABORTED: the target answered 200 with a body this script "
             "could not parse as JSON (%s). Not a flag diagnosis.\n%s")
            % (type(exc).__name__, where))

    return refuse_if_no_stages(body, endpoint, consumer)
