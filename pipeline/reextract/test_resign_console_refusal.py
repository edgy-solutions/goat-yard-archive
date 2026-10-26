# -*- coding: utf-8 -*-
u"""Born-test: the re-sign console's refusal is WIRED UP, not merely present.

`test_reversal_guard_js.py` proves the PREDICATE agrees with `signature_reversal.examine`, under node,
including by mutation.  It says nothing about whether the console ever calls it.  This lane has already
shipped a correct function that nothing called -- the counting localizer, whose `n_before` was 0 for
74 of 74 spans because `draw_pool` passed it the wrong argument and the defect hid behind a text that
usually happened to start in the right place.  A guard that is defined and never reached is that same
failure with a different name, and no in-run render check can see it: guard 3r asserts the script block
is in the document, which is a fact about the document, not about `upd()`.

So this test drives the SHIPPED document:

  * it renders the re-sign console as a subprocess (`glyph_signer.py` does load-bearing writes at
    import time, so it is never imported -- and a subprocess also means the bytes under test are the
    bytes a signer gets, not a reconstruction);
  * it takes BOTH script blocks out of that HTML and the tiles' own `data-cand` attributes, so the
    candidate the test reverses is the candidate the page carries;
  * it runs them under node against a DOM stub and calls `upd()`, which is the one function the
    console runs after every click.

WHAT IT ASSERTS.  That a complete reversal removes the download's href and names the rows; that the
verdicts are still there afterwards (ruling 4: *"never edits a signature"*); that the refusal is not
sticky -- correct the row and the download returns; and that a mutation at the CALL SITE, leaving the
predicate untouched, makes the refusal stop -- so a pass here is not a pass on nothing.

WHAT IT DOES NOT SOLVE.  It drives `upd()` directly; the click handlers that call `upd()` are not
exercised, and neither is a browser.  It says nothing about whether a reversal is the WRONG reading --
only that the console refuses to file one.  And the refusal needs a COMPLETE row: a half-filled
assembly is `length_mismatch`, which is checked here as the empty case, and is why the one-swap shape
that `p442:n0` was actually signed in only warns.

ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

CHECKS = []
FAILED = []

#: Every check this file is written to make, NOT counting the count check itself.  Asserted at the
#: end against what actually ran: an exception in a hand-rolled suite ends the run SILENTLY, and this
#: lane has lost 40 assertions that way, twice.  The count is the tripwire for that.
EXPECTED_CHECKS = 29


def ok(cond, msg):
    CHECKS.append(msg)
    if cond:
        print(u"  ok    %s" % msg)
    else:
        FAILED.append(msg)
        print(u"  FAIL  %s" % msg)


# --------------------------------------------------------------------------- the rendered document
def render(out_dir):
    u"""Render the re-sign console into `out_dir` and return its HTML path."""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.Popen([sys.executable, os.path.join(HERE, "glyph_signer.py"),
                          "--resign", "--out-dir", out_dir],
                         cwd=HERE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    so, _ = p.communicate()
    if p.returncode != 0:
        raise RuntimeError("the re-sign render failed rc=%d:\n%s"
                           % (p.returncode, so.decode("utf-8", "replace")))
    html = [f for f in sorted(os.listdir(out_dir)) if f.endswith(".html")]
    if len(html) != 1:
        raise RuntimeError("expected one console, found %r" % (html,))
    return os.path.join(out_dir, html[0]), so.decode("utf-8", "replace")


_SCRIPT = re.compile(r"<script>(.*?)</script>", re.S)
#: The tile's own identity and candidate, as the page carries them.  The test reverses THIS, so a
#: renderer that wrote a different candidate into the tile would be reversing a different string.
_TILE = re.compile(r'<div class="tile[^"]*" id="t_([^"]+?)_(\d+)" data-s="[^"]*" data-i="\d+"'
                   r' data-cand="([^"]*)"')


def blocks(html):
    u"""(guard_js, console_js) out of the document, identified by what each DEFINES."""
    found = _SCRIPT.findall(html)
    guard = [b for b in found if "function rgExamine(" in b]
    console = [b for b in found if "function upd(" in b]
    return found, guard, console


def tiles_of(html):
    u"""{span_id: [(i, candidate), ...]} in storage order, from the tile divs themselves."""
    out = {}
    for sid, i, cand in _TILE.findall(html):
        out.setdefault(sid, []).append((int(i), cand))
    return {k: sorted(v) for k, v in out.items()}


# --------------------------------------------------------------------------- the node side
_HARNESS = u"""
/* A DOM stub, and only as much of one as upd() reaches.  Any id resolves to an element, so an id this
   stub has not heard of cannot make the console throw and look like a refusal. */
