"""Measure the note-start detector against the ratified truth set, with a TUNE/HOLDOUT split so a score is
never reported on pages a threshold was fit to. The metric that matters is the PRODUCTION one — pages whose
per-column count is EXACTLY right (the gate would map), pages that ABSTAIN (count mismatch — safe/flagged),
and pages with a WRONG count that would have PASSED (FP+FN cancel — the dangerous class) — not F1. Collapse
pages (extractor recorded 1, truth is many) must ABSTAIN against the extractor gate."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from collections import Counter
import numpy as np
import cv_footnote_presplit as ps
import note_start_detect as NS
from note_region import _column_bands

DATA = Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits")
IMG = Path("C:/Users/cnogr/git/dr-voluminous/commentary/volume1")

# HOLD-OUT (never tuned on): full-width singleton 657; dense 226/129; a stitched-candidate; + spread.
HOLDOUT = {657, 226, 129, 362, 912, 206, 423, 543, 897, 522, 565}

def _col_of(y, bands):
    return next((i for i, (b0, b1) in enumerate(bands) if b0 - 25 <= y <= b1 + 25), len(bands) - 1)

def measure(pages, truth, **kw):
    TP = FP = FN = 0
    exact = wrong_pass = abstain = 0
    collapse = {}
    for pg in pages:
        r = truth[pg]
        strip, info = ps.presplit(str(IMG / f"page{pg}_image1.png"), upscale=1)
        bands = [b for b in _column_bands(strip) if b[1] - b[0] > 10] or [(0, strip.height)]
        det = sorted(y for _x, y in NS.page_starts(strip, **kw))
        boxes = sorted(r["notes"], key=lambda n: n["strip_box"][1])
        used = [False] * len(det); tp = 0
        for n in boxes:
            y0, y1 = n["strip_box"][1], n["strip_box"][3]
            m = next((i for i, y in enumerate(det) if not used[i] and y0 - 12 <= y <= y1), None)
            if m is not None: used[m] = True; tp += 1
        fp = used.count(False); fn = len(boxes) - tp
        TP += tp; FP += fp; FN += fn
        ndet = Counter(_col_of(y, bands) for y in det)
        ntru = Counter(_col_of(n["strip_box"][1], bands) for n in boxes)
        counts_match = all(ndet[c] == ntru[c] for c in set(ndet) | set(ntru))
        if not counts_match: abstain += 1
        elif fp == 0 and fn == 0: exact += 1
        else: wrong_pass += 1
        if pg in (129, 393):                                   # gate is detected vs EXTRACTOR count
            collapse[pg] = (len(det) != r["n_extractor"])      # True == correctly abstains (flagged)
    P = TP / (TP + FP) if TP + FP else 0
    R = TP / (TP + FN) if TP + FN else 0
    return dict(n=len(pages), P=P, R=R, TP=TP, FP=FP, FN=FN,
                exact=exact, wrong_pass=wrong_pass, abstain=abstain, collapse=collapse)

def _fmt(name, m):
    print(f"  {name:8} n={m['n']:2}  P={m['P']:.3f} R={m['R']:.3f}  | PRODUCTION: exact={m['exact']} "
          f"abstain={m['abstain']} WRONG-PASS={m['wrong_pass']}  (TP={m['TP']} FP={m['FP']} FN={m['FN']})")
    if m["collapse"]:
        print(f"           collapse flagged (must be True): {m['collapse']}")

if __name__ == "__main__":
    truth = {r["page"]: r for r in (json.loads(l) for l in
             open(DATA / "note_box_truth_20260906_FINAL.jsonl", encoding="utf-8") if l.strip()) if "page" in r}
    allp = sorted(truth)
    tune = [p for p in allp if p not in HOLDOUT]
    hold = [p for p in allp if p in HOLDOUT]
    kw = {}
    if len(sys.argv) > 1:
        kw = json.loads(sys.argv[1])                           # e.g. '{"min_note_h":22}' to try a knob
    print(f"tune={len(tune)} holdout={len(hold)} pages  kw={kw or 'defaults'}")
    _fmt("TUNE", measure(tune, truth, **kw))
    _fmt("HOLDOUT", measure(hold, truth, **kw))
    _fmt("ALL", measure(allp, truth, **kw))
