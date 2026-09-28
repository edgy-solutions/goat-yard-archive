"""note_region born-tested — persisted paste origins (docs/audits/SPEC_presplit_paste_origins_20260927.md)
plus the legacy strip→native un-stacking (the multi-rect region rule), renamed to `strip_box_to_native`.
Verified visually on p138 (left-col red / right-col blue land in-column on the native page). Run:
C:/Users/cnogr/git/goat-yard-archive/.venv/Scripts/python.exe test_note_region.py"""
import sys
from pathlib import Path
import note_region as NR

# ---------------------------------------------------------------------------------------------------------
# Synthetic info with PERSISTED bands, shaped like the real p423 measurement (docs/audits/SPEC...md):
# rules (l, r) = 4515, 4524; xg = 1538; trimmed strip heights [183, 233]; true paste origins [0, 203].
RULE_L, RULE_R = 4515, 4524
XG = 1538
LEFT_H, RIGHT_H = 183, 233
RIGHT_PASTE = LEFT_H + 20  # 203 -- the TRUE right paste origin (left_trimmed_height + 20)
STRIP_W = 3000
PAGE_W, PAGE_H = 3584, 5400

INFO_BANDS = {
    "mode": "two_column", "rules": [RULE_L, RULE_R], "fn_gutter": [XG, 0.8],
    "page": [PAGE_W, PAGE_H], "upscale": 1,
    "bands": [
        {"band": 0, "col": "left", "paste": [0, 0], "size": [STRIP_W, LEFT_H], "native": [0, RULE_L + 6]},
        {"band": 1, "col": "right", "paste": [0, RIGHT_PASTE], "size": [STRIP_W, RIGHT_H],
         "native": [XG, RULE_R + 6]},
    ],
}

Y_TOP = 4200
INFO_FULL = {
    "mode": "full_width", "rules": [Y_TOP, None], "fn_gutter": [1900, 0.1],
    "page": [PAGE_W, PAGE_H], "upscale": 1,
    "bands": [{"band": 0, "col": "full_width", "paste": [0, 0], "size": [STRIP_W, 400],
               "native": [0, Y_TOP + 6]}],
}

# Same shape as INFO_BANDS but at upscale=2 -- paste/size stay PRE-upscale (canvas coords), per spec.
INFO_UP2 = {
    "mode": "two_column", "rules": [RULE_L, RULE_R], "fn_gutter": [XG, 0.8],
    "page": [PAGE_W, PAGE_H], "upscale": 2,
    "bands": [
        {"band": 0, "col": "left", "paste": [0, 0], "size": [STRIP_W, LEFT_H], "native": [0, RULE_L + 6]},
        {"band": 1, "col": "right", "paste": [0, RIGHT_PASTE], "size": [STRIP_W, RIGHT_H],
         "native": [XG, RULE_R + 6]},
    ],
}


def test_left_column_point_maps_to_rule_l_plus_6_plus_y():
    r = NR.strip_to_native(INFO_BANDS, 50, 30)
    assert r == {"x": 50, "y": RULE_L + 6 + 30, "col": "left", "band": 0}, r


def test_right_column_point_shifts_by_gutter_and_right_rule():
    y = RIGHT_PASTE + 10
    r = NR.strip_to_native(INFO_BANDS, 40, y)
    assert r == {"x": XG + 40, "y": RULE_R + 6 + 10, "col": "right", "band": 1}, r


def test_p423_regression_right_column_uses_203_not_35():
    """The defect this exists for. The OLD ink-band inference on p423 (module docstring / spec table)
    yielded THREE surviving bands after the `>10` filter -- (0,13) a sliver, (35,177) the true left column,
    (203,436) the true right column -- and `bands[1][0]` (=35) was taken as the right column's start
    instead of the true origin 203. Assert the NEW mapper uses 203, and assert that differs from the old
    35-based answer by exactly 168px (the measured p423 error), so this test names the defect, not just
    the fix."""
    y = 220  # a right-column strip y (post-upscale == pre since upscale 1)
    r = NR.strip_to_native(INFO_BANDS, 10, y)
    correct_native_y = RULE_R + 6 + (y - RIGHT_PASTE)
    assert r["y"] == correct_native_y, r

    old_ink_bands_p423 = [(0, 13), (35, 177), (203, 436)]  # 3 surviving bands, >10 filter, p423 shape
    old_buggy_right_start = old_ink_bands_p423[1][0]       # = 35 -- the off-by-one
    old_buggy_native_y = RULE_R + 6 + (y - old_buggy_right_start)
    assert abs(correct_native_y - old_buggy_native_y) == 168, (correct_native_y, old_buggy_native_y)


