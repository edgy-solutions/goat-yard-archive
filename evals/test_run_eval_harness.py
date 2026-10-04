"""Born-tests for the run_eval harness integrity changes (ruling 1, 2026-09-27).

Offline: no network, no endpoint, no model. `call_endpoint` is stubbed where a request
would otherwise be made, so these run anywhere and cannot touch a reserved GPU endpoint.

What is under test is not "does the harness compute a number" but "does the harness refuse
to compute a number it has no data for". On 2026-09-20 the flag-on arm reported 17/28 with
14 of 84 runs having produced no generation at all, and an N=3 stability block whose extra
runs were in-process cache replays. Both conditions were invisible in the output.

    python test_run_eval_harness.py
"""
import contextlib
import hashlib
import io
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_eval as RE  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from degradation import (  # noqa: E402
    DEGRADED_ASSERTION,
    DEGRADED_LLM_TIMEOUT,
    DEGRADED_UPSTREAM_RATE_LIMIT,
    GENERATION_FAILURE_ANSWER,
    TIMEOUT_FALLBACK_ANSWER,
)

Q_ANSWER = {
    "id": "t_answer", "question": "What does Gill say?", "category": "doctrine",
    "difficulty": "easy", "expected_behavior": "answer", "must_cite": ["[GENESIS_2_8_S01]"],
}
Q_REFUSE = {
    "id": "t_refuse", "question": "Did Esau eat pizza?", "category": "refusal_anachronism",
    "difficulty": "easy", "expected_behavior": "refuse",
}
# A per-call answer_lm record as the endpoint reports it. Shaped by backend/answer_lm_record.py;
# its own born-tests live in backend/test_answer_lm_record.py. Present in GOOD because a response
# from a current endpoint carries one, and its ABSENCE is now an integrity violation (ruling 2).
LM_REC = {"path": "dspy", "client": "dspy.LM", "model_requested": "openai/deepseek/deepseek-chat",
          "model_returned": "deepseek/deepseek-chat", "temperature_on_the_wire": 0.0,
          "provider_pin": {"order": ["streamlake"], "allow_fallbacks": False},
          "provider_served": "StreamLake", "provider_served_source": "dspy_response_attribute",
          "pin_honored": True}

# The `stages` block as a healthy endpoint reports it under debug:true. Present in GOOD
# because an endpoint that cannot say whether query expansion ran is now a refusal of its own
# (expansion_healthy), and a fixture without one would make every test using GOOD fail for a
# reason it is not about.
STAGES_OK = {"baml_error": None, "baml_fallback": None}

GOOD = {"answer": "Gill holds this [GENESIS_2_8_S01].", "generation_seconds": 12.5,
        "lm_cache_enabled": False, "answer_lm": dict(LM_REC), "stages": dict(STAGES_OK)}


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


# --- a rate limit is a run-level fault, not 25 question-level errors --------------

def test_rate_limited_response_is_a_run_level_fault():
    r = RE.score(Q_ANSWER, {"_error": "HTTP 429: exhausted your daily allowance",
                            "_status": 429}, 0.3)
    assert r.error and r.degraded is None
    assert r.api_status == 429, r.api_status
    reason = RE.run_level_fault(r)
    assert reason and "RATE_LIMIT" in reason, reason


def test_server_error_is_a_question_level_error_and_the_run_continues():
    """A 500 may be about this one question; only the per-day limiter poisons the rest."""
    r = RE.score(Q_ANSWER, {"_error": "HTTP 500: boom", "_status": 500}, 0.3)
    assert r.error and RE.run_level_fault(r) is None


def test_timeout_is_not_a_run_level_fault():
    r = RE.score(Q_ANSWER, {"_error": "ReadTimeout: x",
                            "_degraded": RE.DEGRADED_HARNESS_TIMEOUT}, 200.0)
    assert RE.run_level_fault(r) is None


def test_good_response_is_not_a_run_level_fault():
    assert RE.run_level_fault(RE.score(Q_ANSWER, GOOD, 1.0)) is None


def test_rate_limited_warmup_aborts_preflight():
    _, rc, _ = _preflight({"_error": "HTTP 429: exhausted", "_status": 429})
    assert rc == 2, rc


# --- a dead path aborts instead of manufacturing NO-DATA --------------------------

def test_dead_question_needs_every_run_unscoreable():
    good, bad = RE.score(Q_ANSWER, GOOD, 1.0), RE.score(Q_ANSWER, {"_error": "x"}, 1.0)
    assert RE.dead_question([bad, bad, bad]) is True
    assert RE.dead_question([bad, good, bad]) is False, "one scoreable run is data"
    assert RE.dead_question([]) is False


def test_degraded_only_question_counts_as_dead():
    deg = RE.score(Q_ANSWER, {"answer": TIMEOUT_FALLBACK_ANSWER}, 90.0)
    assert RE.dead_question([deg, deg, deg]) is True


def test_one_dead_question_is_tolerated_two_is_the_threshold():
    """A single all-timeout question can be a hard question, not a dead path."""
    assert RE.MAX_CONSECUTIVE_DEAD_QUESTIONS == 2, RE.MAX_CONSECUTIVE_DEAD_QUESTIONS


def test_the_counter_resets_on_a_scoreable_question():
    i_reset = SRC.index("consecutive_dead = 0", SRC.index("if dead_question(runs):"))
    i_else = SRC.index("else:", SRC.index("if dead_question(runs):"))
    assert i_else < i_reset, "a scoreable question must reset the run of dead ones"


# --- preflight aborts before scoring ----------------------------------------------

class _Stub:
    def __init__(self, resp):
        self.resp, self.calls = resp, 0

    def __call__(self, endpoint, question, auth, timeout):
        self.calls += 1
        return dict(self.resp)


def _preflight(resp, n_runs=3, allow_cache=False, warmup=True, require_pin=False,
                allow_unset_temp=False, allow_expansion_errors=False,
                allow_unpinned_provider=False):
    stub, orig = _Stub(resp), RE.call_endpoint
    RE.call_endpoint = stub
    try:
        info, rc = RE.preflight("http://x/api/search", None, 200.0, n_runs, allow_cache, warmup,
                                require_pin, allow_unset_temp, allow_expansion_errors,
                                allow_unpinned_provider)
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


def test_preflight_aborts_when_the_endpoint_cannot_say_what_served_it():
    # The hole this closes: the harness runs from one checkout while the SERVER was started from
    # another, so the code under test is not the code being committed. The dirty-tree gate reads
    # the harness's tree and cannot see the server's; the warmup response can.
    payload = dict(GOOD)
    payload.pop("answer_lm")
    _, rc, _ = _preflight(payload)
    assert rc == 3, rc


def test_preflight_aborts_when_the_warmup_pin_was_not_honored():
    bad = dict(LM_REC, provider_served="DeepInfra", pin_honored=False)
    _, rc, _ = _preflight(dict(GOOD, answer_lm=bad))
    assert rc == 3, rc


def test_preflight_REFUSES_when_the_pin_is_merely_UNCHECKABLE():
    """Reversed by the 2026-10-04 ruling; the old assertion is kept as the reason.

    This test used to assert rc == 0, on the grounds that an arm whose provider could not be
    read "is still a valid measurement of itself". That is true of a single arm and false of
    the comparison every arm in this lane is run for: the floor pair was served 61/17 and 39/39
    across two providers at different quantizations while reporting violations: []. UNCHECKED
    IS NOT HONORED. The escape is explicit and recorded, not the default.
    """
    unk = dict(LM_REC, provider_pin=None, provider_served=None,
               provider_served_source="unavailable:no-provider-on-dspy-response", pin_honored=None)
    _, rc, _ = _preflight(dict(GOOD, answer_lm=unk, openrouter_provider_pin=None), n_runs=1)
    assert rc == 3, rc


def test_preflight_aborts_when_warmup_itself_degrades():
    _, rc, _ = _preflight({"answer": TIMEOUT_FALLBACK_ANSWER})
    assert rc == 2, rc


def test_preflight_aborts_when_warmup_errors():
    _, rc, _ = _preflight({"_error": "ConnectError"})
    assert rc == 2, rc


def test_single_run_tolerates_unknown_cache_state():
    """N=1 makes no stability claim, so an unverifiable cache is not fatal there.

    The payload carries `answer_lm` because the subject here is the CACHE state, and a missing
    per-call record is a separate abort (ruling 2) with its own tests. Leaving it out would make
    this test pass or fail for a reason it is not about.
    """
    _, rc, _ = _preflight({"answer": "ok", "answer_lm": dict(LM_REC),
                           "stages": dict(STAGES_OK)}, n_runs=1)
    assert rc == 0, rc


def test_allow_lm_cache_does_not_abort():
    _, rc, _ = _preflight(dict(GOOD, lm_cache_enabled=True), allow_cache=True)
    assert rc == 0, rc


