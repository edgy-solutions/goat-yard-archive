"""new_side_norm born-tests: pure strings and a synthetic body JSONL in a temp dir; no model, no
private data. Run: python test_new_side_norm.py

EXPECTED_TESTS asserts the suite's OWN test count so a silently-dropped test fails the run.
"""
import copy
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import new_side_norm as N

EXPECTED_TESTS = 21


def _canon(t):
    return N.canon_marks(t)


def test_marks_unclosed_colon():
    out, e = _canon("things^s:")
    assert out == "things^s^:" and e[0]["kind"] == "format"
    assert e[0]["from"] == "^s" and e[0]["to"] == "^s^" and e[0]["rule"] == "marker_format_v1"


def test_marks_never_cross_a_line_break():
    # a mark at a line start stays on its line: whitespace absorbed is [ \t] only
    out, e = _canon("word\n^c, next")
    assert out == "word\n^c^, next", out
    assert all("\n" not in x["from"] for x in e)
    out2, _ = _canon("word \n ^:")
    assert out2 == "word \n^?^:", out2


def test_marks_bare_caret_letter_missing():
    out, e = _canon("world ^:")
    assert out == "world^?^:" and [x["kind"] for x in e] == ["letter_missing"]


def test_marks_numeric_kept():
    out, e = _canon("assert ^2^,")
    assert out == "assert^2^," and e[0]["kind"] == "numeric"


def test_marks_unclosed_comma():
    out, e = _canon("say^c,")
    assert out == "say^c^," and e[0]["kind"] == "format"


def test_marks_before_semicolon_step():
    out, e = _canon("&c. ^a^;")
    assert out == "&c.^a^;" and len(e) == 1 and e[0]["at"] == 3


def test_marks_uppercase_kept():
    out, e = _canon("Josephus^S")
    assert "S" in out and "s" not in out.replace("Josephus", "") and e[0]["kind"] == "uppercase"


def test_marks_no_caret_identical():
    t = "plain text, no marks; here"
    out, e = _canon(t)
    assert out == t and e == []


def test_marks_unrecognized_unchanged():
    out, e = _canon("a^bc")
    assert out == "a^bc" and [x["kind"] for x in e] == ["unrecognized"]
    assert e[0]["from"] == e[0]["to"]


def test_marks_canonical_no_edit():
    out, e = _canon("word^a^ more")
    assert out == "word^a^ more" and e == []


def test_marks_letter_never_changed():
    for letter in "abjvJV":
        out, _ = _canon(f"x ^{letter}^.")
        assert out == f"x^{letter}^."


def test_semicolon_inserts_space():
    out, e = N.semicolon_space("him;")
    assert out == "him ;" and len(e) == 1


def test_semicolon_collapses_spaces():
    out, e = N.semicolon_space("mercies  ;")
    assert out == "mercies ;" and len(e) == 1 and e[0]["from"] == "  ;"
    out2, e2 = N.semicolon_space("a \t ;")
    assert out2 == "a ;" and len(e2) == 1


def test_semicolon_already_spaced_no_edit():
    out, e = N.semicolon_space("him ;")
    assert out == "him ;" and e == []


def test_semicolon_line_start_untouched():
    assert N.semicolon_space(";start") == (";start", [])
    assert N.semicolon_space("a\n;b") == ("a\n;b", [])


def test_normalize_composition():
    out, e = N.normalize("&c. ^a^;")
    assert out == "&c.^a^ ;"
    assert [x["step"] for x in e] == [1, 2]
    assert [x["rule"] for x in e] == ["marker_format_v1", "space_before_semicolon_v1"]


def test_chain_flags_and_proposes_without_editing():
    text = "one^a^ two^b^ three^d^"
    pages = [{"file_page": 7, "text": text}]
    before = copy.deepcopy(pages)
    recs = N.chain_check(pages)
    assert pages == before and pages[0]["text"] == text   # input untouched, d still read
    r = recs[0]
    assert r["kind"] == "marker_chain_page" and r["letters_read"] == ["a", "b", "d"]
    assert r["flags"] and r["notes_series"] == "absent" and r["resets"] == "not_supplied"
    assert r["proposals"] == [{"index_on_page": 2, "read": "d", "proposed": "c", "basis": "sequence"}]


def test_chain_clean_page_has_no_flags_or_proposals():
    r = N.chain_check([{"file_page": 3, "text": "x^a^ y^b^ z^c^"}])[0]
    assert r["flags"] == [] and r["proposals"] == []


def test_chain_carries_prev_last_only_when_consecutive():
    recs = N.chain_check([{"file_page": 3, "text": "x^a^ y^b^"},
                          {"file_page": 4, "text": "z^d^"},
                          {"file_page": 9, "text": "q^d^"}])
    assert recs[1]["prev_last_carried"] == "b" and recs[1]["proposals"][0]["proposed"] == "c"
    assert recs[2]["prev_last_carried"] is None and recs[2]["proposals"] == []


# ---- CLI -------------------------------------------------------------------

def _body(d):
    p = Path(d) / "body.jsonl"
    chunk = {"file_page": 5, "col": "left", "rect_idx": 0, "chunk_idx": 0, "guard": "ok",
             "error": None, "text": "things^s: &c. ^a^;"}
    bad = {"file_page": 5, "col": "left", "rect_idx": 1, "chunk_idx": 1, "guard": "refused",
           "error": None, "text": None}
    recs = [{"kind": "run_header", "config_hash": "abc123"},
            {"kind": "body_region", "file_page": 5, "key": [5, "left", 1], "chunks": [chunk, bad]}]
    p.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    return p


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def test_cli_writes_header_first_and_body_unchanged():
    d = tempfile.mkdtemp()
    try:
        body = _body(d)
        before = _sha(body)
        out = Path(d) / "sub" / "derived.jsonl"
        assert N.main(["--body", str(body), "--out", str(out)]) == 0
        lines = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
        assert lines[0]["kind"] == "derived_header" and lines[0]["body_sha256"] == before
        assert lines[0]["body_config_hash"] == "abc123" and "git_dirty" in lines[0]
        kinds = [l["kind"] for l in lines]
        assert kinds == ["derived_header", "derived_chunk", "derived_chunk", "marker_chain_page",
                         "derived_summary"]
        assert lines[1]["text_out"] == "things^s^: &c.^a^ ;" and lines[1]["key"] == [5, "left", 1]
        assert lines[2]["text_out"] is None and lines[2]["reason"]
        assert _sha(body) == before
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_cli_refusals_leave_no_file():
    d = tempfile.mkdtemp()
    try:
        body = _body(d)
        before = _sha(body)
        lane = Path(d) / "goatyard-laneA2" / "zz" / "o.jsonl"
        assert N.main(["--body", str(body), "--out", str(lane)]) == 2
        assert not lane.exists() and not (Path(d) / "goatyard-laneA2").exists()
        assert N.main(["--body", str(body), "--out", str(body)]) == 2
        existing = Path(d) / "exists.jsonl"
        existing.write_text("keep\n", encoding="utf-8")
        assert N.main(["--body", str(body), "--out", str(existing)]) == 2
        assert existing.read_text(encoding="utf-8") == "keep\n"
        assert _sha(body) == before
        assert sorted(p.name for p in Path(d).iterdir()) == ["body.jsonl", "exists.jsonl"]
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
