"""Hebrew-span localizer (config-v2 pixel isolation) — locates the Hebrew box by COUNTING, not by
recognizing script. The design (Chris, 2026-09-06): a footnote line segments into WORD boxes by connected
ink + inter-word gaps — real CV, no classifier. The note's extracted text tokenizes into Latin words, a
Greek run, and one contiguous Hebrew run. You know how many non-Hebrew words precede the Hebrew run and how
many follow, so the Hebrew box is the run of word-boxes at that index range — selected by counting, which is
reliable even when the Hebrew READING is garbage. That is why this is robust exactly where the reader is
not: Latin word counts don't depend on the Hebrew being read correctly.

FAIL LOUD, FOR FREE: if the number of word-boxes on the line ≠ the number of text tokens, the alignment
ABSTAINS and flags — and that count mismatch is itself a useful tripwire (a dropped or merged word). No box
is ever guessed; a consumer (nikud gate, glyph-count) that gets no box abstains rather than crop blind.

RTL is not a problem: the Hebrew run is one contiguous visual block, and everything outside it is LTR, so
the run's index range in logical token order equals its box-index range in visual (left-to-right) order —
the internal right-to-left reversal is inside the block and doesn't move the block's extent.

Input is the NOTE-LINE crop (the footnote line(s) for one note). Producing that per-note line region from
the page is the UPSTREAM step (the extractor's span isolation) — not this module's job."""
import re
import numpy as np

_HEB = re.compile(r"[֐-׿יִ-ﭏ]")
_GRK = re.compile(r"[Ͱ-Ͽἀ-῿]")

def _script(word):
    if _HEB.search(word): return "hebrew"
    if _GRK.search(word): return "greek"
    return "latin"

def tokenize(text):
    """Whitespace tokens, each typed by script. Returns [(script, word)]."""
    return [(_script(w), w) for w in (text or "").split() if w.strip()]

def word_boxes(line_crop, word_gap_frac=0.45, min_run_w=3):
    """Segment a single-line crop into ordered (x0, x1) WORD x-ranges (left→right). A blank column-run
    wider than word_gap_frac × line-height is a WORD gap; narrower blanks are within-word (between letters).
    Runs narrower than min_run_w px are dropped (specks)."""
    a = np.asarray(line_crop.convert("L")) < 128
    if a.sum() < 10:
        return []
    H = a.shape[0]
    word_gap = max(4, int(word_gap_frac * H))
    col = a.sum(axis=0) > 1
    words, start, gap = [], None, 0
    for i, c in enumerate(col):
        if c:
            if start is None: start = i
            gap = 0
        elif start is not None:
            gap += 1
            if gap >= word_gap:
                if (i - gap) - start >= min_run_w: words.append((start, i - gap))
                start = None; gap = 0
    if start is not None and len(col) - start >= min_run_w:
        words.append((start, len(col)))
    return words

def align(tokens, boxes, height):
    """Pure counting alignment — the heart of the localizer, independent of CV. Returns (box, status).
    Locates the Hebrew run's box by INDEX (count of preceding tokens), never by recognizing which box is
    Hebrew. status: 'ok' | 'count-mismatch' | 'no-hebrew' | 'hebrew-not-contiguous' | 'empty'."""
    heb_idx = [i for i, (s, _) in enumerate(tokens) if s == "hebrew"]
    if not tokens:
        return None, "empty"
    if not heb_idx:
        return None, "no-hebrew"
    if heb_idx != list(range(heb_idx[0], heb_idx[-1] + 1)):
        return None, "hebrew-not-contiguous"          # >1 Hebrew run; isolate upstream, don't guess
    if len(boxes) != len(tokens):
        return None, "count-mismatch"                 # fail loud — also a dropped/merged-word tripwire
    x0 = min(boxes[i][0] for i in heb_idx)
    x1 = max(boxes[i][1] for i in heb_idx)
    return (x0, 0, x1, height), "ok"

def locate_hebrew(line_crop, note_text):
    """Locate the Hebrew box on a single-line note crop. Returns (box, status); box=(x0,y0,x1,y1) or None.
    box is the union of the Hebrew word-boxes, selected by counting non-Hebrew tokens around the run."""
    return align(tokenize(note_text), word_boxes(line_crop), line_crop.size[1])
