# Result — the OFF-vs-OFF floor after the entity-lookup fix

> **VOID (2026-10-04)** -- every arm cited in this document ran with the query-expansion
> stage dead: `LITELLM_PROXY_URL` was unset at eval launch. It **is** set in the production API
> pod, so production runs that stage live and none of these arms measures production behavior.
> The numbers below are retired as evidence. Derivation and the full void list:
> [VOID_arms_without_expansion_laneA_20261004.md](VOID_arms_without_expansion_laneA_20261004.md).

**Lane A, 2026-09-28.** Scored against
[`PREDICTION_off_vs_off_floor_laneA_20260928.md`](PREDICTION_off_vs_off_floor_laneA_20260928.md),
locked and committed at `6f70692` before the first scored request.

HEAD was `6f70692`, **clean at the start and end of both arms**, and nothing was committed between
arm A's first request and arm B's last. Both arms: `GILL_STRUCTURED_ANSWER` OFF,
`GILL_ANSWER_TEMPERATURE=0.0`, `GILL_DISABLE_LM_CACHE=1`, `--runs 6`, `--timeout 200`, the same 13
stochastic questions. **Cross-process by design** — the server was killed and restarted between
arms, with `PYTHONHASHSEED=1` for arm A and `3` for arm B, the two seeds that pre-fix produced the
bad and the good candidate order (0/10 and 10/10 on the scapegoat manifest).

## The new floor

| statistic | value | prior null (2026-09-27, same-config pair) |
| --- | --- | --- |
| pooled arm A | **63/78** | 55/78 |
| pooled arm B | **63/78** | 55/78 |
| pooled gap | **0** | 0 |
| total absolute per-question movement | **8 of 78** | 14 of 78 |
| questions moving 3+ of 6 | **0** | 2 |
| STABLE-PASS <-> STABLE-FAIL flips | **0** | 0 |
| STABLE-FAIL questions | **0 in both arms** | — |

Per question:

| question | A | B | move |
| --- | --- | --- | --- |
| `scapegoat_001` | 3 | 5 | 2 |
| `real_imprecatory_psalms_001` | 3 | 5 | 2 |
| `sheep_001` | 6 | 4 | 2 |
| `real_covenant_grace_001` | 6 | 5 | 1 |
| `real_covenant_monocovenantal_001` | 6 | 5 | 1 |
| `real_garden_genesis_3_24_misattribution_001` | 1 | 1 | . |
| `day_of_atonement_001` | 4 | 4 | . |
| `real_singing_psalms_001` | 5 | 5 | . |
| `simons_count_001` | 5 | 5 | . |
| `john_baptist_001`, `real_christophanies_001`, `real_election_001`, `real_ishmael_circumcision_001` | 6 | 6 | . |

**The floor on a cross-process pair is 8 of 78 total movement, no question moving more than 2 of
6, pooled totals identical.** That is the number to read future deltas against, and it is tighter
than the only prior null (14 of 78, two questions moving 3+).

It does **not** follow that the fix bought the difference. The prediction document said this in
advance: the 55/78 arms ran before the fix, under unrecorded process conditions and a different
temperature setting. A same-config pair measures a floor; it does not attribute a delta.

## Predictions: 7 held, 1 falsified

| # | prediction | verdict | measured |
| --- | --- | --- | --- |
| P1 | `scapegoat_001` 6/6 in both arms | **FALSIFIED** | 3/6 and 5/6 |
| P2 | pooled per arm in 57–66 | HELD | 63 and 63 |
| P3 | pooled totals within 4 | HELD | gap 0 |
| P4 | movement 6–18 of 78 | HELD | 8 |
| P5 | at most 1 SP<->SF flip, not `scapegoat_001` | HELD | 0 |
| P6 | `stage_health` present, `expansion.errored > 0` both, violation present, neither arm clean | HELD | 78/78 errored in both; violation recorded in both |
| P7 | `entity_lookup.distinct_mode == ["full"]` | HELD | `{"full": 78}` in both |
| P8 | expansion violation, no temperature violation | HELD | exactly one violation per arm |

`answer_temperature` in both arms: `{"distinct": [0.0], "runs_explicit": 78, "runs_absent": 0,
"runs_unrecorded": 0}`.

