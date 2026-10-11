# -*- coding: utf-8 -*-
"""Ingest signing pass 2 of the per-glyph console (26 spans), and classify every row by REASON (Lane B).

    python ingest_pass2.py <pass2_export.jsonl> <pass1_ingest.json>

ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).

THE RULE. A SIGNATURE MAY NOT CLAIM MORE THAN THE CROP SUPPORTS. The export's `full_span_pixel_signature`
is computed by the console as `!hasNotInCrop(s)`, i.e. from the TILE channel alone. It is True on 25 of 26
rows, including five whose PROSE says part of the span is not in the crop. This ingest never trusts that
boolean: it recomputes it from BOTH channels (tiles: any `not_in_crop`; prose: the validated regex below),
keeps the console's value under `full_span_pixel_signature_console`, and reports every disagreement.

WHAT THIS FILE DOES NOT DO. No network call, no model, no crop opened. It does not add a `sic` verdict path
(p594:n0 is the designated first instance, but it is also a contradicted row and goes to adjudication). It
does not edit the export. The prose regex is the one validated against this file and is NOT improved here.
A contradicted row (prose says unsignable, structure says nothing is unsignable) is WITHHELD from truth:
one channel is wrong and this file cannot say which.
"""
import hashlib
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hebrew_aperture_diag as HAD                                        # noqa: E402
from clean_run import git_state, provisional                              # noqa: E402
import apparatus_signature_rule as RULE                                   # noqa: E402  one source of the rule

SET, SET_N = "0401b636ffa7bf1a", 26
PRINTED_OFFSET = 88
REPOS = {"goatyard-laneB": "C:/Users/cnogr/git/goatyard-laneB",
         "dr-voluminous": "C:/Users/cnogr/git/dr-voluminous"}
EXPECTED_CHECKS = 2 * SET_N + 11          # 2 per row, plus ten file-level checks and the final count check

# order item 5: defect classes, derived from `note` text plus structure over THIS export only.
CENSUS_RX = (
    ("index shift", re.compile(r"index[- ]shift|note-index|offset by one|different footnote|adjacent note"
                               r"|from somewhere else", re.I)),
    ("mid-word box start", re.compile(r"starts? (partway|mid|in the middle)|begins after|partway through"
                                      r"|mid-word", re.I)),
    ("edge cut", re.compile(r"cuts? the|cut at the (right|left)|clipped|cut off at", re.I)),
    ("two-notes-one-region", re.compile(r"holds two notes|two notes", re.I)),
    ("plene insertion", re.compile(r"plene|full spelling|vowel letter", re.I)),
    ("synonym substitution", re.compile(r"substitution|synonym", re.I)),
    ("confusable cluster", re.compile(r"confusable|\u2194", re.I)),
)

_KNOWN = {"contradicted_prose_vs_structure", "box_fault_edge_cut", "signed_partial_in_crop",
          "signed_with_editorial_insertion", "signed", "abstain_reading_in_note", "incomplete_unstated"}
TRUTH_DISPOS = ("signed", "signed_with_editorial_insertion", "signed_partial_in_crop")
PASS1_TRUTH_DISPOS = ("signed", "signed_span_aperture_only")
EXPECT_CONTRADICTED = {"p493:n3", "p594:n0", "p803:n0"}
EXPECT_PARTIAL = {"p190:n0"}

CHECKS = 0


def check(cond, msg):
    global CHECKS
    assert cond, msg
    CHECKS += 1


def states():
    return {k: git_state(v) for k, v in REPOS.items()}


def prov(a, b):
    return any(provisional(a[k], b[k]) for k in REPOS)


GIT_START = states()

# ---------------------------------------------------------------- inputs, read-only

EXPORT_PATH, PASS1_PATH = sys.argv[1], sys.argv[2]
rows = [json.loads(l) for l in io.open(EXPORT_PATH, encoding="utf-8") if l.strip()]
pass1 = json.load(io.open(PASS1_PATH, encoding="utf-8"))
EXPORT_SHA = hashlib.sha256(io.open(EXPORT_PATH, "rb").read()).hexdigest()[:16]

