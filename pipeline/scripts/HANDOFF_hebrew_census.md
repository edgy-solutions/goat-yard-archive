# Hebrew-span census → V2 validation: handoff roadmap

Read this before resuming. The V1 detector (`hebrew_span_census.py`) is committed and
controls-validated. **Both gate measurements have now RUN and the gate is CLOSED** — see the
GATE CLOSED banner immediately below; the older "Pre-V2 sequence (the gate)" section is retained
as the record of how the decision was reached.

## ★ VOL1 INSTRUMENTED RUN — 958 pages, 2026-08-10 (the first corpus-scale look; the two-volume-dread answer)
**0 ERRORS across 958 pages** — the pipeline ran the whole corpus without a single crash. Status:
`no_apparatus 107` · `OK 215` · `ANCHOR_FLAGGED 611` · `STITCH_VIOLATION 25`. Of 851 apparatus pages:
25% clean, 75% flagged — **but the tail is ONE KNOWN CLASS, not unknown-unknowns:**
- **ANCHOR-LOSS dominates (620 pages, 3332 notes) — and 609 of 620 are FULLY unanchored (the old body
  has ZERO in-text anchors), only 11 partial.** This is the old-body defect measured at scale: the
  body layer dropped its in-text superscript markers ENTIRELY on ~72% of apparatus pages. The
  re-extracted notes are correct but have nowhere to attach. ⇒ **DECIDES Chris's deferred scope Q:
  in-text anchor RE-DETECTION is now NECESSARY, not optional** — "body untouched" can't yield a linked
  apparatus when 609 pages are anchor-barren.
- **STITCH_VIOLATION = 25 pages (2.6%), a small BOUNDED novel class** — 10 are full_width-mode artifacts,
  15 two-column (spot-check owed: real intra-page splits vs artifacts; base-md census said 0 cross-page).
- geometry: `two_column 724 / full_width 127 / no_apparatus 107`; recrop `279 accepted / 268 gated`;
  high-note-count (≥20) 12 pages (dense apparatus or over-seg — spot-check p171=29/p161=27).
- **TAIL VERDICT: the declining curve, not the monster.** ~98% of flags are ONE characterized class
  (anchor-barrenness) with a KNOWN disposition (in-text anchor re-detect); the novel residue is 25
  pages. The fail-loud architecture made the whole tail ATTRIBUTABLE — exactly what it was built for.
- **TWO OWED AUDITS (instrumentation gaps, honest):** (1) the gate-nikud audit couldn't run — `run_vol1`
  logged recrop COUNTS not change-texts, so "0 nikud accepted" is proven on the 27-page run but NOT
  audited across 958; re-run with change-text logging to close it. (2) the 15 two-column stitch pages
  need an eyeball. **Proposed eyeball sample (Hebrew-oversampled):** 109,188,230,286,379,458,520,619,
  750,831,4,100,323,593,761.

