# OFF-vs-ON rerun — result (Lane A, 2026-10-04)

Against the locked prediction in `PREDICTION_off_vs_on_rerun_laneA_20261004.md`.
Reported in the order that document commits to: **validity first, scores last.**

**Headline: the pair did not complete.** The OFF arm ran and scored; the launcher
aborted on a post-run integrity violation (exit 4) before the ON arm started.
There is no OFF-vs-ON comparison in this document, because half a pair is never
spliced. Two decisions are needed before a pair can be attempted again, and both
are at the bottom.

HEAD `75de4db`, tree clean at both ends of the arm.

---

## P1 — validity verdict: **FAILED**

```
scored_runs 65
expansion     {errored: 1, healthy: 64, distinct_fallback: ["<none>", "dedup_only"]}
entity_lookup {distinct_mode: ["full"], counts: {full: 65}}
verifier      {failures: 0}
```

Predicted: errored 0, healthy 65. One run of 65 had a query-expansion error, so
`run_eval` raised one violation and exited 4:

> 1/65 scored run(s) had a BAML query-expansion error — this arm is not comparable
> against an arm with different expansion health

`must_not_cite_violations: 0`.

**By the rule I locked before running** — *"if P1 fails, no score in that arm means
anything and the arm is reported as void regardless of what it scored"* — **this
arm is void.** Everything below P1 is reported because it was predicted, not
because it is citable.

### The one error, fully attributed

The summary stores only `expansion_error: True` with no cause, and the server's
cumulative counter buckets it as `other` — the same bucket a structural punt falls
in, so neither witness could attribute it. The server's stdout could: exactly one
occurrence of the handler's print, at `server_arm_0.log:20481`.

- **Question:** `real_ishmael_circumcision_001`, run index 1 of 5.
- **Exception:** `BamlValidationError` wrapping
  `reqwest::Error { kind: Request, url: "http://localhost:4000/v1/chat/completions",
  source: hyper::Error(IncompleteMessage) }`.
- **What that is:** a truncated HTTP response body from the LiteLLM proxy. Not a
  404, not a model refusal, not `entities_given_none_returned`, and not the
  structural punt that aborted attempt 2. A transport fault.
- **Which fallback:** `dedup_only` — Case B of the `except` dispatch in
  `backend/main.py:726` ("manifest may be fine, only the rewrite failed"), which is
  consistent: there is no `[BAML FALLBACK]` line in the log, because Case B does not
  print one.
- **Outcome of the affected run: it passed.** Retrieval ran on the raw query plus
  a deduplicated manifest, and the answer still scored.

One error in 67 expansion requests (`ok 66 + errored 1`, `requests_recorded 67`).

### A product defect this exposed

**There is no retry policy anywhere in `baml_src/` — `grep -rn retry baml_src/`
returns nothing.** A single truncated HTTP body is therefore an unretried hard
failure on the expansion path, in production as well as in evals, and the user is
told nothing: retrieval silently degrades to the raw query. That is the same
no-empty-channel shape as the warmup punt found earlier in this task — the
component was honest, the system had nowhere to put the honesty.

It also sets the price of the current P1 rule. At the measured rate, an arm of 67
requests is clean with probability `(1 − 1/67)^67 ≈ 0.37`, and a **pair** needs
both arms clean: **≈ 0.13, about one pair in seven.** Honest caveat: that rate
rests on a single event, so the 95% interval on it is roughly 0.04 %–8 %, which puts
P(clean pair) anywhere from ~0.95 to ~0.00001. The interval is too wide to predict
a success rate from — but it does not contain "reliable," and the rule as written
requires perfection on an axis the product does not retry.

---

## P2 — git axis: **PASS**

`head 75de4db` at both ends, `dirty false`, `dirty_paths 0`,
`changed_during_run false`. The fault that voided the original arm is fixed.

Not fixed, and flagged rather than counted as evidence: the server reports
`commit_sha=unknown`, so the launcher's HEAD-freeze assertion is still the only
guard that the code serving the arm is the code at HEAD.

---

