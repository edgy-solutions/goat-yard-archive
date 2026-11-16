# RELEASE 0.3.3 — the production deploy

`docs/releases/0.3.3.md` is what the release **contains**. This file is what
happens when it is **deployed**, written for whoever runs the upgrade. Same
split as 0.3.2 (`798baa4`).

**The 0.3.2 deploy record is on this branch as of 2026-11-15.** It arrived
with the forward-merge of `release-0.3.2` (`05ecd79`), so
`docs/releases/RELEASE_0.3.2.md` is readable at its own path here. Until that
merge it was absent and this file named `798baa4` instead, which remains its
provenance on `release-0.3.2` and `main`.

Its §"The pre-upgrade rule from here on" is the authoritative definition of the
standing drift gate, and its §Acceptance is the output this release's acceptance
extends.

**Why the merge happened, because it is the reason this release did not deploy
on 2026-11-15.** `release-0.3.3` was branched before 0.3.2's two deploy fixes
and never took them: `529484f` (minio `requests.memory: 4Gi` and
`deploymentUpdate.type: Recreate`) and `a674cd2` (the minio post-install job
disabled with `buckets: []` and `users: []`). The step-1 gate caught it. See
§Prediction for what it printed and for what the old prediction got wrong.

---

## What is being shipped

| | |
|---|---|
| chart tip | `release-0.3.3`, chart subtree `ac4c3282` (chart `version: 0.3.0`, unchanged) |
| api image | `ghcr.io/edgy-solutions/goat-yard-archive/backend@sha256:2fce1e34…b11433` |
| ui image | `ghcr.io/edgy-solutions/goat-yard-archive/frontend@sha256:f386254e…96da4` |
| flag | `GILL_STRUCTURED_ANSWER: "1"` (ConfigMap key, from `api.env`) |

Both images are **the pairing gya-test was serving when the paired gate run
scored it** — the flip evidence is a gate run against that exact pair, not
against either image separately. Both are pinned by `digest`, which wins over
`tag` in the `goat-yard-archive.image` helper (`71981b5`), so the inert tags left
beside them cannot defeat the pin.

**0.3.3 is the first release of this chart pinned by digest at all.** 0.3.2 and
everything before it shipped `tag:` only. That matters below.

Flip evidence:
`docs/audits/GATE_RUN_RESULTS_structured_answer_laneA_20261026.md`, accepted as
written at `e792e7d` **including its "not a win" decomposition** — the PASS is by
the pre-registered ratchet (zero STABLE-PASS → STABLE-FAIL, zero
`must_not_cite`), and the effect clause abstained. Decision to ship: Chris,
2026-11-01, ruling 2.

---

## The commands, in order

Run them in this order. Steps 1 and 2 differ in **exactly one word** (`template`
vs `upgrade`) and in nothing else — if their `-f` sets ever diverge, the gate
checked something other than the upgrade.

### 0 — build the chart copy, from the committed tip

```sh
rm -rf  ~/.gya/chart-0.3.3
mkdir -p ~/.gya/chart-0.3.3
git -C ~/git/goatyard-rel033 rev-parse release-0.3.3:charts/goat-yard-archive
# must print ac4c3282acc7e60c11325b75a49c93205677467d
git -C ~/git/goatyard-rel033 archive release-0.3.3:charts/goat-yard-archive \
  | tar -x -C ~/.gya/chart-0.3.3
helm dependency update ~/.gya/chart-0.3.3
```

**The sha named is the chart SUBTREE, not a commit.** The chart was last
touched by the `release-0.3.2` forward-merge (`05ecd79`), which moved the subtree
from `c56791ea` to `ac4c3282` by restoring the three minio values; the branch
tip moves past it again with every later commit -- this deploy record is
itself a commit -- so naming a commit would make this file stale the moment it
was written. `c56791ea` is what `git archive` actually extracts, and it is stable
under every later commit that does not touch `charts/`. If `rev-parse` prints
anything else, the chart changed after this record was written and the record is
no longer describing the deploy.

