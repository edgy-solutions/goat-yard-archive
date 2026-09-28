"""Note-region proposals + the stacked-strip → native-page coordinate un-stacking (config-v2 metadata).

cv_footnote_presplit vertically CONCATS the two columns (left strip above right strip, 20px gap) into one
reading-order strip. This module (1) proposes a note-region per detected note-start — the band from start k
to start k+1 — and (2) un-stacks each strip-y back to NATIVE PAGE coordinates, which differ for the left vs
right column (the right column lived at a different x and y on the 3584x5400 page). A region is a LIST of
per-column RECTANGLES in native coords (the standing rule — a note that stitches columns is two rects, never
one spanning box). Proposals carry provenance (proposed-by: detector) for the ratify console; the ratified
set is the truth for the note-start detector AND the first navigation metadata.

THE PASTE-ORIGIN BUG (fixed 2026-09-27, see docs/audits/SPEC_presplit_paste_origins_20260927.md). The old
strip→native map RE-INFERRED each column's paste origin from the strip's own ink (`_column_bands`, a blank-
run finder), then filtered bands to `height > 10` and took `bands[1][0]` as the right column's start. On real
pages that filter routinely lets THREE bands survive — a thin ink sliver at the very top of the left strip
(a rule remnant / the first line's ascenders) clears the `>10` floor — so `bands[1]` was the LEFT column's
text and the true right-column origin was `bands[-1][0]`. Measured on p423/p726 this was a 168-172px error
that happened to read as 0 error only because the right strip's first line starts at its own top on those two
pages — nothing guarantees that.

The fix: `cv_footnote_presplit.presplit` now PERSISTS the exact paste arithmetic it already computed (the
loop's own running `y`, each strip's trimmed size, and the native origin) into `info["bands"]`. Both mapping
functions below PREFER `info["bands"]` — an exact record, never a re-inference — and only fall back to the
old ink-band inference (index bug fixed: `bands[-1]`, not `bands[1]`) for an OLDER `info` that predates this
change, flagging every such rect `"native": False` so nothing silently mis-places a box. A strip point in the
20px gap between persisted bands, past the last band, or whose native x would exceed `info["page"][0]`
belongs nowhere and raises `ValueError` — it is not clamped to a neighbour, which is the silent mis-placement
this work removes (Lane B item 3: 5 of 6 clamped crops and 2 of 2 blank crops in Lane B's audit were
right-column boxes that a clamp had been silently swallowing)."""
import numpy as np
from note_start_detect import page_starts, text_lines, strip_vrules, _left_inset, INK

GAP = 20  # the vertical gap cv_footnote_presplit inserts between stacked column strips


def _column_bands(strip):
    """Recover the y-bands of each stacked column in the concatenated strip by finding the ~20px blank
    separators. Returns [(y0, y1)] top→bottom = [left-column, right-column] for a two-column page.
    This is the LEGACY ink-band INFERENCE — kept only for `info` dicts predating persisted paste origins.
    It is not retired: the `>10` filter is real (see module docstring) and remains a needed step, just no
    longer the primary source of truth."""
    a = np.asarray(strip.convert("L")) < INK
    rowink = a.sum(axis=1)
    bands, y, H = [], 0, a.shape[0]
    while y < H:
        if rowink[y] > 0:
            y0 = y
            blank = 0
            while y < H and (rowink[y] > 0 or blank < GAP - 4):
                blank = blank + 1 if rowink[y] == 0 else 0
                y += 1
            bands.append((y0, y - blank))
        else:
            y += 1
    return bands or [(0, H)]


def column_bands(info, strip=None):
    """Band y-ranges for this strip, in the strip's own (post-upscale) space, so existing band-index logic
    keeps working. Prefers `info["bands"]` (persisted paste origins) when present — `strip` is not even
    needed then. `strip` is required ONLY for the legacy inference path, and its absence there is an error,
    not an empty list (a caller that has no strip and no persisted bands has nothing to compute from)."""
    bands_info = info.get("bands") if info is not None else None
    if bands_info is not None:
        up = info.get("upscale", 1) or 1
        return [(int(round(b["paste"][1] * up)), int(round(b["paste"][1] * up + b["size"][1] * up)))
                for b in bands_info]
    if strip is None:
        raise ValueError("column_bands: info has no persisted 'bands' and no strip was given for the "
                          "legacy inference path")
    return [b for b in _column_bands(strip) if b[1] - b[0] > 10]


def _band_extent(b, up):
    py = b["paste"][1] * up
    sh = b["size"][1] * up
    return py, py + sh


