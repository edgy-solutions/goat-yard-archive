# -*- coding: utf-8 -*-
"""The redraw queue: three boxes, one page, for a point-and-name sitting.

WHAT THIS IS NOT. Not the contact sheet. Nothing on this page is approved for sending and nothing on
it is a spend. The contact sheet asks "may I pay for these pixels"; this page asks "is this box drawn
round the right thing", which is a ratification question and Chris's alone.

WHY THE TEXT IS ON THIS PAGE. On the contact sheet the signed text sits beside the crop as provenance
and Chris's rule is to approve on the pixels and not on the text. Here the text is the question: the
check is whether the box contains the span that was signed, so the two have to be looked at together.
That is the difference between the two pages and it is the reason they are two pages.

THE THREE ITEMS, and each is a different kind of box fault:
  p912:n2  span box, possibly short -- 200px for 11 consonants where the corpus median predicts ~360
  p217:n2  note box, ratified left edge at -2, i.e. outside the page. The CROP is repaired by a clamp;
           the BOX is not, and a clamp is not a ratification.
  p362:n1  span box, one MERGED band of 67px starting at row 0 -- two text lines touching, so a read
           off this crop cannot be attributed to a line.

ALL THREE SPANS ARE SEALED. That matters for what a redraw costs: a sealed read speaks for the pixels
it was shown, so redrawing the box does not make the old read wrong -- it makes it a statement about a
crop we no longer use, and the span then needs a rerun to have a read at all. That rerun is a new
spend and Chris's call. Nothing here reruns anything.

No crop on this page leaves the network. The note-box crops in particular are here for local looking
only; `hebrew_frontier_or.cells()` cannot reach an A1 crop by construction.
"""
from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hebrew_aperture_diag as diag                                         # noqa: E402
import hebrew_glyph_card as G                                               # noqa: E402

OUT = diag.CROPDIR.parent / "box_queue_20260927.html"
PRINTED_OFFSET = 88

# The queue, in the order Chris named it. `ask` is the decision he is being asked for, in his words
# where he gave them; `facts` are measured, and anything derived says so in its own line.
QUEUE = [
    dict(span_id="p912:n2", aperture="A2_spanbox",
         why="span box may hold one of the two signed words",
         ask="If it shows the whole span on one line, the box is done. If it holds only one word, "
             "it is a redraw and the span is rerun after."),
    dict(span_id="p217:n2", aperture="A1_notebox",
         why="ratified note box starts at x=-2, two pixels outside the page",
         ask="Name a left edge at or inside 0. The crop already looks right because the cutter "
             "clamps to 0 before cropping; the ratified box is still -2."),
    dict(span_id="p362:n1", aperture="A2_spanbox",
         why="one merged 67px band starting at row 0: two lines touching",
         ask="Tighten to the single band that holds the signed span, or say the crop is fine and the "
             "band test is what needs changing."),
]


def _b64(p):
    p = Path(p)
    return None if not p.exists() else \
        "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode("ascii")


def _bands(pg):
    """Native column bands for a page -- the same source `band_overshoot` uses, so the geometry on
    this page and the geometry in the gate cannot drift apart."""
    import cv_footnote_presplit as _ps
    return _ps.presplit(str(diag.IMG / f"page{pg}_image1.png"), upscale=1)[1]["bands"]


def _man():
    f = diag.CROPDIR / "manifest.json"
    return {m["span_id"]: m for m in json.load(io.open(f, encoding="utf-8"))}


def px_per_consonant():
    """Derived, and DERIVED IS THE WORD: crop width per consonant over every one-band A2 crop.

    This is a proxy, not a reading. It cannot see a box that is short at one end and long at the
    other, and it assumes a fount width that varies between founts on the same page. It is here
    because it puts a number on "this box looks narrow" and because it names p912:n2 without having
    been built to name it. The pixels are still the answer."""
    man, out = _man(), {}
    rows = {r["span_id"]: r for r in G.box_quality(True)}
    for s in diag.build_set(include_sealed=True):
        sid = s["span_id"]
        r, m = rows.get(sid), man.get(sid)
        if not r or not m or not r.get("one_band") or not m.get("A2_spanbox"):
            continue
        cons = len([c for c in G.strip_nikud(s["truth"] or "") if "א" <= c <= "ת"])
        if not cons:                       # p900:n4's sentinel signature has no consonants
            continue
        out[sid] = (m["A2_spanbox"]["native_rects"][0][2] - m["A2_spanbox"]["native_rects"][0][0],
                    cons)
    return {k: (w, c, round(w / c, 1)) for k, (w, c) in out.items()}


