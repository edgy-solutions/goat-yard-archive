# Prediction: pinned OFF vs OFF noise floor, N=3, 28 questions

Lane A, 2026-09-27. Written and committed **before the run**, per the standing rule. Ruling 2's
second step: *"pinned OFF vs OFF, clean tree, N=3, predict first -> decide from that floor whether
the 28-set needs N=5 majority or more questions."*

## Configuration under test

Both arms identical: `GILL_STRUCTURED_ANSWER` unset (OFF / DSPy path),
`GILL_DISABLE_LM_CACHE=1`, `OPENROUTER_PROVIDER_ORDER=streamlake`, `--runs 3`, warmup on, the same
28-question reference set. Server started **from this worktree** at `4bc7fe9`, tree clean at start
and end (ruling 1). The only difference between the arms is time.

## The prior this is measured against

The unpinned pair (`nf1_20260927` / `nf2_20260927`, provisional -- both ran over a dirty tree) gave:
**11 of 28 class changes, 0 STABLE-PASS<->STABLE-FAIL flips**, `summary.passed` 12 -> 14 while
STABLE-PASS fell 9 -> 7, FLAKY 12 on arm 1.

## Predictions

**P1 -- the floor does not close.** `class_changes_n` between 6 and 14 inclusive. Pinning the
provider does not remove the noise.

**P2 -- the gate holds.** `stable_flips_n == 0`. No question moves STABLE-PASS <-> STABLE-FAIL
between two identical arms. If this fails, the gate ruling 1 rests on is measuring noise and the
28-set is unusable as-is at N=3.

**P3 -- FLAKY stays high.** Between 8 and 15 questions FLAKY on each arm.

**P4 -- pass rate is unstable but bounded.** `passed` within 10-17 of 28 on each arm, and the two
arms differ by no more than 4.

**P5 -- this is the falsifiable one, about mechanism.** Pinning will NOT materially reduce the
change count versus the unpinned pair's 11. The temperature probe showed generation is
deterministic *within* a provider at both settings (3/3 identical text, twice), so the variance has
to be downstream of generation -- retrieval order, embeddings, the quote verifier, or server state.
**If `class_changes_n` comes in at 3 or below, that story is wrong** and the unpinned pair's noise
was provider mixing after all. Recording it as a prediction because the causal story is a claim
too, and mis-attributing a mechanism has burned this project repeatedly.

**P6 -- the new instrument reports, live.** Each arm's `summary.json` carries an `answer_lm` block
with **exactly one** distinct row: `path=dspy`, `client=dspy.LM`,
`temperature_on_the_wire="<absent from optional_params>"`, `provider_served="StreamLake"`,
`pin_honored=true`, `runs=84`. `questions_missing_a_record` empty,
`runs_pin_honored_false: 0`, `runs_pin_unchecked: 0`. Preflight prints the `Answer LM:` line before
question 1.

**P7 -- first live sighting of two blocks asserted only by unit tests.** Both `summary.json` files
contain `integrity.git` with `dirty: false` and equal start/end SHAs, and `answer_lm` as above.

**P8 -- `compare_arms` raises no ANSWER-LM note.** Both arms record the same serving configuration,
so `answer_lm_config` matches and no `ANSWER-LM CONFIG DIFFERS` / `NO PER-CALL ANSWER-LM RECORD`
note appears. This is the negative half: the new comparator check must be silent when it should be.

**P9 -- one thing I expect to be wrong about.** The `temperature_on_the_wire` value. It is
predicted as the sentinel string because `dspy.LM` leaves temperature `None`, but the probe read
that from a bare `dspy.LM`, and the server builds its LMs with an `extra_body` and may pick up a
default from `dspy.settings`. If it comes back `0.0` or `1.0`, the OFF path has been sending a
temperature all along and the asymmetry I reported to Chris is a different shape than described.

## What a pass here does NOT license

- It says nothing about OFF vs ON. That is step 3, and it is the comparison that needs this floor.
- It cannot confirm the ON path's per-call record, which has only ever been read from a rendered
  request, never a live response.
- A low change count would not mean the 28-set is a good instrument, only that this pair agreed.
