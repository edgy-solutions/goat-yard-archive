"""Render the stratified truth set into a review CONSOLE — the adjudication interface IS the
deliverable (ADR-0015 ergonomics): crop + re-extracted + stored old-layer side by side, batched by
STRATUM so a class is adjudicated per sitting. Verdicts + reasons are captured as the provenance
record. The page doubles as V2's apparatus ground truth and the re-extraction ADR's evidence.

Emits a self-contained HTML fragment (inline CSS, base64 strips) for publishing as an Artifact.
"""
import sys, os, re, io, json, base64, argparse, html
from pathlib import Path

HEBREW = re.compile(r"[֐-׿Ͱ-Ͽ܀-ݏ][֐-׿Ͱ-Ͽ܀-ݏְ-ׇ ]*")
STRATUM_META = {
    "vol7_sample":        ("Vol7 (NT) apparatus — measurement glance", "vol7's mostly-GREEK apparatus run through the vol1-tuned pipeline. Ingests on MEASUREMENT, not architecture-similarity: markers differ (digit/symbol), front matter is shorter, script is Greek. Read the strips — where does it hold, where does vol7 need its own profile facts?"),
    "collapse":           ("Model-collapse outliers", "Two-model run: one reader returned ~1 marker while the other read many (1-vs-N). One model whiffed the whole page — read the strip and decide whose count is real. p86 is ALSO a stitch violation."),
    "stitch":             ("Stitch violations (all 25)", "The stitch guard fired (two-signal, whitelist-gated). measure_continuations found 0 REAL text-splits on vol1, so these are expected to be whitelist-adjacent furniture, not lost text — confirm the guard stayed correct. (Handoff said 15; the full run flags 25 — all loaded, none dropped.)"),
    "acceptance":         ("Acceptance sample (Hebrew-oversampled)", "Balance stratum, oversampled for apparatus Hebrew — licenses 'the ordinary pages are fine too' and stresses the per-region recrop reading edge."),
    "ground_truth":       ("Ground truth", "Pixel-verified pages — the matcher and recrop must be exactly right here."),
    "whitelist_artifact": ("Whitelist artifacts", "The 6 split-OUT / 2 split-IN artifact classes — the stitch guard must stay silent (no false split)."),
    "collision":          ("Anchor collisions", "Pages the old layer mis-anchored (duplicate letters) — position-matching must dissolve them."),
    "hebrew_dense":       ("Hebrew-dense", "Apparatus Hebrew — the per-region recrop closes the reading edge here."),
    "random":             ("Random balance", "Unremarkable pages — licenses 'and the ordinary pages are fine too'."),
}
STATUS_CLASS = {"OK": "ok", "ANCHOR_FLAGGED": "warn", "STITCH_VIOLATION": "crit", "no_apparatus": "muted"}

def hl(text):
    """HTML-escape, then wrap non-Latin (Hebrew/Greek/Syriac) runs for emphasis."""
    esc = html.escape(text)
    return HEBREW.sub(lambda m: f'<span class="heb">{m.group(0)}</span>', esc)

def note_rows(notes):
    return "".join(f'<div class="mk">{html.escape(n["marker"])}</div><div class="tx">{hl(n["text"])}</div>' for n in notes)

def stored_rows(stored):
    return "".join(f'<div class="mk">{html.escape(s["letter"])}</div><div class="tx">{hl(s["text"])}</div>' for s in stored) or '<div class="mk">–</div><div class="tx muted">— none in stored layer —</div>'

