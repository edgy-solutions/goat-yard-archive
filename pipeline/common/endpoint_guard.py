"""The one place that decides which Ollama endpoint a script is allowed to talk to.

Authority: `gpu-servers.md`. Endpoints **E (192.168.1.179:11434)** and
**F (192.168.1.188:11434)** are RESERVED/CLOSED — "No other project, agent, test, or ad hoc
script may send requests to .179 or .188." They are a characterized matched 7900 XTX pair
serving goatyardarchive PRODUCTION and goatyardtest via LiteLLM round-robin; a stray request
can evict a pinned production model, because `keep_alive: -1` only disables the idle timer —
it does not protect the weights.

Three jobs, and the second and third are the ones that matter:

1. **No default.** An endpoint must be supplied — explicitly, or through an env var. Absent,
   this raises. Before this module, six scripts in `pipeline/reextract/` carried
   `default=os.getenv("OLLAMA_HOST", "192.168.1.179")`, so running one with no arguments on a
   clean shell sent traffic to a closed production endpoint and printed nothing to say so.
   The convenient path was the unsafe one, and forgetting the env var failed *silently*: the
   run worked, it was simply pointed at production hardware.

2. **Hard refusal, regardless of how the endpoint arrived.** A reserved endpoint is refused
   even when passed deliberately on the command line. Deliberately not overridable: requiring
   an explicit endpoint fixes only the *accident*, and a guard that fires on the default but
   waves through `--host 192.168.1.179` is a guard against typos, not against reaching closed
   hardware. There is no force flag, and adding one would defeat the module.

3. **A name that cannot be verified is refused too.** Hostnames are resolved and checked
   against the reserved pair, and — per ruling, 2026-09-20 — *resolution failure is itself a
   refusal*. The earlier version returned "not closed" when DNS failed, which meant an
   unresolvable name was waved through on the theory that it could not reach anything anyway.
   That reasoning is wrong in the case that matters: a name resolvable from the *run host* but
   not from here would pass. Unknown is now refused, not assumed safe.

   IP literals are never resolved — an address needs no lookup — which is also what keeps the
   born-tests offline. Only names hit the resolver, and the resolver is injectable
   (`set_resolver`) so tests can exercise the name paths without a network.

Fail loud, never silently substitute. A refused, missing or unverifiable endpoint raises; it
does not fall back to a "safe" endpoint, because a silent redirect would send a run somewhere
the operator did not choose and the artifacts would record a host nobody selected.

SCOPE — what this does NOT assert: that a permitted endpoint is reachable, that it holds the
model you want, or that it is the endpoint you meant. It refuses the known-bad and the
unverifiable. Everything else is the caller's problem.

Two call-name families are exported on purpose. `resolve_ollama_*` is this module's own;
`resolve_host` / `host_ip` / `RESERVED` / `EndpointRefused` / `EndpointMissing` are the names
`pipeline/reextract/` was written against (Lane B's born-test imports them by those names and
must keep passing unchanged). They are the same code, not a second implementation.
"""

from __future__ import annotations

import os
import re
import socket
from typing import Callable, List, Optional, Sequence
from urllib.parse import urlparse

# gpu-servers.md, verbatim identities. Bare IPs: the port is irrelevant to the refusal,
# since a closed machine is closed on every port.
CLOSED_ENDPOINTS = {
    "192.168.1.179": "E",
    "192.168.1.188": "F",
}

# The name pipeline/reextract/ uses for the same table.
RESERVED = CLOSED_ENDPOINTS

_CITATION = (
    "gpu-servers.md marks this endpoint CLOSED: \"No other project, agent, test, or ad hoc "
    "script may send requests to .179 or .188.\""
)

DEFAULT_ENV_VARS: Sequence[str] = ("OLLAMA_HOST", "OLLAMA_BASE_URL")

_IPV4 = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


class EndpointError(RuntimeError):
    """Base for every failure mode, so a caller can catch them all with one except."""


class ClosedEndpointError(EndpointError):
    """The endpoint requested is one gpu-servers.md marks closed."""


class MissingEndpointError(EndpointError):
    """No endpoint was supplied and there is deliberately no default."""


