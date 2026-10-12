"""Verse-box truth console (Lane A2 step 3) -- verdict-only, native-resolution cards for every
verse-region box of the step-2 rerun-3 20-page run, plus the 10 "miss" items (Tesseract "Ver."
heads the layout never made a candidate for), plus one page card per FILE page. A human gives a
VERDICT only -- no box editing -- per memory (approval records are content-addressed): out_dir is
named by set_sha16 so a rebuilt console with different content can never silently inherit old
localStorage verdicts.

Pattern: render_box_ratify.py (cards / localStorage / JSONL export via Blob download) -- but crops
here are saved as separate native-resolution grayscale PNG files (never base64-embedded, never
resized) and every overlay is rendered SERVER-SIDE as an absolutely-positioned div (no jsdom in
this repo, so no box math needs to happen in the browser; the browser only owns verdict state and
export).

NO model/endpoint calls. Reads page PNGs/geometry/run/misses files as plain file I/O -- never
network. Private data (run/misses/geometry/page PNGs) lives under dr-voluminous; this script and
its synthetic test are the only things that land in the repo.

Usage: PYTHONIOENCODING=utf-8 python render_verse_truth.py [--run ...] [--misses ...]
       [--geometry ...] [--volume-dir ...] [--out-root ...] [--force] [--html-only [--console-dir D]]
"""
import argparse
import datetime
import hashlib
import html as html_mod
import io
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verse_regions as VR  # noqa: E402  (bare-name import convention of this tree)
import build_verse_regions as BVR  # noqa: E402  (reuse get_git_head / get_git_dirty / compute_module_sha256)

PAD_PX = 40
REGION_KINDS = ("verse", "chapter_intro", "continuation_unanchored")

DEFAULT_RUN = "C:/Users/cnogr/git/dr-voluminous/body_shadow_vol1/verse_regions/run_step2_rerun3_d_20p_20261004.jsonl"
DEFAULT_MISSES = "C:/Users/cnogr/git/dr-voluminous/body_shadow_vol1/verse_regions/miss_trace_step3_741ffb8.json"
DEFAULT_GEOMETRY = "C:/Users/cnogr/git/dr-voluminous/body_shadow_vol1/geometry/volume1_page_geometry.jsonl"
DEFAULT_VOLUME_DIR = "C:/Users/cnogr/git/dr-voluminous/commentary/volume1"
DEFAULT_OUT_ROOT = "C:/Users/cnogr/git/dr-voluminous/body_shadow_vol1/verse_regions/console_step3"


class RefuseOverwrite(RuntimeError):
    """out_dir already exists and force was not given, or (should be impossible by construction,
    since out_dir IS named by its own set_sha16) exists with a manifest set_sha16 that disagrees
    with the freshly computed one -- that case is refused unconditionally, never forced."""


# ==================================================================================================
# hashing / ids
# ==================================================================================================

def _sha16_json(obj):
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _sha16_bytes(b):
    return hashlib.sha256(b).hexdigest()[:16]


def _safe_id(item_id):
    return item_id.replace(":", "_")


def _esc(v):
    if v is None:
        return "&mdash;"
    return html_mod.escape(str(v))


# ==================================================================================================
# pure geometry helpers (testable without real data)
# ==================================================================================================

def crop_with_clamp(rect, W, H, pad):
    """rect=[x0,y0,x1,y1] page-absolute native px. Returns (box, origin, clamped_edges): box is
    rect expanded by `pad` on every side and CLAMPED to [0,W]x[0,H]; origin is the CLAMPED
    (cx0,cy0) -- every overlay must be derived from THIS, never from rect-pad unclamped (Lane B
    property: 45/74 note crops clamp left; deriving from the unclamped rect shifts the overlay).
    clamped_edges is the subset of ["left","top","right","bottom"] that actually got clamped."""
    x0, y0, x1, y1 = rect
    cx0, cy0, cx1, cy1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    clamped_edges = []
    if cx0 < 0:
        clamped_edges.append("left")
        cx0 = 0
    if cy0 < 0:
        clamped_edges.append("top")
        cy0 = 0
    if cx1 > W:
        clamped_edges.append("right")
        cx1 = W
    if cy1 > H:
        clamped_edges.append("bottom")
        cy1 = H
    return [cx0, cy0, cx1, cy1], (cx0, cy0), clamped_edges


def overlay(box, origin, crop_size):
    """box=[x0,y0,x1,y1] page-absolute -> local box relative to the CLAMPED crop `origin`.
    Raises ValueError if any coordinate falls outside the crop's width/height -- an overlay that
    cannot be drawn inside the crop it is drawn on is a bug, never clipped silently."""
    ox, oy = origin
    cw, ch = crop_size
    local = [box[0] - ox, box[1] - oy, box[2] - ox, box[3] - oy]
    if not (0 <= local[0] <= cw and 0 <= local[1] <= ch and 0 <= local[2] <= cw and 0 <= local[3] <= ch):
        raise ValueError(
            f"overlay out of crop bounds: box={box} origin={origin} crop_size={crop_size} -> local={local}"
        )
    return local


def mechanism_label(mech, inset_px):
    """miss_trace mech code -> the A/B/C console label (spec rule, verbatim): A iff
    mech=="inset_below_thr" and inset_px<0; B iff mech=="inset_below_thr" and inset_px>=0; C iff
    mech=="in_full_band_not_centred". Anything else fails loud -- never guessed."""
    if mech == "inset_below_thr":
        if inset_px is None:
            raise ValueError("mech=inset_below_thr with inset_px=None cannot be classified A/B")
        if inset_px < 0:
            return "A: xdiv left of the printed rule; left-column word end is the band's leftmost ink"
        return "B: small ink fragment between rule and head word"
    if mech == "in_full_band_not_centred":
        return "C: head inside a full-width band"
    raise ValueError(f"unrecognized mech code: {mech!r}")


# ==================================================================================================
# build_items -- pure, no image I/O, no network
# ==================================================================================================

def build_items(run_records, misses):
    """run_records: parsed lines of the run jsonl. misses: the parsed miss_trace dict (or its
    "misses" list directly). Returns item dicts covering region items (every record with
    "rects"), miss items (every misses entry) and page items (one per `kind":"page"` record).
    Raises ValueError on a duplicate item_id or a region record with empty rects -- both signal a
    structural assumption this console depends on broke upstream; never papered over."""
    items = []
    seen = set()
    region_ids_by_fp = {}
    miss_ids_by_fp = {}
    page_fps = []

    for rec in run_records:
        if rec.get("kind") in REGION_KINDS:
            rects = rec.get("rects") or []
            if not rects:
                raise ValueError(
                    f"region record has empty rects: kind={rec.get('kind')} "
                    f"file_page_first={rec.get('file_page_first')}"
                )
            fp = rec["file_page_first"]
            item_id = f"r:{fp}:{rects[0]['col']}:{rects[0]['box'][1]}"
            if item_id in seen:
                raise ValueError(f"duplicate item_id: {item_id}")
            seen.add(item_id)
            item = {
                "item_id": item_id, "item_kind": rec["kind"], "file_page": fp, "rects": rects,
                "head": rec.get("head"), "number_sources": rec.get("number_sources"),
                "verse": rec.get("verse"), "disputed": rec.get("disputed"),
                "disputed_by": rec.get("disputed_by"), "flags": rec.get("flags") or [],
                "witness_pairing": rec.get("witness_pairing"), "witness_sim": rec.get("witness_sim"),
                "numbers_link_status": rec.get("numbers_link_status"),
            }
            items.append(item)
            region_ids_by_fp.setdefault(fp, []).append(item_id)
        elif rec.get("kind") == "page":
            page_fps.append(rec["file_page"])

    miss_list = misses["misses"] if isinstance(misses, dict) else misses
    for m in miss_list:
        fp = m["fp"]
        item_id = f"m:{fp}:{m['word'][1]}"
        if item_id in seen:
            raise ValueError(f"duplicate item_id: {item_id}")
        seen.add(item_id)
        items.append({"item_id": item_id, "item_kind": "miss", "file_page": fp, "miss": m})
        miss_ids_by_fp.setdefault(fp, []).append(item_id)

    for fp in page_fps:
        item_id = f"p:{fp}"
        if item_id in seen:
            raise ValueError(f"duplicate item_id: {item_id}")
        seen.add(item_id)
        items.append({
            "item_id": item_id, "item_kind": "page", "file_page": fp,
            "region_item_ids": sorted(region_ids_by_fp.get(fp, [])),
            "miss_item_ids": sorted(miss_ids_by_fp.get(fp, [])),
        })

    return items


# ==================================================================================================
# content addressing (memory: approval records are content-addressed)
# ==================================================================================================

def item_sha16(item, crop_shas=None):
    crop_shas = crop_shas or []
    kind = item["item_kind"]
    if kind == "page":
        payload = {
            "fp": item["file_page"],
            "item_ids": sorted(item["region_item_ids"] + item["miss_item_ids"]),
        }
    elif kind == "miss":
        payload = {"miss": item["miss"], "crop_sha": crop_shas[0] if crop_shas else None}
    else:
        payload = {
            "kind": kind,
            "rects": [{"file_page": r["file_page"], "col": r["col"], "box": r["box"]} for r in item["rects"]],
            "head_box": (item.get("head") or {}).get("box"),
            "number_sources": item.get("number_sources"),
            "verse": item.get("verse"),
            "disputed": item.get("disputed"),
            "disputed_by": item.get("disputed_by"),
            "flags": item.get("flags"),
            "crop_shas": crop_shas,
        }
    return _sha16_json(payload)


def set_sha16(pairs):
    """pairs: iterable of (item_id, item_sha16). Hash of the sorted [[item_id, item_sha16], ...]
    canonical JSON."""
    return _sha16_json(sorted([list(p) for p in pairs]))


# ==================================================================================================
# image I/O (the only place this module touches page PNGs)
# ==================================================================================================

def _get_page_gray(fp, volume_dir, cache):
    if fp not in cache:
        path = Path(volume_dir) / f"page{fp}_image1.png"
        if not path.exists():
            raise FileNotFoundError(f"page image not found: {path}")
        im = Image.open(path).convert("L")
        cache[fp] = np.asarray(im)
    arr = cache[fp]
    H, W = arr.shape
    return arr, W, H


def _encode_png(arr):
    im = Image.fromarray(arr, mode="L")
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _region_overlays(item, rect, origin, crop_size):
    """Overlay list for one region rect on its (clamped-origin) crop; shared by build() and
    --html-only (which rebuilds overlays from manifest crop metadata without rendering)."""
    fp = rect["file_page"]
    head = item.get("head")
    rect_local = overlay(rect["box"], origin, crop_size)
    ov = [{"kind": "rect", "box": rect_local, "label": f"rect col={rect['col']}", "color": "accent"}]
    if head and head.get("box") and head.get("col") == rect["col"] and head.get("file_page") == fp:
        head_local = overlay(head["box"], origin, crop_size)
        ov.append({"kind": "head", "box": head_local, "label": "head", "color": "head"})
    return ov


def _render_region_crops(item, volume_dir, image_cache):
    crops = []
    overlays_per_crop = []
    head = item.get("head")
    for idx, rect in enumerate(item["rects"]):
        fp = rect["file_page"]
        arr, W, H = _get_page_gray(fp, volume_dir, image_cache)
        box, origin, clamped_edges = crop_with_clamp(rect["box"], W, H, PAD_PX)
        sub = arr[box[1]:box[3], box[0]:box[2]]
        crop_size = (box[2] - box[0], box[3] - box[1])
        rect_local = overlay(rect["box"], origin, crop_size)
        ink_sub = sub[rect_local[1]:rect_local[3], rect_local[0]:rect_local[2]]
        ink_frac = float(VR.page_ink(ink_sub).mean()) if ink_sub.size else 0.0
        if ink_frac <= 0.0:
            raise ValueError(
                f"region crop has zero ink inside rect (a claimed region is never empty): "
                f"item={item['item_id']} rect_idx={idx}"
            )
        ov = _region_overlays(item, rect, origin, crop_size)
        png_bytes = _encode_png(sub)
        crops.append({
            "idx": idx, "png_bytes": png_bytes, "crop_sha16": _sha16_bytes(png_bytes),
            "crop_origin": list(origin), "crop_size": list(crop_size),
            "clamped_edges": clamped_edges, "rect": rect["box"], "ink_frac": ink_frac,
            "file_page": fp, "col": rect["col"],
        })
        overlays_per_crop.append(ov)
    return crops, overlays_per_crop


def page_records_by_fp(run_records):
    """{file_page: the run's `page` record} -- carries col_split / col_boxes (fix A)."""
    return {r["file_page"]: r for r in run_records if r.get("kind") == "page" and "file_page" in r}


def _ok_split(page_by_fp, fp):
    """The page record's col_split when its status is ok, else None."""
    cs = ((page_by_fp or {}).get(fp) or {}).get("col_split")
    return cs if cs and cs.get("status") == "ok" else None


def _miss_overlays(item, geometry_by_fp, origin, crop_size, page_by_fp=None):
    """Overlay list for a miss crop; shared by build() and --html-only."""
    m = item["miss"]
    fp = item["file_page"]
    band = m["band"]
    ov = [{"kind": "band", "box": overlay(band, origin, crop_size), "label": "band", "color": "accent"}]
    word_local = overlay(m["word"], origin, crop_size)
    ov.append({"kind": "word", "box": word_local, "label": "tess word", "color": "head"})

    geom = geometry_by_fp.get(fp)
    split = _ok_split(page_by_fp, fp)
    if split is not None:
        y_mid = origin[1] + crop_size[1] / 2
        local_x = round(split["slope"] * y_mid + split["c0"]) - origin[0]
        if 0 <= local_x <= crop_size[0]:
            ov.append({"kind": "vline", "x": local_x, "label": "rule split", "color": "xdiv"})
    else:
        xdiv = geom.get("xdiv") if geom else None
        if xdiv is not None:
            local_x = xdiv - origin[0]
            if 0 <= local_x <= crop_size[0]:
                ov.append({"kind": "vline", "x": local_x, "label": "xdiv (geometry)", "color": "xdiv"})

    inset_px = m.get("inset_px")
    col_left_x = m.get("col_left_x")
    if inset_px is not None and col_left_x is not None:
        line_x_page = band[0] + inset_px + col_left_x
        local_x2 = line_x_page - origin[0]
        if 0 <= local_x2 <= crop_size[0]:
            ov.append({"kind": "vline", "x": local_x2, "label": "measured left ink", "color": "measured"})

    return ov


