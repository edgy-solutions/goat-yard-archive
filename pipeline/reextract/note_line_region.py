"""Per-note line-region extraction (config-v2 pixel isolation) — the upstream piece that hands the Hebrew
localizer a clean, column-bounded, single-line crop. Replaces the ratified-y-band SIMULATION used to score
the localizer.

The mapping is ORDER-MATCHING — the localizer's own principle one level up: count the reliable things, never
recognize them. The frozen extractor already knows, per page, how many notes and in what order;
hanging_indent finds note-start lines by the marker-plus-gap projection without reading a glyph. So the join
is arithmetic: the k-th detected note-start is note k, and every line between start k and start k+1 belongs to
note k. No glyph recognition anywhere in the join.

COUNT EQUALITY IS THE GATE. Detected note-starts must equal the extractor's note count. Equal -> map.
Unequal -> ABSTAIN the whole page and flag (a missed indent / a stitched note / an invented marker needs
eyes) — never repair silently, the same discipline as the localizer's box-count abstain.

COLUMN BOUNDING = READING ORDER — BUT THE COLUMNS ARE Y-BANDS, NOT X-HALVES. This is the correction of
2026-09-20, forced by the ratified boxes. `cv_footnote_presplit` has ALREADY un-stacked the page's two
apparatus columns into one reading-order strip: it pastes the left column above the right, separated by a
20px gap, each at FULL strip width. So in strip space a "column" is a horizontal band, and there is no
vertical gutter to find. The original version of this module called `detect_gutter` and split the strip in
X — which on a stacked strip locks onto a spurious whitespace valley mid-line (961px on p102, 1009 on p138,
1147 on p168) and cuts every text line in half. It scored 10.7% count-equality and mean IoU 0.115 against
the 227 ratified boxes; the ratified boxes are all `x: 0 -> width-2`, which is what gave the error away.
The module had never been wired, so nothing had ever caught it.

Reading order is therefore already correct top-to-bottom through the strip. A note that starts at the
bottom of one band and continues at the top of the next is the STITCH case; `strip_to_native` splits it
into two native rects (never one spanning box) because the bands map to different page origins.

WRAPPED NOTES. The Hebrew may be on a note's second line. The localizer counts Latin words from the left up
to the Hebrew, so the mapping must also say WHICH line holds the Hebrew token: walk the note's lines,
subtract each line's word-box count from the Hebrew's token offset, and stop at the line where it lands.

Marker RECOGNITION is not used here — it is only a confirmation check on abstained pages (elsewhere), never a
source of a mapping the count did not already support."""
import numpy as np
from hanging_indent import _text_lines, _is_note_start
import word_box_align as W

INK = 110

def detect_gutter(band):
    """The apparatus gutter x — the whitespace valley in the central third of the strip. Returns None when
    there is no clear valley (a single full-width column)."""
    a = np.asarray(band.convert("L")) < INK
    Wd = a.shape[1]; col = a.sum(axis=0)
    lo, hi = int(Wd * 0.38), int(Wd * 0.62)
    if hi <= lo:
        return None
    x = lo + int(np.argmin(col[lo:hi]))
    # a real gutter is a near-empty column; if the "valley" still carries much ink it's full-width
    return x if col[x] < 0.15 * (col.max() or 1) else None

def _left_inset(a, x0, x1):
    """Skip a column-rule fragment at the left edge of a column: the first narrow ink band that spans most
    of the height. Returns the x to start the column content at."""
    H = a.shape[1] if False else a.shape[0]
    sub = a[:, x0:x1]
    colink = sub.sum(axis=0)
    for x in range(min(60, x1 - x0)):
        if colink[x] > 0.4 * H:                        # a tall rule
            e = x
            while e < x1 - x0 and colink[e] > 0.1 * H: e += 1
            return x0 + e + 2
    return x0

def strip_bands(strip):
    """The stacked strip's reading-order bands — one per page column, top→bottom. Filtered the same way
    `strip_to_native` filters (height > 10) so a band index means the same thing on both sides."""
    import note_region as _NR
    return [b for b in _NR._column_bands(strip) if b[1] - b[0] > 10]

