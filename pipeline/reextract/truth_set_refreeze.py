# -*- coding: utf-8 -*-
"""Re-freeze the truth set: drop the recorded box faults, keep everything else, rename by content.

Chris, 2026-10-04 (after the cut): "drop the 14 and 3 as recorded faults with hashes; re-freeze under a
new hash; predictions stand as rates with the denominator noted."

A set is dropped FROM, never edited. The 96 set stays exactly where it is and keeps its name; this
writes a new set with a new content hash, and the drop record travels inside it -- span id, the fault
class, and the sha16 of the very crop the fault was measured on, so "why is this span not here" is
answerable from the set itself rather than from a report that may not travel with it.

TWO FAULT CLASSES, BOTH MEASURED, NEITHER A READING JUDGEMENT:

  no-line-of-type   14 spans whose crop holds no ink run thick enough to be a line of type. They are
                    the printed footnote rule. Nothing in them can be read, so a signature over them
                    would be a signature about geometry.
  mislocated-box    the duplicate-box locations. Two spans were handed ONE box and cut byte-identical
                    crops, and the crops hold roman-type transliteration, not Hebrew -- the script gate
                    said Hebrew about a transliteration. The localizer put the box somewhere the span
                    is not.

ON THE COUNT, AND I AM NAMING THE DEVIATION. Chris said "the 14 and 3 ... re-freeze at 79", which is
96 - 14 - 3. The three transliteration FAULTS are three locations, but the SET holds two spans at each
of them -- `p283:n0s1` and `p283:n0s2` are different spans sharing one box and one crop. Dropping one
of each pair would leave three spans in a signing set pointing at a crop with no Hebrew in it, which is
the thing the drop exists to prevent. So the rule applied here is BY FAULT, not by count: every span at
a faulted location goes. That is 6 spans, and the set re-freezes at **76**, not 79. Say the word and
the 79-variant is one re-run; it is named here rather than quietly resolved because a truth set's size
is not a detail.

WHAT STAYS. The 22 over-full crops stay, per Chris: a box holding more than the span is a redraw
question, but the pixels are readable and he signs every Hebrew span visible in each crop. The signing
skeleton therefore takes a LIST of readings per crop, not one.

PREDICTIONS. They were registered over 96 and are not re-registered here -- rewriting a prediction
after seeing the population is how a prediction stops being one. They are carried forward as RATES
with both denominators stated: what was predicted over 96, and what the same rate implies over 76.
"""
import hashlib
import io
import json
import os
import re
import sys
import time
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from clean_run import git_state, provisional, banner                       # noqa: E402

DV = "C:/Users/cnogr/git/dr-voluminous/reextract_vol1"
AUD = DV + "/audits"
SRC_SHA = "4e73b10d46a41f4a"
SRC = AUD + "/truth_set96_%s.json" % SRC_SHA
CUT = AUD + "/truthset96_cut_%s.json" % SRC_SHA

READABLE = re.compile(u"[\u0590-\u05FF\uFB1D-\uFB4F\u0370-\u03FF\u1F00-\u1FFF]")

GIT_START = git_state(_HERE)

src = json.load(io.open(SRC, encoding="utf-8"))
cut = json.load(io.open(CUT, encoding="utf-8"))
assert src.get("provisional") is False and cut.get("provisional") is False, \
    "a provisional artifact cannot be the basis of a frozen set"
assert src["set_sha16"] == SRC_SHA and src["n"] == 96, "this is not the frozen 96"

flags = cut["geometry_flags"]
sha = {r["span_id"]: r["crop"]["sha16"] for r in cut["rows"] if r.get("crop")}
NOTYPE = [x["span_id"] for x in flags["no_line_of_type"]]
MISLOC = sorted({sid for ids in flags["duplicate_box"].values() for sid in ids})
assert NOTYPE and MISLOC, "the fault lists are empty -- the cut artifact is not the one that found them"
assert not (set(NOTYPE) & set(MISLOC)), "a span is in both fault classes; the drop record would lie"

