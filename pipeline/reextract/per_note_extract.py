"""PER-NOTE pre-segmentation — the terminal form of the one-job-per-pass law. Instead of asking the
model to SEGMENT a strip (where it can fold N notes into one), the presplit uses the hanging-indent
note-start geometry (hanging_indent.count_notes) to emit ONE crop per note; the model transcribes one
note at a time, and segmentation-collapse becomes STRUCTURALLY UNREPRESENTABLE — a model handed one
note's pixels cannot fold nine into one. If the CV count is NOT confident (full-width/ambiguous), it
falls back to whole-strip transcription (the geometry isn't reliable there — don't force per-note).

This is the run that answers the open architectural question: does pre-segmentation dissolve the
collapse class and demote the router (gemma->qwen3.8 dispatch) from primary defense to residual handler?
"""
import copy, re
import httpx
import hanging_indent as hi
import blind_retry as BR
import assembler as A
from extract_apparatus import transcribe, _b64_png

PER_NOTE_PROMPT = (
    "This image is ONE footnote from a 1766 Bible commentary, cropped from the apparatus. Transcribe it "
    "verbatim as a SINGLE line, keeping its leading marker. Transcribe Hebrew in Hebrew script (right-to-"
    "left), Latin/Greek/Arabic exactly as printed. Do NOT translate, summarize, renumber, or invent. "
    "Output ONLY the one footnote line.")

def _transcribe_one(crop, profile, host):
    t = profile["transcription"]
    r = httpx.post(f"http://{host}:11434/api/generate",
        json={"model": t["model"], "prompt": PER_NOTE_PROMPT, "images": [_b64_png(crop)],
              "think": t.get("think", False), "stream": False,
              "options": {"num_ctx": 4096, "temperature": 0}}, timeout=300)
    return (r.json().get("response", "") or "").strip()

def per_note_read(strip, host, profile, model, reader=None, upscale=1):
    """(notes, mode). mode='per-note' when the CV geometry is confident (one crop per note-start);
    else 'whole-strip' (ambiguous geometry — fall back). `reader(crop)->text` injectable for tests.
    `upscale` = the strip's presplit scale (thresholds scale with it — pass apparatus_upscale in prod)."""
    p = copy.deepcopy(profile); p["transcription"]["model"] = model; p["transcription"]["recrop_enabled"] = False
    count, starts, conf = hi.count_notes(strip, upscale=upscale)
    if not conf or count < 2:
        resp, _ = transcribe(strip, p, host)
        return A.canonicalize_page(resp.splitlines(), p)["notes"], "whole-strip"
    rd = reader or (lambda crop: _transcribe_one(crop, p, host))
    notes = []
    for k in range(count):
        text = re.sub(r"\s+", " ", rd(BR.crop_note(strip, starts, k))).strip()
        if text:
            notes.append({"marker": f"[^{k + 1}]", "text": text})
    return notes, "per-note"

if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import cv_footnote_presplit as ps
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    profile = A.load_profile(str(Path(__file__).parent / "book_profile.gill.yaml"))
    strip, _ = ps.presplit("c:/Users/cnogr/git/dr-voluminous/commentary/volume1/page226_image1.png", upscale=2)
    # demo with a stub reader (no VLM): one crop per note-start -> cannot collapse
    notes, mode = per_note_read(strip, "x", profile, "gemma4:31b", reader=lambda c: "stub note")
    print(f"p226 per-note: mode={mode}, {len(notes)} notes (whole-strip gemma collapsed this to <20)")