class UnresolvableEndpointError(ClosedEndpointError):
    """A hostname that could not be resolved, and so could not be cleared.

    Subclasses ClosedEndpointError on purpose: every existing call site catches that, and the
    ruling is that an unverifiable endpoint is refused. The message says plainly that this is
    a refusal for lack of evidence, not a claim that the host IS reserved.
    """


# The reserved-pair names (Lane B's spelling). Same exceptions, not parallel ones.
EndpointRefused = ClosedEndpointError
EndpointMissing = MissingEndpointError


# --------------------------------------------------------------------------
# Resolution, injectable so the born-tests stay offline
# --------------------------------------------------------------------------

def _dns_resolver(host: str) -> List[str]:
    """Real DNS. Raises on failure; the caller turns that into a refusal."""
    return socket.gethostbyname_ex(host)[2]


_RESOLVER: Callable[[str], List[str]] = _dns_resolver


def set_resolver(fn: Optional[Callable[[str], List[str]]]) -> Callable[[str], List[str]]:
    """Swap the name resolver; returns the previous one so a test can restore it.

    This exists so the name paths can be tested without a network, NOT as an escape hatch:
    a resolver cannot make a reserved IP acceptable, because the literal-IP check runs first
    and does not consult it. Passing None restores real DNS.
    """
    global _RESOLVER
    prev = _RESOLVER
    _RESOLVER = _dns_resolver if fn is None else fn
    return prev


def host_ip(value: str) -> str:
    """The bare host from a URL, a host:port pair, or a bare host.

    The refusal keys on the parsed host, not on string equality with a bare IP, so
    'http://192.168.1.179:11434/v1', 'HTTP://192.168.1.179:11434',
    'http://user@192.168.1.179:11434', '192.168.1.179:11434' and '192.168.1.179' are all the
    same endpoint as far as this module is concerned. Spellings cannot smuggle one through.
    """
    v = (value or "").strip()
    if not v:
        return ""
    if "://" in v:
        try:
            return (urlparse(v).hostname or "").strip()
        except ValueError:
            return ""
    # 'host:port' or 'host/path' — but not a bare IPv6 literal, which we do not use here.
    head = v.split("/", 1)[0]
    if "@" in head:
        head = head.rsplit("@", 1)[1]
    if head.count(":") == 1:
        head = head.split(":", 1)[0]
    return head.strip()


# Kept as the old private name; some call sites import it.
_host_of = host_ip


def _reserved_ip_for(host: str) -> Optional[str]:
    """The reserved IP this host is, or resolves to. Raises if a name cannot be cleared."""
    if host in CLOSED_ENDPOINTS:
        return host
    if _IPV4.match(host):
        # An address needs no lookup, and refusing to resolve it is what keeps tests offline.
        return None
    try:
        addrs = _RESOLVER(host)
    except Exception as e:
        raise UnresolvableEndpointError(
            f"REFUSED: the endpoint name {host!r} could not be resolved ({type(e).__name__}: {e}), "
            "so it could not be checked against the reserved pair. An endpoint that cannot be "
            "verified is refused rather than assumed safe: a name that resolves from the run "
            "host but not from here would otherwise pass. "
            f"{_CITATION} "
            "Pass an IP address, or fix resolution. This refusal is not overridable."
        ) from e
    for a in addrs:
        if a in CLOSED_ENDPOINTS:
            return a
    return None


def assert_endpoint_allowed(value: str, source: str = "endpoint") -> str:
    """Raise if `value` names a reserved or unverifiable endpoint. Return it unchanged."""
    host = host_ip(value)
    if not host:
        return value

    closed_ip = _reserved_ip_for(host)
    if closed_ip:
        label = CLOSED_ENDPOINTS[closed_ip]
        via = "" if closed_ip == host else f" (the name {host!r} resolves to {closed_ip})"
        raise ClosedEndpointError(
            f"REFUSED: endpoint {label} = {closed_ip}{via}, supplied via {source}. "
            f"{_CITATION} "
            "E and F are a matched pair serving goatyardarchive PRODUCTION and goatyardtest via "
            "LiteLLM round-robin; a stray request can evict a pinned production model, because "
            "keep_alive: -1 only disables the idle timer - it does not protect the weights. "
            "This refusal is not overridable; choose an open endpoint (D = 192.168.1.169:11435 "
            "for Lane A) instead."
        )
    return value