def test_no_warmup_refuses_and_sends_no_request():
    # --no-warmup observes neither expansion health nor the pin, so the preflight has nothing
    # to pass on. It still must not spend a request discovering that.
    info, rc, stub = _preflight(GOOD, warmup=False)
    assert rc == 3 and stub.calls == 0 and info["warmup_ran"] is False


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


def test_run_aborts_on_a_run_level_fault_instead_of_reporting():
    i_check = SRC.index("abort_reason = run_level_fault(r)")
    i_abort = SRC.index('print("ABORTED: " + abort_reason)')
    i_write = SRC.index("def write_outputs(") if "def write_outputs(" in SRC else len(SRC)
    assert i_check < i_abort, "the fault must be detected before the abort prints"
    assert "return 5" in SRC, "a run-level abort needs its own exit code"
    assert i_abort < SRC.index("Written:") if "Written:" in SRC else True


# --- reporting: runs are counted in runs, and the two detail lists stay apart ----

def _degraded_res(qid):
    """A run that timed out at the wall: the server answered, with the fallback."""
    r = _res(qid, 12.0)
    r.degraded = "llm_timeout"
    r.error = "llm_timeout"
    return r


def test_run_tally_counts_runs_not_questions():
    # One question, three runs, one of them degraded. The question still classifies, so the
    # question-scoped counters see nothing - this is the defect the tally exists to close.
    ledger = {"q": [_res("q", 10.0), _degraded_res("q"), _res("q", 11.0)]}
    t = RE.run_level_tally(ledger)
    assert t["total"] == 3, t
    assert t["scored"] == 2, t
    assert t["degraded"] == 1, t


def test_run_tally_keeps_degraded_and_errored_disjoint():
    hard = _res("q", 0.0, err="non-JSON response (status 500)")
    ledger = {"q": [_degraded_res("q"), hard]}
    t = RE.run_level_tally(ledger)
    assert t["degraded"] == 1, t
    assert t["errored"] == 1, t
    assert t["degraded"] + t["errored"] == 2, "a degraded run must not also be counted errored"


def test_run_tally_spans_every_question():
    ledger = {"a": [_res("a", 9.0), _res("a", 9.0)], "b": [_degraded_res("b"), _res("b", 9.0)]}
    t = RE.run_level_tally(ledger)
    assert t["total"] == 4 and t["scored"] == 3 and t["degraded"] == 1, t


def test_clean_ledger_tallies_zero_degraded():
    t = RE.run_level_tally({"q": [_res("q", 9.0), _res("q", 10.0), _res("q", 11.0)]})
    assert t["degraded"] == 0 and t["errored"] == 0 and t["scored"] == 3, t


def test_summary_prints_runs_as_well_as_questions():
    assert "summary[\"runs\"] = run_level_tally(run_ledger)" in SRC,         "the run tally must reach the summary dict, not just exist as a helper"
    assert "Runs                     :" in SRC, "the run tally must be printed"
    assert "Questions with no score  :" in SRC,         "the question-scoped line must say it is question-scoped"


def test_flaky_detail_has_its_own_heading_and_unit():
    i_partial = SRC.index("Partially scored (classified on fewer than N runs)")
    i_flaky = SRC.index("FLAKY detail (runs passed / runs scored)")
    assert i_partial < i_flaky, "the flaky list must be headed separately, after the partial list"
    assert "{ratio} passed" in SRC,         "a bare fraction under the partial heading reads as a runs-scoreable count"


# --- the provider pin must not change mid-arm (noise floor, 2026-09-27) -------------

def _pinned_res(qid, pin):
    """A scored run whose endpoint reported `pin` as its provider routing block."""
    payload = dict(GOOD, openrouter_provider_pin=pin)
    return RE.score(dict(Q_ANSWER, id=qid), payload, 1.0)


_SL = {"order": ["StreamLake"], "allow_fallbacks": False}
_DI = {"order": ["DeepInfra"], "allow_fallbacks": False}


def test_one_pin_throughout_is_not_a_violation():
    v = RE.check_run_integrity({"q": [_pinned_res("q", _SL), _pinned_res("q", _SL)]},
                               allow_lm_cache=False)
    assert not any("provider pin" in x for x in v), v


def test_pin_changing_mid_arm_is_an_integrity_violation():
    ledger = {"a": [_pinned_res("a", _SL), _pinned_res("a", _SL)],
              "b": [_pinned_res("b", _DI), _pinned_res("b", _SL)]}
    v = RE.check_run_integrity(ledger, allow_lm_cache=False)
    assert any("provider pin" in x for x in v), v


def test_unpinned_throughout_is_consistent_and_not_flagged_here():
    # Unpinned is a preflight warning, not an integrity violation: the arm did not SPLIT,
    # it was never pinned. Flagging it here would hide the case that matters.
    v = RE.check_run_integrity({"q": [_pinned_res("q", None), _pinned_res("q", None)]},
                               allow_lm_cache=False)
    assert not any("provider pin" in x for x in v), v


def test_pin_appearing_partway_through_is_a_violation():
    ledger = {"q": [_pinned_res("q", None), _pinned_res("q", _SL)]}
    v = RE.check_run_integrity(ledger, allow_lm_cache=False)
    assert any("provider pin" in x for x in v), v


def test_errored_runs_do_not_invent_a_pin_change():
    # An errored run has no endpoint report at all; counting its absent pin as a distinct
    # value would make every run with one timeout look like a split arm.
    ledger = {"q": [_pinned_res("q", _SL), _res("q", 0, err="ReadTimeout")]}
    v = RE.check_run_integrity(ledger, allow_lm_cache=False)
    assert not any("provider pin" in x for x in v), v


# --- the harness must record and be able to demand the pin ---------------------------

def test_preflight_records_the_pin_from_the_endpoint():
    assert 'info["openrouter_provider_pin"] = resp.get("openrouter_provider_pin")' in SRC, (
        "a pin the harness does not record is a pin no result can cite"
    )


def test_summary_carries_the_pin():
    assert '"openrouter_provider_pin": warmup_info.get("openrouter_provider_pin")' in SRC, (
        "summary.json is what a report is written from; the pin belongs in it"
    )


def test_require_provider_pin_exists_and_aborts():
    assert "--require-provider-pin" in SRC, "no way to demand a pin for a comparison arm"
    i_flag = SRC.index("if require_provider_pin:")
    tail = SRC[i_flag:i_flag + 400]
    assert "ABORT" in tail and "return info, 3" in tail, (
        "demanding a pin must stop the run before any question is scored"
    )


def test_fallback_constant_is_not_duplicated_here():
    assert "ink has dried" not in SRC, "harness must import the constant, not copy it"



# --- git state in the summary (added 2026-09-27, after the noise-floor pair) ----------------
# Deviation 1 of the noise-floor result: arm 1 ran over a dirty tree and arm 2 had three commits
# land mid-run, and the artifact recorded NONE of it, so the deviation had to be reconstructed from
# commit timestamps afterwards. These tests are about whether the recorder can SEE dirt, not
# whether it returns a dict: a detector that always answered "clean" would pass a clean-only test.

def test_git_state_reports_head_and_a_boolean_dirty():
    # Deliberately NOT "the tree is clean": this suite normally runs mid-change, and a test that
    # demands a clean tree would just be skipped-in-effect on every real development run. The shape
    # is what is asserted here; whether the detector can see dirt is the next test.
    st = RE.git_state()
    assert "head" in st, st
    assert len(st["head"]) == 40 and all(c in "0123456789abcdef" for c in st["head"]), st
    assert isinstance(st.get("dirty"), bool), st
    assert isinstance(st.get("dirty_paths"), int), st
    assert st["dirty"] == (st["dirty_paths"] > 0), ("dirty and dirty_paths disagree: %r" % (st,))


def test_git_state_can_actually_SEE_a_newly_dirty_path():
    # The companion assertion. Without it, a git_state() hard-coded to dirty=False would pass the
    # test above, and a run over a dirty tree would be recorded as clean. Works whether or not the
    # tree is already dirty, by measuring the DELTA the probe file makes.
    before = RE.git_state()
    probe = RE.REPO_ROOT / "_git_state_borntest_probe.tmp"
    assert not probe.exists(), "probe file left over from an earlier run"
    try:
        probe.write_text("this file exists only inside this test", encoding="utf-8")
        during = RE.git_state()
        assert during.get("dirty") is True, ("git_state cannot see an untracked file; a dirty tree "
                                            "would be recorded as clean. got %r" % (during,))
        assert during["dirty_paths"] == before["dirty_paths"] + 1, (before, during)
        assert any("_git_state_borntest_probe.tmp" in s for s in during.get("dirty_sample", [])),             during
    finally:
        if probe.exists():
            probe.unlink()
    after = RE.git_state()
    assert after["dirty_paths"] == before["dirty_paths"], ("probe not cleaned up", before, after)


