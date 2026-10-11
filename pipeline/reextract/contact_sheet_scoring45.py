# -*- coding: utf-8 -*-
"""The scoring-run contact sheet: the 45 crops that would be sent, native size, beside their signed text. (Lane B)

    python contact_sheet_scoring45.py

ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88). Every file this writes says so.

THE GATE. Chris, 2026-10-11: "Before any outbound call, produce a contact sheet: every crop to be sent, native
size, beside its signed text, before/after where changed; Chris approves it, then spend. Record the hash of every
crop sent in the run header." And: "Approve the crops on what they show, not the text beside them." The crop is
the subject of the approval; the signed text is shown so the reader can see what the scorer will compare a model's
read against -- and what KIND of thing that is (a pixel reading, or the signer's editorial correction).

THIS IS NOT THE SIGNING SHEET. `truth_set_sheet.py` withholds the candidate because those spans were not yet
signed and a shown candidate anchors the signer. These 45 are signed, so the signature is shown. Same two
helpers (native view, 4x nearest-neighbour view) -- but see HELPERS below.

THE RUN BEING GATED (a plan, not an event): 45 truth spans x 2 models (anthropic/claude-opus-5.5,
qwen/qwen3.7-plus) x 2 channels. Channel 1, BARE: the A2 span crop alone. Channel 2: the same span crop PLUS the
Latin note TEXT with every Hebrew run masked to U+2022 by `hebrew_frontier_or._ctx` (imported, not reimplemented).
No note-box crop ever leaves the network; channel 2 carries note TEXT only.

WHAT THIS DOES NOT DO. It sends nothing: no network call of any kind, no key read, no model named in a request.
It cannot say whether a crop is legible -- only a human reading the pixels can; it can only make sure that human
is shown the exact pixels and the exact bytes of text that would go out. It does not decide the scoring rule.

THE CHANNEL-2 FINDING THIS SHEET EXISTS TO SURFACE. `latin_context` is loaded by `hebrew_aperture_diag.build_set`
from the 2026-09-06 sitting records, which cover the OLD 21-span population. Most of these 45 are not in it, so
their channel-2 string is ABSENT -- not empty. Absent means the loader the frontier run uses has nothing for the
span and the run as built could not send it; empty would mean a note that had no Latin. The sheet prints which,
per row, and counts them. It does not invent a note text from another source.

HELPERS. `truth_set_sheet.py` is a script, not a module: importing it executes the whole 74-span sheet at module
level (reads its cut, renders HTML, writes files). Its `_uri` / `_uri_im` / `_views` therefore cannot be imported
here, and `_views` returns a matched-scale comparison, not the 4x view. The two tiny pieces needed (a PNG data
URI, a NEAREST upscale) are written below and say so; nothing was copied silently.

BORN-CHECKS are made over the EMITTED BYTES of the document, each with a liveness count (a probe that matches
nothing passes on everything), and the register check for the two called-out rows is made inside THEIR OWN row
element, because the stylesheet and header mention `corrected` and `sic` and a whole-document grep passes on
furniture.
"""
import base64
import hashlib
import html
import io
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "scripts"))
sys.stdout.reconfigure(encoding="utf-8")
from PIL import Image                                                      # noqa: E402
import hebrew_aperture_diag as HAD                                        # noqa: E402
import hebrew_frontier_or as FOR                                          # noqa: E402  _ctx, ARMS, APERTURE
from clean_run import git_state, provisional                              # noqa: E402

SET = "0401b636ffa7bf1a"
PRINTED_OFFSET = 88
N_EXPECT = 45
N_PASS1, N_PASS2, N_PASS3 = 25, 17, 3
MODELS = ("anthropic/claude-opus-5.5", "qwen/qwen3.7-plus")
CHANNELS = ("bare", "text")
CROP_DIR_NAME = "truthset96_crops_4e73b10d46a41f4a"
CROPDIR = HAD.DATA / CROP_DIR_NAME
APERTURE = FOR.APERTURE
UPSCALE = 4
SHORT_PX = 40
REPOS = {"goatyard-laneB": "C:/Users/cnogr/git/goatyard-laneB",
         "dr-voluminous": "C:/Users/cnogr/git/dr-voluminous"}

F_PASS1 = HAD.DATA / ("signing_pass1_ingest_%s.json" % SET)
F_PASS1_TILES = HAD.DATA / ("glyphsign_signed_%s_20261004_pass1.jsonl" % SET)
F_PASS2 = HAD.DATA / "truth_pass2.jsonl"
F_PASS3R2 = HAD.DATA / "truth_pass3_r2.jsonl"
F_R1_EXPORT = HAD.DATA / ("glyphsign_%s_pass3_3span_signed_51c0e7ba.jsonl" % SET)
F_R2_EXPORT = HAD.DATA / ("glyphsign_%s_pass3_r2_3span_signed_70fc08e1.jsonl" % SET)
F_ADJ = HAD.DATA / "ADJUDICATION_pass3_r1_588879f2f4a2cee8.json"
F_COST_BARE = HAD.DATA / "hebrew_frontier_or_notext_20261004.jsonl"
F_COST_TEXT = HAD.DATA / "hebrew_frontier_or_reads_20260927.jsonl"
SOURCES = (F_PASS1, F_PASS1_TILES, F_PASS2, F_PASS3R2, F_R1_EXPORT, F_R2_EXPORT, F_ADJ, F_COST_BARE, F_COST_TEXT)

POLICY = ("Before any outbound call, produce a contact sheet: every crop to be sent, native size, beside its "
          "signed text, before/after where changed; Chris approves it, then spend. Record the hash of every crop "
          "sent in the run header. (Chris, 2026-10-11.) Approve the crops on what they show, not the text beside "
          "them.")
