"""Render FINAL-vs-corrected ratified-box disagreements as native-resolution diff cards (Chris, 2026-09-20).

    python render_truth_diff.py [out.html]

WHY THIS EXISTS. Two ratified truth files sit side by side in audits/ — `note_box_truth_20260906_FINAL.jsonl`
(227 boxes) and `..._corrected.jsonl` (226). Both carry `ratified_by: human`, both carry `agent_corrected:
true`, and both were written in a session marked `in-context-WARN`. They agree on 31 of 33 pages exactly.
They disagree on TWO: p200 and p261. Every geometry number this project has reported was scored against
FINAL, so which file is right is not a filing question — it is the measuring stick.

This is an ADJUDICATION, not a grading. Per the standing rule on re-extraction diffs, the verdict is
keep / take / neither, never a score: the older file is not on trial and the newer one is not presumed
better. Both are human-ratified readings of the same pixels, and the pixels are the only tiebreaker — which
is why each card shows the native-resolution crop and not a summary of it.

NATIVE RESOLUTION, AND WHAT THAT MEANS. Strips are built with `presplit(..., upscale=1)`, which performs no
resize: strip pixels ARE page pixels. The crops below are emitted at 1:1 and displayed at 1:1, scrolling
horizontally inside their own container rather than being scaled to fit. Box overlays are absolutely
positioned at the same scale, so an overlay edge sitting on a glyph edge on screen is sitting on it in the
file. Nothing here is resampled.

VERDICT-ONLY. There is no box editor. The console offers FINAL / corrected / neither per disagreement
group, plus a free-text reason, and copies the result as JSON. `neither` is a first-class outcome and is
expected to be used: on p200 both files may be drifting, and a console that cannot express that would
extract a false verdict from a real uncertainty.

`dir="auto"` is set on the text containers as the standing convention. It protects nothing on THIS console
— the ratified notes carry boxes and status only, no transcribed text — and it is set so the convention
holds by default rather than by remembering.

DEV + CONTAMINATED ONLY: p200 is a DEV page, p261 is one of the 5 CONTAMINATED. Neither is SEALED; the
split (audits/ratified_split_20260920.json) is not touched by opening these."""
import base64, html, io, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import cv_footnote_presplit as ps

D = Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1")
FINAL = D / "audits" / "note_box_truth_20260906_FINAL.jsonl"
CORR = D / "audits" / "note_box_truth_20260906_corrected.jsonl"
SPLIT = D / "audits" / "ratified_split_20260920.json"
IMG = Path("C:/Users/cnogr/git/dr-voluminous/commentary/volume1")
PAD = 12          # context rows above/below a disagreement group, in native px


def load(path):
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("page") is not None:
            out[r["page"]] = r
    return out


def groups(fb, cb):
    """Maximal y-clusters in which the two files disagree.

    A box present identically in both files is AGREED and is excluded. The rest are clustered by y-overlap
    across both files, so one structural disagreement (a split, a shifted boundary) becomes one verdict
    instead of two or three unrelated-looking ones. Boxes are carried with their ORIGINAL index so the
    card can show where they sit in each file's list — which is how p261's out-of-order storage shows up."""
    fs, cs = {tuple(b) for b in fb}, {tuple(b) for b in cb}
    items = ([("FINAL", i, b) for i, b in enumerate(fb) if tuple(b) not in cs]
             + [("corrected", i, b) for i, b in enumerate(cb) if tuple(b) not in fs])
    items.sort(key=lambda t: t[2][1])
    out = []
    for it in items:
        if out and it[2][1] < max(x[2][3] for x in out[-1]):
            out[-1].append(it)
        else:
            out.append([it])
    return out


