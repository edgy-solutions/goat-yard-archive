"""verse_head_read — the ONLY module in this tree that talks to a model for step 2. Guards a
head-candidate crop (fail-loud, crop_gate-style) and reads it once: "does this line start with
'Ver.', and what numbers follow?" A model witness standing in for a template until step 3 builds
one from ratified heads (amendment point E) -- named, not hidden.

Real calls go through pipeline/common/endpoint_guard.py (no default endpoint, hard refusal of
the reserved .179/.188 pair) to native Ollama /api/chat. The HTTP client is injectable so this
module -- and the run-level fault logic in build_verse_regions.py -- can be tested with a fake
client; nothing in this file or its tests sends a real request.
"""
from __future__ import annotations

import json
import re
from typing import Optional

import numpy as np

import endpoint_guard

DEFAULT_MODEL = "qwen3.6-16k:35b"
READ_TIMEOUT_S = 300

# Head read = transcription, code parses: the model's ONLY job is to transcribe the line exactly;
# verse_regions.parse_ver_head alone decides ver/numbers/status. A prior JSON yes/no PROMPT asked
# the model to CLASSIFY the line itself, which put the parsing rule inside the model instead of in
# code (not testable, not one code-owned rule -- see verse_regions.parse_ver_head's docstring).
TRANSCRIBE_PROMPT = "Transcribe the text in this image exactly. Output only the text."


# --------------------------------------------------------------------------------------------
# guard_crop — fail-loud net against reading garbage pixels (crop_gate-style)
# --------------------------------------------------------------------------------------------

def guard_crop(gray_array, box, page_shape, blank_floor=0.01, uniform_std=2.0):
    """(status) in {"ok","clamped","blank","uniform"}. box=(x0,y0,x1,y1); page_shape=(H,W).
    'clamped' fires BEFORE pixels are even looked at: a box exceeding image bounds must never be
    silently clipped. 'blank'/'uniform' mirror crop_gate's crop_darkness / a flat crop (std
    below floor) -- a blank or textureless crop cannot carry a readable 'Ver.' token."""
    H, W = page_shape
    x0, y0, x1, y1 = box
    if x0 < 0 or y0 < 0 or x1 > W or y1 > H or x1 <= x0 or y1 <= y0:
        return "clamped"
    crop = gray_array[y0:y1, x0:x1]
    if crop.size == 0:
        return "clamped"
    dark_frac = float((crop < 128).mean())
    if dark_frac < blank_floor:
        return "blank"
    if float(crop.std()) < uniform_std:
        return "uniform"
    return "ok"


def head_crop_box(band, col_box, pad_y=None, width_frac=None):
    """The crop box for a head candidate band: y0-pad .. y1+pad, x from the column's left text
    margin to margin + width_frac*column width, at native resolution. band carries x0 (column
    box x0), y0, y1; col_box = (cx0, cy0, cx1, cy1)."""
    from note_start_detect import INK  # noqa: F401 (keeps import-by-bare-name convention visible)
    pad_y = verse_regions_pad() if pad_y is None else pad_y
    frac = verse_regions_frac() if width_frac is None else width_frac
    cx0, cy0, cx1, cy1 = col_box
    col_w = cx1 - cx0
    x0 = cx0
    x1 = int(cx0 + frac * col_w)
    y0 = band["y0"] - pad_y
    y1 = band["y1"] + pad_y
    return (x0, y0, x1, y1)


def verse_regions_pad():
    import verse_regions
    return verse_regions.CROP_PAD_Y


def verse_regions_frac():
    import verse_regions
    return verse_regions.HEAD_CROP_WIDTH_FRAC


# --------------------------------------------------------------------------------------------
# read_head — one guarded model call, strictly parsed
# --------------------------------------------------------------------------------------------

class DegenerateReplyError(RuntimeError):
    """Raised when a model reply carries no usable transcription: an explicit done:false
    (mid-stream / truncated reply, real .post client only), or content that is empty/whitespace,
    or content that is only '/' characters and whitespace (an observed degenerate failure mode on
    this endpoint). Never silently treated as a valid abstain -- counted via counter.record_error()
    in build_verse_regions.run_reads exactly like a transport failure."""


