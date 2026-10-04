# -*- coding: utf-8 -*-
"""Cut the truth-set crops: A2 span box at PAD=12. One recipe for the whole set.

WITHDRAWN 2026-10-04, AND THE REASON IS WORTH KEEPING. Everything below about the band-clip stands as
written and the code still runs when `CLIP_AS_SET_RECIPE` is turned on for a single span. It is not the
set recipe. Chris: "Sixteen of the multi-line crops have the extra line INSIDE the box, so the clip's
intended case didn't occur once, and where it did fire it had to choose a line by a centre-row
heuristic." The 74 are cut at PAD=12 exactly like the 19 already signed, which also keeps the two sets
comparable. The one measurement of whether the clip buys accuracy is the p912 pad probe: 24 paired arms,
14 exact at PAD=12 against 15 with the clip -- a net of +1 across 10 arms that changed tag, with
claude-sonnet-5 and gemini-3.8-flash both going exact -> wrong. That is a null, not a case.

Chris, 2026-10-04: "cutting is use, not a substrate change" -- so Lane B cuts these itself rather than
asking A2. The 96 are A2 SPAN boxes, not note boxes: `note_crop.py`'s `page_note_crops()` cuts note
boxes, which are the A1 aperture, and an A1 note-box crop may never leave the network. So the recipe
mirrored here is this harness's own `crops()` path exactly -- `_native_crop` with PAD, then
`crop_fault` before anything is kept -- with two deliberate differences:

  1. A SEPARATE, CONTENT-ADDRESSED CROP DIRECTORY. The 19-span aperture corpus in `CROPDIR` carries a
     manifest with a narrowing-refusal guard; writing 96 spans of a different population into it would
     either trip that guard or quietly redefine what the index describes. The directory name carries
     the truth set's own sha16, so a set that shifts by one span cannot land on these pixels.
  2. NO A1 LOOP. There is no `("A1_notebox", ...)` row here at all, so a note-box crop is not merely
     unsent, it is unreachable by construction -- the same arrangement the frontier caller uses.

WHY BOTH RECIPES. The pad probe (p912:n2, 24 paired arms) did not settle the cut: the tally is +1 for
band-clip with TEN arms moving class, and the production primary lost `exact`. The one signal that is
not noise-dominated is the ink -- PAD=12 bridged a two-word signature into a single 384px column run
and the trim separated it. So both are cut, locally, and the pair goes on the contact sheet wherever
the two differ in resolved word runs. Chris adjudicates that on pixels.

THE TRIM RULE, AND WHY IT IS NOT A THRESHOLD. "Top cut at the quietest row of the interline gap" needs
a definition of quiet, and the first version of this file tried to derive one from the 96's own valley
depths. There is NO empty band in that distribution -- the valley ratios run smoothly from 0.007 to
1.787, and five of them exceed 1.0, meaning the walk stopped on a row with MORE ink than the span's own
line. A floor derived from that gap would have been a floor derived from nothing.

So the rule is structural instead, and it only ever removes rows that provably belong to ANOTHER text
line: a row is cut if it falls in an ink run that (a) does not overlap the span's own line band, and
(b) is either thick enough to be a line of type (`MIN_BAND_PX`) or touches the crop edge, which is what
a neighbouring line truncated by the pad looks like. Whitespace is never removed and no row of the
span's own band can be. The conventions are `hebrew_glyph_card`'s, already derived and in use.

Measured against the one clip a human has approved (p912:n2, rows 14-72 of 81, 2 word runs):

    PAD=12, all 81 rows      1 word run  [384]        <- the two words bridged by foreign ink
    hand-built clip 14-72    2 word runs [200, 135]   <- approved 2026-10-04
    THIS RULE      14-78     2 word runs [200, 135]   <- same widths, 6 more rows kept
    line_band tight 31-65    3 word runs [15, 174, 135]  <- REJECTED: fragments a word

That last line is why the trim is not `line_band()` itself: cutting to the span's own band amputates
the word. This rule is strictly more conservative than the approved clip and resolves the same words.
The probe's warning travels with it: "trim the pad to the band" must never become "trim the pad to the
box" -- nothing here reads the box's edge.

Every clip is verified by `hebrew_aperture_diag.bandclip_fault()`, which proves against the PIXELS that
it is a full-width row range of its A2 parent, so no clip can introduce a pixel the parent lacked.

What this does NOT do: send anything, spend anything, open a sealed page, touch the alignment gate, or
write into `CROPDIR`. FILE pages throughout (printed = file - 88).
"""
import hashlib
import io
import json
import os
import sys
import time
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "scripts"))   # the presplit lives there
from PIL import Image                                                      # noqa: E402
import numpy as np                                                         # noqa: E402
import cv_footnote_presplit as ps                                          # noqa: E402
import note_region                                                        # noqa: E402
import crop_quality                                                        # noqa: E402
import hebrew_glyph_card as G                                              # noqa: E402
import hebrew_aperture_diag as HAD                                        # noqa: E402
from clean_run import git_state, provisional, banner                      # noqa: E402

