"""body_bottom -- the body-rect bottom fix (Lane A2, ruling #8 item 1).

Stage-1 geometry gives a body region the page bottom (y1_source "page_bottom_no_rule") whenever
presplit.find_hrule finds no separator rule in that column, so the stage-2 body read can run into the
footnote strip. This module derives a separate, additive geometry file in which such a column gets
(A) a rule found by a SEEDED search (the other column's rule, +-WIN) or a PAIRED search (neither column
ruled), else (B) the foot-furniture strip (indented, narrow trailing lines), else it abstains and says so.
The input geometry is never edited; rules, fn_gutter and the notes strips are not touched (Lane B's).

Pure functions: row_max_runs, col_bounds, two_modes, seeded_rule, paired_rule, column_lines, foot_strip.
Library for stage 2: load_bottoms, clamp_rect.
CLI: python body_bottom.py derive --geometry G --volume-dir V --pages P... --out OUT

Exit codes: 0 clean, 2 refused (nothing written). Any exception leaves neither OUT nor OUT.tmp.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_verse_regions as BVR  # noqa: E402
import note_start_detect as NSD  # noqa: E402
from cv_footnote_presplit import _dark  # noqa: E402

DARK_THR = 70
BAND_LO_FRAC = 0.45          # candidate rows for an unseeded / paired search start here
TEXT_LO_FRAC = 0.15          # the body band for the text-run mode starts here
RULE_CLEAR_PX = 30
T_BIN = 50
FOOT_BIN = 0.05
FOOT_MIN_SEP = 0.25
FOOT_LINES_MIN = 4


class Refused(Exception):
    """A derive refusal: exit 2, nothing written."""


# ---------------------------------------------------------------------------
# pure functions
# ---------------------------------------------------------------------------

def row_max_runs(mask):
    """Longest run of True per row of a 2D bool array (vectorised)."""
    h, w = mask.shape
    pad = np.zeros((h, w + 2), dtype=np.int8)
    pad[:, 1:-1] = mask
    d = np.diff(pad, axis=1)
    sr, sc = np.where(d == 1)
    er, ec = np.where(d == -1)
    out = np.zeros(h, dtype=np.int64)
    if len(sr):
        np.maximum.at(out, sr, ec - sc)   # starts/ends pair up row-major
    return out


def col_bounds(W, xdiv):
    """The exact bounds cv_footnote_presplit.presplit gives find_hrule."""
    return {"left": (int(W * 0.03), xdiv - int(W * 0.02)),
            "right": (xdiv + int(W * 0.02), W - int(W * 0.03))}


def two_modes(vals, width, lo=0.0, min_sep=0.0):
    """(threshold | None, hist list, [m1, m2] bin indices | None).

    Bins np.arange(lo, max(vals)+2*width, width). A local max is a bin with count > 0, count >= its
    left neighbour and count > its right neighbour (an edge bin has a lower neighbour outside); an
    empty bin is never a mode. Modes sort by count descending, ties by the lower index; m1 is the
    first, m2 the first later one at least max(min_sep, 2*width) from m1. threshold = the mean of the
    two bin centres; None when there is no second mode."""
    vals = np.asarray(list(vals), dtype=np.float64)
    if vals.size == 0:
        return None, [], None
    edges = np.arange(lo, float(vals.max()) + 2 * width, width)
    hist = np.histogram(vals, bins=edges)[0].astype(int).tolist()
    n = len(hist)
    maxima = []
    for i, c in enumerate(hist):
        if c <= 0:
            continue
        left = hist[i - 1] if i > 0 else -1
        right = hist[i + 1] if i < n - 1 else -1
        if c >= left and c > right:
            maxima.append(i)
    maxima.sort(key=lambda i: (-hist[i], i))
    if not maxima:
        return None, hist, None
    m1 = maxima[0]
    sep_bins = int(np.ceil(max(min_sep, 2 * width) / width - 1e-9))
    for m2 in maxima[1:]:
        if abs(m2 - m1) >= sep_bins:
            c1 = lo + (m1 + 0.5) * width
            c2 = lo + (m2 + 0.5) * width
            return (c1 + c2) / 2.0, hist, [m1, m2]
    return None, hist, None


def seeded_rule(runs, seed, win, T):
    """The TOPMOST y in [max(0, seed-win), min(H-1, seed+win)] with runs[y] > T, else None."""
    H = len(runs)
    lo, hi = max(0, int(seed) - int(win)), min(H - 1, int(seed) + int(win))
    for y in range(lo, hi + 1):
        if runs[y] > T:
            return y
    return None


def paired_rule(runs_l, runs_r, H, win, T):
    """((yl, yr) | None, reason). Candidate rows per column: y in [int(0.45H), H) with run > T; a pair
    is |yl - yr| <= win. A pair gives (min yl over the paired, min yr over the paired), "paired";
    else "unpaired_candidate" if either column has a candidate, else "no_candidate"."""
    lo = int(BAND_LO_FRAC * H)
    cl = [y for y in range(lo, H) if runs_l[y] > T]
    cr = [y for y in range(lo, H) if runs_r[y] > T]
    pl, pr = set(), set()
    for yl in cl:
        for yr in cr:
            if abs(yl - yr) <= win:
                pl.add(yl)
                pr.add(yr)
    if pl:
        return (min(pl), min(pr)), "paired"
    return None, ("unpaired_candidate" if (cl or cr) else "no_candidate")


def column_lines(gray, x0, x1):
    """[[y0, y1, ink_x0, ink_x1], ...]: the pipeline's own line finder over the column, ink columns
    offset by x0; a band with no ink is skipped."""
    ink = gray[:, x0:x1] < NSD.INK
    out = []
    for a, e in NSD.text_lines(ink):
        cols = np.where(ink[a:e].any(axis=0))[0]
        if len(cols):
            out.append([int(a), int(e), int(x0 + cols[0]), int(x0 + cols[-1] + 1)])
    return out


def foot_offsets_widths(lines, colw):
    """(offsets, widths) of every line, relative to the column's median ink_x0."""
    x0_med = float(np.median([l[2] for l in lines]))
    return ([(l[2] - x0_med) / colw for l in lines], [(l[3] - l[2]) / colw for l in lines])


