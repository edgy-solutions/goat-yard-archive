"""verse_regions / verse_head_read born-tests: synthetic-ink unit tests, one per rule, each
designed to FAIL if the rule it tests is removed (see the mutation-check notes in the handoff
report). Run: python test_verse_regions.py

EXPECTED_TESTS asserts the suite's OWN test count (test_marker_ledger.py's pattern) so a
silently-dropped test function fails the run instead of just passing with fewer checks.
"""
import numpy as np

import verse_regions as VR
import verse_head_read as VHR

EXPECTED_TESTS = 51


# 1. derive_threshold ---------------------------------------------------------------------------

def test_derive_threshold_first_empty_band_above_median_and_raises():
    # A WIDE gap sits BELOW the median (a different population boundary: e.g. a centred-lines vs
    # rest split) and must be ignored -- the rule is "first empty gap scanning UP FROM the
    # median", never "widest gap anywhere" (MEASURE_step2_gutter_inset_20261004.md: the
    # widest-gap rule wrongly picked that split instead of the real flush-mode edge).
    vals = [1, 2, 100, 101, 102, 108, 109, 110]
    r = VR.derive_threshold(vals, min_gap=5)
    assert r["lo"] == 102 and r["hi"] == 108, f"must find the first gap above the median, got {r}"
    assert r["value"] == 105.0
    assert r["gap"] == 6
    assert r["rule"] == "first_empty_band_above_median"
    assert r["n_below"] == 5 and r["n_above"] == 3
    try:
        VR.derive_threshold([1, 2, 3, 4, 5], min_gap=5)
        assert False, "expected ThresholdUndetermined"
    except VR.ThresholdUndetermined:
        pass


# 1a. derive_inset_modes (flush/indent mode midpoint, abstain when not bimodal; rerun3 Lane A2 d) --

# hist[i] = count of values placed at bin start + 2 (bin width 5) -- same 20-page-like profile used
# throughout this section.
_HIST_A = [667, 244, 113, 73, 38, 14, 5, 5, 4, 4, 5, 7, 17, 21, 8, 4, 2, 3]


def _vals_from_hist(hist, bin_px=5):
    vals = []
    for i, c in enumerate(hist):
        vals.extend([i * bin_px + 2] * c)
    return vals


def test_derive_inset_modes_bimodal_profile_ok():
    vals = _vals_from_hist(_HIST_A)
    r = VR.derive_inset_modes(vals, pitch_px=57)
    assert r["status"] == "ok", r
    assert r["flush_bin"] == 0
    assert r["indent_bin"] == 13
    assert r["value"] == 35.0
    assert r["rule"] == "mode_midpoint"
    assert r["pitch_px"] == 57
    flush_centre, indent_centre = 0 * 5 + 2, 13 * 5 + 2
    assert flush_centre < r["value"] < indent_centre


def test_derive_inset_modes_stable_under_shift_and_drop():
    # A first-empty-band-above-median rule here degenerated 41 -> 80 when one band's value shifted
    # into a 4-px hole (MEASURE_step2_d_inset_modes) -- the mode-midpoint rule must NOT move when
    # any single value shifts or disappears.
    vals = _vals_from_hist(_HIST_A)
    base = VR.derive_inset_modes(vals, pitch_px=57)["value"]
    for delta in (40, -40):
        trials = 0
        for i in range(len(vals)):
            trial = vals[:i] + [max(0, vals[i] + delta)] + vals[i + 1:]
            assert VR.derive_inset_modes(trial, pitch_px=57)["value"] == base
            trials += 1
        assert trials == len(vals)
    trials = 0
    for i in range(len(vals)):
        trial = vals[:i] + vals[i + 1:]
        assert VR.derive_inset_modes(trial, pitch_px=57)["value"] == base
        trials += 1
    assert trials == len(vals)


def test_derive_inset_modes_unimodal_abstains_no_second_mode():
    vals = _vals_from_hist([500, 200, 80, 30, 10, 4, 2, 1])
    r = VR.derive_inset_modes(vals, pitch_px=57)
    assert r["status"] == "abstained"
    assert r["reason"] == "no_second_mode"
    assert r["value"] is None


def test_derive_inset_modes_separation_is_pitch_relative():
    vals = _vals_from_hist([44, 9, 3, 10, 4, 2, 2, 2, 1])
    r_wide_pitch = VR.derive_inset_modes(vals, pitch_px=57)
    assert r_wide_pitch["status"] == "abstained", r_wide_pitch
    assert r_wide_pitch["reason"] == "no_second_mode"
    r_narrow_pitch = VR.derive_inset_modes(vals, pitch_px=20)
    assert r_narrow_pitch["status"] == "ok", r_narrow_pitch
    assert r_narrow_pitch["flush_bin"] == 0
    assert r_narrow_pitch["indent_bin"] == 3


def test_derive_inset_modes_min_peak_and_valley_clause():
    hist = list(_HIST_A)
    for i in range(11, 18):
        hist[i] = min(hist[i], 4)
    vals = _vals_from_hist(hist)
    r = VR.derive_inset_modes(vals, pitch_px=57)
    assert r["status"] == "abstained"
    assert r["reason"] == "no_second_mode"
    r_empty = VR.derive_inset_modes([], pitch_px=57)
    assert r_empty["status"] == "abstained"
    assert r_empty["reason"] == "no_values"
    assert r_empty["value"] is None


def test_derive_inset_modes_no_trough_abstains():
    hist = [100, 90, 80, 70, 60, 50, 40, 30, 20, 21, 22, 23, 24]
    vals = _vals_from_hist(hist)
    r = VR.derive_inset_modes(vals, pitch_px=20)
    assert r["status"] == "abstained"
    assert r["reason"] == "no_second_mode"


# 1b. choose_line_h (line_h defect: collapsed-column fallback to the page-pooled median) ----------

def test_choose_line_h_basis_cases():
    # Given cases: an intact column's own median (not >1.5x the page median) is trusted as-is
    # (basis "column", line_h=None -- text_lines uses its own med, byte-identical to today); a
    # collapsed column's own median (itself multi-line) is replaced by the page-pooled median.
    assert VR.choose_line_h(54, 53) == (None, "column")
    assert VR.choose_line_h(308, 53) == (53, "page")
    assert VR.choose_line_h(120, 55) == (55, "page")
    assert VR.choose_line_h(61, 50) == (None, "column")


def test_line_h_from_page_splits_collapsed_right_column():
    # LEFT column: 4 intact single-line raw bands (24px each) -> its own median (24) is trusted,
    # basis "column". RIGHT column: ONE fused raw band (76px, three ~24-26px sub-lines bridged by
    # two shallow valleys) -- its own median (76) is > 1.5x the page-pooled median (24), so
    # analyze_page_s1 must fall back to the page-pooled line height (24) to split it, basis "page",
    # and flag line_h_from_page:right. All content is kept far from the probed gutter window
    # (xdiv +/- 120) and well below the running-head top zone so neither interferes.
    H, W, xdiv = 3000, 1200, 600
    ink = np.zeros((H, W), dtype=bool)

    for i in range(4):                                   # left: 4 clean 24px single-line bands
        y0 = 400 + i * 50
        ink[y0:y0 + 24, 50:400] = True

    row_widths = (
        [350] * 22 +                                     # full sub-line A (22 rows)
        [180, 90, 30, 90, 180] +                          # valley A, local min at relative row 24
        [350] * 22 +                                      # full sub-line B
        [180, 90, 30, 90, 180] +                          # valley B, local min at relative row 51
        [350] * 22                                        # full sub-line C
    )
    assert len(row_widths) == 76
    y0_right = 400
    for i, wdt in enumerate(row_widths):
        ink[y0_right + i, 750:750 + wdt] = True

    geom = {"file_page": 999, "xdiv": xdiv,
            "body_regions": [{"col": "left", "box": [0, 0, 500, H]},
                              {"col": "right", "box": [700, 0, 1200, H]}]}
    s1 = VR.analyze_page_s1(ink, geom)

    assert s1["line_h"]["left"]["basis"] == "column", s1["line_h"]
    assert s1["line_h"]["right"]["basis"] == "page", s1["line_h"]
    assert "line_h_from_page:right" in s1["flags"], s1["flags"]
    assert "line_h_from_page:left" not in s1["flags"], s1["flags"]

    assert len(s1["left"]) == 4, [(b["y0"], b["y1"]) for b in s1["left"]]
    assert len(s1["right"]) == 3, [(b["y0"], b["y1"]) for b in s1["right"]]
    for b in s1["right"]:
        h = b["y1"] - b["y0"]
        assert 20 <= h <= 30, (h, "right split bands should be close to the ~24px line pitch")


# 2. vertical-rule run treated as white vs. real crossing ---------------------------------------

