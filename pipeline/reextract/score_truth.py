"""Score pipeline output against the image-VERIFIED ground truth (ground_truth_vol1.json). This is
the acceptance regression harness — Chris adjudicated once (by reading scans); those answers are now
fixtures the pipeline is tested against automatically, no re-adjudication. Grows as pages are verified.

Usage: score_truth.py <results.json>   (results.json = list of {page, extracted:[{marker,text}], ...})
Also usable on a base-only reconstruction of the truth-set run.
"""
import sys, json, re
from pathlib import Path

NIKUD = re.compile(r"[֑-ֽֿׁ-ׇ]")   # Hebrew points/accents (not consonants)

def page_text(rec):
    return "\n".join(n["text"] for n in rec.get("extracted", []))

def score(gt, results):
    by = {str(r["page"]): r for r in results}
    rows = []; npass = nfail = 0
    for page, spec in gt.items():
        if page.startswith("_"): continue
        r = by.get(page)
        if not r: rows.append((page, "MISSING", ["page not in results"])); nfail += 1; continue
        txt = page_text(r); fails = []
        if "n_notes" in spec and len(r.get("extracted", [])) != spec["n_notes"]:
            fails.append(f'note count {len(r.get("extracted",[]))} != {spec["n_notes"]}')
        for s in spec.get("must_contain", []):
            if s not in txt: fails.append(f'missing "{s}"')
        for s in spec.get("must_not_contain", []):
            if s in txt: fails.append(f'contains forbidden "{s}"')
        if spec.get("no_nikud"):
            # only the Hebrew that appears in must_contain spans is asserted unpointed
            for s in spec.get("must_contain", []):
                # find the span in text allowing interleaved nikud, then check none present
                pat = "".join(c + r"[֑-ׇ]*" for c in s)
                m = re.search(pat, txt)
                if m and NIKUD.search(m.group(0)):
                    fails.append(f'added nikud on "{s}" -> "{m.group(0)}"')
        if fails: nfail += 1; rows.append((page, "FAIL", fails))
        else: npass += 1; rows.append((page, "PASS", []))
    return rows, npass, nfail

def main():
    gt = json.loads((Path(__file__).parent / "ground_truth_vol1.json").read_text(encoding="utf-8"))
    results = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    rows, npass, nfail = score(gt, results)
    for page, st, fails in rows:
        print(f"  p{page}: {st}" + ("" if st == "PASS" else "  " + " · ".join(fails)))
    print(f"\n{npass} pass, {nfail} fail  (of {npass+nfail} verified pages)")
    sys.exit(1 if nfail else 0)

if __name__ == "__main__": main()
