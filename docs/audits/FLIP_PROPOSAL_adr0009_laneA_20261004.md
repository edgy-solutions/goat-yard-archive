# ADR-0009: the flip decision, proposed — and why the pass rate cannot carry it yet

**Lane A, 2026-10-04.** Ruling 3 of the same date, verbatim:

> *"No sixth attempt at 5×13. Propose the flip decision on: zero stable regressions across five
> clean arms, the sinkhole result, and the refusal-variant fix — with the pass-rate delta stated as
> below instrument resolution."*

No sixth attempt was made and none is proposed. Everything below comes off disk — the recorded
arms, the recorded answers, and the production code at HEAD. No model was called.

**I cannot propose the flip on the three legs as the ruling states them.** Two of the three do not
hold up when measured, and the pass-rate delta cannot honestly be called below instrument
resolution on the 13-question arms. What the evidence does support is a different and, I think,
better-founded proposal, which is at the end.

---

## 1. The premise audit

### Leg 1 — "zero stable regressions across five clean arms": **does not hold as stated**

The flip gate from ruling 1 (2026-09-27) is **one STABLE-PASS → STABLE-FAIL flip**. Run over every
recorded OFF/ON pair (`evals/compare_arms.py`, floor 10):

| pair | questions × runs | gating SP→SF flips |
|---|---|---|
| `adr0009_flag/off_20260927d` vs `on_20260927d` | 28 × 3 | **1** — `real_moses_death_001` 3/3 → 0/3 |
| `off_vs_on_rerun2_20261004` off vs on | 13 × 5 | **2** — `day_of_atonement_001` 5/5 → 0/5, `real_election_001` 5/5 → 0/5 |
| `off_vs_on_rerun3_20261004` off vs on | 13 × 5 | **0** |

**"Five clean arms" resolves exactly, and the count is right.** The arms carrying a git block with
`dirty: false` and `provisional: false` are, among the flag arms: `rerun_20261004/off`,
`rerun2/off`, `rerun2/on`, `rerun3/off`, `rerun3/on` — **five.** (`off_vs_on_20261004/off` is
`provisional: true` and is out; the four `adr0009_flag` arms predate the git axis and carry no git
block at all, so the 27d pair sits outside the clean set and its row above is for context only.)

Those five clean arms contain **two** complete OFF/ON pairs plus one orphan OFF. Restricted to
them, the gate fires **2 flips in rerun2 and 0 in rerun3** — so it is not zero. rerun3 ran at the
later HEAD, so read naively the sequence looks like a regression that then cleared. It did not
clear; see immediately below.

**And rerun3's zero is an artifact of the comparator, not of the flag.** `day_of_atonement_001`
under ON is **0/5 in rerun2 and 0/5 in rerun3** — ten consecutive failing runs across two HEADs.
It escapes the gate in rerun3 only because the OFF baseline happened to be flaky that arm
(5/5 → 2/5), so the transition reads FLAKY → STABLE-FAIL instead of STABLE-PASS → STABLE-FAIL.
Nothing about the flag improved. The baseline sank onto it.

That is a defect in the gate's shape, not only in this reading of it: **a per-arm
STABLE-PASS → STABLE-FAIL test can be satisfied by a noisier baseline.** It is the same class as
asking what a PASS asserts. Here a pass asserts "no question crossed both thresholds in this one
pairing", which is not "no question regressed."

### Leg 2 — the sinkhole result: **holds, untouched**

`ADR0009_FLAG_RESULT_laneA_20260927.md:91,101` stands. P11 was falsified on the upside: 23 of 28
questions populated `zone3_notes`, 57 of 84 ON runs emitted a non-empty one, and OFF produced
**structurally zero** because the field does not exist on that path. The content is the slant
ADR-0009 predicted it would absorb. Nothing in this document touches that finding, and it is the
one leg of the three I would carry into a flip argument as-is.

### Leg 3 — the refusal-variant fix: **was never implemented**

- `baml_src/gill_answer.baml` has **one commit in its entire history**: `ac71b00`, the commit that
  introduced ADR-0009. No `@description` in the refusal variant has been changed since.
