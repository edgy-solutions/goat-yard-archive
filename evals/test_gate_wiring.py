#!/usr/bin/env python
"""Does `verify_arm` actually CALL the serving-pods gate, with the real inputs?

    python evals/test_gate_wiring.py

`test_expansion_observation.py` proves `serving_pods_fault` is correct. That is
not the same claim as "the gate is live". A correct function that is never
called, or called with an input it derived itself, fails silently and reads as a
pass -- this project has a standing finding on exactly that shape, where a
localizer was written, born-tested, and then handed the wrong argument by its
only caller for 74 of 74 rows.

So this suite fakes the cluster at the `kubectl` boundary and drives the real
`verify_arm`. It asserts three things the pure tests cannot:

1. The endpointslices read HAPPENS (the gate is reached at all).
2. It is reached with the pod that `verify_arm` itself selected, not with
   something recomputed from the same pod list the gate exists to distrust.
3. The two-serving-pods state REFUSES the arm end to end -- the witnessed
   state, through the real control flow.

No cluster, no network, no kubeconfig: every kubectl call is dispatched from a
fixture.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paired_gate_run as pgr  # noqa: E402

EXPECTED_CHECKS = 10
checks = []


def check(name: str, got, want) -> None:
    checks.append((name, got == want, got, want))


NS = "gya-test"
DEPLOY = "gya-frontend-api"
ONE = DEPLOY + "-aaa"
TWO = DEPLOY + "-bbb"
DIGEST = "sha256:2fce1e3467d5f53e4f0700cdd51530db86cc85c8ef7231f091c6e69509b11433"
WRITTEN = datetime(2026, 11, 1, 10, 0, 0, tzinfo=timezone.utc)


def mkpod(name, flag="1", phase="Running", deleting=False):
    meta = {"name": name}
    if deleting:
        meta["deletionTimestamp"] = "2026-11-01T10:00:30Z"
    return {
        "metadata": meta,
        "spec": {"containers": [{"env": [
            {"name": "GILL_STRUCTURED_ANSWER", "value": flag}]}]},
        "status": {
            "phase": phase,
            "startTime": "2026-11-01T10:00:10Z",
            "conditions": [{"type": "Ready", "status": "True"}],
            "containerStatuses": [{"restartCount": 0, "imageID": DEPLOY + "@" + DIGEST}],
        },
    }


def ep(pod, serving=True):
    return {"targetRef": {"kind": "Pod", "name": pod},
            "conditions": {"serving": serving}, "addresses": ["10.0.0.1"]}


def fake_cluster(pods, endpoints, flag="1", calls=None):
    """Dispatch kubectl by what the call is asking for, and record the asks."""
    import json

    def _kubectl(ns, *args, timeout=30):
        if calls is not None:
            calls.append(args)
        if "endpointslices" in args:
            return json.dumps({"items": [
                {"metadata": {"labels": {"kubernetes.io/service-name": DEPLOY}},
                 "endpoints": endpoints}]})
        if "pods" in args:
            return json.dumps({"items": pods})
        if any("matchLabels" in a for a in args):
            return json.dumps({"app.kubernetes.io/name": DEPLOY})
        return flag  # the flag jsonpath

    return _kubectl


def run(pods, endpoints, flag="1", calls=None):
    """Call the REAL verify_arm against a faked cluster."""
    original = pgr.kubectl
    pgr.kubectl = fake_cluster(pods, endpoints, flag, calls)
    try:
        return verify_result(pods, endpoints, flag)
    finally:
        pgr.kubectl = original


def verify_result(pods, endpoints, flag):
    try:
        return ("ok", pgr.verify_arm(NS, DEPLOY, flag, WRITTEN, DIGEST))
    except pgr.Refused as exc:
        return ("refused", str(exc))


# --- 1. the happy path, so a refusal below means something -----------------
calls = []
kind, out = run([mkpod(ONE)], [ep(ONE)], calls=calls)
check("a single serving pod passes the arm", kind, "ok")
check("...and the serving set is RECORDED in the header",
      out.get("serving_pods") if kind == "ok" else out, [ONE])

# --- 2. the gate is actually REACHED ---------------------------------------
# If this fails, serving_pods_fault is dead code and every arm header's
# serving_pods field is a decoration.
check("verify_arm reads endpointslices at all",
      any("endpointslices" in c for c in calls), True)

# --- 3. THE witnessed state, through the real control flow -----------------
# A flag-1 pod and a terminating flag-0 pod, both still serving. The pod scan
# reports "exactly 1 Running pod" (TWO is excluded by its deletionTimestamp),
# which is precisely why the EndpointSlice has to be consulted.
pods = [mkpod(ONE, flag="1"), mkpod(TWO, flag="0", deleting=True)]
kind, out = run(pods, [ep(ONE), ep(TWO)])
check("two serving pods REFUSE the arm", kind, "refused")
check("...and the refusal names the terminating pod", TWO in str(out), True)
check("...and it explains the grace period, not just the count",
      "grace period" in str(out), True)

# The old behaviour, asserted so a regression is legible: the pod scan alone
# does see exactly one Running pod in that same state.
survivors = [p for p in pods
             if p["metadata"].get("deletionTimestamp") is None
             and p["status"]["phase"] == "Running"]
check("the pod scan alone sees only 1 pod in that state -- the blindness",
      len(survivors), 1)

# --- 4. the gate is given the pod verify_arm chose -------------------------
# Not a recomputed one. If the expected pod were derived from the same pod list
# the gate distrusts, a terminating-pod-only serving set would agree with
# itself and pass.
kind, out = run([mkpod(ONE)], [ep(TWO)])
check("serving a pod that is NOT the selected one refuses", kind, "refused")
check("...and the fault names the one actually serving", TWO in str(out), True)

# --- 5. a clean finished rollout must still pass --------------------------
# Otherwise the gate gets relaxed the first time it cries wolf.
kind, _ = run([mkpod(ONE), mkpod(TWO, deleting=True)],
              [ep(ONE), ep(TWO, serving=False)])
check("a terminating pod that stopped serving still passes", kind, "ok")

failed = [c for c in checks if not c[1]]
for name, ok, got, want in checks:
    print("%-4s %-52s got=%r want=%r" % ("PASS" if ok else "FAIL", name, got, want))

if len(checks) != EXPECTED_CHECKS:
    print("FAIL  ran %d checks, expected %d -- a check was lost, which reads "
          "as silence" % (len(checks), EXPECTED_CHECKS))
    sys.exit(1)
print("\n%d/%d checks passed" % (len(checks) - len(failed), len(checks)))
sys.exit(1 if failed else 0)
