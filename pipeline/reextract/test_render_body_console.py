"""render_body_console / score_body_console born-tests: constructed hunks and a synthetic page PNG
in a temp dir; no model, no private data. Run: python test_render_body_console.py

EXPECTED_TESTS asserts the suite's OWN test count so a silently-dropped test fails the run.
"""
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

import body_read
import build_body_shadow as BSB
import render_body_console as RBC
import score_body_console as SBC

EXPECTED_TESTS = 35


def hunk(fp, idx, cls, nl=False):
    return {"kind": "hunk", "file_page": fp, "opcode_idx": idx, "class": cls,
            "flags": {"non_latin": nl, "marker": False, "chunk_edge": False},
            "old_text": f"alpha{idx}", "new_text": f"beta{idx}",
            "old_before": "x y", "old_after": "z", "new_before": "x y", "new_after": "z",
            "chunk": {"box": [0, 0, 40, 30], "file_page": fp, "col": "left", "rect_idx": 0,
                      "chunk_idx": 0, "key": [fp, "left", 1], "stage1_line": 1},
            "span_chunks": [{"box": [0, 0, 40, 30], "file_page": fp, "col": "left", "rect_idx": 0,
                             "chunk_idx": 0, "key": [fp, "left", 1], "stage1_line": 1}],
            "ends_on_chunk_last_line": False}


def ref(box, ci=0, ri=0, fp=90):
    return {"box": box, "file_page": fp, "col": "left", "rect_idx": ri, "chunk_idx": ci,
            "key": [fp, "left", 1], "stage1_line": 1}


def with_span(h, boxes):
    h["span_chunks"] = [ref(b, ci=i) for i, b in enumerate(boxes)]
    return h


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
        h["span_chunks"][0]["box"] = [10, 40, 210, 70]
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
        assert "crops.json" not in low
        cj = (out / "crops.json").read_text(encoding="utf-8")
        assert "old" not in cj.lower() and "new" not in cj.lower() and "alpha" not in cj
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
        # a carried export row ({"carried": true}) is harmless to the scorer's row handling
        rows2 = [dict(r, carried=True) for r in rows]
        assert SBC.score(rows2, key) == s
        crops = json.loads((out / "crops.json").read_text(encoding="utf-8"))
        assert SBC.score(rows, key, crops) == {k: dict(v, not_cardable=0) for k, v in s.items()}
        for t in (html_low := (out / "index.html").read_text(encoding="utf-8").lower(),):
            assert "old" not in t and "new" not in t
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _run_one(d, hunks, shape=(300, 400), seed=5, crop_box_for_png=None):
    """Console over `hunks` (all on page 90) on a gray gradient page; -> (out, rc, gray)."""
    vol = d / "vol"
    vol.mkdir(exist_ok=True)
    page = (np.arange(shape[0] * shape[1], dtype=np.int64).reshape(shape) % 251).astype(np.uint8)
    Image.fromarray(page).save(vol / "page90_image1.png")
    body = d / "body.jsonl"
    body.write_text(json.dumps({"kind": "run_header", "config_hash": "bodyhash", "config": {
        "png_sha256": {"90": BSB.png_sha256(vol, 90)}}}) + "\n", encoding="utf-8")
    diff = d / "diff.jsonl"
    rows = [{"kind": "diff_header", "config_hash": "diffhash", "config": {"body_config_hash": "bodyhash"}}] + hunks
    diff.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    out = d / "console"
    rc = RBC.main(["--diff", str(diff), "--body", str(body), "--volume-dir", str(vol),
                   "--out-dir", str(out), "--seed", str(seed)])
    return out, rc, page


