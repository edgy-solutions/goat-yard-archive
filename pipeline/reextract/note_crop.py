"""Per-note crop emission — the crop SOURCE for the marker verifier (config-v2, Chris 2026-09-20).

This replaces `marker_harvest._page_marker_crops` as the verifier's crop source, and the reason is an
alignment failure that was measured, not suspected. That path produced one crop per *detector* note-start
and handed back a flat list; the verifier then indexed it by the *extractor's* note number. On p129 that was
13 crops for 15 notes, on p145 7 for 2, on p146 12 for 13 — so crop[k] was simply not note k, and every
"verification" downstream of it was asking about the wrong glyph. There is no index to align here because
there is no second list: each crop is cut FROM the note's own region, so the crop cannot belong to a
different note than the one it was cut for.

WHAT IS EMITTED, per note:
  note_rects    column-bounded NATIVE-page rectangles. A note that stitches two columns is two rects, never
                one spanning box (the standing rule) — and now that holds in band coordinates too, because
                note_line_regions returns segments carrying their own column's x-bounds.
  marker_rect   the raised-marker sub-crop, found by _marker_box inside the note's OWN first line. This is
                the verifier's input.
  crops         optional PNGs on disk. Native pixels: presplit(upscale=1) does no resize, so strip pixels
                ARE page pixels. upscale=2 is LANCZOS interpolation — more pixels, not more information —
                and must never be the source for a glyph the matcher will score against native exemplars.

THE GATE IS INHERITED, NOT RE-DECIDED. note_line_regions abstains the whole page when detected note-starts
!= the extractor's count. On abstain this emits NOTHING per note and reports `fallback: whole-band`, which
is the current behaviour — the reader reads the band as it does today. Degrading to the status quo is the
correct failure mode; a partial or repaired mapping is not.

WHAT THE GATE CANNOT SEE: a compensating error. One missed note-start plus one false note-start elsewhere
sums to the right total, passes count equality, and mis-maps every note after the first error. Count
equality is blind to it by construction — the same cancellation class `is_consecutive_run` exists to catch
on the letter axis. The ratified note boxes are the only instrument that can detect it; see
score_note_crops.py, whose gate is zero wrong note->box mappings (abstains are fine)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import numpy as np
from PIL import Image
import cv_footnote_presplit as ps
import note_region as NR
import note_line_region as NLR
import marker_harvest as MH

IMG = Path("C:/Users/cnogr/git/dr-voluminous/commentary/volume1")


def _seg_box(seg):
    """The strip-coordinate rectangle of one segment, from its first line's top to its last line's bottom.
    X follows the RATIFIED convention — full strip width — because in the stacked strip a page column is a
    y-band at full width, not an x-half. `ins` is the content inset and is used for the marker search, not
    for the box."""
    return [int(seg["x0"]), int(seg["lines"][0][0]), int(seg["x1"]), int(seg["lines"][-1][1])]


def page_note_crops(page, n_notes, profile, upscale=1, out_dir=None, img_dir=IMG, want_crops=True):
    """Per-note rectangles + marker sub-crops for one page. Returns (result, strip, info).

    result = {page, status, n_notes, n_detected, notes:[...]} where status is `ok` or `region-abstain`.
    On `region-abstain` `notes` is empty and `fallback` is 'whole-band' — the caller reads the band as
    today. Never a partial mapping."""
    img = Path(img_dir) / f"page{page}_image1.png"
    if not img.exists():
        return {"page": page, "status": "no-image", "notes": []}, None, None
    strip, info = ps.presplit(str(img), upscale=upscale)
    cbands = NR._column_bands(strip)
    regions, st = NLR.note_line_regions(strip, n_notes, profile)

    res = {"page": page, "n_notes": n_notes, "upscale": upscale, "mode": info.get("mode"),
           "strip_size": list(strip.size), "column_bands": cbands, "notes": []}
    if regions is None:
        res["status"] = "region-abstain"
        res["detail"] = st
        res["fallback"] = "whole-band"
        # the detected count is the only diagnostic worth keeping off an abstained page
        try:
            res["n_detected"] = int(st.split("detected=")[1].split(",")[0])
        except Exception:
            pass
        return res, strip, info

    res["status"] = "ok"
    res["n_detected"] = len(regions)
    ink = np.asarray(strip.convert("L")) < NLR.INK
    if out_dir:
        out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)

    for k, reg in enumerate(regions):
        segs = []
        for seg in reg["segments"]:
            sb = _seg_box(seg)
            segs.append({"col": seg["col"], "strip_box": sb,
                         "native_rects": NR.strip_to_native(sb, info, cbands)})
        rec = {"k": k, "segments": segs, "stitched": len(segs) > 1,
               "native_rects": [r for s in segs for r in s["native_rects"]]}

        # MARKER SUB-CROP from the note's own first line. _marker_box wants the line's ink mask, bounded to
        # this segment's column — the floating-superscript test is what separates a true marker from a rule
        # remnant or a body capital, and both impostors live at the column edges.
        fs = reg["segments"][0]
        fy0, fy1 = fs["lines"][0]
        lineband = ink[fy0:fy1, fs["ins"]:fs["x1"]]
        mb = MH._marker_box(lineband)
        if mb is None:
            rec["marker"] = None
            rec["marker_status"] = "no-floating-marker"
        else:
            mx0, my0, mx1, my1 = mb
            msb = [fs["ins"] + mx0, fy0 + my0, fs["ins"] + mx1, fy0 + my1]
            rec["marker"] = {"strip_box": msb, "size": [msb[2] - msb[0], msb[3] - msb[1]],
                             "native_rects": NR.strip_to_native(msb, info, cbands)}
            rec["marker_status"] = "ok"
            if want_crops and out_dir:
                cp = out_dir / f"p{page}_note{k}_marker.png"
                strip.crop(tuple(msb)).save(cp)
                rec["marker"]["crop"] = cp.name
        if want_crops and out_dir:
            for si, s in enumerate(segs):
                cp = out_dir / f"p{page}_note{k}_seg{si}.png"
                strip.crop(tuple(s["strip_box"])).save(cp)
                s["crop"] = cp.name
        res["notes"].append(rec)
    return res, strip, info


def attach_to_notes(notes, crop_result):
    """Persist the geometry ON each Note dict, in place. Body bytes are never touched — positions are
    navigation metadata riding alongside the text (the page-geometry standing rule). A note gets
    `note_rects`/`marker_rect` only when the page mapped; on abstain every note is marked so that no
    consumer can mistake 'no geometry' for 'geometry at the origin'."""
    if crop_result.get("status") != "ok":
        for n in notes:
            n["note_rects"] = None
            n["marker_rect"] = None
            n["geometry_status"] = crop_result.get("status", "unknown")
        return notes
    by_k = {r["k"]: r for r in crop_result["notes"]}
    for k, n in enumerate(notes):
        r = by_k.get(k)
        if r is None:
            n["note_rects"] = None; n["marker_rect"] = None; n["geometry_status"] = "missing"; continue
        n["note_rects"] = r["native_rects"]
        n["marker_rect"] = (r["marker"] or {}).get("native_rects")
        n["geometry_status"] = "ok" if r["marker_status"] == "ok" else r["marker_status"]
    return notes
