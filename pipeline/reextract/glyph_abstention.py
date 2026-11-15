# -*- coding: utf-8 -*-
r"""glyph_abstention -- the signer saying "I cannot tell which letter this is", as a first-class verdict.

ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).

THE CASE. p628:n2's note is `could be vav or nun`. Its tile 1 shows the printed ן and carries
verdict `corrected`, `chose: ו`; the row's derived string is `בו`, `abstain` is False and `complete`
is True. So every structural channel presents a confident vav, and the only trace of the signer's
doubt is a sentence in a free-text note that nothing reads. A row like that ships an honest human's
"either of two letters" as a pipeline's "this letter" -- the signer's honesty turned into the
system's fabrication, which is the inverse of every fabricate-confidently guard in this lane.

Advisor ruling 2026-11-15 item 4: *"could be vav or nun" is an abstention. Give abstention a consumer
as a first-class row verdict with its stated reason. Do not widen UNSIGNABLE_PATTERN.*

TWO DIFFERENT KINDS OF DOUBT, TWO SEPARATE PATTERNS. `RULE.UNSIGNABLE_PATTERN` is about the BOX: how
much of the span the crop covers, a statement about coverage. This pattern is about the GLYPH: which
letter the ink is, a statement about identity. A crop can be perfect and the letter still unreadable,
and a letter can be obvious with half of it outside the box. Merging them would make one regex answer
two questions, and would move the numbers of every row already classified by the first.

PROSE REFUSES; IT DOES NOT FLAG. This lane's division (see apparatus_signature_rule) is that a regex
may not adjudicate a sentence, so it may never be the thing that DECIDES a signature -- only the thing
that REFUSES to let a contradictory row be called complete. The same holds here. This file never
rewrites a tile, never picks between the rivals and never scores anything. It computes one verdict,
and `ingest_pass2.admit_resigned` refuses the row while the verdict stands.

NARROW BY CONSTRUCTION. The verdict fires only when the note names TWO OR MORE letters and some
tile's effective reading IS one of them. A note doubting letters the signature does not claim is
doubt about something this row does not assert, and there is nothing to refuse: that is the
discriminating case in the selftest, and it is what keeps the pattern from becoming a blanket veto
over every note with the word "or" in it.

A NAME THIS FILE DOES NOT KNOW IS A REFUSAL, never a quietly smaller rival set: a table that silently
drops `qoph` would narrow the doubt the signer stated and let the row through on a technicality.
"""
import re
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import signature_attestation as SA                                        # noqa: E402  one tile reader


class GlyphAbstentionError(Exception):
    pass


# The glyph-identity doubt the signer writes in the note. Deliberately NOT UNSIGNABLE_PATTERN, which
# is about how much of the span the box holds. Every alternative here is a way of saying "which
# letter is this"; none of them is a way of saying "how much is in the crop".
ABSTENTION_PATTERN = (
    r"could be|may be|might be|can(?:no|')?t tell|cannot tell|unsure|not sure|uncertain"
    r"|hard to tell|too faint to tell|illegible|either\b|or possibly|possibly")
_RX = re.compile(ABSTENTION_PATTERN, re.I)

# The full consonant inventory, finals included. A plain name covers BOTH forms where a letter has a
# final: a signer who writes "nun" has not said which form, so the rival set holds both -- the wider,
# more conservative reading of their own words.
LETTER_NAMES = {
    "alef": u"א", "aleph": u"א", "bet": u"ב", "beth": u"ב", "vet": u"ב",
    "gimel": u"ג", "dalet": u"ד", "daleth": u"ד", "he": u"ה", "hey": u"ה",
    "heh": u"ה", "vav": u"ו", "waw": u"ו", "zayin": u"ז", "het": u"ח",
    "heth": u"ח", "chet": u"ח", "tet": u"ט", "teth": u"ט", "yod": u"י",
    "yud": u"י", "kaf": u"כך", "kaph": u"כך", "khaf": u"כך",
    "lamed": u"ל", "mem": u"מם", "nun": u"נן", "samekh": u"ס",
    "samech": u"ס", "ayin": u"ע", "pe": u"פף", "peh": u"פף",
    "fe": u"פף", "tsadi": u"צץ", "tzadi": u"צץ",
    "sadi": u"צץ", "qof": u"ק", "qoph": u"ק", "kof": u"ק",
    "resh": u"ר", "shin": u"ש", "sin": u"ש", "tav": u"ת", "taw": u"ת",
    "tau": u"ת",
}
# "final mem", "final nun", "final kaf", "final pe", "final tsadi" name ONE form each.
FINAL_FORMS = {"mem": u"ם", "nun": u"ן", "kaf": u"ך", "kaph": u"ך",
               "khaf": u"ך", "pe": u"ף", "peh": u"ף", "fe": u"ף",
               "tsadi": u"ץ", "tzadi": u"ץ", "sadi": u"ץ"}