- `answered_substantively` appears nowhere in any `.py` file in the repo. It exists only as a
  recommendation and a from-disk re-score inside
  `GATE_DEFECTS_items_b_and_c_laneA_20260927.md:73,122`.
- The only code difference between the rerun2 and rerun3 HEADs (`75955dd5..f06b2509`) is
  `answer_lm_record.py`, `bot.py` (+6 lines), `main.py` and a test — answer-LM provenance
  recording. Instrumentation, not answer behaviour.

**And it would not have addressed these arms even if it had landed.** Across all four rerun arms,
`refusal_correct` is `True` on **every** representative failure, and per-run `verification_failure`
is 0 of 65 in three arms and 1 of 65 in the fourth. There is not one refusal-path failure in the
rerun pairs to fix.

---

## 2. The pass-rate delta, stated

Run-level, from `RUNLEVEL_RATE_RESTATEMENT_laneA_20261004.md`:

| pair | OFF | ON | ON − OFF |
|---|---|---|---|
| `adr0009_flag` 27d (28 × 3) | 45/84 = 53.6% | 45/83 = 54.2% | **+0.6 pp (ON ahead)** |
| `off_vs_on_rerun2` (13 × 5) | 49/65 = 75.4% | 43/65 = 66.2% | **−9.2 pp** |
| `off_vs_on_rerun3` (13 × 5) | 42/65 = 64.6% | 38/65 = 58.5% | **−6.1 pp** |
| pooled, the two 13-question arms | 91/130 = 70.0% | 81/130 = 62.3% | **−7.7 pp** |

Instrument resolution, from the same-config pairs:

| pair | run-level gap |
|---|---|
| `floor_20260928` armA vs armB (identical config) | **0.0 pp** — 63/78 both |
| `pinned_floor` pf1 vs pf2 (the floor of record) | **3.6 pp** |
| `noise_floor` nf1 vs nf2 (RETIRED) | 8.3 pp |
| `temperature_check` t0 vs tu | 9.0 pp |

**The ruling's final clause holds on one arm and not on the others, and I am not going to state it
as though it held on all three.** +0.6 pp on the 28-question pair is below every floor estimate and
is in ON's favour. −9.2 pp and −6.1 pp are both above the 3.6 pp floor of record, and the first is
above every floor estimate on the list. Two arms with the same sign at that size are weak evidence,
not no evidence.

**But the pooled −7.7 pp is not a uniform shift, and decomposing it changes what it means.** Per
question, pooled over the two 13-question arms (10 runs each side):

| question | OFF | ON | Δ runs |
|---|---|---|---|
| `real_election_001` | 10/10 | 1/10 | **−9** |
| `day_of_atonement_001` | 7/10 | 0/10 | **−7** |
| `scapegoat_001` | 10/10 | 5/10 | **−5** |
| `real_covenant_grace_001` | 9/10 | 7/10 | −2 |
| `real_christophanies_001`, `real_garden_…`, `simons_count_001` | | | −1 each |
| `real_imprecatory_psalms_001`, `real_ishmael_circumcision_001` | 7/10, 10/10 | 7/10, 10/10 | 0 |
| `sheep_001` | 7/10 | 9/10 | +2 |
| `real_covenant_monocovenantal_001` | 7/10 | 10/10 | **+3** |
| `real_singing_psalms_001` | 6/10 | 10/10 | **+4** |
| `john_baptist_001` | 3/10 | 10/10 | **+7** |

−26 runs down, +16 up, net −10 of 130. The headline is the residue of large movements in **both**
directions on six questions, not a general degradation. Per the standing lesson, a pooled delta
gets decomposed per question before it is believed, and this one does not survive the decomposition
as a single effect.

---

## 3. What the three big movers actually are: a verifier false positive, reproduced

Every representative failure in all four rerun arms fails on exactly one gate:
`must_be_verified_ok` (`evals/run_eval.py:391`), which is just the API response's `verified` flag.
Not refusals. Not `must_cite`. Not `must_not_cite`.

