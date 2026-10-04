# -*- coding: utf-8 -*-
"""Cut the 96 truth-set crops: A2 span box at PAD=12, and the band-clip, guarded and hashed.

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

SET = "4e73b10d46a41f4a"
TRUTH = HAD.DATA / ("truth_set96_%s.json" % SET)
OUTDIR = HAD.DATA / ("truthset96_crops_%s" % SET)
OUT = HAD.DATA / ("truthset96_cut_%s.json" % SET)
PAD = HAD.PAD

# The column-run convention, taken from the pad probe unchanged so the two runs are comparable: a word
# run is a maximal inked column range separated by >= GAP_MIN empty columns and at least RUN_MIN wide.
GAP_MIN, RUN_MIN, INK_THR = 10, 8, 128

GIT_START = git_state(_HERE)

tset = json.load(io.open(str(TRUTH), encoding="utf-8"))
assert tset.get("provisional") is False, "the truth set is PROVISIONAL -- do not cut from it"
assert tset["set_sha16"] == SET and tset["n"] == 96, "this is not the frozen 96"
rows = tset["rows"]
SEALED = set(HAD.SEALED_TRUTH) if isinstance(HAD.SEALED_TRUTH, dict) else set()
assert not (SEALED & {r["span_id"] for r in rows}), "a sealed span is in the cut list"
# The pad is applied in NATIVE px after the strip->native map, exactly as `crops()` does. Read from the
# harness rather than retyped, so a change there cannot leave this file describing different crops.
assert PAD == 12, "the A2 recipe's pad moved (%r); the probe and this cut would disagree" % PAD


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
    band = G.line_band(im)
    if not band:
        return None, "abstain:no-line-band"
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
    rec["crop"] = {"path": str(p), "size": list(im.size),
                   "sha16": hashlib.sha256(p.read_bytes()).hexdigest()[:16],
                   "native_rects": [x["box"] for x in rects], "n_rects": len(rects),
                   "rect_edges": [x.get("edge") for x in rects],
                   "band_overshoot_px": [x.get("band_overshoot_px") for x in rects],
                   "ink_px": int(sum(prof)), "ink_rows": int(sum(1 for v in prof if v)),
                   "word_runs": word_runs(im)}

    cand, why = clip_rows(im, len(rects))
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
assert len(built) == 96, "the cut list is %d, not the frozen 96" % len(built)
assert all(not b["fault"] for b in cut), "a faulted crop was kept on disk"
assert all(b["crop"]["ink_px"] > 0 for b in cut), "a kept crop has no ink"
# Every clip on disk passed `bandclip_fault`. Re-asserted over the files rather than trusted from the
# loop, because the guard that matters is the one that holds for whatever is in the directory now.
for b in clipped:
    assert HAD.bandclip_fault(b["clip"]["path"]) is None, "a clip on disk does not prove as a slice"
assert not clip_faults or all(not os.path.exists(OUTDIR / ("%s_A2_bandclip.png" % s.replace(":", "_")))
                              for s in clip_faults), "a refused clip is still on disk"
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
over = [{"span_id": b["span_id"], "words": b["words"], "runs": _bestruns(b)} for b in cut
        if _bestruns(b) > b["words"]]
under = [{"span_id": b["span_id"], "words": b["words"], "runs": _bestruns(b)} for b in cut
         if _bestruns(b) < b["words"]]
GEOM_FLAGS = {
    "duplicate_box": dup,
    "duplicate_box_note": "two spans with one box cut byte-identical crops; at least one box is wrong "
                          "and a signature from these pixels cannot distinguish them. REDRAW, not a "
                          "reading question.",
    "box_shorter_than_a_line": short,
    "box_shorter_note": "the unpadded box is thinner than MIN_BAND_PX, the lane's derived floor for an "
                        "ink run to be a line of type at all -- so the box cannot hold a word of this "
                        "fount whatever the crop looks like",
    "runs_exceed_words": over, "runs_below_words": under,
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
                  "clip_validated_against": "p912:n2 hand-built clip (rows 14-72, 2 word runs); this "
                                            "rule keeps 14-78 and resolves the same 2 runs",
                  "word_run_convention": {"gap_min": GAP_MIN, "run_min": RUN_MIN, "ink_thr": INK_THR}},
       "crop_dir": str(OUTDIR), "faults": faults, "clip_faults": clip_faults,
       "clip": {"written": len(clipped), "no_trim": sum(1 for b in cut if b["clip_abstain"].startswith("no-trim")),
                "abstained": sorted({b["clip_abstain"] for b in cut if b["clip_abstain"]
                                     and not b["clip_abstain"].startswith("no-trim")}),
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
print("clips written %d   no trim needed %d   abstains %s"
      % (len(clipped), art["clip"]["no_trim"], art["clip"]["abstained"] or "none"))
print("word runs DIFFER on %d span(s): %s"
      % (len(differ), [(d["span_id"], len(d["base"]), len(d["clip"])) for d in art["clip"]["word_runs_differ"]]))
print("word runs REGRESSED (clip resolves fewer): %s" % (regressed or "none"))
print("geometry flags: duplicate-box groups %d %s   box shorter than a line %s"
      % (len(dup), list(dup.values()) or "", [x["span_id"] for x in short] or "none"))
print("resolved runs vs claimed words: more %d   fewer %d   equal %d"
      % (len(over), len(under), len(cut) - len(over) - len(under)))
print(banner(GIT_START, GIT_END))
print("wrote", OUT.name)