def _raise_no_band(bands, y, up):
    for i in range(len(bands) - 1):
        _, end_i = _band_extent(bands[i], up)
        start_next, _ = _band_extent(bands[i + 1], up)
        if end_i <= y < start_next:
            raise ValueError(f"y={y} falls in the {GAP}px gap between band {i} and band {i + 1}; "
                              f"it belongs to no band and is not clamped to either neighbour")
    start0, _ = _band_extent(bands[0], up)
    if y < start0:
        raise ValueError(f"y={y} is before the first band (band 0 starts at {start0})")
    raise ValueError(f"y={y} is past the last band (band {len(bands) - 1})")


def _check_band_x(b, i, x, up, what):
    """Raise when a strip x lies in the canvas PADDING beside band `b`, which has no native pre-image.

    cv_footnote_presplit pastes every band at canvas x=0 into a canvas as wide as the WIDEST band, so a
    narrower band carries `canvas_w - size[0]` px of white filler to its right. A box detected over that
    filler is not a box on the page at all. The page-width check below catches this only when the
    overshoot happens to cross the page edge, which depends on WHICH column is the narrow one: on p726
    the right band is 336px narrow and the overshoot lands at native 3920 on a 3584px page (loud), while
    on p217 the LEFT band is the narrow one and the same fault lands at native 1959 (silent, well inside
    the page). One mechanism, loud or silent by accident of layout -- so the gate has to be the band's
    own width, which fires either way.

    Measured on all six clamped A1 note boxes (dr-voluminous reextract_vol1/audits/recut_report_20260927.md):
    predicted native x1 from band width + padding reproduces every reported value within the 2px the box
    detector leaves at the canvas edge.
    """
    band_w = (b.get("size") or [None])[0]
    if band_w is None:
        return
    if x / up > band_w:
        raise ValueError(
            f"{what}: strip x={x} is {x / up - band_w:g}px past the right edge of band {i} "
            f"({b.get('col')}, native width {band_w}px at native "
            f"x={b['native'][0]}). The strip canvas is padded to the widest band, so this x falls in "
            f"white filler that has no native pre-image. Not clamped, not mapped.")

CANVAS_EDGE_SLOP_NATIVE_PX = 2


def _clip_band_x(b, i, x0, x1, up, what):
    """Clip a strip x-range to band `b`'s OWN native width, or refuse when there is nothing to clip to.

    -> (x0, x1, flags, overshoot_native_px)

    Ruling (Chris, 2026-09-27), once this gate had found the overruns and Lane B had confirmed them
    independently from the manifest side: "For the six refused boxes, clip to band width and flag
    edge:band-clipped; a note cannot extend past its band." So an x1 out in the canvas filler is cut
    back to the band edge and the rect carries `edge: ["band-clipped"]` plus the overshoot it lost.

    It is NINE boxes, not six. Lane B's manifest sweep (apparatus-next 2576bb4) checked every native
    rect against its own band's x-range and found three more sitting on filler with NO fault recorded
    at all -- file pages 219:n0 (+450px), 293:n0 (+442px), 895:n0 (+300px), every one of them
    LEFT-column, which is precisely the orientation the page-width check below cannot see. Those three
    had been emitting crops the whole time. A fault table is not a census.

    What is still refused is a range with no pre-image to clip TO. A box that STARTS at or past the
    band edge lies wholly in the filler, and clipping it would invent an empty region at the band edge
    where the page has no box at all -- an empty result from a claimed region is an error, not a very
    narrow box.

    The LEFT edge is a different event with a different cause, so it gets its own flag instead of being
    folded into the clip. p217:n2 starts at strip x=-2 (`..._beyond=left2`), which is the box detector's
    slop at the canvas edge -- the same 2px of slack that made the predicted native x1 for all six
    fault cases agree with Lane B's reported values only to within 2px. A small negative x is therefore
    clamped to 0 and flagged `canvas-slop-clamped`; anything deeper is refused, because past the
    measured slop it is not slop at all but a box attributed to the wrong band. That tolerance rests on
    ONE observed negative instance (p217:n2) plus those six right-side agreements -- widen it only on
    new measurements, never to make a page pass.
    """
    band_w = (b.get("size") or [None])[0]
    if band_w is None:
        return x0, x1, [], 0.0
    flags = []
    if x0 < 0:
        if -x0 / up > CANVAS_EDGE_SLOP_NATIVE_PX:
            raise ValueError(
                f"{what}: strip x0={x0} is {-x0 / up:g}px left of band {i} ({b.get('col')}) at native "
                f"x={b['native'][0]}, deeper than the {CANVAS_EDGE_SLOP_NATIVE_PX}px of slop the box "
                f"detector is measured to leave at the canvas edge. That is not edge slop -- the box "
                f"is attributed to the wrong band. Not clamped, not mapped.")
        x0 = 0
        flags.append("canvas-slop-clamped")
    if x0 / up >= band_w:
        raise ValueError(
            f"{what}: strip x0={x0} starts {x0 / up - band_w:g}px past the right edge of band {i} "
            f"({b.get('col')}, native width {band_w}px at native x={b['native'][0]}). The strip canvas "
            f"is padded to the widest band, so this box lies WHOLLY in white filler with no native "
            f"pre-image. There is nothing to clip it to. Not clamped, not mapped.")
    overshoot = 0.0
    if x1 / up > band_w:
        overshoot = x1 / up - band_w
        x1 = band_w * up
        flags.append("band-clipped")
    return x0, x1, flags, overshoot


