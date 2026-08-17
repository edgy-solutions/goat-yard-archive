# ADR-0015: Apparatus Re-Extraction — Acceptance, Failure Taxonomy, and the Deterministic Witness

- **Status:** Proposed
- **Date:** 2026-08-16
- **Deciders:** Chris Nogradi

## Context

The footnote apparatus of Gill's 1766 Exposition was re-extracted with a decomposed pipeline (CV presplit → local VLM transcription → deterministic assembler), replacing the old overloaded single-VLM layer. Acceptance was adjudicated by a **stratified console pass** (ADR-0015's review-bandwidth spend — expert eyes on the known-hard classes, the rest covered by the assertion suite): 46 pages across collapse/stitch/acceptance strata, verdicts captured as the provenance record.

Reading the *actual output* rather than metrics (the standing discipline) surfaced a failure taxonomy a count-audit would have scored as success:

1. **Front-matter as apparatus** — 36 front-matter pages (frontispiece, foreword, memoir) ran through apparatus extraction and manufactured footnotes from body prose; 24 shipped silently as `OK`. p86 fabricated 18 Genesis footnotes from a *blank crop*; p4's model *refusal* ("this is a frontispiece, no footnotes") was wrapped as note `[^1]`.
2. **Segmentation-collapse** — the dominant hard failure: many printed footnotes folded into one note (p226: 20→1), sometimes with fabricated separator markers.
3. **Dropped non-Latin lemma** — the footnote's Hebrew/Arabic headword dropped, Latin gloss kept (p188/252/292/301/402/458).
4. **Hebrew glyph corruption / fabrication** — mostly single-glyph, but p379 invented a place-name (`אשר לי` → `אשדוד`, contradicting its own Latin gloss).

A four-way model bakeoff (qwen3.6:35b / gemma4:31b / qwen3.8 / qwen3.5:122b) on the validated failure set, all recrop-off, one model GPU-resident at a time, settled the model question with decision-grade numbers (Pearson/exact scored against the reconciled ground truth).

## Decision

### 1. Every stage must be able to represent "nothing here"

> A system must be able to represent "nothing here" at every stage, or its components' honesty becomes its fabrications.

One law, three siblings, each fail-loud in **code** (a stochastic reader never volunteers "nothing here," so the boundary cannot be delegated to it):
- **Intake gate** (`crop_gate`): a blank crop with notes → `FABRICATION_SUSPECT` (drop + flag); ink with no notes → `MISS_SUSPECT` (the inverse error). Corpus signature 1/958 — rare, but a silent-fabrication hole.
- **Boundary as a scan-verified book fact**: `commentary_start_page: 89` — images 1–88 return `no_apparatus` without extraction. Scan-verified, **not** stored-derived: p89 is the Genesis opening *with* apparatus the stored layer missed; trusting stored-defs-start=90 would have suppressed a real page.
- **Refusal-honor** (named, next): the model's own "frontispiece / no footnotes" is a `no_apparatus` signal, not note text.

### 2. The compositor's hanging indent is a deterministic footnote counter

The 1766 marker+gap+text convention encodes the note count in the left edge. `hanging_indent.count_notes` reads it off — **no model involved** — validated at **Pearson r = 0.90 over 321 anchored pages** (85% within 2; the +0.48 bias is CV catching notes the old layer dropped, so the imperfect reference *favours* CV). It is a witness, not an oracle, and carries a confidence flag that fires on ambiguous/full-width strips rather than forcing a count. It slots into four mechanisms: **rung-zero adjudication** of the dual-witness ladder (and detection of *correlated* collapse, which model-vs-model cannot see); pre-transcription collapse detection; marker-agnostic count reconciliation; and per-note crops that make collapse *structurally unrepresentable*.

### 3. Model routing is by measured signature, and the spend is model-choice, not model-size

- **gemma4:31b primary** (best Hebrew: 3 exact of the flagged glyphs; 6/6 lemma retention).
- **qwen3.8 fallback** on a measured collapse signature (8/8 segmentation, exact where others undershoot). Dispatch on the CV signature, never a page list — vol2 routes itself.
- Residual disagreement → **blind-retry** on localized crops (independence preserved), converge→ship, diverge→escalation with the note's gloss; hold/fold only as escalation metadata, never a shipping gate.

### 4. The dispute-resolution ladder (one artifact)

Every rung is cheaper and more deterministic than the one above it; each rung's leftovers are the next rung's intake; the expensive minds — frontier and human — touch only the residue that genuinely requires judgment.

| Rung | Mechanism | Cost | Nature |
|---|---|---|---|
| 0 | **CV count** (`hanging_indent`) | free | deterministic referee — the compositor's left-edge geometry |
| 1 | **dual-witness agreement** (two local models, independent) | free | correlated-collapse caught by rung 0 |
| 2 | **blind localized retry** (per-note crops, still local) | free | independence preserved; converge → ship |
| 3 | **text-based frontier adjudication** (`adjudicate_candidates`) | ~$0.0045/span | judge, not witness; **gated on internal evidence**, **verdict-only output** |
| 4 | **review queue** (human) | the scarce resource | only what nothing below could settle |

The compositor's geometry sits at the top of this column, free forever.

