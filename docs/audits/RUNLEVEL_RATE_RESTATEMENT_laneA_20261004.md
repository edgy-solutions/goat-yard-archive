# The headline pass rate, restated over runs — every arm on disk

**Lane A, 2026-10-04.** Ruling 2 of the same date: *"Replace summary.passed with the run-level
rate; mark docs quoting the old number."* This is the marker those docs point at, and it carries
the corrected figures rather than only a caveat on the old ones.

Every line number in this document refers to the files at `56466e8`, i.e. before the
markers were inserted into the six documents and shifted their numbering.

## What was wrong

`summarize()` received `results`, which holds **one row per question** — the question's *last
scored run* (`run_eval.py`, `last_r = scored_runs[-1]`). Every other run of every question was
discarded before the rate was computed. At 13 questions x 5 runs the published "9/13" described
9 of 65 measurements and called the result a pass rate.

A correction to this lane's own record: `RESULT_off_vs_on_rerun3_laneA_20261004.md` line 165 says
the statistic counts each question's **first** run. It does not — it is the **last scored** run.
The substance of that section (one run per question, on a suite that is majority flaky) is
unaffected; the identification of which run was wrong.

## Method

Nothing was re-run and no model was called. Each per-question JSON already stores `run_passes`,
one entry per run with `None` for a run that produced no score, so the figure the summaries
should have published is recoverable from the recorded artifacts:

- `runs_passed` = count of `True` across all questions of the arm
- `runs_scored` = count of entries that are not `None` (errored and degraded runs are out of the
  denominator, exactly as they are for the question-level figure)

Cross-check: `RESULT_off_vs_on_rerun3_laneA_20261004.md` lines 173-175 already published three of
these figures, computed independently at the time. This recomputation reproduces all three to the
run (49/65, 42/65, 38/65), which is the evidence that the method here is the same one.

## Every arm on disk

| arm | published (questions) | run-level (corrected) | delta |
|---|---|---|---|
| `adr0009_flag/off_20260927c` | 16/23 = 69.6% | **43/69 = 62.3%** | -7.3 pp |
| `adr0009_flag/off_20260927d` | 17/28 = 60.7% | **45/84 = 53.6%** | -7.1 pp |
| `adr0009_flag/on_20260927d` | 15/28 = 53.6% | **45/83 = 54.2%** | +0.6 pp |
| `adr0009_flag/rerun_off_20260927` | 1/3 = 33.3% | **4/8 = 50.0%** | +16.7 pp |
| `floor_20260928/armA` | 9/13 = 69.2% | **63/78 = 80.8%** | +11.6 pp |
| `floor_20260928/armB` | 12/13 = 92.3% | **63/78 = 80.8%** | -11.5 pp |
| `noise_floor/nf1_20260927` (RETIRED) | 12/28 = 42.9% | **49/84 = 58.3%** | +15.4 pp |
| `noise_floor/nf2_20260927` (RETIRED) | 14/28 = 50.0% | **42/84 = 50.0%** | 0.0 pp |
| `off_vs_on_20261004/off` | 11/13 = 84.6% | **57/65 = 87.7%** | +3.1 pp |
| `off_vs_on_rerun2_20261004/off` | 12/13 = 92.3% | **49/65 = 75.4%** | -16.9 pp |
| `off_vs_on_rerun2_20261004/on` | 9/13 = 69.2% | **43/65 = 66.2%** | -3.0 pp |
| `off_vs_on_rerun3_20261004/off` | 9/13 = 69.2% | **42/65 = 64.6%** | -4.6 pp |
| `off_vs_on_rerun3_20261004/on` | 8/13 = 61.5% | **38/65 = 58.5%** | -3.0 pp |
| `off_vs_on_rerun_20261004/off` | 9/13 = 69.2% | **43/65 = 66.2%** | -3.0 pp |
| `pinned_floor/pf1_20260927` | 21/28 = 75.0% | **55/84 = 65.5%** | -9.5 pp |
| `pinned_floor/pf2_20260927` | 16/28 = 57.1% | **52/84 = 61.9%** | +4.8 pp |
| `temperature_check/t0_20260927` | 12/13 = 92.3% | **62/78 = 79.5%** | -12.8 pp |
| `temperature_check/tu_20260927` | 8/13 = 61.5% | **55/78 = 70.5%** | +9.0 pp |
| `temperature_check/tu_provisional_20260927` | 8/13 = 61.5% | **55/78 = 70.5%** | +9.0 pp |
| `temperature_check/scapegoat_t0_replicate_20260928` | 0/1 = 0% | **0/6 = 0.0%** | 0.0 pp |

