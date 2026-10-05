"""Re-score recorded eval answers under the fixed quote/citation pairing regex.

No model is called. Every input is already on disk, so this is a re-scoring of
runs that already happened, not a new attempt at the 5x13 pair.

WHAT THIS CAN AND CANNOT DO -- read before quoting a number from it.

1. ONLY THE REPRESENTATIVE RUN IS RE-SCORABLE. `run_eval.py:1729` writes the last
   scored run's `response` and `score` in full and keeps the other runs as a thin
   ledger: `answer_sha16`, `answer_chars`, `pass`, `elapsed_s`, and a BOOLEAN
   `verification_failure` (a stage flag, not the failure list). There is no answer
   text for runs 1..n-1 anywhere on disk, so the fix cannot be applied to them.
   A corrected per-question RUN COUNT -- which is what the run-level pass rate and
   any paired per-question test need -- is therefore NOT obtainable from disk. It
   needs a run whose harness records `verified` and the answer per run.

2. The recorded `score.answer` is POST-repair: `_repair_quotes_in_answer` may have
   already substituted a verbatim span for a near-miss quote before the text was
   written out. Re-running the verifier over it is therefore not bit-identical to
   re-running the live request. For the `no_gill_quote_for_citation` class this is
   conservative -- a repair only ever makes a quote closer to the source -- but a
   `quote_not_verbatim` count taken from here is not trustworthy.

3. KJV text is NOT reconstructed. `_build_chunks_by_sid` fills the "kjv" side from
   `KJV_DATA`, which is not loaded here, so this probe decides the GILL obligation
   only. That is the gate that moved; a KJV-provenance question cannot be answered
   from this output.

4. The resolution rule is stated, not inferred, and it has THREE clauses: a
   recorded unverified SID counts as RESOLVED only if (a) it did NOT pair under the
   old regex, (b) it pairs under the new one, and (c) the newly paired quote is
   verbatim in that SID's own Gill source under `bot._quote_in_source`. An
   unpaired-but-now-paired SID whose quote does not verify is NOT a recovery -- it
   just changes which failure it earns.

   Clause (a) was added after the two-clause rule produced an unexplained flip:
   `noise_floor/nf1/scapegoat_001` `LEVITICUS_16_10_S00` was ALREADY paired under
   the old regex, so the fix cannot be what changed it. What changed it was limit 2
   above -- the recorded answer is post-repair, so the span on disk is the verbatim
   one the repair substituted, while the live verifier failed the pre-repair quote.
   Without clause (a) this probe credits the fix with a recovery that belongs to
   `_repair_quotes_in_answer`. Such SIDs are reported under
   `already_paired_but_unverified` rather than dropped: they are the measure of how
   much of the recorded failure set this probe CANNOT speak to.

5. The reconstruction of `overall_pass` from the recorded gate fields is asserted
   against the recorded value for every record before any flip is reported. If the
   reconstruction disagrees anywhere, the run aborts rather than reporting a delta
   it cannot derive.
"""
import io
import json
import os
import re
import sys
import glob

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import bot  # noqa: E402

# The closer before the fix. Reproduced, not imported, because the point is to
# compare the two; `test_quote_cite_pairing.py` holds the same literal and would
# fail if the live regex ever matched it again.
OLD_RE = re.compile(
    r'["“”]([^"“”]+)["“”][^"“”\n\[\]]{0,80}\[([A-Z0-9_]+_S\d+)\]'
)
NEW_RE = bot.QUOTE_WITH_CITE_RE
ANY_CITE = bot._ANY_CITE_RE


def pairs(rx, answer):
    """sid -> list of quoted spans paired to it."""
    out = {}
    for m in rx.finditer(answer):
        out.setdefault(m.group(2), []).append(m.group(1))
    return out


def verbatim_in_gill(quote, sid, chunks):
    src = (chunks.get("[%s]" % sid) or {}).get("gill") or ""
    if not src:
        return False
    return bot._quote_in_source(quote, bot._normalize_for_quote_match(src))


def reconstruct_pass(score, verified):
    """overall_pass from the recorded gates, with must_be_verified_ok substituted."""
    if score.get("expected_behavior") == "refuse":
        return bool(score.get("refusal_correct")
                    and score.get("must_express_ok")
                    and score.get("must_not_express_ok"))
    mbv = True if score.get("must_be_verified_skipped") else bool(verified)
    recall = score.get("must_cite_recall")
    mc_ok = True
    if score.get("must_cite_missing") and recall is not None and recall < 0.5:
        mc_ok = False
    return bool(score.get("refusal_correct")
                and mc_ok
                and not score.get("must_not_cite_violated")
                and score.get("must_express_ok")
                and score.get("must_not_express_ok")
                and mbv)