def card(r, strip_dir):
    p = r["page"]; st = r["status"]; a = r.get("anchor") or {}
    sc = STATUS_CLASS.get(st, "warn")
    strip = Path(strip_dir) / f"strip_{p}.png"
    img = ""
    if strip.exists():
        b64 = base64.b64encode(strip.read_bytes()).decode()
        img = f'<img class="strip" alt="apparatus strip, page {p}" src="data:image/png;base64,{b64}">'
    badges = [f'<span class="pill {sc}">{html.escape(st)}</span>']
    if r.get("hebrew"): badges.append('<span class="pill accent">Hebrew</span>')
    for c in r.get("recrop_changes", []):
        badges.append(f'<span class="pill accent" title="resolution re-crop">recrop {html.escape(c["old"])}→{html.escape(c["new"])}</span>')
    ua = a.get("unanchored") or []
    if ua:
        gl = [u.get("expected") for u in ua if u.get("expected")]
        why = f'gaps {", ".join(gl)}' if gl else f'{len(ua)} unlinkable · anchors {", ".join(a.get("anchor_letters") or a.get("n_anchors") and [] or [])}'
        badges.append(f'<span class="pill warn" title="fail-loud">flagged {len(ua)}</span>')
    fl = ""
    if ua:
        gl = [u.get("expected") for u in ua if u.get("expected")]
        if gl:
            detail = f'old body is missing the in-text anchors for: {", ".join(gl)}'
        else:
            detail = f'old body has {a.get("n_anchors")} in-text anchors for {r["n_notes"]} notes — cannot place the rest'
        fl = f'<div class="flag"><strong>Linkage (body-layer):</strong> {html.escape(str(detail))}. <span class="muted">The re-extracted notes above are correct; this is the old body\'s dropped superscripts — scopes the in-text anchor re-detect pass, not a re-extraction error.</span></div>'
    return f'''<article class="card">
  <div class="chead"><span class="pg">p{p}</span><div class="badges">{"".join(badges)}</div></div>
  <div class="cbody">
    <div class="cropcol">{img}</div>
    <div class="cmp">
      <div class="col"><h4>Re-extracted <span class="muted">(new · canonical [^N])</span></h4><div class="notes">{note_rows(r["extracted"])}</div></div>
      <div class="col"><h4>Stored <span class="muted">(old overloaded layer)</span></h4><div class="notes">{stored_rows(r.get("stored", []))}</div></div>
    </div>
  </div>
  {fl}
  <div class="verdict" data-page="{p}"><span class="vlabel">Notes verdict</span>
    <label><input type="radio" name="v{p}" value="correct"> correct (≥ stored)</label>
    <label><input type="radio" name="v{p}" value="minor"> minor error</label>
    <label><input type="radio" name="v{p}" value="wrong"> wrong</label>
    <input class="reason" type="text" placeholder="reason / note — provenance record">
  </div>
</article>'''

