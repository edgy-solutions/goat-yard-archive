"""Hebrew-residual sitting — 20 Hebrew spans drawn at random from the 911 un-overlaid pages, to replace
"Hebrew residual unbounded" in caveat 1 with a MEASURED rate. Two judges: agent-blind first (verdict-only,
appended as each is made), then Chris. Each card shows the run's Hebrew reading + the native 3584px band
(click to zoom to full pixels — no sub-16px strip); the judge calls whether the run's Hebrew matches the
page, and supplies the correct span if not. Self-contained HTML; per-verdict JSONL export in the
audit_record shape. The agent's calls are NOT embedded here — this console is for Chris's independent pass."""
import sys, io, json, base64, hashlib, html
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import cv_footnote_presplit as ps
from data_config import data_path
from PIL import Image
import numpy as np

IMG = Path("C:/Users/cnogr/git/dr-voluminous/commentary/volume1")
EMBED_W = 1600

def band_b64(pg):
    strip, info = ps.presplit(str(IMG / f"page{pg}_image1.png"), upscale=1)
    if strip is None:
        im = Image.open(IMG / f"page{pg}_image1.png"); W, H = im.size
        strip = im.crop((0, int(H*0.60), W, H)).convert("L")
    disp = strip
    if strip.size[0] > EMBED_W:
        disp = strip.resize((EMBED_W, int(strip.size[1]*EMBED_W/strip.size[0])), Image.LANCZOS)
    buf = io.BytesIO(); disp.convert("L").save(buf, format="PNG", optimize=True)
    b = buf.getvalue()
    return "data:image/png;base64," + base64.b64encode(b).decode(), hashlib.sha256(b).hexdigest()[:16], strip.size

def esc(s): return html.escape(str(s) if s is not None else "")

def build():
    spans = json.load(io.open(data_path("audits", "hebrew_sample_20260906.json"), encoding="utf-8"))
    cards = []
    for s in spans:
        b64, sha, sz = band_b64(s["page"])
        cand = html.escape(json.dumps([s["run_text"]]))
        cards.append(f'''<article class="card" data-span-id="{esc(s['span_id'])}" data-crop="page{s['page']}_native_band"
     data-crop-sha="{sha}" data-candidates="{cand}">
  <div class="chead"><span class="pg">{esc(s['span_id'])}</span><span class="pill">native {sz[0]}×{sz[1]}px</span></div>
  <div class="q">Does the run's Hebrew match what the page prints?</div>
  <div class="rd">{esc(s['run_text'])}</div>
  <img class="strip" src="{b64}" alt="native band p{s['page']}">
  <div class="verdict">
    <label><input type="radio" name="{esc(s['span_id'])}" value="correct"> Hebrew correct</label>
    <label><input type="radio" name="{esc(s['span_id'])}" value="wrong"> Hebrew wrong</label>
    <label><input type="radio" name="{esc(s['span_id'])}" value="uncertain"> uncertain</label>
    <input class="reason" dir="rtl" spellcheck="false" type="text" placeholder="if wrong: the correct Hebrew span (Hebrew only)">
  </div>
</article>''')
    doc = TEMPLATE.replace("{{CARDS}}", "\n".join(cards)).replace("{{N}}", str(len(spans)))
    out = data_path("audits", "hebrew_sitting_20260906.html")
    Path(out).write_text(doc, encoding="utf-8")
    print(f"wrote {out} — {len(cards)} cards ({Path(out).stat().st_size//1024}KB)")

