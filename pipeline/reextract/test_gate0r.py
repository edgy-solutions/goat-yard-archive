"""GATE 0R, proved live by mutation: the scoreability precondition the blank report must carry.

Advisor ruling of 2026-11-14, item 2: the precondition goes "in the lock's own words and in the
result's first line", and no stability claim may be made for the three cells that abstained
completely in run 1.  `scoreability_from_lock` derives that from the lock BEFORE the first paid
call; `gate_blank_first_line` refuses to write a report that does not lead with it.

Why this file exists at all: a green run proves nothing about a guard.  Each arm below drives the
guard to a DEFECT and asserts it refuses, and the arm count is asserted at the end -- a `raise`
in a hand-rolled suite ends the run silently, so a suite that cannot say how many arms it ran
cannot tell "all passed" from "aborted after two".

No network, no key, no spend.  Run: python test_gate0r.py
"""
import copy
import io
import json
import pathlib
import sys

RX = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(RX))

import score45_run as S                                                        # noqa: E402

LOCK = pathlib.Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits"
                    "/PREDICTIONS_blank45_replicate_9870c46591b19aec.json")

ARMS = []


def arm(name, fn):
    """Run one arm.  An exception inside it is a FAILURE of that arm, never the end of the run."""
    try:
        fn()
        ARMS.append((name, "pass", ""))
    except AssertionError as e:
        ARMS.append((name, "FAIL", str(e)[:200]))
    except Exception as e:                                                     # noqa: BLE001
        ARMS.append((name, "ERROR", "%s: %s" % (type(e).__name__, str(e)[:160])))


def refuses(fn, want):
    """`fn` must raise AssertionError, and the message must name `want`."""
    try:
        fn()
    except AssertionError as e:
        assert want in str(e), "refused, but the message does not name %r: %s" % (want, e)
        assert "NOTHING HAS BEEN SPENT" in str(e) or "GATE 0R(write)" in str(e), \
            "a pre-call refusal must say nothing was spent: %s" % e
        return
    raise AssertionError("SURVIVED: %s was accepted when it should have been refused" % want)


