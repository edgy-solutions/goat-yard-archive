"""verse_regions / verse_head_read born-tests: synthetic-ink unit tests, one per rule, each
designed to FAIL if the rule it tests is removed (see the mutation-check notes in the handoff
report). Run: python test_verse_regions.py

EXPECTED_TESTS asserts the suite's OWN test count (test_marker_ledger.py's pattern) so a
silently-dropped test function fails the run instead of just passing with fewer checks.
"""
import numpy as np

import verse_regions as VR
import verse_head_read as VHR

EXPECTED_TESTS = 94


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


# 3c. head rule under the running head is furniture ----------------------------------------------

def _hr_page(rule=None, head=True, text_h=50, n_lines=5, text_y0=200, extra=None, H=1000):
    """Two-column synthetic page. Head 20..100 (y0 < 0.119*H=119.0). Text lines of uniform height
    text_h with 20px gaps, low fill (4px strokes on / 8 off) in the left column. rule = (y0, y1, kind)
    with kind 'rule' (middle 3 rows inked across the column), 'word' (low-fill short word),
    'solid' (fully inked)."""
    W, xdiv = 800, 400
    ink = np.zeros((H, W), dtype=bool)
    if head:
        ink[20:100, 160:640] = True

    def strokes(y0, y1, x0=20, x1=380):
        for x in range(x0, x1, 12):
            ink[y0:y1, x:x + 4] = True

    for i in range(n_lines):
        y = text_y0 + i * (text_h + 20)
        strokes(y, y + text_h)
    if extra:
        extra(ink, strokes)
    if rule is not None:
        y0, y1, kind = rule
        if kind == "rule":
            # a bare 3-row line is dropped by text_lines (too little ink to open a band), so the
            # rule band carries low-fill dust across its full height around the solid middle rows
            strokes(y0, y1)
            mid = (y0 + y1) // 2
            ink[mid - 1:mid + 2, 20:380] = True
        elif kind == "word":
            strokes(y0, y1, 20, 80)
        elif kind == "solid":
            ink[y0:y1, 20:380] = True
    geom = {"file_page": 1, "xdiv": xdiv,
            "body_regions": [{"col": "left", "box": [0, 0, 400, H]},
                              {"col": "right", "box": [400, 0, 800, H]}]}
    return VR.analyze_page_s1(ink, geom)


def _hr_has_band(s1, y0, y1):
    return any(b["y0"] == y0 and b["y1"] == y1 for col in ("left", "right", "full") for b in s1[col])


def test_head_rule_removed_under_running_head():
    s1 = _hr_page(rule=(125, 150, "rule"))
    assert s1["running_head"] is not None
    assert len(s1["head_rules"]) == 1, s1["head_rules"]
    hr = s1["head_rules"][0]
    assert hr["col"] == "left" and hr["y0"] == 125 and hr["y1"] == 150, hr
    assert not _hr_has_band(s1, 125, 150)
    assert "head_rule_removed:left" in s1["flags"]
    assert len(s1["left"]) == 5, len(s1["left"])


def test_head_rule_thin_low_fill_word_kept():
    s1 = _hr_page(rule=(125, 150, "word"))
    assert s1["head_rules"] == [], s1["head_rules"]
    assert _hr_has_band(s1, 125, 150)


def test_head_rule_no_running_head_kept():
    s1 = _hr_page(rule=(125, 150, "rule"), head=False)
    assert s1["running_head"] is None
    assert s1["head_rules"] == [], s1["head_rules"]
    assert _hr_has_band(s1, 125, 150)


def test_head_rule_thick_high_fill_band_kept():
    s1 = _hr_page(rule=(125, 175, "solid"))
    assert s1["head_rules"] == [], s1["head_rules"]
    assert _hr_has_band(s1, 125, 175)


def test_head_rule_non_topmost_thin_high_fill_band_kept():
    # a text line first (125..175), then a thin inked rule below it -> not topmost
    def extra(ink, strokes):
        strokes(125, 175)
    s1 = _hr_page(rule=(195, 220, "rule"), text_y0=240, n_lines=4, extra=extra)
    assert s1["head_rules"] == [], s1["head_rules"]
    assert _hr_has_band(s1, 195, 220)


def test_head_rule_not_adjacent_kept():
    # median line h = 50; rule starts 150 -> 150-100 = 50 >= median_line_h -> not adjacent
    s1 = _hr_page(rule=(150, 175, "rule"), text_y0=230, n_lines=4)
    assert s1["head_rules"] == [], s1["head_rules"]
    assert _hr_has_band(s1, 150, 175)


def test_head_rule_multi_line_median_abstains_flagged():
    s1 = _hr_page(rule=(125, 150, "rule"), text_h=120, text_y0=200, n_lines=4)
    assert s1["head_rules"] == [], s1["head_rules"]
    assert "head_rule_abstained:line_h_multi" in s1["flags"], s1["flags"]
    assert s1["flags"].count("head_rule_abstained:line_h_multi") == 1
    assert _hr_has_band(s1, 125, 150)


