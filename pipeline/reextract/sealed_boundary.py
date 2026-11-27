# -*- coding: utf-8 -*-
u"""The sealed-page boundary, as the UNION of every record in the tree that names one.

Why this file exists.  On 2026-11-25 `localizer45_run.sealed_pages()` derived the boundary from the
keys of `hebrew_aperture_diag.SEALED_TRUTH` -- a SPAN table -- and got ten pages.  Three records in
this tree name a sealed page, and no two of them agree:

  * `hebrew_aperture_diag.SEALED`              15 pages SINCE 2026-11-26, 14 when this module
                                               was written.  The page-level seal record; the
                                               one `hebrew_glyph_card.seal_state` consults.
  * `draw_pool_20261004.json["sealed_pages"]`  11 pages (Lane A's substrate wrote it, and
                                               span_axis_census and truth_set_draw read it).  It
                                               carried 102, which `SEALED` did not until the
                                               2026-11-26 ruling, and omits 129, 206, 478 and
                                               543, which `SEALED` has.
  * the pages of `SEALED_TRUTH`'s keys         10 pages.  A subset of `SEALED`, and not a boundary:
                                               a page is sealed whether or not a Hebrew span on it
                                               was ever signed.

So the span-derived read was short by five pages, and four of those five -- 129, 206, 478, 543 --
are pages the DRAW did not exclude either.  A boundary that each consumer re-derives for itself is
one consumer away from a page being spent twice.

The rule here is the union, and the union is not a compromise: over-excluding a page costs one span
that nobody sends, and under-excluding one re-opens a page that is SPENT.  Those two errors are not
the same size, so the function does not try to adjudicate which record is right.  It reports the
disagreement as a fact -- `disagreement()` names exactly which record is missing which page -- and
leaves the adjudication to Chris, because what makes a page sealed is a human's ratification and
not a set operation.

An unreadable record RAISES.  An unreadable boundary is not an empty one.

RULED 2026-11-26 (Chris): "the union of 15 stands as the rule unless Chris says otherwise."  So the
union is no longer this module's caution -- it is the rule, and `PINNED_UNION` is what every Lane B
consumer asks.  What the ruling settles is the BOUNDARY: which pages may be read, drawn and sent.

What it does NOT settle, and what `signed_rows_on_union_pages()` measures so that nobody has to
rediscover it: page 102 carries a SIGNED row, `p102:n0`, in `hebrew_aperture_diag.TRUTH` -- the OPEN
truth table -- and no row in `SEALED_TRUTH`.  It is also the ONE span on a union page inside
`D.build_set()` (the unsealed build set, 11 spans); the other ten union-page spans are reachable
only through `include_sealed=True`.  So honouring the union AT THE CARD LAYER would move a signed
row from the open table to the sealed one, drop the unsealed build set from 11 to 10, and re-draw
five pinned populations that name `p102:n0` by hand (`hebrew_span_ceiling`, `hebrew_bind._MEASURED`,
`test_hebrew_frontier_or._EXPECT`, and two in `test_hebrew_sealed_truth`).  That is a second
decision about SIGNED TRUTH, with its own evidence, and `hebrew_glyph_card.seal_state` is therefore
left as it is: page-level off `SEALED`, which still answers "102 is not sealed".  The boundary rule
and the signing surface disagree about exactly one page, on purpose, in the open, until Chris rules
on the row rather than on the page.
"""
import io
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
POOL = ("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits/draw_pool_20261004.json")

# The union, pinned.  MEASURED 2026-11-25 over the three records below; it is a snapshot of a
# SAFETY boundary, so it is pinned rather than trusted, and a change in any record has to come
# through a human reading this line.
PINNED_UNION = 15
# SEALED 14 -> 15 and SEALED_TRUTH_pages 10 -> 11 on 2026-11-26: page 102 was ruled sealed and
# p102:n0's signed row moved into the sealed table with it.  The UNION did not move, which is
# the point -- the ruling closed a disagreement between two records, it did not widen the
# boundary.  Per-source counts are pinned so that a source changing under the union is a
# refusal here and not a silent re-derivation.
PINNED_SOURCES = {"SEALED": 15, "draw_pool_artifact": 11, "SEALED_TRUTH_pages": 11}

# The ruling that makes the union the rule rather than this module's caution.  Consumers cite it;
# nothing reads it to decide anything, because the decision is `union()`.
RULING = {
    "date": "2026-11-26",
    "by": "Chris",
    "words": "the union of 15 stands as the rule unless Chris says otherwise",
    "settles": "the boundary: which pages may be read, drawn and sent",
    "does_not_settle": ("nothing outstanding as of the second ruling of 2026-11-26, which "
                        "settled the one row this boundary left open; see `ROW_RULING` and "
                        "signed_rows_on_union_pages(), whose open-table list is now empty"),
}

# The second ruling of the same day, about the ROW rather than the page. Kept separate because
# they are two decisions: the first says which pages are spent, this one says where a signed
# reading on such a page stands.
ROW_RULING = {
    "date": "2026-11-26",
    "by": "Chris",
    "words": ("Under the union of 15, page 102 is sealed: take p102:n0's card out of the "
              "item-3 build set"),
    "done": ("102 joined `hebrew_aperture_diag.SEALED` and p102:n0's row moved from TRUTH to "
             "SEALED_TRUTH byte for byte, so the unsealed build set is 10 cards and the "
             "combined set is unchanged at 21"),
    "not_done": ("the reading was not reopened, re-scored or withdrawn, and the alignment "
                 "gate was not touched. A sealed page may be READ under the ruling-2 "
                 "carve-out and never re-scored"),
    "label_correction": ("the phrase \"the item-3 build set\" is this lane's wording, from the "
                         "2026-11-26 questions file, and it was loose: item 3 of the "
                         "2026-11-01 ruling is the `signable` rule, whose population never "
                         "contained p102:n0 (it is absent from the 2026-10-25 audit, so "
                         "`signable` returned False before this ruling and after it). The set "
                         "the ruling MOVED is the unsealed `hebrew_aperture_diag.build_set()` "
                         "-- the 11 cards this module reported as the collision -- and that is "
                         "the set named here, measured rather than inferred from the label"),
}


