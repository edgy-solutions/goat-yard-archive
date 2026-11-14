"""diff_body_shadow born-tests: inline strings and constructed units only, no model, no private
data. Run: python test_diff_body_shadow.py

EXPECTED_TESTS asserts the suite's OWN test count so a silently-dropped test fails the run.
"""
import json
import shutil
import tempfile
from pathlib import Path

import diff_body_shadow as DBS

EXPECTED_TESTS = 28


def unit(chunk_texts, key=(90, "left", 10), kind="verse", status="shipped", head=True, line=1):
    return {"key": list(key), "stage1_line": line, "stage1_kind": kind, "head_status": status,
            "head_unit": head,
            "chunks": [{"chunk_idx": i, "rect_idx": 0, "col": "left", "box": [0, i * 100, 10, i * 100 + 90],
                        "text": t, "usable": t is not None} for i, t in enumerate(chunk_texts)]}


def classes(old, units):
    return [h["class"] for h in DBS.diff_page(90, old, units)]


def test_disputed_head_fires_on_head_tokens_of_non_shipped_verse():
    u = unit(["Ver. 12. And God said let"], status="disputed")
    hs = DBS.diff_page(90, "Ver. 21. And God said let", [u])
    assert [h["class"] for h in hs] == ["disputed_head"]


def test_precedence_ws_punct_looking_hunk_at_disputed_head_is_disputed_head():
    new = "Ver. 21 And God said let"
    old = "Ver. 21. And God said let"
    assert classes(old, [unit([new], status="disputed")]) == ["disputed_head"]
    # control: the same hunk on a shipped head is plain ws_punct (so the precedence is what decided)
    assert classes(old, [unit([new], status="shipped")]) == ["ws_punct"]


def test_unread_verse_head_is_also_not_shipped():
    assert classes("Ver. 21. And God", [unit(["Ver. 21 And God"], status="unread")]) == ["disputed_head"]


def test_non_verse_kind_never_disputed_head():
    u = unit(["Ver. 21 And God"], kind="chapter_intro", status=None)
    assert classes("Ver. 21. And God", [u]) == ["ws_punct"]


def test_continuation_unit_is_not_a_head_unit():
    u = unit(["Ver. 21 And God"], status="disputed", head=False)
    assert classes("Ver. 21. And God", [u]) == ["ws_punct"]


def test_old_side_alignment_catches_a_hunk_on_the_old_ver_line():
    old = "Ver. 5. a b c d e f"
    # the old-side head range is the first 4 tokens FROM the Ver token (lock), found through the
    # equal-opcode alignment: a hunk at old token 3 is a head hunk, one at token 7 is not
    assert classes(old, [unit(["Ver. 5. a X c d e f"], status="disputed")]) == ["disputed_head"]
    assert classes(old, [unit(["Ver. 5. a X c d e f"], status="shipped")]) == ["content"]
    assert classes(old, [unit(["Ver. 5. a b c d e g"], status="disputed")]) == ["content"]


def test_prose_ver_words_are_not_verse_heads():
    # "Verily"/"Very" begin with "Ver" but are prose: a content hunk on them stays content
    assert classes("and Verily he said", [unit(["and Verely he said"])]) == ["content"]
    assert classes("a Very great", [unit(["a Vary great"])]) == ["content"]
    for t in ("Ver.", "Ver,", "Ver", "ver.", "**Ver.", "Ver.1."):
        assert DBS.is_ver_token(t), t
    for t in ("Verily", "Very", "ver", "Version", "Ver.a"):
        assert not DBS.is_ver_token(t), t


def test_verse_boundary_on_ver_token_and_on_two_regions():
    assert classes("one two Ver. 2. text", [unit(["one two Verse 2. text"])]) == ["verse_boundary"]
    a = unit(["alpha beta gamma delta"], key=(90, "left", 10), line=1)
    b = unit(["epsilon zeta"], key=(90, "left", 500), line=2)
    hs = DBS.diff_page(90, "alpha beta gamma deltaX epsilonX zeta", [a, b])
    assert [h["class"] for h in hs] == ["verse_boundary"]
    assert hs[0]["regions"] == [[90, "left", 10], [90, "left", 500]]


def test_ws_punct_ignores_whitespace_and_punctuation_only():
    assert classes("the Lord, said", [unit(["the Lord said"])]) == ["ws_punct"]
    assert classes("a b", [unit(["a ; b"])]) == ["ws_punct"]


def test_case_only_difference_is_content():
    assert classes("the lord said", [unit(["the Lord said"])]) == ["content"]


