# -*- coding: utf-8 -*-
u"""Write the methods lock for the OFFLINE LINE LOCALIZER: which printed line carries the Hebrew?

Lane B / session 50612c81.  ALL PAGE NUMBERS ARE FILE pages (printed = file - 88).

Chris, 2026-11-26, item 3: "The localizer is the lane's bottleneck and was never wired (every
stored box is the region's first line).  Write a lock, then build offline with no model calls:
place each span's box on the line that carries Hebrew type, using the page's Tesseract layer and a
script test on ink.  Score it against Chris's GEOMETRY5 verdicts and the signed as-ratified boxes.
Report how many of the 74 boxes land on the right line."

NOTHING HERE SENDS ANYTHING AND NOTHING HERE READS A MODEL.  This module writes a prediction
record and exits.  It is content-addressed by its own body -- strip `self_sha16`, canonical JSON,
UTF-8 bytes, `ensure_ascii=False` (ruling 5's hash rule, stated here because the rule says to state
it) -- so a prediction cannot be edited after the numbers land.

WHAT THE DATA ALREADY SAYS, BEFORE ANY RUN.  "Every stored box is the region's first line" is not
inherited here, it is re-measured: on all 11 development spans `box.y0 == note_region.y0`, and on
the 7 whose region holds one line the box IS the region, rect for rect.  So the stored box encodes
the region, never the span, and the localizer has nothing to improve on -- it has something to
supply.

THE FINDER IS THE TESSERACT LAYER'S OWN SCRIPT, NOT AN INK CLASSIFIER.  Three methods were built
and two were falsified on development spans before this lock was written:

  (1) whole-line script classification.  FALSIFIED: the box's own line carries confident Tesseract
      coverage 0.63-0.87, because a Hebrew span is a short phrase set INSIDE a Latin line.  A
      classifier over lines measures the Latin.
  (2) "the Hebrew is the inked run the Latin layer left unread".  FALSIFIED: unread runs appear on
      nearly every band -- italic, ligatures and small type all go unread.  p385:n0's box band
      alone carries 12 of them around a single Hebrew word.  The ink channel cannot FIND Hebrew.
  (3) the layer's own codepoints.  The vol.1 OCR was built with Hebrew script available and the
      layer carries real Hebrew at high confidence ('shin-kaf-bet-tav' 91, 'yod-tsadi-alef' 88,
      'alef-lamed' 90).  Script is then a DETERMINISTIC PROPERTY of the layer's text -- a codepoint
      range, not a judgement -- so code owns it and an assertion watches it.

So: the finder is codepoints; the ink test is the CORROBORATION (are the pixels under a word the
layer calls Hebrew inked type at all) and, separately, the NEGATIVE test (a box band that is
entirely covered by confident Latin words carries no unread type, so the Hebrew is not on it).  Two
channels in different roles, each named; neither is asked to do the other's job.

WHAT THIS LOCK REFUSES TO SCORE.  "How many of the 74 land on the right line" has no 74-span
answer, and the number it does have is 6.  Of the 11 `box_fault` spans in the send sidecar, TEN are
`box-edge-cut` -- a box that clips the span is a different axis from a box on the wrong line -- and
exactly one, p92:n1, is `fault_box_wrong_line`.  Scoring edge-cut spans as line faults would be a
class label inheriting a population it was never drawn for.  And GEOMETRY5's vocabulary says in its
own words that `box_on_hebrew` was "declared and unused in this sitting": THERE IS NO SIGNED
STATEMENT THAT ANY BOX IS RIGHT.  A run cannot be scored for false positives against a truth set
that has no positives, so the localizer's agreements with the stored box are reported as CLAIMS
AWAITING ADJUDICATION, never as passes.

Run with --write to emit; without, it prints the digest and the body and touches nothing.
"""
import argparse
import hashlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score45_run as S                    # canon / sha16_bytes / git_state / the audits dir

OUT_DIR = S.A
CUT = "0401b636ffa7bf1a"
CUT_SET = "truthset74_cut_%s.json" % CUT
TRUTH_SET = "truth_set74_%s.json" % CUT
GEOM5 = "GEOMETRY5_adjudication_3f6b0357a850548e.json"
FLAGS = "span_send_flags.json"
LOCK_NAME = "LOCK_line_localizer_20261126.json"

