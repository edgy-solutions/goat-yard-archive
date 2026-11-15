"""Point-and-name: capture a signed exemplar, or a re-ratified box, without going through chat.

WHY THIS EXISTS. The 21-span signed set cannot supply the exemplars the glyph cards need -- measured,
it gives gimel 1, pe 2, and no single impression holding both letters of either pair. Chris's ruling
of 2026-09-27 opens exemplars to the whole volume: any word on any page that he reads from pixels and
names is an exemplar with signature authority. What that needs is not a bigger corpus but a RECORD --
file page, box, letter, the letter's index counted from the right of the word, signer, date -- so the
evidence is a row in a store and not a screenshot in a conversation.

2026-11-15, the advisor: "He does not read Hebrew, and signing is from pixels, never by typing."
So the typed Hebrew word is GONE. The word is ASSEMBLED: he draws the box around the rightmost glyph
and clicks that letter's tile, then the next glyph leftwards, and so on. The assembly is the word,
the position he points at is the index, and `letter_boxes` carries one box per glyph.

That move costs something, and the cost is paid in `hebrew_glyph_card.letter_boxes_fault`. The old
gate checked that the named letter sat at the claimed index of the typed word -- two acts, a reading
and a count, which could disagree. Assembled from one set of clicks they cannot: a verifier that
calls the producer agrees by construction. What replaces it is geometric and is NOT produced by the
naming act -- one box per glyph, running right to left, non-overlapping, on one line of type, with
the signed box the one at the claimed index. In re-ratification mode, where the claim is "this box
holds this text" and no index is counted, the tiles are clicked without a box per glyph.

WHAT THIS DELIBERATELY DOES NOT DO: it proposes nothing it does not label. It does not find words,
snap a box to ink, or guess which letter is under the cursor. The signer draws the box and names the
letter; the tool does arithmetic (display pixels -> native page pixels) and formats a line. That
division is the whole design: every machine proposal on a signing surface in this lane has to be
ratifiable by looking at the proposal itself, and a snapped box that is subtly wrong looks exactly
like a snapped box that is right.

The one thing it now offers is NAVIGATION, and it is labelled as navigation: for each letter the
cards have no exemplar of, the rivals that letter must not share a word with (derived from the cards'
own asks) and a few file pages whose stored extraction holds a rival-free word. That extraction is
unsigned machine output. The position of the letter inside the word is deliberately NOT printed --
a page number is not a reading, and the count is his, made by boxing.

WHAT IT DOES DO is show you the crop of the box you just drew, magnified, before you add the record --
so a mis-drawn box is visible as a mis-drawn box, here, rather than on a card three steps later.

Nothing is validated here beyond the obvious. The gate lives in `hebrew_glyph_card.sig_load` /
`rerat_load`, which refuse a record whose box is blank, runs off the page, holds more than one text
line, or whose named letter is not at the index it claims. A record captured here and refused there
is the system working: the capture surface is a convenience, the loader is the authority.

    python hebrew_point_and_name.py            # writes the capture page next to the cards
"""
import datetime
import io
import json
import os
import re
import sys

import hebrew_aperture_diag as D
from write_scope import assert_inside
from hebrew_glyph_card import (CARDS, LETTER, RERAT, SIG_REQUIRED, SIGS, card_asks, exemplars,
                               has_nikud, sig_exemplars, strip_nikud)

OUT = D.DATA / "hebrew_point_and_name.html"
# The page images are not copied into this file and never will be: a capture surface that embeds
# scans is a corpus leaving its folder. The browser loads them from the volume by relative path --
# DERIVED from the two configured roots, not written out by hand, so moving either one cannot leave
# a hand-typed "../.." pointing at nothing. The selftest resolves it against the filesystem.
IMGREL = os.path.relpath(str(D.IMG), str(D.DATA)).replace(os.sep, "/")
FIRST = 423
# The whole-volume span census: 696 rows of stored, UNSIGNED machine extraction. It is the only
# thing on this page that came from a machine reading of the corpus, and the only thing it is used
# for is to say which file pages are worth opening.
CENSUS = D.DATA / "hebrew_span_census_20261004.json"
TODAY = datetime.date.today().isoformat()