## GATE-NIKUD AUDIT — PASSED at corpus scale (2026-08-10, `nikud_audit_run.py`)
Re-ran the 375 recrop-active pages capturing change-texts (the counts-only vol1 run couldn't audit).
**0 gate failures across 279 accepted changes / 0 errors** — no accepted change contains nikud. The
ADR claim upgrades from "gate held on 27 pages" to "gate held on the CORPUS." Bonus visibility into
accepted changes (mostly genuine corrections beyond final-letters): `רָקִיעַ→רקיע` (strips nikud toward
printed form — the gate's intent), `κ χαο→רקיע` / `Χαο→רקיע` (base misread Hebrew as Greek garbage;
recrop fixed it), `אור→מאור`, `מקר→מקום` (letter recovery). **SCOPE CAVEAT the audit surfaced:** the
gate is a NIKUD+TRUNCATION guard, NOT full-correctness — same-length consonant SUBSTITUTIONS pass it
(`אלה→ברא`, plausibly a real Gen-1 correction but UNVERIFIED). Not a gate failure; these land in the
right net (two-model flagging + escalation tier catch the uncertain ones). Recrop-audit data:
`recrop_audit.jsonl`.

## ANCHOR RE-DETECTION — DECIDED (census-forced) + DESIGN: STANDOFF LINKAGE (2026-08-10)
The census (609/851 apparatus pages anchor-barren) converts "ship present-but-unanchored" from partial
to NEAR-TOTAL unlinkage → in-text anchor re-detection is NECESSARY. **Design decision (Chris): STANDOFF
linkage, NOT inline re-insertion.** The body text is load-bearing (SIDs, chunk boundaries, verifier
difflib targets, every eval assertion hang off its exact bytes); re-inserting superscripts INTO it
mutates the substrate for zero retrieval gain. Instead: anchors live in a SEPARATE annotation layer —
note N of page P attaches at body-position X (char offset OR phrase anchor, version-robust like the
alignment JSONs' start/end phrases) — **body text stays byte-identical.** The linkage layer carries
per-anchor provenance + confidence (`found-by-CV` / `placed-by-window-constraint` / `unfound-flagged`).
Visible superscripts, if ever wanted, compose at DISPLAY time from the standoff layer. The CV sub-build
proceeds as queued (localize superscripts in hi-res body strips, letter-scope windows constrain where
each anchor can fall, fail-loud on unfindable) — but emits standoff records, never edits the body. This
is the minimal-invasiveness rule (that protected the body from re-extraction) applied to its one defect.

**LINKAGE CORE BUILT (`standoff.py`, 2026-08-10).** `link_page(notes, body_text, profile, page)` →
standoff records with `body_char_offset` + version-robust `phrase_anchor` (the ~6 preceding words) +
provenance (`old-body-anchor` .95 / `unfound-flagged` 0) + `body_bytes_touched: 0` (invariant). Validated:
p100 (old body has anchors) → 9 linked, phrase-anchors exact (`[^1]`←`…Picherellus`, `[^2]`←`…a full
year`); p550 (barren) → 9 `unfound-flagged` `needs: cv-superscript-redetection`, body untouched. **REMAINING
(the hard sub-piece): CV SUPERSCRIPT RE-DETECTION** — localize the tiny raised markers in the hi-res
body strip (above the footnote rule), constrained by letter-scope windows, fail-loud unfindable; it
FEEDS positions into the built linkage layer. Careful validated build (same discipline as the glyph-witness).

## ★ ADR RESULTS-TABLE LINE (its own claim, not "corrected content"): RECOVERED CONTENT.
The re-extraction produced apparatus on **36 pages the old corpus had NONE** (image-only pages the
overloaded pipeline never OCR'd; see reconciliation). "Recovered content" ≠ "corrected content" — it is
corpus that did not exist before, and it is the line the library thesis ultimately rests on. Put it in
the ADR results table as its own row.

## PAGE-COUNT RECONCILIATION (2026-08-10, fail-loud membership rule — one explanation, not two counts):
the vol1 run walked **958 IMAGES**; the span census walked **871 base-`.md`** (858 `_normalized`). The run
is a SUPERSET: **87 pages are image-only (old pipeline never OCR'd them)** — of those, **36 HAVE APPARATUS
the old corpus lacks ENTIRELY** (a bonus: re-extraction recovers content that never existed in the old
layer), 51 are genuine no-apparatus (front-matter/plates/blanks). 0 base-`.md` pages are absent from the
run. So the two instruments don't disagree — the run is images, the census was markdown, and the delta is
the un-OCR'd image tail.

## GATE CLOSED — 2026-08-09 → **RE-EXTRACT (local, decomposed, free)**
Both gate artifacts are in hand and committed:
- **#1 repair census** (`footnote_structural_census.py`): closed **repair** — no consistent marker
  convention to conform to (≥3 syntaxes, 60% of apparatus pages broken, 127+ items unrecoverable
  from the text layer).
- **#2 CV-presplit probe** (`cv_footnote_presplit.py` + `PROBE_footnote_presplit.md`): opened and
  settled **re-extract** — deterministic presplit solves layout; local **qwen3.6:35b** on the
  strips strictly dominates the stored overloaded layer on every ground-truth page (recovers
  dropped notes, kills anchor collisions, fixes digits); reads the hardest Hebrew apparatus **at
  or above frontier**; residual closes with resolution. Cost ≈ 0.

Three-outcome collapse: **repair dead, defer-as-images unnecessary, re-extract wins.** The same
verdict IS the Psalms ingestion architecture — the gate decision and the new-volume pipeline
design merged into one build.

**Two exhibits to quote in the re-extraction ADR (evidence beats rule-statements):**
1. **Frontier-inversion / pixels-not-parameters.** On the hardest span (p473 note `n`, truth
   `סגר עליהם`) a 235b frontier VL read it *worse* than the local 35b; the SAME local 35b went
   `סגר עליה` (6/7, 2×) → `סגר עליהם` (7/7, ~6×). A 7× model buying nothing = the failure was on
   the INPUT axis, not capability — the mem was in the scan, the pipeline never delivered enough
   of it. Lever is resolution, not parameters or dollars. Same mechanism as the ṭaʿun find: the
   edition's hardest problems resolve at the pixel layer.
2. **Marker-identity dissociation (standing law, in the wild).** qwen3.6 transcribed p100's 9/9
   note *texts* flawlessly while *inventing* the marker letters (`q–u`→`a–i`, prompt-biased). The
   model's job (text) it did; the deterministic positional property (marker) it hallucinated →
   the assembler owns markers by position, the model's letters are discardable.

**Named limits → BUILD SPECS (not caveats) for the re-extraction pass:**
- Scored on 3 pixel-verified pages → the build's acceptance run scores a **larger truth set**,
  assembled ONCE during re-extraction validation and **doubling as V2's apparatus ground truth**
  (truth-set assembly is itself review-bandwidth spend — do it once).
- Cross-page **stitching is the FIRST work item** (measured population: 333 continuation notes;
  pairs p558→559, p600→601→602 presplit cleanly): continuation-in = strip opens with no marker;
  continuation-out = note ends mid-sentence at strip bottom; join across the boundary.
- Hebrew resolution is a **default policy, not an escalation branch**: apparatus strips render
  high-res by default (disk + seconds, free locally) — no 2×-then-6× logic nobody needs.
- Pipeline shape: presplit → local qwen3.6 (`think:false`) → **code-assembled canonical markers**
  + anchor-match → **fail-loud note-count/anchor assertion** (deterministic property → assertion
  watches it). No frontier API in the hot path. Model tier settled by evidence: latest local Qwen
  VL, NOT frontier, NOT older qwen3-vl/glm-ocr.

## Layer-tiering resolution (Chris's Q1: "fix the other ingestions?") — 2026-08-09
Do NOT regenerate load-bearing layers without evidence re-extraction beats repair. Tiering:
- **Apparatus (vol1+vol7 footnotes) = known-broken → re-extract now** (this IS the gate verdict;
  "fix the other ingestion" is already underway).
- **Body text = suspected-fine → VERIFY, don't re-extract.** Damage concentrated in the small-type
  footnote region; body is the large type in the simple layout. V2's in-line extra-biblical sample
  (785 spans) measures the body hit-rate — and specifically **disambiguates the case-1 collapse
  (1,001→18)**, which is currently ambiguous between "Gill rarely quotes the passage verse in
  Hebrew" (style) and "loss" — the structural census measured the apparatus only, so body-Hebrew
  damage is *unmeasured directly*. Re-extracting the body would produce a DIFFERENT text →
  invalidates every SID, chunk boundary, entity anchor, eval assertion. Only earns a case if the
  in-line sample comes back ugly, WITH numbers.
- **vol3 = never processed → new pipeline natively** (Psalms-era queue).
- Sequencing: apparatus re-extraction ∥ V2 in-line sample (different layers), both before Psalms.

## Entity-layer resolution (Chris's Q2: "test entity models + add symbolics?") — 2026-08-09
Current entities = older **xAI Grok**, ungrounded (E-11: LLM-assigned categories, no provenance,
"boost maybe / gate never") AND load-bearing (ADR-0010 derived constants, thesaurus bridges, eval
baseline all anchor to the current entity set). So: **probe, not migration.**

### Probe RAN 2026-08-09 — verdict: **gain is real, but NO clean model swap; harden then re-probe**
Reused `evals/entity_extraction_benchmark.py` (same prompt/schema/10-page fragmentation sample,
same within-page + cross-page analysis) + added a local-Ollama backend. Three backends on 10
pages: grok-4.20 (baseline=current approach), local qwen3.6:35b (candidate), deepseek-v3 (cheap
Chinese ceiling).

| metric (10 pages) | grok(base) | qwen3.6 local | deepseek-v3 |
|---|--:|--:|--:|
| entities | 196 | **301** | 201 |
| TypeOrSymbol | 12 | **24** | 19 |
| invalid categories | 0 | **13 (invented `ScriptureReference`)** | 0 |
| citations-as-entities | ~0 | **~26** | 0 |
| reliability | 10/10 | 9/10 (JSON) | 10/10 |
| cross-page cat-drift / name-drift | 5 / 3 | 3 / 3 | 3 / **0** |

- **"Beef up symbolics" VALIDATED:** both newer models ~2× grok's typology (24/19 vs 12). And the
  **Gill-grounded typology prompt** (anchor TypeOrSymbol to Gill's explicit "a type of / figure of
  / prefigured" language, antitype→description) improved PRECISION (dropped non-types: `Calphi` a
  name, loose `darkness`/`light`) AND completeness on type-rich pages (p720 1→3 incl. `blood of
  Christ`, p886 +`red cow`). Rough edges: once promoted the *antitype* (`Christ`) to a type, and
  duplicated — needs a dedup + antitype-in-description guard. Direction is exactly the bridge law.
- **But local qwen3.6 is high-recall / lower-discipline, NOT a clean win:** its +53% entities are
  ~half real (grok missed `atonement`, `divine/human nature`, `holy of holies`, `high-priest`,
  `tabernacle`) and ~half **scripture-citation pollution** (`Acts ii. 23`, `Leviticus ver. 7` …
  emitted as entities, in an invented `ScriptureReference` category + dumped in `Unknown`). It also
  MISSED abstract doctrine grok caught (`determinate counsel`, `mediator`, `two natures in Christ`)
  and under-tagged `OriginalWord` (2 vs grok 11).
- **The two flaws are the standing law, code-fixable — not model deficiencies. Do this in BAML,
  not raw Ollama `format:"json"`** (the probe used raw calls for speed; production belongs in BAML
  like the rest of the pipeline): (a) valid JSON — `format:"json"` handled it in the probe, BAML
  gives it for free; (b) category ∈ the 12-enum is deterministic → a **BAML enum-typed `category`**
  makes `ScriptureReference` *unrepresentable at the type layer* AND validates-and-retries —
  strictly stronger than `format:"json"`, which only guarantees parseable JSON (an invalid enum
  would still slip through and need a post-filter); (c) "a scripture citation is not an entity" is a
  deterministic pattern → a **regex citation-filter** strips the ~26 pollutants (same move as
  marker-identity in the footnote build). With those three guards, local's real gain (coverage +
  2× grounded typology, cross-page drift already ≤ grok, free) stands clean.
  **Also:** the re-extraction transcription (currently raw Ollama note-lines in `extract_apparatus.py`,
  a probe convenience) should become a **BAML function returning `Note[]`** for production —
  consistent with the rest of the pipeline and hands the assembler a typed list, not parsed lines.
- **deepseek-v3 is the disciplined turnkey alt:** zero invalids, best consistency (name-drift 0),
  solid typology (19), 10/10 reliable, cheap Chinese cloud — the low-effort option if local
  hardening stalls. grok (incumbent) is reliable but weakest on typology.

**Decision (regenerate-on-diffs-not-vibes): do NOT swap the entity layer now.** The evidenced next
step is a **hardened entity-extraction pass** — enum-constrained structured output + deterministic
citation-filter + Gill-grounded typology block (with dedup/antitype guard) — then **re-probe** the
hardened local vs deepseek vs grok, and only then eval-gate a swap (ADR-0010 constants re-derived,
N-run). Scripts: scratchpad `entity_probe.py` / `typology_variant.py` (probe harness + local
backend; fold `call_local` into the committed benchmark when the hardened pass is built).
- **Re-probe candidate set (add for the hardened run — not yet tested):** `gemma4:31b`,
  `gemma4:26b` (also `:12b`/`:e4b`), `gpt-oss:120b` on .169. Entity extraction is TEXT-only, so any
  strong local text model is a fair candidate, not just the VL ones.
- **Re-probe discipline (inherit from the two probes just run — regenerate-on-diffs applies to
  MODEL SELECTION too):** same 10 pages, same ground truth, per-model rows in the SAME table
  (coverage / TypeOrSymbol / invalid-categories / citation-pollution / cross-page drift /
  reliability). **Speed is a REPORTED COLUMN, never a disqualifier** — the footnote probe's lesson
  was the newest local model won on *accuracy* and speed was a bonus. Do NOT pre-eliminate a model
  on a speed prior ("31b may be slower than gpt-oss:120b", "26b may be ~as accurate as 31b" are
  HYPOTHESES the table tests, not selection inputs). If 26b lands ~as accurate as 31b, that's a
  *result the diff shows*, not a prior the selection encodes. gpt-oss:120b may be slow / CPU-spill
  at the sample's context — measure it and report it; don't skip it.
- **Hold the re-extraction trigger** to body-text conservatism — entities are a retrieval
  substrate; swapping = full eval-gate. Only on proven gains, never a drive-by.
- **Symbolics = extraction-of-what-Gill-SAYS** (probe-confirmed viable), NOT a Reformed typology
  knowledge graph (a semester); the deliverable is the Gill-grounded TypeOrSymbol block above.

## Library / profile-discipline — build spec (2026-08-09, before the re-extraction build)
The re-extraction pipeline is the **first book of a library**, not a Gill tool. Build it generic
**by discipline, NOT by framework** — no plugin architecture for hypothetical books (the
abstractions invented before the second book arrives are reliably wrong).
- **`book_profile.yaml` exists from day one, with a single entry.** Every book-specific FACT is
  quarantined there and **forbidden from pass code**: layout convention (horizontal rule,
  two-column apparatus, lowercase-letter markers, j-skip/u-v), reference texts + window (KJV +
  Hebrew Bible, wide), expected scripts (Hebrew/Greek/Arabic), output target, **entity category
  enum + typology grounding-language cues**. The passes (deskew → rule-line → column-split →
  region-transcribe → marker-match → assemble) contain NO book-specific facts. Generic by refusing
  to hardcode = a code-review rule, not an engineering project.
- **The assembler owns the output format** (already law): the model never knows if it's emitting
  SID-chunked markdown or typst. A second output target = a second assembler; extraction passes
  don't change. Proof-of-generic = running a Gill page and a Defoe/Bunyan chapter with only
  **profile + assembler swapped** (daughter's Bunyan/Defoe→typst work is the ideal second book:
  no Hebrew, no verse apparatus, different typography, different output). Until that second book
  runs, "generic" is a design discipline, not a claim — the diff proves it, not the intention.
- **The moat is the verification apparatus traveling with every book** — scan-beside-text,
  per-correction provenance, "check my work". Each author inherits the trust model, not just the
  extraction. That is what ad-wrapped text dumps cannot follow you into.

## Three-layer grounding — each matched to what the layer CLAIMS (2026-08-09)
Resolving Chris's "do we ground the category enum in a doctrinal dictionary?" — **no; the enum and
the thesaurus are different objects with different grounding registers.** Do not fuse them.
1. **Category enum = indexing taxonomy → grounded in the CENSUS (evidence), profile-scoped.** The
   12 labels assert what *kinds of things retrieval must distinguish*, not theology. Test is "do
   these carve the corpus at joints retrieval uses," which a scholarly source cannot answer
   (Muller organizes concepts for scholars; the enum organizes entities for a boost function).
   Grafting a systematic's loci (Soteriology/Eschatology…) = citable but useless discriminators =
   **grounding-theater** — especially since category is already "boost maybe, gate never"
   (ceremonial-homonym test), so no decision rides on it. The enum's grounding instrument IS the
   entity probe: which categories get used, which drift (cat-drift metric), which collapse, which
   absorb garbage (Unknown). A category models can't apply consistently isn't a real joint — the
   drift number is the citation. And the enum lives in `book_profile.yaml` (Bunyan carries
   `AllegoricalCharacter`; Defoe drops `TypeOrSymbol`) — a per-book list can't be grounded in one
   dictionary anyway.
2. **Category DEFINITIONS (per category) → grounded in the corpus's OWN language.** Where a source
   helps is *inside* a category's boundary rule, not the list. `TypeOrSymbol` = "what Gill names a
   type — anchored to his 'a type of / prefigured' language; antitype→description" (the
   probe-validated Gill-grounded prompt). Source = Gill's usage, better than Muller here: the
   corpus grounds its own hardest category. Same pattern if `Heresy` ever needs a boundary ("what
   Gill calls error," not a modern tradition's classification — else you leak tradition-judgments
   into the index, the answer-wall violation).
3. **Thesaurus (modern-term → Gill-vocabulary bridge) → grounded in CITED scholarship.**
   Muller-class *Dictionary of Latin and Greek Theological Terms*, per the bridge law (bridge may
   be built from anything citable). Still the queued follow-up; unchanged.
Each of the three now has a named provenance story; none is "the model felt like it."

## The durable division of labor (the library's economics)
Not irony — the correct, durable split: **frontier intelligence at DESIGN time, deterministic code
+ free local models at RUN time.** Claude's job was never to read the Hebrew; it was to find why
nothing could and fix the structure so a 35b on local hardware beats a 235b in the cloud. Every
added book inherits the trade: pay for thinking once, extraction runs free forever.

## BUILD REDIRECT 2026-08-09 — assembler-first, NOT stitching-first (measured)
Measured the continuation population before building the stitch pass (`measure_continuations.py`,
871 vol1 pages, base letter layer): **cross-page TEXT-split = 0 real cases.** candidate split-OUT
(last note not terminal-punctuated) = 6, all artifacts (signature marks `Y y`/`5 D 2`, Hebrew-word
endings, OCR-dropped periods); candidate split-IN (first note opens lowercase) = 2, both Latin
lexicographer glosses; **0 adjacent OUT/IN pairs.** Undercount worry closes: a spilled note shows
as a lowercase-opening leading note on the RECEIVING page (fires regardless of whether page N's
tail was dropped) — that signal fired twice in 871 pages, neither a cut sentence. Re-extracted
transcriptions of the 5 flagged continuation pages also all showed complete notes both sides.

⇒ The "333 continuation notes" are **sequence-continuation** (letter run spans pages, notes
complete = an *assembler marker-scope* job), NOT text-joining. **Chris confirmed the redirect:**
- **First work item = the core per-page pipeline + assembler:** presplit → transcribe (local
  qwen3.6, think:false, `format:"json"`) → **assembler assigns canonical `[^N]` by position** +
  cross-page marker-scope for sequence-continuation + body-anchor match → fail-loud note-count/
  anchor assertion.
- **Text-stitch = a fail-loud assertion + a profile-aware guarded branch** (near-empty for Gill;
  available for future library books with long footnotes) — NOT a standalone first pass. The
  assertion detects BOTH signals permanently: split-IN (leading note opens lowercase mid-sentence)
  AND split-OUT (trailing note not terminal-punctuated) NOT explained by the artifact whitelist
  (the 6 classified cases: signature marks, Hebrew-final, citation-final, OCR-dropped period).
  A genuine split anywhere ⇒ pipeline STOPS and says so (fail-loud makes building-nothing safe).
  Profile flag: `cross_page_text_splits: none_observed` (Gill vol1) — scoped to THIS book's
  measured reality, not baked into the pipeline for the next book to inherit blind.
- **The assembler is BORN TESTED** — it concentrates the most deterministic jobs (canonical
  markers, position-based identity, sequence-scope across pages, output format, later the typst
  backend), so it carries the most correctness weight and gets its test suite FIRST: the p100
  renumbering fixture (model letters discarded, position wins), marker-scope conventions (per-page
  vs per-paragraph restart, j/u-v skips), sequence-continuation pages as fixtures.

**Pattern worth naming (2nd occurrence):** a dreaded work item evaporated under measurement — the
census keeps converting "build a mechanism for X" into "X doesn't exist here; add an assertion"
(1st was the matres loosening dissolving once the population was split correctly). The hard-sounding
cross-page problem was never joining; it's *scoping*, which the assembler owns anyway under the
markers-by-position law. Measure the population before building the mechanism.
- **When finalizing LAYOUT RULES (Chris):** scan the existing pipeline (`get_md.py`, `fixup_ocr.py`,
  `read_images_baml.py`, `normalize_markdown.py`, census scripts) for corner-case tricks the
  10-page sample won't surface (chapter-spanning headers, j/u-v skips, hyphenation, page furniture)
  — inherit those lessons into `book_profile.yaml`, don't rediscover them.

Build lives in `pipeline/reextract/` (`book_profile.gill.yaml` day-one + `extract_apparatus.py`).

## FOSSIL MINING done 2026-08-09 (Chris: highest-leverage move, do it FIRST) → `reextract/FOSSIL_SCARS.md`
The old pipeline is a fossil record of every corner case the corpus threw. Mined
`get_md/fixup_ocr/normalize_markdown.py` + `main.baml` BEFORE building the anchor-matcher (where
the scars are densest — doing it after = the work twice). Harvested paid-for experience into:
- **Folded NOW (fixtures + profile):** dash-variant word-break join (soft/non-breaking/figure dash,
  not just `-`); non-Latin-final covers Greek+Syriac (not just Hebrew); header region top-3%;
  chapter-heading-only-at-start; roman chapters exceed X (Gen 50 = L). assembler suite now **10
  passing**.
- **Anchor-matcher REQUIREMENTS (build to these next):** (A) body anchor glyphs are a ZOO
  (`^a^ ᵃ * † ‡ ° δ <sup> ¹..⁹`), not `[a-z]` — in `profile.layout.body_anchor_glyphs`; (B)
  **ibid-merge**: `ib/ibid/idem/id` refs legitimately merge → count assertion tolerates
  `body == def + ibid_count`, not every mismatch is damage; (C) the count assertion itself (old
  `verify_normalization` had it — re-home to code); (D) tolerate OCR word-fusion, fuzzy ≥60;
  (E) resolve anchors WITHIN letter-scope windows (search_range ~30–50), not whole-page scan.
- **Explicitly REJECTED (with reason):** the 500px Y-gap (CV presplit replaces it); one-verse Hebrew
  injection (wide window); running a text-normalizer over Hebrew (its `repair_non_latin_footnotes`
  existed only to undo its OWN corruption — proof the stage shouldn't exist).

## NEXT-SESSION PLAN (Chris-ordered): fossils✔ → anchors → stratified truth set
1. **Fossils mined ✔** (above).
2. **Body-anchor matching** — link notes to body superscripts. Fixtures ALREADY EXIST: **p571's 3
   anchor collisions** (stored layer mis-anchored the right column) are the known-failure fixtures,
   go in the born-tested suite like p100's renumbering did. Anchors resolve WITHIN letter-scope
   windows (turns "find this superscript on the page" into "find it between anchors l and n"). If a
   superscript genuinely can't be found in its window → **flagged UNANCHORED, fail-loud, NOT a
   guessed placement** (a mis-anchored citation is worse than an honestly-orphaned one — Aquinas-class
   IDs ride on anchors being RIGHT, not merely present).
3. **Per-region Hebrew hi-res crop — DONE ✔ (`c8da667`+ next commit), CONFIG NOW FROZEN.** Built
   `hebrew_recrop.py`; validated end-to-end on p473: `סגר עליה` (6/7) → `סגר עליהם` (7/7). **Config-
   shaping measurement (recorded so it isn't re-litigated):** full-strip upscale does NOT close the
   Hebrew (6× AND 8× full-strip both stuck at 6/7 — the VL encoder downscales the big strip, so
   pixels-per-glyph doesn't rise); a CONCENTRATED band crop of the note's line does. Two gotchas
   found by measuring: (a) crop from a **MODERATE base (2×)** and upscale the band ONCE — cropping
   the 4× display strip compounds to 12× and DEGRADES the glyph (first attempt gave a *different*
   6/7, `עליו`); (b) **pad_frac ≥ 0.03** required — too-tight bands cut context and mis-read. With
   2× base + pad 0.04 + ×3 it reads 7/7 across 4 band configs. Mechanism: Tesseract locates the
   Hebrew note's line via its Latin anchor ("clausit viam illis"), crop+upscale that band,
   re-transcribe, splice. The truth set now grades THIS frozen config.
4. **Stratified acceptance truth set = review-bandwidth spend (ADR-0015), NOT exhaustive.** Strata:
   the 3 ground-truth pages + 6 whitelist-artifact pages + p571-class collision pages + 2 split-IN
   pages + a Hebrew-dense sample + a random balance — sized to what Chris adjudicates at ṭaʿun-grade.
   The REST of vol1 is validated by the ASSERTIONS (marker-scope, count reconciliation w/ ibid,
   stitch guard, anchor-match status), not by eyes. Assertions make full-corpus confidence
   affordable; the truth set calibrates the assertions. A 200-page truth set nobody reviews is the
   exact ADR-0015 failure mode.

## TRUTH-SET RAN 2026-08-09 — reframed acceptance + a GATE-RELEVANT scope finding
27-page stratified run against the frozen config (`build_truthset.py` → `render_adjudication.py`;
Artifact console published). It first did its calibration job — caught **2 matcher bugs** (caret-def
body-split doubling; `scope_start='a'` phantom gaps) → fixed, 18 tests (`9c19bf5`). Then the honest
result separated into **two axes** the raw "70% flagged" headline had conflated:
- **AXIS 1 — new apparatus quality: MIXED (Chris adjudicated — supersedes my rosy automated framing).**
  Verdicts (`truthset_out/verdicts.json`): **14 correct / 7 minor / 6 wrong** — 13/27 have real issues.
  My "22/27 complete / beats stored" was a WEAK PROXY (count-matches-*stored*, but stored was
  sometimes right where new is wrong: 336/343 counts; and my p702 showcase was WRONG — Chris found
  its `Gerson` wrong + `Negáim` accent spurious). Real defect patterns:
  1. **Hebrew = dominant defect, and the recrop FIRES BUT DOESN'T RELIABLY FIX IT** — 150/269/336/347/
     692/843 all recropped and Hebrew still wrong; 692 (`וְכִי γ`) the recrop may INTRODUCE error
     (spurious points / stray Greek). p473 `סגר עליהם` was NOT representative — resolution closes some
     spans, not the class. (Revises `[[pixels-not-parameters]]`: held for one span, not broadly.)
  2. **Note SEGMENTATION wrong on 5 pages, stored sometimes right:** under-seg 336(2/3) 343(1/2)
     740(3/4) 757(1/3); over-seg 602(2/1).
  3. **Symbol/Greek markers unhandled → missed notes + marker leakage:** 740 `γ De Abstinent` note
     missed + `*` leaked; 343/757 markers left inside note text. Zoo handled letters/caret, not
     `* γ` as note BOUNDARIES.
  Plus Latin slips (546 `Pagnin nus`), dropped Arabic (264). Structure IS better (dedup, canonical
  markers) but accuracy is NOT yet a clear win over stored.
  **⇒ Reorders the build: note-quality fixes (Hebrew reliability, segmentation, symbol-markers) come
  BEFORE the in-text-anchor scope question — no point linking notes that are themselves wrong.**

### FAILURE MAP by pipeline stage (image-verified 2026-08-09) + Chris's fix plan
Five defect classes, FOUR stages, no single villain — decomposition making every error attributable:
- **Stage 1 CV presplit** (no models): `p546 Pagnin nus` = a FULL-WIDTH note (spans both columns, as
  the 1766 printer occasionally sets) sliced through `Pagni|nus` by the column cut → broken image
  downstream. **Fix = detect-and-REROUTE, not predict:** the split-IN/split-OUT signal pair (already
  in the stitch guard) fires at the INTRA-page column seam (left col ends mid-word no-terminal, right
  col opens lowercase mid-word) → re-process the page with the footnote strip UNCUT (full-width mode).
  Profile: `full_width_notes: reroute_uncut`; whitelist discipline as with the 6 stitch artifacts.
- **Stage 2 Tesseract** (demoted to hint + Latin-anchor LOCATOR): the Latin-anchor trick sometimes
  misses Hebrew → recrop never fires, and if the base pass also dropped it, the span is INVISIBLE to
  every text-side instrument (the plausible-omission class). **Fix = deterministic SCRIPT-CENSUS:**
  CV/Tesseract script-detection counts Hebrew-shaped RTL regions per footnote strip; the extraction's
  Hebrew-span count must RECONCILE against it → mismatch = fail-loud (same shape as the marker-count
  assertion). Locator stays for positioning; it stops being the only witness Hebrew exists.
- **Stage 3 main VLM pass (qwen3.6, FULL strip = full context):** `p702 Gersom→Gerson` — context was
  ON the page and the model still let its PRIOR win (Jean Gerson ≫ Gersonides' Gersom in training) on
  the ambiguous final letter; `p150 הניחח→הניח` (dropped final chet); segmentation misses (336 short
  Hebrew-only note; 740 `γ`-marked note) + `* γ` markers not known as note BOUNDARIES. **Fixes:**
  (a) **authority-list** deterministic check vs Gill's citation universe (Gersom, Pagninus, Vatablus,
  Jarchi, Kimchi…) — settles the prior-substitution class WITHOUT a model; (b) **two-model FLAGGING**
  (qwen3.6 + gemma4, free): disagreement → review/authority-list, NOT voting (shared priors → shared
  hallucinations; agreement lowers priority, never closes); (c) **note-scoped body-context** = the
  reference-window trick aimed at the apparatus (feed the anchor's surrounding SENTENCES — names the
  cited author/verse/topic — scoped to the note, not the whole page); (d) symbol markers `* † ‡ γ` in
  the zoo as note boundaries.
- **Stage 4 Hebrew recrop — PULLED (net-negative).** Context amputation: naked hi-res band → prior
  fills the vacuum with nikud (`וכי→וְכִי`) / hallucination (`הקדשה→הַמְּקוֹמוֹת שֶׁלָּהּ`, p336).
  DOWNGRADED 336/692/150 to win only 473. **Redesign (stage-4 v2):** FULL note-strip image + scaled
  section TOGETHER (context restored, pixels kept) — image-context beats text-context (text-anchor
  launders base's errors through a "confirming" pass; independent verification was the goal). GATED:
  a recrop result may ONLY replace base when it REDUCES toward the printed consonantal form (drops a
  spurious char / recovers a final letter), NEVER adds marks. Regression fixtures: 336/692/150 stop
  corrupting, 473 keeps its win.
- **Stage 5 assembler/anchor-matcher** (pure code): not implicated in quality findings.

### ACCEPTANCE HARNESS (Chris adjudicated ONCE; now self-tested) — `ground_truth_vol1.json` + `score_truth.py`
Image-verified answers are fixtures; the pipeline is scored automatically, no re-adjudication. Base-only
floor = **1/6** on strict fixtures (473 needs the stage-4 redesign; 692 passes base-only; 702/546/336/150
are the stage-3/1 fixes). Re-score after each fix; pass-count is the acceptance signal. Grows as pages verify.

### BOUNDING BOXES = the ALIGNMENT problem, not Tesseract geometry (Chris, 2026-08-09)
Nonsensical boxes (cross the gutter into the other column, bleed into footnotes/title, few-chars-wide)
are NOT Tesseract failing at geometry — they're the **cross-modal ALIGNMENT** layer failing at
CORRESPONDENCE then deriving geometry from wrong matches. Old pipeline: match Tesseract's text ↔ the
VLM's (or normalized-VLM's) text to give each VLM word a box — two DIFFERENT transcriptions of a 2D
page, serialized to 1D strings (Tesseract reading-order vs VLM merged-column narrative), matched
page-globally with **no shared coordinate system and no spatial invariants** → matches jump columns,
into footnotes, even across pages; box faithfully reports the location of the WRONG text. (This is
what `fixup_ocr`'s 500px Y-gap actually was — the same alignment problem in a different hat.)
- **The NEW pipeline barely has this problem — alignment was a symptom of the old architecture's
  shape.** It REGIONALIZES before either model reads (per-strip Tesseract + per-strip VLM), so any
  alignment happens WITHIN a region (one column of one page's footnote block) — cross-column/-page
  spillover is structurally impossible (the other column isn't in the input). Alignment shrinks to a
  scale where simple methods work: within a strip both texts are short, share reading order by
  construction, **anchor-first** (distinctive tokens: citations, names, the Latin the locator uses),
  **monotonic** (matches proceed in order, no long jumps), with the **box-sanity geometry gate as the
  output check** (a derived box violating region bounds ⇒ the match was wrong ⇒ reject).
- **Alignment CONFIDENCE is a first-class output** (the rule the old matcher lacked): where no
  anchor-quality match exists (Hebrew, where Tesseract's text is garbage), the honest answer is **"no
  box for this span" — fail-loud, never a forced best-match.** The Hebrew locator already does this in
  spirit (locates via adjacent Latin); make it the general policy: locate what's matchable, flag what
  isn't, never force.
- **box_sanity.py gate** between Tesseract and every consumer: each box vs region geometry (falls in
  exactly ONE region: body-L, body-R, footnote-strip, title; no straddling gutter/rule past tolerance)
  + line-width/height distributional bounds; disposition **clip / reject / flag** (many bad boxes ⇒
  page geometry suspect ⇒ reroute/review). Never consumed raw. **Upstream of stages 2/3/4** (bad boxes
  scramble the base-pass hint and mis-place the locator's recrop band — a candidate mechanism for the
  stage-2 "Hebrew in image not in text"). Slots into the stage-1/2 deterministic batch. Instrumented
  run gets a per-page box-violation column; high-violation pages are where the old silent smearing
  concentrated → oversample them in the random stratum.
- **THREE fallouts:** (a) NEW build — small constrained alignment layer + confidence (above);
  (b) EXISTING corpus — stored boxes may carry wrong-correspondence geometry (internally plausible,
  wrong text) → **un-repairable by geometry validation alone**; spot-check IF anything user-facing draws
  them; the alignment JSONs used start/end PHRASES (text-anchored) so likely DODGED this → damage
  contained to the dead pipeline, just note it; (c) RE-EXTRACTION outputs — **DECISION (Chris):** does
  the new corpus carry boxes? Needed only for the locator (per-strip, ephemeral) and, someday,
  quote-on-scan highlighting (an S-plan upgrade). If highlighting is on the roadmap, record it in the
  profile NOW and let the transcription pass emit per-strip word boxes AT EXTRACTION TIME (the reliable
  direction — from the pass that read the text, with the confidence flag) — never reconstruct by
  post-hoc alignment. Recommendation: defer boxes-as-corpus-output until highlighting is committed;
  the per-strip ephemeral locator boxes suffice now.
- **LAW (record):** *cross-modal correspondence is a STOCHASTIC product — it gets confidence scores,
  spatial invariants, and fail-loud gaps, and never runs unconstrained across region boundaries.* The
  old matcher broke all four clauses at once; the new architecture makes three of them nearly free.

### BUILD ORDER (Chris-settled, REORDERED to deterministic-first 2026-08-09):
1. **base-only re-run** (recrop pulled — DONE, scored per-class: seg 5/6, hebrew 6/8, transcription 0/4).
2. **DETERMINISTIC BATCH (pure geometry, no models, deterministic acceptance — goes FIRST so every
   stochastic experiment downstream inherits a clean substrate & the failure map stays honest):**
   - **stage-1 — SOUND FIX LANDED (footnote gutter, not body gutter). 1/6 → 3/6 fixtures; seg 6/6,
     transcription 4/4 (both perfect).** The unsoundness was using `find_vertical_divider`'s BODY
     gutter for the footnote split. Fix: `find_footnote_gutter` measures the footnote region's OWN
     gutter depth — clean separator (p546 full-width = −1.38; every two-column page = 0.57..0.94);
     `depth<0.30` ⇒ full-width UNCUT (fixes p546 `Pagninus`), else two-column split AT the footnote
     gutter xg (fixes p336 missed-note AND p702 `Gersom` — the cleaner crop beat the prior). The
     earlier geometric regression on p692 is GONE. Residual: p692 `כהות→כהת` (dropped vav, one glyph,
     still 4 notes) — a Hebrew reading-edge miss, now in the stage-4 bucket, not a structural break.
     Full 27-page re-run in flight to confirm no broad regression from the split-x change.
   - **stage-2 SCRIPT-CENSUS — built (`script_census.py`), instrument NOISY, needs DUAL-OCR.** Per the
     fossil (get_md.py ran Tesseract `heb+grc+ara`) + Chris's pointer (he ran BOTH eng-only AND multi
     for exactly this reason). Findings, each validated against image-known pages (validate the
     instrument before trusting it): heb-only ≥2-char is 7/8 on KNOWN pages, but **false-positives on
     UNKNOWN Latin-heavy pages** — p674 flagged +2 but its strip is ALL Latin (the "Hebrew" is
     transliterated names `Maacolot Asurot`/`Pirush` in LATIN letters); the VLM correctly had 0.
     Adding grc+ara made it WORSE (p100/p702 false-pos). **⇒ the census can't answer the denominator
     question yet.** The FIX (Chris's fossil technique) = **DUAL-OCR disambiguation**: a line is real
     non-Latin only if multi-lang finds it AND eng-only does NOT read it as high-confidence Latin
     (a real Hebrew line yields eng-only GARBAGE/low-conf; a Latin line misread as Hebrew yields
     eng-only HIGH-conf Latin → reject). Instrument also false-NEGATIVES (p550 שורש) → lower bound.
     **UPDATE — dual-OCR ALSO FAILS (DEAD-END for Tesseract here).** Apparatus lines are MIXED
     Hebrew+Latin (Hebrew word + Latin gloss on ONE line), so eng-only reads the Latin confidently and
     rejects the whole line even with real Hebrew (p473 `סגר עליה clausit viam illis` → rejected),
     while worn Latin (p674) reads low-conf and is kept. Best dual-OCR 3/8 < heb-only 7/8. ⇒ Tesseract
     (single OR dual) cannot cleanly census non-Latin on this corpus; the invisible-loss DENOMINATOR
     stays OPEN. A different instrument is needed: (a) CV glyph-shape detection (Hebrew is blocky, no
     asc/desc), or (b) a TARGETED VLM presence-check ("how many footnotes contain Hebrew?"). Not built.
     `script_census.py` kept as a WEAK heb-only flag (7/8 on knowns), not a count.
   - **box_sanity gate.**
   Rationale: p546 is a stage-1 failure MASKING that page's stage-3/4 behavior — fix the cut, the page
   goes green or reveals its next defect, attribution stays clean.
3. **stage-4 combined-context gated recrop — DONE (3/6 → 4/6).** Recrop re-enabled but GATED. v2 =
   (a) COMBINED CONTEXT: model gets the full note-strip + the magnified region together (context
   restored, pixels kept) with a consonants-only prompt; (b) GATE (`_gate_accept`): a recrop result
   replaces base ONLY if it adds NO nikud, introduces NO stray non-Hebrew (γ), and is a SMALL edit
   (|Δlen|≤2 — a final-letter recovery / spurious-char drop, NOT truncation or replacement). On the
   4 fixtures the gate is exactly right: p692 `כהת→כהות` ACCEPTED (fixed); p546 `→כִּי יְהִיהָ`
   gated-OUT (nikud); p150 `→הארץ` gated-OUT (truncation); p336 `→מקמה` gated-OUT (replacement). The
   recrop-corruption class is structurally prevented; safe corpus-wide. RESIDUAL: 473 (`עליה`, needs
   final `ם`) + 150 note-e (`הניח`, needs final `ח`) — single FINAL-LETTER reading-edge misses that
   context+resolution do NOT recover = the genuine pixels-not-parameters floor (candidates for the
   authority-list / review, not more pixels).
4. **stage-3 — BATCH DONE (2026-08-09 overnight).** All named pieces built + validated:
   - **symbol-marker split** (`assembler.split_note_line`): superscript/symbol markers (`² ᵃ ᵇ ¹ * † ‡`)
     mid-line merged notes; now split. p343→2, p757→2 (NOT crop-fixed — real work; re-scored per Chris,
     not closed on p740's evidence). 19 assembler tests. `0bde7a7`.
   - **escalation tier COMPONENT** (`escalation_tier.py`): intake gate (self-glossing) in code, faithfulness
     clause, provenance class, dual cost-logging, unanimity→auto-acceptable. `c3bfda7`.
   - **authority-list** (`authority_list.py` + profile seed): citation-misread safety net; Gerson~Gersom
     (0.83), Pagnin~Pagninus (0.86); exact clean. Proposals not auto-corrections. `a8323e5`.
   - **review-queue** (`review_queue.py`): aggregates unanchored / gated-recrop / stitch / citation flags
     as pending items w/ provenance; gates the escalation tier to self-glossing Hebrew. `a8323e5`.
   - **two-model flagging** (`two_model_flag.py`): qwen3.6 vs gemma4, disagreement = DATA (never a vote;
     agreement lowers priority, never closes). Validated: p473 flagged עליו-vs-עליהם (gemma4=truth) → the
     span the tier adjudicates; p550 flagged 2-vs-9 + Physi-vs-Physic. `37769c0`.
   **note-scoped body-context** (reference-window aimed at the apparatus) = the one un-built stage-3 idea;
   the note's OWN Latin gloss already supplies the escalation tier's evidence, so external body-context is
   a lower-priority enhancement. **File the 2 final-letter residuals (473 `עליהם`, 150 `הניחח`) as
   REVIEW-FLAGS + reference-window EXHIBITS:** they fail context+resolution together = the empirical
   case that the reference-window's next shelf (the note's own Latin gloss / Talmud-window, IDEAS.md)
   is the only remaining lever for a measured class — 2 named exhibits for Psalms-era planning.

### FRONTIER ESCALATION TIER — PROBED 2026-08-09 (Chris's idea, reframed): escalate ADJUDICATION not
transcription. The frontier-inversion says bubbling the CROP up buys nothing (235b/72b read it worse
than local 35b). So the tier sends an EVIDENCE PACKAGE (base reading + candidates + the note's own
**Latin gloss**, which self-adjudicates: `clausit viam illis` → *illis* plural → `עליהם` over `עליה`)
and asks a bilingual-philology VERIFICATION question. **Probe on the 2 known-answer spans (~$0.005):**
- p473: **deepseek RECOVERED `סגר עליהם`** (from illis=plural); gpt-4o-mini got plural but wrong gender
  (`עליהן`). The Latin fixes NUMBER, not GENDER (`ם`/`ן`) → models DISAGREE → that disagreement IS the
  flag. Tier NARROWS "unknown final letter" → "plural, `ם` or `ן`, + reasoning" = a rich review item.
- p150: both **OVER-CORRECTED to the dictionary form** (`ניחוח`/`הניחו`) not the PRINTED `הניחח` — the
  gloss `odorem quietis` fixes the LEMMA, not the SPELLING. **Philology-vs-faithfulness:** divergence
  from the printed form is a DEFECT not a fix → confirms the tier must be **propose-into-review, NEVER
  auto-accept**, and p150 is genuinely at the pixels floor.
**RE-PROBED with NEWEST models + faithfulness prompt (Chris: use opus-5/gpt-5.6/gemini-3.6, not cheap
old ones) → 8/8, BOTH floor cases RECOVERED UNANIMOUSLY.** Two changes flipped it: (1) strong models
(`claude-opus-5`, `openai/gpt-5.6-luna-pro`, `google/gemini-3.6-flash`, `deepseek-v4-pro`) — the old
cheap ones fumbled gender/spelling; (2) the prompt constraint "**APPEND the dropped final letter,
reproduce the PRINTED form, do NOT normalize to the dictionary**" — which fixed the p150
over-correction. Result: p473 → `סגר עליהם` (all 4, `ם` from illis=plural); p150 → `ריח הניחח` (all 4,
`ח` from odorem quietis). **The pixels-not-parameters "floor" has a shelf above it: PHILOLOGY** — the
note's own Latin gloss is the reference text that adjudicates the final letter. With the tier disposing
the 2 residuals, fixtures are effectively **6/6**.
**PRECONDITION (the actual thing validated — do NOT let 8/8 calcify into "frontier fixes Hebrew"):**
the tier works because the note **GLOSSES ITSELF** — `illis` grammatically forced `ם`, `odorem quietis`
semantically forced `הניחח`. The models out-REASONED the local 35b over evidence *sitting in the note*;
they did NOT out-SEE it (the frontier-inversion STILL STANDS). So the tier's precondition is NOT
"expensive model" — it is **"the note contains adjudicating material" (Latin gloss / citation /
parallel)**. Mechanized INTAKE GATE: *does this span's note contain adjudicating material?* YES →
escalate WITH it; NO → honest review-queue, NO panel (philology without a text to reason from is just
prior-voting at higher price). **Unanimity is a confidence signal ONLY when the models reason over
shared EVIDENCE, not shared PRIORS** — four models agreeing on a dictionary-form normalization would
look exactly like 8/8 and be exactly WRONG (that was p150 before the constraint). ⇒ **PERMANENT CLAUSE
(not a session fix):** the faithfulness instruction "reproduce the PRINTED form, do NOT normalize to the
dictionary" is a fixed part of the tier prompt.
**Verdict:** a near-ORACLE for the grammatically/philologically-adjudicable final-letter class (given
the intake gate + faithfulness clause + strong models + evidence-grounded unanimity), NOT for
orthographic detail the Latin can't reach, and NOT for spans with no internal evidence at all. Economics trivial (cents corpus-wide; free batched async off the Max plan). **COST UNIT (measured
2026-08-09):** OpenRouter-billed models — opus-5 $0.0045/span, deepseek-v4-pro $0.0025/span.
**gpt-5.6-luna-pro + gemini-3.6-flash showed $0.00 in OpenRouter usage because Chris has BYOK for
OpenAI/Google — they bill UPSTREAM to his own accounts, NOT free** (their true cost is in the provider
billing, priceable from the token counts OpenRouter still returns). Session OpenRouter-key total =
$0.108 of $10 (opus/deepseek/earlier-Chinese only; BYOK spend is separate & small). **Whole-vol1
escalation ≈ $0.35 (tens of spans) to ~$2 (low-hundreds) if routed through opus-5/deepseek**; near-$0
if routed through the BYOK models or batched on Max. FINAL TOTAL = unit × the actual re-eval population
from the instrumented run (residue-of-residues: base→gated-recrop→authority-list→two-model-flag).
**BUILD TODO: log per verdict both `usage.cost` AND token counts** — cost covers OpenRouter-billed
models; tokens×published-rate prices the BYOK models whose OpenRouter cost reads $0. So the total is
exact across both billing paths, not a guess.
Governance (ADR-0015): provenance class `adjudicated-by-frontier-with-bilingual-context` ≠
`Chris-verified-against-scan`; model-disagreement + print-divergence are its fail-loud flags. Slots
into stage-3 as the disposition path for what the authority-list + two-model flag can't settle.

### CENSUS SCOPE-HONESTY (rides into the acceptance claim): the invisible-Hebrew-loss denominator is a
KNOWN-UNKNOWN — this class trips no text-side tripwire by definition. Full-vol1 acceptance language MUST
carry it explicitly: **"Hebrew-span completeness UNVERIFIED pending a non-Tesseract witness."** The
random-unflagged eyeball sample OVERSAMPLES Hebrew-dense pages (where the invisible class hides). CV
glyph-shape witness (Hebrew letterform stats, no Tesseract) stays ON THE LIST — don't let "dead-end"
become "dropped".

### ADR THROUGH-LINE (the session's actual product, one sentence): the adjudication-derived harness
caught THREE wrong conclusions before they shipped (geometric full-width regression, census over-count,
recrop corruption) — one hour of Chris's eyes, converted into permanent instrumentation, out-prevented
the old pipeline's two volumes of serial discovery. ADR-0015's thesis (expert review is the scarce
resource) proven from the other side: spend it once, instrument it, it multiplies.
- **AXIS 2 — linkage: 8/27 linkable, 19 "flagged" = OLD-BODY in-text anchor loss.** Confirmed NOT a
  detection bug and NOT a re-extraction failure: the old body genuinely dropped 70%+ of its in-text
  superscript markers (p550 has 1 inline anchor for 7 notes; p702 has 2 for 8), while keeping the
  definitions. The correct new notes have nowhere to attach.

**GATE-RELEVANT SCOPE FINDING (needs Chris):** re-extracting the footnote DEFINITIONS is **not
enough for a LINKED apparatus** — the body's IN-TEXT ANCHOR MARKERS are a heavily-degraded body-layer
defect (the census's "127 lost anchors", now seen to be pervasive). Two options:
  (a) **Expand scope: in-text anchor RE-DETECTION** — re-detect the small superscript positions from
      the IMAGE and re-insert them (body PROSE still untouched; only the anchor glyphs re-extracted).
  (b) **Ship notes present-but-unanchored** now (already better than stored: correct, deduped,
      Hebrew-recovered) and queue (a) as a follow-on.
This also **refines Q1 body-tiering**: "body PROSE suspected-fine" still holds, but "body IN-TEXT
ANCHORS" are now KNOWN-degraded — a caveat to record before V2 leans on them.
Adjudication console (Axis-1 note quality is what Chris grades from the side-by-side; Axis-2 is
labeled a body-layer property, not a re-extraction verdict): the published Artifact.

**BUILD-DOCS LAW — probe/production split:** raw `httpx`→Ollama/OpenRouter for PROBES (fast
experimentation, no codegen); **BAML for anything the pipeline DEPENDS on** (typed output,
unrepresentable bad states, validate-and-retry). Keep the raw-probe scripts as-is — they're the
fast path. The next probe shouldn't get over-engineered into BAML; the next production seam
shouldn't stay raw. Three-layer division of every component: **BAML wraps the model-calling seam ·
the assembler stays pure code · deterministic filters (citation, furniture) stay code** — which is
what keeps the standing law enforceable at the TYPE layer, not the prompt layer.

**RE-EXTRACTION ADR exhibit pair (the BUILD's, alongside the PROBE's frontier-inversion + p100
renumbering):** **p571-dissolved / p473-flagged** — the same fail-loud-or-fail-closed-never-
fail-*different* architecture on real pages in one commit (`c8da667`). p571's 3 anchor collisions
(a probe damning-exhibit) **ceased to exist** once anchors resolved by position within letter-scope
(dissolved by structure, like the bookend closer becoming unrepresentable and the stitch pass
evaporating); p473's 5 lost anchors (census-unrecoverable, dropped in-text markers) were **flagged
unanchored, not guessed**. Collisions dissolved + losses flagged = the whole law in one pair.

Loose ends unchanged: corpus sync + fingerprint FIRST (Dagster now definitely coming, since
re-extraction runs through it), PuritanBoard after.

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
regardless of the existing-corpus decision. **Reference-window ledger (see
`reextract/FOSSIL_SCARS.md` + `IDEAS.md`):** the one-verse injection is the reference trick (give
the transcriber ground truth for predictable text) aimed one aperture too narrow. Widened: it
**self-fills from Gill's OWN citations** (parse the page's scripture refs — the `cross_references`
the entity pass already extracts — → fetch those verses' Hebrew → inject), covering case-1 + cross-ref
(~55%). It becomes the **DOMINANT correction mechanism in Psalms** (verse-by-verse Hebrew — the tier
that's a rounding error in vol1/zero in vol7). Extra-biblical tier: hi-res crops now, Talmud
tractate/folio window someday (IDEAS, per the bridge law).

## Parallel / loose ends
- **Parallel, no dependency:** ADR-0009 **B1 schema commit** (migration long pole) — landable cold.
- **Chris's, in order:** (1) corpus **sync + fingerprint** FIRST (Dagster approaching; every
  slipped week adds sync ambiguity); (2) PuritanBoard post (no decay; ṭaʿun / three-corruptions
  exhibit strengthens as the comparison page firms up).

## vol3
Never normalized (raw OCR attempt only); deleted-for-now from disk (recoverable via git);
on the Psalms-era ingestion queue. The detector prints a fail-loud ABSENT line for it.
