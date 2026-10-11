"""verse_regions — PURE layout analysis for Lane A2 step 2: verse regions from page layout.

Builds the verse-region substrate from page geometry (volume1_page_geometry.jsonl) plus the page
ink only. Deliberately NOT built from OCR word boxes (align_verses.py's fuzzy text-to-box match
was the cross-modal-correspondence trap; this replaces it). Witness text (the old vol.1 .md) is
used for verse COUNTS AND NUMBERS ONLY, never geometry.

No I/O, no network anywhere in this module. Callers (build_verse_regions.py) load PNGs/geometry/
witness text and pass plain numpy arrays / dicts / strings in.

See DESIGN_step2_verse_regions_20261004.md and DESIGN_step2_amendment_20261004.md (amendment
wins where they differ) for the full rationale. This docstring only orients; it does not repeat
the design.

Stage map (S1-S5), each deterministic, each emits flags, none gates:
  S1 page_ink / analyze_page_s1   -- trim body regions: running head, full-width bands, rule doubt
  S2 head_candidates               -- verse/chapter/book head candidates by printed-mark signature
  S3 reconcile_numbers / confirm_candidates -- count/read/witness sources, never merged silently
  S4 assemble_regions              -- walk heads in reading order across pages into regions
  S5 (flags folded into assemble_regions / page records)
"""
from __future__ import annotations

import difflib
import re
from collections import namedtuple, Counter

import numpy as np

from note_start_detect import INK, _line_geom, strip_vrules, text_lines, _text_lines  # noqa: F401 (INK re-exported)
import box_sanity

# --------------------------------------------------------------------------------------------
# Named constants (recorded in config; spec explicitly asks some of these to be named/recorded)
# --------------------------------------------------------------------------------------------
GUTTER_WINDOW_W = 120            # +/- px around xdiv probed by the per-band gutter-ink test
RULE_RUN_MAX_W = 8                # an ink column-run this wide or narrower is a printed rule -> white
RUNNING_HEAD_TOP_FRAC = 0.119     # running head = topmost full-width band starting above 0.119*H (643 px).
                                  # Measured (207 vol.1 pages): topmost ink line y0 463-632, next starts
                                  # >= 654; 0.119 sits in that empty band. The old 0.10 (540 px) cut the
                                  # mode (p50 589) and found no running head on any of the 20 pages.
TITLE_FRAC_FOSSIL = 0.03          # the old fixed-3% rule, kept ONLY as a cross-check flag
BOOK_XHEIGHT_RATIO = None         # DISABLED. The unmeasured 1.5 was refuted: the 6 chapter heads found on the
                                  # 20 pages measure 1.59-1.86, so 1.5 called every one a book. No book head
                                  # was measurable (p403's Exodus title lies below the geometry body regions),
                                  # so no book threshold can be derived; book heads are NOT detected in step 2.
CHAPTER_XHEIGHT_RATIO = 1.15      # in-column centred heads. Lies in the measured empty band between body
                                  # full bands (<= 1.03) and chapter heads (>= 1.59) on the 20 pages.
CENTRE_MARGIN_MULT = 3            # chapter-head centred margins must be >= this * inset_thr
CENTRE_ASYM_FRAC = 0.10           # centred: |left - right margin| <= this * mean margin. Measured on the 6
                                  # chapter heads of the 20 pages: asymmetry 4-65 px on ~1250 px margins
                                  # (max 5.4%; binding offset). Was "<= inset_thr", a paragraph-indent unit
                                  # used as a centring tolerance -- it moved with the indent derivation and
                                  # dropped 151/197/404. n=6, not an empty-band derivation; named.
# Inset threshold: flush/indent mode midpoint (derive_inset_modes), replacing the old
# derive_threshold/MIN_GAP_INSET_PX first-empty-band rule -- a first-gap selector on a trough
# degenerated 41 -> 80 when one band filled a 4-px hole; bin centres make one band's shift
# invisible (see derive_inset_modes docstring; rerun3 Lane A2 (d)).
INSET_MODE_BIN_PX = 5             # histogram bin width; 3-10 px measured -> 33-36 (MEASURE_step2_d_inset_modes)
INSET_MODE_MIN_PEAK = 5           # a mode is >= 5 bands, not a few strays (3/5/8 identical)
INSET_MODE_MIN_SEP_PITCH_FRAC = 0.5  # indent mode >= half a line pitch from flush (an indent ~ an em ~ the pitch);
                                     # added after page 745 alone gave a false mode at 15-20 px
INSET_MODE_VALLEY_FRAC = 0.5      # a trough bin <= half the indent bin's count (0.3/0.7 identical)
CROP_PAD_Y = 12                   # head-crop vertical padding (verse_head_read.py)
HEAD_CROP_WIDTH_FRAC = 0.5        # head-crop width as a fraction of the column width

# Full-width classification: two MEASURED edges, abstain between (a single derived threshold is
# refused by the data -- see MEASURE_step2_gutter_inset_20261004.md). gap_px <= FULL_GAP_MAX_PX is
# full-width; gap_px >= COL_GAP_MIN_PX is an ordinary column band; the zone between is a column
# band flagged band['gutter_ambiguous'] = True.
FULL_GAP_MAX_PX = 11
COL_GAP_MIN_PX = 55

# The printed column rule is a double line (`.26 #8 .5 #8 .21`); measured cluster widths peak
# 17-21 px over the 20 pages (MEASURE_step2_gutter_inset_20261004.md).
DOUBLE_RULE_MERGE_PX = 5          # merge ink runs separated by white runs <= this many px
DOUBLE_RULE_MAX_W = 24            # a merged ink cluster this wide or narrower may be the rule
DOUBLE_RULE_FLANK_PX = 15         # both flanking white runs must be at least this wide
DOUBLE_RULE_NEAR_PX = 60          # cluster centre must be within this many px of xdiv's window position

# Column-band heights over the 20 pages fall into three clearly separated populations: speck
# clusters 2-15px, a true empty-band gap jumping straight from 19 to 24px, real text lines
# 46-64px (MEASURE_step2_gutter_inset_20261004.md). A band shorter than SLIVER_MAX_H_PX is a
# sliver (noise), never a line: it is held out before full-width pairing and head detection.
SLIVER_MAX_H_PX = 20
# Head rule (printed rule under the running head) = furniture, not a body band. Thresholds measured
# on vol.1 only (207 pages) -- MEASURE_head_rule_20261011.md (dr-voluminous/body_shadow_vol1/verse_regions/).
HEAD_RULE_MAX_H_FRAC = 0.75       # band h / median_line_h; mode midpoint (rule 0.475 vs text 1.025)
HEAD_RULE_MIN_FILL = 0.275        # peak row ink fill over the band's x0:x1; mode midpoint (0.075 vs 0.475)
HEAD_RULE_LINE_H_MAX_PX = 85      # median_line_h above this = multi-line median -> abstain (single-line
                                  # 49-70 px on 203 pages, multi-line 100-256 on 4; envelope, not a mode midpoint)

# text_lines' default valley-split picks the n-1 globally deepest candidate rows with no
# separation constraint, so two minima of ONE inter-line valley can both be picked and starve a
# real line-break of its cut (measured on p402: minima 12 rows apart in one valley; line pitch
# ~63px, median single line ~60px). Requiring cuts to be this fraction of the median line height
# apart from each other rejects the second, spurious minimum and lets the real valley win instead.
TEXT_LINE_MIN_SEP_FRAC = 0.5

# text_lines' deepest-valley rule (with or without min_sep_frac) ranks candidate rows by GLOBAL
# depth, so a near-white row under a baseline INSIDE a line can outrank a true inter-line gap that
# happens to be shallower (measured, 20 vol.1 pages: 20/358 cuts mid-line on own-line-height columns,
# 41/273 on page-line-height columns; pitch: 2 and 2).
# snap="pitch" partitions each band into n evenly spaced windows instead, one per expected cut, so a
# false-deep row elsewhere in the band can no longer steal a cut from the true (if shallower,
# within-window) gap near it.
TEXT_LINE_SNAP = "pitch"

# Defect: note_start_detect.text_lines estimates a column's single-line height as the median of
# that column's OWN raw (pre-split) band heights. On an intact column most raw bands already are
# single lines (measured raw-band medians 48-61px), so the median is a usable line height. On some
# RIGHT columns most raw bands are themselves fused multi-line bands (collapsed), so the column's
# own median is itself multi-line (measured collapsed medians: 92R 254, 126R 312, 197R 189, 923R
# 308, 925R 120 -- raw band counts 7-20 there vs 31-72 on an intact column) and n=round(h/med)=1,
# so nothing splits. Nothing was measured in the empty band between 61 and 120px, so 1.5x an
# intact median (<=~92) separates the two populations below the lowest collapsed value (120)
# without needing a derive_threshold-style empty-band measurement at this grain (no pooled
# corpus-wide distribution of raw medians was available to run it on). See choose_line_h /
# analyze_page_s1.
LINE_H_EMPTY_BAND_MULT = 1.5


# ==============================================================================================
# page_ink
# ==============================================================================================

def page_ink(arr):
    """arr: 2-D grayscale array (e.g. np.asarray(Image.open(p).convert('L'))). -> bool ink mask,
    ink where gray < INK (note_start_detect's constant, reused, not re-picked)."""
    return np.asarray(arr) < INK


# ==============================================================================================
# derive_threshold — thresholds from empty bands (never picked)
# ==============================================================================================

class ThresholdUndetermined(ValueError):
    """Raised by derive_threshold when no empty band wide enough separates the two populations.
    This is a REFUSAL, not a fallback: a threshold that cannot be derived is not silently guessed."""


