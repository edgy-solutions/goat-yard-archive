"""Born-tests for the paired gate. Offline; builds arm directories on disk from literals.

    python evals/test_gate_paired.py

What is under test is mostly the gate's REFUSALS and its two SILENCES: a delta read without a
null, and the two ways a result can look like a verdict without being one (no discordant pair is
not p=1; a question excluded from the test is not a zero). The arithmetic of the sign test is
checked against hand-computed exact values, not against another implementation of itself.
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
import gate_paired as G  # noqa: E402
from compare_arms import load_arm  # noqa: E402

PIN = {"order": ["streamlake"], "allow_fallbacks": False}
LM = {"distinct": [{"client": "baml", "model_returned": "deepseek-chat",
                    "temperature_on_the_wire": 0, "provider_served": "streamlake"}]}
N = 5  # the ruling-1 minimum, so no test raises the under-powered note by accident


def _arm(root, name, questions, pin=PIN, answer_lm=LM):
    """questions: {qid: run_passes}. A run_passes of [None]*k is a NO-DATA question."""
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    for qid, passes in questions.items():
        rec = {"question": {"id": qid}, "run_passes": list(passes),
               "score": {"id": qid, "refusal_correct": True, "expected_behavior": "answer"},
               "response": {"answer": "x" * 50, "refused": False, "partial_match_sids": []}}
        io.open(os.path.join(d, qid + ".json"), "w", encoding="utf-8").write(json.dumps(rec))
    summary = {"openrouter_provider_pin": pin}
    if answer_lm is not None:
        summary["answer_lm"] = answer_lm
    io.open(os.path.join(d, "summary.json"), "w", encoding="utf-8").write(json.dumps(summary))
    return d


def _k(k, n=N):
    """A run_passes with k passes out of n."""
    return [True] * k + [False] * (n - k)


def _tmp():
    return tempfile.mkdtemp()


# --- the sign test, against hand-computed exact values ------------------------------

def test_sign_test_is_the_exact_two_sided_binomial():
    # 5 discordant pairs all one way: 2 * (1/2)^5 = 0.0625, which is ABOVE 0.05. Six are needed:
    # 2 * (1/2)^6 = 0.03125. This is the whole power story of the gate on a small question set,
    # and it is a fact about the test, not about the flag.
    assert G.sign_test_two_sided(5, 0) == 0.0625
    assert G.sign_test_two_sided(6, 0) == 0.03125
    assert G.sign_test_two_sided(0, 6) == 0.03125, "the test is two-sided"
    assert G.sign_test_two_sided(3, 3) == 1.0
    # 2 * P(X<=1 | n=7) = 2 * (1+7)/128
    assert abs(G.sign_test_two_sided(6, 1) - 2 * 8 / 128.0) < 1e-12


def test_no_discordant_pair_is_NOT_p_equals_one():
    # "every question moved exactly as much as the null" and "no evidence either way" are
    # different facts. A gate that renders the second as a comfortable 1.0 has reported a
    # measurement it did not make.
    assert G.sign_test_two_sided(0, 0) is None


def test_a_p_value_is_never_above_one():
    assert G.sign_test_two_sided(1, 1) == 1.0


# --- refusals -----------------------------------------------------------------------

def test_NO_NULL_PAIR_is_a_refusal_not_a_default():
    root = _tmp()
    try:
        a = _arm(root, "off", {"q1": _k(5)})
        b = _arm(root, "on", {"q1": _k(0)})
        try:
            G.gate(load_arm(a), load_arm(b), [])
            raise AssertionError("a delta with no null must not be computable")
        except SystemExit as e:
            assert "no null pair supplied" in str(e), str(e)
            assert "14 of 78" in str(e), "the refusal must carry the measurement behind it"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_an_EFFECT_pair_that_does_not_share_a_question_set_is_refused():
    root = _tmp()
    try:
        off = _arm(root, "off", {"q1": _k(5), "q2": _k(5)})
        on = _arm(root, "on", {"q1": _k(5)})           # q2 was never asked under ON
        na = _arm(root, "na", {"q1": _k(5), "q2": _k(5)})
        nb = _arm(root, "nb", {"q1": _k(5), "q2": _k(5)})
        try:
            G.gate(load_arm(off), load_arm(on), [(load_arm(na), load_arm(nb))])
            raise AssertionError("there is no per-question delta over a question asked once")
        except SystemExit as e:
            assert "do not share a question set" in str(e), str(e)
            assert "q2" in str(e), str(e)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_NULL_PAIR_run_over_two_different_sets_is_refused():
    # The two halves of a null must have been asked the same questions, or the spread between
    # them is not a noise measurement.
    root = _tmp()
    try:
        off = _arm(root, "off", {"q1": _k(5), "q2": _k(5)})
        on = _arm(root, "on", {"q1": _k(5), "q2": _k(5)})
        na = _arm(root, "na", {"q1": _k(5)})
        nb = _arm(root, "nb", {"q1": _k(5), "q2": _k(5)})
        try:
            G.gate(load_arm(off), load_arm(on), [(load_arm(na), load_arm(nb))])
            raise AssertionError("an asymmetric null pair is not a null pair")
        except SystemExit as e:
            assert "two different question sets" in str(e), str(e)
            assert "q2" in str(e), str(e)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_null_pair_SMALLER_than_the_effect_pair_excludes_not_refuses():
    # The floor pair on disk (13 questions, N=6) is smaller than the arms it bounds (16, N=5).
    # Refusing that comparison outright would discard the only null measurement there is; giving
    # the uncovered question a band of 0 would hand it a free regression. It is excluded, named.
    root = _tmp()
    try:
        off = _arm(root, "off", {"q1": _k(5), "q2": _k(5)})
        on = _arm(root, "on", {"q1": _k(5), "q2": _k(0)})
        na = _arm(root, "na", {"q1": _k(5)})           # q2 not covered by the null
        nb = _arm(root, "nb", {"q1": _k(5)})
        r = G.gate(load_arm(off), load_arm(on), [(load_arm(na), load_arm(nb))])
        assert r["questions_shared"] == 2 and r["questions_tested"] == 1, r
        assert r["excluded_ids"] == ["q2"], r["excluded_ids"]
        assert r["regressions_beyond_noise_n"] == 0, "an uncovered 5/5 -> 0/5 is not a measured "
        assert any("DOES NOT COVER" in n and "q2" in n for n in r["notes"]), r["notes"]
        # but the RATCHET still sees it: clause (b) needs no null.
        assert r["ratchet_tripped_n"] == 1 and r["ratchet_tripped"][0]["id"] == "q2", r
        assert r["gate_fires"] is True, r["verdict"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_question_covered_by_only_ONE_of_two_null_pairs_takes_that_pairs_band():
    root = _tmp()
    try:
        off = _arm(root, "off", {"q1": _k(5), "q2": _k(5)})
        on = _arm(root, "on", {"q1": _k(5), "q2": _k(2)})          # q2 effect = -0.6
        n0a = _arm(root, "n0a", {"q1": _k(5)})                      # does not cover q2
        n0b = _arm(root, "n0b", {"q1": _k(5)})
        n1a = _arm(root, "n1a", {"q1": _k(5), "q2": _k(5)})
        n1b = _arm(root, "n1b", {"q1": _k(5), "q2": _k(1)})         # q2 band = 0.8
        r = G.gate(load_arm(off), load_arm(on),
                   [(load_arm(n0a), load_arm(n0b)), (load_arm(n1a), load_arm(n1b))])
        q2 = [x for x in r["rows"] if x["id"] == "q2"][0]
        assert q2["noise_band"] == 0.8, q2
        assert q2["null_deltas"] == [None, -0.8], q2["null_deltas"]
        assert r["regressions_beyond_noise_n"] == 0, r["regressions_beyond_noise"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_an_under_powered_arm_says_so():
    root = _tmp()
    try:
        off = _arm(root, "off", {"q1": [True] * 3})
        on = _arm(root, "on", {"q1": [True] * 3})
        na = _arm(root, "na", {"q1": [True] * 3})
        nb = _arm(root, "nb", {"q1": [True] * 3})
        r = G.gate(load_arm(off), load_arm(on), [(load_arm(na), load_arm(nb))])
        assert sum(1 for n in r["notes"] if "UNDER-POWERED" in n) == 4, r["notes"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_null_pair_whose_arms_differ_is_named_as_not_a_null():
    root = _tmp()
    try:
        off = _arm(root, "off", {"q1": _k(5)})
        on = _arm(root, "on", {"q1": _k(5)})
        na = _arm(root, "na", {"q1": _k(5)}, pin={"order": ["other"]})
        nb = _arm(root, "nb", {"q1": _k(5)})
        r = G.gate(load_arm(off), load_arm(on), [(load_arm(na), load_arm(nb))])
        assert any("NULL PAIR 0 IS NOT A NULL" in n and "provider pin" in n for n in r["notes"]), \
            r["notes"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_null_pair_served_differently_is_named_too():
    root = _tmp()
    try:
        off = _arm(root, "off", {"q1": _k(5)})
        on = _arm(root, "on", {"q1": _k(5)})
        hot = {"distinct": [dict(LM["distinct"][0], temperature_on_the_wire=None)]}
        na = _arm(root, "na", {"q1": _k(5)}, answer_lm=hot)
        nb = _arm(root, "nb", {"q1": _k(5)})
        r = G.gate(load_arm(off), load_arm(on), [(load_arm(na), load_arm(nb))])
        assert any("IS NOT A NULL" in n and "served them" in n for n in r["notes"]), r["notes"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --- the noise band -----------------------------------------------------------------

def test_the_noise_band_is_the_MAX_across_null_pairs():
    # One null replicate understates the noise. An effect of 0.4 beats a 0.2 band and must NOT
    # beat a second pair's 0.6 band; the gate takes the larger, which is the conservative
    # direction.
    root = _tmp()
    try:
        off = _arm(root, "off", {"q1": _k(5)})
        on = _arm(root, "on", {"q1": _k(3)})               # effect = -0.4
        n0a = _arm(root, "n0a", {"q1": _k(5)})
        n0b = _arm(root, "n0b", {"q1": _k(4)})             # band 0.2
        n1a = _arm(root, "n1a", {"q1": _k(5)})
        n1b = _arm(root, "n1b", {"q1": _k(2)})             # band 0.6
        r = G.gate(load_arm(off), load_arm(on),
                   [(load_arm(n0a), load_arm(n0b)), (load_arm(n1a), load_arm(n1b))])
        row = r["rows"][0]
        assert row["noise_band"] == 0.6, row
        assert row["beats_noise"] is False, row
        assert r["regressions_beyond_noise_n"] == 0, r["regressions_beyond_noise"]
        # and with the wide pair alone it WOULD have been a regression, which is the point
        r1 = G.gate(load_arm(off), load_arm(on), [(load_arm(n0a), load_arm(n0b))])
        assert r1["regressions_beyond_noise_n"] == 1, r1["regressions_beyond_noise"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_question_with_no_null_measurement_gets_NO_band_of_zero():
    # A band of 0 would make every movement on that question beat the noise by construction.
    root = _tmp()
    try:
        off = _arm(root, "off", {"q1": _k(5), "q2": _k(5)})
        on = _arm(root, "on", {"q1": _k(5), "q2": _k(0)})
        na = _arm(root, "na", {"q1": _k(5), "q2": [None] * N})
        nb = _arm(root, "nb", {"q1": _k(5), "q2": _k(5)})
        r = G.gate(load_arm(off), load_arm(on), [(load_arm(na), load_arm(nb))])
        assert r["excluded_ids"] == ["q2"], r["excluded_ids"]
        assert r["questions_tested"] == 1 and r["questions_shared"] == 2, r
        assert r["regressions_beyond_noise_n"] == 0, "a 5/5 -> 0/5 fall with no null is NOT a "
        assert any("EXCLUDED FROM THE TEST" in n and "q2" in n for n in r["notes"]), r["notes"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_NO_DATA_question_is_excluded_not_scored_as_zero():
    # Every run errored. `refusal_correct` defaults False on a missing response, and counting
    # that once made five HTTP-500 questions read as five regressions.
    root = _tmp()
    try:
        off = _arm(root, "off", {"q1": _k(5), "q2": _k(5)})
        on = _arm(root, "on", {"q1": _k(5), "q2": [None] * N})
        na = _arm(root, "na", {"q1": _k(5), "q2": _k(5)})
        nb = _arm(root, "nb", {"q1": _k(5), "q2": _k(5)})
        r = G.gate(load_arm(off), load_arm(on), [(load_arm(na), load_arm(nb))])
        assert r["excluded_ids"] == ["q2"], r["excluded_ids"]
        assert r["regressions_beyond_noise_n"] == 0, r["regressions_beyond_noise"]
        assert r["gate_fires"] is False, r["verdict"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_every_question_excluded_leaves_the_verdict_on_the_ratchet_alone():
    root = _tmp()
    try:
        off = _arm(root, "off", {"q1": [None] * N})
        on = _arm(root, "on", {"q1": [None] * N})
        na = _arm(root, "na", {"q1": _k(5)})
        nb = _arm(root, "nb", {"q1": _k(5)})
        r = G.gate(load_arm(off), load_arm(on), [(load_arm(na), load_arm(nb))])
        assert r["questions_tested"] == 0, r
        assert r["sign_test"]["p_two_sided"] is None, r["sign_test"]
        assert any("NO TESTABLE QUESTION" in n for n in r["notes"]), r["notes"]
        assert r["gate_fires"] is False, r["verdict"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_an_exact_tie_with_the_band_votes_for_NEITHER_side():
    # 3/5 - 2/5 is 0.19999999999999998 and 2/10 - 0/10 is exactly 0.2. Under a bare `>` that
    # artifact casts a vote in a gate.
    root = _tmp()
    try:
        off = _arm(root, "off", {"q1": _k(2)})
        on = _arm(root, "on", {"q1": _k(3)})               # effect = +0.2 (the inexact one)
        na = _arm(root, "na", {"q1": [True] * 0 + [False] * 10})
        nb = _arm(root, "nb", {"q1": [True] * 2 + [False] * 8})   # band = exactly 0.2
        r = G.gate(load_arm(off), load_arm(on), [(load_arm(na), load_arm(nb))])
        row = r["rows"][0]
        assert row["beats_noise"] is False and row["within_noise"] is False, row
        assert r["sign_test"]["ties"] == 1, r["sign_test"]
        assert r["sign_test"]["p_two_sided"] is None, r["sign_test"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --- the verdict --------------------------------------------------------------------

def _six(root, off_k, on_k, null_k=(5, 5)):
    """Six questions at the given pass counts, plus one null pair. Six is the smallest number of
    one-way discordant pairs the sign test can call significant at alpha=0.05."""
    off = _arm(root, "off", {("q%d" % i): _k(off_k) for i in range(6)})
    on = _arm(root, "on", {("q%d" % i): _k(on_k) for i in range(6)})
    na = _arm(root, "na", {("q%d" % i): _k(null_k[0]) for i in range(6)})
    nb = _arm(root, "nb", {("q%d" % i): _k(null_k[1]) for i in range(6)})
    return load_arm(off), load_arm(on), [(load_arm(na), load_arm(nb))]


def test_a_distinguishable_pair_that_only_IMPROVED_does_not_fire():
    root = _tmp()
    try:
        off, on, nulls = _six(root, off_k=1, on_k=5)       # +0.8 on every question, band 0
        r = G.gate(off, on, nulls)
        assert r["sign_test"]["p_two_sided"] == 0.03125, r["sign_test"]
        assert r["sign_test"]["significant"] is True, r["sign_test"]
        assert r["improvements_beyond_noise_n"] == 6, r["improvements_beyond_noise_n"]
        assert r["regressions_beyond_noise_n"] == 0, r["regressions_beyond_noise"]
        assert r["gate_fires"] is False, r["verdict"]
        assert any("DIFFERENT, BUT NOT WORSE" in n for n in r["notes"]), r["notes"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_distinguishable_pair_WITH_a_regression_fires():
    root = _tmp()
    try:
        off, on, nulls = _six(root, off_k=5, on_k=1)       # -0.8 on every question, band 0
        r = G.gate(off, on, nulls)
        assert r["sign_test"]["significant"] is True, r["sign_test"]
        assert r["regressions_beyond_noise_n"] == 6, r["regressions_beyond_noise_n"]
        assert r["gate_fires"] is True, r
        assert "paired test + regression" in r["verdict"], r["verdict"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_one_regression_in_a_pair_the_null_explains_does_NOT_fire():
    # The replaced gate fired on exactly this: one question down, nothing else, against an
    # unmeasured floor.
    root = _tmp()
    try:
        qs_off = {("q%d" % i): _k(5) for i in range(6)}
        qs_on = dict(qs_off, q0=_k(1))
        off = _arm(root, "off", qs_off)
        on = _arm(root, "on", qs_on)
        na = _arm(root, "na", {("q%d" % i): _k(5) for i in range(6)})
        nb = _arm(root, "nb", {("q%d" % i): _k(5) for i in range(6)})
        r = G.gate(load_arm(off), load_arm(on), [(load_arm(na), load_arm(nb))])
        assert r["regressions_beyond_noise_n"] == 1, r["regressions_beyond_noise"]
        # ONE discordant pair: 2 * (1/2)^1 = 1.0. Five questions moved by exactly their band (0)
        # and are ties, so the pair is one question's worth of evidence and says nothing.
        assert r["sign_test"]["wins_effect_beats_noise"] == 1, r["sign_test"]
        assert r["sign_test"]["ties"] == 5, r["sign_test"]
        assert r["sign_test"]["p_two_sided"] == 1.0, r["sign_test"]
        assert r["gate_fires"] is False, r["verdict"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_one_regression_against_a_wide_null_is_reported_but_not_fired():
    root = _tmp()
    try:
        qs = {("q%d" % i): _k(5) for i in range(6)}
        off = _arm(root, "off", qs)
        on = _arm(root, "on", dict(qs, q0=_k(1)))
        # one null pair that itself moved q1..q5, so most questions are DISCORDANT the other way
        na = _arm(root, "na", {("q%d" % i): _k(5) for i in range(6)})
        nb = _arm(root, "nb", dict({("q%d" % i): _k(2) for i in range(6)}, q0=_k(5)))
        r = G.gate(load_arm(off), load_arm(on), [(load_arm(na), load_arm(nb))])
        assert r["regressions_beyond_noise_n"] == 1, r["regressions_beyond_noise"]
        assert r["sign_test"]["significant"] is False, r["sign_test"]
        assert r["gate_fires"] is False, r["verdict"]
        assert any("WITHOUT A DISTINGUISHABLE PAIR" in n and "q0" in n for n in r["notes"]), \
            r["notes"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_regression_on_a_NON_GATING_question_cannot_fire_the_gate():
    # The defect this test exists for: with scapegoat_001 counted, the recorded 6/6 -> 0/6 fall
    # at FIXED configuration supplies a regression row, and a distinguishable pair plus that row
    # fires the gate -- which is exactly what ruling 1 pulled it from the gate to prevent.
    root = _tmp()
    try:
        qs_off = dict({("q%d" % i): _k(1) for i in range(6)}, scapegoat_001=_k(5))
        qs_on = dict({("q%d" % i): _k(5) for i in range(6)}, scapegoat_001=_k(0))
        off = _arm(root, "off", qs_off)
        on = _arm(root, "on", qs_on)
        na = _arm(root, "na", dict({("q%d" % i): _k(5) for i in range(6)}, scapegoat_001=_k(5)))
        nb = _arm(root, "nb", dict({("q%d" % i): _k(5) for i in range(6)}, scapegoat_001=_k(5)))
        r = G.gate(load_arm(off), load_arm(on), [(load_arm(na), load_arm(nb))])
        assert r["sign_test_gating"]["significant"] is True, r["sign_test_gating"]
        assert r["regressions_beyond_noise_n"] == 1, r["regressions_beyond_noise"]
        assert r["regressions_gating_n"] == 0, r["regressions_gating"]
        assert r["ratchet_tripped_n"] == 0 and r["ratchet_tripped_excluded_n"] == 1, r
        assert r["gate_fires"] is False, r["verdict"]
        assert any("EXCLUDED FROM THE DECISION" in n and "scapegoat_001" in n
                   for n in r["notes"]), r["notes"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_when_the_exclusions_change_the_sign_test_BOTH_numbers_are_reported():
    # Five gating wins is p=0.0625 (not significant); the three ruling-1 questions bring it to
    # eight, p=0.0078. A gate that printed only the second would be deciding on the coin.
    root = _tmp()
    try:
        ids = ["q%d" % i for i in range(5)] + list(G.NON_GATING)
        off = _arm(root, "off", {q: _k(1) for q in ids})
        on = _arm(root, "on", {q: _k(5) for q in ids})
        na = _arm(root, "na", {q: _k(5) for q in ids})
        nb = _arm(root, "nb", {q: _k(5) for q in ids})
        r = G.gate(load_arm(off), load_arm(on), [(load_arm(na), load_arm(nb))])
        assert r["sign_test"]["questions"] == 8 and r["sign_test_gating"]["questions"] == 5, r
        assert abs(r["sign_test"]["p_two_sided"] - 2 / 256.0) < 1e-12, r["sign_test"]
        assert r["sign_test_gating"]["p_two_sided"] == 0.0625, r["sign_test_gating"]
        assert r["sign_test"]["significant"] is True
        assert r["sign_test_gating"]["significant"] is False, "the decision uses the gating set"
        assert any("THE EXCLUSIONS CHANGE THE SIGN TEST" in n for n in r["notes"]), r["notes"]
        assert r["gate_fires"] is False, r["verdict"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --- the ratchet (clause b) ---------------------------------------------------------

def test_the_ratchet_fires_on_a_stable_fail_that_once_stable_passed():
    root = _tmp()
    try:
        off = _arm(root, "off", {"q1": _k(5)})             # STABLE-PASS
        on = _arm(root, "on", {"q1": _k(0)})               # STABLE-FAIL
        na = _arm(root, "na", {"q1": _k(5)})
        nb = _arm(root, "nb", {"q1": _k(5)})
        r = G.gate(load_arm(off), load_arm(on), [(load_arm(na), load_arm(nb))])
        assert r["ratchet_tripped_n"] == 1, r["ratchet_tripped"]
        assert r["ratchet_tripped"][0]["id"] == "q1"
        assert "OFF" in r["ratchet_tripped"][0]["stable_passed_in"], r["ratchet_tripped"][0]
        assert r["gate_fires"] is True and "ratchet" in r["verdict"], r["verdict"]
        # and it fires WITHOUT significance: one question cannot be significant.
        assert r["sign_test"]["significant"] is False, r["sign_test"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_the_ratchet_honours_the_ruling_1_exclusions():
    # scapegoat_001 is the recorded 6/6 -> 0/6 fall at FIXED configuration. An unexcluded ratchet
    # fires on the coin on its first run.
    root = _tmp()
    try:
        off = _arm(root, "off", {"scapegoat_001": _k(5)})
        on = _arm(root, "on", {"scapegoat_001": _k(0)})
        na = _arm(root, "na", {"scapegoat_001": _k(5)})
        nb = _arm(root, "nb", {"scapegoat_001": _k(5)})
        r = G.gate(load_arm(off), load_arm(on), [(load_arm(na), load_arm(nb))])
        assert r["ratchet_tripped_n"] == 0, r["ratchet_tripped"]
        assert r["ratchet_tripped_excluded_n"] == 1, r["ratchet_tripped_excluded"]
        assert r["gate_fires"] is False, r["verdict"]
        assert any("RATCHET TRIP(S) EXCLUDED" in n and "scapegoat_001" in n for n in r["notes"]), \
            r["notes"]
        assert r["non_gating_questions"] == ["scapegoat_001"], r["non_gating_questions"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_the_ratchet_reaches_back_into_HISTORY_arms():
    # The question never stable-passed in any of the four arms under comparison; it did in an
    # older one. "Ever" means ever.
    root = _tmp()
    try:
        off = _arm(root, "off", {"q1": _k(2)})             # FLAKY
        on = _arm(root, "on", {"q1": _k(0)})               # STABLE-FAIL
        na = _arm(root, "na", {"q1": _k(2)})
        nb = _arm(root, "nb", {"q1": _k(2)})
        hist = _arm(root, "hist", {"q1": _k(5)})           # STABLE-PASS, long ago
        nulls = [(load_arm(na), load_arm(nb))]
        without = G.gate(load_arm(off), load_arm(on), nulls)
        assert without["ratchet_tripped_n"] == 0, without["ratchet_tripped"]
        with_hist = G.gate(load_arm(off), load_arm(on), nulls, history=[load_arm(hist)])
        assert with_hist["ratchet_tripped_n"] == 1, with_hist["ratchet_tripped"]
        assert with_hist["ratchet_tripped"][0]["stable_passed_in"] == ["a --history arm only"], \
            with_hist["ratchet_tripped"][0]
        assert with_hist["gate_fires"] is True
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_question_that_NEVER_stable_passed_does_not_trip_the_ratchet():
    # The companion assertion: an implementation that tripped on any STABLE-FAIL under ON would
    # pass the three tests above and fire on every question that never worked.
    root = _tmp()
    try:
        off = _arm(root, "off", {"q1": _k(0)})
        on = _arm(root, "on", {"q1": _k(0)})
        na = _arm(root, "na", {"q1": _k(0)})
        nb = _arm(root, "nb", {"q1": _k(0)})
        r = G.gate(load_arm(off), load_arm(on), [(load_arm(na), load_arm(nb))])
        assert r["ratchet_tripped_n"] == 0, r["ratchet_tripped"]
        assert r["gate_fires"] is False, r["verdict"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_stable_pass_in_the_NULL_arms_counts_as_ever():
    root = _tmp()
    try:
        off = _arm(root, "off", {"q1": _k(2)})
        on = _arm(root, "on", {"q1": _k(0)})
        na = _arm(root, "na", {"q1": _k(5)})               # stable-passed here
        nb = _arm(root, "nb", {"q1": _k(2)})
        r = G.gate(load_arm(off), load_arm(on), [(load_arm(na), load_arm(nb))])
        assert r["ratchet_tripped_n"] == 1, r["ratchet_tripped"]
        assert r["ratchet_tripped"][0]["stable_passed_in"] == ["null0.a"], r["ratchet_tripped"][0]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_both_clauses_firing_are_named_in_the_verdict():
    root = _tmp()
    try:
        off, on, nulls = _six(root, off_k=5, on_k=0)
        r = G.gate(off, on, nulls)
        assert r["ratchet_tripped_n"] == 6 and r["regressions_beyond_noise_n"] == 6, r
        assert r["gate_fires"] is True
        assert "ratchet" in r["verdict"] and "paired test + regression" in r["verdict"], \
            r["verdict"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --- the CLI ------------------------------------------------------------------------

def test_main_exits_1_when_the_gate_fires_and_0_when_it_does_not():
    root = _tmp()
    try:
        off = _arm(root, "off", {"q1": _k(5)})
        on_bad = _arm(root, "on_bad", {"q1": _k(0)})
        on_ok = _arm(root, "on_ok", {"q1": _k(5)})
        na = _arm(root, "na", {"q1": _k(5)})
        nb = _arm(root, "nb", {"q1": _k(5)})
        jf = os.path.join(root, "gate.json")
        assert G.main(["--off", off, "--on", on_bad, "--null", na, nb,
                       "--json-out", jf]) == 1
        assert G.main(["--off", off, "--on", on_ok, "--null", na, nb]) == 0
        written = json.load(io.open(jf, encoding="utf-8"))
        assert written["gate_fires"] is True and written["ratchet_tripped_n"] == 1, written
        assert written["null_pairs"] == 1 and written["alpha"] == 0.05, written
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_the_parser_can_actually_render_its_own_help():
    # A bare "%" in an argparse help string raises at FORMAT time, not at definition time, so
    # every test that only parses args passes while --help and the usage message on a bad flag
    # both crash. Cost me one in run_eval.py on 2026-10-04.
    import subprocess
    r = subprocess.run([sys.executable, str(Path(G.__file__)), "--help"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr[-800:]
    assert "--null" in r.stdout and "--history" in r.stdout, r.stdout[:400]


def test_alpha_is_reported_next_to_the_p_value_it_judged():
    # A verdict that does not carry the threshold it used is not reproducible from its own output.
    root = _tmp()
    try:
        off, on, nulls = _six(root, off_k=1, on_k=5)
        strict = G.gate(off, on, nulls, alpha=0.01)
        assert strict["alpha"] == 0.01
        assert strict["sign_test"]["p_two_sided"] == 0.03125
        assert strict["sign_test"]["significant"] is False, "0.03125 > 0.01"
    finally:
        shutil.rmtree(root, ignore_errors=True)


# A hand-rolled suite reports what it RAN, and a raise inside a test file ends the run silently.
# Pin the count so a test lost to a rename or a bad merge is a failure rather than a smaller
# number nobody reads.
EXPECTED_TESTS = 33


def test_a_null_pair_sharing_an_arm_with_the_effect_is_named_as_NOT_INDEPENDENT():
    """A band computed from the effect pair's OWN off arm is correlated with the effect, and the
    correlation runs toward silence: the band widens exactly where the effect widens. This is the
    pair that moved rerun3's gating sign test from p=0.039 to p=0.4531 by itself, so a non-firing
    verdict read off such a band has to carry the warning."""
    root = _tmp()
    try:
        off = _arm(root, "off", {"q1": _k(5)})
        on = _arm(root, "on", {"q1": _k(0)})
        nb = _arm(root, "nb", {"q1": _k(2)})
        sources = {"off": off, "on": on, "null0.a": off, "null0.b": nb}
        r = G.gate(load_arm(off), load_arm(on), [(load_arm(off), load_arm(nb))],
                   labels={"off": "off", "on": "on"}, sources=sources)
        hits = [n for n in r["notes"] if "NOT INDEPENDENT" in n]
        assert len(hits) == 1, r["notes"]
        assert "its a arm is the same run directory as off" in hits[0], hits[0]
        assert "toward silence" in hits[0], hits[0]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_independent_null_pairs_and_an_absent_source_map_say_nothing():
    """The note must not fire on the ordinary case, and must not require the source map at all:
    every other test in this file calls gate() with dicts and no paths."""
    root = _tmp()
    try:
        off, on, nulls = _six(root, off_k=5, on_k=0, null_k=(5, 3))
        indep = {"off": "/runs/a/off", "on": "/runs/a/on",
                 "null0.a": "/runs/z/armA", "null0.b": "/runs/z/armB"}
        for sources in (indep, None, {}):
            r = G.gate(off, on, nulls, labels={"off": "off", "on": "on"}, sources=sources)
            assert not [n for n in r["notes"] if "NOT INDEPENDENT" in n], (sources, r["notes"])
    finally:
        shutil.rmtree(root, ignore_errors=True)

if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    assert len(tests) == EXPECTED_TESTS, \
        "collected %d tests, expected %d" % (len(tests), EXPECTED_TESTS)
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("  PASS  %s" % name)
        except Exception:
            failed += 1
            print("  FAIL  %s" % name)
            traceback.print_exc()
    print("")
    print("%d/%d passed" % (len(tests) - failed, len(tests)))
    sys.exit(1 if failed else 0)
