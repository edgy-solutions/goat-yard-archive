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

from write_scope import assert_inside

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hebrew_aperture_diag as HAD                                        # noqa: E402
from clean_run import git_state, provisional                              # noqa: E402
import apparatus_signature_rule as RULE                                   # noqa: E402  one source of the rule
import glyph_abstention as GA                                              # noqa: E402  item 4
import signature_attestation as SA                                        # noqa: E402  second-look marker only

SET, SET_N = "0401b636ffa7bf1a", 26
PRINTED_OFFSET = 88
REPOS = {"goatyard-laneB": "C:/Users/cnogr/git/goatyard-laneB",
         "dr-voluminous": "C:/Users/cnogr/git/dr-voluminous"}
EXPECTED_CHECKS = 2 * SET_N + 13          # 2 per row, plus twelve file-level checks and the final count check

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

# ---------------------------------------------------------------- re-signing diff gate
# A re-signing round can INTRODUCE errors as well as fix them (p493:n3 tile 4: pass 2 `corrected` to resh,
# pass 3 `confirmed` the printed final-pe). A changed tile over IDENTICAL pixels is an adjudication event:
# two human verdicts about the same crop disagree. This surfaces the pair; it never says which is right.
# No score, no winner, no dictionary, no word-likeness: the verdict per disagreement is keep / take /
# neither and is a human's. A re-signed row is admitted only through admit_resigned(), which requires the
# diff this function produced and a human verdict for every disagreement in it.
#
# WHAT THIS DOES NOT SOLVE. It cannot tell a regression from a fix; it makes the pair impossible to miss.
# It compares two signed exports only: a wrong verdict that both rounds agree on is invisible to it.

def sha16(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode("utf-8")).hexdigest()[:16]


class ResignDiffError(Exception):
    pass


ADJUDICATIONS = ("keep", "take", "neither")      # keep = prior reading, take = current reading


def _rs_file_sha16(path):
    return hashlib.sha256(io.open(path, "rb").read()).hexdigest()[:16]


# A RULING about a named sitting, pinned by the signed file's hash, by the provenance record's own
# hash, and by the truth standing that record must state. All three by equality: a record is
# self-consistent by construction, so without the record hash a hand-written record stating a
# different standing would hash fine and lift the ruling. This is a pinned ADJUDICATION, the same
# shape as SEALED_TRUTH -- not a pinned measurement, which is the thing that goes stale.
SITTING_RULINGS = {
    "50d419a4e1cafbc4": {
        "record_sha16": "d60c86def66861e3",
        "no_row_is_truth_on_its_own": True,
        "ruling": "advisor ruling 2026-11-15 item 1: a Claude model read each crop aloud to Chris "
                  "during the sitting; no row from this sitting is truth on its own",
    },
}