def derive_threshold(values, min_gap):
    """The FIRST empty band (gap >= min_gap) scanning UPWARD from the median of the sorted
    distribution of `values` -- the boundary between the dominant (flush/body) population sitting
    at and below the median and whatever lies just above it. This is deliberately NOT the widest
    gap anywhere: a wide gap far above the median (e.g. a population of centred/short lines vs.
    everything else) is a DIFFERENT population boundary, and picking it instead silently
    mis-derives the threshold (see MEASURE_step2_gutter_inset_20261004.md, where the widest-gap
    rule picked a centred-lines/rest split instead of the real flush-mode edge).

    Returns {value, lo, hi, n_below, n_above, gap, rule}: `value` is the midpoint of that first
    empty band above the median; rule is always "first_empty_band_above_median". Raises
    ThresholdUndetermined if no gap >= `min_gap` is found scanning from the median index to the
    top of the distribution -- refuse to pick a threshold from a continuous distribution rather
    than guess one from noise."""
    vals = sorted(float(v) for v in values)
    n = len(vals)
    if n < 2:
        raise ThresholdUndetermined(
            f"derive_threshold: need >= 2 values to find a gap between two populations, got {n}")
    start = n // 2
    for i in range(start, n - 1):
        g = vals[i + 1] - vals[i]
        if g >= min_gap:
            lo, hi = vals[i], vals[i + 1]
            return {
                "value": (lo + hi) / 2.0, "lo": lo, "hi": hi,
                "n_below": i + 1, "n_above": n - (i + 1), "gap": g,
                "rule": "first_empty_band_above_median",
            }
    raise ThresholdUndetermined(
        f"derive_threshold: no empty band >= {min_gap}px found scanning upward from the median "
        f"(index {start} of {n} values); refusing to pick a threshold from a continuous "
        f"distribution.")