CSS = """
:root{--bg:#0e1116;--fg:#e6e6e6;--mut:#9aa4b2;--acc:#7dd3fc;--warn:#fbbf24;--bad:#f87171;
--ok:#4ade80;--card:#161b22;--line:#2d333b}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 -apple-system,Segoe UI,sans-serif}
header{padding:12px 16px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:5}
h1{font-size:16px;margin:0 0 6px}
.mut{color:var(--mut);font-size:12px}
.bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:8px}
input,select,button{background:#0b0e13;color:var(--fg);border:1px solid var(--line);border-radius:6px;
padding:6px 9px;font:13px inherit}
input[dir=auto]{font:20px "Times New Roman",serif}
button{cursor:pointer}
button.go{background:#0b2f1b;border-color:#14532d;color:var(--ok)}
.wrap{display:flex;gap:14px;align-items:flex-start;padding:14px 16px}
.pane{flex:1 1 0;min-width:0}
.side{flex:0 0 430px}
#stage{position:relative;display:inline-block;line-height:0}
#page{max-width:none;image-rendering:pixelated;background:#fff;cursor:crosshair;display:block}
#sel{position:absolute;border:2px solid #f87171;background:rgba(248,113,113,.12);pointer-events:none;display:none}
.scroll{overflow:auto;max-height:76vh;border:1px solid var(--line);border-radius:8px;background:#0b0e13}
.box{border:1px solid var(--line);border-radius:8px;padding:10px;background:var(--card);margin-bottom:12px}
canvas{image-rendering:pixelated;background:#fff;border-radius:4px;max-width:100%;display:block}
textarea{width:100%;height:190px;background:#0b0e13;color:#cbd5e1;border:1px solid var(--line);
border-radius:6px;font:11px ui-monospace,Consolas,monospace;padding:8px}
.warn{border-left:3px solid var(--warn);padding:6px 10px;background:#1b1608;font-size:12px;margin:8px 0}
.k{font:12px ui-monospace,Consolas,monospace;color:var(--acc)}
label{font-size:12px;color:var(--mut)}
.tiles{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px}
.tiles button{font:19px "Times New Roman",serif;min-width:36px;padding:2px 6px;line-height:1.05}
.tiles button span{display:block;font:9px ui-monospace,Consolas,monospace;color:var(--mut)}
#asm{direction:rtl;display:flex;flex-wrap:wrap;gap:6px;min-height:52px;align-items:center;
border:1px dashed var(--line);border-radius:6px;padding:6px;background:#0b0e13}
.pos{cursor:pointer;text-align:center;border:1px solid var(--line);border-radius:5px;padding:1px 7px}
.pos.pointed{border-color:var(--ok);background:#0b2f1b}
.pos b{display:block;font:23px "Times New Roman",serif}
.pos i{display:block;font:10px ui-monospace,Consolas,monospace;color:var(--acc);font-style:normal}
.pos em{display:block;font:9px ui-monospace,Consolas,monospace;color:var(--mut);font-style:normal}
#asmword{font:23px "Times New Roman",serif;direction:rtl}
.heb{font:19px "Times New Roman",serif;direction:rtl}
section{padding:4px 16px 26px}
h2{font-size:14px;margin:14px 0 6px}
table.sug{border-collapse:collapse;font-size:12px;width:100%;margin-top:8px}
table.sug td,table.sug th{border-top:1px solid var(--line);padding:5px 8px;text-align:left;
vertical-align:top}
table.sug th{color:var(--mut);font-weight:normal}
"""

