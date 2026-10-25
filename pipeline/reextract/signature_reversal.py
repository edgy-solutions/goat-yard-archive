# -*- coding: utf-8 -*-
u"""`signature_suspect: reversed` -- a code-owned flag over SIGNED spans.  No spend, no network.

Ruling A(2) 2026-10-25: *"Run now, no spend, before the resolution probe: for every signed span
(45 + 19), flag `signature_suspect: reversed` where read == reverse(signature) exactly or with one
swap from the confusable list.  Report the count and the row ids.  Any hit goes to Chris as a glyph
card with tiles numbered in reading order."*

The cause is given by ruling A(1), which adjudicated p442:n0: *"glyphs signed in visual
left-to-right order, dalet taken as final kaf."*  So this is not a per-row slip, it is a defect of
the signing instrument, and the population to scan is every signature the instrument produced.

WHAT THIS DOES NOT DO.  It never edits a signature and it exposes no function that returns one.  A
hit is a request for a human glyph card, exactly as the ruling says -- the same discipline as
`confusable_vocab`, where membership is a witness and never a verdict.

TWO TRAPS THIS MODULE EXISTS TO AVOID
-------------------------------------
1. **A short string sits near its own reverse by construction.**  For a 3-consonant signature,
   `read == signature` is at Hamming distance 2 from `reverse(signature)`: positions 0 and 2 swap
   and position 1 is fixed.  Measured over this population, 31 of the 34 reads at distance 2 were
   reads that matched the signature *forward*.  A distance band is therefore not a detector; a read
   that already matches the signature is EXCLUDED by cause, not scored.
2. **A read can be no further from the signature than from its reverse.**  Then calling it a
   reversal is unwarranted -- it is just a misread, and the reversal story is the more flattering of
   two available explanations.  Such a read is excluded as `ambiguous_basis`, with both distances
   recorded, so the exclusion can be audited rather than trusted.

SEALED PAGES.  This reads the signed *string* out of `TRUTH` / `SEALED_TRUTH` and the recorded
reads out of committed jsonl.  No page is opened, no crop is cut, no model is called, nothing is
re-scored.  The hard constraint on SEALED pages is about spending them again; a flag computed over
a string the signer already produced does not touch them.  Ruling A(2) names the 45 + 19 population
explicitly.

All page numbers are FILE pages (printed = file - 88).
"""
import io
import json
import os
import re
import sys
import unicodedata

import confusable_vocab as V
import hebrew_aperture_diag as diag

DATA = str(diag.DATA)

#: Hebrew consonants only.  Everything else -- nikud, spaces, the hyphen in "ברא - לעשות", the
#: bracket notation of an out-of-crop signature, any Latin -- is dropped, because a reversal is a
#: claim about GLYPH ORDER and a separator has no order of its own.
LETTER = re.compile(u"[א-ת]")
NIKUD = re.compile(u"[֑-ׇ]")

#: Every read source scanned, with the field the read text lives in.  Listed explicitly rather than
#: globbed so the population is reproducible and a new file cannot silently join or leave it.
#: `hebrew_frontier_or_notext_20261004_FAULTED_1100.jsonl` is deliberately ABSENT: a run-level fault
#: invalidates the run, and a faulted run's reads are not evidence about anything (run-level-fault).
READ_SOURCES = (
    ("score45_reads_501ab577a18a6785.jsonl", ("hebrew",)),
    ("hebrew_context_axes_reads_20261004.jsonl", ("gated", "raw")),
    ("hebrew_aperture_reads_20260920.jsonl", ("gated", "raw")),
    ("hebrew_frontier_or_reads_20260927.jsonl", ("hebrew", "gated", "raw")),
    ("hebrew_frontier_or_notext_20261004.jsonl", ("hebrew", "gated", "raw")),
    ("hebrew_frontier_or_notext_rep_20261004.jsonl", ("hebrew", "gated", "raw")),
    ("hebrew_local_arms_reads_20260920.jsonl", ("gated", "raw")),
    ("hebrew_pad_probe_reads_20261004.jsonl", ("hebrew", "gated", "raw")),
)

