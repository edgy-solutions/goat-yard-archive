# -*- coding: utf-8 -*-
"""signature_unattested -- a SECOND-LOOK MARKER on a signed row. ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).

THE FACT. A row's in-crop derived string (what the signer's per-tile verdicts add up to, with the not-in-crop
brackets removed) is ATTESTED if some channel actually produced that string, or the row's own note supplies it.
It is UNATTESTED when no channel ever read it and the note does not hold it: a string that exists only because the
signer typed it. That is when Chris wants a second look before the string is admitted as truth.

ATTESTATION ONLY. No dictionary, no word-likeness, no linguistic heuristic anywhere in this file. Two sources:

  1. CHANNELS THAT READ THE CROP. In the export, exactly one: the CANDIDATE (the local whole-band read), which is
     reconstructable from the tiles' `shown` letters (consonant tiles; a gap tile is a space). It is compared to the
     derived string over the tiles that are IN the crop (a not-in-crop tile is dropped from both sides: that is a
     statement about the box, not a different reading). So with the candidate as the only channel the flag REDUCES
     TO "the derived string differs from the candidate on the in-crop tiles" -- i.e. the signer corrected, deleted
     or inserted something. The signer's stored-alternative-reads loader found 0 usable reads at this aperture for
     this set (sidecar `alternatives.reads_usable`), so there is no second read to add; `channels` below is the
     list actually used, per row, and says so.
  2. THE NOTE. Exact string containment only: the derived string's whitespace-separated words appear, in order and
     adjacent, among the note's Hebrew-letter words (nikud and cantillation stripped from the note, nothing else
     normalised). A note with no Hebrew in it, e.g. only Latin prose, supplies nothing.

NOT APPLICABLE (flag is None, never False) when the row has no in-crop signature: any tile or insertion still
unanswered leaves a `?` in the derived string, which is not a string anyone could attest.

WHAT THIS DOES NOT DO. It never chooses between two readings, never blocks or holds a row on its own (the
dispositions in ingest_pass2.py do not read it), and never feeds a score. It does not discriminate a regression
from a fix: a signer's correction is unattested whether it is right or wrong. Measured on the p493:n3 reversal,
BOTH the pass-2 string and the pass-3 string are flagged, and that row's note has no Latin gloss, so there is no
gloss-derived expectation at all.
"""
import re
import unicodedata

HEB_LETTER = re.compile(u"[\u05d0-\u05ea]")
_MARK = re.compile(u"[\u0591-\u05c7]")           # cantillation + points + maqaf-class marks


def tile_out(t):
    v, gap = t.get("verdict") or "", t["kind"] == "gap"
    if v == "deleted":
        return ""
    if v == "not_in_crop":
        return "[ ]" if gap else "[" + t["shown"] + "]"
    if v in ("confirmed", "sic"):
        return " " if gap else t["shown"]
    if v == "corrected":
        if gap:
            return " " if t.get("chose") == "space" else ""
        return t.get("chose") or "?"
    return "?"


def ins_out(it):
    v = it.get("verdict") or ""
    if v == "deleted":
        return ""
    if not it.get("chose"):
        return "?"
    if v == "not_in_crop":
        return "[ ]" if it["kind"] == "gap" else "[" + it["chose"] + "]"
    return " " if it["kind"] == "gap" else it["chose"]


def derive_in_crop(row):
    """The row's derived string with the bracketed not-in-crop spans removed (own port, tiles + insertions)."""
    ins = row.get("insertions") or []
    out = [ins_out(x) for x in sorted((x for x in ins if x["after_i"] is None), key=lambda x: x["seq"])]
    for t in row["tiles"]:
        out.append(tile_out(t))
        out.extend(ins_out(x) for x in sorted((x for x in ins if x["after_i"] == t["i"]), key=lambda x: x["seq"]))
    return re.sub(r"\[[^\]]*\]", "", "".join(out))


def candidate_in_crop(row):
    """The candidate (local whole-band read) restricted to the tiles that are in the crop."""
    return "".join((t["shown"] if t["kind"] == "consonant" else " ")
                   for t in row["tiles"] if (t.get("verdict") or "") != "not_in_crop")


def note_words(note):
    """Hebrew-letter words in the note, nikud/cantillation stripped, split on anything that is not a Hebrew letter."""
    s = _MARK.sub("", unicodedata.normalize("NFC", note or ""))
    return [w for w in re.split(u"[^\u05d0-\u05ea]+", s) if w]


def _contiguous(words, hay):
    n = len(words)
    return n > 0 and any(hay[i:i + n] == words for i in range(len(hay) - n + 1))


def attest(row, in_crop=None):
    """Return the per-row record. `in_crop` lets a caller that already holds the derived string pass it in."""
    d = derive_in_crop(row) if in_crop is None else in_crop
    rec = {"derived_in_crop": d, "channels": ["candidate"],
           "channels_note": "only the candidate (local whole-band read) is in the export; the stored-alternative "
                            "reads loader found 0 usable reads at this aperture for this set",
           "n_note_hebrew_words": len(note_words(row.get("note")))}
    if "?" in d or not d.strip():
        rec.update(applicable=False, signature_unattested=None, attested_by=[],
                   why="no in-crop signature (an unanswered item leaves '?', or nothing is in the crop)")
        return rec
    by = []
    if d == candidate_in_crop(row):
        by.append("candidate")
    words = d.split()
    if _contiguous(words, note_words(row.get("note"))):
        by.append("note")
    rec.update(applicable=True, attested_by=by, signature_unattested=not by)
    return rec


def rate(rows):
    """(n_rows, n_applicable, n_unattested) over export rows."""
    recs = [attest(r) for r in rows]
    app = [x for x in recs if x["applicable"]]
    return len(recs), len(app), sum(1 for x in app if x["signature_unattested"])


if __name__ == "__main__":
    import io
    import json
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    for path in sys.argv[1:]:
        rows = [json.loads(l) for l in io.open(path, encoding="utf-8") if l.strip()]
        n, na, nu = rate(rows)
        print("%s: %d rows, %d applicable, %d unattested  (%.1f%% of rows, %.1f%% of applicable)"
              % (path.replace("\\", "/").split("/")[-1], n, na, nu, 100.0 * nu / n, 100.0 * nu / max(na, 1)))
        for r in rows:
            x = attest(r)
            print("  %-9s applicable=%-5s unattested=%-5s attested_by=%s note_hebrew_words=%d  derived=%r"
                  % (r["span_id"], x["applicable"], x["signature_unattested"], x["attested_by"],
                     x["n_note_hebrew_words"], x["derived_in_crop"]))
