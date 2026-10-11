"""The flag gate: a PAIRED per-question test against the measured null, plus a one-way ratchet.

    python evals/gate_paired.py --off OFF_DIR --on ON_DIR --null NULL_A NULL_B [--null C D ...]
                               [--replicate OFF2 ON2] [--history DIR ...] [--alpha 0.05]
                               [--json-out F]

Ruling (2026-10-04, Chris): "replace the gate with a paired per-question test against the null
plus 'stable-fail under ON on any question that ever stable-passed'."

Ruling (2026-10-11, Chris): "Replication rule adopted: effect requires sign repetition across
two replicates; ratchet unchanged."

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

THE REPLICATION RULE (2026-10-11)
---------------------------------
The sign test above answers a question about a PAIR of arms, and that answer turned out to be a
draw of its own. Two replicates of one off-vs-on comparison, against the same independent null,
returned gating p=1.0 (3 wins / 3 losses) and p=0.0391 (8/1, six gating regressions) over the
same 13 questions at the same configuration; requiring each question's sign to repeat left 3
down, 3 up and SEVEN that did not reproduce their own direction, four of them among that second
run's six gating regressions (docs/audits/GATE_PAIRED_two_arm_pairs_laneA_20261004.md).

So the EFFECT clause now needs a second (off, on) pair -- a replicate of the whole comparison,
not of one arm -- and fires only when BOTH of these hold:

  (a) the gating sign test is significant in BOTH replicates. It was the aggregate verdict that
      flipped, so asking for it once is asking for the thing that was shown not to replicate;
  (b) at least one GATING question is a replicated regression: the effect has the same negative
      sign in both replicates, and lost more than its noise band in at least one of them.

Beating the band in EITHER replicate suffices once the direction has repeated, because the band
is itself one pair's draw -- the only independent null on disk reports exactly 0.00 on 7 of 13
questions -- and requiring it twice would be a requirement about the null's noise, not the
effect's size.

Each replicate's sign test is computed over its OWN full row set, never over the rows filtered
to those that replicated: selecting questions by a large-looking effect and then testing those
same effects against p=0.5 is no longer a null.

WITH ONE PAIR THE EFFECT CLAUSE ABSTAINS. It does not fall back to the single-replicate sign
test -- that is the clause this ruling retired, and a gate that reverts to a retired clause when
its input is missing has no rule at all. `effect_clause.state` reads "abstained", the verdict
says so in those words, and the sign tests are still reported as measurements of their pair. The
RATCHET is then the only clause that can fire, which is the clause that was carrying the weight
at this sample size anyway.

THE RATCHET (clause b)
----------------------
Independent of the test, and not statistical: any question that is STABLE-FAIL under ON and was
STABLE-PASS in ANY arm ever supplied (the effect arms, the null arms, and every `--history` arm)
fires the gate. This is a one-way safety clause -- it does not need significance, because "a
question that used to work now never works" is not a distributional claim.

The clause is UNCHANGED by the replication rule and is read over every ON arm supplied, both
replicates'. It does not wait for a direction to repeat, for the reason it exists. Reading the
replicate's arms for the ever-stable-passed set -- where they can only make the ratchet harder
to escape -- while refusing to read the same arms for the trip itself would be one rule applied
on one axis and not the other. One row per question, listing every ON arm it stable-failed in.

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
`aaf48c9`) is baked into every arm run before the fix, and no amount of pairing recovers it. For
the four arms of 2026-10-04 it cannot be recovered at all: `run_eval.py` kept only the
representative run's response, so four runs in five hold a verdict that cannot be recomputed
(`docs/audits/RESCORE_quote_pairing_laneA_20261004.md`). From `95a4981` the harness records the
verification verdict, the wire flag and the unverified sids for EVERY run, so an arm run after
that commit is re-scorable from disk. That is a statement about future arms only.
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


def sign_of(eff: float) -> int:
    """-1, 0 or +1 under the same epsilon the sign-test vote uses.

    A direction is what the replication rule repeats, so it must be computed under one
    convention everywhere: a question that counts as a tie for the band comparison and as a
    movement for the replication table would be two different facts about one measurement.
    """
    if eff > TIE_EPS:
        return 1
    if eff < -TIE_EPS:
        return -1
    return 0


def build_rows(off: dict, on: dict, nulls: list, common, correlated_nulls=()):
    """Per-question effect against the measured band, for ONE pair of arms.

    Extracted so the replicate pair is scored by this code and not by a second copy of it:
    two implementations of "does this effect beat the band" is how a replication requirement
    would end up comparing two different measurements and calling the difference a direction.

    `correlated_nulls` is the indices of null pairs that share an arm with this effect pair.
    A row records whether its band came ONLY from such a pair, because a correlated band
    widens where the effect widens: it cannot be allowed to silently suppress a movement that
    replicates. Marked here, never overridden -- the band is still a real measurement of two
    like-configured arms, and relaxing it would be a weaker gate wearing a stricter name.
    """
    rows, excluded = [], []
    for qid in sorted(common):
        r_off, r_on = pass_rate(off["questions"][qid]), pass_rate(on["questions"][qid])
        if r_off is None or r_on is None:
            excluded.append(qid)
            continue
        bands, per_null = [], []
        for i, (na, nb) in enumerate(nulls):
            # .get, because a null pair need not cover the effect pair's question set. A missing
            # question yields a rate of None, which contributes no band -- never a band of 0.
            ra = pass_rate(na["questions"].get(qid, {}))
            rb = pass_rate(nb["questions"].get(qid, {}))
            if ra is None or rb is None:
                per_null.append(None)
                continue
            bands.append((i, abs(rb - ra)))
            per_null.append(round(rb - ra, 4))
        if not bands:
            # The question has no null measurement at all. It is NOT given a band of 0, which
            # would make every movement on it beat the noise by construction.
            excluded.append(qid)
            continue
        eff = r_on - r_off
        noise = max(b for _, b in bands)
        # Which pair(s) actually supplied the maximum. Compared under TIE_EPS for the same
        # reason the vote is: two pairs can tie on a band only in exact arithmetic.
        at_max = {i for i, b in bands if abs(b - noise) <= TIE_EPS}
        rows.append({"id": qid, "rate_off": round(r_off, 4), "rate_on": round(r_on, 4),
                     "effect": round(eff, 4), "noise_band": round(noise, 4),
                     "effect_sign": sign_of(eff),
                     "null_deltas": per_null,
                     "band_from_null_pairs": sorted(at_max),
                     "band_from_correlated_null_only": bool(at_max)
                                                       and at_max <= set(correlated_nulls),
                     "beats_noise": abs(eff) - noise > TIE_EPS,
                     "within_noise": noise - abs(eff) > TIE_EPS,
                     # The two directional verdicts, computed here from the UNROUNDED rates and
                     # under the same epsilon as the sign-test vote, so a row can never be a
                     # regression under one convention and a tie under the other.
                     "lost_beyond_noise": (-eff) - noise > TIE_EPS,
                     "gained_beyond_noise": eff - noise > TIE_EPS,
                     "class_off": off["questions"][qid]["class"],
                     "class_on": on["questions"][qid]["class"]})
    return rows, excluded


def gate(off: dict, on: dict, nulls: list, history: list = None, alpha: float = DEFAULT_ALPHA,
         labels: dict = None, sources: dict = None, replicate: tuple = None) -> dict:
    """The verdict, with every number it rests on.

    `nulls` is a list of (arm_a, arm_b) pairs. An empty list is a refusal, not a default.
    `history` is extra arms consulted ONLY for the ratchet's ever-stable-passed set.
    `replicate` is a SECOND (off, on) pair at the same configuration -- a replicate of the
    whole comparison, not of one arm. Without it the EFFECT clause abstains; see the module
    docstring. The ratchet is unaffected either way.
    """
    labels = labels or {}
    l_off, l_on = labels.get("off", "OFF"), labels.get("on", "ON")
    l_off2, l_on2 = labels.get("off2", "OFF2"), labels.get("on2", "ON2")
    if not nulls:
        raise SystemExit(
            "no null pair supplied, so there is nothing to test the difference against. Two "
            "identical arms moved 14 of 78 questions and flipped one 6/6 -> 0/6 on this very "
            "harness; a per-question delta read without that measurement is the defect this gate "
            "replaces, not a weaker version of it. Pass --null ARM_A ARM_B.")

    off2, on2 = replicate if replicate else (None, None)
    if replicate and len({l_off, l_on, l_off2, l_on2}) != 4:
        raise SystemExit(
            "two of the four arms carry the same label (%s). The arms dict is keyed by label, so "
            "a collision would silently drop an arm from the noise band, the ever-stable-passed "
            "set and the report. Pass directories whose names differ, or distinct labels."
            % ", ".join(sorted({l_off, l_on, l_off2, l_on2})))
    arms = {l_off: off, l_on: on}
    if replicate:
        arms[l_off2], arms[l_on2] = off2, on2
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
    if replicate:
        # The replicate pair is held to the same standard as the first: a paired test over a
        # question only one arm was asked is not a reading, and that does not become true
        # twice over.
        _, rmiss = _shared_ids({l_off2: off2, l_on2: on2})
        if rmiss:
            raise SystemExit(
                "the REPLICATE pair's two arms do not share a question set, so it is not a "
                "replicate of the comparison.\n"
                + "\n".join("  only in %s: %s" % (k, v) for k, v in sorted(rmiss.items())))
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

    # A null pair that INCLUDES one of the arms under test is still a null measurement -- both
    # of its members ran at the same configuration -- but it is not an INDEPENDENT one. The same
    # rate(off, q) then enters the effect and that pair's own band, so a question where the
    # baseline happened to land at an extreme inflates both together. That correlation widens the
    # band exactly where the effect is widest, which biases this gate toward SILENCE, not toward
    # firing; silence is the direction that hides a regression, so the sharing is named rather
    # than refused. Measured on the two 2026-10-04 rerun pairs: adding the (rerun2/off,
    # rerun3/off) pair moved rerun3's gating sign test from p=0.039 to p=0.4531 on its own.
    # Computed PER EFFECT PAIR, because a pair is correlated with the arms it shares, and a
    # null that shares an arm with the replicate need not share one with the first pair. The
    # indices are carried into build_rows so each row can say whether its band came only from
    # a correlated pair -- a band that widens with the effect must not quietly suppress a
    # movement that replicated.
    def _correlated(pair_labels):
        hits = set()
        if not sources:
            return hits
        for i, _ in enumerate(nulls):
            for suffix in ("a", "b"):
                key = "null%d.%s" % (i, suffix)
                for lbl in pair_labels:
                    if sources.get(key) and sources.get(key) == sources.get(lbl):
                        hits.add(i)
                        _note = (
                            "NULL PAIR %d IS NOT INDEPENDENT: its %s arm is the same run "
                            "directory as %s, so rate(%s) enters both the effect and this pair's "
                            "band. The band is a real measurement of two like-configured arms, "
                            "but a correlated one: it widens where the effect widens, biasing "
                            "this gate toward silence. Read a non-firing verdict accordingly."
                            % (i, suffix, lbl, lbl))
                        if _note not in notes:
                            notes.append(_note)
        return hits

    correlated_nulls = _correlated((l_off, l_on))
    correlated_nulls2 = _correlated((l_off2, l_on2)) if replicate else set()

    rows, excluded = build_rows(off, on, nulls, common, correlated_nulls)
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

    # --- THE REPLICATION RULE (ruling, Chris 2026-10-11) --------------------------------
    # "Effect requires sign repetition across two replicates." Measured basis: two replicates
    # of ONE off-vs-on comparison, against the same independent null, returned p=1.0 and
    # p=0.0391 on the same 13 questions at the same configuration, and 7 of the 13 did not
    # reproduce their own direction
    # (docs/audits/GATE_PAIRED_two_arm_pairs_laneA_20261004.md).
    #
    # Two conditions, because the instrument was unstable at BOTH levels. Per question: the
    # sign of the effect must repeat. In aggregate: the gating sign test must be significant
    # in BOTH replicates -- it was the aggregate verdict that flipped, so requiring it once is
    # requiring the thing that was shown not to replicate.
    #
    # The sign test is computed on each replicate's OWN full row set, never on the rows
    # filtered to those that replicated. Selecting questions by a large-looking effect and
    # then testing those same effects against p=0.5 is not a null any more; the replication
    # requirement belongs on the regression list, which is a per-question claim, not on the
    # distributional one.
    rows2, excluded2, st2_all, st2_gating, replication = [], [], None, None, []
    if replicate:
        rows2, excluded2 = build_rows(off2, on2, nulls, set(off2["questions"]),
                                      correlated_nulls2)
        st2_all = _sign(rows2)
        st2_gating = _sign([r for r in rows2 if r["id"] not in NON_GATING])
        by_id2 = {r["id"]: r for r in rows2}
        only_one = sorted(({r["id"] for r in rows} ^ set(by_id2)))
        if only_one:
            notes.append(
                "NOT TESTED IN BOTH REPLICATES: %s. A direction cannot repeat where it was "
                "measured once, so these questions are absent from the replication table and "
                "cannot supply a replicated regression. They are still in each replicate's own "
                "sign test, which is a measurement of that pair." % ", ".join(only_one))
        for r in rows:
            r2 = by_id2.get(r["id"])
            if r2 is None:
                continue
            same = r["effect_sign"] != 0 and r["effect_sign"] == r2["effect_sign"]
            lost = r["lost_beyond_noise"] or r2["lost_beyond_noise"]
            gained = r["gained_beyond_noise"] or r2["gained_beyond_noise"]
            replication.append({
                "id": r["id"],
                "effect_a": r["effect"], "effect_b": r2["effect"],
                "sign_a": r["effect_sign"], "sign_b": r2["effect_sign"],
                "direction_replicated": same,
                "beats_noise_a": r["beats_noise"], "beats_noise_b": r2["beats_noise"],
                "beats_noise_either": r["beats_noise"] or r2["beats_noise"],
                # Beating the band in EITHER replicate is enough, once the direction has
                # repeated. Requiring both would ask the band -- itself one pair's draw, 0.00
                # on 7 of 13 questions from the only independent null on disk -- to be beaten
                # twice, which is a requirement about the null's own noise, not about the
                # effect.
                "replicated_regression": bool(same and r["effect_sign"] < 0 and lost),
                "replicated_improvement": bool(same and r["effect_sign"] > 0 and gained),
                "band_from_correlated_null_only": bool(
                    r["band_from_correlated_null_only"]
                    and r2["band_from_correlated_null_only"]),
                "non_gating": r["id"] in NON_GATING})
        # A movement that replicated its direction and is held inside a band that NO
        # independent null pair supplied. Named, never overridden: the band is a real
        # measurement of two like-configured arms, and relaxing it on the strength of the
        # thing it is bounding would be a weaker gate wearing a stricter name. What this note
        # says is that nobody has measured the floor for this question independently.
        muffled = [t["id"] for t in replication
                   if t["direction_replicated"] and not t["beats_noise_either"]
                   and t["band_from_correlated_null_only"]]
        if muffled:
            notes.append(
                "HELD INSIDE A CORRELATED BAND: %s replicated its direction across both "
                "replicates and falls within a noise band that only a null pair SHARING an arm "
                "with an effect pair supplied. That band widens where the effect widens, so it "
                "is the weakest possible reason to call a movement noise. Not overridden -- an "
                "independent null on these questions is what would settle it."
                % ", ".join(muffled))

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
    #
    # The clause is UNCHANGED and is applied to every ON arm supplied -- both replicates' --
    # for the reason it exists: "a question that used to work now never works" is not a
    # distributional claim, so it does not need to repeat before it is worth knowing. Applying
    # it to one of two supplied arms would put the replicate's arms in the ever-stable-passed
    # set, where they can only make the ratchet HARDER to escape, while refusing to read the
    # same arms for the trip itself: one rule on one axis and not the other. Each trip records
    # which pair's ON arm it came from.
    ever_sp = set()
    for arm in list(arms.values()) + list(history or []):
        ever_sp |= {q for q, v in arm["questions"].items() if v["class"] == SP}
    on_arms = [(l_on, off, on)] + ([(l_on2, off2, on2)] if replicate else [])
    tripped, tripped_excluded = [], []
    for qid in sorted(common):
        if qid not in ever_sp:
            continue
        # ONE row per question, however many supplied ON arms stable-failed on it. A row per
        # (question, arm) would make `ratchet_tripped_n` count arms while reading as a count of
        # questions, and the same question caught twice is not two regressions.
        failed_in = [lbl for lbl, _, pair_on in on_arms
                     if (pair_on["questions"].get(qid) or {}).get("class") == SF]
        if not failed_in:
            continue
        where = sorted(lbl for lbl, arm in arms.items()
                       if arm["questions"].get(qid, {}).get("class") == SP)
        row = {"id": qid, "stable_passed_in": where or ["a --history arm only"],
               "stable_failed_in": failed_in,
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

    # The decision rests on the GATING sign test and the GATING regression list -- in BOTH
    # replicates, or not at all.
    significant = bool(st_gating["p_two_sided"] is not None
                       and st_gating["p_two_sided"] <= alpha)
    significant2 = (None if st2_gating is None
                    else bool(st2_gating["p_two_sided"] is not None
                              and st2_gating["p_two_sided"] <= alpha))
    replicated_regressions = [t for t in replication if t["replicated_regression"]]
    replicated_regressions_gating = [t for t in replicated_regressions if not t["non_gating"]]
    if replicate:
        effect_fires = bool(significant and significant2 and replicated_regressions_gating)
        effect_state = "fired" if effect_fires else "did_not_fire"
    else:
        # ABSTAIN. Not "did not fire", and above all not a fall back to the single-replicate
        # sign test -- that is the clause the ruling retired, and a gate that quietly reverts
        # to a retired clause when its input is missing has no rule at all. The ratchet still
        # decides, which is the clause that was carrying the weight at this sample size anyway.
        effect_fires = False
        effect_state = "abstained"
        notes.append(
            "EFFECT CLAUSE ABSTAINS: no replicate pair was supplied (--replicate OFF2 ON2). "
            "The replication rule (2026-10-11) requires the sign to repeat across two "
            "replicates of the whole comparison, and the single-replicate sign test it "
            "replaced is NOT used as a fallback: two replicates of one comparison returned "
            "p=1.0 and p=0.0391 on the same questions at the same configuration. The sign "
            "tests below are reported as measurements of this pair and decide nothing. Only "
            "the RATCHET can fire this run.")
    fires = bool(tripped) or effect_fires
    pg = st_gating["p_two_sided"]
    if replicate and significant != significant2:
        notes.append(
            "THE REPLICATES DISAGREE IN AGGREGATE: the gating sign test is %s on %s->%s and %s "
            "on %s->%s (alpha=%g). This is the instability the replication rule exists for, "
            "and it means the effect clause cannot fire on either verdict."
            % ("significant" if significant else "not significant", l_off, l_on,
               "significant" if significant2 else "not significant", l_off2, l_on2, alpha))
    if replicate and replicated_regressions_gating and not (significant and significant2):
        notes.append(
            "REPLICATED GATING REGRESSION(S) WITHOUT TWO DISTINGUISHABLE PAIRS: %s lost more "
            "than the band in at least one replicate and fell the SAME way in both. The "
            "aggregate test did not repeat, so the effect clause does not fire on it. The "
            "RATCHET is the clause that adjudicates one named question."
            % ", ".join(t["id"] for t in replicated_regressions_gating))
    if replicate and not replicated_regressions_gating and regressions_gating:
        notes.append(
            "NO GATING REGRESSION SURVIVED REPLICATION: %s lost more than its band in the "
            "first pair, and none of them fell the same way in both replicates. Measured, not "
            "decisive." % ", ".join(r["id"] for r in regressions_gating))
    # These two describe the FIRST pair. Since the replication rule they are statements about
    # one measurement, not about the decision, and they say so: a note that reads "the gate
    # does not fire on movement" beside an abstaining effect clause would be claiming the gate
    # weighed something it declined to weigh.
    if significant and not regressions_gating:
        notes.append("THIS PAIR IS DIFFERENT, BUT NOT WORSE: on %s->%s the gating set is "
                     "distinguishable from the null (p=%.4g <= alpha=%g) and no gating question "
                     "lost more than its noise band. A measurement of this pair; the decision is "
                     "the effect clause's, below." % (l_off, l_on, pg, alpha))
    if regressions_gating and not significant:
        notes.append("REGRESSION CANDIDATE(S) WITHOUT A DISTINGUISHABLE PAIR: on %s->%s, %s lost "
                     "more than its noise band, but the gating set as a whole is not "
                     "distinguishable from two identical arms (p=%s). One question past one null "
                     "band is what a null pair also produces. The RATCHET is the clause that "
                     "adjudicates a single question, and it is reported separately below."
                     % (l_off, l_on, ", ".join(r["id"] for r in regressions_gating),
                        "n/a (no discordant pair)" if pg is None else "%.4g" % pg))
    # `regressions`, not `regressions_gating`, used to appear here while `fires` was computed
    # from the gating list. A run that fired on the ratchet alone, with a NON_GATING question
    # past its band, then printed a verdict crediting "paired test + regression" -- a clause
    # that had been deliberately prevented from deciding. The verdict string is a causal claim
    # about why the gate fired and has to be built from the same values the firing was.
    reasons = ([] + (["ratchet"] if tripped else [])
               + (["replicated effect + regression"] if effect_fires else []))
    return {
        "labels": ({"off": l_off, "on": l_on} if not replicate else
                   {"off": l_off, "on": l_on, "off2": l_off2, "on2": l_on2}),
        "alpha": alpha,
        "questions_shared": len(common),
        "questions_tested": len(rows),
        "excluded_ids": excluded,
        # The effect clause's own state, as a named value rather than something a reader has to
        # infer from an empty list: "no replicate was supplied, so nothing was decided" and "two
        # replicates were supplied and agreed there is nothing here" are different findings, and
        # only one of them is evidence.
        "replicate_supplied": bool(replicate),
        "effect_clause": {
            "state": effect_state,
            "fires": effect_fires,
            "significant_a": significant,
            "significant_b": significant2,
            "replicated_regressions_n": len(replicated_regressions),
            "replicated_regressions_gating_n": len(replicated_regressions_gating),
        },
        "sign_test_replicate": (None if st2_all is None else
                                dict(st2_all, significant=bool(
                                    st2_all["p_two_sided"] is not None
                                    and st2_all["p_two_sided"] <= alpha))),
        "sign_test_replicate_gating": (None if st2_gating is None else
                                       dict(st2_gating, significant=significant2)),
        "questions_tested_replicate": len(rows2),
        "excluded_ids_replicate": excluded2,
        "rows_replicate": rows2,
        "replication": replication,
        "replication_n": len(replication),
        "replicated_regressions": replicated_regressions,
        "replicated_regressions_gating": replicated_regressions_gating,
        "replicated_improvements": [t for t in replication if t["replicated_improvement"]],
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
        "verdict": (
            "GATE FIRES: " + " and ".join(reasons) if fires
            else "gate does not fire on the RATCHET, and the EFFECT CLAUSE ABSTAINED (one "
                 "replicate only): nothing was decided about the effect, so this is not a "
                 "clean verdict on it" if effect_state == "abstained"
            else "gate does not fire"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--off", required=True, help="the baseline arm directory")
    ap.add_argument("--on", required=True, help="the arm with the change under test")
    ap.add_argument("--null", nargs=2, action="append", metavar=("ARM_A", "ARM_B"),
                    help="a pair of IDENTICALLY configured arms. Required, repeatable; the "
                         "per-question noise band is the LARGEST movement any pair showed.")
    ap.add_argument("--replicate", nargs=2, default=None, metavar=("OFF2", "ON2"),
                    help="a SECOND off/on pair at the same configuration -- a replicate of the "
                         "whole comparison. Without it the EFFECT clause ABSTAINS: two "
                         "replicates of one comparison returned p=1.0 and p=0.0391 on the same "
                         "13 questions, so one replicate's verdict is itself a draw (ruling, "
                         "2026-10-11). The ratchet is unaffected.")
    ap.add_argument("--history", nargs="+", default=[], metavar="DIR",
                    help="extra arms consulted only for the ratchet's ever-stable-passed set")
    ap.add_argument("--alpha", type=float, default=DEFAULT_ALPHA,
                    help="significance level for the sign test (default %(default)s)")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    nulls = [(load_arm(a), load_arm(b)) for a, b in (args.null or [])]
    def _src(p):
        return os.path.normcase(os.path.realpath(p))

    # Labels are directory basenames, and two arms of one comparison can share one (an
    # off/on pair under two parents). A collision would key two arms to one slot, so it is
    # disambiguated here by walking up a directory rather than left to the refusal in gate().
    taken = {}

    def _label(p):
        parts = Path(os.path.normpath(p)).parts
        for n in range(1, len(parts) + 1):
            cand = "/".join(parts[-n:])
            if cand not in taken:
                taken[cand] = p
                return cand
        return os.path.normpath(p)

    l_off0, l_on0 = _label(args.off), _label(args.on)
    sources = {l_off0: _src(args.off), l_on0: _src(args.on)}
    replicate = None
    labels = {"off": l_off0, "on": l_on0}
    if args.replicate:
        r_off, r_on = args.replicate
        labels["off2"], labels["on2"] = _label(r_off), _label(r_on)
        sources[labels["off2"]], sources[labels["on2"]] = _src(r_off), _src(r_on)
        replicate = (load_arm(r_off), load_arm(r_on))
    for i, (a, b) in enumerate(args.null or []):
        sources["null%d.a" % i], sources["null%d.b" % i] = _src(a), _src(b)
    res = gate(load_arm(args.off), load_arm(args.on), nulls,
               history=[load_arm(d) for d in args.history], alpha=args.alpha,
               labels=labels, sources=sources, replicate=replicate)

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
    if res["replicate_supplied"]:
        st2 = res["sign_test_replicate_gating"]
        print("Sign test replicate %s -> %s (gating): %d/%d beat the band -> p=%s %s"
              % (res["labels"]["off2"], res["labels"]["on2"],
                 st2["wins_effect_beats_noise"], st2["questions"],
                 "n/a" if st2["p_two_sided"] is None else "%.4g" % st2["p_two_sided"],
                 "DISTINGUISHABLE" if st2["significant"] else "not distinguishable"))
        print("Replication table (%d question(s) tested in both replicates):"
              % res["replication_n"])
        for t in res["replication"]:
            print("    %-40s %+.2f / %+.2f  %s%s%s"
                  % (t["id"][:40], t["effect_a"], t["effect_b"],
                     "REPLICATED" if t["direction_replicated"] else "did not replicate",
                     "  past the band" if t["beats_noise_either"] else "",
                     "   NOT GATING" if t["non_gating"] else ""))
    print("EFFECT CLAUSE: %s%s" % (res["effect_clause"]["state"].upper().replace("_", " "),
                                   "" if res["replicate_supplied"] else
                                   "  (no replicate supplied; it decides nothing)"))
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
        print("    %-44s stable-failed in %s, stable-passed in %s"
              % (r["id"][:44], ", ".join(r.get("stable_failed_in") or ["?"]),
                 ", ".join(r["stable_passed_in"])))
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
