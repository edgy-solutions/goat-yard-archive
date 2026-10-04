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
from typing import Optional

import numpy as np

import endpoint_guard

DEFAULT_MODEL = "qwen3.6-16k:35b"
READ_TIMEOUT_S = 300

PROMPT = (
    "This image is the start of one printed line from an 18th-century two-column Bible "
    "commentary. If the line begins with the abbreviation 'Ver.' followed by one or more verse "
    "numbers, reply {\"ver\": true, \"numbers\": [..]} with the numbers as integers. If the line "
    "does not begin with 'Ver.', reply {\"ver\": false, \"numbers\": null}. If you cannot read "
    "it, reply {\"ver\": null, \"numbers\": null}. Reply with JSON only."
)


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

def _parse_response(raw_text):
    """Strict parse of the model's JSON reply. Returns (ver, numbers, status)."""
    try:
        obj = json.loads(raw_text)
    except Exception:
        return None, None, "error:parse"
    if not isinstance(obj, dict) or "ver" not in obj:
        return None, None, "error:parse"
    ver = obj.get("ver")
    numbers = obj.get("numbers")
    if ver not in (True, False, None):
        return None, None, "error:parse"
    if numbers is not None:
        if not isinstance(numbers, list) or not all(isinstance(n, int) for n in numbers):
            return None, None, "error:parse"
    if ver is True:
        status = "ok" if numbers else "ok"
    elif ver is False:
        status = "ok"
    else:
        status = "abstain"
    return ver, numbers, status


def read_head(client, png_bytes):
    """client: object with a `.post(url, json=...) -> response` method (response has `.json()` /
    `.status_code`, or raises on transport failure) OR a plain callable client(png_bytes) ->
    raw_text, for the simplest fakes in tests. Returns {"ver", "numbers", "status", "raw"}.
    Never raises on a malformed reply -- that is status "error:parse", not an exception. Transport
    failures (timeout, connection error, non-2xx) propagate AS EXCEPTIONS to the caller, which is
    how build_verse_regions.py's run-level fault counter (3 consecutive) tells a read error from
    a guard refusal or an abstain."""
    raw_text = client(png_bytes) if callable(client) and not hasattr(client, "post") else None
    if raw_text is None and hasattr(client, "post"):
        import base64
        b64 = base64.b64encode(png_bytes).decode("ascii")
        payload = {
            "model": getattr(client, "model", DEFAULT_MODEL),
            "messages": [{"role": "user", "content": PROMPT, "images": [b64]}],
            "think": False, "stream": False, "format": "json",
            "options": {"temperature": 0},
        }
        resp = client.post(client.base_url.rstrip("/") + "/api/chat", json=payload, timeout=READ_TIMEOUT_S)
        body = resp.json()
        raw_text = (body.get("message") or {}).get("content", "")
    ver, numbers, status = _parse_response(raw_text)
    return {"ver": ver, "numbers": numbers, "status": status, "raw": raw_text}


def guarded_read_head(client, gray_array, box, page_shape, blank_floor=0.01, uniform_std=2.0):
    """Runs guard_crop first; on anything but 'ok' the model is NEVER called and the result
    carries status 'guard_refused:<reason>'. On 'ok' it crops the native-res PNG bytes from
    gray_array via PIL and calls read_head."""
    status = guard_crop(gray_array, box, page_shape, blank_floor, uniform_std)
    if status != "ok":
        return {"ver": None, "numbers": None, "status": f"guard_refused:{status}", "raw": None}
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


def resolve_and_check(explicit_host, model, client=None):
    """endpoint_guard-gated base URL resolution + a digest fetch, for build_verse_regions.py's
    step (c): resolve, then fetch the digest BEFORE the header line is written."""
    base_url = endpoint_guard.resolve_ollama_base_url(explicit_host, purpose="verse_head_read")
    digest = model_digest(base_url, model, client=client)
    return base_url, digest
