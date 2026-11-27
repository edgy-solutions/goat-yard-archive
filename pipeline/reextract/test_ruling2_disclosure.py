# -*- coding: utf-8 -*-
u"""Lane B -- the ruling-2 disclosure gate, proved by mutation.

Chris, 2026-11-26, item 2: "Approval scope: the 4-row sheet 3ac8580c8853b9f5 carries the approval
for the new pixels.  The other 41 crops ride on the 2026-11-08 approval by recorded hash equality.
No 45-row sheet is needed."

Five branches.  Four must REFUSE and name the right thing; the fifth must PASS.  The passing branch
is the point: a guard that refuses every input has not discriminated, and the one case that has to
be let through is a record naming the sheet the ruling names.  Green on the refusals alone would be
satisfied by a gate that is simply broken.

The branch COUNT is asserted, because an exception in a hand-rolled suite ends the run instead of
failing a case: without the count, a probe that aborted after two branches would look like a pass.

Nothing is written into the audits directory.  The fabricated records live in a mkdtemp dir and the
module's constants are repointed in-process, because a fake human-approval record must never exist
on disk beside the real ones -- a record of a yes is found by name, and a leftover fake is
indistinguishable from the thing it imitates.

FILE pages throughout (printed = file - 88).  Run:
    python -X utf8 test_ruling2_disclosure.py
"""
import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import localizer45_run as R          # noqa: E402

N_BRANCHES_SPECIFIED = 5
RESULTS = []


def _rec(path, ctrl_bytes, **over):
    u"""A syntactically complete approval record, marked as not a human's yes."""
    rec = {"kind": "human_approval", "lane": "Lane B", "session": "50612c81",
           "approves_sheet_self_sha16": R.CTRL_SHEET_RULED,
           "approves_sheet_bytes_sha16": ctrl_bytes,
           "approves_cut_digest": R.CUT,
           "approves_attempts": [R.ATTEMPT],
           "by": "FABRICATED BY test_ruling2_disclosure.py -- NOT A HUMAN YES",
           "on": "2026-11-26"}
    rec.update(over)
    io.open(str(path), "w", encoding="utf-8").write(json.dumps(rec, indent=1))
    return path


def branch(name, expect, patch, needle, rows_src, tmp, ctrl_bytes):
    saved = (R.CTRL_APPROVAL, R.RIDE_APPROVAL)
    rows = [dict(r) for r in rows_src]
    try:
        rows = patch(rows, tmp, ctrl_bytes) or rows
        try:
            R.gate_disclosure(False, rows)
            got, msg = "PASS", ""
        except AssertionError as e:
            got, msg = "REFUSE", str(e)
    finally:
        R.CTRL_APPROVAL, R.RIDE_APPROVAL = saved
    named = (needle in msg) if needle else True
    ok = (got == expect) and named
    RESULTS.append((ok, name, expect, got, named))
    print("  %-6s %-34s expect=%-7s got=%-7s named=%s"
          % ("ok" if ok else "FAILED", name, expect, got, named))
    return ok


def _baseline(rows, tmp, cb):
    return rows


def _ride_absent(rows, tmp, cb):
    R.RIDE_APPROVAL = tmp / "no_such_approval.json"
    return rows


def _hash_moved(rows, tmp, cb):
    for r in rows:
        if r["stratum"] == "clean":
            r["crop_sha16"] = "0" * 16
            break
    return rows


def _retired_sheet(rows, tmp, cb):
    R.CTRL_APPROVAL = _rec(tmp / "wrong_sheet.json", cb,
                           approves_sheet_self_sha16="e9132010ceda4a52")
    return rows


def _ruled_sheet(rows, tmp, cb):
    R.CTRL_APPROVAL = _rec(tmp / "right.json", cb)
    return rows


def main():
    print("Lane B / session 50612c81 -- ruling-2 disclosure gate, mutation")
    print("FILE pages throughout (printed = file - 88)")
    rows = R.population_rows()
    n_clean = sum(1 for r in rows if r["stratum"] == "clean")
    n_ctrl = sum(1 for r in rows if r["stratum"] == "control")
    print("  population  %d rows (%d clean riding by hash, %d control = new pixels)"
          % (len(rows), n_clean, n_ctrl))
    if (n_clean, n_ctrl) != (41, 4):
        print("FAILED: the ruling is about 41 riding and 4 new; this population is %d and %d"
              % (n_clean, n_ctrl))
        return 1
    ctrl_bytes = R.sha16_bytes(R.CTRL_SHEET.read_bytes())
    tmp = Path(tempfile.mkdtemp(prefix="laneB_ruling2_"))
    try:
        branch("baseline: no new-pixel yes", "REFUSE", _baseline,
               "APPROVAL_controls4_3ac8580c8853b9f5.json", rows, tmp, ctrl_bytes)
        branch("ride record absent", "REFUSE", _ride_absent,
               "ride on an earlier approval", rows, tmp, ctrl_bytes)
        branch("a riding crop's hash moved", "REFUSE", _hash_moved,
               "RECORDED HASH EQUALITY", rows, tmp, ctrl_bytes)
        branch("yes names the retired sheet", "REFUSE", _retired_sheet,
               "the ruling of 2026-11-26 is for", rows, tmp, ctrl_bytes)
        branch("yes names the ruled sheet", "PASS", _ruled_sheet,
               None, rows, tmp, ctrl_bytes)
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)

    print("")
    if len(RESULTS) != N_BRANCHES_SPECIFIED:
        print("FAILED: %d branches ran and %d are specified -- a branch was lost, not passed"
              % (len(RESULTS), N_BRANCHES_SPECIFIED))
        return 1
    bad = [r for r in RESULTS if not r[0]]
    print("%d of %d branches behaved as specified" % (len(RESULTS) - len(bad), len(RESULTS)))
    if bad:
        for _ok, name, expect, got, named in bad:
            print("  FAILED %s: expected %s, got %s, named=%s" % (name, expect, got, named))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
