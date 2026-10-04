# PREDICTION — OFF vs ON rerun pair (attempt 4), Lane A, 2026-10-04 (locked before launch)

Supersedes nothing. `PREDICTION_off_vs_on_rerun_laneA_20261004.md` and its
[RESULT](RESULT_off_vs_on_rerun_laneA_20261004.md) stay as the record of the arm that was **voided
by a truncated HTTP response body**. This is a fresh pair, both arms unrun at the time of writing.

**The voided OFF arm's scores are not cited in this document for anything, including "the fix did
not change much."** This pair is the first thing measured with the retry in place.

## What changed in the product since that arm, identically for both arms

1. **`retry_policy BoundedTransport` (3 retries, exponential 200ms→2s) on `LocalRouter`**, the
   client the expansion call runs on. The arm was voided by one
   `reqwest::Error { kind: Request, source: hyper::Error(IncompleteMessage) }` — a truncated body
   from the LiteLLM proxy, one request in 67 — and `grep -rn retry baml_src/` returned nothing.
   Verified against the exact fault, not a neighbouring one: a raw socket that accepts the request
   and closes without writing reproduces `IncompleteMessage` character-for-character, and BAML
   opens **4** connections (`backend/test_expansion_retry.py`, 4/4).
2. **The bound is observable, not merely declared.** `expansion.retries`
   (`total`, `calls_with_retries`, `max_observed`, `bound_exhausted`, `unobserved`) is counted per
   request from `len(log.calls) - 1` — never from `LLMCall.selected`, which is `True` on every call
   including the three that failed. `unobserved` is a third state kept out of the counts, because a
   missing collector says nothing about retries and folding it into `0` would report a healthy
   transport on no evidence. `backend/test_stage_health.py` 31/31.
3. **`provisional` is narrowed to ATTRIBUTABLE corpus change**, on the condition that read-faulted
   objects are **re-read after the run and still match the AT_START sample**. No re-read, a failed
   re-read, a missing object, or a re-read that differs → still provisional.
   `evals/test_corpus_state.py` 37/37, `evals/test_run_eval_harness.py` 152/152.
4. **Preflight and a new postflight refuse on the retry counters**: absent `retries` key (a server
   that predates the instrumentation cannot report retry health), `bound_exhausted > 0` (every
   allowed attempt failed in a row — a broken transport, not a flaky one), `unobserved > 0`.

## What is being measured

`GILL_STRUCTURED_ANSWER` 0 vs 1 (ADR-0009 typed `GillAnswer` via BAML), 13 question ids × 5 runs =
65 scored runs per arm, against a local uvicorn serving `goatyard-laneA` at `127.0.0.1:8000`,
retrieval from gya-test (`192.168.1.54:80`), answers from `deepseek/deepseek-chat` pinned to
`streamlake` with `allow_fallbacks: false`, temperature 0.0, LM cache disabled, KJV index loaded
from `MINIO_HTTP_ENDPOINT=http://test.chart-example.local`.

**Cross-process on purpose.** The server is killed and relaunched between arms. A same-process pair
is structurally blind to a per-process defect, which this lane has already been bitten by once.

**Endpoint note — corrected from the previous prediction.** Expansion routes through
`LITELLM_PROXY_URL=http://localhost:4000/v1`, a `kubectl port-forward` to `svc/litellm-service` in
namespace `gya-test`, which serves the `local-router` alias and round-robins to `.179`/`.188`. That
is the goatyardtest carve-out `gpu-servers.md` assigns to this project, not a config of mine naming
those hosts. **This pair does not touch endpoint D**, which Lane A2 has priority on and owns.

## Predictions

**P1 — validity before any score.** In BOTH arms:
`stage_health.expansion == {"errored": 0, "healthy": 65, "distinct_fallback": ["<none>"]}` and
`entity_lookup.distinct_mode == ["full"]`. If P1 fails, no score in that arm means anything and the
arm is reported as void regardless of what it scored. Reported first, before any number.

