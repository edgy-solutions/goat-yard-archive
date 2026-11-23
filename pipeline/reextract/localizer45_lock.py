# -*- coding: utf-8 -*-
u"""Write the methods lock for the LOCALIZER draw: is the stored box on the Hebrew at all?

Lane B / session 50612c81.  ALL PAGE NUMBERS ARE FILE pages (printed = file - 88).

Chris, 2026-11-22 (overnight, item 2): "Write the lock for the next localizer draw (about 45 spans,
guard-passed crops, Opus bare and Qwen bare, scored once), with the cost estimate.  It runs only
after the second sitting is ingested and Chris approves the spend."

NOTHING HERE SENDS ANYTHING.  This module writes a prediction record and exits.  The lock is
content-addressed by its own body -- strip `self_sha16`, canonical JSON, UTF-8 bytes,
`ensure_ascii=False` -- which is the recipe GATE 0S re-implements, and the point is that a
prediction cannot be edited after the numbers land.

WHY A LOCALIZER DRAW AND NOT ANOTHER READING DRAW.  Every scored draw in this lane so far has
graded a TRANSCRIPTION against a signed string, and the measured weak link is not the reader: 14 of
74 spans carry a signer's box-location complaint, the counting localizer was never wired up
(`n_before` 0 for 74 of 74), and GEOMETRY5 put five verdicts on hand-picked suspects -- 4
`box_off_by_lines`, 1 `no_hebrew_on_crop`.  Hand-picked suspects cannot give an incidence.  No drawn
population has ever been asked the prior question: DOES THE CROP CARRY THE HEBREW AT ALL.  That
question needs no text truth, which is why it can be asked of the population that currently ships.

THE ONE DESIGN DECISION WORTH READING.  A draw of 41 clean spans that comes back "Hebrew present"
41 times proves nothing on its own: it is equally consistent with 41 good boxes and with an arm
that never says "absent".  So the draw carries four spans the signer himself marked in pass 1 --
p257:n3, p399:n5, p426:n1 (`fault: not-hebrew-or-blank`) and p677:n13 ("crop showing different
hebrew from glyph") -- as a POSITIVE CONTROL for the absent channel.  All four crops are inked
(ink fraction 0.117-0.248 measured), so an arm cannot get them right by noticing blankness.  Those
marks were made 2026-10-04, before this draw existed, so the stratum does not presuppose the
hypothesis.  If the control stratum reads "present" on both arms, the clean stratum's number is
UNSCOREABLE -- a gate must be able to see the failure.

Run with --write to emit; without, it prints the digest and the body and touches nothing.
"""
import argparse
import hashlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score45_run as S                    # canon / sha16_bytes / the pinned constants
import send_refusal as SR                  # law 8: the refusal predicate and the sidecar loader

OUT_DIR = S.A
CUT = "0401b636ffa7bf1a"
SHEET41 = "CONTACT_SHEET_scoring45_adb9a26835533dbc_c26745f4be489471bd.json"
SHEET41_SHA = "ad1ccbe4e7bbbc8b"           # the bytes Chris approved on 2026-11-08
CROPS = Path(str(OUT_DIR)) / ("truthset74_crops_%s" % CUT)
CONTROL = ("p257:n3", "p399:n5", "p426:n1", "p677:n13")

# Pinned 2026-11-22 by `population_digest()` over the 45 realized crop files.  A crop that is
# recut, renamed or re-padded moves this digest and the run ABORTS on it rather than sending a
# different population under this lock's numbers.
PINNED_DIGEST = "93c398cd1c1d2267"     # measured 2026-11-22 by --pin over the 45 realized crops

MAX_TOKENS_PINNED = 700                    # this draw, not S.MAX_TOKENS (1200); see `cost` below