def strip_to_native(info, x, y):
    """Map ONE strip point to native page coords using presplit's persisted paste origins.

    -> {"x": int, "y": int, "col": str, "band": int}

    `col` here is the NAME ("left" / "right" / "full_width"). In `strip_box_to_native` below, `col` is the
    band INDEX (int). Same spelling, different type, on purpose: the rectangle mapper's int is the
    historical contract its consumers index on.

    Requires `info["bands"]` (there is no legacy fallback here — a single point has no `column_bands` to
    infer from, unlike the rectangle mapper below). A y in the 20px gap between bands, or past the last
    band, raises `ValueError` naming the offending y and the bands either side. A native x past
    `info["page"][0]` likewise raises, naming the computed x and the page width — never clamped."""
    bands = info.get("bands")
    if bands is None:
        raise ValueError("strip_to_native(info, x, y): info has no persisted 'bands' — there is no "
                          "single-point fallback; use strip_box_to_native with column_bands for older info")
    if not bands:
        raise ValueError(f"strip_to_native: info['bands'] is empty (no strip was produced) — y={y} maps "
                          f"to nothing")
    up = info.get("upscale", 1) or 1
    page_w = (info.get("page") or [None, None])[0]
    for i, b in enumerate(bands):
        py, end = _band_extent(b, up)
        if py <= y < end:
            _check_band_x(b, i, x, up, "strip_to_native")
            nx = b["native"][0] + x / up
            ny = b["native"][1] + (y - py) / up
            if page_w is not None and nx > page_w:
                raise ValueError(f"strip_to_native: native x={nx} exceeds page width {page_w} "
                                  f"(band {i}, strip point x={x} y={y})")
            return {"x": int(round(nx)), "y": int(round(ny)), "col": b["col"], "band": i}
    _raise_no_band(bands, y, up)


def strip_box_to_native(strip_box, info, column_bands=None):
    """Un-stack a strip box to NATIVE page rectangles. cv_footnote_presplit pasted the left column strip at
    canvas-y 0 (native origin rule_l+6) and the right column strip at canvas-y = left_height+20 (native
    origin rule_r+6, native x origin = the footnote gutter xg). So a box wholly in one column is ONE native
    rect; a box that straddles the 20px gap (a stitched note) is TWO — never one spanning box. Returns
    [{box:[x0,y0,x1,y1], col, col_name, native}] on the persisted path, where `col` is the BAND INDEX (int,
    the historical contract) and `col_name` is presplit's name for it. `strip_to_native` above returns `col`
    as the NAME instead — the asymmetry is deliberate and load-bearing for back-compat, so check the type,
    not the spelling.

    Prefers `info["bands"]` (persisted paste origins) exactly like `strip_to_native`. Only when `info` has
    no `"bands"` key at all (an older `info`, predating this change) does it fall back to the ink-band
    `column_bands` inference passed in by the caller, and every rect from that fallback path is flagged
    `"native": False` — an inferred position is never returned marked as native.

    An x-range that runs out into the canvas padding beside a narrow band is CLIPPED to that band's own
    width per Chris's ruling of 2026-09-27, and the rect then carries `edge` (a sorted list of
    `"band-clipped"` / `"canvas-slop-clamped"`) and `band_overshoot_px`. Both keys are absent on a rect
    that needed no clipping. See `_clip_band_x` for what is clipped and what is still refused."""
    x0, y0, x1, y1 = strip_box
    bands_info = info.get("bands")
    if bands_info is not None:
        return _box_from_persisted(strip_box, info, bands_info)
    return _box_from_inference(strip_box, info, column_bands)


