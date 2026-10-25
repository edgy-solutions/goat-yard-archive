"""realize_rects and the realized-rect side file.
Run: python test_realized_rects.py

Unit tests on synthetic boxes, then tests over the APPROVED 74-span cut's side file. The approved tests need
the private data under HAD.DATA and FAIL LOUD when it is absent; they are never skipped. Pixel tests use only
the side file (origins, placed_at, sizes): no clamp arithmetic lives in this file."""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

import hebrew_aperture_diag as HAD

HERE = Path(__file__).resolve().parent
SET = "0401b636ffa7bf1a"
MANIFEST = HAD.DATA / ("truthset74_cut_%s.json" % SET)
SIDE = HAD.DATA / ("truthset74_cut_%s.realized.json" % SET)
BACKFILL = HERE / "realize_truth_set_cut.py"
N_TESTS = 16
W, H, PADV = 1000, 1500, 12


def _one(box, **kw):
    return HAD.realize_rects([box], (W, H), PADV, **kw)[0]


def test_no_clamp():
    r = _one([100, 200, 300, 260])
    assert r["pad_applied"] == {"l": 12, "t": 12, "r": 12, "b": 12}, r
    assert r["cut_rect"] == [88, 188, 312, 272] and r["native_origin"] == [88, 188]
    assert r["cut_wh"] == [224, 84] and r["dropped"] is False and r["placed_at"] == [0, 0]
    assert r["native_rect"] == [100, 200, 300, 260]


def test_left_clamp():
    r = _one([5, 200, 300, 260])
    assert r["pad_applied"]["l"] == 5 and r["native_origin"][0] == 0 and r["pad_applied"]["r"] == 12, r


def test_right_clamp():
    r = _one([100, 200, W - 3, 260])
    assert r["pad_applied"]["r"] == 3 and r["cut_rect"][2] == W and r["pad_applied"]["l"] == 12, r


def test_top_clamp():
    r = _one([100, 7, 300, 60])
    assert r["pad_applied"]["t"] == 7 and r["native_origin"][1] == 0 and r["pad_applied"]["b"] == 12, r


def test_bottom_clamp():
    r = _one([100, 1400, 300, H - 2])
    assert r["pad_applied"]["b"] == 2 and r["cut_rect"][3] == H and r["pad_applied"]["t"] == 12, r


def test_all_four_sides_clamped():
    r = _one([1, 2, W - 3, H - 4])
    assert r["pad_applied"] == {"l": 1, "t": 2, "r": 3, "b": 4}, r
    assert r["cut_rect"] == [0, 0, W, H] and r["cut_wh"] == [W, H]


def test_small_rect_dropped_and_ignored_by_size():
    rs = HAD.realize_rects([[100, 200, 300, 260], [500, 500, 501, 501]], (W, H), 0)
    # pad 0 makes the second box 1x1: dropped (a side <= 4), no placement, and not in the output size
    assert rs[1]["dropped"] is True and rs[1]["placed_at"] is None, rs[1]
    assert rs[0]["dropped"] is False
    assert HAD.realized_size(rs) == [200, 60], HAD.realized_size(rs)
    assert HAD.realized_size([rs[1]]) is None
    edge = HAD.realize_rects([[0, 0, 4, 50]], (W, H), 0)[0]
    assert edge["dropped"] is True, "a side of exactly 4 is dropped (the existing > 4 test)"


def test_two_rects_stacked():
    rs = HAD.realize_rects([[100, 200, 300, 260], [400, 700, 800, 790]], (W, H), PADV)
    h1 = rs[0]["cut_wh"][1]
    assert rs[0]["placed_at"] == [0, 0] and rs[1]["placed_at"] == [0, h1 + 20], rs
    w, h = HAD.realized_size(rs)
    assert w == max(rs[0]["cut_wh"][0], rs[1]["cut_wh"][0]) == 424
    assert h == h1 + 20 + rs[1]["cut_wh"][1]


# ---- the approved cut -------------------------------------------------------------------------------

def _side():
    assert SIDE.is_file(), "APPROVED side file missing (private data is required, never skipped): %s" % SIDE
    assert MANIFEST.is_file(), "APPROVED manifest missing: %s" % MANIFEST
    return json.loads(SIDE.read_text(encoding="utf-8"))


def _hdr(p):
    with Image.open(p) as im:
        return list(im.size)


def _arr(p):
    return np.asarray(Image.open(p).convert("L"))


def test_page_wh_equals_a_fresh_header_read():
    d = _side()
    assert len(d["rows"]) == 74, len(d["rows"])
    for r in d["rows"]:
        assert r["page_wh"] == _hdr(r["page_png"]), \
            "%s: recorded page_wh %s != header %s" % (r["span_id"], r["page_wh"], _hdr(r["page_png"]))


