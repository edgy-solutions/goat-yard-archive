r"""A TILES-ONLY comparison for the four spans whose only prior signature predates the insertion channel.

This is NOT a re-signing diff and must never be used as one.  `diff_resigned` refuses these four pairs
outright: the 2026-10-04 pass-1 export has no `insertions` channel at all, and an absent channel is
not an empty one -- reading it as empty would assert that signer made no insertions, which his file
does not say.  So one axis of the comparison does not exist, and a report that covered only the other
would be a partial comparison wearing a complete comparison's name.

What this file is instead: the tile axis alone, labelled as such, carrying no `diff_sha16` and no
`disagreements` key -- so `admit_resigned` cannot accept it (it refuses any object without those) and
no row can be ingested on the strength of it.  It exists so Chris can SEE what changed on the axis
that does exist, while the insertion axis stays openly unmeasured and sized: the count of insertions
in each current row is printed, because that is exactly the quantity nothing here compares.

The pixel precondition is still enforced: both hashes must be identical per span, or the comparison
is about two different crops and means nothing.
"""
import hashlib
import io
import json
import sys
import pathlib

from write_scope import assert_inside

A = pathlib.Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits")
CUR = A / "glyphsign_0401b636ffa7bf1a_resign_5span_signed_50d419a4.jsonl"
PRI = A / "glyphsign_signed_0401b636ffa7bf1a_20261004_pass1.jsonl"
SPANS = ("p254:n1", "p442:n0", "p628:n2", "p798:n0")   # p831:n2 is excluded: its LATEST prior is the
                                                       # pass-2 re-sign, and it has a real diff (B).
PRINTED_OFFSET = 88


def sha16f(p):
    return hashlib.sha256(io.open(p, "rb").read()).hexdigest()[:16]


def rows(p):
    return {r["span_id"]: r for r in
            (json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip())}


cur, pri = rows(CUR), rows(PRI)
out = []
for sid in SPANS:
    r, p = cur[sid], pri[sid]
    for k in ("crop_sha16", "candidate_sha16"):
        if not r.get(k) or r.get(k) != p.get(k):
            sys.exit("%s: %s differs (%r vs %r) -- not the same pixels, a comparison means nothing"
                     % (sid, k, r.get(k), p.get(k)))
    ct = dict((t["i"], t) for t in r["tiles"])
    pt = dict((t["i"], t) for t in p["tiles"])
    if set(ct) != set(pt) or len(ct) != len(r["tiles"]) or len(pt) != len(p["tiles"]):
        sys.exit("%s: the tile index sets differ over identical pixels" % sid)
    changes = []
    for i in sorted(ct):
        a, b = pt[i], ct[i]
        ka = (a.get("shown") or "", a.get("verdict") or "", a.get("chose") or "")
        kb = (b.get("shown") or "", b.get("verdict") or "", b.get("chose") or "")
        if ka != kb:
            changes.append({"i": i, "kind": b.get("kind"),
                            "prior": {"shown": ka[0], "verdict": ka[1], "chose": ka[2]},
                            "current": {"shown": kb[0], "verdict": kb[1], "chose": kb[2]},
                            "reversal_corrected_to_confirmed": ka[1] == "corrected" and kb[1] == "confirmed"})
    out.append({"span_id": sid,
                "file_page": int(sid.split(":")[0][1:]),
                "printed_page": int(sid.split(":")[0][1:]) - PRINTED_OFFSET,
                "pixels": [r["crop_sha16"], r["candidate_sha16"]],
                "tiles_compared": len(ct),
                "tile_changes": changes,
                "current_derived_consonants": r.get("derived_consonants"),
                "current_note": r.get("note") or "",
                "insertions_in_current_row_NOT_COMPARED": len(r.get("insertions") or []),
                "insertion_axis": "ABSENT from the prior export; nothing here measures it"})

