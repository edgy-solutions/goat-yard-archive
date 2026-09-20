"""Marker-LETTER assertion for the reset fixtures (Chris, 2026-09-20).

The born-test proved the seam reproduced COUNT and STRUCTURE. That is not enough: a page can carry the
right number of notes in the right shape and still have every marker letter wrong, and the marker chain
is the count authority — so a wrong letter is a wrong authority, silently.

This asserts the run's persisted `marker_letter` per note against the RATIFIED record in
`audits/marker_resets_observed.json` — which stands; the run is what is on trial. Two checks per fixture:

  letters  the flat sequence, position by position  (the k-th note's letter)
  series   the reset segmentation implied by the letters, against the record's `|` segmentation

Only `confidence: high` records with an unannotated `letters_read` are assertable; anything carrying a
parenthetical caveat (p404's "a at ChI top, not cropped") is reported UNASSERTABLE, never silently passed.

This module holds no expectations about passing. See test_born_fixtures.py for the expected-red status.
"""
import json, re
from pathlib import Path

RESETS = Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits/marker_resets_observed.json")


def load_records(path=RESETS):
    """{file_page: record} from the ratified reset observations."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return {r["file_page"]: r for r in d.get("resets_observed", [])}, d.get("offset_file_minus_printed")


def expected_series(letters_read):
    """'c | a,b,c,d' -> [['c'], ['a','b','c','d']]. Returns None if the field carries a caveat, so an
    annotated record is never turned into a silent expectation."""
    if letters_read is None:
        return None
    if re.search(r"[()]", letters_read):
        return None
    segs = [[t.strip().lower() for t in seg.split(",") if t.strip()]
            for seg in letters_read.split("|")]
    segs = [s for s in segs if s]
    if not segs or any(len(t) != 1 or not t.isalpha() for s in segs for t in s):
        return None
    return segs


def observed_series(letters):
    """Segment observed letters at each 'a' that is not first — the same auto-detected reset rule the
    sequence gate uses, so 'series' means the same thing on both sides of the comparison."""
    segs, cur = [], []
    for i, L in enumerate(letters):
        if L == "a" and i != 0:
            segs.append(cur); cur = [L]
        else:
            cur.append(L)
    if cur:
        segs.append(cur)
    return [s for s in segs if s]


def check_page(page, observed_letters, records=None):
    """Assert one fixture. Returns a dict; `ok` is None when the record is not assertable."""
    if records is None:
        records, _ = load_records()
    rec = records.get(page)
    if rec is None:
        return {"page": page, "ok": None, "why": "no ratified record for this page"}
    exp_segs = expected_series(rec.get("letters_read"))
    if exp_segs is None:
        return {"page": page, "ok": None, "why": "record not assertable (caveat or malformed letters_read)",
                "letters_read": rec.get("letters_read"), "confidence": rec.get("confidence")}

    exp_flat = [L for s in exp_segs for L in s]
    obs = [(L or "?").strip().lower() for L in (observed_letters or [])]
    obs_segs = observed_series(obs)

    n_ok = len(obs) == len(exp_flat)
    mism = [] if not n_ok else [
        {"k": k, "expected": e, "observed": o} for k, (e, o) in enumerate(zip(exp_flat, obs)) if e != o]
    letters_ok = n_ok and not mism
    series_ok = [len(s) for s in obs_segs] == [len(s) for s in exp_segs]

    return {"page": page, "printed_page": rec.get("printed_page"), "book": rec.get("book"),
            "confidence": rec.get("confidence"), "letters_read": rec.get("letters_read"),
            "expected_series": exp_segs, "expected_flat": exp_flat,
            "observed_flat": obs, "observed_series": obs_segs,
            "count_ok": n_ok, "expected_n": len(exp_flat), "observed_n": len(obs),
            "letters_ok": letters_ok, "series_ok": series_ok,
            "mismatches": mism,
            "ok": bool(letters_ok and series_ok and n_ok)}


def letters_from_run(run_jsonl, page):
    """The persisted marker_letter sequence for one page out of a born-test run jsonl."""
    for line in Path(run_jsonl).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("kind") == "config_header" or r.get("page") != page:
            continue
        return [(n.get("marker_letter") or n.get("marker") or "?") for n in (r.get("notes") or [])]
    return None