# 3d. head-rule height clause on the deskewed band height (ruling 3, 2026-10-25) -------------------

def _hr_wide_page(kind, slope=0.03, band_h=35, W=2400, H=1000, y0=125):
    """Sibling of _hr_page for wide pages (W >= 2000) so a shallow slope still gives the needed
    height. Running head 20..100; five 50px stripe-text lines in the left column; kind 'tilt' = a
    10px-thick rule tilted by `slope` rows/px across the column, 'mid' = a stripe-text band of band_h."""
    xdiv = W // 2
    ink = np.zeros((H, W), dtype=bool)
    ink[20:100, 600:1800] = True

    def strokes(a, b, x0=20, x1=xdiv - 20):
        for x in range(x0, x1, 12):
            ink[a:b, x:x + 4] = True

    for i in range(5):
        y = 300 + i * 70
        strokes(y, y + 50)
    if kind == "tilt":
        for x in range(20, xdiv - 20):
            c = int(y0 + 3 + slope * (x - 20))
            ink[c:c + 10, x] = True
    elif kind == "mid":
        strokes(y0, y0 + band_h)
    geom = {"file_page": 1, "xdiv": xdiv,
            "body_regions": [{"col": "left", "box": [0, 0, xdiv, H]},
                              {"col": "right", "box": [xdiv, 0, W, H]}]}
    return VR.analyze_page_s1(ink, geom)


def test_band_tilt_recovers_known_slope_of_thin_line():
    H, W, slope = 400, 1400, 0.02
    ink = np.zeros((H, W), dtype=bool)
    for x in range(W):
        c = int(100 + slope * x)
        ink[c:c + 12, x] = True
    k, n = VR.band_tilt(ink, {"y0": 80, "y1": 200, "x0": 0, "x1": W})
    assert n >= 10, n
    assert abs(k - slope) <= 0.05 * slope, (k, slope)


def test_band_tilt_stripe_text_is_untilted():
    ink = np.zeros((200, 1200), dtype=bool)
    for x in range(20, 1180, 12):
        ink[50:100, x:x + 4] = True
    k, n = VR.band_tilt(ink, {"y0": 50, "y1": 100, "x0": 0, "x1": 1200})
    assert n >= 10 and abs(k) < 1e-3, (k, n)


def test_band_tilt_fewer_than_three_bins_is_zero():
    ink = np.zeros((200, 1200), dtype=bool)
    ink[50:100, 0:200] = True            # only two qualifying 100px bins
    k, n = VR.band_tilt(ink, {"y0": 50, "y1": 100, "x0": 0, "x1": 1200})
    assert k == 0.0 and n == 2, (k, n)


def test_head_rule_tilted_rule_removed_only_by_deskew():
    s1 = _hr_wide_page("tilt")
    assert len(s1["head_rules"]) == 1, s1["head_rules"]
    hr = s1["head_rules"][0]
    assert hr["h_frac"] >= 0.75, hr                     # the OLD axis-aligned clause rejects it
    assert hr["h_desk_frac"] < VR.HEAD_RULE_MAX_H_FRAC, hr
    assert hr["fill_max"] >= 0.275, hr
    assert "head_rule_removed:left" in s1["flags"]
    real = VR.band_tilt
    VR.band_tilt = lambda ink, b, **kw: (0.0, 0)
    try:
        s1_off = _hr_wide_page("tilt")
    finally:
        VR.band_tilt = real
    assert s1_off["head_rules"] == [], "without the deskew the tilted rule must NOT be removed"


def test_head_rule_untilted_band_between_thresholds_kept():
    s1 = _hr_wide_page("mid", band_h=35)                # h/mlh = 0.70: old 0.75 removes, 0.675 keeps
    assert s1["head_rules"] == [], s1["head_rules"]
    assert _hr_has_band(s1, 125, 160)


P923_IMG = "C:/Users/cnogr/git/dr-voluminous/commentary/volume1/page923_image1.png"
P923_GEOM = "C:/Users/cnogr/git/dr-voluminous/body_shadow_vol1/geometry/volume1_page_geometry.jsonl"


def test_head_rule_p923_tilted_rule_removed():
    import json
    import os
    from PIL import Image
    for path in (P923_IMG, P923_GEOM):
        assert os.path.exists(path), f"p923 born-test input missing: {path}"
    ink = VR.page_ink(np.asarray(Image.open(P923_IMG).convert("L")))
    geom = None
    with open(P923_GEOM, encoding="utf-8") as f:
        for line in f:
            g = json.loads(line)
            if g["file_page"] == 923:
                geom = g
                break
    assert geom is not None, f"no file_page 923 row in {P923_GEOM}"
    s1 = VR.analyze_page_s1(ink, geom)
    hits = [r for r in s1["head_rules"] if r["col"] == "full" and r["y0"] == 677 and r["y1"] == 741]
    assert len(hits) == 1, s1["head_rules"]
    assert hits[0]["h_desk_frac"] < 0.675 and hits[0]["h_frac"] > 0.75, hits[0]



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


