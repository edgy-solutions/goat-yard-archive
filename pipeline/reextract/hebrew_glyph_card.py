"""Glyph cards: a shape-comparison surface for signing ONE disputed letter.

Built because a vote count cannot find a wrong signature and a human looking at one glyph can. Four
signed truths in this set were wrong (p200:n2 pointing, p362:n1 word division, p895:n0 ayin-for-tsadi,
p217:n2 mem-for-pe) and the two letter cases sat at 80% and 48% arm support, so no threshold separates
them. What settled p217:n2 in about a minute was a mem exemplar, a pe exemplar and the disputed glyph
at matched scale -- no Hebrew reading required, only shape. This renders that comparison.

WHAT THIS DELIBERATELY DOES NOT DO: it does not cut out the disputed glyph, and it draws no pointer
under it. Both were built and both were rejected on measurement, not taste:

  - Per-letter segmentation by column projection accounts for every letter on a MINORITY of spans
    (the born-test re-measures the rate and prints the misses; letters touch in this fount, so an
    isolated "glyph" is usually two letters or half of one). It does not have to fail everywhere to
    be unusable here: it has to be right on every span it is offered on, and a mechanism that
    mislocates silently on the rest is worse than none, because the signer cannot tell which case is
    in front of them. NB an earlier draft of this docstring claimed "p217:n2: 3 ink runs for 5
    letters"; at a raw threshold that span gives 5, matching its letters. The 3 came from a probe
    that merged sub-3px gaps, and the claim was retired when the born-test measured it.
  - Estimating letter boundaries by splitting at ink valleys to the known letter count produces cells
    of 8px beside cells of 91px on the same word. A bracket drawn from that lands under the wrong
    glyph.

A misplaced pointer on a signing surface is not a cosmetic bug. It is a machine-proposed artifact
placed in front of a signer who is looking at something else, which is the exact mechanism that put
four wrong rows in the truth table. So the target letter is named by COUNTING in the signed string
(glyph N from the right, which for Hebrew is character N of the logical string) and the signer counts
it on the image. Counting is the reliable operation; recognising the disputed glyph is the thing under
dispute and can never be an input to locating it.

TWO KINDS OF SIGNED RECORD FEED THIS PAGE, and neither is a screenshot:

  - an EXEMPLAR SIGNATURE (`hebrew_exemplar_signatures.jsonl`): a box on any page of the volume, a
    named letter, and the index of that letter counted from the right of the word it sits in, with
    signer and date. The 21-span signed set cannot supply what these cards need -- measured, it gives
    gimel 1, pe 2, and no single impression containing both letters of either pair -- so exemplars are
    open to the whole volume. The authority is the same as a truth signature: a human read the pixels
    and named the glyph. Rule 2 below (exclude words containing the partner letter) is REPLACED for
    these, because it existed to stop a comparison begging the question and a named index cannot: the
    signer said which glyph, so a word holding BOTH candidates becomes the best exemplar in the set
    rather than the worst.
  - a BOX RE-RATIFICATION (`hebrew_box_reratify.jsonl`): for a span whose ratified box maps to blank
    pixels, the box the signer actually read the text from. The (box, text) binding is one record, so
    signing from the magnified neighbourhood ratifies that box in the same act and the empty rect is
    RETIRED by the record, not kept beside it. Before such a record exists the magnified line is
    labelled UNRATIFIED everywhere it appears; after it exists there is no UNRATIFIED label, only an
    ordinary ratified pair and a note saying the original rect was empty.

Both stores are validated on load and nothing is dropped silently: a record whose box is blank, runs
off the page, straddles more than one text line, or whose named letter is not at the index it claims,
is REFUSED and printed as refused. The gate is `hebrew_aperture_diag.crop_fault`, the same one that
stands in front of the outbound calls -- a signing surface is not a softer place than a spend.

Everything shown is real page pixels, upscaled NEAREST. No smoothing, ever: a resampled curl is an
invented curl, and the whole question on p217:n2 was whether a curl is present or ink-filled.
"""
import base64, hashlib, io, json, re, sys, unicodedata
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

import hebrew_aperture_diag as D
import signature_attestation as SA
import note_region
import cv_footnote_presplit as ps

OUTHTML = D.DATA / "hebrew_glyph_cards_20260927.html"
# Signed records live with the private data, not in the code repo: they are page coordinates for a
# corpus that does not leave the network, and they are evidence, so they are appended to, never
# rewritten by a build.
SIGS = D.DATA / "hebrew_exemplar_signatures.jsonl"
RERAT = D.DATA / "hebrew_box_reratify.jsonl"
INK = 160            # a pixel darker than this is ink
TARGET_BAND = 150    # every COMPARISON image is scaled so its text line is this tall
BAND_FRAC = 0.12     # a row belongs to the line band if its ink reaches this fraction of the peak

# THE LETTERS WHOSE IDENTITY IS A QUESTION ABOUT THE LINE. Those four finals and kof hang below the
# baseline; lamed rises above the ceiling. A card gets a baseline strip when its own candidates meet
# this set -- derived, not hand-picked, which is how p254:n1 (final nun vs nun) came to have one
# although ruling 4's spec names only p628:n2.
VERTICAL = ("final_kaf", "final_nun", "final_pe", "final_tsadi", "kof", "lamed")
STRIP_NBIN = 16        # bins of 1/16 of the strip's OWN peak, so a bin means the same on every strip
STRIP_MIN_SEP = 8      # half of full scale: the FORM of Chris's threshold rule, not a number tuned here
STRIP_WIN_LINES = 4    # window either side of the span, in the line's own heights, so it scales with the fount
STRIP_MIN_COVER = 0.90  # the rect must cover this much of the run it picks (measured: 1.00 on all 8)
GUIDE_BASE = (14, 165, 233)   # the derived baseline
GUIDE_TOP = (120, 130, 150)   # the top of the dense zone -- NOT a letter-class boundary
GUIDE_SPAN = (217, 119, 6)    # the span's own x-extent
MIN_BAND_PX = 20     # an ink run thinner than this is not a text line
MAX_BAND_PX = 50     # a single band thicker than this is two lines merged
SPLIT_FRAC = 0.28    # the threshold a top-edge merge is re-profiled at; see band_geometry

# SPLIT_FRAC IS THE CENTRE OF A STABILITY PLATEAU, which is the same discipline as the two numbers above
# but a different measurement: not a gap between populations, an interval over which the ANSWER does not
# move. Sweeping every value from 0.10 to 0.44 on the p362:n1 crop (h=91):
#   0.10-0.12  one band (0,66), 67px, touching row 0             -- fused: this is the merged verdict
#   0.13-0.15  two bands survive MIN_BAND_PX, the upper at row 0 -- half-separated, still unusable
#   0.16-0.39  exactly ONE band, 31-37px, top at row 30-33       -- the span's own line, intact
#   0.40+      the span's own line itself breaks up, (33,45)(47,63); nothing survives MIN_BAND_PX
# 24 consecutive values give the same verdict, and 0.28 is the middle of them -- as far as the data allows
# from fusion below and from fragmenting the line being measured above. Sampling four values (the first
# version of this) found the plateau but not its edges, and 0.20 sits two steps from fusion.

# BOTH NUMBERS ARE DERIVED, NOT CHOSEN -- each sits in an empty band in the measurements.
# MIN: the ink runs over the 18 measurable span boxes fall into two populations with nothing between
# them, 27 runs of 1 to 14px and 18 runs of 30 to 38px. 20 is in the gap. The thin population is what
# pointed Hebrew is MADE of -- a nikud row under the baseline, an ascender-only row, a neighbour's
# descender reaching into the 12px pad -- so counting ink runs as text lines over-counts exactly on
# the feature this harness studies. That was the first version of this check, and it reported 15 of 18
# good boxes as multi-line.
# MAX: every band in the signed corpus is 30 to 38px (19 of them, including Chris's re-ratified
# p423:n3 at 35px) except p362:n1 at 67px. A 29px gap. 50 is in it.
# Same derivation style as D.NEAR_UNIFORM_INK (empty band 0 -> 0.02555) and hebrew_bind's clip ratio
# (empty band 0.14 -> 4.7). A number taken from a gap has nothing to tune.

# WHY THE SCALE BASIS IS THE LINE BAND AND NOT THE INK BOUNDING BOX. The first build matched crops on
# ink-bbox height and produced a comparison that was not matched at all. Measured over the eleven
# crops these cards use: bbox heights run 47 to 90px while the line band runs 29 to 38px. The bbox is
# unstable because a tight crop on a closely set note picks up its NEIGHBOURS -- 16 of 18 crops have
# ink touching an edge, since PAD=12 reaches into the lines above and below. (This comment used to say
# "every crop here holds 2 to 5 text lines". That was the ink-run miscount described at MIN_BAND_PX:
# the crops hold ONE text band each. The claim the comment exists to make survives -- neighbour ink in
# the pad is what destabilises the bbox -- but the number in it was wrong.) So a bbox-matched pair
# could differ by
# nearly 2x in true letter size while looking deliberate, which on a shape surface is worse than an
# obviously wrong picture.
#
# That neighbour ink is also the mechanical cause of the `contains` class: an arm asked to transcribe
# the crop returns the signed span plus the lines above and below it, and was scored wrong for it.
#
# A second silent defect died with it: the old code capped width at 1500px AFTER computing the scale,
# so a wide crop was quietly resampled to a different magnification than a narrow one -- and the born
# test missed it because it only sampled narrow single-word exemplars. Comparison images are now never
# width-capped; wide ones overflow into a scrolling strip at their true scale.

LETTER = {"alef": "א", "bet": "ב", "gimel": "ג", "dalet": "ד", "he": "ה",
          "vav": "ו", "zayin": "ז", "het": "ח", "tet": "ט", "yod": "י",
          "kaf": "כ", "lamed": "ל", "mem": "מ", "nun": "נ", "samekh": "ס",
          "ayin": "ע", "pe": "פ", "tsadi": "צ", "kof": "ק", "resh": "ר",
          "shin": "ש", "tav": "ת",
          # The five final forms, as DISTINCT SORTS rather than aliases of their base letters.
          # `positions()` locates a glyph by matching a character, so without these a card cannot be
          # built for four of ruling 4's eight spans: p628:n2 (bet + final nun), p254:n1 (final nun +
          # yod + final mem), p442:n0 (resh + bet + final kaf) and p831:n2 (... + final mem).
          #
          # They have to be separate keys because the disputes ARE the distinction. p442:n0's defect
          # is a dalet signed as a FINAL KAF; p254:n1's flag is a WORD-INITIAL final nun, which is
          # orthographically impossible and is the reason that signature is suspect. Folding a final
          # onto its base letter would erase the very thing those cards ask about -- and would also
          # let an exemplar of one sort be offered as evidence about the other.
          "final_kaf": "ך", "final_mem": "ם", "final_nun": "ן",
          "final_pe": "ף", "final_tsadi": "ץ"}

# What to LOOK AT. Every feature here is a shape statement checkable against a picture without
# reading Hebrew. The mem/pe pair is Chris's own wording from the p217:n2 ruling.
FEATURES = {
    "mem": "a sharp horn at the TOP LEFT; the top right is flat and CLOSED with no inward curl; "
           "an OPENING at the bottom left where the base does not meet the left stroke.",
    "pe": "the top-right stroke bends down and curls INWARD, ending in a small hook inside the "
          "letter; the base runs the full width and JOINS the left stroke, so the bottom left is "
          "closed. On a heavy impression the curl fills with ink and the letter reads as a closed "
          "box -- absence of the mem horn is then the deciding feature, not presence of the curl.",
    # Chris's wording, 2026-09-27, and it is a HEEL test: one feature, one corner, answerable on a
    # picture without reading a word of Hebrew.
    "bet": "a SQUARE top, and a base that extends PAST the right-hand stroke -- a little heel "
           "sticking out at the bottom right.",
    "gimel": "NARROWER than bet, with NO heel; the foot kicks out to the LEFT at the bottom.",
    # THE NEW PAIRS NAME A LOCUS, NOT A SHAPE. The four entries above are Chris's own wording from
    # his rulings. For the pairs ruling 4 adds, the only authority available is the 2026-10-25
    # audit, and what it supplies is WHERE to look -- the head, the descender -- not a description
    # of either letterform. So that is all these say. Inventing "the zayin head is wider" would be
    # shape prose with no signer behind it, dressed in the same voice as a ruling: grounding-theater
    # in the one place a reader is entitled to assume every sentence was signed by someone.
    "zayin": "LOOK AT THE HEAD. The audit's basis for p233:n4, verbatim: \u201cposition 2 differs "
             "from an in-word vav at the head\u201d. It offers nothing about the rest of the "
             "letter, and neither does this card. No zayin exemplar exists anywhere in the signed "
             "corpus -- see the exemplar count below, which is a measured zero.",
    "vav": "LOOK AT THE HEAD (against zayin) or AT THE DESCENDER (against final nun). Both loci "
           "come from the 2026-10-25 audit; it describes neither letterform, so neither does this.",
    "final_nun": "LOOK AT THE DESCENDER, below the baseline. The audit's basis for p628:n2, "
                 "verbatim: \u201cposition 2 final nun (signed) vs vav (read); the crop is tight "
                 "and the descender cannot be judged\u201d. That is a statement that THIS CROP "
                 "cannot answer the question -- the baseline strip the audit asks for is renderer "
                 "item 5 and is NOT on this page yet.",
}

# What a card prints when FEATURES has nothing. The empty string the old code fell back to rendered
# an empty box, which reads as "no distinguishing feature" rather than "nobody has stated one".
# VERDICT-ONLY, and these cards broke it before the suite caught them. Section (5) of the selftest
# forbids arm tokens on this page; what it cannot see is a TALLY, and the first draft of the eight
# cards carried both. A read shown to a signer is a prior, not evidence -- so a card names where a
# dispute is recorded and which letters are in question, and nothing about which arm, what string,
# or how many. The unredacted evidence lives in the report, which nobody signs from.
READS_WITHHELD = ("The reading itself is <b>withheld here</b>: this console is verdict-only, "
                  "because a read put in front of a signer is a prior and not evidence. The "
                  "per-arm record is in the report.")

NO_FEATURE = ("<b>No distinguishing feature is offered for this letter.</b> Nobody has signed a "
              "shape statement for it, and this console will not invent one. Compare the exemplars "
              "below, and if they settle it, the record to make is a point-and-name -- which carries "
              "the same authority as a signature and makes the feature available to every later card.")

# A span cannot be an exemplar for the letter it is DISPUTING. This is not hygiene, it is the
# difference between a comparison and a circular argument: the first run of this console offered
# `p217:n2` itself as a mem exemplar, because the truth table still says mem and the batch that
# corrects it has not landed. A signer comparing the disputed glyph against "a mem" that IS the
# disputed glyph would have confirmed the wrong signature with a picture of itself.
#
# The rule is scoped to the GLYPH, not the span, because most disputes leave the rest of the word
# untouched: p895:n0 disputes one letter at word 1 glyph 4, so its pe at word 2 glyph 2 is ordinary
# evidence about the fount; p200:n2 disputed pointing and p362:n1 a word space, and neither touched
# a letterform at all. Only p217:n2 and p423:n3 dispute a letter IDENTITY, so only those glyphs are
# barred -- and barred for BOTH candidates, since a disputed letter is evidence for neither.
# Spans whose signature is CORRECTED IN THE PENDING BATCH but not yet applied to the truth table,
# because the batch rule is one batch then one re-tally. Their row still holds the superseded string,
# so wherever this console prints that string it must say so. p895:n0 reaches the page as a pe
# exemplar (its pe is not the letter in dispute) and printing the old form unlabelled would put a
# known-wrong Hebrew string on a signing surface -- a small version of the defect this file exists to
# catch. p200:n2 and p362:n1 are NOT listed: their corrections already landed.
PENDING_RESIGN = {
    "p895:n0": "one letter (ayin -> tsadi) is being corrected in the 2026-09-27 batch; the letter "
               "shown here is a different glyph and is unaffected",
    "p423:n3": "one letter (bet -> gimel) is being corrected in the 2026-09-27 batch; the string "
               "printed here is the superseded one",
    "p726:n3": "ruled UNPOINTED in the 2026-09-27 batch; the string printed here still carries the "
               "points the page does not have",
    "p138:n6": "being signed for the first time in the 2026-09-27 batch",
    "p596:n2": "being signed for the first time in the 2026-09-27 batch",
}

# THE BATCH LANDED AND THIS TABLE DID NOT NOTICE. Read off the live page on 2026-10-25: every one
# of the five rows above now carries a `truth_basis` stamped with the batch date, so the strings the
# cards print ARE that batch's output -- and three cards were printing "The string above is
# SUPERSEDED" over the CORRECTED string. On a signing surface that is worse than printing nothing: it
# tells a signer to disregard the one string that was actually ruled.
#
# So the frame is DERIVED from the row rather than read from this table. The rule, stated: a
# `truth_basis` bearing the batch tag was written BY that batch, so for that row the batch has landed
# and the sentence above is history. A row listed here whose basis does NOT bear the tag is still
# pending and still gets the warning. The sentences are not edited to match the data -- they are kept
# verbatim as the history they now are, which is also what keeps the staleness visible instead of
# erasable.
BATCH_TAG = "20260927"


def resign_state(sid, basis):
    """("landed"|"pending"|"none", claim) for a span's pending-batch claim.

    `basis` is the span's own `truth_basis`, and the caller must pass the basis of the string it is
    ABOUT TO PRINT -- a state derived from any other row would be a statement about a different
    string. No third source is consulted, so this cannot drift from the two things it reads.
    """
    claim = PENDING_RESIGN.get(sid)
    if not claim:
        return "none", ""
    return ("landed" if BATCH_TAG in (basis or "") else "pending"), claim


# The hand-written entries. These carry the rulings and the reasons, and p895:n0 is a ruled span
# that is NOT one of the cards -- so a pure derivation would LOSE it. Every card's asked positions
# are UNIONED in below, right after `ask_positions` exists to read them.
DISPUTED = {
    "p217:n2": [(1, 3)],        # mem vs pe -- barred as an exemplar for mem AND for pe
    "p423:n3": [(2, 3)],        # bet vs gimel, RULED gimel 2026-09-27; barred until the batch lands
    "p895:n0": [(1, 4)],        # ayin vs tsadi, ruled; the rest of the phrase is unaffected
}

# span_id -> the question, the candidates, and where to look. `pos` is counted in the SIGNED string:
# Hebrew is stored in reading order, so character N of the string is glyph N from the right.
CARDS = [
    dict(span_id="p217:n2", kind="letter", status="DECIDED 2026-09-27 -- reference card",
         question="Is glyph 3 mem or pe?", word=1, pos=3, candidates=("mem", "pe"),
         verdict="pe. Chris: not a mem -- no horn, no bottom-left gap. The curl is ink-filled. This "
                 "card exists to show the method reproducing a span that is already decided: if the "
                 "picture below does not make that call obvious, the open cards are not ready to "
                 "sign and this console needs more magnification first."),
    # RULED 2026-09-27 by Chris, and the method is worth more than the verdict: the THIRD LETTER OF
    # WORD 1 is the same sort as the third letter of word 2. Two impressions of one type, on one
    # line, in one inking -- which is a better exemplar than anything this console could fetch from
    # another page, because it removes fount, wear and impression as variables at the same time.
    # Narrow body, no heel at the bottom right, foot kicking left: gimel. So the signed bet was a
    # slip and the word is the biblical form.
    #
    # It also kills a hypothesis I had put on this card: that the print might really carry bet and be
    # a compositor's reading worth preserving. It does not. This is a fifth inherited-property case,
    # not a diplomatic reading -- and the hypothesis was the less likely one before the pixels
    # arrived, which is the point: it was on the card as a thing to be ruled out, and it was.
    dict(span_id="p423:n3", kind="letter",
         status="DECIDED 2026-09-27 -- gimel; box re-ratified",
         question="Is glyph 3 of the second word bet or gimel?", word=2, pos=3,
         candidates=("bet", "gimel"),
         verdict="Gimel, ruled by Chris from the repeated sort in word 1 (its third letter is the "
                 "same type). The signed bet was a slip; the text is the biblical form. The "
                 "correction is DERIVED, not retyped: one character at word 2 glyph 3. It is not "
                 "applied to the truth table here -- one batch, then one re-tally."),
    # RULED 2026-09-27 by Chris, reading the WHOLE PAGE rather than the crop (his words: "is
    # unpointed but yes the crop is wrong also -- I am looking at the entire page to answer"). Two
    # separate outcomes, and keeping them separate is the point:
    #   - POINTING: decided. The print is unpointed, so the signed row carries points the page does
    #     not have. Same defect as p200:n2, and it is the LAST pointed row in the table.
    #   - CONSONANTS and BOX: still open. He read the page to answer the pointing question; the
    #     consonantal string and the re-drawn box are a separate signature and are not inferred from
    #     this one.
    dict(span_id="p726:n3", kind="pointing",
         status="POINTING DECIDED 2026-09-27 -- unpointed; consonants + box OPEN",
         question="Does the PRINT carry vowel points?", word=None, pos=None, candidates=(),
         verdict="Ruled UNPOINTED by Chris on 2026-09-27, from the whole page. The correction for "
                 "the batch is therefore POINTS REMOVED, consonants unchanged -- derived by a "
                 "stated rule (strip the nikud from the signed string), never retyped. It is not "
                 "applied to the truth table here: one batch, then one re-tally. Scoring "
                 "consequence to carry into item 7: an arm that returned the unpointed consonants "
                 "was not wrong, because adding points to the standard does not make an unpointed "
                 "read wrong."),
    # RULED 2026-09-27. Chris read the line and closed the text question: the rightmost word IS
    # \u05d1\u05d9\u05e2\u05e7\u05d1, so the signed order was right and the ORDER QUESTION WAS THE WRONG QUESTION.
    # His instruction, kept because it is a rule and not a one-off: a card for a `clipped` span asks
    # "does the box hold the whole signed text, and if not, where should it be", never a question
    # about the text. A clipped box is a coordinate defect, and posing it as a reading question
    # invites a signer to re-decide something the page already settles.
    dict(span_id="p912:n2", kind="coverage", status="TEXT CONFIRMED 2026-09-27 -- box OPEN",
         question="Does the ratified box hold the whole signed text, and if not, where should it be?",
         word=None, pos=None, candidates=(),
         verdict="Text confirmed from the page by Chris on 2026-09-27: the order is unchanged and "
                 "the truth row is untouched. The defect is the box -- it covers the second word "
                 "only. When the coverage box is ratified this span stops being `clipped`, and the "
                 "arms that returned the second word alone turn out to have read the crop they were "
                 "given correctly. Re-running this span under the new box is then a real (and small) "
                 "spend, and it is NOT run here."),

    # ---------------------------------------------------------------------------------------------
    # RULING 4's EIGHT. None of these is decided; every one of them is a question with its evidence
    # on the face. They differ from the four cards above in one way that matters: those sit on boxes
    # a human ratified, and seven of these sit on boxes the DRAW POOL drew and nobody ever looked at,
    # which the box caption says in those words.
    #
    # `pos` is counted in the derived SIGNED signature, where character N is glyph N from the right.
    # It is NOT counted in the frozen set's candidate: pass 2 is the insertion pass, so on p233:n4
    # and p831:n2 the two strings are different lengths and the candidate's numbering points at the
    # wrong glyph. The signature is the thing a signer is being asked to confirm, so it is also the
    # thing the counting is done in.

    dict(span_id="p233:n4", kind="letter",
         status="OPEN -- signature suspect, unsettled (audit 2026-10-25)",
         question="Is glyph 2 a vav, as signed, or a zayin?",
         word=1, pos=None, candidates=(),
         asks=[dict(word=1, pos=2, candidates=("vav", "zayin"),
                    basis="Position 2 is an <b>inserted</b> vav &mdash; not a tile anyone confirmed "
                          "against a glyph. Pass 1 left all four tiles unfilled with the note "
                          "<i>2 letters missing</i>; pass 2 confirmed the four and added two vavs, "
                          "insertion seq 1 after tile 0 (this one) and seq 0 after tile 3 (position "
                          "6, not disputed). A disagreement with the signature at this glyph is "
                          "on record in the 2026-10-25 audit. " + READS_WITHHELD,
                    # DERIVED, not typed. The sentence that stood here stated a count, and the
                    # count changed the same day it was written. Everything left in this string is
                    # count-free: the span-side impossibility, what the audit asked for, and whose
                    # call it is.
                    note="{{SIGNED:zayin}} No SPAN exemplar exists and none can be built "
                         "&mdash; the span rule excludes any word that also holds a vav, and no "
                         "span in the set shows both letters. The audit asked for <i>zayin "
                         "exemplars from this fount</i>, plural, and the supply named above is "
                         "what answers it, so this card no longer refuses on exemplar grounds. "
                         "Whether it is enough to settle the glyph is the signer's call and "
                         "nothing here makes it: if it is not, point more zayins before signing "
                         "this row.",
                    cites=())],
         verdict="NO VERDICT, and this card cannot reach one as it stands. The audit's recorded "
                 "verdict is <code>signature_suspect_unsettled</code>. Note what it also says: "
                 "<i>the signed string is not a word</i> &mdash; that is an argument from context, "
                 "not from the pixels, and it is exactly the kind of reasoning a signature is "
                 "supposed to be protected from. Confirm or correct this glyph on what the "
                 "impression shows."),

    dict(span_id="p628:n2", kind="letter",
         status="OPEN -- signature suspect, unsettled (audit 2026-10-25)",
         question="Is glyph 2 a final nun, as signed, or a vav?",
         word=1, pos=None, candidates=(),
         asks=[dict(word=1, pos=2, candidates=("final_nun", "vav"),
                    basis="Both tiles were <b>confirmed</b> in pass 1 and the candidate and the "
                          "signature are the same two characters, so nothing here was corrected: "
                          "the signature confirms the extraction rather than correcting it. "
                          "A disagreement at this glyph is on record in the 2026-10-25 audit. "
                          + READS_WITHHELD,
                    note="The audit refused to decide this one on the crop alone: <i>the crop "
                         "is tight and the descender cannot be judged</i>. <b>All three things it "
                         "asked for are now on this card</b> &mdash; the baseline strip (renderer "
                         "item 5), final-nun and vav exemplars, and the Latin gloss. The question "
                         "the strip makes answerable is the one the audit could not ask: does the "
                         "stroke cross the derived baseline, or stop at it.",
                    cites=())],
         verdict="SIGNABLE. Every need the audit recorded for this span is met, so the refusal that "
                 "stood here is spent: it cited the baseline strip, and the strip is on this page. "
                 "This card no longer withholds a verdict &mdash; record it in the signer, on the "
                 "strip and the exemplars rather than on the tight crop the audit rejected."),

    dict(span_id="p910:n3", kind="letter",
         status="CANDIDATE -- not adjudicated; the weakest dispute in the set",
         question="Is glyph 1 a lamed, as signed, or a final kaf?",
         word=1, pos=None, candidates=(),
         asks=[dict(word=1, pos=1, candidates=("lamed", "final_kaf"),
                    basis="<b>This pair is not a positional alignment, and the card will not "
                          "pretend otherwise.</b> No glyph-for-glyph disagreement puts a final kaf "
                          "at this position: the "
                          "lamed/final-kaf pairing comes from Lane B's reversal scan &mdash; one "
                          "swap from the reverse of the signature &mdash; which the audit records "
                          "as <i>a pair in no register &mdash; a candidate, not a verdict</i>. "
                          "Both tiles were confirmed in pass 1.",
                    note="The note's own Latin, printed above, is consistent with the signature "
                         "as signed. This card is here to be <b>refused as "
                         "easily as confirmed</b>; a candidate that survives a look is not thereby "
                         "promoted. It is also an ascender-versus-descender question, so the "
                         "baseline caveat on p628:n2 applies here too.")],
         verdict="NO VERDICT, and no arm's verdict either: the audit lists this span as "
                 "<code>not_adjudicated</code>. The reason it is on the page at all is that the "
                 "reversal scan named it, and a named candidate that never gets looked at is the "
                 "same as an unnamed one."),

    dict(span_id="p596:n2", kind="letter",
         status="CANDIDATE -- never signed in any export; first signing is owed",
         question="Is glyph 1 a samekh or a dalet?",
         word=1, pos=None, candidates=(),
         asks=[dict(word=1, pos=1, candidates=("samekh", "dalet"),
                    basis="This span is in <b>no signed export at all</b>. Its string comes from "
                          "the ratified truth table, and its basis field says what that means: "
                          "<code>signed-post-sitting:agent-row-verbatim-supplied</code>. It is "
                          "also absent from the 45-span scoring population, so there are <b>no "
                          "model reads</b> for it and no note text was ever resolved &mdash; which "
                          "is why the Latin panel above says ABSENT rather than showing something.",
                    note="Its box is the one <b>human-ratified</b> box among ruling 4's eight. It "
                         "is on a SEALED page, opened here for a read only under ruling 2's "
                         "carve-out: no alignment evidence is re-scored and the gate stays frozen. "
                         "The only samekh in the signed corpus is this span itself, which is "
                         "excluded as its own exemplar &mdash; so the samekh count below is zero, "
                         "and that is the corpus, not a bug.")],
         verdict="NO VERDICT. This is the one span of the eight where there is nothing to disagree "
                 "with: no signature, no reads, no Latin. The dalet candidate comes from the "
                 "confusable vocabulary, not from any reader. Sign it from the picture or leave it."),

    dict(span_id="p442:n0", kind="letter",
         status="OPEN -- reversal candidate; a disagreement is on record at this glyph",
         question="Is glyph 3 a final kaf, as signed, or a dalet?",
         word=1, pos=None, candidates=(),
         asks=[dict(word=1, pos=3, candidates=("final_kaf", "dalet"),
                    basis="Glyph 3 is the <b>one tile a signer corrected</b> on this span: the "
                          "candidate had a bet there and pass 1 chose a final kaf. The rival now "
                          "offered is a dalet, which was <b>not among that tile's choices</b>, so "
                          "the correction already made is not evidence against it. A "
                          "disagreement with the signature is on record at this glyph, and the "
                          "reversal scan's one-swap neighbour of the signature differs from it at "
                          "<b>this glyph only</b>. " + READS_WITHHELD,
                    note="THE POSITION IS COUNTED IN THE SIGNATURE, NOT IN THE REVERSAL. Under "
                          "reversal this glyph lands first, and the audit's note describes it that "
                          "way; here it is glyph <b>3</b>, because that is where it sits in the "
                          "string a signer is being asked to confirm. The glyph printed beside the "
                          "number above is the check on that.")],
         verdict="NO VERDICT. This is the clearest reversal candidate in the set, and the limit is "
                 "worth stating on the card: the signer-half guard refuses a save only when the "
                 "assembly EQUALS the reverse of the candidate. A one-swap reversal is not "
                 "equality, so on this span the guard would <b>warn and let the save through</b>. "
                 "That limit is named in the signer-half report and is not fixed by this card."),

    dict(span_id="p798:n0", kind="letter",
         status="OPEN -- a confusable set is on record against the signature",
         question="Is glyph 4 a he, as signed, or a tav, or a het?",
         word=1, pos=None, candidates=(),
         asks=[dict(word=1, pos=4, candidates=("he", "tav", "het"),
                    basis="<b>Three candidates at one position</b>, which is why the exemplar rule "
                          "below had to be generalised: a word containing ANY rival candidate begs "
                          "the question, not just one named partner. Both rivals are on "
                          "record against the signature at this glyph. " + READS_WITHHELD,
                    note="A correction to the audit's own wording, not to its verdict: its basis "
                         "line for this span says <i>against the corrected signature</i>, but all "
                         "four tiles were <b>confirmed</b> in pass 1 and the candidate equals the "
                         "signature &mdash; nothing on this span was corrected. The verdict "
                         "(<i>agree reader/confusable</i>) is untouched by that.")],
         verdict="NO VERDICT. What makes this span interesting is that agreement among the "
                 "recorded reads would not settle it either way: he/tav/het are a confusable set "
                 "in this fount, and agreement across arms that share a prior is the thing "
                 "cross-arm consensus cannot see past. Two of the three candidates have four "
                 "exemplars; het has one."),

    dict(span_id="p254:n1", kind="letter",
         status="OPEN -- TWO disputed positions; the signature is orthographically impossible",
         question="Two questions on one span: glyph 1, and glyph 2. Answer them separately.",
         word=1, pos=None, candidates=(),
         asks=[dict(word=1, pos=1, candidates=("final_nun", "nun", "yod"),
                    basis="Glyph 1 is signed as a <b>word-initial final nun</b>, which is "
                          "orthographically impossible &mdash; a final form cannot open a word. "
                          "That is already flagged in <code>classify45_sheet</code>'s signature "
                          "flags, and it is the reason this signature is suspect at all. Tiles 0 "
                          "and 1 were confirmed in pass 1. Both rivals above are on record against "
                          "the signature at this glyph. " + READS_WITHHELD,
                    note=None),
               dict(word=1, pos=2, candidates=("yod", "zayin", "vav"),
                    basis="A <b>zayin</b> is on record against the signature at this position, "
                          "and so is a vav. " + READS_WITHHELD + " "
                          "Zayin is the same letter in dispute on p233:n4 glyph 2, which is why "
                          "the ruling asks for zayin exemplars first &mdash; one point-and-name "
                          "record would serve both cards.",
                    note="The zayin panel below is empty for this ask too, and for the same "
                         "measured reason: the corpus holds no zayin.")],
         verdict="NO VERDICT on either position. Glyph 3 is deliberately NOT asked about: it is the "
                 "one tile the signer corrected (candidate mem to final mem) and nothing on "
                 "record disputes the corrected form, so it is settled and a card that re-opened it "
                 "would "
                 "be inviting a signer to re-decide something already answered."),

    dict(span_id="p831:n2", kind="letter",
         status="OPEN -- two bases name different glyphs; this card cuts the PAIR",
         question="One of the two adjacent reshes may be a dalet. Which, if either?",
         word=1, pos=None, candidates=(),
         asks=[dict(word=1, pos=(2, 3), candidates=("resh", "dalet"),
                    basis="TWO BASES, BOTH STATED, NEITHER CHOSEN. <b>Positional alignment names "
                          "glyph 2</b>: aligned character by character against the recorded "
                          "extraction, six of the seven glyphs match the signature and the single "
                          "difference falls at position 2 (<code>audit_overlay_20261025</code>; "
                          "the arm and its string are withheld, as everywhere on this page). "
                          "<b>Insertion provenance names glyph 3</b>: position 3 "
                          "is the resh that pass 2 <b>inserted</b> (insertion seq 0 after tile 1 "
                          "&mdash; <code>after_i</code> is the 0-based tile index, measured, not "
                          "assumed), on a span whose pass-1 note reads <i>Hebrew is missing a "
                          "glyph and one glyph is not in crop but is in hebrew</i>. All six tiles "
                          "were confirmed. <b>Both positions hold the same character</b>, so no "
                          "number can discriminate them &mdash; the discriminator is the picture, "
                          "which is why this card cuts the pair and declines to pick.",
                    note="The third source that disagreed with the first has been FIXED under its "
                         "own name: <code>classify45_sheet</code> stated <i>position 3</i> while "
                         "arguing from positional alignment, where the arithmetic gives 2, so a "
                         "reader who trusted that table alone got the insertion position for the "
                         "alignment reason. Its classification row and its "
                         "<code>SIGNATURE_FLAGS</code> entry now carry both numbers with their "
                         "bases. It is cited by SYMBOL and not by line, because the line it used "
                         "to sit on had already moved from 292 to 296. One further measured fact "
                         "that makes a bare number ambiguous: the positions above are counted in "
                         "the 7-letter derived signature, while the frozen candidate is 6 letters "
                         "with ONE resh &mdash; and that difference is exactly the recorded "
                         "insertion, not a second defect.")],
         verdict="NO VERDICT, and the conflict is the finding. Carried debt this span exposes, "
                 "recorded and not fixed here: pass 1's note matches "
                 "<code>apparatus_signature_rule.UNSIGNABLE_PATTERN</code> (<i>not in crop</i>), "
                 "but the <b>pass-2 note is empty</b> and <code>full_span_pixel_signature</code> "
                 "is true &mdash; so the prose refusal that exists to catch exactly this span "
                 "cannot fire on it. A guard whose input was cleared by a later pass is not a "
                 "guard."),
]


