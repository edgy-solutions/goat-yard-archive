"""Born-tests for the arm comparator. Offline; builds arm directories on disk from literals.

    python evals/test_compare_arms.py

What is under test is the comparator's REFUSALS as much as its arithmetic: a diff over arms with
different question sets, or different provider pins, is not a measurement, and saying so is the
whole point of the instrument.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_arms as CA  # noqa: E402

PIN = {"order": ["streamlake"], "allow_fallbacks": False}

# Pass this as a question's `partial_match_sids` to build a response with the key ENTIRELY
# MISSING, distinct from a present key holding None or []. A backend build that predates the
# field never writes the key at all, and json.dumps of a dict simply omitted at construction is
# the only way to fixture that -- a dict with the key set to None round-trips as a PRESENT key,
# which is a different response shape.
OMIT = object()


def _arm(root, name, questions, pin=PIN, answer_lm=None):
    """questions: {qid: (run_passes, refusal_correct, answer, partial_match_sids)}

    `partial_match_sids` may be `OMIT` to build a response with no such key at all (see OMIT
    above), rather than a key present with an empty or null value.

    `answer_lm` is the arm's summary-level tally block (as run_eval.answer_lm_tally writes it).
    Default None = an arm that predates the field, which is the state of every arm run before
    2026-09-27 and must stay representable.
    """
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    for qid, (passes, refusal_ok, answer, partial) in questions.items():
        response = {"answer": answer, "refused": False}
        if partial is not OMIT:
            response["partial_match_sids"] = partial
        rec = {"question": {"id": qid}, "run_passes": list(passes),
               "score": {"id": qid, "refusal_correct": refusal_ok, "expected_behavior": "answer"},
               "response": response}
        io.open(os.path.join(d, qid + ".json"), "w", encoding="utf-8").write(json.dumps(rec))
    summary = {"openrouter_provider_pin": pin}
    if answer_lm is not None:
        summary["answer_lm"] = answer_lm
    io.open(os.path.join(d, "summary.json"), "w", encoding="utf-8").write(json.dumps(summary))
    return d


# --- classification -----------------------------------------------------------------

def test_class_from_run_passes():
    assert CA.classify([True, True, True]) == CA.SP
    assert CA.classify([False, False, False]) == CA.SF
    assert CA.classify([True, False, True]) == CA.FLAKY
    assert CA.classify([]) == CA.NO_DATA
    assert CA.classify(None) == CA.NO_DATA


def test_none_runs_are_not_failures():
    # A run that produced no scoreable result must not drag a question to STABLE-FAIL.
    assert CA.classify([True, None, True]) == CA.SP, "an unscoreable run is not a FAIL"
    assert CA.classify([None, None]) == CA.NO_DATA


# --- the gate: flip direction -------------------------------------------------------

def test_stable_pass_to_stable_fail_is_counted_as_a_flip():
    root = tempfile.mkdtemp()
    try:
        a = _arm(root, "a", {"q1": ([True] * 3, True, "x" * 100, [])})
        b = _arm(root, "b", {"q1": ([False] * 3, True, "x" * 100, [])})
        r = CA.compare(CA.load_arm(a), CA.load_arm(b), "a", "b")
        assert r["stable_flips_n"] == 1, r
        assert r["class_changes_n"] == 1, r
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_flip_on_a_NON_GATING_question_is_reported_but_does_not_gate():
    # Ruling 1 pulled three near-coin-flip questions from the gate. The flip is still a real class
    # change and must still be visible -- what it must not do is fire the gate.
    qid = "john_baptist_001"
    assert qid in CA.NON_GATING, "the fixture depends on this id being excluded"
    root = tempfile.mkdtemp()
    try:
        a = _arm(root, "a", {qid: ([True] * 5, True, "x" * 100, [])})
        b = _arm(root, "b", {qid: ([False] * 5, True, "x" * 100, [])})
        r = CA.compare(CA.load_arm(a), CA.load_arm(b), "a", "b")
        assert r["stable_flips_n"] == 0, "a non-gating question must not fire the gate"
        assert r["flips_excluded_from_gate_n"] == 1, r
        assert r["flips_excluded_from_gate"][0]["id"] == qid
        assert "p~0.5" in r["flips_excluded_from_gate"][0]["non_gating_reason"]
        assert r["class_changes_n"] == 1, "it is still a class change"
        # and it must be impossible to miss: an exclusion nobody sees cannot be told apart from a
        # gate that failed to fire.
        assert any("EXCLUDED FROM THE GATE" in n for n in r["notes"]), r["notes"]
        assert r["non_gating_questions"] == [qid], r["non_gating_questions"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_gating_and_a_non_gating_flip_in_ONE_pair_are_separated():
    # The companion assertion. An implementation that excluded everything, or that excluded
    # nothing, passes one of the two tests above; only a pair containing both distinguishes them.
    root = tempfile.mkdtemp()
    try:
        qs_a = {"q1": ([True] * 5, True, "x" * 100, []),
                "scapegoat_001": ([True] * 5, True, "x" * 100, [])}
        qs_b = {"q1": ([False] * 5, True, "x" * 100, []),
                "scapegoat_001": ([False] * 5, True, "x" * 100, [])}
        r = CA.compare(CA.load_arm(_arm(root, "a", qs_a)),
                       CA.load_arm(_arm(root, "b", qs_b)), "a", "b")
        assert r["stable_flips_n"] == 1, r["stable_flips"]
        assert r["stable_flips"][0]["id"] == "q1"
        assert r["flips_excluded_from_gate_n"] == 1, r["flips_excluded_from_gate"]
        assert r["flips_excluded_from_gate"][0]["id"] == "scapegoat_001"
        assert r["class_changes_n"] == 2, "both are class changes"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_non_gating_questions_reports_only_the_ones_in_THIS_pair():
    # An empty list must mean "no exclusion applied here", not "the exclusion set was never
    # consulted". Without this field those two states look identical in the output.
    root = tempfile.mkdtemp()
    try:
        r = CA.compare(CA.load_arm(_arm(root, "a", {"q1": ([True] * 5, True, "x", [])})),
                       CA.load_arm(_arm(root, "b", {"q1": ([True] * 5, True, "x", [])})), "a", "b")
        assert r["non_gating_questions"] == [], r
        assert r["flips_excluded_from_gate_n"] == 0
        assert not any("EXCLUDED FROM THE GATE" in n for n in r["notes"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_all_three_ruling_1_exclusions_are_in_force():
    assert set(CA.NON_GATING) == {"john_baptist_001", "scapegoat_001",
                                  "real_imprecatory_psalms_001"}, sorted(CA.NON_GATING)
    for qid, reason in CA.NON_GATING.items():
        assert "/6" in reason and "2026-09-27" in reason, (qid, reason)


def test_an_under_powered_pair_says_so():
    root = tempfile.mkdtemp()
    try:
        r = CA.compare(CA.load_arm(_arm(root, "a", {"q1": ([True] * 3, True, "x", [])})),
                       CA.load_arm(_arm(root, "b", {"q1": ([True] * 3, True, "x", [])})), "a", "b")
        assert r["runs_per_question"] == {"a": 3, "b": 3}, r["runs_per_question"]
        assert any("UNDER-POWERED CLASSIFICATION" in n for n in r["notes"]), r["notes"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_pair_at_N5_does_NOT_raise_the_under_powered_note():
    # The companion assertion: a note raised unconditionally says nothing.
    root = tempfile.mkdtemp()
    try:
        r = CA.compare(CA.load_arm(_arm(root, "a", {"q1": ([True] * 5, True, "x", [])})),
                       CA.load_arm(_arm(root, "b", {"q1": ([True] * 5, True, "x", [])})), "a", "b")
        assert r["min_classification_runs"] == 5
        assert not any("UNDER-POWERED" in n for n in r["notes"]), r["notes"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_flaky_to_stable_is_a_change_but_not_a_flip():
    root = tempfile.mkdtemp()
    try:
        a = _arm(root, "a", {"q1": ([True, False, True], True, "x", [])})
        b = _arm(root, "b", {"q1": ([True, True, True], True, "x", [])})
        r = CA.compare(CA.load_arm(a), CA.load_arm(b), "a", "b")
        assert r["class_changes_n"] == 1, r
        assert r["stable_flips_n"] == 0, "FLAKY -> STABLE-PASS is not the gate"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_identical_arms_report_no_change():
    root = tempfile.mkdtemp()
    try:
        qs = {"q1": ([True] * 3, True, "x" * 50, []), "q2": ([False] * 3, True, "y" * 50, [])}
        r = CA.compare(CA.load_arm(_arm(root, "a", qs)), CA.load_arm(_arm(root, "b", qs)), "a", "b")
        assert r["class_changes_n"] == 0 and r["stable_flips_n"] == 0, r
        assert r["class_unchanged_n"] == 2, r
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_equal_class_counts_can_still_hide_a_flip():
    # The aggregate summary would show 1 STABLE-PASS and 1 STABLE-FAIL on BOTH arms and call it
    # unchanged. This is why classes are recomputed per question.
    root = tempfile.mkdtemp()
    try:
        a = _arm(root, "a", {"q1": ([True] * 3, True, "x", []), "q2": ([False] * 3, True, "y", [])})
        b = _arm(root, "b", {"q1": ([False] * 3, True, "x", []), "q2": ([True] * 3, True, "y", [])})
        r = CA.compare(CA.load_arm(a), CA.load_arm(b), "a", "b")
        assert r["passed"]["a"] == r["passed"]["b"] == 1, r["passed"]
        assert r["stable_flips_n"] == 2, "identical counts, two flips - the count cannot see it"
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --- the refusals -------------------------------------------------------------------

def test_mismatched_question_sets_are_refused():
    root = tempfile.mkdtemp()
    try:
        a = _arm(root, "a", {"q1": ([True] * 3, True, "x", []), "q2": ([True] * 3, True, "y", [])})
        b = _arm(root, "b", {"q1": ([True] * 3, True, "x", [])})
        try:
            CA.compare(CA.load_arm(a), CA.load_arm(b), "a", "b")
        except SystemExit as e:
            assert "q2" in str(e) and "not a failure" in str(e), str(e)
        else:
            raise AssertionError("a missing question must not be silently scored as absent")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_differing_pins_are_called_out():
    root = tempfile.mkdtemp()
    try:
        qs = {"q1": ([True] * 3, True, "x", [])}
        a = _arm(root, "a", qs, pin=PIN)
        b = _arm(root, "b", qs, pin={"order": ["deepinfra"], "allow_fallbacks": False})
        r = CA.compare(CA.load_arm(a), CA.load_arm(b), "a", "b")
        assert any("PROVIDER PIN DIFFERS" in n for n in r["notes"]), r["notes"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_both_unpinned_is_called_out():
    root = tempfile.mkdtemp()
    try:
        qs = {"q1": ([True] * 3, True, "x", [])}
        r = CA.compare(CA.load_arm(_arm(root, "a", qs, pin=None)),
                       CA.load_arm(_arm(root, "b", qs, pin=None)), "a", "b")
        assert any("UNPINNED" in n for n in r["notes"]), r["notes"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_empty_arm_directory_is_refused():
    root = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(root, "empty"))
        try:
            CA.load_arm(os.path.join(root, "empty"))
        except SystemExit as e:
            assert "nothing to compare" in str(e), str(e)
        else:
            raise AssertionError("an empty arm must not compare as all-zero")
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --- ruling 2: what actually served each arm -----------------------------------------

def _tally(temperature=0.0, served="StreamLake", client="dspy.LM", runs=3):
    return {"scored_runs_with_a_record": runs, "questions_missing_a_record": [],
            "runs_pin_honored_false": 0, "runs_pin_unchecked": 0,
            "distinct": [{"path": "dspy", "client": client,
                          "model_requested": "openai/deepseek/deepseek-chat",
                          "model_returned": "deepseek/deepseek-chat",
                          "temperature_on_the_wire": temperature, "provider_pin": PIN,
                          "provider_served": served,
                          "provider_served_source": "dspy_response_attribute",
                          "pin_honored": True, "runs": runs}]}


def test_identical_serving_config_raises_no_answer_lm_note():
    root = tempfile.mkdtemp()
    try:
        qs = {"q1": ([True] * 3, True, "x", [])}
        r = CA.compare(CA.load_arm(_arm(root, "a", qs, answer_lm=_tally())),
                       CA.load_arm(_arm(root, "b", qs, answer_lm=_tally())), "a", "b")
        assert not any("ANSWER-LM" in n for n in r["notes"]), r["notes"]
        assert r["answer_lm_config"]["a"] == r["answer_lm_config"]["b"], r["answer_lm_config"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_temperature_difference_between_arms_is_called_out():
    # The one that hid: BAML sends temperature 0, dspy sends no temperature field at all, so
    # every OFF-vs-ON arm differed on this axis and no artifact said so.
    root = tempfile.mkdtemp()
    try:
        qs = {"q1": ([True] * 3, True, "x", [])}
        r = CA.compare(
            CA.load_arm(_arm(root, "a", qs, answer_lm=_tally(temperature="<absent from optional_params>"))),
            CA.load_arm(_arm(root, "b", qs, answer_lm=_tally(temperature=0.0, client="GillAnswerLM"))),
            "a", "b")
        hits = [n for n in r["notes"] if "ANSWER-LM CONFIG DIFFERS" in n]
        assert len(hits) == 1, r["notes"]
        assert "absent from optional_params" in hits[0], hits
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_provider_difference_between_arms_is_called_out():
    root = tempfile.mkdtemp()
    try:
        qs = {"q1": ([True] * 3, True, "x", [])}
        r = CA.compare(CA.load_arm(_arm(root, "a", qs, answer_lm=_tally(served="StreamLake"))),
                       CA.load_arm(_arm(root, "b", qs, answer_lm=_tally(served="DeepInfra"))),
                       "a", "b")
        assert any("ANSWER-LM CONFIG DIFFERS" in n for n in r["notes"]), r["notes"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_an_arm_with_no_record_is_named_not_assumed_to_match():
    # Absence is not equality. An arm that recorded nothing must not compare as identical to
    # one that did, and the note must say WHICH arm is the one that cannot state its config.
    root = tempfile.mkdtemp()
    try:
        qs = {"q1": ([True] * 3, True, "x", [])}
        r = CA.compare(CA.load_arm(_arm(root, "a", qs, answer_lm=_tally())),
                       CA.load_arm(_arm(root, "b", qs)), "a", "b")
        hits = [n for n in r["notes"] if "NO PER-CALL ANSWER-LM RECORD" in n]
        assert len(hits) == 1, r["notes"]
        assert "in b:" in hits[0] and "in a" not in hits[0], hits
        assert r["answer_lm_config"]["b"] == [], r["answer_lm_config"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --- the floor ----------------------------------------------------------------------

def test_a_diff_at_the_floor_is_not_reportable():
    root = tempfile.mkdtemp()
    try:
        a = _arm(root, "a", {"q1": ([True] * 3, True, "x", []), "q2": ([True] * 3, True, "y", [])})
        b = _arm(root, "b", {"q1": ([True, False, True], True, "x", []), "q2": ([True] * 3, True, "y", [])})
        r = CA.compare(CA.load_arm(a), CA.load_arm(b), "a", "b", floor=1)
        assert r["class_changes_n"] == 1 and r["above_floor"] is False, r
        r2 = CA.compare(CA.load_arm(a), CA.load_arm(b), "a", "b", floor=0)
        assert r2["above_floor"] is True, r2
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --- the other fields item (a) has to report ----------------------------------------

def test_refusal_wrong_set_difference_names_the_questions():
    root = tempfile.mkdtemp()
    try:
        a = _arm(root, "a", {"q1": ([True] * 3, True, "x", []), "q2": ([True] * 3, False, "y", [])})
        b = _arm(root, "b", {"q1": ([True] * 3, False, "x", []), "q2": ([True] * 3, False, "y", [])})
        r = CA.compare(CA.load_arm(a), CA.load_arm(b), "a", "b")
        assert r["refusal_wrong_symmetric_difference"] == ["q1"], r
        assert r["refusal_wrong"]["b"] == ["q1", "q2"], r
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_no_data_questions_are_not_counted_as_refusal_regressions():
    # off_20260927c had 5 HTTP 500s. Their responses carry no answer, so refusal_correct is False
    # by default; counting them made five dead questions read as five refusal regressions.
    root = tempfile.mkdtemp()
    try:
        a = _arm(root, "a", {"q1": ([True] * 3, True, "x", []), "q2": ([], False, "", [])})
        b = _arm(root, "b", {"q1": ([True] * 3, True, "x", []), "q2": ([True] * 3, True, "y", [])})
        r = CA.compare(CA.load_arm(a), CA.load_arm(b), "a", "b")
        assert r["refusal_wrong"]["a"] == [], r["refusal_wrong"]
        assert r["refusal_wrong_symmetric_difference"] == [], r
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_partial_match_sids_emptiness_is_reported_per_arm():
    root = tempfile.mkdtemp()
    try:
        a = _arm(root, "a", {"q1": ([True] * 3, True, "x", [])})
        b = _arm(root, "b", {"q1": ([True] * 3, True, "x", ["GEN_1_1_S00"])})
        r = CA.compare(CA.load_arm(a), CA.load_arm(b), "a", "b")
        assert r["partial_match_sids_nonempty"]["a"] == [], r
        assert r["partial_match_sids_nonempty"]["b"] == ["q1"], r
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_partial_match_sids_absent_in_both_arms_is_NOT_REPORTED_not_empty():
    # The state a run from a backend build that predates the field produces: nothing in either
    # arm ever carries the key. This must read as "not reported", never as "reported and empty" --
    # otherwise a pre-field run compares as if it had computed the field and found nothing, which
    # is a claim that backend never made.
    root = tempfile.mkdtemp()
    try:
        a = _arm(root, "a", {"q1": ([True] * 3, True, "x", OMIT)})
        b = _arm(root, "b", {"q1": ([True] * 3, True, "y", OMIT)})
        r = CA.compare(CA.load_arm(a), CA.load_arm(b), "a", "b")
        assert r["partial_match_sids_nonempty"]["a"] == CA.PARTIAL_NOT_REPORTED, r
        assert r["partial_match_sids_nonempty"]["b"] == CA.PARTIAL_NOT_REPORTED, r
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_partial_match_sids_absent_in_one_arm_present_in_the_other():
    # Mixed old-backend-vs-new-backend comparison: one side never wrote the key, the other did
    # (and found nothing). The two arms must show DIFFERENT states on this line, not the same [].
    root = tempfile.mkdtemp()
    try:
        a = _arm(root, "a", {"q1": ([True] * 3, True, "x", OMIT)})
        b = _arm(root, "b", {"q1": ([True] * 3, True, "y", [])})
        r = CA.compare(CA.load_arm(a), CA.load_arm(b), "a", "b")
        assert r["partial_match_sids_nonempty"]["a"] == CA.PARTIAL_NOT_REPORTED, r
        assert r["partial_match_sids_nonempty"]["b"] == [], r
        assert r["partial_match_sids_nonempty"]["a"] != r["partial_match_sids_nonempty"]["b"], r
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_partial_match_sids_not_reported_is_never_equal_to_empty():
    # Companion assertion for the two tests above: without a real tri-state, NOT_REPORTED could
    # be implemented as `[]` (falling back to dict.get's default) and every one of these
    # assertions on the *value itself* would still read as "falsy" -- this pins the literal
    # inequality, not just a truthiness check.
    assert CA.PARTIAL_NOT_REPORTED != []
    assert CA.PARTIAL_NOT_REPORTED is not None


def test_median_answer_length_per_arm():
    root = tempfile.mkdtemp()
    try:
        a = _arm(root, "a", {"q1": ([True] * 3, True, "x" * 100, []),
                             "q2": ([True] * 3, True, "x" * 300, [])})
        b = _arm(root, "b", {"q1": ([True] * 3, True, "x" * 100, []),
                             "q2": ([True] * 3, True, "x" * 100, [])})
        r = CA.compare(CA.load_arm(a), CA.load_arm(b), "a", "b")
        assert r["median_answer_len"]["a"] == 200 and r["median_answer_len"]["b"] == 100, r
    finally:
        shutil.rmtree(root, ignore_errors=True)


# A hand-rolled suite reports what it RAN, and a raise inside a test file ends the run silently.
# Pin the count so a test lost to a rename or a bad merge is a failure rather than a smaller
# number nobody reads. (This guard has caught my own miscount three times.)
EXPECTED_TESTS = 28

if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    assert len(tests) == EXPECTED_TESTS,         "collected %d tests, expected %d" % (len(tests), EXPECTED_TESTS)
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except KeyboardInterrupt:
            raise
        # SystemExit is NOT an Exception, so `except Exception` let a test that reaches sys.exit
        # end the WHOLE run silently -- no summary line, which reads as a shorter suite. Witnessed
        # 2026-10-11 in evals/test_gate_paired.py (argparse exits 2 on an unrecognized flag).
        except BaseException:
            failed += 1
            print(f"  FAIL  {name}")
            traceback.print_exc()
    print("")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