JS = """
var img = document.getElementById('page');
var stage = document.getElementById('stage');
var sel = document.getElementById('sel');
var box = null;            // native page pixels: the box last drawn, not yet spent
var drag = null;
// The assembled word. Index 1 is the RIGHTMOST glyph and is word[0]: Hebrew is stored in reading
// order, so joining these in array order gives the string the loader counts in.
var word = [];             // [{letter, ch, box, pg}]
var pointAt = 0;           // which position the exemplar is. 0 = he has not said yet.
var loadedPg = FIRST;      // the page actually on screen -- NOT the number in the box

function scale(){ return img.naturalWidth / img.clientWidth; }   // native px per displayed px

function load(){
  var pg = parseInt(document.getElementById('pg').value, 10);
  if(!pg){ return; }
  // A box is a coordinate on ONE page. Changing page under a part-built word would leave boxes cut
  // from the old page in a record stamped with the new one -- the record would be internally
  // consistent and wrong, which is the failure this lane has paid for before.
  if(word.length && pg !== loadedPg){
    if(!confirm('The ' + word.length + ' glyph(s) you have assembled were boxed on page '
                + loadedPg + '. Loading page ' + pg + ' discards them. Continue?')){
      document.getElementById('pg').value = loadedPg; return; }
    word = []; pointAt = 0; render_word();
  }
  loadedPg = pg;
  img.src = IMGREL + '/page' + pg + '_image1.png';
  box = null; sel.style.display='none'; say('');
}
function zoom(f){
  var w = img.clientWidth * f;
  img.style.width = Math.max(200, w) + 'px';
  redraw();
}
function fit(){ img.style.width = (document.querySelector('.scroll').clientWidth - 20) + 'px'; redraw(); }

stage.addEventListener('mousedown', function(e){
  var r = img.getBoundingClientRect();
  drag = {x: e.clientX - r.left, y: e.clientY - r.top};
  sel.style.display = 'block';
  e.preventDefault();
});
stage.addEventListener('mousemove', function(e){
  if(!drag){ return; }
  var r = img.getBoundingClientRect();
  var x = e.clientX - r.left, y = e.clientY - r.top;
  var L = Math.min(x, drag.x), T = Math.min(y, drag.y);
  sel.style.left = L + 'px'; sel.style.top = T + 'px';
  sel.style.width = Math.abs(x - drag.x) + 'px'; sel.style.height = Math.abs(y - drag.y) + 'px';
});
window.addEventListener('mouseup', function(e){
  if(!drag){ return; }
  var r = img.getBoundingClientRect();
  var x = e.clientX - r.left, y = e.clientY - r.top;
  var s = scale();
  box = [Math.round(Math.min(x, drag.x) * s), Math.round(Math.min(y, drag.y) * s),
         Math.round(Math.max(x, drag.x) * s), Math.round(Math.max(y, drag.y) * s)];
  drag = null;
  if(box[2] - box[0] < 4 || box[3] - box[1] < 4){ box = null; sel.style.display='none'; say(''); return; }
  redraw();
});

function redraw(){
  if(!box){ return; }
  var s = scale();
  sel.style.display = 'block';
  sel.style.left = (box[0]/s)+'px'; sel.style.top = (box[1]/s)+'px';
  sel.style.width = ((box[2]-box[0])/s)+'px'; sel.style.height = ((box[3]-box[1])/s)+'px';
  // The crop you are about to sign, magnified. Nearest-neighbour: no smoothing, ever.
  var w = box[2]-box[0], h = box[3]-box[1];
  var k = Math.max(1, Math.min(8, Math.floor(1400 / Math.max(1, w))));
  var c = document.getElementById('crop');
  c.width = w*k; c.height = h*k;
  var g = c.getContext('2d');
  g.imageSmoothingEnabled = false;
  g.drawImage(img, box[0], box[1], w, h, 0, 0, w*k, h*k);
  say('native box <span class="k">[' + box.join(', ') + ']</span> &middot; ' + w + '&times;' + h +
      'px &middot; shown at &times;' + k);
}
function say(s){ document.getElementById('info').innerHTML = s; }

function isEx(){ return document.getElementById('mode').value === 'exemplar'; }

function click_letter(name){
  if(isEx()){
    if(!box){ alert('Draw the box around that glyph first, then click its letter. Right to left: '
                    + 'the RIGHTMOST glyph of the word is position 1.'); return; }
    word.push({letter: name, ch: LETTERCH[name], box: box, pg: loadedPg});
    box = null; sel.style.display = 'none';
    say('glyph ' + word.length + ' captured &mdash; draw the next one to its LEFT');
  } else {
    word.push({letter: name, ch: LETTERCH[name], box: null, pg: loadedPg});
  }
  render_word();
}
function click_space(){
  if(isEx()){ alert('An exemplar is ONE word: the index is counted in word 1, so a space has '
                    + 'nowhere to go. Add the record, then assemble the next word.'); return; }
  word.push({letter: null, ch: ' ', box: null, pg: loadedPg});
  render_word();
}
function undo_letter(){
  word.pop();
  if(pointAt > word.length){ pointAt = 0; }
  render_word();
}
function clear_word(){ word = []; pointAt = 0; render_word(); }
function point_at(i){ if(!isEx()){ return; } pointAt = (pointAt === i ? 0 : i); render_word(); }

function render_word(){
  var h = '', i, w;
  for(i = word.length; i >= 1; i--){
    w = word[i-1];
    h += '<span class="pos' + (i === pointAt ? ' pointed' : '') + '" onclick="point_at(' + i + ')"'
       + ' title="' + (w.box ? 'box [' + w.box.join(', ') + '] on page ' + w.pg : 'no box') + '">'
       + '<b>' + (w.ch === ' ' ? '&nbsp;' : w.ch) + '</b><i>' + i + '</i><em>'
       + (w.letter || 'space') + '</em></span>';
  }
  document.getElementById('asm').innerHTML = h ||
    '<span class="mut">nothing assembled yet &mdash; box the RIGHTMOST glyph of the word, then '
    + 'click its letter below</span>';
  var t = '';
  for(i = 0; i < word.length; i++){ t += word[i].ch; }
  document.getElementById('asmword').textContent = t;
  document.getElementById('asmn').textContent = word.length;
  document.getElementById('pointed').innerHTML = !isEx() ? 'not used in this mode'
    : (pointAt ? ('glyph <span class="k">' + pointAt + '</span> from the right &mdash; <b>'
                  + word[pointAt-1].letter + '</b>')
               : '<span style="color:var(--warn)">none yet &mdash; click the glyph above that you '
                 + 'are signing an exemplar of</span>');
}

function add(){
  var signer = document.getElementById('signer').value.trim();
  var date = document.getElementById('date').value.trim();
  var note = document.getElementById('note').value.trim() || undefined;
  var i, rec;
  if(!word.length){ alert('Assemble the word first: box a glyph, click its letter.'); return; }
  if(!signer || !date){ alert('signer and date are both required.'); return; }
  // The page comes off the GLYPHS, never off the input box: he may have typed a number into it
  // without loading it, and a record must carry the page its boxes were actually cut from.
  var pg = word[0].pg;
  for(i = 0; i < word.length; i++){
    if(word[i].pg !== pg){ alert('These glyphs were boxed on two different pages. Clear and '
                                 + 'start again on one page.'); return; }
  }
  if(isEx()){
    if(!pointAt){ alert('Click the glyph above that you are signing an exemplar of.'); return; }
    var lb = [];
    for(i = 1; i <= word.length; i++){
      if(!word[i-1].box){ alert('Glyph ' + i + ' has no box. In exemplar mode every glyph of the '
                                + 'word is boxed, because the boxes are what prove the index.');
                          return; }
      lb.push({index_from_right: i, letter: word[i-1].letter, box: word[i-1].box});
    }
    rec = {file_page: pg, box: word[pointAt-1].box, coord_space: 'native',
           word: document.getElementById('asmword').textContent,
           word_source: 'assembled from clicked letter tiles, one drawn box per glyph',
           letter: word[pointAt-1].letter, letter_index_from_right: pointAt,
           letter_boxes: lb, signer: signer, date: date, note: note};
  } else {
    if(!box){ alert('Draw the box you read this text from.'); return; }
    var sid = document.getElementById('span').value.trim();
    if(!sid){ alert('A re-ratification needs the span id it replaces.'); return; }
    rec = {span_id: sid, file_page: pg, new_box: box, coord_space: 'native',
           old_box_state: document.getElementById('oldstate').value,
           text: document.getElementById('asmword').textContent,
           text_source: 'assembled from clicked letter tiles',
           signer: signer, date: date,
           basis: 'signed-from-the-page via point-and-name',
           note: note};
  }
  var ta = document.getElementById('out');
  ta.value += JSON.stringify(rec) + '\\n';
  ta.scrollTop = ta.scrollHeight;
  // The assembly is NOT cleared: a word carrying two of the letters the cards want is two records
  // off one set of boxes -- point the other glyph and add again.
  say('record added. The assembly is kept: point another glyph to sign a second letter of the '
      + 'same word, or clear it.');
}

function dl(){
  var mode = document.getElementById('mode').value;
  var name = mode === 'exemplar' ? 'hebrew_exemplar_signatures.jsonl' : 'hebrew_box_reratify.jsonl';
  var b = new Blob([document.getElementById('out').value], {type: 'application/x-ndjson'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(b); a.download = name; a.click();
}
function modeChange(){
  var ex = isEx();
  document.getElementById('exfields').style.display = ex ? '' : 'none';
  document.getElementById('rrfields').style.display = ex ? 'none' : '';
  document.getElementById('spacebtn').style.display = ex ? 'none' : '';
  document.getElementById('wordlbl').innerHTML = ex
    ? 'the word, assembled: <b>box a glyph, then click its letter</b> &mdash; right to left'
    : 'the text you read, assembled by clicking letters &mdash; right to left';
  document.getElementById('dest').textContent = ex ? SIGS : RERAT;
  render_word();
}
// Item 4: the date is the day this page is OPENED, off the browser clock, not the day it was
// written out. A field that defaults to a date in the past dates every record wrongly unless the
// signer notices, and a signature carrying the wrong day is a record about the wrong sitting.
(function(){
  var d = new Date();
  function p(n){ return (n < 10 ? '0' : '') + n; }
  document.getElementById('date').value =
    d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
})();
img.addEventListener('load', function(){ fit(); });
modeChange();
"""


