# -*- coding: utf-8 -*-
"""Score the 2026-10-04 pad probe: does widening p912:n2's crop recover the signed span?

The question is a BOX question, not a reader question. `p912:n2`'s signature is two words and its ratified
span box covers one, so 14 of 19 arms transcribed that one word correctly and were scored `wrong` -- the
`clipped` class. The probe cuts the same span two ways in ONE run (the recorded baseline is two weeks old,
and comparing across runs would carry the confound the pairing removes) and sends both to the same 25 arms:

  base  the ratified A2 span box, as signed
  clip  the band-clip recipe: the box extended to the note band's own edges

A read is evidence only about the crop it was given, so the only thing this scores is whether the SAME arm
on the SAME pixels-but-wider returns the whole signature. Scoring uses the lane's own `classify()` and
`SEALED_TRUTH` -- the Hebrew-aperture-harness carve-out above `SEALED_TRUTH` is what permits a sealed
page here, and nothing is re-signed.

What this does NOT do: send anything (the reads are already recorded), re-sign anything, or generalise from
one span. One span cannot establish a recipe for 96 crops; it can only show whether the wider cut is safe
and whether it changes the verdict at all.
"""
import io
import json
import os
import sys
import time
from collections import Counter, defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import hebrew_aperture_diag as HAD                                         # noqa: E402
from clean_run import git_state, provisional, banner                       # noqa: E402

DV = "C:/Users/cnogr/git/dr-voluminous/reextract_vol1"
AUD = DV + "/audits"
READS = AUD + "/hebrew_pad_probe_reads_20261004.jsonl"
OUT = AUD + "/hebrew_pad_probe_result_20261004.json"
SPAN = "p912:n2"

GIT_START = git_state(_HERE)

L = [json.loads(l) for l in io.open(READS, encoding="utf-8") if l.strip()]
hdr = [d for d in L if d.get("kind") == "config_header"]
foot = [d for d in L if d.get("kind") == "padprobe_run_footer"]
assert len(hdr) == 1 and len(foot) == 1, "a probe with no header or no footer is not a run"
hdr, foot = hdr[0], foot[0]
assert foot.get("clean_run") is True and not foot.get("run_faulted"), \
    "the probe's own footer does not declare a clean, unfaulted run -- do not score it"

# SEALED_TRUTH values are (signed string, provenance tag) -- take the string, never retype it.
_t = HAD.SEALED_TRUTH[SPAN]
truth, truth_why = (_t if isinstance(_t, tuple) else (_t, "unknown-provenance"))
assert truth and HAD.HEB.search(truth), "no signed Hebrew for %s" % SPAN
assert len(truth.split()) == 2,     "%s's signature is the TWO-word case this probe exists for; it now has %d word(s), so either the "     "signature moved or the wrong span is being scored" % (SPAN, len(truth.split()))

reads = [d for d in L if d.get("kind") == "read" and d.get("model") not in HAD.DROPPED_ARMS]
errs = [d for d in L if d.get("kind") == "call_error"]
by = defaultdict(dict)
for d in reads:
    by[d["model"]][d["condition"]] = d

# Only arms with BOTH conditions can speak to the difference. An arm present in one condition only would
# make the comparison a floor, not an effect.
paired = {m: c for m, c in by.items() if "base" in c and "clip" in c}
dropped = {m: sorted(c) for m, c in by.items() if m not in paired}

cls = {m: {k: HAD.classify(d.get("hebrew") or "", truth) for k, d in c.items()}
       for m, c in paired.items()}
tally = {k: dict(Counter(v[k] for v in cls.values())) for k in ("base", "clip")}
moved = {m: (v["base"], v["clip"]) for m, v in cls.items() if v["base"] != v["clip"]}
gained = [m for m, v in cls.items() if v["clip"] == "exact" and v["base"] != "exact"]
lost = [m for m, v in cls.items() if v["base"] == "exact" and v["clip"] != "exact"]

ex = lambda k: sum(1 for v in cls.values() if v[k] == "exact")
n = len(paired)
print("span %s   paired arms %d   (dropped, one condition only: %s)" % (SPAN, n, dropped or "none"))
print("base (ratified span box): exact %d/%d  %s" % (ex("base"), n, tally["base"]))
print("clip (band-clip recipe) : exact %d/%d  %s" % (ex("clip"), n, tally["clip"]))
print("arms that MOVED: %d  -> gained exact %d, lost exact %d" % (len(moved), len(gained), len(lost)))
for m, (a, b) in sorted(moved.items()):
    print("   %-38s %s -> %s" % (m, a, b))