def png_b64(im):
    buf = io.BytesIO(); im.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def card(page, F, C, strip):
    fb = [n["strip_box"] for n in F["notes"]]
    cb = [n["strip_box"] for n in C["notes"]]
    fst = [n.get("status") for n in F["notes"]]
    cst = [n.get("status") for n in C["notes"]]
    gs = groups(fb, cb)

    fy = [b[1] for b in fb]
    warn = ""
    if fy != sorted(fy):
        bad = [i for i in range(1, len(fy)) if fy[i] < fy[i - 1]]
        warn = ('<div class="warn"><b>FINAL is not in reading order on this page.</b> Its note list runs '
                f'y0 = {fy} — index {", ".join(str(i) for i in bad)} steps backwards. '
                f'The record says <code>missed_starts_split: {F.get("missed_starts_split")}</code>: the '
                'split boxes were <b>appended</b> to the list instead of inserted in place. That is a '
                'mechanical artifact of how the file was written, not a claim about the page — but any '
                'scorer that pairs detected region <i>k</i> with ratified note <i>k</i> by position is '
                'guaranteed wrong here for the last three notes, whatever the pixels say. '
                f'corrected is monotone ({[b[1] for b in cb]}).</div>')

    secs = []
    for gi, g in enumerate(gs):
        y0 = max(0, min(b[1] for _, _, b in g) - PAD)
        y1 = min(strip.height, max(b[3] for _, _, b in g) + PAD)
        crop = strip.crop((0, y0, strip.width, y1))
        b64 = png_b64(crop)
        ovl = []
        for src, idx, b in g:
            cls = "f" if src == "FINAL" else "c"
            st = (fst[idx] if src == "FINAL" else cst[idx])
            ovl.append(f'<div class="bx {cls}" style="left:{b[0]}px;top:{b[1]-y0}px;'
                       f'width:{max(1,b[2]-b[0])}px;height:{max(1,b[3]-b[1])}px">'
                       f'<span class="lb {cls}">{src}[{idx}] {b[1]}\u2013{b[3]} \u00b7 {html.escape(str(st))}</span></div>')
        rows = "".join(
            f'<tr class="{ "f" if s=="FINAL" else "c" }"><td>{s}</td><td>[{i}]</td>'
            f'<td>{b[1]}\u2013{b[3]}</td><td>{b[3]-b[1]}px</td>'
            f'<td>{html.escape(str(fst[i] if s=="FINAL" else cst[i]))}</td></tr>'
            for s, i, b in g)
        nf = sum(1 for s, _, _ in g if s == "FINAL")
        nc = len(g) - nf
        shape = (f"{nf} FINAL box{'es' if nf != 1 else ''} vs {nc} corrected "
                 f"box{'es' if nc != 1 else ''} over y {y0}\u2013{y1}")
        secs.append(f"""
<section class="grp" data-page="{page}" data-grp="{gi}">
  <h3>p{page} \u00b7 disagreement {gi+1} of {len(gs)} <span class="shape">{shape}</span></h3>
  <div class="ctl">
    <button onclick="lay(this,'both')" class="on">both</button>
    <button onclick="lay(this,'f')">FINAL only</button>
    <button onclick="lay(this,'c')">corrected only</button>
    <button onclick="lay(this,'none')">pixels only</button>
    <span class="native">native 1:1 \u00b7 {strip.width}\u00d7{y1-y0}px \u00b7 scroll \u2192</span>
  </div>
  <div class="scroll"><div class="stage" style="width:{strip.width}px;height:{y1-y0}px">
    <img src="data:image/png;base64,{b64}" width="{strip.width}" height="{y1-y0}">
    {''.join(ovl)}
  </div></div>
  <table class="bt"><tr><th>file</th><th>idx</th><th>y</th><th>h</th><th>status</th></tr>{rows}</table>
  <div class="verdict" dir="auto">
    <b>verdict</b>
    <label><input type="radio" name="v{page}_{gi}" value="FINAL"> FINAL is right</label>
    <label><input type="radio" name="v{page}_{gi}" value="corrected"> corrected is right</label>
    <label><input type="radio" name="v{page}_{gi}" value="neither"> neither \u2014 both wrong here</label>
    <input class="why" type="text" dir="auto" placeholder="reason (optional, but the reason is the record)">
  </div>
</section>""")

    agreed = len({tuple(b) for b in fb} & {tuple(b) for b in cb})
    return f"""
<article class="pg">
  <h2>p{page} <span class="sub">{F['mode']} \u00b7 strip {F['strip_size'][0]}\u00d7{F['strip_size'][1]} \u00b7
    FINAL {len(fb)} boxes / corrected {len(cb)} \u00b7 {agreed} identical \u00b7 {len(gs)} disagreement{'s' if len(gs)!=1 else ''}</span></h2>
  <div class="prov" dir="auto">both records: <code>ratified_by: {F['provenance'].get('ratified_by')}</code>,
    <code>agent_corrected: {F.get('agent_corrected')}</code>,
    <code>session_freshness: {F['provenance'].get('session_freshness')}</code> \u00b7
    FINAL <code>missed_starts_split: {F.get('missed_starts_split')}</code>,
    corrected <code>missed_starts_split: {C.get('missed_starts_split')}</code></div>
  {warn}
  {''.join(secs)}
</article>"""