def _inside(inner, outer):
    return outer[0] <= inner[0] and outer[1] <= inner[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


def test_born_card2_cover_is_union_and_the_old_crop_missed_the_second_read_box():
    h = with_span(hunk(90, 2, "content"), [[1660, 2101, 3584, 2365], [0, 2523, 3584, 2581]])
    h["chunk"]["box"] = [1660, 2101, 3584, 2365]
    cov = RBC.cover_for(h)
    assert cov["cardable"] and cov["reason"] is None and cov["cover_box"] == [0, 2101, 3584, 2581]
    assert len(cov["read_crops"]) == 2
    (card,) = RBC.build_cards([("content", h)], 1)
    assert card["carry_eligible"] is False
    # the defect, documented: the single crop the console used to cut does not hold read box 2
    assert not _inside(h["span_chunks"][1]["box"], h["chunk"]["box"])
    assert _inside(h["span_chunks"][1]["box"], cov["cover_box"])


def _bands(rows, shape=(400, 300), thin=()):
    g = np.full(shape, 255, np.uint8)
    for a, b in list(rows) + list(thin):
        g[a:b, 10:290] = 0
    return g


def _ext_hunk(boxes, ends=True):
    h = with_span(hunk(90, 1, "content"), boxes)
    h["ends_on_chunk_last_line"] = ends
    return h


def test_extend_down_clipped_line_goes_to_end_of_next_line():
    g = _bands([(20, 40), (60, 80), (100, 120)])
    assert RBC.extend_down(g, [5, 10, 295, 70]) == ([5, 10, 295, 120], None)


def test_extend_down_no_line_below_ends_clipped_line():
    g = _bands([(20, 40), (60, 80)])
    assert RBC.extend_down(g, [5, 10, 295, 70]) == ([5, 10, 295, 80], "no_line_below")
    assert RBC.extend_down(g, [5, 10, 295, 100]) == ([5, 10, 295, 100], "no_line_below"), "never shrinks"


def test_extend_down_blank_cover_is_unchanged_and_flagged():
    g = _bands([(200, 220)])
    assert RBC.extend_down(g, [5, 10, 295, 70]) == ([5, 10, 295, 70], "no_line_in_cover")


def test_extend_down_thin_rule_is_not_the_next_line():
    g = _bands([(20, 40), (60, 80), (120, 140)], thin=[(90, 96)])
    assert body_read._ink_lines(g, (0, 0, 300, 400)) == [(20, 40), (60, 80), (90, 96), (120, 140)]
    assert RBC.extend_down(g, [5, 10, 295, 70]) == ([5, 10, 295, 140], None)


def test_extension_trigger_requires_the_bottom_chunk_to_hold_the_end():
    top, bottom = [0, 0, 300, 70], [0, 40, 300, 130]
    h = _ext_hunk([bottom, top])          # last token's chunk is `top`: bottom edge is bottom's
    assert not RBC.triggers_extension(h, RBC.cover_for(h)["cover_box"])
    h = _ext_hunk([top, bottom])
    assert RBC.triggers_extension(h, RBC.cover_for(h)["cover_box"])
    h = _ext_hunk([top, bottom], ends=False)
    assert not RBC.triggers_extension(h, RBC.cover_for(h)["cover_box"])
    h = _ext_hunk([top, bottom], ends=None)
    assert not RBC.triggers_extension(h, RBC.cover_for(h)["cover_box"])
    (card,) = RBC.build_cards([("content", _ext_hunk([bottom, top]))], 1)
    assert card["trigger_candidate"] is False
    (card,) = RBC.build_cards([("content", _ext_hunk([top, bottom]))], 1)
    assert card["trigger_candidate"] is True


def test_too_tall_applies_after_extension():
    mx = RBC.COVER_MAX_H
    g = _bands([(10, 30), (mx - 20, mx + 10), (mx + 40, mx + 70)], shape=(mx + 400, 300))
    h = _ext_hunk([[0, 0, 300, mx]])
    (card,) = RBC.build_cards([("content", h)], 1)
    assert card["cover"]["cardable"]
    RBC.settle_card(card, g)
    assert card["extension"]["triggered"] and card["extension"]["to_y1"] == mx + 70
    assert not card["cover"]["cardable"] and card["cover"]["reason"] == "too_tall"
    assert card["cover"]["cover_box"] == [0, 0, 300, mx + 70]


def test_extended_card_is_not_carry_eligible_and_crop_bytes_follow_final_box():
    d = Path(tempfile.mkdtemp(prefix="rbc_test_"))
    try:
        g = _bands([(20, 40), (60, 80), (100, 120)])
        vol = d / "vol"
        vol.mkdir()
        Image.fromarray(g).save(vol / "page90_image1.png")
        body = d / "body.jsonl"
        body.write_text(json.dumps({"kind": "run_header", "config_hash": "bodyhash", "config": {
            "png_sha256": {"90": BSB.png_sha256(vol, 90)}}}) + "\n", encoding="utf-8")
        h = _ext_hunk([[10, 10, 290, 70]])
        h["chunk"] = dict(h["span_chunks"][0])
        plain = _ext_hunk([[10, 10, 290, 70]], ends=False)
        plain["opcode_idx"] = 2
        plain["chunk"] = dict(plain["span_chunks"][0])
        diff = d / "diff.jsonl"
        rows = [{"kind": "diff_header", "config_hash": "diffhash",
                 "config": {"body_config_hash": "bodyhash"}}, h, plain]
        diff.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        out = d / "console"
        assert RBC.main(["--diff", str(diff), "--body", str(body), "--volume-dir", str(vol),
                         "--out-dir", str(out), "--seed", "5"]) == 0
        cj = json.loads((out / "crops.json").read_text(encoding="utf-8"))
        c1, c2 = RBC.card_id_for(90, 1, 5), RBC.card_id_for(90, 2, 5)
        assert cj[c1]["cover_box"] == [10, 10, 290, 120] and cj[c1]["carry_eligible"] is False
        assert cj[c1]["extension"] == {"rule": "one_line_down_v1", "triggered": True, "flag": None,
                                       "from_y1": 70, "to_y1": 120}
        assert (out / "crops" / f"{c1}.png").read_bytes() == BSB.crop_png_bytes(g, [10, 10, 290, 120])
        assert cj[c2]["carry_eligible"] is True and cj[c2]["cover_box"] == [10, 10, 290, 70]
        assert cj[c2]["extension"] == {"rule": "one_line_down_v1", "triggered": False, "flag": None,
                                       "from_y1": 70, "to_y1": 70}
        html = (out / "index.html").read_text(encoding="utf-8")
        assert f'data-id="{c1}" data-carry="0"' in html
        assert "height:54.5455%" in html, "outline = 60 of the 110 px final image"
        assert "extension" not in html
        key = json.loads((out / "key.json").read_text(encoding="utf-8"))
        assert set(key["cards"][c1]) == {"old_side", "stratum", "file_page", "opcode_idx"}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_hunk_without_ends_on_chunk_last_line_is_refused():
    h = hunk(90, 1, "content")
    del h["ends_on_chunk_last_line"]
    try:
        RBC.cover_for(h)
    except ValueError as e:
        assert "ends_on_chunk_last_line" in str(e)
    else:
        raise AssertionError("cover_for must refuse")
    try:
        RBC.build_cards([("content", h)], 1)
    except ValueError:
        pass
    else:
        raise AssertionError("build_cards must refuse")


def test_delete_is_not_cardable_has_no_crop_and_is_listed():
    d = Path(tempfile.mkdtemp(prefix="rbc_test_"))
    try:
        dele = hunk(90, 1, "content")
        dele["span_chunks"] = []
        keep = hunk(90, 2, "content")
        out, rc, _ = _run_one(d, [dele, keep])
        assert rc == 0
        cid_d = RBC.card_id_for(90, 1, 5)
        cid_k = RBC.card_id_for(90, 2, 5)
        assert not (out / "crops" / f"{cid_d}.png").exists() and (out / "crops" / f"{cid_k}.png").exists()
        cj = json.loads((out / "crops.json").read_text(encoding="utf-8"))
        assert cj[cid_d]["cardable"] is False and cj[cid_d]["reason"] == "old_only"
        assert cj[cid_d]["cover_box"] is None and cj[cid_d]["read_crops"] == []
        html = (out / "index.html").read_text(encoding="utf-8")
        assert f'data-id="{cid_d}"' not in html and f'data-id="{cid_k}"' in html
        tail = html.split("Not cardable", 1)[1]
        assert cid_d in tail and "no read crop contains this text" in tail and cid_k not in tail
        assert "alpha1" not in html and "beta1" not in html, "no texts for a not-cardable hunk"
        assert "#1 " in tail
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_too_tall_cover_is_not_cardable():
    h = with_span(hunk(90, 1, "content"), [[0, 0, 100, 100], [0, RBC.COVER_MAX_H, 100, RBC.COVER_MAX_H + 50]])
    cov = RBC.cover_for(h)
    assert not cov["cardable"] and cov["reason"] == "too_tall"
    assert cov["cover_box"] == [0, 0, 100, RBC.COVER_MAX_H + 50]
    ok = with_span(hunk(90, 1, "content"), [[0, 0, 100, 100], [0, RBC.COVER_MAX_H - 100, 100, RBC.COVER_MAX_H]])
    assert RBC.cover_for(ok)["cardable"], "exactly COVER_MAX_H is allowed"


def test_single_chunk_cover_equals_chunk_and_crop_bytes_identical():
    d = Path(tempfile.mkdtemp(prefix="rbc_test_"))
    try:
        h = hunk(90, 1, "content")
        h["chunk"]["box"] = h["span_chunks"][0]["box"] = [10, 40, 210, 70]
        (card,) = RBC.build_cards([("content", h)], 5)
        assert card["cover"]["cover_box"] == h["chunk"]["box"] and card["carry_eligible"] is True
        out, rc, page = _run_one(d, [h])
        want = BSB.crop_png_bytes(page, [10, 40, 210, 70])
        assert (out / "crops" / f"{card['card_id']}.png").read_bytes() == want
        html = (out / "index.html").read_text(encoding="utf-8")
        assert 'data-carry="1"' in html and 'data-carry="0"' not in html and "read crops: 1" in html
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_missing_span_chunks_is_refused_and_nothing_is_written():
    d = Path(tempfile.mkdtemp(prefix="rbc_test_"))
    try:
        h = hunk(90, 1, "content")
        del h["span_chunks"]
        try:
            RBC.cover_for(h)
        except ValueError as e:
            assert "span_chunks" in str(e)
        else:
            raise AssertionError("cover_for must refuse")
        try:
            _run_one(d, [h])
        except ValueError as e:
            assert "span_chunks" in str(e)
        else:
            raise AssertionError("main must refuse")
        out = d / "console"
        assert not (out / "index.html").exists() and not (out / "key.json").exists()
        assert not (out / "crops.json").exists() and not list(out.glob("crops/*"))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_crops_json_shas_are_of_the_bytes_stage2_sent_and_carry_no_text():
    d = Path(tempfile.mkdtemp(prefix="rbc_test_"))
    try:
        h = with_span(hunk(90, 2, "content"), [[20, 100, 380, 160], [0, 200, 400, 230]])
        h["chunk"]["box"] = [20, 100, 380, 160]
        out, rc, page = _run_one(d, [h])
        cid = RBC.card_id_for(90, 2, 5)
        cj = json.loads((out / "crops.json").read_text(encoding="utf-8"))
        e = cj[cid]
        assert e["cardable"] and e["cover_box"] == [0, 100, 400, 230] and e["carry_eligible"] is False
        assert [r["box"] for r in e["read_crops"]] == [[20, 100, 380, 160], [0, 200, 400, 230]]
        for r in e["read_crops"]:
            assert r["sha256"] == hashlib.sha256(BSB.crop_png_bytes(page, r["box"])).hexdigest()
            assert set(r) == {"key", "stage1_line", "chunk_idx", "rect_idx", "box", "sha256"}
        assert set(e) == {"cardable", "reason", "cover_box", "carry_eligible", "extension", "read_crops"}
        raw = (out / "crops.json").read_text(encoding="utf-8").lower()
        assert "old_side" not in raw and "old" not in raw and "new" not in raw and "alpha" not in raw
        assert Image.open(out / "crops" / f"{cid}.png").size == (400, 130)
        key = json.loads((out / "key.json").read_text(encoding="utf-8"))
        assert set(key) == {"seed", "diff_config_hash", "render_rules", "cards"}
        assert set(key["cards"][cid]) == {"old_side", "stratum", "file_page", "opcode_idx"}
        html = (out / "index.html").read_text(encoding="utf-8")
        assert "read crops: 2" in html and 'class="ol"' in html and "<i>2</i>" in html
        assert "left:5.0000%" in html and "top:0.0000%" in html      # outline 1, relative to the cover
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_html_namespaces_verdicts_and_offers_carry_import():
    d = Path(tempfile.mkdtemp(prefix="rbc_test_"))
    try:
        one = hunk(90, 1, "content")
        one["chunk"]["box"] = one["span_chunks"][0]["box"] = [10, 40, 210, 70]
        two = with_span(hunk(90, 2, "content"), [[20, 100, 380, 160], [0, 200, 400, 230]])
        two["chunk"]["box"] = [20, 100, 380, 160]
        out, rc, _ = _run_one(d, [one, two])
        html = (out / "index.html").read_text(encoding="utf-8")
        assert "'verdict:'+CONSOLE+':'" in html and "var CONSOLE=\"console\"" in html
        assert "'verdict:'+id" not in html and "'verdict:'+card" not in html
        assert html.count('data-carry="1"') == 1 and html.count('data-carry="0"') == 1
        assert 'id="import"' in html and "Import previous verdicts" in html
        assert "carried from previous console" in html and "carried:carried(id)" in html
        assert "applied '+applied" in html and "discarded" in html
        assert "outlined crop" in html and "whole page image" in html
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_score_crops_puts_not_cardable_in_their_own_bucket():
    key = {"cards": {"c1": {"old_side": "A", "stratum": "content"},
                     "c2": {"old_side": "A", "stratum": "content"},
                     "c3": {"old_side": "A", "stratum": "content"}}}
    crops = {"c1": {"cardable": True}, "c2": {"cardable": False, "reason": "old_only"},
             "c3": {"cardable": True}}
    rows = [{"card_id": "c1", "verdict": "A", "carried": True}]
    s = SBC.score(rows, key, crops)["content"]
    assert s["not_cardable"] == 1 and s["unanswered"] == 1 and s["new_wrong"] == 1
    plain = SBC.score(rows, key)["content"]
    assert "not_cardable" not in plain and plain["unanswered"] == 2, "without --crops: unchanged"


def test_neutralize_makes_every_mark_form_display_identically():
    n = RBC.NEUTRAL_MARK
    for t in ("word[^3] next", "word^a^ next", "word ^a next", "word^1^ next"):
        assert RBC.neutralize(t) == f"word{n} next", t
    assert RBC.neutralize("word ^. next") == f"word{n}. next"
    assert RBC.neutralize("no mark here, 3 words.") == "no mark here, 3 words."


def test_marker_only_rule():
    assert RBC.marker_only("of God[^3] and", "of God^b^ and") is True
    assert RBC.marker_only("Lord[^1].", "Lord ^c.") is True
    assert RBC.marker_only("Jarchi[^2]", "Jarcin^b^") is False
    assert RBC.marker_only("a  b", "a b") is False, "whitespace only, no mark"
    assert RBC.marker_only("same[^1]", "same[^1]") is False


def test_cover_for_refuses_a_marker_only_hunk():
    h = hunk(90, 1, "content")
    h["old_text"], h["new_text"] = "of God[^3] and", "of God^b^ and"
    cov = RBC.cover_for(h)
    assert cov["cardable"] is False and cov["reason"] == "marker_only" and cov["read_crops"] == []
    assert "marker_only" in RBC._REASON and "old" not in RBC._REASON["marker_only"].lower()         and "new" not in RBC._REASON["marker_only"].lower()


def _marked_hunks():
    h = hunk(90, 1, "content")
    h["old_text"], h["new_text"] = "alpha[^4] one", "beta^d^ one"
    h["old_before"], h["new_before"] = "x[^4] y", "x ^d y"
    for k in ("chunk",):
        h[k]["box"] = [10, 40, 210, 70]
    h["span_chunks"][0]["box"] = [10, 40, 210, 70]
    return [h]


def test_rendered_page_has_no_mark_format_and_shows_the_neutral_token():
    d = Path(tempfile.mkdtemp(prefix="rbc_test_"))
    try:
        out, rc, _ = _run_one(d, _marked_hunks())
        assert rc == 0
        html = (out / "index.html").read_text(encoding="utf-8")
        assert RBC.leak_check(html) == []
        assert RBC.NEUTRAL_MARK in html and "[^" not in html
        key = json.loads((out / "key.json").read_text(encoding="utf-8"))
        assert key["render_rules"] == {"marker": "marker_any_v1", "neutral_token": RBC.NEUTRAL_MARK,
                                       "marker_only": "marker_only_v1", "leak_check": "leak_v1"}
        assert set(key) == {"seed", "diff_config_hash", "render_rules", "cards"}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_leak_check_sees_each_form_and_static_page_parts_are_clean():
    assert RBC.leak_check("a [^3] b") == ["[^"]
    assert RBC.leak_check("a ^b^ c") == ["^b"]
    assert RBC.leak_check("clean") == []
    assert RBC.leak_check(RBC._CSS + RBC._JS) == []


def test_build_refuses_and_leaves_nothing_when_a_mark_would_leak():
    d = Path(tempfile.mkdtemp(prefix="rbc_test_"))
    orig = RBC.neutralize
    try:
        RBC.neutralize = lambda t: t
        out, rc, _ = _run_one(d, _marked_hunks())
        assert rc == 3
        assert not out.exists(), "a refused build leaves no out-dir"
    finally:
        RBC.neutralize = orig
        shutil.rmtree(d, ignore_errors=True)


def test_a_card_with_a_mark_in_view_is_not_carry_eligible():
    h = hunk(90, 1, "content")
    h["old_before"] = "x[^4] y"
    card = RBC.build_cards([("content", h)], 5)[0]
    assert card["carry_eligible"] is True, "before settle: unchanged"
    assert RBC.settle_card(card, None)["carry_eligible"] is False
    clean = RBC.build_cards([("content", hunk(90, 2, "content"))], 5)[0]
    assert RBC.settle_card(clean, None)["carry_eligible"] is True


def test_marker_only_hunk_is_listed_not_cardable_in_a_real_run():
    d = Path(tempfile.mkdtemp(prefix="rbc_test_"))
    try:
        h = hunk(90, 1, "content")
        h["old_text"], h["new_text"] = "of God[^3] and", "of God^b^ and"
        h["span_chunks"][0]["box"] = h["chunk"]["box"] = [10, 40, 210, 70]
        out, rc, _ = _run_one(d, [h])
        assert rc == 0
        cj = json.loads((out / "crops.json").read_text(encoding="utf-8"))
        cid = RBC.card_id_for(90, 1, 5)
        assert cj[cid]["cardable"] is False and cj[cid]["reason"] == "marker_only"
        assert not (out / "crops" / f"{cid}.png").exists()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_score_reads_only_cards_from_key():
    import inspect
    src = inspect.getsource(SBC)
    assert "render_rules" not in src


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