# The re-frozen set (2026-10-04). The 96 set keeps its own name, files and crop directory: a set is
# dropped FROM, never edited, and its cut artifact is the record of the faults that caused the drop.
SET, SET_N = "0401b636ffa7bf1a", 74

# BAND-CLIP WITHDRAWN AS A SET RECIPE. Chris, 2026-10-04: "A recipe that abstains on 18 of 42 and chose
# wrong on one is not a set-wide cut. The 76 get the same crop recipe as the 19 you've already signed,
# which also keeps the two sets comparable." The clip machinery below is KEPT and still guarded, as a
# per-span tool for when a cleaner card is wanted on one span -- it is not a pipeline step, and with
# this flag off it is not attempted. A row's `clip_abstain` then reads `withdrawn:` rather than
# `abstain:`, because "not attempted" and "attempted and refused" are different facts and a tally that
# merges them would report 74 abstains as if the rule had looked at something.
CLIP_AS_SET_RECIPE = False
NOT_ATTEMPTED = "withdrawn:band-clip-is-not-a-set-recipe"
TRUTH = HAD.DATA / ("truth_set%d_%s.json" % (SET_N, SET))
OUTDIR = HAD.DATA / ("truthset%d_crops_%s" % (SET_N, SET))
OUT = HAD.DATA / ("truthset%d_cut_%s.json" % (SET_N, SET))
PAD = HAD.PAD

# The column-run convention, taken from the pad probe unchanged so the two runs are comparable: a word
# run is a maximal inked column range separated by >= GAP_MIN empty columns and at least RUN_MIN wide.
GAP_MIN, RUN_MIN, INK_THR = 10, 8, 128

GIT_START = git_state(_HERE)

tset = json.load(io.open(str(TRUTH), encoding="utf-8"))
assert tset.get("provisional") is False, "the truth set is PROVISIONAL -- do not cut from it"
assert tset["set_sha16"] == SET and tset["n"] == SET_N, \
    "this is not the frozen set: %r n=%r" % (tset["set_sha16"], tset["n"])
rows = tset["rows"]
SEALED = set(HAD.SEALED_TRUTH) if isinstance(HAD.SEALED_TRUTH, dict) else set()
assert not (SEALED & {r["span_id"] for r in rows}), "a sealed span is in the cut list"
# The pad is applied in NATIVE px after the strip->native map, exactly as `crops()` does. Read from the
# harness rather than retyped, so a change there cannot leave this file describing different crops.
assert PAD == 12, "the A2 recipe's pad moved (%r); the probe and this cut would disagree" % PAD


def rule_band_fault(im):
    """Refuse a crop that holds no line of TYPE -- the local pre-check Chris asked for, 2026-10-04.

    `crop_quality.crop_has_line()` passes on a printed footnote RULE, because a rule IS an inked
    band: 14 of the first 96 crops were a single 7-13px full-width run with nothing else in them,
    and every one of them passed every gate this harness has. The lane already owns the right
    constant -- MIN_BAND_PX is the floor for an ink run to be a line of type -- it had simply never
    been asked about a crop. This asks.

    It is a REFUSAL, not a flag, because the crop's only use is to be signed and nothing in it can
    be read: writing the file is what puts it in front of somebody. The gate itself lives in Lane
    A's `crop_quality.py` and is being requested there, not edited here; this is Lane B refusing to
    hand out a crop it has measured as unreadable, which is the part Lane B owns.
    """
    runs = G.ink_runs(im)
    if not runs:
        return "blank:no-ink-run"                     # crop_fault should have caught this already
    thick = [r for r in runs if (r[1] - r[0] + 1) >= G.MIN_BAND_PX]
    if thick:
        return None
    return ("no-line-of-type:runs=%s:min_band_px=%d"
            % ([r[1] - r[0] + 1 for r in runs], G.MIN_BAND_PX))