# ---- column split from the printed rule (fix A) ----------------------------------------------
# Synthetic pages only. A page is 3584 x 5000; the printed double rule is two 6-px lines 6 px apart
# (18 px overall) along centre(y) = c0 + slope*y; type is low-fill strokes (10 on / 8 off) in lines
# 44 tall on a 120 pitch (column ink fraction 0.37, under RULE_COL_FRAC).

_CS_W, _CS_H = 3584, 5000
_CS_LINE_H, _CS_PITCH, _CS_Y0 = 44, 120, 800
_CS_RULE_Y = 4600          # geometry footnote rule -> y_end = 4580


def _cs_centre(c0, slope, y):
    return c0 + slope * y


def _cs_page(c0=1939.6, slope=0.00828, xdiv=1931, rule=True, flank=18, jump=None, full_line_y=None,
             right_flank=None):
    """Returns (ink, geom, texts) where texts = {(col, y0): (x_start, x_end)} the synthetic type extents.
    Left type ends `flank` px left of the rule's left edge on every line; right type starts `flank` px
    right of the rule's right edge. No rule -> the same type with a fixed 140-px gutter around c0."""
    ink = np.zeros((_CS_H, _CS_W), dtype=bool)

    def centre(y):
        c = _cs_centre(c0, slope, y)
        if jump is not None and y >= jump[0]:
            c += jump[1]
        return c

    if rule:
        for y in range(700, _CS_RULE_Y):
            c = int(round(centre(y)))
            ink[y, c - 9:c - 3] = True
            ink[y, c + 3:c + 9] = True
    texts = {}
    rf = flank if right_flank is None else right_flank
    for y in range(_CS_Y0, _CS_RULE_Y - 120, _CS_PITCH):
        yb = y + _CS_LINE_H
        c_lo = min(centre(y), centre(yb - 1))
        c_hi = max(centre(y), centre(yb - 1))
        if rule:
            l_end = int(np.floor(c_lo - 9 - flank))
            r_start = int(np.ceil(c_hi + 9 + rf))
        else:
            l_end, r_start = int(c0 - 70), int(c0 + 70)
        for x in range(l_end - 10, 100, -18):          # strokes anchored so the last one ends at l_end
            ink[y:yb, x:x + 10] = True
        l_start = x
        for x in range(r_start, _CS_W - 100, 18):
            ink[y:yb, x:x + 10] = True
        r_end = x + 10
        texts[("left", y)] = (l_start, l_end)
        texts[("right", y)] = (r_start, r_end)
    if full_line_y is not None:
        for x in range(100, _CS_W - 100, 18):
            ink[full_line_y:full_line_y + _CS_LINE_H, x:x + 10] = True
    geom = {"file_page": 1, "mode": "two_column", "xdiv": xdiv, "page": [_CS_W, _CS_H],
            "rules": [_CS_RULE_Y, _CS_RULE_Y],
            "body_regions": [{"col": "left", "box": [0, 640, xdiv, _CS_RULE_Y]},
                              {"col": "right", "box": [xdiv, 640, _CS_W, _CS_RULE_Y]}]}
    return ink, geom, texts


def test_col_split_745_like_far_xdiv():
    c0, slope = 1754.0, -0.0169
    ink, geom, _ = _cs_page(c0=c0, slope=slope, xdiv=1482)
    s1 = VR.analyze_page_s1(ink, geom)
    sp = s1["col_split"]
    assert sp["status"] == "ok", sp
    assert abs(sp["c0"] - 1754) <= 3 and abs(sp["slope"] - slope) < 0.002, sp
    assert s1["full"] == [], [(b["y0"], b["y1"]) for b in s1["full"]]
    assert s1["left"] and all(b["right_ink_x"] > 1482 for b in s1["left"])
    lbox = s1["col_boxes"]["left"]
    rule_left_at_top = _cs_centre(c0, slope, lbox[1]) - 9
    assert lbox[2] >= rule_left_at_top - 1, (lbox, rule_left_at_top)
    # control: the geometry-xdiv behaviour (split abstained) files full bands on this very page, so the
    # assertions above would FAIL on the pre-split code (proves the test is sensitive to the bug)
    orig = VR.locate_column_rule
    VR.locate_column_rule = lambda ink_, g_: {"status": "abstained", "reason": "no_rule"}
    try:
        old = VR.analyze_page_s1(ink, geom)
    finally:
        VR.locate_column_rule = orig
    assert old["full"], "control: geometry xdiv must file a full band on the 745-like page"


def test_col_split_p23_like_no_rule_abstains():
    ink, geom, _ = _cs_page(c0=1790, slope=0.0, xdiv=1790, rule=False)
    s1 = VR.analyze_page_s1(ink, geom)
    assert s1["col_split"]["status"] == "abstained" and s1["col_split"]["reason"] == "no_rule", s1["col_split"]
    assert s1["flags"].count("col_split_abstained:no_rule") == 1, s1["flags"]
    assert s1["col_boxes"] == {r["col"]: tuple(r["box"]) for r in geom["body_regions"]}
    assert s1["xdiv_effective"] == 1790 and s1["xdiv"] == 1790


