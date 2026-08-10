"""Gate-nikud AUDIT — the ADR claim needs "the gate never accepted nikud across the CORPUS", not just
27 pages. run_vol1 logged recrop COUNTS, not change-texts, so this re-runs ONLY the recrop-active pages
(from recrop_pages.json) capturing the full recrop_changes, and flags ANY accepted change containing a
Hebrew point. The gate rejects nikud by construction (_gate_accept); this is defense-in-depth empirical
confirmation. Checkpointed/resumable. Env: OLLAMA_HOST (default .179, free after the vol1 run)."""
import sys, os, re, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import assembler as A
from extract_apparatus import extract_page

IMGDIR = Path("c:/Users/cnogr/git/dr-voluminous/commentary/volume1")
D = Path(os.getenv("AUDIT_DIR", str(Path(__file__).parent)))
PAGES = json.loads((D / "recrop_pages.json").read_text())
OUT = D / "recrop_audit.jsonl"
HOST = os.getenv("OLLAMA_HOST", "192.168.1.179")
NIKUD = re.compile(r"[֑-ׇ]")

def done():
    if not OUT.exists(): return set()
    return {json.loads(l)["page"] for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip()}

def main():
    profile = A.load_profile(str(Path(__file__).parent / "book_profile.gill.yaml"))
    d = done(); todo = [p for p in PAGES if p not in d]
    print(f"nikud audit: {len(PAGES)} recrop-active pages, {len(todo)} to go", flush=True)
    violations = 0
    with OUT.open("a", encoding="utf-8") as f:
        for i, pg in enumerate(todo):
            img = IMGDIR / f"page{pg}_image1.png"
            try:
                r = extract_page(str(img), profile, HOST)
                changes = r.get("recrop_changes", [])
                bad = [c for c in changes if c.get("accepted") and NIKUD.search(c.get("new", ""))]
                violations += len(bad)
                rec = {"page": pg, "changes": [{"old": c["old"], "new": c["new"], "accepted": c.get("accepted")} for c in changes],
                       "NIKUD_VIOLATION": bool(bad)}
                if bad: print(f"  !!! p{pg} GATE FAILURE: accepted nikud {bad}", flush=True)
            except Exception as e:
                rec = {"page": pg, "error": str(e)[:150]}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
            if i % 25 == 0: print(f"  ...{pg} ({i+1}/{len(todo)}) violations-so-far={violations}", flush=True)
    print(f"DONE nikud audit — {violations} gate failures (expect 0)", flush=True)

if __name__ == "__main__": main()
