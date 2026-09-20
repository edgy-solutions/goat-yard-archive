"""Run the alignment gate's reads over the DEV + CONTAMINATED ratified pages. Resumable; writes JSONL.

    python run_note_align.py [--pages dev|contaminated|both]

SEALED PAGES ARE REFUSED BY THIS SCRIPT. The split is frozen in audits/ratified_split_20260920.json and
sealed is scored exactly once, after the gate is frozen — so the runner will not read them even if asked.
That is a guard against me, not against the user.

Two reads per page plus one per region: the whole band (the v2 note sequence) and each detected region on
its own crop. Expensive, so it is cached — classification and threshold changes re-run off this file."""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import assembler as A
import note_align as NA

D = Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1")
SPLIT = D / "audits" / "ratified_split_20260920.json"
OUT = D / "note_align_reads.jsonl"
PROFILE = Path(__file__).parent / "book_profile.gill.yaml"


def done(path):
    if not path.exists():
        return set()
    d = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            d.add(json.loads(line)["page"])
        except Exception:
            pass
    return d


def main(which="both"):
    split = json.loads(SPLIT.read_text(encoding="utf-8"))
    pages = []
    if which in ("dev", "both"):
        pages += split["dev"]
    if which in ("contaminated", "both"):
        pages += split["contaminated"]
    sealed = set(split["sealed"])
    pages = sorted(set(pages) - sealed)
    if sealed & set(pages):
        raise SystemExit("refusing: sealed pages requested")

    profile = A.load_profile(str(PROFILE))
    have = done(OUT)
    todo = [p for p in pages if p not in have]
    print(f"note-align reads -> {OUT}\n  {len(pages)} pages, {len(todo)} to go", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8") as f:
        for i, pg in enumerate(todo):
            t0 = time.perf_counter()
            try:
                rec = NA.read_page(pg, profile)
            except Exception as e:
                rec = {"page": pg, "status": "ERROR", "error": f"{type(e).__name__}: {e}"[:300]}
            rec["total_secs"] = round(time.perf_counter() - t0, 1)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
            print(f"  p{pg} [{rec.get('status')}] regions={rec.get('n_regions')} "
                  f"band_notes={len(rec.get('band_notes') or [])} ({i+1}/{len(todo)}) {rec['total_secs']}s",
                  flush=True)
    print("DONE note-align reads", flush=True)


if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    w = "both"
    if "--pages" in sys.argv:
        w = sys.argv[sys.argv.index("--pages") + 1]
    main(w)