_NAME_RX = re.compile(r"\b(final\s+|sofit\s+)?([a-z']{2,8})\b", re.I)

# The hedge's OWN clause: from the hedge to the end of its sentence, capped. The note field also
# carries long analytical prose that names letters freely ("the page prints tet, bet, tav"), and
# pairing a hedge in one sentence with names in another would invent a doubt nobody stated.
CLAUSE_CHARS = 90
_SENT_END = re.compile(r"[.;!?\n]")


def hedge_clause(note, m):
    """The text the hedge governs: from the match to the first sentence end, at most CLAUSE_CHARS."""
    tail = note[m.start():m.start() + CLAUSE_CHARS]
    e = _SENT_END.search(tail, 1)
    return tail[:e.start()] if e else tail
# Words that appear in these notes and are NOT attempts at a letter name. Anything else that is not
# in LETTER_NAMES is simply not a letter name either; only a word that LOOKS like one and is unknown
# raises, and that is decided by the caller asking for strictness.
_NOT_A_NAME = set("""could be may might can cant cannot tell unsure not sure uncertain hard to too
faint illegible either or possibly the this that a an is it and of in on at i think looks like
probably maybe perhaps first second third last letter glyph char one two three left right here
with word reading note crop box""".split())


def letters_named(note, strict_unknown=()):
    """The letters the note NAMES, in the order they appear, as (name, forms) pairs.

    `strict_unknown` is a tuple of words the caller asserts ARE letter names; any of them missing
    from the table raises instead of being dropped. The default is empty because an arbitrary note is
    full of ordinary English, and a file that raised on every word it did not recognise would refuse
    every note ever written."""
    out, seen = [], set()
    for m in _NAME_RX.finditer(note or ""):
        final, word = m.group(1), m.group(2).lower()
        if word in _NOT_A_NAME:
            continue
        if word not in LETTER_NAMES:
            if word in strict_unknown:
                raise GlyphAbstentionError(
                    "the note names %r, which this file's letter table does not hold. A name dropped "
                    "in silence would narrow the doubt the signer stated." % word)
            continue
        forms = FINAL_FORMS[word] if (final and word in FINAL_FORMS) else LETTER_NAMES[word]
        key = (word, bool(final))
        if key in seen:
            continue
        seen.add(key)
        out.append((("final " + word) if final else word, forms))
    return out


def verdict(row, strict_unknown=()):
    """The row's glyph-abstention verdict, or None.

    Returns a typed record: the signer's own sentence, the letters they named, and the tiles whose
    EFFECTIVE reading (SA.tile_out, the one tile reader in this lane) is one of those letters. The
    verdict exists only when the note names two or more letters AND the signature presents one of
    them: doubt about a letter this row does not claim is not a contradiction of this row."""
    note = row.get("note") or ""
    m = _RX.search(note)
    if not m:
        return None
    clause = hedge_clause(note, m)
    named = letters_named(clause, strict_unknown)
    if len(named) < 2:
        return None
    rivals = set("".join(f for _, f in named))
    presenting = []
    for t in row.get("tiles") or ():
        if t.get("kind") != "consonant":
            continue
        shown = SA.tile_out(t)
        if len(shown) == 1 and shown in rivals:
            presenting.append({"i": t["i"], "presents": shown, "printed": t.get("shown"),
                               "tile_verdict": t.get("verdict")})
    if not presenting:
        return None
    return {
        "verdict": "abstain_glyph_doubt",
        "reason": note.strip(),
        "reason_matched_on": m.group(0),
        "reason_clause": clause,          # the slice the rivals were read from; `reason` is the whole note
        "names": [n for n, _ in named],
        "rivals": "".join(sorted(rivals)),
        "tiles_presenting_a_rival": presenting,
        "means": "the signer's note says this glyph could be any of the letters named; the signature "
                 "presents one of them with no structural trace of the doubt",
        "what_would_lift_it": "a verdict in the STRUCTURE channel that carries the doubt -- an "
                              "abstention per tile, which the signing console does not yet offer -- "
                              "or an adjudication of the tile. Until then the prose and the "
                              "structure disagree and nothing here can say which is right.",
        "not_about_the_box": "this is a statement about which letter the ink is, not about how much "
                             "of the span the crop holds; RULE.UNSIGNABLE_PATTERN is untouched",
    }


# --------------------------------------------------------------------------------------- selftest
EXPECTED_CHECKS = 18


