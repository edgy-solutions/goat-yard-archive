"""Born tests for the quote/citation pairing regex, in BOTH directions.

`bot.QUOTE_WITH_CITE_RE` decides whether a cited sentence has a quote attached to
it. If it does not pair, `_repair_quotes_in_answer` emits
`no_gill_quote_for_citation`, `main` sets `verified=False`, and the eval's
`must_be_verified` gate fails the run. So this one regex sits in front of both the
product's verification badge and every off/on measurement.

Gill's prose is full of nested quotation. A span quoted far enough ends with the
SOURCE's closing mark immediately followed by the answer's own -- `&c.""  [SID]` --
and the single-mark closer could not match that, so the citation read as bare and
the MORE faithful answer scored worse. Nine instances were measured across 108
recorded eval answers; the five distinct ones are embedded below verbatim.

The fix widens the CLOSER to a run of marks. It deliberately does not widen the
capture group, so this file tests the second direction too: a genuinely bare
citation, a quote the model never opened, a single-quote opener, a gap with a
newline, a gap over the 80-char limit, a KJV-only quote, a paraphrase in quote
marks, and a SID that is not in the context must ALL still fail. A repair that
also lets bad citations through is not a repair.

`_try_repair_quote_llm` is monkeypatched off in every full-function test. It calls
BAML on the LocalRouter; a test that reaches a model endpoint is neither hermetic
nor allowed to pick an endpoint on its own.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import bot  # noqa: E402
from backend.bot import QUOTE_WITH_CITE_RE  # noqa: E402

# The closer before the fix: exactly one quote mark. Kept here so the tests can
# show that these instances failed BEFORE and pair AFTER -- the defect itself is
# under test, not just the current behaviour.
OLD_RE = re.compile(
    r'["“”]([^"“”]+)["“”][^"“”\n\[\]]{0,80}\[([A-Z0-9_]+_S\d+)\]'
)

# The five distinct recorded instances, copied verbatim out of
# evals/output/off_vs_on_rerun{2,3}_20261004/on/*.json (representative runs).
# Each runs from the mark the regex would use as the opener through the SID.
RECORDED = [
    ("atonement/EXODUS_30_10_S00",
     '" to any other service."" [EXODUS_30_10_S00]'),
    ("election/JOHN_6_39_S00",
     '"and he (i. e. God) shall order it all, וְנִסְפַּר '
     'יַעֲקֹב כַּעֲפַר, and not any '
     'thing shall be lost, but all shall rise again; for, lo, it is said, Dan. xii. 2. '
     'and many of them that sleep in the dust, &c."" [JOHN_6_39_S00]'),
    ("garden/GENESIS_2_15_S01",
     '"and he placed him in the garden of Eden, to serve in the law, and keep the '
     'commands of it."" [GENESIS_2_15_S01]'),
    ("garden/LUKE_23_43_S01",
     '"the souls of the fathers, or patriarchs have rest, and in a moment, immediately '
     'enter into their separate places, or apartments, and not as the rest of the souls; '
     'of whom it is said, all the twelve months the soul ascends and descends, (goes to '
     'and fro,) but the souls of the fathers, דרפורד דימ, '
     'immediately, upon their separation, return to God that gave them,"" [LUKE_23_43_S01]'),
    ("garden/GENESIS_3_24_S00",
     '" and he placed him, or caused him (Adam) to dwell over-against the paradise of '
     'pleasure, and he ordered the cherubim."" [GENESIS_3_24_S00]'),
]


def _no_llm_repair():
    """Disable the BAML repair path for the duration of a test."""
    saved = bot._try_repair_quote_llm
    bot._try_repair_quote_llm = lambda quote_raw, source_text: None
    return saved


def _restore(saved):
    bot._try_repair_quote_llm = saved


# --------------------------------------------------------------------------
# Direction 1: the measured defect is gone
# --------------------------------------------------------------------------

def test_recorded_nested_close_instances_pair_now():
    for label, frag in RECORDED:
        m = QUOTE_WITH_CITE_RE.search(frag)
        assert m is not None, "still unpaired: %s" % label
        sid = frag[frag.rindex("[") + 1:frag.rindex("]")]
        assert m.group(2) == sid, (label, m.group(2), sid)
        assert m.group(1).strip(), "empty capture: %s" % label
        # The capture is the span the verifier checks against Gill, so it has to
        # be the actual text and not a stray mark.
        assert m.group(1) in frag, label
        assert '"' not in m.group(1), "capture must not hold a mark: %s" % label


def test_recorded_nested_close_instances_did_not_pair_before():
    """The defect, stated as a test: the old closer matched none of these."""
    for label, frag in RECORDED:
        assert OLD_RE.search(frag) is None, "fixture does not exercise the bug: %s" % label


def test_the_minimal_nested_close_shape_pairs():
    m = QUOTE_WITH_CITE_RE.search('"in the dust, &c."" [JOHN_6_39_S00]')
    assert m is not None
    assert m.group(1) == "in the dust, &c."
    assert m.group(2) == "JOHN_6_39_S00"


def test_doubled_opener_does_not_lose_the_citation():
    """A doubled OPENER is not what was fixed, but it must not lose the citation."""
    m = QUOTE_WITH_CITE_RE.search('""a real place"" [GENESIS_2_8_S01]')
    assert m is not None
    assert m.group(1) == "a real place"
    assert m.group(2) == "GENESIS_2_8_S01"


def test_nested_close_now_credits_the_gill_obligation():
    saved = _no_llm_repair()
    try:
        gill = ('The Targum paraphrases it, "and many of them that sleep in the dust, '
                '&c." and so concludes the matter.')
        answer = 'Gill writes: "and many of them that sleep in the dust, &c."" [JOHN_6_39_S00]'
        _, _, failures = bot._repair_quotes_in_answer(
            answer, {"[JOHN_6_39_S00]": {"gill": gill, "kjv": ""}})
        assert failures == [], failures
    finally:
        _restore(saved)


# --------------------------------------------------------------------------
# Direction 2: everything that should still fail, still fails
# --------------------------------------------------------------------------

def test_capture_cannot_span_two_separate_quotes():
    """The mis-pairing the single-mark closer was protecting against.

    This is guaranteed by the capture group, not by the closer: group 1 excludes
    every quote mark, so it cannot reach back across an earlier quote.
    """
    m = QUOTE_WITH_CITE_RE.search('"first thing" and "second thing" [GENESIS_2_8_S01]')
    assert m is not None
    assert m.group(1) == "second thing", m.group(1)


def test_bare_citation_still_fails_loudly():
    saved = _no_llm_repair()
    try:
        _, _, failures = bot._repair_quotes_in_answer(
            "Gill explains the garden at length. [GENESIS_2_8_S01]",
            {"[GENESIS_2_8_S01]": {"gill": "the garden of Eden was a real place", "kjv": ""}})
        assert [f["reason"] for f in failures] == ["no_gill_quote_for_citation"], failures
    finally:
        _restore(saved)


def test_quote_the_model_never_opened_still_does_not_pair():
    """A measured shape (nf2/john_baptist): the model emitted only a closing mark.

    The regex is right to refuse this one, and the fix must not start accepting it
    by scavenging the previous pair's closing mark as an opener.
    """
    answer = ('he "hath a devil" [LUKE_7_33_S00]. This same person was expected to '
              'come before the Messiah" [MATTHEW_11_14_S00]')
    sids = [m.group(2) for m in QUOTE_WITH_CITE_RE.finditer(answer)]
    assert sids == ["LUKE_7_33_S00"], sids


def test_single_quote_opener_still_does_not_pair():
    """The other measured shape (pf2/real_gill_aquinas): opened with an apostrophe.

    Accepting ' as a delimiter would mis-pair on every possessive in the corpus
    ("Peter's wife's mother"), so this stays a failure.
    """
    answer = "Gill references 'and the snail; so the word is rendered\" [LEVITICUS_11_30_S00]"
    assert QUOTE_WITH_CITE_RE.search(answer) is None


def test_gap_with_a_newline_still_does_not_pair():
    answer = '"a real place"\n\n[GENESIS_2_8_S01]'
    assert QUOTE_WITH_CITE_RE.search(answer) is None


def test_gap_over_the_eighty_char_limit_still_does_not_pair():
    assert QUOTE_WITH_CITE_RE.search('"a real place" ' + "x" * 81 + ' [GENESIS_2_8_S01]') is None
    assert QUOTE_WITH_CITE_RE.search('"a real place" ' + "x" * 70 + ' [GENESIS_2_8_S01]') is not None


def test_paraphrase_in_quote_marks_still_fails_as_not_verbatim():
    saved = _no_llm_repair()
    try:
        _, _, failures = bot._repair_quotes_in_answer(
            '"Gill teaches the eternal decree of election."" [GENESIS_2_8_S01]',
            {"[GENESIS_2_8_S01]": {"gill": "the garden of Eden was a real place", "kjv": ""}})
        reasons = sorted(f["reason"] for f in failures)
        assert "quote_not_verbatim" in reasons, failures
        assert "no_gill_quote_for_citation" in reasons, failures
    finally:
        _restore(saved)


def test_kjv_only_quote_still_does_not_credit_the_gill_obligation():
    saved = _no_llm_repair()
    try:
        _, _, failures = bot._repair_quotes_in_answer(
            '"In the beginning God created the heaven and the earth."" [GENESIS_1_1_S00]',
            {"[GENESIS_1_1_S00]": {
                "gill": "Gill comments at length on the work of the first day.",
                "kjv": "In the beginning God created the heaven and the earth."}})
        assert [f["reason"] for f in failures] == ["no_gill_quote_for_citation"], failures
    finally:
        _restore(saved)


def test_cited_sid_absent_from_context_is_still_its_own_failure():
    saved = _no_llm_repair()
    try:
        _, _, failures = bot._repair_quotes_in_answer(
            '"a real place"" [GENESIS_9_9_S09]',
            {"[GENESIS_2_8_S01]": {"gill": "a real place", "kjv": ""}})
        assert [f["reason"] for f in failures] == ["cited_sid_not_in_context"], failures
    finally:
        _restore(saved)


# A hand-rolled suite reports what it happened to collect. If a test is renamed out
# of the test_ prefix, deleted, or shadowed by a duplicate name, the run still
# prints "N passed, 0 failed" and looks healthy. Assert the COUNT.
EXPECTED_TESTS = 14

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try:
            fn()
            p += 1
            print("  PASS %s" % fn.__name__)
        except Exception:
            f += 1
            print("  FAIL %s" % fn.__name__)
            traceback.print_exc()
    print("")
    print("%d passed, %d failed" % (p, f))
    if len(fns) != EXPECTED_TESTS:
        print("FAIL suite: collected %d tests, expected %d - a test was lost or added "
              "without updating EXPECTED_TESTS" % (len(fns), EXPECTED_TESTS))
        f += 1
    raise SystemExit(1 if f else 0)
