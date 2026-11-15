# -*- coding: utf-8 -*-
r"""Lane B writes in two places and nowhere else. This refuses the write, not the review.

Lane A owns the shared substrate and has its own worktrees beside ours. Nothing of Lane B's belongs
in them -- not a report, not a page, and least of all a `_mut_*` scratch copy from a mutation
harness, which is a file designed to be wrong.

Two roots are allowed:
  * this worktree (goatyard-laneB), for code and scratch copies that live beside the module under
    test, because a copied module needs its own directory on sys.path to import its siblings;
  * the audits directory in dr-voluminous, for the artifacts.

Everything else is refused BY PATH, before the bytes are written, which is the earliest point the
input exists. A check that runs afterwards tells you where the file went; this one means it never
went there.

`foreign_trees()` is the second half, for a harness that runs a mutated module as a SUBPROCESS: the
child does not call this module, so containment cannot be asserted from inside it. Snapshot the
other lanes' `git status --porcelain` around the run instead and compare -- a file dropped into one
of their trees shows up as a line that was not there before, whether or not their tree was clean to
begin with.
"""
import os
import subprocess
import pathlib

GIT = pathlib.Path("C:/Users/cnogr/git")
LANE_B = GIT / "goatyard-laneB"
AUDITS = pathlib.Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits")
ALLOWED = (LANE_B, AUDITS)


class WriteScopeError(Exception):
    """A write aimed outside Lane B's two roots. Not a warning: the write does not happen."""


def _real(p):
    # resolve(), so a path reaching another tree through `..` or a link is judged by where it LANDS.
    return pathlib.Path(os.path.realpath(str(p)))


def inside(path, root):
    p, r = _real(path), _real(root)
    return p == r or r in p.parents


def assert_inside(path, why=""):
    """Refuse `path` unless it is under one of Lane B's two roots. Returns the path, so it can wrap
    the write target in place: `io.open(assert_inside(OUT), "w")`."""
    if any(inside(path, r) for r in ALLOWED):
        return path
    raise WriteScopeError(
        "refusing to write outside Lane B: %s\n  resolves to %s\n  allowed roots: %s%s"
        % (path, _real(path), ", ".join(str(r) for r in ALLOWED),
           ("\n  " + why) if why else ""))


def foreign_roots():
    """Every sibling worktree that is not ours: the other lanes, and the shared checkout."""
    out = []
    for d in sorted(GIT.iterdir()) if GIT.exists() else []:
        if not d.is_dir() or _real(d) == _real(LANE_B):
            continue
        if d.name.startswith("goatyard-lane") or d.name == "goat-yard-archive":
            if (d / ".git").exists():
                out.append(d)
    return out


def foreign_trees():
    """{root: set of porcelain lines} for the trees Lane B must not touch."""
    s = {}
    for d in foreign_roots():
        r = subprocess.run(["git", "status", "--porcelain"], cwd=str(d), capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        s[str(d)] = set(l for l in (r.stdout or "").split("\n") if l.strip())
    return s


def assert_foreign_unchanged(before, label=""):
    """Compare a `foreign_trees()` snapshot with now. Names the lines that appeared, since that is
    the file somebody has to go and delete."""
    now, bad = foreign_trees(), []
    for root, lines in now.items():
        new = lines - before.get(root, set())
        if new:
            bad.append("%s: %s" % (root, ", ".join(sorted(new))))
    if bad:
        raise WriteScopeError("another lane's tree changed during %s:\n  %s"
                              % (label or "this run", "\n  ".join(bad)))
    return True


if __name__ == "__main__":
    import sys
    n = f = 0
    cases = [
        ("a path in the audits directory is allowed", lambda: assert_inside(AUDITS / "x.json"), True),
        ("a path in this worktree is allowed",
         lambda: assert_inside(LANE_B / "pipeline/reextract/_mut_x.py"), True),
        # The case this module exists for.
        ("a path in another lane's worktree is refused",
         lambda: assert_inside(GIT / "goatyard-laneA2/pipeline/reextract/_mut_x.html"), False),
        ("a path in the shared checkout is refused",
         lambda: assert_inside(GIT / "goat-yard-archive/x.html"), False),
        # Judged by where it LANDS, not by how it is spelled.
        ("a path reaching another tree through `..` is refused",
         lambda: assert_inside(LANE_B / "../goatyard-laneA2/x.html"), False),
        ("a path outside the git directory altogether is refused",
         lambda: assert_inside(pathlib.Path("C:/tmp/x.html")), False),
        # Liveness: a refusal that refused everything would pass every case above but the first two.
        ("the audits root itself is inside itself", lambda: assert_inside(AUDITS), True),
    ]
    for label, fn, want_ok in cases:
        try:
            fn()
            got = True
        except WriteScopeError:
            got = False
        ok = got == want_ok
        n += ok
        f += not ok
        print("  %-5s %s" % ("ok" if ok else "FAIL", label))
    roots = foreign_roots()
    ok = len(roots) >= 1
    n += ok
    f += not ok
    print("  %-5s foreign trees are actually found, so the snapshot says something: %s"
          % ("ok" if ok else "FAIL", [d.name for d in roots]))
    print("write-scope selftest: %s %d/%d" % ("PASS" if not f else "FAIL", n, n + f))
    sys.exit(1 if f else 0)
