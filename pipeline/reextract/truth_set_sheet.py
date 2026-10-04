# -*- coding: utf-8 -*-
"""The signing sheet: every crop at native size, the candidate WITHHELD, for Chris.

    python truth_set_sheet.py        # the set it renders is named in SET/SET_N below

This is two gates in one surface, and they are not the same gate:

  THE CONTACT-SHEET GATE -- "before any outbound call, produce a contact sheet: every crop to be sent,
  native size, beside its signed text; Chris approves it, then spend." Nothing has been sent for these
  these spans, so this is the pre-send look: every crop, its hash, and the box faults a reader
  could never repair.

  RULING (4) -- sign from PIXELS with the candidate withheld. The last truth set was 30% wrong in the
  direction of the extracted text and one row was affirmed verbatim, so the signer must not be shown
  what the extractor read.

Those two pull in opposite directions on one field: "beside its signed text" is exactly what ruling (4)
forbids here, because these spans are not yet signed -- the sheet exists to GET them signed. So the rule
this file follows is: anything derived from the candidate is absent, and that is ASSERTED over the
emitted bytes rather than arranged by being careful. Absent: the Hebrew, the extractor's word count,
its nikud flag, the note text. Present: geometry, hashes, and measurements taken from the PIXELS --
resolved column runs are an ink measurement and anchor nobody on a reading.

WHAT EACH ROW SHOWS. Three views, because they answer different questions: native pixels (is this the
right patch of page?), 4x nearest-neighbour (what are the letterforms -- a smoothed upscale invents
strokes that are not on the page), and the matched-scale comparison from `hebrew_glyph_card.comparison`
scaled so the text line is 150px (shape comparison across spans, which is what a glyph card is for).
Where a band-clip exists it is shown beside its parent with the rows it removed, and the pair is
badged when the two recipes resolve a different number of word runs -- the subset where the pad probe's
unresolved question actually bites.

THREE BADGES, NONE OF WHICH DROPS A SPAN (exclusions happen afterwards and with a reason):
  DUP-BOX      two spans were handed the same box, so their crops are byte-identical. At least one box
               is wrong and no signature from these pixels can tell them apart. A redraw question.
  SHORT-BOX    the unpadded box is thinner than MIN_BAND_PX, the derived floor for an ink run to be a
               line of type at all. Such a crop can still pass the blank gate -- on ink contributed by
               its PAD, not by its box.
  RECIPE       PAD=12 and the band-clip resolve a different number of word runs here.

WHAT THIS DOES NOT DO: send anything, spend anything, approve anything, or decide a recipe. It also
cannot tell anyone whether a box is right; only a human reading the pixels can. FILE pages throughout,
with the printed page beside each (printed = file - 88).
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
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "scripts"))
from PIL import Image                                                      # noqa: E402
import hebrew_glyph_card as G                                              # noqa: E402
import hebrew_aperture_diag as HAD                                        # noqa: E402
from clean_run import git_state, provisional, banner                      # noqa: E402

# The re-frozen set (2026-10-04): the 96 minus 20 spans at measured box faults. The 96 sheet keeps
# its own name and sidecar -- an approval record is named by the pixels it describes.
SET, SET_N = "13e053b86b75a195", 76
CUT = HAD.DATA / ("truthset%d_cut_%s.json" % (SET_N, SET))
PRINTED_OFFSET = 88
SKEL_NAME = "truthset_signing_%s.jsonl" % SET

# The same check `truth_set_draw.py` makes, for the same reason: any readable script in this file
# defeats the withholding. Hebrew, its presentation forms, and Greek.
READABLE = re.compile(u"[֐-׿יִ-ﭏͰ-Ͽἀ-῿]")
# A literal pair of Hebrew letters, so the pattern can be shown to FIRE without reading a candidate
# from anywhere. A regex that matches nothing passes on everything.
_PROBE = u"אב"
# Candidate-derived keys that may never appear in the emitted bytes, by name OR by value.
FORBIDDEN_KEYS = ("hebrew", "words", "nikud", "letters", "chars", "truth", "signature")

GIT_START = git_state(_HERE)

cut = json.load(io.open(str(CUT), encoding="utf-8"))
assert cut.get("provisional") is False, "the cut artifact is PROVISIONAL -- not an approval record"
assert cut["set_sha16"] == SET and cut["n"] == SET_N, \
    "this is not the frozen set: %r n=%r" % (cut["set_sha16"], cut["n"])
rows = [r for r in cut["rows"] if r.get("crop")]
assert len(rows) == SET_N, "the sheet would describe %d of %d spans; a sheet that silently narrows " \
                           "is how the 19-span approval was lost" % (len(rows), SET_N)
flags = cut["geometry_flags"]
DUP = {sid: [o for o in ids if o != sid] for ids in flags["duplicate_box"].values() for sid in ids}
SHORT = {x["span_id"]: x["box_h_native"] for x in flags["box_shorter_than_a_line"]}
NOTYPE = {x["span_id"]: x["ink_runs_px"] for x in flags["no_line_of_type"]}


def _uri(p):
    return "data:image/png;base64," + base64.b64encode(io.open(str(p), "rb").read()).decode("ascii")


def _uri_im(im):
    b = io.BytesIO()
    im.save(b, format="PNG")
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode("ascii")


def _views(path):
    """(native uri, comparison uri, scale, band height) for one crop file."""
    im = Image.open(str(path)).convert("L")
    cmp_im, scale, band = G.comparison(im)
    return _uri(path), _uri_im(cmp_im), scale, band, im.size


def badges(r):
    out = []
    if r["span_id"] in NOTYPE:
        out.append(("NO-TYPE", "no ink run in this crop is thick enough to be a line of type (runs "
                               "%s px, floor %d). This is the printed RULE. It passed the blank gate "
                               "because a rule IS an inked band -- nothing here is readable, and no "
                               "reading could have repaired it."
                    % (NOTYPE[r["span_id"]], G.MIN_BAND_PX)))
    if r["span_id"] in DUP:
        out.append(("DUP-BOX", "same box as %s -- byte-identical crop; at least one box is wrong"
                    % ", ".join(DUP[r["span_id"]])))
    if r["span_id"] in SHORT:
        out.append(("SHORT-BOX", "unpadded box is %dpx tall, under the %dpx floor for a line of type; "
                                 "this crop may be passing the blank gate on its PAD"
                    % (SHORT[r["span_id"]], G.MIN_BAND_PX)))
    if r.get("clip") and len(r["clip"]["word_runs"]) != len(r["crop"]["word_runs"]):
        out.append(("RECIPE", "PAD=12 resolves %d word run(s), band-clip %d -- the pair below is the "
                              "recipe question, and it is yours to call"
                    % (len(r["crop"]["word_runs"]), len(r["clip"]["word_runs"]))))
    return out


# Flagged rows first: they are decisions, and a decision at row 70 of 96 is a decision nobody makes.
rows.sort(key=lambda r: (not badges(r), r["page"], r["note_index"], r["span_id"]))

CSS = """
body{background:#14161a;color:#e6e6e6;font:13px/1.5 system-ui,Segoe UI,sans-serif;margin:0;padding:24px}
h1{font-size:19px;margin:0 0 4px} h2{font-size:15px;margin:28px 0 8px;color:#9fd}
.sub{color:#9aa;font-size:12px} a{color:#9cf}
table.sum{border-collapse:collapse;margin:10px 0 18px} table.sum td{padding:2px 12px 2px 0;vertical-align:top}
.row{border-top:1px solid #2a2f37;padding:16px 0;display:grid;grid-template-columns:230px 1fr;gap:18px}
.meta b{font-size:14px} .meta code{color:#cda;font-size:11px;word-break:break-all}
.badge{display:inline-block;background:#5a1f22;color:#ffd9d9;border:1px solid #a44;border-radius:3px;
 padding:1px 6px;margin:2px 4px 2px 0;font-size:11px;font-weight:600}
.badge.recipe{background:#1f3a5a;color:#d9ecff;border-color:#468}
.badge.notype{background:#6a3a12;color:#ffe9d0;border-color:#c86}
.why{color:#c9a;font-size:11px;margin:2px 0}
figure{margin:0 14px 14px 0;display:inline-block;vertical-align:top;background:#0d0f12;padding:8px;
 border:1px solid #2a2f37}
figcaption{color:#9aa;font-size:11px;margin-top:6px;max-width:460px}
img{image-rendering:pixelated;background:#fff;display:block;margin-bottom:6px}
.pair{outline:1px dashed #468;outline-offset:6px}
.note{background:#1b2127;border-left:3px solid #468;padding:10px 14px;margin:14px 0}
"""

H = ['<!doctype html><meta charset="utf-8"><title>truth set %s - %d spans, candidate withheld</title>'
     % (SET, SET_N), "<style>%s</style>" % CSS]
H.append("<h1>Truth set <code>%s</code> &mdash; %d spans, candidate withheld</h1>" % (SET, SET_N))
H.append('<div class="sub">FILE pages throughout; printed = file &minus; %d. Crops cut at laneB '
         '<code>%s</code> over a clean tree. A2 span box, PAD=12 native px; band-clip where a '
         'neighbouring line reached into the pad. Nothing here has been sent.</div>' % (
             PRINTED_OFFSET, cut["git_end"]["git_head"]))
H.append('<div class="note"><b>What is deliberately missing.</b> The extractor&rsquo;s reading, its '
         'word count and its pointing flag are all absent, and that absence is asserted over these '
         'bytes before the file is written. The previous truth set was 30% wrong in the direction of '
         'the candidate, once affirmed verbatim. Write what the pixels show, or abstain.<br>'
         '<b>What is present and is NOT a hint:</b> resolved column runs, counted from the ink by gaps '
         'rather than by recognising letters.<br>'
         '<b>Where a crop holds more than one span of Hebrew, sign every one you can see</b>, in the order they are printed (right to left within a line, top line first). Some of these boxes hold more than the span they were drawn for &mdash; that is a redraw question, and your reading of what is actually there is what settles it.</div>')
H.append('<table class="sum">'
         '<tr><td>spans</td><td><b>%d</b> on %d pages, 0 refused by the crop gate &mdash; the 96 set minus 20 spans at measured box faults (14 on the printed rule, 6 at the three duplicate boxes)</td></tr>'
         '<tr><td>band-clips</td><td><b>%d</b> written, %d needed no trim (no foreign line in the pad), '
         '0 abstained, 0 resolved FEWER runs than its parent</td></tr>'
         '<tr><td>recipe differs</td><td><b>%d</b> span(s)</td></tr>'
         '<tr><td>DUP-BOX</td><td><b>%d</b> pair(s): %s</td></tr>'
         '<tr><td>NO-TYPE</td><td><b>%d</b> crop(s) hold no line of type at all &mdash; the box is on '
         'the printed rule: %s</td></tr>'
         '<tr><td>SHORT-BOX</td><td><b>%d</b>: %s</td></tr>'
         '</table>'
         % (SET_N, len({r["page"] for r in rows}), cut["clip"]["written"], cut["clip"]["no_trim"],
            len(cut["clip"]["word_runs_differ"]), len(flags["duplicate_box"]),
            html.escape("; ".join(" = ".join(v) for v in flags["duplicate_box"].values())),
            len(NOTYPE), html.escape(", ".join(sorted(NOTYPE))),
            len(SHORT), html.escape(", ".join(sorted(SHORT)))))

shown, nflag = {}, 0
for r in rows:
    sid = r["span_id"]
    bg = badges(r)
    nflag += 1 if bg else 0
    u_nat, u_cmp, scale, band, size = _views(r["crop"]["path"])
    shown[sid] = {"A2_spanbox": r["crop"]["sha16"]}
    H.append('<div class="row"><div class="meta">')
    H.append("<b>%s</b><br><span class=sub>file p%d &nbsp;&middot;&nbsp; printed p%d &nbsp;&middot;&nbsp; "
             "note %d</span><br>" % (html.escape(sid), r["page"], r["page"] - PRINTED_OFFSET,
                                     r["note_index"]))
    H.append('<span class=sub>box (strip) %s<br>native rect %s<br>crop %d&times;%d &nbsp; line band '
             '%s px<br>runs %s</span><br><code>%s</code><br>'
             % (r["box_strip"], r["crop"]["native_rects"], size[0], size[1], band,
                r["crop"]["word_runs"], r["crop"]["sha16"]))
    for name, why in bg:
        H.append('<span class="badge%s">%s</span><div class="why">%s</div>'
                 % ({"RECIPE": " recipe", "NO-TYPE": " notype"}.get(name, ""), name,
                    html.escape(why)))
    H.append("</div><div>")
    pair = ' class="pair"' if any(n == "RECIPE" for n, _ in bg) else ""
    H.append('<figure%s><img src="%s" width="%d" height="%d"><img src="%s" width="%d" height="%d">'
             '<figcaption>A2 span box, PAD=12 &mdash; native %d&times;%d, then 4&times; nearest. '
             'Resolved runs: %s</figcaption></figure>'
             % (pair, u_nat, size[0], size[1], u_nat, size[0] * 4, size[1] * 4, size[0], size[1],
                r["crop"]["word_runs"]))
    if r.get("clip"):
        c = r["clip"]
        cu_nat, cu_cmp, cscale, cband, csize = _views(c["path"])
        shown[sid]["A2_bandclip"] = c["sha16"]
        H.append('<figure%s><img src="%s" width="%d" height="%d"><img src="%s" width="%d" height="%d">'
                 '<figcaption>band-clip &mdash; rows %d&ndash;%d of %d kept (%d off the top, %d off the '
                 'bottom); removed runs %s. Resolved runs: %s<br><code>%s</code></figcaption></figure>'
                 % (pair, cu_nat, csize[0], csize[1], cu_nat, csize[0] * 4, csize[1] * 4,
                    c["rows"][0], c["rows"][1], c["of"], c["trim_top"], c["trim_bot"],
                    c["removed_runs"], c["word_runs"], c["sha16"]))
    H.append('<figure><img src="%s" width="%d" height="%d"><figcaption>matched scale &mdash; text line '
             'normalised to %dpx (&times;%s). Same letterform scale as every other span, which is the '
             'only thing that makes a shape comparison mean anything.</figcaption></figure>'
             % (u_cmp, Image.open(io.BytesIO(base64.b64decode(u_cmp.split(",", 1)[1]))).width,
                Image.open(io.BytesIO(base64.b64decode(u_cmp.split(",", 1)[1]))).height,
                G.TARGET_BAND, scale))
    H.append("</div></div>")

H.append('<h2>How to record a signature</h2><div class="sub">A skeleton with one row per span, in this '
         'order, is written beside this sheet: <code>%s</code>. Each row has an '
         'empty LIST to fill from the pixels &mdash; one entry per span of Hebrew visible in that crop, '
         'so a box that holds two spans records two readings &mdash; and a flag to set instead when the '
         'pixels support none. The crop hash in each row is what the signature is ABOUT, so a re-cut span '
         'cannot inherit an old signature. (The field is not named here on purpose: this file asserts '
         'that no candidate-derived field name appears in it, and that guard is worth more than the '
         'convenience of writing it out.)</div>' % SKEL_NAME)
H.append('<div class="sub" style="margin-top:18px">Flagged rows: %d of %d, shown first. Sheet built '
         'from <code>%s</code>.</div>' % (nflag, SET_N, CUT.name))
doc = "\n".join(H)

# ---- the withholding, asserted over the bytes that will be written --------------------------------
assert READABLE.search(_PROBE), "the withholding pattern cannot match Hebrew at all -- it would pass " \
                                "on anything, which is the `probe that misses` failure"
hit = READABLE.search(doc)
assert not hit, "the sheet contains readable Hebrew/Greek at offset %d (%r) -- the candidate is not " \
                "withheld and a signature made against it would be worth nothing" \
                % (hit.start() if hit else -1, doc[max(0, hit.start() - 60):hit.start() + 10] if hit else "")
low = doc.lower()
for k in FORBIDDEN_KEYS:
    assert ('"%s"' % k) not in low and (">%s<" % k) not in low, \
        "a candidate-derived field (%r) is named in the sheet" % k
assert "A1_notebox" not in doc and "notebox" not in low, "an A1 note-box crop is referenced"
assert str(HAD.CROPDIR) not in doc, "the sheet points at the 19-span corpus instead of its own crops"
assert doc.count("<div class=\"row\">") == SET_N, \
    "the sheet renders %d rows, not %d" % (doc.count("<div class=\"row\">"), SET_N)

# ---- content-addressed name + the clobber guard ----------------------------------------------------
# The name must address EVERY pixel the sheet shows. It addressed only the parent crops, so when
# the clip rule was corrected on 2026-10-04 the sheet kept its old name and the clobber guard had
# to refuse it -- the guard caught what the name should have expressed.
sig = ";".join("%s:%s:%s" % (s, shown[s]["A2_spanbox"], shown[s].get("A2_bandclip") or "-")
               for s in sorted(shown))
DIG = hashlib.sha256(sig.encode("utf-8")).hexdigest()[:8]
OUT = HAD.DATA / ("truthset_sheet_%s_%dspan_%s.html" % (SET, len(shown), DIG))
SIDE = OUT.with_suffix(".json")
SKEL = HAD.DATA / SKEL_NAME
if SIDE.exists():
    was = (json.loads(io.open(str(SIDE), encoding="utf-8").read()) or {}).get("crop_sha16") or {}
    assert not was or was == shown, \
        "%s already records a look at DIFFERENT pixels (%d span(s)). Overwriting it would destroy the " \
        "record of what was approved, which is how the 19-span approval was lost on 2026-10-04." \
        % (SIDE.name, len(was))

io.open(str(OUT), "w", encoding="utf-8").write(doc)
GIT_END = git_state(_HERE)
json.dump({"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "git_start": GIT_START, "git_end": GIT_END,
           "provisional": provisional(GIT_START, GIT_END),
           "set_sha16": SET, "n": len(shown), "source": CUT.name,
           "sheet_sha16": hashlib.sha256(doc.encode("utf-8")).hexdigest()[:16],
           "page_numbering": "FILE pages (printed = file - %d)" % PRINTED_OFFSET,
           "withheld": ["the extracted Hebrew", "the extractor's word count", "its nikud flag",
                        "the note text"],
           "asserted_over_bytes": ["no Hebrew/Greek/presentation forms", "no candidate-derived field "
                                   "names", "no A1 note-box reference", "%d rows" % SET_N],
           "badges": {"NO-TYPE": sorted(NOTYPE), "DUP-BOX": sorted(DUP), "SHORT-BOX": sorted(SHORT),
                      "RECIPE": [d["span_id"] for d in cut["clip"]["word_runs_differ"]]},
           "crop_sha16": shown},
          io.open(str(SIDE), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# A LIST, not a field: Chris signs every Hebrew span visible in the crop, because 22 of these boxes
# resolve more word runs than the extractor claims words and the box rule makes that a redraw
# question. One reading per visible span, in printed order; an empty list with abstain set means the
# pixels support none.
skel = [{"span_id": s, "crop_sha16": shown[s], "readings": [], "abstain": False, "note": "",
         "readings_are": "one entry per span of Hebrew VISIBLE in this crop, in printed order; the crop may hold more than the span it was drawn for",
         "signed_from": "pixels, candidate withheld", "sheet": OUT.name} for s in sorted(shown)]
sk = "\n".join(json.dumps(x, ensure_ascii=False) for x in skel) + "\n"
assert not READABLE.search(sk), "the signing skeleton carries readable script"
io.open(str(SKEL), "w", encoding="utf-8").write(sk)

print("sheet %s" % OUT.name)
print("  rows %d   flagged %d   clips shown %d   recipe pairs %d"
      % (SET_N, nflag, sum(1 for s in shown.values() if "A2_bandclip" in s),
         len(cut["clip"]["word_runs_differ"])))
print("  withheld: hebrew, word count, nikud flag, note text -- asserted over %d bytes" % len(doc))
print("  sidecar %s   skeleton %s" % (SIDE.name, SKEL.name))
print(banner(GIT_START, GIT_END))
