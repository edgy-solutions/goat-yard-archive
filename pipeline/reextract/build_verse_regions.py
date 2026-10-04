"""Writer: Lane A2 step 2 -- verse regions from page layout.

Orchestrates the PURE functions in verse_regions.py over real inputs (page PNGs, page geometry,
optional witness .md text) that this script loads; verse_regions.py itself never touches a file
or the network. The model-read path (--read on) is the only part of this run that can reach a
network endpoint, and it goes through verse_head_read.py's endpoint_guard-gated resolver -- no
default endpoint, hard refusal of the reserved .179/.188 pair.

Threshold derivation (thresholds-from-empty-bands: never guessed, never per-page):
  Full-width classification no longer derives a threshold at all -- FIX3 replaced it with two
  MEASURED edges (VR.FULL_GAP_MAX_PX, VR.COL_GAP_MIN_PX; see
  MEASURE_step2_gutter_inset_20261004.md): a single derived threshold was refused by the data
  (no empty band separates the full-width population from the column population). The zone
  between the two edges stays a column band flagged 'gutter_ambiguous', never split.
  pass 1: analyze_page_s1 for real (full-width classification uses the fixed edges above), then
          derive inset_thr from the corpus-wide distribution of (left_ink_x - column median) over
          every non-full band -- this IS still a derived threshold (derive_threshold), since the
          inset population does have a real empty band (see the MEASURE file).
  pass 2: head_candidates / confirm_candidates / assemble_regions / check_region_rects with
          inset_thr now fixed for the whole run (never re-derived per page).

Output is private data (derived from a copyrighted scan corpus) and must never land inside this
repo or goat-yard-archive -- see FORBIDDEN_OUTPUT_ROOTS / validate_out_path(), copied verbatim
from pipeline/scripts/build_page_geometry.py's pattern.

JSONL record kinds, in this order within one run:
  run_header   -- once, first line: config, resolved thresholds (with their bands), run inputs.
  run_invalid  -- one per requested page whose geometry record or image file is missing/unusable;
                  the page is excluded from the rest of the run (never silently dropped: named).
  page         -- one per page that WAS processed: S1 summary + S5 per-page flags.
  region       -- one per assembled region (after check_region_rects attaches rect sanity).
  run_summary  -- once, last line, on a clean finish: census + thresholds + flag tally.
  run_aborted  -- written INSTEAD of run_summary if the run-level fault fires (3 consecutive
                  transport-level read errors); the run exits nonzero and no run_summary follows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verse_regions as VR  # noqa: E402  (bare-name import convention of this tree)
import verse_head_read as VHR  # noqa: E402
import endpoint_guard  # noqa: E402

DEFAULT_VOLUME_DIR = "C:/Users/cnogr/git/dr-voluminous/commentary/volume1"
DEFAULT_GEOMETRY = "C:/Users/cnogr/git/dr-voluminous/body_shadow_vol1/geometry/volume1_page_geometry.jsonl"
DEFAULT_MODEL = VHR.DEFAULT_MODEL

# Repo roots this writer refuses to write inside, loudly -- same pattern as
# pipeline/scripts/build_page_geometry.py's validate_out_path, extended with the running repo's
# own root so the guard travels with the file rather than with a hand-maintained path string.
FORBIDDEN_OUTPUT_ROOTS = [
    Path("C:/Users/cnogr/git/goatyard-laneA"),
    Path("C:/Users/cnogr/git/goat-yard-archive"),
]


class OutputPathRefused(Exception):
    """Raised when the resolved --out path lands inside a forbidden repo root."""


def _is_within(path, root):
    p = os.path.normcase(os.path.normpath(str(path)))
    r = os.path.normcase(os.path.normpath(str(root)))
    return p == r or p.startswith(r + os.sep)


_SELF_REPO_ROOT = Path(__file__).resolve().parents[2]
if all(not _is_within(_SELF_REPO_ROOT, r.resolve()) for r in FORBIDDEN_OUTPUT_ROOTS):
    FORBIDDEN_OUTPUT_ROOTS.append(_SELF_REPO_ROOT)


def validate_out_path(out_arg):
    resolved = Path(out_arg).resolve()
    for root in FORBIDDEN_OUTPUT_ROOTS:
        root_resolved = root.resolve()
        if _is_within(resolved, root_resolved):
            raise OutputPathRefused(
                f"REFUSED: output path resolves inside forbidden repo root {root_resolved} "
                f"(resolved --out = {resolved}). This is private data derived from a copyrighted "
                f"scan corpus; it must never land inside a repo root. Pass an --out under "
                f"dr-voluminous (or another path outside both repos)."
            )
    return resolved


# ---------------------------------------------------------------------------
# Config block + hash
# ---------------------------------------------------------------------------

def config_hash(base_config):
    canonical = json.dumps(base_config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def build_config(args, module_sha256, git_head, git_dirty):
    base = {
        "pages": sorted(args.pages),
        "geometry": str(Path(args.geometry).resolve()),
        "volume_dir": str(Path(args.volume_dir).resolve()),
        "witness_dir": str(Path(args.witness_dir).resolve()) if args.witness_dir else None,
        "read": args.read,
        "model": args.model,
        "endpoint_id": args.endpoint_id,
        "full_gap_max_px": VR.FULL_GAP_MAX_PX,
        "col_gap_min_px": VR.COL_GAP_MIN_PX,
        "module_sha256": module_sha256,
        "git_head": git_head,
        "git_dirty": git_dirty,
    }
    cfg = dict(base)
    cfg["hash"] = config_hash(base)
    return cfg


def compute_module_sha256(module_path):
    return hashlib.sha256(Path(module_path).read_bytes()).hexdigest()


def get_git_head(repo_root):
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              cwd=str(repo_root), capture_output=True, text=True, timeout=30)
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return None


def get_git_dirty(repo_root):
    try:
        out = subprocess.run(["git", "status", "--porcelain"],
                              cwd=str(repo_root), capture_output=True, text=True, timeout=30)
        if out.returncode == 0:
            return bool(out.stdout.strip())
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Input loading (the only place in this tree that reads pages/geometry/witness)
# ---------------------------------------------------------------------------

def load_geometry(geometry_path):
    by_page = {}
    with open(geometry_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            by_page[rec["file_page"]] = rec
    return by_page


def load_page_gray(volume_dir, file_page):
    path = Path(volume_dir) / f"page{file_page}_image1.png"
    if not path.exists():
        return None
    return np.asarray(Image.open(path).convert("L"))


def load_witness(witness_dir, file_page):
    if not witness_dir:
        return None
    path = Path(witness_dir) / f"page{file_page}_image1_normalized.md"
    if not path.exists():
        return None
    return VR.parse_witness(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Pass 0/1: threshold derivation (never guessed, never per-page)
# ---------------------------------------------------------------------------

def derive_inset_thr(s1_by_page, min_gap):
    """Pass 1b: inset_px (band left margin minus that column's own median left margin) over
    every non-full body band across the whole run, once -- the paragraph-break signal's
    threshold, taken from the corpus distribution, never picked."""
    # SIGNED, non-negative only: the candidate test is signed (inset_px >= thr), so a line starting
    # LEFT of the column's median text-left (outdent, rule fragment) is not on the indent axis;
    # abs() folded -51/-54 px outdents into the gap and moved the threshold 50 -> 80.5. Bands
    # flagged full_unpaired (one-sided gutter-crossers: the rule under the running head) are not
    # text lines and are excluded.
    inset_values = []
    for fp, s1 in s1_by_page.items():
        for col in ("left", "right"):
            bands = [b for b in (s1.get(col) or []) if not b.get("full_unpaired")]
            med = VR._column_medians(bands)
            for b in bands:
                inset_px = (b["left_ink_x"] - b["x0"]) - med["left_x"]
                if inset_px >= 0:
                    inset_values.append(inset_px)
    thr = VR.derive_threshold(inset_values, min_gap=min_gap)
    return thr, inset_values


# ---------------------------------------------------------------------------
# Model-read wiring (--read on only; never invoked by this run unless asked)
# ---------------------------------------------------------------------------

class _RequestsClient:
    """Thin injectable-shape wrapper so verse_head_read.read_head's `.post`-style branch can
    drive a real `requests` session. Never constructed or called unless --read on."""

    def __init__(self, base_url, model):
        self.base_url = base_url
        self.model = model

    def post(self, url, json=None, timeout=None):
        import requests
        return requests.post(url, json=json, timeout=timeout)


def run_reads(candidates_by_page, gray_by_page, geom_by_page, s1_by_page, client, counter):
    """Guarded read_head over every 'verse'-kind candidate. Returns head_reads keyed exactly as
    verse_regions.confirm_candidates expects: {(file_page,col,y0): {...}}. Raises
    verse_head_read.ConsecutiveReadErrorFault if 3 CONSECUTIVE transport failures occur -- an
    abstain or a guard refusal is not a transport failure and resets nothing by itself (only a
    successful call, including an abstain, resets the counter)."""
    head_reads = {}
    for fp, cands in candidates_by_page.items():
        gray = gray_by_page[fp]
        H, W = gray.shape
        col_boxes = s1_by_page[fp]["col_boxes"]
        for c in cands:
            if c["kind"] != "verse":
                continue
            box = VHR.head_crop_box(c, col_boxes[c["col"]])
            try:
                result = VHR.guarded_read_head(client, gray, box, (H, W))
                counter.record_success()
            except Exception:
                counter.record_error()
                continue
            head_reads[(fp, c["col"], c["y0"])] = result
    return head_reads


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pages", type=int, nargs="+", required=True,
                     help="File-page ints to process, e.g. --pages 90 403 745.")
    ap.add_argument("--geometry", default=DEFAULT_GEOMETRY,
                     help="Path to volume1_page_geometry.jsonl.")
    ap.add_argument("--volume-dir", default=DEFAULT_VOLUME_DIR,
                     help="Directory holding pageNNN_image1.png.")
    ap.add_argument("--witness-dir", default=None,
                     help="Directory holding pageNNN_image1_normalized.md (optional; omit to "
                          "run with witness=null everywhere, flagged numbers_single_source).")
    ap.add_argument("--out", required=True,
                     help="Output JSONL path. Must NOT resolve inside goatyard-laneA* or "
                          "goat-yard-archive -- this is private data.")
    ap.add_argument("--read", choices=["off", "on"], default="off",
                     help="off (default): no model calls, every verse head is head_unconfirmed "
                          "unless rejected is impossible without a read. on: guarded reads via "
                          "endpoint_guard -- never defaults, refuses the reserved .179/.188 pair.")
    ap.add_argument("--host", default=None, help="Ollama endpoint, required when --read on.")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--endpoint-id", default=None, help="Recorded in config for provenance only.")
    return ap


def main(argv=None):
    args = build_arg_parser().parse_args(argv)

    try:
        out_path = validate_out_path(args.out)
    except OutputPathRefused as e:
        print(str(e), file=sys.stderr)
        return 2

    module_path = Path(__file__).resolve().parent / "verse_regions.py"
    module_sha256 = compute_module_sha256(module_path)
    repo_root = Path(__file__).resolve().parents[2]
    git_head = get_git_head(repo_root)
    git_dirty = get_git_dirty(repo_root)
    config = build_config(args, module_sha256, git_head, git_dirty)

    geom_all = load_geometry(args.geometry)

    pages_requested = sorted(set(args.pages))
    invalid_records = []
    geom_by_page, gray_by_page = {}, {}
    for fp in pages_requested:
        geom = geom_all.get(fp)
        if geom is None:
            invalid_records.append({"kind": "run_invalid", "file_page": fp,
                                     "reason": "no_geometry_record"})
            continue
        gray = load_page_gray(args.volume_dir, fp)
        if gray is None:
            invalid_records.append({"kind": "run_invalid", "file_page": fp,
                                     "reason": "image_missing"})
            continue
        geom_by_page[fp] = geom
        gray_by_page[fp] = gray

    usable_pages = sorted(geom_by_page.keys())

    records = [{"kind": "run_header", "config": config, "pages_requested": pages_requested,
                "pages_usable": usable_pages}]
    records.extend(invalid_records)

    if not usable_pages:
        records.append({"kind": "run_aborted", "reason": "no_usable_pages"})
        _write(out_path, records)
        print("ERROR: zero usable pages (all requested pages missing geometry or image)",
              file=sys.stderr)
        return 1

    # --- pass 1: real S1 per page (full-width classification uses fixed measured edges, FIX3 --
    #             no derived full_gap_thr), then derive inset_thr -------------------------------
    s1_by_page = {}
    for fp in usable_pages:
        ink = VR.page_ink(gray_by_page[fp])
        s1_by_page[fp] = VR.analyze_page_s1(ink, geom_by_page[fp])
        geom_by_page[fp]["_s1"] = s1_by_page[fp]  # consumed by check_region_rects (running_head)

    try:
        inset_result, _ = derive_inset_thr(s1_by_page, min_gap=VR.MIN_GAP_INSET_PX)
    except VR.ThresholdUndetermined as e:
        records.append({"kind": "run_aborted", "reason": "inset_thr_undetermined",
                         "detail": str(e)})
        _write(out_path, records)
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    inset_thr = inset_result["value"]

    records[0]["thresholds"] = {
        "full_width_edges": {"full_gap_max_px": VR.FULL_GAP_MAX_PX, "col_gap_min_px": VR.COL_GAP_MIN_PX,
                              "basis": "MEASURE_step2_gutter_inset_20261004.md"},
        "inset_thr": {"value": inset_thr, "lo": inset_result["lo"], "hi": inset_result["hi"],
                      "gap": inset_result["gap"], "n_below": inset_result["n_below"],
                      "n_above": inset_result["n_above"]},
    }

    # --- pass 1c: centred heads printed across the gutter (needs inset_thr) -------------------
    for fp in usable_pages:
        VR.pair_centred_across_gutter(s1_by_page[fp], inset_thr)

    # --- pass 2: head candidates ------------------------------------------------------------
    candidates_by_page, rejected_pre_read_by_page = {}, {}
    for fp in usable_pages:
        cands = VR.head_candidates(s1_by_page[fp], inset_thr=inset_thr)
        candidates_by_page[fp] = cands

    # --- optional model reads (--read on) ----------------------------------------------------
    head_reads = {}
    if args.read == "on":
        try:
            base_url, digest = VHR.resolve_and_check(args.host, args.model)
        except Exception as e:
            records.append({"kind": "run_aborted", "reason": "endpoint_resolution_failed",
                             "detail": str(e)})
            _write(out_path, records)
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        records[0]["model_digest"] = digest
        records[0]["resolved_host"] = base_url
        # Law: the header is on disk BEFORE the first model call (a crash mid-read still leaves
        # the config, thresholds, endpoint and digest). The final _write replaces this file.
        _write(out_path, records[:1])
        client = _RequestsClient(base_url, args.model)
        counter = VHR.ConsecutiveErrorCounter(limit=3)
        try:
            head_reads = run_reads(candidates_by_page, gray_by_page, geom_by_page, s1_by_page,
                                    client, counter)
        except VHR.ConsecutiveReadErrorFault as e:
            records.append({"kind": "run_aborted", "reason": "consecutive_read_errors",
                             "detail": str(e)})
            _write(out_path, records)
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    confirmed_by_page, rejected_by_page = {}, {}
    for fp in usable_pages:
        confirmed, rejected = VR.confirm_candidates(candidates_by_page[fp], head_reads)
        confirmed_by_page[fp] = confirmed
        rejected_by_page[fp] = rejected

    witness_by_page = {fp: load_witness(args.witness_dir, fp) for fp in usable_pages}

    page_records_ordered = [{"file_page": fp} for fp in usable_pages]
    regions, page_summaries = VR.assemble_regions(
        page_records_ordered, s1_by_page, confirmed_by_page, rejected_by_page,
        witness_by_page, config)

    VR.assert_numbering_invariant(regions)
    VR.check_region_rects(regions, geom_by_page)

    for fp in usable_pages:
        ps = page_summaries[fp]
        records.append({"kind": "page", "file_page": fp, **{k: v for k, v in ps.items() if k != "file_page"},
                         "s1_flags": s1_by_page[fp]["flags"],
                         "running_head_present": s1_by_page[fp]["running_head"] is not None})

    flag_counts = Counter()
    for region in regions:
        for fl in region.get("flags") or []:
            flag_counts[fl] += 1
        records.append({"kind": "region", **{k: v for k, v in region.items()}})

    _write(out_path, records)

    print("\n=== run_summary ===")
    summary = {
        "kind": "run_summary",
        "pages_requested": len(pages_requested), "pages_usable": len(usable_pages),
        "pages_invalid": len(invalid_records),
        "regions": len(regions),
        "flags": dict(sorted(flag_counts.items())),
        "thresholds": records[0]["thresholds"],
        "config_hash": config["hash"],
        "read": args.read,
        "output": str(out_path),
    }
    print(json.dumps(summary))
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(summary) + "\n")

    return 0


def _write(out_path, records):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
