"""Overnight step 4 — run the v2 typed seam over the 91 extractor-collapse pages (census: gap>=3, ext>=1,
exposition) and compare v2's note count to the census PREDICTION (the detector's independent count, det). This
is the first evidence the re-extraction does what the HOLD was for: if v2 recovers the notes the frozen
extractor lost (v2 count reaches det where ext << det), the collapse class is fixed. Build-and-measure only —
no ingest, no decisions. Checkpointed/resumable. Reports match / over / under and the status-enum distribution.

The collapse page list + predictions come from scratchpad/collapse.json (page, ext, det)."""
import sys, os, re, json, time, hashlib, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import assembler as A
from extract_apparatus import extract_page
from run_header import build_header
from data_config import data_path

IMGDIR = Path(os.getenv("VOL1_IMG", "c:/Users/cnogr/git/dr-voluminous/commentary/volume1"))
BODYDIR = IMGDIR / "qwen_qwen3-vl-235b-a22b-thinking"
OUT = Path(os.getenv("COLLAPSE_OUT", str(data_path("collapse_v2.jsonl"))))
HOST = os.getenv("OLLAMA_HOST", "192.168.1.169")
PROFILE = Path(__file__).parent / "book_profile.gill.yaml"
BAML_SRC = Path(__file__).resolve().parent.parent.parent / "baml_src" / "gill_apparatus.baml"
LIST = Path(os.getenv("COLLAPSE_LIST", str(data_path("audits", "collapse_pages_census.json"))))


def header(targets):
    try:
        head = subprocess.check_output(["git", "-C", str(Path(__file__).parent), "rev-parse", "HEAD"]).decode().strip()
    except Exception:
        head = "unknown"
    baml = hashlib.sha256(BAML_SRC.read_bytes()).hexdigest()[:16] if BAML_SRC.exists() else "missing"
    prof = hashlib.sha256(PROFILE.read_bytes()).hexdigest()[:16] if PROFILE.exists() else "missing"
    # Machine in the header and in the hash (Chris's ruling, 2026-09-20). `endpoint` meant the API PATH
    # here; it is renamed `api_path` so `endpoint_id`/`endpoint_host` can mean the GPU server unambiguously.
    return build_header(
        host=HOST, model="qwen3.6-16k:35b", profile_path=PROFILE,
        identity_extra={"seam": "baml", "api_path": "/api/chat", "think": False, "baml_sha16": baml},
        extra={"n_targets": len(targets)})


def done_pages():
    if not OUT.exists(): return set()
    d = set()
    for line in OUT.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
            if r.get("kind") != "config_header": d.add(r["page"])
        except Exception: pass
    return d


def main():
    profile = A.load_profile(str(PROFILE))
    targets = json.loads(LIST.read_text(encoding="utf-8"))
    done = done_pages()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fresh = not OUT.exists() or OUT.stat().st_size == 0
    print(f"collapse v2 -> {OUT}\n  {len(targets)} pages ({len(targets)-len(done)} to go), host {HOST}", flush=True)
    with OUT.open("a", encoding="utf-8") as f:
        if fresh:
            f.write(json.dumps(header(targets), ensure_ascii=False) + "\n"); f.flush()
        for i, t in enumerate(targets):
            pg = t["page"]
            if pg in done: continue
            img = IMGDIR / f"page{pg}_image1.png"
            if not img.exists():
                f.write(json.dumps({"page": pg, "status": "NO_IMAGE"}) + "\n"); f.flush(); continue
            body = BODYDIR / f"page{pg}_image1.md"
            t0 = time.perf_counter()
            try:
                r = extract_page(str(img), profile, HOST, body_md=str(body) if body.exists() else None, seam="baml")
                v2 = r.get("n_notes") or 0
                cmp = "match" if v2 == t["det"] else ("over" if v2 > t["det"] else "under")
                rec = {"page": pg, "census_ext": t["ext"], "census_det": t["det"], "v2_n_notes": v2,
                       "compare": cmp, "status": r.get("status"),
                       "note_statuses": [n.get("status") for n in r.get("notes", [])],
                       "marker_leaks": r.get("marker_leaks", 0), "secs": round(time.perf_counter() - t0, 1)}
            except Exception as e:
                rec = {"page": pg, "status": "ERROR", "error": str(e)[:200], "secs": round(time.perf_counter() - t0, 1)}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
            print(f"  p{pg} ext={t['ext']} det={t['det']} v2={rec.get('v2_n_notes')} [{rec.get('compare')}] "
                  f"({i+1}/{len(targets)}) {rec.get('secs')}s", flush=True)
    print("DONE collapse run", flush=True)
    # SUMMARY
    from collections import Counter
    rows = [json.loads(l) for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip()]
    pgs = [r for r in rows if r.get("kind") != "config_header" and "compare" in r]
    cmp = Counter(r["compare"] for r in pgs)
    nstat = Counter(s for r in pgs for s in (r.get("note_statuses") or []))
    print(f"\n--- COMPARE to census prediction (det): {dict(cmp)} of {len(pgs)} pages ---")
    print(f"--- recovered (ext << det, v2 reached det): "
          f"{sum(1 for r in pgs if r['v2_n_notes'] == r['census_det'] and r['census_ext'] < r['census_det'])}")
    print(f"--- per-NOTE status: {dict(nstat)}")


if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    main()
