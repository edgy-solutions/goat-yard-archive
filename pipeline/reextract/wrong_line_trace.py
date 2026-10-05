# -*- coding: utf-8 -*-
"""Why a span box lands on the wrong LINE: a stage trace of the localizer, over all 74 (Lane B, 2026-10-04).

    python wrong_line_trace.py

ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).

THE QUESTION. Signing pass 1 faulted 14 of 74 spans. One carries a note that says what the fault is --
`p92:n1`, "the crop is 3 lines up from the hebrew" -- and the other 13 carry none. The candidate text comes
from the whole-note read, not from the crop, so the text on screen is real and only the BOX can be wrong.
This file asks how, by tracing the stage that drew it rather than by scoring its output.

WHAT IT DOES NOT DO. It does not look at the pixels and judge where the Hebrew is; nothing here recognizes
Hebrew. It re-runs the localizer's own COUNTING with instrumentation and reports two invariants the
composition does not currently check. A box this file calls wrong is wrong by construction, which is a
stronger claim than a box that merely looks wrong -- and a box it cannot fault is NOT thereby confirmed. The
overlay sheet is the record for a human; this is the mechanism.

RETRACTED, 2026-10-04, by this file's own first run. The first version of this trace asserted two
invariants and found 0 frame mismatches and 74 of 74 segmentation mismatches. Both numbers were artifacts of
a false premise: I assumed the localizer is handed the NOTE TEXT. It is not. `draw_pool.py:87` calls
`NLR.locate_span(strip, note_index - 1, r["hebrew"], ...)`, so `run_text` is the Hebrew RUN ALONE. The old
invariant (1) compared two quantities that are equal by construction, and the old invariant (2) compared the
note band's word-box total against the HEBREW's token count, which has no reason to match anything. When a
probe disagrees with a whole set, suspect the probe. The run it produced is superseded by this one.

WHAT THAT PREMISE ACTUALLY MEANS -- INVARIANT (1), STRUCTURAL.

    `word_box_align.tokenize(run_text)` over a Hebrew-only string yields Hebrew tokens and nothing else, so
    `note_offset = sum(1 for s,_ in toks[:lo] if s in ("latin","greek","hebrew"))` is **0 for every span in
    this set, by construction** -- `lo` is 0 because the run starts at token 0. `hebrew_line` therefore
    stops at the FIRST line of the note region on every call, and `align` selects the LEFTMOST `block` word
    boxes on it after the marker strip. The design in `locate_hebrew`'s docstring -- count the words the note
    places before the Hebrew, then take the boxes at that index -- is not in use anywhere in this pipeline.
    Every box in this set is "the first word(s) of the note region's first line". This file asserts that
    positively rather than inferring it: no `run_text` in the set contains a non-Hebrew word token.

    This is the defect, and it is not a tuning question. It is a wiring question with one owner.

INVARIANT (2), POSITIONAL -- replacing the discarded one. `n_before = 0` is not wrong in itself; it is wrong
    only when a word precedes the Hebrew in the note. The span census records `start`, the Hebrew's
    CHARACTER offset inside the note text, computed from the note text by `span_census.py` and never seen by
    the localizer -- so it is an independent witness. `start == 0` means the Hebrew opens the note and the
    always-first-line behaviour is accidentally correct; `start > 0` means a box drawn at index 0 is pointed
    at type the Hebrew is not under. Cross-tabbing `start` against the pass-1 dispositions is the check: it
    is arithmetic over two files, with no recognizer anywhere in it.

WHAT THIS STILL CANNOT SEE. Nothing here says where the Hebrew is in the PIXELS. A row whose Hebrew opens its
note is only shown to be free of the index defect; its box can still be wrong because the note REGION starts
on the wrong line (`p92:n1`'s "3 lines up" is one witnessed instance), or because `word_boxes` split the run.
Those live one layer down, and a disposition this file cannot explain is reported as unexplained, not as fine.

OWNERSHIP. `note_line_region.py` and `word_box_align.py` are Lane A's substrate. This file imports them
READ-ONLY and changes nothing. If the trace lands, the fix is Lane A's to make, and the evidence is the
artifact this writes.
"""
import io
import json
import os
import sys
import time
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, os.pardir, "scripts"))

import cv_footnote_presplit as ps                                          # noqa: E402  Lane A's, read-only
import note_line_region as NLR                                            # noqa: E402  Lane A's, read-only
import word_box_align as W                                                # noqa: E402  Lane A's, read-only
import assembler as ASM                                                   # noqa: E402
import hebrew_aperture_diag as HAD                                        # noqa: E402
from clean_run import git_state, provisional, banner                      # noqa: E402

