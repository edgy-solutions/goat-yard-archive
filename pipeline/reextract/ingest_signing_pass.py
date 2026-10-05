# -*- coding: utf-8 -*-
"""Ingest signing pass 1 of the per-glyph console, and classify every row by REASON (Lane B, 2026-10-04).

    python ingest_signing_pass.py

ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).

WHY THIS EXISTS. `glyph_signer.py` produced a page whose per-row flags do not, on their own, say what
happened. Seven rows came back `complete: true` AND `abstain: true`, which is not a contradiction -- it is
the signer routing around a control the console does not have (there is no way to say "a glyph is MISSING
from the candidate", so every tile present was confirmed and the row was then refused). Any consumer that
reads `complete` as "signed" would ship those. So the disposition is computed here, under Chris's stated
rule: AN ABSTAIN FLAG, OR A NOTE SAYING MISSING OR CLIPPED, OVERRIDES TILE COMPLETENESS.

WHAT THE NOTES ARE. 34 of 74 rows carry free text, because the three things the signer most needed to say
had no channel: a letter is absent from the candidate, a glyph is not visible in this crop, and the crop is
at fault while the Hebrew is right. Those are classified here by explicit regex over the note, MULTI-LABEL
(one note routinely says two of them), and every note must match at least one class -- a note that matches
nothing is a finding about this classifier and is printed, never swallowed.

WHAT A FAULT MEANS NOW, AND WHY NONE OF THEM IS A READING FAULT. The console's only fault button says
`not-hebrew-or-blank`, and 14 rows used it; 13 carry no note. Chris's trace settles what they are: the
candidate Hebrew does not come from the crop at all -- it comes from the whole-note v2 read -- and the
localizer then drew a box where it believed that Hebrew sat. So the text on screen can be real while the
box is on the wrong LINE of the same note (`p92:n1`: "the crop is 3 lines up from the hebrew"). These are
therefore localizer faults in the same family as the boxes that landed on the printed rule and on roman
type, and they are classed `fault_unconfirmed` here, NOT `box_wrong_line`: this file has no evidence about
where the Hebrew sits. Promoting them needs the overlay check, which is a separate run.

WHAT THIS FILE DOES NOT DO. It does not open a crop, score a box, or decide whether a fault is a wrong
line. It reads a signed record and a frozen truth set and classifies. The preliminary extraction score in
section 4 is over the SIGNED rows only, with n stated, and it measures one thing: how often the whole-note
read's Hebrew consonants were already exactly right.
"""
import hashlib
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hebrew_aperture_diag as HAD                                        # noqa: E402
from clean_run import git_state, provisional, banner                      # noqa: E402

SET, SET_N = "0401b636ffa7bf1a", 74
PASS_NAME = "glyphsign_signed_%s_20261004_pass1.jsonl" % SET
PASS_PATH = HAD.DATA / PASS_NAME
TRUTH_PATH = HAD.DATA / ("truth_set%d_%s.json" % (SET_N, SET))
CUT_PATH = HAD.DATA / ("truthset%d_cut_%s.json" % (SET_N, SET))
PRINTED_OFFSET = 88

GIT_START = git_state()


def sha16(b):
    if not isinstance(b, bytes):
        b = b.encode("utf-8")
    return hashlib.sha256(b).hexdigest()[:16]


# ---------------------------------------------------------------- inputs, all read-only

rows = [json.loads(l) for l in io.open(str(PASS_PATH), encoding="utf-8") if l.strip()]
truth = json.load(io.open(str(TRUTH_PATH), encoding="utf-8"))
cut = json.load(io.open(str(CUT_PATH), encoding="utf-8"))

assert truth.get("provisional") is False, "the truth set is provisional"
assert truth["set_sha16"] == SET and truth["n"] == SET_N
assert cut.get("provisional") is False, "the cut is provisional"
TRUTH_ROWS = {r["span_id"]: r for r in truth["rows"]}
CUT_ROWS = {r["span_id"]: r for r in cut["rows"] if r.get("crop")}

assert len(rows) == SET_N, "the pass has %d rows, not %d -- a narrowed record" % (len(rows), SET_N)
assert len(set(r["span_id"] for r in rows)) == SET_N, "duplicate span_id in the pass"
_sealed = sorted(set(HAD.SEALED_TRUTH) & set(r["span_id"] for r in rows))
assert not _sealed, "sealed span(s) %s in the pass -- sealed pages are SPENT" % _sealed

# A signature has to say what it was shown, and this is where that claim gets checked rather than trusted.
# Both halves: the CANDIDATE it adjudicated and the PIXELS it was shown beside it.
_cand_bad, _crop_bad = [], []
for r in rows:
    t = TRUTH_ROWS[r["span_id"]]
    if r.get("candidate_sha16") != sha16(t["hebrew"]):
        _cand_bad.append(r["span_id"])
    c = CUT_ROWS.get(r["span_id"])
    if c and r.get("crop_sha16") != c["crop"].get("sha16"):
        _crop_bad.append(r["span_id"])