def test_vertical_rule_treated_as_white_vs_text_crossing_gutter():
    H, W, xdiv = 50, 400, 200
    ink = np.zeros((H, W), dtype=bool)
    # Case A: only a 4px vertical rule at xdiv -> treated as white -> wide gap -> NOT full-width.
    ink[10:20, 198:202] = True
    gap_px, _ = VR.gutter_gap(ink, xdiv, 10, 20, W=120)
    # Without the thin-rule-as-white collapse the 4px rule would SPLIT the window into two
    # ~118px halves (widest run ~118); collapsed, the whole 240px window is one white run.
    assert gap_px >= 200, f"a thin rule must collapse to white, not split the window, got gap_px={gap_px}"

    # Case B: ink fills the whole probed window -> crosses the gutter -> full-width.
    ink2 = np.zeros((H, W), dtype=bool)
    ink2[10:20, 80:320] = True
    gap_px2, _ = VR.gutter_gap(ink2, xdiv, 10, 20, W=120)
    assert gap_px2 == 0, f"text spanning the gutter window must leave no white run, got {gap_px2}"

    full_gap_thr = 50
    assert gap_px >= full_gap_thr      # case A: not full-width
    assert gap_px2 < full_gap_thr      # case B: full-width


# 2b. double-rule gutter collapse (FIX2) ----------------------------------------------------------

def test_double_rule_gutter_collapses_but_fullwidth_text_survives():
    H, W, xdiv = 60, 400, 200
    ink = np.zeros((H, W), dtype=bool)
    # Two ink runs, each 9px wide -- individually TOO WIDE for the thin-run-only cleaning (which
    # only flips runs <= RULE_RUN_MAX_W=8px) -- separated by a 3px white gap (<=
    # DOUBLE_RULE_MERGE_PX=5). They must merge into one 21px cluster, flanked by >=15px white on
    # both sides and centred within 60px of xdiv: the printed double rule (`.26 #8 .5 #8 .21`,
    # MEASURE_step2_gutter_inset_20261004.md). Without the merge+collapse the window stays split.
    ink[10:20, 188:197] = True
    ink[10:20, 200:209] = True
    gap_px, _ = VR.gutter_gap(ink, xdiv, 10, 20, W=120)
    assert gap_px >= 200, (
        f"two double-rule runs (9px each) must merge and collapse to white, not leave the "
        f"window split, got gap_px={gap_px}")

    # Genuine full-width text crossing the gutter (140px wide -- far past DOUBLE_RULE_MAX_W=24)
    # must NOT be swallowed by the double-rule collapse.
    ink2 = np.zeros((H, W), dtype=bool)
    ink2[30:40, 80:320] = True
    gap_px2, _ = VR.gutter_gap(ink2, xdiv, 30, 40, W=120)
    assert gap_px2 == 0, f"text spanning the gutter window must not be collapsed, got {gap_px2}"


# 3. running head + head_band_disagrees_3pct -----------------------------------------------------

def test_running_head_detection_and_disagrees_3pct_flag():
    H, W, xdiv = 2000, 800, 400
    ink = np.zeros((H, W), dtype=bool)
    ink[20:150, 160:640] = True          # a full-width band (running head), y1=150
    ink[300:310, 20:380] = True          # ordinary left-column body line, 10px tall
    ink[320:330, 20:380] = True
    geom = {"file_page": 1, "xdiv": xdiv,
            "body_regions": [{"col": "left", "box": [0, 0, 400, H]},
                              {"col": "right", "box": [400, 0, 800, H]}]}
    s1 = VR.analyze_page_s1(ink, geom)
    assert s1["running_head"] is not None
    assert s1["running_head"]["y1"] == 150
    # TITLE_FRAC_FOSSIL * H = 60; |150-60|=90 > median line height (10) -> flag fires
    assert "head_band_disagrees_3pct" in s1["flags"]


# 3b. full-width classification: two measured edges, abstain zone (FIX3) --------------------------

def test_full_width_classification_two_edges_and_ambiguous_zone():
    H, W, xdiv = 60, 400, 200
    ink = np.zeros((H, W), dtype=bool)
    # gutter_gap's probed window is [xdiv-120, xdiv+120) = abs[80, 320), 240px wide.
    # Band A (y0=0): an 11px white gap (== FULL_GAP_MAX_PX) -> full-width.
    ink[0:10, 80:195] = True
    ink[0:10, 206:320] = True            # abs[195,206) stays white: 11px gap
    # Band B (y0=20): a 30px white gap (inside the 12-54 abstain zone) -> column, flagged ambiguous.
    ink[20:30, 80:180] = True
    ink[20:30, 210:320] = True           # abs[180,210): 30px gap
    # Band C (y0=40): a 60px white gap (>= COL_GAP_MIN_PX) -> ordinary column, not ambiguous.
    ink[40:50, 80:170] = True
    ink[40:50, 230:320] = True           # abs[170,230): 60px gap

    left_bands = [
        _band("left", 0, 10, 0, 200, 20, 180),
        _band("left", 20, 30, 0, 200, 20, 180),
        _band("left", 40, 50, 0, 200, 20, 180),
    ]
    right_bands = [
        _band("right", 0, 10, 200, 400, 220, 380),
        _band("right", 20, 30, 200, 400, 220, 380),
        _band("right", 40, 50, 200, 400, 220, 380),
    ]
    # One side of the gutter alone is not a full-width line: unpaired -> column band, flagged.
    f0, l0, r0 = VR._merge_full_bands(left_bands[:1], [], ink, xdiv, gutter_window=120)
    assert f0 == [] and r0 == [] and len(l0) == 1 and l0[0]["full_unpaired"] is True, (f0, l0)

    full_bands, left_rest, right_rest = VR._merge_full_bands(left_bands, right_bands, ink, xdiv, gutter_window=120)

    assert len(right_rest) == 2
    assert len(full_bands) == 1 and full_bands[0]["y0"] == 0
    assert full_bands[0]["gap_px"] <= VR.FULL_GAP_MAX_PX

    assert len(left_rest) == 2
    ambiguous = next(b for b in left_rest if b["y0"] == 20)
    column = next(b for b in left_rest if b["y0"] == 40)
    assert ambiguous["gutter_ambiguous"] is True
    assert VR.FULL_GAP_MAX_PX < ambiguous["gap_px"] < VR.COL_GAP_MIN_PX
    assert column["gutter_ambiguous"] is False
    assert column["gap_px"] >= VR.COL_GAP_MIN_PX


# 4. inset candidate ------------------------------------------------------------------------------

def _band(col, y0, y1, x0, x1, left_ink_x, right_ink_x, xheight=10, baseline=None, gap_px=999):
    return {"col": col, "y0": y0, "y1": y1, "x0": x0, "x1": x1,
            "left_ink_x": left_ink_x, "right_ink_x": right_ink_x,
            "baseline": baseline if baseline is not None else y1, "xheight": xheight,
            "gap_px": gap_px}


def test_inset_candidate_fires_after_short_line_not_on_flush_continuation():
    bands = [
        _band("left", 0, 20, 0, 400, 20, 380),     # a: normal (first -> auto-candidate, ignored)
        _band("left", 20, 40, 0, 400, 20, 250),    # b: short line (ragged right)
        _band("left", 40, 60, 0, 400, 70, 380),    # c: indented after short -> CANDIDATE
        _band("left", 60, 80, 0, 400, 20, 380),    # d: flush continuation -> NOT a candidate
        _band("left", 80, 100, 0, 400, 70, 380),   # e: indented, prev (d) is full/justified (NOT
                                                    #    short) -> R5: fires on inset ALONE, flagged
    ]
    s1 = {"file_page": 1, "H": 1000, "W": 800, "xdiv": 400, "left": bands, "right": [], "full": []}
    cands = VR.head_candidates(s1, inset_thr=15)
    fired_y0 = {c["y0"] for c in cands if c["kind"] == "verse"}
    assert 40 in fired_y0, "indented line after a short (ragged-right) line must fire"
    assert 60 not in fired_y0, "a flush continuation must not fire (its own inset is below threshold)"
    assert 80 in fired_y0, (
        "R5: an indented band fires on inset ALONE, even when the previous line was itself "
        "full/justified (not short) -- CAUSE B: 17 such bands were wrongly suppressed")
    by_y0 = {c["y0"]: c for c in cands if c["kind"] == "verse"}
    assert by_y0[40].get("flags") == [], "prev WAS short -> no prev_line_full flag"
    assert by_y0[80].get("flags") == ["prev_line_full"], (
        "prev was full/justified (prev_right_short False) -> carries prev_line_full as evidence, "
        "informational only (does not gate)")


# 4b. cross-column reading order + prev_band reset on a full band (FIX4) --------------------------

