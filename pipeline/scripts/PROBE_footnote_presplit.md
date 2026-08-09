# Gate artifact #2 — CV-presplit probe (footnote apparatus re-extraction)

Companion to `HANDOFF_hebrew_census.md` (roadmap) and `footnote_structural_census.py`
(gate artifact #1). Read both at the gate. Script: `cv_footnote_presplit.py`.

## What this probe answers
The structural census (#1) closed **repair** on structural grounds (no consistent marker
convention to conform to). That left the three-outcome gate at **re-extract vs
defer-as-images**, which turns on one question the census could not touch:

> Is the apparatus layout deterministically solvable, and is a re-extraction of the
> footnote layer *good enough to trust*?

## Layout, verified (was assumed)
The apparatus is NOT "a two-column block below the body." Each page is split by a **centre
vertical rule** into two columns, and **within each column** a **horizontal rule** (often a
SHORT, partial-width printer's rule — this broke the first detector) separates that column's
body from *its own* footnotes. Reading order = left-column notes, then right-column notes.
This is the source of the census's `a–e … w–z` letter anomaly: per-column letter runs, not a
broken sequence.

## The deterministic presplit (numpy + PIL, NO cv2, NO model)
`cv_footnote_presplit.py`: vertical-divider (min-darkness gutter near centre) → per-column
horizontal-rule (topmost row whose longest CONTINUOUS dark run exceeds an absolute floor —
text never runs continuously that far; a short rule still clears it) → crop each column below
its rule → **vertical-concat left strip above right strip** (linear reading order) → 2× upscale.

**Validated** on 11 vol1 probe pages (worst-apparatus + continuation pairs from the census
repair queue): all 11 yield a valid divider + both rules. Three inspected pixel-by-pixel:
- **p100** — clean two-column apparatus (`q–u` | `w–z`): correct, complete.
- **p473** — full-width continuation page incl. the sole Hebrew lexicographer note
  (`n סגר עליהם clausit viam illis, Pagninus, præclusit sese illis, Vatablus`): correct, complete.
- **p571** — 15-note page (`e–m` | `n–t`): correct, complete.

Low-`xdiv` pages (p473/p571) turned out to be full-width-footnote pages (no gutter in the note
region), so the divider value is irrelevant to their split — the genuinely two-column page
(p100) got the correct centre divider. No truncation on any inspected page.

## Lever F (hint quality) — measured, FREE
Per-region Tesseract (`--psm 4`) on the cleaned strips returns **near-perfect,
correctly-ordered** note text on all three pages — reading order perfect, citations clean
(only 1766-type diacritic misses, e.g. "Cosmupeceianm"→Cosmopœiam). Even the Hebrew note `n`,
which Tesseract-eng cannot read, keeps its **position and Latin gloss** — precisely the aligned
per-note hint a VLM needs, and the opposite of today's full-page hint (split at the *body's*
centre, scrambling the footnote columns). **A free, weak OCR engine reads the cleaned strips
well ⇒ the failure was layout, not legibility.**

## Stored-vs-presplit diff on the SAME pages (the re-extract case, made concrete)
The current overloaded single-call output (`page{N}_image1.md`) against the presplit ground truth:

| page | truth notes | stored notes | stored failure |
|---|--:|--:|---|
| p100 | 9 (`q–u`+`w–z`) | 9 | left column silently **re-lettered `q–u`→`a–e`** — printed anchors no longer match the page |
| p473 | 14 (`a–h`+`i–o`) | 9 | **5 notes dropped: `d,g,h,m,n`** — incl. the ONLY Hebrew note (`n`); + digit errors (p.82→"89", c.29→"89") |
| p571 | 15 (`e–m`+`n–t`) | 15 | right column **re-lettered `n–t`→`a–g`** → **3 duplicate anchors** (`c,f,g` twice), right column mis-anchored |

On three real pages the overloaded pipeline **drops notes, re-letters anchors, and collides
markers**; the deterministic presplit recovers every note in correct reading order. Note-loss
is invisible to the span census (a dropped note contributes zero spans — refinement C): p473
alone lost 5/14 notes including its only Hebrew span.

## Transcription N-way — MEASURED (local Ollama + one OpenRouter ceiling call)
Ran per-page transcription on the presplit strips (decomposed job = transcribe only,
`think:false` — runaway thinking on qwen3.6 hit `done_reason=length` and returned EMPTY at
num_ctx 16384; disabling thinking fixed it and cut latency to ~8–23s/page). Scored against the
three pixel-inspected ground-truth pages.

**Structure/Latin/English — local qwen3.6:35b STRICTLY DOMINATES stored on every page:**

| page | qwen3.6:35b on presplit | stored (overloaded single-call) |
|---|---|---|
| p100 | 9/9 notes, correct text/order | 9/9 but re-lettered `q–u`→`a–e` (anchor drift) |
| p473 | **14/14**, digits correct (p.307, c.29, l.2) | **9/14 — 5 dropped incl. only Hebrew note**; digit errors |
| p571 | **15/15, true `e–t` letters, no collision** | 15 defs, **3 duplicate anchors** (right col mis-anchored) |

**Hebrew of note p473-`n` (truth `סגר עליהם`) — the crux, and the surprise:**

| model | reading | note |
|---|---|---|
| **qwen3.6:35b (local, newest)** @2× | `סגר עליה` | 6/7, only final `ם` dropped — **best of all** |
| **qwen3.6:35b (local)** @~6× isolated | **`סגר עליהם`** | **7/7 CORRECT** — resolution closes the gap |
| qwen2.5-vl-72b (OpenRouter) | `סגר אלהים` | word 1 ✓, word 2 wrong |
| qwen3-vl-235b (OpenRouter, $0.0022) | `דָּרַךְ עֲלֵיהֶן` | both words wrong |
| qwen3-vl:32b (local, older) | `נָגַד לְבִי` | fully wrong |
| glm-ocr:bf16 (local) | `כנסית` | fully wrong; also dup-output, digit/marker slips |

Two decision-grade findings:
- **Frontier buys nothing here.** A 235b Chinese VL reads the Hebrew *worse* than the local 35b,
  and costs money. The residual glyph gap is bounded by the SOURCE (worn small-type unpointed
  1766 Hebrew), not model size — so the lever is **resolution/preprocessing, not a paid model**.
- **The lever works locally.** Same model, same page, ~6× vs 2×: `סגר עליה` → `סגר עליהם`.
  Feeding the apparatus strips (or Hebrew sub-crops) at higher upscale recovers the Hebrew
  **locally and free.** (Total OpenRouter spend for the ceiling check: ~$0.003.)
- **Marker identity is deterministic — confirmed in the wild (refinement J / standing law).**
  qwen3.6 preserved true letters on p571 (`e–t`) but renumbered on p100 (`q–u`→`a–i`), biased by
  the prompt's `(a,b,c,…)` example. Irrelevant to the real pipeline: the assembler assigns
  canonical markers by POSITION and pass 4 links anchors — the model's letter output is
  discardable. The probe just demonstrated why the assembler must own the marker, not the model.

## What this probe does NOT establish (the named limit)
- **Scored on 3 pixel-verified pages, not all 11.** The other 8 (incl. continuation pairs)
  presplit cleanly but were not transcription-scored against hand ground truth. The re-extraction
  build should score a larger sample, and add a **fail-loud note-count/anchor assertion** per the
  standing law (deterministic property → assertion watches it).
- **Cross-page stitching not built.** Continuation pairs (p558→559, p600→601→602) presplit
  cleanly, but the join pass (continuation-in = strip opens with no marker; continuation-out =
  note ends mid-sentence at strip bottom) belongs in the re-extraction assembler.
- **Hebrew resolution lever validated on ONE span.** `סגר עליהם` recovered at 6×; the
  re-extraction pass should upscale apparatus regions (or Hebrew sub-crops) by default and
  spot-check, not assume every span closes as cleanly.
- Running heads / signature marks (`VOL. I.—OLD TEST.`, `3 D`, `3 Q 2`) sweep into the strip;
  trivially trimmed in the assembler, harmless to the VLM.

## Gate conclusion → RE-EXTRACT, LOCAL, FREE
1. Repair — closed (census: no convention to repair against).
2. **Re-extract — VIABLE and clearly best.** Deterministic presplit solves layout; local
   **qwen3.6:35b** on the strips strictly dominates the stored layer (recovers dropped notes,
   no anchor collisions, correct digits) and reads the hardest Hebrew apparatus **at or above
   frontier**, with the residual closing at higher resolution. Runs local, free, ~8–23s/page —
   fits Chris's "runs all week, don't pay for frontier" constraint exactly.
3. Defer-as-images — no longer needed for the apparatus: the bar it had to beat is cleared.

**Implication for V3 / Psalms:** apparatus (and Psalms from day one) ingest through the decomposed
design — deterministic presplit → local qwen3.6 transcription (think off, resolution-boosted on
Hebrew regions) → code-assembled canonical markers + anchor-match → fail-loud count assertion.
No frontier API in the hot path. Model tier is settled by evidence: **latest local Qwen VL**,
not a paid frontier, and not the older qwen3-vl/glm-ocr.
