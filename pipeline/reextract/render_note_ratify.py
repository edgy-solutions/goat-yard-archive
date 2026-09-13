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
        # err toward COMPLETE, not clipped: a small top pad so a tall Hebrew letter / raised marker at the
        # line top isn't clipped by default (under-inclusion is fatal for the glyph/nikud gates). You still
        # ratify to tight; over-inclusion into the footer stays your call to trim.
        boxes = [[b[0], max(0, b[1] - 5), b[2], b[3]] for b in (r["strip_box"] for r in regs)]
        cards.append(dict(page=pg, sw=strip.width, sh=strip.height, mode=info.get("mode"),
                          n_extractor=nn.get(pg), n_detected=len(regs),
                          proposed=boxes,
                          column_bands=meta["column_bands"], img=_b64(strip)))
    html = _TEMPLATE.replace("/*DATA*/", json.dumps(cards)).replace("{DATE}", DATE).replace("{N}", str(len(cards)))
    out = DATA / f"note_box_ratify_{DATE}.html"
    out.write_text(html, encoding="utf-8")
    tot = sum(c["n_detected"] for c in cards); ext = sum(c["n_extractor"] or 0 for c in cards)
    print(f"wrote {out} ({out.stat().st_size//1024} KB, {len(cards)} pages, {tot} proposed boxes vs {ext} extractor notes)")

_TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Note-box ratify — vol1 {DATE}</title><style>
:root{--paper:#f6f4ee;--ink:#1a1a1a;--rule:#cbc5b6;--accent:#2f6b8f;--ok:#2f7d4f;--rej:#9a2b2b;--add:#7a4bb0;--mrg:#b7791f;--split:#1f8a70;--sans:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);line-height:1.4}
header{position:sticky;top:0;background:#26302f;color:#f2efe6;padding:10px 16px;display:flex;gap:16px;align-items:center;z-index:20;border-bottom:2px solid var(--accent)}
header h1{font-size:15px;margin:0}header .stat{font-size:13px;opacity:.85}header button{background:var(--accent);color:#fff;border:0;padding:7px 14px;border-radius:5px;font-size:13px;cursor:pointer}
header .sp{margin-left:auto}
.card{max-width:1500px;margin:14px auto;background:#fff;border:1px solid var(--rule);border-radius:7px;overflow:hidden}
.meta{display:flex;gap:14px;align-items:baseline;padding:8px 12px;border-bottom:1px solid var(--rule);flex-wrap:wrap;font-size:13px}
.meta .id{font-weight:700;font-size:14px}.meta .warn{color:var(--rej);font-weight:600}.meta .ok{color:var(--ok);font-weight:600}
.hint{font-size:12px;color:#6b6459}
.stage{position:relative;overflow-y:scroll;overflow-x:auto;background:#faf9f5;max-height:80vh;cursor:crosshair;scrollbar-gutter:stable}
.stage img{display:block}
.nb{position:absolute;border:2px solid var(--accent);background:rgba(47,107,143,.08);cursor:move}
.nb.rej{border-color:var(--rej);background:rgba(154,43,43,.10);border-style:dashed}
.nb.add{border-color:var(--add);background:rgba(122,75,176,.10)}
.nb.adjust{border-color:var(--ok)}
.nb.arm{border-color:var(--split);border-style:dashed;box-shadow:inset 0 0 0 2px var(--split);cursor:row-resize}
.nb .tools .spl{color:var(--split)}
/* top/bottom edge resize bars — full width, grab anywhere clear of the scrollbar */
.nb .edge{position:absolute;left:8px;right:22px;height:9px;cursor:ns-resize;background:rgba(47,107,143,.25)}
.nb .edge:hover{background:var(--accent)}
.nb .edge.top{top:-5px}.nb .edge.bot{bottom:-5px}
/* controls at the LEFT, never under the right scrollbar */
/* chrome is HIDDEN by default so the footnote marker (start) + box bottom (stop) are fully visible;
   it reveals on hover (or while the box is armed for split) */
.nb .tools{position:absolute;left:2px;top:2px;display:flex;gap:3px;z-index:5;opacity:0;transition:opacity .08s}
.nb .tools button{width:22px;height:19px;border:1px solid var(--rule);background:#fff;border-radius:3px;font-size:12px;line-height:1;cursor:pointer;padding:0}
.nb .tools .rej{color:var(--rej)}.nb .tools .mrg{color:var(--mrg)}
.nb .tag{position:absolute;right:2px;top:2px;font:10px ui-monospace,monospace;color:#8a8375;background:rgba(255,255,255,.75);padding:0 3px;z-index:5;opacity:0;transition:opacity .08s}
.nb:hover .tools,.nb:hover .tag,.nb.arm .tools,.nb.arm .tag{opacity:1}
.nb.arm .tag{color:var(--split);background:#fff}
</style></head><body>
<header><h1>Note-box ratify · vol1</h1><span class="stat" id="stat"></span>
<span class="sp"></span><button id="reset" style="background:#7a3b3b">Reset all</button><button id="export">Export note-box truth JSONL</button></header>
<div id="cards"></div>
<script>
const CARDS=/*DATA*/, KEY="notebox_"+"{DATE}";
let state=JSON.parse(localStorage.getItem(KEY)||"{}");
function save(){localStorage.setItem(KEY,JSON.stringify(state));stat();}
function stat(){let done=Object.keys(state).length;document.getElementById("stat").textContent=done+" / {N} pages touched";}
CARDS.forEach(c=>{
  const disp=Math.min(c.sw,1360), sc=disp/c.sw;
  if(!state[c.page]) state[c.page]={boxes:c.proposed.map(b=>({box:b,st:"confirm",src:"detector"}))};
  const S=state[c.page];
  const card=document.createElement("div");card.className="card";card.id="c"+c.page;
  const warn=c.n_detected!==c.n_extractor;
  card.innerHTML=`<div class="meta"><span class="id">p${c.page}</span>
    <span>extractor notes: <b>${c.n_extractor}</b></span>
    <span class="${warn?'warn':'ok'}" data-live>detected: ${c.n_detected}${warn?' — check for missed/extra':' ✓'}</span>
    <span class="hint">${c.mode} · strip ${c.sw}×${c.sh}</span>
    <span class="hint">move=drag body · resize=drag blue top/bottom bars · ✕=reject · ⤒=merge into note above · ✂=split (box has 2 notes) · drag empty area=ADD</span></div>
    <div class="stage" style="width:${disp+18}px"><div class="canvas" style="position:relative;width:${disp}px"><img src="${c.img}" style="width:${disp}px"></div></div>`;
  document.getElementById("cards").appendChild(card);
  const stage=card.querySelector(".stage"), canvas=card.querySelector(".canvas"), live=card.querySelector("[data-live]");
  function pt(e){const r=canvas.getBoundingClientRect();return[(e.clientX-r.left)/sc,(e.clientY-r.top)/sc];}
  function kept(){return S.boxes.filter(b=>b.st!=="reject"&&b.st!=="merged");}
  function live_count(){const n=kept().length;live.textContent="ratified: "+n+(n===c.n_extractor?" ✓ (matches extractor)":" (extractor "+c.n_extractor+")");
    live.className=(n===c.n_extractor?"ok":"warn");}
  function render(){
    [...canvas.querySelectorAll(".nb")].forEach(n=>n.remove());
    const order=[...S.boxes.keys()].filter(i=>S.boxes[i].st!=="merged").sort((a,b)=>S.boxes[a].box[1]-S.boxes[b].box[1]);
    order.forEach((i,pos)=>{const bx=S.boxes[i];const[x0,y0,x1,y1]=bx.box;
      const d=document.createElement("div");
      d.className="nb"+(bx.st==="reject"?" rej":"")+(bx.st==="adjust"?" adjust":"")+(bx.src==="human"?" add":"")+(splitArm===i?" arm":"");
      d.style.left=x0*sc+"px";d.style.top=y0*sc+"px";d.style.width=(x1-x0)*sc+"px";d.style.height=(y1-y0)*sc+"px";
      d.innerHTML=`<div class="tools"><button class="rej" title="reject">${bx.st==="reject"?"↺":"✕"}</button>`+
        (pos>0?`<button class="mrg" title="merge into note above">⤒</button>`:``)+
        `<button class="spl" title="split: has 2 notes — click, then click where the 2nd note starts">✂</button></div>`+
        `<span class="tag">${pos+1}${bx.src==="human"?"+":""}${bx.absorbed?" ⤒"+bx.absorbed:""}${splitArm===i?" ✂ click 2nd note's top":""}</span>`+
        `<div class="edge top"></div><div class="edge bot"></div>`;
      d.querySelector(".rej").onclick=ev=>{ev.stopPropagation();bx.st=bx.st==="reject"?"confirm":"reject";save();render();};
      const mrg=d.querySelector(".mrg");
      if(mrg)mrg.onclick=ev=>{ev.stopPropagation();
        const prev=S.boxes[order[pos-1]];                         // union into the previous note; record merge
        prev.box=[Math.min(prev.box[0],bx.box[0]),Math.min(prev.box[1],bx.box[1]),Math.max(prev.box[2],bx.box[2]),Math.max(prev.box[3],bx.box[3])];
        prev.absorbed=(prev.absorbed||0)+1;if(prev.st==="confirm")prev.st="adjust";
        bx.st="merged";splitArm=null;save();render();};
      d.querySelector(".spl").onclick=ev=>{ev.stopPropagation();splitArm=(splitArm===i?null:i);render();};
      d.addEventListener("mousedown",ev=>{if(ev.target.closest(".tools"))return;
        const[px,py]=pt(ev);
        if(splitArm===i){                                         // SPLIT: box has 2 notes -> click the 2nd's top
          const b=bx.box, cy=Math.round(py);
          if(cy>b[1]+6&&cy<b[3]-6){bx.box=[b[0],b[1],b[2],cy];if(bx.st==="confirm")bx.st="adjust";
            S.boxes.push({box:[b[0],cy,b[2],b[3]],st:"adjust",src:"human",split:true});}  // detector missed this start
          splitArm=null;save();render();ev.stopPropagation();ev.preventDefault();return;}
        const top=ev.target.classList.contains("top"),bot=ev.target.classList.contains("bot");
        drag={i,mode:top?"top":bot?"bot":"move",px,py,box:bx.box.slice()};ev.stopPropagation();ev.preventDefault();});
      canvas.appendChild(d);});
    live_count();
  }
  let drag=null,adding=null,ghost=null,splitArm=null;
  canvas.addEventListener("mousedown",e=>{if(e.target!==canvas&&e.target.tagName!=="IMG")return;
    const[px,py]=pt(e);adding={x0:px,y0:py,x1:px,y1:py};});
  window.addEventListener("mousemove",e=>{
    if(drag){const[px,py]=pt(e);const dx=px-drag.px,dy=py-drag.py;let b=drag.box.slice();
      if(drag.mode==="move"){b=[b[0]+dx,b[1]+dy,b[2]+dx,b[3]+dy];}
      else if(drag.mode==="top"){b[1]=Math.min(b[3]-6,b[1]+dy);}
      else{b[3]=Math.max(b[1]+6,b[3]+dy);}
      S.boxes[drag.i].box=b.map(Math.round);if(S.boxes[drag.i].st==="confirm")S.boxes[drag.i].st="adjust";render();}
    else if(adding){const[px,py]=pt(e);adding.x1=px;adding.y1=py;
      if(!ghost){ghost=document.createElement("div");ghost.className="nb add";canvas.appendChild(ghost);}
      const x0=Math.min(adding.x0,px),y0=Math.min(adding.y0,py);
      ghost.style.left=x0*sc+"px";ghost.style.top=y0*sc+"px";ghost.style.width=Math.abs(px-adding.x0)*sc+"px";ghost.style.height=Math.abs(py-adding.y0)*sc+"px";}});
  window.addEventListener("mouseup",()=>{
    if(drag){drag=null;save();}
    else if(adding){if(ghost){ghost.remove();ghost=null;}
      const dx=Math.abs(adding.x1-adding.x0),dy=Math.abs(adding.y1-adding.y0);
      if(dy>8){S.boxes.push({box:[Math.round(Math.min(adding.x0,adding.x1)),Math.round(Math.min(adding.y0,adding.y1)),
        Math.round(Math.max(adding.x0,adding.x1)),Math.round(Math.max(adding.y0,adding.y1))],st:"adjust",src:"human"});save();}
      adding=null;render();}});
  render();
});
stat();
document.getElementById("reset").onclick=()=>{if(confirm("Clear all ratifications and re-propose from the detector?")){localStorage.removeItem(KEY);location.reload();}};
document.getElementById("export").onclick=()=>{
  const lines=[];
  lines.push(JSON.stringify({kind:"note_box_truth_header",tolerance:"STRICT — boxes complete+tight for extraction crops; navigation fallback (note->column->page) lives downstream, NOT here",
    coordinate_convention:"cv_footnote_presplit stacked reading-order strip, pixels; un-stack to native via note_region.strip_to_native",date:"{DATE}",door:"human-note-box-ratify"}));
  CARDS.forEach(c=>{const S=state[c.page]||{boxes:[]};
    const kept=S.boxes.filter(b=>b.st!=="reject"&&b.st!=="merged");
    const merges=S.boxes.filter(b=>b.st==="merged").length;                 // precision signal: false extra starts
    const splits=S.boxes.filter(b=>b.split).length;                          // recall signal: detector-missed starts
    lines.push(JSON.stringify({page:c.page,strip_size:[c.sw,c.sh],column_bands:c.column_bands,mode:c.mode,
      n_extractor:c.n_extractor,n_detected:c.n_detected,n_ratified:kept.length,continuation_merges:merges,missed_starts_split:splits,
      notes:kept.map(b=>({strip_box:b.box,status:b.st,proposed_by:b.src==="human"?"human":"detector",split_from_detector_box:!!b.split,absorbed_continuations:b.absorbed||0})),
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
