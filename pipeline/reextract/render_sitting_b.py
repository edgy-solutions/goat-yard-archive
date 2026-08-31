"""Sitting B console — span adjudication from the two-witness manifest. Two disjoint sections:

  DISAGREEMENT (three-column, for the human-review rung): stored | extracted | why. Every row is a
    proposed change the re-extraction would make to the corpus; the verdict picks the surviving reading.
    This is rung 5 of the dispute ladder (human review), reached because the witnesses diverge.

  AGREED SAMPLE (spot-check, for the agent): spans where both witnesses read the same. The agent
    confirms the agreement is real, or flags CORRELATED ERROR — unanimity is confidence only over shared
    evidence, and two readers can be blind the same way. This is the invisible-loss check the ladder
    can't make for itself.

Strips embedded once per page (deduped, downscaled) and grounded under each row. Export is the Build-2
contract: per-verdict JSONL, each record with door + session-freshness + pinned inputs (inputs_sha16 =
sha of the exact stored␟extracted bytes shown), so a verdict re-audits, not just records."""
import sys, io, json, base64, hashlib, html
from pathlib import Path
from PIL import Image

HERE = Path(__file__).parent
MANIFEST = HERE / "audits" / "sitting_manifest_span_adjudication.json"
STRIPS = HERE / "truthset_review"
EMBED_W = 1100

def _load(p): return json.load(io.open(p, encoding="utf-8"))

def _strip_path(page): return STRIPS / f"strip_{page}.png"

