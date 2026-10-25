# -*- coding: utf-8 -*-
"""Born tests for the law-8 send-path refusal (`send_refusal.py`, advisor ruling B(4)).

pytest is not installed in this venv: run it directly.

    PYTHONIOENCODING=utf-8 ../../../goat-yard-archive/.venv/Scripts/python.exe test_send_refusal.py

The assertion COUNT is itself asserted at the end.  In a hand-rolled suite an exception ENDS the run
silently -- this lane lost 40 assertions that way, twice -- so a suite that stops early must fail
rather than print a smaller number and exit 0.

The refusing population is not typed in as a literal and then checked against itself.  It is read
from the scoring-45 run's own PREDICTIONS file, which was written before the run and is committed, so
the ids here are the ones the run recorded and not the ones I remember.  All page numbers are FILE
pages (printed = file - 88).
"""
import io
import json
import os
import sys

import hebrew_aperture_diag as diag
import send_refusal as SR

N = 0
FAILED = []


def chk(cond, msg):
    global N
    N += 1
    if not cond:
        FAILED.append(msg)


def raises(exc, fn, msg):
    global N
    N += 1
    try:
        fn()
    except exc:
        return
    except Exception as e:                                        # a different error is not a pass
        FAILED.append("%s: raised %s, wanted %s" % (msg, type(e).__name__, exc.__name__))
        return
    FAILED.append("%s: did not raise %s" % (msg, exc.__name__))


# --------------------------------------------------------------- the predicate, on each flag alone
chk(SR.refuses("pX:n0", ["box_fault"]), "box_fault alone refuses")
chk(SR.refuses("pX:n0", ["partial_in_crop"]), "partial_in_crop alone refuses")
chk(SR.refuses("pX:n0", ["box_fault", "partial_in_crop"]), "both flags refuse")
chk(not SR.refuses("pX:n0", []), "a measured span with no refusing flag is sendable")
chk(not SR.refuses("pX:n0", ["sic", "multi_word", "editorial_insertion", "corrected_heavy"]),
    "the four non-refusing populations do not refuse")
chk(SR.refusal_reason("pX:n0", ["box_fault", "sic"]) == ("box_fault",),
    "the reason names only the refusing population")
chk(SR.refusal_reason("pX:n0", ["partial_in_crop", "box_fault"]) == ("box_fault", "partial_in_crop"),
    "both reasons are reported, sorted")
chk(SR.refusal_reason("pX:n0", ["sic"]) == (), "no refusing flag gives an empty reason")

# ------------------------------------------------- unknown is not clean: the required-argument rule
raises(SR.FlagsUnavailable, lambda: SR.refuses("pX:n0", None),
       "None populations must raise, never return False")
raises(SR.FlagsUnavailable, lambda: SR.refusal_reason("pX:n0", None),
       "None populations raise from refusal_reason too")
raises(SR.FlagsUnavailable, lambda: SR.partition(["a", "b"], {"a": []}),
       "a span absent from the flag mapping refuses the whole population")
raises(SR.FlagsUnavailable, lambda: SR.require_flags(["a"], {"a": None}),
       "an explicit None record is not an empty one")
chk(SR.require_flags(["a", "b"], {"a": [], "b": ["sic"]}) is None,
    "a fully measured population passes require_flags")

# ------------------------------------------------------------------------------ partition arithmetic
pops = {"p1:n0": [], "p2:n0": ["box_fault"], "p3:n0": ["partial_in_crop"], "p4:n0": ["sic"]}
sendable, refused = SR.partition(sorted(pops), pops)
chk(sendable == ["p1:n0", "p4:n0"], "partition sends exactly the unflagged spans")
chk(sorted(refused) == ["p2:n0", "p3:n0"], "partition refuses exactly the flagged spans")
chk(len(sendable) + len(refused) == len(pops), "partition conserves the population: nothing dropped")
chk(refused["p2:n0"] == ("box_fault",), "partition carries the reason, not just the fact")

# ------------------------------------------------------------- law 8: never reaches a paid arm
chk(SR.gate_not_sent(sendable, refused) is None, "a clean plan passes the law-8 gate")
raises(SR.RefusalFault, lambda: SR.gate_not_sent(sendable + ["p2:n0"], refused),
       "a refused span in the built payloads is a RUN fault")
# the gate must be able to see the failure: it is checked against what was built, so a plan that
# excluded the span but a payload that included it must still fail.
raises(SR.RefusalFault, lambda: SR.gate_not_sent(["p2:n0"], refused),
       "the gate reads the payloads, not the plan that was supposed to exclude them")

# --------------------------------------------------------------------- the denominators (the ruling)
cls = {"p1:n0": "exact", "p4:n0": "wrong"}
t = SR.tally(cls, refused)
chk(t["n"] == 2, "n counts the SENT spans only")
chk(t["n_refused"] == 2, "n_refused is reported beside n")
chk(t["n_population"] == 4, "n + n_refused is the whole population: never dropped")
chk(t["exact"] == 1 and t["wrong"] == 1, "exact/wrong count the sent spans")
chk(t["exact"] + t["wrong"] + t["nikud_only"] + t["abstain"] == t["n"],
    "the class counts sum to n")
chk(t["exact_rate_on_sent"] == 0.5, "the rate is taken over the sent denominator")
chk(t["refusal_class"] == "unscorable:input-refused" == SR.REFUSAL_CLASS,
    "the refusal class is the one the ruling names")