def foot_strip(lines, colw, T_O, T_W):
    """(n, y1 | None, bands). Walk up from the last line while n < len(lines)-1, stripping a line whose
    left offset >= T_O and width <= T_W; stop at the first that fails. y1 is the midpoint of the gap
    between the last kept line and the first stripped band. Needs >= 4 lines, else (0, None, [])."""
    if len(lines) < FOOT_LINES_MIN:
        return 0, None, []
    x0_med = float(np.median([l[2] for l in lines]))
    n = 0
    while n < len(lines) - 1:
        l = lines[-1 - n]
        if (l[2] - x0_med) / colw >= T_O and (l[3] - l[2]) / colw <= T_W:
            n += 1
        else:
            break
    if n == 0:
        return 0, None, []
    y1 = (lines[-1 - n][1] + lines[-n][0]) // 2
    return n, y1, [list(l) for l in lines[len(lines) - n:]]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def read_geometry(path, pages):
    """{file_page: record} for the requested pages; a missing page is a refusal."""
    want = set(pages)
    got = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            g = json.loads(line)
            fp = g.get("file_page")
            if fp in want and fp not in got:
                got[fp] = g
    missing = [p for p in pages if p not in got]
    if missing:
        raise Refused(f"geometry has no record for pages {missing}")
    return got


def _runs_for(dark, bounds, col):
    x0, x1 = bounds[col]
    return row_max_runs(dark[:, x0:x1] > DARK_THR)


def _modal_size(sizes):
    return Counter(sizes.values()).most_common(1)[0][0]


# ---------------------------------------------------------------------------
# derive
# ---------------------------------------------------------------------------

