# -*- coding: utf-8 -*-
"""Region-count agreement over every span-bearing page. The draw's actual gate.

The localizer abstained on 7 of 8 sampled spans, all for one reason: `page-abstain: count-mismatch`, the
detector's note-region count against the extractor's n_notes. That is the count-not-recognize guard doing its
job -- it will not index into regions it cannot count -- and it means the drawable population is decided by a
PAGE property, before any span, box or crop is considered. This measures it on all 414 span-bearing pages.

Local CV only. No outbound call, no crop written, no tree touched. Scratchpad only.
"""
import io
import json
import os
import sys
import time
from collections import Counter

# Import from THIS file's directory, never a hardcoded worktree: a copy of this script in the
# other lane's tree must import that lane's modules, not Lane B's.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, os.pardir, "scripts"))
import cv_footnote_presplit as ps                                          # noqa: E402  (Lane A's, read-only)
import note_line_region as NLR                                            # noqa: E402
import assembler as ASM                                                   # noqa: E402

PAGE = "C:/Users/cnogr/git/dr-voluminous/commentary/volume1/page%d_image1.png"
# The committed artifacts, by their committed names. Not a session scratchpad: a script in the repo must be
# able to reproduce the artifact beside it in the repo, and the dated filename is deliberate -- these are
# dated observations of a frozen apparatus run, so a rerun under a new date writes a NEW file rather than
# quietly replacing the one an ADR cites.
DV = "C:/Users/cnogr/git/dr-voluminous/reextract_vol1"
AUD = DV + "/audits"
CENSUS = AUD + "/hebrew_span_census_20261004.json"
OUT = AUD + "/note_region_count_census_20261004.json"
PROF = os.path.join(_HERE, "book_profile.gill.yaml")

rows = json.load(io.open(CENSUS, encoding="utf-8"))["rows"]
prof = ASM.load_profile(PROF)
assert prof, "no profile"

pages = {}
for r in rows:
    pages.setdefault(r["page"], {"page": r["page"], "n_notes": r["notes_on_page"],
                                 "status": r["page_status"], "spans": 0})
    pages[r["page"]]["spans"] += 1

res = []
t00 = time.time()
for i, p in enumerate(sorted(pages), 1):
    rec = dict(pages[p])
    t0 = time.time()
    try:
        strip, info = ps.presplit(PAGE % p, upscale=1)
        if strip is None:
            rec.update(detected=None, agree=False, why="no_strip")
        else:
            band = strip.convert("L")
            regs = NLR.detect_regions(band, prof)
            rec.update(detected=len(regs), agree=(len(regs) == rec["n_notes"]),
                       why="" if len(regs) == rec["n_notes"] else "count-mismatch")
    except Exception as e:
        rec.update(detected=None, agree=False, why="%s: %s" % (type(e).__name__, str(e)[:70]))
    rec["secs"] = round(time.time() - t0, 2)
    res.append(rec)
    if i % 25 == 0:
        ok = sum(1 for r in res if r["agree"])
        print("  %3d/%d pages  agree %d (%.0f%%)  %.0fs elapsed"
              % (i, len(pages), ok, 100.0 * ok / len(res), time.time() - t00), flush=True)

io.open(OUT, "w", encoding="utf-8").write(json.dumps(res, ensure_ascii=False, indent=1))
ok = [r for r in res if r["agree"]]
spans_ok = sum(r["spans"] for r in ok)
print("\npages: %d   agree: %d (%.0f%%)   spans on agreeing pages: %d of %d (%.0f%%)"
      % (len(res), len(ok), 100.0 * len(ok) / len(res), spans_ok, sum(r["spans"] for r in res),
         100.0 * spans_ok / sum(r["spans"] for r in res)))
print("why:", dict(Counter(r["why"] for r in res)))
print("delta detected-extractor:", dict(Counter((r["detected"] - r["n_notes"]) if r["detected"] is not None
                                                else "none" for r in res)))
print("agree by page status:", dict(Counter(r["status"] for r in ok)),
      "| all:", dict(Counter(r["status"] for r in res)))
print("wrote", OUT)
