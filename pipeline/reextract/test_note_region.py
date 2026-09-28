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
