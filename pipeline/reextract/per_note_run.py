"""PER-NOTE run — the same failure set as router_run, but with per-note pre-segmentation (gemma, one
crop per hanging-indent note-start). Diffed against the baseline (router_run) to answer: does pre-
segmentation dissolve the segmentation-collapse class and demote the router to residual handler?
gemma-only (stays loaded); per-note = one VLM call per note, so slower but all local.
"""
import sys, os, re, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import assembler as A
import cv_footnote_presplit as ps
import hanging_indent as hi
from per_note_extract import per_note_read
import httpx

IMG = "c:/Users/cnogr/git/dr-voluminous/commentary/volume1"
HEB = re.compile(r"[\u0590-\u05FF]")
from router_run import EXPECT, PAGES   # same failure set

def main():
    host = os.getenv("OLLAMA_HOST", "192.168.1.169")
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "per_note_run_out.json"
    profile = A.load_profile(str(Path(__file__).parent / "book_profile.gill.yaml"))
    UP = profile['transcription'].get('apparatus_upscale', 2)
    rows = []; t0 = time.time()
    print("### per-note pre-segmentation, gemma4:31b ###", flush=True)
    for pg in PAGES:
        strip, _ = ps.presplit(f"{IMG}/page{pg}_image1.png", upscale=UP)
        cv, _s, conf = hi.count_notes(strip, upscale=UP)
        notes, mode = per_note_read(strip, host, profile, "gemma4:31b", upscale=UP)
        heb = any(HEB.search(n["text"]) for n in notes)
        rows.append({"page": pg, "cv": cv, "cv_conf": conf, "mode": mode,
                     "final_n": len(notes), "expect": EXPECT[pg], "hebrew": heb})
        print(f"  p{pg}: mode={mode} n={len(notes)} cv={cv} exp={EXPECT[pg]}", flush=True)
    try: httpx.post(f"http://{host}:11434/api/generate", json={"model": "gemma4:31b", "keep_alive": 0, "prompt": ""}, timeout=60)
    except Exception: pass
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    seg = [r for r in rows if r["expect"]]
    rec = sum(1 for r in seg if r["final_n"] >= 0.7 * r["expect"])
    heb_pages = [r for r in rows if r["expect"] is None]
    print(f"\n=== PER-NOTE ({time.time()-t0:.0f}s) ===")
    print(f"segmentation recovered: {rec}/{len(seg)}   (router baseline / old qwen3.6 3/8 for comparison)")
    print(f"per-note mode used: {sum(1 for r in rows if r['mode']=='per-note')}/{len(rows)} "
          f"(rest fell back to whole-strip on low CV confidence)")
    print(f"hebrew present: {sum(1 for r in heb_pages if r['hebrew'])}/{len(heb_pages)}")
    print(f"written -> {out}")

if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    main()
