"""hanging_indent born tested — a synthetic strip with known marker+gap note-starts (scale-independent
unit), plus the 8 collapse fixtures at honest tolerance (never collapses to ~1; tracks the count as a
segmentation prior). Run: python test_hanging_indent.py"""
import numpy as np
from PIL import Image
import hanging_indent as hi

def _synthetic():
    """Build a strip: 3 note-starts (narrow marker + gap + text) and 2 flowing continuations."""
    H, W = 300, 400
    a = np.full((H, W), 255, np.uint8)
    def textblock(y, x0, x1): a[y+8:y+34, x0:x1] = 0            # a run of "text" ink
    def marker(y, x): a[y+2:y+18, x:x+12] = 0                    # narrow superscript marker
    rows = [12, 70, 128, 186, 244]
    # note-starts: marker at ~12, gap, text from ~60
    for r in (rows[0], rows[2], rows[4]):
        marker(r, 12); textblock(r, 60, 380)
    # continuations: flowing text from the left, no marker+gap
    for r in (rows[1], rows[3]):
        textblock(r, 12, 380)
    return Image.fromarray(a)

def test_synthetic_counts_markers_only():
    n, ys, conf = hi.count_notes(_synthetic())
    assert n == 3, f"expected 3 note-starts, got {n} ({ys})"
    assert conf is True                                    # clear hanging-indent structure

def test_synthetic_deterministic():
    s = _synthetic()
    assert hi.count_notes(s)[0] == hi.count_notes(s)[0]

def test_continuation_not_flagged():
    # a single flowing line (no marker+gap) must not read as a note-start, and is NOT confident
    a = np.full((60, 400), 255, np.uint8); a[20:46, 12:380] = 0
    n, _, conf = hi.count_notes(Image.fromarray(a))
    assert n == 0 and conf is False                        # no structure -> flag, don't force a count

def test_fixtures_never_collapse_and_track_count():
    """The 8 many->one fixtures: detector must never collapse (>=3) and land within tolerance of the
    true count (a prior, not exact truth). Skips if the scans aren't present."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    IMG = Path("c:/Users/cnogr/git/dr-voluminous/commentary/volume1")
    if not (IMG / "page226_image1.png").exists(): return
    import cv_footnote_presplit as ps
    EXPECT = {129: 13, 146: 13, 163: 18, 226: 20, 393: 8, 625: 3, 725: 9, 784: 7}
    for pg, exp in EXPECT.items():
        strip, _ = ps.presplit(str(IMG / f"page{pg}_image1.png"), upscale=1)
        n, _, conf = hi.count_notes(strip)
        assert conf is True, f"p{pg}: not confident"                   # structure present on all fixtures
        assert n >= 3, f"p{pg}: collapsed ({n})"                       # the signal that matters
        tol = max(4, round(0.35 * exp))
        assert abs(n - exp) <= tol, f"p{pg}: {n} vs {exp} (tol {tol})"  # tracks the count

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed"); raise SystemExit(1 if f else 0)