def build(results, strip_dir):
    from collections import Counter
    by = {}
    for r in results: by.setdefault(r["stratum"], []).append(r)
    stc = Counter(r["status"] for r in results)
    ok = stc.get("OK", 0); total = len(results)
    recrops = sum(len(r.get("recrop_changes", [])) for r in results)
    # note-count vs stored def count = re-extraction COMPLETENESS (its own quality axis)
    def sdef(r): return len(r.get("stored") or [])
    count_ok = sum(1 for r in results if sdef(r) and abs(r["n_notes"] - sdef(r)) <= 1)
    linkable = ok
    body_anchor_loss = total - ok
    strata_rows = "".join(
        f'<tr><td>{STRATUM_META[s][0]}</td><td class="num">{len(by.get(s,[]))}</td>'
        f'<td class="num">{sum(1 for r in by.get(s,[]) if r["status"]=="OK")}</td>'
        f'<td class="num">{sum(1 for r in by.get(s,[]) if r["status"]!="OK")}</td></tr>'
        for s in STRATUM_META if s in by)
    sections = ""
    for s in STRATUM_META:
        if s not in by: continue
        title, desc = STRATUM_META[s]
        cards = "".join(card(r, strip_dir) for r in sorted(by[s], key=lambda x: x["page"]))
        sections += f'<section class="stratum"><header class="shead"><h2>{title}</h2><p>{desc}</p></header>{cards}</section>'
    return f'''<style>{CSS}</style>
<title>Apparatus re-extraction — adjudication</title>
<div class="wrap">
  <div class="toolbar">
    <span id="savest" class="savest">verdicts autosave in this browser</span>
    <button class="tb" type="button" onclick="exportJSON()">⬇ Export verdicts (file)</button>
    <label class="tb">⬆ Import<input type="file" accept="application/json" onchange="importJSON(event)" hidden></label>
    <span class="tbnote">Your work saves automatically as you go — and Export keeps a file you control.</span>
  </div>
  <header class="masthead">
    <div class="kicker">Gill vol.1 · re-extraction acceptance</div>
    <h1>Apparatus adjudication</h1>
    <p class="lede">Two independent axes, and the truth-set run separated them. <strong>Axis 1 — new
    apparatus quality</strong> (adjudicate from the side-by-side): the re-extracted notes match the
    stored-def counts and, where they differ from stored, they are <em>better</em> — OCR errors
    fixed, botched Hebrew recovered, duplicate notes removed, clean canonical markers. <strong>Axis 2
    — linkage to the body</strong>: a page reads <span class="pill warn">flagged</span> when the
    <em>old</em> body dropped its in-text anchor markers (70%+ of pages — a pre-existing body-layer
    defect, the "OCR fails to detect footnote lettering" fossil), so the correct new notes have
    nowhere to attach. <strong>Flagged is a body-layer finding, not a re-extraction failure</strong> —
    it scopes the next pass (in-text anchor re-detection), it does not fault the apparatus.</p>
    <div class="claim">
      <div class="cbox"><div class="big">{count_ok}/{total}</div><div class="lbl">new note-count matches stored (apparatus complete)</div></div>
      <div class="cbox"><div class="big">{linkable}/{total}</div><div class="lbl">body anchors intact → linkable now</div></div>
      <div class="cbox"><div class="big">{body_anchor_loss}</div><div class="lbl">old-body anchor loss → in-text re-detect (next scope)</div></div>
      <div class="cbox"><div class="big">{recrops}</div><div class="lbl">Hebrew spans closed by re-crop</div></div>
    </div>
    <table class="strata"><thead><tr><th>Stratum</th><th class="num">pages</th><th class="num">OK</th><th class="num">flagged</th></tr></thead><tbody>{strata_rows}</tbody></table>
  </header>
  {sections}
  <footer class="foot">Adjudicate by stratum · verdicts are the provenance record · doubles as V2 apparatus ground truth + re-extraction ADR evidence.</footer>
</div>
<script>{JS}</script>'''

