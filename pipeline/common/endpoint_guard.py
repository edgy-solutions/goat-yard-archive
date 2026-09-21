"""One place that decides which Ollama endpoint a script is allowed to talk to.

Authority: `gpu-servers.md`. Endpoints **E (192.168.1.179:11434)** and
**F (192.168.1.188:11434)** are CLOSED — "No other project, agent, test, or ad hoc
script may send requests to .179 or .188."

Two separate jobs, and the second is the one that matters:

1. **No default.** An endpoint must be supplied — explicitly, or through `OLLAMA_HOST` /
   `OLLAMA_BASE_URL`. Absent, this raises. Before this module, six scripts in
   `pipeline/reextract/` carried `default=os.getenv("OLLAMA_HOST", "192.168.1.179")`, which
   means running one with no arguments on a clean shell sent traffic to a closed production
   endpoint and printed nothing to say so. The convenient path was the unsafe one.

2. **Hard refusal, regardless of how the endpoint arrived.** A closed endpoint is refused
   even when passed deliberately on the command line. This is deliberately not overridable:
   requiring an explicit endpoint fixes only the *accident*, and a guard that fires on the
   default but waves through `--host 192.168.1.179` is a guard against typos, not against
   reaching closed hardware. There is no force flag, and adding one would defeat the module.

Fail loud, never silently substitute. A refused or missing endpoint raises; it does not fall
back to a "safe" endpoint, because a silent redirect would send a run somewhere the operator
did not choose and the artifacts would record a host nobody selected.
"""

from __future__ import annotations

import os
import socket
from typing import Optional, Sequence
from urllib.parse import urlparse

# gpu-servers.md, verbatim identities. Bare IPs: the port is irrelevant to the refusal,
# since a closed machine is closed on every port.
CLOSED_ENDPOINTS = {
    "192.168.1.179": "E",
    "192.168.1.188": "F",
}

_CITATION = (
    "gpu-servers.md marks this endpoint CLOSED: \"No other project, agent, test, or ad hoc "
    "script may send requests to .179 or .188.\""
)

DEFAULT_ENV_VARS: Sequence[str] = ("OLLAMA_HOST", "OLLAMA_BASE_URL")


class EndpointError(RuntimeError):
    """Base for both failure modes, so a caller can catch either with one except."""


class ClosedEndpointError(EndpointError):
    """The endpoint requested is one gpu-servers.md marks closed."""


class MissingEndpointError(EndpointError):
    """No endpoint was supplied and there is deliberately no default."""


def _host_of(value: str) -> str:
    """Extract the bare host from a URL, a host:port pair, or a bare host.

    The refusal keys on the resolved host, not on string equality with a bare IP, so
    'http://192.168.1.179:11434/v1' and '192.168.1.179:11434' and '192.168.1.179' are all
    the same endpoint as far as this module is concerned.
    """
    v = (value or "").strip()
    if not v:
        return ""
    if "://" in v:
        return (urlparse(v).hostname or "").strip()
    # 'host:port' — but not a bare IPv6 literal, which we do not use here.
    head = v.split("/", 1)[0]
    if head.count(":") == 1:
        head = head.split(":", 1)[0]
    return head.strip()


def _closed_aliases(host: str) -> Optional[str]:
    """Return the closed IP a hostname resolves to, or None.

    A name pointing at closed hardware must be refused the same as the literal IP.
    Resolution failure is not treated as a refusal — an unresolvable name cannot reach
    anything, and failing the run on a DNS blip would be a worse error than the one being
    prevented. This is the module's one acknowledged hole: a name that resolves to a closed
    IP only from *another* host's DNS view would pass here.
    """
    try:
        _, _, addrs = socket.gethostbyname_ex(host)
    except (socket.gaierror, socket.herror, UnicodeError, OSError):
        return None
    for a in addrs:
        if a in CLOSED_ENDPOINTS:
            return a
    return None


def assert_endpoint_allowed(value: str, source: str = "endpoint") -> str:
    """Raise ClosedEndpointError if `value` names a closed endpoint. Return it unchanged.

    Usable on its own at any call site that already has an endpoint in hand.
    """
    host = _host_of(value)
    if not host:
        return value

    closed_ip = host if host in CLOSED_ENDPOINTS else _closed_aliases(host)
    if closed_ip:
        label = CLOSED_ENDPOINTS[closed_ip]
        via = "" if closed_ip == host else f" (the name {host!r} resolves to {closed_ip})"
        raise ClosedEndpointError(
            f"Refusing to use endpoint {label} = {closed_ip}{via}, supplied via {source}. "
            f"{_CITATION} "
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
        f"No Ollama endpoint supplied for {purpose}, and there is no default. "
        f"Pass one explicitly or set {' or '.join('$' + v for v in env_vars)}. "
        "Lane A's assigned endpoint is D = 192.168.1.169:11435; "
        f"{CLOSED_ENDPOINTS['192.168.1.179']} = 192.168.1.179 and "
        f"{CLOSED_ENDPOINTS['192.168.1.188']} = 192.168.1.188 are closed and will be refused. "
        "See gpu-servers.md."
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

    A value that already carries a scheme is returned as given (still guarded); a bare host
    or host:port is expanded with `scheme` and, when no port is present, `port`.
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
