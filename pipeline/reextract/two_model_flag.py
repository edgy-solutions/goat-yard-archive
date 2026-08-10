"""Stage-3 TWO-MODEL FLAGGING — a second local VLM (gemma4) transcribes the same strip; DISAGREEMENT
with the primary (qwen3.6) is where the adjudication found errors (two models with different priors
won't drop Gersom's final m the same way). Per the standing law, disagreement gets no model authority:
it's a FLAG (data into the review queue), never a vote — and agreement is NOT proof (shared priors →
shared hallucinations), so agreement lowers review priority rather than closing a case. Local + free
(slow — a good overnight/batch fit). Governed as DATA, not disposition.
"""
import sys, os, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import assembler as A
from extract_apparatus import transcribe
import cv_footnote_presplit as ps

def _norm(t):
    return re.sub(r"[^\wא-ת]+", "", t.lower())   # compare on alnum+Hebrew, ignore punctuation/spacing

def compare_page(image_path, profile, host, second_model="gemma4:31b"):
    """Transcribe the strip with the primary model and `second_model`; return per-note agreement and
    a list of DISAGREEMENT flags (count mismatch, or per-position text divergence)."""
    up = profile["transcription"].get("apparatus_upscale", 4)
    strip, _ = ps.presplit(str(image_path), upscale=up)
    if strip is None: return {"status": "no_apparatus", "flags": []}
    prof2 = {**profile, "transcription": {**profile["transcription"], "model": profile["transcription"]["model"]}}
    a = A.canonicalize_page(transcribe(strip, profile, host)[0].splitlines(), profile)["notes"]
    prof_b = {**profile, "transcription": {**profile["transcription"], "model": second_model}}
    b = A.canonicalize_page(transcribe(strip, prof_b, host)[0].splitlines(), prof_b)["notes"]
    flags = []
    if len(a) != len(b):
        flags.append({"type": "count-disagreement", "detail": f"{profile['transcription']['model']}={len(a)} vs {second_model}={len(b)}"})
    for i in range(min(len(a), len(b))):
        if _norm(a[i]["text"]) != _norm(b[i]["text"]):
            flags.append({"type": "text-disagreement", "marker": a[i]["marker"],
                          "primary": a[i]["text"][:60], "second": b[i]["text"][:60]})
    return {"status": "OK", "n_primary": len(a), "n_second": len(b), "flags": flags,
            "note": "flags are DATA into the review queue, not dispositions; agreement lowers priority, never closes"}

if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    host = os.getenv("OLLAMA_HOST", "192.168.1.169")
    profile = A.load_profile(str(Path(__file__).parent / "book_profile.gill.yaml"))
    profile["transcription"]["recrop_enabled"] = False   # compare BASE reads, not recrop
    for pg in (int(x) for x in (sys.argv[1:] or ["473", "550"])):
        img = f"c:/Users/cnogr/git/dr-voluminous/commentary/volume1/page{pg}_image1.png"
        r = compare_page(img, profile, host)
        print(f"p{pg}: {r['status']} primary={r.get('n_primary')} gemma4={r.get('n_second')} flags={len(r.get('flags',[]))}")
        for f in r.get("flags", []): print("   ", f)