def test_col_split_130_like_normal_page():
    c0, slope = 1939.6, 0.00828
    ink, geom, texts = _cs_page(c0=c0, slope=slope, xdiv=1931, flank=18)
    s1 = VR.analyze_page_s1(ink, geom)
    assert s1["col_split"]["status"] == "ok", s1["col_split"]
    assert s1["left"] and s1["right"]
    for b in s1["left"]:
        l_start, l_end = texts[("left", b["y0"])]
        assert b["right_ink_x"] == l_end, (b["y0"], b["right_ink_x"], l_end)
    for b in s1["right"]:
        rule_right = _cs_centre(c0, slope, (b["y0"] + b["y1"]) / 2) + 9
        assert b["left_ink_x"] >= rule_right, (b["y0"], b["left_ink_x"], rule_right)
    assert s1["col_boxes"]["left"][2] > 1931
    assert s1["xdiv_effective"] == int(round(VR.split_centre(s1["col_split"], sum(s1["col_split"]["y_range"]) / 2)))
    assert "col_split" in s1 and "strips" not in s1["col_split"]


def test_col_split_nonlinear_track_abstains():
    ink, geom, _ = _cs_page(c0=1939.6, slope=0.0, xdiv=1931, jump=(2800, 40))
    s1 = VR.analyze_page_s1(ink, geom)
    assert s1["col_split"]["status"] == "abstained" and s1["col_split"]["reason"] == "track_nonlinear", s1["col_split"]
    assert "col_split_abstained:track_nonlinear" in s1["flags"]
    assert s1["col_boxes"]["left"][2] == 1931


def test_col_split_full_width_line_still_full():
    ink, geom, _ = _cs_page(c0=1939.6, slope=0.00828, xdiv=1931, full_line_y=2400 + 0)
    s1 = VR.analyze_page_s1(ink, geom)
    assert s1["col_split"]["status"] == "ok"
    assert any(b["y0"] <= 2400 + _CS_LINE_H and b["y1"] >= 2400 for b in s1["full"]), \
        ([(b["y0"], b["y1"]) for b in s1["full"]], [(b["y0"], b["y1"]) for b in s1["left"] if 2300 < b["y0"] < 2500])


def test_adapter_geom_uses_split_at_rect_mid():
    geom = {"page": [3584, 5000], "xdiv": 1500, "rules": [4600, 4600]}
    assert VR.adapter_geom(geom, "left", 100, y_mid=2000)["gutter"] == 1500
    geom["_s1"] = {"col_split": {"status": "abstained", "reason": "no_rule"}}
    assert VR.adapter_geom(geom, "left", 100, y_mid=2000)["gutter"] == 1500
    geom["_s1"] = {"col_split": {"status": "ok", "slope": 0.01, "c0": 1700.0, "y_range": [700, 4580]}}
    assert VR.adapter_geom(geom, "left", 100, y_mid=2000)["gutter"] == round(0.01 * 2000 + 1700.0)
    assert VR.adapter_geom(geom, "right", 100, y_mid=4000)["gutter"] == round(0.01 * 4000 + 1700.0)
    assert VR.adapter_geom(geom, "left", 100)["gutter"] == round(0.01 * 2640 + 1700.0)



def test_col_split_band_x_edges_tight_to_slanted_split():
    c0, slope = 1754.0, -0.0169            # 65 px of drift over the body
    ink, geom, _ = _cs_page(c0=c0, slope=slope, xdiv=1700)
    s1 = VR.analyze_page_s1(ink, geom)
    sp = s1["col_split"]
    assert sp["status"] == "ok" and abs(sp["slope"] * (sp["y_range"][1] - sp["y_range"][0])) >= 50, sp
    lbox, rbox = s1["col_boxes"]["left"], s1["col_boxes"]["right"]
    bottom_left = [b for b in s1["left"] if b["y0"] > 4000]
    top_right = [b for b in s1["right"] if b["y1"] < 1400]
    assert bottom_left and top_right
    for b in bottom_left:
        le = max(VR.left_edge(sp, b["y0"]), VR.left_edge(sp, b["y1"] - 1))
        assert b["x1"] <= le + 1 and b["x1"] < lbox[2] - 30, (b["y0"], b["x1"], le, lbox)
    for b in top_right:
        re_ = min(VR.right_edge(sp, b["y0"]), VR.right_edge(sp, b["y1"] - 1))
        assert b["x0"] >= re_ - 1 and b["x0"] > rbox[0] + 30, (b["y0"], b["x0"], re_, rbox)


# 99. Step 3 (rerun 8): ink_box standoff with stroke-width fragment exclusion --------------------
# PREDICTION_step3_inkbox_rerun8_20261025.md. Synthetic page: H=500, W=400, median_line_h=60
# (tall limit 1.6*60 = 96 rows), a left-column rect box [0, y0, 200, y1]. Synthetic components are
# 10 px wide blocks (stroke_w 10), above the 4.5 cutoff used here.