CSS = r'''
:root{
  --paper:#f4f2ee; --panel:#fbfaf7; --ink:#201d1a; --muted:#6b6459; --line:#e2ddd3;
  --accent:#7c2d2d; --ok:#2f6b3f; --warn:#9a6a12; --crit:#a33232;
  --serif:"Iowan Old Style",Palatino,"Palatino Linotype",Georgia,serif;
  --sans:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  --mono:ui-monospace,"SFMono-Regular","Cascadia Code",Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){:root{
  --paper:#17150f; --panel:#201d16; --ink:#ece7dd; --muted:#9a9082; --line:#332e24;
  --accent:#d98a6a; --ok:#7fb98a; --warn:#d6a84e; --crit:#e08a7f;
}}
:root[data-theme="light"]{--paper:#f4f2ee;--panel:#fbfaf7;--ink:#201d1a;--muted:#6b6459;--line:#e2ddd3;--accent:#7c2d2d;--ok:#2f6b3f;--warn:#9a6a12;--crit:#a33232;}
:root[data-theme="dark"]{--paper:#17150f;--panel:#201d16;--ink:#ece7dd;--muted:#9a9082;--line:#332e24;--accent:#d98a6a;--ok:#7fb98a;--warn:#d6a84e;--crit:#e08a7f;}
*{box-sizing:border-box}
body{margin:0}
.toolbar{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:.8rem;flex-wrap:wrap;
  background:var(--panel);border-bottom:1px solid var(--line);
  padding:.6rem clamp(1rem,4vw,3rem);font-size:.82rem}
.savest{font-family:var(--mono);color:var(--ok);font-weight:600;min-width:14rem}
.tb{font:inherit;font-size:.82rem;background:var(--paper);color:var(--ink);border:1px solid var(--accent);
  border-radius:7px;padding:.35rem .8rem;cursor:pointer}
.tb:hover{background:color-mix(in srgb,var(--accent) 12%,var(--paper))}
.tb:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.tbnote{color:var(--muted)}
.wrap{background:var(--paper);color:var(--ink);font-family:var(--sans);line-height:1.5;
  padding:clamp(1rem,4vw,3rem);min-height:100vh}
.masthead{max-width:70rem;margin:0 auto 2.5rem}
.kicker{font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:600}
h1{font-family:var(--serif);font-size:clamp(2rem,5vw,3rem);margin:.2em 0 .3em;text-wrap:balance;font-weight:600}
.lede{max-width:62ch;color:var(--ink);font-size:1.02rem}
.lede strong{color:var(--accent)}
.claim{display:flex;gap:1rem;flex-wrap:wrap;margin:1.6rem 0 1.2rem}
.cbox{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:1rem 1.3rem;min-width:9rem}
.big{font-family:var(--mono);font-size:1.9rem;font-weight:600;font-variant-numeric:tabular-nums;color:var(--accent)}
.lbl{font-size:.78rem;color:var(--muted)}
.strata{border-collapse:collapse;width:100%;max-width:34rem;font-size:.86rem}
.strata th,.strata td{border-bottom:1px solid var(--line);padding:.4rem .6rem;text-align:left}
.strata .num{text-align:right;font-family:var(--mono);font-variant-numeric:tabular-nums}
.stratum{max-width:70rem;margin:0 auto 2.5rem}
.shead{border-bottom:2px solid var(--accent);padding-bottom:.4rem;margin-bottom:1.2rem}
.shead h2{font-family:var(--serif);font-size:1.5rem;margin:0}
.shead p{margin:.3em 0 0;color:var(--muted);font-size:.9rem;max-width:62ch}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:1.1rem 1.2rem;margin-bottom:1.1rem}
.chead{display:flex;align-items:center;justify-content:space-between;gap:1rem;margin-bottom:.8rem}
.pg{font-family:var(--mono);font-weight:600;font-size:1.05rem}
.badges{display:flex;gap:.4rem;flex-wrap:wrap;justify-content:flex-end}
.pill{font-size:.7rem;font-family:var(--mono);padding:.16rem .5rem;border-radius:999px;border:1px solid var(--line);white-space:nowrap}
.pill.ok{color:var(--ok);border-color:color-mix(in srgb,var(--ok) 40%,var(--line))}
.pill.warn{color:var(--warn);border-color:color-mix(in srgb,var(--warn) 45%,var(--line))}
.pill.crit{color:#fff;background:var(--crit);border-color:var(--crit)}
.pill.accent{color:var(--accent);border-color:color-mix(in srgb,var(--accent) 40%,var(--line))}
.pill.muted{color:var(--muted)}
.cbody{display:grid;grid-template-columns:minmax(260px,38%) 1fr;gap:1.2rem;align-items:start}
.strip{width:100%;border:1px solid var(--line);border-radius:6px;background:#fff}
.cmp{display:grid;grid-template-columns:1fr 1fr;gap:1rem;min-width:0}
.col{min-width:0}
.col h4{margin:0 0 .5rem;font-size:.82rem;font-weight:600}
.col h4 .muted{font-weight:400}
.notes{display:grid;grid-template-columns:auto 1fr;gap:.15rem .6rem;font-family:var(--serif);font-size:.92rem}
.notes .mk{font-family:var(--mono);font-size:.78rem;color:var(--accent);white-space:nowrap;padding-top:.15rem}
.notes .tx{min-width:0;overflow-wrap:anywhere}
.heb{font-size:1.12em;padding:0 .05em}
.muted{color:var(--muted)}
.flag{margin-top:.8rem;padding:.5rem .7rem;border-left:3px solid var(--warn);background:color-mix(in srgb,var(--warn) 8%,transparent);font-size:.84rem;border-radius:0 6px 6px 0}
.verdict{display:flex;align-items:center;gap:1rem;flex-wrap:wrap;margin-top:.9rem;padding-top:.8rem;border-top:1px dashed var(--line);font-size:.82rem}
.vlabel{font-weight:600;text-transform:uppercase;letter-spacing:.08em;font-size:.7rem;color:var(--muted)}
.verdict label{display:inline-flex;align-items:center;gap:.3rem;cursor:pointer}
.reason{flex:1;min-width:12rem;background:var(--paper);border:1px solid var(--line);border-radius:6px;
  padding:.35rem .6rem;color:var(--ink);font-family:var(--sans);font-size:.84rem}
.reason:focus,.verdict input:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.foot{max-width:70rem;margin:2rem auto 0;color:var(--muted);font-size:.8rem;border-top:1px solid var(--line);padding-top:1rem}
@media (max-width:720px){.cbody{grid-template-columns:1fr}.cmp{grid-template-columns:1fr}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
'''