_DEGENERATE_CONTENT_RE = re.compile(r"[/\s]*")


def _is_degenerate_content(text):
    """True iff text is None, empty/whitespace-only, or made of only '/' and whitespace."""
    if text is None:
        return True
    if text.strip() == "":
        return True
    return _DEGENERATE_CONTENT_RE.fullmatch(text) is not None


def read_head(client, png_bytes):
    """client: object with a `.post(url, json=...) -> response` method (response has `.json()` /
    `.status_code`, or raises on transport failure) OR a plain callable client(png_bytes) ->
    raw_text, for the simplest fakes in tests. Returns {"text","ver","numbers","raw_head","status",
    "raw"} -- the model TRANSCRIBES (TRANSCRIBE_PROMPT), code alone parses it via
    verse_regions.parse_ver_head (one code-owned parser, never a second one here).

    Raises DegenerateReplyError for an explicit done:false, or an empty/whitespace/'/'-only reply
    -- never a silent abstain. Transport failures (timeout, connection error, non-2xx) still
    propagate as exceptions, exactly as before. Both raise paths are counted identically by
    build_verse_regions.run_reads's consecutive-error counter."""
    raw_text = client(png_bytes) if callable(client) and not hasattr(client, "post") else None
    if raw_text is None and hasattr(client, "post"):
        import base64
        b64 = base64.b64encode(png_bytes).decode("ascii")
        payload = {
            "model": getattr(client, "model", DEFAULT_MODEL),
            "messages": [{"role": "user", "content": TRANSCRIBE_PROMPT, "images": [b64]}],
            "think": False, "stream": False,
            "options": {"temperature": 0, "num_predict": 64},
        }
        resp = client.post(client.base_url.rstrip("/") + "/api/chat", json=payload, timeout=READ_TIMEOUT_S)
        body = resp.json()
        if body.get("done") is False:
            raise DegenerateReplyError(f"model reply had done:false: {body!r}")
        raw_text = (body.get("message") or {}).get("content", "")
    if _is_degenerate_content(raw_text):
        raise DegenerateReplyError(f"degenerate model reply: {raw_text!r}")
    import verse_regions
    parsed = verse_regions.parse_ver_head(raw_text)
    return {"text": raw_text, "ver": parsed["ver"], "numbers": parsed["numbers"],
            "raw_head": parsed["raw_head"], "status": parsed["status"], "raw": raw_text}


def guarded_read_head(client, gray_array, box, page_shape, blank_floor=0.01, uniform_std=2.0):
    """Runs guard_crop first; on anything but 'ok' the model is NEVER called and the result
    carries status 'guard_refused:<reason>'. On 'ok' it crops the native-res PNG bytes from
    gray_array via PIL and calls read_head."""
    status = guard_crop(gray_array, box, page_shape, blank_floor, uniform_std)
    if status != "ok":
        return {"text": None, "ver": None, "numbers": None, "raw_head": None,
                "status": f"guard_refused:{status}", "raw": None}
    from io import BytesIO
    from PIL import Image
    x0, y0, x1, y1 = box
    crop = Image.fromarray(gray_array[y0:y1, x0:x1])
    buf = BytesIO()
    crop.save(buf, format="PNG")
    return read_head(client, buf.getvalue())


# --------------------------------------------------------------------------------------------
# model_digest — fail loud if the model is simply not there
# --------------------------------------------------------------------------------------------

def model_digest(base_url, model, client=None):
    """GET {base_url}/api/tags -> the named model's digest, or raise if absent. `client` is
    injectable (an object with a `.get(url)` -> response with `.json()`); defaults to `requests`."""
    if client is None:
        import requests as client
    resp = client.get(base_url.rstrip("/") + "/api/tags", timeout=30)
    data = resp.json()
    for entry in data.get("models", []):
        if entry.get("name") == model or entry.get("model") == model:
            return entry.get("digest")
    raise RuntimeError(f"model {model!r} not found at {base_url}/api/tags")