RULES = (
    "No note-box crop ever leaves the network; channel 2 carries note TEXT only.",
    "No :batch model variants.",
    "Endpoint C 192.168.1.169:11434 for anything compared to signed verdicts; never 192.168.1.179 or "
    "192.168.1.188.",
)
DIGEST_RULE = ('Take each span as the line "<span_id> <crop_sha16>" (one ASCII space; span_id like p133:n5, FILE '
               'page; crop_sha16 = first 16 hex of the SHA-256 of the crop PNG file bytes). Sort the 45 lines in '
               'plain Python str order (code point). Join with "\\n", no trailing newline, encode UTF-8, '
               'SHA-256, take the first 16 hex. That is the set digest.')

CALLED_OUT = ("p493:n3", "p594:n0")
ROUND2 = ("p493:n3", "p594:n0", "p803:n0")

HEB_RX = re.compile(u"[\u0590-\u05ff]")
PROBE_HEB = u"\u05d0\u05d1"
CHECKS = 0


def check(cond, msg):
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError(msg)


def sha16(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode("utf-8")).hexdigest()[:16]


def _jl(p):
    return [json.loads(l) for l in open(str(p), encoding="utf-8") if l.strip()]


def esc(s):
    return html.escape(str(s), quote=True)


def sid_key(s):
    p, n = s.split(":")
    return (int(p[1:]), int(n[1:]))


def printed(sid):
    return int(sid.split(":")[0][1:]) - PRINTED_OFFSET


# ---------------------------------------------------------------- tile -> text (ported from ingest_pass2.py)
# ingest_pass2.py is a script that runs on import, so derive() cannot be imported; this is a port, and the
# r2 rows are cross-checked against the signed file's own signature_full below.

def tile_out(t, prior=False):
    v = t.get("prior_verdict") if prior else t.get("verdict")
    chose = t.get("prior_chose") if prior else t.get("chose")
    v, gap = v or "", t["kind"] == "gap"
    if v == "deleted":
        return ""
    if v == "not_in_crop":
        return "[ ]" if gap else "[" + t["shown"] + "]"
    if v in ("confirmed", "sic"):
        return " " if gap else t["shown"]
    if v == "corrected":
        if gap:
            return " " if chose == "space" else ""
        return chose or "?"
    return "?"


def ins_out(it, prior=False):
    v = it.get("prior_verdict") if prior else it.get("verdict")
    chose = it.get("prior_chose") if prior else it.get("chose")
    if not chose:
        return "?"
    s = " " if it["kind"] == "gap" else chose
    return "[" + s + "]" if v == "not_in_crop" else s


def derive(r, prior=False):
    ins = r.get("insertions", [])
    out = [ins_out(x, prior) for x in sorted((x for x in ins if x["after_i"] is None), key=lambda x: x["seq"])]
    for t in r["tiles"]:
        out.append(tile_out(t, prior))
        out.extend(ins_out(x, prior) for x in sorted((x for x in ins if x["after_i"] == t["i"]),
                                                     key=lambda x: x["seq"]))
    return "".join(out)


def counts_from_tiles(tiles):
    c = {"confirmed": 0, "corrected": 0, "sic": 0}
    for t in tiles:
        if t.get("kind") == "gap":
            continue
        if t.get("verdict") in c:
            c[t["verdict"]] += 1
    return c


# ---------------------------------------------------------------- the two view helpers (see HELPERS in the docstring)

def data_uri_png(im_or_bytes):
    if isinstance(im_or_bytes, bytes):
        raw = im_or_bytes
    else:
        b = io.BytesIO()
        im_or_bytes.save(b, format="PNG")
        raw = b.getvalue()
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def upscale_nearest(im, k=UPSCALE):
    return im.resize((im.width * k, im.height * k), Image.NEAREST)


# ================================================================ START
GIT_START = {k: git_state(v) for k, v in REPOS.items()}

# ---- 1. the 45, derived
p1 = json.load(io.open(str(F_PASS1), encoding="utf-8"))
check(p1.get("set_sha16") == SET, "pass-1 ingest is from set %r, not %r" % (p1.get("set_sha16"), SET))
P1_SIGNED = list(p1["dispositions"]["signed"]) + list(p1["dispositions"]["signed_span_aperture_only"])
P2_ROWS = _jl(F_PASS2)
P3_ROWS = _jl(F_PASS3R2)
P2_IDS = [r["span_id"] for r in P2_ROWS]
P3_IDS = [r["span_id"] for r in P3_ROWS]
ALL_IDS = sorted(set(P1_SIGNED) | set(P2_IDS) | set(P3_IDS), key=sid_key)
DERIVATION = ("pass 1 = dispositions.signed (%d) + dispositions.signed_span_aperture_only (%d) = %d; "
              "pass 2 = lines of truth_pass2.jsonl = %d; pass 3 r2 = lines of truth_pass3_r2.jsonl = %d; "
              "union = %d unique ids" % (len(p1["dispositions"]["signed"]),
                                         len(p1["dispositions"]["signed_span_aperture_only"]), len(P1_SIGNED),
                                         len(P2_IDS), len(P3_IDS), len(ALL_IDS)))
print(DERIVATION)
check(len(P1_SIGNED) == N_PASS1 and len(P2_IDS) == N_PASS2 and len(P3_IDS) == N_PASS3,
      "the files give %d + %d + %d, not %d + %d + %d: %s" % (len(P1_SIGNED), len(P2_IDS), len(P3_IDS),
                                                            N_PASS1, N_PASS2, N_PASS3, DERIVATION))
check(len(ALL_IDS) == N_EXPECT and len(P1_SIGNED) + len(P2_IDS) + len(P3_IDS) == N_EXPECT,
      "the files give %d unique ids (sum %d), not %d: %s" % (len(ALL_IDS),
                                                            len(P1_SIGNED) + len(P2_IDS) + len(P3_IDS),
                                                            N_EXPECT, DERIVATION))
PASS_OF = {}
for s in P1_SIGNED:
    PASS_OF[s] = 1
for s in P2_IDS:
    PASS_OF[s] = 2
for s in P3_IDS:
    PASS_OF[s] = 3

