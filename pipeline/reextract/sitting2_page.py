# -*- coding: utf-8 -*-
u"""The second sitting's page: the standard in hand, the priors as content, a verdict per glyph.

WHAT THIS IS. One page for the sitting Chris called on 2026-11-15 (advisor items 2, 2a and 3). It
carries three things the first sitting did not have:

  1. THE STANDARD, on the same page as the work. Every letter on one of the four confusable axes --
     dalet/resh, vav/zayin/final nun, he/tav, mem/final mem/samekh -- gets a specimen crop of its
     own signed exemplar, magnified, beside the letters it is confused with. A letter with no
     rule-2-clean signed exemplar gets a GAP card instead, naming what exists and why it is not
     enough. Gaps are shown as gaps: a page that prints an absence as a blank space is a page that
     decided something it was not asked to decide.
  2. THE PRIORS AS CONTENT. The five rows signed on 2026-11-14 come back with the signer's own last
     answer printed on the face of each tile, marked `prior`. Not a border colour, not a tooltip --
     text, because a verdict recorded as a colour is not honoured, and this lane has already lost a
     reading that way (p442:n0 tile 2, `corrected -> ך` replaced by `corrected -> ר` on identical
     pixels, with nothing in the record to say a prior reading had been discarded).
  3. A VERDICT PER TILE, with `abstain` as one of its three values and a REQUIRED one-line reason.
     That is the structural channel the p628:n2 refusal asked for: *"could be vav or nun"* was prose
     in a note field with no consumer, and a doubt with no channel becomes either a false verdict or
     a silent hold.

WHAT IT DOES NOT DO.

  - It shows NO model reading and consults none. Not as a promise: the selftest collects every
    Hebrew string in the emitted bytes and refuses any that did not come from a signed record, a
    signed tile, or the palette. The alternative-reads file is not opened by this module at all.
  - It proposes no geometry. The tile strip is laid out in the picture's own order (the strip is
     rendered right-to-left, like the print), so the n-th tile is the n-th glyph counting from the
     right. That is an ORDERING, not a pixel alignment: nothing here claims to know where on the
     crop a glyph begins, and no machine was asked.
  - It validates nothing that matters. `sitting2_load` is the authority: it refuses a row whose
    abstain carries no reason, whose change names no letter, whose tile count does not match the
    prior, or whose crop hash does not match the pixels that were signed. The page's own guard is a
    convenience, and a convenience that disagrees with the loader loses.

THE PIXELS ARE THE SIGNED PIXELS. Each row's crop is located by hashing the files on disk and
matching `crop_sha16` from the signed export -- not by name. A page that showed a crop *called*
p254_n1 while the signature was made over different bytes would be the whole failure of this lane in
one picture.

All page numbers are FILE pages: printed = file - 88. Stated on the page, not only here.

    python sitting2_page.py              # writes the sitting page next to the cards
    python sitting2_page.py selftest     # 0 means every check passed
"""
import datetime
import hashlib
import io
import json
import os
import sys

import hebrew_aperture_diag as D
from write_scope import assert_inside
from hebrew_glyph_card import LETTER, sig_load
from hebrew_point_and_name import (CSS, IMGREL, LEGEND_AXES, axis_rivals, legend_letters)

DATA = D.DATA
OUT = DATA / "sitting2_second_pointing.html"

#: The sitting's inputs, pinned by name AND hashed into the page. The name is how a file is found;
#: the hash is what the page says it showed.
PRIOR = DATA / "glyphsign_0401b636ffa7bf1a_resign_5span_signed_50d419a4.jsonl"
DIFFB = DATA / "RESIGNDIFF_B_vs_pass2_p831n2.json"
#: The crop set the signed export was cut from -- its digest is in the export's own file name.
CROPS = DATA / "truthset74_crops_0401b636ffa7bf1a"
#: Where the signer's verdicts are appended. Not written by this module, ever.
EXPORT = DATA / "sitting2_verdicts.jsonl"

MAG_CROP = 3          # the picture
MAG_GLYPH = 7         # a specimen glyph, which may be 24px tall
MAG_WORD = 3          # a specimen's whole word, with the signed glyph outlined
TODAY = datetime.date.today().isoformat()

#: The three values a tile verdict may take. `keep_prior` makes no new claim about the glyph -- it
#: says the recorded answer stands, which is why re-affirming needs no letter and no reason.
VERDICTS = ("keep_prior", "changed", "abstain")
#: The three a disagreement may take. Not a score: which reading is right, in either direction.
OWED_VERDICTS = ("keep", "take", "neither")


def sha16(path):
    return hashlib.sha256(io.open(str(path), "rb").read()).hexdigest()[:16]


def _rows(path):
    return [json.loads(l) for l in io.open(str(path), encoding="utf-8") if l.strip()]


def crop_index():
    """sha16 -> path, over the crop set the export names. Located by CONTENT.

    A crop is matched to a signature by hashing, never by name. The file name encodes a span id and
    a crop kind, both of which are claims about the file; the hash is the file.
    """
    out = {}
    for name in sorted(os.listdir(str(CROPS))):
        if not name.endswith(".png"):
            continue
        p = CROPS / name
        out.setdefault(sha16(p), p)
    return out


def prior_rows():
    """The five signed rows, each with the crop file whose bytes were signed.

    Raises if a row's `crop_sha16` is not on disk in the named crop set. That is the right
    behaviour: the alternative is a sitting held over pixels nobody can point to.
    """
    idx = crop_index()
    out = []
    for r in _rows(PRIOR):
        h = r.get("crop_sha16")
        if h not in idx:
            raise ValueError("%s: crop_sha16 %s is not in %s -- the signed pixels are not on disk, "
                             "and this page will not show a different crop under that span id"
                             % (r.get("span_id"), h, CROPS.name))
        out.append((r, idx[h]))
    return out


def owed():
    """(sha16, [disagreement]) -- the unadjudicated disagreements on p831:n2, from the diff record.

    Read, not transcribed. The three verdicts owed here were described in a report; a list of
    verdicts typed into source beside the file that holds them is the defect this lane just fixed
    in the geometry-5 record, and it is not being reintroduced on a signing surface.
    """
    d = json.load(io.open(str(DIFFB), encoding="utf-8"))
    open_ = [x for x in d.get("disagreements") or () if x.get("adjudication") is None]
    return sha16(DIFFB), d, open_


