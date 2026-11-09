"""render_body_console -- stage 4 of the 20-page body shadow run: a verdict-only, BLINDED console.

One card per sampled hunk of the stage-3 diff: the chunk crop (native resolution PNG), the hunk
with +-6 tokens of context, and two texts A and B. A seeded coin per card decides which of A and B
is the old text. The coin lives ONLY in key.json (card_id -> which side is old, plus the stratum),
which is written next to index.html but never referenced, named or embedded by it; the HTML even
avoids the words old/new. Verdicts: A matches page / B matches page / neither / both / can't tell,
stored in localStorage keyed by card_id, exported as JSONL {card_id, verdict}.
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


def build_cards(sample, seed):
    cards = []
    for stratum, h in sample:
        cid = card_id_for(h["file_page"], h["opcode_idx"], seed)
        a_old = old_is_a(seed, cid)
        old = {"before": h["old_before"], "text": h["old_text"], "after": h["old_after"]}
        new = {"before": h["new_before"], "text": h["new_text"], "after": h["new_after"]}
        cards.append({"card_id": cid, "stratum": stratum, "file_page": h["file_page"],
                      "opcode_idx": h["opcode_idx"], "old_side": "A" if a_old else "B",
                      "A": old if a_old else new, "B": new if a_old else old,
                      "flags": h["flags"], "chunk": h.get("chunk")})
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
.verdicts button{background:var(--btn);color:var(--fg);border:1px solid var(--line);border-radius:4px;padding:6px 10px;margin:2px;cursor:pointer}
.verdicts button.on{outline:3px solid #2a7;font-weight:700}
"""

_JS = """
function load(id){try{return localStorage.getItem('verdict:'+id)}catch(e){return null}}
function save(id,v){try{localStorage.setItem('verdict:'+id,v)}catch(e){}}
function paint(card,v){card.querySelectorAll('button').forEach(function(b){
  b.classList.toggle('on',b.dataset.v===v)})}
document.querySelectorAll('.card').forEach(function(card){
  var id=card.dataset.id;paint(card,load(id));
  card.querySelectorAll('button').forEach(function(b){
    b.addEventListener('click',function(){save(id,b.dataset.v);paint(card,b.dataset.v)})})});
document.getElementById('export').addEventListener('click',function(){
  var lines=[];document.querySelectorAll('.card').forEach(function(card){
    var v=load(card.dataset.id);if(v){lines.push(JSON.stringify({card_id:card.dataset.id,verdict:v}))}});
  var a=document.createElement('a');
  a.href='data:text/plain;charset=utf-8,'+encodeURIComponent(lines.join('\\n')+'\\n');
  a.download='verdicts.jsonl';document.body.appendChild(a);a.click();a.remove()});
"""


def render_html(cards, seed):
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             f"<title>Body shadow console</title><style>{_CSS}</style></head><body>",
             f"<h1>Body shadow console</h1><p class=\"meta\">{len(cards)} cards. "
             "Judge each against the page image only. "
             '<button id="export">Export JSONL</button></p>']
    for i, c in enumerate(cards, 1):
        img = (f'<img src="crops/{c["card_id"]}.png" alt="page crop">' if c["chunk"]
               else "<i>(no crop: no text on the right-hand side of this hunk's page)</i>")
        btns = "".join(f'<button data-v="{v}">{html.escape(lbl)}</button>' for v, lbl in VERDICTS)
        parts.append(
            f'<div class="card" data-id="{c["card_id"]}">'
            f'<div class="meta">#{i} &middot; page {c["file_page"]} &middot; {c["card_id"]}</div>'
            f'{img}{_side_html("A", c["A"])}{_side_html("B", c["B"])}'
            f'<div class="verdicts">{btns}</div></div>')
    parts.append(f"<script>{_JS}</script></body></html>")
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
    for c in cards:
        if not c["chunk"]:
            continue
        fp = c["file_page"]
        if fp not in grays:
            want = body_header["config"]["png_sha256"].get(str(fp))
            have = BSB.png_sha256(args.volume_dir, fp)
            if want != have:
                raise ValueError(f"page {fp} PNG differs from the pixels the body run read "
                                 f"({have} != {want})")
            grays[fp] = BVR.load_page_gray(args.volume_dir, fp)
        (out_dir / "crops" / f"{c['card_id']}.png").write_bytes(
            BSB.crop_png_bytes(grays[fp], c["chunk"]["box"]))
    (out_dir / "index.html").write_text(render_html(cards, args.seed), encoding="utf-8")
    key = {"seed": args.seed, "diff_config_hash": diff_header["config_hash"],
           "cards": {c["card_id"]: {"old_side": c["old_side"], "stratum": c["stratum"],
                                    "file_page": c["file_page"], "opcode_idx": c["opcode_idx"]}
                     for c in cards}}
    (out_dir / "key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    print(f"{len(cards)} cards -> {out_dir / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
