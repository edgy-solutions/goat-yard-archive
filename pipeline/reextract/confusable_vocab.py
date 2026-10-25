# -*- coding: utf-8 -*-
u"""The fount's confusable-pair vocabulary, in THREE registers that must not be merged.

Ruling B(5) 2026-10-25: *"Confusable-pair vocabulary: add the vav-involving pairs you found
(vav/yod, vav/zayin, vav/final-nun, vav/resh as observed) with their instance counts. Record only;
no threshold."*  Recorded here, and kept in separate registers, because **the grounding differs and
the register is the claim** -- a pair a human confirmed by signing a glyph card and a pair inferred
from two models disagreeing are not the same kind of fact, and merging them would import authority
the second register has not earned.

  SIGNED_GLYPH_CARD   a human read the glyph cards and confirmed the pair.  Adjudicated pixels.
  ARGUED_SAME_DEFECT  not signed; admitted to the run's working list by the argument that the
                      defect is of the same kind (a short descender, an unresolved corner).
  OBSERVED_IN_READS   derived by counting the differing positions of the 18 reader rows.  This is
                      a count of MODEL DISAGREEMENT, not of pixel evidence: neither side of such a
                      pair has been adjudicated, and on at least two rows the printed form is the
                      side under suspicion.  Weakest register.  Never evidence on its own.

Membership in ANY register is a WITNESS, never a verdict -- the same discipline ruling B(2) sets
for lexicon membership.  There is deliberately **no threshold** here: no function in this module
returns a decision, only a register and a count.

Counts are over the 18 reader rows of run 501ab577a18a6785, as committed in
CANONICAL45_reader_e63ecc2eab1aa479.json.  Derivation: NFC, nikud stripped, printed vs read
compared position-by-position, and **only the 14 rows whose consonant counts are equal** admit a
positional pair at all (4 rows differ in length and contribute nothing -- an insertion or a deletion
has no "differing position").  18 substitution positions over those rows.

All page numbers in this module are FILE pages (printed = file - 88).
"""

# --- register 1: signed on glyph cards --------------------------------------------------------
# the-ground-truth-is-a-claim-too: these three were found by a human signing per-letter glyph
# cards, and finding them is what inverted a design conclusion.
SIGNED_GLYPH_CARD = {
    u"עצ": u"ayin/tsadi",
    u"מפ": u"mem/pe",
    u"בג": u"bet/gimel",
}

# --- register 2: admitted by argument, never signed ------------------------------------------
# These five sit in classify45_evidence.CONFUSABLE beside the signed three.  The run's own comment
# justifies dalet/resh and kaf/bet as "the same kind of defect"; the remaining three carry no
# recorded justification at all, which is itself worth knowing.
ARGUED_SAME_DEFECT = {
    u"דר": u"dalet/resh",          # short descender; the run names it
    u"בכ": u"kaf/bet",             # unresolved corner; the run names it
    u"בך": u"final-kaf/bet",       # no recorded justification
    u"הח": u"he/het",              # no recorded justification
    u"וי": u"vav/yod",             # no recorded justification
}
# NOTE on key order: classify45_evidence.CONFUSABLE stores these as `set(p)`, so the order the
# letters were typed in never mattered there.  Here the key is a STRING and lookup is by dict, so an
# unsorted key is unreachable -- `registers(kaf, bet)` would have returned [] while the pair sat in
# the table.  Three of the five were unsorted when copied across (kaf/bet, final-kaf/bet, yod/vav)
# and the born test caught all three.  Every key in this module is sorted, and that is asserted.

