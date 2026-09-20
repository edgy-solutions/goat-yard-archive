"""Decompose the note-region geometry error against the ratified boxes (Chris, 2026-09-20).

    python decompose_geometry.py [out.json]

The item-6 run reported a single number — 32% box match at IoU>=0.5 — which cannot tell you whether the
detector is finding the wrong NUMBER of notes or the right notes with the wrong EXTENT. Those have
different fixes, so the number is useless until it is decomposed. Chris's ruling: classify per ratified box
and per detected region, report counts.

Runs UNGATED (`detect_regions`) — the count gate is retired, and gating here would hide exactly the pages
whose errors we are trying to classify.

DEV + CONTAMINATED ONLY. Sealed pages are not touched; the split is frozen in
`audits/ratified_split_20260920.json`.

Per RATIFIED box, in priority order:
  missed            no region covers 25% of it
  split             2+ regions each cover >=25% of it (the detector broke one note into several)
  merged            its best region also covers >=50% of another ratified box (several notes in one region)
  exact             best IoU >= 0.7
  boundary-drift    single correspondence, IoU < 0.7 — right note, wrong extent

Per DETECTED region:
  spurious          covers no ratified box by >=25%, and is not >=50% contained in one

`split` and `merged` are counted from the box's point of view and the region's point of view respectively,
so one page's error can appear in both — that is the nature of a many-to-many mismatch and the report says
so rather than forcing a partition."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from collections import Counter
import assembler as A
import cv_footnote_presplit as ps
import note_line_region as NLR
import note_crop as NC

D = Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1")
TRUTH = D / "audits" / "note_box_truth_20260906_FINAL.jsonl"
SPLIT = D / "audits" / "ratified_split_20260920.json"
PROFILE = Path(__file__).parent / "book_profile.gill.yaml"
IMG = Path("C:/Users/cnogr/git/dr-voluminous/commentary/volume1")

COVER, MERGE, EXACT = 0.25, 0.50, 0.70      # fixed here, before the run


def _inter(a, b):
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    return max(0, ix1 - ix0) * max(0, iy1 - iy0)


def _area(b):
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def iou(a, b):
    i = _inter(a, b); u = _area(a) + _area(b) - i
    return i / u if u > 0 else 0.0


def classify_page(page, tboxes, profile):
    strip, info = ps.presplit(str(IMG / f"page{page}_image1.png"), upscale=1)
    regions, stitched = NLR.detect_regions(strip, profile)
    rboxes = [NC._seg_box(r["segments"][0]) if len(r["segments"]) == 1
              else [r["segments"][0]["x0"], r["segments"][0]["lines"][0][0],
                    r["segments"][0]["x1"], r["segments"][-1]["lines"][-1][1]]
              for r in regions]
    # cov_t[j][i] = fraction of ratified box j covered by region i; cov_r[i][j] = fraction of region i in box j
    cov_t = [[(_inter(t, r) / _area(t) if _area(t) else 0.0) for r in rboxes] for t in tboxes]
    cov_r = [[(_inter(t, r) / _area(r) if _area(r) else 0.0) for t in tboxes] for r in rboxes]

    box_cls, box_rows = [], []
    for j, t in enumerate(tboxes):
        covs = cov_t[j]
        hits = [i for i, c in enumerate(covs) if c >= COVER]
        best_i = max(range(len(rboxes)), key=lambda i: covs[i]) if rboxes else None
        bi = iou(t, rboxes[best_i]) if best_i is not None else 0.0
        if not hits:
            c = "missed"
        elif len(hits) >= 2:
            c = "split"
        elif any(k != j and cov_t[k][best_i] >= MERGE for k in range(len(tboxes))):
            c = "merged"
        elif bi >= EXACT:
            c = "exact"
        else:
            c = "boundary-drift"
        box_cls.append(c)
        box_rows.append({"j": j, "cls": c, "best_i": best_i, "iou": round(bi, 3),
                         "n_regions_covering": len(hits)})

    spurious = []
    for i, r in enumerate(rboxes):
        if max(cov_t[j][i] for j in range(len(tboxes))) < COVER and max(cov_r[i]) < MERGE:
            spurious.append(i)

    return {"page": page, "n_ratified": len(tboxes), "n_regions": len(rboxes), "stitched": stitched,
            "count_equal": len(rboxes) == len(tboxes),
            "box_classes": dict(Counter(box_cls)), "boxes": box_rows,
            "spurious_regions": spurious, "n_spurious": len(spurious)}


def main(out=None):
    profile = A.load_profile(str(PROFILE))
    split = json.loads(SPLIT.read_text(encoding="utf-8"))
    allow = set(split["dev"]) | set(split["contaminated"])
    rows = [json.loads(l) for l in TRUTH.read_text(encoding="utf-8").splitlines() if l.strip()]
    truth = {r["page"]: [n["strip_box"] for n in r["notes"]] for r in rows if r.get("page") is not None}

    out_rows = []
    for page in sorted(allow):
        if page not in truth:
            continue
        try:
            out_rows.append(classify_page(page, truth[page], profile))
        except Exception as e:
            out_rows.append({"page": page, "error": f"{type(e).__name__}: {e}"[:200]})

    def summarize(pages, label):
        rs = [r for r in out_rows if r["page"] in pages and "error" not in r]
        c = Counter()
        for r in rs:
            c.update(r["box_classes"])
        nb = sum(r["n_ratified"] for r in rs)
        nr = sum(r["n_regions"] for r in rs)
        sp = sum(r["n_spurious"] for r in rs)
        print(f"\n=== {label} — {len(rs)} pages, {nb} ratified boxes, {nr} detected regions ===")
        for k in ("exact", "boundary-drift", "merged", "split", "missed"):
            v = c.get(k, 0)
            print(f"   {k:16} {v:4}  ({100*v/max(1,nb):5.1f}% of ratified boxes)")
        print(f"   {'spurious':16} {sp:4}  ({100*sp/max(1,nr):5.1f}% of detected regions)")
        print(f"   region count == ratified count on {sum(r['count_equal'] for r in rs)}/{len(rs)} pages")
        return {"label": label, "pages": len(rs), "ratified_boxes": nb, "regions": nr,
                "classes": dict(c), "spurious": sp,
                "count_equal_pages": sum(r["count_equal"] for r in rs)}

    dev = summarize(set(split["dev"]), "DEV (14)")
    con = summarize(set(split["contaminated"]), "CONTAMINATED (5)")

    print("\n--- per dev page ---")
    for r in out_rows:
        if r["page"] not in set(split["dev"]) or "error" in r:
            continue
        print(f"  p{r['page']:4} ratified={r['n_ratified']:2} regions={r['n_regions']:2} "
              f"spurious={r['n_spurious']:2} {r['box_classes']}")

    rep = {"thresholds": {"cover": COVER, "merge": MERGE, "exact_iou": EXACT},
           "dev": dev, "contaminated": con, "pages": out_rows}
    if out:
        Path(out).write_text(json.dumps(rep, indent=1), encoding="utf-8")
        print(f"\nwrote {out}")
    return rep


if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    main(sys.argv[1] if len(sys.argv) > 1 else str(D / "audits" / "geometry_decomposition_20260920.json"))
