#!/usr/bin/env python
"""Born-test for the expansion-branch measurement used by the paired gate run.

This instrument decides a number Chris asked for by name. An untested
instrument makes that number a guess with a decimal point on it.

The count assertion at the bottom is not ceremony: an exception in a
hand-rolled suite ends the run and the lost assertions look like silence, so
the suite asserts how many checks it ran.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_eval import expansion_observation, backend_error_signature  # noqa: E402

EXPECTED_CHECKS = 35
checks = []


def check(name: str, got, want) -> None:
    checks.append((name, got == want, got, want))


Q = "What does Gill say about the Word of God?"

# The branch under measurement: retrieval ran on the raw question with no
# entity anchor. This is the signature, and it is a UNION of two causes.
check("discard signature",
      expansion_observation(Q, {"expanded_query": Q, "mapped_entities": []})["state"],
      "raw_query_no_entities")

# Whitespace must not decide a branch. A trailing newline on either side is a
# transport artefact, not a different retrieval.
check("whitespace is not a branch",
      expansion_observation(Q, {"expanded_query": Q + "\n", "mapped_entities": []})["state"],
      "raw_query_no_entities")

# Expansion took effect: the string retrieval ran on is not the question.
check("expanded with entities",
      expansion_observation(Q, {"expanded_query": Q + ", Divine Revelation",
                                "mapped_entities": ["GOD"]})["state"],
      "expanded_with_entities")

check("expanded without entities",
      expansion_observation(Q, {"expanded_query": Q + ", Holy Writ",
                                "mapped_entities": []})["state"],
      "expanded_no_entities")

# Raw query but entities present: a real third case (the anchored-manifest
# path can keep entities while the expansion string is dropped). It must not
# be folded into the discard count.
check("raw query with entities is its own state",
      expansion_observation(Q, {"expanded_query": Q, "mapped_entities": ["GOD"]})["state"],
      "raw_query_with_entities")

# "Nothing here" must be representable. A response that does not report the
# field is not a response reporting the raw question.
check("absent expanded_query is unreported",
      expansion_observation(Q, {"mapped_entities": []})["state"],
      "unreported")
check("absent mapped_entities is unreported",
      expansion_observation(Q, {"expanded_query": Q})["state"],
      "unreported")
check("empty response is unreported",
      expansion_observation(Q, {})["state"],
      "unreported")
# ...and it must name WHICH field was missing, so an unreported tally can be
# attributed instead of shrugged at.
check("unreported names the missing fields",
      sorted(expansion_observation(Q, {})["missing"]),
      ["expanded_query", "mapped_entities"])

# --- the arm's pod-flag witness -------------------------------------------
# The dangerous state this discriminates is real and routine: between a
# `kubectl set env` and the new pod being Ready, the deployment says one value
# and the running pod says the other. A check against the deployment alone
# would call that arm valid.
from paired_gate_run import pod_flag_fault  # noqa: E402


def mkpod(env):
    return {"spec": {"containers": [{"env": env}]}}


fault, realized = pod_flag_fault(mkpod([{"name": "GILL_STRUCTURED_ANSWER", "value": "0"}]), "0")
check("pod agrees with the arm", (fault, realized), (None, "0"))

fault, realized = pod_flag_fault(mkpod([{"name": "GILL_STRUCTURED_ANSWER", "value": "0"}]), "1")
check("pod booted with the OTHER value is a fault", fault is not None, True)
check("...and the realized value is reported, not the claim", realized, "0")

fault, realized = pod_flag_fault(mkpod([{"name": "SOMETHING_ELSE", "value": "1"}]), "0")
check("flag absent from the pod spec is a fault", fault is not None, True)
check("...absent is not reported as a value", realized, None)

fault, realized = pod_flag_fault({"spec": {"containers": []}}, "0")
check("no containers is a fault, not a crash", fault is not None, True)

# --- the arm's TRAFFIC witness --------------------------------------------
# The state these discriminate was witnessed, not imagined: during arm 1 a
# flag-0 and a flag-1 pod were both Ready while --verify-only passed, because
# the pod scan drops anything with a deletionTimestamp and a terminating pod
# keeps serving (and keeps `serving: true`) until its grace period ends.
from paired_gate_run import serving_pods_fault  # noqa: E402

D = "gya-frontend-api"


def mkslice(eps, svc="gya-frontend-api"):
    return {"items": [{"metadata": {"labels": {"kubernetes.io/service-name": svc}},
                       "endpoints": eps}]}


def ep(pod, serving=True, key="serving"):
    return {"targetRef": {"kind": "Pod", "name": pod},
            "conditions": {key: serving}, "addresses": ["10.0.0.1"]}


ONE = D + "-aaa"
TWO = D + "-bbb"

fault, serving = serving_pods_fault(mkslice([ep(ONE)]), D, ONE)
check("one serving pod, as expected", (fault, serving), (None, {ONE}))

# THE witnessed defect: the old check saw "exactly 1 Running pod" here.
fault, serving = serving_pods_fault(mkslice([ep(ONE), ep(TWO)]), D, ONE)
check("a second SERVING pod is a fault", fault is not None, True)
check("...and the fault names the extra pod", TWO in (fault or ""), True)
check("...and both are reported, not just the expected one", serving, {ONE, TWO})

# A terminating pod that has actually stopped serving is NOT a fault: the gate
# must not refuse a clean rollout that finished, or it will be relaxed.
fault, serving = serving_pods_fault(
    mkslice([ep(ONE), ep(TWO, serving=False)]), D, ONE)
check("a terminating pod no longer serving is not a fault", (fault, serving),
      (None, {ONE}))

# Pods of some OTHER deployment sharing the namespace are not this gate's
# business -- otherwise the gate fails for a reason the operator cannot act on.
fault, serving = serving_pods_fault(
    mkslice([ep(ONE), ep("gya-frontend-ui-xyz")]), D, ONE)
check("another deployment's serving pod is ignored", (fault, serving), (None, {ONE}))

# An empty read is a refusal, never a pass: something has to be routing the
# arm's requests.
fault, serving = serving_pods_fault({"items": []}, D, ONE)
check("no endpoints at all is a fault, not a pass", fault is not None, True)
check("...and it says the check did not run", "did not run" in (fault or ""), True)

# An endpoint this function cannot attribute could BE the terminating pod.
fault, _ = serving_pods_fault(
    {"items": [{"metadata": {"labels": {}},
                "endpoints": [{"conditions": {"serving": True},
                               "addresses": ["10.0.0.9"]}]}]}, D, ONE)
check("an unattributable serving endpoint is a fault", fault is not None, True)

# ...but one that is explicitly NOT serving is not worth refusing over.
fault, _ = serving_pods_fault(
    {"items": [{"metadata": {"labels": {}},
                "endpoints": [{"conditions": {"serving": False},
                               "addresses": ["10.0.0.9"]}]},
               {"metadata": {"labels": {"kubernetes.io/service-name": "s"}},
                "endpoints": [ep(ONE)]}]}, D, ONE)
check("an unattributable NON-serving endpoint is not a fault", fault, None)

# Degraded basis: the right answer read off the wrong field still gets said
# out loud. Fix the reading, do not relax the gate.
fault, serving = serving_pods_fault(
    mkslice([ep(ONE, key="ready")]), D, ONE)
check("correct set on a degraded basis is still a fault", fault is not None, True)
check("...and it names the field it actually read", "ready" in (fault or ""), True)

fault, serving = serving_pods_fault(
    {"items": [{"metadata": {"labels": {}},
                "endpoints": [{"targetRef": {"name": ONE}, "conditions": {}}]}]},
    D, ONE)
check("no condition at all is assumed SERVING", serving, {ONE})
check("...and that assumption is reported", fault is not None, True)

# --- a backend error string is not an answer ------------------------------
# Arm 1 of the gate run scored this as 28 content failures and reported a
# 0/28 pass rate with "0 errors". A pass rate over absent answers is not a
# measurement, so this signature has to stop the run.
ARM1 = ("Error generating answer: litellm.AuthenticationError: "
        "AuthenticationError: OpenAIException - User not found.")
sig = backend_error_signature(ARM1)
check("the arm-1 string is caught", sig is not None, True)
check("...and it names the provider class", "authenticationerror" in (sig or ""), True)
check("rate limit shape is caught",
      backend_error_signature("Error generating answer: litellm.RateLimitError: 429")
      is not None, True)

# The negative that matters most. Gill writes about error, sin and judgement
# constantly; a word-match heuristic here would discard real data on the
# questions most worth scoring.
check("Gill on error is NOT a backend fault",
      backend_error_signature(
          "Gill argues that the error of the Arminians lies in supposing the "
          "will to be free; see also his remarks on error in doctrine."),
      None)
check("an answer merely STARTING with the word error is not a fault",
      backend_error_signature(
          "Error is the fruit of ignorance, as Gill observes on Romans 1."),
      None)
check("empty answer is not a backend fault signature",
      backend_error_signature(""), None)

failed = [c for c in checks if not c[1]]
for name, ok, got, want in checks:
    print("%-4s %-45s got=%r want=%r" % ("PASS" if ok else "FAIL", name, got, want))

assert len(checks) == EXPECTED_CHECKS, (
    "ran %d checks, expected %d -- a check was lost, which reads as silence"
    % (len(checks), EXPECTED_CHECKS))
print("\n%d/%d checks passed" % (len(checks) - len(failed), len(checks)))
sys.exit(1 if failed else 0)