# ---- 2. signed text and register, per row
P1_DISPO = {s: k for k in ("signed", "signed_span_aperture_only") for s in p1["dispositions"][k]}
P1_TILES = {r["span_id"]: r for r in _jl(F_PASS1_TILES)}
P2_BY = {r["span_id"]: r for r in P2_ROWS}
P3_BY = {r["span_id"]: r for r in P3_ROWS}
R1 = {r["span_id"]: r for r in _jl(F_R1_EXPORT)}
R2 = {r["span_id"]: r for r in _jl(F_R2_EXPORT)}
ADJ = json.load(io.open(str(F_ADJ), encoding="utf-8"))

# ---- 3. channel 2 text, from the loader the frontier run itself uses
POP = {s["span_id"]: s for s in HAD.build_set(include_sealed=True)}

rows = []
for sid in ALL_IDS:
    ps = PASS_OF[sid]
    r = {"span_id": sid, "page_file": int(sid.split(":")[0][1:]), "page_printed": printed(sid), "pass": ps}
    if ps == 1:
        tr = P1_TILES[sid]
        c = counts_from_tiles(tr["tiles"])
        r.update(disposition=P1_DISPO[sid], signature=derive(tr), signature_full=None,
                 n_confirmed=c["confirmed"], n_corrected=c["corrected"], n_sic=c["sic"],
                 counts_source="derived from the pass-1 per-tile verdicts (consonant tiles only)",
                 signed_from=tr["signed_from"], box_fault=None, in_crop_trimmed=None, sic=[],
                 crop_sha16_signed=tr["crop_sha16"], signed_partial_in_crop=False)
    else:
        sr = (P2_BY if ps == 2 else P3_BY)[sid]
        r.update(disposition=sr["disposition"], signature=sr["signature"], signature_full=sr.get("signature_full"),
                 n_confirmed=sr.get("n_confirmed"), n_corrected=sr.get("n_corrected"), n_sic=sr.get("n_sic"),
                 counts_source="carried by the signed row" if sr.get("n_confirmed") is not None else "not carried",
                 signed_from=sr["signed_from"], box_fault=sr.get("box_fault") or None,
                 in_crop_trimmed=sr.get("in_crop_trimmed") or None, sic=sr.get("sic") or [],
                 crop_sha16_signed=sr["crop_sha16"],
                 signed_partial_in_crop=(sr["disposition"] == "signed_partial_in_crop"))
    path = CROPDIR / ("p%d_n%d_%s.png" % (r["page_file"], int(sid.split(":")[1][1:]), APERTURE))
    check(path.is_file(), "%s: crop %s does not exist" % (sid, path))
    raw = open(str(path), "rb").read()
    im = Image.open(io.BytesIO(raw))
    im.load()
    r.update(crop_file=path.name, crop_sha16=sha16(raw), crop_w=im.size[0], crop_h=im.size[1], _raw=raw, _im=im)
    check(r["crop_sha16"] == r["crop_sha16_signed"],
          "%s: crop file sha16 %s != the sha16 its signature was recorded over (%s) -- the signature is for "
          "other pixels" % (sid, r["crop_sha16"], r["crop_sha16_signed"]))
    check(bool(r["signature"]) and "?" not in r["signature"],
          "%s: signed text empty or carries an unresolved '?': %r" % (sid, r["signature"]))
    lc = (POP.get(sid) or {}).get("latin_context")
    if lc is None:
        r.update(ch2_state="absent", ch2="", ch2_why="not in hebrew_aperture_diag.build_set(include_sealed=True): "
                 "the loader hebrew_frontier_or.cells() uses has no latin_context for this span")
    else:
        masked = FOR._ctx(lc)
        r.update(ch2_state="present" if masked else "empty", ch2=masked, ch2_why="")
    if sid in POP and POP[sid].get("truth") is not None:
        r["loader_truth_agrees"] = (POP[sid]["truth"] == r["signature"])
    rows.append(r)
BY = {r["span_id"]: r for r in rows}
N_CH2 = {k: sum(1 for r in rows if r["ch2_state"] == k) for k in ("present", "empty", "absent")}

# ---- 4. before/after for the three round-2 rows
check(set(R1) == set(ROUND2) and set(R2) == set(ROUND2) and set(P3_IDS) == set(ROUND2),
      "round-2 rows differ from the expected three: r1 %s r2 %s truth %s" % (sorted(R1), sorted(R2), sorted(P3_IDS)))
BEFORE_AFTER = {}
for sid in ROUND2:
    cur = derive(R2[sid])
    check(cur == P3_BY[sid]["signature_full"],
          "%s: derive(r2 tiles) = %r but the signed row's signature_full = %r" % (sid, cur, P3_BY[sid]["signature_full"]))
    r1_sig = derive(R1[sid])
    r2_prior = derive(R2[sid], prior=True)
    tile_diffs = []
    for t in R2[sid]["tiles"]:
        t1 = next(x for x in R1[sid]["tiles"] if x["i"] == t["i"])
        if (t1["verdict"], t1["chose"]) != (t["verdict"], t["chose"]):
            tile_diffs.append({"i": t["i"], "shown": t["shown"], "r1": [t1["verdict"], t1["chose"]],
                               "r2": [t["verdict"], t["chose"]],
                               "r2_prior_fields": [t.get("prior_verdict"), t.get("prior_chose")]})
    BEFORE_AFTER[sid] = {"pass3_r1_signature_full": r1_sig, "r2_prior_fields_signature_full": r2_prior,
                         "current_signature_full": cur, "tiles_changed_r1_to_r2": tile_diffs,
                         "pixels_byte_identical": R1[sid]["crop_sha16"] == R2[sid]["crop_sha16"]}
    check(BEFORE_AFTER[sid]["pixels_byte_identical"], "%s: the re-signed crop sha16 differs between rounds" % sid)

# the adjudication ruling that voided the p493:n3 tile-4 pass-3 confirm
RULING = next((x for x in ADJ["rulings"] if x["span_id"] == "p493:n3" and x.get("tile_i") == 4), None)
check(RULING is not None and RULING["verdict"] == "keep" and "void" in RULING["basis"],
      "ADJUDICATION_pass3_r1 holds no 'keep' ruling voiding p493:n3 tile 4: %r" % (RULING,))

