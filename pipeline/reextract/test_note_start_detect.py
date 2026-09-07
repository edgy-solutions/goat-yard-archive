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
