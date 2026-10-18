# Ruling 3 (smoke 0.3.2 on gya-test) is blocked on a deployment decision

**Date:** 2026-10-11 · **Lane:** A1 · **Branch:** release-0.3.2
**Ruling:** "Smoke 0.3.2 on gya-test: /health/stages, nested-quote citation
verifies, debug 403/200 by flag."

**STATUS: RESOLVED 2026-10-18 — the smoke ran.** Both blockers below were decided by Chris on 2026-10-18 and are answered in the final section; the sections that frame them as open are kept as the record of what the choice looked like beforehand.

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

---

# RESOLVED 2026-10-18 — the smoke ran

**Date:** 2026-10-18 · **Lane:** A1 · **Decided by:** Chris, rulings of 2026-10-18
(gya-test to 0.3.2 by **image bump + env, not chart upgrade**; `/health/stages`
stays **in-cluster** for 0.3.2).

The two open decisions above are made. The sections "Why this is Chris's call and
not mine" and "A second finding" are left exactly as written — they record what
the choice looked like before it was made — and are answered here.

## Method: pinned by digest, not by tag

`:latest` is not a version. The deployment had tracked it for 76 days, and a
`rollout restart` of an unpinned tag would have pulled whatever `latest` meant
today without naming it in any record. Per the ruling, the image is pinned by
digest and the digest is named here.

| | |
|---|---|
| **Image** | `ghcr.io/edgy-solutions/goat-yard-archive/backend@sha256:ac37c84fed147f96fb14c276a8fb51869d6b6d765257959e578bc6366d0c7d8e` |
| **Built by** | Build Containers run `38181578224`, 2026-10-11T22:43:53Z |
| **Head SHA** | `a88ad6f` — identical to `origin/main` |
| **Previous imageID** | `sha256:50ff394f77657c1383b20d69d80ca714b34e270b1cca263751849b4107694938` (the 76-day-old pod) |

No Build Containers run exists after `38181578224`, so `:latest` still pointed at
this digest on 2026-10-18 — the bump is a *pin* of what was already nominally
deployed, not a version jump.

**Digest provenance, and its weakness.** The digest comes from that run's build
log (`pushing manifest for ...backend:latest@sha256:ac37c84...`). The registry
could **not** be queried directly: the available `gh` token lacks `read:packages`
and the package is not anonymously pullable (`ghcr.io` anon token → `DENIED`). A
registry HEAD would have been the stronger witness. What rescues it is that the
pin is **self-witnessing** — a digest that did not exist could not have been
pulled — and the running pod reports back exactly the digest asked for:

```
gya-frontend-api-7c498549b5-f22tq  Running
  ghcr.io/edgy-solutions/goat-yard-archive/backend@sha256:ac37c84fed...66d0c7d8e
```

## Every mutation run, in order

Read-only `kubectl get` / `helm list` / `gh` / `curl` queries are omitted. These
are all of the changes:

```
kubectl -n gya-test set image deploy/gya-frontend-api \
  api=ghcr.io/edgy-solutions/goat-yard-archive/backend@sha256:ac37c84fed147f96fb14c276a8fb51869d6b6d765257959e578bc6366d0c7d8e
kubectl -n gya-test rollout status deploy/gya-frontend-api --timeout=240s
kubectl -n gya-test set env deploy/gya-frontend-api GYA_DEBUG_STAGES=1
kubectl -n gya-test rollout status deploy/gya-frontend-api --timeout=240s
```

Both rollouts reported `successfully rolled out`. **One resource was touched:**
`deploy/gya-frontend-api`. Weaviate, minio, postgres and `gya-frontend-ui` were
not touched — the gya-test corpus is shared and does not move under the gate.

The image and the flag were applied as **two** rollouts rather than one patch on
purpose: if the pod had failed to come up, a combined change could not say which
half did it.

Reversal, if needed: `kubectl -n gya-test rollout undo deploy/gya-frontend-api`
(twice, or `--to-revision=30`), or `kubectl -n gya-test set env
deploy/gya-frontend-api GYA_DEBUG_STAGES-` for the flag alone.

## Before/after manifest diff

Noise filtered (`resourceVersion`, `generation`, timestamps, `uid`):