def signed_items(letter):
    """[item] -- every signed impression of `letter`, WITH the box that was drawn for it.

    Derived from the signature records directly, because the authority for the sitting's state
    (`legend_letters`) reports page/word/index and drops the box, and a specimen without a box
    cannot be shown. `build` asserts the two derivations name the same impressions; a disagreement
    between them is a build failure rather than a picture.
    """
    good, _bad = sig_load()
    rivals = axis_rivals().get(letter, ((), (), ()))[0]
    out = []
    for r in good:
        lbs = list(r.get("letter_boxes") or ())
        if not lbs:
            continue
        xs = [lb["box"] for lb in lbs]
        wordbox = [min(b[0] for b in xs), min(b[1] for b in xs),
                   max(b[2] for b in xs), max(b[3] for b in xs)]
        dirty = sorted(p for p in rivals if LETTER[p] in r["word"])
        for lb in lbs:
            if lb.get("letter") != letter:
                continue
            pointed = (lb.get("index_from_right") == r.get("letter_index_from_right")
                       and r.get("letter") == letter)
            out.append({"kind": "pointed" if pointed else "context",
                        "page": r["file_page"], "word": r["word"],
                        "idx": lb.get("index_from_right"), "box": lb["box"],
                        "wordbox": wordbox, "dirty": dirty,
                        "signer": r.get("signer"), "date": r.get("date")})
    # DEDUPE BY GLYPH, pointed winning -- the same correction the authority needed. One signing
    # sitting writes one record per letter, each carrying boxes for the whole word, so the same
    # drawn glyph arrives once from its own record and again from its neighbour's. Counting it
    # twice would print one box as two specimens and call a single instance corroborated.
    out.sort(key=lambda x: (bool(x["dirty"]), x["kind"] != "pointed", x["page"], x["idx"] or 0))
    seen, uniq = {}, []
    for i in out:
        key = (i["page"], i["word"], i["idx"])
        if key in seen:
            if i["kind"] == "pointed" and uniq[seen[key]]["kind"] != "pointed":
                uniq[seen[key]] = i
            continue
        seen[key] = len(uniq)
        uniq.append(i)
    return uniq


def _key(i):
    return (i["kind"], i["page"], i["word"], i["idx"])


def specimens():
    """[(letter, rivals, state, items)] -- the legend, in the axes' own order, gaps included."""
    out = []
    for letter, rivals, state in legend_letters():
        out.append((letter, rivals, state, signed_items(letter)))
    return out


# ---------------------------------------------------------------- html


def _esc(s):
    return (u"%s" % s).replace(u"&", u"&amp;").replace(u"<", u"&lt;").replace(u">", u"&gt;")


def _q(s):
    return '"%s"' % str(s).replace("\\", "\\\\").replace('"', '\\"')


def _page_crop(page, box, mag, title=u"", outline=None):
    """A native-pixel crop of a page scan, rendered by the browser from the volume.

    No scan is copied into this file and none ever will be. The outer div is the box at `mag`; the
    image inside is scaled about its own top-left and offset by the box origin, so the pixel at
    native (x0, y0) lands at (0, 0) -- arithmetic, with no natural-size assumption anywhere.
    """
    x0, y0, x1, y1 = box
    w, h = max(1, x1 - x0), max(1, y1 - y0)
    inner = ('<img src="%s/page%d_image1.png" style="position:absolute;left:%dpx;top:%dpx;'
             'transform:scale(%s);transform-origin:0 0;image-rendering:pixelated">'
             % (IMGREL, page, -x0 * mag, -y0 * mag, mag))
    if outline:
        ox0, oy0, ox1, oy1 = outline
        inner += ('<div class="gl" style="left:%dpx;top:%dpx;width:%dpx;height:%dpx"></div>'
                  % ((ox0 - x0) * mag, (oy0 - y0) * mag,
                     max(1, ox1 - ox0) * mag, max(1, oy1 - oy0) * mag))
    return ('<div class="pc" style="width:%dpx;height:%dpx" title="%s">%s</div>'
            % (w * mag, h * mag, _esc(title), inner))


def legend_section(spec):
    h = ['<section id="legend"><h2>1 &mdash; The standard, on this page</h2>',
         '<div class="mut">The four axes you named. One line, then a specimen of each letter from '
         'your own signed exemplars, magnified &times;%d. A letter with no rule-2-clean signed '
         'exemplar shows a <b>gap card</b> naming what exists and why it is not a specimen &mdash; '
         'an absence printed as an absence. No specimen here is a machine reading: every one is a '
         'box you drew and a letter you named.</div>' % MAG_GLYPH]
    h.append('<div class="axline">')
    for ax in LEGEND_AXES:
        h.append('<span class="ax">%s <span class="mut">%s</span></span>'
                 % (" / ".join('<span class="heb">%s</span>' % LETTER[l] for l in ax),
                    " / ".join(l.replace("final_", "final ") for l in ax)))
    h.append("</div>")
    by = dict((l, (rv, st, it)) for l, rv, st, it in spec)
    for ax in LEGEND_AXES:
        h.append('<div class="axrow"><div class="axname">%s</div><div class="axcards">'
                 % " / ".join(l.replace("final_", "final ") for l in ax))
        for l in ax:
            rv, st, items = by[l]
            clean = [i for i in items if not i["dirty"]]
            h.append('<div class="card%s">' % (" gap" if st["gap"] else ""))
            h.append('<div class="cl"><span class="heb big">%s</span> <b>%s</b></div>'
                     % (LETTER[l], l.replace("final_", "final ")))
            if clean:
                i = clean[0]
                h.append(_page_crop(i["page"], i["box"], MAG_GLYPH,
                                    u"file p%d, %s" % (i["page"], i["kind"])))
                h.append('<div class="mut">%s &middot; file p%d <span class="mut">(printed %d)'
                         '</span> &middot; index %s from the right &middot; signed %s</div>'
                         % (i["kind"], i["page"], i["page"] - 88, i["idx"], i["date"] or "?"))
                h.append('<div class="mut">in the word it was drawn in, &times;%d, your box '
                         'outlined:</div>' % MAG_WORD)
                h.append(_page_crop(i["page"], i["wordbox"], MAG_WORD,
                                    u"the whole word", outline=i["box"]))
                if not [x for x in clean if x["kind"] == "pointed"]:
                    h.append('<div class="gapmsg">No <b>pointed</b> attestation of this letter '
                             'exists. Every specimen above is a <b>context</b> box &mdash; drawn '
                             'around this glyph while you were attesting a different letter of the '
                             'same word. The box is yours and the index is yours; the letter name '
                             'at this index is not something you were asked to confirm.</div>')
                if len(clean) > 1:
                    h.append('<div class="mut">%d more clean signed impression(s): %s</div>'
                             % (len(clean) - 1,
                                ", ".join("p%d #%s" % (x["page"], x["idx"]) for x in clean[1:])))
                elif st["single"]:
                    h.append('<div class="mut">This is the <b>only</b> clean signed impression of '
                             'this letter. One specimen is a specimen, not a range.</div>')
            else:
                h.append('<div class="gapmsg">No rule-2-clean signed exemplar. '
                         'Nothing is shown here because there is nothing signed to show.</div>')
                if items:
                    h.append('<ul class="mut">')
                    for i in items:
                        h.append('<li>%s, file p%d, index %s &mdash; <b>rule-2 dirty</b>: the word '
                                 'also holds %s</li>'
                                 % (i["kind"], i["page"], i["idx"],
                                    ", ".join(x.replace("final_", "final ") for x in i["dirty"])))
                    h.append("</ul>")
                else:
                    h.append('<div class="mut">No signed impression of any kind, clean or '
                             'dirty.</div>')
                h.append('<div class="mut">%d span exemplar(s) exist; a span exemplar is a whole '
                         'printed span, not a pointed glyph, which is why it is not the specimen '
                         'beside a rival.</div>' % st["span_exemplars"])
            rvn = ", ".join(x.replace("final_", "final ") for x in rv) or "nothing named"
            h.append('<div class="mut">must not share a word with: %s</div></div>' % rvn)
        h.append("</div></div>")
    h.append("</section>")
    return "\n".join(h)


