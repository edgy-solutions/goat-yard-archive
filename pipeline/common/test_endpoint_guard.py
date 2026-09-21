"""Born-tests for the endpoint guard. Run: python pipeline/common/test_endpoint_guard.py

Repo convention is a plain script with a __main__ runner (see
pipeline/reextract/test_box_sanity.py); pytest is not in the venv.

The tests that matter most are the ones asserting the guard cannot be talked out of a
refusal: a closed endpoint passed explicitly, through each env var, and in URL form must all
raise. A guard that only fires on the default would pass every other test here.
"""

from __future__ import annotations

import os
import sys
import traceback
from contextlib import contextmanager

# Import as `common.endpoint_guard`, with pipeline/ on the path, NOT as
# `pipeline.common...`: pipeline/__init__.py imports dagster_slack, which is not in
# the venv, so the package route fails before the guard is even loaded.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.endpoint_guard import (  # noqa: E402
    ClosedEndpointError,
    EndpointError,
    MissingEndpointError,
    assert_endpoint_allowed,
    resolve_ollama_bare_host,
    resolve_ollama_base_url,
    resolve_ollama_host,
)

OPEN_D = "192.168.1.169:11435"
CLOSED_E = "192.168.1.179"
CLOSED_F = "192.168.1.188"


@contextmanager
def _env(**kw):
    """Set/clear env vars for the duration of a test, restoring exactly."""
    old = {k: os.environ.get(k) for k in kw}
    try:
        for k, v in kw.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _clean():
    return _env(OLLAMA_HOST=None, OLLAMA_BASE_URL=None)


def _raises(exc, fn, *a, **kw):
    try:
        fn(*a, **kw)
    except exc as e:
        return str(e)
    except Exception as e:  # wrong exception type is a failure, not a pass
        raise AssertionError(f"expected {exc.__name__}, got {type(e).__name__}: {e}")
    raise AssertionError(f"expected {exc.__name__}, but the call returned normally")


# --------------------------------------------------------------------------
# 1. No default: absent endpoint raises rather than picking one
# --------------------------------------------------------------------------

def test_absent_endpoint_raises():
    with _clean():
        msg = _raises(MissingEndpointError, resolve_ollama_host)
        assert "no default" in msg, msg
        # The message must tell the operator what to do, not just that it failed.
        assert "OLLAMA_HOST" in msg, msg
        assert "gpu-servers.md" in msg, msg


def test_empty_and_whitespace_are_absent_not_valid():
    """'' and '   ' must not satisfy the requirement — they are absence, not a choice."""
    with _clean():
        _raises(MissingEndpointError, resolve_ollama_host, "")
        _raises(MissingEndpointError, resolve_ollama_host, "   ")
    with _env(OLLAMA_HOST="   ", OLLAMA_BASE_URL=None):
        _raises(MissingEndpointError, resolve_ollama_host)


# --------------------------------------------------------------------------
# 2. Hard refusal of E and F, by every route in
# --------------------------------------------------------------------------

def test_closed_E_refused_explicitly():
    """The load-bearing test: passed deliberately on the command line, still refused."""
    with _clean():
        msg = _raises(ClosedEndpointError, resolve_ollama_host, CLOSED_E)
        assert "192.168.1.179" in msg, msg
        assert "gpu-servers.md" in msg, msg
        assert "not overridable" in msg, msg


def test_closed_F_refused_explicitly():
    with _clean():
        msg = _raises(ClosedEndpointError, resolve_ollama_host, CLOSED_F)
        assert "192.168.1.188" in msg, msg
        assert "gpu-servers.md" in msg, msg


def test_closed_refused_via_each_env_var():
    for var in ("OLLAMA_HOST", "OLLAMA_BASE_URL"):
        with _clean():
            with _env(**{var: CLOSED_E}):
                msg = _raises(ClosedEndpointError, resolve_ollama_host)
                assert "192.168.1.179" in msg, msg


def test_closed_refused_in_url_and_host_port_form():
    """The check is on the resolved host, not string equality with a bare IP."""
    forms = [
        f"http://{CLOSED_E}:11434/v1",
        f"http://{CLOSED_E}:11434/api/embeddings",
        f"{CLOSED_E}:11434",
        f"https://{CLOSED_F}/v1",
        f"{CLOSED_F}:11434",
    ]
    with _clean():
        for f in forms:
            msg = _raises(ClosedEndpointError, resolve_ollama_host, f)
            assert "gpu-servers.md" in msg, f


