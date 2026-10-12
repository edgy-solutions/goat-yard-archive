"""render_verse_truth.py born-tests: synthetic-only unit + integration tests, one per spec case
(a)-(g) in SPEC_step3_console.md's "Files" section. Run: python test_render_verse_truth.py

EXPECTED_TESTS asserts the suite's OWN test count (test_verse_regions.py's pattern) so a
silently-dropped test function fails the run instead of just passing with fewer checks.

No jsdom in this repo -> no JS test; case (g)'s localStorage-key/export-filename assertion is done
by checking the generated HTML text contains the expected literal strings.
"""
import json
import shutil
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

import render_verse_truth as RVT

EXPECTED_TESTS = 37


# 1. crop_with_clamp -- left/top edge clamp, origin is the CLAMPED point, not rect-pad -----------

def test_crop_with_clamp_left_edge_clamped_origin_is_zero_not_negative():
    rect = [10, 10, 60, 60]
    box, origin, clamped_edges = RVT.crop_with_clamp(rect, W=500, H=500, pad=40)
    assert origin == (0, 0), origin
    assert clamped_edges == ["left", "top"], clamped_edges
    assert box == [0, 0, 100, 100], box


def test_crop_with_clamp_interior_rect_not_clamped():
    rect = [100, 100, 150, 150]
    box, origin, clamped_edges = RVT.crop_with_clamp(rect, W=500, H=500, pad=40)
    assert origin == (60, 60), origin
    assert clamped_edges == [], clamped_edges
    assert box == [60, 60, 190, 190], box


# 2. overlay -- correct math from the CLAMPED origin (NOT the unclamped rect - pad) ---------------

def test_overlay_from_clamped_origin_left_edge_not_shifted_by_pad():
    # rect x0=10, pad=40 clamps to origin x=0 (case 1 above). The overlay of that SAME rect on its
    # own crop must land at local x0=10 (page_x - clamped_origin_x = 10 - 0), NEVER at x0=40
    # (which is what rect - PAD would imply if origin were taken as the unclamped point).
    rect = [10, 10, 60, 60]
    box, origin, clamped_edges = RVT.crop_with_clamp(rect, W=500, H=500, pad=40)
    crop_size = (box[2] - box[0], box[3] - box[1])
    local = RVT.overlay(rect, origin, crop_size)
    assert local == [10, 10, 60, 60], local

    rect2 = [100, 100, 150, 150]
    box2, origin2, _ = RVT.crop_with_clamp(rect2, W=500, H=500, pad=40)
    crop_size2 = (box2[2] - box2[0], box2[3] - box2[1])
    local2 = RVT.overlay(rect2, origin2, crop_size2)
    assert local2 == [40, 40, 90, 90], local2


def test_overlay_out_of_bounds_raises():
    try:
        RVT.overlay([0, 0, 1000, 1000], (0, 0), (100, 100))
        assert False, "expected ValueError"
    except ValueError:
        pass


# 3. item_sha16 / set_sha16 change-detection -------------------------------------------------------

def _region_item(y0=10, count=None, read=None, witness=None, disputed=False):
    return {
        "item_id": "r:1:left:10", "item_kind": "verse", "file_page": 1,
        "rects": [{"file_page": 1, "col": "left", "box": [0, y0, 100, y0 + 20]}],
        "head": {"box": [0, y0, 20, y0 + 10]},
        "number_sources": {"count": count, "read": read, "witness": witness},
        "verse": 5, "disputed": disputed, "disputed_by": [], "flags": [],
        "witness_pairing": None, "witness_sim": None, "numbers_link_status": None,
    }


def test_item_sha16_changes_on_rect_coord_number_sources_and_disputed_but_stable_otherwise():
    base = RVT.item_sha16(_region_item(), crop_shas=["aaaa"])
    same = RVT.item_sha16(_region_item(), crop_shas=["aaaa"])
    assert base == same, "identical inputs must hash identically (twice)"

    moved = RVT.item_sha16(_region_item(y0=11), crop_shas=["aaaa"])
    assert moved != base, "a changed rect coordinate must change item_sha16"

    ns_changed = RVT.item_sha16(_region_item(read=3), crop_shas=["aaaa"])
    assert ns_changed != base, "a changed number_sources must change item_sha16"

    disputed_changed = RVT.item_sha16(_region_item(disputed=True), crop_shas=["aaaa"])
    assert disputed_changed != base, "a changed disputed flag must change item_sha16"

    pairs_a = [("r:1:left:10", base), ("m:1:5", "bbbb")]
    pairs_b = [("m:1:5", "bbbb"), ("r:1:left:10", base)]
    assert RVT.set_sha16(pairs_a) == RVT.set_sha16(pairs_b), "set_sha16 must be order-independent"
    pairs_c = [("r:1:left:10", moved), ("m:1:5", "bbbb")]
    assert RVT.set_sha16(pairs_a) != RVT.set_sha16(pairs_c), "set_sha16 must change when an item_sha16 changes"


# 4. build_items -- duplicate item_id raises -------------------------------------------------------

def test_build_items_duplicate_item_id_raises():
    rec = {"kind": "verse", "file_page_first": 1, "rects": [{"file_page": 1, "col": "left", "box": [0, 10, 100, 30]}]}
    try:
        RVT.build_items([rec, dict(rec)], {"misses": []})
        assert False, "expected ValueError on duplicate item_id"
    except ValueError:
        pass


# 5. build_items -- region record with empty rects raises -------------------------------------------

