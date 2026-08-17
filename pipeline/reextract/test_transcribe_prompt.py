"""build_transcribe_prompt born tested — the prompt assembles the hanging-indent few-shot + furniture
clause FROM THE PROFILE, and always keeps the faithfulness/Hebrew clauses. (Tests assembly only; the
prompt's effect on extraction is a separate N>=6 validation.) Run: python test_transcribe_prompt.py"""
from extract_apparatus import build_transcribe_prompt, TRANSCRIBE_PROMPT

HANGING = {"compositor_conventions": {"note_layout": "hanging_indent"},
           "furniture": {"signature_example": "VOL. I.—OLD TEST. 4 D"}}

def test_hanging_indent_adds_convention_and_diagram():
    p = build_transcribe_prompt(HANGING)
    assert "HANGING INDENT" in p
    assert "EVERY marker begins a NEW footnote" in p
    assert "never merge two marked footnotes" in p and "never split" in p
    assert "\n  a First note" in p and "\n  b Second note." in p     # the few-shot diagram

def test_furniture_clause_uses_profile_example():
    p = build_transcribe_prompt(HANGING)
    assert "VOL. I.—OLD TEST. 4 D" in p and "NOT footnotes" in p

def test_no_convention_when_profile_silent():
    p = build_transcribe_prompt({})
    assert "HANGING INDENT" not in p
    assert p.startswith(TRANSCRIBE_PROMPT)                            # base preserved
    assert "NOT footnotes" in p                                       # furniture clause still added (default)

def test_faithfulness_and_hebrew_clauses_always_present():
    for prof in (HANGING, {}):
        p = build_transcribe_prompt(prof)
        assert "Do NOT translate, summarize" in p
        assert "Hebrew in Hebrew script" in p and "verbatim" in p

def test_other_layout_gets_no_hanging_indent():
    p = build_transcribe_prompt({"compositor_conventions": {"note_layout": "block"}})
    assert "HANGING INDENT" not in p

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed"); raise SystemExit(1 if f else 0)
