# -*- coding: utf-8 -*-
u"""blank45.py -- the blank-crop control for the scoring-45 run: cut, lock, contact sheet, selftest.

ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).  Every report built on this module says so.

WHAT THIS CONTROL IS FOR.  Run 6a2292bdb14d3c43 measured four exact-match rates against signed
Hebrew -- opus bare 32/41, opus context 31/40, qwen bare 25/41, qwen context 22/40 -- and reported
abstain 0 in all four cells, 162 of 162 calls.  Not one of those four numbers has a FLOOR.  A rate
is evidence about reading only against the rate the same arm reaches with the pixels taken away,
and this lane has a measured precedent for that mattering: a zero-pixel crop once returned the
EXACT signed string, so no output-side check can catch the fabrication.  78% against a floor of 0
and 78% against a floor of 20 are different findings and the run reported neither.

The control changes exactly one thing: the image bytes.  Same arms, same prompt, same channels,
same population, same scorer, same basis, same denominators.  Each span's crop is replaced by a
uniform-255 PNG of that span's own width, height and mode, so everything the arm sees but the ink
is held constant and the comparison is paired per span.

The two cells mean different things and are never pooled:

  blank + bare     prompt and a white rectangle.  Nothing else.  Any Hebrew is produced from the
                   arm's priors alone; any `exact` is a fabrication that happened to land, and it
                   is recorded as a fabrication witness, not scored.

  blank + context  prompt, a white rectangle, and the Latin note text with every Hebrew run masked
                   to U+2022 (GATE 8 proves no Hebrew is in it).  An `exact` here means the Latin
                   ANSWERED the question -- "reptile, V. L. Pagninus, Montanus" implies a word
                   without showing one.  This is the floor the off-vs-on channel comparison was
                   never measured against, and the reason the control is owed.

THE GATE THIS CONTROL HAD TO GET PAST, and how.  `hebrew_aperture_diag.b64_gated` is the only
sanctioned encoder and it routes through `gate_outbound` -> `crop_fault`, which returns
`blank:uniform=255` and REFUSES.  That guard exists precisely to stop a blank crop reaching a paid
arm, and it is right.  Two bad ways out were available: relax it, or write a second encoder.  A
second encoder is the worse of the two -- `b64_gated`'s whole argument is that an arm cannot reach
the wire without encoding, so one step cannot be skipped by forgetting, and a second path destroys
that property permanently for every arm.

So the single encoder is PARAMETERIZED, and the parameter is not a boolean.  `allow_fault` takes
the exact fault string it licenses and the crop's fault must EQUAL it.  A boolean would license the
whole `blank:` family; a string licenses one named instance.  And because equality is required in
both directions, a call that passes `allow_fault="blank:uniform=255"` is STRICTER than the default
path, not looser: it refuses an inked crop, a crop blank at 254, and a crop with no fault at all.
The control therefore cannot send a real crop by a bug, which is the failure mode that matters.
The offnet aperture checks -- A2-span-box suffix, no in-memory image -- sit ABOVE the licensed
clause and are not licensable by it.  No note-box crop becomes sendable by any value of it.

WHAT THIS CONTROL CANNOT DO.  Named here, before it runs.

  * It cannot show that a correct read on real pixels WAS read from the pixels.  It can only name
    the spans where a correct answer is available WITHOUT them.  Those spans stop being evidence
    about reading; the rest are not thereby proven to be evidence about reading.
  * In the context cell it cannot separate "the arm remembers this verse" from "the Latin implies
    the word".  Only the bare cell separates those, and only to the extent the bare cell is clean.
  * One draw per item at temperature 0.  A per-span floor hit is therefore a single observation,
    not a stable property of that span, and the per-span list is labelled provisional for that
    reason.  The CELL rates are what this run is for.
  * It shares the prompt and the scorer with the run it floors, so it cannot see a defect in
    either.  A scorer that calls the wrong thing `exact` calls it that in both.
  * The four law-8 refusals stay refused, for the same reason and by the same gate.  The floor is
    measured on the population the effect was measured on, which is the point, but it is not the
    population the predictions of the scored run were registered over (45/44) -- see that run's
    `denominator_note`.

Subcommands.  None of them touches the network; `selftest` and `lock` write nothing outside the
audits directory, and `cut`/`sheet` write nothing anywhere else.

  cut        write the blank PNGs and the content-addressed manifest.  Deterministic: a re-cut
             either produces byte-identical files or refuses, so a second cut cannot quietly
             replace the evidence of what the first one sent.
  lock       write the registered predictions and the decision rule.  Run BEFORE the control.
  sheet      the contact sheet: every crop to be sent at native size, beside the real crop it
             replaces and beside the signed text.  Chris approves it, then the run may spend.
  selftest   the `allow_fault` clause, both directions, and the cut's invariants.  Writes nothing.

Interpreter: C:/Users/cnogr/git/goat-yard-archive/.venv/Scripts/python.exe, PYTHONIOENCODING=utf-8,
cwd = this directory.
"""
import argparse
import base64
import hashlib
import io
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import hebrew_aperture_diag as diag  # noqa: E402
from PIL import Image  # noqa: E402

A = Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits")
SHEET = A / "CONTACT_SHEET_scoring45_adb9a26835533dbc_c26745f4be489471bd.json"
SCORED = A / "SCORE45_6a2292bdb14d3c43.json"
CROPDIR = A / "truthset74_crops_0401b636ffa7bf1a"
SET_DIGEST = "adb9a26835533dbc"
SCORED_RUN = "6a2292bdb14d3c43"

# The scored run's own payload identity: sha16 over its sorted 162 predicted request hashes and its
# 45 crop hashes, read out of the committed result file.  The sender asserts this is UNCHANGED in
# normal mode and CHANGED in blank mode.  Its lineage is the committed artifact, not this module --
# a verifier that calls the producer agrees by construction.
SCORED_PAYLOAD_DIGEST = "870bf99e65725534"

BLANKDIR = A / ("blank45_crops_%s" % SET_DIGEST)
BLANK_FAULT = "blank:uniform=255"
BLANK_LEVEL = 255

PAGE_CONVENTION = "ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88)"

CHECKS = [0]


def chk(cond, msg):
    CHECKS[0] += 1
    if not cond:
        raise AssertionError(msg)


def canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha16(b):
    return hashlib.sha256(b).hexdigest()[:16]


def digest_of(obj):
    """Content address of a record: sha16 over canonical UTF-8 bytes, `ensure_ascii=False`."""
    return sha16(canon(obj).encode("utf-8"))


# --------------------------------------------------------------------------------- the population
def load_rows():
    """The 45 sheet rows, and the 4 the law-8 send gate refused, read off the committed run.

    The refused set is taken from the run this controls rather than recomputed, because the claim
    being floored is about the spans THAT RUN READ.  The sender recomputes law 8 from the sidecar at
    run time and aborts on a count mismatch, so a refusal set that has since moved cannot be sent
    under this lock -- it aborts, which is correct, and the lock is re-registered."""
    sheet = json.loads(SHEET.read_text(encoding="utf-8"))
    chk(sheet["set_digest"] == SET_DIGEST, "sheet set_digest %s" % sheet["set_digest"])
    rows = sheet["rows"]
    chk(len(rows) == 45, "sheet rows %d != 45" % len(rows))
    scored = json.loads(SCORED.read_text(encoding="utf-8"))["header"]
    ref = scored["refusal"]
    chk(ref["n_population"] == 45 and ref["n"] == 41 and ref["n_refused"] == 4,
        "the scored run's refusal accounting moved: %s" % canon(ref))
    refused = {k: tuple(v) for k, v in ref["refused"].items()}
    ids = {r["span_id"] for r in rows}
    for s in refused:
        chk(s in ids, "refused span %s is not in the sheet" % s)
    chk(len(ids) == 45, "duplicate span_id in the sheet")
    return rows, refused


