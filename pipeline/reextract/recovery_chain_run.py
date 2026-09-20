"""Re-extract the 6 recovery pages AND their left neighbours, persisting marker_letter per note.

Why the neighbours: the two-sided fill rule (arch addendum 2026-09-20) confirms a wildcard run only when it
is pinned on BOTH sides. A recovery page's wildcard run LEADS the page (p129: ?,?,?,?,?,?,z,a..f), so its
left anchor can only be the previous page's last letter. Without page-1 the fill is one-sided and stays
`proposed` no matter how clean the arithmetic looks.

This exists because collapse_v2.jsonl recorded counts but NOT marker letters, so the earlier chain verdicts
on these pages ("only p660 confirms") cannot be re-derived from disk. Same seam/model as born_test.
"""
import sys, os, re, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import assembler as A
from extract_apparatus import extract_page
from data_config import data_path

RECOVERIES = [129, 146, 163, 236, 393, 660]
PAGES = sorted(set(RECOVERIES) | {p - 1 for p in RECOVERIES})
IMGDIR = Path(os.getenv("VOL1_IMG", "c:/Users/cnogr/git/dr-voluminous/commentary/volume1"))
BODYDIR = IMGDIR / "qwen_qwen3-vl-235b-a22b-thinking"
OUT = Path(os.getenv("REC_OUT", str(data_path("recovery_chain_run.jsonl"))))
HOST = os.getenv("OLLAMA_HOST", "192.168.1.169")
PROFILE = Path(__file__).parent / "book_profile.gill.yaml"


def done_pages():
    if not OUT.exists():
        return set()
    out = set()
    for l in OUT.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(l)
            if "page" in d:
                out.add(d["page"])
        except Exception:
            pass
    return out


def main():
    profile = A.load_profile(str(PROFILE))
    done = done_pages()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    print("recovery+neighbour run -> %s\n  %d pages (%d to go), host %s"
          % (OUT, len(PAGES), len(PAGES) - len(done), HOST), flush=True)
    with OUT.open("a", encoding="utf-8") as f:
        for i, pg in enumerate(PAGES):
            if pg in done:
                continue
            img = IMGDIR / ("page%d_image1.png" % pg)
            if not img.exists():
                f.write(json.dumps({"page": pg, "status": "NO_IMAGE"}) + "\n"); f.flush(); continue
            body = BODYDIR / (img.stem + ".md")
            t0 = time.perf_counter()
            try:
                r = extract_page(str(img), profile, HOST,
                                 body_md=str(body) if body.exists() else None, seam="baml")
                rec = {"page": pg, "role": "recovery" if pg in RECOVERIES else "left-neighbour",
                       "status": r.get("status"), "n_notes": r.get("n_notes"),
                       "notes": [{"marker": n["marker"], "text": n["text"],
                                  "marker_letter": n.get("marker_letter"), "note_status": n.get("status"),
                                  "partial": n.get("partial")} for n in r.get("notes", [])],
                       "hebrew": any(re.search(r"[\u0590-\u05ff]", n["text"]) for n in r.get("notes", [])),
                       "marker_leaks": r.get("marker_leaks", 0), "secs": round(time.perf_counter() - t0, 1)}
            except Exception as e:
                rec = {"page": pg, "status": "ERROR", "error": str(e)[:200],
                       "secs": round(time.perf_counter() - t0, 1)}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
            print("  p%d [%s] notes=%s (%d/%d) %ss"
                  % (pg, rec["status"], rec.get("n_notes"), i + 1, len(PAGES), rec.get("secs")), flush=True)
    print("DONE recovery-chain", flush=True)


if __name__ == "__main__":
    main()
