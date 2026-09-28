# Result — the temperature check, N=6 on the 13 stochastic questions

Lane A. Arms run 2026-09-27 into 2026-09-28. Prediction locked beforehand at
`docs/audits/PREDICTION_temperature_check_laneA_20260927.md` (sha16 `80068f19794e3061`, commit
`ac4cc6a`); scorer written before any result existed (`7a85f0b`). Neither file was edited after
the arms ran.

## Headline

**Temperature is not inert, and it is not small.** Four of the eight scorable predictions are
falsified, all in the same direction: the OFF answer path's unrecorded sampling temperature moves
both the answers and the pass/fail outcome substantially.

The consequence is the one the locked prediction named in advance, so it is stated as it was
written there: **every OFF-vs-ON arm ever run is confounded beyond repair, and the OFF-vs-ON
comparison must be re-specified with temperature pinned to 0 on both paths before anything more
is spent on it.**

| | verdict | observed |
|---|---|---|
| P1 >=8 of 13 still stochastic at t=0 | **FALSIFIED** | 6 of 13 |
| P2 >=4 of the 5/6 group still imperfect | **FALSIFIED** | 3 of 8 |
| P3 >=10 of 13 text differs | PARTIAL | 13/13 on the one stored response; per-run text not persisted |
| P4 wire values (companion assertion) | **HELD** | full 13+13 coverage, no off-spec record |
| P5 `compare_arms` raises the ANSWER-LM note | **HELD** | raised, and correct |
| P6 pooled delta within 6 of 78 | **FALSIFIED** | 55 -> 62, **+7** |
| P7 no STABLE-PASS <-> STABLE-FAIL flip | **FALSIFIED** | 1: `scapegoat_001` SF -> SP |
| P8 corpus clean on all four samples | **HELD** | clean, byte-identical across all four |
| P9 156 calls, no degradation, no run fault | **HELD** | 156, 0, 0 |

Both arms: HEAD `7a85f0b`, tree clean and unmoved, `provisional: false`, corpus 7294 chunks
`6cbb33635352` / `dc7968e3290d` identical at all four samples, pin `streamlake` no fallbacks,
LM cache off. The arms differ in `GILL_ANSWER_TEMPERATURE` and in nothing else recorded.

## Per question

| question | tu (unset) | t0 (=0) |
|---|---|---|
| `scapegoat_001` | 0/6 | **6/6** |
| `real_garden_genesis_3_24_misattribution_001` | 2/6 | 5/6 |
| `day_of_atonement_001` | 4/6 | 6/6 |
| `real_covenant_grace_001` | 5/6 | 6/6 |
| `sheep_001` | 2/6 | 3/6 |
| `john_baptist_001` | 4/6 | 4/6 |
| `real_christophanies_001` | 6/6 | 6/6 |
| `real_covenant_monocovenantal_001` | 6/6 | 6/6 |
| `real_election_001` | 6/6 | 6/6 |
| `real_imprecatory_psalms_001` | 5/6 | 4/6 |
| `real_ishmael_circumcision_001` | 6/6 | 5/6 |
| `real_singing_psalms_001` | 6/6 | 5/6 |
| `simons_count_001` | 3/6 | **0/6** |

Temperature 0 is not uniformly better. `simons_count_001` went 3/6 -> 0/6 and two questions left
STABLE-PASS. The effect is large and two-directional, which is what "confounded" means here — not
"the ON arm was flattered".

## The measured null, and why it matters for reading the above

Discarding a provisional arm (below) left two N=6 arms at unset temperature, hours apart, same
corpus, same executed code. That is an OFF-vs-OFF replicate on today's backend:

- pooled 55/78 and 55/78 — **identical**
- but 14 of 78 total per-question movement, two questions moving 3+ of 6 (`sheep_001` 6->2,
  `day_of_atonement_001` 1->4), three class changes, **zero** SP<->SF flips

This was computed and written down **before `t0` produced a number**, so the reading rule it sets
is not a threshold chosen after seeing the arm: at N=6 a per-question delta of up to 4 of 6 is
inside the null, and only the pooled total and an SP<->SF flip carry signal.

Against that rule, the two findings that survive are exactly the two the rule admits: the pooled
+7 (null replicate: 0) and the `scapegoat_001` flip.

