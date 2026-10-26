# Ratified truth-set form (v1)

- **Status:** published 2026-10-25. Describes the format in use; v1 is what the vol.1 Hebrew-span
  sets already emit.
- **Audience:** the two consumers named in the publication plan — the **verse-region rebuild**
  (page-geometry substrate) and the **vol.3 body path**. Written for whoever has to emit or read a
  truth set without having built one.
- **Scope:** the record format, its invariants, and the checks a consumer may run against it. Not a
  tutorial on drawing a population, and not a description of any particular set's contents.

**This repo is public and code-only.** No truth set, no signed verdict, no crop and no page number
of a real span appears in this document. Every example below is synthetic. Real sets live in the
private data repo; the pre-commit hook enforces the split.

**Page numbering.** All page fields are **FILE pages**. `printed = file − printed_offset`, and the
offset is recorded **in the record** (`page_numbering`, `printed_offset`), never inferred by a
consumer and never hard-coded in a reader. For vol.1 it is 88. A consumer that needs printed pages
reads the offset from the record it was handed.

---

## 1. What a truth set is

A drawn population of spans, each **signed by a human from pixels**, carrying the geometry that
produced the crop and the provenance of the signature.

It is **three records**, one per stage, and none of them overwrites another:

| stage | record | names | answers |
|---|---|---|---|
| 1. draw | `truth_set<N>_<set_sha16>.json` | the population | which spans, and why those |
| 2. offer | `truth_set<N>_<set_sha16>_signer.json` | the pixels | what the human was shown |
| 3. sign | `signing_pass<K>_ingest_<set_sha16>.json` | the verdicts | what the human said, and how |

The chain is bound by digests: stage 2 and 3 both carry `set_sha16`, the digest of stage 1, and
stage 2 carries a `crop_sha16` per row — the digest of the actual image bytes offered. A verdict
whose `crop_sha16` is not reproducible from the stored crop is a verdict about an unknown picture.

## 2. Stage 1 — the draw

### Top level

| field | type | meaning |
|---|---|---|
| `generated` | ISO-8601 str | when |
| `n` | int | rows in this record |
| `page_numbering` | str | the human-readable convention, e.g. `FILE pages (printed = file - 88)` |
| `provisional` | bool | **true** unless the run was clean start and end (§7) |
| `git_start`, `git_end` | obj | `{git_head, git_dirty, clean}` — see §7 |
| `limits` | obj | what this population cannot answer, in prose, written before it is used |
| `predictions` | obj | the registered prediction and its standard, **written before the rows are looked at** |
| `drop_accounting` | obj | `{root_n, dropped_from_<root>, dropped_here, n}` and it must balance |

`drop_accounting` is not decoration. A population reported as *n* without saying what left it, and
when, cannot be distinguished from a population selected after the fact.

### Rows

| field | type | meaning |
|---|---|---|
| `span_id` | str | `p<file_page>:n<note_index − 1>`, the join key for every downstream record. **The suffix is 0-based and `note_index` is 1-based — see the hazard note below.** |
| `page` | int | FILE page |
| `note_index` | int | **1-based** ordinal of the note on the page: `1 ≤ note_index ≤ notes_on_page` |
| `notes_on_page` | int | how many notes the page has — the count gate's denominator |
| `box` | `[x, y, w, h]` | the span rect **in band-local pixels** |
| `band` | int or null | index of the note band the span sits in; `null` when no band was found |
| `band_w` | int or null | that band's width in px |
| `over` | int or null | `box[2] − band_w`. **Positive means the box is wider than the band it sits in.** |
| `cut` | str | `""` fine, `"band-overshoot"` when `over > 0`, `"no-band"` when no band was found |
| `hebrew` | str | the extracted span text as drawn — a **candidate**, not truth |
| `letters`, `chars`, `words` | int | counts over that candidate |
| `nikud` | bool | whether the candidate carries points |
| `status` | str | `ok`, or why the row is not |
| `page_status` | str | the page's own state, e.g. an anchor flag — carried, not resolved here |
| `stitch_page` | bool | the page is a stitch of more than one image |
| `verdict` | str | what the draw concluded about the row (e.g. `BOX`) |

**Hazard — the two index bases do not agree.** `note_index` is 1-based; the `span_id` suffix is
0-based, so `p92:n1` is the row whose `note_index` is **2**. Measured over vol.1's 74-span set:
`span_id == "p%d:n%d" % (page, note_index - 1)` on 74 of 74 rows, and
`1 ≤ note_index ≤ notes_on_page` on 74 of 74. A consumer that parses the span id to get an ordinal,
or compares a parsed suffix against `note_index`, is off by one on every row. Join on the **string**
`span_id` and read the ordinal from `note_index`.

`hebrew` in stage 1 is **not** the truth. It is the extractor's candidate, kept so the signed
verdict can be diffed against it. Treating it as truth is the single most likely misreading of this
format.

