# Prediction — OFF vs ON, with query expansion LIVE and the answer provider PINNED

**Locked 2026-10-04, before the first scored request.** Answers the standing instruction: *"Pin the
answer-LM provider on OpenRouter and record it per call; it's the remaining churn source. Then OFF
vs ON at t=0, N=5, flip gate, predict first."*

**Correction, same day, before any run.** The first commit of this document said the run was
blocked on a local Weaviate and a port conflict. That was wrong, and wrong in an avoidable way: I
probed `localhost:8080` and reasoned from a dead local service, without checking what the previous
arms actually addressed. They used the **gya-test Weaviate at `192.168.1.54:80`**, recorded in the
handoff for the floor pair itself. It is up, and it holds the same corpus. **Nothing is blocked.**
The port conflict on `localhost:8080` is real and irrelevant — no arm here uses it. No number had
been seen when this correction was made; the predictions below are unchanged from the locked commit,
and the configuration table gained the rows it should have had from the start.

This pair is the first measurement in this lane taken with the query-expansion stage alive. Every
previous arm is void (`VOID_arms_without_expansion_laneA_20261004.md`), so **this pair re-measures
the floor as well as the flag.**

## Why the level is deliberately NOT predicted

There is no usable prior. 55/78, 63/78, the 8-of-78 floor and the 14-of-78 null were all measured
with expansion dead and a `dedup_only` fallback standing in for it, and they are retired. Inventing
a band from a retired number is the move the void ruling exists to stop.

So the locked predictions below are about **structure, health, recording and the decision gate** —
things whose correct values follow from the code and the configuration. The pooled **level** is
unpredicted, named as unpredicted, and will be reported as a new measurement, scored against
nothing.

With expansion live, three things happen in this lane for the first time: `search_text` exists, so
the **second-pass entity lookup executes** (`backend/main.py:585`); the BAML entity path and its
boost telemetry activate; and the embedding input can differ from the raw query. Any of those can
move retrieval. The direction is unknown and I am not guessing at it.

## Configuration, identical in both arms except the flag

| setting | value |
| --- | --- |
| `LITELLM_PROXY_URL` | `http://localhost:4000` — **set on the server process at launch**, `.env` untouched |
| `OPENROUTER_PROVIDER_ORDER` | `streamlake` (`allow_fallbacks: False`, via `degradation.provider_pin`) |
| `GILL_ANSWER_TEMPERATURE` | `0.0` |
| `GILL_DISABLE_LM_CACHE` | `1` |
| `RATE_LIMIT` | `100000/day` |
| `GILL_STRUCTURED_ANSWER` | **OFF** in arm 1, **ON** in arm 2 — the only difference |
| `--runs` | 5 (so 65 scored runs per arm over 13 questions) |
| `--timeout` | 200 |
| `WEAVIATE_URL` | `192.168.1.54:80` — the **gya-test** instance, the same one the floor pair used |
| corpus | verified 2026-10-04: Weaviate **1.38.1**, `CommentaryChunk` **7294**, `TheologicalEntity` **8433** — identical to the counts the handoff recorded for the floor pair, so the corpus is not a variable between that pair and this one |
| LiteLLM proxy | `localhost:4000`, model list `local-router` + `qwen3-embedding` (gya-test). Embedding traffic goes through the proxy own model_list, which is the pre-existing sanctioned path; nothing here addresses a GPU host directly |
| HEAD | clean and committed before the first request; `integrity.git.git_dirty` must read clean in both |

Question set, the same 13 stochastic ids as the void floor pair: `scapegoat_001`,
`real_imprecatory_psalms_001`, `sheep_001`, `real_covenant_grace_001`,
`real_covenant_monocovenantal_001`, `real_garden_genesis_3_24_misattribution_001`,
`day_of_atonement_001`, `real_singing_psalms_001`, `simons_count_001`, `john_baptist_001`,
`real_christophanies_001`, `real_election_001`, `real_ishmael_circumcision_001`.

