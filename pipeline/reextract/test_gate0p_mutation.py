# Prove GATE 0P and GATE 0Q live BY MUTATION, not by a green run.
#
# Two things this harness must not do, both scars:
#   - count a CRASH as a survival.  Every arm names the substring its AssertionError must carry;
#     a different exception type, or a message that does not name the defect, is a FAIL.
#   - fire on an upstream check and leave the intended one untested.  The GATE 0P arms assert the
#     "DRY-RUN:" banner is ABSENT from the output, which is the only available proof that the
#     raise happened before the dry/real branch -- and therefore, on a real run, before do_call.
import io, os, re, subprocess, sys, pathlib

RX = pathlib.Path(__file__).resolve().parent     # the module under test is beside this
P = RX / "score45_run.py"
PY = sys.executable                              # the running interpreter, not a path
GOLD = io.open(P, encoding="utf-8").read()

# ---- arms that mutate the source and run a FREE dry-run
SRC_ARMS = [
    ("0P normal pin off by one",
     "EXPECTED_CHECKS_PRECALL = 1170", "EXPECTED_CHECKS_PRECALL = 1169",
     [], "GATE 0P: checks_at_precall 1170 != EXPECTED_CHECKS_PRECALL 1169"),
    ("0P blank pin off by one",
     "    True: 1241,", "    True: 1242,",
     ["--blank-crop"], "GATE 0P: checks_at_precall 1241 != EXPECTED_CHECKS_BLANK_PRECALL[approved=True] 1242"),
    # A LOST CHECK IS A REMOVED CALL, not a condition made trivially true: chk() increments the
    # counter before it tests anything, so `chk(True or ...)` leaves the count untouched.  The
    # first build of this arm made that mistake and recorded a survival the gate was never shown.
    ("0P a header-scoped check lost upstream",
     '''    chk(bsheet["calls"] == len(ARMS) * (41 + 40) == 162,
        "GATE B0: the sheet was approved for %d calls" % bsheet["calls"])''',
     '    pass  # chk removed by the mutation harness',
     ["--blank-crop"], "GATE 0P: checks_at_precall 1240 != EXPECTED_CHECKS_BLANK_PRECALL[approved=True] 1241"),
]

# ---- arms that call gate_call_loop_checks directly: GATE 0Q without a paid run
sys.path.insert(0, str(RX))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
import score45_run as M

FN_ARMS = [
    ("0Q a stepped ladder on one call", (325, 162, 2), "remainder 1"),
    ("0Q every per-call assertion lost", (0, 162, 2), "under the floor 1"),
    ("0Q snapshots out of order", (-4, 162, 2), "which is negative"),
    ("0Q no calls to divide by", (0, 0, 2), "there is nothing to divide by"),
]

fails = []
print("== GATE 0Q, direct (free, no run) ==")
for name, args, want in FN_ARMS:
    try:
        got = M.gate_call_loop_checks(*args)
        fails.append("%s: SURVIVED, returned %r" % (name, got))
        print("FAIL  %s -- survived, returned %r" % (name, got))
    except AssertionError as e:
        ok = want in str(e)
        print("%s  %s -- %s" % ("pass" if ok else "FAIL", name, str(e)[:95]))
        if not ok:
            fails.append("%s: raised but message lacks %r" % (name, want))
    except Exception as e:                      # a crash is not a survival AND not a pass
        fails.append("%s: CRASHED %s: %s" % (name, type(e).__name__, e))
        print("FAIL  %s -- CRASHED %s: %s" % (name, type(e).__name__, e))

# the control: the live value must PASS and return the quotient
try:
    v = M.gate_call_loop_checks(324, 162, 2)
    print("%s  0Q control (324/162) -> %r" % ("pass" if v == 2 else "FAIL", v))
    if v != 2:
        fails.append("0Q control returned %r, expected 2" % v)
except Exception as e:
    fails.append("0Q control raised %s: %s" % (type(e).__name__, e))
    print("FAIL  0Q control raised %s: %s" % (type(e).__name__, e))

print("\n== GATE 0P, by source mutation (free dry-runs) ==")
for name, old, new, flags, want in SRC_ARMS:
    if GOLD.count(old) != 1:
        fails.append("%s: anchor matched %d, arm NOT RUN" % (name, GOLD.count(old)))
        print("FAIL  %s -- anchor matched %d times; arm NOT RUN (an unrun arm is not a pass)"
              % (name, GOLD.count(old)))
        continue
    io.open(P, "w", encoding="utf-8", newline="\n").write(GOLD.replace(old, new))
    try:
        r = subprocess.run([PY, "-X", "utf8", str(P), "--dry-run"] + flags,
                           cwd=str(RX), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=600)
        out = (r.stdout or "") + (r.returncode and (r.stderr or "") or "")
        hit = want in out
        early = "DRY-RUN:" not in out               # proof it fired before the dry/real branch
        typ = "AssertionError" in (r.stderr or "")
        ok = r.returncode != 0 and hit and early and typ
        print("%s  %s -- rc=%d names-defect=%s AssertionError=%s before-branch=%s"
              % ("pass" if ok else "FAIL", name, r.returncode, hit, typ, early))
        if not ok:
            fails.append("%s: rc=%d hit=%s type=%s early=%s" % (name, r.returncode, hit, typ, early))
            if not hit:
                print("      wanted: %s" % want)
                print("      tail: %s" % (r.stderr or r.stdout or "")[-300:].replace("\n", " | "))
    finally:
        io.open(P, "w", encoding="utf-8", newline="\n").write(GOLD)

restored = io.open(P, encoding="utf-8").read() == GOLD
print("\nsource restored byte-identical: %s" % restored)
if not restored:
    fails.append("THE SOURCE WAS NOT RESTORED")
print("arms: %d  failures: %d" % (len(SRC_ARMS) + len(FN_ARMS) + 1, len(fails)))
for f in fails:
    print("  - %s" % f)
sys.exit(1 if fails else 0)