def word_runs(im):
    """Resolved word runs by the column ink profile -- counting gaps, never recognizing letters."""
    a = np.asarray(im.convert("L"))
    col = (a < INK_THR).sum(axis=0) > 0
    out, cur, gap = [], None, 0
    for x, v in enumerate(col):
        if v:
            cur = x if cur is None else cur
            gap = 0
        elif cur is not None:
            gap += 1
            if gap >= GAP_MIN:
                out.append((cur, x - gap))
                cur, gap = None, 0
    if cur is not None:
        out.append((cur, len(col) - 1))
    wide = [r for r in out if r[1] - r[0] >= RUN_MIN]
    return [r[1] - r[0] for r in wide]


def clip_rows(im, n_rects):
    """The rows a band-clip keeps, or an abstain. Removes only rows belonging to another text line.

    See the module docstring for the rule and for the measurement that chose it over `line_band()`.
    A stacked crop abstains: `_native_crop` joins two native rects with a 20px white gap, so the
    "other run" there is the span's own second half and trimming it would delete half the signature."""
    if n_rects > 1:
        return None, "abstain:stacked-crop-%d-rects" % n_rects
    # THE BOX IS THE ONLY STATEMENT ABOUT WHERE THE SPAN IS. `line_band` picks the inked band nearest
    # the crop's CENTRE row, on the premise in its docstring that "the box was drawn on that line, so
    # the centre is on it". That premise holds only for a box tight on one line. Found by eye on
    # p677:n13, 2026-10-04: its box covers two text lines (39px and 33px), the centre row fell in the
    # gap between them, and the nearest band won by 4px against 6px -- so the clip kept the roman line
    # and deleted the one carrying the Hebrew. Nothing downstream could see it: the kept band is a
    # perfectly good line of type, the trim removes a perfectly good line of type, and the run count
    # went UP. Measured over all 42 clips: 16 crops hold more than one line of type, and in all 16 the
    # extra line is inside the BOX, not brought in by the pad -- the case this clip was designed for
    # (a pad-neighbour) did not occur once. So the clip abstains, and those boxes are a redraw
    # question. A line counts as inside the box when a full line of type's worth of it is.
    _y0, _y1 = PAD, im.height - PAD
    _in = [(a, b) for a, b in G.ink_runs(im)
           if min(b, _y1 - 1) - max(a, _y0) + 1 >= G.MIN_BAND_PX]
    if len(_in) > 1:
        return None, ("abstain:box-covers-%d-lines-of-type:%s:nothing-here-knows-which-holds-the-span"
                      % (len(_in), [b - a + 1 for a, b in _in]))
    band = G.line_band(im)
    if not band:
        return None, "abstain:no-line-band"
    # THE BAND IS A CLAIM TOO. Found by eye on p558:n3, 2026-10-04: its crop holds two text lines
    # (37px and 39px) with a 6px run of descenders and stops between them, and `line_band` returned
    # the 6px run. The clip rule then did exactly what it promised -- it never removes the span's own
    # band -- and deleted both real lines, keeping a 14px sliver that resolved "6 words". The guard
    # was sound; its INPUT was wrong, which is the lane's own law that a gate's inputs must not
    # depend on what the gate checks. So the same derived constant is asked about the band itself: a
    # band thinner than a line of type is not the span's line, and nothing may be trimmed against it.
    if (band[1] - band[0]) < G.MIN_BAND_PX:
        return None, ("abstain:line-band-is-not-a-line-of-type:%dpx:floor-%d"
                      % (band[1] - band[0], G.MIN_BAND_PX))
    b0, b1 = band[0], band[1] - 1                      # line_band returns y1 EXCLUSIVE
    h = im.height
    runs = G.ink_runs(im)
    top, bot, removed = 0, h - 1, []
    for y0, y1 in runs:
        if not (y1 < b0 or y0 > b1):
            continue                                   # overlaps the span's own line: never removed
        thick, edge = (y1 - y0 + 1) >= G.MIN_BAND_PX, (y0 == 0 or y1 == h - 1)
        if not (thick or edge):
            continue                                   # a thin interior speck is not a text line
        removed.append([y0, y1, "thick" if thick else "edge"])
        if y1 < b0:
            top = max(top, y1 + 1)
        else:
            bot = min(bot, y0 - 1)
    if (bot - top + 1) < G.MIN_BAND_PX:
        # Post-condition, independent of how the trim was reached: whatever survives must still be
        # thick enough to BE a line of type. p381:n1 kept 17px of a crop whose thickest ink run was
        # 30px and nobody would have looked at it, because its run count did not change.
        return None, ("abstain:clip-would-keep-%dpx-under-the-%dpx-line-floor"
                      % (bot - top + 1, G.MIN_BAND_PX))
    if not (top <= b0 and bot >= b1 and top < bot):
        return None, "abstain:trim-would-enter-the-span-band:%d-%d-vs-band-%d-%d" % (top, bot, b0, b1)
    return {"rows": [top, bot], "kept": bot - top + 1, "of": h, "line_band": [b0, b1],
            "trim_top": top, "trim_bot": h - 1 - bot, "removed_runs": removed}, ""


