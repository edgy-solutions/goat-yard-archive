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

THREE SECTIONS, IN THIS ORDER, EACH WITH A DERIVED COUNT IN ITS HEADING (Chris, 2026-10-04): the
over-full boxes, then the crops where a neighbouring word is sliced by the crop edge, then the clean
rest. A decision at row 70 of 74 is a decision nobody makes, and "flagged first" was not the same thing
as telling the signer which KIND of judgement each row needs. The sections are disjoint -- a span that is
both over-full and edge-sliced appears once, in the first section, and carries both badges, so moving it
cannot hide the second hazard. Every count is derived from the cut and asserted against the rendered
document.

EVERY ROW LINKS OUT TWICE, by path and never by embedding: to the note the box was drawn inside, and to
the native page PNG. "So I can check a truncated-looking word against the page before applying the
edge-cut rule" -- which is a judgement this sheet asks for 18 times and a 123x45 crop cannot support.
The note crop is cut from the SAME note region the localizer placed the box in, at the same PAD, and the
containment is asserted at cut time. These are note pixels: they stay on this machine, the sheet carries
file:// paths to them, and the assertion that none of them is EMBEDDED here is made over the emitted
bytes with its own liveness check (the same detector must find the span crops, which are embedded).

A PER-SPAN FAULT BUTTON, because a drop that the measurements could not make must still be recordable.
23 spans were dropped from the 96 for faults a script could measure; the two found by eye say the script
cannot see script. The button records a FAULT, not a signature or an abstain -- "there is nothing here to
sign" is a different fact from "I decline to sign this" -- and it writes a file beside the skeleton.

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
SET, SET_N = "0401b636ffa7bf1a", 74
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


def _furl(p):
    """A LOCAL PATH, NOT PIXELS. The note crops are note-box pixels and they do not leave this machine:
    the sheet carries a file:// path to each one and never embeds it, and that is asserted over the bytes
    below with a liveness check. A path cannot be mailed anywhere useful; a base64 payload can."""
    return "file:///" + str(p).replace("\\", "/")


def _views(path):
    """(native uri, comparison uri, scale, band height) for one crop file."""
    im = Image.open(str(path)).convert("L")
    cmp_im, scale, band = G.comparison(im)
    return _uri(path), _uri_im(cmp_im), scale, band, im.size


# EDGE-SLICED NEIGHBOURS, taken from the cut rather than from a report. The figure behind the sheet's
# edge-cut instruction was quoted as "19 crops" in one place and measured as 18 crops carrying 19 sliced
# EDGES in another -- `p796:n0` is sliced on both sides. Two units, one number, used interchangeably;
# the same shape as "five faults, four names". Both are rendered, both derived.
EDGE = {x["span_id"]: x for x in flags.get("edge_sliced_neighbour", [])}
EDGE_N_EDGES = sum(x["n_edges"] for x in EDGE.values())
assert flags.get("edge_sliced_note"), "the cut carries no rule for the edge-slice population"
assert not flags.get("edge_truncated_span"), \
    "the cut found %d crop(s) where the SPAN itself is cut by the crop edge; the edge-cut instruction " \
    "on this sheet is the wrong instruction for them" % len(flags.get("edge_truncated_span") or [])

# WHAT THE LINK IS. Not "the note": the localizer's REGION, which ends at the next DETECTED note
# start, so a missed start merges two printed notes into one. All 5 regions of 3+ lines on this set were
# opened: 3 hold two notes, 2 hold one note plus page furniture. Rows carry the fact; nothing here asks
# the signer to adjudicate it, because the crop cannot answer it and the pixels are the same pixels
# whichever note they belong to.
REGION_WIDE = {x["span_id"]: x["lines"] for x in cut["note_context"].get("region_covers_3plus_lines", [])}
SHIFT = {x["span_id"]: x for x in cut["note_context"].get("index_shift_screen", [])}
assert cut["note_context"].get("what_the_links_showed"), \
    "the cut carries no account of what the note regions cover"

