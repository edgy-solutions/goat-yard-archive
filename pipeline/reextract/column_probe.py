"""FULL-WIDTH CLASSIFIER (Build 4) — one probe-battery question per strip: is the footnote apparatus a
single FULL-WIDTH column, or TWO columns (one under each body column)? Cached image, cold context (a
detection question, independent of transcription — same discipline as script_probe).

Motivation (measured): the presplit's own full_width detection has FALSE POSITIVES — p663's footnotes
are two-column but presplit flagged it full_width. So full-width detection was never independently
validated (the caveat-#3 gap), and it must not seed its own jaws. This probe is the independent
signal; jaws are SCAN-VERIFIED. Production: replaces the counter's confidence flag as the routed
full-width signal (full-width -> router residual / strip-floor; two-column -> per-note eligible).
"""
import re, base64, io
import httpx

Q_COLUMNS = ("This image is the FOOTNOTE region cropped from the bottom of a 1766 commentary page. Is the "
             "footnote text laid out as ONE single full-width column spanning the whole width, or as TWO "
             "separate columns side by side (one under each body column)? Judge by whether there is a clear "
             "vertical gutter of whitespace splitting the footnotes into a left group and a right group. "
             "Reply with only one word: FULL or TWO.")

def _b64(strip):
    buf = io.BytesIO(); strip.save(buf, format="PNG"); return base64.b64encode(buf.getvalue()).decode()

def classify_columns(strip, host, model):
    r = httpx.post(f"http://{host}:11434/api/generate",
        json={"model": model, "prompt": Q_COLUMNS, "images": [_b64(strip)], "think": False, "stream": False,
              "options": {"num_ctx": 2048, "temperature": 0}}, timeout=300).json()
    resp = (r.get("response", "") or "").strip()
    low = resp.lower()
    label = "full" if "full" in low and "two" not in low else ("two" if "two" in low else "?")
    return {"label": label, "raw": resp[:40]}
