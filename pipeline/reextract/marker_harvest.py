"""Marker-exemplar harvest (config-v2, build step before the confusable-margin matcher).

The labels come from ARITHMETIC THAT PROVABLY HELD, never a glyph read: a human seed gives note[0]'s letter,
and the letter of note[k] is `run(seed, k+1)[-1]` — strict increment, wrap z->a, skip j/v (marker_alphabet).
The DROP GATE is what keeps the labels honest (Chris, 2026-09-13):

  - drop any run that TOUCHES a page in marker_anomalies_observed — a compositor skip (p635 no-y) or a symbol
    note (p178 *) makes strict increment mislabel from the slip onward. Anomalies are runtime facts, NOT
    training labels.
  - drop any run that touches a census BREAK — where the detector and extractor counts disagree, the per-page
    note count is untrustworthy, so the index that propagation rides is untrustworthy.
  - the seed console already anchors note[0] on the detector's start[0] (same page_starts call the harvest
    walks), so seed-index == harvest-index BY CONSTRUCTION — the crop the human read and the crop we label are
    the same note. If that ever drifts, every label shifts by one; the console fix is what prevents it.

Same gate, both jobs: the sequence check that protects the runtime protects the training set. Output: one tight
marker-glyph PNG per note plus a manifest row {page, k, letter, series_pos, crop}. DATA -> private repo."""
import base64, io, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import numpy as np
import cv_footnote_presplit as ps
import note_start_detect as NS
import marker_alphabet as MA

A = Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits")
IMG = Path("C:/Users/cnogr/git/dr-voluminous/commentary/volume1")
OUT = Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/marker_exemplars")
SEEDS = A / "marker_seeds_human_20260913_FINAL.jsonl"


def _marker_box(band, raised_frac=0.25, min_marker_w=7, marker_max_w=42, pad=2):
    """Tight bbox (x0,y0,x1,y1) of the raised marker glyph in a note's FIRST-LINE ink band. The marker is a
    SUPERSCRIPT — it floats above the text baseline — and that is what tells it from the two impostors the second
    stacked column throws up: a residual left-border fragment (strip_vrules leaves the sub-60px remnants of its
    double rule) runs full height and REACHES the baseline; a word-initial capital (the 'M' of 'M...') sits ON
    the baseline. Only the marker floats. So: scan raised, marker-width islands left→right and take the first one
    whose columns are BLANK at the text baseline (floating). Rule remnants and body capitals both reach the
    baseline and are skipped; a too-narrow remnant is also filtered by width. None if none (the note is dropped,
    never cropped blind)."""
    baseline, xh = NS._line_geom(band)
    cut = int(baseline - raised_frac * xh)
    if cut <= 0:
        return None
    H = band.shape[0]
    rcol = band[:cut].any(axis=0)                       # raised-ink columns (marker + any ascenders)
    lo, hi = max(0, baseline - 1), min(H, baseline + 3)  # the text-baseline rows
    W = len(rcol); x = 0
    while x < W:
        while x < W and not rcol[x]:
            x += 1
        if x >= W:
            return None
        e = x
        while e < W and rcol[e]:
            e += 1
        if min_marker_w <= (e - x) <= marker_max_w and band[lo:hi, x:e].sum() <= 1:  # marker-width AND floating
            sub = band[:, x:e]
            rows = np.where(sub.any(axis=1))[0]
            if len(rows):
                y0, y1 = int(rows[0]), int(rows[-1] + 1)
                return (max(0, x - pad), max(0, y0 - pad), e + pad, y1 + pad)
        x = e                                            # reaches baseline (rule/capital) or wrong width — skip


def _page_marker_crops(pg):
    """(strip_L_image, [(strip_box, crop_image)]) — one tight marker crop per detected note-start on the page,
    in reading order. Uses the SAME strip_vrules/inset/text_lines pipeline as page_starts, so the k-th crop is
    the k-th start. Missing-marker notes yield no crop (the note is skipped, not cropped blind)."""
    strip, info = ps.presplit(str(IMG / f"page{pg}_image1.png"), upscale=1)
    if strip is None:
        return None, []
    a = NS.strip_vrules(np.asarray(strip.convert("L")) < NS.INK)
    ins = NS._left_inset(a)
    core = a[:, ins:]
    starts = [y for (y0, y1) in NS.text_lines(core) for y in [y0] if NS.line_opens_note(core[y0:y1])]
    starts = NS._dedupe_slivers(starts, 20)
    lines = {y0: y1 for (y0, y1) in NS.text_lines(core)}
    crops = []
    for y0 in starts:
        y1 = lines.get(y0, y0 + 40)
        band = core[y0:y1]
        mb = _marker_box(band)
        if mb is None:
            crops.append((None, None)); continue         # slot preserved so index stays aligned; skipped on save
        mx0, my0, mx1, my1 = mb
        crop = strip.crop((ins + mx0, y0 + my0, ins + mx1, y0 + my1)).convert("L")
        crops.append(([ins + mx0, y0 + my0, ins + mx1, y0 + my1], crop))
    return strip, crops