`git archive` rather than `cp -r`, deliberately: the copy is then **exactly the
committed chart tree** with no local file in it. The worktree's
`Chart.lock` and `charts/minio-5.3.0.tgz` are untracked (the committed chart has
neither), so a `cp -r` would silently mix committed templates with local
artefacts and the copy would not be attributable to a sha.

`dependency update`, not `build`: with no committed `Chart.lock` there is no lock
to build from. It resolves `minio 5.3.0` — an **exact** version in `Chart.yaml`,
not a range — so this is deterministic over the network rather than a
re-resolution. Last week's lock digest was
`sha256:198ab6469d49282c0bc624fcda64b7935795545d7d246f2f6c78ee92ce66375d`;
**if the new `Chart.lock` shows a different digest, stop** — the upstream tgz
moved under a fixed version number, and that is a change to what you are
deploying that nothing in this repo asked for.

Then confirm the copy is the commit it claims to be:

```sh
git -C ~/git/goatyard-rel033 show \
  release-0.3.3:charts/goat-yard-archive/values-frontend.yaml \
  | diff - ~/.gya/chart-0.3.3/values-frontend.yaml
```

Empty output is the pass. **`git diff --no-index` with a `<( … )` argument does
not run in Git Bash on Windows** (Chris, measured 2026-11-15) -- hence the pipe
into plain `diff`, which reads the committed side on stdin and needs no process
substitution at all. This check exists because last week's
`~/.gya/chart-0.3.2/values-frontend.yaml` was edited in place after the copy was
made (mtime 19:34 against the copy's 14:11) — it happened to end up byte-identical
to the committed `release-0.3.2` file, which is luck, not a procedure. **Nothing
in `~/.gya/chart-0.3.3` gets edited by hand.** The three values this release
changes are already committed at the tip.

### 1 — the standing drift gate, rendered against LIVE

Capture both sides, then compare. **Operator-only**: both commands put secret
values on disk, and `drift_hash.py` is the thing that reads them so that nothing
else has to.

```sh
cd ~/.gya

helm template gya-frontend ~/.gya/chart-0.3.3 -n gya-frontend \
  -f ~/.gya/chart-0.3.3/values-frontend.yaml \
  -f ~/.gya/secrets-prod.yaml \
  > rendered.yaml

kubectl --context edge -n gya-frontend get \
  secret/gya-frontend-secrets \
  secret/gya-frontend-minio \
  configmap/gya-frontend-config \
  deploy/gya-frontend-api \
  deploy/gya-frontend-cloudflared \
  deploy/gya-frontend-minio \
  deploy/gya-frontend-ui \
  -o yaml > live_objects.yaml

/c/Users/cnogr/AppData/Local/Programs/Python/Python311/python.exe ~/.gya/drift_hash.py rendered.yaml live_objects.yaml
```

**`deploy/gya-frontend-ui` is in that capture on purpose, and it is new.**
`drift_hash.py`'s `EXPECTED` list names five objects and the ui deployment is not
one of them, so the gate compares it only if the capture contains it. Without
that line the *second* image line this release changes is invisible to the gate —
the probe would miss, and report no drift on a key it never looked at. Capturing
more than `EXPECTED` is safe: the completeness check only asserts that the
`EXPECTED` five are present on both sides.

**`--context edge` is not optional and is not the default.** Without the
right context selected the `get` either fails or, worse, answers from another
cluster and the gate compares prod's render against something else entirely. It
is written into the command rather than left to the shell's current context
(Chris, 2026-11-15).

Rendered-against-**LIVE**, never against `helm get manifest`. That rehearsal is
withdrawn as a gate: both of its sides derive from helm's *stored* values, so it
is structurally blind to out-of-band cluster change — which is exactly what the
2026-10-18 rotation was.

### 2 — the upgrade

```sh
helm upgrade gya-frontend ~/.gya/chart-0.3.3 -n gya-frontend \
  -f ~/.gya/chart-0.3.3/values-frontend.yaml \
  -f ~/.gya/secrets-prod.yaml \
  --kube-context edge \
  --wait --timeout 10m
```

Both overlays passed explicitly, so there is nothing for the upgrade to revert.
**Never add `--reuse-values` to this release's upgrade.**

**`--kube-context edge` is not optional here either.** `helm upgrade` takes the ambient
context exactly as `kubectl` does, and it is the one command in this runbook that
*changes* a cluster. A capture run against the wrong context produces a wrong gate
verdict; an upgrade run against the wrong context installs this release somewhere
it was never meant to go. `helm template` above is left without a context flag on
purpose: it has no `--validate`, so it contacts no cluster, and a flag there would
assert a connection that is not made.

### 3 — acceptance

```sh
/c/Users/cnogr/AppData/Local/Programs/Python/Python311/python.exe ~/git/goatyard-rel033/evals/accept_0_3_3.py
```

Run it after the revision records `deployed`. Exit `0` means every item passed
**and** nothing was unobservable; `1` is a failure; `2` means no failure but the
acceptance is incomplete, which is not an acceptance. It serves **five real
`/api/search` requests** — five LM calls, and five slots of the anonymous rate
limit (`RATE_LIMIT`, default `10/day`, `backend/main.py:398`), all from one
in-pod source address. `--draws N` lowers that if the budget is tight; a lower
draw count weakens the witness and should be recorded if used.

The six items, in the order the script runs them:

1. **api `imageID`** against `sha256:2fce1e34…`
2. **ui `imageID`** against `sha256:f386254e…` — this is the **in-cluster** ui
   pod, which no public request reaches (§Which UI the public reaches). The
   public page's build identifier is a separate item, in
   `RELEASE_PROCESS.md` § Step 5.
3. **the flag landed in the running container.** Reads
   `printenv GILL_STRUCTURED_ANSWER` *inside* the api container — not the
   ConfigMap, not the pod spec. See D-007 for why those two answer a different
   question, and why the gate run's own jsonpath probe returns empty here.
4. **debug captures refuse by default** (403 naming `GYA_DEBUG_STAGES`)
5. **the ×5 cited-SID witness** — serves the five requests
6. **`/health/stages`**, read **last**

The order of 5 and 6 is not cosmetic. D-004: a cold process reports every stage
`false` with no fault behind it, and clears only once a request has been served.
Reading `/health/stages` before item 5 reads the warm-up. This bit on prod last
week — the first 0.3.2 acceptance run read all-false on a cold pod.

---

## Prediction — restated 2026-11-15, after the first gate run

### What the first run printed, and why it stopped

The step-1 gate ran on 2026-11-15 against `release-0.3.3` **before** the
forward-merge, and Chris stopped the release at step 1. Names only, as reported:

```
37 same, every secret same
DIFFERENT  image[api]                0.3.2  -> 2fce1e34   (intended)
DIFFERENT  image[ui]                 0.3.0  -> f386254e   (intended)
DIFFERENT  minio requests.memory     live 4Gi -> rendered 16Gi   (NOT intended)
           GILL_STRUCTURED_ANSWER    only in RENDERED
           env[MINIO_HTTP_ENDPOINT]  only in LIVE
rendered objects 19   (0.3.2 final rendered 18)
```

**The cause is confirmed, by render rather than by reading.** `release-0.3.3`
lacked `529484f` and `a674cd2`. Rendering the pre-merge
`values-frontend.yaml` reproduces all of it: `requests.memory: 16Gi`,
`strategy.type: RollingUpdate`, 19 objects, and the 19th is
`Job/gya-frontend-minio-post-job`. Rendering the merged file gives `4Gi`,
`Recreate`, 18 objects, no Job.

**Three ways the old prediction was wrong.** Stated as the prediction being
wrong, not as the run being surprising:

1. It said *"Nothing else prints `DIFFERENT`. Any fourth line is either
   pre-existing out-of-band drift on prod or something this edit did not
   intend."* The fourth line was **neither**. It was a fix that existed, was
   deployed to prod, and was missing from this branch -- a third category the
   disjunction did not name. The live 4Gi was not drift; it was the correct
   value, and the render was the thing that was wrong.
2. It predicted the flag as `live='0' -> rendered='1'`, a changed value, and
   explicitly retracted an earlier prediction that the render would *gain* the
   key. The retracted prediction was the right one: the flag came in as **only
   in RENDERED**, because prod runs the 0.3.2 chart, whose `values.yaml` has no
   such key (it arrives with `a81b98b`). This file's own Prediction B named that
   fork correctly and then picked the wrong branch of it. A correction is a
   claim too, and this one was held to a lower bar than the thing it corrected.
3. It said this edit changes the `only-rendered` and `only-live` counts *"by
   exactly zero"*, on the basis that the render diff was three changed values
   and no added key. That basis was file-scoped and could not see that the LIVE
   side lacks the key entirely, so `only-rendered` moved by +1.

**What was right:** both image lines, in direction and in value; every secret
`same`; and the `only in LIVE` env key being unpredictable from the chart.

### The restated prediction for the re-run, post-merge

Chart subtree `ac4c3282`. Each line falsifiable:

```
SAME            38        (37 + minio requests.memory, which moves out of DIFFERENT)
DIFFERENT        2        image[api] and image[ui], nothing else
only-rendered    1        GILL_STRUCTURED_ANSWER, same as the first run
only-live        1        env[MINIO_HTTP_ENDPOINT], same as the first run
rendered objects 18       the hook job is gone
exit             1
```

- **`minio resources[…requests.memory]` reads `same = 4Gi`.** It prints its
  literal value: `plain()` covers keys starting `resources[`. This is the line
  the merge was for, and `same` is the whole point -- the live value was right
  all along.
- **`strategy` does not appear at all, and that is the hole this release leaves
  open.** `Recreate` is restored in the chart, but `strategy` is not among
  `drift_hash.py`'s compared keys, so the gate neither confirms nor denies it.
  The regression that would have hung the upgrade was invisible to the gate on
  the first run and is invisible to it now. It is covered instead by
  `charts/test_image_helper.py::test_values_frontend_minio_strategy_is_recreate`,
  which fails on the pre-merge file for exactly that reason. This residual was
  already written in §"What this deploy does NOT solve" before the first gate
  run -- naming it there did not stop the branch shipping without the fix, which
  is why it is now a test and not a note.
- **Exit is still `1`, and that is still the gate working.** `reverts` is built
  from `DIFFERENT` lines only, and the intended set is hardcoded as
  `r.endswith("image[api]") or "GYA_DEBUG_STAGES" in r`. So `image[ui]` scores as
  one UNINTENDED REVERT and `GILL_STRUCTURED_ANSWER`, being `only-rendered`,
  scores as none. The old prediction said two unintended reverts; one of those
  two was the flag, which cannot be a revert because it is not a `DIFFERENT`
  line. **Do not whitelist `image[ui]`.** The adjudication is the printed
  direction: `tag -> digest` is a pin, not a revert.
- **Any `DIFFERENT` line beyond those two, any secret difference, or any object
  count other than 18 is a STOP**, and this time the disjunction is named in
  full: it is out-of-band change on prod, something this edit did not intend, or
  a fix on `main` or `release-0.3.2` that this branch still does not carry. The
  third is the one that was missed, so it is checked first --
  `git log --oneline release-0.3.3..release-0.3.2` and the same against `main`
  must both be empty before the gate is read.

### `secrets same`, with the unknown named

Predicted: every key of `Secret/gya-frontend-secrets` and
`Secret/gya-frontend-minio` reads `same`. This edit touches no `secretRef` and no
secret key. It is a prediction about a key set and values **I have never seen
and will not see** — `helm get values`, `helm get manifest` and secret reads are
operator-only under the standing law of 2026-10-18, and this lane works from key
names only. If the gate reports a secrets difference, treat it as new
information about prod, not as a fault in this edit.

One known exception in advance: `minio.rootPassword` renders from
`values-frontend.yaml`'s committed literal, so if prod's live value was set
out-of-band it shows as a difference. That is pre-existing drift this edit
neither causes nor fixes.

### "The familiar only in LIVE" — I cannot name the set, and that is the honest answer

Chris's prediction includes the familiar `only in LIVE` keys. **That set is not
recorded anywhere I can read.** `RELEASE_0.3.2.md` records the two pre-deploy
runs as *"22 keys SAME, zero unintended reverts, exit 0"* and does not list
only-live keys; no file in `docs/` contains the string. Chris has last week's
output; this lane does not, and inventing a plausible list would be worse than
saying so.

What I can predict, and it is the part that matters:

> **CORRECTED 2026-11-15, this claim was wrong.** As written it predicted that
> this edit changes the `only-rendered` and `only-live` counts by exactly zero,
> on the basis that the render diff is three *changed values* and no added or
> removed key (`PROD_FLIP_PREDICTION…20261101.md` § MEASURED: six lines, three
> hunks). `only-rendered` came in at +1: `GILL_STRUCTURED_ANSWER` is absent from
> the LIVE side because prod runs the 0.3.2 chart. The basis was a read of this
> repo's own files, and no read of this repo can tell you which keys the live
> object carries. The measured counts for the re-run are in §Prediction.

That last clause is a real caveat about this run specifically: the ui deployment
was **never compared before**, so whatever `only in LIVE` keys it carries will
appear as new to this gate run and are not new to the cluster. Expect its
`env[...]` entries to be the ones that show up — the ui container is rendered
with `envFrom` and no explicit `env`, so any explicit env on the live object was
put there out of band.

A set that could be predicted from the chart would not be what this gate is for.
The gate's whole purpose is the content the chart cannot account for.

---

## What this deploy does NOT solve

- **It is not a measured quality win.** The gate passed the ratchet; the effect
  clause abstained. `real_benjamin_type_001` (STABLE-PASS 9/9 OFF → FLAKY 2/3 ON)
  is the one id to watch at higher n (ruling 6) — named, not acted on, and one
  draw is not a finding.
- **D-004, D-005, D-006 and D-007 all ride along unfixed.** All four are 0.3.4.
  D-006 (a provider error string returned as the answer, at HTTP 200) is
  pre-existing on prod and so not a 0.3.3 regression; it does not block.
- **D-007 means the flip lands as a side effect.** The flag takes effect because
  the *image* line changed in the same upgrade and rolled the Deployment, not
  because the upgrade delivers config. Acceptance item 3 exists so that this is
  witnessed rather than assumed.
- **The flag is not a live toggle and has no canary split.** All-or-nothing per
  namespace, read at container start.
- **The ui digest's build provenance is unverified by this lane.** It is recorded
  as the digest gya-test *is running*; it was never smoked as a release artefact,
  and ruling 2's "CI-built images only" is satisfied for the backend
  (CI run `39168013081`) and **unestablished** for the frontend. Pinning it is
  still strictly better than the floating `tag: "0.3.0"` it replaces, because a
  pin records what runs.
- **The drift gate still does not watch deployment-level fields** (`strategy` is
  the live example), and `crossref_env.py` still answers "does any captured
  source carry this key with this value", not "does *this container's* source
  carry it". Partly covered since 2026-11-15: five render-scoped checks in
  `charts/test_image_helper.py` assert the minio memory request, the `Recreate`
  strategy, the absence of the post-install job and the full rendered object set,
  each paired with a mutation control that puts the subchart default back and
  requires the check to fire. They run at commit time on any branch, where the
  gate runs once per deploy against one cluster. **They do not replace the
  gate**: they can only see what the chart renders, never what prod carries.
- **Nothing checks that a release branch carries `main`'s deploy fixes.** The
  2026-11-15 stop was a branch three weeks behind on exactly the two commits
  that made the 0.3.2 upgrade survivable. The new chart tests catch the three
  symptoms; they do not catch the general case of a release branch missing a
  fix that nothing renders. The `git log release-0.3.3..main` check in
  §Prediction is a manual step, not a gate. It is now step 0 of
  `docs/releases/RELEASE_PROCESS.md`, which is still a checklist and still
  not a gate; a CI check on `release-*` branches is 0.3.4 scope
  (`docs/releases/0.3.4.md`).
- **The gate-run launcher's pod filter fix (ruling 4) is not exercised by this
  deploy.** It lands before the *next* gate run and nothing in this path depends
  on it.

---

## Which UI the public reaches — and what the in-cluster ui pod is for

Recorded here because the 0.3.3 deploy was accepted against the wrong UI for
about an hour: the pinned ui digest rolled in the cluster, and the page Chris
checked in a private window was **not served by that pod**.

| | serves | deployed by | at |
|---|---|---|---|
| **what the public reaches** | `goatyardarchive.org` — the whole page, from `frontend/dist` baked into a Cloudflare Workers bundle | `wrangler deploy`, by hand, from a laptop | last deployed ~2026-08 (Cloudflare version `cb7ca83c`) |
| **the in-cluster `gya-frontend-ui` pod** | the same SPA, behind the cluster Ingress for host `goatyardarchive.org` path `/` | this chart, by digest | revision 33 |

The Worker (root `wrangler.jsonc`, `main: worker.js`) answers `/` out of its own
`ASSETS` binding and forwards **only** `/api/*` and `/scans/*` to
`TUNNEL_HOST = origin.goatyardarchive.org`. So of the three Ingress paths in
`values-frontend.yaml`, two are reached through the tunnel (api, minio) and the
third is not: **no public request reaches the `gya-frontend-ui` pod.** It is not
dead — it is the origin-side copy, reachable directly at the Ingress host and
the thing that would serve the page if the Worker were removed — but it is not
what a user sees, and pinning its digest proved nothing about the live page.

The frontend is **byte-identical between tag `0.3.0` and `release-0.3.3`** (`git
diff --stat 0.3.0 release-0.3.3 -- frontend/` is empty; zero commits touch
`frontend/` in that span). That is why the structured answer rendered correctly
on a three-month-old bundle: nothing client-side was needed for it. It is not
evidence that the deploy reached the page.

The public deploy is its own step. It is written up in
`RELEASE_PROCESS.md` § Step 5, because it is not a 0.3.3-specific command.

---

# MEASURED

Everything in this section is dated and attributed. The gate rows that are not
here are **not here** — they are not reconstructed from §Prediction, because a
prediction written into a MEASURED block is prose wearing a number's clothes.

## The deploy

| | |
|---|---|
| helm revision | **32 → 33** |
| deployed | 2026-11-15 20:15 CST |
| api image | `ghcr.io/edgy-solutions/goat-yard-archive/backend@sha256:2fce1e3467d5f53e4f0700cdd51530db86cc85c8ef7231f091c6e69509b11433` |
| ui image | `ghcr.io/edgy-solutions/goat-yard-archive/frontend@sha256:f386254ee465b77ceee57b3f11ad8f1742e8f6d671e1fa71452aa819c1996da4` |
| public page | renders the structured answer correctly (Chris, private window, 2026-11-15) |

Both digests are the artefacts the gate run scored. Nothing was rebuilt.

## The public page's build identifier — measured

| | |
|---|---|
| served entry script | `assets/index-fx2QcAsD.js` (HTTP 200, 654,395 bytes) |
| read | 2026-11-15, `curl https://goatyardarchive.org/` |
| Cloudflare version | `cb7ca83c`, deployed ~2026-08 (operator-reported) |

The Worker bundle is three months old, and **it does not matter for this
release**, which is a measurement and not a date inference. The live bundle
builds scan URLs as:

```
/scans/vol${fe}_page${Se}_image${fe}.png
```

That is the **post-`e0bf95e`** form — the 2026-08-02 fix that replaced a
hardcoded `_image1`. `_image1.png` occurs **zero** times in the served bundle.
Since `e0bf95e` is the **last** commit to touch `frontend/` and `frontend/` is
byte-identical from tag `0.3.0` to `release-0.3.3`, the public bundle already
contains every frontend change this release has. The stale deploy carries no
exposure, nothing in it is needed for the structured answer, and a redeploy is
hygiene rather than a fix.

What this probe does **not** establish: that the bundle is byte-equal to one
built from the release tree. One grep answered one question — whether the
user-visible scan-URL defect is live — and the local half of the § Step 5
comparison was not built, so the hash pair is recorded on one side only.

## The drift gate — NOT RECORDED HERE YET

The second gate run's verdict block has not reached this lane. What is recorded
is the first run's, in §Prediction, **as a prediction**. The rows this section
needs, by key name:

- `SAME` / `DIFFERENT` / `only-rendered` / `only-live` counts, as printed;
- the `DIFFERENT` keys by name (predicted: exactly `image[api]` and `image[ui]`);
- the `only-rendered` keys by name (predicted: `GILL_STRUCTURED_ANSWER`);
- the `only-live` keys by name (predicted: `env[MINIO_HTTP_ENDPOINT]`);
- the rendered object count (predicted 18) and the gate's exit code
  (predicted 1, on the two intended reverts).

A paste of the block fills this in. Until then this release has a deploy record
and no gate record, and the difference between the two is the whole reason the
gate exists.

## Acceptance

`accept_0_3_3.py`, run by the operator against prod, 2026-11-15:

| item | result |
|---|---|
| 1. api `imageID` | **PASS** |
| 2. ui `imageID` | **PASS** |
| 3. flag landed in the running container | **PASS** |
| 4. debug 403 by default | **PASS** |
| 5. cited-SID witness x5 | **NOT OBSERVED** — the script crashed here |
| 6. `/health/stages` | **NOT OBSERVED** — never reached |

Items 5 and 6 have **no verdict**, and a crash is not a partial pass: four of
six items were observed and the acceptance is incomplete. The cause was in the
script, not the cluster — `subprocess` output was decoded with the Windows
platform codec (cp1252) and died on byte `0x9d`, the third byte of a curly quote
in Gill's text. Fixed in `bc0ba3b`; items 5 and 6 need a rerun, and the rows
above are to be replaced by a complete run, not appended to.

What the four observed items establish, stated narrowly: the kubelet resolved
both signed digests, the running api container's **own environment** carries
`GILL_STRUCTURED_ANSWER=1` (not the ConfigMap's claim about it), and the debug
capture channel refuses by default. What they do not establish is that the
cited-answer path works on prod's corpus — that is item 5, and it is unobserved.

## The named regression

`corpus_ingestion_sha` on `/search` Langfuse traces. The 0.3.3 api image is
built from `a81b98b`, which does not contain the four backend files that landed
on `main` in `bf15b9d` / `a7bb044` / `aa46490`; the attribute is one of them
(`backend/main.py`, 4 lines). Ruling 15 has the file-by-file decomposition.

**Chris reports `INGESTION_SHA` is unset in prod** (2026-11-15). On that basis
the attribute prod loses carries the literal `"unstamped"`
(`os.getenv("INGESTION_SHA", "unstamped")`) and the regression is a missing
field with no content, not a lost corpus version. The basis is his read of
`~/.gya/secrets-prod.yaml`, which is operator-only; this lane did not read it
and cannot confirm it. My own earlier inference of the same conclusion **from
the gate's `only-live` env keys does not hold** and is withdrawn: the api takes
its environment via `envFrom: secretRef`, so a key in that file need not appear
as an env line at all.

gya-test has been without the attribute since 2026-10-18 — 28 days, through the
0.3.3 soak week, which was reported as liveness with the attribute missing and
nothing noticing.

## What the prediction got wrong

Stated as the prediction being wrong, not the run being surprising.

- **"Both `git log` ranges are empty" was wrong for `main`.** The STOP clause
  above requires `release-0.3.3..main` and `release-0.3.3..release-0.3.2` both
  empty. Only the second was run. The first is 86 commits, 4 of them merges.
  The branch shipped behind `main` by four backend files, which is the named
  regression above. A checklist authored in the same session as the branch
  (`RELEASE_PROCESS.md` § Step 0) and not applied to it.
- **The acceptance script was never run on this host before prod.** Its
  `text=True` defect is a Windows-only, content-dependent crash: it needs a
  response body carrying a non-cp1252 byte, which is every real Gill answer and
  no test fixture. Item 5 was the first time the script saw one.
