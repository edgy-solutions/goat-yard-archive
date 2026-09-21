"""Run provenance header: every run records WHICH MACHINE produced it (Chris's ruling, 2026-09-20).

    from run_header import build_header, require_endpoint
    hdr = build_header(host=\n"192.168.1.169", model="qwen3.6-16k:35b", extra={"seam": "baml"})
    # -> endpoint_id "C", endpoint_host "192.168.1.169:11434", model_digest16, config_sha16

WHY THIS EXISTS. The frozen vol1 run is a **signed artifact and is not regenerable**: Chris adjudicated its
strings on 2026-09-06, and those signatures are the truth this lane scores against. Its `config_header`
records `git_head`, `profile_sha16`, `extractor` and `started` — **and no host**. On 2026-09-20 endpoint C
reproduced it on **2 of 5** truthset pages; the three differences were confined to Hebrew letters and
apostrophe style, with note counts, markers and structure unchanged. Today's C is self-deterministic (three
reads of each diverging page gave one output each), so the disagreement is a device/stack change — and
because the header records no host, establishing even that much took a git worktree and an inference rather
than a lookup.

`gpu-servers.md` already states the rule this implements: *"output at temperature 0 is only stable on the
same GPU architecture and backend. Record the endpoint ID with any eval result, and do not compare runs
across endpoints as if they were identical."* The frozen run predates that discipline. Nothing here can fix
it retroactively — **no artifact is re-scored and no signature is touched** — but no run after this one is
allowed to have the same gap.

WHAT GOES IN THE HASH, AND WHY THAT MATTERS. `config_sha16` covers the code commit, the profile bytes, the
model name, **the model digest from `/api/tags`**, and **the endpoint host:port**. Two runs with the same
hash claim to be the same pipeline on the same weights on the same machine. Leaving the machine out of the
hash is what let the frozen run and a fresh C run look like the same configuration when they are not.

  - **The model digest, not just the tag.** `qwen3.6-16k:35b` is a mutable pointer. A re-pull under the same
    tag changes the weights and nothing in the old header would have noticed. `/api/tags` reports a content
    digest; that is the thing that was actually run.
  - **host:PORT, not the bare IP.** Endpoints C and D are the same address on different ports —
    `192.168.1.169:11434` is the 32 GB discrete GPU, `:11435` is the Strix Halo iGPU. Recording the IP alone
    would make two different GPUs indistinguishable in the record.
  - **The endpoint ID is a convenience, not the record.** `ENDPOINT_IDS` is transcribed from
    `gpu-servers.md` and can go stale; an address that is not in it is recorded as `UNREGISTERED:<host:port>`
    rather than silently dropped. `endpoint_host` is the authoritative field.

NAME COLLISION, DELIBERATELY AVOIDED. Some existing headers in this tree use the key `endpoint` for the
Ollama API *path* (`/api/chat`, `/api/generate`). This module never writes that key: it writes
`endpoint_id` and `endpoint_host`, which are about the GPU server. Both meanings can coexist in one header.

SCOPE. This records what ran where. It does NOT make runs reproducible across endpoints, does not detect
that a model was evicted and reloaded mid-run, and does not know which GPU served a request when an address
could route to more than one (as C could before 2026-09-20). It records the address that was asked.

Born-test: `test_run_header.py`."""
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

DEFAULT_PORT = 11434
REF = "C:/Users/cnogr/git/gpu-servers.md"

# Transcribed from gpu-servers.md (last updated 2026-09-20). C and D differ ONLY by port.
ENDPOINT_IDS = {
    "192.168.1.126:11434": "A",
    "192.168.1.100:11434": "B",
    "192.168.1.169:11434": "C",
    "192.168.1.169:11435": "D",
    "192.168.1.179:11434": "E",
    "192.168.1.188:11434": "F",
}


class HeaderMissingEndpoint(RuntimeError):
    """A run artifact whose header cannot say which machine produced it. Not scoreable against another run."""


def normalize_hostport(host, port=None):
    """`192.168.1.169` -> `192.168.1.169:11434`; an explicit port in the string wins over `port`."""
    from endpoint_guard import host_ip
    raw = str(host).strip()
    ip = host_ip(raw)
    stripped = raw.split("//", 1)[-1].split("/", 1)[0]
    if stripped.count(":") == 1 and stripped.rsplit(":", 1)[1].isdigit():
        return f"{ip}:{stripped.rsplit(':', 1)[1]}"
    return f"{ip}:{port or DEFAULT_PORT}"


def endpoint_id(hostport):
    """The `gpu-servers.md` letter, or `UNREGISTERED:<host:port>` — never silently blank."""
    return ENDPOINT_IDS.get(hostport, f"UNREGISTERED:{hostport}")


def model_digest(hostport, model, timeout=15):
    """Content digest of the loaded weights from `/api/tags`, 16 hex chars.

    A metadata call, not inference. Returns `unavailable:<reason>` rather than raising: a header that says
    the digest could not be read is honest and still records the endpoint, whereas a run that dies because
    a metadata endpoint was slow has lost real work. The digest's absence is visible in the artifact."""
    try:
        import httpx
        r = httpx.get(f"http://{hostport}/api/tags", timeout=timeout)
        r.raise_for_status()
        for m in r.json().get("models", []):
            if m.get("name") == model or m.get("model") == model:
                d = str(m.get("digest", "")).replace("sha256:", "")
                return d[:16] if d else "unavailable:no-digest-field"
        return "unavailable:model-not-listed"
    except Exception as e:
        return f"unavailable:{type(e).__name__}"


