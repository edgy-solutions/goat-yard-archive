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
from run_eval import expansion_observation  # noqa: E402

EXPECTED_CHECKS = 15
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

failed = [c for c in checks if not c[1]]
for name, ok, got, want in checks:
    print("%-4s %-45s got=%r want=%r" % ("PASS" if ok else "FAIL", name, got, want))

assert len(checks) == EXPECTED_CHECKS, (
    "ran %d checks, expected %d -- a check was lost, which reads as silence"
    % (len(checks), EXPECTED_CHECKS))
print("\n%d/%d checks passed" % (len(checks) - len(failed), len(checks)))
sys.exit(1 if failed else 0)
