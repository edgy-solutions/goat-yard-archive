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


def _arm(root, name, questions, pin=PIN):
    """questions: {qid: (run_passes, refusal_correct, answer, partial_match_sids)}"""
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    for qid, (passes, refusal_ok, answer, partial) in questions.items():
        rec = {"question": {"id": qid}, "run_passes": list(passes),
               "score": {"id": qid, "refusal_correct": refusal_ok, "expected_behavior": "answer"},
               "response": {"answer": answer, "partial_match_sids": partial, "refused": False}}
        io.open(os.path.join(d, qid + ".json"), "w", encoding="utf-8").write(json.dumps(rec))
    io.open(os.path.join(d, "summary.json"), "w", encoding="utf-8").write(
        json.dumps({"openrouter_provider_pin": pin}))
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


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception:
            failed += 1
            print(f"  FAIL  {name}")
            traceback.print_exc()
    print("")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