def _load_drop_pages():
    """Pages that disqualify a run from the harvest: anomaly pages + census breaks."""
    anom = set()
    ap = A / "marker_anomalies_observed.json"
    if ap.exists():
        anom = {p["file_page"] for p in json.loads(ap.read_text(encoding="utf-8")).get("pages", [])}
    breaks = set()
    cp = A / "chain_census.json"
    if cp.exists():
        breaks = {b["page"] for b in json.loads(cp.read_text(encoding="utf-8")).get("breaks", [])}
    return anom, breaks


def harvest():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "crops").mkdir(exist_ok=True)
    seeds = [json.loads(l) for l in SEEDS.read_text(encoding="utf-8").splitlines() if l.strip()]
    anom, breaks = _load_drop_pages()
    manifest, dropped, kept_runs = [], [], 0
    for s in seeds:
        r0, r1 = s["run"]; seed = s["seed_letter"]
        pages = list(range(r0, r1 + 1))
        hit_anom = sorted(p for p in pages if p in anom)
        hit_break = sorted(p for p in pages if p in breaks)
        if hit_anom or hit_break:
            dropped.append(dict(run=s["run"], seed=seed,
                                reason=("anomaly" if hit_anom else "census-break"),
                                anomaly_pages=hit_anom, break_pages=hit_break))
            continue
        # collect every note-start across the run in reading order, then label by strict increment from the seed
        run_crops = []                                   # [(page, strip_box, crop)]
        for pg in pages:
            _strip, crops = _page_marker_crops(pg)
            for sb, cr in crops:
                run_crops.append((pg, sb, cr))
        n = len(run_crops)
        if n == 0:
            dropped.append(dict(run=s["run"], seed=seed, reason="no-detected-starts"))
            continue
        labels = MA.run(seed, n)                          # wrap-aware, j/v-skipping strict sequence
        kept_runs += 1
        k_in_page = {}
        for k, (pg, sb, cr) in enumerate(run_crops):
            letter = labels[k]
            if cr is None:                                # marker island not isolable -> keep the index, skip the file
                manifest.append(dict(run=s["run"], page=pg, k=k, letter=letter, crop=None, skipped="no-marker-island"))
                continue
            idx = k_in_page.get(pg, 0); k_in_page[pg] = idx + 1
            name = f"{letter}_{pg}_{idx}.png"
            cr.save(OUT / "crops" / name)
            manifest.append(dict(run=s["run"], seed=seed, page=pg, k=k, letter=letter,
                                 strip_box=sb, crop=f"crops/{name}"))
    (OUT / "manifest.jsonl").write_text(
        "\n".join(json.dumps(m) for m in manifest) + "\n", encoding="utf-8")
    (OUT / "harvest_report.json").write_text(json.dumps(dict(
        seeds=len(seeds), kept_runs=kept_runs, dropped=dropped,
        exemplars=sum(1 for m in manifest if m.get("crop")),
        by_letter={l: sum(1 for m in manifest if m.get("letter") == l and m.get("crop")) for l in MA.ALPHABET},
    ), indent=1), encoding="utf-8")
    kept = sum(1 for m in manifest if m.get("crop"))
    print(f"HARVEST: {kept} marker exemplars from {kept_runs} runs "
          f"({len(dropped)} runs dropped: {sum(1 for d in dropped if d['reason']=='anomaly')} anomaly, "
          f"{sum(1 for d in dropped if d['reason']=='census-break')} break, "
          f"{sum(1 for d in dropped if d['reason']=='no-detected-starts')} empty)")
    for d in dropped:
        print(f"  drop run {d['run']} seed={d['seed']}: {d['reason']} {d.get('anomaly_pages') or d.get('break_pages') or ''}")
    cov = {l: n for l, n in ((l, sum(1 for m in manifest if m.get('letter')==l and m.get('crop'))) for l in MA.ALPHABET)}
    print("  per-letter:", " ".join(f"{l}:{n}" for l, n in cov.items() if n))
    print(f"  wrote {OUT/'manifest.jsonl'} and {OUT/'harvest_report.json'}")


if __name__ == "__main__":
    harvest()
