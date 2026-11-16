# Release process — the steps that come before a runbook exists

This file exists because of one failure, named here so the step is not re-derived
from scratch next time.

`release-0.3.3` was cut from `main` and then `main` moved: `529484f` and
`a674cd2` — the two fixes that made the 0.3.2 upgrade survivable at all — landed
on `main` and sat there for three weeks. `RELEASE_0.3.3.md` was written against
the branch as it stood, its prediction was computed from that branch, and the
drift gate stopped at step 1 on 2026-11-15 with three faults in the render. The
gate saw one of them. The object count caught a second. The third
(`deploymentUpdate.type: RollingUpdate`) is not among the gate's compared keys
and was invisible; on one replica of a ReadWriteOnce volume it hangs the upgrade.

The runbook was not wrong about the branch. The branch was wrong about `main`.

---

## Step 0, before a word of the runbook is written

**1. Merge `main` forward into the release branch, and render.**

```sh
git -C ~/git/goatyard-relXXX checkout release-X.Y.Z
git -C ~/git/goatyard-relXXX merge --no-ff --no-edit main

# BOTH must print nothing. The first is the condition that failed in 0.3.3.
git -C ~/git/goatyard-relXXX log --oneline release-X.Y.Z..main
git -C ~/git/goatyard-relXXX log --oneline release-X.Y.Z..release-<previous>
```

Empty output from both is the pass. A non-empty first line means the branch is
missing something `main` already decided, and **every number the runbook is about
to state is computed from the wrong tree** — the prediction, the object count, the
chart subtree sha.

Predict the merge before running it (merge-base, commit count, which files) and
say so, so a surprise is visible rather than absorbed.

**2. Render both sides and diff them, before predicting anything.**

```sh
helm template <release> <chart> -n <ns> -f <overlay> -f <secrets> > rendered.yaml
```

Render the pre-merge tree too, and diff the two renders. In 0.3.3 that diff is
what *confirmed* the cause — 16Gi / RollingUpdate / 19 objects before,
4Gi / Recreate / 18 objects after — independently of reading the commits. A
render is evidence; a commit message is a claim about one.

**3. Run the chart suite on the merged tree.**

```sh
cd charts && <python> test_image_helper.py    # exit 0, N/N, no UNRUN
```

`UNRUN` with exit 2 is not a pass. It means a precondition (helm, the vendored
subchart, PyYAML) is absent and nothing was checked.

**4. Only now re-pin and write.** The chart subtree sha moves when the merge
touches the chart, so every pin in the runbook is re-derived from the merged tree:

```sh
git -C ~/git/goatyard-relXXX rev-parse release-X.Y.Z:charts/goat-yard-archive
```

---

## Step 5 — the public UI is a SEPARATE deploy, by hand, outside the cluster

**This step exists because 0.3.3 was accepted without it.** The chart's ui
digest rolled; the page the public reaches did not change, because it is not
served by the cluster. See `RELEASE_0.3.3.md` § Which UI the public reaches.

The public site is a **Cloudflare Workers** project named `goat-yard-archive`.
Its config is `wrangler.jsonc` **at the repo root** — not in `frontend/` — and
it serves `/` from the `frontend/dist` build baked into the bundle, forwarding
only `/api/*` and `/scans/*` to `origin.goatyardarchive.org`. **No CI workflow
deploys it**: neither `build-containers.yml` nor `eval.yml` mentions wrangler,
pages or workers. Every deploy it has ever had was a hand-run command.

### The commands

```sh
# 1. build the bundle the Worker will serve
cd ~/git/goatyard-relXXX/frontend
npm ci                      # package-lock.json IS tracked; use ci, not install
npm run build               # tsc && vite build -> frontend/dist (gitignored)

# 2. deploy from the REPO ROOT, where wrangler.jsonc lives
cd ~/git/goatyard-relXXX
npx wrangler deploy
```

Cloudflare credentials are the operator's. Nothing in this repo holds them and
no agent runs step 2.

**`wrangler` is not pinned anywhere in this repo.** There is no root
`package.json`, so `npx wrangler` resolves whatever is current that day — and
`wrangler.jsonc`'s own `$schema` points at `node_modules/wrangler/`, which is
never installed. Record the wrangler version the deploy printed. Pinning it is
0.3.4 scope.

### The acceptance item: read the public page's build identifier

The deployed bundle is identified by the content-hashed entry script that the
served `index.html` references, `/assets/index-<hash>.js`. Vite derives that
hash from content, and `frontend/package-lock.json` is tracked, so a local
`npm ci && npm run build` of the release tree reproduces it.

```sh
# what the public is being served
curl -s https://goatyardarchive.org/ | grep -o 'assets/index-[A-Za-z0-9_-]*\.js'

# what the release tree builds
ls ~/git/goatyard-relXXX/frontend/dist/assets/index-*.js
```

**Each command must print exactly one string. A `grep` that matches nothing
prints nothing and exits 1, and a check that reads nothing has not passed —
record it as NOT OBSERVABLE and say which side was silent.** The entry name is
vite's default (`assets/index-<hash>.js`) and is not asserted anywhere; if a
config change renames it, the grep misses and must abstain rather than agree
with an empty counterpart.

Equal means the public page is this release's frontend. **Record both strings
either way**, and record the node and wrangler versions beside them: the hash is
reproducible across a lockfile, not across a toolchain, so a mismatch is a
question ("which tree, which toolchain?") and not by itself a verdict. An
unequal pair with a known-stale Worker is the expected reading, which is what
0.3.3 had and did not notice.

This item answers a question the in-cluster `ui imageID` check cannot: that
check reads a pod no public request reaches.

## What this checklist does NOT solve

- **Nothing enforces it.** These are commands a human can skip, which is exactly
  how 0.3.3 happened. A CI check that fails a `release-*` branch whose
  `log release-X.Y.Z..main` is non-empty is the real fix and is 0.3.4 scope.
- The chart suite catches the three 0.3.2 minio symptoms by name, not the general
  case of a release branch missing a deploy fix.
- Step 2 compares two renders. Neither is prod. The drift gate against a live
  capture is still the only thing that compares a release to the cluster.
- **Step 5 is not automated and the Worker has no CI.** A release can still ship
  a backend and leave the public page three months old, which is what 0.3.1,
  0.3.2 and 0.3.3 each did. Nothing fails when it happens.
- Step 5's build-identifier comparison is reproducible across a lockfile, not
  across a toolchain. It is a recorded pair of strings, not a gate.
