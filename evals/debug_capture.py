"""The one place that turns a gated-debug 403 into an instruction.

POST /api/search answers `debug: true` with 403 wherever the capture channel
is disabled (backend/debug_gate.py, 0.3.2: default OFF, including in
development). httpx's own message for that is `Client error '403 Forbidden'`,
which reads as an auth or ingress problem and sends the reader to the wrong
place; the remedy the route puts in the response body never gets printed.

Every eval script that asks for `debug: true` routes its response through
refuse_if_debug_disabled(), so the operator message lives here instead of
being copied into each caller -- the same reason the route's own refusal text
lives in main.py once. backend/test_debug_gate.py derives the set of callers
by reading evals/ for the debug payload and fails if one of them does not
route through this module, so a new consumer cannot quietly reintroduce the
bare 403.
"""
from __future__ import annotations

REMEDY = (
    "the backend refused debug captures (403). This script needs them: set "
    "GYA_DEBUG_STAGES=1 in the backend environment (the Helm chart sets it for "
    "gya-test; production leaves it 0 on purpose) and restart the pod -- the value "
    "is read from the container environment at start, so a configmap edit alone "
    "does not take effect."
)


def refuse_if_debug_disabled(response, endpoint: str, consumer: str) -> None:
    """Abort with the remedy if `response` is the gate's 403; otherwise return.

    Deliberately a no-op on every other status: this module speaks only about
    the debug gate, and swallowing a 500 or a 404 here would hide a different
    fault behind a confident message about a flag.
    """
    if getattr(response, "status_code", None) != 403:
        return
    raise SystemExit(
        REMEDY + "\n" + ("consumer: %s" % consumer) + "\n"
        + ("endpoint: %s" % endpoint) + "\n"
        + ("body: %s" % (getattr(response, "text", "") or "")[:300]))