def _real(row):
    """(bytes, PIL image, sha16) of the real crop, re-read from the file every time."""
    p = CROPDIR / row["crop_file"]
    chk(p.exists(), "missing real crop %s" % p.name)
    raw = p.read_bytes()
    return raw, Image.open(io.BytesIO(raw)), sha16(raw)


def _blank_bytes(im):
    """A uniform-255 PNG with the real crop's size and mode.  Nothing else about it is chosen."""
    out = io.BytesIO()
    Image.new(im.mode, im.size, color=_white(im.mode)).save(out, format="PNG")
    return out.getvalue()


def _white(mode):
    if mode in ("L", "1"):
        return BLANK_LEVEL
    if mode == "RGB":
        return (BLANK_LEVEL, BLANK_LEVEL, BLANK_LEVEL)
    if mode == "RGBA":
        return (BLANK_LEVEL, BLANK_LEVEL, BLANK_LEVEL, 255)
    raise AssertionError("no white defined for PIL mode %r" % mode)


# ------------------------------------------------------------------------------------------- cut
def cut(write=True):
    rows, refused = load_rows()
    BLANKDIR.mkdir(parents=True, exist_ok=True)
    real_shas = set()
    out = []
    for row in sorted(rows, key=lambda r: (r["page_file"], r["span_id"])):
        sid = row["span_id"]
        raw, im, rsha = _real(row)
        chk(rsha == row["crop_sha16"],
            "%s: real crop sha %s != the sheet's %s" % (sid, rsha, row["crop_sha16"]))
        chk(im.size == (row["crop_w"], row["crop_h"]),
            "%s: real crop %s != sheet w/h %s" % (sid, im.size, (row["crop_w"], row["crop_h"])))
        real_shas.add(rsha)

        bb = _blank_bytes(im)
        dst = BLANKDIR / row["crop_file"]
        # Deterministic, so a re-cut has exactly two honest outcomes: identical, or refuse.  An
        # audit does not overwrite its own evidence of what it sent.
        if dst.exists():
            old = dst.read_bytes()
            chk(old == bb, "%s: %s exists with different bytes -- refusing to clobber the cut "
                           "this control was approved on" % (sid, dst.name))
        elif write:
            dst.write_bytes(bb)
        else:
            chk(False, "%s: %s does not exist. `lock`, `sheet` and `selftest` VERIFY the cut "
                       "on disk rather than recompute it, so run `blank45.py cut` first."
                       % (sid, dst.name))
        bsha = sha16(dst.read_bytes())
        chk(bsha == sha16(bb), "%s: the blank on disk is not the blank this rule derives" % sid)

        bim = Image.open(io.BytesIO(bb))
        chk(bim.size == im.size, "%s: blank size %s != real %s" % (sid, bim.size, im.size))
        chk(bim.mode == im.mode, "%s: blank mode %s != real %s" % (sid, bim.mode, im.mode))
        chk(bsha != rsha, "%s: the blank and the real crop hash the same" % sid)

        # The blankness is read back through the lane's OWN outbound predicate, on the bytes on
        # disk -- not asserted from the fact that this function wrote white.  Its job is to catch a
        # cut that wrote the real crop, and it can only do that by looking at the file.
        _b, bfault = diag.gate_outbound(dst, offnet=True)
        chk(bfault == BLANK_FAULT,
            "%s: the blank crop's fault is %r, not %r" % (sid, bfault, BLANK_FAULT))
        _r, rfault = diag.gate_outbound(CROPDIR / row["crop_file"], offnet=True)
        if sid not in refused:
            chk(rfault is None, "%s: a crop the scored run SENT fails the outbound gate now: %s"
                                % (sid, rfault))

        out.append({
            "span_id": sid, "page_file": row["page_file"], "page_printed": row["page_printed"],
            "crop_file": row["crop_file"], "w": im.size[0], "h": im.size[1], "mode": im.mode,
            "real_sha16": rsha, "blank_sha16": bsha,
            "blank_fault": bfault, "real_fault": rfault,
            "signature": row["signature"], "signature_full": row["signature_full"],
            "ch2_state": row["ch2_state"], "ch2": row["ch2"],
            "sendable": sid not in refused, "refused_by": list(refused.get(sid, ())),
        })

    for r in out:
        chk(r["blank_sha16"] not in real_shas,
            "%s: a blank crop hashes as one of the 45 real crops" % r["span_id"])
    chk(len({r["blank_sha16"] for r in out}) == len({(r["w"], r["h"], r["mode"]) for r in out}),
        "blank hashes do not partition by (w, h, mode) -- a blank carries something besides shape")

    n_send = sum(1 for r in out if r["sendable"])
    n_ctx = sum(1 for r in out if r["sendable"] and r["ch2_state"] == "present")
    chk(n_send == 41, "sendable %d != 41" % n_send)
    chk(n_ctx == 40, "sendable with channel 2 %d != 40" % n_ctx)

    body = {
        "kind": "blank45_cut", "page_convention": PAGE_CONVENTION,
        "set_digest": SET_DIGEST, "floors_run": SCORED_RUN,
        "blank_dir": str(BLANKDIR), "crop_dir": str(CROPDIR),
        "rule": ("one uniform-%d PNG per span, at that span's own width, height and PIL mode.  "
                 "Nothing but the ink is changed, so the comparison is paired per span."
                 % BLANK_LEVEL),
        "blankness_witness": ("hebrew_aperture_diag.gate_outbound on the bytes on disk returns "
                              "%r for all %d" % (BLANK_FAULT, len(out))),
        "n": len(out), "n_sendable": n_send, "n_sendable_with_channel2": n_ctx,
        "calls": 2 * (n_send + n_ctx),
        "rows": out,
    }
    body["digest"] = digest_of({k: v for k, v in body.items() if k != "digest"})
    p = A / ("BLANK45_CUT_%s.json" % body["digest"])
    if write:
        p.write_text(canon(body) + "\n", encoding="utf-8")
    print("%s  %d rows, %d sendable, %d calls, dir %s"
          % (p.name, len(out), n_send, body["calls"], BLANKDIR.name))
    return body, p