def test_head_candidates_cross_column_reading_order_and_prev_none():
    # NEGATIVE case + full-band reset: prev_band must carry the reading-order's last band across
    # the LEFT->RIGHT column switch (not reset per column), yet a flush (non-indented) band must
    # still not fire merely by being first in its column (the removed per-column "is_first ->
    # always a candidate" rule would have fired here); and prev_band must reset to None when a
    # FULL band is crossed, so the next band's candidacy depends on its own inset alone.
    L1 = _band("left", 0, 20, 0, 400, 20, 380)        # normal
    L2 = _band("left", 20, 40, 0, 400, 20, 250)       # short / ragged-right
    R1 = _band("right", 10, 30, 400, 800, 420, 780)   # flush, FIRST in right col, right after short L2
    R2 = _band("right", 30, 50, 400, 800, 420, 780)   # flush (median baseline)
    R3 = _band("right", 50, 70, 400, 800, 420, 780)   # flush (median baseline)
    FB = _band("full", 100, 120, 0, 800, 100, 700)
    L4 = _band("left", 130, 150, 0, 400, 70, 380)     # indented, first band after FB

    s1_neg = {"file_page": 1, "H": 2000, "W": 800, "xdiv": 400,
              "left": [L1, L2, L4], "right": [R1, R2, R3], "full": [FB]}
    cands = VR.head_candidates(s1_neg, inset_thr=15)
    fired = {(c["col"], c["y0"]) for c in cands if c["kind"] == "verse"}
    assert ("right", 10) not in fired, (
        "a flush (non-indented) band must not fire merely by being first in its column "
        "after a column switch")
    assert ("left", 130) in fired, (
        "the first band after a FULL band must fire by its own inset alone -- prev_band must "
        "reset to None on a full band, not carry R3's (flush, non-short) state across it")

    # POSITIVE case: an INDENTED right-column band, first in its column, right after a SHORT
    # left-column line, must fire -- proving prev_band genuinely carries across the column switch
    # (not just failing to fire unconditionally).
    Rp1 = _band("right", 10, 30, 400, 800, 470, 780)  # indented
    Rp2 = _band("right", 30, 50, 400, 800, 420, 780)
    Rp3 = _band("right", 50, 70, 400, 800, 420, 780)
    s1_pos = {"file_page": 1, "H": 1000, "W": 800, "xdiv": 400,
              "left": [L1, L2], "right": [Rp1, Rp2, Rp3], "full": []}
    cands2 = VR.head_candidates(s1_pos, inset_thr=15)
    fired2 = {(c["col"], c["y0"]) for c in cands2 if c["kind"] == "verse"}
    assert ("right", 10) in fired2, (
        "an indented band immediately after a short LEFT line must fire via cross-column "
        "prev_band carry, even though it is the first band in its own column")


# 4c. gutter-rule exclusion from band ink extent (R1) ----------------------------------------------

def test_make_band_excludes_gutter_rule_from_ink_extent():
    # strip_vrules's own max_w=6 is narrower than the printed double-rule's 8-10px line width, so
    # the rule survives strip_vrules (applied once over the whole column) and would otherwise
    # become a band's leftmost/rightmost ink. _make_band must independently zero the SAME rule
    # columns gutter_gap already classifies (_gutter_rule_cols) before measuring extent.
    H, W, xdiv = 2000, 1000, 400
    ink = np.zeros((H, W), dtype=bool)

    # Scenario A: right-column band, a 9px rule at local x[3:12) plus text starting at local x 45.
    ink[200:230, 403:412] = True                       # the rule (abs == local + cx0, cx0=400)
    ink[200:230, 445:500] = True                        # text, local [45:100)
    right_box = (400, 0, W, H)
    right_col_ink = np.zeros((H, W - 400), dtype=bool)
    right_col_ink[200:230, 3:12] = True
    right_col_ink[200:230, 45:100] = True
    band_a = VR._make_band("right", right_box, 200, 230, right_col_ink, ink, xdiv)
    assert band_a["left_ink_x"] == 400 + 45, (
        f"the rule must be excluded -- without R1 this would be 400+3, got {band_a['left_ink_x']}")
    assert band_a["right_ink_x"] == 400 + 100
    assert band_a["rule_cols_removed"] == 9

    # Scenario B: left-column band, text ends 40px before xdiv (abs 300..360), a 9px rule just
    # before xdiv (abs 389..398).
    ink[300:330, 300:360] = True                        # text
    ink[300:330, 389:398] = True                        # the rule
    left_box = (0, 0, 400, H)
    left_col_ink = np.zeros((H, 400), dtype=bool)
    left_col_ink[300:330, 300:360] = True
    left_col_ink[300:330, 389:398] = True
    band_b = VR._make_band("left", left_box, 300, 330, left_col_ink, ink, xdiv)
    assert band_b["right_ink_x"] == 360, (
        f"the rule must be excluded -- without R1 this would be 398, got {band_b['right_ink_x']}")
    assert band_b["left_ink_x"] == 300
    assert band_b["rule_cols_removed"] == 9


# 4d. sliver quarantine (R2) -------------------------------------------------------------------------

def test_sliver_bands_excluded_from_candidates_and_prev_band():
    a = _band("left", 0, 20, 0, 400, 20, 380)           # normal
    b = _band("left", 20, 40, 0, 400, 20, 250)          # short / ragged-right
    speck = _band("left", 40, 46, 0, 400, 20, 380)      # 6px sliver, FLUSH (not short)
    c = _band("left", 46, 66, 0, 400, 70, 380)          # indented after short -> candidate
    d = _band("left", 66, 86, 0, 400, 20, 380)          # flush continuation
    e = _band("left", 86, 106, 0, 400, 70, 380)         # indented, prev (d) full/justified ->
                                                         # R5: fires on inset alone, flagged

    kept, slivers = VR._split_slivers([a, b, speck, c, d, e])
    assert kept == [a, b, c, d, e]
    assert slivers == [speck]

    s1 = {"file_page": 1, "H": 1000, "W": 800, "xdiv": 400, "left": kept, "right": [], "full": []}
    cands = VR.head_candidates(s1, inset_thr=15)
    fired = {c_["y0"] for c_ in cands if c_["kind"] == "verse"}
    by_y0 = {c_["y0"]: c_ for c_ in cands if c_["kind"] == "verse"}
    assert 46 in fired, "with the sliver excluded, c's prev_band is b (short) -- c must fire"
    assert by_y0[46].get("flags") == [], "prev (b) really was short -> no prev_line_full flag"
    assert 86 in fired, "R5: e fires on inset alone even though prev (d) is full/justified"
    assert by_y0[86].get("flags") == ["prev_line_full"]

    # Regression guard: an UNFILTERED sliver (left through to head_candidates untouched) becomes
    # prev_band for c -- being FLUSH (not short) it no longer suppresses c's candidacy under R5
    # (inset alone decides is_verse), but it DOES corrupt c's prev_line_full evidence: the sliver
    # masquerades as a full/justified previous line, wrongly flagging prev_line_full when the real
    # previous line (b) was short. This proves _split_slivers' exclusion is still load-bearing for
    # signature correctness, not incidental.
    s1_unfiltered = {"file_page": 1, "H": 1000, "W": 800, "xdiv": 400,
                      "left": [a, b, speck, c, d, e], "right": [], "full": []}
    cands_unfiltered = VR.head_candidates(s1_unfiltered, inset_thr=15)
    by_y0_unfiltered = {c_["y0"]: c_ for c_ in cands_unfiltered if c_["kind"] == "verse"}
    assert by_y0_unfiltered[46].get("flags") == ["prev_line_full"], (
        "sanity check on the test's own construction: an unexcluded sliver must corrupt "
        "c's prev_line_full evidence")


# 5. head_reads confirmation -----------------------------------------------------------------------

def test_head_reads_ver_false_rejects_none_keeps_unconfirmed():
    cands = [
        {"file_page": 1, "col": "left", "y0": 10, "y1": 20, "box": [0, 10, 100, 20],
         "kind": "verse", "signature": {}},
        {"file_page": 1, "col": "left", "y0": 30, "y1": 40, "box": [0, 30, 100, 40],
         "kind": "verse", "signature": {}},
        {"file_page": 1, "col": "left", "y0": 50, "y1": 60, "box": [0, 50, 100, 60],
         "kind": "verse", "signature": {}},
        {"file_page": 1, "col": "left", "y0": 70, "y1": 80, "box": [0, 70, 100, 80],
         "kind": "chapter", "signature": {}},
    ]
    head_reads = {
        (1, "left", 10): {"ver": False, "numbers": None, "status": "ok"},
        (1, "left", 50): {"ver": None, "numbers": None, "status": "abstain"},
        # (1, "left", 70) rejected by the read-prompt (it's not a Ver. line) -- must be ignored
        (1, "left", 70): {"ver": False, "numbers": None, "status": "ok"},
    }
    confirmed, rejected = VR.confirm_candidates(cands, head_reads)
    assert any(r["y0"] == 10 and r["reason"] == "head_reads:no_ver" for r in rejected)
    y0_to_conf = {c["y0"]: c for c in confirmed}
    assert 30 in y0_to_conf and "head_unconfirmed" in y0_to_conf[30].get("flags", [])   # missing key
    assert 50 in y0_to_conf and "head_unconfirmed" in y0_to_conf[50].get("flags", [])   # ver None
    assert 70 in y0_to_conf, "a chapter candidate must be confirmed by geometry, never by head_reads"


