# -*- coding: utf-8 -*-
"""The per-glyph confirmation signer (Lane B, 2026-10-04).

    python glyph_signer.py

The signing sheet (`truth_set_sheet.py`) asked the human to TYPE Hebrew, which was never going to
happen. Its candidate was withheld because six of twenty earlier signatures went wrong -- but they went
wrong by accepting PROPERTIES nobody looked at (a pointing flag, a word division, a single inherited
letter), not by seeing the candidate itself. So this page does the opposite: it SHOWS the candidate and
makes the signer give a verdict on every property of the string -- one tile per consonant, one tile per
word gap, nothing accepted by default. `signed_from` changes accordingly: a record still claiming
"candidate withheld" would be false here, because the candidate is exactly what is on screen.

ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).

WHAT A TILE IS. `cand = row["hebrew"]` is split per character with `unicodedata.combining`: a combining
mark is a POINT, everything else (that is not whitespace) is a CONSONANT. Tiles are consonants only;
words are `cand.split()` tokens, emitted in printed order (storage order IS right-to-left reading order
for this fount -- word 1 is the rightmost word, and within a word, character 1 is its rightmost glyph;
see `hebrew_glyph_card.words`/`positions` for the existing idiom this file does not reimplement). Between
word i and word i+1 sits a GAP tile, so a word-space error (the measured `p362:n1` class of signature
defect) cannot be inherited silently by an unasked question. Points are never tiled: they are recorded
per row, verbatim, as `points_shown_not_adjudicated`, and the page says the signature is CONSONANTAL --
adding points to the standard does not make an unpointed read wrong, so the pointing is shown and left
unjudged rather than silently dropped.

GLYPH PAIRING -- THE COUNT GATE. To show the crop's own pixels beside a tile, per-letter boxes are
needed, and they are derived by COUNTING ink columns, never by recognising a letter. Three rungs, tried
in order, per span: LETTER (column_runs at gap_min=2/run_min=2 on the whole crop; fires only when the
run count equals the consonant count, paired right-to-left) > WORD (the cut's own word-run recipe,
gap_min=10/run_min=8, matching `cut_truth_set_crops.py` exactly; fires when the run count equals the
row's word count, each word's tiles sharing one image of its own run) > NONE (no pairing at all; the
whole crop is shown once, magnified, above the tiles). A letter rung firing is a COUNT AGREEMENT, not a
proof that the pairing is correct -- the page says so in one sentence, and this file does not tune
`gap_min` to manufacture more of them (see `GAP_MIN_SWEEP` below: swept and recorded, never shipped).

JUDGMENT CALLS MADE WHERE THE SPEC'S WORDING DID NOT RESOLVE CLEANLY (flagged here and in the run
report, not hidden):
  - The spec's inline formula for the consonant-tile-count assertion, `len([c for c in cand if not
    combining])`, literally includes ASCII spaces (space is not a combining mark). Every multi-word
    candidate in this set has at least one literal space in `hebrew`, so the literal formula would
    fail on every multi-word row. `row["letters"]` is already the authoritative consonant-only count
    (verified against several multi-word rows by hand before writing this), so the assertion actually
    enforced is `len(consonant tiles) == count of (cand chars that are not whitespace and not
    combining) == row["letters"]` -- the sensible reading, not the literal one.
  - Gap tiles are never paired to a glyph image under any rung. `column_runs` only returns INKED ranges,
    so there is no "run" an absence-of-ink tile could sensibly pair to, and the word rung's "tile GROUP"
    language names only a word's own consonant tiles. A gap tile is always a pure control (check/cross +
    its two-button palette); the signer judges it against the already-shown neighbouring images.
  - The word rung's literal condition compares the computed word-run count against `row["words"]`
    (the TRUTH row's own claimed count). Grouping tiles by WORD, though, has to walk the actual
    `cand.split()` token list. On the handful of rows already flagged `candidate_word_count_disagrees`
    this file additionally requires the computed run count to equal `len(words)` too, so a flagged row
    can never zip two different-length lists and crash; it falls through to the NONE rung instead.
    `gap_min` itself is never tuned to chase this -- see above.

THE "NO SECOND READ" FINDING (coordinator amendment, 2026-10-04, superseding the spec's own "expect
almost none" wording): of the four alternative-reads files this module loads, exactly one of these 74
spans (`p657:n0`) has any stored read at all, and all of its reads were taken at aperture `A1_notebox`
(the full note strip) rather than this set's `A2_spanbox` crop -- different pixels. A read is evidence
only about the crop it actually saw, so an A1_notebox read is not evidence about an A2_spanbox tile. The
loader therefore filters candidate reads by aperture and the usable count is 0 of 74 by measurement, not
by a missing feature; the box on the page is unconditional, not an `if N==0` branch, and its numbers are
rendered from what was measured rather than typed as prose. The per-tile alternatives-rendering path
stays in the code, exercised by nothing on THIS data -- it would be exercised by a second read of the
same A2_spanbox crops, at PAD=12, on an endpoint that has not yet been run (e.g. a context-axes or
frontier-OR pass pointed at this set's own crop directory instead of the 19-span one).

TODO_exemplars: there is no per-letter fount exemplar library -- only one card exists under
`audits/cards/`. So there is no exemplar row on any tile here. The way to build one, when there is
reason to, is `hebrew_glyph_card.positions(truth, letter)` over the ratified (signed) signatures, which
gives every occurrence of a letter as (word_no, glyph_from_right) pairs that can be cropped from their
own spans. Not attempted here, and not faked with a system font.

RUN DISCIPLINE. `git_state()` taken at start and end, `provisional()` exactly as `truth_set_sheet.py`
computes it, and the run prints the same clean/provisional verdict line via `clean_run.banner`. No
network calls of any kind, ever. Nothing is written outside `audits/`.

PASS 2 (`--pass2`, 2026-10-04, default off -- without it this file's output is byte-identical to
`5a0a65b`'s). Pass 1 signed all 74 but held 26 for reasons about the CANDIDATE TEXT, not the box
(`abstain_candidate_short`, `abstain_candidate_wrong`, `incomplete_unstated` -- see
`PASS2_DISPOSITIONS` below). Pass 2 sheets exactly that derived population, a second time, with the
full note crop beside each span crop so a human can see whether the BOX is what is actually wrong.

PASS 2 JUDGMENT CALLS (flagged here, as the module's own convention requires):
  - The spec's prose says to derive the per-row label from the ingest's "disposition and note_labels".
    The ingest row schema has no `note_labels` key; the field that carries this is `note_classes`
    (confirmed against `signing_pass1_ingest_0401b636ffa7bf1a.json`). `note_classes` is used.
  - Note-crop pixels are LINKED (`file://`), never base64-embedded, mirroring this file's own existing
    treatment of `note_context` (guard 4, pre-pass2) and reading Change 2's "no note crop may ever be
    sent to a model" as a reason to keep pixels out of the document's own bytes entirely, not merely out
    of any model's hands after the fact.
  - The pass-2 console uses its own `localStorage` key (`SETID + "_pass2"`), not the pass-1 console's
    bare `SETID` key. Both consoles embed the same `set_sha16`, and sharing one browser-storage key would
    let a pass-2 draft silently intermix with (and overwrite) a pass-1 draft for the same 26 span_ids.
  - The blank starter skeleton (`SKEL_NAME`/`SKEL`) gets its own pass-2 filename too, not just the HTML
    and sidecar the spec names explicitly -- the skeleton is written to disk every run, and sharing the
    pass-1 name would mean a pass-2 run silently narrows it to 26 rows, which is exactly the "loader that
    silently narrows" failure this file's own comments warn against elsewhere.
  - Auto-import (Change 3) runs once, on a browser that has no saved pass-2 progress yet (`restore()`
    returns 0). On a later visit, the signer's own saved pass-2 state is restored instead and the
    auto-import does not re-run -- re-running it on every load would silently overwrite any revision
    made since the first import with the pass-1 baseline again.
  - Change 3's auto-import needs pass 1's own verdict lines embedded in the page (no file prompt, no
    network call), but at least one held row's pass-1 tile verdict (`p493:n3`, abstain_candidate_wrong)
    carries a real Hebrew consonant in its `chose` field, so the embed text itself contains Hebrew --
    the one thing guard 3's Hebrew-leak detector exists to catch. Resolved by extending that guard with
    ONE more precisely-located, independently-asserted exemption (the exact `json.dumps(PASS1_EMBED_TEXT)`
    substring, stripped before the leak check runs), mirroring its existing `data-cand`/palette
    exemptions, plus a companion round-trip guard that the embed parses back to exactly the selected
    span_ids with matching crop_sha16 -- additive (growing the accounted-for set), never a weakening of
    what the guard forbids everywhere else.
"""
import argparse
import base64
from collections import Counter
import hashlib
import html
import io
import json
import os
import pathlib
import re
import sys
import time
import unicodedata

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "scripts"))
from PIL import Image, ImageDraw                                          # noqa: E402
import hebrew_aperture_diag as HAD                                        # noqa: E402
import nikud_gate                                                         # noqa: E402
import apparatus_signature_rule as RULE                                   # noqa: E402  the one source of the rule
from clean_run import git_state, provisional, banner                      # noqa: E402
import cv_footnote_presplit as ps                                        # noqa: E402  Lane A's, read-only
import note_line_region as NLR                                           # noqa: E402  Lane A's, read-only
import assembler as ASM                                                  # noqa: E402  Lane A's, read-only

_ARGP = argparse.ArgumentParser()
_ARGP.add_argument("--pass2", action="store_true",
                    help="sheet only the ingest-held rows (abstain_candidate_short, "
                         "abstain_candidate_wrong, incomplete_unstated) with the full note crop beside "
                         "the span crop. Without it, output is byte-identical to 5a0a65b.")
_ARGP.add_argument("--pass3", action="store_true",
                    help="sheet only the rows pass 2's ingest held as contradicted_prose_vs_structure, with "
                         "insertion verdicts, the sic verdict and the prose refusal. Mutually exclusive "
                         "with --pass2. Without either, output is byte-identical to 5a0a65b.")
_ARGP.add_argument("--out-dir", default=None,
                    help="directory the HTML, sidecar, skeleton and note crops are WRITTEN to (default: "
                         "the audits directory). Inputs are always read from the audits directory. Lets a "
                         "mode be run for verification without touching tracked files there.")
ARGS = _ARGP.parse_args()
if ARGS.pass2 and ARGS.pass3:
    _ARGP.error("--pass2 and --pass3 are mutually exclusive")
PASS2 = ARGS.pass2
PASS3 = ARGS.pass3
PASS23 = PASS2 or PASS3
OUT_DIR = pathlib.Path(ARGS.out_dir) if ARGS.out_dir else HAD.DATA

# The check counter (Part F). A bare assert aborts loudly but is invisible to a COUNT: this counts every
# check made by the identity pins and by pass 3's own guards, and the run refuses to finish unless the
# number equals EXPECTED_CHECKS for its mode. (The older bare asserts below are unchanged and still abort.)
CHECKS = 0
EXPECTED_CHECKS_BY_MODE = {"default": 4, "pass2": 4, "pass3": 20}
MODE = "pass3" if PASS3 else ("pass2" if PASS2 else "default")
EXPECTED_CHECKS = EXPECTED_CHECKS_BY_MODE[MODE]


def check(cond, msg):
    global CHECKS
    assert cond, msg
    CHECKS += 1


# The same frozen set the sheet signs against. An approval record is named by the pixels it describes,
# and this file reads the SAME truth/cut artifacts the sheet does -- it is a different judgement surface
# over the same 74 spans, not a different set.
SET, SET_N = "0401b636ffa7bf1a", 74
TRUTH_PATH = HAD.DATA / ("truth_set%d_%s.json" % (SET_N, SET))
CUT = HAD.DATA / ("truthset%d_cut_%s.json" % (SET_N, SET))
PRINTED_OFFSET = 88
SKEL_NAME = "glyphsign_%s.jsonl" % SET

# The letter rung's own constants. Fixed by this spec; swept for the record (GAP_MIN_SWEEP below),
# never tuned to manufacture more letter-rung rows.
LETTER_GAP_MIN, LETTER_RUN_MIN = 2, 2
# The word rung reuses the cut's own word-run recipe EXACTLY, so the two agree.
WORD_GAP_MIN, WORD_RUN_MIN = 10, 8
INK_THR = 128
GAP_MIN_SWEEP_VALUES = (1, 2, 3, 4, 5)   # diagnostic only; LETTER_GAP_MIN above is what ships

# Retired 2026-10-04 by Chris's directive, after pass 1: the letter rung was contradicted on three rows and
# confirmed on none, and `p921:n4` shows the mechanism -- a mixed Latin/Hebrew crop supplies roman ink runs
# that make the count agree with the consonant count by accident. This is the shape where a printed rule
# satisfies "is there an inked band": the gate's input cannot tell the kind of thing it is counting. The
# precondition for un-retiring it is a crop KNOWN to be Hebrew-only; there is no such test today.
LETTER_RUNG_RETIRED = True

MAG = 6              # tile/whole-crop magnification, nearest-neighbour
LETTER_CONTEXT_PX = 3

# The aperture this set's crops were cut at (`p<page>_n<idx>_A2_spanbox.png`, confirmed against the cut
# artifact's own crop paths). A stored read is usable only if it was taken at THIS aperture: a read is
# evidence about the pixels it saw, and A1_notebox is a different, much larger crop.
SET_APERTURE = "A2_spanbox"
ALT_FILES = ("hebrew_aperture_reads_20260920.jsonl", "hebrew_local_arms_reads_20260920.jsonl",
             "hebrew_frontier_or_reads_20260927.jsonl", "hebrew_context_axes_reads_20261004.jsonl")

# Pass 1's own signed record (read-only). Change 6 derives the import expectation from THIS file's own
# bytes, never from a literal count -- if the frozen pass-1 artifact ever changed, the expectation would
# change with it rather than silently going stale.
PASS1_NAME = "glyphsign_signed_%s_20261004_pass1.jsonl" % SET
PASS1_PATH = HAD.DATA / PASS1_NAME

# Change 4: pass 1 proved the single `not-hebrew-or-blank` toggle conflated three different-owner faults.
# (value, button label) pairs, in display order.
FAULT_TYPES = (("box-not-hebrew-or-blank", "box: not Hebrew / blank"),
               ("box-wrong-location", "box: wrong location"),
               ("box-edge-cut", "box: edge cut"))
LEGACY_FAULT_VALUE = "not-hebrew-or-blank"

# ---- pass 2 (Change 1): the held-row population, derived from the ingest's own disposition, never a
# literal list of span_ids. (disposition -> why pass 1 held it, for the module docstring / the page itself).
PASS2_DISPOSITIONS = {
    "abstain_candidate_short": "the signer wrote some form of \"a letter is missing\"",
    "abstain_candidate_wrong": "the signer wrote some form of \"the hebrew is wrong\"",
    "incomplete_unstated": "no verdict and no reason",
}
INGEST_NAME = "signing_pass1_ingest_%s.json" % SET
INGEST_PATH = HAD.DATA / INGEST_NAME

# ---- pass 3: the contradicted rows. ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).
# The selection is DERIVED from pass 2's own held_pass2.jsonl; PASS3_EXPECT_IDS is only the ASSERTION
# TARGET the derived set is compared to, never where the selection comes from.
PASS3_DISPOSITION = "contradicted_prose_vs_structure"
PASS3_EXPECT_IDS = {"p493:n3", "p594:n0", "p803:n0"}
HELD2_NAME = "held_pass2.jsonl"
HELD2_PATH = HAD.DATA / HELD2_NAME
INGEST2_REPORT_PATH = HAD.DATA / ("INGEST_pass2_%s.md" % SET)
# Chris's signed pass-2 export: a record of a human's yes, so it is named by what it describes and
# STORED, never referenced where it happened to land. The unsuffixed name in this directory is the blank
# starter SKELETON -- a different file with the same stem, and that fixed-filename collision is how an
# earlier approval record was destroyed. The signed copy therefore carries its own content hash in its
# name and the build pins that hash too, so the name and the bytes have to agree.
PASS2_EXPORT_SHA16 = "3285d39a12c14e6a"
PASS2_EXPORT_NAME = "glyphsign_%s_pass2_26span_signed_%s.jsonl" % (SET, PASS2_EXPORT_SHA16[:8])
PASS2_EXPORT_PATH = HAD.DATA / PASS2_EXPORT_NAME
# Order item 4, already adjudicated by Chris: the project's first sic instance. Printed form, expectation
# and reason are SEEDED as editable defaults; the verdict itself stays his click.
SIC_SEEDS = {"p594:n0": {"printed": u"\u05d4", "expected": u"\u05d7", "reason": u"Exod 31:5 / fabrefactione"}}
EXP_SRC_NAME = PASS2_EXPORT_NAME if PASS3 else PASS1_NAME

# Change 2's cut recipe needs the native page and the book profile -- the same two inputs
# `wrong_line_trace.py` uses, which is known to reach all 74. Loaded/used only under --pass2.
PAGE = "C:/Users/cnogr/git/dr-voluminous/commentary/volume1/page%d_image1.png"
PROF_PATH = os.path.join(_HERE, "book_profile.gill.yaml")

# The note-box overlay colour: used for NOTHING else on this page (guard asserts it against the
# stylesheet text below), so a human can always tell the overlay from the page's own styling.
NOTECROP_BOX_HEX = "#ff00ff"
NOTECROP_BOX_RGB = (255, 0, 255)
NOTECROP_DIR_NAME = "notecrops_%s_pass2" % SET

# 22 base consonants + 5 final forms. A DERIVED list (guard 6 asserts the rendered palette against
# len(CONSONANTS), never against the literal number 27).
_BASE_LETTERS = u"אבגדהוזחטיכל" \
                u"מנסעפצקרשת"
_FINAL_FORMS = u"ךםןףץ"
CONSONANTS = tuple(_BASE_LETTERS + _FINAL_FORMS)

# Readable Hebrew / Hebrew presentation forms / Greek -- the same ranges `truth_set_sheet.py` withholds
# against, reused here as the "did a stray glyph leak outside its labelled slot" detector instead.
READABLE = re.compile(u"[֐-׿יִ-ﭏͰ-Ͽἀ-῿]")
_PROBE = u"אב"   # a literal Hebrew pair, so READABLE is proved to fire on SOMETHING first.
HB_CAND_ATTR = re.compile(r'data-cand="([^"]*)"')

GIT_START = git_state(_HERE)


# ---- loaders ------------------------------------------------------------------------------------------

def _load_json(path):
    return json.load(io.open(str(path), encoding="utf-8"))


truth_doc = _load_json(TRUTH_PATH)
assert truth_doc.get("provisional") is False, "the truth artifact is PROVISIONAL -- not an approval record"
assert truth_doc["set_sha16"] == SET and truth_doc["n"] == SET_N, \
    "the truth artifact is not the frozen set: %r n=%r" % (truth_doc["set_sha16"], truth_doc["n"])
TRUTH_ROWS = {r["span_id"]: r for r in truth_doc["rows"]}
assert len(TRUTH_ROWS) == SET_N, \
    "the truth artifact carries %d of %d spans" % (len(TRUTH_ROWS), SET_N)

cut_doc = _load_json(CUT)
assert cut_doc.get("provisional") is False, "the cut artifact is PROVISIONAL -- not an approval record"
assert cut_doc["set_sha16"] == SET and cut_doc["n"] == SET_N, \
    "the cut artifact is not the frozen set: %r n=%r" % (cut_doc["set_sha16"], cut_doc["n"])
CUT_ROWS = {r["span_id"]: r for r in cut_doc["rows"] if r.get("crop")}
assert len(CUT_ROWS) == SET_N, \
    "the cut artifact would describe %d of %d spans; a loader that silently narrows is how the " \
    "19-span approval was lost" % (len(CUT_ROWS), SET_N)
assert set(TRUTH_ROWS) == set(CUT_ROWS), \
    "the truth and cut artifacts disagree on which spans are in the set"

SPAN_IDS = sorted(TRUTH_ROWS)
assert len(SPAN_IDS) == SET_N == 74, "the frozen set is not 74 spans"

_sealed_hit = sorted(set(HAD.SEALED_TRUTH) & set(SPAN_IDS))
assert not _sealed_hit, \
    "span(s) %s are in HAD.SEALED_TRUTH -- sealed pages are SPENT and must not be re-signed" % _sealed_hit

