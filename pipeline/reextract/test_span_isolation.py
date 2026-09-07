"""span_isolation born-tested — the real p513 note as fixture. Run: python test_span_isolation.py"""
import span_isolation as SI

# the real p513 [^2] note: Hebrew reading, Greek Septuagint quotation, Latin gloss
P513 = "תנשו אל אשה μη προσελθητε γυναικι Sept. to a woman, Ainsworth."

def test_isolates_hebrew_from_mixed_note():
    spans = SI.hebrew_spans(P513)
    assert len(spans) == 1, spans
    assert spans[0]["hebrew"] == "תנשו אל אשה"
    assert "Sept." in spans[0]["latin_context"]        # the gloss travels as context
    assert "μη" not in spans[0]["latin_context"]       # Greek is NOT in the Latin context
    assert spans[0]["greek_present"] is True           # but the note is flagged as carrying Greek

def test_box_is_none_until_extraction_time():
    assert SI.hebrew_spans(P513)[0]["box"] is None      # pixel isolation is the extractor's job

def test_script_gate_exact_on_isolated_field():
    # the payoff: on the ISOLATED Hebrew field the script gate is clean, where the mixed note over-flagged
    import script_gate as S
    sp = SI.hebrew_spans(P513)[0]
    assert S.gate(sp["hebrew"], sp["latin_context"])[0] == "greek-suspect"   # heb + Sept. cite -> suspect
    # and the Hebrew field itself carries no Greek codepoints -> not a wrong-script hard flag
    assert S.has_greek(sp["hebrew"]) is False

def test_multiple_hebrew_runs():
    spans = SI.hebrew_spans("חזק מאד fortis valde, Pagninus; אלהים Deus")
    assert [s["hebrew"] for s in spans] == ["חזק מאד", "אלהים"]

def test_no_hebrew():
    assert SI.hebrew_spans("Pagninus, Montanus, Vatablus") == []

def test_segment_orders_runs():
    scripts = [r["script"] for r in SI.segment(P513)]
    assert scripts == ["hebrew", "greek", "latin"], scripts

if __name__ == "__main__":
    import sys, traceback
    sys.path.insert(0, ".")
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed"); raise SystemExit(1 if f else 0)
