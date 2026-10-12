# -*- coding: utf-8 -*-
"""Position-sourced note identity for the scoring-45 sheet's channel 2. (Lane B)

ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).

Chris rejected rev 4 because p245:n1's channel-2 string was the previous note's gloss: the candidate, its
note_index and the note text were mutually consistent and all pointed at the wrong note. This module answers
"which note is this crop in" from WHERE THE CROP IS, not from the candidate's index:

    box (strip frame, upscale=1) --> the page's note regions (Lane A's note_line_region, called not edited)
    --> the region holding the box --> that region's ORDINAL k --> notes[k] of vol1_apparatus.jsonl.

The note TEXT has no geometry of its own (one whole-strip read), so region -> text is ordinal within the page.
That link is valid only if the region count equals the apparatus note count (COUNT GATE), and a count
agreement is not a correspondence, so the caller adds an independent content witness (see content_witness).

Nothing here touches the network or writes a file.
"""
import io
import os
import re
import sys
import unicodedata

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "scripts"))
from PIL import Image                                                      # noqa: E402
import cv_footnote_presplit as ps                                          # noqa: E402
import note_region                                                         # noqa: E402
import note_line_region as NLR                                             # noqa: E402
import assembler as ASM                                                    # noqa: E402
import hebrew_aperture_diag as HAD                                         # noqa: E402

PROFILE = ASM.load_profile(os.path.join(_HERE, "book_profile.gill.yaml"))

WIN_FRAC = 0.80        # the winning region holds at least this fraction of the box's height
LOSE_FRAC = 0.20       # no other region holds this fraction or more
RULE_TEXT = ("CONTAINMENT RULE: the winning note region holds >= 80% of the box's height, no other region holds "
             ">= 20% of it, and the box's x-centre lies in the winning region's x-range. Exactly one region must "
             "win. Zero winners, two winners, or a box straddling a boundary is UNRESOLVED. COUNT GATE: the region "
             "count must equal the page's apparatus note count (and the truth set's notes_on_page); otherwise "
             "every span on that page is UNRESOLVED. FRAME GATE: the box must lie inside the strip and inside "
             "one band's paste window, must map through strip_box_to_native to the native rectangle(s) stored by "
             "the crop cut, and the regions' union must cover its y-extent; otherwise UNRESOLVED.")

_PAGE_CACHE = {}


def page_strip(page):
    if page not in _PAGE_CACHE:
        strip, info = ps.presplit(str(HAD.IMG / ("page%d_image1.png" % page)), upscale=1)
        _PAGE_CACHE[page] = (strip.convert("L") if strip is not None else None, info)
    return _PAGE_CACHE[page]


def _intervals(region):
    """A region's y-extent in strip coords: one contiguous interval per segment (a stitched note is two)."""
    return [(sg["lines"][0][0], sg["lines"][-1][1], sg["x0"], sg["x1"]) for sg in region["segments"]]