def test_y_in_gap_raises_naming_both_bands():
    y = LEFT_H + 5  # inside [183, 203) -- the 20px gap between band 0 and band 1
    try:
        NR.strip_to_native(INFO_BANDS, 10, y)
        assert False, "expected ValueError"
    except ValueError as e:
        msg = str(e)
        assert "band 0" in msg and "band 1" in msg, msg


def test_y_past_last_band_raises():
    y = RIGHT_PASTE + RIGHT_H + 5
    try:
        NR.strip_to_native(INFO_BANDS, 10, y)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "past the last band" in str(e), e


def test_x_past_page_width_raises_with_page_width_in_message():
    x = PAGE_W - XG + 50  # xg + x > PAGE_W
    y = RIGHT_PASTE + 10
    try:
        NR.strip_to_native(INFO_BANDS, x, y)
        assert False, "expected ValueError"
    except ValueError as e:
        assert str(PAGE_W) in str(e), e


def test_upscale_2_matches_upscale_1_native_y():
    y1 = RIGHT_PASTE                 # upscale=1: query at the band's own (pre-upscale) paste y
    y2 = 2 * RIGHT_PASTE             # upscale=2: the same physical point in post-upscale strip space
    r1 = NR.strip_to_native(INFO_BANDS, 10, y1)
    r2 = NR.strip_to_native(INFO_UP2, 10, y2)
    assert r1["y"] == r2["y"], (r1, r2)


def test_full_width_one_band_origin_y_top_plus_6():
    r = NR.strip_to_native(INFO_FULL, 100, 50)
    assert r == {"x": 100, "y": Y_TOP + 6 + 50, "col": "full_width", "band": 0}, r


def test_no_bands_key_returns_rects_native_false_no_raise():
    r = NR.strip_box_to_native([50, 30, 800, 70], INFO, BANDS)
    assert r, r
    assert all(rect.get("native") is False for rect in r), r


def test_column_bands_persisted_needs_no_strip():
    bands = NR.column_bands(INFO_BANDS)
    assert bands == [(0, LEFT_H), (RIGHT_PASTE, RIGHT_PASTE + RIGHT_H)], bands


def test_column_bands_no_bands_no_strip_raises():
    try:
        NR.column_bands({})
        assert False, "expected ValueError"
    except ValueError:
        pass


# ---------------------------------------------------------------------------------------------------------
# The existing four cases, renamed to the rectangle function `strip_box_to_native` (call sites only --
# nothing else about them changed). INFO/BANDS below deliberately have NO "bands" key, so these exercise
# the legacy inference fallback path.
INFO = {"mode": "two_column", "fn_gutter": [1881, 0.97], "rules": [4290, 4283]}
BANDS = [(0, 200), (220, 400)]  # left band [0,200], gap, right band [220,400]


def test_left_column_box_maps_below_left_rule():
    r = NR.strip_box_to_native([50, 30, 800, 70], INFO, BANDS)
    assert len(r) == 1 and r[0]["col"] == 0
    assert r[0]["box"] == [50, 4290 + 6 + 30, 800, 4290 + 6 + 70]   # native x unchanged, y past left rule


def test_right_column_box_shifts_by_gutter_and_right_rule():
    r = NR.strip_box_to_native([40, 240, 700, 290], INFO, BANDS)        # in the right band
    assert len(r) == 1 and r[0]["col"] == 1
    xg, rr, rstart = 1881, 4283, 220
    assert r[0]["box"] == [xg + 40, rr + 6 + (240 - rstart), xg + 700, rr + 6 + (290 - rstart)]


