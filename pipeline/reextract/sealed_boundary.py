# -*- coding: utf-8 -*-
u"""The sealed-page boundary, as the UNION of every record in the tree that names one.

Why this file exists.  On 2026-11-25 `localizer45_run.sealed_pages()` derived the boundary from the
keys of `hebrew_aperture_diag.SEALED_TRUTH` -- a SPAN table -- and got ten pages.  Three records in
this tree name a sealed page, and no two of them agree:

  * `hebrew_aperture_diag.SEALED`              14 pages.  The page-level seal record; the one
                                               `hebrew_glyph_card.seal_state` consults.
  * `draw_pool_20261004.json["sealed_pages"]`  11 pages (Lane A's substrate wrote it, and
                                               span_axis_census and truth_set_draw read it).  It
                                               carries 102, which `SEALED` does not, and omits
                                               129, 206, 478 and 543, which `SEALED` has.
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
PINNED_SOURCES = {"SEALED": 14, "draw_pool_artifact": 11, "SEALED_TRUTH_pages": 10}


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


if __name__ == "__main__":
    u = union()
    print("sealed union: %d pages  %s" % (len(u), sorted(u)))
    for k, v in sorted(sources().items()):
        print("  %-20s %2d pages" % (k, len(v)))
    for k, p in disagreement():
        print("  DISAGREEMENT: %s does not name page %d" % (k, p))