def blocked_letters():
    """[(letter, [rival names])] for every card candidate with NO exemplar at all.

    DERIVED from the cards, not listed: the letters this page offers pages for are the letters the
    cards are actually stuck on, and a list typed out here would be a snapshot that goes stale the
    first time one of them is signed. The rivals are the UNION over every ask that names the letter,
    because rule 2 holds against every rival or it does not hold -- dalet is asked against resh on
    one card and against samekh and final kaf on others, and a word clean of only one of them begs
    the question on the next card.
    """
    need = {}
    for c in CARDS:
        for a in card_asks(c):
            cands = tuple(a.get("candidates") or ())
            for cand in cands:
                rivals = tuple(x for x in cands if x != cand)
                total = (len(sig_exemplars(cand))
                         + len(exemplars(cand, rivals, exclude=(c["span_id"],))))
                row = need.setdefault(cand, {"rivals": set(), "least": None})
                row["rivals"].update(rivals)
                row["least"] = total if row["least"] is None else min(row["least"], total)
    return [(k, sorted(need[k]["rivals"])) for k in sorted(need) if need[k]["least"] == 0]


def census_pages(letter, rivals, want=12):
    """(rows, n_words_total) -- file pages whose stored text holds `letter` in a rival-free word.

    The rule, which the page prints beside the table so it can be argued with:
      - the word contains the letter and NONE of its rivals (rule 2, as the cards apply it);
      - a word whose whole SPAN is also free of every rival ranks first -- the span is the unit a
        reader's eye takes in, so a rival three words away is still a rival;
      - then the shortest word, because every glyph is a box he has to draw;
      - then the lowest file page.
    One row per FILE PAGE first, since a different page is a different printing and a different
    chance the glyph is clean. Then, only if that ran out before `want` rows, the remaining words
    are topped up in the same rank order, deduped on (page, word) and FLAGGED `same_page` -- a
    letter whose rival-free words all sit on three pages should still give him twelve things to
    look at, and he should be able to see which rows are not a fresh page.
    The POSITION of the letter in the word is computed here and deliberately NOT returned: it is
    the one thing on this page that would do his counting for him, and the geometry gate exists
    because that count is the claim.

    Returns ([], 0) when the census is not on disk. A page that invented candidates because its
    source was missing would be the exact fabrication this lane keeps a blank channel for.
    """
    if not CENSUS.exists():
        return [], 0
    rows = (json.loads(io.open(CENSUS, encoding="utf-8").read()) or {}).get("rows") or []
    ch = LETTER[letter]
    rv = [LETTER[x] for x in rivals]
    hits = []
    for s in rows:
        raw = s.get("hebrew") or ""
        t = strip_nikud(raw)
        if ch not in t:
            continue
        span_clean = not any(p in t for p in rv)
        toks, rawtoks = t.split(), raw.split()
        if len(toks) != len(rawtoks):
            rawtoks = toks
        for w, wraw in zip(toks, rawtoks):
            if ch not in w or any(p in w for p in rv):
                continue
            hits.append((0 if span_clean else 1, len(w), int(s["page"]), w,
                         s["span_id"], has_nikud(wraw)))
    hits.sort()
    out, pages, taken = [], set(), set()
    for h in hits:                                   # pass 1: a different page every row
        if h[2] in pages:
            continue
        pages.add(h[2])
        taken.add((h[2], h[3], h[4]))
        out.append(h + (False,))
        if len(out) == want:
            break
    for h in hits:                                   # pass 2: top up, flagged, never a repeat row
        if len(out) >= want:
            break
        if (h[2], h[3], h[4]) in taken:
            continue
        taken.add((h[2], h[3], h[4]))
        out.append(h + (True,))
    return out, len(hits)