def test_git_state_records_an_error_instead_of_swallowing_it():
    # A summary that cannot say what it ran must say so, not report a clean tree by default.
    orig = RE.REPO_ROOT
    try:
        RE.REPO_ROOT = Path(tempfile.mkdtemp())   # a real directory that is not a git repo
        st = RE.git_state()
        assert any(k.endswith("_error") for k in st), ("a non-repo must record an error, got %r"
                                                       % (st,))
        assert "dirty" not in st or st["dirty"] is not False or "porcelain_error" in st, st
    finally:
        RE.REPO_ROOT = orig


def test_changed_during_run_is_the_comparison_the_summary_makes():
    # The summary sets changed_during_run = (at_start != at_end). Assert the SEMANTICS here, so a
    # later refactor cannot turn it into a constant False.
    a = {"head": "a" * 40, "dirty": False, "dirty_paths": 0, "dirty_sample": []}
    b = {"head": "b" * 40, "dirty": False, "dirty_paths": 0, "dirty_sample": []}
    assert (a != b) is True, "differing HEADs must compare unequal"
    c = dict(a, dirty=True, dirty_paths=1, dirty_sample=["?? x"])
    assert (a != c) is True, "same HEAD but newly dirty must compare unequal"
    assert (a != dict(a)) is False, "an unchanged state must compare equal"


def test_git_run_block_flags_a_clean_unchanged_run_as_NOT_provisional():
    clean = {"head": "a" * 40, "dirty": False, "dirty_paths": 0, "dirty_sample": []}
    b = RE.git_run_block(clean, dict(clean))
    assert b["changed_during_run"] is False, b
    assert b["provisional"] is False, b


def test_git_run_block_flags_a_dirty_run_provisional():
    dirty = {"head": "a" * 40, "dirty": True, "dirty_paths": 2, "dirty_sample": [" M x", " M y"]}
    b = RE.git_run_block(dirty, dict(dirty))
    assert b["changed_during_run"] is False, "the tree never moved; only dirtiness is at issue"
    assert b["provisional"] is True, b


def test_git_run_block_catches_a_commit_landing_MID_RUN():
    # Exactly what happened to noise-floor arm 2 on 2026-09-27: it started dirty and ended clean,
    # three commits having landed while questions were being scored. Nothing recorded it.
    start = {"head": "a" * 40, "dirty": True, "dirty_paths": 10, "dirty_sample": [" M z"]}
    end = {"head": "b" * 40, "dirty": False, "dirty_paths": 0, "dirty_sample": []}
    b = RE.git_run_block(start, end)
    assert b["changed_during_run"] is True, b
    assert b["provisional"] is True, b


def test_git_run_block_is_provisional_when_git_could_not_be_read():
    err = {"head_error": "not a git repository", "porcelain_error": "not a git repository"}
    b = RE.git_run_block(err, dict(err))
    assert b["provisional"] is True, ("a run that cannot say what it ran is provisional, got %r"
                                      % (b,))


def test_run_eval_records_git_in_the_integrity_block():
    src = (Path(RE.__file__)).read_text(encoding="utf-8")
    assert 'summary["integrity"]["git"]' in src, "git state must land in the integrity block"
    assert "changed_during_run" in src, src[:0]
    assert src.index("git_at_start = git_state()") < src.index("preflight(args.endpoint"), "git state must be captured BEFORE preflight spends a request"


def test_dirty_tree_refusal_lets_a_clean_tree_proceed():
    assert RE.dirty_tree_refusal({"head": "a" * 40, "dirty": False, "dirty_paths": 0}, False) is None


def test_dirty_tree_refusal_ABORTS_a_dirty_tree_by_default():
    # The gate ruling 1 asked for. Recording dirtiness was already implemented on 2026-09-27 and
    # both noise-floor arms still ran dirty, so the START half is now a refusal, not a note.
    msg = RE.dirty_tree_refusal(
        {"head": "a" * 40, "dirty": True, "dirty_paths": 2,
         "dirty_sample": [" M evals/run_eval.py", "?? scratch.txt"]}, False)
    assert msg and "REFUSING to start" in msg, msg
    assert "evals/run_eval.py" in msg, "the refusal must name what is dirty, not just the count"
    assert "--allow-dirty-tree" in msg, msg


def test_dirty_tree_refusal_allows_an_explicitly_provisional_run():
    msg = RE.dirty_tree_refusal({"head": "a" * 40, "dirty": True, "dirty_paths": 1,
                                 "dirty_sample": [" M x.py"]}, True)
    assert msg is None, "an explicit --allow-dirty-tree must proceed, labelled provisional"


def test_run_eval_actually_calls_the_refusal_before_scoring_anything():
    # Source-order check: the gate is worthless if it runs after the first question. Paired with
    # the unit tests above, which prove the gate itself can fire.
    src = open(RE.__file__, encoding="utf-8").read()
    assert "refusal = dirty_tree_refusal(git_at_start, args.allow_dirty_tree)" in src
    assert src.index("dirty_tree_refusal(git_at_start") < src.index("preflight(args.endpoint")


# --- ruling 2: the arm must be able to say what served it ---------------------------

def _lm_res(qid, rec, gen=12.0, err=None, degraded=None):
    """A scored run whose endpoint reported `rec` as its per-call answer_lm record."""
    if err:
        return RE.score(dict(Q_ANSWER, id=qid), {"_error": err}, 1.0)
    payload = dict(GOOD, generation_seconds=gen)
    if degraded:
        payload["degraded"] = degraded
    if rec is None:
        payload.pop("answer_lm", None)
    else:
        payload["answer_lm"] = rec
    return RE.score(dict(Q_ANSWER, id=qid), payload, 1.0)


def test_answer_lm_tally_collapses_identical_configurations_to_one_row():
    t = RE.answer_lm_tally({"q1": [_lm_res("q1", dict(LM_REC)), _lm_res("q1", dict(LM_REC))],
                            "q2": [_lm_res("q2", dict(LM_REC))]})
    assert t["scored_runs_with_a_record"] == 3, t
    assert len(t["distinct"]) == 1, t["distinct"]
    assert t["distinct"][0]["runs"] == 3, t["distinct"]
    assert t["distinct"][0]["provider_served"] == "StreamLake", t["distinct"]
    assert t["questions_missing_a_record"] == [], t
    assert t["runs_pin_honored_false"] == 0 and t["runs_pin_unchecked"] == 0, t


def test_answer_lm_tally_can_actually_SEE_two_configurations():
    # The companion assertion: a tally that always collapsed to one row would pass the test
    # above and report a mixed arm as a sample.
    hot = dict(LM_REC, temperature_on_the_wire="<absent from optional_params>")
    t = RE.answer_lm_tally({"q1": [_lm_res("q1", dict(LM_REC)), _lm_res("q1", hot)]})
    assert len(t["distinct"]) == 2, t["distinct"]
    # str() because the two values are a float and a sentinel string -- which is the point:
    # "0.0" and "never sent" are different facts and must not collapse.
    assert {str(d["temperature_on_the_wire"]) for d in t["distinct"]} == {
        "0.0", "<absent from optional_params>"}, t["distinct"]


def test_a_violated_pin_is_an_integrity_violation():
    bad = dict(LM_REC, provider_served="DeepInfra", pin_honored=False)
    v = RE.check_run_integrity({"q": [_lm_res("q", dict(LM_REC)), _lm_res("q", bad)]},
                               allow_lm_cache=False)
    hits = [x for x in v if "OUTSIDE" in x]
    assert len(hits) == 1, v
    assert "DeepInfra" in hits[0], hits
    assert "1 scored run" in hits[0], hits


def test_an_unchecked_pin_is_counted_but_is_NOT_a_violation():
    # pin_honored None means unpinned, or a provider we could not read. Treating it as a
    # violation would abort every unpinned arm ever run; treating it as honored would hide a
    # provider switch. It is counted, separately, and reported.
    unk = dict(LM_REC, provider_served=None,
               provider_served_source="unavailable:no-provider-on-dspy-response", pin_honored=None)
    ledger = {"q": [_lm_res("q", unk), _lm_res("q", unk)]}
    t = RE.answer_lm_tally(ledger)
    assert t["runs_pin_unchecked"] == 2, t
    assert t["runs_pin_honored_false"] == 0, t
    v = RE.check_run_integrity(ledger, allow_lm_cache=False)
    assert not any("OUTSIDE" in x for x in v), v


def test_a_missing_record_on_a_scored_run_is_an_integrity_violation():
    v = RE.check_run_integrity({"q": [_lm_res("q", None)]}, allow_lm_cache=False)
    hits = [x for x in v if "no per-call answer_lm record" in x]
    assert len(hits) == 1, v
    assert "q" in hits[0], hits


def test_a_good_arm_still_has_no_violations_at_all():
    # The other half of the test above: the new checks must not fire on a clean arm, or every
    # run aborts and the gate is worthless.
    v = RE.check_run_integrity({"q": [_lm_res("q", dict(LM_REC)), _lm_res("q", dict(LM_REC))]},
                               allow_lm_cache=False)
    assert v == [], v