def derive_inset_modes(values, pitch_px, bin_px=INSET_MODE_BIN_PX, min_peak=INSET_MODE_MIN_PEAK,
                        min_sep_pitch_frac=INSET_MODE_MIN_SEP_PITCH_FRAC,
                        valley_frac=INSET_MODE_VALLEY_FRAC):
    """Inset threshold = the midpoint between a flush mode and an indent mode in a histogram of
    `values` (bin width `bin_px`), taken ONLY when the two modes are actually separated -- never a
    constant, never a guess from a continuous/unimodal distribution (abstains instead, like
    derive_threshold/ThresholdUndetermined).

    Replaces derive_threshold's first-empty-band-above-median rule for this signal: that rule
    picks the first GAP it finds scanning up from the median, so one band's value drifting into a
    4-px hole (filling it) silently moved the whole threshold 41 -> 80 (MEASURE_step2_d_inset_modes).
    One band moves one count between two bins, which changes the threshold only if it changes
    WHICH bin is a mode; the value is read off bin CENTRES, not in-bin medians (with medians a 40-px
    shift of one band moved it 0.5 px in 15 of 1244 trials; with centres, 0 of 1244, and 0 of 1244
    for one band dropped).

    values: inset_px samples (>= 0). pitch_px: the page's own line pitch (median band height),
    used to reject an indent mode too close to flush to be a real paragraph indent (an indent ~ an
    em ~ the line pitch; a false mode 15-20px away from flush, not pitch-relative, was found on
    page 745 alone and must not be confused for the real indent).

    Returns {"status": "ok"|"abstained", "reason": None|str, "value": float|None,
    "rule": "mode_midpoint", "bin_px", "pitch_px", "flush_bin", "indent_bin" (None when no second
    mode is found), "flush_count", "indent_count", "n", "hist"} (hist truncated to the first 40
    bins). Never raises for a data condition; never returns a constant -- an abstained result
    means the caller must not derive a threshold from this run, not that it should fall back to
    one."""
    vals = list(values)
    n = len(vals)
    if n == 0:
        return {"status": "abstained", "reason": "no_values", "value": None, "rule": "mode_midpoint",
                "bin_px": bin_px, "pitch_px": pitch_px, "flush_bin": None, "indent_bin": None,
                "flush_count": None, "indent_count": None, "n": 0, "hist": []}

    counts = Counter(int(v // bin_px) for v in vals)
    top = max(counts)
    hist = [counts.get(i, 0) for i in range(top + 1)]

    f = max(range(len(hist)), key=lambda i: (hist[i], -i))

    candidates = []
    for j in range(f + 1, len(hist)):
        if hist[j] < min_peak:
            continue
        if (j - f) * bin_px < min_sep_pitch_frac * pitch_px:
            continue
        trough = hist[f + 1:j]
        if not trough:
            continue
        if min(trough) <= valley_frac * hist[j]:
            candidates.append(j)

    if not candidates:
        return {"status": "abstained", "reason": "no_second_mode", "value": None, "rule": "mode_midpoint",
                "bin_px": bin_px, "pitch_px": pitch_px, "flush_bin": f, "indent_bin": None,
                "flush_count": hist[f], "indent_count": None, "n": n, "hist": hist[:40]}

    j = max(candidates, key=lambda k: (hist[k], -k))
    value = (f + j + 1) * bin_px / 2.0
    return {"status": "ok", "reason": None, "value": value, "rule": "mode_midpoint",
            "bin_px": bin_px, "pitch_px": pitch_px, "flush_bin": f, "indent_bin": j,
            "flush_count": hist[f], "indent_count": hist[j], "n": n, "hist": hist[:40]}


# ==============================================================================================
# S1 — gutter-ink test, running head, full-width bands
# ==============================================================================================

def _widest_true_run(bool_vec):
    """(length, start_index) of the widest contiguous True run in a 1-D bool array."""
    best_len = cur = 0
    best_start = cur_start = 0
    for i, v in enumerate(bool_vec):
        if v:
            if cur == 0:
                cur_start = i
            cur += 1
            if cur > best_len:
                best_len, best_start = cur, cur_start
        else:
            cur = 0
    return best_len, best_start


def _treat_thin_ink_runs_as_white(colhas, max_w=RULE_RUN_MAX_W):
    """colhas: 1-D bool, True where a column carries ink anywhere in the band. A printed vertical
    rule is a thin (<=max_w) unbroken ink run; such runs are flipped to False (white) so a rule
    alone does not defeat the gutter-white test (amendment B: the gutter is not white, but a rule
    this narrow is not text either)."""
    out = colhas.copy()
    n = len(out)
    i = 0
    while i < n:
        if out[i]:
            j = i
            while j < n and out[j]:
                j += 1
            if (j - i) <= max_w:
                out[i:j] = False
            i = j
        else:
            i += 1
    return out


def _treat_double_rule_as_white(colhas, centre_idx, merge_px=DOUBLE_RULE_MERGE_PX,
                                 max_w=DOUBLE_RULE_MAX_W, flank_px=DOUBLE_RULE_FLANK_PX,
                                 near_px=DOUBLE_RULE_NEAR_PX):
    """colhas: 1-D bool (already thin-run-cleaned, but this is safe to run on any bool vector --
    it only ever turns MORE ink to white, a union with whatever cleaning ran before it). Merges
    ink runs separated by <= merge_px white into clusters; a cluster <= max_w wide, flanked on
    BOTH sides by >= flank_px white, and centred within +-near_px of centre_idx, is the printed
    double rule (`.26 #8 .5 #8 .21`) -- flip it to white (False). A lone rule-line run (not
    merged with any neighbour) qualifies the same way: 'merged' includes singleton clusters."""
    out = colhas.copy()
    n = len(out)
    runs = []
    i = 0
    while i < n:
        if out[i]:
            j = i
            while j < n and out[j]:
                j += 1
            runs.append([i, j])
            i = j
        else:
            i += 1
    if not runs:
        return out

    merged = [list(runs[0])]
    for start, end in runs[1:]:
        if start - merged[-1][1] <= merge_px:
            merged[-1][1] = end
        else:
            merged.append([start, end])

    for idx, (start, end) in enumerate(merged):
        width = end - start
        if width > max_w:
            continue
        left_white = start if idx == 0 else start - merged[idx - 1][1]
        right_white = (n - end) if idx == len(merged) - 1 else merged[idx + 1][0] - end
        centre = (start + end) / 2.0
        if left_white >= flank_px and right_white >= flank_px and abs(centre - centre_idx) <= near_px:
            out[start:end] = False
    return out


def _gutter_rule_cols(ink_mask, xdiv, y0, y1, W=GUTTER_WINDOW_W):
    """Single shared definition of 'rule, not text' near the gutter, for rows [y0, y1) of the
    FULL-PAGE ink mask. Returns (x0, colhas, cleaned): x0 the page-absolute start column of the
    probed [xdiv-W, xdiv+W) window; colhas/cleaned 1-D bool arrays, local index i <-> absolute
    x0+i, colhas BEFORE and cleaned AFTER the printed-rule classifier
    (_treat_thin_ink_runs_as_white then _treat_double_rule_as_white) runs. Empty window -> (x0,
    empty, empty). Consumed by BOTH gutter_gap (full-width band classification) and _make_band
    (per-band ink-extent measurement) so they can never disagree about what the rule is."""
    H, Wd = ink_mask.shape
    x0 = max(0, xdiv - W)
    x1 = min(Wd, xdiv + W)
    y0c, y1c = max(0, y0), min(H, y1)
    if x1 <= x0 or y1c <= y0c:
        empty = np.zeros(0, dtype=bool)
        return x0, empty, empty
    strip = ink_mask[y0c:y1c, x0:x1]
    colhas = strip.any(axis=0)
    cleaned = _treat_thin_ink_runs_as_white(colhas)
    centre_idx = xdiv - x0
    cleaned = _treat_double_rule_as_white(cleaned, centre_idx)
    return x0, colhas, cleaned


def gutter_gap(ink_mask, xdiv, y0, y1, W=GUTTER_WINDOW_W):
    """(gap_px, centre_x) of the widest white run within [xdiv-W, xdiv+W) over rows [y0, y1) of
    the FULL-PAGE ink mask -- a printed vertical rule (ink run <= RULE_RUN_MAX_W px, OR a double-
    rule cluster matching _treat_double_rule_as_white) counts as white. gap_px small -> ink
    crosses the gutter (full-width); gap_px large -> two columns."""
    x0, colhas, cleaned = _gutter_rule_cols(ink_mask, xdiv, y0, y1, W=W)
    if len(cleaned) == 0:
        return 0, None
    white = ~cleaned
    gap_px, start = _widest_true_run(white)
    centre = (x0 + start + gap_px / 2.0) if gap_px > 0 else None
    return int(gap_px), centre


def _make_band(col, col_box, abs_y0, abs_y1, col_ink, ink, xdiv, gutter_window=GUTTER_WINDOW_W):
    """col_ink: bool ink array for the WHOLE column box (already strip_vrules'd); abs_y0/abs_y1
    page-absolute row bounds of this band; col_box = (x0,y0,x1,y1) of the column region (abs).
    ink/xdiv/gutter_window: the FULL-PAGE ink mask and gutter geometry, used to zero the printed
    column-rule's columns (_gutter_rule_cols -- the SAME definition gutter_gap uses) before
    measuring this band's own left/right ink extent. strip_vrules's own max_w=6 is narrower than
    the double rule's actual 8-10px line width, so the rule survives strip_vrules (applied once,
    over the whole column) and would otherwise become this band's leftmost/rightmost ink."""
    cx0, cy0, cx1, cy1 = col_box
    ly0, ly1 = abs_y0 - cy0, abs_y1 - cy0
    band_ink = col_ink[ly0:ly1]
    baseline, xh = _line_geom(band_ink)

    gx0, colhas, cleaned = _gutter_rule_cols(ink, xdiv, abs_y0, abs_y1, W=gutter_window)
    rule_cols_abs = np.where(colhas & ~cleaned)[0] + gx0

    masked = band_ink.copy()
    rule_cols_removed = 0
    for x_abs in rule_cols_abs:
        lx = int(x_abs) - cx0
        if 0 <= lx < masked.shape[1]:
            masked[:, lx] = False
            rule_cols_removed += 1

    colhas_band = masked.any(axis=0)
    xs = np.where(colhas_band)[0]
    left_local = int(xs[0]) if len(xs) else 0
    right_local = int(xs[-1]) if len(xs) else -1
    return {
        "col": col, "y0": int(abs_y0), "y1": int(abs_y1),
        "x0": int(cx0), "x1": int(cx1),
        "left_ink_x": int(cx0 + left_local), "right_ink_x": int(cx0 + right_local + 1),
        "baseline": int(abs_y0 + baseline), "xheight": int(xh),
        "rule_cols_removed": rule_cols_removed,
    }


def _merge_full_bands(left_bands, right_bands, ink, xdiv, gutter_window=GUTTER_WINDOW_W):
    """Classifies each column-local band by its own per-band gutter test (gutter_gap, over the
    FULL page width, that band's own y-range) against TWO measured edges, abstaining between them
    (a single derived threshold is refused by the data -- see
    MEASURE_step2_gutter_inset_20261004.md): gap_px <= FULL_GAP_MAX_PX is full-width; gap_px >=
    COL_GAP_MIN_PX is an ordinary column band; the zone between is ALSO a column band, but flagged
    band['gutter_ambiguous'] = True (no full-width split is made from an ambiguous band). A
    left-flagged band and a right-flagged band whose y-ranges overlap are the SAME physical
    printed line, split only by our column slicing -- merge them into one 'full' band. An
    unpaired flagged band stays a column band with full_unpaired=True (one side of the gutter is
    not evidence of a full-width line; running heads are taken by the top zone instead). Returns (full_bands, left_rest, right_rest)."""

    def _flag(bands):
        flagged, rest = [], []
        for b in bands:
            gap_px, centre = gutter_gap(ink, xdiv, b["y0"], b["y1"], W=gutter_window)
            if gap_px <= FULL_GAP_MAX_PX:
                flagged.append(dict(b, gap_px=gap_px, gap_centre=centre, gutter_ambiguous=False))
            else:
                ambiguous = gap_px < COL_GAP_MIN_PX
                rest.append(dict(b, gap_px=gap_px, gap_centre=centre, gutter_ambiguous=ambiguous))
        return flagged, rest

    left_flagged, left_rest = _flag(left_bands)
    right_flagged, right_rest = _flag(right_bands)

    full_bands = []
    used_right = set()
    for lb in left_flagged:
        match_i = None
        for i, rb in enumerate(right_flagged):
            if i in used_right:
                continue
            if lb["y0"] < rb["y1"] and rb["y0"] < lb["y1"]:
                match_i = i
                break
        if match_i is not None:
            rb = right_flagged[match_i]
            used_right.add(match_i)
            full_bands.append({
                "col": "full", "y0": min(lb["y0"], rb["y0"]), "y1": max(lb["y1"], rb["y1"]),
                "x0": min(lb["x0"], rb["x0"]), "x1": max(lb["x1"], rb["x1"]),
                "gap_px": min(lb["gap_px"], rb["gap_px"]),
                "left_ink_x": min(lb["left_ink_x"], rb["left_ink_x"]),
                "right_ink_x": max(lb["right_ink_x"], rb["right_ink_x"]),
                "baseline": max(lb["baseline"], rb["baseline"]),
                "xheight": max(lb["xheight"], rb["xheight"]),
            })
        else:
            # Full width needs evidence on BOTH sides of the gutter. An unpaired flagged band stays
            # a column band (flagged full_unpaired): promoted alone, its rect was its own column
            # box, which box_sanity accepted as a column box (p745) -- a "full" rect that was not.
            left_rest.append(dict(lb, gutter_ambiguous=False, full_unpaired=True))
    for i, rb in enumerate(right_flagged):
        if i not in used_right:
            right_rest.append(dict(rb, gutter_ambiguous=False, full_unpaired=True))
    full_bands.sort(key=lambda b: b["y0"])
    left_rest.sort(key=lambda b: b["y0"])
    right_rest.sort(key=lambda b: b["y0"])
    return full_bands, left_rest, right_rest


def _split_slivers(bands, max_h=SLIVER_MAX_H_PX):
    """Partitions column line bands into (kept, slivers). A sliver is a speck/noise cluster
    shorter than max_h (measured: speck clusters 2-15px, real text lines 46-64px over the 20
    pages -- MEASURE_step2_gutter_inset_20261004.md). Slivers are held out BEFORE full-width
    pairing and head detection: they never become candidates, never serve as prev_band, never
    create or extend a rect, and never count toward n_ink_bands."""
    kept, slivers = [], []
    for b in bands:
        (slivers if (b["y1"] - b["y0"]) < max_h else kept).append(b)
    return kept, slivers


def choose_line_h(column_raw_median, page_line_h):
    """Pure decision for the line_h defect: a column's own raw-band median is only a usable
    single-line-height estimate when it is NOT itself multi-line. If it exceeds
    LINE_H_EMPTY_BAND_MULT * the page-pooled raw median, the column is collapsed (most of its raw
    bands are fused) and its own median must not be used -- fall back to the page-pooled median
    instead. Returns (line_h_or_None, basis): basis "column" -> line_h=None (today's path, use the
    column's own median inside text_lines); basis "page" -> line_h=page_line_h (pass it through
    explicitly)."""
    if column_raw_median > LINE_H_EMPTY_BAND_MULT * page_line_h:
        return page_line_h, "page"
    return None, "column"


def analyze_page_s1(ink, geom_record, gutter_window=GUTTER_WINDOW_W):
    """S1: per-column line bands (vertical rules stripped), sliver quarantine (R2), full-width
    band detection (gutter-ink test per band, classified by the two measured edges
    FULL_GAP_MAX_PX/COL_GAP_MIN_PX -- see _merge_full_bands), and running-head detection. Pure:
    ink is the full-page bool mask, geom_record one record from volume1_page_geometry.jsonl.
    Returns a page_s1 dict."""
    H, W = ink.shape
    xdiv = geom_record["xdiv"]
    col_boxes = {r["col"]: tuple(r["box"]) for r in geom_record["body_regions"] if r["col"] in ("left", "right")}

    # Raw (pre-split) band heights per column, on the SAME strip_vrules-cleaned column ink used
    # for the real split below -- pooled median over BOTH columns' raw bands is the page-wide
    # single-line-height estimate (choose_line_h / LINE_H_EMPTY_BAND_MULT). NOTE: if BOTH columns
    # are collapsed, the pooled median is itself multi-line too and this cannot see it -- named,
    # not solved here.
    cleaned_by_col = {}
    raw_heights_by_col = {}
    pooled_raw_heights = []
    for col, box in col_boxes.items():
        x0, y0, x1, y1 = box
        cleaned = strip_vrules(ink[y0:y1, x0:x1])
        cleaned_by_col[col] = cleaned
        heights = [ry1 - ry0 for (ry0, ry1) in _text_lines(cleaned)]
        raw_heights_by_col[col] = heights
        pooled_raw_heights.extend(heights)

    pooled_sorted = sorted(pooled_raw_heights) or [1]
    page_line_h = pooled_sorted[len(pooled_sorted) // 2]

    line_h = {}
    bands = {}
    slivers = []
    flags = []
    for col, box in col_boxes.items():
        x0, y0, x1, y1 = box
        cleaned = cleaned_by_col[col]
        col_heights_sorted = sorted(raw_heights_by_col[col]) or [1]
        column_raw_median = col_heights_sorted[len(col_heights_sorted) // 2]
        col_line_h, basis = choose_line_h(column_raw_median, page_line_h)
        line_h[col] = {"basis": basis, "column_raw_median": column_raw_median, "page_line_h": page_line_h}
        if basis == "page":
            flags.append(f"line_h_from_page:{col}")
        raw_bands = [_make_band(col, box, y0 + ly0, y0 + ly1, cleaned, ink, xdiv, gutter_window)
                     for (ly0, ly1) in text_lines(cleaned, min_sep_frac=TEXT_LINE_MIN_SEP_FRAC,
                                                   line_h=col_line_h, snap=TEXT_LINE_SNAP)]
        kept, col_slivers = _split_slivers(raw_bands)
        bands[col] = kept
        slivers.extend(col_slivers)

    full_bands, left_rest, right_rest = _merge_full_bands(
        bands.get("left", []), bands.get("right", []), ink, xdiv, gutter_window)

    # Running head = the measured top ZONE: every band (full OR column) starting above
    # RUNNING_HEAD_TOP_FRAC*H. A letter-spaced running head can fail the gutter test and be filed
    # as two column bands (p129/130/151/745), so restricting to full bands missed it.
    top_limit = RUNNING_HEAD_TOP_FRAC * H
    rh_bands = [b for b in full_bands + left_rest + right_rest if b["y0"] < top_limit]
    running_head = None
    if rh_bands:
        running_head = {"col": "full", "y0": min(b["y0"] for b in rh_bands),
                        "y1": max(b["y1"] for b in rh_bands),
                        "x0": min(b["x0"] for b in rh_bands), "x1": max(b["x1"] for b in rh_bands),
                        "n_bands": len(rh_bands)}
    rh_ids = {id(b) for b in rh_bands}
    other_full = [b for b in full_bands if id(b) not in rh_ids]
    left_rest = [b for b in left_rest if id(b) not in rh_ids]
    right_rest = [b for b in right_rest if id(b) not in rh_ids]

    all_local = left_rest + right_rest
    heights = sorted((b["y1"] - b["y0"]) for b in all_local) or [1]
    median_line_h = heights[len(heights) // 2]
    if running_head is not None and abs(running_head["y1"] - TITLE_FRAC_FOSSIL * H) > median_line_h:
        flags.append("head_band_disagrees_3pct")

    head_rules = []
    if running_head is not None:
        body = [("full", b) for b in other_full] + [("left", b) for b in left_rest] + \
               [("right", b) for b in right_rest]
        shares = {"full": ("full", "left", "right"), "left": ("left", "full"), "right": ("right", "full")}

        def _topmost(col, b):
            return not any(b2 is not b and c2 in shares[col] and b2["y0"] < b["y0"] for c2, b2 in body)

        matched = []
        for col, b in body:
            if not _topmost(col, b):
                continue
            h = b["y1"] - b["y0"]
            if not (h < HEAD_RULE_MAX_H_FRAC * median_line_h
                    and b["y0"] - running_head["y1"] < median_line_h):
                continue
            fill_max = float(ink[b["y0"]:b["y1"], b["x0"]:b["x1"]].mean(axis=1).max())
            if fill_max >= HEAD_RULE_MIN_FILL:
                matched.append((col, b, h, fill_max))
        if median_line_h > HEAD_RULE_LINE_H_MAX_PX:
            if matched:
                flags.append("head_rule_abstained:line_h_multi")
        else:
            for col, b, h, fill_max in matched:
                head_rules.append({"col": col, "y0": b["y0"], "y1": b["y1"], "x0": b["x0"], "x1": b["x1"],
                                   "h": h, "h_frac": h / median_line_h, "fill_max": fill_max})
                flags.append(f"head_rule_removed:{col}")
            rm = {id(b) for _, b, _, _ in matched}
            other_full = [b for b in other_full if id(b) not in rm]
            left_rest = [b for b in left_rest if id(b) not in rm]
            right_rest = [b for b in right_rest if id(b) not in rm]

    return {
        "file_page": geom_record.get("file_page"), "W": int(W), "H": int(H), "xdiv": xdiv,
        "left": left_rest, "right": right_rest, "full": other_full, "slivers": slivers,
        "running_head": running_head, "flags": flags, "col_boxes": col_boxes, "line_h": line_h, "head_rules": head_rules,
    }


# ==============================================================================================
# S2 — head candidates by printed-mark signature
# ==============================================================================================

def _column_medians(bands):
    if not bands:
        return {"left_x": 0.0, "right_x": 0.0, "xheight": 1.0}
    lefts = sorted(b["left_ink_x"] - b["x0"] for b in bands)
    rights = sorted(b["right_ink_x"] - b["x0"] for b in bands)
    xhs = sorted(b["xheight"] for b in bands)
    n = len(bands)
    return {"left_x": lefts[n // 2], "right_x": rights[n // 2], "xheight": xhs[n // 2]}


def pair_centred_across_gutter(page_s1, inset_thr):
    """S1b: a centred, letter-spaced head ("C H A P. V.") printed ACROSS the gutter has an
    inter-letter gap of 45-55 px at xdiv (measured, p128/p197), so the per-band gutter test files
    it as two column bands and neither half is centred in its own column. Printed-mark signature:
    a left band that is deeply inset (>= CENTRE_MARGIN_MULT*inset_thr from its column's median
    text left) yet reaches its column's median text right (within inset_thr), y-overlapping a right
    band that starts at its column's median text left (within inset_thr) and stops short of its
    column's median text right by >= CENTRE_MARGIN_MULT*inset_thr. The pair is merged into ONE full
    band (full_basis "centred_pair"); whether it is a chapter/book head is still decided by the
    full-band centred test in head_candidates. Mutates page_s1 (left/right/full,
    n_centred_pairs); returns the number of pairs merged."""
    left, right = page_s1.get("left") or [], page_s1.get("right") or []
    ml, mr = _column_medians(left), _column_medians(right)
    deep = CENTRE_MARGIN_MULT * inset_thr
    used_l, used_r, merged = set(), set(), []
    for i, lb in enumerate(left):
        l_left = (lb["left_ink_x"] - lb["x0"]) - ml["left_x"]
        l_right = lb["right_ink_x"] - lb["x0"]
        if l_left < deep or l_right < ml["right_x"] - inset_thr:
            continue
        for j, rb in enumerate(right):
            if j in used_r:
                continue
            ov = min(lb["y1"], rb["y1"]) - max(lb["y0"], rb["y0"])
            if ov < 0.5 * min(lb["y1"] - lb["y0"], rb["y1"] - rb["y0"]):
                continue
            r_left = (rb["left_ink_x"] - rb["x0"]) - mr["left_x"]
            r_short = mr["right_x"] - (rb["right_ink_x"] - rb["x0"])
            if r_left > inset_thr or r_short < deep:
                continue
            used_l.add(i); used_r.add(j)
            merged.append({
                "col": "full", "y0": min(lb["y0"], rb["y0"]), "y1": max(lb["y1"], rb["y1"]),
                "x0": min(lb["x0"], rb["x0"]), "x1": max(lb["x1"], rb["x1"]),
                "gap_px": lb.get("gap_px"), "gutter_ambiguous": False,
                "left_ink_x": lb["left_ink_x"], "right_ink_x": rb["right_ink_x"],
                "baseline": max(lb["baseline"], rb["baseline"]),
                "xheight": max(lb["xheight"], rb["xheight"]),
                "full_basis": "centred_pair",
            })
            break
    if merged:
        page_s1["left"] = [b for i, b in enumerate(left) if i not in used_l]
        page_s1["right"] = [b for j, b in enumerate(right) if j not in used_r]
        page_s1["full"] = sorted((page_s1.get("full") or []) + merged, key=lambda b: b["y0"])
    page_s1["n_centred_pairs"] = len(merged)
    return len(merged)


def _bucket_by_interval(full_bands, left_bands, right_bands, H):
    """Sections split by full bands (running head already excluded upstream). Returns an ordered
    list of (col, band) events: left column top->bottom, then right column top->bottom, per
    section; full-band events are interleaved in y-order between sections."""
    full_sorted = sorted(full_bands, key=lambda b: b["y0"])
    intervals = []
    prev = 0
    for fb in full_sorted:
        intervals.append((prev, fb["y0"]))
        prev = fb["y1"]
    intervals.append((prev, H))

    events = []
    fi = 0
    for lo, hi in intervals:
        left_in = sorted((b for b in left_bands if lo <= b["y0"] < hi), key=lambda b: b["y0"])
        right_in = sorted((b for b in right_bands if lo <= b["y0"] < hi), key=lambda b: b["y0"])
        for i, b in enumerate(left_in):
            events.append(("left", b, i == 0))
        for i, b in enumerate(right_in):
            events.append(("right", b, i == 0))
        if fi < len(full_sorted):
            events.append(("full", full_sorted[fi], None))
            fi += 1
    return events


def head_candidates(page_s1, inset_thr):
    """S2: verse / chapter / book head candidates, each carrying its printed-mark signature.
    `prev_band` tracks the last non-full column band seen in READING ORDER across BOTH columns
    (left column top->bottom, then right column top->bottom, per section -- see
    _bucket_by_interval); it resets to None whenever a full band is crossed, since a full band
    (running head, title, chapter head) breaks the paragraph-continuation context. prev_right_short
    is computed from prev_band against the MEDIAN OF PREV_BAND'S OWN COLUMN (not necessarily the
    current band's column -- the right column's first band after the left column's last line is a
    cross-column case). When prev_band is None (page start, or just after a full band),
    prev_right_short is None and the inset check alone decides is_verse -- there is no
    unconditional "first band is always a candidate" rule.

    Returns a list of candidate dicts in reading order:
      {file_page, col, y0, y1, box, kind: 'verse'|'chapter'|'book',
       signature: {inset_px, prev_right_short, centred, xheight_ratio, gap_px}}
    """
    H, W = page_s1["H"], page_s1["W"]
    fp = page_s1["file_page"]
    # full_unpaired bands (one-sided gutter-crossers: the rule under the running head) are not
    # text lines -- excluded from the medians and never candidates (they stay in rects).
    med = {c: _column_medians([b for b in page_s1.get(c, []) if not b.get("full_unpaired")])
           for c in ("left", "right")}
    events = _bucket_by_interval(page_s1["full"], page_s1["left"], page_s1["right"], H)

    out = []
    prev_band, prev_col = None, None
    for col, band, _is_first in events:
        if col == "full":
            # Centred against the TEXT BLOCK (left column's median text left .. right column's
            # median text right), not the page edge: page margins are asymmetric (binding).
            cb = page_s1.get("col_boxes") or {}
            block_x0 = (cb["left"][0] if "left" in cb else 0) + med["left"]["left_x"]
            block_x1 = (cb["right"][0] if "right" in cb else 0) + med["right"]["right_x"] if med["right"]["right_x"] else W
            left_inset = band["left_ink_x"] - block_x0
            right_inset = block_x1 - band["right_ink_x"]
            centred = (left_inset >= CENTRE_MARGIN_MULT * inset_thr and
                       right_inset >= CENTRE_MARGIN_MULT * inset_thr and
                       abs(left_inset - right_inset) <= CENTRE_ASYM_FRAC * (left_inset + right_inset) / 2)
            xh_ratio = band["xheight"] / max(1.0, med["left"]["xheight"] if med["left"]["xheight"] else med["right"]["xheight"])
            sig = {"inset_px": left_inset, "prev_right_short": None, "centred": centred,
                   "xheight_ratio": xh_ratio, "gap_px": band.get("gap_px")}
            if centred and BOOK_XHEIGHT_RATIO is not None and xh_ratio >= BOOK_XHEIGHT_RATIO:
                out.append(_cand(fp, "full", band, "book", sig))
            elif centred:
                out.append(_cand(fp, "full", band, "chapter", sig))
            prev_band, prev_col = None, None
            continue

        if band.get("full_unpaired"):
            continue
        m = med[col]
        inset_px = (band["left_ink_x"] - band["x0"]) - m["left_x"]
        if prev_band is None:
            prev_right_short = None
        else:
            prev_m = med[prev_col]
            prev_right = (prev_band["right_ink_x"] - prev_band["x0"])
            prev_right_short = prev_right < (prev_m["right_x"] - inset_thr)
        # R5: is_verse is the inset signal ALONE. prev_right_short stays in the signature
        # (informational) but no longer gates -- 17 measured indented bands were wrongly
        # suppressed because the PRECEDING line was itself full/justified (prev_short_by
        # -24..46, i.e. sometimes longer than the column median), not short. When
        # prev_right_short is explicitly False on a firing verse candidate, carry
        # "prev_line_full" as evidence for the console; the head read confirms or rejects it
        # (amendment E) -- this flag does not gate anything at this stage.
        is_verse = inset_px >= inset_thr

        # Centred against the column's TEXT BLOCK (median text left/right), not the column box:
        # the left column box includes the ~470 px page margin, so a centred CHAP head measured
        # against the box always failed |l - r| <= inset_thr.
        left_inset = (band["left_ink_x"] - band["x0"]) - m["left_x"]
        right_inset = m["right_x"] - (band["right_ink_x"] - band["x0"])
        centred = (left_inset >= CENTRE_MARGIN_MULT * inset_thr and
                   right_inset >= CENTRE_MARGIN_MULT * inset_thr and
                   abs(left_inset - right_inset) <= CENTRE_ASYM_FRAC * (left_inset + right_inset) / 2)
        xh_ratio = band["xheight"] / max(1.0, m["xheight"])
        sig = {"inset_px": inset_px, "prev_right_short": prev_right_short, "centred": centred,
               "xheight_ratio": xh_ratio, "gap_px": band.get("gap_px")}

        if centred and xh_ratio >= CHAPTER_XHEIGHT_RATIO:
            out.append(_cand(fp, col, band, "chapter", sig))
        elif is_verse:
            flags = ["prev_line_full"] if prev_right_short is False else None
            out.append(_cand(fp, col, band, "verse", sig, flags))

        prev_band, prev_col = band, col
    return out


def _cand(file_page, col, band, kind, signature, flags=None):
    return {
        "file_page": file_page, "col": col, "y0": band["y0"], "y1": band["y1"],
        "box": [band["x0"], band["y0"], band["x1"], band["y1"]],
        "kind": kind, "signature": signature, "flags": flags or [],
    }


# ==============================================================================================
# S2b — head confirmation (model read stands in for a template until step 3)
# ==============================================================================================

def confirm_candidates(candidates, head_reads=None):
    """head_reads: {(file_page,col,y0): {"ver": True|False|None, "numbers": [int]|None,
    "status": "ok"|...}} or None. Confirmation applies ONLY to 'verse' candidates -- the read
    prompt is Ver.-specific, so a chapter/book candidate would always read ver=False and cannot
    be confirmed/rejected by it; those are confirmed by geometry alone (amendment point E is
    scoped to the verse paragraph-inset signal). Returns (confirmed, rejected)."""
    head_reads = head_reads or {}
    confirmed, rejected = [], []
    for c in candidates:
        if c["kind"] != "verse":
            confirmed.append(dict(c, head_confirm=None))
            continue
        key = (c["file_page"], c["col"], c["y0"])
        hr = head_reads.get(key)
        if hr is None:
            confirmed.append(dict(c, head_confirm=None, flags=list(c.get("flags") or []) + ["head_unconfirmed"]))
            continue
        ver = hr.get("ver")
        status = hr.get("status")
        if status == "guard_refused:straddle":
            # A crop whose y-bounds cut through the middle of a line (guard_crop's straddle check)
            # cannot be trusted to carry the line's real start -- unlike other guard refusals
            # (clamped/blank/uniform/blank_band/too_short), which merely mean "nothing readable was
            # attempted" and leave the geometric candidate standing unconfirmed, a straddling crop
            # is evidence the candidate's own band boundary is WRONG, so it is rejected outright.
            rejected.append(dict(c, head_confirm=hr, reason="guard_refused:straddle"))
            continue
        if ver is False:
            rejected.append(dict(c, head_confirm=hr, reason="head_reads:no_ver"))
            continue
        if ver is None or status != "ok":
            confirmed.append(dict(c, head_confirm=hr, flags=list(c.get("flags") or []) + ["head_unconfirmed"]))
            continue
        flags = list(c.get("flags") or [])
        if hr.get("ver_case") == "lower":
            flags.append("head_ver_lowercase")
        confirmed.append(dict(c, head_confirm=hr, flags=flags))
    return confirmed, rejected


# ==============================================================================================
# S3 — number sources: count, read, witness
# ==============================================================================================

def _norm_numbers(v):
    if v is None:
        return None
    if isinstance(v, int):
        return (v,)
    return tuple(v)


def reconcile_numbers(sources):
    """sources: {"count": int|None, "read": [int..]|None, "witness": [int..]|None}. Pure rule,
    never merging silently: >=2 non-null sources must AGREE for `verse` to be set. count (an int)
    agrees with a longer tuple iff it equals its first element (narrow count rule, amendment A:
    count is only ever a bare '1', never a full group)."""
    present = [(name, sources.get(name)) for name in ("count", "read", "witness") if sources.get(name) is not None]
    if len(present) == 0:
        return {"numbers_link_status": "numbers_none", "numbers_disagree_pairs": [], "verse": None}
    if len(present) == 1:
        return {"numbers_link_status": "numbers_single_source", "numbers_disagree_pairs": [], "verse": None}

    norm = {name: _norm_numbers(val) for name, val in present}
    names = [n for n, _ in present]
    disagree_pairs = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            va, vb = norm[a], norm[b]
            if va == vb:
                continue
            if len(va) == 1 and len(vb) > 1 and va[0] == vb[0]:
                continue
            if len(vb) == 1 and len(va) > 1 and vb[0] == va[0]:
                continue
            disagree_pairs.append(f"{a}|{b}")
    if disagree_pairs:
        return {"numbers_link_status": "numbers_disagree", "numbers_disagree_pairs": disagree_pairs, "verse": None}

    best = None
    for name in ("read", "witness", "count"):
        if name in norm and (best is None or len(norm[name]) > len(best)):
            best = norm[name]
    return {"numbers_link_status": "numbers_agree", "numbers_disagree_pairs": [], "verse": list(best)}


def assert_numbering_invariant(records):
    """records: region records (or anything carrying 'verse', 'numbers_link_status',
    'number_sources'). Raises ValueError NAMING the region if any has verse set without >=2
    agreeing non-null sources. Fail loud -- this is the condition-1 born invariant."""
    for r in records:
        if r.get("verse") is not None:
            srcs = r.get("number_sources") or {}
            non_null = [v for v in srcs.values() if v is not None]
            if r.get("numbers_link_status") != "numbers_agree" or len(non_null) < 2:
                label = r.get("file_page_first", r.get("file_page", "?"))
                raise ValueError(
                    f"numbering invariant violated in region at file_page {label!r}: verse="
                    f"{r['verse']!r} set without >=2 agreeing sources "
                    f"(link_status={r.get('numbers_link_status')!r}, sources={srcs!r})")


_VER_LINE_RE = re.compile(r'(?m)^\s*\**Ver\.\s*')
_CHAP_RE = re.compile(r'(?m)^\s*#\s*Chapter\b.*$')

# One code-owned verse-number parser, shared by parse_ver_head (the model-read / canary path) and
# parse_witness (the old vol.1 .md). The old _VER_RE (`([0-9][0-9, ]*)`) stopped at a dash, so
# witness "Ver. 12--14" parsed as [12] and "Ver. 28-34" as [28] -- this replaced it.
_VER_HEAD_RE = re.compile(r'Ver[.,]?')
# Lowercase "ver" is only treated as a head with REQUIRED punctuation (unlike the capital form,
# where the '.'/',' is optional) -- "ver 3" reads as prose ("ver" is a common word fragment/OCR
# noise), "ver. 3"/"ver, 3" reads as a head. See parse_ver_head.
_VER_HEAD_LOWER_RE = re.compile(r'ver[.,]')
_DASHES = "-–—"  # hyphen, en dash, em dash
_NUM_ITEM_RE = re.compile(r'\s*([0-9]+)(?:\s*[' + _DASHES + r']\s*([0-9]+))?')
RANGE_SPAN_MAX = 20  # a "Ver. N-M" range wider than this is implausible, never silently trusted


def _parse_number_items(s):
    """Parse a comma-separated list of 'N' or 'N<dash>M' items (dash in -, en dash, em dash) from
    the START of s, whitespace tolerant. Returns (items, consumed_end): items is an ordered list of
    (n, m_or_None) int tuples; consumed_end is the index in s right after the last matched item
    (not including any trailing separator/whitespace). items == [] if nothing matched at position 0
    ("Ver" with no number spec following)."""
    items = []
    pos = 0
    first = True
    while True:
        start = pos
        if not first:
            sep = re.match(r'\s*,', s[pos:])
            if not sep:
                break
            start = pos + sep.end()
        m = _NUM_ITEM_RE.match(s, start)
        if not m or m.start() != start:
            break
        n = int(m.group(1))
        mm = int(m.group(2)) if m.group(2) else None
        items.append((n, mm))
        pos = m.end()
        first = False
    return items, pos


def _expand_number_items(items):
    """(expanded_list, implausible): expands each (n, m) range inclusively; implausible iff any
    range has m<=n or a span > RANGE_SPAN_MAX, or the full expanded list is not strictly ascending."""
    implausible = False
    expanded = []
    for n, mm in items:
        if mm is None:
            expanded.append(n)
        else:
            if not (mm > n and (mm - n) <= RANGE_SPAN_MAX):
                implausible = True
            expanded.extend(range(n, mm + 1))
    if not implausible:
        for a, b in zip(expanded, expanded[1:]):
            if not (b > a):
                implausible = True
                break
    return expanded, implausible


def parse_ver_head(text):
    """Code-owned transcription parser for a head-candidate crop read (verse_head_read.read_head):
    the model's job is to TRANSCRIBE the line exactly, never to classify it -- this function alone
    decides ver/numbers/status from the transcription, so there is one parser, not one per caller.

    Returns dict(ver, numbers, raw_head, status, ver_case):
      status "empty"            -- text is empty/whitespace-only; ver=None, numbers=None,
                                    ver_case=None.
      status "no_ver"           -- does not start (after up to 3 leading non-alnum chars) with
                                    capital "Ver" + optional '.'/',' , NOR with lowercase "ver" +
                                    REQUIRED '.'/','; ver=False, numbers=None, ver_case=None.
      status "unparsed"         -- "Ver" present but no number spec follows; ver=True, numbers=None
                                    (capital only -- see below); ver_case="upper".
      status "range_implausible"-- a number spec parsed but failed plausibility (see
                                    _expand_number_items); ver=True, numbers=None (capital only --
                                    see below); ver_case="upper".
      status "ok"               -- ver=True, numbers = the expanded, strictly-ascending list;
                                    ver_case="upper" or "lower".
    raw_head is the matched "Ver..."/"ver..." prefix string (through the parsed number spec, when
    any).

    Lowercase "ver" (punctuation REQUIRED: "ver." / "ver,", never bare "ver") is tried only when the
    capital form does not match at the same position. A lowercase match without a plausible number
    spec is "no_ver", never "unparsed"/"range_implausible": the lowercase form is accepted only when
    the whole head (punctuation + number) is present (one measured instance, 745L "ver. 1.")."""
    s = (text or "").strip()
    if not s:
        return {"ver": None, "numbers": None, "raw_head": None, "status": "empty", "ver_case": None}
    i = 0
    while i < min(3, len(s)) and not s[i].isalnum():
        i += 1
    rest = s[i:]
    m = _VER_HEAD_RE.match(rest)
    if m:
        after = rest[m.end():]
        items, consumed = _parse_number_items(after)
        if not items:
            return {"ver": True, "numbers": None, "raw_head": rest[:m.end()], "status": "unparsed",
                    "ver_case": "upper"}
        expanded, implausible = _expand_number_items(items)
        raw_head = rest[:m.end() + consumed]
        if implausible:
            return {"ver": True, "numbers": None, "raw_head": raw_head,
                    "status": "range_implausible", "ver_case": "upper"}
        return {"ver": True, "numbers": expanded, "raw_head": raw_head, "status": "ok",
                "ver_case": "upper"}

    lm = _VER_HEAD_LOWER_RE.match(rest)
    if lm:
        after = rest[lm.end():]
        items, consumed = _parse_number_items(after)
        if items:
            expanded, implausible = _expand_number_items(items)
            if not implausible:
                raw_head = rest[:lm.end() + consumed]
                return {"ver": True, "numbers": expanded, "raw_head": raw_head, "status": "ok",
                        "ver_case": "lower"}
        return {"ver": False, "numbers": None, "raw_head": None, "status": "no_ver",
                "ver_case": None}

    return {"ver": False, "numbers": None, "raw_head": None, "status": "no_ver", "ver_case": None}


def parse_witness(md_text):
    """Pure string parse of the witness .md: verse-head numbers, verse-head trailing text, and
    chapter-head count, in reading order top to bottom. Counts and numbers ONLY from the numbers --
    never geometry. Witness lines are matched as today (line start, optional leading '*'s, literal
    "Ver."); the number spec after it uses the SAME shared parser as parse_ver_head, so e.g.
    "Ver. 12--14" -> [12,13,14], not [12].

    "verse_lines": for each verse head, the running text AFTER the number spec, to the end of that
    line (exactly simdiag2.py's wit_heads: text[m.end()+consumed:].split('\\n',1)[0]) -- the key
    material for align_witness, which pairs heads by this TEXT, never by the numbers themselves."""
    verse_heads = []
    verse_lines = []
    text = md_text or ""
    for m in _VER_LINE_RE.finditer(text):
        items, consumed = _parse_number_items(text[m.end():])
        nums, _implausible = _expand_number_items(items) if items else ([], False)
        verse_heads.append(nums)
        verse_lines.append(text[m.end() + consumed:].split('\n', 1)[0])
    chapter_count = len(_CHAP_RE.findall(text))
    return {"verse_heads": verse_heads, "verse_lines": verse_lines, "chapter_count": chapter_count}


# ------------------------------------------------------------------------------------------------
# Witness pairing by TEXT-SIMILARITY SEQUENCE ALIGNMENT (replaces positional pairing).
#
# pair_witness_numbers (deleted) only paired when the page's read head-count equaled the witness
# head-count, and then paired strictly by POSITION -- a single missed/extra head anywhere on the
# page nulled out EVERY witness number on that page (30 of 69 heads in rerun 1). Aligning by the
# TEXT after each head (never by the verse numbers, which would make any agreement check
# tautological) survives a missing/extra head: only the heads actually out of step are affected.
# ------------------------------------------------------------------------------------------------

ALIGN_SIM_MID = 0.5     # a read/witness line-key pair below this difflib ratio is not even a
                         # CANDIDATE pair (the alignment weight w = sim - mid must be > 0 to be
                         # usable at all) -- the midpoint of the ratio scale, separating "these are
                         # probably the same line" from "probably not", used as a pair FLOOR, not a
                         # decision threshold (the DP below decides the actual pairing).
ALIGN_KEY_CHARS = 24     # read-head key length: the value the offline measurement used (half-width
                         # crops give read keys of 3-24 chars); not tuned.

_ALIGN_KEY_CLEAN_RE = re.compile(r'[^a-z ]+')


def align_key(s, n=None):
    """Lowercase; any run of non-[a-z ] characters -> a single space; collapse whitespace; strip;
    truncate to n characters if given. The shared text-similarity key for both a read head's
    trailing text and a witness line (simdiag2.py's key())."""
    s = _ALIGN_KEY_CLEAN_RE.sub(' ', (s or '').lower())
    s = re.sub(r'\s+', ' ', s).strip()
    return s[:n] if n is not None else s


def _read_key_text(head_confirm):
    """The text after a read head's raw_head (aligndiag.py's read_key()): the words that follow
    'Ver. N' on the SAME transcribed line -- the alignment key is always this trailing text, never
    the verse numbers. '' when there is no head_confirm text at all (such a head can never pair)."""
    hc = head_confirm or {}
    txt = (hc.get("text") or "").strip()
    if not txt:
        return ""
    rh = hc.get("raw_head") or ""
    i = txt.find(rh) if rh else -1
    return txt[i + len(rh):] if i >= 0 else txt


def _align_sim(rk, wline):
    """difflib ratio between an already align_key'd read key `rk` and a raw witness line, keyed
    and truncated to match rk's length (simdiag2.py's sim())."""
    wk = align_key(wline)[:max(len(rk), 1)]
    return difflib.SequenceMatcher(None, rk, wk).ratio()


def align_witness(read_keys, witness_lines, mid=ALIGN_SIM_MID):
    """Order-preserving (strictly increasing i and j), max-weight alignment between read_keys
    (already align_key'd+truncated text keys, one per verse head in reading order) and
    witness_lines (raw witness line strings, one per witness verse head in order). Weight
    w(i,j) = sim(read_keys[i], witness_lines[j]) - mid; a pair is only allowed if w > 0. The verse
    NUMBERS are never an input here.

    A pair (i,j) is ESSENTIAL iff it is present in EVERY optimal alignment: forbidding it strictly
    lowers the achievable total weight. Returns a list, one entry per read head (reading order):
    ("paired", j)      -- has an essential partner j.
    ("ambiguous", None) -- appears in at least one optimal alignment but has no essential partner
                           (e.g. two witness lines with near-identical keys competing for it).
    ("unpaired", None)  -- never appears in any optimal alignment (no candidate pair, or always
                           loses to a better one)."""
    n, m = len(read_keys), len(witness_lines)
    W = [[_align_sim(rk, wl) - mid for wl in witness_lines] for rk in read_keys]

    def best_table(forbid=None):
        # dp[i][j] = best achievable weight using read[i:], witness[j:].
        dp = [[0.0] * (m + 1) for _ in range(n + 1)]
        for i in range(n - 1, -1, -1):
            for j in range(m - 1, -1, -1):
                val = dp[i + 1][j] if dp[i + 1][j] > dp[i][j + 1] else dp[i][j + 1]
                w = W[i][j]
                if w > 0 and (forbid is None or (i, j) != forbid):
                    cand = dp[i + 1][j + 1] + w
                    if cand > val:
                        val = cand
                dp[i][j] = val
        return dp

    suf = best_table()
    opt = suf[0][0]

    # pre[i][j] = best achievable weight using read[0:i], witness[0:j] (forward/prefix DP).
    pre = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            val = pre[i - 1][j] if pre[i - 1][j] > pre[i][j - 1] else pre[i][j - 1]
            w = W[i - 1][j - 1]
            if w > 0:
                cand = pre[i - 1][j - 1] + w
                if cand > val:
                    val = cand
            pre[i][j] = val

    candidates = [
        (i, j) for i in range(n) for j in range(m)
        if W[i][j] > 0 and abs(pre[i][j] + W[i][j] + suf[i + 1][j + 1] - opt) < 1e-9
    ]

    essential = {}
    ambiguous_i = set()
    for (i, j) in candidates:
        without = best_table(forbid=(i, j))[0][0]
        if without < opt - 1e-9:
            essential[i] = j
        else:
            ambiguous_i.add(i)

    out = []
    for i in range(n):
        if i in essential:
            out.append(("paired", essential[i]))
        elif i in ambiguous_i:
            out.append(("ambiguous", None))
        else:
            out.append(("unpaired", None))
    return out


# ==============================================================================================
# S4 — assemble regions across an ordered list of pages
# ==============================================================================================

def _new_region(kind, file_page, col, head, sources, config):
    return {
        "kind": kind, "file_page_first": file_page,
        "head": {"file_page": file_page, "col": col, "y0": head["y0"], "y1": head["y1"],
                 "box": head["box"], "signature": head["signature"],
                 "head_confirm": head.get("head_confirm")},
        "flags": list(head.get("flags") or []),
        "rects": [],
        "_rect_index": {},
        "number_sources": dict(sources),
        "tier": "best_effort",
        "config": config,
    }


def _extend_region_rect(region, file_page, col, band, full_basis=None):
    key = (file_page, col)
    x0 = band["x0"]
    x1 = band["x1"]
    if key in region["_rect_index"]:
        rect = region["_rect_index"][key]
        rect["box"][1] = min(rect["box"][1], band["y0"])
        rect["box"][3] = max(rect["box"][3], band["y1"])
    else:
        rect = {"file_page": file_page, "col": col, "box": [x0, band["y0"], x1, band["y1"]],
                "full_basis": full_basis}
        region["_rect_index"][key] = rect
        region["rects"].append(rect)


def _finalize_region(region):
    region.pop("_rect_index", None)
    return region


def _count_ink_bands(region, page_s1_by_page):
    """Region emptiness FROM BANDS, not a counter: for each of the region's rects, count the S1
    bands (left/right/full of that page) whose [y0,y1) lies INSIDE the rect's [y0,y1) on that same
    file_page and column ('full' rects count against the page's 'full' bands). The head band
    itself is always inside its own rect (FIX5 extends the rect to the head band on open), so a
    region with a confirmed head and nothing else counts 1, not 0."""
    count = 0
    for rect in region["rects"]:
        fp, col = rect["file_page"], rect["col"]
        s1 = page_s1_by_page.get(fp)
        if s1 is None:
            continue
        rx0, ry0, rx1, ry1 = rect["box"]
        for b in s1.get(col) or []:
            if b["y0"] >= ry0 and b["y1"] <= ry1:
                count += 1
    return count


def _count_sliver_bands(region, page_s1_by_page):
    """Visibility counterpart to _count_ink_bands: how many of a region's rects contain a sliver
    (speck/noise band held out by R2's _split_slivers) in their [y0,y1) range. Slivers never
    count toward n_ink_bands / region_empty / head_only -- this is reporting only."""
    count = 0
    for rect in region["rects"]:
        fp, col = rect["file_page"], rect["col"]
        s1 = page_s1_by_page.get(fp)
        if s1 is None:
            continue
        rx0, ry0, rx1, ry1 = rect["box"]
        for b in s1.get("slivers") or []:
            if b["col"] == col and b["y0"] >= ry0 and b["y1"] <= ry1:
                count += 1
    return count


_CHAIN_KINDS = {"verse", "chapter_intro", "book_intro", "continuation_unanchored"}


def _chains(regions):
    """Split `regions` (in order) into chains of consecutive VERSE regions, exactly as
    ascdiag.chains: a chapter_intro or book_intro region always starts a new chain; any region
    (of a recognized kind) whose file_page_first is not the previous recognized region's page or
    that page + 1 also starts a new chain (a chain must not silently cross a page the walk never
    saw); any kind outside _CHAIN_KINDS is invisible to this walk -- it neither enters a chain nor
    resets one. Only verse regions are ever appended to a chain; chapter_intro/book_intro/
    continuation_unanchored participate only as reset/continuity markers."""
    chains_out = []
    cur = []
    prev = None
    for r in regions:
        kind = r.get("kind")
        if kind not in _CHAIN_KINDS:
            continue
        fp = r["file_page_first"]
        if kind in ("chapter_intro", "book_intro") or (prev is not None and fp not in (prev, prev + 1)):
            if cur:
                chains_out.append(cur)
            cur = []
        if kind == "verse":
            cur.append(r)
        prev = fp
    if cur:
        chains_out.append(cur)
    return chains_out


def disputed(seq):
    """Given `seq` (one entry per chain element, each a list of numbers for that element's source
    or a falsy value when the source has nothing for it), return the set of indices that violate
    the ascending invariant for THIS source alone -- exactly ascdiag.disputed.

    lt(a, b) is true iff element a's numbers are entirely below element b's (max(seq[a]) <
    min(seq[b])): a range only counts as "ascending into" another range if there is no overlap.
    f[i]/g[i] are the longest lt-chain ending/starting at i (a longest-increasing-subsequence DP
    over the partial order lt); an index is KEPT (not disputed) only if it lies on a longest chain
    (f[i]+g[i]-1 == the global longest chain length L) AND is the UNIQUE element at its f-layer
    among on-chain elements (ties at a layer mean more than one candidate claims that position in
    the longest run, so none of them is trustworthy on its own). Every element with numbers that
    is not kept is disputed; elements with nothing (falsy) are never disputed (nothing to check)."""
    idx = [i for i, v in enumerate(seq) if v]
    if not idx:
        return set()

    def lt(a, b):
        return max(seq[a]) < min(seq[b])

    f, g = {}, {}
    for i in idx:
        f[i] = 1 + max([f[j] for j in idx if j < i and lt(j, i)], default=0)
    for i in reversed(idx):
        g[i] = 1 + max([g[j] for j in idx if j > i and lt(i, j)], default=0)
    L = max(f.values())
    on = [i for i in idx if f[i] + g[i] - 1 == L]
    layer = Counter(f[i] for i in on)
    keep = {i for i in on if layer[f[i]] == 1}
    return set(idx) - keep


def _new_unanchored(fp, leading_events, config):
    """A continuation_unanchored region from a page's (col, band) events before its first head."""
    unanchored = {
        "kind": "continuation_unanchored", "file_page_first": fp,
        "head": None, "flags": [], "rects": [], "_rect_index": {},
        "number_sources": {"count": None, "read": None, "witness": None},
        "tier": "best_effort", "config": config,
    }
    for col, band in leading_events:
        _extend_region_rect(unanchored, fp, col, band,
                            band.get("full_basis", "gutter_ink") if col == "full" else None)
    return unanchored


def assemble_regions(page_records, page_s1_by_page, candidates_by_page, rejected_by_page,
                      witness_by_page, config, abstained=False):
    """Walk confirmed heads in reading order across `page_records` (ordered list of dicts with
    at least 'file_page'; pages chain ONLY if consecutive file pages) and build region records.

    candidates_by_page: file_page -> confirmed-candidate list (from confirm_candidates).
    rejected_by_page: file_page -> rejected-candidate list (kept, never dropped).
    witness_by_page: file_page -> parsed witness dict (parse_witness output) or None.
    abstained: True when the run-wide inset threshold could not be derived (not bimodal). Every
    page is then skipped WITHOUT walking its bands at all -- no verse/continuation/intro regions
    are claimed for it (an abstained page must not look like a page that was checked and found to
    have no heads). page_summaries still gets an entry per page, with "head_detection": "abstained"
    (vs. "ok" otherwise) and every count zeroed, so build_verse_regions.py can still emit its
    per-page "page" record. Since every page is skipped, open_region never opens, so regions is []
    and the S3/S5 passes below run over an empty list -- region_empty/invariant checks never fire.

    Returns (regions, page_summaries) where page_summaries carries S5 per-page flags/counts.
    """
    regions = []
    open_region = None
    awaiting_count = False     # True right after a chapter head, consumed by the next verse head
    prev_fp = None
    page_summaries = {}

    for rec in page_records:
        fp = rec["file_page"]
        s1 = page_s1_by_page[fp]

        # A pending chapter count never crosses a page gap -- the same rule _chains applies to the
        # ascending check. Rerun 2: the chapter head on 404 set it, 404's verse heads were not
        # candidates, and it leaked to 745R "Ver. 4" as count 1. Dropping it is flagged on the page
        # that set it, never silent.
        if awaiting_count and not (prev_fp is not None and fp == prev_fp + 1):
            page_summaries[prev_fp]["flags"].append("chapter_count_dropped_at_page_gap")
            awaiting_count = False

        if abstained:
            page_summaries[fp] = {
                "file_page": fp,
                "n_heads": 0,
                "n_rejected_candidates": len(rejected_by_page.get(fp, [])),
                "n_verse_heads": 0,
                "n_witness_paired": 0,
                "n_witness_ambiguous": 0,
                "n_witness_unpaired": 0,
                "flags": ["head_detection_abstained:inset_not_bimodal"],
                "column_order_suspect": False,
                "gutter_ink_crossing": [],
                "n_gutter_ambiguous": 0,
                "n_slivers": len(s1.get("slivers") or []),
                "n_centred_pairs": s1.get("n_centred_pairs", 0),
                "n_full_unpaired": sum(1 for c in ("left", "right")
                                        for b in (s1.get(c) or []) if b.get("full_unpaired")),
                "rejected_candidates": rejected_by_page.get(fp, []),
                "head_detection": "abstained",
            }
            prev_fp = fp
            continue

        H = s1["H"]
        confirmed = candidates_by_page.get(fp, [])
        rejected = rejected_by_page.get(fp, [])
        heads_by_key = {(h["col"], h["y0"]): h for h in confirmed}

        # witness pairing for this page's verse heads, by TEXT-SIMILARITY SEQUENCE ALIGNMENT
        # (align_witness) -- never by position and never by the verse numbers themselves (see the
        # comment above align_witness for why positional pairing was replaced).
        witness = witness_by_page.get(fp)
        events = _bucket_by_interval(s1["full"], s1["left"], s1["right"], H)
        verse_head_keys_in_order = [
            (col, band["y0"]) for col, band, _ in events
            if (col, band["y0"]) in heads_by_key and heads_by_key[(col, band["y0"])]["kind"] == "verse"
        ]
        layout_verse_count = len(verse_head_keys_in_order)
        n_witness_paired = n_witness_ambiguous = n_witness_unpaired = 0
        if witness is not None:
            read_keys = [align_key(_read_key_text(heads_by_key[key].get("head_confirm")), ALIGN_KEY_CHARS)
                         for key in verse_head_keys_in_order]
            witness_lines = witness["verse_lines"]
            alignment = align_witness(read_keys, witness_lines)
            head_count_vs_witness = layout_verse_count != len(witness["verse_heads"])
            witness_slot = {}
            for key, rk, (status, j) in zip(verse_head_keys_in_order, read_keys, alignment):
                if status == "paired":
                    witness_slot[key] = {"pairing": "paired", "numbers": witness["verse_heads"][j],
                                          "sim": round(_align_sim(rk, witness_lines[j]), 3)}
                    n_witness_paired += 1
                else:
                    witness_slot[key] = {"pairing": status, "numbers": None, "sim": None}
                    if status == "ambiguous":
                        n_witness_ambiguous += 1
                    else:
                        n_witness_unpaired += 1
        else:
            head_count_vs_witness = None
            witness_slot = {key: {"pairing": "no_witness", "numbers": None, "sim": None}
                            for key in verse_head_keys_in_order}

        chapter_heads_here = sum(1 for h in confirmed if h["kind"] == "chapter")
        chapter_count_vs_witness = (
            None if witness is None else (chapter_heads_here != witness["chapter_count"]))

        chained = (prev_fp is not None and fp == prev_fp + 1 and open_region is not None)
        leading_events = []
        seen_head_on_page = False
        column_order_suspect = False
        seen_left_in_section = False

        page_flags = []
        if head_count_vs_witness:
            page_flags.append("head_count_vs_witness")
        if chapter_count_vs_witness:
            page_flags.append("chapter_count_vs_witness")

        gutter_ambiguous_y0 = []
        for col, band, _is_first in events:
            # A full band is a section boundary for column-order purposes, but it is NOT skipped:
            # a centred chapter/book head lives in a full band, and full-width text belongs to the
            # open region (skipping dropped both silently).
            if col == "full":
                seen_left_in_section = False
            elif col == "left":
                seen_left_in_section = True
            elif col == "right" and not seen_left_in_section:
                column_order_suspect = True
            if band.get("gutter_ambiguous"):
                gutter_ambiguous_y0.append(band["y0"])

            key = (col, band["y0"])
            head = heads_by_key.get(key)
            if head is not None:
                first_on_page = not seen_head_on_page
                seen_head_on_page = True
                kind = head["kind"]
                if kind == "verse":
                    count = 1 if awaiting_count else None
                    awaiting_count = False
                    read_numbers = None
                    hc = head.get("head_confirm")
                    if hc and hc.get("ver") is True:
                        read_numbers = hc.get("numbers")
                    wp = witness_slot.get(key, {"pairing": "no_witness", "numbers": None, "sim": None})
                    sources = {"count": count, "read": read_numbers, "witness": wp["numbers"]}
                    region = _new_region("verse", fp, col, head, sources, config)
                    region["witness_pairing"] = wp["pairing"]
                    region["witness_sim"] = wp["sim"]
                    if wp["pairing"] == "ambiguous":
                        region["flags"] = list(region.get("flags") or []) + ["witness_alignment_ambiguous"]
                    elif wp["pairing"] == "unpaired":
                        region["flags"] = list(region.get("flags") or []) + ["witness_unpaired"]
                elif kind == "chapter":
                    awaiting_count = True
                    region = _new_region("chapter_intro", fp, col, head,
                                          {"count": None, "read": None, "witness": None}, config)
                else:  # book
                    awaiting_count = False
                    region = _new_region("book_intro", fp, col, head,
                                          {"count": None, "read": None, "witness": None}, config)
                # FIX5: the head band belongs to its own region -- extend the region's rect to the
                # head line itself so region rects start there, not at the next body band.
                full_basis = band.get("full_basis", "gutter_ink") if col == "full" else None
                _extend_region_rect(region, fp, col, band, full_basis)
                if first_on_page and leading_events:
                    # The page's text BEFORE its first head is settled HERE, while open_region is still
                    # the previous page's region: chained -> it continues that region; otherwise it is an
                    # unanchored continuation listed before this head's region. (Settling it after the
                    # band loop gave it to the page's LAST region: 91's whole left column and 6 right
                    # lines went to Ver. 2 instead of Ver. 1; 92's Ver. 4 overlapped Ver. 3.)
                    if chained:
                        for lcol, lband in leading_events:
                            _extend_region_rect(open_region, fp, lcol, lband,
                                                lband.get("full_basis", "gutter_ink") if lcol == "full" else None)
                        regions.append(_finalize_region(open_region))
                    else:
                        if open_region is not None:
                            regions.append(_finalize_region(open_region))
                        regions.append(_finalize_region(_new_unanchored(fp, leading_events, config)))
                    leading_events = []
                elif open_region is not None:
                    regions.append(_finalize_region(open_region))
                open_region = region
            else:
                if not seen_head_on_page:
                    # content before this PAGE's first head: belongs to the previous page's open
                    # region only if the pages chain (consecutive file pages); routed below.
                    leading_events.append((col, band))
                else:
                    full_basis = band.get("full_basis", "gutter_ink") if col == "full" else None
                    _extend_region_rect(open_region, fp, col, band, full_basis)

        if leading_events:
            # Only a page with NO head reaches here (a head settles them above); open_region is still
            # the previous page's region.
            assert not seen_head_on_page
            if chained:
                for col, band in leading_events:
                    full_basis = band.get("full_basis", "gutter_ink") if col == "full" else None
                    _extend_region_rect(open_region, fp, col, band, full_basis)
            else:
                regions.append(_finalize_region(_new_unanchored(fp, leading_events, config)))

        page_summaries[fp] = {
            "file_page": fp,
            "n_heads": len(confirmed),
            "n_rejected_candidates": len(rejected),
            "n_verse_heads": layout_verse_count,
            "n_witness_paired": n_witness_paired,
            "n_witness_ambiguous": n_witness_ambiguous,
            "n_witness_unpaired": n_witness_unpaired,
            "flags": page_flags,
            "column_order_suspect": column_order_suspect,
            "gutter_ink_crossing": gutter_ambiguous_y0,
            "n_gutter_ambiguous": len(gutter_ambiguous_y0),
            "n_slivers": len(s1.get("slivers") or []),
            "n_centred_pairs": s1.get("n_centred_pairs", 0),
            "n_full_unpaired": sum(1 for c in ("left", "right") for b in (s1.get(c) or []) if b.get("full_unpaired")),
            "rejected_candidates": rejected,
            "head_detection": "ok",
        }
        prev_fp = fp

    if open_region is not None:
        regions.append(_finalize_region(open_region))

    # S3 numbering (reconcile per-source numbers into the agreed region["verse"])
    for region in regions:
        rn = reconcile_numbers(region["number_sources"])
        region["numbers_link_status"] = rn["numbers_link_status"]
        region["numbers_disagree_pairs"] = rn["numbers_disagree_pairs"]
        region["verse"] = rn["verse"]
        # FIX5: emptiness FROM BANDS, not a counter -- region_empty (ERROR) and head_only (info).
        n_ink_bands = _count_ink_bands(region, page_s1_by_page)
        region["n_ink_bands"] = n_ink_bands
        region["n_sliver_bands"] = _count_sliver_bands(region, page_s1_by_page)
        region_empty = n_ink_bands == 0
        head_only = region.get("head") is not None and n_ink_bands == 1
        region["region_empty"] = region_empty
        region["head_only"] = head_only
        flags = list(region.get("flags") or [])
        if region_empty:
            flags.append("region_empty")
        if head_only:
            flags.append("head_only")
        region["flags"] = flags

    # S5 ascending invariant, per NUMBER SOURCE (replaces the single-source verse_not_ascending
    # check). That check only looked at the RECONCILED region["verse"], which is None on a
    # disagreement, so it could not see one: 0d5622e's check never fired on 126R 22->32,
    # 127R 24->21, 404R 2->35. It also chained across page gaps (92->126); _chains resets there.
    # Checked independently per source (read, witness); flags only -- never changes region["verse"].
    for chain in _chains(regions):
        disputed_by = [set() for _ in chain]
        for src in ("read", "witness"):
            seq = [r["number_sources"].get(src) for r in chain]
            for i in disputed(seq):
                disputed_by[i].add(src)
        for region, srcs in zip(chain, disputed_by):
            region["disputed"] = bool(srcs)
            region["disputed_by"] = sorted(srcs)
            if srcs:
                flags = list(region.get("flags") or [])
                flags.extend(f"verse_order_disputed:{src}" for src in sorted(srcs))
                region["flags"] = flags

    return regions, page_summaries


# ==============================================================================================
# box_sanity adapter
# ==============================================================================================

def adapter_geom(geom_record, col, head_bottom_y):
    """One box_sanity geom per COLUMN (box_sanity takes a single gutter+rule_y; the geometry
    record carries a rule per column), built fresh per region-rect check. title_frac is the
    MEASURED running-head bottom / H, never the fossil fixed 0.03."""
    W, H = geom_record["page"][0], geom_record["page"][1]
    xdiv = geom_record["xdiv"]
    rules = geom_record.get("rules") or [None, None]
    rule_y = (rules[0] if col == "left" else rules[1]) if col in ("left", "right") else None
    if rule_y is None:
        rule_y = H
    title_frac = (head_bottom_y / H) if head_bottom_y else 0.0
    return {"W": W, "H": H, "gutter": xdiv, "rule_y": rule_y, "title_frac": title_frac}


def check_region_rects(regions, geom_records_by_page):
    """Runs box_sanity.check_box on every rect of every region, via the per-column adapter.
    'full' rects use checker 'full_width_rule' and are EXPECTED to be rejected by the per-column
    geometry (they straddle the gutter by construction) -- that rejection is recorded, not
    silently passed. Mutates each rect in place with a 'sanity' key; returns nothing."""
    for region in regions:
        for rect in region["rects"]:
            fp, col = rect["file_page"], rect["col"]
            geom_record = geom_records_by_page.get(fp)
            if geom_record is None:
                rect["sanity"] = {"disposition": "reject", "reason": "no_geometry", "checker": "box_sanity"}
                continue
            running_head = None
            s1 = geom_record.get("_s1")
            if s1 is not None and s1.get("running_head") is not None:
                running_head = s1["running_head"]["y1"]
            if col == "full":
                adapter = adapter_geom(geom_record, "left", running_head)
                disp, reason = box_sanity.check_box(rect["box"], adapter)
                rect["sanity"] = {"disposition": disp, "reason": reason, "checker": "full_width_rule"}
            else:
                adapter = adapter_geom(geom_record, col, running_head)
                disp, reason = box_sanity.check_box(rect["box"], adapter)
                rect["sanity"] = {"disposition": disp, "reason": reason, "checker": "box_sanity"}