def test_closed_refused_by_base_url_helper_too():
    """Both public entry points guard; neither is a side door around the other."""
    with _clean():
        _raises(ClosedEndpointError, resolve_ollama_base_url, CLOSED_E)
        _raises(ClosedEndpointError, resolve_ollama_base_url, f"http://{CLOSED_F}:11434")


def test_assert_endpoint_allowed_standalone():
    """Usable on its own at a call site that already holds an endpoint."""
    _raises(ClosedEndpointError, assert_endpoint_allowed, f"http://{CLOSED_F}:11434/v1")
    assert assert_endpoint_allowed(f"http://{OPEN_D}/v1") == f"http://{OPEN_D}/v1"


def test_explicit_closed_beats_open_env():
    """An open env var must not launder an explicitly closed argument."""
    with _env(OLLAMA_HOST=OPEN_D, OLLAMA_BASE_URL=None):
        _raises(ClosedEndpointError, resolve_ollama_host, CLOSED_E)


def test_no_force_or_override_parameter_exists():
    """Structural: if someone adds an escape hatch, this test fails.

    The refusal is only worth having while it cannot be argued past, so the absence of an
    override is itself part of the contract and is asserted, not just documented.
    """
    import inspect

    from common import endpoint_guard

    for name in ("assert_endpoint_allowed", "resolve_ollama_host", "resolve_ollama_base_url"):
        params = inspect.signature(getattr(endpoint_guard, name)).parameters
        for bad in ("force", "allow_closed", "override", "unsafe", "ignore_closed"):
            assert bad not in params, f"{name} grew an override parameter: {bad}"


# --------------------------------------------------------------------------
# 3. Open endpoints pass, and precedence is explicit > env
# --------------------------------------------------------------------------

def test_open_endpoint_D_passes():
    with _clean():
        assert resolve_ollama_host(OPEN_D) == OPEN_D


def test_env_used_when_no_explicit():
    with _env(OLLAMA_HOST=OPEN_D, OLLAMA_BASE_URL=None):
        assert resolve_ollama_host() == OPEN_D


def test_explicit_wins_over_env():
    with _env(OLLAMA_HOST="192.168.1.126", OLLAMA_BASE_URL=None):
        assert resolve_ollama_host(OPEN_D) == OPEN_D


def test_base_url_shapes():
    with _clean():
        assert resolve_ollama_base_url("192.168.1.169", port=11435) == "http://192.168.1.169:11435"
        assert resolve_ollama_base_url("192.168.1.169:11435") == "http://192.168.1.169:11435"
        assert resolve_ollama_base_url("http://192.168.1.169:11435/v1/") == "http://192.168.1.169:11435/v1"


def test_other_cluster_endpoints_are_not_refused():
    """Only E and F are closed. A guard that refused everything unfamiliar would be
    unusable, and would push people back to hardcoding."""
    with _clean():
        for host in ("192.168.1.126:11434", "192.168.1.100:11434", "192.168.1.169:11434"):
            assert resolve_ollama_host(host) == host



def test_bare_host_refuses_port_and_url_forms():
    """The reextract scripts build http://{host}:11434/... themselves, so a port here
    would silently produce a malformed URL. It must fail loud, not be stripped."""
    with _clean():
        assert resolve_ollama_bare_host("192.168.1.169") == "192.168.1.169"
        for bad in ("192.168.1.169:11435", "http://192.168.1.169:11434", "http://192.168.1.169:11434/v1"):
            msg = _raises(EndpointError, resolve_ollama_bare_host, bad)
            assert "bare host" in msg, msg


def test_bare_host_still_refuses_closed():
    """The port check must not shadow the closed-endpoint refusal."""
    with _clean():
        msg = _raises(ClosedEndpointError, resolve_ollama_bare_host, CLOSED_E)
        assert "gpu-servers.md" in msg, msg
        # URL form pointing at a closed endpoint: closed wins over the bare-host complaint.
        msg = _raises(ClosedEndpointError, resolve_ollama_bare_host, f"http://{CLOSED_F}:11434/v1")
        assert "gpu-servers.md" in msg, msg


def test_bare_host_requires_an_endpoint():
    with _clean():
        _raises(MissingEndpointError, resolve_ollama_bare_host)


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
