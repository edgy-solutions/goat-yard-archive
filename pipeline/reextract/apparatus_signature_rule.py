# -*- coding: utf-8 -*-
"""The one source of the "may this signature be called complete / full-span" rule (Lane B).

ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).

THE DIVISION. STRUCTURE COMPUTES THE FLAG; PROSE IS ENFORCED AS A REFUSAL, NOT RECORDED AS A FLAG.
`full_span_pixel_signature` is a fact about the verdicts the signer clicked -- tiles AND insertions -- and
is computed from those alone. A regex cannot adjudicate a sentence, so it must never be the thing that
decides a signature. It may only refuse to let a contradictory row (prose says part of the span is not in
the crop, no tile and no insertion says so) be called complete. The old console computed the flag from
tiles alone and was wrong on 5 of 26 signed rows (pass 2); insertions carried no verdict at all.

Stdlib only, no I/O. `UNSIGNABLE_PATTERN` is the single string both Python (re) and the console's JS
(RegExp, flag i) are built from; it is injected into the JS, never typed twice.
"""
import re

UNSIGNABLE_PATTERN = (
    "not in crop|not_in_crop|outside box|outside the box|outside of the box|cut at|cuts the|edge[- ]cut"
    "|clipped|not in the crop|off the border|starts mid-word|starts in the middle|mid-word")
_RX = re.compile(UNSIGNABLE_PATTERN, re.I)


def prose_says_unsignable(note):
    """Case-insensitive search of UNSIGNABLE_PATTERN in the signer's note."""
    return bool(_RX.search(note or ""))


def _has_nic(items):
    return any((x or {}).get("verdict") == "not_in_crop" for x in (items or ()))


def full_span_pixel_signature(tiles, insertions):
    """STRUCTURE ONLY: True iff no tile AND no insertion carries verdict == "not_in_crop"."""
    return not (_has_nic(tiles) or _has_nic(insertions))


def contradicts(note, tiles, insertions):
    """True iff the prose says unsignable and nothing in either structure list carries not_in_crop."""
    return prose_says_unsignable(note) and full_span_pixel_signature(tiles, insertions)