def stuck_section():
    """The rivals and the pages, as one section of the page. Items 2 and 3 of the 2026-11-15 note."""
    h = ['<section><h2>What the cards have no exemplar of &mdash; and some pages to look at</h2>',
         '<div class="mut">The letters below are derived from the cards\' own questions: each is a '
         'candidate some card asks about, and no exemplar of it exists anywhere &mdash; not signed '
         'from the volume, not from a signed span. Pointing one unblocks a card that currently '
         'prints NO VERDICT.</div>',
         '<div class="warn">The words and pages are the <b>stored machine extraction</b> '
         '(<span class="k">%s</span>), which is <b>unsigned</b>. They are <b>navigation, not a '
         'reading</b>: nothing here is asserted to you. If the glyph under your box is not that '
         'letter &mdash; or the word is not that word &mdash; the candidate is wrong, and the next '
         'page in the row is there for exactly that reason. <b>Where the letter sits in the word is '
         'deliberately not printed.</b> That count is the claim you are signing, and you make it by '
         'boxing the glyphs.</div>' % CENSUS.name,
         '<table class="sug"><tr><th>letter</th><th>the word must NOT contain</th>'
         '<th>rival-free words<br>in all 696 spans</th><th>file pages (printed = file &minus; 88)'
         '</th></tr>']
    for letter, rivals in blocked_letters():
        rows, total = census_pages(letter, rivals)
        rv = " ".join(LETTER[x] for x in rivals) or "&mdash;"
        cell = []
        for _r, _n, pg, w, sid, nik, same in rows:
            cell.append('<b>p%d</b> <span class="mut">(printed %d)</span> '
                        '<span class="heb">%s</span> <span class="mut">%d glyph%s, %s, in %s%s</span>'
                        % (pg, pg - 88, w, len(w), "" if len(w) == 1 else "s",
                           "pointed" if nik else "unpointed", sid,
                           ", <b>same page</b>" if same else ""))
        h.append('<tr><td><span class="heb">%s</span> %s</td><td><span class="heb">%s</span> '
                 '<span class="mut">%s</span></td><td>%s</td><td>%s</td></tr>'
                 % (LETTER[letter], letter, rv, ", ".join(rivals) or "nothing named",
                    total if total else "<b>none</b>",
                    "<br>".join(cell) or "<b>no rival-free word in the census</b>"))
    h.append("</table>")
    h.append('<div class="mut">The ranking rule, so it can be argued with: a word containing the '
             'letter and none of its rivals; a word whose whole span is also rival-free first, '
             'since the span is what the eye takes in; then the shortest word, because every glyph '
             'is a box to draw; then the lowest page. A different file page every row for as long '
             'as there are different pages; after that the list is topped up from the words left '
             'over, each marked <b>same page</b>, up to twelve rows. A letter with fewer rows than '
             'that has no more rival-free words in the census at all &mdash; the count beside it is '
             'the whole supply. A pointed word '
             'carries nikud: box the <b>consonants</b> only &mdash; the points are not glyphs and '
             'the loader compares the consonants.</div>')
    h.append("</section>")
    return "\n".join(h)