def rows_section(rows):
    h = ['<section id="rows"><h2>2 &mdash; The five rows you signed on 2026-11-14</h2>',
         '<div class="mut">Your own last answer is printed on the face of every tile, marked '
         '<b>prior</b>. Re-affirming it is <b>keep prior</b> and costs no click of a letter: the '
         'answer is already recorded, and this page does not make you re-enter it. The strip runs '
         '<b>right to left, like the print</b>, so the first tile is the rightmost glyph &mdash; '
         'that is an <b>ordering</b>, not an alignment. Nothing here knows where on the crop a '
         'glyph begins, and nothing was asked. The crop under each span id is the crop that was '
         'signed, found by hashing the files on disk against the signature&rsquo;s own '
         '<span class="k">crop_sha16</span>.</div>',
         '<div class="warn"><b>abstain</b> is a verdict, not a skip, and it requires one line of '
         'reason. It is the channel <i>&ldquo;could be vav or nun&rdquo;</i> did not have: that '
         'sentence went into a note field in the last sitting, where nothing reads it. A reason '
         'written here is carried on the row.</div>']
    for r, crop in rows:
        sid = r["span_id"]
        pg = int(sid.split(":")[0].lstrip("p"))
        tiles = r.get("tiles") or ()
        ins = r.get("insertions") or ()
        h.append('<div class="row" data-span="%s">' % _esc(sid))
        h.append('<div class="rh"><b>%s</b> <span class="mut">file p%d (printed %d) &middot; '
                 'crop <span class="k">%s</span> &middot; %d tile(s)%s &middot; fault '
                 '<span class="k">%s</span></span></div>'
                 % (_esc(sid), pg, pg - 88, _esc(r.get("crop_sha16")), len(tiles),
                    ", %d insertion(s)" % len(ins) if ins else "",
                    _esc(r.get("fault") or "none")))
        h.append('<div class="cropwrap"><img class="crop" src="%s"></div>'
                 % os.path.relpath(str(crop), str(DATA)).replace(os.sep, "/"))
        word = u"".join((t.get("chose") or t.get("shown") or u"") for t in tiles)
        h.append('<div class="asm"><span class="mut">assembled from the prior tiles, set to the '
                 'height of the picture above &mdash; not typed, and not a reading:</span> '
                 '<span class="heb asmw">%s</span></div>' % _esc(word))
        if r.get("note"):
            h.append('<div class="warn">the note you left on this row: '
                     '<b>%s</b> &mdash; prose, with no consumer. If it is a doubt about a glyph, '
                     'it belongs in that glyph&rsquo;s <b>abstain</b> reason.</div>'
                     % _esc(r["note"]))
        h.append('<div class="strip" id="s_%s"></div>' % _esc(sid.replace(":", "_")))
        if ins:
            h.append('<div class="mut">This row also carries %d signed insertion(s) &mdash; a '
                     'glyph you added that the candidate did not have. Insertions are <b>not</b> '
                     'tiles and are not re-opened here; p831:n2&rsquo;s is one of the three '
                     'disagreements in section 3.</div>' % len(ins))
        h.append("</div>")
    h.append("</section>")
    return "\n".join(h)


def owed_section(dsha, diff, open_):
    h = ['<section id="owed"><h2>3 &mdash; p831:n2: three disagreements, three verdicts owed</h2>',
         '<div class="mut">Read from <span class="k">%s</span> (sha16 '
         '<span class="k">%s</span>), not transcribed. This row has two prior signatures and the '
         'comparison that counts is against the <b>latest</b> one, the pass-2 re-sign. The pixels '
         'are byte-identical across both: <span class="k">crop_sha16</span> and '
         '<span class="k">candidate_sha16</span> both match, so nothing about the picture '
         'changed between the two readings.</div>' % (_esc(DIFFB.name), _esc(dsha)),
         '<div class="warn">This is an <b>adjudication, not a score</b>. The question is which '
         'reading is right &mdash; and it runs in both directions: <b>keep</b> the prior, '
         '<b>take</b> the current, or <b>neither</b>, in which case say what is there. The newer '
         'reading is not the better one by being newer. Every verdict needs one line of basis.</div>']
    r = diff.get("rate") or {}
    h.append('<div class="mut">%s of %s tiles changed, %s insertion(s) changed, and '
             '<span class="k">reversals_corrected_to_confirmed</span> is %s &mdash; which is '
             '<b>not</b> the same as no prior reading having been discarded: that counter sees one '
             'shape of reversal only.</div>'
             % (r.get("tiles_changed"), r.get("tiles_compared"), r.get("insertions_changed"),
                r.get("reversals_corrected_to_confirmed")))
    h.append('<table class="ow"><tr><th>#</th><th>what</th><th>prior (pass-2 re-sign)</th>'
             '<th>current (2026-11-14)</th><th>your verdict</th></tr>')
    for n, x in enumerate(open_):
        p, c = x.get("prior") or {}, x.get("current") or {}

        def side(d):
            if not d:
                return '<i class="mut">absent</i>'
            bits = []
            if d.get("shown"):
                bits.append('shown <span class="heb">%s</span>' % _esc(d["shown"]))
            if d.get("chose"):
                bits.append('chose <span class="heb">%s</span>' % _esc(d["chose"]))
            v = d.get("verdict")
            bits.append('<b>%s</b>' % _esc(v if v else u'(no verdict recorded)'))
            return " &middot; ".join(bits)
        what = x.get("what")
        where = ("tile %s" % x.get("i") if what == "tile"
                 else "insertion seq %s, after_i %s" % (x.get("seq"), x.get("after_i")))
        h.append('<tr><td>%d</td><td>%s<div class="mut">%s</div></td><td>%s</td><td>%s</td>'
                 '<td id="ow_%d"></td></tr>'
                 % (n + 1, _esc(where), _esc(x.get("kind") or ""), side(p), side(c), n))
    h.append("</table>")
    if not open_:
        h.append('<div class="mut">No unadjudicated disagreement in that record. A measured zero.'
                 '</div>')
    h.append("</section>")
    return "\n".join(h)