OUTDIR.mkdir(parents=True, exist_ok=True)
built, page_cache, faults, clip_faults = [], {}, {}, {}
for r in rows:
    pg, sid, box = r["page"], r["span_id"], r["box"]
    if pg not in page_cache:
        strip, info = ps.presplit(str(HAD.IMG / ("page%d_image1.png" % pg)), upscale=1)
        page_cache[pg] = (Image.open(HAD.IMG / ("page%d_image1.png" % pg)).convert("L"),
                          strip.convert("L"), info)
    native, strip, info = page_cache[pg]
    bands = note_region._column_bands(strip)
    rec = {"span_id": sid, "page": pg, "note_index": r["note_index"], "box_strip": list(box),
           "band": r["band"], "words": r["words"], "nikud": r["nikud"],
           "stitch_page": r["stitch_page"]}
    try:
        im, rects = HAD._native_crop(native, box, info, bands, PAD)
    except ValueError as e:
        rec.update(crop=None, clip=None, fault="map-error:%s" % e)
        faults[sid] = rec["fault"]
        built.append(rec)
        continue
    fault = HAD.crop_fault(im, rects, native.size, box, strip.size)
    if im is not None and not fault:
        fault = rule_band_fault(im)       # a rule is an inked band; the blank gate cannot see this
    rec["fault"] = fault
    if im is None or fault:
        # A faulted crop is NOT written. A refused crop that exists on disk is a crop a later glob can
        # pick up and show to somebody.
        rec.update(crop=None, clip=None)
        faults[sid] = fault or "no-rect"
        built.append(rec)
        continue
    p = OUTDIR / ("%s_A2_spanbox.png" % sid.replace(":", "_"))
    im.save(str(p))
    prof = G.row_profile(im)
    # A CROP CAN PASS THE BLANK GATE ON A PRINTED RULE. `crop_quality.crop_has_line()` asks whether
    # there is an inked band, and the footnote rule is one: 14 of these 96 crops are a single 7-13px
    # run spanning the full width with no type in them at all, and every one passed the gate. The
    # lane's own derived constant already says what they are -- MIN_BAND_PX is the floor for an ink
    # run to be a line of TYPE -- it had simply never been asked about a crop. No span is dropped
    # here (Chris: exclusions happen afterwards and with a reason); it is recorded so that nobody is
    # asked to sign a word from a rule.
    n_text_bands = len(G.text_bands(im))
    rec["crop"] = {"path": str(p), "size": list(im.size), "text_bands": n_text_bands,
                   "sha16": hashlib.sha256(p.read_bytes()).hexdigest()[:16],
                   "native_rects": [x["box"] for x in rects], "n_rects": len(rects),
                   "rect_edges": [x.get("edge") for x in rects],
                   "band_overshoot_px": [x.get("band_overshoot_px") for x in rects],
                   "ink_px": int(sum(prof)), "ink_rows": int(sum(1 for v in prof if v)),
                   "word_runs": word_runs(im)}

    cand, why = clip_rows(im, len(rects)) if CLIP_AS_SET_RECIPE else (None, NOT_ATTEMPTED)
    rec["clip_abstain"] = why
    rec["clip"] = None
    if cand and (cand["trim_top"] or cand["trim_bot"]):
        y0, y1 = cand["rows"]
        cim = im.crop((0, y0, im.width, y1 + 1))
        cp = OUTDIR / ("%s_A2_bandclip.png" % sid.replace(":", "_"))
        cim.save(str(cp))
        io.open(str(cp.with_suffix(".parent.json")), "w", encoding="utf-8").write(
            json.dumps({"parent": str(p).replace("\\", "/"), "rows": [y0, y1], "span_id": sid,
                        "rule": "remove only ink runs that do not overlap the span's line band and "
                                "are either >= MIN_BAND_PX thick or touch the crop edge; whitespace "
                                "and the span's own band are never removed",
                        "removed_runs": cand["removed_runs"]}, ensure_ascii=False, indent=1))
        # The proof is against the pixels, not the sidecar that names the parent.
        cf = HAD.bandclip_fault(cp)
        blank = (not crop_quality.crop_has_line(cim)) and "blank:no-line" or None
        if cf or blank:
            clip_faults[sid] = cf or blank
            cp.unlink()
            cp.with_suffix(".parent.json").unlink()
        else:
            rec["clip"] = dict(cand, path=str(cp), size=list(cim.size),
                               sha16=hashlib.sha256(cp.read_bytes()).hexdigest()[:16],
                               word_runs=word_runs(cim))
    elif cand:
        rec["clip_abstain"] = "no-trim:no-foreign-line-in-the-pad"
    built.append(rec)

