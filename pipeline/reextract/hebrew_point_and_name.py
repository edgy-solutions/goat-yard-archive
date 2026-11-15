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
from hebrew_glyph_card import (CARDS, DISPUTED, LETTER, RERAT, SIG_REQUIRED, SIGS, card_asks,
                               exemplars, has_nikud, sig_context_tiles, sig_exemplars, strip_nikud)

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


# The four axes Chris named for the second sitting's legend (item 2a, 2026-11-15). They are NOT
# the same thing as the cards' rivals: final_mem is on one of them and no card asks it, and zayin's
# card rivals do not include final_nun while this axis does. Both are unioned where a letter sits on
# both, because rule 2 holds against every rival or it does not hold.
LEGEND_AXES = (("dalet", "resh"), ("vav", "zayin", "final_nun"), ("he", "tav"),
               ("mem", "final_mem", "samekh"))


def axis_rivals():
    """letter -> (rivals, from_card, from_axis). The two sources kept apart, because they answer
    different questions: a card rival is a letter some card actually argues against, an axis rival
    is one Chris named as confusable. A letter with axis rivals and no card rival has a VACUOUS
    rule 2 in the cards' sense, and the page has to say so rather than print "nothing named"."""
    card = {}
    for c in CARDS:
        for a in card_asks(c):
            cands = tuple(a.get("candidates") or ())
            for x in cands:
                card.setdefault(x, set()).update(y for y in cands if y != x)
    out = {}
    for ax in LEGEND_AXES:
        for l in ax:
            out[l] = (set(card.get(l, ())), set(y for y in ax if y != l))
    for l, rv in card.items():
        if l not in out:
            out[l] = (set(rv), set())
    return dict((l, (sorted(c | a), sorted(c), sorted(a - c))) for l, (c, a) in out.items())


def signed_supply(letter):
    """What SIGNED evidence exists for `letter`, each item marked by kind and by rule 2.

    [(kind, file_page, word, index_from_right, dirty_rivals)] where kind is "pointed" or "context".
    `dirty_rivals` is the rivals present in the same word -- empty means rule-2 clean. A pointed
    record is reported with its rule-2 state too, not exempted from the test: the cards exempt it
    (a named index cannot beg the question) but the SITTING is choosing what to print as a specimen
    beside a rival, and a specimen whose own word holds the rival is a worse picture whatever its
    provenance. Both facts are shown; neither is collapsed into the other.
    """
    rivals = axis_rivals().get(letter, ((), (), ()))[0]
    out = []
    for r in sig_exemplars(letter):
        bad = sorted(p for p in rivals if LETTER[p] in r["word"])
        out.append(("pointed", r["file_page"], r["word"], r.get("letter_index_from_right"), bad))
    for pg, word, idx in sig_context_tiles(letter):
        bad = sorted(p for p in rivals if LETTER[p] in word)
        out.append(("context", pg, word, idx, bad))
    return out


def legend_letters():
    """[(letter, rivals, state)] -- every letter on one of the sitting's legend axes.

    ALL of them, gaps included, because the sitting page has to show an exemplar for each and
    "gaps shown as gaps" is the instruction. `state` carries what exists so the page states rather
    than decides: the signed supply by kind with rule 2 run over each item, the span count, whether
    the clean signed supply is a single instance, and `gap` -- no rule-2-clean SIGNED exemplar at
    all, which is the twelve-page ask.
    """
    ar = axis_rivals()
    out = []
    for ax in LEGEND_AXES:
        for letter in ax:
            rivals, from_card, from_axis = ar[letter]
            sup = signed_supply(letter)
            clean = [x for x in sup if not x[4]]
            out.append((letter, rivals, {
                "from_card": from_card, "from_axis": from_axis, "axis": ax,
                "signed": sup, "clean": clean,
                "span_exemplars": len(exemplars(letter, rivals)),
                "single": len(clean) == 1, "gap": not clean}))
    return out


