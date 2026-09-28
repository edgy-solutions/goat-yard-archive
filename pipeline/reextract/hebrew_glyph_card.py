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
import base64, io, json, re, sys, unicodedata
from pathlib import Path

from PIL import Image, ImageDraw

import hebrew_aperture_diag as D
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
          "shin": "ש", "tav": "ת"}

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
}

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
]


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


# --- SIGNED RECORDS FROM THE WHOLE VOLUME ---------------------------------------------------
# Every record is validated before it can reach a card. The refusals are printed, never swallowed:
# a capture surface that drops a mis-drawn box in silence would put the signer back where the four
# wrong truth rows came from -- a plausible picture with nothing checking that it is the right one.
SIG_REQUIRED = ("file_page", "box", "coord_space", "word", "letter",
                "letter_index_from_right", "signer", "date")
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


def sig_load(path=None):
    """(good, refused) exemplar signatures. Validation is the whole point of this function.

    Checks, in order, and every one of them has a failure mode it was written for:
      - every required field present, and `coord_space` == "native" (the other space exists);
      - the box cuts a real, non-blank, in-bounds crop -- D.crop_fault, the outbound gate;
      - the crop holds exactly ONE text line, so the exemplar is a letter and not a paragraph;
      - the named letter really is at the named index of the named word. The word text is provenance,
        the (box, letter, index) triple is the claim, and this check is what ties them: a typo in the
        word or an off-by-one in the index is caught here rather than pointing a signer at the glyph
        next door;
      - the box does not overlap a card's own DISPUTED span on the same page. An exemplar may not be
        the thing it is evidence about, and that guard cannot be left to memory."""
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
            elif not _one_band(im):
                why = ("exemplar crop is %s (%d ink runs) -- it must hold exactly one text band"
                       % (band_geometry(im)[0], n_lines(im)))
            else:
                idx = int(r["letter_index_from_right"])
                want = (1, idx)
                if want not in positions(r["word"], LETTER[r["letter"]]):
                    why = ("%s is not at glyph %d from the right of %s (it is at %s)"
                           % (r["letter"], idx, r["word"],
                              positions(r["word"], LETTER[r["letter"]]) or "no occurrence"))
                else:
                    for sid, rect in dis:
                        if _overlaps(r["box"], rect):
                            why = ("box overlaps the disputed span %s on this page -- an exemplar "
                                   "may not be the glyph under dispute" % sid)
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
    """(span_id, native rect) for every span holding a DISPUTED glyph, so no exemplar can come from one."""
    out = []
    for s in D.build_set(include_sealed=True):
        if s["span_id"] not in DISPUTED or not s["span_box"]:
            continue
        _im, rects = cut(s["page"], s["span_box"], D.PAD, s["column_bands"])
        for rr in rects:
            out.append((s["span_id"], rr["box"]))
    return out


_SIGCACHE = {}


def sig_exemplars(letter, want=9):
    """Signed exemplars of `letter` from anywhere in the volume, newest signature last.

    No partner-letter exclusion: see the module docstring. A word containing both candidates is the
    contrast pair this corpus could not supply, and it is admissible precisely because the signer
    named an index."""
    if "good" not in _SIGCACHE:
        _SIGCACHE["good"], _SIGCACHE["bad"] = sig_load()
    return [r for r in _SIGCACHE["good"] if r["letter"] == letter][:want]


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
    ch = LETTER[letter]
    pch = LETTER[partner] if partner else None
    rows = []
    for s in D.build_set(include_sealed=True):
        t = strip_nikud(s["truth"])
        if not t or s["truth"] == D.NOT_HEBREW or ch not in t:
            continue
        if pch and pch in t:
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


