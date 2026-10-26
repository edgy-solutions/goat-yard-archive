# -*- coding: utf-8 -*-
u"""Build `span_send_flags.json`, the law-8 send-flag sidecar, from the signing records.

`send_refusal.load_span_flags` refuses a whole send population when this file is absent, and A2's own
INPUT_FLAGS file was deleted on the grounds that *"the flags are properties of the truth-set rows;
your path is the record source"* (A2 -> Lane B, 2026-10-25, section 3).  So Lane B derives it here,
from the three signing records that between them cover all 74 spans.

WHAT THE RECORDS ACTUALLY SAY -- measured 2026-10-25, before this file was written:

| source                      | box_fault                          | partial_in_crop                 |
|-----------------------------|------------------------------------|---------------------------------|
| signing_pass1_ingest (74)   | the disposition vocabulary carries | NO bucket can express it:       |
|                             | `box_fault_edge_cut` (7) and       | DEFAULTED, never measured       |
|                             | `fault_box_wrong_line` (1)         |                                 |
| truth_pass2.jsonl (17)      | no key, and no bucket in its       | `signed_partial_in_crop`:       |
|                             | vocabulary: DEFAULTED              | MEASURED                        |
| truth_pass3_r2.jsonl (3)    | `box_fault` key present: MEASURED  | disposition: MEASURED           |

A POSITIVE pass-1 bucket is a geometry verdict.  Its ABSENCE is not, and that is measured rather
than assumed: pass 1 bucketed `p493:n3` and `p594:n0` as `abstain_candidate_wrong` and `p803:n0` as
`abstain_candidate_short`, and pass 3 then found `box-edge-cut` on all three.  The pass-1 abstain
buckets are verdicts about the CANDIDATE TEXT; they are silent about the box.  So a span with no
positive box_fault record is recorded here as `unverified`, never as clean, and the basis travels
with it per span.

This is why the sidecar carries `basis` beside `populations`: the gate can only do what the ruling
says (refuse the recorded faults), and the record must still state which spans nobody checked.  A
flag file that answered "clean" for all 54 unadjudicated spans would launder a default through the
one gate that exists to stop exactly that (`refusal_reason`: *"a caller who has not looked is not a
caller who has looked and found nothing"*).

SCOPE.  Three populations are derived here -- `box_fault`, `partial_in_crop`, `editorial_insertion`.
The other names in `KNOWN_POPULATIONS` (`corrected_heavy`, `sic`, `multi_word`) are NOT derived, and
their absence from a span's list is not a statement that the span is outside them.  Only the first
two refuse a send (`REFUSING_POPULATIONS`).

ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).
"""
import hashlib
import io
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hebrew_aperture_diag as diag          # noqa: E402
import send_refusal as SR                    # noqa: E402

SET = "0401b636ffa7bf1a"
D = diag.DATA
OUT = os.path.join(str(D), SR.SIDECAR_NAME)
SHEET45 = os.path.join(str(D), "CONTACT_SHEET_scoring45_adb9a26835533dbc_c26745f4be489471bd.json")

F_PASS1 = os.path.join(str(D), "signing_pass1_ingest_%s.json" % SET)
F_PASS2 = os.path.join(str(D), "truth_pass2.jsonl")
F_PASS3 = os.path.join(str(D), "truth_pass3_r2.jsonl")
F_TRUTH74 = os.path.join(str(D), "truth_set74_%s.json" % SET)

# pass-1 buckets that ARE a box verdict.  Everything else in that vocabulary is a verdict about the
# candidate text or the signer's confidence, and says nothing about the box -- see the module note.
P1_BOX_FAULT_BUCKETS = ("box_fault_edge_cut", "fault_box_wrong_line")
P1_SIGNED_BUCKETS = ("signed", "signed_span_aperture_only")

CHECKS = 0


def chk(cond, msg):
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError(msg)


def sha16_bytes(b):
    return hashlib.sha256(b).hexdigest()[:16]


def canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _jl(path):
    return [json.loads(l) for l in io.open(path, encoding="utf-8") if l.strip()]


def _load(path):
    return json.load(io.open(path, encoding="utf-8"))


def _sha_file(path):
    return sha16_bytes(io.open(path, "rb").read())


def git_state(repo):
    """`dirty` from git's own state word, never a hand-rolled diff."""
    try:
        head = subprocess.check_output(["git", "-C", repo, "rev-parse", "HEAD"]).decode().strip()
        por = subprocess.check_output(["git", "-C", repo, "status", "--porcelain"]).decode()
    except Exception as e:                                                   # pragma: no cover
        return {"head": "unknown", "dirty": "unknown", "error": str(e)}
    paths = [l[3:] for l in por.splitlines() if l.strip()]
    return {"head": head, "dirty": bool(paths), "n": len(paths), "paths": sorted(paths)[:20]}


