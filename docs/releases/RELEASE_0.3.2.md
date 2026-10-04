# Release 0.3.2 — `GET /health/stages`, backend only

**Prepared by Lane A, 2026-10-04. Chris deploys.** Branch `release-0.3.2`, one commit on top of
`release-0.3.1`. **0.3.1 must go out first** — 0.3.2 contains it.

## Why

Production pod logs carry only uvicorn access lines. The only window into per-stage LM health was
`debug: true` on a single `/api/search` request, which answers "what did this one request do", never
"is the expansion stage alive on the server that is running right now".

That second question is the one that cost fourteen eval arms. Expansion was dead for weeks across
266 questions and every arm summary read `violations: []`
(`docs/audits/VOID_arms_without_expansion_laneA_20261004.md`). Nothing in production can currently
rule out the same silence.

## The whole release, exactly

```
$ git diff --stat release-0.3.1 release-0.3.2
 backend/main.py                               |  49 +++
 backend/stage_health.py                       | 304 ++++++++++++++++
 backend/test_stage_health.py                  | 479 ++++++++++++++++++++++++++
 charts/goat-yard-archive/values-frontend.yaml |   2 +-
```

`backend/main.py` is **208 lines apart** between `0.3.0` and `body-path`, so this is a hand-written
port against the release tree, not a cherry-pick. `stage_health.py` and `test_stage_health.py` are
byte-identical to `body-path` (`f8c31b0`, `fb38d8b`).

### What it does

`GET /health/stages` returns cumulative per-stage counters for **the process that answers the
request**, plus `pid`, `commit_sha` and `uptime_s`:

```json
{"process": {"pid": 1, "commit_sha": "...", "started_at": "...", "uptime_s": 1234.5},
 "requests_recorded": 87,
 "expansion":     {"ok": 0, "errored": 87, "causes": {"missing_env_var:LITELLM_PROXY_URL": 87},
                   "fallbacks": {"dedup_only": 87}},
 "entity_lookup": {"modes": {"full": 87}},
 "answer":        {"ok": 0, "not_run": 2, "unobservable": 85, "degraded": {}},
 "verifier":      {"ok": 0, "not_run": 2, "unobservable": 85, "failures": {}}}
```

**Four states per stage, not two.** `ok` / `degraded` are not enough to describe what happened:

- **`not_run`** — the stage was never reached. A request that retrieves nothing exits before
  generation. Counting that as `ok` would report a healthy answer that never happened.
- **`unobservable`** — the stage **ran** and this build cannot read its health. That is the
  permanent state of `answer` and `verifier` on the 0.3.x line: tag `0.3.0` has no
  `backend/degradation.py` (the file is new on `body-path`, +233 lines) and no
  `verification_failure` local, so there is nothing to read. `ok` there would be a fabricated pass
  in the one tool built to detect fabricated health.

**Expansion and entity lookup are fully readable**, and expansion is the stage the release is for.

### Safety

- **No raw text is ever stored.** The raw BAML exception string is bucketed to a fixed cause key
  (`missing_env_var:<VAR>`, `http_404`, `http_429`, `timeout`, `other`) and discarded before
  `record_request` returns. The bucketing mirrors `evals/expansion_census.py` exactly, so the route
  and the census cannot drift about what "healthy" means.
- Every other field is matched against an allowlist derived from the code that produces it; anything
  unrecognised becomes the literal `"other"`. That bounds memory **and** keeps URLs, secrets and
  query fragments out of a response any operator can curl. Born-tested with a fake secret and URL in
  the exception text, asserted absent from `json.dumps(snapshot())`, and asserted again against the
  live payload by the acceptance script.
- **`record_request` never raises.** Telemetry that can 500 a user request is worse than no
  telemetry.

### What does NOT change

- **`/health` is byte-identical.** A test asserts its returned dict literal is still present
  verbatim, so the k8s probe is untouched.
- **No answer path.** `bot.py`, the prompts, the verifier, DSPy and BAML are not touched. No new
  dependency — stdlib only (`os`, `re`, `threading`, `time`, `datetime`).