OVERFULL = {x["span_id"]: x for x in flags.get("runs_not_measurable", [])}
assert all(x["lines_of_type"] > 1 for x in OVERFULL.values()),     "a span is listed as not-measurable without covering more than one line of type"


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
    if r["span_id"] in OVERFULL:
        # THE SIGNER IS THE ONLY THING THAT CAN SEE THIS. The box covers more than one line of type, so
        # the crop holds a whole extra line of print that is not the span. No tally sees it: `word_runs`
        # is a column ink profile and MERGES stacked lines, which is why these 18 are excluded from the
        # runs-vs-words count rather than passing it. The band-clip used to trim some of them and was
        # withdrawn as a set recipe (2026-10-04) because on p677:n13 it chose the wrong line by 4px of
        # centre proximity and deleted the Hebrew. Untrimmed is the honest state; it is a redraw
        # question for the localizer, and until then the signing rule carries it.
        out.append(("OVER-FULL", "this box covers %d lines of type (%s px), so there is a whole extra "
                                 "line of print in the crop that is not this span. Sign every Hebrew "
                                 "span you can SEE here and nothing you cannot; a box holding more than "
                                 "its span is a redraw, not a reading question."
                    % (OVERFULL[r["span_id"]]["lines_of_type"],
                       ", ".join(str(x) for x in OVERFULL[r["span_id"]].get("bands", [])) or "measured at cut time")))
    if r["span_id"] in EDGE:
        # CARRIED BY THE ROW, NOT BY THE SECTION. Three of these spans are also over-full, so they are
        # rendered in the first section; without a badge on the row, sorting them there would have HIDDEN
        # the edge hazard from the signer, which is the sectioning turning into a filter.
        out.append(("EDGE-CUT", "a word on this line is sliced by the %s crop edge and sits in the pad. "
                                "It is not this span and it is not a whole word. Do not sign it; the "
                                "note crop and the page link under the badges show what it is part of."
                    % " and ".join(EDGE[r["span_id"]]["edges"])))
    if r.get("clip") and len(r["clip"]["word_runs"]) != len(r["crop"]["word_runs"]):
        out.append(("RECIPE", "PAD=12 resolves %d word run(s), band-clip %d -- the pair below is the "
                              "recipe question, and it is yours to call"
                    % (len(r["crop"]["word_runs"]), len(r["clip"]["word_runs"]))))
    return out


# THREE SECTIONS, DISJOINT, FIRST MATCH WINS, in the order Chris named them. The assignment is a
# function of the derived populations only -- nothing is typed here -- and the three counts are asserted
# to account for every span, so a span cannot fall between two sections or appear in both.
SECTIONS = [
    ("overfull", "Over-full boxes", lambda r: r["span_id"] in OVERFULL),
    ("edge", "Edge-sliced neighbours", lambda r: r["span_id"] in EDGE),
    ("clean", "Clean", lambda r: True),
]


def _section(r):
    for key, _t, pred in SECTIONS:
        if pred(r):
            return key
    raise AssertionError("no section claims %s" % r["span_id"])


SEC = {r["span_id"]: _section(r) for r in rows}
SEC_ROWS = {k: sorted([r for r in rows if SEC[r["span_id"]] == k],
                      key=lambda r: (r["page"], r["note_index"], r["span_id"]))
            for k, _t, _p in SECTIONS}
assert sum(len(v) for v in SEC_ROWS.values()) == SET_N, \
    "the three sections hold %d of %d spans -- a span is in none of them or in two" \
    % (sum(len(v) for v in SEC_ROWS.values()), SET_N)
