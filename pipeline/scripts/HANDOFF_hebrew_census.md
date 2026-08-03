# Hebrew-span census → V2 validation: handoff roadmap

Read this before resuming. The V1 detector (`hebrew_span_census.py`) is committed and
controls-validated; the gate is set. Everything below inherits its shape from two cheap
measurements that haven't run yet.

## Current state (trustworthy)
Three tiers + apparatus + garbage, four control jaws passing (ṭaʿun→extra-biblical,
bereshit→case-1, mishpechoteihem→biblical, vol7 case-1==0):

| tier | vol1 | vol7 | total |
|---|--:|--:|--:|
| case-1 (passage's own verse) | 18 | 0 | 18 |
| biblical-cross-ref (easy, Tanakh-checkable) | 62 | 2,378 | 2,440 |
| extra-biblical in-line (HARD, V2's first sample) | 28 | 757 | 785 |
| **apparatus (footnote)** | **1,087** | 19 | **1,106** |
| garbage | 46 | 47 | 93 |

- **91% reference gap, measured:** case-1 collapsed 1,001→18. The sweep is the first
  ground-truth pass over ~91% of the corpus's Hebrew. (ADR-0015 context claim.)

## Pre-V2 sequence (the gate)
1. **Structural census — free text checks, no model calls.** Letter-sequence gaps in note
   blocks, text-marker↔note-count mismatches, continuation-page flags, orphaned anchors →
   per-volume structural error rates + sized repair queue.
2. **Ten-page CV-presplit probe — TARGET vol1 (see refinement B).** deskew → CV rule-line
   split → CV column-split + vertical concat → 2× footnote upscale (with a 1×/2× compare) →
   current-model per-region transcription → marker match → diff vs stored.
3. **Gate — Chris reads structural rates + probe diffs together → one decision:** repair the
   apparatus span-by-span, or re-extract the footnote layer wholesale. Finalizes V2's sample.
4. Then V2 → V3 (cost/model-tier, apparatus possibly its own tier) → V4 (review queue +
   provenance) → ADR-0015 + the model-tier ADR, written from evidence.

## Three refinements to carry in (from the census read)

**A. Matres-rejection is a validated PATTERN, not a one-off.** Twice this session a proposed
*loosening* was rejected by symmetric controls and the problem then dissolved *structurally*
instead: the global matres/skeleton collapse fixed its target plene words but would have
mater-matched ṭaʿun's ט-ע-ן into a biblical root (hard span routed around review — the one
failure direction the design prevents); the apparatus split then made the loosening
unnecessary — the in-line tier came clean with no loosening at all. **Lesson for the
Psalms-era matcher: when a loosening is tempting, first check whether splitting the
population correctly removes the need.** Build the control BEFORE the fix; keep it after.

**B. The apparatus problem lives in vol1, not vol7 — the probe's assumed target is inverted.**
1,087 of 1,106 apparatus spans are vol1 (Gill's Genesis Hebrew-lexicographer apparatus —
Pagninus, Montanus; philological machinery = the *hardest* material: lexicographer forms,
unpointed roots, abbreviated citations, small-type worst case). So: **the ten worst pages
come from vol1, the 1×/2× resolution compare runs on vol1 footnote strips, and
repair-vs-re-extract is functionally a vol1 decision.** vol7's 19 apparatus spans are a
rounding error either way. Do not build the probe against vol7 layout quirks.

**C. 1,106 apparatus is a FLOOR, not the count.** Missing markers, boundary bleed, and
orphaned notes are exactly the OCR failures that make apparatus Hebrew *invisible to the span
census* — a note the pipeline dropped contributes zero spans. Part of the structural census's
job is to measure how much apparatus **isn't in the text layer at all**. That number is the
strongest input to the *re-extract* side of the gate: repair can only fix what was captured.

## Corpus-pipeline context for the probe (verified this session)
The current footnote path is a **single overloaded VLM call** (`ExtractTextFromImage`,
`baml_src/main.baml`) doing body + two-column-merge + footnote-detection + marker-linking +
multilingual transcription at once on the full page; `get_md.py` is layout-naïve (single
page-center split, no rule-line) and injects a **one-verse** Hebrew reference
(`get_hebrew_verse`); `fixup_ocr.py` separates footnotes post-hoc by text-alignment + a magic
500px Y-gap. The CV-presplit design removes the layout burden from the model deterministically
— which is why re-extraction (footnote regions only, body untouched) is a live gate option.
Psalms ingests through the decomposed multi-pass design + wide reference window from day one,
regardless of the existing-corpus decision.

## Parallel / loose ends
- **Parallel, no dependency:** ADR-0009 **B1 schema commit** (migration long pole) — landable cold.
- **Chris's, in order:** (1) corpus **sync + fingerprint** FIRST (Dagster approaching; every
  slipped week adds sync ambiguity); (2) PuritanBoard post (no decay; ṭaʿun / three-corruptions
  exhibit strengthens as the comparison page firms up).

## vol3
Never normalized (raw OCR attempt only); deleted-for-now from disk (recoverable via git);
on the Psalms-era ingestion queue. The detector prints a fail-loud ABSENT line for it.
