"""Score pipeline output against image-VERIFIED ground truth (ground_truth_vol1.json). Acceptance
regression harness — Chris adjudicated once (by reading scans); those answers are fixtures the
pipeline is scored against automatically, no re-adjudication.

Reports PER DEFECT CLASS (segmentation | transcription | hebrew) so partial page improvements stay
visible in the numbers. Assertions listed in a page's `uncertain` report PENDING, not FAIL.
Strict by design — 1/6 is a floor reading, not a grade; its job is to move monotonically and loudly.

Usage: score_truth.py <results.json>   (list of {page, extracted:[{marker,text}], ...})
"""
import sys, json, re
from pathlib import Path

NIKUD = re.compile(r"[֑-ֽֿׁ-ׇ]")
CLASSES = ["segmentation", "transcription", "hebrew"]

def page_text(rec): return "\n".join(n["text"] for n in rec.get("extracted", []))

def check_class(spec):
    """One page-spec -> list of (class, key, ok, detail). key is used to mark uncertain."""
    return spec  # placeholder; real logic in score()

def score(gt, results):
    by = {str(r["page"]): r for r in results}
    per_page = {}
    class_tally = {c: {"pass": 0, "fail": 0, "pending": 0} for c in CLASSES}
    for page, spec in gt.items():
        if page.startswith("_"): continue
        uncertain = set(spec.get("uncertain", []))
        r = by.get(page); txt = page_text(r) if r else ""
        checks = []   # (class, key, ok, detail)
        seg = spec.get("segmentation", {})
        if "n_notes" in seg:
            got = len(r.get("extracted", [])) if r else 0
            checks.append(("segmentation", "n_notes", got == seg["n_notes"], f'count {got}!={seg["n_notes"]}'))
        for cls in ("transcription", "hebrew"):
            c = spec.get(cls, {})
            for s in c.get("must_contain", []):
                checks.append((cls, "must_contain:" + s, (s in txt) if r else False, f'missing "{s}"'))
            for s in c.get("must_not_contain", []):
                checks.append((cls, "must_not:" + s, (s not in txt) if r else False, f'has "{s}"'))
            if c.get("no_nikud"):
                bad = None
                for s in c.get("must_contain", []):
                    pat = "".join(ch + r"[֑-ׇ]*" for ch in s)
                    m = re.search(pat, txt)
                    if m and NIKUD.search(m.group(0)): bad = m.group(0); break
                checks.append((cls, "no_nikud", bad is None, f'added nikud "{bad}"'))
        page_fail = []
        for cls, key, ok, detail in checks:
            if ok: class_tally[cls]["pass"] += 1
            elif key in uncertain or key.split(":")[0] in uncertain:
                class_tally[cls]["pending"] += 1; page_fail.append(f'PENDING {detail}')
            else:
                class_tally[cls]["fail"] += 1; page_fail.append(detail)
        hard = [d for d in page_fail if not d.startswith("PENDING")]
        per_page[page] = ("PASS" if not hard else "FAIL", page_fail)
    return per_page, class_tally

def main():
    gt = json.loads((Path(__file__).parent / "ground_truth_vol1.json").read_text(encoding="utf-8"))
    results = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    per_page, ct = score(gt, results)
    npass = sum(1 for st, _ in per_page.values() if st == "PASS")
    for page, (st, fails) in sorted(per_page.items()):
        print(f"  p{page}: {st}" + ("" if st == "PASS" else "  " + " · ".join(fails)))
    print(f"\nPAGES: {npass}/{len(per_page)} pass")
    print("PER DEFECT CLASS (checks):")
    for c in CLASSES:
        t = ct[c]; print(f"  {c:14} pass={t['pass']} fail={t['fail']} pending={t['pending']}")
    sys.exit(1 if npass < len(per_page) else 0)

if __name__ == "__main__": main()
