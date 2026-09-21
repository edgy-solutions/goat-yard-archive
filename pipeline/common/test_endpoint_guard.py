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
# --------------------------------------------------------------------------
# 4. Name resolution: injectable, and failure is a refusal (ruling 2026-09-20)
# --------------------------------------------------------------------------

from common.endpoint_guard import (  # noqa: E402
    RESERVED,
    EndpointRefused,
    UnresolvableEndpointError,
    host_ip,
    resolve_host,
    set_resolver,
)


@contextmanager
def _resolver(fn):
    """Swap the name resolver for the duration of a test, restoring exactly."""
    prev = set_resolver(fn)
    try:
        yield
    finally:
        set_resolver(prev)


def test_name_resolving_to_reserved_is_refused():
    """The hole the old module documented and left open. A name is not a loophole."""
    with _clean(), _resolver(lambda h: ["10.0.0.5", CLOSED_E]):
        msg = _raises(ClosedEndpointError, resolve_ollama_host, "gpu-box.local")
        assert "192.168.1.179" in msg, msg
        assert "gpu-box.local" in msg, msg          # says HOW it got there
        assert "gpu-servers.md" in msg, msg


def test_resolution_failure_is_a_refusal_not_a_pass():
    """Unknown is refused, not assumed safe.

    The old module returned "not closed" when DNS failed, reasoning that an unresolvable name
    cannot reach anything. That is wrong in the case that matters: a name resolvable from the
    run host but not from here would pass. This is the ruling, asserted.
    """
    def boom(h):
        raise OSError("no such host")

    with _clean(), _resolver(boom):
        msg = _raises(UnresolvableEndpointError, resolve_ollama_host, "unknown.local")
        assert "REFUSED" in msg, msg
        assert "could not be resolved" in msg, msg
        assert "not overridable" in msg, msg


def test_resolution_failure_is_caught_by_existing_except_clauses():
    """UnresolvableEndpointError must be catchable as EndpointRefused.

    pipeline/reextract/ scripts catch (EndpointMissing, EndpointRefused). If the new error
    were a sibling rather than a subclass, they would traceback instead of exiting 2 with a
    message - a guard that fires as a crash.
    """
    def boom(h):
        raise OSError("no such host")

    with _clean(), _resolver(boom):
        try:
            resolve_host("unknown.local", who="probe")
        except EndpointRefused as e:
            assert "REFUSED" in str(e), str(e)
        else:
            raise AssertionError("an unresolvable name was allowed through")


def test_ip_literals_never_hit_the_resolver():
    """The property that keeps every born-test offline: an address needs no lookup."""
    calls = []

    def tripwire(h):
        calls.append(h)
        raise AssertionError(f"resolver called for the IP literal {h!r}")

    with _clean(), _resolver(tripwire):
        assert resolve_ollama_host("192.168.1.169") == "192.168.1.169"
        _raises(ClosedEndpointError, resolve_ollama_host, CLOSED_E)   # refused without DNS
        assert calls == [], calls


def test_a_resolver_cannot_launder_a_reserved_ip():
    """set_resolver is a test seam, not an escape hatch: the literal check runs first."""
    with _clean(), _resolver(lambda h: ["10.0.0.5"]):
        _raises(ClosedEndpointError, resolve_ollama_host, CLOSED_E)
        _raises(ClosedEndpointError, resolve_ollama_host, f"http://{CLOSED_F}:11434/v1")


# --------------------------------------------------------------------------
# 5. The cross-lane contract: pipeline/reextract/test_endpoint_guard.py greps
#    subprocess output for these exact tokens. Reword the messages and Lane B's
#    born-test fails in a way that looks like a wiring regression. Asserted here
#    so it cannot be broken silently from this side.
# --------------------------------------------------------------------------

def test_refusal_message_contains_the_literal_token_REFUSED():
    with _clean():
        msg = _raises(ClosedEndpointError, resolve_host, CLOSED_E, who="probe")
        assert "REFUSED" in msg, msg
        assert "gpu-servers.md" in msg, msg


def test_missing_message_reads_as_NO_DEFAULT_in_both_spellings():
    with _clean():
        msg = _raises(MissingEndpointError, resolve_host, None, "_UNSET_VAR_", "probe")
        assert "no default" in msg, msg            # Lane A's spelling
        assert "NO DEFAULT" in msg.upper(), msg    # Lane B's spelling


def test_reextract_names_are_the_same_objects_not_a_second_implementation():
    """If the shim ever grows its own copy, this fails."""
    import sys as _sys
    _sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reextract"))
    import endpoint_guard as reextract_guard

    from common import endpoint_guard as common_guard

    assert reextract_guard.resolve_host is common_guard.resolve_host
    assert reextract_guard.host_ip is common_guard.host_ip
    assert reextract_guard.RESERVED is common_guard.RESERVED
    assert reextract_guard.EndpointRefused is common_guard.ClosedEndpointError
    assert reextract_guard.EndpointMissing is common_guard.MissingEndpointError


def test_host_ip_parses_every_spelling_this_tree_uses():
    for raw, want in [
        ("192.168.1.179", "192.168.1.179"),
        ("192.168.1.179:11434", "192.168.1.179"),
        ("http://192.168.1.179:11434", "192.168.1.179"),
        ("http://192.168.1.179:11434/v1", "192.168.1.179"),
        ("  192.168.1.179  ", "192.168.1.179"),
        ("HTTP://192.168.1.179:11434", "192.168.1.179"),
        ("http://user@192.168.1.188:11434", "192.168.1.188"),
        ("http://192.168.1.179:11434/../v1", "192.168.1.179"),
    ]:
        assert host_ip(raw) == want, f"{raw!r} -> {host_ip(raw)!r}, wanted {want!r}"


def test_reserved_table_is_exactly_the_pair_gpu_servers_names():
    assert RESERVED == {"192.168.1.179": "E", "192.168.1.188": "F"}, RESERVED


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
