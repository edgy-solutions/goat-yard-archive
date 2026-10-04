# Release 0.3.1 — entity-manifest determinism, backend only

**Prepared by Lane A, 2026-10-04. Chris deploys.** Branch `release-0.3.1`, two commits on top of
tag `0.3.0`.

## Why this is a clean isolation

Production runs image tag **`0.3.0`** (`charts/goat-yard-archive/values-frontend.yaml`,
`api.image.tag`), which is commit `84d8afa`.

**`backend/gill_search.py` is byte-identical between `0.3.0` and `d1afdec`, the parent of the
fix.** No commit touched that file in between:

```
$ git diff --stat 0.3.0 d1afdec -- backend/gill_search.py
  (empty)
```

So the fix cherry-picks onto what production actually runs with no conflict and no entanglement with
the 120 other commits on `body-path`. The release is the fix, its born-test, and one line of chart.

## The whole release, exactly

```
$ git diff --stat 0.3.0 release-0.3.1
 backend/gill_search.py                        |  92 +++++++++++++++++---
 backend/test_entity_lookup_order.py           | 118 ++++++++++++++++++++++++++
 charts/goat-yard-archive/values-frontend.yaml |   2 +-
 3 files changed, 197 insertions(+), 15 deletions(-)
```

| commit | what |
| --- | --- |
| `c9186b1` | `fix(search): make the Tier-2 entity manifest a pure function of (query, corpus)` — cherry-pick of `5c93b28`, identical diffstat |
| `fe8ea83` | `release: 0.3.1` — `api.image.tag` `0.3.0` -> `0.3.1` |

### What changes, behaviorally

Inside `GillSearchEngine.get_relevant_entities`, **Tier 2 (substring) only**:

1. Candidate keys are collected into a **list in first-appearance order** instead of a `set`. Set
   iteration order over `str` is randomized per *process*, which is what made the manifest depend on
   which `PYTHONHASHSEED` the server process happened to draw.
2. Matches are consumed **distinctive-first** — candidates ordered by `(number of matches, key)`.
   A candidate matching 2 entities spends the 5-slot cap before one matching 23. The alphabetical
   tie-break makes the order total.

Observable effect: for `What is the spiritual meaning of the scapegoat?` the manifest now contains
`scape-goat` and `antitypical scape-goat` in **every** process. Measured pre-fix across 7 hash
seeds, 4 of 7 processes dropped both; post-fix, 70/70 calls across the same 7 seeds returned one
manifest.

### What does NOT change

- **No feature flag.** Nothing to toggle, nothing to roll forward behind an env var.
- **No answer path.** `backend/bot.py`, the prompts, the verbatim verifier, DSPy and BAML are
  untouched. `GILL_STRUCTURED_ANSWER` is not involved and stays as it is.
- **No change to the other tiers.** Tier 1 (vector, `VECTOR_CONFIDENT_DIST_MAX = 0.25`,
  `VECTOR_TIER_CAP = 3`) and Tier 3 (BM25) are identical, as are `MANIFEST_TOTAL_CAP = 5`, the
  length-5 token floor, the stopword list, and the per-candidate `limit=25`.
- **No signature or contract change.** `get_relevant_entities(query) -> (List[str], mode)`, same
  mode strings, so no caller changes — `backend/main.py` is untouched in this release.
- **The same number of Weaviate calls, in the same order.** Candidates are still fetched in
  first-appearance order; only the order in which results are *consumed* changed. A candidate whose
  fetch raises is still skipped and still contributes nothing.
- **No schema change, no data migration, no re-ingestion, no Weaviate write.**
- **No API shape change.** `/api/search` request and response models are identical.
- **No env var added or required.**
- **The UI image stays at `0.3.0`** on purpose — this release touches only the backend, so
  rebuilding the frontend would be a pod restart for nothing.

## Deploy