## P1 is the finding, not the footnote

**The manifest is deterministic and `scapegoat_001` still moved.** `available_entities` is the
fixed set in every run of both arms — `['antitypical scape-goat', 'scape-goat', 'spiritual Israel
of God', 'spiritual reign of Christ', 'spiritual seed']` — exactly the manifest the 70/70 live
probe predicted, in a process seeded to produce the *bad* order pre-fix. The lookup is doing what
`5c93b28` claims. The question still scored 3/6 and 5/6.

So the entity manifest was **not the only thing moving that question**, and the earlier inference
that it was would have been a fourth wrong causal story. What did change is the **failure mode**:

- pre-fix failures: `must_cite_missing: ['LEVITICUS_16_21_S0', 'LEVITICUS_16_22_S0']`, a
  no-extracts answer — Leviticus 16 never reached the answer LM at all.
- post-fix, the stored failing response: `must_cite_missing: ['LEVITICUS_16_21_S0']`,
  `must_cite_recall: 0.5` — Leviticus 16 **is** in evidence; one of the two required sentences was
  cited and the other was not.

Retrieval reaches the material every time now; what moves is which sentence-level chunk the answer
cites. That is a generation/citation-boundary behavior, and the live suspects are the answer LM at
temperature 0 with an **UNPINNED** provider (`deepseek-chat` is served at different quantizations —
the harness prints this warning every run) and the verbatim-verification boundary. This is the next
thing to instrument, not the next thing to guess about.

## A reading rule that comes out of this pair

**Counting STABLE-PASS questions is a much noisier statistic than the pooled total.** These two
arms have identical pooled totals and 8 points of movement, yet the class counts read
`SP=7 / FLAKY=6` and `SP=4 / FLAKY=9`. Three questions left STABLE-PASS on a 1-or-2 point move and
none entered. A one-run change reclassifies, because STABLE-PASS requires 6/6 exactly.

The existing gate — STABLE-PASS <-> **STABLE-FAIL** flips — is unaffected, because STABLE-FAIL
requires 0/6, which nothing hit. But "the STABLE-PASS count went down" must never be read as a
regression signal. It is inside this floor.

## What this does NOT solve

- **Both arms are formally not clean, and that is correct.** 78/78 scored runs in each arm had a
  BAML query-expansion error, fallback `dedup_only`. The pair is internally valid (both arms carry
  the fault identically) but it cannot be compared against any arm with different expansion health.
- **The expansion fault is now diagnosed, and it is not a dead dependency.** The new preflight
  warning named it on the warmup, before any scored question: `LLM client 'LocalRouter' requires
  environment variable 'LITELLM_PROXY_URL' to be set but it is not`. The LiteLLM proxy is **up** on
  `localhost:4000` and lists both `qwen3-embedding` and `local-router`; the variable simply is not
  exported to the server process. It was left unset here on purpose — the prediction was locked
  stating it unset, and changing the configuration to defeat a locked prediction is not a
  measurement. Setting it is a one-line change to how the server is launched and should be the
  first thing done before the next arm pair. `.env` was not touched.
- **The provider is UNPINNED in both arms.** `OPENROUTER_PROVIDER_ORDER` is not set, so
  `deepseek-chat` may be served at different quantizations within and between arms. It is a churn
  source inside this floor and it is not separated from it.
- **This floor is for the 13 stochastic questions only.** The other 15 were not run.
- **Per-run answers are still not persisted** — only `answer_sha16`, length, and now the stage
  flags. The must_cite analysis above is from the single stored representative response per
  question, so "which sentence was cited" is known for one run, not six.
- **No claim is made for the temperature pin.** It stays; nothing here measures it.
- **Nothing here says the fix improved the eval.** It says the fix holds (P7, and the manifest in
  every run) and that the floor is 8 of 78. Arms published before today remain unusable as
  controls.

## Artifacts

- `evals/output/floor_20260928/armA/`, `.../armB/` (worktree-local; `evals/output` is gitignored —
  summaries published to the private repo).
- Fix and diagnosis: `docs/audits/RESULT_entity_lookup_determinism_laneA_20260928.md`.
- Locked prediction: `docs/audits/PREDICTION_off_vs_off_floor_laneA_20260928.md`.