def test_realized_size_equals_png_size():
    d, n = _side(), 0
    for r in d["rows"]:
        for key in ("crop", "note_context"):
            c = r[key]
            if c is None:
                continue
            n += 1
            assert HAD.realized_size(c["rects"]) == c["size_wh"] == _hdr(c["path"]), \
                "%s %s: realized %s recorded %s png %s" % (r["span_id"], key, HAD.realized_size(c["rects"]),
                                                          c["size_wh"], _hdr(c["path"]))
    assert n >= 74, "only %d crops checked" % n


def test_span_pixels_sit_inside_note_pixels_single_rect():
    d, n = _side(), 0
    for r in d["rows"]:
        nc, sc = r["note_context"], r["crop"]
        if not nc or len(nc["rects"]) != 1 or len(sc["rects"]) != 1:
            continue
        N, S = _arr(nc["path"]), _arr(sc["path"])
        dx = sc["rects"][0]["native_origin"][0] - nc["rects"][0]["native_origin"][0]
        dy = sc["rects"][0]["native_origin"][1] - nc["rects"][0]["native_origin"][1]
        h, w = S.shape
        assert dx >= 0 and dy >= 0, (r["span_id"], dx, dy)
        sub = N[dy:dy + h, dx:dx + w]
        assert sub.shape == S.shape and np.array_equal(sub, S), "%s: span is not at (%d,%d)" % (r["span_id"], dx, dy)
        n += 1
    assert n >= 60, "only %d single-rect pairs checked" % n


def test_span_pixels_sit_inside_the_two_rect_note():
    d, n = _side(), 0
    for r in d["rows"]:
        nc, sc = r["note_context"], r["crop"]
        if not nc or len(nc["rects"]) < 2 or len(sc["rects"]) != 1:
            continue
        N, S = _arr(nc["path"]), _arr(sc["path"])
        s = sc["rects"][0]
        sx0, sy0, sx1, sy1 = s["cut_rect"]
        hosts = [q for q in nc["rects"] if not q["dropped"] and q["cut_rect"][0] <= sx0 and q["cut_rect"][1] <= sy0
                 and q["cut_rect"][2] >= sx1 and q["cut_rect"][3] >= sy1]
        assert len(hosts) == 1, "%s: %d note rects contain the span" % (r["span_id"], len(hosts))
        q = hosts[0]
        x = q["placed_at"][0] + s["native_origin"][0] - q["native_origin"][0]
        y = q["placed_at"][1] + s["native_origin"][1] - q["native_origin"][1]
        h, w = S.shape
        sub = N[y:y + h, x:x + w]
        assert sub.shape == S.shape and np.array_equal(sub, S), "%s: span is not at (%d,%d)" % (r["span_id"], x, y)
        n += 1
    assert n >= 1, "the approved set has a 2-rect note crop and none was checked"


def test_manifest_sha256_matches_the_bytes_on_disk():
    d = _side()
    assert d["manifest"] == MANIFEST.name
    assert d["manifest_sha256"] == hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    assert d["pad_requested"] == 12 and "page_wh" not in d


def test_no_row_carries_a_requested_pad():
    d = _side()
    def keys(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield k
                yield from keys(v)
        elif isinstance(o, list):
            for v in o:
                yield from keys(v)
    bad = {k for r in d["rows"] for k in keys(r) if k in ("pad_native_px", "pad_requested")}
    assert not bad, "rows carry the requested pad: %s" % bad


# ---- the backfill's refusals ------------------------------------------------------------------------

def _backfill(manifest):
    return subprocess.run([sys.executable, str(BACKFILL), str(manifest)], cwd=str(HERE), capture_output=True,
                          text=True, encoding="utf-8", timeout=300,
                          env=dict(__import__("os").environ, PYTHONIOENCODING="utf-8"))


def test_backfill_refuses_when_output_exists():
    _side()
    with tempfile.TemporaryDirectory() as td:
        m = Path(td) / MANIFEST.name
        shutil.copy(MANIFEST, m)
        out = Path(td) / (m.stem + ".realized.json")
        out.write_text("sentinel", encoding="utf-8")
        r = _backfill(m)
        assert r.returncode == 2 and "REFUSED" in r.stderr and "Traceback" not in r.stderr, (r.returncode, r.stderr[-300:])
        assert out.read_text(encoding="utf-8") == "sentinel"


def test_backfill_refuses_on_size_mismatch():
    _side()
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    row = next(b for b in man["rows"] if b.get("note_context"))
    row["note_context"]["native_rects"][0][2] += 30      # the crop PNG on disk is not this wide
    with tempfile.TemporaryDirectory() as td:
        m = Path(td) / MANIFEST.name
        m.write_text(json.dumps(man, ensure_ascii=False), encoding="utf-8")
        r = _backfill(m)
        assert r.returncode == 2 and row["span_id"] in r.stderr and "Traceback" not in r.stderr, (r.returncode, r.stderr[-300:])
        assert not (Path(td) / (m.stem + ".realized.json")).exists(), "a refused run wrote the side file"


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    assert len(fns) == N_TESTS, "found %d tests, expected %d" % (len(fns), N_TESTS)
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed")
    raise SystemExit(1 if f or p != N_TESTS else 0)