cut = [b for b in built if b.get("crop")]
clipped = [b for b in built if b.get("clip")]
assert cut, "nothing was cut -- do not write a manifest describing an empty population"
assert len(built) == SET_N, "the cut list is %d, not the frozen %d" % (len(built), SET_N)
assert not [b for b in cut if rule_band_fault(Image.open(b["crop"]["path"]))], \
    "a crop with no line of type is on disk after the pre-check"
assert all(not b["fault"] for b in cut), "a faulted crop was kept on disk"
assert all(b["crop"]["ink_px"] > 0 for b in cut), "a kept crop has no ink"
# Every clip on disk passed `bandclip_fault`. Re-asserted over the files rather than trusted from the
# loop, because the guard that matters is the one that holds for whatever is in the directory now.
for b in clipped:
    assert HAD.bandclip_fault(b["clip"]["path"]) is None, "a clip on disk does not prove as a slice"
assert not clip_faults or all(not os.path.exists(OUTDIR / ("%s_A2_bandclip.png" % s.replace(":", "_")))
                              for s in clip_faults), "a refused clip is still on disk"
# THE DIRECTORY MUST BE WHAT THE ARTIFACT SAYS IT IS. A clip that this run abstained from but an
# EARLIER run wrote is still on disk, and a glob is all it takes to put it in front of somebody --
# which is how a clip trimmed against a 6px band would have survived the rule that now refuses it.
# Only band-clips and their sidecars are swept; a parent crop is never touched by this.
_want = {b["clip"]["path"].replace("\\", "/") for b in clipped}
_stale = []
for _p in sorted(OUTDIR.glob("*_A2_bandclip.png")):
    if str(_p).replace("\\", "/") not in _want:
        _sid = _p.name[:-len("_A2_bandclip.png")].replace("_", ":")
        assert _sid.split(":")[0].startswith("p"), "refusing to sweep an unrecognised file: %s" % _p.name
        _stale.append(_p.name)
        _p.unlink()
        if _p.with_suffix(".parent.json").exists():
            _p.with_suffix(".parent.json").unlink()
assert len(list(OUTDIR.glob("*_A2_bandclip.png"))) == len(clipped), \
    "the crop directory holds a different number of clips than the artifact describes"
# The clip must never resolve FEWER words than its parent: that is the amputation `line_band` caused.
regressed = [b["span_id"] for b in clipped if len(b["clip"]["word_runs"]) < len(b["crop"]["word_runs"])]

differ = [b for b in clipped if len(b["clip"]["word_runs"]) != len(b["crop"]["word_runs"])]

# ---- geometry flags: what the signer must be told about the BOX, not about the reading ------------
# None of these drops a span -- Chris's ruling is that exclusions happen afterwards and with a reason.
# They are recorded because a signer cannot see them in the crop, and one of them is a box fault that
# no reading can repair: two spans handed the SAME box produce byte-identical pixels, so asking for two
# different signatures from one image is asking for a guess.
def _bestruns(b):
    return len((b["clip"] or b["crop"])["word_runs"])

seen = {}
for b in cut:
    seen.setdefault((b["page"], tuple(b["box_strip"])), []).append(b["span_id"])
dup = {("p%d:%s" % (k[0], list(k[1]))): v for k, v in seen.items() if len(v) > 1}
short = [{"span_id": b["span_id"], "box_h_native": b["crop"]["native_rects"][0][3] - b["crop"]["native_rects"][0][1],
          "min_band_px": G.MIN_BAND_PX}
         for b in cut if (b["crop"]["native_rects"][0][3] - b["crop"]["native_rects"][0][1]) < G.MIN_BAND_PX]
