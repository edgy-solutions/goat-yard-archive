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
    """
    evals = os.path.join(os.path.dirname(_HERE), "evals")
    assert os.path.isdir(evals), evals
    hits = {}
    for fn in sorted(f for f in os.listdir(evals) if f.endswith(".py")):
        text = io.open(os.path.join(evals, fn), encoding="utf-8").read()
        body = text.split('if __name__')[0]
        if '"debug": True' in body or '"debug": true' in body.lower():
            hits[fn] = body
    return hits


def test_EVERY_eval_script_that_requests_a_debug_capture_handles_the_403():
    hits = _debug_consumers()
    # Liveness: a probe that matched nothing would pass on nothing, and this
    # one's whole job is to notice a consumer nobody wired up.
    assert len(hits) >= 2, sorted(hits)
    bare = [fn for fn, body in hits.items()
            if "refuse_if_debug_disabled" not in body]
    assert not bare, (
        "these evals request debug captures but do not route the response "
        "through evals/debug_capture.py, so the gate's 403 reaches the "
        "operator as a bare HTTP error: %r" % bare)


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


if __name__ == "__main__":
    EXPECTED_TEST_COUNT = 12
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
