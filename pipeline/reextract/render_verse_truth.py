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
       [--geometry ...] [--volume-dir ...] [--out-root ...] [--force]
"""
import argparse
import datetime
import hashlib
import html as html_mod
import io
import json
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
        ov = [{"kind": "rect", "box": rect_local, "label": f"rect col={rect['col']}", "color": "accent"}]
        if head and head.get("box") and head.get("col") == rect["col"] and head.get("file_page") == fp:
            head_local = overlay(head["box"], origin, crop_size)
            ov.append({"kind": "head", "box": head_local, "label": "head", "color": "head"})
        png_bytes = _encode_png(sub)
        crops.append({
            "idx": idx, "png_bytes": png_bytes, "crop_sha16": _sha16_bytes(png_bytes),
            "crop_origin": list(origin), "crop_size": list(crop_size),
            "clamped_edges": clamped_edges, "rect": rect["box"], "ink_frac": ink_frac,
            "file_page": fp, "col": rect["col"],
        })
        overlays_per_crop.append(ov)
    return crops, overlays_per_crop


def _render_miss_crop(item, geometry_by_fp, volume_dir, image_cache):
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

    ov = [{"kind": "band", "box": band_local, "label": "band", "color": "accent"}]
    word_local = overlay(m["word"], origin, crop_size)
    ov.append({"kind": "word", "box": word_local, "label": "tess word", "color": "head"})

    geom = geometry_by_fp.get(fp)
    xdiv = geom.get("xdiv") if geom else None
    if xdiv is not None:
        local_x = xdiv - origin[0]
        if 0 <= local_x <= crop_size[0]:
            ov.append({"kind": "vline", "x": local_x, "label": "xdiv", "color": "xdiv"})

    inset_px = m.get("inset_px")
    col_left_x = m.get("col_left_x")
    if inset_px is not None and col_left_x is not None:
        line_x_page = band[0] + inset_px + col_left_x
        local_x2 = line_x_page - origin[0]
        if 0 <= local_x2 <= crop_size[0]:
            ov.append({"kind": "vline", "x": local_x2, "label": "measured left ink", "color": "measured"})

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


def _crop_html(crop, overlays, rel_path):
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


def _region_card(item, crops, overlays, crop_rel_paths, volume_dir):
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

    crops_html = "".join(_crop_html(c, ov, rel) for c, ov, rel in zip(crops, overlays, crop_rel_paths))
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
{_verdict_fieldset(item)}
</section>'''


def _miss_card(item, crop, overlays, crop_rel_path, volume_dir):
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
{_verdict_fieldset(item)}
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


def _utc_now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ==================================================================================================
# build (the orchestrator -- the only thing that touches images/disk, besides the loaders above)
# ==================================================================================================

def build(run_path, misses_path, geometry_path, volume_dir, out_root, force=False, module_path=None):
    run_path = Path(run_path)
    misses_path = Path(misses_path)
    geometry_path = Path(geometry_path)
    volume_dir = Path(volume_dir)
    out_root = Path(out_root)
    module_path = Path(module_path).resolve() if module_path else Path(__file__).resolve()

    run_records = load_run_records(run_path)
    misses_doc = load_misses(misses_path)
    geometry_by_fp = load_geometry_by_fp(geometry_path)

    run_header = next((r for r in run_records if r.get("kind") == "run_header"), None)
    run_config_hash = (run_header.get("config") or {}).get("hash") if run_header else None

    items = build_items(run_records, misses_doc)

    image_cache = {}
    n_clamped = 0
    n_crops = 0
    rendered = {}

    for item in items:
        kind = item["item_kind"]
        if kind in REGION_KINDS:
            crops, overlays = _render_region_crops(item, volume_dir, image_cache)
        elif kind == "miss":
            crop, ov = _render_miss_crop(item, geometry_by_fp, volume_dir, image_cache)
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
            grp["region"].append(card_html)
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
    return ap


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    try:
        result = build(args.run, args.misses, args.geometry, args.volume_dir, args.out_root, force=args.force)
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