# ------------------------------------------------------------------------------------------- lock
REGISTERED = {
    # Registered BEFORE the run, over the SAME denominators the scored run used, so a delta here is
    # comparable -- unlike the scored run's own predictions, which were registered over 45/44 and
    # read 41/40.  Each is a range with both ends, so each can miss in either direction.
    "anthropic/claude-opus-5.5|bare": {"n": 41, "abstain_min": 30, "exact_max": 2},
    "anthropic/claude-opus-5.5|context": {"n": 40, "abstain_max": 25, "exact_min": 4, "exact_max": 16},
    "qwen/qwen3.7-plus|bare": {"n": 41, "abstain_min": 20, "exact_max": 3},
    "qwen/qwen3.7-plus|context": {"n": 40, "abstain_max": 25, "exact_min": 2, "exact_max": 14},
}

SIGNS = [
    ("D1", "exact(blank, context) > exact(blank, bare), for BOTH arms.  The Latin licenses a guess "
           "that a white rectangle alone does not."),
    ("D2", "abstain(blank) > 0 in at least one cell.  On real pixels these arms abstained 0 times "
           "in 162 calls; if a white rectangle also draws zero abstentions, the arms have no "
           "`nothing here` channel at all and every blank answer is a fabrication."),
    ("D3", "exact(blank, context) >= 2/40 in at least one arm -- the context floor is not zero."),
    ("D4", "at least 3 spans score exact in blank+context on BOTH arms.  Those spans' context-"
           "channel `exact` in run %s is not evidence about reading." % SCORED_RUN),
]

