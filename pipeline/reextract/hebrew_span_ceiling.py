# -*- coding: utf-8 -*-
u"""A ceiling on how much of the Hebrew truth set this PUBLIC repository may carry.

Chris's ruling of 2026-11-16 (law 1):
  1. "The Hebrew truth set as a whole lives only in dr-voluminous. The public repository may carry
     small samples: test fixtures and example rows in console or result code. It never carries a
     truth-set file, a run output, or a signed export."
  4. "Make it a guard: extend the code-only pre-commit hook to count distinct span ids with Hebrew
     in the staged tree and refuse above the ceiling, with a born-test. The ceiling is Chris's
     number, 10% of the signed set; state it in the hook."

THE CEILING IS STATED, NOT COMPUTED HERE: 11 distinct span ids, which is 10% of the 111 signed rows
(int(111 * 0.10)). 111 is the signed set as of 2026-11-16 -- pass-1 74, pass-2 26, pass-3 3,
pass-3-r2 3, the 5-span return 5 -- and it is a figure about a file in the PRIVATE repository. This
module does not read that repository and must not: a guard in a public repo that needs the private
repo to decide is a guard that is skipped on the machine that matters. So 111 and 11 are written
here as constants with their basis, and SIGNED_ROWS_BASIS says what would have to be re-derived if
the signed set grows.

WHAT IS COUNTED, and the three readings that were available:

  A span id is `pNNN:nN`. Hebrew is the Hebrew block plus the alphabetic presentation forms. A span
  id COUNTS when a Hebrew character appears within WINDOW lines of it, in the same file.

  (a) same line only. Measured over this repository on 2026-11-16: 6 of the 74 distinct signed ids.
  (b) within 2 lines -- what this module uses. A dict literal or a fixture row routinely puts the
      id and the reading on neighbouring lines, and (a) would score those zero while a human reading
      the file sees a truth-set row. Wider is STRICTER, and a guard should not be defeated by a line
      break.
  (c) anywhere in the same file. Measured: 23 signed ids. That is not a reading of "with Hebrew" --
      it counts every id in any module that happens to hold one Hebrew string anywhere, including
      modules whose ids are test names. Rejected as over-broad, and named here so the choice is
      visible rather than silent.

  The count is over the RESULTING TREE -- every file the commit would leave in the repository, which
  is what `git ls-files` with the staged content gives -- and NOT over the staged diff alone. "The
  staged tree" is the words of the ruling, and the diff-only reading is defeated by splitting a leak
  across commits that are each under the ceiling. The ceiling is therefore cumulative, which is also
  what law 1 is about: what the public repository CARRIES.

  It counts span ids by their syntax, not against a list of the signed ones, because the list lives
  in the private repo. So the count is conservative: an id that is not in the signed set still
  counts against the ceiling. That is the right direction for a wall.

WHAT THIS GUARD CANNOT DO -- and the first two are the reason it is not the whole of law 1:
  - It cannot see Hebrew that travels WITHOUT a span id, nor a reading rewritten into an id-free
    fixture. A truth set could leak as a bare list of words and this guard would count zero.
  - It cannot see a file that was public and has been deleted. The history keeps it. The ceiling
    governs what the next commit carries; LAW1_span_leak_measure_20261116.json measures what the
    remote already holds, and the two are different questions.
  - It cannot judge whether a sample is a "small sample" in Chris's sense. It counts.
"""
import io
import json
import os
import re
import subprocess
import sys

SIGNED_ROWS = 111
SIGNED_ROWS_BASIS = ("the signed set as of 2026-11-16: pass-1 74 + pass-2 26 + pass-3 3 + "
                     "pass-3-r2 3 + the 5-span return 5 = 111 rows (74 distinct span ids). A file "
                     "in dr-voluminous; if the signed set grows, this constant and CEILING are "
                     "re-derived there and restated here, by a human.")
CEILING = int(SIGNED_ROWS * 0.10)          # 11. Chris's number.
WINDOW = 2                                 # reading (b), see the module docstring.

# THE CEILING'S POPULATION, AND WHY `check` WILL NOT TAKE A COUNT FROM THE TREE ALONE.
# Chris, 2026-11-23: "The ceiling of 11 applies to the signed-set measurement on the
# dr-voluminous side (8, under the ceiling). The public hook ratchets the syntactic count at
# 25. Do not compare 25 with 11; change `check` so it cannot."
#
# It now cannot. `check` takes the signed ids as a REQUIRED argument -- no default, so a call
# without them is a TypeError, not a verdict -- and scopes the tree's hits to that set before
# it compares anything. There is no path by which the syntactic total reaches the comparison.
# A function that derives its own input fails silently; this one cannot derive it at all,
# because the population is not readable from this repository, by design.
SIGNED_DISTINCT = 74
SIGNED_DISTINCT_BASIS = (
    "the %d signed rows carry 74 distinct span ids: pass-1 signs 74, and the later passes "
    "re-sign ids already in it. The ceiling is 10%% of the ROW count, Chris's number; the "
    "scoped measurement counts DISTINCT ids, so the population handed to `check` must be "
    "those 74 -- a shorter one would lower the count and turn a refusal into a pass."
    % SIGNED_ROWS)

# THE RATCHET, AND WHY IT IS A SECOND NUMBER. Chris, 2026-11-22, item 3: "the public hook ratchets
# the syntactic count (it may not rise above today's), and the check against the signed set and the
# ceiling of 11 runs on the dr-voluminous side."
#
# CEILING is Chris's number over the SIGNED SET -- the population this module cannot read, because a
# public repo's guard must not need the private one. RATCHET is this tree's own count of what the
# guard CAN see: span-shaped ids with Hebrew near them, a conservative superset. One tree scores 8
# against the ceiling and 25 against the ratchet, and neither number is wrong; they are about
# different populations, which is the whole reason the rule was split in two.
#
# The ratchet may be LOWERED whenever the tree carries fewer, and may never rise. Lowering it is the
# point: a ratchet that is never tightened is a ceiling with a nicer name.
RATCHET = 25
RATCHET_BASIS = ("measured over this repository's tracked tree on 2026-11-22 (branch "
                 "apparatus-next, clean, at the band-rule commit): 25 distinct span-shaped ids "
                 "with Hebrew within %d line(s). Split against dr-voluminous on 2026-11-16, which "
                 "this module cannot do: 8 SIGNED rows (7.2%% of the 111, under the ceiling), 14 "
                 "census spans nobody has signed, 3 not spans at all. The number is a measurement "
                 "of this tree, not a judgement about it." % WINDOW)
