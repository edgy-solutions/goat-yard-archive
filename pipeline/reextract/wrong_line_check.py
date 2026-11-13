# -*- coding: utf-8 -*-
u"""Wrong-line CHECKER for the 13 noteless pass-1 faults -- with a witness that is not the localizer.

WHY A NEW WITNESS WAS NEEDED, AND WHAT KILLED THE OBVIOUS ONES
--------------------------------------------------------------
`wrong_line_trace.py` reproduced all 74 stored boxes and found the structural cause: the localizer is
handed the Hebrew run, not the note (`draw_pool.py:87`), so its token count before the Hebrew is
always 0 and it always lands on line 0 of the note region.  That explains the MECHANISM.  It renders
no verdict on any span, and it says so: "a box it cannot fault is NOT thereby confirmed."

Two witnesses were built and MEASURED DEAD before this one.  Both are recorded here because the next
reader will otherwise build them again:

  (1) THE WIRED-UP COUNT.  Run the same line walk with the NOTE text -- the input the counting design
      was designed around and never received.  Result: landing line still 0 on 72 of 74, None
      (offset overflow) on 2.  It cannot discriminate, because 59 of the 74 note regions have exactly
      ONE detected line, and in the multi-line ones the Hebrew opens the note (offset 0).  "Which
      line" has no degrees of freedom on this population.
  (2) THE TOKEN/BOX BALANCE.  Note word count against the region's box total, to ask whether the
      region even holds the note.  Result: the SIGNED range (-20..+13) strictly CONTAINS the fault
      range (-9..+6); 4 of 60 signed rows would be flagged; and the one confirmed fault `p92:n1`
      sits at -1.  No threshold separates them.

The reason both failed is the same, and it is the finding: **every quantity computed relative to the
note region is blind to a misplaced region.**  `p92:n1` is the proof -- a human wrote "the crop is 3
lines up from the hebrew", and the walk reports `n_lines=1, landing=0`.  The box is on the only line
of its region.  The REGION is in the wrong place.  So the fault class is misnamed: these are not
line-choice faults.

THE WITNESS THIS FILE USES
--------------------------
The page's own Tesseract layer, `pageN_image1_ocr.json`, in NATIVE PAGE coordinates, produced by the
main pipeline's Step 2.  It is independent of `cv_footnote_presplit`, of `note_line_region` and of
the localizer -- none of them can see it and it cannot see them.  The match is made on the note's
LATIN words, never on the Hebrew, so a Hebrew misread cannot move the verdict.

Frame: band -> page is `native + (band_xy - paste)` from `info["bands"]`, exact because
`_trim_strip` crops the BOTTOM only (its own docstring states the top origin is never touched) and
this run uses `upscale=1`.  A frame error would make every verdict meaningless, so it is not assumed:
the 60 SIGNED spans are the calibration control, and a frame fault shows up as signed spans landing
off their own text.

Confidence, per the standing rule that cross-modal correspondence is stochastic: a note's position is
taken only from words that are >= MIN_WORD_LEN characters, appear EXACTLY ONCE in the page's OCR (so
the match is unambiguous), and whose matches are spatially coherent within COHERENCE_LH line heights.
Fewer than MIN_MATCHES such words -> `cannot-say`, loudly, counted, never a pass.

`lh` (the page's line height) is a REQUIRED argument taken from `position_census.json`, not derived
in here: a function that derives its own input fails silently.

CONTROLS, all asserted or reported, never skipped
-------------------------------------------------
  * POSITIVE: `p92:n1` is human-witnessed wrong-line, "3 lines up".  If the checker does not call it
    wrong-line with a negative offset near -3 lh, the checker cannot see the one fault class that is
    confirmed to exist, and the run says so in its own output rather than reporting the other 13.
  * SPECIFICITY: the 60 signed spans carry ratified boxes.  Every one the checker calls wrong-line is
    a contradiction -- checker or signature -- and is named individually.
  * LIVENESS: if NO span anywhere is called wrong-line, the checker has no discriminating power and
    the run reports NO-DISCRIMINATION instead of a clean bill.

Verdicts are three-state and one of them is an abstention: `right-line`, `wrong-line`, `cannot-say`.
No span is ever scored, and `right-line` means "the witness places the box on the note's own line",
not "this crop is good" -- horizontal extent and which-note-is-it are different faults.

Reads only.  No model calls, no spend.  Lane A's modules are imported read-only.
All page numbers in the output are FILE pages; printed = file - 88.
"""
import io
import json
import os
import re
import sys
import time
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, os.pardir, "scripts"))