## 3. Stage 2 — the signer sheet

| field | type | meaning |
|---|---|---|
| `set_sha16` | str | digest of the stage-1 record this sheet offers |
| `instruction` | str | the signing instruction **as given to the human**, verbatim |
| `withheld` | list | spans deliberately not offered, with the reason |
| `n`, `generated`, `page_numbering`, `provisional` | — | as stage 1 |
| rows: `span_id`, `page`, `note_index`, `notes_on_page`, `band`, `band_w` | — | as stage 1 |
| rows: `box_strip` | `[x, y, w, h]` | the rect of the strip actually rendered |
| rows: `crop_sha16` | str | digest of the image bytes offered for that row |

Rules this stage carries:

1. **The signer does not type.** The offer is **one tile per consonant and one per word gap**, each
   needing its own verdict. A signer who types a string signs a reading, and a property of their
   expectation rides along with it.
2. **`withheld` is content, not absence.** A span held back for a stated reason is recorded here; a
   span simply missing from the sheet is a defect.
3. **A trailing word separator with nothing beyond it is a boundary artifact, not a letter** — strip
   it and record the trim.
4. **The realized rect, not the requested one.** `box_strip` is what was rendered after clamping,
   with the clamp bounds recorded. A consumer that needs the pad applied must not be handed the pad
   requested.

## 4. Stage 3 — the signed ingest

| field | type | meaning |
|---|---|---|
| `pass`, `pass_sha16` | str | which signing pass, and its digest |
| `set_sha16` | str | the draw it is about |
| `rule` | str | the decision rule applied, stated |
| `printed_offset` | int | the page offset, carried so no reader guesses it |
| `dispositions`, `disposition_counts` | obj | the typed outcomes and their tally |
| rows: `candidate` | str | what stage 1 offered |
| rows: `tiles` | list | the per-tile verdicts, in **reading order** |
| rows: `verdict_counts` | obj | confirmed / corrected / sic, per row |
| rows: `corrections` | list | which tiles the human changed, and to what |
| rows: `complete` | bool | every tile has a verdict |
| rows: `abstain`, `fault`, `disputed` | bool | typed non-verdicts (§5) |
| rows: `disposition` | str | the row's outcome |
| rows: `note_classes`, `paired_at`, `note` | — | the note context the verdict was read in |

Rules this stage carries:

1. **Reading order is explicit.** Tiles are numbered in reading order and Hebrew is rendered
   right-to-left in anything a human signs on. A signature assembled from tiles read
   left-to-right produces a **reversed** string that is a plausible word, and no output-side check
   catches it. Producers must refuse to save a signature equal to the reverse of the candidate.
2. **`verdict_counts` decides what the signature IS.** A row that is mostly `corrected` is a
   **signed reading**, not a pixel signature, and `signed_from` must say so. Consumers that need
   pixel-grounded truth filter on this, not on the presence of a string.
3. **Nikud-only difference is a third state**, not a correction: points added to an unpointed
   standard do not make the unpointed read wrong.
4. **A signature is a claim.** Measured on vol.1, 6 of 20 signed strings were wrong, in one
   direction each (points, a word space, and confusable pairs of the fount). A tally cannot audit
   the standard it scores against, so a consumer must keep the route back to the pixels open.

## 5. Absence, refusal, and the three states

**`unknown` is not `false`.** Every flag a consumer may filter on has at least three states: the
condition holds, it does not, and **nobody measured it**. A field defaulted to `false` and consumed
as measured has already caused a wrong denominator in this project.

**Typed non-verdicts are first-class.** `abstain` (the human could not read it), `fault` (the input
was not fit to read) and `disputed` (two readings stand) are outcomes, not missing data. A format
with no channel for "nothing here" turns an honest component's refusal into a fabrication
downstream.

**A flag with no consumer is not a guard.** If a record carries `cut`, `over` or a box fault, the
consumer must either act on it or state in its own output that it did not.

## 6. Geometry invariants

1. **Native page pixels, one convention**, and the page size stated in the record (vol.1:
   3584 × 5400). No consumer rescales silently.
2. **A region is a LIST of per-column rectangles, never one spanning box.** A unit that spills
   bottom-left to top-right gets a second rect, not a bounding box across the gutter — that
   bounding box bleeds into the adjacent column, the footnotes and the header.
3. **Realized, not requested** (§3 rule 4), with the clamp bounds beside it.
4. **Ratified to the STRICT tolerance.** One truth set serves extraction (boxes must be complete
   and tight; clipping a tall letter feeds a mutilated crop to the gates) and navigation (loose).
   It is ratified to the strict one. The loose tolerance lives **downstream** as a fallback
   hierarchy — note box → column region → page — and never as an approved sloppy box.
