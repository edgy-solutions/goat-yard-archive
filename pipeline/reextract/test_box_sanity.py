"""box_sanity born tested — synthetic boxes against a known page geometry, covering each disposition
class Chris named (region membership, gutter/rule straddle, few-char fragment, page-flag). Run:
python test_box_sanity.py"""
import box_sanity as B

# a page like the probe pages: 3584x5400, footnote gutter ~1900, body/footnote rule ~4400, title top 3%
GEOM = {"W": 3584, "H": 5400, "gutter": 1900, "rule_y": 4400, "title_frac": 0.03}

def test_clean_boxes_ok():
    assert B.check_box((100, 500, 1700, 560), GEOM)[0] == "ok"      # body-left line
    assert B.check_box((2000, 500, 3400, 560), GEOM)[0] == "ok"     # body-right line
    assert B.check_box((100, 4600, 1700, 4660), GEOM)[0] == "ok"    # footnote line
    assert B.check_box((100, 500, 1700, 560), GEOM)[1] == "body-left"
    assert B.check_box((100, 4600, 1700, 4660), GEOM)[1] == "footnote"

def test_gutter_straddle_rejected():
    # a box crossing the column gutter (the old pipeline's center-cross smear) -> reject
    d, why = B.check_box((1500, 500, 2300, 560), GEOM)
    assert d == "reject" and "straddles" in why

def test_rule_straddle_rejected():
    # a box bleeding 100px from body into the footnote area (center in footnote) -> reject
    d, why = B.check_box((100, 4300, 1700, 4550), GEOM)
    assert d == "reject" and "straddles" in why

def test_fragment_rejected():
    # a few-char-wide box (statistical outlier) -> reject
    d, why = B.check_box((300, 500, 310, 560), GEOM)
    assert d == "reject" and "fragment" in why

def test_small_overshoot_clipped():
    # a body-left box poking ~50px past the rule (>tol 35, <=2*tol 70) -> clip to body-left
    d, region = B.check_box((100, 500, 1700, 4450), GEOM)
    assert d == "clip" and region == "body-left"

def test_within_tolerance_ok():
    # 15px past the region edge (<=tol) -> ok, not clip
    assert B.check_box((100, 500, 1915, 560), GEOM)[0] == "ok"

def test_page_flag_when_many_bad():
    boxes = [(100, 500, 1700, 560)] + [(1500, y, 2300, y + 60) for y in range(600, 1200, 100)]  # 1 ok + 6 straddles
    r = B.check_page(boxes, GEOM)
    assert r["page_flag"] and r["reason"] == "geometry-suspect"

def test_page_ok_when_mostly_clean():
    boxes = [(100, y, 1700, y + 60) for y in range(500, 1500, 100)]   # all clean body-left
    r = B.check_page(boxes, GEOM)
    assert not r["page_flag"] and r["bad"] == 0

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed"); raise SystemExit(1 if f else 0)
