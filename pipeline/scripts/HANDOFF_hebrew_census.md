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
   **CONSTRAINT (D):** markers are lowercase letters REUSED across paragraphs on a page, so
   gap-detection must operate **per anchor-scope, not per page**, or it reports phantom gaps
   and phantom duplicates everywhere. **Verify the actual 1766 convention first** on a few
   pages — restart per page? per column? per paragraph? — that answer sets the scope for
   both this census and the probe's marker-matcher (pass 4).
2. **Ten-page CV-presplit probe — TARGET vol1 (refinement B) — THREE-WAY matrix (E).**
   deskew → CV rule-line split → CV column-split + vertical concat → 2× footnote upscale
   (1×/2× compare) → per-region transcription → marker match → diff vs stored. Run the
   transcription pass as a **3-way**: (a) current **qwen3-vl** (the operative model, local
   Ollama) on the presplit inputs, (b) a **frontier model** on the same inputs, (c) the
   **stored output** (old single-call architecture). This separates the two conflated
   variables — *architecture* (overloading) vs *model capability* (vintage/size). Because
   the pipeline is decomposed, each pass diffs separately, so you see WHICH pass the old
   architecture failed (region-find vs transcription vs marker-link), not one entangled diff.
   Also test the **hint-quality lever (F)**: per-region Tesseract on the cropped strips gives
   the model an aligned word-hint, vs today's scrambled full-page hint — plausibly a bigger
   lever than resolution, so measure it alongside 1×/2×.
3. **Gate — Chris reads structural rates + probe diffs together → one decision:** repair the
   apparatus span-by-span, or re-extract the footnote layer wholesale. **Tilt: toward
   re-extract** — there is no tuned footnote-detection stage to repair (the presplit is the
   *first existence* of one; today's 500px Y-gap is a text-space confession, not a mechanism).
   Repair can only fix what was captured; the probe measures re-extraction quality directly.
   If qwen3-vl-on-solved-layout ≈ frontier, Psalms stays **local + free** with the presplit
   doing the work — a materially different cost picture than routing apparatus through a
   frontier API; V3 prices whichever the probe shows.
4. Then V2 → V3 (cost/model-tier, apparatus possibly its own tier) → V4 (review queue +
   provenance) → ADR-0015 + the model-tier ADR, written from evidence.

## Post-structural-census additions (banked 2026-08 — probe + gate + design law)

**Structural census ran (`footnote_structural_census.py`). Headline: the apparatus has NO
consistent marker convention** — ≥3 syntaxes (`[^a]:` 64%, `^a^` 32%, `[^a^]:`/hybrid ~4%,
12 pages ref-syntax≠def-syntax). 349 apparatus pages, **60% structurally broken** (repair
queue); damage floor 56 lost note-text + 71 lost anchors + 26 large anomalies; **333
continuation notes** cross page boundaries. Caveat: small letter-gaps (132) overlap the 1766
printer's j/u-v skips → NOT counted as damage (only orphan_ref/def + big_gap are clean).

**G. Repair is closed on STRUCTURAL grounds, not just the numbers.** Repair presupposes a
target convention to conform to; there isn't one — the VLM invented format per call, so a
"repair" would first have to *impose* a standard on 349 pages of freeform output = re-extraction
with worse provenance. Even at half the damage numbers, "no stable structure to repair against"
holds. The format lottery also infects every future consumer (S2 comparison page,
footnote-anchored retrieval, provenance) — re-extraction retires the lottery, not just the spans.

**H. The gate is THREE-outcome, not two.** This artifact establishes *repair is not viable*; it
does NOT establish *re-extraction is viable* — that's the probe's half, genuinely open. Outcomes:
**repair / re-extract / defer-as-images** (S-plan already renders footnotes as scans, so
"apparatus stays image-only until model capability catches up" is a legitimate result). The
probe's bar is therefore **"good enough to trust," not "better than the dead alternative."**

**I. Probe page-selection MUST include ≥2 continuation-note page-pairs.** The current pipeline
is per-page with zero cross-page awareness, so the 333 continuation notes are stored as
disconnected fragments (and pollute orphan counts on both sides). The decomposed pipeline needs
a **cross-page stitching pass**: detect continuation-in (footnote block opens with no marker
letter) and continuation-out (note ends mid-sentence at strip bottom), join across the boundary.
If the ten vol1 probe pages contain no continuation pair, the probe validates a pipeline that
handles the easy 60% and silently fails the hardest structural case — the exact validation gap
this project keeps catching.

**J. FORMAT IS A PROPERTY OF ASSEMBLY, NOT MODEL OUTPUT (the corrected design).** In the
decomposed pipeline the model never chooses a format at all: pass 3 transcribes note *text*
from a solved layout, pass 4 matches markers↔anchors, and **the pipeline CODE assembles output,
emitting canonical `[^N]:` itself.** Format becomes unbreakable by construction (same move as the
schema making Zone-3 closers unrepresentable), and the transcription prompts get *shorter* —
honoring the original overload concern more fully than either existing pass. **Do NOT build a
deterministic canonicalizer for the EXISTING corpus now** — the gate tilts hard to re-extract,
which produces a clean layer natively; the census parser is already format-agnostic for interim
readers. Canonicalizer logic lives once, in the new pipeline's assembler. (Revisit only if the
gate lands on defer-as-images.)

**STANDING LAW (this session's, Chris's):** *is this job's output a deterministic property?
Then a model may not own it, and an assertion must watch it.* Marker syntax is deterministic;
it was assigned to a text model (normalize_markdown) and never asserted → 349 pages of drift,
silent until the census parser whipsawed 2,542→96→stable trying to read it. Sixth appearance of
the one-sided-boundary pattern (assumed output contract, never asserted). Every pipeline stage
gets this test.

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
500px Y-gap. Note the `ocr_text` hint the VLM receives is Tesseract's **layout-naïve** output,
which splits the footnote block at the **body's** center line — so in exactly the region where
the model most needs help, its hint is systematically scrambled (footnote columns interleaved
at the wrong boundary). Per-region Tesseract on presplit strips fixes this for free (lever F).
The CV-presplit design removes the layout burden from the model deterministically
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
