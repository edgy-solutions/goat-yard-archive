"""body_bottom born-tests: synthetic arrays, a synthetic temp-dir volume for derive, and (skipped when
the data is absent) real pages 128 and 923 for the pure functions. No network, no model.
Run: python test_body_bottom.py

EXPECTED_TESTS asserts the suite's OWN test count so a silently-dropped test fails the run.
"""
import json
import shutil
import tempfile
from pathlib import Path

import numpy as np

import body_bottom as BB

EXPECTED_TESTS = 29

DV = Path("C:/Users/cnogr/git/dr-voluminous-a2run")
GEOM = DV / "body_shadow_vol1/geometry/volume1_page_geometry.jsonl"
VOL1 = DV / "commentary/volume1"
LOCK = {"T": 175, "WIN": 39, "T_O": 0.20, "T_W": 0.525}


# ---- row_max_runs ----------------------------------------------------------

def test_row_max_runs_longest_run_per_row():
    m = np.zeros((4, 12), bool)
    m[0, 2:5] = True; m[0, 7:12] = True          # runs 3 and 5 -> 5
    m[1, :] = True                                # whole row -> 12
    m[3, 0] = True                                # edge single -> 1
    r = BB.row_max_runs(m)
    assert r.dtype == np.int64 and r.tolist() == [5, 12, 0, 1]


def test_row_max_runs_empty_mask():
    assert BB.row_max_runs(np.zeros((3, 5), bool)).tolist() == [0, 0, 0]


# ---- col_bounds ------------------------------------------------------------

def test_col_bounds_are_presplits():
    b = BB.col_bounds(3584, 1970)
    assert b == {"left": (107, 1970 - 71), "right": (1970 + 71, 3584 - 107)}


def test_col_bounds_match_presplit_source():
    import inspect
    import cv_footnote_presplit as ps
    src = inspect.getsource(ps.presplit)
    assert "find_hrule(dark, int(W*0.03), xdiv-int(W*0.02))" in src
    assert "find_hrule(dark, xdiv+int(W*0.02), W-int(W*0.03))" in src


# ---- two_modes -------------------------------------------------------------

def test_two_modes_midpoint_of_the_two_most_populated():
    vals = [5] * 6 + [25] * 3 + [15] * 1                  # width 10: bins 0 (6), 1 (1), 2 (3)
    t, hist, modes = BB.two_modes(vals, 10)
    assert hist[:3] == [6, 1, 3] and modes == [0, 2] and t == 15.0


def test_two_modes_min_separation_boundary_is_inclusive():
    vals = [0.5] * 5 + [3.5] * 3                          # bins 0 and 3, width 1: distance exactly 3
    assert BB.two_modes(vals, 1, min_sep=3)[0] is not None
    assert BB.two_modes(vals, 1, min_sep=4)[0] is None


def test_two_modes_default_min_sep_is_two_widths():
    vals = [0.5] * 5 + [1.5] * 0 + [2.5] * 3              # bins 0 and 2: distance 2 widths
    t, _h, modes = BB.two_modes(vals, 1)
    assert modes == [0, 2] and t == 1.5
    assert BB.two_modes([0.5] * 5 + [1.5] * 3, 1)[0] is None   # adjacent bins never two modes


def test_two_modes_empty_bin_is_never_a_mode():
    t, hist, modes = BB.two_modes([5.0] * 4, 10)
    assert t is None and modes is None and 0 in hist
    assert BB.two_modes([], 10) == (None, [], None)


def test_two_modes_tie_goes_to_lower_index_and_plateau_edge():
    vals = [0.5] * 4 + [5.5] * 4                           # equal counts: m1 is the lower index
    t, _h, modes = BB.two_modes(vals, 1)
    assert modes == [0, 5] and t == 3.0
    # a plateau: count >= left and > right, so only its right end qualifies
    h = BB.two_modes([0.5] * 3 + [1.5] * 3 + [8.5] * 2, 1)[1]
    assert h[0] == 3 and h[1] == 3


def test_two_modes_lo_offsets_the_bins():
    t, _h, modes = BB.two_modes([10.5] * 3 + [20.5] * 2, 1, lo=10.0)
    assert modes == [0, 10] and t == 15.5