def test_build_items_empty_rects_raises():
    rec = {"kind": "verse", "file_page_first": 1, "rects": []}
    try:
        RVT.build_items([rec], {"misses": []})
        assert False, "expected ValueError on empty rects"
    except ValueError:
        pass


# 6. mechanism_label -- A/B/C rule from (mech, inset_px) ---------------------------------------------

def test_mechanism_label_rule_a_b_c_and_unknown_raises():
    assert RVT.mechanism_label("inset_below_thr", -5).startswith("A:")
    assert RVT.mechanism_label("inset_below_thr", 0).startswith("B:")
    assert RVT.mechanism_label("inset_below_thr", 5).startswith("B:")
    assert RVT.mechanism_label("in_full_band_not_centred", None).startswith("C:")
    try:
        RVT.mechanism_label("something_else", 1)
        assert False, "expected ValueError on unrecognized mech"
    except ValueError:
        pass


# 7. full synthetic build integration test ------------------------------------------------------------

def _write_synthetic_page(path, W=200, H=200, fill=230):
    arr = np.full((H, W), fill, dtype=np.uint8)
    # Dark ink block so every claimed rect/band has ink > 0.
    arr[20:180, 20:180] = 40
    Image.fromarray(arr, mode="L").save(path)


_BODY_REGIONS = [{"col": "left", "box": [0, 0, 100, 200]}, {"col": "right", "box": [100, 0, 200, 200]}]


def _make_synthetic_inputs(tmp_dir):
    tmp_dir = Path(tmp_dir)
    volume_dir = tmp_dir / "volume1"
    volume_dir.mkdir(parents=True, exist_ok=True)
    for fp in (101, 102):
        _write_synthetic_page(volume_dir / f"page{fp}_image1.png")

    run_records = [
        {"kind": "run_header", "config": {"hash": "cfgABC"}},
        {"kind": "page", "file_page": 101},
        {"kind": "page", "file_page": 102},
        {
            "kind": "verse", "file_page_first": 101,
            "rects": [{"file_page": 101, "col": "left", "box": [30, 30, 150, 60]}],
            "head": {"box": [30, 30, 60, 45], "head_confirm": {"text": "5 In the", "numbers": [5], "ver": True, "status": "ok"}},
            "number_sources": {"count": 1, "read": 5, "witness": 5}, "verse": 5,
            "disputed": False, "disputed_by": [], "flags": [], "witness_pairing": "read=witness",
            "witness_sim": 1.0, "numbers_link_status": "ok",
        },
        {
            "kind": "chapter_intro", "file_page_first": 102,
            "rects": [{"file_page": 102, "col": "full", "box": [30, 30, 150, 60]}],
            "head": None, "number_sources": {"count": None, "read": None, "witness": None},
            "verse": None, "disputed": None, "disputed_by": None, "flags": [],
            "witness_pairing": None, "witness_sim": None, "numbers_link_status": None,
        },
        {"kind": "run_summary", "layout": {"head_first": 0, "overlap": 0, "rect_before_head": 0}},
    ]
    run_path = tmp_dir / "run.jsonl"
    with open(run_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(json.dumps(r) for r in run_records) + "\n")

    misses_doc = {
        "thr": 35.0, "pitch": 57.0, "n": 1,
        "misses": [{
            "fp": 101, "word": [100, 100, 130, 115], "tess": "Ver.", "mech": "inset_below_thr",
            "col": "right", "band": [90, 95, 160, 120], "band_h": 25, "inset_px": -3,
            "word_inset_px": 2, "col_left_x": 90,
        }],
    }
    misses_path = tmp_dir / "misses.json"
    misses_path.write_text(json.dumps(misses_doc), encoding="utf-8")

    geometry_records = [
        {"file_page": 101, "xdiv": 100, "body_regions": _BODY_REGIONS},
        {"file_page": 102, "xdiv": 100, "body_regions": _BODY_REGIONS},
    ]
    geometry_path = tmp_dir / "geometry.jsonl"
    with open(geometry_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(json.dumps(r) for r in geometry_records) + "\n")

    return run_path, misses_path, geometry_path, volume_dir