def rescore_arm(arm_dir):
    rows = []
    for f in sorted(glob.glob(os.path.join(arm_dir, "*.json"))):
        if os.path.basename(f) == "summary.json":
            continue
        rec = json.load(io.open(f, encoding="utf-8"))
        score = rec.get("score") or {}
        resp = rec.get("response") or {}
        answer = score.get("answer") or ""
        qid = score.get("id") or os.path.basename(f)[:-5]

        # The reconstruction self-check: recorded gates must reproduce the
        # recorded verdict before any re-scored verdict is believed.
        recorded_verified = resp.get("verified", True)
        recon = reconstruct_pass(score, recorded_verified)
        if recon != bool(score.get("overall_pass")):
            raise SystemExit(
                "ABORT: cannot reconstruct overall_pass for %s (recorded %s, "
                "reconstructed %s). The re-score is not derivable; nothing written."
                % (f, score.get("overall_pass"), recon))

        unver = list(resp.get("unverified_sentence_ids") or [])
        chunks = bot._build_chunks_by_sid(resp.get("evidence") or [])
        old_p, new_p = pairs(OLD_RE, answer), pairs(NEW_RE, answer)

        resolved, unresolved, already = [], [], []
        for sid in unver:
            if sid in old_p:
                # The fix cannot be the cause; see clause (a) in the header.
                already.append(sid)
                unresolved.append(sid)
                continue
            got = [q for q in new_p.get(sid, []) if verbatim_in_gill(q, sid, chunks)]
            (resolved if got else unresolved).append(sid)

        # The other direction: a SID that paired under the old regex and whose
        # captured span CHANGED, or that stopped pairing. Either would be a
        # regression introduced by the widened closer.
        changed = sorted(s for s in old_p if old_p[s] != new_p.get(s, []))
        lost = sorted(s for s in old_p if s not in new_p)

        new_verified = bool(recorded_verified) or (not unresolved and bool(resolved))
        rows.append({
            "id": qid,
            "cited": len({m.group(1) for m in ANY_CITE.finditer(answer)}),
            "recorded_verified": bool(recorded_verified),
            "recorded_pass": bool(score.get("overall_pass")),
            "unverified": unver,
            "resolved": resolved,
            "unresolved": unresolved,
            "already_paired_but_unverified": already,
            "capture_changed": changed,
            "pairing_lost": lost,
            "new_verified": new_verified,
            "new_pass": reconstruct_pass(score, new_verified),
            "run_passes": rec.get("run_passes") or [],
        })
    return rows


def main(argv):
    arms = argv[1:] or [
        "evals/output/off_vs_on_rerun2_20261004/off",
        "evals/output/off_vs_on_rerun2_20261004/on",
        "evals/output/off_vs_on_rerun3_20261004/off",
        "evals/output/off_vs_on_rerun3_20261004/on",
    ]
    report = {}
    for arm in arms:
        rows = rescore_arm(arm)
        flips = [r for r in rows if r["new_pass"] != r["recorded_pass"]]
        report[arm] = {
            "questions": len(rows),
            "representative_passed_before": sum(1 for r in rows if r["recorded_pass"]),
            "representative_passed_after": sum(1 for r in rows if r["new_pass"]),
            "flips_to_pass": sorted(r["id"] for r in flips if r["new_pass"]),
            "flips_to_fail": sorted(r["id"] for r in flips if not r["new_pass"]),
            "capture_changed": sorted(r["id"] for r in rows if r["capture_changed"]),
            "pairing_lost": sorted(r["id"] for r in rows if r["pairing_lost"]),
            "unresolved_still": {r["id"]: r["unresolved"] for r in rows if r["unresolved"]},
            "already_paired_but_unverified": {r["id"]: r["already_paired_but_unverified"]
                                              for r in rows if r["already_paired_but_unverified"]},
            "rows": rows,
        }
        print("%-54s rep %2d -> %2d   +%s  -%s" % (
            arm,
            report[arm]["representative_passed_before"],
            report[arm]["representative_passed_after"],
            report[arm]["flips_to_pass"] or "[]",
            report[arm]["flips_to_fail"] or "[]"))
        if report[arm]["capture_changed"] or report[arm]["pairing_lost"]:
            print("   REGRESSION CANDIDATES capture_changed=%s pairing_lost=%s"
                  % (report[arm]["capture_changed"], report[arm]["pairing_lost"]))

    out = os.path.join("evals", "output", "rescore_quote_pairing.json")
    io.open(out, "w", encoding="utf-8", newline="\n").write(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    print("")
    print("wrote %s" % out)
    print("REMINDER: representative run only. Runs 1..n-1 have no answer text on "
          "disk, so no corrected run-level rate comes out of this.")


if __name__ == "__main__":
    main(sys.argv)