RULE = [
    "1.  ABSTENTION IS READ FIRST, per cell, before any accuracy number is computed or looked at.  "
    "A cell whose abstention is 0 has an exact-rate that is a fabrication rate, and is reported in "
    "those words.",

    "2.  An `exact` in blank+bare is NOT a scoring event.  It is a fabrication witness: recorded by "
    "span id, and that (span, arm) is struck from the bare channel's read-evidence.  A read is "
    "evidence only about a guarded crop, and this crop has no ink to be evidence about.",

    "3.  CITATION RULE.  After this control, each of the four rates of run %s may be cited only "
    "beside its floor, as `measured/n (floor f/n)`.  The control does not re-score that run, does "
    "not touch a stored row, and does not change a signed verdict." % SCORED_RUN,

    "4.  The per-span output is `no_pixel_recoverable`: the (span, arm, channel) triples where a "
    "blank crop scored exact or nikud_only.  Published as a list, labelled PROVISIONAL at one draw "
    "per item.",

    "5.  A missed prediction is reported as a miss, with the measured number beside the registered "
    "one and the same denominator.  No range is widened after the fact and no cell is re-run.",

    "6.  RUN-LEVEL FAULT.  A 429 or 4 consecutive dead items aborts the run and writes nothing.  "
    "Errors stay in the denominator as `error`; a run that aborted is never spliced into one that "
    "did not.",

    "7.  The cut is content-addressed and its digest is in this lock.  The blanks are not re-cut "
    "after looking, and the cut refuses to overwrite itself.",

    "8.  `nikud_only` from a blank crop is counted in `answered_without_pixels` and NOT in the "
    "exact floor.  Nikud-only is a third state, not a wrong answer and not an exact one.",
]


def lock(write=True):
    body, cutp = cut(write=False)
    obj = {
        "kind": "blank45_predictions", "page_convention": PAGE_CONVENTION,
        "registered_on": "2026-11-08", "registered_by": "Lane B, before the run",
        "floors_run": SCORED_RUN, "set_digest": SET_DIGEST,
        "cut_digest": body["digest"],
        "scored_payload_digest": SCORED_PAYLOAD_DIGEST,
        "population": {
            "n_spans": 45, "n_sendable": body["n_sendable"],
            "n_sendable_with_channel2": body["n_sendable_with_channel2"],
            "calls": body["calls"],
            "refused": sorted(r["span_id"] for r in body["rows"] if not r["sendable"]),
            "refusal_law": "law 8 / ruling B(4), recomputed by the sender; unchanged by this control",
            "bare_only": [r["span_id"] for r in body["rows"] if r["ch2_state"] != "present"],
        },
        "ablation": {
            "changed": "the image bytes, and nothing else",
            "held_constant": ["arms", "prompt", "channel-2 text", "reasoning", "max_tokens",
                              "temperature", "population", "scorer", "basis", "denominators"],
            "images_per_call": 1,
            "images_per_call_basis": ("hebrew_frontier_or._body builds one image_url and one text "
                                     "part, so there is no second image channel to leak through.  "
                                     "The law `a blank channel is not an absent input` was written "
                                     "about a harness that sent two; this one does not."),
            "channel2_not_ablated": ("deliberate.  The masked Latin is the input whose contribution "
                                     "the context floor measures."),
        },
        "basis": {
            "primary": "the row's in-crop `signature`",
            "secondary": "`signature_full`, reported beside it and never instead of it",
            "classes": ["exact", "nikud_only", "wrong", "abstain", "error"],
            "scorer": "score45_run's local scorer, unchanged, so the classes are the registered ones",
        },
        "measured_on_real_pixels": {
            "anthropic/claude-opus-5.5|bare": "32/41 exact, 0 abstain",
            "anthropic/claude-opus-5.5|context": "31/40 exact, 0 abstain",
            "qwen/qwen3.7-plus|bare": "25/41 exact, 0 abstain",
            "qwen/qwen3.7-plus|context": "22/40 exact, 3 nikud_only, 0 abstain",
        },
        "registered_cells": REGISTERED,
        "registered_signs": [{"id": i, "claim": c} for i, c in SIGNS],
        "decision_rule": RULE,
        "cannot_do": [
            "show that a correct read on real pixels WAS read from the pixels",
            "separate `the arm remembers the verse` from `the Latin implies the word` in the "
            "context cell",
            "make a per-span floor hit a stable property of that span: one draw, temperature 0",
            "see a defect in the prompt or the scorer, which it shares with the run it floors",
            "say anything about the 4 law-8 refusals, which stay refused",
        ],
        "gate_override": {
            "gate": "hebrew_aperture_diag.gate_outbound via b64_gated",
            "fault_licensed": BLANK_FAULT,
            "mechanism": ("the single encoder is parameterized with `allow_fault`, which takes the "
                          "exact fault string and requires EQUALITY, so the licensed call is "
                          "stricter than the default path and cannot send an inked crop.  No "
                          "second encoder exists.  The offnet aperture checks sit above the "
                          "licensed clause and are not licensable by it."),
            "authority": "PENDING -- Chris approves the contact sheet before the run spends",
        },
        "cost_estimate_usd": 0.27,
        "cost_basis": "run %s: 162 calls, $0.262841 measured, same pixel count and same texts"
                      % SCORED_RUN,
    }
    obj["prediction_sha16"] = digest_of({k: v for k, v in obj.items() if k != "prediction_sha16"})
    p = A / ("PREDICTIONS_blank45_%s.json" % obj["prediction_sha16"])
    chk(not p.exists() or p.read_text(encoding="utf-8") == canon(obj) + "\n",
        "%s exists with different content -- a lock is not re-registered in place" % p.name)
    if write:
        p.write_text(canon(obj) + "\n", encoding="utf-8")
    print("%s  cut %s  %d calls  est $%.2f"
          % (p.name, obj["cut_digest"], obj["population"]["calls"], obj["cost_estimate_usd"]))
    return obj, p


