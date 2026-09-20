"""Born-test: note regions from a presplit strip are FULL-WIDTH. Regression guard for the gutter bug.

    python test_region_fullwidth.py

THE BUG THIS EXISTS FOR (2026-09-20). `note_line_region` called `detect_gutter` and split the stacked strip
in X into "left" and "right" columns. But `cv_footnote_presplit` has ALREADY un-stacked the page's two
apparatus columns into one reading-order strip — left column pasted above right, 20px gap, each at FULL
strip width. In strip space a column is a horizontal y-band and there is no vertical gutter to find, so
`detect_gutter` locked onto a spurious whitespace valley mid-line (961px on p102, 1009 on p138, 1147 on
p168) and cut every text line in half. Count-equality 10.7%, mean IoU 0.115.

The module had never been wired into a caller, so nothing had ever contradicted it. Nothing will again:
this asserts the invariant directly, and against the ratified boxes' own x-extent rather than against a
number I chose. All 227 ratified boxes are `x: 0 -> strip_width - 2`.

DEV PAGES ONLY. Sealed pages are not opened (split frozen in audits/ratified_split_20260920.json); the
invariant is a property of the representation, not of a page, so a dev sample proves it."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import assembler as A
import cv_footnote_presplit as ps
import note_line_region as NLR
import note_crop as NC

D = Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1")
TRUTH = D / "audits" / "note_box_truth_20260906_FINAL.jsonl"
SPLIT = D / "audits" / "ratified_split_20260920.json"
IMG = Path("C:/Users/cnogr/git/dr-voluminous/commentary/volume1")
PROFILE = Path(__file__).parent / "book_profile.gill.yaml"


def main():
    profile = A.load_profile(str(PROFILE))
    split = json.loads(SPLIT.read_text(encoding="utf-8"))
    dev = set(split["dev"])
    rows = [json.loads(l) for l in TRUTH.read_text(encoding="utf-8").splitlines() if l.strip()]
    truth = {r["page"]: r for r in rows if r.get("page") is not None}

    fails, unassertable, checked, nreg = [], [], 0, 0
    print("born-test: note regions are full-width (no X split)\n")
    for page in sorted(p for p in truth if p in dev):
        t = truth[page]
        tb = [n["strip_box"] for n in t["notes"]]
        strip, _info = ps.presplit(str(IMG / f"page{page}_image1.png"), upscale=1)

        if list(strip.size) != list(t["strip_size"]):
            fails.append((page, f"strip {list(strip.size)} != ratified {t['strip_size']} — scale changed"))
            continue

        # what the ratified boxes say the x-extent is — read from truth, not assumed
        tx = sorted({(b[0], b[2]) for b in tb})
        if len(tx) != 1:
            # NOT a code failure — the RATIFIED boxes disagree with each other on this page, so there is no
            # single x-extent to assert against. Same discipline as fixture_assert: a record that cannot
            # state an expectation is reported UNASSERTABLE, never silently passed and never scored as red.
            neg = [t for t in tx if t[0] < 0]
            unassertable.append((page, f"ratified x-extents disagree: {tx}"
                                 + (f"  (and {len(neg)} start at NEGATIVE x — outside the image)" if neg else "")))
            print(f"  p{page:4} strip={strip.width:5}px  UNASSERTABLE — ratified x-extents disagree: {tx}")
            continue
        exp_x0, exp_x1 = tx[0]

        regions, _st = NLR.detect_regions(strip, profile)
        checked += 1
        nreg += len(regions)
        bad = []
        for k, r in enumerate(regions):
            for s in r["segments"]:
                b = NC._seg_box(s)
                if (b[0], b[2]) != (exp_x0, exp_x1):
                    bad.append((k, [b[0], b[2]]))
        # the gutter bug's signature: a detected region whose width is about half the strip
        half = [k for k, xs in bad if (xs[1] - xs[0]) < 0.75 * strip.width]
        if bad:
            fails.append((page, f"{len(bad)} region-segments not at x=({exp_x0},{exp_x1}): {bad[:4]}"
                                + (f"  <-- {len(half)} are HALF-WIDTH: the gutter bug is back" if half else "")))
        print(f"  p{page:4} strip={strip.width:5}px  ratified x=({exp_x0},{exp_x1})  "
              f"regions={len(regions):2}  {'FAIL' if bad else 'ok'}")

    print(f"\n--- {checked} pages, {nreg} regions checked ---")
    if unassertable:
        print(f"UNASSERTABLE on {len(unassertable)} pages (truth-file irregularity, NOT a code failure):")
        for p, why in unassertable:
            print(f"  p{p}: {why}")
        print("  These need a human eye on the ratified boxes, not a change here.")
    if fails:
        print(f"FAIL on {len(fails)} pages:")
        for p, why in fails:
            print(f"  p{p}: {why}")
        print("\nThe strip is ALREADY un-stacked into reading order: a page column is a y-band at full")
        print("width. If regions are narrower than the strip, something is splitting it in X again.")
        return 1
    print("PASS: every region segment spans the full strip width, matching the ratified x-extent.")
    return 0


if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    sys.exit(main())
