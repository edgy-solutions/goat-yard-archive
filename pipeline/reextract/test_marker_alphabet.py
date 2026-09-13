"""marker_alphabet born-tested — the 24-letter (no j/v) count + legality rules. Run: python test_marker_alphabet.py"""
import marker_alphabet as M

def test_count_skips_j_and_v():
    assert M.count_between("a", "n") == 13          # a..n minus j = 13, not 14
    assert M.count_between("a", "z") == 24          # the whole alphabet
    assert M.count_between("t", "z") == 6           # t u w x y z (v skipped)

def test_jv_illegal_and_merged():
    assert M.is_legal("k") and not M.is_legal("j") and not M.is_legal("v")
    assert M.normalize("J") == "i" and M.normalize("v") == "u"

def test_sequence_breaks_flags_slip_and_gap():
    assert M.sequence_breaks(["h", "i", "k", "l"]) == []             # legal run: i→k skips j, still consecutive
    assert any("illegal" in p for p in M.sequence_breaks(["a", "b", "j"]))   # a stray j
    assert any("non-consecutive" in p for p in M.sequence_breaks(["a", "c"]))  # missing b

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed"); raise SystemExit(1 if f else 0)
