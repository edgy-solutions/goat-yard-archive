# D-001 — Digit misread inside a citation

**Status:** open, named, not fixed.
**Found:** vol.1 body shadow run, step 1 (old-site vs re-extraction, 74 Chris-signed spans over
17 pages). Evidence: `dr-voluminous/body_shadow_vol1/step1_old_vs_run.md` and
`body_shadow_vol1/LANE_A_INVENTORY.md`. Raised to a named defect per ruling 5.

## The defect

Two of the re-extraction's four regressions on the signed set are digits inside citation numbers,
both on file page 761, both the **third digit of a three-digit number**:

| span | old layer | re-extraction |
|---|---|---|
| `p761:n7` | `c. 586` | `c. 580` |
| `p761:n8` | `c. 583` | `c. 533` |

These are Schulchan Aruch section numbers. **A wrong section number is a wrong reference, not a
typo** — it resolves, silently, to a different place in a real book. The other two regressions on
the set are punctuation (`T.` → `T,`, `T.` → `T'.`), which a reader absorbs; this class a reader
cannot detect at all.

This is **the only class on that set where the old layer is genuinely better than the
re-extraction.** That fact is what makes it worth a record rather than a line in a report.

## Why it is its own class, not "OCR is imperfect"

Prose has redundancy. A misread word in a Latin sentence is usually visible — it makes the
sentence ungrammatical, or it is a word that does not exist, and the next layer or the reader
catches it. **A three-digit citation number has no redundancy whatsoever.** Every one of the
1,000 values is equally well-formed, so a single wrong glyph produces output that is
indistinguishable from a correct read by inspection of the text alone. There is nothing
downstream that can notice.

That is also why a model is the wrong owner for the recovery: there is no linguistic signal for
it to reason from. This is a *seeing* problem in a span with zero error-correcting structure —
which is the population that the "spend pixels, not parameters" finding points at, and the
opposite of the self-glossing spans where frontier escalation earns its cost.

Both instances landing on one page, and both on the third digit, is suggestive of a local cause
(print quality or crop on that page) rather than a uniform per-glyph error rate. **Suggestive is
all it is** — two samples, and I have not looked at the page image. The causal story is a claim
too, and this one is untested.

## Proposed deterministic check

Two parts, because they have different lifetimes. Neither tries to decide which reading is
correct — per the bidirectional-editorial finding, the old layer has been wrong in this exact
region too (p619, where it turned Hebrew into digits), so an auto-picker would be inventing an
authority nobody has.

### Check 1 — digit-diff tripwire (available now, dies when the old layer does)

Where old layer and re-extraction both produce a note at the same index and the texts are
otherwise near-identical (normalised difflib ratio ≥ 0.85), compute the diff. **If every
differing character is a digit, emit an adjudication item** — never a score, never a silent
accept of either side. Deterministic, ~free, and it would have caught both p761 spans:
`586`/`580` and `583`/`533` are single-digit diffs inside otherwise-exact spans.

The verdict vocabulary is the existing one: keep / take / neither.

This check only exists where a prior layer exists. It covers vol.1 and vol.7 and nothing after,
which is exactly why it is not the whole answer.

### Check 2 — citation-digit spans are a declared low-redundancy class (survives to vol.3+)

Detect citation-shaped spans containing digits by pattern — `c. NNN`, `fol. NN`, `p. NNN`,
`ch. N`, `ver. N`, and the profile's own citation forms. The **detection is deterministic**; that
is the only thing being claimed here. Spans that match are marked as a named class whose single
read is **not** sufficient evidence, and are routed to either a second witness or the human
adjudication queue.

What this deliberately does **not** do:

- It does not validate the number against any external register of Schulchan Aruch sections.
  That would be a real check and it is a different project; asserting it here would be grounding
  theater.
- It does not guess. A span with no second witness and no adjudication stays flagged, not
  repaired.
- It does not claim a rate. Two instances on one page is the entire evidence base for the class's
  frequency, and the signed set that produced it is selection-biased in the run's favour (17
  pages chosen because note counts agreed, excluding every segmentation-collapse page).

## What this does NOT solve

- **No measurement of how often it happens.** Two spans. The class is named on the strength of
  its *severity* and its undetectability, not its measured frequency. Establishing a rate needs a
  digit-bearing-span census across the corpus, which does not exist yet.
- **Neither check corrects anything.** Both produce work for a human. That is the intended
  ceiling.
- **Check 2 cannot fire on a citation whose shape the pattern does not cover**, and the pattern
  is drawn from vol.1's forms. It belongs in `book_profile.yaml`, not in the detector, so a
  second book can carry its own.
- **The page-local hypothesis is untested.** If the cause is the p761 crop, the right fix is a
  re-crop at higher resolution and neither check above is the primary remedy — they are the net
  under it. Looking at the page image settles this and has not been done.