# ------------------------------------------------------------------------------------ contact sheet
def _img(raw, w, h, extra=""):
    return ('<img src="data:image/png;base64,%s" width="%d" height="%d" class="crop%s">'
            % (base64.b64encode(raw).decode(), w, h, extra))


def sheet(write=True):
    body, _ = cut(write=False)
    lk, lkp = lock(write=False)
    rows = [r for r in body["rows"] if r["sendable"]]
    chk(len(rows) == 41, "contact sheet rows %d != 41" % len(rows))

    h = []
    h.append(u"<!doctype html><meta charset='utf-8'>")
    h.append(u"<title>blank45 contact sheet</title>")
    h.append(u"<style>body{font:14px/1.5 Georgia,serif;margin:28px;max-width:1100px}"
             u"table{border-collapse:collapse;width:100%}"
             u"td,th{border-top:1px solid #ccc;padding:10px 8px;vertical-align:top}"
             u".crop{image-rendering:pixelated;display:block}"
             u".blank{outline:2px dashed #c00}"
             u".heb{font-size:20px;direction:rtl;unicode-bidi:bidi-override}"
             u"code{font:12px Consolas,monospace}"
             u".lat{color:#444;font-size:13px}</style>")
    h.append(u"<h1>blank45 &mdash; the crops this control would send</h1>")
    h.append(u"<p><b>Lane B / session 50612c81.</b> 2026-11-08. %s.</p>" % PAGE_CONVENTION)
    h.append(u"<p>Each row: the crop run <code>%s</code> <b>sent</b> (left) and the crop this "
             u"control <b>would send</b> in its place (right, red dashed outline), both at native "
             u"size, beside the signed text. Everything but the ink is held constant &mdash; same "
             u"width, height and PIL mode. The whole point is that the right-hand image carries "
             u"nothing: approve these on <b>what they show</b>, not on the text beside them.</p>"
             % SCORED_RUN)
    h.append(u"<p><b>%d crops, %d calls</b> (2 arms &times; (%d bare + %d context)); estimated "
             u"<b>$%.2f</b>. Lock <code>%s</code>, cut <code>%s</code>. The 4 law-8 refusals are "
             u"absent from this sheet and from the run.</p>"
             % (len(rows), body["calls"], body["n_sendable"], body["n_sendable_with_channel2"],
                lk["cost_estimate_usd"], lk["prediction_sha16"], body["digest"]))
    h.append(u"<table><tr><th>span</th><th>sent</th><th>would send</th><th>signed / Latin</th></tr>")
    for r in rows:
        raw, _im, _s = _real({"crop_file": r["crop_file"], "span_id": r["span_id"]})
        # The bytes ON DISK, which are the bytes that will be posted -- not a re-derivation.
        # A contact sheet showing a picture of something other than what is sent is not a
        # contact sheet, and the hash is asserted here so it cannot drift into one.
        bb = (BLANKDIR / r["crop_file"]).read_bytes()
        chk(sha16(bb) == r["blank_sha16"],
            "%s: the sheet would show bytes that hash %s, not the manifest's %s"
            % (r["span_id"], sha16(bb), r["blank_sha16"]))
        lat = (u"<div class='lat'>%s</div>" % _esc(r["ch2"])) if r["ch2_state"] == "present" \
            else u"<div class='lat'><i>no channel-2 text &mdash; bare only</i></div>"
        h.append(u"<tr><td><b>%s</b><br>file %d / printed %d<br><code>%d&times;%d %s</code>"
                 u"<br><code>real %s</code><br><code>blank %s</code></td>"
                 u"<td>%s</td><td>%s</td><td><div class='heb'>%s</div>%s</td></tr>"
                 % (r["span_id"], r["page_file"], r["page_printed"], r["w"], r["h"], r["mode"],
                    r["real_sha16"], r["blank_sha16"],
                    _img(raw, r["w"], r["h"]), _img(bb, r["w"], r["h"], " blank"),
                    _esc(r["signature"] or u""), lat))
    h.append(u"</table>")
    html = u"\n".join(h) + u"\n"

    obj = {
        "kind": "blank45_contact_sheet", "page_convention": PAGE_CONVENTION,
        "set_digest": SET_DIGEST, "floors_run": SCORED_RUN,
        "cut_digest": body["digest"], "prediction_sha16": lk["prediction_sha16"],
        "n_crops": len(rows), "calls": body["calls"],
        "cost_estimate_usd": lk["cost_estimate_usd"],
        "approval": {"by": None, "on": None,
                     "what": "the 41 blank crops at native size, beside the crops they replace"},
        "crop_sha16_to_send": {r["span_id"]: r["blank_sha16"] for r in rows},
        "crop_sha16_replaced": {r["span_id"]: r["real_sha16"] for r in rows},
        "rows": [{k: r[k] for k in ("span_id", "page_file", "page_printed", "crop_file", "w", "h",
                                    "mode", "real_sha16", "blank_sha16", "blank_fault",
                                    "signature", "ch2_state")} for r in rows],
    }
    obj["digest"] = digest_of({k: v for k, v in obj.items() if k != "digest"})
    jp = A / ("CONTACT_SHEET_blank45_%s.json" % obj["digest"])
    hp = A / ("CONTACT_SHEET_blank45_%s.html" % obj["digest"])
    if write:
        jp.write_text(canon(obj) + "\n", encoding="utf-8")
        hp.write_text(html, encoding="utf-8")
    print("%s" % hp)
    print("%s  %d crops, sheet digest %s" % (jp.name, len(rows), obj["digest"]))
    return obj, hp