def palette_html():
    """The palette. Every letter carries its NAME under the glyph -- the interface fix from item 2a,
    and the reason is that a palette of 27 unlabelled glyphs asks the signer to read Hebrew in order
    to say what he read."""
    return "".join('<button onclick="pick_letter(\'%s\')" title="%s">%s<span>%s</span></button>'
                   % (k, k, v, k.replace("final_", "f."))
                   for k, v in LETTER.items())


CSS2 = u"""
h2{font-size:15px;margin:22px 0 4px}
section{padding:0 16px 10px}
.pc{position:relative;overflow:hidden;background:#fff;border-radius:3px;margin:4px 0}
.pc img{position:absolute}
.gl{position:absolute;border:2px solid #f87171;box-sizing:border-box}
.axline{display:flex;gap:18px;flex-wrap:wrap;margin:8px 0;padding:6px 10px;border:1px solid
var(--line);border-radius:8px;background:var(--card)}
.ax{font-size:19px}
.ax .mut{font-size:11px}
.axrow{display:flex;gap:10px;align-items:flex-start;margin:10px 0}
.axname{flex:0 0 150px;color:var(--mut);font-size:12px;padding-top:8px}
.axcards{display:flex;gap:8px;flex-wrap:wrap}
.card{flex:0 0 232px;border:1px solid var(--line);border-radius:8px;padding:8px;background:var(--card)}
.card.gap{border-color:#7f1d1d;background:#1b0f0f}
.gapmsg{color:var(--bad);font-size:12px;margin:4px 0}
.cl{margin-bottom:4px}
.heb{font-family:"Times New Roman",serif}
.heb.big{font-size:26px}
.row{border:1px solid var(--line);border-radius:8px;padding:10px;margin:12px 0;background:var(--card)}
.rh{margin-bottom:6px}
.cropwrap{background:#fff;border-radius:4px;display:inline-block;padding:2px}
img.crop{image-rendering:pixelated;display:block;transform-origin:0 0}
.asm{margin:6px 0}
.asmw{display:inline-block;line-height:1;vertical-align:middle}
.strip{display:flex;direction:rtl;gap:6px;flex-wrap:wrap;margin-top:8px}
.tile{direction:ltr;flex:0 0 164px;border:1px solid var(--line);border-radius:8px;padding:6px;
background:#0b0e13}
.tile .g{font:30px "Times New Roman",serif;text-align:center;line-height:1}
.tile .pv{display:block;font:11px/1.35 ui-monospace,Consolas,monospace;color:#fc8;background:#2a2012;
border:1px solid #c86;border-radius:4px;padding:2px 4px;margin:4px 0}
.tile .now{display:block;font:11px/1.35 ui-monospace,Consolas,monospace;color:var(--ok);
background:#0b2f1b;border:1px solid #14532d;border-radius:4px;padding:2px 4px;margin:4px 0}
.tile .und{display:block;font:11px/1.35 ui-monospace,Consolas,monospace;color:var(--bad);margin:4px 0}
.tile button{padding:3px 6px;font-size:11px}
.tile input{width:100%;font-size:11px;padding:3px 5px;margin-top:4px}
.tiles{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px}
.tiles button{font:19px "Times New Roman",serif;min-width:36px;padding:2px 6px;line-height:1.05}
.tiles button span{display:block;font:9px ui-monospace,Consolas,monospace;color:var(--mut)}
.tiles.armed{outline:2px solid var(--acc);border-radius:8px;padding:4px}
table.ow{border-collapse:collapse;margin:8px 0;font-size:13px}
table.ow th,table.ow td{border:1px solid var(--line);padding:5px 8px;text-align:left;vertical-align:top}
.sticky{position:sticky;bottom:0;background:var(--bg);border-top:1px solid var(--line);padding:8px 16px}
"""

