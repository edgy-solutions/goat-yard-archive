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

---

# Ancestry against the deployed head (2026-10-18, ruling 2)

Asked for before any prod action: is the deployed head `a88ad6f` — the commit the
pinned digest was built from — missing anything that 0.3.1 or 0.3.2 claims to
ship? One line each, `y` = contained in `a88ad6f`.

| commit | in `a88ad6f` | what it is |
|---|---|---|
| `fe8ea83` | **y** | release: 0.3.1 |
| `c9186b1` | **y** | 0.3.1 entity fix — Tier-2 entity manifest as a pure function |
| `5c93b28` | **n** | the *same change*, on `body-path` — see reconciliation below |
| `88d18b6` | **y** | release: 0.3.2 |
| `2e2fa41` | **y** | 0.3.2 code — citation-pairing regex (nested quote) |
| `7a5a69a` | **y** | 0.3.2 code — `GET /health/stages` |
| `0f3fe6d` | **y** | 0.3.2 code — debug captures gated off by default |
| `824b8d2` | **y** | 0.3.2 code — the debug gate's second consumer |
| `9763cf9` | **y** | 0.3.2 code — bounded transport retry on `LocalRouter` |
| `530696c` | **n** | docs + a **comment-only** BAML change — see "the one real gap" |
| `c46ad0b` | **n** | docs only (this audit's first 94 lines) |
| `a04efbf` | **n** | docs only (the smoke record) |
| `ac71b00` | **n** | `GILL_STRUCTURED_ANSWER` — **not** 0.3.2, carried only by `body-path` |
| `b532065` | **n** | the debug-gate port onto `body-path` (ruling 1) |

**Every 0.3.1 and 0.3.2 code commit is `y`.** The five `n` rows below the release
commits are four docs commits and one commit that belongs to a different release.

## Reconciliation: `5c93b28` vs `c9186b1`

The handoff says `5c93b28` is not on `main`. The smoke record says the 0.3.2 code
is. **Both are true and they are not in tension** — they are statements about two
different commit *objects* carrying one *change*:

```
5c93b28 patch-id: 1bfe15d6a671faacc00111698c188611ed2939fa
c9186b1 patch-id: 1bfe15d6a671faacc00111698c188611ed2939fa
```

Same patch-id, same two files, same line counts, and the resulting blobs are
identical object-for-object:

| file | `5c93b28` | `c9186b1` | |
|---|---|---|---|
| `backend/gill_search.py` | `37b87d2d` | `37b87d2d` | identical |
| `backend/test_entity_lookup_order.py` | `f3e715ce` | `f3e715ce` | identical |

`5c93b28` is the `body-path` instance and was never an ancestor of `main`;
`c9186b1` is the release-line instance and is. **The 0.3.1 entity fix is in the
deployed image.** The 0.3.2 release notes already warned about exactly this shape
— a deploy cut from a `main` checkout taken before 2026-10-11 regressed to 0.3.0
because it followed the commit id rather than the content. The lesson generalises:
*ancestry of a commit id is not the same question as presence of a change*, and on
a repo with parallel lane branches only the second one is worth asking.

## What `c46ad0b` contains, and what the image lacks because of it

`c46ad0b` is **one file, docs only** — the first 94 lines of this audit
(`docs/audits/SMOKE_BLOCKED_...md`). It contains no code, no chart values and no
BAML. **The deployed image is missing nothing because of it.** The same holds for
`a04efbf` (this audit's resolution section plus release-note prose).

## The one real gap, and it is not code

`530696c` is the only non-ancestor commit that touches a file the runtime loads:

```
 baml_client/inlinedbaml.py   |  2 +-
 baml_src/main.baml           | 11 ++--
 docs/defects/D-003-...md     | 68 +
 docs/releases/0.3.2.md       | 71 +
```

The `main.baml` change is a **correction to a comment** about D-003 — filtering
the diff to non-comment, non-blank lines returns **nothing**. `inlinedbaml.py`
moved only because `baml-cli generate` re-inlines that comment into the embedded
source string.

So the image's `inlinedbaml.py` is **not byte-identical** to `release-0.3.2` HEAD,
and the difference is entirely comment text inside the inlined BAML. The parser
discards comments, so there is no behavioural difference — but the honest
statement is "differs by a comment", not "identical", and anything that hashes
that file will see it move.

**Bottom line for ruling 3's condition:** `a88ad6f` contains the 0.3.1 entity fix
and all five 0.3.2 code commits. Nothing in 0.3.2 is withheld from the deployed
image.

## Weak link: NOT closed, needs a grant

Ruling 3 requires closing it before prod: a registry HEAD of the digest with a
`read:packages` token, or `docker manifest inspect`. **Attempted and failed:**

```
docker manifest inspect ghcr.io/edgy-solutions/goat-yard-archive/backend@sha256:ac37c84...
  -> unauthorized
```

Docker is present (29.8.0) but is not logged in to `ghcr.io`, and the `gh` token
still lacks `read:packages` (`ghcr.io` anonymous token → `DENIED`). **No
credential was harvested or improvised to get around this.** It needs one of:

- `gh auth refresh -s read:packages`, then `gh api .../versions`, or
- `docker login ghcr.io`, then `docker manifest inspect` as above.

**What is already established without it:** the kubelet pulled this exact digest
with the cluster's own pull secret, and the pod reports
`imageID: ...@sha256:ac37c84...`. A registry cannot serve content under a digest
unless the content hashes to it, so the image's *existence and content-address*
are confirmed by the pull. What the pull does **not** independently confirm is the
digest's provenance — that it is the artefact of run `38181578224` on head
`a88ad6f`. That still rests on GitHub's record of the run plus its build log, which
is a second source but not a registry one.

Which method actually closed it will be recorded here when it runs.

---

# 2026-10-18 (later) — ruling 4: the 0.3.3 candidate, and three findings about the chart

Ruling B4 asked for a 0.3.3 candidate = `release-0.3.2` + `ac71b00`, cherry-picked
**by path**, deployed to gya-test by digest, then the flag set. The cherry-pick is
done and committed. **Nothing has been built or deployed**, because building it
turns out to interact with ruling B3's prod plan in a way that is Chris's call.

## The candidate: `b72c0f8` on `release-0.3.3` (branch NOT pushed)

Worktree `C:\Users\cnogr\git\goatyard-rel033`, branched from `release-0.3.2`
(`b626576`). The diff against `release-0.3.2` is the same shape as `ac71b00`'s own
diff against *its* parent — 12 paths, 1188 insertions, 6 deletions, identical
per-file counts, and the path set compares equal.

**"By path" could not mean `git checkout ac71b00 -- <path>`.** `ac71b00` branches
from `cc6b1af`, which predates the 0.3.2 citation-pairing fix (`2e2fa41`): its
`backend/bot.py` still carries the *single*-closer regex. Taking its file wholesale
would have silently reverted the nested-quote repair smoked on gya-test the same
morning. A 3-way cherry-pick was used and the surviving regex asserted — the closer
is still a run.

**The four conflicts were all in generated `baml_client/`, and were not
hand-merged.** `ac71b00`'s side of the generated client declares `Note` and inlines
a `gill_apparatus.baml` — Lane A2's config-v2 apparatus seam, which is *not* in
`ac71b00`'s diff and whose `.baml` source does not exist in this tree. Resolving in
its favour would have shipped generated types for a source file that isn't here.
Per AGENTS.md rule 3 the client was regenerated from the merged `baml_src` with the
pinned `baml-cli 0.211.1`.

**The null was measured before the delta was read.** Regenerating from *pristine*
`release-0.3.2` sources reproduces that branch's committed client exactly — 0
differing lines across all 13 files ignoring CR — so nothing in this commit is
generator-version drift. Three files (`config.py`, `globals.py`, `tracing.py`) come
back CRLF-modified in the worktree only; git's own diffstat for them is empty and
they are excluded.

Predicted before regenerating, asserted after: 14 classes (0.3.2's 11 plus
`GillAnswer`, `GillRefusal`, `Zone2Phrase`), no `Note`, 6 inlined keys with no
`gill_apparatus.baml`, no conflict markers. Suites green: `baml_retry_policy` 6/6,
`debug_gate` 12/12, `entity_lookup_order` 10/10, `quote_cite_pairing` 14/14,
`stage_health` 31/31, `structured_answer` 24/24 — **97 checks**.

## Finding 1 — prod cannot reach the smoked digest by a tag change. **Blocks B3.**

Ruling B3: *"prod goes to this exact digest as 0.3.2 in one helm upgrade (tag change
only)"*. Three facts make that impossible as the chart stands:

1. **The chart cannot express a digest.**
   `charts/goat-yard-archive/templates/api-deployment.yaml:29` is
   `image: "{{ .Values.api.image.repository }}:{{ .Values.api.image.tag }}"` — the
   `:` is hard-coded. A digest needs `repository@sha256:…`. There is no digest
   value anywhere in the templates.
2. **The prod values already say `0.3.2`.**
   `charts/goat-yard-archive/values-frontend.yaml:27` is `tag: "0.3.2"`, set by the
   0.3.2 release commit `88d18b6`, which *is* contained in `a88ad6f`. So the "tag
   change" B3 describes has already been committed.
3. **No `0.3.2` image exists.** Every ref Build Containers has ever built:
   `0.2.1`, `0.2.2`, `0.3.0`, `main`, `vol1-apparatus-frozen-config`. The workflow
   tags `backend:${{ github.ref_name }}`, and there is no git tag `0.3.1` or
   `0.3.2` in the repo (tags present: 0.0.1, 0.1.0, 0.1.1, 0.2.0, 0.2.1, 0.3.0,
   vol1-apparatus-frozen-config).

With `pullPolicy: Always`, a `helm upgrade` of prod against the committed values
would therefore go to **ImagePullBackOff**, not to 0.3.2.

**This is older than 0.3.2.** `fe8ea83` set the same value to `"0.3.1"`, and
`backend:0.3.1` was never built either. So the committed prod values have named a
non-existent tag since the 0.3.1 release — which means the 0.3.1 deploy that is
first on Chris's list would have hit the same wall. Whether the *live* prod release
overrides the tag cannot be known from here and prod was not touched: the read-only
check is `helm -n <prod-ns> get values <release>`.

**Evidence bound:** the registry itself still could not be queried (the `read:packages`
weak link below is still open). "No 0.3.2 image" rests on the git tag list, the
workflow's tagging rule and the full run list — three consistent sources, none of
them the registry.

**Three routes, and a recommendation.**

- **(a) Re-point the tag at the already-built digest, without rebuilding.**
  `docker buildx imagetools create -t ghcr.io/edgy-solutions/goat-yard-archive/backend:0.3.2 ghcr.io/edgy-solutions/goat-yard-archive/backend@sha256:ac37c84fed…66d0c7d8e`
  (or `crane tag`). This creates a tag pointing at the *same manifest*, server-side:
  no rebuild, so prod gets **exactly the artefact that was smoked**, the committed
  values already match, and `:latest` does **not** move. Needs `packages:write`,
  which this lane does not have and did not improvise. **Recommended.**
- **(b) Push a git tag `0.3.2`.** CI builds and tags `backend:0.3.2`. But a rebuild
  of the same source yields a **different digest** — so prod would run an artefact
  that was never smoked, which is precisely what B3's "this exact digest" forbids.
  It also moves `:latest`.
- **(c) Teach the chart a digest value.** Correct long-term, but it is a chart
  change, and B1/B5 deferred the chart upgrade to its own ticket after the gate run.

## Finding 2 — correction to the DRIFT table accepted on 2026-10-18

The table above says `GYA_DEBUG_STAGES` is *"absent from the gya-test configmap"*
under the **"chart as committed"** column. **That row is wrong.**
`charts/goat-yard-archive/values-test.yaml:21` carries `GYA_DEBUG_STAGES: "1"`,
committed by `0f3fe6d` — a 0.3.2 code commit, present in both `release-0.3.2` and
`a88ad6f`.

The practical consequence **inverts**: a `helm upgrade` of gya-test would *restore*
the flag through the chart's configmap, not drop it. The live configmap lacks it
only because helm revision 26 dates from 2026-06-21, months before `0f3fe6d` — so
the gap is between the *deployed* release and the chart, not inside the chart.

**The image half of the drift stands unchanged**, and it is the half that bites: the
chart still says `backend:latest` for gya-test, so an upgrade still reverts the
digest pin. What is corrected is only the claim that the eval would then abort
naming `GYA_DEBUG_STAGES`; it would not.

`GILL_STRUCTURED_ANSWER`'s row is correct as written for the release line. The chart
change that would set it — `b6077f7`, *"GILL_STRUCTURED_ANSWER in the configmap, ON
for gya-test only"* — exists on **`body-path` only** and is not in `release-0.3.2`,
`release-0.3.3` or `a88ad6f`. B5's chart-upgrade ticket can cherry-pick it rather
than re-author it.

## Finding 3 — building the candidate moves `:latest`, and that now matters more

A push of `release-0.3.3` will **not** produce an image: Build Containers triggers
on `main`, tags `v*` / `*.*.*`, PRs to `main`, and `workflow_dispatch`. Producing a
digest for the candidate needs a tag, a dispatch, or a PR to `main`.

Whichever is used, the build also pushes `backend:latest`. Combined with finding 2,
that is sharper than it was this morning: gya-test's chart value is `latest`, so a
later `helm upgrade` of gya-test — the silent revert already recorded — would land
**`ac71b00` code** on gya-test rather than the 76-day-old image. Prod does not drift
from this (its values name a tag, not `latest`), but the constraint *"prod never
sees `ac71b00` until the ratchet holds"* is then being kept by the fact that prod's
tag is broken, which is not a safeguard anyone chose.

`workflow_dispatch` is the narrowest of the three — no git tag is created and no PR
is opened — but it moves `:latest` like the others.

## What this still does NOT solve

- **Nothing is built and nothing is deployed.** `GILL_STRUCTURED_ANSWER` is still
  unset everywhere and unexercised outside `body-path`. B4 is paused at exactly the
  point where it would have required a build.
- **The `read:packages` weak link is still open**, so finding 1 rests on git and CI
  evidence rather than on the registry.
- `release-0.3.3` is **unpushed**, by choice: pushing it is harmless on its own, but
  it is the step before a build, and the build is the decision above.
- `backend/test_structured_answer.py`'s runner counts its tests dynamically with no
  `EXPECTED_TESTS` assertion, so a test lost to a rename would pass unnoticed. Left
  as `ac71b00` wrote it — a cherry-pick by path is not the place to change it.
- Four requests is still not a scored run; the gate's pass rate on that pod remains
  unmeasured.

---

# 2026-10-18 (prod path) — rulings 1–7: re-point, rehearsal, and two things found on the way

## Ruling 7 — DRIFT correction applied

The `GYA_DEBUG_STAGES` row of the DRIFT table above is **withdrawn**: the flag *is*
in the chart as committed (`values-test.yaml:21`, `0f3fe6d`). The **image** half
stands — gya-test's chart value is still `backend:latest`, so a `helm upgrade`
still reverts the digest pin.

## Ruling 6 — `:latest` is never a deploy target again

Accepted that a 0.3.3 build moves `backend:latest` onto code containing `ac71b00`.
Both environments are pinned to something else (gya-test by digest, prod by tag),
and the rule from here is that **`:latest` is never a deploy target**. Stated in
the 0.3.2 release notes.

## Ruling 3 — ancestry of the entity fix in `a88ad6f`

**`5c93b28`: n.** Not an ancestor of `a88ad6f` as a commit object.

The change it carries **is** in the deployed image, and this is now stated in its
strongest form — not by patch-id alone, but by the deployed tree's own bytes:

| | `5c93b28` | `c9186b1` | `a88ad6f` (deployed) |
|---|---|---|---|
| ancestor of `a88ad6f` | **n** | **y** | — |
| patch-id | `1bfe15d6…2939fa` | `1bfe15d6…2939fa` | — |
| `backend/gill_search.py` blob | `37b87d2d` | `37b87d2d` | **`37b87d2d`** |
| `backend/test_entity_lookup_order.py` blob | `f3e715ce` | `f3e715ce` | **`f3e715ce`** |

The deployed tree's blobs for both files are byte-identical to the ones `5c93b28`
produces. The commit object is absent; **the content is not.** Flagged because the
ruling said *stop on no*, and the literal answer is no.

## Ruling 2 — re-pointing `:0.3.2` at the smoked digest

**Prerequisite.** Docker on this machine is **not logged in to ghcr.io**
(`credsStore: desktop`, `auths: []`), and the `gh` token still lacks
`read:packages`. The re-point needs a token with **`write:packages`**:

```
docker login ghcr.io -u <user>          # PAT with write:packages
```

**The command, as ruled:**

```
docker buildx imagetools create \
  -t ghcr.io/edgy-solutions/goat-yard-archive/backend:0.3.2 \
     ghcr.io/edgy-solutions/goat-yard-archive/backend@sha256:ac37c84fed147f96fb14c276a8fb51869d6b6d765257959e578bc6366d0c7d8e
```

No rebuild: this writes a tag that references manifests already in the registry.

**Expected resulting manifest digest — I cannot predict it, and the reason matters.**
`imagetools create` does not simply bind a name to an existing digest; it
*constructs* an image index referencing the source's manifests and pushes that.
If the source is already an index and buildx re-serialises it byte-identically, the
tag resolves to `sha256:ac37c84f…` unchanged. If buildx normalises ordering or adds
annotations — or if the source is a single manifest that now gets wrapped in an
index — **the tag resolves to a different digest that points at the same layers.**
Which of those happens depends on the source manifest's media type, and the
registry could not be queried from this lane (the `read:packages` weak link is
still open). Predicting a digest I cannot check would be a guess dressed as a
verification.

**If the digests being equal is the requirement, use `crane` instead:**

```
crane tag ghcr.io/edgy-solutions/goat-yard-archive/backend@sha256:ac37c84fed…66d0c7d8e 0.3.2
```

`crane tag` writes the tag against the **existing** manifest without re-creating it,
so `:0.3.2` resolves to `sha256:ac37c84f…` by construction. This is the stronger
form of what ruling 2 asks for.

**Verification, and the part that actually settles it.**

```
docker buildx imagetools inspect ghcr.io/edgy-solutions/goat-yard-archive/backend:0.3.2
```

Compare the reported digest to `sha256:ac37c84f…`. **A difference here is not
automatically a failure** — see above — so the decisive check is a content witness
rather than a name:

```
kubectl -n gya-test      get pod -l app.kubernetes.io/name=gya-frontend-api -o jsonpath='{.items[*].status.containerStatuses[*].imageID}'
kubectl -n gya-frontend  get pod -l app.kubernetes.io/name=gya-frontend-api -o jsonpath='{.items[*].status.containerStatuses[*].imageID}'
```

Run after the prod upgrade. **The two `imageID`s must be identical strings.**
`imageID` is what the kubelet actually resolved and pulled, so equality here means
prod is running the artefact that was smoked on gya-test — which is the claim the
acceptance is really about, and it holds whether or not the tag's own digest moved.

**Do not push a git tag `0.3.2`.** It would trigger Build Containers, which tags
`backend:${{ github.ref_name }}` — overwriting the re-pointed tag with a **rebuild**
of the same source, and a rebuild yields a different artefact than the one smoked.
Per the ruling, no git tag of that name at all.

## Ruling 4 — prod rehearsal, read-only. **The literal variant would break prod.**

**Prod identified:** release `gya-frontend`, namespace `gya-frontend`, revision 29,
chart `goat-yard-archive-0.3.0`, last upgraded 2026-08-02. It runs
`backend:0.3.0` and `frontend:0.3.0`; live values say `tag: 0.3.0`. So prod never
reached 0.3.1 or 0.3.2 — consistent with neither tag ever having been built.
(`gya-backend`/`gya-backend` ns, revision 15, is the corpus-side release and is not
touched by any of this.)

Both variants were rendered with `helm upgrade --dry-run` against the real release
from the chart at `a88ad6f` (deps resolved with `helm dependency build`; the chart
does not render without it). Both returned rc=0. Each rendered manifest was diffed
against `helm get manifest`.

### Variant A — `-f charts/goat-yard-archive/values-frontend.yaml` (the literal reading)

38 changed lines. The image line moves `0.3.0` → `0.3.2` as intended, and
`GYA_DEBUG_STAGES: "0"` is added — both wanted. **And then it removes seven
secret-bearing lines:**

- `OPENROUTER_API_KEY`, `OPENROUTER_API_KEY_ANON` — deleted from the configmap
- `LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY` — deleted
- `VITE_CLERK_PUBLISHABLE_KEY` — deleted
- the cloudflared tunnel argument `--token=<redacted>` → **`--token=`** (emptied)

The last one takes the public tunnel down; the first five leave the backend with no
provider credentials. **This variant would break prod, not upgrade it.**

The cause is not a bug in the chart: `values-frontend.yaml` as committed is **not a
complete prod values file.** Prod's live user-values carry an `api.env` block and a
tunnel token that the committed file does not contain, and `-f` replaces
user-supplied values wholesale rather than merging with what is deployed.

### Variant B — `--reuse-values --set api.image.tag=0.3.2` (recommended)

28 changed lines, of which exactly **two** are substantive:

```
-           image: "ghcr.io/edgy-solutions/goat-yard-archive/backend:0.3.0"
+           image: "ghcr.io/edgy-solutions/goat-yard-archive/backend:0.3.2"
-             secretName: gya-frontend-minio        (trailing whitespace)
+             secretName: gya-frontend-minio
```

Everything else is blank-line churn plus the `GYA_DEBUG_STAGES` comment block.
**Zero secret-bearing lines are removed** (variant A: seven). This is the
"tag change only" upgrade ruling 3 described:

```
helm upgrade -n gya-frontend gya-frontend <chart> --reuse-values --set api.image.tag=0.3.2
```

**One difference to know about, not a defect.** Under `--reuse-values` the
configmap renders the `GYA_DEBUG_STAGES` *comment* but **not the key** — the live
values have no such key for the template to emit. Prod therefore gets the debug
gate off **by absence** rather than by an explicit `"0"`. Functionally identical:
`debug_gate.stage_debug_allowed()` reads the variable and an unset variable is
disabled — which is exactly the state gya-test was in when the 403 half of the
smoke was recorded. If an explicit value is wanted, add
`--set api.env.GYA_DEBUG_STAGES="0"` to the same upgrade.

## Found on the way: a credential-handling finding, recorded elsewhere

Ruling 4's `helm get values` surfaced a credential-handling problem with the
production release. **It is deliberately not described in this repository**, which
is public: naming the weakness here would publish an attack path against a live
system. The finding, its scope and the options are written up in the private
handoff (`dr-voluminous`) and were reported to Chris directly. Rotation and any
change of storage are his call and nothing was acted on.

Two things from it do belong here, because they bear on the upgrade:

- **`values-frontend.yaml` as committed is not a complete production values file.**
  The live release carries user-supplied values the committed file does not, which
  is the mechanism behind variant A's damage above. Nothing should ever upgrade
  production with `-f` against this file.
- **Variant B touches none of it**, which is a further reason to prefer it.


## What this still does NOT solve

- **No prod action was taken.** The re-point, the upgrade and the acceptance are all
  Chris's, and the re-point is blocked on `write:packages`.
- The `read:packages` weak link is still open, so the resulting tag digest cannot be
  predicted from here — hence the `imageID` content witness above.
- The acceptance (entity manifest ×5 identical + the three smoke items **on prod**)
  has not been run; only the gya-test smoke has.
- Rehearsal fidelity: `--dry-run` renders against the live release, but it does not
  prove the pull succeeds. If `:0.3.2` is absent or unreadable when the real upgrade
  runs, the failure appears as ImagePullBackOff *after* a successful `helm upgrade`.
  The `imagetools inspect` above is what rules that out beforehand.