def test_content_on_a_changed_word():
    assert classes("the Lord said", [unit(["the Lord spake"])]) == ["content"]


def test_flags_non_latin_marker_and_neither():
    hs = DBS.diff_page(90, "and אלהים said", [unit(["and אלוהים said"])])
    assert hs[0]["flags"]["non_latin"] is True and hs[0]["flags"]["marker"] is False
    hs = DBS.diff_page(90, "the word said", [unit(["the word^a^ said"])])
    assert hs[0]["flags"]["marker"] is True and hs[0]["flags"]["non_latin"] is False
    assert hs[0]["class"] == "content"   # ^ is a symbol, not P*: a marker is content, flagged
    hs = DBS.diff_page(90, "the word said", [unit(["the work said"])])
    assert hs[0]["flags"] == {"non_latin": False, "marker": False, "chunk_edge": False}


def test_chunk_edge_flag_within_one_token_of_a_boundary():
    # tokens: c0 = a b c d e f | c1 = g h i j k l ; boundary between f and g (index 6)
    old = "a b c d e f g h i j k l"
    near = DBS.diff_page(90, old, [unit(["a b c d e f", "X h i j k l"])])        # token 6: at boundary
    near2 = DBS.diff_page(90, old, [unit(["a b c d e Y", "g h i j k l"])])       # token 5: adjacent
    far = DBS.diff_page(90, old, [unit(["a b X d e f", "g h i j k l"])])         # token 2: 3 away
    far2 = DBS.diff_page(90, old, [unit(["a b c d e f", "g h i j Z l"])])        # token 10
    assert near[0]["flags"]["chunk_edge"] and near2[0]["flags"]["chunk_edge"]
    assert not far[0]["flags"]["chunk_edge"] and not far2[0]["flags"]["chunk_edge"]


def test_hunk_maps_to_region_and_chunk():
    a = unit(["a b c", "d e f"], key=(90, "left", 10), line=3)
    hs = DBS.diff_page(90, "a b c d X f", [a])
    ref = hs[0]["chunk"]
    assert ref["chunk_idx"] == 1 and ref["stage1_line"] == 3 and ref["key"] == [90, "left", 10]
    assert ref["box"] == [0, 100, 10, 190] and hs[0]["regions"] == [[90, "left", 10]]
    assert hs[0]["old_before"] == "a b c d" and hs[0]["new_after"] == "f"


def test_tokeniser_is_one_function_for_both_sides():
    calls = []
    real = DBS.tagged_tokens
    DBS.tagged_tokens = lambda tl: (calls.append(len(tl)), real(tl))[1]
    try:
        # old prints the break joined, new carries it across two CHUNKS: no hunk iff both sides use
        # the same join-then-split path
        hs = DBS.diff_page(90, "so regeneration of", [unit(["so regene-", "ration of"])])
    finally:
        DBS.tagged_tokens = real
    assert hs == [] and len(calls) == 2, calls
    assert DBS.tokens("regene-\nration of") == ["regeneration", "of"]
    assert DBS.tokens("Lord-\nAnd") == ["Lord-", "And"]


def test_unusable_chunk_contributes_nothing():
    u = unit(["a b c", None, "g h i"])
    hs = DBS.diff_page(90, "a b c d e f g h i", [u])
    assert [h["op"] for h in hs] == ["delete"] and hs[0]["old_text"] == "d e f"


def test_verse_number_agreement_record():
    s1 = {"kind": "verse", "head_status": "shipped",
          "number_sources": {"count": [21], "read": [21], "witness": [21]}}
    agree = DBS.verse_number_record(90, s1, 4, unit(["Ver. 21. In the"], line=4))
    assert agree["head_read_eq_witness"] and agree["body_read_eq_witness"] and agree["body_read"] == [21]
    wrong = DBS.verse_number_record(90, s1, 4, unit(["Ver. 12. In the"], line=4))
    assert wrong["head_read_eq_witness"] and not wrong["body_read_eq_witness"] and wrong["body_read"] == [12]
    gone = DBS.verse_number_record(90, s1, 4, unit([None], line=4))
    assert gone["body_read"] is None and not gone["body_read_eq_witness"]
    nounit = DBS.verse_number_record(90, s1, 4, None)
    assert nounit["body_read"] is None
    split = {"kind": "verse", "head_status": "disputed",
             "number_sources": {"count": None, "read": [21], "witness": [12]}}
    r = DBS.verse_number_record(90, split, 5, unit(["Ver. 21. x"], line=5))
    assert not r["head_read_eq_witness"] and not r["body_read_eq_witness"] and r["body_read"] == [21]