# ---- seeded_rule -----------------------------------------------------------

def test_seeded_rule_topmost_in_window():
    runs = np.zeros(100, np.int64)
    runs[40] = 300; runs[45] = 400; runs[60] = 500
    assert BB.seeded_rule(runs, 50, 10, 200) == 40       # topmost, not the longest, not the last
    assert BB.seeded_rule(runs, 50, 4, 200) is None       # 45 is outside [46, 54]
    assert BB.seeded_rule(runs, 50, 5, 200) == 45


def test_seeded_rule_is_strict_and_windowed_and_clipped():
    runs = np.zeros(50, np.int64)
    runs[30] = 200
    assert BB.seeded_rule(runs, 30, 5, 200) is None      # run > T, not >=
    runs[30] = 201
    assert BB.seeded_rule(runs, 40, 9, 200) is None      # 30 is outside [31, 49]
    assert BB.seeded_rule(runs, 40, 10, 200) == 30
    runs[0] = 999
    assert BB.seeded_rule(runs, 3, 10, 200) == 0         # window clipped at 0
    runs[:] = 0; runs[49] = 999
    assert BB.seeded_rule(runs, 47, 10, 200) == 49       # clipped at H-1


# ---- paired_rule -----------------------------------------------------------

def _runs(H, **rows):
    r = np.zeros(H, np.int64)
    for y, v in rows.items():
        r[int(y[1:])] = v
    return r


def test_paired_rule_min_of_the_paired_rows():
    H = 1000
    l = _runs(H, y600=300, y640=300, y900=300)
    r = _runs(H, y610=300, y650=300)
    pair, why = BB.paired_rule(l, r, H, 15, 200)
    assert why == "paired" and pair == (600, 610)       # 640/650 also pair but 600/610 is higher
    assert BB.paired_rule(l, r, H, 5, 200) == (None, "unpaired_candidate")   # 10 px apart: no pair at WIN 5


def test_paired_rule_unpaired_and_none_reasons():
    H = 1000
    l = _runs(H, y600=300)
    r = _runs(H, y700=300)
    assert BB.paired_rule(l, r, H, 50, 200) == (None, "unpaired_candidate")
    assert BB.paired_rule(l, np.zeros(H, np.int64), H, 50, 200) == (None, "unpaired_candidate")
    assert BB.paired_rule(np.zeros(H, np.int64), np.zeros(H, np.int64), H, 50, 200) == (None, "no_candidate")


def test_paired_rule_band_starts_at_045H_and_threshold_is_strict():
    H = 1000
    l = _runs(H, y440=300, y500=200)                     # 440 < 450 excluded; 500 is run == T
    r = _runs(H, y440=300, y500=200)
    assert BB.paired_rule(l, r, H, 50, 200) == (None, "no_candidate")
    l[450] = 201; r[450] = 201
    assert BB.paired_rule(l, r, H, 0, 200) == ((450, 450), "paired")


# ---- column_lines / foot_strip --------------------------------------------

def _gray_lines(H=400, W=300, rows=(), x=(10, 290)):
    g = np.full((H, W), 255, np.uint8)
    for y0, y1, xa, xb in rows:
        g[y0:y1, xa:xb] = 0
    return g


def test_column_lines_ink_extents_offset_by_x0():
    g = _gray_lines(rows=[(20, 32, 60, 200), (60, 72, 70, 150)])
    got = BB.column_lines(g, 50, 280)
    assert len(got) == 2
    assert got[0][2:] == [60, 200] and got[1][2:] == [70, 150]   # absolute x, exclusive end
    assert got[0][0] <= 20 and got[0][1] >= 32 and got[1][0] <= 60


def test_column_lines_ignores_ink_outside_the_column():
    g = _gray_lines(rows=[(20, 32, 5, 40)])
    assert BB.column_lines(g, 100, 280) == []


def _L(*specs):
    """(y0, y1, ink_x0, ink_x1) rows spaced 30 px apart."""
    return [[30 * i, 30 * i + 12, a, b] for i, (a, b) in enumerate(specs)]


