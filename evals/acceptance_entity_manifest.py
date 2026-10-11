"""Release 0.3.1 acceptance: N identical queries must yield ONE entity manifest.

The 5c93b28 claim is narrow and this script tests exactly it: the FIRST-PASS
entity manifest is a pure function of (query, corpus). That manifest is
stages.available_entities, built from the thesaurus-expanded lookup_query
(backend/main.py:513), which BAML never sees.

It deliberately does NOT assert on:
  * second_pass_entities -- fed by BAML's expansion (backend/main.py:585),
    which is stochastic LM output. In production, where query expansion is
    live, this may legitimately vary between identical requests. It is
    reported for information, never scored.
  * entity_lookup_mode -- a non-full second pass downgrades the whole
    request's mode (backend/main.py:595), so this can vary in production for
    the same reason. Reported, not scored.

The endpoint is REQUIRED and has no default. Nothing here may silently address
production.

Usage:
  python evals/acceptance_entity_manifest.py --base-url https://host [--runs 5]
                                             [--query "..."]

Exit codes: 0 pass, 1 FAIL (more than one distinct manifest), 2 bad usage,
3 a request failed or returned no stages (inconclusive, never a pass).
"""
import argparse
import json
import sys

import httpx

# sys.path[0] is evals/ when this is run as `python evals/acceptance_entity_manifest.py`.
import debug_capture

DEFAULT_QUERY = "What is the spiritual meaning of the scapegoat?"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True,
                    help="Scheme and host of the server under test. REQUIRED, no default.")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--query", default=DEFAULT_QUERY)
    ap.add_argument("--timeout", type=float, default=200.0)
    args = ap.parse_args(argv)

    base = args.base_url.rstrip("/")
    if not base.startswith("http"):
        print("REFUSED: --base-url must include the scheme")
        return 2

    url = base + "/api/search"
    # Before args.runs requests. This script asserts on
    # stages["available_entities"], and the check below ("not a dict, or the key is
    # missing") cannot tell a CLOSED CHANNEL from a manifest that came back empty --
    # one is a misconfigured target, the other is the finding.
    debug_capture.preflight_debug_capture(url, __file__, timeout=args.timeout)
    manifests, modes, second = [], [], []
    for i in range(args.runs):
        try:
            r = httpx.post(url, json={"query": args.query, "debug": True},
                           timeout=args.timeout)
            # Before raise_for_status, and before the `except Exception` below
            # can turn the remedy into "REQUEST FAILED HTTPStatusError":
            # SystemExit is not an Exception, so the refusal gets out.
            debug_capture.refuse_if_debug_disabled(r, url, __file__)
            r.raise_for_status()
            body = r.json()
        except Exception as e:
            print("run %d: REQUEST FAILED %s: %s" % (i + 1, type(e).__name__, e))
            return 3
        stages = body.get("stages")
        if not isinstance(stages, dict) or "available_entities" not in stages:
            print("run %d: no stages.available_entities in the response -- "
                  "inconclusive, not a pass" % (i + 1))
            return 3
        man = tuple(sorted(stages.get("available_entities") or []))
        manifests.append(man)
        modes.append(stages.get("entity_lookup_mode"))
        second.append(tuple(sorted(stages.get("second_pass_entities") or [])))
        print("run %d: mode=%s first_pass=%s" % (i + 1, stages.get("entity_lookup_mode"),
                                                 json.dumps(list(man))))

    distinct = sorted(set(manifests))
    print()
    print("ASSERTED  distinct first-pass manifests over %d runs: %d" % (args.runs, len(distinct)))
    for d in distinct:
        print("   %s" % json.dumps(list(d)))
    print("REPORTED  distinct entity_lookup_mode values: %s" % sorted(set(str(m) for m in modes)))
    print("REPORTED  distinct second-pass manifests: %d (variation here is NOT a failure)"
          % len(set(second)))
    for d in sorted(set(second)):
        print("   %s" % json.dumps(list(d)))

    if len(distinct) == 1:
        print()
        print("PASS - one first-pass manifest.")
        return 0
    print()
    print("FAIL - %d distinct first-pass manifests. The deployed image does not "
          "carry 5c93b28, or there is a second cause." % len(distinct))
    return 1


if __name__ == "__main__":
    sys.exit(main())
