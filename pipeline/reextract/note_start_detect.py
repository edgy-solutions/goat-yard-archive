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

def _longest_run(colmask):
    """Longest contiguous run of True in a 1-D bool array."""
    best = cur = 0
    for v in colmask:
        cur = cur + 1 if v else 0
        if cur > best:
            best = cur
    return best

def strip_vrules(a, min_run=60, max_w=6):
    """Blank vertical rule-lines — by LONGEST CONTIGUOUS vertical ink run, not fraction of total height. A
    rule is a thin column with a long unbroken vertical segment (>> a letter's ~30px); keying on total
    fraction misses a rule that spans only PART of the strip, e.g. the second stacked column's own border
    (which reaches only the bottom half). Such rules (a) bridge inter-line gaps so lines can't separate and
    (b) become the leftmost ink and defeat the raised-marker/floating test. Returns a cleaned copy."""
    H = a.shape[0]
    runs = np.array([_longest_run(a[:, x]) for x in range(a.shape[1])])
    tall = runs > min_run
    out = a.copy()
    x = 0
    while x < a.shape[1]:
        if tall[x]:
            e = x
            while e < a.shape[1] and tall[e]:
                e += 1
            if e - x <= max_w:                         # a thin rule (not a genuine wide ink block)
                out[:, x:e] = False
            x = e
        else:
            x += 1
    return out

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

def line_opens_note(band, raised_frac=0.25, gap_min=3, marker_max_w=42, min_text=25):
    """True iff the line opens with a note marker, by RAISED-BAND PROJECTION (robust where the marker touches
    the text letter beneath it, which defeats connected-components). A marker is: ink in the raised band
    (above baseline - raised_frac*x-height) whose columns are FLOATING — they carry no ink at the baseline
    (an ascender's columns reach the baseline; a marker's don't) — narrow, isolated by a gap, text after.
    That is the continuation-vs-marker discriminator: a continuation's leading ascender reaches the baseline;
    only a true marker floats."""
    col = band.any(axis=0)
    if col.sum() < min_text:
        return False
    baseline, xh = _line_geom(band)
    cut = int(baseline - raised_frac * xh)             # marker ink lives above this row
    if cut <= 0:
        return False
    rcol = band[:cut].any(axis=0)
    xs = np.where(rcol)[0]
    if len(xs) == 0:
        return False
    xm0 = int(xs[0]); e = xm0
    while e < len(rcol) and rcol[e]:
        e += 1
    if (e - xm0) > marker_max_w:                        # too wide -> a word's ascenders, not a marker
        return False
    g = e                                              # ISOLATION in the FULL line: a gap right after the
    while g < len(col) and not col[g]:                 # marker. This is the real discriminator — a marker
        g += 1                                         # is `c` then a gap then text; a continuation word's
    if (g - e) < gap_min:                              # first letter (`are`) is followed immediately by the
        return False                                   # rest of the word (no gap), and its letters connect
    return bool(col[g:].sum() >= min_text)             # in the full line. (Floating/reaches-baseline was too
                                                       # strict — it rejected low-sitting markers like `c`.)

def text_lines(ink):
    """Text lines with tall (merged multi-line) bands SPLIT at internal ink valleys. _text_lines groups
    rows on a global threshold, so densely-set apparatus lines fuse; a merged band then breaks the per-line
    baseline/x-height geometry the marker test needs. So: take the raw bands, estimate the single-line
    height from their median, and split any band taller than 1.5x that at its rowink minima."""
    raw = _text_lines(ink)
    if not raw:
        return raw
    heights = sorted(h for (y0, y1) in raw for h in [y1 - y0])
    med = heights[len(heights) // 2]
    out = []
    for (y0, y1) in raw:
        h = y1 - y0
        n = int(round(h / med)) if med else 1
        if n <= 1 or h < 1.5 * med:
            out.append((y0, y1)); continue
        prof = ink[y0:y1].sum(axis=1).astype(float)    # split at the n-1 deepest interior valleys
        lo, hi = int(0.4 * med), h - int(0.4 * med)
        cand = [i for i in range(lo, hi) if prof[i] <= prof[i - 1] and prof[i] < prof[i + 1]]
        cand.sort(key=lambda i: prof[i])
        cuts = sorted(cand[:n - 1])
        prev = 0
        for c in cuts:
            out.append((y0 + prev, y0 + c)); prev = c
        out.append((y0 + prev, y1))
    return out

def column_starts(col_ink, **kw):
    """y0 of each note-start line in a column ink mask, top→bottom."""
    return [y0 for (y0, y1) in text_lines(col_ink) if line_opens_note(col_ink[y0:y1], **kw)]

def detect_gutter(strip):
    a = np.asarray(strip.convert("L")) < INK
    Wd = a.shape[1]; col = a.sum(axis=0)
    lo, hi = int(Wd * 0.38), int(Wd * 0.62)
    if hi <= lo:
        return None
    x = lo + int(np.argmin(col[lo:hi]))
    return x if col[x] < 0.15 * (col.max() or 1) else None

def page_starts(strip, profile=None):
    """All note-starts in reading order as (x0, y0). NOTE: cv_footnote_presplit already VERTICALLY CONCATS
    the two columns (left strip above right strip, 20px gap) into one single-column strip in linear reading
    order — so there is NO side-by-side gutter to split; the 20px gaps separate the columns in the line
    projection. Run detection on the whole strip. Vertical rules removed first; left margin inset once."""
    a = strip_vrules(np.asarray(strip.convert("L")) < INK)
    ins = _left_inset(a)
    ys = column_starts(a[:, ins:], **(_kw(profile)))
    return [(ins, y) for y in _dedupe_slivers(ys)]

def _dedupe_slivers(ys, min_note_h=20):
    """STRUCTURAL guard (a bug, not a threshold): two note-starts cannot be only a few pixels apart — a note
    is at least a line tall. Collapse a run of starts closer than min_note_h to the first. Kills the sliver
    class a small-strip over-split produces, without touching any real start (which is ≥ a line apart)."""
    out = []
    for y in sorted(ys):
        if not out or y - out[-1] >= min_note_h:
            out.append(y)
    return out

def _kw(profile):
    if not profile:
        return {}
    nd = (profile.get("compositor_conventions") or {}).get("note_start_detection") or {}
    return {}                                          # profile thresholds are pixel-tuned for v1; v2 geometry knobs are its own
