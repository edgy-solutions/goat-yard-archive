"""note_region born-tested — the strip→native un-stacking (the multi-rect region rule). Verified visually on
p138 (left-col red / right-col blue land in-column on the native page). Run: python test_note_region.py"""
import note_region as NR

# a two-column page: left strip pasted at y0, right strip after the 20px gap at strip-y 220
INFO = {"mode": "two_column", "fn_gutter": [1881, 0.97], "rules": [4290, 4283]}
BANDS = [(0, 200), (220, 400)]                          # left band [0,200], gap, right band [220,400]

def test_left_column_box_maps_below_left_rule():
    r = NR.strip_to_native([50, 30, 800, 70], INFO, BANDS)
    assert len(r) == 1 and r[0]["col"] == 0
    assert r[0]["box"] == [50, 4290 + 6 + 30, 800, 4290 + 6 + 70]   # native x unchanged, y past left rule

def test_right_column_box_shifts_by_gutter_and_right_rule():
    r = NR.strip_to_native([40, 240, 700, 290], INFO, BANDS)        # in the right band
    assert len(r) == 1 and r[0]["col"] == 1
    xg, rr, rstart = 1881, 4283, 220
    assert r[0]["box"] == [xg + 40, rr + 6 + (240 - rstart), xg + 700, rr + 6 + (290 - rstart)]

def test_stitched_box_becomes_two_rects_never_one_span():
    # a box straddling the 20px gap (a note stitched left-bottom -> right-top) -> TWO native rects
    r = NR.strip_to_native([30, 180, 900, 260], INFO, BANDS)
    assert len(r) == 2, r
    assert {x["col"] for x in r} == {0, 1}              # one rect per column, never a single spanning box

def test_full_width_is_one_rect():
    r = NR.strip_to_native([0, 10, 1900, 80], {"mode": "full_width", "rules": [4500, None], "fn_gutter": [1900, 0.1]}, [(0, 100)])
    assert len(r) == 1 and r[0]["col"] == 0

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed"); raise SystemExit(1 if f else 0)