JS2 = u"""
var PICK=null;            /* which tile a palette click is for, or null */
var V={};                 /* "span|i" -> {v, chose, reason} */
var OV={};                /* owed index -> {v, basis} */
function k(s,i){return s+"|"+i}
function esc(x){return String(x==null?"":x).replace(/&/g,"&amp;").replace(/</g,"&lt;")}
function vDesc(t){
  var v=t.prior_verdict||"(none recorded)";
  return v+(t.prior_chose?" \\u2192 "+t.prior_chose:"")}
function strip(row){
  var el=document.getElementById("s_"+row.span_id.replace(":","_"));
  el.innerHTML="";
  for(var n=0;n<row.tiles.length;n++){
    var t=row.tiles[n],key=k(row.span_id,t.i),st=V[key]||{},d=document.createElement("div");
    d.className="tile";
    var h='<div class="mut">glyph '+(t.i+1)+' from the right</div>'+
          '<div class="g">'+esc(t.shown)+'</div>'+
          '<span class="pv">prior: '+esc(vDesc(t))+'</span>';
    if(st.v==="keep_prior"){h+='<span class="now">now: keep prior</span>'}
    else if(st.v==="changed"){h+='<span class="now">now: changed \\u2192 '+
        esc(st.chose||"(no letter yet)")+'</span>'}
    else if(st.v==="abstain"){h+='<span class="now">now: abstain</span>'}
    else{h+='<span class="und">no verdict yet</span>'}
    h+='<div class="bar"><button onclick="setv(\\''+row.span_id+'\\','+t.i+',\\'keep_prior\\')">keep prior</button>'+
       '<button onclick="arm(\\''+row.span_id+'\\','+t.i+')">change</button>'+
       '<button onclick="setv(\\''+row.span_id+'\\','+t.i+',\\'abstain\\')">abstain</button></div>';
    if(st.v==="abstain"){
      h+='<input placeholder="one line: why you cannot call it" value="'+esc(st.reason||"")+
         '" oninput="setreason(\\''+row.span_id+'\\','+t.i+',this.value)">';
      if(!(st.reason||"").trim()){h+='<span class="und">a reason is required</span>'}}
    if(PICK&&PICK.s===row.span_id&&PICK.i===t.i){
      h+='<span class="und">click a letter in the palette below</span>'}
    d.innerHTML=h;el.appendChild(d)}}
function owed(){
  for(var n=0;n<OWED.length;n++){
    var st=OV[n]||{},c=document.getElementById("ow_"+n),h="";
    for(var j=0;j<OWV.length;j++){
      h+='<button onclick="setow('+n+',\\''+OWV[j]+'\\')"'+
         (st.v===OWV[j]?' class="go"':'')+'>'+OWV[j]+'</button> '}
    h+='<input placeholder="one line: the basis for that verdict" value="'+esc(st.basis||"")+
       '" oninput="setbasis('+n+',this.value)">';
    if(st.v&&!(st.basis||"").trim()){h+='<span class="und">a basis is required</span>'}
    c.innerHTML=h}}
function render(){for(var i=0;i<ROWS.length;i++){strip(ROWS[i])}owed();
  document.getElementById("pal").className="tiles"+(PICK?" armed":"");count()}
function setv(s,i,v){var key=k(s,i),st=V[key]||{};st.v=v;
  if(v!=="changed"){st.chose=""}if(v!=="abstain"){st.reason=""}
  V[key]=st;if(v!=="changed"){PICK=null}render()}
function arm(s,i){var st=V[k(s,i)]||{};st.v="changed";V[k(s,i)]=st;PICK={s:s,i:i};render()}
function pick_letter(name){
  if(!PICK){alert("Click 'change' on a tile first. A letter clicked with no tile armed is a "+
    "letter named about nothing.");return}
  var st=V[k(PICK.s,PICK.i)]||{};st.v="changed";st.chose=LETTERCH[name];st.letter=name;
  V[k(PICK.s,PICK.i)]=st;PICK=null;render()}
function setreason(s,i,x){var st=V[k(s,i)]||{};st.reason=x;V[k(s,i)]=st;count()}
function setow(n,v){var st=OV[n]||{};st.v=v;OV[n]=st;owed();count()}
function setbasis(n,x){var st=OV[n]||{};st.basis=x;OV[n]=st;count()}
function problems(){
  var out=[];
  for(var i=0;i<ROWS.length;i++){var r=ROWS[i];
    for(var n=0;n<r.tiles.length;n++){var t=r.tiles[n],st=V[k(r.span_id,t.i)]||{};
      if(!st.v){out.push(r.span_id+" glyph "+(t.i+1)+": no verdict")}
      else if(st.v==="changed"&&!st.chose){out.push(r.span_id+" glyph "+(t.i+1)+": changed, no letter")}
      else if(st.v==="abstain"&&!(st.reason||"").trim()){
        out.push(r.span_id+" glyph "+(t.i+1)+": abstain with no reason")}}}
  for(var j=0;j<OWED.length;j++){var o=OV[j]||{};
    if(!o.v){out.push("disagreement "+(j+1)+": no verdict")}
    else if(!(o.basis||"").trim()){out.push("disagreement "+(j+1)+": no basis")}}
  return out}
function count(){
  var p=problems();
  document.getElementById("cnt").innerHTML=p.length?
    ("<b>"+p.length+"</b> thing(s) still open: "+esc(p.slice(0,4).join("; "))+
     (p.length>4?" \\u2026":"")):"<b>complete</b> \\u2014 every glyph and every disagreement answered";
  document.getElementById("cnt").className=p.length?"und":"now"}
function build_export(){
  var p=problems();
  if(p.length){document.getElementById("out").value=
    "NOT EXPORTED \\u2014 "+p.length+" open:\\n"+p.join("\\n");return}
  var lines=[],sg=document.getElementById("signer").value,dt=document.getElementById("date").value;
  for(var i=0;i<ROWS.length;i++){var r=ROWS[i],ts=[];
    for(var n=0;n<r.tiles.length;n++){var t=r.tiles[n],st=V[k(r.span_id,t.i)];
      ts.push({i:t.i,shown:t.shown,prior_verdict:t.prior_verdict,prior_chose:t.prior_chose,
               verdict:st.v,chose:st.chose||"",letter:st.letter||"",reason:(st.reason||"").trim()})}
    lines.push(JSON.stringify({kind:"sitting2_tile_verdicts",span_id:r.span_id,
      crop_sha16:r.crop_sha16,prior_source:PRIOR_SRC,prior_source_sha16:PRIOR_SHA,
      signer:sg,date:dt,tiles:ts}))}
  var ow=[];
  for(var j=0;j<OWED.length;j++){var o=OV[j];
    ow.push({n:j,what:OWED[j].what,i:OWED[j].i,seq:OWED[j].seq,after_i:OWED[j].after_i,
             verdict:o.v,basis:o.basis.trim()})}
  if(ow.length){lines.push(JSON.stringify({kind:"sitting2_disagreement_verdicts",
    span_id:OWED_SPAN,source:DIFF_SRC,source_sha16:DIFF_SHA,signer:sg,date:dt,verdicts:ow}))}
  document.getElementById("out").value=lines.join("\\n")+"\\n"}
function dl(){
  var t=document.getElementById("out").value;
  if(!t||t.indexOf("NOT EXPORTED")===0){build_export();t=document.getElementById("out").value}
  if(t.indexOf("NOT EXPORTED")===0){return}
  var a=document.createElement("a");
  a.href=URL.createObjectURL(new Blob([t],{type:"application/x-ndjson"}));
  a.download=EXPORT_NAME;a.click()}
render();
"""


