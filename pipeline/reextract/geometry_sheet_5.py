# -*- coding: utf-8 -*-
u"""The 5-card geometry sheet: the newly-adjudicated misplaced-region candidates, for Chris.

    python geometry_sheet_5.py

Ruling 2026-11-14(2): *"The 5 candidates (p107:n3, p133:n1, p144:n0, p256:n3, p306:n1) go to Chris
as a 5-card geometry sheet for adjudication. Flag p306 on its card as contaminated by the page-level
shift and exclude it from any rate."*

No spend, no outbound call, nothing crosses the network.

**The pixels do not leave this machine.**  Every crop is written to disk and the sheet carries a
`file://` path to it.  Nothing is base64-embedded, and that is asserted over the sheet's own bytes
before it is written -- `truth_set_sheet.py:182` states the reason and it is the reason here: a path
cannot be mailed anywhere useful, a base64 payload can.  These are note-band pixels.

**Two views per card, and the unmarked one comes first.**  An overlay is drawn from the very numbers
whose correctness is the question, so a sheet that shows only the overlay cannot be used to check the
overlay -- the reader's eye is handed the conclusion before the evidence.  So each card shows the
crop UNMARKED, for locating the Hebrew and the note's line by eye, and then the SAME crop with the
stored box outlined and the witness's line ticked.  The disagreement between what the eye finds and
what the marks assert is the signal; agreement is the confirmation.  The colours are locators, never
verdicts: every quantity a mark stands for is also printed as text on the card, because a verdict
recorded as a border colour is not honoured.

**The frame is derived, never invented.**  The crop's column comes from the band whose own
`native`/`paste` mapping reproduces the stored page box EXACTLY; if no band does, the card refuses
and says so rather than cropping a guessed column.  The vertical extent is the union of the stored
box and the witness line plus MARGIN_LH line heights, clamped to the page, and both the REQUESTED
and the REALIZED origin and extent are recorded with the clamp bounds -- a record of the crop that
was asked for, where the consumer needs the crop that was taken, has misled two consumers before.

**The control card is on the sheet and is not for adjudication.**  `p92:n1` is the one span a human
independently placed ("the crop is 3 lines up from the hebrew"), and the checker measures it at
-3.32 lh.  It is rendered first, labelled CONTROL, so the eye can be calibrated on the known answer
before judging the five.  It is excluded from the adjudication population by construction.

**This sheet carries no answer field.**  A content-addressed artifact cannot carry the record of its
own approval: answering inside the sheet renames the thing that was approved.  The verdicts come back
as a separate standoff record naming this sheet's sha256, in the shape `audit_overlay_20261025.py`
established.  If such a record already exists for this digest the sheet refuses to re-render, because
re-rendering the pixels someone has already signed would silently move the thing their yes was about.
"""
import base64                                                              # noqa: F401  (see check)
import hashlib
import html
import io
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, os.pardir, "scripts"))

from PIL import Image, ImageDraw                                           # noqa: E402
import cv_footnote_presplit as ps                                          # noqa: E402  Lane A's, read-only
import hebrew_aperture_diag as HAD                                         # noqa: E402
import wrong_line_check as C                                               # noqa: E402
from clean_run import git_state, provisional                               # noqa: E402

DATA = HAD.DATA
CHECK_PATH = DATA / ("wrong_line_check_%s.json" % C.SET)
LANEB = "C:/Users/cnogr/git/goatyard-laneB"
DRV = "C:/Users/cnogr/git/dr-voluminous"

CANDIDATES = ["p107:n3", "p133:n1", "p144:n0", "p256:n3", "p306:n1"]
CONTROL = "p92:n1"
MARGIN_LH = 2.5         # line heights of context above and below the union of box and witness line
INK_FLOOR = 128         # a pixel darker than this is ink, for the liveness count only


def digest_obj(obj):
    s = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def sha16_file(p):
    with io.open(str(p), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:16]


