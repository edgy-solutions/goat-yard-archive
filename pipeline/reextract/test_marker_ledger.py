"""marker_ledger born-tested: two-series alignment + chain walk. Fixtures are the p90/p403/p635
truth-vs-reader scenarios from the spec (ADR two-series-marker-ledger). Run: python test_marker_ledger.py

EXPECTED_TESTS asserts the suite's OWN test count so a silently-dropped test function (e.g. a typo
turning test_foo into _test_foo) fails the run instead of just passing with fewer checks.
"""
import json

import marker_ledger as ML

EXPECTED_TESTS = 17


def _page(file_page, body, notes, body_cols=None, notes_cols=None):
    return {"file_page": file_page, "body": body, "notes": notes,
            "body_cols": body_cols, "notes_cols": notes_cols}


# 1. body_markers -----------------------------------------------------------

def test_body_markers_order_incl_wild_and_symbol():
    text = "a⟦a⟧ b⟦?⟧ c⟦*⟧ d⟦j⟧"
    assert ML.body_markers(text) == ["a", "?", "*", "j"]
    assert ML.body_markers("no sentinels here") == []


# 2. project_legacy -----------------------------------------------------------

def test_project_legacy_identity_numbering_and_errors():
    plain = "no sentinel text"
    assert ML.project_legacy(plain) is plain                      # byte-identical / same object
    text = "see⟦a⟧ and⟦b⟧ also⟦c⟧"
    assert ML.project_legacy(text) == "see[^1] and[^2] also[^3]"
    assert ML.project_legacy(text, link_numbers=[5, 9, 2]) == "see[^5] and[^9] also[^2]"
    try:
        ML.project_legacy(text, link_numbers=[1, 2])
        assert False, "expected ValueError on length mismatch"
    except ValueError:
        pass
    try:
        ML.project_legacy(text, link_numbers=[1, None, 3])
        assert False, "expected ValueError on a None entry"
    except ValueError:
        pass


# 3. p90 truth ----------------------------------------------------------------

def test_p90_truth_notes_fill_body_wildcards():
    pages = [_page(90, ["?"] * 5, ["c", "a", "b", "c", "d"])]
    r = ML.reconcile(pages, resets={90: [1]})
    assert len(r["slots"]) == 5
    assert [s["link_status"] for s in r["slots"]] == ["linked"] * 5
    assert [s["filled_from"] for s in r["slots"]] == ["notes"] * 5
    assert [s["letter"] for s in r["slots"]] == ["c", "a", "b", "c", "d"]
    assert r["breaks"] == []


# 4. p90 reader read, disputes against the reset-anchored chain ---------------

def test_p90_reader_read_disputes_against_reset_chain():
    pages = [_page(90, ["?"] * 5, ["c", "b", "d", "c", "d"])]
    r = ML.reconcile(pages, resets={90: [1]})
    slots = r["slots"]
    assert slots[1]["link_status"] == "disputed" and "reader_vs_chain" in slots[1]["flags"]
    assert slots[2]["link_status"] == "disputed" and "reader_vs_chain" in slots[2]["flags"]
    assert [slots[1]["chain_expects"], slots[2]["chain_expects"]] == ["a", "b"]
    assert slots[1]["letter"] is None and slots[2]["letter"] is None
    assert slots[1]["notes_read"] == "b" and slots[2]["notes_read"] == "d"   # raw read preserved
    for i in (0, 3, 4):
        assert slots[i]["link_status"] == "linked"


# 5. p90 two reads disagree -- positional, never gapped ------------------------

def test_p90_two_reads_disagree_no_gaps_inserted():
    pages = [_page(90, ["c", "a", "b", "c", "d"], ["c", "b", "d", "c", "d"])]
    r = ML.reconcile(pages)
    slots = r["slots"]
    assert len(slots) == 5
    assert all(s["body_idx"] is not None and s["notes_idx"] is not None for s in slots)  # no gaps
    assert slots[1]["link_status"] == "disputed" and "reads_disagree" in slots[1]["flags"]
    assert slots[2]["link_status"] == "disputed" and "reads_disagree" in slots[2]["flags"]
    assert slots[1]["letter"] is None and slots[2]["letter"] is None


# 6. p403 truth, wrap is not a break -------------------------------------------

def test_p403_truth_wrap_not_a_break():
    notes = ["x", "y", "z", "a", "b", "c", "d", "e", "f", "a"]
    pages = [_page(403, ["?"] * 10, notes)]
    r = ML.reconcile(pages, resets={403: [9]}, prev_last="w")
    slots = r["slots"]
    assert [s["letter"] for s in slots] == notes
    assert all(s["link_status"] == "linked" for s in slots)
    assert all(s["chain"] == "anchored" for s in slots)
    assert r["breaks"] == []


# 7. p403 fabrication, no anchor: undetectable -- documents a limit -----------

def test_p403_fabrication_undetectable_without_anchor():
    notes = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]
    pages = [_page(403, ["?"] * 10, notes)]
    r = ML.reconcile(pages, resets={403: [9]}, prev_last=None)
    slots = r["slots"]
    assert all(s["link_status"] != "disputed" for s in slots)
    for i in range(9):
        assert slots[i]["chain"] == "internal"
    assert slots[9]["letter"] == "a"
    assert "reset_anchor" in slots[9]["flags"]
    assert slots[9]["notes_read"] == "j"          # raw fabricated read kept, letter forced to 'a'


# 8. same fabrication, WITH an outside anchor -> detected ----------------------

