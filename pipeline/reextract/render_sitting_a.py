"""Sitting A console — the 25 position-invariant jaw pages, each rendered as its footnote strip with the
CV note-start lines overlaid (red), for a COLD visual verdict: are the red lines real note boundaries, or
spurious (two lines inside one note)? Self-contained HTML, images DOWNSCALED + embedded (raw 11.6MB
overloaded the browser = the 3-of-25 render bug; downscale fixes it). Export is the Build-2 contract:
per-verdict JSONL (not an end-blob), each record carrying door + session-freshness + pinned inputs
(crop path + sha of the exact bytes shown), so a verdict is re-auditable, not a diary line."""
import sys, json, base64, io, hashlib, html
from pathlib import Path
from PIL import Image, ImageDraw

HERE = Path(__file__).parent
MANIFEST = HERE / "audits" / "sitting_manifest_position_jaws.json"
EMBED_W = 1100   # downscale overlays to this width before embedding (keeps the console ~2-3MB, all 25 render)

def _overlay_b64(overlay_path):
    """Load the overlay, downscale, return (base64_png, sha16_of_embedded_bytes)."""
    im = Image.open(HERE / overlay_path).convert("RGB")
    if im.size[0] > EMBED_W:
        im = im.resize((EMBED_W, int(im.size[1] * EMBED_W / im.size[0])), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, format="PNG", optimize=True)
    b = buf.getvalue()
    return base64.b64encode(b).decode(), hashlib.sha256(b).hexdigest()[:16]

def build():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cards = []
    n_embedded = 0
    for p in m["pages"]:
        pg = p["page"]
        b64, sha = _overlay_b64(p["overlay"])
        n_embedded += 1
        span_id = f"p{pg}:positions"
        # candidates = what the verdict is ABOUT: the CV-proposed note-start boundaries (count + min gap).
        # Pinned verbatim so the record re-audits — the contract's inputs.candidates, position-jaw form.
        cand = html.escape(json.dumps([{"cv_note_starts": p["n_starts"], "min_gap_lh": p["min_gap_lh"]}]))
        cards.append(f'''<article class="card" data-span-id="{span_id}" data-crop="{html.escape(p['overlay'])}" data-crop-sha="{sha}" data-candidates="{cand}">
  <div class="chead"><span class="pg">p{pg}</span><span class="pill">min-gap {p['min_gap_lh']} lh · {p['n_starts']} starts</span></div>
  <img class="strip" alt="p{pg} footnote strip with CV note-start lines overlaid" src="data:image/png;base64,{b64}">
  <div class="q">Are the red lines real note-start boundaries, or spurious (two lines inside one note)?</div>
  <div class="verdict">
    <label><input type="radio" name="v{pg}" value="valid"> valid boundaries</label>
    <label><input type="radio" name="v{pg}" value="spurious"> spurious (≥2 in one note)</label>
    <input class="reason" type="text" placeholder="rationale — cite what you see">
  </div>
</article>''')
    assert n_embedded == len(m["pages"]), f"embedded {n_embedded} != {len(m['pages'])} pages"
    doc = TEMPLATE.replace("{{CARDS}}", "\n".join(cards)).replace("{{N}}", str(n_embedded)).replace(
        "{{RULE}}", html.escape(m["sampling_rule"])).replace("{{OPENQ}}", html.escape(m["open_question"]))
    out = HERE / "audits" / "sitting_a_console.html"
    out.write_text(doc, encoding="utf-8")
    print(f"wrote {out} — {n_embedded}/{len(m['pages'])} cards embedded ({out.stat().st_size//1024}KB)")

