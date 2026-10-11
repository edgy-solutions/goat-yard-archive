# Ruling 3 (smoke 0.3.2 on gya-test) is blocked on a deployment decision

**Date:** 2026-10-11 · **Lane:** A1 · **Branch:** release-0.3.2
**Ruling:** "Smoke 0.3.2 on gya-test: /health/stages, nested-quote citation
verifies, debug 403/200 by flag."

Every fact below is from read-only `kubectl`/`helm`/`gh` queries. Nothing was
changed in any namespace.

## What is actually running on gya-test

| Thing | State | Age |
|---|---|---|
| `gya-frontend-api` image | `backend:latest` @ `sha256:50ff394f…` | pod started **2026-08-02** |
| helm release `gya-backend-test` | chart `goat-yard-archive-0.2.1`, rev 26 | last upgrade **2026-06-21** |
| helm release `gya-frontend-test` | chart `goat-yard-archive-0.2.1`, rev 20 | last upgrade **2026-06-21** |
| configmap `gya-frontend-config` | 14 keys, **no** `GYA_DEBUG_STAGES`, **no** `GILL_STRUCTURED_ANSWER` | 231d |

So gya-test is ~70 days behind on the image and **~4 months behind on the
chart**. The two flags the ruling turns on do not exist in its environment at
all, which is why nothing there can be smoked as it stands.

## What is NOT a problem

- **Prod is not on the shared tag.** `gya-frontend` namespace pins
  `backend:0.3.0` and `frontend:0.3.0`. Only gya-test tracks `:latest`, so
  pushing or pulling `:latest` cannot reach production.
- **The 0.3.2 image exists.** The merge-forward push built it: Build Containers
  run `38181578224`, success, 2026-10-11T22:43:53Z, from `main` -- which is the
  two release branches merged. Nothing needs building. It predates `530696c`
  (release notes, D-003, the corrected main.baml comment), which is docs and one
  comment, so the running code would be 0.3.2 behaviourally.
- **No new required env key.** Every `os.getenv("X")` with no default in the
  0.3.2 backend is a SECRET key (`OPENROUTER_API_KEY`, `OPENROUTER_API_KEY_ANON`,
  `CLERK_WEBHOOK_SECRET`, `LANGFUSE_SECRET_KEY`), not a configmap key. So the
  code jump does not obviously want something the 0.2.1 chart does not provide.
  This is a *scan*, not a run: it cannot see a key read through a wrapper.

## Why this is Chris's call and not mine

There is no small version of this.

1. **`helm upgrade` to the current chart** is a 0.2.1 -> current jump touching
   weaviate connection config, minio, postgres and both deployments at once. No
   one has rehearsed it, and the chart as committed does not even
   `helm template` (`missing in charts/ directory: minio`) without a
   `helm dependency build` first. gya-test's Weaviate is the corpus other lanes
   read, so a bad upgrade is not contained to this task.
2. **Image-only bump** (`kubectl rollout restart` + `kubectl set env
   GYA_DEBUG_STAGES=1`) is one resource and reversible (`rollout undo`,
   `set env VAR-`), but it runs 0.3.2 code against a 0.2.1 chart and leaves
   deliberate drift from the helm release that the next upgrade silently wipes.
   It also still jumps the backend ~70 days in one step.

Either way the decision is "how does gya-test get current", which is a
deployment question on a shared cluster, not a step inside this ruling.

## What is already verified without a cluster

The three things the smoke would check are covered by born-checks on both
branches -- which is **not** the same claim as "verified live", and is exactly
why the ruling exists:

- debug 403/200 by flag: `backend/test_debug_gate.py` (22/22 on body-path),
  both directions, plus the chart-render assertion that gya-test's values set
  it ON and prod's set it OFF.
- `/health/stages` semantics: `backend/test_stage_health.py` 31/31 on the
  release line.
- nested-quote citation: `backend/test_quote_cite_pairing.py` 14/14.

**None of that is a live smoke.** A rendered chart value is not an environment,
and `envFrom` is read at container start, so the one failure mode a born-check
structurally cannot see is "the pod was never restarted".

## A second finding, independent of the above

`/health/stages` is **not reachable through the ingress**. The ingress routes
only `/` -> ui and `/api` -> backend, and the route is registered at
`/health/stages`, not `/api/health/stages` -- so from outside the cluster that
path is served the frontend SPA (confirmed: `curl` against the test host returns
`<!doctype html>`). `/health` has always sat there and is fine, because its
consumer is the k8s probe in `api-deployment.yaml`. But a *monitor* is the
consumer 0.3.2 added `/health/stages` for, and a monitor outside the cluster
cannot see it. Either it moves under `/api`, or its consumer is in-cluster only
and the release notes should say so.

## What this does NOT solve

- It does not tell you whether 0.3.2 works on a real corpus. That is the whole
  content of ruling 3 and it remains open.
- It does not establish that the 0.2.1 chart is adequate for 0.3.2 -- only that
  no *unconditionally read* env key is missing.
- It says nothing about the frontend, which also tracks `:latest` and would be
  pulled by the same restart.
