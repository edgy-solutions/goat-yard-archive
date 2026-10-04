# -*- coding: utf-8 -*-
"""Five recipe pairs, chosen by a stated rule, for a global decision on the band-clip.

    python recipe_five_sheet.py

Chris, 2026-10-04: "Chris will check five recipe pairs and approve band-clip globally if all five hold."

THE SELECTION RULE, STATED BEFORE THE PICTURES. 20 of the 76 spans resolve a different number of word
runs under the two recipes; that is where the recipe question bites. Five of twenty can only license the
other fifteen if they are the five the rule acts on hardest, so:

  * the FOUR LARGEST TRIMS (rows removed, top + bottom), including the only span where the rule removed
    four separate foreign runs;
  * plus the SMALLEST trim that still changes the run count.

The four worst cases test over-trimming -- is the rule cutting into the span? The minimal case tests the
opposite -- is it cutting at all when it barely needs to? Nothing was chosen for looking persuasive, and
the ranking is in the artifact so the choice can be checked rather than taken.

WHAT YOU ARE BEING ASKED. Not "is this the right reading" -- the candidate is withheld here as everywhere
in this lane. Only: **does the clip keep every row of the span's own line and drop only rows belonging to
something else.** Three views per span: the PAD=12 parent with the removed rows tinted, the parent plain,
and the clip. All at native size and at 4x nearest-neighbour, which invents no strokes.

WHAT THE RULE IS. Remove an ink run only if it (a) does not overlap the span's line band and (b) is either
>= MIN_BAND_PX thick (a line of type) or touches the crop edge (a neighbour truncated by the pad).
Whitespace is never removed; the span's own band cannot be; nothing reads the box edge. It was validated
against the one clip a human has approved (p912:n2, rows 14-72, 2 word runs: this rule keeps 14-78 and
resolves the same 2 runs) and `line_band()` was REJECTED as the trim because it amputated a word.

FILE pages throughout (printed = file - 88).
"""
import base64
import hashlib
import html
import io
import json
import os
import re
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from PIL import Image                                                      # noqa: E402
import hebrew_glyph_card as G                                              # noqa: E402
import hebrew_aperture_diag as HAD                                        # noqa: E402
from clean_run import git_state, provisional, banner                      # noqa: E402

SET, SET_N = "13e053b86b75a195", 76
CUT = HAD.DATA / ("truthset%d_cut_%s.json" % (SET_N, SET))
PRINTED_OFFSET = 88
N_WORST, N_MILD = 4, 1

READABLE = re.compile(u"[֐-׿יִ-ﭏͰ-Ͽἀ-῿]")
_PROBE = u"אב"
FORBIDDEN_KEYS = ("hebrew", "words", "nikud", "letters", "chars", "truth", "signature")

GIT_START = git_state(_HERE)

cut = json.load(io.open(str(CUT), encoding="utf-8"))
assert cut.get("provisional") is False, "the cut artifact is PROVISIONAL -- not a decision surface"
assert cut["set_sha16"] == SET and cut["n"] == SET_N, "this is not the re-frozen set"
# EVERY CLIP IS A PAIR. This used to show only clips whose resolved run count MOVED, which selects the
# population by the very proxy that cannot see the failure: p381:n1 kept 17px of a crop whose thickest
# line was 30px and its run count did not change, so it would never have been offered for an eye. The
# ranking is by how much the clip cuts, which is a statement about the trim and not about the reading.
pairs = [r for r in cut["rows"] if r.get("clip")]
assert len(pairs) == cut["clip"]["written"], "the pair list disagrees with the artifact's clip count"


def trim(r):
    return r["clip"]["trim_top"] + r["clip"]["trim_bot"]


ranked = sorted(pairs, key=lambda r: (-trim(r), r["span_id"]))
chosen = ranked[:N_WORST] + ranked[-N_MILD:]
assert len(chosen) == len({r["span_id"] for r in chosen}) == N_WORST + N_MILD, \
    "the worst and mildest selections overlap -- with %d pairs five cannot be chosen this way" % len(pairs)
assert trim(chosen[0]) == max(trim(r) for r in pairs) and trim(chosen[-1]) == min(trim(r) for r in pairs), \
    "the selection is not the extremes of the ranking it claims to be"


def _uri_im(im):
    b = io.BytesIO()
    im.save(b, format="PNG")
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode("ascii")


