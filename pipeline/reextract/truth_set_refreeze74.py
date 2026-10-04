# -*- coding: utf-8 -*-
"""Re-freeze at 74: drop the two script-gate faults Chris ruled on, carry the 96 drop record forward.

Chris, 2026-10-04: "p935:n1 and p750:n0 leave the set as script-gate faults, same class as the 3 DUP
pairs: that's five roman-transliteration false positives. Re-freeze at 74."

A set is dropped FROM, never edited. The 96 set and the 76 set both stay exactly where they are and
keep their names. This writes a THIRD set with its own content hash, and it carries the 96 -> 76 drop
record forward verbatim so that the provenance of all 22 absent spans is answerable from ONE file:
span id, fault class, and the sha16 of the crop the fault was measured on.

THE FAULT CLASS IS ONE CLASS, AND IT IS WIDER THAN THE RULING NAMES IT. Chris wrote "five
roman-transliteration false positives (Bereshit, Torat, Negaim, Sepher)" -- four names for five faults,
and the fifth is not a transliteration. The three DUP locations were montaged and read:

  p283 (printed 195)   "Bereshit"   italic roman transliteration, in the note text
  p784 (printed 696)   "Torat"      italic roman transliteration, in the note text
  p315 (printed 227)   "G g 2"      NOT a transliteration: roman letters and a digit, and the last
                                    ink on the page (last inked row 4789 of 5400, nothing below
                                    y=4800). That is a printer's signature mark -- page FURNITURE.

So the defect is not "italic Latin transliterations of Hebrew words are flagged as Hebrew". It is
**roman type is flagged as Hebrew**, and the population includes page furniture, which puts it in the
same family as the 14 printed-rule crops rather than in a separate one. Named here because a defect
recorded one notch too narrow is a defect that will be re-found.

p935:n1 ("Negaim, c.", 2 words claimed, nikud claimed) and p750:n0 ("Sepher", 1 word claimed) are the
two found by eye in the surviving 76. Neither is a DUP: their boxes are not shared and their crops are
not byte-identical with anything. They are the same gate fault reached by a different route, which is
why they are recorded under one class with the route stated per span.

PREDICTIONS. Still not re-registered -- rewriting a prediction after seeing the population is how it
stops being one. Carried as RATES with every denominator in the chain stated: registered over 96,
implied over 76, implied over 74.

ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).
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
SRC_SHA = "13e053b86b75a195"
SRC = AUD + "/truth_set76_%s.json" % SRC_SHA
CUT = AUD + "/truthset76_cut_%s.json" % SRC_SHA

READABLE = re.compile(u"[\u0590-\u05FF\uFB1D-\uFB4F\u0370-\u03FF\u1F00-\u1FFF]")

GIT_START = git_state(_HERE)

src = json.load(io.open(SRC, encoding="utf-8"))
cut = json.load(io.open(CUT, encoding="utf-8"))
assert src.get("provisional") is False and cut.get("provisional") is False, \
    "a provisional artifact cannot be the basis of a frozen set"
assert src["set_sha16"] == SRC_SHA and src["n"] == 76, "this is not the frozen 76"
assert cut["set_sha16"] == SRC_SHA, "the cut was taken over a different set than the one being dropped from"

sha = {r["span_id"]: r["crop"]["sha16"] for r in cut["rows"] if r.get("crop")}

# Each span's own route to the same gate fault, and what the crop shows. The "shows" string is a
# reading of the PIXELS, recorded as such: it is why the span is out, so it has to be inspectable.
RULED = [
    ("p935:n1", u'roman "Negaim, c."',
     "found by eye in the surviving 76. One line of type, roman. The extractor claims 2 Hebrew words "
     "with nikud, and the crop resolves 2 word runs, so the word-run check ACTIVELY ENDORSED it: a "
     "count agreeing with a claim is not evidence about script."),
    ("p750:n0", u'roman "Sepher"',
     "found by eye in the surviving 76. One line of type, roman. The extractor claims 1 Hebrew word. "
     "Passed all three box-fault filters."),
]
for _sid, _shows, _why in RULED:
    assert _sid in sha, "%s is not in the cut -- its fault was not measured on a crop that exists" % _sid
    assert not any(d["span_id"] == _sid for d in src["dropped_from_96"]), \
        "%s was already dropped once; dropping it again would double-count the funnel" % _sid

DROP74 = [{"span_id": sid, "fault": "script-gate-false-positive", "shows": shows, "why": why,
           "route": "eyeball on the 76-span crops, 2026-10-04", "crop_sha16": sha[sid]}
          for sid, shows, why in RULED]
assert all(d["crop_sha16"] for d in DROP74), "a dropped span has no crop hash"

dropped = {d["span_id"] for d in DROP74}
rows = [r for r in src["rows"] if r["span_id"] not in dropped]
assert len(rows) == len(src["rows"]) - len(dropped), "a drop did not match a row in the set"
assert len(rows) == 74, "expected 74 after dropping %d of 76, got %d" % (len(dropped), len(rows))

ident = [[r["span_id"], r["page"], r["note_index"], r["hebrew"], list(r["box"])] for r in rows]
SHA16 = hashlib.sha256(json.dumps(ident, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
assert SHA16 not in (SRC_SHA, "4e73b10d46a41f4a"), "the re-frozen set hashes the same as one it came from"
OUT = AUD + "/truth_set%d_%s.json" % (len(rows), SHA16)
SIGN = AUD + "/truth_set%d_%s_signer.json" % (len(rows), SHA16)

one = [r for r in rows if r["words"] == 1]
multi = [r for r in rows if r["words"] > 1]
P = src["predictions"]
R96 = P["registered_over"]
PREDICT = {
    "status": "CARRIED FORWARD TWICE, NOT RE-REGISTERED. Rewriting a prediction after seeing the "
              "population is how it stops being one.",
    "standard": P["standard"],
    "registered_over": R96,
    "denominator_chain": [
        {"set": R96["set"], "n": R96["n"], "one_word": R96["one_word"], "multi_word": R96["multi_word"],
         "note": "where the rates were registered"},
        {"set": SRC_SHA, "n": 76, "one_word": len([r for r in src["rows"] if r["words"] == 1]),
         "multi_word": len([r for r in src["rows"] if r["words"] > 1]),
         "note": "after 20 measured box faults"},
        {"set": SHA16, "n": len(rows), "one_word": len(one), "multi_word": len(multi),
         "note": "after 2 script-gate faults; the denominator that will be scored"},
    ],
    "denominator_note": "the rates were registered over a population that later lost 22 spans to box "
                        "and gate faults. Scoring those would have scored GEOMETRY as reading. The "
                        "rates below are the SAME rates against the signable denominator; the chain "
                        "above is every denominator they have passed through.",
    "one_word": {"n": len(one), "predicted_exact_pct": P["one_word"]["predicted_exact_pct"],
                 "predicted_exact_n": round(P["one_word"]["predicted_exact_pct"] / 100.0 * len(one)),
                 "basis": P["one_word"]["basis"]},
    "multi_word": {"n": len(multi), "predicted_exact_pct": P["multi_word"]["predicted_exact_pct"],
                   "predicted_exact_n": round(P["multi_word"]["predicted_exact_pct"] / 100.0 * len(multi)),
                   "basis": P["multi_word"]["basis"]},
    "if_wrong": P["if_wrong"],
}

LIMITS = dict(src["limits"])
LIMITS["drawn_from"] = (
    "re-frozen from set %s (76), itself re-frozen from %s (96). 20 spans dropped at measured box "
    "faults (14 no-line-of-type, 6 mislocated-box at 3 locations) and 2 at script-gate faults found by "
    "eye. No span has been dropped for how it READS." % (SRC_SHA, "4e73b10d46a41f4a"))
LIMITS["script_gate_defect"] = (
    "NAMED DEFECT: the script gate asks whether the TEXT is Hebrew-ish and has no way to ask what "
    "script the PIXELS are in, so roman type is flagged as Hebrew. 5 faults at 5 locations in 96: "
    "Bereshit (p283), Torat (p784), Negaim (p935), Sepher (p750) are roman transliterations of Hebrew "
    "words; 'G g 2' (p315) is a printer's signature mark -- page FURNITURE, not a transliteration, and "
    "the last ink on printed page 227. Chris's ruling named the class 'italic Latin transliterations'; "
    "the measured population is wider than that and overlaps the printed-rule class.")
LIMITS["script_gate_not_a_rate"] = (
    "5 of 96 is NOT the rate. 3 were caught because two spans shared one box, which is a geometry "
    "signal and not a script one; the other 2 were caught by looking at 12 crops. The class has no "
    "detector, so its size in the remaining 74 is unknown and the only honest statement is a floor.")
LIMITS["eyeball_provenance"] = (
    "p935:n1 and p750:n0 are out on an EYEBALL, not a measurement, by Chris's explicit word. That is a "
    "different kind of warrant from the 20 before them and the record says so per span.")
LIMITS["one_crop_recipe"] = (
    "every span in this set is cut at PAD=12 with NO band-clip -- the same recipe as the 19 already "
    "signed, so the two sets are comparable. The band-clip is withdrawn as a set recipe (Chris, "
    "2026-10-04) and survives as a per-span tool only.")

meta = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "set_sha16": SHA16, "n": len(rows),
        "source": {"set": os.path.basename(SRC), "cut": os.path.basename(CUT),
                   "root_set": "truth_set96_4e73b10d46a41f4a.json",
                   "pool_funnel": src["source"]["pool_funnel"]},
        "page_numbering": src["page_numbering"],
        "ruling": "Chris, 2026-10-04: band-clip withdrawn as a set recipe, all crops at PAD=12 like "
                  "the 19; drop p935:n1 and p750:n0 as script-gate faults; record the roman-type false "
                  "positives as a named script-gate defect; re-freeze at 74 under a new hash; "
                  "predictions stand as rates.",
        "dropped_here": DROP74,
        "dropped_from_96": src["dropped_from_96"],
        "drop_accounting": {"root_n": 96, "dropped_from_96": len(src["dropped_from_96"]),
                            "dropped_here": len(DROP74), "n": len(rows)},
        "limits": LIMITS, "predictions": PREDICT,
        "strata": {"one_word": len(one), "multi_word": len(multi),
                   "words": dict(Counter(min(r["words"], 4) for r in rows)),
                   "nikud": dict(Counter(r["nikud"] for r in rows)),
                   "stitch_page": dict(Counter(r["stitch_page"] for r in rows))}}
assert (meta["drop_accounting"]["root_n"] - len(src["dropped_from_96"]) - len(DROP74)) == len(rows), \
    "the drop accounting does not reach the set size from the root set"

sign_rows = [{"span_id": r["span_id"], "page": r["page"], "note_index": r["note_index"],
              "notes_on_page": r["notes_on_page"], "box_strip": list(r["box"]),
              "band": r["band"], "band_w": r["band_w"], "crop_sha16": sha.get(r["span_id"])}
             for r in rows]
signer = {"generated": meta["generated"], "set_sha16": SHA16, "n": len(sign_rows),
          "page_numbering": meta["page_numbering"],
          "instruction": "Sign each span from its CROP. The extracted candidate is deliberately absent: "
                         "the previous truth set was 30% wrong in the direction of the candidate, once "
                         "affirmed verbatim. Sign every Hebrew span you can SEE in the crop. Never sign "
                         "a word the crop edge cuts -- in 19 of these crops a neighbouring word on the "
                         "same line is sliced by the pad, and a fragment signed as a word is a wrong "
                         "truth. Write what the pixels show, or abstain.",
          "withheld": ["hebrew", "note text", "any extracted reading", "the extractor's word count"],
          "rows": sign_rows}
assert all(r["crop_sha16"] for r in sign_rows), "a signable row has no crop hash"

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

print("re-frozen %s -> %s   n %d -> %d   dropped %d script-gate faults"
      % (SRC_SHA, SHA16, src["n"], len(rows), len(DROP74)))
print("provenance in one file: 96 - %d box faults - %d gate faults = %d"
      % (len(src["dropped_from_96"]), len(DROP74), len(rows)))
print("one-word %d   multi-word %d   nikud %d   stitch-page %d"
      % (len(one), len(multi), sum(1 for r in rows if r["nikud"]),
         sum(1 for r in rows if r["stitch_page"])))
print("predictions carried: one-word %d%% -> %d/%d   multi-word %d%% -> %d/%d"
      % (PREDICT["one_word"]["predicted_exact_pct"], PREDICT["one_word"]["predicted_exact_n"], len(one),
         PREDICT["multi_word"]["predicted_exact_pct"], PREDICT["multi_word"]["predicted_exact_n"],
         len(multi)))
print("CORRECTION TO THE RULING: 4 of the 5 are transliterations; p315 shows 'G g 2', a printer's "
      "signature mark. The defect is roman type flagged as Hebrew, furniture included.")
print(banner(GIT_START, GIT_END))
print("wrote", os.path.basename(OUT))
print("wrote", os.path.basename(SIGN))
