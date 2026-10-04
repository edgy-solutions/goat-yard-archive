"""Per-question diff of two eval arms, and the noise floor that bounds what a diff can claim.

    python evals/compare_arms.py ARM_A_DIR ARM_B_DIR [--floor N] [--label-a X --label-b Y]

Ruling 1 (2026-09-27) gated the ADR-0009 flag on ONE STABLE-PASS -> STABLE-FAIL flip. The same
run measured a 36-43% FLAKY rate, at which a 28-question set cannot detect a 2-question
difference. Chris's ordering item (a): "No arm comparison is reportable as a difference below
that floor." This script is how the floor is measured (run it on two IDENTICAL arms) and how it
is then applied (`--floor N` from that measurement).

The aggregate summary cannot answer this. `summary.json` reports one representative result per
question plus class COUNTS, and two arms can have identical counts with a different set of
questions in each class. So classes are recomputed here from each question's own `run_passes`,
which is the per-run ground truth.

What it refuses to do:
  - compare arms whose question sets differ (an id missing from one arm is not a 0);
  - compare arms whose recorded provider pin differs, or which were run unpinned, without
    saying so in the output -- temperature 0 is deterministic within an OpenRouter provider,
    not across two;
  - print a class-change count without the flip DIRECTION, since STABLE-PASS -> STABLE-FAIL is
    the gate and FLAKY <-> anything is not.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import statistics
import sys

from run_dir import is_question_file

SP, SF, FLAKY, NO_DATA = "STABLE-PASS", "STABLE-FAIL", "FLAKY", "NO-DATA"

# Questions that are MEASURED but do not decide the gate (ruling 1, 2026-09-27, Chris).
#
# The pinned OFF-vs-OFF floor pooled 6 runs per question across two arms with identical recorded
# configuration. Three questions came back near a coin flip, and no N rescues a p~0.5 item as a
# pass/fail gate: at p=0.5 the same question is STABLE-PASS, FLAKY and STABLE-FAIL on different
# days with nothing having changed. Including them means the gate fires on the coin, and a gate
# that fires on noise gets ignored, which is worse than not having one.
#
# They are still asked, still scored, and still counted in the pass rate and the class-change
# count. What they no longer do is contribute a STABLE-PASS <-> STABLE-FAIL flip. Every excluded
# flip is reported separately and raises a note, because an exclusion nobody sees is indistinguish-
# able from a gate that failed to fire.
#
# The exit condition is a DETERMINISTIC scorer for these three, not a bigger N. Until then the
# value here is a measurement, and the measurement is in
# docs/audits/RESULT_pinned_floor_laneA_20260927.md.
NON_GATING = {
    "john_baptist_001": "pooled 4/6 on the pinned floor pair (2026-09-27) -- p~0.5",
    "scapegoat_001": "pooled 4/6 on the pinned floor pair (2026-09-27) -- p~0.5",
    "real_imprecatory_psalms_001": "pooled 3/6 on the pinned floor pair (2026-09-27) -- p~0.5",
}

# Runs per question below which a pair is not classifiable (ruling 1). N=3 cannot discriminate a
# question at p~0.83 from a deterministic pass: 3/3 comes up about 58% of the time, which is the
# whole of the 10 class changes the floor pair recorded between two identical arms.
MIN_CLASSIFICATION_RUNS = 5

# `partial_match_sids` has three real states, not two. A response dict from a backend build that
# predates the field has no key at all -- which is a different fact from a response whose backend
# computed the field and found nothing (key present, value `[]`). This sentinel is how load_arm()
# tells "key absent" apart from "key present, value falsy" (None or []); dict.get's ordinary
# default cannot make that distinction.
_NO_PARTIAL_FIELD = object()

# The tri-state an arm's partial_match_sids can be in, once every question is considered:
#   NOT_REPORTED     - no scored response in the arm carries the key at all (pre-field backend)
#   [] (empty list)  - the key is present, and every value is empty (computed it, found nothing)
#   [qid, ...]       - the key is present and non-empty on at least one question
# A run from a pre-field backend and a run from a field-computing one must not compare equal on
# this line: NOT_REPORTED is not []. "Computed, and empty" and "never computed" are different
# facts about the measurement, not two spellings of the same one.
PARTIAL_NOT_REPORTED = "NOT-REPORTED-BY-THIS-BACKEND"


def fmt_partial(v) -> str:
    """Render one arm's partial_match_sids_nonempty value so the three states never look alike:
    not reported at all, reported-and-empty, reported-with-values."""
    if v == PARTIAL_NOT_REPORTED:
        return "NOT REPORTED (field absent from every response)"
    return v if v else "NONE (reported, empty)"


def classify(run_passes) -> str:
    """Stability class from the per-run pass list. Mirrors run_eval.classify_stability, but over
    the persisted `run_passes` rather than live QuestionResults."""
    ps = [p for p in (run_passes or []) if p is not None]
    if not ps:
        return NO_DATA
    if all(ps):
        return SP
    if not any(ps):
        return SF
    return FLAKY


def load_arm(d: str) -> dict:
    """{id: {...}} from an arm directory's per-question JSON, plus the arm's summary."""
    if not os.path.isdir(d):
        raise SystemExit(f"not a directory: {d}")
    qs = {}
    for name in sorted(os.listdir(d)):
        if not is_question_file(name):
            continue
        rec = json.load(io.open(os.path.join(d, name), encoding="utf-8"))
        score = rec.get("score") or {}
        resp = rec.get("response") or {}
        qid = score.get("id") or name[:-5]
        qs[qid] = {
            "class": classify(rec.get("run_passes")),
            "passes": sum(1 for p in (rec.get("run_passes") or []) if p),
            "runs": len(rec.get("run_passes") or []),
            "refusal_correct": score.get("refusal_correct"),
            "refused": resp.get("refused"),
            "expected_behavior": score.get("expected_behavior"),
            "answer_len": len(resp.get("answer") or ""),
            "partial_match_sids": resp.get("partial_match_sids", _NO_PARTIAL_FIELD),
        }
    summary_path = os.path.join(d, "summary.json")
    summary = (json.load(io.open(summary_path, encoding="utf-8"))
               if os.path.exists(summary_path) else {})
    if not qs:
        raise SystemExit(f"no per-question JSON in {d}; nothing to compare")
    return {"questions": qs, "summary": summary, "dir": d}


def provider_pin_of(arm: dict):
    """The pin as the arm RECORDED it, from summary.json or, failing that, the warmup block."""
    s = arm["summary"]
    if "openrouter_provider_pin" in s:
        return s["openrouter_provider_pin"]
    return (s.get("warmup") or {}).get("openrouter_provider_pin")


# The fields of a per-call answer_lm record that make two arms a different measurement rather
# than the same measurement twice. `provider_served_source` and `runs` are deliberately excluded:
# reading the provider off a different field is not a difference in what served the arm.
ANSWER_LM_COMPARED = ("client", "model_returned", "temperature_on_the_wire", "provider_served")


def answer_lm_config_of(arm: dict) -> list:
    """The distinct serving configurations the arm RECORDED, as sorted comparable strings.

    Empty when the arm predates the field. Empty is not "the same as the other arm": an arm that
    recorded nothing cannot be asserted to match one that did, which is why the caller reports
    the absence rather than a silent equality.
    """
    rows = ((arm["summary"].get("answer_lm") or {}).get("distinct") or [])
    return sorted(json.dumps({k: row.get(k) for k in ANSWER_LM_COMPARED},
                             sort_keys=True, default=str) for row in rows)


def compare(a: dict, b: dict, label_a: str, label_b: str, floor=None) -> dict:
    ids_a, ids_b = set(a["questions"]), set(b["questions"])
    if ids_a != ids_b:
        only_a, only_b = sorted(ids_a - ids_b), sorted(ids_b - ids_a)
        raise SystemExit(
            f"the arms do not share a question set, so no per-question diff is meaningful.\n"
            f"  only in {label_a}: {only_a}\n  only in {label_b}: {only_b}\n"
            f"A missing question is not a failure and must not be scored as one.")

    pin_a, pin_b = provider_pin_of(a), provider_pin_of(b)
    notes = []
    if pin_a != pin_b:
        notes.append(f"PROVIDER PIN DIFFERS: {label_a}={pin_a!r} {label_b}={pin_b!r}. Any delta "
                     f"below may be a provider difference, not the change under test.")
    elif not pin_a:
        notes.append("BOTH ARMS UNPINNED: deepseek-chat has providers at different "
                     "quantizations. A small delta is not attributable.")

    # The pin above is what each arm was CONFIGURED with. This is what actually served it, per
    # call. They can disagree, and one axis in particular did so invisibly for every OFF-vs-ON
    # arm ever run: the BAML path sends temperature 0, the DSPy path sends no temperature field
    # at all. An arm pair that differs on this is not one measurement of one change.
    lm_a, lm_b = answer_lm_config_of(a), answer_lm_config_of(b)
    if not lm_a or not lm_b:
        which = [lbl for lbl, v in ((label_a, lm_a), (label_b, lm_b)) if not v]
        notes.append(f"NO PER-CALL ANSWER-LM RECORD in {', '.join(which)}: that arm cannot state "
                     f"what model, temperature or provider served it, so the pair is not a "
                     f"pinned comparison.")
    elif lm_a != lm_b:
        notes.append(f"ANSWER-LM CONFIG DIFFERS: {label_a}={lm_a} {label_b}={lm_b}. The arms "
                     f"differ in what served them, not only in the change under test.")

    # Runs actually performed, per arm. A pair classified below MIN_CLASSIFICATION_RUNS is not a
    # classification: it is the floor being read as a result, which is the fault ruling 1 names.
    def max_runs(arm):
        vals = [v.get("runs") or 0 for v in arm["questions"].values()]
        return max(vals) if vals else 0

    runs_a, runs_b = max_runs(a), max_runs(b)
    if min(runs_a, runs_b) < MIN_CLASSIFICATION_RUNS:
        notes.append(f"UNDER-POWERED CLASSIFICATION: {label_a} ran {runs_a} time(s) per question "
                     f"and {label_b} ran {runs_b}, below the N={MIN_CLASSIFICATION_RUNS} ruling 1 "
                     f"requires. At N=3 a question at p~0.83 shows 3/3 about 58% of the time, so a "
                     f"class change here may be the floor rather than a difference.")

    changes, flips, excluded_flips, same = [], [], [], 0
    for qid in sorted(ids_a):
        ca, cb = a["questions"][qid]["class"], b["questions"][qid]["class"]
        if ca == cb:
            same += 1
            continue
        row = {"id": qid, label_a: ca, label_b: cb,
               "passes": f"{a['questions'][qid]['passes']}/{a['questions'][qid]['runs']} -> "
                         f"{b['questions'][qid]['passes']}/{b['questions'][qid]['runs']}"}
        changes.append(row)
        if {ca, cb} == {SP, SF}:
            # A flip on a non-gating question is recorded and reported -- just not gating.
            if qid in NON_GATING:
                row = dict(row, non_gating_reason=NON_GATING[qid])
                excluded_flips.append(row)
            else:
                flips.append(row)
    if excluded_flips:
        notes.append("FLIP(S) EXCLUDED FROM THE GATE: "
                     + "; ".join(r["id"] + " (" + r["non_gating_reason"] + ")"
                                 for r in excluded_flips)
                     + ". These are real class changes on questions ruling 1 pulled from the gate "
                       "pending a deterministic scorer. The gate count below does NOT include them.")

    def refusal_wrong(arm):
        # NO-DATA is excluded deliberately. A question whose runs all errored has no answer to
        # judge, and `refusal_correct` is False by default on a missing response - so counting it
        # here made the 5 HTTP-500 questions of off_20260927c look like five refusal regressions.
        return {q for q, v in arm["questions"].items()
                if v["refusal_correct"] is False and v["class"] != NO_DATA}

    def median_len(arm):
        vals = [v["answer_len"] for v in arm["questions"].values() if v["answer_len"]]
        return statistics.median(vals) if vals else 0

    def nonempty_partial(arm):
        """qids with a non-empty partial_match_sids, or PARTIAL_NOT_REPORTED if the field is
        absent from every scored response in the arm (see the module-level comment)."""
        values = [v["partial_match_sids"] for v in arm["questions"].values()]
        if all(v is _NO_PARTIAL_FIELD for v in values):
            return PARTIAL_NOT_REPORTED
        return sorted(q for q, v in arm["questions"].items()
                      if v["partial_match_sids"] not in (_NO_PARTIAL_FIELD, None)
                      and v["partial_match_sids"])

    ra, rb = refusal_wrong(a), refusal_wrong(b)
    out = {
        "labels": [label_a, label_b],
        "provider_pin": {label_a: pin_a, label_b: pin_b},
        "answer_lm_config": {label_a: lm_a, label_b: lm_b},
        "notes": notes,
        "questions": len(ids_a),
        "class_changes": changes,
        "class_changes_n": len(changes),
        "class_unchanged_n": same,
        "stable_flips": flips,
        "stable_flips_n": len(flips),
        "flips_excluded_from_gate": excluded_flips,
        "flips_excluded_from_gate_n": len(excluded_flips),
        # Which exclusions were in force for THIS pair, so a reader can tell an empty excluded list
        # apart from an exclusion set that was never applied.
        "non_gating_questions": sorted(q for q in ids_a if q in NON_GATING),
        "runs_per_question": {label_a: runs_a, label_b: runs_b},
        "min_classification_runs": MIN_CLASSIFICATION_RUNS,
        "passed": {label_a: sum(1 for v in a["questions"].values() if v["class"] == SP),
                   label_b: sum(1 for v in b["questions"].values() if v["class"] == SP)},
        "refusal_wrong": {label_a: sorted(ra), label_b: sorted(rb)},
        "refusal_wrong_symmetric_difference": sorted(ra ^ rb),
        "median_answer_len": {label_a: median_len(a), label_b: median_len(b)},
        "partial_match_sids_nonempty": {label_a: nonempty_partial(a), label_b: nonempty_partial(b)},
    }
    if floor is not None:
        out["floor"] = floor
        out["above_floor"] = len(changes) > floor
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("arm_a")
    ap.add_argument("arm_b")
    ap.add_argument("--label-a", default=None)
    ap.add_argument("--label-b", default=None)
    ap.add_argument("--floor", type=int, default=None,
                    help="class-change count measured between two IDENTICAL arms. A diff at or "
                         "below it is not reportable as a difference.")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    la = args.label_a or os.path.basename(os.path.normpath(args.arm_a))
    lb = args.label_b or os.path.basename(os.path.normpath(args.arm_b))
    if la == lb:
        la, lb = la + "(a)", lb + "(b)"
    res = compare(load_arm(args.arm_a), load_arm(args.arm_b), la, lb, args.floor)

    print("=" * 70)
    print(f"ARM DIFF  {la}  vs  {lb}      {res['questions']} questions")
    print("=" * 70)
    for n in res["notes"]:
        print(f"  !! {n}")
    print(f"Provider pin   : {la}={res['provider_pin'][la]!r}")
    print(f"                 {lb}={res['provider_pin'][lb]!r}")
    print(f"STABLE-PASS    : {res['passed'][la]} -> {res['passed'][lb]}")
    print(f"Class changes  : {res['class_changes_n']} of {res['questions']} "
          f"({res['class_unchanged_n']} unchanged)")
    print(f"STABLE-PASS <-> STABLE-FAIL flips : {res['stable_flips_n']}  <- the gate")
    print(f"Runs per question : {la}={res['runs_per_question'][la]} {lb}="
          f"{res['runs_per_question'][lb]}  (ruling 1 requires "
          f"{res['min_classification_runs']})")
    if res["non_gating_questions"]:
        print(f"Non-gating questions in this pair : {', '.join(res['non_gating_questions'])}")
    if res["flips_excluded_from_gate"]:
        print(f"Flips EXCLUDED from the gate : {res['flips_excluded_from_gate_n']}")
        for r in res["flips_excluded_from_gate"]:
            print(f"    {r['id']}  {r[la]} -> {r[lb]}  {r['passes']}  ({r['non_gating_reason']})")
    if res["class_changes"]:
        print("\n  question                                      %-12s %-12s  runs" % (la[:12], lb[:12]))
        for r in res["class_changes"]:
            mark = ("  <== FLIP" if r in res["stable_flips"]
                    else "  <== flip, NOT GATING" if r["id"] in NON_GATING else "")
            print("  %-44s %-12s %-12s  %s%s" % (r["id"][:44], r[la], r[lb], r["passes"], mark))
    print(f"\nRefusal-incorrect set difference : {res['refusal_wrong_symmetric_difference'] or 'none'}")
    print(f"  {la}: {res['refusal_wrong'][la] or 'none'}")
    print(f"  {lb}: {res['refusal_wrong'][lb] or 'none'}")
    print(f"Median answer length : {res['median_answer_len'][la]} -> {res['median_answer_len'][lb]}")
    print(f"partial_match_sids non-empty : {la}={fmt_partial(res['partial_match_sids_nonempty'][la])}"
          f"  {lb}={fmt_partial(res['partial_match_sids_nonempty'][lb])}")
    if "floor" in res:
        verdict = "ABOVE the floor" if res["above_floor"] else "AT OR BELOW the floor - NOT REPORTABLE"
        print(f"\nFloor {res['floor']} class changes: {res['class_changes_n']} observed -> {verdict}")
    if args.json_out:
        io.open(args.json_out, "w", encoding="utf-8").write(
            json.dumps(res, indent=2, sort_keys=True))
        print(f"\nWritten: {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