chk(sorted(t["refused"]) == ["p2:n0", "p3:n0"], "the refused ids travel with the tally")
chk(t["refused"]["p2:n0"] == ["box_fault"], "the refused reasons travel with the tally")
# never counted wrong: the refusal must not be reachable as a read class
chk(SR.REFUSAL_CLASS not in SR.READ_CLASSES, "the refusal class is not a read class")
raises(SR.RefusalFault, lambda: SR.tally({"p2:n0": "wrong"}, refused),
       "a refused span with a read class is a run fault, not a wrong row")
raises(ValueError, lambda: SR.tally({"p1:n0": "box_fault"}, {}),
       "an unknown read class is rejected")
# the refusal is NOT free: it raises the rate on the sent population, and that must be visible
t_all = SR.tally({"p1:n0": "exact", "p4:n0": "wrong", "p2:n0": "wrong", "p3:n0": "wrong"}, {})
chk(t_all["exact_rate_on_sent"] == 0.25 and t["exact_rate_on_sent"] == 0.5,
    "refusing the flagged rows RAISES the exact rate (0.25 -> 0.50): not a free improvement")
chk("counted neither exact nor wrong" in t["denominator_note"],
    "the tally states which denominator its rates are over")

# ------------------------------------------- liveness: the ids come from the run, not from my memory
PRED = os.path.join(str(diag.DATA), "PREDICTIONS_scoring45_36122ad8eb06a9c2.json")
chk(os.path.exists(PRED), "the scoring-45 PREDICTIONS file is present (a probe that misses passes "
                          "on nothing): %s" % PRED)
if os.path.exists(PRED):
    p = json.load(io.open(PRED, encoding="utf-8"))
    pop45 = p["basis"]["populations_reported_separately"]
    for name in SR.REFUSING_POPULATIONS:
        chk(name in pop45, "the run records a '%s' population" % name)
    bf = set(pop45["box_fault"]["ids"])
    pic = set(pop45["partial_in_crop"]["ids"])
    chk(len(bf) == 3, "3 of the 45 carry a ratified box_fault (got %d)" % len(bf))
    chk(len(pic) == 4, "4 of the 45 carry partial_in_crop (got %d)" % len(pic))
    chk(bf < pic, "every box_fault row is also partial_in_crop")
    # build the mapping the send path would build, over the whole 45, and refuse through it
    ids45 = sorted({r["span_id"] for r in json.load(io.open(
        os.path.join(str(diag.DATA),
                     "CONTACT_SHEET_scoring45_adb9a26835533dbc_c26745f4be489471bd.json"),
        encoding="utf-8"))["rows"]}) if os.path.exists(os.path.join(
            str(diag.DATA),
            "CONTACT_SHEET_scoring45_adb9a26835533dbc_c26745f4be489471bd.json")) else sorted(bf | pic)
    by = {sid: sorted(n for n, v in pop45.items() if sid in set(v.get("ids") or []))
          for sid in ids45}
    sent45, ref45 = SR.partition(ids45, by)
    chk(sorted(ref45) == sorted(bf | pic),
        "the refusal over the run's own population is exactly box_fault | partial_in_crop: %s"
        % sorted(ref45))
    chk(len(ref45) == 4, "4 of the sent spans would have been refused (got %d)" % len(ref45))
    chk(len(sent45) + len(ref45) == len(ids45),
        "the 45-span population is conserved: %d sent + %d refused = %d"
        % (len(sent45), len(ref45), len(ids45)))
    # the negative control that matters: p442:n0 is the reader row that withdrew the ship rule.
    # If the refusal caught it, the refusal would be claiming a crop cause it does not have.
    chk("p442:n0" in by, "p442:n0 is in the run's population")
    chk(not SR.refuses("p442:n0", by.get("p442:n0") or []),
        "p442:n0 is NOT refused -- it is reader/substitution on a clean crop, and a geometry "
        "refusal must not claim it")
    chk("p493:n3" in ref45, "p493:n3 IS refused -- the crop-class agreement-and-wrong row")

# --------------------------------------------------- the gate is WIRED UP, not merely implemented
# This lane shipped a localizer that was never called: `n_before` was 0 on 74 of 74 rows because the
# function could derive its own input. A guard that exists and is not wired is the same defect with a
# different face, so the wiring is asserted on the sender's source, not assumed.
import inspect

import hebrew_frontier_or as H

src = inspect.getsource(H.run)
chk("SR.load_span_flags" in src, "run() loads the send-flag sidecar")
chk("SR.partition" in src, "run() partitions the send list through the refusal")
chk("SR.gate_not_sent" in src, "run() calls the law-8 payload gate")
chk(SR.REFUSAL_CLASS in src, "run() names the refusal class in its refusal message")
# ordering: the refusal must precede every paid step. `catalog` is the first thing that reaches the
# network and `call` is the thing that spends; both must come after the gate.
i_gate = src.index("SR.load_span_flags")
for paid in ("catalog(", "call("):
    j = src.find(paid)
    chk(j == -1 or i_gate < j, "the law-8 gate precedes %s in run()" % paid)
# and it must NOT be in cells(), which the post-hoc `score` path also calls: a refusal there would
# make a spent run unanalysable.
csrc = inspect.getsource(H.cells)
chk("SR.load_span_flags" not in csrc and "SR.partition" not in csrc,
    "the refusal is NOT in cells(): score() analyses spent runs through it")

# ------------------------------------------------------------------------------------------ report
EXPECTED = 53
print("send_refusal: %d checks, %d failed" % (N, len(FAILED)))
for m in FAILED:
    print("  FAIL  %s" % m)
if N != EXPECTED:
    print("SUITE DID NOT RUN TO COMPLETION: %d checks, expected %d. An exception in a hand-rolled "
          "suite ends it silently; a short count is a failure, not a smaller pass." % (N, EXPECTED))
    sys.exit(2)
sys.exit(1 if FAILED else 0)
