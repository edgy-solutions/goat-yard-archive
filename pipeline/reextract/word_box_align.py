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
    if re.search(r"[A-Za-z]", word): return "latin"
    return "punct"                                     # pure punctuation (hyphen/maqaf) — script-neutral

def tokenize(text):
    """Whitespace tokens, each typed by script. Returns [(script, word)]. 'punct' tokens (a bare hyphen or
    maqaf between Hebrew words) are neutral: they neither break a run nor consume a word-box."""
    return [(_script(w), w) for w in (text or "").split() if w.strip()]

def _hebrew_run(tokens):
    """The contiguous Hebrew run's (lo, hi) token indices, allowing interspersed punct (a maqaf splits
    `ברא ־ לעשות` into tokens but is not a break). Returns None (no Hebrew) or 'split' (a Latin/Greek WORD
    sits inside the Hebrew, so it is genuinely non-contiguous — isolate upstream, don't guess)."""
    hi = [i for i, (s, _) in enumerate(tokens) if s == "hebrew"]
    if not hi:
        return None
    lo, hh = hi[0], hi[-1]
    if any(tokens[i][0] in ("latin", "greek") for i in range(lo, hh + 1)):
        return "split"
    return (lo, hh)

def word_boxes(line_crop, min_run_w=3, gap_factor=1.6):
    """Segment a single-line crop into ordered (x0, x1) WORD x-ranges (left→right). The word-gap threshold
    is ADAPTIVE, not a fraction of the (ascender-padded) crop height: collect the blank runs between
    ink-column runs, and split words only at gaps wider than gap_factor × their median. Inter-letter gaps
    are small and frequent (they set the median); inter-word gaps are the outliers that exceed it. Runs
    narrower than min_run_w px are dropped (specks)."""
    a = np.asarray(line_crop.convert("L")) < 128
    if a.sum() < 10:
        return []
    col = a.sum(axis=0) > 1
    runs, start = [], None                             # contiguous ink-column runs (letters / strokes)
    for i, c in enumerate(col):
        if c and start is None: start = i
        elif not c and start is not None: runs.append([start, i]); start = None
    if start is not None: runs.append([start, len(col)])
    if len(runs) < 2:
        return [(s, e) for s, e in runs if e - s >= min_run_w]
    gaps = sorted(runs[k + 1][0] - runs[k][1] for k in range(len(runs) - 1))
    med = gaps[len(gaps) // 2]
    word_gap = max(6, med * gap_factor)
    words = [runs[0][:]]                               # merge runs separated by < word_gap into words
    for r in runs[1:]:
        if r[0] - words[-1][1] < word_gap: words[-1][1] = r[1]
        else: words.append(r[:])
    return [(w[0], w[1]) for w in words if w[1] - w[0] >= min_run_w]

def align(tokens, boxes, height):
    """Pure counting alignment — the heart of the localizer, independent of CV. Returns (box, status).
    Locates the Hebrew by INDEX from the LEFT: count the word-producing tokens (latin/greek/hebrew, NOT
    punct) before the Hebrew run, then take that many boxes in. It does NOT require the box count to equal
    the WHOLE note's token count — the note wraps past this line, so only the words up to and including the
    Hebrew must be present. Fail loud only when the line has FEWER boxes than needed (a dropped/merged word
    before or within the Hebrew). status: 'ok' | 'count-mismatch' | 'no-hebrew' | 'hebrew-not-contiguous'."""
    if not tokens:
        return None, "empty"
    run = _hebrew_run(tokens)
    if run is None:
        return None, "no-hebrew"
    if run == "split":
        return None, "hebrew-not-contiguous"
    lo, hh = run
    n_before = sum(1 for s, _ in tokens[:lo] if s in ("latin", "greek", "hebrew"))
    block = hh - lo + 1                                # tokens the Hebrew spans, incl. an interior maqaf —
                                                       # each is its own box (ברא ־ לעשות = 3 boxes)
    need = n_before + block
    if len(boxes) < need:
        return None, "count-mismatch"                 # dropped/merged word — a real tripwire
    sel = boxes[n_before:need]
    return (min(b[0] for b in sel), 0, max(b[1] for b in sel), height), "ok"

def strip_marker(boxes, height):
    """Drop leading non-text boxes — the note marker (raised a/b/c…) and any column-rule fragment — which
    are much narrower than a word. Iteratively drops a leftmost box narrower than 0.30x the median box
    width. The threshold clears markers (~15px) and rule fragments while keeping even a 2-letter Hebrew
    word (לך, ~80px, well above 0.30x a ~150px median). Keeps everything if nothing qualifies."""
    if len(boxes) < 2:
        return boxes
    widths = sorted(b[1] - b[0] for b in boxes)
    upper = widths[len(widths) // 2:]                  # the WORD widths — the small junk can't drag this
    word_w = upper[len(upper) // 2]
    out = list(boxes)
    removed = 0
    while len(out) > 1 and removed < 2 and (out[0][1] - out[0][0]) < 0.40 * word_w:
        out = out[1:]; removed += 1                     # at most border + marker; never eat a Hebrew word
    return out

def locate_hebrew(line_crop, note_text, drop_marker=True):
    """Locate the Hebrew box on a single-line note crop. Returns (box, status); box=(x0,y0,x1,y1) or None.
    box is the union of the Hebrew word-boxes, selected by counting non-Hebrew tokens before the run.
    The note marker is stripped by default (it is not a text token)."""
    boxes = word_boxes(line_crop)
    if drop_marker:
        boxes = strip_marker(boxes, line_crop.size[1])
    return align(tokenize(note_text), boxes, line_crop.size[1])
