"""Lock the prediction for the wrong-row classification (advisor ruling 3, 2026-10-18).

Written and committed BEFORE the classification build exists and before any crop has been opened in
this session.  The basis is pre-run knowledge only: the signed set's own population flags (box_fault,
partial_in_crop, editorial_insertion, multi_word, sic, corrected_heavy), the per-arm wrong lists from
run 501ab577a18a6785, and the fact that exactly one of opus's 13 wrong rows was read non-wrong by qwen.
No read string was inspected, no edit distance computed and no crop or strip viewed to write this.

Hash rule: sha256 over canonical JSON (sort_keys=True, separators=(',',':'), ensure_ascii=False)
encoded UTF-8, first 16 hex, over this object with `self_sha16` and `hash_rule` removed.

ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).
"""
import hashlib
import io
import json
import pathlib

A = pathlib.Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits")

READER = ("confusable", "plene", "substitution", "short", "fabrication")
CROP = ("edge-cut", "neighbour-ink", "mid-word-start", "wrong-line", "over-full", "index-shift")

OPUS_13 = ["p190:n0", "p233:n4", "p254:n1", "p326:n11", "p381:n1", "p428:n0", "p442:n0",
           "p493:n3", "p594:n0", "p622:n0", "p798:n0", "p803:n0", "p831:n2"]

# per-row predicted class, with the pre-run reason.  More falsifiable than the split alone.
PER_ROW = {
    "p493:n3": ["crop", "box_fault AND partial_in_crop AND corrected_heavy: ratified geometry fault"],
    "p594:n0": ["crop", "box_fault AND partial_in_crop AND sic: ratified geometry fault"],
    "p803:n0": ["crop", "box_fault AND partial_in_crop: ratified geometry fault"],
    "p190:n0": ["crop", "partial_in_crop, 0/4 exact on opus in BOTH channels; a cut, not a reading"],
    "p233:n4": ["reader", "editorial_insertion, no geometry flag"],
    "p428:n0": ["reader", "editorial_insertion + multi_word, no geometry flag"],
    "p831:n2": ["reader", "editorial_insertion, no geometry flag"],
    "p381:n1": ["reader", "multi_word only; also carries qwen nikud, a reader behaviour"],
    "p254:n1": ["reader", "no flag; wrong on both arms bare and in context"],
    "p326:n11": ["reader", "no flag"],
    "p442:n0": ["reader", "no flag; one of the two bare agreement-and-wrong rows"],
    "p622:n0": ["reader", "no flag; wrong on both arms bare and in context"],
    "p798:n0": ["reader", "no flag; wrong on both arms bare and in context"],
}