# ---------------------------------------------------------------------------------------------
# FROZEN PARAMETERS.  Every one of these was chosen by looking at the 11 development spans named
# in DEV below and at nothing else.  A threshold chosen on a scored span would make the score a
# measurement of the tuning.
# ---------------------------------------------------------------------------------------------
PARAMS = {
    "ink_threshold": 128,
    "ink_threshold_basis": "grayscale < 128 is ink; vol.1 scans are mode 'L' on white paper",
    "latin_conf_ok": 60,
    "latin_conf_ok_basis": ("a Tesseract word at or above this counts as CONFIDENTLY READ for the "
                            "negative test only.  It is NOT applied to Hebrew candidates: the "
                            "layer's Hebrew confidences on development spans run 41-96 and a "
                            "floor of 60 would discard three true candidates.  A Hebrew candidate "
                            "is corroborated by ink, not by confidence."),
    "hebrew_ranges": [[0x0590, 0x05FF], [0xFB1D, 0xFB4F]],
    "hebrew_ranges_basis": ("Hebrew block plus the presentation forms.  U+200E (LRM) rides along "
                            "in the layer's text and is NOT a Hebrew codepoint, so a word that is "
                            "only a direction mark cannot become a candidate."),
    "window_pitches": 3.5,
    "window_basis": ("the search window is +-3.5 x band-local pitch around the stored box.  It "
                     "MUST exceed the note region: p144:n0 has one line in its region and Chris "
                     "ruled its box 2 lines off, so the right line can lie outside the region.  "
                     "The cost is that a neighbouring note's Hebrew can enter the window, which "
                     "is why region containment is RECORDED per candidate and never assumed."),
    "pitch_scope": "band-local",
    "pitch_basis": ("median spacing of Tesseract line tops in this column within 500 px of the "
                    "box.  Band-local on purpose: a page-wide pitch is a different unit from the "
                    "local one, and a control measured in the wrong unit licenses nothing."),
    "pitch_fallback": 55,
    "seg_smooth_divisor": 8,
    "seg_peak_halfwindow": 0.45,
    "seg_peak_floor": 0.18,
    "seg_trim_floor": 0.06,
    "seg_basis": ("lines are cut at the VALLEYS between ink peaks spaced at the local pitch.  A "
                  "fixed ink floor was tried first and merged whole paragraphs into one band, "
                  "because descenders and speckle keep the gap between printed lines inked."),
    "furniture_rule": {"min_width_frac_of_col": 0.85, "max_height_frac_of_pitch": 0.45,
                       "min_density": 0.25},
    "furniture_basis": ("a printed rule IS an inked band and satisfies every liveness check, so "
                        "furniture bands are struck from the line sequence BEFORE indices are "
                        "taken.  A rule counted as a line inflates any offset measured across it "
                        "by one.  The count of struck bands is recorded per span."),
    "ink_corroboration": {"min_ink_frac": 0.10, "min_height_frac_of_pitch": 0.30,
                          "max_height_frac_of_pitch": 1.30},
    "ink_corroboration_basis": ("a DEGENERACY GUARD, not a Hebrew classifier: it rejects a "
                                "candidate whose pixels are blank (ink_frac ~ 0) or are a printed "
                                "rule (height far under the pitch at high density).  Development "
                                "spans measured ink_frac 0.306-0.612 and height 0.47-0.92 of "
                                "pitch, so the bounds sit well outside the observed band and the "
                                "guard is not doing the finding."),
}

# The 11 development spans: every span of the 74 that carries NO truth of any kind -- not a
# GEOMETRY5 verdict, not `signed`, not a measured box_fault, not a pass-1 control mark -- and does
# not share a page with a GEOMETRY5 row.  p306:n0 is excluded for sharing page 306 with the signed
# GEOMETRY5 row p306:n1: a page looked at while tuning leaks into the row scored on it.
DEV = ("p203:n8", "p275:n3", "p291:n0", "p300:n0", "p312:n7", "p377:n1",
       "p381:n2", "p385:n0", "p463:n0", "p492:n1", "p921:n4")

