# RESPONSE to Golden Chain: does fix A's rule recogniser accept a single printed rule? (2026-10-25)

Answered from code at tag `substrate-v0` = 3d0b03e (branch body-path-a2). The request came through Chris, so there is no request file. Your measurement is in your repo at `docs/sources/gill-column-rule.md`: single rule 20/20, median width 14 px, gutter median 131 px at your resolution. I read it as relayed and have not opened your repo.

## Your measurement against the recogniser
- **Single rule 20/20.** This is the case accepted by construction (below). On that point nothing here blocks you.
- **Width 14 px.** On a single rule `half_w` ≈ 7. At vol.1 resolution this is under the gutter cleaner's `DOUBLE_RULE_MAX_W` 24.
- **Gutter 131 px.** This is well inside the ±300 px search window around `xdiv`.
- **I can't check scale.** Every pixel constant below is in vol.1 pixels, and I don't know the ratio of your resolution to ours. `RULE_MAX_RESID_PX` 15 and `DOUBLE_RULE_MAX_W` 24 do not scale themselves. If your scans are at a different DPI, those two constants are where a single rule would fail, not the fact that it is single.

## Answer
**Yes, a single rule is accepted. It is accepted by construction, and single vs double is not a parameter.**
- No code counts rule lines, and there is no switch.
- A single line passes as a one-run cluster. A double passes because its two lines merge into one cluster.
- Nothing in the output records which was found, except the width (`half_w`).

## Code path (pipeline/reextract/verse_regions.py at 3d0b03e)
1. `analyze_page_s1` calls `locate_column_rule(ink, geom_record)` (verse_regions.py:652 → :368).
2. The body (y 700 → footnote rule − 20) is cut into 300 px strips within ±300 px of geometry `xdiv`. Each strip passes its per-column ink fractions to `_rule_clusters` (:340).
3. **The cluster rule is the whole recogniser.**
   - Columns with ink fraction ≥ `RULE_COL_FRAC` (0.59) form runs.
   - Runs separated by white ≤ `RULE_MERGE_GAP_PX` (20) merge into one cluster. That merge is how a double becomes one cluster; a single line is a one-run cluster with nothing to merge.
   - Each strip keeps its cluster with the largest width × mass.
4. **Acceptance:**
   - ≥ `RULE_MIN_STRIPS` (3) strips carry a cluster, and ≥ `RULE_MIN_STRIP_FRAC` (0.5) of the strips do;
   - a line fit centre(y) = slope·y + c0 has max residual ≤ `RULE_MAX_RESID_PX` (15).
   - Otherwise it abstains with `no_rule` or `track_nonlinear`.
5. **Output:** `half_w` = median cluster width / 2; `pad` = ceil(max residual). Columns are split at centre ± half_w ± pad (`left_edge` / `right_edge`, `_mask_column_by_split`).

## Verified, not only read
I ran an off-repo check on the committed synthetic fixture (`test_verse_regions._cs_page`: two 6 px lines, 6 px apart, slanted):

| Rule | status | c0 | half_w | strips |
|---|---|---|---|---|
| Double (as committed) | ok | 1939.4 | 8.5 | 13/13 |
| Single (right line removed) | ok | 1933.4, the remaining line's own centre | 2.5 | 13/13 |

**There is no single-rule test.** The committed column-rule tests use the double only (test_verse_regions.py:1423 onward). The check above is not in the suite.

## The three tuned constants
All three were measured on vol.1, which prints a double rule (207 pages, in the private measurement record). **A single-rule volume has never been measured.**

| Constant | Value | What it was tuned on |
|---|---|---|
| `RULE_COL_FRAC` | 0.59 | per-column ink fraction in a 300 px strip: type 0.18 vs rule 1.00 |
| `RULE_MERGE_GAP_PX` | 20 | midpoint of the 7 px inner gap of the double and the next mode, 32 px. **This encodes the double.** |
| `RULE_MAX_RESID_PX` | 15 | set equal to the double's flank (`DOUBLE_RULE_FLANK_PX`). **This encodes the double.** |

## Limits you should know about
1. **A single rule and an unmerged double look the same.** If a double's two lines sit more than 20 px apart, each line becomes its own cluster. The strip then keeps one of them, and the centre is off by half the spacing. The recogniser cannot tell that case from a true single rule, and records nothing that would.
2. **Faint or broken rules can be missed.** A line must ink ≥ 59 % of a strip's 300 rows at some column to count. That holds for a single line on its own; a double gives no redundancy here either, because each line is tested separately.
3. **The step-2 gutter cleaner also accepts singletons, by design.** `_treat_double_rule_as_white` (verse_regions.py:296) says so in its docstring ("'merged' includes singleton clusters"). Its limits are `DOUBLE_RULE_MAX_W` 24, flank 15, and within 60 px of xdiv.

## What this does NOT solve
- It does not re-run your measurement or check its resolution against vol.1. The comparison above uses the three figures as relayed.
- It adds no single-rule test and no `rule_kind` field. If you need either, request it; it would go into a new substrate tag, not `substrate-v0`.