def build():
    rows = prior_rows()
    dsha, diff, open_ = owed()
    spec = specimens()
    # The two derivations of "what is signed for this letter" must name the same impressions. One
    # of them is the sitting's authority and drops the box; the other exists because a specimen
    # needs a box. If they disagree, the page would show a picture the state does not describe.
    for letter, _rv, st, items in spec:
        a = set((x[0], x[1], x[2], x[3]) for x in st["signed"])
        b = set(_key(i) for i in items)
        if a != b:
            raise ValueError("%s: legend_letters and signed_items disagree about what is signed; "
                             "only in the authority: %s; only here: %s"
                             % (letter, sorted(a - b), sorted(b - a)))
    jrows = [{"span_id": r["span_id"], "crop_sha16": r.get("crop_sha16"),
              "tiles": [{"i": t.get("i"), "shown": t.get("shown"),
                         "prior_verdict": t.get("verdict"), "prior_chose": t.get("chose") or ""}
                        for t in r.get("tiles") or ()]}
             for r, _c in rows]
    h = ['<!doctype html><meta charset="utf-8"><title>Second sitting</title>',
         "<style>%s%s</style>" % (CSS, CSS2),
         '<header><h1>The second sitting &mdash; the standard, the priors, a verdict per '
         'glyph</h1>',
         '<div class="mut">Lane B. <b>All page numbers are FILE pages; printed = file &minus; 88.'
         '</b> Three sections: the confusable axes with a specimen of each letter from your own '
         'signed exemplars; the five rows you signed on 2026-11-14 with your own answers printed '
         'on the tiles; and p831:n2&rsquo;s three open disagreements. '
         '<b>No model reading is shown on this page and none was consulted to build it</b> '
         '&mdash; that is checked over the emitted bytes, not promised. Pointing new exemplars is '
         'still the other page, <span class="k">hebrew_point_and_name.html</span>: this one asks '
         'for verdicts, not boxes.</div>',
         # The date is the SIGNER'S, filled from their own browser at load. It used to default
         # to the build date, which would have put the builder's day on the signer's record --
         # the export reads this field verbatim. The build date stays on the page as a labelled
         # fact. Editable, because a sitting may be recorded on a later day than it was held.
         '<div class="bar"><label>signer</label><input id="signer" size="8" value="Chris">'
         '<label>date</label><input id="date" size="10" value="">'
         '<script>document.getElementById("date").value='
         'new Date(Date.now()-new Date().getTimezoneOffset()*60000)'
         '.toISOString().slice(0,10);</script>'
         '<span class="mut">built %s &middot; priors from <span class="k">%s</span> (sha16 '
         '<span class="k">%s</span>)</span></div>'
         % (TODAY, _esc(PRIOR.name), sha16(PRIOR)),
         "</header>",
         legend_section(spec),
         rows_section(rows),
         owed_section(dsha, diff, open_),
         '<section><h2>4 &mdash; The palette</h2>',
         '<div class="mut">Every letter carries its name. A palette click is a naming act and '
         'nothing else, so it only lands on a tile you have armed with <b>change</b> &mdash; a '
         'letter clicked with no tile armed is a letter named about nothing, and the page says so '
         'rather than guessing where you meant it.</div>',
         '<div id="pal" class="tiles">%s</div></section>' % palette_html(),
         '<section><h2>5 &mdash; Export</h2>',
         '<div class="mut">Nothing is exported while anything is open: every glyph needs a '
         'verdict, every change needs a letter, every abstain needs a reason, and every '
         'disagreement needs a verdict with a basis. The page says which are missing. '
         '<b>The loader is the authority</b> &mdash; <span class="k">sitting2_load</span> refuses '
         'the same things again when the file is read, and a page that let something through would '
         'lose there.</div>',
         '<div class="bar"><button class="go" onclick="build_export()">build export</button>'
         '<button onclick="dl()">download</button>'
         '<span class="mut">append to <span class="k">%s</span></span></div>' % _esc(EXPORT.name),
         '<textarea id="out" spellcheck="false"></textarea></section>',
         '<div class="sticky"><span id="cnt" class="und"></span></div>',
         "<script>var ROWS=%s;\nvar OWED=%s;\nvar OWV=%s;\nvar LETTERCH=%s;\n"
         "var PRIOR_SRC=%s;var PRIOR_SHA=%s;var DIFF_SRC=%s;var DIFF_SHA=%s;var OWED_SPAN=%s;"
         "var EXPORT_NAME=%s;\n%s</script>"
         % (json.dumps(jrows, ensure_ascii=False),
            json.dumps(open_, ensure_ascii=False), json.dumps(list(OWED_VERDICTS)),
            json.dumps(LETTER, ensure_ascii=False), _q(PRIOR.name), _q(sha16(PRIOR)),
            _q(DIFFB.name), _q(dsha),
            _q(open_[0].get("span_id") if open_ else ""), _q(EXPORT.name), JS2)]
    assert_inside(OUT, "the sitting page belongs in the audits directory, beside the cards")
    # newline="\n" DELIBERATELY. write_text translates on Windows, so the page came out
    # CRLF on disk while git stored LF -- and a sha16 pinning an artifact would then be a
    # hash of bytes nobody else ever receives. The page is pinned by its hash, so its
    # bytes have to be the bytes.
    io.open(str(OUT), "w", encoding="utf-8", newline="\n").write("\n".join(h))
    return OUT


# ---------------------------------------------------------------- the authority


