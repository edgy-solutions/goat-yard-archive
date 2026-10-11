"""Born-tests for the BoundedTransport retry policy on OptimizeSearchQuery
(baml_src/main.baml), added after a single truncated HTTP response body voided
a scored eval arm (real_ishmael_circumcision_001, 1 request in 67) with NO
retry anywhere in baml_src.

    PYTHONIOENCODING=utf-8 python backend/test_expansion_retry.py

This file plays two roles, selected by argv, exactly like a probe script that
has been promoted into a test:

  - `python backend/test_expansion_retry.py <mode>` (mode is "decode_truncation"
    or "silent_close") runs ONE probe in THIS process: start a raw socket
    server that reproduces one fault class, point LITELLM_PROXY_URL at it,
    call b.OptimizeSearchQuery, and print a single JSON line with what
    happened. This has to be a separate process per probe because
    baml_client reads env.LITELLM_PROXY_URL at import time, so the env var
    must be set before baml_client is first imported -- two probes in one
    process could not each get their own fake server.
  - `python backend/test_expansion_retry.py` (no mode) runs the test suite:
    each test spawns the above as a subprocess (sys.executable, __file__,
    mode), parses its one JSON line, and asserts on it.

Two fault classes are covered because they are different reqwest/hyper error
*kinds*, and the policy's coverage of one says nothing about the other:
  - "decode_truncation": server sends `HTTP/1.1 200 OK` + `Content-Length:
    5000`, writes 10 bytes, closes. Body shorter than declared ->
    reqwest kind: Decode / hyper::Error(Body, IncompleteBody).
  - "silent_close": server writes NOTHING and closes. No response message
    ever arrived -> reqwest kind: Request / hyper_util
    Error(SendRequest, hyper::Error(IncompleteMessage)). THIS is the exact
    shape of the fault that voided the scored arm.

NOTE on why retries are counted as len(log.calls) - 1 and not by inspecting
`selected`: every one of the 4 calls BAML makes for a single bounded-retry
request -- the original attempt and all 3 retries -- reports
`LLMCall.selected == True`. There is no "this was the one that actually
returned" flag to read off an individual call; `selected` marks something
else (which client in a policy was chosen, not which attempt succeeded) and
cannot be used to tell attempt 1 from attempt 4. The only reliable count is
the length of the call list itself minus the one original attempt.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))


def _repo_root() -> str:
    # backend/ is one level below the repo root; baml_client and baml_src
    # live at the root, not under backend/.
    return os.path.dirname(_HERE)


# --------------------------------------------------------------------------
# Socket handlers for the two fault classes. Each drains the request first
# (so the client has finished sending before the fault fires), then diverges.
# --------------------------------------------------------------------------

def _drain_request(conn: "socket.socket") -> None:
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = conn.recv(65536)
        if not chunk:
            break
        buf += chunk


def _serve_decode_truncation(conn: "socket.socket") -> None:
    # Declares 5000 bytes, sends 10, hangs up -> reqwest kind: Decode /
    # hyper::Error(Body, IncompleteBody).
    _drain_request(conn)
    conn.sendall(
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: 5000\r\n\r\n"
        b'{"choices"'
    )


def _serve_silent_close(conn: "socket.socket") -> None:
    # Writes nothing at all and hangs up. This is the exact fault that voided
    # the scored arm: reqwest kind: Request, source: hyper_util
    # Error(SendRequest, hyper::Error(IncompleteMessage)) -- the connection
    # died before any response message arrived, as opposed to a body shorter
    # than its declared length (kind: Decode / IncompleteBody above).
    _drain_request(conn)


_HANDLERS = {
    "decode_truncation": _serve_decode_truncation,
    "silent_close": _serve_silent_close,
}


def _run_probe(mode: str) -> dict:
    """Runs entirely inside the subprocess started with argv[1] == mode. Starts
    the fake server, points LITELLM_PROXY_URL at it BEFORE importing
    baml_client (baml_client reads that env var at import time, so setting it
    after import would test nothing), makes the real call through the real
    LocalRouter client and its real BoundedTransport retry_policy from
    baml_src, and returns everything the tests need as a plain dict.
    """
    handler = _HANDLERS[mode]
    host = "127.0.0.1"
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, 0))
    srv.listen(16)
    port = srv.getsockname()[1]

    attempts = []
    stop = threading.Event()

    def serve():
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            attempts.append(time.monotonic())
            try:
                conn.settimeout(5.0)
                handler(conn)
            except Exception:
                pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    t = threading.Thread(target=serve, daemon=True)
    t.start()

    os.environ["LITELLM_PROXY_URL"] = "http://%s:%d/v1" % (host, port)

    sys.path.insert(0, os.path.abspath("."))
    import baml_py  # noqa: E402 -- deferred until the env var above is set
    from baml_client.sync_client import b  # noqa: E402

    collector = baml_py.Collector(name="probe")
    err = None
    try:
        b.OptimizeSearchQuery(
            user_query="what does Gill say about the Nazarite vow?",
            available_entities=["Nazarite", "vow"],
            baml_options={"collector": collector},
        )
    except Exception as e:  # noqa: BLE001 -- the point is which error survives the retries
        err = e

    stop.set()
    srv.close()

    log = collector.last
    calls = [] if log is None else list(log.calls)

    return {
        "mode": mode,
        "connections": len(attempts),
        "gaps": [attempts[i + 1] - attempts[i] for i in range(len(attempts) - 1)],
        "log_is_none": log is None,
        "calls": len(calls),
        "selected": [bool(c.selected) for c in calls],
        "error_type": None if err is None else type(err).__name__,
        "error_head": None if err is None else str(err)[:220],
    }


# --------------------------------------------------------------------------
# Skip (not fail) if this environment cannot import the BAML runtime at all.
# Checked once at module load, imported with sys.path temporarily carrying
# the repo root so baml_client resolves the same way the subprocess resolves
# it (cwd = repo root). The actual probes always run in a subprocess, so this
# check only ever gates whether the tests can attempt that subprocess.
# --------------------------------------------------------------------------

def _baml_import_problem():
    root = _repo_root()
    added = root not in sys.path
    if added:
        sys.path.insert(0, root)
    try:
        import importlib.util
        import baml_py  # noqa: F401
        if importlib.util.find_spec("baml_client.sync_client") is None:
            return "baml_client.sync_client not found under %s" % root
    except Exception as e:  # noqa: BLE001 -- any import failure means skip, not crash
        return "%s: %s" % (type(e).__name__, e)
    finally:
        if added:
            sys.path.remove(root)
    return None


_SKIP_REASON = _baml_import_problem()


def _expected_attempts() -> int:
    # Derived from baml_src/main.baml rather than hardcoded, so this test
    # follows the policy if it changes instead of silently asserting a
    # number the policy no longer sets.
    path = os.path.join(_repo_root(), "baml_src", "main.baml")
    text = io_read(path)
    import re
    m = re.search(r"retry_policy\s+BoundedTransport\s*\{.*?max_retries\s+(\d+)", text, re.DOTALL)
    assert m, "could not find 'max_retries' inside retry_policy BoundedTransport in %s" % path
    max_retries = int(m.group(1))
    return max_retries + 1


def io_read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _run_probe_subprocess(mode: str) -> dict:
    root = _repo_root()
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    # The child sets its own LITELLM_PROXY_URL before importing baml_client;
    # a value leaking in from this process's own environment would make the
    # subprocess silently test the wrong server.
    env.pop("LITELLM_PROXY_URL", None)
    proc = subprocess.run(
        [sys.executable, __file__, mode],
        capture_output=True, text=True, env=env, cwd=root, timeout=120,
    )
    assert proc.returncode == 0, (
        "probe subprocess (mode=%s) exited %d\nSTDOUT:\n%s\nSTDERR:\n%s"
        % (mode, proc.returncode, proc.stdout[-4000:], proc.stderr[-4000:])
    )
    lines = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
    assert lines, "probe subprocess (mode=%s) produced no stdout; stderr=%s" % (
        mode, proc.stderr[-2000:],
    )
    return json.loads(lines[-1])


# --------------------------------------------------------------------------
# Tests.
# --------------------------------------------------------------------------

def test_a_truncated_response_body_is_retried_to_the_bound_and_then_raises():
    # A FAILURE here means a response body that is shorter than its own
    # declared Content-Length (a mid-stream cut, not a 4xx/5xx) is treated as
    # an unretried hard failure again -- i.e. the regression this policy
    # exists to close has come back for the "Decode/IncompleteBody" fault
    # shape.
    if _SKIP_REASON:
        print("  SKIP  baml runtime unavailable: %s" % _SKIP_REASON)
        return
    expected = _expected_attempts()
    result = _run_probe_subprocess("decode_truncation")
    assert result["connections"] == expected, result
    assert result["calls"] == expected, result
    assert result["error_type"] == "BamlValidationError", result
    assert "kind: Decode" in result["error_head"], result["error_head"]
    assert "IncompleteBody" in result["error_head"], result["error_head"]
    # exponential_backoff: each gap strictly longer than the last.
    gaps = result["gaps"]
    assert len(gaps) == expected - 1, result
    assert all(gaps[i] < gaps[i + 1] for i in range(len(gaps) - 1)), gaps


def test_the_exact_fault_that_voided_an_arm_silent_close_is_retried():
    # A FAILURE here means the SPECIFIC fault that voided
    # real_ishmael_circumcision_001 (a connection that closes before any
    # response message arrives at all -- reqwest kind: Request /
    # hyper_util Error(SendRequest, hyper::Error(IncompleteMessage))) is still
    # an unretried hard failure. This is the one case that matters most: the
    # decode-truncation case above is a close cousin, not the actual incident.
    if _SKIP_REASON:
        print("  SKIP  baml runtime unavailable: %s" % _SKIP_REASON)
        return
    expected = _expected_attempts()
    result = _run_probe_subprocess("silent_close")
    assert result["connections"] == expected, result
    assert result["calls"] == expected, result
    assert result["error_type"] == "BamlValidationError", result
    assert "kind: Request" in result["error_head"], result["error_head"]
    assert "IncompleteMessage" in result["error_head"], result["error_head"]


def test_the_retry_is_bounded_not_a_loop():
    # A FAILURE here (connections > expected, for EITHER mode) means the
    # retry can fail to stop -- a retry policy that loops silently is the
    # same defect as having no retry at all, just harder to notice, because
    # now a broken transport burns requests forever instead of raising.
    if _SKIP_REASON:
        print("  SKIP  baml runtime unavailable: %s" % _SKIP_REASON)
        return
    expected = _expected_attempts()
    for mode in ("decode_truncation", "silent_close"):
        result = _run_probe_subprocess(mode)
        assert result["connections"] == expected, (mode, result)
        assert not (result["connections"] > expected), (mode, result)


def test_retries_are_counted_from_len_calls_minus_one_because_selected_is_useless():
    # A FAILURE here (any call's `selected` is False, or all four are not
    # True) means the premise behind every retry count in this file and in
    # backend/stage_health.py is wrong, and `selected` can in fact
    # distinguish attempts -- in which case the module docstring's warning is
    # stale and whatever currently reads len(log.calls) - 1 should be
    # revisited. As measured, `selected` marks something else entirely:
    # it is True on the original attempt AND on every one of the 3 retries.
    if _SKIP_REASON:
        print("  SKIP  baml runtime unavailable: %s" % _SKIP_REASON)
        return
    expected = _expected_attempts()
    result = _run_probe_subprocess("silent_close")
    assert result["calls"] == expected, result
    assert len(result["selected"]) == expected, result
    assert all(result["selected"]), result
    retries = result["calls"] - 1
    assert retries == expected - 1, result


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in _HANDLERS:
        print(json.dumps(_run_probe(sys.argv[1])))
        sys.exit(0)

    EXPECTED_TEST_COUNT = 4
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    if len(tests) != EXPECTED_TEST_COUNT:
        print(
            "FAIL  expected %d tests, collected %d -- a test silently disappeared"
            % (EXPECTED_TEST_COUNT, len(tests))
        )
        sys.exit(1)

    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("  ok    %s" % name)
        except KeyboardInterrupt:
            raise
        # SystemExit is NOT an Exception, so `except Exception` let a test that reaches sys.exit
        # end the WHOLE run silently -- no summary line, which reads as a shorter suite. Witnessed
        # 2026-10-11 in evals/test_gate_paired.py (argparse exits 2 on an unrecognized flag).
        except BaseException:
            failed += 1
            print("  FAIL  %s" % name)
            traceback.print_exc()
    print("")
    print("%d/%d passed" % (len(tests) - failed, len(tests)))
    sys.exit(1 if failed else 0)
