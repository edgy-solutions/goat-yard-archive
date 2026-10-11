# D-003 — The retry bound is declared but not observed

**Status:** open, known at cut, scheduled for **0.3.3**. Not a bug in the retry; a gap in the
evidence about it.
**Opened:** Lane A1, 2026-10-11, by Chris's ruling — "Retry attempt counter -> 0.3.3; note in
0.3.2 release notes that retries are bounded but unobserved."
**Shipped in:** 0.3.2 (`9763cf9`). Release notes: `docs/releases/0.3.2.md`.

## The defect

`retry_policy BoundedTransport` on `client<llm> LocalRouter` gives both backend BAML
functions — `OptimizeSearchQuery` (expansion) and `RepairQuote` — at most four attempts
against a transport fault. The policy is asserted in `baml_src/main.baml` **and** in
`baml_client/inlinedbaml.py`, the copy the runtime actually parses, so the retry happens.

**Nothing reads the attempt count.** `backend/stage_health.py` on the release line records a
stage's name and a boolean. A call that burned all four attempts and then failed produces the
same `expansion: false` as a call that failed on its first try. Consequences:

- `/health/stages` **cannot distinguish flaky transport from broken transport.** The two have
  different remedies (leave it alone / page someone) and the same signal.
- A backend sitting at three retries on every request — degraded but succeeding — is
  indistinguishable from a healthy one. The bound's own exhaustion is the leading indicator of
  the fault it was added for, and it is the one thing not reported.
- The fix that motivated the policy (one voided eval arm, one truncated body in 67 requests,
  `hyper::Error(IncompleteMessage)`) cannot be confirmed to have taken effect in production by
  any production signal.

## Why it was shipped this way

The retry itself is the thing production needed, and it is small, bounded and verified at the
layer it acts on. The counter is a different piece of work: it needs a per-call hook into the
BAML collector, a decision about whether "retries exhausted" is a **fault** (which would make
`/health/stages` go red on a request that eventually succeeded — a design decision, not a
port), and a shape for the number in a projection whose whole premise is "name and boolean, no
counters". Bundling that into 0.3.2 would have widened a release that was closing a data-exposure
channel.

## What already exists to build on — the two halves are on different branches

This is not a feature to design. **Both halves exist; neither branch has both.**

- **`body-path` has the observation, with no narrowed surface.** `backend/stage_health.py`
  there defines `retries_from_baml_log(log)` (attempts-minus-one as `len(log.calls) - 1`, with
  `None` kept distinct from `0` because a missing collector says *nothing* about retries), and
  `_fresh_state()` carries `expansion.retries` with `total`, `calls_with_retries`,
  `max_observed`, **`bound_exhausted`** and **`unobserved`** — the third state, deliberately
  outside the counts. `backend/main.py` passes `expansion_retries=` at two call sites
  (`:844`, `:1242`). Measured note worth keeping: retries are counted by call length and *not*
  by `LLMCall.selected`, which is `True` on every call including the failures under baml_py
  0.211.1, so it cannot identify the winning attempt.
- **The release line has the narrowed surface, with nothing to put in it.** `7a5a69a`'s
  `public_snapshot()` is name-and-boolean by design and is not on `body-path`.

So 0.3.3's work is the join, and the only open question is a **design decision the port does
not make for you**: does `bound_exhausted > 0` turn the `expansion` boolean **false**? That
would make `/health/stages` go red on requests that eventually *succeeded*, which is a
different claim than the boolean makes today. A projection whose premise is "no counters" also
has nowhere to put "max_observed: 3". Resolve that before porting, or the counters land
available-and-unread and look like progress while changing nothing.

## Not in scope here

- Retrying anything other than a transport fault. A model that answers wrongly, slowly, or with
  an unparseable body is a separate problem.
- The latency the retry adds (~1.4s across 200/400/800ms on the one request in 67 that needs
  it). Named, not measured on a pod.
- Telling a user anything when expansion fails. Still unaddressed, separately.
