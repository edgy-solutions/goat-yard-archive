"""Glyph-count tripwire (config-v2 Hebrew layer) — a deterministic, non-Tesseract witness that checks a
property the reader shouldn't own: the number of letters. Connected components on an UNPOINTED Hebrew crop
≈ the letter count (not exact — ligatures and touching glyphs undercount, broken glyphs overcount — but a
one- or two-letter gap on a short word is a strong signal). A dropped letter is a length shortfall between
the ink in the crop and the string that came out (`לך` = 2 for `קנים` = 4). It is COMPLEMENTARY to the
reference-hypothesis stage: passage-scope catches same-length substitutions (`היה` for `סנה`), the glyph
count catches length shortfalls (`לך` for `קנים`) — each a class the other misses. Same shape as crop-hash
pinning: deterministic, checks a property against the pixels, flags rather than corrects.

Requires an unpointed crop (nikud would add components) — run it AFTER the gated nikud strip.

REAL-PRINT REALITY (validated on Gill crops, not synthetic): letters do NOT map 1:1 to connected
components — at scan resolution they FRAGMENT into strokes (an 11-letter word gave 31 components) and
occasionally MERGE. Column ink-runs are closer (14 for 11) but still over-count by ~30%. This noise is
comparable to a single dropped letter, so an EXACT count with a tight tolerance false-positives on correct
words. So the tripwire is a RATIO BAND, not an exact count: it reliably catches GROSS shortfalls (the
`לך`(2)-for-`קנים`(4) class — a ~2x drop clears any noise) and names its limit: single-letter drops need
per-font calibration of the run-to-letter ratio and are NOT caught here. That's fine — it's the secondary
net for the length-shortfall class; the reference-hypothesis stage carries the same-length substitutions.
A flag routes to the second reader, never a correction."""
import re
import numpy as np

def _cons(w):
    return re.sub(r"[^א-תךםןףץ]", "", w or "")

def letter_count(text):
    """Consonant count of the Hebrew in `text` (nikud/spacing/Latin ignored)."""
    return sum(len(_cons(w)) for w in re.findall(r"[֐-׿]+", text or ""))

def count_glyphs(crop, gap_min=2, min_run_w=4):
    """Estimate letters by COLUMN ink-runs — spans of ink-columns, merging internal gaps < gap_min, then
    keeping only runs ≥ min_run_w wide (drops specks and stray points). More robust than connected
    components, which fragment on real print. Over-counts ~30% on 1766 print, so use only via the ratio
    band, never as an exact letter count."""
    a = np.asarray(crop.convert("L")) < 128
    if a.sum() < 10 or a.mean() > 0.9:                    # empty or solid-black (bad crop) -> unusable
        return 0
    col = a.sum(axis=0) > 2
    runs, start, gap = [], None, 0
    for i, c in enumerate(col):
        if c:
            if start is None: start = i
            gap = 0
        elif start is not None:
            gap += 1
            if gap >= gap_min:
                runs.append((start, i - gap + 1)); start = None; gap = 0
    if start is not None:
        runs.append((start, len(col)))
    return sum(1 for s, e in runs if (e - s) >= min_run_w)

def tripwire(crop, text, lo=0.55, hi=1.7):
    """Flag when the letter count is grossly OUT OF BAND with the glyph estimate — letters < lo*glyphs
    (a drop) or > hi*glyphs (a hallucinated addition). The band absorbs the ~30% real-print over-count;
    only gross mismatches clear it. Returns (flagged, glyphs, letters). A false flag costs a gemma read."""
    g = count_glyphs(crop); n = letter_count(text)
    if g == 0 or n == 0:
        return (g != n, g, n)                             # one side empty, other not -> flag
    return (n < lo * g or n > hi * g, g, n)
