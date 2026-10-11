"""Born-tests for backend/debug_gate.py and the two gates it feeds in main.py.

    python backend/test_debug_gate.py

backend/main.py cannot be imported here (it pulls in Weaviate/DSPy), so the
route-level assertions read it as plain text, the style
backend/test_stage_health.py and backend/test_typed_channels.py already use.
"""
from __future__ import annotations

import io
import os
import sys
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import debug_gate as dg  # noqa: E402

_MAIN = io.open(os.path.join(_HERE, "main.py"), encoding="utf-8").read()


class _Env:
    """Set or clear GYA_DEBUG_STAGES and always put the old value back."""

    def __init__(self, val):
        self.val = val

    def __enter__(self):
        self.prev = os.environ.get(dg.ENV_VAR)
        if self.val is None:
            os.environ.pop(dg.ENV_VAR, None)
        else:
            os.environ[dg.ENV_VAR] = self.val
        return self

    def __exit__(self, *exc):
        os.environ.pop(dg.ENV_VAR, None)
        if self.prev is not None:
            os.environ[dg.ENV_VAR] = self.prev
        return False


def test_the_gate_is_CLOSED_when_the_var_is_absent():
    # The default is the whole point: a capture channel that is open unless
    # someone remembers to close it is what this gate replaces.
    with _Env(None):
        assert dg.stage_debug_allowed() is False


def test_only_the_explicit_TRUE_VALUES_open_it():
    cases = [("1", True), ("true", True), ("TRUE", True), ("on", True),
             ("yes", True), (" 1 ", True),
             ("0", False), ("false", False), ("", False), ("maybe", False),
             ("2", False), ("off", False), ("none", False), ("debug", False)]
    for val, expected in cases:
        with _Env(val):
            assert dg.stage_debug_allowed() is expected, (val, expected)


def test_it_is_read_PER_CALL_not_at_import():
    # Read per call so a request is judged by the environment it arrives in,
    # and so this file can flip it without reimporting the module.
    with _Env("1"):
        assert dg.stage_debug_allowed() is True
    with _Env("0"):
        assert dg.stage_debug_allowed() is False
    with _Env("1"):
        assert dg.stage_debug_allowed() is True


def test_the_env_var_name_is_the_one_the_CHART_actually_sets():
    """The gate and the chart have to agree on the literal, and nothing else
    checks that: main.py names the variable through debug_gate.ENV_VAR (one
    definition, deliberately), so a renamed var would leave the chart setting a
    key no code reads and the gate silently closed in every environment.

    The two chart files are located and read here rather than assumed; a probe
    that cannot find its input passes on nothing.
    """
    assert dg.ENV_VAR == "GYA_DEBUG_STAGES", dg.ENV_VAR
    # main.py must NOT hardcode it -- it interpolates debug_gate.ENV_VAR into
    # the 403 so the operator message cannot drift from the thing being read.
    assert "debug_gate.ENV_VAR" in _MAIN

    chart = os.path.join(os.path.dirname(_HERE), "charts", "goat-yard-archive")
    prod = os.path.join(chart, "values.yaml")
    test = os.path.join(chart, "values-test.yaml")
    for p in (prod, test):
        assert os.path.exists(p), p
    prod_text = io.open(prod, encoding="utf-8").read()
    test_text = io.open(test, encoding="utf-8").read()
    assert dg.ENV_VAR + ': "0"' in prod_text, "production does not set it OFF explicitly"
    assert dg.ENV_VAR + ': "1"' in test_text, "gya-test does not set it ON"
    # And the key has to survive templating: the configmap enumerates its keys
    # one by one, so a values entry with no stanza reaches no pod.
    cm = io.open(os.path.join(chart, "templates", "configmap.yaml"), encoding="utf-8").read()
    assert dg.ENV_VAR + ": {{ .Values.api.env." + dg.ENV_VAR in cm, cm[:1]


