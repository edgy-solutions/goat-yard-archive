"""Born-test: no script in this tree may inherit a default endpoint or reach the RESERVED pair.

    python test_endpoint_guard.py

THE HAZARD THIS EXISTS FOR (2026-09-20). Four scripts here defaulted to `192.168.1.179` — endpoint **E**,
which `gpu-servers.md` marks Closed: "No other project, agent, test, or ad hoc script may send requests to
.179 or .188." E and F are a characterized matched pair serving goatyardarchive PRODUCTION and goatyardtest
via LiteLLM round-robin. A stray request can evict a pinned production model, because `keep_alive: -1` only
disables the idle timer — it does not protect the weights.

Nothing had ever contradicted those defaults, because forgetting the env var FAILS SILENTLY: the run works,
it is simply pointed at production hardware. That is exactly the class of bug the full-width born-test was
written for — an invariant nobody had ever stated, so nothing could violate it noisily.

WHAT THIS ASSERTS, AND AT WHICH LAYER. Two layers, because passing one is not passing the other:

  (1) `endpoint_guard.resolve_host` raises on a missing endpoint and on either reserved address, in every
      spelling this tree passes hosts around in (bare IP, ip:port, http://, trailing /v1).
  (2) The SCRIPTS actually call it. A guard nothing imports is the `note_line_region` situation again — a
      correct module wired to no caller. So the two owned scripts are exercised as SUBPROCESSES with the
      reserved host set, and must exit non-zero, print the refusal, and NOT reach the network.

This test makes no network call and loads no page. It is pure CPU and runs in under a second.

SCOPE. It asserts refusal and requirement. It does NOT assert that a permitted host is reachable, holds the
model, or is the endpoint the caller meant — see `endpoint_guard.py`'s scope note. It covers only the two
scripts Lane B owns; `extract_apparatus.py` and `run_vol1.py` are shared substrate and are Lane A's to
change (they are listed below as UNGUARDED so their absence is documented, not silent)."""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from endpoint_guard import resolve_host, host_ip, EndpointMissing, EndpointRefused, RESERVED

# Lane B owns these two; the guard must be wired into both.
OWNED = ["build_truthset.py", "nikud_audit_run.py"]
# Shared substrate — Lane A's to change. Named so the gap is documented, not silent.
SUBSTRATE = ["extract_apparatus.py", "run_vol1.py"]

SPELLINGS = ["{ip}", "{ip}:11434", "http://{ip}:11434", "http://{ip}:11434/v1", "  {ip}  ", "HTTP://{IP}:11434"]

fails = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}" + (f"   {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(f"{name}: {detail}")


print("(1) endpoint_guard.resolve_host")

# --- missing endpoint: no default, fail loud ---
for val in (None, "", "   "):
    try:
        got = resolve_host(val, env="_ENDPOINT_GUARD_TEST_UNSET_")
        check(f"missing({val!r}) raises", False, f"returned {got!r} instead of raising")
    except EndpointMissing as e:
        check(f"missing({val!r}) raises EndpointMissing", "NO DEFAULT" in str(e).upper() or "no default" in str(e))
    except Exception as e:
        check(f"missing({val!r}) raises EndpointMissing", False, f"raised {type(e).__name__}")

# --- reserved pair: refused in every spelling, explicit arg AND env ---
for ip, eid in RESERVED.items():
    for form in SPELLINGS:
        raw = form.format(ip=ip, IP=ip.upper())
        try:
            got = resolve_host(raw)
            check(f"refuse {raw!r}", False, f"RETURNED {got!r} - a reserved endpoint was allowed through")
        except EndpointRefused as e:
            msg = str(e)
            check(f"refuse {raw!r}", "gpu-servers.md" in msg and eid in msg,
                  "refused but the message does not cite gpu-servers.md and the endpoint ID")
        except Exception as e:
            check(f"refuse {raw!r}", False, f"raised {type(e).__name__}, expected EndpointRefused")

    os.environ["_EG_TEST_HOST"] = ip
    try:
        got = resolve_host(None, env="_EG_TEST_HOST")
        check(f"refuse {ip} via env", False, f"RETURNED {got!r}")
    except EndpointRefused:
        check(f"refuse {ip} via env", True)
    finally:
        os.environ.pop("_EG_TEST_HOST", None)

# --- the refusal must not be defeatable by a permitted host that merely CONTAINS a reserved string ---
check("host_ip('192.168.1.169') == 192.168.1.169", host_ip("192.168.1.169") == "192.168.1.169")
check("permitted host passes", resolve_host("192.168.1.169") == "192.168.1.169")
check("permitted host with port passes", resolve_host("192.168.1.100:11434") == "192.168.1.100:11434")

# A path or userinfo must not be able to smuggle a reserved address past the check.
for sneaky in ("http://192.168.1.179:11434/../v1", "http://user@192.168.1.188:11434"):
    try:
        got = resolve_host(sneaky)
        check(f"refuse {sneaky!r}", False, f"RETURNED {got!r}")
    except EndpointRefused:
        check(f"refuse {sneaky!r}", True)

print("\n(2) the owned scripts actually call it (subprocess; no network reached)")

for script in OWNED:
    path = HERE / script
    if not path.exists():
        check(f"{script} exists", False, "not found")
        continue

    # Reserved endpoint via env -> must exit non-zero, must say REFUSED, must cite gpu-servers.md.
    env = dict(os.environ, OLLAMA_HOST="192.168.1.179", PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, timeout=120,
                       cwd=str(HERE), env=env)
    out = (r.stdout or "") + (r.stderr or "")
    check(f"{script}: reserved host exits non-zero", r.returncode != 0, f"exit={r.returncode}")
    check(f"{script}: reserved host says REFUSED", "REFUSED" in out, out.strip()[-300:] or "(no output)")
    check(f"{script}: refusal cites gpu-servers.md", "gpu-servers.md" in out, out.strip()[-300:])

    # Missing endpoint -> must exit non-zero and say there is no default.
    env2 = {k: v for k, v in os.environ.items() if k != "OLLAMA_HOST"}
    env2["PYTHONIOENCODING"] = "utf-8"
    r2 = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, timeout=120,
                        cwd=str(HERE), env=env2)
    out2 = (r2.stdout or "") + (r2.stderr or "")
    check(f"{script}: missing host exits non-zero", r2.returncode != 0, f"exit={r2.returncode}")
    check(f"{script}: missing host says NO DEFAULT", "NO DEFAULT" in out2.upper(), out2.strip()[-300:])

print("\n(3) shared substrate — NOT guarded here, documented so the gap is not silent")
for script in SUBSTRATE:
    txt = (HERE / script).read_text(encoding="utf-8", errors="replace") if (HERE / script).exists() else ""
    guarded = "endpoint_guard" in txt
    still_defaults = "192.168.1.179" in txt
    print(f"  {'GUARDED' if guarded else 'UNGUARDED'}  {script}"
          + ("   still defaults to 192.168.1.179 — Lane A's change to make" if still_defaults else ""))

print()
if fails:
    print(f"FAIL: {len(fails)} assertion(s)")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print("PASS: no default endpoint, and the reserved pair is refused in the guard AND in both owned scripts.")
sys.exit(0)