def esc(t):
    """HTML-escape. The Latin note text goes on the page verbatim, so it is escaped verbatim too."""
    return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def strip_nikud(t):
    return "".join(c for c in unicodedata.normalize("NFD", t or "")
                   if not unicodedata.combining(c))


def has_nikud(t):
    return any(unicodedata.combining(c) for c in unicodedata.normalize("NFD", t or ""))


def words(truth):
    """The signed string as whitespace tokens. Token 1 is the RIGHTMOST word on the page."""
    return strip_nikud(truth).split()


def where(truth, occ):
    """Prose locator that names the WORD as well as its number.

    The number alone is not safe: p102:n0 is two words joined by a dash, which tokenises as three,
    and a signer counting words on the image would not call the dash a word. Printing the word makes
    the count checkable against the picture instead of trusted."""
    ws = words(truth)
    return ", ".join("word %d (%s), glyph %d from the right" % (w, ws[w - 1], g) for w, g in occ)


# THE NOTE'S OWN LATIN. Ruling 4 asks for the Latin gloss on p628:n2, and the obvious source is the
# wrong one: `build_set`'s `latin_context` comes from the 2026-09-06 sitting records, which cover the
# OLD ~21-span population, so it is absent for 44 of the 45 frozen spans. `contact_sheet_scoring45`
# already hit that and fixed it, and its fix is the thing worth reusing -- not the file path, the
# WITNESSED MAPPING. It resolves note text by POSITION (the span's own box inside the page's note
# regions), not by the span id's N, and records five witnesses per row plus a content witness.
#
# So this reads that artifact's finished rows. It does not re-derive the mapping: a second port of a
# witnessed rule is a second rule. The contact-sheet module cannot be imported -- it runs its whole
# pipeline at module scope, reading crops and checking hashes -- which is also why the artifact, not
# the code, is the dependency.
#
# AND THE CONSOLE DOES NOT TRANSLATE IT. On three of these spans the Latin bears hard on the answer
# (p442:n0's note reads `pestis`; p254:n1's reads `monile aureum`). Printing my translation beside
# the glyph would be me adjudicating the span in the signer's chair. The Latin goes up verbatim,
# labelled as the note's own words, and the inference is the signer's to draw or refuse.
C2SHEET = D.DATA / "CONTACT_SHEET_scoring45_adb9a26835533dbc_c26745f4be489471bd.json"
_C2CACHE = {}


def latin_gloss(span_id):
    """(text, state, why) for the note's Latin. state is present | absent."""
    if "rows" not in _C2CACHE:
        try:
            _o = json.loads(io.open(str(C2SHEET), encoding="utf-8").read())
            _C2CACHE["rows"] = {r["span_id"]: r for r in _o["rows"]}
            _C2CACHE["src"] = _o.get("channel2_source") or {}
        except Exception as e:
            _C2CACHE["rows"], _C2CACHE["src"] = {}, {}
            _C2CACHE["err"] = "%s: %s" % (type(e).__name__, e)
    if _C2CACHE.get("err"):
        return "", "absent", "the contact-sheet artifact could not be read (%s)" % _C2CACHE["err"]
    r = _C2CACHE["rows"].get(span_id)
    if not r:
        return "", "absent", ("this span is not in the 45-span scoring population, so no note text "
                              "was ever resolved for it")
    if r.get("ch2_state") != "present":
        return "", "absent", r.get("ch2_why") or "the contact sheet records no note text"
    pos = r.get("pos") or {}
    if pos.get("state") != "resolved":
        return "", "absent", ("the note position did not resolve (%s), and an unresolved position "
                              "means the text cannot be attributed to this span"
                              % (pos.get("why") or pos.get("state")))
    w = r.get("ch2_witness") or {}
    bad = sorted(k for k, v in w.items() if v is False)
    if bad:
        return "", "absent", "witness(es) %s do not match, so the mapping is not established" % bad
    return r["ch2"], "present", ""


def card_asks(c):
    """A card's questions as a list, one per disputed position.

    A card used to carry exactly one (word, pos, candidates). Two of ruling 4's spans break that:
    p254:n1 has TWO disputed positions with different candidate sets, and a card asking one of them
    would leave the other signed as-is with nothing on the page saying so. So `asks` is the general
    form and the single-question fields are the shorthand -- not the reverse, because the shorthand
    is what silently drops the second question.

    `pos` may be a tuple. p831:n2's two candidate positions are BOTH resh, so no single number can
    discriminate them and the card must cut the pair; see its entry."""
    if c.get("asks"):
        return c["asks"]
    if not c.get("pos"):
        return []
    return [dict(word=c.get("word"), pos=c["pos"], candidates=c.get("candidates") or (),
                 basis=None, note=None)]


def ask_positions(ask):
    """`pos` as a tuple, whether it was written as an int or a tuple."""
    p = ask["pos"]
    return tuple(p) if isinstance(p, (tuple, list)) else (p,)


def _disputed_from_cards():
    """{span_id: [(word, pos)]} for every glyph a card actually asks about.

    DERIVED, because the hand list above was a snapshot and went stale: it covered 2 of the 10
    letter-cards, so `sig_load`'s "an exemplar may not be the glyph under dispute" check could not
    see the other eight. The measured consequence was that the final-nun census offered p628:n2's
    own word -- the span whose glyph 2 is the question "final nun or vav?" -- as a page to point a
    final nun on, and the loader would have taken it.

    `card_asks` is the general form and `pos` may be a tuple (p831:n2 cuts a PAIR, both resh), so
    both are read through the same two helpers the cards themselves are read through. Nothing is
    typed here that a card does not already say.
    """
    out = {}
    for c in CARDS:
        for a in card_asks(c):
            if not (a.get("candidates") or ()):
                continue
            w = a.get("word", c.get("word"))
            for p in ask_positions(a):
                out.setdefault(c["span_id"], []).append((w, p))
    return {k: sorted(set(v)) for k, v in out.items()}


# UNION, never replacement: the hand list holds rulings and a non-card span, the derivation holds
# the seven cards nobody added. A position in either is a position no exemplar may come from.
for _sid, _pp in _disputed_from_cards().items():
    DISPUTED[_sid] = sorted(set(DISPUTED.get(_sid, [])) | set(_pp))


def glyphs_at(truth, ask):
    """The characters the SIGNATURE holds at this ask's positions, or None where out of range.

    This is the card's own statement of what it is pointing at, derived from the signed string every
    time the page is built. It is what makes an off-by-one `pos` visible to a reader instead of
    being a wrong instruction delivered confidently."""
    ws = words(truth)
    wi = ask.get("word") or 1
    if wi > len(ws):
        return [None for _ in ask_positions(ask)]
    w = ws[wi - 1]
    return [w[p - 1] if 1 <= p <= len(w) else None for p in ask_positions(ask)]


def positions(truth, letter):
    """[(word_no, glyph_from_right)] for every occurrence. Word 1 is the RIGHTMOST word."""
    out = []
    for wi, w in enumerate(strip_nikud(truth).split(), start=1):
        for ci, c in enumerate(w, start=1):
            if c == letter:
                out.append((wi, ci))
    return out


def row_profile(im, thr=INK):
    """Ink pixels per row. The basis for finding the text line without segmenting letters."""
    m = im.convert("L").point(lambda v: 255 if v < thr else 0)
    w, h = m.size
    px = m.load()
    return [sum(1 for x in range(w) if px[x, y]) for y in range(h)]


def line_band(im, frac=BAND_FRAC):
    """(y0, y1) of the text line the box was drawn on, or None if the crop holds no ink.

    The contiguous inked band containing the centre row -- the box was drawn on that line, so the
    centre is on it. This is a HORIZONTAL slice: it removes neighbouring lines and never touches a
    letter, which is the whole difference between this and the per-letter segmentation that was
    rejected. Counting rows is reliable in this fount; cutting columns is not."""
    r = row_profile(im)
    if not any(r):
        return None
    h = len(r)
    thr = max(1, max(r) * frac)
    c = h // 2
    if r[c] < thr:
        inked = [y for y in range(h) if r[y] >= thr]
        if not inked:
            return None
        c = min(inked, key=lambda y: abs(y - h // 2))
    y0 = c
    while y0 > 0 and r[y0 - 1] >= thr:
        y0 -= 1
    y1 = c
    while y1 < h - 1 and r[y1 + 1] >= thr:
        y1 += 1
    return y0, y1 + 1


def ink_runs(im, frac=BAND_FRAC):
    """[(y0, y1)] for every maximal run of rows reaching `frac` of the peak ink. Positions, not a
    count: a run's THICKNESS is the whole discriminator between a line of type and a vowel row."""
    r = row_profile(im)
    if not any(r):
        return []
    thr = max(1, max(r) * frac)
    out, start = [], None
    for i, v in enumerate(r):
        if v >= thr and start is None:
            start = i
        elif v < thr and start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, len(r) - 1))
    return out


def text_bands(im, frac=BAND_FRAC):
    """Only the ink runs thick enough to be a line of type. See MIN_BAND_PX for the derivation."""
    return [(a, b) for a, b in ink_runs(im, frac) if b - a + 1 >= MIN_BAND_PX]


def band_geometry(im, frac=BAND_FRAC):
    """(verdict, info) for the crop's text bands. Verdicts, and the failure each one is for:

      one-band    exactly one band, 30-38px like the rest of the corpus. The crop holds its line.
      multi-band  two or more bands: the box spans lines, so a read cannot be attributed to a line.
      merged      one band but thicker than MAX_BAND_PX and NOT touching the top edge -- two lines
                  inside the box, touching at this threshold. A box fault: no read can be attributed.
      merged-top-edge
                  one band thicker than MAX_BAND_PX that touches row 0, and which separates at
                  SPLIT_FRAC into a single band of corpus-normal height that does NOT touch row 0.
                  A PASS. The crop holds its line; what it also holds is the bottom of the line above,
                  cut by the box's top edge, which is a fact about the page and not about the box.
                  Fires on p362:n1 (67px -> 33px at SPLIT_FRAC) and nothing else.
      no-band     no run survives MIN_BAND_PX. Blank or near-blank; D.crop_fault owns that case.

    WHY merged-top-edge IS A PASS, from Chris's ruling of 2026-09-27 on p362:n1: "the ink touching at
    the top is descenders from the line above, which is a fact about the page, not the box. Trimming the
    top would cost a rerun on a sealed span for no reading gain." The distinction the verdict draws is
    not between clean and dirty crops -- it is between a box that CONTAINS two lines (merged, the read
    is unattributable) and a box that CLIPS one (merged-top-edge, the read is fine). Both look identical
    to a thickness test at a single threshold, and they are told apart by where the band sits, not by how
    thick it is. This is the same mistake the edge-clearance clause would have been: a property of the
    page read as a property of the box.

    `info` also carries clear_top / clear_bottom, and those are REPORTED, NEVER JUDGED here. Edge
    contact is not a fault: PAD=12 reaches into the neighbouring lines, so 16 of 18 span crops have
    ink at an edge by construction, and a deliberately tight crop -- Chris's re-ratified p423:n3 box,
    h=35 around a 35px band -- touches both edges because the box IS the band. An edge-clearance
    requirement in the accept gate would have rejected that ratified box. It nearly did."""
    bands = text_bands(im, frac)
    h = im.size[1]
    if not bands:
        return "no-band", dict(n_bands=0, main=None, clear_top=None, clear_bottom=None, height=h,
                               band_px=None)
    main = max(bands, key=lambda t: t[1] - t[0])
    px = main[1] - main[0] + 1
    info = dict(n_bands=len(bands), main=list(main), clear_top=main[0],
                clear_bottom=h - 1 - main[1], height=h, band_px=px)
    if len(bands) > 1:
        return "multi-band", info
    if px > MAX_BAND_PX:
        # A merge at row 0 is the top edge cutting the line above, not two lines in the box. Re-profile
        # once at SPLIT_FRAC: if a single band of corpus-normal height survives and it has cleared row
        # 0, the span's own line is intact below the clipped one and this is a pass. The probe runs ONLY
        # down this branch, so no crop that already passes can change verdict because of it.
        if main[0] == 0:
            sub = text_bands(im, SPLIT_FRAC)
            if (len(sub) == 1 and sub[0][0] > 0
                    and MIN_BAND_PX <= sub[0][1] - sub[0][0] + 1 <= MAX_BAND_PX):
                frag = [r for r in ink_runs(im, SPLIT_FRAC) if r[1] < sub[0][0]]
                info.update(split_frac=SPLIT_FRAC, split_band=list(sub[0]),
                            split_px=sub[0][1] - sub[0][0] + 1,
                            top_fragment_px=max((b - a + 1 for a, b in frag), default=0))
                return "merged-top-edge", info
        return "merged", info
    return "one-band", info


def n_lines(im, frac=BAND_FRAC):
    """How many INK RUNS the crop holds -- NOT how many text lines, despite what this used to claim.
    Still reported on the card, because the run count is what explains a `contains` read. Any claim
    about LINES must come from text_bands() or band_geometry(). See MIN_BAND_PX."""
    r = row_profile(im)
    if not any(r):
        return 0
    thr = max(1, max(r) * frac)
    n = 0
    prev = False
    for v in r:
        cur = v >= thr
        if cur and not prev:
            n += 1
        prev = cur
    return n


def ink_bbox(im, thr=INK):
    return im.convert("L").point(lambda v: 255 if v < thr else 0).getbbox()


def comparison(im, target=TARGET_BAND):
    """Crop to the text line, scale so that line is `target` tall, NEAREST. Returns (img, scale, band).

    Two images produced by this function are at the same letterform scale, which is the only property
    that makes a shape comparison mean anything. The margin kept above and below is half the band
    height: enough for ascenders, descenders and any vowel points under the baseline -- the marks the
    p726:n3 card exists to look for -- while staying clear of the next line."""
    b = line_band(im)
    if b is None:
        return im.convert("L"), 0.0, None
    y0, y1 = b
    bh = max(1, y1 - y0)
    m = bh // 2
    g = im.convert("L").crop((0, max(0, y0 - m), im.width, min(im.height, y1 + m)))
    f = target / float(bh)
    return (g.resize((max(1, int(g.width * f)), max(1, int(g.height * f))), Image.NEAREST),
            round(f, 2), bh)


def context(im, up=1):
    """A context image: native pixels, never scaled DOWN, no ink matching.

    The recovery windows and the whole-note strips are for locating text, not for judging a letter.
    The first build ran them through the matched-scale path, which shrank a 366x580 recovery window to
    169x156 -- below native, on the one image whose job was to let a signer find Hebrew the box had
    missed. Scale is a property of what an image is FOR."""
    g = im.convert("L") if im.mode not in ("L", "RGB") else im
    if up > 1:
        g = g.resize((g.width * up, g.height * up), Image.NEAREST)
    return g, float(up)


_pages = {}


def page_bits(pg):
    if pg not in _pages:
        strip, info = ps.presplit(str(D.IMG / ("page%d_image1.png" % pg)), upscale=1)
        native = Image.open(D.IMG / ("page%d_image1.png" % pg)).convert("L")
        _pages[pg] = (native, strip.convert("L"), info)
    return _pages[pg]


def cut(pg, box, pad=0, bands=None):
    native, strip, info = page_bits(pg)
    bands = bands or note_region._column_bands(strip)
    return D._native_crop(native, box, info, bands, pad)


def find_ink(pg, rects, grow=260, tries=4):
    """A window around a BLANK rect that actually holds ink, with the asked-for rect outlined.

    For p423:n3 and p726:n3 the ratified box maps to pixels holding nothing, so there is no crop to
    magnify and no glyph to compare. The honest substitute is the neighbourhood with a mark showing
    where the box asked to look, so the signer sees both the text and the miss. That red outline is
    an OVERLAY on a context image; it is never drawn on a crop used for a shape verdict."""
    native, _s, _i = page_bits(pg)
    W, H = native.size
    x0 = max(0, min(r["box"][0] for r in rects))
    x1 = min(W, max(r["box"][2] for r in rects))
    y0 = max(0, min(r["box"][1] for r in rects))
    y1 = min(H, max(r["box"][3] for r in rects))
    win = wx0 = wy0 = None
    for k in range(1, tries + 1):
        wy0, wy1 = max(0, y0 - grow * k), min(H, y1 + grow * k)
        wx0, wx1 = max(0, x0 - 40), min(W, x1 + 40)
        win = native.crop((wx0, wy0, wx1, wy1))
        if ink_bbox(win):
            vis = win.convert("RGB")
            ImageDraw.Draw(vis).rectangle([x0 - wx0, y0 - wy0, x1 - wx0 - 1, y1 - wy0 - 1],
                                          outline=(220, 40, 40), width=3)
            return vis, "+/-%dpx" % (grow * k), True, [wx0, wy0, wx1, wy1]
    return win.convert("RGB"), "+/-%dpx" % (grow * tries), False, [wx0, wy0, wx1, wy1]


# --- THE LINE STRIP AND ITS DERIVED BASELINE ------------------------------------------------
# An ascender/descender question is not answerable on a tight crop: the 2026-10-25 audit said so of
# p628:n2 in those words, "the crop is tight and the descender cannot be judged". A tight crop holds
# no reference for BELOW THE LINE. The reference comes from the span's own line, where the Latin is
# plentiful and legible -- the reliable things are counted to place the unreliable one. Nothing in
# here reads a letter, and nothing here decides anything: it draws a guide a signer may refuse.


def line_strip(pg, span_box, bands):
    """The span's own line of type at full band width, as a dict -- or one carrying `why` instead.

    Regionalized BEFORE anything is measured: the presplit's own band (one column, or one band it
    declares full width), then the inked run the span's rect actually covers. The strip then reaches
    to the MIDPOINT of the interline gap on each side. That last part is the whole point -- the
    ascender and descender rows ARE the low-ink rows, and `ink_runs` cuts at a fraction of the peak,
    so a strip cut at the run's own bounds has already discarded the evidence the question needs.

    Every refusal is named and returned. A silent fallback here would put a plausible line on a
    picture with nothing able to say which line it came from.
    """
    out = {"why": None}
    rects = cut(pg, span_box, 0, bands)[1] if span_box else []
    if not rects:
        out["why"] = "the span box yields no native rect"
        return out
    r = rects[0]["box"]
    native, _st, info = page_bits(pg)
    cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
    hit = None
    for b in (info.get("bands") or []):
        bx, by = b["native"]
        bw, bh = b["size"]
        if bx <= cx < bx + bw and by <= cy < by + bh:
            hit = b
    if hit is None:
        out["why"] = "the rect's centre lies in no presplit band"
        return out
    bx, by = hit["native"]
    bw, bh = hit["size"]
    # A strip across the column gutter would average TWO lines' baselines into one guide, and the
    # guide would look perfectly plausible. The presplit declares each band's column; a band that
    # does not declare itself full width and yet spans most of the page is refused, not trusted.
    if hit.get("col") != "full_width" and bw > 0.75 * native.width:
        out["why"] = ("the band is %r yet spans %.0f%% of the page width, so the strip could cross "
                      "the gutter" % (hit.get("col"), 100.0 * bw / native.width))
        return out
    band = native.crop((bx, by, bx + bw, by + bh))
    runs = ink_runs(band)
    ry0, ry1 = r[1] - by, r[3] - by
    ov = sorted(((max(0, min(ry1, z + 1) - max(ry0, a)), i) for i, (a, z) in enumerate(runs)),
                reverse=True)
    if not ov or ov[0][0] <= 0:
        out["why"] = "the rect overlaps no inked run in its band"
        return out
    i = ov[0][1]
    a, z = runs[i]
    cover = ov[0][0] / float(z - a + 1)
    if cover < STRIP_MIN_COVER:
        out["why"] = ("the rect covers only %.0f%% of the run it selects, so the line it sits on is "
                      "not established" % (100.0 * cover))
        return out
    nl = n_lines(band.crop((0, a, bw, z + 1)))
    if nl != 1:
        out["why"] = "the run the rect selects holds %d text lines, not one" % nl
        return out
    up = runs[i - 1][1] if i > 0 else None
    dn = runs[i + 1][0] if i + 1 < len(runs) else None
    top = (up + 1 + a) // 2 if up is not None else max(0, a - (z - a))
    bot = (z + dn) // 2 + 1 if dn is not None else min(band.height, z + (z - a))
    out.update(strip=band.crop((0, top, bw, bot)), top=top, run=(a, z), run_h=z - a + 1,
               cover=cover, col=hit.get("col"), band_box=[bx, by, bx + bw, by + bh],
               native_rect=list(r),
               # In STRIP coordinates: x from the band's own x0, y from the strip's top row.
               rect=[r[0] - bx, r[1] - by - top, r[2] - bx, r[3] - by - top])
    return out