# ---- 5. set digest, geometry, counts, cost
DIGEST_LINES = sorted("%s %s" % (r["span_id"], r["crop_sha16"]) for r in rows)
SET_DIGEST = sha16("\n".join(DIGEST_LINES))
SRC_SHA = {p.name: sha16(open(str(p), "rb").read()) for p in SOURCES}
N_CALLS = len(rows) * len(CHANNELS) * len(MODELS)
check(N_CALLS == 180, "call count %d != 180" % N_CALLS)
HS = [r["crop_h"] for r in rows]
WS = [r["crop_w"] for r in rows]
N_SHORT = sum(1 for h in HS if h < SHORT_PX)


def mean_cost(path, model):
    v = [float(o["cost_usd"]) for o in _jl(path) if o.get("model") == model and o.get("cost_usd") is not None]
    return (sum(v) / len(v), len(v)) if v else (None, 0)


COST = {"basis": ("DERIVED from measured per-call cost_usd in earlier runs, not a quote: channel 1 from %s, "
                  "channel 2 from %s; mean over the rows of that model that carry a cost_usd" %
                  (F_COST_BARE.name, F_COST_TEXT.name)), "per_model": {}, "total_usd": None}
_tot, _unk = 0.0, False
for m in MODELS:
    b, nb = mean_cost(F_COST_BARE, m)
    t, nt = mean_cost(F_COST_TEXT, m)
    if b is None or t is None:
        _unk = True
        COST["per_model"][m] = {"unknown": True}
        continue
    est = len(rows) * (b + t)
    _tot += est
    COST["per_model"][m] = {"mean_usd_per_call_bare": round(b, 6), "n_costed_bare": nb,
                            "mean_usd_per_call_text": round(t, 6), "n_costed_text": nt,
                            "estimate_usd_for_%d_spans_both_channels" % len(rows): round(est, 4)}
COST["total_usd"] = None if _unk else round(_tot, 4)
COST["caveats"] = ("measured on the 19-20-span OLD population; these 45 crops differ in size and the text channel "
                   "here is masked note text for a minority of rows (see channel-2 counts), so channel 2 will "
                   "cost less than the measured text-channel call for the absent rows. A measurement of other "
                   "inputs, not a forecast." if not _unk else "cost UNKNOWN: no measured per-call cost found.")

# ---------------------------------------------------------------- the document
CSS = """
:root{--bg:#fff;--fg:#1a1a1a;--mut:#555;--line:#c8c8c8;--card:#f6f6f2;--warn:#8a2a00;--ok:#14532d;--chip:#e8e8e0}
@media (prefers-color-scheme: dark){:root{--bg:#161616;--fg:#e8e8e8;--mut:#a0a0a0;--line:#444;--card:#202020;--warn:#ffb084;--ok:#86efac;--chip:#2c2c2c}}
body{background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif;margin:0;padding:16px;max-width:1400px}
h1{font-size:20px;margin:.2em 0}h2{font-size:16px;margin:1.4em 0 .4em}
code,pre{font:12px/1.4 ui-monospace,Consolas,monospace}
pre{white-space:pre-wrap;word-break:break-all;margin:.2em 0}
section.row{border:1px solid var(--line);background:var(--card);margin:14px 0;padding:10px;border-radius:4px}
.views{display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap;margin:6px 0}
.views figure{margin:0}figcaption{font-size:11px;color:var(--mut)}
.px{background:#fff;border:1px solid var(--line);image-rendering:pixelated;display:block}
.x4{max-width:100%;overflow-x:auto}
.meta td{padding:1px 10px 1px 0;vertical-align:top}.meta td:first-child{color:var(--mut);white-space:nowrap}
.heb{font:20px/1.3 'Times New Roman',serif;direction:rtl;unicode-bidi:isolate}
.chip{display:inline-block;background:var(--chip);border:1px solid var(--line);padding:0 6px;margin:1px;border-radius:3px}
.chip[data-register=corrected]{border-color:var(--warn);color:var(--warn)}
.chip[data-register=sic]{border-color:var(--warn);color:var(--warn);font-weight:700}
.chip[data-register=confirmed]{border-color:var(--ok)}
.chip[data-register=not_in_crop]{opacity:.55}
.callout{border-left:4px solid var(--warn);padding:4px 10px;margin:6px 0}
.mut{color:var(--mut)}.warn{color:var(--warn)}
table.hdr td{padding:1px 10px 1px 0;vertical-align:top}
"""


def chip(t):
    shown, v, chose = t["shown"], t["verdict"], t.get("chose") or ""
    if t["kind"] == "gap":
        shown = "(space)"
    txt = {"confirmed": "%s printed" % shown, "corrected": "%s printed, read as %s" % (shown, chose or "?"),
           "sic": "%s printed (sic; expected %s)" % (shown, t.get("expected") or "?"),
           "not_in_crop": "%s not in crop" % shown}.get(v, "%s %s" % (shown, v))
    return '<span class="chip heb" data-register="%s" data-tile="%d">%s</span>' % (esc(v), t["i"], esc(txt))