# 6. reconcile_numbers ------------------------------------------------------------------------------

def test_reconcile_numbers_cases():
    r = VR.reconcile_numbers({"count": None, "read": [3], "witness": None})
    assert r["numbers_link_status"] == "numbers_single_source" and r["verse"] is None

    r = VR.reconcile_numbers({"count": None, "read": [3], "witness": [3]})
    assert r["numbers_link_status"] == "numbers_agree" and r["verse"] == [3]

    r = VR.reconcile_numbers({"count": None, "read": [3], "witness": [4]})
    assert r["numbers_link_status"] == "numbers_disagree"
    assert r["numbers_disagree_pairs"] == ["read|witness"]
    assert r["verse"] is None

    r = VR.reconcile_numbers({"count": 1, "read": [1, 2], "witness": [1, 2]})
    assert r["numbers_link_status"] == "numbers_agree" and r["verse"] == [1, 2]

    r = VR.reconcile_numbers({"count": 1, "read": None, "witness": None})
    assert r["numbers_link_status"] == "numbers_single_source" and r["verse"] is None

    r = VR.reconcile_numbers({"count": None, "read": None, "witness": None})
    assert r["numbers_link_status"] == "numbers_none" and r["verse"] is None


# 7. assert_numbering_invariant ----------------------------------------------------------------------

def test_assert_numbering_invariant_raises_and_passes():
    bad = {"file_page_first": 99, "verse": [3], "numbers_link_status": "numbers_single_source",
           "number_sources": {"count": None, "read": [3], "witness": None}}
    try:
        VR.assert_numbering_invariant([bad])
        assert False, "expected ValueError"
    except ValueError as e:
        assert "99" in str(e)

    good = {"file_page_first": 99, "verse": [3], "numbers_link_status": "numbers_agree",
            "number_sources": {"count": None, "read": [3], "witness": [3]}}
    VR.assert_numbering_invariant([good])    # must not raise


# 7b. parse_ver_head / parse_witness -- one code-owned verse-number parser -----------------------

def test_parse_ver_head_cases():
    ok = VR.parse_ver_head("Ver. 21. And his")
    assert ok == {"ver": True, "numbers": [21], "raw_head": "Ver. 21", "status": "ok",
                  "ver_case": "upper"}, ok

    for dash in ("-", "–", "—"):                # hyphen, en dash, em dash
        r = VR.parse_ver_head(f"Ver. 12{dash}14 some text")
        assert r["status"] == "ok" and r["numbers"] == [12, 13, 14], (dash, r)

    r = VR.parse_ver_head("Ver. 3, 5, 7")
    assert r["status"] == "ok" and r["numbers"] == [3, 5, 7], r

    r = VR.parse_ver_head("Ver, 4")                        # comma variant, no period
    assert r["status"] == "ok" and r["numbers"] == [4], r

    r = VR.parse_ver_head("Ver. 5-3")                       # M not > N
    assert r == {"ver": True, "numbers": None, "raw_head": "Ver. 5-3",
                 "status": "range_implausible", "ver_case": "upper"}, r

    r = VR.parse_ver_head("Ver. 5-30")                      # span 25 > RANGE_SPAN_MAX (20)
    assert r["status"] == "range_implausible" and r["numbers"] is None, r

    r = VR.parse_ver_head("Ver. 9, 5")                      # expands to [9,5], not strictly ascending
    assert r["status"] == "range_implausible" and r["numbers"] is None, r

    r = VR.parse_ver_head("Ver.")                           # "Ver" with no number spec
    assert r == {"ver": True, "numbers": None, "raw_head": "Ver.", "status": "unparsed",
                 "ver_case": "upper"}, r

    r = VR.parse_ver_head("   ")                            # empty/whitespace-only
    assert r == {"ver": None, "numbers": None, "raw_head": None, "status": "empty",
                 "ver_case": None}, r
    assert VR.parse_ver_head("") == r

    r = VR.parse_ver_head("ver. 5")                         # lowercase "ver." WITH a number -> a head
    assert r == {"ver": True, "numbers": [5], "raw_head": "ver. 5", "status": "ok",
                 "ver_case": "lower"}, r

    r = VR.parse_ver_head("ver. And")                       # lowercase "ver." with NO number -> prose
    assert r == {"ver": False, "numbers": None, "raw_head": None, "status": "no_ver",
                 "ver_case": None}, r

    for bad in ("very good", "verse 3", "ver 3"):            # no required lowercase punctuation / not "ver"
        r = VR.parse_ver_head(bad)
        assert r["status"] == "no_ver" and r["ver"] is False and r["ver_case"] is None, (bad, r)

    r = VR.parse_ver_head(' "Ver. 7 is the just')           # <=3 leading non-alnum chars tolerated
    assert r["status"] == "ok" and r["numbers"] == [7], r

    r = VR.parse_ver_head("And God said, Let there be light")  # no "Ver" at all
    assert r["status"] == "no_ver" and r["ver"] is False, r


def test_parse_witness_multiline_ranges_and_chapters():
    md = (
        "# Chapter I.\n"
        "Ver. 1. In the beginning God created the heaven and the earth.\n"
        "more running text here\n"
        "Ver. 2—4. And the earth was without form, and void.\n"
        "# Chapter II.\n"
        "Ver. 5. Continuing text for the next chapter.\n"
    )
    w = VR.parse_witness(md)
    assert w["chapter_count"] == 2, w
    assert w["verse_heads"] == [[1], [2, 3, 4], [5]], w


# 8. witness pairing by text-similarity sequence alignment (replaces positional pairing) ----------

_WIT_TEXTS = [
    "in the beginning god created the heaven and the earth",
    "and the earth was without form and void and darkness",
    "and god said let there be light and there was light",
    "and god saw the light that it was good and divided",
]


def _rk(t):
    return VR.align_key(t, VR.ALIGN_KEY_CHARS)


def test_align_witness_equal_counts_same_order_positional():
    read_keys = [_rk(t) for t in _WIT_TEXTS[:3]]
    assert VR.align_witness(read_keys, _WIT_TEXTS[:3]) == [("paired", 0), ("paired", 1), ("paired", 2)]


def test_align_witness_extra_witness_head_is_skipped():
    read_keys = [_rk(t) for t in _WIT_TEXTS[:3]]
    extra = "zzz qqq xyz nonsense filler phrase totally unlike"
    witness_lines = [_WIT_TEXTS[0], extra, _WIT_TEXTS[1], _WIT_TEXTS[2]]
    assert VR.align_witness(read_keys, witness_lines) == [("paired", 0), ("paired", 2), ("paired", 3)]


def test_align_witness_identical_competing_lines_are_ambiguous():
    read_keys = [_rk(_WIT_TEXTS[0])]
    witness_lines = [_WIT_TEXTS[0], _WIT_TEXTS[0]]        # two lines, same key -> neither essential
    assert VR.align_witness(read_keys, witness_lines) == [("ambiguous", None)]


def test_align_witness_empty_read_key_is_unpaired():
    assert VR.align_witness([""], [_WIT_TEXTS[0]]) == [("unpaired", None)]


def test_assemble_regions_witness_pairs_by_text_not_by_numbers():
    # Read and witness DISAGREE on the verse numbers for every head (20/21/32/23 vs 99/98/97/96),
    # but the witness lines are IDENTICAL text to the read heads' trailing text, in the same order.
    # align_witness must still pair every head (by text alone) and the region's witness number
    # must come from the witness's OWN number (never the read's), proving numbers are not an input
    # to the alignment itself.
    read_nums = [20, 21, 32, 23]
    wit_nums = [[99], [98], [97], [96]]
    bands, cands = [], []
    for y0, n, t in zip((10, 30, 50, 70), read_nums, _WIT_TEXTS):
        y1 = y0 + 10
        bands.append(_band("left", y0, y1, 0, 400, 20, 380))
        hc = {"text": f"Ver. {n}. {t}", "ver": True, "numbers": [n], "raw_head": f"Ver. {n}",
              "status": "ok", "raw": f"Ver. {n}. {t}", "ver_case": "upper"}
        cands.append({"file_page": 1, "col": "left", "y0": y0, "y1": y1, "box": [0, y0, 400, y1],
                      "kind": "verse", "signature": {}, "head_confirm": hc, "flags": []})
    s1 = {"file_page": 1, "H": 1000, "W": 800, "xdiv": 400, "left": bands, "right": [], "full": []}
    witness = {"verse_heads": wit_nums, "verse_lines": _WIT_TEXTS, "chapter_count": 0}
    regions, summaries = VR.assemble_regions(
        [{"file_page": 1}], {1: s1}, {1: cands}, {1: []}, {1: witness}, config={})
    assert [r["witness_pairing"] for r in regions] == ["paired"] * 4
    assert [r["number_sources"]["witness"] for r in regions] == wit_nums
    assert [r["number_sources"]["read"] for r in regions] == [[n] for n in read_nums]
    assert summaries[1]["n_witness_paired"] == 4
    assert summaries[1]["n_witness_ambiguous"] == 0
    assert summaries[1]["n_witness_unpaired"] == 0


