"""body_read -- the body-shadow reader's pure pieces plus one thin native-Ollama client call
(PREDICTION_shadow_run_20p_20261108.md, stage 2). Nothing here opens a file or a socket by itself:
`read_chunk` takes an injected client (an object with `.post(url, json=, timeout=)`), exactly like
verse_head_read.read_head, so the born tests drive it with a fake and never send a request.

Chunking is code-owned: a rect is split at printed inter-line gaps (note_start_detect.text_lines)
into chunks of at most `max_lines` lines; every boundary is the midpoint of a gap, so no boundary
can sit inside a line. `core_at_edge` is the guard that a chunk's edge does not cut a line anyway.
The 20-line cap is a capacity parameter, not a threshold derived from modes (lock: "What this does
NOT solve").
"""
from __future__ import annotations

import base64
import re

import numpy as np

import assembler
import note_start_detect as NSD
import verse_head_read as VHR

BODY_PROMPT = (
    "Transcribe the printed text in this image exactly as printed, line by line, one output line "
    "per printed line. Keep the original spelling, capitals, punctuation and hyphens; do not "
    "correct or modernise anything. Write each superscript note-reference letter as ^a^ (the "
    "letter between carets) where it stands. Write Hebrew, Greek or other non-Latin text in its "
    "own script. Output only the text."
)

MAX_LINES = 20
NUM_PREDICT = 2048
NO_LINES = "no_lines_detected"
_NL = chr(10)

_REPEAT_RE = re.compile(r"(.)\1{19}", re.S)
_LATIN_RE = re.compile(r"[A-Za-z]")


class RunFault(RuntimeError):
    """A run-level fault from the endpoint (HTTP 429/5xx or any other non-200): the whole run is
    suspect, abort and write nothing -- never an item error, never retried."""


def _ink_lines(gray, box):
    """Printed line bands of the crop `box`, in PAGE rows: [(y0, y1), ...]."""
    x0, y0, x1, y1 = box
    ink = np.asarray(gray)[y0:y1, x0:x1] < NSD.INK
    return [(y0 + a, y0 + b) for a, b in NSD.text_lines(ink)]