def population():
    u"""(clean_ids, control_ids) -- derived from the committed sheet and the law-8 sidecar.

    Derived, not transcribed: a hand-copied list of 45 ids is a snapshot pin, and a snapshot pin
    cannot tell a legitimate change from a mistake.  The REFUSAL SET is the thing that must not
    move silently, so it is derived here from the sidecar and compared with the pinned 4 below.
    """
    sheet = json.loads(io.open(str(Path(str(OUT_DIR)) / SHEET41), encoding="utf-8").read())
    drawn = [r["span_id"] for r in sheet["rows"]]
    flags = SR.load_span_flags(str(Path(str(OUT_DIR)) / SR.SIDECAR_NAME))
    clean, refused = SR.partition(drawn, flags)
    assert sorted(refused) == ["p190:n0", "p493:n3", "p594:n0", "p803:n0"], \
        ("the law-8 refusal set over the scoring-45 sheet moved: %r.  The denominators in this "
         "lock are no longer the denominators -- write a NEW lock, never relax the pin."
         % sorted(refused))
    ctrl, ctrl_refused = SR.partition(list(CONTROL), flags)
    assert not ctrl_refused, \
        ("law 8 refuses %r, which is the CONTROL stratum.  A refusal set that eats exactly the "
         "informative subpopulation has happened in this lane before; the draw is not scoreable "
         "without its control, so it does not run." % sorted(ctrl_refused))
    return sorted(clean), sorted(ctrl)


def crop_path(span_id):
    pg, ni = span_id.split(":")
    return CROPS / ("%s_%s_A2_spanbox.png" % (pg, ni))


def population_digest():
    u"""sha16 over the REALIZED bytes of the 45 crops, keyed by span.  Not the requested pad, not
    the box: the bytes an arm would be shown.  (requested-vs-realized: persist what was applied.)"""
    clean, ctrl = population()
    items = []
    for sid in clean + ctrl:
        p = crop_path(sid)
        if not p.exists():
            raise RuntimeError("crop missing for %s at %s -- re-cut from the manifest (cut %s) "
                               "before anything is pinned" % (sid, p, CUT))
        items.append([sid, hashlib.sha256(p.read_bytes()).hexdigest()[:16]])
    items.sort()
    return S.sha16_bytes(S.canon(items).encode("utf-8")), items