def test_foot_strip_strips_indented_narrow_tail_and_places_the_cut_in_the_gap():
    lines = _L((100, 900), (100, 900), (100, 900), (100, 900), (400, 480))   # colw 1000
    n, y1, bands = BB.foot_strip(lines, 1000, 0.20, 0.525)
    assert n == 1 and bands == [lines[-1]]
    assert y1 == (lines[3][1] + lines[4][0]) // 2


def test_foot_strip_stops_at_first_failing_line_and_needs_both_conditions():
    full = (100, 900)
    lines = _L(full, full, full, (400, 480), full, (400, 480))               # a wide line breaks the walk
    assert BB.foot_strip(lines, 1000, 0.20, 0.525)[0] == 1
    assert BB.foot_strip(_L(full, full, full, (400, 960)), 1000, 0.20, 0.525)[0] == 0   # indented but wide
    assert BB.foot_strip(_L(full, full, full, (100, 160)), 1000, 0.20, 0.525)[0] == 0   # narrow but flush
    two = _L(full, full, full, (400, 480), (400, 480))
    assert BB.foot_strip(two, 1000, 0.20, 0.525)[0] == 2


def test_foot_strip_needs_four_lines_and_keeps_one():
    assert BB.foot_strip(_L((100, 900), (100, 900), (400, 480)), 1000, 0.2, 0.5) == (0, None, [])
    tail = _L((400, 480), (400, 480), (400, 480), (400, 480))
    n, y1, bands = BB.foot_strip(tail, 1000, 0.0, 0.5)
    assert n == 3 and len(bands) == 3 and y1 == (tail[0][1] + tail[1][0]) // 2    # never strips every line


# ---- clamp_rect / load_bottoms --------------------------------------------

BOT = {(5, "left"): 1000, (5, "right"): 900}


def test_clamp_rect_column_full_and_wholly_below():
    nb, info = BB.clamp_rect([0, 100, 500, 1200], "left", 5, BOT)
    assert nb == [0, 100, 500, 1000] and info == {"limit": 1000, "clamped": True}
    nb, info = BB.clamp_rect([0, 100, 500, 800], "left", 5, BOT)
    assert nb == [0, 100, 500, 800] and info == {"limit": 1000, "clamped": False}
    nb, info = BB.clamp_rect([0, 100, 1000, 1200], "full", 5, BOT)
    assert nb == [0, 100, 1000, 900] and info["limit"] == 900          # the SMALLER column bottom
    nb, info = BB.clamp_rect([0, 950, 500, 1200], "right", 5, BOT)
    assert nb is None and info == {"limit": 900, "clamped": True}
    assert BB.clamp_rect([0, 900, 500, 1200], "right", 5, BOT)[0] is None   # new_y1 == y0 is wholly below


def _bottoms_file(d, pages=(5,), error=None, header=True):
    p = Path(d) / "bb.jsonl"
    recs = [{"kind": "run_header", "config_hash": "cafe"}] if header else []
    for fp in pages:
        r = {"file_page": fp, "body_regions": [{"col": "left", "box": [0, 0, 10, 1000]},
                                               {"col": "right", "box": [10, 0, 20, 900]}]}
        if error:
            r["error"] = error
        recs.append(r)
    p.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    return p


def test_load_bottoms_reads_y1_and_refuses():
    d = tempfile.mkdtemp()
    try:
        b, sha, ch = BB.load_bottoms(_bottoms_file(d), [5])
        assert b == {(5, "left"): 1000, (5, "right"): 900} and len(sha) == 64 and ch == "cafe"
        for kw, pages in (({"header": False}, [5]), ({}, [5, 6]), ({"error": "boom"}, [5])):
            try:
                BB.load_bottoms(_bottoms_file(d, **kw), pages)
            except BB.Refused:
                continue
            raise AssertionError(f"no refusal for {kw} {pages}")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ---- derive on a synthetic volume -----------------------------------------

def _segments(g, y, xa, xb, thick=12, seg=60, gap=10):
    x = xa
    while x + seg <= xb:
        g[y:y + thick, x:x + seg] = 0
        x += seg + gap