def test_summarize_counts_classes_flags_and_agreement():
    mk = lambda fp, cls, nl=False: {"file_page": fp, "class": cls,
                                     "flags": {"non_latin": nl, "marker": False, "chunk_edge": False}}
    hunks = [mk(90, "content", True), mk(90, "content"), mk(91, "ws_punct")]
    v = [{"file_page": 90, "head_read_eq_witness": True, "body_read_eq_witness": False},
         {"file_page": 91, "head_read_eq_witness": True, "body_read_eq_witness": True}]
    s = DBS.summarize(hunks, v)
    assert s["classes"] == {"content": 2, "ws_punct": 1}
    assert s["per_page"] == {"90": {"content": 2}, "91": {"ws_punct": 1}}
    assert s["flags_per_class"]["content"] == {"non_latin": 1}
    assert s["verse_agreement"] == {"n": 2, "head_read_eq_witness": 2, "body_read_eq_witness": 1}
    assert s["verse_agreement_per_page"]["90"]["body_read_eq_witness"] == 0


def test_main_end_to_end_on_synthetic_files():
    d = Path(tempfile.mkdtemp(prefix="dbs_test_"))
    try:
        (d / "page90_image1_normalized.md").write_text(
            "Ver. 1. In the beginning God\nmade the heaven.\n\n[^1] note text\n", encoding="utf-8")
        s1 = [{"kind": "run_header"},
              {"kind": "verse", "file_page_first": 90, "head_status": "shipped",
               "head": {"col": "left", "y0": 10},
               "number_sources": {"count": [1], "read": [1], "witness": [1]}}]
        (d / "s1.jsonl").write_text("\n".join(json.dumps(r) for r in s1) + "\n", encoding="utf-8")
        chunk = {"file_page": 90, "col": "left", "rect_idx": 0, "chunk_idx": 0, "box": [0, 0, 10, 10],
                 "n_lines": 2, "guard": "ok", "text": "Ver. 1. In the beginning God\nmade the heavens.",
                 "error": None}
        body = [{"kind": "run_header", "config_hash": "abc"},
                {"kind": "body_region", "file_page": 90, "key": [90, "left", 10], "stage1_line": 1,
                 "stage1_kind": "verse", "head_status": "shipped", "chunks": [chunk]}]
        (d / "body.jsonl").write_text("\n".join(json.dumps(r) for r in body) + "\n", encoding="utf-8")
        out = d / "diff.jsonl"
        rc = DBS.main(["--body", str(d / "body.jsonl"), "--stage1", str(d / "s1.jsonl"),
                       "--witness-dir", str(d), "--out", str(out)])
        assert rc == 0
        recs = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
        assert [r["kind"] for r in recs] == ["diff_header", "hunk", "verse_numbers", "diff_summary"]
        assert recs[0]["config_hash"] and recs[0]["config"]["body_config_hash"] == "abc"
        assert recs[1]["class"] == "content" and recs[1]["new_text"] == "heavens."
        assert recs[2]["body_read_eq_witness"] is True
        assert recs[3]["classes"] == {"content": 1}
        assert DBS.main(["--body", str(d / "body.jsonl"), "--stage1", str(d / "s1.jsonl"),
                         "--witness-dir", str(d), "--out", str(out)]) == 2   # never clobbers
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_missing_witness_fails_loud_naming_the_page():
    try:
        DBS.load_old_body(tempfile.gettempdir(), 987654)
    except ValueError as e:
        assert "987654" in str(e)
    else:
        raise AssertionError("a missing witness md must raise")



def test_head_old_range_is_first_four_tokens_from_ver_not_the_whole_line():
    words = " ".join("w%d" % i for i in range(30))
    old = "Ver. 22. " + words
    # a changed token 8+ tokens after the Ver token: under the whole-line rule this was disputed_head
    assert classes(old, [unit(["Ver. 22. " + words.replace("w10", "wX"), ], status="disputed")]) == ["content"]
    # a changed head number IS a head hunk
    assert classes(old, [unit(["Ver. 32. " + words], status="disputed")]) == ["disputed_head"]
    # a line with text before the Ver token: the range starts AT the Ver token
    old2 = "lead in text Ver. 22. " + words
    assert classes(old2, [unit(["lead in text Ver. 32. " + words], status="disputed")]) == ["disputed_head"]