def band_for(row, info):
    """The band whose own mapping reproduces this row's stored page box exactly, or None.

    `band_to_page` maps a band box to the page as `native + (xy - paste)`. Inverting that for every
    band and demanding EXACT equality with the stored page box identifies the band the checker used
    without re-deriving it and without a tolerance -- a tolerance here would let a neighbouring band
    answer for this one. No match is a refusal, not a fallback.
    """
    bb, pb = row["stored_box_band"], row["stored_box_page"]
    for i, b in enumerate(info.get("bands") or []):
        dx = b["native"][0] - b["paste"][0]
        dy = b["native"][1] - b["paste"][1]
        if [bb[0] + dx, bb[1] + dy, bb[2] + dx, bb[3] + dy] == list(pb):
            return i, b
    return None, None


def card_crops(row, info, page_im, outdir):
    """(unmarked path, marked path, geometry dict) or (None, None, {'refused': why})."""
    bi, b = band_for(row, info)
    if b is None:
        return None, None, {"refused": "no band's own mapping reproduces this stored page box, so "
                                       "the column frame cannot be derived; nothing is cropped"}
    lh = float(row["lh"])
    box = row["stored_box_page"]
    wy = float(row["note_y_ocr"])
    x0, x1 = b["native"][0], b["native"][0] + b["size"][0]
    req_y0 = min(box[1], wy) - MARGIN_LH * lh
    req_y1 = max(box[3], wy) + MARGIN_LH * lh
    W, H = page_im.size
    rx0, rx1 = max(0, int(x0)), min(W, int(x1))
    ry0, ry1 = max(0, int(round(req_y0))), min(H, int(round(req_y1)))

    im = page_im.crop((rx0, ry0, rx1, ry1)).convert("RGB")
    dark = sum(1 for p in im.convert("L").getdata() if p < INK_FLOOR)

    up = os.path.join(outdir, "%s_plain.png" % row["span_id"].replace(":", "_"))
    im.save(up)

    mk = im.copy()
    d = ImageDraw.Draw(mk)
    d.rectangle([box[0] - rx0, box[1] - ry0, box[2] - rx0, box[3] - ry0],
                outline=(220, 30, 30), width=4)
    ty = int(round(wy - ry0))
    d.line([(0, ty), (mk.size[0], ty)], fill=(30, 90, 220), width=3)
    d.rectangle([0, ty - 6, 26, ty + 6], fill=(30, 90, 220))
    mp = os.path.join(outdir, "%s_marked.png" % row["span_id"].replace(":", "_"))
    mk.save(mp)

    geo = {
        "band_index": bi,
        "band_col": b["col"],
        "band_native_origin": list(b["native"]),
        "band_paste": list(b["paste"]),
        "band_size": list(b["size"]),
        # REQUESTED vs REALIZED, both, with the bounds that did the clamping.
        "requested_crop": {"x0": int(x0), "y0": round(req_y0, 1),
                           "x1": int(x1), "y1": round(req_y1, 1)},
        "realized_crop_origin": [rx0, ry0],
        "realized_crop_extent": [rx1 - rx0, ry1 - ry0],
        "clamp_bounds": {"page_w": W, "page_h": H},
        "clamped": [rx0 != int(x0), ry0 != int(round(req_y0)),
                    rx1 != int(x1), ry1 != int(round(req_y1))],
        "margin_lh": MARGIN_LH,
        "ink_pixels_below_%d" % INK_FLOOR: dark,
        "ink_fraction": round(dark / float(max(1, (rx1 - rx0) * (ry1 - ry0))), 4),
        "plain_sha16": sha16_file(up),
        "marked_sha16": sha16_file(mp),
    }
    return up, mp, geo


def furl(p):
    """A LOCAL PATH, NOT PIXELS -- see the module docstring. Note-band pixels stay on this disk."""
    return "file:///" + str(p).replace("\\", "/")


