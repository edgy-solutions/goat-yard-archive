"""render_body_console / score_body_console born-tests: constructed hunks and a synthetic page PNG
in a temp dir; no model, no private data. Run: python test_render_body_console.py

EXPECTED_TESTS asserts the suite's OWN test count so a silently-dropped test fails the run.
"""
import json
import shutil
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

import build_body_shadow as BSB
import render_body_console as RBC
import score_body_console as SBC

EXPECTED_TESTS = 10


def hunk(fp, idx, cls, nl=False):
    return {"kind": "hunk", "file_page": fp, "opcode_idx": idx, "class": cls,
            "flags": {"non_latin": nl, "marker": False, "chunk_edge": False},
            "old_text": f"alpha{idx}", "new_text": f"beta{idx}",
            "old_before": "x y", "old_after": "z", "new_before": "x y", "new_after": "z",
            "chunk": {"box": [0, 0, 40, 30], "file_page": fp, "col": "left", "rect_idx": 0,
                      "chunk_idx": 0, "key": [fp, "left", 1], "stage1_line": 1}}


def population():
    hs = [hunk(90, i, "disputed_head") for i in range(3)]
    hs += [hunk(90, 10 + i, "verse_boundary") for i in range(15)]
    for fp in (90, 91):
        hs += [hunk(fp, 100 + i, "content", nl=(i % 2 == 0)) for i in range(8)]
    hs += [hunk(92, 200 + i, "content") for i in range(6)]          # a page with Latin-only content
    hs += [hunk(91, 300 + i, "ws_punct") for i in range(12)]
    return hs


def test_sample_is_deterministic_in_seed():
    hs = population()
    a1 = RBC.build_cards(RBC.sample_hunks(hs, 7), 7)
    a2 = RBC.build_cards(RBC.sample_hunks(list(reversed(hs)), 7), 7)
    assert [(c["card_id"], c["old_side"], c["stratum"]) for c in a1] == \
           [(c["card_id"], c["old_side"], c["stratum"]) for c in a2]
    b = RBC.build_cards(RBC.sample_hunks(hs, 8), 8)
    # the coin for the SAME hunk (page, opcode) differs somewhere between seeds
    sides = lambda cs: {(c["file_page"], c["opcode_idx"]): c["old_side"] for c in cs}
    sa, sb = sides(a1), sides(b)
    common = set(sa) & set(sb)
    assert common and any(sa[k] != sb[k] for k in common)
    assert {c["card_id"] for c in a1}.isdisjoint({c["card_id"] for c in b})


def test_card_id_is_sha16_of_page_opcode_seed():
    import hashlib
    assert RBC.card_id_for(90, 12, 5) == hashlib.sha256(b"90:12:5").hexdigest()[:16]
    assert RBC.card_id_for(90, 12, 5) != RBC.card_id_for(90, 12, 6)


def test_strata_caps_and_balance():
    s = RBC.sample_hunks(population(), 3)
    by = {}
    for st, h in s:
        by.setdefault(st, []).append(h)
    assert len(by["disputed_head"]) == 3                      # every one
    assert len(by["verse_boundary"]) == 10                    # capped
    assert len(by["ws_punct"]) == 5                           # capped
    for fp in (90, 91):
        cs = [h for h in by["content"] if h["file_page"] == fp]
        assert len(cs) == 3 and 1 <= sum(h["flags"]["non_latin"] for h in cs) <= 2, fp
    assert len([h for h in by["content"] if h["file_page"] == 92]) == 3
    assert len(by["content"]) == 9
    # fewer available than the cap: take what exists
    few = RBC.sample_hunks([hunk(90, 1, "verse_boundary"), hunk(90, 2, "ws_punct")], 1)
    assert [st for st, _ in few] == ["verse_boundary", "ws_punct"]


def test_ab_texts_follow_the_coin():
    cards = RBC.build_cards(RBC.sample_hunks(population(), 3), 3)
    seen = set()
    for c in cards:
        old, new = f"alpha{c['opcode_idx']}", f"beta{c['opcode_idx']}"
        assert (c["A"]["text"], c["B"]["text"]) == ((old, new) if c["old_side"] == "A" else (new, old))
        seen.add(c["old_side"])
    assert seen == {"A", "B"}


def _make_run(d, seed=11):
    """A page PNG, a body header carrying its sha, and a diff with a few hunks."""
    vol = d / "vol"
    vol.mkdir()
    page = np.full((300, 400), 255, np.uint8)
    page[50:60, 20:200] = 0
    Image.fromarray(page).save(vol / "page90_image1.png")
    sha = BSB.png_sha256(vol, 90)
    body = d / "body.jsonl"
    body.write_text(json.dumps({"kind": "run_header", "config_hash": "bodyhash",
                                "config": {"png_sha256": {"90": sha}}}) + "\n", encoding="utf-8")
    hs = [hunk(90, 1, "disputed_head"), hunk(90, 2, "content", True), hunk(90, 3, "ws_punct")]
    for h in hs:
        h["chunk"]["box"] = [10, 40, 210, 70]
    diff = d / "diff.jsonl"
    rows = [{"kind": "diff_header", "config_hash": "diffhash", "config": {"body_config_hash": "bodyhash"}}] + hs
    diff.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return vol, body, diff