def derive(geometry_path, volume_dir, pages, out_path):
    """Build the derived file at out_path (via out_path.tmp). Returns the run_summary dict."""
    geom = read_geometry(geometry_path, pages)
    sizes = {}
    for fp in pages:
        from PIL import Image
        with Image.open(Path(volume_dir) / geom[fp]["image"]) as im:
            sizes[fp] = tuple(im.size)
    modal = _modal_size(sizes)
    modal_pages = [fp for fp in pages if sizes[fp] == modal]

    rule_gaps = []
    for fp in modal_pages:
        r = geom[fp].get("rules") or [None, None]
        if len(r) == 2 and r[0] is not None and r[1] is not None:
            rule_gaps.append(abs(r[0] - r[1]))
    if not rule_gaps:
        raise Refused("no modal page has two rules: WIN underivable")
    WIN = int(max(rule_gaps))

    # ---- one image pass over the modal pages ----
    from PIL import Image
    text_max_all, sw_all = [], []
    stash = {}   # fp -> {"H", "runs": {col: arr}, "lines": {col: [...]}, "seed": {col: int}, "colw": {col: int}}
    for fp in modal_pages:
        g = geom[fp]
        regs = {b["col"]: b for b in g["body_regions"]}
        no_rule = [c for c, b in regs.items() if b["y1_source"] == "page_bottom_no_rule"]
        with Image.open(Path(volume_dir) / g["image"]) as im:
            W, H = im.size
            dark = _dark(im)
            gray = np.asarray(im.convert("L")) if no_rule else None
        bounds = col_bounds(W, g["xdiv"])
        runs = {c: _runs_for(dark, bounds, c) for c in regs}
        for c, b in regs.items():
            if b["y1_source"] != "page_bottom_no_rule" and b.get("rule_y") is not None:
                lo = int(TEXT_LO_FRAC * H)
                hi = max(lo + 1, b["rule_y"] - RULE_CLEAR_PX)
                text_max_all.append(int(runs[c][lo:hi].max()))
        st = {"H": H, "runs": {c: runs[c] for c in no_rule}, "lines": {}, "seed": {}, "colw": {}}
        for c in no_rule:
            other = "right" if c == "left" else "left"
            ob = regs.get(other)
            if ob is not None and ob.get("rule_y") is not None:
                seed = int(ob["rule_y"])
            else:
                lo = int(BAND_LO_FRAC * H)
                seed = int(lo + int(np.argmax(runs[other][lo:H])))
                st["runs"].setdefault(other, runs[other])
            a, e = max(0, seed - WIN), min(H, seed + WIN + 1)
            sw_all.append(int(runs[c][a:e].max()))
            st["seed"][c] = seed
            x0, x1 = bounds[c]
            st["colw"][c] = x1 - x0
            st["lines"][c] = column_lines(gray, x0, x1)
        stash[fp] = st
        del dark, gray

    T, hist_T, modes_T = two_modes(text_max_all + sw_all, T_BIN)
    if T is None:
        raise Refused("T underivable: no second mode in the run-length histogram")

    # ---- rule search ----
    results = {}   # (fp, col) -> dict
    page_flags = {fp: [] for fp in pages}
    for fp in modal_pages:
        g, st = geom[fp], stash[fp]
        regs = {b["col"]: b for b in g["body_regions"]}
        no_rule = [c for c in ("left", "right") if c in regs
                   and regs[c]["y1_source"] == "page_bottom_no_rule"]
        if not no_rule:
            continue
        H = st["H"]
        if len(no_rule) == 1:
            c = no_rule[0]
            seed = st["seed"][c]
            y = seeded_rule(st["runs"][c], seed, WIN, T)
            if y is not None:
                results[(fp, c)] = {"y1": y, "source": "rule_seeded", "method": "rule_seeded",
                                    "run": int(st["runs"][c][y]), "seed": seed}
            else:
                results[(fp, c)] = {"abstain": "no_candidate_in_window", "seed": seed}
        else:
            pair, reason = paired_rule(st["runs"]["left"], st["runs"]["right"], H, WIN, T)
            if pair is not None:
                for c, y in zip(("left", "right"), pair):
                    results[(fp, c)] = {"y1": y, "source": "rule_paired", "method": "rule_paired",
                                        "run": int(st["runs"][c][y]), "seed": None}
            else:
                for c in ("left", "right"):
                    results[(fp, c)] = {"abstain": reason, "seed": None}
        for c in no_rule:
            if "abstain" in results[(fp, c)]:
                if "body_bottom_abstained" not in page_flags[fp]:
                    page_flags[fp].append("body_bottom_abstained")

    # ---- foot thresholds, over the abstained columns ----
    offs, wids = [], []
    for (fp, c), r in results.items():
        if "abstain" not in r:
            continue
        lines = stash[fp]["lines"][c]
        if len(lines) >= FOOT_LINES_MIN:
            o, w = foot_offsets_widths(lines, stash[fp]["colw"][c])
            offs += [max(0.0, x) for x in o[-3:]]
            wids += w[-3:]
    T_O, hist_O, modes_O = two_modes(offs, FOOT_BIN, min_sep=FOOT_MIN_SEP)
    T_W, hist_W, modes_W = two_modes(wids, FOOT_BIN, min_sep=FOOT_MIN_SEP)
    if T_O is None or T_W is None:
        raise Refused(f"foot thresholds underivable (T_O={T_O}, T_W={T_W})")

    for (fp, c), r in results.items():
        if "abstain" not in r:
            continue
        n, y1, bands = foot_strip(stash[fp]["lines"][c], stash[fp]["colw"][c], T_O, T_W)
        if n > 0:
            r["y1"], r["source"], r["bands"] = y1, "foot_furniture_excluded", bands

    # ---- records ----
    repo_root = Path(__file__).resolve().parents[2]
    config = {
        "geometry": str(Path(geometry_path).resolve()), "geometry_sha256": sha256_file(geometry_path),
        "pages": list(pages), "modal_size": list(modal),
        "WIN": WIN, "T": T, "T_O": T_O, "T_W": T_W,
        "histograms": {"T": {"bin": T_BIN, "hist": hist_T, "modes": modes_T},
                       "T_O": {"bin": FOOT_BIN, "min_sep": FOOT_MIN_SEP, "hist": hist_O, "modes": modes_O},
                       "T_W": {"bin": FOOT_BIN, "min_sep": FOOT_MIN_SEP, "hist": hist_W, "modes": modes_W}},
        "module_sha256": sha256_file(__file__),
        "git_head": BVR.get_git_head(repo_root), "git_dirty": BVR.get_git_dirty(repo_root),
    }
    chash = BVR.config_hash(config)
    header = {"kind": "run_header", "tier": "best_effort", "config": config, "config_hash": chash}

    counts = Counter()
    page_recs = []
    for fp in pages:
        g = geom[fp]
        rec = json.loads(json.dumps(g))   # a deep copy: every original field untouched
        rec["config_hash"] = chash
        off = fp not in modal_pages
        if off:
            page_flags[fp].append("page_size_off_mode")
            counts["page_size_off_mode"] += 1
        for b in rec["body_regions"]:
            c = b["col"]
            b["y1_prior"], b["y1_source_prior"] = b["box"][3], b["y1_source"]
            if off:
                b["body_bottom"] = {"method": "unchanged", "reason": "page_size_off_mode"}
            elif b["y1_source"] != "page_bottom_no_rule":
                b["body_bottom"] = {"method": "rule"}
            else:
                r = results[(fp, c)]
                if "abstain" in r:
                    counts["abstained:" + r["abstain"]] += 1
                    b["y1_source"] = "abstained_no_rule"
                    bb = {"method": "abstained", "seed": r["seed"], "window": WIN, "reason": r["abstain"]}
                    if "y1" in r:   # the foot strip moved it
                        b["box"][3] = r["y1"]
                        b["y1_source"] = r["source"]
                        bb.update({"method": "foot_furniture_excluded", "stripped_bands": r["bands"]})
                        counts["foot_furniture_excluded"] += 1
                    b["body_bottom"] = bb
                else:
                    b["box"][3] = r["y1"]
                    b["y1_source"] = r["source"]
                    counts[r["source"]] += 1
                    b["body_bottom"] = {"method": r["method"], "run": r["run"], "seed": r["seed"],
                                        "window": WIN}
        rec["body_bottom_flags"] = list(page_flags[fp])
        page_recs.append(rec)
    summary = {"kind": "run_summary", "tier": "best_effort", "config_hash": chash,
               "counts": dict(counts), "WIN": WIN, "T": T, "T_O": T_O, "T_W": T_W,
               "pages": len(pages), "modal_pages": len(modal_pages)}

    tmp = Path(str(out_path) + ".tmp")
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            for r in [header] + page_recs + [summary]:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, out_path)
    except BaseException:
        if tmp.exists():
            os.remove(tmp)
        raise
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("derive")
    d.add_argument("--geometry", required=True)
    d.add_argument("--volume-dir", required=True)
    d.add_argument("--pages", type=int, nargs="+", required=True)
    d.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    try:
        out_path = BVR.validate_out_path(args.out)
    except BVR.OutputPathRefused as e:
        print(str(e), file=sys.stderr)
        return 2
    if out_path.exists():
        print(f"REFUSED: {out_path} exists; never clobbered", file=sys.stderr)
        return 2
    try:
        summary = derive(args.geometry, args.volume_dir, list(args.pages), out_path)
    except Refused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        _cleanup(out_path)
        return 2
    except BaseException:
        _cleanup(out_path)
        raise
    print(json.dumps({k: summary[k] for k in ("counts", "WIN", "T", "T_O", "T_W", "pages", "modal_pages")},
                     ensure_ascii=False))
    return 0


