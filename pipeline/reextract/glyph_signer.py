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
import unicodedata

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "scripts"))
from PIL import Image                                                      # noqa: E402
import hebrew_aperture_diag as HAD                                        # noqa: E402
import nikud_gate                                                         # noqa: E402
from clean_run import git_state, provisional, banner                      # noqa: E402

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

MAG = 6              # tile/whole-crop magnification, nearest-neighbour
LETTER_CONTEXT_PX = 3

# The aperture this set's crops were cut at (`p<page>_n<idx>_A2_spanbox.png`, confirmed against the cut
# artifact's own crop paths). A stored read is usable only if it was taken at THIS aperture: a read is
# evidence about the pixels it saw, and A1_notebox is a different, much larger crop.
SET_APERTURE = "A2_spanbox"
ALT_FILES = ("hebrew_aperture_reads_20260920.jsonl", "hebrew_local_arms_reads_20260920.jsonl",
             "hebrew_frontier_or_reads_20260927.jsonl", "hebrew_context_axes_reads_20261004.jsonl")

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
for _sid in SPAN_IDS:
    _usable = usable_reads_for(_sid, RAW_READS_BY_SPAN)
    _texts = [d.get("gated") or d.get("raw") or "" for d in _usable]
    _alts, _flag = aligned_alternatives(TRUTH_ROWS[_sid]["hebrew"], _texts)
    if _alts:
        ALT_BY_SPAN[_sid] = _alts
    if _flag == "length-mismatch":
        ALT_LENGTH_MISMATCH.add(_sid)

SPANS_WITH_2PLUS_USABLE = sum(1 for sid in SPAN_IDS if len(usable_reads_for(sid, RAW_READS_BY_SPAN)) >= 2)
TILES_OFFERING_ALTERNATIVE = sum(len(v) for v in ALT_BY_SPAN.values())
assert SPANS_WITH_2PLUS_USABLE == 0, \
    "expected 0 of 74 spans with >=2 usable (A2_spanbox) reads on this data; got %d -- the alternatives " \
    "path IS live now and the page's unconditional 'no second read' box is no longer true" \
    % SPANS_WITH_2PLUS_USABLE


# ---- per-row pairing: letter rung > word rung > none ---------------------------------------------------

RUNG_COUNTS = {"letter": 0, "word": 0, "none": 0}
GAP_MIN_SWEEP = {gm: 0 for gm in GAP_MIN_SWEEP_VALUES}
WORD_COUNT_DISAGREES = []
ROWS = []  # built records, one per span, in SPAN_IDS order

for sid in SPAN_IDS:
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

    paired_at = "none"
    letter_assign = {}   # tile i -> (x0, x1)
    word_assign = {}     # word index -> (x0, x1)
    if len(letter_runs) == len(cons_chars) and cons_chars:
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
                 "gray_im": None})

assert sum(RUNG_COUNTS.values()) == SET_N, "the three rungs do not account for every span"
TOTAL_CONSONANT_TILES = sum(len(r["consonant_tiles"]) for r in ROWS)
TOTAL_GAP_TILES = sum(len(r["gap_tiles"]) for r in ROWS)
TOTAL_TILES = TOTAL_CONSONANT_TILES + TOTAL_GAP_TILES


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