# --- register 3: observed in the reader rows, with counts ------------------------------------
# key -> (count, human name).  Counts are instances of a differing POSITION, not of rows: one row
# may contribute two positions (qwen p442:n0 contributes dalet/resh and final-kaf/resh).
OBSERVED_IN_READS = {
    u"דר": (3, u"dalet/resh"),
    u"וז": (2, u"vav/zayin"),
    u"ךר": (2, u"final-kaf/resh"),
    u"הח": (2, u"he/het"),
    u"וי": (1, u"vav/yod"),
    u"הו": (1, u"he/vav"),
    u"ות": (1, u"vav/tav"),
    u"הת": (1, u"he/tav"),
    u"הן": (1, u"he/final-nun"),
    u"ון": (1, u"vav/final-nun"),
    u"עת": (1, u"ayin/tav"),
    u"יל": (1, u"yod/lamed"),
    u"יך": (1, u"yod/final-kaf"),
}

# --- the pair the ruling named that the data does not contain --------------------------------
# Ruling B(5) lists vav/resh among the pairs "you found".  It is NOT in this population: zero
# instances over the 18 rows.  Recorded as an explicit null rather than added with no evidence,
# because a vocabulary entry with no instance behind it is exactly the kind of fact that later gets
# cited as measured.  The likely intent is dalet/resh, which IS the most frequent observed pair
# (n=3) and was already in the vocabulary -- but that is a guess about a ruling, so the entry stays
# null until Chris says which was meant.
NOT_OBSERVED = {
    u"ור": (0, u"vav/resh -- named in ruling B(5), zero instances in the 18 reader rows"),
}

#: Every pair this module knows, with no register distinction.  Provided because a caller that wants
#: "is this pair known at all" should not have to union three dicts and accidentally include the
#: zero-count entry.  NOT_OBSERVED is deliberately excluded.
ALL_WITNESSED = dict(
    [(k, v) for k, v in SIGNED_GLYPH_CARD.items()]
    + [(k, v) for k, v in ARGUED_SAME_DEFECT.items()]
    + [(k, v[1]) for k, v in OBSERVED_IN_READS.items()]
)


def key(a, b):
    u"""The canonical key for an unordered consonant pair: the two letters, sorted."""
    return u"".join(sorted((a, b)))


def registers(a, b):
    u"""Every register the pair (a, b) appears in, strongest first.  [] if unknown.

    Returns register NAMES, not a boolean and not a score.  A caller deciding anything must look at
    which register the pair came from, because that is the whole content of the claim."""
    k = key(a, b)
    out = []
    if k in SIGNED_GLYPH_CARD:
        out.append(u"SIGNED_GLYPH_CARD")
    if k in ARGUED_SAME_DEFECT:
        out.append(u"ARGUED_SAME_DEFECT")
    if k in OBSERVED_IN_READS:
        out.append(u"OBSERVED_IN_READS")
    return out


def observed_count(a, b):
    u"""How many differing positions in the 18 reader rows showed this pair.  0 if none.

    A count, never a threshold.  In particular 0 does not mean "not confusable" -- the population
    is 18 positions over 12 spans, far too small for an absence to mean anything."""
    k = key(a, b)
    if k in OBSERVED_IN_READS:
        return OBSERVED_IN_READS[k][0]
    return 0


def name(a, b):
    u"""Human name for the pair, or None."""
    return ALL_WITNESSED.get(key(a, b)) or (NOT_OBSERVED.get(key(a, b)) or (None, None))[1]


#: Letters whose stroke is narrow enough that this fount's pairs cluster on them, with the count of
#: observed positions each is implicated in.  Recorded as a COUNT, not a cause: vav leads, but `he`
#: is close behind and `he` is not a narrow stroke -- its pairs (he/het, he/tav) are about an
#: unclosed leg, a different defect.  So "vav is the narrowest stroke" does not explain this table.
IMPLICATED_LETTER_COUNTS = {
    u"ו": (6, u"vav"),          # vav/zayin 2, vav/yod 1, he/vav 1, vav/tav 1, vav/final-nun 1
    u"ה": (5, u"he"),           # he/het 2, he/vav 1, he/tav 1, he/final-nun 1
    u"ר": (5, u"resh"),         # dalet/resh 3, final-kaf/resh 2
    u"י": (3, u"yod"),          # vav/yod 1, yod/lamed 1, yod/final-kaf 1
}
