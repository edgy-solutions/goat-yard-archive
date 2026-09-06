"""editorial_annotation born-tested — one record type, three kinds, corpus keeps the printed form and the
editor's reading is a marked standoff annotation. The three real values that motivated it are the fixtures:
a name-variant, an emendation, an unresolved glyph. Run: python test_editorial_annotation.py"""
import editorial_annotation as EA

def test_name_variant():
    a = EA.make_annotation("p323:n2", "name-variant", printed="Menassch", proposed="Menasseh",
                           basis="evidence-grounded", basis_note="Franciscus Vatablus-class page variant",
                           confidence="high", editor="human:Chris")
    assert EA.validate(a) and a["proposed"] == "Menasseh" and a["display"] == "editorial"

def test_emendation_p619():
    a = EA.make_annotation("p619:n0", "emendation", printed="חח", proposed="חת",
                           basis="prior-grounded",
                           basis_note="Kimchi Sefer ha-Shorashim heads the geminate root חתת this way; חח is no root",
                           confidence="moderate", editor="human:Chris")
    assert EA.validate(a) and a["basis"] == "prior-grounded" and a["indexed_for_retrieval"] is True

def test_unresolved_carries_no_reading():
    a = EA.make_annotation("p188:n0", "unresolved", printed="??", proposed=None,
                           confidence="low", editor="human:Chris")
    assert EA.validate(a) and a["proposed"] is None

def test_emendation_requires_grounded_basis():
    try:
        EA.make_annotation("p1:n0", "emendation", "חח", "חת", confidence="moderate", editor="x", basis=None)
        raise SystemExit("emendation without basis accepted")
    except ValueError: pass

def test_non_unresolved_requires_proposed():
    try:
        EA.make_annotation("p1:n0", "name-variant", "x", proposed="", confidence="high",
                           editor="x", basis="evidence-grounded")
        raise SystemExit("name-variant without proposed accepted")
    except ValueError: pass

def test_display_is_always_editorial():
    a = EA.make_annotation("p1:n0", "emendation", "a", "b", basis="prior-grounded",
                           confidence="low", editor="x")
    bad = dict(a); bad["display"] = "corpus"
    try: EA.validate(bad); raise SystemExit("non-editorial display accepted")
    except ValueError: pass

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed"); raise SystemExit(1 if f else 0)
