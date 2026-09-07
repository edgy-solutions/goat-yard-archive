"""glyph_count_tripwire born-tested — a dropped letter is a length shortfall between ink and string.
Fixtures are constructed crops: N well-separated bars = N letters. Run: python test_glyph_count_tripwire.py"""
import numpy as np
from PIL import Image
import glyph_count_tripwire as G

def _crop(n_glyphs, speck=False):
    """n_glyphs separated bars in one band; optional tiny speck (a stray point) that must be filtered."""
    a = np.zeros((60, 40 * n_glyphs + 40), dtype=np.uint8)
    for k in range(n_glyphs):
        x = 20 + k * 40
        a[12:44, x:x + 18] = 255
    if speck:
        a[50:53, 5:8] = 255                    # a 3x3 speck — below the letter-size floor, must be ignored
    return Image.fromarray(255 - a)

def test_letter_count_ignores_nikud_and_latin():
    assert G.letter_count("שְׂרֵי מַקְנָה") == 7          # שרי (3) + מקנה (4) consonants, nikud ignored
    assert G.letter_count("קנים nidos") == 4             # Latin ignored
    assert G.letter_count("") == 0

def test_count_glyphs_matches_bars():
    assert G.count_glyphs(_crop(4)) == 4
    assert G.count_glyphs(_crop(6)) == 6

def test_speck_is_filtered():
    assert G.count_glyphs(_crop(4, speck=True)) == 4      # the stray point doesn't count as a letter

def test_dropped_letter_flags_p138_case():
    # קנים (4 glyphs of ink) but the reader output לך (2 letters) -> GROSS shortfall -> FLAG
    flagged, g, n = G.tripwire(_crop(4), "לך")
    assert flagged and g == 4 and n == 2, (flagged, g, n)

def test_correct_length_passes():
    flagged, g, n = G.tripwire(_crop(4), "קנים")          # 4 glyphs, 4 letters -> no flag
    assert not flagged and g == 4 and n == 4

def test_realprint_overcount_does_not_false_flag():
    # THE real-print guard: the counter over-counts ~30% on 1766 print (a correct 11-letter word can
    # estimate ~14 glyphs). The ratio band must NOT flag it as a hallucinated addition.
    flagged, g, n = G.tripwire(_crop(14), "אחי יפת הגדול")  # 11 letters vs 14-glyph estimate
    assert not flagged, (flagged, g, n)                    # 11 > 0.55*14 and 11 < 1.7*14 -> in band

def test_single_letter_drop_is_the_named_limit():
    # the honest limit: a single-letter drop (4->3) is WITHIN the noise band, NOT caught here.
    # the reference-hypothesis stage carries this class; the glyph count is only the gross-drop net.
    flagged, g, n = G.tripwire(_crop(4), "קנם")            # 3 letters vs 4 glyphs -> 3 > 0.55*4=2.2
    assert not flagged, (flagged, g, n)

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed"); raise SystemExit(1 if f else 0)