def _render_miss_crop(item, geometry_by_fp, volume_dir, image_cache, page_by_fp=None):
    m = item["miss"]
    fp = item["file_page"]
    arr, W, H = _get_page_gray(fp, volume_dir, image_cache)
    band = m["band"]
    box, origin, clamped_edges = crop_with_clamp(band, W, H, PAD_PX)
    sub = arr[box[1]:box[3], box[0]:box[2]]
    crop_size = (box[2] - box[0], box[3] - box[1])
    band_local = overlay(band, origin, crop_size)
    ink_sub = sub[band_local[1]:band_local[3], band_local[0]:band_local[2]]
    ink_frac = float(VR.page_ink(ink_sub).mean()) if ink_sub.size else 0.0

    ov = _miss_overlays(item, geometry_by_fp, origin, crop_size, page_by_fp)

    png_bytes = _encode_png(sub)
    crop = {
        "idx": 0, "png_bytes": png_bytes, "crop_sha16": _sha16_bytes(png_bytes),
        "crop_origin": list(origin), "crop_size": list(crop_size),
        "clamped_edges": clamped_edges, "rect": band, "ink_frac": ink_frac,
        "file_page": fp, "col": m.get("col"),
    }
    return crop, ov


# ==================================================================================================
# HTML rendering (overlays are plain server-rendered divs; JS only owns verdict state + export)
# ==================================================================================================

def _page_url(fp, volume_dir):
    fwd = str(Path(volume_dir).resolve()).replace("\\", "/")
    return f"file:///{fwd}/page{fp}_image1.png"


def _crop_html(crop, overlays, rel_path, idx=0):
    w, h = crop["crop_size"]
    divs = []
    for ov in overlays:
        label = _esc(ov["label"])
        color = ov.get("color", "accent")
        cls = "ov" + (f" ov-{color}" if color != "accent" else "")
        if ov["kind"] == "vline":
            cls += " vline"
            divs.append(f'<div class="{cls}" style="left:{ov["x"]}px;height:{h}px" title="{label}"></div>')
        else:
            x0, y0, x1, y1 = ov["box"]
            divs.append(
                f'<div class="{cls}" style="left:{x0}px;top:{y0}px;width:{x1 - x0}px;height:{y1 - y0}px" '
                f'title="{label}"></div>'
            )
    clamp_txt = ",".join(crop["clamped_edges"]) or "none"
    return (
        f'<div class="stage"><div class="stagewrap" style="width:{w}px;height:{h}px">'
        f'<img src="{rel_path}" width="{w}" height="{h}" alt="crop">'
        + "".join(divs)
        + "</div></div>"
        + f'<div class="cropmeta">FILE {crop["file_page"]} col {_esc(crop.get("col"))} '
          f'box {crop["rect"]} clamped_edges {clamp_txt}</div>'
    )


def _verdict_fieldset(item):
    kind = item["item_kind"]
    safe = _safe_id(item["item_id"])
    if kind == "verse":
        opts = ["correct", "box_wrong", "number_wrong", "not_a_verse_head", "unsure"]
        extra = '<input type="text" class="pnumber" placeholder="printed number as seen">'
    elif kind in ("chapter_intro", "continuation_unanchored"):
        opts = ["correct", "box_wrong", "unsure"]
        extra = ""
    elif kind == "miss":
        opts = ["cause_confirmed", "cause_wrong", "not_a_verse_head", "unsure"]
        extra = ""
    else:
        return ""
    radios = "".join(f'<label><input type="radio" name="v_{safe}" value="{o}"> {o}</label>' for o in opts)
    return f'<fieldset class="verdict">{radios}{extra}<textarea class="note" placeholder="note"></textarea></fieldset>'


def _region_card(item, crops, overlays, crop_rel_paths, volume_dir, crop_fn=None, fieldset_fn=None):
    crop_fn = crop_fn or _crop_html
    fieldset_fn = fieldset_fn or _verdict_fieldset
    fp = item["file_page"]
    printed = fp - 88
    ns = item.get("number_sources") or {}
    head = item.get("head") or {}
    hc = head.get("head_confirm") or {}
    verse = item.get("verse")
    disputed = item.get("disputed")
    flags = item.get("flags") or []
    numbers_present = bool(ns.get("read")) or bool(ns.get("witness")) or bool(verse)
    if disputed:
        badge_cls = "bad"
        badge_txt = "ascending: disputed by " + ", ".join(item.get("disputed_by") or [])
    elif not numbers_present:
        badge_cls, badge_txt = "na", "ascending: n/a"
    else:
        badge_cls, badge_txt = "ok", "ascending: ok"

    crops_html = "".join(crop_fn(c, ov, rel, i) for i, (c, ov, rel) in enumerate(zip(crops, overlays, crop_rel_paths)))
    safe = _safe_id(item["item_id"])
    url = _page_url(fp, volume_dir)
    flags_html = "".join(f'<span class="chip">{_esc(fl)}</span>' for fl in flags)
    return f'''<section class="card" id="card_{safe}" data-item-id="{item["item_id"]}">
<header class="cardhead"><span class="iid">{item["item_id"]}</span><span class="kind">{item["item_kind"]}</span>
<span class="pages">FILE {fp} / printed {printed}</span>
<a class="pnglink" target="_blank" href="{url}">open page PNG</a></header>
<div class="row">
<span class="cell">verse <b>{_esc(verse)}</b></span>
<span class="cell">count <b>{_esc(ns.get("count"))}</b></span>
<span class="cell">read <b>{_esc(ns.get("read"))}</b></span>
<span class="cell">witness <b>{_esc(ns.get("witness"))}</b></span>
<span class="cell">pairing <b>{_esc(item.get("witness_pairing"))}</b> sim <b>{_esc(item.get("witness_sim"))}</b></span>
<span class="badge {badge_cls}">{_esc(badge_txt)}</span>
</div>
<div class="chips">{flags_html}</div>
<div class="headtext">head: {_esc(hc.get("text"))}</div>
{crops_html}
{fieldset_fn(item)}
</section>'''


def _miss_card(item, crop, overlays, crop_rel_path, volume_dir, extra_html="", fieldset_fn=None):
    fieldset_fn = fieldset_fn or _verdict_fieldset
    m = item["miss"]
    fp = item["file_page"]
    printed = fp - 88
    label = mechanism_label(m["mech"], m.get("inset_px"))
    safe = _safe_id(item["item_id"])
    url = _page_url(fp, volume_dir)
    crops_html = _crop_html(crop, overlays, crop_rel_path)
    return f'''<section class="card" id="card_{safe}" data-item-id="{item["item_id"]}">
<header class="cardhead"><span class="iid">{item["item_id"]}</span><span class="kind">miss</span>
<span class="pages">FILE {fp} / printed {printed}</span>
<a class="pnglink" target="_blank" href="{url}">open page PNG</a></header>
<div class="row">
<span class="cell">tess text <b>{_esc(m.get("tess"))}</b></span>
<span class="cell">mechanism <b>{_esc(label)}</b></span>
<span class="cell">band inset_px <b>{_esc(m.get("inset_px"))}</b></span>
<span class="cell">word_inset_px <b>{_esc(m.get("word_inset_px"))}</b></span>
<span class="cell">band_h <b>{_esc(m.get("band_h"))}</b></span>
</div>
{crops_html}
{extra_html}
{fieldset_fn(item)}
</section>'''


def _page_card(item, volume_dir):
    fp = item["file_page"]
    printed = fp - 88
    n_regions = len(item["region_item_ids"])
    n_misses = len(item["miss_item_ids"])
    safe = _safe_id(item["item_id"])
    url = _page_url(fp, volume_dir)
    return f'''<section class="card page" id="card_{safe}" data-item-id="{item["item_id"]}">
<header class="cardhead"><span class="iid">{item["item_id"]}</span><span class="kind">page</span>
<span class="pages">FILE {fp} / printed {printed}</span>
<a class="pnglink" target="_blank" href="{url}">open page PNG</a></header>
<div class="row">
<span class="cell">regions on this page <b>{n_regions}</b></span>
<span class="cell">misses on this page <b>{n_misses}</b></span>
</div>
<fieldset class="verdict">
<label>verse heads on this page shown in NO card:
<input type="number" min="0" step="1" class="headsnotshown"></label>
<textarea class="note" placeholder="note"></textarea>
</fieldset>
</section>'''


def _add_region_card(grp, kind, card):
    """Region cards of one FILE page, in reading order. Run order is used except that the page's
    continuation_unanchored region goes FIRST: by the assembler's definition it is the page's text
    before its first head. The step-2 runs appended it after the regions the page had already closed
    (page 90 showed chapter_intro before the top-of-page text; assembler fixed after rerun 3), so
    the console must not trust that record order. At most one per page; a second one raises."""
    if kind == "continuation_unanchored":
        if grp.get("has_continuation"):
            raise ValueError("two continuation_unanchored regions on one page")
        grp["has_continuation"] = True
        grp["region"].insert(0, card)
    else:
        grp["region"].append(card)


def _render_card(item, crops, overlays, crop_rel_paths, volume_dir):
    kind = item["item_kind"]
    if kind in REGION_KINDS:
        return _region_card(item, crops, overlays, crop_rel_paths, volume_dir)
    if kind == "miss":
        return _miss_card(item, crops[0], overlays[0], crop_rel_paths[0], volume_dir)
    if kind == "page":
        return _page_card(item, volume_dir)
    raise ValueError(f"unknown item_kind: {kind}")


_CSS = r"""
:root{--paper:#f6f4ee;--ink:#1a1a1a;--rule:#cbc5b6;--accent:#b5482e;--head:#2f6f9c;--xdiv:#3a6ea5;
--measured:#b7791f;--ok:#2f7d4f;--bad:#9a2b2b;--na:#6b6459;--sans:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);line-height:1.4}
header{position:sticky;top:0;background:#2a2723;color:#f2efe6;padding:10px 16px;display:flex;gap:16px;
align-items:center;z-index:9;border-bottom:2px solid var(--accent)}
header h1{font-size:15px;margin:0;font-weight:600}
header button{margin-left:auto;background:var(--accent);color:#fff;border:0;padding:7px 14px;border-radius:5px;
font-size:13px;cursor:pointer}
.card{max-width:1700px;margin:14px auto;background:#fff;border:1px solid var(--rule);border-radius:7px;
overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.cardhead{display:flex;gap:14px;align-items:baseline;padding:8px 12px;border-bottom:1px solid var(--rule);
flex-wrap:wrap;background:#f1efe6}
.cardhead .iid{font-weight:700;font-size:13px;font-family:ui-monospace,monospace}
.cardhead .kind{font-size:12px;color:#6b6459}
.row{display:flex;gap:14px;align-items:baseline;padding:6px 12px;flex-wrap:wrap}
.cell{font-size:13px}
.badge{font-size:12px;padding:2px 8px;border-radius:10px;border:1px solid var(--rule)}
.badge.ok{background:#e4f3e9;color:var(--ok);border-color:var(--ok)}
.badge.bad{background:#f7e3e1;color:var(--bad);border-color:var(--bad)}
.badge.na{background:#eee;color:var(--na)}
.chips{padding:0 12px 6px}
.chip{font-size:11px;background:#ede8dc;border:1px solid var(--rule);border-radius:3px;padding:1px 6px;
margin-right:4px;color:#7a4a1a}
.headtext{padding:0 12px 8px;font-size:13px;color:#333}
.stage{overflow:auto;max-height:70vh;border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);background:#111}
.stagewrap{position:relative}
.stagewrap img{display:block;image-rendering:pixelated}
.ov{position:absolute;border:2px solid var(--accent);background:rgba(181,72,46,.10);pointer-events:none}
.ov-head{border-color:var(--head);background:rgba(47,111,156,.10)}
.vline{width:0;border-left-style:dashed;border-right:none;top:0;background:none}
.ov-xdiv{border-color:var(--xdiv)}
.ov-measured{border-color:var(--measured)}
.cropmeta{font-size:11px;color:#6b6459;padding:4px 12px;font-family:ui-monospace,monospace}
.verdict{display:flex;gap:10px;align-items:center;padding:8px 12px;border-top:1px solid var(--rule);flex-wrap:wrap}
.verdict label{font-size:12px}
.verdict textarea{flex:1 1 200px;min-height:34px;font-size:12px}
.verdict .pnumber{font-size:12px;padding:3px 6px}
.verdict .headsnotshown{width:80px}
.pnglink{font-size:12px}
"""

