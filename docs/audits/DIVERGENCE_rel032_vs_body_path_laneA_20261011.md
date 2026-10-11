# Divergence: release-0.3.2 vs body-path, 2026-10-11

Written for Chris, as the input to one decision: whether the two 0.3.2 backend
commits get forward-ported to `body-path` now, later, or at merge.

## What is actually divergent

`release-0.3.2` forked from `84d8afa` (0.3.0). `body-path` is 245 commits ahead
of it on everything else. Of the seven commits on the release line, five are
already on `body-path` under different shas or need nothing:

| release-0.3.2 | on body-path? |
|---|---|
| `c9186b1` entity manifest a pure function | yes, as `5c93b28` |
| `fe8ea83` release 0.3.1 | release bookkeeping only |
| `88d18b6` release 0.3.2 | release bookkeeping only |
| `2e2fa41` citation pairing regex | yes, as `aaf48c9` |
| `9763cf9` bounded transport retry | yes — ported FROM body-path |
| `7a5a69a` `/health/stages` name+boolean | **NO** |
| `0f3fe6d` + `824b8d2` debug gate | **NO** |

So the gap is two features, not a branch's worth of drift.

## Why they are not ported yet

**The debug gate cannot be ported to `body-path` without a deploy decision.**
`evals/run_eval.py:424` on `body-path` posts `{"debug": true}` on every scored
arm, and the comment above it says why: the structured BAML fields the harness
scores against live in `stages`, and on 2026-09-20 a prediction written against
them could not be scored at all because they were absent. Port the gate and
every scored arm 403s unless `GYA_DEBUG_STAGES=1` is set on the backend the arm
is pointed at — one week before the run that decides the `GILL_STRUCTURED_ANSWER`
flip. That is not a hygiene change; it is a change to the eval lane's
prerequisites, so it is named here instead of done.

`values-test.yaml` on the release line already sets the flag to `1` for
gya-test, so the arrangement works — but only once that chart is deployed and
the pod restarted (envFrom is read at container start). Sequence matters.

**`/health/stages` touches `backend/stage_health.py`**, which the deferred
`baml_punt:<reason>` split is also waiting on, for the reason that the file must
stay byte-identical across a measured pair. Both arms of a pair run after an
edit are fine; an arm compared against one recorded before it is not. That is a
question about when the next pair runs, which is Chris's.

Note also that `body-path`'s `snapshot()` carries `expansion.retries`, which the
release line does not. If `public_snapshot()` is ported as-is, that counter is
*available* and *unread* — so the bounded retry's exhaustion would still not show
up in the boolean. Treating "retries exhausted" as a fault is a design decision,
not part of a port, and is not made here.

## Release-safety check done

Nothing in `frontend/` requests `debug`, on either line (the only match is the
word in `Privacy.tsx` prose). The 403 cannot reach the UI. The consumers are
eval scripts only, and both of them now route through `evals/debug_capture.py`.

## What this does NOT establish

- Neither feature has been exercised against a deployed backend. The gate's
  403, the `/health/stages` projection and the retry are all verified by unit
  assertion and source probe in this repo, not by a request to a running pod.
- It does not say the port is safe once the flag is set. It says the one
  coupling I found makes it unsafe without it; there may be another consumer
  outside `evals/`, which the derived probe cannot see.
- `5c93b28` is still not an ancestor of `main`. A deploy from a `main` checkout
  still silently regresses production to 0.3.0. Unchanged by anything here.