def _sitting_fault(sitting, current_sha16, span_id):
    """Why this sitting-provenance record does NOT cover this row, or "" if it does.

    The hash rule is recomputed here from the record's own terms and shares no code with
    `sitting_provenance.py`, which wrote it -- a verifier that calls the producer agrees by
    construction. Every provenance field must be a real bool: the export has no channel for how a
    sitting was conducted, and a field that may be absent is the silence the record exists to end."""
    if not isinstance(sitting, dict):
        return "the sitting provenance is not an object"
    if sitting.get("kind") != "sitting_provenance":
        return "the record is of kind %r, not sitting_provenance" % sitting.get("kind")
    if not current_sha16:
        return ("the diff report records no current file hash, so no record can be matched to it by "
                "equality")
    if sitting.get("describes_file_sha16") != current_sha16:
        return ("the record describes the file %r, not the file this diff compared (%r)"
                % (sitting.get("describes_file_sha16"), current_sha16))
    rows = sitting.get("rows")
    if not isinstance(rows, dict) or not rows:
        return "the record covers no rows, so it would cover every row by vacuity"
    if span_id not in rows:
        return "the record does not cover %s; it covers %s" % (span_id, ", ".join(sorted(rows)))
    per_row = rows[span_id] if isinstance(rows[span_id], dict) else {}
    if not isinstance(per_row.get("signed_with_advisor_reading"), bool):
        return ("the record states no boolean signed_with_advisor_reading for %s (%r)"
                % (span_id, per_row.get("signed_with_advisor_reading")))
    if not isinstance(sitting.get("signed_with_advisor_reading"), bool):
        return ("the record states no boolean signed_with_advisor_reading for the sitting (%r)"
                % sitting.get("signed_with_advisor_reading"))
    standing = sitting.get("no_row_is_truth_on_its_own")
    if not isinstance(standing, bool):
        return "the record states no boolean no_row_is_truth_on_its_own (%r)" % (standing,)
    if standing and not str(sitting.get("what_would_lift_it") or "").strip():
        return ("the record withholds truth standing and names nothing that would lift it; a refusal "
                "that names no way out is a dead end, not a gate")
    claimed = sitting.get("record_sha16")
    body = {k: v for k, v in sitting.items() if k not in ("record_sha16", "record_sha16_rule")}
    got = sha16(json.dumps(body, indent=1, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    if claimed != got:
        return "the record was altered after it was written (claims %r, is %r)" % (claimed, got)
    ruling = SITTING_RULINGS.get(current_sha16)
    if ruling and claimed != ruling["record_sha16"]:
        # The hash was recomputed from the record's own body just above, so pinning the hash pins
        # EVERY field of the ruled record, the truth standing included. A separate comparison of the
        # standing could not be reached by any record and could not be killed by any mutation -- an
        # unreachable check reads as a second line of defence that is not there.
        return ("this file is under a ruling that names record %s; the record supplied is %s"
                % (ruling["record_sha16"], claimed))
    return ""


def _rs_basis_token(basis):
    """The part of a channel basis the diff digest must cover, so a basis cannot be attached to a
    diff after the fact. EMPTY when there is no basis, which keeps the formula -- and so the
    diff_sha16 of every report already written -- byte-for-byte what it was."""
    if not basis:
        return ""
    return "|basis:%s:%s:%s:%s" % (basis.get("kind"), basis.get("channel"),
                                   basis.get("side"), basis.get("commit"))


def _rs_digest(dis, current_sha16, prior_sha16, ids, basis=None):
    body = json.dumps([{k: v for k, v in d.items() if k != "adjudication"} for d in dis],
                      sort_keys=True, ensure_ascii=True)
    return sha16(sha16(body) + "|" + current_sha16 + "|" + prior_sha16 + "|" + ",".join(ids)
                 + _rs_basis_token(basis))


def _rs_basis_fault(basis, missing_sides, current_sha16, prior_sha16):
    """Why this channel basis does NOT license this comparison, or "" if it does.

    A licence by NAMED INSTANCE, with equality: the record must name the side that is actually
    absent and the very file being compared. The hash rule is recomputed here from the record's own
    terms and shares no code with the script that wrote it -- a verifier that calls the producer
    agrees by construction."""
    if not isinstance(basis, dict):
        return "the channel basis is not an object"
    if basis.get("kind") != "channel_absent_by_construction":
        return "the basis is of kind %r, not channel_absent_by_construction" % basis.get("kind")
    if basis.get("channel") != "insertions":
        return "the basis is about the %r channel, not insertions" % basis.get("channel")
    side = basis.get("side")
    if side not in ("current", "prior"):
        return "the basis names side %r" % side
    if set(missing_sides) != {side}:
        return ("the basis licenses the %s side, but the channel is absent from %s"
                % (side, " and ".join(missing_sides)))
    if not re.match(r"^[0-9a-f]{40}$", str(basis.get("commit") or "")):
        return "the basis carries no 40-hex commit (%r)" % basis.get("commit")
    if basis.get("insert_tokens_not_allowed_found"):
        return ("the basis claims the channel is absent by construction while listing %s as present"
                % basis["insert_tokens_not_allowed_found"])
    want = {"prior": ("licenses_prior_file_sha16", prior_sha16),
            "current": ("licenses_current_file_sha16", current_sha16)}[side]
    if not want[1] or basis.get(want[0]) != want[1]:
        return ("the basis licenses %s %r, not the %s file being compared (%r)"
                % (want[0], basis.get(want[0]), side, want[1]))
    claimed = basis.get("record_sha16")
    body = {k: v for k, v in basis.items() if k not in ("record_sha16", "record_sha16_rule")}
    got = sha16(json.dumps(body, indent=1, ensure_ascii=True, sort_keys=True).encode("utf-8"))
    if claimed != got:
        return "the basis record was altered after it was written (claims %r, is %r)" % (claimed, got)
    return ""


def diff_resigned(current_rows, prior_rows, current_sha16="", prior_sha16="", channel_basis=None):
    """Every tile whose (shown, verdict, chose) changed and every insertion whose (chose, verdict) changed,
    for each span in `current_rows`, against `prior_rows`. Raises ResignDiffError unless crop_sha16 and
    candidate_sha16 are identical for every compared span (a diff only means something over the same
    pixels), the tile index sets agree, and BOTH exports carry an `insertions` channel at all -- an
    absent channel is not an empty one. An absent channel is read as empty ONLY against a
    `channel_basis` record that names the absent side and the exact file by hash, carries the commit
    whose source has no such UI, and verifies against its own hash rule; the basis rides into
    `diff_sha16`, so it cannot be attached to a diff afterwards. Returns the report; `adjudication` is None on every entry."""
    prior = {r["span_id"]: r for r in prior_rows}
    if len(prior) != len(prior_rows):
        raise ResignDiffError("duplicate span_id in the prior export")
    cur_ids = [r["span_id"] for r in current_rows]
    if len(set(cur_ids)) != len(cur_ids):
        raise ResignDiffError("duplicate span_id in the current export")
    dis, rows_touched, reversal_rows = [], set(), set()
    n_tiles = n_ins = n_rev = 0
    for r in current_rows:
        sid = r["span_id"]
        if sid not in prior:
            raise ResignDiffError("%s is in the current export but has no prior row to compare" % sid)
        p = prior[sid]
        for k in ("crop_sha16", "candidate_sha16"):
            if not r.get(k) or r.get(k) != p.get(k):
                raise ResignDiffError("%s: %s differs (%r vs %r) -- not the same pixels, a diff means nothing"
                                      % (sid, k, r.get(k), p.get(k)))
        ct, pt = {t["i"]: t for t in r["tiles"]}, {t["i"]: t for t in p["tiles"]}
        if len(ct) != len(r["tiles"]) or len(pt) != len(p["tiles"]) or set(ct) != set(pt):
            raise ResignDiffError("%s: the tile index sets differ over identical pixels" % sid)
        for i in sorted(ct):
            a, b = pt[i], ct[i]
            ka = (a.get("shown") or "", a.get("verdict") or "", a.get("chose") or "")
            kb = (b.get("shown") or "", b.get("verdict") or "", b.get("chose") or "")
            if ka != kb:
                rev = (ka[1] == "corrected" and kb[1] == "confirmed")
                dis.append({"span_id": sid, "what": "tile", "i": i, "kind": b.get("kind"),
                            "prior": {"shown": ka[0], "verdict": ka[1], "chose": ka[2]},
                            "current": {"shown": kb[0], "verdict": kb[1], "chose": kb[2]},
                            "reversal_corrected_to_confirmed": rev, "adjudication": None})
                n_tiles += 1
                rows_touched.add(sid)
                if rev:
                    n_rev += 1
                    reversal_rows.add(sid)

        # An ABSENT insertion channel is not an EMPTY one. The 2026-10-04 pass-1 console had no
        # insertion channel at all, and the line below used to die with a bare KeyError -- a refusal
        # the caller could not read. Coercing the missing key to [] would be worse: it would assert
        # that that signer looked at the span and made no insertions, which the file does not say.
        missing = [w for w, d in (("current", r), ("prior", p)) if "insertions" not in d]
        if missing:
            why = _rs_basis_fault(channel_basis, missing, current_sha16, prior_sha16)
            if why:
                raise ResignDiffError(
                    "%s: the %s export has no 'insertions' channel at all. An absent channel is not "
                    "an empty channel: reading it as [] would assert that signer made no insertions, "
                    "which the file does not say. %s" % (
                        sid, " and ".join(missing),
                        ("No channel basis was given. Supply a channel_absent_by_construction record "
                         "naming the build whose source has no insertion UI, or rule on the row "
                         "without a diff." if channel_basis is None
                         else "A channel basis was given and does NOT license this comparison: %s."
                              % why)))
            # Licensed: the named build could not emit an insertion, so there was none to record.
            # Read as empty HERE ONLY, never written back into anybody's file.
            r = dict(r, insertions=r.get("insertions") or [])
            p = dict(p, insertions=p.get("insertions") or [])

        def ikey(x):
            return (x.get("seq"), x.get("after_i"), x.get("kind"))
        ci, pi = {ikey(x): x for x in r["insertions"]}, {ikey(x): x for x in p["insertions"]}
        if len(ci) != len(r["insertions"]) or len(pi) != len(p["insertions"]):
            raise ResignDiffError("%s: duplicate insertion key" % sid)
        for k in sorted(set(ci) | set(pi), key=lambda z: (z[0] is None, z[0] or 0, str(z))):
            a, b = pi.get(k), ci.get(k)
            ka = None if a is None else (a.get("chose") or "", a.get("verdict") or "")
            kb = None if b is None else (b.get("chose") or "", b.get("verdict") or "")
            if ka != kb:
                dis.append({"span_id": sid, "what": "insertion", "seq": k[0], "after_i": k[1], "kind": k[2],
                            "prior": None if ka is None else {"chose": ka[0], "verdict": ka[1]},
                            "current": None if kb is None else {"chose": kb[0], "verdict": kb[1]},
                            "reversal_corrected_to_confirmed": False, "adjudication": None})
                n_ins += 1
                rows_touched.add(sid)
    basis_out = None
    if channel_basis:
        basis_out = {"kind": channel_basis.get("kind"), "channel": channel_basis.get("channel"),
                     "side": channel_basis.get("side"), "commit": channel_basis.get("commit"),
                     "record_sha16": channel_basis.get("record_sha16"),
                     "verdict": channel_basis.get("verdict")}
    return {"current_file_sha16": current_sha16, "prior_file_sha16": prior_sha16,
            "channel_basis": basis_out,
            "spans_compared": cur_ids,
            "pixels": {r["span_id"]: [r["crop_sha16"], r["candidate_sha16"]] for r in current_rows},
            "disagreements": dis,
            "rate": {"rows_compared": len(cur_ids), "rows_touched": len(rows_touched),
                     "tiles_compared": sum(len(r["tiles"]) for r in current_rows), "tiles_changed": n_tiles,
                     "insertions_changed": n_ins, "reversals_corrected_to_confirmed": n_rev,
                     "reversal_rows": sorted(reversal_rows)},
            "diff_sha16": _rs_digest(dis, current_sha16, prior_sha16, cur_ids, channel_basis)}


def admit_resigned(row, report, adjudications=None, sitting=None):
    """The only door a re-signed row goes through. Refuses unless `report` is an intact output of
    diff_resigned covering this row, and every disagreement on this row carries a human verdict in
    ADJUDICATIONS (adjudications: {(span_id, what, i_or_seq): 'keep'|'take'|'neither'}). Returns a copy of
    the row annotated with the diff id; it does not choose between readings.

    `sitting` is the sitting-provenance record for the file this diff took as CURRENT. It is required
    whenever that file is under a ruling in SITTING_RULINGS, and admitting such a row without it would
    assert that nothing influenced the signer -- a claim nobody made, since the export's only
    provenance field is a constant. A record that withholds truth standing REFUSES here, which in the
    round-2 shape puts the row in `held_rows` with the reason, where a reader looks.

    A row whose NOTE abstains about a letter one of its tiles presents is refused too, until a human
    gives that tile a keep/take/neither verdict under the key (span_id, "glyph_abstention", i). The
    signer's "could be vav or nun" is a verdict of its own, and a pipeline that reads only the
    structural channels turns their honesty into its own confident letter.

    There is deliberately NO door for a later sitting's confirmation: the second sitting produces its
    own file, with its own provenance record, and that file is then the current side of its own diff.
    A confirmation format nobody has written yet would be a door with no key and a hole for a weak
    one."""
    if not isinstance(report, dict) or "diff_sha16" not in report or "disagreements" not in report:
        raise ResignDiffError("no diff report: a re-signed row is not admitted without the diff")
    sid = row["span_id"]
    if sid not in report["spans_compared"]:
        raise ResignDiffError("%s was not covered by the diff" % sid)
    if report["pixels"][sid] != [row.get("crop_sha16"), row.get("candidate_sha16")]:
        raise ResignDiffError("%s: the row's pixels are not the ones the diff compared" % sid)
    if report["diff_sha16"] != _rs_digest(report["disagreements"], report["current_file_sha16"],
                                          report["prior_file_sha16"], report["spans_compared"],
                                          report.get("channel_basis")):
        raise ResignDiffError("the diff report was altered after it was produced")
    _cf = report.get("current_file_sha16")
    _ruling = SITTING_RULINGS.get(_cf)
    if _ruling is not None and sitting is None:
        raise ResignDiffError(
            "%s: the current file %s is under a ruling and no sitting-provenance record was supplied. "
            "%s. The export has no channel for how a sitting was conducted -- every row of every "
            "sitting carries the same constant signed_in -- so admitting this row in silence would "
            "assert that nothing influenced the signer." % (sid, _cf, _ruling["ruling"]))
    if sitting is not None:
        _why = _sitting_fault(sitting, _cf, sid)
        if _why:
            raise ResignDiffError("%s: the sitting-provenance record does not cover this row: %s"
                                  % (sid, _why))
        if sitting["no_row_is_truth_on_its_own"]:
            raise ResignDiffError(
                "%s: no row from this sitting is truth on its own (%s). What would lift it: %s"
                % (sid, sitting.get("ruled_by") or "ruling not named on the record",
                   sitting["what_would_lift_it"]))
    adjudications = adjudications or {}
    for d in report["disagreements"]:
        if d["span_id"] != sid:
            continue
        key = (sid, d["what"], d["i"] if d["what"] == "tile" else d["seq"])
        if adjudications.get(key) not in ADJUDICATIONS:
            raise ResignDiffError("%s %s %s changed over identical pixels and has no keep/take/neither "
                                  "verdict from a human" % key)
    # The signer's own doubt about WHICH LETTER the ink is. Computed from the row (note + tiles),
    # not from the diff, so it stands whether or not anything changed between sittings. Placed after
    # the adjudication loop so no refusal that exists today changes what it reports.
    _abst = GA.verdict(row)
    if _abst is not None:
        for _t in _abst["tiles_presenting_a_rival"]:
            _key = (sid, "glyph_abstention", _t["i"])
            if adjudications.get(_key) not in ADJUDICATIONS:
                raise ResignDiffError(
                    "%s tile %d presents %s while the signer's note abstains between %s -- %r. An "
                    "abstention is a verdict, not a silence: the row has no keep/take/neither "
                    "verdict for it from a human. What would lift it: %s"
                    % (sid, _t["i"], _t["presents"], "/".join(_abst["names"]), _abst["reason"],
                       _abst["what_would_lift_it"]))
    out = dict(row)
    out["resign_diff_sha16"] = report["diff_sha16"]
    if _abst is not None:
        # Kept even once adjudicated: the doubt was real and a human overruled it. A row that dropped
        # the record on decision would present the same unqualified letter the ruling objected to.
        out["glyph_abstention"] = dict(_abst, adjudicated={
            str(_t["i"]): adjudications.get((sid, "glyph_abstention", _t["i"]))
            for _t in _abst["tiles_presenting_a_rival"]})
    if sitting is not None:
        # The row names how its own sitting was conducted. Reached only when the record does NOT
        # withhold truth standing; a withheld row raised above and is never stamped as admitted.
        out["sitting_provenance"] = {
            "describes_file_sha16": sitting["describes_file_sha16"],
            "record_sha16": sitting["record_sha16"],
            "signed_with_advisor_reading": sitting["rows"][sid]["signed_with_advisor_reading"],
            "ruled_by": sitting.get("ruled_by"),
            "means": "what was in the room when this row was signed, recorded beside the signed file "
                     "because the export has no field for it"}
    if report.get("channel_basis"):
        # The row names its own licence. A row admitted over an ABSENT channel must carry what made
        # that admissible, or a later reader sees a clean diff and no sign that one axis of it was
        # read as empty by construction rather than measured.
        b = report["channel_basis"]
        out["channel_read_as_empty_by_construction"] = {
            "channel": b["channel"], "side": b["side"], "commit": b["commit"],
            "basis_record_sha16": b["record_sha16"],
            "means": "the build named above could not emit this channel, so its absence is not a "
                     "signer's silence; nothing on this axis was compared"}
    return out


def format_resign_diff(rep):
    L = []
    for d in rep["disagreements"]:
        loc = ("%s tile %d" % (d["span_id"], d["i"])) if d["what"] == "tile" else \
              ("%s insertion seq %s after_i %s" % (d["span_id"], d["seq"], d["after_i"]))
        L.append("  %-30s prior %s  ->  current %s%s" % (
            loc, json.dumps(d["prior"], ensure_ascii=True), json.dumps(d["current"], ensure_ascii=True),
            "   <== REVERSAL corrected->confirmed (a prior reading discarded)"
            if d["reversal_corrected_to_confirmed"] else ""))
    r = rep["rate"]
    L.append("rate: %d/%d tiles changed, %d insertion(s) changed, %d/%d row(s) touched, "
             "%d corrected->confirmed reversal(s) in row(s) %s" % (
                 r["tiles_changed"], r["tiles_compared"], r["insertions_changed"], r["rows_touched"],
                 r["rows_compared"], r["reversals_corrected_to_confirmed"], r["reversal_rows"]))
    b = rep.get("channel_basis")
    if b:
        L.append("channel basis: the %s side's `%s` channel read as EMPTY BY CONSTRUCTION -- %s, "
                 "commit %s, record %s" % (b["side"], b["channel"], b["verdict"], b["commit"][:12],
                                           b["record_sha16"]))
    L.append("pixels identical for all %d span(s); diff_sha16 %s; every verdict (keep/take/neither) is "
             "still a human's" % (r["rows_compared"], rep["diff_sha16"]))
    return "\n".join(L)


EXPECTED_CHECKS_RESIGN = 35          # 21 diff/basis + 11 sitting-gate + 3 abstention


def resign_selftest():
    """The REFUSAL branches of diff_resigned, over synthetic rows. No data file read, nothing written.

    These are the branches a green run never visits: every refusal here is a path the three real
    exports do not take. Each case names the refusal it expects, so a refusal that stopped firing, or
    started firing for a different reason, fails rather than passes.

    The discriminating case is case 3: two exports that both carry an EMPTY insertions channel must
    diff CLEANLY. Without it, a guard written as `if not r["insertions"]` would satisfy every other
    case in this function while turning a signer's statement that he made no insertions into a
    refusal -- the exact confusion the guard exists to prevent, passing as a green run.
    """
    def row(sid, tiles, ins=(), crop="c0", cand="d0"):
        return {"span_id": sid, "crop_sha16": crop, "candidate_sha16": cand,
                "tiles": [dict(t) for t in tiles], "insertions": [dict(x) for x in ins]}

    def refuses(cur, pri, want, label, basis_arg=None):
        # An untyped blow-up is NOT a refusal. `KeyError: 'insertions'` is what the pass-1 diff
        # actually printed, and no caller could read what had been refused or why. Catch anything,
        # name the type, and require the refusal to be the typed one.
        msg, typed = "", False
        try:
            diff_resigned(cur, pri, "CUR16" if basis_arg else "cur",
                          "PRI16" if basis_arg else "pri", basis_arg)
        except ResignDiffError as e:
            msg, typed = str(e), True
        except Exception as e:
            msg = "UNTYPED %s: %s" % (type(e).__name__, e)
        check(typed and all(w in msg for w in want),
              "%s: expected a ResignDiffError naming %s, got %r" % (label, list(want), msg))

    T = [{"i": 0, "kind": "consonant", "shown": "a", "verdict": "confirmed", "chose": ""},
         {"i": 1, "kind": "consonant", "shown": "b", "verdict": "confirmed", "chose": ""}]
    base = row("p1:n0", T)
    noins = dict((k, v) for k, v in base.items() if k != "insertions")

    # 1-2. the absent channel, each side, named as the side it is absent from
    refuses([base], [noins], ("p1:n0", "prior", "'insertions' channel"), "prior lacks the channel")
    refuses([noins], [base], ("p1:n0", "current", "'insertions' channel"), "current lacks the channel")

    # 3. THE CONTROL: an empty channel is a statement, not an absence. It must diff.
    def diffs(cur, pri, label):
        # A case that expects a RESULT must not be left to raise: an exception in a test file ends the
        # run, so the check below would never evaluate and its message would never print. Fold the
        # exception into the check instead, and let the check say what happened.
        try:
            return diff_resigned(cur, pri, "cur", "pri"), ""
        except Exception as e:
            return None, "REFUSED %s: %s" % (type(e).__name__, e)

    rep, why = diffs([row("p1:n0", T)], [row("p1:n0", T)], "the control")
    check(rep is not None and rep["disagreements"] == [] and rep["rate"]["rows_touched"] == 0,
          "two identical rows with EMPTY insertion channels did not diff cleanly: %s"
          % (why or rep["rate"]))

    # 4. the pixel gate: a different hash and an absent hash are both refusals
    refuses([row("p1:n0", T, crop="X")], [base], ("crop_sha16 differs",), "crop hash differs")
    refuses([row("p1:n0", T, cand="")], [base], ("candidate_sha16 differs",), "candidate hash empty")

    # 5. a current row with nothing to compare against
    refuses([base], [row("p9:n9", T)], ("p1:n0", "no prior row"), "no prior row")

    # 6. duplicate span ids, each side
    refuses([base, base], [base], ("duplicate span_id in the current export",), "duplicate current")
    refuses([base], [base, base], ("duplicate span_id in the prior export",), "duplicate prior")

    # 7. the tile index sets
    refuses([base], [row("p1:n0", T[:1])], ("tile index sets differ",), "tile index sets")

    # 8. a positive, so the refusals above are not passing by refusing everything
    rep, why = diffs([row("p1:n0", [T[0], dict(T[1], verdict="corrected", chose="z")],
                          ins=[{"seq": 0, "after_i": 0, "kind": "consonant",
                                "chose": "q", "verdict": "confirmed"}])],
                     [base], "the positive case")
    dis = [] if rep is None else rep["disagreements"]
    check(rep is not None and [(d["what"], d.get("i"), d.get("seq")) for d in dis]
          == [("tile", 1, None), ("insertion", None, 0)],
          "the positive case found %s" % (why or dis))
    check(rep is not None and rep["rate"]["tiles_changed"] == 1
          and rep["rate"]["insertions_changed"] == 1
          and rep["rate"]["reversals_corrected_to_confirmed"] == 0,
          "the positive case counted %s" % (why or rep["rate"]))
    check(rep is not None and all(d["adjudication"] is None for d in dis),
          "a disagreement came out of the diff pre-adjudicated: %s" % (why or dis))

    # 9. the channel basis: the refusal is lifted by a CITED record, and by nothing else.
    def basis(**over):
        b = {"kind": "channel_absent_by_construction", "verdict": "insertions channel absent by "
             "construction", "channel": "insertions", "side": "prior",
             "licenses_prior_file_sha16": "PRI16", "commit": "a" * 40,
             "insert_tokens_not_allowed_found": []}
        b.update(over)
        body = {k: v for k, v in b.items() if k not in ("record_sha16", "record_sha16_rule")}
        b["record_sha16"] = sha16(json.dumps(body, indent=1, ensure_ascii=True,
                                             sort_keys=True).encode("utf-8"))
        b.update((k, v) for k, v in over.items() if k == "record_sha16")
        return b

    pass1 = {k: v for k, v in base.items() if k != "insertions"}      # the prior with NO channel
    cur1 = row("p1:n0", T)                                           # the current, with one

    def with_basis(b):
        try:
            return diff_resigned([cur1], [pass1], "CUR16", "PRI16", b), ""
        except Exception as e:
            return None, "REFUSED %s: %s" % (type(e).__name__, e)

    rep, why = with_basis(basis())
    check(rep is not None and rep["disagreements"] == []
          and (rep.get("channel_basis") or {}).get("commit") == "a" * 40,
          "a correct basis did not license the comparison: %s" % (why or rep))
    # The basis is INSIDE the digest. Recomputed without it, the id must differ -- otherwise a basis
    # could be bolted onto a report that was produced without one.
    check(rep is not None and rep["diff_sha16"] != _rs_digest(
        rep["disagreements"], "CUR16", "PRI16", rep["spans_compared"], None),
        "the diff id does not cover the basis, so a basis could be attached after the fact")
    # ... and the door notices if it is taken away again.
    stripped, admitted = dict(rep, channel_basis=None), None
    try:
        admit_resigned(cur1, rep)
        admitted = True
    except ResignDiffError as e:
        admitted = "REFUSED: %s" % e
    strip_ok = False
    try:
        admit_resigned(cur1, stripped)
    except ResignDiffError:
        strip_ok = True
    check(admitted is True and strip_ok,
          "admit: with the basis %r; stripping it refused: %s" % (admitted, strip_ok))

    refuses([cur1], [pass1], ("not the prior file being compared",), "basis names another file",
            basis(licenses_prior_file_sha16="SOMEONEELSE"))
    refuses([cur1], [pass1], ("licenses the current side",), "basis names the wrong side",
            basis(side="current", licenses_current_file_sha16="CUR16"))
    refuses([cur1], [pass1], ("altered after it was written",), "basis record altered",
            basis(record_sha16="0" * 16))
    refuses([cur1], [pass1], ("while listing",), "basis lists insertion machinery",
            basis(insert_tokens_not_allowed_found=["insertRow"]))
    refuses([cur1], [pass1], ("not insertions",), "basis is about another channel",
            basis(channel="tiles"))

    # ---------------------------------------------------------------- the sitting gate
    # Synthetic records, hashed here, so nothing is read from disk. RULED is the file hash the ruling
    # names; UNRULED is any other sitting, where a record is optional but still validated.
    RULED, UNRULED = "50d419a4e1cafbc4", "aaaa0000bbbb1111"

    def sitting(file_sha16=UNRULED, rows=None, standing=True, lift="a second sitting", **kw):
        rec = {"kind": "sitting_provenance", "describes_file_sha16": file_sha16,
               "rows": rows if rows is not None else {"s1": {"signed_with_advisor_reading": True}},
               "signed_with_advisor_reading": True, "no_row_is_truth_on_its_own": standing,
               "what_would_lift_it": lift, "ruled_by": "a ruling"}
        rec.update(kw)
        if "record_sha16" not in kw:
            body = {k: v for k, v in rec.items() if k not in ("record_sha16", "record_sha16_rule")}
            rec["record_sha16"] = sha16(json.dumps(body, indent=1, sort_keys=True,
                                                   ensure_ascii=False).encode("utf-8"))
        return rec

    def adm(cur_sha16, sit, row_sid="s1"):
        """Admit cur1 through a clean diff whose CURRENT file hash is cur_sha16. Returns the admitted
        row, or the refusal text."""
        r = dict(cur1, span_id=row_sid)
        rep2 = diff_resigned([r], [r], cur_sha16, "PRI16")
        try:
            return admit_resigned(r, rep2, {}, sit)
        except ResignDiffError as e:
            return "REFUSED: %s" % e

    def sit_refuses(sit, needle, label, cur_sha16=UNRULED):
        got = adm(cur_sha16, sit)
        check(isinstance(got, str) and needle in got, "%s: expected a refusal naming %r, got %r"
              % (label, needle, got))

    # (a) a file under a ruling, with no record at all: silence must not admit it
    got = adm(RULED, None)
    check(isinstance(got, str) and "under a ruling and no sitting-provenance record" in got
          and "nothing influenced the signer" in got,
          "a ruled file admitted a row with no provenance record: %r" % got)

    # (b) a ruled file with a record that is not the one the ruling names: refused, so the ruling
    # cannot be talked round with a self-consistent record of somebody's own making
    sit_refuses(sitting(file_sha16=RULED, standing=False),
                "names record d60c86def66861e3", "a ruled file took another record", RULED)

    # (c) a record that withholds truth standing refuses, and the refusal carries the way out
    got = adm(UNRULED, sitting(standing=True, lift="a second sitting, blind, no model reading"))
    check(isinstance(got, str) and "no row from this sitting is truth on its own" in got
          and "blind, no model reading" in got,
          "a withheld sitting did not refuse with its way out: %r" % got)

    # (d) THE DISCRIMINATING CASE: a record that does not withhold standing ADMITS, and the row then
    # carries how it was signed. Without this, "refuse whenever a record is present" would pass (a-c).
    got = adm(UNRULED, sitting(standing=False))
    # `.get(...) or {}`: with the stamp gone this check must FAIL with its own message, not raise.
    # A raise in a hand-rolled suite aborts the run, and an aborted run loses every later assertion.
    _sp = (got.get("sitting_provenance") or {}) if isinstance(got, dict) else {}
    check(isinstance(got, dict) and _sp.get("signed_with_advisor_reading") is True
          and _sp.get("describes_file_sha16") == UNRULED,
          "a sitting that does not withhold standing failed to admit and stamp: %r" % got)

    # (k) the stamp reads the ROW, not the sitting: the ruling is about rows, and a sitting where
    # only some crops were read aloud is a sitting the record can state. With both values True
    # everywhere else, nothing could tell a row-level read from a sitting-level one.
    got = adm(UNRULED, sitting(standing=False, signed_with_advisor_reading=True,
                               rows={"s1": {"signed_with_advisor_reading": False}}))
    _sp = (got.get("sitting_provenance") or {}) if isinstance(got, dict) else {}
    check(isinstance(got, dict) and _sp.get("signed_with_advisor_reading") is False,
          "the stamp took the sitting-level flag where the row's differs: %r" % got)

    # (e-j) the record must be ABOUT this file, this row, and must not have moved
    sit_refuses(sitting(file_sha16="ffff0000ffff0000", standing=False),
                "not the file this diff compared", "record about another file")
    sit_refuses(sitting(rows={"somebody_else": {"signed_with_advisor_reading": True}}, standing=False),
                "does not cover s1", "record does not cover the row")
    sit_refuses(sitting(rows={"s1": {"signed_with_advisor_reading": "yes"}}, standing=False),
                "no boolean signed_with_advisor_reading for s1", "per-row flag is not a bool")
    sit_refuses(sitting(standing=False, record_sha16="0" * 16),
                "altered after it was written", "record hash does not recompute")
    sit_refuses(sitting(rows={}, standing=False),
                "by vacuity", "record covers no rows")
    sit_refuses(sitting(standing=True, lift="   "),
                "names nothing that would lift it", "withheld with no way out")

    # ------------------------------------------------- (l-n) the glyph abstention, item 4
    # Hebrew tiles, so none of this reaches the cases above: every row there shows Latin placeholders.
    VAV, NUNF, BET, DALET = u"\u05d5", u"\u05df", u"\u05d1", u"\u05d3"

    def doubt_row(note, chose=VAV):
        return dict(cur1, span_id="p628:n2", note=note,
                    tiles=[{"i": 0, "kind": "consonant", "shown": BET, "verdict": "confirmed",
                            "chose": ""},
                           {"i": 1, "kind": "consonant", "shown": NUNF, "verdict": "corrected",
                            "chose": chose}])

    def adm_doubt(note, adjs=None, chose=VAV):
        r = doubt_row(note, chose)
        rep2 = diff_resigned([r], [r], "ABST16", "PRI16")
        try:
            return admit_resigned(r, rep2, adjs or {}, None)
        except ResignDiffError as e:
            return "REFUSED: %s" % e

    # (l) the real row: the note abstains, tile 1 presents one of the two letters, nobody decided
    got = adm_doubt("could be vav or nun")
    check(isinstance(got, str) and "the signer's note abstains between vav/nun" in got
          and "'could be vav or nun'" in got and "no keep/take/neither verdict" in got,
          "an abstained glyph was admitted, or refused without its stated reason: %r" % got)

    # (m) a human decides the tile the signer could not: admitted, and the doubt stays on the row
    got = adm_doubt("could be vav or nun", {("p628:n2", "glyph_abstention", 1): "take"})
    check(isinstance(got, dict) and (got.get("glyph_abstention") or {}).get("verdict")
          == "abstain_glyph_doubt"
          and (got.get("glyph_abstention") or {}).get("adjudicated") == {"1": "take"}
          and got["glyph_abstention"]["reason"] == "could be vav or nun",
          "an adjudicated abstention did not admit, or dropped the record: %r" % got)

    # (n) THE DISCRIMINATING CASE, inside the real door: doubt about letters this row does not
    # present is not a contradiction of this row, and must not hold it. Without this, every note
    # with a hedge and two letter names in it would become a veto over any row.
    got = adm_doubt("could be dalet or resh")
    check(isinstance(got, dict) and "glyph_abstention" not in got,
          "doubt about dalet/resh held a row presenting neither: %r" % got)

    check(CHECKS + 1 == EXPECTED_CHECKS_RESIGN, "ran %d checks before the final count, expected %d"
          % (CHECKS + 1, EXPECTED_CHECKS_RESIGN))
    print("resign-diff refusal selftest: PASS %d/%d  (no data file read, nothing written)"
          % (CHECKS, EXPECTED_CHECKS_RESIGN))


if len(sys.argv) > 1 and sys.argv[1] == "--resign-selftest":
    resign_selftest()
    sys.exit(0)


if len(sys.argv) > 1 and sys.argv[1] == "--resign-diff":
    # --resign-diff <current> <prior> [report_out] [--basis <channel_basis.json>]
    _argv = list(sys.argv)
    _basis = None
    if "--basis" in _argv:
        _bi = _argv.index("--basis")
        _basis = json.load(io.open(_argv[_bi + 1], encoding="utf-8"))
        del _argv[_bi:_bi + 2]
    _only = None
    if "--only" in _argv:
        _oi = _argv.index("--only")
        _only = [s for s in _argv[_oi + 1].split(",") if s.strip()]
        del _argv[_oi:_oi + 2]
    _cur, _pri = _argv[2], _argv[3]
    try:
        _crows = [json.loads(l) for l in io.open(_cur, encoding="utf-8") if l.strip()]
        if _only is not None:
            # A span named but not present is a REFUSAL, never a quietly smaller run: the whole point
            # of naming the population is that the report's denominator is the one that was asked for.
            _have = set(r.get("span_id") for r in _crows)
            _absent = [s for s in _only if s not in _have]
            if _absent:
                raise ResignDiffError("--only names %s, which %s does not contain"
                                      % (", ".join(_absent), os.path.basename(_cur)))
            _crows = [r for r in _crows if r["span_id"] in set(_only)]
        _rep = diff_resigned(_crows,
                             [json.loads(l) for l in io.open(_pri, encoding="utf-8") if l.strip()],
                             _rs_file_sha16(_cur), _rs_file_sha16(_pri), _basis)
        if _only is not None:
            _rep["population"] = {
                "named_on_the_command_line": sorted(_only),
                "rows_in_the_current_file": len(_have),
                "why": "the current file holds more rows than this diff covers; the rest have a "
                       "different latest prior and are not scored here"}
    except ResignDiffError as _e:
        # A refusal is an ANSWER, not a crash: a traceback buries it under a stack. No report is
        # written either -- a build that refuses must leave nothing behind, and `admit_resigned`
        # admits nothing without one.
        print("REFUSED: %s" % _e)
        print("no report written; no row is admitted without one")
        sys.exit(2)
    print(format_resign_diff(_rep))
    if len(_argv) > 4:
        # The report path comes off the COMMAND LINE, so this is the one write in this file
        # whose destination a typo picks. Refused outside Lane B's two roots, before the bytes.
        io.open(assert_inside(_argv[4], "a diff report belongs in the audits directory"),
                "w", encoding="utf-8").write(json.dumps(_rep, indent=1, ensure_ascii=True))
    sys.exit(0)


# ---------------------------------------------------------------- round 2 of the pass-3 console (--round2)
# python ingest_pass2.py --round2 <r2_export.jsonl> <r1_export.jsonl> <pass1_ingest.json>
#
# ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).
#
# The three rows pass 2 held as `contradicted_prose_vs_structure`, re-signed over byte-identical pixels. Their
# two channels now agree (every row has not-in-crop tiles AND prose saying so), so each is
# `signed_partial_in_crop`: truth holds over the IN-CROP SUBSTRING only. The `fault` flag is a statement about
# the BOX; the tile marks are a statement about which LETTERS the pixels support. A faulted box whose cut the
# signer delimited precisely still gives a valid partial signature, so the fault does not hold the row out of
# truth -- it TRAVELS with it as `box_fault`, named in `signed_from`, so nobody scores against a span whose
# box needs redrawing without knowing it.
#
# What the in-crop signature is: the console's derived string with every `[...]` (not-in-crop) removed, then
# LEADING AND TRAILING separator output stripped (a word gap with nothing beyond it is a boundary artifact,
# not a signed letter). The trim is recorded per row in `in_crop_trimmed`, never silent, and an INTERIOR
# separator is never touched. A `sic` tile prints the PRINTED form into the signature; the signer's
# `expected` form, `reason` and `basis` ride beside it as separate fields (`sic`), never inside it.
#
# The prior state for the re-signing diff is what the signer was SHOWN: each tile's and insertion's own
# `prior_verdict` / `prior_chose`. Pixels (crop_sha16, candidate_sha16) can only come from the earlier export,
# so the round-1 export is read for those two hashes alone and the gate compares them as it always does.
#
# WHAT THIS DOES NOT SOLVE. No scorer: it only guarantees that `printed`/`expected`/`reason`/`basis` exist and
# survive. A partly-corrected signature is a signed reading, not a pure pixel signature; the counts say how
# much. A box fault stays an open fault: the span's box still needs redrawing before a full-span claim.
# The ruling on the one disagreement is DERIVED (no click by Chris) and says so.

R2_SET_N = 3
R2_EXPECT_ROWS = ("p493:n3", "p594:n0", "p803:n0")
R2_EXPECT_SIG = {"p493:n3": "חסיר", "p594:n0": "בהרשת",
                 "p803:n0": "נים נתונים"}
R2_EXPECT_DIFF = {("p594:n0", "tile", 1)}
R2_AUTHORITY = "DERIVED — the sole change in round 2, a sic placed deliberately; no prior reading discarded"
EXPECTED_CHECKS_R2 = 41                   # file-level and diff checks, then per-row and sic checks, plus the final count check
R2_VERDICTS = ("confirmed", "corrected", "sic")


def r2_tile_out(t):
    v, gap = t.get("verdict") or "", t["kind"] == "gap"
    if v == "deleted":
        return ""
    if v == "not_in_crop":
        return "[ ]" if gap else "[" + t["shown"] + "]"
    if v == "confirmed":
        return " " if gap else t["shown"]
    if v == "sic":
        return t["shown"]                      # the PRINTED form; `expected` never enters the string
    if v == "corrected":
        if gap:
            return " " if t.get("chose") == "space" else ""
        return t.get("chose") or "?"
    return "?"


def r2_ins_out(it):
    if it.get("verdict") == "not_in_crop":
        return "[ ]" if it["kind"] == "gap" else "[" + (it.get("chose") or "") + "]"
    if not it.get("chose"):
        return "?"
    return " " if it["kind"] == "gap" else it["chose"]


def r2_derive(r):
    out = [r2_ins_out(x) for x in sorted((x for x in r["insertions"] if x["after_i"] is None),
                                         key=lambda x: x["seq"])]
    for t in r["tiles"]:
        out.append(r2_tile_out(t))
        out.extend(r2_ins_out(x) for x in sorted((x for x in r["insertions"] if x["after_i"] == t["i"]),
                                                 key=lambda x: x["seq"]))
    return "".join(out)


def r2_prior_rows(cur_rows, r1_rows):
    """The prior state the signer was SHOWN, rebuilt from each item's own prior_* fields. Pixel hashes are
    taken from the round-1 export row (the only place they exist) so the gate's identity check is real."""
    r1 = {r["span_id"]: r for r in r1_rows}
    out = []
    for r in cur_rows:
        check(r["span_id"] in r1, "%s has no round-1 row to take its pixel hashes from" % r["span_id"])
        check(all("prior_verdict" in t for t in r["tiles"]) and all("prior_verdict" in x for x in r["insertions"]),
              "%s: an item has no prior_verdict, so the shown state cannot be rebuilt" % r["span_id"])
        out.append({"span_id": r["span_id"], "crop_sha16": r1[r["span_id"]]["crop_sha16"],
                    "candidate_sha16": r1[r["span_id"]]["candidate_sha16"],
                    "tiles": [{"i": t["i"], "kind": t["kind"], "shown": t["shown"],
                               "verdict": t["prior_verdict"], "chose": t.get("prior_chose") or ""}
                              for t in r["tiles"]],
                    "insertions": [{"seq": x["seq"], "after_i": x["after_i"], "kind": x["kind"],
                                    "chose": x.get("prior_chose") or "", "verdict": x["prior_verdict"]}
                                   for x in r["insertions"]]})
    return out


def r2_ruling(d):
    """DERIVED rulings only, and only for the one shape this round is known to hold: a tile the signer
    moved confirmed -> sic over the same printed glyph. Anything else gets no ruling, so admission refuses."""
    if (d["what"] == "tile" and d["prior"]["verdict"] == "confirmed" and d["current"]["verdict"] == "sic"
            and d["prior"]["shown"] == d["current"]["shown"] and not d["reversal_corrected_to_confirmed"]):
        return "take"
    return None


def r2_git_raw(where):
    import subprocess
    st = subprocess.run(["git", "-C", where, "status", "--porcelain"], capture_output=True, text=True,
                        encoding="utf-8").stdout.splitlines()
    hd = subprocess.run(["git", "-C", where, "rev-parse", "HEAD"], capture_output=True, text=True,
                        encoding="utf-8").stdout.strip()
    return {"head": hd, "porcelain": st}


def jl_r2(path, recs):
    io.open(str(path), "w", encoding="utf-8", newline="\n").write(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in recs))


def round2(r2_path, r1_path, pass1_path):
    git_raw_start = {k: r2_git_raw(v) for k, v in REPOS.items()}
    cur = [json.loads(l) for l in io.open(r2_path, encoding="utf-8") if l.strip()]
    r1 = [json.loads(l) for l in io.open(r1_path, encoding="utf-8") if l.strip()]
    pass1 = json.load(io.open(pass1_path, encoding="utf-8"))
    r2_sha, r1_sha = _rs_file_sha16(r2_path), _rs_file_sha16(r1_path)
    check(len(cur) == R2_SET_N and tuple(sorted(r["span_id"] for r in cur)) == R2_EXPECT_ROWS,
          "the round-2 export holds %s, expected %s" % ([r["span_id"] for r in cur], list(R2_EXPECT_ROWS)))
    check(all(r.get("set_sha16") == SET for r in cur), "a round-2 row carries a different set_sha16")
    check(len(pass1["rows"]) > 0 and pass1.get("set_sha16") == SET, "pass 1 ingest is empty or from another set")

    # held and truth rows of pass 2, read from the files (not literals)
    held2 = [json.loads(l) for l in io.open(str(HAD.DATA / "held_pass2.jsonl"), encoding="utf-8") if l.strip()]
    truth2 = [json.loads(l) for l in io.open(str(HAD.DATA / "truth_pass2.jsonl"), encoding="utf-8") if l.strip()]
    held2_ids = [h["span_id"] for h in held2]
    check(all(r["span_id"] in held2_ids for r in cur),
          "a round-2 span is not among pass 2's held rows %s" % held2_ids)

    # the diff gate, over the shown state
    prior_rows = r2_prior_rows(cur, r1)
    prior_sha = sha16(json.dumps(prior_rows, sort_keys=True, ensure_ascii=True))
    rep = diff_resigned(cur, prior_rows, r2_sha, prior_sha)
    got_diff = set((d["span_id"], d["what"], d["i"] if d["what"] == "tile" else d["seq"])
                   for d in rep["disagreements"])
    check(got_diff == R2_EXPECT_DIFF, "disagreements differ: only-computed %s, only-expected %s"
          % (sorted(got_diff - R2_EXPECT_DIFF), sorted(R2_EXPECT_DIFF - got_diff)))
    check(rep["rate"]["insertions_changed"] == 0 and rep["rate"]["reversals_corrected_to_confirmed"] == 0,
          "round 2 changed an insertion or reversed a correction: %s" % rep["rate"])

    # the content-addressed adjudication file
    rulings = []
    for d in rep["disagreements"]:
        v = r2_ruling(d)
        if v is None:
            continue
        rulings.append({"span_id": d["span_id"], "what": d["what"], "tile_i": d["i"], "verdict": v,
                        "authority": R2_AUTHORITY,
                        "basis": "Not clicked by Chris. The signer moved this tile from confirmed to sic over "
                                 "byte-identical pixels this round: an ADDITION (the printed form stays in the "
                                 "signature, the expectation is recorded beside it), not a reversal of any "
                                 "prior reading. The current reading is taken as it stands. DERIVED, not "
                                 "quoted: Chris may reject it.",
                        "prior": d["prior"], "current": d["current"]})
    adj = {"kind": "resign_adjudication",
           "note": "ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88). Rulings on the disagreements the "
                   "re-signing diff found between the pass-3 round-2 export (current) and the state the signer "
                   "was SHOWN (the export's own prior_verdict/prior_chose fields), over byte-identical pixels. "
                   "keep = prior reading, take = current reading, neither = leave unanswered. The one ruling "
                   "is DERIVED and labelled so.",
           "set_sha16": SET, "diff_sha16": rep["diff_sha16"],
           "current_file": os.path.basename(r2_path), "current_file_sha16": r2_sha,
           "prior_file": "reconstructed from the round-2 export's own prior_verdict/prior_chose fields; pixel "
                         "hashes from " + os.path.basename(r1_path),
           "prior_file_sha16": prior_sha, "round1_export_sha16": r1_sha, "rulings": rulings}
    adj_bytes = json.dumps(adj, indent=1, ensure_ascii=True).encode("utf-8")
    adj_sha = hashlib.sha256(adj_bytes).hexdigest()[:16]
    adj_path = HAD.DATA / ("ADJUDICATION_pass3_r2_%s.json" % adj_sha)
    if not adj_path.exists():
        io.open(str(adj_path), "wb").write(adj_bytes)
    check(io.open(str(adj_path), "rb").read() == adj_bytes, "%s holds different bytes" % adj_path.name)
    check(_rs_file_sha16(adj_path) == adj_sha and adj_sha in adj_path.name,
          "the adjudication file is not named by its own sha16")
    loaded = json.load(io.open(str(adj_path), encoding="utf-8"))
    check(loaded["diff_sha16"] == rep["diff_sha16"], "the adjudication file is for a different diff")
    adjudications = {(x["span_id"], x["what"], x["tile_i"] if x["what"] == "tile" else x["seq"]): x["verdict"]
                     for x in loaded["rulings"]}
    check(set(adjudications) == R2_EXPECT_DIFF and all(x["authority"].startswith("DERIVED") for x in loaded["rulings"]),
          "the adjudication file does not cover exactly the one disagreement, or a ruling is not marked DERIVED")

    # the refusal, demonstrated: without the ruling the door shuts
    refusal = ""
    try:
        admit_resigned([r for r in cur if r["span_id"] == "p594:n0"][0], rep, {})
    except ResignDiffError as e:
        refusal = str(e)
    check("no keep/take/neither verdict" in refusal, "admission did not refuse without the ruling: %r" % refusal)

    truth_rows, held_rows = [], []
    for r in cur:
        s = r["span_id"]
        derived = r2_derive(r)
        check(derived == r["derived_consonants"], "%s: port gives %r, console said %r"
              % (s, derived, r["derived_consonants"]))
        note = (r.get("note") or "").strip()
        n_nic = (sum(1 for t in r["tiles"] if t.get("verdict") == "not_in_crop")
                 + sum(1 for x in r["insertions"] if x.get("verdict") == "not_in_crop"))
        prose = RULE.prose_says_unsignable(note)
        check(r.get("complete") and n_nic > 0 and prose, "%s: not complete with not-in-crop tiles that the prose "
              "agrees with (complete %s, n_nic %d, prose %s)" % (s, r.get("complete"), n_nic, prose))
        disp = "signed_partial_in_crop"
        raw = re.sub(r"\[[^\]]*\]", "", derived)
        sig = raw.strip(" ")
        lead, trail = len(raw) - len(raw.lstrip(" ")), len(raw) - len(raw.rstrip(" "))
        trimmed = ("leading and trailing separator" if lead and trail else
                   "leading separator" if lead else "trailing separator" if trail else "")
        check(sig == R2_EXPECT_SIG[s], "%s: in-crop signature %r, expected %r" % (s, sig, R2_EXPECT_SIG[s]))
        in_tiles = [t for t in r["tiles"] if t["kind"] == "consonant" and t.get("verdict") in R2_VERDICTS]
        n_conf = sum(1 for t in in_tiles if t["verdict"] == "confirmed")
        n_corr = sum(1 for t in in_tiles if t["verdict"] == "corrected")
        n_sic = sum(1 for t in in_tiles if t["verdict"] == "sic")
        n_ins_in = sum(1 for x in r["insertions"] if x.get("verdict") != "not_in_crop" and x["kind"] == "consonant")
        check(n_conf + n_corr + n_sic + n_ins_in == len(sig.replace(" ", "")),
              "%s: %d+%d+%d+%d in-crop letters counted, signature has %d" % (
                  s, n_conf, n_corr, n_sic, n_ins_in, len(sig.replace(" ", ""))))
        sics = []
        for t in in_tiles:
            if t["verdict"] == "sic":
                check(t.get("expected") and t.get("reason") and t.get("basis"),
                      "%s tile %d: a sic with no expected/reason/basis" % (s, t["i"]))
                check(t["shown"] in sig and t["expected"] not in sig,
                      "%s tile %d: the signature must hold the printed %r and not the expected %r"
                      % (s, t["i"], t["shown"], t["expected"]))
                sics.append({"tile_i": t["i"], "printed": t["shown"], "expected": t["expected"],
                             "reason": t["reason"], "basis": t["basis"]})
        sf = ("pixels, %d confirmed + %d corrected + %d sic letter(s)%s, in-crop only; box_fault %s "
              "(the box needs redrawing; this signature holds over the in-crop substring only)"
              % (n_conf, n_corr, n_sic, (", + %d signer insertion(s)" % n_ins_in) if n_ins_in else "",
                 r.get("fault") or "none"))
        check(not r.get("full_span_pixel_signature"), "%s: full_span_pixel_signature must be False" % s)
        pts = r.get("points_shown_not_adjudicated") or {}
        row = {"span_id": s, "disposition": disp, "signature": sig, "signature_full": derived,
               "full_span_pixel_signature": False,
               "full_span_pixel_signature_console": bool(r.get("full_span_pixel_signature")),
               "signed_from": sf, "box_fault": r.get("fault") or "",
               "in_crop_trimmed": trimmed, "n_confirmed": n_conf, "n_corrected": n_corr, "n_sic": n_sic,
               "sic": sics, "crop_sha16": r.get("crop_sha16"), "candidate_sha16": r.get("candidate_sha16"),
               "n_points": pts.get("n_points"), "nikud_flag": pts.get("nikud_flag"), "pass": 3, "round": 2}
        try:
            adm = admit_resigned(r, rep, adjudications)
            row["resign_diff_sha16"] = adm["resign_diff_sha16"]
            truth_rows.append(row)
        except ResignDiffError as e:
            held_rows.append({"span_id": s, "disposition": disp, "note": note,
                              "why_held": "the re-signing diff channel objected: %s" % e})
    check(len(truth_rows) == R2_SET_N and not held_rows, "admitted %d of %d; held %s" % (
        len(truth_rows), R2_SET_N, [h["span_id"] for h in held_rows]))
    check(all(t["disposition"] == "signed_partial_in_crop" and t["resign_diff_sha16"] == rep["diff_sha16"]
              for t in truth_rows), "an admitted row is not signed_partial_in_crop through the diff")
    trimmed_rows = [t["span_id"] for t in truth_rows if t["in_crop_trimmed"]]

    # combined total, derived from the files
    p1_truth = [x["span_id"] for x in pass1["rows"] if x["disposition"] in PASS1_TRUTH_DISPOS]
    p2_truth = [t["span_id"] for t in truth2]
    r2_truth = [t["span_id"] for t in truth_rows]
    check(len(set(p1_truth) | set(p2_truth) | set(r2_truth)) == len(p1_truth) + len(p2_truth) + len(r2_truth),
          "a span is in truth in more than one pass")
    total = len(p1_truth) + len(p2_truth) + len(r2_truth)
    line = "TRUTH TOTAL: %d (pass 1 %d + pass 2 %d + pass 3 r2 %d)" % (total, len(p1_truth), len(p2_truth),
                                                                      len(r2_truth))
    still_held = [h for h in held2 if h["span_id"] not in r2_truth]
    check(len(still_held) == len(held2) - len(r2_truth), "held count does not follow from the files")

    # write truth/held, then read back: the sic fields must survive
    out_t, out_h = HAD.DATA / "truth_pass3_r2.jsonl", HAD.DATA / "held_pass3_r2.jsonl"
    jl_r2(out_t, truth_rows)
    if held_rows:
        jl_r2(out_h, held_rows)
    back = [json.loads(l) for l in io.open(str(out_t), encoding="utf-8") if l.strip()]
    sic_back = [t for t in back if t["sic"]]
    check(len(sic_back) == 1 and sic_back[0]["span_id"] == "p594:n0"
          and sic_back[0]["sic"][0]["printed"] == "ה" and sic_back[0]["sic"][0]["expected"] == "ח"
          and sic_back[0]["sic"][0]["reason"] == "Exod 31:5 / fabrefactione"
          and sic_back[0]["sic"][0]["basis"] == "evidence_grounded"
          and "ה" in sic_back[0]["signature"] and "ח" not in sic_back[0]["signature"],
          "the sic fields did not round-trip through the truth file")
    check(all(b["box_fault"] == "box-edge-cut" and "box_fault box-edge-cut" in b["signed_from"] for b in back),
          "box_fault does not travel with every truth row")
    check(CHECKS + 1 == EXPECTED_CHECKS_R2, "ran %d checks before the final count, expected %d"
          % (CHECKS + 1, EXPECTED_CHECKS_R2))

    git_raw_end = {k: r2_git_raw(v) for k, v in REPOS.items()}
    gend = states()
    prov_r2 = (prov(GIT_START, gend) or any(git_raw_start[k] != git_raw_end[k] for k in REPOS)
               or any(git_raw_start[k]["porcelain"] for k in REPOS))
    report = HAD.DATA / ("INGEST_pass3_r2_%s.md" % r2_sha)
    L = ["# Ingest of pass-3 round 2 (%d spans)%s" % (R2_SET_N, "  -- PROVISIONAL" if prov_r2 else ""), "",
         "ALL PAGE NUMBERS ARE FILE PAGES (printed = file - %d)." % PRINTED_OFFSET, "",
         "- round-2 export: `%s` (sha16 %s)" % (os.path.basename(r2_path), r2_sha),
         "- round-1 export (pixel hashes only): `%s` (sha16 %s)" % (os.path.basename(r1_path), r1_sha),
         "- prior state: reconstructed from the export's own prior_verdict/prior_chose (sha16 %s)" % prior_sha,
         "- diff_sha16 %s; adjudication `%s` (content sha16 %s; DERIVED)" % (rep["diff_sha16"], adj_path.name, adj_sha),
         "- checks run: %d (expected %d)" % (CHECKS, EXPECTED_CHECKS_R2),
         "- run: %s" % ("PROVISIONAL (not citable)" if prov_r2 else "clean"), ""]
    for k in REPOS:
        L.append("- git %s: start head %s, %d porcelain line(s) -> end head %s, %d porcelain line(s)" % (
            k, git_raw_start[k]["head"][:7], len(git_raw_start[k]["porcelain"]),
            git_raw_end[k]["head"][:7], len(git_raw_end[k]["porcelain"])))
        L.append("  - start porcelain: %s" % ("; ".join(git_raw_start[k]["porcelain"]) or "(clean)"))
        L.append("  - end porcelain: %s" % ("; ".join(git_raw_end[k]["porcelain"]) or "(clean)"))
    L += ["", "## %s" % line, "",
          "Pass 1 from `%s` rows in %s; pass 2 = lines of `truth_pass2.jsonl`; pass 3 r2 = rows admitted here. "
          "Read from files, not literals." % (os.path.basename(pass1_path), list(PASS1_TRUTH_DISPOS)), "",
          "## Admitted (%d), held (%d)" % (len(truth_rows), len(held_rows)), ""]
    for t in truth_rows:
        L.append("- %s `%s` signature len %d, trimmed: %s; box_fault %s; letters %d confirmed + %d corrected + "
                 "%d sic; from: %s" % (t["span_id"], t["disposition"], len(t["signature"]),
                                       t["in_crop_trimmed"] or "none", t["box_fault"], t["n_confirmed"],
                                       t["n_corrected"], t["n_sic"], t["signed_from"]))
    L += ["", "Separator trims: %d row(s) %s." % (len(trimmed_rows), trimmed_rows), "",
          "## Pass 2's %d held rows: %d remain held" % (len(held2), len(still_held)), ""]
    for h in still_held:
        L.append("- %s `%s`" % (h["span_id"], h["disposition"]))
    L += ["", "## Refusal without the ruling", "", "`%s`" % refusal, "",
          "## What this does NOT solve", "",
          "- The three signatures hold over the in-crop substring only; the box of each still needs redrawing.",
          "- A partly-corrected signature is a signed reading, not a pure pixel signature (counts above).",
          "- The sic ruling is DERIVED, not clicked; no scorer reads `printed`/`expected` yet.",
          "- Held box-fault and abstain rows are untouched."]
    io.open(str(report), "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")

    print("round 2 ingest of %s (%d rows)%s" % (os.path.basename(r2_path), len(cur), "  PROVISIONAL" if prov_r2 else ""))
    print("  admitted %d via admit_resigned, held %d; disagreements %s; diff_sha16 %s" % (
        len(truth_rows), len(held_rows), sorted(got_diff), rep["diff_sha16"]))
    print("  adjudication %s; refusal without it: %s" % (adj_path.name, "yes" if refusal else "NO"))
    for t in truth_rows:
        print("  %s %s len %d trimmed=%s letters %d/%d/%d (conf/corr/sic) box_fault=%s" % (
            t["span_id"], t["disposition"], len(t["signature"]), t["in_crop_trimmed"] or "none",
            t["n_confirmed"], t["n_corrected"], t["n_sic"], t["box_fault"]))
    print("  " + line)
    print("  pass 2 held %d, remain held %d: %s" % (len(held2), len(still_held),
                                                    " ".join(h["span_id"] for h in still_held)))
    print("  trims %d, checks run %d, expected %d" % (len(trimmed_rows), CHECKS, EXPECTED_CHECKS_R2))
    print("  git: %s" % ("PROVISIONAL" if prov_r2 else "clean run"))
    print("  wrote %s, %s%s" % (out_t.name, report.name, (", " + out_h.name) if held_rows else ""))


if len(sys.argv) > 1 and sys.argv[1] == "--round2":
    round2(sys.argv[2], sys.argv[3], sys.argv[4])
    sys.exit(0)


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
    # SECOND-LOOK MARKER ONLY (signature_attestation.py): never read by disposition_pass2, never blocks a row,
    # never feeds a score. None = not applicable (no in-crop signature).
    f["signature_attestation"] = SA.attest(r)
    f["signature_unattested"] = f["signature_attestation"]["signature_unattested"]
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

check(all(f["signature_attestation"]["derived_in_crop"] == f["signature_in_crop"] for f in F.values()),
      "signature_attestation derives a different in-crop string from this file's own port of derivedFor")
check(all("signature_unattested" in f for f in F.values()) and len(F) == SET_N,
      "a row has no signature_unattested fact")
N_ATT_APP = sum(1 for f in F.values() if f["signature_attestation"]["applicable"])
N_UNATT = sum(1 for f in F.values() if f["signature_unattested"])

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
            "n_points": pts.get("n_points"), "nikud_flag": pts.get("nikud_flag"), "pass": 2,
            "signature_unattested": f["signature_unattested"]})
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
L.append("| span | disposition | nic | del | corr | conf | empty | ins | prose_unsig | fsps console/recomputed "
         "| unattested |")
