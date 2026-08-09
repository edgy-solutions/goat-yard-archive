"""Per-page apparatus re-extraction — the vertical slice: page image -> clean canonical footnote
markdown. Wires the three validated pieces: deterministic CV presplit (cv_footnote_presplit) ->
local VL transcription (profile model) -> deterministic assembler (canonical [^N] markers,
furniture removal, fail-loud stitch guard). NO book-specific facts here — all read from the profile.

Passes are generic; book_profile.gill.yaml makes them Gill-specific. Host is infra (env OLLAMA_HOST).
"""
import sys, os, re, io, base64, argparse
from pathlib import Path
import httpx
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import cv_footnote_presplit as presplit
import assembler as A

TRANSCRIBE_PROMPT = (
    "This image is a strip of footnotes from an early Bible commentary, already cropped and placed "
    "in correct reading order. Transcribe EVERY footnote verbatim, one footnote per line. Each "
    "footnote begins with a single lowercase letter marker (a, b, c, ...) — keep that marker at the "
    "line start. Transcribe Latin, English, Greek and Hebrew exactly as printed; output Hebrew in "
    "Hebrew script (right-to-left). Do NOT translate, summarize, renumber, or invent. Omit running "
    "page-headers and signature marks. Output only the footnote lines.")

def _b64_png(img):
    buf = io.BytesIO(); img.save(buf, format="PNG"); return base64.b64encode(buf.getvalue()).decode()

def transcribe(strip_img, profile, host):
    t = profile["transcription"]
    r = httpx.post(f"http://{host}:11434/api/generate",
        json={"model": t["model"], "prompt": TRANSCRIBE_PROMPT, "images": [_b64_png(strip_img)],
              "think": t.get("think", False), "stream": False,
              "options": {"num_ctx": t.get("num_ctx", 16384), "temperature": 0}}, timeout=900)
    d = r.json()
    return (d.get("response", "") or ""), d.get("done_reason")

def extract_page(image_path, profile, host):
    up = profile["transcription"].get("apparatus_upscale", 2)
    strip, info = presplit.presplit(str(image_path), upscale=up)
    page = re.search(r"page(\d+)", Path(image_path).name)
    page = page.group(1) if page else "?"
    if strip is None:
        return {"page": page, "status": "no_apparatus", "notes": [], "info": info}
    resp, done = transcribe(strip, profile, host)
    r = A.canonicalize_page(resp.splitlines(), profile)
    viol = A.assert_no_text_split(r["notes"], profile)
    md = "\n".join(f"{n['marker']}: {n['text']}" for n in r["notes"])
    return {"page": page, "status": "OK" if not viol else "STITCH_VIOLATION",
            "done_reason": done, "n_notes": len(r["notes"]), "violations": viol,
            "dropped_furniture": r["dropped_furniture"], "notes": r["notes"], "markdown": md,
            "presplit_info": info}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+", help="page image path(s)")
    ap.add_argument("--profile", default=str(Path(__file__).parent / "book_profile.gill.yaml"))
    ap.add_argument("--host", default=os.getenv("OLLAMA_HOST", "192.168.1.179"))
    a = ap.parse_args()
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    except Exception: pass
    profile = A.load_profile(a.profile)
    for img in a.images:
        res = extract_page(img, profile, a.host)
        print(f"\n{'='*66}\np{res['page']}: {res['status']}  notes={res.get('n_notes')} "
              f"done={res.get('done_reason')}  dropped_furniture={len(res.get('dropped_furniture',[]))}")
        if res.get("violations"): print("  !! STITCH VIOLATIONS:", res["violations"])
        print("-" * 66); print(res.get("markdown", ""))

if __name__ == "__main__":
    main()