def _box_from_persisted(strip_box, info, bands_info):
    x0, y0, x1, y1 = strip_box
    up = info.get("upscale", 1) or 1
    page_w = (info.get("page") or [None, None])[0]
    rects = []
    for i, b in enumerate(bands_info):
        py, end = _band_extent(b, up)
        oy0, oy1 = max(y0, py), min(y1, end)
        if oy0 >= oy1:
            continue
        cx0, cx1, edge_flags, overshoot = _clip_band_x(b, i, x0, x1, up, "strip_box_to_native")
        nx0 = b["native"][0] + cx0 / up
        nx1 = b["native"][0] + cx1 / up
        ny0 = b["native"][1] + (oy0 - py) / up
        ny1 = b["native"][1] + (oy1 - py) / up
        if page_w is not None and nx1 > page_w:
            raise ValueError(f"strip_box_to_native: native x1={nx1} exceeds page width {page_w} "
                              f"(band {i}, strip_box {strip_box})")
        # `col` stays the BAND INDEX here, the int this function has always returned, because existing
        # consumers index on it. `col_name` carries the persisted name. Note the deliberate asymmetry
        # with strip_to_native, whose `col` is the NAME: two fields spelled the same with different
        # types is the hazard that produced this whole audit, so both are stated in both docstrings.
        rect = {"box": [int(round(nx0)), int(round(ny0)), int(round(nx1)), int(round(ny1))],
                "col": i, "col_name": b["col"], "native": True}
        if edge_flags:
            # Present ONLY when something was cut, so a consumer filters with
            # `"band-clipped" in r.get("edge", [])` and an untouched rect stays byte-identical to
            # what it was before this gate existed. A list, not a scalar: p217:n2 trips both flags
            # at once, and two causes that share one field cannot be told apart later.
            rect["edge"] = sorted(edge_flags)
            if overshoot:
                rect["band_overshoot_px"] = round(overshoot, 1)
        rects.append(rect)
    if not rects:
        raise ValueError(f"strip_box_to_native: strip_box {strip_box} y-range overlaps no persisted band")
    return rects


def _box_from_inference(strip_box, info, column_bands):
    """The legacy ink-band-inference path, for an `info` predating persisted paste origins. Index bug fixed:
    the right column is the LAST surviving band (`bands[-1]`), not `bands[1]` — on real pages a thin ink
    sliver at the very top of the left strip routinely survives the `>10` filter as an extra band, and
    `bands[1]` was that sliver's neighbour, not the right column. The `>10` filter itself is left exactly as
    it was — the sliver is real ink, and raising the threshold would be a second guess layered on the first.
    Every returned rect is flagged `"native": False`: an inferred position is never returned marked as
    native."""
    x0, y0, x1, y1 = strip_box
    xg = int(info.get("fn_gutter", [x1])[0])
    rl, rr = (info.get("rules") or [None, None] + [None, None])[:2]
    bands = [b for b in (column_bands or []) if b[1] - b[0] > 10]
    if info.get("mode") == "full_width" or len(bands) < 2 or rr is None:
        ry = rl if rl is not None else (rr or 0)
        return [{"box": [x0, ry + 6 + y0, x1, ry + 6 + y1], "col": 0, "native": False}]
    right_start = bands[-1][0]                          # = left_height + 20 (fixed: was bands[1][0])
    rects = []
    if y0 < right_start - GAP:                          # portion in the left column
        ly1 = min(y1, right_start - GAP)
        rects.append({"box": [x0, rl + 6 + y0, min(x1, xg), rl + 6 + ly1], "col": 0, "native": False})
    if y1 > right_start:                                # portion in the right column (stitch tail)
        ry0 = max(y0, right_start)
        rects.append({"box": [xg + x0, rr + 6 + (ry0 - right_start), xg + x1, rr + 6 + (y1 - right_start)],
                      "col": 1, "native": False})
    return rects or [{"box": [x0, (rl or 0) + 6 + y0, x1, (rl or 0) + 6 + y1], "col": 0, "native": False}]


def propose_regions(strip, info=None):
    """Propose a note-region per detected note-start. Returns (regions, meta). Each region: {strip_box:
    [x0,y0,x1,y1], col_index}. meta carries the column bands and native mapping availability."""
    starts = [y for (_x, y) in page_starts(strip)]
    a = strip_vrules(np.asarray(strip.convert("L")) < INK)
    ins = _left_inset(a)
    lines = text_lines(a[:, ins:])
    bottom = {y0: y1 for (y0, y1) in lines}
    cbands = _column_bands(strip)
    regions = []
    ys = sorted(starts)
    for i, y in enumerate(ys):
        nxt = ys[i + 1] if i + 1 < len(ys) else strip.height
        # end at the next start, but not across a column band boundary
        ci = next((k for k, (b0, b1) in enumerate(cbands) if b0 <= y <= b1 + GAP), 0)
        band_end = cbands[ci][1] if ci < len(cbands) else strip.height
        y1 = min(nxt, band_end)
        regions.append({"strip_box": [ins, int(y), strip.width - 2, int(max(y1, bottom.get(y, y + 20)))],
                        "col_index": ci})
    return regions, {"column_bands": cbands, "n_detected": len(regions)}
