"""CV superscript detector CORE (first cut) — the piece cv_anchor_harness was built to validate. Finds
in-text footnote-anchor superscripts in the body-region image by geometry: a superscript is a SMALL,
RAISED connected component — its ink sits in the upper band of its text line and its bottom does NOT
reach the line's baseline (a normal letter's bottom does). Standoff-only: this returns POSITIONS, it
never writes the body.

Coordinate reality: ground_truth() gives char offsets; this gives pixel positions. First-cut validation
is at COUNT level (detected vs known anchors per page) — the cheapest comparable signal. Char-offset
alignment (map each pixel detection to a body position via word boxes / phrase anchors) is the next
stage, before the letter-scope-window score() means anything.

Predict before running: a raised-small heuristic OVER-detects — punctuation tops, accents, worn letters
read as raised marks. Predicted: count within +/-1 of truth on ~50-55% of anchored pages; systematic
over-count (median detected - truth ~ +2..+4).

MEASURED (14 anchored pages, count level) — PREDICTION WRONG BY ~500x, APPROACH REJECTED:
  within +/-1 of truth: 0/14. Detected ~1000-3000 per page vs 1-15 known anchors; median diff +1724.
  Diagnosis (p104, truth=1): 57 lines, 6741 connected components, the raised+small filter accepts 21% of
  ALL components. The geometry cannot separate a superscript from the raised top of any normal letter —
  at a 65px line height a ~30px letter is "small", and "raised above baseline" matches a fifth of all type.
  This is a broken mechanism, not a miscalibration (two knobs won't fix a 500x miss). predict-before-run
  caught it before it ever ran on a barren page — the point of the discipline.
  NEXT APPROACH (resumes after reconciliation): do NOT calibrate this. Get real baselines/boxes — OCR the
  body (glm-ocr / Tesseract with word+char boxes), then a superscript is a char whose OWN baseline sits
  above its line's baseline. Position then maps to a body char offset for free (the coordinate bridge the
  count-level check deferred), and score()'s letter-scope window finally means something. Template-matching
  the specific marker glyphs is the fallback. The detect() below is kept as the recorded dead-end."""
import numpy as np

def _lines(ink, min_frac=0.02):
    """Text-line row bands from the horizontal ink projection."""
    rows = ink.sum(axis=1)
    thr = max(1, rows.max() * min_frac)
    on = rows > thr
    bands, st = [], None
    for i, v in enumerate(on):
        if v and st is None: st = i
        elif not v and st is not None:
            if i - st >= 6: bands.append((st, i))
            st = None
    if st is not None and len(on) - st >= 6: bands.append((st, len(on)))
    return bands

def _components(sub):
    """4-connected components in a binary sub-image -> list of (x0,y0,x1,y1). scipy if present, else BFS."""
    try:
        from scipy import ndimage
        lab, n = ndimage.label(sub)
        boxes = []
        for sl in ndimage.find_objects(lab):
            if sl is None: continue
            ys, xs = sl
            boxes.append((xs.start, ys.start, xs.stop, ys.stop))
        return boxes
    except Exception:
        return _components_bfs(sub)

def _components_bfs(sub):
    H, W = sub.shape
    seen = np.zeros_like(sub, dtype=bool)
    boxes = []
    from collections import deque
    for y in range(H):
        for x in range(W):
            if sub[y, x] and not seen[y, x]:
                q = deque([(y, x)]); seen[y, x] = True
                x0 = x1 = x; y0 = y1 = y
                while q:
                    cy, cx = q.popleft()
                    x0, x1, y0, y1 = min(x0, cx), max(x1, cx), min(y0, cy), max(y1, cy)
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < H and 0 <= nx < W and sub[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True; q.append((ny, nx))
                boxes.append((x0, y0, x1 + 1, y1 + 1))
    return boxes

def detect(body_img, raised_frac=0.45, max_h_frac=0.55, min_area=6):
    """Return superscript detections [{x, y, line, h}] in reading order (top-to-bottom, left-to-right).
    A component is a superscript candidate iff, within its text line: its bottom is ABOVE the line
    baseline by >= raised_frac of the line height (it is raised), and its height <= max_h_frac of the
    line height (it is small). raised_frac/max_h_frac are the two knobs to calibrate against the anchored
    pages."""
    a = np.asarray(body_img.convert("L")) < 128
    dets = []
    for li, (y0, y1) in enumerate(_lines(a)):
        lh = y1 - y0
        if lh < 8: continue
        band = a[y0:y1]
        colmass = band.sum(axis=1)                       # baseline ~ lowest dense row of the line body
        dense = np.where(colmass > colmass.max() * 0.25)[0]
        baseline = (dense[-1] if len(dense) else lh - 1)
        for (cx0, cy0, cx1, cy1) in _components(band):
            h = cy1 - cy0; area = (cx1 - cx0) * h
            if area < min_area or h > max_h_frac * lh:
                continue
            if cy1 <= baseline - raised_frac * lh:       # bottom is raised above the baseline
                dets.append({"x": (cx0 + cx1) // 2, "y": y0 + (cy0 + cy1) // 2, "line": li, "h": h})
    dets.sort(key=lambda d: (d["line"], d["x"]))
    return dets

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent / "scripts"))
    import cv_anchor_harness as H
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    pg = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    d = detect(H.render_body_strip(pg, upscale=1))
    print(f"p{pg}: {len(d)} superscript candidates vs {len(H.ground_truth(pg))} known anchors")
