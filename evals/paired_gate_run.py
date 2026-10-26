#!/usr/bin/env python
"""One arm of the paired GILL_STRUCTURED_ANSWER gate run on gya-test.

Why this exists as a repo file and not a scratchpad script: the previous
launcher lived in a scratchpad, which means no run it produced can be
reproduced or audited. An arm of a decision gate is not a scratch artefact.

An ARM is one pod boot at one flag value, over the whole reference set, with
--runs draws per question. The flag is read by the process at container start
(envFrom/env semantics), so an arm is defined by a boot, not by a request.
That is the one fact this script exists to enforce: it refuses to run unless
the pod serving the arm was created AFTER the flag was last written, because
a spec that says `0` over a pod that booted while it said `1` produces a
correctly-labelled file full of wrongly-labelled data.

What it asserts before spending a cent, each one able to fail:

  1. The live deployment's GILL_STRUCTURED_ANSWER equals the value this arm
     claims. Read by jsonpath for that ONE named non-secret key -- never an
     env dump, which is operator-only (standing law, 2026-10-18).
  2. Exactly one api pod is Running and Ready.
  3. The POD's own spec declares that flag value. The pod spec is immutable
     after creation and is what the container read its environment from, so
     this is the direct witness; the deployment spec can be edited under a
     running pod, and a timestamp is only a proxy for both.
  4. The pod's imageID digest equals --digest. Both arms of a pair must run
     the same build; the flag is meant to be the only variable, and a digest
     that moved underneath an arm invalidates the comparison rather than
     degrading it.
  5. restartCount is 0. A mid-arm restart means some requests were served by
     a process that booted under conditions this header does not describe.

It writes a header beside the results recording the REALIZED state -- pod
name, digest, flag, boot time, git head and dirty bit -- not the state
requested. A run over a dirty tree is marked provisional and may not be cited
in an ADR or a tier change.

Usage (one arm):

    python evals/paired_gate_run.py --arm A1-off-null1 --flag 0 \
        --flag-written-at 2026-10-25T18:40:00Z \
        --digest sha256:2fce1e34... --runs 3

Namespace and deployment default to gya-test / gya-frontend-api. Production
(192.168.1.52, and the gya-frontend namespace) is not addressable from here
and must never be: this script hard-refuses any namespace that is not a test
namespace.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_NS = "gya-test"
DEFAULT_DEPLOY = "gya-frontend-api"
FLAG = "GILL_STRUCTURED_ANSWER"
# Namespaces this script will address. Prod is absent on purpose, and the
# check is a whitelist rather than a blacklist so a new prod-like namespace
# is refused by default instead of allowed by omission.
ALLOWED_NAMESPACES = {"gya-test"}


class Refused(SystemExit):
    """Raised with a message naming what was not true, and nothing is spent."""

    def __init__(self, msg: str) -> None:
        super().__init__("REFUSED: " + msg)


def kubectl(ns: str, *args: str, timeout: int = 30) -> str:
    cmd = ["kubectl", "--request-timeout=%ds" % timeout, "-n", ns, *args]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise Refused("kubectl failed: %s\n%s" % (" ".join(args), p.stderr.strip()))
    return p.stdout.strip()


def parse_ts(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def git_state(allow_untracked: list) -> dict:
    """What produced this arm, recorded rather than assumed.

    A run over a dirty tree is provisional and may not be cited in an ADR or a
    tier change. The point of that rule is that the code which produced a
    result is identified -- so a path may be excluded from it only by being
    NAMED on the command line and recorded in the header beside the full dirty
    list. A silent default would quietly widen the rule every time something
    new appeared in the tree, which is how a guard stops guarding.
    """
    def g(*args: str) -> str:
        p = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True)
        return p.stdout.strip() if p.returncode == 0 else "unknown"

    # git already knows about autocrlf; never hand-roll a CR check.
    porcelain = g("status", "--porcelain")
    dirty = sorted(line[2:].strip().strip('"') for line in porcelain.splitlines() if line)
    allowed = sorted(set(allow_untracked))
    unexplained = [p for p in dirty if p not in allowed]
    return {
        "git_head": g("rev-parse", "HEAD"),
        "git_branch": g("rev-parse", "--abbrev-ref", "HEAD"),
        "git_dirty": "dirty" if dirty else "clean",
        "git_dirty_paths": dirty[:20],
        "git_dirty_allowed": allowed,
        "git_dirty_unexplained": unexplained[:20],
    }


def pod_flag_fault(pod: dict, want_flag: str):
    """Does this pod's OWN spec declare the flag value the arm claims?

    Pure so it can be proven without a cluster. Returns (fault_or_None,
    realized_value). The pod spec is immutable after creation and is what the
    container read its environment from, which makes it the witness; the
    deployment spec can be edited under a running pod, and that is not a
    hypothetical -- it is the normal state for the seconds between a
    `kubectl set env` and the new pod being Ready.
    """
    containers = pod.get("spec", {}).get("containers") or []
    if not containers:
        return "pod spec declares no containers", None
    env = {e.get("name"): e.get("value") for e in (containers[0].get("env") or [])}
    if FLAG not in env:
        return ("no %s in its own spec, so this process booted with the code "
                "default rather than a declared value -- a THIRD state, not 0."
                % FLAG), None
    realized = env[FLAG]
    if realized != want_flag:
        return ("booted with %s=%r; this arm claims %r. The deployment spec "
                "agreeing is not enough: it can be edited under a running pod, "
                "and the flag is read at container start."
                % (FLAG, realized, want_flag)), realized
    return None, realized


def verify_arm(ns: str, deploy: str, want_flag: str, written_at: datetime,
               want_digest: str) -> dict:
    """Every claim this arm's header will make, checked against the cluster."""
    live_flag = kubectl(
        ns, "get", "deploy", deploy, "-o",
        "jsonpath={range .spec.template.spec.containers[0].env[?(@.name==\"%s\")]}"
        "{.value}{end}" % FLAG)
    if live_flag == "":
        raise Refused(
            "%s is not set as an explicit env entry on %s/%s. This arm cannot "
            "state a flag value it cannot read, and an unset flag is a THIRD "
            "state (the code's default), not the same thing as 0." % (FLAG, ns, deploy))
    if live_flag != want_flag:
        raise Refused(
            "%s reads %r on the live deployment; this arm claims %r. Fix the "
            "deployment or the arm label, not this check." % (FLAG, live_flag, want_flag))

    # Ask the deployment which pods it owns rather than hardcoding a selector.
    # A hardcoded one was wrong here on the first try (it named the repo, not
    # the chart's app label) and the symptom was "found 0 Running pods" -- a
    # refusal with the wrong reason on it, which is worse than no refusal
    # because it sends you to look at the cluster instead of at this line.
    match = json.loads(kubectl(ns, "get", "deploy", deploy, "-o",
                               "jsonpath={.spec.selector.matchLabels}"))
    if not match:
        raise Refused("deployment %s/%s declares no selector" % (ns, deploy))
    selector = ",".join("%s=%s" % (k, v) for k, v in sorted(match.items()))
    raw = kubectl(ns, "get", "pods", "-l", selector, "-o", "json")
    pods = [
        p for p in json.loads(raw).get("items", [])
        if p["metadata"]["name"].startswith(deploy + "-")
        and p.get("metadata", {}).get("deletionTimestamp") is None
    ]
    running = [p for p in pods if p.get("status", {}).get("phase") == "Running"]
    if len(running) != 1:
        raise Refused(
            "expected exactly 1 Running pod for %s, found %d (%s). Two pods means "
            "two processes, and a rollout mid-arm serves requests from both."
            % (deploy, len(running), [p["metadata"]["name"] for p in running]))
    pod = running[0]
    name = pod["metadata"]["name"]
    ready = [c for c in pod["status"].get("conditions", [])
             if c["type"] == "Ready" and c["status"] == "True"]
    if not ready:
        raise Refused("pod %s is Running but not Ready" % name)

    cs = pod["status"]["containerStatuses"][0]
    if cs.get("restartCount", 0) != 0:
        raise Refused(
            "pod %s has restartCount=%d. Some requests in this arm would have "
            "been served by a process whose boot conditions this header does "
            "not describe." % (name, cs["restartCount"]))

    digest = cs.get("imageID", "")
    if want_digest not in digest:
        raise Refused(
            "pod %s runs imageID %s; this arm claims digest %s. Both arms must "
            "run the same build or the flag is not the only variable."
            % (name, digest, want_digest))

    # The authoritative witness that this process booted with this flag value
    # is the POD's own spec, which is immutable after creation and is what the
    # container read its environment from. Not the deployment's spec (which can
    # be edited under a running pod) and not a timestamp.
    #
    # This replaced a timestamp comparison, and the reason is worth keeping:
    # the first arm's pod was created BY the env patch and its startTime landed
    # in the same second as the write, so `started <= written_at` refused a pod
    # that demonstrably had the new value. The fix is not a looser comparison --
    # that would still be a proxy, just a proxy with a tolerance on it. A check
    # on the thing itself has no tolerance to argue about.
    fault, realized_flag = pod_flag_fault(pod, want_flag)
    if fault:
        raise Refused("pod %s: %s" % (name, fault))

    started = parse_ts(pod["status"]["startTime"])
    # Recorded, and reported when it looks odd, but NOT a gate: the pod-spec
    # check above is the stronger statement and two gates on one fact only
    # produce arguments about which one is right.
    boot_vs_write = (
        "after" if started > written_at
        else "same second as" if started == written_at
        else "BEFORE (benign only because the pod spec above matched)")

    return {
        "pod": name,
        "pod_selector": selector,
        "image_id": digest,
        "pod_started": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pod_spec_flag": realized_flag,
        "boot_vs_flag_write": boot_vs_write,
        "flag_written_at": written_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "flag": {FLAG: live_flag},
        "restart_count": cs.get("restartCount", 0),
    }


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", required=True,
                    help="Arm label, e.g. A1-off-null1. Becomes the output dir.")
    ap.add_argument("--flag", required=True, choices=["0", "1"],
                    help="The %s value this arm claims; asserted against the "
                         "live deployment." % FLAG)
    ap.add_argument("--flag-written-at", required=True,
                    help="UTC %%Y-%%m-%%dT%%H:%%M:%%SZ when the flag was last "
                         "written. Required, not derived: a value this script "
                         "computed itself could not witness the thing it checks.")
    ap.add_argument("--digest", required=True,
                    help="Expected image digest (sha256:...), asserted on the pod.")
    ap.add_argument("--runs", type=int, default=3,
                    help="Draws per question. Stability, not a single draw, is "
                         "what the ratchet reads.")
    ap.add_argument("--namespace", default=DEFAULT_NS)
    ap.add_argument("--deployment", default=DEFAULT_DEPLOY)
    ap.add_argument("--endpoint", default="http://test.chart-example.local/api/search")
    ap.add_argument("--output-root", default=str(REPO_ROOT / "evals" / "output" / "gate_20261025"))
    ap.add_argument("--allow-untracked", nargs="*", default=[],
                    help="Paths excluded from the dirty-tree check, named "
                         "explicitly. Recorded in the header beside the full "
                         "dirty list; anything dirty and not named here makes "
                         "the arm provisional.")
    ap.add_argument("--verify-only", action="store_true",
                    help="Run every assertion and write no results. Use this to "
                         "prove the refusals fire before trusting a pass.")
    args = ap.parse_args(argv)

    if args.namespace not in ALLOWED_NAMESPACES:
        raise Refused(
            "namespace %r is not in the test whitelist %s. Production is not "
            "addressable from this script." % (args.namespace, sorted(ALLOWED_NAMESPACES)))

    written_at = parse_ts(args.flag_written_at)
    realized = verify_arm(args.namespace, args.deployment, args.flag,
                          written_at, args.digest)

    out_dir = Path(args.output_root) / args.arm
    header = {
        "arm": args.arm,
        "runs_per_question": args.runs,
        "endpoint": args.endpoint,
        "namespace": args.namespace,
        "deployment": args.deployment,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "realized": realized,
        **git_state(args.allow_untracked or []),
    }
    # Provisional on UNEXPLAINED dirt only, with the excluded paths on the
    # record. An excluded path that is not actually dirty is harmless; a
    # dirty path nobody named makes the arm uncitable, as it should.
    header["provisional"] = bool(header["git_dirty_unexplained"])

    print("=" * 72)
    print("ARM %s  flag %s=%s  runs=%d" % (args.arm, FLAG, args.flag, args.runs))
    for k in ("pod", "image_id", "pod_spec_flag", "pod_started",
              "boot_vs_flag_write", "restart_count"):
        print("  %-16s %s" % (k, realized[k]))
    print("  %-16s %s (%s)" % ("git", header["git_head"][:12], header["git_dirty"]))
    if header["provisional"]:
        print("  PROVISIONAL: dirty tree -- this arm may not be cited in an ADR "
              "or a tier change.")
        print("               unexplained: %s" % header["git_dirty_unexplained"])
    elif header["git_dirty"] == "dirty":
        print("  %-16s dirty, all of it named: %s"
              % ("tree", header["git_dirty_allowed"]))
    print("=" * 72)

    if args.verify_only:
        print("--verify-only: every assertion above held; nothing was run and "
              "nothing was written.")
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "arm_header.json").write_text(
        json.dumps(header, indent=2), encoding="utf-8")

    sys.path.insert(0, str(REPO_ROOT / "evals"))
    import run_eval  # noqa: E402  -- after the path is set, deliberately

    rc = run_eval.main([
        "--endpoint", args.endpoint,
        "--output-dir", str(out_dir),
        "--runs", str(args.runs),
    ])

    # Re-verify AFTER the arm: a rollout or a crash during two hours of
    # requests would otherwise leave a header describing a process that
    # stopped serving halfway through.
    try:
        after = verify_arm(args.namespace, args.deployment, args.flag,
                           written_at, args.digest)
    except SystemExit as e:
        header["post_run_verification"] = "FAILED: %s" % e
        header["valid"] = False
        print("\nPOST-RUN VERIFICATION FAILED -- this arm's results describe an "
              "unknown mixture of processes and must not be scored.\n%s" % e)
    else:
        same_pod = after["pod"] == realized["pod"]
        header["post_run_verification"] = after
        header["valid"] = same_pod
        if not same_pod:
            print("\nPOST-RUN: pod changed from %s to %s mid-arm. Not scorable."
                  % (realized["pod"], after["pod"]))
        else:
            print("\nPOST-RUN: same pod, same digest, flag unchanged, no restart.")

    header["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (out_dir / "arm_header.json").write_text(
        json.dumps(header, indent=2), encoding="utf-8")
    print("Header: %s" % (out_dir / "arm_header.json"))
    if not header.get("valid", False):
        return 2
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Refused as e:
        print(str(e))
        sys.exit(3)
