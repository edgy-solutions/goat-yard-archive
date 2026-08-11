"""box_sanity — the geometry gate between any box-producer (Tesseract locator, future CV superscript
detector, alignment layer) and its consumers. Boxes were the one intermediate the old pipeline consumed
UNVALIDATED; nonsensical boxes (cross the gutter into the other column, bleed into footnotes/title, a
few chars wide) are the SYMPTOM of the alignment layer deriving geometry from wrong correspondences
(see cross-modal-correspondence law). The new pipeline computes page geometry (gutter, rule) BEFORE any
box is consumed, so a box can be checked against the page's structure and DISPOSITIONED deterministically:
  clip   — slightly over a boundary  -> trim to its region
  reject — nonsensical (straddles a region boundary, or a few-char fragment) -> drop (let the VLM read
           the image unaided there rather than feed it garbage)
  flag   — many bad boxes on one page -> the page geometry is suspect -> route to reroute/review
Never consumed raw. Born-tested; validated against the vol1 run's per-page geometry.
"""
GEOM_KEYS = ("W", "H", "gutter", "rule_y", "title_frac")   # title_frac default 0.03 (FOSSIL header band)

def regions(geom):
    """Named regions from page geometry. footnote = below the rule; title = top band; body-L/R split
    at the (footnote) gutter."""
    W, H = geom["W"], geom["H"]; g = geom["gutter"]; r = geom.get("rule_y") or H
    t = int(H * geom.get("title_frac", 0.03))
    return {"title": (0, 0, W, t), "body-left": (0, t, g, r), "body-right": (g, t, W, r),
            "footnote": (0, r, W, H)}

def _straddles(box, geom, tol):
    x0, y0, x1, y1 = box; g = geom["gutter"]; r = geom.get("rule_y") or geom["H"]
    if x0 < g - tol and x1 > g + tol: return "gutter"        # crosses the column gutter
    if y0 < r - tol and y1 > r + tol: return "rule"          # crosses body/footnote rule
    t = int(geom["H"] * geom.get("title_frac", 0.03))
    if y0 < t - tol and y1 > t + tol: return "title"         # crosses into the title band
    return None

def home_region(box, geom):
    """The region containing the box's CENTRE (the box's claimed home), ignoring overshoot."""
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    for name, (rx0, ry0, rx1, ry1) in regions(geom).items():
        if rx0 <= cx < rx1 and ry0 <= cy < ry1: return name
    return "outside"

def classify(box, geom):
    """Region name, or 'outside'. (Straddle is a check_box disposition, not a region.)"""
    return home_region(box, geom)

def check_box(box, geom, min_w=None, min_h=8, tol=None):
    """(disposition, region_or_reason): measure how far the box pokes OUTSIDE its home region —
    <=tol clean (ok); <=2*tol small overshoot (clip → trim to region); beyond = straddle (reject).
    Plus a fragment guard (a few-char box = statistical outlier)."""
    tol = tol if tol is not None else max(8, int(geom["W"] * 0.01))
    W = geom["W"]; min_w = min_w if min_w is not None else max(20, int(W * 0.01))
    x0, y0, x1, y1 = box
    if (x1 - x0) < min_w or (y1 - y0) < min_h:
        return "reject", f"fragment({x1-x0}x{y1-y0})"
    home = home_region(box, geom)
    if home == "outside":
        return "reject", "outside-all-regions"
    rx0, ry0, rx1, ry1 = regions(geom)[home]
    overshoot = max(rx0 - x0, x1 - rx1, ry0 - y0, y1 - ry1, 0)   # how far the box exceeds its home region
    if overshoot <= tol: return "ok", home
    if overshoot <= 2 * tol: return "clip", home
    return "reject", f"straddles-{home}"

def check_page(boxes, geom, flag_ratio=0.30):
    """Disposition a page's boxes; if too many are bad, FLAG the page (geometry suspect)."""
    out = [check_box(b, geom) for b in boxes]
    bad = sum(1 for d, _ in out if d != "ok")
    page_flag = len(boxes) > 3 and bad / len(boxes) > flag_ratio
    return {"dispositions": out, "n": len(boxes), "bad": bad,
            "page_flag": page_flag, "reason": "geometry-suspect" if page_flag else None}