function mkel(id){return {id:id,_a:{},textContent:"",className:"",style:{},
 setAttribute:function(k,v){this._a[k]=v;},
 getAttribute:function(k){return (k in this._a)?this._a[k]:null;},
 removeAttribute:function(k){delete this._a[k];if(k==="href")delete this.href;},
 addEventListener:function(){},appendChild:function(){},
 querySelector:function(){return null;},querySelectorAll:function(){return [];}};}
var EL={};
var document={getElementById:function(id){if(!EL[id])EL[id]=mkel(id);return EL[id];},
 querySelector:function(){return null;},querySelectorAll:function(){return [];},
 addEventListener:function(){},createElement:function(){return mkel("new");}};
var window={addEventListener:function(){}};
var localStorage={getItem:function(){return null;},setItem:function(){},removeItem:function(){}};
var alert=function(){};
var TILES=__TILES__;

__GUARD__
__CONSOLE__

/* The tiles carry the candidate, so the stub must too: tileShown() reads data-cand off the div. */
var sids=Object.keys(TILES),si,ti;
for(si=0;si<sids.length;si++){var s=sids[si];
 for(ti=0;ti<TILES[s].length;ti++){var t=TILES[s][ti];
  document.getElementById("t_"+s+"_"+t[0]).setAttribute("data-cand",t[1]);}}

function dlstate(){var a=document.getElementById("dl"),rb=document.getElementById("rgbar");
 return {href_present:("href" in a),text:a.textContent,rgbar:rb.textContent};}
function rowstate(s){var rec=rgRecFor(s);
 return {cand:candFor(s),derived:derivedFor(s),flag:rec.flag,refuses:rgRefuses(rec.flag),
  warns:rgWarns(rec.flag),rg_class:document.getElementById("rg_"+s).className,
  rg_text:document.getElementById("rg_"+s).textContent,
  verdicts_kept:Object.keys(trow(s).tv).length};}
function snap(){var o={dl:dlstate(),rows:{}},i;
 for(i=0;i<sids.length;i++)o.rows[sids[i]]=rowstate(sids[i]);return o;}
function setHalf(s){var r=trow(s),n=TILES[s].length,j,half=Math.ceil(n/2);
 for(j=0;j<n;j++){var t=TILES[s][j];
  if(j<half)r.tv[t[0]]={verdict:"confirmed",chose:""};else delete r.tv[t[0]];}}
function setAll(s,mode){var r=trow(s),n=TILES[s].length,j;
 for(j=0;j<n;j++){var t=TILES[s][j];
  if(mode==="confirmed")r.tv[t[0]]={verdict:"confirmed",chose:""};
  else if(mode==="reversed")r.tv[t[0]]={verdict:"corrected",chose:TILES[s][n-1-j][1]};
  else delete r.tv[t[0]];}}