rule_only = [{"span_id": b["span_id"], "size": b["crop"]["size"],
              "ink_runs_px": [r[1] - r[0] + 1 for r in G.ink_runs(Image.open(b["crop"]["path"]))]}
             for b in cut if b["crop"]["text_bands"] == 0]
# A PROBE THAT MISSES PASSES ON NOTHING. `word_runs` is a COLUMN ink profile, so on a crop holding two
# stacked lines the columns are inked from both and the whole crop collapses to one wide run: p921:n4
# holds four lines resolving 6, 5, 5 and 3 runs and the parent reports ONE. Measured over this set, all
# 18 multi-line crops resolve fewer runs than their own busiest line, and 16 of them then EQUAL the
# claimed word count -- a pass the check did not earn. So this tally is reported only over crops where
# it means something, with the blind population named rather than scored as agreement.
def _lines_of_type(b):
    im = Image.open((b["clip"] or b["crop"])["path"])
    return sum(1 for y0, y1 in G.ink_runs(im) if (y1 - y0 + 1) >= G.MIN_BAND_PX)


blind = [{"span_id": b["span_id"], "words": b["words"], "lines_of_type": _lines_of_type(b)}
         for b in cut if _lines_of_type(b) > 1]

# THE FLOOR'S EMPTY BAND, RE-MEASURED ON THE POPULATION IT IS APPLIED TO. MIN_BAND_PX = 20 was derived
# from a gap between two dense populations of ink runs in the SIGNED corpus -- 27 runs of 1-14px and 18
# of 30-38px, a 16px gap with 20 in it. Those were single-line boxes. The OVER-FULL badge applies the
# same floor to MULTI-LINE boxes, which is a different population, and Lane A2 warned (2026-10-04, their
# 26e68f2) that a narrow empty band in a sparse trough can be a SAMPLING HOLE rather than a real gap:
# one re-cut band moved their inset_thr from 41 to 80 and cost them a declared run. A threshold taken
# from a gap is only derived while the gap is still there, so it is re-measured here rather than trusted
# from the comment that derived it. The assertion is about the GAP, not about the count: if the two
# populations ever touch at the floor, these badges are a coin flip on some crop and this run must say so
# instead of shipping a number.
_t = [b - a + 1 for x in blind
      for a, b in G.ink_runs(Image.open((lambda r: (r["clip"] or r["crop"])["path"])(
          [c for c in cut if c["span_id"] == x["span_id"]][0])))]
_below = [t for t in _t if t < G.MIN_BAND_PX]
_above = [t for t in _t if t >= G.MIN_BAND_PX]
floor_margin = {"floor": G.MIN_BAND_PX, "population": "the %d crops the OVER-FULL badge is applied to" % len(blind),
                "runs_below": len(_below), "runs_at_or_above": len(_above),
                "thickest_below": max(_below) if _below else None,
                "thinnest_above": min(_above) if _above else None,
                "empty_band_px": (min(_above) - max(_below) - 1) if (_below and _above) else None,
                "derived_from": "a 16px gap in the SIGNED corpus (27 runs of 1-14px, 18 of 30-38px); "
                                "re-measured here on the multi-line population because a gap is only a "
                                "derivation while it is still empty (Lane A2's sampling-hole caution)"}
assert not (_below and _above) or min(_above) > max(_below) + 1, \
    ("the two ink-run populations TOUCH at the floor on the over-full crops (%dpx below, %dpx above): "
     "MIN_BAND_PX is no longer taken from an empty band here and the OVER-FULL count is a coin flip on "
     "some crop" % (max(_below), min(_above)))
# THE WIDTH BAR. Lane A2 MEASURED a 4px empty band that turned out to be a sampling hole (their
# 26e68f2: one re-cut band moved inset_thr from 41 to 80 and cost them a declared run), so 4 is
# known-insufficient and twice it is the floor for calling a gap a gap. 9 is also well inside both
# gaps actually measured -- 16px in the signed corpus, 15px here -- so it is a bar neither
# population is pinned to.
assert floor_margin["empty_band_px"] is None or floor_margin["empty_band_px"] >= 9, \
    ("the empty band around the floor is only %dpx wide on this population -- Lane A2 measured a 4px "
     "empty band that turned out to be a sampling hole, so this is too narrow to call a gap"
     % floor_margin["empty_band_px"])
_meas = [b for b in cut if _lines_of_type(b) <= 1]
assert len(_meas) + len(blind) == len(cut), "every crop is either measurable or named as blind"
over = [{"span_id": b["span_id"], "words": b["words"], "runs": _bestruns(b)} for b in _meas
        if _bestruns(b) > b["words"]]