STROKE_OK = {"status": "ok", "cutoff": 4.5}


def _bfs_components(m):
    H, W = m.shape
    seen = np.zeros_like(m, dtype=bool)
    out = []
    for y in range(H):
        for x in range(W):
            if m[y, x] and not seen[y, x]:
                stack = [(y, x)]
                seen[y, x] = True
                x0, y0, x1, y1 = x, y, x + 1, y + 1
                while stack:
                    cy, cx = stack.pop()
                    x0, y0, x1, y1 = min(x0, cx), min(y0, cy), max(x1, cx + 1), max(y1, cy + 1)
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            ny, nx = cy + dy, cx + dx
                            if 0 <= ny < H and 0 <= nx < W and m[ny, nx] and not seen[ny, nx]:
                                seen[ny, nx] = True
                                stack.append((ny, nx))
                out.append((x0, y0, x1, y1))
    return sorted(out, key=lambda b: (b[1], b[0], b[3], b[2]))


def test_ink_components_is_8_connected():
    """Guards the connectivity: diagonal touch joins (8-connected), a 1-px gap does not."""
    m = np.zeros((10, 10), dtype=bool)
    m[2, 2] = True
    m[3, 3] = True
    assert VR.ink_components(m) == [(2, 2, 4, 4)], VR.ink_components(m)
    m = np.zeros((10, 10), dtype=bool)
    m[2, 2] = True
    m[2, 4] = True
    assert len(VR.ink_components(m)) == 2
    m = np.zeros((10, 10), dtype=bool)
    m[2, 2] = True
    m[4, 4] = True
    assert len(VR.ink_components(m)) == 2


def test_ink_components_matches_bfs_reference_on_random_masks():
    """Guards the union-find against a brute-force 8-connected BFS on 20 seeded random masks."""
    for seed in range(20):
        m = np.random.RandomState(seed).rand(30, 40) < 0.3
        assert VR.ink_components(m) == _bfs_components(m), seed


def _ib_band(y0, y1, x0=0, x1=400, col="left"):
    return {"col": col, "x0": x0, "x1": x1, "y0": y0, "y1": y1}


def _ib_s1(left=(), full=(), running_head=None, head_rules=(), mlh=60):
    return {"left": list(left), "right": [], "full": list(full), "slivers": [],
            "running_head": running_head, "head_rules": list(head_rules), "median_line_h": mlh}


def _ib_run(s1, comps, box, col="left", cutoff=STROKE_OK):
    ink = np.zeros((500, 400), dtype=bool)
    for (x0, y0, x1, y1) in comps:
        ink[y0:y1, x0:x1] = True
    region = {"flags": [], "rects": [{"file_page": 7, "col": col, "box": list(box)}]}
    counts = VR.apply_ink_box_page([region], 7, s1, ink, cutoff)
    return region, region["rects"][0], counts


def test_ink_box_capital_raises_top_and_box_untouched():
    """Guards the purpose and the box law: a tall initial capital owned by the first band lifts
    ink_box top to 70 while rect["box"] stays exactly the input."""
    first = _ib_band(100, 150)
    _, rect, _ = _ib_run(_ib_s1(left=[first]), [(50, 70, 60, 150)], [0, 100, 200, 150])
    assert rect["box"] == [0, 100, 200, 150], rect
    assert rect["ink_box"] == [0, 70, 200, 150] and rect["ink_box_detail"]["n_first"] >= 1, rect


def test_ink_box_neighbour_descender_owned_by_neighbour():
    """Guards ownership: a component sharing 35 rows with the previous band and 4 with the first
    band belongs to the neighbour and must not move the top."""
    s1 = _ib_s1(left=[_ib_band(40, 95), _ib_band(100, 150)])
    _, rect, _ = _ib_run(s1, [(50, 60, 60, 104)], [0, 100, 200, 150])
    assert rect["ink_box"][1] == 100 and rect["ink_box_detail"]["n_first"] == 0, rect


def test_ink_box_running_head_owns_its_ink():
    """Guards the owner set: running head and head rules own their ink."""
    s1 = _ib_s1(left=[_ib_band(100, 150)], running_head=_ib_band(40, 95, col="full"))
    _, rect, _ = _ib_run(s1, [(50, 60, 60, 104)], [0, 100, 200, 150])
    assert rect["ink_box"][1] == 100, rect
    s1 = _ib_s1(left=[_ib_band(100, 150)], head_rules=[_ib_band(40, 95, col="left")])
    _, rect, _ = _ib_run(s1, [(50, 60, 60, 104)], [0, 100, 200, 150])
    assert rect["ink_box"][1] == 100, rect


def test_ink_box_tall_component_excluded_and_flagged():
    """Guards the tall exclusion (h > 1.6 x mlh): listed in excluded_tall, flagged, moves nothing."""
    first = _ib_band(100, 150)
    region, rect, counts = _ib_run(_ib_s1(left=[first]), [(50, 60, 60, 240)], [0, 100, 200, 150])
    assert rect["ink_box"] == [0, 100, 200, 150], rect
    assert rect["ink_box_detail"]["excluded_tall"] == [[50, 60, 60, 240]], rect["ink_box_detail"]
    assert rect["ink_box_detail"]["excluded_stroke"] == []
    assert "ink_box_excluded_tall" in region["flags"] and counts["n_excluded_tall"] == 1