def _strip_b64(page):
    p = _strip_path(page)
    if not p.exists(): return None
    im = Image.open(p).convert("L")
    if im.size[0] > EMBED_W:
        im = im.resize((EMBED_W, int(im.size[1] * EMBED_W / im.size[0])), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode()

def _pinned(rec, candidates):
    """Contract inputs for one span: crop points at the visual ground truth (the strip) when it exists,
    else at the text source; crop_sha16 pins whichever; candidates pins the readings verbatim."""
    p = _strip_path(rec["page"])
    if p.exists():
        crop, sha = f"truthset_review/strip_{rec['page']}.png", hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    else:
        crop = f"truthset_results.json#{rec['span_id']}"
        sha = rec.get("inputs_sha16") or hashlib.sha256("␟".join(candidates).encode("utf-8")).hexdigest()[:16]
    return crop, sha, candidates

def esc(s): return html.escape(str(s) if s is not None else "")

KIND_PILL = {"script": ("dropped-lemma", "var(--accent)"), "text": ("text divergence", "var(--warn)"),
             "minor": ("minor / normalization", "var(--muted)")}

def dis_card(d):
    kind, color = KIND_PILL.get(d.get("kind"), (d.get("kind", "?"), "var(--muted)"))
    strip = f'<img class="strip" data-page="{d["page"]}" alt="p{d["page"]} strip">' if d.get("strip") else ""
    crop, sha, cand = _pinned(d, [d["stored"], d["extracted"]])
    return f'''<article class="card dis" data-span-id="{esc(d['span_id'])}" data-page="{d['page']}"
     data-crop="{esc(crop)}" data-crop-sha="{esc(sha)}" data-candidates="{esc(json.dumps(cand))}"
     data-kind="{esc(d.get('kind'))}">
  <div class="chead"><span class="pg">{esc(d['span_id'])}</span>
    <span class="pill" style="border-color:{color};color:{color}">{esc(kind)}</span></div>
  <div class="why">{esc(d.get('reason'))}</div>
  <div class="cols">
    <div class="col stored"><span class="clabel">stored (corpus now)</span><div class="ctext">{esc(d['stored'])}</div></div>
    <div class="col extr"><span class="clabel">extracted (re-extraction)</span><div class="ctext">{esc(d['extracted'])}</div></div>
  </div>
  {strip}
  <div class="verdict">
    <label><input type="radio" name="{esc(d['span_id'])}" value="take-extracted"> take extracted</label>
    <label><input type="radio" name="{esc(d['span_id'])}" value="keep-stored"> keep stored</label>
    <label><input type="radio" name="{esc(d['span_id'])}" value="neither"> neither / correct by hand</label>
    <input class="reason" type="text" dir="auto" spellcheck="false" placeholder="correction (if neither) or rationale">
    <div class="err"></div>
  </div>
</article>'''

def agr_card(a):
    strip = f'<img class="strip" data-page="{a["page"]}" alt="p{a["page"]} strip">' if a.get("strip") else ""
    crop, sha, cand = _pinned(a, [a["stored"]])
    return f'''<article class="card agr" data-span-id="{esc(a['span_id'])}" data-page="{a['page']}"
     data-crop="{esc(crop)}" data-crop-sha="{esc(sha)}" data-candidates="{esc(json.dumps(cand))}">
  <div class="chead"><span class="pg">{esc(a['span_id'])}</span>
    <span class="pill" style="border-color:var(--ok);color:var(--ok)">both witnesses agree</span></div>
  <div class="ctext single">{esc(a['stored'])}</div>
  {strip}
  <div class="verdict">
    <label><input type="radio" name="{esc(a['span_id'])}" value="confirm"> agreement is real</label>
    <label><input type="radio" name="{esc(a['span_id'])}" value="correlated-error"> correlated error (both wrong the same way)</label>
    <input class="reason" type="text" dir="auto" spellcheck="false" placeholder="if correlated error — what's actually there">
    <div class="err"></div>
  </div>
</article>'''

def build():
    m = _load(MANIFEST)
    dis, agr = m["disagreement"], m["agreed_sample"]
    pages = sorted({d["page"] for d in dis if d.get("strip")} | {a["page"] for a in agr if a.get("strip")})
    stripmap = {}
    for pg in pages:
        b = _strip_b64(pg)
        if b: stripmap[pg] = f"data:image/png;base64,{b}"
    limit = m.get("limit")
    doc = TEMPLATE.replace("{{DIS_CARDS}}", "\n".join(dis_card(d) for d in dis)) \
                  .replace("{{AGR_CARDS}}", "\n".join(agr_card(a) for a in agr)) \
                  .replace("{{NDIS}}", str(len(dis))).replace("{{NAGR}}", str(len(agr))) \
                  .replace("{{NCR}}", str(m["counts"].get("count_reconcile_pages", 0))) \
                  .replace("{{LIMIT}}", esc(limit) if limit else "") \
                  .replace("{{LIMITSHOW}}", "" if limit else "display:none") \
                  .replace("{{STRIPMAP}}", json.dumps(stripmap))
    out = HERE / "audits" / "sitting_b_console.html"
    out.write_text(doc, encoding="utf-8")
    print(f"wrote {out} — {len(dis)} disagreement + {len(agr)} agreed cards, "
          f"{len(stripmap)} strips embedded ({out.stat().st_size//1024}KB)")

TEMPLATE = r'''<style>
:root{--paper:#f4f2ee;--panel:#fbfaf7;--ink:#201d1a;--muted:#6b6459;--line:#e2ddd3;--accent:#7c2d2d;--ok:#2f6b3f;--warn:#9a6a12;--crit:#a33232;
 --stored:#8a5a12;--extr:#2f5b6b;--sans:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;--mono:ui-monospace,Consolas,Menlo,monospace;}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#17150f;--panel:#201d16;--ink:#ece7dd;--muted:#9a9082;--line:#332e24;--accent:#d98a6a;--ok:#7fb98a;--warn:#d6a84e;--crit:#e08a7f;--stored:#d6a84e;--extr:#7fb4c7;}}
:root[data-theme="dark"]{--paper:#17150f;--panel:#201d16;--ink:#ece7dd;--muted:#9a9082;--line:#332e24;--accent:#d98a6a;--ok:#7fb98a;--warn:#d6a84e;--crit:#e08a7f;--stored:#d6a84e;--extr:#7fb4c7;}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);line-height:1.5}
.toolbar{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:.8rem;flex-wrap:wrap;background:var(--panel);border-bottom:1px solid var(--line);padding:.6rem 3vw;font-size:.82rem}
.savest{font-family:var(--mono);color:var(--ok);font-weight:600;min-width:12rem}
.tb{font:inherit;font-size:.82rem;background:var(--paper);color:var(--ink);border:1px solid var(--accent);border-radius:7px;padding:.35rem .8rem;cursor:pointer}
.wrap{padding:clamp(1rem,4vw,3rem);max-width:74rem;margin:0 auto}
.kicker{font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:600}
h1{font-family:var(--mono);font-size:clamp(1.4rem,4vw,2.1rem);margin:.2em 0 .3em}
h2{font-family:var(--mono);font-size:1.15rem;margin:2.4rem 0 .3rem;padding-top:1.2rem;border-top:2px solid var(--line)}
.lede{max-width:64ch;color:var(--ink)}.lede strong{color:var(--accent)}
.sectnote{color:var(--muted);font-size:.88rem;max-width:64ch;margin:.2rem 0 1.2rem}
.limit{margin:1rem 0;padding:.6rem 1rem;border-left:3px solid var(--warn);background:color-mix(in srgb,var(--warn) 8%,transparent);font-size:.84rem;border-radius:0 6px 6px 0;font-family:var(--mono)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:1rem 1.1rem;margin-bottom:1.1rem}
.chead{display:flex;align-items:center;justify-content:space-between;margin-bottom:.5rem}
.pg{font-family:var(--mono);font-weight:600;font-size:1rem}
.pill{font-size:.7rem;font-family:var(--mono);padding:.14rem .5rem;border-radius:999px;border:1px solid var(--line)}
.why{font-size:.78rem;color:var(--muted);font-family:var(--mono);margin-bottom:.6rem}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:.8rem}
@media(max-width:640px){.cols{grid-template-columns:1fr}}
.col{border:1px solid var(--line);border-radius:8px;padding:.5rem .7rem;background:var(--paper)}
.col.stored{border-left:3px solid var(--stored)}.col.extr{border-left:3px solid var(--extr)}
.clabel{font-size:.66rem;text-transform:uppercase;letter-spacing:.08em;font-weight:600;display:block;margin-bottom:.3rem}
.col.stored .clabel{color:var(--stored)}.col.extr .clabel{color:var(--extr)}
.ctext{font-family:"Gentium Plus","Times New Roman",serif;font-size:1.02rem;line-height:1.55;word-break:break-word}
.ctext.single{border:1px solid var(--line);border-left:3px solid var(--ok);border-radius:8px;padding:.5rem .7rem;background:var(--paper)}
.strip{width:100%;margin-top:.7rem;border:1px solid var(--line);border-radius:6px;background:#fff;display:block}
.verdict{display:flex;align-items:center;gap:.9rem;flex-wrap:wrap;padding-top:.6rem;margin-top:.7rem;border-top:1px dashed var(--line);font-size:.82rem}
.verdict label{display:inline-flex;align-items:center;gap:.3rem;cursor:pointer}
.reason{flex:1;min-width:13rem;background:var(--paper);border:1px solid var(--line);border-radius:6px;padding:.32rem .6rem;color:var(--ink);font:inherit;font-size:.84rem}
.err{flex-basis:100%;color:var(--crit);font-size:.76rem;font-weight:600;margin-top:.2rem;display:none}
.err.on{display:block}
.card.bad{border-color:var(--crit)}
</style>
<title>Sitting B — Span Adjudication</title>
<div class="toolbar">
 <span id="savest" class="savest">verdicts autosave in this browser</span>
 <button class="tb" type="button" onclick="exportJSONL()">⬇ Export verdicts (JSONL)</button>
 <span style="color:var(--muted)">per-verdict JSONL · door + freshness + pinned inputs</span>
</div>
<div class="wrap">
 <div class="kicker">Fresh-session audit · Sitting B</div>
 <h1>Span adjudication — two witnesses</h1>
 <p class="lede">Witness A is <strong>stored</strong> (the corpus now); witness B is <strong>extracted</strong>
 (the re-extraction). Where they diverge, the re-extraction is proposing a change — adjudicate which reading
 survives before it can replace the stored one. Where they agree, spot-check that the agreement is real and
 not two readers blind the same way.</p>
 <div class="limit" style="{{LIMITSHOW}}">⚖️ named limit — {{LIMIT}}</div>

 <h2>1 · Disagreement — {{NDIS}} proposed changes (human-review rung)</h2>
 <p class="sectnote">Three columns per span. Pick the surviving reading; "neither" if both are wrong and type
 the correction. {{NCR}} count-mismatch pages are NOT here — a note-count change is the CV counter + Sitting A's
 question, not a text adjudication; they are recorded under <code>count_reconcile</code> in the manifest.</p>
 {{DIS_CARDS}}

 <h2>2 · Agreed sample — {{NAGR}} spans (correlated-error check)</h2>
 <p class="sectnote">Both witnesses read these the same. Confirm the agreement, or flag it as correlated error —
 the one thing unanimity can hide.</p>
 {{AGR_CARDS}}
 <footer style="color:var(--muted);border-top:1px solid var(--line);padding-top:1rem;margin-top:2rem;font-size:.8rem">Disagreement verdicts gate what the re-extraction is allowed to change; agreed-sample verdicts bound the invisible-loss denominator.</footer>
</div>
<script>
var STRIPS={{STRIPMAP}};
var KEY='sitting_b_span_adjudication_v2', FRESHNESS='cold-context';
var DOOR_DIS='adjudicated-by-human-review', DOOR_AGR='audited-by-agent-in-session';
document.querySelectorAll('img.strip').forEach(function(im){var s=STRIPS[im.dataset.page];if(s)im.src=s;else im.remove();});
function stamp(m){var s=document.getElementById('savest');if(s)s.textContent=m;}
function usesCorr(val){return val==='neither'||val==='correlated-error';}
/* The two guards backported from audit_record.validate() — the base console shipped without them.
   A record this refuses is one the verifier would reject on the human door. */
function check(c){
  var v=c.querySelector('input[type=radio]:checked'), e=c.querySelector('.err'), msg='';
  if(v){
    var corr=usesCorr(v.value)?(c.querySelector('.reason').value||'').trim():'';
    var cands=JSON.parse(c.dataset.candidates), notelen=0;
    cands.forEach(function(x){if(x.length>notelen)notelen=x.length;});
    if(v.value==='neither'&&!corr) msg='"neither" needs a correction span.';
    else if(corr&&corr.length>0.6*notelen) msg='That is '+corr.length+' chars against a '+notelen+
      '-char note — a re-transcription, not a span. Give only the disputed fragment.';
  }
  if(e){e.textContent=msg;e.classList.toggle('on',!!msg);}
  c.classList.toggle('bad',!!msg);
  return !msg;
}
/* raw per-card state for persistence — everything the auditor typed, valid or not, so nothing is lost on reload */
function collect(){var d={};document.querySelectorAll('.card').forEach(function(c){
  var v=c.querySelector('input[type=radio]:checked'), reason=c.querySelector('.reason').value;
  if(v||reason) d[c.dataset.spanId]={chosen:v?v.value:null, reason:reason};});
  return d;}
/* export records — only cards that PASS the guards; an invalid card is skipped, not silently emitted */
function records(){var recs=[];document.querySelectorAll('.card').forEach(function(c){
  var v=c.querySelector('input[type=radio]:checked'); if(!v||!check(c)) return;
  var isDis=c.classList.contains('dis');
  recs.push({span_id:c.dataset.spanId, chosen:v.value,
    disputed_span_correction:usesCorr(v.value)?c.querySelector('.reason').value:"",
    rationale:usesCorr(v.value)?"":c.querySelector('.reason').value,
    confidence:null, kind:c.dataset.kind||"agreed",
    provenance:{door:isDis?DOOR_DIS:DOOR_AGR, session_freshness:FRESHNESS, date:new Date().toISOString().slice(0,10)},
    inputs:{crop:c.dataset.crop, crop_sha16:c.dataset.cropSha, candidates:JSON.parse(c.dataset.candidates), page:Number(c.dataset.page)}});});
  return recs;}
function badcount(){var n=0;document.querySelectorAll('.card').forEach(function(c){if(!check(c))n++;});return n;}
function save(){try{localStorage.setItem(KEY,JSON.stringify(collect()));
    var b=badcount();stamp('saved ✓ '+new Date().toLocaleTimeString()+(b?' · '+b+' need fixing':''));}
  catch(e){stamp('⚠ autosave blocked — Export often');}}
function restore(){var d;try{d=JSON.parse(localStorage.getItem(KEY)||'{}');}catch(e){return;}
  Object.keys(d).forEach(function(id){var c=document.querySelector('.card[data-span-id="'+id+'"]');if(!c)return;
    var x=d[id];
    if(x.chosen){var r=c.querySelector('input[value="'+x.chosen+'"]');if(r)r.checked=true;}
    if(x.reason)c.querySelector('.reason').value=x.reason;});}
document.addEventListener('input',function(e){var c=e.target.closest&&e.target.closest('.card');if(c){check(c);save();}});
document.addEventListener('change',function(e){var c=e.target.closest&&e.target.closest('.card');if(c){check(c);save();}});
function exportJSONL(){
  var recs=records(), bad=badcount();
  var manifest={kind:"sitting_manifest",sitting:"span-adjudication",session_freshness:FRESHNESS,
    date:new Date().toISOString().slice(0,10),doors:{disagreement:DOOR_DIS,agreed:DOOR_AGR},
    n_disagreement:document.querySelectorAll('.card.dis').length,n_agreed:document.querySelectorAll('.card.agr').length};
  var lines=[JSON.stringify(manifest)].concat(recs.map(function(r){return JSON.stringify(r);}));
  var blob=new Blob([lines.join("\n")+"\n"],{type:'application/x-ndjson'});
  var a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='sitting_b_verdicts.jsonl';
  document.body.appendChild(a);a.click();a.remove();
  stamp('exported ✓ ('+recs.length+' verdicts'+(bad?', '+bad+' still need fixing':'')+')');}
restore();document.querySelectorAll('.card').forEach(check);save();
</script>'''

if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    build()