DROP = ([{"span_id": s, "fault": "no-line-of-type",
          "why": "the crop holds no ink run thick enough to be a line of type: it is the printed "
                 "footnote rule. Measured against MIN_BAND_PX.",
          "crop_sha16": sha.get(s)} for s in sorted(NOTYPE)] +
        [{"span_id": s, "fault": "mislocated-box",
          "why": "two spans share one box and cut byte-identical crops, and the crop holds roman-type "
                 "transliteration rather than Hebrew. The script gate was a false positive and the "
                 "localizer placed the box where the span is not.",
          "crop_sha16": sha.get(s)} for s in MISLOC])
assert all(d["crop_sha16"] for d in DROP), \
    "a dropped span has no crop hash -- then the fault was not measured on a crop that exists, and the " \
    "drop record cannot be checked against anything"

dropped = {d["span_id"] for d in DROP}
rows = [r for r in src["rows"] if r["span_id"] not in dropped]
assert len(rows) == len(src["rows"]) - len(dropped), "a drop did not match a row in the set"
assert len(rows) == 76, "expected 76 after dropping %d of 96, got %d" % (len(dropped), len(rows))

ident = [[r["span_id"], r["page"], r["note_index"], r["hebrew"], list(r["box"])] for r in rows]
SHA16 = hashlib.sha256(json.dumps(ident, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
assert SHA16 != SRC_SHA, "the re-frozen set hashes the same as the set it was drawn from"
OUT = AUD + "/truth_set%d_%s.json" % (len(rows), SHA16)
SIGN = AUD + "/truth_set%d_%s_signer.json" % (len(rows), SHA16)

one = [r for r in rows if r["words"] == 1]
multi = [r for r in rows if r["words"] > 1]
P = src["predictions"]
PREDICT = {
    "status": "CARRIED FORWARD, NOT RE-REGISTERED. Rewriting a prediction after seeing the population "
              "is how it stops being one.",
    "standard": P["standard"],
    "registered_over": {"set": SRC_SHA, "n": 96, "one_word": P["one_word"]["n"],
                        "multi_word": P["multi_word"]["n"]},
    "denominator_note": "the rates were registered over a population that included 17 spans later "
                        "found to have faulted boxes. 14 of them could not be read at all, so scoring "
                        "them either way would have scored geometry as reading. The rates below are "
                        "the SAME rates against the signable denominator.",
    "one_word": {"n": len(one), "predicted_exact_pct": P["one_word"]["predicted_exact_pct"],
                 "predicted_exact_n": round(P["one_word"]["predicted_exact_pct"] / 100.0 * len(one)),
                 "basis": P["one_word"]["basis"]},
    "multi_word": {"n": len(multi), "predicted_exact_pct": P["multi_word"]["predicted_exact_pct"],
                   "predicted_exact_n": round(P["multi_word"]["predicted_exact_pct"] / 100.0 * len(multi)),
                   "basis": P["multi_word"]["basis"]},
    "if_wrong": P["if_wrong"],
}

LIMITS = dict(src["limits"])
LIMITS["drawn_from"] = ("re-frozen from set %s (96) by dropping %d spans at measured box faults: %d "
                        "no-line-of-type, %d mislocated-box. No span was dropped for how it reads."
                        % (SRC_SHA, len(dropped), len(NOTYPE), len(MISLOC)))
LIMITS["localizer_mislocation_measured"] = (
    "the localizer's BOX verdict is NOT evidence that the box holds the span: 14 of 96 (15%) sat on "
    "the printed rule and 3 locations (6 spans) on roman transliteration. Any funnel figure claiming "
    "0 mislocated is WITHDRAWN.")
LIMITS["over_full_crops_retained"] = (
    "%d crops resolve more word runs than the extractor claims words -- the box holds material beyond "
    "the span. KEPT by Chris's ruling: the pixels are readable and every Hebrew span visible in the "
    "crop is signed, so the signing record takes a LIST of readings per crop."
    % len(flags["runs_exceed_words"]))

meta = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "set_sha16": SHA16, "n": len(rows),
        "source": {"set": os.path.basename(SRC), "cut": os.path.basename(CUT),
                   "pool_funnel": src["source"]["pool_funnel"]},
        "page_numbering": src["page_numbering"],
        "ruling": "Chris, 2026-10-04 after the cut: drop the recorded faults with hashes, re-freeze "
                  "under a new hash, predictions stand as rates with the denominator noted. The "
                  "over-full crops stay and all visible Hebrew is signed.",
        "dropped_from_96": DROP,
        "deviation": "Chris said 79 (96 - 14 - 3). The three transliteration faults are three "
                     "LOCATIONS and the set holds two spans at each, so dropping by fault removes 6 "
                     "spans and lands at 76. Dropping one of each pair would leave three spans "
                     "pointing at a crop with no Hebrew in it. Named, not resolved quietly.",
        "limits": LIMITS, "predictions": PREDICT,
        "strata": {"one_word": len(one), "multi_word": len(multi),
                   "words": dict(Counter(min(r["words"], 4) for r in rows)),
                   "nikud": dict(Counter(r["nikud"] for r in rows)),
                   "stitch_page": dict(Counter(r["stitch_page"] for r in rows))}}

sign_rows = [{"span_id": r["span_id"], "page": r["page"], "note_index": r["note_index"],
              "notes_on_page": r["notes_on_page"], "box_strip": list(r["box"]),
              "band": r["band"], "band_w": r["band_w"], "crop_sha16": sha.get(r["span_id"])}
             for r in rows]
signer = {"generated": meta["generated"], "set_sha16": SHA16, "n": len(sign_rows),
          "page_numbering": meta["page_numbering"],
          "instruction": "Sign each span from its CROP. The extracted candidate is deliberately absent: "
                         "the previous truth set was 30% wrong in the direction of the candidate, once "
                         "affirmed verbatim. Where a crop holds more than one Hebrew span, sign every "
                         "one you can see. Write what the pixels show, or abstain.",
          "withheld": ["hebrew", "note text", "any extracted reading", "the extractor's word count"],
          "rows": sign_rows}

blob = json.dumps(signer, ensure_ascii=False, sort_keys=True)
hit = READABLE.search(blob)
assert not hit, "the signer view contains readable Hebrew/Greek at offset %d" % (hit.start() if hit else -1)
assert READABLE.search(rows[0]["hebrew"]), \
    "the withholding check cannot match the very Hebrew it exists to exclude -- it would pass on anything"

GIT_END = git_state(_HERE)
for d, p in ((dict(meta, provisional=provisional(GIT_START, GIT_END), git_start=GIT_START,
                   git_end=GIT_END, rows=rows), OUT),
             (dict(signer, provisional=provisional(GIT_START, GIT_END)), SIGN)):
    json.dump(d, io.open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print("re-frozen %s -> %s   n %d -> %d   dropped %d (%d no-line-of-type, %d mislocated-box)"
      % (SRC_SHA, SHA16, 96, len(rows), len(dropped), len(NOTYPE), len(MISLOC)))
print("one-word %d   multi-word %d   nikud %d   stitch-page %d"
      % (len(one), len(multi), sum(1 for r in rows if r["nikud"]),
         sum(1 for r in rows if r["stitch_page"])))
print("predictions carried: one-word %d%% -> %d/%d   multi-word %d%% -> %d/%d"
      % (PREDICT["one_word"]["predicted_exact_pct"], PREDICT["one_word"]["predicted_exact_n"], len(one),
         PREDICT["multi_word"]["predicted_exact_pct"], PREDICT["multi_word"]["predicted_exact_n"],
         len(multi)))
print("DEVIATION: Chris said 79; dropping BY FAULT removes both spans at each of the 3 transliteration "
      "locations, so this is 76.")
print(banner(GIT_START, GIT_END))
print("wrote", os.path.basename(OUT))
print("wrote", os.path.basename(SIGN))