def baseline_guides(prof):
    """(baseline, dense_top, detail) as strip rows from a row profile -- or (None, None, detail).

    Chris's threshold rule, 2026-10-04: the threshold is the MIDPOINT of the two modes, it needs a
    minimum separation, it ABSTAINS when there is no second mode, and it is never the first gap.
    Here the two modes are the paper floor and the body of the type; the midpoint between them cuts
    the x-height mass, whose lowest row is the baseline and whose highest is the top of the dense
    zone. Binning is on 1/16 of the strip's own peak so a bin means the same thing on a 140-peak
    strip and a 1194-peak one, and the histogram is padded with ZERO rather than clamped: clamping
    re-uses the end bin as its own neighbour and manufactures a mode there.

    The two modes are the two most POPULATED ones. Taking the lowest and the highest instead let a
    2-row bin set a threshold while the 16-row body mode sat unused.
    """
    pk = max(prof) if prof else 0
    h = [0] * STRIP_NBIN
    for v in prof:
        h[min(STRIP_NBIN - 1, v * STRIP_NBIN // (pk + 1))] += 1
    sm = [(h[i - 1] if i > 0 else 0) + h[i] + (h[i + 1] if i < STRIP_NBIN - 1 else 0)
          for i in range(STRIP_NBIN)]
    # `sm[i] > 0` is load-bearing: without it a bin holding ZERO rows beat the -1 sentinel on the
    # left and tied an equally empty neighbour on the right, so an EMPTY bin 0 was a mode. A uniform
    # strip then reported two modes 14 bins apart, was accepted, and drew a baseline on its last
    # row. The live strips hid it because their lowest bin is populated.
    loc = [i for i in range(STRIP_NBIN)
           if sm[i] > 0
           and sm[i] > (sm[i - 1] if i > 0 else -1)
           and sm[i] >= (sm[i + 1] if i < STRIP_NBIN - 1 else -1)]
    d = {"peak": pk, "hist": h, "smooth": sm, "modes": loc, "why": None}
    if len(loc) < 2:
        d["why"] = ("the profile has %d mode, so there is nothing to take a midpoint between"
                    % len(loc))
        return None, None, d
    two = sorted(sorted(loc, key=lambda i: -sm[i])[:2])
    d["two"], d["sep"] = two, two[1] - two[0]
    if d["sep"] < STRIP_MIN_SEP:
        d["why"] = ("the two modes are %d bins apart, under the %d the rule requires (half of full "
                    "scale), so the paper floor and the type are not separated here"
                    % (d["sep"], STRIP_MIN_SEP))
        return None, None, d
    d["thr"] = ((two[0] + two[1]) / 2.0 + 0.5) * (pk + 1) / STRIP_NBIN
    rows = [i for i, v in enumerate(prof) if v >= d["thr"]]
    return rows[-1], rows[0], d


def strip_image(sp):
    """The span's line as one image, with the derived guides painted on PAPER PIXELS ONLY.

    No mark ever overwrites ink. That keeps the image the page's own pixels rather than a picture
    this console drew, and it makes the guide BREAK exactly where a glyph crosses it -- which is the
    signal a signer is looking for, not a decoration. The scale is an integer NEAREST factor, so no
    row is duplicated unevenly and a one-native-row guide stays one native row thick.

    Returns a dict carrying `clean` (the same window, unmarked) so a check can compare the two.
    """
    st, rect, rh = sp["strip"], sp["rect"], sp["run_h"]
    base, dtop, d = baseline_guides(row_profile(st))
    f = max(1, int(round(TARGET_BAND / float(rh))))
    wx0 = max(0, rect[0] - STRIP_WIN_LINES * rh)
    wx1 = min(st.width, rect[2] + STRIP_WIN_LINES * rh)
    win = st.crop((wx0, 0, wx1, st.height))
    big = win.resize((win.width * f, win.height * f), Image.NEAREST).convert("RGB")
    out = {"f": f, "win": [wx0, wx1], "baseline": base, "dense_top": dtop, "detail": d,
           "clean": big.copy(), "img": big}
    if base is None:
        return out
    px = big.load()
    # The paper test reads the UNMARKED copy. Read it off the image being painted instead and the
    # invariant becomes draw-order dependent, because GUIDE_BASE's own green channel is above INK
    # and a later mark would see an earlier guide as paper.
    clean_px = out["clean"].load()

    def paper_row(row, colour, step):
        for y in range(row * f, min(big.height, row * f + f)):
            for x in range(0, big.width, step):
                if clean_px[x, y][1] >= INK:
                    px[x, y] = colour

    paper_row(base, GUIDE_BASE, 1)
    paper_row(dtop, GUIDE_TOP, 2)
    for ex in (rect[0] - wx0, rect[2] - wx0 - 1):
        if 0 <= ex < win.width:
            for x in range(ex * f, min(big.width, ex * f + f)):
                for y in range(0, big.height, 3):
                    if clean_px[x, y][1] >= INK:
                        px[x, y] = GUIDE_SPAN
    return out


# --- SIGNED RECORDS FROM THE WHOLE VOLUME ---------------------------------------------------
# Every record is validated before it can reach a card. The refusals are printed, never swallowed:
# a capture surface that drops a mis-drawn box in silence would put the signer back where the four
# wrong truth rows came from -- a plausible picture with nothing checking that it is the right one.
SIG_REQUIRED = ("file_page", "box", "coord_space", "word", "letter",
                "letter_index_from_right", "letter_boxes", "signer", "date")
RERAT_REQUIRED = ("span_id", "file_page", "new_box", "coord_space", "text", "signer", "date",
                  "old_box_state")


def _jsonl(path):
    if not path.exists():
        return []
    out = []
    for i, ln in enumerate(io.open(path, encoding="utf-8"), 1):
        ln = ln.strip()
        if not ln or ln.startswith("//"):
            continue
        try:
            r = json.loads(ln)
        except ValueError as e:
            out.append({"_line": i, "_parse_error": str(e)})
            continue
        r["_line"] = i
        out.append(r)
    return out


def cut_native(pg, box, pad=0):
    """Cut a NATIVE-pixel box straight from the page, with the standard fault gate applied.

    Truth-table boxes are in presplit STRIP coordinates and must be un-stacked by
    `D._native_crop`; a box drawn by a human on the page image is already native and must NOT go
    through that mapping. Two coordinate spaces, one substrate: every record therefore declares
    which one it is in, and a record that does not declare it is refused."""
    native, _s, _i = page_bits(pg)
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    fault = D.crop_fault(native.crop((max(0, x0), max(0, y0), x1, y1)),
                         [{"box": [x0, y0, x1, y1]}], native.size)
    if fault:
        return None, fault
    return native.crop((x0, y0, x1, y1)), None


def _one_band(im):
    """True when the crop holds exactly one text band of normal height. See BOX QUALITY below.

    Was `n_lines(im) == 1`, which counted ink runs and so called 15 of 18 good boxes multi-line. Those
    15 were about to enter the held redraw queue; the real count is one (p362:n1). This gate stays a
    band-count-and-height test and says nothing about edge clearance -- see band_geometry for why
    adding that clause would have rejected an already-ratified box.

    merged-top-edge passes too, per Chris's ruling on p362:n1: a band that is thick only because the
    box's top edge clips the line above, with the span's own line intact below it, is a fact about the
    page. What stays a failure is a box holding two whole lines, where a read cannot be attributed to
    either -- which is what `merged` now means."""
    return band_geometry(im)[0] in ("one-band", "merged-top-edge")


def word_band(file_page, boxes, expect):
    """(verdict, band in NATIVE rows, info) for the band of the WORD these glyph boxes make up.

    Chris's ruling of 2026-11-16, on p309's yod: "do not lower MIN_BAND_PX. One line of type is a
    property of the word, so apply the band check to the union of the word's glyph boxes, and check
    each glyph box only for being inside that band and non-blank."

    THE GATE THIS REPLACES ASKED ONE GLYPH TO BE A LINE OF TYPE. MIN_BAND_PX = 20 is a floor derived
    on lines of type, and a yod is a short letter: p309's yod crop holds one unbroken 18px ink run,
    which IS the letter, and the gate read that as `no-band` and refused the record. The floor is
    not wrong and is not touched. It was being asked of the wrong unit. A letter is not a line, and
    the word is the smallest thing on the page that has a line.

    `expect` is REQUIRED, and is the number of glyphs the word has. A function that derives its own
    input fails silently: handed a short or empty box list this would otherwise return the band of
    whatever it was given -- in the limit the signed glyph alone, which is exactly the gate being
    replaced, passing under the new name and leaving the record set unchanged for a reason no one
    could see. So the caller states the count, and a mismatch raises rather than measuring.

    The verdict set is band_geometry's, unchanged, and the admissible set is _one_band's, unchanged.
    What moved is the CROP the question is asked about."""
    boxes = [[int(round(v)) for v in b] for b in boxes]
    if len(boxes) != int(expect):
        raise ValueError("word_band got %d box(es) for a %d-glyph word -- the caller must pass "
                         "every glyph box, because the band belongs to the WORD"
                         % (len(boxes), int(expect)))
    u = [min(b[0] for b in boxes), min(b[1] for b in boxes),
         max(b[2] for b in boxes), max(b[3] for b in boxes)]
    im, fault = cut_native(file_page, u)
    if fault:
        return "crop-fault", None, dict(union=u, fault=fault)
    verdict, info = band_geometry(im)
    main = info.get("main")
    native = None if not main else [u[1] + int(main[0]), u[1] + int(main[1])]
    # PART 1 OF THE RULED RULE IS AN INVARIANT OF THIS DERIVATION, NOT A TEST OF THE RECORD.
    # Chris, 2026-11-22: "the word's band lies within the union of its glyph boxes". The band is
    # measured ON the union crop and offset by the union's top, so it is inside the union's row
    # range by construction and no record can break it. A check that cannot fail asserts nothing,
    # so it is asserted HERE, where what it watches is the derivation: if band_geometry ever
    # returns rows outside the image it was handed, this raises instead of shipping a band that
    # part 1 would have caught had it been a test.
    if native is not None and not (u[1] <= native[0] and native[1] <= u[3]):
        raise AssertionError(
            "word_band derived a band %s outside the union %s it was measured on -- part 1 of the "
            "ruled band rule is an invariant of this function and it has stopped holding"
            % (native, [u[1], u[3]]))
    return verdict, native, dict(union=u, verdict=verdict, n_bands=info.get("n_bands"),
                                 band_px=info.get("band_px"), main=main, band_native=native,
                                 crop_size=list(im.size))


def box_band_margin(box, band_native):
    """(inside, margins) for one box against the word's band. The margins are REPORTED ALWAYS.

    `top` and `bottom` are how far INSIDE the band the box sits at each end: >= 0 is inside, and a
    negative number is how far it reaches past. Both are recorded whatever the verdict.

    `inside` WAS clause 4(a), strict containment with no tolerance, which Chris withdrew on
    2026-11-22 after it refused all eleven signed records. It is still computed and still persisted:
    it is the whole of the evidence any future ruling about containment would have to argue from,
    and a gate that stores only its yes/no leaves that ruling nothing. A measurement not persisted
    is a comment. Nothing gates on it -- see BAND_RULE and band_clause_fault."""
    b = [int(round(v)) for v in box]
    top = b[1] - int(band_native[0])
    bot = int(band_native[1]) - b[3]
    return (top >= 0 and bot >= 0), dict(top=top, bottom=bot)


BAND_RULE = (
    "ENFORCED since Chris's ruling of 2026-11-22, which withdrew clause 4(a) of "
    "PREDICTIONS_exemplarband_3410d26cb1826b10.json (strict containment, no tolerance: it refused "
    "all eleven signed records, 0 of 29 boxes inside the band). The rule is now two parts. PART 1, "
    "the word's band lies within the union of its glyph boxes: an INVARIANT of the derivation, "
    "asserted in word_band -- the band is measured on the union crop, so no record can break it, "
    "and it is reported here, never counted as evidence about this record. PART 2, every glyph box "
    "overlaps the band: ENFORCED on this record, no tolerance, and a record that fails it is "
    "refused with the offending indices and their margins. `box_in_band` is the withdrawn clause's "
    "own measure, kept because it is the evidence any future ruling about containment would argue "
    "from; nothing gates on it.")


def band_clause_fault(entries, band_native):
    """(why or None, info) for the ruled band rule against one record's glyph boxes.

    Pure geometry, no images, so the refusal can be driven by MUTATION rather than attested by a
    green run over eleven records that all pass. `entries` are the record's letter_boxes, each with
    `index_from_right` and `box`; `band_native` is the word's band in native rows.

    Part 2 is the clause with teeth. A glyph box that overlaps nothing of the word's band is a box
    on another line of type, or around nothing -- and the thing it would have been read as, an
    exemplar of the named letter in the named word, is then false about the page. Overlap is
    inclusive: a box touching the band's first or last row shares a row of ink with it.

    Part 1 is checked here too, because hand-made inputs CAN break it even though the derivation
    cannot, and its message says what such a failure means: a defect in word_band, not a verdict
    about the record."""
    ents = sorted(entries, key=lambda e: int(e["index_from_right"]))
    if not ents:
        raise ValueError("band_clause_fault needs the record's glyph boxes, and got none")
    lo, hi = int(band_native[0]), int(band_native[1])
    marg, inside, over = {}, {}, {}
    for e in ents:
        i = int(e["index_from_right"])
        ok, m = box_band_margin(e["box"], band_native)
        b = [int(round(v)) for v in e["box"]]
        marg[i], inside[i] = m, bool(ok)
        over[i] = bool(b[1] <= hi and lo <= b[3])
    tops = [int(round(e["box"][1])) for e in ents]
    bots = [int(round(e["box"][3])) for e in ents]
    in_union = bool(min(tops) <= lo and hi <= max(bots))
    info = dict(margins=marg, box_in_band=inside, box_overlaps_band=over,
                band_in_box_union=in_union, band_rule=BAND_RULE)
    if not in_union:
        return ("the word's band %s is not inside the union of its glyph boxes %s -- part 1 of the "
                "ruled rule, which this derivation is supposed to make unbreakable, so this is a "
                "defect in word_band and not a verdict about the record"
                % ([lo, hi], [min(tops), max(bots)]), info)
    off = sorted(i for i, v in over.items() if not v)
    if off:
        return ("glyph box(es) %s overlap no row of the word's band %s -- part 2 of the ruled band "
                "rule (Chris 2026-11-22): every glyph box overlaps the band, no tolerance. Their "
                "margins: %s" % (off, [lo, hi], dict((i, marg[i]) for i in off)), info)
    return None, info


def letter_boxes_fault(word, letter, idx, box, lboxes):
    """Why the per-glyph boxes do not support the claim, or None.  Pure geometry: no images.

    THE INDEX CHECK CAN NO LONGER DO THIS WORK.  While the word was typed, "the named letter is at
    the claimed index of the named word" tied together two independent acts -- a reading of the
    whole word and a count -- so a typo or an off-by-one showed up as a disagreement between them.
    Chris does not read Hebrew and does not sign by typing (advisor, 2026-11-15), so the word is now
    ASSEMBLED from the letter tiles he clicks: the string and the letter name come out of the same
    clicks and cannot disagree.  A verifier that calls the producer is not a verifier, and leaving
    that check as the gate would have been exactly that.

    What is NOT by construction is the geometry.  He draws one box per glyph, in reading order, and
    these checks are about those boxes: that there are as many of them as the word has glyphs, that
    they run right to left in the order claimed, that no two are the same box or sit inside one
    another, that they are all on one line of type, and that the box signed as the exemplar IS the
    box at the claimed index.  Every one of those can be false while each tile click is the letter
    he meant -- which is the point: it is a claim the naming act does not produce.

    What it still cannot see is whether the glyph inside a box is the letter he named.  Nothing on a
    capture surface can see that.  It is why the crop is shown magnified before the record is added,
    and why the page proposes no reading of its own.
    """
    glyphs = strip_nikud(word or "")
    if not glyphs:
        return "the assembled word is empty"
    if " " in glyphs:
        return ("the assembled word %r holds a space -- an exemplar is ONE word, because the index "
                "is counted in word 1" % glyphs)
    lboxes = list(lboxes or ())
    if len(lboxes) != len(glyphs):
        return ("%d glyph box(es) for a %d-glyph word -- one box per glyph, or the index counts "
                "nothing" % (len(lboxes), len(glyphs)))
    seen = {}
    for e in lboxes:
        if not isinstance(e, dict):
            return "a glyph box entry is a %s, not an object" % type(e).__name__
        for k in ("index_from_right", "letter", "box"):
            if e.get(k) in (None, ""):
                return "a glyph box entry has no %s" % k
        i = int(e["index_from_right"])
        if not 1 <= i <= len(glyphs):
            return "glyph box index %d is outside 1..%d" % (i, len(glyphs))
        if i in seen:
            return "two glyph boxes both claim index %d" % i
        if e["letter"] not in LETTER:
            return "unknown letter name %r on the glyph box at index %d" % (e["letter"], i)
        b = [int(round(v)) for v in e["box"]]
        if b[2] - b[0] < 2 or b[3] - b[1] < 2:
            return ("the glyph box at index %d is %dx%d -- that is not a box"
                    % (i, b[2] - b[0], b[3] - b[1]))
        seen[i] = (e["letter"], b)
    built = "".join(LETTER[seen[i][0]] for i in sorted(seen))
    if built != glyphs:
        return "the glyph boxes spell %r, the word is %r" % (built, glyphs)
    for i in range(1, len(glyphs)):
        a, b = seen[i][1], seen[i + 1][1]
        if (a[0] + a[2]) <= (b[0] + b[2]):
            return ("glyph %d is not to the right of glyph %d -- Hebrew is boxed right to left and "
                    "position 1 is the rightmost glyph" % (i, i + 1))
        ov = min(a[2], b[2]) - max(a[0], b[0])
        if ov > 0.5 * min(a[2] - a[0], b[2] - b[0]):
            return ("the boxes for glyphs %d and %d overlap by %dpx -- one box per glyph, not one "
                    "box signed twice" % (i, i + 1, ov))
    ks = sorted(seen)
    for n_, i in enumerate(ks):
        for j in ks[n_ + 1:]:
            a, b = seen[i][1], seen[j][1]
            ov = min(a[3], b[3]) - max(a[1], b[1])
            if ov < 0.5 * min(a[3] - a[1], b[3] - b[1]):
                return ("the boxes for glyphs %d and %d are not on one line of type (%dpx of "
                        "shared height) -- a word sits on one line" % (i, j, max(0, ov)))
    i = int(idx)
    if i not in seen:
        return "the record claims index %d and there is no glyph box there" % i
    if seen[i][0] != letter:
        return ("the glyph box at index %d was named %s, the record is signed for %s"
                % (i, seen[i][0], letter))
    if [int(round(v)) for v in box] != seen[i][1]:
        return ("the signed box %s is not the glyph box at index %d, which is %s"
                % ([int(round(v)) for v in box], i, seen[i][1]))
    return None


def sig_load(path=None):
    """(good, refused) exemplar signatures. Validation is the whole point of this function.

    Checks, in order, and every one of them has a failure mode it was written for:
      - every required field present, and `coord_space` == "native" (the other space exists);
      - the box cuts a real, non-blank, in-bounds crop -- D.crop_fault, the outbound gate;
      - the WORD -- the union of the record's glyph boxes -- holds exactly one line of type, and
        every box in the record sits inside that line's band. Until 2026-11-16 this question was put
        to the signed GLYPH's crop, which refused p309's yod for holding a single 18px ink run: a
        short letter read as no line at all. One line of type is a property of the word, so the band
        is measured on the word and each glyph box is then asked only to be inside it (Chris's
        ruling, 2026-11-16; registered in PREDICTIONS_exemplarband_3410d26cb1826b10.json). No
        threshold moved, and the span path keeps the old gate -- see word_band;
      - the named letter really is at the named index of the named word. Since 2026-11-15 this is
        ARITHMETIC OVER ONE ACT: the word is assembled from the signer's own tile clicks, so the
        string and the letter name have a single source and cannot disagree. It is kept because a
        malformed emitter can still break it, but the claim it used to carry has moved to
        `letter_boxes_fault` -- the geometry of one drawn box per glyph, right to left, on one line,
        with the signed box at the claimed index, which is the part the naming act does not produce;
      - every glyph box cuts a real, non-blank, in-bounds crop: the same outbound gate as the signed
        box, applied to every box in the record rather than to one of them;
      - no box in the record overlaps a card's own DISPUTED span ON THE SAME PAGE -- and the page
        is checked since 2026-11-15, having been absent from the comparison since the guard was
        written. An exemplar may
        not be the thing it is evidence about, and that guard cannot be left to memory. It is now
        tested against every glyph box and not only the signed one -- the word is as much part of
        the record as the letter, and a discriminator applied on one axis and not the other is how
        one record came to hold a true and a false verdict about the same thing."""
    good, bad = [], []
    dis = _disputed_native()
    for r in _jsonl(path or SIGS):
        why = None
        if r.get("_parse_error"):
            why = "unparseable JSON: %s" % r["_parse_error"]
        else:
            miss = [k for k in SIG_REQUIRED if r.get(k) in (None, "")]
            if miss:
                why = "missing field(s): %s" % ", ".join(miss)
            elif r.get("coord_space") != "native":
                why = "coord_space=%r -- only native boxes may be signed here" % r.get("coord_space")
            elif r["letter"] not in LETTER:
                why = "unknown letter name %r" % r["letter"]
        if not why:
            im, fault = cut_native(r["file_page"], r["box"])
            if fault:
                why = "crop fault: %s" % fault
            else:
                # NO BAND CHECK ON THE GLYPH. It used to stand here, and it refused p309's yod for
                # the HEIGHT of a single unbroken ink run -- 18px against a 20px floor derived on
                # lines of type. The band question is now asked once, of the word, below, where its
                # inputs exist; a gate belongs at the earliest point its inputs exist, and the
                # word's inputs are the glyph boxes, which letter_boxes_fault has not yet checked
                # at this point in the function.
                pass
            if not why:
                idx = int(r["letter_index_from_right"])
                want = (1, idx)
                if want not in positions(r["word"], LETTER[r["letter"]]):
                    why = ("%s is not at glyph %d from the right of %s (it is at %s)"
                           % (r["letter"], idx, r["word"],
                              positions(r["word"], LETTER[r["letter"]]) or "no occurrence"))
                else:
                    gf = letter_boxes_fault(r["word"], r["letter"], idx, r["box"],
                                            r.get("letter_boxes"))
                    if gf:
                        why = "glyph boxes: %s" % gf
                if not why:
                    for e in r["letter_boxes"]:
                        _gim, gfault = cut_native(r["file_page"], e["box"])
                        if gfault:
                            why = ("glyph box at index %s: crop fault: %s"
                                   % (e["index_from_right"], gfault))
                            break
                if not why:
                    # THE WORD'S BAND. Every input it needs now exists and has been checked:
                    # letter_boxes_fault has established one box per glyph, in order, on one line,
                    # with the signed box at the claimed index, and the loop above has established
                    # that each of those boxes cuts a real, non-blank, in-bounds crop. The count is
                    # passed, not derived.
                    _bx = [e["box"] for e in sorted(r["letter_boxes"],
                                                    key=lambda e: int(e["index_from_right"]))]
                    _v, _band, _info = word_band(r["file_page"], _bx,
                                                 len(strip_nikud(r["word"])))
                    r["_word_band"] = _info
                    if _v not in ("one-band", "merged-top-edge"):
                        why = ("the word %s is %s -- union %s, %s band(s), main %s px: a word sits "
                               "on one line of type"
                               % (strip_nikud(r["word"]), _v, _info.get("union"),
                                  _info.get("n_bands"), _info.get("band_px")))
                    else:
# THE RULED BAND RULE IS ENFORCED HERE (Chris, 2026-11-22, item 1).
                        #
                        # Clause 4(a) -- strict containment of each glyph box in the word's band --
                        # is WITHDRAWN. Enforced literally on 2026-11-16 it refused all eleven
                        # records Chris had signed: 0 of 29 glyph boxes sat inside the band, 0 of 29
                        # inside even the crop's full ink extent, while the band sat inside the box
                        # union in 11 of 11 words and 29 of 29 boxes overlapped it. The boxes are
                        # hand-drawn containers with slack around the glyph, so the containment ran
                        # the other way round and no tolerance was going to fix the direction.
                        #
                        # What is ruled in its place is two clauses, and they are not of the same
                        # kind. Part 1 -- the band lies within the union of the glyph boxes -- holds
                        # BY CONSTRUCTION, because word_band measures the band on that very union;
                        # it is asserted inside word_band, where what it watches is the derivation,
                        # and reported on the record, never counted as evidence about the record.
                        # Part 2 -- every glyph box overlaps the band -- is the clause with teeth,
                        # and it refuses. The whole of it lives in band_clause_fault, a pure
                        # function, so that its refusal is proved by MUTATION in the suite and not
                        # attested by a green run over eleven records that all pass it today.
                        _w4, _i4 = band_clause_fault(r["letter_boxes"], _band)
                        _info.update(_i4)
                        if _w4:
                            why = _w4
                if not why:
                    for lbl, bx in ([("the signed box", r["box"])]
                                    + [("glyph box %s" % e["index_from_right"], e["box"])
                                       for e in r["letter_boxes"]]):
                        for sid, dpage, rect in dis:
                            # ON THIS PAGE, which is what the message has always claimed and what
                            # the comparison did not check. An exemplar drawn on p503 cannot be the
                            # glyph under dispute on p895, and refusing it as though it could threw
                            # away two of six signatures in one sitting.
                            if dpage != int(r["file_page"]):
                                continue
                            if _overlaps(bx, rect):
                                why = ("%s overlaps the disputed span %s on this page -- an "
                                       "exemplar may not be the glyph under dispute" % (lbl, sid))
                                break
                        if why:
                            break
            if not why:
                r["_crop"] = im
                good.append(r)
        if why:
            r["_refused"] = why
            bad.append(r)
    return good, bad


def _overlaps(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _disputed_native():
    """(span_id, FILE PAGE, native rect) for every span holding a DISPUTED glyph.

    The page is in the tuple and not in a lookup beside it, deliberately. It used to be absent
    altogether: this returned (span_id, rect), sig_load compared every box in a record against
    every rect on any page, and the refusal it emitted said "on this page" about a page it had
    never consulted. Two of Chris's six signatures of 2026-11-15 were refused that way -- p503's
    kaf box against a rect on p895, p577's tav box against the same one -- and a third would have
    been, p309's yod against a rect on p423.

    It will not stay rare, which is why the shape changes rather than the call site. Every footnote
    in this volume sits in the same band at the foot of the page (all eleven signed boxes fall
    between y=4385 and y=4707) and the disputed rects sit in that band too, so a signature collides
    whenever its x happens to land inside one. Three of eleven did.

    A rect test cannot see a mapping error -- containment arithmetic will compare two boxes that
    were never in the same frame and report a confident refusal of good work. So a consumer that
    drops the page now gets a TypeError instead of a wrong answer.
    """
    out = []
    for s in D.build_set(include_sealed=True):
        if s["span_id"] not in DISPUTED or not s["span_box"]:
            continue
        _im, rects = cut(s["page"], s["span_box"], D.PAD, s["column_bands"])
        for rr in rects:
            out.append((s["span_id"], int(s["page"]), rr["box"]))
    return out


_SIGCACHE = {}


def card_rivals_union(letter):
    """Every rival `letter` is asked against on any card, as one set.

    The default rule-2 standard for a context tile. UNION, because rule 2 holds against every rival
    or it does not hold: dalet is asked against resh on one card and against samekh and final kaf on
    others, and a word clean of only one of them begs the question on the next card.
    """
    out = set()
    for c in CARDS:
        for a in card_asks(c):
            cand = tuple(a.get("candidates") or ())
            if letter in cand:
                out.update(x for x in cand if x != letter)
    return out


def _rule2_dirt(word, letter, rivals):
    """The rivals actually present in `word` -- the reason a context tile is refused, or ()."""
    w = strip_nikud(word)
    return tuple(sorted(p for p in rivals if p != letter and LETTER.get(p) and LETTER[p] in w))


def sig_exemplars(letter, want=9, partners=None):
    """Signed exemplars of `letter` from anywhere in the volume, pointed first.

    Two kinds, and the difference is a difference in what was attested (Chris, 2026-11-15):

      kind="pointed"  the letter the signer named. EXEMPT from rule 2 -- see the module docstring:
                      a word containing both candidates is the contrast pair this corpus could not
                      supply, and it is admissible precisely because the signer named an index.
      kind="context"  a glyph box drawn around another letter of the same pointed word, in the same
                      sitting, by the same hand. It carries a named index too, which is why it is
                      admissible at all. But the letter being ATTESTED was the pointed one, so this
                      kind is admitted ONLY where rule 2 holds: a context resh standing next to a
                      dalet is a specimen of neither.

    `partners` is the rule-2 standard applied to the context tiles, and it is an ARGUMENT because
    consumers differ: a card's standard is its own rivals (the default, unioned over every ask that
    names the letter), while the sitting's legend scores against its axes. One consumer's axis
    silently scoring another's is exactly the confusion this parameter exists to prevent.

    Each returned row is a COPY carrying `kind`, `rule2_dirt` and `single_instance` -- the cached
    records are not mutated, and `single_instance` is true only when this call admitted exactly one,
    so a card can say what it rests on instead of printing one picture and implying a corpus.
    """
    if "good" not in _SIGCACHE:
        _SIGCACHE["good"], _SIGCACHE["bad"] = sig_load()
    rivals = set(card_rivals_union(letter) if partners is None else partners)
    out = []
    for r in _SIGCACHE["good"]:
        if r["letter"] == letter:
            out.append(dict(r, kind="pointed", rule2_dirt=()))
    for r in _SIGCACHE["good"]:
        for lb in r.get("letter_boxes") or ():
            if lb.get("letter") != letter:
                continue
            if (lb.get("index_from_right") == r.get("letter_index_from_right")
                    and r.get("letter") == letter):
                continue        # the pointed one, already taken above
            dirt = _rule2_dirt(r["word"], letter, rivals)
            if dirt:
                continue        # refused, and `sig_context_tiles` reports it with its reason
            out.append(dict(r, letter=letter, kind="context", rule2_dirt=(),
                            letter_index_from_right=lb.get("index_from_right")))
    out = out[:want]
    for r in out:
        r["single_instance"] = (len(out) == 1)
    return out


def rerat_load(path=None):
    """(good, refused) box re-ratifications: span_id -> the box the signer actually read from.

    Same gate as an exemplar signature, plus: the record must name what was wrong with the old box,
    because retiring a ratified rect without saying why is how a coordinate fault becomes invisible."""
    good, bad = {}, []
    for r in _jsonl(path or RERAT):
        why = None
        if r.get("_parse_error"):
            why = "unparseable JSON: %s" % r["_parse_error"]
        else:
            miss = [k for k in RERAT_REQUIRED if r.get(k) in (None, "")]
            if miss:
                why = "missing field(s): %s" % ", ".join(miss)
            elif r.get("coord_space") != "native":
                why = "coord_space=%r -- only native boxes may be signed here" % r.get("coord_space")
        if not why:
            im, fault = cut_native(r["file_page"], r["new_box"])
            if fault:
                why = "crop fault on the new box: %s" % fault
            elif not _one_band(im):
                why = ("the new box is %s (%d ink runs) -- a span box must contain exactly one text "
                       "band" % (band_geometry(im)[0], n_lines(im)))
            else:
                r["_crop"] = im
                good[r["span_id"]] = r
        if why:
            r["_refused"] = why
            bad.append(r)
    return good, bad


_RERATCACHE = {}


def rerat_for(span_id):
    if "good" not in _RERATCACHE:
        _RERATCACHE["good"], _RERATCACHE["bad"] = rerat_load()
    return _RERATCACHE["good"].get(span_id)


def candidate_band_box(pg, win_box):
    """The native box of the nearest single text line inside a recovery window.

    This is what makes ruling 2 one record instead of two: the image the signer reads the letter from
    IS a box, stated in native page coordinates, so signing the text ratifies that box in the same
    act. The band is found by ink profile (a horizontal slice -- no letter is cut) and the horizontal
    extent is the inked columns within it, so the box is the line and not the window."""
    native, _s, _i = page_bits(pg)
    wx0, wy0, wx1, wy1 = win_box
    win = native.crop(win_box)
    b = line_band(win)
    if not b:
        return None
    strip = win.crop((0, b[0], win.width, b[1]))
    bb = ink_bbox(strip)
    if not bb:
        return None
    return [wx0 + bb[0], wy0 + b[0], wx0 + bb[2], wy0 + b[1]]


def coverage_candidates(pg, rect, reach=1200, gap=13, most=4):
    """Boxes that extend a clipped span rightwards, one word-run at a time. PROPOSALS, not answers.

    A clipped box holds part of the signed text and the rest sits beside it on the same line. What
    the machine can do reliably is find the line band and the inked runs on it; what it CANNOT do is
    say which of those runs are Hebrew, because on this page the Hebrew is followed on the same line
    by the Latin gloss and the inter-word gaps run 13-25px throughout with no separation between the
    two scripts. Measured on p912:n2, not assumed.

    So this enumerates instead of deciding: each candidate is a real native box, rendered as the crop
    it makes, and the signer ratifies the one that holds exactly the signed text. A machine-proposed
    box that the signer confirms BY LOOKING AT ITS OWN CROP is a different object from a machine-
    proposed pointer: the proposal and the evidence for it are the same picture, so a wrong proposal
    is visibly wrong rather than quietly persuasive. In Hebrew a clipped span's missing words are to
    the RIGHT, which is why the candidates only grow that way."""
    native, _s, _i = page_bits(pg)
    W, H = native.size
    x0, y0, x1, y1 = rect
    win = (max(0, x0 - 40), max(0, y0 - 40), min(W, x1 + reach), min(H, y1 + 40))
    wim = native.crop(win)
    b = line_band(wim)
    if not b:
        return []
    band = wim.crop((0, b[0], wim.width, b[1]))
    px = band.convert("L").point(lambda v: 255 if v < INK else 0).load()
    BW, BH = band.size
    col = [any(px[xx, yy] for yy in range(BH)) for xx in range(BW)]
    runs, st = [], None
    for xx in range(BW):
        if col[xx] and st is None:
            st = xx
        elif not col[xx] and st is not None:
            runs.append((st, xx))
            st = None
    if st is not None:
        runs.append((st, BW))
    ws = []
    for a, bb in runs:
        if ws and a - ws[-1][1] < gap:
            ws[-1] = (ws[-1][0], bb)
        else:
            ws.append([a, bb])
    by0, by1 = win[1] + b[0], win[1] + b[1]
    right = [w for w in ws if win[0] + w[0] >= x1 - 4]
    out = []
    for k in range(1, min(most, len(right)) + 1):
        out.append(dict(box=[max(0, x0 - 6), max(0, by0 - 6),
                             min(W, win[0] + right[k - 1][1] + 6), min(H, by1 + 6)],
                        n_words=k))
    return out


def paste_rerat(span_id, pg, box, old_state):
    """A ready-to-paste record line for `hebrew_box_reratify.jsonl`, with the text left EMPTY.

    Empty is deliberate: the loader refuses a record with a missing field, so a line pasted without
    the signer typing what they read fails loud instead of ratifying a box with a placeholder
    attached to it."""
    return json.dumps(dict(span_id=span_id, file_page=pg, new_box=[int(v) for v in box],
                           coord_space="native", old_box_state=old_state, text="",
                           signer="", date="2026-09-27",
                           basis="signed-from-magnified-neighbourhood"), ensure_ascii=False)


# --- BOX QUALITY ---------------------------------------------------------------------------------
# RESULT, 2026-09-27, recorded at Chris's instruction: ten of twelve span-box crops carry neighbour
# ink and every crop holds 2 to 5 text lines. That is a statement about how the boxes were DRAWN, not
# about the pad: growing the A2 pad from 12 to 32 to 57px makes edge contact worse, because the crop
# reaches further into the lines above and below. Two consequences, both load-bearing:
#
#   - it was believed to be the mechanical cause of the `contains` class -- "an arm asked to transcribe
#     the crop returns the signed span with its neighbours attached and was scored wrong for obeying
#     the prompt." MEASURED over all 22 contains reads (hebrew_bind.contains_population), that is not
#     what is in the bucket. Nothing in it can be identified as a line from above or below. 13 of 22
#     are extra material on the SAME line, 10 of those on p124:n4 alone -- the widest box in the set,
#     458px for a two-word signature, whose reads pick up the Latin `quasi` beside the Hebrew. The
#     other 9 are not box faults at all: a glued letter, a trailing colon, a stray vav, a duplication
#     loop, and two broken parses that `truth in read` CREDITS. So the class names a geometric cause
#     and implements a string relation, and the two populations barely overlap. The pad claim above is
#     true about bbox instability and was wrong about this;
#   - "a signed span's box contains exactly one line band" is the invariant item 3's (box, text)
#     binding test asserts. It is implemented here (`one_band_report`) so item 3 calls a measurement
#     that already exists rather than inventing one, and so the number is visible now.
#
# It bears on the 227 note boxes of volume 1 the same way, and that is NOT measured here: this
# function sees only the spans the Hebrew harness carries. Flagged, not claimed.
def box_quality(include_sealed=True):
    """Per span: crop size, how many text lines the ratified box actually holds, and any fault."""
    rows = []
    for s in D.build_set(include_sealed=include_sealed):
        if not s["span_box"]:
            rows.append(dict(span_id=s["span_id"], page=s["page"], size=None, lines=None,
                             fault="no-span-box", one_band=False, band=None))
            continue
        im, rects = cut(s["page"], s["span_box"], D.PAD, s["column_bands"])
        native, _x, _y = page_bits(s["page"])
        fault = D.crop_fault(im, rects, native.size)
        # The VERDICT as well as the bit. `one_band` is now true for two different shapes -- one-band
        # and merged-top-edge -- and a row that says only "yes" hides which, when the second is a crop
        # whose top edge cuts the line above. Reported, not gated: `one_band` is unchanged.
        rows.append(dict(span_id=s["span_id"], page=s["page"],
                         size=None if im is None else list(im.size),
                         lines=None if (im is None or fault) else n_lines(im),
                         fault=fault, rects=len(rects),
                         band=None if (im is None or fault) else band_geometry(im)[0],
                         one_band=bool(im is not None and not fault and _one_band(im))))
    return rows


def one_band_report(include_sealed=True):
    """(n_one_band, n_measurable, [violating span_ids]) -- the debt item 3 will assert against."""
    rows = [r for r in box_quality(include_sealed) if r["lines"] is not None]
    bad = [r["span_id"] for r in rows if not r["one_band"]]
    return len(rows) - len(bad), len(rows), bad


def partner_prose(partners):
    """`partners` as prose, for a message that used to assume exactly one rival."""
    ps = [p for p in partners or ()]
    if not ps:
        return "any rival candidate"
    if len(ps) == 1:
        return ps[0]
    return ", ".join(ps[:-1]) + " or " + ps[-1]


COUNT_WORD = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
SIGN_TOKEN = re.compile(r"\{\{SIGNED:([a-z_]+)\}\}")


def _heb_entities(s):
    """A Hebrew string as numeric character references, which is how the card notes are written."""
    return "".join("&#%d;" % ord(ch) for ch in s)


def signed_impressions_sentence(letter, partners=None):
    """The signed supply of `letter` as prose, derived from the records at every render.

    This sentence used to be typed by hand into p233:n4's note: "There is now exactly one zayin
    exemplar in the signed corpus, and it is a pointed one: Chris, file p264". True when it was
    written on 2026-11-15, false later the same day when Chris pointed p534 -- the second zayin the
    roster asked him for. A card's note is what a human reads INSTEAD of the tally, so a count in a
    note has to recompute itself or it is a claim with nobody watching it.

    Every impression is named -- page, printed page, word, index, signer, date -- for two reasons. A
    signer deciding whether the supply is enough has to be able to go and look at each one; and a
    note saying "two" without saying which two cannot be checked against the records at all.

    The arithmetic clause is derived with the count, because it is an argument FROM the count: "one
    impression is one impression" is a true and useful thing to say about one impression and a false
    thing to say about three.
    """
    rs = sig_exemplars(letter, want=10 ** 6, partners=partners)
    if not rs:
        return ("<b>No signed exemplar of %s exists</b> in the corpus: nobody has pointed one and "
                "no box drawn around a neighbouring glyph has been admitted, so there is nothing "
                "here to compare an impression against." % letter)
    kinds = set(r.get("kind") for r in rs)
    nm = (COUNT_WORD[len(rs)] if len(rs) < len(COUNT_WORD) else str(len(rs)))
    named = []
    for r in rs:
        named.append('%s, file p%s (printed %s), the word <span class="heb" dir="auto">%s</span>, '
                     'glyph %s from the right, %s%s'
                     % (r["signer"], r["file_page"], int(r["file_page"]) - 88,
                        _heb_entities(r["word"]), r["letter_index_from_right"], r["date"],
                        "" if r.get("kind") != "context" else
                        " &mdash; from context, not the letter he named"))
    if len(rs) == 1:
        head = ("There is <b>exactly one signed %s exemplar</b> in the corpus, and it is a %s one: "
                % (letter, "pointed" if "context" not in kinds else "context"))
        tail = " <b>One impression is one impression.</b>"
    else:
        head = ("There are <b>%s signed %s exemplars</b> in the corpus, %s: "
                % (nm, letter,
                   ("both" if len(rs) == 2 else "all") + " of them "
                   + ("pointed" if kinds == set(["pointed"])
                      else "from context" if kinds == set(["context"])
                      else "pointed or from context")))
        # HOW MANY INDEPENDENT SPECIMENS, which is not the same question as how many impressions.
        # yod's two are two glyphs of one word on one page: a reader who takes "two" as two
        # specimens is reading more independence into the supply than it has, and this is the same
        # point the single-exemplar clause makes one step further down.
        _pgs = set(r["file_page"] for r in rs)
        _wds = set((r["file_page"], r["word"]) for r in rs)
        if len(_wds) == 1:
            tail = (" <b>%s impressions &mdash; but all of them glyphs of the same word, on file "
                    "p%s. One word is one word.</b>" % (nm.capitalize(), sorted(_pgs)[0]))
        elif len(_pgs) == 1:
            tail = (" <b>%s impressions, all on file p%s.</b>" % (nm.capitalize(), sorted(_pgs)[0]))
        else:
            tail = (" <b>%s impressions, on %d different pages.</b>"
                    % (nm.capitalize(), len(_pgs)))
    return head + "; and ".join([", ".join(named[:-1]), named[-1]] if len(named) > 1
                                else named) + "." + tail


def fill_note(s):
    """Fill every {{SIGNED:letter}} token in a card note from the measured supply.

    Filled wherever a note is READ -- on the page and in the suite's own field scan -- so the thing
    checked is the thing a human sees. An unfilled token is visible garbage inside a warnbox, and
    the suite looks for one.
    """
    return SIGN_TOKEN.sub(lambda m: signed_impressions_sentence(m.group(1)), s or "")


def sig_context_tiles(letter):
    """[(file_page, word, index_from_right)] -- `letter` as a CONTEXT tile in a pointed word.

    A signature records one letter at a named index AND a box for every other glyph in the word, so
    a pointed dalet on p386 also carries boxes for the yods and the final nun around it. Those
    boxes are drawn and indexed by the same hand in the same sitting.

    RULED 2026-11-15: a context tile IS an exemplar where its word is rule-2 clean, labelled as
    coming from context and as a single instance. `sig_exemplars` now admits those. THIS function
    still reports ALL of them, clean and dirty alike, because the capture page has to say "one
    context tile, rule-2 DIRTY, holds yod" rather than "none" -- a letter refused for a stated
    reason and a letter nobody ever drew are different states, and a page that prints both as
    absence sends a signer to the wrong work.
    """
    if "good" not in _SIGCACHE:
        _SIGCACHE["good"], _SIGCACHE["bad"] = sig_load()
    out = []
    for r in _SIGCACHE["good"]:
        for lb in r.get("letter_boxes") or ():
            if lb.get("letter") != letter:
                continue
            if (lb.get("index_from_right") == r.get("letter_index_from_right")
                    and r.get("letter") == letter):
                continue        # the pointed one; sig_exemplars owns it
            out.append((r["file_page"], r["word"], lb.get("index_from_right")))
    return out


def exemplars(letter, partner, want=4, exclude=()):
    """Signed spans whose print shows `letter` unambiguously, best first. The rule, stated:

      1. the span has a signed truth containing `letter`;
      2. its truth does NOT contain `partner` -- so no glyph in that word can be the other candidate
         and the comparison cannot beg the question;
      2b. the occurrence is not itself a DISPUTED glyph, and the span is not the card's own span. A
         letter under dispute is evidence for neither candidate, so it appears on neither side;
      3. its crop exists and is not faulted (a blank or clamped crop is not an exemplar);
      4. ranked by fewest letters (fewer glyphs to count), then most ink (clearer impression), then
         span_id, so the selection is reproducible.

    Rule 2 is the one that matters for a span exemplar: a word that could itself contain either
    candidate would be evidence about the reader's expectation, not about the fount.

    This function returns SPAN exemplars only. Signed volume exemplars come from `sig_exemplars`,
    are not subject to rule 2 (a named index cannot beg the question), and the card shows them
    first -- they were signed for this purpose, and a truth span merely happens to contain the
    letter."""
    # `partner` was one letter name. p798:n0 has THREE candidates at one position (he, tav, het)
    # and p254:n1 has three at each of two positions, and rule 2 has to hold against EVERY rival or
    # it does not hold at all: a word containing any other candidate can still beg the question.
    # A bare string is still accepted, so the two decided cards call this exactly as before.
    ch = LETTER[letter]
    partners = (partner,) if isinstance(partner, str) and partner else tuple(partner or ())
    pch = [LETTER[p] for p in partners]
    rows = []
    for s in D.build_set(include_sealed=True):
        t = strip_nikud(s["truth"])
        if not t or s["truth"] == D.NOT_HEBREW or ch not in t:
            continue
        if any(p in t for p in pch):
            continue
        if s["span_id"] in exclude:
            continue
        occ = [x for x in positions(s["truth"], ch) if x not in DISPUTED.get(s["span_id"], [])]
        if not occ:
            continue
        if s["unscorable"] and "crop-fault" in str(s["unscorable"]):
            continue
        p = D.CROPDIR / (s["span_id"].replace(":", "_") + "_A2_spanbox.png")
        if not p.exists():
            continue
        bb = ink_bbox(Image.open(p))
        if not bb:
            continue
        im = Image.open(p)
        ink = (bb[2] - bb[0]) * (bb[3] - bb[1]) / float(max(1, im.width * im.height))
        rows.append((len(t.replace(" ", "")), -round(ink, 3), s["span_id"], s, p, occ))
    rows.sort()
    return [(sid, s, p, occ) for _n, _i, sid, s, p, occ in rows[:want]]


def _unguarded_exemplars(letter, partner):
    """exemplars() with rule 2b switched off, for the born-test only."""
    saved = dict(DISPUTED)
    DISPUTED.clear()
    try:
        return exemplars(letter, partner)
    finally:
        DISPUTED.update(saved)


# --- WHAT A SPAN STILL NEEDS BEFORE IT CAN BE SIGNED --------------------------------------------
# Ruling 2026-11-01. A need is a KEY with a predicate, never a sentence. Item 2 of that ruling asks
# for a check that a card's "insufficient" note cites only needs that are currently UNMET, and a
# sentence cannot be evaluated -- so the audit's two free-text needs are decomposed here into the
# keys they name:
#
#   p233:n4  "zayin exemplars from this fount"
#              -> exemplar:zayin
#   p628:n2  "a strip with the baseline visible, final-nun and vav exemplars from this fount, and
#             the Latin gloss as the expected tile"
#              -> strip_baseline, exemplar:final_nun, exemplar:vav, latin_gloss
#
# The audit file is NOT edited to hold these. `audit_overlay_20261025.py` records what a human
# adjudicated on 2026-10-25; a need is a statement about what this console can currently supply,
# which changes every time a renderer lands, and writing one into the adjudication record would
# make a moving quantity look like a signed finding. Each entry carries its own provenance so a
# later reader can tell which needs came from the audit and which this lane added.
NEEDS = {
    "p233:n4": (("exemplar:zayin", "audit"),),
    # Ruling 2026-11-01 item 4 asked for these two to be recorded as reversal hits. They are not.
    # p910:n3 is `not_adjudicated` with reversed=False; p596:n2 has no audit row at all; and the
    # only reversal hit in the twenty-row audit is p442:n0, which is already signable. So what is
    # recorded is what is actually missing. Both also fail item 3's qualifying clause, so these
    # needs do not currently decide anything -- they are here so that if a verdict ever lands, the
    # need does not have to be remembered.
    "p910:n3": (("adjudication", "laneB"),),
    # Chris, 2026-11-08: "p596:n2 goes on the next sheet by hash." `audit_row` STAYS -- he also
    # said no audit rows written by hand, so nobody has adjudicated this span and the record
    # should not pretend otherwise. What changes is that the audit row is no longer the thing
    # blocking it: `sheet` is, and `sheet` is met by building the next sheet, which is work this
    # lane can actually do. The two needs say different things and both are true.
    "p596:n2": (("sheet", "laneB"), ("audit_row", "laneB")),
    "p628:n2": (("strip_baseline", "audit"), ("exemplar:final_nun", "audit"),
                ("exemplar:vav", "audit"), ("latin_gloss", "audit")),
}

# Human-directed sheet inclusions: a THIRD route onto a sheet, beside a qualifying audit
# verdict and a reversal flag. Chris, 2026-11-08: "p596:n2 goes on the next sheet by hash; no
# audit rows written by hand." Deliberately NOT folded into audit_qualifies -- that function
# answers what a human adjudicated on 2026-10-25, and a directive about a future sheet is not
# a verdict about pixels. Keeping them apart is also what leaves `signable` alone, so the
# five-span console already built does not quietly grow a sixth row.
#
# `pixel_pin` is the point of "by hash": the file, and 16 hex of SHA-256 over its bytes, so a
# sheet cannot carry a different crop under the same span id. `sheet_crop_sha16` is the sheet's
# OWN crop and is None until a sheet exists -- which is what makes the `sheet` need falsifiable
# without scanning a directory for documents.
DIRECTED = {
    "p596:n2": dict(
        on="2026-11-08",
        by="Chris",
        words="p596:n2 goes on the next sheet by hash; no audit rows written by hand",
        # Relative to D.DATA, which is the AUDITS directory, not the volume root. The first
        # version of this entry wrote "audits/..." and the pin reported the crop gone --
        # which is the gate working: a pin that cannot find its file must fail, not abstain.
        pixel_pin=("hebrew_aperture_crops_20260920/p596_n2_A2_spanbox.png",
                   "842abe52c2829e14"),
        sheet_crop_sha16=None,
        # p596 is a SEALED page (measured: 596 in D.SEALED, p596:n2 in D.SEALED_TRUTH), and
        # ruling 2 of 2026-09-20 opens sealed pages for a READ in the aperture harness only.
        # A signing sheet is not that read: glyph_signer carries its own refusal, "re-sign
        # span(s) ... are in HAD.SEALED_TRUTH -- sealed pages are SPENT". The directive and
        # the seal collided, Chris was asked, and he ruled the seal holds -- so this stays
        # None. None means NO RULING LIFTS THE SEAL, which is what he decided; it is not a
        # pending field. A field recording "the seal was upheld" would read, to a later
        # consumer, as a ruling that opened the page.
        seal_ruling=None,
        # The order above is NOT edited to agree with the ruling that overturned it. It is
        # what he asked for on 2026-11-08 and it stays legible as that; the withdrawal
        # stands beside it with its own date and its own words. Same standoff rule this lane
        # applies to the printed text: the reading lives next to the form, never over it.
        sheet_withdrawn=dict(
            on="2026-11-08", by="Chris",
            words="Ruling 2 opened sealed pages for a machine read in the aperture harness; "
                  "putting a sealed span's glyph cards in front of a human signer is a "
                  "different act and I'm not widening it for one span. Withdraw the sheet "
                  "clause, reissue the readiness line as sealed, not missing, keep the pin "
                  "and seal_ruling=None as the record.",
            leaves="the pin, the order, and the span's standing: SEALED, and final",
        ),
        licenses="sheet inclusion only: not a verdict, and not a qualifying audit row",
    ),
}

NEED_TEXT = {
    "strip_baseline": "a strip with the baseline visible",
    "adjudication": "a human verdict: the 2026-10-25 audit never reached this row",
    "audit_row": "an audit row at all: this span was never adjudicated (not a precondition "
                 "for being SHEETED, only for being re-signed under item 3)",
    "sheet": "a signing sheet that contains it: it has never been on one",
    "latin_gloss": "the Latin gloss as the expected tile",
    "reading_order_tiles": "a reading-order tile card showing the candidate and its reverse",
}


def pin_holds(span_id):
    """(holds, why) -- does the directive's pinned file still hash to what it recorded?

    Re-read from the bytes, never from a sidecar: a pin that trusted a recorded number to
    verify itself would agree by construction. A missing file is a failure, not an abstention,
    because "the pixels this directive is about" is the whole content of "by hash".
    """
    d = DIRECTED.get(span_id)
    if d is None:
        return False, "no directive recorded for this span"
    rel, want = d["pixel_pin"]
    path = D.DATA / rel
    if not path.exists():
        return False, "the pinned crop is gone: %s" % rel
    with io.open(path, "rb") as fh:
        got = hashlib.sha256(fh.read()).hexdigest()[:16]
    if got != want:
        return False, "the pinned crop now hashes %s, not %s" % (got, want)
    return True, "pinned crop %s matches %s" % (rel.rsplit("/", 1)[-1], want)


def directed(span_id):
    """(directed, why) -- is this span on a sheet by a human's instruction, pins holding?"""
    d = DIRECTED.get(span_id)
    if d is None:
        return False, "no directive recorded for this span"
    ok, why = pin_holds(span_id)
    if not ok:
        return False, "directed %s by %s, but %s" % (d["on"], d["by"], why)
    return True, "directed %s by %s: %s (%s)" % (d["on"], d["by"], d["words"], why)


def seal_state(span_id):
    """(sealed, why) -- is this span under the seal, and is there a ruling that lifts it?

    Page-level, because that is how the seal is recorded: `D.SEALED` is 14 pages. The span
    table `D.SEALED_TRUTH` is consulted too and reported when it adds anything, but the page
    is the governing fact -- a span on a sealed page is sealed whether or not the Hebrew
    table happens to carry a row for it.

    A ruling is read off the DIRECTIVE, never off a page or a date: "somebody decided this"
    is a thing a human writes down, and nothing here infers it.
    """
    page = int(span_id.split(":")[0].lstrip("p"))
    in_page, in_table = page in D.SEALED, span_id in D.SEALED_TRUTH
    if not (in_page or in_table):
        return False, "page %d is not sealed" % page
    where = "page %d is SEALED" % page + (" and the span is in SEALED_TRUTH" if in_table
                                          else " (no SEALED_TRUTH row)")
    d = DIRECTED.get(span_id) or {}
    r = d.get("seal_ruling")
    if r:
        return True, "%s; lifted for a sheet by: %s" % (where, r)
    return True, "%s; no ruling lifts it for a signing surface" % where


SHEET_CODES = ("not_directed", "withdrawn", "collision", "ok")


def sheet_verdict(directive, sealed, seal_why):
    """(code, why) -- may a sheet contain this span? The whole table, in one place.

    Every input is a REQUIRED ARGUMENT and none is derived here. That is deliberate twice
    over. A predicate that fetches its own inputs cannot be driven through its own rows, and
    this lane has already shipped one that silently took the wrong channel for 74 of 74
    spans. And since p596:n2 is now withdrawn before it reaches the collision row, a table
    driven only by live spans would stop exercising the row Chris asked be kept.

    Order matters: WITHDRAWN outranks COLLISION. A collision is an open question; a
    withdrawal is the answer to one. Reporting a settled matter as still colliding would ask
    a human to rule on something he has already ruled on.
    """
    if directive is None:
        return "not_directed", "no directive that a sheet contain this span"
    w = directive.get("sheet_withdrawn")
    if w:
        return "withdrawn", ("the sheet clause was WITHDRAWN %s by %s: %s%s"
                             % (w["on"], w["by"], w["words"],
                                "" if not sealed else
                                " -- %s, and that standing is final" % seal_why))
    if sealed and not directive.get("seal_ruling"):
        return "collision", ("COLLISION: a directive puts this span on a sheet, and %s. "
                             "Ruling 2 (2026-09-20) opens sealed pages for a READ in the "
                             "aperture harness only, and the signing surface carries its "
                             "own refusal. No sheet is built until a human rules; the "
                             "ruling goes in the directive's seal_ruling field." % seal_why)
    return "ok", "directed onto a sheet, and nothing holds it back"


def sheetable(span_id):
    """(sheetable, why) -- may the NEXT sheet contain this span?

    Wider than `signable` on purpose. `signable` is item 3's rule for RE-signing a span the
    2026-10-25 audit ruled on, and the five-span console is built to it. This answers a
    different question -- what goes on the next sheet -- and a human's directive is an answer
    to it that no audit verdict can supply. Nothing that is signable is excluded here.
    """
    ok, why = signable(span_id)
    if ok:
        return True, "signable: %s" % why
    dok, dwhy = directed(span_id)
    if not dok:
        return False, "not signable (%s) and not directed (%s)" % (why, dwhy)
    # A directive is an answer to "what goes on the next sheet"; the seal is an answer to
    # "what may be opened at all", and the second was never this console's to overrule.
    # Answering True here would license a build that glyph_signer refuses, and that refusal
    # is the guard a builder would then be tempted to "fix".
    sealed, swhy = seal_state(span_id)
    code, cwhy = sheet_verdict(DIRECTED.get(span_id), sealed, swhy)
    if code == "ok":
        return True, dwhy + ("" if not sealed else " [%s]" % swhy)
    return False, "%s -- %s" % (dwhy, cwhy)


def need_text(key):
    """The need in words, for a card to print. Derived from the key, so the two cannot drift."""
    if key.startswith("exemplar:"):
        return "%s exemplars from this fount" % key.split(":", 1)[1].replace("_", "-")
    return NEED_TEXT.get(key, key)


def _ask_partners(span_id, letter):
    """The rival candidates the card asks against at the position holding `letter`.

    Rule 2 holds against EVERY rival or it does not hold, so an exemplar count that ignored the
    other candidates at the same position would be a different number from the one on the card.
    """
    for c in CARDS:
        if c["span_id"] != span_id:
            continue
        for a in c.get("asks") or ():
            cand = tuple(a.get("candidates") or ())
            if letter in cand:
                return tuple(x for x in cand if x != letter)
    return ()


def need_met(span_id, key):
    """(met, why) for one need, read off the record -- never off a note or a tally.

    `strip_baseline` is the one that moved on 2026-10-25: item 5 landed, so a card still citing it
    is citing a satisfied need. It is answered by building the strip and asking whether the
    threshold rule ABSTAINED, not by asking whether the renderer exists -- an abstention leaves a
    span with no baseline even though the code to draw one is present.
    """
    if key == "strip_baseline":
        # card_spans(), NOT build_set. The first version of this asked build_set and reported
        # "the span is not in the build set" for p628:n2, which is in the FROZEN set -- so a need
        # the record SATISFIES came back unmet, and the card would have gone on refusing for a
        # reason this function invented. A predicate that derives its own input from the wrong
        # source fails in the direction that looks like a finding.
        row = card_spans()[0].get(span_id)   # (spans, refused, overlap)
        if row is None:
            return False, "no span record a strip could be cut from"
        sp = line_strip(row["page"], row["span_box"], row["column_bands"])
        if sp.get("why"):
            return False, "no strip: %s" % sp["why"]
        si = strip_image(sp)
        if si["baseline"] is None:
            return False, "the threshold rule abstained on this strip"
        return True, "baseline derived at strip row %d" % si["baseline"]
    if key == "latin_gloss":
        _t, _state, _why = latin_gloss(span_id)
        return (_state == "present"), ("gloss %s" % _state) + (": %s" % _why if _why else "")
    if key.startswith("exemplar:"):
        letter = key.split(":", 1)[1]
        if letter not in LETTER:
            return False, "no such letter: %s" % letter
        partners = _ask_partners(span_id, letter)
        n_sig = len(sig_exemplars(letter))
        n_span = len(exemplars(letter, partners, exclude=(span_id,)))
        return (n_sig + n_span >= 1), "%d signed + %d span exemplar(s)" % (n_sig, n_span)
    if key == "sheet":
        # Read off the directive's own sheet_crop_sha16, not off a scan of the audits folder.
        # The question is "has a sheet been built that shows THESE pixels", and only the build
        # that cut the crop can answer that; a document found by filename glob would answer a
        # weaker question and call it this one.
        d = DIRECTED.get(span_id)
        if d is None:
            return False, "no sheet, and no directive that one be built"
        if d.get("sheet_crop_sha16"):
            return True, "sheeted, crop %s" % d["sheet_crop_sha16"]
        # "not built yet" promises a sheet is coming, and for this span none is. An unmet
        # need that reads as pending is how a readiness report files a decision as a gap --
        # which mine did on 2026-11-01, and which is the sentence Chris told me to reissue.
        # The need stays unmet (the span has never been on a sheet, and that is true), but
        # it is no longer OWED, and the difference is the whole point of saying so here.
        sealed, swhy = seal_state(span_id)
        code, cwhy = sheet_verdict(d, sealed, swhy)
        if code == "withdrawn":
            return False, "CLOSED, not owed: %s" % cwhy
        if code == "collision":
            return False, "BLOCKED by the seal, not merely unbuilt: %s" % cwhy
        return False, "directed onto the next sheet %s; that sheet is not built yet" % d["on"]
    if key in ("adjudication", "audit_row"):
        # Not a thing this console can supply, and deliberately not faked as one. These report the
        # same fact item 3's qualifying clause reports, from the other side: nobody decided.
        return False, "only a human adjudication can meet this"
    if key == "reading_order_tiles":
        # No card renders a candidate beside its reverse yet. The signer's reversal guard refuses a
        # download whose assembly is the candidate reversed, which is a different thing: it catches
        # a reversal after a human signed one, and cannot show a human which reading is which.
        return False, "no card renders the candidate beside its reverse"
    return False, "unknown need key"


def needs_state(span_id):
    """Every recorded need for a span, each with its provenance and whether it is met NOW."""
    out = []
    for key, source in NEEDS.get(span_id, ()):
        met, why = need_met(span_id, key)
        out.append(dict(key=key, source=source, met=met, why=why, text=need_text(key)))
    return out


def unmet(span_id):
    return [n["key"] for n in needs_state(span_id) if not n["met"]]


def audit_qualifies(span_id):
    """(qualifies, why) under ruling 2026-11-01 item 3's first clause.

    Signature, signature-suspect-unsettled, or a reversal hit. `not_adjudicated` is none of those,
    and a span absent from the audit has no verdict at all -- neither is a near miss to be waved
    through, because the clause names what a human decided and those two record that nobody did.
    """
    import audit_overlay_20261025 as _A
    rows = [r for r in _A.AUDIT if r["span_id"] == span_id]
    if not rows:
        return False, "absent from the audit: no verdict and no reversal flag"
    vs = sorted(set(r["verdict"] for r in rows))
    if any(r["reversed"] for r in rows):
        return True, "reversal hit (verdicts %s)" % ", ".join(vs)
    for v in ("signature", "signature_suspect_unsettled"):
        if v in vs:
            return True, "verdict %s" % v
    return False, "verdicts %s, and not a reversal hit" % ", ".join(vs)


def signable(span_id):
    """(signable, why) -- ruling 2026-11-01 item 3, as a rule over the record.

    Readiness is "has a surface and all needs met" (item 4). This function is the second half; the
    first half is whether the signer builds a console containing the span at all, which is this
    same predicate read by glyph_signer. A card whose needs are unmet stays NO VERDICT and is
    absent from the signer, so the two surfaces cannot disagree about one span.
    """
    ok, why = audit_qualifies(span_id)
    if not ok:
        return False, why
    u = unmet(span_id)
    if u:
        return False, "needs unmet: %s" % ", ".join(u)
    return True, "%s, every recorded need met" % why


def census():
    """How many unambiguous exemplars each candidate letter actually has. MEASURED, not assumed.

    The result as of 2026-09-27 over the 21-span signed set: mem 3, pe 2, bet 4 (5 occurrences on
    p912:n2 alone), gimel 1, and ZERO spans containing both letters of either pair -- so the ideal
    exemplar, one impression showing both candidates side by side, does not exist in this corpus and
    cannot be manufactured from it. pe and gimel fall below the floor of three.

    This is a corpus limit, not a bug, and the fix is not code: any word on any page whose letter a
    human will name is an exemplar of the same authority as a signature. One minute of pointing adds
    what 21 signed spans cannot."""
    out = {}
    for a, b in (("mem", "pe"), ("pe", "mem"), ("bet", "gimel"), ("gimel", "bet")):
        ex = exemplars(a, b, want=99)
        out[a] = dict(n=len(ex), spans=[sid for sid, _s, _p, _o in ex],
                      occurrences=sum(len(o) for _x, _s, _p, o in ex))
    both = []
    for pair in (("mem", "pe"), ("bet", "gimel")):
        A, B = LETTER[pair[0]], LETTER[pair[1]]
        for x in D.build_set(include_sealed=True):
            if x["truth"] == D.NOT_HEBREW or not x["truth"]:
                continue
            pa = [q for q in positions(x["truth"], A) if q not in DISPUTED.get(x["span_id"], [])]
            pb = [q for q in positions(x["truth"], B) if q not in DISPUTED.get(x["span_id"], [])]
            if pa and pb:
                both.append((x["span_id"], "/".join(pair)))
    out["contrast_pairs"] = both
    good, bad = sig_load()
    for k in ("mem", "pe", "bet", "gimel"):
        sg = [r for r in good if r["letter"] == k]
        out[k]["signatures"] = len(sg)
        out[k]["total"] = out[k]["n"] + len(sg)
    out["signature_refusals"] = [(r.get("_line"), r.get("_refused")) for r in bad]
    # A signed word holding BOTH candidates is the contrast pair the signed set could not supply.
    for pair in (("mem", "pe"), ("bet", "gimel")):
        for r in good:
            w = strip_nikud(r["word"])
            if LETTER[pair[0]] in w and LETTER[pair[1]] in w:
                both.append(("sig:p%s:%s" % (r["file_page"], r["word"]), "/".join(pair)))
    return out


def b64(im):
    b = io.BytesIO()
    im.save(b, format="PNG")
    return base64.b64encode(b.getvalue()).decode()


def img_comp(im, unratified=False):
    """A comparison image: matched letterform scale, true size, never width-capped."""
    m, f, bh = comparison(im)
    return ('<img class="comp" src="data:image/png;base64,%s" title="%sline band %spx native, '
            'scaled to %dpx (NEAREST x%s) -- same scale as every other comparison image here">'
            % (b64(m), "UNRATIFIED, not the signed span -- " if unratified else "", bh,
               TARGET_BAND, f))


def img_ctx(im, up=1):
    """A context image: native scale or up, fitted to the page width by the browser, not by resampling."""
    g, f = context(im, up)
    return ('<img class="ctx" src="data:image/png;base64,%s" title="native pixels x%s">'
            % (b64(g), f))


def img_strip(im, f):
    """A strip image: never width-capped. It is for judging a vertical extent, not for locating."""
    return ('<img class="strip" src="data:image/png;base64,%s" title="the span\'s own line of type, '
            'native pixels at NEAREST x%d; every mark is painted on paper pixels only, so no ink is '
            'hidden">' % (b64(im), f))


CSS = """
:root{--bg:#0e1116;--fg:#e6e6e6;--mut:#9aa4b2;--acc:#7dd3fc;--warn:#fbbf24;--bad:#f87171;
--ok:#4ade80;--card:#161b22;--line:#2d333b}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.55 -apple-system,Segoe UI,sans-serif;
padding:24px 16px}
.wrap{max-width:1180px;margin:0 auto}
h1{font-size:20px;margin:0 0 4px}
.sub{color:var(--mut);font-size:13px;margin-bottom:6px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:20px 0}
.hd{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;margin-bottom:8px}
.sid{font:15px ui-monospace,Consolas,monospace;color:var(--acc)}
.badge{font-size:11px;padding:2px 8px;border-radius:99px;border:1px solid var(--line);
text-transform:uppercase;letter-spacing:.04em}
.open{background:#3b2f0b;color:var(--warn);border-color:#6b5310}
.done{background:#0b2f1b;color:var(--ok);border-color:#14532d}
.q{font-size:16px;margin:10px 0}
.heb{font-size:26px;font-family:"Times New Roman",serif}
.mut{color:var(--mut)}
.row{display:flex;gap:14px;align-items:flex-end;margin:10px 0;overflow-x:auto;padding-bottom:6px}
.row.wrap{flex-wrap:wrap}
.cell{border:1px solid var(--line);border-radius:8px;padding:8px;background:#0b0e13}
.cap{font-size:12px;color:var(--mut);margin-top:6px;max-width:470px}
img{display:block;image-rendering:pixelated;background:#fff;border-radius:3px}
/* .comp is NEVER constrained: a browser-downscaled comparison image is a lie about scale. Wide ones
   overflow into the scrolling strip at true size. .ctx may be fitted -- it is for locating, not judging. */
img.comp{max-width:none}
/* .strip answers "does this glyph cross the line", which a browser-downscaled image cannot. */
img.strip{max-width:none;image-rendering:pixelated}
img.ctx{max-width:100%}
.cell{flex:0 0 auto}
.lbl{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--mut);margin:16px 0 4px}
.feat{border-left:3px solid var(--acc);padding:6px 12px;margin:8px 0;background:#0b1620}
.warnbox{border-left:3px solid var(--bad);padding:8px 12px;background:#1b0f10;margin:10px 0}
.note{font-size:13px;color:var(--mut);border-top:1px solid var(--line);margin-top:14px;padding-top:10px}
code{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:var(--acc)}
pre.paste{font-family:ui-monospace,Consolas,monospace;font-size:11px;color:#cbd5e1;background:#0b0e13;
border:1px solid var(--line);border-radius:6px;padding:8px;overflow-x:auto;white-space:pre-wrap;
word-break:break-all;margin:6px 0}
.prov{font-size:11px;color:#64748b;font-family:ui-monospace,Consolas,monospace}
"""


# --- THE POPULATION BRIDGE ------------------------------------------------------------------
# `D.build_set` reaches 21 spans and reads their signed string from the TRUTH / SEALED_TRUTH table.
# Seven of ruling 4's eight owed spans are not in it; they live in the frozen 74-span signer set.
# That set's `hebrew` column is the CANDIDATE -- the machine's proposal, the signer's INPUT -- and it
# is not the signature. On the two spans the ruling puts first they differ in LENGTH, because pass 2
# is the insertion pass: p233:n4's candidate is 4 consonants and its signature is 6 (two inserted
# vavs), p831:n2's candidate is 6 and its signature is 7 (one inserted resh). A card's `pos` is
# counted in the SIGNED string, so a card built from the candidate points at the wrong glyph.
#
# So the signature is DERIVED from the signed verdicts. The derivation is not re-ported here: it is
# `signature_attestation.derive_in_crop`, already shipped and already checked against the console's
# own `derived_consonants` (a cross-lineage witness -- the console computes it in JavaScript). I
# measured the three existing derivations against each other over all 74 latest rows: they disagree
# on 4, every one of them a row carrying a `disputed`, `deleted` or `not_in_crop` verdict, and two of
# those four also disagree with the console. The gate below refuses exactly that population, so the
# bridge only ever runs where all three agree -- which is measured, not assumed.
#
# BOX PROVENANCE IS NOT THE SAME IN THE TWO POPULATIONS, and the page must not pretend it is. A
# build_set box is a HUMAN-RATIFIED rect from `span_box_verdicts_20260906.jsonl`. A frozen-set box is
# machine-drawn by the draw pool. The two populations are very nearly disjoint -- one span of 74 is in
# both, and it has no ratified box -- so there is no cross-check available and no span whose two boxes
# could be compared. `card_spans` stamps the provenance on every record it returns, so the caption can
# state which kind of box the signer is looking at rather than calling a drawn rect ratified.
#
# THE FROZEN RECORDS CARRY NO NOTE BOX. That is the state of the evidence, not a shortcut: of the
# eight owed pages only p596 (the sealed one, which build_set already reaches) has a ratified note box
# at all. Deriving one from `note_line_regions(...)[note_index - 1]` was available and is refused --
# that is the geometry the draw pool used to place the span box in the first place, so it could not
# witness it, and this lane has already shipped one wrong-line crop that way. The note cell simply
# does not render for these seven, and the card is the span crop plus its magnified line.

FROZEN_SET = D.DATA / "truth_set74_0401b636ffa7bf1a.json"

# Later file wins: a re-sign supersedes the signature it replaces. The tag is what lands in
# `truth_basis`, so a reader can name the export a card's string came from without opening this file.
FROZEN_EXPORTS = (
    ("glyphsign_signed_0401b636ffa7bf1a_20261004_pass1.jsonl", "pass1:20261004"),
    ("glyphsign_0401b636ffa7bf1a_pass2_26span_signed_3285d39a.jsonl", "pass2:3285d39a"),
    ("glyphsign_0401b636ffa7bf1a_pass3_r2_3span_signed_70fc08e1.jsonl", "pass3r2:70fc08e1"),
)


# The verdicts all three shipped derivations render identically. Measured over the 74 latest signed
# rows: `ingest_pass2.derive`, `signature_attestation.derive_in_crop` and the console's own
# `derivedFor` agree on every row carrying only these, and disagree on all 4 that carry anything else
# -- two of those 4 disagreeing with the console itself. `confirmed` and `corrected` cover both tile
# kinds: a gap tile is a WORD SPACE, emitted as a space by every port, and it is what `words()` splits
# on and what a card's per-word `pos` counts within.
AGREED_VERDICTS = ("confirmed", "corrected")


def _derivable(r):
    """Why this signed row may NOT be derived into a card signature, or None when it may.

    One rule: the row must be complete and unfaulted, and every verdict on it must be one the three
    shipped derivations render the same way. That is the stated rule -- "an unfilled verdict emits
    nothing and is reported, never guessed" -- with the same treatment extended to the verdicts where
    the ports diverge, and it is not defensive padding. A glyph the signer marked `not_in_crop` is BY
    HIS OWN VERDICT not in the picture, so there is no glyph on the card to count to; `deleted` and
    `disputed` have no single character to put in a string at all.

    It refuses nothing else. An earlier draft also refused gap tiles and insertions anchored before
    the first tile; both are rendered identically by all three ports, so refusing them asserted a
    disagreement the measurement did not find -- and the gap clause would have refused every
    multi-word span, which is the population `words()` and `where()` exist to serve.
    """
    if not r.get("complete"):
        return "the row is not complete"
    if r.get("fault"):
        return "the row carries fault %r" % r["fault"]
    for t in r["tiles"]:
        v = t.get("verdict") or ""
        if v not in AGREED_VERDICTS:
            # A claim about the VERDICT, not about this row. Of the four rows where the ports
            # actually produce different strings, one lands here and three are caught by the
            # `complete` clause above; the other three rows refused here carry a `deleted` or
            # `disputed` tile that the ports happen to agree on. Saying "the derivations disagree on
            # this row" would be false on three of four refusals, and an operator chasing it would
            # find nothing.
            return ("tile %s is %s, which is outside the set of verdicts all three shipped "
                    "derivations render identically" % (t["i"], v or "unfilled"))
        if v == "corrected" and t["kind"] == "consonant" and not t.get("chose"):
            return "tile %s is corrected with nothing chosen" % t["i"]
    for x in (r.get("insertions") or []):
        if x.get("verdict"):
            return "insertion %s carries verdict %r" % (x.get("seq"), x["verdict"])
        if not x.get("chose"):
            return "insertion %s has nothing chosen" % x.get("seq")
    return None


def frozen_spans():
    """Card-shaped records for the frozen 74-span set, with the DERIVED signature as `truth`.

    Returns (records_by_span_id, refusals). A refusal is shown on the page, never swallowed: a
    capture surface that drops a span in silence leaves the signer believing a card is there.
    """
    d = json.loads(io.open(str(FROZEN_SET), encoding="utf-8").read())
    rows = {r["span_id"]: r for r in d["rows"]}
    signed, tag = {}, {}
    for fn, t in FROZEN_EXPORTS:
        p = D.DATA / fn
        if not p.exists():
            continue
        for ln in io.open(str(p), encoding="utf-8"):
            ln = ln.strip()
            if not ln:
                continue
            o = json.loads(ln)
            if "span_id" in o and "tiles" in o:
                signed[o["span_id"]], tag[o["span_id"]] = o, t
    out, refused = {}, []
    for sid, r in sorted(rows.items()):
        sg = signed.get(sid)
        if sg is None:
            refused.append({"span_id": sid, "_refused": "absent from every signed export",
                            "set": FROZEN_SET.name})
            continue
        why = _derivable(sg)
        if why:
            refused.append({"span_id": sid, "_refused": why, "export": tag[sid]})
            continue
        truth = SA.derive_in_crop(sg)
        if not truth:
            refused.append({"span_id": sid, "_refused": "the derivation is empty",
                            "export": tag[sid]})
            continue
        out[sid] = dict(
            span_id=sid, page=r["page"], note_idx=r["note_index"],
            signed=sg.get("chosen"), latin_context="",
            truth=truth, truth_basis="derived-from-signed-verdicts:" + tag[sid],
            unscorable=None, sealed=(r["page"] in D.SEALED),
            # No ratified note box exists for these pages, and an index-derived one is refused
            # above. `cut` is never called with None, so the note cell does not render.
            note_box=None, note_box_status=None,
            a1_idx_declared=r["note_index"], a1_idx_used=None, a1_span_overlap=None,
            a1_clips_span_frac=None,
            # Strip coords, as `glyph_signer` cuts them (`_box_strip`); `cut` maps strip -> native.
            span_box=list(r["box"]),
            # None makes `cut` recompute the bands from the page, which is what the runner does.
            column_bands=None, n_ratified=None,
            crop_unmeasured=True)
    return out, refused


def card_spans():
    """Every span a card can be built from: build_set where it reaches, the frozen set elsewhere.

    build_set is authoritative where it reaches -- its string is a table a human signed and its box is
    a human-ratified rect, which is strictly more than a derivation over verdicts. The frozen set
    fills in the rest. `box_provenance` is stamped on EVERY record, so the caption can never be
    rendered without knowing which kind of box it is describing.
    """
    out = {}
    for s in D.build_set(include_sealed=True):
        s = dict(s)
        s["box_provenance"] = "human-ratified"
        out[s["span_id"]] = s
    fz, refused = frozen_spans()
    overlap = sorted(set(fz) & set(out))
    for sid, s in fz.items():
        if sid in out:
            continue
        s["box_provenance"] = "draw-pool"
        out[sid] = s
    return out, refused, overlap


def build(out=None):
    out = out or OUTHTML
    spans, _bridge_refused, _bridge_overlap = card_spans()
    h = ['<!doctype html><meta charset="utf-8"><title>Hebrew glyph cards</title>',
         "<style>%s</style><div class=\"wrap\">" % CSS,
         "<h1>Hebrew glyph cards &mdash; shape verdicts</h1>",
         '<div class="sub">All page numbers are FILE pages; printed = file &minus; 88. Every image '
         'is real page pixels, upscaled NEAREST &mdash; no smoothing, because a resampled curl is an '
         'invented curl. <b>Comparison</b> images are cropped to their text line and scaled so that '
         'line is %dpx tall, so any two of them are at the same letterform scale; they are never '
         'fitted to the window, so a wide one scrolls rather than shrink. <b>Context</b> images '
         '(whole notes, recovery windows) are at native size and are for locating text, not for '
         'judging a letter.</div>' % TARGET_BAND,
         '<div class="sub">Verdict only: no model reading appears anywhere on this page. The target '
         'letter is named by COUNTING in the signed string (glyph N from the right = character N, '
         'since Hebrew is stored in reading order). No pointer is drawn under it &mdash; the module '
         'docstring gives the two measurements that rejected one.</div>']

    # Refused records are shown, not swallowed. A capture surface that silently drops a mis-drawn box
    # leaves the signer believing an exemplar is on the page when it is not.
    _sg, _sb = sig_load()
    _rg, _rb = rerat_load()
    h.append('<div class="sub">Signed records loaded: %d exemplar signature(s) from the volume, %d '
             'box re-ratification(s).</div>' % (len(_sg), len(_rg)))
    h.append('<div class="sub">Spans reachable for a card: %d &mdash; %d with a human-ratified '
             'box from the signed sitting, %d from the frozen 74-span signer set whose signature is '
             'DERIVED from the signed verdicts and whose box is drawn, not ratified. %d frozen row(s) '
             'refused. %d span(s) in both populations, where the ratified record wins.</div>'
             % (len(spans), sum(1 for x in spans.values() if x["box_provenance"] == "human-ratified"),
                sum(1 for x in spans.values() if x["box_provenance"] == "draw-pool"),
                len(_bridge_refused), len(_bridge_overlap)))
    for src, refused in (("exemplar signature", _sb), ("box re-ratification", _rb),
                         ("frozen-set span", _bridge_refused)):
        for r in refused:
            # The line number is printed only when there is one. A JSONL refusal has one; a
            # frozen-set refusal is about a span and has nothing to put there, and "line None" on a
            # signing surface invites a reader to go looking for a line that does not exist.
            # NOT `where` -- that is a module-level function this very function calls further
            # down, and shadowing it crashed the whole render while the selftest stayed green.
            at = "" if r.get("_line") is None else ", line %s" % r["_line"]
            h.append('<div class="warnbox">REFUSED %s%s: %s<br><span class="prov">%s</span>'
                     '</div>' % (src, at, r.get("_refused"),
                                 json.dumps({k: v for k, v in r.items()
                                             if not k.startswith("_")}, ensure_ascii=False)[:400]))

    for c in CARDS:
        s = spans[c["span_id"]]
        pg = s["page"]
        done = c["status"].startswith("DECIDED")
        h.append('<div class="card">')
        h.append('<div class="hd"><span class="sid">%s</span><span class="mut">file p%d &middot; '
                 'printed p%d</span><span class="badge %s">%s</span></div>'
                 % (c["span_id"], pg, pg - 88, "done" if done else "open", c["status"]))
        h.append('<div class="q">%s</div>' % c["question"])
        h.append('<div>signed: <span class="heb" dir="auto">%s</span> <span class="mut">&nbsp;basis '
                 '<code>%s</code></span></div>' % (s["truth"], s["truth_basis"]))
        _lat, _lstate, _lwhy = latin_gloss(c["span_id"])
        if _lstate == "present":
            h.append('<div class="lbl">the note\'s own Latin</div>'
                     '<div class="feat"><i>%s</i><br><span class="prov">From '
                     '<code>vol1_apparatus.jsonl</code> via the scoring-45 contact sheet, which '
                     'resolves note text by the span box\'s POSITION among the page\'s note '
                     'regions &mdash; not by the <code>n</code> in the span id &mdash; and records '
                     'five witnesses, all matched for this span. Hebrew runs in the note are masked '
                     'to &bull;. <b>This console does not translate it and draws no inference from '
                     'it.</b> It is the note\'s own words, put beside the picture so a signer can '
                     'use them or set them aside.</span></div>' % esc(_lat))
        else:
            h.append('<div class="lbl">the note\'s own Latin</div>'
                     '<div class="warnbox">ABSENT: %s.</div>' % esc(_lwhy))
        # Derived from the row being printed, never from PENDING_RESIGN alone -- see `resign_state`.
        # Until 2026-10-25 this branch labelled three strings SUPERSEDED that were the batch's own
        # corrected output, because the table was consulted and the basis beside it was not.
        _rstate, _rclaim = resign_state(c["span_id"], s["truth_basis"])
        if _rstate == "pending":
            h.append('<div class="warnbox">The string above is SUPERSEDED: %s.</div>' % _rclaim)
        elif _rstate == "landed":
            h.append('<div class="feat"><b>History, not a warning.</b> %s. <b>That batch has since '
                     'LANDED in this row</b> &mdash; the basis above, <code>%s</code>, carries the '
                     'batch\'s own stamp, so the string printed above is the batch\'s OUTPUT and '
                     'not the string it replaced. This console called it SUPERSEDED until '
                     '2026-10-25, on three cards, over the corrected strings.</div>'
                     % (_rclaim, esc(s["truth_basis"] or "")))
        for _ask in card_asks(c):
            ws = words(s["truth"])
            w = (' in word %d, <span class="heb" dir="auto">%s</span> (word 1 is the rightmost)'
                 % (_ask["word"], ws[_ask["word"] - 1])) if _ask.get("word") else ""
            _ps = ask_positions(_ask)
            _gs = glyphs_at(s["truth"], _ask)
            # The card SHOWS the glyph it is counting to. A `pos` is an instruction to cut a
            # particular letter, so printing the character the signature holds there turns a wrong
            # number into something a reader can see rather than something they act on.
            _shown = ", ".join('<b>%d</b> (<span class="heb" dir="auto">%s</span>)'
                               % (p, g if g else "&mdash;") for p, g in zip(_ps, _gs))
            h.append('<div class="mut">Count glyph %s from the right%s.</div>'
                     % (_shown, w))
            if len(_ps) > 1:
                h.append('<div class="warnbox">This card points at <b>%d adjacent positions</b> '
                         'because no single number discriminates them &mdash; see the two bases '
                         'below. Cut the <b>pair</b>, not one glyph.</div>' % len(_ps))
            if _ask.get("basis"):
                h.append('<div class="feat"><b>Why this position.</b> %s</div>' % _ask["basis"])
            if _ask.get("note"):
                h.append('<div class="warnbox">%s</div>' % fill_note(_ask["note"]))

        bands = s["column_bands"]
        a2, r2 = cut(pg, s["span_box"], D.PAD, bands) if s["span_box"] else (None, [])
        a1, r1 = cut(pg, s["note_box"], 0, bands) if s["note_box"] else (None, [])
        blank = not (a2 and ink_bbox(a2))
        rr = rerat_for(c["span_id"])
        h.append('<div class="lbl">the print</div><div class="row">')
        if rr:
            # RULING 2 (Chris, 2026-09-27): signing the text from the magnified neighbourhood
            # ratifies the box in the SAME record. So there is no UNRATIFIED label here and no empty
            # rectangle kept beside the new one -- the old rect is retired by this record, with a
            # note saying what was wrong with it. The (box, text) binding is one object.
            im = rr["_crop"]
            h.append('<div class="cell">%s<div class="cap">the <b>re-ratified</b> box at NATIVE '
                     'size. It holds <b>%d text line(s)</b>.</div></div>'
                     % (img_ctx(im), n_lines(im)))
            h.append('<div class="cell">%s<div class="cap"><b>the line, magnified.</b> Scaled so '
                     'the text line is %dpx tall &mdash; the same scale as every comparison image '
                     'on this page.</div></div>' % (img_comp(im), TARGET_BAND))
        elif blank:
            win, grew, found, wbox = find_ink(pg, r2 or r1)
            h.append('<div class="cell">%s<div class="cap"><b>NO CROP EXISTS.</b> The ratified span '
                     'box maps to pixels holding no ink, so nothing was ever shown to any reader '
                     'and there is no glyph to magnify. Above is the neighbourhood grown %s; the '
                     'red outline is where the box asked to look. %s</div></div>'
                     % (img_ctx(win, up=2), grew,
                        "Shown at 2x: the text lines here are about 31px native. Find the Hebrew, "
                        "then re-draw the box." if found
                        else "No ink found even at that range."))
            cand = candidate_band_box(pg, wbox) if found else None
            cim = cut_native(pg, cand)[0] if cand else None
            if cim is not None:
                # The letter question is not answerable from the ratified box, but it need not be
                # wholly blocked: the nearest text line in the recovery window can be magnified at the
                # same scale as the exemplars, so a verdict is at least possible. It is labelled
                # UNRATIFIED in the caption and in the image title, because a magnified line that is
                # NOT the ratified span is exactly the kind of plausible artifact that gets mistaken
                # for evidence -- and a signature taken from the wrong line would be a fifth
                # inherited property, arrived at by a nicer picture.
                h.append('<div class="cell">%s<div class="cap"><b>UNRATIFIED &mdash; not yet the '
                         'signed span.</b> The nearest text line inside that window, cut as a real '
                         'native box and magnified to the same scale as the exemplars below. '
                         'UNRATIFIED is the state BEFORE you sign: if you read the text from this '
                         'image, the box below becomes the ratified box in the same act and the '
                         'empty rect is retired. Use it only if you can see it is the right line; '
                         'it carries no claim to be.</div></div>'
                         % img_comp(cim, unratified=True))
        else:
            prov = ('the <b>ratified</b> span box' if s["box_provenance"] == "human-ratified"
                    else 'the span box as the <b>draw pool drew it</b> &mdash; machine-drawn, never '
                         'ratified by anyone, so judge the letter and not the rect')
            h.append('<div class="cell">%s<div class="cap">%s at NATIVE size, '
                     'cut as the runner cuts it (A2, pad %dpx) &mdash; exactly what a reader was '
                     'shown. It holds <b>%d text line(s)</b>: the neighbours come with the box, and '
                     'they are why an arm that transcribes the whole crop returns more than the '
                     'signature and is scored <code>contains</code>.</div></div>'
                     % (img_ctx(a2), prov, D.PAD, n_lines(a2)))
            h.append('<div class="cell">%s<div class="cap"><b>the line, magnified.</b> Cropped to the '
                     'text line the box sits on (a horizontal slice &mdash; no letter is cut) and '
                     'scaled so the line is %dpx tall. Every comparison image below is at this same '
                     'scale.</div></div>' % (img_comp(a2), TARGET_BAND))
        if a1 and ink_bbox(a1):
            h.append('<div class="cell">%s<div class="cap">the whole note (A1) at native size, for '
                     'context and word order.</div></div>' % img_ctx(a1))
        h.append("</div>")
        if rr:
            h.append('<div class="note"><b>Box re-ratified by %s on %s.</b> The original rect was '
                     '<code>%s</code> and is RETIRED by this record rather than kept beside it: '
                     'signing the text from the magnification ratified the box in the same act. '
                     'Signed text <span class="heb" dir="auto">%s</span>%s. New box, native: '
                     '<code>%s</code>.</div>'
                     % (rr["signer"], rr["date"], rr["old_box_state"], rr["text"],
                        (" &middot; points <code>%s</code>" % rr["points"]) if rr.get("points")
                        else "", rr["new_box"]))
        elif blank:
            h.append('<div class="warnbox">This span cannot be signed from its ratified box. If you '
                     'read the text from the magnified line above, paste this line into '
                     '<code>hebrew_box_reratify.jsonl</code> with the text and your name filled in '
                     '&mdash; that one record ratifies the box and retires the empty rect together. '
                     'It is refused on load until the text is present, so an unfilled paste fails '
                     'loud.</div>')
            if cand:
                h.append('<pre class="paste">%s</pre>'
                         % paste_rerat(c["span_id"], pg, cand, "blank-no-ink"))

        # THE LINE, AND WHERE ITS BASELINE FALLS. Only for a card whose candidates differ above or
        # below the line. The eligible set is DERIVED from the card's own candidates against
        # VERTICAL, which is how p254:n1 (final nun vs nun) came to have a strip although ruling 4's
        # spec names only p628:n2 -- a hand-picked list would have missed it.
        _vc = sorted({x for _a in card_asks(c) for x in _a["candidates"]} & set(VERTICAL))
        if _vc:
            h.append('<div class="lbl">the line, and where its baseline falls</div>')
            h.append('<div class="mut">This card has a strip because <b>%s</b> %s above or below '
                     'the line, so the question is a vertical one &mdash; and the 2026-10-25 audit '
                     'said of p628:n2, in these words, that <i>the crop is tight and the descender '
                     'cannot be judged</i>.</div>'
                     % (", ".join(_vc), "differ" if len(_vc) > 1 else "differs"))
            _sp = line_strip(pg, s["span_box"], bands)
            if _sp.get("why"):
                h.append('<div class="warnbox"><b>NO STRIP, and no guide:</b> %s. Nothing is drawn, '
                         'rather than drawn from a line this console cannot establish.</div>'
                         % esc(_sp["why"]))
            else:
                _si = strip_image(_sp)
                _d = _si["detail"]
                _mk = ('The <span style="color:%s">solid line is the derived baseline</span>, the '
                       '<span style="color:%s">dotted one is the top of the dense zone</span> '
                       '(which is not a letter-class boundary), and the '
                       '<span style="color:%s">vertical ticks are the span box\'s own edges</span>. '
                       'Every mark is painted on <b>paper pixels only</b>: no ink is hidden '
                       'anywhere, which is why the baseline BREAKS where a glyph crosses it. That '
                       'break is the signal.'
                       % tuple('#%02x%02x%02x' % g
                               for g in (GUIDE_BASE, GUIDE_TOP, GUIDE_SPAN))
                       ) if _si["baseline"] is not None else 'No guide is drawn on it.'
                h.append('<div class="row"><div class="cell">%s<div class="cap">The span\'s own '
                         'line of type, the full width of its <code>%s</code> band, cut to the '
                         '<b>midpoint of the interline gap</b> on each side &mdash; the ascender '
                         'and descender rows are the LOW-ink rows, so a strip cut at the line\'s '
                         'own bounds throws away the evidence this question needs. The window is '
                         'the span plus %d line-heights either side (%dpx here), so it scales with '
                         'the fount, at NEAREST x%d. <b>This is not the scale of the comparison '
                         'images above:</b> those take the line height from the span crop\'s own '
                         'peak, which differs from the band\'s own run in both directions. %s'
                         '</div></div></div>'
                         % (img_strip(_si["img"], _si["f"]), esc(str(_sp["col"])),
                            STRIP_WIN_LINES, STRIP_WIN_LINES * _sp["run_h"], _si["f"], _mk))
                if _si["baseline"] is None:
                    h.append('<div class="warnbox"><b>NO BASELINE IS DRAWN.</b> %s. The rule is '
                             'Chris\'s, 2026-10-04: the midpoint of the two modes, with a minimum '
                             'separation, and <b>abstain when there is no second mode</b> &mdash; '
                             'never the first gap. It abstained here, so the strip carries no line '
                             'rather than one it cannot justify.</div>' % esc(_d["why"]))
                else:
                    h.append('<div class="feat"><b>How that line was derived, in numbers.</b> The '
                             'row-ink profile of this strip, binned on 1/16 of its own peak (peak '
                             '%d ink pixels in a row). Modes at bins %s; the two most populated are '
                             '<b>%d</b> (the paper floor) and <b>%d</b> (the body of the type), '
                             '<b>%d bins apart</b> where the rule requires %d. The threshold is '
                             'their midpoint, %.0f ink pixels per row; the baseline is the LOWEST '
                             'row at or above it (strip row %d of %d, row %d of the band) and the '
                             'dense-zone top is the highest (strip row %d). The threshold rule '
                             'is Chris&rsquo;s, 2026-10-04: <i>the midpoint of the two modes</i> '
                             'with a minimum separation, abstaining when there is no second mode, '
                             'never the first gap &mdash; and it does abstain, printing why, when '
                             'a strip gives it nothing to work with. <b>It is a derived '
                             'guide and you may refuse it.</b> It is taken from this line\'s '
                             'Latin, which is plentiful and legible, so that the glyph in question '
                             'is judged against something other than itself.</div>'
                             % (_d["peak"], ", ".join(str(x) for x in _d["modes"]),
                                _d["two"][0], _d["two"][1], _d["sep"], STRIP_MIN_SEP, _d["thr"],
                                _si["baseline"], _sp["strip"].height,
                                _sp["top"] + _si["baseline"], _si["dense_top"]))

        if c["kind"] == "letter":
            # Chris's method on p423:n3, 2026-09-27, promoted to a standing instruction because it
            # beats the exemplar machinery it sits above: a second impression of the same sort on
            # the SAME LINE holds fount, wear, inking and scan geometry constant, which no
            # cross-page exemplar can. Look here first.
            h.append('<div class="feat"><b>Look for the letter twice on the same line first.</b> '
                     'If either candidate appears elsewhere in this span or its neighbours, that '
                     'second impression is the best exemplar available anywhere: same sort, same '
                     'inking, same wear, same scan. p423:n3 was settled that way in one look &mdash; '
                     'the third letter of word 1 is the same type as the third letter of word 2. '
                     'The exemplars below are for when the line does not give you one.</div>')
            # One panel per (ask, candidate). A card with two disputed positions gets two sets of
            # panels, each headed with the position it answers, so neither question can be read as
            # evidence about the other.
            panels, _seenask = [], []
            for _a in card_asks(c):
                for _cand in _a["candidates"]:
                    _hdr = ""
                    if id(_a) not in _seenask:
                        _seenask.append(id(_a))
                        _gl = ", ".join(str(p) for p in ask_positions(_a))
                        _hdr = ('<div class="q">Glyph %s: %s</div>'
                                % (_gl, " vs ".join(_a["candidates"])))
                    panels.append((_hdr, _cand,
                                   tuple(x for x in _a["candidates"] if x != _cand)))
            for _hdr, cand, partner in panels:
                if _hdr:
                    h.append(_hdr)
                sg = sig_exemplars(cand)
                ex = exemplars(cand, partner, exclude=(c["span_id"],))
                h.append('<div class="lbl">%s &mdash; %s &mdash; %d exemplar(s): %d signed from the '
                         'volume, %d from signed spans</div>'
                         % (cand, LETTER[cand], len(sg) + len(ex), len(sg), len(ex)))
                # NO_FEATURE, not "": an empty box reads as "no distinguishing feature", which
                # is a claim about the letterforms. The truth is that nobody has stated one.
                h.append('<div class="feat">%s</div>' % (FEATURES.get(cand) or NO_FEATURE))
                if len(sg) + len(ex) < 3:
                    h.append('<div class="warnbox">Only %d exemplar(s) of %s are available. The '
                             'signed spans give %d, and that is a measured corpus limit, not a bug: '
                             'the span rule excludes any word that also contains %s, and no span in '
                             'the set contains both letters, so the ideal exemplar &mdash; one '
                             'impression showing both candidates side by side &mdash; cannot be '
                             'built from those 21 signatures at all. The route past it is open: '
                             'point at any word on any page, name the letter and its index, and '
                             'that record has the same authority as a signature. Use '
                             '<code>hebrew_point_and_name.html</code>.</div>'
                             % (len(sg) + len(ex), cand, len(ex), partner_prose(partner)))
                h.append('<div class="row wrap">')
                for r in sg:
                    # A signed volume exemplar carries its own provenance, and it is shown: a record
                    # whose page, box, index and signer are not on the page beside the picture is a
                    # screenshot with extra steps.
                    # LABELLED by kind, and by whether it is the only one (Chris, 2026-11-15).
                    # A context tile is a box the same hand drew around a neighbouring glyph of the
                    # same word; it counts, and it is weaker, and an unlabelled picture would read
                    # as the same evidence as a pointed one. "single exemplar" is printed where this
                    # is all there is, so the card states what it rests on rather than showing one
                    # specimen and implying a corpus.
                    _kind = ("pointed &mdash; the letter the signer named"
                             if r.get("kind") != "context" else
                             "from context &mdash; a box the signer drew around another glyph of "
                             "the same word, in the same sitting; admitted because this word holds "
                             "no lookalike of it")
                    _only = ('<br><b>single exemplar:</b> this is the only signed impression of %s '
                             'in the corpus, so the comparison rests on one specimen.' % r["letter"]
                             ) if r.get("single_instance") else ""
                    h.append('<div class="cell">%s<div class="cap"><b>signed exemplar</b> '
                             '(%s)<br><span class="heb" dir="auto">%s</span><br>%s<br>'
                             '<span class="prov">file p%s &middot; printed p%s &middot; box %s '
                             '&middot; %s, %s</span>%s%s</div></div>'
                             % (img_comp(r["_crop"]), _kind, r["word"],
                                where(r["word"], [(1, int(r["letter_index_from_right"]))]),
                                r["file_page"], r["file_page"] - 88, r["box"], r["signer"],
                                r["date"],
                                ("<br>" + r["note"]) if r.get("note") else "", _only))
                for sid, es, p, occ in ex:
                    # Same derivation as the card frame. p895:n0 reaches this loop as a pe exemplar
                    # and its claim says the shown glyph is a DIFFERENT letter and unaffected; that
                    # sentence is what licenses the exemplar, so it is printed in either state.
                    _es, _ec = resign_state(sid, es.get("truth_basis"))
                    pend = ""
                    if _es == "pending":
                        pend = "<br><b>note:</b> %s" % _ec
                    elif _es == "landed":
                        pend = ("<br><b>history:</b> %s &mdash; and that batch has landed in this "
                                "row (<code>%s</code>), so the string shown is its output."
                                % (_ec, esc(es.get("truth_basis") or "")))
                    h.append('<div class="cell">%s<div class="cap"><code>%s</code> <span class="heb"'
                             ' dir="auto">%s</span><br>%s%s</div></div>'
                             % (img_comp(Image.open(p)), sid, es["truth"],
                                where(es["truth"], occ), pend))
                h.append("</div>")

        elif c["kind"] == "pointing":
            full = D.build_set(include_sealed=True)
            unp = [x for x in full if x["truth"] and x["truth"] != D.NOT_HEBREW
                   and not has_nikud(x["truth"])
                   and not (x["unscorable"] and "crop-fault" in str(x["unscorable"]))]
            pt = [x for x in full if x["truth"] and has_nikud(x["truth"])
                  and x["span_id"] != c["span_id"]]
            h.append('<div class="lbl">unpointed exemplars &mdash; what this fount normally '
                     'prints</div>')
            h.append('<div class="feat">The verdict is a shape question and nothing more: <b>do you '
                     'see dots and dashes under the letters, yes or no.</b> Whether the specific '
                     'points are the right ones is a different question and is not asked here. '
                     'There is no pointed exemplar anywhere in this corpus to compare against, so '
                     'the answer rests on the shape you see. p200:n2 was signed pointed and ruled '
                     'unpointed, so a pointed-looking signature is not evidence.</div>')
            h.append('<div class="note"><b>Record shape (Chris, 2026-09-27).</b> If the print is '
                     'pointed: sign the consonants <code>verified</code> and the points '
                     '<code>unverified</code> &mdash; neither invented nor dropped. If it is '
                     'unpointed: consonants only, and the correction is POINTS REMOVED, derived by '
                     'stripping the nikud from the signed string rather than retyping it. '
                     '<b>Ruled unpointed on 2026-09-27</b>, so the second branch applies: the '
                     'consonants stand as <span class="heb" dir="auto">%s</span> and the points go. '
                     'That string is shown as the RULE\'s output, not as a new signature &mdash; '
                     'the consonantal text and the box are still open, because the pointing verdict '
                     'was read from the whole page and does not carry them.</div>'
                     % strip_nikud(s["truth"]))
            h.append('<div class="row">')
            for x in unp[:4]:
                p = D.CROPDIR / (x["span_id"].replace(":", "_") + "_A2_spanbox.png")
                if p.exists() and ink_bbox(Image.open(p)):
                    h.append('<div class="cell">%s<div class="cap"><code>%s</code> <span class="heb"'
                             ' dir="auto">%s</span></div></div>'
                             % (img_comp(Image.open(p)), x["span_id"], x["truth"]))
            h.append("</div>")
            h.append('<div class="note">Pointed exemplars available in the signed set: %d. %s</div>'
                     % (len(pt), "None -- there is nothing in this corpus to compare against, so a "
                                 "pointed verdict here would rest on the signature alone."
                        if not pt else ""))

        elif c["kind"] == "coverage" and not rr:
            h.append('<div class="lbl">candidate coverage boxes &mdash; machine proposals</div>')
            h.append('<div class="feat">The signed text is <span class="heb" dir="auto">%s</span> '
                     'and the ratified box holds only part of it. Each box below extends the box '
                     'rightwards by one more word-run on the same text line &mdash; in Hebrew the '
                     'missing words are to the RIGHT. <b>These are proposals, not findings.</b> The '
                     'machine can find the line and the inked runs on it; it cannot say which runs '
                     'are Hebrew, because the Latin gloss continues along the same line and the '
                     'inter-word gaps run 13&ndash;25px throughout with no break between the two '
                     'scripts (measured on this span, not assumed). Ratify the one whose crop holds '
                     'exactly the signed text and nothing else.</div>' % s["truth"])
            h.append('<div class="row wrap">')
            cands = coverage_candidates(pg, (r2 or r1)[0]["box"])
            for cd in cands:
                ci = cut_native(pg, cd["box"])[0]
                if ci is None:
                    continue
                h.append('<div class="cell">%s<div class="cap">+%d word-run(s) to the right<br>'
                         '<span class="prov">native box %s</span></div></div>'
                         % (img_comp(ci), cd["n_words"], cd["box"]))
            h.append("</div>")
            for cd in cands:
                h.append('<pre class="paste">%s</pre>'
                         % paste_rerat(c["span_id"], pg, cd["box"], "clipped-partial-text"))

        h.append('<div class="note">%s</div></div>' % c["verdict"])

    h.append('<div class="note" style="border:0">Signing: record the verdict, the feature you saw, '
             'and the confidence. A verdict of "cannot tell from these pixels" is a real outcome '
             'and is recorded as <code>disputed</code> with both candidates and their witnesses '
             '&mdash; scoring then holds the span unscorable rather than forcing a truth. A forced '
             'verdict would be a fifth inherited property.</div></div>')
    # `out` used to be accepted, defaulted, and then IGNORED: the write went to OUTHTML and
    # OUTHTML came back, so a caller rendering into a scratch directory silently overwrote the
    # shipped page and was told its own path had been written. Found by doing exactly that.
    out.write_text("\n".join(h), encoding="utf-8")
    return out


def selftest():
    import audit_overlay_20261025 as _AUD
    n = [0]
    f = [0]

    def ck(name, cond, extra=""):
        n[0] += 1
        ok = bool(cond)
        if not ok:
            f[0] += 1
        print("  %s  %s%s" % ("ok  " if ok else "FAIL", name,
                              "" if ok else "   " + str(extra)))

    print("(1) counting, not recognising")
    ck("mem is glyph 3 from the right in the p217 signature",
       positions("הימלא", LETTER["mem"]) == [(1, 3)],
       positions("הימלא", LETTER["mem"]))
    ck("word 1 is the RIGHTMOST word (first in the logical string)",
       positions("ביעקב בישראל",
                 LETTER["ayin"]) == [(1, 3)])
    ck("nikud never shifts a glyph position",
       positions("שְׁאָר", LETTER["alef"]) == [(1, 2)],
       positions("שְׁאָר", LETTER["alef"]))

    print("")
    print("(2) the exemplar rule cannot beg the question")
    for a, b in (("mem", "pe"), ("pe", "mem"), ("bet", "gimel"), ("gimel", "bet")):
        ex = exemplars(a, b)
        bad = [sid for sid, s, _p, _o in ex if LETTER[b] in strip_nikud(s["truth"])]
        ck("no %s exemplar contains a %s" % (a, b), not bad, bad)
        ck("every %s exemplar really contains a %s" % (a, a),
           all(LETTER[a] in strip_nikud(s["truth"]) for _x, s, _p, _o in ex))
        ck("no %s exemplar is a faulted crop" % a,
           all(not (s["unscorable"] and "crop-fault" in str(s["unscorable"]))
               for _x, s, _p, _o in ex))
        ck("no %s exemplar offers a DISPUTED glyph" % a,
           all(not (set(o) & set(DISPUTED.get(sid, []))) for sid, _s, _p, o in ex),
           [(sid, o) for sid, _s, _p, o in ex if set(o) & set(DISPUTED.get(sid, []))])

    print("")
    print("(2b) the circular exemplars rule 2b removes -- DERIVED over every pair, then named")
    # This guard was demonstrated on p217:n2 as a MEM exemplar, and that check went red when the
    # batch landed Chris's 2026-09-27 verdict: the truth row is now `היפלא`,
    # which holds NO mem at all and a pe at the disputed position. I recorded that as "the case
    # evaporated, so pin a synthetic one". MEASURED, THAT WAS WRONG. The witness did not disappear,
    # it CHANGED LETTERS: the unguarded rule still offers p217:n2 at exactly the disputed glyph, now
    # as a PE exemplar, and p895:n0 is a second live witness on the ayin/tsadi pair. No synthetic
    # case is needed, and a hand-named letter is what went stale -- so the witnesses are DERIVED
    # from DISPUTED against every pair, and the one I expect is then named so that its silent
    # disappearance is a failure rather than a shorter list.
    _pairs = (("mem", "pe"), ("pe", "mem"), ("bet", "gimel"), ("gimel", "bet"),
              ("ayin", "tsadi"), ("tsadi", "ayin"))
    _wit = []
    for _a, _b in _pairs:
        _un = [x[0] for x in _unguarded_exemplars(_a, _b)]
        _gu = [x[0] for x in exemplars(_a, _b)]
        _wit += [(sid, _a, _b) for sid in _un if sid in DISPUTED and sid not in _gu]
    ck("rule 2b has at least one LIVE witness, derived over every pair", len(_wit) >= 1, _wit)
    # BOTH expected witnesses are named, not just one. A red here does not mean a bug: it means a
    # dispute was ruled and its batch landed, which is exactly the event that taught me the letter
    # had moved rather than the case vanishing. Pinning the COUNT instead would go red on the same
    # legitimate event while saying less about what changed.
    for _sid, _a, _b in (("p217:n2", "pe", "mem"), ("p895:n0", "tsadi", "ayin")):
        ck("the witness I expect is still there: %s as a %s exemplar" % (_sid, _a.upper()),
           (_sid, _a, _b) in _wit, _wit)
    # A span leaves the list only when EVERY impression of the letter in it is disputed. Without
    # this, rule 2b could be discarding a clean second impression -- and a clean second impression
    # on the same line is the best exemplar there is, which is the method Chris ruled p217:n2 with.
    # p423:n3 is the standing proof in the other direction: its word-2 gimel is disputed, its word-1
    # gimel is not, and the span correctly STAYS a gimel exemplar pointing at the undisputed one.
    _rows = {x["span_id"]: x for x in D.build_set(include_sealed=True)}
    for _sid, _a, _b in _wit:
        _occ = positions(_rows[_sid]["truth"], LETTER[_a])
        ck("%s loses its %s only because EVERY impression of it is disputed" % (_sid, _a),
           bool(_occ) and all(x in DISPUTED.get(_sid, []) for x in _occ),
           (_occ, DISPUTED.get(_sid)))
    ck("p423:n3 KEEPS its undisputed word-1 gimel while its word-2 gimel is disputed",
       "p423:n3" in [x[0] for x in exemplars("gimel", "bet")]
       and [x for x in exemplars("gimel", "bet") if x[0] == "p423:n3"][0][3] == [(1, 3)],
       [x[3] for x in exemplars("gimel", "bet") if x[0] == "p423:n3"])
    # The own-card exclusion is a DIFFERENT clause of rule 2b and gets its own check. Note what it
    # can and cannot witness: `exclude` removes the span by NAME, so this pair would stay green with
    # the disputed-glyph half of the rule deleted. That is why the witnesses above pass no exclude.
    for cand, partner in (("mem", "pe"), ("pe", "mem")):
        ck("own-card clause: p217:n2 is not a %s exemplar on its own card "
           "(by name -- blind to the disputed-glyph clause)" % cand,
           "p217:n2" not in [sid for sid, _s, _p, _o in
                             exemplars(cand, partner, exclude=("p217:n2",))])
    # The floor of three is a target the CORPUS decides, not an invariant this code can hold: mem
    # reaches 3, pe reaches 2, gimel reaches 1, and no span contains both letters of either pair.
    # Asserting ">=3 each way" would only encode a wish and go red on a fact. What IS an invariant is
    # that a thin comparison is never shown without saying it is thin -- checked below against the
    # rendered page, which is where the signer would be misled.
    nm = len(exemplars("mem", "pe", exclude=("p217:n2",)))
    npe = len(exemplars("pe", "mem", exclude=("p217:n2",)))
    ck("mem reaches the floor of three", nm >= 3, nm)
    ck("pe is still short (corpus limit, pinned so a later fix is noticed)", npe < 3, npe)
    # gimel has ONE usable exemplar and pe has two. The invariant is not "there are always three"
    # -- the corpus decides that -- it is that a thin comparison is never shown without saying so.
    ng = len(exemplars("gimel", "bet", exclude=("p423:n3",)))
    ck("gimel is still short (corpus limit, pinned so a later fix is noticed)", ng < 3, ng)
    if OUTHTML.exists():
        t0 = re.sub(r"base64,[A-Za-z0-9+/=]+", "", OUTHTML.read_text(encoding="utf-8"))
        for cand in ("pe", "gimel"):
            # thin is now counted over BOTH sources: signed spans plus volume signatures. The warnbox
            # wording is the probe, so it is asserted to exist rather than assumed -- a probe string
            # that no longer matches the page is a test that passes on nothing.
            thin = (len(exemplars(cand, {"pe": "mem", "gimel": "bet"}[cand]))
                    + len(sig_exemplars(cand))) < 3
            said = ("exemplar(s) of %s are available" % cand) in t0
            ck("a thin %s comparison is never shown silently" % cand, said or not thin,
               (thin, said))
        # DERIVED, and RED on the page this replaced: the old form asked only that p895's claim
        # text appear somewhere on the page, which it did -- beside a string the batch had already
        # corrected. What has to hold is that the LABEL matches the state of the row's own basis.
        _cs0 = card_spans()[0]
        _pend0 = [x for x in PENDING_RESIGN
                  if x in _cs0 and resign_state(x, _cs0[x].get("truth_basis"))[0] == "pending"]
        ck("the SUPERSEDED frame appears only while some row's batch has not landed",
           ("is SUPERSEDED" in t0) == bool(_pend0), (_pend0, "is SUPERSEDED" in t0))
        for _sid in [c_["span_id"] for c_ in CARDS if c_["span_id"] in PENDING_RESIGN]:
            _st0, _cl0 = resign_state(_sid, _cs0[_sid].get("truth_basis"))
            ck("%s's batch claim is printed, framed as %s" % (_sid, _st0), _cl0[:40] in t0, _st0)
        _s895, _c895 = resign_state("p895:n0", _cs0["p895:n0"].get("truth_basis"))
        ck("p895:n0 carries its claim wherever it is shown",
           ("p895" not in t0) or (_c895[:40] in t0), _s895)

    print("")
    print("(2c) locators name the word, not just its number")
    ck("a dash-joined signature does not mislabel the word",
       where("\u05d1\u05e8\u05d0 - \u05dc\u05e2\u05e9\u05d5\u05ea", [(1, 1)])
       == "word 1 (\u05d1\u05e8\u05d0), glyph 1 from the right",
       where("\u05d1\u05e8\u05d0 - \u05dc\u05e2\u05e9\u05d5\u05ea", [(1, 1)]))

    print("")
    print("(3) matched scale means matched LINE BAND, and holds for wide images too")
    # The old version of this check sampled three narrow single-word exemplars and passed while the
    # width cap was silently rescaling every wide image. It now includes the widest crop in the set.
    wide = D.CROPDIR / "p200_n2_A2_spanbox.png"
    srcs = [p for _x, _s, p, _o in exemplars("mem", "pe")] + [wide]
    bands, widths, scales = [], [], []
    for q in srcs:
        im = Image.open(q)
        m, sc, bh = comparison(im)   # not `f`: that is the failure counter in this scope
        b = line_band(m)
        bands.append(b[1] - b[0])
        widths.append(m.width)
        scales.append(sc)
    print("      band after scaling: %s   widths: %s   scales: %s" % (bands, widths, scales))
    ck("every comparison image has the same line-band height within 3px",
       max(bands) - min(bands) <= 3, bands)
    ck("the widest crop is NOT rescaled to fit (no silent width cap)",
       max(widths) > 1500, max(widths))
    ck("no comparison image is absurdly wide (would mean a bad band)", max(widths) < 4000,
       max(widths))
    ck("native line bands really do cluster (29-38px measured)",
       all(29 <= line_band(Image.open(q))[1] - line_band(Image.open(q))[0] <= 40
           for q in srcs if line_band(Image.open(q))),
       [(str(q)[-24:], line_band(Image.open(q))) for q in srcs])

    print("")
    print("(3b) a context image is never shrunk below native")
    # `card_spans()`, not `build_set`: seven of the twelve cards are frozen-set spans that
    # build_set does not reach, and indexing it by their span_id raised KeyError and ABORTED the
    # whole suite -- zero assertions printed, exit 1, no FAIL line to read. A check must iterate the
    # population the renderer iterates, or it is a check about a different console.
    _cs3b = card_spans()[0]
    for c in CARDS:
        s_ = _cs3b[c["span_id"]]
        if not s_["span_box"]:
            continue
        a2_, r2_ = cut(s_["page"], s_["span_box"], D.PAD, s_["column_bands"])
        if a2_ is None:
            continue
        if not ink_bbox(a2_):
            w0 = find_ink(s_["page"], r2_)[0]
            g, _sc = context(w0)
            ck("%s recovery window stays at native size or larger" % c["span_id"],
               g.width >= w0.width and g.height >= w0.height,
               (w0.size, g.size))
        else:
            g, _sc = context(a2_)
            ck("%s A2 context stays at native size" % c["span_id"], g.size == a2_.size)

    print("")
    print("(4) the two rejected mechanisms stay rejected -- re-measured, not recalled")
    # CORRECTION, found by this test going red: the docstring claimed p217:n2 yields "3 ink runs for
    # 5 letters". At a raw threshold it yields FIVE, which matches the letter count. The 3 came from a
    # column probe that merged runs separated by less than 3px, and I carried that number forward as
    # though it were the raw geometry of that span. The number was real; the sentence I hung on it was
    # not, and on this one span segmentation would in fact have worked.
    #
    # The reason for showing no pointer does not depend on p217, so it survives: segmentation has to
    # be right on EVERY span it is offered on, and the rate below is what it actually achieves. A
    # mechanism that works on some spans and silently mislocates on the rest is worse on a signing
    # surface than no mechanism, because the signer cannot tell which case they are looking at.
    tot = hit = 0
    detail = []
    for x in D.build_set(include_sealed=True):
        if not x["truth"] or x["truth"] == D.NOT_HEBREW:
            continue
        q = D.CROPDIR / (x["span_id"].replace(":", "_") + "_A2_spanbox.png")
        if not q.exists():
            continue
        im = Image.open(q).convert("L")
        if not ink_bbox(im):
            continue
        px = im.point(lambda v: 255 if v < INK else 0).load()
        W, H = im.size
        col = [any(px[xx, y] for y in range(H)) for xx in range(W)]
        runs = sum(1 for xx in range(1, W) if col[xx] and not col[xx - 1]) + (1 if col[0] else 0)
        want = len(strip_nikud(x["truth"]).replace(" ", "").replace("-", ""))
        tot += 1
        if runs == want:
            hit += 1
        else:
            detail.append("%s %d/%d" % (x["span_id"], runs, want))
    print("      column projection accounts for every letter on %d of %d spans" % (hit, tot))
    print("      misses: %s" % ", ".join(detail))
    ck("per-letter segmentation is a MINORITY outcome, so no pointer is drawn from it",
       hit * 2 < tot, "%d/%d" % (hit, tot))
    if OUTHTML.exists():
        # Scan the TEXT, not the pixels. The first run of this check went red on "grok" because the
        # token occurred inside a base64 image payload -- and the twelve arm names that passed did so
        # by luck, not by absence. A test that can be satisfied by chance in a 3MB blob is not a test.
        t = re.sub(r"base64,[A-Za-z0-9+/=]+", "base64,<payload>",
                   OUTHTML.read_text(encoding="utf-8")).lower()
        ck("the scan actually strips image payloads", "<payload>" in t and len(t) < 200000, len(t))
        ck("the page states the two image classes and what each is for",
           "comparison" in t and "context" in t and "same letterform scale" in t)
        # One magnified image on this page may not be the ratified span. It must be labelled every
        # time it appears, in the caption and in the image title, or it becomes evidence by
        # resemblance. Section (7) checks the count against the spans that are actually unsigned.
        _mark = "unratified, not the signed span -- "
        _unsigned = [c_["span_id"] for c_ in CARDS
                     if c_["span_id"] not in rerat_load()[0] and _blank_span(spans_of(c_["span_id"]))]
        ck("exactly one titled UNRATIFIED image per unsigned blank span",
           t.count(_mark) == len(_unsigned), (t.count(_mark), _unsigned))
        ck("an UNRATIFIED image always has the label in its caption too",
           t.count("unratified") >= 2 * len(_unsigned), (t.count("unratified"), _unsigned))
        ck("no valley/bracket pointer reaches the output", "valley" not in t)

        print("")
        print("(5) verdict-only: no model reading reaches a signing surface")
        # `opus`, `gemma` and `astra` were missing, and they are the arms THIS lane's records
        # actually name -- so five card bases quoted the arm by name and the probe saw none of them.
        # A probe that omits the model in use passes on nothing.
        #
        # THIS LIST IS ARM NAMES ONLY. `abstain` was here too, and on 2026-10-25 it fired on a
        # correct page: the threshold rule of the baseline strip abstains, in Chris's own words, and
        # the card says so. A model's abstention is still a read and is still forbidden -- it is
        # checked in section (11) against the CARD DATA, which is where a reported read lives and
        # where the rule's prose does not. A name can never be legitimate here; a verb can.
        for arm in ("gpt-", "claude-", "gemini", "qwen", "glm-", "deepseek", "kimi", "grok",
                    "minimax", "mimo", "nemotron", "ling-", "step-",
                    "opus", "gemma", "astra", "sonnet"):
            ck("no arm/read token '%s' in the page text" % arm, arm not in t)

    print("")
    print("(6) the record gate: a bad signature is refused, not shown")
    _b6 = n[0]
    # Every check here is a refusal that has a failure mode behind it. The fixtures are synthesized
    # from a REAL span so the geometry is real, and they are written to a temp file -- a born-test
    # never writes to the evidence store.
    import tempfile, os
    sp = {x["span_id"]: x for x in D.build_set(include_sealed=True)}["p491:n1"]
    _i, _r = cut(sp["page"], sp["span_box"], D.PAD, sp["column_bands"])
    _v, _g, _fo, _wb = find_ink(sp["page"], _r, grow=80)
    bandbox = candidate_band_box(sp["page"], _wb)
    # One box per glyph is now part of the record, so the fixture needs them -- the band split into
    # as many columns as the word has glyphs, RIGHT TO LEFT, since position 1 is the rightmost. They
    # are synthetic columns and not letter segmentation: this module rejected segmenting letters,
    # and the geometry gate asks about order, overlap and line, which columns of a real inked band
    # answer honestly. The signed box is the column at the claimed index, because the gate requires
    # it to be.
    _rev = {v: k for k, v in LETTER.items()}
    _glyphs = strip_nikud(sp["truth"])
    _names = [_rev.get(c) for c in _glyphs]
    ck("the fixture word is one word of known letters, so columns can stand for its glyphs",
       " " not in _glyphs and len(_glyphs) >= 2 and None not in _names, (_glyphs, _names))
    _w = (bandbox[2] - bandbox[0]) / float(max(1, len(_glyphs)))

    def _col(i):
        """The column standing for glyph `i`, counted from the RIGHT edge of the band."""
        x1 = int(round(bandbox[2] - (i - 1) * _w))
        return [int(round(bandbox[2] - i * _w)), bandbox[1], x1, bandbox[3]]

    def _lb(over=None):
        out = []
        for i, nm in enumerate(_names, start=1):
            out.append({"index_from_right": i, "letter": nm,
                        "box": (over or {}).get(i) or _col(i)})
        return out

    okbox = _col(1)
    # A box that really holds two lines of type. Grown UPWARD ONLY, and 200px, neither of which is
    # arbitrary: okbox is the rightmost glyph column at the FOOT of page 491, so downward is blank
    # paper, and 120px upward stops in the leading short of the line above. The old fixture grew
    # 120 both ways, measured one-band [24], and was refused only because a box on page 491 was
    # being compared against a disputed rect on page 423 -- the band gate was never asked. The
    # subject check below counts the bands from the pixels, so the clause cannot pass vacuously
    # again.
    twoline = [okbox[0], okbox[1] - 200, okbox[2], okbox[3]]
    _tim, _tfault = cut_native(sp["page"], twoline)
    ck("the multi-line fixture really does hold more than one text band",
       _tfault is None and _tim is not None and len(text_bands(_tim)) >= 2,
       (_tfault, None if _tim is None else [b[1] - b[0] for b in text_bands(_tim)]))
    base = dict(file_page=sp["page"], box=okbox, coord_space="native", word=sp["truth"],
                letter=_names[0], letter_index_from_right=1, letter_boxes=_lb(),
                signer="TEST", date="2026-09-27")
    ck("the fixture names a real letter at a real index",
       (1, 1) in positions(sp["truth"], LETTER[_names[0]]),
       positions(sp["truth"], LETTER[_names[0]]))
    cases = [("a well-formed signature is accepted", dict(base), True),
             ("a strip-coordinate box is refused", dict(base, coord_space="strip"), False),
             ("an off-by-one letter index is refused",
              dict(base, letter_index_from_right=2), False),
             ("a box off the page is refused",
              dict(base, box=[okbox[0], okbox[1] + 90000, okbox[2], okbox[3] + 90000],
                   letter_boxes=_lb({1: [okbox[0], okbox[1] + 90000,
                                         okbox[2], okbox[3] + 90000]})), False),
             # And it names the refusal it is for. A count of refusals cannot tell this gate
             # firing from any other gate firing, which is how a cross-page rect collision stood in
             # for the band gate from the day this clause was written until 2026-11-15.
             ("a box holding more than one text line is refused",
              dict(base, box=twoline, letter_boxes=_lb({1: twoline})), False,
              "multi-band"),
             ("a record with no glyph boxes at all is refused",
              dict(base, letter_boxes=[]), False),
             ("a glyph box on another line of type is refused",
              dict(base, letter_boxes=_lb({2: [_col(2)[0], _col(2)[1] + 400,
                                               _col(2)[2], _col(2)[3] + 400]})), False),
             ("a signed box that is not the glyph box at the claimed index is refused",
              dict(base, box=[okbox[0] + 3, okbox[1], okbox[2] + 3, okbox[3]]), False),
             ("a signature with no signer is refused", dict(base, signer=""), False),
             ("an unknown letter name is refused", dict(base, letter="aleph"), False)]
    fd, tmp = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    try:
        for case in cases:
            name, rec, want_ok = case[0], case[1], case[2]
            # Optional 4th element: a substring of the refusal this case exists to exercise. Where a
            # case names one, accepted/refused is not enough -- the named gate has to be the one
            # that spoke.
            need = case[3] if len(case) > 3 else None
            io.open(tmp, "w", encoding="utf-8", newline="\n").write(
                json.dumps(rec, ensure_ascii=False) + "\n")
            g_, b_ = sig_load(Path(tmp))
            good = (len(g_) == 1) if want_ok else (len(b_) == 1 and not g_)
            if good and need is not None:
                good = any(need in (x.get("_refused") or "") for x in b_)
            ck(name, good, (len(g_), [x.get("_refused") for x in b_]))
        io.open(tmp, "w", encoding="utf-8", newline="\n").write("{not json\n")
        g_, b_ = sig_load(Path(tmp))
        ck("an unparseable line is refused and reported, not skipped",
           not g_ and len(b_) == 1 and "unparseable" in b_[0]["_refused"])

        # ------------------------------------------------ THE DISPUTED-SPAN GUARD, ON BOTH AXES
        # This guard had no check at all, which is how it ran page-blind from the day it was
        # written until 2026-11-15, when it refused two of Chris's six signatures and said "on
        # this page" about a page it had never consulted. The fixture is DERIVED from
        # `_disputed_native()`, so a span that stops being disputed moves it instead of breaking
        # it, and the record is built from that span's own truth so it reaches the overlap test
        # rather than dying at the word or the index.
        _rev6 = {v: k for k, v in LETTER.items()}
        _cs6 = card_spans()[0]
        _dfix = None
        for _sid, _dpg, _drect in _disputed_native():
            _s6 = _cs6.get(_sid)
            if not _s6:
                continue
            _g6 = strip_nikud(_s6["truth"])
            _n6 = [_rev6.get(ch) for ch in _g6]
            if " " in _g6 or None in _n6 or len(_g6) < 2:
                continue
            _w6 = (_drect[2] - _drect[0]) / float(len(_g6))

            def _c6(i, _r=_drect, _wi=_w6):
                return [int(round(_r[2] - i * _wi)), _r[1],
                        int(round(_r[2] - (i - 1) * _wi)), _r[3]]
            _lb6 = [{"index_from_right": i, "letter": nm, "box": _c6(i)}
                    for i, nm in enumerate(_n6, start=1)]
            _dfix = (_sid, _dpg, dict(file_page=_dpg, box=_c6(1), coord_space="native",
                                      word=_s6["truth"], letter=_n6[0],
                                      letter_index_from_right=1, letter_boxes=_lb6,
                                      signer="TEST", date="2026-09-27"))
            break
        # THE OTHER AXIS IS A LIVE RECORD, not a synthetic box on a clean page. That is what this
        # clause used to be, and `mutate_card_sig.py` case 1 proved it blind: restore the
        # page-blindness and the clause still passes, because the synthetic box lands on blank paper
        # on another page and `sig_load` refuses it with `exemplar crop is no-band` before the
        # overlap test is reached. "Not refused for THIS reason" is then true whatever the overlap
        # test does. A subject that dies at an earlier gate asserts nothing about the gate it names.
        # The records that DO pass every other gate and overlap a disputed rect on another page are
        # the two the page-blind guard actually refused: p503's final nun and p577's tav, each
        # against p895:n0, a footnote band 300 pages away.
        # THE POPULATION MUST NOT COME FROM THE GATE. This clause first drew its subject from
        # `sig_load()[0]`, the admitted set -- and page-blind, these records are precisely the ones
        # the guard refuses, so the population emptied, the clause was skipped, and the mutant
        # walked. It stayed DEAD through that repair for no other reason. The subject is therefore
        # every record that passes every gate OTHER than this one: admitted, or refused WITH a
        # disputed-span reason. p503's final nun is in the first list when the guard is right and in
        # the second when it is page-blind, so it is a subject either way.
        _raw6 = [json.loads(_l) for _l in io.open(SIGS, encoding="utf-8") if _l.strip()]
        _good6, _bad6 = sig_load()

        def _key6(x):
            return (str(x.get("file_page")), x.get("letter"), x.get("word"),
                    str(x.get("letter_index_from_right")))
        _gk6 = set(_key6(g) for g in _good6)
        _dk6 = set(_key6(b) for b in _bad6
                   if "disputed span" in (b.get("_refused") or ""))
        _cross = []
        for _r6 in _raw6:
            _h6 = [(s, p) for s, p, rect in _disputed_native()
                   if p != int(_r6["file_page"])
                   and any(_overlaps(lb["box"], rect) for lb in _r6.get("letter_boxes") or ())]
            if _h6 and _key6(_r6) in (_gk6 | _dk6):
                _cross.append((_r6, _h6))
        ck("a disputed span gives a usable same-page fixture, and a signature that clears every"
           " other gate really does overlap a disputed rect on another page (%d of %d records)"
           % (len(_cross), len(_raw6)),
           _dfix is not None and bool(_cross),
           (None if not _dfix else _dfix[0],
            [(r["file_page"], r["letter"], h) for r, h in _cross]))
        if _dfix:
            _sid6, _pg6, _rec6 = _dfix
            io.open(tmp, "w", encoding="utf-8", newline="\n").write(
                json.dumps(_rec6, ensure_ascii=False) + "\n")
            _g6b, _b6b = sig_load(Path(tmp))
            ck("a box on a disputed span's own page is refused, and the span is named",
               not _g6b and any(("disputed span %s" % _sid6) in (x.get("_refused") or "")
                                for x in _b6b),
               (_pg6, len(_g6b), [x.get("_refused") for x in _b6b]))
        if _cross:
            _r6, _h6 = _cross[0]
            io.open(tmp, "w", encoding="utf-8", newline="\n").write(
                json.dumps(_r6, ensure_ascii=False) + "\n")
            _g6c, _b6c = sig_load(Path(tmp))
            ck("a signature overlapping a disputed span on ANOTHER page is admitted"
               " (file p%s, %s, vs %s)" % (_r6["file_page"], _r6["letter"], _h6[0][0]),
               len(_g6c) == 1 and not [x for x in _b6c
                                       if ("disputed span %s" % _h6[0][0])
                                       in (x.get("_refused") or "")],
               (len(_g6c), [x.get("_refused") for x in _b6c]))
    finally:
        os.unlink(tmp)

    print("")
    print("(6b) the glyph-box geometry gate, by mutation: what the index check can no longer say")
    # Pure numbers, no page: the gate is geometry, and a guard is proved live by breaking it, never
    # by a green run over the one record that satisfies it. Each case names the refusal it is for.
    _G = "\u05d1\u05e9\u05de\u05e2"          # bet shin mem ayin -- 4 glyphs, 1 is the RIGHTMOST
    _GN = ["bet", "shin", "mem", "ayin"]

    def _gb(over=None):
        """Four boxes on one line, marching leftwards as the index rises."""
        out = []
        for i, nm in enumerate(_GN, start=1):
            x1 = 400 - 30 * (i - 1)
            out.append({"index_from_right": i, "letter": nm,
                        "box": (over or {}).get(i) or [x1 - 25, 100, x1, 130]})
        return out

    _good = _gb()
    for name, args, want in (
            ("a well-formed set of glyph boxes passes",
             (_G, "bet", 1, _good[0]["box"], _good), None),
            ("one box short of the word is refused", (_G, "bet", 1, _good[0]["box"], _good[:3]),
             "one box per glyph"),
            ("two boxes claiming one index is refused",
             (_G, "bet", 1, _good[0]["box"],
              [dict(e, index_from_right=2) if e["index_from_right"] == 4 else e for e in _gb()]),
             "both claim index"),
            ("glyphs out of right-to-left order are refused",
             (_G, "bet", 1, _good[0]["box"], _gb({2: [500, 100, 525, 130]})),
             "right to left"),
            ("one box signed twice is refused",
             (_G, "bet", 1, _good[0]["box"], _gb({2: [350, 100, 394, 130]})),
             "overlap"),
            ("a glyph on another line of type is refused",
             (_G, "bet", 1, _good[0]["box"], _gb({3: [315, 200, 340, 230]})),
             "one line of type"),
            ("boxes that spell a different word are refused",
             (_G, "bet", 1, _good[0]["box"],
              [dict(e, letter="vav") if e["index_from_right"] == 3 else e for e in _gb()]),
             "spell"),
            ("a signed box that is not the box at the claimed index is refused",
             (_G, "bet", 1, [1, 2, 30, 40], _good), "is not the glyph box at index"),
            ("a letter named differently from the box at that index is refused",
             (_G, "shin", 1, _good[0]["box"], _good), "signed for shin"),
            ("a zero-width glyph box is refused",
             (_G, "bet", 1, [370, 100, 370, 130], _gb({1: [370, 100, 370, 130]})),
             "not a box"),
            ("a word with a space in it is refused",
             (_G[:2] + " " + _G[2:], "bet", 1, _good[0]["box"], _good), "ONE word"),
    ):
        _f = letter_boxes_fault(*args)
        ck(name, (_f is None) if want is None else (_f is not None and want in _f), _f)
    # A COUNT, not `True`. It read `ck("section 6b ran every one of its checks", True)` -- a
    # count check that asserted nothing, in the two sections where a guard with no check of its own
    # was refusing good signatures. Covers 6 and 6b together, which is where `_b6` is taken.
    # 28 = 3 fixture subjects + 10 record-gate cases + 1 unparseable line + 3 disputed-span
    # clauses + 11 letter-box faults in 6b. Read off the run and written out, because a count
    # recomputed from the loops it counts asserts nothing -- and because this line read `True` for
    # its whole life, in the two sections where a guard that had no check was refusing good work.
    # 29 until the vacuous clean-page clause came out: it could not see a page-blind overlap test.
    ck("sections 6 and 6b ran every one of their checks", n[0] - _b6 == 28, n[0] - _b6)

    print("")
    print("(7) ruling 2: signing from the neighbourhood re-ratifies the box in ONE record")
    rg, rb = rerat_load()
    ck("every re-ratification on file is accepted", not rb,
       [(x.get("span_id"), x.get("_refused")) for x in rb])
    ck("every re-ratified box holds exactly ONE line band",
       all(n_lines(r["_crop"]) == 1 for r in rg.values()),
       [(k, n_lines(v["_crop"])) for k, v in rg.items()])
    ck("a re-ratified box is not the empty rect it replaces",
       all(r["new_box"] != r.get("old_box") for r in rg.values()))
    if OUTHTML.exists():
        t2 = re.sub(r"base64,[A-Za-z0-9+/=]+", "", OUTHTML.read_text(encoding="utf-8")).lower()
        for sid in rg:
            ck("%s is shown as re-ratified, with the old rect retired" % sid,
               "re-ratified" in t2 and "retired by this record" in t2)
        # UNRATIFIED is the PRE-SIGN state only. Once a record exists the label must be gone for
        # that span, or the console is telling the signer their own signature is unratified.
        still = [c_["span_id"] for c_ in CARDS
                 if c_["span_id"] not in rg and _blank_span(spans_of(c_["span_id"]))]
        ck("UNRATIFIED appears exactly for the spans not yet signed (%d)" % len(still),
           (t2.count("unratified") >= 2 * len(still)
            and (t2.count("unratified") == 0) == (not still)),
           (t2.count("unratified"), still))

    print("")
    print("(8) ruling 3: a span box should contain exactly one line band")
    one, tot_, bad_ = one_band_report()
    print("      %d of %d ratified span boxes contain exactly one line band" % (one, tot_))
    print("      loose boxes: %s" % ", ".join(bad_))
    ck("the one-line-band property is measured for every readable crop", tot_ >= 15, tot_)
    ck("the box-quality table covers every span in the set",
       len(box_quality()) == len(D.build_set(include_sealed=True)))
    # This is a DEBT, not an invariant: the boxes are what they are until they are re-drawn. What is
    # asserted is that every box this lane RATIFIES from now on holds one line -- enforced in
    # rerat_load, checked above -- and that the debt is reported rather than discovered later.
    ck("the debt is non-zero and named, so item 3 has something to assert against", bad_)

    print("")
    print("(9) the four rulings reach the page")
    if OUTHTML.exists():
        ck("the p912 card asks a coverage question, not a question about the text",
           "does the ratified box hold the whole signed text" in t2 and "rightmost on the page" not in t2)
        ck("the compositor hypothesis is off the p423 card", "compositor" not in t2)
        ck("the p726 card states the unpointed record shape",
           "points removed" in t2 and "consonants" in t2)
        ck("the pointing verdict is posed as a shape question",
           "dots and dashes under the letters" in t2)
        ck("the repeated-sort method is on every letter card",
           t2.count("look for the letter twice on the same line") >= 2)
        # The old form asked for the lowercase word "superseded" ONCE anywhere on the page, for
        # any card in the table -- and the page's only lowercase occurrence was inside p423:n3's own
        # claim sentence, never the label. It was a probe matching on something else, and it stayed
        # green while all three labels were wrong.
        _cs7 = card_spans()[0]
        # `t2` is LOWERCASED (line ~2121), so every needle here is too -- and the label needle
        # is the whole phrase, because "superseded" alone appears inside p423:n3's claim sentence
        # and that is what the check this replaced was matching.
        _LBL = "string above is superseded"
        for _sid in [c_["span_id"] for c_ in CARDS if c_["span_id"] in PENDING_RESIGN]:
            _st7, _cl7 = resign_state(_sid, _cs7[_sid].get("truth_basis"))
            ck("%s's card frames its batch claim as %s" % (_sid, _st7),
               _cl7[:40].lower() in t2 and ((_LBL in t2) if _st7 == "pending" else True), _st7)
        ck("no landed correction is called superseded anywhere on the page",
           (_LBL not in t2)
           or any(resign_state(x, _cs7[x].get("truth_basis"))[0] == "pending"
                  for x in PENDING_RESIGN if x in _cs7))
        ck("signed exemplars carry provenance when any exist",
           (not sig_exemplars("bet") and not sig_exemplars("gimel"))
           or ("signed exemplar" in t2 and "printed p" in t2))

    # (10): "(8)" collided with "(8) ruling 3" above and printed after "(9)".
    print("(10) the population bridge")
    _b0 = n[0]
    _bspans, _bref, _bov = card_spans()
    _owed = ("p233:n4", "p628:n2", "p910:n3", "p596:n2", "p442:n0", "p798:n0", "p254:n1", "p831:n2")
    _missing = [x for x in _owed if x not in _bspans]
    ck("all eight spans ruling 4 owes a card are reachable", not _missing, _missing)
    ck("every reachable record states its box provenance",
       all(x.get("box_provenance") in ("human-ratified", "draw-pool") for x in _bspans.values()),
       sorted({str(x.get("box_provenance")) for x in _bspans.values()}))

    # THE DEFECT THE BRIDGE EXISTS TO PREVENT. Pass 2 is the insertion pass, so on these two spans the
    # signature is LONGER than the candidate -- a card built from the frozen set's `hebrew` column
    # would count to a glyph that is not the one in dispute. Stated as the property (longer, and the
    # candidate is a prefix-with-a-hole, not equal), never as a pinned pair of strings.
    _fz = json.loads(io.open(str(FROZEN_SET), encoding="utf-8").read())
    _cand = {r["span_id"]: strip_nikud(r["hebrew"]) for r in _fz["rows"]}
    _grew = [x for x in ("p233:n4", "p831:n2")
             if x in _bspans and len(_bspans[x]["truth"]) > len(_cand.get(x, ""))]
    ck("the two insertion-pass signatures are longer than their candidates",
       sorted(_grew) == ["p233:n4", "p831:n2"],
       [(x, _cand.get(x), _bspans[x]["truth"] if x in _bspans else None)
        for x in ("p233:n4", "p831:n2")])
    ck("no card signature is the frozen set's candidate where the two differ",
       all(_bspans[x]["truth"] != _cand[x] for x in _cand
           if x in _bspans and _bspans[x]["box_provenance"] == "draw-pool"
           and len(_bspans[x]["truth"]) != len(_cand[x])))

    # The accept path, re-derived rather than trusted: nothing admitted may carry a verdict outside
    # the set all three shipped derivations render identically.
    _signed = {}
    for _fn, _tg in FROZEN_EXPORTS:
        _p = D.DATA / _fn
        if not _p.exists():
            continue
        for _ln in io.open(str(_p), encoding="utf-8"):
            _ln = _ln.strip()
            if _ln:
                _o = json.loads(_ln)
                if "span_id" in _o and "tiles" in _o:
                    _signed[_o["span_id"]] = _o
    _leak = [sid for sid, x in _bspans.items()
             if x["box_provenance"] == "draw-pool" and sid in _signed
             and any((t.get("verdict") or "") not in AGREED_VERDICTS for t in _signed[sid]["tiles"])]
    ck("no admitted row carries a verdict the derivations render differently", not _leak, _leak)

    # CROSS-LINEAGE WITNESS. `derived_consonants` is computed by the console in JavaScript, so an
    # agreement with the Python port is a witness and not a construction. The liveness count is
    # printed: a check that compares nothing would otherwise pass on nothing.
    _n_wit = _n_bad = 0
    for sid, x in _bspans.items():
        _c = (_signed.get(sid) or {}).get("derived_consonants")
        if x["box_provenance"] == "draw-pool" and _c:
            _n_wit += 1
            if _c != x["truth"]:
                _n_bad += 1
    print("      the console's own JavaScript string exists on %d admitted row(s)" % _n_wit)
    ck("the derivation agrees with the console on every admitted row that carries its string",
       _n_wit > 0 and _n_bad == 0, "%d witness(es), %d mismatch(es)" % (_n_wit, _n_bad))

    ck("the frozen records carry no note box, because no ratified one exists for those pages",
       all(x["note_box"] is None for x in _bspans.values() if x["box_provenance"] == "draw-pool"))

    # The gap clause that over-refused. A gap tile is a word space, so refusing it refused every
    # multi-word span -- the population `words()` and `where()` exist to serve.
    _mw = [sid for sid, x in _bspans.items() if " " in (x["truth"] or "")]
    print("      multi-word signatures admitted: %d" % len(_mw))
    ck("a word space does not get a span refused", len(_mw) > 0, len(_mw))

    if OUTHTML.exists():
        # LIVENESS, stated rather than assumed: until the eight CARDS entries land, no card sits on a
        # drawn box and this branch is checking nothing. The count is printed so a zero is visible.
        _dp = [c for c in CARDS if _bspans.get(c["span_id"], {}).get("box_provenance") == "draw-pool"]
        print("      cards sitting on a draw-pool box: %d" % len(_dp))
        ck("a card on a drawn box never calls it ratified",
           not _dp or "machine-drawn, never " in t2, len(_dp))
    else:
        ck("a card on a drawn box never calls it ratified", True, "no rendered page to scan")

    # 9, not 10: the caption check is one `ck` reached through an if/else, not two. The first run of
    # this line said 10 and went red, which is what the line is for.
    # WHAT THE HTML CHECKS ARE ACTUALLY SCANNING. Nothing in this suite renders; every check that
    # reads `t2` reads a page some earlier run left on disk. When `build()` crashed on a shadowed
    # name it wrote nothing, and all of those checks passed anyway against the previous version's
    # page. Comparing mtimes is derived from the filesystem, not matched against a string this same
    # code emits, so it cannot pass by construction.
    if OUTHTML.exists():
        _fresh = OUTHTML.stat().st_mtime >= Path(__file__).stat().st_mtime
        ck("the page the HTML checks scan was rendered by THIS code, not an earlier one",
           _fresh, "page is older than the module -- re-run `build` before trusting section 7")
    else:
        ck("the page the HTML checks scan was rendered by THIS code, not an earlier one",
           True, "no rendered page on disk, so no HTML check ran")

    # 10, not 9: the staleness guard above is one `ck` reached through an if/else. The first version
    # of this line said 10 when there were 9 and went red, which is what the line is for.
    ck("section 10 ran every one of its checks", n[0] - _b0 == 10, n[0] - _b0)

    print("")
    print("(11) the eight new cards -- what items 3 and 4 claim")
    _c0 = n[0]
    _s9 = card_spans()[0]
    OWED9 = ("p233:n4", "p628:n2", "p910:n3", "p596:n2",
             "p442:n0", "p798:n0", "p254:n1", "p831:n2")

    # THE POS INVARIANT, SCOPED. The glyph the signature holds at a card's `pos` must be one of that
    # ask's candidates ALWAYS -- a card pointing at a letter nobody is disputing is a wrong number
    # and sends a signer to the wrong glyph. It equals candidates[0] only while the card is open: the
    # two DECIDED cards have had their rulings LAND in the truth table, so their signatures now hold
    # the ruled letter, which is candidates[1]. Scoping this is why the check exists at all -- the
    # unscoped form reported those two landings as mismatches.
    for c in CARDS:
        for a in card_asks(c):
            gs = glyphs_at(_s9[c["span_id"]]["truth"], a)
            names = [k for k in a["candidates"]]
            chars = [LETTER[k] for k in names]
            ck("%s glyph %s is one of the candidates it disputes"
               % (c["span_id"], ",".join(str(p) for p in ask_positions(a))),
               all(g in chars for g in gs), (gs, names))
            if not c["status"].startswith("DECIDED"):
                ck("%s still holds its first-named candidate" % c["span_id"],
                   all(g == chars[0] for g in gs), (gs, names[0]))

    ck("every candidate a card names is a letter this file can draw",
       all(k in LETTER for c in CARDS for a in card_asks(c) for k in a["candidates"]),
       sorted({k for c in CARDS for a in card_asks(c) for k in a["candidates"]
               if k not in LETTER}))

    # CROSS-LINEAGE, not by construction: `cut()` un-stacks a frozen span's STRIP coordinates into
    # native page rects, and the scoring-45 contact sheet stored native rects for the same spans from
    # a different run. Agreement on all seven is a witness that the un-stacking is right; nothing in
    # this file produced the number it is compared against. p596:n2 is excluded because it is not in
    # the 45-span population -- its box is human-ratified and never passed through a strip.
    _agree, _seen = [], []
    if C2SHEET.exists():
        _c2 = {r["span_id"]: r for r in json.loads(
            C2SHEET.read_text(encoding="utf-8"))["rows"]}
        for sid in OWED9:
            r = _c2.get(sid)
            if not r or sid not in _s9 or not _s9[sid]["span_box"]:
                continue
            theirs = (((r.get("pos") or {}).get("frame") or {})
                      .get("native_rects_stored"))
            if theirs is None:
                continue
            _seen.append(sid)
            _im, rects = cut(_s9[sid]["page"], _s9[sid]["span_box"], 0,
                             _s9[sid]["column_bands"])
            mine = [[int(v) for v in rr["box"]] for rr in rects]
            _agree.append(mine == [[int(v) for v in rr] for rr in theirs])
        ck("cut() lands on the contact sheet's native rects for every owed frozen span",
           len(_seen) == 7 and all(_agree), (len(_seen), _agree))
    else:
        ck("cut() lands on the contact sheet's native rects for every owed frozen span",
           False, "the scoring-45 contact sheet is missing, so nothing witnesses the un-stacking")

    # The Latin panel's state is asserted PER SPAN, because an ABSENT that goes quietly is the shape
    # of the first contact-sheet build: it took `latin_context` from build_set and came out absent
    # for 44 of 45 without saying so.
    for sid in OWED9:
        _lt, _ls, _lw = latin_gloss(sid)
        want = "absent" if sid == "p596:n2" else "present"
        ck("%s's Latin gloss is %s" % (sid, want), _ls == want, (_ls, (_lw or _lt)[:60]))

    # RULING 4'S FIRST DELIVERABLE NOW EXISTS, AND THIS CHECK IS WHAT SAID SO. It used to assert a
    # measured zero from both sources, with the comment that the day one was pointed and named it
    # would go red and the card's refusal would come off the page. That day was 2026-11-15: Chris
    # pointed a zayin on file p264. The precondition is restated rather than the assertion relaxed.
    # Both sources are still counted separately, because they are different kinds of evidence: a
    # POINTED exemplar is admissible because the signer named an index, while a SPAN exemplar has
    # to pass rule 2, and no span can -- no word in the set holds a zayin without a vav.
    # THE NOTE IS CHECKED AGAINST THE RECORD IT DESCRIBES. It was written with the wrong index --
    # "glyph 2 from the right" of a two-letter word whose zayin is at 1 -- and a card's note is what
    # a human reads instead of the tally, so a misnamed glyph points a signer at the rival's
    # neighbour. Fails in both directions: a wrong note, or a note left behind by a re-signing.
    # EVERY impression, not the one that existed when this was written. The note is filled from
    # the records, so the check reads what the signer reads and the count comes from the data.
    _z = sig_exemplars("zayin", want=10 ** 6)
    _znote = [fill_note(a.get("note", "")) for c in CARDS if c["span_id"] == "p233:n4"
              for a in card_asks(c)]
    ck("p233:n4's note names every signed zayin impression: page, word and index",
       bool(_z) and any(all(("file p%s" % r["file_page"]) in nt
                            and ("glyph %s from the right" % r["letter_index_from_right"]) in nt
                            and _heb_entities(r["word"]) in nt
                            for r in _z)
                        for nt in _znote),
       ([(r["file_page"], r["letter_index_from_right"]) for r in _z],
        [nt[:160] for nt in _znote]))
    # The subject for the clause above. Without it, a supply that went to zero would make the
    # for-all true and the note could say anything.
    ck("the signed zayin supply is non-zero, so the clause above is not a for-all over nothing",
       len(_z) >= 1, len(_z))
    # What is actually invariant here, and the reason the note's span sentence is count-free: no
    # word in the set holds a zayin without a vav, so no SPAN exemplar can be built at any supply.
    ck("no span exemplar of zayin can be built, which is what the note says",
       len(exemplars("zayin", None)) == 0, len(exemplars("zayin", None)))
    # The check above reads the note only if the note exists to be read; this one says the card is
    # still there to have a note. A card whose ask vanished would make it vacuous.
    ck("p233:n4 still asks something, so the note check above has a subject",
       bool(_znote) and all(isinstance(nt, str) for nt in _znote), len(_znote))
    if OUTHTML.exists():
        # THE PAGE'S OWN NUMBER, parsed. The previous version looked for the warnbox sentence
        # "only N exemplar(s) of zayin are available" -- which the page prints only while the
        # supply is under three, so it would have gone red at the third zayin for the opposite
        # reason, when the sentence legitimately disappears. The count line below is printed for
        # every candidate panel at every supply.
        _m = re.search(r"zayin &mdash; . &mdash; (\d+) exemplar\(s\): (\d+) signed from the "
                       r"volume, (\d+) from signed spans", t2)
        ck("the zayin card's face agrees with the measured count",
           bool(_m) and int(_m.group(2)) == len(sig_exemplars("zayin")),
           (None if not _m else _m.group(0), len(sig_exemplars("zayin"))))
        # An unfilled token is visible garbage in a warnbox a human is being asked to act on.
        ck("no unfilled {{SIGNED:...}} token reaches the page",
           not SIGN_TOKEN.search(t2), SIGN_TOKEN.findall(t2)[:3])
    else:
        ck("the zayin card's face agrees with the measured count", True,
           "no rendered page to scan")
        ck("no unfilled {{SIGNED:...}} token reaches the page", True, "no rendered page to scan")

    # Section 8's draw-pool caption check was live-counting ZERO before these cards landed, which it
    # printed. Pinning the number here is what turns that printed zero into something that cannot
    # quietly return.
    _dp9 = [c["span_id"] for c in CARDS
            if _s9.get(c["span_id"], {}).get("box_provenance") == "draw-pool"]
    ck("seven cards now sit on a machine-drawn box, so section 10's caption check is live",
       len(_dp9) == 7, sorted(_dp9))
    ck("p596:n2 is the one owed span with a human-ratified box",
       [x for x in OWED9 if _s9[x]["box_provenance"] == "human-ratified"] == ["p596:n2"],
       [(x, _s9[x]["box_provenance"]) for x in OWED9])

    # NO READING ON THE SIGNING SURFACE, checked over the CARD DATA and not the page text.
    # Section (5) scans the rendered page for arm names; it cannot see a tally, and it cannot see a
    # card at all until the card renders. Both of those let the first draft of these eight through.
    # The phrases below are the shapes the leak actually took, plus the generic ones.
    _fields = []
    for c in CARDS:
        _fields.append((c["span_id"], "status", c.get("status") or ""))
        _fields.append((c["span_id"], "question", c.get("question") or ""))
        _fields.append((c["span_id"], "verdict", str(c.get("verdict") or "")))
        for a in card_asks(c):
            _fields.append((c["span_id"], "basis", a.get("basis") or ""))
            # FILLED: the no-reading scan has to see what a human sees, and a derived sentence
            # is as capable of naming an arm as a typed one.
            _fields.append((c["span_id"], "note", fill_note(a.get("note") or "")))
    _ARMS = ("opus", "qwen", "gemma", "astra", "sonnet", "gpt-", "claude-", "gemini", "deepseek")
    _armhit = [(sid, k, t_) for sid, k, v in _fields for t_ in _ARMS if t_ in v.lower()]
    ck("no card names the arm that produced a reading (%d field(s) scanned)" % len(_fields),
       not _armhit and len(_fields) > 40, _armhit[:4])
    # A TALLY is the same leak in the form the token list is blind to.
    _TALLY = ("reads put", "reads return", "read it", "arms agree", "all four reads",
              "three reads", "two of the four", "both qwen", "returns the signature",
              "reads agree", "arms agreeing",
              # An abstention reported as a read is a read. These phrasings came out of section (5)
              # when the baseline strip's own rule needed the bare word `abstain` back.
              # `no read` was tried and REMOVED: it matched "no signature, no reads, no Latin"
              # on p596:n2 -- a card ASSERTING that no arm read the span, which is the
              # opposite of reporting one. A needle for "a read happened" must not match a
              # denial that any did.
              "abstained", "abstention", "abstains", "arm declined")
    _tally = [(sid, k, t_) for sid, k, v in _fields for t_ in _TALLY if t_ in v.lower()]
    ck("no card reports how many reads said what, or that one abstained", not _tally,
       _tally[:4])

    # 36: eleven asks give 11 candidate checks plus 9 first-named checks (the two DECIDED cards are
    # skipped there), then 1 candidate-name, 1 rect, 8 Latin, 2 zayin, 2 provenance, 2 no-reading.
    # This line is NOT
    # in its own total -- `ck`'s condition is evaluated before `ck` increments -- which is also how
    # section (10)'s count works. Written out because a count recomputed from the loops it counts
    # asserts nothing; it went red at 35 and that is what the line is for.
    # 38 since 2026-11-15: the zayin arrival added a check that the card's NOTE agrees with the
    # signed record's page, word and index (the note had the index wrong), plus its liveness sibling.
    # 40 later the same day, when the second zayin landed and the pinned "exactly one" went red: the
    # supply floor and the span-side zero are now separate clauses, and the token guard is new.
    ck("section 11 ran every one of its checks", n[0] - _c0 == 40, n[0] - _c0)

    print("")
    print("(12) item 5: the line strip and its derived baseline")
    _d0 = n[0]
    _cs12 = card_spans()[0]
    _elig = [c["span_id"] for c in CARDS
             if {x for a in card_asks(c) for x in a["candidates"]} & set(VERTICAL)]
    # A biconditional, so a card that silently lost its strip fails and so does one that gained a
    # strip without a vertical candidate. The count is checked too: an empty eligible set would
    # satisfy the biconditional on nothing.
    _LBL12 = "the line, and where its baseline falls"
    ck("every card with a vertical candidate has a strip, and no other card does (%d of %d)"
       % (len(_elig), len(CARDS)),
       t0.count(_LBL12) == len(_elig) and len(_elig) >= 1, (len(_elig), t0.count(_LBL12)))
    ck("the eligible set is derived, and it reaches a span ruling 4 does not name",
       "p254:n1" in _elig and "p628:n2" in _elig, _elig)
    for _sid in _elig:
        _s12 = _cs12[_sid]
        _sp12 = line_strip(_s12["page"], _s12["span_box"], _s12["column_bands"])
        ck("%s: the strip is established, not refused" % _sid, not _sp12.get("why"),
           _sp12.get("why"))
        if _sp12.get("why"):
            continue
        # The run the rect selected must really be a line of type, and the band must really be one
        # column. A strip that crossed the gutter would average two baselines into a plausible one.
        ck("%s: the rect covers the run it selects (%.0f%%, floor %.0f%%)"
           % (_sid, 100.0 * _sp12["cover"], 100.0 * STRIP_MIN_COVER),
           _sp12["cover"] >= STRIP_MIN_COVER)
        ck("%s: that run holds exactly one text line" % _sid,
           n_lines(_sp12["strip"].crop((0, _sp12["run"][0] - _sp12["top"], _sp12["strip"].width,
                                       _sp12["run"][1] - _sp12["top"] + 1))) == 1)
        ck("%s: the band declares its column (%r) and does not straddle the gutter"
           % (_sid, _sp12["col"]),
           _sp12["col"] in ("left", "right", "full_width")
           and (_sp12["col"] == "full_width"
                or (_sp12["band_box"][2] - _sp12["band_box"][0])
                <= 0.75 * page_bits(_s12["page"])[0].width))
        # The strip must be TALLER than the run it was taken from, or the low-ink rows the rule
        # needs are not in it -- the defect that made every profile look unimodal in probe2.
        ck("%s: the strip reaches past the line's own ink (%dpx strip, %dpx run)"
           % (_sid, _sp12["strip"].height, _sp12["run_h"]),
           _sp12["strip"].height > _sp12["run_h"])
        _si12 = strip_image(_sp12)
        ck("%s: a baseline was derived" % _sid, _si12["baseline"] is not None,
           _si12["detail"].get("why"))
        if _si12["baseline"] is None:
            continue
        _bb = _sp12["top"] + _si12["baseline"]
        ck("%s: the baseline falls inside the line it was derived from (band row %d in run %r)"
           % (_sid, _bb, _sp12["run"]),
           _sp12["run"][0] <= _bb <= _sp12["run"][1])
        ck("%s: the dense zone's top is above the baseline (%d < %d)"
           % (_sid, _si12["dense_top"], _si12["baseline"]),
           0 <= _si12["dense_top"] < _si12["baseline"])
        ck("%s: the two modes are at least %d bins apart (%d)"
           % (_sid, STRIP_MIN_SEP, _si12["detail"]["sep"]),
           _si12["detail"]["sep"] >= STRIP_MIN_SEP)
        ck("%s: the window holds the whole span box plus %d line-heights"
           % (_sid, STRIP_WIN_LINES),
           _si12["win"][0] <= _sp12["rect"][0] and _si12["win"][1] >= _sp12["rect"][2]
           and (_si12["win"][1] - _si12["win"][0])
           <= (_sp12["rect"][2] - _sp12["rect"][0]) + 2 * STRIP_WIN_LINES * _sp12["run_h"])
        # BOTH HALVES of the paper-only claim. "No mark landed on ink" passes on an image with no
        # marks at all, so the liveness half has to be here beside it.
        _msk = _si12["clean"].convert("L").point(lambda v: 255 if v < INK else 0)
        _dif = ImageChops.difference(_si12["img"], _si12["clean"]).convert("L")
        ck("%s: marks were actually drawn on the strip" % _sid, _dif.getbbox() is not None)
        ck("%s: not one mark landed on ink" % _sid,
           ImageChops.multiply(_dif, _msk).getbbox() is None)
        ck("%s: the scale is the stated integer factor" % _sid,
           _si12["f"] == max(1, int(round(TARGET_BAND / float(_sp12["run_h"])))), _si12["f"])
    # The caption may not claim the comparison scale, because it is not that scale: `comparison()`
    # takes the line height from the span crop's own peak and that differs from the band's run in
    # both directions (33/48/32/31 against 38/23/35/35 on these four).
    ck("the strip caption says it is NOT the comparison scale",
       "this is not the scale of the comparison images above" in t2)
    ck("the strip card states whose rule the threshold is, and names the abstention",
       "the midpoint of the two modes" in t2 and "2026-10-04" in t2
       and "abstaining when there is no second mode" in t2)

    # ABSTENTION, PROVEN LIVE. Every eligible span accepts, so the abstaining branch has no natural
    # case on this page -- and a guard nobody has seen work is not a guard. The third profile is the
    # control: without it, both abstention checks would pass on a function that always abstains.
    _uni = [40] * 60
    _b, _t, _du = baseline_guides(_uni)
    ck("a uniform profile abstains: no second mode", _b is None and "mode" in (_du["why"] or ""),
       _du.get("why"))
    # For a separation UNDER half scale the low mode must sit above half the peak, because the
    # peak itself always lands in the top bin: 60 against 100 puts the modes 6 bins apart. The first
    # draft of this case was [12] vs [95], whose modes are 13 bins apart -- it tested nothing.
    _near = [60] * 30 + [100] * 24
    _b, _t, _dn = baseline_guides(_near)
    ck("two modes under half scale apart abstain", _b is None and "apart" in (_dn["why"] or ""),
       (_dn.get("two"), _dn.get("sep"), _dn.get("why")))
    _far = [8] * 30 + [400] * 24
    _b, _t, _df = baseline_guides(_far)
    ck("CONTROL: two modes far apart are ACCEPTED, so the two checks above are not vacuous",
       _b == 53 and _t == 30 and _df["sep"] >= STRIP_MIN_SEP,
       (_b, _t, _df.get("two"), _df.get("sep")))
    # The zero padding, as a case rather than as a comment: a profile whose only mass is in the top
    # bin must not grow a second mode out of the end of the histogram.
    _top = [0] * 40 + [100] * 20
    _b, _t, _dz = baseline_guides(_top)
    ck("the histogram is padded with zero, not clamped (no mode manufactured at the top bin)",
       _dz["smooth"][STRIP_NBIN - 1] == _dz["hist"][STRIP_NBIN - 2] + _dz["hist"][STRIP_NBIN - 1],
       _dz["smooth"][-3:])
    # 1 biconditional, 1 derivation, 4 spans x 13, 2 caption, 4 synthetic = 60. This line is NOT
    # in its own total: `ck` evaluates the condition before it increments `n`.
    ck("section 12 ran every one of its checks", n[0] - _d0 == 60, n[0] - _d0)

    print("")
    print("(13) ruling 2026-11-01: needs, the cited-need check, and the signing rule")
    _e0 = n[0]
    _all_needs = [(sid, k, src) for sid, ents in NEEDS.items() for (k, src) in ents]
    _cites = [(c["span_id"], a.get("cites")) for c in CARDS for a in card_asks(c)
              if a.get("cites") is not None]
    _cited = [(sid, k) for sid, ks in _cites for k in ks]

    # A need whose key no predicate knows is not a need, it is a sentence with a colon in it.
    _unknown = [(sid, k) for sid, k, _s in _all_needs if need_met(sid, k)[1] == "unknown need key"]
    ck("every recorded need key is evaluable", not _unknown, _unknown)
    ck("every span with a recorded need is in the card population",
       not [sid for sid in NEEDS if sid not in {c["span_id"] for c in CARDS}],
       [sid for sid in NEEDS if sid not in {c["span_id"] for c in CARDS}])
    ck("every need carries a provenance this file knows",
       not [(s, k, x) for s, k, x in _all_needs if x not in ("audit", "laneB")],
       [(s, k, x) for s, k, x in _all_needs if x not in ("audit", "laneB")])
    # Provenance, checked against the audit rather than trusted. An `audit` source must point at a
    # span whose audit row actually carries a `needs` sentence -- otherwise the decomposition would
    # be free to attribute this lane's own asks to a human's adjudication.
    _AN = {r["span_id"] for r in _AUD.AUDIT if r.get("needs")}
    ck("every audit-sourced need belongs to a span whose audit row records one",
       not [(s, k) for s, k, x in _all_needs if x == "audit" and s not in _AN],
       [(s, k) for s, k, x in _all_needs if x == "audit" and s not in _AN])
    ck("every laneB-sourced need is one the audit did NOT record",
       not [(s, k) for s, k, x in _all_needs if x == "laneB" and s in _AN],
       [(s, k) for s, k, x in _all_needs if x == "laneB" and s in _AN])

    # ---- item 2's check, and the two things that stop it passing on nothing --------------------
    # THE CHECK. p628:n2 is why it exists: its note went on refusing on "the baseline strip is NOT
    # on this page yet" after item 5 put the strip on the page, so the card withheld a verdict on a
    # ground the same page satisfied.
    _met_cited = [(sid, k, need_met(sid, k)[1]) for sid, k in _cited if need_met(sid, k)[0]]
    ck("no card cites a need that is already met", not _met_cited, _met_cited)
    # LIVENESS. Without this, deleting every `cites` would make the check above green forever.
    # RESTATED 2026-11-15: the pointed zayin met p233:n4's only need, both cards now cite nothing
    # legitimately, and a guard that demanded a subject fired on the honest state. It asserts the
    # REASON there is none instead -- every need of a span a card asks about is met -- which goes
    # red on the real defect in this direction: a card whose own need is unmet and whose note says
    # nothing about it.
    _card_spans_asking = set(sid for sid, _ks in _cites)
    _unmet_of_cards = [(s_, k) for s_, ks in NEEDS.items() for k, _x in ks
                       if s_ in _card_spans_asking and not need_met(s_, k)[0]]
    ck("a card cites a need, or every need of a card's own span is met and that is why none does",
       any(ks for _s, ks in _cites) or not _unmet_of_cards, (_cites, _unmet_of_cards))
    # DISCRIMINATION. The clause above is satisfied for free if `need_met` has got stuck answering
    # True. Some need in the registry must still be unmet, or it is not a predicate.
    _unmet_any = [(s_, k) for s_, ks in NEEDS.items() for k, _x in ks if not need_met(s_, k)[0]]
    ck("need_met still answers both ways: some declared need is unmet",
       bool(_unmet_any) and bool([1 for s_, ks in NEEDS.items() for k, _x in ks
                                  if need_met(s_, k)[0]]), (_unmet_any, len(NEEDS)))
    # And the key has to be a RECORDED one: `need_met` answers an unknown key False, so an invented
    # key reads as unmet and would pass the check indefinitely.
    _ghost = [(sid, k) for sid, k in _cited if k not in [x[0] for x in NEEDS.get(sid, ())]]
    ck("every cited key is a need the record records", not _ghost, _ghost)

    # ---- item 3's rule, on the rows it decides -------------------------------------------------
    ck("p628:n2 cites nothing and is signable",
       dict(_cites).get("p628:n2") == () and signable("p628:n2")[0], signable("p628:n2"))
    # Restated 2026-11-15, when the pointed zayin met the need. The row this section was built
    # around is now the row that shows the need-clause CLEARING -- which is the direction nothing
    # had ever exercised, and the reason the predicate is read rather than the note.
    ck("p233:n4's zayin need is met by the pointed exemplar, so the card is signable",
       unmet("p233:n4") == [] and signable("p233:n4")[0], (unmet("p233:n4"), signable("p233:n4")))
    # `not_adjudicated` and `absent from the audit` are not near misses to be waved through: they
    # record that nobody decided, which is the opposite of a verdict.
    ck("not_adjudicated does not qualify (p910:n3)",
       audit_qualifies("p910:n3") == (False, "verdicts not_adjudicated, and not a reversal hit"),
       audit_qualifies("p910:n3"))
    ck("a span absent from the audit does not qualify (p596:n2)",
       audit_qualifies("p596:n2")[0] is False
       and "absent from the audit" in audit_qualifies("p596:n2")[1],
       audit_qualifies("p596:n2"))
    # The population, stated as a set rather than a count: a count would hold while one span
    # swapped for another. glyph_signer reads `signable` over this same union, so the card and the
    # sheet cannot disagree about one span.
    _pop = sorted(set(r["span_id"] for r in _AUD.AUDIT) | set(NEEDS))
    _sign = sorted(s for s in _pop if signable(s)[0])
    # SIX since 2026-11-15, not the five measured on 2026-11-01, and the sixth is named with its
    # cause: p233:n4 joined when Chris's pointed zayin met `exemplar:zayin`. A set, not a count, so
    # one span cannot swap for another silently.
    ck("the signable set is the five of 2026-11-01 plus p233:n4, whose zayin need was met",
       _sign == ["p233:n4", "p254:n1", "p442:n0", "p628:n2", "p798:n0", "p831:n2"], _sign)
    # The complement, BY CAUSE. The first draft of this check asserted the held-back set was the
    # three rows the cards cover; the population is the whole audit -- fourteen spans over twenty
    # rows -- so nine are held, and the check named a subset of the complement and called it the
    # complement. Typed by cause rather than listed flat, because the two causes are not the same
    # thing: a row held on the verdict clause is one a human decided needs no re-signing, while
    # p233:n4 is one a human WANTS signed and cannot have yet.
    _held = {}
    for _s in sorted(set(_pop) - set(_sign)):
        _held.setdefault("need" if signable(_s)[1].startswith("needs unmet") else "verdict",
                         []).append(_s)
    ck("the rows held on the verdict clause are the eight nobody asked to re-sign",
       _held.get("verdict") == ["p326:n11", "p428:n0", "p558:n3", "p594:n0", "p596:n2",
                                "p622:n0", "p735:n0", "p910:n3"], _held.get("verdict"))
    # Was "exactly one row is held on an unmet need, and it is p233:n4". It is nobody now: every
    # declared need in the registry is met. Kept as a check on the EMPTY state rather than deleted,
    # because a need that silently reappears is exactly what this row's history is about.
    ck("no row is held on an unmet need any more -- every declared need is met",
       _held.get("need") is None, _held.get("need"))
    # NAMED RESIDUAL: this section governs DECLARED citations. A note that claims insufficiency and
    # declares no `cites` is invisible to it -- only a reader catches that, and the reason the check
    # is scoped this way is that a card's prose cannot be parsed for a claim. What it does kill is
    # the shape the p628:n2 defect actually took: a named need, satisfied, still cited.
    #
    # 16 checks since 2026-11-15: the cites-liveness guard was restated when the pointed zayin
    # emptied every `cites`, and it gained a DISCRIMINATION sibling -- the restated clause is
    # satisfied for free if `need_met` stops answering False. This line is not in its own total:
    # `ck` increments after evaluating.
    ck("section 13 ran every one of its checks", n[0] - _e0 == 16, n[0] - _e0)

    # ---------------------------------------------------------------- (14) directed inclusions
    # Chris, 2026-11-08: "p596:n2 goes on the next sheet by hash; no audit rows written by hand."
    # A human-directed route onto a sheet. The hazard is not that it admits a span -- that is its
    # purpose -- but that it quietly widens a population somebody is about to sign, so both halves
    # are asserted here: sheetable yes, signable no, and the five-row signable set unchanged.
    print("")
    print("(14) directed sheet inclusions")
    _e14 = n[0]
    _dirs = sorted(DIRECTED)
    # Same union section 13 uses, plus the directed spans: a directive for a span in no other
    # population would otherwise be invisible to every check below.
    _pop14 = sorted(set(r["span_id"] for r in _AUD.AUDIT) | set(NEEDS) | set(DIRECTED))
    _cards14 = {c["span_id"] for c in CARDS}
    ck("at least one directive is recorded, so this section has a subject", bool(_dirs), _dirs)
    ck("every directive's pinned crop still hashes to what it recorded",
       all(pin_holds(s)[0] for s in _dirs),
       [(s, pin_holds(s)[1]) for s in _dirs if not pin_holds(s)[0]])
    ck("every directive names a span in the card population",
       all(s in _cards14 for s in _dirs), [s for s in _dirs if s not in _cards14])
    ck("every directive carries who, when, the words, and what it licenses",
       all(all(str(DIRECTED[s].get(k) or "").strip() for k in ("on", "by", "words", "licenses"))
           for s in _dirs),
       [s for s in _dirs if not all(str(DIRECTED[s].get(k) or "").strip()
                                    for k in ("on", "by", "words", "licenses"))])
    # A directive for a span the audit already qualifies would be a widening of a rule that
    # already covers it -- indistinguishable, afterwards, from the rule having changed.
    ck("no directive covers a span the audit already qualifies",
       not [s for s in _dirs if audit_qualifies(s)[0]],
       [s for s in _dirs if audit_qualifies(s)[0]])
    ck("no directive claims to license a verdict",
       not [s for s in _dirs if "verdict" not in DIRECTED[s]["licenses"].lower()
            or "not a verdict" not in DIRECTED[s]["licenses"].lower()],
       [DIRECTED[s]["licenses"] for s in _dirs])
    # The pin discriminates: a comparison that would pass on any bytes is not a pin.
    _other = D.DATA / "hebrew_aperture_crops_20260920" / "p596_context_strip.png"
    _oh = hashlib.sha256(_other.read_bytes()).hexdigest()[:16] if _other.exists() else None
    ck("the pinned hash is specific to those pixels, not shared by a neighbouring crop",
       _oh is not None and _oh != DIRECTED["p596:n2"]["pixel_pin"][1], _oh)
    ck("pin_holds refuses a span with no directive",
       pin_holds("p254:n1") == (False, "no directive recorded for this span"),
       pin_holds("p254:n1"))

    # THE COLLISION, asserted on the sealed clause by itself. `seal_state` consults the seal
    # and the ruling field and nothing else -- no audit, no needs -- so a check phrased over it
    # cannot be carried by a clause it does not name. That is this morning's mutation lesson,
    # applied before the defect instead of after it.
    ck("p596 is a SEALED page and p596:n2 is in SEALED_TRUTH",
       seal_state("p596:n2") == (True, "page 596 is SEALED and the span is in SEALED_TRUTH; "
                                       "no ruling lifts it for a signing surface"),
       seal_state("p596:n2"))
    ck("seal_state does not call every span sealed", not seal_state("p254:n1")[0],
       seal_state("p254:n1"))
    # Chris ruled on 2026-11-08 that the seal HOLDS, so this field stays None -- None meaning no
    # ruling lifts it, which is what he decided. A field recording "the seal was upheld" would
    # read to a later consumer as a ruling that opened the page, so the upholding lives in the
    # withdrawal and not here. If this ever becomes non-empty, somebody widened ruling 2.
    ck("the ruling upheld the seal, so no directive carries one that lifts it",
       not [s for s in _dirs if DIRECTED[s].get("seal_ruling")],
       [(s, DIRECTED[s].get("seal_ruling")) for s in _dirs])
    ck("p596:n2 is NOT sheetable: the sheet clause was withdrawn, and the seal is named as final",
       not sheetable("p596:n2")[0] and "WITHDRAWN" in sheetable("p596:n2")[1]
       and "standing is final" in sheetable("p596:n2")[1], sheetable("p596:n2"))
    ck("the `sheet` need reads CLOSED and not owed, while staying unmet",
       need_met("p596:n2", "sheet")[0] is False
       and need_met("p596:n2", "sheet")[1].startswith("CLOSED, not owed:")
       and "sheet" in unmet("p596:n2"), (need_met("p596:n2", "sheet"), unmet("p596:n2")))
    # The ORDER is not edited to agree with the ruling that overturned it. Pinned verbatim,
    # because "he asked for a sheet and I was told no" and "he never asked" are different
    # histories and only one of them is true.
    ck("the order stands in the record exactly as he gave it",
       DIRECTED["p596:n2"]["words"] == ("p596:n2 goes on the next sheet by hash; no audit rows "
                                        "written by hand"),
       DIRECTED["p596:n2"]["words"])
    # `.get(...) or {}`, not a subscript. A subscript here ABORTED the whole run under mutation
    # W1 (the withdrawal deleted) with a KeyError, so the 100-odd checks after this line never
    # ran and the harness could not tell a survival from a crash. A check must be able to FAIL.
    _sw = DIRECTED["p596:n2"].get("sheet_withdrawn") or {}
    ck("the withdrawal carries its own date, author and words",
       all(_sw.get(k) for k in ("on", "by", "words")) and _sw.get("on") == "2026-11-08", _sw)
    # THE TABLE. p596:n2 is withdrawn before it reaches the collision row, so without this the
    # branch Chris asked be kept would be kept and never run -- one refactor from gone. Every
    # input is passed IN, which is the whole reason `sheet_verdict` takes required arguments.
    # Expected codes are literal and ORDERED: withdrawn must outrank collision, or a matter he
    # has already settled comes back to him as an open question.
    _W = {"on": "2026-11-08", "by": "Chris", "words": "W"}
    _tbl = [(None, False, "-", "not_directed"),
            ({"on": "d"}, False, "-", "ok"),
            ({"on": "d"}, True, "page 9 is SEALED", "collision"),
            ({"on": "d", "seal_ruling": "lifted by X"}, True, "page 9 is SEALED", "ok"),
            ({"on": "d", "sheet_withdrawn": _W}, False, "-", "withdrawn"),
            ({"on": "d", "sheet_withdrawn": _W}, True, "page 9 is SEALED", "withdrawn")]
    _got = [sheet_verdict(a, b, c)[0] for a, b, c, _want in _tbl]
    ck("sheet_verdict's table reads row for row, and withdrawn outranks collision",
       _got == [r[3] for r in _tbl], list(zip(_got, [r[3] for r in _tbl])))
    ck("the table exercises every code sheet_verdict can return",
       sorted(set(_got)) == sorted(SHEET_CODES), (sorted(set(_got)), sorted(SHEET_CODES)))
    # Page-level is the stronger predicate and it is free: measured 2026-11-08, none of the frozen
    # 74 sits on any of the 14 sealed pages. If that ever stops holding, a span somebody signed is
    # on a sealed page and this lane needs to know before anything else. The count is the liveness
    # guard -- "none of them is sealed" passes on an empty list.
    _fz14 = [r["span_id"] for r in json.loads(io.open(str(FROZEN_SET),
                                                      encoding="utf-8").read())["rows"]]
    ck("all 74 of the frozen set are in front of that check", len(_fz14) == 74, len(_fz14))
    ck("no span in the frozen 74 sits on a sealed page",
       not [s for s in _fz14 if seal_state(s)[0]],
       [s for s in _fz14 if seal_state(s)[0]])

    # THE guard, and it has to bite on the audit clause by itself. `signable` is an AND of the
    # audit verdict and the needs, and p596:n2 fails both, so the two checks below it pass whether
    # or not the directive has leaked into qualification -- measured by mutation 2026-11-08: fold
    # the directive into audit_qualifies and both of them go on passing. These two cannot: the
    # qualifying population is the audit's answer with no needs clause in it, so a directive
    # folded in there has nothing to hide behind.
    ck("audit_qualifies does not consult the directive: it still reports p596:n2 absent",
       audit_qualifies("p596:n2") == (False, "absent from the audit: no verdict and no "
                                             "reversal flag"),
       audit_qualifies("p596:n2"))
    ck("the audit-qualifying population is unchanged by the directive",
       sorted(s for s in _pop14 if audit_qualifies(s)[0]) == ["p233:n4", "p254:n1", "p442:n0",
                                                              "p628:n2", "p798:n0", "p831:n2"],
       sorted(s for s in _pop14 if audit_qualifies(s)[0]))
    # Kept, and relabelled to what they show: two independent clauses hold this span out of the
    # console. That is worth asserting as belt and braces. It is not evidence about either clause.
    ck("p596:n2 is NOT signable -- by BOTH clauses, audit and needs (overdetermined)",
       not signable("p596:n2")[0] and not audit_qualifies("p596:n2")[0]
       and bool(unmet("p596:n2")), (signable("p596:n2"), unmet("p596:n2")))
    ck("the signable set is the five of 2026-11-01 plus p233:n4 (pointed zayin, 2026-11-15)",
       sorted(s for s in _pop14 if signable(s)[0]) == ["p233:n4", "p254:n1", "p442:n0", "p628:n2",
                                                       "p798:n0", "p831:n2"],
       sorted(s for s in _pop14 if signable(s)[0]))
    ck("nothing signable is excluded from sheetable",
       all(sheetable(s)[0] for s in _pop14 if signable(s)[0]),
       [s for s in _pop14 if signable(s)[0] and not sheetable(s)[0]])

    ck("every directed span records a `sheet` need",
       all("sheet" in [k for k, _src in NEEDS.get(s, ())] for s in _dirs),
       [s for s in _dirs if "sheet" not in [k for k, _src in NEEDS.get(s, ())]])
    ck("the `sheet` need is unmet while the sheet's own crop hash is unrecorded",
       all(need_met(s, "sheet")[0] == bool(DIRECTED[s].get("sheet_crop_sha16")) for s in _dirs),
       [(s, need_met(s, "sheet")) for s in _dirs])
    ck("p596:n2 still records that it has no audit row",
       "audit_row" in [k for k, _src in NEEDS.get("p596:n2", ())],
       [k for k, _src in NEEDS.get("p596:n2", ())])
    # NAMED RESIDUAL: `sheet` is met by a hash written INTO this registry by whoever builds the
    # next sheet. Nothing here forces that write, so a sheet could be built and the need left
    # reading unmet. What this does catch is the inverse -- a hash recorded with no sheet behind
    # it fails the pin's sibling check the moment a consumer re-reads those bytes.
    #
    # 23 checks. Not counting this line: `ck` increments after evaluating. Two were added
    # 2026-11-08 after mutation showed the population pair was overdetermined: both passed
    # through the very change they were written to catch, because `signable` is an AND and
    # this span fails both halves of it. Six more the same day, when building the directed
    # sheet turned up the SEAL: one check ("p596:n2 is sheetable, by the directive") was
    # REPLACED, because it asserted the thing that is now refused. Then on his ruling the
    # same day -- the seal holds, the sheet clause is withdrawn -- two of those six were
    # REPLACED in turn and four added, the table drive among them: p596:n2 no longer
    # reaches the collision row, so the row he asked be kept needs a driver that is not a
    # live span.
    ck("section 14 ran every one of its checks", n[0] - _e14 == 27, n[0] - _e14)

    # ---------------------------------------------------------------- (15) the disputed list
    # `DISPUTED` is what `sig_load` and rule 2b read to refuse an exemplar drawn on the glyph under
    # dispute. It was hand-typed and covered 2 of the 10 letter-cards, and the measured consequence
    # was that the final-nun census offered p628:n2's own word -- the span whose glyph 2 IS the
    # question "final nun or vav?" -- as a page to go and point a final nun on, and this loader
    # would have accepted the record.
    _e15 = n[0]
    # RE-DERIVED HERE, from CARDS, and NOT by calling `_disputed_from_cards`. Mutation proved the
    # first version of these two checks dead: they compared the producer against the producer, so a
    # derivation returning {} made the left side vacuous and one barring five positions a span made
    # the right side as wide as the defect. Both passed through the change they were written to
    # catch. This is the same arithmetic in different code, which is enough to fail a mutation of
    # the producer or of the union loop -- and it is the test's own statement of what a card asks.
    _asked = {}
    for _c in CARDS:
        for _a in card_asks(_c):
            if not (_a.get("candidates") or ()):
                continue
            for _p in ask_positions(_a):
                _asked.setdefault(_c["span_id"], set()).add((_a.get("word", _c.get("word")), _p))
    ck("every glyph a card asks about is a glyph no exemplar may come from",
       bool(_asked) and all(_asked[s] <= set(DISPUTED.get(s, ())) for s in _asked),
       sorted(s for s in _asked if not _asked[s] <= set(DISPUTED.get(s, ()))) or len(_asked))
    # The seven that were missing. Named, so that a derivation quietly narrowing back to the old
    # three cannot pass this section by deriving nothing.
    ck("the seven stale spans are in it, not just the two that were typed",
       all(s in DISPUTED for s in ("p233:n4", "p254:n1", "p442:n0", "p596:n2", "p628:n2",
                                   "p798:n0", "p831:n2")),
       [s for s in ("p233:n4", "p254:n1", "p442:n0", "p596:n2", "p628:n2", "p798:n0", "p831:n2")
        if s not in DISPUTED])
    # The union, in the direction a pure derivation would have broken: p895:n0 is a RULED span and
    # not one of the cards, so nothing in CARDS can put it back.
    ck("the hand list's non-card span survives the union",
       DISPUTED.get("p895:n0") == [(1, 4)], DISPUTED.get("p895:n0"))
    # The other direction. An over-exclusion is not the safe way to be wrong: every position barred
    # here is an exemplar this lane cannot draw, out of a supply that is 26 words wide for final nun.
    _hand = {"p217:n2": [(1, 3)], "p423:n3": [(2, 3)], "p895:n0": [(1, 4)]}
    ck("nothing is barred that neither a card nor the hand list names",
       all(set(DISPUTED[s]) <= _asked.get(s, set()) | set(_hand.get(s, ())) for s in DISPUTED),
       sorted(s for s in DISPUTED
              if not set(DISPUTED[s]) <= _asked.get(s, set()) | set(_hand.get(s, ()))))
    # p831:n2 cuts a PAIR -- `pos` is a tuple there -- so a derivation reading `pos` as a number
    # would store one position and drop the other, and the dropped one is a resh under dispute.
    ck("a card whose pos is a tuple contributes BOTH of its positions",
       sorted(DISPUTED.get("p831:n2", ())) == [(1, 2), (1, 3)], DISPUTED.get("p831:n2"))
    ck("section 15 ran every one of its checks", n[0] - _e15 == 5, n[0] - _e15)

    # ---------------------------------------------------------------- (16) the context-tile ruling
    print("")
    print("(16) Chris's ruling: a context tile is an exemplar where rule 2 holds")
    _e16 = n[0]
    # ADMITTED, and labelled. resh, vav and he are covered by NOTHING ELSE: if the admission broke,
    # three letters on the sitting's own legend would silently have no specimen, and the legend would
    # print a comparison with one side missing.
    _resh = sig_exemplars("resh")
    ck("a rule-2-clean context tile is an exemplar, and says it came from context",
       len(_resh) == 1 and _resh[0]["kind"] == "context" and _resh[0]["word"] == u"\u05e1\u05e0\u05e8",
       [(r["kind"], r["word"]) for r in _resh])
    _only_ctx = [k for k in ("resh", "vav", "he")
                 if sig_exemplars(k) and all(r["kind"] == "context" for r in sig_exemplars(k))]
    ck("some letter is covered by a context tile and nothing else, so the clause above matters",
       sorted(_only_ctx) == ["he", "resh", "vav"], _only_ctx)
    # REFUSED, in the same breath. final nun's only impression anywhere is the p386 tile, and the
    # word holds a yod -- its own lookalike on card p254:n1. Admitting it would have put the glyph
    # under dispute on the card as the specimen of the answer.
    # OVER EVERY LETTER, because the rule is about tiles and not about letters. This clause used
    # to read "final_nun and yod have no exemplar at all", which was true on the day it was written
    # and false the moment Chris pointed a final nun on p503 and a mem on p150 whose word carries
    # two clean yods. The dirty tile is still refused; the letter it belongs to simply got supply
    # from somewhere else, which is precisely what naming a letter could not express.
    _dirty, _admitted = [], []
    for _k in sorted(LETTER):
        _adm = set((r["file_page"], r["word"], r["letter_index_from_right"])
                   for r in sig_exemplars(_k, want=10 ** 6) if r["kind"] == "context")
        _admitted.extend(sorted(_adm))
        for _t in sig_context_tiles(_k):
            if _rule2_dirt(_t[1], _k, card_rivals_union(_k)):
                _dirty.append((_k, _t, _t in _adm))
    ck("no rule-2-dirty context tile is admitted as an exemplar, for any letter",
       not [x for x in _dirty if x[2]], [x for x in _dirty if x[2]][:4])
    ck("dirty tiles exist, so the refusal above has a subject (%d of them)" % len(_dirty),
       bool(_dirty) and bool(_admitted),
       ([(k, t) for k, t, _in in _dirty][:4], len(_admitted)))
    # The two states must stay DISTINGUISHABLE. "refused, and here is the rival" and "nobody ever
    # drew one" send a signer to different work, and a page printing both as absence is the
    # represent-nothing-here defect.
    # The word is a literal because it is a fixed printed word; the letter with NO tile is not,
    # because that population moves with every signature. tav stood here and passed only because
    # nobody has yet signed a word containing a tav he did not point.
    _notile = sorted(k for k in LETTER if not sig_context_tiles(k))
    ck("a refused tile is still reported, with the rival that refused it named",
       _rule2_dirt(u"\u05d9\u05d3\u05d9\u05df", "final_nun", card_rivals_union("final_nun"))
       == ("yod",) and bool(_notile),
       (_rule2_dirt(u"\u05d9\u05d3\u05d9\u05df", "final_nun", card_rivals_union("final_nun")),
        _notile[:6]))
    # THE EXEMPTION, under a standard that would refuse the word. The pointed zayin sits in a word
    # holding a he; scored against he it survives, because the signer named the index.
    # EVERY zayin admitted under a standard that refuses its word is pointed, and there is at
    # least one. Pinned to a list of one, this went red when the second zayin arrived -- the second
    # impression of the letter the roster asked for, i.e. the check broke on the work succeeding.
    _zhe = sig_exemplars("zayin", want=10 ** 6, partners=("he",))
    ck("a POINTED exemplar survives a standard that refuses its word",
       bool(_zhe) and all(r["kind"] == "pointed" for r in _zhe)
       and all(u"\u05d4" in r["word"] for r in _zhe),   # the he that refuses the word
       [(r["kind"], r["word"]) for r in _zhe])
    ck("the same kind of standard DOES refuse a context tile, so the exemption is not vacuous",
       sig_exemplars("resh", partners=("samekh",)) == [] and len(_resh) == 1,
       (len(sig_exemplars("resh", partners=("samekh",))), len(_resh)))
    # The default standard is the CARD's rivals, unioned over every ask. resh is asked only against
    # dalet, which is why its samekh-bearing word is clean here and would not be under another axis.
    ck("the default standard is the union of the card rivals, not a global list",
       sorted(card_rivals_union("resh")) == ["dalet"]
       and sorted(card_rivals_union("dalet")) == ["final_kaf", "resh", "samekh"],
       (sorted(card_rivals_union("resh")), sorted(card_rivals_union("dalet"))))
    # SINGLE INSTANCE, both directions, over the POPULATIONS and not two named letters. zayin
    # stood for the single and dalet for the multiple; zayin has two now and dalet three, so both
    # literals went red while the labelling they test stayed correct. The flag is a property of the
    # CALL -- `want` truncates before it is computed -- so these use the renderer's own default,
    # which is the call whose output a human reads.
    _sing = sorted(k for k in LETTER if len(sig_exemplars(k)) == 1)
    _many = sorted(k for k in LETTER if len(sig_exemplars(k)) > 1)
    ck("a letter with one admitted impression has it marked single_instance",
       all(sig_exemplars(k)[0]["single_instance"] for k in _sing),
       [(k, sig_exemplars(k)[0]["single_instance"]) for k in _sing
        if not sig_exemplars(k)[0]["single_instance"]] or _sing)
    ck("a letter with more than one has none of them marked single_instance",
       all(not r["single_instance"] for k in _many for r in sig_exemplars(k)),
       [(k, [r["single_instance"] for r in sig_exemplars(k)]) for k in _many
        if any(r["single_instance"] for r in sig_exemplars(k))] or _many)
    ck("both populations exist, so neither clause above is a for-all over nothing",
       bool(_sing) and bool(_many), (len(_sing), len(_many)))
    # The labels are added to COPIES. A record relabelled in the cache would arrive at the next
    # caller already carrying another caller's standard, and a context tile whose `letter` was
    # overwritten in place would stop being findable as the letter its signer actually pointed at.
    for _k in ("resh", "zayin", "dalet", "nun", "he", "vav"):
        sig_exemplars(_k)
    ck("the labels go on copies: the cached signature records are untouched",
       not any("kind" in r or "single_instance" in r for r in _SIGCACHE.get("good", ()))
       and sorted(r["letter"] for r in _SIGCACHE.get("good", ())) ==
       sorted(r["letter"] for r in sig_load()[0]),
       [k for r in _SIGCACHE.get("good", ()) for k in ("kind", "single_instance") if k in r])
    if OUTHTML.exists():
        _t16 = re.sub(r"base64,[A-Za-z0-9+/=]+", "", OUTHTML.read_text(encoding="utf-8"))
        # The ruling is only honoured if it reaches the page a human reads. An unlabelled picture
        # reads as the same evidence as a pointed one, which is the opposite of what admitting the
        # weaker kind was for.
        ck("the page labels a context exemplar as coming from context",
           "a box the signer drew around another glyph" in _t16, "a box the signer drew" in _t16)
        # EVERY single-instance letter a card actually shows -- the renderer only reaches the
        # letters that are candidates on some card, so the population is the intersection. zayin
        # was named here as a literal and stopped being single-instance the same day.
        _cands16 = set(x for c in CARDS for a in card_asks(c) for x in a["candidates"])
        _shown = sorted(set(_sing) & _cands16)
        ck("the page states where a comparison rests on one specimen, and names the letter",
           bool(_shown) and "single exemplar:" in _t16
           and all(("the only signed impression of %s" % k) in _t16 for k in _shown),
           (_shown, [k for k in _shown
                     if ("the only signed impression of %s" % k) not in _t16]))
    else:
        ck("the page labels a context exemplar as coming from context", False, "no page")
        ck("the page states where a comparison rests on one specimen, and names the letter",
           False, "no page")
    # 14 since the populations were derived: single_instance gained its liveness sibling, which
    # the two named letters did not need because naming them was itself the (wrong) subject.
    ck("section 16 ran every one of its checks", n[0] - _e16 == 14, n[0] - _e16)

    print("")
    print("(17) Chris's ruling 2026-11-16: the band belongs to the WORD")
    _e17 = n[0]
    _LOCK = "PREDICTIONS_exemplarband_3410d26cb1826b10.json"

    def _calls_in(fnname):
        """Every name called inside one function, from the AST.

        The claim these checks make is about WHICH CROP a question is asked about, and that is a
        property of the call graph, not of the text. A docstring can name band_geometry; only the
        AST says whether the function calls it."""
        import ast
        t = ast.parse(io.open(__file__, encoding="utf-8").read())
        for node in ast.walk(t):
            if isinstance(node, ast.FunctionDef) and node.name == fnname:
                out = set()
                for x in ast.walk(node):
                    if isinstance(x, ast.Call):
                        fn = x.func
                        if isinstance(fn, ast.Name):
                            out.add(fn.id)
                        elif isinstance(fn, ast.Attribute):
                            out.add(fn.attr)
                return out
        return None

    _sl = _calls_in("sig_load")
    ck("no band question is put to a GLYPH any more: sig_load calls neither _one_band nor "
       "text_bands",
       _sl is not None and not (_sl & {"_one_band", "text_bands", "ink_runs"}),
       sorted((_sl or set()) & {"_one_band", "text_bands", "ink_runs"}))
    ck("sig_load asks the WORD instead", _sl is not None and "word_band" in _sl, sorted(_sl or ()))
    # The carve-out is for the exemplar path ONLY. If one of these goes red, a line-crop
    # population has silently inherited a rule derived for words, and p362:n1 and p423:n3 are
    # ratified on the first of them. rerat_load gates new_box; box_quality reports one_band.
    #
    # The first version of this check named `sig_rerat`, which is not a function in this module. It
    # went red on a name I had invented rather than read, and a check pinned to a name that does
    # not exist cannot see the path it names. _calls_in returns None for an unknown name, so both
    # of these assert `is not None` as well: a rename must make the check RED, never vacuous.
    for _fn17 in ("rerat_load", "box_quality"):
        _rr = _calls_in(_fn17)
        ck("the LINE-CROP path keeps the old gate: %s still calls _one_band, not word_band" % _fn17,
           _rr is not None and "_one_band" in _rr and "word_band" not in _rr,
           (_fn17, sorted(_rr or ())))

    # P4 of the lock. A pin is right here: the ruling's own clause is that no threshold moves, and
    # the lock it is registered in is named so the pin can be read back to its authority.
    ck("no threshold moved (%s): MIN 20, MAX 50, frac 0.12" % _LOCK,
       (MIN_BAND_PX, MAX_BAND_PX, BAND_FRAC) == (20, 50, 0.12),
       (MIN_BAND_PX, MAX_BAND_PX, BAND_FRAC))

    # The required argument. A function that derives its own input fails silently: handed the signed
    # box alone, word_band would measure the glyph and pass under the new name.
    _g17, _b17 = sig_load()
    _r17 = [x for x in _g17 if int(x["file_page"]) == 309]
    ck("every record in the file is either admitted or refused with a reason -- none is dropped",
       len(_g17) + len(_b17) == len([1 for _l in io.open(SIGS, encoding="utf-8") if _l.strip()])
       and all(x.get("_refused") for x in _b17),
       (len(_g17), len(_b17)))
    if _r17:
        _rec = _r17[0]
        _bx = [e["box"] for e in sorted(_rec["letter_boxes"],
                                        key=lambda e: int(e["index_from_right"]))]
        _raised = None
        try:
            word_band(_rec["file_page"], _bx[:1], len(strip_nikud(_rec["word"])))
        except ValueError as _e:
            _raised = str(_e)
        ck("word_band REFUSES a short box list rather than measuring the glyph it was handed",
           _raised and "box(es) for a" in _raised, _raised)
        ck("the count is a required argument, not a default",
           "expect" in word_band.__code__.co_varnames[:word_band.__code__.co_argcount]
           and not (word_band.__defaults__ or ()),
           word_band.__defaults__)

        # THE DISCRIMINATING CHECK. The record the old gate refused is admitted now, and the reason
        # it refused is still reproducible on the glyph crop -- so this is not "the gate got looser",
        # it is "the question moved to the word". A check that only asserted admission would pass
        # equally if the gate had been deleted.
        _gim, _gf = cut_native(_rec["file_page"], _rec["box"])
        _runs = [] if _gf else [b - a + 1 for a, b in ink_runs(_gim)]
        _wv, _wband, _winfo = word_band(_rec["file_page"], _bx, len(strip_nikud(_rec["word"])))
        ck("p309's yod: the GLYPH crop is still no-band (one %s px ink run, under the %d px floor) "
           "while the WORD is one-band at %s px" % (_runs, MIN_BAND_PX, _winfo.get("band_px")),
           not _gf and not _one_band(_gim) and len(_runs) == 1 and _runs[0] < MIN_BAND_PX
           and _wv == "one-band",
           (_gf, _runs, _wv))
        ck("p309 is admitted, which it was not before the ruling", bool(_r17))

    # The ruled band rule (Chris 2026-11-22). Part 2 is enforced, part 1 is an invariant, the
    # withdrawn clause's measure is still carried, and the refusal is driven by mutation.
    ck("every admitted record carries a margin for every one of its glyph boxes",
       all(sorted((x["_word_band"].get("margins") or {}).keys())
           == sorted(int(e["index_from_right"]) for e in x["letter_boxes"]) for x in _g17),
       [x["file_page"] for x in _g17
        if sorted((x["_word_band"].get("margins") or {}).keys())
        != sorted(int(e["index_from_right"]) for e in x["letter_boxes"])])
    ck("a margin is a signed number at BOTH ends, not a verdict",
       all(set(m) == {"top", "bottom"} and all(isinstance(v, int) for v in m.values())
           for x in _g17 for m in x["_word_band"]["margins"].values())
       and box_band_margin([0, 10, 10, 90], [20, 80])[1] == {"top": -10, "bottom": -10},
       box_band_margin([0, 10, 10, 90], [20, 80]))
    ck("every admitted record states the ruled rule in words, and says part 1 is by construction",
       all("ENFORCED since" in (x["_word_band"].get("band_rule") or "")
           and "INVARIANT" in (x["_word_band"].get("band_rule") or "")
           and "2026-11-22" in (x["_word_band"].get("band_rule") or "")
           and _LOCK in (x["_word_band"].get("band_rule") or "")
           and "clause_4a" not in x["_word_band"] for x in _g17),
       [x["file_page"] for x in _g17 if "clause_4a" in x["_word_band"]])

    # PART 2, re-measured on every run rather than remembered: 29 of 29 overlapped on 2026-11-22,
    # so the clause refuses nothing today and this check is the record of that, not evidence that
    # the clause is wired up. The mutation checks below are that evidence.
    _nbox = sum(len(x["_word_band"]["box_overlaps_band"]) for x in _g17)
    _ovl = sum(1 for x in _g17 for v in x["_word_band"]["box_overlaps_band"].values() if v)
    _inb = sum(1 for x in _g17 for v in x["_word_band"]["box_in_band"].values() if v)
    _binb = sum(1 for x in _g17 if x["_word_band"]["band_in_box_union"])
    ck("part 2 holds on every admitted record: %d of %d glyph boxes overlap their word's band"
       % (_ovl, _nbox), _ovl == _nbox and _nbox > 0, (_ovl, _nbox))
    ck("part 1 holds on %d of %d words -- reported, and by construction, so it is not evidence"
       % (_binb, len(_g17)), _binb == len(_g17), (_binb, len(_g17)))
    ck("the WITHDRAWN clause is still measured and still refuses everything: %d of %d boxes sit "
       "inside the band" % (_inb, _nbox), _inb == 0, (_inb, _nbox))

    # THE REFUSAL, PROVED BY MUTATION. A green run over records that all pass says nothing about
    # whether the clause is wired up; the only thing that does is driving it to refuse.
    _band17 = [100, 130]
    _ok17 = [dict(index_from_right=1, box=[0, 95, 10, 135]),
             dict(index_from_right=0, box=[12, 96, 22, 134])]
    _w_ok, _i_ok = band_clause_fault(_ok17, _band17)
    _moved = [_ok17[0], dict(index_from_right=0, box=[12, 200, 22, 240])]
    _w_mv, _i_mv = band_clause_fault(_moved, _band17)
    _w_p1, _i_p1 = band_clause_fault(
        [dict(index_from_right=0, box=[0, 105, 10, 125])], [100, 130])
    ck("the clause ADMITS two boxes that overlap the band", _w_ok is None, _w_ok)
    ck("the clause REFUSES a glyph box displaced clear of the band, naming part 2 and the index",
       _w_mv is not None and "part 2" in _w_mv and "[0]" in _w_mv
       and _i_mv["box_overlaps_band"] == {0: False, 1: True}, (_w_mv, _i_mv.get("box_overlaps_band")))
    _touch = [dict(index_from_right=1, box=[0, 95, 10, 135]),
              dict(index_from_right=0, box=[12, 130, 22, 180])]
    _w_t, _i_t = band_clause_fault(_touch, _band17)
    ck("a box that only TOUCHES the band's last row still overlaps it",
       _w_t is None and _i_t["box_overlaps_band"] == {0: True, 1: True}
       and _i_t["box_in_band"][0] is False, (_w_t, _i_t.get("box_overlaps_band")))
    ck("a part-1 failure is reported as a defect in word_band, not a verdict about the record",
       _w_p1 is not None and "part 1" in _w_p1 and "defect in word_band" in _w_p1
       and _i_p1["band_in_box_union"] is False, _w_p1)
    _w_e = None
    try:
        band_clause_fault([], _band17)
    except ValueError as _e4:
        _w_e = str(_e4)
    ck("the clause REFUSES an empty box list rather than passing a record it measured nothing of",
       _w_e is not None and "glyph boxes" in _w_e, _w_e)
    ck("section 17 ran every one of its checks", n[0] - _e17 == 21, n[0] - _e17)

    print("")
    print("%s: %d/%d checks" % ("PASS" if not f[0] else "FAIL", n[0] - f[0], n[0]))
    return f[0]


def spans_of(sid):
    """One span record from the CARD population -- build_set where it reaches, frozen set elsewhere.

    Not `build_set` alone. Both callers iterate CARDS, seven of which are frozen-set spans, and the
    KeyError aborted the suite from inside a list comprehension in section (7).
    """
    return card_spans()[0][sid]


def _blank_span(s):
    if not s["span_box"]:
        return False
    im, _r = cut(s["page"], s["span_box"], D.PAD, s["column_bands"])
    return not (im and ink_bbox(im))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "build":
        print("wrote %s" % build())
    elif cmd == "selftest":
        sys.exit(1 if selftest() else 0)
    elif cmd == "census":
        c = census()
        print("exemplar census over the signed set (FILE pages; printed = file - 88)")
        for k in ("mem", "pe", "bet", "gimel"):
            v = c[k]
            print("  %-6s %s %d span(s), %d occurrence(s)  %s"
                  % (k, "OK " if v["n"] >= 3 else "SHORT", v["n"], v["occurrences"],
                     ", ".join(v["spans"])))
        print("  contrast pairs (one impression showing both candidates): %s"
              % (c["contrast_pairs"] or "NONE -- cannot be built from this corpus"))
    elif cmd == "sigs":
        g, b = sig_load()
        print("exemplar signatures (FILE pages; printed = file - 88)")
        for r in g:
            print("  OK      %-6s file p%-4d printed p%-4d %-22s %s  %s %s"
                  % (r["letter"], r["file_page"], r["file_page"] - 88, r["word"],
                     r["box"], r["signer"], r["date"]))
        for r in b:
            print("  REFUSED line %-3s %s" % (r.get("_line"), r.get("_refused")))
        print("")
        rg, rb = rerat_load()
        print("box re-ratifications")
        for k, r in rg.items():
            print("  OK      %-9s %s  %s  old=%s  %s %s"
                  % (k, r["text"], r["new_box"], r["old_box_state"], r["signer"], r["date"]))
        for r in rb:
            print("  REFUSED line %-3s %s" % (r.get("_line"), r.get("_refused")))
    elif cmd == "boxq":
        one, tot_, bad_ = one_band_report()
        print("box quality over the signed set (FILE pages; printed = file - 88)")
        for r in box_quality():
            print("  %-9s p%-5d %-11s %s line(s)  %s"
                  % (r["span_id"], r["page"], str(r["size"]), r["lines"], r["fault"] or ""))
        print("")
        print("  exactly one line band: %d of %d readable crops" % (one, tot_))
        print("  loose boxes: %s" % ", ".join(bad_))
    elif cmd == "exemplars":
        for a, b in (("mem", "pe"), ("pe", "mem"), ("bet", "gimel"), ("gimel", "bet")):
            print("")
            print("%s (excluding any word containing %s):" % (a, b))
            for sid, s, _p, occ in exemplars(a, b):
                print("   %-10s %s   %s" % (sid, s["truth"], where(s["truth"], occ)))