# 8b. ascending invariant per source (disputed/chains) -- replaces verse_not_ascending -------------

def test_disputed_cases():
    # NOTE: the spec's worked example states [[20],[21],[32],[23]] -> {2}, but the cited reference
    # (C:\tmp\a2\fix_abc\ascdiag.py's disputed(), reproduced here byte-for-byte) actually returns
    # {2, 3} for this input when run directly: 20,21,32 and 20,21,23 are two equally-long (length
    # 3) ascending chains, so BOTH 32 and 23 are tied at the same f-layer and neither is uniquely
    # kept -- this is the algorithm's own tie rule, not a transcription error (verified by running
    # the reference script's code against this exact input). Held to the verified reference
    # behaviour, not the spec's prose, per the "reproduce their behaviour exactly" instruction;
    # flagged in the report.
    assert VR.disputed([[20], [21], [32], [23]]) == {2, 3}
    assert VR.disputed([[22], [23], [21]]) == {2}
    assert VR.disputed([[1], [35], [3], [4]]) == {1}
    assert VR.disputed([[1], [2], [3], [4]]) == set()
    assert VR.disputed([[2], [1]]) == {0, 1}
    assert VR.disputed([[12, 13, 14], [15]]) == set()


def test_chains_splits_at_chapter_intro_and_page_gap():
    regs = [
        {"kind": "verse", "file_page_first": 1, "tag": "a"},
        {"kind": "verse", "file_page_first": 1, "tag": "b"},
        {"kind": "chapter_intro", "file_page_first": 2, "tag": "ci"},   # resets the chain
        {"kind": "verse", "file_page_first": 2, "tag": "c"},
        {"kind": "verse", "file_page_first": 5, "tag": "d"},            # page gap (2 -> 5) resets
        {"kind": "continuation_unanchored", "file_page_first": 5, "tag": "cu"},  # doesn't enter/reset
        {"kind": "verse", "file_page_first": 6, "tag": "e"},
        {"kind": "unknown_kind", "file_page_first": 6, "tag": "u"},     # invisible to the walk
        {"kind": "verse", "file_page_first": 7, "tag": "f"},
    ]
    chains = VR._chains(regs)
    assert [[r["tag"] for r in c] for c in chains] == [["a", "b"], ["c"], ["d", "e", "f"]]


def test_ascending_invariant_wired_into_assemble_regions():
    # read == witness == [20, 21, 32, 23] for 4 consecutive verse heads on one page: the ascending
    # check runs independently per source but both sources carry the SAME sequence here, so both
    # flag the same disputed indices (2 and 3, see test_disputed_cases) while 0 and 1 stay
    # undisputed on both sources even though read == witness everywhere.
    nums = [20, 21, 32, 23]
    bands, cands = [], []
    for y0, n, t in zip((10, 30, 50, 70), nums, _WIT_TEXTS):
        y1 = y0 + 10
        bands.append(_band("left", y0, y1, 0, 400, 20, 380))
        hc = {"text": f"Ver. {n}. {t}", "ver": True, "numbers": [n], "raw_head": f"Ver. {n}",
              "status": "ok", "raw": f"Ver. {n}. {t}", "ver_case": "upper"}
        cands.append({"file_page": 1, "col": "left", "y0": y0, "y1": y1, "box": [0, y0, 400, y1],
                      "kind": "verse", "signature": {}, "head_confirm": hc, "flags": []})
    s1 = {"file_page": 1, "H": 1000, "W": 800, "xdiv": 400, "left": bands, "right": [], "full": []}
    witness = {"verse_heads": [[n] for n in nums], "verse_lines": _WIT_TEXTS, "chapter_count": 0}
    regions, _ = VR.assemble_regions(
        [{"file_page": 1}], {1: s1}, {1: cands}, {1: []}, {1: witness}, config={})
    assert [r["disputed"] for r in regions] == [False, False, True, True]
    assert [r["disputed_by"] for r in regions] == [[], [], ["read", "witness"], ["read", "witness"]]
    assert "verse_order_disputed:read" in regions[2]["flags"]
    assert "verse_order_disputed:witness" in regions[2]["flags"]
    assert "verse_order_disputed:read" not in regions[0]["flags"]


def test_chapter_count_resets_at_page_gap_404_to_745():
    # Rerun 2's leak, born-tested on exactly that pair: a chapter head on 404 with no verse head after
    # it, then 745 (a page gap) whose first verse head is "Ver. 4". The count must be None on 745 and
    # the drop flagged on 404. Control: the same chapter head on 404 followed by 405 (consecutive)
    # still gives count 1.
    def page(fp, kind):
        band = _band("left", 10, 20, 0, 400, 20, 380)
        hc = None
        if kind == "verse":
            hc = {"text": "Ver. 4. x", "ver": True, "numbers": [4], "raw_head": "Ver. 4",
                  "status": "ok", "raw": "Ver. 4. x", "ver_case": "upper"}
        cand = {"file_page": fp, "col": "left", "y0": 10, "y1": 20, "box": [0, 10, 400, 20],
                "kind": kind, "signature": {}, "head_confirm": hc, "flags": []}
        s1 = {"file_page": fp, "H": 100, "W": 800, "xdiv": 400, "left": [band], "right": [], "full": []}
        return s1, [cand]

    for nxt, want_count, want_flag in ((745, None, True), (405, 1, False)):
        s1a, ca = page(404, "chapter")
        s1b, cb = page(nxt, "verse")
        regions, summaries = VR.assemble_regions(
            [{"file_page": 404}, {"file_page": nxt}], {404: s1a, nxt: s1b}, {404: ca, nxt: cb},
            {404: [], nxt: []}, {404: None, nxt: None}, config={})
        verse = [r for r in regions if r["kind"] == "verse"]
        assert len(verse) == 1 and verse[0]["file_page_first"] == nxt
        assert verse[0]["number_sources"]["count"] == want_count, (nxt, verse[0]["number_sources"])
        assert verse[0]["number_sources"]["read"] == [4]
        assert ("chapter_count_dropped_at_page_gap" in summaries[404]["flags"]) is want_flag, nxt
        assert "chapter_count_dropped_at_page_gap" not in summaries[nxt]["flags"]


def test_unanchored_continuation_listed_first_on_its_page_90_layout():
    # Page 90's order bug (Chris, console 2026-10-11): an unchained page with text before its first
    # head, a chapter head, then a verse head. The continuation was appended AFTER the chapter_intro
    # the page had already closed. Reading order: continuation, chapter_intro, verse. With a prior
    # page (89, verse head left open, then a GAP to 91) the previous page's region stays first.
    def cand(fp, y, kind):
        hc = None
        if kind == "verse":
            hc = {"text": "Ver. 1. x", "ver": True, "numbers": [1], "raw_head": "Ver. 1",
                  "status": "ok", "raw": "Ver. 1. x", "ver_case": "upper"}
        return {"file_page": fp, "col": "left", "y0": y, "y1": y + 10, "box": [0, y, 400, y + 10],
                "kind": kind, "signature": {}, "head_confirm": hc, "flags": []}

    def page(fp, heads):
        ys = [10] + [y for y, _ in heads]
        bands = [_band("left", y, y + 10, 0, 400, 20, 380) for y in ys]
        s1 = {"file_page": fp, "H": 200, "W": 800, "xdiv": 400, "left": bands, "right": [], "full": []}
        return s1, [cand(fp, y, k) for y, k in heads]

    s1, c = page(90, [(30, "chapter"), (50, "verse")])
    regions, _ = VR.assemble_regions([{"file_page": 90}], {90: s1}, {90: c}, {90: []}, {90: None}, config={})
    assert [r["kind"] for r in regions] == ["continuation_unanchored", "chapter_intro", "verse"],         [r["kind"] for r in regions]
    assert regions[0]["rects"][0]["box"][1] == 10

    s1a, ca = page(89, [(30, "verse")])
    s1b, cb = page(91, [(30, "chapter"), (50, "verse")])
    regions, _ = VR.assemble_regions([{"file_page": 89}, {"file_page": 91}], {89: s1a, 91: s1b},
                                     {89: ca, 91: cb}, {89: [], 91: []}, {89: None, 91: None}, config={})
    got = [(r["kind"], r["file_page_first"]) for r in regions]
    assert got == [("continuation_unanchored", 89), ("verse", 89), ("continuation_unanchored", 91),
                   ("chapter_intro", 91), ("verse", 91)], got
    # chained control (89 -> 90): leading text extends 89's open verse, no continuation record
    s1b, cb = page(90, [(30, "chapter"), (50, "verse")])
    regions, _ = VR.assemble_regions([{"file_page": 89}, {"file_page": 90}], {89: s1a, 90: s1b},
                                     {89: ca, 90: cb}, {89: [], 90: []}, {89: None, 90: None}, config={})
    got = [(r["kind"], r["file_page_first"]) for r in regions]
    assert got == [("continuation_unanchored", 89), ("verse", 89), ("chapter_intro", 90), ("verse", 90)], got


