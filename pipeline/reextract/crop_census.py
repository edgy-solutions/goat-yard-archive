"""Census of every crop PNG in the data tree: which are blank, and which would be refused before a send.

WHY. Item 2 asks for the blank-crop count across ALL artifact folders, not just the aperture folder
where the two known blanks were found. The reason is the shape of the original defect: the guard
existed in `crop_quality.crop_has_line` since Build 3 and the aperture harness simply never called
it, so the question "how many blank crops are sitting in this tree" had never once been asked
globally. Two were found by accident, in one folder, because a model answered a white rectangle with
confident Hebrew. That is not a search.

Folders are DISCOVERED by walking the tree, never listed in this file. A hardcoded list is how a
census misses the folder that someone added last week, and a census that misses a folder reports a
smaller number with exactly the same confidence.

The verdict per crop comes from `hebrew_aperture_diag.crop_fault`, the same gate that stands in
front of the outbound spend, so a crop cannot be blank to the census and sendable to an arm. Only
the pixel half runs here: a PNG on disk has no ratified rect to check, and the geometry half is
checked where the geometry lives.

TWO COLUMNS, NOT ONE, and the first census run is why. `crop_fault` has two blank verdicts and they
do not travel equally well:

  EMPTY (uniform / near-uniform ink) is meaningful for any image whatsoever. An image with one grey
  value carries no information no matter what it was meant to be.

  NO TEXT LINE is `crop_quality.crop_has_line`, a detector for the printed lines of this corpus. It
  is evidence of blankness ONLY where the image was supposed to be a text crop.

The tree is not all text crops. `audits/position_jaws/` holds diagnostic visualisations,
`truthset_review/` holds whole page strips, `marker_exemplars/crops/` holds single glyphs. Run
against everything, the line detector flagged `p299_starts.png` -- a 4802x448 diagnostic carrying
5.8% ink -- and calling that a blank crop would be a false positive of this tool, not a finding about
the corpus. So the headline count is EMPTY, the no-line cases are listed separately with their
dimensions, and a reader can tell which is which.

    python crop_census.py                 # table to stdout, report to the audits folder
    python crop_census.py selftest        # born-tests
"""
import io
import json
import os
import sys
import time
from pathlib import Path

from PIL import Image

import hebrew_aperture_diag as D

ROOT = D.DATA.parent                       # reextract_vol1/
OUT = D.DATA / "crop_census.json"
MD = D.DATA / "crop_census.md"
SKIP = {".git", "__pycache__", "node_modules"}


def folders(root=None):
    """Every directory under the data root that holds at least one PNG, discovered by walking."""
    root = Path(root or ROOT)
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        if any(f.lower().endswith(".png") for f in filenames):
            found.append(Path(dirpath))
    return sorted(found)


def verdict(path):
    """(ink_fraction, extrema, fault) for one PNG. fault is None when it would be safe to send.

    An unreadable file is a fault, not a skip. A census that silently drops what it cannot open
    reports on the files that happened to work."""
    try:
        im = Image.open(path)
        im.load()
        im = im.convert("L")
    except Exception as e:
        return None, None, f"unreadable:{type(e).__name__}"
    # Pixel half of the outbound gate only -- rects are empty, so the geometry checks are skipped and
    # the page size is the image's own, which can never be out of bounds against itself.
    return D.ink_fraction(im), im.getextrema(), D.crop_fault(im, [], im.size)


def census(root=None):
    rows, per = [], {}
    for d in folders(root):
        rel = str(d.relative_to(Path(root or ROOT).parent))
        pngs = sorted(p for p in d.iterdir() if p.suffix.lower() == ".png")
        agg = dict(folder=rel, n=len(pngs), empty=0, noline=0, unreadable=0)
        for p in pngs:
            ink, ext, fault = verdict(p)
            if fault:
                kind = ("unreadable" if fault.startswith("unreadable")
                        else "noline" if fault == "blank:no-line" else "empty")
                agg[kind] += 1
                try:
                    size = list(Image.open(p).size)
                except Exception:
                    size = None
                rows.append(dict(folder=rel, name=p.name, ink=ink, size=size, kind=kind,
                                 extrema=list(ext) if ext else None, fault=fault))
        per[rel] = agg
    return per, rows