def selftest():
    n = [0]

    def ck(cond, msg):
        n[0] += 1
        if not cond:
            raise AssertionError("check %d: %s" % (n[0], msg))

    def tile(i, shown, v, chose=""):
        return {"i": i, "kind": "consonant", "shown": shown, "verdict": v, "chose": chose}

    # The real row, verbatim from the signed return: printed final nun, corrected to vav.
    p628 = {"span_id": "p628:n2", "note": "could be vav or nun",
            "tiles": [tile(0, u"ב", "confirmed"), tile(1, u"ן", "corrected", u"ו")]}
    v = verdict(p628)
    ck(v is not None, "p628:n2's note is an abstention and did not produce a verdict")
    ck(v["verdict"] == "abstain_glyph_doubt", "the verdict is named")
    ck(v["reason"] == "could be vav or nun", "the reason is the signer's own sentence, verbatim")
    ck(v["names"] == ["vav", "nun"], "the letters named, in the note's order: %s" % v["names"])
    ck(v["rivals"] == u"".join(sorted(u"ונן")),
       "a plain 'nun' covers both forms, so the rival set is vav + nun + final nun: %r" % v["rivals"])
    # A FINAL NAME NAMES ONE FORM. "nun" is both; "final nun" is only the final. Without this check
    # nothing distinguishes the two branches, and a table that collapsed them would widen every
    # rival set a signer deliberately narrowed.
    ck([f for _, f in letters_named("could be final nun or vav")] == [u"ן", u"ו"],
       "'final nun' names one form, a plain 'nun' both: %s"
       % letters_named("could be final nun or vav"))

    ck([t["i"] for t in v["tiles_presenting_a_rival"]] == [1]
       and v["tiles_presenting_a_rival"][0]["presents"] == u"ו"
       and v["tiles_presenting_a_rival"][0]["printed"] == u"ן",
       "tile 1 presents the chosen vav over a printed final nun: %s" % v["tiles_presenting_a_rival"])
    ck(v["what_would_lift_it"].strip(), "the verdict names what would lift it")

    # THE DISCRIMINATING CASE: doubt about letters this signature does not claim is not a
    # contradiction of this signature. Without it, any note with "or" in it would veto any row.
    other = dict(p628, note="could be dalet or resh")
    ck(verdict(other) is None,
       "doubt about dalet/resh fired on a row presenting neither: %s" % verdict(other))

    # one letter named is not a doubt BETWEEN rivals
    ck(verdict(dict(p628, note="might be vav")) is None, "one named letter is not a rival set")

    # A BARE "or" IS NOT A DOUBT. Two letters named and no hedge -- the signer telling you which
    # letters are in the word -- must not read as an abstention, or the verdict fires on description.
    ck(verdict(dict(p628, note="the vav or nun is clear enough")) is None,
       "a note with no hedge produced an abstention verdict on the strength of the word 'or'")
    ck(verdict(dict(p628, note="")) is None, "an empty note is not an abstention")

    # A HEDGE IN ONE SENTENCE AND LETTER NAMES IN ANOTHER IS NOT A DOUBT ABOUT THOSE LETTERS. Taken
    # from the real population: a dozen signed notes are long analytical prose that names letters while
    # asserting them. Here the hedge governs the crop; the letters belong to a separate sentence.
    prose = dict(p628, note="The box could be a line too low. The page prints vav and nun clearly.")
    ck(verdict(prose) is None,
       "a hedge paired with letter names from another sentence: %s" % verdict(prose))
    ck(verdict(dict(p628, note="could be vav or nun. The page prints tet and bet."))["names"]
       == ["vav", "nun"],
       "the clause stops at the sentence end, so tet and bet are not rivals here")

    # the BOX pattern must not fire this one: coverage prose is the other pattern's business
    import apparatus_signature_rule as RULE
    box = dict(p628, note="the right edge cuts the letter")
    ck(RULE.prose_says_unsignable(box["note"]) and verdict(box) is None,
       "coverage prose produced a glyph-abstention verdict, so the two patterns are not separate")

    # a tile DELETED or NOT IN CROP presents no letter, so it cannot present a rival
    gone = dict(p628, tiles=[tile(0, u"ב", "confirmed"),
                             tile(1, u"ן", "not_in_crop")])
    ck(verdict(gone) is None,
       "a bracketed not-in-crop tile was counted as presenting a letter: %s" % verdict(gone))

    # an unknown name raises only when the caller asserts it IS a name
    try:
        letters_named("could be vav or qoof", strict_unknown=("qoof",))
        ck(False, "an asserted name missing from the table did not raise")
    except GlyphAbstentionError:
        ck(True, "refused a name the table does not hold")

    ck(n[0] + 1 == EXPECTED_CHECKS, "ran %d checks including this one, expected %d"
       % (n[0] + 1, EXPECTED_CHECKS))
    return n[0]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--selftest" in sys.argv:
        print("glyph_abstention selftest: %d/%d checks pass" % (selftest(), EXPECTED_CHECKS))
    else:
        sys.exit("usage: glyph_abstention.py --selftest")
