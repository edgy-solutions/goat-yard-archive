"""Born-tests for the run_eval harness integrity changes (ruling 1, 2026-09-27).

Offline: no network, no endpoint, no model. `call_endpoint` is stubbed where a request
would otherwise be made, so these run anywhere and cannot touch a reserved GPU endpoint.

What is under test is not "does the harness compute a number" but "does the harness refuse
to compute a number it has no data for". On 2026-09-20 the flag-on arm reported 17/28 with
14 of 84 runs having produced no generation at all, and an N=3 stability block whose extra
runs were in-process cache replays. Both conditions were invisible in the output.

    python test_run_eval_harness.py
"""
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

GOOD = {"answer": "Gill holds this [GENESIS_2_8_S01].", "generation_seconds": 12.5,
        "lm_cache_enabled": False, "answer_lm": dict(LM_REC)}


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


def test_preflight_proceeds_when_the_pin_is_merely_UNCHECKABLE():
    # None is not False. An unpinned arm, or one whose provider could not be read, is still a
    # valid measurement of itself -- it just cannot claim a verified provider. Aborting here
    # would make every unpinned baseline unrunnable.
    unk = dict(LM_REC, provider_pin=None, provider_served=None,
               provider_served_source="unavailable:no-provider-on-dspy-response", pin_honored=None)
    _, rc, _ = _preflight(dict(GOOD, answer_lm=unk, openrouter_provider_pin=None), n_runs=1)
    assert rc == 0, rc


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
    _, rc, _ = _preflight({"answer": "ok", "answer_lm": dict(LM_REC)}, n_runs=1)
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


def _run_main(responses, ids):
    out = Path(tempfile.mkdtemp()) / "run"
    stub, orig = _SeqStub(responses), RE.call_endpoint
    RE.call_endpoint = stub
    try:
        rc = RE.main(["--endpoint", "http://x/api/search", "--output-dir", str(out),
                      "--ids"] + ids + ["--runs", "1", "--no-warmup", "--allow-dirty-tree"])
    finally:
        RE.call_endpoint = orig
    return rc, out, stub


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