def test_stitched_box_becomes_two_rects_never_one_span():
    # a box straddling the 20px gap (a note stitched left-bottom -> right-top) -> TWO native rects
    r = NR.strip_box_to_native([30, 180, 900, 260], INFO, BANDS)
    assert len(r) == 2, r
    assert {x["col"] for x in r} == {0, 1}              # one rect per column, never a single spanning box


def test_full_width_is_one_rect():
    r = NR.strip_box_to_native([0, 10, 1900, 80], {"mode": "full_width", "rules": [4500, None],
                               "fn_gutter": [1900, 0.1]}, [(0, 100)])
    assert len(r) == 1 and r[0]["col"] == 0


# ---------------------------------------------------------------------------------------------------------
# Real-page tests -- guarded by a skip when the private image repo is absent.
IMG_DIR = Path("c:/Users/cnogr/git/dr-voluminous/commentary/volume1")


def _presplit_real(page):
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    import cv_footnote_presplit as ps
    return ps.presplit(str(IMG_DIR / f"page{page}_image1.png"), upscale=1)


def test_real_p423_p726_persisted_bands():
    if not IMG_DIR.exists():
        _skip("no dr-voluminous checkout")
    strip423, info423 = _presplit_real(423)
    strip726, info726 = _presplit_real(726)
    assert [b["paste"][1] for b in info423["bands"]] == [0, 203], info423["bands"]
    assert [b["paste"][1] for b in info726["bands"]] == [0, 208], info726["bands"]
    assert [b["native"][1] for b in info423["bands"]] == [4521, 4530], info423["bands"]
    assert [b["native"][1] for b in info726["bands"]] == [4514, 4495], info726["bands"]


def test_real_p423_native_y_168px_below_old_code():
    if not IMG_DIR.exists():
        _skip("no dr-voluminous checkout")
    strip, info = _presplit_real(423)
    right_band = info["bands"][-1]
    rule_r = info["rules"][1]
    y = right_band["paste"][1] + 10  # a point in the right band
    r = NR.strip_to_native(info, 5, y)
    assert rule_r + 6 <= r["y"] <= rule_r + 6 + right_band["size"][1], r

    # what the PRE-CHANGE code returned for the same strip point: ink-band inference, `bands[1][0]`.
    old_bands = [b for b in NR._column_bands(strip) if b[1] - b[0] > 10]
    old_right_start = old_bands[1][0]
    old_native_y = rule_r + 6 + (y - old_right_start)
    assert old_native_y - r["y"] == 168, (r["y"], old_native_y)


def test_persisted_rects_are_flagged_native_and_carry_both_col_forms():
    """A rect off the persisted path must SAY it is native, and must keep the int `col` its consumers
    index on while also carrying the persisted name. The fallback path flags native False; if the good
    path says nothing, "native" is being read from the absence of a key."""
    rects = NR.strip_box_to_native([0, RIGHT_PASTE + 5, 100, RIGHT_PASTE + 40], INFO_BANDS)
    assert len(rects) == 1, rects
    r = rects[0]
    assert r["native"] is True, r
    assert r["col"] == 1 and isinstance(r["col"], int), r
    assert r["col_name"] == "right", r


def test_point_col_is_a_name_while_box_col_is_an_index():
    """The deliberate asymmetry, pinned so nobody "fixes" one to match the other by accident."""
    pt = NR.strip_to_native(INFO_BANDS, 10, RIGHT_PASTE + 10)
    bx = NR.strip_box_to_native([0, RIGHT_PASTE + 5, 100, RIGHT_PASTE + 40], INFO_BANDS)[0]
    assert pt["col"] == "right" and isinstance(pt["col"], str), pt
    assert bx["col"] == 1 and isinstance(bx["col"], int), bx


