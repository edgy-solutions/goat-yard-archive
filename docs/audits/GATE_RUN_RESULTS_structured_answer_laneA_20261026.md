# Results -- paired `GILL_STRUCTURED_ANSWER` gate run

Pre-registration: `GATE_RUN_LOCK_structured_answer_laneA_20261025.md`. Every
prediction and the decision rule were fixed in that file before any arm ran.
This file reports what came back. Nothing here amends a prediction.

Run date: 2026-10-26. Target gya-test only. Image digest
`sha256:2fce1e34...b11433` on all arms, asserted per arm on the pod.

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

## Part 3 -- arms 3 and 4 (effect comparison)

*Pending. The null above was reported first, as the lock requires.*

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