def _sealed_record():
    u"""`hebrew_aperture_diag.SEALED` and the pages of its signed span keys."""
    import hebrew_aperture_diag as _d
    sealed = getattr(_d, "SEALED", None)
    if not sealed:
        raise RuntimeError("hebrew_aperture_diag.SEALED is missing or empty: the page-level seal "
                           "record cannot be read, and an unreadable boundary is not an empty one.")
    truth = getattr(_d, "SEALED_TRUTH", None)
    if truth is None:
        raise RuntimeError("hebrew_aperture_diag.SEALED_TRUTH is missing: the signed span table "
                           "cannot be read.")
    span_pages = set()
    for k in truth:
        m = re.match(r"^p(\d+):n\d+$", str(k))
        if m:
            span_pages.add(int(m.group(1)))
    return set(int(p) for p in sealed), span_pages


def _pool_record():
    u"""The sealed set the DRAW used, read from the artifact and never by importing draw_pool.

    `draw_pool.py` is Lane A's substrate and a script: importing it runs the draw and rewrites its
    own output.  Reading it is use; running it is not."""
    if not os.path.exists(POOL):
        raise RuntimeError("%s is missing: the sealed set the draw itself used cannot be read."
                           % os.path.basename(POOL))
    d = json.loads(io.open(POOL, encoding="utf-8").read())
    got = d.get("sealed_pages")
    if not got:
        raise RuntimeError("%s carries no `sealed_pages`: the draw's own boundary is unreadable."
                           % os.path.basename(POOL))
    return set(int(p) for p in got)


def sources():
    u"""{record name: the pages it names}.  Every record, each under its own name."""
    sealed, span_pages = _sealed_record()
    return {"SEALED": sealed,
            "draw_pool_artifact": _pool_record(),
            "SEALED_TRUTH_pages": span_pages}


def union(check=True):
    u"""Every page any record calls sealed.  The set a gate must use."""
    src = sources()
    u = set()
    for v in src.values():
        u |= v
    if check:
        counts = dict((k, len(v)) for k, v in src.items())
        if len(u) != PINNED_UNION or counts != PINNED_SOURCES:
            raise RuntimeError(
                "the sealed boundary moved: union %d (pinned %d), per record %r (pinned %r). This "
                "is a safety boundary, so it does not widen or narrow silently -- read the change, "
                "then move the pin." % (len(u), PINNED_UNION, counts, PINNED_SOURCES))
    return u


def disagreement():
    u"""[(record, page)] -- each page some record calls sealed and this one does not name.

    Reported, not resolved.  What makes a page sealed is a ratification, not a set operation."""
    src = sources()
    u = set()
    for v in src.values():
        u |= v
    return sorted((k, p) for k, v in src.items() for p in sorted(u - v))


def intersects(pages):
    u"""The sealed pages among `pages`, MEASURED.  A registered `0` is a prediction, not a result."""
    return sorted(set(int(p) for p in pages) & union())


def signed_rows_on_union_pages():
    """Where the boundary rule and the SIGNING SURFACE disagree, measured rather than argued.

    A page in the union may carry a signed row in either truth table.  A row in `SEALED_TRUTH` is
    consistent with the seal -- that table exists for sealed pages.  A row in `TRUTH`, the OPEN
    table, is the collision: the rule calls the page spent while the signed reading lives where
    unsealed readings live.  Returns both lists, plus the unsealed build set and its union-page
    members, so the size of the open question is a number and not an impression.

    Imported lazily: this module is a boundary, and nothing about the boundary should depend on the
    card/diagnostic layer being importable.
    """
    import hebrew_aperture_diag as D
    u = set(union())

    def _page(sid):
        return int(sid.split(":")[0][1:])

    build = [s["span_id"] for s in D.build_set()]
    return {
        "sealed_table": sorted(s for s in D.SEALED_TRUTH if _page(s) in u),
        "open_table": sorted(s for s in D.TRUTH if _page(s) in u),
        "build_set_n": len(build),
        "build_set_on_union": sorted(s for s in build if _page(s) in u),
    }


if __name__ == "__main__":
    u = union()
    print("sealed union: %d pages  %s" % (len(u), sorted(u)))
    for k, v in sorted(sources().items()):
        print("  %-20s %2d pages" % (k, len(v)))
    for k, p in disagreement():
        print("  DISAGREEMENT: %s does not name page %d" % (k, p))
    print("ruled %s by %s: %s" % (RULING["date"], RULING["by"], RULING["words"]))
    coll = signed_rows_on_union_pages()
    print("  signed rows on union pages: %d sealed-table, %d OPEN-table %s"
          % (len(coll["sealed_table"]), len(coll["open_table"]), coll["open_table"]))
    print("  unsealed build set: %d span(s), %d of them on a union page %s"
          % (coll["build_set_n"], len(coll["build_set_on_union"]), coll["build_set_on_union"]))