doc = {
    "kind": "tiles_only_diagnostic",
    "NOT_A_RESIGN_DIFF": True,
    "why": "diff_resigned REFUSES these four pairs: the prior export has no 'insertions' channel at "
           "all, and an absent channel is not an empty one. One axis of the comparison does not "
           "exist, so this file compares the other axis and says so. It carries no diff_sha16 and no "
           "disagreements key, so admit_resigned cannot accept it and no row can be ingested on it.",
    "note": "ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88). Lane B / session 50612c81.",
    "lane": "Lane B", "session": "50612c81",
    "current_file": CUR.name, "current_file_sha16": sha16f(CUR),
    "prior_file": PRI.name, "prior_file_sha16": sha16f(PRI),
    "pixel_precondition": "crop_sha16 and candidate_sha16 identical per span, enforced above; a "
                          "comparison over different crops would mean nothing",
    "diagnostic_sha16_rule": "sha256 of json.dumps(this document WITHOUT the diagnostic_sha16 and "
                             "diagnostic_sha16_rule keys, indent=1, ensure_ascii=True, sort_keys=True), "
                             "UTF-8 bytes, first 16 hex. ensure_ascii=True to match _rs_digest in "
                             "ingest_pass2.py, which the resign-diff reports beside this one use.",
    "spans": out,
    "tile_axis_rate": {"rows": len(out),
                       "rows_touched": sum(1 for s in out if s["tile_changes"]),
                       "tiles_compared": sum(s["tiles_compared"] for s in out),
                       "tiles_changed": sum(len(s["tile_changes"]) for s in out),
                       "reversals_corrected_to_confirmed":
                           sum(1 for s in out for c in s["tile_changes"]
                               if c["reversal_corrected_to_confirmed"])},
    "what_this_does_not_solve": [
        "The insertion axis is UNMEASURED, not empty. The current rows carry "
        + ", ".join("%s: %d" % (s["span_id"], s["insertions_in_current_row_NOT_COMPARED"]) for s in out)
        + " insertion(s), and nothing here compares any of them to anything.",
        "No verdict. A changed tile over identical pixels is two human readings disagreeing; which "
        "one is right is a keep/take/neither that only Chris can give, and none is recorded here.",
        "No row is admitted. admit_resigned requires a real diff report; this is not one, by "
        "construction, and these four rows stay unadmitted until the insertion axis has a prior.",
    ],
}
_rule = doc.pop("diagnostic_sha16_rule")
body = json.dumps(doc, indent=1, ensure_ascii=True, sort_keys=True).encode("utf-8")
doc["diagnostic_sha16_rule"] = _rule
doc["diagnostic_sha16"] = hashlib.sha256(body).hexdigest()[:16]
dest = A / ("TILESONLY_pass1_4span_%s.json" % doc["diagnostic_sha16"])
final = json.dumps(doc, indent=1, ensure_ascii=True).encode("utf-8")
assert_inside(dest, "the diagnostic belongs in the audits directory")
if dest.exists() and io.open(dest, "rb").read() != final:
    sys.exit("REFUSING TO CLOBBER: %s exists and holds different bytes" % dest.name)
io.open(dest, "wb").write(final)

print("wrote %s" % dest.name)
print("  tile axis: %(tiles_changed)d/%(tiles_compared)d tiles changed, %(rows_touched)d/%(rows)d rows "
      "touched, %(reversals_corrected_to_confirmed)d corrected->confirmed reversal(s)"
      % doc["tile_axis_rate"])
for s in out:
    print("  %-9s (printed %3d)  %d tile(s) changed of %d, insertions NOT compared: %d   -> %s"
          % (s["span_id"], s["printed_page"], len(s["tile_changes"]), s["tiles_compared"],
             s["insertions_in_current_row_NOT_COMPARED"], s["current_derived_consonants"]))
    for c in s["tile_changes"]:
        print("       tile %d  %s -> %s%s" % (c["i"], json.dumps(c["prior"], ensure_ascii=False),
                                              json.dumps(c["current"], ensure_ascii=False),
                                              "   <== REVERSAL corrected->confirmed"
                                              if c["reversal_corrected_to_confirmed"] else ""))
