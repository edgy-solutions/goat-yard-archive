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
