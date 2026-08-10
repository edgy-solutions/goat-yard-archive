"""Morning deliverable from the vol1 instrumented run — the first corpus-scale look. Reads
vol1_run.jsonl and reports, in the order Chris reads: what flagged, the flag DISTRIBUTION, NOVEL
flag classes not seen in the 27-page set, geometry stats, and a PROPOSED random-unflagged sample for
the eyeball pass (oversampling Hebrew-dense pages, where the invisible-loss class hides)."""
import sys, os, json, argparse
from collections import Counter
from pathlib import Path

# the 27-page set's statuses/flag-shapes, to detect NOVEL classes tonight
SEEN_STATUSES = {"OK", "ANCHOR_FLAGGED", "STITCH_VIOLATION", "no_apparatus", "ERROR"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jsonl"); ap.add_argument("--sample", type=int, default=15)
    a = ap.parse_args()
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    recs = [json.loads(l) for l in Path(a.jsonl).read_text(encoding="utf-8").splitlines() if l.strip()]
    n = len(recs)
    st = Counter(r["status"] for r in recs)
    print(f"=== VOL1 INSTRUMENTED RUN — {n} pages ===")
    print("STATUS DISTRIBUTION:", dict(st))
    errs = [r for r in recs if r["status"] == "ERROR"]
    print(f"\nERRORS (fail-loud stops — diagnose, don't work around): {len(errs)}")
    for r in errs[:15]: print(f"  p{r['page']}: {r.get('error')}")
    # anchor / fail-loud flag census
    flagged = [r for r in recs if r.get("unanchored", 0) > 0]
    tot_unanch = sum(r.get("unanchored", 0) for r in recs)
    print(f"\nANCHOR fail-loud: {len(flagged)} pages with unanchored notes, {tot_unanch} notes total")
    # recrop stats
    acc = sum(r.get("recrop_accepted", 0) for r in recs); gat = sum(r.get("recrop_gated", 0) for r in recs)
    print(f"RECROP: {acc} accepted, {gat} gated-out (gate must never accept nikud — audit separately)")
    # geometry
    modes = Counter(r.get("presplit_mode") for r in recs)
    print(f"PRESPLIT MODE: {dict(modes)}")
    noapp = [r for r in recs if r["status"] == "no_apparatus"]
    print(f"no_apparatus pages: {len(noapp)}")
    # NOVEL classes
    novel = [r for r in recs if r["status"] not in SEEN_STATUSES]
    if novel:
        print(f"\n⚠ NOVEL STATUS CLASSES (not in 27-page set): {Counter(r['status'] for r in novel)}")
    # note-count outliers (very high / zero) — candidate segmentation anomalies
    big = sorted([r for r in recs if (r.get("n_notes") or 0) >= 20], key=lambda r: -(r.get("n_notes") or 0))
    print(f"\nHIGH note-count pages (>=20, candidate over-seg / dense apparatus): {len(big)}")
    for r in big[:8]: print(f"  p{r['page']}: {r['n_notes']} notes [{r['status']}]")
    # proposed random-unflagged eyeball sample, OVERSAMPLING Hebrew-dense (invisible-loss hides there)
    clean = [r for r in recs if r["status"] == "OK" and r.get("unanchored", 0) == 0]
    heb = [r for r in clean if r.get("hebrew")]; nonheb = [r for r in clean if not r.get("hebrew")]
    # deterministic stride sample (no RNG in this env)
    def stride(lst, k):
        if not lst or k <= 0: return []
        s = max(1, len(lst)//k); return [lst[i] for i in range(0, len(lst), s)][:k]
    samp = stride(heb, a.sample*2//3) + stride(nonheb, a.sample//3)
    print(f"\nPROPOSED EYEBALL SAMPLE ({len(samp)} clean pages, ~2/3 Hebrew-dense) — for the acceptance pass:")
    print("  ", [r["page"] for r in samp])
    print("\nMORNING ORDER: what changed (commits) · what flagged (above) · what's blocked on Chris.")

if __name__ == "__main__": main()