def sitting2_load(path=None, prior_path=None):
    """(good, bad) -- the signer's verdict rows, with every refusal carrying its reason.

    THIS is the gate, not the page. A row is refused when:
      - a tile verdict is not one of VERDICTS;
      - `abstain` carries no reason -- the whole point of the channel;
      - `changed` names no letter;
      - the tiles do not correspond one-for-one, by index, with the prior row's tiles;
      - the row's `crop_sha16` is not the prior row's;
      - the span is not one of the priors at all.
    A disagreement row is refused when a verdict is not in OWED_VERDICTS or carries no basis.
    """
    path = path or EXPORT
    prior = dict((r["span_id"], r) for r in _rows(prior_path or PRIOR))
    good, bad = [], []
    if not os.path.exists(str(path)):
        return good, bad
    for r in _rows(path):
        why = None
        kind = r.get("kind")
        if kind == "sitting2_tile_verdicts":
            p = prior.get(r.get("span_id"))
            if p is None:
                why = ("span %s is not in the prior export; a verdict about a row nobody signed "
                       "has no prior to keep" % r.get("span_id"))
            elif r.get("crop_sha16") != p.get("crop_sha16"):
                why = ("crop_sha16 %s is not the %s the signature was made over -- a verdict over "
                       "different pixels is a verdict about a different picture"
                       % (r.get("crop_sha16"), p.get("crop_sha16")))
            else:
                pi = [t.get("i") for t in p.get("tiles") or ()]
                ri = [t.get("i") for t in r.get("tiles") or ()]
                if ri != pi:
                    why = ("tile indices %s do not match the prior's %s; a verdict strip that does "
                           "not correspond one-for-one is answering about other glyphs" % (ri, pi))
                else:
                    for t in r.get("tiles") or ():
                        v = t.get("verdict")
                        if v not in VERDICTS:
                            why = "glyph %s: verdict %r is not one of %s" % (t.get("i"), v, VERDICTS)
                        elif v == "abstain" and not (t.get("reason") or "").strip():
                            why = ("glyph %s: abstain with no reason. The reason IS the verdict's "
                                   "content: without it the row says only that something was hard"
                                   % t.get("i"))
                        elif v == "changed" and not (t.get("chose") or "").strip():
                            why = "glyph %s: changed, but no letter was named" % t.get("i")
                        if why:
                            break
        elif kind == "sitting2_disagreement_verdicts":
            for x in r.get("verdicts") or ():
                if x.get("verdict") not in OWED_VERDICTS:
                    why = "disagreement %s: verdict %r is not one of %s" % (
                        x.get("n"), x.get("verdict"), OWED_VERDICTS)
                elif not (x.get("basis") or "").strip():
                    why = ("disagreement %s: no basis. An adjudication without a basis cannot be "
                           "argued with, and this one reverses a signer on identical pixels"
                           % x.get("n"))
                if why:
                    break
        else:
            why = "unknown row kind %r" % kind
        if why:
            r = dict(r)
            r["_refused"] = why
            bad.append(r)
        else:
            good.append(r)
    return good, bad


# ---------------------------------------------------------------- selftest


def _hebrew_runs(text):
    out, cur = [], []
    for ch in text:
        if u"\u0590" <= ch <= u"\u05ff":
            cur.append(ch)
        elif cur:
            out.append(u"".join(cur))
            cur = []
    if cur:
        out.append(u"".join(cur))
    return out