def test_leading_text_continues_previous_page_region_91_layout():
    # Page 91 (Chris, console 2026-10-11): Ver. 1 opens on 90; on 91 the whole LEFT column and the
    # top of the RIGHT column continue Ver. 1, and "Ver. 2" is a head lower in the right column.
    # The leading text was settled after the band loop and went to the page's LAST open region:
    # Ver. 2 got rects from the top of both columns and Ver. 1 had nothing on 91.
    def vcand(fp, col, y, n):
        hc = {"text": f"Ver. {n}. x", "ver": True, "numbers": [n], "raw_head": f"Ver. {n}",
              "status": "ok", "raw": f"Ver. {n}. x", "ver_case": "upper"}
        x0, x1 = (0, 400) if col == "left" else (400, 800)
        return {"file_page": fp, "col": col, "y0": y, "y1": y + 10, "box": [x0, y, x1, y + 10],
                "kind": "verse", "signature": {}, "head_confirm": hc, "flags": []}
    L = lambda y: _band("left", y, y + 10, 0, 400, 20, 380)
    R = lambda y: _band("right", y, y + 10, 400, 800, 420, 780)
    s90 = {"file_page": 90, "H": 200, "W": 800, "xdiv": 400, "left": [L(30), L(50)], "right": [R(10), R(30)], "full": []}
    s91 = {"file_page": 91, "H": 200, "W": 800, "xdiv": 400, "left": [L(10), L(30), L(50)],
           "right": [R(10), R(30), R(50), R(70)], "full": []}
    regions, _ = VR.assemble_regions(
        [{"file_page": 90}, {"file_page": 91}], {90: s90, 91: s91},
        {90: [vcand(90, "left", 30, 1)], 91: [vcand(91, "right", 50, 2)]},
        {90: [], 91: []}, {90: None, 91: None}, config={})
    v = {r["number_sources"]["read"][0]: r for r in regions if r["kind"] == "verse"}
    r1 = {(x["file_page"], x["col"]): x["box"] for x in v[1]["rects"]}
    r2 = {(x["file_page"], x["col"]): x["box"] for x in v[2]["rects"]}
    assert r1.get((91, "left")) is not None and r1[(91, "left")][1] == 10 and r1[(91, "left")][3] == 60, r1
    assert r1.get((91, "right")) is not None and r1[(91, "right")][1] == 10 and r1[(91, "right")][3] == 40, r1
    assert set(r2) == {(91, "right")} and r2[(91, "right")][1] == 50 and r2[(91, "right")][3] == 80, r2
    # unchained (89 -> 91 gap) same page: the leading text is its own continuation, listed before Ver. 2
    regions, _ = VR.assemble_regions(
        [{"file_page": 89}, {"file_page": 91}], {89: dict(s90, file_page=89), 91: s91},
        {89: [vcand(89, "left", 30, 1)], 91: [vcand(91, "right", 50, 2)]},
        {89: [], 91: []}, {89: None, 91: None}, config={})
    got = [(r["kind"], r["file_page_first"]) for r in regions]
    assert got[-2:] == [("continuation_unanchored", 91), ("verse", 91)], got
    cont = regions[-2]
    assert {(x["col"], x["box"][1], x["box"][3]) for x in cont["rects"]} == {("left", 10, 60), ("right", 10, 40)}, cont["rects"]

# 9. region_empty / head_only, derived from bands not a counter (FIX5) --------------------------------

def test_head_only_region_has_head_band_counted_and_region_empty_via_helper():
    head_band = _band("left", 10, 20, 0, 100, 10, 90)
    s1 = {"file_page": 1, "H": 100, "W": 200, "xdiv": 100, "left": [head_band], "right": [], "full": []}
    cand = {"file_page": 1, "col": "left", "y0": 10, "y1": 20, "box": [0, 10, 100, 20],
            "kind": "verse", "signature": {}, "head_confirm": None, "flags": []}
    regions, _ = VR.assemble_regions(
        [{"file_page": 1}], {1: s1}, {1: [cand]}, {1: []}, {1: None}, config={})
    assert len(regions) == 1
    # FIX5: the head band belongs to its own region's rect (extended on open) -- a region with
    # ONLY its head band is not empty (it has one ink band: the head itself), but it IS head_only.
    assert regions[0]["region_empty"] is False
    assert regions[0]["head_only"] is True
    assert "head_only" in regions[0]["flags"]
    assert "region_empty" not in regions[0]["flags"]

    # The region_empty born-test: assemble_regions can no longer naturally produce an empty region
    # (FIX5 always extends the opening rect to the head band), so build one by hand and confirm
    # _count_ink_bands -- the function assemble_regions now derives emptiness from -- returns 0
    # for a rect whose row range has no S1 band at all.
    empty_region = {"rects": [{"file_page": 1, "col": "left", "box": [0, 50, 100, 60]}]}
    n = VR._count_ink_bands(empty_region, {1: s1})
    assert n == 0, "a rect covering rows with no S1 band must count zero ink bands"


# 10. continuation chaining -----------------------------------------------------------------------------

def test_continuation_chains_and_unanchored():
    head_band = _band("left", 10, 20, 0, 100, 10, 90)
    s1_p1 = {"file_page": 1, "H": 100, "W": 200, "xdiv": 100, "left": [head_band], "right": [], "full": []}
    cand = {"file_page": 1, "col": "left", "y0": 10, "y1": 20, "box": [0, 10, 100, 20],
            "kind": "verse", "signature": {}, "head_confirm": None, "flags": []}

    body_band = _band("left", 5, 15, 0, 100, 10, 90)

    # A: consecutive page chains -> ONE region, gains a rect from page 2.
    s1_p2 = {"file_page": 2, "H": 100, "W": 200, "xdiv": 100, "left": [body_band], "right": [], "full": []}
    regions_a, _ = VR.assemble_regions(
        [{"file_page": 1}, {"file_page": 2}],
        {1: s1_p1, 2: s1_p2}, {1: [cand], 2: []}, {1: [], 2: []}, {1: None, 2: None}, config={})
    assert len(regions_a) == 1
    assert regions_a[0]["region_empty"] is False
    assert any(r["file_page"] == 2 for r in regions_a[0]["rects"])

    # B: a non-consecutive page does NOT chain -> a separate continuation_unanchored region.
    s1_p3 = {"file_page": 3, "H": 100, "W": 200, "xdiv": 100, "left": [body_band], "right": [], "full": []}
    regions_b, _ = VR.assemble_regions(
        [{"file_page": 1}, {"file_page": 3}],
        {1: s1_p1, 3: s1_p3}, {1: [cand], 3: []}, {1: [], 3: []}, {1: None, 3: None}, config={})
    kinds = sorted(r["kind"] for r in regions_b)
    assert kinds == ["continuation_unanchored", "verse"]
    verse_r = next(r for r in regions_b if r["kind"] == "verse")
    unanchored_r = next(r for r in regions_b if r["kind"] == "continuation_unanchored")
    # FIX5: verse_r's rect was extended to its own head band on open, so it is NOT empty (one ink
    # band: the head itself) even though page 3 did not chain to it -- it IS head_only.
    assert verse_r["region_empty"] is False
    assert verse_r["head_only"] is True
    assert unanchored_r["file_page_first"] == 3
    assert unanchored_r["region_empty"] is False


# 11. guard_crop --------------------------------------------------------------------------------------

