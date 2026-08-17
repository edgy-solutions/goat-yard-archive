"""HANGING-INDENT note-start detector — deterministic CV segmentation, attacking the dominant
failure class (segmentation-collapse, the many->one folds) at the INPUT layer instead of asking the
transcriber to notice typography (constrain-direction / deterministic-property-not-a-model).

The 1766 compositor's convention (read off the page by Chris): each footnote begins with a narrow
SUPERSCRIPT marker glyph, then a whitespace GAP, then the note text; continuation lines flow without
that marker+gap signature (even full-width wraps start with running text, not a marker+gap). So a
note-start is detectable per text-line by one local pattern — a narrow first ink-run followed by a
gap — which needs no column model and survives the presplit's block rearrangement.

count_notes(strip) -> (n_starts, [y positions]). Book-scoped thresholds live in book_profile
(compositor_conventions.note_layout). Born-tested against the 8 collapse fixtures (known counts).
"""
import numpy as np

def _text_lines(ink):
    """Contiguous inked row-bands = text lines. ink is a boolean HxW mask."""
    rowink = ink.sum(axis=1)
    if rowink.max() == 0: return []
    thr = max(2, rowink.max() * 0.02)
    lines, y, H = [], 0, ink.shape[0]
    while y < H:
        if rowink[y] > thr:
            y0 = y
            while y < H and rowink[y] > thr: y += 1
            if y - y0 >= 4: lines.append((y0, y))   # ignore rule-thin bands
        else:
            y += 1
    return lines

def _is_note_start(band, marker_w, gap_min, min_text):
    """band = ink mask for one text line. True iff it opens with a NARROW glyph (the marker) then a
    GAP then more ink (the text) — the hanging-indent signature. Flowing text / full-width wraps
    open with a wide first run or no gap, so they read False."""
    col = band.any(axis=0)
    xs = np.where(col)[0]
    if len(xs) < min_text: return False
    x0 = xs[0]
    e = x0
    while e < len(col) and col[e]: e += 1          # first ink run = candidate marker
    if (e - x0) > marker_w: return False            # too wide -> running text, not a marker
    g = e
    while g < len(col) and not col[g]: g += 1       # whitespace gap after the marker
    if (g - e) < gap_min: return False              # no indent gap -> not a marker+indent
    return col[g:].sum() >= min_text                # real text follows the gap

def count_notes(strip, marker_w=32, gap_min=3, min_text=25, ink_thresh=110):
    """DETERMINISTIC footnote counter from the compositor's hanging indent. Returns
    (count, [y0 of each note-start], confident). count = number of note-start lines (marker-column
    lines) — the compositor encoded the count in the left edge; this reads it off, no model involved.

    `confident` is False when the strip lacks the expected hanging-indent structure — no note-start
    detected at all (full-width notes / p546 class / ambiguous geometry). Per Chris's honesty caveat:
    FLAG the ambiguous strip (route it) rather than forcing a count. A count without confidence is a
    reroute signal, not a number to trust. (Slight undercount where tight spacing merges a note with
    its wrap is safe — it never collapses toward 1, the signal that matters.)"""
    a = np.asarray(strip.convert("L")) < ink_thresh
    lines = _text_lines(a)
    starts = [y0 for (y0, y1) in lines if _is_note_start(a[y0:y1], marker_w, gap_min, min_text)]
    confident = len(lines) >= 2 and len(starts) >= 1     # structure present -> trust the count
    return len(starts), starts, confident

def count_notes_for(strip, profile):
    """count_notes with thresholds read from the book profile (compositor_conventions), not hardcoded —
    so a second book supplies its own printer's geometry. Falls back to the tuned Gill defaults."""
    nd = (profile.get("compositor_conventions") or {}).get("note_start_detection") or {}
    return count_notes(strip, marker_w=nd.get("marker_max_width", 32),
                       gap_min=nd.get("gap_min", 3), min_text=nd.get("min_text", 25))

if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import cv_footnote_presplit as ps
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    IMG = "c:/Users/cnogr/git/dr-voluminous/commentary/volume1"
    EXPECT = {129: 13, 146: 13, 163: 18, 226: 20, 393: 8, 625: 3, 725: 9, 784: 7}
    print(f"{'page':>5} {'expect':>7} {'detect':>7}  {'err':>4}")
    tot_err = 0
    for pg, exp in EXPECT.items():
        strip, _ = ps.presplit(f"{IMG}/page{pg}_image1.png", upscale=1)
        n, _ys, _c = count_notes(strip)
        err = n - exp; tot_err += abs(err)
        print(f"{pg:>5} {exp:>7} {n:>7}  {err:>+4}")
    print(f"\ntotal abs error over 8 fixtures: {tot_err}")