under = [{"span_id": b["span_id"], "words": b["words"], "runs": _bestruns(b)} for b in _meas
         if _bestruns(b) < b["words"]]
GEOM_FLAGS = {
    "duplicate_box": dup,
    "duplicate_box_note": "two spans with one box cut byte-identical crops; at least one box is wrong "
                          "and a signature from these pixels cannot distinguish them. REDRAW, not a "
                          "reading question.",
    "no_line_of_type": rule_only,
    "no_line_of_type_note": "EMPTY BY CONSTRUCTION since 2026-10-04: rule_band_fault() now REFUSES "
                            "such a crop at cut time, so it is in `faults`, not here. Kept as a "
                            "flag so the artifact shape does not change. "
                            "The crop holds no ink run thick enough to be a line of type, so there is "
                            "nothing in it to read. Measured by the lane's own MIN_BAND_PX. These are "
                            "boxes on the footnote RULE, and every one of them passed crop_has_line() "
                            "-- a printed rule satisfies `there is an inked band`. The gate is Lane "
                            "A's crop_quality.py: REQUEST, do not edit.",
    "box_shorter_than_a_line": short,
    "box_shorter_note": "the unpadded box is thinner than MIN_BAND_PX, the lane's derived floor for an "
                        "ink run to be a line of type at all -- so the box cannot hold a word of this "
                        "fount whatever the crop looks like",
    "runs_exceed_words": over, "runs_below_words": under,
    "runs_not_measurable": blind,
    "runs_not_measurable_note": "the crop shown for these holds more than one line of type, and a "
                                "COLUMN ink profile cannot be read across stacked lines -- it merges "
                                "them and under-counts. These are NOT agreements and NOT exceedances; "
                                "the check does not apply to them. Every one is also a box the clip "
                                "abstained on, so they are the same redraw question.",
    "runs_note": "resolved column runs against the extractor's word count, best recipe per span. More "
                 "runs than words means the box holds material beyond the signature (a redraw question "
                 "by the box rule); fewer means ink still bridges, or the extraction claims words the "
                 "pixels do not show. Both are for the signer to see, neither is scored here.",
}
GIT_END = git_state(_HERE)
art = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
       "git_start": GIT_START, "git_end": GIT_END,
       "provisional": provisional(GIT_START, GIT_END),
       "set_sha16": SET, "n": len(built), "cut": len(cut), "refused": len(built) - len(cut),
       "page_numbering": "FILE pages (printed = file - 88)",
       "recipe": {"aperture": "A2_spanbox", "pad_native_px": PAD, "a1_reachable": False,
                  "source": "hebrew_aperture_diag._native_crop + crop_fault, as crops() applies them",
                  "clip_rule": "remove only ink runs that do not overlap the span's line band and are "
                               "either >= %d px thick or touch the crop edge" % G.MIN_BAND_PX,
                  "clip_abstains_when": "the BOX covers more than one line of type (p677:n13), the band "
                                        "line_band() returns is itself thinner than a line of type, or "
                                        "the trim would keep less than one line of type (p558:n3) -- "
                                        "all three found by eye on 2026-10-04",
                  "rule_band_precheck": "a crop with no ink run >= %d px is refused and not written "
                                        "(rule_band_fault); crop_has_line() passes on a printed "
                                        "rule and cannot see this" % G.MIN_BAND_PX,
                  "clip_validated_against": "p912:n2 hand-built clip (rows 14-72, 2 word runs); this "
                                            "rule keeps 14-78 and resolves the same 2 runs",
                  "word_run_convention": {"gap_min": GAP_MIN, "run_min": RUN_MIN, "ink_thr": INK_THR}},
       "crop_dir": str(OUTDIR), "faults": faults, "clip_faults": clip_faults,
       "floor_margin": floor_margin,
       "stale_clips_swept": _stale,
       "clip": {"applied_as_set_recipe": CLIP_AS_SET_RECIPE,
                "written": len(clipped), "no_trim": sum(1 for b in cut if b["clip_abstain"].startswith("no-trim")),
                "not_attempted": sum(1 for b in cut if b["clip_abstain"] == NOT_ATTEMPTED),
                # `abstained` is a SET of reason strings and two spans can share one, so it under-
                # counts: 18 abstains collapsed to 16 strings and written + no_trim + abstained did not
                # add up to the set. The ids are the count; the strings are the vocabulary.
                "abstained_ids": {b["span_id"]: b["clip_abstain"] for b in cut if b["clip_abstain"]
                                  and not b["clip_abstain"].startswith("no-trim")
                                  and b["clip_abstain"] != NOT_ATTEMPTED},
                "abstained": sorted({b["clip_abstain"] for b in cut if b["clip_abstain"]
                                     and not b["clip_abstain"].startswith("no-trim")
                                     and b["clip_abstain"] != NOT_ATTEMPTED}),
                "word_runs_differ": [{"span_id": b["span_id"], "base": b["crop"]["word_runs"],
                                      "clip": b["clip"]["word_runs"]} for b in differ],
                "word_runs_regressed": regressed,
                "trim_px": sorted(b["clip"]["trim_top"] + b["clip"]["trim_bot"] for b in clipped)},
       "geometry_flags": GEOM_FLAGS,
       "strata_cut": {"words": dict(Counter(min(b["words"], 4) for b in cut)),
                      "nikud": dict(Counter(b["nikud"] for b in cut)),
                      "stitch_page": dict(Counter(b["stitch_page"] for b in cut))},
       "rows": built}
