"""Score the alignment gate against the ratified boxes (Chris, 2026-09-20).

    python score_note_align.py [--pages dev|contaminated|both] [--sealed-once] [out.json]

Reads the cached reads from `note_align_reads.jsonl`, classifies with `note_align.classify`, applies the
secondary marker check, and asks the only question that matters: **of the mappings the gate actually
emitted, how many are wrong?** The gate's release condition is ZERO, and the rate of abstention is a cost,
not a failure — a gate that abstains everywhere and is never wrong is a starting point; a gate that maps
everything and is wrong 39% of the time (the count gate, measured) is not.

HOW A MAPPING IS SCORED WRONG. The gate emits `region i -> band-note j`. Truth is the ratified box list.
So region i's TRUE note is the ratified box it corresponds to — and that correspondence has to be clean
before the mapping can be graded at all. Reusing the decomposition's classes:

  region sits on exactly one ratified box (exact / boundary-drift)
        -> correct iff the mapped note index j equals that box's index
  region covers two or more ratified boxes (merged)
        -> any mapping is WRONG: note j is handed a rectangle containing another note
  region covers no ratified box (spurious)
        -> any mapping is WRONG: note j is handed a rectangle with no note in it

UNSCORABLE PAGES ARE NOT SCORED AS PASSES. Mapping correctness compares a band-note INDEX to a ratified box
INDEX, which is only meaningful when the whole-band read found the same number of notes the ratified boxes
record, in the same order. Where it did not, the band read is itself wrong and the page is reported
UNSCORABLE with the reason, never counted as zero-wrong. p261's FINAL list is additionally non-monotone
(its missed-start splits were appended, not inserted), so it is unscorable on ordering regardless of counts.
This is disclosed because it narrows the population the zero-wrong claim covers.

SEALED IS SCORED ONCE. `--sealed-once` is the only way to touch the sealed 14 and it refuses to run unless
the thresholds in note_align.py match the frozen values recorded in the split file.

THE SECONDARY MARKER CHECK IS OFF BY DEFAULT, AND MEASUREMENT IS WHY (2026-09-20). Chris ruled it in:
marker sub-crop -> verifier expecting the aligned note's letter, reject demotes to abstain. It is
implemented (`--marker-check` turns it on) and it was run. On dev it rejected **33 of 33** aligned regions
whose expected letter has a confusable competitor, and confirmed none — a 100% reject rate, which carries
no information about any particular crop.

The cause is in the verifier, not in the crops. `_pick_margin` returned **0.29**, which is `grid[-1]` — the
give-up fallback, reached because no margin satisfied its leave-one-run-out criterion on train. Only 9.3%
of the matcher's OWN exemplars clear 0.29 on their OWN true letter. Sweeping the margin against holdout:

    margin   confirmed-wrong   coverage      confusable-pair coverage
    0.00     12                85.7%         76.4%
    0.05      1                50.5%         18.2%
    0.10      0                45.1%          9.1%
    0.25      0                39.6%          0.0%
    0.29      0                39.6%          0.0%

A margin with zero confirmed-wrong does exist (0.10) — so the fallback is an artifact of the calibration
procedure, not proof the matcher is hopeless. But at every SAFE margin the confusable-pair coverage is 9%
falling to 0, and the 40% of overall coverage that survives is the 11 letters that have no competitor and
are therefore confirmed unconditionally. The verifier confirms unconditionally where it cannot be wrong and
rejects unconditionally where it might be. It does not discriminate on the letters it exists for.

So leaving the check ON would delete 71% of the gate's mappings on grounds unrelated to whether they are
right, and the resulting "zero wrong" would be bought by abstention rather than earned. It is off, the
numbers are reported both ways, and the ruling is Chris's to re-make on this evidence."""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from collections import Counter
import numpy as np
from PIL import Image
import assembler as A
import cv_footnote_presplit as ps
import note_align as NA
import note_line_region as NLR
import note_crop as NC
import marker_harvest as MH
import marker_matcher as MM

D = Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1")
READS = D / "note_align_reads.jsonl"
TRUTH = D / "audits" / "note_box_truth_20260906_FINAL.jsonl"
SPLIT = D / "audits" / "ratified_split_20260920.json"
IMG = Path("C:/Users/cnogr/git/dr-voluminous/commentary/volume1")
PROFILE = Path(__file__).parent / "book_profile.gill.yaml"

COVER, MERGE, EXACT = 0.25, 0.50, 0.70      # identical to decompose_geometry.py — same classes, same cuts


def _inter(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def _area(b):
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def geom_truth(rboxes, tboxes):
    """For each detected region: (kind, true_box_index). kind in single / merged / spurious."""
    out = []
    for r in rboxes:
        cov = [(_inter(t, r) / _area(t) if _area(t) else 0.0) for t in tboxes]
        hits = [j for j, c in enumerate(cov) if c >= MERGE]
        inside = max(((_inter(t, r) / _area(r)) if _area(r) else 0.0) for t in tboxes) if tboxes else 0.0
        best = max(range(len(tboxes)), key=lambda j: cov[j]) if tboxes else None
        if len(hits) >= 2:
            out.append(("merged", None))
        elif best is not None and cov[best] >= COVER:
            out.append(("single", best))
        elif inside >= MERGE and best is not None:
            out.append(("single", best))            # region inside one box — a split piece, still one note
        else:
            out.append(("spurious", None))
    return out


def _vec_from_img(im):
    """marker_matcher._vec reads a path; the same normalization from an in-memory crop."""
    a = 255 - np.asarray(im.convert("L"), float)
    if a.max() > a.min():
        a = (a - a.min()) / (a.max() - a.min())
    im2 = Image.fromarray((a * 255).astype("uint8"))
    w, h = im2.size
    s = (MM.N - 4) / max(w, h)
    im2 = im2.resize((max(1, round(w * s)), max(1, round(h * s))))
    canvas = Image.new("L", (MM.N, MM.N), 0)
    canvas.paste(im2, ((MM.N - im2.size[0]) // 2, (MM.N - im2.size[1]) // 2))
    v = np.asarray(canvas, float).ravel()
    n = np.linalg.norm(v)
    return v / n if n else v


MARKER_LOG = []   # ruling 4: per-call (expected letter, confusable set, verdict, computed margin)


def marker_check(strip, region, expected, templates, margin):
    """Secondary check on an ALIGNED note: cut the marker from the region's OWN first line and ask the
    verifier whether it is the aligned note's letter. Returns 'reject' / 'confirm' / 'abstain'.

    ONE-DIRECTIONAL BY DESIGN: only `reject` acts (demote to abstain). `verify()` has no competitor for 11
    of the 24 letters, so for those it compares the score against nothing and confirms unconditionally —
    trusted to REFUSE, never to CONFIRM. A letter outside the confusable sets can therefore never be
    rejected here, and the check is silently inert on it; that is reported, not hidden."""
    if not expected or expected not in MM.CONF:
        return "abstain-no-competitor"
    fs = region["segments"][0]
    fy0, fy1 = fs["lines"][0]
    ink = np.asarray(strip.convert("L")) < NLR.INK
    mb = MH._marker_box(ink[fy0:fy1, fs["ins"]:fs["x1"]])
    if mb is None:
        return "abstain-no-marker"
    mx0, my0, mx1, my1 = mb
    crop = strip.crop((fs["ins"] + mx0, fy0 + my0, fs["ins"] + mx1, fy0 + my1))
    if crop.size[0] < 3 or crop.size[1] < 3:
        return "abstain-tiny"
    ok, _m = MM.verify(_vec_from_img(crop), expected, templates, margin)
    # Ruling 4 (2026-09-20): log the expected letter WITH its computed margin. `expected_letter` was
    # already recorded per row, but the margin was not, so a reject could not be told from a near-miss.
    MARKER_LOG.append({"expected": expected, "confusables": MM.CONF.get(expected, []),
                       "verdict": "confirm" if ok else "reject", "margin": round(float(_m), 4),
                       "threshold": margin})
    return "confirm" if ok else "reject"


def score_page(rec, tboxes, profile, templates, margin, use_marker=False):
    page = rec["page"]
    strip, _info = ps.presplit(str(IMG / f"page{page}_image1.png"), upscale=1)
    regions, _st = NLR.detect_regions(strip, profile)
    rboxes = [NC._seg_box(r["segments"][0]) for r in regions]
    band = rec.get("band_notes") or []
    reads = [{"text": r.get("text"), "status": r.get("status"), "marker_letter": r.get("marker_letter"),
              "n_read": r.get("n_read")} for r in rec["regions"]]
    cls = NA.classify(reads, band)

    ty = [b[1] for b in tboxes]
    reason = None
    if len(band) != len(tboxes):
        reason = f"band read {len(band)} notes, ratified {len(tboxes)}"
    elif ty != sorted(ty):
        # Comparing a band-note INDEX to a ratified box INDEX presumes both are in reading order. Two pages
        # in FINAL are not: p261 (its 2 missed-start splits were appended, not inserted) and p522 (y0 runs
        # 35, 310, 351, 90 — and its boxes also start at negative x). Neither is scorable for mapping and
        # neither is counted as a pass.
        reason = f"ratified list is not in reading order: y0={ty}"
    scorable = reason is None

    gt = geom_truth(rboxes, tboxes) if len(rboxes) == len(cls) else [("spurious", None)] * len(cls)
    rows, demoted = [], 0
    for c in cls:
        i = c["i"]
        row = dict(c)
        row["geom"], row["true_note"] = gt[i] if i < len(gt) else ("spurious", None)
        if c["cls"] == "aligned" and use_marker:
            exp = (band[c["note"]] or {}).get("marker_letter") if c["note"] is not None else None
            mk = marker_check(strip, regions[i], exp, templates, margin) if i < len(regions) else "abstain-tiny"
            row["marker_check"] = mk
            row["expected_letter"] = exp
            if mk == "reject":
                row["cls"], row["note"], row["demoted_from"] = "abstain", None, "aligned"
                demoted += 1
        if row["cls"] == "aligned" and scorable:
            if row["geom"] == "single":
                row["verdict"] = "correct" if row["note"] == row["true_note"] else "wrong-index"
            else:
                row["verdict"] = f"wrong-{row['geom']}"
        elif row["cls"] == "aligned":
            row["verdict"] = "unscorable"
        rows.append(row)

    return {"page": page, "n_regions": len(cls), "n_band": len(band), "n_ratified": len(tboxes),
            "scorable": scorable, "unscorable_reason": reason, "demoted": demoted,
            "classes": dict(Counter(r["cls"] for r in rows)),
            "verdicts": dict(Counter(r["verdict"] for r in rows if "verdict" in r)),
            "empty_self_report": sum(1 for r in rows if r["cls"] == "spurious" and r["empty_self_report"]),
            "rows": rows}


def summarize(rs, label):
    cls, ver = Counter(), Counter()
    nreg = nsp = ndem = 0
    for r in rs:
        cls.update(r["classes"]); ver.update(r["verdicts"])
        nreg += r["n_regions"]; nsp += r["empty_self_report"]; ndem += r["demoted"]
    scor = [r for r in rs if r["scorable"]]
    aligned_scored = sum(v for k, v in ver.items() if k != "unscorable")
    wrong = sum(v for k, v in ver.items() if k.startswith("wrong"))
    print(f"\n=== {label} — {len(rs)} pages, {nreg} regions ({len(scor)} pages scorable for mapping) ===")
    for k in ("aligned", "spurious", "merged", "ambiguous", "abstain"):
        v = cls.get(k, 0)
        print(f"   {k:11} {v:4}  ({100*v/max(1,nreg):5.1f}% of regions)")
    print(f"   demoted by marker check: {ndem}")
    print(f"   spurious regions that self-reported no_footnote_present: {nsp}/{cls.get('spurious',0)}")
    print(f"   --- mappings graded: {aligned_scored} ---")
    for k, v in sorted(ver.items(), key=lambda kv: -kv[1]):
        print(f"   {k:16} {v:4}")
    print(f"   *** WRONG MAPPINGS: {wrong}  (gate: 0) ***")
    for r in rs:
        if not r["scorable"]:
            print(f"   unscorable p{r['page']}: {r['unscorable_reason']}")
    return {"label": label, "pages": len(rs), "regions": nreg, "classes": dict(cls),
            "verdicts": dict(ver), "graded": aligned_scored, "wrong": wrong,
            "demoted": ndem, "empty_self_report": nsp, "scorable_pages": len(scor)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", default="both")
    ap.add_argument("--sealed-once", action="store_true")
    ap.add_argument("--marker-check", action="store_true",
                    help="enable the secondary marker check — measured 33/33 reject on dev, see module docstring")
    ap.add_argument("out", nargs="?")
    args = ap.parse_args()

    split = json.loads(SPLIT.read_text(encoding="utf-8"))
    want = set()
    if args.pages in ("dev", "both"):
        want |= set(split["dev"])
    if args.pages in ("contaminated", "both"):
        want |= set(split["contaminated"])
    if args.sealed_once:
        frozen = (split.get("frozen_thresholds") or {})
        now = {"T_HIGH": NA.T_HIGH, "T_LOW": NA.T_LOW, "T_CONT": NA.T_CONT, "MARGIN": NA.MARGIN}
        if not frozen:
            raise SystemExit("refusing --sealed-once: no frozen_thresholds recorded in the split file")
        if {k: frozen.get(k) for k in now} != now:
            raise SystemExit(f"refusing --sealed-once: thresholds {now} != frozen {frozen}")
        want |= set(split["sealed"])

    profile = A.load_profile(str(PROFILE))
    rows = [json.loads(l) for l in TRUTH.read_text(encoding="utf-8").splitlines() if l.strip()]
    truth = {r["page"]: [n["strip_box"] for n in r["notes"]] for r in rows if r.get("page") is not None}
    ex = MM._load()
    templates, margin = MM._templates(ex), MM._pick_margin(ex)
    if args.marker_check:
        print(f"secondary marker check ON: {len(ex)} exemplars, margin={margin} "
              f"({len(MM.CONF)} of 24 letters have a competitor; the rest cannot be rejected).\n"
              f"  measured 33/33 reject on dev — see the module docstring before trusting a demotion.")
    else:
        print("secondary marker check OFF (default): it rejected 33/33 confusable-letter mappings on dev\n"
              "  at margin 0.29, the give-up fallback. Enable with --marker-check to reproduce.")

    out = []
    for line in READS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec["page"] not in want or rec.get("status") != "ok" or rec["page"] not in truth:
            continue
        out.append(score_page(rec, truth[rec["page"]], profile, templates, margin, args.marker_check))

    dev = summarize([r for r in out if r["page"] in set(split["dev"])], "DEV")
    con = summarize([r for r in out if r["page"] in set(split["contaminated"])], "CONTAMINATED")
    seal = summarize([r for r in out if r["page"] in set(split["sealed"])], "SEALED") if args.sealed_once else None

    print("\n--- per page ---")
    for r in out:
        tag = "DEV" if r["page"] in set(split["dev"]) else ("CON" if r["page"] in set(split["contaminated"]) else "SEAL")
        print(f"  p{r['page']:4} [{tag}] reg={r['n_regions']:2} band={r['n_band']:2} ratified={r['n_ratified']:2} "
              f"{r['classes']} {r['verdicts'] or ''}{'' if r['scorable'] else '  UNSCORABLE'}")

    rep = {"thresholds": {"T_HIGH": NA.T_HIGH, "T_LOW": NA.T_LOW, "T_CONT": NA.T_CONT, "MARGIN": NA.MARGIN},
           "marker_check": "on" if args.marker_check else "disabled-33of33-reject-on-dev",
           "verifier_margin": margin, "marker_log": MARKER_LOG, "dev": dev, "contaminated": con,
           "sealed": seal, "pages": out}
    path = Path(args.out or (D / "audits" / "note_align_score_20260920.json"))
    path.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    sys.exit(main())