# The membership as of that measurement. The ratchet Chris ruled is on the COUNT, so this list is
# not the gate: it is what lets a refusal say WHICH id is new instead of only that one more exists.
# A count pin cannot see a substitution -- one id leaving as another arrives -- and this list can,
# so the refusal reports it even though the rule does not refuse it.
RATCHET_SET = (
    "p1:n0", "p102:n0", "p138:n5", "p138:n6", "p217:n2", "p233:n4", "p254:n1", "p293:n0",
    "p379:n2", "p423:n3", "p427:n4", "p442:n0", "p491:n1", "p493:n3", "p594:n0", "p596:n2",
    "p619:n0", "p628:n2", "p726:n3", "p803:n0", "p895:n0", "p897:n4", "p900:n4", "p910:n3",
    "p912:n2")

# The state of the guard, on the artifact rather than in a report only. A guard that refuses every
# commit is not installed by the lane that wrote it.
WIRING = ("RULED AND INSTALLED, 2026-11-22. Chris, item 3: the public hook ratchets the "
          "syntactic count and the signed-set check runs on the dr-voluminous side. So the hook "
          "invokes `ratchet`, which is this module's DEFAULT command. Chris's second ruling the "
          "same day: Lane B INSTALLS the block in .githooks/pre-commit itself, on apparatus-next, "
          "with a born-test (test_precommit_span_ratchet.py); the change request to Lane A is "
          "WITHDRAWN, and A1 carries the same block to main with 0.3.4. `check` stays here as the "
          "ceiling's definition and its "
          "refusal text, and is what the dr-voluminous side runs, because that side can see both "
          "populations. Withheld before the split because it was being applied to the wrong "
          "population -- the syntactic count -- which would have refused every commit in both "
          "lanes. Chris, 2026-11-23: the ceiling applies to the SIGNED-SET measurement, the hook "
          "ratchets the syntactic count, and the two numbers are not to be compared; `check` was "
          "changed so that it cannot, by taking the signed population as a required argument. "
          "The ceiling is still not widened, the window is still not narrowed to the same line, "
          "and the hook is still never given the signed list.")

COMMANDS = ("selftest", "report", "check", "ratchet")

# The hook is invoked with no argument, so this is the gate Chris's item 3 wired: the ratchet over
# the syntactic count. `check` -- the ceiling of 11 over the signed set -- is explicit, because the
# population it measures is not readable from here.
DEFAULT_CMD = "ratchet"

MAX_BYTES = 4 * 1024 * 1024

ID = re.compile(r"p\d{1,4}:n\d{1,3}")
HEB = re.compile(u"[֐-׿יִ-ﭏ]")


def ids_with_hebrew(text, window=WINDOW):
    """The distinct span ids in `text` that have a Hebrew character within `window` lines.

    Pure: takes the text, returns a set. The born-test feeds it fixtures, which is the only way to
    prove a guard fires -- a guard proved by a green run over the current tree has been proved to
    agree with the tree, not to refuse anything.
    """
    lines = text.splitlines()
    heb = [bool(HEB.search(ln)) for ln in lines]
    out = {}
    for i, ln in enumerate(lines):
        found = ID.findall(ln)
        if not found:
            continue
        lo, hi = max(0, i - window), min(len(lines), i + window + 1)
        if any(heb[lo:hi]):
            for m in found:
                out.setdefault(m, i + 1)
    return out


