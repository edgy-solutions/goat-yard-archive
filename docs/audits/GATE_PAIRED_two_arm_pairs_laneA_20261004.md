# The paired gate, run on two real arm pairs — and what replication did to the verdict

**Date:** 2026-10-04 · **Lane:** A1 (`body-path`) · **Gate:** `evals/gate_paired.py` (`c5bfeb8`,
`d1c064c`, `0e309df`) · **Suite:** `evals/test_gate_paired.py` 33/33

Ruling 3 (Chris, 2026-10-04): *"After the re-score, replace the gate with a paired per-question
test against the null plus 'stable-fail under ON on any question that ever stable-passed.'"*

The gate is built, tested and now **run on two independent replicates of the same off-vs-on
comparison**. This report records the prediction, both verdicts, the one number the prediction got
wrong, and the thing the second replicate exposed that neither run alone could: **the gate's
statistical clause is not stable across replicates of the same comparison, while its ratchet
clause is.** `evals/output/` is gitignored, so without this file the numbers exist nowhere.

---

## 1. The prediction, written before the first run

Hand-computed from disk and saved before `gate_paired.py` was invoked on real arms
(`scratchpad/PREDICTION_gate_rerun2.md`, reproduced verbatim in appendix A).

It held on every number — bands, exclusions, both sign tests, regression and improvement counts,
both ratchet trips — **except one line**:

> "ratchet: 2 trips (…), 1 excluded (scapegoat_001)"

Actual: 2 trips, **0 excluded**. `scapegoat_001` under ON is 2/5, which is FLAKY, not STABLE-FAIL,
so it never qualified as a trip for the ruling-1 exclusion to remove. The exclusion machinery was
exercised on the *regression* list (where scapegoat does appear, and is correctly marked NOT
GATING) and not on the ratchet. Predicting a trip that cannot exist is a misread of my own
classifier, not of the data; the number that matters — what fires — was right.

The prediction's last line was about the *second* pair, and it was **falsified**:

> "For rerun3 I predict the same two ratchet trips, because the re-score found the same two sids
> unverified in both ON arms."

rerun3 produced **one** trip. `real_election_001` went 1.00 → 0.20 under ON rather than to 0.00,
and 1/5 is FLAKY, so the ratchet — which demands a *stable* fail — correctly declined to trip on
it. The regression is still reported; the ratchet simply refuses to call a 1/5 a stable fail. That
is the clause behaving as specified against a prediction that assumed the flag's effect was
deterministic. It is not.

---

## 2. Both verdicts, four runs

Effect pairs: `off_vs_on_rerun2_20261004/{off,on}` and `off_vs_on_rerun3_20261004/{off,on}`
(13 real questions, N=5). Nulls: `floor_20260928/{armA,armB}` (13 questions, N=6) and — added
second — `(off_vs_on_rerun2_20261004/off, off_vs_on_rerun3_20261004/off)`, two OFF arms at the
same configuration.

| run | nulls | sign test (all) | **sign test (gating — decides)** | regressions | improvements | ratchet | verdict |
|---|---|---|---|---|---|---|---|
| rerun2 | floor only | 5/4/4 p=1.0 | **3/3/4 p=1.0 not disting.** | 3 (2 gating) | 2 | 2 | **FIRES: ratchet** |
| rerun2 | + shared-arm | 5/5/3 p=1.0 | **3/4/3 p=1.0 not disting.** | 3 (2 gating) | 2 | 2 | **FIRES: ratchet** |
| rerun3 | floor only | 10/2/1 p=0.0386 | **8/1/1 p=0.0391 DISTINGUISHABLE** | 7 (6 gating) | 3 | 1 | **FIRES: ratchet and paired test + regression** |
| rerun3 | + shared-arm | 7/3/3 p=0.3438 | **5/2/3 p=0.4531 not disting.** | 5 (4 gating) | 2 | 1 | **FIRES: ratchet** |

