# -*- coding: utf-8 -*-
u"""The standard header every Lane B report carries.

Chris, 2026-11-08: "Reprint 'Lane B / session id' at the top of every report." A report that does
not say which lane and which session produced it cannot be traced back to the run that measured it
-- and this project has two lanes writing into one data repo, so "a Lane B report" is not something
a filename can be trusted to establish.

`session` is a REQUIRED argument and there is no default. A session id read from the environment
would silently become wrong the first time a script was run from somewhere that does not set it,
and a wrong session id is worse than a missing one: it attributes a measurement to a run that did
not make it. A caller that does not know its session id cannot call this.

The FILE-pages line is part of the header for the same reason it is in the standing reporting rule:
every page number in every Lane B report is a file page, and a report that does not say so invites
the reader to subtract 88 twice or not at all.
"""
import time

FILE_PAGE_RULE = u"All page numbers are FILE pages (printed = file − 88)."


def header(title, session, built_from=None, supersedes=None, when=None):
    u"""Return the report's opening lines as a list of strings, without trailing newlines.

    title       the report's own title, without a leading '#'
    session     this session's id as ListAgents prints it, e.g. 'goat-yard-archive-eb [aca358]'
    built_from  one line naming what produced the figures (modules, commit), or None
    supersedes  one line naming the report this replaces and what of it is withdrawn, or None
    when        a time tuple for the stamp; defaults to now. Passed only by the selftest, which
                cannot assert against a clock it does not control.
    """
    if not title or not title.strip():
        raise ValueError("a report needs a title")
    if not session or not session.strip():
        raise ValueError("a report must name the session that produced it; there is no default")
    stamp = time.strftime("%Y-%m-%d %H:%M", when or time.localtime())
    out = [
        u"# %s" % title.strip(),
        u"",
        u"**Lane B** · session `%s` · %s" % (session.strip(), stamp),
        u"",
        FILE_PAGE_RULE,
    ]
    if built_from:
        out += [u"", built_from.strip()]
    if supersedes:
        out += [u"", supersedes.strip()]
    return out


def selftest():
    u"""Checks that the header cannot be produced without a lane and a session."""
    n = [0, 0]

    def check(ok, msg):
        n[0] += 1
        if not ok:
            n[1] += 1
        print(u"  %-5s %s" % (u"ok" if ok else u"FAIL", msg))

    fixed = time.struct_time((2026, 11, 8, 9, 30, 0, 5, 312, -1))
    h = header(u"A title", u"goat-yard-archive-eb [aca358]", when=fixed)
    check(h[0] == u"# A title", "the title is the first line")
    check(u"**Lane B**" in h[2], "the lane is named")
    check(u"goat-yard-archive-eb [aca358]" in h[2], "the session id is reprinted verbatim")
    check(u"2026-11-08 09:30" in h[2], "the stamp comes from the given time, not the clock")
    check(FILE_PAGE_RULE in h, "the FILE-pages rule is in the header")

    for bad, what in ((u"", "an empty session"), (u"   ", "a whitespace session"), (None, "None")):
        try:
            header(u"A title", bad)
            check(False, "%s is refused" % what)
        except ValueError:
            check(True, "%s is refused" % what)
    try:
        header(u"", u"s")
        check(False, "an empty title is refused")
    except ValueError:
        check(True, "an empty title is refused")

    # A caller cannot reach the header by positional accident: session has no default, so omitting
    # it is a TypeError rather than a report that quietly claims no session.
    try:
        header(u"A title")
        check(False, "omitting the session is a TypeError, not a default")
    except TypeError:
        check(True, "omitting the session is a TypeError, not a default")

    # 10, not 11: the argument is evaluated before check() increments, so this one counts
    # the ten before it. An off-by-one here would make the count assertion itself the
    # failure and hide whatever it was meant to catch.
    check(n[0] == 10, "selftest ran every one of its checks (%d before this one)" % n[0])
    print(u"%d checks, %d failed" % (n[0], n[1]))
    return n[1]


if __name__ == "__main__":
    import sys
    sys.exit(1 if selftest() else 0)