# The page's own script. Placeholders substituted via .replace(), never %-formatted -- a literal '%' in
# prose crashed a run of the sheet once, and this file carries far more prose than that one did.
JS = r"""
var RM=__RM__, SETID=__SETID__, N=__N__, SKEL=__SKEL__, ST={}, CUR_S=null, CUR_I=null;
function trow(s){if(!ST[s])ST[s]={tv:{},note:"",fault:0,abst:0};return ST[s];}
function tileDiv(s,i){return document.getElementById("t_"+s+"_"+i);}
function setVerdict(s,i,verdict,chose){
 var r=trow(s);r.tv[i]={verdict:verdict,chose:chose||""};
 var td=tileDiv(s,i);if(td)td.setAttribute("data-v",verdict);
 closePalette();upd();}
function tOk(b){setVerdict(b.getAttribute("data-s"),b.getAttribute("data-i"),"confirmed","");}
function tBad(b){var s=b.getAttribute("data-s"),i=b.getAttribute("data-i"),k=b.getAttribute("data-k");
 CUR_S=s;CUR_I=i;
 var pal=document.getElementById(k==="gap"?"gpal_gap":"gpal_cons");
 pal.style.display="block";}
function closePalette(){var a=document.getElementById("gpal_cons"),b=document.getElementById("gpal_gap");
 if(a)a.style.display="none";if(b)b.style.display="none";CUR_S=null;CUR_I=null;}
function chooseLetterGlobal(b){if(CUR_S===null)return;setVerdict(CUR_S,CUR_I,"corrected",b.getAttribute("data-letter"));}
function cantTellGlobal(){if(CUR_S===null)return;setVerdict(CUR_S,CUR_I,"disputed","");}
function chooseGapGlobal(b){if(CUR_S===null)return;setVerdict(CUR_S,CUR_I,"corrected",b.getAttribute("data-choice"));}
function setnote(inp){trow(inp.getAttribute("data-s")).note=inp.value;upd();}
function markFault(b){var s=b.getAttribute("data-s"),r=trow(s);
 r.fault=r.fault?0:1;b.className=r.fault?"fault on":"fault";upd();}
function absn(b){var s=b.getAttribute("data-s"),r=trow(s);
 r.abst=r.abst?0:1;b.className=r.abst?"abst on":"abst";upd();}
function rowComplete(s){var m=RM[s],r=trow(s),n=m.tiles.length,k=0,i;
 for(i=0;i<n;i++){if(r.tv[m.tiles[i].i]&&r.tv[m.tiles[i].i].verdict)k++;}
 return [k,n];}
function pointsText(s){var el=document.querySelector('.points[data-s="'+s+'"]');
 return el?el.getAttribute("data-cand"):"";}
function tileShown(s,i,kind){if(kind==="gap")return "space";
 var el=tileDiv(s,i);return el?el.getAttribute("data-cand"):"";}
function lines(){
 /* EVERY span, every time -- empty rows included. A partial download dropped over a full one is how
    an approval record dies with every byte in it valid. */
 var K=Object.keys(RM).sort(),L=[],si;
 for(si=0;si<K.length;si++){var s=K[si],m=RM[s],r=trow(s),tiles=[],j;
  for(j=0;j<m.tiles.length;j++){var td=m.tiles[j],v=r.tv[td.i]||{verdict:"",chose:""};
   tiles.push({i:td.i,kind:td.kind,shown:tileShown(s,td.i,td.kind),verdict:v.verdict||"",
    chose:v.chose||"",paired_to:td.paired_to});}
  var kn=rowComplete(s);
  L.push(JSON.stringify({span_id:s,crop_sha16:m.crop16,candidate_sha16:m.cand16,tiles:tiles,
   complete:kn[0]===kn[1],abstain:!!r.abst,fault:r.fault?"not-hebrew-or-blank":"",note:r.note,
   points_shown_not_adjudicated:{text:pointsText(s),n_points:m.n_points,nikud_flag:m.nikud},
   paired_at:m.paired_at,signed_from:"pixels, candidate shown as consonant tiles, per-tile verdicts",
   signed_in:"glyph signer, in the browser",set_sha16:SETID,sheet:SKEL}));}
 return L.join("\n")+"\n";}
function upd(){var K=Object.keys(RM).sort(),nc=0,ntouch=0,i;
 for(i=0;i<K.length;i++){var s=K[i],kn=rowComplete(s),r=trow(s);
  var rowEl=document.getElementById("row_"+s);
  if(rowEl){var lab=document.getElementById("kn_"+s);
   if(lab)lab.textContent=kn[0]+"/"+kn[1]+" tiles";
   rowEl.className="row"+(kn[0]===kn[1]?" complete":"");}
  if(kn[0]===kn[1])nc++;
  if(kn[0]>0||r.fault||r.abst||r.note)ntouch++;}
 document.getElementById("ncomplete").textContent=nc;
 document.getElementById("nleft").textContent=(N-ntouch);
 var a=document.getElementById("dl");
 a.href="data:text/plain;charset=utf-8,"+encodeURIComponent(lines());
 try{localStorage.setItem("gs_"+SETID,JSON.stringify(ST));}catch(e){}}
function applyState(s){var r=ST[s],m=RM[s];if(!r||!m)return;var j;
 for(j=0;j<m.tiles.length;j++){var td=m.tiles[j],v=(r.tv||{})[td.i];
  var el=tileDiv(s,td.i);if(el&&v&&v.verdict)el.setAttribute("data-v",v.verdict);}
 var fb=document.querySelector('.fault[data-s="'+s+'"]');if(fb&&r.fault)fb.className="fault on";
 var ab=document.querySelector('.abst[data-s="'+s+'"]');if(ab&&r.abst)ab.className="abst on";
 var nt=document.querySelector('.nt[data-s="'+s+'"]');if(nt)nt.value=r.note||"";}
function restore(){
 /* BEST EFFORT ONLY -- the download is the record, not this. */
 var raw=null;try{raw=localStorage.getItem("gs_"+SETID);}catch(e){raw=null;}
 if(!raw)return 0;var S=null;try{S=JSON.parse(raw);}catch(e){return 0;}
 var K=Object.keys(S),i,k=0;
 for(i=0;i<K.length;i++){var s=K[i];if(!RM[s])continue;ST[s]=S[s];k++;applyState(s);}
 return k;}
function doImport(inp){
 var f=inp.files&&inp.files[0];if(!f)return;
 var rd=new FileReader();
 rd.onload=function(){
  var txt=rd.result||"",ln=txt.split("\n"),i,bad=[],k=0;
  for(i=0;i<ln.length;i++){var s=ln[i].replace(/^\s+|\s+$/g,"");if(!s)continue;
   var d=null;try{d=JSON.parse(s);}catch(e){continue;}
   if(!d.span_id||!RM[d.span_id])continue;
   if(d.crop_sha16!==RM[d.span_id].crop16){bad.push(d.span_id);continue;}
   var rr=trow(d.span_id);rr.tv={};var tj;
   for(tj=0;tj<(d.tiles||[]).length;tj++){var tt=d.tiles[tj];
    if(tt.verdict)rr.tv[tt.i]={verdict:tt.verdict,chose:tt.chose||""};}
   rr.note=d.note||"";rr.fault=d.fault?1:0;rr.abst=d.abstain?1:0;
   applyState(d.span_id);k++;}
  var w=document.getElementById("impwarn");
  w.textContent=bad.length?("NOT restored (crop_sha16 differs -- a re-cut span must not inherit a "+
   "verdict): "+bad.join(", ")):"";
  document.getElementById("impmsg").textContent="imported "+k+" row(s) from "+f.name;
  upd();};
 rd.readAsText(f,"utf-8");}
window.addEventListener("load",function(){var k=restore();
 document.getElementById("rst").textContent=k?("restored "+k+" row(s) from this browser"):
  "nothing restored from this browser";upd();});
"""