def tinted(path, removed, kept):
    """The parent with the REMOVED rows tinted red and the kept range left exactly as it is."""
    im = Image.open(str(path)).convert("RGB")
    px = im.load()
    for y0, y1, _why in removed:
        for y in range(max(0, y0), min(im.height, y1 + 1)):
            for x in range(im.width):
                r, g, b = px[x, y]
                px[x, y] = (min(255, r // 2 + 128), g // 2, b // 2)
    return im


CSS = ("body{background:#111;color:#ddd;font:13px/1.5 ui-monospace,Consolas,monospace;margin:26px}"
       "h1{font-size:19px;margin:0 0 4px}h2{font-size:15px;margin:26px 0 6px;color:#9cf}"
       ".sub{color:#999}.note{border:1px solid #444;background:#191919;padding:10px 12px;margin:14px 0}"
       ".row{border-top:1px solid #333;padding:16px 0;display:grid;grid-template-columns:270px 1fr;gap:18px}"
       "figure{margin:0 0 14px}figcaption{color:#9a9a9a;font-size:12px;margin-top:3px}"
       "img{image-rendering:pixelated;background:#fff;display:block;margin-bottom:5px}"
       "table{border-collapse:collapse;margin:10px 0}td,th{border:1px solid #444;padding:3px 9px;"
       "text-align:left}code{color:#cfc}")

H = ['<!doctype html><meta charset="utf-8"><title>band-clip: five pairs for a global call</title>',
     "<style>%s</style>" % CSS,
     "<h1>Band-clip &mdash; five recipe pairs, for a global approval</h1>",
     '<div class="sub">Set <code>%s</code> (%d spans). FILE pages; printed = file &minus; %d. '
     'Crops cut at laneB <code>%s</code> over a clean tree. Nothing has been sent.</div>'
     % (SET, SET_N, PRINTED_OFFSET, cut["git_end"]["git_head"]),
     '<div class="note"><b>The question.</b> Does the clip keep every row of the span&rsquo;s own line and '
     'drop only rows belonging to something else? That is all. The extracted reading is withheld here as '
     'everywhere in this lane, so this is a geometry call, not a reading call.<br>'
     '<b>Why these five.</b> 20 of %d spans resolve a different number of word runs under the two '
     'recipes. These are the <b>four largest trims</b> &mdash; where the rule removed the most, including '
     'the one span where it removed four separate foreign runs &mdash; <b>plus the smallest trim that '
     'still changes the count</b>. The heavy cases test whether the rule cuts into the span; the light one '
     'tests whether it cuts when it barely needs to. If all five hold, the fifteen in between are '
     'bounded by them.<br>'
     '<b>The rule.</b> Remove an ink run only if it does not overlap the span&rsquo;s line band AND is '
     'either &ge; %d px thick (a line of type) or touches the crop edge (a neighbour truncated by the '
     'pad). Whitespace is never removed; the span&rsquo;s own band cannot be.</div>'
     % (len(pairs), G.MIN_BAND_PX)]

H.append('<table><tr><th>span</th><th>rows removed</th><th>of</th><th>runs: PAD=12 &rarr; clip</th>'
         '<th>why chosen</th></tr>')
for i, r in enumerate(chosen):
    H.append("<tr><td><code>%s</code></td><td>%d (%d top, %d bottom)</td><td>%d</td><td>%d &rarr; %d</td>"
             "<td>%s</td></tr>"
             % (html.escape(r["span_id"]), trim(r), r["clip"]["trim_top"], r["clip"]["trim_bot"],
                r["clip"]["of"], len(r["crop"]["word_runs"]), len(r["clip"]["word_runs"]),
                ("largest trim #%d of %d pairs" % (i + 1, len(pairs))) if i < N_WORST
                else "smallest trim that changes the count"))
H.append("</table>")

shown = {}
for r in chosen:
    sid, c = r["span_id"], r["clip"]
    pim = Image.open(str(r["crop"]["path"])).convert("L")
    cim = Image.open(str(c["path"])).convert("L")
    tim = tinted(r["crop"]["path"], c["removed_runs"], c["rows"])
    shown[sid] = {"A2_spanbox": r["crop"]["sha16"], "A2_bandclip": c["sha16"]}
    H.append('<div class="row"><div>')
    H.append("<b>%s</b><br><span class=sub>file p%d &nbsp;&middot;&nbsp; printed p%d &nbsp;&middot;&nbsp; "
             "note %d</span><br><span class=sub>crop %d&times;%d &nbsp; keep rows %d&ndash;%d of %d"
             "<br>line band %s px<br>removed runs %s<br>runs %d &rarr; %d</span><br>"
             "<code>%s</code><br><code>%s</code>"
             % (html.escape(sid), r["page"], r["page"] - PRINTED_OFFSET, r["note_index"],
                pim.width, pim.height, c["rows"][0], c["rows"][1], c["of"], c["line_band"],
                c["removed_runs"], len(r["crop"]["word_runs"]), len(c["word_runs"]),
                r["crop"]["sha16"], c["sha16"]))
    H.append("</div><div>")
    for im, cap in ((tim, "PAD=12 parent, <b>removed rows tinted</b> &mdash; the tint is the only thing "
                          "added; every untinted row is in the clip"),
                    (pim, "PAD=12 parent, plain"),
                    (cim, "band-clip, rows %d&ndash;%d" % (c["rows"][0], c["rows"][1]))):
        u = _uri_im(im)
        H.append('<figure><img src="%s" width="%d" height="%d">'
                 '<img src="%s" width="%d" height="%d"><figcaption>%s &mdash; native %d&times;%d, then '
                 '4&times; nearest</figcaption></figure>'
                 % (u, im.width, im.height, u, im.width * 4, im.height * 4, cap, im.width, im.height))
    H.append("</div></div>")

H.append('<h2>What approving this does and does not settle</h2>'
         '<div class="sub"><b>Does:</b> licenses the band-clip as the recipe for all %d spans whose two '
         'cuts differ, and for the %d where they are the same pixels anyway.<br>'
         '<b>Does not:</b> say anything about whether a BOX is right. The clip only removes rows that '
         'belong to another line &mdash; a box sitting one line above its span produces a clip that is '
         'perfectly clean and perfectly wrong, and %d of the %d crops in this set still resolve more word '
         'runs than the extractor claims words. Those are a redraw question.<br>'
         '<b>Also does not:</b> re-open a sealed page or move the alignment gate. Nothing here was '
         'rescored.</div>'
         % (len(pairs), cut["clip"]["no_trim"], len(cut["geometry_flags"]["runs_exceed_words"]), SET_N))
doc = "\n".join(H)

assert READABLE.search(_PROBE), "the withholding pattern cannot match Hebrew at all"
hit = READABLE.search(doc)
assert not hit, "readable Hebrew/Greek in the sheet at offset %d" % (hit.start() if hit else -1)
low = doc.lower()
for k in FORBIDDEN_KEYS:
    assert ('"%s"' % k) not in low and (">%s<" % k) not in low, "a candidate-derived field (%r) is named" % k
assert "A1_notebox" not in doc and "notebox" not in low, "an A1 note-box crop is referenced"
assert doc.count('<div class="row">') == N_WORST + N_MILD, "the sheet does not render five rows"

sig = ";".join("%s:%s:%s" % (s, shown[s]["A2_spanbox"], shown[s]["A2_bandclip"]) for s in sorted(shown))
DIG = hashlib.sha256(sig.encode("utf-8")).hexdigest()[:8]
OUT = HAD.DATA / ("recipe_five_%s_%s.html" % (SET, DIG))
SIDE = OUT.with_suffix(".json")
if SIDE.exists():
    was = (json.loads(io.open(str(SIDE), encoding="utf-8").read()) or {}).get("crop_sha16") or {}
    assert not was or was == shown, \
        "%s already records a look at DIFFERENT pixels. Overwriting it would destroy the record of what " \
        "was approved -- how the 19-span approval was lost on 2026-10-04." % SIDE.name

io.open(str(OUT), "w", encoding="utf-8").write(doc)
GIT_END = git_state(_HERE)
json.dump({"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "git_start": GIT_START, "git_end": GIT_END,
           "provisional": provisional(GIT_START, GIT_END),
           "set_sha16": SET, "source": CUT.name, "n_pairs_total": len(pairs),
           "asks": "approve the band-clip globally, or name which of the five fails and how",
           "selection_rule": "the %d largest trims (rows removed, top+bottom) plus the %d smallest trim "
                             "that still changes the resolved run count" % (N_WORST, N_MILD),
           "ranking": [{"span_id": r["span_id"], "trim_px": trim(r), "of": r["clip"]["of"],
                        "runs_base": len(r["crop"]["word_runs"]), "runs_clip": len(r["clip"]["word_runs"]),
                        "chosen": r["span_id"] in shown} for r in ranked],
           "page_numbering": "FILE pages (printed = file - %d)" % PRINTED_OFFSET,
           "withheld": ["the extracted Hebrew", "the extractor's word count", "its pointing flag"],
           "sheet_sha16": hashlib.sha256(doc.encode("utf-8")).hexdigest()[:16],
           "crop_sha16": shown},
          io.open(str(SIDE), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print("sheet %s   (%d pairs ranked, %d shown)" % (OUT.name, len(pairs), len(shown)))
for r in chosen:
    print("  %-11s trim %3d of %3d   runs %d -> %d"
          % (r["span_id"], trim(r), r["clip"]["of"], len(r["crop"]["word_runs"]),
             len(r["clip"]["word_runs"])))
print("  sidecar %s" % SIDE.name)
print(banner(GIT_START, GIT_END))