assert len(SEC_ROWS["overfull"]) == len(OVERFULL), "the over-full section is not the over-full population"
rows = SEC_ROWS["overfull"] + SEC_ROWS["edge"] + SEC_ROWS["clean"]

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
.badge.overfull{background:#4a3a6a;color:#e6dcff;border-color:#86a}
.why{color:#c9a;font-size:11px;margin:2px 0}
figure{margin:0 14px 14px 0;display:inline-block;vertical-align:top;background:#0d0f12;padding:8px;
 border:1px solid #2a2f37}
figcaption{color:#9aa;font-size:11px;margin-top:6px;max-width:460px}
img{image-rendering:pixelated;background:#fff;display:block;margin-bottom:6px}
.pair{outline:1px dashed #468;outline-offset:6px}
.note{background:#1b2127;border-left:3px solid #468;padding:10px 14px;margin:14px 0}
.badge.edgecut{background:#5a4a12;color:#fff3d0;border-color:#ca6}
.links{margin:6px 0 4px;font-size:11px}
button.fault{background:#2a1416;color:#ffd9d9;border:1px solid #a44;border-radius:3px;padding:3px 8px;
 font:11px system-ui,sans-serif;cursor:pointer;margin-top:4px}
button.fault.on{background:#a44;color:#fff;font-weight:700}
#bar{position:fixed;right:14px;bottom:14px;background:#1b2127;border:1px solid #468;border-radius:4px;
 padding:8px 12px;font-size:12px;z-index:9}
h2 .cnt{color:#fff;background:#2a3a4a;border-radius:3px;padding:0 7px;margin-left:6px}
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
         'bytes before the file is written. The previous truth set was 30%% wrong in the direction of '
         'the candidate, once affirmed verbatim. Write what the pixels show, or abstain.<br>'
         '<b>What is present and is NOT a hint:</b> resolved column runs, counted from the ink by gaps '
         'rather than by recognising letters.<br>'
         '<b>Where a crop holds more than one span of Hebrew, sign every one you can see</b>, in the order they are printed (right to left within a line, top line first). Some of these boxes hold more than the span they were drawn for &mdash; that is a redraw question, and your reading of what is actually there is what settles it. <b>Do not sign a word that the crop edge cuts.</b> Measured on this set, by the rule the cut records: in <b>%d</b> crops a NEIGHBOURING word on the same line is sliced by a vertical crop edge and sits in the pad &mdash; <b>%d</b> sliced edges in all, since %s is cut on both sides. In <b>%d</b> crops is the span&rsquo;s OWN ink cut: edge ink never runs continuously across the box boundary, which is the measurement that could have shown otherwise. A sliced neighbour is noise, not a span, and a fragment signed as a word is a wrong truth. Every row carries a link to the region the box sits in and to the native page, so a word that merely LOOKS truncated can be checked instead of guessed at. The linked picture is the LOCALIZER&rsquo;s region, not a printed note: it ends where the detector saw the next note start, and of the 5 regions here that run to three or more lines, 3 hold two printed notes. Rows say so where it applies.<br>'
         '<b>If a crop holds no Hebrew at all, or nothing legible, do not sign it &mdash; press its button.</b> That records a fault against the box, which is a different fact from declining to sign, and the faults download as a file beside the signing skeleton. 23 spans have already been dropped from 96 for faults a script could measure; two of those were found by eye, because no script here can ask what SCRIPT the pixels are in.</div>'
         % (len(EDGE), EDGE_N_EDGES,
            " and ".join(sorted(x for x in EDGE if EDGE[x]["n_edges"] == 2)) or "no crop",
            len(flags.get("edge_truncated_span") or [])))
H.append('<table class="sum">'
         '<tr><td>spans</td><td><b>%d</b> on %d pages, 0 refused by the crop gate &mdash; the 96 set minus 20 spans at measured box faults (14 on the printed rule, 6 at the three duplicate boxes)</td></tr>'
         '<tr><td>band-clips</td><td>%s</td></tr>'
         '<tr><td>(clip detail)</td><td><b>%d</b> written, %d needed no trim (no foreign line in the pad), '
         '<b>%d abstained</b>, %d resolved FEWER runs than its parent</td></tr>'
         '<tr><td>recipe differs</td><td><b>%d</b> span(s)</td></tr>'
         '<tr><td>DUP-BOX</td><td><b>%d</b> pair(s): %s</td></tr>'
         '<tr><td>NO-TYPE</td><td><b>%d</b> crop(s) hold no line of type at all &mdash; the box is on '
         'the printed rule: %s</td></tr>'
         '<tr><td>SHORT-BOX</td><td><b>%d</b>: %s</td></tr>'
         '<tr><td>sections</td><td><b>%d</b> over-full &nbsp;&middot;&nbsp; <b>%d</b> edge-sliced shown '
         'in section 2 (<b>%d</b> in the set; %d of those are also over-full and are in section 1) '
         '&nbsp;&middot;&nbsp; <b>%d</b> clean</td></tr>'
         '<tr><td>edge slices</td><td><b>%d</b> crop(s), <b>%d</b> sliced edge(s). Span itself cut: '
         '<b>%d</b>.</td></tr>'
         '<tr><td>note context</td><td><b>%d</b> of %d spans link to the region the box sits in '
         '(same PAD=%d recipe; the span crop is asserted byte-identical inside it) and to the native '
         'page PNG. %s</td></tr>'
         '<tr><td>region width</td><td><b>%d</b> region(s) run to 3+ lines (%s); all were opened, 3 hold '
         'two printed notes. <b>%d</b> span(s) sit behind one and carry a note-NUMBER question: %s. '
         'Neither changes what you sign.</td></tr>'
         '</table>'
         % (SET_N, len({r["page"] for r in rows}),
            ('applied: see the detail row below' if cut["clip"].get("applied_as_set_recipe") else
             '<b>WITHDRAWN as a set recipe</b> &mdash; every crop here is PAD=12 only, the same recipe '
             'as the 19 spans already signed, so the two sets are comparable. The clip survives as a '
             'per-span tool. Its one accuracy measurement (p912:n2, 24 paired arms) moved 10 arms for a '
             'net of +1 exact, losing claude-sonnet-5 and gemini-3.8-flash to <i>wrong</i>.'),
            cut["clip"]["written"], cut["clip"]["no_trim"],
            SET_N - cut["clip"]["written"] - cut["clip"]["no_trim"],
            len(cut["clip"]["word_runs_regressed"]),
            len(cut["clip"]["word_runs_differ"]), len(flags["duplicate_box"]),
            html.escape("; ".join(" = ".join(v) for v in flags["duplicate_box"].values())),
            len(NOTYPE), html.escape(", ".join(sorted(NOTYPE))),
            len(SHORT), html.escape(", ".join(sorted(SHORT))),
            len(SEC_ROWS["overfull"]), len(SEC_ROWS["edge"]), len(EDGE),
            len(set(EDGE) & set(OVERFULL)), len(SEC_ROWS["clean"]),
            len(EDGE), EDGE_N_EDGES, len(flags.get("edge_truncated_span") or []),
            cut["note_context"]["written"], SET_N, cut["note_context"]["pad_native_px"],
            ("Every one derived." if not cut["note_context"]["faults"] else
             "NOT derived for: %s &mdash; those rows link to the page only."
             % html.escape(", ".join(sorted(cut["note_context"]["faults"])))),
            len(REGION_WIDE), html.escape(", ".join("%s at %d lines" % (k, v)
                                                    for k, v in sorted(REGION_WIDE.items()))),
            len(SHIFT), html.escape(", ".join(sorted(SHIFT))) or "none"))

assert not cut["clip"]["word_runs_regressed"], "a clip resolves fewer runs than its parent"
assert SET_N == (cut["clip"]["written"] + cut["clip"]["no_trim"] + len(cut["clip"]["abstained_ids"])
                 + cut["clip"].get("not_attempted", 0)), \
    "written + no-trim + abstained + not-attempted does not account for every span in the set"
assert cut["clip"].get("applied_as_set_recipe") or cut["clip"]["written"] == 0, \
    "the cut says the clip is withdrawn as a set recipe and then reports clips written"
assert (cut["clip"]["written"] > 0) == any(r.get("clip") for r in rows), \
    "the clip count and the rows the sheet would render a clip for disagree"

_both = sorted(set(EDGE) & set(OVERFULL))
SECTION_HEAD = {
    "overfull": '<h2>1 &middot; Over-full boxes <span class="cnt">%d</span></h2>'
                '<div class="note">The box covers more than one line of type, so the crop holds a whole '
                'extra line of print that is not this span. Each row is badged with the number of lines '
                'its box covers, which is what tells you what &ldquo;all the Hebrew visible&rdquo; means '
                'here. <b>Sign every Hebrew span you can see and nothing you cannot.</b> These boxes are '
                'not redrawn: a hand-placed box in a localizer-placed set would change what the set '
                'measures, so the box stays as the localizer drew it and the badge carries the '
                'consequence.%s</div>'
                % (len(SEC_ROWS["overfull"]),
                   (" %d of these are ALSO edge-sliced (%s) and carry both badges."
                    % (len(_both), ", ".join(_both))) if _both else ""),
    "edge": '<h2>2 &middot; Edge-sliced neighbours <span class="cnt">%d</span></h2>'
            '<div class="note">A word on the span&rsquo;s own line is sliced by a vertical crop edge and '
            'sits in the pad. <b>Do not sign a word the crop edge cuts.</b> %d crops in the set carry a '
            'sliced edge (%d edges in all); the %d also in section 1 are shown there with both badges. '
            'The note crop and page links on each row are there for exactly this: a short word and a cut '
            'word look the same inside the crop.</div>'
            % (len(SEC_ROWS["edge"]), len(EDGE), EDGE_N_EDGES, len(_both)),
    "clean": '<h2>3 &middot; Clean <span class="cnt">%d</span></h2>'
             '<div class="note">One line of type in the box, no neighbour cut by a crop edge. Nothing '
             'measured here needs a caveat &mdash; which is not a claim that the box is right, only that '
             'no measurement this lane has says otherwise.</div>' % len(SEC_ROWS["clean"]),
}

shown, nflag, _cur = {}, 0, None
for r in rows:
    sid = r["span_id"]
    if SEC[sid] != _cur:
        _cur = SEC[sid]
        H.append(SECTION_HEAD[_cur])
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
                 % ({"RECIPE": " recipe", "NO-TYPE": " notype", "OVER-FULL": " overfull",
                     "EDGE-CUT": " edgecut"}.get(name, ""), name,
                    html.escape(why)))
    # TWO LINKS OUT, BY PATH. The note the box was drawn inside, and the page it came off. A failure
    # to derive the note is PRINTED on the row, because a missing link that looks like an absent link is
    # how a narrowed view passes for a complete one.
    nc = r.get("note_context")
    H.append('<div class="links">')
    if nc:
        H.append('<a href="%s">the region this box sits in &mdash; %d&times;%d, %d line(s)%s</a> &nbsp;&middot;&nbsp; '
                 % (_furl(nc["path"]), nc["size"][0], nc["size"][1], nc["lines_in_segment"],
                    "" if nc["segment_held_the_span"] else ", FIRST segment of a stitched note"))
    else:
        H.append('<span class="why">no note crop derived: %s</span> &nbsp;&middot;&nbsp; '
                 % html.escape(r.get("note_fault") or "unrecorded"))
    H.append('<a href="%s">native page PNG, file p%d</a></div>' % (_furl(r["page_png"]), r["page"]))
    if sid in REGION_WIDE:
        H.append('<div class="why">This region runs to %d lines. 5 regions on this set do; all 5 were '
                 'opened and 3 of them hold TWO printed notes, because the detector ends a note at the '
                 'next note start it SEES. Nothing for you to decide &mdash; sign the Hebrew in the box '
                 'above. It is on the row because the extra lines in the linked picture may belong to a '
                 'different note.</div>' % REGION_WIDE[sid])
    if sid in SHIFT:
        H.append('<div class="why">A region of %d lines sits earlier on this page (at note %d). If that '
                 'region covers two printed notes, this span&rsquo;s note NUMBER is one off &mdash; which '
                 'is a question about scoring, not about these pixels. Checked by hand: %s</div>'
                 % (SHIFT[sid]["behind_a_region_of"], SHIFT[sid]["at_note_index"],
                    "this box is in the note printed <b>o</b> while carrying note 2, so its note identity "
                    "is open." if sid == "p245:n1" else "it checks out."))
    H.append('<button class="fault" data-s="%s" onclick="mark(this)">not Hebrew / blank '
             '&mdash; record a fault</button>' % html.escape(sid))
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

# A FAULT IS NOT AN ABSTAIN AND NOT A SIGNATURE. 23 of the 96 were dropped for faults a script could
# measure; the last two were found by eye, because nothing here can ask what SCRIPT the pixels are in.
# So the signer needs a way to say "there is nothing here to sign" that lands as a RECORD rather than as
# an empty row, and it has to name the span and the pixels it was given -- the crop hash, so a re-cut
# span cannot inherit the fault any more than it could inherit a signature.
H.append('<div id="bar">faults recorded: <b id="fc">0</b> &nbsp;&middot;&nbsp; '
         '<a id="dl" download="truthset_faults_%s.jsonl" href="#" style="display:none">download</a></div>'
         % SET)
H.append('<script>\n'
         'var CH=%s, SETID=%s, F={};\n'
         'function mark(b){var s=b.getAttribute("data-s");\n'
         ' if(F[s]){delete F[s];b.className="fault";}else{F[s]=1;b.className="fault on";}\n'
         ' upd();}\n'
         'function upd(){var k=Object.keys(F).sort();\n'
         ' document.getElementById("fc").textContent=k.length;\n'
         ' var L=k.map(function(s){return JSON.stringify({span_id:s,crop_sha16:CH[s],\n'
         '   fault:"not-hebrew-or-blank",basis:"human, from the pixels",set_sha16:SETID});}).join("\\n");\n'
         ' var a=document.getElementById("dl");\n'
         ' a.href="data:text/plain;charset=utf-8,"+encodeURIComponent(L+(L?"\\n":""));\n'
         ' a.style.display=k.length?"inline":"none";}\n'
         '</script>' % (json.dumps({_s: shown[_s]["A2_spanbox"] for _s in sorted(shown)}),
                        json.dumps(SET)))
H.append('<h2>How to record a fault</h2><div class="sub">The button on a row records a fault against '
         'that BOX &mdash; nothing legible, or nothing in the script this span is supposed to be in. It '
         'is not an abstain and not a signature: &ldquo;there is nothing here to sign&rdquo; and &ldquo;I '
         'will not sign this&rdquo; are different facts and the set needs the first one recorded. Press '
         'as many as apply, then use <b>download</b> at the bottom right; it writes one line per fault, '
         'each naming the span and the hash of the pixels you were shown, beside the signing skeleton. '
         'The 23 spans already dropped took every non-legible crop that could be MEASURED, so this '
         'should be empty or nearly so &mdash; it is here for the ones no measurement could find.</div>')
H.append('<h2>How to record a signature</h2><div class="sub">A skeleton with one row per span, in this '
         'order, is written beside this sheet: <code>%s</code>. Each row has an '
         'empty LIST to fill from the pixels &mdash; one entry per span of Hebrew visible in that crop, '
         'so a box that holds two spans records two readings &mdash; and a flag to set instead when the '
         'pixels support none. The crop hash in each row is what the signature is ABOUT, so a re-cut span '
         'cannot inherit an old signature. (The field is not named here on purpose: this file asserts '
         'that no candidate-derived field name appears in it, and that guard is worth more than the '
         'convenience of writing it out.)</div>' % SKEL_NAME)
H.append('<div class="sub" style="margin-top:18px">Flagged rows: %d of %d &mdash; no longer shown '
         'first, but grouped into the three sections above, so what a row needs from you is stated '
         'before you reach it. Sheet built from <code>%s</code>.</div>' % (nflag, SET_N, CUT.name))
doc = "\n".join(H)
by_id = {r["span_id"]: r for r in rows}
assert set(by_id) >= set(shown), "a span is shown without a row to badge it from"

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
# THE SECTIONS, PROVED OVER THE RENDERED DOCUMENT. A section is a claim about which rows need which
# judgement, so it is asserted where the signer reads it, not where it was computed.
_pos = [doc.index(SECTION_HEAD[k]) for k, _t, _p in SECTIONS]
assert all(doc.count(SECTION_HEAD[k]) == 1 for k, _t, _p in SECTIONS), \
    "a section heading is rendered twice or not at all"
assert _pos == sorted(_pos), "the sections are not rendered in the order they were named"
for _i, (_k, _t, _p) in enumerate(SECTIONS):
    _lo = _pos[_i]
    _hi = _pos[_i + 1] if _i + 1 < len(_pos) else len(doc)
    for _r in SEC_ROWS[_k]:
        _at = doc.index("<b>%s</b>" % html.escape(_r["span_id"]))
        assert _lo < _at < _hi, \
            "%s is rendered outside the %s section it was assigned to" % (_r["span_id"], _k)
assert doc.count(">EDGE-CUT<") == len(EDGE), \
    "the sheet renders %d EDGE-CUT badges for %d edge-sliced crops" % (doc.count(">EDGE-CUT<"), len(EDGE))
assert doc.count("record a fault</button>") == SET_N, \
    "the fault button is on %d of %d rows" % (doc.count("record a fault</button>"), SET_N)

# ---- NO NOTE-BOX PIXELS IN THIS FILE, AND A DETECTOR THAT CAN SEE THEM -----------------------------
# The standing rule is that no note-box crop leaves the network. Chris asked for each span to link to its
# full note crop (2026-10-04, "file:// is fine"), and a path is not pixels: this file stays free of note
# pixels and the links resolve only on this machine. The old guard was the string "notebox", which these
# crops do not contain -- a name check is not a pixel check, so the guard is now made over the BYTES.
# A middle slice of the base64 is used, not a prefix: every PNG shares its header, so a prefix test would
# fire on anything. LIVENESS FIRST -- the same construction must FIND the span crops, which are embedded
# here on purpose. A probe that misses passes on nothing.
def _mid64(p):
    b = base64.b64encode(io.open(str(p), "rb").read()).decode("ascii")
    return b[len(b) // 2:len(b) // 2 + 64]


assert all(_mid64(r["crop"]["path"]) in doc for r in rows), \
    "the embed detector cannot find the span crops, which ARE embedded in this document -- it would " \
    "pass on a note crop too"
_emb = [r["span_id"] for r in rows if r.get("note_context") and _mid64(r["note_context"]["path"]) in doc]
assert not _emb, "note pixels are EMBEDDED in the sheet, not linked, for %s" % _emb
_nolink = [r["span_id"] for r in rows
           if r.get("note_context") and _furl(r["note_context"]["path"]) not in doc]
assert not _nolink, "a note crop was derived at cut time and the sheet does not link it: %s" % _nolink
assert all(_furl(r["page_png"]) in doc for r in rows), "a row does not link its native page PNG"
assert "A1_notebox" not in doc and "notebox" not in low, "an A1 note-box crop is referenced"
assert str(HAD.CROPDIR) not in doc, "the sheet points at the 19-span corpus instead of its own crops"
# A BADGE THAT MISSES FLAGS NOTHING. The OVER-FULL population is the one thing on this sheet that
# only the signer can act on, and it is derived from the cut rather than listed here, so the
# rendered count is asserted against the derived one instead of against a number somebody typed.
assert doc.count(">OVER-FULL<") == len(OVERFULL), \
    "the sheet renders %d OVER-FULL badges for %d over-full boxes" % (doc.count(">OVER-FULL<"), len(OVERFULL))
assert nflag == sum(1 for r in rows if badges(r)), \
    "the flagged count in the header is not the number of rows carrying a badge"
assert doc.count("<div class=\"row\">") == SET_N, \
    "the sheet renders %d rows, not %d" % (doc.count("<div class=\"row\">"), SET_N)

# ---- content-addressed name + the clobber guard ----------------------------------------------------
# The name must address EVERY pixel the sheet shows. It addressed only the parent crops, so when
# the clip rule was corrected on 2026-10-04 the sheet kept its old name and the clobber guard had
# to refuse it -- the guard caught what the name should have expressed.
#
# AND IT MUST ADDRESS WHAT THE SIGNER IS TOLD. Found the same day by watching this script
# overwrite its own output: the OVER-FULL badges were added, the crops did not change, so the
# digest did not change and the badge-less sheet was replaced in place with the clobber guard
# satisfied -- it compares crop hashes and the crops were identical. Nothing was lost here (that
# sheet had never been shown to anybody) but the mechanism is the one that lost the 19-span
# approval. A sheet is not a set of pictures, it is a reading TASK: the badge on a row tells the
# signer that the box is over-full and to sign only what they can see, and a signature given
# with that instruction is not the same record as one given without it. So the badges are in the
# address.
# AND IT MUST ADDRESS THE PROSE. Named as unfixed on 2026-10-04 and fixed the same day at Chris's
# instruction: "put the prose rules in the sheet's address along with the badges." A reworded header used
# to produce the same digest, and the header is where the signing rules live -- the edge-cut rule, the
# over-full rule, what a fault means. A signature given under one wording is not a record of a signature
# given under another. So the address covers the whole document with the image payloads stripped out,
# which is everything the signer can READ. The strip is asserted to have hit every payload and only
# payloads, so nothing silently leaves the address.
#
# CONSEQUENCE, NAMED: the subheader carries the commit the crops were cut at, so a new HEAD gives a new
# sheet name even when the pixels and the words are identical. That is churn, not loss, and it is the
# honest side of the trade -- the code that made the pixels is part of the task the signature records.
# The clobber guard still compares crop hashes only, so it remains the pixel-level protection it was.
PROSE = re.sub(r"data:image/png;base64,[A-Za-z0-9+/=]+", "<payload>", doc)
assert doc.count("data:image/png;base64,") >= SET_N, \
    "the payload pattern matches %d things in a document with %d rows -- it does not describe this file" \
    % (doc.count("data:image/png;base64,"), SET_N)
assert PROSE.count("<payload>") == doc.count("data:image/png;base64,"), \
    "the payload strip hit %d of %d payloads" % (PROSE.count("<payload>"),
                                                 doc.count("data:image/png;base64,"))
assert "base64," not in PROSE, "a payload survived the strip and is inside the prose digest"
PDIG = hashlib.sha256(PROSE.encode("utf-8")).hexdigest()[:8]
sig = ";".join("%s:%s:%s:%s" % (s, shown[s]["A2_spanbox"], shown[s].get("A2_bandclip") or "-",
                               ",".join(n for n, _ in badges(by_id[s])) or "-")
               for s in sorted(shown)) + "|prose:" + PDIG
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
                                   "names", "no A1 note-box reference",
                                   "no note pixels EMBEDDED (byte test, with its liveness check against "
                                   "the span crops that are)", "%d rows" % SET_N,
                                   "three sections in order, every row inside the one it was assigned",
                                   "one EDGE-CUT badge per edge-sliced crop",
                                   "a fault button on every row",
                                   "every derived note crop and every page PNG linked"],
           "prose_digest": PDIG,
           "address_covers": ["every crop hash", "every badge name per span",
                              "the whole readable document (image payloads stripped)"],
           "sections": {k: [r["span_id"] for r in SEC_ROWS[k]] for k, _t, _p in SECTIONS},
           "edge_sliced": {"crops": len(EDGE), "edges": EDGE_N_EDGES,
                           "also_over_full": sorted(set(EDGE) & set(OVERFULL)),
                           "span_truncations": len(flags.get("edge_truncated_span") or [])},
           "note_context": {"linked": sum(1 for r in rows if r.get("note_context")),
                            "embedded": 0, "how": "file:// path, never a payload",
                            "region_covers_3plus_lines": REGION_WIDE,
                            "note_number_question": sorted(SHIFT)},
           "badges": {"NO-TYPE": sorted(NOTYPE), "DUP-BOX": sorted(DUP), "SHORT-BOX": sorted(SHORT),
                      "EDGE-CUT": sorted(EDGE),
                      "RECIPE": [d["span_id"] for d in cut["clip"]["word_runs_differ"]],
                      "OVER-FULL": sorted(OVERFULL)},
           "crop_sha16": shown},
          io.open(str(SIDE), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# A LIST, not a field: Chris signs every Hebrew span visible in the crop, because 22 of these boxes
# resolve more word runs than the extractor claims words and the box rule makes that a redraw
# question. One reading per visible span, in printed order; an empty list with abstain set means the
# pixels support none.
skel = [{"span_id": s, "crop_sha16": shown[s], "readings": [], "abstain": False, "note": "",
         "fault": "", "fault_means": "set to not-hebrew-or-blank when the crop holds nothing to sign. "
                                     "A fault is about the BOX and is not an abstain: the sheet's "
                                     "per-row button writes these lines for you",
         "section": SEC[s],
         "readings_are": "one entry per span of Hebrew VISIBLE in this crop, in printed order; the crop may hold more than the span it was drawn for",
         "signed_from": "pixels, candidate withheld", "sheet": OUT.name} for s in sorted(shown)]
sk = "\n".join(json.dumps(x, ensure_ascii=False) for x in skel) + "\n"
assert not READABLE.search(sk), "the signing skeleton carries readable script"
io.open(str(SKEL), "w", encoding="utf-8").write(sk)

print("sheet %s" % OUT.name)
print("  sections: over-full %d, edge-sliced %d (of %d in the set, %d also over-full), clean %d"
      % (len(SEC_ROWS["overfull"]), len(SEC_ROWS["edge"]), len(EDGE),
         len(set(EDGE) & set(OVERFULL)), len(SEC_ROWS["clean"])))
print("  note crops linked %d, embedded 0; page PNGs linked %d; prose digest %s"
      % (sum(1 for r in rows if r.get("note_context")), SET_N, PDIG))
print("  rows %d   flagged %d   clips shown %d   recipe pairs %d"
      % (SET_N, nflag, sum(1 for s in shown.values() if "A2_bandclip" in s),
         len(cut["clip"]["word_runs_differ"])))
print("  withheld: hebrew, word count, nikud flag, note text -- asserted over %d bytes" % len(doc))
print("  sidecar %s   skeleton %s" % (SIDE.name, SKEL.name))
print(banner(GIT_START, GIT_END))