TEMPLATE = r'''<style>
:root{--paper:#f4f2ee;--panel:#fbfaf7;--ink:#201d1a;--muted:#6b6459;--line:#e2ddd3;--accent:#7c2d2d;--ok:#2f6b3f;
 --serif:"Gentium Plus","Times New Roman",serif;--sans:ui-sans-serif,system-ui,"Segoe UI",Roboto,sans-serif;--mono:ui-monospace,Consolas,monospace;}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#17150f;--panel:#201d16;--ink:#ece7dd;--muted:#9a9082;--line:#332e24;--accent:#d98a6a;--ok:#7fb98a;}}
:root[data-theme="dark"]{--paper:#17150f;--panel:#201d16;--ink:#ece7dd;--muted:#9a9082;--line:#332e24;--accent:#d98a6a;--ok:#7fb98a;}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);line-height:1.5}
.toolbar{position:sticky;top:0;z-index:10;display:flex;gap:.8rem;align-items:center;flex-wrap:wrap;background:var(--panel);border-bottom:1px solid var(--line);padding:.6rem 3vw;font-size:.82rem}
.savest{font-family:var(--mono);color:var(--ok);font-weight:600;min-width:12rem}
.tb{font:inherit;font-size:.82rem;background:var(--paper);color:var(--ink);border:1px solid var(--accent);border-radius:7px;padding:.35rem .8rem;cursor:pointer}
.wrap{padding:clamp(1rem,4vw,3rem);max-width:74rem;margin:0 auto}
.kicker{font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:600}
h1{font-family:var(--mono);font-size:clamp(1.4rem,4vw,2.1rem);margin:.2em 0 .3em}
.lede{max-width:64ch}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:1rem 1.1rem;margin-bottom:1.3rem}
.chead{display:flex;justify-content:space-between;align-items:center;margin-bottom:.5rem}
.pg{font-family:var(--mono);font-weight:600}.pill{font-size:.7rem;font-family:var(--mono);color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:.14rem .5rem}
.q{font-size:.85rem;color:var(--muted);margin-bottom:.3rem}
.rd{font-family:var(--serif);font-size:1.15rem;border-left:3px solid var(--accent);padding-left:.6rem;margin-bottom:.6rem;overflow-wrap:anywhere}
.strip{width:100%;border:1px solid var(--line);border-radius:6px;background:#fff;display:block;cursor:zoom-in}
.strip.zoom{position:fixed;inset:2vh 2vw;width:96vw;height:96vh;object-fit:contain;z-index:50;background:#fff;cursor:zoom-out}
.verdict{display:flex;gap:1rem;flex-wrap:wrap;align-items:center;padding-top:.6rem;margin-top:.7rem;border-top:1px dashed var(--line);font-size:.85rem}
.verdict label{display:inline-flex;gap:.3rem;align-items:center;cursor:pointer}
.reason{flex:1;min-width:14rem;background:var(--paper);border:1px solid var(--line);border-radius:6px;padding:.35rem .6rem;color:var(--ink);font:inherit;font-family:var(--serif);font-size:1.05rem}
</style>
<title>Hebrew Residual — 20-span sitting</title>
<div class="toolbar"><span id="savest" class="savest">verdicts autosave</span>
 <button class="tb" onclick="exportJSONL()">⬇ Export verdicts (JSONL)</button>
 <span style="color:var(--muted)">click any band to zoom to full native pixels</span></div>
<div class="wrap"><div class="kicker">caveat 1 · measured, not unbounded</div>
 <h1>Hebrew residual — {{N}} random un-overlaid spans</h1>
 <p class="lede">Twenty Hebrew spans drawn at random from the 911 pages with no adjudication overlay. For each,
 does the run's Hebrew reading match what the page prints at native resolution? Your call sets the measured
 silent-error rate that replaces "unbounded" in caveat 1. Verdict-only — if wrong, give the correct span.</p>
 {{CARDS}}</div>
<script>
var KEY='hebrew_sitting_20260906', DOOR='adjudicated-by-human-review', FRESH='cold-context';
document.addEventListener('click',function(e){if(e.target.classList&&e.target.classList.contains('strip'))e.target.classList.toggle('zoom');});
function stamp(m){var s=document.getElementById('savest');if(s)s.textContent=m;}
function records(){var o=[];document.querySelectorAll('.card').forEach(function(c){
  var v=c.querySelector('input[type=radio]:checked'); if(!v)return;
  o.push({span_id:c.dataset.spanId, chosen:v.value,
    disputed_span_correction:v.value==='wrong'?c.querySelector('.reason').value:"", rationale:"", confidence:null,
    provenance:{door:DOOR,session_freshness:FRESH,editor:'human:Chris',date:new Date().toISOString().slice(0,10)},
    inputs:{crop:c.dataset.crop,crop_sha16:c.dataset.cropSha,candidates:JSON.parse(c.dataset.candidates)}});});
  return o;}
function save(){try{localStorage.setItem(KEY,JSON.stringify(records()));stamp('saved ✓ '+new Date().toLocaleTimeString());}catch(e){stamp('⚠ autosave blocked — Export');}}
function restore(){var d;try{d=JSON.parse(localStorage.getItem(KEY)||'[]');}catch(e){return;}
  d.forEach(function(r){var c=document.querySelector('.card[data-span-id="'+r.span_id+'"]');if(!c)return;
    var v=c.querySelector('input[value="'+r.chosen+'"]');if(v)v.checked=true;
    if(r.disputed_span_correction)c.querySelector('.reason').value=r.disputed_span_correction;});}
document.addEventListener('input',function(e){if(e.target.closest('.card'))save();});
function exportJSONL(){var recs=records();
  var man={kind:"sitting_manifest",sitting:"hebrew-residual-20",date:new Date().toISOString().slice(0,10),door:DOOR,n_spans:recs.length};
  var lines=[JSON.stringify(man)].concat(recs.map(function(r){return JSON.stringify(r);}));
  var b=new Blob([lines.join("\n")+"\n"],{type:'application/x-ndjson'});
  var a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='hebrew_sitting_chris_20260906.jsonl';
  document.body.appendChild(a);a.click();a.remove();stamp('exported ✓ ('+recs.length+')');}
restore();save();
</script>'''

if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    build()