check(len(rows) == SET_N, "the export has %d rows, not %d -- a narrowed record" % (len(rows), SET_N))
check(len(set(r["span_id"] for r in rows)) == SET_N, "duplicate span_id in the export")
check(all(r.get("set_sha16") == SET for r in rows), "a row carries a different set_sha16")
p1_rows = pass1["rows"]
check(len(p1_rows) > 0 and pass1.get("set_sha16") == SET, "pass 1 ingest is empty or from another set")


# ---------------------------------------------------------------- derivedFor, ported from glyph_signer.py 913-926

def tile_out(t):
    v, gap = t.get("verdict") or "", t["kind"] == "gap"
    if v == "deleted":
        return ""
    if v == "not_in_crop":
        return "[ ]" if gap else "[" + t["shown"] + "]"
    if v == "confirmed":
        return " " if gap else t["shown"]
    if v == "corrected":
        if gap:
            return " " if t.get("chose") == "space" else ""
        return t.get("chose") or "?"
    return "?"


def ins_out(it):
    if not it.get("chose"):
        return "?"
    return " " if it["kind"] == "gap" else it["chose"]


def derive(r):
    out = [ins_out(x) for x in sorted((x for x in r["insertions"] if x["after_i"] is None),
                                      key=lambda x: x["seq"])]
    for t in r["tiles"]:
        out.append(tile_out(t))
        out.extend(ins_out(x) for x in sorted((x for x in r["insertions"] if x["after_i"] == t["i"]),
                                              key=lambda x: x["seq"]))
    return "".join(out)