#: The two signed populations ruling A(2) names.  45 = run 501ab577a18a6785 (SCORE45 rows).
#: 19 = the sitting population, whose signed strings live in code as TRUTH + SEALED_TRUTH.
SCORE45 = "SCORE45_501ab577a18a6785.json"


# ----------------------------------------------------------------------------- string normalisation
def consonants(s):
    u"""The Hebrew consonant sequence of `s`, in stored order.  [] for anything else."""
    s = NIKUD.sub(u"", unicodedata.normalize("NFC", s or u""))
    return LETTER.findall(s)


def words(s):
    u"""Consonant runs of `s`, split on anything that is not a Hebrew letter."""
    s = NIKUD.sub(u"", unicodedata.normalize("NFC", s or u""))
    return [consonants(w) for w in re.split(u"[^א-ת]+", s) if consonants(w)]


def reverse_all(cs):
    u"""Visual-left-to-right misreading of a whole span: every glyph in the opposite order."""
    return list(reversed(cs))


def reverse_per_word(s):
    u"""The other way the same mistake lands: word order kept, letters reversed inside each word.

    A signer working left to right through a crop can reverse the span or reverse each word; the two
    differ as soon as there is more than one word, and which one fits is evidence about HOW the
    instrument was misused.  Reported as a separate basis, never merged with the other."""
    out = []
    for w in words(s):
        out.extend(reversed(w))
    return out


def diffs(a, b):
    u"""Positions where equal-length sequences differ, as (index, a, b).  None if lengths differ."""
    if len(a) != len(b):
        return None
    return [(i, x, y) for i, (x, y) in enumerate(zip(a, b)) if x != y]


# --------------------------------------------------------------------------------------- the flag
#: Causes a read is not scored.  Each is a NAMED exclusion, because "not flagged" and "could not be
#: tested" are different facts and a count that merges them is a count of nothing.
EXCLUSIONS = (
    "empty_read",
    "empty_signature",
    "read_equals_signature",
    "palindrome_signature",
    "length_mismatch",
    "ambiguous_basis",
)

#: Verdicts.  The first two are ruling A(2)'s hits.  The third is NOT: it is the same shape with a
#: pair the vocabulary does not carry, and it is reported separately because the founding case
#: p442:n0 was exactly that -- dalet/final-kaf was in no register until ruling A(1) named it, so the
#: rule as literally written would have fired on nothing at all, including its own instance.
VERDICTS = (
    "reversed_exact",
    "reversed_one_swap",
    "reversed_one_swap_unlisted",
    "reversed_per_word_exact",
)


