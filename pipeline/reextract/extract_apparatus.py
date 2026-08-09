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

def _body_before_defs(md):
    return A.split_body_defs(md)[0]     # robust body/def split (all zoo def formats)

def extract_page(image_path, profile, host, body_md=None):
    up = profile["transcription"].get("apparatus_upscale", 2)
    strip, info = presplit.presplit(str(image_path), upscale=up)
    page = re.search(r"page(\d+)", Path(image_path).name)
    page = page.group(1) if page else "?"
    if strip is None:
        return {"page": page, "status": "no_apparatus", "notes": [], "info": info}
    resp, done = transcribe(strip, profile, host)
    r = A.canonicalize_page(resp.splitlines(), profile)
    recrop_changes = []
    if profile["transcription"].get("recrop_base_upscale"):
        import hebrew_recrop as hr        # per-region non-Latin re-crop (resolution lever)
        recrop_changes = hr.recrop_nonlatin(image_path, r["notes"], profile, host)
    viol = A.assert_no_text_split(r["notes"], profile)
    md = "\n".join(f"{n['marker']}: {n['text']}" for n in r["notes"])
    status = "STITCH_VIOLATION" if viol else "OK"
    match = None
    if body_md and Path(body_md).exists():
        match = A.match_notes_to_anchors(r["notes"], _body_before_defs(Path(body_md).read_text(encoding="utf-8")), profile)
        if match["status"] != "OK" and status == "OK":
            status = f"ANCHOR_{match['status']}"     # e.g. ANCHOR_FLAGGED: notes with no body anchor
    return {"page": page, "status": status, "done_reason": done, "n_notes": len(r["notes"]),
            "violations": viol, "dropped_furniture": r["dropped_furniture"], "notes": r["notes"],
            "markdown": md, "presplit_info": info, "anchor_match": match, "recrop_changes": recrop_changes}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+", help="page image path(s)")
    ap.add_argument("--profile", default=str(Path(__file__).parent / "book_profile.gill.yaml"))
    ap.add_argument("--host", default=os.getenv("OLLAMA_HOST", "192.168.1.179"))
    ap.add_argument("--body-dir", default="", help="dir of body .md files (for anchor matching)")
    a = ap.parse_args()
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    except Exception: pass
    profile = A.load_profile(a.profile)
    for img in a.images:
        body_md = ""
        if a.body_dir:
            body_md = str(Path(a.body_dir) / (Path(img).stem + ".md"))
        res = extract_page(img, profile, a.host, body_md=body_md or None)
        print(f"\n{'='*66}\np{res['page']}: {res['status']}  notes={res.get('n_notes')} "
              f"done={res.get('done_reason')}  dropped_furniture={len(res.get('dropped_furniture',[]))}")
        if res.get("violations"): print("  !! STITCH VIOLATIONS:", res["violations"])
        if res.get("recrop_changes"): print("  hi-res recrop:", [f"{c['old']}→{c['new']}" for c in res["recrop_changes"]])
        m = res.get("anchor_match")
        if m: print(f"  anchor-match: {m['status']}  links={len(m['links'])} anchors={m['n_anchors']} "
                    f"unanchored={len(m['unanchored'])}"
                    + (f"  gaps={[u.get('expected_letter') for u in m['unanchored']]}" if m['unanchored'] else ""))
        print("-" * 66); print(res.get("markdown", ""))

if __name__ == "__main__":
    main()