def _cleanup(out_path):
    tmp = Path(str(out_path) + ".tmp")
    if tmp.exists():
        os.remove(tmp)


# ---------------------------------------------------------------------------
# library for stage 2
# ---------------------------------------------------------------------------

def load_bottoms(path, pages):
    """(bottoms, sha256, config_hash); bottoms = {(file_page, col): y1}. Raises Refused when the
    run_header is missing, a requested page is missing (or lacks a column), or a page record has an
    error."""
    raw = Path(path).read_bytes()
    recs = [json.loads(l) for l in raw.decode("utf-8").splitlines() if l.strip()]
    header = next((r for r in recs if r.get("kind") == "run_header"), None)
    if header is None:
        raise Refused(f"{path}: no run_header")
    by_page = {}
    for r in recs:
        if "body_regions" in r and "file_page" in r:
            by_page[r["file_page"]] = r
    bottoms = {}
    for fp in pages:
        r = by_page.get(fp)
        if r is None:
            raise Refused(f"{path}: no record for page {fp}")
        if r.get("error"):
            raise Refused(f"{path}: page {fp} record has an error: {r['error']}")
        for b in r["body_regions"]:
            bottoms[(fp, b["col"])] = int(b["box"][3])
        for c in ("left", "right"):
            if (fp, c) not in bottoms:
                raise Refused(f"{path}: page {fp} has no {c} body region")
    return bottoms, sha256_bytes(raw), header.get("config_hash")


def clamp_rect(box, col, fp, bottoms):
    """(new_box | None, info). The limit is bottoms[(fp, col)]; for col "full" the smaller of the two
    columns'. new_y1 = min(box[3], limit); None when the rect is wholly below the bottom."""
    if col == "full":
        limit = min(bottoms[(fp, "left")], bottoms[(fp, "right")])
    else:
        limit = bottoms[(fp, col)]
    new_y1 = min(box[3], limit)
    if new_y1 <= box[1]:
        return None, {"limit": limit, "clamped": new_y1 != box[3]}
    return [box[0], box[1], box[2], new_y1], {"limit": limit, "clamped": new_y1 != box[3]}


if __name__ == "__main__":
    raise SystemExit(main())