def row_html(r):
    sid = r["span_id"]
    rid = "row-" + sid.replace(":", "-")
    x4 = upscale_nearest(r["_im"])
    L = ['<section class="row" id="%s" data-span="%s" data-sha16="%s">' % (rid, esc(sid), r["crop_sha16"]),
         "<h3 style='margin:0 0 4px'>%s <span class='mut'>file page %d, printed page %d, pass %d</span></h3>"
         % (esc(sid), r["page_file"], r["page_printed"], r["pass"]),
         '<div class="views"><figure><img class="px" src="%s" width="%d" height="%d" alt="%s native">'
         "<figcaption>native %dx%d px, no scaling</figcaption></figure>"
         % (data_uri_png(r["_raw"]), r["crop_w"], r["crop_h"], esc(sid), r["crop_w"], r["crop_h"]),
         '<figure class="x4"><img class="px" src="%s" width="%d" height="%d" alt="%s 4x nearest">'
         "<figcaption>4x nearest-neighbour (no smoothing)</figcaption></figure></div>"
         % (data_uri_png(x4), x4.width, x4.height, esc(sid)),
         '<table class="meta">',
         "<tr><td>crop</td><td><code>%s</code> &nbsp; sha16 <code>%s</code> &nbsp; %dx%d px%s</td></tr>"
         % (esc(r["crop_file"]), r["crop_sha16"], r["crop_w"], r["crop_h"],
            ' <span class="warn">(under %d px tall)</span>' % SHORT_PX if r["crop_h"] < SHORT_PX else ""),
         '<tr><td>signed text</td><td class="heb" dir="rtl">%s</td></tr>' % esc(r["signature"])]
    if r["signature_full"] and r["signature_full"] != r["signature"]:
        L.append("<tr><td>signature_full</td><td class='heb' dir='rtl'>%s</td></tr>" % esc(r["signature_full"]))
    L.append("<tr><td>disposition</td><td><code>%s</code></td></tr>" % esc(r["disposition"]))
    L.append("<tr><td>register</td><td>n_confirmed=<b>%s</b> n_corrected=<b>%s</b> n_sic=<b>%s</b> "
             "<span class='mut'>(%s)</span></td></tr>" % (esc(r["n_confirmed"]), esc(r["n_corrected"]),
                                                       esc(r["n_sic"]), esc(r["counts_source"])))
    L.append("<tr><td>signed_from</td><td><code>%s</code></td></tr>" % esc(r["signed_from"]))
    if r["box_fault"]:
        L.append("<tr><td>box_fault</td><td><code>%s</code></td></tr>" % esc(r["box_fault"]))
    if r["signed_partial_in_crop"]:
        L.append("<tr><td>signed_partial_in_crop</td><td>truth holds over the IN-CROP SUBSTRING ONLY; the signed "
                 "text above is that substring%s</td></tr>" %
                 ("; <code>in_crop_trimmed: %s</code>" % esc(r["in_crop_trimmed"]) if r["in_crop_trimmed"] else ""))
    if r["ch2_state"] == "absent":
        L.append("<tr><td>channel 2 string</td><td><b class='warn'>ABSENT</b> <span class='mut'>(not empty: %s)"
                 "</span><pre class=\"ch2\" data-state=\"absent\"></pre></td></tr>" % esc(r["ch2_why"]))
    else:
        L.append("<tr><td>channel 2 string</td><td><span class='mut'>%s; exact bytes that would be sent as the "
                 "text part:</span><pre class=\"ch2\" data-state=\"%s\">%s</pre></td></tr>"
                 % ("present" if r["ch2_state"] == "present" else "EMPTY (loaded, but nothing after masking)",
                    r["ch2_state"], esc(r["ch2"])))
    L.append("</table>")
    if sid in CALLED_OUT:
        L.append(called_out_html(sid))
    if sid in ROUND2:
        L.append(before_after_html(sid))
    else:
        L.append('<div class="mut" data-changed="no">Unchanged: this row was signed once and has not been re-signed.'
                 "</div>")
    L.append("</section>")
    return "\n".join(L)


def called_out_html(sid):
    tiles = R2[sid]["tiles"]
    if sid == "p493:n3":
        return (
            '<div class="callout" data-callout="p493:n3"><b>Register: this signature is mostly an EDITORIAL '
            "reading, not a pixel reading.</b> Signature <span class='heb'>%s</span>, 4 of 8 letters in the "
            "in-crop substring; <b>1 confirmed + 3 corrected</b>. Only the yod is a confirmed printed glyph; the "
            "other three are the signer's corrections (ayin to chet, resh to samekh, final-pe to resh). A scorer "
            "that treats this as pixel evidence is scoring an editorial reading.<br>%s<br>"
            "Tile 4 (the final letter) is the <b>restored resh</b>: the pass-3 round-1 confirm of the printed "
            "final-pe over byte-identical pixels was VOIDED by Chris's ruling (%s, tile 4 verdict "
            "<code>keep</code>: %s).</div>"
            % (esc(BY[sid]["signature"]), " ".join(chip(t) for t in tiles if t["verdict"] != "not_in_crop" and t["kind"] != "gap"),
               esc(F_ADJ.name), esc(RULING["authority"])))
    sic = BY[sid]["sic"][0]
    return (
        '<div class="callout" data-callout="p594:n0"><b>Register: PRINTED and EXPECTED are two different '
        "things.</b> The signature <span class='heb'>%s</span> is the PRINTED reading: 4 confirmed + <b>1 sic</b>; "
        "the printed he IS in the signature. The expected chet stands BESIDE it, not in it.<br>"
        "<span data-register='printed'>printed: <span class='heb'>%s</span> (tile %d)</span> &nbsp; "
        "<span data-register='expected'>expected: <span class='heb'>%s</span></span> &nbsp; "
        "reason <code>%s</code> &nbsp; basis <code>%s</code><br>%s<br>"
        "<code>expected_match</code> is a SEPARATE scored outcome from <code>exact</code>: a model that reads the "
        "printed he is <code>exact</code>; a model that reads the expected chet is <code>expected_match</code> "
        "and not <code>exact</code>.</div>"
        % (esc(BY[sid]["signature"]), esc(sic["printed"]), sic["tile_i"], esc(sic["expected"]),
           esc(sic["reason"]), esc(sic["basis"]), " ".join(chip(t) for t in tiles if t["verdict"] != "not_in_crop" and t["kind"] != "gap")))