def resolve_ollama_host(
    explicit: Optional[str] = None,
    *,
    env_vars: Sequence[str] = DEFAULT_ENV_VARS,
    purpose: str = "this script",
) -> str:
    """The endpoint to use, or an exception. Never a default.

    Order: `explicit` (a --host argument), then each name in `env_vars`. An endpoint found
    anywhere in that order is still put through `assert_endpoint_allowed`.
    """
    candidates = [(explicit, "the --host argument")]
    candidates += [(os.getenv(v), f"${v}") for v in env_vars]

    for value, source in candidates:
        if value and value.strip():
            return assert_endpoint_allowed(value.strip(), source)

    raise MissingEndpointError(
        f"No Ollama endpoint supplied for {purpose}, and there is no default on purpose. "
        f"Pass one explicitly or set {' or '.join('$' + v for v in env_vars)}. "
        "Lane A's assigned endpoint is D = 192.168.1.169:11435; "
        f"{CLOSED_ENDPOINTS['192.168.1.179']} = 192.168.1.179 and "
        f"{CLOSED_ENDPOINTS['192.168.1.188']} = 192.168.1.188 are closed and will be refused. "
        "See gpu-servers.md."
    )


def resolve_host(
    explicit: Optional[str] = None,
    env: str = "OLLAMA_HOST",
    who: Optional[str] = None,
) -> str:
    """`pipeline/reextract/`'s spelling: one env var, a `who` label, the value as given.

    Kept byte-compatible with the signature those scripts and Lane B's born-test call. It is a
    thin adapter over `resolve_ollama_host`, not a second implementation, so the refusal rules
    cannot drift between the two trees.
    """
    return resolve_ollama_host(
        explicit,
        env_vars=(env,),
        purpose=f"[{who}]" if who else "this script",
    )


def resolve_ollama_base_url(
    explicit: Optional[str] = None,
    *,
    port: int = 11434,
    scheme: str = "http",
    env_vars: Sequence[str] = DEFAULT_ENV_VARS,
    purpose: str = "this script",
) -> str:
    """`resolve_ollama_host` as a base URL, for call sites that want one.

    A value that already carries a scheme is returned as given (still guarded); a bare host or
    host:port is expanded with `scheme` and, when no port is present, `port`.
    """
    value = resolve_ollama_host(explicit, env_vars=env_vars, purpose=purpose)
    if "://" in value:
        return value.rstrip("/")
    head = value.split("/", 1)[0]
    if head.count(":") == 1:
        return f"{scheme}://{value}".rstrip("/")
    return f"{scheme}://{value}:{port}"


def resolve_ollama_bare_host(
    explicit: Optional[str] = None,
    *,
    env_vars: Sequence[str] = DEFAULT_ENV_VARS,
    purpose: str = "this script",
) -> str:
    """An endpoint for call sites that hardcode the port, e.g. f"http://{host}:11434/...".

    Those call sites cannot accept a host:port pair — "192.168.1.169:11435" would build
    "http://192.168.1.169:11435:11434", a malformed URL that fails confusingly at connect
    time. So a port here is refused with an explanation rather than silently stripped:
    stripping it would send the run to :11434 on a machine where the operator asked for a
    different port, and the artifacts would record a host that was never chosen.

    Note this means such call sites can only reach port 11434, which excludes endpoint
    D (192.168.1.169:11435). Widening them is a change to the URL construction in
    pipeline/reextract/, shared with Lane B, and is deliberately not done here.
    """
    value = resolve_ollama_host(explicit, env_vars=env_vars, purpose=purpose)
    head = value.split("/", 1)[0]
    if "://" in value or head.count(":") == 1:
        raise EndpointError(
            f"{purpose} builds its own URL as http://<host>:11434/..., so it needs a bare "
            f"host, not {value!r}. Pass just the address (e.g. 192.168.1.169). "
            "A host:port or URL form cannot be used here; note this also means this call "
            "site cannot reach endpoint D on port 11435."
        )
    return value