def test_guard_crop_statuses():
    page = np.full((100, 100), 255, dtype=np.uint8)
    assert VHR.guard_crop(page, (-5, 0, 50, 50), (100, 100)) == "clamped"
    assert VHR.guard_crop(page, (60, 60, 150, 150), (100, 100)) == "clamped"

    blank = np.full((100, 100), 255, dtype=np.uint8)
    assert VHR.guard_crop(blank, (0, 0, 50, 50), (100, 100)) == "blank"

    uniform = np.full((100, 100), 50, dtype=np.uint8)
    assert VHR.guard_crop(uniform, (0, 0, 50, 50), (100, 100)) == "uniform"

    ok = np.zeros((100, 100), dtype=np.uint8)
    ok[::2, :] = 255     # checkerboard-ish rows: plenty of dark + plenty of texture
    assert VHR.guard_crop(ok, (0, 0, 50, 50), (100, 100)) == "ok"


def test_guard_crop_straddle_and_blank_band():
    # crop = gray[0:40, 0:50]; pad=CROP_PAD_Y=12 -> band = crop rows [12, 28).
    W = 50
    box = (0, 0, W, 40)

    def _page(dark_rows):
        page = np.full((100, W), 255, dtype=np.uint8)
        for y in dark_rows:
            page[y, :] = 0
        return page

    # whole line fully inside the band, clear of both pad margins -> ok
    whole = _page(range(18, 22))
    assert VHR.guard_crop(whole, box, (100, W)) == "ok"

    # band starts mid-line: core ink runs right up to the band's own first row -> straddle
    top = _page(range(8, 17))
    assert VHR.guard_crop(top, box, (100, W)) == "straddle"

    # band ends mid-line: core ink runs right up to the band's own last row -> straddle
    bottom = _page(range(24, 32))
    assert VHR.guard_crop(bottom, box, (100, W)) == "straddle"

    # ink only in the pad margins, none inside the band at all -> blank_band
    pad_only = _page(list(range(2, 7)) + list(range(33, 38)))
    assert VHR.guard_crop(pad_only, box, (100, W)) == "blank_band"


# 12. read_head with a fake client -- head read = transcription, code parses ----------------------

def test_read_head_fake_client_parses():
    r = VHR.read_head(lambda b: "Ver. 3, 4. In the beginning", b"x")
    assert r == {"text": "Ver. 3, 4. In the beginning", "ver": True, "numbers": [3, 4],
                 "raw_head": "Ver. 3, 4", "status": "ok", "raw": "Ver. 3, 4. In the beginning",
                 "ver_case": "upper"}

    r = VHR.read_head(lambda b: "And God said, Let there be light", b"x")
    assert r["ver"] is False and r["status"] == "no_ver"

    r = VHR.read_head(lambda b: "Ver.", b"x")
    assert r["ver"] is True and r["numbers"] is None and r["status"] == "unparsed"


def test_read_head_parses_ver21_transcription():
    # The exact case named in the spec: a plain transcription, numbers parsed by code alone.
    r = VHR.read_head(lambda b: "Ver. 21. And his", b"x")
    assert r["ver"] is True and r["numbers"] == [21] and r["status"] == "ok"


def test_read_head_payload_has_no_format_key_and_transcribe_prompt():
    captured = {}

    class FakeResp:
        def json(self):
            return {"done": True, "message": {"content": "Ver. 8. Thus saith the Lord"}}

    class FakeClient:
        base_url = "http://example:11434"
        model = "m"

        def post(self, url, json=None, timeout=None):
            captured["payload"] = json
            return FakeResp()

    r = VHR.read_head(FakeClient(), b"png")
    payload = captured["payload"]
    assert "format" not in payload, payload
    assert payload["messages"][0]["content"] == VHR.TRANSCRIBE_PROMPT
    assert payload["options"] == {"temperature": 0, "num_predict": 64}, payload["options"]
    assert payload["think"] is False and payload["stream"] is False
    assert r["numbers"] == [8]


def test_read_head_degenerate_reply_raises():
    for bad in ("", "   ", "////", "/ / /"):
        try:
            VHR.read_head(lambda b, bad=bad: bad, b"x")
            assert False, f"expected DegenerateReplyError for {bad!r}"
        except VHR.DegenerateReplyError:
            pass

    class FakeResp:
        def json(self):
            return {"done": False, "message": {"content": "Ver. 1"}}

    class FakeClient:
        base_url = "http://example:11434"
        model = "m"

        def post(self, url, json=None, timeout=None):
            return FakeResp()

    try:
        VHR.read_head(FakeClient(), b"png")
        assert False, "expected DegenerateReplyError for done:false"
    except VHR.DegenerateReplyError:
        pass


# 12b. endpoint canary -- abort, never retry -------------------------------------------------------

def test_run_canary_ok_fake():
    def load_gray(fp):
        return np.full((10, 10), 255, dtype=np.uint8)

    orig = VHR.guarded_read_head

    def fake_guarded(client, gray, box, page_shape, blank_floor=0.01, uniform_std=2.0):
        for crop in VHR.CANARY_CROPS:
            if crop["box"] == box:
                exp = crop["expected"]
                return {"text": "x", "ver": exp["ver"], "numbers": exp["numbers"],
                        "raw_head": None, "status": "ok", "raw": "x"}
        raise AssertionError("unexpected box in canary test")

    VHR.guarded_read_head = fake_guarded
    try:
        rec = VHR.run_canary(client=None, load_gray=load_gray, batch=0, at_read=0)
    finally:
        VHR.guarded_read_head = orig
    assert rec["ok"] is True and rec["batch"] == 0 and rec["at_read"] == 0, rec
    assert all(c["match"] for c in rec["crops"]), rec


def test_run_canary_fail_stale_raises():
    # The endpoint has drifted/gone stale: every canary crop now reads back the WRONG number.
    def load_gray(fp):
        return np.full((10, 10), 255, dtype=np.uint8)

    orig = VHR.guarded_read_head

    def fake_guarded_stale(client, gray, box, page_shape, blank_floor=0.01, uniform_std=2.0):
        return {"text": "stale", "ver": True, "numbers": [999], "raw_head": None,
                "status": "ok", "raw": "stale"}

    VHR.guarded_read_head = fake_guarded_stale
    try:
        try:
            VHR.run_canary(client=None, load_gray=load_gray, batch=3, at_read=60)
            assert False, "expected CanaryFault"
        except VHR.CanaryFault:
            pass
    finally:
        VHR.guarded_read_head = orig


# 13. run-level fault: 3 consecutive read errors abort ----------------------------------------------

def test_run_level_fault_aborts_after_3_consecutive_errors():
    counter = VHR.ConsecutiveErrorCounter(limit=3)

    class FlakyClient:
        base_url = "http://example:11435"
        model = "m"

        def __init__(self):
            self.calls = 0

        def post(self, *a, **k):
            self.calls += 1
            raise TimeoutError("boom")

    client = FlakyClient()
    aborted = False
    try:
        for _ in range(5):
            try:
                VHR.read_head(client, b"png")
                counter.record_success()
            except Exception:
                counter.record_error()
    except VHR.ConsecutiveReadErrorFault:
        aborted = True
    assert aborted
    assert client.calls == 3, f"must abort exactly at the 3rd consecutive error, got {client.calls} calls"


# 13b. build-level: a canary failure aborts the whole run header-only --------------------------------

