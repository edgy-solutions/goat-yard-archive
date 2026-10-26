# Results -- paired `GILL_STRUCTURED_ANSWER` gate run

Pre-registration: `GATE_RUN_LOCK_structured_answer_laneA_20261025.md`. Every
prediction and the decision rule were fixed in that file before any arm ran.
This file reports what came back. Nothing here amends a prediction.

Run date: 2026-10-26. Target gya-test only. Image digest
`sha256:2fce1e34...b11433` on all arms, asserted per arm on the pod.

## Scorecard against the locked predictions

| # | prediction | outcome |
|---|---|---|
| 1 | null not silent, 2-6 stable flips | **HOLDS**, at the bottom: 2 |
| 2 | effect lands inside the null band | **HOLDS**: 2 flips vs band of 2 |
| 3 | zero `must_not_cite` under ON | **HOLDS** (last-draw fidelity) |
| 4 | discard branch on >half the set | **FALSIFIED**: 5/28 and 4/28 (~16%) |
| 5 | same branch population both arms | **HOLDS**: differs by 1 id, = null's own |

**Decision: PASS by the pre-registered rule.** Zero STABLE-PASS ->
STABLE-FAIL flips, zero `must_not_cite` violations under ON.

**The flag is not shown to improve anything.** The +2 STABLE-PASS headline
decomposes entirely into A3 being the low arm on two questions that move
between identical OFF arms. See Part 3.

---

## Part 1 -- THE MEASURED NULL (reported before the effect pair ran)

Two arms at the **same** flag value (`0`), each a fresh pod boot, 28 questions
x 3 draws. Whatever they differ by is noise, and that is the yardstick.

| | A1-off-null1 | A2-off-null2 |
|---|---|---|
| pod | `...75cd6854ff-f5cfw` | `...645b4575db-8rtsn` |
| STABLE-PASS | 14 | 14 |
| STABLE-FAIL | 11 | 10 |
| FLAKY | 3 | 4 |
| `must_not_cite` violations | 0 | 0 |
| `valid` / `provisional` | true / false | true / false |

**Null flip set, by id** -- this is the object the decision rule uses, which is
why the ledger reports sets and not the counts `summary.json` stores:

- STABLE-PASS -> STABLE-FAIL: **2** -- `real_covenant_monocovenantal_001`,
  `real_imprecatory_psalms_001`
- STABLE-FAIL -> STABLE-PASS: **0**
- STABLE-PASS -> FLAKY: 1 -- `day_of_atonement_001`
- FLAKY -> STABLE-PASS: 3 -- `real_christophanies_001`,
  `real_moses_death_001`, `sheep_001`

**Prediction 1 HOLDS, at the bottom of its band.** Predicted 2-6 stable flips
with at least one question flipping STABLE in one arm and not the other.
Measured: 2, with 2 such questions. The pass-rate totals would have told the
opposite story -- 14 and 14, identical, a difference of zero. Two arms that
agree exactly on the headline moved 2 questions and destabilised a third.

**One thing the null shows that was not predicted**: its 2 flips are both in
the same direction (2 regressions, 0 improvements). At n=2 that is a coin
landing twice and must not be read as a baseline direction; it is recorded
because a direction claim about the effect pair cannot lean on this.

**Instrument drift between the null halves: checked, none.** The halves ran at
different `git_head` (`25b5be8` vs `bcac4c0`) because the ledger tool was
committed between them. That commit touched `docs/` and the new
`evals/gate_ledger.py` only -- **0** files in the request or scoring path
(`run_eval.py`, `paired_gate_run.py`, `gill_reference_set.jsonl`), verified by
`git diff --name-only` rather than assumed.

## Part 2 -- PREDICTION 4 IS FALSIFIED

Predicted: the discard branch (`raw_query_no_entities`) on **more than half**
of the 28 questions in each arm, reasoning from the 5-key thesaurus.