```
-     deployment.kubernetes.io/revision: "30"
+     deployment.kubernetes.io/revision: "32"

+         - name: GYA_DEBUG_STAGES
+           value: "1"

-         image: ghcr.io/edgy-solutions/goat-yard-archive/backend:latest
+         image: ghcr.io/edgy-solutions/goat-yard-archive/backend@sha256:ac37c84fed...66d0c7d8e
```

Revision 30 → 32. Two substantive changes and the ReplicaSet condition that
follows from them. Nothing else in the spec moved.

## Smoke results — all three items of ruling 3

Predictions were derived from `backend/main.py:411-421` on `origin/main` before
any request was sent, not written afterwards.

| item | predicted | observed | |
|---|---|---|---|
| `debug: true`, flag **absent** | 403 naming the variable | **403** — `stage debug captures are disabled in this deployment; set GYA_DEBUG_STAGES=1 on the backend to enable them` | PASS |
| `debug: true`, flag **= 1** | 200, non-empty `stages` | **200**, `stages` dict with **24** keys (`bot_raw_answer`, `embedding_hash`, `retrieval_sids_ordered`, …) | PASS |
| `GET /health/stages` in-cluster | 200, name+boolean only | **200** — `{"stages":{"expansion":true,"entity_lookup":true},"not_observable":["answer","verifier"]}` | PASS |
| nested-quote citation pairs | `failures == []` | **3/3 recorded instances pair**; bare citation still fails; capture cannot span two quotes | PASS |

The 403 half is only observable *before* the flag is set, so it was run in that
window — the one-way door was used in the right order.

`/health/stages` returned exactly the documented shape: `answer` and `verifier`
carry **no boolean** and are named in `not_observable`, so a consumer gets a
`KeyError` rather than a wrong answer.

### How the nested-quote item was actually verified, and why not by a generation

Two live generations were run (`faith`, `resurrection at the last day`, 48s and
54s). **Neither produced the nested-quote shape** — a run of two closing marks
before a SID. That is not a surprise: the defect was measured at 9 instances
across 108 recorded answers (~8%), so a live generation is a coin that mostly
lands the other way, and a smoke that depends on luck proves nothing when it
passes and nothing when it fails.

So the item was verified two deterministic ways instead, both **on the deployed
pod**:

1. **The regex in the running image is the fixed one.** `QUOTE_WITH_CITE_RE` read
   out of `/app/backend/bot.py` in the pod is byte-identical to
   `origin/main:backend/bot.py:70-72` — the closer is a *run* of marks, which is
   the whole of `2e2fa41`.
2. **The deployed pairing function was exercised on the recorded instances.** The
   three verbatim instances from `backend/test_quote_cite_pairing.py`
   (`JOHN_6_39_S00`, `GENESIS_2_15_S01`, `GENESIS_3_24_S00`) all returned
   `failures == []` against the deployed `bot._repair_quotes_in_answer`.

Gated in **both** directions in the same probe, because a repair that also lets
bad citations through is not a repair: a genuinely bare citation still failed
with `no_gill_quote_for_citation`, and the capture still could not span two
separate quotes (`"first thing" and "second thing" [SID]` captures only
`second thing`).

The probe disabled `_try_repair_quote_llm` before running. A smoke must not reach
a model endpoint, and must not pick one on its own.

### A result that looks like a failure and is not

Both live queries returned `verified: false`. **Neither is a regression**, and
neither is evidence about the nested-quote fix (no nested shape was present in
either answer). Both were checked against the retrieved evidence:

- `JOHN_6_29_S00` — the model's `"the gift of God, and the operation of his
  spirit"` is **not verbatim** in the retrieved chunk. Correct refusal.
- `MATTHEW_17_20_S00` — `"if ye have faith as a grain of mustard-seed...
  nothing shall be impossible unto you"` splices two spans across an ellipsis;
  the tail is not verbatim. Correct refusal.
- `JOHN_6_39_S00` — the quoted span is the KJV text of the verse, which the
  verifier is designed to refuse. Correct refusal.

The verification gate was working in all three. Recorded here because
`verified: false` on a fresh deploy is exactly the shape that gets mis-read as a
deploy fault.

