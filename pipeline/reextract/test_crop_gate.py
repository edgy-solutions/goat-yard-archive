"""crop_gate born tested — the three verdicts + the p86 regression (real image if present).
Run: python test_crop_gate.py"""
import numpy as np
from PIL import Image
import crop_gate as G

def _blank(): return Image.new("L", (400, 300), 255)
def _inked(frac_rows=0.2):
    a = np.full((300, 400), 255, np.uint8); a[:int(300*frac_rows), :] = 0
    return Image.fromarray(a)

def test_blank_with_notes_is_fabrication():
    v, d = G.check(_blank(), 18)
    assert v == "fabrication_suspect" and d == 0.0

def test_blank_without_notes_is_no_apparatus():
    assert G.check(_blank(), 0)[0] == "no_apparatus"

def test_inked_is_ok():
    assert G.check(_inked(0.2), 18)[0] == "ok"

def test_inked_but_no_notes_is_miss_suspect():
    # INVERSE error: crop has ink, model returned nothing -> real apparatus possibly missed
    assert G.check(_inked(0.2), 0)[0] == "miss_suspect"

def test_gate_notes_miss_flags_but_keeps_empty():
    kept, st, flag = G.gate_notes(_inked(0.2), [])
    assert kept == [] and st == "MISS_SUSPECT" and flag and "missed" in flag["reason"]

def test_none_strip_treated_as_blank():
    assert G.check(None, 5)[0] == "fabrication_suspect"
    assert G.check(None, 0)[0] == "no_apparatus"

def test_floor_boundary():
    # a crop just under vs just over the floor
    assert G.check(_inked(0.005), 3)[0] == "fabrication_suspect"   # ~0.005 dark < 0.01
    assert G.check(_inked(0.05), 3)[0] == "ok"                      # ~0.05 dark > 0.01

def test_gate_notes_drops_and_flags():
    notes = [{"marker": f"[^{i}]"} for i in range(1, 19)]
    kept, st, flag = G.gate_notes(_blank(), notes)
    assert kept == [] and st == "FABRICATION_SUSPECT"
    assert flag and flag["n_dropped"] == 18

def test_gate_notes_passes_real():
    notes = [{"marker": "[^1]"}]
    kept, st, flag = G.gate_notes(_inked(0.2), notes)
    assert st == "ok" and kept == notes and flag is None

def test_p86_regression_if_present():
    # the discovering case: p86's presplit crop must gate as fabrication (skip if image absent)
    import sys; sys.path.insert(0, "../scripts"); sys.path.insert(0, ".")
    from pathlib import Path
    img = Path("c:/Users/cnogr/git/dr-voluminous/commentary/volume1/page86_image1.png")
    if not img.exists(): return
    import cv_footnote_presplit as ps
    strip, _ = ps.presplit(str(img), upscale=1)
    assert G.check(strip, 18)[0] == "fabrication_suspect", "p86 blank crop must gate as fabrication"

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed"); raise SystemExit(1 if f else 0)
