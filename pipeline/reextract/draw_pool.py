# -*- coding: utf-8 -*-
"""The 100-span truth set's drawable population, measured rather than assumed (ruling 4).

The draw has four cuts before a single span can be shown to a signer, and each one is a PAGE or BOX
property, not a choice:

  1. SEALED/SIGNED. The 19 ratified spans are spent and their pages are closed. Excluded by page and by
     span id, including the multi-run children of a signed id.
  2. COUNT AGREEMENT. The localizer will not index into regions it cannot count, so a span on a page where
     the detector's region count differs from the extractor's n_notes is unreachable -- before any box.
     Read from the CORRECTED region census; the first one was retracted (it took len() of a 2-tuple).
  3. LOCALIZER. Even on a counting page the Hebrew line may not be found or the run may not be locatable
     at the confidence floor. That is the abstain-and-flag the whole geometry rests on, not a failure.
  4. THE BAND-CLIP CUT. presplit pastes each native band at canvas x=0 into a canvas as wide as the widest
     band, so a narrow band carries filler on its right. A box reaching into that filler is not on the
     page. Those spans leave the draw: a truth set must not contain a span whose crop would show canvas.

What this does NOT do: cut a crop, send anything, or choose the 100. It produces the population and the
funnel. Local CV only; nothing is written outside the audits artifact named below.
"""
import io
import json
import os
import sys
import time
from collections import Counter

# Import from THIS file's directory, never a hardcoded worktree.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, os.pardir, "scripts"))
import cv_footnote_presplit as ps                                          # noqa: E402  (Lane A's, read-only)
import note_line_region as NLR                                            # noqa: E402
import assembler as ASM                                                   # noqa: E402
from clean_run import git_state, provisional, banner                      # noqa: E402


DV = "C:/Users/cnogr/git/dr-voluminous/reextract_vol1"
AUD = DV + "/audits"
PAGE = "C:/Users/cnogr/git/dr-voluminous/commentary/volume1/page%d_image1.png"
CENSUS = AUD + "/hebrew_span_census_20261004.json"
REGIONS = AUD + "/note_region_count_census_20261004_corrected.json"
VERDICTS = AUD + "/span_box_verdicts_20260906.jsonl"
OUT = AUD + "/draw_pool_20261004.json"
PROF = os.path.join(_HERE, "book_profile.gill.yaml")

# The pages of the ratified 19. Spent: never re-scored, never re-opened, and never drawn from.
SEALED_PAGES = {102, 217, 293, 362, 423, 427, 491, 596, 726, 897, 912}

rows = json.load(io.open(CENSUS, encoding="utf-8"))["rows"]
reg = json.load(io.open(REGIONS, encoding="utf-8"))
assert "rows" in reg and reg.get("retracts"), \
    "%s is not the corrected region census -- the retracted one has no wrapper and its `detected` " \
    "column is the constant 2." % os.path.basename(REGIONS)
agree = {r["page"]: r for r in reg["rows"]}
signed = {json.loads(l)["span_id"] for l in io.open(VERDICTS, encoding="utf-8") if l.strip()}
prof = ASM.load_profile(PROF)
assert prof, "no profile -- locate_span would take None and die on .get"

cut1 = [r for r in rows
        if r["span_id"] not in signed
        and r["span_id"].split("s")[0] not in signed            # multi-run children of a signed id
        and r["page"] not in SEALED_PAGES]
# The one invariant that must never be merely probable: nothing spent is in the population.
assert not (SEALED_PAGES & {r["page"] for r in cut1}), "a sealed page survived cut 1"
assert not (signed & {r["span_id"] for r in cut1}), "a signed span id survived cut 1"

cut2 = [r for r in cut1 if agree.get(r["page"], {}).get("agree")]
print("census %d -> unsigned/unsealed %d -> on count-agreeing pages %d (%d pages)"
      % (len(rows), len(cut1), len(cut2), len({r["page"] for r in cut2})))