def chunk_rect(gray, box, max_lines=MAX_LINES):
    """-> (boxes, n_lines, flag). boxes: chunk boxes (x0,y0,x1,y1) in native px inside `box`;
    n_lines: the printed-line count per chunk; flag: None, or "no_lines_detected" when zero lines
    were found (then boxes == [box] unchanged and n_lines == [0]; the caller records the flag).
    Consecutive lines are grouped in sets of at most max_lines; each internal boundary is the
    midpoint of the gap between the last line of one group and the first line of the next. The
    first chunk starts at the box top, the last ends at the box bottom."""
    if max_lines < 1:
        raise ValueError(f"max_lines must be >= 1, got {max_lines}")
    x0, y0, x1, y1 = (int(v) for v in box)
    lines = _ink_lines(gray, (x0, y0, x1, y1))
    if not lines:
        return [(x0, y0, x1, y1)], [0], NO_LINES
    groups = [lines[i:i + max_lines] for i in range(0, len(lines), max_lines)]
    edges = [y0]
    for a, b in zip(groups, groups[1:]):
        edges.append((a[-1][1] + b[0][0]) // 2)
    edges.append(y1)
    boxes = [(x0, edges[i], x1, edges[i + 1]) for i in range(len(groups))]
    return boxes, [len(g) for g in groups], None


EDGE_CORE_FRAC = 0.35


def line_peak(gray, rect_box, lines=None):
    """The rect's typical line-core density: the median, over its text_lines bands at least half the
    median band height, of each band's peak ink row-sum (within the rect's x-range). Sliver bands
    (text_lines splits merged bands into 2-7-row fragments at valleys) and descender fringes never
    vote, so their tiny own peaks cannot make a valley row look like a line's core."""
    arr = np.asarray(gray)
    x0, _y0, x1, _y1 = (int(v) for v in rect_box)
    if lines is None:
        lines = _ink_lines(arr, tuple(int(v) for v in rect_box))
    if not lines:
        return 0.0
    half = 0.5 * float(np.median([b - a for a, b in lines]))
    rows = (arr[:, x0:x1] < NSD.INK).sum(axis=1)
    peaks = [float(rows[a:b].max()) for a, b in lines if b - a >= half]
    return float(np.median(peaks)) if peaks else 0.0


def edge_ratio(gray, rect_box, y, lines=None, peak=None):
    """min(rowsum(y-1), rowsum(y)) / line_peak of the rect (rowsums within the rect's x-range, on
    the page); 0.0 when no text_lines band of the rect holds row y-1 or row y (the edge lies in an
    inter-line gap) or y is the page's first/last row. `lines` / `peak`: the rect's bands and
    line_peak, if the caller already has them."""
    arr = np.asarray(gray)
    H = arr.shape[0]
    x0, _ry0, x1, _ry1 = (int(v) for v in rect_box)
    if not 0 < y < H:
        return 0.0
    if lines is None:
        lines = _ink_lines(arr, tuple(int(v) for v in rect_box))
    if not any(b[0] <= y < b[1] or b[0] <= y - 1 < b[1] for b in lines):
        return 0.0
    if peak is None:
        peak = line_peak(arr, rect_box, lines)
    edge = min(float((arr[y - 1, x0:x1] < NSD.INK).sum()), float((arr[y, x0:x1] < NSD.INK).sum()))
    return edge / peak if peak else 0.0


def core_at_edge(gray, chunk_box, rect_box=None):
    """True iff the chunk's top or bottom edge cuts a printed line's CORE: both rows straddling the
    edge (y-1 and y, within the x-range) carry ink row-sum >= EDGE_CORE_FRAC x the rect's typical
    line peak (edge_ratio / line_peak). This is the straddle test's rule (verse_head_read.guard_crop:
    a core run of >= 2 rows touching the boundary), applied across the edge.
    Bands and line_peak are those of `rect_box` (the stage-1 rect the chunk was cut from; default:
    the chunk itself), so the two chunks sharing an internal boundary judge it from identical
    inputs. Measuring an edge against the peak of whatever band holds it failed twice on real
    pages: a descender fringe left below a boundary (p200R) and text_lines' 2-7-row valley slivers
    (p92L, p129L, p200L) each have a tiny own peak, so a valley row read as a cut.
    Ascender/descender specks beyond an ink-tight edge are not a cut: the first version tested any
    ink pixel outside and refused 168 of 175 production chunks (every ink-tight box top).
    EDGE_CORE_FRAC is the midpoint of the two modes (MEASURE_core_at_edge_20261108.md). Known blind
    spot: a line with no x-height concentration (spaced capitals, sparse headings) can be cut
    mid-line below the threshold."""
    rect = chunk_box if rect_box is None else rect_box
    lines = _ink_lines(np.asarray(gray), tuple(int(v) for v in rect))
    peak = line_peak(gray, rect, lines)
    _x0, y0, _x1, y1 = (int(v) for v in chunk_box)
    return any(edge_ratio(gray, rect, y, lines, peak) >= EDGE_CORE_FRAC for y in (y0, y1))


def classify_read(text, done_reason, n_lines):
    """None (ok) or one of empty / truncated / degenerate_repeat / degenerate_no_latin."""
    if text is None or text.strip() == "":
        return "empty"
    if done_reason != "stop":
        return "truncated"
    if _REPEAT_RE.search(text):
        return "degenerate_repeat"
    if n_lines >= 1 and not _LATIN_RE.search(text):
        return "degenerate_no_latin"
    return None


def read_chunk(client, png_bytes):
    """One native /api/chat call (think False, stream False, temperature 0, num_predict 2048).
    -> {"text","done_reason","eval_count","http_status"}. Any non-200 status (429, 5xx, ...) or a
    reply without done:true raises RunFault; transport exceptions propagate unchanged."""
    b64 = base64.b64encode(png_bytes).decode("ascii")
    payload = {
        "model": getattr(client, "model", VHR.DEFAULT_MODEL),
        "messages": [{"role": "user", "content": BODY_PROMPT, "images": [b64]}],
        "think": False, "stream": False,
        "options": {"temperature": 0, "num_predict": NUM_PREDICT},
    }
    resp = client.post(client.base_url.rstrip("/") + "/api/chat", json=payload,
                       timeout=VHR.READ_TIMEOUT_S)
    status = getattr(resp, "status_code", 200)
    if status != 200:
        raise RunFault(f"HTTP {status} from {client.base_url}")
    body = resp.json()
    if body.get("done") is not True:
        # A non-streamed reply that is not done is the server cutting generation off, not a read:
        # on 2026-11-08 endpoint D degraded mid-run and every call (the canary chunk too) came back
        # HTTP 200, done:false, no done_reason, text ending in '/' x 31. As an item `truncated` it
        # took 3 calls to abort and the fault named "HTTP/timeout".
        raise RunFault(f"partial reply from {client.base_url}: done={body.get('done')!r}, "
                       f"done_reason={body.get('done_reason')!r}")
    return {"text": (body.get("message") or {}).get("content", ""),
            "done_reason": body.get("done_reason"),
            "eval_count": body.get("eval_count"),
            "http_status": status}


def join_wordbreaks_tagged(tagged_lines):
    """The join rule on [(line, tag), ...] -> [(joined_line, tag_of_first_part), ...]. The single
    implementation: join_wordbreaks is this over untagged lines, and the diff stage uses the tags
    to map every token back to the chunk it was printed in."""
    out = []
    for ln, tag in tagged_lines:
        if out and out[-1][0].endswith(assembler._WORDBREAK_DASH) and ln[:1].islower():
            out[-1] = (out[-1][0][:-1] + ln, out[-1][1])
        else:
            out.append((ln, tag))
    return out


def join_wordbreaks(text):
    """A line ending in a word-break dash (assembler._WORDBREAK_DASH) followed by a line whose
    first character is lowercase is joined with no space and no dash. Nothing else changes (an
    em dash is not a word-break dash; a capital or a space after the break leaves the lines)."""
    lines = [(ln, None) for ln in text.split(_NL)]
    return _NL.join(ln for ln, _ in join_wordbreaks_tagged(lines))