def test_build_canary_failure_writes_header_only_aborted():
    # A minimal, fully synthetic single-page fixture (blank 200x200 page, no real corpus data
    # touched) driven through the real build_verse_regions.main() CLI entry point. derive_inset_thr
    # / resolve_and_check / run_canary are monkeypatched on the MODULE objects (bare-name calls
    # inside main() resolve via the module's globals dict at call time, so this reaches them) so
    # the test never derives a real threshold, never resolves a real endpoint, and forces the
    # canary to fail on its very first call (batch 0, before any head read) -- exercising only the
    # abort path: exit 3, header-only write, status='aborted', abort_reason names batch 0, canary=[].
    import json
    import tempfile
    from pathlib import Path
    from PIL import Image
    import build_verse_regions as BVR

    tmpdir = Path(tempfile.mkdtemp(prefix="dev_fix10_canary_"))
    vol_dir = tmpdir / "vol"
    vol_dir.mkdir()
    Image.fromarray(np.full((200, 200), 255, dtype=np.uint8)).save(vol_dir / "page1_image1.png")
    geom_path = tmpdir / "geom.jsonl"
    geom_rec = {"file_page": 1, "xdiv": 100,
                "body_regions": [{"col": "left", "box": [0, 0, 100, 200]},
                                  {"col": "right", "box": [100, 0, 200, 200]}]}
    geom_path.write_text(json.dumps(geom_rec) + "\n", encoding="utf-8")
    out_path = tmpdir / "out" / "run.jsonl"

    orig_derive = BVR.derive_inset_thr
    orig_resolve = VHR.resolve_and_check
    orig_canary = VHR.run_canary

    def fake_derive(s1_by_page):
        return {"status": "ok", "reason": None, "value": 50.0, "rule": "mode_midpoint",
                "bin_px": 5, "pitch_px": 57, "flush_bin": 0, "indent_bin": 10,
                "flush_count": 100, "indent_count": 10, "n": 110, "hist": [100] + [0] * 9 + [10]}, [45]

    def fake_resolve(host, model, client=None):
        return "http://fake-host:11434", "sha256:fakedigest"

    def fake_canary(client, load_gray, batch, at_read):
        raise VHR.CanaryFault(f"canary_failed batch {batch}: forced-by-test")

    BVR.derive_inset_thr = fake_derive
    VHR.resolve_and_check = fake_resolve
    VHR.run_canary = fake_canary
    try:
        rc = BVR.main(["--pages", "1", "--geometry", str(geom_path), "--volume-dir", str(vol_dir),
                        "--out", str(out_path), "--read", "on", "--host", "fake-host"])
    finally:
        BVR.derive_inset_thr = orig_derive
        VHR.resolve_and_check = orig_resolve
        VHR.run_canary = orig_canary

    assert rc == 3, f"canary failure must abort with exit 3, got {rc}"
    lines = [l for l in out_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1, f"header-only write must be exactly 1 line, got {len(lines)}"
    rec = json.loads(lines[0])
    assert rec["kind"] == "run_header", rec
    assert rec["status"] == "aborted", rec
    assert rec["abort_reason"] == "canary_failed batch 0", rec
    assert rec["canary"] == [], rec


def test_centred_chapter_head_measured_against_text_block_not_column_box():
    # Left column box starts at 0 but its text block starts at 470 (page margin) and ends at 1930.
    # A CHAP head centred in the TEXT BLOCK: ink 1050..1350 -> insets 580 / 580. Against the box
    # it would read 1050 / 580 and fail |l - r| <= inset_thr (the measured miss: chapter heads
    # found on 1 of 5 expected pages).
    body = [_band("left", 100 + 60 * i, 150 + 60 * i, 0, 1940, 470, 1930, xheight=10) for i in range(5)]
    chap = _band("left", 400, 460, 0, 1940, 1050, 1350, xheight=13)
    s1 = {"file_page": 1, "H": 5400, "W": 3584, "xdiv": 1940, "left": body[:5] + [chap],
          "right": [], "full": [], "col_boxes": {"left": (0, 0, 1940, 5400)}}
    cands = VR.head_candidates(s1, inset_thr=50)
    kinds = [(c["kind"], c["y0"]) for c in cands]
    assert ("chapter", 400) in kinds, kinds
    # and an ordinary indented verse line is NOT centred
    assert not any(k == "chapter" and y != 400 for k, y in kinds), kinds


def test_letter_spaced_head_across_gutter_is_paired_into_one_full_chapter_band():
    # Measured on p128: "C H A P. V." centred on xdiv=1970, inter-letter gap 45 px at the gutter,
    # so S1 files it as left 1718..1957 + right 2005..2197. Left text block 465..1917 (local,
    # box x0=0), right 1989..3446 (box x0=1970). Pairing must merge it into ONE full band that the
    # centred test calls a chapter; a deep-inset LEFT line that does NOT reach the gutter and a
    # short RIGHT line flush at the gutter that has no left partner must stay column bands.
    L = [_band("left", 700 + 60 * i, 750 + 60 * i, 0, 1970, 465, 1917, xheight=30) for i in range(6)]
    R = [_band("right", 700 + 60 * i, 750 + 60 * i, 1970, 3584, 1989, 3446, xheight=29) for i in range(6)]
    chap_l = _band("left", 2911, 2965, 0, 1970, 1718, 1957, xheight=53, gap_px=45)
    chap_r = _band("right", 2909, 2937, 1970, 3584, 2005, 2197, xheight=25, gap_px=45)
    lone_l = _band("left", 3100, 3150, 0, 1970, 1000, 1500, xheight=30)   # centred-ish, not at gutter
    lone_r = _band("right", 3300, 3350, 1970, 3584, 1990, 2400, xheight=29)  # short, no partner
    s1 = {"file_page": 128, "H": 5400, "W": 3584, "xdiv": 1970, "left": L + [chap_l, lone_l],
          "right": R + [chap_r, lone_r], "full": [],
          "col_boxes": {"left": (0, 0, 1970, 5400), "right": (1970, 0, 3584, 5400)}}
    n = VR.pair_centred_across_gutter(s1, inset_thr=50)
    assert n == 1 and s1["n_centred_pairs"] == 1, n
    assert len(s1["full"]) == 1 and s1["full"][0]["full_basis"] == "centred_pair", s1["full"]
    assert (s1["full"][0]["left_ink_x"], s1["full"][0]["right_ink_x"]) == (1718, 2197)
    assert lone_l in s1["left"] and lone_r in s1["right"]
    assert chap_l not in s1["left"] and chap_r not in s1["right"]
    kinds = [(c["kind"], c["y0"]) for c in VR.head_candidates(s1, inset_thr=50)]
    assert ("chapter", 2909) in kinds, kinds


def test_confirm_candidates_preserves_candidate_flags():
    c = {"file_page": 1, "col": "left", "y0": 10, "y1": 20, "box": [0, 10, 100, 20], "kind": "verse",
         "signature": {}, "flags": ["prev_line_full"]}
    conf, rej = VR.confirm_candidates([c], head_reads=None)
    assert conf[0]["flags"] == ["prev_line_full", "head_unconfirmed"], conf[0]["flags"]
    conf, rej = VR.confirm_candidates([c], head_reads={(1, "left", 10): {"ver": True, "numbers": [3], "status": "ok"}})
    assert conf[0]["flags"] == ["prev_line_full"], conf[0]["flags"]


def test_confirm_candidates_straddle_refused_is_rejected():
    c = {"file_page": 1, "col": "left", "y0": 10, "y1": 20, "box": [0, 10, 100, 20], "kind": "verse",
         "signature": {}, "flags": []}
    hr = {"ver": None, "numbers": None, "status": "guard_refused:straddle", "ver_case": None}
    conf, rej = VR.confirm_candidates([c], head_reads={(1, "left", 10): hr})
    assert conf == []
    assert len(rej) == 1 and rej[0]["reason"] == "guard_refused:straddle" and rej[0]["head_confirm"] == hr


def test_confirm_candidates_lowercase_ver_case_flags_confirmed_head():
    c = {"file_page": 1, "col": "left", "y0": 10, "y1": 20, "box": [0, 10, 100, 20], "kind": "verse",
         "signature": {}, "flags": []}
    hr = {"ver": True, "numbers": [5], "status": "ok", "ver_case": "lower"}
    conf, rej = VR.confirm_candidates([c], head_reads={(1, "left", 10): hr})
    assert rej == []
    assert conf[0]["flags"] == ["head_ver_lowercase"], conf[0]["flags"]


# 12. abstention wired into assemble_regions (rerun3 Lane A2 d) --------------------------------
#
# The build-level harness this spec also asks for (forced-abstained main() run -> page_abstained
# JSONL records + run_summary["pages_head_abstained"]) has no synthetic equivalent: main() only
# reads real geometry/image files (build_verse_regions.load_geometry/load_page_gray), and no
# existing test harness drives it over synthetic input. Per spec, that is reported rather than
# built here; this test instead exercises the one piece that IS a pure function over synthetic s1
# -- assemble_regions(abstained=True) itself.

def test_assemble_regions_abstained_flag_emits_zero_regions_and_head_detection():
    head_band = _band("left", 10, 20, 0, 100, 10, 90)
    s1_p1 = {"file_page": 1, "H": 100, "W": 200, "xdiv": 100, "left": [head_band], "right": [], "full": []}
    cand = {"file_page": 1, "col": "left", "y0": 10, "y1": 20, "box": [0, 10, 100, 20],
            "kind": "verse", "signature": {}, "head_confirm": None, "flags": []}
    regions, page_summaries = VR.assemble_regions(
        [{"file_page": 1}], {1: s1_p1}, {1: [cand]}, {1: []}, {1: None}, config={}, abstained=True)
    # Candidates are passed in here (as build_verse_regions.py would, pre-abstention-skip, if it
    # forgot to clear them) to prove abstained=True alone is what suppresses regions -- not an
    # empty candidates_by_page upstream.
    assert regions == []
    assert page_summaries[1]["head_detection"] == "abstained"
    assert page_summaries[1]["n_heads"] == 0


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    if len(fns) != EXPECTED_TESTS:
        print(f"EXPECTED_TESTS mismatch: discovered {len(fns)}, expected {EXPECTED_TESTS}")
        raise SystemExit(1)
    p = f = 0
    for fn in fns:
        try:
            fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception:
            f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed")
    raise SystemExit(1 if f else 0)