_JS = r"""
let state = {};
try { state = JSON.parse(localStorage.getItem(LS_KEY) || "{}"); } catch (e) { state = {}; }
function save() {
  try { localStorage.setItem(LS_KEY, JSON.stringify(state)); } catch (e) {}
  renderStat();
}
function getS(id) { return state[id] || (state[id] = {}); }
function isRated(it) {
  const s = state[it.item_id];
  if (!s) return false;
  if (it.item_kind === "page") return s.heads_not_shown !== undefined && s.heads_not_shown !== "";
  return !!s.verdict;
}
function renderStat() {
  const n = ITEMS.filter(isRated).length;
  document.getElementById("stat").textContent = n + " / " + ITEMS.length + " rated";
}
document.addEventListener("change", function (e) {
  const t = e.target;
  const card = t.closest(".card");
  if (!card) return;
  const id = card.dataset.itemId;
  const s = getS(id);
  if (t.type === "radio") { s.verdict = t.value; }
  save();
});
document.addEventListener("input", function (e) {
  const t = e.target;
  const card = t.closest(".card");
  if (!card) return;
  const id = card.dataset.itemId;
  const s = getS(id);
  if (t.classList.contains("note")) s.note = t.value;
  else if (t.classList.contains("pnumber")) s.printed_number_as_seen = t.value;
  else if (t.classList.contains("headsnotshown")) s.heads_not_shown = t.value;
  save();
});
ITEMS.forEach(function (it) {
  const card = document.getElementById("card_" + it.item_id.split(":").join("_"));
  if (!card) return;
  const s = state[it.item_id];
  if (!s) return;
  if (s.verdict) {
    const r = card.querySelector('input[type=radio][value="' + s.verdict + '"]');
    if (r) r.checked = true;
  }
  if (s.note != null) { const n = card.querySelector(".note"); if (n) n.value = s.note; }
  if (s.printed_number_as_seen != null) { const p = card.querySelector(".pnumber"); if (p) p.value = s.printed_number_as_seen; }
  if (s.heads_not_shown != null) { const h = card.querySelector(".headsnotshown"); if (h) h.value = s.heads_not_shown; }
});
renderStat();
document.getElementById("export").addEventListener("click", function () {
  const lines = ITEMS.map(function (it) {
    const s = state[it.item_id] || {};
    const rec = {
      item_id: it.item_id, item_kind: it.item_kind, file_page: it.file_page,
      printed_page: it.printed_page, verdict: s.verdict || "unrated", note: s.note || "",
      item_sha16: it.item_sha16, set_sha16: SET_SHA16, run_config_hash: RUN_CONFIG_HASH,
      door: "human-verse-box-truth", session_freshness: "in-context-WARN",
      exported_utc: new Date().toISOString(),
    };
    if (it.item_kind === "verse" && s.verdict === "number_wrong") {
      rec.printed_number_as_seen = s.printed_number_as_seen || "";
    }
    if (it.item_kind === "page") {
      const raw = s.heads_not_shown;
      if (raw === undefined || raw === "") { rec.heads_not_shown = null; rec.verdict = "unrated"; }
      else {
        const n = Number(raw);
        const isInt = Number.isInteger(n) && n >= 0 && String(raw).trim() === String(n);
        rec.heads_not_shown = isInt ? n : "invalid";
        rec.verdict = "answered";
      }
    }
    return JSON.stringify(rec);
  });
  const blob = new Blob([lines.join("\n")], { type: "application/x-ndjson" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = EXPORT_FILENAME;
  a.click();
});
"""


def _render_html(set_sha, items_for_js, run_config_hash, cards_html_list):
    ls_key = "versetruth_" + set_sha
    export_filename = f"verse_box_verdicts_{set_sha}.jsonl"
    cards = "\n".join(cards_html_list)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Verse-box truth console -- step 3 -- {set_sha}</title>
<style>{_CSS}</style></head><body>
<header><h1>Verse-box truth console</h1>
<span id="stat"></span><button id="export" type="button">Export verdicts JSONL</button></header>
<main id="cards">
{cards}
</main>
<script>
const SET_SHA16 = {json.dumps(set_sha)};
const LS_KEY = {json.dumps(ls_key)};
const EXPORT_FILENAME = {json.dumps(export_filename)};
const RUN_CONFIG_HASH = {json.dumps(run_config_hash)};
const ITEMS = {json.dumps(items_for_js, ensure_ascii=False)};
{_JS}
</script>
</body></html>"""


# ==================================================================================================
# loaders
# ==================================================================================================

def load_run_records(path):
    recs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    return recs


def load_misses(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_geometry_by_fp(path):
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            out[rec["file_page"]] = rec
    return out


# ==================================================================================================
# layout refusal, stale-miss check, carry-forward map (miss-card diagnoses by heading identity)
# ==================================================================================================

LAYOUT_KEYS = ("head_first", "overlap", "rect_before_head")


def check_layout(run_records):
    """Refuse (ValueError) a run whose run_summary is missing, lacks "layout", or has any
    layout count > 0. Old runs predate the layout invariants and are refused by design."""
    summ = next((r for r in run_records if r.get("kind") == "run_summary"), None)
    if summ is None:
        raise ValueError("run has no run_summary line: refusing (an unfinished run has no layout verdict)")
    layout = summ.get("layout")
    if not isinstance(layout, dict):
        raise ValueError('run_summary has no "layout" field: the run predates the layout invariants; refusing')
    counts = {k: layout.get(k) for k in LAYOUT_KEYS}
    bad = {k: v for k, v in counts.items() if v is None or v > 0}
    if bad:
        raise ValueError(f"run layout violations (head_first/overlap/rect_before_head must all be 0): {counts}")
    return counts


def _boxes_intersect(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def check_misses_not_stale(run_records, misses):
    """Raise if any miss's Tesseract word box is now covered by a region head on the same file page."""
    miss_list = misses["misses"] if isinstance(misses, dict) else misses
    for rec in run_records:
        if rec.get("kind") not in REGION_KINDS:
            continue
        head = rec.get("head")
        if not head or not head.get("box"):
            continue
        hfp = head.get("file_page", rec.get("file_page_first"))
        for m in miss_list:
            if m["fp"] == hfp and _boxes_intersect(head["box"], m["word"]):
                raise ValueError(
                    f"miss trace stale: m:{m['fp']}:{m['word'][1]} now detected by region "
                    f"{rec.get('kind')} on file page {hfp} (head box {head['box']})")


def _int4(b):
    return [int(round(v)) for v in b]


def read_old_console(old_dir):
    """Returns (set_sha16, [ {item_id,item_sha16,file_page,band,word_y0} ]) for the miss items of an
    old console. Raises if the manifest header's set_sha16 differs from the directory name."""
    old_dir = Path(old_dir)
    mlines = _read_manifest(old_dir / "manifest.jsonl")
    old_set = mlines[0].get("set_sha16")
    if old_set != old_dir.name:
        raise ValueError(f"old console set_sha16 {old_set!r} != directory name {old_dir.name!r}")
    out = []
    for l in mlines:
        if l.get("kind") == "item" and l.get("item_kind") == "miss":
            out.append({"item_id": l["item_id"], "item_sha16": l["item_sha16"], "file_page": l["file_page"],
                        "band": _int4(l["crops"][0]["rect"]), "word_y0": int(l["item_id"].rsplit(":", 1)[1])})
    return old_set, out


def new_miss_entries(items, item_shas=None):
    item_shas = item_shas or {}
    return [{"item_id": it["item_id"], "item_sha16": item_shas.get(it["item_id"]), "file_page": it["file_page"],
             "band": _int4(it["miss"]["band"]), "word_y0": int(it["miss"]["word"][1])}
            for it in items if it["item_kind"] == "miss"]


def compute_carry(old_set, old_entries, new_entries):
    """Classify by heading identity (file_page, word_y0, band rect). Returns (CARRY, counts, lists).
    identity_conflict list = NEW item ids whose fp+word_y0 matches an old item with a different band
    (the old side of such a pair is not also counted as old_unmatched)."""
    old_by_id = {}
    for o in old_entries:
        old_by_id.setdefault((o["file_page"], o["word_y0"], tuple(o["band"])), []).append(o)
    old_by_fy = {}
    for o in old_entries:
        old_by_fy.setdefault((o["file_page"], o["word_y0"]), []).append(o)
    cmap, conflicts, new_unmatched, used_old = {}, [], [], set()
    for n in new_entries:
        key = (n["file_page"], n["word_y0"], tuple(n["band"]))
        hits = [o for o in old_by_id.get(key, []) if o["item_id"] not in used_old]
        if hits:
            o = hits[0]
            used_old.add(o["item_id"])
            cmap[n["item_id"]] = {"old_item_id": o["item_id"], "old_item_sha16": o["item_sha16"],
                                  "identity": {"file_page": n["file_page"], "word_y0": n["word_y0"], "band": list(n["band"])}}
        elif old_by_fy.get((n["file_page"], n["word_y0"])):
            conflicts.append(n["item_id"])
            for o in old_by_fy[(n["file_page"], n["word_y0"])]:
                used_old.add(o["item_id"])
        else:
            new_unmatched.append(n["item_id"])
    old_unmatched = sorted(o["item_id"] for o in old_entries if o["item_id"] not in used_old)
    carry = {"from_set_sha16": old_set, "from_ui_key": "versetruth_" + old_set + "_ui2",
             "fields": ["cause_verdict", "note"], "map": cmap}
    counts = {"matched": len(cmap), "identity_conflict": len(conflicts),
              "old_unmatched": len(old_unmatched), "new_unmatched": len(new_unmatched)}
    lists = {"identity_conflict": sorted(conflicts), "old_unmatched": old_unmatched,
             "new_unmatched": sorted(new_unmatched)}
    return carry, counts, lists


def carry_from_console(old_dir, items, item_shas=None):
    old_set, old_entries = read_old_console(old_dir)
    carry, counts, lists = compute_carry(old_set, old_entries, new_miss_entries(items, item_shas))
    return carry, _sha16_json(carry), counts, lists



# ==================================================================================================
# prior verdicts carried by HEADING IDENTITY (the old console's region / page verdicts)
# ==================================================================================================

PRIOR_VERDICTS_WITH_BOX = ("correct", "adjusted", "region_drawn")


def run_pitch_px(run_records):
    """thresholds.inset_thr.pitch_px of the run's run_summary, or None when absent."""
    for r in run_records:
        if r.get("kind") == "run_summary":
            try:
                p = r["thresholds"]["inset_thr"]["pitch_px"]
            except (KeyError, TypeError):
                return None
            return p if isinstance(p, (int, float)) and p > 0 else None
    return None


def prior_head_tol_px(pitch_px):
    """Half-pitch tolerance. Refuses (no default) when the pitch is absent."""
    if not isinstance(pitch_px, (int, float)) or isinstance(pitch_px, bool) or pitch_px <= 0:
        raise ValueError("compute_prior: the new run's run_summary.thresholds.inset_thr.pitch_px is absent; "
                         "refusing to default the near-match tolerance")
    return int(math.floor(pitch_px / 2))


def _fp_of_item_id(item_id):
    return int(item_id.split(":")[1])


def _verse_tuple(v):
    if v is None:
        return ()
    return tuple(v) if isinstance(v, (list, tuple)) else (v,)


def _head_col_y0(item):
    """(col, y0) of the item's head; col falls back to the first rect's col, y0 to head.box[1]."""
    h = item["head"]
    return (h.get("col") or item["rects"][0]["col"]), (h["y0"] if h.get("y0") is not None else h["box"][1])


def _prior_identity(item):
    fp = int(item["file_page"])
    if not item.get("head"):
        return ("cont", fp, item["rects"][0]["col"])
    col, y0 = _head_col_y0(item)
    return ("head", fp, col, y0, _verse_tuple(item.get("verse")))


def _prior_edges(edges):
    out = {}
    for k in ("top", "bottom"):
        e = (edges or {}).get(k) or {}
        out[k] = {"snapped": bool(e.get("snapped")), "at_crop_limit": bool(e.get("at_crop_limit"))}
    return out


def _prior_rect(r):
    return {"file_page": int(r["file_page"]), "col": r["col"], "box": [int(v) for v in r["box"]],
            "edges": _prior_edges(r.get("edges"))}