class _Skip(Exception):
    """Raised by a test that cannot run. A SKIP is reported as a SKIP and counted apart from PASS.
    The real-page tests here returned early when dr-voluminous was absent, and an early return made
    the runner score them as passes: with IMG_DIR pointed at a nonexistent path this file printed
    "17 passed, 0 failed" while two of its assertions never ran. A suite that passes on nothing is
    not evidence of anything."""


def _skip(why):
    raise _Skip(why)



# ---------------------------------------------------------------------------------------------------------
# The canvas-padding fault, measured on the real pages. cv_footnote_presplit pastes each band at canvas
# x=0 into a canvas as wide as the WIDEST band, so the narrower band has white filler beside it that is
# not part of any column. These are the six A1 note boxes Lane B reported as "clamped past the page edge"
# (dr-voluminous reextract_vol1/audits/recut_report_20260927.md); the geometry here is what
# cv_footnote_presplit.presplit() actually returns for each page, read off the scans, not invented.
#
#     page   left_w  right_w  canvas(native)  narrow band  reported native x1
SIX_CLAMPED = [
    # page, left_w, right_w, narrow_col, reported_native_x1
    (124, 1801, 1783, "right", 3600),
    (200, 1910, 1674, "right", 3818),
    (900, 1841, 1743, "right", 3680),
    (596, 1923, 1661, "right", 3844),
    (726, 1960, 1624, "right", 3918),
    # p217 is the mirror case: on this page the LEFT column is the narrow one, so the identical fault
    # lands at native 1955 -- INSIDE the 3584px page, where the page-width check cannot see it.
    (217, 1625, 1959, "left", 1955),
]
UP = 2  # presplit(upscale=2) -- paste/size stay pre-upscale, strip x is post-upscale


def _six_info(left_w, right_w):
    """info as presplit persists it: band native x = 0 and left_w, band size = its OWN width."""
    return {"mode": "two_column", "page": [PAGE_W, PAGE_H], "upscale": UP,
            "bands": [
                {"band": 0, "col": "left", "paste": [0, 0], "size": [left_w, 188],
                 "native": [0, 4514]},
                {"band": 1, "col": "right", "paste": [0, 208], "size": [right_w, 206],
                 "native": [left_w, 4495]},
            ]}


def _full_canvas_box(left_w, right_w, narrow_col, reported_x1):
    """The strip box the detector produced: it runs to the padded canvas edge, not the band edge."""
    info = _six_info(left_w, right_w)
    b = info["bands"][0 if narrow_col == "left" else 1]
    x1 = (reported_x1 - b["native"][0]) * UP     # derive strip x from the value Lane B reported
    y = b["paste"][1] * UP + 10
    return info, b, [0, y, x1, y + 40]


def test_all_six_clamped_boxes_now_CLIP_to_the_band_edge_and_say_so():
    # Chris, 2026-09-27: "clip to band width and flag edge:band-clipped; a note cannot extend past its
    # band." Before the ruling these six raised. The diagnosis did not change -- the branch did.
    for page, lw, rw, col, rx1 in SIX_CLAMPED:
        info, b, box = _full_canvas_box(lw, rw, col, rx1)
        rects = NR.strip_box_to_native(box, info)
        assert len(rects) == 1, (page, rects)
        r = rects[0]
        band_w = b["size"][0]
        assert r["box"][2] == b["native"][0] + band_w, (page, r)
        assert "band-clipped" in r.get("edge", []), (page, r)
        # the overshoot it lost, so an audit can still see how far into the filler the box ran
        assert r["band_overshoot_px"] == round(rx1 - (b["native"][0] + band_w), 1), (page, r)
        # and the clip is exact, not approximate: nothing is left hanging over the band
        assert r["box"][2] - b["native"][0] == band_w, (page, r)


def test_the_five_right_column_clips_land_exactly_on_the_page_edge():
    # The measured coincidence the ruling rests on: for a right-column band, native[0] + size[0] IS the
    # page width, so clipping a right-column overrun puts the note flush with the outer page edge.
    # Stated separately because it is NOT true of the left-column cases, and reading it as a general
    # property is how a page-width clip would get written next time.
    for page, lw, rw, col, rx1 in SIX_CLAMPED:
        if col != "right":
            continue
        info, b, box = _full_canvas_box(lw, rw, col, rx1)
        r = NR.strip_box_to_native(box, info)[0]
        assert r["box"][2] == PAGE_W == lw + rw, (page, r, lw, rw)


