# -*- coding: utf-8 -*-
u"""Register the exemplar-band rule and its prediction BEFORE the rule is implemented.

Chris's ruling of 2026-11-16 on the yod question: do not lower MIN_BAND_PX. "One line of type"
is a property of the WORD, so the band check moves to the union of the word's glyph boxes, and
each glyph box is then asked only whether it is inside that band and non-blank. The ruling also
says: lock a prediction that no currently accepted record changes.

This module writes that lock. It does NOT implement the rule and it does NOT compute a single
verdict under it -- a lock written after the measurement is not a lock, and a module that can
see the answer while stating the prediction is the same defect in slower motion. The only thing
it reads is the status quo, which is already known and already in the report: sig_load today
accepts 10 signature records and refuses one, p309's yod, for an ink run of 18px under a 20px
floor.

The artifact is content-addressed by the hash of its own JSON, per ruling 5: UTF-8 bytes with
ensure_ascii=False. An approval record is named by what it describes.

ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).
"""
import hashlib
import io
import json
import sys

import hebrew_glyph_card as C
from write_scope import assert_inside

OUT_DIR = C.D.DATA   # the audits directory: SIGS and the other locks live here

RULE = [
    u"1. The word's extent is the union rect of every box in `letter_boxes` TOGETHER WITH the "
    u"signed `box`. The signed box should already be one of them, at the claimed index; the union "
    u"is taken over all of them so that a malformed emitter cannot shrink the word.",

    u"2. band_geometry() is applied to the crop of that union rect, with BAND_FRAC, MIN_BAND_PX "
    u"and MAX_BAND_PX UNCHANGED, and the record is refused unless the verdict is `one-band` or "
    u"`merged-top-edge` -- the same admissible set _one_band has always used, moved from the glyph "
    u"to the word. The floor is not lowered; it is applied to the thing it was derived on, a line "
    u"of type.",

    u"3. The band's native rows are [uy0 + main[0], uy0 + main[1]], where uy0 is the union rect's "
    u"top row and `main` is band_geometry's main band in crop-local rows.",

    u"4. Each box in the record -- the signed box and EVERY glyph box -- must then satisfy exactly "
    u"two things: (a) its rows lie inside the band's native rows, inclusive, with NO tolerance; "
    u"(b) the crop it cuts is in bounds and non-blank, which is D.crop_fault, the existing "
    u"outbound gate, already applied per glyph box today.",

    u"5. No per-glyph band check remains. A glyph box is never again asked to hold a line of type, "
    u"and MIN_BAND_PX is never read at glyph scale.",

    u"6. NOTHING in the span path changes: sig_rerat's gate on `new_box` and the span_crop_rows "
    u"report keep _one_band exactly as it is. That population is line crops, and p362:n1 and "
    u"p423:n3 are ratified on it. The carve-out here is for the exemplar path only.",
]

PREDICTION = [
    u"P1. All 10 records sig_load accepts today are accepted under the new rule. No reason, no "
    u"field and no verdict changes for any of them.",
    u"P2. p309 yod idx2 is ADMITTED. It is refused today for the height of a single ink run, which "
    u"clause 5 stops asking about.",
    u"P3. The refusal count goes 1 -> 0, and the accepted count 10 -> 11.",
    u"P4. MIN_BAND_PX stays 20, MAX_BAND_PX stays 50, BAND_FRAC stays 0.12.",
]

FALSIFIERS = [
    u"F1. Any record accepted today is refused under the new rule. Then the prediction is false, "
    u"and it is REPORTED with the measured margins -- not fixed by adding tolerance to clause 4a.",
    u"F2. p309 is still refused.",
    u"F3. Any threshold moves.",
    u"F4. A record is accepted for a reason outside clauses 2-4.",
]

