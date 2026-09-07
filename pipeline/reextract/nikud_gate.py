"""Gated nikud strip (config-v2 Hebrew layer) — the model points unpointed consonantal text (~16% of
Hebrew spans carry nikud, ~70%+ of it model-added). Stripping recovers the exact page reading. But Gill
ARGUES FROM the vowel points in places (he published a dissertation defending their antiquity), so a
GLOBAL strip would delete the argument. So the strip is GATED per-span by a deterministic pointed-crop
detector, and it errs SAFE: strip only when the crop is CONFIDENTLY unpointed; on any doubt, KEEP the
points (the cost of keeping a few spurious ones is nothing; the cost of deleting Gill's pointing is the
edition). Pointed crops become a census line — where Gill vocalizes.

Detector: Hebrew nikud are small marks BELOW the consonant baseline (most vowels) and a few above
(holam/dagesh). A consonantal line has a clean baseline with ink below it only under the few final-letter
descenders (ך ן ף ץ); a pointed line has dots under MOST consonants. So the discriminator is the FRACTION
OF COLUMNS carrying ink in the sub-baseline band — low for unpointed (descenders only), high for pointed
(a dot under nearly every letter). Deterministic, no model — a property the model shouldn't own."""
import re
import numpy as np

NIKUD_RE = re.compile(r"[֑-ׇ]")

def strip_nikud(text):
    """Remove Hebrew combining marks (points, cantillation). Consonants + spacing untouched."""
    return NIKUD_RE.sub("", text or "")

def _sub_density(crop):
    """Fraction of ink-columns that carry ink in the sub-baseline band of the (Hebrew) crop.
    Returns (density, has_main_band). density ~0.0-0.2 = unpointed (descenders only); ~0.35+ = pointed."""
    a = np.asarray(crop.convert("L")) < 128
    if a.sum() < 20:
        return 0.0, False
    rowmass = a.sum(axis=1)
    peak = rowmass.max()
    on = rowmass > peak * 0.30
    dense = int(np.argmax(rowmass))                      # the consonant body is the CONTIGUOUS dense band
    top = dense                                          # around the densest row; nikud sit below it, after
    while top > 0 and on[top - 1]: top -= 1              # a gap, so a flat threshold would wrongly absorb them
    baseline = dense
    while baseline < len(on) - 1 and on[baseline + 1]: baseline += 1
    main = np.arange(top, baseline + 1)
    sub = a[baseline + 1:]                               # rows below the baseline = where most nikud sit
    if sub.shape[0] < 2:
        return 0.0, True
    ink_cols = (a[main[0]:baseline + 1].sum(axis=0) > 0)  # columns that carry a consonant
    n_ink = max(1, ink_cols.sum())
    sub_cols = (sub.sum(axis=0) > 0) & ink_cols          # sub-baseline ink under a consonant column
    return sub_cols.sum() / n_ink, True

def is_pointed(crop, strip_below=0.10, keep_above=0.30):
    """Conservative verdict for the gate. Returns 'unpointed' ONLY when confidently below strip_below
    (safe to strip); 'pointed' when above keep_above (keep); 'uncertain' in between (KEEP by policy).
    Erring toward KEEP protects Gill's genuinely-pointed pages."""
    d, ok = _sub_density(crop)
    if not ok:
        return "uncertain", d
    if d <= strip_below:
        return "unpointed", d
    if d >= keep_above:
        return "pointed", d
    return "uncertain", d

def gated_strip(text, crop):
    """Strip nikud ONLY when the crop is confidently unpointed; keep otherwise. Returns
    (result_text, verdict, density) so the caller can census 'pointed' pages and flag 'uncertain'."""
    verdict, d = is_pointed(crop)
    if verdict == "unpointed" and NIKUD_RE.search(text or ""):
        return strip_nikud(text), verdict, d
    return text, verdict, d