Tracing that flag: `verified = not quote_failures` (`backend/main.py:1028`), and `quote_failures`
comes from the ADR-0006 quote repair in `backend/bot.py`. A cited SID that has no Gill-side quote
*paired to it* yields a `no_gill_quote_for_citation` failure — "Gill was summarized, not quoted."
The pairing is done by one regex, `backend/bot.py:61`:

```python
QUOTE_WITH_CITE_RE = re.compile(
    r'["“”]([^"“”]+)["“”][^"“”\n\[\]]{0,80}\[([A-Z0-9_]+_S\d+)\]'
)
```

The captured span is `[^"“”]+` — **it cannot contain a quote mark.** Gill's own prose is full of
nested quotation: he quotes the Targum, Jarchi, the Jews, Scripture. A quoted span that runs far
enough to include one of those ends with the source's closing mark *and* the answer's, producing
`.""` before the SID. The regex then cannot pair it in either direction, the citation reads as
bare, and the answer is marked unverified.

**Measured, over every representative answer on disk:**

| arm | answers | containing `""` | with an unpaired citation | `verified: false` |
|---|---|---|---|---|
| `adr0009_flag/off_20260927d` | 28 | **0** | 1 | 5 |
| `adr0009_flag/on_20260927d` | 28 | **3** | 2 | 6 |
| `rerun2/off` | 13 | **0** | 0 | 1 |
| `rerun2/on` | 13 | **3** | 3 | 4 |
| `rerun3/off` | 13 | **0** | 0 | 4 |
| `rerun3/on` | 13 | **3** | 3 | 5 |

Nine instances, **all nine on ON, zero in 54 OFF answers.**

**And the quotes are genuine.** For each of the 7 unpaired citations in the rerun arms I pulled the
span the answer attached to the citation and tested it against the text of the sentence it cites,
as delivered in that same response's own context:

| | |
|---|---|
| unpaired citations examined | 7 |
| whose quoted span is an **exact** substring of the cited sentence | **7 of 7** (21, 21, 90, 116, 205, 205, 362 chars — longest common prefix equal to the full span in every case) |
| preceded by a doubled quote mark | **7 of 7** |
| whose cited SID was absent from the retrieved context | **0 of 7** |

Worked example — `real_election_001`, ON, rerun3. `unverified_sentence_ids: ["JOHN_6_39_S00"]`.
The SID is in the retrieved context; OFF retrieved the **identical 28-SID context** and verified
clean. The 205-character span the answer attached to it, Hebrew included, is a character-exact
substring of `JOHN_6_39_S00`. It ends `…and many of them that sleep in the dust, &c.""` — Gill
quoting the Jews quoting Daniel. The answer is more faithful than OFF's and scores worse for it.

ON answers on these questions run 3–5× longer than OFF's on every single run (e.g.
`real_election_001` ON 3321–6158 chars against OFF 452–2353), which is why ON reaches the nested
quotations and OFF does not.

**The defect is not ADR-0009's.** `bot.py:61` is shared code that ADR-0009 never touched; it is
latent on the OFF path for the same reason it never fires there — OFF's quotes are too short to
reach a nested quotation. ADR-0009 makes a pre-existing verifier bug load-bearing. But the
consequence for ruling 3 is direct: **the measured pass-rate gap is in substantial part this
regex.** `real_election_001` (−9) and `day_of_atonement_001` (−7) are 16 of the 26 downward runs,
and both are driven by it in their representative runs.

Three of the nine ON representative failures (`simons_count_001` ×2, `scapegoat_001`) have **no**
unpaired citation and are candidates for genuine quote-fidelity failures — the same class as all
five OFF failures. That is the honest residual, and it is not nothing.

---

## 4. The proposal

**Do not flip, and do not reject, on the current pass rate. Fix the verifier, re-score from disk,
and read the delta then.** Specifically, in this order:

1. **Fix `QUOTE_WITH_CITE_RE` so a quoted span may contain the source's own quote marks.** Born-test
   it against the 7 recorded instances — the fixtures already exist on disk, in the answers
   themselves — and in **both** directions: a quote containing a nested mark must pair, and a
   citation with genuinely no quote attached must still fail. A one-direction gate is half a gate,
   and the repair must not become a way of passing a bare citation.
