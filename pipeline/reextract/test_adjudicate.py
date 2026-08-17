"""adjudicate_candidates born tested — the verdict-only contract (never re-transcribes -> can't become
a third witness), the no-evidence gate (no frontier guess without internal evidence), and confidence
gating. Caller is injected, so no network. Run: python test_adjudicate.py"""
import escalation_tier as ET

NOTE = "על אשר לי magistros pecuariæ super illos, qui sunt mihi, Junius & Tremellius"

def _caller(chosen, correction="", conf=0.9):
    return lambda a, b, note, key: {"chosen": chosen, "disputed_span_correction": correction,
                                    "rationale": "cited qui sunt mihi", "confidence": conf, "cost": 0.004}

def test_gate_blocks_when_no_material():
    # two name spellings with NO gloss/citation -> review queue, NO frontier call
    called = []
    caller = lambda a, b, n, k: called.append(1) or {"chosen": "A"}
    r = ET.adjudicate_candidates("עליה", "עליהם", "עליהם", caller=caller)
    assert r["escalated"] is False and r["chosen"] == "neither" and called == []
    assert r["provenance"] == "review-queue-no-adjudicating-material"

def test_verdict_only_never_returns_full_note():
    r = ET.adjudicate_candidates("על אשר לי", "על אשדוד", NOTE, hspan="על אשר לי",
                                 caller=_caller("A", "על אשר לי"))
    # returns a choice + span correction, NOT the whole footnote
    assert r["chosen"] == "A" and r["correction"] == "על אשר לי"
    assert "magistros" not in r["correction"] and "qui sunt mihi" not in r["correction"]

def test_correction_defaults_to_chosen_candidate():
    # if the model omits the span, we fall back to the chosen candidate — still no re-transcription
    r = ET.adjudicate_candidates("על אשר לי", "על אשדוד", NOTE, hspan="על אשר לי", caller=_caller("B", ""))
    assert r["correction"] == "על אשדוד"

def test_neither_is_not_auto_acceptable():
    r = ET.adjudicate_candidates("עליה", "עליהם", NOTE, hspan="עליה", caller=_caller("neither"))
    assert r["escalated"] is True and r["auto_acceptable"] is False

def test_low_confidence_not_auto_acceptable():
    r = ET.adjudicate_candidates("על אשר לי", "על אשדוד", NOTE, hspan="על אשר לי",
                                 caller=_caller("A", "על אשר לי", conf=0.5))
    assert r["chosen"] == "A" and r["auto_acceptable"] is False   # chose, but not confident enough to auto

def test_high_confidence_choice_is_auto_acceptable():
    r = ET.adjudicate_candidates("על אשר לי", "על אשדוד", NOTE, hspan="על אשר לי",
                                 caller=_caller("A", "על אשר לי", conf=0.95))
    assert r["auto_acceptable"] is True

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed"); raise SystemExit(1 if f else 0)
