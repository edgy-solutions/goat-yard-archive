# -*- coding: utf-8 -*-
"""Can the localizer put a box on a census span at all? Local compute only -- no outbound call.

score_localizer.py measures LOCATED/ABSTAIN/MISLOCATE against the 30 ratified boxes using the SIGNED text.
That is the wrong input for the draw: the draw's run_text comes from the frozen apparatus, which is right 12
times out of 30 where we can check. A drifted row asks the localizer to find a string that is not on the page.
This measures the abstain rate on the input the draw would actually use, over a random sample of the 696
that excludes every span with a signed verdict and every sealed page.

No crop is written, nothing is sent, the tree is not touched. Scratchpad only.
"""
import io
import json
import random
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

A = "C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits/"
PAGE = "C:/Users/cnogr/git/dr-voluminous/commentary/volume1/page%d_image1.png"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 24

# The committed artifacts, by their committed names. Not a session scratchpad: a script in the repo must be
# able to reproduce the artifact beside it in the repo, and the dated filename is deliberate -- these are
# dated observations of a frozen apparatus run, so a rerun under a new date writes a NEW file rather than
# quietly replacing the one an ADR cites.
DV = "C:/Users/cnogr/git/dr-voluminous/reextract_vol1"
AUD = DV + "/audits"
CENSUS = AUD + "/hebrew_span_census_20261004.json"
OUT = AUD + "/localizer_feasibility_20261004.json"

rows = json.load(io.open(CENSUS, encoding="utf-8"))["rows"]
signed = {json.loads(l)["span_id"] for l in io.open(A + "span_box_verdicts_20260906.jsonl",
                                                   encoding="utf-8") if l.strip()}
sealed_pages = {102, 217, 293, 362, 423, 427, 491, 596, 726, 897, 912}     # pages of the sealed/ratified 19
pool = [r for r in rows
        if r["span_id"] not in signed
        and r["span_id"].split("s")[0] not in signed            # multi-run children of a signed id
        and r["page"] not in sealed_pages]
print("pool after excluding signed ids and sealed pages: %d of %d" % (len(pool), len(rows)))

random.seed(20261004)                                           # the draw's own seed comes later; this is a probe
sample = random.sample(pool, N)
prof = ASM.load_profile(os.path.join(_HERE, "book_profile.gill.yaml"))
assert prof, "no profile -- locate_span would take None and die on .get"

res = []
for i, r in enumerate(sorted(sample, key=lambda x: x["page"]), 1):
    t0 = time.time()
    try:
        strip, info = ps.presplit(PAGE % r["page"], upscale=1)
        if strip is None:
            res.append((r, "NO_STRIP", "presplit returned no apparatus strip", 0))
            continue
        band = strip.convert("L")
        box, st = NLR.locate_span(band, r["note_index"] - 1, r["hebrew"], r["notes_on_page"], prof)
        res.append((r, "BOX" if box else "ABSTAIN", (str(st) if box is None else str(box)), time.time() - t0))
    except Exception as e:
        res.append((r, "ERROR", "%s: %s" % (type(e).__name__, str(e)[:90]), time.time() - t0))
    print("  %2d/%d %-12s %-8s %s" % (i, N, res[-1][0]["span_id"], res[-1][1], res[-1][2][:70]))

c = Counter(k for _r, k, _d, _t in res)
print("\n%s" % dict(c))
print("box rate: %d/%d" % (c["BOX"], len(res)))
print("abstain reasons:", dict(Counter(d.split(":")[0] for _r, k, d, _t in res if k == "ABSTAIN")))
print("errors:", dict(Counter(d.split(":")[0] for _r, k, d, _t in res if k == "ERROR")))
io.open(OUT, "w", encoding="utf-8").write(json.dumps(
    [{"span_id": r["span_id"], "page": r["page"], "note_index": r["note_index"],
      "notes_on_page": r["notes_on_page"], "hebrew": r["hebrew"], "words": r["words"],
      "letters": r["letters"], "nikud": r["nikud"], "verdict": k, "detail": d, "secs": round(t, 2)}
     for r, k, d, t in res], ensure_ascii=False, indent=1))
print("wrote", OUT)
