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

# The state of the guard, on the artifact rather than in a report only. A guard that refuses every
# commit is not installed by the lane that wrote it.
WIRING = ("WITHHELD, 2026-11-16. Run over this repository's tracked tree the count is 25 distinct "
          "span ids with Hebrew within 2 lines, against the ceiling of 11, so wiring this into "
          ".githooks/pre-commit would refuse every commit in both lanes. The ceiling is Chris's "
          "number and is not widened; the window is not narrowed to the same line (6 signed ids) "
          "because choosing a window by which rows it admits is fitting; and the hook is not given "
          "the signed list because a PUBLIC repo's hook must not need the private one. The hook "
          "change is requested once Chris rules on which population the ceiling governs: the 74 "
          "distinct signed ids, or every span-shaped id in the tree.")
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


def measure(cwd=None):
    files, skipped = staged_tree(cwd)
    hits = {}
    for path, text in files.items():
        for sid, lineno in ids_with_hebrew(text).items():
            hits.setdefault(sid, []).append("%s:%d" % (path, lineno))
    return hits, files, skipped


def check(cwd=None, out=sys.stdout):
    """0 if the resulting tree is at or under the ceiling, 1 if it is over. Fails CLOSED."""
    try:
        hits, files, skipped = measure(cwd)
    except Exception as exc:                                    # noqa: BLE001
        out.write("########################################################################\n")
        out.write("# COMMIT REFUSED -- the Hebrew span ceiling could not be measured.\n")
        out.write("#   %s\n" % exc)
        out.write("# A guard that cannot run must not pass. Fix it, or override knowingly:\n")
        out.write("#   git commit --no-verify\n")
        out.write("########################################################################\n")
        return 1
    n = len(hits)
    if n <= CEILING:
        return 0
    out.write("########################################################################\n")
    out.write("# COMMIT REFUSED -- too much of the Hebrew truth set would be in this\n")
    out.write("# PUBLIC repository. Law 1 (Chris, 2026-11-16): the truth set as a whole\n")
    out.write("# lives only in dr-voluminous; this repo may carry small samples.\n")
    out.write("#\n")
    out.write("# distinct span ids with Hebrew within %d line(s), in the resulting tree: %d\n"
              % (WINDOW, n))
    out.write("# CEILING: %d -- 10%% of the %d signed rows, Chris's number.\n"
              % (CEILING, SIGNED_ROWS))
    out.write("#\n")
    for sid in sorted(hits):
        out.write("#   %-12s %s\n" % (sid, ", ".join(sorted(hits[sid])[:4])))
    if skipped:
        out.write("# not scanned (%d): %s\n"
                  % (len(skipped), ", ".join("%s [%s]" % s for s in skipped[:4])))
    out.write("# Move the rows to dr-voluminous, or override knowingly:\n")
    out.write("#   git commit --no-verify\n")
    out.write("########################################################################\n")
    return 1


def report(cwd=None):
    hits, files, skipped = measure(cwd)
    print("ceiling %d (10%% of %d signed rows) | window %d line(s) | files scanned %d, skipped %d"
          % (CEILING, SIGNED_ROWS, WINDOW, len(files), len(skipped)))
    print("distinct span ids with Hebrew in the resulting tree: %d" % len(hits))
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
    print("(4) the live tree -- and why the wiring is WITHHELD")
    try:
        hits, files, skipped = measure(_repo())
        # THE GUARD REFUSES THIS REPOSITORY AS IT STANDS. Measured 2026-11-16: 25 distinct span ids
        # carry Hebrew within 2 lines, against a ceiling of 11. The ceiling is not wrong and is not
        # touched; the two numbers are not the same measurement. Chris's 10% is 10% of the SIGNED
        # set, and the signed set is 74 distinct ids in the private repo; this guard counts span ids
        # by SYNTAX, because a public repo's hook must not need the private one, so it also counts
        # ids that were never signed and strings that are not spans at all (p1:n0).
        #
        # Three things were available and are refused: widening the ceiling (it is Chris's number),
        # narrowing the window to the same line (6 signed ids -- chosen because it passes, which is
        # fitting a threshold to the rows it has to admit), and gating on the signed list (the hook
        # would then read the private repo). So the measurement stands, the count is DISCLOSED here
        # and in the report, and WIRING says the hook change is not requested until Chris rules on
        # which population the ceiling governs.
        ck("the live count is measured, not assumed: %d distinct ids with Hebrew within %d lines"
           % (len(hits), WINDOW), isinstance(len(hits), int) and len(hits) > 0, sorted(hits)[:6])
        ck("the module DISCLOSES that the live tree is over the ceiling and withholds the wiring",
           "WITHHELD" in WIRING and str(CEILING) in WIRING and "25" in WIRING, WIRING[:60])
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
    ck("born-test check count is pinned, so a raise cannot quietly shorten the suite",
       n[0] == 23, n[0])   # 23 counted before this one; 24 in all

    print("")
    print("%s: %d/%d checks" % ("PASS" if not f[0] else "FAIL", n[0] - f[0], n[0]))
    return f[0]


def _repo():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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
        measure = lambda cwd=None: (dict((("p%d:n1" % (100 + i)), ["f.py:1"])
                                         for i in range(CEILING + 1)), {}, [])
        check(out=s)
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
        rc = check(out=s)
    finally:
        measure = real
    body = "".join(s.b)
    return rc, all(sid in body for sid in ids_with_hebrew(text))


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
        return check(out=S())
    finally:
        measure = real


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "selftest":
        sys.exit(selftest())
    if cmd == "report":
        report(_repo())
        sys.exit(0)
    sys.exit(check(_repo()))
