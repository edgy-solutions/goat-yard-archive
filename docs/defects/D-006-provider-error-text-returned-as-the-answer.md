# D-006 — the provider's raw error text is returned to the user as the answer, at HTTP 200

**Status**: open. Scheduled for 0.3.4 by ruling (Chris, 2026-11-01, item 5),
with [D-004](D-004-cold-process-stage-health-false-alarm.md) and
[D-005](D-005-stage-health-conflates-suppression-with-fault.md).
**Found**: 2026-10-26, in the blocked first arm of the paired gate run
(`docs/audits/GATE_RUN_LOCK_structured_answer_laneA_20261025.md`, first
addendum).
**Affects**: 0.3.2 and 0.3.3 identically. `backend/main.py:1096` predates both,
and it is **pre-existing on production** — so it is explicitly **not a 0.3.3
regression and does not block the 0.3.3 ship** (same ruling).
**Not a sibling of D-004/D-005.** Those are two conflations behind one boolean
on `/health/stages`. This one is on the answer path, and it is the inverse
failure: not a flag that says `false` when nothing is wrong, but a **200 and a
populated `answer` field when everything is wrong**.

## What happens

```python
# backend/main.py:1091-1097
except Exception as e:
    if "Assert" in type(e).__name__ or isinstance(e, AssertionError):
          answer = f"Generated answer could not be verified against sources.\nError: {e}"
          verified = False
    else:
          answer = f"Error generating answer: {e}"
          verified = False
```

The second branch interpolates the **raw exception** into the field the product
renders as Gill's answer, and the request returns **HTTP 200**.

## What it actually produced

With a revoked `OPENROUTER_API_KEY` on gya-test, all 28 questions × 3 draws
returned, at 200, an `answer` of:

    Error generating answer: litellm.AuthenticationError: AuthenticationError:
    OpenAIException - User not found.

and, with `GILL_STRUCTURED_ANSWER=1`, the same credential surfaced through the
other client as a `BamlClientHttpError` with `401 Unauthorized`. One cause, two
client names — which is how the cross-client witness established the fault was
flag-independent.

## Four consequences, each independently worth fixing

1. **A user is shown a provider stack string as the commentary's answer.** The
   text names a third-party vendor exception class and an upstream message. The
   product's whole claim is that what a reader sees is Gill's own words or an
   honest refusal; this is a third thing, and it is dressed as the first.

2. **It is a 200, so nothing counts it.** Any monitor, dashboard or SLO built on
   non-2xx responses sees a perfectly healthy service during a total outage of
   the answer path.

3. **An eval harness scores it as a content failure.** This is not
   hypothetical — it is how the defect was found. Arm 1 reported
   **`0/28, 28 STABLE-FAIL, 0 errors`**: a pass rate computed over 84 responses
   that contained no answers. A measurement over absent answers is not a
   measurement, and the harness had no way to tell. Mitigated on the eval side
   only (`evals/run_eval.py`'s run-level abort, `25b5be8`), which catches the
   signature and aborts the run. **That guard is in the harness, not in the
   product**, and a signature list is a denylist: the next provider's error
   phrasing is not on it.

4. **Upstream error text reaches the response body.** In the observed instance
   it was `User not found.` and carried no secret. But the class of thing being
   echoed is an arbitrary exception from an HTTP client, which in other
   failure modes carries request URLs, model and account identifiers, and in
   some client libraries fragments of the request. `/api/search`
   (`backend/main.py:396-399`) declares **no auth dependency** on the handler,
   so on the face of the signature this body is reachable without
   authentication; whether middleware gates the route I did **not** verify, and
   that is the one open question in this entry rather than a claim.

## What the fix has to decide (not decided here)

- The user-facing string must be a **refusal**, not a diagnostic. The product
  already has an honest-refusal vocabulary; this path should use it.
- The diagnostic must still go **somewhere** — logs and `stages_capture` — or
  fixing the leak just converts a loud failure into a silent one. That is the
  trade to get right, and it is the same shape as D-004/D-005: an operator
  needs to distinguish causes that a user must not see.
- **The status code is a separate decision from the body.** A 200 with a refusal
  is defensible; a 200 with a provider exception is not. Changing the code may
  affect clients, so it is a decision, not a cleanup.
- The eval harness's abort stays regardless. It guards a different
  thing — that a run cannot report a pass rate over non-answers — and it should
  not be removed on the grounds that the product no longer emits that string.

## What this entry does NOT establish

- **Not** that the leak has ever exposed a credential. It has not, in anything
  observed.
- **Not** that the route is unauthenticated. The handler declares no auth
  dependency; middleware was not checked.
- **Not** a frequency. It was observed under one induced condition (a revoked
  key). How often production takes this branch for ordinary provider errors —
  rate limits, timeouts, 5xx — is unmeasured, and the branch is reached by
  **every** non-assertion exception in generation, so the population is wider
  than auth failures.
