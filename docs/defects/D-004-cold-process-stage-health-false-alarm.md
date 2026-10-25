# D-004 — `/health/stages` alarms on a cold process

**Status**: open. Scheduled for 0.3.4 by ruling (Chris, 2026-10-18 consolidated,
item 5).
**Found**: 2026-10-18, during the 0.3.3 smoke on gya-test.
**Affects**: 0.3.2 and 0.3.3 identically — `backend/stage_health.py` is
byte-identical across them, so this is **pre-existing, not a 0.3.3 regression**.
It was simply first witnessed on a pod young enough to be read before its first
request.

## What happens

A freshly started api process, before it has served any search request:

```
GET /health/stages
{"stages": {"expansion": false, "entity_lookup": false,
            "answer": false, "verifier": false},
 "not_observable": []}
```

After exactly one request, the same process:

```
{"stages": {"expansion": true, "entity_lookup": true},
 "not_observable": ["answer", "verifier"]}
```

`answer` and `verifier` move from **`false`** to **`not_observable`** — and
`not_observable` is where this build's own docstring says they always belong,
because the 0.3.x line cannot observe them at all. For the window between
process start and first request, a monitor sees **four stages alarming, two of
them about things this build can never report on**, and nothing in the response
distinguishes that from a real fault.

## Cause — the exact branch

`public_snapshot()` reads counters that are all zero on a cold process, and
zero-observation falls through to a fault verdict:

- `stages["expansion"]` requires `(ok + errored) > 0`; zero → `False`.
- `stages["entity_lookup"]` requires `sum(modes.values()) > 0`; zero → `False`.
- for `answer` and `verifier` the chain is
  `faulted → False`, `elif ok > 0 → True`, `elif unobservable > 0 → append to
  not_observable`, **`else → False`**. On a cold process no branch above the
  last one can fire, so the final `else` reports a fault.

`not_observable` is populated **per request**, from
`record_request(..., unobservable=...)`. It is therefore a fact about traffic
that has happened, when what it actually states is a fact about **the build**.
A property of the build is being derived from the request stream, so before the
first request it cannot be known — and the code answers "faulted" instead of
"not known".

This is the inverse shape of the usual failure: there is no channel for "nothing
observed yet", so the absent channel turns into a **confident alarm** rather
than a confident reading. The module's own `_fresh_state()` docstring makes the
same argument for `not_run` being a third state next to `ok`; the public
snapshot then collapses the third state it was given.

## Fix, as ruled

1. **Derive `not_observable` from the build at startup**, not from the request
   stream. Which stages this build can observe is a static property of the
   build; it belongs in a module-level declaration evaluated at import, so the
   answer is the same before the first request as after the millionth.
2. **A stage that is observable but has no observations yet is not `false`.** It
   needs the same third-outcome treatment — omitted from `stages`, or reported
   in its own bucket. `false` must mean "observed and faulted", nothing else,
   because `false` is what pages someone.

## Born-test

**A fresh process, zero requests, must produce no false alarm.** Start the app,
call `/health/stages` before anything else touches it, and assert that no stage
reports `false`, that `answer` and `verifier` appear in `not_observable`, and
that this holds *identically* before and after the first successful request. The
test has to run against a genuinely cold process — a suite that calls
`_reset_for_tests()` after an import that already served traffic is not cold,
and a check that cannot see the cold window has not tested it.

## What this does NOT cover

- The real fault verdicts are unaffected: a faulted stage still reports `false`
  correctly. This is only about the zero-observation window.
- It does not make `answer` or `verifier` observable. That is a separate piece
  of work on the 0.3.x line's generation path, and this defect must not be
  closed by pretending otherwise.
- No monitor is known to be polling `/health/stages` today, so the live impact
  is a latent one. That is a reason to fix it before something starts polling,
  not a reason to downgrade it.