H = ['<!doctype html><meta charset="utf-8"><title>glyph signer %s - %d spans, per-glyph verdicts</title>'
     % (SET, SET_N), "<style>%s</style>" % CSS]
H.append("<h1>Glyph signer <code>%s</code> &mdash; %d spans, per-glyph verdicts</h1>" % (SET, SET_N))
H.append('<div class="sub">FILE pages throughout; printed = file &minus; %d. A2 span box, PAD=%d native '
         'px, over a clean tree. The candidate is SHOWN here (it was withheld on the signing sheet); '
         'every property of it -- each consonant, each word gap, the pointing -- gets its own verdict. '
         'Nothing is accepted by default.</div>' % (PRINTED_OFFSET, HAD.PAD))

H.append('<div class="note loud"><b>No second read exists for this set.</b> Of the four stored-reads '
         'files this page loads, %d read(s) across this set&rsquo;s %d spans were found (liveness: the '
         'loader actually opened %d file(s) and actually saw them); %d of those %d were taken at this '
         'set&rsquo;s own aperture (<code>%s</code>) and %d were rejected for having been read at a '
         '<i>different</i> aperture (mostly <code>A1_notebox</code>, the full note strip &mdash; '
         'different pixels, not evidence about this crop). Usable reads: <b>%d</b>. Spans with two or '
         'more usable reads: <b>%d of %d</b>. So every &#10003; here confirms a SINGLE extraction; '
         'agreement between arms is not available as evidence on this set.</div>'
         % (READS_SEEN, SET_N, _ALT_FILES_SEEN, READS_USABLE, READS_SEEN, SET_APERTURE, READS_REJECTED,
            READS_USABLE, SPANS_WITH_2PLUS_USABLE, SET_N))

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
         '<tr><td>pairing rungs</td><td>letter <b>%d</b> &middot; word <b>%d</b> &middot; none <b>%d</b></td></tr>'
         '<tr><td>word-count disagreement</td><td><b>%d</b> row(s): %s</td></tr>'
         '<tr><td>alternatives</td><td>reads seen <b>%d</b>, usable (this aperture) <b>%d</b>, spans '
         'with &ge;2 usable <b>%d</b> of %d, tiles offering an alternative <b>%d</b></td></tr>'
         '</table>' % (SET_N, TOTAL_TILES, TOTAL_CONSONANT_TILES, TOTAL_GAP_TILES,
                       RUNG_COUNTS["letter"], RUNG_COUNTS["word"], RUNG_COUNTS["none"],
                       len(WORD_COUNT_DISAGREES), html.escape(", ".join(WORD_COUNT_DISAGREES)) or "none",
                       READS_SEEN, READS_USABLE, SPANS_WITH_2PLUS_USABLE, SET_N,
                       TILES_OFFERING_ALTERNATIVE))