NAMED_RISK = (
    u"Clause 4(a) is strict containment of the BOX, not of the ink, and it is the fragile clause. "
    u"A hand-drawn box with slack above the band will sit outside it, and so will a legitimate "
    u"ascender whose thin rows fall under BAND_FRAC on a narrow word crop -- the lamed of p309's "
    u"word is exactly that shape, so the record this ruling is meant to admit is also the one most "
    u"likely to trip it. Named here, before the measurement, so that if it fires it is a finding "
    u"and not a reason to loosen the clause."
)

CANNOT_DO = [
    u"It cannot say a box is drawn around the right glyph. That is letter_boxes_fault, unchanged.",
    u"It cannot say anything about pixels nobody has looked at. Every one of these crops is still "
    u"unseen on screen; passing a gate is not a human having seen it.",
    u"It cannot speak for the span path, which keeps the old gate by clause 6.",
]


def status_quo():
    u"""The population, as sig_load reads it TODAY. Ids only -- no new verdict is computed here."""
    good, bad = C.sig_load()
    acc = [{"file_page": r["file_page"], "letter": r["letter"],
            "index_from_right": int(r["letter_index_from_right"]),
            "n_glyph_boxes": len(r.get("letter_boxes") or [])} for r in good]
    ref = [{"file_page": r.get("file_page"), "letter": r.get("letter"),
            "index_from_right": r.get("letter_index_from_right"),
            "n_glyph_boxes": len(r.get("letter_boxes") or []),
            "refused_today": r["_refused"]} for r in bad]
    return acc, ref


def payload():
    acc, ref = status_quo()
    return {
        "kind": "exemplar_band_predictions",
        "lane": "Lane B",
        "session": "50612c81",
        "date": "2026-11-16",
        "page_convention": "ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88)",
        "ruling": ("Chris, 2026-11-16: do not lower MIN_BAND_PX. One line of type is a property of "
                   "the word, so apply the band check to the union of the word's glyph boxes, and "
                   "check each glyph box only for being inside that band and non-blank. Lock a "
                   "prediction that no currently accepted record changes."),
        "scope": {
            "changes": "hebrew_glyph_card.sig_load, the exemplar gate only",
            "unchanged": ["sig_rerat's gate on new_box", "span_crop_rows' one_band column",
                          "band_geometry", "text_bands", "MIN_BAND_PX", "MAX_BAND_PX",
                          "BAND_FRAC", "letter_boxes_fault", "D.crop_fault"],
            "sealed_untouched": ["p362:n1", "p423:n3"],
        },
        "thresholds_at_lock": {"MIN_BAND_PX": C.MIN_BAND_PX, "MAX_BAND_PX": C.MAX_BAND_PX,
                               "BAND_FRAC": C.BAND_FRAC},
        "decision_rule": RULE,
        "population": {"n_records": len(acc) + len(ref), "accepted_today": acc,
                       "refused_today": ref,
                       "basis": "hebrew_exemplar_signatures.jsonl as sig_load reads it at lock time"},
        "prediction": PREDICTION,
        "falsifiers": FALSIFIERS,
        "named_risk": NAMED_RISK,
        "cannot_do": CANNOT_DO,
        "measured_here": "NOTHING. This module computes no verdict under the new rule.",
    }


def write(out_dir=None):
    d = payload()
    body = json.dumps(d, indent=2, sort_keys=True, ensure_ascii=False)
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    d["prediction_sha16"] = sha
    body = json.dumps(d, indent=2, sort_keys=True, ensure_ascii=False)
    p = (out_dir or OUT_DIR) / ("PREDICTIONS_exemplarband_%s.json" % sha)
    assert_inside(p, "the prediction lock belongs in the audits directory with the other locks")
    io.open(str(p), "w", encoding="utf-8", newline="\n").write(body)
    return p, sha


def _calls_and_defs():
    """Every name this module CALLS, and every function it DEFINES, from the AST.

    The first two checks below used to grep this file's own text, and their own string literals
    satisfied the condition they forbid -- the same defect as a patch script whose comment matches
    the assert against the defect. Prose can say "band_geometry" all day; the AST only holds what
    the module actually calls.
    """
    import ast
    t = ast.parse(io.open(__file__, encoding="utf-8").read())
    calls = set()
    for node in ast.walk(t):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name):
                calls.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                calls.add(fn.attr)
    defs = set(x.name for x in ast.walk(t) if isinstance(x, ast.FunctionDef))
    return calls, defs


