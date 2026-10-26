# -*- coding: utf-8 -*-
u"""Ruling 2 (2026-10-25): the headline restated under the adjudication overlay.

*"Restate the headline under the overlay, as a table with n: Opus bare on 45 -> exact /
crop-refused (guard should have refused: p493:n3, p326:n11, p428:n0, p622:n0, p831:n2 and the 2-band
rows) / signature-error (Opus right) / reader / unsettled. Same for Qwen. Do not edit run 501ab577;
this is a derived view citing the overlay."*

A DERIVED VIEW.  It writes a new record and reads three committed ones; it modifies nothing:

  SCORE45_501ab577a18a6785.json       the run's score per (span, arm) -- exact or wrong
  CLASSIFY45_501ab577a18a6785.json    the run's 31 assignments, family crop / reader / withheld
  ADJUDICATION_classify45_20261025_*  Chris's audit, which RE-TYPES 7 of the reader rows as crop

Every row's bucket is derived by a stated rule from those three, in one place (`bucket()`), so a
reader can check the rule rather than the tally.  Nothing is typed in from the ruling: the ruling's
own list of crop rows is checked AGAINST the data, and where it disagrees the disagreement is
reported rather than reconciled silently.

All page numbers are FILE pages (printed = file - 88).
"""
import glob
import hashlib
import io
import json
import os
import sys

import hebrew_aperture_diag as diag

DATA = str(diag.DATA)
SCORE45 = "SCORE45_501ab577a18a6785.json"
CLASSIFY45 = "CLASSIFY45_501ab577a18a6785.json"

#: The arm each ruling-2 column is about.  `bare` only: the ruling says "Opus bare" and "same for
#: Qwen", and the context arms are a separate comparison that this table is not about.
ARMS = [("opus", "anthropic/claude-opus-5.5|bare"), ("qwen", "qwen/qwen3.7-plus|bare")]

#: The buckets, in the order the ruling names them.  `not_adjudicated` is not in the ruling and is
#: added because two rows have no verdict: folding them into `reader` would turn "nobody looked" into
#: "the model misread", which is the whole failure this overlay exists to undo.
BUCKETS = ("exact", "crop_refused", "signature_error_model_right",
           "signature_error_model_not_ruled", "reader", "unsettled", "not_adjudicated")


def overlay_path():
    hits = sorted(glob.glob(os.path.join(DATA, "ADJUDICATION_classify45_20261025_*.json")))
    if len(hits) != 1:
        raise IOError("expected exactly one adjudication overlay in %s, found %d: %s"
                      % (DATA, len(hits), [os.path.basename(h) for h in hits]))
    return hits[0]


def load():
    s = json.load(io.open(os.path.join(DATA, SCORE45), encoding="utf-8"))
    c = json.load(io.open(os.path.join(DATA, CLASSIFY45), encoding="utf-8"))
    op = overlay_path()
    o = json.load(io.open(op, encoding="utf-8"))
    return s, c, o, os.path.basename(op)


def bucket(span, arm, score_class, assignment, verdict):
    u"""The one place a row's bucket is decided.  Returns (bucket, why).

    Order matters and is the content of the rule:

      1. The run scored it exact -> `exact`.  No adjudication touched an exact row.
      2. The overlay re-typed it -> the overlay WINS over the run's family.  That is what an
         adjudication is for; a crop fault the run blamed on the reader is still a crop fault.
      3. No overlay verdict -> the run's own family stands.
    """
    if score_class == "exact":
        return "exact", "run scored exact"
    if verdict is not None:
        v = verdict["verdict"]
        if v == "crop_edge_cut":
            return "crop_refused", "audit re-typed from run family %r" % assignment["class_family"]
        if v == "signature":
            if verdict.get("model_was_right") is True:
                return "signature_error_model_right", "audit: signature wrong, model read it right"
            return "signature_error_model_not_ruled", \
                "audit: signature wrong; this arm's own read not separately ruled"
        if v == "signature_suspect_unsettled":
            return "unsettled", "audit refused to decide; needs: %s" % verdict.get("needs", "")
        if v == "not_adjudicated":
            if assignment["class_family"] == "crop":
                return "crop_refused", "run family crop; audit did not reach it"
            return "not_adjudicated", "audit did not reach this row"
        if v == "agreed":
            if assignment["class_family"] == "crop":
                return "crop_refused", "run family crop, audit agreed"
            return "reader", "audit agreed with the run's reader class %r" % assignment["class"]
        raise ValueError("unhandled overlay verdict %r on %s/%s" % (v, span, arm))
    fam = assignment["class_family"]
    if fam == "crop":
        return "crop_refused", "run family crop (%s); no audit verdict" % assignment["class"]
    if fam == "reader":
        return "reader", "run family reader (%s); no audit verdict" % assignment["class"]
    if fam == "withheld":
        return "unsettled", "run withheld (%s); no audit verdict" % assignment["class"]
    raise ValueError("unhandled run family %r on %s/%s" % (fam, span, arm))