CSS = """
:root{--bg:#faf9f7;--fg:#1c1b19;--mut:#6b6864;--line:#dcd8d2;--f:#c02a2a;--c:#1a63c4}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 -apple-system,Segoe UI,system-ui,sans-serif}
header{padding:20px 24px;border-bottom:1px solid var(--line);background:#fff}
h1{margin:0 0 6px;font-size:19px} .lede{margin:0;color:var(--mut);max-width:78ch}
main{padding:20px 24px;max-width:100%}
.pg{background:#fff;border:1px solid var(--line);border-radius:6px;padding:16px;margin:0 0 22px}
h2{margin:0 0 4px;font-size:17px} .sub{font-weight:400;color:var(--mut);font-size:13px}
.prov{color:var(--mut);font-size:12px;margin:0 0 10px} code{background:#f0eeea;padding:1px 4px;border-radius:3px}
.warn{background:#fff7e6;border:1px solid #e8c986;border-left:3px solid #d99a2b;padding:10px 12px;
  border-radius:4px;margin:10px 0;font-size:13px}
.grp{border-top:1px solid var(--line);padding-top:14px;margin-top:14px}
h3{margin:0 0 8px;font-size:14px} .shape{font-weight:400;color:var(--mut)}
.ctl{margin:0 0 8px} .ctl button{font:inherit;font-size:12px;padding:3px 10px;margin-right:5px;
  border:1px solid var(--line);background:#fff;border-radius:4px;cursor:pointer}
.ctl button.on{background:var(--fg);color:#fff;border-color:var(--fg)}
.native{color:var(--mut);font-size:11px;margin-left:8px}
.scroll{overflow-x:auto;border:1px solid var(--line);background:#fff}
.stage{position:relative} .stage img{display:block;image-rendering:pixelated}
.bx{position:absolute;box-sizing:border-box;pointer-events:none}
.bx.f{border:2px solid var(--f)} .bx.c{border:2px dashed var(--c)}
.lb{position:absolute;left:2px;top:-15px;font:11px/1.3 ui-monospace,Menlo,Consolas,monospace;
  padding:0 4px;border-radius:2px;white-space:nowrap;color:#fff}
.lb.f{background:var(--f)} .lb.c{background:var(--c)}
.stage.hf .bx.c,.stage.hc .bx.f,.stage.hn .bx{display:none}
.bt{border-collapse:collapse;margin:10px 0 0;font:12px/1.4 ui-monospace,Menlo,Consolas,monospace}
.bt th,.bt td{border:1px solid var(--line);padding:2px 8px;text-align:left}
.bt th{background:#f5f3f0;font-weight:600} .bt tr.f td:first-child{color:var(--f)} .bt tr.c td:first-child{color:var(--c)}
.verdict{margin-top:10px;padding:10px;background:#f7f6f3;border-radius:4px}
.verdict label{margin:0 14px 0 6px} .why{width:48%;font:inherit;padding:4px 7px;border:1px solid var(--line);border-radius:3px}
footer{padding:16px 24px;border-top:1px solid var(--line);background:#fff}
#out{width:100%;height:150px;font:12px ui-monospace,Menlo,Consolas,monospace;margin-top:8px;display:none}
"""