# ---------------------------------------------------------------------------------------------
# THE DECISION RULE, stated before the run.
# ---------------------------------------------------------------------------------------------
DECISION_RULE = {
    "verdict_vocabulary": {
        "on_hebrew": ("a corroborated Hebrew candidate lies on the stored box's own line band.  "
                      "Carries offset 0."),
        "off_by_lines": ("corroborated Hebrew candidates exist in the window but none on the box's "
                         "band.  Carries a signed offset to the NEAREST such candidate."),
        "abstain_no_candidate": ("no Hebrew codepoint anywhere in the window.  The localizer does "
                                 "not place the span.  This is not a fault verdict and not a "
                                 "pass: it is the absence channel, and a system with no way to "
                                 "say 'nothing here' turns its components' honesty into "
                                 "fabrications."),
        "abstain_no_band": ("the box's centre falls in no line band, or the page has no usable "
                            "pitch.  Unplaceable for a reason that is about this method, not "
                            "about the box."),
    },
    "sign_rule": ("offset = box_line_index - hebrew_line_index.  NEGATIVE = the stored box is "
                  "ABOVE the Hebrew, POSITIVE = BELOW.  Taken from GEOMETRY5's own sign_rule, "
                  "which derives it from the words 'above' and 'below' in Chris's basis, so the "
                  "two records are in one convention and an agreement is not a units accident."),
    "ambiguity": ("when candidates sit on more than one band, the offset is to the nearest and "
                  "`candidate_bands` records all of them.  The verdict 'the box is not on a line "
                  "carrying Hebrew type' survives the ambiguity even where 'which line is right' "
                  "does not -- p381:n2 offers two 3-letter candidates two and three lines above "
                  "its box, and which of them is this span's is not decidable offline."),
    "negative_corroboration": ("`box_band_all_read` is recorded when every inked column of the "
                               "box's band is covered by a confident Latin word.  It is reported "
                               "beside the verdict and never substituted for it: it says the box "
                               "sits on fully-read Latin, which is evidence the Hebrew is "
                               "elsewhere, not evidence of where."),
    "region_containment": ("`in_region` is recorded per candidate.  On three development spans the "
                           "located Hebrew sits just ABOVE the note region, which has two rival "
                           "causes -- a region off by one line, or Hebrew belonging to the "
                           "PREVIOUS note while this span's own Hebrew went unread.  This method "
                           "cannot discriminate them and does not claim to; the causal story is a "
                           "claim too, and it is left unmade."),
}

