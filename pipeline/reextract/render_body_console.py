"""render_body_console -- stage 4 of the 20-page body shadow run: a verdict-only, BLINDED console.

One card per sampled hunk of the stage-3 diff: the chunk crop (native resolution PNG), the hunk
with +-6 tokens of context, and two texts A and B. A seeded coin per card decides which of A and B
is the old text. The coin lives ONLY in key.json (card_id -> which side is old, plus the stratum),
which is written next to index.html but never referenced, named or embedded by it; the HTML even
avoids the words old/new. Verdicts: A matches page / B matches page / neither / both / can't tell,
stored in localStorage keyed by console + card_id, exported as JSONL {card_id, verdict, carried}.
score_body_console.py un-blinds an export with key.json.

Strata (the lock): every disputed_head hunk; up to 10 verse_boundary; up to 3 content per page,
balanced on non_latin (alternating, non_latin first); 5 ws_punct as a classifier audit. All draws
use random.Random(seed); the seed is recorded in key.json.

The console never says which text is the old reference and never says "wrong": the page decides.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_body_shadow as BSB  # noqa: E402
import build_verse_regions as BVR  # noqa: E402

MAX_VERSE_BOUNDARY = 10
MAX_CONTENT_PER_PAGE = 3
N_WS_PUNCT = 5
# px. The tallest usable chunk in the reference body run (a covering box taller than this was never
# a thing a model was shown at once, so the console does not card it).
COVER_MAX_H = 2616
VERDICTS = (("A", "A matches page"), ("B", "B matches page"), ("neither", "neither"),
            ("both", "both"), ("cant_tell", "can't tell"))


def card_id_for(file_page, opcode_idx, seed):
    return hashlib.sha256(f"{file_page}:{opcode_idx}:{seed}".encode()).hexdigest()[:16]


def old_is_a(seed, card_id):
    """The seeded coin: True when text A is the old text."""
    return random.Random(f"{seed}:{card_id}:coin").random() < 0.5


def sample_hunks(hunks, seed):
    """-> [(stratum, hunk), ...]. Deterministic in (hunks, seed): hunks are first put in
    (file_page, opcode_idx) order, then every draw comes from one random.Random(seed)."""
    rng = random.Random(seed)
    hs = sorted(hunks, key=lambda h: (h["file_page"], h["opcode_idx"]))
    out = [("disputed_head", h) for h in hs if h["class"] == "disputed_head"]
    vb = [h for h in hs if h["class"] == "verse_boundary"]
    out += [("verse_boundary", h) for h in rng.sample(vb, min(MAX_VERSE_BOUNDARY, len(vb)))]
    for fp in sorted({h["file_page"] for h in hs}):
        nl = [h for h in hs if h["class"] == "content" and h["file_page"] == fp and h["flags"]["non_latin"]]
        la = [h for h in hs if h["class"] == "content" and h["file_page"] == fp and not h["flags"]["non_latin"]]
        rng.shuffle(nl)
        rng.shuffle(la)
        pick, turn = [], 0
        while len(pick) < MAX_CONTENT_PER_PAGE and (nl or la):
            src = (nl, la)[turn % 2] or (la, nl)[turn % 2]
            pick.append(src.pop(0))
            turn += 1
        out += [("content", h) for h in pick]
    ws = [h for h in hs if h["class"] == "ws_punct"]
    out += [("ws_punct", h) for h in rng.sample(ws, min(N_WS_PUNCT, len(ws)))]
    return out


def cover_for(hunk):
    """Pure. The one image a card shows must contain EVERY read chunk of the hunk's new text.
    -> {"cardable", "reason": None|"old_only"|"too_tall", "cover_box", "read_crops"}.
    A hunk from a diff built before `span_chunks` existed is refused (ValueError), never rendered
    with the old single-crop behaviour."""
    if "span_chunks" not in hunk:
        raise ValueError(f"hunk page {hunk.get('file_page')} opcode {hunk.get('opcode_idx')} has no "
                         "span_chunks: rebuild the diff with the current diff_body_shadow")
    crops = hunk["span_chunks"]
    if not crops:
        return {"cardable": False, "reason": "old_only", "cover_box": None, "read_crops": []}
    boxes = [c["box"] for c in crops]
    cover = [min(b[0] for b in boxes), min(b[1] for b in boxes),
             max(b[2] for b in boxes), max(b[3] for b in boxes)]
    for b in boxes:
        assert cover[0] <= b[0] and cover[1] <= b[1] and b[2] <= cover[2] and b[3] <= cover[3], \
            f"read box {b} outside cover {cover}"
    if cover[3] - cover[1] > COVER_MAX_H:
        return {"cardable": False, "reason": "too_tall", "cover_box": cover, "read_crops": crops}
    return {"cardable": True, "reason": None, "cover_box": cover, "read_crops": crops}


def build_cards(sample, seed):
    cards = []
    for stratum, h in sample:
        cid = card_id_for(h["file_page"], h["opcode_idx"], seed)
        a_old = old_is_a(seed, cid)
        old = {"before": h["old_before"], "text": h["old_text"], "after": h["old_after"]}
        new = {"before": h["new_before"], "text": h["new_text"], "after": h["new_after"]}
        cover = cover_for(h)
        cards.append({"card_id": cid, "stratum": stratum, "file_page": h["file_page"],
                      "opcode_idx": h["opcode_idx"], "old_side": "A" if a_old else "B",
                      "A": old if a_old else new, "B": new if a_old else old,
                      "flags": h["flags"], "chunk": h.get("chunk"), "cover": cover,
                      "carry_eligible": bool(cover["cardable"]
                                             and cover["cover_box"] == (h.get("chunk") or {}).get("box"))})
    return cards


def _side_html(label, side):
    text = html.escape(side["text"]) if side["text"] else "<i>(nothing)</i>"
    return (f'<div class="side"><b>{label}</b> {html.escape(side["before"])} '
            f'<mark>{text}</mark> {html.escape(side["after"])}</div>')


_CSS = """
:root{--bg:#fafafa;--fg:#1a1a1a;--card:#fff;--line:#c8c8c8;--mark:#ffe58a;--btn:#eee}
@media (prefers-color-scheme:dark){:root{--bg:#161616;--fg:#e8e8e8;--card:#212121;--line:#444;--mark:#6b5a10;--btn:#333}}
body{background:var(--bg);color:var(--fg);font:16px/1.45 Georgia,serif;margin:0;padding:12px 16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:6px;margin:14px 0;padding:10px}
.card img{max-width:100%;border:1px solid var(--line)}
.side{margin:6px 0;white-space:pre-wrap}
mark{background:var(--mark);color:inherit}
.meta{font:12px monospace;opacity:.7}
.wrap{position:relative;display:inline-block;max-width:100%}
.wrap img{display:block;max-width:100%;height:auto}
.ol{position:absolute;box-sizing:border-box;border:2px solid #e22;pointer-events:none}
.ol i{position:absolute;top:0;left:0;background:#e22;color:#fff;font:11px monospace;padding:0 3px}
.tag{font:12px monospace;color:#2a7}
.verdicts button{background:var(--btn);color:var(--fg);border:1px solid var(--line);border-radius:4px;padding:6px 10px;margin:2px;cursor:pointer}
.verdicts button.on{outline:3px solid #2a7;font-weight:700}
"""

_JS = """
var NS='verdict:'+CONSOLE+':', NC='carried:'+CONSOLE+':';
var KNOWN={A:1,B:1,neither:1,both:1,cant_tell:1};
function load(id){try{return localStorage.getItem(NS+id)}catch(e){return null}}
function save(id,v){try{localStorage.setItem(NS+id,v)}catch(e){}}
function carried(id){try{return localStorage.getItem(NC+id)==='1'}catch(e){return false}}
function setCarried(id,on){try{if(on){localStorage.setItem(NC+id,'1')}else{localStorage.removeItem(NC+id)}}catch(e){}}
function paint(card){var v=load(card.dataset.id);
  card.querySelectorAll('button').forEach(function(b){b.classList.toggle('on',b.dataset.v===v)});
  card.querySelector('.tag').textContent=(v&&carried(card.dataset.id))?'carried from previous console':''}
document.querySelectorAll('.card').forEach(function(card){
  var id=card.dataset.id;paint(card);
  card.querySelectorAll('button').forEach(function(b){
    b.addEventListener('click',function(){save(id,b.dataset.v);setCarried(id,false);paint(card)})})});
document.getElementById('export').addEventListener('click',function(){
  var lines=[];document.querySelectorAll('.card').forEach(function(card){
    var id=card.dataset.id,v=load(id);
    if(v){lines.push(JSON.stringify({card_id:id,verdict:v,carried:carried(id)}))}});
  var a=document.createElement('a');
  a.href='data:text/plain;charset=utf-8,'+encodeURIComponent(lines.join('\\n')+'\\n');
  a.download='verdicts.jsonl';document.body.appendChild(a);a.click();a.remove()});
document.getElementById('import').addEventListener('change',function(ev){
  var f=ev.target.files[0];if(!f){return}
  f.text().then(function(txt){
    var applied=0,discarded=0,kept=0;
    txt.split('\\n').forEach(function(ln){
      if(!ln.trim()){return}
      var r;try{r=JSON.parse(ln)}catch(e){discarded++;return}
      var card=null;document.querySelectorAll('.card').forEach(function(c){
        if(r&&c.dataset.id===r.card_id){card=c}});
      if(!card||card.dataset.carry!=='1'||!KNOWN.hasOwnProperty(r.verdict)){discarded++;return}
      if(load(card.dataset.id)){kept++;return}
      save(card.dataset.id,r.verdict);setCarried(card.dataset.id,true);paint(card);applied++});
    document.getElementById('imported').textContent=
      'applied '+applied+', discarded '+discarded+' (ineligible, unknown or malformed rows), '+
      'kept '+kept+' (card already had a verdict)'})});
"""

_REASON = {"old_only": "no read crop contains this text",
           "too_tall": "covering crop taller than {} px".format(COVER_MAX_H)}


def render_html(cards, seed, console="console"):
    live = [(i, c) for i, c in enumerate(cards, 1) if c["cover"]["cardable"]]
    dead = [(i, c) for i, c in enumerate(cards, 1) if not c["cover"]["cardable"]]
    cjs = json.dumps(console).replace("</", "<\\/")
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             f"<title>Body shadow console</title><style>{_CSS}</style></head><body>",
             f"<h1>Body shadow console</h1><p class=\"meta\">{len(live)} cards. "
             "Judge each against the page image only. The image on each card is cut by the console "
             "from the outlined crop(s) that a model read for ONE of the two texts; the other text "
             "was read from the whole page image. "
             '<button id="export">Export JSONL</button> '
             'Import previous verdicts: <input type="file" id="import" accept=".jsonl,.txt"> '
             '<span id="imported"></span></p>']
    for i, c in live:
        cx0, cy0, cx1, cy1 = c["cover"]["cover_box"]
        cw, ch = cx1 - cx0, cy1 - cy0
        ols = "".join(
            f'<div class="ol" style="left:{(r["box"][0] - cx0) / cw * 100:.4f}%;'
            f'top:{(r["box"][1] - cy0) / ch * 100:.4f}%;'
            f'width:{(r["box"][2] - r["box"][0]) / cw * 100:.4f}%;'
            f'height:{(r["box"][3] - r["box"][1]) / ch * 100:.4f}%"><i>{n}</i></div>'
            for n, r in enumerate(c["cover"]["read_crops"], 1))
        img = f'<div class="wrap"><img src="crops/{c["card_id"]}.png" alt="page crop">{ols}</div>'
        btns = "".join(f'<button data-v="{v}">{html.escape(lbl)}</button>' for v, lbl in VERDICTS)
        parts.append(
            f'<div class="card" data-id="{c["card_id"]}" data-carry="{1 if c["carry_eligible"] else 0}">'
            f'<div class="meta">#{i} &middot; page {c["file_page"]} &middot; {c["card_id"]} '
            f'&middot; read crops: {len(c["cover"]["read_crops"])} <span class="tag"></span></div>'
            f'{img}{_side_html("A", c["A"])}{_side_html("B", c["B"])}'
            f'<div class="verdicts">{btns}</div></div>')
    parts.append(f'<h2>Not cardable</h2><p class="meta">{len(dead)} hunks have no single image that '
                 "shows the text they were read from; they get no card and no verdict.</p><ul>")
    for i, c in dead:
        parts.append(f'<li class="meta">#{i} &middot; page {c["file_page"]} &middot; {c["card_id"]}'
                     f' &middot; {_REASON[c["cover"]["reason"]]}</li>')
    parts.append(f"</ul><script>var CONSOLE={cjs};{_JS}</script></body></html>")
    return "\n".join(parts)


def build_arg_parser():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--diff", required=True)
    ap.add_argument("--body", required=True)
    ap.add_argument("--volume-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--seed", type=int, required=True)
    return ap


def _jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    out_dir = BVR.validate_out_path(args.out_dir)
    if (out_dir / "index.html").exists() or (out_dir / "key.json").exists():
        print(f"REFUSED: {out_dir} already holds a console; never clobbered", file=sys.stderr)
        return 2
    diff = _jsonl(args.diff)
    body_header = next(r for r in _jsonl(args.body) if r["kind"] == "run_header")
    diff_header = next(r for r in diff if r["kind"] == "diff_header")
    if diff_header["config"]["body_config_hash"] != body_header["config_hash"]:
        raise ValueError("diff was built from a different body run than --body "
                         f"({diff_header['config']['body_config_hash']} != {body_header['config_hash']})")
    cards = build_cards(sample_hunks([r for r in diff if r["kind"] == "hunk"], args.seed), args.seed)
    (out_dir / "crops").mkdir(parents=True, exist_ok=True)
    grays = {}
    crops_meta = {}
    for c in cards:
        cov = c["cover"]
        crops_meta[c["card_id"]] = {"cardable": cov["cardable"], "reason": cov["reason"],
                                    "cover_box": cov["cover_box"], "carry_eligible": c["carry_eligible"],
                                    "read_crops": []}
        if not cov["read_crops"]:
            continue
        fp = c["file_page"]
        if fp not in grays:
            want = body_header["config"]["png_sha256"].get(str(fp))
            have = BSB.png_sha256(args.volume_dir, fp)
            if want != have:
                raise ValueError(f"page {fp} PNG differs from the pixels the body run read "
                                 f"({have} != {want})")
            grays[fp] = BVR.load_page_gray(args.volume_dir, fp)
        for r in cov["read_crops"]:
            crops_meta[c["card_id"]]["read_crops"].append(
                {"key": r["key"], "stage1_line": r["stage1_line"], "chunk_idx": r["chunk_idx"],
                 "rect_idx": r["rect_idx"], "box": r["box"],
                 "sha256": hashlib.sha256(BSB.crop_png_bytes(grays[fp], r["box"])).hexdigest()})
        if cov["cardable"]:
            (out_dir / "crops" / f"{c['card_id']}.png").write_bytes(
                BSB.crop_png_bytes(grays[fp], cov["cover_box"]))
    (out_dir / "index.html").write_text(render_html(cards, args.seed, out_dir.name), encoding="utf-8")
    (out_dir / "crops.json").write_text(json.dumps(crops_meta, indent=1), encoding="utf-8")
    key = {"seed": args.seed, "diff_config_hash": diff_header["config_hash"],
           "cards": {c["card_id"]: {"old_side": c["old_side"], "stratum": c["stratum"],
                                    "file_page": c["file_page"], "opcode_idx": c["opcode_idx"]}
                     for c in cards}}
    (out_dir / "key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    print(f"{sum(c['cover']['cardable'] for c in cards)} cards "
          f"({sum(not c['cover']['cardable'] for c in cards)} not cardable) -> {out_dir / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
