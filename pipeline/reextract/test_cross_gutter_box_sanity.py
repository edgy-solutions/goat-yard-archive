"""test_cross_gutter_box_sanity — Chris's GO condition 2: a NAMED cross-gutter test wired to
box_sanity on file 90, 403, and the one unequal-column page (745; amendment point D).

Runs the real pipeline (read off, witness on) over real pages 90/403/745 -- private data. If that
data (geometry record, page PNG, or witness .md) is missing for ANY of the three pages, this
prints "NOT RUN: data missing" and exits 2. It NEVER reports a pass in that case -- a skipped
check is not a passed one.

The amendment's 4 named checks, per page:
  1. Every left/right region rect -> box_sanity.check_box(rect, adapter_geom) == ("ok", "body-left"
     or "body-right"); adapter gutter = the geometry record's xdiv (asserted != W/2 on 745, the
     unequal-column page), rule_y = that column's own rule (or H), title_frac = the MEASURED
     running-head bottom / H.
  2. Every 'full' rect carries full_basis "gutter_ink" or "centred_pair" and box_sanity on the column geometry
     REJECTS it (it straddles the gutter by construction -- box_sanity CAN see what body_regions'
     own xdiv-clipped rects cannot, amendment point C).
  3. Negative control per page: a left rect shifted past xdiv by 2*tol+1, where tol is box_sanity's
     OWN overshoot tolerance (tol = max(8, int(W*0.01)), box_sanity.py:46) -- box_sanity tolerates
     overshoot <= 2*tol as a clip, so this is the minimum shift guaranteed to land in reject.
  4. The per-band gutter-ink check ran on every column band (count asserted > 0 and equal to the
     number of column bands). Its crossings are FLAGS reported here, never asserted on.

Each check is run per page, wrapped so one failing assertion is reported as a FAIL and does not
abort the other checks or pages (a raise in a test file aborts, not fails -- test_verse_regions.py's
pattern, reused here).
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verse_regions as VR
import build_verse_regions as BVR
import box_sanity

PAGES = [90, 403, 745]
GEOMETRY = BVR.DEFAULT_GEOMETRY
VOLUME_DIR = BVR.DEFAULT_VOLUME_DIR
WITNESS_DIR = "C:/Users/cnogr/git/dr-voluminous/commentary/volume1/qwen_qwen3-vl-235b-a22b-thinking"


def _check_data_present():
    missing = []
    if not Path(GEOMETRY).exists():
        missing.append(f"geometry file missing: {GEOMETRY}")
    geom_all = BVR.load_geometry(GEOMETRY) if Path(GEOMETRY).exists() else {}
    for fp in PAGES:
        if fp not in geom_all:
            missing.append(f"page {fp}: no geometry record")
        img = Path(VOLUME_DIR) / f"page{fp}_image1.png"
        if not img.exists():
            missing.append(f"page {fp}: image missing ({img})")
        wit = Path(WITNESS_DIR) / f"page{fp}_image1_normalized.md"
        if not wit.exists():
            missing.append(f"page {fp}: witness missing ({wit})")
    return missing, geom_all


def _build_real_run():
    """Read off, witness on -- the same pipeline build_verse_regions.main() runs, inlined here
    so the test can inspect intermediate structures (s1, candidates) as well as final regions."""
    geom_all = BVR.load_geometry(GEOMETRY)
    geom_by_page = {fp: geom_all[fp] for fp in PAGES}
    gray_by_page = {fp: BVR.load_page_gray(VOLUME_DIR, fp) for fp in PAGES}

    s1_by_page = {}
    for fp in PAGES:
        ink = VR.page_ink(gray_by_page[fp])
        s1_by_page[fp] = VR.analyze_page_s1(ink, geom_by_page[fp])
        geom_by_page[fp]["_s1"] = s1_by_page[fp]

    inset_result, _ = BVR.derive_inset_thr(s1_by_page, min_gap=VR.MIN_GAP_INSET_PX)
    inset_thr = inset_result["value"]

    for fp in PAGES:
        VR.pair_centred_across_gutter(s1_by_page[fp], inset_thr)
    candidates_by_page = {fp: VR.head_candidates(s1_by_page[fp], inset_thr=inset_thr) for fp in PAGES}
    confirmed_by_page, rejected_by_page = {}, {}
    for fp in PAGES:
        confirmed, rejected = VR.confirm_candidates(candidates_by_page[fp], head_reads=None)
        confirmed_by_page[fp] = confirmed
        rejected_by_page[fp] = rejected

    witness_by_page = {fp: BVR.load_witness(WITNESS_DIR, fp) for fp in PAGES}

    page_records_ordered = [{"file_page": fp} for fp in PAGES]
    config = {"test": "test_cross_gutter_box_sanity",
              "full_gap_max_px": VR.FULL_GAP_MAX_PX, "col_gap_min_px": VR.COL_GAP_MIN_PX,
              "inset_thr": inset_thr}
    regions, page_summaries = VR.assemble_regions(
        page_records_ordered, s1_by_page, confirmed_by_page, rejected_by_page,
        witness_by_page, config)
    VR.assert_numbering_invariant(regions)
    VR.check_region_rects(regions, geom_by_page)

    return {
        "geom_by_page": geom_by_page, "gray_by_page": gray_by_page, "s1_by_page": s1_by_page,
        "regions": regions, "page_summaries": page_summaries,
        "inset_thr": inset_thr,
    }


def _running_head_bottom(s1):
    rh = s1.get("running_head")
    return rh["y1"] if rh is not None else None


def check1_left_right_rects_ok(ctx, fp, report):
    geom = ctx["geom_by_page"][fp]
    s1 = ctx["s1_by_page"][fp]
    rh_y = _running_head_bottom(s1)
    W = geom["page"][0]
    xdiv = geom["xdiv"]
    if fp == 745:
        assert xdiv != W / 2, f"page 745: xdiv ({xdiv}) must differ from W/2 ({W/2})"
    rects = [r for region in ctx["regions"] for r in region["rects"]
             if r["file_page"] == fp and r["col"] in ("left", "right")]
    n = 0
    for r in rects:
        adapter = VR.adapter_geom(geom, r["col"], rh_y)
        assert adapter["gutter"] == xdiv
        disp, reason = box_sanity.check_box(r["box"], adapter)
        expected_reason = "body-left" if r["col"] == "left" else "body-right"
        assert (disp, reason) == ("ok", expected_reason), (
            f"rect {r} -> ({disp}, {reason}), expected (ok, {expected_reason})")
        n += 1
    report.append(f"    check1 left/right rects ok: n_checked={n}")
    assert n > 0, f"page {fp}: no left/right rects to check"


def check2_full_rects_rejected(ctx, fp, report):
    geom = ctx["geom_by_page"][fp]
    s1 = ctx["s1_by_page"][fp]
    rh_y = _running_head_bottom(s1)
    rects = [r for region in ctx["regions"] for r in region["rects"]
             if r["file_page"] == fp and r["col"] == "full"]
    n = 0
    for r in rects:
        assert r.get("full_basis") in ("gutter_ink", "centred_pair"),             f"full rect {r} missing full_basis gutter_ink|centred_pair"
        adapter = VR.adapter_geom(geom, "left", rh_y)
        disp, reason = box_sanity.check_box(r["box"], adapter)
        assert disp == "reject", f"full rect {r} -> ({disp}, {reason}), expected reject"
        n += 1
    # A check over zero rects passes on nothing: every S1 full band on this page must lie inside
    # some full rect (derived from S1, not a snapshot count).
    for b in s1.get("full") or []:
        assert any(r["box"][1] <= b["y0"] and b["y1"] <= r["box"][3] for r in rects), (
            f"page {fp}: S1 full band y{b['y0']}-{b['y1']} not inside any full rect")
    report.append(f"    check2 full rects rejected by column geom: n_checked={n}, "
                  f"s1_full_bands={len(s1.get('full') or [])}")


def check3_negative_control(ctx, fp, report):
    geom = ctx["geom_by_page"][fp]
    s1 = ctx["s1_by_page"][fp]
    rh_y = _running_head_bottom(s1)
    left_box = next(r["box"] for r in geom["body_regions"] if r["col"] == "left")
    xdiv = geom["xdiv"]
    W = geom["page"][0]
    x0, y0, x1, y1 = left_box
    # Derived from box_sanity's OWN overshoot tolerance (box_sanity.py:46: tol = max(8, int(W*0.01))),
    # not a hand-picked pixel count -- box_sanity.check_box tolerates overshoot <= 2*tol as a clip,
    # so shift = 2*tol+1 is the minimum shift guaranteed to land in reject.
    tol = max(8, int(W * 0.01))
    shift = 2 * tol + 1
    straddle_box = [x0, y0, min(xdiv + shift, W), y1]
    adapter = VR.adapter_geom(geom, "left", rh_y)
    disp, reason = box_sanity.check_box(straddle_box, adapter)
    assert disp == "reject", f"negative control {straddle_box} -> ({disp}, {reason}), expected reject"
    report.append(f"    check3 negative control (straddle +{shift}px = 2*tol+1, tol={tol}) "
                  f"rejected: ({disp}, {reason})")
    report.append("    box_sanity tolerates overshoot <= 2*tol as clip")


def check4_gutter_ink_ran_on_every_band(ctx, fp, report):
    s1 = ctx["s1_by_page"][fp]
    bands = (s1.get("left") or []) + (s1.get("right") or [])
    n_bands = len(bands)
    n_with_gap = sum(1 for b in bands if b.get("gap_px") is not None)
    assert n_with_gap > 0, f"page {fp}: gutter-ink check produced zero gap_px values"
    assert n_with_gap == n_bands, (
        f"page {fp}: gutter-ink check ran on {n_with_gap}/{n_bands} column bands")
    crossings = ctx["page_summaries"][fp]["gutter_ink_crossing"]
    report.append(f"    check4 gutter-ink check ran on every band: n_bands={n_bands}")
    report.append(f"    gutter_ink_crossing flags (reported, not asserted): {crossings}")


CHECKS = [
    ("check1_left_right_rects_ok", check1_left_right_rects_ok),
    ("check2_full_rects_rejected", check2_full_rects_rejected),
    ("check3_negative_control", check3_negative_control),
    ("check4_gutter_ink_ran_on_every_band", check4_gutter_ink_ran_on_every_band),
]


def main():
    missing, _ = _check_data_present()
    if missing:
        print("NOT RUN: data missing")
        for m in missing:
            print(f"  - {m}")
        return 2

    ctx = _build_real_run()
    print(f"full_gap_max_px={VR.FULL_GAP_MAX_PX}  col_gap_min_px={VR.COL_GAP_MIN_PX}  "
          f"inset_thr={ctx['inset_thr']}")

    p = f = 0
    for fp in PAGES:
        print(f"=== page {fp} ===")
        report = []
        for name, fn in CHECKS:
            try:
                fn(ctx, fp, report)
                for line in report[-10:]:
                    print(line)
                print(f"  PASS {name}")
                p += 1
            except Exception:
                print(f"  FAIL {name}")
                traceback.print_exc()
                f += 1

    print(f"\n{p} passed, {f} failed")
    return 0 if f == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