# ---------------------------------------------------------------------------------------------
# THE SCORING STRATA.  Each carries its own denominator, and the strata that cannot score this
# question carry a denominator of zero WITH the reason, so nothing can be imported into them later.
# ---------------------------------------------------------------------------------------------
STRATA = {
    "S1_geometry5_signed_lines": {
        "n": 4,
        "spans": ["p107:n3", "p133:n1", "p144:n0", "p306:n1"],
        "truth": {"p107:n3": -1, "p133:n1": -1, "p144:n0": 2, "p306:n1": 2},
        "scores": "sign agreement, then magnitude agreement, reported separately",
        "note": ("Chris's own `box_off_by_lines` verdicts with signed counts.  p306:n1 carries "
                 "excluded_from_rate: True in the adjudication record, so it is scored and "
                 "reported but kept OUT of any rate.  GEOMETRY5 is provisional (built over dirty "
                 "trees) and citable for the verdicts themselves, not for a fault rate -- so this "
                 "stratum can say whether the method reproduces his readings, and cannot say what "
                 "the volume's fault rate is."),
    },
    "S1b_geometry5_no_hebrew_on_crop": {
        "n": 1,
        "spans": ["p256:n3"],
        "truth": {"p256:n3": "not_on_hebrew_binary"},
        "scores": "binary only: does the method also decline to put the Hebrew on this box?",
        "note": ("GEOMETRY5's vocabulary: 'no line on the crop can be the Hebrew.  NOT an offset "
                 "of any size; carries no line count, by rule.'  So a magnitude from this span "
                 "would be invented."),
    },
    "S2_measured_wrong_line": {
        "n": 1,
        "spans": ["p92:n1"],
        "truth": {"p92:n1": "fault_box_wrong_line, magnitude reported elsewhere as 3, sign never "
                            "verified"},
        "scores": "fault/no-fault agreement; magnitude recorded, not scored",
        "note": ("a pass-1 disposition, not a Chris verdict: GEOMETRY5 carries p92:n1 as "
                 "`not_adjudicated` and says in its own words that it claims nothing about it.  "
                 "Weaker stratum, kept separate."),
    },
    "S3_edge_cut": {
        "n": 0,
        "spans": ["p322:n1", "p493:n3", "p546:n0", "p594:n0", "p628:n1", "p724:n4",
                  "p796:n0", "p803:n0", "p894:n4", "p910:n0"],
        "scores": "NOTHING, by rule",
        "note": ("these ten are `box-edge-cut`: the box clips the span.  That is a different "
                 "fault axis from line placement and these spans are NOT evidence about it in "
                 "either direction.  They are listed so that a later run cannot quietly adopt "
                 "them as a line-fault denominator."),
    },
    "S4_glyph_signed": {
        "n": 0,
        "spans": "the 45 spans with signed: True in the send sidecar",
        "scores": "NOTHING in this run, pending provenance",
        "note": ("the signing surface showed per-glyph consonant tiles and `note_crops: null`, so "
                 "a signature attests the glyph chain, not the box.  There IS a containment "
                 "inference available -- if the tiles were cut from the stored box's crop, a "
                 "signed glyph proves the Hebrew's pixels were inside that crop, which would "
                 "falsify any placement putting the Hebrew outside it -- but the tiles' "
                 "provenance has not been verified in this session, and an unverified provenance "
                 "is not a truth stratum.  Registered as UNUSED so that using it later requires "
                 "a new lock and the provenance check."),
    },
    "S5_remainder": {
        "n": 0,
        "scores": "UNSCOREABLE",
        "note": ("the balance of the 74 carry no statement about placement from anyone.  The "
                 "localizer's output on them is a claim awaiting adjudication and is reported as "
                 "a census, never as an accuracy."),
    },
}

# ---------------------------------------------------------------------------------------------
# PREDICTIONS, registered before the run.  Ranges, because a point prediction here would be a
# guess dressed as a number.
# ---------------------------------------------------------------------------------------------
PREDICTIONS = {
    "standard": ("offsets compared against GEOMETRY5's signed counts in GEOMETRY5's own sign "
                 "convention; abstentions counted, never redistributed"),
    "S1_sign_agreement": {"min": 3, "of": 4,
                          "why": ("the method reproduced a non-zero offset on 3 of 11 development "
                                  "spans unprompted, and GEOMETRY5's four are hand-picked "
                                  "suspects, which is the easy direction for a fault detector")},
    "S1_magnitude_agreement": {"min": 2, "of": 4,
                               "why": ("p107:n3's own basis says two printed notes share one note "
                                       "region, so the window will likely offer the neighbouring "
                                       "note's Hebrew and the magnitude is the part most at risk")},
    "S1b_binary": {"expect": "not_on_hebrew or abstain_no_candidate", "of": 1},
    "S2_binary": {"expect": "off_by_lines or abstain_no_candidate", "of": 1},
    "abstention_rate_over_74": {"min": 10, "max": 30,
                                "why": "3 of 11 development spans had no Hebrew codepoint at all"},
    "resolved_at_offset_zero": {"min_frac": 0.35, "max_frac": 0.70,
                                "why": ("5 of the 8 resolved development spans came out at 0.  "
                                        "This is a CLAIM, not an accuracy: no signed truth says "
                                        "any box is right")},
    "per_word_count": ("rates reported separately for one-word (50) and multi-word (24) spans, "
                       "under the truth set's own `short_span_skew` limit, which says averaging "
                       "them away is not allowed"),
}