def sha16(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- facts per row

def facts_for(r):
    tiles = r["tiles"]
    f = {"span_id": r["span_id"], "complete": bool(r.get("complete")), "fault": r.get("fault") or "",
         "note": (r.get("note") or "").strip()}
    for kind in ("consonant", "gap"):
        tk = [t for t in tiles if t["kind"] == kind]
        f["n_nic_" + kind] = sum(1 for t in tk if t.get("verdict") == "not_in_crop")
    f["n_nic"] = sum(1 for t in tiles if t.get("verdict") == "not_in_crop")
    f["n_deleted"] = sum(1 for t in tiles if t.get("verdict") == "deleted")
    f["n_corrected"] = sum(1 for t in tiles if t.get("verdict") == "corrected")
    f["n_confirmed"] = sum(1 for t in tiles if t.get("verdict") == "confirmed")
    f["n_empty"] = sum(1 for t in tiles if not t.get("verdict"))
    f["prose_says_unsignable"] = RULE.prose_says_unsignable(f["note"])
    f["signature_recomputed"] = derive(r)
    f["signature_in_crop"] = re.sub(r"\[[^\]]*\]", "", f["signature_recomputed"])
    f["n_insertions"] = len(r["insertions"])
    f["insertions_called_unsignable"] = f["n_insertions"] > 0 and f["prose_says_unsignable"]
    f["full_span_pixel_signature_console"] = bool(r.get("full_span_pixel_signature"))
    # historical value of THIS ingest: structure (RULE) AND NOT prose; kept so its numbers do not move.
    f["full_span_pixel_signature"] = (RULE.full_span_pixel_signature(tiles, r["insertions"])
                                      and not f["prose_says_unsignable"])
    f["fsps_console_disagrees"] = f["full_span_pixel_signature"] != f["full_span_pixel_signature_console"]
    return f


def disposition_pass2(r, f):
    if f["prose_says_unsignable"] and f["n_nic"] == 0 and f["n_empty"] == 0:
        return "contradicted_prose_vs_structure"
    if f["fault"] == "box-edge-cut":
        return "box_fault_edge_cut"
    if f["complete"] and f["n_nic"] > 0:
        return "signed_partial_in_crop"
    if f["complete"] and f["n_insertions"] > 0 and not f["insertions_called_unsignable"]:
        return "signed_with_editorial_insertion"
    if f["complete"]:
        return "signed"
    if f["n_empty"] > 0 and f["note"]:
        return "abstain_reading_in_note"
    return "incomplete_unstated"


F, DISPO = {}, {}
n_match = 0
for r in rows:
    f = facts_for(r)
    check(f["signature_recomputed"] == r["derived_consonants"],
          "%s: port of derivedFor gives %r, console said %r" % (r["span_id"], f["signature_recomputed"],
                                                                r["derived_consonants"]))
    n_match += 1
    check(not (f["complete"] and f["n_empty"] > 0),
          "%s: complete with %d empty tile(s) -- a disposition this file has not named" % (r["span_id"], f["n_empty"]))
    F[r["span_id"]] = f
    DISPO[r["span_id"]] = disposition_pass2(r, f)

by_dis = {}
for s, d in DISPO.items():
    by_dis.setdefault(d, []).append(s)
got_contra = set(by_dis.get("contradicted_prose_vs_structure", []))
got_part = set(by_dis.get("signed_partial_in_crop", []))
check(got_contra == EXPECT_CONTRADICTED, "contradicted set differs: only-computed %s, only-expected %s"
      % (sorted(got_contra - EXPECT_CONTRADICTED), sorted(EXPECT_CONTRADICTED - got_contra)))
check(got_part == EXPECT_PARTIAL, "partial set differs: only-computed %s, only-expected %s"
      % (sorted(got_part - EXPECT_PARTIAL), sorted(EXPECT_PARTIAL - got_part)))
_unk = sorted(set(DISPO.values()) - _KNOWN)
check(not _unk, "unnamed disposition(s): %s" % _unk)
check(sum(len(v) for v in by_dis.values()) == SET_N, "the tally does not sum to %d" % SET_N)

# ---------------------------------------------------------------- truth and held

WHY = {
    "contradicted_prose_vs_structure":
        "the signer's PROSE says part of the span is not in the crop, but every tile is confirmed/corrected/"
        "deleted and none is marked not-in-crop; the two channels disagree and this file cannot say which is right",
    "box_fault_edge_cut":
        "the typed fault says the BOX cut a glyph off; a signature over a cut crop is not a signature of the span",
    "abstain_reading_in_note":
        "the signer left tiles empty on purpose and put the reading in the note; no per-tile verdict backs it",
    "incomplete_unstated": "incomplete with no note saying why",
}

truth_rows, held_rows = [], []
for r in rows:
    s, f, d = r["span_id"], F[r["span_id"]], DISPO[r["span_id"]]
    if d in TRUTH_DISPOS:
        sf = r.get("signed_from")
        if d == "signed_with_editorial_insertion":
            sf = "pixels, plus %d signer insertion(s) not present as tiles" % f["n_insertions"]
        pts = r.get("points_shown_not_adjudicated") or {}
        truth_rows.append({
            "span_id": s, "disposition": d,
            "signature": f["signature_in_crop"] if d == "signed_partial_in_crop" else f["signature_recomputed"],
            "signature_full": f["signature_recomputed"],
            "full_span_pixel_signature": f["full_span_pixel_signature"],
            "full_span_pixel_signature_console": f["full_span_pixel_signature_console"],
            "fsps_console_disagrees": f["fsps_console_disagrees"],
            "signed_from": sf, "crop_sha16": r.get("crop_sha16"), "candidate_sha16": r.get("candidate_sha16"),
            "n_points": pts.get("n_points"), "nikud_flag": pts.get("nikud_flag"), "pass": 2})
    else:
        held_rows.append({"span_id": s, "disposition": d, "note": f["note"], "why_held": WHY[d]})

# ---------------------------------------------------------------- combined truth count, derived

p1_truth = [x["span_id"] for x in p1_rows if x["disposition"] in PASS1_TRUTH_DISPOS]
check(len(set(p1_truth) & set(t["span_id"] for t in truth_rows)) == 0, "a span is in truth in both passes")
TRUTH_TOTAL = len(p1_truth) + len(truth_rows)
TRUTH_LINE = "TRUTH TOTAL: %d (pass 1 %d + pass 2 %d)" % (TRUTH_TOTAL, len(p1_truth), len(truth_rows))

# ---------------------------------------------------------------- census (this export only)

census = {}
for name, rx in CENSUS_RX:
    ids = sorted(s for s, f in F.items() if rx.search(f["note"]))
    if name == "edge cut":
        ids = sorted(set(ids) | set(s for s, f in F.items() if f["fault"] == "box-edge-cut"))
    census[name] = ids
census_hit = set(x for v in census.values() for x in v)
# structural-only signals with no reliable textual rule: listed for an eye, never counted as a class.
needs_eye = sorted(
    [s for s, f in F.items() if (f["n_insertions"] or f["n_deleted"] or f["n_corrected"]) and s not in census_hit])
check(all(s in F for s in needs_eye), "needs-an-eye list names an unknown span")

GIT_END = states()
PROV = prov(GIT_START, GIT_END)

# ---------------------------------------------------------------- output

check(CHECKS + 1 == EXPECTED_CHECKS, "ran %d checks before the final count, expected %d" % (CHECKS + 1, EXPECTED_CHECKS))


def jl(path, recs):
    io.open(str(path), "w", encoding="utf-8", newline="\n").write(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in recs))