def build():
    score, classify, overlay, oname = load()
    asn = dict(((r["span_id"], r["arm"]), r) for r in classify["assignments"])
    ver = dict(((r["span_id"], r["arm"]), r) for r in overlay["rows"])

    table, rows = {}, []
    for short, full in ARMS:
        counts = dict((b, 0) for b in BUCKETS)
        ids = dict((b, []) for b in BUCKETS)
        for r in score["rows"]:
            sid = r["span_id"]
            if full not in r["results"]:
                raise IOError("%s has no %s result; the table would silently shrink" % (sid, full))
            sc = r["results"][full]["class_primary"]
            a = asn.get((sid, short))
            if sc != "exact" and a is None:
                raise IOError("%s/%s scored %r but has no assignment to bucket it by"
                              % (sid, short, sc))
            b, why = bucket(sid, short, sc, a, ver.get((sid, short)))
            counts[b] += 1
            if b != "exact":
                ids[b].append(sid)
                rows.append({"span_id": sid, "arm": short, "page_file": r["page_file"],
                             "page_printed": r["page_printed"], "run_score": sc,
                             "run_family": a["class_family"], "run_class": a["class"],
                             "audit_verdict": (ver.get((sid, short)) or {}).get("verdict"),
                             "bucket": b, "why": why})
        if sum(counts.values()) != len(score["rows"]):
            raise IOError("%s buckets sum to %d, not %d" % (short, sum(counts.values()),
                                                            len(score["rows"])))
        table[short] = {"n": len(score["rows"]), "counts": counts, "ids": ids}

    # ---- the ruling's own crop list, checked against the data rather than adopted
    named = ["p493:n3", "p326:n11", "p428:n0", "p622:n0", "p831:n2"]
    blind = []
    for (sid, arm), a in sorted(asn.items()):
        v = ver.get((sid, arm))
        if v is not None and v["verdict"] == "crop_edge_cut":
            blind.append({"span_id": sid, "arm": arm, "run_family": a["class_family"],
                          "run_class": a["class"],
                          "ratified_box_fault": a["screen"].get("ratified_box_fault"),
                          "partial_in_crop": "partial_in_crop" in (a["populations"] or [])})
    guard_saw = {}
    for sid in named:
        hits = [a for (s, _), a in asn.items() if s == sid]
        if not hits:
            guard_saw[sid] = "not in the 31 assignments"
            continue
        bf = sorted(set(bool(h["screen"].get("ratified_box_fault")) for h in hits))
        pic = sorted(set("partial_in_crop" in (h["populations"] or []) for h in hits))
        fam = sorted(set(h["class_family"] for h in hits))
        guard_saw[sid] = {"ratified_box_fault": bf, "partial_in_crop": pic, "run_family": fam}

    rec = {
        "kind": "derived_headline",
        "ruling": "2 of 2026-10-25: restate the headline under the adjudication overlay",
        "derived_from": {"score": SCORE45, "classify": CLASSIFY45, "overlay": oname},
        "modifies": "nothing. This is a derived view; run 501ab577a18a6785 is untouched.",
        "page_convention": "all page numbers are FILE pages (printed = file - 88)",
        "arms": "bare only. The ruling says Opus bare and 'same for Qwen'; the context arms are a "
                "different comparison and are not in this table.",
        "bucket_rule": "Decided in headline_restate.bucket(), in this order: a row the run scored "
                       "exact is `exact`; otherwise an overlay verdict WINS over the run's family "
                       "(that is what an adjudication is for); otherwise the run's family stands. "
                       "`not_adjudicated` is kept as its own bucket because folding it into "
                       "`reader` would turn 'nobody looked' into 'the model misread'.",
        "table": table,
        "non_exact_rows": sorted(rows, key=lambda r: (r["arm"], r["span_id"])),
        "guard_blindness": {
            "what": "assignments the audit re-typed as crop_edge_cut, with the guard flags the run "
                    "recorded for them. Every one has ratified_box_fault False and partial_in_crop "
                    "False while a glyph is cut by the crop boundary.",
            "rows": blind,
            "n_assignments": len(blind),
            "n_spans": len(set(b["span_id"] for b in blind)),
        },
        "ruling_crop_list_checked": {
            "what": "ruling 2 names these as rows the guard should have refused. Checked against "
                    "the run's own recorded flags instead of adopted.",
            "named": named,
            "measured": guard_saw,
        },
    }
    rec["self_sha16"] = hashlib.sha256(json.dumps(
        rec, ensure_ascii=False, sort_keys=True, indent=1).encode("utf-8")).hexdigest()[:16]
    return rec


