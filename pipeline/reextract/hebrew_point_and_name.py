"""Point-and-name: capture a signed exemplar, or a re-ratified box, without going through chat.

WHY THIS EXISTS. The 21-span signed set cannot supply the exemplars the glyph cards need -- measured,
it gives gimel 1, pe 2, and no single impression holding both letters of either pair. Chris's ruling
of 2026-09-27 opens exemplars to the whole volume: any word on any page that he reads from pixels and
names is an exemplar with signature authority. What that needs is not a bigger corpus but a RECORD --
file page, box, letter, the letter's index counted from the right of the word, signer, date -- so the
evidence is a row in a store and not a screenshot in a conversation.

WHAT THIS DELIBERATELY DOES NOT DO: it proposes nothing. It does not find words, snap a box to ink, or
guess which letter is under the cursor. The signer draws the box and names the letter; the tool does
arithmetic (display pixels -> native page pixels) and formats a line. That division is the whole
design: every machine proposal on a signing surface in this lane has to be ratifiable by looking at
the proposal itself, and a snapped box that is subtly wrong looks exactly like a snapped box that is
right.

WHAT IT DOES DO is show you the crop of the box you just drew, magnified, before you add the record --
so a mis-drawn box is visible as a mis-drawn box, here, rather than on a card three steps later.

Nothing is validated here beyond the obvious. The gate lives in `hebrew_glyph_card.sig_load` /
`rerat_load`, which refuse a record whose box is blank, runs off the page, holds more than one text
line, or whose named letter is not at the index it claims. A record captured here and refused there
is the system working: the capture surface is a convenience, the loader is the authority.

    python hebrew_point_and_name.py            # writes the capture page next to the cards
"""
import io
import os
import sys

import hebrew_aperture_diag as D
from hebrew_glyph_card import LETTER, SIGS, RERAT

OUT = D.DATA / "hebrew_point_and_name.html"
# The page images are not copied into this file and never will be: a capture surface that embeds
# scans is a corpus leaving its folder. The browser loads them from the volume by relative path --
# DERIVED from the two configured roots, not written out by hand, so moving either one cannot leave
# a hand-typed "../.." pointing at nothing. The selftest resolves it against the filesystem.
IMGREL = os.path.relpath(str(D.IMG), str(D.DATA)).replace(os.sep, "/")
FIRST = 423

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
"""

JS = """
var img = document.getElementById('page');
var stage = document.getElementById('stage');
var sel = document.getElementById('sel');
var box = null;            // native page pixels
var drag = null;

function scale(){ return img.naturalWidth / img.clientWidth; }   // native px per displayed px