It also exposes **P6 as a weak prediction.** The +/-6 band was a guess; I had no measured null when
I locked it. A null replicate of 0 makes +7 meaningful, but one replicate is a single draw, not a
variance estimate — I cannot claim +7 sits outside a distribution I have measured exactly once.
The honest statement is: the pooled delta exceeds the only null I have, and P7 is the stronger
evidence.

## I was wrong about `scapegoat_001`, and said so too confidently

Mid-run I recorded that `scapegoat_001` returning 0/6 in both unset arms, against 4/6 on the
pinned floor, was "not the coin" and that "the cause is on the retrieval or gating path in the
backend as it stands today, not in the corpus and **not in sampling**." I put it at p~0.0002.

The arithmetic was right and the conclusion was wrong. It is sampling. At temperature 0 the same
question is 6/6, with the same corpus, same code, same retrieval path. 0/12 unset and 6/6 at
t=0 is a temperature effect, not a backend regression, and there is no backend investigation to
open.

What went wrong is not the number — it is that I named a mechanism when all I had was a rejection
of the coin hypothesis. Ruling out chance does not select a cause. This is the fourth time on this
project that a correct measurement carried a fabricated mechanism, and it is worth noting that I
wrote it down an hour before the arm that refuted it was already running.

## Two defects in my own setup, found and repaired before `t0`

**1. The first `tu` arm was provisional.** HEAD moved `7fcab13 -> 7a85f0b` mid-arm because I
committed the scorer while it ran. The executed code *was* identical — verified, not assumed: the
diff is a single added file, nothing imports it, uvicorn had no `--reload`. It was re-run anyway.
The provisional flag is the ruling-4 guard, and its value is that whoever trips it does not get to
adjudicate past it with a mechanism story. Kept at
`evals/output/temperature_check/tu_provisional_20260927/` with a note; it is the second half of
the null replicate above, so the 78 calls were not wasted.

Standing rule: **commit nothing between the start of the first arm and the end of the last.** The
recorder watches HEAD, not just the working tree.

**2. "Same server process" was unachievable as locked.** `answer_temperature()` is read inside
`lifespan` in `backend/main.py`, so the value is fixed at process start and an env var cannot be
changed in a running process from outside. I wrote that clause as if the knob were per-request. It
is process-level, so `t0` requires a restart by construction. Repair: both arms got a fresh restart
from the same clean HEAD, which restores the symmetry the clause was reaching for. The prediction
file was not edited.

## What this does NOT solve

- **The variance is reduced, not explained.** Six of 13 are still stochastic at temperature 0, and
  `sheep_001` is 3/6 with the field pinned. Temperature is *a* source; the remaining suspects named
  in the prediction — retrieval order (embedding ties, gRPC result ordering) and the scorer itself
  — are untouched here and still need their own instruments.
- **The 19 deterministic questions were not run.** Temperature 0 could break a question that is
  currently 6/6 and this pair cannot see it. That surfaces, if anywhere, in the full-28 OFF-vs-ON
  run, and should be watched for there.
- **P3 is still unmeasurable as worded.** Per-run answer text is not persisted — `runs[]` holds
  pass/degraded/elapsed only. 13/13 differ on the single stored final response per question, which
  is one sample per arm, not the claim. A per-run answer digest costs nothing and should be added
  **before** OFF-vs-ON, never between arms.
- **One provider, one model.** `streamlake` serving `deepseek/deepseek-chat`. Deepseek's actual
  default temperature is still unrecorded — this run shows it is not 0, and nothing more.
- **It does not re-open the gate by itself.** The prediction's own escape clause was that the three
  near-coin-flip questions stay out of the flip gate "unless it shows them deterministic at
  temperature 0". `scapegoat_001` is 6/6 at t=0 and 0/12 unset, which fits — but on a single N=6
  arm, and its exclusion reason ("p~0.5") is now falsified as a description of it.
  `john_baptist_001` (4/6) and `real_imprecatory_psalms_001` (4/6) do not fit and stay out.
  **Recommendation, not a change: confirm `scapegoat_001` at t=0 in a second arm, then return it to
  the gate.** The non-gating set is Chris's ruling and this run does not amend it.

## Artifacts

- `evals/output/temperature_check/tu_20260927/` — control, unset, citable
- `evals/output/temperature_check/t0_20260927/` — explicit 0, citable
- `evals/output/temperature_check/tu_provisional_20260927/` — superseded, kept as the null replicate
- published by explicit path to `dr-voluminous/body_shadow_vol1/evals/`