def build(out=None):
    out = out or OUTHTML
    spans = {s["span_id"]: s for s in D.build_set(include_sealed=True)}
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
    for src, refused in (("exemplar signature", _sb), ("box re-ratification", _rb)):
        for r in refused:
            h.append('<div class="warnbox">REFUSED %s, line %s: %s<br><span class="prov">%s</span>'
                     '</div>' % (src, r.get("_line"), r.get("_refused"),
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
        if c["span_id"] in PENDING_RESIGN:
            # The truth table still holds the superseded string, because the batch rule is one batch
            # then one re-tally. Printing it unlabelled on a signing surface is the small version of
            # the defect this file exists to catch.
            h.append('<div class="warnbox">The string above is SUPERSEDED: %s.</div>'
                     % PENDING_RESIGN[c["span_id"]])
        if c["pos"]:
            ws = words(s["truth"])
            w = (' in word %d, <span class="heb" dir="auto">%s</span> (word 1 is the rightmost)'
                 % (c["word"], ws[c["word"] - 1])) if c["word"] else ""
            h.append('<div class="mut">Count glyph <b>%d</b> from the right%s.</div>'
                     % (c["pos"], w))

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
            h.append('<div class="cell">%s<div class="cap">the ratified span box at NATIVE size, '
                     'cut as the runner cuts it (A2, pad %dpx) &mdash; exactly what a reader was '
                     'shown. It holds <b>%d text line(s)</b>: the neighbours come with the box, and '
                     'they are why an arm that transcribes the whole crop returns more than the '
                     'signature and is scored <code>contains</code>.</div></div>'
                     % (img_ctx(a2), D.PAD, n_lines(a2)))
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

        if c["kind"] == "letter":
            a, b = c["candidates"]
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
            for cand, partner in ((a, b), (b, a)):
                sg = sig_exemplars(cand)
                ex = exemplars(cand, partner, exclude=(c["span_id"],))
                h.append('<div class="lbl">%s &mdash; %s &mdash; %d exemplar(s): %d signed from the '
                         'volume, %d from signed spans</div>'
                         % (cand, LETTER[cand], len(sg) + len(ex), len(sg), len(ex)))
                h.append('<div class="feat">%s</div>' % FEATURES.get(cand, ""))
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
                             % (len(sg) + len(ex), cand, len(ex), partner))
                h.append('<div class="row wrap">')
                for r in sg:
                    # A signed volume exemplar carries its own provenance, and it is shown: a record
                    # whose page, box, index and signer are not on the page beside the picture is a
                    # screenshot with extra steps.
                    h.append('<div class="cell">%s<div class="cap"><b>signed exemplar</b> '
                             '<span class="heb" dir="auto">%s</span><br>%s<br>'
                             '<span class="prov">file p%s &middot; printed p%s &middot; box %s '
                             '&middot; %s, %s</span>%s</div></div>'
                             % (img_comp(r["_crop"]), r["word"],
                                where(r["word"], [(1, int(r["letter_index_from_right"]))]),
                                r["file_page"], r["file_page"] - 88, r["box"], r["signer"],
                                r["date"],
                                ("<br>" + r["note"]) if r.get("note") else ""))
                for sid, es, p, occ in ex:
                    pend = ("<br><b>note:</b> %s" % PENDING_RESIGN[sid]) if sid in PENDING_RESIGN \
                        else ""
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
    OUTHTML.write_text("\n".join(h), encoding="utf-8")
    return OUTHTML


def selftest():
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
    print("(2b) the circular exemplar that the first run actually produced")
    # p217:n2 disputes mem-vs-pe and its truth row still SAYS mem, so the unguarded rule offered the
    # disputed glyph as the reference shape for one of its own candidates. An invariant nobody can
    # watch fail is not tested, so the guard is demonstrated against that real case.
    ck("p217:n2 IS picked as a mem exemplar without the guard",
       "p217:n2" in [sid for sid, _s, _p, _o in _unguarded_exemplars("mem", "pe")])
    for cand, partner in (("mem", "pe"), ("pe", "mem")):
        ck("p217:n2 is NOT a %s exemplar on its own card" % cand,
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
        ck("a superseded signature is never printed unlabelled",
           all(("p895" not in t0) or (PENDING_RESIGN["p895:n0"][:40] in t0) for _ in [0]))

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
    for c in CARDS:
        s_ = {x["span_id"]: x for x in D.build_set(include_sealed=True)}[c["span_id"]]
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
        for arm in ("gpt-", "claude-", "gemini", "qwen", "glm-", "deepseek", "kimi", "grok",
                    "minimax", "mimo", "nemotron", "ling-", "step-", "abstain"):
            ck("no arm/read token '%s' in the page text" % arm, arm not in t)

    print("")
    print("(6) the record gate: a bad signature is refused, not shown")
    # Every check here is a refusal that has a failure mode behind it. The fixtures are synthesized
    # from a REAL span so the geometry is real, and they are written to a temp file -- a born-test
    # never writes to the evidence store.
    import tempfile, os
    sp = {x["span_id"]: x for x in D.build_set(include_sealed=True)}["p491:n1"]
    _i, _r = cut(sp["page"], sp["span_box"], D.PAD, sp["column_bands"])
    _v, _g, _fo, _wb = find_ink(sp["page"], _r, grow=80)
    okbox = candidate_band_box(sp["page"], _wb)
    base = dict(file_page=sp["page"], box=okbox, coord_space="native", word=sp["truth"],
                letter="bet", letter_index_from_right=1, signer="TEST", date="2026-09-27")
    ck("the fixture names a real letter at a real index",
       (1, 1) in positions(sp["truth"], LETTER["bet"]), positions(sp["truth"], LETTER["bet"]))
    cases = [("a well-formed signature is accepted", dict(base), True),
             ("a strip-coordinate box is refused", dict(base, coord_space="strip"), False),
             ("an off-by-one letter index is refused",
              dict(base, letter_index_from_right=2), False),
             ("a box off the page is refused",
              dict(base, box=[okbox[0], okbox[1] + 90000, okbox[2], okbox[3] + 90000]), False),
             ("a box holding more than one text line is refused",
              dict(base, box=[okbox[0], okbox[1] - 120, okbox[2], okbox[3] + 120]), False),
             ("a signature with no signer is refused", dict(base, signer=""), False),
             ("an unknown letter name is refused", dict(base, letter="aleph"), False)]
    fd, tmp = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    try:
        for name, rec, want_ok in cases:
            io.open(tmp, "w", encoding="utf-8", newline="\n").write(
                json.dumps(rec, ensure_ascii=False) + "\n")
            g_, b_ = sig_load(Path(tmp))
            ck(name, (len(g_) == 1) if want_ok else (len(b_) == 1 and not g_),
               (len(g_), [x.get("_refused") for x in b_]))
        io.open(tmp, "w", encoding="utf-8", newline="\n").write("{not json\n")
        g_, b_ = sig_load(Path(tmp))
        ck("an unparseable line is refused and reported, not skipped",
           not g_ and len(b_) == 1 and "unparseable" in b_[0]["_refused"])
    finally:
        os.unlink(tmp)

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
        ck("a superseded signature is labelled on its own card",
           all(("superseded" in t2) for sid in PENDING_RESIGN
               if sid in [c_["span_id"] for c_ in CARDS]))
        ck("signed exemplars carry provenance when any exist",
           (not sig_exemplars("bet") and not sig_exemplars("gimel"))
           or ("signed exemplar" in t2 and "printed p" in t2))

    print("")
    print("%s: %d/%d checks" % ("PASS" if not f[0] else "FAIL", n[0] - f[0], n[0]))
    return f[0]


def spans_of(sid):
    return {x["span_id"]: x for x in D.build_set(include_sealed=True)}[sid]


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