# --------------------------------------------------------------------------- the real lock
raw = json.loads(LOCK.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- A. the deriver
def a1_no_p1():
    bad = copy.deepcopy(raw)
    bad["scoreability_preconditions"] = [p for p in bad["scoreability_preconditions"]
                                         if p.get("id") != "P1"]
    refuses(lambda: S.scoreability_from_lock(bad), "preconditions with id P1")


def a2_two_p1():
    bad = copy.deepcopy(raw)
    bad["scoreability_preconditions"].append(dict(bad["scoreability_preconditions"][0]))
    refuses(lambda: S.scoreability_from_lock(bad), "preconditions with id P1")


def a3_empty_text():
    bad = copy.deepcopy(raw)
    for p in bad["scoreability_preconditions"]:
        if p["id"] == "P1":
            p["precondition"] = "   "
    refuses(lambda: S.scoreability_from_lock(bad), "empty `precondition`")


def a4_no_cells():
    bad = copy.deepcopy(raw)
    # Leave the non-cell keys in place.  This is the trap the deriver has to survive: a mapping
    # that is NOT empty, but holds nothing cell-shaped.  A deriver that iterated the mapping
    # would invent cells out of an id list and a status string.
    bad["baseline_measured"] = {k: v for k, v in bad["baseline_measured"].items()
                                if not (isinstance(v, dict) and "n" in v)}
    assert bad["baseline_measured"], "this arm needs a non-empty mapping, or it tests nothing"
    refuses(lambda: S.scoreability_from_lock(bad), "no cell carrying both")


def a5_control():
    sc = S.scoreability_from_lock(raw)
    assert sc["scoreable"] == ["qwen/qwen3.7-plus|context"], sc["scoreable"]
    assert sc["floor_only"] == ["anthropic/claude-opus-5.5|bare",
                               "anthropic/claude-opus-5.5|context",
                               "qwen/qwen3.7-plus|bare"], sc["floor_only"]
    assert sc["p1_verbatim"] == [p for p in raw["scoreability_preconditions"]
                                 if p["id"] == "P1"][0]["precondition"], "P1 is not verbatim"


def a6_non_cell_keys_are_not_cells():
    # baseline_measured carries 6 keys, 4 of which are cells.  n_cells must be 4.
    assert len(raw["baseline_measured"]) == 6, len(raw["baseline_measured"])
    assert S.scoreability_from_lock(raw)["n_cells"] == 4


# --------------------------------------------------------------------------- B. the write gate
GOOD = "\n".join(["# BLANK45 deadbeef -- blank-crop CONTROL for run c957403401a9f865", "",
                  S.blank_scoreability_line(S.scoreability_from_lock(raw)), "",
                  "ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).", "",
                  "| arm | channel | abstain |", "|---|---|---|"])


def b1_no_title():
    refuses(lambda: S.gate_blank_first_line(GOOD.split("\n", 1)[1]), "does not open with its title")


def b2_absent():
    md = "\n".join(l for l in GOOD.split("\n") if not l.startswith("**SCOREABILITY"))
    refuses(lambda: S.gate_blank_first_line(md), "0 scoreability lines, not 1")


def b3_duplicated():
    lines = GOOD.split("\n")
    i = [n for n, l in enumerate(lines) if l.startswith("**SCOREABILITY")][0]
    lines.insert(i + 1, lines[i].replace("verbatim", "roughly"))
    refuses(lambda: S.gate_blank_first_line("\n".join(lines)), "2 scoreability lines, not 1")


def b4_demoted():
    # The defect the ruling is actually about: the precondition is present, but a reader meets a
    # number first.  Here the page-convention line and the cell table are moved above it.
    lines = GOOD.split("\n")
    i = [n for n, l in enumerate(lines) if l.startswith("**SCOREABILITY")][0]
    sc = lines.pop(i)
    lines.append(sc)
    refuses(lambda: S.gate_blank_first_line("\n".join(lines)), "must be the first thing read")


def b5_control():
    assert S.gate_blank_first_line(GOOD) == 2, S.gate_blank_first_line(GOOD)


# --------------------------------------------------------------------------- C. the line itself
def c1_no_lock_branch():
    s = S.blank_scoreability_line(None)
    assert s.startswith("**SCOREABILITY: NO LOCK.**"), s[:60]
    assert "NOTHING below is licensed" in s, s
    # The no-lock branch must still satisfy the gate, or a run without a lock cannot report.
    md = "\n".join(["# BLANK45 x", "", s, ""])
    assert S.gate_blank_first_line(md) == 2


def c2_names_the_cells():
    sc = S.scoreability_from_lock(raw)
    s = S.blank_scoreability_line(sc)
    assert sc["p1_verbatim"] in s, "the lock's P1 is not quoted verbatim in the line"
    assert "`qwen/qwen3.7-plus|context`" in s and "only" in s, s
    for c in sc["floor_only"]:
        assert "`%s`" % c in s, "floor-only cell %s is not named" % c
    assert "CORROBORATE a floor of" in s and "NEVER test its stability" in s, s
    assert "0 == 0" in s, "the line does not say what a 0 == 0 is not"


# --------------------------------------------------------------------------- D. the wiring
def d1_every_write_path_passes_the_gate():
    """Structural, because no offline end-to-end exists.

    The blank writer cannot be driven offline: `rescore` refuses blank runs by name, run 1's
    stored evaluation predates `no_pixel_recoverable_single_arm`, and no per-call blank reads
    file was kept.  So instead of claiming an end-to-end this asserts the only thing that can be
    asserted for free and is worth asserting: inside `md_blank_report` there is exactly ONE
    return, the gate call sits immediately before it, and therefore no path writes a report
    without passing the gate.  Comments are stripped first -- a comment mentioning the call
    would otherwise satisfy an assertion about the call.
    """
    src = io.open(RX / "score45_run.py", encoding="utf-8").read()
    body = src.split("def md_blank_report(")[1]
    body = body.split("\ndef ")[0]
    code = [l for l in body.split("\n") if not l.lstrip().startswith("#")]
    rets = [n for n, l in enumerate(code) if l.strip().startswith("return ")]
    assert len(rets) == 1, "md_blank_report has %d returns; the gate guards one path" % len(rets)
    calls = [n for n, l in enumerate(code) if "gate_blank_first_line(" in l]
    assert len(calls) == 1, "%d gate calls in md_blank_report" % len(calls)
    assert calls[0] == rets[0] - 1, \
        "the gate call is at %d and the return at %d: not adjacent" % (calls[0], rets[0])


# --------------------------------------------------------------------------- run
for nm, f in [("A1 lock with no P1", a1_no_p1),
              ("A2 lock with two P1", a2_two_p1),
              ("A3 P1 with empty text", a3_empty_text),
              ("A4 baseline with no cell-shaped entry", a4_no_cells),
              ("A5 control: the real lock derives one scoreable cell", a5_control),
              ("A6 non-cell keys are not counted as cells", a6_non_cell_keys_are_not_cells),
              ("B1 report with no title", b1_no_title),
              ("B2 precondition absent", b2_absent),
              ("B3 precondition duplicated", b3_duplicated),
              ("B4 precondition demoted below a number", b4_demoted),
              ("B5 control: the real shape passes at line 2", b5_control),
              ("C1 the no-lock branch", c1_no_lock_branch),
              ("C2 the line quotes P1 and names every cell", c2_names_the_cells),
              ("D1 every write path passes the gate", d1_every_write_path_passes_the_gate)]:
    arm(nm, f)

EXPECTED_ARMS = 14
bad = [a for a in ARMS if a[1] != "pass"]
for nm, st, msg in ARMS:
    print("%-6s %-52s %s" % (st, nm, msg))
print("\n%d arms, %d not passing" % (len(ARMS), len(bad)))
if len(ARMS) != EXPECTED_ARMS:
    print("ARM COUNT: ran %d, expected %d -- the suite did not finish" % (len(ARMS), EXPECTED_ARMS))
    sys.exit(2)
sys.exit(1 if bad else 0)