def test_p217_is_the_case_the_page_width_check_CANNOT_see():
    # The companion assertion, and the reason this gate exists at all. On p217 the narrow band is the
    # LEFT one, so the padding overrun maps to native 1955 -- 1629px INSIDE the page. A page-width check
    # passes it silently and the box is wrongly widened; only the band-width check sees it. Without this
    # test the gate could be a restatement of the old one and nobody would know.
    page, lw, rw, col, rx1 = SIX_CLAMPED[-1]
    assert page == 217 and col == "left"
    info, b, box = _full_canvas_box(lw, rw, col, rx1)
    nx1 = b["native"][0] + box[2] / UP
    assert nx1 == rx1 == 1955
    assert nx1 < PAGE_W, "if this ever exceeds PAGE_W the test has stopped testing the silent case"
    r = NR.strip_box_to_native(box, info)[0]
    assert r["box"][2] == 1625, r          # the left band's own width, not the page width
    assert r["box"][2] < PAGE_W, r
    assert "band-clipped" in r["edge"], r


def test_p217_trips_BOTH_flags_because_its_real_box_starts_at_minus_2():
    # The real recut fault string is out-of-strip:box=[-2, 109, 1955, 213]_beyond=left2, so this box runs
    # off BOTH ends: 2px of detector slop on the left, filler on the right. Two causes, two flags, one
    # rect -- which is why `edge` is a list. A scalar field would have to discard one of them.
    page, lw, rw, col, rx1 = SIX_CLAMPED[-1]
    info, b, box = _full_canvas_box(lw, rw, col, rx1)
    box[0] = -2
    r = NR.strip_box_to_native(box, info)[0]
    assert r["edge"] == ["band-clipped", "canvas-slop-clamped"], r
    assert r["box"][0] == 0, r             # clamped to the band origin, not mapped to native -1
    assert r["box"][2] == 1625, r


def test_a_negative_x0_deeper_than_the_measured_slop_is_refused():
    # The other direction of the slop clamp. 2px is the detector slack that was actually measured; a box
    # starting 40px left of its band is not slop, it is the wrong band, and clamping it would silently
    # move a note across a column boundary. Without this test the clamp would accept any negative x.
    info = _six_info(1625, 1959)
    b = info["bands"][1]
    y = b["paste"][1] * UP + 10
    try:
        NR.strip_box_to_native([-80, y, 400, y + 40], info)
        assert False, "expected ValueError: 40px left of the band is not edge slop"
    except ValueError as e:
        assert "not edge slop" in str(e), e


def test_a_box_starting_past_the_band_edge_is_still_REFUSED():
    # The companion assertion for the whole clip branch: clipping must not have become "always
    # succeed". A box whose LEFT edge is already in the filler has no pre-image to clip back to, and
    # emitting a zero-width rect at the band edge would be an invented region, not a repair.
    info = _six_info(1960, 1624)
    b = info["bands"][1]
    y = b["paste"][1] * UP + 10
    x0 = (b["size"][0] + 50) * UP
    try:
        NR.strip_box_to_native([x0, y, x0 + 200, y + 40], info)
        assert False, "expected ValueError: box lies wholly in the canvas filler"
    except ValueError as e:
        m = str(e)
        assert "WHOLLY in white filler" in m, m
        assert "nothing to clip it to" in m, m


