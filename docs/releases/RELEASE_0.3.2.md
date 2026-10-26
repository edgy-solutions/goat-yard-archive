# RELEASE 0.3.2 — prod deploy record

Written for whoever runs the next prod upgrade, and for whoever reads
`/health/stages` on production afterwards.

**This is not the release notes.** What 0.3.2 *contains* is
[`0.3.2.md`](0.3.2.md) — the commit line, what ships, the operational caveats.
This file is what happened when it was deployed to prod on 2026-10-25: three
helm revisions, two failures, what was changed to get past each, and what the
acceptance did and did not establish.

---

## The artefact

| | |
|---|---|
| repository | `ghcr.io/edgy-solutions/goat-yard-archive/backend` |
| digest | `sha256:ac37c84fed147f96fb14c276a8fb51869d6b6d765257959e578bc6366d0c7d8e` |
| tag | `0.3.2`, bound to that digest by `crane tag` |
| frontend | unchanged, `frontend:0.3.0` — neither 0.3.1 nor 0.3.2 rebuilds the UI |

**The `:0.3.2` tag was created by re-pointing, not by rebuilding.** The digest
above is the artefact that was smoked on gya-test; a CI rebuild of the same
source would have produced a different digest and therefore an artefact that
was never smoked. Chris ran the re-point at 13:48–13:49 on 2026-10-25:

| step | result |
|---|---|
| `crane digest …backend:0.3.2` (before) | `MANIFEST_UNKNOWN` — the tag did not exist, so nothing was overwritten |
| `crane tag …backend@sha256:ac37c84f… 0.3.2` | `digest: sha256:ac37c84fed…66d0c7d8e  size: 1609` |
| `crane digest …backend:0.3.2` (after) | `sha256:ac37c84fed147f96fb14c276a8fb51869d6b6d765257959e578bc6366d0c7d8e` |

`crane tag` binds a name to an **existing** manifest, so tag-equals-digest holds
by construction rather than by luck. `docker buildx imagetools create` does not:
it constructs and pushes a new index, which is where the earlier worry about an
unpredictable resulting digest came from. Use `crane tag` or nothing.

**This was a one-time bridge, and tagging is CI-only from 0.3.3 onward.** The
0.3.2 tag had to be made by hand because it never existed — the 0.3.2 line was
built and smoked before anyone tagged it. From 0.3.3 on, CI publishes the tags
(the 0.3.3 build pushed `:0.3.3` and `:latest`), so there is no manual retag to
do and nobody should invent one. If a future release needs a hand-made tag, that
is a sign the release was cut without a tag, which is the defect to fix.

**Verification is against the digest, not against gya-test.** The acceptance was
originally written as "identical pod `imageID` vs gya-test". That comparison
expired: gya-test was rolled onto the 0.3.3 digest (`2fce1e34…`) on 2026-10-18
and nothing there serves `ac37c84f…` any more. Comparing prod to gya-test was
only ever a proxy for comparing prod to the smoked artefact; the digest *is* that
artefact, so the check is the same claim with one hop fewer — and it does not
expire when a test environment moves on.

---

## The deploy: revision 29 → 32

Prod sat on revision 29 (chart 0.3.0) from 2026-08-02. It took three revisions
to record `deployed`, and **neither failure was in anything 0.3.2 changed** —
both were in the MinIO subchart, surfacing stale defaults that had never been
exercised because nothing had upgraded this release in two and a half months.

| rev | result | what happened |
|---|---|---|
| 29 | — | the starting point: chart 0.3.0, last written 2026-08-02 |
| 30 | `failed` | `--wait` timed out (client rate limiter / context deadline exceeded). MinIO's new pod was **Pending**: `0/7 nodes are available: 1 Insufficient memory`. The old MinIO pod stayed Running and Ready throughout, so `/scans` never went down. |
| 31 | `failed` | api rolled to the 0.3.2 digest and MinIO came up on 4Gi, but the **post-upgrade hook** (`gya-frontend-minio-post-job`) sat in `ImagePullBackOff`, BackOff ×109 over 25m, until the hook timed out. |
| 32 | **`deployed`** | hook disabled and the MinIO server image pinned. No MinIO rollout, so no `/scans` outage. |

