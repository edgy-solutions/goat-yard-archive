# RETIRED as a baseline - nf1_20260927 / nf2_20260927 (ruling 1, 2026-09-27)

> **VOID (2026-10-04)** -- every arm cited in this document ran with the query-expansion
> stage dead: `LITELLM_PROXY_URL` was unset at eval launch. It **is** set in the production API
> pod, so production runs that stage live and none of these arms measures production behavior.
> The numbers below are retired as evidence. Derivation and the full void list:
> [VOID_arms_without_expansion_laneA_20261004.md](VOID_arms_without_expansion_laneA_20261004.md).

**Do not cite either arm as a baseline, a floor, or the comparison point for any later run.**
Neither arm can state what it measured. The measurements themselves are not being deleted; what is
withdrawn is their standing as a point of comparison.

Superseded by **`pf1_20260927` / `pf2_20260927`** (commit `201a4b9`, clean tree at start *and* end),
written up in `docs/audits/RESULT_pinned_floor_laneA_20260927.md`. That pair is the floor of record:
`class_changes_n = 10` of 28, STABLE-PASS <-> STABLE-FAIL flips = 0.

## Why

1. **Both arms ran over a dirty tree**, contrary to the prediction document's own clause. Arm 2 also
   had three commits land mid-run. Under ruling 1 the pair is permanently provisional.
2. **nf1 predates `integrity.git` and `answer_lm`.** Its commit, its server configuration and which
   model actually served it are unrecorded, so nothing about it can be reproduced or attributed.
3. **An unattributable 9-question gap.** nf1 scored 12/28. pf1 - same day, same provider pin, same
   cache setting, same DSPy path, identical response shape - scored 21/28. No scorer-semantics
   commit sits in the window. A baseline whose distance from a later run is unexplained is not a
   baseline; it is a number.
4. **Neither arm recorded corpus state.** The corpus is a shared remote instance that any lane or
   ingest can move, and until `integrity.corpus` existed (2026-09-27, commit `3da88f3`) no run could
   see it. That is the most plausible cause of item 3, and it stays untestable backwards: the corpus
   of 2026-09-27T23:52Z was never fingerprinted and cannot be now.
5. **nf2 has at least one known-wrong row.** An upstream 429 arrived as HTTP 200 with the error in
   the prose (`real_garden_genesis_3_24_misattribution_001`), so it was scored as a content failure
   rather than excluded as a degradation. nf2's pass rate is therefore wrong by an unknown amount in
   a known direction.

## What still stands

- The **method**: two arms, identical configuration, and a count of the questions that change class.
  That is exactly what the pinned pair then did properly.
- The pair as **evidence about the harness, not about the system**. nf1/nf2 are the run that found
  the 429-as-HTTP-200 hole, the unlabelled-degradation hole and the `RATE_LIMIT` `.env` fault. Cite
  them for those. They are why `backend/degradation.py` and the run-level fault gate exist, and
  `backend/degradation.py`, `backend/test_typed_channels.py` and `evals/run_eval.py` reference the
  nf2 artifact deliberately, as the fixture of a real incident.
- The prediction scorecard in `docs/audits/NOISE_FLOOR_RESULT_laneA_20260927.md`, as a record of
  what was predicted and what happened. Calibration history stays honest even when the underlying
  arm is withdrawn. `evals/score_noise_floor_predictions.py` still defaults to these two run
  directories for exactly that reason.

## What this does NOT solve

Retiring the pair does not recover the 9-question gap. It is unattributable and stays that way;
`integrity.corpus` only prevents the next one. It also does not remove the pair from the repo's
references, deliberately: three files cite the nf2 artifact as a fault fixture and the scorer still
points at both directories. And a notice cannot stop a citation - `compare_arms.py` has no idea
which run directories it is handed, so nothing mechanically prevents someone diffing a new arm
against nf1 tomorrow.