### Economics: judgment over text is cheap; perception at the frontier is where the tokens and the errors both live

A vision escalation ships the crop (~1,500–2,500 input tokens) and spends frontier capacity on perception it is *measurably worse at* than the local 35b. The text adjudication ships ~300–500 tokens — two candidate spans, the gloss, the citation, the question — and, by schema rule, returns a **verdict, not a transcription**: `{chosen: A|B|neither, disputed_span_correction, rationale, confidence}`, ~50 output tokens, never re-emitting the note. Measured unit cost ≈ **$0.0045/span** (opus), an order below what vision escalation would run. The verdict-only rule is not only cheaper — it is *safer*: a model that never re-transcribes **cannot introduce a third reading with its own fresh errors** (the tie-breaker-becomes-third-witness failure). Output constrained to a choice-plus-minimal-correction structurally cannot fabricate at length.

### The boundary that cannot be softened

A text-only judge can adjudicate only what the *text* determines. The self-glossing class — where the Latin, the grammar, the citation force the answer (`illis` is plural → final `ם`) — is its jurisdiction, and the intake gate (`has_adjudicating_material`) enforces exactly that. A dispute with **no** internal evidence (two spellings of a proper name, no gloss, no parallel, no citation) hands a text judge nothing but its priors — and a frontier prior confidently picking between `עליה` and `עליהם` with no `illis` to reason from is the Gerson failure wearing a robe. Those spans get the **review queue**, or one more perception attempt at the **local** layer (per-note crop, different model) — never a frontier guess dressed as adjudication. This gate does not soften when the queue gets long.

### The two meta-conclusions (verbatim)

**The Hebrew competence perimeter.** Of the six defects a fast human pass missed, five were Hebrew, and the worst — p379's fabrication — was one the reviewer *structurally could not catch*, because he does not read Hebrew. This is ADR-0015's scarce-resource rule discovering its own boundary: expert review is the scarce resource, and it has a **competence perimeter**. Hebrew fidelity therefore rides on the pixel-grounded validator fleet, not on human eyes, and the review process now routes around both the bandwidth limit and the competence limit.

**The 122b mechanism (why frontier inverts).** The 80GB model behaves like a *reasoner, not a transcriber*: it normalizes, summarizes, drops the Hebrew it can't confidently render (0/6 lemma retention, empty on 5/7 glyph pages, worst-of-four segmentation at 1/8), and *uniquely* resolves the single hardest glyph (`חח`) because raw capability does peak higher. That is the complete evidence set for escalate-the-adjudication-never-the-perception: local beats frontier on perception (measured twice), frontier beats local on reasoning-over-evidence (8/8 unanimous on self-glossing spans), and the 122b's split personality — drops everything, nails `חח` — is the exhibit showing *why* the division exists. **Big models don't out-see, they out-think, and thinking is precisely wrong for verbatim transcription.** A negative result (bigger is worse on the volume axes) is as decision-grade as a positive; the spend is model-choice among small models plus resolution (recrop), never size.

## What this does NOT solve

- **The counter is not an oracle** — r=0.90, MAE 1.4, 22% exact. It is trustworthy as a ±2 adjudicator and an unambiguous collapse detector (a 1-vs-13 gap is ~10σ past the noise), but it must not be treated as an exact note count. Full-width notes (p546 class) degrade it; the confidence flag routes those, it does not read them.
- **The prompt few-shot's *effect* on extraction is an un-run N≥6 gate** (prompt-changes-shift-verbatim-boundary) — assembly is tested, effect is not.
- **Router combined lift — CONFIRMED LIVE (2026-08-16 symmetric run).** gemma-primary recovers 8/8 segmentation on the failure set (fallback fired on exactly p129/p146), *and* holds all 50 clean pages (0 seg-regressions, 0 Hebrew-drops vs incumbent qwen3.6; better Hebrew on p516/p925). The bias objection is answered: gemma-primary holds the incumbent's wins, not just wins on its losses. No longer stub-only.
- **Segmentation-collapse — DISSOLVED IN THE PIPELINE (2026-08-16 per-note run).** Per-note pre-segmentation (one crop per hanging-indent note-start) recovers 8/8 with gemma *alone*; the two pages the router needed the qwen3.8 fallback for are dissolved unaided. The router is thereby demoted from primary defense to **residual handler** for the low-CV-confidence (full-width) pages per-note can't pre-segment. Two costs remain: per-note count is bounded by the counter (r=0.90/MAE 1.4 — undercounts true count slightly, never collapses), and per-note runs one VLM call per note (~1 note/9s), a real corpus-scale tradeoff vs the router's one-call-per-page.
- **The dropped-lemma severity is unresolved.** Whether a dropped Hebrew headword is "minor" (gloss survives) or "wrong" (subject lost) is a standing human call; the pipeline flags it deterministically but does not decide it.
- **Refusal-honor (sibling 3) and the segmentation-collapse CV pre-segmentation are named, not built.**
- **The worst fabrication (p379 `אשדוד`) is rare stochastic variance, not reliably reproducible** — it appeared in 2 historical runs, 0 of 5 fresh ones. Coverage rests on the disagreement net catching it (it did), not on eliminating it at the source.
