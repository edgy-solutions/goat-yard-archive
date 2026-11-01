#!/usr/bin/env python
"""Born-tests for `accept_0_3_3.py` -- the acceptance script, exercised.

    python evals/test_accept_0_3_3.py

No cluster, no network. Two kinds of check:

1. **Anti-drift.** The script hard-codes three things that live somewhere else:
   the SID regex (backend/main.py) and the two image digests
   (charts/goat-yard-archive/values-frontend.yaml). A copied constant that
   silently diverges from its source is how an acceptance script comes to accept
   a release other than the one being shipped. These checks make the copy fail
   loudly rather than quietly describe the wrong artefact.

2. **Behaviour of the witness predicates.** `witness_draw` decides whether a
   draw is a release failure. 0.3.2's acceptance script had no tests at all, and
   an unexercised acceptance script is a gate whose PASS asserts nothing
   demonstrated. Each refusal branch is driven here, including the two that
   exist to stop a VACUOUS pass (empty context, no cited SID).
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import accept_0_3_3 as acc  # noqa: E402

EXPECTED_CHECKS = 21
checks = []


def check(name: str, got, want) -> None:
    checks.append((name, got == want, got, want))


def read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


# --- 1. anti-drift: the copied constants still match their sources ----------
main_py = read("backend/main.py")
check("SID_RE is still backend/main.py's pattern",
      acc.SID_RE.pattern in main_py, True)
check("...and backend/main.py really does define one (the probe did not miss)",
      "_SID_IN_ANSWER_RE" in main_py, True)

vf = read("charts/goat-yard-archive/values-frontend.yaml")
check("API_DIGEST matches the prod chart pin", acc.API_DIGEST in vf, True)
check("UI_DIGEST matches the prod chart pin", acc.UI_DIGEST in vf, True)
check("...and the chart really pins by digest (the probe did not miss)",
      vf.count("digest:") >= 2, True)

api_dep = read("charts/goat-yard-archive/templates/api-deployment.yaml")
# The reason item 3 reads the container's environment instead of the pod spec.
# If this ever becomes false, the comment in accept_0_3_3.py is wrong and the
# cheaper jsonpath probe becomes available.
check("the api container still gets the flag via envFrom, not explicit env",
      "envFrom" in api_dep and "GILL_STRUCTURED_ANSWER" not in api_dep, True)
check("and api-deployment.yaml still has no checksum/config (D-007)",
      "checksum/config" in api_dep, False)


# --- 2. context_sids ------------------------------------------------------
def doc(answer="x", sids=("ABC_S1",), verified=True, refused=False, key="sentence_id"):
    return {
        "answer": answer,
        "verified": verified,
        "refused": refused,
        "evidence": [{"sentence_data": [{key: s} for s in sids]}],
    }


check("context_sids reads sentence_id",
      acc.context_sids(doc(sids=("ABC_S1", "ABC_S2"))), {"ABC_S1", "ABC_S2"})
check("context_sids also reads the `sid` spelling",
      acc.context_sids(doc(sids=("ABC_S9",), key="sid")), {"ABC_S9"})
check("context_sids strips brackets",
      acc.context_sids(doc(sids=("[ABC_S3]",))), {"ABC_S3"})
check("context_sids on a response with no evidence is EMPTY, not an error",
      acc.context_sids({"evidence": []}), set())


# --- 3. witness_draw, branch by branch -----------------------------------
fault, obs = acc.witness_draw(doc(answer="Gill says [ABC_S1] plainly.",
                                  sids=("ABC_S1", "ABC_S2")))
check("a clean draw is no fault", fault, None)
check("...and the observation records what was cited", obs["cited"], ["ABC_S1"])

fault, _ = acc.witness_draw(doc(
    answer="Error generating answer: litellm.AuthenticationError"))
check("a D-006 error string in `answer` is a FAULT, not a 200",
      fault is not None and "D-006" in fault, True)

# The two vacuous-pass guards. Without them `cited <= context` is 0 <= 0.
fault, _ = acc.witness_draw({"answer": "[ABC_S1]", "verified": True,
                             "evidence": []})
check("empty retrieved context is a FAULT (the subset check would pass on "
      "nothing)", fault is not None and "pass on nothing" in fault, True)

fault, _ = acc.witness_draw(doc(answer="I cannot answer from Gill.",
                                refused=True))
check("an answer citing no SID is a FAULT", fault is not None and
      "cites no sentence id" in fault, True)

fault, _ = acc.witness_draw(doc(answer="see [ZZZ_S7]", sids=("ABC_S1",)))
check("a cited SID absent from the context is a FAULT naming ADR-0006",
      fault is not None and "ADR-0006" in fault, True)

fault, _ = acc.witness_draw(doc(answer="Gill says [ABC_S1].", verified=False))
check("verified=False is a FAULT even when every cited SID resolves",
      fault is not None and "verified=False" in fault, True)


# --- 4. image_id_check: an empty selector must FAIL, not pass -------------
class FakeRun:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


def with_kubectl(stdout, returncode=0):
    original, acc.results[:] = acc.kubectl, []
    acc.kubectl = lambda *a, **k: FakeRun(stdout, returncode)
    try:
        acc.image_id_check("probe", "gya-frontend-api", acc.API_REPO, acc.API_DIGEST)
        return acc.results[-1][1]
    finally:
        acc.kubectl = original
        acc.results[:] = []


check("no pod matching the selector FAILS (a probe that misses passes on "
      "nothing)", with_kubectl(""), False)
check("a pod on the wrong digest FAILS",
      with_kubectl("pod-a ghcr.io/x/backend@sha256:deadbeef|"), False)
check("a pod on the signed digest PASSES",
      with_kubectl("pod-a ghcr.io/x/backend@" + acc.API_DIGEST + "|"), True)

failed = [c for c in checks if not c[1]]
for name, ok, got, want in checks:
    print("%-4s %-62s got=%r want=%r"
          % ("PASS" if ok else "FAIL", name, got, want))

if len(checks) != EXPECTED_CHECKS:
    print("FAIL  ran %d checks, expected %d -- a check was lost, which reads "
          "as silence" % (len(checks), EXPECTED_CHECKS))
    sys.exit(1)
print("\n%d/%d checks passed" % (len(checks) - len(failed), len(checks)))
sys.exit(1 if failed else 0)