def _esc(t):
    return (t or u"").replace(u"&", u"&amp;").replace(u"<", u"&lt;").replace(u">", u"&gt;")


# --------------------------------------------------------------------------------------- selftest
def selftest():
    rows, refused = load_rows()
    row = sorted(rows, key=lambda r: r["span_id"])[0]
    raw, im, rsha = _real(row)
    bb = _blank_bytes(im)

    # Scratch files go outside the audits tree: the gate's aperture check is on the FILENAME,
    # so the location is free, and an audit directory is not a place to leave test fixtures.
    td = Path(tempfile.mkdtemp(prefix="blank45_selftest_"))
    tmp = td / "_selftest_A2_spanbox.png"
    tmp.write_bytes(bb)
    real = CROPDIR / row["crop_file"]
    try:
        # The clause refuses by default.  This is the guard the control had to get past, and it is
        # asserted here rather than assumed, because the whole design rests on it still holding.
        _b, f = diag.gate_outbound(tmp, offnet=True)
        chk(f == BLANK_FAULT, "default path does not refuse a blank crop: %r" % f)
        try:
            diag.b64_gated(tmp, what="selftest", offnet=True)
            chk(False, "b64_gated encoded a blank crop with no licence")
        except diag.CropRefused:
            chk(True, "b64_gated refuses a blank crop by default")

        # Licensed by the EXACT fault: permitted.
        _b, f = diag.gate_outbound(tmp, offnet=True, allow_fault=BLANK_FAULT)
        chk(f is None, "the exact licensed fault was still refused: %r" % f)
        chk(len(diag.b64_gated(tmp, what="selftest", offnet=True, allow_fault=BLANK_FAULT)) > 0,
            "b64_gated did not encode under the exact licence")

        # STRICTER, not looser, in three directions.  This is why `allow_fault` is a string and not
        # a boolean: a boolean would license the whole `blank:` family and, worse, would license a
        # crop with no fault at all -- i.e. the real crop.
        _b, f = diag.gate_outbound(real, offnet=True, allow_fault=BLANK_FAULT)
        chk(f is not None and "allow_fault" in f,
            "a licence for a blank fault let an INKED crop through: %r" % f)
        _b, f = diag.gate_outbound(tmp, offnet=True, allow_fault="blank:uniform=254")
        chk(f is not None and "allow_fault" in f,
            "a licence for 254 licensed a crop blank at 255: %r" % f)
        _b, f = diag.gate_outbound(real, offnet=True)
        chk(f is None, "the real crop fails the unlicensed gate: %r" % f)

        # The licence does not reach the aperture checks.  No value of it makes a note-box crop
        # sendable, and that is a standing rule, not a preference.
        nb = td / "_selftest_A1_notebox.png"
        nb.write_bytes(bb)
        try:
            for lic in (None, BLANK_FAULT, "offnet:not-an-A2-span-box-crop:_selftest_A1_notebox.png"):
                _b, f = diag.gate_outbound(nb, offnet=True, allow_fault=lic)
                chk(f is not None and "A2-span-box" in f,
                    "a note-box crop passed the aperture check under allow_fault=%r: %r" % (lic, f))
        finally:
            nb.unlink()
    finally:
        tmp.unlink()
        td.rmdir()

    # The cut's invariants, over the whole population, with no file written.
    body, _ = cut(write=False)
    chk(body["n"] == 45 and body["n_sendable"] == 41 and body["calls"] == 162,
        "cut population moved: %s" % canon({k: body[k] for k in ("n", "n_sendable", "calls")}))
    chk(all(r["blank_fault"] == BLANK_FAULT for r in body["rows"]), "a blank row is not blank")
    chk(all(r["blank_sha16"] != r["real_sha16"] for r in body["rows"]), "a blank hashes as its real")

    # The lock registers both ends of every cell, so every cell can miss in either direction.  A
    # one-sided range is a prediction that cannot be wrong on the side that matters.
    for cell, v in REGISTERED.items():
        chk(any(k.startswith("exact") for k in v) and any(k.startswith("abstain") for k in v),
            "cell %s registers no exact or no abstention bound" % cell)
    chk(len(REGISTERED) == 4 and len(SIGNS) == 4 and len(RULE) == 8,
        "the lock's shape moved: %d cells, %d signs, %d rules"
        % (len(REGISTERED), len(SIGNS), len(RULE)))

    print("selftest OK: %d checks" % CHECKS[0])
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("cut", "lock", "sheet", "selftest"))
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    w = not a.no_write
    if a.cmd == "cut":
        cut(write=w)
    elif a.cmd == "lock":
        lock(write=w)
    elif a.cmd == "sheet":
        sheet(write=w)
    else:
        return selftest()
    print("checks: %d" % CHECKS[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