- **No behavior change on any request.** The recorder is passive. The one new assignment in the
  request path (`fallback_kind` at the ADR-0014 gate) is read by nothing except the recorder: the
  only other reader runs earlier in the same request.
- **No env var, no schema, no migration, no API shape change.** `/api/search` request and response
  models are identical.
- **The UI image stays at `0.3.0`.**

## Deploy

```bash
# 0.3.1 first -- 0.3.2 contains it.
git push origin release-0.3.2
git tag 0.3.2 release-0.3.2
git push origin 0.3.2
# CI builds on '*.*.*' (build-containers.yml)
./pipeline/scripts/deploy_helm.sh prod   # from the release-0.3.2 checkout
```

**Rollback** is `api.image.tag` back to `"0.3.1"` (or `"0.3.0"`) and a redeploy. No data or schema
component.

**Forward-merge footgun, same as 0.3.1:** neither `5c93b28` nor the chart bump is on `main`. A
deploy from a `main` checkout silently regresses production.

## Acceptance

```bash
python evals/acceptance_stage_health.py --base-url https://goatyardarchive.org --probe-search
```

**The script lives on `body-path`, not on the release branch** — run it from the Lane A checkout
(`C:\Users\cnogr\git\goatyard-laneA`), same as the 0.3.1 acceptance script.

`--base-url` is required with no default; no scheme exits 2. Exit **0 pass**, **1 fail** (route
absent → the deployed image is not this release; wrong snapshot shape; counters did not move;
sentinel or URL leak), **3 inconclusive, never a pass** (a request failed).

`--probe-search` serves **one** real `/api/search` so the counters can be shown to move. It costs
one LM call and one slot of the anonymous rate limit (`RATE_LIMIT`, default `10/day`). Without it
the script only reads the snapshot — enough if the pod has already served traffic, but then nothing
proves the recorder is *wired*, and the script says so.

**What the verdict covers and what it does not.** PASS means the route answers, the shape is right,
the safety properties hold on the live payload, and serving a request increments the counters. It
does **not** mean any stage is healthy. A snapshot showing `expansion.errored > 0` is a **PASS for
this release and a finding about the server** — the route exists to report exactly that, and failing
the release on it would be a gate refusing to show what it was built to see. The script prints the
per-stage block under a header saying none of it is a release verdict.

Six branches born-tested against a stub server: shape-only PASS, probe PASS with a counter delta,
and FAIL on each of a degenerate snapshot, a leaked sentinel, a leaked URL, and a 404 route.

## What this release does NOT solve

- **It cannot read the answer or verifier stage.** Both report `unobservable` and will keep doing so
  until `backend/degradation.py` and the bot's `verification_failure` local ship. That is
  answer-path code and a separate, larger release. Chris asked for four stages; this delivers two
  measured and two explicitly typed as unreadable, which is the honest split, not the requested one.
- **Counters are per process and in memory.** Each replica reports its own; a restart zeroes them;
  nothing is persisted. `pid` and `uptime_s` are in the snapshot so a reader can tell which process
  answered, and the acceptance script fails if two reads come from different pids during a probe.
- **"Ran" means the stage was reachable on this request path**, not that every internal sub-check
  executed. A reached answer stage that skipped verification internally would still count the
  verifier as reached.
- **The route is unauthenticated**, like `/health`. It discloses the commit SHA, request volume and
  per-stage error rates to anyone who curls it. That is a deliberate disclosure, in the same family
  as `debug: true` being ungated (`backend/main.py:386`), and it is a decision worth making
  explicitly rather than inheriting. Gating it behind the existing auth is a one-line change if the
  answer is no.
- **It does not make any eval arm valid, and it does not fix expansion anywhere.** It makes the
  state visible. If production shows `missing_env_var:LITELLM_PROXY_URL`, that is a finding to act
  on, not something this release broke.
- **It measures nothing about scores.** No question, no answer, no retrieval behavior is touched.
