"""Stage-3 AUTHORITY-LIST check — deterministic safety net for the citation-name misread class
(Gersom->Gerson, the model's prior winning over worn type). A transcribed capitalized token that
FUZZY-matches Gill's citation universe (profile `authorities`) but is NOT exact = candidate misread,
flagged to the review queue with the nearest authority + ratio. Pure code, no model. The stage-1
sound crop already fixes many (p702 Gerson); this catches the ones it doesn't, corpus-wide.

Flags are PROPOSALS (review-queue), not auto-corrections — a genuine new name absent from the seed
list would false-flag, and the seed list grows from the corpus's own CitedAuthority entities.
"""
import re, difflib

_TOKEN = re.compile(r"[A-Z][A-Za-zëéèäöü'\-]{3,}")

def check_note(text, authorities, lo=0.80, hi=1.0):
    """Return [{token, nearest, ratio}] for near-miss author names (lo <= ratio < hi = suspicious)."""
    aset = set(authorities); flags = []
    for tok in _TOKEN.findall(text):
        if tok in aset: continue
        m = difflib.get_close_matches(tok, authorities, n=1, cutoff=lo)
        if not m: continue
        ratio = difflib.SequenceMatcher(None, tok, m[0]).ratio()
        if lo <= ratio < hi:
            flags.append({"token": tok, "nearest": m[0], "ratio": round(ratio, 2)})
    return flags

def check_page(notes, profile):
    authorities = profile.get("authorities", [])
    out = []
    for n in notes:
        for f in check_note(n["text"], authorities):
            out.append({"marker": n.get("marker"), **f})
    return out

if __name__ == "__main__":
    import sys, yaml
    from pathlib import Path
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    prof = yaml.safe_load((Path(__file__).parent / "book_profile.gill.yaml").read_text(encoding="utf-8"))
    A = prof["authorities"]
    tests = [
        "T. Bab. Eruvin, fol. 82. 2. Misn. Negáim, c. 12. sect. 4. Gerson in loc.",   # Gerson -> Gersom
        "clausit viam illis, Pagninus, præclusit sese illis, Vatablus.",              # exact -> no flag
        "Vid. Scheuchzer. Physic. Sacr.",                                             # exact -> no flag
        "quia erit, Pagnin, Montanus, Drusius.",                                      # Pagnin -> Pagninus
    ]
    for t in tests:
        print(repr(t[:50]), "->", check_note(t, A))