assert not _cand_bad, "%d row(s) were signed against a candidate that is not the frozen one: %s" \
    % (len(_cand_bad), _cand_bad[:6])
assert not _crop_bad, "%d row(s) carry a crop_sha16 the cut does not have: %s" % (len(_crop_bad), _crop_bad[:6])
_SF = "pixels, candidate shown as consonant tiles, per-tile verdicts"
_sf_bad = [r["span_id"] for r in rows if r.get("signed_from") != _SF]
assert not _sf_bad, "%d row(s) carry a different signed_from: %s" % (len(_sf_bad), _sf_bad[:6])


# ---------------------------------------------------------------- the note taxonomy

# Multi-label. Each class is the thing the signer had no control for, named as what it says about the
# ARTIFACT, not about the signer. `candidate_short` and `edge_cut` are deliberately separate: one says the
# READ dropped a glyph, the other says the BOX cut one off, and they have different owners.
NOTE_CLASSES = (
    ("candidate_short",
     re.compile(r"miss?s?ing|mssing|only \d+ glyphs?|should be \d+ glyphs?|not \d+\b", re.I)),
    ("edge_cut",
     re.compile(r"clip|cropped out|crops? out|crop is clipp", re.I)),
    ("candidate_wrong",
     re.compile(r"\bwrong\b|\bincorrect\b|out of order", re.I)),
    ("pairing_misaligned",
     re.compile(r"crops? (are|is) (all )?wrong|crop showing different", re.I)),
    ("box_wrong_line",
     re.compile(r"lines? (up|down) from", re.I)),
    ("mixed_script_crop",
     re.compile(r"mixed .*english|english and hebrew", re.I)),
    ("hebrew_vouched",
     re.compile(r"hebrew is correct|hebrew correct|hebew correct|but hebrew", re.I)),
)

# `candidate_wrong` fires on the literal word "wrong", which also appears in every "crops are wrong" note.
# A note that faults the CROP and vouches for the text is not a note that faults the text, so the broad
# label is withdrawn where a narrower one that explains the same word is present.
WRONG_EXPLAINED_BY = ("pairing_misaligned", "box_wrong_line")


def classify_note(note):
    labs = [name for name, rx in NOTE_CLASSES if rx.search(note)]
    if "candidate_wrong" in labs and any(x in labs for x in WRONG_EXPLAINED_BY):
        labs = [l for l in labs if l != "candidate_wrong"]
    return labs


# ---------------------------------------------------------------- disposition, by Chris's rule

def disposition(r, labs):
    """One of: signed / signed_span_aperture_only / box_fault_edge_cut / abstain_* / fault_unconfirmed /
    fault_box_wrong_line / incomplete_unstated. An abstain flag or a missing/clipped note beats
    `complete`."""
    if r.get("fault"):
        return "fault_box_wrong_line" if "box_wrong_line" in labs else "fault_unconfirmed"
    if "edge_cut" in labs:
        # A glyph cut off by the box is a BOX fault, not a reading abstain -- the signer could read
        # everything the box showed. It is still not signable: a confirm for a glyph that is not in the
        # pixels is a verdict with nothing behind it, whatever the tile state says.
        return "box_fault_edge_cut"
    if "candidate_short" in labs:
        return "abstain_candidate_short"
    if "candidate_wrong" in labs:
        return "abstain_candidate_wrong"
    if "pairing_misaligned" in labs or "mixed_script_crop" in labs:
        # The signer vouched for the string off the whole-span view; only the per-letter pairing failed.
        # Signable, at the SPAN aperture, and the row says which rung lied.
        return "signed_span_aperture_only" if r.get("complete") else "abstain_pairing_misaligned"
    if r.get("abstain"):
        return "abstain_unstated"
    if r.get("complete"):
        return "signed"
    return "incomplete_unstated"


out = []
unmatched_notes = []
for r in rows:
    note = (r.get("note") or "").strip()
    labs = classify_note(note) if note else []
    if note and not labs:
        unmatched_notes.append((r["span_id"], note))
    tiles = r.get("tiles", [])
    vc = {}
    for t in tiles:
        vc[t.get("verdict") or ""] = vc.get(t.get("verdict") or "", 0) + 1
    corrections = [(t["i"], t.get("shown"), t.get("chose")) for t in tiles if t.get("verdict") == "corrected"]
    disputed = [t["i"] for t in tiles if t.get("verdict") == "disputed"]
    page = int(r["span_id"].split(":")[0][1:])
    out.append({
        "span_id": r["span_id"],
        "page": page,
        "printed": page - PRINTED_OFFSET,
        "paired_at": r.get("paired_at"),
        "complete": bool(r.get("complete")),
        "abstain": bool(r.get("abstain")),
        "fault": r.get("fault") or "",
        "note": note,
        "note_classes": labs,
        "tiles": len(tiles),
        "verdict_counts": vc,
        "corrections": corrections,
        "disputed": disputed,
        "disposition": disposition(r, labs),
        "candidate": TRUTH_ROWS[r["span_id"]]["hebrew"],
    })