def _page(W=1000, H=2000, text_from=300, text_to=1400, rules=(None, None), long_rows=()):
    g = np.full((H, W), 255, np.uint8)
    for y in range(text_from, text_to, 24):
        _segments(g, y, 30, 480)
        _segments(g, y, 520, 970)
    for y, (xa, xb) in zip(rules, ((30, 480), (520, 970))):
        if y is not None:
            g[y:y + 3, xa:xb] = 0
    for y, xa, xb in long_rows:
        g[y:y + 3, xa:xb] = 0
    return g


def _foot_page():
    """both columns unruled; body lines to y 1700, then a short indented tail line."""
    g = np.full((2000, 1000), 255, np.uint8)
    for xa, xb in ((30, 480), (520, 970)):
        for y in range(300, 1700, 24):
            _segments(g, y, xa, xb)
        g[1760:1772, xa + 180:xa + 225] = 0
    return g


def _geom(fp, g, rules, sources, name=None):
    H, W = g.shape
    xdiv = 500
    return {"volume": 1, "file_page": fp, "image": name or f"page{fp}_image1.png", "page": [W, H],
            "xdiv": xdiv, "rules": list(rules), "mode": "two_column", "fn_gutter": [490, 0.7],
            "body_regions": [
                {"col": "left", "box": [0, 0, xdiv, H], "rule_y": rules[0], "y1_source": sources[0]},
                {"col": "right", "box": [xdiv, 0, W, H], "rule_y": rules[1], "y1_source": sources[1]}],
            "tier": "best_effort", "flags": ["x"], "config": {"presplit": {"hash": "h"}}}


def _volume(d):
    from PIL import Image
    pages = {}
    spec = [(1, _page(rules=(1500, 1520)), (1500, 1520), ("rule", "rule")),
            (2, _page(rules=(1500, 1510)), (1500, 1510), ("rule", "rule")),
            (3, _page(rules=(1500, 1500)), (1500, 1500), ("rule", "rule")),
            (4, _page(rules=(None, 1500), long_rows=[(1505, 30, 480)]), (None, 1500),
             ("page_bottom_no_rule", "rule")),
            (5, _foot_page(), (None, None), ("page_bottom_no_rule", "page_bottom_no_rule")),
            (6, _page(W=800, rules=(1500, 1500)), (None, None), ("page_bottom_no_rule", "page_bottom_no_rule")),
            (7, _page(long_rows=[(1500, 30, 480), (1520, 520, 970)]), (None, None),
             ("page_bottom_no_rule", "page_bottom_no_rule"))]
    geoms = []
    for fp, g, rules, src in spec:
        Image.fromarray(g).save(Path(d) / f"page{fp}_image1.png")
        geoms.append(_geom(fp, g, rules, src))
    geoms[5]["xdiv"] = 400
    gp = Path(d) / "geom.jsonl"
    gp.write_text("".join(json.dumps(x) + "\n" for x in geoms), encoding="utf-8")
    return gp, geoms


