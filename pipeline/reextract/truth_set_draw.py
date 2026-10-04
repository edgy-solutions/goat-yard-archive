# -*- coding: utf-8 -*-
"""Freeze the truth set: all 96 drawable spans, content-addressed, with the candidate WITHHELD.

Chris's ruling of 2026-10-04: draw all 96 and name the shortfall. "The number 100 was mine and it was
arbitrary; 96 of a defined population is better than 100 of a fudged one." So there is no sampling step
here and no stratification -- the set IS the population, which is why it can be frozen by its content
instead of by a seed.

Three things this file is responsible for, each because leaving it to a convention has already failed once:

1. CONTENT-ADDRESSED NAMING. The set's filename carries a hash of the set itself (span ids, pages, note
   indices, boxes, and the extracted Hebrew). A record of a human's yes must be named by what it describes:
   a fixed filename once let a single-span build destroy a 19-span approval. If the population shifts by
   one span, the name changes and the old signatures do not silently appear to cover the new set.

2. THE CANDIDATE IS WITHHELD FROM THE SIGNER VIEW. Ruling (4) requires signing from PIXELS with the
   candidate withheld, because the last signed truth set was 30% wrong in the direction of the extracted
   text -- the signer was reading a candidate and affirming it, in one case verbatim. So the signer file
   carries geometry and nothing readable: no Hebrew, no Greek, no note text. This is ASSERTED over the
   serialized bytes, not arranged by being careful, because "I did not include it" is not a property.

3. PREDICTIONS RECORDED FIRST, AND SPLIT BY SPAN LENGTH. The draw skews short (3+-word spans are 4% of
   the set against 11% of the pool), so a single averaged rate would hide the skew rather than name it.
   One prediction for one-word spans, one for multi-word, both written before a single crop is read.

What this does NOT do: cut a crop (Lane A's `note_crop.py`), send anything, or score anything. It emits
the crop request Lane A's cutter needs, in STRIP coordinates, which is the coordinate system the boxes
were measured in.
"""
import hashlib
import io
import json
import os
import re
import sys
import time
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from clean_run import git_state, provisional, banner                       # noqa: E402

DV = "C:/Users/cnogr/git/dr-voluminous/reextract_vol1"
AUD = DV + "/audits"
POOL = AUD + "/draw_pool_20261004.json"
AXIS = AUD + "/span_axis_census_20261004.json"

# Any readable script in the signer view defeats the withholding. Hebrew, its presentation forms, and
# Greek -- the three scripts a Gill note's adjudicable content is written in.
READABLE = re.compile(u"[\u0590-\u05FF\uFB1D-\uFB4F\u0370-\u03FF\u1F00-\u1FFF]")

GIT_START = git_state(_HERE)

pool = json.load(io.open(POOL, encoding="utf-8"))
assert pool.get("provisional") is False, \
    "the draw pool artifact is PROVISIONAL -- a truth set must not be frozen from a run that cannot be " \
    "cited. Re-run draw_pool.py over a clean tree first."
axis = {r["span_id"]: r["axis"] for r in json.load(io.open(AXIS, encoding="utf-8"))["rows"]}
SEALED = set(pool["sealed_pages"])

rows = [r for r in pool["rows"] if r["verdict"] == "BOX"]
rows.sort(key=lambda r: (r["page"], r["note_index"], r["span_id"]))
assert len(rows) == 96, "expected the measured population of 96, got %d -- the funnel moved, so the " \
                        "report's numbers and this set no longer describe the same thing" % len(rows)
assert not (SEALED & {r["page"] for r in rows}), "a sealed page is in the truth set"
assert all(r.get("cut") == "" for r in rows), "a span with a band-clip fault is in the truth set"
assert all(r.get("box") for r in rows), "a span with no box is in the truth set"