def test_source_the_route_REFUSES_a_debug_request_instead_of_quietly_dropping_it():
    assert "if req.debug and not debug_gate.stage_debug_allowed():" in _MAIN
    assert "status_code=403" in _MAIN
    # A 200 with stages: null would tell the caller this build has no stage
    # captures, which is a different and false statement.
    assert "stage debug captures are disabled in this deployment" in _MAIN


def test_source_the_CAPTURE_is_gated_too_not_only_the_refusal():
    assert "{} if (req.debug and debug_gate.stage_debug_allowed()) else None" in _MAIN
    assert "{} if req.debug else None" not in _MAIN, \
        "the capture is populated from req.debug alone again"


def test_source_the_refusal_comes_BEFORE_the_capture_is_built():
    gate = _MAIN.index("if req.debug and not debug_gate.stage_debug_allowed():")
    cap = _MAIN.index("stages_capture: Optional[dict] = (")
    assert gate < cap, (gate, cap)


def test_source_debug_still_DEFAULTS_to_false_on_the_request_model():
    # The gate is the second line of defence, not the first: a caller has to
    # ask for debug, and a deployment has to allow it.
    assert "debug: bool = False" in _MAIN


def test_source_main_imports_the_gate_module():
    assert "from . import debug_gate" in _MAIN


def _debug_consumers():
    """Every file under evals/ that asks the API for a debug capture.

    DERIVED on every run. The docstring in debug_gate.py originally named one
    consumer when there were two: determinism_harness.py had the 403 remedy
    and zone3_eval_replay.py, a DAILY monitor, got the bare 403 that reads as
    an ingress fault. A hand-maintained list would have been just as wrong, so
    the set is read off disk.

    A consumer POSTS the payload; a file that merely MENTIONS it does not.
    evals/test_run_eval_harness.py asserts the literal appears in run_eval's
    source, and the release line's version of this probe -- which keyed on the
    literal alone -- called it a consumer and demanded it handle a 403 it can
    never receive. The discriminator is behavioural (`.post(`) rather than a
    name prefix, because "it is a test file" is a fact about the filename and
    "it never makes a request" is the fact that matters.
    """
    evals = os.path.join(os.path.dirname(_HERE), "evals")
    assert os.path.isdir(evals), evals
    hits, mentions = {}, []
    for fn in sorted(f for f in os.listdir(evals) if f.endswith(".py")):
        text = io.open(os.path.join(evals, fn), encoding="utf-8").read()
        body = text.split('if __name__')[0]
        if '"debug": True' not in body and '"debug": true' not in body.lower():
            continue
        if ".post(" in body:
            hits[fn] = body
        else:
            mentions.append(fn)
    return hits, mentions


def _dc():
    sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "evals"))
    import debug_capture  # noqa: E402
    return debug_capture


def test_EVERY_eval_script_that_requests_a_debug_capture_handles_the_403():
    hits, _ = _debug_consumers()
    # Liveness: a probe that matched nothing would pass on nothing, and this
    # one's whole job is to notice a consumer nobody wired up. Four on this
    # branch: run_eval, determinism_harness, zone3_eval_replay,
    # acceptance_entity_manifest.
    assert len(hits) >= 4, sorted(hits)
    bare = [fn for fn, body in hits.items()
            if "refuse_if_debug_disabled" not in body]
    assert not bare, (
        "these evals request debug captures but do not route the response "
        "through evals/debug_capture.py, so the gate's 403 reaches the "
        "operator as a bare HTTP error: %r" % bare)