The gate fires on all four. **Why** it fires is not stable.

### 2a. Two replicates of one comparison, two different statistical verdicts

Against the same independent null, rerun2's gating set is indistinguishable from two identical
arms (p=1.0, 3 wins / 3 losses) and rerun3's is distinguishable (p=0.0391, 8 wins / 1 loss) with
six gating regressions. Same flag, same config, same question set, 13 questions, N=5 — and the
paired test's answer flips. This is the memory *measure the null before reading a delta* arriving
one level up: it is no longer the per-question rate that is unstable under replication, it is the
**aggregate significance verdict computed from those rates**. At n=13 with one draw per question,
the sign test can detect only a broad effect, and the breadth it sees is itself a draw.

### 2b. The second null pair was not independent, and it is now labelled

Adding `(rerun2/off, rerun3/off)` moved rerun3's gating test from p=0.0391 to p=0.4531 **by
itself**. That looks like the significance was an artifact of an under-measured null — and the
floor pair *is* under-measured, reporting a band of exactly 0.00 on 7 of 13 questions. But the
added pair contains each effect pair's own OFF arm, so `rate(off, q)` enters the effect and that
pair's band at once. The correlation widens the band precisely where the effect is widest, and it
runs one way: **toward not firing.** A gate biased toward silence hides what it exists to catch.

Measured per row, the shared-arm pair supplies the decisive (larger) band on only 2 of 13
questions, but it is the *sole* source of any band at all on three the floor pair called 0.00 —
`day_of_atonement_001` (0.60), `john_baptist_001` (0.20) and
`real_garden_genesis_3_24_misattribution_001` (0.20) — and it raises
`real_covenant_monocovenantal_001` from 0.1667 to 0.60. So both readings are defensible and neither is clean: the floor null is independent but blind, the
shared null sees real OFF-vs-OFF movement but is correlated with the effect.

`0e309df` makes the gate say so in its notes rather than refuse the pair — both members did run at
the same configuration, so the band is a real measurement, just not an independent one. Born both
directions (shared pair → exactly one note naming the arm; independent pair, `None` map and empty
map → none).

**This is not a conclusion that rerun3's signal was noise.** It is a conclusion that the two
available nulls disagree, and that the one which cancels the signal is the one that cannot be
trusted to cancel it.

---

## 3. What survives replication — the finding

Because neither single-replicate verdict can be trusted, the honest instrument at this sample size
is the **sign of the movement, required to repeat in both replicates.**

| question | rerun2 off→on | rerun3 off→on | replicates? |
|---|---|---|---|
| `day_of_atonement_001` | 1.00 → 0.00 | 0.40 → 0.00 | **DOWN in both** |
| `real_election_001` | 1.00 → 0.00 | 1.00 → 0.20 | **DOWN in both** |
| `scapegoat_001` | 1.00 → 0.40 | 1.00 → 0.60 | **DOWN in both** (NOT GATING, ruling 1) |
| `john_baptist_001` | 0.40 → 1.00 | 0.20 → 1.00 | UP in both (NOT GATING) |
| `real_singing_psalms_001` | 0.60 → 1.00 | 0.60 → 1.00 | UP in both |
| `sheep_001` | 0.80 → 1.00 | 0.60 → 0.80 | UP in both |
| `real_christophanies_001` | 1.00 → 1.00 | 1.00 → 0.80 | no |
| `real_covenant_grace_001` | 0.80 → 0.80 | 1.00 → 0.60 | no |
| `real_covenant_monocovenantal_001` | 1.00 → 1.00 | 0.40 → 1.00 | no |
| `real_garden_genesis_3_24_misattribution_001` | 0.40 → 0.40 | 0.20 → 0.00 | no |
| `real_imprecatory_psalms_001` | 0.60 → 0.80 | 0.80 → 0.60 | no (sign reverses) |
| `simons_count_001` | 0.20 → 0.20 | 0.20 → 0.00 | no |
| `real_ishmael_circumcision_001` | 1.00 → 1.00 | 1.00 → 1.00 | flat in both |

