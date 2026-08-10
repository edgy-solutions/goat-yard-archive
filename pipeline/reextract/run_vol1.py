"""Full-vol1 INSTRUMENTED dry-run — the first corpus-scale look (the answer to the two-volume dread:
the unknown-unknowns tail surfaces in ONE batch, not one dreaded page at a time). ~870-958 pages
through the CURRENT pipeline (gated recrop on), every assertion armed, accumulating per-page:
status, note count, Hebrew flag, anchor-match summary + fail-loud unanchored counts, recrop
accept/gated stats, presplit mode + footnote-gutter + rule geometry, furniture dropped.

CHECKPOINTED per-page (JSONL append): a crash RESUMES (skips pages already in the file), never
restarts. Re-running when stage-3 changes outputs is free. Summarize with summarize_vol1.py.
Env: OLLAMA_HOST (default .179).
"""
import sys, os, re, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import assembler as A
from extract_apparatus import extract_page

IMGDIR = Path(os.getenv("VOL1_IMG", "c:/Users/cnogr/git/dr-voluminous/commentary/volume1"))
BODYDIR = IMGDIR / "qwen_qwen3-vl-235b-a22b-thinking"
OUT = Path(os.getenv("VOL1_OUT", str(Path(__file__).parent / "vol1_run.jsonl")))
HOST = os.getenv("OLLAMA_HOST", "192.168.1.179")

def done_pages():
    if not OUT.exists(): return set()
    d = set()
    for line in OUT.read_text(encoding="utf-8").splitlines():
        try: d.add(json.loads(line)["page"])
        except Exception: pass
    return d

def main():
    profile = A.load_profile(str(Path(__file__).parent / "book_profile.gill.yaml"))
    imgs = sorted(IMGDIR.glob("page*_image1.png"),
                  key=lambda p: int(re.search(r"page(\d+)", p.name).group(1)))
    done = done_pages()
    print(f"vol1: {len(imgs)} images, {len(done)} already done, {len(imgs)-len(done)} to go", flush=True)
    with OUT.open("a", encoding="utf-8") as f:
        for i, img in enumerate(imgs):
            pg = int(re.search(r"page(\d+)", img.name).group(1))
            if pg in done: continue
            body = str(BODYDIR / f"{img.stem}.md")
            t0 = time.perf_counter()
            try:
                r = extract_page(str(img), profile, HOST, body_md=body if Path(body).exists() else None)
                rc = r.get("recrop_changes", []); m = r.get("anchor_match") or {}
                info = r.get("presplit_info") or {}
                rec = {"page": pg, "status": r["status"], "n_notes": r.get("n_notes"),
                       "hebrew": any(re.search(r"[֐-׿]", n["text"]) for n in r.get("notes", [])),
                       "anchor_status": m.get("status"), "n_anchors": m.get("n_anchors"),
                       "unanchored": len(m.get("unanchored", [])),
                       "recrop_accepted": sum(1 for c in rc if c.get("accepted")),
                       "recrop_gated": sum(1 for c in rc if not c.get("accepted")),
                       "presplit_mode": info.get("mode"), "fn_gutter": info.get("fn_gutter"),
                       "rules": info.get("rules"), "dropped_furniture": len(r.get("dropped_furniture", [])),
                       "secs": round(time.perf_counter() - t0, 1)}
            except Exception as e:
                rec = {"page": pg, "status": "ERROR", "error": str(e)[:200], "secs": round(time.perf_counter() - t0, 1)}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
            if i % 25 == 0:
                print(f"  ...{pg} [{rec['status']}] ({i+1}/{len(imgs)})", flush=True)
    print("DONE vol1 run", flush=True)

if __name__ == "__main__": main()
