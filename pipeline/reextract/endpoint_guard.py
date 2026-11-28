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
`gpu-servers.md` for the assignment table (C `192.168.1.169:11434` is this project's testing endpoint;
D `192.168.1.169:11435` is open for large models).  B2 `.100` was listed here as "open and may be
offline" until 2026-11-28; it was RETIRED 2026-11-14 and the register's words are "Send nothing to
it", so naming it here was advertising a dead host -- and as B, which is a different dead machine.
Nothing here inspects the port: a request aimed at D by port is a request to a different GPU, and only the
caller knows which was meant.

Born-test: `test_endpoint_guard.py`."""
import os
import re

REF = "C:/Users/cnogr/git/gpu-servers.md"

# The Closed pair. Keys are bare IPs; the value is the endpoint ID as `gpu-servers.md` names it.
RESERVED = {"192.168.1.179": "E", "192.168.1.188": "F"}

# Endpoints this project may use, quoted for the error message so the fix is in the failure.
# .100 was REMOVED from this text on 2026-11-28.  BASIS: the register REF names below --
# gpu-servers.md :104, "192.168.1.100 ... IS RETIRED. Send nothing to it.", and :27, where
# B2 (the Windows VM on landinator at .100) is retired 2026-11-14 and ".100 is hard-refused
# in code (whole host, any port), born-tested".
#
# This string is interpolated into the REFUSED path below, so it handed a retired host to an
# operator at the exact moment they were refused and looking for a replacement -- the worst
# position for this defect.  It also mislabelled the host: .100 is B2, not B (B was the RX
# 7900 XTX in a Thunderbolt enclosure on ai1, retired 2026-11-13 -- a different dead
# machine).  An endpoint label is a role, not a host.
#
# NO replacement host is suggested.  Which hosts are endorsed is an open question with Chris
# (allow-list vs this lane's recorded "UNREGISTERED passes on purpose" design point), and
# naming one would pre-empt it.  Removing a retired host does not: both readings forbid a
# host the register says to send nothing to appearing in the text a refusal prints.
SUGGESTED = "192.168.1.169  (C, ai2 32 GB — this project's assigned testing endpoint)"


class EndpointRefused(RuntimeError):
    """Raised for a reserved address. Distinct from the missing-host case so a caller can tell them apart."""


class EndpointMissing(RuntimeError):
    """Raised when no endpoint was named. There is no default and there will not be one."""


def host_ip(value):
    """Bare IP/hostname from any of the forms this tree passes around.

    Accepts `192.168.1.169`, `192.168.1.169:11434`, `http://192.168.1.169:11434`, and the same with a
    trailing `/v1` or other path. Returns the host part, lowercased and stripped. The refusal must not be
    defeatable by the spelling of the URL, which is why it never string-matches the raw value."""
    v = str(value).strip()
    v = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", v)   # scheme
    v = v.split("/", 1)[0]                               # path
    v = v.split("@")[-1]                                 # userinfo, if anyone ever adds one
    if v.startswith("["):                                # bracketed IPv6
        return v[1:].split("]", 1)[0].lower()
    return v.rsplit(":", 1)[0].lower() if v.count(":") == 1 else v.lower()


def resolve_host(explicit=None, env="OLLAMA_HOST", who=None):
    """Return the endpoint to use, or raise. There is no default.

    `explicit` is the CLI value (or None); `env` is consulted only if `explicit` is empty. Either way the
    endpoint has to have been *named by a human at the call site*, which is the whole point."""
    tag = f" [{who}]" if who else ""
    raw = explicit if (explicit is not None and str(explicit).strip()) else os.getenv(env)

    if raw is None or not str(raw).strip():
        raise EndpointMissing(
            f"No Ollama endpoint named{tag}, and this script has NO DEFAULT on purpose.\n"
            f"  Pass --host, or set {env}.\n"
            f"  Endpoints this project may use (see {REF}):\n"
            f"    {SUGGESTED}\n"
            f"  Record the endpoint ID with any result: output at temperature 0 is only stable on the\n"
            f"  same GPU architecture and backend, and runs from different endpoints are not comparable.")

    ip = host_ip(raw)
    if ip in RESERVED:
        raise EndpointRefused(
            f"REFUSED{tag}: {raw!r} resolves to {ip}, endpoint {RESERVED[ip]} — RESERVED.\n"
            f"  {REF} marks E (192.168.1.179) and F (192.168.1.188) Closed: a characterized matched\n"
            f"  7900 XTX pair serving goatyardarchive PRODUCTION and goatyardtest via LiteLLM\n"
            f"  round-robin. \"No other project, agent, test, or ad hoc script may send requests to\n"
            f"  .179 or .188.\"\n"
            f"  A request here can evict a pinned production model: keep_alive -1 only disables the idle\n"
            f"  timer, it does not protect the weights.\n"
            f"  Use instead:\n"
            f"    {SUGGESTED}\n"
            f"  There is no override flag. If production work genuinely needs to run here, it does not\n"
            f"  run from this tree.")

    return str(raw).strip()
