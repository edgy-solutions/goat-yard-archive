"""Two-model flagging across the corpus — background compute. qwen3.6 vs gemma4 on each apparatus
strip; DISAGREEMENT accumulates into the review queue as DATA (not dispositions). The morning gets the
disagreement DISTRIBUTION — which also converts the escalation tier's intake-population estimate
("tens to low hundreds") into a COUNT. Split across both hosts (--half 0/1, every-other-page) so the
full apparatus set is covered in one night. Checkpointed/resumable.
"""
import sys, os, re, json, time, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import assembler as A
import two_model_flag as TMF

IMGDIR = Path("c:/Users/cnogr/git/dr-voluminous/commentary/volume1")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--census", required=True)     # vol1_run.jsonl (to pick apparatus pages)
    ap.add_argument("--half", type=int, default=0) # 0 or 1 (every-other-page split across hosts)
    ap.add_argument("--out", required=True)
    ap.add_argument("--host", default=os.getenv("OLLAMA_HOST", "192.168.1.179"))
    ap.add_argument("--second", default="gemma4:31b")
    a = ap.parse_args()
    profile = A.load_profile(str(Path(__file__).parent / "book_profile.gill.yaml"))
    profile["transcription"]["recrop_enabled"] = False   # compare BASE reads
    census = [json.loads(l) for l in Path(a.census).read_text(encoding="utf-8").splitlines()]
    apparatus = sorted(x["page"] for x in census if x.get("status") != "no_apparatus")
    mine = apparatus[a.half::2]
    out = Path(a.out); done = set()
    if out.exists():
        done = {json.loads(l)["page"] for l in out.read_text(encoding="utf-8").splitlines() if l.strip()}
    todo = [p for p in mine if p not in done]
    print(f"two-model half{a.half} on {a.host}: {len(mine)} pages, {len(todo)} to go", flush=True)
    with out.open("a", encoding="utf-8") as f:
        for i, pg in enumerate(todo):
            img = IMGDIR / f"page{pg}_image1.png"
            t0 = time.perf_counter()
            try:
                r = TMF.compare_page(str(img), profile, a.host, second_model=a.second)
                rec = {"page": pg, "status": r["status"], "n_primary": r.get("n_primary"),
                       "n_second": r.get("n_second"), "n_flags": len(r.get("flags", [])),
                       "flags": r.get("flags", []), "secs": round(time.perf_counter() - t0, 1)}
            except Exception as e:
                rec = {"page": pg, "status": "ERROR", "error": str(e)[:150]}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
            if i % 20 == 0: print(f"  ...{pg} ({i+1}/{len(todo)})", flush=True)
    print("DONE two-model half", a.half, flush=True)

if __name__ == "__main__": main()