def before_after_html(sid):
    b = BEFORE_AFTER[sid]
    td = "".join("<li>tile %d <span class='heb'>%s</span>: round 1 %s, now %s</li>"
                 % (d["i"], esc(d["shown"]), esc("/".join(map(str, d["r1"]))), esc("/".join(map(str, d["r2"]))))
                 for d in b["tiles_changed_r1_to_r2"]) or "<li>no tile verdict differs between round 1 and now</li>"
    return ('<div class="callout" data-before-after="%s"><b>Before / after</b> (re-signed over byte-identical '
            "pixels, same crop sha16): <table class='meta'>"
            "<tr><td>pass-3 round 1</td><td class='heb' dir='rtl'>%s</td></tr>"
            "<tr><td>prior as recorded in the round-2 export (prior_verdict / prior_chose)</td>"
            "<td class='heb' dir='rtl'>%s</td></tr>"
            "<tr><td>current</td><td class='heb' dir='rtl'>%s</td></tr></table>"
            "<ul>%s</ul></div>"
            % (esc(sid), esc(b["pass3_r1_signature_full"]), esc(b["r2_prior_fields_signature_full"]),
               esc(b["current_signature_full"]), td))


def header_html():
    tb = ['<table class="hdr">']

    def kv(k, v):
        tb.append("<tr><td class='mut'>%s</td><td>%s</td></tr>" % (esc(k), v))
    kv("page convention", "ALL PAGE NUMBERS ARE FILE PAGES (printed = file - %d). Every span id here is a file page." % PRINTED_OFFSET)
    kv("status", "NOTHING IS SENT. No network call of any kind was made to produce this sheet.")
    kv("policy", esc(POLICY))
    kv("approval is for", "the PIXELS in each row, not the text beside them. The signed text is shown because "
       "these spans are already signed; this is not the signing sheet.")
    kv("spans", "%d unique (%s)" % (len(rows), esc(DERIVATION)))
    kv("set digest", "<code>%s</code>" % SET_DIGEST)
    kv("digest rule", esc(DIGEST_RULE))
    kv("crop directory", "<code>%s</code> (class (b) regenerable, gitignored; nothing was re-cut)" % esc(CROP_DIR_NAME))
    kv("truth sources (sha16)", "<br>".join("<code>%s</code> %s" % (esc(k), v) for k, v in SRC_SHA.items()
                                            if k in (F_PASS1.name, F_PASS1_TILES.name, F_PASS2.name,
                                                     F_PASS3R2.name, F_R1_EXPORT.name, F_R2_EXPORT.name,
                                                     F_ADJ.name)))
    kv("models", ", ".join("<code>%s</code>" % esc(m) for m in MODELS))
    kv("channel 1 (bare)", "the A2 span crop alone")
    kv("channel 2 (text)", "the same A2 span crop PLUS the Latin note text, every Hebrew run masked to U+2022 by "
       "<code>hebrew_frontier_or._ctx</code>. Note TEXT only: no note-box crop.")
    kv("channel-2 availability", "%d present, %d empty, %d ABSENT (of %d). ABSENT = the loader the frontier run "
       "uses has no latin_context for the span; EMPTY = loaded but nothing after masking."
       % (N_CH2["present"], N_CH2["empty"], N_CH2["absent"], len(rows)))
    kv("standing rules", "<ul>" + "".join("<li>%s</li>" % esc(x) for x in RULES) + "</ul>")
    kv("scoring", "per channel: <code>exact</code> / <code>nikud</code> / <code>wrong</code> / "
       "<code>expected_match</code>, plus the agreement-and-wrong rate. Predicted first.")
    kv("call count", "%d spans x %d channels x %d models = <b>%d</b>" % (len(rows), len(CHANNELS), len(MODELS), N_CALLS))
    kv("cost", esc(json.dumps(COST, ensure_ascii=False)))
    kv("crop geometry", "width %d to %d px, height %d to %d px; %d crop(s) under %d px tall"
       % (min(WS), max(WS), min(HS), max(HS), N_SHORT, SHORT_PX))
    kv("changed rows", "Only the 3 round-2 rows (%s) were re-signed; each shows before/after below. No other row "
       "changed, and each of the other %d says so." % (", ".join(ROUND2), len(rows) - len(ROUND2)))
    kv("git at start", esc(json.dumps({k: {"head": v["git_head"], "dirty": v["git_dirty"]} for k, v in GIT_START.items()})))
    tb.append("</table>")
    return "\n".join(tb)


def end_header_html(git_end, prov, why):
    return ('<h2>Run record</h2><table class="hdr"><tr><td class="mut">git at end</td><td>%s</td></tr>'
            '<tr><td class="mut">verdict</td><td><b class="%s">%s</b> %s</td></tr></table>'
            % (esc(json.dumps({k: {"head": v["git_head"], "dirty": v["git_dirty"]} for k, v in git_end.items()})),
               "warn" if prov else "", "PROVISIONAL" if prov else "clean", esc(why)))


# the end-of-run git state is taken immediately before the document is composed (the outputs themselves are
# written afterwards and would otherwise dirty the very tree being described)
GIT_END = {k: git_state(v) for k, v in REPOS.items()}
PROV = any(provisional(GIT_START[k], GIT_END[k]) for k in REPOS)
WHY = []
for k in REPOS:
    if not GIT_START[k]["clean"] or not GIT_END[k]["clean"]:
        WHY.append("%s is not clean (%s)" % (k, json.dumps(GIT_END[k]["git_dirty"], ensure_ascii=False)[:300]))
    if GIT_START[k] != GIT_END[k]:
        WHY.append("%s moved between start and end" % k)
WHY_TXT = "; ".join(WHY) if WHY else "both repos clean and identical at both ends"

parts = ['<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
         "<title>Scoring run contact sheet, %d spans, digest %s</title><style>%s</style>" % (len(rows), SET_DIGEST, CSS),
         "<h1>Scoring-run contact sheet: %d spans, %d calls, nothing sent</h1>" % (len(rows), N_CALLS),
         header_html(), end_header_html(GIT_END, PROV, WHY_TXT),
         "<h2>Index</h2><p>%s</p>" % " ".join("<a href='#row-%s'>%s</a>" % (s.replace(":", "-"), s) for s in ALL_IDS)]
parts.extend(row_html(r) for r in rows)
DOC = "\n".join(parts) + "\n"

