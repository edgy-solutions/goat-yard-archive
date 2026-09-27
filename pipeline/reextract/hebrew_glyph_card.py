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

Everything shown is real page pixels, upscaled NEAREST. No smoothing, ever: a resampled curl is an
invented curl, and the whole question on p217:n2 was whether a curl is present or ink-filled.
"""
import base64, io, re, sys, unicodedata

from PIL import Image, ImageDraw

import hebrew_aperture_diag as D
import note_region
import cv_footnote_presplit as ps

OUTHTML = D.DATA / "hebrew_glyph_cards_20260927.html"
INK = 160            # a pixel darker than this is ink
TARGET_BAND = 150    # every COMPARISON image is scaled so its text line is this tall
BAND_FRAC = 0.12     # a row belongs to the line band if its ink reaches this fraction of the peak

# WHY THE SCALE BASIS IS THE LINE BAND AND NOT THE INK BOUNDING BOX. The first build matched crops on
# ink-bbox height and produced a comparison that was not matched at all. Measured over the eleven
# crops these cards use: bbox heights run 47 to 90px while the line band runs 29 to 38px. The bbox is
# unstable because a tight crop on a closely set note picks up its NEIGHBOURS -- every crop here holds
# 2 to 5 text lines, and 10 of 12 have ink touching an edge. So a bbox-matched pair could differ by
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
    "bet": "a single flat base that projects to the RIGHT past the vertical stroke, making a clear "
           "right-angled foot; the top right is a closed corner.",
    "gimel": "no projecting base; the lower stroke is a short leg kicking out to the LEFT, and the "
             "letter is narrower than bet with an open bottom right.",
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
    "p138:n6": "being signed for the first time in the 2026-09-27 batch",
    "p596:n2": "being signed for the first time in the 2026-09-27 batch",
}

DISPUTED = {
    "p217:n2": [(1, 3)],        # mem vs pe -- barred as an exemplar for mem AND for pe
    "p423:n3": [(2, 3)],        # bet vs gimel -- same, and it has no crop either way
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
    dict(span_id="p423:n3", kind="letter", status="OPEN",
         question="Is glyph 3 of the second word bet or gimel?", word=2, pos=3,
         candidates=("bet", "gimel"),
         verdict="The signature has bet. The biblical form (Exodus 4:25, which the Latin gloss "
                 "translates) has gimel. If the print really has bet it is a compositor's reading "
                 "worth keeping, and this span becomes the best substitution probe in the set: "
                 "every arm reading gimel would be reading the verse, not the page."),
    dict(span_id="p726:n3", kind="pointing", status="OPEN",
         question="Does the PRINT carry vowel points?", word=None, pos=None, candidates=(),
         verdict="The signed truth is pointed. The prompt asserts on every span that Gill's Hebrew "
                 "is unpointed, and p200:n2's signature was wrong for exactly this reason. This is "
                 "the last pointed row in the table. Look BELOW the letters."),
    dict(span_id="p912:n2", kind="order", status="OPEN",
         question="Which word is physically the RIGHTMOST on the page?", word=None, pos=None,
         candidates=(),
         verdict="Hebrew reads right to left, so the rightmost word is the first word of the "
                 "signature. The Latin gloss runs 'in Jahacob, in Israel'. Gill's Hebrew and his "
                 "gloss do not always run in the same order, so the gloss does not settle it."),
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


def n_lines(im, frac=BAND_FRAC):
    """How many text lines the crop holds. Reported on the card because it explains `contains`."""
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
            return vis, "+/-%dpx" % (grow * k), True
    return win.convert("RGB"), "+/-%dpx" % (grow * tries), False


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

    Rule 2 is the one that matters. An exemplar drawn from a word that could itself contain either
    candidate would be evidence about the reader's expectation, not about the fount."""
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
"""


def build():
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
        h.append('<div class="lbl">the print</div><div class="row">')
        if blank:
            win, grew, found = find_ink(pg, r2 or r1)
            h.append('<div class="cell">%s<div class="cap"><b>NO CROP EXISTS.</b> The ratified span '
                     'box maps to pixels holding no ink, so nothing was ever shown to any reader '
                     'and there is no glyph to magnify. Above is the neighbourhood grown %s; the '
                     'red outline is where the box asked to look. %s</div></div>'
                     % (img_ctx(win, up=2), grew,
                        "Shown at 2x: the text lines here are about 31px native. Find the Hebrew, "
                        "then re-draw the box." if found
                        else "No ink found even at that range."))
            if found:
                # The letter question is not answerable from the ratified box, but it need not be
                # wholly blocked: the nearest text line in the recovery window can be magnified at the
                # same scale as the exemplars, so a verdict is at least possible. It is labelled
                # UNRATIFIED in the caption and in the image title, because a magnified line that is
                # NOT the ratified span is exactly the kind of plausible artifact that gets mistaken
                # for evidence -- and a signature taken from the wrong line would be a fifth
                # inherited property, arrived at by a nicer picture.
                h.append('<div class="cell">%s<div class="cap"><b>UNRATIFIED &mdash; not the signed '
                         'span.</b> The nearest text line found inside that window, magnified to the '
                         'same scale as the exemplars below. Use it to attempt the letter question '
                         'only if you can see that it is the right line; it carries no claim to be. '
                         'The box still has to be re-drawn either way.</div></div>'
                         % img_comp(win, unratified=True))
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
        if blank:
            h.append('<div class="warnbox">This span cannot be signed from the crop. The box has to '
                     'be re-drawn on the page first; the question above stays open until then.</div>')

        if c["kind"] == "letter":
            a, b = c["candidates"]
            for cand, partner in ((a, b), (b, a)):
                ex = exemplars(cand, partner, exclude=(c["span_id"],))
                h.append('<div class="lbl">%s &mdash; %s &mdash; %d exemplar(s) from the same '
                         'fount</div>' % (cand, LETTER[cand], len(ex)))
                h.append('<div class="feat">%s</div>' % FEATURES.get(cand, ""))
                if len(ex) < 3:
                    h.append('<div class="warnbox">Only %d unambiguous exemplar(s) of %s exist '
                             'in the whole signed set. This is a corpus limit, measured: the rule '
                             'excludes any word that also contains %s, and no span in the set '
                             'contains both letters, so the ideal exemplar &mdash; one impression '
                             'showing both candidates side by side &mdash; cannot be built from '
                             'these 21 signatures at all. Fewer than three is thin. The fix is not '
                             'code: point at any word on any page and name its letter, and that is '
                             'an exemplar of the same authority as a signature.</div>'
                             % (len(ex), cand, partner))
                h.append('<div class="row wrap">')
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
            h.append('<div class="feat">Look BELOW the letters. Unpointed text leaves a clean band '
                     'under the baseline; pointed text carries small dots and short strokes there. '
                     'p200:n2 was signed pointed and ruled unpointed, so a pointed-looking '
                     'signature is not evidence.</div>')
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

        elif c["kind"] == "order":
            wo = words(s["truth"])   # not `words`: that shadows the helper
            h.append('<div class="lbl">the two candidate orders</div>')
            h.append('<div class="row"><div class="cell"><div class="heb" dir="auto">%s</div>'
                     '<div class="cap">as signed: word 1 (rightmost) is <span class="heb" '
                     'dir="auto">%s</span></div></div><div class="cell"><div class="heb" '
                     'dir="auto">%s</div><div class="cap">the other order: word 1 (rightmost) '
                     'would be <span class="heb" dir="auto">%s</span></div></div></div>'
                     % (" ".join(wo), wo[0], " ".join(wo[::-1]), wo[-1]))
            h.append('<div class="feat">Read the A1 note image above right-to-left. Whichever word '
                     'sits furthest RIGHT is word 1. The span box holds only part of the phrase '
                     '(this is the span scored <code>clipped</code>), so use the note, not the span '
                     'crop.</div>')

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
            thin = len(exemplars(cand, {"pe": "mem", "gimel": "bet"}[cand])) < 3
            said = ("unambiguous exemplar(s) of %s" % cand) in t0
            ck("a thin %s comparison is never shown silently" % cand, said or not thin)
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
        # One magnified image on this page is NOT the ratified span. It must be labelled every time
        # it appears, in the caption and in the image title, or it becomes evidence by resemblance.
        nblank = sum(1 for c_ in CARDS
                     if (lambda x: x["span_box"] and not ink_bbox(
                         cut(x["page"], x["span_box"], D.PAD, x["column_bands"])[0] or
                         Image.new("L", (1, 1), 255)))(
                         {y["span_id"]: y for y in D.build_set(include_sealed=True)}[c_["span_id"]]))
        ck("every unratified magnification is labelled in caption and title",
           t.count("unratified") >= 2 * nblank, (t.count("unratified"), nblank))
        ck("no valley/bracket pointer reaches the output", "valley" not in t)

        print("")
        print("(5) verdict-only: no model reading reaches a signing surface")
        for arm in ("gpt-", "claude-", "gemini", "qwen", "glm-", "deepseek", "kimi", "grok",
                    "minimax", "mimo", "nemotron", "ling-", "step-", "abstain"):
            ck("no arm/read token '%s' in the page text" % arm, arm not in t)

    print("")
    print("%s: %d/%d checks" % ("PASS" if not f[0] else "FAIL", n[0] - f[0], n[0]))
    return f[0]


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
    elif cmd == "exemplars":
        for a, b in (("mem", "pe"), ("pe", "mem"), ("bet", "gimel"), ("gimel", "bet")):
            print("")
            print("%s (excluding any word containing %s):" % (a, b))
            for sid, s, _p, occ in exemplars(a, b):
                print("   %-10s %s   %s" % (sid, s["truth"], where(s["truth"], occ)))
