# Re-score of every recorded eval arm under the fixed quote/citation pairing regex

Lane A1, 2026-10-04. Discharges the re-score half of Chris's ruling item (1):
*"Fix bot.py:61 regex; born-tests both directions; re-score both pairs from disk;
include the fix in 0.3.2 — it affects production's citation verifier."*

**This file is the record.** `evals/output/` is gitignored, so the instrument's
JSON (`evals/output/rescore_quote_pairing.json`) is not durable. The instrument
itself is committed (`evals/rescore_quote_pairing.py`) and re-running it against
the same arms reproduces every number below; nothing here was read off a model.

## The defect, and what the fix was

The eval gate `must_be_verified_ok` (`evals/run_eval.py:384-391`) reads the
response's `verified` flag, which is `not quote_failures` (`backend/main.py:1028`),
which comes from `no_gill_quote_for_citation` in `_repair_quotes_in_answer`, which
comes from one regex: the quote/citation pairing pattern at `backend/bot.py:61`.

Gill's prose is full of nested quotation. A span quoted far enough into it ends
with the **source's own** closing mark immediately followed by the answer's —
`&c."" [SID]`. The old closer was a single mark, so the first mark closed the
quote and the second landed in the intervening gap, which excludes quote
characters. No match → the citation read as BARE → a false
`no_gill_quote_for_citation`. **The more faithful answer scored worse.**

The fix widens the closer to a run of marks (`["“”]` → `["“”]+`), one character.
It is safe because of a property of the **capture group**, not of the closer:
group 1 is `[^"“”]+` and cannot contain a quote mark at all, so
`"A" and "B" [SID]` can only ever capture `B`. Widening the closer does not
widen the capture. Born tests in both directions:
`backend/test_quote_cite_pairing.py` (14 tests, `EXPECTED_TESTS = 14`), which
holds the old pattern so the defect itself stays under test.

