"""Seed sitting — one card per (corpus) unbroken run: the native crop of the run's first footnote band, you
enter the FIRST marker letter, and the invariant propagates the label through the whole run. Human seeds only
here; agent-seeds (the bootstrap) are recorded separately with margin+confidence. Memoir runs (file 10–88)
and front matter (<89) are excluded — corpus only. Export: {run:[start,end], seed_letter, first_page}."""
import base64, io, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from PIL import Image
import cv_footnote_presplit as ps
import note_start_detect as NS

A = Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits")
IMG = Path("C:/Users/cnogr/git/dr-voluminous/commentary/volume1")
DATE = "20260913"

def _first_note_crop(pg, height=440):
    """Crop the reading-order STRIP from the FIRST detected note-start down. The seed card MUST be anchored on
    the detector's start[0] — the SAME `page_starts` call and ordering the harvest walks — so that seed-index ==
    harvest-index BY CONSTRUCTION: the human reads the letter at note[0], the harvest labels note[0] with it and
    propagates. The old whitespace-gap heuristic guessed a band top independently and could land BELOW note[0]
    (or clip it), shifting the human's 'first' by one and poisoning every propagated label from the start.
    Returns (crop_image, n_starts) or (None, 0) when presplit/detection find nothing."""
    strip, info = ps.presplit(str(IMG / f"page{pg}_image1.png"), upscale=1)
    if strip is None:
        return None, 0
    starts = sorted(NS.page_starts(strip), key=lambda p: p[1])   # reading order; start[0] = the run's first marker
    if not starts:
        return None, 0
    y0 = max(0, int(starts[0][1]) - 8)                           # a hair above note[0] so its raised marker is whole
    return strip.crop((0, y0, strip.width, min(strip.height, y0 + height))), len(starts)

def build(n_longest=40):
    census = json.loads((A / "chain_census.json").read_text(encoding="utf-8"))
    nn = {r["page"]: (r.get("n_notes") or 0) for r in (json.loads(l) for l in
          open(A.parent / "vol1_apparatus.jsonl", encoding="utf-8") if l.strip()) if "page" in r}
    corpus = [e for e in census["runs"] if e[0] >= 89]                 # exclude front matter + memoir
    # rank by TOTAL notes in the run (exemplar yield), not page-length; drop note-less (body-only) runs, and
    # anchor the card on the run's first page that actually HAS notes (skip leading 0-note body pages)
    def first_noted(e):
        return next((p for p in range(e[0], e[1] + 1) if nn.get(p, 0) > 0), None)
    scored = [(sum(nn.get(p, 0) for p in range(e[0], e[1] + 1)), first_noted(e), e) for e in corpus]
    scored = sorted([(t, fp, e) for t, fp, e in scored if t > 0 and fp is not None], reverse=True)
    cards = []
    for total, fp, e in scored[:n_longest]:
        pg = fp
        crop, n_starts = _first_note_crop(pg)                         # anchored on detector start[0] (harvest-aligned)
        if crop is None:                                              # no detected note-start → skip (can't anchor)
            continue
        b = io.BytesIO(); crop.save(b, format="PNG")
        cards.append(dict(run=e, length=e[1] - e[0] + 1, first_page=pg, printed=pg - 88, n_starts=n_starts,
                          img="data:image/png;base64," + base64.b64encode(b.getvalue()).decode()))
    html = _T.replace("/*DATA*/", json.dumps(cards)).replace("{DATE}", DATE).replace("{N}", str(len(cards)))
    out = A / f"marker_seed_console_{DATE}.html"; out.write_text(html, encoding="utf-8")
    cov = sum(c["length"] for c in cards)
    print(f"wrote {out} ({out.stat().st_size//1024} KB, {len(cards)} corpus runs, covering {cov} pages)")

_T = r"""<!doctype html><html lang=en><head><meta charset=utf-8><title>Marker seed sitting — vol1 {DATE}</title><style>
:root{--pa:#f6f4ee;--ink:#1a1a1a;--ru:#cbc5b6;--ac:#2f6b8f;--rej:#9a2b2b}
*{box-sizing:border-box}body{margin:0;background:var(--pa);color:var(--ink);font:14px system-ui}
header{position:sticky;top:0;background:#26302f;color:#f2efe6;padding:10px 16px;display:flex;gap:16px;align-items:center;z-index:9}
header button{margin-left:auto;background:var(--ac);color:#fff;border:0;padding:7px 14px;border-radius:5px;cursor:pointer}
.card{max-width:1500px;margin:12px auto;background:#fff;border:1px solid var(--ru);border-radius:7px;overflow:hidden}
.m{display:flex;gap:14px;align-items:center;padding:8px 12px;border-bottom:1px solid var(--ru)}
.m b{font-size:15px}.m .hint{color:#6b6459;font-size:12px}
.m input{width:46px;font:18px ui-monospace,monospace;text-align:center;padding:4px;border:2px solid var(--ru);border-radius:5px;text-transform:lowercase}
.m input.ok{border-color:#2f7d4f;background:#eef7f0}.m input.bad{border-color:var(--rej);background:#fbeeee}
.card img{display:block;width:100%;background:#faf9f5}
</style></head><body>
<header><h1 style="font-size:15px;margin:0">Marker seed sitting · vol1</h1><span id=stat class=hint></span>
<button id=export>Export seeds JSONL</button></header><div id=cards></div>
<script>
const C=/*DATA*/, KEY="mseed_"+"{DATE}", LEGAL="abcdefghiklmnopqrstuwxyz";
let S=JSON.parse(localStorage.getItem(KEY)||"{}");
function save(){localStorage.setItem(KEY,JSON.stringify(S));stat();}
function stat(){document.getElementById("stat").textContent=Object.keys(S).length+" / {N} seeded";}
C.forEach((c,i)=>{const k=c.first_page;
  const d=document.createElement("div");d.className="card";
  d.innerHTML=`<div class=m><b>run ${c.run[0]}–${c.run[1]}</b> <span class=hint>${c.length} pages · first page file ${c.first_page} (printed ${c.printed}) · read note[0] of ${c.n_starts} — the TOP marker in the crop</span>
    <span style="margin-left:auto">first marker letter: <input maxlength=1 data-k="${k}" value="${(S[k]||{}).letter||''}"></span>
    <span class=hint>a–z, no j/v</span></div><img src="${c.img}">`;
  document.getElementById("cards").appendChild(d);
  const inp=d.querySelector("input");
  function upd(){const v=inp.value.toLowerCase();inp.value=v;
    const ok=LEGAL.includes(v);inp.className=v?(ok?"ok":"bad"):"";
    if(ok){S[k]={run:c.run,letter:v,first_page:c.first_page};save();}else if(!v){delete S[k];save();}}
  inp.oninput=upd;upd();});
stat();
document.getElementById("export").onclick=()=>{
  const lines=C.filter(c=>S[c.first_page]).map(c=>JSON.stringify({run:c.run,first_page:c.first_page,printed_page:c.printed,
    seed_letter:S[c.first_page].letter,source:"human",door:"marker-seed-sitting",date:"{DATE}"}));
  const b=new Blob([lines.join("\n")],{type:"application/x-ndjson"});const a=document.createElement("a");
  a.href=URL.createObjectURL(b);a.download="marker_seeds_human_{DATE}.jsonl";a.click();};
</script></body></html>"""

if __name__ == "__main__":
    build()
