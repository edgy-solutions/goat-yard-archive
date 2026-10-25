# -*- coding: utf-8 -*-
u"""Chris's audit of CLASSIFY45_SHEET_501ab577a18a6785.html, as a STANDOFF overlay.

Ruling A(1) 2026-10-25 orders a reclassification: *"Reclassify both assignments as `signature`."*
This is how that is done here, and why it is not done by editing the record:

**The editor's marks are a standoff record, never edits.**  `CLASSIFY45_501ab577a18a6785.json` is
what the run measured and `CANONICAL45_reader_e63ecc2eab1aa479.json` is content-addressed by its own
digest and has been verified byte-identical across regenerations.  Rewriting a class inside either
one would destroy the thing a later reader needs most -- the ability to see that the run said
`substitution` and a human said `signature`, and to see which of the two is grounded in what.  So
the adjudication lives beside the measurement, carrying its own basis, and a consumer joins them.

PROVENANCE, AND WHY IT IS THE WEAK POINT.  Every verdict below is TRANSCRIBED by me from Chris's
audit message of 2026-10-25.  It is not a measurement and it is not my judgment; it is a
transcription, and a transcription can be wrong in ways neither a test nor a hash can see.  Each row
therefore carries `basis` in Chris's own terms, so the verdict can be checked against what he said
rather than against what I concluded.  Rows he did not reach carry `not_adjudicated` -- never an
inference, because a class I guessed and a class he ruled would then be indistinguishable.

HASH RULE (ruling 5): the digest is sha256 over the UTF-8 bytes of the record serialised with
`ensure_ascii=False, sort_keys=True, indent=1`, with the `self_sha16` field absent.

All page numbers are FILE pages (printed = file - 88).
"""
import hashlib
import io
import json
import os
import sys

import hebrew_aperture_diag as diag

DATA = str(diag.DATA)
CANONICAL = "CANONICAL45_reader_e63ecc2eab1aa479.json"
SHEET = "CLASSIFY45_SHEET_501ab577a18a6785.html"

#: Verdict vocabulary.  `signature` and `crop_edge_cut` MOVE the fault off the reader; `agreed`
#: leaves the run's class standing; `signature_suspect_unsettled` is a refusal to decide, which is a
#: verdict in its own right and must not collapse into either of the others.
VERDICTS = ("signature", "crop_edge_cut", "agreed", "signature_suspect_unsettled",
            "not_adjudicated")