def test_derive_synthetic_volume_end_to_end():
    d = tempfile.mkdtemp()
    try:
        gp, geoms = _volume(d)
        out = Path(d) / "sub" / "bb.jsonl"
        assert BB.main(["derive", "--geometry", str(gp), "--volume-dir", d,
                        "--pages", "1", "2", "3", "4", "5", "6", "7", "--out", str(out)]) == 0
        recs = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
        h, pages, s = recs[0], recs[1:-1], recs[-1]
        assert h["kind"] == "run_header" and h["tier"] == "best_effort" and h["config_hash"]
        c = h["config"]
        assert c["modal_size"] == [1000, 2000] and c["WIN"] == 20 and 150 < c["T"] < 450
        assert 0.1 < c["T_O"] < 0.3 and 0.2 < c["T_W"] < 0.9 and c["geometry_sha256"] and c["module_sha256"]
        assert "git_dirty" in c and "git_head" in c and set(c["histograms"]) == {"T", "T_O", "T_W"}
        assert [p["file_page"] for p in pages] == [1, 2, 3, 4, 5, 6, 7] and s["kind"] == "run_summary"
        # every original field of every region is untouched except box[3] / y1_source
        for g, p in zip(geoms, pages):
            for k, v in g.items():
                if k != "body_regions":
                    assert p[k] == v, k
            assert p["config_hash"] == h["config_hash"]
            for gb, pb in zip(g["body_regions"], p["body_regions"]):
                assert pb["rule_y"] == gb["rule_y"] and pb["col"] == gb["col"]
                assert pb["y1_prior"] == gb["box"][3] and pb["y1_source_prior"] == gb["y1_source"]
                assert pb["box"][:3] == gb["box"][:3]
        by = {p["file_page"]: p for p in pages}
        assert by[1]["body_regions"][0]["body_bottom"] == {"method": "rule"} and by[1]["body_bottom_flags"] == []
        assert by[1]["body_regions"][0]["box"][3] == 2000
        l4 = by[4]["body_regions"][0]                                  # seeded from the other column's rule
        assert l4["y1_source"] == "rule_seeded" and l4["box"][3] == 1505 and l4["body_bottom"]["seed"] == 1500
        assert l4["body_bottom"]["window"] == 20 and l4["body_bottom"]["run"] == 450
        l7, r7 = by[7]["body_regions"]                                 # neither ruled: a pair, within WIN
        assert (l7["y1_source"], r7["y1_source"]) == ("rule_paired", "rule_paired")
        assert (l7["box"][3], r7["box"][3]) == (1500, 1520)
        l5 = by[5]["body_regions"][0]                                  # no rule, foot furniture stripped
        assert l5["y1_source"] == "foot_furniture_excluded" and 1700 < l5["box"][3] < 1760
        assert l5["body_bottom"]["reason"] == "no_candidate" and len(l5["body_bottom"]["stripped_bands"]) == 1
        assert by[5]["body_bottom_flags"] == ["body_bottom_abstained"]
        off = by[6]
        assert off["body_bottom_flags"] == ["page_size_off_mode"]
        assert [b["box"][3] for b in off["body_regions"]] == [b["box"][3] for b in geoms[5]["body_regions"]]
        assert [b["y1_source"] for b in off["body_regions"]] == ["page_bottom_no_rule"] * 2
        assert s["counts"]["rule_seeded"] == 1 and s["counts"]["rule_paired"] == 2
        assert s["counts"]["foot_furniture_excluded"] == 2 and s["counts"]["page_size_off_mode"] == 1
        assert s["counts"]["abstained:no_candidate"] == 2
        assert not Path(str(out) + ".tmp").exists()
        # library round trip
        b, _sha, ch = BB.load_bottoms(out, [1, 4, 7])
        assert b[(4, "left")] == 1505 and b[(7, "right")] == 1520 and ch == h["config_hash"]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_derive_refusals_leave_nothing_behind():
    d = tempfile.mkdtemp()
    try:
        gp, _g = _volume(d)
        out = Path(d) / "o.jsonl"
        out.write_text("keep\n", encoding="utf-8")
        assert BB.main(["derive", "--geometry", str(gp), "--volume-dir", d, "--pages", "1", "--out", str(out)]) == 2
        assert out.read_text(encoding="utf-8") == "keep\n" and not Path(str(out) + ".tmp").exists()
        out2 = Path(d) / "o2.jsonl"                                    # a missing geometry page is a refusal
        assert BB.main(["derive", "--geometry", str(gp), "--volume-dir", d,
                        "--pages", "1", "99", "--out", str(out2)]) == 2
        assert not out2.exists() and not Path(str(out2) + ".tmp").exists()
        out3 = Path(d) / "o3.jsonl"                                    # an exception mid-way: nothing left
        try:
            BB.main(["derive", "--geometry", str(gp), "--volume-dir", str(Path(d) / "nope"),
                     "--pages", "1", "--out", str(out3)])
        except Exception:
            pass
        assert not out3.exists() and not Path(str(out3) + ".tmp").exists()
        # an undeterminable T refuses (no second mode: a single page of ruled columns)
        out4 = Path(d) / "o4.jsonl"
        assert BB.main(["derive", "--geometry", str(gp), "--volume-dir", d, "--pages", "3", "--out", str(out4)]) == 2
        assert not out4.exists() and not Path(str(out4) + ".tmp").exists()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_derive_refuses_an_out_inside_a_repo():
    d = tempfile.mkdtemp()
    try:
        gp, _g = _volume(d)
        out = Path(__file__).resolve().parent / "zz_never_written.jsonl"
        assert BB.main(["derive", "--geometry", str(gp), "--volume-dir", d, "--pages", "1", "--out", str(out)]) == 2
        assert not out.exists()
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ---- born-tests on real pages (skip when the data is absent) --------------