# ---- identity -------------------------------------------------------------------------------------
# The hash covers what is being adjudicated: which span, where on the page, which pixels, and what the
# extractor claims it says. A box redraw or a re-extraction changes the set's name, which is the point.
ident = [[r["span_id"], r["page"], r["note_index"], r["hebrew"], list(r["box"])] for r in rows]
SHA16 = hashlib.sha256(json.dumps(ident, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
OUT = AUD + "/truth_set96_%s.json" % SHA16
SIGN = AUD + "/truth_set96_%s_signer.json" % SHA16

# ---- the named limits, carried WITH the set, not in a report that may not travel with it -----------
one = [r for r in rows if r["words"] == 1]
multi = [r for r in rows if r["words"] > 1]
LIMITS = {
    "shortfall": "96 of a defined population, not 100. The 100 was arbitrary; the four spans a lower "
                 "localizer floor would have added are the ones the geometry trusts least.",
    "short_span_skew": "3+-word spans are 4%% of this set (%d of %d) against 11%% of the 654-span "
                       "unspent pool. Rates MUST be reported separately for one-word and multi-word "
                       "spans or the skew is averaged away."
                       % (sum(1 for r in rows if r["words"] >= 3), len(rows)),
    "not_a_corpus_sample": "this is the localizer-REACHABLE population. 295 of 414 pages fail the "
                           "note-count gate, so ~480 spans are unreachable before any box is attempted. "
                           "Coverage is a substrate question (Lane A2), not a reader question.",
    "stitch_pages_retained": "40 of 96 sit on stitch-flagged pages and are KEPT. Excluding them now "
                             "would halve the set to remove something nobody has measured as a fault; "
                             "if the glyph console shows one, exclude it afterwards WITH the reason.",
    "pointing_not_skewed": "nikud-bearing is 15%% here and 15%% in the pool (%d of %d), which is the "
                           "axis the Hebrew gates care about." % (sum(1 for r in rows if r["nikud"]),
                                                                 len(rows)),
    "axis_absent": "ruling (4)'s third stratification axis has 2 instances in the whole volume and "
                   "neither is drawable, so the set cannot be stratified on it: %s"
                   % dict(Counter(axis.get(r["span_id"], "?") for r in rows)),
}

# ---- predictions, recorded BEFORE any crop is read ------------------------------------------------
# Registered so that being wrong is informative. The split is the point: a single averaged rate would
# hide exactly the skew named above. Basis is stated per cell, and the base rate it leans on is itself
# suspect -- the n=19 figure was signed against a truth set later found 30% wrong, so these are
# predictions against PIXEL adjudication, which is a harder standard than the one that produced 18/19.
PREDICT = {
    "standard": "exact against a signature made from pixels with the candidate withheld",
    "one_word": {"n": len(one), "predicted_exact_pct": 92, "predicted_exact_n": round(0.92 * len(one)),
                 "basis": "a one-word span gives a plausible-word substitution almost nowhere to land, "
                          "and the published n=19 run was dominated by short spans. The residual I "
                          "expect is the fount's confusable PAIRS (ayin/tsadi, mem/pe, bet/gimel), "
                          "which are a property of the type and not of span length."},
    "multi_word": {"n": len(multi), "predicted_exact_pct": 79,
                   "predicted_exact_n": round(0.79 * len(multi)),
                   "basis": "substitution opportunity scales with word count, and the measured misread "
                            "class is a MORE fluent reading that differs from the printed form. I expect "
                            "the gap between the two cells to be real and larger than any arm-to-arm "
                            "difference measured so far."},
    "if_wrong": "if the two cells come out equal, span length is not the axis that matters and the "
                "skew limit above is overstated -- which would be worth more than the rate itself.",
}

meta = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "set_sha16": SHA16, "n": len(rows),
        "source": {"pool": os.path.basename(POOL), "axis": os.path.basename(AXIS),
                   "pool_funnel": pool["funnel"]},
        "page_numbering": "FILE pages (printed = file - 88)",
        "ruling": "Chris, 2026-10-04: draw all 96 and name the shortfall. Do not drop stitch pages; "
                  "exclude any afterwards only on a measured fault.",
        "limits": LIMITS, "predictions": PREDICT,
        "strata": {"one_word": len(one), "multi_word": len(multi),
                   "words": dict(Counter(min(r["words"], 4) for r in rows)),
                   "nikud": dict(Counter(r["nikud"] for r in rows)),
                   "stitch_page": dict(Counter(r["stitch_page"] for r in rows))}}

# ---- the signer view: geometry only ---------------------------------------------------------------
# `crop` is a REQUEST, not a path that exists. Lane A's note_crop.py owns the cutter; these are strip
# coordinates, the system the boxes were measured in.
sign_rows = [{"span_id": r["span_id"], "page": r["page"], "note_index": r["note_index"],
              "notes_on_page": r["notes_on_page"], "box_strip": list(r["box"]),
              "band": r["band"], "band_w": r["band_w"],
              "crop": "REQUESTED: volume1/page%d strip, box %s" % (r["page"], list(r["box"]))}
             for r in rows]
signer = {"generated": meta["generated"], "set_sha16": SHA16, "n": len(sign_rows),
          "page_numbering": meta["page_numbering"],
          "instruction": "Sign each span from its CROP. The extracted candidate is deliberately absent "
                         "from this file: the previous truth set was 30% wrong in the direction of the "
                         "candidate, once affirmed verbatim. Write what the pixels show, or abstain.",
          "withheld": ["hebrew", "note text", "any extracted reading"],
          "rows": sign_rows}

blob = json.dumps(signer, ensure_ascii=False, sort_keys=True)
hit = READABLE.search(blob)
assert not hit, "the signer view contains readable Hebrew/Greek at offset %d (%r) -- the candidate is " \
                "not withheld, and a signature made against this file would be worth nothing" \
                % (hit.start(), blob[max(0, hit.start() - 40):hit.start() + 10])
assert "hebrew" not in {k for row in sign_rows for k in row}, "a signer row carries a `hebrew` key"
# And the assert must be able to fire: a pattern that matches nothing passes on everything.
assert READABLE.search(rows[0]["hebrew"]), \
    "the withholding check cannot match the very Hebrew it exists to exclude -- it would pass on anything"

GIT_END = git_state(_HERE)
for d, p in ((dict(meta, provisional=provisional(GIT_START, GIT_END), git_start=GIT_START,
                   git_end=GIT_END, rows=rows), OUT),
             (dict(signer, provisional=provisional(GIT_START, GIT_END)), SIGN)):
    json.dump(d, io.open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print("set %s  n=%d  one-word %d  multi-word %d  nikud %d  stitch-page %d"
      % (SHA16, len(rows), len(one), len(multi), sum(1 for r in rows if r["nikud"]),
         sum(1 for r in rows if r["stitch_page"])))
print("predicted exact: one-word %d/%d (%d%%)   multi-word %d/%d (%d%%)"
      % (PREDICT["one_word"]["predicted_exact_n"], len(one), PREDICT["one_word"]["predicted_exact_pct"],
         PREDICT["multi_word"]["predicted_exact_n"], len(multi),
         PREDICT["multi_word"]["predicted_exact_pct"]))
print("pages %d  crops to request %d (Lane A note_crop.py, strip coords)"
      % (len({r["page"] for r in rows}), len(sign_rows)))
print(banner(GIT_START, GIT_END))
print("wrote", os.path.basename(OUT))
print("wrote", os.path.basename(SIGN))
