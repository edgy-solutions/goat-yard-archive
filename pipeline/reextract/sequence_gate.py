"""The sequence gate as the COUNT AUTHORITY (config-v2, Chris 2026-09-14). The note-start detector is retired
as a counter — it is a strong POSITION signal but over-counts (it fired 13 body lines as notes on p89). The
count authority is now v2's own output validated by the marker chain: a page whose persisted marker_letters
form a VALID chain (consecutive in the 24-letter alphabet, wrap-aware, with an auto-detected reset to 'a')
IS its own count. Where the chain does not validate — a misread, an illegal marker (Greek/symbol/j/v), or a
structure this page-local check can't resolve — the gate ABSTAINS (confirmed=False) and the page falls to the
detector's boxes + a witness (gemma / human). Abstain-never-guess: a page never gets a confirmed count from a
chain it couldn't verify.

This is deliberately page-LOCAL (no body alignment): it confirms the strong, clean majority cheaply and hands
the ambiguous minority to the fallback. Reset points from body alignment (the full segmented gate) remain the
authority when they exist; this is the count-authority layer that runs on every page from the marker_letters
alone."""
import marker_alphabet as MA

_ILLEGAL = "jv"  # legal-alphabet twins that must not appear as an output (i/j, u/v merged)


def _clean(markers):
    """(normalized lowercase letters, illegal_or_symbol_markers). '?' and non-alphabet (Greek α, symbols) are
    illegal; j/v are the merged twins and also illegal as printed output."""
    norm, bad = [], []
    for m in markers or []:
        if not m or len(m) != 1 or not m.isalpha() or not ("a" <= m.lower() <= "z"):
            bad.append(m); continue
        lo = m.lower()
        if lo in _ILLEGAL:
            bad.append(m); continue
        norm.append(MA.normalize(lo))
    return norm, bad


def _segments_at_resets(letters):
    """Split a letter run into segments at each 'a' that is NOT the first letter (an auto-detected reset). A
    single run with no interior 'a' is one segment. Each segment must be individually consecutive."""
    segs, cur = [], []
    for i, L in enumerate(letters):
        if L == "a" and i != 0:
            segs.append(cur); cur = [L]
        else:
            cur.append(L)
    if cur:
        segs.append(cur)
    return segs


def page_chain_status(marker_letters):
    """The count-authority verdict for one page from its notes' marker_letters (in reading order). Returns:
      {confirmed: bool, count: int|None, status: str, illegal: [...], n_notes: int, segments: [...]}
    status:
      valid-chain        one consecutive run (a,b,c…, wrap-aware) — count CONFIRMED = n_notes.
      valid-with-reset   consecutive segments split at an auto-detected reset to 'a' (e.g. c | a,b,c,d) —
                         CONFIRMED = n_notes.
      illegal-markers    a Greek/symbol/?/j/v marker present — ABSTAIN (a marker misread or a non-letter class).
      broken-chain       legal letters that don't form consecutive run(s) — ABSTAIN (a misread or a dropped note).
      too-few            0–1 notes — nothing to validate as a chain; not confirmable this way (fallback).
    A confirmed page's count is authoritative; an abstained page falls to the detector boxes + a witness."""
    n = len(marker_letters or [])
    letters, bad = _clean(marker_letters)
    if bad:
        return {"confirmed": False, "count": None, "status": "illegal-markers",
                "illegal": bad, "n_notes": n, "segments": []}
    if len(letters) < 2:
        return {"confirmed": False, "count": None, "status": "too-few",
                "illegal": [], "n_notes": n, "segments": [letters]}
    if MA.is_consecutive_run(letters):
        return {"confirmed": True, "count": n, "status": "valid-chain",
                "illegal": [], "n_notes": n, "segments": [letters]}
    segs = _segments_at_resets(letters)
    if len(segs) > 1 and all(MA.is_consecutive_run(s) for s in segs):
        return {"confirmed": True, "count": n, "status": "valid-with-reset",
                "illegal": [], "n_notes": n, "segments": segs}
    return {"confirmed": False, "count": None, "status": "broken-chain",
            "illegal": [], "n_notes": n, "segments": segs}