**3 down, 3 up, 7 unreplicated.** Seven of thirteen questions — including four of rerun3's six
gating regressions — do not reproduce their own direction across two runs of the same comparison.
The rerun3 run's apparent breadth was carried mostly by questions that moved once.

Of the three replicated regressions, one (`scapegoat_001`) is NON_GATING by ruling 1. The gating
replicated regressions are **exactly the two questions the rerun2 ratchet tripped on**:
`day_of_atonement_001` and `real_election_001`. Under a replication rule the gating sign test is
3 up vs 2 down, p=1.0 — **no broad effect** — with two specific questions reproducibly worse.

So the two clauses separate cleanly on real data: the paired test, which looks for breadth, found
breadth once out of twice and should not be believed at this n. The ratchet, which looks for a
specific question going stably bad, named the same two questions that survive replication. At 13
questions and N=5 **the ratchet is the clause doing the work**, exactly as its docstring claims.

---

## 4. What those two questions actually fail on

Taken from disk, per-question representative score records, polarity checked (`must_not_*` and
`*_skipped` are False when *passing*). In every off→on pair whose representative score changed at
all, the **only** check that changed is `must_be_verified_ok`:

| arm | question | `must_*` checks that differ, off → on |
|---|---|---|
| rerun2 | `day_of_atonement_001` | `must_be_verified_ok` True → **False** |
| rerun2 | `real_election_001` | `must_be_verified_ok` True → **False** |
| rerun3 | `real_election_001` | `must_be_verified_ok` True → **False** |
| rerun3 | `scapegoat_001` | `must_be_verified_ok` True → **False** |
| rerun2 | `scapegoat_001` | *(none — both representatives passed; run_passes 5 vs 2)* |
| rerun3 | `day_of_atonement_001` | *(none — OFF's representative was already failing verification)* |

On every one of these: `must_cite_recall` 1.0 (0.5 for scapegoat, unchanged between arms),
`must_express_ok` True, `must_not_cite_violated` False, `must_not_express_ok` True,
`verification_failure` **False** — the verifier ran and returned, it did not error — and five
distinct `answer_sha16` per question, so these are five genuinely different generations, not a
cached answer scored five times.

`must_be_verified_ok` is the check governed by the quote-pairing regex fixed under ruling 1
(`bot.py:61`). `day_of_atonement_001` and `real_election_001` are two of the three sids that
re-score resolved — `EXODUS_30_10_S00` and `JOHN_6_39_S00`
(`docs/audits/RESCORE_quote_pairing_laneA_20261004.md`).

**So the gate's only firing clause on these arms, on both replicates, rests entirely on the one
check whose scorer was demonstrably broken when these runs were scored.** The two replicated
regressions are most likely scorer artifacts rather than flag regressions. That is a statement
about where to look next, not a verdict: the fix is in the code, the runs on disk were scored
before it, and the re-score could only reach the representative run.

---

## 5. What this does NOT solve

- **The other four runs per question cannot be re-scored from disk.** `run_eval.py:1729` writes the
  representative run's `response`/`score`; the per-run record keeps `answer_chars`, `answer_sha16`,
  `degraded`, `elapsed_s`, `entity_lookup_mode`, `error`, `expansion_error`, `expansion_fallback`,
  `generation_seconds`, `pass`, `pin_honored`, `provider_pin`, `provider_served`,
  `temperature_on_the_wire`, `verification_failure` — **not `must_be_verified_ok`**, and not the
  unverified sids. The pass *rates* in section 3 therefore carry the old scorer's verdict on four
  runs in five. This is **ruling 4's blocker**, named concretely; the enabling fix (record
  `verified` plus the unverified sids per run in the harness) is specified in the re-score report
  and **not implemented**. A fresh 5×13 would be a sixth attempt at the same comparison and is not
  taken.