Committed `aaf48c9` on `body-path`; cherry-picked onto `release-0.3.2` as
`2e2fa41` (both unpushed, awaiting Chris's deploy; **0.3.1 ships first**).

## Prediction, made before the run

For the two pairs the ruling named: **3 question-flips per ON arm, 0 on either
OFF arm, no regressions.** It held exactly. The other 16 arms were swept without
a numbered prediction; one of them moved (see below), which is why it is called
out rather than folded into a total.

## Result — all 20 recorded arms, 383 questions

Representative-run pass count before → after. `res` = sids the fix resolves,
`alr` = sids already paired under the old regex (the fix cannot be their cause),
`unv` = unverified sids recorded, `cc`/`pl` = capture changes / pairings lost.

| arm | q | rep before → after | res | alr | unv | cc | pl |
|---|---|---|---|---|---|---|---|
| `off_vs_on_rerun2_20261004/on` | 16 | **9 → 12** | 4 | 1 | 5 | 0 | 0 |
| `off_vs_on_rerun3_20261004/on` | 16 | **8 → 11** | 3 | 2 | 5 | 0 | 0 |
| `adr0009_flag/on_20260927d` | 28 | **15 → 17** | 2 | 6 | 8 | 0 | 0 |
| `off_vs_on_rerun2_20261004/off` | 16 | 12 → 12 | 0 | 1 | 1 | 0 | 0 |
| `off_vs_on_rerun3_20261004/off` | 16 | 9 → 9 | 0 | 11 | 11 | 0 | 0 |
| `off_vs_on_rerun_20261004/off` | 16 | 9 → 9 | 0 | 6 | 6 | 0 | 0 |
| `off_vs_on_20261004/off` | 13 | 11 → 11 | 0 | 1 | 1 | 0 | 0 |
| `adr0009_flag/off_20260927c` | 28 | 16 → 16 | 0 | 5 | 5 | 0 | 0 |
| `adr0009_flag/off_20260927d` | 28 | 17 → 17 | 0 | 5 | 5 | 0 | 0 |
| `adr0009_flag/rerun_off_20260927` | 28 | 1 → 1 | 0 | 3 | 3 | 0 | 0 |
| `floor_20260928/armA` | 13 | 9 → 9 | 0 | 4 | 8 | 0 | 0 |
| `floor_20260928/armB` | 13 | 12 → 12 | 0 | 1 | 1 | 0 | 0 |
| `noise_floor/nf1_20260927` | 28 | 12 → 12 | 0 | 10 | 18 | 0 | 0 |
| `noise_floor/nf2_20260927` | 28 | 14 → 14 | 0 | 8 | 16 | 0 | 0 |
| `pinned_floor/pf1_20260927` | 28 | 21 → 21 | 0 | 2 | 5 | 0 | 0 |
| `pinned_floor/pf2_20260927` | 28 | 16 → 16 | 0 | 7 | 10 | 0 | 0 |
| `temperature_check/t0_20260927` | 13 | 12 → 12 | 0 | 2 | 2 | 0 | 0 |
| `temperature_check/tu_20260927` | 13 | 8 → 8 | 0 | 2 | 3 | 0 | 0 |
| `temperature_check/tu_provisional_20260927` | 13 | 8 → 8 | 0 | 2 | 6 | 0 | 0 |
| `temperature_check/scapegoat_t0_replicate_20260928` | 1 | 0 → 0 | 0 | 0 | 0 | 0 | 0 |

**Totals: 9 sids resolved, 79 already paired but unverified, 31 unresolved and
paired under neither regex, 119 unverified sids in all; 0 capture changes, 0
pairings lost.** The 9 matches the 9 instances measured independently by the
geometry census of all 40 unpaired citations (9 run-of-2 marks adjacent to the
gap, 19 single mark, 12 no mark at all).

Every arm that moved is an **ON** arm. Every OFF arm is unchanged. The eight
flipping questions and their sids:

| arm | question | resolved sids |
|---|---|---|
| `rerun2/on` | `day_of_atonement_001` | `EXODUS_30_10_S00` |
| `rerun2/on` | `real_election_001` | `JOHN_6_39_S00` |
| `rerun2/on` | `real_garden_genesis_3_24_misattribution_001` | `GENESIS_2_15_S01`, `LUKE_23_43_S01` |
| `rerun3/on` | `day_of_atonement_001` | `EXODUS_30_10_S00` |
| `rerun3/on` | `real_election_001` | `JOHN_6_39_S00` |
| `rerun3/on` | `real_garden_genesis_3_24_misattribution_001` | `GENESIS_3_24_S00` |
| `on_20260927d` | `day_of_atonement_001` | `EXODUS_30_10_S00` |
| `on_20260927d` | `real_garden_genesis_3_24_misattribution_001` | `GENESIS_2_15_S01` |

Three questions, not a spread: atonement, election, and the Genesis 3:24
misattribution probe. All three are questions whose Gill source quotes a Targum,
i.e. exactly where nested quotation lives.

## The two limits that bound every number above

1. **Representative run only.** `run_eval.py:1729` writes the last scored run's
   `response` and `score` in full and keeps the other runs as a thin ledger:
   `answer_sha16`, `answer_chars`, `pass`, `elapsed_s`, and a BOOLEAN
   `verification_failure` (a stage flag, not the failure list). **There is no
   answer text for runs 1..n-1 anywhere on disk**, so the fix cannot be applied
   to them, and **no corrected run-level rate comes out of disk.** This is the
   unit Chris's ruling (3) and (4) need, and it blocks them as written — see
   "What this does NOT solve".
2. **The recorded answer is POST-repair.** `_repair_quotes_in_answer` may have
   already substituted a verbatim span for a near-miss before the text was
   written out, so re-running the verifier over `score.answer` is not
   bit-identical to re-running the live request. Conservative for the
   `no_gill_quote_for_citation` class (a repair only moves a quote closer to its
   source), but a `quote_not_verbatim` count taken from this probe is not
   trustworthy.

Two further scope limits: KJV text is not reconstructed (`KJV_DATA` is not
loaded), so the probe decides the **Gill** obligation only — which is the gate
that moved; and the reconstruction of `overall_pass` from the recorded gate
fields is asserted against the recorded value for **every** record and aborts the
whole run on any mismatch, so a delta is never reported off a verdict the probe
cannot derive.

## A defect in the instrument, found and corrected

The resolution rule started with two clauses — did not pair before, pairs now —
and produced an unexplained flip: `noise_floor/nf1/scapegoat_001`
(`LEVITICUS_16_10_S00`) went to pass, but that sid was **already paired under the
old regex**, so the fix cannot be what changed it. The cause was limit 2: the
span on disk is the verbatim one the repair substituted, while the live verifier
failed the pre-repair quote. Without the third clause the probe credits the fix
with a recovery belonging to `_repair_quotes_in_answer`.

The rule now has three clauses — a recorded unverified sid is RESOLVED only if
(a) it did **not** pair under the old regex, (b) it pairs under the new one, and
(c) the newly paired span is verbatim in that sid's own Gill source under
`bot._quote_in_source`. Such sids are reported under
`already_paired_but_unverified` rather than dropped, because they are the measure
of how much of the recorded failure set this probe **cannot speak to**: 79 of
119, two thirds. After the tightening, exactly 9 sids resolve — and only then
did the probe's count agree with the independently measured 9.

This is the causal story being a claim too: the first number was right in
direction and wrong in cause, and the thing that settled it was the old regex
itself, not a second opinion.

## What this does NOT solve

- **No corrected run-level rate, and therefore no corrected gate.** Rulings (3)
  and (4) are computed per question across runs. Limit 1 makes that
  uncomputable from disk, and a fresh run would be a forbidden sixth attempt at
  the 5×13 pair. The enabling fix is cheap and not yet made: record `verified`
  and the unverified sids **per run** in the harness, not just for the
  representative. Until then the paired per-question test and the flip proposal
  rest on representative-level numbers, which is the unit ruling (2) retired.
- **79 of 119 recorded unverified sids are untouched by this fix** — they paired
  and did not verify. The dominant recorded failure class is not non-pairing.
  Nothing here says what that class is.
- **The 31 that pair under neither regex are not all defects.** Two were
  diagnosed as model-side malformations the regex is right to refuse: a quote the
  model never opened (`nf2/john_baptist`) and a `'` opener
  (`pf2/real_gill_aquinas`). The other 29 are uncharacterised.
- **A nested quotation in the MIDDLE of a span is deliberately not handled.** No
  instance was measured; there the capture stops at the inner mark and the pair
  still forms on the tail, so the citation is not lost. If that shape ever
  appears it will present as `quote_not_verbatim`, not as a missing citation.
- **The production effect is asserted, not measured.** The same regex runs in the
  product's citation verifier, so the fix removes false `verified=False` badges
  there too — but no production answer was re-scored, and none should be from
  here.