def body(pop_digest, n_clean, n_control):
    return {
        "lock": "localizer draw, attempt 1: is the stored box on the Hebrew at all?",
        "written": "2026-11-22",
        "by": "Lane B / session 50612c81",
        "page_convention": "FILE pages (printed = file - 88)",
        "hash_rule":
            "sha256[:16] over the UTF-8 bytes of this record serialised with ensure_ascii=False, "
            "sort_keys=True, separators=(\",\",\":\"), with the self_sha16 field absent.  Stated "
            "here so the recipe can be re-implemented from the record alone; GATE 0S re-implements "
            "it and refuses a run whose lock does not recompute.",
        "spend_at_write_time": "none; this module writes a file and makes no outbound call",

        "run": {
            "attempt": 1,
            "mode": "localizer presence draw",
            "arms": ["anthropic/claude-opus-5.5", "qwen/qwen3.7-plus"],
            "arm_variants_forbidden": ":batch variants are not used in this run",
            "channels": ["bare"],
            "why_bare_only":
                "Two reasons, both measured.  (1) The context channel carries the Latin note text, "
                "which names the note the box is supposed to sit in -- it would hand the arm the "
                "answer to the question being asked.  (2) The no-pixel floor is 0 answered of 41 "
                "on BARE in both arms, measured twice (blank45 and its replicate); the one "
                "non-zero cell in that control was qwen|context, 5 answered of 40 with 1 exact.  "
                "So a `present` answer on bare is evidence about pixels, and the same answer on "
                "context would not be.",
            "draws_per_item": 1,
            "endpoint": "openrouter.ai, remote arms only",
            "endpoint_c_rule_not_engaged":
                "No local arm runs here, so the standing rule that local reads compared with "
                "signed verdicts stay on endpoint C (192.168.1.169:11434) is not engaged.  If a "
                "local arm is ever added to this draw it goes on endpoint C and nowhere else.  "
                "192.168.1.179 and 192.168.1.188 are never contacted.",
            "calls": 90,
            "composition": "2 arms x 45 spans x 1 channel x 1 draw",
            "max_tokens": MAX_TOKENS_PINNED,
            "population_digest_required": pop_digest,
        },

        # ------------------------------------------------------------------ the question
        "question": {
            "asks":
                "For each guard-passed A2 span-box crop, does the crop carry HEBREW SCRIPT at "
                "all, and if it does, which consonants?  The endpoint is the presence verdict, "
                "not the transcription.",
            "why_it_matters":
                "The finder is the measured weak link and nothing has ever measured it over a "
                "population that was not selected for being suspect.  14 of 74 spans carry a "
                "signer's location complaint; the counting localizer was never wired up, so every "
                "stored box is the note region's FIRST line by construction; GEOMETRY5 adjudicated "
                "six hand-picked spans and found four boxes off by lines and one crop with no "
                "Hebrew on it at all.  A rate cannot be read off six chosen rows.",
            "what_this_is_NOT":
                "Not a re-score of any read run, not a re-score of a signed verdict, and not an "
                "opening of a sealed page: 0 of the 45 spans sit on the eleven sealed pages "
                "(measured 2026-11-22).  The alignment gate is untouched.  No model verdict "
                "becomes a layer -- the output is a standoff queue in GEOMETRY5's vocabulary, and "
                "only a human sitting signs.",
        },

        # ------------------------------------------------------------------ the population
        "population": {
            "named_before_the_run": True,
            "n_spans": n_clean + n_control,
            "strata": {
                "clean": {
                    "n": n_clean,
                    "definition":
                        "the rows of %s (bytes sha16 %s, approved by Chris 2026-11-08) that law 8 "
                        "does not refuse.  Derived from the sidecar at run time, not transcribed."
                        % (SHEET41, SHEET41_SHA),
                    "pixels_already_approved": True,
                    "bytes_match_the_approved_sheet": "41 of 41, measured 2026-11-22",
                },
                "control": {
                    "n": n_control,
                    "ids": list(CONTROL),
                    "definition":
                        "spans the SIGNER marked in pass 1 (2026-10-04) as the crop not showing "
                        "the Hebrew: `fault: not-hebrew-or-blank` on p257:n3, p399:n5, p426:n1, "
                        "and `abstain_candidate_short` with the note \"crop showing different "
                        "hebrew from glyph and missing letters\" on p677:n13.",
                    "role":
                        "positive control for the ABSENT channel.  Without it, 45 `present` "
                        "answers are consistent with 45 good boxes and with an arm that cannot "
                        "say absent, and the draw could not tell those apart.",
                    "label_predates_the_hypothesis":
                        "the four marks were made on 2026-10-04, seven weeks before this lock; "
                        "the stratum is not drawn from the thing under test.",
                    "ink_fraction_measured": {"p257:n3": 0.11681, "p399:n5": 0.21768,
                                              "p426:n1": 0.21441, "p677:n13": 0.24785},
                    "why_ink_matters":
                        "all four crops are INKED, so an arm cannot answer `absent` correctly by "
                        "noticing blank paper.  A blank positive control would license the wrong "
                        "inference.",
                    "pixels_are_new_disclosure": True,
                },
            },
            "law_8": {
                "refused_in_this_draw": 0,
                "pinned_refusal_set_of_the_sheet": ["p190:n0", "p493:n3", "p594:n0", "p803:n0"],
                "rule":
                    "The four spans law 8 refuses on the scoring-45 sheet are NOT in this draw and "
                    "are not replaced by substitutes.  If the sidecar's refusal set moves, the "
                    "population moves and the run ABORTS on the count: re-measure free, write a "
                    "new lock, never relax a pin.",
                "what_is_therefore_outside_this_draw":
                    "every span with a RECORDED box fault.  Law 8 forbids a paid call on a box "
                    "that failed a geometry check, so the incidence this draw measures is the "
                    "incidence over the boxes nobody has faulted -- the residual that currently "
                    "ships.  It is NOT the corpus-wide fault rate and must never be quoted as one.",
            },
            "guard": {
                "name": "hebrew_aperture_diag.gate_outbound(..., offnet=True)",
                "checks": "A2 span-box aperture by filename, then uniform / near-uniform / "
                          "no-line / clamp-loss / beyond-strip over the pixels",
                "measured_2026_11_22": "45 of 45 pass; 0 refused, 0 absent",
                "guard_that_does_NOT_exist":
                    "core-at-edge.  The 923R instance (\"Transcriber's Note:\") showed that a crop "
                    "straddling two printed lines passes blank, uniform and clamp, and no "
                    "implementation of a core-at-edge check exists in this tree (grep, "
                    "2026-11-22).  So `guard-passed` in this lock means the five checks named "
                    "above and not more than that.",
            },
            "sealed_pages_intersected": 0,
        },

        # ------------------------------------------------------------------ what the arm is asked
        "task": {
            "image": "exactly one image per call: the A2 span-box crop, native pixels, no upscale",
            "prompt_carries":
                "the question and the answer shape only.  No note text, no candidate string, no "
                "signed form, no verse reference, no page number, no neighbouring span.",
            "required_answer_shape": [
                "hebrew_present: yes | no",
                "consonants: the Hebrew consonants in order, or empty when hebrew_present is no",
                "a one-line reason",
            ],
            "the_absent_channel_is_required":
                "`no` is a first-class answer with its own field, not an empty string.  A system "
                "with no way to say `nothing here` turns an honest component into a fabricator: "
                "p4 shipped a frontispiece's \"no footnotes\" as a footnote.",
            "no_reasoning_ladder":
                "the reasoning ladder is for hard glyph reads; presence is not one, and a ladder "
                "step would change the payload and the cost without changing the endpoint.",
        },

        # ------------------------------------------------------------------ the decision rule
        "decision_rule": {
            "primary":
                "Per span, the pair of presence verdicts.  BOTH `present` -> `present`; BOTH "
                "`absent` -> `absent_candidate`, queued for a human sitting in GEOMETRY5's "
                "vocabulary as a candidate `no_hebrew_on_crop`; DISAGREE -> `disputed`, queued.  "
                "The headline is three counts over the clean stratum and three over the control "
                "stratum, reported separately and never pooled.",
            "agreement_is_not_confidence":
                "two arms on the same pixels share priors, so AGREEMENT is not evidence of "
                "correctness and is not reported as confidence.  Disagreement is the signal, and "
                "its only use is the queue.",
            "secondary_reported_never_primary":
                "for `present` reads in the clean stratum, base-consonant comparison against the "
                "row's signed in-crop signature, and -- where it misses -- against the census "
                "Hebrew of the OTHER notes on the same page.  A match to another note's Hebrew is "
                "positive evidence of MISLOCATION; a miss against everything is evidence of "
                "nothing in particular and is reported as unattributed, never as a misread.",
            "secondary_is_undefined_for_the_control":
                "the four control spans have no signed string (pass 1 recorded `complete: false`), "
                "so no string comparison is defined for them.  Their endpoint is presence only, "
                "and a transcription from them is reported as text without a verdict.",
            "no_model_verdict_ships":
                "nothing in this draw writes an apparatus byte, a box, or a signed layer.  The "
                "deliverable is a queue and a standoff record.",
            "no_reformulation":
                "the rule above is fixed by this lock's hash.  If the result is awkward, the "
                "result is reported awkward.",
        },

        # ------------------------------------------------------------------ predictions
        "predictions": {
            "informed_not_blind":
                "I have read the pass-1 marks, GEOMETRY5's five verdicts and the scoring-45 rows.  "
                "These predictions are informed; their value is that they carry a hash from before "
                "the run.",
            "clean_stratum_n": n_clean,
            "clean": {"present_both": "37-41, point 40",
                      "absent_both": "0-2, point 0",
                      "disputed": "0-4, point 1"},
            "control_stratum_n": n_control,
            "control": {"absent_both_on_the_three_not_hebrew_spans": "2-3 of 3, point 3",
                        "p677:n13": "`present` on both arms, with consonants that do NOT match its "
                                    "census candidate -- it is the mislocation control, not an "
                                    "absence control"},
            "secondary": {"clean_present_reads_matching_their_own_signature": "30-39 of about 40",
                          "clean_present_reads_matching_ANOTHER_note_on_the_page": "0-2, point 0"},
        },

        "falsifiers": [
            {"id": "F1",
             "fires_if": "all three not-Hebrew control spans read `present` with a Hebrew string "
                         "on both arms",
             "then": "the absent channel does not work on this corpus, and the clean stratum's "
                     "presence count is UNSCOREABLE -- not clean.  Report it as unscoreable and "
                     "do not convert it into a box-quality statement."},
            {"id": "F2",
             "fires_if": "any control span returns the span's own census or signed Hebrew string",
             "then": "that is fabrication on inked non-Hebrew pixels.  The whole draw is withdrawn "
                     "as a measurement of pixels and reported as a measurement of priors.  A "
                     "zero-pixel crop has already returned an exact signed string once in this "
                     "lane, so this is a live mode and not a hypothetical."},
            {"id": "F3",
             "fires_if": "the clean stratum yields more than 6 `absent_both`",
             "then": "the shipping population's boxes are worse than 1 in 7 and the apparatus "
                     "geometry layer is not publication-grade.  That is a tier statement, so it "
                     "needs a CLEAN run under the clean-run rule or it cannot be cited at all."},
            {"id": "F4",
             "fires_if": "`disputed` exceeds 10 of 45",
             "then": "presence is not a stable read at one draw per item.  The draw yields a queue "
                     "only; no incidence is reported from it."},
            {"id": "F5",
             "fires_if": "the population digest, the law-8 refusal set, or any cell's n differs "
                         "from what this lock registers",
             "then": "the run is UNSCOREABLE against this lock.  Write a new lock; never rescore "
                     "against a different denominator."},
            {"id": "F6",
             "fires_if": "more than 2 calls finish on the token cap",
             "then": "the cap chosen here is wrong for the task.  The run is rerun from the top "
                     "with a stated cap -- never spliced, and the capped items are not scored as "
                     "reads."},
        ],

        "scoreability_preconditions": [
            {"id": "P1",
             "precondition": "This draw CANNOT test the counting-localizer defect.",
             "why": "The defect can only be expressed where the Hebrew does not open its note.  "
                    "Census `start` is 0 for 39 of the 41 clean spans and 2 for the other two "
                    "(p274:n0, p526:n0), so the un-wired path is accidentally right by "
                    "construction across the whole clean stratum.  The four spans in the cut where "
                    "`start` is 55/37/21/12 are p257:n3, p399:n5, p426:n1 and p677:n13 -- which is "
                    "the control stratum, already marked faulted by the signer.  Measured "
                    "2026-11-22, before the run, so the report cannot later present a clean clean "
                    "stratum as evidence that the counting defect is harmless."},
            {"id": "P2",
             "precondition": "A presence count at one draw per item is a count, not a rate.",
             "why": "A one-draw-per-item estimator has already manufactured a regression out of "
                    "flake in this lane.  The honest unit is the ITEM and the deliverable is the "
                    "queue; any rate reported from this run carries `one draw per item` in the "
                    "same sentence."},
            {"id": "P3",
             "precondition": "The bare no-pixel floor licenses the pixel inference.",
             "why": "0 answered of 41 on bare in both arms, twice.  Without that measurement a "
                    "`present` answer would be a prior rather than a read, and no output-side "
                    "check could tell the difference."},
            {"id": "P4",
             "precondition": "The control stratum's crops are NEW disclosure and need their own "
                             "contact-sheet approval before the run.",
             "why": "The 41 clean crops are the bytes Chris approved on 2026-11-08 and the "
                    "approval is content-addressed over exactly those pixels.  The four control "
                    "crops have never been shown to him, so the sheet for this run is a new sheet "
                    "with new bytes and a new approval record naming attempt 1."},
        ],

        # ------------------------------------------------------------------ cost
        "cost": {
            "basis":
                "DERIVED from measurement, not predicted: run 501ab577a18a6785 sent 45 bare calls "
                "per arm over these same crops, and its cost recompute "
                "(COST_RECOMPUTE_501ab577a18a6785_ee6d6da46f4279d1, self_sha16 "
                "ee6d6da46f4279d1) records every call's native tokens at live list price.",
            "measured_bare_per_arm": {
                "anthropic/claude-opus-5.5": {
                    "n": 45, "prompt_tokens_min_med_max": [229, 244, 442],
                    "completion_tokens_min_med_max": [14, 68, 552],
                    "usd_mean_per_call": 0.003118, "usd_max_per_call": 0.01214,
                    "usd_total": 0.140328},
                "qwen/qwen3.7-plus": {
                    "n": 45, "prompt_tokens_min_med_max": [210, 220, 305],
                    "completion_tokens_min_med_max": [8, 10, 20],
                    "usd_mean_per_call": 0.000085, "usd_max_per_call": 0.000112,
                    "usd_total": 0.003813},
            },
            "expected_usd": 0.145,
            "expected_is":
                "the measured total of the same 90 bare calls ($0.144141).  The prompt is shorter "
                "than the classify prompt and the answer shape is smaller, so this is an upper "
                "estimate of the expected case rather than a central one.",
            "ceiling_usd": 0.72,
            "ceiling_is":
                "every opus call running to the pinned cap: 45 x (442 prompt x $4e-6 + %d "
                "completion x $2e-5) + qwen's measured $0.0038.  Reported because an expected "
                "value is not a bound, and because the sender's default cap of %d would put that "
                "bound at about $1.2." % (MAX_TOKENS_PINNED, S.MAX_TOKENS),
            "why_the_cap_is_lowered":
                "the answer is a flag, a short consonant string and one line of reason.  The cap "
                "is a cost bound, and F6 fires if it turns out to be a content bound too.",
            "wall_clock":
                "about 4 minutes.  Derived from the scored run's 443 s over 162 calls (2.7 s per "
                "call, 0 retries), at 90 calls.",
            "retries_do_not_change_the_bound":
                "RETRIES is %d and fires only on transient upstream 429/5xx; a retried call is "
                "counted and reported, and %d consecutive dead items aborts the run."
                % (S.RETRIES, S.CONSECUTIVE_FAIL_ABORT),
        },

        "run_level_fault": {
            "law": "errors out of the denominator is not enough.  A 429, or %d consecutive dead "
                   "items, is a RUN-LEVEL fault: the run aborts, writes nothing, and is rerun from "
                   "the top.  Never spliced." % S.CONSECUTIVE_FAIL_ABORT,
            "a_faulted_head_poisons_the_load":
                "a `done: false` as the FIRST reply of a load leaves every later item UNMEASURED, "
                "not fine.  If the first call of either arm faults, the arm's whole pass is "
                "discarded, not patched around.",
            "retries": "%d, transient upstream only; every retry is counted and reported, and a "
                       "retried call's tokens are in the cost." % S.RETRIES,
        },

        "check_count_gates": {
            "rule":
                "the run asserts its own internal check count and aborts on a mismatch, and the "
                "count is pinned by a FREE --dry-run before the paid pass -- a header-scoped guard "
                "must never be discovered by spending.",
            "no_number_is_pinned_here":
                "this draw's sender mode does not exist yet, so a count written into this lock "
                "would be a number invented before the thing it counts.  The dry-run pins it, the "
                "pin is recorded in the run header, and a later rerun compares against that.",
            "assert_the_check_count_itself":
                "the suite that checks this run asserts how many checks it ran: an exception in a "
                "hand-rolled suite ends the run silently, and that has cost this lane 40 "
                "assertions once already.",
        },

        # ------------------------------------------------------------------ gates
        "gates_before_the_first_paid_call": [
            "the second sitting is INGESTED.  Chris's condition, and it is also the honest order: "
            "the sitting's verdicts change which spans carry a signed string.",
            "a contact sheet for all 45 crops, native size, each beside its signed text where one "
            "exists, with the four control crops marked as new disclosure; Chris eyeballs the "
            "crops and approves them on what they SHOW.",
            "an approval record named by the new sheet's BYTES, naming the cut, an approver, a "
            "date, and licensing attempt 1 only.  A yes to attempt 1 is not a yes to attempt 2.",
            "GATE 0S: this lock recomputes to its own pinned hash and the approval record exists "
            "and licenses this attempt.",
            "law 8: the sidecar is present and refuses none of the 45; the refusal set over the "
            "scoring-45 sheet is still exactly the pinned four.",
            "the outbound guard admits all 45 crops, and the population digest equals %s." %
            pop_digest,
            "a --dry-run that builds all 90 payloads, writes nothing, and pins the pre-call check "
            "count free, so no header-scoped guard is discovered by spending.",
            "the clean-run rule: git_state() over both repos clean at start and at end and "
            "identical, or the run is provisional and cannot be cited in an ADR or a tier change.",
        ],

        "what_this_cannot_settle": [
            "The corpus-wide box fault rate.  Law 8 keeps every recorded fault out of the draw, so "
            "the number is an incidence over the unfaulted residual.",
            "The counting-localizer defect -- see precondition P1.  It is latent across the whole "
            "clean stratum.",
            "Whether an `absent` verdict is right.  Two arms agreeing that a crop carries no "
            "Hebrew is a queue entry, not a verdict; GEOMETRY5's five rows were signed by a human "
            "looking at marked crops and this draw changes none of them.",
            "Anything about the 29 spans of the 74-set that are outside the scoring-45 sheet, the "
            "sealed 19, or any span on the eleven sealed pages.",
            "Where a box IS when it is wrong.  Presence does not give a displacement; the "
            "secondary analysis can only say `this looks like another note on the page`.",
            "Whether the apparatus text for a span is right.  No signed string is re-scored.",
        ],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="emit the lock; default is to print it")
    ap.add_argument("--pin", action="store_true",
                    help="print the population digest and exit (what PINNED_DIGEST is set from)")
    a = ap.parse_args()

    dig, items = population_digest()
    if a.pin:
        print("population_digest: %s over %d crops" % (dig, len(items)))
        for sid, sha in items:
            print("  %-10s %s" % (sid, sha))
        return 0
    if dig != PINNED_DIGEST:
        print("REFUSED: the population digest is %s, not the pinned %s.  Something about the 45 "
              "crops changed since this lock was written.  Look at what moved, then write a NEW "
              "lock -- do not repin this one." % (dig, PINNED_DIGEST))
        return 1

    clean, ctrl = population()
    b = body(dig, len(clean), len(ctrl))
    d = S.sha16_bytes(S.canon(b).encode("utf-8"))
    rec = dict(b, self_sha16=d)
    back = {k: v for k, v in rec.items() if k != "self_sha16"}
    assert S.sha16_bytes(S.canon(back).encode("utf-8")) == d, "the recipe does not round-trip"

    out = Path(str(OUT_DIR)) / ("PREDICTIONS_localizer45_%s.json" % d)
    print("population:  %d clean + %d control = %d spans, 90 calls"
          % (len(clean), len(ctrl), len(clean) + len(ctrl)))
    print("pop digest:  %s" % dig)
    print("self_sha16:  %s" % d)
    print("path:        %s" % out)
    if not a.write:
        print("\n-- not written (pass --write).  Body follows --")
        print(json.dumps(rec, ensure_ascii=False, indent=1))
        return 0
    if out.exists():
        print("REFUSED: %s already exists.  A lock is content-addressed; identical bytes mean "
              "nothing to do, and different bytes would be a different file." % out.name)
        return 0
    io.open(str(out), "w", encoding="utf-8", newline="\n").write(
        json.dumps(rec, ensure_ascii=False, indent=1) + "\n")
    print("WROTE %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