def card_axis_thin():
    """[(letter, rivals, signed_supply)] -- card-argued letters with no rule-2-clean SIGNED exemplar
    that are NOT on a legend axis.

    Reported, never asked for. The sitting's legend covers the four axes Chris named, and widening a
    human's sitting by nine letters on this lane's own authority is not this function's business.
    But one of them is in a state the legend page would never reveal: yod has no pointed record and
    BOTH its context tiles sit in p386's yod-dalet-yod-final-nun, each dirtied by the final nun --
    and yod is a rival on three separate card asks. That belongs in a report with the reason it is
    not in the ask.
    """
    on_legend = set(l for ax in LEGEND_AXES for l in ax)
    ar = axis_rivals()
    out = []
    for letter in sorted(ar):
        if letter in on_legend:
            continue
        sup = signed_supply(letter)
        if any(not x[4] for x in sup):
            continue
        out.append((letter, ar[letter][0], sup))
    return out


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
    because that count is the claim. It IS used for one thing: an occurrence that is itself a
    DISPUTED glyph is not offered. Measured: this list used to hand back p628:n2's own word as a
    page to point a final nun on, and p628:n2 is the card asking whether that glyph is a final nun
    or a vav. Excluded by POSITION and not by span, because a disputed span's other glyphs are
    ordinary print -- the hand list's own comment says the rest of the phrase is unaffected.

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
        dis = DISPUTED.get(s["span_id"], [])
        for wi, (w, wraw) in enumerate(zip(toks, rawtoks), start=1):
            if ch not in w or any(p in w for p in rv):
                continue
            # Every occurrence of `ch` in this word is a disputed glyph -> the word has nothing
            # clean to point at. One clean occurrence is enough to offer it.
            if dis and all((wi, ci) in dis
                           for ci, c in enumerate(w, start=1) if c == ch):
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


def offer_letters():
    """[(letter, rivals, tier, why)] -- every letter this page asks Chris to point, both tiers.

    tier "blocked": no exemplar from ANY source, so a card prints NO VERDICT. tier "gap": on one of
    the sitting's legend axes with no rule-2-clean SIGNED exemplar, so the legend cannot show a
    specimen beside its rival. The tiers stay labelled all the way to the page -- they are different
    states with different consequences, and a reader who cannot tell them apart cannot tell what his
    pointing would buy.

    A letter in both tiers appears once, as "blocked", because that is the stronger statement.
    """
    out, seen = [], set()
    for letter, rivals in blocked_letters():
        out.append((letter, rivals, "blocked",
                    "no exemplar of any kind: a card prints NO VERDICT until one is pointed"))
        seen.add(letter)
    for letter, rivals, st in legend_letters():
        if letter in seen or not st["gap"]:
            continue
        sup = st["signed"]
        if not sup:
            why = ("no signed exemplar at all; %d span exemplar(s) exist but the legend needs a "
                   "hand-drawn specimen" % st["span_exemplars"])
        else:
            why = ("the only signed impression(s) are rule-2 dirty: %s"
                   % "; ".join("p%d %s (%s, holds %s)" % (pg, w, k, ",".join(bad))
                               for k, pg, w, _i, bad in sup))
        out.append((letter, rivals, "gap", why))
        seen.add(letter)
    return out