def test_p403_fabrication_detected_with_anchor():
    notes = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]
    pages = [_page(403, ["?"] * 10, notes)]
    r = ML.reconcile(pages, resets={403: [9]}, prev_last="w")
    slots = r["slots"]
    for i in range(9):
        assert slots[i]["link_status"] == "disputed" and "reader_vs_chain" in slots[i]["flags"]
        assert "possible_reset" not in slots[i]["flags"]
    assert r["anomaly_candidates"] == []


# 9. same, but the page is reset-UNKNOWN -> possible_reset, not disputed ------

def test_p403_reset_unknown_possible_reset_not_disputed():
    notes = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]
    pages = [_page(403, ["?"] * 10, notes)]
    r = ML.reconcile(pages, resets={}, prev_last="w")
    slots = r["slots"]
    assert "possible_reset" in slots[0]["flags"]
    for s in slots[:9]:
        assert s["link_status"] != "disputed"


# 10. count-unequal same page: positional gap, not an offset ------------------

def test_count_unequal_same_page_positional_gap():
    pages = [_page(90, ["a", "b", "d", "e"], ["a", "b", "c", "d", "e"])]
    r = ML.reconcile(pages)
    slots = r["slots"]
    assert len(slots) == 5
    c_slot = next(s for s in slots if s["notes_read"] == "c")
    assert c_slot["seen_in_body"] is False
    assert c_slot["link_status"] == "filled" and c_slot["filled_from"] == "notes"
    d_slot = next(s for s in slots if s["notes_read"] == "d" and s["body_read"] == "d")
    e_slot = next(s for s in slots if s["notes_read"] == "e" and s["body_read"] == "e")
    assert d_slot["letter"] == "d" and e_slot["letter"] == "e"


# 11. cross-page pairing --------------------------------------------------------

def test_cross_page_pairing_flagged():
    pages = [
        _page(1, ["a", "b", "c"], ["a", "b"]),
        _page(2, ["d"], ["c", "d"]),
    ]
    r = ML.reconcile(pages)
    slots = r["slots"]
    assert len(slots) == 4
    cross = [s for s in slots if "cross_page_link" in s["flags"]]
    assert len(cross) == 1
    assert cross[0]["body_read"] == "c" and cross[0]["notes_read"] == "c"


# 12. two-sided chain fill, and the one-sided (unfillable) counterpart --------

def test_two_sided_fill_and_one_sided_open():
    pages = [_page(90, ["?"] * 4, ["a", "?", "?", "d"])]
    r = ML.reconcile(pages)
    slots = r["slots"]
    assert slots[1]["letter"] == "b" and slots[1]["filled_from"] == "chain"
    assert slots[2]["letter"] == "c" and slots[2]["filled_from"] == "chain"

    pages2 = [{"file_page": 90, "body": None, "notes": ["?", "?", "c"],
               "body_cols": None, "notes_cols": None}]
    r2 = ML.reconcile(pages2, prev_last=None)
    slots2 = r2["slots"]
    assert slots2[0]["link_status"] == "open" and slots2[0]["letter"] is None
    assert slots2[1]["link_status"] == "open" and slots2[1]["letter"] is None


# 13. anomaly table pins a skip-letter page; without it, a candidate surfaces --

def test_anomaly_table_pins_skip_letter_without_table_flags_candidate():
    notes = ["w", "x", "z", "a", "b"]
    pages = [{"file_page": 635, "body": None, "notes": list(notes),
              "body_cols": None, "notes_cols": None}]
    anomalies = {635: {"kind": "skip-letter", "observed": list(notes)}}
    r = ML.reconcile(pages, anomalies=anomalies, prev_last="u")
    assert r["breaks"] == []
    assert all("anomaly_applied" in s["flags"] for s in r["slots"])

    pages2 = [_page(635, list(notes), list(notes))]
    r2 = ML.reconcile(pages2, prev_last="u")
    z_candidates = [a for a in r2["anomaly_candidates"] if a["observed"] == "z"]
    assert len(z_candidates) == 1


# 14. a symbol marker never joins the letter chain -----------------------------

def test_symbol_marker_outside_chain_no_break():
    pages = [_page(90, ["x", "y", "*", "z"], ["x", "y", "*", "z"])]
    r = ML.reconcile(pages)
    star = r["slots"][2]
    assert star["chain"] == "outside" and star["link_status"] == "linked"
    assert r["breaks"] == []


# 15. column-order correction suppresses the breaks it would have caused -------

def test_column_order_suspect_suppresses_breaks():
    pages = [_page(90, ["?"] * 6, ["d", "e", "f", "a", "b", "c"], notes_cols=[3, 3])]
    r = ML.reconcile(pages, prev_last="z", resets={})
    assert "column_order_suspect" in r["page_flags"].get(90, [])
    assert r["breaks"] == []
    assert len(r["suppressed_breaks"]) > 0


# 16. None (not captured) vs [] (captured, empty) stay distinct ---------------

def test_none_vs_empty_series_distinct():
    pages = [{"file_page": 90, "body": None, "notes": ["c"],
              "body_cols": None, "notes_cols": None}]
    r = ML.reconcile(pages)
    s = r["slots"][0]
    assert s["seen_in_body"] is None
    assert s["link_status"] == "open"
    assert s["letter"] == "c" and s["filled_from"] == "notes"
    assert "body_not_captured" in s["flags"]

    pages2 = [_page(90, [], ["c", "d"])]
    r2 = ML.reconcile(pages2)
    assert "empty_series_with_counterpart" in r2["page_flags"].get(90, [])


# 17. determinism ---------------------------------------------------------------

def test_determinism():
    pages = [_page(90, ["c", "a", "b", "c", "d"], ["c", "b", "d", "c", "d"])]
    r1 = ML.reconcile(pages, resets={90: [1]}, prev_last="z")
    r2 = ML.reconcile(pages, resets={90: [1]}, prev_last="z")
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)


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
