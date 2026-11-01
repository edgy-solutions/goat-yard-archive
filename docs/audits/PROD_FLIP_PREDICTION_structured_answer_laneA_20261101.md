# Prod flip prediction — `GILL_STRUCTURED_ANSWER=1` into 0.3.3

Lane A1, 2026-11-01. Written and committed **before** the values edit and before
any render, so the prediction can be wrong on the record. Authority: Chris's
rulings of 2026-11-01, item 2 (the decision) and item 3 (the path).

Evidence for the flip: `docs/audits/GATE_RUN_RESULTS_structured_answer_laneA_20261026.md`
(accepted as written at `e792e7d`, including its "not a win" decomposition —
PASS is by the pre-registered **ratchet**, zero STABLE-PASS → STABLE-FAIL and
zero `must_not_cite`, *not* by a measured quality gain).

## What the edit does

`charts/goat-yard-archive/values-frontend.yaml` only:

| value | before | after |
|---|---|---|
| `api.image.digest` | absent (`tag: "0.3.2"`) | `sha256:2fce1e34…b11433` |
| `ui.image.digest` | absent (`tag: "0.3.0"`) | `sha256:f386254e…96da4` |
| `api.env.GILL_STRUCTURED_ANSWER` | absent | `"1"` |

Both digests are the pairing **gya-test is actually serving** and that the gate
run scored, copied from `values-test.yaml:34` and `:46`. Tags are kept as inert
fallbacks — `digest` wins over `tag` in the `goat-yard-archive.image` helper
(`71981b5`), so a leftover tag cannot defeat the pin.

## Prediction A — the render diff of my own edit

`helm template gya-frontend . -f values-frontend.yaml`, before vs after, differs
in **exactly three places**:

1. `gya-frontend-api` container image → `…/backend@sha256:2fce1e34…`
2. `gya-frontend-ui` container image → `…/frontend@sha256:f386254e…`
3. `gya-frontend-config` ConfigMap gains `GILL_STRUCTURED_ANSWER: "1"`

and in **no others**. Specifically predicted *not* to move: the three
`checksum/…` annotations at render lines 714, 715 and 971. They belong to the
**minio** and **litellm** deployments; `templates/api-deployment.yaml` carries
no `checksum/config` annotation at all.

That absence is a mechanical consequence worth stating plainly, because it
decides whether the flag takes effect:

> **A config-only `helm upgrade` would not restart the api pod.** `envFrom` is
> read at container start, and nothing hashes the config into the api pod spec.
> The flag takes effect here **only because the image line changes in the same
> upgrade** and that rolls the Deployment. If prod's live api image already
> equals `2fce1e34…`, the ConfigMap would be updated and the running container
> would keep serving flag-off. In that case the rollout must be forced, and
> acceptance would otherwise pass on an image check while the flag never landed.

## Prediction B — the standing drift gate against prod

Chris runs it (`values-frontend` + `secrets-prod`; `helm get values`,
`helm get manifest` and secret reads are operator-only under the standing law of
2026-10-18, so this lane works from key names and never from values).

Chris's prediction, restated: **two image lines and the flag line DIFFERENT,
secrets the same.** I hold that prediction, with one stated condition and one
stated unknown:

- **Condition.** It holds only if prod's live release already renders from a
  chart at or near `0.3.0` (the committed `Chart.yaml` version). gya-test was
  found on chart `0.2.1` on 2026-10-11
  (`SMOKE_BLOCKED_gya_test_deployment_state_laneA_20261011.md`). If prod is
  likewise on an older revision, the gate shows a **template-wide** diff, not
  three lines — and that is the gate working, not a failure. I cannot check
  this from here: it needs `helm list`/`helm get` on prod, which is
  operator-only.
- **Unknown.** `secrets same` is a prediction about *key set and values*, and I
  have never seen either side. It rests on the api `secretRef` being unchanged
  by this edit, which is true of the diff above. If the gate reports a secrets
  difference, treat it as new information about prod, not as a fault in this
  edit.
- **`minio.rootPassword` renders from `values-frontend.yaml`'s committed literal.**
  If prod's live value was set out-of-band it will show as a difference. That is
  pre-existing drift this edit neither causes nor fixes.

## Provenance caveat carried, not resolved