def test_ink_box_thin_fragment_excluded_by_stroke_and_flagged():
    """Guards the stroke exclusion: a 2 px wide, 50 row (>= 0.5 x mlh) fragment crossing the first
    band's top is excluded (listed with its stroke_w), moves nothing, and flags the region; a 10 px
    wide twin is a letter and moves the top. Tall is tested first: a 2 px x 100 row stroke goes to
    excluded_tall only."""
    first = _ib_band(100, 150)
    region, rect, counts = _ib_run(_ib_s1(left=[first]), [(50, 70, 52, 120)], [0, 100, 200, 150])
    assert rect["ink_box"] == [0, 100, 200, 150], rect
    assert rect["ink_box_detail"]["excluded_stroke"] == [[50, 70, 52, 120, 2.0]], rect["ink_box_detail"]
    assert "ink_box_excluded_stroke" in region["flags"] and counts["n_excluded_stroke"] == 1
    _, rect, _ = _ib_run(_ib_s1(left=[first]), [(50, 70, 60, 120)], [0, 100, 200, 150])
    assert rect["ink_box"][1] == 70, rect
    region, rect, _ = _ib_run(_ib_s1(left=[first]), [(50, 70, 52, 170)], [0, 100, 200, 150])
    assert rect["ink_box_detail"]["excluded_tall"] == [[50, 70, 52, 170]]
    assert rect["ink_box_detail"]["excluded_stroke"] == []


def test_ink_box_edges_only_grow():
    """Guards grow-only: components strictly inside the bands leave ink_box equal to box."""
    first, last = _ib_band(100, 150), _ib_band(200, 250)
    _, rect, counts = _ib_run(_ib_s1(left=[first, last]), [(50, 110, 60, 140), (50, 210, 60, 240)],
                              [0, 100, 200, 250])
    assert rect["ink_box"] == [0, 100, 200, 250], rect
    assert counts["n_top_moved"] == 0 and counts["n_bottom_moved"] == 0


def test_ink_box_descender_lowers_bottom():
    """Guards the bottom edge: last band 300-350, component 320-362 -> ink_box bottom 362."""
    _, rect, counts = _ib_run(_ib_s1(left=[_ib_band(300, 350)]), [(50, 320, 60, 362)], [0, 300, 200, 350])
    assert rect["ink_box"][3] == 362 and rect["box"][3] == 350, rect
    assert rect["ink_box_detail"]["n_last"] == 1 and counts["n_bottom_moved"] == 1


def test_ink_box_tie_between_owners_moves_nothing():
    """Guards the tie rule: equal shared rows with two bands -> unassigned and counted."""
    s1 = _ib_s1(left=[_ib_band(60, 100), _ib_band(100, 150)])
    _, rect, _ = _ib_run(s1, [(50, 90, 60, 110)], [0, 100, 200, 150])
    assert rect["ink_box"][1] == 100 and rect["ink_box_detail"]["n_tie"] == 1, rect


def test_ink_box_x_equals_box_and_other_column_ignored():
    """Guards x and the rect x-range: ink_box x equals box x; a component outside the x-range has no effect."""
    first = _ib_band(100, 150, x0=0, x1=400)
    _, rect, _ = _ib_run(_ib_s1(left=[first]), [(250, 60, 260, 150)], [0, 100, 200, 150])
    assert rect["ink_box"] == [0, 100, 200, 150], rect
    _, rect, _ = _ib_run(_ib_s1(left=[first]), [(50, 70, 60, 150)], [0, 100, 200, 150])
    assert rect["ink_box"][0] == 0 and rect["ink_box"][2] == 200 and rect["ink_box"][1] == 70, rect


def test_ink_box_no_band_flagged():
    """Guards the no-band path: a rect containing no S1 band gets no ink_box and the region is
    flagged ink_box_no_band."""
    region, rect, counts = _ib_run(_ib_s1(left=[_ib_band(300, 350)]), [(50, 70, 60, 150)], [0, 100, 200, 150])
    assert rect["box"] == [0, 100, 200, 150] and "ink_box" not in rect
    assert "ink_box_no_band" in region["flags"] and counts["n_no_band"] == 1


# --- derive_stroke_cutoff (B5, synthetic) ---------------------------------------------------------

def _widths(counts):
    """{bin: count} -> list of stroke widths (bin + 0.5)."""
    return [b + 0.5 for b, n in counts.items() for _ in range(n)]


BIMODAL = {1: 50, 2: 2, 3: 10, 4: 10, 5: 10, 6: 10, 7: 1000, 8: 300}


def _floors(h3, h, a20):
    return {"third": _widths(h3), "half": _widths(h), "abs20": _widths(a20)}