#: (span_id, arm) -> verdict.  `basis` is Chris's stated ground, trimmed but not reworded.
#: `model_was_right` is his call, not mine, and is None where he did not make one.
AUDIT = [
    # ----- ruling A(1): the one adjudicated reversal.  Both arms, both models right.
    {"span_id": "p442:n0", "arm": "opus", "run_class": "substitution", "verdict": "signature",
     "model_was_right": True, "reversed": True,
     "basis": u"signed רבך; pixels and both bare reads דבר. Glyphs "
              u"signed in visual left-to-right order, dalet taken as final kaf."},
    {"span_id": "p442:n0", "arm": "qwen", "run_class": "substitution", "verdict": "signature",
     "model_was_right": True, "reversed": True,
     "basis": u"same span, same cause; ruling A(1) names both arms."},

    # ----- signature errors where the model read the pixels correctly
    {"span_id": "p254:n1", "arm": "opus", "run_class": None, "verdict": "signature",
     "model_was_right": True, "reversed": False,
     "basis": u"pixels read נזם; opus exact. Stray ink along the bottom crop edge "
              u"with box_fault False."},
    {"span_id": "p254:n1", "arm": "qwen", "run_class": "substitution", "verdict": "signature",
     "model_was_right": None, "reversed": False,
     "basis": u"signature wrong on the same span; qwen's own read not separately ruled."},
    {"span_id": "p798:n0", "arm": "opus", "run_class": "confusable", "verdict": "signature",
     "model_was_right": True, "reversed": False,
     "basis": u"position 4 is tav, not he. Opus exact."},
    {"span_id": "p831:n2", "arm": "opus", "run_class": "confusable", "verdict": "signature",
     "model_was_right": True, "reversed": False,
     "basis": u"position 2 is dalet. Opus exact."},

    # ----- crop/edge-cut: the fault is the rect, not the reader.  Every one of these carries
    # box_fault False AND partial_in_crop False, which is the guard failing to see its own fault.
    {"span_id": "p326:n11", "arm": "opus", "run_class": "confusable", "verdict": "crop_edge_cut",
     "model_was_right": None, "reversed": False,
     "basis": u"first letter clipped at the RIGHT crop edge; the truncated vav reads as yod."},
    {"span_id": "p326:n11", "arm": "qwen", "run_class": "short", "verdict": "crop_edge_cut",
     "model_was_right": None, "reversed": False,
     "basis": u"same clip; the stub was dropped rather than read."},
    {"span_id": "p428:n0", "arm": "opus", "run_class": "confusable", "verdict": "crop_edge_cut",
     "model_was_right": None, "reversed": False,
     "basis": u"final he clipped at the LEFT crop edge; the residue reads as vav."},
    {"span_id": "p428:n0", "arm": "qwen", "run_class": "confusable", "verdict": "crop_edge_cut",
     "model_was_right": None, "reversed": False,
     "basis": u"same clip; the residue reads as final nun."},
    {"span_id": "p622:n0", "arm": "opus", "run_class": "confusable", "verdict": "crop_edge_cut",
     "model_was_right": None, "reversed": False,
     "basis": u"final tav clipped at the LEFT crop edge; the surviving right stroke reads as vav. "
              u"Corrects Lane B's rejection, which said opus read the tav: opus read a vav."},
    {"span_id": "p622:n0", "arm": "qwen", "run_class": "short", "verdict": "crop_edge_cut",
     "model_was_right": None, "reversed": False,
     "basis": u"same clip; the stub was dropped."},
    {"span_id": "p831:n2", "arm": "qwen", "run_class": "substitution", "verdict": "crop_edge_cut",
     "model_was_right": None, "reversed": False,
     "basis": u"clipped at the TOP edge, letter heads cut, 2 bands; the two substituted letters are "
              u"the ones whose heads are cut."},

    # ----- the run's class stands
    {"span_id": "p558:n3", "arm": "qwen", "run_class": "plene", "verdict": "agreed",
     "model_was_right": None, "reversed": False,
     "basis": u"agree reader/plene. Note the crop is 2 bands with a Latin line above, yet box_fault "
              u"is False."},
    {"span_id": "p594:n0", "arm": "opus", "run_class": "substitution", "verdict": "agreed",
     "model_was_right": None, "reversed": False,
     "basis": u"agree reader/substitution; the sic is confirmed on the glyph (open top-left "
              u"corner). The crop carries Latin “in” at the left edge; box_fault is "
              u"ratified, so this span is refused at send time."},
    {"span_id": "p798:n0", "arm": "qwen", "run_class": "confusable", "verdict": "agreed",
     "model_was_right": None, "reversed": False,
     "basis": u"agree reader/confusable (het for tav), against the corrected signature."},

    # ----- refusals to decide.  These are verdicts, and each carries what would settle it.
    {"span_id": "p233:n4", "arm": "opus", "run_class": "confusable",
     "verdict": "signature_suspect_unsettled", "model_was_right": None, "reversed": False,
     "basis": u"position 2 differs from an in-word vav at the head; no zayin exemplar on the card, "
              u"so it cannot be settled. Context favours zayin, so the signature is not likely "
              u"because the signed string is not a word.",
     "needs": u"zayin exemplars from this fount"},
    {"span_id": "p628:n2", "arm": "qwen", "run_class": "confusable",
     "verdict": "signature_suspect_unsettled", "model_was_right": None, "reversed": False,
     "basis": u"position 2 final nun (signed) vs vav (read); the crop is tight and the descender "
              u"cannot be judged.",
     "needs": u"a strip with the baseline visible, final-nun and vav exemplars from this fount, and "
              u"the Latin gloss as the expected tile"},

    # ----- reached by the sheet, not reached by the audit.  Recorded as absent, never inferred.
    {"span_id": "p735:n0", "arm": "qwen", "run_class": "substitution", "verdict": "not_adjudicated",
     "model_was_right": None, "reversed": False,
     "basis": u"not in the audit's per-row list."},
    {"span_id": "p910:n3", "arm": "qwen", "run_class": "substitution", "verdict": "not_adjudicated",
     "model_was_right": None, "reversed": False,
     "basis": u"not in the audit's per-row list. Lane B's reversal scan reports it as a one-swap "
              u"from reverse(signature) with lamed/final-kaf, a pair in no register -- a candidate, "
              u"not a verdict."},
]


