# ADR-0009 flag decision — both arms, 28 questions, N=3

> **VOID (2026-10-04)** -- every arm cited in this document ran with the query-expansion
> stage dead: `LITELLM_PROXY_URL` was unset at eval launch. It **is** set in the production API
> pod, so production runs that stage live and none of these arms measures production behavior.
> The numbers below are retired as evidence. Derivation and the full void list:
> [VOID_arms_without_expansion_laneA_20261004.md](VOID_arms_without_expansion_laneA_20261004.md).

Scored against [`PREDICTION_rerun_20260927.md`](../../evals/output/adr0009_flag/PREDICTION_rerun_20260927.md)
(sha16 `caac488609c9b5ba`, verified unedited after the run). Ruling 1, 2026-09-27.

- **Arms:** `off_20260927d` (flag unset) and `on_20260927d` (`GILL_STRUCTURED_ANSWER=1`), both
  `GILL_DISABLE_LM_CACHE=1`, `--runs 3`, warmup on, `debug=True`, server wall 180s.
- **Harness:** `evals/run_eval.py` at `26efb4e`. Tree **clean** at run time, so per ruling 4 these
  results are citable, not provisional.
- **Arm validity, measured not assumed:** 85 requests per arm; `GenerateGillAnswer` fired
  **85/85 on ON and 0/85 on OFF**. The flag really gates the typed path on every request.
  `OptimizeSearchQuery` fired 85 times per arm — one model call per request, independently
  corroborating that the LM cache was off, beyond the endpoint's own self-report.
- **Data integrity:** 0 run-integrity violations, 0 errors, 0 NO-DATA on both arms. One degraded
  run total (`real_election_001` run 2, `llm_timeout`).

## Headline

| | OFF | ON |
|---|---|---|
| Scored / attempted | 28 / 28 | 28 / 28 |
| Passed (representative) | 17 (60.7%) | 15 (53.6%) |
| STABLE-PASS / STABLE-FAIL / FLAKY | 8 / 8 / 12 | 10 / 8 / 10 |
| `must_not_cite` violations | **0** | **0** |
| Refusal correctness | 27 / 28 | **23 / 28** |
| Answer length, median chars | 785 | **1807** |
| Non-empty `zone3_notes` | **0 / 84 runs** | **57 / 84 runs (23 / 28 questions)** |

## Decision: the flag stays OFF

The rule was fixed in advance: flip only if P8 holds, P9 holds, **no STABLE-PASS → STABLE-FAIL
flip**, and the three named failures are no worse. There is exactly one gate flip —
`real_moses_death_001`, "Where did Moses die?" — so the flag stays off. One flip is enough
because its cause is diagnosed and it is not noise.

## Why it flipped: ADR-0009 destroys the informative refusal

Retrieval was **identical** on both arms for that question — 12 citations, `verified: True`.
Only the rendering changed:

- **OFF** — an informative non-answer: names the gap, then surfaces the nearest indexed material
  *with its citation*: *"The nearest indexed material discusses Aaron's death on Mount Hor: 'in
  Mount Hor he died, on the first day of the fifth month' [NUMBERS_33_38_S00]."*
- **ON** — discards that content for a stock template: *"I regret that the provided extracts …
  do not appear to address this specific inquiry."*

This generalizes. Five questions with `expected_behavior: answer` refuse on ON but not OFF, and
**all five retrieved 12 citations on both arms**:

| Question | Category | OFF → ON refused |
|---|---|---|
| `real_moses_death_001` | `biblical_fact` | False → **True** |
| `real_christophanies_001` | `typology_partial_match` | False → **True** |
| `real_imprecatory_psalms_001` | `informative_refusal_corpus_adjacent` | False → **True** |
| `real_universal_atonement_001` | `doctrine_gill_specific` | False → **True** |
| `real_gill_aquinas_001` | `informative_refusal_corpus_adjacent` | True → True (unchanged) |

Two are literally the category ADR-0008 created for this behavior. **This is E-12 restated at a
different layer:** the slots do not carry the behavior. ADR-0009's typed schema has a refusal
variant and a `reasoning` field documented as *"shown to the user on a refusal, so that an opaque
no becomes an actionable starting point"* — and the typed path still produces the opaque no,
because nothing in the schema obliges the refusal variant to carry adjacent retrieved material.
The behavior lived in the free-prose prompt and did not survive the move to fields.

## Scored predictions

| # | Prediction | Outcome |
|---|---|---|
| P1 | Preflight passes, cache reported off | **HELD** both arms |
| P2 | 0 integrity violations, gen ≥ 5s | **HELD** — 0 violations |
| P3 | ≤ 6 degraded runs across 168 | **HELD** — 1 |
| P4 | 0 NO-DATA | **HELD** both arms |
| P5 | OFF passes 12–16 of 28 | **FALSIFIED (just)** — 17 |
| P6 | FLAKY 2–6 questions per arm | **FALSIFIED** — 12 OFF, 10 ON. Instability is far worse than I expected; the old `FLAKY 0` was entirely cache replay |
| P7 | ON−OFF pass delta within ±3 | **HELD** — −2 |
| P8 | Refusals 3/3 both arms | **HELD for the real refusal cases, but the prediction was mis-specified** — see corrections |
| P9 | 0 `must_not_cite` | **HELD** both arms |
| P10 | `stages` present on ≥ 26 ON responses | **HELD** — 28/28 |
| P11 | `zone3_notes` non-empty on 5–15 of 28 | **FALSIFIED ON THE UPSIDE — 23 of 28** |