def test_derive_stroke_cutoff_bimodal_gives_4_5():
    r = VR.derive_stroke_cutoff(_floors(BIMODAL, BIMODAL, BIMODAL))
    assert r["status"] == "ok" and r["cutoff"] == 4.5, r
    for rec in r["per_floor"].values():
        assert (rec["F"], rec["v"], rec["L"], rec["bimodal"], rec["cutoff"]) == (1, 2, 7, True, 4.5), rec
        assert rec["hist"][1:9] == [50, 2, 10, 10, 10, 10, 1000, 300]


def test_derive_stroke_cutoff_unimodal_abstains():
    uni = {1: 5, 2: 20, 3: 100, 4: 400, 5: 1000, 6: 400, 7: 100}
    r = VR.derive_stroke_cutoff(_floors(uni, uni, uni))
    assert r["status"] == "abstain" and r["cutoff"] is None, r


def test_derive_stroke_cutoff_floors_disagree_on_F_abstains():
    other = {1: 30, 2: 50, 3: 3, 4: 10, 5: 10, 6: 10, 7: 1000}
    r = VR.derive_stroke_cutoff(_floors(BIMODAL, other, BIMODAL))
    assert r["per_floor"]["half"]["bimodal"] and r["per_floor"]["half"]["F"] == 2, r["per_floor"]["half"]
    assert r["per_floor"]["third"]["F"] == 1
    assert r["status"] == "abstain" and r["cutoff"] is None, r


def test_derive_stroke_cutoff_fragment_peak_below_5_abstains():
    low = dict(BIMODAL)
    low[1] = 4
    r = VR.derive_stroke_cutoff(_floors(low, low, low))
    assert r["per_floor"]["half"]["F"] == 1 and not r["per_floor"]["half"]["bimodal"], r
    assert r["status"] == "abstain"


def test_derive_stroke_cutoff_failed_separation_abstains():
    sep = {1: 100, 2: 100, 3: 100, 4: 100, 5: 101, 6: 10, 7: 1000}     # F=5, v=6, L=7: 5.5 > 0.5*7.5
    r = VR.derive_stroke_cutoff(_floors(sep, sep, sep))
    rec = r["per_floor"]["half"]
    assert (rec["F"], rec["v"], rec["L"]) == (5, 6, 7) and not rec["bimodal"], rec
    assert r["status"] == "abstain"


def test_ink_box_abstain_sets_null_and_flag_on_every_rect():
    """Guards the abstain path (proved live by mutation): status abstain -> ink_box and
    ink_box_detail None on every rect, region flagged ink_box_abstain_stroke, nothing computed."""
    first = _ib_band(100, 150)
    region, rect, counts = _ib_run(_ib_s1(left=[first]), [(50, 70, 60, 150)], [0, 100, 200, 150],
                                   cutoff={"status": "abstain", "cutoff": None})
    assert rect["ink_box"] is None and rect["ink_box_detail"] is None, rect
    assert rect["box"] == [0, 100, 200, 150]
    assert "ink_box_abstain_stroke" in region["flags"] and counts["n_abstain"] == 1


# --- real pages (private data referenced by path, never copied; inputs asserted, never skipped) ---

IB_VOL = "C:/Users/cnogr/git/dr-voluminous/commentary/volume1"
IB_GEOM = "C:/Users/cnogr/git/dr-voluminous/body_shadow_vol1/geometry/volume1_page_geometry.jsonl"
IB_RUN7 = ("C:/Users/cnogr/git/dr-voluminous/body_shadow_vol1/verse_regions/"
           "run_step3_rerun7_inkextent_d_20p_20261025.jsonl")
IB_PAGES = [90, 91, 92, 126, 127, 128, 129, 130, 151, 197, 198, 199, 200, 402, 403, 404, 745, 923, 924, 925]


def _ib_page_geom(fp):
    import json
    import os
    assert os.path.exists(IB_GEOM), IB_GEOM
    with open(IB_GEOM, encoding="utf-8") as f:
        for line in f:
            g = json.loads(line)
            if g["file_page"] == fp:
                return g
    raise AssertionError(f"no file_page {fp} row in {IB_GEOM}")


def _ib_page_ink(fp):
    import os
    from PIL import Image
    path = f"{IB_VOL}/page{fp}_image1.png"
    assert os.path.exists(path), path
    return VR.page_ink(np.asarray(Image.open(path).convert("L")))