def compute_prior(old_run_records, old_export_rows, new_items, pitch_px=None, export_sha256=None,
                  old_run_sha256=None):
    """Carry the old console's verdicts to the new items by heading identity. Returns
    (PRIOR, counts, lists). Refuses (ValueError) on a mixed-set export, on an export row whose
    item_id is not an item of the old run (+ the export's own miss rows), and when pitch_px is
    absent. Matching: exact head identity; near (same fp/col/verse, |dy| <= floor(pitch/2), exactly
    one candidate); near_old_verse_unread (stage 2b: the OLD verse is None/[] -- the witness was silent --
    same fp/col, same tolerance, same uniqueness rules; two READ verses that differ never match);
    from a miss's drawn region. Each old source is used at most once."""
    tol = prior_head_tol_px(pitch_px)
    rows = list(old_export_rows)
    sets = sorted({r.get("set_sha16") for r in rows}, key=str)
    if len(sets) != 1:
        raise ValueError(f"compute_prior: export rows come from {len(sets)} sets {sets}; need exactly one")
    from_set = sets[0]
    miss_rows = [r for r in rows if r.get("item_kind") == "miss"]
    old_misses = [{"fp": _fp_of_item_id(r["item_id"]), "word": [0, int(r["item_id"].rsplit(":", 1)[1]), 0, 0]}
                  for r in miss_rows]
    old_items = build_items(old_run_records, old_misses)
    old_by_id = {i["item_id"]: i for i in old_items}
    for r in rows:
        if r["item_id"] not in old_by_id:
            raise ValueError(f"compute_prior: export row {r['item_id']} is not an item of the old run")
    row_by_id = {r["item_id"]: r for r in rows}

    old_regions = [i for i in old_items if i["item_kind"] in REGION_KINDS]
    new_regions = [i for i in new_items if i["item_kind"] in REGION_KINDS]
    miss_src = []
    for r in miss_rows:
        if r.get("verdict") == "region_drawn" and r.get("as_ratified"):
            miss_src.append({"item_id": r["item_id"], "fp": _fp_of_item_id(r["item_id"]),
                             "y": int(r["item_id"].rsplit(":", 1)[1]),
                             "cols": {d["col"] for d in r["as_ratified"]}})

    src = {}                    # new id -> (kind, old id, match)
    used_old, used_miss, conflicts = set(), set(), []

    # 1. exact
    by_ident = {}
    for o in old_regions:
        by_ident.setdefault(_prior_identity(o), []).append(o["item_id"])
    for n in new_regions:
        for oid in by_ident.get(_prior_identity(n), []):
            if oid not in used_old:
                used_old.add(oid)
                src[n["item_id"]] = ("region", oid, "exact")
                break

    def pending():
        return [n for n in new_regions if n["item_id"] not in src and n["item_id"] not in conflicts
                and n.get("head")]

    def claim(cands_fn, kind, match):
        claims = {}
        for n in pending():
            cands = cands_fn(n)
            if len(cands) >= 2:
                conflicts.append(n["item_id"])
            elif len(cands) == 1:
                claims.setdefault(cands[0], []).append(n["item_id"])
        for oid, nids in claims.items():
            if len(nids) > 1:
                conflicts.extend(nids)
            else:
                (used_old if kind == "region" else used_miss).add(oid)
                src[nids[0]] = (kind, oid, match)

    # 2. near
    def near_cands(n):
        col, y0 = _head_col_y0(n)
        return [o["item_id"] for o in old_regions
                if o["item_id"] not in used_old and o.get("head")
                and int(o["file_page"]) == int(n["file_page"]) and _head_col_y0(o)[0] == col
                and _verse_tuple(o.get("verse")) == _verse_tuple(n.get("verse"))
                and abs(y0 - _head_col_y0(o)[1]) <= tol]
    claim(near_cands, "region", "near")

    # 2b. near, old verse unread: an unread verse is the witness's silence, not a different heading
    def unread_cands(n):
        col, y0 = _head_col_y0(n)
        return [o["item_id"] for o in old_regions
                if o["item_id"] not in used_old and o.get("head") and _verse_tuple(o.get("verse")) == ()
                and int(o["file_page"]) == int(n["file_page"]) and _head_col_y0(o)[0] == col
                and abs(y0 - _head_col_y0(o)[1]) <= tol]
    claim(unread_cands, "region", "near_old_verse_unread")

    # 3. from a miss's drawn region
    def miss_cands(n):
        col, y0 = _head_col_y0(n)
        return [m["item_id"] for m in miss_src
                if m["item_id"] not in used_miss and m["fp"] == int(n["file_page"]) and col in m["cols"]
                and abs(y0 - m["y"]) <= tol]
    claim(miss_cands, "miss", "from_miss")

    # ---- classify ----
    pmap = {}
    for n in new_regions:
        nid = n["item_id"]
        if nid not in src:
            continue
        kind, oid, match = src[nid]
        row = row_by_id.get(oid)
        v = (row or {}).get("verdict") or "unrated"
        note = (row or {}).get("note") or ""
        if not note.strip():
            note = ""
        if kind == "miss":
            T_raw = row["as_ratified"]
        else:
            T_raw = (row or {}).get("as_ratified") or (row or {}).get("as_detected")
        T = [_prior_rect(t) for t in (T_raw or [])]
        ent = {"class": None, "match": match, "old_item_id": oid, "seeded": None, "delta": None,
               "prior": {"verdict": v, "rects": T, "note": note, "heads_not_shown": None}}
        if v not in PRIOR_VERDICTS_WITH_BOX and v != "not_a_verse":
            ent["class"] = "fresh"
        elif v == "not_a_verse":
            ent["class"] = "carried_verdict"
            ent["seeded"] = {"verdict": "not_a_verse"}
            if note:
                ent["seeded"]["note"] = note
        else:
            nkeys = [(int(r["file_page"]), r["col"]) for r in n["rects"]]
            tkeys = [(t["file_page"], t["col"]) for t in T]
            same = bool(T) and len(set(nkeys)) == len(nkeys) and len(set(tkeys)) == len(tkeys) \
                and set(nkeys) == set(tkeys)
            if not same:
                ent["class"] = "layout_changed"
            else:
                tmap = {(t["file_page"], t["col"]): t for t in T}
                rat, delta, all_eq = [], {}, True
                for r, key in zip(n["rects"], nkeys):
                    t = tmap[key]
                    box = [int(r["box"][0]), t["box"][1], int(r["box"][2]), t["box"][3]]
                    if box != [int(x) for x in r["box"]]:
                        all_eq = False
                    rat.append({"box": box, "edges": t["edges"]})
                    delta[f"{key[0]}:{key[1]}"] = [t["box"][1] - int(r["box"][1]), t["box"][3] - int(r["box"][3])]
                ent["class"] = "carried_same_layout"
                ent["seeded"] = {"verdict": "correct" if all_eq else "adjusted", "ratified": rat}
                if note:
                    ent["seeded"]["note"] = note
                ent["delta"] = delta
        pmap[nid] = ent

    # ---- pages ----
    new_pages = [i for i in new_items if i["item_kind"] == "page"]
    for pg in new_pages:
        fp = int(pg["file_page"])
        prow = row_by_id.get(f"p:{fp}")
        hns = (prow or {}).get("heads_not_shown")
        if not (prow and prow.get("verdict") == "answered" and isinstance(hns, int) and not isinstance(hns, bool)):
            continue
        pnote = prow.get("note") or ""
        regs_new = [n["item_id"] for n in new_regions if int(n["file_page"]) == fp]
        ok_new = all(i in pmap and pmap[i]["class"] in ("carried_same_layout", "carried_verdict") for i in regs_new)
        ok_old = all(o["item_id"] in used_old for o in old_regions if int(o["file_page"]) == fp)
        ent = {"class": None, "match": "page", "old_item_id": f"p:{fp}", "seeded": None, "delta": None,
               "prior": {"verdict": "answered", "rects": [], "note": pnote, "heads_not_shown": hns}}
        if ok_new and ok_old:
            ent["class"] = "carried_same_layout"
            ent["seeded"] = {"heads_not_shown": hns}
            if pnote.strip():
                ent["seeded"]["note"] = pnote
        else:
            ent["class"] = "layout_changed"
        pmap[pg["item_id"]] = ent

    # ---- leftovers (retired: never carried, never silently dropped) ----
    old_unmatched = []
    for o in old_regions:
        r = row_by_id.get(o["item_id"])
        if o["item_id"] not in used_old and r and (r.get("verdict") or "unrated") != "unrated":
            old_unmatched.append({"item_id": o["item_id"], "verdict": r["verdict"], "note": r.get("note") or ""})
    for m in miss_rows:
        if m["item_id"] not in used_miss and (m.get("verdict") or "unrated") != "unrated":
            old_unmatched.append({"item_id": m["item_id"], "verdict": m["verdict"], "note": m.get("note") or ""})
    new_page_ids = {p["item_id"] for p in new_pages}
    for r in rows:
        if r.get("item_kind") == "page" and r.get("verdict") == "answered" and r["item_id"] not in new_page_ids:
            old_unmatched.append({"item_id": r["item_id"], "verdict": r["verdict"], "note": r.get("note") or ""})
    old_unmatched.sort(key=lambda d: d["item_id"])
    new_unmatched = sorted(n["item_id"] for n in new_regions if n["item_id"] not in src and n["item_id"] not in conflicts)

    prior = {"from_set_sha16": from_set, "export_sha256": export_sha256, "old_run_sha256": old_run_sha256,
             "map": pmap}
    by_class, by_match = {}, {}
    for nid, e in pmap.items():
        by_class.setdefault(e["class"], []).append(nid)
        by_match[e["match"]] = by_match.get(e["match"], 0) + 1
    counts = {"by_class": {k: len(v) for k, v in sorted(by_class.items())}, "by_match": dict(sorted(by_match.items())),
              "seeded": sum(1 for e in pmap.values() if e["seeded"]),
              "identity_conflict": len(conflicts), "old_unmatched": len(old_unmatched),
              "new_unmatched": len(new_unmatched)}
    lists = {"by_class": {k: sorted(v) for k, v in sorted(by_class.items())},
             "identity_conflict": sorted(conflicts), "old_unmatched": old_unmatched, "new_unmatched": new_unmatched}
    return prior, counts, lists


def prior_from_paths(prior_export, prior_run, new_run_records, new_items):
    """File front end for compute_prior: reads the export + old run, hashes them, reads the pitch
    from the NEW run. Returns (PRIOR, prior_sha16, counts, lists)."""
    rows = [json.loads(l) for l in Path(prior_export).read_text(encoding="utf-8").splitlines() if l.strip()]
    old_recs = load_run_records(prior_run)
    prior, counts, lists = compute_prior(old_recs, rows, new_items, pitch_px=run_pitch_px(new_run_records),
                                         export_sha256=_sha256_file(prior_export),
                                         old_run_sha256=_sha256_file(prior_run))
    return prior, _sha16_json(prior), counts, lists


def _utc_now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ==================================================================================================
# build (the orchestrator -- the only thing that touches images/disk, besides the loaders above)
# ==================================================================================================

def _prior_manifest_fields(prior_export, prior_run, prior, prior_sha, counts, lists):
    return {
        "prior_export": str(prior_export) if prior_export else None,
        "export_sha256": prior["export_sha256"] if prior else None,
        "prior_run": str(prior_run) if prior_run else None,
        "old_run_sha256": prior["old_run_sha256"] if prior else None,
        "prior_map_sha16": prior_sha, "prior_counts": counts, "prior_lists": lists,
    }


def build(run_path, misses_path, geometry_path, volume_dir, out_root, force=False, module_path=None,
          carry_from=None, prior_export=None, prior_run=None):
    if carry_from:
        raise ValueError("--carry-from is not valid for a fresh build (it emits UI1): build first, then run "
                         "--html-only --carry-from <old console dir>")
    run_path = Path(run_path)
    misses_path = Path(misses_path)
    geometry_path = Path(geometry_path)
    volume_dir = Path(volume_dir)
    out_root = Path(out_root)
    module_path = Path(module_path).resolve() if module_path else Path(__file__).resolve()

    run_records = load_run_records(run_path)
    misses_doc = load_misses(misses_path)
    check_layout(run_records)
    check_misses_not_stale(run_records, misses_doc)
    geometry_by_fp = load_geometry_by_fp(geometry_path)
    page_by_fp = page_records_by_fp(run_records)

    run_header = next((r for r in run_records if r.get("kind") == "run_header"), None)
    run_config_hash = (run_header.get("config") or {}).get("hash") if run_header else None

    items = build_items(run_records, misses_doc)
    if bool(prior_export) != bool(prior_run):
        raise ValueError("--prior-export and --prior-run go together")
    prior, prior_sha, prior_counts, prior_lists = None, None, None, None
    if prior_export:
        prior, prior_sha, prior_counts, prior_lists = prior_from_paths(prior_export, prior_run, run_records, items)

    image_cache = {}
    n_clamped = 0
    n_crops = 0
    rendered = {}

    for item in items:
        kind = item["item_kind"]
        if kind in REGION_KINDS:
            crops, overlays = _render_region_crops(item, volume_dir, image_cache)
        elif kind == "miss":
            crop, ov = _render_miss_crop(item, geometry_by_fp, volume_dir, image_cache,
                                         page_records_by_fp(run_records))
            crops, overlays = [crop], [ov]
        else:
            crops, overlays = [], []
        rendered[item["item_id"]] = {"crops": crops, "overlays": overlays}
        for c in crops:
            n_crops += 1
            if c["clamped_edges"]:
                n_clamped += 1

    item_shas = {}
    for item in items:
        crop_shas = [c["crop_sha16"] for c in rendered[item["item_id"]]["crops"]]
        item_shas[item["item_id"]] = item_sha16(item, crop_shas)

    set_sha = set_sha16((iid, sha) for iid, sha in item_shas.items())
    out_dir = out_root / set_sha

    run_file_sha256 = _sha256_file(run_path)
    misses_file_sha256 = _sha256_file(misses_path)
    module_sha256 = BVR.compute_module_sha256(module_path)
    builder_config = {
        "PAD_PX": PAD_PX, "run": str(run_path), "misses": str(misses_path),
        "geometry": str(geometry_path), "volume_dir": str(volume_dir),
        "run_file_sha256": run_file_sha256, "misses_file_sha256": misses_file_sha256,
        "module_sha256": module_sha256,
    }
    config_hash = _sha16_json(builder_config)

    repo_root = module_path.parents[2]
    git_head = BVR.get_git_head(repo_root)
    git_dirty = BVR.get_git_dirty(repo_root)

    manifest_path = out_dir / "manifest.jsonl"
    if out_dir.exists():
        if manifest_path.exists():
            try:
                first_line = manifest_path.read_text(encoding="utf-8").splitlines()[0]
                existing_set = json.loads(first_line).get("set_sha16")
            except Exception:
                existing_set = None
            if existing_set is not None and existing_set != set_sha:
                raise RefuseOverwrite(
                    f"REFUSED: {out_dir} exists with manifest set_sha16={existing_set!r} but the "
                    f"freshly computed set_sha16={set_sha!r} -- impossible by construction (out_dir "
                    f"is named by set_sha16); refusing unconditionally, never forced."
                )
        if not force:
            raise RefuseOverwrite(
                f"REFUSED: {out_dir} already exists. Pass force=True (--force on the CLI) to overwrite it."
            )

    crops_dir = out_dir / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)

    n_items_by_kind = {"region": 0, "miss": 0, "page": 0}
    for item in items:
        if item["item_kind"] in REGION_KINDS:
            n_items_by_kind["region"] += 1
        elif item["item_kind"] == "miss":
            n_items_by_kind["miss"] += 1
        else:
            n_items_by_kind["page"] += 1

    header = {
        "kind": "console_header", "tier": "best_effort", "config_hash": config_hash,
        "git_head": git_head, "git_dirty": git_dirty, "started_utc": _utc_now_iso(),
        "run_file": str(run_path), "run_file_sha256": run_file_sha256,
        "run_config_hash": run_config_hash, "set_sha16": set_sha, "n_items": n_items_by_kind,
        "carry_from": None, "carry_from_set_sha16": None, "carry_map_sha16": None, "carry_counts": None,
        "carry_identity_conflict": None, "carry_old_unmatched": None, "carry_new_unmatched": None,
        # the UI1 this fresh build emits does not seed from the prior; the UI that does is --html-only
        **_prior_manifest_fields(prior_export, prior_run, prior, prior_sha, prior_counts, prior_lists),
    }
    lines = [json.dumps(header, sort_keys=True)]

    cards_by_fp = {}
    items_for_js = []

    for item in items:
        r = rendered[item["item_id"]]
        crop_meta_list = []
        crop_rel_paths = []
        for c in r["crops"]:
            fname = f"{_safe_id(item['item_id'])}_{c['idx']}.png"
            rel_path = f"crops/{fname}"
            (crops_dir / fname).write_bytes(c["png_bytes"])
            crop_meta_list.append({
                "path": rel_path, "crop_sha16": c["crop_sha16"], "crop_origin": c["crop_origin"],
                "crop_size": c["crop_size"], "clamped_edges": c["clamped_edges"],
                "rect": c["rect"], "ink_frac": c["ink_frac"],
            })
            crop_rel_paths.append(rel_path)

        item_line = {
            "kind": "item", "item_id": item["item_id"], "item_kind": item["item_kind"],
            "item_sha16": item_shas[item["item_id"]], "file_page": item["file_page"],
            "crops": crop_meta_list, "tier": "best_effort", "config_hash": config_hash,
        }
        lines.append(json.dumps(item_line, sort_keys=True))

        items_for_js.append({
            "item_id": item["item_id"], "item_kind": item["item_kind"],
            "file_page": item["file_page"], "printed_page": item["file_page"] - 88,
            "item_sha16": item_shas[item["item_id"]],
        })

        card_html = _render_card(item, r["crops"], r["overlays"], crop_rel_paths, volume_dir)
        grp = cards_by_fp.setdefault(item["file_page"], {"region": [], "miss": [], "page": None})
        if item["item_kind"] in REGION_KINDS:
            _add_region_card(grp, item["item_kind"], card_html)
        elif item["item_kind"] == "miss":
            grp["miss"].append(card_html)
        else:
            grp["page"] = card_html

    summary = {
        "kind": "console_summary", "n_items": len(items), "n_crops": n_crops,
        "n_clamped": n_clamped, "finished_utc": _utc_now_iso(),
    }
    lines.append(json.dumps(summary, sort_keys=True))
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")

    all_cards_html = []
    for fp in sorted(cards_by_fp):
        grp = cards_by_fp[fp]
        all_cards_html.extend(grp["region"])
        all_cards_html.extend(grp["miss"])
        if grp["page"]:
            all_cards_html.append(grp["page"])

    html_text = _render_html(set_sha, items_for_js, run_config_hash, all_cards_html)
    with open(out_dir / "index.html", "w", encoding="utf-8", newline="\n") as f:
        f.write(html_text)

    return {
        "out_dir": out_dir, "crops_dir": crops_dir, "set_sha16": set_sha,
        "n_items_by_kind": n_items_by_kind, "n_items": len(items), "n_crops": n_crops,
        "n_clamped": n_clamped, "html_bytes": len(html_text.encode("utf-8")),
        "items": items, "item_shas": item_shas, "header": header,
    }