GIT_START = git_state(_HERE)
res, secs, cache = [], [], {}
t00 = time.time()
for i, r in enumerate(sorted(cut2, key=lambda x: (x["page"], x["note_index"])), 1):
    t0 = time.time()
    rec = {k: r[k] for k in ("span_id", "page", "note_index", "notes_on_page", "hebrew",
                             "words", "letters", "nikud", "chars", "page_status")}
    rec["stitch_page"] = bool(agree[r["page"]].get("stitched"))
    try:
        if r["page"] not in cache:
            cache[r["page"]] = ps.presplit(PAGE % r["page"], upscale=1)
        strip, info = cache[r["page"]]
        if strip is None:
            rec.update(verdict="NO_STRIP", status="presplit returned no apparatus strip")
        else:
            box, st = NLR.locate_span(strip.convert("L"), r["note_index"] - 1, r["hebrew"],
                                      r["notes_on_page"], prof)
            if box is None:
                rec.update(verdict="ABSTAIN", status=st)
            else:
                rec.update(verdict="BOX", status=st, box=list(box))
                # cut 4, in STRIP coords. Bands are pasted at canvas x=0, stacked down the strip, so the
                # box's band is the one whose paste window contains its top edge, and the filler starts at
                # that band's own native width. No tolerance: a box with no band is itself a fault.
                hit = [b for b in info["bands"]
                       if b["paste"][1] <= box[1] < b["paste"][1] + b["size"][1]]
                if len(hit) != 1:
                    rec.update(band=None, band_w=None, over=None, cut="no-band")
                else:
                    b = hit[0]
                    over = box[2] - b["size"][0]
                    rec.update(band=b["band"], band_w=b["size"][0], over=over,
                               cut=("band-overshoot" if over > 0 else ""))
    except Exception as e:
        rec.update(verdict="ERROR", status="%s: %s" % (type(e).__name__, str(e)[:90]))
    secs.append(round(time.time() - t0, 2))                  # footer, never a data row
    res.append(rec)
    if i % 25 == 0:
        print("  %3d/%d  BOX %d  %.0fs" % (i, len(cut2), sum(1 for x in res if x["verdict"] == "BOX"),
                                           time.time() - t00), flush=True)

boxed = [r for r in res if r["verdict"] == "BOX"]
# A box whose band-clip status was never computed is not a clean box. The flag must exist on every one of
# them, or the cut would silently pass whatever it failed to measure.
assert all("cut" in r for r in boxed), "a BOX row carries no band-clip verdict"
clean = [r for r in boxed if not r["cut"]]
print("\nlocalizer: %s" % dict(Counter(r["verdict"] for r in res)))
print("abstain reasons: %s" % dict(Counter(r["status"].split(":")[0]
                                           for r in res if r["verdict"] == "ABSTAIN")))
print("band-clip cut: %s" % dict(Counter(r["cut"] for r in boxed)))
print("\nFUNNEL  census %d -> unsigned/unsealed %d -> counting pages %d -> boxed %d -> after band cut %d"
      % (len(rows), len(cut1), len(cut2), len(boxed), len(clean)))
print("of the %d survivors, %d are on stitch-flagged pages"
      % (len(clean), sum(1 for r in clean if r["stitch_page"])))
print("words: %s   nikud: %s" % (dict(Counter(min(r["words"], 4) for r in clean)),
                                 dict(Counter(r["nikud"] for r in clean))))
GIT_END = git_state(_HERE)
PROVISIONAL = provisional(GIT_START, GIT_END)
print("\n" + banner(GIT_START, GIT_END))
io.open(OUT, "w", encoding="utf-8").write(json.dumps(
    {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
     "git_start": GIT_START, "git_end": GIT_END, "provisional": PROVISIONAL,
     "inputs": {"census": os.path.basename(CENSUS), "regions": os.path.basename(REGIONS),
                "verdicts": os.path.basename(VERDICTS)},
     "sealed_pages": sorted(SEALED_PAGES),
     "funnel": {"census": len(rows), "unsigned_unsealed": len(cut1), "counting_pages": len(cut2),
                "boxed": len(boxed), "after_band_cut": len(clean)},
     "footer": {"spans": len(res), "pages": len(cache), "secs_total": round(sum(secs), 1)},
     "rows": res}, ensure_ascii=False, indent=1))
print("wrote", OUT)
