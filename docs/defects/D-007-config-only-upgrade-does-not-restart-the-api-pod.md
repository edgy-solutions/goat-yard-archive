# D-007 — a config-only `helm upgrade` does not restart the api pod, so the new config does not take effect

**Status**: open. Scheduled for 0.3.4 by ruling (Chris, 2026-11-01): *"0.3.4
adds `checksum/config` to the api deployment so a config-only change restarts
the pod."*
**Found**: 2026-11-01, while predicting the 0.3.3 render diff for the
`GILL_STRUCTURED_ANSWER` flip
(`docs/audits/PROD_FLIP_PREDICTION_structured_answer_laneA_20261101.md`).
**Affects**: every release of this chart to date, including 0.3.2 and 0.3.3.
Not a 0.3.3 regression, and it did **not** block the 0.3.3 ship — 0.3.3 changes
the api image in the same upgrade, which rolls the Deployment and carries the
config with it. The defect is that the flip's landing is a **side effect of an
unrelated change**, not a property of the upgrade.

## What happens

`templates/api-deployment.yaml:58-62` gives the api container its configuration
through `envFrom`:

```yaml
          envFrom:
            - configMapRef:
                name: gya-frontend-config
            - secretRef:
                name: gya-frontend-secrets
```

`envFrom` is resolved **once, at container start**. The deployment carries no
`checksum/config` annotation — `gya-frontend-minio` and `litellm` both do
(render lines 714, 715 and 971); the api deployment does not. So a `helm
upgrade` whose only change is a ConfigMap value produces:

- an **updated** `ConfigMap/gya-frontend-config`,
- an **unchanged** pod template, therefore no new ReplicaSet, no rollout,
- a **still-running container holding the old value**.

Nothing in that state is an error. `helm upgrade --wait` succeeds, the revision
records `deployed`, and every object is exactly what the chart asked for. The
config is live in the cluster and dead in the process.

## Why it is worth an entry rather than a note

**It makes an acceptance check mean less than it appears to.** The natural
witness for the 0.3.3 flip is "is prod on the signed digest?" — and that check
can pass while the flag never landed. If prod's live api image had already
equalled `sha256:2fce1e34…`, the 0.3.3 upgrade would have been config-only, the
`imageID` item would have passed, and `GILL_STRUCTURED_ANSWER` would still have
read `0` inside the container. The release would have been accepted on the
strength of a check that was never about the thing being shipped.

That is the same shape as the standing finding that a gate must be able to see
the failure it is named for, and it is why `evals/accept_0_3_3.py` item 3 reads
the **container's own environment** rather than the ConfigMap or the pod spec:

- the **ConfigMap** says what the cluster holds, not what the process got;
- the **pod spec** has no `GILL_STRUCTURED_ANSWER` entry at all here, because
  the value arrives via `envFrom` (the paired gate run's jsonpath probe, written
  against a gya-test pod whose flag came from `kubectl set env`, returns empty
  on prod);
- the **container environment** is what the process started with, which is the
  question.

**And it makes the two environments differ in a way that is easy to miss.**
gya-test's flag was flipped with `kubectl set env`, which mutates the pod
template and therefore always restarts the pod. Prod's comes from the chart as a
ConfigMap key, which never does on its own. The flag was *measured* under one
delivery mechanism and is *shipped* under another.

## The fix (0.3.4, not decided in detail here)

Add to `templates/api-deployment.yaml`'s pod template annotations:

```yaml
        checksum/config: {{ include (print $.Template.BasePath "/configmap.yaml") . | sha256sum }}
```

Two things the fix has to get right, both of which the existing minio/litellm
annotations already illustrate:

- **The secret needs the same treatment or the gap only half closes.** A
  rotation of `gya-frontend-secrets` has exactly this failure mode, and
  2026-10-18 was a rotation. A `checksum/secret` entry is the sibling, and
  leaving it out would fix the case that just bit and keep the case with teeth.
- **Hashing the rendered template, not the values**, is what makes the
  annotation move when anything the ConfigMap emits moves — including a chart
  change that adds a key nobody edited.

## What this entry does NOT establish

- **Not** that any past deploy actually lost a config change. The 0.3.3 upgrade
  did roll the pod (the image line changed); 0.3.2's did too. This is an
  unexercised failure mode, found by prediction rather than by an incident. The
  entry exists so that the next config-only upgrade is not the one that
  exercises it.
- **Not** that `checksum/config` makes config changes safe. It makes them
  *effective*: a config-only upgrade would then restart the api pod, which is a
  brief interruption where there is currently none. That trade is the reason it
  is a release item and not a hotfix.
- **Not** a claim about `cloudflared`, `postgres` or the `ui` deployment. The
  `ui` deployment reads the same ConfigMap (render lines 930, 932) and so has
  the same shape; it was not examined here and is not covered by this entry's
  evidence.
