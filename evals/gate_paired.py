"""The flag gate: a PAIRED per-question test against the measured null, plus a one-way ratchet.

    python evals/gate_paired.py --off OFF_DIR --on ON_DIR --null NULL_A NULL_B [--null C D ...]
                               [--history DIR ...] [--alpha 0.05] [--json-out F]

Ruling (2026-10-04, Chris): "replace the gate with a paired per-question test against the null
plus 'stable-fail under ON on any question that ever stable-passed'."

WHAT THE OLD GATE WAS, AND WHY IT IS REPLACED
---------------------------------------------
Ruling 1 (2026-09-27) gated the ADR-0009 flag on ONE STABLE-PASS -> STABLE-FAIL flip between two
arms. Two identical arms then produced ten class changes and a 6/6 -> 0/6 flip at FIXED
configuration (`docs/audits/RESULT_pinned_floor_laneA_20260927.md`). A gate whose trigger the
null reproduces is not measuring the flag. The repair is not a bigger threshold -- a scalar
threshold on a pooled count throws away the one fact that makes the comparison tractable, that
the SAME questions are asked in both arms. So the question is asked per question, and the
comparison is against what two identical arms did on that same question.

THE TEST
--------
For every question classifiable in all supplied arms:

    effect(q) = pass_rate(ON, q) - pass_rate(OFF, q)
    noise(q)  = max over the supplied null pairs of |pass_rate(B, q) - pass_rate(A, q)|

`noise(q)` is a MAXIMUM, deliberately. One null replicate understates the noise: the floor pair
pooled 55/78 twice and still moved 14 of 78 questions, and `scapegoat_001` went 6/6 -> 0/6 with
nothing changed. Taking the largest movement any null pair showed on that question makes the
noise band harder to beat, which is the direction an honest gate errs in.

Then a two-sided exact binomial SIGN TEST over the questions where |effect(q)| and noise(q)
differ: wins = |effect| > noise, losses = |effect| < noise, ties dropped and counted. It is run
TWICE -- over every tested question, which is a measurement of the arm pair, and over the
ruling-1 gating subset, which is what decides. The regression list is split the same way, and it
has to be: with `scapegoat_001` in, the recorded 6/6 -> 0/6 fall at fixed configuration supplies
a regression row that could fire the gate, which is what pulling it from the gate was for. Exact,
closed form (`math.comb`), no sampling and no seed -- a permutation test here would freeze a coin
and call it determinism. The p-value answers one question only: *is this pair of arms a different
measurement from two identical arms?* It does not say the flag is better or worse, and it is not
a per-question claim.

THE RATCHET (clause b)
----------------------
Independent of the test, and not statistical: any question that is STABLE-FAIL under ON and was
STABLE-PASS in ANY arm ever supplied (the effect arms, the null arms, and every `--history` arm)
fires the gate. This is a one-way safety clause -- it does not need significance, because "a
question that used to work now never works" is not a distributional claim.

It honours the ruling-1 NON_GATING exclusions, and it has to: `scapegoat_001` is the recorded
case of a 6/6 -> 0/6 fall at fixed configuration, so an unexcluded ratchet would fire on the coin
on its first run. Excluded trips are reported in full and raise a note, because an exclusion
nobody sees is indistinguishable from a gate that failed to fire.

WHAT IT REFUSES
---------------
  - NO NULL PAIR: a delta cannot be read without one. This is a refusal, not a default -- the
    whole defect in the old gate was reading a difference against an unmeasured floor.
  - arms that do not share a question set (a missing id is not a 0);
  - arms under N = MIN_CLASSIFICATION_RUNS runs per question (a note, loudly, on every arm that
    is short);
  - a null pair that is not actually a null -- it cannot verify that two arms were identically
    configured, so it reports each arm's recorded pin and serving config and says so.

WHAT IT DOES NOT DO
-------------------
It does not re-score anything. It reads `run_passes` as persisted, and `run_passes` is written
from whatever the scorer believed at run time. A scorer defect (the quote-pairing regex, fixed in
`aaf48c9`) is baked into every arm run before the fix, and no amount of pairing recovers it:
`run_eval.py` keeps only the representative run's response, so the other runs' verdicts cannot be
recomputed from disk. See `docs/audits/RESCORE_quote_pairing_laneA_20261004.md`.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from compare_arms import (MIN_CLASSIFICATION_RUNS, NON_GATING, NO_DATA, SF, SP,  # noqa: E402
                          answer_lm_config_of, load_arm, provider_pin_of)

# The significance level, as a default rather than a constant, because it is a choice and the
# flag that sets it should appear in the output next to the p-value it judged.
DEFAULT_ALPHA = 0.05

# Pass rates are k/n, and two mathematically equal differences over different n are not equal in
# binary floating point: 3/5 - 2/5 is 0.19999999999999998 while 2/10 - 0/10 is exactly 0.2. Under
# a bare `>` that artifact decides a win, and a float artifact must not contribute a vote to a
# gate. Anything inside this of the band is a TIE, which the sign test drops.
TIE_EPS = 1e-9


def sign_test_two_sided(wins: int, losses: int):
    """Exact two-sided binomial sign test at p=0.5 over the DISCORDANT pairs.

    Returns None when there are no discordant pairs -- which is NOT p=1. "Every question moved
    exactly as much as the null did" and "there is no evidence either way" are different facts,
    and a gate that renders the second as a comfortable 1.0 has reported a measurement it did
    not make.
    """
    n = wins + losses
    if n <= 0:
        return None
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / float(2 ** n)
    return min(1.0, 2.0 * tail)


def pass_rate(q: dict):
    """passes/runs, or None when the question has no classifiable runs.

    None, never 0.0: a question whose every run errored has no pass rate, and scoring it as a
    total failure is how five HTTP-500 questions once read as five regressions.
    """
    runs = q.get("runs") or 0
    if not runs or q.get("class") == NO_DATA:
        return None
    return (q.get("passes") or 0) / float(runs)


def _shared_ids(arms: dict):
    """The id set every arm shares, plus what each arm holds that the others do not."""
    sets = {label: set(arm["questions"]) for label, arm in arms.items()}
    common = set.intersection(*sets.values()) if sets else set()
    missing = {label: sorted(s - common) for label, s in sets.items() if s - common}
    return common, missing


def gate(off: dict, on: dict, nulls: list, history: list = None, alpha: float = DEFAULT_ALPHA,
         labels: dict = None) -> dict:
    """The verdict, with every number it rests on.

    `nulls` is a list of (arm_a, arm_b) pairs. An empty list is a refusal, not a default.
    `history` is extra arms consulted ONLY for the ratchet's ever-stable-passed set.
    """
    labels = labels or {}
    l_off, l_on = labels.get("off", "OFF"), labels.get("on", "ON")
    if not nulls:
        raise SystemExit(
            "no null pair supplied, so there is nothing to test the difference against. Two "
            "identical arms moved 14 of 78 questions and flipped one 6/6 -> 0/6 on this very "
            "harness; a per-question delta read without that measurement is the defect this gate "
            "replaces, not a weaker version of it. Pass --null ARM_A ARM_B.")

    arms = {l_off: off, l_on: on}
    for i, (na, nb) in enumerate(nulls):
        arms["null%d.a" % i], arms["null%d.b" % i] = na, nb

    # The EFFECT pair must share its question set exactly. There is no reading of a per-question
    # delta over a question only one of the two arms was asked.
    common, missing = _shared_ids({l_off: off, l_on: on})
    if missing:
        raise SystemExit(
            "the two arms under comparison do not share a question set, so no paired test is "
            "meaningful.\n"
            + "\n".join("  only in %s: %s" % (k, v) for k, v in sorted(missing.items()))
            + "\nA missing question is not a failure and must not be scored as one.")

    notes = []
    # A NULL PAIR is held to a different standard, and deliberately. Its two arms must share
    # their own set -- a null measured over different questions is not a null -- but it does NOT
    # have to cover the effect pair's set. The real floor pairs on disk were run over a smaller
    # question list than the arms they bound, and refusing the whole comparison for that would
    # throw away the only null measurement that exists. A question the null never measured gets
    # NO band (see below), so it is excluded from the test rather than given a free pass.
    for i, (na, nb) in enumerate(nulls):
        _, nmiss = _shared_ids({"null%d.a" % i: na, "null%d.b" % i: nb})
        if nmiss:
            raise SystemExit(
                "null pair %d was run over two different question sets, so its spread is not a "
                "noise measurement.\n" % i
                + "\n".join("  only in %s: %s" % (k, v) for k, v in sorted(nmiss.items())))
        uncovered = sorted(common - set(na["questions"]))
        if uncovered:
            notes.append("NULL PAIR %d DOES NOT COVER: %s. Those questions take their band from "
                         "the other null pair(s), and are EXCLUDED from the test entirely if no "
                         "pair covers them." % (i, ", ".join(uncovered)))
    # Runs per question, per arm. The pairing does not rescue an under-powered arm: at N=3 a
    # question at p~0.83 reads 3/3 about 58% of the time, so its "effect" is the floor.
    for label in sorted(arms):
        n = max([v.get("runs") or 0 for v in arms[label]["questions"].values()] or [0])
        if n < MIN_CLASSIFICATION_RUNS:
            notes.append("UNDER-POWERED: %s ran %d time(s) per question, below the N=%d ruling 1 "
                         "requires. Its per-question rates are not distinguishable from the floor."
                         % (label, n, MIN_CLASSIFICATION_RUNS))

    # A null pair is a CLAIM about two arms, and this instrument cannot verify it. What it can do
    # is report the two things that made an earlier "identical" pair not identical.
    for i, (na, nb) in enumerate(nulls):
        if provider_pin_of(na) != provider_pin_of(nb):
            notes.append("NULL PAIR %d IS NOT A NULL: the two arms recorded different provider "
                         "pins (%r vs %r), so its spread includes a provider difference."
                         % (i, provider_pin_of(na), provider_pin_of(nb)))
        if answer_lm_config_of(na) != answer_lm_config_of(nb):
            notes.append("NULL PAIR %d IS NOT A NULL: the two arms recorded different serving "
                         "configurations (%s vs %s), so its spread includes what served them."
                         % (i, answer_lm_config_of(na) or "nothing recorded",
                            answer_lm_config_of(nb) or "nothing recorded"))

    rows, excluded = [], []
    for qid in sorted(common):
        r_off, r_on = pass_rate(off["questions"][qid]), pass_rate(on["questions"][qid])
        if r_off is None or r_on is None:
            excluded.append(qid)
            continue
        bands, per_null = [], []
        for na, nb in nulls:
            # .get, because a null pair need not cover the effect pair's question set. A missing
            # question yields a rate of None, which contributes no band -- never a band of 0.
            ra = pass_rate(na["questions"].get(qid, {}))
            rb = pass_rate(nb["questions"].get(qid, {}))
            if ra is None or rb is None:
                per_null.append(None)
                continue
            bands.append(abs(rb - ra))
            per_null.append(round(rb - ra, 4))
        if not bands:
            # The question has no null measurement at all. It is NOT given a band of 0, which
            # would make every movement on it beat the noise by construction.
            excluded.append(qid)
            continue
        eff = r_on - r_off
        noise = max(bands)
        rows.append({"id": qid, "rate_off": round(r_off, 4), "rate_on": round(r_on, 4),
                     "effect": round(eff, 4), "noise_band": round(noise, 4),
                     "null_deltas": per_null,
                     "beats_noise": abs(eff) - noise > TIE_EPS,
                     "within_noise": noise - abs(eff) > TIE_EPS,
                     # The two directional verdicts, computed here from the UNROUNDED rates and
                     # under the same epsilon as the sign-test vote, so a row can never be a
                     # regression under one convention and a tie under the other.
                     "lost_beyond_noise": (-eff) - noise > TIE_EPS,
                     "gained_beyond_noise": eff - noise > TIE_EPS,
                     "class_off": off["questions"][qid]["class"],
                     "class_on": on["questions"][qid]["class"]})
    if excluded:
        notes.append("EXCLUDED FROM THE TEST (no classifiable runs in some arm, or no null "
                     "measurement on that question): %s. The test below is over %d questions, "
                     "not %d." % (", ".join(excluded), len(rows), len(common)))
    if not rows:
        notes.append("NO TESTABLE QUESTION: every shared question was excluded above, so the "
                     "paired test is not a result and the verdict rests on the ratchet alone.")

    def _sign(rs):
        w = sum(1 for r in rs if r["beats_noise"])
        l = sum(1 for r in rs if r["within_noise"])
        return {"wins_effect_beats_noise": w, "losses_effect_within_noise": l,
                "ties": len(rs) - w - l, "p_two_sided": sign_test_two_sided(w, l),
                "questions": len(rs)}

    # Ruling 1's NON_GATING questions are MEASURED but do not decide. That applies to the sign
    # test and to the regression list as much as to the ratchet, and getting this wrong was a
    # real defect in the first draft of this file: with all questions in, `scapegoat_001` -- the
    # recorded 6/6 -> 0/6 fall at fixed configuration -- supplied a regression row that could
    # fire the gate, which is precisely what ruling 1 pulled it from the gate to prevent.
    #
    # So there are two of each: the ALL version, reported because an exclusion nobody sees is
    # indistinguishable from a gate that failed to fire, and the GATING version, which decides.
    gating_rows = [r for r in rows if r["id"] not in NON_GATING]
    st_all, st_gating = _sign(rows), _sign(gating_rows)
    p = st_all["p_two_sided"]

    # The directional lists. The sign test says "a different measurement"; it does not say which
    # way, and a flag is not gated on moving things. These are the only rows that can carry a
    # regression claim: ON lost MORE than the null band allows.
    regressions = [r for r in rows if r["lost_beyond_noise"]]
    improvements = [r for r in rows if r["gained_beyond_noise"]]
    regressions_gating = [r for r in regressions if r["id"] not in NON_GATING]
    if len(regressions) != len(regressions_gating):
        notes.append("REGRESSION ROW(S) EXCLUDED FROM THE DECISION: %s. Real movement past the "
                     "null band, on question(s) ruling 1 pulled from the gate. Reported, not "
                     "decisive."
                     % ", ".join(r["id"] for r in regressions if r["id"] in NON_GATING))
    if (st_all["p_two_sided"] is not None and st_all["p_two_sided"] <= alpha) != \
            (st_gating["p_two_sided"] is not None and st_gating["p_two_sided"] <= alpha):
        notes.append("THE EXCLUSIONS CHANGE THE SIGN TEST: over all %d tested questions p=%s, "
                     "over the %d gating ones p=%s (alpha=%g). The DECISION uses the gating "
                     "set; the other number is a measurement of the whole arm pair."
                     % (st_all["questions"],
                        "n/a" if st_all["p_two_sided"] is None else "%.4g" % st_all["p_two_sided"],
                        st_gating["questions"],
                        "n/a" if st_gating["p_two_sided"] is None
                        else "%.4g" % st_gating["p_two_sided"], alpha))

    # Clause (b), the ratchet. "Ever stable-passed" is read over every arm supplied, including
    # the ones that exist only as history.
    ever_sp = set()
    for arm in list(arms.values()) + list(history or []):
        ever_sp |= {q for q, v in arm["questions"].items() if v["class"] == SP}
    tripped, tripped_excluded = [], []
    for qid in sorted(common):
        if on["questions"][qid]["class"] != SF or qid not in ever_sp:
            continue
        where = sorted(lbl for lbl, arm in arms.items()
                       if arm["questions"].get(qid, {}).get("class") == SP)
        row = {"id": qid, "stable_passed_in": where or ["a --history arm only"],
               "rate_off": pass_rate(off["questions"][qid]),
               "rate_on": pass_rate(on["questions"][qid])}
        if qid in NON_GATING:
            tripped_excluded.append(dict(row, non_gating_reason=NON_GATING[qid]))
        else:
            tripped.append(row)
    if tripped_excluded:
        notes.append("RATCHET TRIP(S) EXCLUDED: "
                     + "; ".join(r["id"] + " (" + r["non_gating_reason"] + ")"
                                 for r in tripped_excluded)
                     + ". These are real STABLE-FAIL-under-ON events on questions ruling 1 pulled "
                       "from the gate pending a deterministic scorer. They do NOT fire the gate.")

    # The decision rests on the GATING sign test and the GATING regression list.
    significant = bool(st_gating["p_two_sided"] is not None
                       and st_gating["p_two_sided"] <= alpha)
    fires = bool(tripped) or bool(significant and regressions_gating)
    pg = st_gating["p_two_sided"]
    if significant and not regressions_gating:
        notes.append("DIFFERENT, BUT NOT WORSE: the gating set is distinguishable from the null "
                     "(p=%.4g <= alpha=%g) and no gating question lost more than its noise band. "
                     "The gate does not fire on movement." % (pg, alpha))
    if regressions_gating and not significant:
        notes.append("REGRESSION CANDIDATE(S) WITHOUT A DISTINGUISHABLE PAIR: %s lost more than "
                     "its noise band, but the gating set as a whole is not distinguishable from "
                     "two identical arms (p=%s). One question past one null band is what a null "
                     "pair also produces, which is why this does not fire on its own. The "
                     "RATCHET is the clause that catches a single question, and it is reported "
                     "separately below."
                     % (", ".join(r["id"] for r in regressions_gating),
                        "n/a (no discordant pair)" if pg is None else "%.4g" % pg))
    reasons = ([] + (["ratchet"] if tripped else [])
               + (["paired test + regression"] if significant and regressions else []))
    return {
        "labels": {"off": l_off, "on": l_on},
        "alpha": alpha,
        "questions_shared": len(common),
        "questions_tested": len(rows),
        "excluded_ids": excluded,
        # Two sign tests: `sign_test` over every tested question (a measurement of the arm
        # pair) and `sign_test_gating` over the ruling-1 gating subset (what decides).
        "sign_test": dict(st_all, significant=bool(st_all["p_two_sided"] is not None
                                                   and st_all["p_two_sided"] <= alpha)),
        "sign_test_gating": dict(st_gating, significant=significant),
        "regressions_beyond_noise": regressions,
        "regressions_beyond_noise_n": len(regressions),
        "regressions_gating": regressions_gating,
        "regressions_gating_n": len(regressions_gating),
        "improvements_beyond_noise": improvements,
        "improvements_beyond_noise_n": len(improvements),
        "ratchet_tripped": tripped,
        "ratchet_tripped_n": len(tripped),
        "ratchet_tripped_excluded": tripped_excluded,
        "ratchet_tripped_excluded_n": len(tripped_excluded),
        # Which exclusions were in force for THIS pair, so an empty excluded list is tellable
        # apart from an exclusion set that was never applied.
        "non_gating_questions": sorted(q for q in common if q in NON_GATING),
        "null_pairs": len(nulls),
        "rows": rows,
        "notes": notes,
        "gate_fires": fires,
        "verdict": ("GATE FIRES: " + " and ".join(reasons)) if fires else "gate does not fire",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--off", required=True, help="the baseline arm directory")
    ap.add_argument("--on", required=True, help="the arm with the change under test")
    ap.add_argument("--null", nargs=2, action="append", metavar=("ARM_A", "ARM_B"),
                    help="a pair of IDENTICALLY configured arms. Required, repeatable; the "
                         "per-question noise band is the LARGEST movement any pair showed.")
    ap.add_argument("--history", nargs="+", default=[], metavar="DIR",
                    help="extra arms consulted only for the ratchet's ever-stable-passed set")
    ap.add_argument("--alpha", type=float, default=DEFAULT_ALPHA,
                    help="significance level for the sign test (default %(default)s)")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    nulls = [(load_arm(a), load_arm(b)) for a, b in (args.null or [])]
    res = gate(load_arm(args.off), load_arm(args.on), nulls,
               history=[load_arm(d) for d in args.history], alpha=args.alpha,
               labels={"off": os.path.basename(os.path.normpath(args.off)),
                       "on": os.path.basename(os.path.normpath(args.on))})

    l_off, l_on = res["labels"]["off"], res["labels"]["on"]
    print("=" * 74)
    print("PAIRED GATE  %s -> %s   %d shared / %d tested / %d null pair(s)"
          % (l_off, l_on, res["questions_shared"], res["questions_tested"], res["null_pairs"]))
    print("=" * 74)
    for n in res["notes"]:
        print("  !! %s" % n)
    for key, what in (("sign_test", "all tested  "), ("sign_test_gating", "gating only ")):
        st = res[key]
        print("Sign test %s: %d/%d beat the noise band, %d within it, %d tied -> p=%s %s%s"
              % (what, st["wins_effect_beats_noise"], st["questions"],
                 st["losses_effect_within_noise"], st["ties"],
                 "n/a" if st["p_two_sided"] is None else "%.4g" % st["p_two_sided"],
                 "DISTINGUISHABLE" if st["significant"] else "not distinguishable",
                 "  <- decides" if key == "sign_test_gating" else ""))
    print("Regressions beyond the noise band  : %d (%d gating)"
          % (res["regressions_beyond_noise_n"], res["regressions_gating_n"]))
    for r in res["regressions_beyond_noise"]:
        print("    %-44s %.2f -> %.2f  (band %.2f)%s"
              % (r["id"][:44], r["rate_off"], r["rate_on"], r["noise_band"],
                 "" if r in res["regressions_gating"] else "   NOT GATING"))
    print("Improvements beyond the noise band : %d" % res["improvements_beyond_noise_n"])
    for r in res["improvements_beyond_noise"]:
        print("    %-44s %.2f -> %.2f  (band %.2f)"
              % (r["id"][:44], r["rate_off"], r["rate_on"], r["noise_band"]))
    print("Ratchet (STABLE-FAIL under ON, ever STABLE-PASS) : %d" % res["ratchet_tripped_n"])
    for r in res["ratchet_tripped"]:
        print("    %-44s stable-passed in %s" % (r["id"][:44], ", ".join(r["stable_passed_in"])))
    if res["non_gating_questions"]:
        print("Non-gating questions in this pair : %s" % ", ".join(res["non_gating_questions"]))
    print("")
    print(res["verdict"])
    if args.json_out:
        io.open(args.json_out, "w", encoding="utf-8").write(
            json.dumps(res, indent=2, sort_keys=True, default=str))
        print("\nWritten: %s" % args.json_out)
    # The gate FIRING is a finding, and a finding is not a crash: exit 1 so a script can branch
    # on it, with the whole basis printed above either way.
    return 1 if res["gate_fires"] else 0


if __name__ == "__main__":
    sys.exit(main())