def build():
    # The palette, in the order LETTER itself declares: the twenty-two, then the five finals as
    # distinct sorts. A click on one of these is the whole naming act, so the tile shows the glyph
    # at reading size with its name under it -- nothing else on the tile, and no glyph is offered
    # twice under two names.
    tiles = "".join('<button onclick="click_letter(\'%s\')" title="%s">%s<span>%s</span></button>'
                    % (k, k, v, k.replace("final_", "f."))
                    for k, v in LETTER.items())
    h = ['<!doctype html><meta charset="utf-8"><title>Point and name</title>',
         "<style>%s</style>" % CSS,
         '<header><h1>Point and name &mdash; capture a signed exemplar or a re-ratified box</h1>',
         '<div class="mut">All page numbers are FILE pages; printed = file &minus; 88. '
         'Nothing here is proposed by the machine: you draw the box and you name the letter. The '
         'crop of the box you drew is shown magnified before you add it, so a mis-drawn box is '
         'visible now rather than on a card later. Records are refused on load if the box is blank, '
         'runs off the page, holds more than one text line, or the glyph boxes do not put the '
         'letter you pointed at where you pointed at it &mdash; that check is the authority, not '
         'this page.</div>',
         '<div class="bar">',
         '<label>file page</label><input id="pg" size="6" value="%d">' % FIRST,
         '<button onclick="load()">load</button>',
         '<button onclick="zoom(1.6)">+</button><button onclick="zoom(0.625)">&minus;</button>',
         '<button onclick="fit()">fit</button>',
         '<label>mode</label><select id="mode" onchange="modeChange()">'
         '<option value="exemplar">exemplar signature</option>'
         '<option value="rerat">box re-ratification</option></select>',
         '<label>signer</label><input id="signer" size="8" value="Chris">',
         '<label>date</label><input id="date" size="10" value="%s">' % TODAY,
         "</div></header>",
         '<div class="wrap"><div class="pane"><div class="scroll"><div id="stage">',
         '<img id="page" src="%s/page%d_image1.png"><div id="sel"></div>' % (IMGREL, FIRST),
         "</div></div></div>",
         '<div class="side">',
         '<div class="box"><div class="mut">the box you drew, magnified</div>',
         '<canvas id="crop" width="10" height="10"></canvas>',
         '<div class="mut" id="info" style="margin-top:6px"></div></div>',
         '<div class="box">',
         '<div><label id="wordlbl"></label></div>',
         '<div id="asm"></div>',
         '<div class="bar"><span class="mut">assembled</span> <span id="asmword"></span> '
         '<span class="mut">&middot; <span id="asmn">0</span> glyph(s) &middot; pointing at</span> '
         '<span id="pointed"></span></div>',
         '<div class="bar"><button onclick="undo_letter()">undo last glyph</button>'
         '<button onclick="clear_word()">clear word</button>'
         '<button id="spacebtn" onclick="click_space()">word space</button></div>',
         '<div class="tiles">%s</div>' % tiles,
         '<div id="exfields" style="margin-top:8px">',
         '<div class="warn">You are not asked to type Hebrew and never will be. Box the '
         '<b>rightmost</b> glyph of the word and click its letter; then the next glyph to its '
         'left, and so on. The assembly above IS the word, and the glyph you click in it is the '
         'index &mdash; position 1 is the rightmost. The boxes are the part a machine cannot '
         'fake for you: the loader checks that there is one per glyph, that they run right to '
         'left, that none sits on top of another, that they are all on one line of type, and that '
         'the box signed is the one at the position you pointed at. What no check can see is '
         'whether the glyph inside a box is the letter you named &mdash; that is why the crop is '
         'magnified beside it before you add anything.</div></div>',
         '<div id="rrfields" style="display:none;margin-top:8px">',
         '<label>span id</label> <input id="span" size="10" placeholder="p912:n2"> ',
         '<label>what was wrong with the old box</label> <select id="oldstate">'
         '<option value="blank-no-ink">blank &mdash; no ink</option>'
         '<option value="clipped-partial-text">clipped &mdash; held part of the text</option>'
         '<option value="out-of-bounds-clamped">out of bounds &mdash; silently clamped</option>'
         '</select>',
         '<div class="warn">This one record ratifies the new box and retires the old rect '
         'together. The (box, text) binding is one object, so the text assembled above is the text '
         'you read from THIS box &mdash; the one box you drew, which is the claim here. No index is '
         'counted in this mode, so the glyphs are clicked without a box each, and the word space '
         'button is available.</div></div>',
         '<div style="margin-top:8px"><label>note (optional)</label><br>'
         '<input id="note" size="34"></div>',
         '<div class="bar"><button class="go" onclick="add()">add record</button>'
         '<button onclick="dl()">download</button></div></div>',
         '<div class="box"><div class="mut">append these lines to <span class="k" id="dest"></span>'
         '</div><textarea id="out" spellcheck="false"></textarea></div>',
         "</div></div>",
         stuck_section(),
         "<script>var IMGREL=%s;var SIGS=%s;var RERAT=%s;var FIRST=%d;\nvar LETTERCH=%s;\n%s"
         "</script>"
         % (_q(IMGREL), _q(str(SIGS)), _q(str(RERAT)), FIRST,
            json.dumps(LETTER, ensure_ascii=False), JS)]
    assert_inside(OUT, "the capture page belongs in the audits directory, beside the cards")
    OUT.write_text("\n".join(h), encoding="utf-8")
    return OUT