SET, SET_N = "0401b636ffa7bf1a", 74
TRUTH_PATH = HAD.DATA / ("truth_set%d_%s.json" % (SET_N, SET))
INGEST = HAD.DATA / ("signing_pass1_ingest_%s.json" % SET)
PAGE = "C:/Users/cnogr/git/dr-voluminous/commentary/volume1/page%d_image1.png"
PROF = os.path.join(_HERE, "book_profile.gill.yaml")
OUT = HAD.DATA / ("wrong_line_trace_%s.json" % SET)
PRINTED_OFFSET = 88

GIT_START = git_state(_HERE)

truth = json.load(io.open(str(TRUTH_PATH), encoding="utf-8"))
assert truth.get("provisional") is False and truth["set_sha16"] == SET and truth["n"] == SET_N
ROWS = truth["rows"]
assert len(ROWS) == SET_N
_sealed = sorted(set(HAD.SEALED_TRUTH) & set(r["span_id"] for r in ROWS))
assert not _sealed, "sealed span(s) %s -- sealed pages are SPENT" % _sealed

DISPO = {}
if INGEST.exists():
    DISPO = {r["span_id"]: r["disposition"] for r in json.load(io.open(str(INGEST), encoding="utf-8"))["rows"]}
assert DISPO, "the pass-1 ingest is missing -- the cross-tab against dispositions is the whole payload"

# The independent witness for invariant (2). `start` is the Hebrew's character offset inside the NOTE TEXT,
# computed by span_census.py from the note text. The localizer never receives the note text, so this number
# cannot be an echo of the thing it is being used to check.
CENSUS_PATH = HAD.DATA / "hebrew_span_census_20261004.json"
CEN = {r["span_id"]: r for r in json.load(io.open(str(CENSUS_PATH), encoding="utf-8"))["rows"]}
_nocen = sorted(r["span_id"] for r in ROWS if r["span_id"] not in CEN)
assert not _nocen, "%d span(s) absent from the census, so invariant (2) has no witness for them: %s" \
    % (len(_nocen), _nocen[:6])

prof = ASM.load_profile(PROF)
assert prof, "no profile -- note_line_regions would take None and die on .get"


def trace_note(band, region, run_text):
    """`note_line_region.hebrew_line`'s walk, instrumented. Mirrors it line for line -- including that the
    marker is stripped on the FIRST line only -- and records what it consumed instead of only where it
    stopped. Returns a dict; `landing` is None when the walk overflows."""
    toks = W.tokenize(run_text)
    run = W._hebrew_run(toks)
    if run is None:
        return {"status": "no-hebrew"}
    if run == "split":
        return {"status": "hebrew-not-contiguous"}
    lo, hh = run
    note_offset = sum(1 for s, _ in toks[:lo] if s in ("latin", "greek", "hebrew"))
    block = hh - lo + 1
    # `run_text` is the Hebrew run, not the note (draw_pool.py:87), so this counts the HEBREW's own word
    # tokens. It is NOT the note's token count and must never be compared against the band's box total --
    # that comparison is the retracted invariant. It is kept only to witness `nonhebrew_tokens == 0`.
    run_tokens = sum(1 for s, _ in toks if s in ("latin", "greek", "hebrew"))
    nonhebrew_tokens = sum(1 for s, _ in toks if s in ("latin", "greek"))

    offset = note_offset
    per_line, landing, first = [], None, True
    li = 0
    for seg in region.get("segments") or [region]:
        for (y0, y1) in seg["lines"]:
            crop = band.crop((seg["ins"], y0, seg["x1"], y1))
            wb = W.word_boxes(crop)
            if first:
                wb = W.strip_marker(wb, y1 - y0)
            first = False
            per_line.append({"line": li, "y0": y0, "y1": y1, "ins": seg["ins"], "boxes": len(wb),
                             "offset_in": offset})
            if landing is None and offset < len(wb):
                landing = {"line": li, "y0": y0, "y1": y1, "ins": seg["ins"], "x1": seg["x1"],
                           "boxes": len(wb), "local_offset": offset, "wb": wb, "h": y1 - y0}
            if landing is None:
                offset -= len(wb)
            li += 1
    return {"status": "ok", "note_offset": note_offset, "block": block, "run_tokens": run_tokens,
            "nonhebrew_tokens": nonhebrew_tokens,
            "box_total": sum(p["boxes"] for p in per_line), "n_lines": li, "per_line": per_line,
            "landing": landing}


