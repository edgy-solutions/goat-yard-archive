# -*- coding: utf-8 -*-
u"""Born tests for audit_overlay_20261025: the REFUSALS, and the content.

pytest is not installed in this venv: run it directly.

    PYTHONIOENCODING=utf-8 ../../../goat-yard-archive/.venv/Scripts/python.exe \
        test_audit_overlay.py

`audit_overlay_20261025.main()` already runs 12 content checks on every build.  This file tests the
three things those checks cannot see, because they are properties of the WRITE:

  1. A build whose digest does not round-trip is refused AND LEAVES NOTHING BEHIND.  The first
     version of this writer raised after placing the file, so a record that failed its own hash rule
     sat in the audits directory where it could be cited.
  2. A file of the same name with different bytes is not clobbered.  (approval-records-are-content-
     addressed: a fixed filename once destroyed a 19-span approval.)
  3. The verification is INDEPENDENT of the function it verifies.  The first version of guard (1)
     called digest() -- the same function that produced the value -- so patching digest() made both
     sides agree and the guard passed a deliberately wrong value.  A check that calls the function
     that made the value cannot witness it.  Test 1 below only means something because the
     verification now spells the rule out separately; if someone replaces it with a digest() call,
     test 1 goes green and stays green while the guard is dead, so test 3 watches the SOURCE.

The assertion COUNT is asserted: an exception in a hand-rolled suite ends the run silently.

All page numbers are FILE pages (printed = file - 88).
"""
import io
import json
import os
import re
import sys

import audit_overlay_20261025 as A

N = 0
FAILED = []


def chk(cond, msg):
    global N
    N += 1
    if not cond:
        FAILED.append(msg)


def staging():
    return [f for f in os.listdir(A.DATA) if f.endswith(".staging")]


def record_path(rec):
    return os.path.join(A.DATA, "ADJUDICATION_classify45_20261025_%s.json" % rec["self_sha16"])


chk(staging() == [], "no staging file is lying around before the tests start: %s" % staging())

# ----------------------------------------------------------- 1. a bad digest is refused, and swept
_real = A.digest
A.digest = lambda o: u"deadbeefdeadbeef"
try:
    A.main()
    chk(False, "a record whose digest does not round-trip was ACCEPTED")
except IOError as e:
    chk("round-trip" in str(e),
        "the round-trip refusal fires, and says what failed: %s" % e)
finally:
    A.digest = _real
_bad = os.path.join(A.DATA, "ADJUDICATION_classify45_20261025_deadbeefdeadbeef.json")
chk(not os.path.exists(_bad),
    "the refused build left NO record on disk -- a file that failed its own hash rule must not "
    "survive where it can be cited: %s" % _bad)
chk(staging() == [], "the refused build left no staging file: %s" % staging())
# Sweep it if the guard is dead.  A failing run of this suite must not leave a record that failed
# its own hash rule in the audits directory -- which is the very thing test 1 is about, and which a
# mutation run of this suite did leave behind once.
if os.path.exists(_bad):
    os.remove(_bad)

# --------------------------------------------- 2. same name, different bytes is not clobbered
_rec = A.build()
_p = record_path(_rec)
chk(os.path.exists(_p),
    "the committed record is on disk to begin with, or test 2 proves nothing: %s" % _p)
_orig = open(_p, "rb").read()
try:
    with open(_p, "wb") as fh:
        fh.write(b'{"kind": "tampered"}')
    try:
        A.main()
        chk(False, "a file with the same digest-name and DIFFERENT bytes was clobbered")
    except IOError as e:
        chk("refusing to clobber" in str(e), "the clobber refusal fires: %s" % str(e)[:80])
    chk(open(_p, "rb").read() == b'{"kind": "tampered"}',
        "and the refusal did not touch the file it refused to clobber")
    chk(staging() == [], "no staging file after the clobber refusal: %s" % staging())
finally:
    with open(_p, "wb") as fh:
        fh.write(_orig)

# ------------------------------------- 3. the guard does not call the function it is checking
_src = io.open(os.path.join(os.path.dirname(os.path.abspath(A.__file__)),
                            "audit_overlay_20261025.py"), encoding="utf-8").read()