### P11 is the run's strongest result

57 of 84 ON runs emitted a non-empty `zone3_notes`; 13 questions populated it on all three runs;
OFF produced **zero**, because the field does not exist there. The content is exactly the slant
ADR-0009 predicted the sinkhole would absorb — assertions *about* Gill in the model's own voice:

> *"Gill interprets the scapegoat as a type of Christ, emphasizing its role in bearing the sins of
> the people…"*
>
> *"Gill consistently identifies the 'Logos' with Christ… This aligns with his Calvinist theology."*

Under OFF that material has nowhere to go **but the rendered answer**, which is precisely what
ADR-0008's lexical scan was failing to catch. So the ADR-0009 thesis — give Zone 3 a structural
home and it stops contaminating prose — is **empirically confirmed**, in the same run that says
don't ship it yet. Those are not in tension: the sinkhole works, the refusal path regressed.

## The three named failures, separately

| Question | OFF | ON | Reading |
|---|---|---|---|
| Garden (`real_garden_genesis_3_24_misattribution_001`) | **STABLE-FAIL 0/3** | FLAKY 1/3 | Prediction said STABLE-PASS both arms — **falsified**. The prior "1/1 valid run passed" was a single sample; ON is mildly better |
| covenant "two administrations" (`real_covenant_monocovenantal_001`) | STABLE-PASS 3/3 | FLAKY 2/3 | Predicted FLAKY on at least one arm. Worse on ON, but inside the noise band, not a gate flip |
| eternal justification (`real_eternal_justification_001`) | STABLE-FAIL 0/3 | FLAKY 1/3 | Predicted STABLE-FAIL both arms — **falsified on ON**. Its refusal also became *correct* on ON (it is an `expected_behavior: refuse` question: False → True) |

Net: two of three named failures are **better** on ON, one is worse-but-flaky. The three named
failures are not what blocks the flag; the over-refusal class is.

## Corrections to the locked prediction

Per its own rule, corrections go here, not in the prediction file.

1. **Harness commit moved.** Predicted `fd80ee6`; the run used `26efb4e`, after two harness
   defects found by running it (`e6f9743` run-level 429 abort, `26efb4e` dead-path abort).
2. **P8 mis-specified the refusal set.** It named `real_singing_psalms_001` as a refusal case. It
   is `expected_behavior: answer`. The set has exactly **two** refusal questions:
   `real_esau_pizza_001` (3/3 both arms) and `real_eternal_justification_001` (refusal correct on
   ON, incorrect on OFF). P8 therefore tested the wrong direction: the refusal risk in ADR-0009
   was never under-refusal on refusal questions — it was **over-refusal on answer questions**,
   which P8 could not see by construction.
3. **P11's key and location.** `zone3_notes` is real and implemented, but it goes to
   `structured_payload` → logs/traces, never to the API response. It is measurable only in the
   server log. `zone3_excisions` in the response `stages` is a *different* ADR-0008 field present
   on **both** arms (4 non-empty OFF, 1 ON) and is not ADR-0009's sinkhole. An earlier note in
   this session that the key was "`zone3_excisions` not `zone3_notes`" was wrong.

## Two harness reporting defects found by this run

Neither corrupts data; both are honest-reporting failures of the class this harness exists to prevent.

- **`degraded` is question-scoped but printed as run-scoped.** `Errors (excluded): 0 of which
  degraded: 0` while `real_election_001` run 2 was `DEGRADED (llm_timeout)`. A question that is
  still classifiable never reaches the counter, so run-level degradation is invisible. P3 is
  stated in *runs*, so the summary as printed **could not score my own prediction** — I had to
  grep the log.
- **`flaky_detail` prints under the `partial_detail` heading.** Two loops write into one visual
  list with no second header and no `passed` suffix, so `real_election_001 2/3 runs scoreable`
  and `real_election_001 1/2` read as a self-contradiction. Both statements are true and about
  different quantities.

## What this does NOT solve

- It does not say ADR-0009 is wrong. The sinkhole works (P11) and schema validity was never in
  doubt (E-12, 120/120). What fails is the **refusal branch**, and that is a fixable
  `@description` problem in the refusal variant — the E-12 lesson applied where it wasn't yet.
- It does not measure answer quality. ON answers are 2.3× longer with no markdown sections; no
  gate here reads whether that is better or worse prose, and the citation gates both passed.
- It does not explain the 10–12 FLAKY questions. A 36–43% flake rate is now the dominant source
  of uncertainty in this eval and it is **not** an ADR-0009 property — OFF is worse. Any future
  gate on this set is weak until that is understood. N=3 is too few to characterize it.
- `partial_match_sids` is empty on 28/28 in **both** arms. The channel exists and nothing fills
  it — the "represent nothing here" failure mode, unexamined, and plausibly related to the
  over-refusal class.
- Generation is OpenRouter DeepSeek, not a local GPU; no endpoint-D assignment applies, and these
  numbers cannot be compared to a locally-generated run.
- One degraded run means `real_election_001` is classified over 2 samples, not 3.

## Recommended next step

Do **not** flip the flag. Fix the refusal variant's `@description` so a refusal must carry the
nearest adjacent retrieved material and its citation when retrieval returned any, then rerun both
arms. Gate on the five over-refusals, not on the pass total. A prompt edit on the refusal path can
regress the answer path, so the rerun must be both arms and full-width, not a spot check on the five.