# ---- pass 2 (Change 1): derive the held-row selection from the ingest's own disposition -----------------
PASS2_SELECTED_IDS = SPAN_IDS            # the default-mode "selection" is the whole frozen set
PASS2_DISPOSITION_OF = {}                # span_id -> (disposition, note_classes); empty outside --pass2
if PASS2:
    assert INGEST_PATH.exists(), \
        "--pass2 needs the pass-1 ingest %s, which is not on disk at %s" % (INGEST_NAME, HAD.DATA)
    _ingest_doc = _load_json(INGEST_PATH)
    assert _ingest_doc.get("set_sha16") == SET and _ingest_doc.get("n") == SET_N, \
        "the ingest is not over the frozen %d-span set: set_sha16=%r n=%r" \
        % (SET_N, _ingest_doc.get("set_sha16"), _ingest_doc.get("n"))
    _ingest_rows = _ingest_doc["rows"]
    assert len(_ingest_rows) == SET_N, \
        "the ingest carries %d of %d rows" % (len(_ingest_rows), SET_N)
    _ingest_dispo_counts = Counter(r["disposition"] for r in _ingest_rows)
    PASS2_DISPOSITION_OF = {r["span_id"]: (r["disposition"], r.get("note_classes") or [])
                             for r in _ingest_rows}
    PASS2_SELECTED_IDS = sorted(sid for sid, (dispo, _cls) in PASS2_DISPOSITION_OF.items()
                                 if dispo in PASS2_DISPOSITIONS)
    assert PASS2_SELECTED_IDS, \
        "the derived pass-2 selection is empty -- %s matched nothing in the ingest" \
        % sorted(PASS2_DISPOSITIONS)
    _not_in_74 = sorted(set(PASS2_SELECTED_IDS) - set(SPAN_IDS))
    assert not _not_in_74, "pass-2 selected span(s) %s are not in the frozen 74" % _not_in_74
    _sealed_in_selection = sorted(set(HAD.SEALED_TRUTH) & set(PASS2_SELECTED_IDS))
    assert not _sealed_in_selection, \
        "pass-2 selected span(s) %s are in HAD.SEALED_TRUTH -- sealed pages are SPENT" \
        % _sealed_in_selection
    # Assert the count against the INGEST'S OWN per-disposition tally, not against a literal 26: if the
    # ingest ever changes, this fails loudly instead of silently sheeting a different population.
    _expect_n = sum(_ingest_dispo_counts.get(d, 0) for d in PASS2_DISPOSITIONS)
    assert len(PASS2_SELECTED_IDS) == _expect_n, \
        "the pass-2 selection has %d span(s) but the ingest's own disposition_counts for %s sum to %d" \
        % (len(PASS2_SELECTED_IDS), sorted(PASS2_DISPOSITIONS), _expect_n)
    # Guard list item: the two consoles' disk artifacts can never be confused with each other, including
    # the blank starter skeleton (the spec names the HTML and the sidecar explicitly; the skeleton is a
    # third disk artifact this file already writes every run, and sharing its name would silently narrow
    # it to 26 rows -- see the module docstring's PASS 2 JUDGMENT CALLS).
    SKEL_NAME = "glyphsign_%s_pass2_%dspan.jsonl" % (SET, len(PASS2_SELECTED_IDS))

PASS3_HELD = {}            # span_id -> pass 2's held row (disposition, note, why_held); empty outside --pass3
if PASS3:
    check(HELD2_PATH.exists(), "--pass3 needs pass 2's %s at %s" % (HELD2_NAME, HAD.DATA))
    _held_rows = [json.loads(_l) for _l in io.open(str(HELD2_PATH), encoding="utf-8") if _l.strip()]
    PASS3_HELD = {r["span_id"]: r for r in _held_rows if r.get("disposition") == PASS3_DISPOSITION}
    PASS2_SELECTED_IDS = sorted(PASS3_HELD)
    check(len(PASS2_SELECTED_IDS) > 0, "the derived pass-3 selection is empty -- %r matched nothing in %s"
          % (PASS3_DISPOSITION, HELD2_NAME))
    check(INGEST2_REPORT_PATH.exists(), "pass 2's ingest report %s is missing" % INGEST2_REPORT_PATH.name)
    _rx_ct = re.search(r"- `%s` (\d+):" % PASS3_DISPOSITION,
                       io.open(str(INGEST2_REPORT_PATH), encoding="utf-8").read())
    check(_rx_ct is not None, "the ingest report does not state a count for %r" % PASS3_DISPOSITION)
    check(len(PASS2_SELECTED_IDS) == int(_rx_ct.group(1)),
          "the derived selection has %d row(s) but the ingest reported %s for %r"
          % (len(PASS2_SELECTED_IDS), _rx_ct.group(1), PASS3_DISPOSITION))
    check(set(PASS2_SELECTED_IDS) == PASS3_EXPECT_IDS,
          "the derived set differs from the expected one: only-derived %s, only-expected %s"
          % (sorted(set(PASS2_SELECTED_IDS) - PASS3_EXPECT_IDS), sorted(PASS3_EXPECT_IDS - set(PASS2_SELECTED_IDS))))
    assert not (set(PASS2_SELECTED_IDS) - set(SPAN_IDS)), "a pass-3 span is not in the frozen 74"
    assert not (set(HAD.SEALED_TRUTH) & set(PASS2_SELECTED_IDS)), "a pass-3 span is in HAD.SEALED_TRUTH"
    SKEL_NAME = "glyphsign_%s_pass3_%dspan.jsonl" % (SET, len(PASS2_SELECTED_IDS))

RUN_SPAN_IDS = PASS2_SELECTED_IDS
RUN_N = len(RUN_SPAN_IDS)


# ---- pass 2 (Change 4): "pass 1: <verb> -- <reason>", derived from the ingest's own disposition ---------
def _pass1_label(sid):
    """Derived from the ingest's own `disposition` (verb/reason split on the first '_') and corroborated
    against `note_classes` where the ingest carries one -- never re-phrased. Confirmed by hand against
    the actual ingest: the reason half of every held disposition equals note_classes[0] when present
    (empty for incomplete_unstated, whose reason is itself 'unstated')."""
    dispo, classes = PASS2_DISPOSITION_OF[sid]
    verb, _sep, reason = dispo.partition("_")
    if classes:
        assert classes[0] == reason, \
            "%s: disposition %r's reason half (%r) disagrees with its own note_classes %r" \
            % (sid, dispo, reason, classes)
    return u"pass 1: %s — %s" % (verb, reason)


# ---- pass 2 (Change 3): carry pass 1's verdicts in, through the EXISTING import path -- never a second
# importer. PASS1_ROWS is pass 1's own signed file (not the ingest), read-only, for the per-row "your
# note, pass 1" / signed_from readout. PASS1_EMBED_TEXT is the exact on-disk LINES for the selected rows
# only (byte-identical to what a human would get importing the real file by hand), embedded so the page
# can auto-import on load without a network call or a file prompt.
PASS1_ROWS = {}
PASS1_EMBED_TEXT = ""
if PASS2:
    assert PASS1_PATH.exists(), \
        "--pass2 needs pass 1's own signed file %s to carry its verdicts in" % PASS1_NAME
    _p1_lines_kept = []
    with io.open(str(PASS1_PATH), encoding="utf-8") as f:
        for _line in f:
            _stripped = _line.strip()
            if not _stripped:
                continue
            _d = json.loads(_stripped)
            PASS1_ROWS[_d["span_id"]] = _d
            if _d["span_id"] in set(RUN_SPAN_IDS):
                _p1_lines_kept.append(_stripped)
    _missing_p1 = sorted(set(RUN_SPAN_IDS) - set(PASS1_ROWS))
    assert not _missing_p1, \
        "pass 1 (%s) has no row for %s, which pass 2 selected" % (PASS1_NAME, _missing_p1)
    assert len(_p1_lines_kept) == RUN_N, \
        "kept %d of pass 1's own lines for a %d-row selection" % (len(_p1_lines_kept), RUN_N)
    PASS1_EMBED_TEXT = "\n".join(_p1_lines_kept) + "\n"

PASS2_ROWS = {}
PASS2_EMBED_TEXT = ""
if PASS3:
    check(PASS2_EXPORT_PATH.exists(), "--pass3 needs Chris's signed pass-2 export at %s" % PASS2_EXPORT_PATH)
    _p2_bytes = io.open(str(PASS2_EXPORT_PATH), "rb").read()
    check(hashlib.sha256(_p2_bytes).hexdigest()[:16] == PASS2_EXPORT_SHA16,
          "the pass-2 export's sha16 is %s, not the %s the pass-2 ingest recorded -- not the file Chris signed"
          % (hashlib.sha256(_p2_bytes).hexdigest()[:16], PASS2_EXPORT_SHA16))
    _p2_kept = []
    for _line in _p2_bytes.decode("utf-8").splitlines():
        _stripped = _line.strip()
        if not _stripped:
            continue
        _d = json.loads(_stripped)
        PASS2_ROWS[_d["span_id"]] = _d
        if _d["span_id"] in set(RUN_SPAN_IDS):
            _p2_kept.append(_stripped)
    check(len(_p2_kept) == RUN_N and set(PASS2_ROWS) >= set(RUN_SPAN_IDS),
          "kept %d of pass 2's own lines for a %d-row selection" % (len(_p2_kept), RUN_N))
    PASS2_EMBED_TEXT = "\n".join(_p2_kept) + "\n"

# ---- pass 2 (Change 2): the full note crop, cut exactly the way wrong_line_trace.py does (Lane A's
# substrate, read-only -- this file only CALLS ps.presplit / NLR.note_line_regions). Only loaded/used
# under --pass2; a book-profile or native-page problem must never touch the default-mode run.
# Pass 3 writes its note crops into a pass3/ subdirectory of the EXISTING note-crop directory (so nothing
# new appears next to the tracked files, the PNGs are gitignored, and the existing WHY.txt governs them).
NOTECROP_DIR = (OUT_DIR / NOTECROP_DIR_NAME / "pass3") if PASS3 else (OUT_DIR / NOTECROP_DIR_NAME)
NOTECROP_WHY_DIR = NOTECROP_DIR.parent if PASS3 else NOTECROP_DIR
NOTECROP_WHY = ("These are NOTE-REGION crops, for local human review only. No note crop may ever be sent "
                "to a model -- the span-box aperture (A2_spanbox) is the only aperture any arm reads.")
_PAGE_BAND_CACHE = {}
NOTE_CROP_INFO = {}   # span_id -> {note_crop_sha16, native_wh, box_in_note_crop, box_inside_note, path}

if PASS23:
    PROF = ASM.load_profile(PROF_PATH)
    assert PROF, "no book profile at %s -- note_line_regions would take None and die on .get" % PROF_PATH

    NOTECROP_DIR.mkdir(parents=True, exist_ok=True)
    if PASS3:
        # the EXISTING WHY.txt governs pass 3's subdirectory; write one only where none exists (a scratch
        # --out-dir), never rewrite the tracked one.
        if not (NOTECROP_WHY_DIR / "WHY.txt").exists():
            io.open(str(NOTECROP_WHY_DIR / "WHY.txt"), "w", encoding="utf-8").write(NOTECROP_WHY + "\n")
    else:
        io.open(str(NOTECROP_DIR / "WHY.txt"), "w", encoding="utf-8").write(NOTECROP_WHY + "\n")

    def _page_band(page):
        if page not in _PAGE_BAND_CACHE:
            _strip, _info = ps.presplit(PAGE % page, upscale=1)
            assert _strip is not None, \
                "presplit returned no strip for page %d -- --pass2 needs the native page PNG" % page
            _PAGE_BAND_CACHE[page] = _strip.convert("L")
        return _PAGE_BAND_CACHE[page]

    for _sid2 in RUN_SPAN_IDS:
        _tr2 = TRUTH_ROWS[_sid2]
        _band2 = _page_band(_tr2["page"])
        _regions2, _st2 = NLR.note_line_regions(_band2, _tr2["notes_on_page"], PROF)
        assert _regions2 is not None, \
            "%s: note_line_regions abstained (%s) -- the spec says this recipe is known to reach all 74" \
            % (_sid2, _st2)
        assert 0 <= _tr2["note_index"] - 1 < len(_regions2), \
            "%s: note_index %d is out of range for %d region(s) found on page %d" \
            % (_sid2, _tr2["note_index"], len(_regions2), _tr2["page"])
        _reg2 = _regions2[_tr2["note_index"] - 1]
        _segs2 = _reg2.get("segments") or [_reg2]
        _x0 = min(s["ins"] for s in _segs2)
        _x1 = max(s["x1"] for s in _segs2)
        _y0 = min(l[0] for s in _segs2 for l in s["lines"])
        _y1 = max(l[1] for s in _segs2 for l in s["lines"])
        _note_crop = _band2.crop((_x0, _y0, _x1, _y1))
        _nw, _nh = _note_crop.size
        assert _nw > 0 and _nh > 0, "%s: note crop is zero-area (%d x %d)" % (_sid2, _nw, _nh)

        _box_strip = list(TRUTH_ROWS[_sid2]["box"])
        _rel_box = [_box_strip[0] - _x0, _box_strip[1] - _y0, _box_strip[2] - _x0, _box_strip[3] - _y0]
        _box_inside = (_rel_box[0] >= 0 and _rel_box[1] >= 0
                       and _rel_box[2] <= _nw and _rel_box[3] <= _nh
                       and _rel_box[0] < _rel_box[2] and _rel_box[1] < _rel_box[3])

        _overlay = _note_crop.convert("RGB")
        _draw = ImageDraw.Draw(_overlay)
        # The overlay is a RECORD for a human, never evidence -- drawn even when the box falls (partly)
        # outside the crop, which PIL tolerates (it simply clips the line to the canvas).
        _draw.rectangle([_rel_box[0], _rel_box[1], _rel_box[2] - 1, _rel_box[3] - 1],
                         outline=NOTECROP_BOX_RGB, width=1)

        _buf = io.BytesIO()
        _overlay.save(_buf, format="PNG")
        _data = _buf.getvalue()
        _nc_sha16 = hashlib.sha256(_data).hexdigest()[:16]
        _nc_path = NOTECROP_DIR / ("notecrop_%s.png" % _sid2.replace(":", "_"))
        io.open(str(_nc_path), "wb").write(_data)

        NOTE_CROP_INFO[_sid2] = {"note_crop_sha16": _nc_sha16, "native_wh": [_nw, _nh],
                                  "box_in_note_crop": _rel_box, "box_inside_note": _box_inside,
                                  "path": _nc_path}

    assert set(NOTE_CROP_INFO) == set(RUN_SPAN_IDS), \
        "note crops were built for %d of %d selected rows" % (len(NOTE_CROP_INFO), RUN_N)


def _furl(p):
    """A LOCAL PATH, NOT PIXELS -- see `truth_set_sheet._furl`. Note-box and page pixels never leave
    this machine; only a file:// path is carried, and that is asserted over the emitted bytes below."""
    return "file:///" + str(p).replace("\\", "/")


def _uri_bytes(path):
    """The crop's OWN, UNMODIFIED file bytes, base64-embedded. This is the one image per row that must
    be byte-identical to the file on disk, so the `_mid64` liveness check below (carried over from the
    sheet) has something real to find."""
    return "data:image/png;base64," + base64.b64encode(io.open(str(path), "rb").read()).decode("ascii")


def _uri_im(im):
    b = io.BytesIO()
    im.save(b, format="PNG")
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode("ascii")


def _gray(path):
    return np.asarray(Image.open(str(path)).convert("L"))


# ---- the count gate: column ink runs, never letter recognition ----------------------------------------

def column_runs(gray, gap_min, run_min, ink_thr=INK_THR):
    """Maximal inked column ranges [(x0, x1), ...], inclusive, separated by >= gap_min empty columns,
    each >= run_min wide. The same idiom as `cut_truth_set_crops.word_runs`, generalised to return the
    ranges themselves (needed to crop a tile) rather than just their widths, and parameterised so the
    letter rung (gap_min=2, run_min=2) and the word rung (gap_min=10, run_min=8, matching
    `cut_truth_set_crops.py` exactly) can share one function. Counts ink; never recognises a letter."""
    ink_cols = (gray < ink_thr).any(axis=0)
    out, cur, gap = [], None, 0
    for x, v in enumerate(ink_cols):
        if v:
            if cur is None:
                cur = x
            gap = 0
        elif cur is not None:
            gap += 1
            if gap >= gap_min:
                out.append((cur, x - gap))
                cur, gap = None, 0
    if cur is not None:
        out.append((cur, len(ink_cols) - 1))
    return [r for r in out if r[1] - r[0] >= run_min]


def _crop_slice_uri(im, x0, x1, context=0, mag=MAG):
    """A vertical column slice [x0-context, x1+context] of `im`, full height, magnified by nearest
    neighbour. A smoothed upscale would invent strokes that are not on the page."""
    w, h = im.size
    cx0 = max(0, x0 - context)
    cx1 = min(w, x1 + context + 1)
    sub = im.crop((cx0, 0, cx1, h))
    sub = sub.resize((max(1, sub.width * mag), max(1, sub.height * mag)), Image.NEAREST)
    return _uri_im(sub)


def _whole_crop_uri(im, mag=MAG):
    return _crop_slice_uri(im, 0, im.size[0] - 1, context=0, mag=mag)


# ---- the tile model: consonants, points, gaps ----------------------------------------------------------

def split_consonants_and_points(cand):
    """([consonant_chars_in_order], n_points) for the whole candidate, skipping whitespace, by
    `unicodedata.combining` exactly as `hebrew_glyph_card.strip_nikud` (~line 242) does it. Reused, not
    reimplemented: this is the SAME test, just kept per-character instead of joined into a string."""
    cons, n_points = [], 0
    for c in cand:
        if c.isspace():
            continue
        if unicodedata.combining(c):
            n_points += 1
        else:
            cons.append(c)
    return cons, n_points


def build_tiles(row_truth):
    """[{"i", "kind", "word_i"(or None for a gap), "cand"(consonant char or None)}], in printed order:
    word 1's consonants, a gap, word 2's consonants, a gap, ... Word 1 is the rightmost word and, within
    it, character 1 is its rightmost glyph -- storage order already IS right-to-left reading order for
    this fount (see `hebrew_glyph_card.words`/`where`)."""
    cand = row_truth["hebrew"]
    words = cand.split()
    tiles = []
    i = 0
    for wi, w in enumerate(words):
        for c in w:
            if unicodedata.combining(c):
                continue
            tiles.append({"i": i, "kind": "consonant", "word_i": wi, "cand": c})
            i += 1
        if wi < len(words) - 1:
            tiles.append({"i": i, "kind": "gap", "word_i": None, "cand": None})
            i += 1
    return tiles, words


# ---- alternatives: aperture-filtered, consonant-wise, length-mismatch-safe ----------------------------