_block = _src[_src.index("claimed = back.pop"):_src.index("if recomputed != claimed")]
# Strip comments first: the block's own comment EXPLAINS that it must not call digest(), and the
# first version of this test matched that explanation and failed on the prose.  A check that reads
# source has to read the code, not the commentary about the code.
_code = chr(10).join([l.split("#")[0] for l in _block.split(chr(10))])
# A word boundary, because `hexdigest(` CONTAINS `digest(` -- the first version of this
# matcher flagged the hashlib call it was written to require.
chk(re.search("(?<![A-Za-z_])digest[(]", _code) is None,
    "the round-trip verification must NOT call digest(): digest() produced the claimed value, so a "
    "check that calls it agrees by construction and test 1 above would pass on a dead guard")
chk("hashlib.sha256" in _code and "ensure_ascii=False" in _code and "sort_keys=True" in _code
    and "indent=1" in _code,
    "the verification spells the stated rule out itself, so the two spellings can disagree")

# --------------------------------------------------------- the happy path, and the content
chk(A.main() == 0, "the accepted build returns 0")
chk(open(_p, "rb").read() == _orig,
    "and writes bytes identical to the committed record: the build is reproducible")
_d = json.loads(_orig.decode("utf-8"))
chk((chr(13) + chr(10)).encode("ascii") not in _orig,
    "the record on disk has no CRLF, so its bytes are the serialisation the hash rule names")
chk(_d["of_sha256_16"] == u"24ed1d191b3d821f",
    "the record names the BYTES of the audited sheet, not just its filename: got %r"
    % _d["of_sha256_16"])

_sheet = os.path.join(A.DATA, A.SHEET)
chk(os.path.exists(_sheet), "the sheet those verdicts are about is on disk: %s" % _sheet)
if os.path.exists(_sheet):
    import hashlib
    with open(_sheet, "rb") as fh:
        chk(hashlib.sha256(fh.read()).hexdigest()[:16] == _d["of_sha256_16"],
            "and the sheet on disk IS the one audited -- a different digest means these verdicts "
            "are not about this document")

# the standoff claim: this record must not be the only place a verdict lives, nor edit the measured
# records.  Assert there is no writer here that touches them.
# The overlay SHOULD name both measured records -- a standoff record that does not say what it
# stands off from is just a second opinion from nowhere.  The property that matters is that neither
# is ever opened for writing, and the single-write assertion below is what establishes that.
chk("CLASSIFY45_501ab577a18a6785.json" in _src and A.CANONICAL in _src,
    "the record names BOTH measured records it stands beside, so a reader can find them")
_writes = [l for l in _src.split(chr(10))
           if ("open(" in l and '"w' in l) or "os.remove" in l or "os.rename" in l]
chk(all(("staged" in l or "(p" in l or "(p," in l) for l in _writes),
    "every write, remove and rename targets only the staging file or the record itself: %s"
    % [l.strip()[:60] for l in _writes
       if not ("staged" in l or "(p" in l or "(p," in l)])
chk(_src.count('"w"') == 1,
    "exactly ONE write in this module -- the staging write -- so there is no second path that "
    "could modify a record: got %d" % _src.count('"w"'))

_rows = _d["rows"]
chk(len([r for r in _rows if r["verdict"] == "signature" and r.get("reversed")]) == 2
    and all(r["span_id"] == "p442:n0" for r in _rows
            if r["verdict"] == "signature" and r.get("reversed")),
    "ruling A(1) is in the record and is confined to p442:n0: exactly two reversed-signature rows, "
    "both that span")
chk(all(r["page_printed"] == r["page_file"] - 88 for r in _rows),
    "printed = file - 88 holds on every row of the written record, not just in the builder")

EXPECTED = 21
print("audit_overlay refusals: %d checks, %d failed" % (N, len(FAILED)))
for m in FAILED:
    print("  FAIL  %s" % m)
if N != EXPECTED:
    print("SUITE DID NOT RUN TO COMPLETION: %d checks, expected %d. An exception in a hand-rolled "
          "suite ends it silently; a short count is a failure, not a smaller pass." % (N, EXPECTED))
    sys.exit(2)
sys.exit(1 if FAILED else 0)