res, cache = [], {}
t00 = time.time()
for i, r in enumerate(sorted(ROWS, key=lambda x: (x["page"], x["note_index"])), 1):
    rec = {"span_id": r["span_id"], "page": r["page"], "printed": r["page"] - PRINTED_OFFSET,
           "note_index": r["note_index"], "notes_on_page": r["notes_on_page"],
           "hebrew": r["hebrew"], "words": r["words"], "stored_box": list(r["box"]),
           "disposition": DISPO.get(r["span_id"], "?"),
           "start_in_note": CEN[r["span_id"]]["start"], "note_len": CEN[r["span_id"]]["note_len"],
           "spans_in_note": CEN[r["span_id"]]["spans_in_note"],
           "hebrew_opens_note": CEN[r["span_id"]]["start"] == 0}
    try:
        if r["page"] not in cache:
            cache[r["page"]] = ps.presplit(PAGE % r["page"], upscale=1)
        strip, info = cache[r["page"]]
        if strip is None:
            rec["status"] = "no-strip"
        else:
            band = strip.convert("L")
            regions, st = NLR.note_line_regions(band, r["notes_on_page"], prof)
            if regions is None:
                rec["status"] = "page-abstain:" + st
            elif not (0 <= r["note_index"] - 1 < len(regions)):
                rec["status"] = "note-idx-oob"
            else:
                t = trace_note(band, regions[r["note_index"] - 1], r["hebrew"])
                rec["status"] = t["status"]
                if t["status"] == "ok":
                    rec.update(n_lines=t["n_lines"], run_tokens=t["run_tokens"],
                               nonhebrew_tokens=t["nonhebrew_tokens"],
                               box_total=t["box_total"], note_offset=t["note_offset"], block=t["block"],
                               line_box_counts=[p["boxes"] for p in t["per_line"]])
                    L = t["landing"]
                    if L is None:
                        rec["landing"] = None
                        rec["status"] = "offset-overflow"
                    else:
                        rec["landing_line"] = L["line"]
                        rec["local_offset"] = L["local_offset"]
                        # What `align` uses on that line: the NOTE-level count, recomputed from scratch.
                        rec["n_before_align"] = t["note_offset"]
                        rec["frame_mismatch"] = (t["note_offset"] != L["local_offset"])
                        # The frame-correct selection: the same counting method, at the index the line walk
                        # itself established. Folded back to BAND coords exactly as `locate_span` does.
                        need = L["local_offset"] + t["block"]
                        if len(L["wb"]) < need:
                            rec["recomputed_box"] = None
                            rec["recompute_status"] = "count-mismatch-local"
                        else:
                            sel = L["wb"][L["local_offset"]:need]
                            rec["recomputed_box"] = [min(b[0] for b in sel) + L["ins"], L["y0"],
                                                     max(b[1] for b in sel) + L["ins"], L["y1"]]
                            rec["recompute_status"] = "ok"
                        # And what `align` would have selected with the note-level index on this line.
                        need2 = t["note_offset"] + t["block"]
                        rec["align_needs_boxes"] = need2
                        rec["align_has_boxes"] = len(L["wb"])
    except Exception as e:
        rec["status"] = "%s: %s" % (type(e).__name__, str(e)[:110])
    res.append(rec)
    if i % 20 == 0:
        print("  %3d/%d  %.0fs" % (i, SET_N, time.time() - t00), flush=True)

assert len(res) == SET_N, "the trace covers %d of %d spans" % (len(res), SET_N)

ok = [x for x in res if x["status"] == "ok"]
# A trace that reached almost nothing would otherwise report a reassuring zero. Floor stated, not assumed.
assert len(ok) >= 40, "only %d of %d spans traced -- this is a report about the TRACE, not the boxes" \
    % (len(ok), SET_N)


def box_same(a, b, tol=2):
    return a is not None and b is not None and all(abs(p - q) <= tol for p, q in zip(a, b))


for x in ok:
    rb, sb = x.get("recomputed_box"), x["stored_box"]
    if rb is None:
        x["verdict"] = "recompute-abstained"
    elif box_same(rb, sb):
        x["verdict"] = "stored-box-agrees"
    elif abs(rb[1] - sb[1]) > 4 or abs(rb[3] - sb[3]) > 4:
        x["verdict"] = "different-LINE"
    else:
        x["verdict"] = "same-line-different-words"
    x["dy_top"] = (rb[1] - sb[1]) if rb else None