def load_alternative_reads():
    """{span_id: [reads]} for every stored read in the four named files whose span_id is one of ours,
    REGARDLESS of aperture -- the raw population, used for the liveness check. Each read keeps
    `aperture`, `raw`/`gated`, and the file it came from."""
    by_span = {}
    seen_files, total_lines = 0, 0
    for fn in ALT_FILES:
        path = HAD.DATA / fn
        if not path.exists():
            continue
        seen_files += 1
        with io.open(str(path), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                total_lines += 1
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                sid = d.get("span_id")
                if sid not in TRUTH_ROWS or "aperture" not in d:
                    continue
                d = dict(d)
                d["_file"] = fn
                by_span.setdefault(sid, []).append(d)
    return by_span, seen_files, total_lines


def usable_reads_for(span_id, raw_reads_by_span):
    """Reads for `span_id` taken at THIS set's aperture only -- a read is evidence about the pixels it
    saw, and an A1_notebox read is not evidence about an A2_spanbox tile."""
    return [d for d in raw_reads_by_span.get(span_id, []) if d.get("aperture") == SET_APERTURE]


def aligned_alternatives(cand, usable_texts):
    """Per consonant-tile-index, the set of alternative consonants offered where usable reads disagree
    with the candidate at that position, after `nikud_gate.strip_nikud` on both sides. Needs >=2 usable
    reads to say anything. A length mismatch after stripping is worse than no alternative (a misaligned
    comparison), so it shows none and the row is flagged `alternatives: "length-mismatch"` instead.
    NOT exercised by this run's data (0 usable reads anywhere) -- see the module docstring for what
    would exercise it."""
    if len(usable_texts) < 2:
        return {}, None
    cand_cons = nikud_gate.strip_nikud(cand).replace(" ", "")
    stripped = [nikud_gate.strip_nikud(t or "").replace(" ", "") for t in usable_texts]
    if any(len(s) != len(cand_cons) for s in stripped):
        return {}, "length-mismatch"
    out = {}
    for pos in range(len(cand_cons)):
        alts = {s[pos] for s in stripped if s[pos] != cand_cons[pos]}
        if alts:
            out[pos] = sorted(alts)
    return out, None


RAW_READS_BY_SPAN, _ALT_FILES_SEEN, _ALT_LINES_SEEN = load_alternative_reads()
assert _ALT_FILES_SEEN == len(ALT_FILES), \
    "only %d of %d alternative-reads files were found under %s -- the loader would silently report " \
    "zero on a bad path, which is a probe that misses passing on nothing" \
    % (_ALT_FILES_SEEN, len(ALT_FILES), HAD.DATA)

_raw_reads_in_set = {sid: reads for sid, reads in RAW_READS_BY_SPAN.items() if sid in TRUTH_ROWS}
READS_SEEN = sum(len(v) for v in _raw_reads_in_set.values())
READS_REJECTED = sum(1 for reads in _raw_reads_in_set.values() for d in reads
                     if d.get("aperture") != SET_APERTURE)
READS_USABLE = READS_SEEN - READS_REJECTED
# LIVENESS, MANDATORY (coordinator amendment, 2026-10-04): the loader must actually have opened the
# files and actually have seen the six known reads, or a silently-wrong glob would report zero and look
# identical to an honest zero. Hardcoding 6 as a floor is intended -- if a future run has fewer,
# something broke.
assert READS_SEEN >= 6, \
    "the loader saw only %d read(s) for spans in this set; expected >= 6 (p657:n0 alone has 6) -- a " \
    "loader that silently found nothing must fail, not report zero" % READS_SEEN
assert "p657:n0" in _raw_reads_in_set, \
    "p657:n0 is not among the span_ids the loader saw any read for -- the known population is missing"

ALT_BY_SPAN, ALT_LENGTH_MISMATCH = {}, set()
for _sid in RUN_SPAN_IDS:
    _usable = usable_reads_for(_sid, RAW_READS_BY_SPAN)
    _texts = [d.get("gated") or d.get("raw") or "" for d in _usable]
    _alts, _flag = aligned_alternatives(TRUTH_ROWS[_sid]["hebrew"], _texts)
    if _alts:
        ALT_BY_SPAN[_sid] = _alts
    if _flag == "length-mismatch":
        ALT_LENGTH_MISMATCH.add(_sid)

SPANS_WITH_2PLUS_USABLE = sum(1 for sid in RUN_SPAN_IDS if len(usable_reads_for(sid, RAW_READS_BY_SPAN)) >= 2)
TILES_OFFERING_ALTERNATIVE = sum(len(v) for v in ALT_BY_SPAN.values())
assert SPANS_WITH_2PLUS_USABLE == 0, \
    "expected 0 of %d spans with >=2 usable (A2_spanbox) reads on this run; got %d -- the alternatives " \
    "path IS live now and the page's unconditional 'no second read' box is no longer true" \
    % (RUN_N, SPANS_WITH_2PLUS_USABLE)


# ---- per-row pairing: letter rung > word rung > none ---------------------------------------------------

RUNG_COUNTS = {"letter": 0, "word": 0, "none": 0}
GAP_MIN_SWEEP = {gm: 0 for gm in GAP_MIN_SWEEP_VALUES}
WORD_COUNT_DISAGREES = []
LETTER_WOULD_HAVE_FIRED = 0   # change 1: measured even though the rung is retired
ROWS = []  # built records, one per span, in RUN_SPAN_IDS order (== SPAN_IDS order outside --pass2)

for sid in RUN_SPAN_IDS:
    tr, cr = TRUTH_ROWS[sid], CUT_ROWS[sid]
    cand = tr["hebrew"]
    cons_chars, n_points = split_consonants_and_points(cand)
    tiles, words = build_tiles(tr)
    consonant_tiles = [t for t in tiles if t["kind"] == "consonant"]
    gap_tiles = [t for t in tiles if t["kind"] == "gap"]

    assert len(consonant_tiles) == len(cons_chars) == tr["letters"], \
        "%s: consonant-tile count (%d) disagrees with the candidate's own non-space, non-combining " \
        "character count (%d) and/or row['letters'] (%d)" \
        % (sid, len(consonant_tiles), len(cons_chars), tr["letters"])
    assert len(gap_tiles) == max(0, len(words) - 1), \
        "%s: %d gap tile(s) for %d word(s)" % (sid, len(gap_tiles), len(words))

    if len(words) != tr["words"]:
        WORD_COUNT_DISAGREES.append(sid)

    for gm in GAP_MIN_SWEEP_VALUES:
        if len(column_runs(_gray(cr["crop"]["path"]), gm, LETTER_RUN_MIN, INK_THR)) == len(cons_chars):
            GAP_MIN_SWEEP[gm] += 1

    gray = _gray(cr["crop"]["path"])
    letter_runs = column_runs(gray, LETTER_GAP_MIN, LETTER_RUN_MIN, INK_THR)
    word_runs_native = column_runs(gray, WORD_GAP_MIN, WORD_RUN_MIN, INK_THR)

    # Change 1: the letter rung is measured but no longer SELECTED. A count agreement is computed exactly
    # as before and recorded per row (`letter_rung_would_have_fired`), so the retirement stays measurable
    # and reversible, but `paired_at` can only land on "word" or "none" while LETTER_RUNG_RETIRED is True.
    letter_rung_would_have_fired = bool(cons_chars) and len(letter_runs) == len(cons_chars)
    if letter_rung_would_have_fired:
        LETTER_WOULD_HAVE_FIRED += 1

    paired_at = "none"
    letter_assign = {}   # tile i -> (x0, x1); stays empty while the rung is retired
    word_assign = {}     # word index -> (x0, x1)
    if (not LETTER_RUNG_RETIRED) and letter_rung_would_have_fired:
        paired_at = "letter"
        rtl = sorted(letter_runs, key=lambda r: -r[0])
        for k, t in enumerate(consonant_tiles):
            letter_assign[t["i"]] = rtl[k]
    elif (len(word_runs_native) == tr["words"] and len(word_runs_native) == len(words)
          and len(words) > 0):
        paired_at = "word"
        rtl_w = sorted(word_runs_native, key=lambda r: -r[0])
        for k in range(len(words)):
            word_assign[k] = rtl_w[k]
    RUNG_COUNTS[paired_at] += 1

    ROWS.append({"sid": sid, "tr": tr, "cr": cr, "cand": cand, "cons_chars": cons_chars,
                 "n_points": n_points, "tiles": tiles, "words": words,
                 "consonant_tiles": consonant_tiles, "gap_tiles": gap_tiles,
                 "paired_at": paired_at, "letter_assign": letter_assign, "word_assign": word_assign,
                 "letter_rung_would_have_fired": letter_rung_would_have_fired,
                 "gray_im": None})

assert sum(RUNG_COUNTS.values()) == RUN_N, "the three rungs do not account for every span in the run"
assert RUNG_COUNTS["letter"] == 0, \
    "the letter rung fired %d time(s) despite LETTER_RUNG_RETIRED -- it is retired because it was " \
    "contradicted 3 times and confirmed never; it must not be selected" % RUNG_COUNTS["letter"]
TOTAL_CONSONANT_TILES = sum(len(r["consonant_tiles"]) for r in ROWS)
TOTAL_GAP_TILES = sum(len(r["gap_tiles"]) for r in ROWS)
TOTAL_TILES = TOTAL_CONSONANT_TILES + TOTAL_GAP_TILES


# ---- change 6: the import expectation, derived read-only from pass 1's own signed file ----------------

def _derive_import_expectation(path, allowed_ids=None):
    """The counts a correct import of `path` must produce, derived from the file itself -- never
    hard-coded, so a change to the frozen pass-1 artifact would change these numbers too. Returns None
    (never invents zeros) if the file is absent.

    `allowed_ids`, when not None, restricts the derivation to rows whose span_id is in that set --
    pass 2 (Change 3) needs the expectation recomputed for the 26-row selection, not the 74-row figures,
    while reusing this same derivation rather than writing a second one."""
    if not path.exists():
        return None
    rows = tiles = confirmed = corrected = disputed = 0
    notes = abstains = legacy_faults = insertions = 0
    with io.open(str(path), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if allowed_ids is not None and d.get("span_id") not in allowed_ids:
                continue
            rows += 1
            dtiles = d.get("tiles") or []
            tiles += len(dtiles)
            for t in dtiles:
                v = t.get("verdict")
                if v == "confirmed":
                    confirmed += 1
                elif v == "corrected":
                    corrected += 1
                elif v == "disputed":
                    disputed += 1
            if d.get("note"):
                notes += 1
            if d.get("abstain"):
                abstains += 1
            if d.get("fault") == LEGACY_FAULT_VALUE or d.get("fault_legacy") == LEGACY_FAULT_VALUE:
                legacy_faults += 1
            insertions += len(d.get("insertions") or [])
    return {"rows": rows, "tiles": tiles, "confirmed": confirmed, "corrected": corrected,
            "disputed": disputed, "notes": notes, "abstains": abstains,
            "legacy_faults": legacy_faults, "insertions": insertions}


IMPORT_EXPECTATION = (_derive_import_expectation(PASS2_EXPORT_PATH, set(RUN_SPAN_IDS)) if PASS3 else
                      _derive_import_expectation(PASS1_PATH, set(RUN_SPAN_IDS) if PASS2 else None))
_EXP_ORDER = ("rows", "tiles", "confirmed", "corrected", "disputed", "notes", "abstains",
              "legacy_faults", "insertions")
if IMPORT_EXPECTATION is not None:
    EXP_LINE = ", ".join(
        "%s %d" % (k.replace("_", " "), IMPORT_EXPECTATION[k]) for k in _EXP_ORDER)
else:
    EXP_LINE = None


# ---- HTML assembly --------------------------------------------------------------------------------------

CSS = """
body{background:#14161a;color:#e6e6e6;font:13px/1.5 system-ui,Segoe UI,sans-serif;margin:0;padding:24px}
h1{font-size:19px;margin:0 0 4px} h2{font-size:15px;margin:28px 0 8px;color:#9fd}
.sub{color:#9aa;font-size:12px} a{color:#9cf}
.note{background:#1b2127;border-left:3px solid #468;padding:10px 14px;margin:14px 0}
.note.loud{border-left-color:#ca6;background:#241c12}
table.sum{border-collapse:collapse;margin:10px 0 18px} table.sum td{padding:2px 12px 2px 0;vertical-align:top}
.row{border-top:1px solid #2a2f37;padding:16px 0}
.row.complete{border-left:3px solid #6a9;padding-left:10px}
.meta code{color:#cda;font-size:11px;word-break:break-all}
.links{margin:6px 0;font-size:11px}
figure{margin:0 10px 10px 0;display:inline-block;vertical-align:top;background:#0d0f12;padding:6px;
 border:1px solid #2a2f37}
figcaption{color:#9aa;font-size:11px;margin-top:4px;max-width:420px}
img{image-rendering:pixelated;background:#fff;display:block;margin-bottom:4px}
.tiles{margin:8px 0}
.tile{display:inline-block;vertical-align:top;margin:3px;padding:6px;background:#0d0f12;
 border:1px solid #333;text-align:center;min-width:34px}
.tile.cons::before{content:attr(data-cand);display:block;font:26px/1.1 "Times New Roman",serif;
 color:#dde;margin-bottom:3px}
.tile.gap{min-width:18px;background:#141414}
.tile.gap::before{content:"\\2194";display:block;color:#889;font-size:16px;margin-bottom:3px}
.tbtn{font:12px system-ui,sans-serif;padding:2px 6px;margin:1px;cursor:pointer;border-radius:3px;
 border:1px solid #556;background:#20232a;color:#dde}
.tbtn.ok{border-color:#4a8}
.tbtn.no{border-color:#a44}
.tile[data-v="confirmed"]{border-color:#4a8;box-shadow:0 0 0 1px #4a8 inset}
.tile[data-v="corrected"]{border-color:#c86;box-shadow:0 0 0 1px #c86 inset}
.tile[data-v="disputed"]{border-color:#a44;box-shadow:0 0 0 1px #a44 inset}
.tile[data-v="deleted"]{border-color:#666;box-shadow:0 0 0 1px #666 inset;opacity:.55}
.tile[data-v="not_in_crop"]{border-color:#c6a;box-shadow:0 0 0 1px #c6a inset}
.tbtn.del{border-color:#876}
.tbtn.nic{border-color:#767;font-size:10px}
.insslot{display:inline-block;vertical-align:top;margin:3px 0}
.insslot .tbtn.ins{background:#14241a;border-color:#4a8;color:#9e9}
.inschip{display:inline-block;background:#1a1612;border:1px solid #654;border-radius:3px;
 padding:2px 5px;margin:2px;font-size:11px;color:#dcb}
.inschip b{font:16px "Times New Roman",serif;color:#eef;margin:0 3px}
.derived{margin:6px 0;padding:6px 8px;background:#121418;border:1px dashed #445;border-radius:4px;
 color:#9bd;font-size:12px}
.derived code{font:18px "Times New Roman",serif;color:#eef;direction:rtl;unicode-bidi:bidi-override}
.legfault{color:#fc9;font-size:11px;margin:2px 0}
.points{margin:6px 0;padding:6px 8px;background:#141a1f;border:1px solid #2c3a46;border-radius:4px}
.points::before{content:attr(data-cand);display:block;direction:rtl;font:22px/1.3 "Times New Roman",serif;
 color:#cda}
.kn{font-size:11px;color:#9aa;margin-left:8px}
.palette{position:fixed;left:50%;bottom:70px;transform:translateX(-50%);background:#1b2127;
 border:2px solid #468;border-radius:6px;padding:10px;z-index:50;max-width:640px;text-align:center}
.pbtn{font:28px/1.2 "Times New Roman",serif;margin:3px;padding:3px 10px;background:#20232a;color:#eef;
 border:1px solid #556;border-radius:3px;cursor:pointer}
.pbtn.canttell,.pbtn.gapchoice{font:13px system-ui,sans-serif;padding:6px 10px}
button.fault{background:#2a1416;color:#ffd9d9;border:1px solid #a44;border-radius:3px;padding:3px 8px;
 font:11px system-ui,sans-serif;cursor:pointer;margin-top:4px}
button.fault.on{background:#a44;color:#fff;font-weight:700}
button.abst{background:#20232a;color:#dde;border:1px solid #556;border-radius:3px;padding:3px 8px;
 font:11px system-ui,sans-serif;cursor:pointer;margin:4px 6px 0 0}
button.abst.on{background:#667;color:#fff;font-weight:700}
input.nt{display:block;width:100%;max-width:520px;box-sizing:border-box;margin:4px 0;padding:5px 8px;
 background:#0c1116;color:#cde;border:1px solid #2c3a46;border-radius:3px;font:12px system-ui,sans-serif}
#bar{position:fixed;right:14px;bottom:14px;background:#1b2127;border:1px solid #468;border-radius:4px;
 padding:8px 12px;font-size:12px;z-index:9}
#bar b{color:#cfe}
#impwarn{color:#fc9;font-size:11px}
"""

# Pass 2 only (Change 2 rule 1): the note crop is NEVER scaled by CSS -- width:auto is its own natural
# size, not a scale rule, and a guard below asserts the stylesheet carries no numeric width/height naming
# .notecrop. The wrap is the horizontally-scrollable container the native-size image sits in. Kept as a
# SEPARATE string, appended only under --pass2, so the default-mode document (and its byte-identity to
# 5a0a65b) cannot be touched by a pass-2-only rule.
CSS_PASS2 = """
.notecrop-wrap{overflow-x:auto;max-width:100%;border:1px solid #2a2f37;background:#0d0f12;padding:6px}
img.notecrop{width:auto;height:auto;display:block}
.badge-outside{color:#fc9}
"""
CSS_PASS3 = """
.tile[data-v="sic"]{border-color:#6ad;box-shadow:0 0 0 1px #6ad inset}
.tbtn.sic{border-color:#6ad;font-size:10px}
.sicform{margin-top:4px;padding:4px;background:#101820;border:1px solid #356;text-align:left;font-size:11px;
 max-width:240px}
.sicin{background:#0c1116;color:#cde;border:1px solid #2c3a46;font:12px system-ui,sans-serif}
.sicmsg{color:#fc9;margin-top:2px}
.inschip[data-v="confirmed"]{border-color:#4a8}
.inschip[data-v="not_in_crop"]{border-color:#c6a}
.inschip[data-v="deleted"]{border-color:#666;opacity:.55}
.inschip .insword{color:#9aa;font-size:10px}
.inschip .insstate{color:#fc9}
.conflict{color:#fdd;background:#2a1416;border-left:3px solid #a44;padding:8px 12px;margin:8px 0}
"""
if PASS23:
    CSS += CSS_PASS2
if PASS3:
    CSS += CSS_PASS3

# The page's own script. Placeholders substituted via .replace(), never %-formatted -- a literal '%' in
# prose crashed a run of the sheet once, and this file carries far more prose than that one did.
#
# Two FULL, SEPARATE scripts, never one script conditionally patched: guard 1 requires the default-mode
# document to be byte-identical to 5a0a65b's, and the importText refactor + new globals (change 3) change
# the TEXT of the script regardless of what values the new placeholders carry. JS_V1 below is verbatim
# 5a0a65b -- untouched, never edited again. JS_PASS2 is the pass-2 console. JS is chosen by mode.
JS_PASS2 = r"""
var RM=__RM__, SETID=__SETID__, N=__N__, SKEL=__SKEL__, EXP=__EXP__, TYPED_FAULTS=__TYPED_FAULTS__,
    LEGACY_FAULT=__LEGACY_FAULT__, STOREKEY=__STOREKEY__, AUTOIMPORT=__AUTOIMPORT__,
    PASS1_EMBED=__PASS1_EMBED__, PASS1_NAME_JS=__PASS1_NAME_JS__,
    ST={}, CUR_S=null, CUR_I=null, PAL_MODE="tile", CUR_SEQ=null, CUR_AFTER=null;
function trow(s){if(!ST[s])ST[s]={tv:{},note:"",fault:"",fault_legacy:"",abst:0,ins:[],insSeq:0};
 if(!ST[s].ins)ST[s].ins=[];if(ST[s].insSeq===undefined)ST[s].insSeq=0;
 if(ST[s].fault_legacy===undefined)ST[s].fault_legacy="";
 return ST[s];}
function tileDiv(s,i){return document.getElementById("t_"+s+"_"+i);}
function setVerdict(s,i,verdict,chose){
 var r=trow(s);r.tv[i]={verdict:verdict,chose:chose||""};
 var td=tileDiv(s,i);if(td)td.setAttribute("data-v",verdict);
 closePalette();upd();}
function tOk(b){setVerdict(b.getAttribute("data-s"),b.getAttribute("data-i"),"confirmed","");}
function tBad(b){var s=b.getAttribute("data-s"),i=b.getAttribute("data-i"),k=b.getAttribute("data-k");
 CUR_S=s;CUR_I=i;PAL_MODE="tile";
 var pal=document.getElementById(k==="gap"?"gpal_gap":"gpal_cons");
 pal.style.display="block";}
function tDel(b){setVerdict(b.getAttribute("data-s"),b.getAttribute("data-i"),"deleted","");}
function tNic(b){setVerdict(b.getAttribute("data-s"),b.getAttribute("data-i"),"not_in_crop","");}
function closePalette(){var a=document.getElementById("gpal_cons"),b=document.getElementById("gpal_gap");
 if(a)a.style.display="none";if(b)b.style.display="none";
 CUR_S=null;CUR_I=null;PAL_MODE="tile";CUR_SEQ=null;CUR_AFTER=null;}
function chooseLetterGlobal(b){
 if(PAL_MODE==="ins"){insSetChoice(b.getAttribute("data-letter"),"consonant");return;}
 if(CUR_S===null)return;setVerdict(CUR_S,CUR_I,"corrected",b.getAttribute("data-letter"));}
function cantTellGlobal(){if(PAL_MODE==="ins")return;if(CUR_S===null)return;setVerdict(CUR_S,CUR_I,"disputed","");}
function chooseGapGlobal(b){if(CUR_S===null)return;setVerdict(CUR_S,CUR_I,"corrected",b.getAttribute("data-choice"));}
function insSpaceGlobal(){if(PAL_MODE==="ins")insSetChoice("space","gap");}
function insKey(a){return a===null?"none":String(a);}
function insSetChoice(chose,kind){if(CUR_S===null||CUR_SEQ===null)return;
 var r=trow(CUR_S),i;for(i=0;i<r.ins.length;i++){if(r.ins[i].seq===CUR_SEQ){
  r.ins[i].kind=kind;r.ins[i].chose=chose;break;}}
 var after=CUR_AFTER;closePalette();renderInsAt(CUR_S,after);upd();}
function openIns(b){var s=b.getAttribute("data-s"),a=b.getAttribute("data-after");
 var after=(a==="none")?null:parseInt(a,10);
 var r=trow(s),seq=r.insSeq++;
 r.ins.push({seq:seq,after_i:after,kind:null,chose:""});
 renderInsAt(s,after);upd();
 CUR_S=s;CUR_SEQ=seq;CUR_AFTER=after;PAL_MODE="ins";
 document.getElementById("gpal_cons").style.display="block";}
function editIns(b){var s=b.getAttribute("data-s"),seq=parseInt(b.getAttribute("data-seq"),10);
 var r=trow(s),i,after=null;
 for(i=0;i<r.ins.length;i++){if(r.ins[i].seq===seq){after=r.ins[i].after_i;break;}}
 CUR_S=s;CUR_SEQ=seq;CUR_AFTER=after;PAL_MODE="ins";
 document.getElementById("gpal_cons").style.display="block";}
function removeIns(b){var s=b.getAttribute("data-s"),seq=parseInt(b.getAttribute("data-seq"),10);
 var r=trow(s),i,after=null;
 for(i=0;i<r.ins.length;i++){if(r.ins[i].seq===seq){after=r.ins[i].after_i;r.ins.splice(i,1);break;}}
 renderInsAt(s,after);upd();}
function renderInsAt(s,after){var el=document.querySelector('.insat[data-s="'+s+'"][data-after="'+insKey(after)+'"]');
 if(!el)return;var r=trow(s),items=(r.ins||[]).filter(function(x){return x.after_i===after;}),h="",i;
 for(i=0;i<items.length;i++){var it=items[i],shown=it.chose?(it.kind==="gap"?"↔":it.chose):"…";
  h+='<span class="inschip">'+(it.chose?("<b>"+shown+"</b>"):"<i>pending</i>")+
   ' <button class="tbtn edit" data-s="'+s+'" data-seq="'+it.seq+'" onclick="editIns(this)">edit</button>'+
   ' <button class="tbtn rm" data-s="'+s+'" data-seq="'+it.seq+'" onclick="removeIns(this)">x</button></span>';}
 el.innerHTML=h;}
function setnote(inp){trow(inp.getAttribute("data-s")).note=inp.value;upd();}
function markFault(b){var s=b.getAttribute("data-s"),t=b.getAttribute("data-ft"),r=trow(s),i;
 r.fault=(r.fault===t)?"":t;
 var btns=document.querySelectorAll('.fault[data-s="'+s+'"]');
 for(i=0;i<btns.length;i++){btns[i].className=(btns[i].getAttribute("data-ft")===r.fault)?"fault on":"fault";}
 upd();}
function absn(b){var s=b.getAttribute("data-s"),r=trow(s);
 r.abst=r.abst?0:1;b.className=r.abst?"abst on":"abst";upd();}
function rowComplete(s){var m=RM[s],r=trow(s),n=m.tiles.length,k=0,i;
 for(i=0;i<n;i++){if(r.tv[m.tiles[i].i]&&r.tv[m.tiles[i].i].verdict)k++;}
 var ins=r.ins||[],j;
 for(j=0;j<ins.length;j++){n++;if(ins[j].chose)k++;}
 return [k,n];}
function hasNotInCrop(s){var m=RM[s],r=trow(s),i;
 for(i=0;i<m.tiles.length;i++){var v=r.tv[m.tiles[i].i];if(v&&v.verdict==="not_in_crop")return true;}
 return false;}
function pointsText(s){var el=document.querySelector('.points[data-s="'+s+'"]');
 return el?el.getAttribute("data-cand"):"";}
function tileShown(s,i,kind){if(kind==="gap")return "space";
 var el=tileDiv(s,i);return el?el.getAttribute("data-cand"):"";}
function tileOut(s,td){var r=trow(s),v=r.tv[td.i]||{verdict:"",chose:""},shown=tileShown(s,td.i,td.kind);
 if(v.verdict==="deleted")return "";
 if(v.verdict==="not_in_crop")return td.kind==="gap"?"[ ]":("["+shown+"]");
 if(v.verdict==="confirmed")return td.kind==="gap"?" ":shown;
 if(v.verdict==="corrected"){if(td.kind==="gap")return v.chose==="space"?" ":"";return v.chose||"?";}
 return "?";}
function insOut(it){if(!it.chose)return "?";return it.kind==="gap"?" ":it.chose;}
function derivedFor(s){var m=RM[s],r=trow(s),out=[],j,k;
 var atNone=(r.ins||[]).filter(function(x){return x.after_i===null;}).sort(function(a,b){return a.seq-b.seq;});
 for(j=0;j<atNone.length;j++)out.push(insOut(atNone[j]));
 for(j=0;j<m.tiles.length;j++){var td=m.tiles[j];out.push(tileOut(s,td));
  var ats=(r.ins||[]).filter(function(x){return x.after_i===td.i;}).sort(function(a,b){return a.seq-b.seq;});
  for(k=0;k<ats.length;k++)out.push(insOut(ats[k]));}
 return out.join("");}
function lines(){
 /* EVERY span, every time -- empty rows included. A partial download dropped over a full one is how
    an approval record dies with every byte in it valid. */
 var K=Object.keys(RM).sort(),L=[],si;
 for(si=0;si<K.length;si++){var s=K[si],m=RM[s],r=trow(s),tiles=[],j;
  for(j=0;j<m.tiles.length;j++){var td=m.tiles[j],v=r.tv[td.i]||{verdict:"",chose:""};
   tiles.push({i:td.i,kind:td.kind,shown:tileShown(s,td.i,td.kind),verdict:v.verdict||"",
    chose:v.chose||"",paired_to:td.paired_to});}
  var kn=rowComplete(s);
  var ins=(r.ins||[]).map(function(x){return {seq:x.seq,after_i:x.after_i,kind:x.kind,chose:x.chose};});
  L.push(JSON.stringify({span_id:s,crop_sha16:m.crop16,candidate_sha16:m.cand16,tiles:tiles,
   insertions:ins,complete:kn[0]===kn[1],abstain:!!r.abst,fault:r.fault||"",
   fault_legacy:r.fault_legacy||"",note:r.note,
   points_shown_not_adjudicated:{text:pointsText(s),n_points:m.n_points,nikud_flag:m.nikud},
   paired_at:m.paired_at,letter_rung_would_have_fired:!!m.letter_fired,
   full_span_pixel_signature:!hasNotInCrop(s),
   derived_consonants:derivedFor(s),derived_from_verdicts:true,
   signed_from:"pixels, candidate shown as consonant tiles, per-tile verdicts",
   signed_in:"glyph signer, in the browser",set_sha16:SETID,sheet:SKEL}));}
 return L.join("\n")+"\n";}
function upd(){var K=Object.keys(RM).sort(),nc=0,ntouch=0,i;
 for(i=0;i<K.length;i++){var s=K[i],kn=rowComplete(s),r=trow(s);
  var rowEl=document.getElementById("row_"+s);
  if(rowEl){var lab=document.getElementById("kn_"+s);
   if(lab)lab.textContent=kn[0]+"/"+kn[1]+" tiles"+
    (hasNotInCrop(s)?" · NOT a full-span pixel signature (not_in_crop present)":"");
   rowEl.className="row"+(kn[0]===kn[1]?" complete":"");}
  var dtxt=document.getElementById("der_txt_"+s);if(dtxt)dtxt.textContent=derivedFor(s);
  if(kn[0]===kn[1])nc++;
  if(kn[0]>0||r.fault||r.abst||r.note||(r.ins&&r.ins.length))ntouch++;}
 document.getElementById("ncomplete").textContent=nc;
 document.getElementById("nleft").textContent=(N-ntouch);
 var a=document.getElementById("dl");
 a.href="data:text/plain;charset=utf-8,"+encodeURIComponent(lines());
 try{localStorage.setItem("gs_"+STOREKEY,JSON.stringify(ST));}catch(e){}}
function applyState(s){var r=ST[s],m=RM[s];if(!r||!m)return;var j;
 for(j=0;j<m.tiles.length;j++){var td=m.tiles[j],v=(r.tv||{})[td.i];
  var el=tileDiv(s,td.i);if(el&&v&&v.verdict)el.setAttribute("data-v",v.verdict);}
 var fbtns=document.querySelectorAll('.fault[data-s="'+s+'"]'),fi;
 for(fi=0;fi<fbtns.length;fi++){
  fbtns[fi].className=(fbtns[fi].getAttribute("data-ft")===r.fault)?"fault on":"fault";}
 var lg=document.querySelector('.legfault[data-s="'+s+'"]');
 if(lg)lg.style.display=r.fault_legacy?"block":"none";
 var ab=document.querySelector('.abst[data-s="'+s+'"]');if(ab&&r.abst)ab.className="abst on";
 var nt=document.querySelector('.nt[data-s="'+s+'"]');if(nt)nt.value=r.note||"";
 var seen={},ij;
 for(ij=0;ij<(r.ins||[]).length;ij++){var ak=insKey(r.ins[ij].after_i);
  if(!seen[ak]){seen[ak]=1;renderInsAt(s,r.ins[ij].after_i);}}}
function restore(){
 /* BEST EFFORT ONLY -- the download is the record, not this. */
 var raw=null;try{raw=localStorage.getItem("gs_"+STOREKEY);}catch(e){raw=null;}
 if(!raw)return 0;var S=null;try{S=JSON.parse(raw);}catch(e){return 0;}
 var K=Object.keys(S),i,k=0;
 for(i=0;i<K.length;i++){var s=K[i];if(!RM[s])continue;ST[s]=S[s];k++;applyState(s);}
 return k;}
function renderImportCheck(rc){var el=document.getElementById("impcheck");if(!el)return;
 if(!EXP){el.textContent="no import expectation available (pass-1 file not found at generation time)";
  return;}
 var keys=["rows","tiles","confirmed","corrected","disputed","notes","abstains","legacy_faults",
  "insertions"],h="",i;
 for(i=0;i<keys.length;i++){var k=keys[i],r=rc[k]||0,e=EXP[k];
  h+=k+": restored "+r+" vs expected "+e+" -- "+(r===e?"PASS":"MISMATCH")+"<br>";}
 el.innerHTML=h;}
function importText(txt,fname){
 /* The whole of the former doImport body, now shared by the file-input path AND pass 2's auto-import
    (Change 3) -- ONE importer, same span_id+crop_sha16 matching, same refusal list, same
    renderImportCheck, whichever path called it. */
 var ln=(txt||"").split("\n"),i,bad=[],k=0;
 var rc={rows:0,tiles:0,confirmed:0,corrected:0,disputed:0,notes:0,abstains:0,legacy_faults:0,
  insertions:0};
 for(i=0;i<ln.length;i++){var s=ln[i].replace(/^\s+|\s+$/g,"");if(!s)continue;
  var d=null;try{d=JSON.parse(s);}catch(e){continue;}
  if(!d.span_id||!RM[d.span_id])continue;
  if(d.crop_sha16!==RM[d.span_id].crop16){bad.push(d.span_id);continue;}
  var rr=trow(d.span_id);rr.tv={};var tj,dtiles=d.tiles||[];
  rc.rows++;rc.tiles+=dtiles.length;
  for(tj=0;tj<dtiles.length;tj++){var tt=dtiles[tj];
   if(tt.verdict){rr.tv[tt.i]={verdict:tt.verdict,chose:tt.chose||""};
    if(tt.verdict==="confirmed")rc.confirmed++;
    else if(tt.verdict==="corrected")rc.corrected++;
    else if(tt.verdict==="disputed")rc.disputed++;}}
  rr.note=d.note||"";if(rr.note)rc.notes++;
  rr.abst=d.abstain?1:0;if(d.abstain)rc.abstains++;
  rr.fault=(TYPED_FAULTS.indexOf(d.fault)>=0)?d.fault:"";
  rr.fault_legacy=d.fault_legacy?d.fault_legacy:((d.fault===LEGACY_FAULT)?LEGACY_FAULT:"");
  if(rr.fault_legacy)rc.legacy_faults++;
  rr.ins=(d.insertions||[]).map(function(x){return {seq:x.seq,after_i:x.after_i,kind:x.kind,
   chose:x.chose||""};});
  rr.insSeq=rr.ins.length?(Math.max.apply(null,rr.ins.map(function(x){return x.seq;}))+1):0;
  rc.insertions+=rr.ins.length;
  applyState(d.span_id);k++;}
 var w=document.getElementById("impwarn");
 w.textContent=bad.length?("NOT restored (crop_sha16 differs -- a re-cut span must not inherit a "+
  "verdict): "+bad.join(", ")):"";
 document.getElementById("impmsg").textContent="imported "+k+" row(s) from "+fname;
 renderImportCheck(rc);
 upd();}
function doImport(inp){
 var f=inp.files&&inp.files[0];if(!f)return;
 var rd=new FileReader();
 rd.onload=function(){importText(rd.result||"",f.name);};
 rd.readAsText(f,"utf-8");}
window.addEventListener("load",function(){var k=restore();
 document.getElementById("rst").textContent=k?("restored "+k+" row(s) from this browser"):
  "nothing restored from this browser";
 if(AUTOIMPORT&&k===0){importText(PASS1_EMBED,PASS1_NAME_JS);}
 upd();});
"""

# JS_V1 -- verbatim 5a0a65b, byte for byte. Do not edit this block; edit JS_PASS2 above instead.
JS_V1 = r"""
var RM=__RM__, SETID=__SETID__, N=__N__, SKEL=__SKEL__, EXP=__EXP__, TYPED_FAULTS=__TYPED_FAULTS__,
    LEGACY_FAULT=__LEGACY_FAULT__,
    ST={}, CUR_S=null, CUR_I=null, PAL_MODE="tile", CUR_SEQ=null, CUR_AFTER=null;
function trow(s){if(!ST[s])ST[s]={tv:{},note:"",fault:"",fault_legacy:"",abst:0,ins:[],insSeq:0};
 if(!ST[s].ins)ST[s].ins=[];if(ST[s].insSeq===undefined)ST[s].insSeq=0;
 if(ST[s].fault_legacy===undefined)ST[s].fault_legacy="";
 return ST[s];}
function tileDiv(s,i){return document.getElementById("t_"+s+"_"+i);}
function setVerdict(s,i,verdict,chose){
 var r=trow(s);r.tv[i]={verdict:verdict,chose:chose||""};
 var td=tileDiv(s,i);if(td)td.setAttribute("data-v",verdict);
 closePalette();upd();}
function tOk(b){setVerdict(b.getAttribute("data-s"),b.getAttribute("data-i"),"confirmed","");}
function tBad(b){var s=b.getAttribute("data-s"),i=b.getAttribute("data-i"),k=b.getAttribute("data-k");
 CUR_S=s;CUR_I=i;PAL_MODE="tile";
 var pal=document.getElementById(k==="gap"?"gpal_gap":"gpal_cons");
 pal.style.display="block";}
function tDel(b){setVerdict(b.getAttribute("data-s"),b.getAttribute("data-i"),"deleted","");}
function tNic(b){setVerdict(b.getAttribute("data-s"),b.getAttribute("data-i"),"not_in_crop","");}
function closePalette(){var a=document.getElementById("gpal_cons"),b=document.getElementById("gpal_gap");
 if(a)a.style.display="none";if(b)b.style.display="none";
 CUR_S=null;CUR_I=null;PAL_MODE="tile";CUR_SEQ=null;CUR_AFTER=null;}
function chooseLetterGlobal(b){
 if(PAL_MODE==="ins"){insSetChoice(b.getAttribute("data-letter"),"consonant");return;}
 if(CUR_S===null)return;setVerdict(CUR_S,CUR_I,"corrected",b.getAttribute("data-letter"));}
function cantTellGlobal(){if(PAL_MODE==="ins")return;if(CUR_S===null)return;setVerdict(CUR_S,CUR_I,"disputed","");}
function chooseGapGlobal(b){if(CUR_S===null)return;setVerdict(CUR_S,CUR_I,"corrected",b.getAttribute("data-choice"));}
function insSpaceGlobal(){if(PAL_MODE==="ins")insSetChoice("space","gap");}
function insKey(a){return a===null?"none":String(a);}
function insSetChoice(chose,kind){if(CUR_S===null||CUR_SEQ===null)return;
 var r=trow(CUR_S),i;for(i=0;i<r.ins.length;i++){if(r.ins[i].seq===CUR_SEQ){
  r.ins[i].kind=kind;r.ins[i].chose=chose;break;}}
 var after=CUR_AFTER;closePalette();renderInsAt(CUR_S,after);upd();}
function openIns(b){var s=b.getAttribute("data-s"),a=b.getAttribute("data-after");
 var after=(a==="none")?null:parseInt(a,10);
 var r=trow(s),seq=r.insSeq++;
 r.ins.push({seq:seq,after_i:after,kind:null,chose:""});
 renderInsAt(s,after);upd();
 CUR_S=s;CUR_SEQ=seq;CUR_AFTER=after;PAL_MODE="ins";
 document.getElementById("gpal_cons").style.display="block";}
function editIns(b){var s=b.getAttribute("data-s"),seq=parseInt(b.getAttribute("data-seq"),10);
 var r=trow(s),i,after=null;
 for(i=0;i<r.ins.length;i++){if(r.ins[i].seq===seq){after=r.ins[i].after_i;break;}}
 CUR_S=s;CUR_SEQ=seq;CUR_AFTER=after;PAL_MODE="ins";
 document.getElementById("gpal_cons").style.display="block";}
function removeIns(b){var s=b.getAttribute("data-s"),seq=parseInt(b.getAttribute("data-seq"),10);
 var r=trow(s),i,after=null;
 for(i=0;i<r.ins.length;i++){if(r.ins[i].seq===seq){after=r.ins[i].after_i;r.ins.splice(i,1);break;}}
 renderInsAt(s,after);upd();}
function renderInsAt(s,after){var el=document.querySelector('.insat[data-s="'+s+'"][data-after="'+insKey(after)+'"]');
 if(!el)return;var r=trow(s),items=(r.ins||[]).filter(function(x){return x.after_i===after;}),h="",i;
 for(i=0;i<items.length;i++){var it=items[i],shown=it.chose?(it.kind==="gap"?"↔":it.chose):"…";
  h+='<span class="inschip">'+(it.chose?("<b>"+shown+"</b>"):"<i>pending</i>")+
   ' <button class="tbtn edit" data-s="'+s+'" data-seq="'+it.seq+'" onclick="editIns(this)">edit</button>'+
   ' <button class="tbtn rm" data-s="'+s+'" data-seq="'+it.seq+'" onclick="removeIns(this)">x</button></span>';}
 el.innerHTML=h;}
function setnote(inp){trow(inp.getAttribute("data-s")).note=inp.value;upd();}
function markFault(b){var s=b.getAttribute("data-s"),t=b.getAttribute("data-ft"),r=trow(s),i;
 r.fault=(r.fault===t)?"":t;
 var btns=document.querySelectorAll('.fault[data-s="'+s+'"]');
 for(i=0;i<btns.length;i++){btns[i].className=(btns[i].getAttribute("data-ft")===r.fault)?"fault on":"fault";}
 upd();}
function absn(b){var s=b.getAttribute("data-s"),r=trow(s);
 r.abst=r.abst?0:1;b.className=r.abst?"abst on":"abst";upd();}
function rowComplete(s){var m=RM[s],r=trow(s),n=m.tiles.length,k=0,i;
 for(i=0;i<n;i++){if(r.tv[m.tiles[i].i]&&r.tv[m.tiles[i].i].verdict)k++;}
 var ins=r.ins||[],j;
 for(j=0;j<ins.length;j++){n++;if(ins[j].chose)k++;}
 return [k,n];}
function hasNotInCrop(s){var m=RM[s],r=trow(s),i;
 for(i=0;i<m.tiles.length;i++){var v=r.tv[m.tiles[i].i];if(v&&v.verdict==="not_in_crop")return true;}
 return false;}
function pointsText(s){var el=document.querySelector('.points[data-s="'+s+'"]');
 return el?el.getAttribute("data-cand"):"";}
function tileShown(s,i,kind){if(kind==="gap")return "space";
 var el=tileDiv(s,i);return el?el.getAttribute("data-cand"):"";}
function tileOut(s,td){var r=trow(s),v=r.tv[td.i]||{verdict:"",chose:""},shown=tileShown(s,td.i,td.kind);
 if(v.verdict==="deleted")return "";
 if(v.verdict==="not_in_crop")return td.kind==="gap"?"[ ]":("["+shown+"]");
 if(v.verdict==="confirmed")return td.kind==="gap"?" ":shown;
 if(v.verdict==="corrected"){if(td.kind==="gap")return v.chose==="space"?" ":"";return v.chose||"?";}
 return "?";}
function insOut(it){if(!it.chose)return "?";return it.kind==="gap"?" ":it.chose;}
function derivedFor(s){var m=RM[s],r=trow(s),out=[],j,k;
 var atNone=(r.ins||[]).filter(function(x){return x.after_i===null;}).sort(function(a,b){return a.seq-b.seq;});
 for(j=0;j<atNone.length;j++)out.push(insOut(atNone[j]));
 for(j=0;j<m.tiles.length;j++){var td=m.tiles[j];out.push(tileOut(s,td));
  var ats=(r.ins||[]).filter(function(x){return x.after_i===td.i;}).sort(function(a,b){return a.seq-b.seq;});
  for(k=0;k<ats.length;k++)out.push(insOut(ats[k]));}
 return out.join("");}
function lines(){
 /* EVERY span, every time -- empty rows included. A partial download dropped over a full one is how
    an approval record dies with every byte in it valid. */
 var K=Object.keys(RM).sort(),L=[],si;
 for(si=0;si<K.length;si++){var s=K[si],m=RM[s],r=trow(s),tiles=[],j;
  for(j=0;j<m.tiles.length;j++){var td=m.tiles[j],v=r.tv[td.i]||{verdict:"",chose:""};
   tiles.push({i:td.i,kind:td.kind,shown:tileShown(s,td.i,td.kind),verdict:v.verdict||"",
    chose:v.chose||"",paired_to:td.paired_to});}
  var kn=rowComplete(s);
  var ins=(r.ins||[]).map(function(x){return {seq:x.seq,after_i:x.after_i,kind:x.kind,chose:x.chose};});
  L.push(JSON.stringify({span_id:s,crop_sha16:m.crop16,candidate_sha16:m.cand16,tiles:tiles,
   insertions:ins,complete:kn[0]===kn[1],abstain:!!r.abst,fault:r.fault||"",
   fault_legacy:r.fault_legacy||"",note:r.note,
   points_shown_not_adjudicated:{text:pointsText(s),n_points:m.n_points,nikud_flag:m.nikud},
   paired_at:m.paired_at,letter_rung_would_have_fired:!!m.letter_fired,
   full_span_pixel_signature:!hasNotInCrop(s),
   derived_consonants:derivedFor(s),derived_from_verdicts:true,
   signed_from:"pixels, candidate shown as consonant tiles, per-tile verdicts",
   signed_in:"glyph signer, in the browser",set_sha16:SETID,sheet:SKEL}));}
 return L.join("\n")+"\n";}
function upd(){var K=Object.keys(RM).sort(),nc=0,ntouch=0,i;
 for(i=0;i<K.length;i++){var s=K[i],kn=rowComplete(s),r=trow(s);
  var rowEl=document.getElementById("row_"+s);
  if(rowEl){var lab=document.getElementById("kn_"+s);
   if(lab)lab.textContent=kn[0]+"/"+kn[1]+" tiles"+
    (hasNotInCrop(s)?" · NOT a full-span pixel signature (not_in_crop present)":"");
   rowEl.className="row"+(kn[0]===kn[1]?" complete":"");}
  var dtxt=document.getElementById("der_txt_"+s);if(dtxt)dtxt.textContent=derivedFor(s);
  if(kn[0]===kn[1])nc++;
  if(kn[0]>0||r.fault||r.abst||r.note||(r.ins&&r.ins.length))ntouch++;}
 document.getElementById("ncomplete").textContent=nc;
 document.getElementById("nleft").textContent=(N-ntouch);
 var a=document.getElementById("dl");
 a.href="data:text/plain;charset=utf-8,"+encodeURIComponent(lines());
 try{localStorage.setItem("gs_"+SETID,JSON.stringify(ST));}catch(e){}}
function applyState(s){var r=ST[s],m=RM[s];if(!r||!m)return;var j;
 for(j=0;j<m.tiles.length;j++){var td=m.tiles[j],v=(r.tv||{})[td.i];
  var el=tileDiv(s,td.i);if(el&&v&&v.verdict)el.setAttribute("data-v",v.verdict);}
 var fbtns=document.querySelectorAll('.fault[data-s="'+s+'"]'),fi;
 for(fi=0;fi<fbtns.length;fi++){
  fbtns[fi].className=(fbtns[fi].getAttribute("data-ft")===r.fault)?"fault on":"fault";}
 var lg=document.querySelector('.legfault[data-s="'+s+'"]');
 if(lg)lg.style.display=r.fault_legacy?"block":"none";
 var ab=document.querySelector('.abst[data-s="'+s+'"]');if(ab&&r.abst)ab.className="abst on";
 var nt=document.querySelector('.nt[data-s="'+s+'"]');if(nt)nt.value=r.note||"";
 var seen={},ij;
 for(ij=0;ij<(r.ins||[]).length;ij++){var ak=insKey(r.ins[ij].after_i);
  if(!seen[ak]){seen[ak]=1;renderInsAt(s,r.ins[ij].after_i);}}}
function restore(){
 /* BEST EFFORT ONLY -- the download is the record, not this. */
 var raw=null;try{raw=localStorage.getItem("gs_"+SETID);}catch(e){raw=null;}
 if(!raw)return 0;var S=null;try{S=JSON.parse(raw);}catch(e){return 0;}
 var K=Object.keys(S),i,k=0;
 for(i=0;i<K.length;i++){var s=K[i];if(!RM[s])continue;ST[s]=S[s];k++;applyState(s);}
 return k;}
function renderImportCheck(rc){var el=document.getElementById("impcheck");if(!el)return;
 if(!EXP){el.textContent="no import expectation available (pass-1 file not found at generation time)";
  return;}
 var keys=["rows","tiles","confirmed","corrected","disputed","notes","abstains","legacy_faults",
  "insertions"],h="",i;
 for(i=0;i<keys.length;i++){var k=keys[i],r=rc[k]||0,e=EXP[k];
  h+=k+": restored "+r+" vs expected "+e+" -- "+(r===e?"PASS":"MISMATCH")+"<br>";}
 el.innerHTML=h;}
function doImport(inp){
 var f=inp.files&&inp.files[0];if(!f)return;
 var rd=new FileReader();
 rd.onload=function(){
  var txt=rd.result||"",ln=txt.split("\n"),i,bad=[],k=0;
  var rc={rows:0,tiles:0,confirmed:0,corrected:0,disputed:0,notes:0,abstains:0,legacy_faults:0,
   insertions:0};
  for(i=0;i<ln.length;i++){var s=ln[i].replace(/^\s+|\s+$/g,"");if(!s)continue;
   var d=null;try{d=JSON.parse(s);}catch(e){continue;}
   if(!d.span_id||!RM[d.span_id])continue;
   if(d.crop_sha16!==RM[d.span_id].crop16){bad.push(d.span_id);continue;}
   var rr=trow(d.span_id);rr.tv={};var tj,dtiles=d.tiles||[];
   rc.rows++;rc.tiles+=dtiles.length;
   for(tj=0;tj<dtiles.length;tj++){var tt=dtiles[tj];
    if(tt.verdict){rr.tv[tt.i]={verdict:tt.verdict,chose:tt.chose||""};
     if(tt.verdict==="confirmed")rc.confirmed++;
     else if(tt.verdict==="corrected")rc.corrected++;
     else if(tt.verdict==="disputed")rc.disputed++;}}
   rr.note=d.note||"";if(rr.note)rc.notes++;
   rr.abst=d.abstain?1:0;if(d.abstain)rc.abstains++;
   rr.fault=(TYPED_FAULTS.indexOf(d.fault)>=0)?d.fault:"";
   rr.fault_legacy=d.fault_legacy?d.fault_legacy:((d.fault===LEGACY_FAULT)?LEGACY_FAULT:"");
   if(rr.fault_legacy)rc.legacy_faults++;
   rr.ins=(d.insertions||[]).map(function(x){return {seq:x.seq,after_i:x.after_i,kind:x.kind,
    chose:x.chose||""};});
   rr.insSeq=rr.ins.length?(Math.max.apply(null,rr.ins.map(function(x){return x.seq;}))+1):0;
   rc.insertions+=rr.ins.length;
   applyState(d.span_id);k++;}
  var w=document.getElementById("impwarn");
  w.textContent=bad.length?("NOT restored (crop_sha16 differs -- a re-cut span must not inherit a "+
   "verdict): "+bad.join(", ")):"";
  document.getElementById("impmsg").textContent="imported "+k+" row(s) from "+f.name;
  renderImportCheck(rc);
  upd();};
 rd.readAsText(f,"utf-8");}
window.addEventListener("load",function(){var k=restore();
 document.getElementById("rst").textContent=k?("restored "+k+" row(s) from this browser"):
  "nothing restored from this browser";upd();});
"""

# JS_PASS3 -- the pass-3 console, forked from JS_PASS2 (byte copy, then the Part C/D edits). A third
# fork because JS_V1 and JS_PASS2 are both SPENT approval records; edit THIS block, never those two.
JS_PASS3 = r"""
var RM=__RM__, SETID=__SETID__, N=__N__, SKEL=__SKEL__, EXP=__EXP__, TYPED_FAULTS=__TYPED_FAULTS__,
    LEGACY_FAULT=__LEGACY_FAULT__, STOREKEY=__STOREKEY__, AUTOIMPORT=__AUTOIMPORT__,
    EMBED=__P3_EMBED__, EMBED_NAME=__P3_EMBED_NAME__, UNSIGNABLE=__P3_UNSIGNABLE__,
    SIG_RULE=__P3_SIG_RULE__, SEEDS=__P3_SEEDS__, SIC_BASES=["prior_grounded","evidence_grounded"],
    UNSIGNABLE_RX=new RegExp(UNSIGNABLE,"i"),
    ST={}, CUR_S=null, CUR_I=null, PAL_MODE="tile", CUR_SEQ=null, CUR_AFTER=null;
function trow(s){if(!ST[s])ST[s]={tv:{},note:"",fault:"",fault_legacy:"",abst:0,ins:[],insSeq:0,sic:{}};
 if(!ST[s].ins)ST[s].ins=[];if(!ST[s].sic)ST[s].sic={};if(ST[s].insSeq===undefined)ST[s].insSeq=0;
 if(ST[s].fault_legacy===undefined)ST[s].fault_legacy="";
 return ST[s];}
function tileDiv(s,i){return document.getElementById("t_"+s+"_"+i);}
function setVerdict(s,i,verdict,chose){
 var r=trow(s);r.tv[i]={verdict:verdict,chose:chose||""};
 var td=tileDiv(s,i);if(td)td.setAttribute("data-v",verdict);
 closePalette();renderSic(s,i);upd();}
function tOk(b){setVerdict(b.getAttribute("data-s"),b.getAttribute("data-i"),"confirmed","");}
function tBad(b){var s=b.getAttribute("data-s"),i=b.getAttribute("data-i"),k=b.getAttribute("data-k");
 CUR_S=s;CUR_I=i;PAL_MODE="tile";
 var pal=document.getElementById(k==="gap"?"gpal_gap":"gpal_cons");
 pal.style.display="block";}
function tDel(b){setVerdict(b.getAttribute("data-s"),b.getAttribute("data-i"),"deleted","");}
function tNic(b){setVerdict(b.getAttribute("data-s"),b.getAttribute("data-i"),"not_in_crop","");}
/* ---- pass 3 (Part D): the sic verdict. The PRINTED letter stays in the signature; the expectation lives
   beside it (expected / reason / basis), never in it. A sic tile counts as answered only when all three
   are present and valid. */
function sicDraft(s,i){var r=trow(s);if(!r.sic[i])r.sic[i]={expected:"",reason:"",basis:""};return r.sic[i];}
function sicShown(s,i){return tileShown(s,i,"consonant");}
function sicValid(s,i){var d=trow(s).sic[i];if(!d)return false;
 var e=d.expected||"",rs=(d.reason||"").replace(/\s+/g,"");
 return Array.from(e).length===1&&e!==sicShown(s,i)&&rs.length>0&&SIC_BASES.indexOf(d.basis)>=0;}
function escA(x){return String(x).replace(/&/g,"&amp;").replace(/"/g,"&quot;").replace(/</g,"&lt;");}
function sicMsg(s,i){var m=document.getElementById("sm_"+s+"_"+i);if(!m)return;
 m.textContent=sicValid(s,i)?"sic recorded: complete":
  "sic needs: one expected letter different from the printed one, a reason, and a basis";}
function renderSic(s,i){var el=document.querySelector('.sicbox[data-s="'+s+'"][data-i="'+i+'"]');
 if(!el)return;var r=trow(s),v=r.tv[i];
 if(!v||v.verdict!=="sic"){el.innerHTML="";return;}
 var d=sicDraft(s,i),a=' data-s="'+s+'" data-i="'+i+'"',j,
  h='<div class="sicform">printed <b>'+escA(sicShown(s,i))+'</b> stays in the signature; the expectation '+
  'lives beside it, never in it.<br>expected <input class="sicin" size="2" dir="rtl" data-f="expected"'+a+
  ' value="'+escA(d.expected)+'" oninput="sicSet(this)"><br>reason <input class="sicin" size="30" '+
  'data-f="reason"'+a+' value="'+escA(d.reason)+'" oninput="sicSet(this)"><br>basis <select data-f="basis"'+
  a+' onchange="sicSet(this)"><option value="">-- choose --</option>';
 for(j=0;j<SIC_BASES.length;j++)h+='<option value="'+SIC_BASES[j]+'"'+(d.basis===SIC_BASES[j]?' selected':'')+
  '>'+SIC_BASES[j]+'</option>';
 h+='</select><div class="sicmsg" id="sm_'+s+'_'+i+'"></div></div>';
 el.innerHTML=h;sicMsg(s,i);}
function sicSet(inp){var s=inp.getAttribute("data-s"),i=inp.getAttribute("data-i"),f=inp.getAttribute("data-f");
 sicDraft(s,i)[f]=inp.value;sicMsg(s,i);upd();}
function tSic(b){var s=b.getAttribute("data-s"),i=b.getAttribute("data-i");
 sicDraft(s,i);setVerdict(s,i,"sic","");}
function applySeeds(){var K=Object.keys(SEEDS),k;
 for(k=0;k<K.length;k++){var s=K[k],sd=SEEDS[s];if(!RM[s])continue;
  var r=trow(s);if(!r.sic[sd.tile_i])r.sic[sd.tile_i]={expected:sd.expected,reason:sd.reason,basis:""};
  renderSic(s,sd.tile_i);}}
/* ---- pass 3 (Part C): insertions carry a verdict, are shown as chips, and are counted by rowComplete. */
var VLAB={confirmed:"confirmed",not_in_crop:"not in crop",deleted:"deleted"};
function insVerdict(b){var s=b.getAttribute("data-s"),seq=parseInt(b.getAttribute("data-seq"),10),
 vv=b.getAttribute("data-vv"),r=trow(s),i,after=null;
 for(i=0;i<r.ins.length;i++){if(r.ins[i].seq===seq){r.ins[i].verdict=vv;after=r.ins[i].after_i;break;}}
 renderInsAt(s,after);upd();}
function proseConflict(s){var r=trow(s);return UNSIGNABLE_RX.test(r.note||"")&&!hasNotInCrop(s);}
function conflictText(s){var m=UNSIGNABLE_RX.exec(trow(s).note||"");
 return 'Conflict: your note says part of the span is not in the crop ("'+(m?m[0]:"")+'"), but no tile and no '+
  'insertion is marked not-in-crop. A row cannot be called complete while the two disagree. Mark the '+
  'out-of-crop tile or insertion "not in crop", or reword the note.';}
function rowDone(s){var kn=rowComplete(s);return kn[0]===kn[1]&&!proseConflict(s);}
function closePalette(){var a=document.getElementById("gpal_cons"),b=document.getElementById("gpal_gap");
 if(a)a.style.display="none";if(b)b.style.display="none";
 CUR_S=null;CUR_I=null;PAL_MODE="tile";CUR_SEQ=null;CUR_AFTER=null;}
function chooseLetterGlobal(b){
 if(PAL_MODE==="ins"){insSetChoice(b.getAttribute("data-letter"),"consonant");return;}
 if(CUR_S===null)return;setVerdict(CUR_S,CUR_I,"corrected",b.getAttribute("data-letter"));}
function cantTellGlobal(){if(PAL_MODE==="ins")return;if(CUR_S===null)return;setVerdict(CUR_S,CUR_I,"disputed","");}
function chooseGapGlobal(b){if(CUR_S===null)return;setVerdict(CUR_S,CUR_I,"corrected",b.getAttribute("data-choice"));}
function insSpaceGlobal(){if(PAL_MODE==="ins")insSetChoice("space","gap");}
function insKey(a){return a===null?"none":String(a);}
function insSetChoice(chose,kind){if(CUR_S===null||CUR_SEQ===null)return;
 var r=trow(CUR_S),i;for(i=0;i<r.ins.length;i++){if(r.ins[i].seq===CUR_SEQ){
  r.ins[i].kind=kind;r.ins[i].chose=chose;break;}}
 var after=CUR_AFTER,s0=CUR_S;closePalette();renderInsAt(s0,after);upd();}
function openIns(b){var s=b.getAttribute("data-s"),a=b.getAttribute("data-after");
 var after=(a==="none")?null:parseInt(a,10);
 var r=trow(s),seq=r.insSeq++;
 r.ins.push({seq:seq,after_i:after,kind:null,chose:"",verdict:"",expected:"",reason:"",basis:""});
 renderInsAt(s,after);upd();
 CUR_S=s;CUR_SEQ=seq;CUR_AFTER=after;PAL_MODE="ins";
 document.getElementById("gpal_cons").style.display="block";}
function editIns(b){var s=b.getAttribute("data-s"),seq=parseInt(b.getAttribute("data-seq"),10);
 var r=trow(s),i,after=null;
 for(i=0;i<r.ins.length;i++){if(r.ins[i].seq===seq){after=r.ins[i].after_i;break;}}
 CUR_S=s;CUR_SEQ=seq;CUR_AFTER=after;PAL_MODE="ins";
 document.getElementById("gpal_cons").style.display="block";}
function removeIns(b){var s=b.getAttribute("data-s"),seq=parseInt(b.getAttribute("data-seq"),10);
 var r=trow(s),i,after=null;
 for(i=0;i<r.ins.length;i++){if(r.ins[i].seq===seq){after=r.ins[i].after_i;r.ins.splice(i,1);break;}}
 renderInsAt(s,after);upd();}
function renderInsAt(s,after){var el=document.querySelector('.insat[data-s="'+s+'"][data-after="'+insKey(after)+'"]');
 if(!el)return;var r=trow(s),items=(r.ins||[]).filter(function(x){return x.after_i===after;}),h="",i;
 items.sort(function(x,y){return x.seq-y.seq;});
 for(i=0;i<items.length;i++){var it=items[i],v=it.verdict||"",
  shown=it.chose?(it.kind==="gap"?"\u2194":it.chose):"\u2026",
  st=!it.chose?"no letter chosen yet":(v?VLAB[v]:"unanswered"),
  a=' data-s="'+s+'" data-seq="'+it.seq+'"';
  h+='<span class="inschip" data-v="'+v+'" data-seq="'+it.seq+'"><span class="insword">added</span> <b>'+shown+
   '</b> <span class="insstate">'+st+'</span> '+
   '<button class="tbtn ok"'+a+' data-vv="confirmed" onclick="insVerdict(this)">&#10003;</button>'+
   '<button class="tbtn nic"'+a+' data-vv="not_in_crop" onclick="insVerdict(this)">not in crop</button>'+
   '<button class="tbtn del"'+a+' data-vv="deleted" onclick="insVerdict(this)">del</button> '+
   '<button class="tbtn edit"'+a+' onclick="editIns(this)">edit</button> '+
   '<button class="tbtn rm"'+a+' onclick="removeIns(this)">x</button></span>';}
 el.innerHTML=h;}
function setnote(inp){trow(inp.getAttribute("data-s")).note=inp.value;upd();}
function markFault(b){var s=b.getAttribute("data-s"),t=b.getAttribute("data-ft"),r=trow(s),i;
 r.fault=(r.fault===t)?"":t;
 var btns=document.querySelectorAll('.fault[data-s="'+s+'"]');
 for(i=0;i<btns.length;i++){btns[i].className=(btns[i].getAttribute("data-ft")===r.fault)?"fault on":"fault";}
 upd();}
function absn(b){var s=b.getAttribute("data-s"),r=trow(s);
 r.abst=r.abst?0:1;b.className=r.abst?"abst on":"abst";upd();}
function rowComplete(s){var m=RM[s],r=trow(s),n=m.tiles.length,k=0,i;
 for(i=0;i<n;i++){var tv=r.tv[m.tiles[i].i];
  if(tv&&tv.verdict&&(tv.verdict!=="sic"||sicValid(s,m.tiles[i].i)))k++;}
 var ins=r.ins||[],j;
 for(j=0;j<ins.length;j++){n++;if(ins[j].chose&&ins[j].verdict)k++;}
 return [k,n];}
function hasNotInCrop(s){var m=RM[s],r=trow(s),i;
 for(i=0;i<m.tiles.length;i++){var v=r.tv[m.tiles[i].i];if(v&&v.verdict==="not_in_crop")return true;}
 var ins=r.ins||[];
 for(i=0;i<ins.length;i++){if(ins[i].verdict==="not_in_crop")return true;}
 return false;}
function pointsText(s){var el=document.querySelector('.points[data-s="'+s+'"]');
 return el?el.getAttribute("data-cand"):"";}
function tileShown(s,i,kind){if(kind==="gap")return "space";
 var el=tileDiv(s,i);return el?el.getAttribute("data-cand"):"";}
function tileOut(s,td){var r=trow(s),v=r.tv[td.i]||{verdict:"",chose:""},shown=tileShown(s,td.i,td.kind);
 if(v.verdict==="deleted")return "";
 if(v.verdict==="not_in_crop")return td.kind==="gap"?"[ ]":("["+shown+"]");
 if(v.verdict==="confirmed")return td.kind==="gap"?" ":shown;
 if(v.verdict==="sic")return shown;
 if(v.verdict==="corrected"){if(td.kind==="gap")return v.chose==="space"?" ":"";return v.chose||"?";}
 return "?";}
function insOut(it){var v=it.verdict||"";if(v==="deleted")return "";if(!it.chose)return "?";
 if(v==="not_in_crop")return it.kind==="gap"?"[ ]":("["+it.chose+"]");
 return it.kind==="gap"?" ":it.chose;}
function derivedFor(s){var m=RM[s],r=trow(s),out=[],j,k;
 var atNone=(r.ins||[]).filter(function(x){return x.after_i===null;}).sort(function(a,b){return a.seq-b.seq;});
 for(j=0;j<atNone.length;j++)out.push(insOut(atNone[j]));
 for(j=0;j<m.tiles.length;j++){var td=m.tiles[j];out.push(tileOut(s,td));
  var ats=(r.ins||[]).filter(function(x){return x.after_i===td.i;}).sort(function(a,b){return a.seq-b.seq;});
  for(k=0;k<ats.length;k++)out.push(insOut(ats[k]));}
 return out.join("");}
function lines(){
 /* EVERY span, every time -- empty rows included. A partial download dropped over a full one is how
    an approval record dies with every byte in it valid. */
 var K=Object.keys(RM).sort(),L=[],si;
 for(si=0;si<K.length;si++){var s=K[si],m=RM[s],r=trow(s),tiles=[],j;
  for(j=0;j<m.tiles.length;j++){var td=m.tiles[j],v=r.tv[td.i]||{verdict:"",chose:""};
   var sd=(v.verdict==="sic")?(r.sic[td.i]||{}):{};
   tiles.push({i:td.i,kind:td.kind,shown:tileShown(s,td.i,td.kind),verdict:v.verdict||"",
    chose:v.chose||"",expected:sd.expected||"",reason:sd.reason||"",basis:sd.basis||"",
    paired_to:td.paired_to});}
  var kn=rowComplete(s);
  var ins=(r.ins||[]).map(function(x){return {seq:x.seq,after_i:x.after_i,kind:x.kind,chose:x.chose,verdict:x.verdict||"",
   expected:x.expected||"",reason:x.reason||"",basis:x.basis||""};});
  L.push(JSON.stringify({span_id:s,crop_sha16:m.crop16,candidate_sha16:m.cand16,tiles:tiles,
   insertions:ins,complete:rowDone(s),abstain:!!r.abst,fault:r.fault||"",
   fault_legacy:r.fault_legacy||"",note:r.note,
   points_shown_not_adjudicated:{text:pointsText(s),n_points:m.n_points,nikud_flag:m.nikud},
   paired_at:m.paired_at,letter_rung_would_have_fired:!!m.letter_fired,
   full_span_pixel_signature:!hasNotInCrop(s),signature_rule:SIG_RULE,
   derived_consonants:derivedFor(s),derived_from_verdicts:true,
   signed_from:"pixels, candidate shown as consonant tiles, per-tile verdicts",
   signed_in:"glyph signer, in the browser",set_sha16:SETID,sheet:SKEL}));}
 return L.join("\n")+"\n";}
function upd(){var K=Object.keys(RM).sort(),nc=0,ntouch=0,i;
 for(i=0;i<K.length;i++){var s=K[i],kn=rowComplete(s),r=trow(s),done=rowDone(s),pc=proseConflict(s);
  var rowEl=document.getElementById("row_"+s);
  if(rowEl){var lab=document.getElementById("kn_"+s);
   if(lab)lab.textContent=kn[0]+"/"+kn[1]+" items (tiles + insertions)"+
    (hasNotInCrop(s)?" \u00b7 NOT a full-span pixel signature (not_in_crop present)":"");
   var cf=document.getElementById("cf_"+s);
   if(cf){cf.style.display=pc?"block":"none";cf.textContent=pc?conflictText(s):"";}
   rowEl.className="row"+(done?" complete":"");}
  var dtxt=document.getElementById("der_txt_"+s);if(dtxt)dtxt.textContent=derivedFor(s);
  if(done)nc++;
  if(kn[0]>0||r.fault||r.abst||r.note||(r.ins&&r.ins.length))ntouch++;}
 document.getElementById("ncomplete").textContent=nc;
 document.getElementById("nleft").textContent=(N-ntouch);
 var a=document.getElementById("dl");
 a.href="data:text/plain;charset=utf-8,"+encodeURIComponent(lines());
 try{localStorage.setItem("gs_"+STOREKEY,JSON.stringify(ST));}catch(e){}}
function applyState(s){var r=ST[s],m=RM[s];if(!r||!m)return;var j;
 for(j=0;j<m.tiles.length;j++){var td=m.tiles[j],v=(r.tv||{})[td.i];
  var el=tileDiv(s,td.i);if(el&&v&&v.verdict)el.setAttribute("data-v",v.verdict);renderSic(s,td.i);}
 var fbtns=document.querySelectorAll('.fault[data-s="'+s+'"]'),fi;
 for(fi=0;fi<fbtns.length;fi++){
  fbtns[fi].className=(fbtns[fi].getAttribute("data-ft")===r.fault)?"fault on":"fault";}
 var lg=document.querySelector('.legfault[data-s="'+s+'"]');
 if(lg)lg.style.display=r.fault_legacy?"block":"none";
 var ab=document.querySelector('.abst[data-s="'+s+'"]');if(ab&&r.abst)ab.className="abst on";
 var nt=document.querySelector('.nt[data-s="'+s+'"]');if(nt)nt.value=r.note||"";
 var seen={},ij;
 for(ij=0;ij<(r.ins||[]).length;ij++){var ak=insKey(r.ins[ij].after_i);
  if(!seen[ak]){seen[ak]=1;renderInsAt(s,r.ins[ij].after_i);}}}
function restore(){
 /* BEST EFFORT ONLY -- the download is the record, not this. */
 var raw=null;try{raw=localStorage.getItem("gs_"+STOREKEY);}catch(e){raw=null;}
 if(!raw)return 0;var S=null;try{S=JSON.parse(raw);}catch(e){return 0;}
 var K=Object.keys(S),i,k=0;
 for(i=0;i<K.length;i++){var s=K[i];if(!RM[s])continue;ST[s]=S[s];k++;applyState(s);}
 return k;}
function renderImportCheck(rc){var el=document.getElementById("impcheck");if(!el)return;
 if(!EXP){el.textContent="no import expectation available (pass-1 file not found at generation time)";
  return;}
 var keys=["rows","tiles","confirmed","corrected","disputed","notes","abstains","legacy_faults",
  "insertions"],h="",i;
 for(i=0;i<keys.length;i++){var k=keys[i],r=rc[k]||0,e=EXP[k];
  h+=k+": restored "+r+" vs expected "+e+" -- "+(r===e?"PASS":"MISMATCH")+"<br>";}
 el.innerHTML=h;}
function importText(txt,fname){
 /* The whole of the former doImport body, now shared by the file-input path AND pass 2's auto-import
    (Change 3) -- ONE importer, same span_id+crop_sha16 matching, same refusal list, same
    renderImportCheck, whichever path called it. */
 var ln=(txt||"").split("\n"),i,bad=[],k=0;
 var rc={rows:0,tiles:0,confirmed:0,corrected:0,disputed:0,notes:0,abstains:0,legacy_faults:0,
  insertions:0};
 for(i=0;i<ln.length;i++){var s=ln[i].replace(/^\s+|\s+$/g,"");if(!s)continue;
  var d=null;try{d=JSON.parse(s);}catch(e){continue;}
  if(!d.span_id||!RM[d.span_id])continue;
  if(d.crop_sha16!==RM[d.span_id].crop16){bad.push(d.span_id);continue;}
  var rr=trow(d.span_id);rr.tv={};rr.sic={};var tj,dtiles=d.tiles||[];
  rc.rows++;rc.tiles+=dtiles.length;
  for(tj=0;tj<dtiles.length;tj++){var tt=dtiles[tj];
   if(tt.verdict){rr.tv[tt.i]={verdict:tt.verdict,chose:tt.chose||""};
    if(tt.verdict==="sic")rr.sic[tt.i]={expected:tt.expected||"",reason:tt.reason||"",basis:tt.basis||""};
    if(tt.verdict==="confirmed")rc.confirmed++;
    else if(tt.verdict==="corrected")rc.corrected++;
    else if(tt.verdict==="disputed")rc.disputed++;}}
  rr.note=d.note||"";if(rr.note)rc.notes++;
  rr.abst=d.abstain?1:0;if(d.abstain)rc.abstains++;
  rr.fault=(TYPED_FAULTS.indexOf(d.fault)>=0)?d.fault:"";
  rr.fault_legacy=d.fault_legacy?d.fault_legacy:((d.fault===LEGACY_FAULT)?LEGACY_FAULT:"");
  if(rr.fault_legacy)rc.legacy_faults++;
  rr.ins=(d.insertions||[]).map(function(x){return {seq:x.seq,after_i:x.after_i,kind:x.kind,
   chose:x.chose||"",verdict:x.verdict||"",expected:x.expected||"",reason:x.reason||"",basis:x.basis||""};});
  rr.insSeq=rr.ins.length?(Math.max.apply(null,rr.ins.map(function(x){return x.seq;}))+1):0;
  rc.insertions+=rr.ins.length;
  applyState(d.span_id);k++;}
 var w=document.getElementById("impwarn");
 w.textContent=bad.length?("NOT restored (crop_sha16 differs -- a re-cut span must not inherit a "+
  "verdict): "+bad.join(", ")):"";
 document.getElementById("impmsg").textContent="imported "+k+" row(s) from "+fname;
 renderImportCheck(rc);
 applySeeds();upd();}
function doImport(inp){
 var f=inp.files&&inp.files[0];if(!f)return;
 var rd=new FileReader();
 rd.onload=function(){importText(rd.result||"",f.name);};
 rd.readAsText(f,"utf-8");}
window.addEventListener("load",function(){var k=restore();
 document.getElementById("rst").textContent=k?("restored "+k+" row(s) from this browser"):
  "nothing restored from this browser";
 if(AUTOIMPORT&&k===0){importText(EMBED,EMBED_NAME);}
 applySeeds();upd();});
"""
# end JS_PASS3 -- everything above this line from its label is the pass-3 console.

# ---- blob identity, pinned in EVERY mode. JS_V1 renders the console that produced pass 1 and JS_PASS2
# the one Chris signed pass 2 on: each is a console that is already signed and spent, and an edit to
# either rewrites the record of what was approved. Length is len(str) of the blob without its
# surrounding newlines; the hash is sha256 of its UTF-8 bytes.
def _blob_id(blob):
    t = blob.strip("\n")
    return len(t), hashlib.sha256(t.encode("utf-8")).hexdigest()[:16]


check(_blob_id(JS_V1) == (11968, "7fa5fd3fd0d4f9f7"),
      "JS_V1 measures %r, not (11968, 7fa5fd3fd0d4f9f7): it renders a console that is already signed and "
      "spent (pass 1); it must never be edited -- fork a new blob instead" % (_blob_id(JS_V1),))
check(_blob_id(JS_PASS2) == (12422, "3ccd5adfbb39c5c4"),
      "JS_PASS2 measures %r, not (12422, 3ccd5adfbb39c5c4): it renders a console that is already signed "
      "and spent (pass 2); it must never be edited -- fork a new blob instead" % (_blob_id(JS_PASS2),))

JS = JS_PASS3 if PASS3 else (JS_PASS2 if PASS2 else JS_V1)
check(JS is (JS_PASS3 if PASS3 else (JS_PASS2 if PASS2 else JS_V1)) and (PASS3 or JS is not JS_PASS3),
      "the console chosen for this mode is not the one this mode names")

_TITLE_SUFFIX = " (pass 3)" if PASS3 else (" (pass 2)" if PASS2 else "")
H = ['<!doctype html><meta charset="utf-8"><title>glyph signer %s%s - %d spans, per-glyph verdicts</title>'
     % (SET, _TITLE_SUFFIX, RUN_N), "<style>%s</style>" % CSS]
H.append("<h1>Glyph signer <code>%s</code>%s &mdash; %d spans, per-glyph verdicts</h1>"
         % (SET, " &mdash; PASS 3" if PASS3 else (" &mdash; PASS 2" if PASS2 else ""), RUN_N))
H.append('<div class="sub">FILE pages throughout; printed = file &minus; %d. A2 span box, PAD=%d native '
         'px, over a clean tree. The candidate is SHOWN here (it was withheld on the signing sheet); '
         'every property of it -- each consonant, each word gap, the pointing -- gets its own verdict. '
         'Nothing is accepted by default.</div>' % (PRINTED_OFFSET, HAD.PAD))

# Change 1's last bullet: state near the top which dispositions were selected and how many of each --
# derived from the ingest's own recomputed tally (the same one the module-level assertion checked), printed.
if PASS2:
    _dispo_lines = "".join(
        '<li><code>%s</code> &mdash; <b>%d</b> row(s): %s</li>'
        % (html.escape(d), _ingest_dispo_counts.get(d, 0), html.escape(why))
        for d, why in sorted(PASS2_DISPOSITIONS.items()))
    H.append('<div class="note loud"><b>Pass 2 selection.</b> Pass 1 signed all 74 and held %d for '
             'reasons about the CANDIDATE TEXT, not the box. This page sheets exactly those %d rows, '
             'derived from <code>%s</code>, a second time, with the full note crop beside each span '
             'crop:<ul>%s</ul></div>' % (RUN_N, RUN_N, html.escape(INGEST_NAME), _dispo_lines))

if PASS3:
    H.append('<div class="note loud"><b>Pass 3 selection.</b> Pass 2 held %d row(s) as <code>%s</code>: '
             'your PROSE says part of the span is not in the crop, but every tile was confirmed/corrected/'
             'deleted and none was marked not-in-crop, so the two channels disagreed. Derived from '
             '<code>%s</code>. Your pass-2 verdicts are already open on this page; correct them. New here: '
             'insertions take a verdict and show as chips; a row whose note says &ldquo;not in the '
             'crop&rdquo; cannot be completed unless a tile or insertion is marked not-in-crop; and a '
             '<b>sic</b> verdict records a printed form that is certainly printed and certainly wrong '
             '(the printed letter stays in the signature; expected / reason / basis sit beside it).</div>'
             % (RUN_N, html.escape(PASS3_DISPOSITION), html.escape(HELD2_NAME)))

H.append('<div class="note loud"><b>No second read exists for this set.</b> Of the four stored-reads '
         'files this page loads, %d read(s) across this set&rsquo;s %d spans were found (liveness: the '
         'loader actually opened %d file(s) and actually saw them); %d of those %d were taken at this '
         'set&rsquo;s own aperture (<code>%s</code>) and %d were rejected for having been read at a '
         '<i>different</i> aperture (mostly <code>A1_notebox</code>, the full note strip &mdash; '
         'different pixels, not evidence about this crop). Usable reads: <b>%d</b>. Spans with two or '
         'more usable reads: <b>%d of %d</b>. So every &#10003; here confirms a SINGLE extraction; '
         'agreement between arms is not available as evidence on this set.</div>'
         % (READS_SEEN, RUN_N, _ALT_FILES_SEEN, READS_USABLE, READS_SEEN, SET_APERTURE, READS_REJECTED,
            READS_USABLE, SPANS_WITH_2PLUS_USABLE, RUN_N))

H.append('<div class="note">The candidate is CONSONANTAL here: points (nikud/cantillation) are shown '
         'verbatim on each row&rsquo;s points line but are never tiled and never adjudicated -- a '
         'pointed read is not a wrong read. Pairing a tile to the crop&rsquo;s own glyph is done by '
         'COUNTING ink columns (never by recognising a letter): the LETTER rung fires only when the '
         'count of ink columns equals the count of consonants, which is a count AGREEMENT, not a proof '
         'that the pairing lines up letter-for-letter -- treat it as such. Failing that, the WORD rung '
         'groups a word&rsquo;s tiles under its own resolved word-run image. Failing that, no pairing is '
         'offered and the whole crop is shown once, magnified, above the tiles.</div>')

H.append('<table class="sum">'
         '<tr><td>spans</td><td><b>%d</b></td></tr>'
         '<tr><td>tiles</td><td><b>%d</b> total &mdash; <b>%d</b> consonant, <b>%d</b> gap</td></tr>'
         '<tr><td>pairing rungs</td><td>word <b>%d</b> &middot; none <b>%d</b> &mdash; letter rung '
         '<b>RETIRED</b> (would have fired on <b>%d</b> row(s))</td></tr>'
         '<tr><td>word-count disagreement</td><td><b>%d</b> row(s): %s</td></tr>'
         '<tr><td>alternatives</td><td>reads seen <b>%d</b>, usable (this aperture) <b>%d</b>, spans '
         'with &ge;2 usable <b>%d</b> of %d, tiles offering an alternative <b>%d</b></td></tr>'
         '</table>' % (RUN_N, TOTAL_TILES, TOTAL_CONSONANT_TILES, TOTAL_GAP_TILES,
                       RUNG_COUNTS["word"], RUNG_COUNTS["none"], LETTER_WOULD_HAVE_FIRED,
                       len(WORD_COUNT_DISAGREES), html.escape(", ".join(WORD_COUNT_DISAGREES)) or "none",
                       READS_SEEN, READS_USABLE, SPANS_WITH_2PLUS_USABLE, RUN_N,
                       TILES_OFFERING_ALTERNATIVE))

# Change 6: the import expectation, derived read-only from pass 1's own signed file, never hard-coded.
if IMPORT_EXPECTATION is not None:
    H.append('<div class="note">import expectation, derived read-only from <code>%s</code>: %s. After '
              'an import the page prints what was restored beside these and says PASS or MISMATCH per '
              'line.</div><div id="impcheck" class="sub"></div>'
             % (html.escape(EXP_SRC_NAME), html.escape(EXP_LINE)))
else:
    H.append('<div class="note loud"><code>%s</code> was not found at generation time -- the import '
              'expectation is SKIPPED here rather than invented.</div><div id="impcheck" '
              'class="sub"></div>' % html.escape(EXP_SRC_NAME))

# The two GLOBAL palettes -- one copy each in the whole document, shown/hidden by the JS and retargeted
# per click via CUR_S/CUR_I, rather than one copy per tile. Keeps the fixed alphabet's Hebrew glyphs out
# of the per-candidate accounting below (guard 3) and off the wire 600+ times over.
_letter_buttons = "".join(
    '<button class="pbtn" data-letter="%s" onclick="chooseLetterGlobal(this)">%s</button>' % (c, c)
    for c in CONSONANTS)
H.append('<div id="gpal_cons" class="palette" style="display:none">%s'
         '<button class="pbtn canttell" onclick="cantTellGlobal()">can&rsquo;t tell</button>'
         '<button class="pbtn gapchoice" onclick="insSpaceGlobal()">space (gap insertion)</button>'
         '</div>'
         % _letter_buttons)
H.append('<div id="gpal_gap" class="palette" style="display:none">'
         '<button class="pbtn gapchoice" data-choice="space" onclick="chooseGapGlobal(this)">space here</button>'
         '<button class="pbtn gapchoice" data-choice="no-space" onclick="chooseGapGlobal(this)">no space here</button>'
         '</div>')

def _insert_slot_html(sid, after_i):
    """Change 3: a thin '+' between every pair of adjacent tiles, before the first and after the last.
    `after_i=None` means before tile 0. The letter/space actually chosen lives client-side in `.insat`,
    rendered by the JS -- the tile array itself is never mutated."""
    esid = html.escape(sid)
    after_attr = "none" if after_i is None else str(after_i)
    return ('<span class="insslot"><button class="tbtn ins" data-s="%s" data-after="%s" '
            'onclick="openIns(this)">+</button>'
            '<span class="insat" data-s="%s" data-after="%s"></span></span>'
            % (esid, after_attr, esid, after_attr))


def _ent(s):
    """html-escape, then write every non-ASCII char as a numeric entity: pass 3 shows the signer's OWN pass-2
    note and the settled sic context, which contain Hebrew, and guard 3 forbids raw Hebrew outside data-cand.
    The browser renders the entity identically; the guard still sees no readable candidate in the source."""
    return "".join(c if ord(c) < 128 else "&#x%x;" % ord(c) for c in html.escape(s))


def _sic_wrap(tile_html, sid, i):
    """Pass 3 (Part D): a consonant tile gains a fifth control, `sic`, and a (JS-filled) form box."""
    esid = html.escape(sid)
    head, sep, tail = tile_html.rpartition("</div>")
    assert sep and not tail, "a consonant tile's HTML does not end in its own </div>"
    return head + ('<button class="tbtn sic" data-s="%s" data-i="%d" onclick="tSic(this)">sic</button>'
                   '<span class="sicbox" data-s="%s" data-i="%d"></span>' % (esid, i, esid, i)) + sep + tail


RM = {}   # embedded per-span metadata for the JS: NEVER candidate-derived Hebrew text (see guard 3)

for r in ROWS:
    sid, tr, cr = r["sid"], r["tr"], r["cr"]
    crop_path = cr["crop"]["path"]
    im = Image.open(str(crop_path)).convert("L")

    H.append('<div class="row" id="row_%s"><div class="meta">' % html.escape(sid))
    H.append("<b>%s</b><br><span class=sub>file p%d &nbsp;&middot;&nbsp; printed p%d &nbsp;&middot;&nbsp; "
             "note %d &nbsp;&middot;&nbsp; <span class=kn id=kn_%s>0/%d tiles</span></span><br>"
             % (html.escape(sid), tr["page"], tr["page"] - PRINTED_OFFSET, tr["note_index"],
                html.escape(sid), len(r["tiles"])))
    H.append('<span class=sub>crop %d&times;%d &nbsp; rung <b>%s</b> &nbsp; letters %d &nbsp; words %d'
              '%s</span><br><code>%s</code>'
             % (cr["crop"]["size"][0], cr["crop"]["size"][1], r["paired_at"], tr["letters"],
                len(r["words"]),
                " &mdash; CANDIDATE CLAIMS %d WORD(S), DISAGREES" % tr["words"]
                if sid in WORD_COUNT_DISAGREES else "",
                cr["crop"]["sha16"]))

    nc = cr.get("note_context")
    H.append('<div class="links">')
    if nc:
        H.append('<a href="%s">the region this box sits in &mdash; %d&times;%d</a> &nbsp;&middot;&nbsp; '
                 % (_furl(nc["path"]), nc["size"][0], nc["size"][1]))
    else:
        H.append('<span class="why">no note crop derived: %s</span> &nbsp;&middot;&nbsp; '
                 % html.escape(cr.get("note_fault") or "unrecorded"))
    H.append('<a href="%s">native page PNG, file p%d</a></div>' % (_furl(cr["page_png"]), tr["page"]))

    # THE BYTE-IDENTITY REFERENCE. The sheet's embed detector works because it embeds the crop's OWN,
    # unmodified file bytes; every OTHER image on this page is a crop+resize derivative of them and
    # would never match. So every row carries exactly this one untouched copy too.
    H.append('<figure><img src="%s" width="%d" height="%d"><figcaption>native crop, unmagnified, for '
              'reference</figcaption></figure>'
             % (_uri_bytes(crop_path), cr["crop"]["size"][0], cr["crop"]["size"][1]))

    if PASS2:
        # Change 4: what pass 1 concluded about THIS row, in the ingest's own words -- never re-phrased.
        H.append('<div class="note loud">%s</div>' % html.escape(_pass1_label(sid)))

        # Change 3: pass 1's own verdicts are already open on this page (auto-imported, Change 3); this
        # is additionally the signer's own note and signed_from VERBATIM, read-only, so a row whose crop
        # was re-cut is obvious.
        p1row = PASS1_ROWS[sid]
        H.append('<div class="sub">your note, pass 1: <code>%s</code> &nbsp;&middot;&nbsp; signed_from, '
                 'pass 1: <code>%s</code></div>'
                 % (html.escape(p1row.get("note") or "(none)"), html.escape(p1row.get("signed_from") or "")))

    if PASS3:
        # What pass 2 concluded about THIS row, and the signer's own pass-2 note, VERBATIM. The pass-2
        # verdicts themselves are auto-imported on load through the one importer.
        _h2 = PASS3_HELD[sid]
        H.append('<div class="note loud">pass 2: <code>%s</code> &mdash; %s</div>'
                 % (_ent(_h2["disposition"]), _ent(_h2["why_held"])))
        H.append('<div class="sub">your note, pass 2: <code>%s</code></div>'
                 % _ent(PASS2_ROWS[sid].get("note") or "(none)"))
        if sid in SIC_SEEDS:
            _sd = SIC_SEEDS[sid]
            H.append('<div class="note">Settled earlier: printed %s, expected %s, reason &ldquo;%s&rdquo;. '
                     'Click <b>sic</b> on the %s tile to record it &mdash; expected and reason are pre-filled '
                     'and editable, the basis is yours to choose, and the verdict is not pre-set.</div>'
                     % (_ent(_sd["printed"]), _ent(_sd["expected"]), _ent(_sd["reason"]),
                        _ent(_sd["printed"])))
        H.append('<div class="conflict" id="cf_%s" style="display:none"></div>' % html.escape(sid))
    if PASS23:
        # Change 2: the whole footnote this span sits in, at NATIVE size, in a horizontally scrollable
        # container (rule 1) -- never CSS-scaled (guard asserts this over the stylesheet text). The span
        # box is drawn on it (rule 2) as a record for a human, never evidence; linked, never embedded
        # (rule 3) -- no note-crop pixel may ever reach a model.
        nci = NOTE_CROP_INFO[sid]
        _badge = "" if nci["box_inside_note"] else \
            ' <b class="badge-outside">box-outside-note</b>'
        H.append('<figure class="notecrop-wrap"><div style="overflow-x:auto">'
                 '<img class="notecrop" src="%s" width="%d" height="%d"></div>'
                 '<figcaption>whole footnote, native %d&times;%d, span box drawn in <code>%s</code>%s'
                 '</figcaption></figure>'
                 % (_furl(nci["path"]), nci["native_wh"][0], nci["native_wh"][1],
                    nci["native_wh"][0], nci["native_wh"][1], NOTECROP_BOX_HEX, _badge))

    tiles_meta = []
    if r["paired_at"] == "none":
        H.append('<figure><img src="%s"><figcaption>no pairing offered (ink-run count did not match '
                  'letters or words) &mdash; whole crop, &times;%d</figcaption></figure>'
                 % (_whole_crop_uri(im), MAG))
    # A row with NO pairing still renders every tile -- it has to be signable either way. All that
    # is absent is the magnified glyph beside each tile, which is what the figure above says.
    # Render strictly in tile order, emitting a word figure once at the first consonant of a word
    # (for the WORD rung; the LETTER rung has no shared per-word image).
    _emitted_word = set()
    for t in r["tiles"]:
        if t["kind"] == "consonant" and r["paired_at"] == "word" and t["word_i"] not in _emitted_word:
            _emitted_word.add(t["word_i"])
            run = r["word_assign"].get(t["word_i"])
            if run:
                H.append('<figure><img src="%s"><figcaption>word run %s, &times;%d</figcaption></figure>'
                         % (_crop_slice_uri(im, run[0], run[1], context=0, mag=MAG), run, MAG))
    H.append(_insert_slot_html(sid, None))
    for t in r["tiles"]:
        if t["kind"] == "consonant":
            run = (r["letter_assign"].get(t["i"]) if r["paired_at"] == "letter"
                   else r["word_assign"].get(t["word_i"]) if r["paired_at"] == "word" else None)
            img_html = ""
            if r["paired_at"] == "letter" and run:
                img_html = ('<img src="%s">'
                            % _crop_slice_uri(im, run[0], run[1], context=LETTER_CONTEXT_PX, mag=MAG))
            _tile_html = ('<div class="tile cons" id="t_%s_%d" data-s="%s" data-i="%d" data-cand="%s">%s'
                      '<button class="tbtn ok" data-s="%s" data-i="%d" onclick="tOk(this)">&#10003;</button>'
                      '<button class="tbtn no" data-s="%s" data-i="%d" data-k="cons" '
                      'onclick="tBad(this)">&#10007;</button>'
                      '<button class="tbtn del" data-s="%s" data-i="%d" onclick="tDel(this)">del</button>'
                      '<button class="tbtn nic" data-s="%s" data-i="%d" onclick="tNic(this)">not in '
                      'crop</button></div>'
                     % (html.escape(sid), t["i"], html.escape(sid), t["i"], html.escape(t["cand"]),
                        img_html, html.escape(sid), t["i"], html.escape(sid), t["i"],
                        html.escape(sid), t["i"], html.escape(sid), t["i"]))
            H.append(_sic_wrap(_tile_html, sid, t["i"]) if PASS3 else _tile_html)
            tiles_meta.append({"i": t["i"], "kind": "consonant", "paired_to": list(run) if run else None})
        else:
            H.append('<div class="tile gap" id="t_%s_%d" data-s="%s" data-i="%d">'
                      '<button class="tbtn ok" data-s="%s" data-i="%d" onclick="tOk(this)">&#10003;</button>'
                      '<button class="tbtn no" data-s="%s" data-i="%d" data-k="gap" '
                      'onclick="tBad(this)">&#10007;</button>'
                      '<button class="tbtn del" data-s="%s" data-i="%d" onclick="tDel(this)">del</button>'
                      '<button class="tbtn nic" data-s="%s" data-i="%d" onclick="tNic(this)">not in '
                      'crop</button></div>'
                     % (html.escape(sid), t["i"], html.escape(sid), t["i"],
                        html.escape(sid), t["i"], html.escape(sid), t["i"],
                        html.escape(sid), t["i"], html.escape(sid), t["i"]))
            tiles_meta.append({"i": t["i"], "kind": "gap", "paired_to": None})
        H.append(_insert_slot_html(sid, t["i"]))

    H.append('<div class="derived">derived from your verdicts &mdash; not a candidate, not signable: '
             '<code id="der_txt_%s"></code></div>' % html.escape(sid))

    H.append('<div class="points" data-s="%s" data-cand="%s"></div>'
             '<div class="sub">points shown, not adjudicated: n_points=%d, nikud_flag=%s '
             '(a pointed read is not a wrong read)</div>'
             % (html.escape(sid), html.escape(r["cand"]), r["n_points"], tr["nikud"]))

    if sid in ALT_BY_SPAN:
        H.append('<div class="sub">alternatives at position(s): %s</div>'
                 % html.escape(str(sorted(ALT_BY_SPAN[sid]))))
    if sid in ALT_LENGTH_MISMATCH:
        H.append('<div class="sub">a stored alternative read differs in length from the candidate after '
                  'stripping -- shown as none rather than misaligned</div>')

    _e = html.escape(sid)
    # Change 4: three mutually-exclusive typed fault buttons, replacing the single conflated toggle --
    # pass 1 showed these have different owners (box-not-hebrew-or-blank / box-wrong-location /
    # box-edge-cut). A `fault_legacy` value imported from pass 1 is shown but never a selectable button.
    _fault_btns = "".join(
        '<button class="fault" data-s="%s" data-ft="%s" onclick="markFault(this)">%s</button> '
        % (_e, html.escape(ft), html.escape(label)) for ft, label in FAULT_TYPES)
    H.append('<div>%s<button class="abst" data-s="%s" onclick="absn(this)">abstain</button></div>'
             '<div class="legfault" data-s="%s" style="display:none">legacy fault &mdash; needs '
             're-typing</div>'
             '<input class="nt" data-s="%s" oninput="setnote(this)" placeholder="note (optional)">'
             % (_fault_btns, _e, _e, _e))
    H.append("</div></div>")

    RM[sid] = {"crop16": cr["crop"]["sha16"], "cand16": hashlib.sha256(r["cand"].encode("utf-8")).hexdigest()[:16],
               "paired_at": r["paired_at"], "n_points": r["n_points"], "nikud": bool(tr["nikud"]),
               "letter_fired": bool(r["letter_rung_would_have_fired"]), "tiles": tiles_meta}

H.append('<div id="bar">complete <b id="ncomplete">0</b> of %d &nbsp;&middot;&nbsp; untouched '
         '<b id="nleft">%d</b><br><a id="dl" download="%s" href="#">download all %d rows</a> '
         '&nbsp;&middot;&nbsp; <input type="file" accept=".jsonl,.txt" onchange="doImport(this)"> '
         '<span id="impmsg" style="color:#8aa"></span><div id="impwarn"></div>'
         '&nbsp;&middot;&nbsp; <span id="rst" style="color:#8aa"></span>'
         '<div class="sub">The downloaded file is the record; the browser is not.</div></div>'
         % (RUN_N, RUN_N, SKEL_NAME, RUN_N))

# Pass 2 (judgment call, see module docstring): its own localStorage key, so a pass-2 draft can never
# silently intermix with a pass-1 draft for the same span_ids.
SIGNATURE_RULE = "structure(tiles+insertions)+prose-refusal"
SIC_SEED_META = {}
for _ssid, _sd in SIC_SEEDS.items():
    if PASS3:
        _hits = [t["i"] for t in next(r for r in ROWS if r["sid"] == _ssid)["tiles"]
                 if t["kind"] == "consonant" and t["cand"] == _sd["printed"]]
        check(_ssid in RUN_SPAN_IDS and len(_hits) == 1,
              "sic seed %s: the printed letter must be on exactly one consonant tile of the row, found %r"
              % (_ssid, _hits))
        SIC_SEED_META[_ssid] = {"tile_i": _hits[0], "expected": _sd["expected"], "reason": _sd["reason"]}
SEEDS_JS = json.dumps(SIC_SEED_META)
STOREKEY = (SET + "_pass3") if PASS3 else ((SET + "_pass2") if PASS2 else SET)

H.append("<script>"
         + JS.replace("__RM__", json.dumps(RM, sort_keys=True))
             .replace("__SETID__", json.dumps(SET))
             .replace("__N__", str(RUN_N))
             .replace("__SKEL__", json.dumps(SKEL_NAME))
             .replace("__EXP__", json.dumps(IMPORT_EXPECTATION))
             .replace("__TYPED_FAULTS__", json.dumps([ft for ft, _ in FAULT_TYPES]))
             .replace("__LEGACY_FAULT__", json.dumps(LEGACY_FAULT_VALUE))
             .replace("__STOREKEY__", json.dumps(STOREKEY))
             .replace("__AUTOIMPORT__", json.dumps(bool(PASS23)))
             .replace("__PASS1_EMBED__", json.dumps(PASS1_EMBED_TEXT))
             .replace("__PASS1_NAME_JS__", json.dumps(PASS1_NAME))
             .replace("__P3_EMBED__", json.dumps(PASS2_EMBED_TEXT))
             .replace("__P3_EMBED_NAME__", json.dumps(PASS2_EXPORT_NAME))
             .replace("__P3_UNSIGNABLE__", json.dumps(RULE.UNSIGNABLE_PATTERN))
             .replace("__P3_SIG_RULE__", json.dumps(SIGNATURE_RULE))
             .replace("__P3_SEEDS__", SEEDS_JS)
         + "</script>")

doc = "\n".join(H)


# ---- guards, asserted over the RENDERED document, not over intermediates ------------------------------

# 0. The withholding guard is deliberately VOID on this page (the candidate is shown on purpose) but it
# must be REPLACED, not just dropped. First prove the detector can fire at all.
assert READABLE.search(_PROBE), "the Hebrew detector cannot match Hebrew at all -- a probe that misses " \
                                "passes on anything"

# 1. Every tile carries all four per-tile controls (check, cross, delete, not-in-crop); the insert
# control appears once before the first tile and once after every tile in every row, i.e.
# TOTAL_TILES + RUN_N times (rows adjacent-pairs + 1 slot each). RUN_N == SET_N outside --pass2.
_n_ok = doc.count('onclick="tOk(this)"')
_n_no = doc.count('onclick="tBad(this)"')
_n_del = doc.count('onclick="tDel(this)"')
_n_nic = doc.count('onclick="tNic(this)"')
assert _n_ok == TOTAL_TILES and _n_no == TOTAL_TILES and _n_del == TOTAL_TILES and _n_nic == TOTAL_TILES, \
    "the check control is on %d tiles, cross on %d, delete on %d, not-in-crop on %d -- not %d each -- " \
    "a tile missing any one of the four controls cannot record that verdict" \
    % (_n_ok, _n_no, _n_del, _n_nic, TOTAL_TILES)
_n_ins = doc.count('onclick="openIns(this)"')
assert _n_ins == TOTAL_TILES + RUN_N, \
    "the insert (+) control appears %d times, not %d (TOTAL_TILES %d + RUN_N %d, one slot before the " \
    "first tile and one after every tile, per row) -- an insertion position is missing" \
    % (_n_ins, TOTAL_TILES + RUN_N, TOTAL_TILES, RUN_N)

# 2. No tile ships with a verdict.
assert 'class="tile ok"' not in doc and 'class="tile bad"' not in doc and 'verdict="' not in doc, \
    "a tile or a JS state object ships pre-verdicted -- no default acceptance is allowed"
# The whole document is the wrong unit here: this page's own stylesheet selects on data-v, so a
# document-wide string count cannot tell a CSS rule from a shipped verdict. Assert over the TILE TAGS,
# which is the unit the claim is about, and assert the probe found them -- a probe that misses passes
# on nothing.
_tile_tags = re.findall(r'<div class="tile[^>]*>', doc)
assert len(_tile_tags) == TOTAL_TILES,     "the tile-tag probe found %d tags, not %d -- it cannot vouch for tiles it did not see"     % (len(_tile_tags), TOTAL_TILES)
_pre = [t for t in _tile_tags if 'data-v' in t]
assert not _pre, "%d tile(s) ship a data-v (verdict) attribute before any signer acts, e.g. %s"     % (len(_pre), _pre[0][:120])

# 3. The candidate may appear ONLY inside a tile's data-cand (one per consonant tile) or a row's points
# line (one per row); the fixed 22+5-letter palette is NOT candidate-derived and is excluded by name.
_cand_attrs = HB_CAND_ATTR.findall(doc)
assert all(READABLE.search(a) for a in _cand_attrs if a), \
    "a data-cand attribute carries no Hebrew at all -- the probe pattern is not finding what it should"
assert len(_cand_attrs) == TOTAL_CONSONANT_TILES + RUN_N, \
    "%d data-cand attribute(s) in the document, expected %d (%d consonant tiles + %d points lines) -- " \
    "the candidate is appearing somewhere other than a tile or a points line" \
    % (len(_cand_attrs), TOTAL_CONSONANT_TILES + RUN_N, TOTAL_CONSONANT_TILES, RUN_N)
_doc_wo_palette = re.sub(r'<div id="gpal_cons".*?</div>', '', doc, count=1, flags=re.S)
_doc_wo_cand = HB_CAND_ATTR.sub('data-cand=""', _doc_wo_palette)
# Pass 2 deliberately embeds pass 1's own signed verdicts verbatim (change 3) so the browser can
# auto-import them with no file prompt and no network call; at least one held row's pass-1 tile
# verdict carries a real consonant (p493:n3, disposition abstain_candidate_wrong), so the embed text
# itself contains Hebrew. That is a SECOND, precisely-located exemption (judgment call 6, see module
# docstring) -- never a loosened comparison: strip the EXACT json.dumps(PASS1_EMBED_TEXT) substring,
# and only that substring, before testing for a leak.
_doc_wo_cand_p1 = _doc_wo_cand
if PASS2:
    _p1_embed_js = json.dumps(PASS1_EMBED_TEXT)
    assert _p1_embed_js in _doc_wo_cand_p1, \
        "the pass-1 embed text is not present verbatim in the document -- change 3's auto-import " \
        "has nothing to import"
    _doc_wo_cand_p1 = _doc_wo_cand_p1.replace(_p1_embed_js, "", 1)
_leak = READABLE.search(_doc_wo_cand_p1)
assert not _leak, \
    "Hebrew/Greek leaks outside a data-cand attribute, the fixed letter palette, or the pass-1 embed " \
    "at offset %d (%r)" \
    % (_leak.start() if _leak else -1,
       _doc_wo_cand_p1[max(0, _leak.start() - 40):_leak.start() + 10] if _leak else "")

# 3c (pass 3). The embedded pass-2 signed rows are a round trip too: exactly the selection, each on the
# pixels this run cut, and the Hebrew they carry is escaped (json.dumps), never raw in the document.
if PASS3:
    _p2_back = [json.loads(_l) for _l in PASS2_EMBED_TEXT.splitlines() if _l.strip()]
    check(sorted(d["span_id"] for d in _p2_back) == sorted(RUN_SPAN_IDS),
          "the embedded pass-2 span_ids do not match this run's selection")
    check(all(d.get("crop_sha16") == RM[d["span_id"]]["crop16"] for d in _p2_back),
          "an embedded pass-2 row's crop_sha16 disagrees with this run's own cut -- the auto-import would "
          "silently match the wrong pixels")
    check(json.dumps(PASS2_EMBED_TEXT) in doc and not READABLE.search(json.dumps(PASS2_EMBED_TEXT)),
          "the pass-2 embed is not present verbatim in the document")
    check(("function applySeeds(" in doc) and ("function insVerdict(" in doc) and ("function tSic(" in doc),
          "a pass-3 console function is not defined in the document")
    check(RULE.UNSIGNABLE_PATTERN in doc.replace("\/", "/") or json.dumps(RULE.UNSIGNABLE_PATTERN) in doc,
          "the shared unsignable pattern is not injected into the console")
    check(doc.count('class="tbtn sic"') == TOTAL_CONSONANT_TILES,
          "%d sic buttons for %d consonant tiles" % (doc.count('class="tbtn sic"'), TOTAL_CONSONANT_TILES))

# 3b (change 3). The pass-1 embed is a round trip, not a hope: it must parse back to exactly RUN_N
# lines, one per selected span, each a crop_sha16 that matches what this run cut.
if PASS2:
    _p1_back = [json.loads(_l) for _l in PASS1_EMBED_TEXT.splitlines() if _l.strip()]
    assert len(_p1_back) == RUN_N, \
        "the embedded pass-1 text parses back to %d lines, not RUN_N (%d) -- the embed does not " \
        "describe this run's selection" % (len(_p1_back), RUN_N)
    _p1_back_ids = sorted(d.get("span_id") for d in _p1_back)
    assert _p1_back_ids == sorted(RUN_SPAN_IDS), \
        "the embedded pass-1 span_ids do not match this run's selection: %s" % _p1_back_ids
    _p1_back_mismatch = [d["span_id"] for d in _p1_back
                          if d.get("crop_sha16") != RM[d["span_id"]]["crop16"]]
    assert not _p1_back_mismatch, \
        "the embedded pass-1 crop_sha16 disagrees with this run's own cut for %s -- the auto-import " \
        "would silently match the wrong pixels" % _p1_back_mismatch

# 4. Note-context and page links by file:// path; no note-crop pixels embedded; the span crops ARE
# embedded (liveness for the byte test, carried over from the sheet).
def _mid64(p):
    b = base64.b64encode(io.open(str(p), "rb").read()).decode("ascii")
    return b[len(b) // 2:len(b) // 2 + 64]


assert all(_mid64(CUT_ROWS[sid]["crop"]["path"]) in doc for sid in RUN_SPAN_IDS), \
    "the embed detector cannot find the span crops, which ARE embedded in this document (the native " \
    "reference image) -- it would pass on a note crop too"
_emb = [sid for sid in RUN_SPAN_IDS
        if CUT_ROWS[sid].get("note_context") and _mid64(CUT_ROWS[sid]["note_context"]["path"]) in doc]
assert not _emb, "note pixels are EMBEDDED in the page, not linked, for %s" % _emb
_nolink = [sid for sid in RUN_SPAN_IDS
           if CUT_ROWS[sid].get("note_context") and _furl(CUT_ROWS[sid]["note_context"]["path"]) not in doc]
assert not _nolink, "a note crop was derived at cut time and the page does not link it: %s" % _nolink
assert all(_furl(CUT_ROWS[sid]["page_png"]) in doc for sid in RUN_SPAN_IDS), \
    "a row does not link its native page PNG"

# 4b (change 2, pass 2 only). Exactly one whole-note crop per row, each <img class="notecrop"> carrying
# its native width and height; no CSS rule or inline style scales it -- width:auto/height:auto is the
# only sizing a .notecrop may ever have.
_notecrop_imgs = re.findall(r'<img class="notecrop"[^>]*>', doc)
if PASS23:
    assert len(_notecrop_imgs) == RUN_N, \
        "the page renders %d note crops, not RUN_N (%d) -- change 2 requires exactly one per row" \
        % (len(_notecrop_imgs), RUN_N)
    for _sid3 in RUN_SPAN_IDS:
        _w3, _h3 = NOTE_CROP_INFO[_sid3]["native_wh"]
        assert ('width="%d" height="%d"' % (_w3, _h3)) in doc, \
            "row %s's note crop does not carry its native size %dx%d in the <img> tag" % (_sid3, _w3, _h3)
else:
    assert not _notecrop_imgs, "a note crop is rendered outside --pass2 -- the pass-1 console must not change"
_scale_rule = re.search(r'\.notecrop\s*\{[^}]*\b(?:width|height)\s*:\s*(?!auto\b)[^;}]+', CSS)
assert not _scale_rule, \
    "a CSS rule scales .notecrop numerically (%r) -- native pixels must render at native size" \
    % (_scale_rule.group(0) if _scale_rule else "")
_notecrop_inline_scale = [t for t in _notecrop_imgs
                           if re.search(r'style="[^"]*\b(?:width|height)\s*:\s*(?!auto\b)', t)]
assert not _notecrop_inline_scale, \
    "an inline style scales a .notecrop numerically: %s" % _notecrop_inline_scale[:1]

# 4c (change 2 rule 3, pass 2 only). The note-crop directory's WHY.txt exists and states the no-send rule.
if PASS23:
    assert NOTECROP_WHY_DIR.joinpath("WHY.txt").exists(), \
        "the note-crop directory has no WHY.txt -- the no-send-to-a-model rule is not recorded beside " \
        "the pixels it governs"
    _why_text = io.open(str(NOTECROP_WHY_DIR / "WHY.txt"), encoding="utf-8").read()
    assert "no note crop" in _why_text.lower() and "model" in _why_text.lower(), \
        "WHY.txt exists but does not state the no-send-to-a-model rule in words a reader would find"

# 5. Row count == the derived selection; every selected span present.
assert doc.count('<div class="row" id="row_') == RUN_N, \
    "the page renders %d rows, not %d" % (doc.count('<div class="row" id="row_'), RUN_N)
assert all(('id="row_%s"' % html.escape(sid)) in doc for sid in RUN_SPAN_IDS), \
    "a span in the selection has no row -- a page that silently narrows is how the 19-span approval " \
    "was lost"

# 6. The palette offers exactly len(CONSONANTS) letters -- asserted against the derived list, not a
# literal 27.
_n_letter_buttons = doc.count('onclick="chooseLetterGlobal(this)"')
assert _n_letter_buttons == len(CONSONANTS), \
    "the palette offers %d letters, not %d (len(CONSONANTS))" % (_n_letter_buttons, len(CONSONANTS))
assert doc.count('onclick="cantTellGlobal()"') == 1, "the can't-tell control is not present exactly once"
assert doc.count('data-choice="space"') == 1 and doc.count('data-choice="no-space"') == 1, \
    "the gap palette does not offer exactly its two choices"

# 6b (change 1). No rendered row's rung is "letter": retired 2026-10-04 after pass 1 showed the letter
# rung contradicted 3 times and confirmed never, with p921:n4 showing the mechanism (a mixed Latin/Hebrew
# crop supplies roman ink runs that agree with the consonant count by accident).
assert "rung <b>letter</b>" not in doc, \
    "a row renders rung=letter -- the letter rung is retired by directive and must not be selected"

# 6c (change 4). Exactly three typed fault buttons per row, 3 * RUN_N total; the legacy fault value is
# shown (as text, when imported) but never offered as a selectable button.
assert doc.count('onclick="markFault(this)"') == 3 * RUN_N, \
    "the typed fault buttons appear %d times, not %d (3 * RUN_N) -- a row is missing one of the three " \
    "mutually-exclusive fault types" % (doc.count('onclick="markFault(this)"'), 3 * RUN_N)
assert ('data-ft="%s"' % LEGACY_FAULT_VALUE) not in doc, \
    "the legacy fault value %r is offered as a selectable button -- it must only ever be shown as text " \
    "needing re-typing" % LEGACY_FAULT_VALUE

# 6d (change 6). The import-expectation numbers, derived from pass 1, appear in the rendered document.
if IMPORT_EXPECTATION is not None:
    assert EXP_LINE in doc, \
        "the import expectation line derived from %s does not appear in the document -- a number " \
        "computed but not shown cannot be checked by the person doing the import" % PASS1_NAME

# 7. Every JS function the HTML calls is defined in the document. importText exists only in the
# pass-2 script (JS_PASS2) -- JS_V1 is 5a0a65b verbatim and must not be asked to define it.
_fns = ["tOk", "tBad", "tDel", "tNic", "chooseLetterGlobal", "cantTellGlobal", "chooseGapGlobal",
        "setnote", "markFault", "absn", "upd", "lines", "restore", "doImport",
        "applyState", "closePalette", "openIns", "editIns", "removeIns", "insSpaceGlobal"]
if PASS23:
    _fns.append("importText")
for _fn in _fns:
    assert ("function %s(" % _fn) in doc, "the page calls %s and does not define it" % _fn

# extra, cheap: no "accept all" control of any kind.
assert "accept all" not in doc.lower() and "acceptall" not in doc.lower() and "accept-all" not in doc.lower(), \
    "an accept-all control exists -- the spec forbids one, not even per row"

PROSE = re.sub(r"data:image/png;base64,[A-Za-z0-9+/=]+", "<payload>", doc)
assert doc.count("data:image/png;base64,") >= RUN_N, \
    "the payload pattern matches %d things in a document with %d rows -- it does not describe this file" \
    % (doc.count("data:image/png;base64,"), RUN_N)
assert PROSE.count("<payload>") == doc.count("data:image/png;base64,"), \
    "the payload strip hit %d of %d payloads" % (PROSE.count("<payload>"), doc.count("data:image/png;base64,"))
assert "base64," not in PROSE, "a payload survived the strip and is inside the prose digest"
PDIG = hashlib.sha256(PROSE.encode("utf-8")).hexdigest()[:8]

# Guard list item 1. Without --pass2 the rendered document must be BYTE-IDENTICAL to 5a0a65b's: pass 2
# must never alter the pass-1 console. Checked against the two numbers the spec itself names, not a
# locally-recomputed baseline (which could drift with this very file and stop meaning anything).
if not PASS23:
    assert PDIG == "0188f491", \
        "prose digest is %s, not 5a0a65b's 0188f491 -- pass 2's own code has changed the pass-1 console" \
        % PDIG
    assert len(doc.encode("utf-8")) == 926197, \
        "document is %d bytes, not 5a0a65b's 926197 -- pass 2's own code has changed the pass-1 console" \
        % len(doc.encode("utf-8"))

sig = ";".join("%s:%s:%s" % (sid, RM[sid]["crop16"], RM[sid]["paired_at"]) for sid in RUN_SPAN_IDS) \
    + "|prose:" + PDIG
DIG = hashlib.sha256(sig.encode("utf-8")).hexdigest()[:8]
# Output filename and sidecar carry "pass2" and the row count under --pass2, so the two consoles can
# never be confused; the pass-1 console's own name (this else-branch) must not change.
if PASS3:
    OUT = OUT_DIR / ("glyphsign_%s_pass3_%dspan_%s.html" % (SET, RUN_N, DIG))
elif PASS2:
    OUT = OUT_DIR / ("glyphsign_%s_pass2_%dspan_%s.html" % (SET, RUN_N, DIG))
else:
    OUT = OUT_DIR / ("glyphsign_%s_%dspan_%s.html" % (SET, SET_N, DIG))
SIDE = OUT.with_suffix(".json")
SKEL = OUT_DIR / SKEL_NAME
check(not (PASS3 and (("pass2" in OUT.name) or ("pass2" in SIDE.name) or ("%dspan" % SET_N) in OUT.name)),
      "pass 3 must never write to a pass-1 or pass-2 filename: %s" % OUT.name)

if SIDE.exists():
    _prev = _load_json(SIDE)
    _was = (_prev or {}).get("crop_sha16") or {}
    assert not _was or _was == {sid: RM[sid]["crop16"] for sid in RUN_SPAN_IDS}, \
        "%s already records a look at DIFFERENT pixels. Overwriting it would destroy the record of " \
        "what was approved." % SIDE.name

io.open(str(OUT), "w", encoding="utf-8").write(doc)
GIT_END = git_state(_HERE)

json.dump({"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "git_start": GIT_START, "git_end": GIT_END,
           "provisional": provisional(GIT_START, GIT_END),
           "set_sha16": SET, "n": RUN_N, "pass2": PASS2, "pass3": PASS3, "mode": MODE,
           "checks_run": CHECKS, "expected_checks": EXPECTED_CHECKS,
           "note_numbering": "FILE pages (printed = file - %d)" % PRINTED_OFFSET,
           "pass2_selection": ({"dispositions": sorted(PASS2_DISPOSITIONS),
                                 "counts": {d: _ingest_dispo_counts.get(d, 0)
                                            for d in sorted(PASS2_DISPOSITIONS)}}
                                if PASS2 else None),
           "source": {"truth": TRUTH_PATH.name, "cut": CUT.name},
           "page_numbering": "FILE pages (printed = file - %d)" % PRINTED_OFFSET,
           "shown": "the candidate, as per-glyph consonant tiles with per-tile verdicts; points shown "
                    "verbatim and not adjudicated",
           "tiles": {"total": TOTAL_TILES, "consonant": TOTAL_CONSONANT_TILES, "gap": TOTAL_GAP_TILES},
           "rungs": RUNG_COUNTS,
           "letter_rung_would_have_fired": LETTER_WOULD_HAVE_FIRED,
           "letter_rung_retired": LETTER_RUNG_RETIRED,
           "tile_controls": {"confirm": _n_ok, "dispute_open": _n_no, "delete": _n_del,
                              "not_in_crop": _n_nic, "insert": _n_ins},
           "import_expectation": IMPORT_EXPECTATION,
           "gap_min_sweep": {"shipped": LETTER_GAP_MIN, "run_min_held_at": LETTER_RUN_MIN,
                             "counts_by_gap_min": GAP_MIN_SWEEP,
                             "note": "diagnostic only -- the shipped value is LETTER_GAP_MIN above, "
                                     "never chosen to maximise this count"},
           "word_count_disagreement_rows": WORD_COUNT_DISAGREES,
           "alternatives": {"files_loaded": list(ALT_FILES), "files_found": _ALT_FILES_SEEN,
                            "reads_seen_in_set": READS_SEEN, "reads_rejected_wrong_aperture": READS_REJECTED,
                            "reads_usable": READS_USABLE, "set_aperture": SET_APERTURE,
                            "spans_with_2plus_usable": SPANS_WITH_2PLUS_USABLE,
                            "tiles_offering_alternative": TILES_OFFERING_ALTERNATIVE,
                            "length_mismatch_rows": sorted(ALT_LENGTH_MISMATCH),
                            "liveness": "reads_seen_in_set >= 6 and p657:n0 present, asserted live"},
           "prose_digest": PDIG,
           "crop_sha16": {sid: RM[sid]["crop16"] for sid in RUN_SPAN_IDS},
           "note_crops": ({sid: {"note_crop_sha16": NOTE_CROP_INFO[sid]["note_crop_sha16"],
                                  "native_wh": NOTE_CROP_INFO[sid]["native_wh"],
                                  "box_in_note_crop": NOTE_CROP_INFO[sid]["box_in_note_crop"],
                                  "box_inside_note": NOTE_CROP_INFO[sid]["box_inside_note"]}
                           for sid in RUN_SPAN_IDS}
                          if PASS23 else None)},
          io.open(str(SIDE), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

skel = [{"span_id": sid, "crop_sha16": RM[sid]["crop16"], "candidate_sha16": RM[sid]["cand16"],
         "tiles": [{"i": t["i"], "kind": t["kind"], "shown": "", "verdict": "", "chose": "",
                    "paired_to": t["paired_to"]} for t in RM[sid]["tiles"]],
         "insertions": [], "complete": False, "abstain": False, "fault": "", "fault_legacy": "", "note": "",
         "points_shown_not_adjudicated": {"text": "", "n_points": RM[sid]["n_points"],
                                           "nikud_flag": RM[sid]["nikud"]},
         "derived_consonants": "", "derived_from_verdicts": True,
         "full_span_pixel_signature": True,
         "paired_at": RM[sid]["paired_at"], "letter_rung_would_have_fired": RM[sid]["letter_fired"],
         "signed_from": "pixels, candidate shown as consonant tiles, per-tile verdicts",
         "signed_in": "glyph signer, in the browser", "set_sha16": SET, "sheet": OUT.name}
        for sid in RUN_SPAN_IDS]
sk = "\n".join(json.dumps(x, ensure_ascii=False) for x in skel) + "\n"
if not PASS3:     # pass 3 imports the signed pass-2 rows; a blank skeleton would be a second, unsigned file
    io.open(str(SKEL), "w", encoding="utf-8").write(sk)

assert (CHECKS == EXPECTED_CHECKS or EXPECTED_CHECKS < 0), (
      "ran %d counted checks, EXPECTED_CHECKS for mode %s is %d" % (CHECKS, MODE, EXPECTED_CHECKS))
print("  mode %s: %d counted checks (EXPECTED_CHECKS %d)" % (MODE, CHECKS, EXPECTED_CHECKS))

print("glyph signer %s" % OUT.name)
print("  rows %d   tiles %d (consonant %d, gap %d)" % (RUN_N, TOTAL_TILES, TOTAL_CONSONANT_TILES, TOTAL_GAP_TILES))
print("  rungs: word %d, none %d" % (RUNG_COUNTS["word"], RUNG_COUNTS["none"]))
print("  letter rung would have fired on %d row(s) (retired)" % LETTER_WOULD_HAVE_FIRED)
print("  tile controls: confirm %d, dispute-open %d, delete %d, not-in-crop %d, insert %d"
      % (_n_ok, _n_no, _n_del, _n_nic, _n_ins))
if IMPORT_EXPECTATION is not None:
    print("  import expectation (from %s): %s" % (EXP_SRC_NAME, EXP_LINE))
else:
    print("  import expectation SKIPPED -- %s not found at generation time" % PASS1_NAME)
print("  word-count disagreement: %d row(s): %s" % (len(WORD_COUNT_DISAGREES), ", ".join(WORD_COUNT_DISAGREES)))
print("  alternatives: reads seen %d, rejected (aperture != %s) %d, usable %d; spans with >=2 usable %d of %d; "
      "tiles offering an alternative %d"
      % (READS_SEEN, SET_APERTURE, READS_REJECTED, READS_USABLE, SPANS_WITH_2PLUS_USABLE, RUN_N,
         TILES_OFFERING_ALTERNATIVE))
print("  prose digest %s   document bytes %d" % (PDIG, len(doc.encode("utf-8"))))
if PASS3:
    print("  pass 3 selection (derived from %s, disposition %s): %s"
          % (HELD2_NAME, PASS3_DISPOSITION, ", ".join(RUN_SPAN_IDS)))
    print("  import: %s (sha16 %s), %d signed row(s) embedded" % (PASS2_EXPORT_NAME, PASS2_EXPORT_SHA16, RUN_N))
    print("  note crops in %s" % NOTECROP_DIR)
if PASS2:
    print("  pass 2 selection: %s"
          % ", ".join("%s %d" % (d, _ingest_dispo_counts.get(d, 0)) for d in sorted(PASS2_DISPOSITIONS)))
    _box_outside_n = sum(1 for sid in RUN_SPAN_IDS if not NOTE_CROP_INFO[sid]["box_inside_note"])
    _ws = [NOTE_CROP_INFO[sid]["native_wh"][0] for sid in RUN_SPAN_IDS]
    _hs = [NOTE_CROP_INFO[sid]["native_wh"][1] for sid in RUN_SPAN_IDS]
    print("  note crops: box_inside_note false on %d row(s); native size w[%d,%d] h[%d,%d]"
          % (_box_outside_n, min(_ws), max(_ws), min(_hs), max(_hs)))
print("  sidecar %s   skeleton %s" % (SIDE.name, "(none -- pass 3 imports the signed pass-2 rows)" if PASS3 else SKEL.name))
print(banner(GIT_START, GIT_END))
