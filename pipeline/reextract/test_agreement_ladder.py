"""agreement_ladder born tested — the three rungs, their precedence, and the dropped-lemma signal
(the real gemma-vs-qwen p402 shape). Run: python test_agreement_ladder.py"""
import agreement_ladder as AL

def test_scripts_in_ranges():
    assert AL.scripts_in("viri fratres") == frozenset({"latin"})
    assert AL.scripts_in("אנשים vos") == frozenset({"latin", "hebrew"})
    assert AL.scripts_in("περιείρειν") == frozenset({"greek"})
    assert "arabic" in AL.scripts_in("cruda ملح")

def test_count_rung_stops_first():
    r = AL.ladder(["a", "b", "c"], ["a", "b"])
    assert r["rung"] == "count" and r["count"] == (3, 2) and not r["agree"]

def test_script_rung_catches_dropped_lemma():
    # real p402 shape: gemma keeps both Hebrew lemmas, qwen drops them; counts equal
    gemma = ["התחת אלהים אני annon enim sub Deo sum? Vatablus", "על לבם ad cor eorum"]
    qwen  = ["annon enim sub Deo sum?", "ad cor eorum"]
    r = AL.ladder(gemma, qwen)
    assert r["rung"] == "script"
    assert {d["note"] for d in r["script_diffs"]} == {0, 1}
    assert all("hebrew" in d["dropped"] for d in r["script_diffs"])

def test_script_rung_precedes_text():
    # a note differs in BOTH script and text — must report at the script rung, not text
    r = AL.ladder(["שלום aaa"], ["bbb"])
    assert r["rung"] == "script" and r["text_diffs"] == []

def test_text_rung_only_when_scripts_agree():
    # same scripts (latin), different tokens -> text rung
    r = AL.ladder(["Pagninus Montanus Drusius"], ["Junius Tremellius Piscator"])
    assert r["rung"] == "text" and r["text_diffs"] and r["text_diffs"][0]["overlap"] < 0.5

def test_clean_agreement():
    notes = ["שרי מקנה על אשר לי magistros", "Works, vol. 1. p. 667."]
    assert AL.ladder(notes, notes)["rung"] == "agree" and AL.ladder(notes, notes)["agree"]

def test_dropped_lemma_helper():
    gemma = ["חום nigram", "Bereshit Rabba"]
    qwen  = ["nigram", "Bereshit Rabba"]
    dl = AL.dropped_lemma_notes(gemma, qwen)
    assert len(dl) == 1 and dl[0]["note"] == 0 and dl[0]["dropped"] == ["hebrew"]

def test_rung0_adjudicates_disagreement():
    # qwen collapsed to 1, gemma got 9, CV counted 9 -> CV adjudicates toward gemma (b)
    r = AL.adjudicate_count(1, 9, 9, True)
    assert r["verdict"] == "adjudicated" and r["winner"] == "b"

def test_rung0_catches_correlated_collapse():
    # BOTH models say 7, CV says 13 -> the hole dual-witness can't see
    r = AL.adjudicate_count(7, 7, 13, True)
    assert r["verdict"] == "correlated-collapse" and r["winner"] == "cv" and r["models"] == 7

def test_rung0_agree_when_all_match():
    assert AL.adjudicate_count(12, 13, 13, True)["verdict"] == "agree"

def test_rung0_defers_when_cv_unsure():
    # CV not confident (full-width/ambiguous) -> do not let it referee
    assert AL.adjudicate_count(1, 9, 9, False)["verdict"] == "cv-unsure"

def test_dropped_lemma_empty_on_count_mismatch():
    # rung-1 gate: no per-note comparison when counts differ
    assert AL.dropped_lemma_notes(["חום a", "b"], ["a"]) == []

def test_accepts_dict_notes():
    a = [{"text": "אנשים vos"}]; b = [{"text": "vos"}]
    assert AL.ladder(a, b)["rung"] == "script"

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed"); raise SystemExit(1 if f else 0)
