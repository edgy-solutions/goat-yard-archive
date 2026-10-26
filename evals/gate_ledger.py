#!/usr/bin/env python
"""Recompute the pass ledger and the branch census for gate arms, with IDS.

Why this exists rather than reading `summary.json`: `summary.passed` keeps ONE
draw per question (the last run -- `results.append(last_r)`), and a
one-draw-per-item estimator manufactures regressions out of flake. The lock
fixes the estimator as a STABLE-PASS -> STABLE-FAIL flip, which needs the
per-draw `run_passes` array and, crucially, the question IDS -- `summary.json`
stores stable counts, and a count is not a set. You cannot subtract two counts
and learn which question moved.

Two limitations, stated here because the numbers are misleading without them:

1. `must_not_cite_violated` is recorded only for the LAST draw (the runner
   keeps one score object per question). A violation on draw 1 or 2 still
   costs that draw its `overall_pass`, so it cannot hide from the ledger
   entirely -- it appears as a non-passing draw -- but its REASON is not
   recoverable from the stored record. So `must_not_cite` here is a
   last-draw-fidelity signal, and any non-STABLE-PASS question in the ON arm
   has to be read as "a violation is not excluded on the unstored draws".

2. `raw_query_no_entities` is a UNION of two causes (expansion succeeded and
   was discarded; expansion errored and retrieval fell to the floor). This
   tool reports the branch population, never the cause. Attribution is a
   separate debug pass.

Usage:
    gate_ledger.py ARM_DIR [ARM_DIR ...]      # per-arm ledger
    gate_ledger.py --compare BASE_DIR OTHER_DIR
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

NON_QUESTION = {"summary.json", "arm_header.json", "RUN_ABORTED.json"}


def load_arm(d: Path) -> dict:
    """Read one arm directory into a ledger. Raises if it is not scorable."""
    if (d / "RUN_ABORTED.json").exists():
        raise SystemExit("%s holds RUN_ABORTED.json -- aborted, not scorable" % d)
    if (d / "VOID.md").exists():
        raise SystemExit("%s is marked VOID -- see its VOID.md" % d)

    header = {}
    hp = d / "arm_header.json"
    if hp.exists():
        header = json.loads(hp.read_text(encoding="utf-8"))
    if header.get("valid") is False:
        raise SystemExit("%s header says valid=false -- unscorable arm" % d)

    stable_pass, stable_fail, flaky = set(), set(), set()
    no_draws, violations, branch, branch_ids = set(), set(), {}, {}
    n_draws = set()

    for f in sorted(d.glob("*.json")):
        if f.name in NON_QUESTION:
            continue
        rec = json.loads(f.read_text(encoding="utf-8"))
        qid = (rec.get("question") or {}).get("id") or f.stem
        passes = rec.get("run_passes")
        if not passes:
            # A question with no draws is neither a pass nor a fail. Folding it
            # into either one would be inventing a result.
            no_draws.add(qid)
            continue
        n_draws.add(len(passes))
        if all(passes):
            stable_pass.add(qid)
        elif not any(passes):
            stable_fail.add(qid)
        else:
            flaky.add(qid)

        if (rec.get("score") or {}).get("must_not_cite_violated"):
            violations.add(qid)

        for obs in rec.get("expansion_observations") or []:
            st = obs.get("state", "missing_observation")
            branch[st] = branch.get(st, 0) + 1
            branch_ids.setdefault(st, set()).add(qid)

    return {
        "dir": d,
        "header": header,
        "stable_pass": stable_pass,
        "stable_fail": stable_fail,
        "flaky": flaky,
        "no_draws": no_draws,
        "violations": violations,
        "branch": branch,
        "branch_ids": branch_ids,
        "n_questions": len(stable_pass) + len(stable_fail) + len(flaky) + len(no_draws),
        "draw_counts": sorted(n_draws),
    }


def print_arm(a: dict) -> None:
    h = a["header"]
    print("=" * 72)
    print("ARM %s" % a["dir"].name)
    if h:
        # Provenance lives under "realized" -- the values the launcher READ off
        # the live pod, not the ones the arm asked for. A record of the request
        # where the consumer needs the realization misleads the reader.
        r = h.get("realized") or {}
        print("  flag=%s pod=%s restarts=%s" % (
            r.get("pod_spec_flag"), r.get("pod"), r.get("restart_count")))
        print("  valid=%s provisional=%s git=%s%s" % (
            h.get("valid"), h.get("provisional"), (h.get("git_head") or "?")[:12],
            " UNEXPLAINED-DIRT" if h.get("git_dirty_unexplained") else ""))
    print("  questions      : %d   draws/question: %s"
          % (a["n_questions"], a["draw_counts"] or "none"))
    print("  STABLE-PASS    : %d" % len(a["stable_pass"]))
    print("  STABLE-FAIL    : %d" % len(a["stable_fail"]))
    print("  FLAKY          : %d  %s" % (len(a["flaky"]), sorted(a["flaky"])))
    if a["no_draws"]:
        print("  NO DRAWS       : %d  %s" % (len(a["no_draws"]), sorted(a["no_draws"])))
    print("  must_not_cite  : %d  %s  (LAST DRAW ONLY -- see module docstring)"
          % (len(a["violations"]), sorted(a["violations"])))
    print("  branch census (per draw, union of causes -- not an attribution):")
    for st in sorted(a["branch"], key=lambda s: -a["branch"][st if False else s]):
        print("    %-26s %3d draws over %2d questions"
              % (st, a["branch"][st], len(a["branch_ids"][st])))
    rq = sorted(a["branch_ids"].get("raw_query_no_entities", ()))
    print("  raw_query_no_entities ids: %s" % (rq or "none"))


def print_compare(base: dict, other: dict) -> None:
    """The estimator the lock fixed: STABLE-PASS -> STABLE-FAIL flips, by id."""
    print("=" * 72)
    print("COMPARE  base=%s  other=%s" % (base["dir"].name, other["dir"].name))
    regressions = sorted(base["stable_pass"] & other["stable_fail"])
    improvements = sorted(base["stable_fail"] & other["stable_pass"])
    destabilized = sorted(base["stable_pass"] & other["flaky"])
    stabilized = sorted(base["flaky"] & other["stable_pass"])
    print("  STABLE-PASS -> STABLE-FAIL : %d  %s" % (len(regressions), regressions))
    print("  STABLE-FAIL -> STABLE-PASS : %d  %s" % (len(improvements), improvements))
    print("  STABLE-PASS -> FLAKY       : %d  %s" % (len(destabilized), destabilized))
    print("  FLAKY -> STABLE-PASS       : %d  %s" % (len(stabilized), stabilized))
    hard = sorted(set(base["stable_pass"] | base["stable_fail"] | base["flaky"]) ^
                  set(other["stable_pass"] | other["stable_fail"] | other["flaky"]))
    if hard:
        print("  !! question sets differ between arms: %s" % hard)
        print("     The population was fixed before the run; this must be empty.")
    print("  TOTAL STABLE FLIPS (either direction): %d"
          % (len(regressions) + len(improvements)))
    bs = base["branch_ids"].get("raw_query_no_entities", set())
    os_ = other["branch_ids"].get("raw_query_no_entities", set())
    print("  discard-branch id set: base=%d other=%d  symmetric difference=%s"
          % (len(bs), len(os_), sorted(bs ^ os_) or "none"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+", type=Path)
    ap.add_argument("--compare", action="store_true",
                    help="treat the first two dirs as base and other")
    args = ap.parse_args(argv)

    arms = [load_arm(d) for d in args.dirs]
    for a in arms:
        print_arm(a)
    if args.compare:
        if len(arms) != 2:
            raise SystemExit("--compare takes exactly 2 arm dirs")
        print_compare(arms[0], arms[1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
