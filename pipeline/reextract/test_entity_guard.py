"""entity_guard born tested — the deterministic citation boundary + the safe-direction guarantee
(bare book-names stay figures) + the fail-loud watcher. Run: python test_entity_guard.py"""
import entity_guard as G

def test_citation_forms_detected():
    assert G.is_scripture_citation("Rom. i. 4") == ("ROMANS", 1, 4)
    assert G.is_scripture_citation("Mark xvi. 11") == ("MARK", 16, 11)
    assert G.is_scripture_citation("Is. liii. 6") == ("ISAIAH", 53, 6)
    assert G.is_scripture_citation("1 Cor. xv. 3") == ("1 CORINTHIANS", 15, 3)
    assert G.is_scripture_citation("Dan. vii. 13") == ("DANIEL", 7, 13)

def test_chapter_only_citation():
    # a book + chapter with no verse is still a citation (verse None)
    assert G.is_scripture_citation("Ps. cx") == ("PSALMS", 110, None)

def test_bare_booknames_are_NOT_citations():
    # the safe-direction guarantee: no following numeral -> preserved as the biblical FIGURE
    for n in ["Mark", "John", "Amos", "Job", "Dan", "Hosea"]:
        assert G.is_scripture_citation(n) is None, n

def test_lookalike_names_not_false_matched():
    # names that merely START with book letters must not be swallowed
    for n in ["Israel", "Isaac", "David", "Herod", "Heman", "Josephus", "Daniel the prophet"]:
        assert G.is_scripture_citation(n) is None, n

def test_book_then_nonnumeral_not_citation():
    # "<book> <word>" (not a numeral) is not a citation form
    assert G.is_scripture_citation("John Baptist") is None
    assert G.is_scripture_citation("Mark Antony") is None

def test_harden_moves_only_citations():
    res = {"entities": [{"name": "Mark", "category": "BiblicalFigure"},
                        {"name": "Mark xvi. 11", "category": "BiblicalFigure"},
                        {"name": "Josephus", "category": "CitedAuthority"}],
           "cross_references": ["ISAIAH_53_06"]}
    hardened, rep = G.harden(res)
    assert rep["n_moved"] == 1
    assert [e["name"] for e in hardened["entities"]] == ["Mark", "Josephus"]
    assert "MARK_16_11" in hardened["cross_references"]
    assert "ISAIAH_53_06" in hardened["cross_references"]   # pre-existing xref preserved

def test_harden_dedupes_xref():
    res = {"entities": [{"name": "Rom. i. 4", "category": "BiblicalFigure"}],
           "cross_references": ["ROMANS_01_04"]}   # same ref already present
    hardened, rep = G.harden(res)
    assert hardened["cross_references"].count("ROMANS_01_04") == 1

def test_watcher_passes_after_harden():
    res = {"entities": [{"name": "Rom. i. 4", "category": "BiblicalFigure"},
                        {"name": "Paul", "category": "BiblicalFigure"}], "cross_references": []}
    hardened, _ = G.harden(res)
    assert G.assert_no_citation_entities(hardened) is True

def test_watcher_fails_loud_on_leak():
    leaked = {"entities": [{"name": "Rom. i. 4", "category": "BiblicalFigure"}], "cross_references": []}
    try:
        G.assert_no_citation_entities(leaked); raise SystemExit("watcher did not fire")
    except AssertionError:
        pass  # expected: fail-loud

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed"); raise SystemExit(1 if f else 0)