TRUTH_OUT, HELD_OUT = HAD.DATA / "truth_pass2.jsonl", HAD.DATA / "held_pass2.jsonl"
REPORT = HAD.DATA / ("INGEST_pass2_%s.md" % SET)
jl(TRUTH_OUT, truth_rows)
jl(HELD_OUT, held_rows)

dis_ct = {k: len(v) for k, v in sorted(by_dis.items())}
dis_rows = [s for s in sorted(F) if F[s]["fsps_console_disagrees"]]
L = []
L.append("# Ingest of signing pass 2 (%d spans)%s" % (SET_N, "  -- PROVISIONAL" if PROV else ""))
L.append("")
L.append("ALL PAGE NUMBERS ARE FILE PAGES (printed = file - %d)." % PRINTED_OFFSET)
L.append("")
L.append("- export: `%s` (sha16 %s)" % (os.path.basename(EXPORT_PATH), EXPORT_SHA))
L.append("- pass 1 ingest used: `%s`" % PASS1_PATH)
L.append("- run: %s" % ("PROVISIONAL (not citable)" if PROV else "clean"))
for k in REPOS:
    L.append("- git %s: start %s %s -> end %s %s" % (
        k, GIT_START[k]["git_head"][:7], GIT_START[k]["git_dirty"].get("state"),
        GIT_END[k]["git_head"][:7], GIT_END[k]["git_dirty"].get("state")))
L.append("- checks run: %d (expected %d)" % (CHECKS, EXPECTED_CHECKS))
L.append("- prose regex (RULE.UNSIGNABLE_PATTERN, unchanged): `%s`" % RULE.UNSIGNABLE_PATTERN)
L.append("")
L.append("## %s" % TRUTH_LINE)
L.append("")
L.append("Derived from pass 1's `%s` rows with disposition in %s, plus pass 2's truth rows. Not a literal."
         % (os.path.basename(PASS1_PATH), list(PASS1_TRUTH_DISPOS)))
L.append("")
L.append("## signature_recomputed == derived_consonants: %d of %d" % (n_match, SET_N))
L.append("")
L.append("## Dispositions")
L.append("")
for k in sorted(by_dis, key=lambda k: (-len(by_dis[k]), k)):
    L.append("- `%s` %d: %s" % (k, len(by_dis[k]), " ".join(sorted(by_dis[k]))))
