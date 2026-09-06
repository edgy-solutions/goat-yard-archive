"""Native-resolution recheck console — the 7 lowest-resolution truthset strips (text band under ~22px)
shown as SHIPPED 1600px strip vs NATIVE band re-cropped from the 3584px scan via the same presplit
detector (upscale=1 = true native, no interpolation). No renderer change: this reads the native scan
directly, changes nothing in the pipeline. Purpose: the correlated-error class (spurious nikud, mis-OCR
of worn glyphs) concentrates on low-res strips — p593 is the flagged case, p379 already flipped to
'neither' from native. If native detail flips any of the seven verdicts, better to know before ingest.
Each card carries the span(s) on that page, the two witness readings, and the CURRENT settled verdict,
so a flip is legible. Click either image to zoom to full native pixels."""
import sys, io, json, base64, hashlib, html
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import cv_footnote_presplit as ps
import audit_record as AR
from PIL import Image

HERE = Path(__file__).parent
IMG = Path("C:/Users/cnogr/git/dr-voluminous/commentary/volume1")
SEVEN = [619, 230, 657, 593, 385, 520, 379]

def _load(p): return json.load(io.open(p, encoding="utf-8"))
def verdicts(p): return {r["span_id"]: r for r in AR.load_verdicts(HERE / "audits" / p) if r.get("kind") != "sitting_manifest"}
def esc(s): return html.escape(str(s) if s is not None else "")

def b64(im):
    buf = io.BytesIO(); im.convert("L").save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

def native_band(pg):
    """The footnote band at native resolution via the same detector that made the strips (upscale=1)."""
    strip, info = ps.presplit(str(IMG / f"page{pg}_image1.png"), upscale=1)
    if strip is None:                                    # presplit blanked -> native footnote region fallback
        im = Image.open(IMG / f"page{pg}_image1.png"); W, H = im.size
        return im.crop((0, int(H * 0.60), W, H)), "full-page-fallback"
    return strip, info.get("mode", "?")