2. **Re-score both 13-question arms and the 28-question pair from disk.** Free, no model call, and
   it is not a sixth attempt at 5×13: the answers are recorded and only the scoring changes. State
   the per-question table and the pooled delta against the 3.6 pp floor of record.
3. **Then decide the flip** on the sinkhole result (leg 2, which stands), the re-scored delta, and
   the residual failures that survive the fix.
4. **Separately, change the flip gate.** A per-arm STABLE-PASS → STABLE-FAIL test can be satisfied
   by a noisier baseline, which is exactly what happened in rerun3. Pooled per-question run counts
   with a stated resolution — which the run-level restatement now makes computable — do not have
   that hole.

Leg 3 as written — the refusal-variant fix — should be **dropped from the flip argument**, not
deferred. There is no refusal failure in the rerun arms for it to fix. It remains a real item for
the 28-question arm, where ON refused 7 of 28 under both a lexical and a behavioural reading, but
it is not load-bearing for this decision.

### Prediction, locked before the re-score

Stated now so the re-score can falsify it. On the two pooled 13-question arms, with only the
pairing regex fixed and nothing else changed:

- **R1.** `real_election_001` ON recovers to ≥ 7/10 and `day_of_atonement_001` ON to ≥ 5/10.
- **R2.** The pooled ON run count rises by **10 to 18 of 130** (+7.7 to +13.8 pp).
- **R3.** The pooled ON − OFF delta lands in **[−3, +5] pp**, i.e. at or inside the 3.6 pp floor of
  record. OFF rises by **0 to 2 runs** (it has no doubled-quote instances; any movement is the one
  bare-citation case on the 28-question arm).
- **R4.** `scapegoat_001` and `simons_count_001` do **not** materially recover — they are the
  residual, and if they do recover, my attribution in §3 is wrong.
- **R5.** No question that currently passes starts failing.

Falsifiers: if R2 comes in under +6 runs, the regex is not the dominant mechanism and §3 overstates
it. If R5 breaks, the fix is too loose and step 1's second direction was undertested.

---

## What this does NOT solve

- **It does not flip the flag, and it does not settle whether ADR-0009 is good.** It says the
  instrument currently in front of the decision is measuring its own bug, and names the cheap fix
  that would let the decision be read.
- **Per-run attribution is not available, and this is a real limit on §3.** Only the representative
  run's answer text and gate detail are retained; the other four runs keep `answer_sha16`,
  `answer_chars` and `verification_failure`, but **not** `verified`. So the claim that the pairing
  defect drives all ten of `day_of_atonement_001`'s ON failures is an inference from one run per
  arm plus a consistent answer-length profile — not a measurement. The harness should record the
  `verified` flag per run; it currently cannot answer "which gate failed on run 3."
- **It does not establish a rate for the verifier defect.** Nine instances in 108 representative
  answers, all on one arm, over three pairs. That is a mechanism reproduced nine times, not a
  frequency for the corpus.
- **My own probe shared the blind spot it was measuring.** The first version took the span between
  the last two quote marks, which a doubled mark makes empty, and so reported "no quote found" for
  all seven cases — the same failure as the production regex, for the same reason. Corrected and
  noted because the corrected numbers are the ones above.
- **The three movers in ON's favour are unexplained.** `john_baptist_001` 3/10 → 10/10,
  `real_singing_psalms_001` 6/10 → 10/10, `real_covenant_monocovenantal_001` 7/10 → 10/10. Those
  are large and they are in the flag's favour, and I have no mechanism for them. They are not
  included in any argument here.
- **Nothing here is cited from a provisional arm's corpus axis.** The three pairs are git-clean and
  non-provisional on the git axis. Their corpus axis was marked provisional by the digest-only
  read fault, which ruling 1 reclassified as `differs-digest-only`; the figures above come from
  `run_passes` on disk and do not depend on that reclassification.
