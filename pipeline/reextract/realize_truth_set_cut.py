"""Backfill the realized-rect side file for an EXISTING truth-set cut manifest.

Run: python realize_truth_set_cut.py MANIFEST

Writes <manifest stem>.realized.json beside the manifest, in the shape cut_truth_set_crops.py writes at cut
time (generated_by.mode is "backfill" here, "cut" there). Reads only PNG headers: page_wh from each row's
page PNG, size_wh from each crop PNG. Rects come from hebrew_aperture_diag.realize_rects.

Exit 2, nothing written, when: the output already exists; a page PNG or crop PNG is missing; or any
realized_size disagrees with the crop PNG's actual size (the span_ids are named). A row is never dropped.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

import hebrew_aperture_diag as HAD


def _git(here):
    try:
        head = subprocess.check_output(["git", "-C", str(here), "rev-parse", "HEAD"]).decode().strip()
        por = subprocess.check_output(["git", "-C", str(here), "status", "--porcelain"]).decode()
        paths = [l for l in por.splitlines() if l.strip()]
        return head, ({"state": "clean"} if not paths else {"state": "dirty", "n": len(paths), "paths": paths[:12]})
    except Exception as e:                                  # not knowing is not the same as clean
        return "unknown", {"state": "unknown", "error": str(e)[:120]}


def _hdr(path):
    with Image.open(path) as im:
        return list(im.size)


def build(manifest_path):
    """(doc, problems). problems is a list of strings; a non-empty list means nothing may be written."""
    mp = Path(manifest_path)
    raw = mp.read_bytes()
    man = json.loads(raw.decode("utf-8"))
    pad = man["recipe"]["pad_native_px"]
    rows, problems = [], []
    for b in man["rows"]:
        if not b.get("crop"):
            continue
        sid = b["span_id"]
        page_png = HAD.IMG / ("page%d_image1.png" % b["page"])
        try:
            page_wh = _hdr(page_png)
        except OSError as e:
            problems.append("%s: page PNG unreadable %s (%s)" % (sid, page_png, type(e).__name__))
            continue
        ent = {}
        for key, src in (("crop", b["crop"]), ("note_context", b.get("note_context"))):
            if not src:
                ent[key] = None
                continue
            try:
                size = _hdr(src["path"])
            except OSError as e:
                problems.append("%s: %s PNG unreadable %s (%s)" % (sid, key, src["path"], type(e).__name__))
                ent[key] = None
                continue
            rects = HAD.realize_rects(src["native_rects"], page_wh, pad)
            rs = HAD.realized_size(rects)
            if rs != size:
                problems.append("%s: %s realized_size %s != PNG size %s" % (sid, key, rs, size))
            ent[key] = {"path": src["path"], "size_wh": size, "rects": rects}
        rows.append({"span_id": sid, "page": b["page"], "page_png": str(page_png), "page_wh": page_wh,
                     "crop": ent["crop"], "note_context": ent["note_context"]})
    head, dirty = _git(Path(__file__).resolve().parent)
    doc = {"kind": "truth_set_cut_realized_rects", "manifest": mp.name,
           "manifest_sha256": hashlib.sha256(raw).hexdigest(),
           "set_sha16": man["set_sha16"], "page_numbering": "file (printed = file - 88)",
           "pad_requested": pad, "stack_gap_px": 20, "min_side_px": 4,
           "generated_by": {"script": "realize_truth_set_cut.py", "mode": "backfill",
                            "git_head": head, "git_dirty": dirty},
           "rows": rows}
    return doc, problems


def main(argv):
    if len(argv) != 1:
        sys.stderr.write("usage: realize_truth_set_cut.py MANIFEST\n")
        return 2
    mp = Path(argv[0])
    out = mp.with_name(mp.stem + ".realized.json")
    if out.exists():
        sys.stderr.write("REFUSED: %s already exists. Nothing was written.\n" % out)
        return 2
    doc, problems = build(mp)
    if problems:
        sys.stderr.write("REFUSED: %d problem(s), nothing written:\n" % len(problems))
        for p in problems:
            sys.stderr.write("   " + p + "\n")
        return 2
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print("wrote %s  rows %d" % (out, len(doc["rows"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
