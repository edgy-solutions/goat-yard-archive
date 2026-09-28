# Pinned OFF-vs-OFF floor — result (Lane A, 2026-09-27)

Ruling 2 step 2. Both arms: `201a4b9`, clean tree at start **and** end, N=3, 28 questions,
provider pinned to StreamLake, DSPy cache disabled, one server process throughout.
Prediction locked before the runs in `PREDICTION_pinned_floor_laneA_20260927.md` (committed `201a4b9`).

Published (ruling 3) and hash-verified 33/33 both arms:
`dr-voluminous/body_shadow_vol1/evals/pf1_20260927/`, `.../pf2_20260927/` — commit `b2f2eb7b`.

## The floor

| | pf1 | pf2 |
|---|---|---|
| passed | 21/28 (75.0%) | 16/28 (57.1%) |
| refusal correct | 27/28 | 26/28 |
| STABLE-PASS | 13 | 13 |
| STABLE-FAIL | 6 | 8 |
| FLAKY | 9 | 7 |
| must_not_cite violations | 0 | 0 |
| runs scored | 84/84 | 84/84 |
| answer-LM configurations | 1 | 1 |

`class_changes_n = 10` of 28. **STABLE-PASS <-> STABLE-FAIL flips = 0.**

Two arms with **identical recorded configuration** — same commit, same clean tree, same pin,
same model, same corpus, same server — differ by **5 questions** on the headline pass rate.
That is the floor. The arm pass-rate total is not a measurement of a code change; the flip
gate is, and it held at 0 while the total moved 5.

## Prediction scorecard

| # | prediction | outcome |
|---|---|---|
| P1 | `class_changes_n` 6-14 | **HIT** — 10 |
| P2 | `stable_flips_n == 0` (the gate) | **HIT** — 0 |
| P3 | FLAKY 8-15 per arm | **MISS** — pf1 9 (in), pf2 7 (just below) |
| P4 | `passed` 10-17, arms differ <=4 | **MISS both ways** — 21 and 16, differ by 5 |
| P5 | *mechanism:* pinning will NOT materially cut the change count vs the unpinned pair's 11; falsified if <=3 | **HIT, and it is the load-bearing one** — 10 vs 11. Pinning the provider changed essentially nothing. The noise was never provider mixing. |
| P6 | exactly one `answer_lm` row/arm, 84 runs, `dspy`/`dspy.LM`, temperature `<absent from optional_params>`, StreamLake, `pin_honored: true` | **HIT** — every field, both arms |
| P7 | first live sighting of `integrity.git` + `answer_lm` in a written summary.json | **HIT** — `at_start`/`at_end` both `201a4b9` clean, `changed_during_run: false`, `provisional: false`, violations `[]` |
| P8 | `compare_arms` raises no ANSWER-LM note | **HIT** — none; configs compared equal rather than assumed equal |
| P9 | the thing most likely wrong: the OFF temperature value | **RESOLVED in favour of the original claim** — OFF genuinely sends no temperature |

P4 was calibrated on nf1's 12/28. It missed because pf1 came in at 21 — see the unattributable
shift below. P4's *spread* clause (<=4) missing is not a calibration error; it is the result.

## Answer to ruling 2 step 3 — does the 28-set need N=5?

Pooling the 6 runs per question across both arms (the recorded configuration is identical, so they
pool):

- **9** deterministic pass (6/6)
- **6** deterministic fail (0/6)
- **13 of 28 (46%) stochastic**, and **8 of those sit at 5/6** — one failing run out of six.

At N=3 a question with p~0.83 shows 3/3 about 58% of the time and 2/3 about 40%. Those eight
therefore move between STABLE-PASS and FLAKY by chance alone, which is the 10 class changes.

**N=5 majority would help the 5/6 group and would not help the real problem.** Three questions sit
near a coin flip — `john_baptist_001` 4/6, `scapegoat_001` 4/6, `real_imprecatory_psalms_001` 3/6.
No N rescues a p~0.5 item as a pass/fail gate. Recommendation, for Chris to rule on:

1. Keep gating on STABLE-PASS<->STABLE-FAIL flips. It just held at 0 across a 5-question swing.
2. Stop quoting arm pass-rate totals as comparative evidence. Two identical arms differ by 5.
3. Raise N for *classification* (6 pooled runs already classify better than either arm's 3), but
   treat the three near-coin-flip questions as unusable gate items until their scorer is
   deterministic or they are cut from the gate set.
4. **Before OFF-vs-ON, chase the 46%.** The OFF path sends *no* temperature, so deepseek's own
   default applies. The earlier probe concluding "temperature is not the flakiness lever" was N=3
   on questions this floor now shows N=3 cannot discriminate — that conclusion is under-powered and
   should be re-run at N=6 on these 13 stochastic questions specifically, with temperature=0 set
   explicitly.

## What this does NOT solve

- **An unattributable 12->21 shift.** nf1 (same day, same pin, same cache setting, same dspy path,
  identical response shape) scored 12/28; pf1 scored 21/28. nf1 predates both `integrity.git` and
  `answer_lm`, so its commit and server config are unrecorded and the gap cannot be attributed. No
  scorer-semantics commit sits in the window. **nf1/nf2 should be retired as a baseline**, which is
  the same conclusion ruling 1 already reached for a different reason.
- **The harness records code state but not corpus state.** Captured by hand for this pair:
  Weaviate 1.38.1 at 192.168.1.54, `CommentaryChunk` 7294, `TheologicalEntity` 8433. A shared remote
  corpus that any lane or ingest can move is the most plausible cause of the shift above, and the
  config hash cannot see it. A corpus fingerprint belongs in `integrity`.
- OFF-vs-ON is not run. (b)'s prompt change still waits.

## Two harness faults found by running it

1. **`RATE_LIMIT` never reached the process.** `.env` line 44 is one malformed line: a missing
   newline concatenated `RATE_LIMIT="1000/day"` onto the end of the `PROD_MINIO_PASS` value, so
   dotenv defines neither correctly and `/api/search` fell back to its 10/day anonymous default.
   Arm 1 aborted at question 3. The run-level-fault gate behaved exactly as specified — aborted,
   wrote no report — but it left 2 per-question JSONs on disk while saying "No report is written";
   a later reader could mistake that directory for a run. `.env` is gitignored and holds live
   credentials, so I did not edit it: the arms were run with `RATE_LIMIT` passed explicitly at
   launch. **`PROD_MINIO_PASS` is also wrong by 22 trailing characters**, which will break Step 9's
   MinIO upload. Chris's call.
2. **`publish_run.py` validates `--also` after copying.** A bad `--also` path aborted the call with
   the run directory already copied, leaving a published-but-incomplete measurement that then
   refused re-publishing without `--replace`. It should validate every input before copying a byte.

Also: the server must be launched `PYTHONIOENCODING=utf-8` (the init path crashes printing a U+274C
under cp1252, and `/api/books` then serves a hardcoded 2-book fallback that looks healthy), and my
own readiness probe was wrong in the mirror direction — the real book list is
`["Genesis-Numbers","Matthew-John"]`, also length 2, so `len(books) > 2` can never pass. Compare the
names, not the count.
