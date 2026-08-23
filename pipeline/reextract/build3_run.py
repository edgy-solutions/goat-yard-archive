"""BUILD 3 — per-note vs strip-pass on the CLEAN slice (the symmetric half; the failure-set diff is
already banked). Chris's two-pass decision rule: strip-pass stays the fast first read; per-note becomes
the accuracy pass IF it measures >= strip everywhere and > somewhere ("even 1 answer better is worth
it"; wall-time only breaks ties). The named suspect is BOUNDARY-CLIPPING at crop edges — a note that
word-wraps with a hyphen ('Contro-'/'versy') could lose the join if the crop clips a continuation line.
So this run checks per-note text for hyphen/fragment artifacts the whole-strip read (which sees the
join) would not produce, on pages the pipeline already gets right.
"""
import sys, os, re, json, time, copy
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import assembler as A
import cv_footnote_presplit as ps
import hanging_indent as hi
from per_note_extract import per_note_read
from extract_apparatus import transcribe
import apparatus_router as R
import httpx

IMG = "c:/Users/cnogr/git/dr-voluminous/commentary/volume1"
HEB = re.compile(r"[\u0590-\u05FF]")
CLIP = re.compile(r"[-\u2010\u00ad]\s*$")          # trailing word-break hyphen = unjoined continuation
CLEAN = json.loads((Path(__file__).parent / "clean_slice.json").read_text())
STRIP = {r["page"]: r for r in json.loads((Path(__file__).parent / "overnight_out.json").read_text())["clean"]}

def main():
    host = os.getenv("OLLAMA_HOST", "192.168.1.169")
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "build3_out.json"
    profile = A.load_profile(str(Path(__file__).parent / "book_profile.gill.yaml"))
    UP = profile['transcription'].get('apparatus_upscale', 2)
    # also need strip-pass TEXT for the boundary-clip comparison -> run gemma strip fresh (cheap, 1/page)
    p = copy.deepcopy(profile); p["transcription"]["model"] = "gemma4:31b"; p["transcription"]["recrop_enabled"] = False
    rows = []; t0 = time.time()
    print("### Build 3: gemma per-note vs strip on clean slice ###", flush=True)
    for pg in CLEAN:
        strip, _ = ps.presplit(f"{IMG}/page{pg}_image1.png", upscale=UP)
        cv, _s, conf = hi.count_notes(strip, upscale=UP)
        strip_notes = A.canonicalize_page(transcribe(strip, p, host)[0].splitlines(), p)["notes"]
        pn_notes, mode = per_note_read(strip, host, profile, "gemma4:31b", upscale=UP)
        s_clip = sum(1 for n in strip_notes if CLIP.search(n["text"]))
        p_clip = sum(1 for n in pn_notes if CLIP.search(n["text"]))
        s_heb = any(HEB.search(n["text"]) for n in strip_notes); p_heb = any(HEB.search(n["text"]) for n in pn_notes)
        rows.append({"page": pg, "cv": cv, "cv_conf": conf, "mode": mode,
                     "strip_n": len(strip_notes), "pernote_n": len(pn_notes),
                     "strip_clip": s_clip, "pernote_clip": p_clip,
                     "strip_heb": s_heb, "pernote_heb": p_heb})
        print(f"  p{pg}: cv={cv} strip={len(strip_notes)}(clip{s_clip}) per-note={len(pn_notes)}(clip{p_clip}) "
              f"mode={mode} heb s/p={s_heb}/{p_heb}", flush=True)
    try: httpx.post(f"http://{host}:11434/api/generate", json={"model": "gemma4:31b", "keep_alive": 0, "prompt": ""}, timeout=60)
    except Exception: pass
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    conf = [r for r in rows if r["cv_conf"] and r["cv"] >= 3]
    pn_better = [r for r in conf if R._matches(r["pernote_n"], r["cv"]) and not R._matches(r["strip_n"], r["cv"])]
    strip_better = [r for r in conf if R._matches(r["strip_n"], r["cv"]) and not R._matches(r["pernote_n"], r["cv"])]
    clip_reg = [r for r in rows if r["pernote_clip"] > r["strip_clip"]]     # per-note introduced hyphen breaks
    heb_reg = [r for r in rows if r["strip_heb"] and not r["pernote_heb"]]
    print(f"\n=== BUILD 3 ({time.time()-t0:.0f}s) — per-note vs strip on {len(rows)} clean pages ===")
    print(f"segmentation (confident n={len(conf)}): per-note-better {len(pn_better)}  strip-better {len(strip_better)}")
    print(f"BOUNDARY-CLIP regressions (per-note hyphen breaks > strip): {len(clip_reg)} {[r['page'] for r in clip_reg]}")
    print(f"Hebrew regressions (strip kept, per-note dropped): {len(heb_reg)} {[r['page'] for r in heb_reg]}")
    verdict = ("per-note >= strip everywhere AND > somewhere -> WIRE as production 2nd pass"
               if (not strip_better and not clip_reg and not heb_reg and pn_better)
               else "per-note ties or regresses -> strip stays primary, per-note shelved with this measurement")
    print(f"VERDICT: {verdict}")
    print(f"written -> {out}")

if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    main()