# ==================================================================================================
# UI 2 (--html-only): box placement. Crops are NOT re-rendered; the existing console is verified
# against its own manifest and only index.html is rebuilt (the old one is renamed, never deleted).
# ==================================================================================================

UI_VERSION = 2
UI_JS_NAME = "verse_truth_ui.js"


def _ui_js_path(module_path):
    return Path(module_path).resolve().parent / UI_JS_NAME


def _crop_html_ui2(crop, overlays, rel_path, idx=0):
    """Region crop for UI 2: static (non-rect) overlays server-side; the detected/ratified outlines,
    snap ticks and drag handles live in the JS-built .edit layer."""
    w, h = crop["crop_size"]
    static = [ov for ov in overlays if ov.get("kind") != "rect"]
    inner = _crop_html(crop, static, rel_path)
    inner = inner.replace(
        f'<div class="stagewrap" style="width:{w}px;height:{h}px">',
        f'<div class="stagewrap" data-idx="{idx}" style="width:{w}px;height:{h}px">', 1)
    inner = inner.replace("</div></div><div class=\"cropmeta\">",
                          '<div class="edit"></div></div></div><div class="cropmeta">', 1)
    return inner + f'<div class="lm" data-idx="{idx}"></div>'


def _verdict_fieldset_ui2(item):
    kind = item["item_kind"]
    safe = _safe_id(item["item_id"])
    if kind == "verse":
        opts, extra = ["correct", "adjusted", "not_a_verse"], '<input type="text" class="pnumber" placeholder="printed number as seen">'
    elif kind in ("chapter_intro", "continuation_unanchored"):
        opts, extra = ["correct", "adjusted"], ""
    elif kind == "miss":
        opts, extra = ["region_drawn", "not_a_verse"], ""
    else:
        return ""
    radios = "".join(f'<label><input type="radio" name="v_{safe}" value="{o}"> {o}</label>' for o in opts)
    cause = ""
    if kind == "miss":
        cause = ('<fieldset class="verdict cause"><span class="lbl">cause of the miss:</span>'
                 + "".join(f'<label><input type="radio" class="causeradio" name="c_{safe}" value="{o}"> {o}</label>'
                           for o in ("cause_confirmed", "cause_wrong", "unsure"))
                 + "</fieldset>")
    return (f'<fieldset class="verdict"><span class="lbl">{"region:" if kind == "miss" else "box:"}</span>{radios}{extra}'
            f'<textarea class="note" placeholder="note"></textarea></fieldset>{cause}')


def _pagewin_html(item, volume_dir, W, H):
    url = _page_url(item["file_page"], volume_dir)
    return (f'<div class="pwwrap"><div class="errbanner" hidden>page image failed to load: {_esc(url)}</div>'
            f'<div class="pwmsg"></div><div class="drawbar"></div>'
            f'<div class="pagewin"><div class="pwinner" style="width:{W}px;height:{H}px">'
            f'<img class="pwimg" src="{url}" alt="page" data-path="{_esc(url)}">'
            f'<div class="pedit"></div></div></div></div>')


_CSS_UI2 = r"""
[hidden]{display:none!important}
header label.snap{font-size:13px;display:flex;gap:4px;align-items:center}
header #export{margin-left:0}
.migbanner{background:#9a2b2b;color:#fff;padding:8px 16px;font-size:13px;display:flex;gap:12px;align-items:center}
.migbanner button{background:#fff;color:#9a2b2b;border:0;padding:4px 10px;border-radius:4px;cursor:pointer}
.errbanner{background:#9a2b2b;color:#fff;padding:6px 12px;font-size:12px}
.stagewrap .edit,.pwinner .pedit{position:absolute;left:0;top:0;right:0;bottom:0}
.pwinner .pedit{cursor:crosshair}
.edit .det,.pedit .det{position:absolute;border:1px dashed #111;background:none;pointer-events:none}
.edit .rat,.pedit .rat{position:absolute;border:2px solid #d4380d;background:rgba(212,56,13,.08);pointer-events:none}
.edit .tick{position:absolute;left:0;width:14px;height:0;border-top:1px solid rgba(60,180,75,.7);pointer-events:none}
.edit .tick.b{left:auto;right:0;border-top-color:rgba(70,130,220,.7)}
.handle{position:absolute;left:0;width:100%;height:12px;cursor:ns-resize;pointer-events:auto;background:rgba(212,56,13,.0)}
.handle:hover{background:rgba(212,56,13,.25)}
.lm{font-size:12px;font-family:ui-monospace,monospace;padding:2px 12px;color:#7a2a12}
.pagewin{height:900px;overflow:auto;background:#222;border-top:1px solid var(--rule)}
.pwinner{position:relative}
.pwimg{display:block;image-rendering:pixelated}
.pedit .prect{position:absolute;border:1px dashed #3a8;pointer-events:none;font-size:11px;color:#3a8;background:rgba(58,170,136,.06)}
.pedit .prect span{background:#fff;padding:0 3px}
.card{max-width:none;margin:12px 8px}
.stagewrap,.pwinner{transform-origin:0 0}
.handle{height:calc(12px * var(--inv,1))}
.edit .tick{border-top-width:calc(1px * var(--inv,1));width:calc(14px * var(--inv,1))}
.edit .det,.pedit .det{border-width:calc(1px * var(--inv,1))}
.edit .rat,.pedit .rat{border-width:calc(2px * var(--inv,1))}
.pedit .prect{font-size:calc(11px * var(--inv,1));border-width:calc(1px * var(--inv,1))}
.pedit .bandov{position:absolute;border:2px solid #b5482e;pointer-events:none}
.pedit .wordov{position:absolute;border:2px solid #2f6f9c;pointer-events:none}
.drawbar{padding:4px 12px;font-size:12px}
.drawbar button{margin-right:8px}
.pwmsg{padding:2px 12px;font-size:12px;color:#9a2b2b}
.verdict .lbl{font-size:12px;font-weight:600}
.carrybanner{padding:8px 16px;font-size:13px;color:#fff;background:#1f7a3a}
.carrybanner.red{background:#9a2b2b}
.carrybanner input,.carrybanner button{margin-left:8px}
.priorbadge{background:#1f7a3a;color:#fff;font-size:11px;padding:1px 6px;border-radius:3px;margin-left:8px}
.priorbadge.layout{background:#9a2b2b}
.needsbadge{background:#b36b00;color:#fff;font-size:11px;padding:1px 6px;border-radius:3px;margin-left:8px}
.priorbox{padding:2px 12px;font-size:12px;color:#7a2a12;font-family:ui-monospace,monospace}
.edit .ghost{position:absolute;border:2px dashed #7b3fb3;background:none;pointer-events:none}
.edit .ghost span{position:absolute;left:2px;top:0;font-size:calc(11px * var(--inv,1));background:#fff;color:#7b3fb3;padding:0 3px}
#missing{margin-left:12px;font-size:13px}
#nextinc{margin-left:8px}
.carrybadge{background:#1f7a3a;color:#fff;font-size:11px;padding:1px 6px;border-radius:3px;margin-left:8px}
"""

