"""Write the methods lock for the blank-crop control's SECOND run (attempt 2).

Lane B.  All page numbers are FILE pages (printed = file - 88).

Why this file exists.  GATE 0S refuses a blank-crop run at attempt >= 2 with "the blank-crop
control path has no methods lock registered".  That refusal is correct and it is new: GATE 0S used
to be hard-wired to the read path's lock, payload digest and approval record, so a blank replicate
could only ever have run under a lock that misdescribed it.  This writes the lock that was missing.

The lock is content-addressed by its own body: strip `self_sha16`, canonical JSON, UTF-8 bytes,
`ensure_ascii=False`.  That is the recipe GATE 0S re-implements from this sentence, and the point
is that a prediction cannot be edited after the numbers land.

Run it with --write to emit; without, it prints the digest and the body and touches nothing.
"""
import argparse
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score45_run as S                    # for canon / sha16_bytes / the pinned constants

OUT_DIR = S.A
BASELINE = "c957403401a9f865"
PAYLOAD = S.BLANK_PAYLOAD_DIGEST


def body():
    return {
        "lock": "blank-crop control, attempt 2: does the no-pixel floor replicate?",
        "written": "2026-11-14",
        "by": "Lane B / session 50612c81",
        "page_convention": "FILE pages (printed = file - 88)",

        "run": {
            "attempt": 2,
            "mode": "blank-crop control",
            "payload_identity_digest_required": PAYLOAD,
            "baseline_run": BASELINE,
            "baseline_was_clean": True,
            "scored_against": S.BLANK_PRED_SHA,
            "cut_digest": S.BLANK_CUT_DIGEST,
            "sheet_digest": S.BLANK_SHEET_DIGEST,
            "endpoint": "openrouter.ai, the two arms of the scored run, one draw per item",
            "prediction_lock_not_repointed":
                "PREDICTIONS_blank45_%s.json keeps its registered numbers.  Repointing it would "
                "make this a new experiment instead of a replicate, and the numbers it registers "
                "are predictions about READING pixels, which this run does not do."
                % S.BLANK_PRED_SHA,
        },

        # ------------------------------------------------------------------ the question
        "question": {
            "asks":
                "Run 1 of this control found the no-pixel floor at ZERO in three of four cells "
                "and at ONE `exact` out of 40 in the fourth (qwen/qwen3.7-plus|context, which "
                "also answered at all without pixels 5 times out of 40).  Does that single "
                "`exact` replicate, and does it land on the SAME span?",
            "why_it_matters":
                "The memo amendment withdrawing channel 2 cites this control.  A floor measured "
                "once, at one draw per span, is a floor measured by a one-draw-per-item "
                "estimator, and this lane has already been bitten by one of those manufacturing "
                "a regression out of flake.  A single success cannot retract an intermittent "
                "failure, and a single failure cannot establish one.",
            "what_this_is_NOT":
                "Not a re-score of run 6a2292bdb14d3c43 and not a re-score of run %s.  No stored "
                "row is touched and no sealed page is opened.  Both runs keep their own numbers; "
                "this adds a second draw beside the first." % BASELINE,
        },

        # ------------------------------------------------------------------ the population
        "population": {
            "named_before_the_run": True,
            "calls": 162,
            "composition": "2 arms x (41 bare + 40 context)",
            "cells": [
                "anthropic/claude-opus-5.5|bare", "anthropic/claude-opus-5.5|context",
                "qwen/qwen3.7-plus|bare", "qwen/qwen3.7-plus|context",
            ],
            "refusal_set_precondition": {
                "law_8_refused": ["p190:n0", "p493:n3", "p594:n0", "p803:n0"],
                "n": 4,
                "of": 45,
                "rule":
                    "If that set moves, the call count moves, the registered denominators below "
                    "are no longer the denominators, and THE RUN ABORTS ON THE COUNT rather than "
                    "running.  That is correct behaviour, not a fault to work around: a refusal "
                    "set that moves can empty a stratum, and this lane has already published "
                    "levels whose strata scored zero rows for exactly that reason.  The fix is to "
                    "re-measure free with --dry-run and write a NEW lock, never to relax a pin.",
            },
            "pixels":
                "45 uniform-255 crops, cut %s, contact sheet %s, approved by Chris on 2026-11-08. "
                "The pixels carry nothing, so the disclosure is unchanged from run 1 and the only "
                "new thing is the money and the attempt number."
                % (S.BLANK_CUT_DIGEST, S.BLANK_SHEET_DIGEST),
        },

        # ------------------------------------------------------------------ the baseline
        # Transcribed from BLANK45_<baseline>.json's own blank_control_evaluation, so the
        # comparison below is against numbers that were written down before this lock existed.
        "baseline_measured": {
            "anthropic/claude-opus-5.5|bare":
                {"n": 41, "abstain": 41, "answered_without_pixels": 0, "exact_floor": 0},
            "anthropic/claude-opus-5.5|context":
                {"n": 40, "abstain": 40, "answered_without_pixels": 0, "exact_floor": 0},
            "qwen/qwen3.7-plus|bare":
                {"n": 41, "abstain": 41, "answered_without_pixels": 0, "exact_floor": 0},
            "qwen/qwen3.7-plus|context":
                {"n": 40, "abstain": 35, "answered_without_pixels": 5, "exact_floor": 1},
            "no_pixel_recoverable_ids": [],
            "no_pixel_recoverable_status_in_run_1":
                "PROVISIONAL -- one draw per span at temperature 0; a span that lands here once "
                "has not been shown to land there reliably",
        },

        # ------------------------------------------------------------------ the decision rule
        "decision_rule": {
            "primary":
                "Per cell, compare answered_without_pixels and exact_floor against the baseline "
                "above.  The verdict is REPLICATES / DOES NOT REPLICATE / UNSCOREABLE per cell, "
                "and there is no pooled verdict: a pooled delta that lands while its rows "
                "disagree is a hit by cancellation.",
            "the_one_item_ratchet":
                "At n=1 the honest unit is the ITEM, not the rate.  The claim that gets reported "
                "is whether the SAME span_id answers without pixels in both runs.  Two different "
                "spans answering once each is NOT a replicated floor; it is a floor of 1 drawn "
                "from a population of 2, and it is reported that way.",
            "direction_must_repeat":
                "A sign that does not repeat is not an effect.  If qwen|context's exact_floor is "
                "1 in run 1 and 0 in run 2, the floor is NOT 'about 1' -- it is unresolved at "
                "this n, and that is the finding.",
            "no_reformulation":
                "The rule above is fixed by this lock's hash.  If the result is awkward, the "
                "result is reported awkward.  Reformulating a rule to rescue a verdict is a move "
                "this lane has made before and will not make again.",
        },

        "falsifiers": [
            {"id": "F1",
             "fires_if": "any of the three cells that scored 0/0 in run 1 scores "
                         "answered_without_pixels > 2 in run 2",
             "then": "the run-1 floor of zero in that cell is WITHDRAWN as a floor; it becomes "
                     "one draw that happened to come out clean, and the memo amendment's citation "
                     "of this control must be narrowed to the cell that still holds."},
            {"id": "F2",
             "fires_if": "qwen|context's answered_without_pixels is 0 in run 2",
             "then": "the 5-of-40 in run 1 is not a stable property of that cell either, and the "
                     "control's own variability is the headline, not the floor."},
            {"id": "F3",
             "fires_if": "any cell's n differs from the registered n above",
             "then": "the run is UNSCOREABLE against this lock.  Do not rescore against a "
                     "different denominator; write a new lock."},
        ],

        "scoreability_preconditions": [
            {"id": "P1",
             "precondition": "A STABILITY claim about a cell needs that cell to have produced a "
                             "non-abstention in at least one of the two runs.",
             "why": "A falsifier phrased over variation fires on perfect stability too: a cell "
                    "that abstains 41/41 twice gives 0 == 0 and scores nothing.  Three of four "
                    "cells are in exactly that state, so for them this run can only CORROBORATE "
                    "a floor of zero, never test its stability.  Said here, before the run, so "
                    "the report cannot later present 0 == 0 as a confirmation of anything."},
            {"id": "P2",
             "precondition": "The two runs must be compared cell-by-cell, never arm-by-arm "
                             "pooled across channels.",
             "why": "The channel is the variable under test.  Pooling it away is the one "
                    "arrangement that cannot see the effect."},
            {"id": "P3",
             "precondition": "This run is its own second draw; it is not a null for any read-path "
                             "effect.",
             "why": "Never bound an effect with a null that shares one of its arms -- it biases "
                    "toward silence."},
        ],

        "run_level_fault": {
            "rule":
                "A 429, or %d consecutive dead items, or a `done: false` as the first reply of a "
                "load, invalidates the whole run: abort, write nothing, rerun from the top.  "
                "Never splice.  A faulted head makes every later item UNMEASURED, not fine."
                % S.CONSECUTIVE_FAIL_ABORT,
            "clean_run_rule":
                "The run is clean only if git_state() over both repos is clean at start AND at "
                "end AND identical.  A provisional run cannot be cited in an ADR or a tier "
                "change, and it is recorded provisional rather than quietly used.",
        },

        "check_count_gates": {
            "precall":
                "GATE 0P pins the header-scoped check count BEFORE the first paid call: %r for "
                "this mode with the approval record on disk, measured free by --dry-run.  A "
                "header-scoped guard is no longer discovered by spending."
                % (S.EXPECTED_CHECKS_BLANK_PRECALL.get(True),),
            "per_call":
                "GATE 0Q divides the call loop's check count by the call count and refuses a "
                "remainder, so a stepped reasoning ladder or a per-call assertion lost on one "
                "path surfaces as a named defect instead of an off-by-n total.",
            "total":
                "EXPECTED_CHECKS_BLANK is %d and is still enforced in the write block, after the "
                "spend.  It is NOT re-derived by this lock, because no honest offline derivation "
                "exists: the clean run %s persisted no check count at all, so '1684 was measured' "
                "survives only as a comment.  This run is the one that measures the three terms "
                "and persists them, after which the total decomposes and stops being opaque.  If "
                "it fires, the decomposition names which term moved and GATE 0P has already "
                "cleared the pre-call term for free." % (S.EXPECTED_CHECKS_BLANK, BASELINE),
        },

        "what_this_cannot_settle": [
            "Whether the context channel's read-path gains are recall rather than reading.  This "
            "control puts a FLOOR under them; it does not attribute them.",
            "Anything about the three cells that abstained completely in run 1 beyond "
            "corroborating a floor of zero -- see precondition P1.",
            "Whether a span that answers without pixels would answer again on a third draw.  Two "
            "draws distinguish 'never' from 'sometimes'; they do not measure a rate.",
            "The read run's four rates.  They keep their measured values and gain a floor; this "
            "run does not rescore them.",
        ],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="emit the lock; default is to print it")
    a = ap.parse_args()

    b = body()
    dig = S.sha16_bytes(S.canon(b).encode("utf-8"))
    rec = dict(b, self_sha16=dig)
    # The gate recomputes from the body with self_sha16 stripped, so prove here that the record we
    # are about to write satisfies the gate's own recipe -- not that our two lines agree.
    back = {k: v for k, v in rec.items() if k != "self_sha16"}
    assert S.sha16_bytes(S.canon(back).encode("utf-8")) == dig, "the recipe does not round-trip"

    out = OUT_DIR / ("PREDICTIONS_blank45_replicate_%s.json" % dig)
    print("self_sha16: %s" % dig)
    print("path:       %s" % out)
    print("pin it:     SPEND_MODES['blank']['lock_sha'] = %r" % dig)
    if not a.write:
        print("\n-- not written (pass --write).  Body follows --")
        print(json.dumps(rec, ensure_ascii=False, indent=1))
        return 0
    if out.exists():
        print("REFUSED: %s already exists.  A lock is content-addressed; identical bytes mean "
              "nothing to do, and different bytes would be a different file." % out.name)
        return 0
    io.open(out, "w", encoding="utf-8", newline="\n").write(
        json.dumps(rec, ensure_ascii=False, indent=1) + "\n")
    print("WROTE %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
