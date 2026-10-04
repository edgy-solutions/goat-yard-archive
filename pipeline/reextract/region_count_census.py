# -*- coding: utf-8 -*-
"""Region-count agreement over every span-bearing page. The draw's actual gate.

The localizer abstained on 7 of 8 sampled spans, all for one reason: `page-abstain: count-mismatch`, the
detector's note-region count against the extractor's n_notes. That is the count-not-recognize guard doing its
job -- it will not index into regions it cannot count -- and it means the drawable population is decided by a
PAGE property, before any span, box or crop is considered. This measures it on all 414 span-bearing pages.

RETRACTION, 2026-10-04. The first run of this script reported `detected` == 2 on all 414 pages and
therefore `count-mismatch` on 369 of them (89%), which read as "the drawable population is decided by a
page property the detector almost never satisfies." It was not a measurement of anything.
`detect_regions()` returns a **2-tuple** `(ordered, stitched)`, and the call site took `len()` of the
tuple -- so the column was the constant 2, and the 45 "agreeing" pages agreed because they happen to
have two notes. The artifact `note_region_count_census_20261004.json` is retracted in full; this script
now writes `..._corrected.json` beside it rather than overwriting it, so the retraction stays auditable.

The shape error could not be caught by reading the numbers: a constant column is perfectly consistent
with itself, and the span census reproduced byte-for-byte beside it. So the guard here is not a tally, it
is `_regions()`: it asserts the call's SHAPE at the call site, and a second assert refuses to write an
artifact whose `detected` column never varies, because a detector that returns the same count on 414
pages was not consulted.

Local CV only. No outbound call, no crop written, no tree touched. Scratchpad only.
"""
import io
import json
import os
import sys
import time
from collections import Counter

# Import from THIS file's directory, never a hardcoded worktree: a copy of this script in the
# other lane's tree must import that lane's modules, not Lane B's.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, os.pardir, "scripts"))
import cv_footnote_presplit as ps                                          # noqa: E402  (Lane A's, read-only)
import note_line_region as NLR                                            # noqa: E402
import assembler as ASM                                                   # noqa: E402
from clean_run import git_state, provisional, banner                      # noqa: E402

PAGE = "C:/Users/cnogr/git/dr-voluminous/commentary/volume1/page%d_image1.png"
# The committed artifacts, by their committed names. Not a session scratchpad: a script in the repo must be
# able to reproduce the artifact beside it in the repo, and the dated filename is deliberate -- these are
# dated observations of a frozen apparatus run, so a rerun under a new date writes a NEW file rather than
# quietly replacing the one an ADR cites.
DV = "C:/Users/cnogr/git/dr-voluminous/reextract_vol1"
AUD = DV + "/audits"
CENSUS = AUD + "/hebrew_span_census_20261004.json"
OUT = AUD + "/note_region_count_census_20261004_corrected.json"
RETRACTED = AUD + "/note_region_count_census_20261004.json"   # kept, wrong, superseded
PROF = os.path.join(_HERE, "book_profile.gill.yaml")

rows = json.load(io.open(CENSUS, encoding="utf-8"))["rows"]
prof = ASM.load_profile(PROF)
assert prof, "no profile"


def _regions(band, profile):
    """detect_regions() returns (ordered, stitched). Unpack it HERE and assert the shape, because the
    bug this guards against was invisible downstream: len() of the 2-tuple is 2, which is a plausible
    note count, so every number computed from it stayed self-consistent."""
    out = NLR.detect_regions(band, profile)
    assert isinstance(out, tuple) and len(out) == 2,         "detect_regions() no longer returns (ordered, stitched) but %r -- do not take len() of its "         "return value, which is what produced the retracted census." % (type(out),)
    ordered, stitched = out
    assert isinstance(ordered, list), "detect_regions()[0] is %r, not the region list" % (type(ordered),)
    return ordered, bool(stitched)

pages = {}
for r in rows:
    pages.setdefault(r["page"], {"page": r["page"], "n_notes": r["notes_on_page"],
                                 "status": r["page_status"], "spans": 0})
    pages[r["page"]]["spans"] += 1

GIT_START = git_state(_HERE)
res, secs = [], []
t00 = time.time()
for i, p in enumerate(sorted(pages), 1):
    rec = dict(pages[p])
    t0 = time.time()
    try:
        strip, info = ps.presplit(PAGE % p, upscale=1)
        if strip is None:
            rec.update(detected=None, agree=False, why="no_strip")
        else:
            band = strip.convert("L")
            regs, stitched = _regions(band, prof)
            rec.update(detected=len(regs), stitched=stitched,
                       agree=(len(regs) == rec["n_notes"]),
                       why="" if len(regs) == rec["n_notes"] else "count-mismatch")
    except Exception as e:
        rec.update(detected=None, agree=False, why="%s: %s" % (type(e).__name__, str(e)[:70]))
    secs.append(round(time.time() - t0, 2))      # NOT in the row: a wall clock inside a data row makes
    res.append(rec)                              # the artifact unhashable against its own generator
    if i % 25 == 0:
        ok = sum(1 for r in res if r["agree"])
        print("  %3d/%d pages  agree %d (%.0f%%)  %.0fs elapsed"
              % (i, len(pages), ok, 100.0 * ok / len(res), time.time() - t00), flush=True)

# A detector that returns the same count on every page in the corpus was not consulted. This is the
# assertion the retracted run needed: it fires on the constant column itself, not on any tally over it.
_dv = sorted({r["detected"] for r in res if r["detected"] is not None})
assert len(_dv) > 1, (
    "`detected` is the constant %r on all %d pages, so it is not an output of the detector. That is the "
    "defect that produced the retracted census -- do not write this artifact." % (_dv, len(res)))

GIT_END = git_state(_HERE)
PROVISIONAL = provisional(GIT_START, GIT_END)
print(banner(GIT_START, GIT_END))
io.open(OUT, "w", encoding="utf-8").write(json.dumps(
    {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
     "git_start": GIT_START, "git_end": GIT_END, "provisional": PROVISIONAL,
     "retracts": os.path.basename(RETRACTED),
     "retraction_reason": "len() of detect_regions()'s (ordered, stitched) tuple: `detected` was the "
                          "constant 2 on all 414 pages, and the 45 'agreeing' pages have two notes",
     "footer": {"pages": len(res), "secs_total": round(sum(secs), 1),
                "secs_max": max(secs) if secs else None},
     "rows": res}, ensure_ascii=False, indent=1))
ok = [r for r in res if r["agree"]]
spans_ok = sum(r["spans"] for r in ok)
print("\npages: %d   agree: %d (%.0f%%)   spans on agreeing pages: %d of %d (%.0f%%)"
      % (len(res), len(ok), 100.0 * len(ok) / len(res), spans_ok, sum(r["spans"] for r in res),
         100.0 * spans_ok / sum(r["spans"] for r in res)))
print("why:", dict(Counter(r["why"] for r in res)))
print("delta detected-extractor:", dict(Counter((r["detected"] - r["n_notes"]) if r["detected"] is not None
                                                else "none" for r in res)))
print("agree by page status:", dict(Counter(r["status"] for r in ok)),
      "| all:", dict(Counter(r["status"] for r in res)))
print("stitch flagged on %d page(s)" % sum(1 for r in res if r.get("stitched")))
print("wrote", OUT, "-- retracts", os.path.basename(RETRACTED))
