# -*- coding: utf-8 -*-
"""`git_state()` at the start AND the end of a run, so an artifact can say whether it is citable.

The clean-run rule binding both lanes: **a run is clean only if the state at start and at end are both
clean and identical. A run over a dirty tree, or one where HEAD or the tree moved mid-run, is PROVISIONAL
and cannot be cited in an ADR or a tier change.**

This records that rather than asserting it, because a provisional local run is still worth having -- it
just has to say so inside the artifact instead of in a sentence somebody has to remember. The pair is the
point: a single capture at the start cannot see a commit landing while a six-minute census is running.

It lives in its own module and not beside the first generator that needed it, because `import draw_pool`
to borrow a helper would RUN the draw -- the generators are scripts whose work is at module level. A
rule-bearing helper that two artifacts' provenance depends on is also not something to duplicate: one
definition, so a correction reaches every artifact that quotes the rule.
"""
from run_header import _git_dirty, _git_head


def git_state(where=None):
    """`{git_head, git_dirty, clean}`. `clean` is True only on a literal `clean` state from git.

    Never hand-roll the dirty check: git already knows about autocrlf, and `_git_dirty` returns a dict
    (`clean` / `dirty`+paths / `unknown`), where `unknown` is NOT clean -- not knowing is not the same as
    knowing it was clean."""
    d = _git_dirty(where)
    return {"git_head": _git_head(where), "git_dirty": d,
            "clean": isinstance(d, dict) and d.get("state") == "clean"}


def provisional(start, end):
    """True when the run cannot be cited: either end was dirty, or the tree/HEAD moved mid-run."""
    return not (start.get("clean") and end.get("clean") and start == end)


def banner(start, end):
    """One line for the run log, stating the verdict rather than leaving it to be inferred."""
    return "git: start %s %s -> end %s %s  =>  %s" % (
        start["git_head"][:7], start["git_dirty"].get("state"),
        end["git_head"][:7], end["git_dirty"].get("state"),
        "PROVISIONAL (not citable in an ADR or a tier change)"
        if provisional(start, end) else "clean run")
