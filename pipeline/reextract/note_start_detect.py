"""Note-start detector v2 (config-v2) — PER-COLUMN, marker by the body-side filter, count as the gate.

The v1 hanging_indent signature ("narrow first ink-run, then a gap, then text") over-fires: a continuation
line whose first word is short (`nus,`) mimics marker-plus-gap and reads as a false start. The fix is the
body-side marker filter (cv_superscript_detect's cut-2 spec): a real marker is an ISOLATED, RAISED,
SUB-X-HEIGHT floating island — a continuation word's first letter is attached to its word and sits ON the
baseline. So a line opens a note iff its leftmost ink component is (a) raised: bottom above the line
baseline, (b) small: height under the x-height, (c) isolated: a whitespace gap after it before the text.

Run PER COLUMN (detect the gutter, split, detect each column, left then right = reading order). The count is
the GATE, never loosened: detected starts must equal the extractor's note count, else abstain the page.
Marker letter-reading is a CONFIRMATION check elsewhere, never a source of a start here."""
import numpy as np
from hanging_indent import _text_lines

INK = 110

def _line_geom(band):
    """(baseline_row, x_height_px) for one line's ink mask. baseline = lowest dense row; x-height = height
    of the dense body (rows carrying >= 0.5x the peak row-ink)."""
    rowink = band.sum(axis=1)
    if rowink.max() == 0:
        return band.shape[0] - 1, band.shape[0]
    dense = np.where(rowink >= 0.5 * rowink.max())[0]
    baseline = int(dense[-1]) if len(dense) else band.shape[0] - 1
    xh = int(dense[-1] - dense[0] + 1) if len(dense) else band.shape[0]
    return baseline, max(1, xh)

def _leftmost_component(band, min_area=4):
    """Bounding box (x0,y0,x1,y1) of the leftmost ink connected-component, or None. BFS, small enough for
    a single line band."""
    from collections import deque
    H, W = band.shape
    cols = np.where(band.any(axis=0))[0]
    if len(cols) == 0:
        return None
    seen = np.zeros_like(band, bool)
    x_start = cols[0]
    # seed from the leftmost inked column, all its inked rows
    best = None
    for y in np.where(band[:, x_start])[0]:
        if seen[y, x_start]:
            continue
        q = deque([(y, x_start)]); seen[y, x_start] = True
        xs0 = xs1 = x_start; ys0 = ys1 = y; area = 0
        while q:
            cy, cx = q.popleft(); area += 1
            xs0, xs1, ys0, ys1 = min(xs0, cx), max(xs1, cx), min(ys0, cy), max(ys1, cy)
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < H and 0 <= nx < W and band[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True; q.append((ny, nx))
        if area >= min_area and (best is None or xs0 < best[0]):
            best = (xs0, ys0, xs1 + 1, ys1 + 1)
    return best

def _left_inset(col_ink):
    """x to start column content at, past a leftmost column-rule fragment (a narrow band spanning most of
    the height)."""
    H = col_ink.shape[0]
    colink = col_ink.sum(axis=0)
    x = 0
    while x < min(60, col_ink.shape[1]) and colink[x] > 0.4 * H:
        x += 1
    if x:                                              # a rule was found; skip it and the gap after
        while x < min(60, col_ink.shape[1]) and colink[x] <= 0.1 * H:
            x += 1
    return x

def line_opens_note(band, raised_frac=0.25, max_h_frac=1.15, gap_min=3, marker_max_w=34, min_text=25):
    # RAISED is the workhorse discriminator (a continuation word's first letter sits on the baseline); the
    # height cap only rejects a full ascender, since Gill's markers are raised lowercase letters ~= x-height.
    """True iff the line's ink mask opens with an isolated, raised, small marker then a gap then text."""
    if band.any(axis=0).sum() < min_text:
        return False
    baseline, xh = _line_geom(band)
    comp = _leftmost_component(band)
    if comp is None:
        return False
    x0, y0, x1, y1 = comp
    if (x1 - x0) > marker_max_w:                        # wide first run -> running text, not a marker
        return False
    if (y1 - y0) > max_h_frac * xh:                     # tall -> a full letter on the baseline, not a marker
        return False
    if y1 > baseline - raised_frac * xh:                # bottom reaches the baseline -> not raised
        return False
    col = band.any(axis=0)                              # isolation: whitespace gap after the marker
    g = x1
    while g < len(col) and not col[g]:
        g += 1
    if (g - x1) < gap_min:
        return False
    return col[g:].sum() >= min_text

def column_starts(col_ink, **kw):
    """y0 of each note-start line in a column ink mask, top→bottom."""
    return [y0 for (y0, y1) in _text_lines(col_ink) if line_opens_note(col_ink[y0:y1], **kw)]

def detect_gutter(strip):
    a = np.asarray(strip.convert("L")) < INK
    Wd = a.shape[1]; col = a.sum(axis=0)
    lo, hi = int(Wd * 0.38), int(Wd * 0.62)
    if hi <= lo:
        return None
    x = lo + int(np.argmin(col[lo:hi]))
    return x if col[x] < 0.15 * (col.max() or 1) else None

def page_starts(strip, profile=None):
    """All note-starts in reading order as (col, x0, x1, y0). Per column: left then right."""
    a = np.asarray(strip.convert("L")) < INK
    gut = detect_gutter(strip)
    spans = [("L", 0, gut), ("R", gut, strip.width)] if gut else [("F", 0, strip.width)]
    out = []
    for name, cx0, cx1 in spans:
        col = a[:, cx0:cx1]
        ins = _left_inset(col)
        for y0 in column_starts(col[:, ins:]):
            out.append((name, cx0 + ins, cx1, y0))
    return out
