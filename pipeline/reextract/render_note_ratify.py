"""Note-box ratify console — the truth-set sitting for the note-start detector (and the first navigation
metadata). Per page: the presplit strip with a proposed note-box per DETECTED note-start; you CONFIRM /
ADJUST (drag+resize) / REJECT each, and ADD a box for any note the detector missed. Verdict-only JSONL
export with provenance (proposed-by: detector, ratified-by: human) and the coordinate convention stated once
in the header. The exported set is the truth for the detector's precision/recall AND the seed navigation
metadata. Coordinates are STRIP pixels (cv_footnote_presplit's stacked reading-order strip); the strip→native
un-stacking (note_region) is applied downstream so a stitched note becomes per-column native rects.

Usage: python render_note_ratify.py  ->  writes note_box_ratify_<date>.html next to the proposals."""
import base64, io, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import numpy as np
from PIL import Image
import cv_footnote_presplit as ps
import note_region as NR

DATA = Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits")
IMG = Path("C:/Users/cnogr/git/dr-voluminous/commentary/volume1")
DATE = "20260906"

def _nnotes():
    m = {}
    for line in open(Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/vol1_apparatus.jsonl"), encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if "page" in r:
            m[r["page"]] = len(r.get("notes", []))
    return m

def _b64(im):
    b = io.BytesIO(); im.convert("L").save(b, format="PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()

def build(pages):
    nn = _nnotes()
    cards = []
    for pg in pages:
        strip, info = ps.presplit(str(IMG / f"page{pg}_image1.png"), upscale=1)
        if strip is None:
            continue
        regs, meta = NR.propose_regions(strip, info)
        cards.append(dict(page=pg, sw=strip.width, sh=strip.height, mode=info.get("mode"),
                          n_extractor=nn.get(pg), n_detected=len(regs),
                          proposed=[r["strip_box"] for r in regs],
                          column_bands=meta["column_bands"], img=_b64(strip)))
    html = _TEMPLATE.replace("/*DATA*/", json.dumps(cards)).replace("{DATE}", DATE).replace("{N}", str(len(cards)))
    out = DATA / f"note_box_ratify_{DATE}.html"
    out.write_text(html, encoding="utf-8")
    tot = sum(c["n_detected"] for c in cards); ext = sum(c["n_extractor"] or 0 for c in cards)
    print(f"wrote {out} ({out.stat().st_size//1024} KB, {len(cards)} pages, {tot} proposed boxes vs {ext} extractor notes)")

_TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Note-box ratify — vol1 {DATE}</title><style>
:root{--paper:#f6f4ee;--ink:#1a1a1a;--rule:#cbc5b6;--accent:#2f6b8f;--ok:#2f7d4f;--rej:#9a2b2b;--add:#7a4bb0;--sans:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);line-height:1.4}
header{position:sticky;top:0;background:#26302f;color:#f2efe6;padding:10px 16px;display:flex;gap:16px;align-items:center;z-index:9;border-bottom:2px solid var(--accent)}
header h1{font-size:15px;margin:0}header .stat{font-size:13px;opacity:.85}header button{background:var(--accent);color:#fff;border:0;padding:7px 14px;border-radius:5px;font-size:13px;cursor:pointer}
header .sp{margin-left:auto}
.card{max-width:1500px;margin:14px auto;background:#fff;border:1px solid var(--rule);border-radius:7px;overflow:hidden}
.meta{display:flex;gap:14px;align-items:baseline;padding:8px 12px;border-bottom:1px solid var(--rule);flex-wrap:wrap;font-size:13px}
.meta .id{font-weight:700;font-size:14px}.meta .warn{color:var(--rej);font-weight:600}.meta .ok{color:var(--ok);font-weight:600}
.hint{font-size:12px;color:#6b6459}
.stage{position:relative;overflow:auto;background:#faf9f5;max-height:78vh;cursor:crosshair}
.stage img{display:block}
.nb{position:absolute;border:2px solid var(--accent);background:rgba(47,107,143,.10);cursor:move}
.nb.rej{border-color:var(--rej);background:rgba(154,43,43,.10);border-style:dashed}
.nb.add{border-color:var(--add);background:rgba(122,75,176,.12)}
.nb .tag{position:absolute;left:0;top:-16px;font:11px ui-monospace,monospace;background:#fff;padding:0 3px;border:1px solid var(--rule)}
.nb .x{position:absolute;right:-9px;top:-9px;width:17px;height:17px;border-radius:50%;background:var(--rej);color:#fff;font-size:12px;line-height:15px;text-align:center;cursor:pointer;border:0}
.nb .h{position:absolute;width:11px;height:11px;background:#fff;border:2px solid var(--accent);right:-6px;bottom:-6px;cursor:nwse-resize}
</style></head><body>
<header><h1>Note-box ratify · vol1</h1><span class="stat" id="stat"></span>
<span class="sp"></span><button id="export">Export note-box truth JSONL</button></header>
<div id="cards"></div>
<script>
const CARDS=/*DATA*/, KEY="notebox_"+"{DATE}";
let state=JSON.parse(localStorage.getItem(KEY)||"{}");
function save(){localStorage.setItem(KEY,JSON.stringify(state));stat();}
function stat(){let done=Object.keys(state).length;document.getElementById("stat").textContent=done+" / {N} pages touched";}
CARDS.forEach(c=>{
  const disp=Math.min(c.sw,1400), sc=disp/c.sw;
  if(!state[c.page]) state[c.page]={boxes:c.proposed.map(b=>({box:b,st:"confirm",src:"detector"}))};
  const S=state[c.page];
  const card=document.createElement("div");card.className="card";card.id="c"+c.page;
  const warn = c.n_detected!==c.n_extractor;
  card.innerHTML=`<div class="meta"><span class="id">p${c.page}</span>
    <span>extractor notes: <b>${c.n_extractor}</b></span>
    <span class="${warn?'warn':'ok'}">detected: ${c.n_detected}${warn?' — check for missed/extra':' ✓'}</span>
    <span class="hint">${c.mode} · strip ${c.sw}×${c.sh}</span>
    <span class="hint">drag=move · corner=resize · ✕=reject · drag on empty area=ADD a missed note</span></div>
    <div class="stage" style="width:${disp}px"><img src="${c.img}" style="width:${disp}px"></div>`;
  document.getElementById("cards").appendChild(card);
  const stage=card.querySelector(".stage");
  function pt(e){const r=stage.getBoundingClientRect();return[(e.clientX-r.left+stage.scrollLeft)/sc,(e.clientY-r.top+stage.scrollTop)/sc];}
  function render(){
    [...stage.querySelectorAll(".nb")].forEach(n=>n.remove());
    S.boxes.forEach((bx,i)=>{
      if(bx.st==="deleted")return;
      const[x0,y0,x1,y1]=bx.box;const d=document.createElement("div");
      d.className="nb"+(bx.st==="reject"?" rej":"")+(bx.src==="human"?" add":"");
      d.style.left=x0*sc+"px";d.style.top=y0*sc+"px";d.style.width=(x1-x0)*sc+"px";d.style.height=(y1-y0)*sc+"px";
      d.innerHTML=`<span class="tag">${i+1}${bx.src==="human"?"+":""}</span><button class="x">${bx.st==="reject"?"↺":"✕"}</button><div class="h"></div>`;
      d.querySelector(".x").onclick=ev=>{ev.stopPropagation();bx.st=bx.st==="reject"?"confirm":"reject";save();render();};
      d.addEventListener("mousedown",ev=>{if(ev.target.classList.contains("x"))return;
        const rz=ev.target.classList.contains("h");const[px,py]=pt(ev);drag={i,rz,px,py,box:bx.box.slice()};ev.stopPropagation();ev.preventDefault();});
      stage.appendChild(d);
    });
  }
  let drag=null,adding=null;
  stage.addEventListener("mousedown",e=>{if(e.target!==stage&&e.target.tagName!=="IMG")return;
    const[px,py]=pt(e);adding={x0:px,y0:py};});
  window.addEventListener("mousemove",e=>{
    if(drag){const[px,py]=pt(e);const dx=px-drag.px,dy=py-drag.py;let b=drag.box.slice();
      if(drag.rz){b[2]=Math.max(b[0]+8,b[2]+dx);b[3]=Math.max(b[1]+8,b[3]+dy);}
      else{b=[b[0]+dx,b[1]+dy,b[2]+dx,b[3]+dy];}
      S.boxes[drag.i].box=b.map(Math.round);if(S.boxes[drag.i].st!=="reject")S.boxes[drag.i].st="adjust";render();}
    else if(adding){const[px,py]=pt(e);adding.x1=px;adding.y1=py;render();
      const d=document.createElement("div");d.className="nb add";
      const x0=Math.min(adding.x0,px),y0=Math.min(adding.y0,py);
      d.style.left=x0*sc+"px";d.style.top=y0*sc+"px";d.style.width=Math.abs(px-adding.x0)*sc+"px";d.style.height=Math.abs(py-adding.y0)*sc+"px";
      stage.appendChild(d);}});
  window.addEventListener("mouseup",e=>{
    if(drag){drag=null;save();}
    else if(adding){const dx=Math.abs((adding.x1||adding.x0)-adding.x0),dy=Math.abs((adding.y1||adding.y0)-adding.y0);
      if(dx>12&&dy>8){const x0=Math.min(adding.x0,adding.x1),y0=Math.min(adding.y0,adding.y1);
        S.boxes.push({box:[x0,y0,adding.x1<adding.x0?adding.x0:adding.x1,adding.y1<adding.y0?adding.y0:adding.y1].map(Math.round),st:"adjust",src:"human"});save();}
      adding=null;render();}});
  render();
});
stat();
document.getElementById("export").onclick=()=>{
  const lines=[];
  lines.push(JSON.stringify({kind:"note_box_truth_header",coordinate_convention:"cv_footnote_presplit stacked reading-order strip, pixels; un-stack to native via note_region",date:"{DATE}",door:"human-note-box-ratify"}));
  CARDS.forEach(c=>{const S=state[c.page]||{boxes:[]};
    const kept=S.boxes.filter(b=>b.st!=="reject"&&b.st!=="deleted");
    lines.push(JSON.stringify({page:c.page,strip_size:[c.sw,c.sh],column_bands:c.column_bands,
      n_extractor:c.n_extractor,n_ratified:kept.length,
      notes:kept.map(b=>({strip_box:b.box,status:b.st,proposed_by:b.src==="human"?"human":"detector"})),
      provenance:{ratified_by:"human",session_freshness:"in-context-WARN"}}));});
  const blob=new Blob([lines.join("\n")],{type:"application/x-ndjson"});const a=document.createElement("a");
  a.href=URL.createObjectURL(blob);a.download="note_box_truth_{DATE}.jsonl";a.click();};
</script></body></html>"""

if __name__ == "__main__":
    span = sorted({int(s["span_id"].split(":")[0][1:]) for s in
                   json.load(open(DATA / "hebrew_sample_20260906.json", encoding="utf-8")) +
                   json.load(open(DATA / "nikud_sample_10.json", encoding="utf-8"))})
    hard = [546, 657, 129, 226, 393]                   # full-width (546), footer class (657), dense fixtures
    pages = span + [p for p in hard if p not in span]
    build(pages)
