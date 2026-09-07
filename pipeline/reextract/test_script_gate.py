"""script_gate born-tested — the Greek-as-Hebrew catcher, both witnesses. Run: python test_script_gate.py"""
import script_gate as S

def test_greek_codepoints_are_hard_flagged():
    v, _ = S.gate("λόγος", "Sept. reads thus")            # Greek shipped as Hebrew -> hard flag
    assert v == "wrong-script"

def test_mixed_script_flagged():
    v, _ = S.gate("אמרβ", "")                              # Hebrew + a stray Greek beta
    assert v == "wrong-script"

def test_hebrew_with_greek_source_is_suspect():
    # the measured 33-note signal: note cites the Septuagint -> pure-Hebrew reading is suspect
    for ctx in ["as the Sept. renders", "Aquila hath it", "so LXX", "Symmachus and Theod."]:
        v, _ = S.gate("דבר", ctx)
        assert v == "greek-suspect", (ctx, v)

def test_hebrew_no_greek_signal_is_ok():
    v, _ = S.gate("בראשית", "Pagninus, Montanus, so the Chaldee")   # Latin/Aramaic sources, not Greek
    assert v == "ok", v

def test_cites_greek_source_direct():
    assert S.cites_greek_source("the Septuagint version")
    assert S.cites_greek_source("Aq. and Sym.")
    assert not S.cites_greek_source("the Vulgate and Targum")       # not Greek versions

def test_empty_is_ok():
    assert S.gate("", "Sept.")[0] == "ok"                 # no Hebrew to suspect

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed"); raise SystemExit(1 if f else 0)