print("call errors: %s" % [(d.get("model"), d.get("condition")) for d in errs])
cost = (foot.get("budget_after", {}).get("usage", 0) or 0) - (hdr.get("budget_before", {}).get("usage", 0) or 0)
print("cost $%.4f   crops sent %s   note-box crops sent %s"
      % (cost, hdr.get("crops_archived"), hdr.get("note_box_crops_sent")))

# ---- what the two crops ARE, measured in pixels rather than inferred from the tally ---------------
# A vote cannot tell you which input was better; the ink can. This counts WORD RUNS by the column ink
# profile -- counting the reliable thing (gaps) rather than recognizing the unreliable one (letters).
def _ink(path, gap_min=10, run_min=8):
    from PIL import Image
    import numpy as np
    a = np.asarray(Image.open(path).convert("L"))
    ink = a < 128
    col = (ink.sum(axis=0) > 0)
    runs, cur, gap = [], None, 0
    for x, v in enumerate(col):
        if v:
            cur = x if cur is None else cur
            gap = 0
        elif cur is not None:
            gap += 1
            if gap >= gap_min:
                runs.append((cur, x - gap)); cur, gap = None, 0
    if cur is not None:
        runs.append((cur, len(col) - 1))
    wide = [r for r in runs if r[1] - r[0] >= run_min]
    return {"size": list(Image.open(path).size), "ink_px": int(ink.sum()),
            "ink_rows": int((ink.sum(axis=1) > 0).sum()), "rows": int(a.shape[0]),
            "word_runs": len(wide), "run_widths": [r[1] - r[0] for r in wide]}

GEOM = {k: _ink(v) for k, v in hdr["conditions"].items()}
for k, g in GEOM.items():
    print("%-5s %sx%s  ink %d px on %d/%d rows  word runs %d %s"
          % (k, g["size"][0], g["size"][1], g["ink_px"], g["ink_rows"], g["rows"],
             g["word_runs"], g["run_widths"]))
assert all(g["ink_px"] > 0 for g in GEOM.values()),     "a condition's crop is blank, so its reads are evidence about nothing"
# The finding, recorded as a measurement and not as a conclusion: the signature is two words, and on the
# PAD=12 crop the pad's foreign ink (the bottom of the line above) BRIDGES them into one column run, so
# the geometric argument for the band trim is independent of how the arms voted.
GEOM_NOTE = ("signature is %d words; PAD=12 resolves %d word run(s), band-clip resolves %d. A tally "
             "cannot see this and the ink cannot be voted on."
             % (len(truth.split()), GEOM["base"]["word_runs"], GEOM["clip"]["word_runs"]))
print(GEOM_NOTE)

GIT_END = git_state(_HERE)
print(banner(GIT_START, GIT_END))
json.dump({"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "git_start": GIT_START, "git_end": GIT_END,
           "provisional": provisional(GIT_START, GIT_END),
           "span": SPAN, "source": os.path.basename(READS),
           "probe_config_sha16": hdr.get("config_sha16"),
           "probe_clean_run": foot.get("clean_run"),
           "crops": hdr.get("crops_archived"), "crop_paths": hdr.get("conditions"),
           "truth_digest": hdr.get("truth_digest"), "truth_provenance": truth_why,
           "truth_words": len(truth.split()),
           "paired_arms": n, "dropped_arms_one_condition": dropped,
           "exact": {"base": ex("base"), "clip": ex("clip")},
           "tally": tally, "moved": moved, "gained_exact": gained, "lost_exact": lost,
           "call_errors": [{"model": d.get("model"), "condition": d.get("condition"),
                            "error": str(d.get("error"))[:120]} for d in errs],
           "cost_usd": round(cost, 4), "crop_geometry": GEOM, "geometry_note": GEOM_NOTE,
           "per_arm": {m: {"base": cls[m]["base"], "clip": cls[m]["clip"],
                           "applied": {k: paired[m][k].get("applied") for k in ("base", "clip")}}
                       for m in sorted(cls)}},
          io.open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("wrote", os.path.basename(OUT))