_JS_UI2_GLUE = r"""
// ---- DOM glue (all geometry/verdict logic is in the pure functions above) ----
var state = {}, snapOn = true;
try {
  var raw0 = localStorage.getItem(LS_KEY);
  if (raw0) { var o0 = JSON.parse(raw0); if (o0 && o0.ui_version === 2) { state = o0.items || {}; snapOn = o0.snap_on !== false; } }
} catch (e) { state = {}; }
var ITEM_BY_ID = {};
ITEMS.forEach(function (it) { ITEM_BY_ID[it.item_id] = it; });
function carriedCount() {
  var n = 0;
  ITEMS.forEach(function (it) { var s = state[it.item_id]; if (s && s.carried_from && CARRY && s.carried_from.set_sha16 === CARRY.from_set_sha16) n++; });
  return n;
}
function renderCarryBanner(extra) {
  if (!CARRY) return;
  var b = document.getElementById("carrybanner"); b.hidden = false; b.textContent = "";
  var n = carriedCount();
  var span = document.createElement("span");
  if (n > 0) {
    b.className = "carrybanner";
    span.textContent = "Carried " + n + " miss-card diagnoses from console " + CARRY.from_set_sha16 +
      " by heading identity (cause verdict + note). Region verdicts and drawn rects are NOT carried \u2014 the geometry is re-sat in full.";
  } else {
    b.className = "carrybanner red";
    span.textContent = "No diagnoses found under " + CARRY.from_ui_key + " in this browser. If they were made in another browser, export them there and use Import.";
  }
  b.appendChild(span);
  if (extra) { var e = document.createElement("div"); e.textContent = extra; b.appendChild(e); }
  var inp = document.createElement("input"); inp.type = "file"; inp.accept = ".jsonl,.json,.txt";
  inp.title = "verse_box_verdicts_" + CARRY.from_set_sha16 + "_ui2.jsonl";
  inp.addEventListener("change", function () {
    var f = inp.files && inp.files[0]; if (!f) return;
    var rd = new FileReader();
    rd.onload = function () {
      var rows = [];
      String(rd.result).split("\n").forEach(function (ln) { ln = ln.trim(); if (!ln) return; try { rows.push(JSON.parse(ln)); } catch (e) {} });
      var conv = rowsToOldItems(rows, CARRY.from_set_sha16);
      if (conv.refused) window.alert(conv.refused + " row(s) refused: set_sha16 is not " + CARRY.from_set_sha16);
      applyCarry(conv.items);
    };
    rd.readAsText(f);
  });
  var lab = document.createElement("label"); lab.textContent = "Import old verdicts JSONL:"; lab.style.marginLeft = "12px"; lab.appendChild(inp);
  b.appendChild(lab);
}
function carryNotes() {
  var parts = [];
  if (typeof CARRY_REPORT !== "undefined" && CARRY_REPORT) {
    ["identity_conflict", "new_unmatched"].forEach(function (k) { if (CARRY_REPORT[k] && CARRY_REPORT[k].length) parts.push(k + ": " + CARRY_REPORT[k].join(", ")); });
  }
  return parts.join("  |  ");
}
function applyCarry(oldItems) {
  var res = carryForward(state, oldItems, CARRY);
  state = res.items;
  save();
  ITEMS.forEach(function (it) { restoreFields(it); renderItem(it); });
  renderCarryBanner(carryNotes());
}
function save() {
  try { localStorage.setItem(LS_KEY, JSON.stringify({ ui_version: 2, items: state, snap_on: snapOn })); } catch (e) {}
  renderStat();
}
function cardOf(it) { return document.getElementById("card_" + it.item_id.split(":").join("_")); }
function renderStat() {
  var n = ITEMS.filter(function (it) { return isRated(it, state[it.item_id]); }).length;
  document.getElementById("stat").textContent = n + " / " + ITEMS.length + " rated";
  document.getElementById("missing").textContent = formatMissing(missingSummary(ITEMS, state));
  ITEMS.forEach(refreshNeeds);
}
function refreshNeeds(it) {
  var card = cardOf(it); if (!card) return;
  var hd = card.querySelector(".cardhead"); if (!hd) return;
  var b = hd.querySelector(".needsbadge"), txt = needsBadgeText(it, state[it.item_id]);
  if (!txt) { if (b) hd.removeChild(b); return; }
  if (!b) { b = document.createElement("span"); b.className = "needsbadge"; hd.appendChild(b); }
  b.textContent = txt;
}
function renderPrior(it, st) {
  var card = cardOf(it); if (!card || typeof PRIOR === "undefined" || !PRIOR) return;
  var ent = PRIOR.map[it.item_id]; if (!ent) return;
  var hd = card.querySelector(".cardhead");
  card.querySelectorAll(".priorbadge,.priorbox").forEach(function (e) { e.parentNode.removeChild(e); });
  var carried = !!(st && st.carried_from && st.carried_from["class"]);
  if (ent["class"] !== "layout_changed" && !carried) return;
  priorBadgeText(ent, st).forEach(function (t, i) {
    var sp = document.createElement("span");
    sp.className = "priorbadge" + (ent["class"] === "layout_changed" ? " layout" : "");
    sp.textContent = t + (i === 0 && st && st.edited_after_carry ? " (edited)" : "");
    hd.appendChild(sp);
  });
  var pr = ent.prior || {}, bits = ["your earlier verdict: " + (pr.heads_not_shown != null ? pr.heads_not_shown : pr.verdict)];
  (pr.rects || []).forEach(function (t) { bits.push("earlier box " + t.file_page + ":" + t.col + " y " + t.box[1] + "-" + t.box[3]); });
  if (pr.note) bits.push("earlier note: " + pr.note);
  var bx = document.createElement("div"); bx.className = "priorbox"; bx.textContent = bits.join("  |  ");
  hd.parentNode.insertBefore(bx, hd.nextSibling);
}
function snapList(fp, col, which) {
  var p = SNAP[String(fp)]; var c = p && p[col]; return (c && c[which]) || [];
}
function div(cls, css, parent, text) {
  var d = document.createElement("div"); d.className = cls;
  if (css) d.style.cssText = css;
  if (text) d.textContent = text;
  if (parent) parent.appendChild(d);
  return d;
}
function edgeTxt(label, n) {
  return label + " " + (n > 0 ? "+" : "") + n + " line" + (Math.abs(n) === 1 ? "" : "s");
}
function renderRegion(it, st) {
  var card = cardOf(it); if (!card) return;
  var rat = (st.verdict === "not_a_verse") ? null : (st.ratified || initialRatified(it));
  it.rects.forEach(function (r, i) {
    var wrap = card.querySelector('.stagewrap[data-idx="' + i + '"]'); if (!wrap) return;
    var layer = wrap.querySelector(".edit"); layer.innerHTML = "";
    var ox = r.origin[0], oy = r.origin[1], ch = r.size[1];
    var tops = snapList(r.file_page, r.col, "tops"), bots = snapList(r.file_page, r.col, "bottoms");
    tops.forEach(function (t) { if (t >= oy && t <= oy + ch) div("tick", "top:" + (t - oy) + "px", layer); });
    bots.forEach(function (t) { if (t >= oy && t <= oy + ch) div("tick b", "top:" + (t - oy) + "px", layer); });
    var b = r.box;
    div("det", "left:" + (b[0] - ox) + "px;top:" + (b[1] - oy) + "px;width:" + (b[2] - b[0]) + "px;height:" + (b[3] - b[1]) + "px", layer);
    var pent = (typeof PRIOR !== "undefined" && PRIOR) ? PRIOR.map[it.item_id] : null;
    if (pent && pent.prior) (pent.prior.rects || []).forEach(function (t) {
      if (t.file_page !== r.file_page || t.col !== r.col) return;
      var gy0 = Math.max(t.box[1], oy), gy1 = Math.min(t.box[3], oy + ch);
      var gx0 = Math.max(t.box[0], ox), gx1 = Math.min(t.box[2], ox + r.size[0]);
      if (gy1 <= gy0 || gx1 <= gx0) return;
      var g = div("ghost", "left:" + (gx0 - ox) + "px;top:" + (gy0 - oy) + "px;width:" + (gx1 - gx0) + "px;height:" + (gy1 - gy0) + "px", layer);
      var gl = document.createElement("span"); gl.textContent = "your earlier box"; g.appendChild(gl);
    });
    var lm = card.querySelector('.lm[data-idx="' + i + '"]');
    if (!rat) { if (lm) lm.textContent = "not a verse: no box"; return; }
    var q = rat[i].box;
    div("rat", "left:" + (q[0] - ox) + "px;top:" + (q[1] - oy) + "px;width:" + (q[2] - q[0]) + "px;height:" + (q[3] - q[1]) + "px", layer);
    ["top", "bottom"].forEach(function (edge) {
      var y = edge === "top" ? q[1] : q[3];
      var h = div("handle", "top:calc(" + (y - oy) + "px - 6px * var(--inv,1))", layer);
      h.dataset.edge = edge; h.dataset.kind = "region"; h.dataset.idx = String(i); h.dataset.item = it.item_id;
    });
    var tl = linesMoved(b[1], q[1], tops), bl = linesMoved(b[3], q[3], bots);
    if (lm) lm.textContent = edgeTxt("top", tl) + " / " + edgeTxt("bottom", bl) +
      (rat[i].edges.top.at_crop_limit || rat[i].edges.bottom.at_crop_limit ? "   [edge at crop limit: true edge may lie beyond]" : "");
  });
}
function renderMiss(it, st) {
  var card = cardOf(it); if (!card) return;
  var hd = card.querySelector(".cardhead"), oldb = card.querySelector(".carrybadge");
  if (oldb) oldb.parentNode.removeChild(oldb);
  if (hd && st.carried_from) {
    var bd = document.createElement("span"); bd.className = "carrybadge";
    bd.textContent = "carried from " + st.carried_from.set_sha16 + ":" + st.carried_from.item_id +
      (st.edited_after_carry ? " (edited)" : "");
    hd.appendChild(bd);
  }
  var layer = card.querySelector(".pedit"); layer.innerHTML = "";
  var m = it.miss;
  var bx = m.band, wd = m.word;
  div("bandov", "left:" + bx[0] + "px;top:" + bx[1] + "px;width:" + (bx[2] - bx[0]) + "px;height:" + (bx[3] - bx[1]) + "px", layer);
  div("wordov", "left:" + wd[0] + "px;top:" + wd[1] + "px;width:" + (wd[2] - wd[0]) + "px;height:" + (wd[3] - wd[1]) + "px", layer);
  it.page_rects.forEach(function (pr) {
    var d = div("prect", "left:" + pr.box[0] + "px;top:" + pr.box[1] + "px;width:" + (pr.box[2] - pr.box[0]) + "px;height:" + (pr.box[3] - pr.box[1]) + "px", layer);
    var sp = document.createElement("span"); sp.textContent = pr.item_id; d.appendChild(sp);
  });
  var drawn = (st.verdict === "not_a_verse") ? [] : (st.ratified || []);
  var bar = card.querySelector(".drawbar"); bar.innerHTML = "";
  drawn.forEach(function (r, i) {
    var b = r.box;
    div("rat", "left:" + b[0] + "px;top:" + b[1] + "px;width:" + (b[2] - b[0]) + "px;height:" + (b[3] - b[1]) + "px", layer);
    ["top", "bottom"].forEach(function (edge) {
      var y = edge === "top" ? b[1] : b[3];
      var h = div("handle", "top:calc(" + y + "px - 6px * var(--inv,1));left:" + b[0] + "px;width:" + (b[2] - b[0]) + "px", layer);
      h.dataset.edge = edge; h.dataset.kind = "miss"; h.dataset.idx = String(i); h.dataset.item = it.item_id;
    });
    var btn = document.createElement("button"); btn.type = "button";
    btn.textContent = "clear " + r.col + " rect [" + b.join(",") + "]";
    btn.addEventListener("click", function () { commit(it, { type: "clear", item: it, rectIdx: i }); });
    bar.appendChild(btn);
  });
  if (!drawn.length) bar.textContent = "Drag in a column of the page window below to draw the missing region (Alt = no snap).";
}
function renderItem(it, st) {
  st = st || state[it.item_id] || {};
  if (it.item_kind === "miss") renderMiss(it, st);
  else if (it.rects) renderRegion(it, st);
  renderPrior(it, st);
  refreshNeeds(it);
}
function restoreFields(it) {
  var card = cardOf(it); if (!card) return;
  var s = state[it.item_id] || {};
  card.querySelectorAll('input[type=radio]').forEach(function (r) {
    var want = r.classList.contains("causeradio") ? s.cause_verdict : s.verdict;
    r.checked = (want !== undefined && r.value === want);
  });
  if (s.note != null) { var n = card.querySelector(".note"); if (n) n.value = s.note; }
  if (s.printed_number_as_seen != null) { var p = card.querySelector(".pnumber"); if (p) p.value = s.printed_number_as_seen; }
  if (s.heads_not_shown != null) { var h = card.querySelector(".headsnotshown"); if (h) h.value = s.heads_not_shown; }
}
function commit(it, event) {
  var res = verdictCoupling(state[it.item_id] || {}, event);
  if (res.needsConfirm) {
    if (!window.confirm("Reset the ratified box to the detected box? Your moved edges will be lost.")) { restoreFields(it); return; }
    event.confirmed = true;
    res = verdictCoupling(state[it.item_id] || {}, event);
  }
  state[it.item_id] = res.state;
  if (res.state.carried_from) res.state.edited_after_carry = true;
  save(); renderItem(it); restoreFields(it);
}
document.addEventListener("change", function (e) {
  var t = e.target, card = t.closest ? t.closest(".card") : null;
  if (!card || t.type !== "radio") return;
  var it = ITEM_BY_ID[card.dataset.itemId];
  if (t.classList.contains("causeradio")) {
    var s = state[it.item_id] || (state[it.item_id] = {}); s.cause_verdict = t.value;
    if (s.carried_from) s.edited_after_carry = true;
    save(); renderItem(it); return;
  }
  commit(it, { type: "choose", value: t.value, item: it });
});
document.addEventListener("input", function (e) {
  var t = e.target, card = t.closest ? t.closest(".card") : null;
  if (!card) return;
  var s = state[card.dataset.itemId] || (state[card.dataset.itemId] = {});
  if (t.classList.contains("note")) { s.note = t.value; if (s.carried_from) s.edited_after_carry = true; }
  else if (t.classList.contains("pnumber")) s.printed_number_as_seen = t.value;
  else if (t.classList.contains("headsnotshown")) { s.heads_not_shown = t.value; if (s.carried_from) s.edited_after_carry = true; }
  save();
  if (s.carried_from) { var itx = ITEM_BY_ID[card.dataset.itemId]; if (itx) renderPrior(itx, s); }
});
// ---- fit to width: crops and page windows scale down (never up) to the card; geometry stays native px ----
var fitOn = true;
function localPt(layer, e) {
  var r = layer.getBoundingClientRect();
  var k = r.height ? layer.offsetHeight / r.height : 1;
  return { x: (e.clientX - r.left) * k, y: (e.clientY - r.top) * k };
}
function fitAll() {
  document.querySelectorAll(".stagewrap, .pwinner").forEach(function (el) {
    var w = parseFloat(el.style.width), h = parseFloat(el.style.height);
    var avail = el.parentNode.clientWidth - 20;
    var sc = (fitOn && avail > 0 && w > avail) ? avail / w : 1;
    el.style.transform = sc === 1 ? "" : "scale(" + sc + ")";
    el.style.marginRight = sc === 1 ? "" : (-w * (1 - sc)) + "px";
    el.style.marginBottom = sc === 1 ? "" : (-h * (1 - sc)) + "px";
    el.style.setProperty("--inv", String(1 / sc));
    el.dataset.scale = String(sc);
  });
}
window.addEventListener("resize", fitAll);
// ---- edge drag (region crops and drawn rects on a page window) ----
var drag = null, drawing = null;
document.addEventListener("mousedown", function (e) {
  var h = e.target;
  if (h.classList && h.classList.contains("handle")) {
    e.preventDefault();
    var it = ITEM_BY_ID[h.dataset.item], idx = Number(h.dataset.idx), kind = h.dataset.kind;
    var st = state[it.item_id] || {};
    var layer = h.parentNode;
    var box, col, fp, range, originY;
    if (kind === "region") {
      var rr = it.rects[idx]; fp = rr.file_page; col = rr.col; originY = rr.origin[1];
      range = [originY, originY + rr.size[1]];
      box = (st.ratified || initialRatified(it))[idx].box.slice();
    } else {
      var dr = st.ratified[idx]; fp = it.file_page; col = dr.col; originY = 0;
      range = [0, it.page_h]; box = dr.box.slice();
    }
    drag = { it: it, idx: idx, kind: kind, edge: h.dataset.edge, layer: layer, box: box, originY: originY, range: range,
             targets: snapList(fp, col, h.dataset.edge === "top" ? "tops" : "bottoms"), base: st };
    return;
  }
  if (h.classList && h.classList.contains("pedit")) {
    e.preventDefault();
    var it2 = ITEM_BY_ID[h.closest(".card").dataset.itemId];
    var p0 = localPt(h, e), x = p0.x, y = p0.y;
    var col2 = pageColumn(it2, x, y);
    if (!col2) { Object.keys(it2.col_boxes).forEach(function (c) { var cb = it2.col_boxes[c]; if (x >= cb[0] && x <= cb[2]) col2 = c; }); }
    var msg = h.closest(".pwwrap").querySelector(".pwmsg"); msg.textContent = "";
    if (!col2 || !it2.col_boxes[col2]) { msg.textContent = "no column extent in the geometry for that position"; return; }
    var cur = (state[it2.item_id] && state[it2.item_id].verdict !== "not_a_verse" && state[it2.item_id].ratified) || [];
    if (cur.some(function (q) { return q.col === col2; })) { msg.textContent = "the " + col2 + " column already has a drawn rect: clear it first"; return; }
    drawing = { it: it2, layer: h, col: col2, y0: y, temp: div("rat", "pointer-events:none", h) };
  }
});
document.addEventListener("mousemove", function (e) {
  if (drag) {
    var y = localPt(drag.layer, e).y + drag.originY;
    var res = applyDrag(drag.box, drag.edge, y, drag.targets, drag.range, !snapOn || e.altKey);
    drag.pending = res;
    var ev = drag.kind === "region"
      ? { type: "drag", item: drag.it, rectIdx: drag.idx, rect: res.rect, edge: drag.edge, edgeInfo: res.edgeInfo }
      : { type: "mdrag", item: drag.it, rectIdx: drag.idx, rect: res.rect, edge: drag.edge, edgeInfo: res.edgeInfo };
    renderItem(drag.it, verdictCoupling(drag.base, ev).state);
  } else if (drawing) {
    var yy = localPt(drawing.layer, e).y;
    var cb = drawing.it.col_boxes[drawing.col];
    var a = Math.min(drawing.y0, yy), b = Math.max(drawing.y0, yy);
    drawing.temp.style.cssText = "pointer-events:none;left:" + cb[0] + "px;width:" + (cb[2] - cb[0]) + "px;top:" + a + "px;height:" + (b - a) + "px";
  }
});
document.addEventListener("mouseup", function (e) {
  if (drag) {
    var d = drag; drag = null;
    var y = localPt(d.layer, e).y + d.originY;
    var res = applyDrag(d.box, d.edge, y, d.targets, d.range, !snapOn || e.altKey);
    state[d.it.item_id] = d.base;
    commit(d.it, { type: d.kind === "region" ? "drag" : "mdrag", item: d.it, rectIdx: d.idx, rect: res.rect, edge: d.edge, edgeInfo: res.edgeInfo });
  } else if (drawing) {
    var w = drawing; drawing = null;
    var yy = localPt(w.layer, e).y;
    if (w.temp.parentNode) w.temp.parentNode.removeChild(w.temp);
    if (Math.abs(yy - w.y0) < 4) return;
    var fp = w.it.file_page, cb = w.it.col_boxes[w.col];
    var nr = newRect(cb, w.y0, yy, snapList(fp, w.col, "tops"), snapList(fp, w.col, "bottoms"), [0, w.it.page_h], !snapOn || e.altKey);
    if (!nr) return;
    commit(w.it, { type: "draw", item: w.it, rect: { col: w.col, file_page: fp, box: nr.rect, edges: nr.edges } });
  }
});
// ---- init ----
fitAll();
if (CARRY) {
  var oldItems = {};
  try {
    var oraw = localStorage.getItem(CARRY.from_ui_key);   // read-only: this key is NEVER written or deleted
    if (oraw) { var oo2 = JSON.parse(oraw); if (oo2 && oo2.items) oldItems = oo2.items; }
  } catch (e) { oldItems = {}; }
  var cres = carryForward(state, oldItems, CARRY);
  state = cres.items;
  if (cres.carried.length) save();
}
var priorSeeded = [];
if (typeof PRIOR !== "undefined" && PRIOR) {
  var sres = seedPrior(state, PRIOR);
  state = sres.state; priorSeeded = sres.seeded;
  if (priorSeeded.length) save();
}
ITEMS.forEach(function (it) {
  restoreFields(it);
  renderItem(it);
  if (it.item_kind === "miss") {
    var card = cardOf(it), win = card.querySelector(".pagewin"), img = card.querySelector(".pwimg"), ban = card.querySelector(".errbanner");
    var fail = function () { ban.hidden = false; };
    img.addEventListener("error", fail);
    if (img.complete && img.naturalWidth === 0) fail();
    var psc = parseFloat(card.querySelector(".pwinner").dataset.scale || "1");
    win.scrollTop = Math.max(0, it.miss.band[1] * psc - 300);
    var cbx = it.col_boxes && it.col_boxes[it.miss.col];
    win.scrollLeft = (it.miss.col === "right" && cbx) ? Math.max(0, cbx[0] * psc - 20) : 0;
  }
});
renderCarryBanner(carryNotes());
(function () {
  if (typeof PRIOR === "undefined" || !PRIOR) return;
  var ids = Object.keys(PRIOR.map), nCarried = 0, nLayout = 0;
  ids.forEach(function (id) {
    var s = state[id]; if (s && s.carried_from && s.carried_from["class"]) nCarried++;
    if (PRIOR.map[id]["class"] === "layout_changed") nLayout++;
  });
  var ban = document.getElementById("priorbanner"); ban.hidden = false;
  var t = nCarried + " cards carry your earlier verdicts (console " + PRIOR.from_set_sha16 + "; " + priorSeeded.length +
    " seeded just now); " + nLayout + " cards changed layout and need a fresh verdict.";
  var un = (typeof PRIOR_REPORT !== "undefined" && PRIOR_REPORT && PRIOR_REPORT.old_unmatched) || [];
  if (un.length) t += " Retired (no matching card, not carried): " + un.map(function (u) { return u.item_id + " (" + u.verdict + ")"; }).join(", ") + ".";
  ban.textContent = t;
})();
var nextCursor = null;
document.getElementById("nextinc").addEventListener("click", function () {
  var order = Array.prototype.map.call(document.querySelectorAll(".card"), function (c) { return ITEM_BY_ID[c.dataset.itemId]; }).filter(Boolean);
  var id = nextIncompleteId(order, state, nextCursor);
  if (!id) { document.getElementById("missing").textContent = "all complete"; return; }
  nextCursor = id;
  var hdr = document.querySelector("header"), off = hdr ? hdr.getBoundingClientRect().height : 0;
  window.scrollTo(0, cardOf(ITEM_BY_ID[id]).getBoundingClientRect().top + window.pageYOffset - off - 6);
});
var snapBox = document.getElementById("snap");
snapBox.checked = snapOn;
snapBox.addEventListener("change", function () { snapOn = snapBox.checked; save(); });
var fitBox = document.getElementById("fit");
fitBox.addEventListener("change", function () { fitOn = fitBox.checked; fitAll(); });
renderStat();
function download(name, text) {
  var a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: "application/x-ndjson" }));
  a.download = name; a.click();
}
document.getElementById("export").addEventListener("click", function () {
  var consts = { SNAP: SNAP, set_sha16: SET_SHA16, ui_config_hash: UI_CONFIG_HASH, run_config_hash: RUN_CONFIG_HASH,
                 exported_utc: new Date().toISOString() };
  download(EXPORT_FILENAME, ITEMS.map(function (it) { return JSON.stringify(buildExportRow(it, state[it.item_id], consts)); }).join("\n"));
});
try {
  var old = localStorage.getItem(LS1_KEY);
  if (old) {
    var oo = JSON.parse(old), ids = Object.keys(oo || {});
    if (ids.length) {
      var mb = document.getElementById("mig");
      mb.hidden = false;
      mb.querySelector("span").textContent = ids.length + " items have verdicts from the earlier verdict-only console; they are NOT restored here";
      mb.querySelector("button").addEventListener("click", function () {
        download(EXPORT1_FILENAME, ids.map(function (id) { return JSON.stringify({ item_id: id, state: oo[id] }); }).join("\n"));
      });
    }
  }
} catch (e) {}
"""