L.append("|---|---|---|---|---|---|---|---|---|---|---|")
for s in sorted(F):
    f = F[s]
    L.append("| %s | %s | %d | %d | %d | %d | %d | %d | %s | %s/%s | %s |" % (
        s, DISPO[s], f["n_nic"], f["n_deleted"], f["n_corrected"], f["n_confirmed"], f["n_empty"],
        f["n_insertions"], f["prose_says_unsignable"], f["full_span_pixel_signature_console"],
        f["full_span_pixel_signature"], {True: "UNATTESTED", False: "attested", None: "n/a"}[f["signature_unattested"]]))
L.append("")
L.append("## signature_unattested (second-look marker only): %d of %d rows (%d applicable)"
         % (N_UNATT, SET_N, N_ATT_APP))
L.append("")
L.append("A row's in-crop derived string is unattested when no channel produced it and the note does not hold it. "
         "Channels in the export: the candidate only, so the flag reduces to 'differs from the candidate on the "
         "in-crop tiles'. It never holds a row, never chooses a reading, never feeds a score "
         "(signature_attestation.py).")
L.append("")
L.append("## What this does NOT solve")
L.append("")
L.append("- `signature_unattested` cannot tell a right correction from a wrong one, so it does not discriminate "
         "the p493:n3 reversal (both the pass-2 and the pass-3 strings are unattested).")
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
print("  signature_unattested (second-look marker only): %d of %d rows, %d applicable" % (N_UNATT, SET_N, N_ATT_APP))
print("  checks run %d, expected %d" % (CHECKS, EXPECTED_CHECKS))
print("  git: %s" % ("PROVISIONAL" if PROV else "clean run"))
print("  wrote %s, %s, %s" % (TRUTH_OUT.name, HELD_OUT.name, REPORT.name))
