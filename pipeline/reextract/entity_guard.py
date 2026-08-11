"""ENTITY GUARD — the deterministic post-extraction hardening the BAML pipeline is missing.

gill_extract.baml asks the MODEL to keep scripture citations out of the entity list
("CHECK THE PATTERN: 'Rom. i. 4' -> CITATION, 'Mark' -> FIGURE"). But "a known book
abbreviation followed by a chapter numeral" is a DETERMINISTIC PROPERTY of the string —
so per deterministic-property-not-a-model, CODE owns it and an ASSERTION watches it; the
model is never the last line of defence on a boundary code can compute exactly.

  is_scripture_citation(name) -> the property (book-abbrev + numeral), computed off the
                                 canonical backend/bible_mapping table (single source of truth).
  harden(result)            -> move citation-leaks out of `entities` into `cross_references`
                                 (normalized BOOK_CH_VS where parseable), return report.
  assert_no_citation_entities(result) -> the watcher: FAIL-LOUD if any entity is still a
                                 citation. Runs after harden; a raise means the property broke.

SAFE BY CONSTRUCTION: a BARE book-name ("Mark", "John", "Amos") has no following numeral,
so it is NEVER reclassified — the biblical FIGURE is preserved; only "<book> <chapter>[...]"
strings move. This is the one direction that's safe to automate (constrain-direction-safely).

Probe-ready but unprobed: operates on ExtractionResult dicts, no LLM call. Plug it on the
output of ExtractGillKnowledge (baml_src/gill_extract.baml) once that path runs.
"""
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from bible_mapping import BIBLE_BOOK_MAP  # canonical abbrev -> CANONICAL_NAME (single source of truth)

# book keys longest-first so "1 cor" wins over a hypothetical "1"
_BOOK_KEYS = sorted(BIBLE_BOOK_MAP, key=len, reverse=True)
_ROMAN = re.compile(r"^[ivxlcdm]+$")
_DIGIT = re.compile(r"^\d+$")

def _numeral(tok):
    """Chapter/verse token -> int, or None. Accepts roman ('xvi') or digit ('16')."""
    t = tok.strip(" .,:;").lower()
    if not t: return None
    if _DIGIT.match(t): return int(t)
    if _ROMAN.match(t):
        vals = {"i":1,"v":5,"x":10,"l":50,"c":100,"d":500,"m":1000}; total = 0; prev = 0
        for ch in reversed(t):
            v = vals[ch]; total += -v if v < prev else v; prev = max(prev, v)
        return total
    return None

def is_scripture_citation(name):
    """The DETERMINISTIC property: does `name` begin with a canonical book abbreviation
    FOLLOWED BY a chapter numeral? Returns (book_canonical, chapter, verse|None) or None.
    A bare book-name (no numeral) returns None on purpose (that's the biblical figure)."""
    s = " ".join(name.strip().split())
    low = s.lower()
    for key in _BOOK_KEYS:
        # book token boundary: end-of-string or a non-alnum separator (space/period)
        if low == key: return None                       # bare book name -> NOT a citation
        if low.startswith(key) and not low[len(key)].isalnum():
            rest = s[len(key):]
            toks = [t for t in re.split(r"[\s.,:;]+", rest) if t]
            if not toks: return None
            ch = _numeral(toks[0])
            if ch is None: return None                   # "<book> <non-numeral>" -> not a citation
            vs = _numeral(toks[1]) if len(toks) > 1 else None
            return (BIBLE_BOOK_MAP[key], ch, vs)
    return None

def _norm_ref(book_canonical, ch, vs):
    """BOOK_CH_VS form matching the BAML cross_references convention (e.g. ROMANS_01_04)."""
    b = book_canonical.replace(" ", "_")
    return f"{b}_{ch:02d}_{vs:02d}" if vs else f"{b}_{ch:02d}"

def harden(result):
    """Move citation-leaks from entities -> cross_references. Returns (hardened_result, report).
    Non-destructive: works on a shallow copy; unparseable-but-citation names still leave the
    entity list (they don't belong there) and are logged raw."""
    entities = result.get("entities", []) or []
    xrefs = list(result.get("cross_references", []) or [])
    kept, moved = [], []
    for e in entities:
        hit = is_scripture_citation(e.get("name", ""))
        if hit:
            ref = _norm_ref(*hit)
            if ref not in xrefs: xrefs.append(ref)
            moved.append({"name": e.get("name"), "was_category": e.get("category"), "ref": ref})
        else:
            kept.append(e)
    out = dict(result); out["entities"] = kept; out["cross_references"] = xrefs
    return out, {"moved": moved, "n_moved": len(moved), "n_entities_out": len(kept)}

def assert_no_citation_entities(result):
    """The WATCHER (fail-loud). After harden, no entity name may satisfy the property.
    A raise here means the deterministic boundary was violated — a real bug, not a judgment call."""
    bad = [e.get("name") for e in (result.get("entities") or []) if is_scripture_citation(e.get("name", ""))]
    if bad:
        raise AssertionError(f"citation(s) still classified as entities: {bad}")
    return True

if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    # demo: the exact cases from the BAML prompt, plus the figure/citation edge
    for n in ["Rom. i. 4", "Mark xvi. 11", "Mark", "John", "Is. liii. 6", "1 Cor. xv. 3", "Amos", "Josephus"]:
        print(f"  {n!r:18} -> {is_scripture_citation(n)}")
    sample = {"entities": [{"name": "Mark", "category": "BiblicalFigure"},
                           {"name": "Mark xvi. 11", "category": "BiblicalFigure"},
                           {"name": "Josephus", "category": "CitedAuthority"}],
              "cross_references": ["ISAIAH_53_06"]}
    hardened, rep = harden(sample)
    print("  moved:", rep["moved"]); print("  xrefs:", hardened["cross_references"])
    print("  entities kept:", [e["name"] for e in hardened["entities"]])
    print("  watcher:", "PASS" if assert_no_citation_entities(hardened) else "FAIL")