JS = """
function lay(b,m){var g=b.closest('.grp'),s=g.querySelector('.stage');
 s.className='stage'+(m==='f'?' hf':m==='c'?' hc':m==='none'?' hn':'');
 g.querySelectorAll('.ctl button').forEach(function(x){x.classList.remove('on')});b.classList.add('on');}
function collect(){var o=[];document.querySelectorAll('.grp').forEach(function(g){
 var r=g.querySelector('input[type=radio]:checked');
 o.push({page:+g.dataset.page,group:+g.dataset.grp,verdict:r?r.value:null,
         reason:g.querySelector('.why').value||null});});
 var t=document.getElementById('out');t.style.display='block';
 t.value=JSON.stringify({adjudication:'note_box_truth FINAL vs corrected',date:'2026-09-20',verdicts:o},null,1);
 t.select();}
"""


def main(out=None):
    Fm, Cm = load(FINAL), load(CORR)
    split = json.loads(SPLIT.read_text(encoding="utf-8"))
    sealed = set(split["sealed"])
    pages = sorted(p for p in Fm if p in Cm
                   and [n["strip_box"] for n in Fm[p]["notes"]] != [n["strip_box"] for n in Cm[p]["notes"]])
    if sealed & set(pages):
        raise SystemExit(f"refusing: sealed pages in diff set {sorted(sealed & set(pages))}")

    cards, ngrp = [], 0
    for p in pages:
        strip, _ = ps.presplit(str(IMG / f"page{p}_image1.png"), upscale=1)
        if list(strip.size) != list(Fm[p]["strip_size"]):
            raise SystemExit(f"p{p}: strip {list(strip.size)} != ratified {Fm[p]['strip_size']}")
        ngrp += len(groups([n["strip_box"] for n in Fm[p]["notes"]], [n["strip_box"] for n in Cm[p]["notes"]]))
        cards.append(card(p, Fm[p], Cm[p], strip))
        print(f"  p{p}: rendered ({len(Fm[p]['notes'])} vs {len(Cm[p]['notes'])} boxes)")

    doc = f"""<!doctype html><meta charset="utf-8"><title>Ratified truth: FINAL vs corrected</title>
<style>{CSS}</style>
<header>
<h1>Ratified note boxes \u2014 FINAL vs corrected</h1>
<p class="lede" dir="auto">Two human-ratified truth files, 33 pages each, identical on 31 of them. They
disagree on <b>p{ ' and p'.join(str(p) for p in pages) }</b> \u2014 {ngrp} disagreements in all. Every geometry
number reported on this project was scored against <b>FINAL</b>. Crops are native 1:1, no resampling;
<span style="color:var(--f)">solid red = FINAL</span>,
<span style="color:var(--c)">dashed blue = corrected</span>. Verdict is keep / take / neither \u2014 the older
file is not on trial and the newer one is not presumed better. <b>neither</b> is a real answer.</p>
</header>
<main>{''.join(cards)}</main>
<footer><button onclick="collect()" style="font:inherit;padding:6px 14px">copy verdicts as JSON</button>
<textarea id="out" dir="auto"></textarea></footer>
<script>{JS}</script>"""

    path = Path(out or (D / "consoles" / "truth_diff_FINAL_vs_corrected_20260920.html"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc, encoding="utf-8")
    print(f"\n{len(pages)} pages, {ngrp} disagreement groups -> {path}")
    return 0


if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