# The two GLOBAL palettes -- one copy each in the whole document, shown/hidden by the JS and retargeted
# per click via CUR_S/CUR_I, rather than one copy per tile. Keeps the fixed alphabet's Hebrew glyphs out
# of the per-candidate accounting below (guard 3) and off the wire 600+ times over.
_letter_buttons = "".join(
    '<button class="pbtn" data-letter="%s" onclick="chooseLetterGlobal(this)">%s</button>' % (c, c)
    for c in CONSONANTS)
H.append('<div id="gpal_cons" class="palette" style="display:none">%s'
         '<button class="pbtn canttell" onclick="cantTellGlobal()">can&rsquo;t tell</button></div>'
         % _letter_buttons)
H.append('<div id="gpal_gap" class="palette" style="display:none">'
         '<button class="pbtn gapchoice" data-choice="space" onclick="chooseGapGlobal(this)">space here</button>'
         '<button class="pbtn gapchoice" data-choice="no-space" onclick="chooseGapGlobal(this)">no space here</button>'
         '</div>')

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
    for t in r["tiles"]:
        if t["kind"] == "consonant":
            run = (r["letter_assign"].get(t["i"]) if r["paired_at"] == "letter"
                   else r["word_assign"].get(t["word_i"]) if r["paired_at"] == "word" else None)
            img_html = ""
            if r["paired_at"] == "letter" and run:
                img_html = ('<img src="%s">'
                            % _crop_slice_uri(im, run[0], run[1], context=LETTER_CONTEXT_PX, mag=MAG))
            H.append('<div class="tile cons" id="t_%s_%d" data-s="%s" data-i="%d" data-cand="%s">%s'
                      '<button class="tbtn ok" data-s="%s" data-i="%d" onclick="tOk(this)">&#10003;</button>'
                      '<button class="tbtn no" data-s="%s" data-i="%d" data-k="cons" '
                      'onclick="tBad(this)">&#10007;</button></div>'
                     % (html.escape(sid), t["i"], html.escape(sid), t["i"], html.escape(t["cand"]),
                        img_html, html.escape(sid), t["i"], html.escape(sid), t["i"]))
            tiles_meta.append({"i": t["i"], "kind": "consonant", "paired_to": list(run) if run else None})
        else:
            H.append('<div class="tile gap" id="t_%s_%d" data-s="%s" data-i="%d">'
                      '<button class="tbtn ok" data-s="%s" data-i="%d" onclick="tOk(this)">&#10003;</button>'
                      '<button class="tbtn no" data-s="%s" data-i="%d" data-k="gap" '
                      'onclick="tBad(this)">&#10007;</button></div>'
                     % (html.escape(sid), t["i"], html.escape(sid), t["i"],
                        html.escape(sid), t["i"], html.escape(sid), t["i"]))
            tiles_meta.append({"i": t["i"], "kind": "gap", "paired_to": None})

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
    H.append('<div><button class="fault" data-s="%s" onclick="markFault(this)">not Hebrew / blank '
             '&mdash; record a fault</button> '
             '<button class="abst" data-s="%s" onclick="absn(this)">abstain</button></div>'
             '<input class="nt" data-s="%s" oninput="setnote(this)" placeholder="note (optional)">'
             % (_e, _e, _e))
    H.append("</div></div>")

    RM[sid] = {"crop16": cr["crop"]["sha16"], "cand16": hashlib.sha256(r["cand"].encode("utf-8")).hexdigest()[:16],
               "paired_at": r["paired_at"], "n_points": r["n_points"], "nikud": bool(tr["nikud"]),
               "tiles": tiles_meta}