5. **On segmentation failure, abstain and flag.** Never fall back to reading the whole band: that
   records one note where there were thirteen.
6. **Count is the gate.** Detected units must equal the extractor's count or the page abstains.

## 7. Run validity

- `git_start` and `git_end` each carry `{git_head, git_dirty, clean}`, with `git_dirty` derived from
  `git status --porcelain` — never a hand-rolled line-ending check, because git already knows about
  `autocrlf`.
- A run is **clean** only if both are clean **and identical**. Otherwise the record is
  `provisional: true` and may not be cited in an ADR or a tier change.
- **Run-level fault aborts and writes nothing.** Errors-out-of-the-denominator is not enough: a rate
  limit, or N consecutive dead items, invalidates the run. Rerun from the top; never splice.

## 8. Hash and naming rules

1. Every digest is taken over **UTF-8 bytes** of `json.dumps(obj, ensure_ascii=False,
   sort_keys=True, indent=<stated>)`, and the file is written **LF-only**. The options are part of
   the rule and must be stated wherever the rule is.
2. A **self-referential** digest cannot be a hash of the file that carries it. The rule is:
   parse, remove the digest field, re-serialise with the stated options, hash.
3. **A record that fails its own rule must not exist.** Stage to a temporary name, verify, then
   rename. Every refusal path sweeps the staging file.
4. **Names are content-addressed**, and a same-name/different-bytes write is **refused**, not
   clobbered. A fixed filename has already destroyed a 19-span approval in this project.
5. **A verifier must not call the producer.** A round-trip check that calls the same function that
   computed the value agrees by construction, and will pass on a deliberately wrong value. Spell the
   rule out at the check site, and prove the guard live by **mutation**, never by it going green.

## 9. Adjudication is a standoff record, never an edit

When a human overturns something in a signed set, the verdict is written **beside** the measurement,
joined on `(span_id, …)`, with its own `basis` — not into it. The measured record keeps what it
measured. Rewriting a class in place destroys the only thing a later reader needs: that the run said
one thing, a human said another, and which is grounded in what.

This applies to the signature itself. An editorial reading lives beside the printed form with its
basis and confidence; the corpus keeps the printed form.

## 10. Acceptance checks for a consumer

Runnable against any v1 set, in order.

**Checks 3, 4, 5, 6, 7 and 11 were run against vol.1's 74-span set while this form was written, and
all pass** — after the run corrected two claims this document made about its own format (the
`note_index` base and the `span_id` suffix, §2). Checks 1, 2, 8, 9, 10 and 12 are stated from the
rules in §3–§8 and have **not** been run as a suite; each guards a failure this project has had, but
a consumer should treat them as specified rather than as exercised.

1. `set_sha16` in stages 2 and 3 reproduces the digest of stage 1 **by the stated rule** (§8.1–8.2).
2. Every `crop_sha16` reproduces from the stored crop bytes.
3. `drop_accounting` balances: `root_n − dropped… = n`, and `n == len(rows)`.
4. `span_id` is unique and equals `"p%d:n%d" % (page, note_index - 1)` on every row (the two bases differ, §2).
5. `printed = page − printed_offset` holds wherever a printed page is written.
6. `1 <= note_index <= notes_on_page` on every row.
7. `over == box[2] − band_w` wherever `band_w` is not null, and `cut` agrees with the sign of `over`.
8. Every row with `cut != ""` is either consumed or explicitly declared unconsumed.
9. No row is `complete: true` with an unsigned tile; no row carries a signature **and** `abstain`.
10. No signed string equals the reverse of its candidate (§4.1).
11. `git_start == git_end` and both clean, or `provisional: true`.
12. Every field a consumer filters on is one of three states (§5) — and a field that is absent is
    read as `unknown`, never as `false`.

A consumer that cannot run 1, 2 and 3 has not been handed a truth set; it has been handed a table.

## What this form does NOT solve

- **It does not make a signature correct.** It makes the route back to the pixels, and the basis of
  the reading, recoverable. The measured error rate in signed vol.1 strings was 6 of 20.
- **It does not define the drawing of a population.** `limits` and `predictions` are required
  fields, but no schema can tell whether the prediction was registered before the rows were seen.
- **It says nothing about tolerances for a non-Hebrew unit.** Verse regions and body spans are
  ratified to the strict extraction tolerance by §6.4, but the pixel meaning of "tight" for a
  verse-heading rect has not been measured. That is the first thing the verse-region consumer should
  send back.
- **No `rule_kind`-style field records which structural variant was found.** Where a detector can
  accept two shapes (a single and a double printed rule, say) and records nothing that tells them
  apart, this format does not currently carry that distinction. A consumer who needs it should
  request the field rather than infer it from a width.
- **v1 is vol.1's shape.** It has never been emitted by a second volume. Generic is a claim that
  only survives a second book.