def _band_notes(a, by0, by1, profile):
    """Note-starts and their line-bands within ONE stacked-strip band (= one page column), at full width.
    Returns (ins, pre, notes); `notes` is [(start_y, [(y0,y1) lines])] in ABSOLUTE strip y, and `pre` is
    the lines before this band's first start — a stitch tail carried over from the previous band."""
    nd = (profile.get("compositor_conventions") or {}).get("note_start_detection") or {}
    mw, gm, mt = nd.get("marker_max_width", 32), nd.get("gap_min", 3), nd.get("min_text", 25)
    full = a[by0:by1]
    # the left inset is computed WITHIN the band: a column-rule remnant spans this band's height, not the
    # whole strip's, so a strip-height threshold would never fire on it
    ins = _left_inset(full, 0, full.shape[1])
    sub = full[:, ins:]
    lines = _text_lines(sub)
    starts = set(y0 for (y0, y1) in lines if _is_note_start(sub[y0:y1], mw, gm, mt))
    notes, pre = [], []
    cur = None
    for (y0, y1) in lines:
        ay0, ay1 = y0 + by0, y1 + by0
        if y0 in starts:
            if cur is not None: notes.append(cur)
            cur = (ay0, [(ay0, ay1)])
        else:
            (cur[1].append((ay0, ay1)) if cur is not None else pre.append((ay0, ay1)))
    if cur is not None: notes.append(cur)
    return ins, pre, notes

def note_line_regions(band, n_notes, profile):
    """Map notes 0..n_notes-1 to {col, x0, x1, ins, lines, segments}. Returns (regions|None, status). Gate:
    total detected note-starts must equal n_notes; else abstain the page with a count-mismatch/stitch
    status. Box x-bounds follow the RATIFIED convention — full strip width — while `ins` is the content
    inset used for line analysis and the marker search."""
    Wd = band.width
    a = np.asarray(band.convert("L")) < INK
    spans = [(str(i), y0, y1) for i, (y0, y1) in enumerate(strip_bands(band))] or [("0", 0, band.height)]
    ordered, stitched = [], False
    x0, x1 = 0, Wd - 2
    for name, by0, by1 in spans:
        ins, pre, notes = _band_notes(a, by0, by1, profile)
        if pre and ordered:                            # lines before this band's first start = stitch tail
            # SEGMENTS, not a flat line list. The stitch tail lives in THIS band, which maps to a different
            # native page origin than the previous band — so it must stay a separate rectangle all the way
            # down. A stitched note is two rects, never one spanning box, and that has to hold in band
            # coordinates too, not only after strip_to_native un-stacks it.
            ordered[-1]["segments"].append(dict(col=name, x0=x0, x1=x1, ins=ins, lines=list(pre)))
            ordered[-1]["lines"].extend((y0, y1) for y0, y1 in pre); stitched = True
        elif pre:
            stitched = True                            # stitch tail with no prior note -> flag
        for (sy, lns) in notes:
            ordered.append(dict(col=name, x0=x0, x1=x1, ins=ins, lines=lns,
                                segments=[dict(col=name, x0=x0, x1=x1, ins=ins, lines=lns)]))
    if len(ordered) != n_notes:
        return None, f"count-mismatch:detected={len(ordered)},extractor={n_notes}" + (";stitch" if stitched else "")
    return ordered, "ok"

def hebrew_line(band, region, run_text):
    """Walk the note's lines to the one holding the Hebrew token, and return (line_crop, (y0,y1)) column-
    bounded, or (None, status). The offset is the count of word-producing tokens before the Hebrew run;
    each line's word-boxes are subtracted until it lands. The marker is stripped only on the FIRST line."""
    toks = W.tokenize(run_text)
    run = W._hebrew_run(toks)
    if run is None: return None, "no-hebrew"
    if run == "split": return None, "hebrew-not-contiguous"
    lo, _ = run
    offset = sum(1 for s, _ in toks[:lo] if s in ("latin", "greek", "hebrew"))
    first = True
    for seg in region.get("segments") or [region]:
        for (y0, y1) in seg["lines"]:
            crop = band.crop((seg["ins"], y0, seg["x1"], y1))
            wb = W.word_boxes(crop)
            if first:
                wb = W.strip_marker(wb, y1 - y0)       # the marker is on the note's first line only
            first = False
            if offset < len(wb):
                return crop, (y0, y1, seg["ins"])      # ins travels with the line: a stitch tail sits in the
            offset -= len(wb)                          # other column, so the fold-back x differs per segment
    return None, "offset-overflow"

def locate_span(band, note_idx, run_text, n_notes, profile, confidence=(0.75, 2.5)):
    """Full flow: map the page (gated), find the Hebrew's line for note_idx, locate. Returns (box|None,
    status) where box is in BAND coords (line-crop x/y offsets folded back in)."""
    regions, st = note_line_regions(band, n_notes, profile)
    if regions is None: return None, "page-abstain:" + st
    if not (0 <= note_idx < len(regions)): return None, "note-idx-oob"
    reg = regions[note_idx]
    line, info = hebrew_line(band, reg, run_text)
    if line is None: return None, info
    y0, y1, ins = info
    box, lst = W.locate_hebrew(line, run_text, confidence=confidence)
    if box is None: return None, lst
    return (box[0] + ins, box[1] + y0, box[2] + ins, box[3] + y0), "ok"
