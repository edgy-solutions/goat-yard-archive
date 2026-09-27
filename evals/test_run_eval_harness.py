"""Born-tests for the run_eval harness integrity changes (ruling 1, 2026-09-27).

Offline: no network, no endpoint, no model. `call_endpoint` is stubbed where a request
would otherwise be made, so these run anywhere and cannot touch a reserved GPU endpoint.

What is under test is not "does the harness compute a number" but "does the harness refuse
to compute a number it has no data for". On 2026-09-20 the flag-on arm reported 17/28 with
14 of 84 runs having produced no generation at all, and an N=3 stability block whose extra
runs were in-process cache replays. Both conditions were invisible in the output.

    python test_run_eval_harness.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_eval as RE  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from degradation import TIMEOUT_FALLBACK_ANSWER, DEGRADED_LLM_TIMEOUT  # noqa: E402

Q_ANSWER = {
    "id": "t_answer", "question": "What does Gill say?", "category": "doctrine",
    "difficulty": "easy", "expected_behavior": "answer", "must_cite": ["[GENESIS_2_8_S01]"],
}
Q_REFUSE = {
    "id": "t_refuse", "question": "Did Esau eat pizza?", "category": "refusal_anachronism",
    "difficulty": "easy", "expected_behavior": "refuse",
}
GOOD = {"answer": "Gill holds this [GENESIS_2_8_S01].", "generation_seconds": 12.5,
        "lm_cache_enabled": False}


# --- degradation is an ERROR, never a FAIL -----------------------------------------

def test_unlabelled_fallback_is_error_not_fail():
    r = RE.score(Q_ANSWER, {"answer": TIMEOUT_FALLBACK_ANSWER}, 90.0)
    assert r.degraded == RE.DEGRADED_UNLABELLED, r.degraded
    assert r.error and "DEGRADED" in r.error, r.error
    assert r.overall_pass is False


def test_structured_degraded_field_is_honoured():
    r = RE.score(Q_ANSWER, {"answer": TIMEOUT_FALLBACK_ANSWER,
                            "degraded": DEGRADED_LLM_TIMEOUT}, 181.0)
    assert r.degraded == DEGRADED_LLM_TIMEOUT, r.degraded
    assert r.error


def test_degraded_run_is_not_scored_at_all():
    """No content comparison may happen on a placeholder - not even a favourable one."""
    r = RE.score(Q_ANSWER, {"answer": TIMEOUT_FALLBACK_ANSWER}, 90.0)
    assert r.cited_ids == [], r.cited_ids
    assert r.must_cite_recall == 0.0
    assert r.refusal_correct is False


def test_degraded_refusal_question_is_not_credited_as_a_refusal():
    """The trap: a timeout placeholder contains no citations and reads as a non-answer, so
    a naive scorer marks a refusal question CORRECT for a question never asked."""
    r = RE.score(Q_REFUSE, {"answer": TIMEOUT_FALLBACK_ANSWER}, 90.0)
    assert r.degraded, "placeholder on a refusal question must be degraded"
    assert r.refusal_correct is False, "must not be credited as a correct refusal"
    assert r.overall_pass is False


def test_harness_read_timeout_is_labelled_degraded():
    r = RE.score(Q_ANSWER, {"_error": "ReadTimeout: x",
                            "_degraded": RE.DEGRADED_HARNESS_TIMEOUT}, 200.0)
    assert r.degraded == RE.DEGRADED_HARNESS_TIMEOUT
    assert r.error


def test_plain_transport_error_stays_an_error_without_degraded_label():
    r = RE.score(Q_ANSWER, {"_error": "ConnectError: refused"}, 0.1)
    assert r.error and r.degraded is None


def test_good_response_still_scores():
    """Regression guard: the degradation gate must not swallow real answers."""
    r = RE.score(Q_ANSWER, GOOD, 12.6)
    assert r.error is None and r.degraded is None
    assert r.cited_ids == ["[GENESIS_2_8_S01]"], r.cited_ids
    assert r.must_cite_recall == 1.0
    assert r.overall_pass is True
    assert r.generation_seconds == 12.5 and r.lm_cache_enabled is False


# --- errors out of the denominator ------------------------------------------------

def test_errors_excluded_from_denominators():
    rs = [RE.score(Q_ANSWER, GOOD, 1.0),
          RE.score(dict(Q_ANSWER, id="t_fail"), {"answer": "no citation here"}, 1.0),
          RE.score(dict(Q_ANSWER, id="t_deg"), {"answer": TIMEOUT_FALLBACK_ANSWER}, 90.0)]
    s = RE.summarize(rs, "http://x/api/search")
    assert s["attempted"] == 3, s["attempted"]
    assert s["total"] == 2, s["total"]
    assert s["passed"] == 1 and s["pass_pct"] == 50.0, (s["passed"], s["pass_pct"])
    assert s["errors"] == 1 and s["degraded"] == 1
    assert [e["id"] for e in s["error_detail"]] == ["t_deg"]
    assert s["by_category"]["doctrine"]["total"] == 2, "degraded row in a category total"


def test_all_degraded_reports_zero_over_zero_not_zero_percent_of_n():
    rs = [RE.score(dict(Q_ANSWER, id="t%d" % i), {"answer": TIMEOUT_FALLBACK_ANSWER}, 90.0)
          for i in range(3)]
    s = RE.summarize(rs, "http://x/api/search")
    assert s["total"] == 0 and s["passed"] == 0 and s["pass_pct"] == 0
    assert s["attempted"] == 3 and s["errors"] == 3


# --- stability over scored runs only ----------------------------------------------

def test_no_data_is_not_stable_fail():
    assert RE.classify_stability([], 3) == "NO-DATA"


def test_stable_labels_over_scored_runs():
    assert RE.classify_stability([True, True, True], 3) == "STABLE-PASS"
    assert RE.classify_stability([False, False], 3) == "STABLE-FAIL"
    assert RE.classify_stability([True, False], 3) == "FLAKY"


def test_single_scored_pass_out_of_three_runs_is_stable_pass_not_flaky():
    """One scored run that passed is STABLE-PASS over what was measured; the partial count
    is reported separately rather than being smuggled into the label."""
    assert RE.classify_stability([True], 3) == "STABLE-PASS"


# --- run integrity: N runs must be N generations ----------------------------------

def _res(qid, gen, cache=False, err=None):
    payload = {"_error": err} if err else dict(GOOD, generation_seconds=gen,
                                               lm_cache_enabled=cache)
    return RE.score(dict(Q_ANSWER, id=qid), payload, 1.0)


def test_cache_replay_is_an_integrity_violation():
    v = RE.check_run_integrity({"q": [_res("q", 12.0), _res("q", 0.0), _res("q", 0.001)]},
                               allow_lm_cache=False)
    assert len(v) == 1 and "2/3" in v[0], v


def test_cache_enabled_endpoint_is_an_integrity_violation():
    v = RE.check_run_integrity({"q": [_res("q", 12.0, cache=True)]}, allow_lm_cache=False)
    assert any("cache-enabled" in x for x in v), v


def test_clean_runs_have_no_violations():
    v = RE.check_run_integrity({"q": [_res("q", 12.0), _res("q", 9.5), _res("q", 20.1)]},
                               allow_lm_cache=False)
    assert v == [], v


def test_allow_lm_cache_suppresses_the_assertion():
    v = RE.check_run_integrity({"q": [_res("q", 0.0, cache=True)]}, allow_lm_cache=True)
    assert v == [], v


def test_error_only_question_is_not_an_integrity_violation():
    v = RE.check_run_integrity({"q": [_res("q", 0, err="ReadTimeout")]}, allow_lm_cache=False)
    assert v == [], v


# --- preflight aborts before scoring ----------------------------------------------

class _Stub:
    def __init__(self, resp):
        self.resp, self.calls = resp, 0

    def __call__(self, endpoint, question, auth, timeout):
        self.calls += 1
        return dict(self.resp)


def _preflight(resp, n_runs=3, allow_cache=False, warmup=True):
    stub, orig = _Stub(resp), RE.call_endpoint
    RE.call_endpoint = stub
    try:
        info, rc = RE.preflight("http://x/api/search", None, 200.0, n_runs, allow_cache, warmup)
    finally:
        RE.call_endpoint = orig
    return info, rc, stub


def test_preflight_aborts_when_lm_cache_enabled():
    _, rc, _ = _preflight(dict(GOOD, lm_cache_enabled=True))
    assert rc == 3, rc


def test_preflight_aborts_when_cache_state_unknown():
    _, rc, _ = _preflight({"answer": "ok", "generation_seconds": 5.0})
    assert rc == 3, rc


def test_preflight_passes_when_cache_disabled():
    _, rc, stub = _preflight(GOOD)
    assert rc == 0 and stub.calls == 1


def test_preflight_aborts_when_warmup_itself_degrades():
    _, rc, _ = _preflight({"answer": TIMEOUT_FALLBACK_ANSWER})
    assert rc == 2, rc


def test_preflight_aborts_when_warmup_errors():
    _, rc, _ = _preflight({"_error": "ConnectError"})
    assert rc == 2, rc


def test_single_run_tolerates_unknown_cache_state():
    """N=1 makes no stability claim, so an unverifiable cache is not fatal there."""
    _, rc, _ = _preflight({"answer": "ok"}, n_runs=1)
    assert rc == 0, rc


def test_allow_lm_cache_does_not_abort():
    _, rc, _ = _preflight(dict(GOOD, lm_cache_enabled=True), allow_cache=True)
    assert rc == 0, rc


def test_no_warmup_sends_no_request():
    info, rc, stub = _preflight(GOOD, warmup=False)
    assert rc == 0 and stub.calls == 0 and info["warmup_ran"] is False


# --- wiring (a constant nothing calls is the defect this work exists to fix) ------

SRC = (Path(__file__).resolve().parent / "run_eval.py").read_text(encoding="utf-8")


def test_debug_flag_is_actually_sent():
    assert '"debug": True' in SRC, "zone3_notes is only captured when debug is requested"


def test_harness_timeout_default_exceeds_server_wall():
    assert "default=200.0" in SRC, "harness wall must exceed the server 180s wall"


def test_preflight_is_called_before_the_question_loop():
    i_pre = SRC.index("warmup_info, pre_rc = preflight(")
    i_loop = SRC.index("for i, q in enumerate(questions, 1)")
    assert i_pre < i_loop, "preflight must run before anything is scored"


def test_integrity_violation_fails_the_exit_code():
    assert "return 4" in SRC and "if integrity_violations:" in SRC


def test_representative_row_prefers_a_scored_run():
    assert "scored_runs[-1] if scored_runs else runs[-1]" in SRC


def test_harness_never_addresses_an_ollama_host_directly():
    """The embedding fleet in the LiteLLM model_list is 192.168.1.179/.188 (E/F, reserved).
    The warmup goes through the application, so the harness has no business holding an
    Ollama host, port or path - including to pin keep_alive."""
    for forbidden in ("11434", "11435", "/api/chat", "/api/embed", "api/tags"):
        assert forbidden not in SRC, "run_eval.py addresses an Ollama surface: " + forbidden


def test_fallback_constant_is_not_duplicated_here():
    assert "ink has dried" not in SRC, "harness must import the constant, not copy it"


if __name__ == "__main__":
    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passed += 1
            except AssertionError as e:
                failed += 1
                print("FAIL %s: %s" % (name, e))
            except Exception as e:
                failed += 1
                print("ERROR %s: %s: %s" % (name, type(e).__name__, e))
    print("%d passed, %d failed" % (passed, failed))
    sys.exit(1 if failed else 0)