def _render_html_ui2(set_sha, items_for_js, run_config_hash, ui_config_hash, snap, cards_html_list, ui_js_text,
                     carry=None, carry_lists=None, prior=None, prior_lists=None):
    ls_key = "versetruth_" + set_sha + "_ui2"
    ls1_key = "versetruth_" + set_sha
    export_filename = f"verse_box_verdicts_{set_sha}_ui2.jsonl"
    export1_filename = f"verse_box_verdicts_{set_sha}_ui1.jsonl"
    cards = "\n".join(cards_html_list)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Verse-box truth console -- step 3 -- UI 2 -- {set_sha}</title>
<style>{_CSS}{_CSS_UI2}</style></head><body>
<header><h1>Verse-box truth console (place boxes)</h1>
<span id="stat"></span><span id="missing"></span><button id="nextinc" type="button">Next incomplete</button><label class="snap"><input type="checkbox" id="snap" checked> Snap</label><label class="snap"><input type="checkbox" id="fit" checked> Fit width</label>
<button id="export" type="button">Export verdicts JSONL</button></header>
<div class="carrybanner" id="carrybanner" hidden></div>
<div class="carrybanner" id="priorbanner" hidden></div>
<div class="migbanner" id="mig" hidden><span></span><button type="button">download them as ui1 JSONL</button></div>
<main id="cards">
{cards}
</main>
<script>
const SET_SHA16 = {json.dumps(set_sha)};
const LS_KEY = {json.dumps(ls_key)};
const LS1_KEY = {json.dumps(ls1_key)};
const EXPORT_FILENAME = {json.dumps(export_filename)};
const EXPORT1_FILENAME = {json.dumps(export1_filename)};
const RUN_CONFIG_HASH = {json.dumps(run_config_hash)};
const UI_CONFIG_HASH = {json.dumps(ui_config_hash)};
const SNAP = {json.dumps(snap)};
const CARRY = {json.dumps(carry, ensure_ascii=False, sort_keys=True)};
const CARRY_REPORT = {json.dumps(carry_lists, ensure_ascii=False, sort_keys=True)};
const PRIOR = {json.dumps(prior, ensure_ascii=False, sort_keys=True)};
const PRIOR_REPORT = {json.dumps(prior_lists, ensure_ascii=False, sort_keys=True)};
const ITEMS = {json.dumps(items_for_js, ensure_ascii=False)};
{ui_js_text}
{_JS_UI2_GLUE}
</script>
</body></html>"""


def _read_manifest(manifest_path):
    lines = [json.loads(l) for l in Path(manifest_path).read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines or lines[0].get("kind") != "console_header":
        raise ValueError(f"manifest {manifest_path} does not start with a console_header")
    return lines


def _find_console_dir(out_root, console_dir):
    if console_dir:
        return Path(console_dir)
    cands = [d for d in Path(out_root).iterdir() if d.is_dir() and (d / "manifest.jsonl").exists()]
    if len(cands) != 1:
        raise ValueError(f"cannot pick a console dir under {out_root}: {len(cands)} candidates; pass --console-dir")
    return cands[0]


def _next_ui_name(out_dir):
    k = 1
    while (out_dir / f"index_ui{k}.html").exists():
        k += 1
    return f"index_ui{k}.html"


def compute_snap_targets(items, geometry_by_fp, volume_dir, image_cache=None):
    """Returns (SNAP, coincidence, page_dims). SNAP = {str(fp): {left|right|full: {tops, bottoms}}}.
    Band-edge sets from VR.analyze_page_s1, then every detected rect's own y0/y1 added for its
    page/col (so 'back to as_detected' is always reachable). coincidence counts, BEFORE the addition,
    how many rect tops/bottoms already sit on a band edge."""
    image_cache = {} if image_cache is None else image_cache
    fps = set()
    for it in items:
        fps.add(it["file_page"])
        for r in it.get("rects") or []:
            fps.add(r["file_page"])
    edges = {}
    dims = {}
    for fp in sorted(fps):
        geom = geometry_by_fp.get(fp)
        if geom is None:
            raise ValueError(f"no geometry record for file page {fp}")
        arr, W, H = _get_page_gray(fp, volume_dir, image_cache)
        dims[fp] = (W, H)
        s1 = VR.analyze_page_s1(VR.page_ink(arr), geom)
        full_t = {b["y0"] for b in s1["full"]}
        full_b = {b["y1"] for b in s1["full"]}
        per = {}
        for col in ("left", "right"):
            per[col] = {"tops": {b["y0"] for b in s1[col]} | full_t, "bottoms": {b["y1"] for b in s1[col]} | full_b}
        per["full"] = {"tops": per["left"]["tops"] | per["right"]["tops"],
                       "bottoms": per["left"]["bottoms"] | per["right"]["bottoms"]}
        edges[fp] = per
    hit_t = hit_b = n = 0
    for it in items:
        if it["item_kind"] not in REGION_KINDS:
            continue
        for r in it["rects"]:
            per = edges[r["file_page"]][r["col"]]
            n += 1
            hit_t += r["box"][1] in per["tops"]
            hit_b += r["box"][3] in per["bottoms"]
    for it in items:
        if it["item_kind"] not in REGION_KINDS:
            continue
        for r in it["rects"]:
            per = edges[r["file_page"]][r["col"]]
            per["tops"].add(r["box"][1])
            per["bottoms"].add(r["box"][3])
    snap = {str(fp): {col: {"tops": sorted(int(v) for v in v2["tops"]), "bottoms": sorted(int(v) for v in v2["bottoms"])}
                      for col, v2 in per.items()} for fp, per in edges.items()}
    return snap, {"tops": [int(hit_t), n], "bottoms": [int(hit_b), n]}, dims


def html_only(run_path, misses_path, geometry_path, volume_dir, out_root, console_dir=None, force=False,
              module_path=None, carry_from=None, prior_export=None, prior_run=None):
    """Rebuild ONLY index.html (UI 2) for an existing console. Verifies the crops against the
    manifest first; raises (writing nothing) on any mismatch."""
    run_path, misses_path, geometry_path = Path(run_path), Path(misses_path), Path(geometry_path)
    volume_dir, out_root = Path(volume_dir), Path(out_root)
    module_path = Path(module_path).resolve() if module_path else Path(__file__).resolve()
    ui_js_path = _ui_js_path(module_path)

    out_dir = _find_console_dir(out_root, console_dir)
    manifest_path = out_dir / "manifest.jsonl"
    mlines = _read_manifest(manifest_path)
    header = mlines[0]
    man_items = {l["item_id"]: l for l in mlines if l.get("kind") == "item"}

    run_records = load_run_records(run_path)
    misses_doc = load_misses(misses_path)
    geometry_by_fp = load_geometry_by_fp(geometry_path)
    page_by_fp = page_records_by_fp(run_records)
    run_header = next((r for r in run_records if r.get("kind") == "run_header"), None)
    run_config_hash = (run_header.get("config") or {}).get("hash") if run_header else None
    check_misses_not_stale(run_records, misses_doc)
    items = build_items(run_records, misses_doc)

    if {it["item_id"] for it in items} != set(man_items):
        raise ValueError("recomputed item ids differ from the manifest's")
    item_shas, crop_meta_by_id = {}, {}
    for it in items:
        ml = man_items[it["item_id"]]
        expected_n = len(it["rects"]) if it["item_kind"] in REGION_KINDS else (1 if it["item_kind"] == "miss" else 0)
        if len(ml["crops"]) != expected_n:
            raise ValueError(f"{it['item_id']}: manifest has {len(ml['crops'])} crops, expected {expected_n}")
        for c in ml["crops"]:
            cp = out_dir / c["path"]
            if not cp.exists():
                raise ValueError(f"crop file missing: {cp}")
            if _sha16_bytes(cp.read_bytes()) != c["crop_sha16"]:
                raise ValueError(f"crop file sha mismatch: {cp}")
        sha = item_sha16(it, [c["crop_sha16"] for c in ml["crops"]])
        if sha != ml["item_sha16"]:
            raise ValueError(f"{it['item_id']}: recomputed item_sha16 {sha} != manifest {ml['item_sha16']}")
        item_shas[it["item_id"]] = sha
        crop_meta_by_id[it["item_id"]] = ml["crops"]
    set_sha = set_sha16(item_shas.items())
    if set_sha != header.get("set_sha16") or set_sha != out_dir.name:
        raise ValueError(f"set_sha16 mismatch: recomputed {set_sha}, manifest {header.get('set_sha16')}, dir {out_dir.name}")

    if bool(prior_export) != bool(prior_run):
        raise ValueError("--prior-export and --prior-run go together")
    prior, prior_sha, prior_counts, prior_lists = None, None, None, None
    if prior_export:
        prior, prior_sha, prior_counts, prior_lists = prior_from_paths(prior_export, prior_run, run_records, items)
    image_cache = {}
    carry, carry_sha, carry_counts, carry_lists = None, None, None, None
    if carry_from:
        carry, carry_sha, carry_counts, carry_lists = carry_from_console(carry_from, items, item_shas)
    snap, coincidence, dims = compute_snap_targets(items, geometry_by_fp, volume_dir, image_cache)
    snap_sha = _sha16_json(snap)

    ui_js_text = ui_js_path.read_text(encoding="utf-8")
    module_sha256 = BVR.compute_module_sha256(module_path)
    ui_js_sha256 = BVR.compute_module_sha256(ui_js_path)
    config_hash = _sha16_json({"ui_version": UI_VERSION, "module_sha256": module_sha256,
                               "ui_js_sha256": ui_js_sha256, "snap_targets_sha16": snap_sha, "set_sha16": set_sha,
                               "carry_map_sha16": carry_sha, "prior_map_sha16": prior_sha})

    index_path = out_dir / "index.html"
    last = mlines[-1]
    if (not force and last.get("kind") == "html_rebuild" and last.get("config_hash") == config_hash
            and index_path.exists()):
        raise RefuseOverwrite(f"REFUSED: html_rebuild with identical config_hash {config_hash} is already the last "
                              f"manifest line and index.html exists. Pass --force to rebuild anyway.")

    # ---- build everything in memory first ----
    rects_by_fp = {}
    for it in items:
        if it["item_kind"] in REGION_KINDS:
            for r in it["rects"]:
                rects_by_fp.setdefault(r["file_page"], []).append({"item_id": it["item_id"], "col": r["col"], "box": r["box"]})
    cards_by_fp, items_for_js = {}, []
    for it in items:
        kind = it["item_kind"]
        cms = crop_meta_by_id[it["item_id"]]
        rels = [c["path"] for c in cms]
        entry = {"item_id": it["item_id"], "item_kind": kind, "file_page": it["file_page"],
                 "printed_page": it["file_page"] - 88, "item_sha16": item_shas[it["item_id"]]}
        if kind in REGION_KINDS:
            crops, overlays = [], []
            for r, c in zip(it["rects"], cms):
                origin, size = tuple(c["crop_origin"]), tuple(c["crop_size"])
                crops.append({"crop_size": list(size), "clamped_edges": c["clamped_edges"], "rect": c["rect"],
                              "file_page": r["file_page"], "col": r["col"]})
                overlays.append(_region_overlays(it, r, origin, size))
            entry["rects"] = [{"file_page": r["file_page"], "col": r["col"], "box": r["box"],
                               "origin": c["crop_origin"], "size": c["crop_size"]} for r, c in zip(it["rects"], cms)]
            card = _region_card(it, crops, overlays, rels, volume_dir, crop_fn=_crop_html_ui2,
                                fieldset_fn=_verdict_fieldset_ui2)
        elif kind == "miss":
            c = cms[0]
            origin, size = tuple(c["crop_origin"]), tuple(c["crop_size"])
            crop = {"crop_size": list(size), "clamped_edges": c["clamped_edges"], "rect": c["rect"],
                    "file_page": it["file_page"], "col": it["miss"].get("col")}
            ov = _miss_overlays(it, geometry_by_fp, origin, size, page_by_fp)
            geom = geometry_by_fp[it["file_page"]]
            W, H = dims[it["file_page"]]
            entry["miss"] = {"band": it["miss"]["band"], "word": it["miss"]["word"], "col": it["miss"].get("col")}
            entry["page_w"], entry["page_h"] = int(W), int(H)
            entry["xdiv"] = geom.get("xdiv")
            entry["col_boxes"] = {r["col"]: r["box"] for r in geom.get("body_regions", []) if r.get("col") in ("left", "right")}
            _sp = _ok_split(page_by_fp, it["file_page"])
            if _sp is not None:
                entry["col_boxes"] = {c: list(b) for c, b in ((page_by_fp[it["file_page"]].get("col_boxes")) or {}).items()} or entry["col_boxes"]
                entry["col_split"] = {"slope": _sp["slope"], "c0": _sp["c0"]}
            entry["page_rects"] = rects_by_fp.get(it["file_page"], [])
            card = _miss_card(it, crop, ov, rels[0], volume_dir, extra_html=_pagewin_html(it, volume_dir, W, H),
                              fieldset_fn=_verdict_fieldset_ui2)
        else:
            card = _page_card(it, volume_dir)
        items_for_js.append(entry)
        grp = cards_by_fp.setdefault(it["file_page"], {"region": [], "miss": [], "page": None})
        if kind in REGION_KINDS:
            _add_region_card(grp, kind, card)
        elif kind == "miss":
            grp["miss"].append(card)
        else:
            grp["page"] = card
    all_cards = []
    for fp in sorted(cards_by_fp):
        grp = cards_by_fp[fp]
        all_cards.extend(grp["region"]); all_cards.extend(grp["miss"])
        if grp["page"]:
            all_cards.append(grp["page"])
    html_text = _render_html_ui2(set_sha, items_for_js, run_config_hash, config_hash, snap, all_cards, ui_js_text,
                                 carry=carry, carry_lists=carry_lists, prior=prior, prior_lists=prior_lists)

    miss_fps = sorted({it["file_page"] for it in items if it["item_kind"] == "miss"})
    page_png_sha256 = {str(fp): _sha256_file(volume_dir / f"page{fp}_image1.png") for fp in miss_fps}
    repo_root = module_path.parents[2]
    renamed_to = _next_ui_name(out_dir) if index_path.exists() else None
    rec = {
        "kind": "html_rebuild", "ui_version": UI_VERSION, "tier": "best_effort", "config_hash": config_hash,
        "git_head": BVR.get_git_head(repo_root), "git_dirty": BVR.get_git_dirty(repo_root),
        "started_utc": _utc_now_iso(), "snap_targets_sha16": snap_sha, "snap_edge_coincidence": coincidence,
        "page_png_sha256": page_png_sha256, "prior_index_renamed_to": renamed_to, "set_sha16": set_sha,
        "carry_from": str(carry_from) if carry_from else None,
        "carry_from_set_sha16": carry["from_set_sha16"] if carry else None,
        "carry_map_sha16": carry_sha, "carry_counts": carry_counts,
        "carry_identity_conflict": carry_lists["identity_conflict"] if carry_lists else None,
        "carry_old_unmatched": carry_lists["old_unmatched"] if carry_lists else None,
        "carry_new_unmatched": carry_lists["new_unmatched"] if carry_lists else None,
        **_prior_manifest_fields(prior_export, prior_run, prior, prior_sha, prior_counts, prior_lists),
    }
    # ---- write order: manifest line FIRST, then rename, then the new index.html ----
    text = manifest_path.read_text(encoding="utf-8")
    with open(manifest_path, "a", encoding="utf-8", newline="\n") as f:
        if text and not text.endswith("\n"):
            f.write("\n")
        f.write(json.dumps(rec, sort_keys=True) + "\n")
    if renamed_to:
        index_path.rename(out_dir / renamed_to)
    with open(index_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(html_text)
    return {"out_dir": out_dir, "set_sha16": set_sha, "config_hash": config_hash, "snap": snap,
            "snap_edge_coincidence": coincidence, "html_bytes": len(html_text.encode("utf-8")),
            "renamed_to": renamed_to, "manifest_record": rec, "carry": carry, "prior": prior}


# ==================================================================================================
# CLI
# ==================================================================================================

def build_arg_parser():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default=DEFAULT_RUN)
    ap.add_argument("--misses", default=DEFAULT_MISSES)
    ap.add_argument("--geometry", default=DEFAULT_GEOMETRY)
    ap.add_argument("--volume-dir", default=DEFAULT_VOLUME_DIR)
    ap.add_argument("--out-root", default=DEFAULT_OUT_ROOT)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--html-only", action="store_true",
                    help="rebuild only index.html (UI 2: box placement) for an existing console; crops are verified, never rewritten")
    ap.add_argument("--carry-from", default=None,
                    help="OLD console dir: carry its miss-card diagnoses (cause verdict + note) by heading identity "
                         "(valid with --html-only or --carry-dry-run; refused for a fresh build)")
    ap.add_argument("--carry-dry-run", action="store_true",
                    help="with --carry-from: print the carry classification for (old dir, --misses) and write nothing")
    ap.add_argument("--prior-export", default=None,
                    help="OLD console's UI2 export JSONL: its region/page verdicts are carried by heading identity (needs --prior-run)")
    ap.add_argument("--prior-run", default=None, help="the run JSONL the old console was built from (needs --prior-export)")
    ap.add_argument("--prior-dry-run", action="store_true",
                    help="print the prior classification for (--prior-export, --prior-run, --run) and write nothing")
    ap.add_argument("--console-dir", default=None, help="existing console dir (default: the only one under --out-root)")
    return ap


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    if bool(args.prior_export) != bool(args.prior_run):
        print("--prior-export and --prior-run go together", file=sys.stderr)
        return 2
    if args.prior_dry_run:
        if not args.prior_export:
            print("--prior-dry-run needs --prior-export and --prior-run", file=sys.stderr)
            return 2
        recs = load_run_records(args.run)
        items = build_items(recs, load_misses(args.misses))
        try:
            prior, sha, counts, lists = prior_from_paths(args.prior_export, args.prior_run, recs, items)
        except ValueError as e:
            print(f"REFUSED: {e}", file=sys.stderr)
            return 2
        print(f"from_set_sha16: {prior['from_set_sha16']}  prior_map_sha16: {sha}")
        print(f"prior_counts: {counts}")
        print(f"lists: {lists}")
        return 0
    if args.carry_dry_run:
        if not args.carry_from:
            print("--carry-dry-run needs --carry-from", file=sys.stderr)
            return 2
        old_set, old_entries = read_old_console(args.carry_from)
        mdoc = load_misses(args.misses)
        items = [{"item_id": f"m:{m['fp']}:{m['word'][1]}", "item_kind": "miss", "file_page": m["fp"], "miss": m}
                 for m in mdoc["misses"]]
        carry, counts, lists = compute_carry(old_set, old_entries, new_miss_entries(items))
        print(f"from_set_sha16: {old_set}  carry_map_sha16: {_sha16_json(carry)}")
        print(f"carry_counts: {counts}")
        print(f"lists: {lists}")
        return 0
    if args.carry_from and not args.html_only:
        print("--carry-from is not valid for a fresh build: build first, then --html-only --carry-from <old dir>",
              file=sys.stderr)
        return 2
    if args.html_only:
        try:
            r = html_only(args.run, args.misses, args.geometry, args.volume_dir, args.out_root,
                          console_dir=args.console_dir, force=args.force, carry_from=args.carry_from,
                          prior_export=args.prior_export, prior_run=args.prior_run)
        except RefuseOverwrite as e:
            print(str(e), file=sys.stderr)
            return 2
        print(f"out_dir: {r['out_dir']}")
        print(f"set_sha16: {r['set_sha16']}  ui config_hash: {r['config_hash']}")
        print(f"snap edge coincidence (rect tops/bottoms on a band edge): {r['snap_edge_coincidence']}")
        print(f"prior index renamed to: {r['renamed_to']}")
        print(f"html size: {r['html_bytes'] / 1024:.1f} KB")
        return 0
    try:
        result = build(args.run, args.misses, args.geometry, args.volume_dir, args.out_root, force=args.force,
                       prior_export=args.prior_export, prior_run=args.prior_run)
    except RefuseOverwrite as e:
        print(str(e), file=sys.stderr)
        return 2

    crops_bytes = sum(f.stat().st_size for f in result["crops_dir"].glob("*.png"))
    print(f"out_dir: {result['out_dir']}")
    print(f"n_items by kind: {result['n_items_by_kind']}")
    print(f"n_crops: {result['n_crops']}  n_clamped: {result['n_clamped']}")
    print(f"html size: {result['html_bytes'] / 1024:.1f} KB")
    print(f"crops dir total: {crops_bytes / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