def _ib_fixture(fp):
    """Rerun-7 records with box y reset to the line geometry (ink_extent top/bottom_detected),
    ink_extent deleted. Returns (regions, rerun7_ink_extent_by_rect_id, s1, ink)."""
    import copy
    import json
    import os
    assert os.path.exists(IB_RUN7), IB_RUN7
    regs, ie_by = [], {}
    with open(IB_RUN7, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("rects") is None or r.get("kind") not in ("verse", "chapter_intro", "continuation_unanchored"):
                continue
            r = copy.deepcopy(r)
            for x in r["rects"]:
                ie = x.pop("ink_extent", None)
                if ie:
                    x["box"][1], x["box"][3] = ie["top_detected"], ie["bottom_detected"]
                ie_by[id(x)] = ie
            regs.append(r)
    ink = _ib_page_ink(fp)
    s1 = VR.analyze_page_s1(ink, _ib_page_geom(fp))
    return regs, ie_by, s1, ink


def _ib_target(regs, ie_by, fp, col, key, val):
    hits = [x for r in regs for x in r["rects"]
            if x["file_page"] == fp and x["col"] == col and ie_by[id(x)] and ie_by[id(x)][key] == val]
    assert len(hits) == 1, (fp, col, key, val, len(hits))
    return hits[0]


def test_ib_p197_stroke_fragment_does_not_set_bottom():
    regs, ie_by, s1, ink = _ib_fixture(197)
    t = _ib_target(regs, ie_by, 197, "left", "bottom", 2203)
    VR.apply_ink_box_page(regs, 197, s1, ink, STROKE_OK)
    assert [1634, 2109, 1636, 2203] in [e[:4] for e in t["ink_box_detail"]["excluded_stroke"]], t["ink_box_detail"]
    assert t["ink_box"][3] < 2203, t["ink_box"]
    assert t["ink_box"][3] - t["box"][3] <= 20, (t["ink_box"], t["box"])
    below = [x for r in regs for x in r["rects"]
             if x["file_page"] == 197 and x["col"] == "left" and x["box"][1] > t["box"][1]]
    nxt = min(below, key=lambda x: x["box"][1])
    assert nxt["ink_box"] is not None
    overlap = max(0, t["ink_box"][3] - nxt["ink_box"][1])
    assert overlap <= 16, (overlap, t["ink_box"], nxt["ink_box"])


def test_ib_p925_stroke_fragment_does_not_set_top():
    regs, ie_by, s1, ink = _ib_fixture(925)
    t = _ib_target(regs, ie_by, 925, "right", "top", 2575)
    VR.apply_ink_box_page(regs, 925, s1, ink, STROKE_OK)
    assert [1724, 2575, 1726, 2617] in [e[:4] for e in t["ink_box_detail"]["excluded_stroke"]], t["ink_box_detail"]
    assert abs(t["ink_box"][1] - t["box"][1]) <= 5, (t["ink_box"], t["box"])


def test_ib_p127_stroke_fragment_does_not_set_top():
    regs, ie_by, s1, ink = _ib_fixture(127)
    t = _ib_target(regs, ie_by, 127, "right", "top", 4318)
    VR.apply_ink_box_page(regs, 127, s1, ink, STROKE_OK)
    assert [1618, 4318, 1621, 4363] in [e[:4] for e in t["ink_box_detail"]["excluded_stroke"]], t["ink_box_detail"]
    assert abs(t["ink_box"][1] - t["box"][1]) <= 5, (t["ink_box"], t["box"])


def test_ib_p197_box_byte_identical_with_exclusion_on():
    """B6: apply_ink_box_page never writes rect["box"] (deep comparison against the input)."""
    import copy
    regs, _, s1, ink = _ib_fixture(197)
    before = copy.deepcopy([[x["box"] for x in r["rects"]] for r in regs])
    VR.apply_ink_box_page(regs, 197, s1, ink, STROKE_OK)
    assert [[x["box"] for x in r["rects"]] for r in regs] == before
    VR.apply_ink_box_page(regs, 197, s1, ink, {"status": "abstain", "cutoff": None})
    assert [[x["box"] for x in r["rects"]] for r in regs] == before


B4_EXPECT = {
    "third": [79, 21, 21, 149, 1426, 13873, 47189, 30502, 5434, 997, 296, 105],
    "half": [47, 16, 14, 69, 923, 11624, 43614, 28798, 4656, 788, 246, 79],
    "abs20": [73, 20, 20, 121, 1331, 13736, 46871, 29990, 5152, 954, 292, 101],
}


def test_ib_b4_stroke_range_over_20_pages_slow():
    """B4 (slow): run-level derivation over the 20 rerun pages returns ok, F=1, L=7, cutoff 4.5 at
    every floor, and the floors' histograms (bins 1..12) equal the measured values."""
    pop = []
    for fp in IB_PAGES:
        ink = _ib_page_ink(fp)
        s1 = VR.analyze_page_s1(ink, _ib_page_geom(fp))
        pop.extend(VR.stroke_population_page(ink, s1))
    r = VR.derive_stroke_cutoff(VR.stroke_floors(pop))
    for name, rec in r["per_floor"].items():
        print(name, "F", rec["F"], "v", rec["v"], "L", rec["L"], "cutoff", rec["cutoff"], "hist[1:13]", rec["hist"][1:13])
    print("status", r["status"], "cutoff", r["cutoff"], "n_pop", len(pop))
    assert r["status"] == "ok" and r["cutoff"] == 4.5, r
    for name, rec in r["per_floor"].items():
        assert (rec["F"], rec["L"], rec["cutoff"]) == (1, 7, 4.5), (name, rec)
        assert rec["hist"][1:13] == B4_EXPECT[name], (name, rec["hist"][1:13], B4_EXPECT[name])


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
