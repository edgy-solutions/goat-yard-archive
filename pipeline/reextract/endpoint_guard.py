"""Endpoint guard: NO default endpoint, and a hard refusal of the RESERVED pair (Chris's ruling, 2026-09-20).

    from endpoint_guard import resolve_host
    host = resolve_host(args.host, who="build_truthset")        # bare IP, e.g. "192.168.1.169"

WHY THIS EXISTS. Four scripts in this tree defaulted to `192.168.1.179` — endpoint **E**, which
`C:/Users/cnogr/git/gpu-servers.md` marks **Closed**: "No other project, agent, test, or ad hoc script may
send requests to .179 or .188." E and F are a characterized matched 7900 XTX pair serving goatyardarchive
PRODUCTION and goatyardtest through LiteLLM round-robin, reserved for output determinism and production
isolation. A stray request there does not just borrow a GPU: it can evict a pinned model (`keep_alive: -1`
only disables the idle timer — Ollama will still unload an idle pinned model when another request needs the
memory), which is a production incident caused by a test script.

No evidence any run actually used those defaults — every artifact that records a host records `.169`, and
the frozen run's model would not have fit beside E/F's ~10 GB of pinned weights in 24 GB. That is luck plus
an env var, not a guard. The env var had to be remembered *every single time*, and the failure mode of
forgetting was silent: the run works, it is simply pointed at production hardware.

TWO RULES, AND WHY BOTH. Removing the default is not enough on its own, and refusing .179/.188 is not
enough on its own.

  1. **No default, fail loud.** A default endpoint is a decision made once and then inherited by every
     future caller who never thought about it. `gpu-servers.md` says "Record the endpoint ID with any eval
     result" and "do not compare runs across endpoints as if they were identical" — an endpoint that was
     never chosen cannot be meaningfully recorded. Ruling 6 (2026-09-20) made this concrete: endpoint C did
     not reproduce the frozen run on 3 of 5 pages, and the frozen run's own `config_header` records no host
     at all, so the comparison needed a worktree and an inference rather than a lookup.
  2. **Hard-refuse the reserved pair.** Requiring an explicit host stops the silent inheritance, not a
     typo or a copied command line. The refusal is unconditional and has no override flag on purpose: an
     override is the env var again, one layer down.

SCOPE, HONESTLY. This refuses two addresses and requires a choice. It does NOT validate that the host you
did name is reachable, is the endpoint you meant, holds the model you want, or has the memory for it — see
`gpu-servers.md` for the assignment table (C `192.168.1.169:11434` is this project's testing endpoint; B
`192.168.1.100:11434` is open and may be offline; D `192.168.1.169:11435` is open for large models).
Nothing here inspects the port: a request aimed at D by port is a request to a different GPU, and only the
caller knows which was meant.

Born-test: `test_endpoint_guard.py`.

---

COLLAPSED INTO `pipeline/common/endpoint_guard.py` (Lane A, per ruling 2026-09-20). Everything above still
holds; what changed is where it lives. Two guard modules existed for about a day — this one and Lane A's —
and they agreed on the refusal but disagreed at the edges: this one did no name resolution, that one did.
The edge is exactly where a guard earns its keep, so two guards that differ there are worse than one.

This file stays, with every public name unchanged, because the six scripts in this tree import from it, and
because `test_endpoint_guard.py` imports `resolve_host`, `host_ip`, `RESERVED`, `EndpointMissing` and
`EndpointRefused` from it by name and must keep passing UNCHANGED. There is no second implementation below:
the names are re-exported from `common`, so the two trees cannot drift apart again.

BEHAVIOUR CHANGES, since the names did not change:
  - A hostname is now resolved and checked against the reserved pair. It previously was not, so a name
    pointing at .179/.188 would have passed.
  - A hostname that FAILS to resolve is now REFUSED (`UnresolvableEndpointError`, a subclass of
    `EndpointRefused`, so existing `except` clauses already catch it). Unknown is refused rather than
    assumed safe: a name that resolves from the run host but not from here would otherwise get through.
  - IP literals are never resolved, so nothing here makes a network call for an address, and the born-test
    stays offline. The resolver is injectable (`set_resolver`) so the name paths can be tested offline too.
"""

from __future__ import annotations

import os
import sys

# Import as `common.endpoint_guard`, with pipeline/ on the path, NOT as `pipeline.common...`:
# pipeline/__init__.py imports dagster_slack, which is not in the venv, so the package route
# fails before the guard is even loaded.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.endpoint_guard import (  # noqa: E402,F401
    RESERVED,
    ClosedEndpointError,
    EndpointError,
    EndpointMissing,
    EndpointRefused,
    MissingEndpointError,
    UnresolvableEndpointError,
    assert_endpoint_allowed,
    host_ip,
    resolve_host,
    resolve_ollama_bare_host,
    resolve_ollama_base_url,
    resolve_ollama_host,
    set_resolver,
)

__all__ = [
    "RESERVED",
    "ClosedEndpointError",
    "EndpointError",
    "EndpointMissing",
    "EndpointRefused",
    "MissingEndpointError",
    "UnresolvableEndpointError",
    "assert_endpoint_allowed",
    "host_ip",
    "resolve_host",
    "resolve_ollama_bare_host",
    "resolve_ollama_base_url",
    "resolve_ollama_host",
    "set_resolver",
]