def _img(uri, w, cap, scale=1):
    if uri is None:
        return "<p class=miss>crop missing on disk</p>"
    return (f"<figure><img src='{uri}' style='width:{int(w * scale)}px'"
            f"{' class=zoom' if scale > 1 else ''}><figcaption>{cap}</figcaption></figure>")


def build():
    man = _man()
    spans = {s["span_id"]: s for s in diag.build_set(include_sealed=True)}
    rows = {r["span_id"]: r for r in G.box_quality(True)}
    ppc = px_per_consonant()
    lo = sorted(ppc.items(), key=lambda kv: kv[1][2])

    P = ["""<!doctype html><meta charset=utf-8><title>Box redraw queue</title><style>
body{font:15px/1.55 Georgia,serif;max-width:1100px;margin:2em auto;padding:0 16px;color:#1a1a1a}
h1{font-size:1.5em;margin-bottom:.2em} h2{margin-top:2.2em;border-top:2px solid #333;padding-top:.6em}
figure{margin:.8em 0} img{border:1px solid #999;background:#fff;image-rendering:pixelated}
figcaption{font:12px/1.4 monospace;color:#555;margin-top:.3em}
table{border-collapse:collapse;margin:.8em 0;font-size:.92em}
th,td{border:1px solid #ccc;padding:.32em .6em;text-align:left;vertical-align:top}
th{background:#f2f2f2;white-space:nowrap}
.heb{font-size:1.9em;direction:rtl;unicode-bidi:bidi-override;font-family:"Times New Roman",serif}
.ask{background:#fffbe6;border-left:4px solid #d4a017;padding:.7em 1em;margin:1em 0}
.note{background:#f5f5f5;border-left:4px solid #888;padding:.6em 1em;font-size:.93em}
.miss{color:#a00;font-weight:bold} code{font-size:.9em} .d{color:#666;font-size:.9em}
</style>
<h1>Box redraw queue &mdash; three boxes, point and name</h1>
<p><b>All page numbers are FILE pages; printed page = file &minus; 88.</b></p>
<div class=note><b>This is not the contact sheet and nothing here is a spend.</b> The contact sheet
asks whether the pixels may be paid for. This page asks whether each box is drawn round the right
thing, which is a ratification question. The signed text is shown beside each crop <i>because that is
the question here</i> &mdash; whether the box contains what was signed &mdash; which is the opposite of
the rule on the approval sheet.<br><br>
<b>All three spans are SEALED.</b> A sealed read speaks for the pixels it was shown, so a redraw does
not make the old read wrong; it makes it a statement about a crop we stop using, and the span then has
no read for the new pixels. Rerunning it is a new spend and your call. Nothing here reruns anything,
and no crop on this page leaves the network.</div>"""]

    for i, q in enumerate(QUEUE, 1):
        sid, ap = q["span_id"], q["aperture"]
        s, m, r = spans[sid], man.get(sid, {}), rows.get(sid, {})
        rec = m.get(ap) or {}
        other = "A1_notebox" if ap == "A2_spanbox" else "A2_spanbox"
        orec = m.get(other) or {}
        page = s["page"]
        P.append(f"<h2>{i}. {sid} &mdash; file page {page}, printed {page - PRINTED_OFFSET} "
                 f"&mdash; {q['why']}</h2>")
        P.append(f"<p>Signed span, {ap.replace('_', ' ')}: <span class=heb>{s['truth']}</span></p>")

        if rec:
            box = rec["native_rects"][0] if rec.get("native_rects") else None
            sha = diag.crop_sha(sid, ap)
            ratified = s.get("span_box") if ap == "A2_spanbox" else s.get("note_box")
            native_bands = [b["native"] + list(b["size"]) for b in _bands(page)]
            geom = ""
            if s.get("span_box"):
                _im = G.cut(page, s["span_box"], diag.PAD, s["column_bands"])[0]
                geom = G.band_geometry(_im)
            P.append(_img(_b64(rec["path"]), rec["size"][0],
                          f"{ap} at 1x &mdash; {rec['size'][0]}x{rec['size'][1]} px, "
                          f"sha {(sha or '')[:16]}"))
            P.append(_img(_b64(rec["path"]), rec["size"][0],
                          f"{ap} at 4x (nearest neighbour; no pixel invented)", 4))
            P.append("<table>")
            P.append(f"<tr><th>crop</th><td>{rec['size'][0]}&times;{rec['size'][1]} px native</td></tr>")
            if box:
                P.append(f"<tr><th>mapped rect</th><td><code>{box}</code> &mdash; "
                         f"{box[2] - box[0]}&times;{box[3] - box[1]} px</td></tr>")
            P.append(f"<tr><th>ratified box</th><td><code>{ratified}</code> &mdash; the box this "
                     f"sitting is about, in its own coordinate space</td></tr>")
            P.append(f"<tr><th>native bands</th><td><code>{native_bands}</code> &mdash; "
                     f"[x, y, w, h]; bands sit side by side</td></tr>")
            P.append(f"<tr><th>cut / fault</th><td>edges <code>{rec.get('rect_edges')}</code>, "
                     f"overshoot <code>{rec.get('band_overshoot_px')}</code>, "
                     f"fault <code>{rec.get('fault')}</code></td></tr>")
            if geom:
                P.append(f"<tr><th>band test</th><td>one_band <code>{r.get('one_band')}</code>, "
                         f"ink runs <code>{r.get('lines')}</code>, "
                         f"<code>{geom}</code></td></tr>")
            P.append("</table>")
        else:
            P.append("<p class=miss>no crop record for this aperture</p>")

        # The px/consonant proxy is a statement about the SPAN box width. In a note-box section it
        # would be a number about a different box than the one being judged, which is exactly the kind
        # of near-miss that gets cited as if it were on topic. So it prints only where it applies.
        if sid in ppc and ap == "A2_spanbox":
            w, c, v = ppc[sid]
            rank = [k for k, _ in lo].index(sid) + 1
            P.append(f"<p class=d><b>Derived, not read:</b> {w}px of span box for {c} consonants = "
                     f"<b>{v} px/consonant</b>, rank {rank} of {len(lo)} one-band crops "
                     f"(lowest = narrowest). Corpus median "
                     f"{sorted(v3 for _, (_, _, v3) in lo)[len(lo) // 2]}; at the median this span "
                     f"would be about {int(sorted(v3 for _, (_, _, v3) in lo)[len(lo) // 2] * c)}px "
                     f"wide. A proxy, not a reading &mdash; the pixels above are the answer.</p>")

        if orec:
            P.append(f"<p class=d>Context, {other.replace('_', ' ')} at 1x &mdash; local looking only, "
                     f"never sent:</p>")
            P.append(_img(_b64(orec["path"]), orec["size"][0],
                          f"{other} &mdash; {orec['size'][0]}x{orec['size'][1]} px, "
                          f"edges {orec.get('rect_edges')}"))

        P.append(f"<div class=ask><b>The decision:</b> {q['ask']}</div>")

    P.append(f"<h2>px per consonant, every one-band A2 crop</h2><table>"
             f"<tr><th>span</th><th>box px</th><th>consonants</th><th>px/consonant</th></tr>"
             + "".join(f"<tr><td>{k}</td><td>{w}</td><td>{c}</td><td>{v}</td></tr>"
                       for k, (w, c, v) in lo) + "</table>"
             "<p class=d>Derived from the mapped rect width and the signed consonant count. It cannot "
             "see a box short at one end and long at the other, and fount width varies within a page, "
             "so it is a way of noticing a narrow box and not a way of judging one.</p>")

    io.open(OUT, "w", encoding="utf-8", newline="\n").write("\n".join(x for x in P if x))
    return OUT


if __name__ == "__main__":
    p = build()
    print("wrote", p)
    for k, (w, c, v) in sorted(px_per_consonant().items(), key=lambda kv: kv[1][2])[:4]:
        print("  narrowest %-9s %4dpx / %2d consonants = %5.1f px/consonant" % (k, w, c, v))