`ui.image` is the digest gya-test **is running**, recorded as-running. It was
never smoked as a release artefact, and this lane has not established that it is
CI-built. Ruling 2 says CI-built images only (the crane exception was 0.3.2's);
the backend digest is the CI artefact of run `39168013081` per
`docs/releases/0.3.3.md`, and **the ui digest's build provenance is unverified
here.** Pinning it is still strictly better than the floating `tag: "0.3.0"` it
replaces, because the pin records what runs. Named so it is not mistaken for a
verified claim.

## Acceptance, per ruling 3

In order, after `helm upgrade --wait --timeout 10m`:

1. `imageID` ×2 on the live pods, against the two digests above.
2. The three safe items.
3. The ×5 cited-SID witness.
4. **One served request, then** `/health/stages` — in that order. D-004: a cold
   process alarms with no fault behind it and clears only once a request is
   served, so reading the endpoint first would read the warm-up, not the system.

## What this does NOT solve

- It does not make the flip a measured quality win. The gate passed the ratchet;
  the effect clause abstained. `real_benjamin_type_001` (STABLE-PASS 9/9 OFF →
  FLAKY 2/3 ON) is the one id to watch at higher n (ruling 6) — named, not acted
  on, and one draw is not a finding.
- D-004, D-005 and D-006 ride along to prod unfixed; all three are 0.3.4.
  D-006 is pre-existing on prod, so it is not a 0.3.3 regression (ruling 5).
- The flag is still not a live toggle and still has no canary split: it is
  all-or-nothing per namespace, read at container start.
- The gate-run launcher's pod filter still cannot see a terminating pod that is
  still `serving=true` in the EndpointSlice (witnessed defect,
  `evals/paired_gate_run.py`). Ruling 4 fixes it before the **next** gate run;
  it does not block this ship, and nothing in this deploy path depends on it.

---

# MEASURED — the edit, 2026-11-01

`helm template gya-frontend . -f values-frontend.yaml`, before (`a012c7d`'s
tree) vs after. Six changed lines, three hunks, nothing else:

    @@ -484 +484 @@
    -  GILL_STRUCTURED_ANSWER: "0"
    +  GILL_STRUCTURED_ANSWER: "1"
    @@ -803 +803 @@
    -          image: ".../backend:0.3.2"
    +          image: ".../backend@sha256:2fce1e34...b11433"
    @@ -921 +921 @@
    -          image: ".../frontend:0.3.0"
    +          image: ".../frontend@sha256:f386254e...96da4"

**Prediction A held on what it was for.** Exactly three places changed, and the
three `checksum/…` annotations did **not** move — confirming the mechanical
point above: this upgrade rolls the api pod because the *image* line changed,
not because the config did.

## Prediction A was wrong in one detail, and the error is the instructive part

I predicted the ConfigMap would **gain** `GILL_STRUCTURED_ANSWER`. It did not:
the key was **already rendering at `"0"`**, inherited from `values.yaml:101`,
which is the chart default and is always merged under the overlay. My edit
*changed* a value; it did not add a key.

The cause is not a typo. I asserted "absent" from a **file-scoped read** of
`values-frontend.yaml` and `templates/configmap.yaml`, and a file-scoped
assertion cannot see a two-file merge — only the render can. I had the render in
hand (I had already produced `render_before.yaml` to check the checksum
annotations) and did not grep it for the key I was making a claim about.

Chris's own wording — "flag line **DIFFERENT**" — is the correct description and
mine was not. Two consequences, both real:

1. **Prod's live ConfigMap very likely already carries `GILL_STRUCTURED_ANSWER: "0"`**,
   if prod renders from a chart that has the key (added `a81b98b`). So the drift
   gate should show that line as a *changed value*, not as an addition. If it
   shows as an addition, prod is on a chart older than `a81b98b` — which is the
   Prediction-B condition firing, and worth knowing.
2. A grep of either values file alone answers a different question than "what
   does prod deploy". `test_values_frontend_ships_the_flag_on` now asserts on
   the **render** for exactly this reason, with the miss recorded in its
   docstring.

## Guards added, and proved live by mutation

`charts/test_image_helper.py` went 12 → 17 checks (`EXPECTED_TEST_COUNT`
bumped with them, so a silently vanishing test still fails the run). The prod
pin had **no** guard at all until now, while gya-test has had one since the day
it was pinned — a guard on one environment and not the other is an asymmetry,
not coverage.

- `test_values_frontend_is_still_pinned_by_digest`
- `test_values_frontend_ui_is_still_pinned_by_digest`
- `test_prod_ships_the_pairing_the_gate_actually_scored` — prod and gya-test must
  render the **same two digests**. Ruling 2 ships "the gya-test pairing", and the
  flip evidence is a gate run against that exact pair; bumping one side alone
  would put prod on an unscored pairing while every single-file check still
  passed.
- `test_values_frontend_ships_the_flag_on` — on the render, not the file.
- `test_values_yaml_default_stays_off` — a fresh install without the prod
  overlay must not inherit the flip.

Green does not show a guard is live, so each was mutated:

| mutation | result |
|---|---|
| drop the prod api digest | FAIL × 2 (`…pinned_by_digest`, `…pairing…`) |
| flag back to `"0"` | FAIL (`…ships_the_flag_on`) |
| ui digest → all-zeroes | FAIL × 2 (`…ui_pinned…`, `…pairing…`) |

Restored afterwards; 17/17 green on the restored tree. The suite still exits
**UNRUN (2)** rather than passing when helm or the chart dependencies are
absent.
