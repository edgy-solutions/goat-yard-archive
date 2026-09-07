"""nikud_gate born-tested. The detector is deterministic geometry, so the fixtures are constructed crops:
a consonantal line = vertical bars in one band; a pointed line = the same bars with a dot BELOW each
(where real nikud sit). The gate must strip only the confidently-unpointed and KEEP everything else, so
Gill's genuinely-pointed pages survive. Run: python test_nikud_gate.py"""
import numpy as np
from PIL import Image
import nikud_gate as NG

def _crop(pointed):
    """A synthetic Hebrew line: 6 consonant bars in the main band; if pointed, a dot under each bar."""
    a = np.zeros((60, 240), dtype=np.uint8)
    for k in range(6):
        x = 20 + k * 36
        a[10:38, x:x + 16] = 255              # consonant body (main band)
        if pointed:
            a[46:52, x + 5:x + 11] = 255      # a vowel dot below the baseline
    return Image.fromarray(255 - a)           # ink = dark

def test_strip_is_exact():
    assert NG.strip_nikud("שְׂרֵי מַקְנָה") == "שרי מקנה"
    assert NG.strip_nikud("שרי מקנה") == "שרי מקנה"      # no-op when already bare
    assert NG.strip_nikud("") == ""

def test_unpointed_detected():
    v, d = NG.is_pointed(_crop(pointed=False))
    assert v == "unpointed", (v, d)

def test_pointed_kept():
    v, d = NG.is_pointed(_crop(pointed=True))
    assert v == "pointed", (v, d)                         # dot-under-every-letter reads as pointed

def test_gate_strips_only_unpointed():
    txt = "שְׂרֵי מַקְנָה"
    out, v, d = NG.gated_strip(txt, _crop(pointed=False))
    assert out == "שרי מקנה" and v == "unpointed"         # spurious nikud on an unpointed crop -> stripped
    out2, v2, d2 = NG.gated_strip(txt, _crop(pointed=True))
    assert out2 == txt and v2 == "pointed"                # genuinely pointed -> KEPT (Gill's argument survives)

def test_uncertain_keeps():
    # a faint/ambiguous crop must NOT be stripped — err toward keeping the points
    a = np.zeros((60, 240), dtype=np.uint8)
    for k in range(6):
        x = 20 + k * 36; a[10:38, x:x + 16] = 255
        if k < 2: a[46:52, x + 5:x + 11] = 255            # dots under only 2 of 6 -> between thresholds
    out, v, d = NG.gated_strip("שְׂרֵי", Image.fromarray(255 - a))
    assert v == "uncertain" and out == "שְׂרֵי", (v, d)   # uncertain -> keep

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed"); raise SystemExit(1 if f else 0)
