"""Gate-nikud AUDIT — the ADR claim needs "the gate never accepted nikud across the CORPUS", not just
27 pages. run_vol1 logged recrop COUNTS, not change-texts, so this re-runs ONLY the recrop-active pages
(from recrop_pages.json) capturing the full recrop_changes, and flags ANY accepted change containing a
Hebrew point. The gate rejects nikud by construction (_gate_accept); this is defense-in-depth empirical
confirmation. Checkpointed/resumable. Endpoint: OLLAMA_HOST is REQUIRED (no default; .179/.188 refused - see endpoint_guard.py)."""
import sys, os, re, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import assembler as A
from extract_apparatus import extract_page
from endpoint_guard import resolve_host, EndpointMissing, EndpointRefused

IMGDIR = Path("c:/Users/cnogr/git/dr-voluminous/commentary/volume1")
D = Path(os.getenv("AUDIT_DIR", str(Path(__file__).parent)))
OUT = D / "recrop_audit.jsonl"
# LAZY, not module-level (born-test test_endpoint_guard.py caught this): loading the page list at import
# made the script die on a missing data file BEFORE the endpoint guard could refuse a reserved host. It
# still exited non-zero, but for the wrong reason - which is a guard that only looks like it fired.
def _pages():
    return json.loads((D / "recrop_pages.json").read_text())
# NO DEFAULT ENDPOINT (Chris's ruling, 2026-09-20). The old default was 192.168.1.179 = endpoint E,
# which gpu-servers.md marks Closed. Resolved in main(), not at import: a guard that raises while the
# module is being imported also breaks `import nikud_audit_run` for anything that only wants done().
NIKUD = re.compile(r"[֑-ׇ]")

def done():
    if not OUT.exists(): return set()
    return {json.loads(l)["page"] for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip()}

def main():
    # Resolve the endpoint before the first page is touched, so a refused run is refused at second zero.
    try:
        host = resolve_host(os.getenv("OLLAMA_HOST"), who="nikud_audit_run")
    except (EndpointMissing, EndpointRefused) as e:
        print("", file=sys.stderr); print(e, file=sys.stderr); print("", file=sys.stderr); return 2
    print(f"endpoint: {host}   (record this with the result - runs from different endpoints are not comparable)", flush=True)
    profile = A.load_profile(str(Path(__file__).parent / "book_profile.gill.yaml"))
    pages = _pages()
    d = done(); todo = [p for p in pages if p not in d]
    print(f"nikud audit: {len(pages)} recrop-active pages, {len(todo)} to go", flush=True)
    violations = 0
    with OUT.open("a", encoding="utf-8") as f:
        for i, pg in enumerate(todo):
            img = IMGDIR / f"page{pg}_image1.png"
            try:
                r = extract_page(str(img), profile, host)
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

if __name__ == "__main__": sys.exit(main() or 0)