CSS = u"""
body{background:#14110e;color:#eee;font:14px/1.55 Georgia,serif;margin:0;padding:26px 30px}
h1{font-size:21px;margin:0 0 4px}
.sub{color:#b2a79a;font-size:12.5px;margin-bottom:18px}
.pre{background:#1d1915;border-left:3px solid #6b5c46;padding:11px 14px;margin:14px 0;
     font:12.5px/1.6 Consolas,monospace;color:#d8cdbd;white-space:pre-wrap}
.card{background:#1b1713;border:1px solid #39322a;border-radius:5px;margin:22px 0;padding:16px 18px}
.card.ctl{border-color:#4b6b3a;background:#171c14}
.card.cont{border-color:#7a5a20}
.id{font:16px Consolas,monospace;color:#f0e6d6}
.tag{display:inline-block;font:11px Consolas,monospace;padding:2px 7px;border-radius:3px;
     margin-left:8px;vertical-align:2px}
.tag.ctl{background:#2f4a22;color:#cfe8bd}.tag.cont{background:#5a3f12;color:#f0d6a0}
.tag.cls{background:#3a2f22;color:#e6cfa8}
table{border-collapse:collapse;margin:10px 0;font:12.5px/1.5 Consolas,monospace}
td{border:1px solid #3a3229;padding:3px 9px;vertical-align:top}
td.k{color:#a79a88;white-space:nowrap}
.heb{font-size:23px;direction:rtl;background:#241f19;padding:7px 11px;display:inline-block;
     border-radius:3px}
.view{margin:12px 0 4px}
.view a{color:#9fc4e8;font:12px Consolas,monospace}
.view .lab{color:#b2a79a;font-size:12px;margin:6px 0 3px}
.warn{background:#3a2412;border-left:3px solid #a8701f;padding:10px 13px;margin:10px 0;
      color:#f2ddba;font-size:13px}
.noink{background:#4a1414;border-left:3px solid #c23;padding:10px 13px;color:#ffd9d9}
.k2{color:#a79a88}
"""