def report(root=None, write=True):
    per, bad = census(root)
    n_all = sum(a["n"] for a in per.values())
    n_blank = sum(a["empty"] for a in per.values())
    n_noline = sum(a["noline"] for a in per.values())
    n_unread = sum(a["unreadable"] for a in per.values())
    lines = ["# Crop census -- every PNG in the data tree", "",
             "Generated %s by `crop_census.py`. Folders are discovered by walking, not listed."
             % time.strftime("%Y-%m-%d %H:%M"),
             "All page numbers in crop names are FILE pages; printed = file - 88.", "",
             "**EMPTY** is the blank-crop count. **no-line** is the text-line detector, which is",
             "evidence of blankness only where the image was meant to be a text crop -- see the",
             "module docstring.", "",
             "| folder | PNGs | EMPTY | no-line | unreadable |", "|---|---|---|---|---|"]
    for rel, a in sorted(per.items()):
        lines.append("| `%s` | %d | %d | %d | %d |"
                     % (rel, a["n"], a["empty"], a["noline"], a["unreadable"]))
    lines += ["| **total** | **%d** | **%d** | **%d** | **%d** |"
              % (n_all, n_blank, n_noline, n_unread), ""]
    if bad:
        lines += ["## Every PNG the gate would refuse", "",
                  "| folder | file | size | ink | extrema | class | fault |",
                  "|---|---|---|---|---|---|---|"]
        for r in bad:
            lines.append("| `%s` | `%s` | %s | %s | %s | %s | `%s` |"
                         % (r["folder"], r["name"], r.get("size"),
                            "%.5f" % r["ink"] if r["ink"] is not None else "-",
                            r["extrema"], r["kind"], r["fault"]))
    else:
        lines.append("No PNG in the tree would be refused.")
    txt = "\n".join(lines) + "\n"
    if write:
        MD.write_text(txt, encoding="utf-8")
        OUT.write_text(json.dumps(dict(generated=time.strftime("%Y-%m-%dT%H:%M:%S"),
                                       total=n_all, empty=n_blank, noline=n_noline,
                                       unreadable=n_unread,
                                       per_folder=per, refused=bad),
                                  ensure_ascii=False, indent=1), encoding="utf-8")
    return per, bad, (n_all, n_blank, n_noline, n_unread)


def selftest():
    n = f = 0

    def ck(name, cond, detail=""):
        nonlocal n, f
        n += 1
        if not cond:
            f += 1
        print("  %s  %s%s" % ("ok  " if cond else "FAIL", name,
                              "" if cond else "   <- %r" % (detail,)))

    fs = folders()
    ck("folders are discovered, not hardcoded, and several are found", len(fs) >= 5, len(fs))
    # The property is DISCOVERY, so test discovery: make a folder this file has never heard of and
    # see it counted. Probing the source for a folder name tested the comment, not the behaviour.
    import tempfile, shutil
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "brand_new_folder").mkdir()
        Image.new("L", (30, 20), 255).save(tmp / "brand_new_folder" / "x.png")
        ck("a folder this tool has never heard of is discovered and counted",
           any(fd.name == "brand_new_folder" for fd in folders(tmp)), folders(tmp))
        _p2, _b2, tot2 = report(tmp, write=False)
        ck("and a blank PNG inside it is refused", tot2[1] == 1, tot2)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    per, bad, (n_all, n_blank, n_noline, n_unread) = report(write=False)
    ck("every PNG in the tree is accounted for", n_all >= 700, n_all)
    # The four known blanks are p423:n3 and p726:n3 at BOTH apertures. They are the whole reason the
    # gate exists, so a census that cannot see them is not measuring anything.
    empties = sorted(r["name"] for r in bad if r["kind"] == "empty")
    for want in ("p423_n3_A1_notebox.png", "p423_n3_A2_spanbox.png",
                 "p726_n3_A1_notebox.png", "p726_n3_A2_spanbox.png"):
        ck("the census finds the known blank %s" % want, want in empties, empties)
    # The FIRST run of this census asserted "exactly 4" and was wrong: it also flagged
    # position_jaws/p299_starts.png, which is not empty at all (5.8% ink) but fails the text-line
    # detector because it is a 4802x448 diagnostic image and not a text crop. The assumption was mine
    # and the census falsified it, which is the tool working. The assertion now separates the two
    # classes rather than quietly widening to fit the result.
    ck("EMPTY is exactly the four known blanks and nothing else", len(empties) == 4, empties)
    nolines = sorted(r["name"] for r in bad if r["kind"] == "noline")
    ck("no-line cases are reported apart from EMPTY and are named",
       nolines == ["p299_starts.png"], nolines)
    ck("the no-line case is demonstrably NOT empty",
       all(r["ink"] > D.NEAR_UNIFORM_INK for r in bad if r["kind"] == "noline"),
       [(r["name"], r["ink"]) for r in bad if r["kind"] == "noline"])
    ck("nothing in the tree is unreadable", n_unread == 0, n_unread)
    # One definition of ink, or a crop could be blank to the census and inked to the gate.
    im = Image.open(D.CROPDIR / "p912_n2_A2_spanbox.png")
    ck("the census and the gate share one ink definition",
       verdict(D.CROPDIR / "p912_n2_A2_spanbox.png")[0] == D.ink_fraction(im))
    ck("a crop the census refuses is one the gate refuses",
       all(D.gate_outbound(Path(r["folder"]).name and (ROOT.parent / r["folder"] / r["name"]))[1]
           for r in bad))
    print("")
    print("%s: %d/%d checks" % ("PASS" if not f else "FAIL", n - f, n))
    return f


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        sys.exit(1 if selftest() else 0)
    per, bad, (n_all, n_blank, n_noline, n_unread) = report()
    print("crop census -- %d PNGs in %d folders" % (n_all, len(per)))
    for rel, a in sorted(per.items()):
        print("  %-50s %4d PNGs  %2d EMPTY  %2d no-line  %2d unreadable"
              % (rel, a["n"], a["empty"], a["noline"], a["unreadable"]))
    print("")
    print("  TOTAL %d PNGs, %d EMPTY, %d no-line, %d unreadable"
          % (n_all, n_blank, n_noline, n_unread))
    for r in bad:
        print("    %-34s %-30s ink=%s  %s"
              % (r["folder"], r["name"],
                 "%.5f" % r["ink"] if r["ink"] is not None else "-", r["fault"]))
    print("")
    print("wrote %s" % MD)