def build():
    m = _load(HERE / "audits" / "sitting_manifest_span_adjudication.json")
    dis = {s["span_id"]: s for s in m["disagreement"]}
    agr = {a["span_id"]: a for a in m["agreed_sample"]}
    res = verdicts("chris_sitting_b_residue_20260823.jsonl")
    agent = verdicts("agent_session_20260823.jsonl")
    cards = []
    for pg in SEVEN:
        old = Image.open(HERE / "truthset_review" / f"strip_{pg}.png")
        nat, mode = native_band(pg)
        factor = nat.size[0] / old.size[0]
        spans = [sid for sid in list(dis) + list(agr) if int(sid.split(":")[0][1:]) == pg]
        rows = []
        for sid in spans:
            src = dis.get(sid) or agr.get(sid)
            v = res.get(sid) or agent.get(sid)
            verdict = v["chosen"] if v else "(unbanked)"
            corr = (v.get("disputed_span_correction") if v else None) or ""
            rows.append(
                f'<tr><td class="sid">{esc(sid)}</td>'
                f'<td class="rd">{esc(src["stored"])}</td>'
                f'<td class="rd">{esc(src["extracted"])}</td>'
                f'<td class="vd">{esc(verdict)}{("<br><span class=corr>"+esc(corr)+"</span>") if corr else ""}</td></tr>')
        band = None
        # median text-band height (same measure used to select the seven)
        import numpy as np
        a = np.array(old.convert("L")) < 128; r = a.sum(axis=1); thr = max(2, r.max() * 0.04); on = r > thr
        hs = []; st = None
        for i, val in enumerate(on):
            if val and st is None: st = i
            elif not val and st is not None:
                if i - st >= 3: hs.append(i - st)
                st = None
        band = int(np.median(hs)) if hs else 0
        cards.append(f'''<article class="card">
 <div class="chead"><span class="pg">p{pg}</span>
   <span class="pill">band ~{band}px · native {factor:.2f}× · {esc(mode)}</span></div>
 <table class="spans"><tr><th>span</th><th>A — stored</th><th>B — extracted</th><th>verdict</th></tr>{"".join(rows)}</table>
 <div class="imgs">
   <figure><figcaption>shipped strip — {old.size[0]}×{old.size[1]} px</figcaption>
     <img class="shot" src="{b64(old)}" alt="shipped strip p{pg}"></figure>
   <figure><figcaption>native band — {nat.size[0]}×{nat.size[1]} px</figcaption>
     <img class="shot" src="{b64(nat)}" alt="native band p{pg}"></figure>
 </div>
</article>''')
    doc = TEMPLATE.replace("{{CARDS}}", "\n".join(cards)).replace("{{N}}", str(len(SEVEN)))
    out = HERE / "audits" / "native_recheck_20260906.html"
    out.write_text(doc, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size//1024}KB, {len(SEVEN)} cards)")

TEMPLATE = r'''<style>
:root{--paper:#f4f2ee;--panel:#fbfaf7;--ink:#201d1a;--muted:#6b6459;--line:#e2ddd3;--accent:#7c2d2d;--ok:#2f6b3f;--warn:#9a6a12;
 --serif:"Gentium Plus","Times New Roman",serif;--sans:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;--mono:ui-monospace,Consolas,Menlo,monospace;}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#17150f;--panel:#201d16;--ink:#ece7dd;--muted:#9a9082;--line:#332e24;--accent:#d98a6a;--ok:#7fb98a;--warn:#d6a84e;}}
:root[data-theme="dark"]{--paper:#17150f;--panel:#201d16;--ink:#ece7dd;--muted:#9a9082;--line:#332e24;--accent:#d98a6a;--ok:#7fb98a;--warn:#d6a84e;}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);line-height:1.5}
.wrap{padding:clamp(1rem,4vw,3rem);max-width:80rem;margin:0 auto}
.kicker{font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:600}
h1{font-family:var(--mono);font-size:clamp(1.5rem,4vw,2.3rem);margin:.2em 0 .3em}
.lede{max-width:66ch}.lede strong{color:var(--accent)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:1.1rem 1.2rem;margin-bottom:1.6rem}
.chead{display:flex;align-items:center;justify-content:space-between;margin-bottom:.6rem}
.pg{font-family:var(--mono);font-weight:600;font-size:1.15rem}
.pill{font-size:.72rem;font-family:var(--mono);padding:.16rem .5rem;border-radius:999px;border:1px solid var(--line);color:var(--muted)}
table.spans{width:100%;border-collapse:collapse;font-size:.86rem;margin-bottom:.9rem}
.spans th{text-align:left;font-size:.68rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);border-bottom:1px solid var(--line);padding:.3rem .4rem}
.spans td{padding:.35rem .4rem;vertical-align:top;border-bottom:1px solid var(--line)}
.sid{font-family:var(--mono);font-size:.8rem;white-space:nowrap}
.rd{font-family:var(--serif);font-size:1rem;overflow-wrap:anywhere}
.vd{font-family:var(--mono);font-size:.82rem;color:var(--accent);white-space:nowrap}
.corr{font-family:var(--serif);color:var(--ink);font-size:.95rem}
.imgs{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
@media(max-width:820px){.imgs{grid-template-columns:1fr}}
figure{margin:0}figcaption{font-size:.72rem;color:var(--muted);font-family:var(--mono);margin-bottom:.3rem}
img.shot{width:100%;border:1px solid var(--line);border-radius:6px;background:#fff;display:block;cursor:zoom-in;image-rendering:crisp-edges}
img.shot.zoom{position:fixed;inset:2vh 2vw;width:96vw;height:96vh;object-fit:contain;z-index:50;background:#fff;cursor:zoom-out;border-width:2px}
</style>
<title>Native Recheck — 7 Strips</title>
<div class="wrap">
 <div class="kicker">Last sitting · resolution recheck</div>
 <h1>The 7 low-resolution strips</h1>
 <p class="lede">The seven Sitting B strips with the smallest text band (under ~22px). Each shows the
 <strong>shipped 1600px strip</strong> the auditors read against the <strong>native band</strong>
 re-cropped from the 3584px scan by the same detector (no interpolation). The correlated-error class —
 spurious vowel-points, worn-glyph mis-reads — concentrates exactly here: p593 is the flagged case,
 p379 already flipped to <em>neither</em> once read at native. <strong>Click either image to zoom to full
 native pixels.</strong> If native detail flips a verdict, it flips before ingest, not after.</p>
 {{CARDS}}
 <footer style="color:var(--muted);border-top:1px solid var(--line);padding-top:1rem;font-size:.8rem">
 If all seven hold at native resolution, the strip-resolution caveat stands as named (n={{N}}) and the
 acceptance claim proceeds. Renderer unchanged — this console only reads the native scan.</footer>
</div>
<script>
document.addEventListener('click',function(e){if(e.target.classList&&e.target.classList.contains('shot'))e.target.classList.toggle('zoom');});
</script>'''

if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    build()