# ---------------------------------------------------------------- born-checks over the emitted bytes
sidecar = {
    "kind": "contact_sheet_scoring45", "page_convention": "ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88)",
    "nothing_sent": True, "set_digest": SET_DIGEST, "digest_rule": DIGEST_RULE, "digest_lines": DIGEST_LINES,
    "derivation": DERIVATION, "policy": POLICY, "standing_rules": list(RULES), "models": list(MODELS),
    "channels": {"bare": "A2 span crop alone", "text": "A2 span crop plus Latin note text, Hebrew runs masked to U+2022"},
    "n_calls": N_CALLS, "cost": COST, "truth_sources_sha16": SRC_SHA,
    "channel2_counts": N_CH2, "crop_w_range": [min(WS), max(WS)], "crop_h_range": [min(HS), max(HS)],
    "n_crops_under_%dpx_tall" % SHORT_PX: N_SHORT, "git_start": GIT_START, "git_end": GIT_END,
    "provisional": PROV, "provisional_reason": WHY_TXT, "before_after": BEFORE_AFTER,
    "rows": [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows],
}
SIDE = json.dumps(sidecar, ensure_ascii=False, indent=1, sort_keys=True) + "\n"

# 1. no note-box path anywhere
NB_RX = re.compile(r"A1_notebox|note_box")
check(NB_RX.search("C:/x/p1_n1_A1_notebox.png") and NB_RX.search("note_box"), "note-box detector does not fire on its probes")
check(len(re.findall(r"p\d+_n\d+_A2_spanbox\.png", DOC)) == N_EXPECT,
      "liveness: expected %d crop file names in the document, found %d"
      % (N_EXPECT, len(re.findall(r"p\d+_n\d+_A2_spanbox\.png", DOC))))
check(not NB_RX.search(DOC), "a note-box path appears in the document: %r" % NB_RX.search(DOC))
check(not NB_RX.search(SIDE), "a note-box path appears in the sidecar")

# 2. no key
KEY_RX = re.compile(r"sk-or-")
check(KEY_RX.search("sk-or-v1-probe"), "key detector does not fire on its probe")
check(not KEY_RX.search(DOC) and not KEY_RX.search(SIDE), "an sk-or- substring appears in the document or sidecar")
_env = os.environ.get("OPENROUTER_API_KEY", "")
check(not _env or (_env not in DOC and _env not in SIDE), "the OPENROUTER_API_KEY value appears in an output")

# 3. all 45 crop sha16 in the document
n_rows_in_doc = len(re.findall(r'<section class="row" id="row-[^"]+" data-span="[^"]+" data-sha16="([0-9a-f]{16})"', DOC))
check(n_rows_in_doc == N_EXPECT, "liveness: %d row elements in the document, expected %d" % (n_rows_in_doc, N_EXPECT))
n_sha_present = sum(1 for r in rows if r["crop_sha16"] in DOC)
check(n_sha_present == N_EXPECT, "only %d of %d crop sha16 values appear in the document" % (n_sha_present, N_EXPECT))
check(len(set(r["crop_sha16"] for r in rows)) == N_EXPECT, "crop sha16 values are not 45 distinct values")

# 4. channel-2 strings free of Hebrew
check(HEB_RX.search(PROBE_HEB), "Hebrew detector does not fire on its probe")
CH2 = re.findall(r'<pre class="ch2" data-state="(\w+)">(.*?)</pre>', DOC, flags=re.S)
check(len(CH2) == N_EXPECT, "liveness: %d channel-2 elements, expected %d" % (len(CH2), N_EXPECT))
ST = {k: sum(1 for s, _t in CH2 if s == k) for k in ("present", "empty", "absent")}
check(ST == N_CH2, "channel-2 states in the document %r != derived %r" % (ST, N_CH2))
n_nonempty = sum(1 for s, t in CH2 if html.unescape(t).strip())
check(n_nonempty == N_CH2["present"] and n_nonempty >= 1, "non-empty channel-2 count %d vs present %d" % (n_nonempty, N_CH2["present"]))
check(all(not HEB_RX.search(html.unescape(t)) for _s, t in CH2), "a channel-2 string carries a Hebrew codepoint")
n_masked = sum(1 for _s, t in CH2 if u"\u2022" in html.unescape(t))
check(n_masked >= 1, "liveness: no channel-2 string carries the U+2022 mask, so the masking was never exercised")
check(all(t == "" for s, t in CH2 if s == "absent"), "an absent row carries channel-2 text")

# 5. register inside the called-out rows' OWN elements
def row_el(sid):
    m = re.search(r'<section class="row" id="row-%s".*?</section>' % re.escape(sid.replace(":", "-")), DOC, flags=re.S)
    return m.group(0) if m else ""


E493, E594 = row_el("p493:n3"), row_el("p594:n0")
check(E493 and E594 and E493 != E594, "liveness: could not extract the two called-out row elements")
check(E493.count('data-register="corrected"') == 3 and E493.count('data-register="confirmed"') == 1
      and 'data-register="sic"' not in E493 and "n_confirmed=<b>1</b>" in E493 and "n_corrected=<b>3</b>" in E493,
      "p493:n3 row element does not carry 1 confirmed + 3 corrected as tile chips")
check("restored resh" in E493 and F_ADJ.name in E493, "p493:n3 row element does not name the restored resh and the ruling")
check(E594.count('data-register="sic"') == 1 and E594.count('data-register="confirmed"') == 4
      and "n_sic=<b>1</b>" in E594 and "n_confirmed=<b>4</b>" in E594
      and "Exod 31:5 / fabrefactione" in E594 and "evidence_grounded" in E594
      and "data-register='printed'" in E594 and "data-register='expected'" in E594 and "expected_match" in E594
      and "in_crop_trimmed: trailing separator" in E594,
      "p594:n0 row element does not carry 4 confirmed + 1 sic, printed beside expected, reason, basis, expected_match")
n_other_with_tile_chips = sum(1 for r in rows if r["span_id"] not in CALLED_OUT and 'data-register="sic"' in row_el(r["span_id"]))
check(n_other_with_tile_chips == 0, "a row other than the two called-out rows carries a sic chip")
for r in rows:
    check("n_confirmed=<b>%s</b>" % r["n_confirmed"] in row_el(r["span_id"]),
          "%s: its own row element does not carry its n_confirmed" % r["span_id"])