FALSIFIERS = {
    "method_wrong_for_a_signed_span": ("the localizer returns on_hebrew (offset 0) for a span "
                                       "Chris signed as box_off_by_lines.  That is the method "
                                       "contradicting a signed verdict and it is reported as the "
                                       "method's failure, not as his error."),
    "sign_inversion": ("offsets reproduce magnitudes but with the sign flipped on 2 or more of "
                       "S1.  The convention is then wrong and every offset in the run is "
                       "retracted, not re-signed."),
    "abstention_eats_the_informative_set": ("if the method abstains on 2 or more of the 6 scored "
                                            "spans, S1 and S2 are UNSCOREABLE and no rate is "
                                            "reported from them -- a refusal set that lands "
                                            "exactly on the hard subpopulation has emptied a "
                                            "scored population in this lane before."),
    "furniture_as_a_line": ("any span whose offset changes when furniture bands are struck is "
                            "listed; if that is more than a quarter of the resolved spans, the "
                            "line index is furniture-sensitive and offsets are reported with "
                            "both counts, never one."),
    "pitch_degenerate": ("spans falling back to pitch 55 are counted and reported separately: a "
                         "derived parameter that silently defaults is a function deriving its own "
                         "input."),
}

WHAT_THIS_DOES_NOT_SOLVE = [
    ("It does not place the Hebrew where the Tesseract layer is mute.  3 of 11 development spans "
     "have no Hebrew codepoint in the window and the ink channel cannot supply one, because unread "
     "runs are everywhere.  Those spans ABSTAIN and stay unplaced until something reads pixels."),
    ("It does not discriminate 'the note region is off by a line' from 'this is the previous "
     "note's Hebrew'.  Both produce Hebrew just above the region, and the A2 note-region debt -- "
     "two printed notes inside one region, which p107:n3 confirms -- is the live alternative."),
    ("It cannot measure a false-positive rate.  GEOMETRY5 declared `box_on_hebrew` and never used "
     "it, so no signed statement says any box is correct, and an offset of 0 from this method is "
     "a claim about a line, not a pass."),
    ("It does not fix anything.  The run writes a placement proposal per span; nothing is written "
     "back into any crop, box, sheet or signed record, and no box is recut."),
    ("It says nothing about the 68 spans outside the 6-span scored population beyond its own "
     "reading of them, and that reading has not been in front of Chris."),
    ("It is not a corpus incidence.  The 74 are the localizer-REACHABLE population; 295 of 414 "
     "pages fail the note-count gate before a box is attempted."),
]


def _dev_carries_no_truth():
    u"""Derive the no-truth claim about DEV from the records, rather than asserting it in prose.

    A development set whose cleanliness is only claimed in a docstring is a snapshot pin.  This
    re-derives it from the three truth-bearing records every time the lock is built, and refuses
    if any development span has since acquired truth.
    """
    geom = json.loads(io.open(str(OUT_DIR / GEOM5), encoding="utf-8").read())
    flags = json.loads(io.open(str(OUT_DIR / FLAGS), encoding="utf-8").read())
    truth = json.loads(io.open(str(OUT_DIR / TRUTH_SET), encoding="utf-8").read())
    g_spans = set(r["span_id"] for r in geom["rows"])
    g_pages = set(r["span_id"].split(":")[0] for r in geom["rows"])
    fb = flags["flags_by_span"]
    signed = set(k for k, v in fb.items() if v.get("signed"))
    boxfault = set(flags["counts"]["box_fault"])
    bad = []
    for sid in DEV:
        why = []
        if sid in g_spans:
            why.append("has a GEOMETRY5 verdict")
        if sid.split(":")[0] in g_pages:
            why.append("shares a page with a GEOMETRY5 row")
        if sid in signed:
            why.append("signed")
        if sid in boxfault:
            why.append("measured box_fault")
        if why:
            bad.append((sid, why))
    if bad:
        raise SystemExit("REFUSED: development spans now carry truth: %r.  Thresholds were set by "
                         "looking at them, so scoring them would measure the tuning.  Redraw the "
                         "development set and write a NEW lock." % bad)
    ids74 = set(r["span_id"] for r in truth["rows"])
    missing = [s for s in DEV if s not in ids74]
    if missing:
        raise SystemExit("REFUSED: %r are not in the 74 cut %s" % (missing, CUT))
    return {"checked_against": [GEOM5, FLAGS, TRUTH_SET], "n_dev": len(DEV),
            "n_signed_in_set": len(signed), "n_box_fault_in_set": len(boxfault)}