**No rollback was performed at any point.** Rolling back to revision 29 would
have restored that revision's stored values, which predate the 2026-10-18
credential rotation — so a rollback was the one action guaranteed to break
production, and the instruction to roll back was withdrawn permanently while
revision 30 was still failing.

### Why revision 30 could not schedule

minio-5.3.0's own default is `requests.memory: 16Gi`, and this chart carried no
override — so every render since the dependency was pinned asked for 16Gi, while
the live pod ran on **4Gi that had been set out of band**. A hand-edit was the
only reason MinIO was schedulable, and the first `helm upgrade` to touch that
Deployment took it away.

The pod can only ever land on `k3s-worker5`, and **not** because of the dmz node
label — `k3s-worker4` carries `network=dmz` too, is Ready and schedulable, and
has 30018Mi allocatable, which 16Gi would have fitted. The pin is the
**volume**: PVC `gya-frontend-minio` binds a `local-path` PV carrying
`nodeAffinity: kubernetes.io/hostname In [k3s-worker5]`, with the data on that
node's disk under `/var/lib/rancher/k3s/storage/`. That is also why the
scheduler said "**1** Insufficient memory" rather than 2: worker4 was filtered
at the volume predicate before memory was considered. If you read the earlier
cause in `529484f` ("the only dmz node"), it is wrong and corrected in
`a674cd2`. It matters because on the recorded cause, adding a dmz node is a fix;
on the real one it does nothing at all.

### Why revision 31's hook could not pull

`quay.io/minio/mc:RELEASE.2024-04-18T16-45-29Z` returns **401**. Not a deleted
tag — the whole `minio/*` namespace is auth-gated or withdrawn, on both public
registries, **including the server image prod is running**. Measured with an
anonymous token flow whose controls pass:

| reference | result |
|---|---|
| `quay.io/minio/minio:RELEASE.2024-04-18T19-09-19Z` (the running server) | 401 |
| `quay.io/minio/mc:RELEASE.2024-04-18T16-45-29Z` (the failing hook) | 401 |
| `docker.io/minio/minio`, `docker.io/minio/mc` | 401 |
| control: `quay.io/coreos/etcd:v3.5.0` | 200 |
| control: `docker.io/library/alpine`, `docker.io/grafana/grafana` | 200 |
| Docker Hub repository API, `minio/minio` | `object not found` |

The controls are the point: without them a 401 is ambiguous between "the tag was
deleted" and "the repository is now gated", and those take opposite fixes. **No
tag pin can work** — not for mc, not for the server, and not on gya-test either.

This is the same failure as **revision 25 in June**, so treat the hook as a known
defect rather than as news.

---

## The MinIO changes, and the one that is a live-credential matter

Two commits on `release-0.3.2`, both inside the `minio:` block of
`charts/goat-yard-archive/values-frontend.yaml`:

**`529484f`** — `resources.requests.memory: 4Gi` and
`deploymentUpdate.type: Recreate`. Two changes for two reasons: `Recreate`
because a single replica on a ReadWriteOnce volume can never satisfy
`maxUnavailable: 0`, and the request because `Recreate` alone still would not
have fitted 16Gi onto worker5. A brief `/scans` outage during the Recreate was
accepted in advance; it is the only outage this upgrade caused.

**`a674cd2`** — the hook disabled with `buckets: []` and `users: []`, and the
server image pinned to `quay.io/minio/minio:RELEASE.2024-04-18T19-09-19Z` with
`pullPolicy: IfNotPresent`.

### The hook takes three layers to disable, not one

The job renders on
`{{- if or .Values.buckets .Values.users .Values.policies .Values.customCommands .Values.svcaccts }}`.
Removing the `buckets` block from the overlay does **not** disable it, and
neither does `buckets: null`. Both were tried, and the Job rendered both times:

- the parent chart's own `values.yaml` also sets `minio.buckets`, and helm's
  merge keeps a base value that an overlay merely omits;
