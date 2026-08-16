"""Scored model bakeoff on the VALIDATED failure pages (ground truth from the console + fleet audit).
Tests two hypotheses: (1) does another model fix SEGMENTATION-collapse (prior: gemma keeps markers);
(2) does a BIGGER model read Hebrew better, or is it pixels-not-parameters (prior: bigger doesn't out-SEE).

Operating rule (Chris): ONE model resident at a time — cold-load, run its whole batch, OFFLOAD
(keep_alive:0) before the next. Never co-resident (an 81GB guest spills the next model to CPU).
Checkpointed: re-run resumes; the 122b is slow so nothing is lost on interruption.
"""
import sys, os, re, json, time, argparse, copy
from pathlib import Path
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import assembler as A
from extract_apparatus import extract_page

IMG = "c:/Users/cnogr/git/dr-voluminous/commentary/volume1"
NONLATIN = re.compile(r"[\u0590-\u05FF\u0600-\u06FF]")   # Hebrew + Arabic blocks
HEB = re.compile(r"[\u0590-\u05FF]+")

MODELS = ["qwen3.6:35b", "gemma4:31b", "qwen3.8:latest", "qwen3.5:122b"]

# ground truth from the validation (fleet + Chris + my own scan reads)
SEGMENTATION = {129: 13, 146: 13, 163: 18, 226: 20, 393: 8, 625: 3, 725: 9, 784: 7}
LEMMA = [188, 252, 292, 301, 402, 458]                    # note MUST contain non-Latin lemma
HEBREW = {109: "ואת הפעם", 119: "ואת להט החרב", 286: "במקומנו",
          379: "על אשר לי", 385: "כבדו", 619: "חח", 831: "לדרתיכם"}
ALL_PAGES = sorted(set(SEGMENTATION) | set(LEMMA) | set(HEBREW))

def unload(model, host):
    try: httpx.post(f"http://{host}:11434/api/generate",
                    json={"model": model, "keep_alive": 0, "prompt": ""}, timeout=60)
    except Exception: pass

def gpu_residency(model, host):
    """(vram_GB, total_GB, gpu_fraction) for a resident model, from /api/ps."""
    try:
        for m in httpx.get(f"http://{host}:11434/api/ps", timeout=10).json().get("models", []):
            if m["name"] == model:
                tot, vram = m.get("size", 0), m.get("size_vram", 0)
                return vram/1e9, tot/1e9, (vram/tot if tot else 0)
    except Exception: pass
    return 0.0, 0.0, 0.0

def confirm_gpu(model, host):
    """Cold-load the model with a tiny call, then confirm it is GPU-resident (not spilled to CPU).
    Returns the GPU fraction; warns loudly if <0.99 (the gemma-in-CPU failure mode)."""
    t0 = time.time()
    try:
        httpx.post(f"http://{host}:11434/api/generate",     # warm up at the WORKING ctx (16k) so
                   json={"model": model, "prompt": "ok", "stream": False,   # residency is true and the
                         "options": {"num_ctx": 16384, "temperature": 0}}, timeout=1800)  # batch won't reload
    except Exception as e:
        print(f"  [load] {model}: ERROR {str(e)[:100]}", flush=True); return 0.0
    vram, tot, frac = gpu_residency(model, host)
    flag = "  <-- OK 100% GPU" if frac >= 0.99 else ("  <-- WARNING: CPU SPILL" if frac < 0.99 else "")
    print(f"  [load] {model}: {vram:.1f}/{tot:.1f} GB in GPU = {frac*100:.0f}% GPU "
          f"(cold-load {time.time()-t0:.0f}s){flag}", flush=True)
    return frac

