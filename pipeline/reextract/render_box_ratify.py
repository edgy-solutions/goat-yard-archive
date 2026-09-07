"""Span-box ratify console — the validation-set sitting. The agent proposed a native box per span
(column-bounded); this renders a card per span with the band crop + the proposed rectangle drawn on it, and
CONFIRM / ADJUST (drag + resize) / REJECT per card. Verdict-only export as usual: one JSONL line per span
carrying the ratified box, the door, and the freshness attestation — a ratification, not a re-derivation.
Confirming is a two-second visual check (no Hebrew to read); adjusting is a drag. Once ratified this set is
the TRUTH for the Hebrew-span localizer — calibrate word_gap / marker / column bounding against it and report
located-correctly vs abstained vs mislocated on all 30 before any pixel gate consumes a box.

Usage: python render_box_ratify.py  ->  writes span_box_ratify_<date>.html next to the proposals."""
import base64, io, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import numpy as np
from PIL import Image
import cv_footnote_presplit as ps

DATA = Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits")
IMG = Path("C:/Users/cnogr/git/dr-voluminous/commentary/volume1")
DATE = "20260906"

def _gutter(band):
    a = np.asarray(band.convert("L")) < 128; W = a.shape[1]; col = a.sum(axis=0)
    lo, hi = int(W * 0.40), int(W * 0.60)
    return lo + int(np.argmin(col[lo:hi]))

def _band(page):
    strip, info = ps.presplit(str(IMG / f"page{page}_image1.png"), upscale=1)
    if strip is None:
        im = Image.open(IMG / f"page{page}_image1.png").convert("L"); W, H = im.size
        return im.crop((0, int(H * 0.60), W, H))
    return strip.convert("L")