def test_split_old_defs_wrapped_numeric_definitions_all_removed():
    md = ("Ver. 1. body text\n\n[^3]: and, with mighty wings\ncontinues here\nand here\n"
          "[^4]: another note\n")
    body, defs = DBS.split_old_defs(md)
    assert "[^3]" not in body and "mighty" not in body and "continues here" not in body
    assert "[^4]" not in body and "another note" not in body
    assert "Ver. 1. body text" in body
    assert "continues here" in defs and "and here" in defs and "[^4]: another note" in defs


def test_split_old_defs_blank_closes_block_and_paragraph_stays_in_body():
    md = ("[^8]: first def\n\nA body paragraph that must stay.\n\n[^10]: tenth def\nwrapped tail\n")
    body, defs = DBS.split_old_defs(md)
    assert "A body paragraph that must stay." in body
    assert "first def" not in body and "tenth def" not in body and "wrapped tail" not in body
    assert "first def" in defs and "tenth def" in defs


def test_split_old_defs_inline_reference_is_not_a_definition():
    md = "He cites Strabo[^14]: and more text\nnext line\n"
    body, defs = DBS.split_old_defs(md)
    assert body == md and defs == ""


def test_split_old_defs_no_defs_body_unchanged():
    md = "Ver. 1. text\n\nmore text\n"
    body, defs = DBS.split_old_defs(md)
    assert body == md and defs == ""


def test_split_old_defs_letter_marker_removed_too():
    body, defs = DBS.split_old_defs("text\n[^a]: x\nmore\n")
    assert body.split("\n")[0] == "text" and "[^a]: x" in defs and "more" not in body


def _synthetic_run(d, s1_extra=None, body_status="shipped", s1_status="shipped", s1_head_y0=10,
                   text="Ver. 1. In the beginning God"):
    (d / "page90_image1_normalized.md").write_text("Ver. 1. In the beginning God\n", encoding="utf-8")
    s1 = [{"kind": "run_header"},
          {"kind": "verse", "file_page_first": 90, "head_status": s1_status,
           "head": {"col": "left", "y0": s1_head_y0},
           "number_sources": {"count": [1], "read": [1], "witness": [1]}}]
    (d / "s1.jsonl").write_text("\n".join(json.dumps(r) for r in s1) + "\n", encoding="utf-8")
    chunk = {"file_page": 90, "col": "left", "rect_idx": 0, "chunk_idx": 0, "box": [0, 0, 10, 10],
             "n_lines": 1, "guard": "ok", "text": text, "error": None}
    body = [{"kind": "run_header", "config_hash": "abc"},
            {"kind": "body_region", "file_page": 90, "key": [90, "left", 10], "stage1_line": 1,
             "stage1_kind": "verse", "head_status": body_status, "chunks": [chunk]}]
    (d / "body.jsonl").write_text("\n".join(json.dumps(r) for r in body) + "\n", encoding="utf-8")
    out = d / "diff.jsonl"
    rc = DBS.main(["--body", str(d / "body.jsonl"), "--stage1", str(d / "s1.jsonl"),
                   "--witness-dir", str(d), "--out", str(out)])
    return rc, out


def test_head_status_mismatched_stage1_region_key_refuses_and_writes_nothing():
    d = Path(tempfile.mkdtemp(prefix="dbs_test_"))
    try:
        rc, out = _synthetic_run(d, s1_head_y0=99)
        assert rc == 2 and not out.exists()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_head_status_comes_from_stage1_and_changes_are_listed():
    d = Path(tempfile.mkdtemp(prefix="dbs_test_"))
    try:
        rc, out = _synthetic_run(d, body_status="shipped", s1_status="disputed",
                                 text="Ver. 2. In the beginning God")
        assert rc == 0
        recs = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
        assert recs[0]["config"]["head_status_source"] == "stage1"
        assert recs[0]["config"]["old_defs_rule"] == "def_block_v1"
        assert recs[0]["config"]["head_old_rule"] == "first4_from_ver"
        assert recs[-1]["head_status_changed_vs_body"] == [json.dumps([90, "left", 10])]
        # the head hunk is classified with the STAGE-1 status (body said shipped)
        assert [r["class"] for r in recs if r["kind"] == "hunk"] == ["disputed_head"]
    finally:
        shutil.rmtree(d, ignore_errors=True)
    d = Path(tempfile.mkdtemp(prefix="dbs_test_"))
    try:
        rc, out = _synthetic_run(d, body_status="shipped", s1_status="shipped")
        recs = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
        assert recs[-1]["head_status_changed_vs_body"] == []
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