def run_model(model, host, profile, pages, out, done):
    print(f"\n### {model} — {len(pages)} pages (cold load) ###", flush=True)
    confirm_gpu(model, host)                                # verify GPU residency before the batch
    p = copy.deepcopy(profile); p["transcription"]["model"] = model
    p["transcription"]["recrop_enabled"] = False           # isolate raw model reading
    with out.open("a", encoding="utf-8") as f:
        for pg in pages:
            if (model, pg) in done: continue
            t0 = time.time()
            try:
                r = extract_page(f"{IMG}/page{pg}_image1.png", p, host)
                notes = r.get("notes", [])
                joined = " ".join(n["text"] for n in notes)
                rec = {"model": model, "page": pg, "status": r["status"], "n_notes": len(notes),
                       "has_nonlatin": bool(NONLATIN.search(joined)),
                       "hebrew_found": HEB.findall(joined),
                       "secs": round(time.time() - t0, 1)}
            except Exception as e:
                rec = {"model": model, "page": pg, "status": "ERROR", "error": str(e)[:150]}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
            print(f"  p{pg}: {rec.get('status')} n_notes={rec.get('n_notes')} "
                  f"nonlatin={rec.get('has_nonlatin')} ({rec.get('secs')}s)", flush=True)
    unload(model, host)
    print(f"### {model} offloaded ###", flush=True)

def score(out):
    rows = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]
    by = {}
    for r in rows: by.setdefault(r["model"], {})[r["page"]] = r
    present = {r["model"] for r in rows}
    models = [m for m in MODELS if m in present] + [m for m in present if m not in MODELS]
    print("\n" + "=" * 70 + "\nSEGMENTATION (recovered = n_notes >= 70% of expected count; * = recovered)")
    print(f"  {'page':>5} {'exp':>4} " + " ".join(f"{m.split(':')[0]:>10}" for m in models))
    for pg, exp in sorted(SEGMENTATION.items()):
        cells = []
        for m in models:
            n = by.get(m, {}).get(pg, {}).get("n_notes")
            cells.append("-" if n is None else f"{n}{'*' if n and n>=0.7*exp else ''}")
        print(f"  {pg:>5} {exp:>4} " + " ".join(f"{c:>10}" for c in cells))
    print("\nDROPPED LEMMA (want HEB = non-Latin present)")
    print(f"  {'page':>5} " + " ".join(f"{m.split(':')[0]:>10}" for m in models))
    for pg in LEMMA:
        cells = ["-" if pg not in by.get(m, {}) else ("HEB" if by[m][pg].get("has_nonlatin") else "DROP") for m in models]
        print(f"  {pg:>5} " + " ".join(f"{c:>10}" for c in cells))
    print("\nHEBREW CORRECTNESS (printed vs each model's Hebrew — eyeball)")
    for pg, truth in HEBREW.items():
        print(f"  p{pg} printed={truth!r}")
        for m in models:
            hf = by.get(m, {}).get(pg, {}).get("hebrew_found")
            if pg in by.get(m, {}): print(f"      {m:>16}: {hf}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="192.168.1.169")
    ap.add_argument("--out", default=str(Path(__file__).parent / "bakeoff_out.jsonl"))
    ap.add_argument("--score-only", action="store_true")
    ap.add_argument("--preflight", action="store_true", help="cold-load each model, confirm GPU residency, unload — no batch")
    ap.add_argument("--models", default="", help="comma-separated subset to run this invocation (default: all MODELS)")
    a = ap.parse_args()
    run_models = [m.strip() for m in a.models.split(",") if m.strip()] or MODELS
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    out = Path(a.out)
    if a.score_only:
        score(out); raise SystemExit(0)
    if a.preflight:
        print("PRE-FLIGHT: confirm each model loads 100% into GPU (one at a time)")
        for model in run_models:
            confirm_gpu(model, a.host); unload(model, a.host); time.sleep(2)
        print("pre-flight done"); raise SystemExit(0)
    profile = A.load_profile(str(Path(__file__).parent / "book_profile.gill.yaml"))
    done = set()
    if out.exists():
        for l in out.read_text(encoding="utf-8").splitlines():
            if l.strip():
                r = json.loads(l)
                if r.get("status") != "ERROR": done.add((r["model"], r["page"]))
    for model in run_models:                               # sequential — one resident at a time
        run_model(model, a.host, profile, ALL_PAGES, out, done)
    score(out)