def check(rec):
    n, fail = [0], []

    def ck(c, m):
        n[0] += 1
        if not c:
            fail.append(m)

    for short, _ in ARMS:
        t = rec["table"][short]
        ck(sum(t["counts"].values()) == 45,
           "%s buckets sum to the full population of 45, so no row is dropped: got %d"
           % (short, sum(t["counts"].values())))
        ck(set(t["counts"]) == set(BUCKETS),
           "%s uses exactly the declared buckets, so a stray bucket cannot appear in a tally"
           % short)
        ck(all(len(t["ids"][b]) == t["counts"][b] for b in BUCKETS if b != "exact"),
           "%s: every non-exact count is backed by that many named span ids" % short)
    ck(rec["table"]["opus"]["counts"]["exact"] == 32 and rec["table"]["qwen"]["counts"]["exact"] == 27,
       "the exact counts match the run's own tally (32 opus, 27 qwen); if these moved, this view "
       "is not about run 501ab577a18a6785: got %s"
       % [rec["table"][a]["counts"]["exact"] for a, _ in ARMS])
    ck(rec["guard_blindness"]["n_assignments"] == 7
       and rec["guard_blindness"]["n_spans"] == 4,
       "the blind-guard population is 7 assignments over 4 spans: got %d over %d"
       % (rec["guard_blindness"]["n_assignments"], rec["guard_blindness"]["n_spans"]))
    ck(all(r["ratified_box_fault"] is False and r["partial_in_crop"] is False
           for r in rec["guard_blindness"]["rows"]),
       "every re-typed row really did carry BOTH flags False -- that is the claim, and if one of "
       "them was flagged the blindness story is wrong for it")
    # the ruling named p493:n3 among them; the run flagged it, so it is NOT blind
    m = rec["ruling_crop_list_checked"]["measured"]["p493:n3"]
    ck(m["ratified_box_fault"] == [True] and m["partial_in_crop"] == [True],
       "p493:n3 carries box_fault True and partial_in_crop True in the run's own record, so the "
       "guard DID flag it and it does not belong in the blind set: got %s" % m)
    ck("p493:n3" not in [r["span_id"] for r in rec["guard_blindness"]["rows"]],
       "and it is therefore absent from the blind population this record reports")
    ck(all(r["page_printed"] == r["page_file"] - 88 for r in rec["non_exact_rows"]),
       "printed = file - 88 on every row, derived not typed")
    ck(rec["modifies"].startswith("nothing"),
       "the record states on its face that it modifies nothing")
    EXPECTED = 13
    print("headline_restate: %d checks, %d failed" % (n[0], len(fail)))
    for m2 in fail:
        print("  FAIL  %s" % m2)
    if n[0] != EXPECTED:
        print("SUITE DID NOT RUN TO COMPLETION: %d checks, expected %d." % (n[0], EXPECTED))
        return 2
    return 1 if fail else 0


def main():
    rec = build()
    rc = check(rec)
    if rc:
        return rc
    name = "HEADLINE_RESTATED_20261025_%s.json" % rec["self_sha16"]
    p = os.path.join(DATA, name)
    staged = p + ".staging"
    body = json.dumps(rec, ensure_ascii=False, sort_keys=True, indent=1)
    with io.open(staged, "w", encoding="utf-8", newline="") as fh:
        fh.write(body)
    try:
        back = json.loads(io.open(staged, encoding="utf-8").read())
        claimed = back.pop("self_sha16")
        recomputed = hashlib.sha256(json.dumps(
            back, ensure_ascii=False, sort_keys=True, indent=1).encode("utf-8")).hexdigest()[:16]
        if recomputed != claimed:
            raise IOError("does not round-trip its hash rule (%s vs %s)" % (recomputed, claimed))
    except Exception:
        os.remove(staged)
        raise
    if os.path.exists(p):
        os.remove(p)
    os.rename(staged, p)

    print("")
    hdr = "%-34s %s" % ("bucket", "  ".join("%6s" % a for a, _ in ARMS))
    print(hdr)
    print("-" * len(hdr))
    for b in BUCKETS:
        print("%-34s %s" % (b, "  ".join("%6d" % rec["table"][a]["counts"][b] for a, _ in ARMS)))
    print("-" * len(hdr))
    print("%-34s %s" % ("total", "  ".join("%6d" % rec["table"][a]["n"] for a, _ in ARMS)))
    print("")
    print("wrote %s" % p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
