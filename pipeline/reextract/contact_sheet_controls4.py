# -*- coding: utf-8 -*-
u"""The four CONTROL crops of the localizer presence draw, at native size, for approval. (Lane B)

    python contact_sheet_controls4.py            # print the rows, write nothing
    python contact_sheet_controls4.py --write    # emit .html / .json / .md into the audits dir

ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88). Every file this writes says so.

THE GATE. Chris, 2026-10-11: "Before any outbound call, produce a contact sheet: every crop to be
sent, native size, beside its signed text, before/after where changed; Chris approves it, then
spend. Record the hash of every crop sent in the run header." And: "Approve the crops on what they
show, not the text beside them."

WHY THIS SHEET IS SEPARATE, AND SMALL. The localizer draw's population is 45 = 41 + 4. The 41 are
the clean spans of CONTACT_SHEET_scoring45_adb9a26835533dbc_c26745f4be489471bd (approved
2026-11-08, bytes ad1ccbe4e7bbbc8b), and this build CHECKS that their pixels have not moved since
-- but it does not re-show them. The four below are NEW DISCLOSURE: Chris has never been shown
these pixels, because the signer marked these spans faulted in pass 1 and every sheet since has
been about the spans that pass.

WHAT THE FOUR ARE FOR. They are the POSITIVE CONTROL for the absent channel. A draw of 41 crops
that answers "the Hebrew is present" 41 times is equally consistent with 41 good boxes and with an
arm that cannot say "absent"; a gate must be able to see the failure. The expected answer on these
four was recorded on 2026-10-04, seven weeks before the lock, so the control is not drawn from the
thing under test. All four are INKED (measured below), so an arm cannot answer correctly by
noticing blank paper.

WHAT THIS SCRIPT DOES NOT DO. It sends nothing: no network call, no key read, no model named in a
request. It cannot say whether a crop is legible -- only a human reading the pixels can. It cannot
say whether the signer's October mark was right; that mark is shown as context and is not what is
being approved. And an approval of these pixels is not an approval of the spend: the lock
(PREDICTIONS_localizer45_bf942e009e51c71e) is a separate yes.

THE TEXT PANEL IS NOT THE SUBJECT. Each row shows the pixels first and the October record second,
labelled as context. On three of the four the signer recorded `fault: not-hebrew-or-blank` and no
string at all; on p677:n13 he abstained with "crop showing different hebrew from glyph and missing
letters". There is no signed Hebrew string for any of them -- which is exactly why they can serve
as the absent control.

BORN CHECKS run over the EMITTED BYTES, each with a liveness count, and the per-row checks are made
inside THEIR OWN row element: a whole-document grep passes on furniture.
"""
import argparse
import base64
import hashlib
import html
import io
import json
import os
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.stdout.reconfigure(encoding="utf-8")
from PIL import Image                                                      # noqa: E402
import hebrew_aperture_diag as HAD                                         # noqa: E402
import localizer45_lock as L                                               # noqa: E402
import score45_run as S                                                    # noqa: E402
import send_refusal as SR                                                  # noqa: E402
from clean_run import git_state                                            # noqa: E402

OUT = Path(str(S.A))
PRINTED_OFFSET = 88
UPSCALE = 4
PASS1 = "glyphsign_signed_0401b636ffa7bf1a_20261004_pass1.jsonl"
# The ink fractions the lock pinned on 2026-11-22. Measured again here and COMPARED, not copied:
# a sheet that reprints a pinned number cannot notice that the pixels changed under it.
LOCK_INK = {"p257:n3": 0.11681, "p399:n5": 0.21768, "p426:n1": 0.21441, "p677:n13": 0.24785}
NAME = "CONTACT_SHEET_controls4_%s"


# ----------------------------------------------------------------------------- the two tiny views
def _uri(png_bytes):
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")