def test_errored_and_degraded_runs_do_not_count_as_missing_records():
    # An errored or degraded run was never asked the question, so it has nothing to record.
    # Counting it as a gap made five HTTP 500s read as a mis-configured endpoint.
    ledger = {"q1": [_lm_res("q1", None, err="ReadTimeout")],
              "q2": [_lm_res("q2", None, degraded="llm_timeout")]}
    t = RE.answer_lm_tally(ledger)
    assert t["questions_missing_a_record"] == [], t
    assert t["scored_runs_with_a_record"] == 0, t
    assert not any("answer_lm record" in x for x in RE.check_run_integrity(ledger, False)), ledger


def test_score_carries_the_record_off_the_response():
    r = RE.score(Q_ANSWER, dict(GOOD), 1.0)
    assert r.answer_lm == LM_REC, r.answer_lm
    assert RE.score(Q_ANSWER, {"answer": "x [GENESIS_2_8_S01]."}, 1.0).answer_lm is None


# --- ruling 4: an upstream rate limit is a RUN-level fault even at HTTP 200 -----------

# What the backend now sends when litellm raises a rate limit inside generation. The status
# line is 200 -- the request succeeded, the generation did not -- so the HTTP gate cannot see
# it and the label is the only evidence there is.
RATE_LIMITED_200 = {
    "answer": GENERATION_FAILURE_ANSWER,
    "degraded": DEGRADED_UPSTREAM_RATE_LIMIT,
    "degraded_detail": ("RateLimitError: litellm.RateLimitError: RateLimitError: "
                        "OpenAIException - Provider returned error"),
    "generation_seconds": 1.2, "lm_cache_enabled": False, "answer_lm": dict(LM_REC),
}


def test_an_upstream_rate_limit_at_http_200_is_a_run_level_fault():
    r = RE.score(Q_ANSWER, dict(RATE_LIMITED_200), 1.2)
    assert r.api_status == 200, r.api_status
    assert r.degraded == DEGRADED_UPSTREAM_RATE_LIMIT, r.degraded
    assert r.error, "a degradation is an error, never a fail"
    reason = RE.run_level_fault(r)
    assert reason and DEGRADED_UPSTREAM_RATE_LIMIT in reason, reason
    assert "UPSTREAM" in reason, "the abort must say whose limit it was; ours is a different fix"


def test_the_nf2_prose_is_kept_out_of_the_denominator_but_CANNOT_abort():
    # The honest limit of the compatibility floor, stated as a test. Against a backend that
    # predates the typed field -- which is every already-published run -- the prose is still
    # recognised as a non-answer and still excluded from scoring, but the label is
    # "detected by text" and nothing can tell a rate limit from any other raised error. So the
    # run continues. Only the typed field can abort, which is why the fix had to be in the
    # backend and not in a smarter matcher here.
    legacy = {"answer": ("Error generating answer: litellm.RateLimitError: RateLimitError: "
                         "OpenAIException - Provider returned error"),
              "lm_cache_enabled": False, "answer_lm": dict(LM_REC)}
    r = RE.score(Q_ANSWER, legacy, 1.2)
    assert r.degraded == RE.DEGRADED_UNLABELLED, r.degraded
    assert r.error and not r.overall_pass
    assert RE.run_level_fault(r) is None, (
        "text detection must NOT be allowed to abort a run: it cannot distinguish a provider "
        "outage from our own assertion firing, and an invented abort kills a healthy arm"
    )


def test_a_backend_timeout_label_is_not_a_run_level_fault():
    # Companion assertion: the gate is narrow on purpose. One question can time out three
    # times running without the endpoint being dead -- MAX_CONSECUTIVE_DEAD_QUESTIONS catches
    # that pattern instead, over evidence rather than over one label.
    r = RE.score(Q_ANSWER, {"answer": TIMEOUT_FALLBACK_ANSWER, "degraded": DEGRADED_LLM_TIMEOUT,
                            "lm_cache_enabled": False, "answer_lm": dict(LM_REC)}, 180.0)
    assert r.degraded == DEGRADED_LLM_TIMEOUT
    assert RE.run_level_fault(r) is None


def test_our_own_assertion_label_is_not_a_run_level_fault():
    # A bad week for the model is not an outage. If this aborted, a prompt regression would
    # look like infrastructure and the arm would never be measured.
    r = RE.score(Q_ANSWER, {"answer": GENERATION_FAILURE_ANSWER, "degraded": DEGRADED_ASSERTION,
                            "lm_cache_enabled": False, "answer_lm": dict(LM_REC)}, 3.0)
    assert r.degraded == DEGRADED_ASSERTION
    assert RE.run_level_fault(r) is None


# --- ruling 4: an aborted directory says so, and keeps what it measured ---------------

class _SeqStub:
    """call_endpoint that returns responses[i] for call i, then repeats the last one."""

    def __init__(self, responses):
        self.responses, self.calls = responses, 0

    def __call__(self, endpoint, question, auth, timeout):
        i = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return dict(self.responses[i])


def _corpus(content="a" * 64, vector="b" * 64, chunks=7294):
    """A corpus_state record as corpus_state() returns one. Built here rather than imported so a
    change to that shape shows up as a failure in this suite too."""
    return {"available": True, "unavailable_reason": None, "weaviate_url": "10.0.0.1:80",
            "include_vectors": True, "counts": {"CommentaryChunk": chunks}, "chunk_count": chunks,
            "content_sha256": content, "vector_sha256": vector, "n_hashed": chunks,
            "n_vectors_hashed": chunks, "seconds": 1.0}


def _run_main(responses, ids, corpus=None, fingerprint="skip"):
    """Drive RE.main offline.

    `fingerprint` defaults to "skip" because the default ("vectors") reads the live Weaviate
    instance twice at 80s a sample: with it, this suite hung past 120s and would fail outright
    anywhere without a corpus. `corpus` is a list of corpus_state records handed out in order,
    which is how a corpus that MOVES mid-run is testable without moving a real one.
    """
    out = Path(tempfile.mkdtemp()) / "run"
    stub, orig = _SeqStub(responses), RE.call_endpoint
    RE.call_endpoint = stub
    orig_cs = RE.corpus_state
    if corpus is not None:
        seq = list(corpus)

        def _cs(*a, **kw):
            return seq.pop(0) if len(seq) > 1 else seq[0]

        RE.corpus_state = _cs
    else:
        def _refuse(*a, **kw):
            raise AssertionError("the offline suite must not read the live corpus")

        RE.corpus_state = _refuse
    try:
        rc = RE.main(["--endpoint", "http://x/api/search", "--output-dir", str(out),
                      "--ids"] + ids + ["--runs", "1", "--no-warmup", "--allow-dirty-tree",
                                        "--allow-expansion-errors",
                                        "--allow-unpinned-provider",
                                        "--corpus-fingerprint", fingerprint])
    finally:
        RE.call_endpoint = orig
        RE.corpus_state = orig_cs
    return rc, out, stub


def _summary(out):
    return json.loads((out / "summary.json").read_text(encoding="utf-8"))