def model_digests(hostport, models, timeout=15, digest_fn=None):
    """Digest per model for a run that calls more than one (the aperture harness calls qwen AND gemma).

    A multi-model run has no single set of weights, so `model` alone cannot identify it. The per-model map
    goes into the hash; collapsing it to one model would make two runs with a swapped witness hash alike."""
    fn = digest_fn or model_digest
    return {m: fn(hostport, m, timeout) if digest_fn is None else fn(hostport, m) for m in models}


def _git_head(where=None):
    try:
        return subprocess.check_output(
            ["git", "-C", str(where or Path(__file__).parent), "rev-parse", "HEAD"]).decode().strip()
    except Exception:
        return "unknown"


def _git_dirty(where=None):
    """Files modified or untracked relative to `git_head`, or `unknown`. Goes IN the hash.

    `git_head` alone is a lie whenever the tree is dirty: it names a commit, and the code that ran was
    something else. The n=19 local-arms run of 2026-09-20 is the worked example. Its header recorded
    `git_head 29f58c1` (committed 21:38:49); the run started at 22:01:26; the sealed carve-out that
    produced its n=19 truth set was not committed until 07:16:47 the next morning. Every SEALED_TRUTH
    read in that artifact executed code that was in no commit, and a reader doing `git checkout 29f58c1`
    to reproduce it gets the n=10 module and a different answer, silently.

    Returns the count and the paths (capped), not a boolean: "3 files dirty" is a footnote, "47 files
    dirty" means the commit hash in the header is decoration. `unknown` when git cannot be reached --
    distinguishable from `clean`, because not knowing is not the same as knowing it was clean."""
    root = str(where or Path(__file__).parent)
    try:
        out = subprocess.check_output(["git", "-C", root, "status", "--porcelain"]).decode()
    except Exception:
        return {"state": "unknown"}
    paths = [ln[3:].strip() for ln in out.splitlines() if ln.strip()]
    if not paths:
        return {"state": "clean"}
    return {"state": "dirty", "n": len(paths), "paths": sorted(paths)[:20]}


def config_sha16(fields):
    """Hash over the identity fields, machine included. Canonical JSON so key order cannot change it."""
    return hashlib.sha256(json.dumps(fields, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def build_header(host, model, profile_path=None, extra=None, identity_extra=None, port=None,
                 digest_fn=model_digest, kind="config_header"):
    """Build a run header that names the machine. `digest_fn` is injectable so the born-test needs no network.

    `identity_extra` goes INTO the hash; `extra` sits beside it and does not. The split is the point:
    born_test.py already hashed the BAML source because the prompt and output schema are part of the
    seam, and that discipline must survive this change rather than be flattened into it. Anything that
    would make two runs non-comparable belongs in `identity_extra`; run bookkeeping (page lists, counts)
    belongs in `extra`."""
    hostport = normalize_hostport(host, port)
    eid = endpoint_id(hostport)
    digest = digest_fn(hostport, model)
    prof = "absent"
    if profile_path:
        p = Path(profile_path)
        prof = hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else "missing"

    identity = {"git_head": _git_head(), "git_dirty": _git_dirty(), "profile_sha16": prof,
                "model": model, "model_digest16": digest, "endpoint_host": hostport, "endpoint_id": eid}
    if identity_extra:
        identity.update(identity_extra)
    hdr = dict(identity)
    hdr.update({"kind": kind, "config_sha16": config_sha16(identity),
                "endpoint_ref": REF, "started": time.strftime("%Y-%m-%dT%H:%M:%S")})
    if extra:
        for k, v in extra.items():
            if k in identity:
                raise ValueError(f"extra[{k!r}] would overwrite an identity field the hash is computed over")
            hdr[k] = v
    return hdr


def require_endpoint(header, where=""):
    """Raise unless the header names the machine. Call this before scoring one run against another.

    `UNREGISTERED:<host:port>` PASSES: an address absent from `gpu-servers.md` is still a recorded machine,
    and refusing it would push people back to recording nothing. A blank, missing, or placeholder value
    fails."""
    tag = f" ({where})" if where else ""
    if not isinstance(header, dict) or header.get("kind") != "config_header":
        raise HeaderMissingEndpoint(
            f"No config_header{tag}: a run artifact must open with one, and it must name the"
            f" machine that produced it.\n"
            f"  Every run records endpoint ID, host:port and model digest (Chris's ruling, 2026-09-20).\n"
            f"  See {REF}: record the endpoint ID with any eval result.")
    eid, host = header.get("endpoint_id"), header.get("endpoint_host")
    bad = {"", "unknown", "none", "null", "n/a", "?"}
    if not eid or str(eid).strip().lower() in bad or not host or str(host).strip().lower() in bad:
        raise HeaderMissingEndpoint(
            f"config_header{tag} does not name the machine: endpoint_id={eid!r} endpoint_host={host!r}.\n"
            f"  Every run records endpoint ID, host:port and model digest (Chris's ruling, 2026-09-20).\n"
            f"  The frozen 2026-09-06 run has this gap and is the reason for the rule: it is a SIGNED,\n"
            f"  non-regenerable artifact that endpoint C reproduces on only 2 of 5 pages, and its header\n"
            f"  cannot say what produced it. See {REF}: record the endpoint ID with any eval result.")
    return True


def read_header(path):
    """First record of a JSONL run artifact, or None. Reads one line — never the whole file."""
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    return json.loads(line)
                except Exception:
                    return None
    return None