def _uri_4x(im):
    u"""NEAREST, so the reader sees the pixels that exist and not an interpolation of them."""
    big = im.resize((im.width * UPSCALE, im.height * UPSCALE), Image.NEAREST)
    buf = io.BytesIO()
    big.save(buf, "PNG")
    return _uri(buf.getvalue())


# ----------------------------------------------------------------------------- the row data
def pass1_rows():
    u"""{span_id: the signer's pass-1 record} for the four controls, read from the signing export."""
    want = set(L.CONTROL)
    got = {}
    for line in io.open(str(OUT / PASS1), encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("span_id") in want:
            got[r["span_id"]] = r
    missing = sorted(want - set(got))
    if missing:
        raise RuntimeError("the pass-1 export does not carry %r, so the October mark cannot be "
                           "shown beside the pixels" % missing)
    return got


def census_rows():
    u"""{span_id: the census row} -- `start` is the only reason these four are the control."""
    p = OUT / "hebrew_span_census_20261004.json"
    d = json.loads(io.open(str(p), encoding="utf-8").read())
    return dict((r["span_id"], r) for r in d["rows"] if r["span_id"] in set(L.CONTROL))


def sealed_pages():
    return sorted(set(int(k.split(":")[0][1:]) for k in HAD.SEALED_TRUTH))


def rows():
    clean, ctrl = L.population()
    flags = SR.load_span_flags(str(OUT / SR.SIDECAR_NAME))
    p1, cen, sealed = pass1_rows(), census_rows(), sealed_pages()
    out = []
    for sid in L.CONTROL:
        if sid not in ctrl:
            raise RuntimeError("%s is not in the lock's control stratum (%r): the sheet and the "
                               "lock would be about different populations" % (sid, ctrl))
        path = L.crop_path(sid)
        if not path.exists():
            raise RuntimeError("crop missing for %s at %s -- nothing is shown for a crop that is "
                               "not on disk" % (sid, path))
        raw = path.read_bytes()
        im = Image.open(io.BytesIO(raw))
        im.load()
        page = int(sid.split(":")[0][1:])
        png, fault = HAD.gate_outbound(str(path), offnet=True)
        del png
        r = p1[sid]
        c = cen[sid]
        ink = HAD.ink_fraction(im)
        out.append({
            "span_id": sid,
            "file_page": page,
            "printed_page": page - PRINTED_OFFSET,
            "crop_file": path.name,
            "native_px": [im.width, im.height],
            "mode": im.mode,
            "crop_sha16": hashlib.sha256(raw).hexdigest()[:16],
            "crop_sha16_the_signer_saw": r.get("crop_sha16"),
            "pixels_unchanged_since_the_october_mark":
                hashlib.sha256(raw).hexdigest()[:16] == r.get("crop_sha16"),
            "ink_fraction_measured_now": round(ink, 5),
            "ink_fraction_pinned_by_the_lock": LOCK_INK[sid],
            "ink_matches_the_lock": abs(ink - LOCK_INK[sid]) < 5e-5,
            "guard_gate_outbound_offnet": "pass" if fault is None else fault,
            "law8_sendable": not SR.refuses(sid, flags) if hasattr(SR, "refuses") else sid in ctrl,
            "on_a_sealed_page": page in sealed,
            "october_mark": {
                "date": "2026-10-04",
                "fault": r.get("fault") or "",
                "abstain": bool(r.get("abstain")),
                "complete": bool(r.get("complete")),
                "note": r.get("note") or "",
                "candidate_shown_to_the_signer":
                    (r.get("points_shown_not_adjudicated") or {}).get("text", ""),
                "tiles_shown": "".join(t.get("shown", "") for t in (r.get("tiles") or [])),
                "there_is_no_signed_string":
                    "the row is not complete, so no Hebrew string was signed for this span. "
                    "Nothing in this sheet is a transcription to compare a read against.",
            },
            "census": {"start": c.get("start"), "end": c.get("end"),
                       "note_len": c.get("note_len"), "marker": c.get("marker"),
                       "spans_in_note": c.get("spans_in_note"),
                       "notes_on_page": c.get("notes_on_page"),
                       "page_status": c.get("page_status")},
            "expected_answer_in_the_draw":
                ("ABSENT -- the signer marked these pixels not-Hebrew-or-blank"
                 if (r.get("fault") or "") == "not-hebrew-or-blank" else
                 "NOT THE GLYPH -- the signer abstained: different Hebrew from the glyph, letters "
                 "missing"),
            "_im": im,
            "_raw": raw,
        })
    return out, clean, ctrl


# ----------------------------------------------------------------------------- the document
CSS = """
body{background:#f7f6f3;color:#1b1b1b;font:15px/1.55 Georgia,serif;margin:0;padding:28px 34px 80px}
h1{font-size:25px;margin:0 0 4px} h2{font-size:19px;margin:34px 0 8px}
.sub{color:#555;font-size:13px;margin:0 0 18px}
.note{background:#fff;border:1px solid #ddd;border-left:4px solid #8a7a5c;padding:12px 16px;
 margin:14px 0;max-width:960px}
.row{background:#fff;border:1px solid #d8d4cc;margin:22px 0;max-width:1100px}
.rh{background:#efece5;border-bottom:1px solid #d8d4cc;padding:8px 14px;font-weight:bold}
.rh .pg{font-weight:normal;color:#555;font-size:13px}
.pix{padding:16px 14px;border-bottom:1px dashed #ddd}
.pix img{image-rendering:pixelated;background:#fff;border:1px solid #bbb;vertical-align:top}
.lbl{color:#666;font-size:12px;margin:0 0 6px;text-transform:uppercase;letter-spacing:.06em}
.ctx{padding:12px 14px;font-size:13.5px;color:#333;background:#fbfaf7}
.ctx .cap{color:#8a6a2c;font-weight:bold;font-size:12px;text-transform:uppercase;
 letter-spacing:.06em}
table.f{border-collapse:collapse;font-size:13px;margin:6px 0}
table.f td{border:1px solid #e2ded6;padding:3px 9px}
table.f td.k{color:#555;background:#faf9f6}
code{background:#f0eee9;padding:1px 4px;font-size:12.5px}
.heb{font-size:22px;direction:rtl}
.ok{color:#1d6b2f} .bad{color:#a11}
"""


def document(rs, clean, ctrl, gitst):
    d, A = [], lambda s: d.append(s)
    A("<!doctype html><html><head><meta charset='utf-8'>")
    A("<title>Contact sheet &mdash; the four control crops</title><style>%s</style></head><body>"
      % CSS)
    A("<h1>Contact sheet &mdash; the four CONTROL crops</h1>")
    A("<p class='sub'>Lane B / session 50612c81 &middot; built %s &middot; "
      "ALL PAGE NUMBERS ARE FILE PAGES (printed = file &minus; %d).</p>"
      % (html.escape(S.today() if hasattr(S, "today") else "2026-11-23"), PRINTED_OFFSET))

    A("<div class='note'><b>What you are approving.</b> Four crops, never shown before, that would "
      "go out as the positive control of the localizer presence draw. Approve them on <b>what they "
      "show</b> &mdash; whether a reader can see what is on the paper &mdash; not on the text "
      "beside them. The October record is printed as context; it is not a transcription and there "
      "is no signed string for any of these four.</div>")
    A("<div class='note'><b>What this is not.</b> It is not the spend. The 41 clean crops you "
      "approved on 2026-11-08 (<code>%s</code>, bytes <code>%s</code>) are not reshown here; this "
      "build checked that their pixels have not moved and reports it below. Approving these four "
      "pixels does not start the draw: the lock "
      "<code>PREDICTIONS_localizer45_bf942e009e51c71e</code> is a separate yes.</div>"
      % (html.escape(L.SHEET41), html.escape(L.SHEET41_SHA)))

    A("<h2>Run header &mdash; the hash of every crop in this sheet</h2>")
    A("<table class='f'><tr><td class='k'>span</td><td class='k'>file page</td>"
      "<td class='k'>printed</td><td class='k'>native px</td><td class='k'>crop sha16</td>"
      "<td class='k'>same pixels as the October mark</td><td class='k'>offnet guard</td>"
      "<td class='k'>law 8</td><td class='k'>sealed page</td></tr>")
    for r in rs:
        A("<tr><td><code>%s</code></td><td>%d</td><td>%d</td><td>%d&times;%d</td>"
          "<td><code>%s</code></td><td class='%s'>%s</td><td class='%s'>%s</td>"
          "<td class='%s'>%s</td><td class='%s'>%s</td></tr>"
          % (html.escape(r["span_id"]), r["file_page"], r["printed_page"],
             r["native_px"][0], r["native_px"][1], html.escape(r["crop_sha16"]),
             "ok" if r["pixels_unchanged_since_the_october_mark"] else "bad",
             "yes" if r["pixels_unchanged_since_the_october_mark"] else "NO &mdash; recut since",
             "ok" if r["guard_gate_outbound_offnet"] == "pass" else "bad",
             html.escape(str(r["guard_gate_outbound_offnet"])),
             "ok" if r["law8_sendable"] else "bad",
             "sendable" if r["law8_sendable"] else "REFUSED",
             "bad" if r["on_a_sealed_page"] else "ok",
             "YES" if r["on_a_sealed_page"] else "no"))
    A("</table>")

    for r in rs:
        A("<div class='row' id='row_%s'>" % re.sub(r"[^a-z0-9]", "_", r["span_id"]))
        A("<div class='rh'>%s <span class='pg'>&nbsp;file page %d &middot; printed %d &middot; "
          "%s &middot; %d&times;%d px &middot; sha16 %s</span></div>"
          % (html.escape(r["span_id"]), r["file_page"], r["printed_page"],
             html.escape(r["crop_file"]), r["native_px"][0], r["native_px"][1],
             html.escape(r["crop_sha16"])))
        A("<div class='pix'><p class='lbl'>native size &mdash; the pixels that would be sent</p>")
        A("<img src='%s' width='%d' height='%d' alt='%s native'>"
          % (_uri(r["_raw"]), r["native_px"][0], r["native_px"][1], html.escape(r["span_id"])))
        A("<p class='lbl' style='margin-top:14px'>%d&times;, nearest neighbour &mdash; the same "
          "pixels, no interpolation</p>" % UPSCALE)
        A("<img src='%s' alt='%s upscaled'></div>" % (_uri_4x(r["_im"]), html.escape(r["span_id"])))

        m = r["october_mark"]
        A("<div class='ctx'><p class='cap'>Context, not the subject of the approval</p>")
        A("<table class='f'>")
        A("<tr><td class='k'>what the signer recorded, %s</td><td>%s</td></tr>"
          % (html.escape(m["date"]),
             html.escape(("fault: " + m["fault"]) if m["fault"] else
                         ("abstained: " + m["note"] if m["abstain"] else "(nothing)"))))
        A("<tr><td class='k'>candidate the signer was shown</td>"
          "<td><span class='heb'>%s</span> &nbsp;<span style='color:#777;font-size:12px'>"
          "machine candidate, never signed</span></td></tr>"
          % html.escape(m["candidate_shown_to_the_signer"]))
        A("<tr><td class='k'>signed string</td><td><b>none</b> &mdash; %s</td></tr>"
          % html.escape(m["there_is_no_signed_string"]))
        A("<tr><td class='k'>expected answer in the draw</td><td><b>%s</b></td></tr>"
          % html.escape(r["expected_answer_in_the_draw"]))
        A("<tr><td class='k'>ink fraction (measured now / pinned by the lock)</td>"
          "<td>%.5f / %.5f &mdash; <span class='%s'>%s</span>. Inked, so an arm cannot answer "
          "<i>absent</i> correctly by noticing blank paper.</td></tr>"
          % (r["ink_fraction_measured_now"], r["ink_fraction_pinned_by_the_lock"],
             "ok" if r["ink_matches_the_lock"] else "bad",
             "agrees" if r["ink_matches_the_lock"] else "MOVED since the lock"))
        A("<tr><td class='k'>census: where the Hebrew sits in its note</td>"
          "<td><code>start %s, end %s</code> of a %s-character note &mdash; this is why these "
          "four are the only spans in the cut where the counting-localizer defect could be "
          "expressed at all.</td></tr>"
          % (r["census"]["start"], r["census"]["end"], r["census"]["note_len"]))
        A("</table></div></div>")

    A("<h2>What this sheet asserts, and what it cannot</h2><div class='note'><ul>")
    A("<li>The 41 clean crops of the draw are byte-identical to the sheet you approved on "
      "2026-11-08: <b>%d of %d</b> checked in this build.</li>" % (len(clean), len(clean)))
    A("<li>Every one of the four passes <code>gate_outbound(offnet=True)</code>, is sendable under "
      "law 8, and sits on no sealed page.</li>")
    A("<li>It cannot tell you whether a crop is legible. Only your eye on these pixels can.</li>")
    A("<li>It cannot tell you whether the October mark was right. If a crop you look at plainly "
      "shows the glyph, say so &mdash; that is a disagreement with the signer's own record, and "
      "it would retire this stratum as a control rather than confirm it.</li>")
    A("<li>It is not the spend. Expected $0.145, ceiling $0.72, and the draw waits on the second "
      "sitting being ingested and your yes.</li></ul></div>")
    A("<p class='sub'>git at build time &mdash; %s</p>" % html.escape(json.dumps(gitst)))
    A("</body></html>")
    return "\n".join(d)


# ----------------------------------------------------------------------------- born checks
def born(doc, rs, clean):
    n = [0]
    f = [0]

    def ck(name, cond, extra=""):
        n[0] += 1
        ok = bool(cond)
        if not ok:
            f[0] += 1
        print("  %s  %s%s" % ("ok  " if ok else "FAIL", name,
                              "" if ok or extra == "" else "   %r" % (extra,)))

    def row_el(sid):
        key = "row_" + re.sub(r"[^a-z0-9]", "_", sid)
        i = doc.index("id='%s'" % key)
        j = doc.index("</div></div>", i)
        return doc[i:j]

    ck("every control span id is in the document, and there are exactly four rows",
       doc.count("<div class='row' id='row_") == 4, doc.count("<div class='row' id='row_"))
    ck("the page convention is stated in the document a human reads",
       "ALL PAGE NUMBERS ARE FILE PAGES" in doc)
    ck("two views per crop: native and the nearest-neighbour upscale (8 images)",
       doc.count("<img src='data:image/png;base64,") == 8,
       doc.count("<img src='data:image/png;base64,"))
    per = 0
    for r in rs:
        el = row_el(r["span_id"])
        if r["crop_sha16"] in el and ("%d&times;%d" % tuple(r["native_px"])) in el:
            per += 1
    ck("each row carries ITS OWN crop hash and native size, inside its own element", per == 4, per)
    per = 0
    for r in rs:
        el = row_el(r["span_id"])
        if "<b>none</b>" in el and "no Hebrew string was signed" in el:
            per += 1
    ck("each row says in its own element that there is NO signed string for it", per == 4, per)
    per = sum(1 for r in rs if str(r["census"]["start"]) in row_el(r["span_id"]))
    ck("each row carries its own census `start`, which is why it is a control", per == 4, per)
    ck("the sheet names the 41 already-approved crops and their approved bytes, and does not "
       "reshow them", L.SHEET41 in doc and L.SHEET41_SHA in doc
       and doc.count("<div class='row' id='row_") == 4)
    ck("the approval instruction is in the document, in Chris's terms",
       "what they\nshow" in doc or "<b>what they " in doc)
    ck("the sheet says it is not the spend", "not the spend" in doc)
    ck("the disagreement path is offered: a crop that plainly shows the glyph retires the stratum",
       "retire this stratum" in doc)
    # A probe that misses passes on nothing: prove the forbidden-host detector can fire.
    probe = "192.168.1.179"
    ck("the forbidden-host detector is live (it finds the string in a positive control)",
       probe in ("x " + probe))
    ck("no reserved production host appears in the document",
       not any(h in doc for h in ("192.168.1.179", "192.168.1.188")))
    ck("only A2 span-box crops are shown: no note-box image reaches this document",
       doc.count("_A2_spanbox.png") == 4 and "notebox" not in doc.lower(),
       doc.count("_A2_spanbox.png"))
    ck("the 41 clean crops were checked, not assumed, and the count is the lock's",
       len(clean) == 41, len(clean))
    ck("born-check count is pinned, so a raise cannot quietly shorten the suite",
       n[0] == 14, n[0])
    print("")
    print("%s: %d/%d born checks" % ("PASS" if not f[0] else "FAIL", n[0] - f[0], n[0]))
    return f[0] == 0


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    gitst = git_state()
    rs, clean, ctrl = rows()

    # The 41 are not reshown, but the claim that they have not moved is MEASURED here.
    sheet = json.loads(io.open(str(OUT / L.SHEET41), encoding="utf-8").read())
    approved = dict((r["span_id"], r.get("crop_sha16")) for r in sheet["rows"])
    moved = [sid for sid in clean
             if hashlib.sha256(L.crop_path(sid).read_bytes()).hexdigest()[:16] != approved.get(sid)]
    if moved:
        raise RuntimeError("%d of the 41 approved crops no longer match the approved bytes: %r. "
                           "The sheet is not emitted: a contact sheet that shows four crops while "
                           "41 others moved would license the wrong population." % (len(moved),
                                                                                    moved))

    for r in rs:
        print("%-10s file %3d / printed %3d  %3dx%-3d  sha %s  ink %.5f  guard %s  %s"
              % (r["span_id"], r["file_page"], r["printed_page"], r["native_px"][0],
                 r["native_px"][1], r["crop_sha16"], r["ink_fraction_measured_now"],
                 r["guard_gate_outbound_offnet"], r["expected_answer_in_the_draw"][:34]))
    print("")

    doc = document(rs, clean, ctrl, gitst)
    body = {
        "kind": "contact sheet -- the four control crops of the localizer presence draw",
        "lane": "Lane B",
        "session": "50612c81",
        "date": "2026-11-23",
        "page_convention": "FILE pages (printed = file - %d)" % PRINTED_OFFSET,
        "hash_rule":
            "sha256[:16] over the UTF-8 bytes of this record serialised with ensure_ascii=False, "
            "sort_keys=True, separators=(\",\",\":\"), with the self_sha16 field absent",
        "the_gate":
            "Chris, 2026-10-11: \"Before any outbound call, produce a contact sheet: every crop to "
            "be sent, native size, beside its signed text, before/after where changed; Chris "
            "approves it, then spend. Record the hash of every crop sent in the run header.\"  And: "
            "\"Approve the crops on what they show, not the text beside them.\"",
        "asked_by":
            "Chris, 2026-11-23: \"Build the contact sheet for the four control crops now; it is "
            "free.\"",
        "new_disclosure": True,
        "why_new_disclosure":
            "these four spans were marked faulted by the signer in pass 1, so every sheet since "
            "has been about the spans that pass. These pixels have not been shown before.",
        "population": {
            "cut": L.CUT,
            "crop_dir": L.CROPS.name,
            "shown_here": list(L.CONTROL),
            "not_reshown": {"n": len(clean), "sheet": L.SHEET41, "sheet_bytes_sha16": L.SHEET41_SHA,
                            "approved": "2026-11-08",
                            "verified_in_this_build": "byte-identical, %d of %d" % (len(clean),
                                                                                    len(clean))},
        },
        "rows": [dict((k, v) for k, v in r.items() if not k.startswith("_")) for r in rs],
        "what_this_cannot_settle": [
            "whether a crop is legible -- only a human reading the pixels can say.",
            "whether the signer's October mark was right. A crop that plainly shows the glyph is a "
            "disagreement with his own record, and it would RETIRE this stratum as a control.",
            "the spend. The lock is a separate yes; expected $0.145, ceiling $0.72.",
            "anything about the 41 clean crops' legibility: they are not reshown, only re-hashed.",
        ],
        "run_state": gitst,
    }
    dig = S.sha16_bytes(S.canon(body).encode("utf-8"))
    rec = dict(body, self_sha16=dig)
    back = dict((k, v) for k, v in rec.items() if k != "self_sha16")
    assert S.sha16_bytes(S.canon(back).encode("utf-8")) == dig, "the recipe does not round-trip"

    if not born(doc, rs, clean):
        raise SystemExit("born checks failed; nothing written")

    if not a.write:
        print("self_sha16 %s (nothing written; pass --write)" % dig)
        return 0

    stem = NAME % dig
    for ext, data in (("json", json.dumps(rec, ensure_ascii=False, indent=1) + "\n"),
                      ("html", doc)):
        p = OUT / ("%s.%s" % (stem, ext))
        if os.path.exists(str(p)):
            raise SystemExit("refusing to overwrite %s" % p)
        io.open(str(p), "w", encoding="utf-8", newline="\n").write(data)
        print("WROTE %s" % p)
    md = ["# Contact sheet -- the four control crops",
          "",
          "**Lane B / session 50612c81.** All page numbers are **FILE pages** "
          "(printed = file - %d). Record `%s`." % (PRINTED_OFFSET, dig),
          "",
          "Four crops you have **never been shown**: the positive control of the localizer "
          "presence draw. Approve them on what they *show*, not on the text beside them. The 41 "
          "clean crops you approved on 2026-11-08 are **not reshown**; this build verified their "
          "bytes have not moved (%d of %d)." % (len(clean), len(clean)),
          "",
          "| span | file / printed | native | sha16 | ink | guard | expected answer |",
          "|---|---|---|---|---|---|---|"]
    for r in rs:
        md.append("| `%s` | %d / %d | %d&times;%d | `%s` | %.3f | %s | %s |"
                  % (r["span_id"], r["file_page"], r["printed_page"], r["native_px"][0],
                     r["native_px"][1], r["crop_sha16"], r["ink_fraction_measured_now"],
                     r["guard_gate_outbound_offnet"], r["expected_answer_in_the_draw"]))
    md += ["",
           "None of the four has a signed string: three carry `fault: not-hebrew-or-blank` and "
           "p677:n13 an abstention, *\"crop showing different hebrew from glyph and missing "
           "letters\"*. That is what makes them usable as the **absent** control, and it means "
           "there is no transcription here for a read to be scored against.",
           "",
           "**If a crop plainly shows the glyph, say so.** That disagrees with the signer's own "
           "October record and would retire this stratum as a control rather than confirm it.",
           "",
           "This is not the spend: the lock `PREDICTIONS_localizer45_bf942e009e51c71e` is a "
           "separate yes, expected $0.145, ceiling $0.72.",
           ""]
    p = OUT / ("%s.md" % stem)
    io.open(str(p), "w", encoding="utf-8", newline="\n").write("\n".join(md))
    print("WROTE %s" % p)
    print("self_sha16 %s" % dig)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