def examine(signature, read):
    u"""One read against one signature.  Returns a record; raises nothing; decides nothing.

    `flag` is None, an exclusion name, or a verdict name.  Both distances are always reported so an
    exclusion can be checked instead of believed."""
    sig_cs = consonants(signature)
    read_cs = consonants(read)
    rev = reverse_all(sig_cs)
    perword = reverse_per_word(signature)
    rec = {
        "signature_cons": u"".join(sig_cs),
        "read_cons": u"".join(read_cs),
        "reverse_cons": u"".join(rev),
        "reverse_per_word_cons": u"".join(perword),
        "n_cons": len(sig_cs),
        "dist_to_signature": None,
        "dist_to_reverse": None,
        "swap": None,
        "registers": [],
        "flag": None,
    }
    if not read_cs:
        rec["flag"] = "empty_read"
        return rec
    if not sig_cs:
        rec["flag"] = "empty_signature"
        return rec

    d_fwd = diffs(sig_cs, read_cs)
    d_rev = diffs(rev, read_cs)
    rec["dist_to_signature"] = None if d_fwd is None else len(d_fwd)
    rec["dist_to_reverse"] = None if d_rev is None else len(d_rev)

    if read_cs == sig_cs:
        # trap 1: this read is at distance len(sig)-something from the reverse purely because the
        # string is short.  It is not a reversal suspect, it is a correct read.
        rec["flag"] = "read_equals_signature"
        return rec
    if rev == sig_cs:
        # the test cannot discriminate: a reversal of this signature is the signature
        rec["flag"] = "palindrome_signature"
        return rec

    if d_rev is None:
        if perword == read_cs and perword != rev:
            rec["flag"] = "reversed_per_word_exact"
            return rec
        rec["flag"] = "length_mismatch"
        return rec

    if len(d_rev) == 0:
        rec["flag"] = "reversed_exact"
        return rec

    # trap 2: the reverse must be STRICTLY the better explanation, or this is just a misread
    if d_fwd is not None and len(d_rev) >= len(d_fwd):
        rec["flag"] = "ambiguous_basis"
        return rec

    if len(d_rev) == 1:
        i, want, got = d_rev[0]
        # Hebrew is STORED in logical order, so index i of the candidate reading is the (i+1)th
        # glyph read.  The same glyph sits at stored index len-1-i of the SIGNED string, which is
        # the number a glyph card must carry if Chris is to find the tile that went wrong.
        rec["swap"] = {"position_in_candidate": i,
                       "reading_position": i + 1,
                       "position_in_signature": len(rev) - 1 - i,
                       "reverse_has": want, "read_has": got,
                       "pair": V.name(want, got)}
        rec["registers"] = V.registers(want, got)
        rec["flag"] = "reversed_one_swap" if rec["registers"] else "reversed_one_swap_unlisted"
        return rec

    if perword == read_cs and perword != rev:
        rec["flag"] = "reversed_per_word_exact"
        return rec
    return rec


# ------------------------------------------------------------------------------- the two populations
def signed_spans():
    u"""span_id -> (signature, provenance).  The 45 of run 501ab577a18a6785 plus the 19 signed in
    code.  A span in both keeps the SCORE45 string and records that it was in both."""
    out = {}
    p = os.path.join(DATA, SCORE45)
    if not os.path.exists(p):
        raise IOError("the 45-span signed record is missing, so the population cannot be built: %s" % p)
    for r in json.load(io.open(p, encoding="utf-8"))["rows"]:
        out[r["span_id"]] = (r["signature"], "SCORE45:" + SCORE45)
    both = dict(diag.TRUTH)
    both.update(diag.SEALED_TRUTH)
    for sid, val in both.items():
        s = val[0] if isinstance(val, (tuple, list)) else val
        if sid in out:
            out[sid] = (out[sid][0], out[sid][1] + "+TRUTH")
        else:
            out[sid] = (s, "TRUTH/SEALED_TRUTH")
    return out