JS = r'''
var KEY='gill_apparatus_adjudication_v1';
function collect(){var d={};document.querySelectorAll('.verdict').forEach(function(v){
  var p=v.dataset.page;var r=v.querySelector('input[type=radio]:checked');
  var reason=v.querySelector('.reason').value;
  if(r||reason)d[p]={verdict:r?r.value:null,reason:reason};});return d;}
function stamp(msg){var s=document.getElementById('savest');if(s)s.textContent=msg;}
var dirty=false;
function save(){try{localStorage.setItem(KEY,JSON.stringify(collect()));
  stamp('saved ✓ '+new Date().toLocaleTimeString());dirty=false;}
  catch(e){stamp('⚠ autosave blocked here — use Export to keep your work');}}
function restore(){var d;try{d=JSON.parse(localStorage.getItem(KEY)||'{}');}catch(e){return;}
  Object.keys(d).forEach(function(p){var vd=document.querySelector('.verdict[data-page="'+p+'"]');
    if(!vd)return;var v=d[p];
    if(v.verdict){var r=vd.querySelector('input[value="'+v.verdict+'"]');if(r)r.checked=true;}
    if(v.reason)vd.querySelector('.reason').value=v.reason;});}
document.addEventListener('input',function(e){if(e.target.closest('.verdict')){dirty=true;save();}});
document.addEventListener('change',function(e){if(e.target.closest('.verdict')){dirty=true;save();}});
window.addEventListener('beforeunload',function(e){if(dirty){e.preventDefault();e.returnValue='';}});
function exportJSON(){var payload={when:new Date().toISOString(),verdicts:collect()};
  var blob=new Blob([JSON.stringify(payload,null,2)],{type:'application/json'});
  var a=document.createElement('a');a.href=URL.createObjectURL(blob);
  a.download='gill_apparatus_verdicts.json';document.body.appendChild(a);a.click();a.remove();
  dirty=false;stamp('exported ✓ '+new Date().toLocaleTimeString());}
function importJSON(ev){var f=ev.target.files[0];if(!f)return;var rd=new FileReader();
  rd.onload=function(){try{var d=JSON.parse(rd.result);var v=d.verdicts||d;
    try{localStorage.setItem(KEY,JSON.stringify(v));}catch(e){}
    Object.keys(v).forEach(function(p){var vd=document.querySelector('.verdict[data-page="'+p+'"]');
      if(!vd)return;var x=v[p];if(x.verdict){var r=vd.querySelector('input[value="'+x.verdict+'"]');if(r)r.checked=true;}
      if(x.reason)vd.querySelector('.reason').value=x.reason;});
    stamp('imported ✓');}catch(e){stamp('⚠ could not read that file');}};rd.readAsText(f);}
restore();save();
'''

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(Path(__file__).parent / "truthset_out"))
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    d = Path(a.dir)
    results = json.loads((d / "truthset_results.json").read_text(encoding="utf-8"))
    htmlout = build(results, d)
    out = Path(a.out) if a.out else d / "adjudication.html"
    out.write_text(htmlout, encoding="utf-8")
    print(f"wrote {out} ({len(results)} pages)")

if __name__ == "__main__": main()