def _git(args, cwd=None, binary=False):
    p = subprocess.Popen(["git"] + args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    o, e = p.communicate()
    if p.returncode:
        raise RuntimeError("git %s: %s" % (" ".join(args[:3]), e.decode("utf-8", "replace")[:300]))
    return o if binary else o.decode("utf-8", "replace")


def staged_tree(cwd=None):
    """{path: staged text} for every file the commit would leave in the repository.

    Reads the INDEX (`git ls-files -s`, then the blob by its id), not the working copy, so a file
    staged and then edited is counted as it will be committed. Binary and oversized blobs are
    skipped and RETURNED SEPARATELY rather than silently: a skip the caller cannot see is a hole.
    """
    files, skipped = {}, []
    for line in _git(["ls-files", "-s"], cwd=cwd).splitlines():
        if not line.strip():
            continue
        meta, path = line.split("\t", 1)
        sha = meta.split()[1]
        try:
            size = int(_git(["cat-file", "-s", sha], cwd=cwd).strip())
        except RuntimeError:
            skipped.append((path, "unreadable"))
            continue
        if size > MAX_BYTES:
            skipped.append((path, "%d bytes" % size))
            continue
        raw = _git(["cat-file", "blob", sha], cwd=cwd, binary=True)
        if b"\0" in raw[:8000]:
            skipped.append((path, "binary"))
            continue
        files[path] = raw.decode("utf-8", "replace")
    return files, skipped


FASTPATH = (u"THE FAST PATH AND WHAT IT RESTS ON. A whole-tree scan costs 23 s (measured "
            u"2026-11-22, 425 files), and a 23 s pre-commit hook gets uninstalled. The window "
            u"never crosses a file, so the tree count can only RISE if a blob this commit adds or "
            u"modifies carries a span id with Hebrew within the window: reading only the staged "
            u"blobs is a NECESSARY CONDITION, not a proxy. It does not establish that the tree is "
            u"under the pin -- only that this commit did not raise the count. That rests on the "
            u"previous commit having passed the same gate, and on the dr-voluminous gate "
            u"re-measuring the WHOLE tree before every push. `ratchet full` forces the full scan, "
            u"and a commit that reached the branch WITHOUT PASSING THIS GATE is caught there, not "
            u"here.")


def ids_from_staged(texts):
    u"""The span ids with Hebrew in a {path: staged text} map. Pure; the git part is separate."""
    out = {}
    for path, text in texts.items():
        for sid, lineno in ids_with_hebrew(text).items():
            out.setdefault(sid, []).append("%s:%d" % (path, lineno))
    return out


def staged_blobs(cwd=None):
    u"""{path: text} for the blobs this commit ADDS or MODIFIES, with skips returned separately."""
    out, skipped = {}, []
    names = [l for l in _git(["diff", "--cached", "--name-only", "--diff-filter=AM"],
                             cwd=cwd).splitlines() if l.strip()]
    for path in names:
        try:
            raw = _git(["show", ":" + path], cwd=cwd, binary=True)
        except RuntimeError:
            skipped.append((path, "unreadable from the index"))
            continue
        if len(raw) > MAX_BYTES:
            skipped.append((path, "%d bytes" % len(raw)))
            continue
        if b"\0" in raw[:8000]:
            skipped.append((path, "binary"))
            continue
        out[path] = raw.decode("utf-8", "replace")
    return out, skipped


def measure(cwd=None):
    files, skipped = staged_tree(cwd)
    hits = {}
    for path, text in files.items():
        for sid, lineno in ids_with_hebrew(text).items():
            hits.setdefault(sid, []).append("%s:%d" % (path, lineno))
    return hits, files, skipped


class SignedSetUnavailable(Exception):
    u"""The signed population is not readable, so the ceiling cannot be applied to anything.

    This is "cannot decide", which is neither a pass nor a refusal, and it is raised rather than
    returned so no caller can mistake it for a count.
    """


def signed_ids_from_exports(paths):
    u"""(frozenset of signed span ids, [(file, n)]) read from signing exports the caller NAMES.

    The paths come from the command line. This repository holds none of them and must not: a guard
    in a public repo that needs a path into the private one is a guard that is skipped on the
    machine that matters.

    Raises rather than returning a short set. A shrunken population lowers the scoped count and
    turns a refusal into a pass, which is the fail-open this whole rule exists to prevent --
    unknown is not clean.
    """
    if not paths:
        raise SignedSetUnavailable("no signing export was named, so the ceiling has no population")
    ids, per = set(), []
    for p in paths:
        if not os.path.exists(p):
            raise SignedSetUnavailable("named export does not exist: %s" % p)
        here = set()
        for line in io.open(p, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError as exc:
                raise SignedSetUnavailable("%s is not one JSON object per line: %s" % (p, exc))
            sid = row.get("span_id")
            if not sid or not ID.match(str(sid)):
                raise SignedSetUnavailable(
                    "a row of %s carries no span id, so these rows are not that population" % p)
            here.add(sid)
        if not here:
            raise SignedSetUnavailable("named export is empty: %s" % p)
        per.append((os.path.basename(p), len(here)))
        ids |= here
    if len(ids) != SIGNED_DISTINCT:
        raise SignedSetUnavailable(
            "the named exports carry %d distinct signed ids, not the %d the ceiling of %d rests "
            "on. %s  A different signed set needs a ceiling re-derived where that set is "
            "readable, and restated here by a human. Per export: %s"
            % (len(ids), SIGNED_DISTINCT, CEILING, SIGNED_DISTINCT_BASIS,
               ", ".join("%s %d" % t for t in per)))
    return frozenset(ids), per


def check(signed_ids, cwd=None, out=sys.stdout):
    u"""0 if the SIGNED-SCOPED count is at or under the ceiling, 1 if over. Fails CLOSED.

    `signed_ids` is required and has no default, which is the whole point: the ceiling is a number
    about the signed set, the syntactic count is the ratchet's population, and this function is
    handed the one and cannot reach the other's total. The two numbers are not comparable and
    nothing here can compare them.
    """
    if not signed_ids:
        raise SignedSetUnavailable("check() was handed an empty signed population")
    try:
        hits, files, skipped = measure(cwd)
    except Exception as exc:                                    # noqa: BLE001
        out.write("########################################################################\n")
        out.write("# COMMIT REFUSED -- the Hebrew span ceiling could not be measured.\n")
        out.write("#   %s\n" % exc)
        out.write("# A guard that cannot run must not pass. Fix the measurement and commit\n")
        out.write("# again; the whole tree is measured before every push either way.\n")
        out.write("########################################################################\n")
        return 1
    hits = dict((sid, where) for sid, where in hits.items() if sid in signed_ids)
    n = len(hits)
    if n <= CEILING:
        # A pass should say what it asserts, and what it does not.
        out.write("# ceiling: %d of the %d SIGNED ids appear with Hebrew within %d line(s) in the "
                  "resulting tree; the ceiling is %d. At or under.\n"
                  % (n, len(signed_ids), WINDOW, CEILING))
        if n:
            out.write("# they are: %s\n" % " ".join(sorted(hits)))
        out.write("# This is a statement about the SIGNED set and nothing else. The syntactic "
                  "count is a different population with its own pin -- `ratchet full` -- and it "
                  "is not measured against this number.\n")
        return 0
    out.write("########################################################################\n")
    out.write("# COMMIT REFUSED -- too much of the Hebrew truth set would be in this\n")
    out.write("# PUBLIC repository. Law 1 (Chris, 2026-11-16): the truth set as a whole\n")
    out.write("# lives only in dr-voluminous; this repo may carry small samples.\n")
    out.write("#\n")
    out.write("# SIGNED span ids with Hebrew within %d line(s), in the resulting tree: %d\n"
              % (WINDOW, n))
    out.write("# CEILING: %d -- 10%% of the %d signed rows, Chris's number.\n"
              % (CEILING, SIGNED_ROWS))
    out.write("# Scored over the %d signed ids the caller named. Ids in the tree that are\n"
              % len(signed_ids))
    out.write("# not in that population are not counted here at all: they belong to the\n")
    out.write("# ratchet's population, and the two counts are not comparable.\n")
    out.write("#\n")
    for sid in sorted(hits):
        out.write("#   %-12s %s\n" % (sid, ", ".join(sorted(hits[sid])[:4])))
    if skipped:
        out.write("# not scanned (%d): %s\n"
                  % (len(skipped), ", ".join("%s [%s]" % s for s in skipped[:4])))
    out.write("# Move the rows named above to dr-voluminous, then commit again.\n")
    out.write("########################################################################\n")
    return 1


def ratchet(cwd=None, out=sys.stdout, full=False):
    """0 if the resulting tree is at or under RATCHET, 1 if it has risen. Fails CLOSED.

    This is the PUBLIC hook's gate (Chris, 2026-11-22, item 3). It does not know the signed set and
    does not pretend to: it refuses a tree that carries MORE span-shaped ids with Hebrew than the
    tree did on the day the number was measured. The ceiling of 11 is a different rule about a
    different population and runs where both populations are readable."""
    if not full:
        try:
            texts, fskip = staged_blobs(cwd)
            staged_ids = ids_from_staged(texts)
        except Exception as exc:                                    # noqa: BLE001
            out.write("RATCHET FAILED CLOSED on the fast path: %s\n" % exc)
            return 1
        if not staged_ids:
            # A skip the caller cannot see is a hole, so the skip says what it rests on.
            out.write("# ratchet: no staged blob carries a span id with Hebrew within %d line(s), "
                      "so this commit cannot have raised the count of %d.\n"
                      % (WINDOW, RATCHET))
            if fskip:
                out.write("# staged blobs not read (%d): %s\n"
                          % (len(fskip), "; ".join("%s [%s]" % t for t in fskip[:4])))
            out.write("# This is NOT a measurement of the tree. The tree is measured in full "
                      "before every push, by the dr-voluminous side.\n")
            return 0
    try:
        hits, files, skipped = measure(cwd)
    except Exception as exc:                                    # noqa: BLE001
        out.write("########################################################################\n")
        out.write("# COMMIT REFUSED -- the Hebrew span ratchet could not be measured.\n")
        out.write("#   %s\n" % exc)
        out.write("# A guard that cannot run must not pass. Fix the measurement and commit\n")
        out.write("# again; the whole tree is measured before every push either way.\n")
        out.write("########################################################################\n")
        return 1
    n = len(hits)
    arrived = sorted(set(hits) - set(RATCHET_SET))
    left = sorted(set(RATCHET_SET) - set(hits))
    if n <= RATCHET:
        # DISCLOSURE, NOT A GATE. Two things the rule does not refuse but nobody should have to go
        # looking for: that the ratchet can now be tightened, and that the membership moved while
        # the count did not.
        if n < RATCHET:
            out.write("note: the Hebrew span ratchet can be lowered from %d to %d "
                      "(hebrew_span_ceiling.RATCHET, with RATCHET_SET and its basis).\n"
                      % (RATCHET, n))
        elif arrived:
            out.write("note: the Hebrew span ratchet is unchanged at %d, but its membership moved "
                      "-- arrived %s, left %s.\n" % (n, " ".join(arrived), " ".join(left)))
        return 0
    out.write("########################################################################\n")
    out.write("# COMMIT REFUSED -- this PUBLIC repository would carry MORE of the Hebrew\n")
    out.write("# truth set than it did when the ratchet was measured. Law 1 (Chris,\n")
    out.write("# 2026-11-16): the truth set as a whole lives only in dr-voluminous.\n")
    out.write("#\n")
    out.write("# distinct span ids with Hebrew within %d line(s), in the resulting tree: %d\n"
              % (WINDOW, n))
    out.write("# RATCHET: %d -- %s\n" % (RATCHET, RATCHET_BASIS))
    out.write("#\n")
    out.write("# This is NOT the ceiling. That is a different rule over the signed set,\n")
    out.write("# with its own number, checked on the dr-voluminous side where that set is\n")
    out.write("# readable. This count is not comparable with it, so it is not printed\n")
    out.write("# beside it.\n")
    out.write("#\n")
    for sid in arrived:
        out.write("#   ARRIVED  %-12s %s\n" % (sid, ", ".join(sorted(hits[sid])[:4])))
    if not arrived:
        out.write("#   no id is new, so the rise is in the count alone -- re-measure.\n")
    if left:
        out.write("#   (left since the measurement: %s)\n" % " ".join(left))
    if skipped:
        out.write("# not scanned (%d): %s\n"
                  % (len(skipped), ", ".join("%s [%s]" % s for s in skipped[:4])))
    out.write("# Put the row named above in dr-voluminous, then commit again.\n")
    out.write("########################################################################\n")
    return 1


def check_cli(argv, out=sys.stdout):
    u"""`check <signing export> [...]` -- the ceiling, over the population those exports name.

    Returns 2 when that population is not readable. Two is not a pass and not a refusal: it is the
    guard saying it has not been given the thing it is about, which is the only honest answer from
    a repository that cannot hold it.
    """
    paths = [a for a in argv[2:] if not a.startswith("-")]
    try:
        signed, per = signed_ids_from_exports(paths)
    except SignedSetUnavailable as exc:
        out.write("########################################################################\n")
        out.write("# CANNOT DECIDE -- the ceiling is a rule about the SIGNED set, and the\n")
        out.write("# signed set is not readable from this repository.\n")
        out.write("#   %s\n" % exc)
        out.write("# Run this command from the side that holds the signing exports, naming\n")
        out.write("# them:   hebrew_span_ceiling.py check <export.jsonl> ...\n")
        out.write("# The count this repository CAN measure is a different population with its\n")
        out.write("# own pin -- `ratchet full`. It is not comparable with the ceiling, and this\n")
        out.write("# command will not stand in for that one.\n")
        out.write("########################################################################\n")
        return 2
    out.write("# signed population: %d distinct ids from %s\n"
              % (len(signed), ", ".join("%s (%d)" % t for t in per)))
    return check(signed, _repo(), out=out)


def report(cwd=None):
    hits, files, skipped = measure(cwd)
    print("ceiling %d (10%% of %d signed rows) | window %d line(s) | files scanned %d, skipped %d"
          % (CEILING, SIGNED_ROWS, WINDOW, len(files), len(skipped)))
    print("distinct span ids with Hebrew in the resulting tree: %d  (ratchet %d, %s)"
          % (len(hits), RATCHET,
             "at the pin" if len(hits) == RATCHET else
             "RISEN -- the hook refuses" if len(hits) > RATCHET else "below: lower the pin"))
    for sid in sorted(hits):
        print("  %-12s %s" % (sid, ", ".join(sorted(hits[sid]))))
    for p, why in skipped:
        print("  skipped: %-50s %s" % (p, why))
    # The same tree under the two readings this module rejected, so the choice stays measurable.
    same = set()
    anyfile = set()
    for path, text in files.items():
        same |= set(ids_with_hebrew(text, 0))
        if HEB.search(text):
            anyfile |= set(ID.findall(text))
    print("for comparison -- same line only: %d | any id in a file holding Hebrew: %d"
          % (len(same), len(anyfile)))
    return len(hits)


# ----------------------------------------------------------------------------- the born test
def selftest():
    n, f = [0], [0]

    def ck(name, cond, extra=""):
        n[0] += 1
        if cond:
            print("  ok    %s" % name)
        else:
            f[0] += 1
            print("  FAIL  %s   %s" % (name, extra))

    print("(1) the ceiling, and where it comes from")
    ck("the ceiling is Chris's number: 10%% of the %d signed rows = %d" % (SIGNED_ROWS, CEILING),
       (SIGNED_ROWS, CEILING) == (111, 11), (SIGNED_ROWS, CEILING))
    ck("the basis of the 111 is stated in the module, naming the five exports",
       all(w in SIGNED_ROWS_BASIS for w in ("pass-1 74", "pass-2 26", "pass-3-r2 3", "2026-11-16")))
    ck("the ceiling's POPULATION is named and pinned: 74 distinct ids behind the 111 rows",
       SIGNED_DISTINCT == 74 and "74 distinct span ids" in SIGNED_DISTINCT_BASIS,
       SIGNED_DISTINCT)
    ck("the ceiling is restated in the refusal a human reads, with its basis",
       all(s in _refusal_text() for s in ("CEILING: 11", "10% of the 111 signed rows")),
       _refusal_text()[:80])

    print("")
    print("(2) what counts: the id must have Hebrew NEAR it")
    HE = u"גלוליכם"
    ck("an id on a line with Hebrew counts",
       set(ids_with_hebrew(u'row("p442:n0", u"%s")' % HE)) == {"p442:n0"})
    ck("an id with Hebrew on the NEXT line counts -- a line break must not defeat the guard",
       set(ids_with_hebrew(u'  "span": "p442:n0",\n  "text": u"%s",' % HE)) == {"p442:n0"})
    ck("an id with no Hebrew within the window does NOT count",
       set(ids_with_hebrew(u'def test_p442_n0():\n    assert span == "p442:n0"\n')) == set())
    ck("Hebrew far away in the same file does not make an id count (reading (c) was rejected)",
       set(ids_with_hebrew(u'"p442:n0"\n' + u"\n" * 40 + u'u"%s"\n' % HE)) == set())
    ck("the window is symmetric: Hebrew on the PRECEDING line counts",
       set(ids_with_hebrew(u'u"%s"\n"p442:n0"\n' % HE)) == {"p442:n0"})
    ck("the count is DISTINCT ids, not occurrences",
       len(ids_with_hebrew(u'"p442:n0" u"%s"\n"p442:n0" u"%s"\n' % (HE, HE))) == 1)
    ck("two ids on one Hebrew-bearing line both count",
       set(ids_with_hebrew(u'"p442:n0","p628:n2",u"%s"' % HE)) == {"p442:n0", "p628:n2"})
    ck("presentation-form Hebrew counts too (שׁ is not in the main block)",
       set(ids_with_hebrew(u'"p442:n0" u"שׁ"')) == {"p442:n0"})

    print("")
    print("(3) the guard FIRES -- proved by mutation, not by a green tree")
    over = u"\n".join(u'row("p%d:n1", u"%s")' % (100 + i, HE) for i in range(CEILING + 1))
    at = u"\n".join(u'row("p%d:n1", u"%s")' % (100 + i, HE) for i in range(CEILING))
    ck("a fixture one over the ceiling measures %d" % (CEILING + 1),
       len(ids_with_hebrew(over)) == CEILING + 1, len(ids_with_hebrew(over)))
    ck("a fixture AT the ceiling measures %d -- the boundary is tested on both sides" % CEILING,
       len(ids_with_hebrew(at)) == CEILING, len(ids_with_hebrew(at)))
    ck("`check` refuses the over-ceiling tree and prints every id",
       _check_over(over) == (1, True), _check_over(over))
    ck("`check` passes the at-ceiling tree", _check_over(at)[0] == 0, _check_over(at))
    ck("`check` fails CLOSED: a measurement that raises refuses the commit",
       _check_raises() == 1)

    print("")
    print("(3b) the ceiling is about the SIGNED set, and `check` CANNOT reach the other count")
    # Chris, 2026-11-23: "Do not compare 25 with 11; change `check` so it cannot."
    ck("`check` cannot be called without a signed population -- the argument is required, with "
       "no default, so a call that omits it is a TypeError and not a verdict",
       _raises(TypeError, lambda: check(out=_Sink())))
    ck("`check` refuses an EMPTY population instead of scoring 0 against the ceiling",
       _raises(SignedSetUnavailable, lambda: check(frozenset(), out=_Sink())))
    # The mutation that matters: a tree carrying as many ids as the ratchet pins, of which only
    # eight are signed -- the live state Chris described on 2026-11-23. If anything still
    # compared the syntactic total with the ceiling, this would refuse, and the number would be
    # in the text. The ids are synthetic and even-numbered so that none of them can CONTAIN the
    # syntactic total as a substring; otherwise the check below could pass or fail by accident.
    _tree = ["p%d:n1" % (800 + 2 * i) for i in range(RATCHET)]
    ck("the fixture cannot fake the next check: no id in it contains the syntactic total",
       not any(str(RATCHET) in i for i in _tree), _tree[:3])
    _rc_scoped, _body_scoped = _check_scoped(_tree, _tree[:8])
    ck("a tree with %d ids of which 8 are signed PASSES: the ceiling scores the signed ones"
       % RATCHET, _rc_scoped == 0, (_rc_scoped, _body_scoped[:70]))
    ck("and the syntactic total appears NOWHERE in what `check` prints, so the two numbers "
       "cannot be read as a comparison",
       str(RATCHET) not in _body_scoped,
       [l for l in _body_scoped.splitlines() if str(RATCHET) in l])
    ck("the pass says what it asserts: the signed count, the population it scored, and that the "
       "syntactic count is a different population with its own pin",
       all(x in _body_scoped for x in ("SIGNED ids", "ceiling is %d" % CEILING,
                                       "ratchet full", "not measured against this number")),
       _body_scoped[:120])
    _rc_sover, _body_sover = _check_scoped(_tree, _tree[:CEILING + 1])
    ck("the ceiling still FIRES when the SIGNED-scoped count goes over it",
       _rc_sover == 1 and "COMMIT REFUSED" in _body_sover, _rc_sover)
    ck("that refusal names the population it scored, and says the other count is not comparable",
       "signed ids the caller named" in _body_sover and "not comparable" in _body_sover,
       [l for l in _body_sover.splitlines() if "comparable" in l])
    # The loader is the other half: the ceiling rests on 74 ids, so a shorter population must not
    # be accepted -- it would lower the count and turn a refusal into a pass.
    ck("the loader refuses when no export is named", _loader_refuses([]))
    ck("the loader refuses an export that does not exist", _loader_refuses(["no_such_file.jsonl"]))
    ck("the loader refuses an EMPTY export", _loader_refuses([_tmp_jsonl([])]))
    ck("the loader refuses rows that carry no span id -- those rows are not that population",
       _loader_refuses([_tmp_jsonl([{"note": "no id here"}])]))
    ck("the loader refuses a population that is NOT the %d the ceiling rests on, however well "
       "formed it is" % SIGNED_DISTINCT,
       _loader_refuses([_tmp_jsonl([{"span_id": "p%d:n1" % i} for i in range(SIGNED_DISTINCT - 1)])]))
    ck("the loader ACCEPTS exactly %d distinct ids" % SIGNED_DISTINCT,
       not _loader_refuses([_tmp_jsonl([{"span_id": "p%d:n1" % i} for i in range(SIGNED_DISTINCT)])]))
    _rc_cli, _body_cli = _check_cli([])
    ck("`check` with no export CANNOT DECIDE: exit 2, which is neither a pass nor a refusal",
       _rc_cli == 2 and "CANNOT DECIDE" in _body_cli, (_rc_cli, _body_cli[:60]))
    ck("and it says it will not stand in for the ratchet, so nobody reads a 2 as a clean tree",
       all(x in _body_cli for x in ("not comparable", "will not stand in", "ratchet full")),
       _body_cli[-200:])
    ck("the cannot-decide text names no bypass either",
       not any(w in _body_cli.lower() for w in ("no-verify", "override", "bypass")))

    print("")
    print("(4) the live tree -- and which gate the ruling wired")
    try:
        hits, files, skipped = measure(_repo())
        # THE GUARD REFUSES THIS REPOSITORY AS IT STANDS. Measured 2026-11-16: 25 distinct span ids
        # carry Hebrew within 2 lines, against a ceiling of 11. The ceiling is not wrong and is not
        # touched; the two numbers are not the same measurement. Chris's 10% is 10% of the SIGNED
        # set, and the signed set is 74 distinct ids in the private repo; this guard counts span ids
        # by SYNTAX, because a public repo's hook must not need the private one, so it also counts
        # ids that were never signed and strings that are not spans at all (p1:n0).
        #
        # Three things were available and are still refused: widening the ceiling (it is Chris's
        # number), narrowing the window to the same line (6 signed ids -- chosen because it passes,
        # which is fitting a threshold to the rows it has to admit), and gating on the signed list
        # (the hook would then read the private repo). Chris ruled the split on 2026-11-22: the
        # public hook ratchets THIS count, and the ceiling of 11 is enforced where the signed set
        # is readable. So the measurement below still stands and is still disclosed -- it is the
        # basis of the pin, not a passing grade.
        ck("the live count is measured, not assumed: %d distinct ids with Hebrew within %d lines"
           % (len(hits), WINDOW), isinstance(len(hits), int) and len(hits) > 0, sorted(hits)[:6])
        # Re-anchored 2026-11-22 on the ruled state. The two numbers are two measurements over
        # two populations, and the thing to watch is that the module keeps saying so in words: the
        # live count is over the ceiling, the ceiling is not what this hook enforces, and nothing
        # here pretends the pin is the ceiling met.
        # This check used to assert `len(hits) > CEILING`, which is the comparison Chris ruled
        # out on 2026-11-23: it put the syntactic count and the ceiling in one expression. What
        # is asserted now is that the module says in words which rule is about which population
        # and which side runs it -- no number of one is weighed against the number of the other.
        ck("the module keeps the two RULES apart in words: which population each is about, and "
           "which side runs which",
           all(x in WIRING for x in ("SIGNED-SET measurement", "syntactic count",
                                     "not to be compared", "dr-voluminous side", "ratchets")),
           WIRING[:80])
        ck("the scan read this repository's tracked code, not an empty tree",
           len(files) >= 100 and "pipeline/reextract/hebrew_glyph_card.py" in files,
           (len(files), "pipeline/reextract/hebrew_glyph_card.py" in files))
        # A skip is a hole in the count, so it is counted and shown rather than trusted.
        ck("every file not scanned is named with a reason", all(len(s) == 2 and s[1] for s in skipped),
           skipped[:3])
    except Exception as exc:                                    # noqa: BLE001
        ck("the live tree could be measured", False, exc)

    print("")
    print("(5) what the guard does not claim")
    ck("the module states that Hebrew without a span id is invisible to it",
       "cannot see Hebrew that travels WITHOUT a span id" in (__doc__ or ""))
    ck("the module states that history is not covered, and names the artifact that measures it",
       "LAW1_span_leak_measure_20261116.json" in (__doc__ or ""))
    # The private repo must not be reachable from a PUBLIC repo's hook. Asserted over the AST's
    # string constants, excluding this module's own docstring, and the forbidden names are
    # ASSEMBLED FROM PIECES: a check written as `"<name>" not in source` is satisfied by nothing,
    # because its own literal puts the name in the source. (Hit twice before in this lane.)
    import ast
    bad_bits = ("reextract" + "_" + "vol1", "C:" + "/Users", "dr-" + "voluminous" + "/")
    tree = ast.parse(io.open(__file__, encoding="utf-8").read())
    body = list(tree.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]                       # the module docstring, which is prose, not a path
    strings = [x.value for b in body for x in ast.walk(b)
               if isinstance(x, ast.Constant) and isinstance(x.value, str)]
    ck("no path into the private repository is reachable from this module's CODE",
       not [s for s in strings if any(b in s for b in bad_bits)],
       [s[:50] for s in strings if any(b in s for b in bad_bits)])
    print("")
    print("(6) the ratchet: the number the PUBLIC hook enforces")
    _live = len(measure(_repo())[0])
    ck("the ratchet is a measurement of this tree, and it still is: pinned %d, live %d"
       % (RATCHET, _live), RATCHET == _live, (RATCHET, _live))
    ck("the pinned MEMBERSHIP is this tree's too, so a refusal can name what is new",
       set(RATCHET_SET) == set(measure(_repo())[0]),
       sorted(set(RATCHET_SET) ^ set(measure(_repo())[0])))
    ck("the basis says when it was measured and what the 25 are made of",
       all(x in RATCHET_BASIS for x in ("2026-11-22", "8 SIGNED", "14 census", "3 not spans")))
    # `RATCHET > CEILING` was asserted here. It is the forbidden comparison in an assert, and
    # it would also be FALSE on a tree that carries almost nothing -- the day the ratchet is
    # lowered past 11 this test would have failed for the right tree. What is asserted instead is
    # that the basis names the split between the two populations.
    ck("the ratchet's basis names the split, so the two populations stay distinguishable: the "
       "signed rows it contains, and that they were under the ceiling",
       all(x in RATCHET_BASIS for x in ("8 SIGNED", "under the ceiling", "different populations"))
       or all(x in RATCHET_BASIS for x in ("8 SIGNED", "under the ceiling")),
       RATCHET_BASIS[:90])
    ck("the ratchet ADMITS a tree at exactly the pin", _ratchet_over(RATCHET)[0] == 0)
    ck("the ratchet ADMITS a tree below the pin, and says it can be lowered",
       _ratchet_over(RATCHET - 3)[0] == 0 and "can be lowered" in _ratchet_over(RATCHET - 3)[1],
       _ratchet_over(RATCHET - 3)[1][:60])
    _rc_up, _body_up = _ratchet_over(RATCHET + 1)
    ck("the ratchet REFUSES a tree one id over the pin -- proved by mutation, not by a green run",
       _rc_up == 1 and "COMMIT REFUSED" in _body_up, _rc_up)
    ck("the refusal NAMES the id that arrived, and says it is not the ceiling",
       "ARRIVED" in _body_up and "NOT the ceiling" in _body_up,
       [l for l in _body_up.splitlines() if "ARRIVED" in l or "ceiling" in l])
    ck("the ratchet fails CLOSED when it cannot measure", _ratchet_raises() == 1)

    # The fast path is a NECESSARY CONDITION, not a proxy: the window never crosses a file, so a
    # commit that stages no id-with-Hebrew blob cannot have raised the tree count. What it does
    # not establish is stated in FASTPATH and checked below.
    ck("the fast path sees an id with Hebrew in a staged blob",
       list(ids_from_staged({"a.py": u"p9:n1 %s" % _HEB1})) == ["p9:n1"])
    ck("a staged blob with a BARE id does not trip the fast path",
       ids_from_staged({"a.py": u"p9:n1 and nothing else"}) == {})
    ck("a staged blob with Hebrew and no id does not trip it either",
       ids_from_staged({"a.py": _HEB1}) == {})
    _rc_fast, _body_fast = _ratchet_fast(staged={})
    ck("with nothing staged that could raise the count, the ratchet SKIPS the full scan",
       _rc_fast == 0 and "cannot have raised" in _body_fast, _body_fast[:70])
    ck("the skip says it is NOT a measurement, and names where the tree is measured in full",
       "NOT a measurement" in _body_fast and "dr-voluminous" in _body_fast)
    _rc_slow, _body_slow = _ratchet_fast(staged={"a.py": u"p9:n1 %s" % _HEB1})
    ck("with such a blob staged, the ratchet does NOT skip: it measures",
       "cannot have raised" not in _body_slow, _body_slow[:70])
    ck("`ratchet full` ignores the fast path entirely",
       "cannot have raised" not in _ratchet_fast(staged={}, full=True)[1])
    ck("the fast path's basis and its limit are stated on the artifact",
       all(x in FASTPATH for x in ("NECESSARY CONDITION", "not establish", "before every push",
                                   "WITHOUT PASSING THIS GATE")))
    ck("a substitution at an unchanged count is DISCLOSED, since the rule does not refuse it",
       "membership moved" in _ratchet_sub(), _ratchet_sub()[:60])
    # The first version of this check read the last `sys.exit(` line and was GREEN while the
    # default was still `check`. It now goes through `main`, so what it reports is the branch the
    # hook reaches. Every name in the table is dispatchable, and an unknown one refuses.
    ck("the DEFAULT command is the ratchet, so a hook invoked without an argument enforces the "
       "rule that was ruled, not the ceiling it was not given the inputs for",
       _default_cmd() == "ratchet" and DEFAULT_CMD == "ratchet", _default_cmd())
    ck("every named command is reachable through the dispatch",
       all(_cmd_reached([None, c]) == c for c in COMMANDS), COMMANDS)
    ck("an unrecognised command REFUSES instead of falling through to a gate nobody named",
       main([None, "chekc"], handlers=dict((k, lambda: 0) for k in COMMANDS)) == 2)
    ck("the module states the wiring: installed by this lane, and the request withdrawn",
       all(x in WIRING for x in ("RULED AND INSTALLED", "WITHDRAWN", "apparatus-next", "DEFAULT",
                                 "never given the signed list")))

    # Chris, 2026-11-22 (second ruling): "a refusal names the count and the files, not the bypass."
    # Checked over the bytes a human would READ, on all four refusal paths, not over the source --
    # a hint reintroduced in any one of them fails this.
    _bodies = _refusal_bodies()
    ck("no refusal path names a bypass: not the flag, not the word",
       not [k for k, b in _bodies.items()
            if "no-verify" in b or "override" in b.lower() or "bypass" in b.lower()],
       [k for k, b in _bodies.items() if "no-verify" in b or "override" in b.lower()])
    ck("each of the four refusals is still a refusal, and says so in the first line a human reads",
       all("COMMIT REFUSED" in b for b in _bodies.values()), sorted(_bodies))
    ck("the two refusals that MEASURED something name the count and the file it is in",
       all(x in _bodies["ceiling over"] for x in ("resulting tree: %d" % (CEILING + 1), "f.py:1"))
       and all(x in _bodies["ratchet over"] for x in ("resulting tree: %d" % (RATCHET + 1),
                                                      "fixture.py:1")),
       (_bodies["ceiling over"][:60], _bodies["ratchet over"][:60]))
    ck("the two that could NOT measure name the reason instead, since there is no count to name",
       all("git is not here" in _bodies[k] for k in ("ceiling closed", "ratchet closed")))

    print("")
    ck("born-test check count is pinned, so a raise cannot quietly shorten the suite",
       n[0] == 67, n[0])   # counted before this one; one more in all

    print("")
    print("%s: %d/%d checks" % ("PASS" if not f[0] else "FAIL", n[0] - f[0], n[0]))
    return f[0]


def _repo():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _Sink(object):
    u"""Collects what a human would be shown, so a refusal can be asserted over its bytes."""

    def __init__(self):
        self.b = []

    def write(self, x):
        self.b.append(x)

    def text(self):
        return "".join(self.b)


def _raises(exc, fn):
    try:
        fn()
    except exc:
        return True
    except Exception:                                           # noqa: BLE001
        return False
    return False


def _with_measure(hits, fn):
    u"""Run `fn` with a synthetic measurement in place. One seam, used by every mutation below."""
    g = globals()
    real = g["measure"]
    try:
        g["measure"] = lambda cwd=None: (dict((i, ["fixture.py:1"]) for i in hits),
                                         {"fixture.py": u""}, [])
        return fn()
    finally:
        g["measure"] = real


def _check_scoped(tree_ids, signed_ids):
    u"""(rc, what a human sees) for a tree carrying `tree_ids` when `signed_ids` are the signed."""
    s = _Sink()
    rc = _with_measure(tree_ids, lambda: check(frozenset(signed_ids), out=s))
    return rc, s.text()


def _tmp_jsonl(rows):
    u"""A throwaway signing export, written where temporary files go on this machine."""
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + u"\n")
    return path


def _loader_refuses(paths):
    return _raises(SignedSetUnavailable, lambda: signed_ids_from_exports(paths))


def _check_cli(paths):
    u"""(rc, what a human sees) for `check` invoked with these export paths and nothing else."""
    s = _Sink()
    return check_cli(["hebrew_span_ceiling.py", "check"] + list(paths), out=s), s.text()


def _refusal_text():
    class S(object):
        def __init__(self):
            self.b = []

        def write(self, s):
            self.b.append(s)
    s = S()

    class Fake(dict):
        pass
    # Force the over-ceiling branch with a synthetic measurement.
    global measure
    real = measure
    try:
        _ids = ["p%d:n1" % (100 + i) for i in range(CEILING + 1)]
        measure = lambda cwd=None: (dict((i, ["f.py:1"]) for i in _ids), {}, [])
        # Every id in the fixture is signed, so the scoped count is the fixture's count: the
        # refusal text under test is the one a real over-ceiling signed tree would produce.
        check(frozenset(_ids), out=s)
    finally:
        measure = real
    return "".join(s.b)


def _check_over(text):
    class S(object):
        def __init__(self):
            self.b = []

        def write(self, x):
            self.b.append(x)
    s = S()
    global measure
    real = measure
    try:
        hits = {}
        for sid, ln in ids_with_hebrew(text).items():
            hits.setdefault(sid, []).append("fixture.py:%d" % ln)
        measure = lambda cwd=None: (hits, {"fixture.py": text}, [])
        rc = check(frozenset(hits), out=s)
    finally:
        measure = real
    body = "".join(s.b)
    return rc, all(sid in body for sid in ids_with_hebrew(text))


def _ratchet_over(count):
    """(rc, what a human sees) for a synthetic tree carrying `count` ids with Hebrew."""
    class S(object):
        def __init__(self):
            self.b = []

        def write(self, x):
            self.b.append(x)
    s = S()
    ids = list(RATCHET_SET)[:count]
    while len(ids) < count:                      # over the pin: the extra ids are NEW
        ids.append("p%d:n9" % (1000 + len(ids)))
    global measure
    real = measure
    try:
        measure = lambda cwd=None: (dict((i, ["fixture.py:1"]) for i in ids), {}, [])
        rc = ratchet(out=s, full=True)   # the measuring path, not the fast path
    finally:
        measure = real
    return rc, "".join(s.b)


def _ratchet_sub():
    """What a human sees when the count holds but one id has been swapped for another."""
    class S(object):
        def __init__(self):
            self.b = []

        def write(self, x):
            self.b.append(x)
    s = S()
    ids = list(RATCHET_SET)[:-1] + ["p1001:n9"]
    global measure
    real = measure
    try:
        measure = lambda cwd=None: (dict((i, ["fixture.py:1"]) for i in ids), {}, [])
        ratchet(out=s, full=True)
    finally:
        measure = real
    return "".join(s.b)


_HEB1 = u"\u05d0\u05db\u05dc"


def _ratchet_fast(staged, full=False):
    u"""Run `ratchet` with a synthetic staged set, to exercise the fast path by mutation."""
    class S(object):
        def __init__(self):
            self.buf = []

        def write(self, x):
            self.buf.append(x)
    g = globals()
    real_blobs, real_measure = g["staged_blobs"], g["measure"]
    try:
        g["staged_blobs"] = lambda cwd=None: (staged, [])
        g["measure"] = lambda cwd=None: (dict((s, ["fixture.py:1"]) for s in RATCHET_SET),
                                         {"fixture.py": u""}, [])
        s = S()
        return ratchet(out=s, full=full), u"".join(s.buf)
    finally:
        g["staged_blobs"], g["measure"] = real_blobs, real_measure


def _ratchet_raises():
    class S(object):
        def write(self, x):
            pass
    global measure
    real = measure
    try:
        def boom(cwd=None):
            raise RuntimeError("git is not here")
        measure = boom
        return ratchet(out=S(), full=True)
    finally:
        measure = real


def _closed_body(fn):
    u"""What a human reads when the measurement itself fails -- the fail-CLOSED refusal."""
    class S(object):
        def __init__(self):
            self.b = []

        def write(self, x):
            self.b.append(x)
    s = S()
    g = globals()
    real = g["measure"]
    try:
        def boom(cwd=None):
            raise RuntimeError("git is not here")
        g["measure"] = boom
        fn(out=s, full=True) if fn is ratchet else fn(frozenset(["p1:n0"]), out=s)
    finally:
        g["measure"] = real
    return "".join(s.b)


def _refusal_bodies():
    u"""Every refusal a human can be shown by this module, keyed by which one it is."""
    return {"ceiling over": _refusal_text(),
            "ratchet over": _ratchet_over(RATCHET + 1)[1],
            "ceiling closed": _closed_body(check),
            "ratchet closed": _closed_body(ratchet)}


def _default_cmd():
    """Which command the hook runs when it passes no argument.

    This used to read the last `sys.exit(` line of the __main__ block. It was GREEN while the line
    that actually decides still said `check`: the probe resembled the dispatch instead of being it,
    and a hook with no argument would have run the ceiling this repo cannot supply the inputs for.
    It now puts recording handlers through `main` itself and reports the branch that was reached.
    """
    seen = []

    def rec(name):
        return lambda: seen.append(name) or 0

    main(["hebrew_span_ceiling.py"], handlers=dict((k, rec(k)) for k in COMMANDS))
    return seen[0] if len(seen) == 1 else seen


def _cmd_reached(argv):
    """Which branch `main` dispatches for this argv, recorded by the dispatch rather than read."""
    seen = []
    main(argv, handlers=dict((k, (lambda n: lambda: seen.append(n) or 0)(k)) for k in COMMANDS))
    return seen[0] if len(seen) == 1 else seen


def _check_raises():
    class S(object):
        def write(self, x):
            pass
    global measure
    real = measure
    try:
        def boom(cwd=None):
            raise RuntimeError("git is not here")
        measure = boom
        return check(frozenset(["p1:n0"]), out=S())
    finally:
        measure = real


def main(argv, handlers=None):
    """Dispatch. One table, one named default, so what a check can ask is what the hook will do.

    `handlers` is the seam: a check passes recording handlers to learn which branch an empty argv
    reaches, without running the gate. An unrecognised command returns 2 rather than falling
    through to a gate nobody named -- a mistyped hook invocation should refuse, not enforce
    something else.
    """
    cmd = argv[1] if len(argv) > 1 else DEFAULT_CMD
    live = {
        "selftest": lambda: selftest(),
        "report": lambda: report(_repo()) or 0,
        # The CEILING, over the signed set, which this side cannot read: the exports are
        # NAMED on the command line by the side that holds them. Not the hook's gate, not the
        # default, and it returns 2 -- cannot decide -- rather than a verdict without them.
        "check": lambda: check_cli(argv),
        "ratchet": lambda: ratchet(_repo(), full=(len(argv) > 2 and argv[2] == "full")),
    }
    table = handlers if handlers is not None else live
    if cmd not in table:
        sys.stderr.write("hebrew_span_ceiling: unknown command %r; one of %s\n"
                         % (cmd, ", ".join(COMMANDS)))
        return 2
    return table[cmd]()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