## What the same-config pairs say about the instrument

The question-level figure did not merely add noise — it **manufactured gaps between arms that are
not there**. Each row below is two arms of the *same* configuration:

| pair | question-level gap | run-level gap |
|---|---|---|
| `floor_20260928` armA vs armB | 23.1 pp | **0.0 pp** (63/78 both, identical to the run) |
| `pinned_floor` pf1 vs pf2 (floor of record) | 17.9 pp | **3.6 pp** |
| `noise_floor` nf1 vs nf2 (RETIRED, calibration history only) | 7.1 pp | 8.3 pp |

So the run-level estimator is **not** noise-free: the worst same-config gap it shows is 8.3 pp, on
the retired pair. Taking the floor of record and the September floor pair together, a run-level
difference under roughly **4 pp** is inside the instrument, and one under 8 pp cannot be
distinguished from the retired pair's null.

Two cautions against reading the armA/armB row as "the arms were identical":

- 63/78 twice is **equal totals over different compositions**. 14 of 78 per-question runs moved
  between those two arms; the pooled total is what matched, and one null replicate flipped a
  question 6/6 to 0/6 at fixed config. A pooled equality is not a per-question equality.
- Both estimators are fed by the same scorer. A scorer defect moves both and is invisible here.

## What changed in the code

- `run_level_tally()` is now the one place the run-level pass count is computed, so the headline
  and the run block cannot drift into two numbers about one arm.
- `summarize()` takes `run_ledger` as a **required** argument. Optional would let a call site fall
  back to the one-run-per-question number under the same key `passed`, which is the defect being
  removed.
- `summary["passed"]`, `pass_pct` and `by_category` are over scored **runs**; `pass_denominator`
  states the denominator beside the numerator; `pass_basis: "runs"` makes a pre-ruling summary
  detectable instead of inferred from a date.
- The question-level count survives as `representative_passed`, with a note saying it is one run
  per question and is not a rate. The old artifacts stay readable; the number just may no longer
  be called the pass rate.
- `compare_to_baseline()` **refuses** a baseline whose `pass_basis` is not `runs` instead of
  subtracting a share of questions from a share of runs. A missing baseline file is nothing to
  compare and still exits 0; a baseline that exists and states a rate in another unit is a trap.
- Fixed while in there: `main()` returned the baseline comparison's code **above** the integrity
  check, so any arm invoked with `--baseline` could exit 0 while its samples were cache replays.
  Precedence is now a pure function, `exit_code()`, with 4 outranking everything.

## What this does NOT solve

- **The rate is still a pooled total.** On a suite where roughly 8 of 13 questions are flaky, a
  run-level rate is a better-conditioned number, not a licence for question-level claims. The
  gate remains the stability block (STABLE-PASS / STABLE-FAIL / FLAKY classes and stable flips),
  not the rate. Nothing here changes what gates a flip.
- **No arm's verdict is revised.** The published verdicts were reached on the stability block and
  the integrity gates, which are untouched. This restates one headline number.
- **The pre-ruling artifacts are not rewritten.** Their summaries keep the figure they published,
  which is why `pass_basis` exists. Scripts reading stored arms must read
  `representative_passed`, or `passed` only when `pass_basis` is absent.
- **The resolution figures above rest on three same-config pairs**, one of which is retired. That
  is a small sample for an instrument claim, and it is a lower bound on the noise, not a bound on
  it.