def test_main_writes_blinded_html_crops_and_separate_key():
    d = Path(tempfile.mkdtemp(prefix="rbc_test_"))
    try:
        vol, body, diff = _make_run(d)
        out = d / "console"
        assert RBC.main(["--diff", str(diff), "--body", str(body), "--volume-dir", str(vol),
                         "--out-dir", str(out), "--seed", "11"]) == 0
        html = (out / "index.html").read_text(encoding="utf-8")
        low = html.lower()
        assert "old" not in low and "new" not in low, "the page must not label a side old/new"
        assert "key.json" not in low and str(out).lower() not in low and "old_side" not in low
        assert "<script src" not in low and "http://" not in low.replace("http://www.w3.org", "")
        key = json.loads((out / "key.json").read_text(encoding="utf-8"))
        assert key["seed"] == 11 and len(key["cards"]) == 3
        for cid, meta in key["cards"].items():
            assert cid in html and meta["old_side"] in ("A", "B")
            png = out / "crops" / f"{cid}.png"
            assert Image.open(png).size == (200, 30), "the crop is native resolution"
        assert "alpha1" in html and "beta1" in html
        assert "A matches page" in html and "can't tell" in __import__("html").unescape(html) and "Export JSONL" in html
        assert "localStorage" in html
        # never clobbers a finished console
        assert RBC.main(["--diff", str(diff), "--body", str(body), "--volume-dir", str(vol),
                         "--out-dir", str(out), "--seed", "11"]) == 2
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_main_refuses_diff_from_a_different_body_run():
    d = Path(tempfile.mkdtemp(prefix="rbc_test_"))
    try:
        vol, body, diff = _make_run(d)
        body.write_text(json.dumps({"kind": "run_header", "config_hash": "OTHER",
                                    "config": {"png_sha256": {}}}) + "\n", encoding="utf-8")
        try:
            RBC.main(["--diff", str(diff), "--body", str(body), "--volume-dir", str(vol),
                      "--out-dir", str(d / "c"), "--seed", "1"])
        except ValueError as e:
            assert "different body run" in str(e)
        else:
            raise AssertionError("must refuse")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_main_refuses_when_page_png_differs_from_the_read_pixels():
    d = Path(tempfile.mkdtemp(prefix="rbc_test_"))
    try:
        vol, body, diff = _make_run(d)
        Image.fromarray(np.full((300, 400), 200, np.uint8)).save(vol / "page90_image1.png")
        try:
            RBC.main(["--diff", str(diff), "--body", str(body), "--volume-dir", str(vol),
                      "--out-dir", str(d / "c"), "--seed", "1"])
        except ValueError as e:
            assert "page 90" in str(e)
        else:
            raise AssertionError("must refuse")
        assert not (d / "c" / "index.html").exists()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_score_mapping_on_a_synthetic_export():
    key = {"cards": {
        "c1": {"old_side": "A", "stratum": "content"},   # A=old
        "c2": {"old_side": "B", "stratum": "content"},   # A=new
        "c3": {"old_side": "A", "stratum": "content"},
        "c4": {"old_side": "A", "stratum": "ws_punct"},
        "c5": {"old_side": "B", "stratum": "ws_punct"},
        "c6": {"old_side": "B", "stratum": "disputed_head"},
        "c7": {"old_side": "A", "stratum": "disputed_head"},   # never answered
    }}
    rows = [{"card_id": "c1", "verdict": "A"},          # A=old matches -> new_wrong
            {"card_id": "c2", "verdict": "A"},          # A=new matches -> old_wrong
            {"card_id": "c3", "verdict": "B"},          # B=new matches -> old_wrong
            {"card_id": "c4", "verdict": "both"},       # equivalent
            {"card_id": "c5", "verdict": "neither"},    # both_differ_from_page
            {"card_id": "c6", "verdict": "cant_tell"}]
    s = SBC.score(rows, key)
    assert s["content"] == {"old_wrong": 2, "new_wrong": 1, "both_differ_from_page": 0,
                            "equivalent": 0, "cant_tell": 0, "unanswered": 0}
    assert s["ws_punct"]["equivalent"] == 1 and s["ws_punct"]["both_differ_from_page"] == 1
    assert s["disputed_head"]["cant_tell"] == 1 and s["disputed_head"]["unanswered"] == 1
    assert SBC.outcome("B", "B") == "new_wrong" and SBC.outcome("B", "A") == "old_wrong"


def test_score_refuses_bad_exports():
    key = {"cards": {"c1": {"old_side": "A", "stratum": "content"}}}
    for rows, needle in (([{"card_id": "zz", "verdict": "A"}], "zz"),
                         ([{"card_id": "c1", "verdict": "A"}, {"card_id": "c1", "verdict": "B"}], "repeats"),
                         ([{"card_id": "c1", "verdict": "maybe"}], "maybe")):
        try:
            SBC.score(rows, key)
        except ValueError as e:
            assert needle in str(e)
        else:
            raise AssertionError(f"must refuse {rows}")


def test_end_to_end_blinding_round_trip():
    # render -> a reader answering "the side that carries the NEW text matches the page" on every
    # card -> the scorer must report old_wrong for all of them, whatever the coin said
    d = Path(tempfile.mkdtemp(prefix="rbc_test_"))
    try:
        vol, body, diff = _make_run(d)
        out = d / "console"
        RBC.main(["--diff", str(diff), "--body", str(body), "--volume-dir", str(vol),
                  "--out-dir", str(out), "--seed", "21"])
        key = json.loads((out / "key.json").read_text(encoding="utf-8"))
        rows = [{"card_id": cid, "verdict": "B" if m["old_side"] == "A" else "A"}
                for cid, m in key["cards"].items()]
        s = SBC.score(rows, key)
        assert sum(v["old_wrong"] for v in s.values()) == 3
        assert sum(v["new_wrong"] for v in s.values()) == 0
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
