"""note_start_detect born-tested — the unit pieces (rule removal, line splitting, marker isolation) on
constructed masks, plus a fixture regression bound. Run: python test_note_start_detect.py"""
import numpy as np
from PIL import Image
import note_start_detect as NS

def _img(mask):
    return Image.fromarray(np.where(mask, 0, 255).astype(np.uint8))

def test_strip_vrules_removes_partial_height_rule():
    a = np.zeros((400, 200), bool)
    a[200:400, 30:33] = True                 # a rule spanning only the bottom half (the stacked-column case)
    a[100:130, 80:120] = True                # some text
    out = NS.strip_vrules(a)
    assert not out[200:400, 30:33].any(), "partial-height rule not removed"
    assert out[100:130, 80:120].any(), "text wrongly removed"

def test_text_lines_splits_merged_band():
    a = np.zeros((120, 300), bool)
    for cy in (20, 60, 100):                  # three text lines, small gaps -> _text_lines fuses them
        a[cy - 8:cy + 8, 20:280] = True
    lines = NS.text_lines(a)
    assert len(lines) >= 3, (len(lines), "merged band not split into its lines")

def test_text_lines_min_sep_frac_default_unchanged_and_separates_double_minimum_valley():
    """A merged 3-line band (plus three clean 30px single-line bands elsewhere, to anchor the
    median at 30) whose FIRST inter-line valley has two close local minima 12 rows apart (prof 15
    at row 21, prof 12 at row 33 -- mirrors the p402 measurement of two minima of one inter-line
    valley 12 rows apart) both deeper than the second valley's single minimum (prof 35 at row 63).

    Default (min_sep_frac=None): documents TODAY's behaviour -- the two globally-deepest rows (33,
    21) both come from the FIRST valley, starving the real second-valley cut and leaving a 57-row
    merged remainder (lines 2+3 never separated). This is the CAUSE A bug, held fixed here so a
    change to the default is caught.

    min_sep_frac=0.5 (med=30 -> 15-row minimum separation): row 21 is only 12 rows from the
    already-accepted row 33, so it is rejected and the real second-valley cut (row 63) is used
    instead, yielding three bands close to the true ~30px line pitch."""
    W, H = 300, 270
    ink = np.zeros((H, W), bool)

    def setrow(y, c):
        ink[y, 20:20 + c] = True

    for y in range(0, 18):
        setrow(y, 260)                        # line1 body
    valley_a = {18: 180, 19: 140, 20: 100, 21: 15, 22: 70, 23: 90, 24: 95, 25: 95, 26: 90,
                27: 90, 28: 80, 29: 70, 30: 60, 31: 50, 32: 45, 33: 12, 34: 60, 35: 120,
                36: 180, 37: 230}
    for y, c in valley_a.items():
        setrow(y, c)
    for y in range(38, 56):
        setrow(y, 260)                        # line2 body
    valley_b = {56: 220, 57: 180, 58: 140, 59: 100, 60: 70, 61: 50, 62: 40, 63: 35, 64: 45,
                65: 70, 66: 100, 67: 140, 68: 180, 69: 210, 70: 240, 71: 255}
    for y, c in valley_b.items():
        setrow(y, c)
    for y in range(72, 90):
        setrow(y, 260)                        # line3 body
    for y0 in (120, 180, 240):                # three clean, isolated 30px single-line bands
        for y in range(y0, y0 + 30):
            setrow(y, 260)

    default_out = NS.text_lines(ink)
    assert default_out[:3] == [(0, 21), (21, 33), (33, 90)], \
        ("current default behaviour changed", default_out[:3])

    sep_out = NS.text_lines(ink, min_sep_frac=0.5)
    sep_heights = [y1 - y0 for (y0, y1) in sep_out[:3]]
    assert sep_out[:3] == [(0, 33), (33, 63), (63, 90)], ("min_sep_frac split wrong", sep_out[:3])
    assert all(20 <= h <= 40 for h in sep_heights), \
        (sep_heights, "min_sep_frac bands should be ~1 line tall, not a sliver or a merged pair")

def test_text_lines_line_h_keyword_default_byte_identical():
    # Same merged 3-line band as test_text_lines_splits_merged_band: line_h=None (the default, not
    # passed at all) must be byte-identical to calling with no line_h keyword -- this is the
    # substrate-change contract (verse_regions' choose_line_h/analyze_page_s1 pass line_h
    # explicitly only for a collapsed column; every other caller must see no change at all).
    a = np.zeros((120, 300), bool)
    for cy in (20, 60, 100):
        a[cy - 8:cy + 8, 20:280] = True
    assert NS.text_lines(a) == NS.text_lines(a, line_h=None)

    # line_h, when GIVEN, drives the split instead of the column's own median: a band tall enough
    # relative to an explicit (small) line_h must be split even though it would NOT be split
    # against its own (large) median -- proving line_h, not med, is what decided it. Two shallow
    # valleys (one local minimum each) give the split something to cut at.
    b = np.zeros((60, 300), bool)

    def setrow(y, c):
        b[y, 20:20 + c] = True

    for y in range(0, 16):
        setrow(y, 260)
    for y, c in zip(range(16, 21), (180, 90, 30, 90, 180)):
        setrow(y, c)
    for y in range(21, 38):
        setrow(y, 260)
    for y, c in zip(range(38, 43), (180, 90, 30, 90, 180)):
        setrow(y, c)
    for y in range(43, 60):
        setrow(y, 260)

    assert NS.text_lines(b) == [(0, 60)], "own-median split: a single 60px band has med=60, n=1, no split"
    split = NS.text_lines(b, line_h=20)      # against line_h=20, h=60 -> n=3, 1.5x test fires
    assert len(split) == 3, split

def test_marker_opens_continuation_does_not():
    # marker line: a small RAISED isolated glyph, a gap, then text
    m = np.zeros((44, 400), bool)
    m[6:20, 20:34] = True                     # raised marker (top of line), narrow
    m[16:40, 70:380] = True                   # text after a gap, full x-height to baseline
    assert NS.line_opens_note(m)
    # continuation line: a word at the left (first letter reaches the baseline, no gap after it)
    c = np.zeros((44, 400), bool)
    c[16:40, 20:360] = True                   # running text from the left edge, baseline-height
    assert not NS.line_opens_note(c)

def test_fixture_regression():
    import os, sys
    sys.path.insert(0, "../scripts")
    import cv_footnote_presplit as ps
    IMG = "C:/Users/cnogr/git/dr-voluminous/commentary/volume1"
    if not os.path.exists(IMG):
        print("  (skip fixtures: scans not present)"); return
    EXPECT = {129: 13, 146: 13, 163: 18, 226: 20, 393: 8, 625: 3, 725: 9, 784: 7}
    tot = 0
    for pg, exp in EXPECT.items():
        strip, _ = ps.presplit(f"{IMG}/page{pg}_image1.png", upscale=1)
        tot += abs(len(NS.page_starts(strip)) - exp)
    mae = tot / len(EXPECT)
    assert mae <= 2.5, f"fixture mean abs err regressed to {mae:.2f} (was ~2.0)"

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed"); raise SystemExit(1 if f else 0)