**Why StreamLake:** measured 2026-09-27 from OpenRouter endpoint metadata, recorded in
`backend/degradation.py` — StreamLake ctx 128000, quant unknown, status 0, uptime 99.5%; DeepInfra
ctx 163840, quant **fp4**, status -2, uptime 94.4%. A deranked fp4 endpoint is the one to exclude.
**That choice is not itself measured.** Nothing here compares providers; the pin only stops them
mixing, which is the fault found in the floor arms (DeepInfra 61 / StreamLake 17, `violations: []`).

The server is restarted between arms — the flag and the pin are read at process start — so this
pair is cross-process, as the floor pair was.

## Locked predictions, with the exact field each is read from

Eval-side paths are in the arm `summary.json`. The server-side path is the `/health/stages`
snapshot (release 0.3.2), read on the warmup and again after each arm.

| # | prediction | read from | falsifier |
| --- | --- | --- | --- |
| P1 | `errored == 0`, `healthy == 65`, `distinct_fallback == ["<none>"]` in **both** arms | `summary.integrity.stage_health.expansion` | any expansion error — **the pair is void, not failed**: relaunch, do not analyse |
| P2 | server-side `expansion.errored == 0` and `causes == {}` after each arm | `/health/stages` `expansion` | a non-empty `causes` — same void rule; this is the independent witness for P1 |
| P3 | `runs_pin_honored_false == 0` **and** `runs_pin_unchecked == 0` in both arms | `summary.answer_lm` | either non-zero. `runs_pin_unchecked` is the one the floor arms could not fail: unpinned, it was every run, and silent |
| P4 | `distinct_provider_served == ["StreamLake"]` — length exactly 1 — and **no** mixture violation | `summary.answer_lm` | a second served provider, or length 0 (nothing recorded) |
| P5 | `runs[].provider_served` non-null on all 130 runs | arm `runs[]` entries | any null → provider attribution is unavailable and the arm cannot be cited for provider claims, by the rule that voided the fourteen |
| P6 | `distinct == [0.0]`, `runs_explicit == 65`, `runs_absent == 0`, `runs_unrecorded == 0` in both arms | `summary.integrity.answer_temperature` | anything else |
| P7 | `violations == []` in both arms | `summary.integrity.violations` | any violation. First time an empty list asserts something: the expansion, temperature, pin and new mixture gates can all fire now |
| P8 | `entity_lookup.distinct_mode == ["full"]` in both arms | `summary.integrity.stage_health` | a non-`full` mode → the second-pass vector tier flaked. The pair stays readable; the manifest claim does not. Note `full` means "the tier did not raise", **not** "the manifest was stable" |
| P9 | **The decision gate: 0 STABLE-PASS ↔ STABLE-FAIL flips** in either direction | per-question verdicts across the two arms | 1+ flip. A flip either way means the flag moves a question that was stable, and the flag stays OFF |
| P10 | **pooled gap between the arms is 4 or fewer of 65** | pooled scores | a gap of 5+ |
| P11 | **total absolute per-question movement is 5–16 of 65**, and no single question moves more than 3 of 5 | per-question pass counts across the arms | movement under 5 (suspiciously still — look for a cache or a replay before believing it) or over 16 (the null widened; see below) |

**Where 65 appears above it means "every scored run".** `stage_health` and
`answer_temperature` count scored runs only, so an errored or degraded run lowers
`scored_runs` rather than creating a gap. The literal check is `healthy == scored_runs` and
`runs_explicit == scored_runs`; 65 is the value when nothing errors, which is itself expected
but not predicted — a transport error is not a measurement failure.

**P9, P10 and P11 are the only predictions about the flag.** P1–P8 are health and recording gates:
they say whether the pair is a measurement at all.

**Grounding for P10 and P11, and why it is borrowed.** The two same-config null pairs on this same
13-question set each had a **pooled gap of 0**, with **8 of 78** and **14 of 78** total absolute
per-question movement and no question moving more than 2 of 6
(`RESULT_off_vs_off_floor_laneA_20260928.md`). Those arms ran at N=6, so 78 scales to 65 as roughly
6.7 and 11.7 — hence the 5–16 band, widened at the top rather than centred, and a per-question cap
of 3 of 5 rather than 2.