TEMPLATE = r'''<style>
:root{--paper:#f4f2ee;--panel:#fbfaf7;--ink:#201d1a;--muted:#6b6459;--line:#e2ddd3;--accent:#7c2d2d;--ok:#2f6b3f;--warn:#9a6a12;
 --sans:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;--mono:ui-monospace,Consolas,Menlo,monospace;}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#17150f;--panel:#201d16;--ink:#ece7dd;--muted:#9a9082;--line:#332e24;--accent:#d98a6a;--ok:#7fb98a;--warn:#d6a84e;}}
:root[data-theme="dark"]{--paper:#17150f;--panel:#201d16;--ink:#ece7dd;--muted:#9a9082;--line:#332e24;--accent:#d98a6a;--ok:#7fb98a;--warn:#d6a84e;}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);line-height:1.5}
.toolbar{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:.8rem;flex-wrap:wrap;background:var(--panel);border-bottom:1px solid var(--line);padding:.6rem 3vw;font-size:.82rem}
.savest{font-family:var(--mono);color:var(--ok);font-weight:600;min-width:12rem}
.tb{font:inherit;font-size:.82rem;background:var(--paper);color:var(--ink);border:1px solid var(--accent);border-radius:7px;padding:.35rem .8rem;cursor:pointer}
.wrap{padding:clamp(1rem,4vw,3rem);max-width:70rem;margin:0 auto}
.kicker{font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:600}
h1{font-family:var(--mono);font-size:clamp(1.5rem,4vw,2.2rem);margin:.2em 0 .3em}
.lede{max-width:62ch;color:var(--ink)}.lede strong{color:var(--accent)}
.openq{margin:1rem 0;padding:.7rem 1rem;border-left:3px solid var(--warn);background:color-mix(in srgb,var(--warn) 8%,transparent);font-size:.9rem;border-radius:0 6px 6px 0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:1.1rem 1.2rem;margin-bottom:1.4rem}
.chead{display:flex;align-items:center;justify-content:space-between;margin-bottom:.7rem}
.pg{font-family:var(--mono);font-weight:600;font-size:1.05rem}
.pill{font-size:.72rem;font-family:var(--mono);padding:.16rem .5rem;border-radius:999px;border:1px solid var(--line);color:var(--muted)}
.strip{width:100%;border:1px solid var(--line);border-radius:6px;background:#fff;display:block}
.q{margin:.7rem 0 .4rem;font-size:.9rem;color:var(--muted)}
.verdict{display:flex;align-items:center;gap:1rem;flex-wrap:wrap;padding-top:.6rem;border-top:1px dashed var(--line);font-size:.85rem}
.verdict label{display:inline-flex;align-items:center;gap:.3rem;cursor:pointer}
.reason{flex:1;min-width:14rem;background:var(--paper);border:1px solid var(--line);border-radius:6px;padding:.35rem .6rem;color:var(--ink);font:inherit;font-size:.84rem}
</style>
<title>Sitting A — Position Jaws</title>
<div class="toolbar">
 <span id="savest" class="savest">verdicts autosave in this browser</span>
 <button class="tb" type="button" onclick="exportJSONL()">⬇ Export verdicts (JSONL)</button>
 <span class="tbnote" style="color:var(--muted)">Each verdict saved as you go; export is per-verdict JSONL with pinned inputs + door + freshness.</span>
</div>
<div class="wrap">
 <div class="kicker">Fresh-session audit · Sitting A</div>
 <h1>Position-invariant jaws</h1>
 <p class="lede">Each card is a footnote strip with the CV note-start positions drawn as <strong>red lines</strong>.
 The position invariant flagged these {{N}} pages (two starts &lt; one line-height apart). Judge each COLD from the
 pixels: are the red lines real note-start boundaries, or spurious (two falling inside a single note)? Sampling: {{RULE}}.</p>
 <div class="openq">⚖️ <strong>The question these verdicts decide:</strong> {{OPENQ}}</div>
 {{CARDS}}
 <footer style="color:var(--muted);border-top:1px solid var(--line);padding-top:1rem;font-size:.8rem">Verdicts are the calibration record — they set the position invariant, or reveal it wants a page-relative form.</footer>
</div>
<script>
var KEY='sitting_a_position_jaws_v1';
var DOOR='audited-by-agent-in-session', FRESHNESS='cold-context';
function stamp(m){var s=document.getElementById('savest');if(s)s.textContent=m;}
function records(){var recs=[];document.querySelectorAll('.card').forEach(function(c){
  var v=c.querySelector('input[type=radio]:checked'); if(!v) return;
  recs.push({span_id:c.dataset.spanId, chosen:v.value, disputed_span_correction:"",
    rationale:c.querySelector('.reason').value, confidence:null,
    provenance:{door:DOOR, session_freshness:FRESHNESS, date:new Date().toISOString().slice(0,10)},
    inputs:{crop:c.dataset.crop, crop_sha16:c.dataset.cropSha, candidates:JSON.parse(c.dataset.candidates)}});});
  return recs;}
function save(){try{localStorage.setItem(KEY,JSON.stringify(records()));stamp('saved ✓ '+new Date().toLocaleTimeString());}
  catch(e){stamp('⚠ autosave blocked — use Export');}}
function restore(){var d;try{d=JSON.parse(localStorage.getItem(KEY)||'[]');}catch(e){return;}
  d.forEach(function(r){var c=document.querySelector('.card[data-span-id="'+r.span_id+'"]');if(!c)return;
    var v=c.querySelector('input[value="'+r.chosen+'"]');if(v)v.checked=true;
    if(r.rationale)c.querySelector('.reason').value=r.rationale;});}
document.addEventListener('input',function(e){if(e.target.closest('.card'))save();});
document.addEventListener('change',function(e){if(e.target.closest('.card'))save();});
function exportJSONL(){
  var manifest={kind:"sitting_manifest",sitting:"position-invariant-jaws",door:DOOR,
    session_freshness:FRESHNESS,date:new Date().toISOString().slice(0,10),
    n_spans:document.querySelectorAll('.card').length};
  var lines=[JSON.stringify(manifest)].concat(records().map(function(r){return JSON.stringify(r);}));
  var blob=new Blob([lines.join("\n")+"\n"],{type:'application/x-ndjson'});
  var a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='sitting_a_verdicts.jsonl';
  document.body.appendChild(a);a.click();a.remove();stamp('exported ✓ (JSONL, '+records().length+' verdicts)');}
restore();save();
</script>'''

if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    build()
