# -*- coding: utf-8 -*-
u"""Born-test for the Hebrew span ratchet's block in .githooks/pre-commit.

Chris, 2026-11-22 (second ruling): "append the block to .githooks/pre-commit yourself, on
apparatus-next, with a born-test."

This file does not assert that the hook SAYS the right thing. It EXTRACTS the committed bytes
between the block's markers and RUNS them, with a stub standing in for the interpreter, so what
is checked is the behaviour of the installed block and not a copy of what it is supposed to be.
That distinction has already cost this lane once: a check that re-derived a dispatch by reading
source was green while the real dispatch did the opposite.

Every branch of the block is driven by mutation: the module refusing, the module passing, the
module absent, and no interpreter at all. A green run on this machine proves none of them.

Run: python -X utf8 pipeline/reextract/test_precommit_span_ratchet.py
"""
import io
import os
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOOK = os.path.join(REPO, ".githooks", "pre-commit")
MODULE_REL = "pipeline/reextract/hebrew_span_ceiling.py"
BEGIN = "# --- BEGIN Lane B: Hebrew span ratchet"
END = "# --- END Lane B: Hebrew span ratchet ---"

STUB = u"""#!/bin/sh
# Stands in for the interpreter, records what the block asked it to run, and exits as told.
echo "$@" >> "$STUBLOG"
exit ${STUBRC:-0}
"""


def _hook_text():
    return io.open(HOOK, encoding="utf-8").read()


def _block(text=None):
    u"""The committed bytes of the block, markers included. Fails if it is not exactly one."""
    t = text if text is not None else _hook_text()
    if t.count(BEGIN) != 1 or t.count(END) != 1:
        raise RuntimeError("expected exactly one BEGIN and one END marker, got %d/%d"
                           % (t.count(BEGIN), t.count(END)))
    i, j = t.index(BEGIN), t.index(END) + len(END)
    if j < i:
        raise RuntimeError("END comes before BEGIN")
    return t[i:j] + u"\n"


def _sh():
    return shutil.which("sh") or shutil.which("bash")