json.dump(art, io.open(str(OUT), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print("set %s  cut %d/%d  refused %d  dir %s" % (SET, len(cut), len(built), len(built) - len(cut),
                                                 OUTDIR.name))
for sid, f in sorted(faults.items()):
    print("   REFUSED crop %-10s %s" % (sid, f))
for sid, f in sorted(clip_faults.items()):
    print("   REFUSED clip %-10s %s" % (sid, f))
print("ink: min %d px on %d rows   sizes %dx%d..%dx%d"
      % (min(b["crop"]["ink_px"] for b in cut), min(b["crop"]["ink_rows"] for b in cut),
         min(b["crop"]["size"][0] for b in cut), min(b["crop"]["size"][1] for b in cut),
         max(b["crop"]["size"][0] for b in cut), max(b["crop"]["size"][1] for b in cut)))
assert (len(clipped) + art["clip"]["no_trim"] + len(art["clip"]["abstained_ids"])
        + art["clip"]["not_attempted"]) == len(cut), \
    "written + no-trim + abstained + not-attempted does not account for every crop that was cut"
assert CLIP_AS_SET_RECIPE or (not clipped and not list(OUTDIR.glob("*_A2_bandclip.png"))), \
    "the clip is withdrawn as a set recipe but a clip was written or is on disk"
print("clips written %d   no trim needed %d   abstains %d (%d distinct reasons)   not attempted %d"
      % (len(clipped), art["clip"]["no_trim"], len(art["clip"]["abstained_ids"]),
         len(art["clip"]["abstained"]), art["clip"]["not_attempted"]))
if not CLIP_AS_SET_RECIPE:
    print("BAND-CLIP WITHDRAWN AS A SET RECIPE: all %d crops are PAD=%d only, the same recipe as the 19 "
          "already signed." % (len(cut), PAD))
for _s, _r in sorted(art["clip"]["abstained_ids"].items()):
    print("   ABSTAIN %-10s %s" % (_s, _r))
print("floor %dpx sits in a %spx empty band on the %d over-full crops (%d runs below, thickest %s; %d at or above, thinnest %s)"
      % (floor_margin["floor"], floor_margin["empty_band_px"], len(blind),
         floor_margin["runs_below"], floor_margin["thickest_below"],
         floor_margin["runs_at_or_above"], floor_margin["thinnest_above"]))
print("word runs DIFFER on %d span(s): %s"
      % (len(differ), [(d["span_id"], len(d["base"]), len(d["clip"])) for d in art["clip"]["word_runs_differ"]]))
print("word runs REGRESSED (clip resolves fewer): %s" % (regressed or "none"))
print("NO LINE OF TYPE (box on a rule): %d  %s"
      % (len(rule_only), [x["span_id"] for x in rule_only]))
print("geometry flags: duplicate-box groups %d %s   box shorter than a line %s"
      % (len(dup), list(dup.values()) or "", [x["span_id"] for x in short] or "none"))
print("resolved runs vs claimed words (single-line crops only, n=%d of %d): more %d  fewer %d  equal %d"
      % (len(_meas), len(cut), len(over), len(under), len(_meas) - len(over) - len(under)))
print("   NOT MEASURABLE (crop holds >1 line of type; the column profile merges them): %d  %s"
      % (len(blind), [x["span_id"] for x in blind]))
print(banner(GIT_START, GIT_END))
print("wrote", OUT.name)