var OUT={};
/* 1. nothing filled in. The save path must WORK here, or a later "href present" proves nothing. */
upd();OUT.empty=snap();
/* 1b. half of one row filled in: fewer consonants than the candidate has. */
setHalf(sids[0]);upd();OUT.half=snap();
/* 2. one row confirmed as printed: the assembly IS the candidate. */
setAll(sids[0],"confirmed");upd();OUT.confirmed=snap();
/* 3. the same row assembled backwards -- ruling 4's case. */
setAll(sids[0],"reversed");upd();OUT.reversed=snap();
/* 4. corrected back: a refusal that does not lift is a dead console, not a guard. */
setAll(sids[0],"confirmed");upd();OUT.restored=snap();
/* 5. every row backwards at once, so the message's COUNT is exercised, not just its text. */
for(si=0;si<sids.length;si++)setAll(sids[si],"reversed");
upd();OUT.all_reversed=snap();
OUT.span_ids=sids;
require("fs").writeFileSync(process.argv[2],JSON.stringify(OUT),"utf-8");
"""


def run_node(guard, console, tiles, tmp, mutate=None):
    u"""Run the console under node and return its snapshots.  `mutate` edits the CONSOLE only."""
    con = console
    if mutate is not None:
        old, new = mutate
        if con.count(old) != 1:
            raise RuntimeError("the mutation target occurs %d time(s): %r" % (con.count(old), old))
        con = con.replace(old, new, 1)
    js = (_HARNESS
          .replace("__TILES__", json.dumps(tiles, sort_keys=True))
          .replace("__GUARD__", guard)
          .replace("__CONSOLE__", con))
    jsf = os.path.join(tmp, "drive.js")
    outf = os.path.join(tmp, "out.json")
    io.open(jsf, "w", encoding="utf-8", newline="\n").write(js)
    # No `--` separator: node puts it in argv, so argv[2] would be the separator, not the file.
    p = subprocess.Popen(["node", jsf, outf], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _, se = p.communicate()
    if p.returncode != 0:
        raise RuntimeError("node failed rc=%d: %s" % (p.returncode, se.decode("utf-8", "replace")))
    return json.load(io.open(outf, encoding="utf-8"))


def main():
    tmp = tempfile.mkdtemp(prefix="resign_refusal_")
    try:
        out_dir = os.path.join(tmp, "render")
        os.makedirs(out_dir)
        path, log = render(out_dir)
        html = io.open(path, encoding="utf-8").read()

        found, guard, console = blocks(html)
        ok(len(found) == 2 and len(guard) == 1 and len(console) == 1,
           "the console ships exactly two script blocks, one defining rgExamine and one upd "
           "(found %d, guard %d, console %d)" % (len(found), len(guard), len(console)))
        guard, console = guard[0], console[0]
        ok("rgRecFor(" in console and "rgRefuses(" in console,
           "the console block itself CALLS the guard (rgRecFor and rgRefuses appear in it)")
        ok("function rgExamine(" not in console and "function rgCons(" not in console,
           "the console does not DEFINE the predicate -- it calls the generated one, so there is no "
           "second implementation to drift from signature_reversal.examine")

        tiles = tiles_of(html)
        ok(len(tiles) == 4 and sorted(tiles) == ["p254:n1", "p442:n0", "p798:n0", "p831:n2"],
           "the tiles parsed out of the document are the four audit spans: %r" % (sorted(tiles),))
        ok(all(len(v) >= 2 for v in tiles.values()) and sum(len(v) for v in tiles.values()) == 16,
           "every row has at least two tiles (a one-tile row cannot be reversed) and there are 16")
        ok(all(c.strip() for v in tiles.values() for (_i, c) in v),
           "every tile carries a non-empty data-cand, so the reversal below reverses something")

        got = run_node(guard, console, tiles, tmp)
        first = got["span_ids"][0]

        # ---- 1. the empty row: the save path works, and nothing is refused on an unfilled console
        e = got["empty"]
        ok(e["dl"]["href_present"] and "download all" in e["dl"]["text"],
           "unfilled, the download is a live link (%r)" % (e["dl"]["text"][:48],))
        ok(all(not r["refuses"] for r in e["rows"].values()),
           "unfilled, no row is refused")
        ok(all(r["flag"] == "empty_read" for r in e["rows"].values()),
           "an unfilled row derives no consonants at all: empty_read")
        ok(e["dl"]["rgbar"] == "", "unfilled, the refusal bar says nothing")

        # ---- 1b. HALF filled. This is the refusal's limit, measured rather than asserted: the
        #      comparison is consonant for consonant, so an incomplete row cannot be refused at all.
        hf = got["half"]["rows"][first]
        ok(hf["flag"] == "length_mismatch" and not hf["refuses"],
           "a half-filled row is length_mismatch and CANNOT be refused: the guard needs a complete "
           "assembly, which is why the one-swap shape p442:n0 was signed in only warns")
        ok(got["half"]["dl"]["href_present"],
           "half-filled, the download is still live -- the refusal does not fire on partial work")

        # ---- 2. confirmed as printed
        c = got["confirmed"]
        ok(c["rows"][first]["derived"] == c["rows"][first]["cand"],
           "confirming every tile derives exactly the candidate the tiles carry")
        ok(c["rows"][first]["flag"] == "read_equals_signature" and not c["rows"][first]["refuses"],
           "an assembly equal to the candidate is read_equals_signature and is not refused")
        ok(c["dl"]["href_present"], "confirmed as printed, the download stays a live link")

        # ---- 3. the reversal -- ruling 4
        r = got["reversed"]
        rf = r["rows"][first]
        ok(rf["flag"] == "reversed_exact" and rf["refuses"],
           "the backwards assembly is reversed_exact and the guard refuses it")
        ok(not r["dl"]["href_present"],
           "THE WIRING: a refused row removes the download's href, so there is nothing to click")
        ok("REFUSED" in r["dl"]["text"] and "1 row" in r["dl"]["text"],
           "the link's own text says it is refused, and for how many rows (%r)"
           % (r["dl"]["text"][:72],))
        ok(first in r["dl"]["rgbar"] and "Nothing of yours was changed" in r["dl"]["rgbar"],
           "the bar names the refused row and says the verdicts were not touched")
        ok(rf["verdicts_kept"] == len(tiles[first]),
           "NEVER EDITS A SIGNATURE: all %d verdicts survive the refusal (kept %d)"
           % (len(tiles[first]), rf["verdicts_kept"]))
        ok("refuse" in rf["rg_class"] and "RIGHTMOST" in rf["rg_text"],
           "the row's own message is styled as a refusal and says which end position 1 is")
        ok(all(not got["reversed"]["rows"][s]["refuses"] for s in got["span_ids"] if s != first),
           "only the row that was reversed is refused; the other three are untouched")

        # ---- 4. the refusal lifts
        s4 = got["restored"]
        ok(s4["dl"]["href_present"] and "download all" in s4["dl"]["text"],
           "correcting the row brings the download back -- the refusal is not sticky")
        ok(s4["dl"]["rgbar"] == "", "and the refusal bar is cleared")

        # ---- 5. all four backwards
        a = got["all_reversed"]
        ok(not a["dl"]["href_present"] and "4 row" in a["dl"]["text"],
           "four reversed rows refuse and the message counts four (%r)" % (a["dl"]["text"][:72],))
        ok(all(got["all_reversed"]["rows"][s]["refuses"] for s in got["span_ids"]),
           "every one of the four rows is individually refused")

        # ---- 6. the mutation: break the CALL SITE, leave the predicate alone
        mut = run_node(guard, console, tiles, tmp,
                       mutate=("if(rgRefuses(rec.flag))refused.push(s);", ""))
        mf = mut["reversed"]["rows"][first]
        ok(mf["flag"] == "reversed_exact",
           "mutation: the predicate still says reversed_exact, so only the wiring was cut")
        ok(mut["reversed"]["dl"]["href_present"],
           "mutation: with the push removed the download is NOT refused -- so the assertion above is "
           "live, and tied to that one call site rather than to the guard being present")

        # ---- 7. and the OTHER half of the wiring: the row message
        mut2 = run_node(guard, console, tiles, tmp,
                        mutate=('var rgel=document.getElementById("rg_"+s),rec=rgRecFor(s);',
                                'var rgel=null,rec=rgRecFor(s);'))
        ok(not mut2["reversed"]["dl"]["href_present"],
           "mutation 2: silencing the per-row message does NOT silence the refusal -- the two are "
           "separate consequences of one record, so a styling change cannot disable the guard")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # Read the count BEFORE calling ok(), which appends: a count check whose own arithmetic depends
    # on when it is evaluated is one more thing to get wrong by one.
    _n = len(CHECKS)
    ok(_n == EXPECTED_CHECKS,
       "every check this file is written to make ran: %d of %d" % (_n, EXPECTED_CHECKS))
    print(u"\nresign console refusal: %d checks, %d failed" % (len(CHECKS), len(FAILED)))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
