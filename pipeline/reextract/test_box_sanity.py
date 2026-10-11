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

# ---- region layout invariants (synthetic) ----
def _rg(kind, fpf, head, rects):
    return {"kind": kind, "file_page_first": fpf, "head": head,
            "rects": [{"file_page": fp, "col": c, "box": [0, y0, 10, y1]} for fp, c, y0, y1 in rects]}

def _hd(col, y):
    return {"col": col, "box": [0, y, 10, y + 5]}

def _zero(res):
    return all(v == 0 for v in res["counts"].values())

def test_layout_clean_two_page_chain():
    regs = [_rg("verse", 1, _hd("left", 10), [(1, "left", 10, 100), (1, "right", 0, 100), (2, "left", 0, 40)]),
            _rg("verse", 2, _hd("left", 40), [(2, "left", 40, 100), (2, "right", 0, 100)])]
    assert _zero(B.check_layout(regs)), B.check_layout(regs)["counts"]

def test_layout_head_first_violation():
    regs = [_rg("verse", 1, _hd("left", 50), [(1, "left", 20, 100)])]
    r = B.check_layout(regs)
    assert r["counts"]["head_first"] == 1 and r["head_first"][0]["rect_y0s_on_head_col"] == [20]

def test_layout_overlap_same_col_and_touching():
    a = _rg("verse", 1, None, [(1, "left", 0, 50)])
    assert len(B.overlap_pairs([a, _rg("verse", 1, None, [(1, "left", 40, 90)])])) == 1
    assert B.overlap_pairs([a, _rg("verse", 1, None, [(1, "left", 50, 90)])]) == []

def test_layout_overlap_full_vs_right_page128_shape():
    a = _rg("chapter_intro", 128, None, [(128, "full", 2909, 2965)])
    b = _rg("verse", 128, None, [(128, "right", 721, 4476)])
    p = B.overlap_pairs([a, b])
    assert len(p) == 1 and p[0]["a_col"] == "full" and p[0]["b_col"] == "right"

def test_layout_rect_before_head():
    regs = [_rg("verse", 5, _hd("right", 1121), [(5, "right", 1121, 4000), (5, "left", 741, 4290)])]
    assert len(B.rect_before_head(regs)) == 1

def test_layout_tier_saves_page_745_shape():
    own = _rg("verse", 745, _hd("right", 2102), [(745, "right", 2102, 2475), (745, "left", 2602, 3591)])
    other = _rg("chapter_intro", 745, None, [(745, "full", 2476, 2601)])
    assert B.rect_before_head([own, other]) == []
    assert len(B.rect_before_head([own])) == 1

def test_layout_page_91_end_to_end():
    import verse_regions as VR
    from test_verse_regions import _band
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
    assert _zero(B.check_layout(regions)), B.check_layout(regions)["counts"]
    # the BUGGY shape as 26af210 produced it (Chris found it in the step-3 console, 2026-10-11):
    # Ver. 1 had nothing on 91; Ver. 2 got the top of both columns although its head is lower right.
    bad = [_rg("verse", 90, _hd("left", 30), [(90, "left", 30, 60), (90, "right", 10, 40)]),
           _rg("verse", 91, _hd("right", 50), [(91, "right", 10, 80), (91, "left", 10, 60)])]
    c = B.check_layout(bad)["counts"]
    # rect_before_head lists one entry per offending rect: (91,right,10) and (91,left,10) both precede the head
    assert c["head_first"] == 1 and c["rect_before_head"] == 2 and c["regions_violating"] == 1, c

EXPECTED_TESTS = 15


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed (EXPECTED {EXPECTED_TESTS})")
    if p + f != EXPECTED_TESTS:
        print(f"FAIL: ran {p + f} tests, expected {EXPECTED_TESTS}"); f += 1
    raise SystemExit(1 if f else 0)