def test_the_parser_can_actually_render_its_own_help():
    # A bare "%" in an argparse help string raises at FORMAT time, not at definition time, so the
    # parser builds fine and every test that only parses args passes. It breaks --help AND the
    # usage message argparse prints on any bad flag, which is exactly when a user needs it. Cost
    # me one: "58% of the time" in the --runs help crashed with
    # "TypeError: %o format: an integer is required, not dict".
    p = RE.build_parser() if hasattr(RE, "build_parser") else None
    if p is None:
        # The parser is built inside main(); drive the real path instead.
        import subprocess
        r = subprocess.run([sys.executable, str(Path(RE.__file__)), "--help"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert r.returncode == 0, r.stderr[-800:]
        assert "--runs" in r.stdout and "--corpus-fingerprint" in r.stdout, r.stdout[:400]
        return
    assert "--runs" in p.format_help()


def test_skipping_the_fingerprint_performs_NO_corpus_read_and_is_provisional():
    # The stub in _run_main raises if corpus_state is called at all, so this asserts the cost as
    # well as the label: `skip` must not touch the network.
    rc, out, stub = _run_main([dict(GOOD)], ["logos_001", "sheep_001"])
    c = _summary(out)["integrity"]["corpus"]
    assert c["skipped"] is True, c
    assert c["provisional"] is True, "an unstamped run cannot be cited"
    assert c["violations"] == [], "but skipping is not a violation"
    assert c["changed_during_run"] is None, c["changed_during_run"]


def test_a_corpus_that_holds_still_is_recorded_clean():
    # The companion assertion for the violation test below: an implementation that reported every
    # run as a moved corpus would pass that test and fail every real run.
    same = _corpus()
    rc, out, stub = _run_main([dict(GOOD)], ["logos_001", "sheep_001"],
                              corpus=[same, dict(same)], fingerprint="text")
    c = _summary(out)["integrity"]["corpus"]
    assert c["changed_during_run"] is False, c
    assert c["provisional"] is False, c
    assert c["at_start"]["content_sha256"] == "a" * 64, "the sample itself is recorded, not a flag"
    assert not any("CORPUS CHANGED" in v for v in _summary(out)["integrity"]["violations"])


def test_a_corpus_that_MOVES_mid_run_is_a_violation_and_a_nonzero_exit():
    rc, out, stub = _run_main([dict(GOOD)], ["logos_001", "sheep_001"],
                              corpus=[_corpus(), _corpus(content="f" * 64)], fingerprint="text")
    s_ = _summary(out)
    c = s_["integrity"]["corpus"]
    assert c["changed_during_run"] is True, c
    assert any("CORPUS CHANGED MID-RUN" in v for v in c["violations"]), c["violations"]
    # and it must reach the run-level violation list, which is what decides the exit code
    assert any("CORPUS CHANGED MID-RUN" in v for v in s_["integrity"]["violations"]), s_["integrity"]
    assert rc != 0, "a run scored against a moving corpus must not exit 0"


def test_a_revectorisation_mid_run_is_caught_by_the_wiring_too():
    # Identical text, different embeddings. The end-to-end version of the case a text-only
    # fingerprint cannot see.
    rc, out, stub = _run_main([dict(GOOD)], ["logos_001", "sheep_001"],
                              corpus=[_corpus(), _corpus(vector="f" * 64)], fingerprint="text")
    c = _summary(out)["integrity"]["corpus"]
    assert c["at_start"]["content_sha256"] == c["at_end"]["content_sha256"], "the premise"
    assert c["changed_during_run"] is True, c
    assert rc != 0


def test_an_unreadable_corpus_is_provisional_but_does_NOT_fail_the_run():
    unread = {"available": False, "unavailable_reason": "unavailable:read-failed:ConnectionError",
              "weaviate_url": "10.0.0.1:80", "include_vectors": False, "counts": None,
              "chunk_count": None, "content_sha256": None, "vector_sha256": None,
              "n_hashed": None, "n_vectors_hashed": None, "seconds": None}
    rc, out, stub = _run_main([dict(GOOD)], ["logos_001", "sheep_001"],
                              corpus=[unread, dict(unread)], fingerprint="text")
    s_ = _summary(out)
    c = s_["integrity"]["corpus"]
    assert c["changed_during_run"] is None, "unknowable, not unchanged"
    assert c["provisional"] is True
    assert c["violations"] == []
    assert not any("CORPUS" in v for v in s_["integrity"]["violations"]), s_["integrity"]["violations"]


def test_the_report_renders_the_corpus_row_in_both_directions():
    clean = {"integrity": {"violations": [],
                           "git": {"at_start": {"head": "0123456789abcdef", "dirty": False},
                                   "at_end": {"head": "0123456789abcdef", "dirty": False},
                                   "changed_during_run": False, "provisional": False},
                           "corpus": RE.corpus_run_block(_corpus(), _corpus())}}
    txt = "".join(RE.integrity_report_lines(clean))
    assert "## Run integrity" in txt
    assert "Clean on both axes" in txt, txt
    assert "7294 chunks" in txt and "aaaaaaaaaaaa" in txt, txt
    assert "PROVISIONAL" not in txt, txt

    moved = {"integrity": {"violations": ["CORPUS CHANGED MID-RUN: ..."],
                           "git": clean["integrity"]["git"],
                           "corpus": RE.corpus_run_block(_corpus(), _corpus(content="f" * 64))}}
    txt2 = "".join(RE.integrity_report_lines(moved))
    assert "THIS RUN IS PROVISIONAL" in txt2, txt2
    assert "VIOLATION" in txt2 and "CORPUS CHANGED MID-RUN" in txt2, txt2
    assert "Clean on both axes" not in txt2


def test_the_report_says_unknown_rather_than_False_for_an_unread_corpus():
    unread = {"available": False, "unavailable_reason": "unavailable:read-failed:ConnectionError"}
    summary = {"integrity": {"violations": [],
                             "git": {"at_start": {}, "at_end": {}, "changed_during_run": False,
                                     "provisional": False},
                             "corpus": RE.corpus_run_block(unread, dict(unread))}}
    txt = "".join(RE.integrity_report_lines(summary))
    assert "unknown (not established at both ends)" in txt, txt
    assert "unread: unavailable:read-failed:ConnectionError" in txt, txt
    assert "THIS RUN IS PROVISIONAL" in txt




def test_abort_writes_a_marker_and_KEEPS_the_question_files_it_already_had():
    good = dict(GOOD)
    rc, out, stub = _run_main([good, RATE_LIMITED_200], ["logos_001", "sheep_001"])
    assert rc == 5, rc
    marker_path = out / "ABORTED.json"
    assert marker_path.is_file(), sorted(p.name for p in out.iterdir())
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    assert marker["aborted"] is True
    assert DEGRADED_UPSTREAM_RATE_LIMIT in marker["reason"], marker["reason"]
    assert marker["at"]["question_id"] == "sheep_001", marker["at"]
    assert marker["last_run"]["degraded"] == DEGRADED_UPSTREAM_RATE_LIMIT, marker["last_run"]
    # The measurement that WAS taken is still on disk, and the marker names it. Deleting it
    # would be a silent drop; leaving it unnamed is how a fragment directory gets mistaken
    # for a run (the fault the floor report filed against this same abort path).
    assert marker["question_files_present"] == ["logos_001"], marker["question_files_present"]
    assert (out / "logos_001.json").is_file()
    assert not (out / "summary.json").exists(), "an aborted attempt must write no summary"
    assert not (out / "report.md").exists(), "and no report"


def test_a_COMPLETED_run_writes_no_marker_and_does_write_a_summary():
    # The companion assertion. A marker written unconditionally would pass every assertion
    # above while telling a reader nothing, and would make every healthy run look aborted.
    rc, out, stub = _run_main([dict(GOOD)], ["logos_001", "sheep_001"])
    assert not (out / "ABORTED.json").exists(), "a completed run must not be marked aborted"
    assert (out / "summary.json").is_file(), sorted(p.name for p in out.iterdir())
    assert stub.calls == 2, stub.calls


# --- per-run answer digest (text drift is unmeasurable without it) ---------------

def test_per_question_runs_entry_carries_answer_digest_fields():
    rc, out, stub = _run_main([dict(GOOD)], ["logos_001"])
    rec = json.loads((out / "logos_001.json").read_text(encoding="utf-8"))
    run0 = rec["runs"][0]
    assert "answer_sha16" in run0 and "answer_chars" in run0 and "temperature_on_the_wire" in run0, run0
    assert run0["answer_chars"] == len(GOOD["answer"]), run0
    assert run0["temperature_on_the_wire"] == 0.0, run0
    assert run0["answer_sha16"] == hashlib.sha256(GOOD["answer"].encode("utf-8")).hexdigest()[:16], run0


def test_identical_answer_text_yields_identical_sha_different_text_yields_different_sha():
    same_a = dict(GOOD)
    same_b = dict(GOOD)
    different = dict(GOOD, answer="A wholly different sentence about Zion [GENESIS_2_8_S01].")
    rc, out, stub = _run_main([same_a, same_b, different],
                              ["logos_001", "sheep_001", "peter_001"])
    r1 = json.loads((out / "logos_001.json").read_text(encoding="utf-8"))["runs"][0]
    r2 = json.loads((out / "sheep_001.json").read_text(encoding="utf-8"))["runs"][0]
    r3 = json.loads((out / "peter_001.json").read_text(encoding="utf-8"))["runs"][0]
    assert r1["answer_sha16"] == r2["answer_sha16"], (r1, r2)
    assert r1["answer_sha16"] != r3["answer_sha16"], (r1, r3)


def test_answer_sha16_is_None_not_a_hash_of_the_empty_string_when_no_answer():
    empty = dict(GOOD, answer="")
    rc, out, stub = _run_main([empty], ["logos_001"])
    rec = json.loads((out / "logos_001.json").read_text(encoding="utf-8"))
    assert rec["runs"][0]["answer_sha16"] is None, rec["runs"][0]
    assert rec["runs"][0]["answer_chars"] == 0, rec["runs"][0]


# --- temperature recorded in integrity, and an unset temperature REFUSES ----------

def test_answer_temperature_block_counts_explicit_absent_and_unrecorded():
    explicit = _lm_res("q1", dict(LM_REC))
    absent = _lm_res("q1", dict(LM_REC, temperature_on_the_wire="<absent from optional_params>"))
    unrecorded = _lm_res("q1", None)
    t = RE.answer_temperature_block({"q1": [explicit, absent, unrecorded]})
    assert t["runs_explicit"] == 1, t
    assert t["runs_absent"] == 1, t
    assert t["runs_unrecorded"] == 1, t
    assert 0.0 in t["distinct"], t["distinct"]
    assert "<absent from optional_params>" in t["distinct"], t["distinct"]


def test_ZERO_on_the_wire_counts_as_EXPLICIT_not_absent():
    # The load-bearing case: 0 is falsy, and this is the exact value the new rule requires.
    # A truthiness check (`if temp:`) would silently sort it into "absent".
    zero = _lm_res("q", dict(LM_REC, temperature_on_the_wire=0.0))
    t = RE.answer_temperature_block({"q": [zero]})
    assert t["runs_explicit"] == 1, t
    assert t["runs_absent"] == 0, t
    assert t["runs_unrecorded"] == 0, t


def test_degraded_and_errored_runs_are_excluded_from_the_temperature_denominator():
    ok = _lm_res("q", dict(LM_REC))
    bad_err = _lm_res("q", None, err="ReadTimeout")
    bad_deg = _lm_res("q", None, degraded="llm_timeout")
    t = RE.answer_temperature_block({"q": [ok, bad_err, bad_deg]})
    assert t["runs_explicit"] == 1, t
    assert t["runs_absent"] == 0 and t["runs_unrecorded"] == 0, t


def test_check_run_integrity_flags_unset_temperature_by_default_and_the_flag_suppresses_it():
    absent = dict(LM_REC, temperature_on_the_wire="<absent from optional_params>")
    ledger = {"q": [_lm_res("q", absent)]}
    v_default = RE.check_run_integrity(ledger, allow_lm_cache=False)
    assert any("temperature" in x.lower() for x in v_default), v_default
    v_allowed = RE.check_run_integrity(ledger, allow_lm_cache=False, allow_unset_temperature=True)
    assert not any("temperature" in x.lower() for x in v_allowed), v_allowed


def test_preflight_refuses_when_warmup_temperature_is_absent_and_flag_not_passed():
    absent = dict(LM_REC, temperature_on_the_wire="<absent from optional_params>")
    _, rc, _ = _preflight(dict(GOOD, answer_lm=absent))
    assert rc == 3, rc


def test_preflight_does_NOT_refuse_when_warmup_temperature_is_ZERO():
    # Companion assertion: a refusal that always fires certifies nothing.
    zero = dict(LM_REC, temperature_on_the_wire=0.0)
    _, rc, _ = _preflight(dict(GOOD, answer_lm=zero))
    assert rc == 0, rc


def test_preflight_allows_unset_temperature_and_warns_when_the_flag_is_passed():
    absent = dict(LM_REC, temperature_on_the_wire="<absent from optional_params>")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _, rc, _ = _preflight(dict(GOOD, answer_lm=absent), allow_unset_temp=True)
    assert rc == 0, rc
    out = buf.getvalue()
    assert "WARNING" in out and "temperature" in out.lower(), out


def test_help_still_renders_and_shows_the_new_temperature_flag():
    import subprocess
    r = subprocess.run([sys.executable, str(Path(RE.__file__)), "--help"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr[-800:]
    assert "--allow-unset-temperature" in r.stdout, r.stdout[:400]


# --- stage health: BAML query expansion / entity lookup / verifier, rolled up per run ----

def _stage_res(qid, stages, gen=12.0, err=None, degraded=None):
    """A scored run whose endpoint reported `stages` as its debug stage-capture block."""
    if err:
        return RE.score(dict(Q_ANSWER, id=qid), {"_error": err}, 1.0)
    payload = dict(GOOD, generation_seconds=gen)
    if degraded:
        payload["degraded"] = degraded
    if stages is not None:
        payload["stages"] = stages
    return RE.score(dict(Q_ANSWER, id=qid), payload, 1.0)


def test_healthy_stage_ledger_has_no_expansion_errors_or_violations():
    ok = _stage_res("q", {"entity_lookup_mode": "full"})
    h = RE.stage_health_block({"q": [ok]})
    assert h["expansion"]["errored"] == 0, h
    v = RE.check_run_integrity({"q": [ok]}, allow_lm_cache=False)
    assert not any("expansion" in x.lower() for x in v), v


def test_one_erroring_scored_run_is_counted_and_flagged():
    bad = _stage_res("q", {"baml_error": "missing LITELLM_PROXY_URL", "baml_fallback": "some_fallback"})
    h = RE.stage_health_block({"q": [bad]})
    assert h["expansion"]["errored"] == 1, h
    v = RE.check_run_integrity({"q": [bad]}, allow_lm_cache=False)
    assert any("expansion" in x.lower() for x in v), v


def test_degraded_or_errored_stage_runs_are_excluded_from_stage_health():
    bad_deg = _stage_res("q", {"baml_error": "x"}, degraded="llm_timeout")
    h_deg = RE.stage_health_block({"q": [bad_deg]})
    assert h_deg["scored_runs"] == 0, h_deg
    assert h_deg["expansion"]["errored"] == 0, h_deg

    bad_err = _stage_res("q", None, err="ReadTimeout")
    h_err = RE.stage_health_block({"q": [bad_err]})
    assert h_err["scored_runs"] == 0, h_err
    assert h_err["expansion"]["errored"] == 0, h_err


def test_missing_stages_key_does_not_raise_and_counts_as_not_errored():
    no_stages = _stage_res("q", None)
    h = RE.stage_health_block({"q": [no_stages]})
    assert h["scored_runs"] == 1, h
    assert h["expansion"]["errored"] == 0, h


def test_distinct_fallback_renders_none_as_placeholder_and_sorts():
    with_fallback = _stage_res("q", {"baml_error": "x", "baml_fallback": "keyword_only"})
    no_fallback_key = _stage_res("q", {"baml_fallback": None})
    h = RE.stage_health_block({"q": [with_fallback, no_fallback_key]})
    assert h["expansion"]["distinct_fallback"] == ["<none>", "keyword_only"], h["expansion"]


def test_entity_lookup_counts_tally_distinct_modes_across_runs():
    full = _stage_res("q", {"entity_lookup_mode": "full"})
    degraded_mode = _stage_res("q", {"entity_lookup_mode": "degraded_no_vector"})
    h = RE.stage_health_block({"q": [full, degraded_mode]})
    assert h["entity_lookup"]["counts"] == {"full": 1, "degraded_no_vector": 1}, h["entity_lookup"]
    assert set(h["entity_lookup"]["distinct_mode"]) == {"full", "degraded_no_vector"}, h["entity_lookup"]


# --- item 3: an UNPINNED arm served by two providers is a mixture ---------------------
# Measured, not hypothetical: floor_20260928 armA was served DeepInfra 61 / StreamLake 17 and
# armB DeepInfra 39 / StreamLake 39, and both arms reported violations: []. An unpinned arm has
# ONE pin value (None) and pin_honored None on every run, so both pre-existing pin gates are
# structurally blind to it -- the same defect as a gate that cannot see its own failure.

_UNPINNED_SL = dict(LM_REC, provider_pin=None, provider_served="StreamLake", pin_honored=None)
_UNPINNED_DI = dict(LM_REC, provider_pin=None, provider_served="DeepInfra", pin_honored=None)


def _mixed_violations():
    return RE.check_run_integrity(
        {"q1": [_lm_res("q1", dict(_UNPINNED_DI)), _lm_res("q1", dict(_UNPINNED_DI)),
                _lm_res("q1", dict(_UNPINNED_SL))],
         "q2": [_lm_res("q2", dict(_UNPINNED_DI))]},
        allow_lm_cache=False)


def test_unpinned_arm_served_by_two_providers_is_a_violation():
    v = [x for x in _mixed_violations() if "different providers" in x]
    assert len(v) == 1, _mixed_violations()
    assert "2 different providers" in v[0], v[0]


def test_the_mixture_violation_names_both_providers_and_their_run_counts():
    v = [x for x in _mixed_violations() if "different providers" in x][0]
    assert "DeepInfra=3" in v, v
    assert "StreamLake=1" in v, v
    # it has to say what to do about it, or it is a label rather than a gate
    assert "OPENROUTER_PROVIDER_ORDER" in v, v


def test_the_mixture_gate_does_not_fire_on_the_pre_existing_pin_gates():
    # The point of the new gate is that the old ones CANNOT see this arm. If either of them
    # fires here, the new gate is redundant and this whole addition is unjustified.
    all_v = _mixed_violations()
    assert not any("provider pin changed" in x for x in all_v), all_v
    assert not any("OUTSIDE" in x for x in all_v), all_v


def test_one_served_provider_throughout_is_not_a_mixture():
    v = RE.check_run_integrity(
        {"q1": [_lm_res("q1", dict(_UNPINNED_SL)), _lm_res("q1", dict(_UNPINNED_SL))]},
        allow_lm_cache=False)
    assert not any("different providers" in x for x in v), v


def test_no_provider_reported_anywhere_manufactures_no_mixture():
    # An endpoint that cannot read the serving provider reports None. Counting None as a
    # provider would turn "unknown" into a second provider and fabricate a violation --
    # the inverse of folding silence into health.
    blind = dict(LM_REC, provider_pin=None, provider_served=None,
                 provider_served_source=None, pin_honored=None)
    ledger = {"q1": [_lm_res("q1", dict(blind)), _lm_res("q1", dict(blind))]}
    v = RE.check_run_integrity(ledger, allow_lm_cache=False)
    assert not any("different providers" in x for x in v), v
    t = RE.answer_lm_tally(ledger)
    assert t["runs_by_provider_served"] == {}, t["runs_by_provider_served"]
    assert t["distinct_provider_served"] == [], t["distinct_provider_served"]


def test_answer_lm_tally_counts_scored_runs_per_served_provider():
    t = RE.answer_lm_tally(
        {"q1": [_lm_res("q1", dict(_UNPINNED_DI)), _lm_res("q1", dict(_UNPINNED_SL)),
                _lm_res("q1", dict(_UNPINNED_SL))],
         "q2": [_lm_res("q2", dict(_UNPINNED_SL), err="boom")]})
    # the errored run is not a gap in the evidence and is not counted
    assert t["runs_by_provider_served"] == {"DeepInfra": 1, "StreamLake": 2}, t
    assert t["distinct_provider_served"] == ["DeepInfra", "StreamLake"], t


def test_per_question_runs_entry_carries_the_provider_fields():
    # Attribution, not just detection: floor_20260928 recorded no per-run provider, so a
    # blocky pass/fail pattern (armA scapegoat_001 was T,T,T,F,F,F) could not be tested
    # against which provider served which run. These three fields are what makes it testable.
    rc, out, stub = _run_main([dict(GOOD)], ["logos_001"])
    rec = json.loads((out / "logos_001.json").read_text(encoding="utf-8"))
    r0 = rec["runs"][0]
    assert r0["provider_served"] == "StreamLake", r0
    assert r0["provider_pin"] == {"order": ["streamlake"], "allow_fallbacks": False}, r0
    assert r0["pin_honored"] is True, r0


# --- the scored-run preflight: three conditions, enforced at launch ----------------------
#
# Ruling (2026-10-04, Chris): expansion healthy, pin honored, header written, enforced as a
# LAUNCHER REFUSAL and born-tested -- not a rule in a prediction document.
#
# The defect these cover: PREDICTION_off_vs_on_expansion_live_laneA_20261004.md said "if the
# warmup shows an expansion error, no scored question is sent". Nothing enforced it. The arm's
# warmup punted, the harness printed a WARNING, and all 13 questions were scored. Every test
# below fails against the parent commit, except the ones marked as negative controls -- a
# refusal that always fires certifies nothing.


def _refusals(**kw):
    """scored_run_refusals over a warmup_info built from the GOOD/LM_REC fixtures."""
    info = {"warmup_ran": True, "answer_lm": dict(LM_REC),
            "warmup_expansion": dict(STAGES_OK, observed=True)}
    info.update(kw)
    return RE.scored_run_refusals(info)


def test_scored_run_refusals_is_SILENT_on_a_healthy_warmup():
    # Negative control. Every refusal below is worthless if this one does not hold.
    assert _refusals() == [], _refusals()


def test_preflight_refuses_a_warmup_expansion_error():
    exp = {"observed": True, "baml_error": "BAML output structurally punted: ['x']",
           "baml_fallback": "poisoned_manifest_suppressed"}
    _, rc, _ = _preflight(dict(GOOD, stages=exp))
    assert rc == 3, rc


def test_preflight_refuses_a_warmup_with_no_stages_block():
    # Unobservable is not healthy. The same shape as stage_health's `unobservable` state: a
    # stage whose health cannot be read must never be counted as ok.
    payload = dict(GOOD)
    payload.pop("stages")
    _, rc, _ = _preflight(payload)
    assert rc == 3, rc


def test_expansion_override_scores_anyway_and_names_itself():
    exp = {"observed": True, "baml_error": "missing env var", "baml_fallback": "dedup_only"}
    _, rc, _ = _preflight(dict(GOOD, stages=exp), allow_expansion_errors=True)
    assert rc == 0, rc


def test_expansion_refusal_quotes_the_error_and_the_fallback():
    # A refusal that does not say WHAT it saw sends the reader back to the log.
    r = _refusals(warmup_expansion={"observed": True, "baml_error": "punted: ['x']",
                                    "baml_fallback": "poisoned_manifest_suppressed"})
    assert len(r) == 1, r
    assert "punted" in r[0] and "poisoned_manifest_suppressed" in r[0], r[0]


def test_expansion_remedy_separates_the_env_fault_from_the_punt():
    # The old warning said "Check LITELLM_PROXY_URL" for both causes. One is a dead dependency
    # and deterministic; the other is a stochastic BAML punt whose remedy is to rerun.
    env = RE._expansion_remedy("LLM client 'LocalRouter' requires environment variable "
                               "'LITELLM_PROXY_URL' to be set but it is not")
    punt = RE._expansion_remedy("BAML output structurally punted: "
                                "['entities_given_none_returned']")
    assert "LITELLM_PROXY_URL" in env and "rerun" not in env.lower(), env
    assert "rerun" in punt.lower() and "LITELLM_PROXY_URL" not in punt, punt


def test_preflight_refuses_when_no_provider_pin_is_set():
    unpinned = dict(LM_REC, provider_pin=None, pin_honored=None)
    _, rc, _ = _preflight(dict(GOOD, answer_lm=unpinned, openrouter_provider_pin=None))
    assert rc == 3, rc


def test_pin_override_permits_an_unpinned_arm():
    unpinned = dict(LM_REC, provider_pin=None, pin_honored=None)
    _, rc, _ = _preflight(dict(GOOD, answer_lm=unpinned, openrouter_provider_pin=None),
                          allow_unpinned_provider=True)
    assert rc == 0, rc


def test_pin_refusal_fires_on_None_as_well_as_False():
    # The closed hole: the old code PRINTED "unchecked is not honored" about
    # provider_served=None and then returned 0. False and None are different facts with the
    # same consequence for a comparison.
    for honored in (False, None):
        alm = dict(LM_REC, pin_honored=honored, provider_served=None)
        r = _refusals(answer_lm=alm)
        assert len(r) == 1 and "pin_honored" in r[0], (honored, r)


def test_pin_refusal_does_not_fire_when_the_pin_came_from_the_server_block():
    # Negative control on the pin's SOURCE: a per-call record with no provider_pin but a
    # server-reported pin, honored, is a pinned arm and must not refuse.
    alm = dict(LM_REC, provider_pin=None)
    r = _refusals(answer_lm=alm,
                  openrouter_provider_pin={"order": ["streamlake"], "allow_fallbacks": False})
    assert r == [], r


def test_no_warmup_refuses_BOTH_health_conditions():
    r = RE.scored_run_refusals({"warmup_ran": False})
    assert len(r) == 2, r
    assert any("expansion_healthy" in x for x in r) and any("pin_honored" in x for x in r), r


def test_no_warmup_proceeds_only_with_both_overrides():
    assert RE.scored_run_refusals({"warmup_ran": False}, True, True) == []
    assert len(RE.scored_run_refusals({"warmup_ran": False}, True, False)) == 1
    assert len(RE.scored_run_refusals({"warmup_ran": False}, False, True)) == 1


def test_every_named_condition_can_actually_refuse():
    """Assert the COUNT and that each named condition has a reachable refusal.

    Derived, not pinned: the gate's conditions are read from SCORED_RUN_CONDITIONS and each one
    must be produced by some input. A condition listed in the header but enforced nowhere is
    the exact defect this work exists to fix, and a snapshot of three message strings would not
    notice it.
    """
    fired = set()
    for x in RE.scored_run_refusals({"warmup_ran": False}):
        for c in RE.SCORED_RUN_CONDITIONS:
            if c in x:
                fired.add(c)
    bad = RE.write_run_header(Path(tempfile.mkdtemp()) / "nope" / "deeper",
                              RE.build_run_header("http://x", [], 1, 1.0, {}, {}, None, []))
    for c in RE.SCORED_RUN_CONDITIONS:
        if bad and c in bad:
            fired.add(c)
    assert len(RE.SCORED_RUN_CONDITIONS) == 3, RE.SCORED_RUN_CONDITIONS
    assert fired == set(RE.SCORED_RUN_CONDITIONS), (fired, RE.SCORED_RUN_CONDITIONS)


# --- condition 3: the header -------------------------------------------------------------

def _hdr(**kw):
    info = {"warmup_ran": True, "answer_lm": dict(LM_REC), "lm_cache_enabled": False,
            "warmup_expansion": dict(STAGES_OK, observed=True)}
    args = {"endpoint": "http://x/api/search", "question_ids": ["a", "b"], "n_runs": 5,
            "timeout": 200.0, "warmup_info": info, "git_at_start": {"head": "abc", "dirty": False},
            "corpus_at_start": _corpus(), "overrides_in_force": []}
    args.update(kw)
    return RE.build_run_header(**args)


def test_run_header_round_trips_and_names_the_arm():
    out = Path(tempfile.mkdtemp())
    h = _hdr()
    assert RE.write_run_header(out, h) is None
    back = json.loads((out / RE.RUN_HEADER_NAME).read_text(encoding="utf-8"))
    assert back["config_sha16"] == h["config_sha16"], back
    # The facts a reader of an abandoned directory needs: which endpoint, which commit, which
    # corpus, which provider, which temperature, whether expansion was alive.
    assert back["endpoint"] == "http://x/api/search"
    assert back["git"]["head"] == "abc"
    assert back["corpus"]["content_sha256"] == h["corpus"]["content_sha256"]
    assert back["answer_lm"]["provider_served"] == "StreamLake"
    assert back["answer_lm"]["temperature_on_the_wire"] == 0.0
    assert back["answer_lm"]["pin_honored"] is True
    assert back["expansion"]["observed"] is True
    assert back["question_ids"] == ["a", "b"] and back["n_runs"] == 5


def test_run_header_refuses_an_unwritable_destination():
    # A write that silently failed would leave the anonymous directory the header exists to
    # prevent, so the refusal is on write-and-read-back, not on write alone.
    missing = Path(tempfile.mkdtemp()) / "no-such-dir" / "deeper"
    msg = RE.write_run_header(missing, _hdr())
    assert msg and "header_written" in msg, msg


def test_run_header_refuses_a_DIFFERENT_config_in_the_same_directory():
    out = Path(tempfile.mkdtemp())
    assert RE.write_run_header(out, _hdr()) is None
    msg = RE.write_run_header(out, _hdr(n_runs=3))
    assert msg and "DIFFERENT config" in msg, msg
    # and it did not clobber the first header
    back = json.loads((out / RE.RUN_HEADER_NAME).read_text(encoding="utf-8"))
    assert back["n_runs"] == 5, back


def test_run_header_accepts_a_rerun_of_the_SAME_config():
    # Negative control: a refusal that fires on every rerun teaches its reader to ignore it.
    out = Path(tempfile.mkdtemp())
    assert RE.write_run_header(out, _hdr()) is None
    assert RE.write_run_header(out, _hdr()) is None


def test_config_sha16_ignores_wall_clock():
    a, b = _hdr(), _hdr()
    b["written_at"] = "1999-01-01T00:00:00Z"
    assert RE.config_sha16(a) == RE.config_sha16(b)


def test_run_header_records_the_overrides_in_force():
    h = _hdr(overrides_in_force=[RE.EXPANSION_OVERRIDE_FLAG])
    assert h["overrides_in_force"] == [RE.EXPANSION_OVERRIDE_FLAG], h
    # and a waived condition changes the config identity, so two arms that differ only in which
    # gate was waived are not the same config
    assert RE.config_sha16(h) != RE.config_sha16(_hdr())


def test_a_run_header_is_not_a_question_file():
    # The header lands in the same directory as the per-question results. compare_arms and the
    # expansion census both glob *.json there; without this it becomes a phantom question.
    import run_dir
    assert run_dir.is_question_file("scapegoat_001.json")
    for name in ("run_header.json", "summary.json", "ABORTED.json", "PUBLISHED.json",
                 "report.md"):
        assert not run_dir.is_question_file(name), name


def test_the_run_dir_consumers_do_not_restate_the_exclusion_list():
    # Four copies of this knowledge existed and no two agreed. A new sidecar must be added in
    # one place, so assert the consumers resolve it through run_dir rather than by name.
    for mod in ("run_eval.py", "compare_arms.py", "expansion_census.py"):
        src = (Path(__file__).resolve().parent / mod).read_text(encoding="utf-8")
        assert "from run_dir import" in src, mod
        body = src.split("from run_dir import", 1)[1]
        assert 'name == "summary.json"' not in body, mod
        assert '!= "ABORTED.json"' not in body, mod


# --- the whole launcher, end to end -----------------------------------------------------

def _run_main_with_warmup(responses, ids, extra_argv=()):
    """Drive RE.main WITH a warmup, so the preflight gate is on the path.

    _run_main passes --no-warmup and therefore waives both health conditions; these tests are
    about the gate itself, so they must not.
    """
    out = Path(tempfile.mkdtemp()) / "run"
    stub, orig = _SeqStub(responses), RE.call_endpoint
    orig_cs = RE.corpus_state
    RE.call_endpoint = stub

    def _refuse(*a, **kw):
        raise AssertionError("the offline suite must not read the live corpus")

    RE.corpus_state = _refuse
    try:
        rc = RE.main(["--endpoint", "http://x/api/search", "--output-dir", str(out),
                      "--ids"] + list(ids) + ["--runs", "1", "--allow-dirty-tree",
                                              "--corpus-fingerprint", "skip"] + list(extra_argv))
    finally:
        RE.call_endpoint = orig
        RE.corpus_state = orig_cs
    return rc, out, stub


def test_main_scores_NOTHING_when_the_warmup_expansion_is_broken():
    """The whole point. The arm this gate came from scored 65 runs after this exact warning."""
    broken = dict(GOOD, stages={"baml_error": "BAML output structurally punted: "
                                              "['entities_given_none_returned']",
                                "baml_fallback": "poisoned_manifest_suppressed"})
    rc, out, stub = _run_main_with_warmup([broken], ["logos_001"])
    assert rc == 3, rc
    assert stub.calls == 1, ("a scored question was sent after the refusal", stub.calls)
    assert not (out / "summary.json").exists(), sorted(p.name for p in out.iterdir())
    assert RE.question_files(p.name for p in out.iterdir()) == [], sorted(
        p.name for p in out.iterdir())


def test_main_writes_the_header_BEFORE_the_first_question_file():
    rc, out, stub = _run_main_with_warmup([GOOD], ["logos_001"])
    assert rc == 0, rc
    hdr_path = out / RE.RUN_HEADER_NAME
    assert hdr_path.is_file(), sorted(p.name for p in out.iterdir())
    q = out / "logos_001.json"
    assert q.is_file(), sorted(p.name for p in out.iterdir())
    assert hdr_path.stat().st_mtime <= q.stat().st_mtime, "header written after the question"
    hdr = json.loads(hdr_path.read_text(encoding="utf-8"))
    assert hdr["question_ids"] == ["logos_001"], hdr
    assert hdr["overrides_in_force"] == [], hdr


def test_main_records_the_gate_state_in_the_summary():
    rc, out, _ = _run_main_with_warmup([GOOD], ["logos_001"])
    assert rc == 0, rc
    pre = _summary(out)["integrity"]["preflight"]
    assert pre["conditions_enforced"] == list(RE.SCORED_RUN_CONDITIONS), pre
    assert pre["overrides_in_force"] == [], pre
    assert pre["config_sha16"], pre


def test_main_records_a_WAIVED_condition_in_the_summary():
    # An escape hatch nobody can see in the artifact is the same hole in a new place.
    broken = dict(GOOD, stages={"baml_error": "missing env var", "baml_fallback": "dedup_only"})
    rc, out, _ = _run_main_with_warmup([broken], ["logos_001"],
                                       ["--allow-expansion-errors"])
    # The override waives the LAUNCH refusal, not the post-run violation: the arm runs, and
    # still exits 4 because its scored runs had an expansion error. Waiving a gate must not
    # also silence the check downstream of it.
    assert rc == 4, rc
    viols = _summary(out)["integrity"]["violations"]
    assert any("expansion" in v for v in viols), viols
    pre = _summary(out)["integrity"]["preflight"]
    assert pre["overrides_in_force"] == [RE.EXPANSION_OVERRIDE_FLAG], pre
    hdr = json.loads((out / RE.RUN_HEADER_NAME).read_text(encoding="utf-8"))
    assert hdr["overrides_in_force"] == [RE.EXPANSION_OVERRIDE_FLAG], hdr


def test_the_header_write_precedes_the_scoring_loop_in_SOURCE():
    # Ordering is the property, and a passing end-to-end test on one input does not pin it.
    assert SRC.index("write_run_header(out_dir") < SRC.index(
        "results: List[QuestionResult] = []"), "the header must be written before scoring"
    assert SRC.index("scored_run_refusals(info") < SRC.index("return info, 0"), \
        "the health gate must run before preflight returns success"

# A hand-rolled suite reports what it happened to collect. If a test is renamed out of the
# test_ prefix, deleted, or shadowed by a duplicate name, the run still prints "N passed, 0
# failed" and looks healthy. Assert the COUNT so a silently shrinking suite fails loudly.
EXPECTED_TESTS = 144

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
    if passed + failed != EXPECTED_TESTS:
        print("FAIL suite: collected %d tests, expected %d - a test was lost or added without "
              "updating EXPECTED_TESTS" % (passed + failed, EXPECTED_TESTS))
        failed += 1
    sys.exit(1 if failed else 0)