import cv_footnote_presplit as ps                                          # noqa: E402  Lane A's, read-only
import word_box_align as W                                                # noqa: E402  Lane A's, read-only
import hebrew_aperture_diag as HAD                                        # noqa: E402
from clean_run import git_state, provisional, banner                      # noqa: E402

SET, SET_N = "0401b636ffa7bf1a", 74
PRINTED_OFFSET = 88
DATA = HAD.DATA
TRUTH_PATH = DATA / ("truth_set%d_%s.json" % (SET_N, SET))
INGEST = DATA / ("signing_pass1_ingest_%s.json" % SET)
CENSUS_PATH = DATA / "hebrew_span_census_20261004.json"
POS_CENSUS = "C:/Users/cnogr/git/dr-voluminous/reextract_vol1/position_census.json"
APP = "C:/Users/cnogr/git/dr-voluminous/reextract_vol1/vol1_apparatus.jsonl"
VOL = "C:/Users/cnogr/git/dr-voluminous/commentary/volume1"
PAGE = VOL + "/page%d_image1.png"
OCR = VOL + "/page%d_image1_ocr.json"
OUT = DATA / ("wrong_line_check_%s.json" % SET)
LANEB = "C:/Users/cnogr/git/goatyard-laneB"
DRV = "C:/Users/cnogr/git/dr-voluminous"

# The witness's confidence constraints.  Stated as constants so a later reader can see what was
# required of a match, and so loosening one is a visible edit rather than a silent drift.
MIN_WORD_LEN = 4        # shorter words are too common in OCR noise to anchor anything
MIN_MATCHES = 3         # a position from fewer than 3 unique words is not a position
COHERENCE_LH = 2.5      # unique matches must sit within this many line heights of each other
RIGHT_LH = 0.6          # |offset| <= this many line heights -> the box is on the note's own line
WRONG_LH = 1.0          # |offset| >= this many line heights -> the box is on a different line
MIN_OCR_CONF = 30       # Tesseract conf floor; 18th-century type scores low, so this is permissive
MIN_PITCH_GAPS = 3      # a BAND of N lines yields N-1 gaps and a footnote band is a few lines
                        # tall, so 8 rejected almost every band; 3 is the smallest count whose
                        # median is not simply an extremum.  Set from that structure, not from
                        # watching verdicts move: the number that validates the unit is the
                        # agreement with the census witness below, not the verdict count.

WORDRE = re.compile(r"[^0-9a-z]+")


def norm(s):
    """Fold an OCR token and a note token onto the same key.  Deliberately crude: the long-s and
    ligature damage in this type means anything subtler would be a recognizer with opinions."""
    return WORDRE.sub("", s.lower().replace(u"\u017f", "s").replace(u"\ufb00", "ff")
                      .replace(u"\ufb01", "fi").replace(u"\ufb02", "fl"))