L.append("")
L.append("## Console `full_span_pixel_signature` disagrees with the recomputed value: %d" % len(dis_rows))
L.append("")
for s in dis_rows:
    L.append("- %s (%s): console %s, recomputed %s, n_nic %d, prose_unsignable %s"
             % (s, DISPO[s], F[s]["full_span_pixel_signature_console"], F[s]["full_span_pixel_signature"],
                F[s]["n_nic"], F[s]["prose_says_unsignable"]))
L.append("")
L.append("## Truth rows entering (%d), held (%d)" % (len(truth_rows), len(held_rows)))
L.append("")
for t in truth_rows:
    L.append("- %s `%s` signature len %d, from: %s" % (t["span_id"], t["disposition"], len(t["signature"]),
                                                      t["signed_from"]))
L.append("")
for h in held_rows:
    L.append("- HELD %s `%s`: %s" % (h["span_id"], h["disposition"], h["why_held"]))
L.append("")
L.append("## Defect-class census (this export only, %d rows; not cumulative)" % SET_N)
L.append("")
for name, ids in census.items():
    L.append("- %s: %d  %s" % (name, len(ids), " ".join(ids)))
L.append("- unclassified-by-rule (a structural edit, no class matched; needs an eye): %d  %s"
         % (len(needs_eye), " ".join(needs_eye)))
L.append("")
L.append("## Per-row facts")
L.append("")
L.append("| span | disposition | nic | del | corr | conf | empty | ins | prose_unsig | fsps console/recomputed |")
L.append("|---|---|---|---|---|---|---|---|---|---|")
for s in sorted(F):
    f = F[s]
    L.append("| %s | %s | %d | %d | %d | %d | %d | %d | %s | %s/%s |" % (
        s, DISPO[s], f["n_nic"], f["n_deleted"], f["n_corrected"], f["n_confirmed"], f["n_empty"],
        f["n_insertions"], f["prose_says_unsignable"], f["full_span_pixel_signature_console"],
        f["full_span_pixel_signature"]))
L.append("")
L.append("## What this does NOT solve")
L.append("")
L.append("- Recomputed `full_span_pixel_signature` is tiles + prose-regex only; incomplete rows with empty tiles "
         "are not counted as not-full by it (they are held by disposition instead).")
L.append("- A contradicted row is withheld, not adjudicated; which channel is right is a human reading.")
L.append("- Insertions carry no verdict and cannot be marked not-in-crop; `signed_with_editorial_insertion` is a "
         "signed reading, not a pure pixel signature.")
L.append("- Census classes come from note text plus structure; rows with a structural edit and no textual signal "
         "are listed, not guessed.")
io.open(str(REPORT), "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")

print("ingest of %s  (%d rows)  pass1 file: %s" % (os.path.basename(EXPORT_PATH), len(rows), PASS1_PATH))
print("  signature_recomputed == derived_consonants: %d of %d" % (n_match, SET_N))
print("  dispositions:")
for k in sorted(by_dis, key=lambda k: (-len(by_dis[k]), k)):
    print("    %-34s %3d   %s" % (k, len(by_dis[k]), " ".join(sorted(by_dis[k]))[:120]))
print("  tally sums to %d" % sum(dis_ct.values()))
print("  fsps console disagrees: %d  %s" % (len(dis_rows), " ".join(dis_rows)))
print("  census (this export): " + "; ".join("%s %d" % (k, len(v)) for k, v in census.items())
      + "; unclassified-by-rule %d" % len(needs_eye))
print("  " + TRUTH_LINE)
print("  checks run %d, expected %d" % (CHECKS, EXPECTED_CHECKS))
print("  git: %s" % ("PROVISIONAL" if PROV else "clean run"))
print("  wrote %s, %s, %s" % (TRUTH_OUT.name, HELD_OUT.name, REPORT.name))