multi = [x for x in ok if x.get("n_lines", 1) > 1]
fm = [x for x in ok if x.get("frame_mismatch")]

# INVARIANT (1), asserted positively. If this ever fails, `run_text` has stopped being the Hebrew run and
# every conclusion below about "always the first line" is void -- which is exactly the premise error this
# file was rewritten to retract, so it is checked rather than narrated.
_nh = [x["span_id"] for x in ok if x.get("nonhebrew_tokens")]
assert not _nh, "run_text carries non-Hebrew word tokens on %d span(s) %s -- re-read draw_pool.py:87 before " \
    "reading any number in this file" % (len(_nh), _nh[:6])
_off = [x["span_id"] for x in ok if x.get("note_offset") != 0]
assert not _off, "note_offset is non-zero on %d span(s) %s" % (len(_off), _off[:6])
_land = [x["span_id"] for x in ok if x.get("landing_line") not in (0, None)]
assert not _land, "the walk landed below line 0 on %s -- impossible at offset 0" % (_land[:6],)

# INVARIANT (2). Arithmetic over the census and the ingest; no recognizer.
opens = [x for x in ok if x["hebrew_opens_note"]]
mid = [x for x in ok if not x["hebrew_opens_note"]]
pos_x_dis = Counter(("opens" if x["hebrew_opens_note"] else "mid-note",
                     x["disposition"].split("_")[0]) for x in ok)
mid_rows = sorted(((x["start_in_note"], x["note_len"], x["span_id"], x["disposition"]) for x in mid),
                  reverse=True)