def digest(obj):
    s = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def build():
    rows = []
    for a in AUDIT:
        pf = int(a["span_id"].split(":")[0][1:])
        r = dict(a)
        r["page_file"] = pf
        r["page_printed"] = pf - 88
        rows.append(r)

    sheet = os.path.join(DATA, SHEET)
    if not os.path.exists(sheet):
        raise IOError("the audited sheet is not on disk, so this record cannot name the bytes "
                      "Chris read: %s" % sheet)
    with open(sheet, "rb") as fh:
        sheet_sha = hashlib.sha256(fh.read()).hexdigest()[:16]

    rec = {
        "kind": "adjudication_overlay",
        "of": SHEET,
        # approval-records-are-content-addressed: the filename carries the RUN hash, not the
        # sheet's own bytes.  The sheet is self-contained (80 embedded crops, no file:// refs), so
        # this digest covers the pixels Chris actually read.  A regenerated sheet with a different
        # digest is a different document and these verdicts would not be about it.
        "of_sha256_16": sheet_sha,
        "ruling": "A(1)-A(4) 2026-10-25, Chris's audit of the classify45 sheet",
        "standoff": "This record does NOT edit CLASSIFY45_501ab577a18a6785.json or "
                    "CANONICAL45_reader_e63ecc2eab1aa479.json. The run's class and the human's "
                    "verdict are both kept, each with its own grounding, and a consumer joins "
                    "them on (span_id, arm).",
        "provenance": "TRANSCRIBED by Lane B from Chris's audit message of 2026-10-25. Not a "
                      "measurement and not Lane B's judgment. `basis` carries Chris's stated "
                      "ground so each verdict can be checked against what he said.",
        "page_convention": "all page numbers are FILE pages (printed = file - 88)",
        "verdict_vocabulary": {
            "signature": "the signed string is wrong; the fault is the signer's",
            "crop_edge_cut": "the crop cuts a glyph; the fault is the rect's, not the reader's",
            "agreed": "the run's class stands",
            "signature_suspect_unsettled": "a refusal to decide, with what would settle it in "
                                           "`needs`. Not a weaker `signature`.",
            "not_adjudicated": "the audit did not reach this row. Never an inference.",
        },
        "hash_rule": "sha256 over the UTF-8 bytes of this record serialised with "
                     "ensure_ascii=False, sort_keys=True, indent=1, with self_sha16 absent",
        "rows": rows,
        "tallies": dict((v, len([r for r in rows if r["verdict"] == v])) for v in VERDICTS),
    }
    rec["self_sha16"] = digest(rec)
    return rec


# ------------------------------------------------------------------------------- assertions, inline
def check(rec):
    n, fail = [0], []

    def ck(cond, msg):
        n[0] += 1
        if not cond:
            fail.append(msg)

    rows = rec["rows"]
    ck(all(r["verdict"] in VERDICTS for r in rows), "every verdict is in the vocabulary")
    ck(len(set((r["span_id"], r["arm"]) for r in rows)) == len(rows),
       "one verdict per (span, arm): a duplicate would let two verdicts about the same row both "
       "stand")
    ck(all(r["page_printed"] == r["page_file"] - 88 for r in rows),
       "the printed page is derived, never typed")
    ck(all(r.get("needs") for r in rows if r["verdict"] == "signature_suspect_unsettled"),
       "every refusal to decide says what would settle it, or it is just a shrug")
    ck(all(r["basis"] for r in rows), "every row carries a basis")
    ck(all(r["model_was_right"] is None for r in rows if r["verdict"] == "not_adjudicated"),
       "an unadjudicated row claims nothing about the model")
    p442 = [r for r in rows if r["span_id"] == "p442:n0"]
    ck(len(p442) == 2 and all(r["verdict"] == "signature" and r["reversed"] and r["model_was_right"]
                              for r in p442),
       "ruling A(1) is carried out: BOTH p442:n0 assignments are `signature`, flagged reversed, "
       "with the model right")
    ck(rec["self_sha16"] == digest(dict((k, v) for k, v in rec.items() if k != "self_sha16")),
       "the digest is over the record without its own digest field")
    # the overlay must join onto the canonical record, or it describes nothing
    ck(len(rec["of_sha256_16"]) == 16,
       "the record names the BYTES of the sheet that was audited, not just its filename")
    p = os.path.join(DATA, CANONICAL)
    ck(os.path.exists(p), "the canonical reader record is present to join against: %s" % p)
    if os.path.exists(p):
        can = json.load(io.open(p, encoding="utf-8"))["rows"]
        keys = set((r["span_id"], r["arm"]) for r in can)
        mine = set((r["span_id"], r["arm"]) for r in rows)
        orphan = sorted(k for k in mine if k not in keys)
        ck(orphan == [("p254:n1", "opus"), ("p254:n1", "qwen")],
           "every overlay row joins onto a canonical reader row, except p254:n1 which was withheld "
           "from the 18 and is adjudicated here for the first time: orphans %s" % (orphan,))
        uncovered = sorted(k for k in keys if k not in mine)
        ck(uncovered == [],
           "every one of the 18 canonical reader rows has a verdict or an explicit "
           "`not_adjudicated`: uncovered %s" % (uncovered,))
    EXPECTED = 12
    print("audit_overlay: %d checks, %d failed" % (n[0], len(fail)))
    for m in fail:
        print("  FAIL  %s" % m)
    if n[0] != EXPECTED:
        print("SUITE DID NOT RUN TO COMPLETION: %d checks, expected %d." % (n[0], EXPECTED))
        return 2
    return 1 if fail else 0


def main():
    rec = build()
    rc = check(rec)
    if rc:
        return rc
    name = "ADJUDICATION_classify45_20261025_%s.json" % rec["self_sha16"]
    p = os.path.join(DATA, name)
    with io.open(p, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True, indent=1))
    print("")
    for v in VERDICTS:
        print("  %-30s %d" % (v, rec["tallies"][v]))
    print("")
    print("wrote %s" % p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
