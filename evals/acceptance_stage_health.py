"""Release 0.3.2 acceptance: GET /health/stages answers, and its counters move.

What this asserts is narrow on purpose: that the deployed image carries the
route, that the snapshot has the expected shape, and that serving a request
increments it. It does NOT assert that any stage is healthy.

That distinction is the whole point. A snapshot showing
expansion.errored > 0 is a PASS for this release and a FINDING about the
server -- the route exists to report that, and failing the release on it would
be a gate that refuses to show you the thing you built it to see. The script
prints the per-stage block and says plainly which numbers are a release
verdict and which are an observation.

Two stages read "unobservable" on the 0.3.x line, by design: tag 0.3.0 has no
backend/degradation.py and no verification_failure local, so answer and
verifier RUN and their health cannot be read. "unobservable" is the honest
report; "ok" would be a fabricated pass. Expansion and entity lookup are fully
readable.

The endpoint is REQUIRED and has no default. Nothing here may silently address
production.

Usage:
  python evals/acceptance_stage_health.py --base-url https://host [--probe-search]

  --probe-search serves ONE real /api/search request so the counters can be
  shown to move. It costs one LM call and one slot of the anonymous rate limit
  (RATE_LIMIT, default 10/day). Without it the script only reads the snapshot,
  which is enough if the pod has already served traffic.

Exit codes: 0 pass, 1 FAIL (route absent, wrong shape, or counters did not
move), 2 bad usage, 3 a request failed (inconclusive, never a pass).
"""
import argparse
import json
import sys

import httpx

DEFAULT_QUERY = "What is the spiritual meaning of the scapegoat?"

# Derived from backend/stage_health.py snapshot(); a missing key means the
# deployed image is not this release, or the snapshot shape drifted.
TOP_KEYS = {"process", "requests_recorded", "expansion", "entity_lookup",
            "answer", "verifier"}
EXPANSION_KEYS = {"ok", "errored", "causes", "fallbacks"}
ANSWER_KEYS = {"ok", "not_run", "unobservable", "degraded"}


def _get(url, timeout):
    r = httpx.get(url, timeout=timeout)
    return r.status_code, (r.json() if r.status_code == 200 else None)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True,
                    help="Scheme and host of the server under test. REQUIRED, no default.")
    ap.add_argument("--probe-search", action="store_true",
                    help="Serve one real /api/search so the counters can be shown to move.")
    ap.add_argument("--query", default=DEFAULT_QUERY)
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--search-timeout", type=float, default=200.0)
    args = ap.parse_args(argv)

    base = args.base_url.rstrip("/")
    if not base.startswith("http"):
        print("REFUSED: --base-url must include the scheme")
        return 2

    url = base + "/health/stages"

    try:
        code, before = _get(url, args.timeout)
    except Exception as e:
        print("INCONCLUSIVE: GET %s raised %s: %s" % (url, type(e).__name__, e))
        return 3

    if code == 404:
        print("FAIL: GET /health/stages returned 404 - the deployed image does not "
              "carry release 0.3.2.")
        return 1
    if code != 200 or not isinstance(before, dict):
        print("INCONCLUSIVE: GET /health/stages returned HTTP %s" % code)
        return 3

    # --- shape, which IS a release verdict --------------------------------
    failures = []
    missing = TOP_KEYS - set(before)
    if missing:
        failures.append("snapshot is missing top-level keys: %s" % sorted(missing))
    if isinstance(before.get("expansion"), dict):
        m = EXPANSION_KEYS - set(before["expansion"])
        if m:
            failures.append("expansion block is missing keys: %s" % sorted(m))
    else:
        failures.append("expansion block is not an object")
    if isinstance(before.get("answer"), dict):
        m = ANSWER_KEYS - set(before["answer"])
        if m:
            failures.append("answer block is missing keys: %s" % sorted(m))
    else:
        failures.append("answer block is not an object")

    # The safety property, checked on the live payload rather than trusted
    # from the unit tests: no sentinel, no raw text.
    blob = json.dumps(before)
    if "__unobservable__" in blob:
        failures.append("the UNOBSERVABLE wire sentinel leaked into the snapshot")
    if "LITELLM_PROXY_URL=" in blob or "http://" in blob or "https://" in blob:
        failures.append("the snapshot contains a URL - raw text is reaching the response")

    proc = before.get("process") or {}
    print("process      pid=%s commit_sha=%s uptime_s=%.1f"
          % (proc.get("pid"), proc.get("commit_sha"), proc.get("uptime_s") or 0.0))
    print("requests_recorded (before): %s" % before.get("requests_recorded"))

    after = before
    if args.probe_search:
        try:
            r = httpx.post(base + "/api/search",
                           json={"query": args.query},
                           timeout=args.search_timeout)
            if r.status_code != 200:
                print("INCONCLUSIVE: the probe search returned HTTP %s" % r.status_code)
                return 3
        except Exception as e:
            print("INCONCLUSIVE: the probe search raised %s: %s" % (type(e).__name__, e))
            return 3
        try:
            code, after = _get(url, args.timeout)
        except Exception as e:
            print("INCONCLUSIVE: the second GET raised %s: %s" % (type(e).__name__, e))
            return 3
        if code != 200 or not isinstance(after, dict):
            print("INCONCLUSIVE: the second GET returned HTTP %s" % code)
            return 3
        d = (after.get("requests_recorded") or 0) - (before.get("requests_recorded") or 0)
        print("requests_recorded (after):  %s   delta=%s" % (after.get("requests_recorded"), d))
        if d < 1:
            failures.append("requests_recorded did not increment after a served request - "
                            "the recorder is not wired into the request path")
        if (after.get("process") or {}).get("pid") != proc.get("pid"):
            failures.append("a different pid answered the two reads (%s then %s) - with more "
                            "than one replica the counters are per process and this comparison "
                            "is not valid; re-run against a single pod"
                            % (proc.get("pid"), (after.get("process") or {}).get("pid")))

    # --- the observation, which is NOT a release verdict -------------------
    print("")
    print("--- per-stage, OBSERVED (none of this passes or fails the release) ---")
    for k in ("expansion", "entity_lookup", "answer", "verifier"):
        print("%-14s %s" % (k, json.dumps(after.get(k), sort_keys=True)))
    exp = after.get("expansion") or {}
    if exp.get("errored"):
        print("")
        print("NOTE: expansion errored on %s request(s), causes=%s. That is the finding this "
              "route was built to surface, not a failure of this release."
              % (exp.get("errored"), json.dumps(exp.get("causes"), sort_keys=True)))
    if not args.probe_search and not after.get("requests_recorded"):
        print("")
        print("NOTE: requests_recorded is 0, so no request has reached the recorder on this "
              "process yet. The shape check passed, but nothing here shows the recorder is "
              "WIRED. Re-run with --probe-search to assert that.")

    print("")
    if failures:
        print("FAIL")
        for f in failures:
            print("  - %s" % f)
        return 1
    print("PASS: the route answers, the snapshot shape is correct"
          + (", and the counters moved." if args.probe_search else "."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