Measured: **5 of 28** (A1) and **4 of 28** (A2). Roughly 16%, not >50%. The
prediction was wrong and the reasoning behind it was wrong.

| arm | `expanded_with_entities` | `raw_query_no_entities` |
|---|---|---|
| A1 | 74 draws / 26 q | 10 draws / 5 q |
| A2 | 76 draws / 26 q | 8 draws / 4 q |

Two details worth more than the headline:

1. **The branch is itself stochastic.** The 5 questions in A1 hit it on 10 of
   their 15 draws, not 15. A one-draw-per-item branch count would have
   misreported the population as well as the rate -- the same estimator fault
   the lock rejected for scoring, which is why this was recorded per draw.
2. **Its id set varies between identical arms** by one question
   (`real_bread_of_life_001`). So prediction 5's comparison needs a tolerance
   of at least 1 id, and that tolerance comes from the null, not from taste.

The union limitation stands unchanged: `raw_query_no_entities` does not say
*why* retrieval ran on the raw question. This is the branch population, never
an attribution.

## Part 3 -- THE EFFECT COMPARISON (A3-off vs A4-on)

| | A3-off | A4-on |
|---|---|---|
| pod | `...6bdcff5896-zggrt` | `...869b5874df-kjn7s` |
| pod_spec_flag | 0 | 1 |
| STABLE-PASS | 14 | 16 |
| STABLE-FAIL | 10 | 5 |
| FLAKY | 4 | 7 |
| `must_not_cite` violations | 0 | 0 |

### Verdict by the pre-registered rule: PASS

- **STABLE-PASS -> STABLE-FAIL: 0.** No regression, so nothing to test against
  the null's flip set.
- **`must_not_cite` violations under ON: 0.** Prediction 3 holds.
- Total stable flips 2, against a locked null band of 2. Prediction 2 holds.
- Discard-branch id sets differ by 1 (`real_bread_of_life_001`), the same
  tolerance the null itself showed. Prediction 5 holds.

### The apparent IMPROVEMENT is NOT established, and this is the main result

The headline reads like a win: +2 STABLE-PASS, -5 STABLE-FAIL. It does not
survive the per-question decomposition, and reporting the headline would have
been wrong.

**Both stable improvements are questions where A3 was the outlier OFF arm:**

| question | A1 off | A2 off | A3 off | A4 ON |
|---|---|---|---|---|
| `john_baptist_001` | SP | SP | **SF** | SP |
| `day_of_atonement_001` | SP | FLAKY 1/3 | **SF** | SP |

`john_baptist_001` stable-passes in two of three OFF arms. The ON arm agrees
with those two and disagrees with A3. That is not the flag improving a
question; that is A3 being low on it. `day_of_atonement_001` spans SP ->
FLAKY -> SF **under OFF alone**, so an ON reading at the top of that range is
inside the configuration's own spread.

**The three OFF arms scoring 14 each is a hit by cancellation, not stability.**
Intersection of the three STABLE-PASS sets: **9**. Union: **19**. The three
14s are not the same 14 questions. An arm-level total was identical three
times over while the rows underneath it disagreed, which is exactly why the
decision rule is a per-id flip and not a pass rate.

**Where A3's 10 STABLE-FAILs actually went under ON**: 4 stayed SF (and were
SF in A1 and A2 too -- genuinely failing, not noise), 2 went SP (the two
above), 4 went FLAKY. So the -5 STABLE-FAIL is mostly STABLE-FAIL -> FLAKY,
i.e. questions that now pass *sometimes*, which is the noise band by
definition.

### The only candidate signal, with its counterweight at equal strength

Reported together deliberately. A one-directional read of these rows is how a
noise floor becomes a feature.

| question | OFF (3 arms, 9 draws) | ON (3 draws) | direction |
|---|---|---|---|
| `real_exclusive_psalmody_001` | SF, SF, SF (0/9) | FLAKY 1/3 | toward pass |
| `real_universal_atonement_001` | SF, SF, SF (0/9) | FLAKY 1/3 | toward pass |
| `real_benjamin_type_001` | SP, SP, SP (9/9) | FLAKY 2/3 | toward fail |

