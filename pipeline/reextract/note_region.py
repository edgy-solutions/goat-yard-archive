"""Note-region proposals + the stacked-strip → native-page coordinate un-stacking (config-v2 metadata).

cv_footnote_presplit vertically CONCATS the two columns (left strip above right strip, 20px gap) into one
reading-order strip. This module (1) proposes a note-region per detected note-start — the band from start k
to start k+1 — and (2) un-stacks each strip-y back to NATIVE PAGE coordinates, which differ for the left vs
right column (the right column lived at a different x and y on the 3584x5400 page). A region is a LIST of
per-column RECTANGLES in native coords (the standing rule — a note that stitches columns is two rects, never
one spanning box). Proposals carry provenance (proposed-by: detector) for the ratify console; the ratified
set is the truth for the note-start detector AND the first navigation metadata.

The strip→native map is read from presplit's `info` (the per-column crop origins). When info lacks the
origins (older presplit), we fall back to strip coordinates and flag `native=false` so nothing silently
mis-places a box."""
import numpy as np
from note_start_detect import page_starts, text_lines, strip_vrules, _left_inset, INK

GAP = 20  # the vertical gap cv_footnote_presplit inserts between stacked column strips


def _column_bands(strip):
    """Recover the y-bands of each stacked column in the concatenated strip by finding the ~20px blank
    separators. Returns [(y0, y1)] top→bottom = [left-column, right-column] for a two-column page."""
    a = np.asarray(strip.convert("L")) < INK
    rowink = a.sum(axis=1)
    bands, y, H = [], 0, a.shape[0]
    while y < H:
        if rowink[y] > 0:
            y0 = y
            blank = 0
            while y < H and (rowink[y] > 0 or blank < GAP - 4):
                blank = blank + 1 if rowink[y] == 0 else 0
                y += 1
            bands.append((y0, y - blank))
        else:
            y += 1
    return bands or [(0, H)]


def strip_to_native(strip_box, info, column_bands):
    """Un-stack a strip box to NATIVE page rectangles. cv_footnote_presplit pasted the left column strip at
    canvas-y 0 (native origin rule_l+6) and the right column strip at canvas-y = left_height+20 (native
    origin rule_r+6, native x origin = the footnote gutter xg). So a box wholly in one column is ONE native
    rect; a box that straddles the 20px gap (a stitched note) is TWO — never one spanning box. Returns
    [{box:[x0,y0,x1,y1], col}]."""
    x0, y0, x1, y1 = strip_box
    xg = int(info.get("fn_gutter", [x1])[0])
    rl, rr = (info.get("rules") or [None, None] + [None, None])[:2]
    bands = [b for b in column_bands if b[1] - b[0] > 10]
    if info.get("mode") == "full_width" or len(bands) < 2 or rr is None:
        ry = rl if rl is not None else (rr or 0)
        return [{"box": [x0, ry + 6 + y0, x1, ry + 6 + y1], "col": 0}]
    right_start = bands[1][0]                           # = left_height + 20
    rects = []
    if y0 < right_start - 20:                           # portion in the left column
        ly1 = min(y1, right_start - 20)
        rects.append({"box": [x0, rl + 6 + y0, min(x1, xg), rl + 6 + ly1], "col": 0})
    if y1 > right_start:                                # portion in the right column (stitch tail)
        ry0 = max(y0, right_start)
        rects.append({"box": [xg + x0, rr + 6 + (ry0 - right_start), xg + x1, rr + 6 + (y1 - right_start)], "col": 1})
    return rects or [{"box": [x0, (rl or 0) + 6 + y0, x1, (rl or 0) + 6 + y1], "col": 0}]

def propose_regions(strip, info=None):
    """Propose a note-region per detected note-start. Returns (regions, meta). Each region: {strip_box:
    [x0,y0,x1,y1], col_index}. meta carries the column bands and native mapping availability."""
    starts = [y for (_x, y) in page_starts(strip)]
    a = strip_vrules(np.asarray(strip.convert("L")) < INK)
    ins = _left_inset(a)
    lines = text_lines(a[:, ins:])
    bottom = {y0: y1 for (y0, y1) in lines}
    cbands = _column_bands(strip)
    regions = []
    ys = sorted(starts)
    for i, y in enumerate(ys):
        nxt = ys[i + 1] if i + 1 < len(ys) else strip.height
        # end at the next start, but not across a column band boundary
        ci = next((k for k, (b0, b1) in enumerate(cbands) if b0 <= y <= b1 + GAP), 0)
        band_end = cbands[ci][1] if ci < len(cbands) else strip.height
        y1 = min(nxt, band_end)
        regions.append({"strip_box": [ins, int(y), strip.width - 2, int(max(y1, bottom.get(y, y + 20)))],
                        "col_index": ci})
    return regions, {"column_bands": cbands, "n_detected": len(regions)}
