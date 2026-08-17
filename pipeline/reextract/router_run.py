"""BASELINE router run — apparatus_router live on the failure set with real gemma/qwen3.8 readers.
Two-phase batched so each model loads ONCE (gemma over all pages; qwen3.8 only over the pages whose
primary count diverges from the deterministic CV count) — never alternating per page. This is the
BASELINE the per-note pre-segmentation run gets diffed against (does pre-segmentation dissolve the
collapse class and demote the router to residual handler?).
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
EXPECT = {129: 13, 146: 13, 163: 18, 226: 20, 393: 8, 625: 3, 725: 9, 784: 7,   # segmentation
          188: None, 252: None, 292: None, 301: None, 402: None, 458: None,      # dropped-lemma (Hebrew present)
          109: None, 119: None, 286: None, 379: None, 385: None, 619: None, 831: None}  # hebrew-glyph
PAGES = sorted(EXPECT)

def unload(model, host):
    try: httpx.post(f"http://{host}:11434/api/generate", json={"model": model, "keep_alive": 0, "prompt": ""}, timeout=60)
    except Exception: pass

def make_reader(model, host, profile):
    p = copy.deepcopy(profile); p["transcription"]["model"] = model; p["transcription"]["recrop_enabled"] = False
    def read(strip):
        resp, _ = transcribe(strip, p, host)
        return A.canonicalize_page(resp.splitlines(), p)["notes"]
    return read

def main():
    host = os.getenv("OLLAMA_HOST", "192.168.1.169")
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "router_run_out.json"
    profile = A.load_profile(str(Path(__file__).parent / "book_profile.gill.yaml"))
    UP = profile['transcription'].get('apparatus_upscale', 2)
    strips = {pg: ps.presplit(f"{IMG}/page{pg}_image1.png", upscale=UP)[0] for pg in PAGES}
    cvres = {pg: hi.count_notes(strips[pg], upscale=UP) for pg in PAGES}   # scale-aware (strips are UPx)
    cv = {pg: cvres[pg][0] for pg in PAGES}
    cv_conf = {pg: cvres[pg][2] for pg in PAGES}
    # Phase 1: gemma primary, all pages
    print("### phase 1: gemma4:31b primary (all pages) ###", flush=True)
    gemma = make_reader("gemma4:31b", host, profile)
    primary = {}
    t0 = time.time()
    for pg in PAGES:
        primary[pg] = gemma(strips[pg]); print(f"  p{pg}: gemma n={len(primary[pg])} cv={cv[pg]}", flush=True)
    unload("gemma4:31b", host)
    # who needs fallback? primary count diverges from a confident CV count
    need = [pg for pg in PAGES if cv_conf[pg] and cv[pg] >= 3 and not R._matches(len(primary[pg]), cv[pg])]
    print(f"### phase 2: qwen3.8 fallback on {len(need)} divergent pages: {need} ###", flush=True)
    fb = {}
    if need:
        qwen = make_reader("qwen3.8:latest", host, profile)
        for pg in need:
            fb[pg] = qwen(strips[pg]); print(f"  p{pg}: qwen3.8 n={len(fb[pg])} cv={cv[pg]}", flush=True)
        unload("qwen3.8:latest", host)
    # apply router decision per page
    rows = []
    for pg in PAGES:
        pn = len(primary[pg])
        if pg not in fb:
            route, notes = "primary", primary[pg]
        else:
            fn = len(fb[pg])
            (route, notes) = min((("primary", primary[pg]), ("fallback", fb[pg])), key=lambda kv: abs(len(kv[1]) - cv[pg]))
            if not R._matches(len(notes), cv[pg]): route = "queue"
        heb = any(HEB.search(n["text"]) for n in notes)
        rows.append({"page": pg, "cv": cv[pg], "cv_conf": cv_conf[pg], "primary_n": pn,
                     "fallback_n": len(fb[pg]) if pg in fb else None, "route": route,
                     "final_n": len(notes), "expect": EXPECT[pg], "hebrew": heb})
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    # summary vs the old qwen3.6 baseline (bakeoff): segmentation recovery
    seg = [r for r in rows if r["expect"]]
    rec = sum(1 for r in seg if r["final_n"] >= 0.7 * r["expect"])
    heb_pages = [r for r in rows if r["expect"] is None]
    print(f"\n=== ROUTER BASELINE ({time.time()-t0:.0f}s) ===")
    print(f"segmentation recovered (final >= 70% expected): {rec}/{len(seg)}   (old qwen3.6 was 3/8)")
    print(f"routes: primary={sum(1 for r in rows if r['route']=='primary')} "
          f"fallback={sum(1 for r in rows if r['route']=='fallback')} queue={sum(1 for r in rows if r['route']=='queue')}")
    print(f"hebrew present on hebrew/lemma pages: {sum(1 for r in heb_pages if r['hebrew'])}/{len(heb_pages)}")
    print(f"written -> {out}")

if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    main()