def recorded_reads():
    u"""[(span_id, source, model, cell, text)] over every declared read source."""
    rows = []
    for fname, fields in READ_SOURCES:
        p = os.path.join(DATA, fname)
        if not os.path.exists(p):
            raise IOError("a declared read source is missing; the population would silently shrink: "
                          "%s" % p)
        for line in io.open(p, encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            if "span_id" not in r:
                continue            # run header / footer
            txt = None
            for f in fields:
                if r.get(f):
                    txt = r[f]
                    break
            if not txt:
                continue
            rows.append((r["span_id"], fname,
                         r.get("arm") or r.get("model") or "?",
                         r.get("channel") or r.get("cell") or r.get("aperture") or "?",
                         txt))
    return rows


def scan():
    u"""The whole ruling-A(2) scan.  Returns (hits, unlisted, excluded_counter, meta)."""
    sigs = signed_spans()
    reads = recorded_reads()
    hits, unlisted, other = [], [], []
    counts = {}
    n_compared = 0
    spans_seen = set()
    for span, src, model, cell, txt in reads:
        if span not in sigs:
            counts["span_not_signed"] = counts.get("span_not_signed", 0) + 1
            continue
        spans_seen.add(span)
        sig, prov = sigs[span]
        rec = examine(sig, txt)
        rec.update({"span_id": span, "source": src, "model": model, "cell": cell,
                    "signature": sig, "read": txt, "provenance": prov,
                    "page_file": int(span.split(":")[0][1:]),
                    "page_printed": int(span.split(":")[0][1:]) - 88})
        flag = rec["flag"]
        counts[flag or "no_match"] = counts.get(flag or "no_match", 0) + 1
        if flag in ("reversed_exact", "reversed_one_swap", "reversed_per_word_exact"):
            hits.append(rec)
        elif flag == "reversed_one_swap_unlisted":
            unlisted.append(rec)
        if flag not in EXCLUSIONS:
            n_compared += 1
        other.append(rec)
    meta = {"n_signed_spans": len(sigs), "n_reads": len(reads),
            "n_spans_with_a_read": len(spans_seen), "n_compared": n_compared,
            "counts": counts}
    return hits, unlisted, counts, meta


def main():
    hits, unlisted, counts, meta = scan()
    if meta["n_compared"] == 0:
        print("NOTHING WAS COMPARED: a scan that tests nothing passes on nothing.")
        return 2

    def rows(rs):
        seen = {}
        for r in rs:
            seen.setdefault(r["span_id"], []).append(r)
        return seen

    out = {
        "kind": "signature_reversal_scan",
        "ruling": "A(2) 2026-10-25 -- flag signature_suspect: reversed over every signed span "
                  "(45 + 19).  Record only: this never edits a signature.",
        "page_convention": "all page numbers are FILE pages (printed = file - 88)",
        "basis": "Hebrew consonants only; nikud stripped; spaces, hyphens, bracket notation and "
                 "Latin dropped, because a reversal is a claim about glyph order",
        "rule": {
            "reversed_exact": "read == reverse(signature)",
            "reversed_one_swap": "one differing position from reverse(signature), and that pair is "
                                 "in confusable_vocab",
            "reversed_one_swap_unlisted": "NOT a ruling-A(2) hit: same shape, pair absent from the "
                                          "vocabulary.  Reported because the founding case was one.",
            "excluded:read_equals_signature": "a short string sits near its own reverse by "
                                              "construction; a correct read is not a suspect",
            "excluded:ambiguous_basis": "the reverse is not strictly the better explanation",
        },
        "meta": meta,
        "hits": hits,
        "unlisted_one_swap": unlisted,
        "hit_spans": sorted(rows(hits)),
        "unlisted_spans": sorted(rows(unlisted)),
    }
    name = "SIGNATURE_REVERSAL_20261025.json"
    p = os.path.join(DATA, name)
    with io.open(p, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True))
    print("signed spans scanned: %d  reads: %d  compared: %d"
          % (meta["n_signed_spans"], meta["n_reads"], meta["n_compared"]))
    for k in sorted(counts):
        print("  %-28s %d" % (k, counts[k]))
    print("\nHITS (ruling A(2) as written): %d reads over %d spans -> %s"
          % (len(hits), len(rows(hits)), sorted(rows(hits))))
    for r in hits:
        print(u"  %-10s pg%-4s %-26s %-10s sig=%s rev=%s read=%s swap=%s %s"
              % (r["span_id"], r["page_printed"], r["model"][:26], r["cell"],
                 r["signature_cons"], r["reverse_cons"], r["read_cons"],
                 (r["swap"] or {}).get("pair"), r["registers"]))
    print("\nUNLISTED one-swap (same shape, pair not in the vocabulary): %d reads over %d spans -> %s"
          % (len(unlisted), len(rows(unlisted)), sorted(rows(unlisted))))
    for r in unlisted:
        print(u"  %-10s pg%-4s %-26s %-10s sig=%s rev=%s read=%s swap=%s/%s"
              % (r["span_id"], r["page_printed"], r["model"][:26], r["cell"],
                 r["signature_cons"], r["reverse_cons"], r["read_cons"],
                 (r["swap"] or {}).get("reverse_has"), (r["swap"] or {}).get("read_has")))
    print("\nwrote %s" % p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