def _b64(im):
    b = io.BytesIO(); im.convert("L").save(b, format="PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()

def build():
    props = json.load(open(DATA / f"span_box_proposals_{DATE}.json", encoding="utf-8"))
    cards = []
    for p in props:
        page = int(p["span_id"].split(":")[0][1:])
        band = _band(page); W, H = band.size
        cards.append(dict(p, page=page, bw=W, bh=H, gutter=_gutter(band), img=_b64(band)))
    data_js = json.dumps(cards, ensure_ascii=False)
    html = _TEMPLATE.replace("/*DATA*/", data_js).replace("{DATE}", DATE).replace("{N}", str(len(cards)))
    out = DATA / f"span_box_ratify_{DATE}.html"
    out.write_text(html, encoding="utf-8")
    print("wrote", out, f"({out.stat().st_size//1024} KB, {len(cards)} cards)")

_TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Span-box ratify — vol1 {DATE}</title><style>
:root{--paper:#f6f4ee;--ink:#1a1a1a;--rule:#cbc5b6;--accent:#b5482e;--ok:#2f7d4f;--adj:#b7791f;--rej:#9a2b2b;--sans:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);line-height:1.4}
header{position:sticky;top:0;background:#2a2723;color:#f2efe6;padding:10px 16px;display:flex;gap:18px;align-items:center;z-index:9;border-bottom:2px solid var(--accent)}
header h1{font-size:15px;margin:0;font-weight:600}header .stat{font-size:13px;opacity:.85}header button{margin-left:auto;background:var(--accent);color:#fff;border:0;padding:7px 14px;border-radius:5px;font-size:13px;cursor:pointer}
.card{max-width:1500px;margin:14px auto;background:#fff;border:1px solid var(--rule);border-radius:7px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.meta{display:flex;gap:14px;align-items:baseline;padding:8px 12px;border-bottom:1px solid var(--rule);flex-wrap:wrap}
.meta .id{font-weight:700;font-size:14px}.meta .heb{font-size:20px;direction:rtl}.meta .note{font-size:12px;color:#6b6459}
.flag{font-size:11px;background:#ede8dc;border:1px solid var(--rule);border-radius:3px;padding:1px 6px;color:#7a4a1a}
.stage{position:relative;overflow:auto;background:#faf9f5;max-height:70vh}
.stage img{display:block;image-rendering:crisp-edges}
.box{position:absolute;border:2px solid var(--accent);background:rgba(181,72,46,.12);cursor:move}
.h{position:absolute;width:12px;height:12px;background:#fff;border:2px solid var(--accent);border-radius:50%}
.h.nw{left:-7px;top:-7px;cursor:nwse-resize}.h.ne{right:-7px;top:-7px;cursor:nesw-resize}.h.sw{left:-7px;bottom:-7px;cursor:nesw-resize}.h.se{right:-7px;bottom:-7px;cursor:nwse-resize}
.gut{position:absolute;top:0;bottom:0;width:0;border-left:2px dashed #3a6ea5;opacity:.6}
.ctl{display:flex;gap:8px;align-items:center;padding:8px 12px;border-top:1px solid var(--rule);flex-wrap:wrap}
.ctl button{border:1px solid var(--rule);background:#f3f1ea;padding:6px 12px;border-radius:5px;font-size:13px;cursor:pointer}
.ctl button.on.c{background:var(--ok);color:#fff;border-color:var(--ok)}.ctl button.on.a{background:var(--adj);color:#fff;border-color:var(--adj)}.ctl button.on.r{background:var(--rej);color:#fff;border-color:var(--rej)}
.ctl .coord{font:12px ui-monospace,monospace;color:#6b6459;margin-left:auto}
.done{outline:3px solid var(--ok)}
</style></head><body>
<header><h1>Span-box ratify · vol1</h1><span class="stat" id="stat"></span>
<button id="export">Export verdicts JSONL</button></header>
<div id="cards"></div>
<script>
const CARDS=/*DATA*/;
const KEY="spanbox_"+"{DATE}";
let state=JSON.parse(localStorage.getItem(KEY)||"{}");
const cardsEl=document.getElementById("cards");
function save(){localStorage.setItem(KEY,JSON.stringify(state));stat();}
function stat(){const done=Object.values(state).filter(v=>v&&v.status).length;
  document.getElementById("stat").textContent=done+" / {N} ratified";}
CARDS.forEach(c=>{
  const disp=Math.min(c.bw,1460), sc=disp/c.bw;      // display scale; box stored in BAND coords
  const st=state[c.span_id]||(state[c.span_id]={box:c.proposed_box.slice(),status:null});
  const card=document.createElement("div");card.className="card";card.id="card_"+c.span_id.replace(":","_");
  card.innerHTML=`<div class="meta"><span class="id">${c.span_id}</span>
    <span class="heb">${c.printed_hebrew}</span><span class="note">note ${c.note_marker} · p${c.page} · ${c.run_note||""}</span>
    ${(c.flags||[]).map(f=>`<span class="flag">${f}</span>`).join("")}</div>
    <div class="stage" style="width:${disp}px"><img src="${c.img}" style="width:${disp}px">
      <div class="gut" style="left:${c.gutter*sc}px"></div>
      <div class="box"><div class="h nw"></div><div class="h ne"></div><div class="h sw"></div><div class="h se"></div></div>
    </div>
    <div class="ctl"><button class="c">Confirm</button><button class="a">Adjusted</button><button class="r">Reject</button>
      <span class="coord"></span></div>`;
  cardsEl.appendChild(card);
  const boxEl=card.querySelector(".box"), coord=card.querySelector(".coord"), stage=card.querySelector(".stage");
  function draw(){const[x0,y0,x1,y1]=st.box;boxEl.style.left=x0*sc+"px";boxEl.style.top=y0*sc+"px";
    boxEl.style.width=(x1-x0)*sc+"px";boxEl.style.height=(y1-y0)*sc+"px";
    coord.textContent=`[${st.box.map(Math.round).join(", ")}]  (band ${c.bw}×${c.bh}, gut ${c.gutter})`;}
  draw();
  // drag move + corner resize, all in DISPLAY px -> convert to band px
  let drag=null;
  function pt(e){const r=stage.getBoundingClientRect();return[(e.clientX-r.left+stage.scrollLeft)/sc,(e.clientY-r.top+stage.scrollTop)/sc];}
  boxEl.addEventListener("mousedown",e=>{if(e.target.classList.contains("h"))return;
    const[px,py]=pt(e);drag={mode:"move",px,py,box:st.box.slice()};e.preventDefault();});
  card.querySelectorAll(".h").forEach(h=>h.addEventListener("mousedown",e=>{
    const[px,py]=pt(e);drag={mode:"resize",corner:[...h.classList].find(k=>k.length==2),px,py,box:st.box.slice()};
    e.stopPropagation();e.preventDefault();}));
  window.addEventListener("mousemove",e=>{if(!drag)return;const[px,py]=pt(e);const dx=px-drag.px,dy=py-drag.py;let b=drag.box.slice();
    if(drag.mode=="move"){b=[b[0]+dx,b[1]+dy,b[2]+dx,b[3]+dy];}
    else{if(drag.corner[0]=="n")b[1]+=dy;else b[3]+=dy;if(drag.corner[1]=="w")b[0]+=dx;else b[2]+=dx;}
    b=[Math.min(b[0],b[2]),Math.min(b[1],b[3]),Math.max(b[0],b[2]),Math.max(b[1],b[3])];
    st.box=b.map(v=>Math.max(0,Math.round(v)));draw();
    if(st.status=="confirm"){st.status="adjust";paint();}});
  window.addEventListener("mouseup",()=>{if(drag){drag=null;save();}});
  const btns={confirm:card.querySelector(".c"),adjust:card.querySelector(".a"),reject:card.querySelector(".r")};
  function paint(){for(const k in btns)btns[k].classList.toggle("on",st.status==k);
    card.classList.toggle("done",!!st.status);}
  btns.confirm.onclick=()=>{st.status="confirm";st.box=c.proposed_box.slice();draw();paint();save();};
  btns.adjust.onclick=()=>{st.status="adjust";paint();save();};
  btns.reject.onclick=()=>{st.status="reject";paint();save();};
  paint();
});
stat();
document.getElementById("export").onclick=()=>{
  const lines=CARDS.map(c=>{const s=state[c.span_id]||{};
    return JSON.stringify({span_id:c.span_id,page:c.page,printed_hebrew:c.printed_hebrew,
      proposed_box:c.proposed_box,ratified_box:s.box||c.proposed_box,
      status:s.status||"unrated",band_size:[c.bw,c.bh],gutter:c.gutter,flags:c.flags,
      provenance:{door:"human-box-ratify",session_freshness:"in-context-WARN",date:"{DATE}"}});}).join("\n");
  const blob=new Blob([lines],{type:"application/x-ndjson"});const a=document.createElement("a");
  a.href=URL.createObjectURL(blob);a.download="span_box_verdicts_{DATE}.jsonl";a.click();};
</script></body></html>"""

if __name__ == "__main__":
    build()