n_unchanged = len(re.findall(r'data-changed="no"', DOC))
n_ba = len(re.findall(r'data-before-after="', DOC))
check(n_ba == 3 and n_unchanged == N_EXPECT - 3, "before/after elements %d, unchanged elements %d" % (n_ba, n_unchanged))
check(all(row_el(s).count('data-before-after="%s"' % s) == 1 for s in ROUND2), "a round-2 row lacks its own before/after block")
check(DOC.count("FILE PAGES") >= 1 and "FILE PAGES" in SIDE, "the file-page convention is missing from an output")

# the .md summary (a class (a) record)
OUT_STEM = "CONTACT_SHEET_scoring45_%s" % SET_DIGEST
MD = "\n".join([
    "# Scoring-run contact sheet, %d spans (digest `%s`)" % (len(rows), SET_DIGEST), "",
    "ALL PAGE NUMBERS ARE FILE PAGES (printed = file - %d)." % PRINTED_OFFSET, "",
    "**Nothing was sent.** No network call of any kind. The sheet is `%s.html` (class (b), regenerable, not "
    "committed); this file and `%s.json` are the class (a) records." % (OUT_STEM, OUT_STEM), "",
    "Policy: %s" % POLICY, "",
    "- Spans: %d (%s)" % (len(rows), DERIVATION),
    "- Set digest rule: %s" % DIGEST_RULE,
    "- Models: %s" % ", ".join(MODELS),
    "- Channel 1 bare = A2 span crop alone; channel 2 = crop plus Latin note text with Hebrew masked to U+2022. "
    "No note-box crop leaves the network.",
    "- Calls: %d spans x %d channels x %d models = %d" % (len(rows), len(CHANNELS), len(MODELS), N_CALLS),
    "- Cost: %s" % (("derived estimate USD %s; %s" % (COST["total_usd"], COST["basis"])) if COST["total_usd"] is not None
                    else "UNKNOWN (no measured per-call cost found)"),
    "- Crop size: width %d-%d px, height %d-%d px; %d under %d px tall" % (min(WS), max(WS), min(HS), max(HS), N_SHORT, SHORT_PX),
    "- Channel 2 string: %d present, %d empty, %d ABSENT. Absent means the loader the frontier run uses "
    "(`hebrew_aperture_diag.build_set`) has no latin_context for the span." % (N_CH2["present"], N_CH2["empty"], N_CH2["absent"]),
    "- Called-out registers: p493:n3 (1 confirmed + 3 corrected; editorial reading; tile 4 restored resh) and p594:n0 "
    "(4 confirmed + 1 sic; printed he in the signature, expected chet beside it; `expected_match` separate from `exact`).",
    "- Changed rows: only %s (re-signed over byte-identical pixels); no other row changed." % ", ".join(ROUND2),
    "- Git start: %s" % json.dumps({k: [v["git_head"][:8], v["git_dirty"].get("state")] for k, v in GIT_START.items()}),
    "- Git end: %s" % json.dumps({k: [v["git_head"][:8], v["git_dirty"].get("state")] for k, v in GIT_END.items()}),
    "- Verdict: %s. %s" % ("PROVISIONAL" if PROV else "clean", WHY_TXT), "",
    "## What this does NOT solve", "",
    "It does not say any crop is legible; Chris reading the pixels does. It does not supply a note text for the "
    "%d ABSENT rows, so channel 2 as built cannot send them. It does not fix the scoring rule for the two "
    "editorial-register rows." % N_CH2["absent"], "",
    "## Rows", "", "| span (file page) | printed | pass | px | crop sha16 | signed text | disposition | ch2 |",
    "|---|---|---|---|---|---|---|---|"] +
    ["| %s | %d | %d | %dx%d | `%s` | %s | %s | %s |" % (r["span_id"], r["page_printed"], r["pass"], r["crop_w"],
                                                           r["crop_h"], r["crop_sha16"], r["signature"], r["disposition"],
                                                           r["ch2_state"]) for r in rows]) + "\n"

# EXPECTED_CHECKS is pinned to the count observed on the first full run (3 per row in the build loop, plus the
# file-level and born-checks above); a check added or removed changes it and this line then refuses to pass.
EXPECTED_CHECKS = 217
if CHECKS != EXPECTED_CHECKS:
    raise AssertionError("ran %d checks, expected %d" % (CHECKS, EXPECTED_CHECKS))

# ---------------------------------------------------------------- write (the only side effect)
for name, text in ((OUT_STEM + ".html", DOC), (OUT_STEM + ".json", SIDE), (OUT_STEM + ".md", MD)):
    with io.open(str(HAD.DATA / name), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
print("set digest", SET_DIGEST)
print("crop px: width %d-%d, height %d-%d; under %d tall: %d" % (min(WS), max(WS), min(HS), max(HS), SHORT_PX, N_SHORT))
print("calls", N_CALLS, "cost", COST["total_usd"])
print("ch2", N_CH2, "masked-with-bullet", n_masked)
print("loader_truth_agrees", {r["span_id"]: r["loader_truth_agrees"] for r in rows if "loader_truth_agrees" in r})
print("born-check liveness: note-box probe ok; crop names %d; key probe ok; rows %d, sha present %d; ch2 elements %d "
      "(nonempty %d, masked %d); p493 corrected chips %d confirmed %d; p594 sic %d confirmed %d; before/after %d "
      "unchanged %d" % (N_EXPECT, n_rows_in_doc, n_sha_present, len(CH2), n_nonempty, n_masked,
                        E493.count('data-register="corrected"'), E493.count('data-register="confirmed"'),
                        E594.count('data-register="sic"'), E594.count('data-register="confirmed"'), n_ba, n_unchanged))
print("provisional", PROV, "-", WHY_TXT)
print("checks %d / %d" % (CHECKS, EXPECTED_CHECKS))
print("wrote", OUT_STEM)