**Those arms are void**, and the borrowing has to be named for what it is. What survives the void is
narrow: the churn *magnitude* is a property of answer-LM stochasticity, which the dead expansion
stage did not touch. What does not survive is the assumption that it is the same magnitude here,
because with expansion live a second stochastic input (`search_text`) now feeds retrieval. So
**movement may legitimately exceed 16 for reasons that have nothing to do with the flag.**

That is why pooled gap and movement are separate predictions. Pooled totals were the stable
statistic in both nulls (gap 0 twice) while per-question verdicts churned by 8 and 14; a single
number hiding both would be unfalsifiable. If P11 breaks while P10 holds, the honest reading is
**the null widened under live expansion**, not that the flag did something — and settling that needs
a same-config null pair at this configuration, which this pair does not include. Noting it here, in
advance, so that reading cannot be invented afterwards.

## The decision rule, stated before the numbers exist

- **Flag stays OFF** unless ON is at least as good as OFF on **every** question *and* P9 holds. A
  pooled improvement with one stable-question flip is a trade, not an improvement.
- **Any P1 or P2 failure voids the pair.** It does not get analysed with a caveat; it gets
  relaunched. That is the whole lesson of the fourteen void arms.
- **A pooled gap inside P10's band is "no effect measured", never "ON is better."**
- **A void or inconclusive pair does not promote the flag either way.** OFF stays the default by
  conservatism, exactly as it does today.

## What a result here can and cannot say

It can say: whether expansion is alive, whether the pin holds, what the pooled level is *with
expansion live*, and whether the typed-answer flag moves any question off a stable verdict.

It cannot say: that the flag is safe (one pair, 13 questions, one provider, one process each); that
the level is comparable to any published number (none of them is); that the provider choice was
right (unmeasured, deliberately); or that the second-pass entity manifest is stable — it is a
function of `(search_text, corpus)` and `search_text` is stochastic LM output, so variation there is
expected and is **not** a regression of `5c93b28`.

## Launch (blocked at lock time — see below)

```bash
# server, per arm; the flag and the pin are read at process start
LITELLM_PROXY_URL=http://localhost:4000 \
OPENROUTER_PROVIDER_ORDER=streamlake \
GILL_ANSWER_TEMPERATURE=0.0 GILL_DISABLE_LM_CACHE=1 RATE_LIMIT=100000/day \
GILL_STRUCTURED_ANSWER=0 \
  python -m uvicorn backend.main:app --port 8000

# preflight, BEFORE any scored question: expansion alive, recorder wired
python evals/acceptance_stage_health.py --base-url http://localhost:8000 --probe-search

# arm
python evals/run_eval.py --endpoint http://localhost:8000/api/search --runs 5 \
  --timeout 200 --output-dir evals/output/off_vs_on_20261004/off --ids <the 13 ids>
```

## Preconditions, verified 2026-10-04 before locking

| precondition | state |
| --- | --- |
| gya-test Weaviate `192.168.1.54:80` | **UP**, `/v1/meta` 200, version 1.38.1 |
| corpus counts | **7294 / 8433**, matching the floor pair exactly |
| LiteLLM proxy `localhost:4000` | **UP**, `/health/liveliness` 200, 2 models |
| Ollama `localhost:11434` | UP (not on this path; embedding goes through the proxy) |
| `localhost:8080` | held by an unrelated container and **not used by this run** |

The only thing left before the first request is launching the two servers with the environment in
the table above, and confirming on the warmup that `/health/stages` reports `expansion.errored == 0`
with empty `causes`. **If the warmup shows an expansion error, no scored question is sent** — that
is P1 and P2 acting as a preflight rather than a post-mortem, which is the one procedural change
this whole void episode earns.

If the configuration at launch differs from the table above in any row, **this document is void and
a new one is locked.** A prediction edited to match its run is not a prediction.
