"""SYMMETRIC overnight run — the router baseline, but measuring BOTH directions so gemma-primary isn't
crowned on the incumbent's home losses:
  FAILURE SET (21, qwen3.6's known breaks) -> router (gemma primary + qwen3.8 fallback): does it FIX?
  CLEAN SLICE (50 currently-OK pages, Hebrew-dense stratified) -> gemma AND qwen3.6 both: does gemma
    HOLD what the incumbent already gets right, or introduce its own regressions (segmentation quirks,
    its own Hebrew failures — it hallucinated שורש for חח)?
Three models, one resident at a time (gemma all; qwen3.6 clean-incumbent; qwen3.8 failure-fallback).
The clean slice is the half the bakeoff could not show — asymmetric evidence made symmetric.
"""
import sys, os, re, json, time, copy
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import assembler as A
import cv_footnote_presplit as ps
import hanging_indent as hi
import apparatus_router as R
from extract_apparatus import transcribe
import httpx

IMG = "c:/Users/cnogr/git/dr-voluminous/commentary/volume1"
HEB = re.compile(r"[\u0590-\u05FF]")
FAIL_EXPECT = {129: 13, 146: 13, 163: 18, 226: 20, 393: 8, 625: 3, 725: 9, 784: 7}
FAIL = sorted(list(FAIL_EXPECT) + [188, 252, 292, 301, 402, 458, 109, 119, 286, 379, 385, 619, 831])
CLEAN = json.loads((Path(__file__).parent / "clean_slice.json").read_text())

def unload(m, host):
    try: httpx.post(f"http://{host}:11434/api/generate", json={"model": m, "keep_alive": 0, "prompt": ""}, timeout=60)
    except Exception: pass

def reader(model, host, profile):
    p = copy.deepcopy(profile); p["transcription"]["model"] = model; p["transcription"]["recrop_enabled"] = False
    return lambda strip: A.canonicalize_page(transcribe(strip, p, host)[0].splitlines(), p)["notes"]

def _heb(notes): return any(HEB.search(n["text"]) for n in notes)

def main():
    host = os.getenv("OLLAMA_HOST", "192.168.1.169")
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "overnight_out.json"
    profile = A.load_profile(str(Path(__file__).parent / "book_profile.gill.yaml"))
    UP = profile['transcription'].get('apparatus_upscale', 2)
    allp = FAIL + CLEAN
    print(f"presplit {len(allp)} pages @upscale={UP}...", flush=True)
    strips = {pg: ps.presplit(f"{IMG}/page{pg}_image1.png", upscale=UP)[0] for pg in allp}
    cvr = {pg: hi.count_notes(strips[pg], upscale=UP) for pg in allp}
    t0 = time.time()
    # phase gemma (all)
    print("### gemma4:31b (all pages) ###", flush=True); g = reader("gemma4:31b", host, profile)
    gem = {}
    for pg in allp: gem[pg] = g(strips[pg]); print(f"  g p{pg}: n={len(gem[pg])} cv={cvr[pg][0]}", flush=True)
    unload("gemma4:31b", host)
    # phase qwen3.6 (clean incumbent)
    print("### qwen3.6:35b (clean slice, incumbent) ###", flush=True); q36 = reader("qwen3.6:35b", host, profile)
    q36n = {}
    for pg in CLEAN: q36n[pg] = q36(strips[pg]); print(f"  q36 p{pg}: n={len(q36n[pg])}", flush=True)
    unload("qwen3.6:35b", host)
    # phase qwen3.8 (failure fallback on divergent)
    need = [pg for pg in FAIL if cvr[pg][2] and cvr[pg][0] >= 3 and not R._matches(len(gem[pg]), cvr[pg][0])]
    print(f"### qwen3.8 (failure fallback: {need}) ###", flush=True)
    q38n = {}
    if need:
        q38 = reader("qwen3.8:latest", host, profile)
        for pg in need: q38n[pg] = q38(strips[pg]); print(f"  q38 p{pg}: n={len(q38n[pg])}", flush=True)
        unload("qwen3.8:latest", host)
    # score
    fail_rows, clean_rows = [], []
    for pg in FAIL:
        cv = cvr[pg][0]; pn = len(gem[pg])
        if pg in q38n:
            route, notes = min((("primary", gem[pg]), ("fallback", q38n[pg])), key=lambda kv: abs(len(kv[1]) - cv))
            if not R._matches(len(notes), cv): route = "queue"
        else:
            route, notes = "primary", gem[pg]
        fail_rows.append({"page": pg, "cv": cv, "route": route, "final_n": len(notes),
                          "expect": FAIL_EXPECT.get(pg), "hebrew": _heb(notes)})
    for pg in CLEAN:
        cv, conf = cvr[pg][0], cvr[pg][2]
        gm, qm = _heb(gem[pg]), _heb(q36n[pg])
        g_ok = R._matches(len(gem[pg]), cv) if conf and cv >= 3 else None
        q_ok = R._matches(len(q36n[pg]), cv) if conf and cv >= 3 else None
        seg_reg = (q_ok is True and g_ok is False)              # incumbent matched CV, gemma didn't
        heb_reg = (qm and not gm)                               # incumbent kept Hebrew, gemma dropped it
        clean_rows.append({"page": pg, "cv": cv, "cv_conf": conf, "gemma_n": len(gem[pg]),
                           "qwen36_n": len(q36n[pg]), "gemma_heb": gm, "qwen36_heb": qm,
                           "seg_regression": seg_reg, "heb_regression": heb_reg})
    out.write_text(json.dumps({"failure": fail_rows, "clean": clean_rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    seg = [r for r in fail_rows if r["expect"]]; fixrec = sum(1 for r in seg if r["final_n"] >= 0.7 * r["expect"])
    segreg = sum(1 for r in clean_rows if r["seg_regression"]); hebreg = sum(1 for r in clean_rows if r["heb_regression"])
    print(f"\n=== OVERNIGHT SYMMETRIC ({time.time()-t0:.0f}s) ===")
    print(f"FAILURE fix (router): segmentation recovered {fixrec}/{len(seg)} (old qwen3.6 3/8)")
    print(f"CLEAN hold (n={len(clean_rows)}): gemma seg-regressions {segreg}, gemma Hebrew-drops {hebreg}")
    print(f"  -> gemma HOLDS {len(clean_rows)-segreg-hebreg}/{len(clean_rows)} clean pages")
    if segreg or hebreg:
        print("  regressions:", [r["page"] for r in clean_rows if r["seg_regression"] or r["heb_regression"]])
    print(f"written -> {out}")

if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    main()