def _skip(name, what):
    print(f"SKIP {name}: {GEOM} / {VOL1} absent ({what})")


def _real(fp):
    from PIL import Image
    import cv_footnote_presplit as ps
    g = next(json.loads(l) for l in open(GEOM, encoding="utf-8") if f'"file_page": {fp},' in l)
    im = Image.open(VOL1 / g["image"])
    W, H = im.size
    b = BB.col_bounds(W, g["xdiv"])
    dark = ps._dark(im)
    gray = np.asarray(im.convert("L"))
    return g, H, b, dark, gray


def _have_real(geom=None, vol=None):
    geom, vol = geom or GEOM, vol or VOL1
    return geom.exists() and (vol / "page128_image1.png").exists() and (vol / "page923_image1.png").exists()


def test_born_p128_left_seeded_rule_finds_the_rule():
    if not _have_real():
        return _skip("test_born_p128_left", "seeded_rule on p128 left")
    g, H, b, dark, _gray = _real(128)
    x0, x1 = b["left"]
    runs = BB.row_max_runs(dark[:, x0:x1] > BB.DARK_THR)
    y = BB.seeded_rule(runs, g["rules"][1], LOCK["WIN"], LOCK["T"])
    assert y is not None and 4498 <= y <= 4508, y


def test_born_p923_right_has_no_seeded_rule_and_foot_strip_cuts_at_the_signature():
    if not _have_real():
        return _skip("test_born_p923_right", "no rule and the foot strip on p923")
    g, H, b, dark, gray = _real(923)
    assert g["rules"][0] is None and g["rules"][1] is None
    x0, x1 = b["right"]
    runs = BB.row_max_runs(dark[:, x0:x1] > BB.DARK_THR)
    lr = BB.paired_rule(BB.row_max_runs(dark[:, b["left"][0]:b["left"][1]] > BB.DARK_THR), runs, H,
                        LOCK["WIN"], LOCK["T"])
    assert lr == (None, "no_candidate"), lr
    n, y1, _bands = BB.foot_strip(BB.column_lines(gray, x0, x1), x1 - x0, LOCK["T_O"], LOCK["T_W"])
    assert n >= 1 and abs(y1 - 4773) <= 2, (n, y1)


def test_born_p923_left_has_no_foot_strip():
    if not _have_real():
        return _skip("test_born_p923_left", "no foot strip on p923 left")
    g, H, b, dark, gray = _real(923)
    x0, x1 = b["left"]
    n, y1, bands = BB.foot_strip(BB.column_lines(gray, x0, x1), x1 - x0, LOCK["T_O"], LOCK["T_W"])
    assert n == 0 and y1 is None and bands == []


def test_skip_is_conditional_on_exactly_the_named_paths():
    d = Path(tempfile.mkdtemp())
    try:
        assert not _have_real(d / "g.jsonl", d)                  # nothing there: skip
        (d / "g.jsonl").write_text("x", encoding="utf-8")
        (d / "page128_image1.png").write_bytes(b"")
        assert not _have_real(d / "g.jsonl", d)                  # one image missing: still skip
        (d / "page923_image1.png").write_bytes(b"")
        assert _have_real(d / "g.jsonl", d)                      # exactly the named paths: run
        (d / "g.jsonl").unlink()
        assert not _have_real(d / "g.jsonl", d)                  # geometry missing: skip
    finally:
        shutil.rmtree(d, ignore_errors=True)


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