function load(){
  var pg = parseInt(document.getElementById('pg').value, 10);
  if(!pg){ return; }
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

function add(){
  if(!box){ alert('Draw a box on the page first.'); return; }
  var pg = parseInt(document.getElementById('pg').value, 10);
  var signer = document.getElementById('signer').value.trim();
  var date = document.getElementById('date').value.trim();
  var mode = document.getElementById('mode').value;
  var rec;
  if(mode === 'exemplar'){
    rec = {file_page: pg, box: box, coord_space: 'native',
           word: document.getElementById('word').value.trim(),
           letter: document.getElementById('letter').value,
           letter_index_from_right: parseInt(document.getElementById('idx').value, 10),
           signer: signer, date: date,
           note: document.getElementById('note').value.trim() || undefined};
  } else {
    rec = {span_id: document.getElementById('span').value.trim(), file_page: pg,
           new_box: box, coord_space: 'native',
           old_box_state: document.getElementById('oldstate').value,
           text: document.getElementById('word').value.trim(),
           signer: signer, date: date,
           basis: 'signed-from-the-page via point-and-name',
           note: document.getElementById('note').value.trim() || undefined};
  }
  var ta = document.getElementById('out');
  ta.value += JSON.stringify(rec) + '\\n';
  ta.scrollTop = ta.scrollHeight;
}

function dl(){
  var mode = document.getElementById('mode').value;
  var name = mode === 'exemplar' ? 'hebrew_exemplar_signatures.jsonl' : 'hebrew_box_reratify.jsonl';
  var b = new Blob([document.getElementById('out').value], {type: 'application/x-ndjson'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(b); a.download = name; a.click();
}
function modeChange(){
  var ex = document.getElementById('mode').value === 'exemplar';
  document.getElementById('exfields').style.display = ex ? '' : 'none';
  document.getElementById('rrfields').style.display = ex ? 'none' : '';
  document.getElementById('wordlbl').textContent = ex ? 'the whole word' : 'the text you read';
  document.getElementById('dest').textContent = ex ? SIGS : RERAT;
}
img.addEventListener('load', function(){ fit(); });
modeChange();
"""


def build():
    opts = "".join('<option value="%s">%s %s</option>' % (k, k, v)
                   for k, v in sorted(LETTER.items()))
    h = ['<!doctype html><meta charset="utf-8"><title>Point and name</title>',
         "<style>%s</style>" % CSS,
         '<header><h1>Point and name &mdash; capture a signed exemplar or a re-ratified box</h1>',
         '<div class="mut">All page numbers are FILE pages; printed = file &minus; 88. '
         'Nothing here is proposed by the machine: you draw the box and you name the letter. The '
         'crop of the box you drew is shown magnified before you add it, so a mis-drawn box is '
         'visible now rather than on a card later. Records are refused on load if the box is blank, '
         'runs off the page, holds more than one text line, or the letter is not at the index you '
         'gave &mdash; that check is the authority, not this page.</div>',
         '<div class="bar">',
         '<label>file page</label><input id="pg" size="6" value="%d">' % FIRST,
         '<button onclick="load()">load</button>',
         '<button onclick="zoom(1.6)">+</button><button onclick="zoom(0.625)">&minus;</button>',
         '<button onclick="fit()">fit</button>',
         '<label>mode</label><select id="mode" onchange="modeChange()">'
         '<option value="exemplar">exemplar signature</option>'
         '<option value="rerat">box re-ratification</option></select>',
         '<label>signer</label><input id="signer" size="8" value="Chris">',
         '<label>date</label><input id="date" size="10" value="2026-09-27">',
         "</div></header>",
         '<div class="wrap"><div class="pane"><div class="scroll"><div id="stage">',
         '<img id="page" src="%s/page%d_image1.png"><div id="sel"></div>' % (IMGREL, FIRST),
         "</div></div></div>",
         '<div class="side">',
         '<div class="box"><div class="mut">the box you drew, magnified</div>',
         '<canvas id="crop" width="10" height="10"></canvas>',
         '<div class="mut" id="info" style="margin-top:6px"></div></div>',
         '<div class="box">',
         '<div><label id="wordlbl">the whole word</label><br>'
         '<input id="word" dir="auto" size="20" placeholder=""></div>',
         '<div id="exfields" style="margin-top:8px">',
         '<label>letter</label> <select id="letter">%s</select> ' % opts,
         '<label>index from the right of the word</label> <input id="idx" size="3" value="1">',
         '<div class="warn">Count the letter in the WORD, from the right: Hebrew is stored in '
         'reading order, so glyph N from the right is character N. The loader checks this against '
         'the word you typed and refuses the record if they disagree, which is what catches an '
         'off-by-one before it reaches a card.</div></div>',
         '<div id="rrfields" style="display:none;margin-top:8px">',
         '<label>span id</label> <input id="span" size="10" placeholder="p912:n2"> ',
         '<label>what was wrong with the old box</label> <select id="oldstate">'
         '<option value="blank-no-ink">blank &mdash; no ink</option>'
         '<option value="clipped-partial-text">clipped &mdash; held part of the text</option>'
         '<option value="out-of-bounds-clamped">out of bounds &mdash; silently clamped</option>'
         '</select>',
         '<div class="warn">This one record ratifies the new box and retires the old rect together. '
         'The (box, text) binding is one object, so the text you type here is the text you read from '
         'THIS box.</div></div>',
         '<div style="margin-top:8px"><label>note (optional)</label><br>'
         '<input id="note" size="34"></div>',
         '<div class="bar"><button class="go" onclick="add()">add record</button>'
         '<button onclick="dl()">download</button></div></div>',
         '<div class="box"><div class="mut">append these lines to <span class="k" id="dest"></span>'
         '</div><textarea id="out" spellcheck="false"></textarea></div>',
         "</div></div>",
         "<script>var IMGREL=%s;var SIGS=%s;var RERAT=%s;\n%s</script>"
         % (_q(IMGREL), _q(str(SIGS)), _q(str(RERAT)), JS)]
    OUT.write_text("\n".join(h), encoding="utf-8")
    return OUT


def _q(s):
    return '"%s"' % s.replace("\\", "\\\\").replace('"', '\\"')


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        p = build()
        t = io.open(p, encoding="utf-8").read()
        n = f = 0
        for name, cond in (
                ("no page image is embedded in the capture page", "base64," not in t),
                ("the images are referenced by relative path", IMGREL in t),
                # The one piece of arithmetic on this page that a reader cannot check by eye is the
                # relative path the browser will follow. Resolve it for real.
                ("the relative image path resolves to a page that exists",
                 (D.DATA / IMGREL / ("page%d_image1.png" % FIRST)).exists()),
                ("every Hebrew letter is offered", all(k in t for k in LETTER)),
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