def run_block(rc=0, module_present=True, with_python=True, block=None):
    u"""Run the committed block in a sandbox. Returns (rc, stdout+stderr, [argv the stub saw])."""
    sh = _sh()
    if not sh:
        raise RuntimeError("no sh on PATH: the block cannot be executed here, so these checks "
                           "are UNMEASURED -- which is a failure, not a skip")
    d = tempfile.mkdtemp(prefix="ratchet_hook_")
    try:
        os.makedirs(os.path.join(d, "pipeline", "reextract"))
        if module_present:
            io.open(os.path.join(d, MODULE_REL.replace("/", os.sep)), "w",
                    encoding="utf-8").write(u"# placeholder; the stub is what runs\n")
        bin_ = os.path.join(d, "bin")
        os.makedirs(bin_)
        log = os.path.join(d, "stub.log")
        if with_python:
            # BOTH names, so whichever `command -v` resolves first is the stub and not a real one.
            for name in ("python", "python3"):
                p = os.path.join(bin_, name)
                io.open(p, "w", encoding="utf-8", newline="\n").write(STUB)
                os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        script = os.path.join(d, "block.sh")
        io.open(script, "w", encoding="utf-8", newline="\n").write(
            block if block is not None else _block())
        env = dict(os.environ)
        # An EMPTY PATH would also make `command -v` fail, but then nothing in the block's own
        # `if` could run either. Keep a real PATH and simply withhold the interpreter.
        env["PATH"] = bin_ if with_python else os.path.join(d, "empty")
        env["STUBLOG"] = log
        env["STUBRC"] = str(rc)
        proc = subprocess.Popen([sh, script], cwd=d, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = proc.communicate()[0].decode("utf-8", "replace")
        seen = io.open(log, encoding="utf-8").read().splitlines() if os.path.exists(log) else []
        return proc.returncode, out, seen
    finally:
        shutil.rmtree(d, ignore_errors=True)


def selftest():
    n, f = [0], [0]

    def ck(name, cond, extra=""):
        n[0] += 1
        if cond:
            print("  ok    %s" % name)
        else:
            f[0] += 1
            print("  FAIL  %s   %s" % (name, extra))

    print("(1) the block is installed, once, and the hook still parses")
    text = _hook_text()
    ck("the hook exists and carries exactly one copy of the block",
       text.count(BEGIN) == 1 and text.count(END) == 1, (text.count(BEGIN), text.count(END)))
    blk = _block(text)
    sh = _sh()
    ck("`sh -n` parses the WHOLE hook, not just the block",
       sh is not None and subprocess.call([sh, "-n", HOOK]) == 0, sh)
    ck("the block comes BEFORE the hook's final `exit 0`, so it is reached",
       text.index(BEGIN) < text.rindex("exit 0") and text.rstrip().endswith("exit 0"))
    ck("the hook names three rules now, and the third is this one",
       "# Three rules:" in text and "may not rise" in text)
    ck("the block invokes the module in exactly one place, and guards it in exactly one place",
       blk.count('"$py" -X utf8 ' + MODULE_REL) == 1
       and blk.count('[ ! -f ' + MODULE_REL + ' ]') == 1,
       (blk.count('"$py" -X utf8 ' + MODULE_REL), blk.count('[ ! -f ' + MODULE_REL + ' ]')))
    # A probe that misses passes on nothing: the path the block names must be a real file here.
    ck("the module the block names EXISTS in this tree",
       os.path.isfile(os.path.join(REPO, MODULE_REL.replace("/", os.sep))))
    ck("the block passes NO command argument, since `ratchet` is the module's default",
       "hebrew_span_ceiling.py check" not in blk and "hebrew_span_ceiling.py ratchet" not in blk)
    ck("the block names no bypass -- a refusal names the count and the files (Chris, 2026-11-22)",
       "no-verify" not in blk and "override" not in blk.lower())

    print("")
    print("(2) every branch of the block, driven by mutation")
    rc_pass, out_pass, seen_pass = run_block(rc=0)
    ck("the module exiting 0 lets the commit proceed", rc_pass == 0, (rc_pass, out_pass[:80]))
    ck("the stub was really the thing invoked, with the module and no command argument",
       len(seen_pass) == 1 and seen_pass[0].split() == ["-X", "utf8", MODULE_REL], seen_pass)
    rc_ref, out_ref, _ = run_block(rc=1)
    ck("the module REFUSING fails the commit -- the whole point, proved by mutation",
       rc_ref != 0, (rc_ref, out_ref[:80]))
    rc_odd, _, _ = run_block(rc=7)
    ck("any non-zero exit fails the commit, not only 1", rc_odd != 0, rc_odd)
    rc_abs, out_abs, seen_abs = run_block(rc=1, module_present=False)
    ck("a MISSING module does not refuse: branches that predate it stay committable",
       rc_abs == 0, (rc_abs, out_abs[:80]))
    ck("...but it is LOUD: the notice says the ratchet did not run, and where the tree is "
       "measured instead",
       "did NOT run" in out_abs and "dr-voluminous" in out_abs, out_abs[:120])
    ck("with the module missing, nothing was invoked at all", seen_abs == [], seen_abs)
    rc_nopy, out_nopy, _ = run_block(rc=1, with_python=False)
    ck("no interpreter on PATH does not refuse either, and says so",
       rc_nopy == 0 and "did NOT run" in out_nopy, (rc_nopy, out_nopy[:100]))

    print("")
    print("(3) the block against the REAL module, on this tree")
    sh = _sh()
    d = tempfile.mkdtemp(prefix="ratchet_hook_real_")
    try:
        script = os.path.join(d, "block.sh")
        io.open(script, "w", encoding="utf-8", newline="\n").write(blk)
        proc = subprocess.Popen([sh, script], cwd=REPO, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        out_real = proc.communicate()[0].decode("utf-8", "replace")
        rc_real = proc.returncode
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ck("the installed block, run from the repository root with no staged change, ADMITS",
       rc_real == 0, (rc_real, out_real[-200:]))
    ck("and it did not fall into either notice branch -- the real module ran",
       "did NOT run" not in out_real, out_real[:120])

    print("")
    ck("born-test check count is pinned, so a raise cannot quietly shorten the suite",
       n[0] == 18, n[0])

    print("")
    print("%s: %d/%d checks" % ("PASS" if not f[0] else "FAIL", n[0] - f[0], n[0]))
    return f[0]


if __name__ == "__main__":
    sys.exit(selftest())
