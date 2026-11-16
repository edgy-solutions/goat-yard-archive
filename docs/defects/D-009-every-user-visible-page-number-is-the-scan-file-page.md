# D-009 — every user-visible page number is the scan-FILE page; users must see the PRINTED page

**Status**: open. Scheduled for 0.3.4 by ruling (Chris, 2026-11-15): *users see
the printed page of the BSB volume, never the scan-file page.* Scope and
acceptance are [§5 of the 0.3.4 scope](../releases/0.3.4.md), alongside
[D-008](D-008-viewer-opens-on-the-page-before-the-citation.md).
**Found**: 2026-11-15, from the same Genesis 2:15 panel that produced D-008.
**Affects**: 0.3.0, 0.3.2 and 0.3.3 identically — the number is born in
`backend/gill_search.py` and rendered by a `frontend/` that is byte-identical
from tag `0.3.0` to `release-0.3.3`. **Pre-existing on production, not a 0.3.3
regression.**
**User-visible**: yes, on every answer, in seven places, with no flag set.

## What happens

`gill_search.py:343` builds the citation string `[Vol {vol}, p. {page}]` from
`page_number`, which `ingest.py:1030` writes from `parse_page_info`'s parse of
the **filename** (`page106_image1.png`). That number is the scan file's index,
not the number printed on the leaf.

For volume 1 the printed page is `file - 88`. So the panel's `p. 106` is
printed page **18**, and the viewer badge's `PAGE 105` is printed **17**.

This is also why the scan URL resolves: the citation string and
`/scans/vol1_page106_image1.png` come from the same field in the same frame, so
they cannot disagree. The number is internally consistent and **not citable** —
a reader who opens Gill vol. 1 at p. 106 does not find Genesis 2:15.

## Every place the file page reaches a user

Read from the code, 2026-11-15. All of these render the file page today:

| where | code | shows |
|---|---|---|
| evidence panel citation | `App.tsx:799` ← `ev.citation` ← `gill_search.py:343` | `Vol 1, p. 106` |
| viewer badge | `App.tsx:949` | `Vol. 1 — Page 105` |
| gallery per-scan label | `ScanGallery.tsx:101` | `Page 105` |
| scan `alt` text | `ScanGallery.tsx:110` | `Page 105` — screen readers |
| hover titles | `App.tsx:692-693`, `App.tsx:761` | `View Source: [Vol 1, p. 106]` |
| citations array | `main.py:1108` → `App.tsx:821` | the same strings |
| dev fixture | `frontend/src/mock_data.ts:7` | `[Vol 1, p. 287]` |

## The channel rendering cannot fix

**The answer LM is handed the file page inside its context.** `bot.py:1016-1020`
writes `citation_tag` into `formatted_context`, and the `GillSignature` input
field says the context is *"tagged with Sentence IDs and [Vol, Page]
citations"* (`bot.py:984`). The prompt tells the model to cite with inline
SIDs, not `p.` strings, so in practice the prose does not carry page
numbers — but **the number is in the model's input**, and any draw that echoes
it produces a file page inside generated prose, downstream of every render fix.

Changing that tag is a **prompt-surface** change, gated by the standing rule
that a prompt edit can move the verbatim boundary and regress `verified`. So
either the tag carries the printed page under that gate, or a check asserts the
answer prose contains no `p. <n>` string. **Named, not decided.**

## The mapping does not exist yet

Searched 2026-11-15: **no `printed_page`, `page_offset`, `PAGE_OFFSET` or page
`-88` exists anywhere in the repository** — not in `backend/`, not in
`pipeline/scripts/`, not in the chart. Volume 1's offset of 88 is a lane fact
carried in notes and handoffs. There is nothing to generalize from and nothing
to copy: the per-volume mapping has to be **created**, and the other served
volume's offset **does not exist**.

It must be derived by a stated rule, not pinned as a number somebody
remembered: read the printed number in the **running head** of a sample of that
volume's scans, recorded as readings with the file page beside each; solve for
the offset and require it to be **constant across the sample** — a sample
yielding two offsets means a discontinuity (inserted plate, numbering restart)
and a single integer is the wrong model, which must be said rather than
averaged; record the offset with the volume, its derivation sample and the
date.

**Front matter needs a third state, not a number.** Pages whose printed number
is roman, or absent, have no arabic printed page, and no integer offset covers
them: `file 1 - 88` is negative. The mapping is a **function with a declared
domain**; a page outside that domain renders as what it is — the roman numeral,
or front matter with no number — **never a clamped 1, never a negative, never a
silently substituted file page**. A system with no "this page has no printed
number" channel turns an honest gap into a fabricated citation.

## Acceptance (from the 0.3.4 scope)

- Every row of the table renders the printed page, or renders no page number at
  all. One record may not carry a true and a false statement about one page.
- The response carries both numbers under **distinct names** (`page` stays the
  file page for the scan lookup; the printed page is its own field). No
  consumer infers one from the other by arithmetic at the call site.
- The mapping lives in **one named place, keyed by volume**, with its
  derivation sample and date beside it, returning a typed "no printed number"
  for front matter.
- **Born-tests, per volume**: expected printed numbers are *recorded readings
  of the running head*, never values computed by the mapping under test — a
  test that derives its expectation from the code it checks proves nothing.
  Assert the **count** of sampled pages, so a sample that silently shrinks
  reads as a failure rather than as silence. At least one front-matter page per
  volume, asserting the no-number state.
- The scan URL still resolves from the file page after the split, with a test
  that says so.
- The dev fixture is updated with it, or it teaches the next reader the old
  contract.

## What this entry does NOT establish

- **Not** that `-88` is right for volume 1 beyond the pages this lane has read.
  It is a lane fact with no recorded derivation sample in the repo; this entry
  schedules the derivation, it does not supply it.
- **Not** anything about the second served volume. Its offset is unknown, and
  assuming 88 would be exactly the "number somebody remembered" the acceptance
  forbids.
- **Not** that the file page should disappear. Internals keep file pages
  exactly as now; the scan lookup depends on them. Only the rendering changes.
- **Not** a fix for the viewer landing on the wrong page, which is
  [D-008](D-008-viewer-opens-on-the-page-before-the-citation.md). Correcting
  the number on a page the reader should not be looking at trades one wrong
  statement for another.
