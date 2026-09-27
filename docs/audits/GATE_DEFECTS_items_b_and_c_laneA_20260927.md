# Items (b) and (c), diagnosed before implementing either — and a correction to ruling 1's table

Lane A, 2026-09-27, while the item (a) noise-floor arms ran. All findings below are from
artifacts already on disk (`evals/output/adr0009_flag/{off,on}_20260927d`) and from reading the
code. **No model call and no new run was needed for any of it.**

## (c) `partial_match_sids` is unreachable by construction, not merely empty

`backend/main.py:954-966` fills it only when **both** hold:

```python
refused = len(answer_sids) == 0              # zero SIDs in the answer text
...
if refused and reasoning_text:               # AND the predictor produced reasoning
```

The response's `reasoning` field is the same variable (`main.py:1130` returns
`locals().get("reasoning_text")`), so the recorded artifacts are a faithful witness of it. Counted
across both arms:

| arm | responses with non-empty `reasoning` | refusals (`refused: true`) | refusals with non-empty `reasoning` |
|---|---|---|---|
| OFF | 25 / 28 | 2 | **0** |
| ON | 21 / 28 | 7 | **0** |

`reasoning_text` is non-empty precisely when the model answers and empty precisely when it
refuses. The two conditions are mutually exclusive in practice, so the branch cannot fire. **The
field is dead by construction**, which is why it was empty 28/28 on both arms — not bad luck, and
not a sampling question that more runs would settle.

**Recommendation: retire the field.** Its stated purpose — "you can still click these to read what
the model considered" on a refusal — is the *same behavior* item (b) exists to restore, and item
(b) restores it in the place that reaches the user: the answer text, with citations. A second
channel for it, gated on a condition that never holds, is a channel that can only ever report
"nothing here" while the real material is being discarded elsewhere.

Born-test before retiring, per Chris's item (c): extract the block into a pure function and assert
(1) a crafted refusal-with-SIDs-in-reasoning **does** yield sids — proving the logic is correct and
the *condition* is what is wrong — and (2) the real recorded refusals yield none. Retire on that
evidence, not on this reading alone. Deferred until the arms finish, because `backend/main.py` is
on the eval run path.

## (b) The refusal gate is two literal strings, and they are the ON template verbatim

`evals/run_eval.py:56-79`:

```python
REFUSAL_MARKERS = (
    "regret that the provided extracts",
    "do not appear to address this specific inquiry",
)
def is_refusal(answer): return any(m in answer.lower() for m in REFUSAL_MARKERS)
```

Every ON refusal in the recorded arm is **exactly 242 characters** and contains **both** markers —
the identical stock template every time, verbatim:

> *"I regret that the provided extracts from the Doctor's writings do not appear to address this
> specific inquiry. Could it be that you are looking for something not in the library (Exodus,
> Genesis, John, Leviticus, Luke, Mark, Matthew, Numbers)?"*

**So item (b) as ordered can pass its own gate by rewording alone.** Change the refusal variant's
`@description` so the model says "The library does not contain…" instead of "I regret that the
provided extracts…", change nothing about the behavior, and `is_refusal` returns False for all
five questions, `refusal_correct` climbs 23 → 28, and the gate reports success. That is a gate on a
string, not on a behavior — the same shape as the ADR-0009 schema passing 120/120 while the
behavior was gone.

**This must be fixed before (b), not after.** Add a behavioral signal **alongside** the lexical
one rather than replacing it, so every historical number stays comparable and the divergence
between the two is visible:

- `answered_substantively` — the answer cites ≥ 1 SID that is in the retrieved context.
- Report both, and treat a question where the two signals **disagree** as a case to read, not to
  score. The disagreement set is the interesting output.

Replacing `is_refusal` outright would silently rewrite every prior arm's `refusal_correct` and
destroy the comparison ruling 1 rests on.

## Correction to ruling 1's over-refusal table: four are real, one is a gate artifact

`ADR0009_FLAG_RESULT_laneA_20260927.md` lists **five** over-refusals. Re-read against the answers:

| question | OFF answer | ON answer | verdict |
|---|---|---|---|
| `real_moses_death_001` | 244 ch, **1 SID**, names the gap then cites Aaron's death | 242 ch template, 0 SIDs | **real regression** |
| `real_christophanies_001` | 1075 ch, **4 SIDs** | 242 ch template, 0 SIDs | **real regression** |
| `real_imprecatory_psalms_001` | 531 ch, **2 SIDs** | 242 ch template, 0 SIDs | **real regression** |
| `real_universal_atonement_001` | 566 ch, **1 SID** | 242 ch template, 0 SIDs | **real regression** |
| `real_gill_aquinas_001` | 65 ch, **0 SIDs**: *"The indexed corpus does not contain Gill's commentary on Aquinas."* | 242 ch template, 0 SIDs, and it **names the books that are in the library** | **gate artifact — ON is arguably better** |

OFF's `gill_aquinas` answer is a refusal in plain English that the two-string detector cannot see,
so OFF was scored as having *answered* it (`refusal_correct: True`, `expected_behavior: answer`).
ON's reply is scored as a refusal. Neither surfaces adjacent material or a citation; ON at least
tells the reader which books exist. **The gate ranked them backwards.**

Two further precisions on that document:

1. Its five-row table's column header reads "OFF → ON refused" and its values come from the
   server's `refused` field, while the aggregate `27 → 23` comes from the harness's lexical
   `refusal_correct`. Both statements are true of their own signal, but they are presented in one
   section as one measurement. For `real_gill_aquinas_001` the two signals **disagree on OFF**
   (server: refused; harness: answered), which is exactly how the artifact hid.
2. The arithmetic is unchanged and still consistent: five `expected_behavior: answer` questions
   lost `refusal_correct`, one `refuse` question gained it, 27 − 5 + 1 = 23.

**What this does not change:** the flag decision. Four genuine regressions remain, each replacing
cited adjacent material with an uncited stock template, all four with **identical retrieval** to
OFF (12 citations, `verified: True`). The mechanism — the typed refusal variant discards what OFF
surfaced — is unaffected. What changes is that the headline count is **four**, and that item (b)
cannot be gated with the instrument as it stands.

## Order this implies

Chris's ordering has (b) as the next item. I am not reordering it, but (b) has a prerequisite that
did not exist when it was written: **add `answered_substantively` to the harness and re-score the
two recorded arms with it before touching `baml_src/gill_answer.baml`.** Re-scoring is free — the
answers are on disk — and it establishes what the four regressions look like under a gate that
reads citations instead of two phrases. Without it, (b)'s rerun cannot distinguish a fix from a
rewording.

## What this does NOT solve

- It does not measure how often the two signals disagree across all 28 questions; only the seven
  refusal-relevant ones were read. The re-score above is what would answer it.
- It does not establish that `answered_substantively` is the right signal for `expected_behavior:
  refuse` questions, where citing nothing is correct. That needs its own born-test per direction,
  since this is a binary behavior and a one-direction gate is half a gate.
- It does not touch `partial_match_sids` in code. Nothing here has been changed yet; both items
  wait on the arms.
