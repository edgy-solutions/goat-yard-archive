"""Born-test: a run whose header does not name the machine FAILS (Chris's ruling, 2026-09-20).

    python test_run_header.py

THE GAP THIS EXISTS FOR. The frozen vol1 run of 2026-09-06 is a **signed, non-regenerable artifact** — Chris
adjudicated its strings, and those signatures are what this lane scores against. Its `config_header` records
`git_head`, `profile_sha16`, `extractor`, `started` — **and no host**. On 2026-09-20 endpoint C reproduced it
byte-identically on only **2 of 5** truthset pages, with every difference confined to Hebrew letters and
apostrophe style and nothing structural moved; today's C is self-deterministic (3 reads → 1 output), so the
disagreement is a device/stack change. Establishing that took a git worktree and an inference, because the
artifact cannot say what produced it. **Nothing here re-scores that run.** The rule is forward-only.

WHAT IS ASSERTED, AT THREE LAYERS — passing one is not passing another:

  (1) `require_endpoint` rejects a header with no machine: missing, blank, or a placeholder like "unknown".
      `UNREGISTERED:<host:port>` PASSES on purpose — an address absent from `gpu-servers.md` is still a
      recorded machine, and refusing it would push people back to recording nothing.
  (2) `build_header` cannot produce a header that fails (1), and `config_sha16` **changes** when the
      endpoint, the port, or the model digest changes. A hash that ignores the machine is what let a frozen
      run and a fresh C run look like the same configuration when they are not.
  (3) Every header-writing script Lane B owns actually calls `build_header`. A guard nothing imports is the
      `note_line_region` situation: a correct module wired to no caller.

No network call and no page load — `digest_fn` is injected. Pure CPU, runs in about a second.

SCOPE. This asserts that the machine is RECORDED, not that it was the right machine, not that the endpoint
was reachable, and not that the weights did not change mid-run. `run_vol1.py` is shared substrate and is
listed below as UNWIRED so the gap is documented rather than silent."""
import io
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_header import (build_header, require_endpoint, config_sha16, endpoint_id,
                        normalize_hostport, model_digests, HeaderMissingEndpoint)

OWNED = ["born_test.py", "collapse_run.py", "gemma_witness.py", "hebrew_aperture_diag.py"]
SUBSTRATE = ["run_vol1.py"]

FAKE = lambda hostport, model, timeout=None: "deadbeefcafe0001"