def main():
    g0 = {"laneB": git_state(LANEB), "drv": git_state(DRV)}
    print("git start       :", json.dumps(g0, ensure_ascii=False))

    chk = json.loads(io.open(str(CHECK_PATH), encoding="utf-8").read())
    assert chk["set_sha16"] == C.SET and chk["n"] == C.SET_N, \
        "the checker output is not about the frozen truth set"
    assert chk.get("provisional") is False, \
        "the checker run is provisional; no card may be drawn from it"
    by = dict((r["span_id"], r) for r in chk["rows"])

    order = [CONTROL] + CANDIDATES
    for s in order:
        assert s in by, "%s is not in the checker output" % s
    assert by[CONTROL]["verdict"] == "wrong-line", \
        "the control is on this sheet to calibrate the eye on a KNOWN wrong-line; it is not one"
    assert all(by[s]["verdict"] == "wrong-line" for s in CANDIDATES), \
        "a candidate card is being drawn for a span the checker did not call wrong-line"
    assert all(by[s]["is_fault"] for s in order), \
        "every card on this sheet must be a pass-1 fault; a signed row does not belong here"

    # Contamination, read from the reclassification record's derivation rather than typed here.
    rc = sorted(str(p) for p in DATA.glob("FAULTCLASS_reclass_*.json"))
    assert rc, "the reclassification record must exist before a sheet can carry its classes"
    rec = json.loads(io.open(rc[-1], encoding="utf-8").read())
    cls_of = dict((r["span_id"], r) for r in rec["rows"])
    excluded = set(rec["excluded_from_rate"])
    assert excluded == {"p306:n1"}, \
        "the ruling's exclusion is p306:n1; the record derives %s" % sorted(excluded)

    # CONTENT-ADDRESSED BY WHAT IT DESCRIBES, computed before anything is rendered.
    dig = digest_obj({"of": sha16_file(CHECK_PATH), "set": C.SET, "order": order,
                      "margin_lh": MARGIN_LH,
                      "boxes": dict((s, by[s]["stored_box_page"]) for s in order),
                      "witness_y": dict((s, by[s]["note_y_ocr"]) for s in order)})
    adj = DATA / ("GEOMETRY5_adjudication_%s.json" % dig)
    assert not os.path.exists(str(adj)), \
        ("an adjudication record already exists for this sheet (%s): re-rendering would move the "
         "pixels a human has already signed. Delete that record deliberately, or change nothing."
         % adj)

    outdir = str(DATA / ("geometry5_%s" % dig))
    if not os.path.isdir(outdir):
        os.makedirs(outdir)

    cards, geos = [], {}
    pages = {}
    for s in order:
        r = by[s]
        pg = r["page"]
        if pg not in pages:
            _strip, info = ps.presplit(C.PAGE % pg, upscale=1)
            pages[pg] = (info, Image.open(C.PAGE % pg))
        info, pim = pages[pg]
        up, mp, geo = card_crops(r, info, pim, outdir)
        geos[s] = geo
        cards.append((s, r, up, mp, geo))

    # ---------------------------------------------------------------- the sheet
    h = [u"<!doctype html><meta charset='utf-8'><title>GEOMETRY5 %s</title><style>%s</style>"
         % (dig, CSS)]
    h.append(u"<h1>Five misplaced-region candidates, for adjudication</h1>")
    h.append(u"<div class='sub'>Lane B / session <code>50612c81</code> &middot; sheet "
             u"<code>%s</code> &middot; all page numbers are FILE pages (printed = file &minus; 88)"
             u" &middot; no spend, nothing left this machine</div>" % dig)
    h.append(u"<div class='pre'>WHAT IS BEING ASKED.  Pass 1 faulted 14 of 74 spans.  The fault "
             u"class was misnamed: no quantity computed inside the note region can see these "
             u"faults, because the region itself is what moves.  An independent witness -- the "
             u"page's own Tesseract layer in native page coordinates, matched on the note's LATIN "
             u"words only -- places five of them off the note's own line.  Those five are below.\n\n"
             u"WHAT A VERDICT HERE DECIDES.  Only the vertical question: is the red box on the "
             u"line the blue tick marks?  Nothing on this sheet speaks to horizontal extent, to "
             u"which printed note the region covers, or to the content of any crop.\n\n"
             u"HOW TO READ A CARD.  The PLAIN crop is first on purpose: find the Hebrew and the "
             u"note's line by eye before looking at the marks, because the marks are drawn from "
             u"the numbers under test.  Then open the MARKED crop.  Agreement confirms; "
             u"disagreement is the finding.  Both crops are native resolution, unscaled.\n\n"
             u"THE COLOURS ARE LOCATORS, NOT VERDICTS.  Red = the stored box.  Blue = where the "
             u"witness puts the note's own line.  Every number a mark stands for is printed as "
             u"text on the card.\n\n"
             u"THIS SHEET HAS NO ANSWER FIELD.  Reply with a verdict per span and it will be "
             u"transcribed into a standoff record naming this sheet's digest; nothing here edits "
             u"the pass-1 ingest, re-signs anything, or touches a sealed page.</div>")
    h.append(u"<div class='pre'>THE SCALE RESTS ON ONE POINT.  <b>%s</b> is the only span a human "
             u"independently placed -- \u201cthe crop is 3 lines up from the hebrew\u201d -- and "
             u"the checker measures it at <b>%s lh</b>.  It is rendered first as a CONTROL so the "
             u"eye can be calibrated on the known answer.  It is not for adjudication and is in no "
             u"population.  There is no second control; a second human-witnessed span would do "
             u"more for this check than any amount of tuning.</div>"
             % (CONTROL, by[CONTROL]["offset_lh"]))

    for s, r, up, mp, geo in cards:
        is_ctl = (s == CONTROL)
        cont = s in excluded
        klass = "card" + (" ctl" if is_ctl else "") + (" cont" if cont else "")
        h.append(u"<div class='%s'>" % klass)
        h.append(u"<div><span class='id'>%s</span>" % html.escape(s))
        if is_ctl:
            h.append(u"<span class='tag ctl'>CONTROL &mdash; not for adjudication</span>")
        if cont:
            h.append(u"<span class='tag cont'>CONTAMINATED &mdash; excluded from any rate</span>")
        h.append(u"<span class='tag cls'>%s</span></div>"
                 % html.escape(cls_of[s]["class"]))

        if cont:
            h.append(u"<div class='warn'><b>Contaminated by a page-level shift.</b> %s<br><br>"
                     u"So a verdict on this card is a verdict about <b>page %d</b>, not about this "
                     u"box in isolation. The checker cannot tell a shifted band from two shifted "
                     u"boxes, and it is excluded from any rate by derivation, not by hand."
                     % (html.escape(cls_of[s]["contamination_note"]), r["page"]))
            h.append(u"</div>")

        if geo.get("refused"):
            h.append(u"<div class='noink'><b>No crop.</b> %s</div></div>"
                     % html.escape(geo["refused"]))
            continue
        if geo["ink_pixels_below_%d" % INK_FLOOR] == 0:
            h.append(u"<div class='noink'><b>This crop carries no ink at all.</b> It shows "
                     u"nothing and must not be adjudicated; the geometry below is still "
                     u"recorded.</div>")

        h.append(u"<div>signed Hebrew: <span class='heb'>%s</span></div>"
                 % html.escape(r.get("hebrew") or u"(none)"))
        rows = [
            (u"witness offset", u"<b>%s lh</b> (%s), %s lines off"
                % (r["offset_lh"], u"below the note's line" if (r["offset_lh"] or 0) > 0
                   else u"above the note's line", r["lines_off"])),
            (u"line height", u"%s px, source <b>%s</b>%s"
                % (r["lh"], r["lh_source"],
                   u" &mdash; census and OCR witnesses agree to a median 1.096 but range "
                   u"0.887&ndash;1.47, so roughly half a line of slack is real")),
            (u"anchors", u"%s note Latin words were candidates, %s matched, <b>%s unique</b> on "
                         u"the page, %s spatially coherent, spread %s lh"
                % (r["witness"].get("note_latin_candidates"), r["witness"].get("matched_any"),
                   r["witness"].get("matched_unique"), r["witness"].get("coherent"),
                   r["witness"].get("kept_spread_lh"))),
            (u"stored box (page px)", u"%s" % (r["stored_box_page"],)),
            (u"box y centre / witness y", u"%s / %s" % (r["box_y_mid_page"], r["note_y_ocr"])),
            (u"band", u"index %s, col <b>%s</b>, native origin %s, size %s"
                % (geo["band_index"], geo["band_col"], geo["band_native_origin"],
                   geo["band_size"])),
            (u"crop requested", u"%s" % json.dumps(geo["requested_crop"])),
            (u"crop realized", u"origin %s, extent %s, clamped %s, page %sx%s"
                % (geo["realized_crop_origin"], geo["realized_crop_extent"], geo["clamped"],
                   geo["clamp_bounds"]["page_w"], geo["clamp_bounds"]["page_h"])),
            (u"ink", u"%s px below %d (%s of the crop)"
                % (geo["ink_pixels_below_%d" % INK_FLOOR], INK_FLOOR, geo["ink_fraction"])),
            (u"pass-1 disposition", u"<code>%s</code> &mdash; unchanged on disk"
                % html.escape(r["disposition"])),
            (u"new class", u"<b>%s</b>, confidence <b>%s</b>"
                % (html.escape(cls_of[s]["class"]), html.escape(cls_of[s]["confidence"]))),
        ]
        h.append(u"<table>")
        for k, v in rows:
            h.append(u"<tr><td class='k'>%s</td><td>%s</td></tr>" % (k, v))
        h.append(u"</table>")
        h.append(u"<div class='view'><div class='lab'>1 &mdash; PLAIN, judge this first "
                 u"(%s px, sha <code>%s</code>)</div><a href='%s'>%s</a></div>"
                 % (geo["realized_crop_extent"], geo["plain_sha16"], furl(up),
                    html.escape(os.path.basename(up))))
        h.append(u"<div class='view'><div class='lab'>2 &mdash; MARKED: red = stored box, blue "
                 u"tick = witness's line for this note (sha <code>%s</code>)</div>"
                 u"<a href='%s'>%s</a></div>"
                 % (geo["marked_sha16"], furl(mp), html.escape(os.path.basename(mp))))
        h.append(u"</div>")

    h.append(u"<div class='pre'>WHAT THIS SHEET DOES NOT SETTLE.\n"
             u"  &bull; One control point. Every verdict rests on %s alone.\n"
             u"  &bull; The false-positive rate is unmeasured. The checker contradicted 3 signed "
             u"rows and they decompose into a bad line height (p275 census lh = 14 px), this "
             u"page-level shift (p306) and a corroboration of a known open mystery (p245:n1). "
             u"Three heterogeneous contradictions are not a rate, and none is published.\n"
             u"  &bull; 32 of 74 spans abstain, 19 for too few unique anchor words -- worst "
             u"exactly where notes are short. 3 of the 14 faults are among them and are untouched, "
             u"not cleared.\n"
             u"  &bull; 5 of the 14 faults measured ON the note's line. They are NOT on this sheet "
             u"and are NOT misplaced regions; their fault is real but on another axis. A blanket "
             u"rename of the class would have asserted a mechanism for them that the only "
             u"measurement on record contradicts.\n"
             u"  &bull; The structural cause, <code>draw_pool.py:87</code>, is still unfixed. It is "
             u"Lane A substrate and the change remains requested, not made. This sheet measures "
             u"the damage; it does not repair it.</div>" % CONTROL)

    doc = u"\n".join(h)

    # LIVENESS OVER THE BYTES: the rule is that note-band pixels are linked, never embedded. A rule
    # nothing checks is a rule that silently lapses the first time a helper is swapped.
    assert u"data:image" not in doc, \
        "a crop is base64-embedded in this sheet; note-band pixels must be linked, never embedded"
    assert doc.count(u"file:///") == 2 * len(cards), \
        "every card must link exactly two views; found %d links for %d cards" \
        % (doc.count(u"file:///"), len(cards))
    assert all(geos[s].get("plain_sha16") for s in order), "a card rendered no pixels"
    assert len(set(geos[s]["plain_sha16"] for s in order)) == len(order), \
        "two cards share a crop digest, so one card is showing another span's pixels"

    out = DATA / ("GEOMETRY5_sheet_%s.html" % dig)
    io.open(str(out), "w", encoding="utf-8", newline="\n").write(doc)

    g1 = {"laneB": git_state(LANEB), "drv": git_state(DRV)}
    side = {
        "kind": "geometry5_sheet_manifest",
        "lane": "Lane B", "session": "50612c81",
        "ruling": "2026-11-14(2)",
        "sheet": os.path.basename(str(out)),
        "sheet_sha256_16": sha16_file(out),
        "addressed_by": "a digest over the checker output's bytes, the span order, the stored "
                        "boxes, the witness line positions and the margin -- i.e. over what the "
                        "sheet describes, not over its own bytes",
        "digest": dig,
        "of": os.path.basename(str(CHECK_PATH)),
        "of_sha256_16": sha16_file(CHECK_PATH),
        "reclass_record": os.path.basename(rc[-1]),
        "reclass_self_sha16": rec["self_sha16"],
        "adjudication_population": CANDIDATES,
        "control_not_adjudicated": CONTROL,
        "excluded_from_rate": sorted(excluded),
        "pixels": "linked by file:// path, never embedded; note-band pixels do not leave this disk",
        "crop_dir": outdir,
        "cards": geos,
        "page_convention": "all page numbers are FILE pages (printed = file - 88)",
        "answer_record_would_be": os.path.basename(str(adj)),
        "answer_not_in_sheet_because": "a content-addressed artifact cannot carry the record of "
                                       "its own approval; answering inside the sheet renames the "
                                       "thing approved",
        "git_start": g0, "git_end": g1,
        "provisional": any(provisional(g0[k], g1[k]) for k in g0),
        "spend": "none; no model call, no outbound request",
    }
    io.open(str(DATA / ("GEOMETRY5_sheet_%s.json" % dig)), "w",
            encoding="utf-8", newline="\n").write(
        json.dumps(side, ensure_ascii=False, sort_keys=True, indent=1))

    print("cards           : %d (1 control + %d candidates)" % (len(cards), len(CANDIDATES)))
    print("excluded        :", sorted(excluded))
    print("ink fractions   :", json.dumps(dict((s, geos[s]["ink_fraction"]) for s in order)))
    print("clamped any     :", any(any(geos[s]["clamped"]) for s in order))
    print("provisional     :", side["provisional"])
    print("sheet           :", out)
    print("crops           :", outdir)


if __name__ == "__main__":
    main()