- minio-5.3.0 ships a **truthy `users:` default**, so the guard is satisfied by
  the subchart alone with every parent-level key removed.

Hence the empty-list overrides: a list override *replaces*, where a null leans on
helm's deletion semantics across a subchart boundary. `values.yaml` is
deliberately untouched, so gya-test and the backend release keep the job.

**Do not re-enable it to "fix" a missing bucket.** The image it needs cannot be
pulled (above), so enabling it fails the release.

### The console user — a live exposure, closed 2026-10-25

The subchart default that kept the job alive was
`users: [{accessKey: console, secretKey: console123, policy: consoleAdmin}]`.
The rendered container is `minio-make-user` running `/config/add-user`: creating
that user is what the job was actually *for* here, and the bucket was incidental.

**That user existed on production, with `consoleAdmin` — admin equivalent — and
the chart's published default secret.** Chris removed it via `mc` on 2026-10-25
and the user list is now empty. `users: []` is what stops the next upgrade
recreating it. The cause was not a local misconfiguration: it was a stale
subchart default that nothing in this repo ever set, reviewed, or knew about.

### What disabling the hook costs

Bucket and policy creation for this release is now **one-time manual
provisioning with no declarative record**. The `scans` bucket and its `public`
policy already exist on prod, so nothing was lost — but a fresh install of this
release against an empty MinIO comes up with no bucket, and this paragraph is the
only place that says so.

---

## Acceptance

Run after revision 32 recorded `deployed`, with
`C:/Users/cnogr/.gya/accept_0_3_2.py`. **3 pass, 0 fail, 0 not-observable,
exit 0**, confirmed on two independent runs:

```
[PASS          ] api imageID
                 all 1 pod(s) on the signed digest: gya-frontend-api-7f485677fd-xqnpb ghcr.io/edgy-solutions/goat-yard-archive/backend@sha256:ac37c84fed147f96fb14c276a8fb51869d6b6d765257959e578bc6366d0c7d8e

[PASS          ] /health/stages
                 stages={"entity_lookup": true, "expansion": false} not_observable=['answer', 'verifier'] (answer/verifier absent from stages: True)

[PASS          ] debug 403 by default
                 403 and the refusal names the variable

pass 3   fail 0   not-observable 0
```

What each line establishes:

1. **the pod is running the artefact that was smoked** — `imageID` is what the
   kubelet actually resolved and pulled, not what the manifest asked for;
2. **`/health/stages` answers with the 0.3.x contract** — every stage value is a
   boolean, and `answer`/`verifier` carry **no** boolean and are named in
   `not_observable` instead, so a consumer reading `stages["answer"]` gets a
   `KeyError` rather than a fabricated pass;
3. **the debug capture channel refuses by default**, with a 403 that names
   `GYA_DEBUG_STAGES` so the reader is not sent to look at ingress or auth.

**The first run, on a cold pod, read all-false.** That is D-004, now observed on
production — see below. One served request is a precondition of this acceptance,
not an optional warm-up.

### `expansion: false` is not a failure of this release

The stage flag reads false and the release is healthy. Both are true, and the
reason is worth knowing before someone pages on it.

On the served request (`"What does Gill say about the Word of God?"`), BAML
expansion **ran and succeeded** in 6.27s, returning
`Word of God, Divine Revelation, Holy Writ, Inspired Scripture`. What it did not
return was entities: `mapped_entities` came back `[]`. The structural sentinel
(`backend/main.py:518`, ADR-0008 step 2b) classifies that as a punt
(`entities_given_none_returned`) and **deliberately raises** `ValueError`, which
routes into the fallback dispatch. There the thesaurus had also droughted, so
case A2 fired — `poisoned_manifest_suppressed`, ADR-0012 — the entity boost was
suppressed, and retrieval ran on the deterministic floor.

So, to answer the question directly: **expansion was not skipped, and it did not
fail on truncation or a retry.** There was no network error and no retry path.
The flag is false because `record_request` counted an `expansion_error`, and the
"error" was the project's own guard firing on a legitimate model outcome.

Three things follow, none of which is a bug in 0.3.2:

- **`expansion` has no `not_run` state.** `record_request` increments `ok` or
  `errored` on every completed request, so after one request the flag can only be
  false by way of `errored > 0` or `fallbacks > 0`. It cannot report a skip. If
  you see false, something ran.
- **Three of the four fallback kinds are deliberate design decisions, not
  faults** (`anchored_manifest_trusted`, `poisoned_manifest_suppressed`,
  `vector_tier_degraded_suppressed`), and two of them are set on the
  BAML-*success* path. A boolean cannot distinguish "the stage broke" from "a
  designed suppression fired", and this flag does not try to.
- **`vector_tier_degraded_suppressed` is ruled out here** by the same response:
  `entity_lookup` reads `true`, which it could not if that gate had fired.

One observation for whoever owns retrieval quality, which is a product matter
rather than a deploy one: on this path the expansion string BAML produced is
**discarded** (`search_text = req.query`), so retrieval ran on the raw question
with no expansion and no entity anchor, even though four usable expansion terms
existed. The branch that would have kept the manifest
(`anchored_manifest_trusted`) requires the thesaurus to have fired, and
`[EXPANSION INIT] vector thesaurus ready with 5 keys` — with five keys, the
drought is close to the default outcome, so A2 will be the common path.
Reported, not changed; nothing here was touched for this release.

---

## D-004, observed on production

`/health/stages` on a **cold process** reports stages false that have not run —
the counters are empty, and an empty counter reads as an alarm rather than as
"no data". Full cause and fix in
`docs/defects/D-004-cold-process-stage-health-false-alarm.md` (on
`release-0.3.3`): the final `else` in `public_snapshot()`, plus `not_observable`
being derived **per request** from something that is a property of the **build**.

Until that is fixed, two rules for anyone reading this endpoint on prod:

1. **A cold pod's `/health/stages` is not evidence of ill health.** Serve one
   request first. The acceptance above is only valid after a served request, and
   its first run demonstrated exactly this.
2. **Do not point an alerting rule at this endpoint yet.** Every api pod
   restart opens a window in which it alarms with no underlying fault — and
   prod's api process restarted around 2026-10-19 with nothing reporting it, so
   that window is not hypothetical.

---

## The pre-upgrade rule from here on

**Run the drift gate before every prod `helm upgrade` of this release.**
`C:/Users/cnogr/.gya/drift_hash.py`, rendered against live, per key.

The rehearsal that preceded this deploy is **withdrawn as a gate**. It compared
a `helm upgrade --dry-run` render against `helm get manifest`, and both sides of
that comparison derive from helm's **stored** values — so it is structurally
incapable of seeing anything changed in the cluster outside helm, which is
exactly what the 2026-10-18 rotation was. It reported clean, and it would have
said go.

The gate compares rendered against **live**, and it is value-free by
construction: each value is hashed under a random per-run salt that is never
printed, so only object names, key names, value lengths and same/DIFFERENT leave
the script. That is what makes it runnable at all under the rule that commands
printing secret values are operator-only.

It ran twice before this deploy: **22 keys SAME, zero unintended reverts,
exit 0**. The inference it was built to test — that the upgrade would revert the
rotation — **did not hold for the path actually used**, and the reason is the
path. `--reuse-values` renders from release 29's stored values and remains the
dangerous form; the deploy passes the overlay explicitly:

```
helm upgrade gya-frontend <chart-0.3.2> -n gya-frontend -f values-frontend.yaml -f secrets-prod.yaml --wait --timeout 10m
```

With the overlay supplying the rotated values there is nothing to revert.
**Never add `--reuse-values` to this release's upgrade.**

### What the gate does not watch

A clean run means clean **on the compared keys**. Stated plainly because this
gate passed clean and revision 30 broke anyway:

- **Deployment-level fields are uncompared.** `strategy` is the live example —
  the thing `529484f` fixed is a field the gate cannot see.
- **The intended-change set is hardcoded** (`image[api]`, `GYA_DEBUG_STAGES`),
  so the deliberate 16Gi→4Gi fix reports as an *unintended revert* and must be
  read by its printed direction rather than by the exit code. Deliberately not
  whitelisted: a gate that learns each release's exceptions stops being a gate.