**P2 — the retry counters.** Across the whole pair (~134 expansion requests):
`bound_exhausted == 0` and `unobserved == 0` in both arms; `total` in **0–4** with
`max_observed ≤ 2`. Reasoning: the measured fault rate is one request in 67, each fault needs one
retry to clear, and three consecutive failures of the same request would be a different defect.
**Falsifier for the whole fix:** `errored > 0` with a transport cause *and* `bound_exhausted > 0`
means the bound was reached and the retry did not save the arm.

**P3 — `unobserved` is the honest risk in this pair.** The collector tests are source- and
shape-level; this run is the **first live evidence** that `baml_py.Collector.last` is populated
per request inside the real server on the success path. If `unobserved == 65`, the wiring is wrong
and the preflight refuses on the probe request alone — within seconds, not after an hour.

**P4 — the corpus axis comes back CITABLE WITH A CAVEAT, not provisional.** Predicted:
`changed_during_run is None`, `violations == []`, `read_fault_uuids` naming **1–6** objects per arm,
`reread.status == "confirmed"`, `reread_confirmed is True`, `provisional is False`, and exactly one
`caveats` entry naming those uuids. The client-side corruption hits roughly 7 vectors per 7294 and
produced 2 last time, so 0 is possible; if it is 0, `reread.status == "not-needed"`,
`provisional is False` via `changed_during_run is False`, and that is a pass of P4 too.
**Falsifier:** `reread.status == "differs"` would mean something actually wrote to gya-test during
the arm — a finding, not noise, and the arm stays provisional.

**P5 — git axis.** `integrity.git.changed_during_run is False`, `dirty false` at both ends, HEAD
identical to the commit this prediction is committed in. Nothing is committed in either repo from
the first scored request until the pair finishes.

**P6 — the gates fire in the right direction.** Preflight PASSES on both arms (it has refused
three times on three different real faults). Postflight PASSES on both arms. `run_eval` exits 0 on
both.

**P7 — provider pin.** `{order: [streamlake], allow_fallbacks: false}`, `lm_cache_allowed False`,
one distinct `answer_lm` per arm, `pin_honored true`, `temperature_on_the_wire 0.0`.

**P8 — scores, with no citable basis and said so.** Every prior arm on this question set is void:
the pre-2026-10-04 arms ran with expansion dead (`VOID_arms_without_expansion_laneA_20261004.md`),
and the only arm that ever ran with it live is the one voided for the transport fault, whose numbers
this document does not use. So this is a **prior, not an extrapolation**: OFF lands in **7–13 of
13**, and I expect **no readable OFF-vs-ON delta** — `|ON − OFF| ≤ 2 questions`.

**P9 — flakiness swamps the delta.** `flaky ≥ 3` of 13 at fixed config in each arm. Any
OFF-vs-ON difference smaller than that is unreadable whatever the integrity verdict says, and I
will not report one as a finding.

## The rule, locked before launch

- P1 fails in **either** arm → that arm is void and **the pair is abandoned, not spliced**.
- Postflight refuses on **either** arm → that arm's scores are not citable.
- HEAD moves during either arm → the pair is void.
- A corpus `read_fault` whose re-read **differs** → that arm is provisional and the reason is
  reported as a finding about gya-test, not as noise.

## What this prediction does NOT cover

- **The root cause of the body truncation.** The retry makes the arm survive it; it does not
  explain it. The honest next step is still a packet capture, and it has not been taken.
- **The production path.** The same retry belongs on the deployed API together with the
  `/health/stages` endpoint; that is a 0.3.2 item and is not in this pair.
- **`commit_sha=unknown`** from the server, so the launcher's HEAD-freeze assertion is still the
  only guard that the code serving the arm is the code at HEAD.
- **The `other` cause bucket.** An HTTP 404 and a legitimately empty extraction remain
  indistinguishable in the counters; the `baml_punt:<reason>` split stays deferred because
  `backend/stage_health.py` must be byte-identical across the pair.
- **What the product tells a user** when expansion fails: still nothing. Retrieval falls back to
  the raw query silently.
- **The launcher.** `preflight_arm.py`, `postflight` and `run_pair.sh` all still live in a session
  scratchpad, not in `evals/`, so the next person wiring a pair can repeat attempt 1's mistake.