P = {
    "kind": "classification_prediction",
    "for": "advisor ruling 3, 2026-10-18 -- reader-vs-crop class per wrong row",
    "run_classified": "501ab577a18a6785",
    "page_convention": "ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88)",
    "locked_before": "any crop opened, any read string inspected, any edit distance computed",

    "class_vocabulary": {"reader": list(READER), "crop": list(CROP),
                         "constraint": "exactly one class per (row, arm); if a row needs two to "
                                       "describe it, that is reported as a defect in the vocabulary, "
                                       "not forced into one"},

    "unit": {
        "assignment_unit": "(row, arm) -- a reader cause is a property of one arm's reading, so 13 "
                           "opus-bare + 18 qwen-bare = 31 assignments over 19 distinct rows",
        "registered_unit": "the ruling registers a split for THE 13 (opus bare); that is what the "
                           "numbers below predict",
    },

    "REGISTERED_1_split_of_the_13": {
        "crop": 4, "reader": 9,
        "crop_ids": sorted(k for k, v in PER_ROW.items() if v[0] == "crop"),
        "claim": "crop class does NOT dominate opus's 13; it is confined to the rows the signed set "
                 "ALREADY flags as geometry faults, plus nothing else",
        "basis": "all 3 box_fault rows and all 4 partial_in_crop rows sit inside the 13; the other 9 "
                 "carry no geometry flag at all",
    },

    "REGISTERED_2_are_both_AW_rows_crop_class": {
        "answer": "NO -- exactly one of the two",
        "p493:n3": "crop (box_fault, ratified)",
        "p442:n0": "reader (no geometry flag)",
        "what_follows_if_wrong": "if BOTH land crop class, the agreement rule stands untouched and the "
                                 "finding is that the input guard passed two crops it should have "
                                 "refused -- I then owe the property that would have refused them, "
                                 "stated as a computable predicate, not a description",
        "what_follows_if_right": "the agreement rule is NOT rescued by geometry: at least one "
                                 "agreement-and-wrong row is two readers converging on a plausible "
                                 "wrong word from legible pixels, which is the substitution class and "
                                 "the thing cross-arm agreement cannot be confidence about",
    },

    "per_row_predicted_class": PER_ROW,

    "REGISTERED_3_edit_distance": {
        "claim": "base-consonant edit distance separates the two classes: median <= 2 for reader rows, "
                 ">= 3 for crop rows, because a cut loses whole letters while a misread swaps one",
        "NOT_a_classifier": "distance is REPORTED beside each row and is never the rule that assigns "
                            "the class.  Crop class is assigned on geometry (box/ink/position) only, "
                            "which is also the basis Chris audits.  If distance were allowed to "
                            "assign, the prediction above would be self-fulfilling.",
    },

    "discriminator_i_intend_to_use": {
        "rule": "a crop-class cause is a property of the CROP, which both arms receive; so a row that "
                "ONE arm read exactly cannot be crop class -- the exact read is proof the pixels carry "
                "the signature (the p628:n2 logic, run in reverse)",
        "known_conflict": "p594:n0 is the one row of the 13 that qwen read non-wrong, AND it is a "
                          "ratified box_fault.  My two criteria disagree on exactly this row.  I "
                          "predict geometry wins (crop), and register the consequence: if p594:n0 is "
                          "crop class while qwen read it exactly, then 'one arm read it exactly' is "
                          "NOT sufficient to refute crop class, and the discriminator above is wrong "
                          "and must not be used on the remaining rows.",
    },

    "falsifiers": {
        "F1": "crop class reaches 7 or more of the 13 (dominates): my reading is wrong, the 13 go to "
              "A2 as fault instances with their classes, and B's open list collapses to the "
              "sic/expected_match consumer plus the three box redraws",
        "F2": "0 of the 13 are crop class: then box_fault does not predict a wrong read at all, and "
              "the three-box-redraw debt is not the priority this lane has been treating it as",
        "F3": "both AW rows land crop class (registered 2 inverted)",
        "F4": "any (row, arm) needs two classes, or none of the twelve fits: the vocabulary is not a "
              "partition of this population and I report that instead of forcing a fit",
        "F5": "the two classes' distance medians come out the wrong way round (reader > crop): the "
              "mechanism story in registered 3 is backwards",
    },

    "what_this_prediction_does_NOT_cover": [
        "the 18 qwen-bare rows get no registered split -- 6 of them are rows opus read exactly, and I "
        "have no pre-run basis for predicting a weaker arm's failure mode",
        "the signed string is the standard and the standard is a claim too: 6 of 20 earlier signed "
        "truths were wrong.  A row classified 'reader' may be a row where the SIGNATURE is wrong, which "
        "is a third outcome neither class names.  I will flag such rows rather than classify them.",
        "no re-cut is possible to test a crop-class call (cut_truth_set_crops writes into the approved "
        "corpus in place), so every crop-class assignment is made on the crop AS CUT plus the strip, "
        "never on a re-cut comparison",
    ],
}

P["hash_rule"] = ("sha256 over canonical JSON of this object with self_sha16 and hash_rule removed, "
                  "sort_keys=True, separators=(',',':'), ensure_ascii=False, encoded UTF-8; first 16 hex")
body = {k: v for k, v in P.items() if k not in ("self_sha16", "hash_rule")}
P["self_sha16"] = hashlib.sha256(
    json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
).hexdigest()[:16]

dest = A / ("PREDICTIONS_classify45_%s.json" % P["self_sha16"])
assert not dest.exists(), "refusing to clobber %s" % dest.name
io.open(dest, "w", encoding="utf-8", newline="\n").write(
    json.dumps(P, indent=1, ensure_ascii=False) + "\n")

print("locked", dest.name)
print("split of the 13: crop %d / reader %d" % (P["REGISTERED_1_split_of_the_13"]["crop"],
                                                P["REGISTERED_1_split_of_the_13"]["reader"]))
print("crop ids:", P["REGISTERED_1_split_of_the_13"]["crop_ids"])
print("both AW crop class?", P["REGISTERED_2_are_both_AW_rows_crop_class"]["answer"])
print("per-row predictions:", len(PER_ROW), "covering the 13:", sorted(PER_ROW) == sorted(OPUS_13))
print("self_sha16", P["self_sha16"])