def build():
    p1 = _load(F_PASS1)
    dispo = p1["dispositions"]
    bucket_of = {}
    for k, ids in dispo.items():
        for s in ids:
            chk(s not in bucket_of, "%s is in two pass-1 dispositions (%s, %s)"
                % (s, bucket_of.get(s), k))
            bucket_of[s] = k
    t74 = [r["span_id"] for r in _load(F_TRUTH74)["rows"]]
    chk(len(t74) == 74 and len(set(t74)) == 74, "truth set is not 74 unique spans: %d" % len(t74))
    chk(set(bucket_of) == set(t74),
        "the pass-1 ingest does not cover the truth set exactly: %d vs %d"
        % (len(bucket_of), len(t74)))

    p2 = {r["span_id"]: r for r in _jl(F_PASS2)}
    p3 = {r["span_id"]: r for r in _jl(F_PASS3)}
    chk(not (set(p2) & set(p3)), "a span is in both pass 2 and pass 3")
    p1_signed = sorted(s for s in t74 if bucket_of[s] in P1_SIGNED_BUCKETS)
    signed45 = set(p1_signed) | set(p2) | set(p3)
    chk(len(signed45) == 45, "the three records do not partition 45 signed spans: %d" % len(signed45))

    flags = {}
    for sid in sorted(t74):
        b = bucket_of[sid]
        pops, basis = [], {}
        # ---- box_fault
        if b in P1_BOX_FAULT_BUCKETS:
            pops.append("box_fault")
            basis["box_fault"] = "measured:pass1-disposition=%s" % b
        if sid in p3:
            bf = p3[sid].get("box_fault")
            if bf:
                if "box_fault" not in pops:
                    pops.append("box_fault")
                basis["box_fault"] = "measured:pass3-box_fault=%s" % bf
            else:
                basis["box_fault"] = "measured:pass3-record-has-no-box_fault"
        if "box_fault" not in basis:
            basis["box_fault"] = (
                "unverified:no-positive-record. The pass-1 bucket %r is a verdict about the "
                "candidate text, not the box (pass 1 bucketed p493:n3/p594:n0 "
                "abstain_candidate_wrong and p803:n0 abstain_candidate_short, and pass 3 then "
                "found box-edge-cut on all three). Pass 2 carries no box_fault key and no bucket "
                "that could express one." % b)
        # ---- partial_in_crop
        rec = p3.get(sid) or p2.get(sid)
        if rec is not None:
            d = rec["disposition"]
            if d == "signed_partial_in_crop":
                pops.append("partial_in_crop")
            basis["partial_in_crop"] = "measured:disposition=%s" % d
            if d == "signed_with_editorial_insertion":
                pops.append("editorial_insertion")
        else:
            basis["partial_in_crop"] = (
                "defaulted:not-measured. This span's only record is pass 1, whose disposition "
                "vocabulary has no bucket that can express partial-in-crop; the field was "
                "introduced in pass 2. Absence here is silence, not a clean box.")
        unknown = sorted(set(pops) - set(SR.KNOWN_POPULATIONS))
        chk(not unknown, "%s: population(s) outside KNOWN_POPULATIONS: %s" % (sid, unknown))
        flags[sid] = {"populations": sorted(pops), "basis": basis,
                      "pass": 3 if sid in p3 else (2 if sid in p2 else 1),
                      "pass1_disposition": b,
                      "signed": sid in signed45}

    # ---- the measured breakdown, derived here and asserted below
    def n_basis(flag, kind):
        return sum(1 for v in flags.values() if v["basis"][flag].startswith(kind))

    refusing = {s: sorted(set(v["populations"]) & set(SR.REFUSING_POPULATIONS))
                for s, v in flags.items()}
    refusing = {s: v for s, v in refusing.items() if v}
    box = sorted(s for s, v in flags.items() if "box_fault" in v["populations"])
    partial = sorted(s for s, v in flags.items() if "partial_in_crop" in v["populations"])
    edit = sorted(s for s, v in flags.items() if "editorial_insertion" in v["populations"])

    chk(len(box) == 11, "box_fault over the 74 is %d, expected 11 (7 pass-1 edge-cut + "
                        "p92:n1 wrong-line + 3 pass-3)" % len(box))
    chk(len(partial) == 4, "partial_in_crop over the 74 is %d, expected 4" % len(partial))
    chk(len(edit) == 11, "editorial_insertion is %d, expected 11" % len(edit))
    chk(n_basis("partial_in_crop", "measured") == 20,
        "partial_in_crop measured on %d, expected 20 (17 pass-2 + 3 pass-3)"
        % n_basis("partial_in_crop", "measured"))
    chk(n_basis("partial_in_crop", "defaulted") == 54,
        "partial_in_crop defaulted on %d, expected 54" % n_basis("partial_in_crop", "defaulted"))
    chk(n_basis("box_fault", "measured") == 11,
        "box_fault measured on %d, expected 11" % n_basis("box_fault", "measured"))
    chk(n_basis("box_fault", "unverified") == 63,
        "box_fault unverified on %d, expected 63" % n_basis("box_fault", "unverified"))
    # the counterexample the basis string cites must stay true, or the string is a false claim
    for s in ("p493:n3", "p594:n0", "p803:n0"):
        chk(flags[s]["pass1_disposition"].startswith("abstain_candidate"),
            "%s: pass-1 bucket is %r, so the basis string's counterexample is stale"
            % (s, flags[s]["pass1_disposition"]))
        chk("box_fault" in flags[s]["populations"], "%s should carry box_fault from pass 3" % s)

    # ---- the 45 subset against the contact sheet's own columns.
    # NOT an independent witness: the sheet was derived from these same three records, so agreement
    # is partly by construction.  It is a STALENESS check -- different code, a different read of the
    # same files -- and it would catch a sheet built from an older record or a transcription slip.
    sheet = _load(SHEET45)
    srows = {r["span_id"]: r for r in sheet["rows"]}
    chk(set(srows) == signed45, "the sheet's 45 ids are not the three records' signed set")
    for sid, r in sorted(srows.items()):
        want_p = "partial_in_crop" in flags[sid]["populations"]
        chk(bool(r["partial_in_crop"]) == want_p,
            "%s: sheet partial_in_crop=%r, records say %r" % (sid, r["partial_in_crop"], want_p))
        chk(bool(r["box_fault"]) == ("box_fault" in flags[sid]["populations"]),
            "%s: sheet box_fault=%r disagrees with the records" % (sid, r["box_fault"]))

    out = {
        "kind": "span_send_flags",
        "page_convention": "ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88)",
        "set_digest": SET,
        "built_by": "span_send_flags_build.py (Lane B), 2026-10-25",
        "why": ("send_refusal.load_span_flags refuses a whole population without this file. A2's "
                "INPUT_FLAGS file was deleted and the record source handed to Lane B."),
        "derivation": {
            "sources": {os.path.basename(p): _sha_file(p)
                        for p in (F_PASS1, F_PASS2, F_PASS3, F_TRUTH74)},
            "rule": ("box_fault: positive from a pass-1 box bucket (%s) or a pass-3 box_fault key. "
                     "partial_in_crop: from the pass-2/3 disposition == signed_partial_in_crop. "
                     "editorial_insertion: from disposition == signed_with_editorial_insertion."
                     % ", ".join(P1_BOX_FAULT_BUCKETS)),
            "populations_derived": ["box_fault", "partial_in_crop", "editorial_insertion"],
            "populations_NOT_derived": ["corrected_heavy", "sic", "multi_word"],
            "not_derived_note": ("absence of a non-derived population from a span's list is not a "
                                 "statement that the span is outside it"),
            "basis_vocabulary": {
                "measured": "a record field or disposition bucket decides this flag for this span",
                "defaulted": "no field in any record for this span could express the flag",
                "unverified": ("no POSITIVE record, and the records that exist cannot witness "
                               "absence -- see pass1_bucket_is_not_a_box_verdict"),
            },
            "pass1_bucket_is_not_a_box_verdict": {
                "claim": ("a positive pass-1 box bucket is a geometry verdict; its absence is not"),
                "evidence": {s: flags[s]["pass1_disposition"]
                             for s in ("p493:n3", "p594:n0", "p803:n0")},
                "evidence_note": ("pass 3 found box-edge-cut on all three of these, which pass 1 "
                                  "had bucketed by candidate text"),
            },
            "sheet_crosscheck": ("the 45-span contact sheet's own box_fault / partial_in_crop "
                                 "columns agree 45/45. This is a STALENESS check, not an "
                                 "independent witness: the sheet was built from these same three "
                                 "records, so part of the agreement is by construction."),
        },
        "counts": {
            "n_spans": len(flags), "n_signed": len(signed45),
            "box_fault": box, "partial_in_crop": partial, "editorial_insertion": edit,
            "n_refusing_spans": len(refusing),
            "refusing_populations": list(SR.REFUSING_POPULATIONS),
            "refused_over_74": {s: v for s, v in sorted(refusing.items())},
        },
        "basis_counts": {
            "partial_in_crop": {"measured": n_basis("partial_in_crop", "measured"),
                                "defaulted": n_basis("partial_in_crop", "defaulted")},
            "box_fault": {"measured": n_basis("box_fault", "measured"),
                          "unverified": n_basis("box_fault", "unverified")},
        },
        "what_this_does_NOT_solve": [
            ("The 54 spans whose partial_in_crop is `defaulted` were never checked for it. The gate "
             "sends them because the ruling says to refuse the RECORDED faults; the record says "
             "here that nobody looked. The refused set is a FLOOR."),
            ("box_fault is `unverified` on 63 of 74 for the same reason, and the three pass-3 spans "
             "prove the floor is not tight: pass 1 missed a box-edge-cut on each of them."),
            ("No pixel was read here. This file transcribes signing records; if a signer recorded "
             "the wrong disposition, this file carries it faithfully and no check can see it."),
            ("The sheet cross-check is a staleness check only -- see derivation.sheet_crosscheck."),
        ],
        "git_state": {"goatyard-laneB": git_state("C:/Users/cnogr/git/goatyard-laneB"),
                      "dr-voluminous": git_state("C:/Users/cnogr/git/dr-voluminous")},
        "flags_by_span": flags,
    }
    out["self_sha16_rule"] = ("sha256 of canon(self minus self_sha16/self_sha16_rule)[:16], "
                              "UTF-8 bytes, ensure_ascii=False")
    out["self_sha16"] = sha16_bytes(canon({k: v for k, v in out.items()
                                           if k not in ("self_sha16", "self_sha16_rule")})
                                    .encode("utf-8"))
    return out