## P3 — corpus axis: **CONFIRMED, exactly as predicted**

```
changed_during_run  None          provisional True       violations 0
read_fault_uuids    n=2  21b5a877-9bfd-59ed-a757-f8a0781327b1
                         5ef3456a-fb1a-5892-86bc-20ae70b9ea49
at_start/at_end     available=True  7294 objects  dim_hist {4096: 7294}
                    dim_anomalies 0   read_faults 14 per sample
read_fault kinds    at_start {dim_anomaly_retry: 7, json_decode_retry: 7}
                    at_end   {dim_anomaly_retry: 1, json_decode_retry: 13}
weaviate_url        192.168.1.54:80   include_vectors True (both samples)
```

Predicted 1–6 named uuids; got 2. `dim_anomalies 0` with 14 retries per sample means
the re-fetch resolved every detectable anomaly, which is the instrument from
`c01ee3b` working as designed.

### P4's re-derivability claim, tested rather than asserted

`classify_change` re-run offline against the two stored sidecars, with no server
in the loop, reproduces the run's verdict **exactly**: `real_change False`,
`attributable True`, `added/removed/rewritten` all empty, `read_fault` the same two
uuids in the same order. **MATCH.**

And the two faults have precisely the signature the design predicted:

| uuid | `last_update_ms` | text digest | vector digest |
|---|---|---|---|
| `21b5a877…` | identical (1777234927676) | identical | **differs** |
| `5ef3456a…` | identical (1777231429620) | identical | **differs** |

Both at `dim 4096` on both reads — length-preserving, so no output-side length or
schema check could have caught either. Had the fold-level fingerprint been the only
instrument, `vector_sha256` would have moved and this arm would have reported
**CORPUS CHANGED** — a false violation, attributable to nothing. That is the whole
point of `c01ee3b`, and this is the first run where it fired on real data.

### A claim of mine to retract

I reported `reason: None` in this block as a possible dropped string in `c01ee3b`.
**That was my reader's bug, not a defect in the commit.** The block has no `reason`
key; the string `corpus_changed()` returns is stored as `comparison_scope`, and it
is present and complete:

> not-compared: 2 objects differ only by digest while their last_update_ms is
> identical, which is a bad read, not a corpus change; 21b5a877-…, 5ef3456a-…

The capped human-facing prose is in `note` as well, with both uuids named and the
remedy stated ("the remedy is a RE-READ, never a re-ingest"). `scratchpad/read_arm.py`
asked for a key the producer never wrote and printed `None`, i.e. it manufactured
an absence — the same class of defect as the three gate failures earlier in this
task. It now asserts the key exists instead of defaulting.

### A unification I am declining to make

Three transport-level body faults inside one run — 14 Weaviate read-retries per
sample, 2 undetectable vector corruptions, and one truncated LiteLLM response — is
a conspicuous coincidence, and I previously attributed the Weaviate class to
httpx 0.28.1 / h11 0.16.0. An independent Rust client (reqwest/hyper) failing the
same way would be evidence against a library-specific cause. **It does not hold up:**
the two go over different transports — Weaviate **direct** to `192.168.1.54:80`, LiteLLM
through a `kubectl port-forward` on loopback, which is a userspace TCP relay with
a well-known reputation for truncating under load. The symptoms differ too
(truncation vs. length-preserving re-emission of an earlier block). Two causes,
most likely, and the port-forward one is the better explained. Recorded so the
coincidence does not get written up later as a single root cause it never was.

---

## P5 — the preflight gate: exercised in both directions

Refused twice before this arm (HTTP 404 on every expansion call; then the warmup's
own structural punt), passed here, and the arm it passed then failed P1 on a cause
no preflight could see — a transport fault on request 20 of 67. That is the correct
scope for a preflight, not a gap in it.

## P6 — provider pin: **PASS, exactly**

`{order: [streamlake], allow_fallbacks: false}`, `lm_cache_allowed False`, one
distinct `answer_lm` entry across all 65 runs, `model_returned
deepseek/deepseek-chat`, `temperature_on_the_wire 0.0`, `pin_honored true`,
`provider_served StreamLake`.