def stuck_section():
    """The rivals and the pages, as one section of the page. Items 2 and 3 of the 2026-11-15 note."""
    OFF = offer_letters()
    _n1 = len([1 for r in OFF if r[2] == "blocked"])
    h = ['<section><h2>What has no exemplar &mdash; and some pages to look at</h2>',
         '<div class="mut">Two tiers, labelled on every row, because they are different states. '
         '<b>blocked</b>: no exemplar of the letter exists anywhere &mdash; not signed from the '
         'volume, not built from a signed span &mdash; so a card asking about it prints NO VERDICT '
         'until one is pointed. <b>gap</b>: the letter is on one of the four axes the sitting\'s '
         'legend covers, and it has no <b>signed</b> exemplar that is rule-2 clean, so the legend '
         'cannot show you a specimen of it beside the letter it is confused with. A gap letter may '
         'still have span exemplars; the reason that is not enough is in its own row.</div>',
         '<div class="%s">There %s <b>%d</b> blocked letter%s today%s</div>'
         % ("mut" if _n1 == 0 else "warn", "is" if _n1 == 1 else "are", _n1,
            "" if _n1 == 1 else "s",
            " &mdash; every card candidate has an exemplar from some source. That is not the same "
            "as every legend letter having a signed one, which is what the gap rows below are."
            if _n1 == 0 else "."),
         '<div class="warn">The words and pages are the <b>stored machine extraction</b> '
         '(<span class="k">%s</span>), which is <b>unsigned</b>. They are <b>navigation, not a '
         'reading</b>: nothing here is asserted to you. If the glyph under your box is not that '
         'letter &mdash; or the word is not that word &mdash; the candidate is wrong, and the next '
         'page in the row is there for exactly that reason. <b>Where the letter sits in the word is '
         'deliberately not printed.</b> That count is the claim you are signing, and you make it by '
         'boxing the glyphs.</div>' % CENSUS.name,
         '<table class="sug"><tr><th>letter</th><th>tier</th>'
         '<th>the word must NOT contain</th>'
         '<th>rival-free words<br>in all 696 spans</th><th>file pages (printed = file &minus; 88)'
         '</th></tr>']
    for letter, rivals, tier, why in OFF:
        rows, total = census_pages(letter, rivals)
        rv = " ".join(LETTER[x] for x in rivals) or "&mdash;"
        cell = []
        for _r, _n, pg, w, sid, nik, same in rows:
            cell.append('<b>p%d</b> <span class="mut">(printed %d)</span> '
                        '<span class="heb">%s</span> <span class="mut">%d glyph%s, %s, in %s%s</span>'
                        % (pg, pg - 88, w, len(w), "" if len(w) == 1 else "s",
                           "pointed" if nik else "unpointed", sid,
                           ", <b>same page</b>" if same else ""))
        h.append('<tr><td><span class="heb">%s</span> %s</td>'
                 '<td><b>%s</b><div class="mut">%s</div></td>'
                 '<td><span class="heb">%s</span> '
                 '<span class="mut">%s</span></td><td>%s</td><td>%s</td></tr>'
                 % (LETTER[letter], letter, tier, why, rv,
                    ", ".join(rivals) or "nothing named",
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
        # BOTH tiers, so every check over the suggestion table runs over the gap rows too.
        OFFER = offer_letters()
        BLOCKED = [(k, rv) for k, rv, _t, _w in OFFER]
        TIER = dict((k, t) for k, _rv, t, _w in OFFER)
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
        # (offer, total) for two letters, with the disputed-glyph exclusion ON and then OFF. Taken
        # here rather than inside the tuple so the toggle happens once and is restored once; the
        # card suite toggles DISPUTED the same way.
        _sv = dict(DISPUTED)
        _CENS = [census_pages("final_nun", ["nun", "vav", "yod"], want=16)]
        _CENS.append(None)
        _CENS.append(census_pages("bet", ["gimel"], want=16))
        _CENS.append(None)
        DISPUTED.clear()
        _CENS[1] = census_pages("final_nun", ["nun", "vav", "yod"], want=16)
        _CENS[3] = census_pages("bet", ["gimel"], want=16)
        DISPUTED.update(_sv)
        assert DISPUTED == _sv, "the exclusion was not restored"
        n = f = 0
        for name, cond in (
                # The navigation half of the derived disputed list. A page that offers the glyph
                # under dispute as a place to point its own answer begs the question, and the
                # loader used to take the signature.
                #
                # NOT asserted over the parsed page rows, deliberately, and the reason is a limit
                # worth writing down: a row only reaches the page while its letter is BLOCKED, and
                # the letter this defect was live on (final_nun) is not blocked today. A page-level
                # check would therefore pass on an empty set -- a probe that misses passes on
                # nothing. So it is asserted against the function, with a liveness count beside it.
                #
                # The NAMED INSTANCE, and the one that was live: p628:n2's own word was offered as
                # a final-nun exemplar. Checked against the function with its real rivals, because
                # the row only reaches the page while final_nun is blocked, and it is not today.
                ("the final-nun offer does not contain p628:n2, the span that asks the question",
                 all(r[4] != "p628:n2"
                     for r in census_pages("final_nun", ["nun", "vav", "yod"], want=16)[0])),
                # Liveness, and the over-exclusion direction in one pair. Both sides are
                # MEASURED IN THIS RUN -- the exclusion is lifted and re-applied -- so nothing is
                # pinned to a count that goes stale when the corpus does.
                #
                # A >= 12 threshold was the first version of this, and mutation proved it dead: only
                # ONE disputed span holds a rival-free final-nun word at all, so barring the glyph
                # and barring the whole span both give 25 and the threshold cannot tell them apart.
                # The discrimination is the OTHER letter.
                ("the exclusion drops the final-nun word that has nothing clean left in it",
                 _CENS[0][1] == _CENS[1][1] - 1 and len(_CENS[0][0]) >= 12),
                # p423:n3's disputed glyph is a word-2 gimel/bet, and word 1 of that span shows an
                # undisputed impression of the same letter. That word is ordinary print and must
                # still be offered -- every position barred is an exemplar this lane cannot draw.
                ("a word whose other impression is undisputed is still offered",
                 _CENS[2][1] == _CENS[3][1]),
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
                # Tier-scoped, and the scoping is itself asserted below rather than left as a
                # quietly loosened conjunct. A tier-1 letter has no exemplar of any kind; a tier-2
                # letter may have span exemplars (tav has three) and what it lacks is a signed one
                # that is rule-2 clean.
                ("every letter the page calls blocked has no exemplar from any source",
                 all(not sig_exemplars(k) and not exemplars(k, rv)
                     for k, rv in BLOCKED if TIER[k] == "blocked")),
                ("every letter the page calls a gap has no rule-2-clean signed exemplar",
                 all(not [1 for x in signed_supply(k) if not x[4]]
                     for k, _rv in BLOCKED if TIER[k] == "gap")),
                ("every blocked letter is a candidate on some card",
                 all(k in CANDS for k, _r in BLOCKED if TIER[k] == "blocked")),
                # The reason the clause above is tier-1 only, stated as a fact rather than implied
                # by its absence: final_mem is on the mem/final mem/samekh axis the legend covers
                # and NO card asks about it, so rule 2 is vacuous for it in the cards' sense.
                ("a gap letter on no card exists, which is why that clause is tier-1 only",
                 any(k not in CANDS for k, _r in BLOCKED if TIER[k] == "gap")),
                ("the page offers something to point, in at least one tier",
                 bool(BLOCKED)),
                # THE OTHER DIRECTION. Every clause above is of the form "no gap letter has a clean
                # exemplar", which a SHRINKING gap tier satisfies just as well -- the empty set
                # satisfies it best. This one fails when rule 2 stops being applied: a letter whose
                # every signed impression is dirty must be IN the ask. Derived over all the legend
                # letters, naming none, so a new signature does not break it.
                ("a legend letter whose every signed impression is rule-2 dirty is in the ask",
                 all(k in TIER for k, _rv, st in legend_letters()
                     if st["signed"] and not [1 for x in st["signed"] if not x[4]])),
                # And the subject for it, so the clause is not satisfied by there being no such
                # letter: final nun is one today, its only tile dirtied by the yod beside it.
                ("some legend letter is in that state, so the clause above has a subject",
                 any(st["signed"] and not [1 for x in st["signed"] if not x[4]]
                     for _k, _rv, st in legend_letters())),
                # A row with no rival to avoid teaches the wrong thing, and the for-all above is
                # satisfied vacuously by one. final_mem gets its rivals from the legend axis, not
                # from a card ask, and a scoping mutation would empty them silently.
                ("every offered letter has at least one rival named",
                 all(rv for _k, rv in BLOCKED)),
                ("every row's tier is printed on the page beside its letter",
                 all(("<b>%s</b>" % TIER[k]) in t for k, _r in BLOCKED)),
                ("the rivals of every offered letter are printed", bool(BLOCKED) and
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