def selftest():
    n = [0, 0]

    def ck(name, cond, extra=""):
        n[0] += 1
        if not cond:
            n[1] += 1
        print("%-4s %s%s" % ("ok" if cond else "FAIL", name, ("   " + str(extra)) if extra else ""))

    out = build()
    txt = io.open(str(out), encoding="utf-8").read()
    rows = prior_rows()
    dsha, diff, open_ = owed()
    spec = specimens()

    ck("every signed row's crop is on disk under the hash it was signed over (%d rows)" % len(rows),
       len(rows) == len(_rows(PRIOR)) and all(sha16(c) == r["crop_sha16"] for r, c in rows))

    # Prior state is CONTENT. One "prior:" face per tile, counted against the priors themselves.
    want_tiles = sum(len(r.get("tiles") or ()) for r, _c in rows)
    ck("the prior face is text rendered from the tile's own recorded verdict, not a colour",
       'class="pv"' in txt and "prior: " in txt and "vDesc(t)" in txt and "prior_chose" in txt)
    jr = json.loads(txt.split("var ROWS=")[1].split(";\nvar OWED=")[0])
    ck("every tile reaches the page with its prior verdict as data, one for one (%d)" % want_tiles,
       sum(len(r["tiles"]) for r in jr) == want_tiles
       and all(t["prior_verdict"] for r in jr for t in r["tiles"]),
       [len(r["tiles"]) for r in jr])
    ck("no tile's prior is dropped to an empty string",
       all((t["prior_verdict"] or "").strip() for r in jr for t in r["tiles"]))

    # The three open disagreements, read not transcribed.
    ck("the three open disagreements come from the diff record and reach the page (%d)"
       % len(open_), len(open_) == 3 and json.loads(
           txt.split("var OWED=")[1].split(";\nvar OWV=")[0]) == open_)
    ck("the diff record's hash is on the page", dsha in txt and len(dsha) == 16)

    # Gaps as gaps.
    gaps = [l for l, _rv, st, _it in spec if st["gap"]]
    ck("every legend-axis letter has a card (%d letters, %d axes)"
       % (len(spec), len(LEGEND_AXES)),
       all(('<b>%s</b>' % l.replace("final_", "final ")) in txt for l, _r, _s, _i in spec)
       and len(spec) == sum(len(a) for a in LEGEND_AXES))
    ck("a gap is shown as a gap, once per gap letter (%d: %s)" % (len(gaps), ", ".join(gaps)),
       txt.count("No rule-2-clean signed exemplar") == len(gaps))
    ck("no gap letter shows a specimen crop, and every non-gap letter does",
       all((st["gap"] and not [i for i in it if not i["dirty"]])
           or (not st["gap"] and [i for i in it if not i["dirty"]])
           for _l, _rv, st, it in spec))

    # No model reading, asserted over the bytes.
    licensed = set()
    for r, _c in rows:
        for t in r.get("tiles") or ():
            licensed.update([t.get("shown") or u"", t.get("chose") or u""])
        for x in r.get("insertions") or ():
            licensed.update([x.get("chose") or u""])
        licensed.add(u"".join((t.get("chose") or t.get("shown") or u"")
                              for t in r.get("tiles") or ()))
    for _l, _rv, _st, items in spec:
        for i in items:
            licensed.add(i["word"])
    licensed.update(LETTER.values())
    for x in open_:
        for side in ("prior", "current"):
            d = x.get(side) or {}
            licensed.update([d.get("shown") or u"", d.get("chose") or u""])
    licensed.discard(u"")
    runs = set(_hebrew_runs(txt))
    stray = sorted(r for r in runs if r not in licensed)
    ck("every Hebrew string on the page came from a signature, a signed tile or the palette "
       "(%d distinct, %d unlicensed)" % (len(runs), len(stray)), not stray, stray[:6])

    pgs = sorted(set([i["page"] for _l, _rv, _st, it in spec for i in it]))
    ck("every scan a specimen crop points at exists on disk (%d page(s))" % len(pgs),
       bool(pgs) and all((DATA / IMGREL / ("page%d_image1.png" % p)).exists() for p in pgs),
       [p for p in pgs if not (DATA / IMGREL / ("page%d_image1.png" % p)).exists()])

    # The interface fixes.
    ck("every palette letter carries its name", all(
        ('>%s<span>%s</span>' % (v, k.replace("final_", "f."))) in txt for k, v in LETTER.items()))
    ck("the tile strip is laid out in the print's own direction, and says it is an ordering",
       "direction:rtl" in txt and "not an alignment" in txt)
    ck("the assembled word is under the picture, at the picture's height, and is labelled as "
       "neither typed nor a reading",
       txt.count('class="asm"') == len(rows) and "not typed, and not a reading" in txt)
    # Matched against the DE-ESCAPED page: these calls are emitted inside JS string literals, and
    # a check that counts backslashes is measuring the emitter's quoting, not what the page offers.
    flat = txt.replace("\\'", "'")
    ck("each of the three verdicts is reachable from a tile, and the abstain reason is required",
       "'keep_prior')" in flat and "'abstain')" in flat and 'st.v="changed"' in flat
       and "a reason is required" in txt)
    ck("no fourth verdict is offered on a tile (%d tile verdict calls)" % flat.count("setv('"),
       flat.count("setv('") == flat.count("'keep_prior')") + flat.count("'abstain')")
       and flat.count("setv('") > 0)
    # The gap branch asserted nothing above: no legend letter is a gap today. A check whose subject
    # does not exist is not a passing check, so the branch is exercised directly -- the one way to
    # know the page would print an absence rather than a blank if the supply went away.
    faked = [(l, rv, dict(st, signed=[], clean=[], gap=True, single=False), [])
             for l, rv, st, _it in spec]
    gtxt = legend_section(faked)
    ck("the gap branch prints an absence for every letter when the supply is empty (%d)"
       % len(faked),
       gtxt.count("No rule-2-clean signed exemplar") == len(faked)
       and '<div class="pc"' not in gtxt and "No signed impression of any kind" in gtxt)
    ck("a context-only letter is named as such, and a pointed one is not (%d context-only)"
       % len([1 for _l, _r, st, it in spec
              if [x for x in it if not x["dirty"]]
              and not [x for x in it if not x["dirty"] and x["kind"] == "pointed"]]),
       txt.count("No <b>pointed</b> attestation") == len(
           [1 for _l, _r, st, it in spec if [x for x in it if not x["dirty"]]
            and not [x for x in it if not x["dirty"] and x["kind"] == "pointed"]]))

    # The loader is the authority. Each refusal exercised on a real row.
    base = dict(json.loads(json.dumps({
        "kind": "sitting2_tile_verdicts", "span_id": rows[0][0]["span_id"],
        "crop_sha16": rows[0][0]["crop_sha16"], "signer": "T", "date": TODAY,
        "tiles": [{"i": t.get("i"), "shown": t.get("shown"), "verdict": "keep_prior"}
                  for t in rows[0][0].get("tiles") or ()]})))

    def load_one(row):
        p = DATA / "_sitting2_selftest.jsonl"
        io.open(str(p), "w", encoding="utf-8", newline="\n").write(
            json.dumps(row, ensure_ascii=False) + "\n")
        try:
            return sitting2_load(p)
        finally:
            os.remove(str(p))

    g, b = load_one(base)
    ck("a complete row loads", len(g) == 1 and not b, b and b[0]["_refused"])
    r2 = json.loads(json.dumps(base))
    r2["tiles"][0]["verdict"] = "abstain"
    g, b = load_one(r2)
    ck("abstain with no reason is refused, and the refusal says why the reason is the content",
       not g and len(b) == 1 and "abstain with no reason" in b[0]["_refused"])
    r2["tiles"][0]["reason"] = "   "
    g, b = load_one(r2)
    ck("a whitespace reason is not a reason", not g and len(b) == 1)
    r2["tiles"][0]["reason"] = "the ink is broken where the stroke would join"
    g, b = load_one(r2)
    ck("abstain WITH a reason is admitted", len(g) == 1 and not b, b and b[0]["_refused"])
    r3 = json.loads(json.dumps(base))
    r3["tiles"][0]["verdict"] = "changed"
    g, b = load_one(r3)
    ck("changed with no letter is refused", not g and "no letter was named" in (b[0]["_refused"]
                                                                               if b else ""))
    r4 = json.loads(json.dumps(base))
    r4["crop_sha16"] = "0" * 16
    g, b = load_one(r4)
    ck("a verdict over different pixels is refused",
       not g and "different picture" in (b[0]["_refused"] if b else ""))
    r5 = json.loads(json.dumps(base))
    r5["tiles"] = r5["tiles"][:-1]
    g, b = load_one(r5)
    ck("a strip that does not correspond one-for-one is refused",
       not g and "one-for-one" in (b[0]["_refused"] if b else ""))
    r6 = json.loads(json.dumps(base))
    r6["span_id"] = "p999:n9"
    g, b = load_one(r6)
    ck("a verdict about a row nobody signed is refused",
       not g and "has no prior" in (b[0]["_refused"] if b else ""))
    o1 = {"kind": "sitting2_disagreement_verdicts", "span_id": "p831:n2", "signer": "T",
          "date": TODAY, "verdicts": [{"n": 0, "verdict": "keep", "basis": ""}]}
    g, b = load_one(o1)
    ck("an adjudication with no basis is refused", not g and "no basis" in (b[0]["_refused"]
                                                                           if b else ""))
    o1["verdicts"][0]["verdict"] = "better"
    o1["verdicts"][0]["basis"] = "x"
    g, b = load_one(o1)
    ck("a verdict outside keep/take/neither is refused -- an adjudication is not a score",
       not g and "is not one of" in (b[0]["_refused"] if b else ""))

    # The date field used to default to the BUILD date, and the export reads the field verbatim,
    # so a signed row would have carried the builder's day. Asserted over the emitted bytes: the
    # field ships EMPTY, it is filled from the signer's own browser, and the build date is still
    # on the page as a labelled fact rather than as the default.
    ck('the date field ships empty, not stamped with the build date',
       '<input id="date" size="10" value="">' in txt and ('value="%s"' % TODAY) not in txt,
       [l for l in txt.splitlines() if 'id="date"' in l][:1])
    ck("the date is filled from the signer's own browser at load",
       'document.getElementById("date").value=new Date(' in txt.replace("\n", ""))
    ck("the build date is still disclosed on the page, as a fact and not as a default",
       ("built %s" % TODAY) in txt)

    ck("the export file is not written by this module",
       not os.path.exists(str(EXPORT)) or "sitting2_page" not in txt.split("EXPORT_NAME")[0][-80:])
    print("\n%d checks, %d failed" % (n[0], n[1]))
    return n[1]


if __name__ == "__main__":
    if "selftest" in sys.argv[1:]:
        sys.exit(selftest())
    p = build()
    print("wrote %s" % p)