def test_full_synthetic_build_counts_manifest_header_and_refuse_overwrite():
    tmp_dir = Path(tempfile.mkdtemp(prefix="rvt_test_"))
    try:
        run_path, misses_path, geometry_path, volume_dir = _make_synthetic_inputs(tmp_dir)
        out_root = tmp_dir / "out"

        result = RVT.build(run_path, misses_path, geometry_path, volume_dir, out_root)
        assert result["n_items_by_kind"] == {"region": 2, "miss": 1, "page": 2}, result["n_items_by_kind"]
        assert result["n_items"] == 5

        out_dir = result["out_dir"]
        manifest_lines = (out_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        header = json.loads(manifest_lines[0])
        assert header["kind"] == "console_header"
        assert "git_dirty" in header
        assert header["set_sha16"] == result["set_sha16"]
        footer = json.loads(manifest_lines[-1])
        assert footer["kind"] == "console_summary"

        item_lines = [json.loads(l) for l in manifest_lines[1:-1] if json.loads(l).get("kind") == "item"]
        assert len(item_lines) == 5
        seen_ids = [l["item_id"] for l in item_lines]
        assert len(seen_ids) == len(set(seen_ids)), "every item_id must appear exactly once"

        html_text = (out_dir / "index.html").read_text(encoding="utf-8")
        for item_id in seen_ids:
            assert html_text.count(f'data-item-id="{item_id}"') == 1, item_id

        try:
            RVT.build(run_path, misses_path, geometry_path, volume_dir, out_root)
            assert False, "expected RefuseOverwrite without --force"
        except RVT.RefuseOverwrite:
            pass

        result2 = RVT.build(run_path, misses_path, geometry_path, volume_dir, out_root, force=True)
        assert result2["set_sha16"] == result["set_sha16"]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# 8. generated HTML carries the localStorage key prefix + export filename (no-jsdom substitute) ----

def test_html_contains_localstorage_key_prefix_and_export_filename():
    tmp_dir = Path(tempfile.mkdtemp(prefix="rvt_test_"))
    try:
        run_path, misses_path, geometry_path, volume_dir = _make_synthetic_inputs(tmp_dir)
        out_root = tmp_dir / "out"
        result = RVT.build(run_path, misses_path, geometry_path, volume_dir, out_root)
        html_text = (result["out_dir"] / "index.html").read_text(encoding="utf-8")
        set_sha = result["set_sha16"]
        assert f'"versetruth_{set_sha}"' in html_text
        assert f"verse_box_verdicts_{set_sha}.jsonl" in html_text
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# 9. region crop with zero ink inside the rect fails loud --------------------------------------------

def test_region_crop_zero_ink_in_rect_raises():
    tmp_dir = Path(tempfile.mkdtemp(prefix="rvt_test_"))
    try:
        volume_dir = tmp_dir / "volume1"
        volume_dir.mkdir(parents=True, exist_ok=True)
        # Uniform blank (no ink anywhere) -- a claimed region rect over it must fail loud.
        arr = np.full((200, 200), 250, dtype=np.uint8)
        Image.fromarray(arr, mode="L").save(volume_dir / "page101_image1.png")

        item = {
            "item_id": "r:1:left:10", "item_kind": "verse", "file_page": 101,
            "rects": [{"file_page": 101, "col": "left", "box": [30, 30, 150, 60]}],
            "head": None, "number_sources": {}, "verse": None,
        }
        try:
            RVT._render_region_crops(item, volume_dir, {})
            assert False, "expected ValueError on zero-ink region crop"
        except ValueError:
            pass
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# 10. build_items -- page items pick up region/miss item_ids on their own page ------------------------

def test_build_items_page_item_lists_its_own_regions_and_misses():
    run_records = [
        {"kind": "page", "file_page": 101},
        {"kind": "verse", "file_page_first": 101,
         "rects": [{"file_page": 101, "col": "left", "box": [0, 10, 100, 30]}]},
    ]
    misses = {"misses": [{"fp": 101, "word": [0, 50, 10, 60], "tess": "Ver.", "mech": "in_full_band_not_centred",
                            "col": "full", "band": [0, 45, 100, 65], "band_h": 20}]}
    items = RVT.build_items(run_records, misses)
    page_item = next(i for i in items if i["item_kind"] == "page")
    assert page_item["region_item_ids"] == ["r:101:left:10"]
    assert page_item["miss_item_ids"] == ["m:101:50"]


# 11. --html-only (UI 2) ------------------------------------------------------------------------------

def _crop_shas(out_dir):
    return {p.name: RVT._sha16_bytes(p.read_bytes()) for p in sorted((out_dir / "crops").glob("*.png"))}


def _built_console(tmp_dir):
    run_path, misses_path, geometry_path, volume_dir = _make_synthetic_inputs(tmp_dir)
    out_root = Path(tmp_dir) / "out"
    result = RVT.build(run_path, misses_path, geometry_path, volume_dir, out_root)
    return (run_path, misses_path, geometry_path, volume_dir, out_root), result


def test_html_only_keeps_set_sha_and_crops_renames_old_index_and_appends_manifest_line():
    tmp_dir = Path(tempfile.mkdtemp(prefix="rvt_test_"))
    try:
        (run_path, misses_path, geometry_path, volume_dir, out_root), result = _built_console(tmp_dir)
        out_dir = result["out_dir"]
        before = _crop_shas(out_dir)
        old_html = (out_dir / "index.html").read_bytes()
        r = RVT.html_only(run_path, misses_path, geometry_path, volume_dir, out_root)
        assert r["set_sha16"] == result["set_sha16"] == out_dir.name
        assert _crop_shas(out_dir) == before, "crops must be byte-identical"
        assert (out_dir / "index_ui1.html").read_bytes() == old_html
        assert (out_dir / "index.html").read_bytes() != old_html
        last = json.loads((out_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        assert last["kind"] == "html_rebuild" and last["ui_version"] == 2, last
        assert last["prior_index_renamed_to"] == "index_ui1.html"
        assert last["set_sha16"] == result["set_sha16"]
        assert last["snap_edge_coincidence"]["tops"][1] == 2
        # a second rebuild with an identical config is refused unless forced; forcing never overwrites ui1
        try:
            RVT.html_only(run_path, misses_path, geometry_path, volume_dir, out_root)
            assert False, "expected RefuseOverwrite"
        except RVT.RefuseOverwrite:
            pass
        r2 = RVT.html_only(run_path, misses_path, geometry_path, volume_dir, out_root, force=True)
        assert r2["renamed_to"] == "index_ui2.html"
        assert (out_dir / "index_ui1.html").read_bytes() == old_html
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_html_only_tampered_crop_raises_and_writes_nothing():
    tmp_dir = Path(tempfile.mkdtemp(prefix="rvt_test_"))
    try:
        (run_path, misses_path, geometry_path, volume_dir, out_root), result = _built_console(tmp_dir)
        out_dir = result["out_dir"]
        crop = sorted((out_dir / "crops").glob("*.png"))[0]
        b = bytearray(crop.read_bytes())
        b[-5] ^= 0xFF
        crop.write_bytes(bytes(b))
        html_before = (out_dir / "index.html").read_bytes()
        n_lines = len((out_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines())
        try:
            RVT.html_only(run_path, misses_path, geometry_path, volume_dir, out_root)
            assert False, "expected ValueError on a tampered crop"
        except ValueError:
            pass
        assert (out_dir / "index.html").read_bytes() == html_before
        assert len((out_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()) == n_lines
        assert not (out_dir / "index_ui1.html").exists()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_html_only_snap_targets_contain_every_detected_rect_edge():
    tmp_dir = Path(tempfile.mkdtemp(prefix="rvt_test_"))
    try:
        (run_path, misses_path, geometry_path, volume_dir, out_root), result = _built_console(tmp_dir)
        r = RVT.html_only(run_path, misses_path, geometry_path, volume_dir, out_root)
        snap = r["snap"]
        n = 0
        for item in result["items"]:
            if item["item_kind"] not in RVT.REGION_KINDS:
                continue
            for rect in item["rects"]:
                per = snap[str(rect["file_page"])][rect["col"]]
                assert rect["box"][1] in per["tops"], (rect, per)
                assert rect["box"][3] in per["bottoms"], (rect, per)
                n += 1
        assert n == 2
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_html_only_html_carries_ui2_keys_export_name_and_inlined_js_functions():
    tmp_dir = Path(tempfile.mkdtemp(prefix="rvt_test_"))
    try:
        (run_path, misses_path, geometry_path, volume_dir, out_root), result = _built_console(tmp_dir)
        RVT.html_only(run_path, misses_path, geometry_path, volume_dir, out_root)
        html_text = (result["out_dir"] / "index.html").read_text(encoding="utf-8")
        set_sha = result["set_sha16"]
        assert f'"versetruth_{set_sha}_ui2"' in html_text
        assert f'"versetruth_{set_sha}"' in html_text, "ui1 migration key"
        assert f"verse_box_verdicts_{set_sha}_ui2.jsonl" in html_text
        assert f"verse_box_verdicts_{set_sha}_ui1.jsonl" in html_text
        for fn in ("function snap(", "function clampEdge(", "function linesMoved(", "function applyDrag(",
                   "function verdictCoupling(", "function buildExportRow("):
            assert fn in html_text, fn
        assert "page101_image1.png" in html_text and "pagewin" in html_text
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)



def test_continuation_card_first_on_its_page():
    # page 90 (Chris 2026-10-11): run order chapter_intro, continuation_unanchored, verse
    grp = {"region": [], "miss": [], "page": None}
    for kind, card in (("chapter_intro", "C"), ("continuation_unanchored", "U"), ("verse", "V")):
        RVT._add_region_card(grp, kind, card)
    assert grp["region"] == ["U", "C", "V"], grp["region"]
    try:
        RVT._add_region_card(grp, "continuation_unanchored", "U2")
    except ValueError:
        pass
    else:
        raise AssertionError("second continuation on one page must raise")


# 12. layout refusal / stale misses / carry-forward ---------------------------------------------------

def _rewrite_summary(run_path, summary):
    recs = [json.loads(l) for l in Path(run_path).read_text(encoding="utf-8").splitlines() if l.strip()]
    recs = [r for r in recs if r.get("kind") != "run_summary"]
    if summary is not None:
        recs.append(summary)
    Path(run_path).write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")


def test_build_layout_refusal_writes_nothing_and_all_zero_builds():
    tmp_dir = Path(tempfile.mkdtemp(prefix="rvt_test_"))
    try:
        run_path, misses_path, geometry_path, volume_dir = _make_synthetic_inputs(tmp_dir)
        out_root = tmp_dir / "out"
        for summary, needle in (
            (None, "no run_summary"),
            ({"kind": "run_summary"}, "layout"),
            ({"kind": "run_summary", "layout": {"head_first": 0, "overlap": 2, "rect_before_head": 0}}, "overlap"),
            ({"kind": "run_summary", "layout": {"head_first": 1, "overlap": 0, "rect_before_head": 3}}, "head_first"),
        ):
            _rewrite_summary(run_path, summary)
            try:
                RVT.build(run_path, misses_path, geometry_path, volume_dir, out_root)
                assert False, f"expected ValueError for {summary}"
            except ValueError as e:
                assert needle in str(e), (needle, str(e))
            assert not out_root.exists(), "nothing may be written on refusal"
        _rewrite_summary(run_path, {"kind": "run_summary", "layout": {"head_first": 0, "overlap": 0, "rect_before_head": 0}})
        assert RVT.build(run_path, misses_path, geometry_path, volume_dir, out_root)["n_items"] == 5
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_stale_miss_raises_in_build_and_html_only_and_writes_nothing():
    tmp_dir = Path(tempfile.mkdtemp(prefix="rvt_test_"))
    try:
        (run_path, misses_path, geometry_path, volume_dir, out_root), result = _built_console(tmp_dir)
        recs = [json.loads(l) for l in run_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        for r in recs:
            if r.get("kind") == "verse":
                r["head"]["box"] = [95, 98, 135, 112]      # now covers the miss word [100,100,130,115]
        stale_run = tmp_dir / "stale_run.jsonl"
        stale_run.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
        out_root_b = tmp_dir / "out_b"
        try:
            RVT.build(stale_run, misses_path, geometry_path, volume_dir, out_root_b)
            assert False, "expected stale ValueError"
        except ValueError as e:
            assert "miss trace stale: m:101:100" in str(e), str(e)
        assert not out_root_b.exists()
        try:
            RVT.html_only(stale_run, misses_path, geometry_path, volume_dir, out_root)
            assert False, "expected stale ValueError in html_only"
        except ValueError as e:
            assert "miss trace stale" in str(e)
        assert not (result["out_dir"] / "index_ui1.html").exists()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _synthetic_old_console(root, set_sha, items):
    """items: [(item_id, item_sha16, file_page, band)] -> a minimal old console dir named set_sha."""
    d = Path(root) / set_sha
    d.mkdir(parents=True)
    lines = [{"kind": "console_header", "set_sha16": set_sha}]
    for iid, sha, fp, band in items:
        lines.append({"kind": "item", "item_id": iid, "item_kind": "miss", "item_sha16": sha, "file_page": fp,
                      "crops": [{"rect": band}]})
    lines.append({"kind": "item", "item_id": "r:1:left:10", "item_kind": "verse", "item_sha16": "zz", "file_page": 1,
                  "crops": [{"rect": [0, 0, 1, 1]}]})
    (d / "manifest.jsonl").write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
    return d


def _new_entry(iid, fp, y0, band):
    return {"item_id": iid, "item_sha16": "n" + iid[-3:], "file_page": fp, "band": band, "word_y0": y0}


def test_carry_map_classifies_matched_conflict_old_and_new_unmatched():
    root = Path(tempfile.mkdtemp(prefix="rvt_test_"))
    try:
        d = _synthetic_old_console(root, "aaaaaaaaaaaaaaaa", [
            ("m:130:3986", "o1", 130, [1931, 3986, 3584, 4045]),
            ("m:131:500", "o2", 131, [0, 500, 900, 560]),
            ("m:132:700", "o3", 132, [0, 700, 900, 760]),
            ("m:133:100", "o4", 133, [0, 100, 900, 160]),
        ])
        old_set, old = RVT.read_old_console(d)
        assert old_set == "aaaaaaaaaaaaaaaa" and len(old) == 4, "only miss items are read"
        new = [
            _new_entry("m:130:3986", 130, 3986, [1931, 3986, 3584, 4045]),     # matched
            _new_entry("m:131:500", 131, 500, [0, 500, 950, 560]),             # same fp+y0, different band
            _new_entry("m:140:9", 140, 9, [0, 9, 10, 19]),                     # new only
        ]
        carry, counts, lists = RVT.compute_carry(old_set, old, new)
        assert counts == {"matched": 1, "identity_conflict": 1, "old_unmatched": 2, "new_unmatched": 1}, counts
        assert lists["identity_conflict"] == ["m:131:500"] and lists["new_unmatched"] == ["m:140:9"]
        assert lists["old_unmatched"] == ["m:132:700", "m:133:100"]
        assert carry["map"]["m:130:3986"]["old_item_id"] == "m:130:3986"
        assert carry["from_ui_key"] == "versetruth_aaaaaaaaaaaaaaaa_ui2" and carry["fields"] == ["cause_verdict", "note"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_carry_old_dir_set_mismatch_raises():
    root = Path(tempfile.mkdtemp(prefix="rvt_test_"))
    try:
        d = _synthetic_old_console(root, "bbbbbbbbbbbbbbbb", [("m:1:1", "o", 1, [0, 1, 2, 3])])
        d2 = d.rename(root / "cccccccccccccccc")
        try:
            RVT.read_old_console(d2)
            assert False, "expected ValueError"
        except ValueError:
            pass
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_html_only_carry_embeds_map_manifest_fields_and_null_without_flag():
    tmp_dir = Path(tempfile.mkdtemp(prefix="rvt_test_"))
    try:
        (run_path, misses_path, geometry_path, volume_dir, out_root), result = _built_console(tmp_dir)
        out_dir = result["out_dir"]
        RVT.html_only(run_path, misses_path, geometry_path, volume_dir, out_root)
        html0 = (out_dir / "index.html").read_text(encoding="utf-8")
        assert "const CARRY = null;" in html0
        last0 = json.loads((out_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        assert last0["carry_map_sha16"] is None and last0["carry_counts"] is None
        old = _synthetic_old_console(tmp_dir / "old", "dddddddddddddddd", [
            ("m:101:100", "oldsha", 101, [90, 95, 160, 120]), ("m:150:1", "x", 150, [0, 1, 2, 3])])
        r = RVT.html_only(run_path, misses_path, geometry_path, volume_dir, out_root, carry_from=old, force=True)
        html1 = (out_dir / "index.html").read_text(encoding="utf-8")
        assert '"from_ui_key": "versetruth_dddddddddddddddd_ui2"' in html1
        assert '"m:101:100"' in html1 and '"old_item_sha16": "oldsha"' in html1
        assert "function carryForward(" in html1 and "const CARRY_REPORT" in html1
        rec = json.loads((out_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        assert rec["carry_counts"] == {"matched": 1, "identity_conflict": 0, "old_unmatched": 1, "new_unmatched": 0}, rec["carry_counts"]
        assert rec["carry_old_unmatched"] == ["m:150:1"] and rec["carry_from_set_sha16"] == "dddddddddddddddd"
        assert rec["carry_map_sha16"] == RVT._sha16_json(r["carry"]) and rec["carry_from"] == str(old)
        assert rec["config_hash"] != last0["config_hash"], "carry_map_sha16 enters the ui config hash"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_build_with_carry_from_raises():
    tmp_dir = Path(tempfile.mkdtemp(prefix="rvt_test_"))
    try:
        run_path, misses_path, geometry_path, volume_dir = _make_synthetic_inputs(tmp_dir)
        try:
            RVT.build(run_path, misses_path, geometry_path, volume_dir, tmp_dir / "out", carry_from=tmp_dir)
            assert False, "expected ValueError"
        except ValueError as e:
            assert "--carry-from" in str(e)
        assert not (tmp_dir / "out").exists()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_miss_overlay_labels_rule_split_vs_geometry_xdiv():
    item = {"file_page": 101, "miss": {"band": [90, 95, 160, 120], "word": [100, 100, 130, 115]}}
    geometry = {101: {"file_page": 101, "xdiv": 100}}
    origin, size = (50, 40), (200, 120)           # crop middle y = 100
    ok = {101: {"kind": "page", "file_page": 101,
                "col_split": {"status": "ok", "slope": 0.01, "c0": 120.0}}}
    vl = [o for o in RVT._miss_overlays(item, geometry, origin, size, ok) if o["kind"] == "vline"]
    assert [(o["label"], o["x"]) for o in vl] == [("rule split", round(0.01 * 100 + 120.0) - 50)], vl
    for page_by_fp in (None, {}, {101: {"col_split": {"status": "abstained", "reason": "no_rule"}}}):
        vl = [o for o in RVT._miss_overlays(item, geometry, origin, size, page_by_fp) if o["kind"] == "vline"]
        assert [(o["label"], o["x"]) for o in vl] == [("xdiv (geometry)", 100 - 50)], (page_by_fp, vl)


def test_html_only_miss_entry_carries_col_split_and_col_boxes_from_page_record():
    tmp_dir = Path(tempfile.mkdtemp(prefix="rvt_test_"))
    try:
        (run_path, misses_path, geometry_path, volume_dir, out_root), result = _built_console(tmp_dir)
        recs = [json.loads(l) for l in run_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        for r in recs:
            if r.get("kind") == "page" and r["file_page"] == 101:
                r["col_split"] = {"status": "ok", "slope": 0.0123, "c0": 111.5}
                r["col_boxes"] = {"left": [0, 0, 105, 200], "right": [105, 0, 200, 200]}
        run_path.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
        RVT.html_only(run_path, misses_path, geometry_path, volume_dir, out_root)
        html_text = (result["out_dir"] / "index.html").read_text(encoding="utf-8")
        assert '"col_split": {"slope": 0.0123, "c0": 111.5}' in html_text
        assert '"left": [0, 0, 105, 200]' in html_text
        assert '"xdiv": 100' in html_text
        assert "function pageColumn(" in html_text and "pageColumn(it2, x, y)" in html_text
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# 13. prior verdicts carried by heading identity ---------------------------------------------------------

PITCH = 57.0   # tol = floor(57 / 2) = 28


def _prec(fp, rect_y0, head_y0, verse=(1,), col="left", extra_rects=(), x=(0, 1900), kind="verse", h=200, head=True):
    rects = [{"file_page": fp, "col": col, "box": [x[0], rect_y0, x[1], rect_y0 + h]}]
    for ecol in extra_rects:
        rects.append({"file_page": fp, "col": ecol, "box": [1900, rect_y0, 3800, rect_y0 + h]})
    hd = {"file_page": fp, "col": col, "y0": head_y0, "y1": head_y0 + 60, "box": [x[0], head_y0, x[1], head_y0 + 60]} if head else None
    return {"kind": kind, "file_page_first": fp, "head": hd, "rects": rects, "verse": list(verse) if head else None,
            "flags": []}


def _xrow(item_id, kind, verdict, ratified=None, detected=None, note="", set_="S1", heads=None):
    return {"item_id": item_id, "item_kind": kind, "file_page": int(item_id.split(":")[1]), "verdict": verdict,
            "as_ratified": ratified, "as_detected": detected, "note": note, "set_sha16": set_,
            "heads_not_shown": heads}


def _rat(fp, col, y0, y1, x=(0, 1900)):
    return {"file_page": fp, "col": col, "box": [x[0], y0, x[1], y1],
            "edges": {"top": {"snapped": True, "lines_moved": 1, "at_crop_limit": False},
                      "bottom": {"snapped": False, "lines_moved": 0, "at_crop_limit": True}}}


def _prior(old_recs, rows, new_recs, pitch=PITCH):
    return RVT.compute_prior(old_recs, rows, RVT.build_items(new_recs, []), pitch_px=pitch)


def test_prior_exact_match_same_layout_correct_seeds_correct():
    old = [_prec(5, 100, 100)]
    rows = [_xrow("r:5:left:100", "verse", "correct", ratified=[_rat(5, "left", 100, 300)], note="fine")]
    P, c, l = _prior(old, rows, [_prec(5, 100, 100)])
    e = P["map"]["r:5:left:100"]
    assert (e["class"], e["match"]) == ("carried_same_layout", "exact"), e
    assert e["seeded"]["verdict"] == "correct" and e["seeded"]["note"] == "fine"
    assert e["seeded"]["ratified"][0]["box"] == [0, 100, 1900, 300]
    assert e["delta"] == {"5:left": [0, 0]} and c["seeded"] == 1 and P["from_set_sha16"] == "S1"


def test_prior_near_match_within_half_pitch_and_not_beyond():
    old = [_prec(5, 100, 100)]
    rows = [_xrow("r:5:left:100", "verse", "correct", ratified=[_rat(5, "left", 100, 300)])]
    P, c, l = _prior(old, rows, [_prec(5, 120, 128)])           # dy = 28 == tol
    e = P["map"]["r:5:left:120"]
    assert e["match"] == "near" and e["old_item_id"] == "r:5:left:100", e
    P2, c2, l2 = _prior(old, rows, [_prec(5, 120, 129)])        # dy = 29 > tol
    assert "r:5:left:120" not in P2["map"] and l2["new_unmatched"] == ["r:5:left:120"]
    assert [d["item_id"] for d in l2["old_unmatched"]] == ["r:5:left:100"]


def test_prior_near_with_two_candidates_is_identity_conflict_and_carries_nothing():
    old = [_prec(5, 100, 100), _prec(5, 140, 130)]               # same verse, both within 28 of 115
    rows = [_xrow("r:5:left:100", "verse", "correct", ratified=[_rat(5, "left", 100, 300)]),
            _xrow("r:5:left:140", "verse", "correct", ratified=[_rat(5, "left", 140, 340)])]
    P, c, l = _prior(old, rows, [_prec(5, 115, 115)])
    assert P["map"] == {} and l["identity_conflict"] == ["r:5:left:115"] and c["identity_conflict"] == 1
    assert len(l["old_unmatched"]) == 2, "unused old sources are retired, not dropped"


def test_prior_not_a_verse_is_carried_verdict_with_note():
    old = [_prec(5, 100, 100)]
    rows = [_xrow("r:5:left:100", "verse", "not_a_verse", note="a footnote number")]
    P, c, l = _prior(old, rows, [_prec(5, 100, 100)])
    e = P["map"]["r:5:left:100"]
    assert e["class"] == "carried_verdict" and e["seeded"] == {"verdict": "not_a_verse", "note": "a footnote number"}


def test_prior_same_layout_with_moved_y_seeds_adjusted_with_delta_and_new_x():
    old = [_prec(5, 100, 100)]
    rows = [_xrow("r:5:left:100", "verse", "adjusted", ratified=[_rat(5, "left", 90, 310, x=(7, 1800))], note="n")]
    P, c, l = _prior(old, rows, [_prec(5, 100, 100)])
    e = P["map"]["r:5:left:100"]
    assert e["class"] == "carried_same_layout"
    assert e["seeded"]["verdict"] == "adjusted"
    assert e["seeded"]["ratified"][0]["box"] == [0, 90, 1900, 310], "x comes from the NEW detection"
    assert e["seeded"]["ratified"][0]["edges"]["top"] == {"snapped": True, "at_crop_limit": False}
    assert e["delta"] == {"5:left": [-10, 10]}


def test_prior_layout_changed_seeds_nothing_and_keeps_the_prior_as_content():
    old = [_prec(5, 100, 100)]
    rows = [_xrow("r:5:left:100", "verse", "adjusted", ratified=[_rat(5, "left", 90, 310)], note="mine")]
    P, c, l = _prior(old, rows, [_prec(5, 100, 100, extra_rects=("right",))])
    e = P["map"]["r:5:left:100"]
    assert e["class"] == "layout_changed" and e["seeded"] is None and e["delta"] is None
    assert e["prior"]["verdict"] == "adjusted" and e["prior"]["note"] == "mine"
    assert e["prior"]["rects"][0]["box"] == [0, 90, 1900, 310]
    assert c["seeded"] == 0 and c["by_class"] == {"layout_changed": 1}


def test_prior_from_miss_drawn_region_matches_a_new_head():
    rows = [_xrow("m:5:3000", "miss", "region_drawn", ratified=[_rat(5, "left", 2990, 3400)], note="drawn")]
    old = [_prec(5, 100, 100)]
    P, c, l = _prior(old, rows, [_prec(5, 3005, 3020, verse=(9,))])   # |3020 - 3000| = 20 <= 28
    e = P["map"]["r:5:left:3005"]
    assert e["match"] == "from_miss" and e["old_item_id"] == "m:5:3000", e
    assert e["class"] == "carried_same_layout" and e["seeded"]["verdict"] == "adjusted"
    assert e["seeded"]["ratified"][0]["box"] == [0, 2990, 1900, 3400]
    assert l["old_unmatched"] == [], "the miss was used"


def test_prior_page_item_carried_only_when_every_region_carried():
    old = [_prec(5, 100, 100), _prec(5, 500, 500, verse=(2,)), {"kind": "page", "file_page": 5}]
    rows = [_xrow("r:5:left:100", "verse", "correct", ratified=[_rat(5, "left", 100, 300)]),
            _xrow("r:5:left:500", "verse", "not_a_verse"),
            _xrow("p:5", "page", "answered", heads=3, note="three")]
    new = [_prec(5, 100, 100), _prec(5, 500, 500, verse=(2,)), {"kind": "page", "file_page": 5}]
    P, c, l = _prior(old, rows, new)
    pe = P["map"]["p:5"]
    assert pe["class"] == "carried_same_layout" and pe["seeded"] == {"heads_not_shown": 3, "note": "three"}
    new2 = [_prec(5, 100, 100, extra_rects=("right",)), _prec(5, 500, 500, verse=(2,)), {"kind": "page", "file_page": 5}]
    P2, c2, l2 = _prior(old, rows, new2)
    pe2 = P2["map"]["p:5"]
    assert pe2["class"] == "layout_changed" and pe2["seeded"] is None and pe2["prior"]["heads_not_shown"] == 3
    new3 = [_prec(5, 100, 100), {"kind": "page", "file_page": 5}]      # an old region no longer matched
    P3, c3, l3 = _prior(old, rows, new3)
    assert P3["map"]["p:5"]["class"] == "layout_changed"
    assert [d["item_id"] for d in l3["old_unmatched"]] == ["r:5:left:500"]


def test_prior_old_unmatched_lists_verdict_and_note_and_skips_unrated():
    old = [_prec(5, 100, 100), _prec(5, 700, 700, verse=(3,))]
    rows = [_xrow("r:5:left:100", "verse", "adjusted", ratified=[_rat(5, "left", 90, 300)], note="gone"),
            _xrow("r:5:left:700", "verse", "unrated")]
    P, c, l = _prior(old, rows, [_prec(5, 2000, 2000, verse=(8,))])
    assert l["old_unmatched"] == [{"item_id": "r:5:left:100", "verdict": "adjusted", "note": "gone"}]
    assert c["old_unmatched"] == 1 and l["new_unmatched"] == ["r:5:left:2000"]


def test_prior_cont_regions_match_on_exact_identity_only():
    old = [_prec(5, 100, 0, kind="continuation_unanchored", head=False)]
    rows = [_xrow("r:5:left:100", "continuation_unanchored", "correct", ratified=[_rat(5, "left", 100, 300)])]
    P, c, l = _prior(old, rows, [_prec(5, 100, 0, kind="continuation_unanchored", head=False)])
    assert P["map"]["r:5:left:100"]["match"] == "exact"
    P1, _, _ = _prior(old, rows, [_prec(5, 110, 0, kind="continuation_unanchored", head=False)])
    assert P1["map"]["r:5:left:110"]["match"] == "exact", "identity is (fp, col): a moved top still matches"
    P2, c2, l2 = _prior(old, rows, [_prec(5, 100, 0, col="right", kind="continuation_unanchored", head=False)])
    assert P2["map"] == {} and l2["new_unmatched"] == ["r:5:right:100"], "another column never near-matches"


def test_prior_refuses_mixed_sets_unknown_rows_and_missing_pitch():
    old = [_prec(5, 100, 100)]
    mixed = [_xrow("r:5:left:100", "verse", "correct", ratified=[_rat(5, "left", 100, 300)]),
             _xrow("m:5:3000", "miss", "region_drawn", ratified=[_rat(5, "left", 2990, 3400)], set_="S2")]
    for rows, pitch, what in ((mixed, PITCH, "set"),
                              ([_xrow("r:9:left:1", "verse", "correct")], PITCH, "not an item"),
                              ([_xrow("r:5:left:100", "verse", "correct")], None, "pitch")):
        try:
            _prior(old, rows, [_prec(5, 100, 100)], pitch=pitch)
            assert False, f"expected ValueError ({what})"
        except ValueError as e:
            assert what in str(e) or what == "set", e
    assert RVT.run_pitch_px([{"kind": "run_summary", "thresholds": {}}]) is None
    assert RVT.run_pitch_px([{"kind": "run_summary", "thresholds": {"inset_thr": {"pitch_px": 57.0}}}]) == 57.0


def test_prior_html_only_embeds_map_and_manifest_and_changes_the_ui_config_hash():
    tmp_dir = Path(tempfile.mkdtemp(prefix="rvt_test_"))
    try:
        (run_path, misses_path, geometry_path, volume_dir, out_root), result = _built_console(tmp_dir)
        out_dir = result["out_dir"]
        _rewrite_summary(run_path, {"kind": "run_summary", "thresholds": {"inset_thr": {"pitch_px": 57.0}},
                                    "layout": {"head_first": 0, "overlap": 0, "rect_before_head": 0}})
        RVT.html_only(run_path, misses_path, geometry_path, volume_dir, out_root)
        last0 = json.loads((out_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        assert last0["prior_map_sha16"] is None and last0["prior_counts"] is None
        html0 = (out_dir / "index.html").read_text(encoding="utf-8")
        assert "const PRIOR = null;" in html0
        recs = RVT.load_run_records(run_path)
        rows = [_xrow("r:101:left:30", "verse", "correct", ratified=[_rat(101, "left", 30, 60, x=(30, 150))], note="ok"),
                _xrow("p:101", "page", "answered", heads=2)]
        exp = tmp_dir / "export.jsonl"
        exp.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        r = RVT.html_only(run_path, misses_path, geometry_path, volume_dir, out_root, prior_export=exp,
                          prior_run=run_path, force=True)
        html1 = (out_dir / "index.html").read_text(encoding="utf-8")
        assert '"class": "carried_same_layout"' in html1 and "function seedPrior(" in html1
        assert 'id="nextinc"' in html1 and 'id="missing"' in html1 and "const PRIOR_REPORT" in html1
        rec = json.loads((out_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        assert rec["prior_map_sha16"] == RVT._sha16_json(r["prior"]) and rec["prior_export"] == str(exp)
        assert rec["export_sha256"] == RVT._sha256_file(exp) and rec["old_run_sha256"] == RVT._sha256_file(run_path)
        assert rec["prior_counts"]["by_class"] == {"carried_same_layout": 2, "fresh": 1}, rec["prior_counts"]
        assert rec["config_hash"] != last0["config_hash"], "prior_map_sha16 enters the ui config hash"
        try:
            RVT.html_only(run_path, misses_path, geometry_path, volume_dir, out_root, prior_export=exp, force=True)
            assert False, "expected ValueError"
        except ValueError:
            pass
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


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