- **The gate does not implement the replication rule** used in section 3. That analysis was done by
  hand over two JSON outputs. Writing it into the gate is a design change beyond ruling 3's wording
  and is offered as a proposal (§6), not shipped.
- **Nothing verifies that two arms called a null were configured alike.** The provider-pin and
  serving-config notes remain the only checks; a null pair is a caller's claim.
- **Neither null is both independent and informative.** The floor pair reports a 0.00 band on 7 of
  13 questions, which is a band from one pair at N=6, not a measured zero.
- **No statement is made about the flag's effect on production.** These are `goatyardtest` arms;
  the production corpus (`192.168.1.52`) was not addressed.
- The gate still cannot tell an under-powered arm's rate from a real one beyond printing the
  UNDER-POWERED note, and two arms whose directory basenames collide are labelled identically.

---

## 6. Proposal, for Chris's ruling

Replace the single-replicate sign test as the *deciding* clause with a **replication requirement**:
a question counts as moved only if its sign repeats across two independent replicates of the same
comparison; the sign test then runs over replicated movements only. Keep the ratchet unchanged —
it is the clause that survived this exercise. The cost is that every gated comparison needs two
replicate pairs instead of one, which is 2× the runs; the benefit is that 7 of 13 questions in
this very comparison would stop contributing verdicts they cannot reproduce.

Not implemented pending ruling, because it changes what ruling 3 specified.

---

## Appendix A — the prediction, verbatim

```
# Prediction, hand-computed before running gate_paired.py on rerun2 vs the 2026-09-28 floor

Arms: off_vs_on_rerun2_20261004/{off,on} (16 files, N=5), null = floor_20260928/{armA,armB} (13, N=6).

- shared 16, tested 13: corpus_objects_at_start, corpus_objects_at_end and run_header have 0 runs
  and must be EXCLUDED, not scored as zeros. The null covers all 13 real questions.
- bands: 0 for 9 questions; 0.1667 covenant_grace, covenant_monocovenantal; 0.3333 imprecatory,
  scapegoat, sheep.
- sign test, all 13: wins 5 (atonement, john_baptist, election, singing_psalms, scapegoat),
  losses 4 (grace, mono, imprecatory, sheep), ties 4 -> p = 1.0, not distinguishable.
- sign test, gating 10: wins 3, losses 3, ties 4 -> p = 1.0, not distinguishable.
- regressions beyond band: 3 reported (atonement -1.0, election -1.0, scapegoat -0.6 vs 0.33),
  2 gating.
- improvements beyond band: 2 (john_baptist +0.6, singing_psalms +0.4).
- ratchet: 2 trips (day_of_atonement_001 5/5 -> 0/5, real_election_001 5/5 -> 0/5), 1 excluded
  (scapegoat_001).
- VERDICT: GATE FIRES on the ratchet alone, with the sign test NOT distinguishable.

For rerun3 I predict the same two ratchet trips, because the re-score found the same two sids
unverified in both ON arms.
```

## Appendix B — reproducing these numbers

```sh
# rerun3 against the independent null only; swap rerun3 -> rerun2 above for the other pair
python evals/gate_paired.py \
  --off evals/output/off_vs_on_rerun3_20261004/off \
  --on  evals/output/off_vs_on_rerun3_20261004/on \
  --null evals/output/floor_20260928/armA evals/output/floor_20260928/armB \
  --history evals/output/off_vs_on_rerun2_20261004/off \
            evals/output/off_vs_on_rerun2_20261004/on

# add the second, non-independent null pair (expect the NOT INDEPENDENT note)
  --null evals/output/off_vs_on_rerun2_20261004/off \
         evals/output/off_vs_on_rerun3_20261004/off
```

Exit code 1 means the gate fired, which is a finding and not a crash. Run directories are under
`evals/output/`, which is gitignored; these numbers are reproducible only where those arms exist.