# A THIRD HYPOTHESIS, TESTED AND REJECTED -- kept so nobody spends the run again. If the note REGION
# under-detected its lines, a long note squeezed into one region line would be the shape of "3 lines up", and
# chars-per-line would separate the faults from the signed rows. It does not: the control kills it. The
# signed row `p798:n0` carries 129 chars in a ONE-line region and its box was accepted, which is above every
# fault in the set. A rejected hypothesis is reported, not dropped.
def _cpl(rows):
    v = sorted(x["note_len"] / float(x["n_lines"]) for x in rows)
    return {"n": len(v), "median": round(v[len(v) // 2], 1) if v else None,
            "max": round(v[-1], 1) if v else None}

faults = [x for x in ok if x["disposition"].startswith("fault")]
f_mid = [x for x in faults if not x["hebrew_opens_note"]]
f_opens = [x for x in faults if x["hebrew_opens_note"]]
by_verdict = Counter(x["verdict"] for x in ok)
cross = Counter((x["verdict"], x["disposition"].split("_")[0]) for x in ok)
fm_by_dis = Counter(x["disposition"] for x in fm)

GIT_END = git_state(_HERE)
doc = {
    "set_sha16": SET, "n": SET_N, "printed_offset": PRINTED_OFFSET,
    "question": "the 14 pass-1 faults: is the box on the wrong line, and by what mechanism",
    "method": "re-run the localizer's own counting with instrumentation; nothing here recognizes Hebrew",
    "retracted": {
        "when": "2026-10-04, by this file's own first run",
        "what": "the frame invariant (0 mismatches) and the segmentation-total invariant (74 of 74) both "
                "rested on the premise that the localizer receives the NOTE TEXT",
        "why_false": "draw_pool.py:87 passes r['hebrew'] as run_text, so the localizer never sees the note",
    },
    "invariants": {
        "structural": "run_text is the Hebrew run alone, so note_offset is 0 on every span by construction "
                      "and every box is the leftmost `block` word boxes of the note region's FIRST line; "
                      "the counting design in locate_hebrew's docstring is not in use. ASSERTED, not shown.",
        "positional": "census `start` (the Hebrew's char offset in the NOTE TEXT, never seen by the "
                      "localizer) decides whether index 0 is the right index; cross-tabbed against the "
                      "pass-1 dispositions",
    },
    "structural_defect": {
        "site": "draw_pool.py:87 -> note_line_region.locate_span(.., run_text=r['hebrew'], ..)",
        "owner": "Lane A substrate (note_line_region.py / word_box_align.py); change requested, not made",
        "note_offset_zero": len(ok), "landing_line_zero": len(ok),
    },
    "rejected_hypothesis": {
        "claim": "the note region under-detected its lines, so a long note on one region line is the "
                 "'3 lines up' shape; chars-per-line would separate faults from signed rows",
        "verdict": "REJECTED by its own control",
        "why": "the SIGNED row p798:n0 is 129 chars in a 1-line region -- higher than every fault in the "
               "set -- so a long note on one region line is normal here and discriminates nothing",
        "chars_per_line": {"signed": _cpl([x for x in ok if x["disposition"] == "signed"]),
                           "fault_opening_note": _cpl(f_opens),
                           "abstain": _cpl([x for x in ok if x["disposition"].startswith("abstain")])},
    },
    "positional": {
        "hebrew_opens_note": len(opens), "hebrew_mid_note": len(mid),
        "x_disposition": {"%s|%s" % k: v for k, v in sorted(pos_x_dis.items())},
        "mid_note_rows": [{"span_id": c, "start": a, "note_len": b, "disposition": d}
                          for a, b, c, d in mid_rows],
        "faults_mid_note": len(f_mid), "faults_opening_note": len(f_opens),
        "faults_mid_note_ids": sorted(x["span_id"] for x in f_mid),
        "faults_opening_note_ids": sorted(x["span_id"] for x in f_opens),
        "unexplained": "a fault on a span whose Hebrew OPENS its note is not explained by the index defect; "
                       "the remaining candidates are the note region's first line and word_boxes, both one "
                       "layer down. Reported as unexplained, never as fine.",
    },
    "traced": len(ok), "not_traced": SET_N - len(ok),
    "multi_line_notes": len(multi),
    "frame_mismatch": len(fm), "frame_mismatch_by_disposition": dict(fm_by_dis),
    "verdicts": dict(by_verdict),
    "verdict_x_disposition": {"%s|%s" % k: v for k, v in sorted(cross.items())},
    "rows": res,
    "git_start": GIT_START, "git_end": GIT_END, "provisional": provisional(GIT_START, GIT_END),
}
io.open(str(OUT), "w", encoding="utf-8", newline="\n").write(
    json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=False))

print("wrong-line trace over %d spans (%d traced, %d not)" % (SET_N, len(ok), SET_N - len(ok)))
print("  statuses: %s" % dict(Counter(x["status"] for x in res)))
print("  multi-line notes: %d of %d traced" % (len(multi), len(ok)))
print("  INVARIANT 1 (structural): note_offset==0 and landing_line==0 on %d of %d traced -- ASSERTED."
      % (len(ok), len(ok)))
print("      every box is the leftmost word box(es) of the note region's FIRST line; the counting design")
print("      is not in use. Site: draw_pool.py:87 passes r['hebrew'] where the note text is required.")
print("  INVARIANT 2 (positional): Hebrew opens its note on %d, sits mid-note on %d" % (len(opens), len(mid)))
for k, v in sorted(pos_x_dis.items()):
    print("      %-9s %-12s %d" % (k[0], k[1], v))
print("      faults mid-note %d of %d   faults on opening spans %d of %d  (UNEXPLAINED by the index defect)"
      % (len(f_mid), len(mid), len(f_opens), len(opens)))
print("  REJECTED hypothesis (region under-detected lines): chars/line signed %s vs fault-opening %s --"
      % (_cpl([x for x in ok if x["disposition"] == "signed"]), _cpl(f_opens)))
print("      the SIGNED row p798:n0 is 129 chars in a 1-line region, above every fault: discriminates nothing.")
for a, b, c, d in mid_rows:
    print("      mid-note  %-10s start=%-4d note_len=%-5d %s" % (c, a, b, d))
print("  recomputed vs stored box:")
for k, v in sorted(by_verdict.items(), key=lambda kv: -kv[1]):
    print("      %-28s %d" % (k, v))
print("  cross-tab verdict x disposition:")
for k, v in sorted(cross.items()):
    print("      %-28s %-12s %d" % (k[0], k[1], v))
print("  the 14 pass-1 faults, one line each:")
for x in sorted(ok, key=lambda x: x["span_id"]):
    if x["disposition"].startswith("fault"):
        print("      %-10s lines=%-2s landing=%-2s local=%-3s block=%-3s has=%-3s start=%-4s %-6s %s"
              % (x["span_id"], x.get("n_lines"), x.get("landing_line"), x.get("local_offset"),
                 x.get("block"), x.get("align_has_boxes"), x.get("start_in_note"),
                 "opens" if x["hebrew_opens_note"] else "MID", x["verdict"]))
print("  wrote %s" % OUT.name)
print(banner(GIT_START, GIT_END))
