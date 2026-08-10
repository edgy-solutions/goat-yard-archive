"""Per-region non-Latin re-crop — the resolution lever, MEASURED necessary (2026-08-09):
full-strip upscale does NOT close the Hebrew (p473 note n: 6× and 8× full-strip both `סגר עליה`,
6/7), because the VL encoder downscales a huge strip so pixels-per-glyph doesn't rise. A CONCENTRATED
band crop of the note's line does (`סגר עליהם`, 7/7). So the lever is REGION SIZE, not upscale factor.

Mechanism: for each first-pass note containing non-Latin (Hebrew/Greek/Syriac), locate its line in
the strip via a Latin-anchor Tesseract match (Tesseract mangles the Hebrew but boxes the adjacent
Latin — "clausit viam illis"), crop that band, upscale to concentrate pixels, re-transcribe, and
splice the re-read non-Latin span back into the note. Local + free.
"""
import re, io, base64, os
import httpx
from PIL import Image
import pytesseract
pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_CMD", r"C:/Program Files/Tesseract-OCR/tesseract.exe")

_NONLATIN = re.compile(r"[\u0590-\u05FF\u0370-\u03FF\u0700-\u074F]")     # Hebrew/Greek/Syriac
def _nonlatin_span(text):
    """Return the contiguous non-Latin run (with any interior spaces) in text, or None."""
    m = re.search(r"[\u0590-\u05FF\u0370-\u03FF\u0700-\u074F][\u0590-\u05FF\u0370-\u03FF\u0700-\u074F \u05B0-\u05C7]*", text)
    return m.group(0).strip() if m else None

_NIKUD = re.compile(r"[֑-ׇ]")
_HEB = re.compile(r"[֐-׿]")
_B64 = lambda img: base64.b64encode((lambda b: (img.save(b, format="PNG"), b.getvalue())[1])(io.BytesIO())).decode()

# Stage-4 v2 prompt: COMBINED CONTEXT (full strip + magnified region) + consonants-only instruction.
# The recrop's disease was context amputation; the full strip restores it while the crop keeps pixels.
_RECROP_PROMPT = (
    "Image 1 is a full footnote strip from a 1766 Bible commentary. Image 2 is a MAGNIFIED region "
    "from it containing a Hebrew word (usually followed by a Latin gloss). Using image 1 for full "
    "context, transcribe ONLY the Hebrew word shown magnified in image 2. Output the Hebrew "
    "CONSONANTS exactly as printed — the source is UNPOINTED, so do NOT add any vowel points (nikud). "
    "Output only the Hebrew word, nothing else.")

def _transcribe_combined(full_strip, region, model, host, num_ctx):
    r = httpx.post(f"http://{host}:11434/api/generate",
                   json={"model": model, "prompt": _RECROP_PROMPT, "images": [_B64(full_strip), _B64(region)],
                         "think": False, "stream": False,
                         "options": {"num_ctx": num_ctx, "temperature": 0}}, timeout=900)
    return r.json().get("response", "") or ""

def _gate_accept(new, old):
    """The recrop may ONLY reduce toward the printed CONSONANTAL form — never add marks. Rejects the
    corruptions (p150/p692 added nikud; p336 hallucinated a pointed phrase); accepts consonant
    recovery (p473 עליה->עליהם). stochastic-never-authoritative between two passes of one model."""
    if not new or not _HEB.search(new): return False
    if _NIKUD.search(new): return False                       # never add vowel points
    if re.search(r"[^֐-׿\s]", new): return False     # no stray non-Hebrew (e.g. γ)
    old_cons = _NIKUD.sub("", old)
    if abs(len(new) - len(old_cons)) > 2: return False        # small edit only (recover/drop a char), NOT truncation/replace
    return new != old

def _line_boxes(strip):
    """Tesseract line boxes: [(text, y0, y1)] over the strip."""
    d = pytesseract.image_to_data(strip, lang="eng", config="--psm 4", output_type=pytesseract.Output.DICT)
    lines = {}
    for i in range(len(d["text"])):
        if not d["text"][i].strip(): continue
        key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
        t, top, h = d["text"][i], d["top"][i], d["height"][i]
        e = lines.setdefault(key, {"words": [], "y0": top, "y1": top + h})
        e["words"].append(t); e["y0"] = min(e["y0"], top); e["y1"] = max(e["y1"], top + h)
    return [(" ".join(v["words"]), v["y0"], v["y1"]) for v in lines.values()]

def _best_line(note_text, boxes):
    """Line whose Tesseract text shares the most long Latin words with the note."""
    want = {w.lower().strip(".,;") for w in note_text.split() if w.isascii() and len(w) > 3}
    best, best_score = None, 0
    for text, y0, y1 in boxes:
        have = {w.lower().strip(".,;") for w in text.split()}
        s = len(want & have)
        if s > best_score: best, best_score = (y0, y1), s
    return best

def recrop_nonlatin(image_path, notes, profile, host):
    """Mutates notes in place: re-reads each non-Latin span at concentrated resolution. Returns
    [{marker, old, new}] for changes. MEASURED (p473): crop from a MODERATE-res strip (2×) and
    upscale the band ONCE — cropping from the 4× display strip compounds interpolation (12×) and
    degrades the glyph; pad_frac >= 0.03 is required (too-tight bands cut context and mis-read)."""
    import cv_footnote_presplit as ps      # local import: presplit lives in ../scripts (sys.path)
    t = profile["transcription"]
    base_up = t.get("recrop_base_upscale", 2); pad_frac = t.get("recrop_pad_frac", 0.04)
    scale = t.get("recrop_scale", 3); model = t["model"]; num_ctx = t.get("num_ctx", 16384)
    strip, _ = ps.presplit(str(image_path), upscale=base_up)
    if strip is None: return []
    W, H = strip.size; boxes = None; changes = []
    for n in notes:
        old = _nonlatin_span(n["text"])
        if not old: continue
        if boxes is None: boxes = _line_boxes(strip)
        band = _best_line(n["text"], boxes)
        if not band: continue
        pad = int(H * pad_frac); y0 = max(0, band[0] - pad); y1 = min(H, band[1] + pad)
        crop = strip.crop((0, y0, W, y1)).resize((W * scale, (y1 - y0) * scale), Image.LANCZOS)
        new = _nonlatin_span(_transcribe_combined(strip, crop, model, host, num_ctx))
        if _gate_accept(new, old):                # GATE: only a consonant-ward correction, never adds marks
            n["text"] = n["text"].replace(old, new); changes.append({"marker": n.get("marker"), "old": old, "new": new, "accepted": True})
        elif new and new != old:
            changes.append({"marker": n.get("marker"), "old": old, "new": new, "accepted": False})  # gated OUT
    return changes
