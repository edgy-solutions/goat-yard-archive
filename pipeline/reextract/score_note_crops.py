"""Score the per-note crop path against the 227 RATIFIED note boxes (Chris 2026-09-20).

    python score_note_crops.py [out.json]

THE GATE IS ZERO WRONG note->box MAPPINGS. Abstains are fine. A wrong mapping means note k's region
overlaps ratified box j!=k better than it overlaps box k — i.e. the arithmetic join silently shifted, which
is the compensating-error class count equality cannot see (one missed start + one false start sums right).
Low IoU is a tightness problem and is reported as such; a shifted identity is a correctness failure.

CONTAMINATION IS SPLIT, NOT POOLED. Five of the 33 ratified pages are named in the sources that set the
note-start constants and the abstain branch this path runs on (book_profile.gill.yaml: p138 p226 p261 p393;
hanging_indent.py: p546). They are scored and printed SEPARATELY. See
dr-voluminous/reextract_vol1/audits/pernote_crop_prerun_20260920.md, committed before this file existed,
for the full disclosure and the pre-run predictions this is measured against.

Truth is at presplit upscale=1 (verified: truth strip_size matches presplit(upscale=1).size exactly on
p102/p124/p138/p168). Both sides are therefore in native strip pixels and no rescaling is applied — if that
ever stops holding, every IoU here is meaningless and the assert below fires."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import assembler as A
import note_crop as NC

D = Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1")
TRUTH = D / "audits" / "note_box_truth_20260906_FINAL.jsonl"
ALT = D / "audits" / "note_box_truth_20260906_corrected.jsonl"
PROFILE = Path(__file__).parent / "book_profile.gill.yaml"

# Pages named in the sources that tuned this path. NOT held out. Reported separately, never pooled.
CONTAMINATED = {138, 226, 261, 393, 546}
IOU_PRIMARY, IOU_TIGHT = 0.5, 0.7          # fixed before the run; see the pre-run doc


def iou(a, b):
    ax0, ay0, ax1, ay1 = a; bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    ua = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / ua if ua > 0 else 0.0


def load_truth(path=TRUTH):
    rows = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    return [r for r in rows if r.get("kind") != "note_box_truth_truth" and r.get("page") is not None]


def truth_delta():
    """Which pages/boxes differ between FINAL (227) and corrected (226). Unresolved — reported, not decided."""
    if not ALT.exists():
        return {"alt": "missing"}
    a = {r["page"]: [n["strip_box"] for n in r["notes"]] for r in load_truth(ALT)}
    f = {r["page"]: [n["strip_box"] for n in r["notes"]] for r in load_truth(TRUTH)}
    diff = {p: {"FINAL": f.get(p), "corrected": a.get(p)} for p in sorted(set(a) | set(f))
            if a.get(p) != f.get(p)}
    return {"pages_differing": sorted(diff), "n_pages_differing": len(diff),
            "FINAL_boxes": sum(len(v) for v in f.values()), "corrected_boxes": sum(len(v) for v in a.values()),
            "detail": {str(p): v for p, v in list(diff.items())[:6]}}


def score_page(r, profile):
    """One ratified page. n_notes comes from the RATIFIED count — the truth of how many notes are there.
    Using n_extractor instead would confound a detector miss with an extractor miss."""
    page = r["page"]
    tb = [n["strip_box"] for n in r["notes"]]
    res, strip, _info = NC.page_note_crops(page, len(tb), profile, upscale=1, want_crops=False)
    out = {"page": page, "n_ratified": len(tb), "n_extractor": r.get("n_extractor"),
           "n_detected_old": r.get("n_detected"), "mode": r.get("mode"),
           "contaminated": page in CONTAMINATED, "status": res["status"],
           "n_detected": res.get("n_detected"), "detail": res.get("detail")}
    if strip is not None:
        assert list(strip.size) == list(r["strip_size"]), \
            f"p{page}: strip {list(strip.size)} != truth {r['strip_size']} — scale assumption broken"
    if res["status"] != "ok":
        out["count_equal"] = False
        return out
    out["count_equal"] = True

    # Union box per note in band coords. A stitched note is two rects; IoU against a single ratified
    # strip_box uses the union only when the note is NOT stitched — a stitched note is scored per segment
    # against the ratified box and credited with its best segment, and flagged, because the truth file
    # stores one strip_box per note and cannot express two rects.
    pred = []
    for rec in res["notes"]:
        boxes = [s["strip_box"] for s in rec["segments"]]
        pred.append({"k": rec["k"], "boxes": boxes, "stitched": rec["stitched"],
                     "marker": (rec.get("marker") or {}).get("strip_box"),
                     "marker_status": rec.get("marker_status")})

    rows, wrong = [], 0
    for k, p in enumerate(pred):
        own = max(iou(b, tb[k]) for b in p["boxes"])
        best_j, best = k, own
        for j, t in enumerate(tb):
            v = max(iou(b, t) for b in p["boxes"])
            if v > best:
                best, best_j = v, j
        is_wrong = (best_j != k) and (best > own + 1e-9) and best >= IOU_PRIMARY
        wrong += int(is_wrong)
        rows.append({"k": k, "iou": round(own, 3), "best_j": best_j, "best_iou": round(best, 3),
                     "wrong_mapping": is_wrong, "stitched": p["stitched"],
                     "marker_status": p["marker_status"],
                     "marker_size": ([p["marker"][2] - p["marker"][0], p["marker"][3] - p["marker"][1]]
                                     if p["marker"] else None)})
    out["notes"] = rows
    out["wrong_mappings"] = wrong
    out["match_50"] = sum(1 for x in rows if x["iou"] >= IOU_PRIMARY)
    out["match_70"] = sum(1 for x in rows if x["iou"] >= IOU_TIGHT)
    out["markers_found"] = sum(1 for x in rows if x["marker_status"] == "ok")
    out["mean_iou"] = round(sum(x["iou"] for x in rows) / max(1, len(rows)), 3)
    return out


def summarize(pages, label):
    n = len(pages)
    mapped = [p for p in pages if p.get("count_equal")]
    notes = [x for p in mapped for x in p.get("notes", [])]
    tot_notes = sum(p["n_ratified"] for p in pages)
    return {"label": label, "pages": n, "ratified_notes": tot_notes,
            "count_equal_pages": len(mapped),
            "count_equality_rate": round(len(mapped) / n, 3) if n else None,
            "abstain_rate": round(1 - len(mapped) / n, 3) if n else None,
            "notes_on_mapped_pages": len(notes),
            "match_50": sum(1 for x in notes if x["iou"] >= IOU_PRIMARY),
            "match_70": sum(1 for x in notes if x["iou"] >= IOU_TIGHT),
            "match_rate_50": round(sum(1 for x in notes if x["iou"] >= IOU_PRIMARY) / len(notes), 3) if notes else None,
            "match_rate_70": round(sum(1 for x in notes if x["iou"] >= IOU_TIGHT) / len(notes), 3) if notes else None,
            "mean_iou": round(sum(x["iou"] for x in notes) / len(notes), 3) if notes else None,
            "wrong_mappings": sum(p.get("wrong_mappings", 0) for p in mapped),
            "markers_found": sum(1 for x in notes if x["marker_status"] == "ok"),
            "marker_rate": round(sum(1 for x in notes if x["marker_status"] == "ok") / len(notes), 3) if notes else None}


def main(out_path=None):
    profile = A.load_profile(str(PROFILE))
    truth = load_truth()
    results = []
    for r in truth:
        try:
            results.append(score_page(r, profile))
        except Exception as e:
            results.append({"page": r["page"], "status": "ERROR", "error": f"{type(e).__name__}: {e}"[:300],
                            "contaminated": r["page"] in CONTAMINATED, "count_equal": False,
                            "n_ratified": len(r["notes"])})
    held = [p for p in results if not p["contaminated"]]
    cont = [p for p in results if p["contaminated"]]
    rep = {"iou_primary": IOU_PRIMARY, "iou_tight": IOU_TIGHT,
           "truth_file": TRUTH.name, "upscale": 1,
           "contaminated_pages": sorted(CONTAMINATED),
           "held_out": summarize(held, "HELD-OUT (28 pages)"),
           "contaminated": summarize(cont, "CONTAMINATED (5 pages) — reported separately, never pooled"),
           "truth_delta_FINAL_vs_corrected": truth_delta(),
           "pages": results}

    for s in (rep["held_out"], rep["contaminated"]):
        print(f"\n=== {s['label']} ===")
        print(f"  pages {s['pages']}  ratified notes {s['ratified_notes']}")
        print(f"  count-equality  {s['count_equal_pages']}/{s['pages']}  = {s['count_equality_rate']}"
              f"   (abstain {s['abstain_rate']})")
        print(f"  notes on mapped pages: {s['notes_on_mapped_pages']}")
        print(f"  box match  IoU>={IOU_PRIMARY}: {s['match_50']} ({s['match_rate_50']})"
              f"   IoU>={IOU_TIGHT}: {s['match_70']} ({s['match_rate_70']})   mean IoU {s['mean_iou']}")
        print(f"  marker sub-crop found: {s['markers_found']} ({s['marker_rate']})")
        print(f"  *** WRONG MAPPINGS: {s['wrong_mappings']} ***  (gate: 0)")

    errs = [p for p in results if p.get("status") == "ERROR"]
    if errs:
        print(f"\n  ERRORS on {len(errs)} pages:")
        for p in errs[:8]:
            print(f"    p{p['page']}: {p['error']}")
    td = rep["truth_delta_FINAL_vs_corrected"]
    print(f"\n  truth delta: FINAL {td.get('FINAL_boxes')} boxes vs corrected {td.get('corrected_boxes')}; "
          f"pages differing {td.get('pages_differing')}")

    if out_path:
        Path(out_path).write_text(json.dumps(rep, indent=1), encoding="utf-8")
        print(f"\nwrote {out_path}")
    return rep


if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    main(sys.argv[1] if len(sys.argv) > 1 else str(D / "audits" / "note_crop_score_20260920.json"))