def _strata_add_up():
    u"""The strata must partition the 74 with nothing counted twice and nothing lost."""
    flags = json.loads(io.open(str(OUT_DIR / FLAGS), encoding="utf-8").read())
    fb = flags["flags_by_span"]
    all74 = set(fb)
    if len(all74) != 74:
        raise SystemExit("REFUSED: the sidecar carries %d spans, not 74" % len(all74))
    s1 = set(STRATA["S1_geometry5_signed_lines"]["spans"])
    s1b = set(STRATA["S1b_geometry5_no_hebrew_on_crop"]["spans"])
    s2 = set(STRATA["S2_measured_wrong_line"]["spans"])
    s3 = set(STRATA["S3_edge_cut"]["spans"])
    named = s1 | s1b | s2 | s3
    for a, b, an, bn in ((s1, s1b, "S1", "S1b"), (s1, s2, "S1", "S2"), (s1, s3, "S1", "S3"),
                         (s1b, s2, "S1b", "S2"), (s1b, s3, "S1b", "S3"), (s2, s3, "S2", "S3")):
        if a & b:
            raise SystemExit("REFUSED: %s and %s share %r" % (an, bn, sorted(a & b)))
    outside = named - all74
    if outside:
        raise SystemExit("REFUSED: named scoring spans not in the 74: %r" % sorted(outside))
    # the ten S3 spans must really be edge-cut, and the one S2 span must really be wrong-line:
    # a stratum built on a label it never checked is a rename inheriting the old population
    for sid in s3:
        d = fb[sid].get("pass1_disposition") or ""
        basis = (fb[sid].get("basis") or {}).get("box_fault") or ""
        if "edge_cut" not in d and "edge-cut" not in basis:
            raise SystemExit("REFUSED: %s is in S3 but its disposition is %r / %r -- the "
                             "edge-cut stratum is not what it says it is" % (sid, d, basis))
    d92 = fb["p92:n1"].get("pass1_disposition")
    if d92 != "fault_box_wrong_line":
        raise SystemExit("REFUSED: p92:n1's disposition is %r, not fault_box_wrong_line" % d92)
    return {"n_sidecar": len(all74), "n_named": len(named),
            "n_scoreable_for_line_placement": len(s1 | s1b | s2),
            "n_unscoreable": len(all74) - len(s1 | s1b | s2),
            "partition_disjoint": True}


def _geom5_truth_matches_record():
    u"""S1's truth numbers must come from the record, not from this file's memory of it."""
    geom = json.loads(io.open(str(OUT_DIR / GEOM5), encoding="utf-8").read())
    rows = dict((r["span_id"], r) for r in geom["rows"])
    want = STRATA["S1_geometry5_signed_lines"]["truth"]
    for sid, off in want.items():
        got = rows[sid].get("lines_from_hebrew")
        if got != off:
            raise SystemExit("REFUSED: this lock says %s is %r but GEOMETRY5 says %r.  The lock "
                             "does not get to remember a verdict differently from the record."
                             % (sid, off, got))
        if rows[sid].get("verdict") != "box_off_by_lines":
            raise SystemExit("REFUSED: %s is verdict %r in GEOMETRY5" % (sid, rows[sid]["verdict"]))
    if rows["p256:n3"].get("verdict") != "no_hebrew_on_crop":
        raise SystemExit("REFUSED: p256:n3 is not no_hebrew_on_crop in the record")
    if rows["p92:n1"].get("verdict") != "not_adjudicated":
        raise SystemExit("REFUSED: p92:n1 is not not_adjudicated in the record")
    excl = [s for s, r in rows.items() if r.get("excluded_from_rate")]
    return {"sign_rule_quoted_from": GEOM5, "geom5_provisional": geom.get("provisional"),
            "geom5_citable_for": geom.get("citable_for"), "excluded_from_rate": sorted(excl),
            "box_on_hebrew_tally": geom["tallies"].get("box_on_hebrew")}


