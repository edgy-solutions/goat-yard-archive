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

COLUMN BOUNDING = READING ORDER. Detect the apparatus gutter, segment lines PER COLUMN, match order per
column: left column's notes top-to-bottom, then right column's. A note that starts at the bottom of the left
column and continues at the top of the right is the STITCH case; the per-column count gate catches it.

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

def _column_notes(band, x0, x1, profile):
    """Note-starts and their line-bands for one column, in reading (top→bottom) order. Returns a list of
    (start_y, [(y0,y1) lines]) — one entry per detected note-start; trailing lines before the first start
    (a stitch continuation from the previous column) are attached to a leading None-start entry."""
    nd = (profile.get("compositor_conventions") or {}).get("note_start_detection") or {}
    mw, gm, mt = nd.get("marker_max_width", 32), nd.get("gap_min", 3), nd.get("min_text", 25)
    a = np.asarray(band.convert("L")) < INK
    ins = _left_inset(a, x0, x1)
    sub = a[:, ins:x1]
    lines = _text_lines(sub)
    starts = set(y0 for (y0, y1) in lines if _is_note_start(sub[y0:y1], mw, gm, mt))
    notes, pre = [], []
    cur = None
    for (y0, y1) in lines:
        if y0 in starts:
            if cur is not None: notes.append(cur)
            cur = (y0, [(y0, y1)])
        else:
            (cur[1].append((y0, y1)) if cur is not None else pre.append((y0, y1)))
    if cur is not None: notes.append(cur)
    return ins, pre, notes

def note_line_regions(band, n_notes, profile):
    """Map notes 0..n_notes-1 to {col, x0, x1, ins, lines}. Returns (regions|None, status). Gate: total
    detected note-starts must equal n_notes; else abstain the page with a count-mismatch/stitch status."""
    gut = detect_gutter(band)
    Wd = band.width
    spans = [("L", 0, gut)] if gut else [("F", 0, Wd)]
    if gut:
        spans.append(("R", gut, Wd))
    ordered, stitched = [], False
    for name, x0, x1 in spans:
        ins, pre, notes = _column_notes(band, x0, x1, profile)
        if pre and ordered:                            # lines before this column's first start = stitch tail
            ordered[-1]["lines"].extend((y0, y1) for y0, y1 in pre); stitched = True
        elif pre:
            stitched = True                            # stitch tail with no prior note -> flag
        for (sy, lns) in notes:
            ordered.append(dict(col=name, x0=x0, x1=x1, ins=ins, lines=lns))
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
    for i, (y0, y1) in enumerate(region["lines"]):
        crop = band.crop((region["ins"], y0, region["x1"], y1))
        wb = W.word_boxes(crop)
        if i == 0:
            wb = W.strip_marker(wb, y1 - y0)
        if offset < len(wb):
            return crop, (y0, y1)
        offset -= len(wb)
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
    y0, y1 = info
    box, lst = W.locate_hebrew(line, run_text, confidence=confidence)
    if box is None: return None, lst
    return (box[0] + reg["ins"], box[1] + y0, box[2] + reg["ins"], box[3] + y0), "ok"