def _q(s):
    return '"%s"' % s.replace("\\", "\\\\").replace('"', '\\"')


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        p = build()
        t = io.open(p, encoding="utf-8").read()
        # Derived once here and compared against the PAGE, so a check cannot pass by asking the
        # same function the page asked. CANDS is independent of the exemplar count: it is just
        # which letters the cards argue about.
        BLOCKED = blocked_letters()
        SUG = dict((k, census_pages(k, rv)) for k, rv in BLOCKED)
        CANDS = set(x for c in CARDS for a in card_asks(c) for x in (a.get("candidates") or ()))
        # The exemplar record's object literal ALONE. Scoped because the re-ratification record
        # carries some of the same field names, and a page-wide scan for `coord_space:` was
        # satisfied by the wrong branch -- which a mutation, not a green run, is how we found out.
        _m = re.search(r"rec = \{file_page: pg, box:.*?\};", t, re.S)
        EXREC = _m.group(0) if _m else ""
        # The suggestion table as the SIGNER sees it: (letter name, the count cell, [(page, word)]).
        # Parsed out of the HTML on purpose -- the checks below must not be able to pass by asking
        # `census_pages` whether `census_pages` was right.
        ROWS = [(_r[0], _r[1],
                 re.findall(r"<b>p(\d+)</b>.*?<span class=\"heb\">(\S+)</span>", _r[2]))
                for _r in re.findall(r"<tr><td><span class=\"heb\">.</span> (\w+)</td>"
                                     r"<td>.*?</td><td>(.*?)</td><td>(.*?)</td></tr>", t, re.S)]
        RIV = dict(BLOCKED)
        n = f = 0
        for name, cond in (
                ("no page image is embedded in the capture page", "base64," not in t),
                ("the images are referenced by relative path", IMGREL in t),
                # The one piece of arithmetic on this page that a reader cannot check by eye is the
                # relative path the browser will follow. Resolve it for real.
                ("the relative image path resolves to a page that exists",
                 (D.DATA / IMGREL / ("page%d_image1.png" % FIRST)).exists()),
                # Item 1. The typed field is gone, and its absence is checked by NAME: a page
                # that still carried a Hebrew text input would be the thing the advisor ruled out,
                # whatever else was added beside it.
                ("no free-text Hebrew input is left on the page",
                 'id="word"' not in t and 'dir="auto"' not in t),
                ("every Hebrew letter is a clickable tile",
                 all(("click_letter('%s')" % k) in t for k in LETTER)),
                ("every Hebrew glyph is on exactly one tile",
                 all(t.count(">%s<span>" % v) == 1 for v in LETTER.values())),
                ("the word is assembled from the clicks, and says so in the record",
                 "assembled from clicked letter tiles" in t and '"letter_boxes"' not in t
                 and "letter_boxes: lb" in t),
                ("the exemplar record carries one box per glyph",
                 "index_from_right" in t and "letter_boxes" in t),
                ("the index is pointed at, not typed",
                 'id="idx"' not in t and "letter_index_from_right: pointAt" in t),
                ("the page a record names comes off the glyphs, not the input box",
                 "var pg = word[0].pg" in t),
                # Item 4.
                ("the date field defaults to today, not to a date in the past",
                 ('value="%s"' % TODAY) in t and "getFullYear" in t
                 and 'value="2026-09-27"' not in t),
                # Items 2 and 3, checked against the records rather than against the page's own
                # arithmetic: every letter the page says is blocked must really have no signed
                # exemplar and must really be a candidate on a card, and every word it suggests
                # must really be free of that letter's rivals on a page that really exists.
                ("every letter the page calls blocked has no signed exemplar",
                 all(not sig_exemplars(k) for k, _r in BLOCKED)),
                ("every letter the page calls blocked is a candidate on some card",
                 all(k in CANDS for k, _r in BLOCKED)),
                ("the rivals of every blocked letter are printed", bool(BLOCKED) and
                 all(LETTER[x] in t for _k, rv in BLOCKED for x in rv)),
                ("the suggestion table has one row per blocked letter, by name",
                 [r[0] for r in ROWS] == [k for k, _rv in BLOCKED]),
                ("words were actually parsed off the table, so the checks below say something",
                 sum(len(r[2]) for r in ROWS) >= 2),
                ("every word printed on the page holds the letter it is offered for",
                 all(LETTER[r[0]] in w for r in ROWS for _p, w in r[2])),
                ("no word printed on the page holds a rival of that letter",
                 all(not any(LETTER[x] in w for x in RIV[r[0]])
                     for r in ROWS for _p, w in r[2])),
                ("every page printed on the page exists on disk",
                 all((D.DATA / IMGREL / ("page%s_image1.png" % p)).exists()
                     for r in ROWS for p, _w in r[2])),
                ("a letter with no rival-free word in the census is offered no page",
                 all(bool(r[2]) != ("none" in r[1]) for r in ROWS)),
                ("the census is named on the page as the source of the suggestions",
                 CENSUS.name in t),
                ("no input element arrives holding Hebrew",
                 not [m for m in re.findall(r"<input[^>]*>", t)
                      if re.search(r"[\u0590-\u05ff]", m)]),
                # Liveness first: an empty slice would satisfy nothing and pass everything.
                ("the exemplar record literal was found in the page, and is only part of it",
                 bool(EXREC) and len(EXREC) < len(t) / 4),
                ("the emitter writes every field the loader requires, in the exemplar record",
                 all(("%s:" % k) in EXREC for k in SIG_REQUIRED)),
                ("the exemplar record is not the re-ratification record",
                 "span_id" not in EXREC and "new_box" not in EXREC),
                ("both record shapes are reachable", "exemplar signature" in t
                 and "box re-ratification" in t),
                ("the display-to-native scale is computed from naturalWidth",
                 "naturalWidth" in t and "clientWidth" in t),
                ("the crop preview never smooths", "imageSmoothingEnabled = false" in t),
                ("nothing is snapped to ink", "snap" not in t.lower()),
                ("the loader is named as the authority", "refused on load" in t or
                 "Records are refused" in t)):
            n += 1
            if not cond:
                f += 1
            print("  %s  %s" % ("ok  " if cond else "FAIL", name))
        print("%s: %d/%d checks" % ("PASS" if not f else "FAIL", n - f, n))
        sys.exit(1 if f else 0)
    print("wrote %s" % build())