def test_lane_b_three_UNFAULTED_left_column_overshoots_clip_to_the_band_edge():
    # Lane B's manifest sweep (apparatus-next 2576bb4) found three boxes over filler with no fault
    # recorded at all, so they had been emitting crops the whole time: FILE pages 219:n0 +450px,
    # 293:n0 +442px, 895:n0 +300px, all left-column. Their band widths are not in my measurements, so
    # the geometry here is synthetic and only the OVERSHOOTS are Lane B's -- what this pins is the
    # arithmetic at those magnitudes, not those pages' layouts.
    for page, band_w, overshoot in ((219, 1600, 450), (293, 1610, 442), (895, 1700, 300)):
        info = _six_info(band_w, PAGE_W - band_w)
        b = info["bands"][0]
        y = b["paste"][1] * UP + 10
        r = NR.strip_box_to_native([0, y, (band_w + overshoot) * UP, y + 40], info)[0]
        assert r["box"][2] == band_w, (page, r)
        assert r["band_overshoot_px"] == float(overshoot), (page, r)
        assert r["edge"] == ["band-clipped"], (page, r)


def test_an_untouched_rect_carries_NO_edge_key_at_all():
    # Absence is the signal downstream: a rect that needed no clipping must be byte-identical to what it
    # was before this gate existed, or every consumer has to learn to ignore an empty flag list.
    info = _six_info(1960, 1624)
    b = info["bands"][1]
    y = b["paste"][1] * UP + 10
    r = NR.strip_box_to_native([10, y, 200, y + 40], info)[0]
    assert "edge" not in r, r
    assert "band_overshoot_px" not in r, r


def test_a_box_inside_the_narrow_band_still_maps_unchanged():
    # p726:n3 A2_spanbox, the real recut output: native x 2112..2347 in the right column. The new gate
    # must not touch a box that is genuinely inside its band.
    info = _six_info(1960, 1624)
    b = info["bands"][1]
    x0 = (2112 - b["native"][0]) * UP
    x1 = (2347 - b["native"][0]) * UP
    y = b["paste"][1] * UP + 10
    rects = NR.strip_box_to_native([x0, y, x1, y + 40], info)
    assert len(rects) == 1, rects
    assert rects[0]["box"][0] == 2112 and rects[0]["box"][2] == 2347, rects
    assert rects[0]["col_name"] == "right"


def test_a_box_ending_exactly_on_the_band_edge_is_allowed():
    # The other direction: the gate must not reject the legal boundary. A note that fills its column to
    # the outer edge maps to native 1960+1624 = 3584 = the page edge, which is correct, not an error.
    info = _six_info(1960, 1624)
    b = info["bands"][1]
    y = b["paste"][1] * UP + 10
    rects = NR.strip_box_to_native([0, y, b["size"][0] * UP, y + 40], info)
    assert rects[0]["box"][2] == 1960 + 1624 == PAGE_W, rects


def test_the_point_mapper_still_REFUSES_and_does_not_clip():
    # A point is not a region. Chris's ruling is about note boxes -- "a note cannot extend past its
    # band" -- and clipping a single point would silently relocate it to the band edge and report that
    # as its position. Nothing has ruled on points, so the point mapper keeps refusing.
    info = _six_info(1960, 1624)
    b = info["bands"][1]
    y = b["paste"][1] * UP + 10
    ok = NR.strip_to_native(info, b["size"][0] * UP, y)
    assert ok["x"] == PAGE_W, ok
    try:
        NR.strip_to_native(info, b["size"][0] * UP + 2, y)
        assert False, "expected ValueError one px past the band edge"
    except ValueError as e:
        assert "past the right edge of band" in str(e), e


def test_the_gate_is_silent_when_size_is_missing():
    # Older info without per-band size must keep working -- the check abstains rather than inventing a
    # width, and the page-width check remains the only gate for those.
    info = _six_info(1960, 1624)
    del info["bands"][1]["size"]
    try:
        NR.strip_to_native(info, 10, 300)
    except ValueError as e:
        assert "past the right edge" not in str(e), e

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = s = 0
    for fn in fns:
        try:
            fn(); p += 1; print(f"  PASS {fn.__name__}")
        except _Skip as e:
            s += 1; print(f"  SKIP {fn.__name__}  ({e})")
        except Exception:
            f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed, {s} skipped")
    if s:
        print("  A SKIP is not a PASS. Those assertions did not run.")
    raise SystemExit(1 if f else 0)