H.append('<div id="bar">complete <b id="ncomplete">0</b> of %d &nbsp;&middot;&nbsp; untouched '
         '<b id="nleft">%d</b><br><a id="dl" download="%s" href="#">download all %d rows</a> '
         '&nbsp;&middot;&nbsp; <input type="file" accept=".jsonl,.txt" onchange="doImport(this)"> '
         '<span id="impmsg" style="color:#8aa"></span><div id="impwarn"></div>'
         '&nbsp;&middot;&nbsp; <span id="rst" style="color:#8aa"></span>'
         '<div class="sub">The downloaded file is the record; the browser is not.</div></div>'
         % (SET_N, SET_N, SKEL_NAME, SET_N))

H.append("<script>"
         + JS.replace("__RM__", json.dumps(RM, sort_keys=True))
             .replace("__SETID__", json.dumps(SET))
             .replace("__N__", str(SET_N))
             .replace("__SKEL__", json.dumps(SKEL_NAME))
         + "</script>")

doc = "\n".join(H)


# ---- guards, asserted over the RENDERED document, not over intermediates ------------------------------

# 0. The withholding guard is deliberately VOID on this page (the candidate is shown on purpose) but it
# must be REPLACED, not just dropped. First prove the detector can fire at all.
assert READABLE.search(_PROBE), "the Hebrew detector cannot match Hebrew at all -- a probe that misses " \
                                "passes on anything"

# 1. Every tile carries both a check and a cross control.
_n_ok = doc.count('onclick="tOk(this)"')
_n_no = doc.count('onclick="tBad(this)"')
assert _n_ok == TOTAL_TILES and _n_no == TOTAL_TILES, \
    "the check control is on %d tiles and the cross control on %d, not %d each -- a tile missing " \
    "either control cannot record a verdict" % (_n_ok, _n_no, TOTAL_TILES)

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
assert len(_cand_attrs) == TOTAL_CONSONANT_TILES + SET_N, \
    "%d data-cand attribute(s) in the document, expected %d (%d consonant tiles + %d points lines) -- " \
    "the candidate is appearing somewhere other than a tile or a points line" \
    % (len(_cand_attrs), TOTAL_CONSONANT_TILES + SET_N, TOTAL_CONSONANT_TILES, SET_N)