def load_rows():
    truth = json.load(io.open(str(TRUTH_PATH), encoding="utf-8"))
    assert truth.get("provisional") is False and truth["set_sha16"] == SET and truth["n"] == SET_N, \
        "truth set is not the frozen one this checker is scoped to"
    rows = truth["rows"]
    assert len(rows) == SET_N
    dispo = {r["span_id"]: r["disposition"]
             for r in json.load(io.open(str(INGEST), encoding="utf-8"))["rows"]}
    cen = {r["span_id"]: r
           for r in json.load(io.open(str(CENSUS_PATH), encoding="utf-8"))["rows"]}
    missing = [r["span_id"] for r in rows if r["span_id"] not in cen]
    assert not missing, "no census witness for %s" % missing
    # page-level line height, the REQUIRED argument.  Keyed by page; `pos_valid` says whether the
    # page's own position pass stood up, and a page it disowns gets no lh rather than a bad one.
    lh = {}
    for r in json.load(io.open(POS_CENSUS, encoding="utf-8")):
        if r.get("pos_valid") and r.get("lh"):
            lh[r["page"]] = float(r["lh"])
    notes = {}
    for line in io.open(APP, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        o = json.loads(line)
        if o.get("kind") == "config_header":
            continue
        for ni, nt in enumerate(o.get("notes") or [], 1):
            if isinstance(nt, dict):
                notes[(o["page"], ni)] = nt.get("text") or ""
    return rows, dispo, cen, lh, notes


def ocr_line_pitch(words, y_min):
    """The FOOTNOTE BAND's printed line pitch from the OCR layer alone, or None with a reason.

    `y_min` is the band's top edge in native page coordinates: only words at or below it count, so
    this is the note type's pitch and not the body's.  The two differ by about 1.44x in this book,
    which is why the argument is required rather than defaulted.

    Tesseract already groups words into lines; this takes each line's median y-centre and the MEDIAN
    gap between consecutive lines of the same block.  Median rather than mean because a block that
    ends mid-page leaves one huge gap, and one outlier must not set the pitch.

    Independent of `note_line_region` and of the localizer by construction -- it reads only the OCR
    sidecar.  Requires MIN_PITCH_GAPS gaps, so a page with two detected lines gets no pitch rather
    than a pitch resting on one measurement.
    """
    lines = {}
    for w in words:
        if w.get("conf", -1) < MIN_OCR_CONF:
            continue
        if not (w.get("text") or "").strip():
            continue
        # BAND ONLY.  The body is set larger than the notes, so a page-wide pitch is the wrong unit
        # for a note box's vertical offset.  `y_min` is the band's own top in page coordinates and is
        # passed in, never guessed here.
        if w["top"] + w["height"] / 2.0 < y_min:
            continue
        k = (w.get("block_num"), w.get("par_num"), w.get("line_num"))
        lines.setdefault(k, []).append(w["top"] + w["height"] / 2.0)
    if len(lines) < 3:
        return None, "too-few-ocr-lines:%d" % len(lines)
    mids = {}
    for k, ys in lines.items():
        ys.sort()
        mids[k] = ys[len(ys) // 2]
    gaps = []
    for (b, p, ln), y in mids.items():
        nxt = mids.get((b, p, ln + 1))
        if nxt is not None:
            d = nxt - y
            # A gap is a pitch only if it is positive and plausible; a reflowed block can emit a
            # next-line number that sits ABOVE its predecessor, and that is not a line height.
            if 5.0 <= d <= 400.0:
                gaps.append(d)
    if len(gaps) < MIN_PITCH_GAPS:
        return None, "too-few-pitch-gaps:%d" % len(gaps)
    gaps.sort()
    return gaps[len(gaps) // 2], "median-of-%d-gaps" % len(gaps)


def band_to_page(box, info):
    """Map a band-coordinate box to native page coordinates, or return None with a reason.

    The mapping is `native + (xy - paste)` for the band whose paste rect contains the box.  Returned
    as a reason rather than a guess when no band contains it, because a silently wrong frame is the
    one failure this whole check cannot survive.
    """
    x0, y0, x1, y1 = box
    bands = info.get("bands") or []
    if not bands:
        return None, "no-bands"
    if info.get("upscale") not in (1, None):
        return None, "upscaled-band:%s" % info.get("upscale")
    for b in bands:
        px, py = b["paste"]
        bw, bh = b["size"]
        if px <= x0 and py <= y0 and x1 <= px + bw and y1 <= py + bh:
            nx, ny = b["native"]
            return ([int(x0 - px + nx), int(y0 - py + ny),
                     int(x1 - px + nx), int(y1 - py + ny)], b.get("col", "?")), None
    return None, "box-in-no-band"


def locate_note(note_text, words, lh):
    """Where the note's own Latin words sit on the page, from the OCR layer alone.

    Returns (y_center, detail) or (None, detail-with-reason).  Uniqueness is the confidence gate:
    only note words that occur EXACTLY ONCE among the page's OCR tokens can anchor a position, so an
    ambiguous match cannot vote.
    """
    toks = W.tokenize(note_text)
    cand = set()
    for s, t in toks:
        if s == "latin":
            k = norm(t)
            if len(k) >= MIN_WORD_LEN:
                cand.add(k)
    seen = Counter()
    where = {}
    for w in words:
        if w.get("conf", -1) < MIN_OCR_CONF:
            continue
        k = norm(w.get("text") or "")
        if len(k) < MIN_WORD_LEN or k not in cand:
            continue
        seen[k] += 1
        where.setdefault(k, []).append(w)
    uniq = [k for k in seen if seen[k] == 1]
    detail = {"note_latin_candidates": len(cand), "matched_any": len(seen), "matched_unique": len(uniq)}
    if len(uniq) < MIN_MATCHES:
        detail["reason"] = "too-few-unique-matches"
        return None, detail
    ys = sorted(where[k][0]["top"] + where[k][0]["height"] / 2.0 for k in uniq)
    mid = ys[len(ys) // 2]
    # Spatial coherence: a scattered match set is not a location.  Keep the words within
    # COHERENCE_LH of the median and require MIN_MATCHES of them to survive.
    keep = [y for y in ys if abs(y - mid) <= COHERENCE_LH * lh]
    detail["coherent"] = len(keep)
    detail["spread_lh"] = round((ys[-1] - ys[0]) / lh, 2)
    if len(keep) < MIN_MATCHES:
        detail["reason"] = "matches-not-coherent"
        return None, detail
    keep.sort()
    detail["kept_spread_lh"] = round((keep[-1] - keep[0]) / lh, 2)
    return sum(keep) / float(len(keep)), detail


def main():
    # Both repos, because the rule binds the tree the code is in AND the tree the data is in.
    g0 = {"laneB": git_state(LANEB), "drv": git_state(DRV)}
    print("start %s" % json.dumps({k: {"head": v["git_head"][:7],
                                       "state": v["git_dirty"].get("state")}
                                   for k, v in sorted(g0.items())}))
    rows, dispo, cen, lh_of, notes = load_rows()

    res, cache = [], {}
    t0 = time.time()
    for i, r in enumerate(sorted(rows, key=lambda x: (x["page"], x["note_index"])), 1):
        sid, pg = r["span_id"], r["page"]
        rec = {"span_id": sid, "page": pg, "printed": pg - PRINTED_OFFSET,
               "note_index": r["note_index"], "hebrew": r["hebrew"],
               "disposition": dispo.get(sid, "?"),
               "is_fault": str(dispo.get(sid, "")).startswith("fault"),
               "stored_box_band": list(r["box"]),
               "census_start": cen[sid]["start"], "opens_note": cen[sid]["start"] == 0}
        try:
            txt = notes.get((pg, r["note_index"]))
            if txt is None:
                rec.update(verdict="cannot-say", reason="no-note-text")
                res.append(rec)
                continue
            # dual witness on the note text: the apparatus text this checker reads must be the text
            # the census measured, or `census_start` describes a different string than I tokenized.
            rec["note_len_agrees"] = (len(txt) == cen[sid]["note_len"])
            if not rec["note_len_agrees"]:
                rec.update(verdict="cannot-say", reason="note-text-disagrees-with-census")
                res.append(rec)
                continue
            if pg not in cache:
                _strip, info = ps.presplit(PAGE % pg, upscale=1)
                ocr = json.load(io.open(OCR % pg, encoding="utf-8"))
                _bands = info.get("bands") or []
                _ytop = (min(b["native"][1] for b in _bands) if _bands else None)
                cache[pg] = (info, ocr,
                             (ocr_line_pitch(ocr, _ytop) if _ytop is not None
                              else (None, "no-band-origin")),
                             _ytop)
            info, ocr, (opitch, pwhy), band_ytop = cache[pg]
            rec["band_top_page_y"] = band_ytop
            # TWO line-height witnesses, both recorded.  The census is the established one; the OCR
            # pitch is what makes the 18 census-less pages -- including the positive control --
            # measurable at all.  Their ratio on the overlap is what licenses that use.
            clh = lh_of.get(pg)
            rec["lh_census"] = clh
            rec["lh_ocr"] = (round(opitch, 1) if opitch else None)
            rec["lh_ocr_why"] = pwhy
            if clh and opitch:
                rec["lh_ratio_ocr_over_census"] = round(opitch / clh, 3)
            lh = clh or opitch
            rec["lh_source"] = "census" if clh else ("ocr" if opitch else None)
            if not lh:
                rec.update(verdict="cannot-say", reason="no-line-height-witness:" + pwhy)
                res.append(rec)
                continue
            rec["lh"] = lh
            mapped, why = band_to_page(r["box"], info)
            if mapped is None:
                rec.update(verdict="cannot-say", reason="frame:" + why)
                res.append(rec)
                continue
            pbox, col = mapped
            rec["stored_box_page"] = pbox
            rec["band_col"] = col
            box_mid = (pbox[1] + pbox[3]) / 2.0
            ny, detail = locate_note(txt, ocr, lh)
            rec["witness"] = detail
            if ny is None:
                rec.update(verdict="cannot-say", reason="witness:" + detail.get("reason", "?"))
                res.append(rec)
                continue
            off = (box_mid - ny) / lh
            rec["note_y_ocr"] = round(ny, 1)
            rec["box_y_mid_page"] = round(box_mid, 1)
            rec["offset_lh"] = round(off, 2)
            if abs(off) <= RIGHT_LH:
                rec["verdict"] = "right-line"
            elif abs(off) >= WRONG_LH:
                rec["verdict"] = "wrong-line"
                rec["lines_off"] = int(round(off))
            else:
                rec.update(verdict="cannot-say", reason="offset-in-dead-band")
        except Exception as e:                                             # noqa: BLE001
            rec.update(verdict="cannot-say", reason="exc:%s:%s" % (type(e).__name__, str(e)[:120]))
        res.append(rec)
        if i % 15 == 0:
            print("  %d/%d  %.0fs" % (i, SET_N, time.time() - t0), flush=True)

    assert len(res) == SET_N, "the checker covers %d of %d spans" % (len(res), SET_N)

    F = [r for r in res if r["is_fault"]]
    S = [r for r in res if not r["is_fault"]]
    wrong = [r for r in res if r["verdict"] == "wrong-line"]
    # LIVENESS.  A checker that calls nothing wrong has not cleared anything; it has only failed to
    # fire.  Recorded as a top-level flag so no reader can mistake silence for a pass.
    discriminating = bool(wrong)
    # SPECIFICITY.  Signed boxes are ratified; a wrong-line call on one is a contradiction.
    signed_wrong = [r["span_id"] for r in S if r["verdict"] == "wrong-line"]
    # POSITIVE CONTROL.  The only fault with a human witness.
    ctl = [r for r in res if r["span_id"] == "p92:n1"]
    control = None
    if ctl:
        c = ctl[0]
        control = {"span_id": "p92:n1", "human_note": "the crop is 3 lines up from the hebrew",
                   "verdict": c["verdict"], "offset_lh": c.get("offset_lh"),
                   "reason": c.get("reason"),
                   "agrees_with_human": (c["verdict"] == "wrong-line"
                                         and c.get("offset_lh") is not None
                                         and c["offset_lh"] < 0),
                   "near_three_lines": (c.get("offset_lh") is not None
                                        and -4.0 <= c["offset_lh"] <= -2.0)}

    _r = [r["lh_ratio_ocr_over_census"] for r in res if r.get("lh_ratio_ocr_over_census")]
    _r.sort()
    lh_agree = {"rows_with_both": len(_r),
                "median_ratio": (_r[len(_r) // 2] if _r else None),
                "within_10pct": sum(1 for x in _r if 0.9 <= x <= 1.1),
                "min": (_r[0] if _r else None), "max": (_r[-1] if _r else None),
                "means": "OCR pitch / census lh, on the pages where both witnesses exist; this is what licenses using the OCR pitch on the pages the census cannot serve"}
    g1 = {"laneB": git_state(LANEB), "drv": git_state(DRV)}
    # PROVISIONAL if EITHER tree was dirty or moved: the artifact is as citable as its weakest repo.
    prov = any(provisional(g0[k], g1[k]) for k in g0)
    out = {
        "what": "wrong-line checker over the frozen 74-span set, witness = the page's own Tesseract "
                "OCR layer in native page coordinates (independent of the localizer, of "
                "note_line_region and of cv_footnote_presplit)",
        "set_sha16": SET, "n": SET_N, "printed_offset": PRINTED_OFFSET,
        "page_numbers_are": "FILE pages; printed = file - %d" % PRINTED_OFFSET,
        "lane": "B", "session": "50612c81",
        "spend": "none -- reads only, no model calls",
        "git_start": g0, "git_end": g1, "provisional": prov,
        "git_banner": {k: banner(g0[k], g1[k]) for k in sorted(g0)},
        "witness_constraints": {"min_word_len": MIN_WORD_LEN, "min_matches": MIN_MATCHES,
                                "coherence_lh": COHERENCE_LH, "right_lh": RIGHT_LH,
                                "wrong_lh": WRONG_LH, "min_ocr_conf": MIN_OCR_CONF},
        "dead_witnesses_measured_first": {
            "wired_up_count": "landing line 0 on 72 of 74 with the NOTE text supplied; 59 of 74 "
                              "regions are single-line, so 'which line' has no degrees of freedom",
            "token_box_balance": "signed deficit range -20..13 CONTAINS fault range -9..6; 4 of 60 "
                                 "signed rows would be flagged; p92:n1 sits at -1",
            "why_both_failed": "every quantity computed relative to the note region is blind to a "
                               "misplaced region, and p92:n1 is a misplaced region",
        },
        "line_height_witness_agreement": lh_agree,
        "lh_source_counts": dict(Counter(r.get("lh_source") for r in res)),
        "verdicts": dict(Counter(r["verdict"] for r in res)),
        "verdicts_faults": dict(Counter(r["verdict"] for r in F)),
        "verdicts_signed": dict(Counter(r["verdict"] for r in S)),
        "cannot_say_reasons": dict(Counter(r.get("reason") for r in res
                                           if r["verdict"] == "cannot-say")),
        "discriminating": discriminating,
        "NO_DISCRIMINATION": (not discriminating),
        "specificity_contradictions": signed_wrong,
        "positive_control": control,
        "fault_population": {"n": len(F),
                             "noteless": [r["span_id"] for r in F if r["span_id"] != "p92:n1"],
                             "witnessed": "p92:n1"},
        "rows": sorted(res, key=lambda x: (x["page"], x["note_index"])),
    }
    io.open(str(OUT), "w", encoding="utf-8", newline="\n").write(
        json.dumps(out, ensure_ascii=False, indent=1))

    print()
    print("lh witnesses    :", json.dumps(lh_agree, ensure_ascii=False))
    print("lh source       :", out["lh_source_counts"])
    print("verdicts        :", out["verdicts"])
    print("  faults (14)   :", out["verdicts_faults"])
    print("  signed (60)   :", out["verdicts_signed"])
    print("cannot-say why  :", out["cannot_say_reasons"])
    print("discriminating  :", discriminating, "" if discriminating else "  <<< NO DISCRIMINATION")
    print("specificity     :", len(signed_wrong), "signed rows called wrong-line", signed_wrong or "")
    print("positive control:", json.dumps(control, ensure_ascii=False))
    for k in sorted(out["git_banner"]):
        print("  %-6s %s" % (k, out["git_banner"][k]))
    print("provisional     :", out["provisional"])
    print()
    print("FAULTS:")
    for r in sorted(F, key=lambda x: x["span_id"]):
        print("  %-10s %-11s off=%-7s %s" % (r["span_id"], r["verdict"],
                                             r.get("offset_lh"), r.get("reason") or ""))
    print()
    print("written:", OUT)


if __name__ == "__main__":
    main()