class ConsecutiveReadErrorFault(RuntimeError):
    """Raised by ConsecutiveErrorCounter once `limit` consecutive read errors (HTTP/timeout
    transport failures -- never abstains or guard refusals) have been recorded. A run-level
    fault: build_verse_regions.py writes run_aborted and exits nonzero without a summary."""


class ConsecutiveErrorCounter:
    """Counts CONSECUTIVE transport-failure read errors; any success resets it to zero. Kept as
    a standalone, injectable-client-testable unit so the run-level fault logic is born-tested
    without driving the whole CLI."""

    def __init__(self, limit=3):
        self.limit = limit
        self.consecutive = 0

    def record_success(self):
        self.consecutive = 0

    def record_error(self):
        self.consecutive += 1
        if self.consecutive >= self.limit:
            raise ConsecutiveReadErrorFault(
                f"{self.consecutive} consecutive read errors (HTTP/timeout), aborting the run")


# --------------------------------------------------------------------------------------------
# Endpoint canary -- abort, never retry. A fixed, known-good pair of crops whose transcription is
# already known (pages 126/130 of volume 1, verified against the witness .md): if the endpoint
# stops reading them correctly, the model/endpoint has drifted or gone stale mid-run and the whole
# run is suspect -- never spliced, never silently retried on a different endpoint.
# --------------------------------------------------------------------------------------------

CANARY_CROPS = [
    {"file_page": 126, "col": "left", "box": (0, 3390, 963, 3464),
     "expected": {"ver": True, "numbers": [21]}},
    {"file_page": 130, "col": "left", "box": (0, 3079, 965, 3152),
     "expected": {"ver": True, "numbers": [6]}},
]
CANARY_EVERY = 20


class CanaryFault(RuntimeError):
    """Raised by run_canary when any canary crop's read does not match its hardcoded `expected`
    ver/numbers (or errors outright). Abort, never retry: build_verse_regions.main writes a
    header-only aborted record (status='aborted', abort_reason='canary_failed batch <k>') and
    exits nonzero without attempting the endpoint again."""


def run_canary(client, load_gray, batch, at_read):
    """Reads every CANARY_CROPS entry through `client` (real .post-style or callable fake) via
    guarded_read_head, and compares the parsed ver/numbers against each entry's hardcoded
    `expected`. load_gray(file_page) -> gray array|None, injected so this is testable without a
    real page file (build_verse_regions.main passes load_page_gray(volume_dir, ...) bound to
    file_page). `batch`/`at_read` are recorded on the result for the run header's canary log only
    -- they never affect pass/fail. Any per-crop exception (transport failure, missing page,
    DegenerateReplyError, guard refusal, mismatch) counts as that crop failing; the record still
    carries every crop's outcome before CanaryFault is raised, so a failure is visible, not blind.
    Returns the record dict on full success; raises CanaryFault otherwise."""
    crops_out = []
    ok = True
    for crop in CANARY_CROPS:
        try:
            gray = load_gray(crop["file_page"])
            if gray is None:
                raise RuntimeError("canary page image missing")
            H, W = gray.shape
            res = guarded_read_head(client, gray, crop["box"], (H, W))
            match = (res.get("ver") == crop["expected"].get("ver")
                     and res.get("numbers") == crop["expected"].get("numbers"))
            crops_out.append({"file_page": crop["file_page"], "col": crop["col"],
                               "status": res.get("status"), "ver": res.get("ver"),
                               "numbers": res.get("numbers"), "match": match})
            if not match:
                ok = False
        except Exception as e:
            crops_out.append({"file_page": crop["file_page"], "col": crop["col"],
                               "status": f"error:{e}", "match": False})
            ok = False
    record = {"batch": batch, "at_read": at_read, "ok": ok, "crops": crops_out}
    if not ok:
        raise CanaryFault(f"canary_failed batch {batch}: {record}")
    return record


def resolve_and_check(explicit_host, model, client=None):
    """endpoint_guard-gated base URL resolution + a digest fetch, for build_verse_regions.py's
    step (c): resolve, then fetch the digest BEFORE the header line is written."""
    base_url = endpoint_guard.resolve_ollama_base_url(explicit_host, purpose="verse_head_read")
    digest = model_digest(base_url, model, client=client)
    return base_url, digest
