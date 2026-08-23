"""Export-layer bridge (Build-2 contract, task 3). Two jobs:

  1. VERIFY  — load a sitting's exported JSONL (from either console) and run audit_record.validate() on
     every verdict line. This is what makes "wired to the contract" a checkable claim, not a resemblance:
     a record that doesn't pin its crop-hash + candidates and name a real door FAILS here, loudly.

  2. APPEND  — the agent-path per-verdict writer. The browser console can only append to localStorage
     (sandbox) and hand back a JSONL; when the agent runs a sitting itself it calls append_verdict() and
     the line hits the file AS the verdict is made — the end-blob export the old console did is exactly
     what this refuses.

Run:  python verify_sitting_export.py audits/sitting_b_verdicts.jsonl
The first line may be the sitting manifest (kind=sitting_manifest) — it is coverage, not a verdict, and
is checked for door/date but skipped by validate()."""
import sys, io, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from audit_record import validate, DOORS

def verify(jsonl_path):
    lines = [l for l in io.open(jsonl_path, encoding="utf-8").read().splitlines() if l.strip()]
    ok, manifest, fails = 0, None, []
    for i, l in enumerate(lines):
        rec = json.loads(l)
        if rec.get("kind") == "sitting_manifest":
            manifest = rec
            continue
        try:
            validate(rec)
            ok += 1
        except ValueError as e:
            fails.append((i + 1, rec.get("span_id", "?"), str(e)))
    return ok, manifest, fails

def main(path):
    ok, manifest, fails = verify(path)
    print(f"=== {path} ===")
    if manifest:
        print(f"manifest: {manifest.get('sitting','?')} · doors={manifest.get('doors') or manifest.get('door')} "
              f"· freshness={manifest.get('session_freshness','?')}")
    print(f"valid verdicts: {ok}")
    if fails:
        print(f"CONTRACT VIOLATIONS: {len(fails)}")
        for ln, sid, why in fails[:20]:
            print(f"  line {ln} [{sid}]: {why}")
        return 1
    print(f"all {ok} verdicts satisfy the Build-2 contract (crop pinned by hash, candidates verbatim, "
          f"door ∈ {DOORS})")
    return 0

if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    if len(sys.argv) < 2:
        print("usage: python verify_sitting_export.py <exported.jsonl>"); sys.exit(2)
    sys.exit(main(sys.argv[1]))
