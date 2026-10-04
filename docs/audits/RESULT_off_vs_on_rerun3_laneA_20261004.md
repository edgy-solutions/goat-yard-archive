# RESULT — OFF vs ON pair (attempt 5), Lane A, 2026-10-04

Prediction: [`PREDICTION_off_vs_on_rerun3_laneA_20261004.md`](PREDICTION_off_vs_on_rerun3_laneA_20261004.md),
committed in `f06b250` **before** launch.

Output: `evals/output/off_vs_on_rerun3_20261004/{off,on}`. Pair start 2026-10-04T21:32:04Z.
OFF 16:32:45–17:00:38 (27.9 min). ON 17:01:37–17:34:50 (33.2 min).

**Commit, stated precisely.** The code under test is `4702459`. HEAD at all four samples is
`f06b250`, which is `4702459` plus the prediction document and nothing else. The prediction's own
P9 wording ("`4702459` throughout") was stale the moment it was committed, because committing a
prediction necessarily moves HEAD. The substantive claim — HEAD frozen and identical at both ends
of both arms, tree clean — holds.

## Headline

**Both arms ran to completion and exited 0. That is the first time in five attempts.** The
recording fix did exactly what it was built to do.

**And there is still no citable OFF-vs-ON effect, for two reasons that have nothing to do with
each other:**

1. **Both arms are `provisional: true` on the corpus axis — on a stated cause that is false.** The
   record says the re-read difference is "evidence of a real write, not a bad read." I checked, and
   **no write happened.** Details below; this is a defect in the verdict, not in the corpus.
2. **The headline pass metric is a one-run-per-question statistic**, and on the honest run-level
   metric the **same-configuration null (−7 runs) is larger than the OFF-vs-ON difference (−4
   runs)**. The effect is smaller than the instrument's own replicate noise.

So: the pipeline is fixed, the experiment ran clean, and the experiment as designed cannot resolve
the question it was built to answer.

## Validity

| | OFF | ON |
|---|---|---|
| `run_eval` exit | **0** | **0** |
| preflight / postflight | PASS / PASS | PASS / PASS |
| `integrity.violations` | `[]` | `[]` |
| `expansion` | `ok 67, errored 0, fallbacks {}` | `ok 67, errored 0, fallbacks {}` |
| `expansion.retries` | `total 0, bound_exhausted 0, unobserved 0` | same |
| `entity_lookup` | `full` only | `full` only |
| runs | 65 total / 65 scored / 0 degraded / 0 errored | same |
| git axis | `changed_during_run False`, clean both ends, `f06b250` ×4 | same |
| corpus axis | **`provisional True`**, re-read `differs` (1 object) | **`provisional True`**, re-read `differs` (3 of 4) |
| answer LM | 65 runs, 1 config | 65 runs, 1 config |

`ok 67` is the per-process cumulative counter: 65 scored + warmup + the preflight probe.

**The retry again never fired** (`total 0`, both arms). Two clean pairs in a row is not evidence
the bounded retry rescues a truncated body; it is still verified only by its born test.

## P3 — the fix, confirmed at the layer where it lands

The ON arm's answer-LM table is **one configuration across all 65 scored runs**:

> `path=baml  client=GillAnswerLM  model_returned=deepseek/deepseek-chat  temperature_on_the_wire=0
>  provider_served=StreamLake  provider_served_source=openrouter_response_body  pin_honored=True`
>
> `scored_runs_with_a_record=65  questions_missing_a_record=[]  distinct=1
>  runs_pin_honored_false=0  runs_pin_unchecked=0`

Zero runs with no recorded temperature, in either arm. No `unavailable:` source appeared, so the
resolver's backstop branch never fired — as predicted. OFF is the unchanged mirror image:
`path=dspy client=dspy.LM temp=0.0 source=dspy_response_attribute`, 65 runs, one config.

The wire temperature is `0` in ON and `0.0` in OFF. Same value; the type differs because the two
recorders read it from different places (the OpenRouter response body vs the DSPy response
attribute). Not a configuration difference, and named here so nobody later reads it as one.

**P3 PASS.** The attribution defect that refused attempt 4 is fixed and the fix is confirmed on 65
live runs.

## P5 — FAIL, and this is the honest limit on the fix

**Zero verification-failure runs in either arm.** The branch the fix exists for — a structured-path
early return that drops the record — **was never taken in this pair.** Attempt 4 hit it twice; this
pair hit it zero times.

So what is confirmed is that the *normal* structured path attributes correctly, 65 for 65. What is
**not** confirmed in flight is the refusal branch itself. Its correctness still rests on the source
check, the code reading (`answer_lm` is bound at `bot.py:1047` and filled from the Collector at
`:1049`, before all three returns), and the born tests — the same standing as the bounded retry.
`bot.py:1185` and `:1202` remain unexercised too.

A clean pair is not proof the fix works on the path that broke. P5 was written to force that
sentence and it did its job.

## The corpus verdict is wrong, and here is the proof

Both arms were marked provisional because the post-run re-read of the read-faulted objects
*differed* from the start sample. The record's explanation:

> `1 re-read object(s) do NOT match the start sample (56c66e4e…) -- that is evidence of a real
> write, not a bad read; this arm stays provisional`

**The same record contradicts itself about the same object.** Its start-vs-end comparator says:

> `not-compared: 1 objects differ only by digest while their last_update_ms is identical, which is
> a bad read, not a corpus change; 56c66e4e…`

I discriminated with the source's own `_lastUpdateTimeUnix`, read live, three independent repeats
per object, for all five faulted uuids (1 in OFF, 4 in ON):

| uuid | arm | fields that differ from `at_start` | `last_update_ms` across baseline + 3 repeats |
|---|---|---|---|
| `56c66e4e` | OFF | `vec` (all 3 repeats) | `1777230822952` — unchanged |
| `0fe2e11b` | ON | `vec` (all 3) | `1779673650969` — unchanged |
| `7e96223c` | ON | `vec` (all 3) | `1777228590090` — unchanged |
| `ce3c44ce` | ON | `vec` (all 3) | `1777234806942` — unchanged |
| `4e8f7075` | ON | **nothing** | `1777234910989` — unchanged |

**No write happened.** `last_update_ms` held still on every object across the stored baseline and
three live reads. The newest of those timestamps is 2026-04-26 and the newest seen anywhere in the
probe is 2026-05-25 — over four months before this run. The "real write" claim is false for all
five objects.

Two further points, because the direction of the fault matters:

- The three live repeats **agree with each other** and differ from the stored sample. So it is the
  `at_start` vector read that was corrupt, not the re-read. The arm's `vector_sha256` at start is a
  digest over corrupted bytes.
- `dim` is 4096 in both the baseline and every repeat. This corruption does **not** show up as an
  anomalous vector length, unlike the 4094/4097/4099 cases in the ledger. A length check would not
  have caught it.
- `4e8f7075` matched exactly on all four fields. That is the companion assertion: the probe is not
  systematically skewed, or that object would have differed too.

**Cause, in code.** `evals/corpus_state.py:265-271` (`reread_verdict`) compares
`REREAD_COMPARE_FIELDS = ("text","vec","dim","last_update_ms")` and attributes **any** difference
to a write. The start/end path (`_attributable_classification`, `corpus_state.py:343-352`) already
applies the discriminator — digest moved while `last_update_ms` held still ⇒ bad read, not a
change — and the re-read path simply does not. One module holds both the right rule and the wrong
one, applied on two axes.

**Consequence.** Two arms that ran clean were labelled provisional on a false causal claim. Under
the standing rule a provisional arm "may withdraw an earlier claim but asserts nothing new, and
cannot be cited in an ADR or a tier change."

**What I am not doing about it.** Ruling 2 says read-faulted uuids "must match the start sample;
otherwise provisional," and that a differing re-read keeps the arm provisional. The code implements
that ruling faithfully. I am not relaxing the gate on my own, and there is a real argument for
keeping it strict: the at_start vector digest *is* demonstrably corrupt for these objects, so the
"corpus held still" claim for the run is genuinely weaker, even though nothing was written. What I
will fix is the false cause — the verdict should name a digest-only difference with a static
`last_update_ms` as a bad read in one of the two samples, which is a different finding from a
write, and remain non-confirming either way. **Whether that case should still make an arm
provisional is Chris's call, not mine.**

### A second, smaller gate defect

Exit 0 with `violations []` while `provisional: true`. The console text in that branch is also
mismatched to the condition — it printed, in both arms:

> `Corpus state was NOT established at both ends:  / `

with both reason strings empty, because that branch is written for *unreadable* samples and both
samples read fine (`available: true`, `unavailable_reason: null`). The git axis prints a loud
`*** THIS RUN IS PROVISIONAL ***` block; the corpus axis does not. So an exit 0 does not mean
citable, and the output does not say which one you have. Asking what a PASS asserts: here it
asserts no violation, not citability.

## The headline metric discards four fifths of the runs

`summary.passed` counts the questions whose **first run** passed (`score.overall_pass` on run 1).
It is 9/13 for OFF and 8/13 for ON — computed from 13 of the 65 runs in each arm, on a suite where
8 of 13 questions are flaky. The attempt-4 "12/13" was the same statistic.

On the run-level metric, using all 65:

| | first-run metric | run passes |
|---|---|---|
| attempt 4 OFF | 12/13 | **49/65 (75.4%)** |
| attempt 5 OFF | 9/13 | **42/65 (64.6%)** |
| attempt 5 ON | 8/13 | **38/65 (58.5%)** |

## The null is larger than the effect

| comparison | net | sum \|Δ\| | questions moved |
|---|---|---|---|
| **NULL** — OFF attempt 4 vs OFF attempt 5 (same configuration) | **−7 runs** | 11 | 7 of 13 |
| **EFFECT** — OFF vs ON, attempt 5 (same commit, same hour) | **−4 runs** | 24 | 12 of 13 |

The same configuration, re-run, moved 7 runs out of 65. The flag moved 4. **The effect is smaller
than the instrument's replicate noise**, and one null replicate understates that noise. P7
predicted the totals would be unreadable; they are.

Per question, runs passed out of 5:

| question | OFF | ON | Δ |
|---|---|---|---|
| `john_baptist_001` | 1 | 5 | **+4** |
| `real_covenant_monocovenantal_001` | 2 | 5 | +3 |
| `real_singing_psalms_001` | 3 | 5 | +2 |
| `sheep_001` | 3 | 4 | +1 |
| `real_ishmael_circumcision_001` | 5 | 5 | 0 |
| `real_christophanies_001` | 5 | 4 | −1 |
| `real_garden_genesis_3_24_misattribution_001` | 1 | 0 | −1 |
| `real_imprecatory_psalms_001` | 4 | 3 | −1 |
| `simons_count_001` | 1 | 0 | −1 |
| `day_of_atonement_001` | 2 | 0 | −2 |
| `real_covenant_grace_001` | 5 | 3 | −2 |
| `scapegoat_001` | 5 | 3 | −2 |
| `real_election_001` | 5 | 1 | **−4** |

Stability: OFF `stable_pass 5, flaky 8, stable_fail 0`; ON `stable_pass 4, flaky 6, stable_fail 3`.
The ON arm's three stable-fails (`day_of_atonement`, `garden`, `simons`) are the same low tail that
scores 2/5, 1/5 and 1/5 in OFF — the tail reaching zero, not three new failures.

**One hypothesis worth naming, and not claiming.** The flag's net effect (−4) is small while its
per-question churn (24) is more than twice the null's (11), with large offsetting swings:
`john_baptist` +4 against `real_election` −4. That pattern would be consistent with the flag
changing *which* questions pass rather than *how many*. At n=5 runs, one null replicate, and 13
questions, it is a hypothesis, not a result. Testing it needs a paired design with more runs per
question — not another attempt at this one.

## Prediction scored

| | predicted | observed | verdict |
|---|---|---|---|
| P1 | `errored 0`, no fallbacks, `entity_lookup full`, both arms | exactly that | **PASS** |
| P2 | `bound_exhausted 0`, `unobserved 0`, `total` 0–4 | `0/0/0` | **PASS** (bottom of band; never needed) |
| P3 | ON: one config, 65 runs, no missing temperature, no `unavailable:` | exactly that | **PASS** |
| P4 | exit 0 on both arms, `violations []` | exit 0 and `[]` on both | **PASS** |
| P5 | ≥1 verification-failure run, each with a full record | **0 such runs** | **FAIL** — the fix is unexercised in flight |
| P6 | OFF in 11–13 (first-run metric) | **9** | **FAIL** — band built on a single prior; replicate noise is ±3 |
| P7 | `\|ON − OFF\| ≤ 3` is noise; report per-question | gap 1; null (7) > effect (4) | **PASS**, and more strongly than written |
| P8 | `flaky ≥ 3` per arm | OFF 8, ON 6 | **PASS** |
| P9 | git clean and frozen; corpus re-read **confirmed**, non-provisional | git PASS; **corpus provisional on both arms** | **FAIL on the corpus half** |

P6's failure is instructive about prediction, not about the product: I built an 11–13 band from one
prior observation (12) when the arm's own replicate spread is ±3 on that metric. The prior was a
draw from a wide distribution and I treated it as a point.

P9's corpus half failed for a reason the prediction did anticipate as a falsifier — "a re-read that
differs" — but I wrote that falsifier expecting it to mean a real write. It meant a wrong verdict.

## What this result does NOT establish

- **Nothing about ADR-0009's merits.** Both arms are provisional, so neither is citable in an ADR;
  and even if they were, the effect is inside the null.
- **Nothing about the refusal branch in flight.** Zero verification-failure runs. See P5.
- **Nothing about the bounded retry in flight.** `total 0` for the second pair running.
- **Nothing about the truncation's root cause.** Still unlocalised; no packet capture taken.
- **Nothing about why the vector read corrupts.** Five objects, silent, at correct `dim`, stable
  across three repeats of the *live* read — so the corruption is in the fingerprint read path, not
  randomly distributed per read. That is a new and unexplained observation, not a diagnosis.
- **Whether a digest-only difference with a static `last_update_ms` should keep an arm
  provisional.** Ruling 2's letter says yes. That is Chris's call and I have not changed it.
- **`commit_sha=unknown`** from the server in both arms, so the launcher's HEAD-freeze assertion
  remains the only guard that the running code is the code at HEAD.
- **The launcher** still lives in the session scratchpad rather than `evals/`.

## Open decisions

1. **The provisional rule for digest-only re-read differences.** Keep it strict (current
   behaviour), or treat a static `last_update_ms` as confirming that nothing was written and leave
   the arm citable with a named caveat? I lean strict, because the start sample's vector digest is
   genuinely corrupt, but the call is Chris's.
2. **The headline metric.** `summary.passed` reporting one run of five on a suite that is 60%
   flaky invites exactly the misreading that produced the "12 → 9 regression" scare. Replacing it
   with the run-level rate is a one-line change to the reporter plus every doc that quotes the old
   number.
3. **Experiment design.** Resolving a 4-run effect against a 7-run null needs more runs per
   question and a paired per-question test, not a sixth attempt at 5×13.