fails = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}" + (f"   {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(f"{name}: {detail}")


def rejects(hdr, label):
    try:
        require_endpoint(hdr, where=label)
        check(f"reject {label}", False, "ACCEPTED a header that does not name the machine")
    except HeaderMissingEndpoint as e:
        check(f"reject {label}", "gpu-servers.md" in str(e) or "endpoint" in str(e).lower())
    except Exception as e:
        check(f"reject {label}", False, f"raised {type(e).__name__}")


print("(1) require_endpoint")

GOOD = {"kind": "config_header", "endpoint_id": "C", "endpoint_host": "192.168.1.169:11434"}
check("accept a header naming the machine", require_endpoint(GOOD) is True)
check("accept UNREGISTERED (a recorded machine is still recorded)",
      require_endpoint({"kind": "config_header", "endpoint_id": "UNREGISTERED:10.0.0.5:11434",
                        "endpoint_host": "10.0.0.5:11434"}) is True)

# The frozen run's actual header shape: git_head + profile_sha16 + extractor + started, no host.
rejects({"kind": "config_header", "git_head": "fb6ed2c7", "profile_sha16": "abc123",
         "extractor": "extract_apparatus.extract_page", "started": "2026-09-06T01:00:00"},
        "the frozen run's header shape (no host at all)")
rejects({"kind": "config_header", "endpoint_host": "192.168.1.169:11434"}, "host but no endpoint_id")
rejects({"kind": "config_header", "endpoint_id": "C"}, "endpoint_id but no host")
for placeholder in ("", "   ", "unknown", "none", "?"):
    rejects({"kind": "config_header", "endpoint_id": placeholder, "endpoint_host": placeholder},
            f"placeholder {placeholder!r}")
rejects({"page": 100, "notes": []}, "a page record where a header should be")
rejects(None, "no header at all")

print("\n(2) build_header cannot produce a failing header, and the hash covers the machine")

h = build_header(host="192.168.1.169", model="qwen3.6-16k:35b", digest_fn=FAKE)
check("build_header passes require_endpoint", require_endpoint(h) is True)
check("endpoint_id resolved to C", h["endpoint_id"] == "C", h.get("endpoint_id"))
check("bare IP got the default port", h["endpoint_host"] == "192.168.1.169:11434", h.get("endpoint_host"))
check("model digest recorded", h["model_digest16"] == "deadbeefcafe0001", h.get("model_digest16"))
check("header cites gpu-servers.md", "gpu-servers.md" in str(h.get("endpoint_ref", "")))
check("api path is NOT written as 'endpoint'", "endpoint" not in h,
      "key collision with the API-path meaning of 'endpoint'")

# C and D are the same IP on different ports. If the port fell out of the hash they would be identical.
hC = build_header(host="192.168.1.169", model="m", digest_fn=FAKE)
hD = build_header(host="192.168.1.169:11435", model="m", digest_fn=FAKE)
check("D resolves by port", hD["endpoint_id"] == "D", hD.get("endpoint_id"))
check("C and D hash DIFFERENTLY (port is in the hash)", hC["config_sha16"] != hD["config_sha16"],
      "same hash for two different GPUs")

hB = build_header(host="192.168.1.100", model="m", digest_fn=FAKE)
check("different endpoint -> different hash", hC["config_sha16"] != hB["config_sha16"])

hRepull = build_header(host="192.168.1.169", model="m",
                       digest_fn=lambda hp, mo, t=None: "0000000000000002")
check("re-pulled weights under the same tag -> different hash",
      hC["config_sha16"] != hRepull["config_sha16"], "a weight change would have been invisible")

hSame = build_header(host="192.168.1.169", model="m", digest_fn=FAKE)
check("same configuration -> same hash", hC["config_sha16"] == hSame["config_sha16"])

check("identity_extra changes the hash",
      build_header(host="192.168.1.169", model="m", identity_extra={"seam": "baml"},
                   digest_fn=FAKE)["config_sha16"] != hC["config_sha16"])
check("extra does NOT change the hash",
      build_header(host="192.168.1.169", model="m", extra={"pages": [1, 2]},
                   digest_fn=FAKE)["config_sha16"] == hC["config_sha16"])
try:
    build_header(host="192.168.1.169", model="m", extra={"endpoint_id": "E"}, digest_fn=FAKE)
    check("extra cannot overwrite a hashed identity field", False, "silently overwrote endpoint_id")
except ValueError:
    check("extra cannot overwrite a hashed identity field", True)

check("multi-model digests map", model_digests("h:1", ["a", "b"], digest_fn=FAKE) ==
      {"a": "deadbeefcafe0001", "b": "deadbeefcafe0001"})
check("normalize_hostport strips scheme and path",
      normalize_hostport("http://192.168.1.169:11435/v1") == "192.168.1.169:11435")
check("endpoint_id never returns blank", endpoint_id("10.0.0.9:11434").startswith("UNREGISTERED:"))

print("\n(2b) the header says whether the tree was DIRTY, and that is inside the hash")
# WHY. `git_head` alone is a lie whenever the tree is dirty: it names a commit, and what ran was
# something else. Worked example, from this lane: the n=19 local-arms run recorded git_head 29f58c1
# (committed 2026-09-20T21:38:49), started at 22:01:26, and the sealed carve-out that built its n=19
# truth set was not committed until 07:16:47 the next morning. A reader reproducing that run from
# 29f58c1 gets the n=10 module and a different answer, with nothing in the artifact to warn them.
#
# The dirty check is `git status --porcelain` on purpose. Byte- or grep-level CR hunting is
# environment-dependent here -- on this machine the same file reports 349 CRs to one shell's grep and
# 0 to another's, while `tr -d \r` strips 349 bytes either way. git already knows about autocrlf, so
# git is the honest primitive and the only one whose answer does not depend on whose shell ran it.
IDENTITY_KEYS = ["git_head", "git_dirty", "profile_sha16", "model", "model_digest16",
                 "endpoint_host", "endpoint_id"]
hd = build_header(host="192.168.1.169", model="m", digest_fn=FAKE)
check("header records git_dirty", "git_dirty" in hd)
check("git_dirty has a state of clean/dirty/unknown",
      isinstance(hd.get("git_dirty"), dict) and
      hd["git_dirty"].get("state") in ("clean", "dirty", "unknown"), str(hd.get("git_dirty")))
check("'unknown' is distinguishable from 'clean' (not knowing is not knowing it was clean)",
      hd["git_dirty"].get("state") != "unknown" or "n" not in hd["git_dirty"])

# The decisive one: recompute the hash from the identity fields and confirm it matches. If git_dirty
# were recorded BESIDE the hash instead of inside it, two runs from the same commit -- one clean, one
# with an uncommitted rewrite of the truth set -- would carry the same config_sha16.
base = {k: hd[k] for k in IDENTITY_KEYS}
check("config_sha16 is computed over git_dirty (recomputation matches)",
      config_sha16(base) == hd["config_sha16"], "git_dirty sits outside the hash")
check("a clean tree and a dirty tree hash differently",
      config_sha16({**base, "git_dirty": {"state": "clean"}}) !=
      config_sha16({**base, "git_dirty": {"state": "dirty", "n": 1, "paths": ["x.py"]}}))
check("WHICH files were dirty is in the hash, not just how many",
      config_sha16({**base, "git_dirty": {"state": "dirty", "n": 1, "paths": ["a.py"]}}) !=
      config_sha16({**base, "git_dirty": {"state": "dirty", "n": 1, "paths": ["b.py"]}}))

print("\n(3) a written run artifact is checkable end-to-end")
with tempfile.TemporaryDirectory() as td:
    from run_header import read_header
    good = Path(td) / "good.jsonl"
    with io.open(good, "w", encoding="utf-8") as f:
        f.write(json.dumps(build_header(host="192.168.1.169", model="m", digest_fn=FAKE)) + "\n")
        f.write(json.dumps({"page": 100, "notes": []}) + "\n")
    check("a run written by build_header passes", require_endpoint(read_header(good), "good.jsonl") is True)

    bad = Path(td) / "legacy.jsonl"
    with io.open(bad, "w", encoding="utf-8") as f:
        f.write(json.dumps({"kind": "config_header", "git_head": "fb6ed2c7",
                            "profile_sha16": "abc", "started": "2026-09-06T01:00:00"}) + "\n")
        f.write(json.dumps({"page": 100, "notes": []}) + "\n")
    rejects(read_header(bad), "a legacy run file on disk")

print("\n(4) the owned header-writing scripts actually call build_header")
for script in OWNED:
    txt = (HERE / script).read_text(encoding="utf-8", errors="replace") if (HERE / script).exists() else ""
    check(f"{script} imports run_header", "from run_header import" in txt)
    check(f"{script} calls build_header", "build_header(" in txt)
    check(f"{script} writes no hand-rolled config_header",
          'json.dumps({"kind": "config_header"' not in txt.replace(" ", "").replace(
              'json.dumps({"kind":"config_header"', 'json.dumps({"kind": "config_header"'),
          "a literal config_header dict survives")

print("\n(5) shared substrate — NOT wired here, documented so the gap is not silent")
for script in SUBSTRATE:
    txt = (HERE / script).read_text(encoding="utf-8", errors="replace") if (HERE / script).exists() else ""
    wired = "from run_header import" in txt
    print(f"  {'WIRED' if wired else 'UNWIRED'}  {script}"
          + ("" if wired else "   header still records no endpoint — Lane A's change to make"))

print()
if fails:
    print(f"FAIL: {len(fails)} assertion(s)")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print("PASS: a run that cannot name its machine fails, and the machine is inside the config hash.")
sys.exit(0)