def resolve(span_id, page, box, apparatus_n, notes_on_page, native_rects):
    """Returns a dict. `state` is 'resolved' or 'unresolved'; `gate` names the failing gate
    ('frame' | 'count' | 'containment') when unresolved. `ordinal` is the 0-based region ordinal when resolved.
    `overlap` is the per-region fraction of the box's height (all regions, in ordinal order)."""
    out = {"span_id": span_id, "state": "unresolved", "gate": None, "why": "", "ordinal": None, "overlap": [],
           "n_regions": None, "apparatus_n": apparatus_n, "notes_on_page": notes_on_page, "frame": {}}
    strip, info = page_strip(page)
    if strip is None or not info or not info.get("bands"):
        out.update(gate="frame", why="presplit returned no strip or no persisted bands")
        return out
    x0, y0, x1, y1 = box
    W, H = strip.size
    fr = out["frame"] = {"strip_size": [W, H], "box_in_strip": bool(0 <= x0 < x1 <= W and 0 <= y0 < y1 <= H)}
    hit = [b for b in info["bands"] if b["paste"][1] <= y0 < b["paste"][1] + b["size"][1]]
    fr["n_bands_holding_box_top"] = len(hit)
    fr["box_x_within_band_width"] = bool(len(hit) == 1 and x1 <= hit[0]["size"][0])
    try:
        rects = [r["box"] for r in note_region.strip_box_to_native(list(box), info)]
    except Exception as e:                                              # noqa: BLE001 -- named, not silent
        rects = None
        fr["map_error"] = "%s: %s" % (type(e).__name__, str(e)[:80])
    fr["native_rects_recomputed"] = rects
    fr["native_rects_stored"] = native_rects
    fr["maps_to_stored_native"] = bool(rects is not None and native_rects is not None and
                                       [list(r) for r in rects] == [list(r) for r in native_rects])
    bad = [k for k in ("box_in_strip", "box_x_within_band_width", "maps_to_stored_native") if not fr[k]]
    if fr["n_bands_holding_box_top"] != 1:
        bad.append("one_band")
    if bad:
        out.update(gate="frame", why="frame not established: " + ", ".join(bad))
        return out
    regions, det = NLR.detect_regions(strip, PROFILE)[0], None
    out["n_regions"] = len(regions)
    if len(regions) != apparatus_n or len(regions) != notes_on_page:
        out.update(gate="count", why="count gate: %d note regions detected, %d apparatus notes, truth-set "
                   "notes_on_page %d" % (len(regions), apparatus_n, notes_on_page))
        return out
    h = float(y1 - y0)
    ov = []
    for reg in regions:
        tot = 0
        for a0, a1, _xa, _xb in _intervals(reg):
            tot += max(0, min(y1, a1) - max(y0, a0))
        ov.append(tot / h)
    out["overlap"] = [round(v, 4) for v in ov]
    cover = sum(ov)
    fr["union_cover_fraction"] = round(min(cover, 1.0), 4)
    if cover < 0.999:
        out.update(gate="frame", why="frame not established: the regions' union covers only %.3f of the box's "
                   "y-extent" % cover)
        return out
    state, k, why = decide(ov, (x0 + x1) / 2.0, [[(xa, xb) for _a0, _a1, xa, xb in _intervals(reg)] for reg in regions])
    if state != "resolved":
        out.update(gate="containment", why=why)
        return out
    out.update(state="resolved", ordinal=k)
    return out


def decide(ov, cx, xranges):
    """The containment rule, pure. ov[k] = fraction of the box's height inside region k; xranges[k] = that
    region's list of (x0, x1). Returns (state, ordinal|None, why)."""
    win = [k for k, v in enumerate(ov) if v >= WIN_FRAC]
    other = [k for k, v in enumerate(ov) if v >= LOSE_FRAC]
    if len(win) != 1 or len(other) != 1:
        return "unresolved", None, ("containment: regions holding >=80%%: %s; regions holding >=20%%: %s" % (win, other))
    k = win[0]
    if not any(xa <= cx <= xb for xa, xb in xranges[k]):
        return "unresolved", None, "containment: the box's x-centre lies outside region %d's x-range" % k
    return "resolved", k, ""


# ------------------------------------------------------------------ content witness
_FINAL = str.maketrans(u"ךםןףץ", u"כמנפצ")
_NOT_CONS = re.compile(u"[^א-ת]")
_HEB_RUN = re.compile(u"[֐-׿][֐-׿\\s\\[\\]־]*")


def fold(s):
    t = unicodedata.normalize("NFC", s or "").replace("[", "").replace("]", "")
    return _NOT_CONS.sub("", t).translate(_FINAL)


def lev(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def note_distance(signed, note_text):
    """Better of (a) Levenshtein from the folded signed string to the folded FIRST Hebrew run of the note and
    (b) 0 if the folded signed string occurs anywhere in the note's folded Hebrew."""
    s = fold(signed)
    t = unicodedata.normalize("NFC", note_text or "")
    m = _HEB_RUN.search(t)
    first = fold(m.group(0)) if m else ""
    allheb = fold(t)
    d = lev(s, first) if first else len(s)
    if s and s in allheb:
        d = 0
    return d


def content_witness(signed, notes):
    """Score every note; lowest distance wins; a tie for the lowest is an abstention (best=None)."""
    ds = [note_distance(signed, n["text"]) for n in notes]
    lo = min(ds)
    best = [k for k, d in enumerate(ds) if d == lo]
    rest = sorted(d for k, d in enumerate(ds) if k not in best)
    return {"distances": ds, "best": best[0] if len(best) == 1 else None, "tied": best if len(best) > 1 else [],
            "best_distance": lo, "runner_up_distance": (lo if len(best) > 1 else (rest[0] if rest else None))}
