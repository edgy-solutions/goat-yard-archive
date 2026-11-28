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
scripts Lane B owns.  Everything else is MEASURED and not asserted, and section (3) says so in those
words: a derived scan over every .py under the repo root classifies each file that names a closed
address, prints the whole table, and RATCHETS -- a NEW unguarded addressing site fails the run, while
the nine in the 2026-11-28 baseline do not, because none of them is Lane B's to edit.

WHY THE SCAN REPLACED A LIST (2026-11-28, A1's finding, accepted).  Until today this section printed two
hardcoded names, `extract_apparatus.py` and `run_vol1.py`, and called them the gap.  It asserted nothing --
no `check()` call -- and it was an allow-list of the call sites this lane happened to know: 2 of the 6
scripts that default to a closed endpoint and 0 of the 4 that hardcode one.  Lane B's own rule, broken in
Lane B's own test: count against a derived set, never a parity proxy; a probe that misses passes on
nothing.  The scan derives its forbidden set from `RESERVED`, imported from the guard, so it does not keep
a second copy of the table it checks against."""
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from endpoint_guard import resolve_host, host_ip, EndpointMissing, EndpointRefused, RESERVED

# Lane B owns these two; the guard must be wired into both.
OWNED = ["build_truthset.py", "nikud_audit_run.py"]
# RETIRED, from the register this guard cites (gpu-servers.md): B2 at .100 was retired
# 2026-11-14 with the words "Send nothing to it", and B at .198-in-an-enclosure 2026-11-13.
# A reserved address legitimately appears in a refusal table; a RETIRED one has no reason to
# appear in this lane's code at all. .100 sat in this guard's own remedy text for fourteen
# days because nothing asserted this.
RETIRED = {"192.168.1.100": "B2 (retired 2026-11-14, gpu-servers.md:27 and :104)"}

# The repo root, derived rather than assumed: this file is at <root>/pipeline/reextract/.
ROOT = HERE.parents[1]
SKIP_DIRS = ("baml_client", ".git", ".venv", "__pycache__", "node_modules")

# A line ADDRESSES an endpoint when a closed IP appears in a construct that aims traffic at
# it. Positively identified, because the negative ("a line that is not a refusal table") is
# not mechanically decidable and would silently reclassify the tables this module needs.
ADDRESSING = re.compile(r"getenv|default\s*=|api_base|base_url|OLLAMA_URL|"
                        r"\bHOST\s*=|\bhost\s*=|\burl\s*=", re.I)

# REGISTERED BASELINE, measured on apparatus-next 2026-11-28, derived by the scan below and
# pasted here. This is a RATCHET, not a guard: it fails when a NEW unguarded addressing site
# appears, and it does not make the listed ones safe. Every entry is shared substrate or
# another lane's tree -- none is Lane B's to edit -- and the list is the deliverable, not a
# clean bill. A1 measured 6 defaulting scripts on `main`; two of those six, build_truthset.py
# and nikud_audit_run.py, are guarded HERE and still default on main, so main is worse than
# this branch on exactly the two files this lane fixed.
BASELINE_UNGUARDED = {
    "evals/e6_entity_lookup_probe/e6_near_vector_probe.py",
    "evals/e6_entity_lookup_probe/e6b_post_fix_validation.py",
    "evals/e7_query_expansion_probe/e7_1_expansion_coverage.py",
    "pipeline/reextract/extract_apparatus.py",
    "pipeline/reextract/run_vol1.py",
    "pipeline/reextract/two_model_corpus.py",
    "pipeline/reextract/vol7_run.py",
    "pipeline/scripts/normalize_markdown.py",
    "test/test_litellm_proxy.py",
}

SPELLINGS = ["{ip}", "{ip}:11434", "http://{ip}:11434", "http://{ip}:11434/v1", "  {ip}  ", "HTTP://{IP}:11434"]

fails = []
checks_run = 0


def check(name, cond, detail=""):
    global checks_run
    checks_run += 1
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
# This fixture was `192.168.1.100:11434` from 2026-09-20 until 2026-11-28.  It was correct when
# written -- .100 was B2, open and in service -- and became wrong on 2026-11-14, when the
# register retired the host with the words "Send nothing to it".  Nothing noticed for fourteen
# days, because this suite went on PASSING: it was asserting that the retired host resolves.
# Had anyone hard-refused .100 in endpoint_guard.py -- which gpu-servers.md:27 asserts is
# already true of this project's code -- this check would have gone red and reported the FIX as
# the breakage.  A test can defend a defect.  Caught by the retired-host assertion in section
# (3) below, minutes after that assertion was written, which is the only reason this is a
# comment and not still a green check.
#
# What the check is FOR is that a port-bearing spelling survives the refusal logic, so any
# registered non-reserved host serves.  .169:11435 is D, registered and assigned, and differs
# from the line above only by port -- the C/D distinction the port handling exists for.  A
# REGISTERED host was chosen so this pre-empts nothing in the open allow-list question.
check("permitted host with port passes", resolve_host("192.168.1.169:11435") == "192.168.1.169:11435")

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

print("\n(3) DERIVED scan: every .py under the repo root naming a closed endpoint")
print("    The forbidden set is RESERVED, imported from the guard -- the scan does not keep\n    its own copy of the table it is checking against.")

addresses, advertises_retired, references = {}, {}, {}
scanned = 0
for py in sorted(ROOT.rglob("*.py")):
    rel = py.relative_to(ROOT).as_posix()
    if any(part in SKIP_DIRS for part in py.parts):
        continue
    scanned += 1
    try:
        txt = py.read_text(encoding="utf-8", errors="replace")
    except OSError:
        continue
    guarded = "endpoint_guard" in txt
    for n, line in enumerate(txt.split("\n"), 1):
        for ip in list(RESERVED) + list(RETIRED):
            if ip not in line:
                continue
            stripped = line.strip()
            # The RETIRED table must name the retired host, for the same reason the guard's
            # RESERVED table must name the reserved pair: it IS the authority this scan reads.
            # Exempted by exact construct so the exemption cannot widen quietly.
            if stripped.startswith("RETIRED = {"):
                continue
            if ip in RETIRED:
                # A comment citing the retirement is the one legitimate mention.
                if not stripped.startswith("#"):
                    advertises_retired.setdefault(rel, []).append((n, ip, stripped[:90]))
            elif ADDRESSING.search(line) and not stripped.startswith("#"):
                if not guarded:
                    addresses.setdefault(rel, []).append((n, ip, stripped[:90]))
            else:
                references.setdefault(rel, 0)
                references[rel] += 1

print(f"    scanned {scanned} .py files under {ROOT}")
print(f"\n  ADDRESSES a closed endpoint and does NOT import the guard ({len(addresses)} files):")
for rel in sorted(addresses):
    for n, ip, snippet in addresses[rel]:
        print(f"    UNGUARDED  {rel}:{n}  [{RESERVED[ip]}]  {snippet}")
print(f"\n  mentions a closed address in a table, fixture or prose ({len(references)} files,"
      f" informational -- a refusal table MUST name them):")
for rel in sorted(references):
    print(f"    ref  {rel}  ({references[rel]} line(s))")

# (3a) THE RATCHET. A new unguarded addressing site fails the run. Fixing one is reported,
# not failed, with the instruction to re-register -- a baseline nobody updates is a comment.
new_sites = sorted(set(addresses) - BASELINE_UNGUARDED)
fixed_sites = sorted(BASELINE_UNGUARDED - set(addresses))
check("no NEW unguarded addressing site since the 2026-11-28 baseline",
      not new_sites, f"new: {new_sites}")
if fixed_sites:
    print(f"\n  NOTE: {len(fixed_sites)} baseline site(s) no longer address a closed endpoint:")
    for rel in fixed_sites:
        print(f"    fixed  {rel}   -- remove it from BASELINE_UNGUARDED")
print(f"\n  ratchet: {len(addresses)} unguarded addressing file(s); baseline is"
      f" {len(BASELINE_UNGUARDED)}. This is a MEASUREMENT with a ratchet, not a guard:"
      f" nothing here stops a send from any listed file.")

# (3b) THE PROPERTY THAT WAS MISSING FOR FOURTEEN DAYS. A reserved address belongs in a
# refusal table; a RETIRED one has no reason to appear in this lane's code. .100 sat in this
# guard's own remedy text, offered to an operator who had just been refused, from
# 2026-11-14 to 2026-11-28, because nothing asserted this. Scoped to the files this lane
# owns -- naming the population the assertion actually covers, not the whole repo it scans.
owned_rel = {f"pipeline/reextract/{s}" for s in OWNED} | {
    "pipeline/reextract/endpoint_guard.py", "pipeline/reextract/test_endpoint_guard.py"}
owned_offenders = {rel: v for rel, v in advertises_retired.items() if rel in owned_rel}
check("no Lane B owned file names a RETIRED host outside a comment citing the retirement",
      not owned_offenders, f"{owned_offenders}")
other_offenders = {rel: v for rel, v in advertises_retired.items() if rel not in owned_rel}
if other_offenders:
    print(f"\n  NOT ASSERTED ({len(other_offenders)} file(s) outside Lane B's ownership name a"
          f" retired host; reported so the gap is not silent):")
    for rel in sorted(other_offenders):
        for n, ip, snippet in other_offenders[rel]:
            print(f"    retired-host  {rel}:{n}  {snippet}")

# A raise ends a hand-rolled run silently, and a dropped check is invisible without this.
EXPECTED_CHECKS = 34
print()
if checks_run != EXPECTED_CHECKS:
    fails.append(f"check COUNT is {checks_run}, expected {EXPECTED_CHECKS} -- a check was"
                 f" added, dropped, or skipped by an early exception")
    print(f"FAIL  check count: {checks_run} != {EXPECTED_CHECKS}")
if fails:
    print(f"FAIL: {len(fails)} assertion(s)")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print(f"PASS ({checks_run} checks): no default endpoint; the reserved pair is refused in the\nguard and in both owned scripts; no Lane B owned file names a retired host; and no unguarded\naddressing site has appeared since the 2026-11-28 baseline of {len(BASELINE_UNGUARDED)}.\nThis does NOT assert that those {len(BASELINE_UNGUARDED)} are safe -- they are not guarded,\nand none of them is Lane B's to edit.")
sys.exit(0)