_doc_wo_palette = re.sub(r'<div id="gpal_cons".*?</div>', '', doc, count=1, flags=re.S)
_doc_wo_cand = HB_CAND_ATTR.sub('data-cand=""', _doc_wo_palette)
_leak = READABLE.search(_doc_wo_cand)
assert not _leak, \
    "Hebrew/Greek leaks outside a data-cand attribute or the fixed letter palette at offset %d (%r)" \
    % (_leak.start() if _leak else -1,
       _doc_wo_cand[max(0, _leak.start() - 40):_leak.start() + 10] if _leak else "")

# 4. Note-context and page links by file:// path; no note-crop pixels embedded; the span crops ARE
# embedded (liveness for the byte test, carried over from the sheet).
def _mid64(p):
    b = base64.b64encode(io.open(str(p), "rb").read()).decode("ascii")
    return b[len(b) // 2:len(b) // 2 + 64]


assert all(_mid64(CUT_ROWS[sid]["crop"]["path"]) in doc for sid in SPAN_IDS), \
    "the embed detector cannot find the span crops, which ARE embedded in this document (the native " \
    "reference image) -- it would pass on a note crop too"
_emb = [sid for sid in SPAN_IDS
        if CUT_ROWS[sid].get("note_context") and _mid64(CUT_ROWS[sid]["note_context"]["path"]) in doc]
assert not _emb, "note pixels are EMBEDDED in the page, not linked, for %s" % _emb
_nolink = [sid for sid in SPAN_IDS
           if CUT_ROWS[sid].get("note_context") and _furl(CUT_ROWS[sid]["note_context"]["path"]) not in doc]
assert not _nolink, "a note crop was derived at cut time and the page does not link it: %s" % _nolink
assert all(_furl(CUT_ROWS[sid]["page_png"]) in doc for sid in SPAN_IDS), \
    "a row does not link its native page PNG"

# 5. Row count == 74; every span in the frozen set is present.
assert doc.count('<div class="row" id="row_') == SET_N, \
    "the page renders %d rows, not %d" % (doc.count('<div class="row" id="row_'), SET_N)
assert all(('id="row_%s"' % html.escape(sid)) in doc for sid in SPAN_IDS), \
    "a span in the frozen set has no row -- a page that silently narrows is how the 19-span approval " \
    "was lost"

# 6. The palette offers exactly len(CONSONANTS) letters -- asserted against the derived list, not a
# literal 27.
_n_letter_buttons = doc.count('onclick="chooseLetterGlobal(this)"')
assert _n_letter_buttons == len(CONSONANTS), \
    "the palette offers %d letters, not %d (len(CONSONANTS))" % (_n_letter_buttons, len(CONSONANTS))
assert doc.count('onclick="cantTellGlobal()"') == 1, "the can't-tell control is not present exactly once"
assert doc.count('data-choice="space"') == 1 and doc.count('data-choice="no-space"') == 1, \
    "the gap palette does not offer exactly its two choices"

# 7. Every JS function the HTML calls is defined in the document.
for _fn in ("tOk", "tBad", "chooseLetterGlobal", "cantTellGlobal", "chooseGapGlobal", "setnote",
            "markFault", "absn", "upd", "lines", "restore", "doImport", "applyState", "closePalette"):
    assert ("function %s(" % _fn) in doc, "the page calls %s and does not define it" % _fn

# extra, cheap: no "accept all" control of any kind.
assert "accept all" not in doc.lower() and "acceptall" not in doc.lower() and "accept-all" not in doc.lower(), \
    "an accept-all control exists -- the spec forbids one, not even per row"

PROSE = re.sub(r"data:image/png;base64,[A-Za-z0-9+/=]+", "<payload>", doc)
assert doc.count("data:image/png;base64,") >= SET_N, \
    "the payload pattern matches %d things in a document with %d rows -- it does not describe this file" \
    % (doc.count("data:image/png;base64,"), SET_N)
assert PROSE.count("<payload>") == doc.count("data:image/png;base64,"), \
    "the payload strip hit %d of %d payloads" % (PROSE.count("<payload>"), doc.count("data:image/png;base64,"))
assert "base64," not in PROSE, "a payload survived the strip and is inside the prose digest"
PDIG = hashlib.sha256(PROSE.encode("utf-8")).hexdigest()[:8]

sig = ";".join("%s:%s:%s" % (sid, RM[sid]["crop16"], RM[sid]["paired_at"]) for sid in SPAN_IDS) \
    + "|prose:" + PDIG
DIG = hashlib.sha256(sig.encode("utf-8")).hexdigest()[:8]
OUT = HAD.DATA / ("glyphsign_%s_%dspan_%s.html" % (SET, SET_N, DIG))
SIDE = OUT.with_suffix(".json")
SKEL = HAD.DATA / SKEL_NAME

if SIDE.exists():
    _prev = _load_json(SIDE)
    _was = (_prev or {}).get("crop_sha16") or {}
    assert not _was or _was == {sid: RM[sid]["crop16"] for sid in SPAN_IDS}, \
        "%s already records a look at DIFFERENT pixels. Overwriting it would destroy the record of " \
        "what was approved." % SIDE.name

io.open(str(OUT), "w", encoding="utf-8").write(doc)
GIT_END = git_state(_HERE)

json.dump({"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "git_start": GIT_START, "git_end": GIT_END,
           "provisional": provisional(GIT_START, GIT_END),
           "set_sha16": SET, "n": SET_N, "source": {"truth": TRUTH_PATH.name, "cut": CUT.name},
           "page_numbering": "FILE pages (printed = file - %d)" % PRINTED_OFFSET,
           "shown": "the candidate, as per-glyph consonant tiles with per-tile verdicts; points shown "
                    "verbatim and not adjudicated",
           "tiles": {"total": TOTAL_TILES, "consonant": TOTAL_CONSONANT_TILES, "gap": TOTAL_GAP_TILES},
           "rungs": RUNG_COUNTS,
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
           "crop_sha16": {sid: RM[sid]["crop16"] for sid in SPAN_IDS}},
          io.open(str(SIDE), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

skel = [{"span_id": sid, "crop_sha16": RM[sid]["crop16"], "candidate_sha16": RM[sid]["cand16"],
         "tiles": [{"i": t["i"], "kind": t["kind"], "shown": "", "verdict": "", "chose": "",
                    "paired_to": t["paired_to"]} for t in RM[sid]["tiles"]],
         "complete": False, "abstain": False, "fault": "", "note": "",
         "points_shown_not_adjudicated": {"text": "", "n_points": RM[sid]["n_points"],
                                           "nikud_flag": RM[sid]["nikud"]},
         "paired_at": RM[sid]["paired_at"],
         "signed_from": "pixels, candidate shown as consonant tiles, per-tile verdicts",
         "signed_in": "glyph signer, in the browser", "set_sha16": SET, "sheet": OUT.name}
        for sid in SPAN_IDS]
sk = "\n".join(json.dumps(x, ensure_ascii=False) for x in skel) + "\n"
io.open(str(SKEL), "w", encoding="utf-8").write(sk)

print("glyph signer %s" % OUT.name)
print("  rows %d   tiles %d (consonant %d, gap %d)" % (SET_N, TOTAL_TILES, TOTAL_CONSONANT_TILES, TOTAL_GAP_TILES))
print("  rungs: letter %d, word %d, none %d" % (RUNG_COUNTS["letter"], RUNG_COUNTS["word"], RUNG_COUNTS["none"]))
print("  word-count disagreement: %d row(s): %s" % (len(WORD_COUNT_DISAGREES), ", ".join(WORD_COUNT_DISAGREES)))
print("  alternatives: reads seen %d, rejected (aperture != %s) %d, usable %d; spans with >=2 usable %d of %d; "
      "tiles offering an alternative %d"
      % (READS_SEEN, SET_APERTURE, READS_REJECTED, READS_USABLE, SPANS_WITH_2PLUS_USABLE, SET_N,
         TILES_OFFERING_ALTERNATIVE))
print("  prose digest %s   document bytes %d" % (PDIG, len(doc.encode("utf-8"))))
print("  sidecar %s   skeleton %s" % (SIDE.name, SKEL.name))
print(banner(GIT_START, GIT_END))