- **`crossref_env.py` flattens envFrom keys across objects**, so it answers "does
  any captured source carry this key with this value", not "does *this
  container's* source carry it".

The gate was extended on 2026-10-25 after it passed clean and the upgrade broke:
`Deployment/gya-frontend-minio` was outside its object set and `resources` were
not extracted at all. A resource request decides whether a pod can be
**scheduled**, which gives it the same teeth as a credential revert.

---

## The named residual

This is the residual `backend/stage_health.py:210` points at.

**`answer_ran` / `verifier_ran` say whether a stage was reached on the request
path. They do not assert that every internal sub-check inside a reached stage
executed.** A request that exits on empty retrieval, or runs with no bot
configured, counts into `not_run` and never into `ok` — that part is sound, and
it is what keeps a request that never reached generation from being reported as a
healthy generation. What the flags cannot tell you is whether a stage that *was*
reached ran all of its own internal steps. A stage is reported healthy on the
strength of having been entered and not having recorded a fault.

So `/health/stages` answers "did this stage run and report a fault", and never
"did this stage do everything it is supposed to do". Treat a green board as the
absence of a recorded fault, which is weaker than it looks.

Two acceptance items are also unverified on prod, and will stay that way:

- nested-quote citation pairing
- entity manifest ×5 identical

Both read `available_entities` or the per-stage capture, which `backend/main.py`
populates **only** when the debug gate allows it. Observing them on production
means setting `GYA_DEBUG_STAGES=1` there — opening the exposure channel 0.3.2
exists to keep shut. Both were verified on gya-test against the same digest the
`imageID` check pins, so **the artefact is identical**; what is unverified is
that it behaves the same in prod's environment. That residual is accepted
knowingly, and it is not closed by anything in this document.

---

## What this release does NOT solve

- **The MinIO server image is obtainable from exactly one place: worker5's
  containerd cache.** The pin keeps the reference byte-identical so that cache
  keeps satisfying `IfNotPresent`; it does **not** make the image pullable.
  kubelet garbage-collects images under disk pressure and a reimage destroys
  them, and the node holding the only copy of the image is the node holding the
  only copy of the data. The fix is a mirror in `ghcr.io/edgy-solutions` — where
  the api image already comes from — with `minio.image` repointed at it. Until
  then prod's object store cannot be rebuilt anywhere. **This is the largest
  unaddressed risk this deploy leaves behind.** Whether the image is cached
  cannot even be read from node status: every worker reports exactly 50 images,
  the `--node-status-max-images` cap, so absence there is not evidence.
- **Bucket and policy provisioning is undeclared** (above). A fresh install comes
  up with no `scans` bucket.
- **The committed MinIO root credentials disagree with live.** This file's chart
  still reads `rootUser: "minio"` / `rootPassword: "minio123"`; the live root
  user is `admin`, set during the rotation, and the overlay matches live, so the
  drift gate reads SAME. **The overlay governs — this is a discrepancy in the
  committed file, not a live weak credential.** It is still a landmine: a deploy
  that omits `secrets-prod.yaml` renders those values, and because they are
  MinIO's *root* credentials, that render changes the server's own identity
  rather than merely setting a wrong value. The remedy is the chart ceasing to
  accept credential values at all, which is platform-ticket work.
- **An orphan `gya-minio` PVC** holds 50Gi on worker5, Bound and mounted by
  nothing, alongside stale `gya-minio` Services and a ConfigMap. Not touched
  here; tracked on the platform ticket.
- **D-004 is open.** The endpoint this release added is not yet safe to alert on.
- **The 0.3.2 line does not rebuild the UI.** Prod's frontend stays on
  `frontend:0.3.0`.
- **Nothing here measures answer quality.** Acceptance establishes that the right
  artefact is running, that its health contract is honest about what it cannot
  see, and that the debug channel is shut. It does not establish that answers got
  better, and the paired ON/OFF gate run that would speak to that has not been
  done.