def test_EVERY_consumer_REFUSES_a_target_that_carries_no_stage_captures():
    """Chris's ruling of 2026-10-11: "eval preflight refuses a target without
    stages, naming the flag."

    The per-request 403 handler is not enough on its own. Each of these scripts
    makes MANY requests, and the fault they are protected from is spending the
    whole run before learning the target could not answer the question being
    asked of it -- which is what happened on 2026-09-20.

    The rule is the CHECK, not one function's name. Three consumers do it with
    one probe up front (preflight_debug_capture); run_eval does it in
    run_level_fault, which every response passes through, because a probe there
    cost a real generation on the one path --no-warmup exists to serve and still
    could not see a pod rolled mid-run. Both name the flag, from one text. The
    symbol set is debug_capture's own, so this is not a hand-kept allow-list.
    """
    hits, _ = _debug_consumers()
    assert len(hits) >= 4, sorted(hits)
    symbols = _dc().STAGES_CHECK_SYMBOLS
    unchecked = [fn for fn, body in hits.items()
                 if not any(sym in body for sym in symbols)]
    assert not unchecked, (
        "these evals post debug captures but never check that the target returned "
        "any, so a misconfigured backend is discovered question by question "
        "instead of up front: %r" % unchecked)


def test_every_STAGES_CHECK_SYMBOL_actually_exists_in_debug_capture():
    """Liveness for the probe above. It keys on names; a renamed or deleted name
    would make `any(sym in body)` false for everyone -- loud -- but a STALE extra
    name would make it true for a file that only mentions the dead symbol, and
    that failure is silent. So each one is resolved on the module."""
    dc = _dc()
    assert dc.STAGES_CHECK_SYMBOLS, "the symbol set is empty; the probe above passes on nothing"
    for sym in dc.STAGES_CHECK_SYMBOLS:
        assert hasattr(dc, sym), (
            "%s is in STAGES_CHECK_SYMBOLS but does not exist in debug_capture" % sym)


def test_a_file_that_only_MENTIONS_the_payload_is_not_called_a_consumer():
    """The discriminator itself, with a liveness floor.

    evals/test_run_eval_harness.py contains the literal inside an assertion
    about run_eval's source and makes no request. If this list is ever empty the
    discriminator has stopped discriminating and the probe above is weaker than
    it reads -- so the floor is asserted, not assumed.
    """
    hits, mentions = _debug_consumers()
    assert mentions, "no mention-only file found; the discriminator is untested"
    assert not (set(mentions) & set(hits)), (sorted(mentions), sorted(hits))
    # Exactly two kinds of mention are legitimate, and they are named rather than
    # pattern-matched loosely: the SHARED MODULE itself (it builds the probe payload
    # and sends it through an injected sender, which is how its refusals are
    # testable without a server), and a TEST that asserts on another file's source.
    # Anything else mentioning the payload without posting it is something to look
    # at -- this assertion found debug_capture.py the first time it ran, which is
    # the only reason the exclusion above is stated instead of assumed.
    for fn in mentions:
        assert fn == "debug_capture.py" or fn.startswith("test_"), (
            "%s mentions the debug payload without posting it, and is neither the "
            "shared refusal module nor a test; look at it before trusting this "
            "exclusion" % fn)


def test_the_shared_refusal_NAMES_the_env_var_and_the_restart():
    # The remedy is the whole point of the module: a 403 that does not say
    # what to set is the stack trace it replaced.
    p = os.path.join(os.path.dirname(_HERE), "evals", "debug_capture.py")
    assert os.path.exists(p), p
    text = io.open(p, encoding="utf-8").read()
    assert dg.ENV_VAR in text, dg.ENV_VAR
    assert "restart" in text.lower(), "the rollout-restart caveat is missing"


def test_the_shared_refusal_is_SILENT_on_every_other_status():
    # A module that aborted on any error status would hide a 500 behind a
    # confident message about a flag it has no evidence about.
    sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "evals"))
    import debug_capture  # noqa: E402

    class _R:
        def __init__(self, code):
            self.status_code = code
            self.text = "body"

    for code in (200, 404, 500, 502):
        debug_capture.refuse_if_debug_disabled(_R(code), "http://x", "t")
    try:
        debug_capture.refuse_if_debug_disabled(_R(403), "http://x", "t")
    except SystemExit as exc:
        assert dg.ENV_VAR in str(exc), str(exc)
    else:
        raise AssertionError("403 did not abort")


class _Resp:
    def __init__(self, code, body=None, raises=False):
        self.status_code = code
        self.text = "body text"
        self._body = body
        self._raises = raises

    def json(self):
        if self._raises:
            raise ValueError("not json")
        return self._body