Two questions that never passed in 9 OFF draws passed once each under ON; one
question that passed all 9 OFF draws failed once under ON. Same evidential
strength, opposite directions, all three inside the FLAKY band. **At one draw
of difference each, none of these is a finding.** They are the population to
watch if this is ever run at higher n, and `real_benjamin_type_001` is the one
to watch first, because a stably-passing question becoming unstable is the
failure mode the flag would plausibly cause.

### What this PASS asserts, and what it does not

It asserts: at n=28 with 3 draws, `GILL_STRUCTURED_ANSWER=1` moved **no**
question from stably-passing to stably-failing, and produced **no**
`must_not_cite` violation.

It does **not** assert the flag improves answers. The +2 is accounted for by
A3's position on two unstable questions. It does not assert an effect below
roughly 15% of the set is absent -- that is invisible to this design.

**`must_not_cite` caveat, load-bearing here.** The stored record keeps the
violation flag for the LAST draw only. Under ON there are 7 FLAKY and 5
STABLE-FAIL questions, so a violation on an unstored draw is not excluded by
the 0 above -- it would have cost that draw its `overall_pass`, which the
ledger does see, but its reason is not recoverable. Prediction 3 holds at
last-draw fidelity, not absolutely.

## Part 4 -- the pre-registered null was too narrow, shown by its own data

Three OFF arms give three identical-configuration pairs:

| pair | SP->SF | SF->SP | total stable flips |
|---|---|---|---|
| A1 vs A2 *(the locked null)* | 2 | 0 | **2** |
| A1 vs A3 | 3 | 2 | **5** |
| A2 vs A3 | 2 | 3 | **5** |

The locked null was the **lowest of the three**. Across all three pairs, **7
distinct questions move stably between identical configurations** (25% of the
set), and the regression-direction union alone is 5 ids:
`real_covenant_monocovenantal_001`, `real_imprecatory_psalms_001`,
`day_of_atonement_001`, `john_baptist_001`, `real_moses_death_001`.

**This did not change the verdict, and that is the only reason it is safe to
report.** The effect comparison produced 0 regressions, so a wider null could
only have made a PASS easier. Had the rule fired, the pre-registered null
would have stood as the verdict and this section would have been evidence for
the next lock, not grounds for reversing this one -- using post-hoc same-config
data to cancel a pre-registered positive is how a flag gets protected.

**Design lesson for the next lock**: one null replicate understates the noise.
Two of the five regression-direction ids above
(`day_of_atonement_001`, `john_baptist_001`) are *outside* the locked null's
2-id set, so a regression landing on either would have been called real by the
locked rule while same-config data says it is noise. Budget three
same-configuration arms, not two, and derive the band from the union.

---

## Carried residuals

- **Witnessed gate defect**: the single-pod gate filters pods carrying a
  `deletionTimestamp`, but such a pod can still be `serving=true` in the
  service's EndpointSlice -- observed directly between A1 and A2. The gate
  cannot see the state it exists to prevent. A1 escaped it on a ~21 second
  margin (old flag-1 pod `Killing` at 02:56:16Z, 30s grace, A1's first request
  02:57:07Z) that nothing in the launcher enforced. Arms are being drained to a
  single serving endpoint by procedure; the launcher fix is filed, not applied
  mid-run, because editing the instrument between arms would make the arms
  non-identical.
- **`must_not_cite` is last-draw fidelity only.** A violation on draw 1 or 2
  costs that draw its `overall_pass`, so it cannot hide from the ledger, but
  its reason is not recoverable from the stored record. Both OFF null arms
  report 0; for the ON arm this limitation is load-bearing on prediction 3 and
  is stated with the result.
- The cause of the 2026-10-25 credential failure remains **UNDETERMINED**.