def selftest():
    def ck(name, cond, extra=""):
        print("%-4s %s%s" % ("ok" if cond else "FAIL", name,
                             ("   %s" % (extra,)) if extra and not cond else ""))
        return bool(cond)

    checks = []
    d = payload()
    calls, defs = _calls_and_defs()
    MEASURING = {"band_geometry", "text_bands", "ink_runs", "cut_native", "_one_band",
                 "crop_fault", "letter_boxes_fault", "sig_exemplars"}

    checks.append(ck("the lock CALLS nothing that could compute a band verdict, and says it "
                     "measures nothing",
                     d["measured_here"].startswith("NOTHING") and not (calls & MEASURING),
                     sorted(calls & MEASURING)))

    # The one property that matters about a lock: the module stating the prediction cannot also be
    # the one that scores it. Scoring lives in exemplar_band_result.py, which does not exist yet.
    checks.append(ck("this module defines no scorer",
                     not [x for x in defs if x.startswith("score") or x.startswith("verdict")],
                     sorted(defs)))

    checks.append(ck("the population is the whole signature file, accepted and refused together "
                     "(%d records)" % d["population"]["n_records"],
                     d["population"]["n_records"] == len(list(C._jsonl(C.SIGS))),
                     (d["population"]["n_records"], len(list(C._jsonl(C.SIGS))))))

    checks.append(ck("p309's yod is in the population as refused TODAY, named by its reason",
                     any(r["file_page"] == 309 and r["letter"] == "yod" and "18" in r["refused_today"]
                         for r in d["population"]["refused_today"])))

    checks.append(ck("the thresholds are recorded as read from the module, not retyped",
                     d["thresholds_at_lock"] == {"MIN_BAND_PX": C.MIN_BAND_PX,
                                                 "MAX_BAND_PX": C.MAX_BAND_PX,
                                                 "BAND_FRAC": C.BAND_FRAC}))

    checks.append(ck("the span path is named as out of scope, with the two ratified spans",
                     "sig_rerat" in " ".join(d["scope"]["unchanged"])
                     and d["scope"]["sealed_untouched"] == ["p362:n1", "p423:n3"]))

    checks.append(ck("every falsifier names a state of the world, and F1 forbids the fix that "
                     "would hide it",
                     len(FALSIFIERS) == 4 and "not fixed by adding tolerance" in FALSIFIERS[0]))

    checks.append(ck("the fragile clause is named BEFORE the measurement, and named as a finding",
                     "4(a)" in NAMED_RISK and "before the measurement" in NAMED_RISK))

    body = json.dumps(payload(), indent=2, sort_keys=True, ensure_ascii=False)
    s1 = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    body2 = json.dumps(payload(), indent=2, sort_keys=True, ensure_ascii=False)
    checks.append(ck("two builds of the payload hash the same",
                     s1 == hashlib.sha256(body2.encode("utf-8")).hexdigest()[:16]))

    checks.append(ck("the page convention is on the artifact",
                     "file - 88" in d["page_convention"]))

    # A check that cannot fail is not a check: the old "content-addressed by its own hash --
    # True" line asserted a sentence, not a fact. It is replaced by the two-build hash check
    # below, which can go red. The COUNT is asserted so a raise cannot quietly shorten the suite.
    EXPECT = 10
    if len(checks) != EXPECT:
        print("FAIL the suite ran %d checks, not the %d it claims" % (len(checks), EXPECT))
        checks.append(False)
    n = len(checks)
    f = len([c for c in checks if not c])
    print("\n%d checks, %d failed" % (n, f))
    return f


if __name__ == "__main__":
    if "selftest" in sys.argv:
        sys.exit(1 if selftest() else 0)
    p, sha = write()
    print("%s\n%s" % (p, sha))
