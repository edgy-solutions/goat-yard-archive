"""AGREEMENT LADDER — tiered comparison of two independent model readings of one apparatus strip.
Cheapest-most-deterministic first; a disagreement high on the ladder makes the lower rungs moot
(same tiered logic as retrieval). Three rungs:

  1. NOTE COUNT   — n_a vs n_b (the census structural gate: n_primary != n_second). A count mismatch
                    means the notes don't align; stop — per-note comparison is meaningless.
  2. SCRIPT SET   — per aligned note, does it contain the SAME set of scripts (Latin/Hebrew/Greek/
                    Arabic)? Pure Unicode-range comparison, NO text judgment. This rung catches the
                    DROPPED-LEMMA class exactly: reading A keeps the Hebrew headword, reading B drops
                    it -> the note's script-set differs (hebrew present vs absent) with zero text diff.
  3. TEXT         — token overlap, and ONLY within notes that cleared rungs 1-2.

Also a partial GLYPH-WITNESS (still-owed): two models independently reporting "Hebrew present in note
k" is a decent witness Hebrew is there; both reporting its absence where the crop has RTL ink is the
miss-signal. Doesn't fully close the invisible-loss denominator (correlated omission remains), but
narrows it for free. Deterministic; no model calls.
"""
import re

SCRIPT_RANGES = {
    "hebrew": (0x0590, 0x05FF),
    "greek":  (0x0370, 0x03FF),
    "arabic": (0x0600, 0x06FF),
    "syriac": (0x0700, 0x074F),
}
_LATIN = re.compile(r"[A-Za-z]")

def scripts_in(text):
    """Frozenset of scripts present in `text` (Unicode ranges; 'latin' via A-Za-z)."""
    found = set()
    if _LATIN.search(text or ""): found.add("latin")
    for ch in text or "":
        cp = ord(ch)
        for name, (lo, hi) in SCRIPT_RANGES.items():
            if lo <= cp <= hi: found.add(name)
    return frozenset(found)

def _tokens(text):
    return set(re.findall(r"[A-Za-z֐-׿Ͱ-Ͽ؀-ۿ]+", text or ""))

def _text(note):
    return note["text"] if isinstance(note, dict) else note

def ladder(notes_a, notes_b, text_overlap_min=0.5):
    """Compare two readings (each a list of note strings or {'text':...} dicts). Returns a dict:
      rung        : 'count' | 'script' | 'text' | 'agree'  (highest rung that found a disagreement)
      count       : (n_a, n_b)
      script_diffs: [{note, a_scripts, b_scripts, dropped}]  (rung 2; 'dropped' = scripts in one not the other)
      text_diffs  : [{note, overlap}]  (rung 3, only for notes that cleared rung 2)
    """
    a = [_text(n) for n in (notes_a or [])]
    b = [_text(n) for n in (notes_b or [])]
    if len(a) != len(b):
        return {"rung": "count", "count": (len(a), len(b)),
                "script_diffs": [], "text_diffs": [], "agree": False}
    script_diffs = []
    for i, (na, nb) in enumerate(zip(a, b)):
        sa, sb = scripts_in(na), scripts_in(nb)
        if sa != sb:
            script_diffs.append({"note": i, "a_scripts": sorted(sa), "b_scripts": sorted(sb),
                                 "dropped": sorted((sa | sb) - (sa & sb))})
    if script_diffs:
        return {"rung": "script", "count": (len(a), len(b)),
                "script_diffs": script_diffs, "text_diffs": [], "agree": False}
    text_diffs = []
    for i, (na, nb) in enumerate(zip(a, b)):
        ta, tb = _tokens(na), _tokens(nb)
        ov = len(ta & tb) / max(1, len(ta | tb))
        if ov < text_overlap_min:
            text_diffs.append({"note": i, "overlap": round(ov, 2)})
    rung = "text" if text_diffs else "agree"
    return {"rung": rung, "count": (len(a), len(b)),
            "script_diffs": [], "text_diffs": text_diffs, "agree": not text_diffs}

def dropped_lemma_notes(notes_a, notes_b):
    """The dropped-lemma signal specifically: aligned notes where one reading has a non-Latin script
    the other lacks. Empty if counts differ (rung-1 gate) or no script disagreement."""
    r = ladder(notes_a, notes_b)
    if r["rung"] == "count": return []
    return [d for d in r["script_diffs"] if set(d["dropped"]) & set(SCRIPT_RANGES)]

if __name__ == "__main__":
    import sys
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    # dropped-lemma: gemma keeps the Hebrew headword, qwen3.8 drops it -> script rung fires, no text diff
    gemma = ["אנשים אחים אנחנו viri fratres vos", "Nic. Abram. p. 59."]
    qwen  = ["viri fratres vos", "Nic. Abram. p. 59."]
    print("dropped-lemma ->", ladder(gemma, qwen)["rung"], ladder(gemma, qwen)["script_diffs"])
    print("count mismatch ->", ladder(["a", "b", "c"], ["a", "b"])["rung"])
    print("clean agree ->", ladder(gemma, gemma)["rung"])