def main():
    out = build()
    text = json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n"

    # Everything is verified from a scratch copy FIRST.  A run that fails its own checks must leave
    # nothing behind, and the thing it would leave behind here is the file a paid run is gated on.
    tmp = os.path.join(os.environ.get("TEMP", "."), "span_send_flags.verify.json")
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    got = SR.load_span_flags(tmp)
    chk(len(got) == 74, "load_span_flags round-trip gave %d spans" % len(got))
    ids45 = sorted(s for s, v in out["flags_by_span"].items() if v["signed"])
    plan = SR.refuse_at_send(ids45, got, on_refused="record")
    chk(sorted(plan.refused) == ["p190:n0", "p493:n3", "p594:n0", "p803:n0"],
        "the 45-span refused set is %r, not the four agreed ids" % sorted(plan.refused))
    chk(plan.report["n"] == 41 and plan.report["n_refused"] == 4, "41 + 4 is not the 45")
    if CHECKS != EXPECTED_CHECKS:
        os.remove(tmp)
        raise AssertionError("CHECKS %d != EXPECTED_CHECKS %d -- nothing written"
                             % (CHECKS, EXPECTED_CHECKS))
    os.remove(tmp)

    # every check passed: now the file may land
    if os.path.exists(OUT):
        old = io.open(OUT, encoding="utf-8").read()
        if old == text:
            print("unchanged: %s (self_sha16 %s)" % (OUT, out["self_sha16"]))
        else:
            raise SystemExit(
                "refusing to clobber %s: it exists and differs. A send-flag sidecar is what a paid "
                "run was gated on; move the old one aside deliberately if it is stale." % OUT)
    else:
        with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("wrote %s (self_sha16 %s)" % (OUT, out["self_sha16"]))
    print("ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).")
    print("box_fault %d, partial_in_crop %d, editorial_insertion %d over 74; refusing spans %d"
          % (len(out["counts"]["box_fault"]), len(out["counts"]["partial_in_crop"]),
             len(out["counts"]["editorial_insertion"]), out["counts"]["n_refusing_spans"]))
    print("basis: partial_in_crop measured %d / defaulted %d; box_fault measured %d / unverified %d"
          % (out["basis_counts"]["partial_in_crop"]["measured"],
             out["basis_counts"]["partial_in_crop"]["defaulted"],
             out["basis_counts"]["box_fault"]["measured"],
             out["basis_counts"]["box_fault"]["unverified"]))
    print("checks: %d" % CHECKS)
    return 0


EXPECTED_CHECKS = 259      # measured 2026-10-25; the first run printed it and wrote nothing


if __name__ == "__main__":
    sys.exit(main())
