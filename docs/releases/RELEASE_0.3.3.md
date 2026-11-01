# RELEASE 0.3.3 — the production deploy

`docs/releases/0.3.3.md` is what the release **contains**. This file is what
happens when it is **deployed**, written for whoever runs the upgrade. Same
split as 0.3.2 (`798baa4`).

**The 0.3.2 deploy record is not on this branch.** `798baa4` is on
`release-0.3.2` and `main`, never merged into `release-0.3.3`, so
`docs/releases/RELEASE_0.3.2.md` is absent here and cannot be found by looking.
Read it with:

```
git show 798baa4:docs/releases/RELEASE_0.3.2.md
```

Its §"The pre-upgrade rule from here on" is the authoritative definition of the
standing drift gate, and its §Acceptance is the output this release's acceptance
extends. Naming the sha rather than the path because the path does not exist
from here.

---

## What is being shipped

| | |
|---|---|
| chart tip | `f70ccf9` on `release-0.3.3` (chart `version: 0.3.0`, unchanged) |
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
git -C ~/git/goatyard-rel033 archive f70ccf9:charts/goat-yard-archive \
  | tar -x -C ~/.gya/chart-0.3.3
helm dependency update ~/.gya/chart-0.3.3
```

`git archive` rather than `cp -r`, deliberately: the copy is then **exactly the
committed tree at `f70ccf9`** with no local file in it. The worktree's
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
git -C ~/git/goatyard-rel033 diff --no-index --stat \
  <(git -C ~/git/goatyard-rel033 show f70ccf9:charts/goat-yard-archive/values-frontend.yaml) \
  ~/.gya/chart-0.3.3/values-frontend.yaml
```

Empty output is the pass. This check exists because last week's
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

kubectl -n gya-frontend get \
  secret/gya-frontend-secrets \
  secret/gya-frontend-minio \
  configmap/gya-frontend-config \
  deploy/gya-frontend-api \
  deploy/gya-frontend-cloudflared \
  deploy/gya-frontend-minio \
  deploy/gya-frontend-ui \
  -o yaml > live_objects.yaml

python ~/.gya/drift_hash.py rendered.yaml live_objects.yaml
```

**`deploy/gya-frontend-ui` is in that capture on purpose, and it is new.**
`drift_hash.py`'s `EXPECTED` list names five objects and the ui deployment is not
one of them, so the gate compares it only if the capture contains it. Without
that line the *second* image line this release changes is invisible to the gate —
the probe would miss, and report no drift on a key it never looked at. Capturing
more than `EXPECTED` is safe: the completeness check only asserts that the
`EXPECTED` five are present on both sides.

Rendered-against-**LIVE**, never against `helm get manifest`. That rehearsal is
withdrawn as a gate: both of its sides derive from helm's *stored* values, so it
is structurally blind to out-of-band cluster change — which is exactly what the
2026-10-18 rotation was.

### 2 — the upgrade

```sh
helm upgrade gya-frontend ~/.gya/chart-0.3.3 -n gya-frontend \
  -f ~/.gya/chart-0.3.3/values-frontend.yaml \
  -f ~/.gya/secrets-prod.yaml \
  --wait --timeout 10m
```

Both overlays passed explicitly, so there is nothing for the upgrade to revert.
**Never add `--reuse-values` to this release's upgrade.**

### 3 — acceptance

```sh
python ~/git/goatyard-rel033/evals/accept_0_3_3.py
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
2. **ui `imageID`** against `sha256:f386254e…`
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

## Prediction — written before the run

### The drift gate will exit **1**, and that is the gate working

`drift_hash.py` hardcodes its intended-change set as
`r.endswith("image[api]") or "GYA_DEBUG_STAGES" in r` — 0.3.2's two intended
changes. 0.3.3's three do not match that pair, so **two of them classify as
UNINTENDED REVERTS and the script returns 1.** Predicted verdict block:

```
intended changes (the 0.3.2 upgrade): 1
  Deployment/gya-frontend-api image[api]
UNINTENDED REVERTS -- live value helm would overwrite: 2
  Deployment/gya-frontend-ui image[ui]
  ConfigMap/gya-frontend-config GILL_STRUCTURED_ANSWER
```

**Do not read exit 1 as STOP here, and do not whitelist the two lines.** The
0.3.2 record settled this: the intended set is deliberately not parameterised,
because a gate that learns each release's exceptions stops being a gate. The
adjudication is the printed **direction**, not the exit code. All three keys are
`plain()` — `image[` prefix, and `GILL_STRUCTURED_ANSWER` is in `SAFE_PRINT` — so
all three print their literal values:

```
Deployment/gya-frontend-api
  image[api]               DIFFERENT  live='…/backend:0.3.2' -> rendered='…/backend@sha256:2fce1e34…'
Deployment/gya-frontend-ui
  image[ui]                DIFFERENT  live='…/frontend:0.3.0' -> rendered='…/frontend@sha256:f386254e…'
ConfigMap/gya-frontend-config
  GILL_STRUCTURED_ANSWER   DIFFERENT  live='0' -> rendered='1'
```

Three predictions inside that, each falsifiable:

- **The two live image strings are `tag`s, not digests.** `release-0.3.2`'s
  `values-frontend.yaml` has no `digest:` key for api or ui (lines 25-27, 197-199):
  it shipped `backend:0.3.2` and `frontend:0.3.0`. So the direction here is
  tag → digest, which is a *pin*, not a version bump for the ui.
- **The flag line reads `live='0' -> rendered='1'`, a changed value, not an
  addition.** `values.yaml:101` carries the key at `"0"` as the chart default and
  is always merged under the overlay. **If it prints as "only in RENDERED
  (upgrade would ADD it)", prod is running a chart older than `a81b98b`** — which
  is Prediction B's condition firing, and worth knowing before the upgrade. This
  is a correction of my own earlier prediction: I predicted the render would
  *gain* the key, from a file-scoped read of two values files, and a file-scoped
  assertion cannot see a two-file merge — only the render can. Chris's wording
  ("flag line DIFFERENT") was right and mine was not.
- **Nothing else prints `DIFFERENT`.** Any fourth line is either pre-existing
  out-of-band drift on prod or something this edit did not intend, and either way
  it is new information to read before upgrading, not noise to step over.

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

> **This edit changes the `only-rendered` and `only-live` counts by exactly
> zero.** The render diff of the edit is three *changed values* and no added or
> removed key (measured, `PROD_FLIP_PREDICTION…20261101.md` § MEASURED: six
> lines, three hunks). So if either count differs from last week's run, the cause
> is not this edit — it is something that changed on prod since 2026-10-25, or
> the ui deployment now being in the capture for the first time.

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
  carry it".
- **The gate-run launcher's pod filter fix (ruling 4) is not exercised by this
  deploy.** It lands before the *next* gate run and nothing in this path depends
  on it.

---

# MEASURED — fill in after the run

Not filled in. The commands above have not been run by this lane and will not
be: steps 1 and 2 read `~/.gya/secrets-prod.yaml` and write secret values to
disk, which is operator-only under the standing law of 2026-10-18. `kubectl` is
also not reachable from this lane's shell.

Record here, after the run:

- the drift gate's verdict block, as printed, both runs;
- whether the three predicted `DIFFERENT` lines were the only ones, and what the
  `only-rendered` / `only-live` counts were against last week's;
- the helm revision number and its status;
- `accept_0_3_3.py`'s output and exit code;
- anything the prediction got wrong, stated as the prediction being wrong rather
  than as the run being surprising.
