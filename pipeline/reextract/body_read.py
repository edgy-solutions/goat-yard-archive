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


def core_at_edge(gray, chunk_box):
    """True iff a printed line (text_lines band) of the chunk crosses its top or bottom edge: the
    band touches the chunk's first/last row AND the page row just outside the chunk, within the
    chunk's x-range, also carries ink (so the line continues beyond the edge, i.e. the edge cuts
    it). A line that merely starts at an ink-tight box edge, with blank page beyond, is not cut."""
    arr = np.asarray(gray)
    H = arr.shape[0]
    x0, y0, x1, y1 = (int(v) for v in chunk_box)
    lines = _ink_lines(arr, (x0, y0, x1, y1))
    if not lines:
        return False
    if lines[0][0] <= y0 and y0 > 0 and bool((arr[y0 - 1, x0:x1] < NSD.INK).any()):
        return True
    if lines[-1][1] >= y1 and y1 < H and bool((arr[y1, x0:x1] < NSD.INK).any()):
        return True
    return False


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
    -> {"text","done_reason","eval_count","http_status"}. Any non-200 status (429, 5xx, ...)
    raises RunFault; transport exceptions propagate unchanged."""
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