def _probe(resp=None, exc=None):
    """Run the preflight against a canned response. Returns (ok, message)."""
    dc = _dc()

    def post(url, headers=None, json=None, timeout=None):
        if exc is not None:
            raise exc
        return resp

    try:
        keys = dc.preflight_debug_capture("http://x/api/search", "t", post=post)
    except SystemExit as e:
        return False, str(e)
    return True, keys


def test_the_PREFLIGHT_passes_a_target_that_carries_stages():
    # Negative control. Every refusal below certifies nothing without this.
    ok, keys = _probe(_Resp(200, {"stages": {"question": "q", "baml_expansion": "x"}}))
    assert ok, keys
    assert keys == ["baml_expansion", "question"], keys


def test_the_PREFLIGHT_refuses_a_200_with_NO_stages_and_names_the_flag():
    for body in ({"answer": "a"}, {"stages": None}, {"stages": {}}, {"stages": []}):
        ok, msg = _probe(_Resp(200, body))
        assert not ok, body
        assert dg.ENV_VAR in msg, (body, msg)
        # It must say what to DO, not only what is wrong.
        assert "restart" in msg.lower() or "roll" in msg.lower(), msg


def test_the_PREFLIGHT_treats_the_gates_403_as_the_FLAG_and_says_so():
    ok, msg = _probe(_Resp(403))
    assert not ok
    assert dg.ENV_VAR in msg, msg


def test_the_PREFLIGHT_does_NOT_blame_the_flag_for_any_other_status():
    """A refusal that names a flag it has no evidence about is worse than a
    stack trace: it sends the reader to set something that was already set.
    Same rule as refuse_if_debug_disabled staying silent on a 500 -- here the
    run must still abort, but the message has to disclaim the diagnosis."""
    for code in (404, 500, 502):
        ok, msg = _probe(_Resp(code))
        assert not ok, code
        assert "NOT a diagnosis" in msg, (code, msg)
        assert str(code) in msg, (code, msg)


def test_the_PREFLIGHT_does_NOT_blame_the_flag_when_the_request_never_completed():
    ok, msg = _probe(exc=OSError("connection refused"))
    assert not ok
    assert "NOT a diagnosis" in msg, msg
    assert "OSError" in msg, msg


def test_the_PREFLIGHT_refuses_a_200_whose_body_is_not_JSON():
    ok, msg = _probe(_Resp(200, raises=True))
    assert not ok
    assert "Not a flag diagnosis" in msg, msg


def test_source_the_NO_RESULTS_path_carries_the_stages_it_did_collect():
    """Both SearchResponse return sites pass the capture.

    The no-results early return used to omit it, so a debug caller got 200 with
    `stages: null` -- the statement "this build has no capture channel", which
    was false: the channel was open and the query had retrieved nothing. That
    also made the preflight unsound, since it refuses on exactly that shape.
    """
    assert _MAIN.count("stages=stages_capture") == 2, _MAIN.count("stages=stages_capture")
    assert _MAIN.count("return SearchResponse(") == 2, "a third return site appeared"


if __name__ == "__main__":
    EXPECTED_TEST_COUNT = 22
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    if len(tests) != EXPECTED_TEST_COUNT:
        print("FAIL  expected %d tests, collected %d -- a test silently disappeared"
              % (EXPECTED_TEST_COUNT, len(tests)))
        sys.exit(1)

    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("  ok    %s" % name)
        except KeyboardInterrupt:
            raise
        # SystemExit is NOT an Exception: `except Exception` lets a test that
        # reaches sys.exit end the whole run with no summary line, which reads
        # as a shorter suite (witnessed 2026-10-11 in evals/test_gate_paired.py).
        except BaseException:
            failed += 1
            print("  FAIL  %s" % name)
            traceback.print_exc()
    print("")
    print("%d/%d passed" % (len(tests) - failed, len(tests)))
    sys.exit(1 if failed else 0)