assert len(out) == SET_N
# Every disposition must be one this file named. A new string appearing here is a silent class.
_KNOWN = {"signed", "signed_span_aperture_only", "box_fault_edge_cut", "abstain_candidate_short",
          "abstain_candidate_wrong", "abstain_pairing_misaligned", "abstain_unstated",
          "fault_unconfirmed", "fault_box_wrong_line", "incomplete_unstated"}
_unk = sorted(set(o["disposition"] for o in out) - _KNOWN)
assert not _unk, "unnamed disposition(s): %s" % _unk


# ---------------------------------------------------------------- the preliminary extraction score

# Over SIGNED rows only, with n stated. One question: how often was the whole-note read's Hebrew already
# exactly right at the consonant level? A corrected tile means it was not. This is NOT a score of the
# localizer, which is the weak link, and it is NOT a score of the 50 held rows.
SIGNED_DISPOS = ("signed", "signed_span_aperture_only")
signed = [o for o in out if o["disposition"] in SIGNED_DISPOS]
exact = [o for o in signed if not o["corrections"] and not o["disputed"]]
corrected = [o for o in signed if o["corrections"]]
with_disputed = [o for o in signed if o["disputed"]]
n_tiles_signed = sum(o["tiles"] for o in signed)
n_tiles_corrected = sum(len(o["corrections"]) for o in signed)


# ---------------------------------------------------------------- output

by_dis = {}
for o in out:
    by_dis.setdefault(o["disposition"], []).append(o["span_id"])
label_counts = {}
for o in out:
    for l in o["note_classes"]:
        label_counts[l] = label_counts.get(l, 0) + 1

GIT_END = git_state()
PROV = provisional(GIT_START, GIT_END)

doc = {
    "set_sha16": SET, "n": SET_N, "pass": PASS_NAME,
    "pass_sha16": sha16(io.open(str(PASS_PATH), "rb").read()),
    "printed_offset": PRINTED_OFFSET,
    "rule": "an abstain flag, or a note saying missing or clipped, overrides tile completeness",
    "dispositions": {k: sorted(v) for k, v in sorted(by_dis.items())},
    "disposition_counts": {k: len(v) for k, v in sorted(by_dis.items())},
    "note_label_counts": label_counts,
    "unmatched_notes": unmatched_notes,
    "preliminary_extraction_score": {
        "scope": "signed rows only; consonant level; the whole-note read's Hebrew, not the localizer's box",
        "n_rows": len(signed), "exact": len(exact), "rows_with_a_correction": len(corrected),
        "rows_with_a_disputed_tile": len(with_disputed),
        "tiles": n_tiles_signed, "tiles_corrected": n_tiles_corrected,
    },
    "rows": out,
    "git_start": GIT_START, "git_end": GIT_END, "provisional": PROV,
}
OUT = HAD.DATA / ("signing_pass1_ingest_%s.json" % SET)
io.open(str(OUT), "w", encoding="utf-8", newline="\n").write(
    json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=False))

print("ingest of %s  (%d rows)" % (PASS_NAME, len(out)))
print("  rule: %s" % doc["rule"])
print("  dispositions:")
for k in sorted(by_dis, key=lambda k: (-len(by_dis[k]), k)):
    print("    %-28s %3d   %s" % (k, len(by_dis[k]), " ".join(sorted(by_dis[k]))[:150]))
print("  note labels (multi-label over %d notes): %s"
      % (sum(1 for o in out if o["note"]),
         ", ".join("%s %d" % (k, v) for k, v in sorted(label_counts.items()))))
print("  notes matching no class: %d %s" % (len(unmatched_notes), unmatched_notes[:3]))
s = doc["preliminary_extraction_score"]
print("  preliminary extraction score (n=%d signed rows, %d tiles): exact %d, with a correction %d, "
      "with a disputed tile %d; tiles corrected %d of %d"
      % (s["n_rows"], s["tiles"], s["exact"], s["rows_with_a_correction"], s["rows_with_a_disputed_tile"],
         s["tiles_corrected"], s["tiles"]))
print("  every correction in the pass, signed or not:")
for o in out:
    for i, shown, chose in o["corrections"]:
        print("    %-10s %-26s tile %2d  %s -> %s" % (o["span_id"], o["disposition"], i, shown, chose))
print("  wrote %s" % OUT.name)
print(banner(GIT_START, GIT_END))