```bash
# 1. review
git log --oneline 0.3.0..release-0.3.1
git diff 0.3.0 release-0.3.1

# 2. publish the branch and tag the tip (the tag is what CI builds from,
#    and '*.*.*' is already a build trigger in build-containers.yml)
git push origin release-0.3.1
git tag 0.3.1 release-0.3.1
git push origin 0.3.1

# 3. CI builds ghcr.io/edgy-solutions/goat-yard-archive/backend:0.3.1
#    (it also builds frontend:0.3.1, which this release does not use)

# 4. deploy from the release-0.3.1 checkout, so the chart carries tag 0.3.1
./pipeline/scripts/deploy_helm.sh prod

# 5. confirm the running image is 0.3.1 before accepting
kubectl -n gya-frontend get pods -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{range .spec.containers[*]}{.image}{" "}{end}{"\n"}{end}'
```

**Rollback** is one line and a redeploy: set `api.image.tag` back to `"0.3.0"` and run
`deploy_helm.sh prod`. There is no data or schema component, so rollback is a pod restart with no
cleanup.

**Forward-merge footgun:** `5c93b28` is on `body-path` and **not on `main`**. If a later deploy runs
from a `main` checkout, its `values-frontend.yaml` still says `0.3.0` and production would silently
regress to the broken lookup. The fix and the tag bump both need to reach `main` when `body-path`
merges forward.

## Acceptance

`evals/acceptance_entity_manifest.py` — the endpoint is **required and has no default**, so the
script cannot silently address production.

```bash
python evals/acceptance_entity_manifest.py --base-url https://goatyardarchive.org --runs 5
```

**Pass:** `distinct first-pass manifests over 5 runs: 1`, exit 0. **Fail:** 2 or more, exit 1 — the
deployed image does not carry `5c93b28`, or there is a second cause. **Inconclusive, never a pass:**
exit 3 if a request fails or the response carries no `stages`.

What it asserts and what it only reports:

- **Asserted: `stages.available_entities`**, the first-pass manifest. It is built from the
  *thesaurus*-expanded `lookup_query` (`backend/main.py:513`), which BAML never sees, so it is
  independent of query-expansion health. It is also the manifest the entity boost is anchored on
  (ADR-0013 Part C). This is precisely the claim `5c93b28` makes.
- **Reported, not asserted: `second_pass_entities`.** That lookup (`backend/main.py:585`) is fed by
  **BAML's** expansion, which is stochastic LM output. Production has query expansion live, so this
  may legitimately differ between identical requests. **Variation there is not a failure of this
  release.**
- **Reported, not asserted: `entity_lookup_mode`.** A non-`full` second pass downgrades the whole
  request's mode (`backend/main.py:595`), so it can vary in production for the same reason.

Two practical notes: the anonymous rate limiter (`RATE_LIMIT`, default `10/day`) means 5 runs is
near the per-client budget, so do not loop it; and `debug: true` is settable by any client
(`backend/main.py:386`, no gate), which is how this test can read stages at all and is a standing
disclosure decision of its own.

## What this release does NOT solve

- **It does not make any past eval arm valid.** All 14 arms on disk ran with query expansion dead
  and are void — see `docs/audits/VOID_arms_without_expansion_laneA_20261004.md`.
- **It does not make the second-pass manifest stable in production.** It makes it a pure function of
  `(search_text, corpus)`; `search_text` itself is not stable. In every measurement behind this fix,
  expansion was dead and the second pass **never ran**, so production will exercise a path this fix
  has never been observed on. The acceptance test prints the second-pass manifests for exactly that
  reason — to see what that path does, not to grade it.
- **It does not address the remaining answer-side churn.** `scapegoat_001` still moved 3/6 to 5/6
  with the manifest provably fixed; the live suspects are the unpinned `deepseek-chat` provider and
  the citation boundary. Both are separate work.
- **It adds no observability.** Production stage health still cannot be read from pod logs
  (uvicorn access lines only) or from any route; the only window is `debug: true` on a query. A
  stage-health route is prepared separately as 0.3.2.