## P7 — scores (uncitable; P1 failed)

`passed 9 / total 13` = **69.23 %**, `attempted 13`, `errors 0`, `degraded 0`.
Predicted band 9–13; landed on its floor.

## P8 — flakiness: **confirmed**

`flaky 5` (predicted ≥3), `stable_pass 6`, `stable_fail 2`, `no_data 0`.
Stable failures: `john_baptist_001`, `simons_count_001`.
Flaky detail: `scapegoat_001` 4/5, `day_of_atonement_001` 1/5,
`real_covenant_monocovenantal_001` 4/5,
`real_garden_genesis_3_24_misattribution_001` 1/5, `real_singing_psalms_001`.

Five of thirteen questions are flaky at fixed config, which is the pre-existing
measurement-floor problem and is not caused by anything in this arm.

---

## Two decisions — both Chris's, neither mine

I am the party both of these rules blocked, so I am recording the evidence and
declining to relax either one myself.

### Decision 1 — P1: what does a single transport fault do to an arm?

The gate's own wording is *"not comparable against an arm with **different**
expansion health,"* but the rule it enforces demands perfection. Options:

1. **Void and rerun as-is.** No code change; ~1 pair in 7 completes (point
   estimate), and the next attempt is another lottery ticket.
2. **Require matched expansion health across arms** rather than 65/65. Satisfies
   the gate's stated rationale. Against it: it weakens a gate at the request of the
   party it blocked, and it buries the missing-retry defect.
3. **Fix the cause — add a `retry_policy` to the expansion client — then rerun the
   pair.** *My recommendation.* It makes 65/65 actually achievable instead of
   improbable, and it fixes a production path where one truncated body silently
   degrades a real user's retrieval with no notice. Costs: `baml-cli generate` in
   the venv (per `AGENTS.md` §3), and it changes the product under test, so the OFF
   data above is superseded and **both** arms must rerun on the new HEAD. The
   comparison stays valid because the change is identical across arms.

### Decision 2 — P3/P4, still unanswered from the prior turn

Should a **read-fault-only** corpus comparison make an arm uncitable?
`changed_during_run None` → `provisional True` → uncitable, with zero violations,
zero unattributed change, and the verdict re-derivable offline. The transport
produces this on nearly every run, so as written it is a permanent uncitable flag.

My stated preference remains **option 2**: narrow `provisional` to *attributable*
change, and make read-fault-only a named caveat carrying the uuids. Same reasoning
as above — I built this instrument, so I am not the one who should loosen its
verdict.

---

## What this does NOT solve

- **No OFF-vs-ON result exists.** The ON arm has never run. The task is unfinished
  and the blocker is Decision 1.
- **The `other` cause bucket.** An HTTP 404 and a legitimately empty extraction are
  indistinguishable in the counters; attribution here needed the server's stdout,
  which is not an artifact the harness keeps. The `baml_punt:<reason>` split stays
  deferred because `backend/stage_health.py` must be byte-identical across the pair.
- **The missing retry is named, not fixed** — fixing it is Decision 1, option 3.
- **Five of thirteen questions are flaky at fixed config.** Any OFF-vs-ON delta
  smaller than that noise is unreadable, whatever the integrity verdict says.
- **`commit_sha=unknown`** from the server; the HEAD-freeze assertion is unbacked
  on that axis.
- **Product behaviour behind an expansion failure:** the user is told nothing when
  retrieval silently falls back to the raw query.
- **`MINIO_HTTP_ENDPOINT`** still defaults to an in-cluster host, so a local server
  loads zero verses unless the operator knows better, and no route reports the empty
  map.
- **The launcher preflight still lives in `scratchpad/preflight_arm.py`.** `evals/`
  ships only `acceptance_stage_health.py`, whose scope is release wiring — so the
  next person wiring a pair can repeat attempt 1's mistake exactly.
- **The body-corruption root cause is not localised.** The honest next step is a
  packet capture against a known-stable server; it has not been taken.
