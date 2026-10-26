# -*- coding: utf-8 -*-
u"""Born-test for the law-8 send gate in score45_run (Chris, ruling 1 of 2026-10-25).

*"Wire refuse_at_send into score45_run with on_refused='record' and refused_records() written beside
the read rows; born-test: the four refused ids are recorded, none sent."*

Both halves are tested, and the second one twice: the refused spans are absent from the REAL
payloads that build_payloads produces, and the gate inside `gate_counts` raises when a refused span
is planted in a payload list that still has the right counts.  Those are two different nets -- the
plan filter and the leak check -- and a test that only exercised the filter could not tell whether
the leak check works at all.

The suite asserts its own check COUNT: an exception in a hand-rolled suite ends the run silently,
and this lane has lost 40 assertions that way twice.

ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import score45_run as S                      # noqa: E402
import send_refusal as SR                    # noqa: E402

AGREED_REFUSED = ["p190:n0", "p493:n3", "p594:n0", "p803:n0"]

N = 0
FAILED = []


def ok(cond, msg):
    global N
    N += 1
    if cond:
        print("  ok    %s" % msg)
    else:
        print("  FAIL  %s" % msg)
        FAILED.append(msg)


def raises(fn, exc, msg):
    try:
        fn()
    except exc:
        ok(True, msg + " -- RAISES")
        return
    except Exception as e:                                                   # pragma: no cover
        ok(False, msg + " -- raised the WRONG type: %r" % (e,))
        return
    ok(False, msg + " -- NO RAISE")


def synth_payloads(sheet, sendable):
    """Payload dicts with only the fields gate_counts reads.  Deliberately not build_payloads: this
    half of the suite needs to control the counts exactly, and the real builder is exercised below."""
    allow = set(sendable)
    out = []
    for arm in S.ARMS:
        for ch in S.CHANNELS:
            for r in sheet["rows"]:
                if r["span_id"] not in allow:
                    continue
                if ch == "context" and r["ch2_state"] != "present":
                    continue
                out.append({"arm": arm, "channel": ch, "row": r,
                            "request_sha16": "%s|%s|%s" % (arm, ch, r["span_id"])})
    return out


def main():
    print("ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).")
    sheet, _pred = S.load_inputs()
    ids = [r["span_id"] for r in sheet["rows"]]
    ok(len(ids) == 45, "the sheet is the 45-span population")

    # ---- the sidecar
    ok(S.SIDECAR.exists(), "the send-flag sidecar exists (span_send_flags_build.py built it)")
    flags = SR.load_span_flags(str(S.SIDECAR))
    ok(len(flags) == 74, "the sidecar covers all 74 truth-set spans, not just the 45 being sent")
    side = json.loads(S.SIDECAR.read_text(encoding="utf-8"))
    bc = side["basis_counts"]
    ok(bc["partial_in_crop"] == {"measured": 20, "defaulted": 54},
       "partial_in_crop is MEASURED on 20 and DEFAULTED on 54 -- the refused set is a floor")
    ok(bc["box_fault"] == {"measured": 11, "unverified": 63},
       "box_fault is measured on 11 and unverified on 63")
    ok(len(side["counts"]["box_fault"]) == 11 and "p92:n1" in side["counts"]["box_fault"],
       "11 box_fault spans over the 74, p92:n1 (the wrong-line crop) among them")

    # ---- the plan: exactly the four, and WHY each one
    plan = SR.refuse_at_send(ids, flags, on_refused="record")
    ok(sorted(plan.refused) == AGREED_REFUSED,
       "the refused set is the four agreed with A2: %s" % ", ".join(AGREED_REFUSED))
    ok(plan.report["n"] == 41 and plan.report["n_refused"] == 4 and plan.report["n_population"] == 45,
       "41 sendable + 4 refused = the 45-span population")
    # `plan.refused` holds TUPLES (refusal_reason returns one) while `report["refused"]` holds
    # lists for JSON.  Both are checked, so neither shape can drift unnoticed.
    ok(list(plan.refused["p190:n0"]) == ["partial_in_crop"],
       "p190:n0 is refused on partial_in_crop alone (pass-2 disposition)")
    ok(plan.report["refused"]["p190:n0"] == ["partial_in_crop"],
       "p190:n0's reason survives into the JSON report as a list")
    for sid in ("p493:n3", "p594:n0", "p803:n0"):
        ok(list(plan.refused[sid]) == ["box_fault", "partial_in_crop"],
           "%s is refused on BOTH box_fault and partial_in_crop (pass-3 record)" % sid)

    # ---- "are recorded"
    recs = list(plan.refused_records())
    ok(len(recs) == 4, "four refused records, one per refused span")
    ok(all(r["class_primary"] == SR.REFUSAL_CLASS for r in recs),
       "every refused record is classed `%s`" % SR.REFUSAL_CLASS)
    ok(all(r["reached_wire"] is False for r in recs),
       "every refused record says reached_wire false -- `False`, not falsy")
    ok(sorted(r["span_id"] for r in recs) == AGREED_REFUSED, "the records name the four spans")
    ok(all(r["refused"] for r in recs), "every refused record carries its reasons, not just a class")

    # ---- "none sent", net 1: the production plan filter
    calls = S.plan_calls(sheet, plan.sendable)
    planned = {r["span_id"] for _a, _c, r in calls}
    ok(not (planned & set(plan.refused)), "no refused span is in a planned call")
    ok(len(calls) == 162, "162 calls planned, not the ungated 178")
    ok(S.UNGATED_CALLS == 178, "the ungated population is still recorded as 178")
    ok(S.EXPECTED_CALLS is None,
       "EXPECTED_CALLS is unpinned -- the count is derived from the plan, not a constant")
    for arm in S.ARMS:
        ok(sum(1 for a, c, _r in calls if a == arm and c == "bare") == 41, "%s: 41 bare" % arm)
        ok(sum(1 for a, c, _r in calls if a == arm and c == "context") == 40, "%s: 40 ctx" % arm)

    # ---- "none sent", net 2: the leak check inside gate_counts, proved by mutation.
    # Counts stay right and one sendable row is swapped for a refused one, so only the leak check can
    # catch it.  Without this, a passing suite would say nothing about whether that check works.
    good = synth_payloads(sheet, plan.sendable)
    ok(len(good) == 162, "the synthetic payload list matches the planned count")
    S.gate_counts(good, sheet, plan)
    ok(True, "gate_counts accepts the gated plan")
    byid = {r["span_id"]: r for r in sheet["rows"]}
    leaked = list(good)
    for i, p in enumerate(leaked):
        if p["channel"] == "bare" and p["arm"] == S.ARMS[0]:
            leaked[i] = dict(p, row=byid["p493:n3"])
            break
    ok(len(leaked) == len(good), "the mutant has the same call count as the clean list")
    raises(lambda: S.gate_counts(leaked, sheet, plan), AssertionError,
           "a refused span planted in a correctly-counted payload list")

    # a second mutant: the gate must not pass just because the plan says nothing is refused
    empty = SR.SendPlan(sendable=tuple(ids), refused={},
                        report={"n": 45, "n_refused": 0, "n_population": 45,
                                "refusal_class": SR.REFUSAL_CLASS, "refused": {}})
    raises(lambda: S.gate_counts(good, sheet, empty), AssertionError,
           "a plan that refuses nothing, checked against the 162 gated payloads")

    # ---- "none sent", net 3: the REAL builder, end to end over the real crops
    payloads = S.build_payloads(calls)
    built = {p["row"]["span_id"] for p in payloads}
    ok(len(payloads) == 162, "build_payloads built 162 real payloads")
    ok(not (built & set(plan.refused)),
       "no refused span appears in a real built payload (end to end, real crops)")
    blob = "\n".join(p["row"]["crop_file"] for p in payloads)
    for sid in AGREED_REFUSED:
        pf, nf = sid.split(":n")
        ok(("p%s_n%s_" % (pf[1:], nf)) not in blob,
           "%s's crop file is referenced by no payload" % sid)
    S.gate_counts(payloads, sheet, plan)
    ok(True, "gate_counts accepts the real payloads")

    # ---- the three-state rule: a span can be refused, clean, or UNKNOWN, and unknown is not clean
    ok(flags["p92:n1"] == ["box_fault"],
       "p92:n1 carries box_fault in the sidecar although it is outside the 45")
    ok("p92:n1" not in ids, "p92:n1 is not in this sheet, so it is refused for a later draw, not now")
    raises(lambda: SR.refuse_at_send(["p999:n9"], flags, on_refused="record"),
           SR.FlagsUnavailable, "a span with no flag record at all")
    raises(lambda: SR.refuse_at_send(ids, flags, on_refused=None), ValueError,
           "on_refused omitted (passed as None)")
    ok(sorted(side["counts"]["refused_over_74"]) ==
       sorted(set(side["counts"]["box_fault"]) | set(side["counts"]["partial_in_crop"])),
       "the sidecar's refused-over-74 set is the union of the two refusing populations (12 spans)")


def run():
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        # An exception here would otherwise end the run before the count assertion below, which is
        # how this lane lost 40 assertions twice.  It becomes a reported failure instead.
        import traceback
        traceback.print_exc()
        FAILED.append("UNEXPECTED EXCEPTION: %r" % (e,))
    print("score45_refusal: %d checks, %d failed" % (N, len(FAILED)))
    rc = 0
    if FAILED:
        for m in FAILED:
            print("  - %s" % m)
        rc = 1
    if N != EXPECTED_CHECKS:
        print("CHECK COUNT %d != EXPECTED_CHECKS %d -- a check was lost, added, or never reached"
              % (N, EXPECTED_CHECKS))
        rc = 1
    return rc


EXPECTED_CHECKS = 43


if __name__ == "__main__":
    sys.exit(run())