def build():
    body = {
        "kind": "line_localizer_methods_lock",
        "lane": "B",
        "session": "50612c81",
        "date": "2026-11-26",
        "page_convention": "all page numbers are FILE pages (printed = file - 88)",
        "directive": ("Chris, 2026-11-26, item 3: write a lock, then build offline with no model "
                      "calls; place each span's box on the line that carries Hebrew type, using "
                      "the page's Tesseract layer and a script test on ink; score it against the "
                      "GEOMETRY5 verdicts and the signed as-ratified boxes; report how many of "
                      "the 74 land on the right line"),
        "spend": {"model_calls": 0, "usd": 0.0,
                  "note": "offline by construction; this lock and its run have no network path"},
        "inputs": {"cut": CUT, "cut_set": CUT_SET, "truth_set": TRUTH_SET,
                   "geometry5": GEOM5, "send_flags": FLAGS,
                   "ocr_layer": "commentary/volume1/pageNNN_image1_ocr.json",
                   "page_png": "commentary/volume1/pageNNN_image1.png"},
        "method": {
            "finder": ("Hebrew codepoints in the Tesseract layer's own text, corroborated by ink. "
                       "Deterministic: a codepoint range is a property, not a judgement."),
            "falsified_first": [
                "whole-line script classification (the box's line is 0.63-0.87 confident Latin)",
                "unread-ink-run detection (unread runs appear on nearly every band)",
            ],
            "ink_channel_roles": ["corroboration of a candidate's own pixels",
                                  "negative test: box band entirely covered by confident Latin"],
            "line_index": ("pitch-driven valley cuts over the window's row ink profile, furniture "
                           "bands struck before indices are taken"),
        },
        "params": PARAMS,
        "development_set": {
            "spans": list(DEV),
            "rule": ("every span of the 74 carrying no truth of any kind and not sharing a page "
                     "with a GEOMETRY5 row"),
            "excluded_for_leak": {"p306:n0": "shares page 306 with the signed row p306:n1"},
            "statement": ("no scored span's pixels, box or offset was examined while these "
                          "parameters were chosen"),
            "derived_check": None,
        },
        "decision_rule": DECISION_RULE,
        "strata": STRATA,
        "predictions": PREDICTIONS,
        "falsifiers": FALSIFIERS,
        "what_this_does_NOT_solve": WHAT_THIS_DOES_NOT_SOLVE,
        "hash_rule": ("sha256 over canonical JSON of this body with self_sha16 removed, encoded "
                      "UTF-8 with ensure_ascii=False, first 16 hex chars"),
        "git_state_at_build": {"public": S.git_state("C:/Users/cnogr/git/goatyard-laneB"),
                               "private": S.git_state("C:/Users/cnogr/git/dr-voluminous")},
    }
    body["development_set"]["derived_check"] = _dev_carries_no_truth()
    body["strata_check"] = _strata_add_up()
    body["geometry5_check"] = _geom5_truth_matches_record()
    body["self_sha16"] = None
    probe = dict(body)
    probe.pop("self_sha16")
    body["self_sha16"] = hashlib.sha256(S.canon(probe).encode("utf-8")).hexdigest()[:16]
    return body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    body = build()
    out = OUT_DIR / LOCK_NAME
    print("lock %s  self_sha16=%s" % (LOCK_NAME, body["self_sha16"]))
    print("scoreable for line placement: %d of 74 (S1 %d, S1b %d, S2 %d); unscoreable %d"
          % (body["strata_check"]["n_scoreable_for_line_placement"],
             STRATA["S1_geometry5_signed_lines"]["n"],
             STRATA["S1b_geometry5_no_hebrew_on_crop"]["n"],
             STRATA["S2_measured_wrong_line"]["n"],
             body["strata_check"]["n_unscoreable"]))
    print("GEOMETRY5 box_on_hebrew tally = %r  (no signed statement that any box is right)"
          % body["geometry5_check"]["box_on_hebrew_tally"])
    if not a.write:
        print("-- dry run; nothing written.  Pass --write to emit.")
        return 0
    if out.exists():
        prev = json.loads(io.open(str(out), encoding="utf-8").read())
        if prev.get("self_sha16") != body["self_sha16"]:
            raise SystemExit("REFUSED: %s exists with digest %s and this build is %s.  A lock is "
                             "not editable after the fact -- write a new one under a new name."
                             % (LOCK_NAME, prev.get("self_sha16"), body["self_sha16"]))
        print("already written, identical digest")
        return 0
    io.open(str(out), "w", encoding="utf-8", newline="\n").write(
        S.canon(body) + u"\n")
    print("WROTE %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