## DRIFT — what the next `helm upgrade` must carry (dated 2026-10-18)

The chart is still `goat-yard-archive-0.2.1`, helm revision 26/20, last upgraded
2026-06-21. **Both changes above are imperative `kubectl` edits and live outside
the chart.** The next `helm upgrade` of this release reverts them *silently* —
it will not fail, it will just put a 76-day-old `:latest` back and drop the flag,
and the next eval run against gya-test would then abort naming `GYA_DEBUG_STAGES`
with no obvious connection to the upgrade that caused it.

| value | live now (imperative) | chart as committed |
|---|---|---|
| backend image | `backend@sha256:ac37c84fed...66d0c7d8e` | `backend:latest` (unpinned) |
| `GYA_DEBUG_STAGES` | `"1"` on the deployment | absent from the gya-test configmap |
| `GILL_STRUCTURED_ANSWER` | **not set** — see below | absent |

Chart upgrade is a **separate ticket, after the paired gate run**, per the
ruling. Its first two steps are `helm dependency build` and a `helm template`
dry-run — the chart as committed does not render (`missing in charts/ directory:
minio`), which is a defect in the chart, not in the renderer.

## `GILL_STRUCTURED_ANSWER=1` was NOT set, and why

The ruling's order was `GYA_DEBUG_STAGES=1` → smoke → *then*
`GILL_STRUCTURED_ANSWER=1`. The first two are done. **The third was not run**,
because the flag does not exist in the thing that is deployed. Three independent
witnesses:

1. `git merge-base --is-ancestor ac71b00 origin/main` → **not an ancestor**.
   `ac71b00` ("feat(bot): ADR-0009 typed GillAnswer via BAML, behind
   GILL_STRUCTURED_ANSWER") is carried only by `body-path`, `body-path-a2` and
   `body-path-a2-console`.
2. `git grep GILL_STRUCTURED_ANSWER origin/main` → **no match anywhere in the
   tree**.
3. `grep -rl GILL_STRUCTURED_ANSWER /app` inside the running pod → **no files**.

Setting it would have added an environment variable that no code in this image
reads, spent a third rollout, and — worse — put a flag in the DRIFT table above
that the deployed build cannot honour. A later reader would reasonably conclude
the structured-answer path had been exercised on gya-test. It has not been.

This is a scope correction, not a refusal: the flag ships with `ac71b00`, which
is not in 0.3.2. It becomes settable on gya-test only once that commit is on a
branch that gets built. **Chris's call** whether that is a 0.3.3 item or waits on
the gate run that was to decide the flip on the ratchet alone.

(The 0.3.2 release notes list `GILL_STRUCTURED_ANSWER` among the non-live
toggles. That mention is correct about `envFrom` semantics but reads as though
the flag ships in 0.3.2; it does not.)

## Correction to "A second finding" above

That section said `/health` "has always sat there and is fine, because its
consumer is the k8s probe". The first half is now measured and is **worse than
stated**: `curl http://test.chart-example.local/health` returns `200` with
`<!doctype html>` — the SPA. The ingress sends the **entire** `/health*` tree to
the UI, not just `/health/stages`. `/health` is fine only because the kubelet
probe addresses the pod directly and never traverses the ingress.

Per the ruling the path **stays in-cluster for 0.3.2** and the release notes say
so. `0.3.3` adds `/api/health/stages` additively, keeping the old path, alongside
the D-003 retry attempt counter.

## What this still does NOT solve

- **0.3.2 has now been exercised against a deployed backend, but not against a
  scored run.** Four requests is not an eval. The gate's pass-rate claim is
  still unmeasured on this pod.
- The nested-quote fix is verified on the **deployed code path**, not on a live
  answer that contained the shape. No generation in this smoke produced one.
- `GILL_STRUCTURED_ANSWER` is unexercised anywhere outside `body-path`.
- The digest was read from a build log, not from the registry. See the weakness
  named above.
- The frontend still tracks `:latest` and is still unpinned. It was deliberately
  not touched, so a restart of `gya-frontend-ui` for any unrelated reason will
  pull an unnamed image.
- The retry bound remains **declared, not observed** (D-003). `/health/stages`
  went green on `expansion` here; that says nothing about how many attempts it
  took.
