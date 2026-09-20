"""Two-sided wildcard fill for the marker chain (arch addendum, 2026-09-20).

A `?`, a Greek-shaped glyph, or a j/v does not mean "this page is illegal". It means the READER could not
see the letter. The chain invariant often already knows it. But a one-sided fill is unfalsifiable: with only
a right anchor, ANY wildcard count yields a legal run (five `?` before `z` fill as t..y, seven as r..y), so
the gate would pass everything and stop being a gate. A fill is therefore CONFIRMED only when pinned on BOTH
sides and the wildcard count equals the alphabet gap between the anchors.

  left anchor  = the previous known letter IN THIS PAGE, or the previous page's last chain-confirmed letter
  right anchor = the next known letter in this page
  confirmed    <=> len(run) == gap(left, right)      [24-letter alphabet, wrap-aware]

One-sided fills are recorded as `proposed` and never count toward a confirmed page or a recovery number,
whatever the matcher says about them. This module fills; it does not read glyphs. Confirming a FILLED letter
against its printed glyph is the confusable-margin matcher's job in verifier mode (zero-wrong, abstains).

What this does NOT solve: it cannot invent the left anchor. A leading wildcard run on a page whose left
neighbour was never extracted is one-sided by construction, so the arithmetic that looks decisive on paper
(p129's six `?` before `z`) yields `proposed` until p128 is read.
"""
import marker_alphabet as MA

_TWINS = ("j", "v")  # merged-twin glyphs: an output j/v means the reader could not resolve i/j or u/v


def classify(marker):
    """('letter', normalized) for a readable marker, ('wild', reason) for one the reader could not resolve."""
    m = (marker or "").strip()
    if not m:
        return ("wild", "empty")
    if m == "?":
        return ("wild", "unread")
    if len(m) != 1 or not m.isalpha():
        return ("wild", "symbol")
    lo = m.lower()
    if not ("a" <= lo <= "z"):
        return ("wild", "non-latin")      # Greek-shaped etc.
    if lo in _TWINS:
        return ("wild", "merged-twin")
    return ("letter", MA.normalize(lo))


def _gap(left, right):
    """Number of letters strictly BETWEEN left and right in the 24-letter alphabet, wrap-aware."""
    a, b = MA.index(left), MA.index(right)
    if a < 0 or b < 0:
        return None
    return (b - a) % len(MA.ALPHABET) - 1


def _spans_reset(left, n):
    """True if the arithmetic fill from `left` would step onto 'a'. A wrap to 'a' is legal after z, but a
    reset to 'a' is also how a new chapter starts -- the two are indistinguishable from letters alone, so a
    fill that would traverse 'a' is never confirmed."""
    return "a" in MA.run(left, n + 1)[1:]


def fill_page(marker_letters, prev_page_last=None, page=None, reset_pages=(), anomaly_pages=()):
    """Fill wildcard runs from the chain. Returns:
      {page, verdict, letters, runs: [...], n_confirmed_fills, n_proposed_fills, n_mismatch}
    verdict:
      confirmed      every wildcard run was two-sided and the filled sequence is a valid chain
      proposed       at least one run was one-sided; nothing here counts toward a recovery number
      count-mismatch a two-sided run's wildcard count != the alphabet gap -> Chris's queue
      no-wildcards   delegate to the frozen page_chain_status
    """
    marks = list(marker_letters or [])
    kinds = [classify(m) for m in marks]
    if not any(k == "wild" for k, _ in kinds):
        return {"page": page, "verdict": "no-wildcards", "letters": [v for _, v in kinds],
                "runs": [], "n_confirmed_fills": 0, "n_proposed_fills": 0, "n_mismatch": 0}

    letters = [v if k == "letter" else None for k, v in kinds]
    runs, i = [], 0
    while i < len(letters):
        if letters[i] is not None:
            i += 1
            continue
        j = i
        while j < len(letters) and letters[j] is None:
            j += 1
        left = letters[i - 1] if i > 0 else prev_page_last
        left_src = "in-page" if i > 0 else ("prev-page" if prev_page_last else None)
        right = letters[j] if j < len(letters) else None
        runs.append({"start": i, "n": j - i, "left": left, "left_src": left_src, "right": right,
                     "reasons": [r for k, r in kinds[i:j] if k == "wild"]})
        i = j

    n_conf = n_prop = n_mis = 0
    for r in runs:
        if page is not None and page in set(reset_pages):
            r["status"], r["why"] = "proposed", "page carries a recorded reset; arithmetic may not bridge it"
            n_prop += 1; continue
        if page is not None and page in set(anomaly_pages):
            r["status"], r["why"] = "proposed", "page carries a recorded compositor anomaly; gap is not strict"
            n_prop += 1; continue
        if r["left"] and r["right"]:
            need = _gap(r["left"], r["right"])
            r["need"] = need
            if need != r["n"]:
                r["status"] = "count-mismatch"
                r["why"] = "%d wildcards but gap(%s,%s)=%s" % (r["n"], r["left"], r["right"], need)
                n_mis += 1; continue
            if _spans_reset(r["left"], r["n"]):
                r["status"], r["why"] = "proposed", "fill would traverse 'a' (wrap vs reset is ambiguous)"
                n_prop += 1; continue
            r["fill"] = MA.run(r["left"], r["n"] + 1)[1:]
            r["status"], r["why"] = "confirmed", "two-sided: gap matches wildcard count"
            n_conf += 1
        else:
            r["status"] = "proposed"
            r["why"] = "one-sided (%s anchor missing)" % ("left" if not r["left"] else "right")
            n_prop += 1

    out = list(letters)
    for r in runs:
        if r.get("status") == "confirmed":
            out[r["start"]:r["start"] + r["n"]] = r["fill"]

    if n_mis:
        verdict = "count-mismatch"
    elif n_prop:
        verdict = "proposed"
    elif all(x is not None for x in out) and MA.is_consecutive_run(out):
        verdict = "confirmed"
    else:
        verdict = "count-mismatch"
    return {"page": page, "verdict": verdict, "letters": out, "runs": runs,
            "n_confirmed_fills": n_conf, "n_proposed_fills": n_prop, "n_mismatch": n_mis}
