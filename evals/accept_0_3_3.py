"""Prod 0.3.3 acceptance -- the items observable WITHOUT opening a
data-exposure channel on production.

Run:  python C:/Users/cnogr/git/goatyard-rel033/evals/accept_0_3_3.py

Prints nothing secret. Every kubectl call is read-only or an in-pod HTTP request
against localhost; no namespace is modified.

Lane A1, 2026-11-01. Extends `C:/Users/cnogr/.gya/accept_0_3_2.py` per Chris's
ruling 3 of 2026-11-01: **two** imageIDs instead of one, plus the x5 cited-SID
witness that 0.3.2 listed and deliberately did not run.

### Why this one lives in the repo and 0.3.2's did not

`accept_0_3_2.py` was written straight into `~/.gya/` and never committed, so
`RELEASE_0.3.2.md`'s Acceptance section cites a script that nobody can recover
from the repository. Same class as every other index-loss finding here: the
record of what was run outlived the thing that ran. This file is committed, and
the runbook invokes it by its repo path, so the acceptance output and the code
that produced it share one git sha.

### Exit codes -- stricter than 0.3.2's, on purpose

    0  every item PASS and nothing unobservable  -- acceptance is complete
    1  any item FAIL
    2  no FAIL, but something was NOT OBSERVABLE -- a half-observed acceptance
       is not an acceptance, and the 0.3.2 record's own claim was
       "3 pass, 0 fail, 0 not-observable, exit 0"

### Order matters, and it is not arbitrary

1-4 read state. 5 SERVES five real requests. 6 reads `/health/stages` LAST,
because D-004 says a cold process reports every stage false with no fault
behind it and clears only once a request has been served. Reading the endpoint
before item 5 would read the warm-up, not the system.
"""
import argparse
import json
import re
import subprocess
import sys

NS = "gya-frontend"
API_DEPLOY = "deploy/gya-frontend-api"
API_CONTAINER = "api"

API_REPO = "ghcr.io/edgy-solutions/goat-yard-archive/backend"
UI_REPO = "ghcr.io/edgy-solutions/goat-yard-archive/frontend"
# The pairing gya-test served and the paired gate run scored, pinned by digest
# in charts/goat-yard-archive/values-frontend.yaml (commit b8288d7). A digest
# here that disagrees with the chart means this script and the chart are
# describing different releases -- see test_accept_0_3_3.py, which asserts they
# do not drift apart.
API_DIGEST = ("sha256:2fce1e3467d5f53e4f0700cdd51530db86cc"
              "85c8ef7231f091c6e69509b11433")
UI_DIGEST = ("sha256:f386254ee465b77ceee57b3f11ad8f1742e8"
             "f6d671e1fa71452aa819c1996da4")

FLAG = "GILL_STRUCTURED_ANSWER"

# The x5 witness query. NOT chosen for being interesting: `predestination_001`
# is one of eight ids that stable-passed 3/3 draws in ALL FOUR scorable arms of
# the gate run -- the three OFF arms and the ON arm (recomputed from
# evals/output/gate_20261025/, intersection of the four STABLE-PASS sets).
# Twelve passing draws is the strongest in-corpus prior available for "this
# query produces a cited answer with the flag on".
WITNESS_ID = "predestination_001"
WITNESS_QUERY = "What does Gill teach about predestination?"

# backend/main.py:15, copied rather than imported: this script runs against a
# cluster from an operator's shell and must not need the backend importable.
# test_accept_0_3_3.py asserts the two patterns have not drifted apart.
SID_RE = re.compile(r"\[([A-Z0-9_]+_S\d+)\]")

# D-006: a provider exception is interpolated into the `answer` field and
# returned at HTTP 200. A 200 is therefore not evidence that an answer was
# produced, and the witness below has to look at the text.
D006_SIGNATURES = ("Error generating answer:",
                   "could not be verified against sources")

results = []


def record(name, ok, detail):
    results.append((name, ok, detail))
    flag = {True: "PASS", False: "FAIL", None: "NOT OBSERVABLE"}[ok]
    print("[%-14s] %s\n                 %s\n" % (flag, name, detail))


def kubectl(*args, **kw):
    return subprocess.run(["kubectl", "-n", NS] + list(args),
                          capture_output=True, text=True, **kw)


def image_id_check(name, selector_name, repo, digest):
    """One imageID item. The kubelet's resolved digest, not the manifest's ask."""
    r = kubectl("get", "pod",
                "-l", "app.kubernetes.io/name=%s,"
                      "app.kubernetes.io/instance=gya-frontend" % selector_name,
                "-o", "jsonpath={range .items[*]}{.metadata.name}"
                      "{\" \"}{.status.containerStatuses[*].imageID}{\"|\"}{end}")
    if r.returncode != 0:
        record(name, False, "kubectl failed: " + r.stderr.strip()[:300])
        return
    rows = [x.strip() for x in r.stdout.split("|") if x.strip()]
    if not rows:
        # An empty selector result is not "no drift": it is a probe that missed,
        # and a probe that misses must not pass on nothing.
        record(name, False,
               "no pod matched app.kubernetes.io/name=%s -- nothing to accept"
               % selector_name)
        return
    bad = [x for x in rows if digest not in x]
    detail = "; ".join(rows)
    record(name, not bad,
           ("all %d pod(s) on the signed digest: %s" % (len(rows), detail))
           if not bad else
           ("expected %s@%s\n                 got: %s" % (repo, digest, detail)))


def in_pod_http(path, method="GET", body=None, timeout=120):
    """One python one-liner inside the api container. Returns (status, text)."""
    script = (
        "import json,urllib.request,urllib.error,sys\n"
        "url='http://localhost:8000%s'\n"
        "data=%s\n"
        "req=urllib.request.Request(url, data=(json.dumps(data).encode() if data else None),"
        " headers={'Content-Type':'application/json'}, method='%s')\n"
        "try:\n"
        "    r=urllib.request.urlopen(req, timeout=%d)\n"
        "    print(r.status); print(r.read().decode())\n"
        "except urllib.error.HTTPError as e:\n"
        "    print(e.code); print(e.read().decode()[:2000])\n"
        "except Exception as e:\n"
        "    print(-1); print(repr(e))\n"
    ) % (path, repr(body), method, timeout - 10)
    r = None
    for interp in ("python", "python3"):
        r = kubectl("exec", API_DEPLOY, "-c", API_CONTAINER, "--",
                    interp, "-c", script, timeout=timeout)
        if r.returncode == 0 and r.stdout.strip():
            head, _, rest = r.stdout.partition("\n")
            try:
                return int(head.strip()), rest.strip()
            except ValueError:
                return -1, r.stdout.strip()
    return -1, ((r.stderr or r.stdout).strip()[:500] if r else "no kubectl run")


def context_sids(doc):
    """Every sentence id in the RETRIEVED context of one response.

    `citations` is a list of human-readable citation strings
    (`ev.citation`, backend/main.py:1108), NOT sentence ids -- so the cited-SID
    check cannot be built on it. The context SID set lives in
    evidence[*].sentence_data[*], under either `sentence_id` or `sid`
    (backend/main.py:737 reads both).
    """
    out = set()
    for ev in doc.get("evidence") or []:
        for sd in (ev.get("sentence_data") or []):
            if isinstance(sd, dict):
                sid = sd.get("sentence_id") or sd.get("sid")
                if sid:
                    out.add(str(sid).strip("[]"))
    return out


def witness_draw(doc):
    """What one draw establishes. Pure, so test_accept_0_3_3.py can drive it.

    Returns (fault_or_None, observation_dict). A fault is a release failure; the
    observation is reported either way.
    """
    answer = doc.get("answer") or ""
    cited = set(SID_RE.findall(answer))
    ctx = context_sids(doc)
    obs = {"cited": sorted(cited), "n_context": len(ctx),
           "verified": doc.get("verified"), "refused": doc.get("refused"),
           "unverified": sorted(doc.get("unverified_sentence_ids") or [])}

    for sig in D006_SIGNATURES:
        if sig in answer:
            return ("D-006: the answer field carries an error string, not an "
                    "answer (%r). A 200 here is not a produced answer." % sig), obs
    if not ctx:
        # Without this, `cited <= ctx` is 0 <= 0 and the subset check passes
        # vacuously on a response that retrieved nothing.
        return ("no sentence ids in the retrieved context -- the subset check "
                "below would pass on nothing"), obs
    if not cited:
        return ("the answer cites no sentence id (refused=%r). The structured "
                "answer path produced no verbatim-cited claim."
                % doc.get("refused")), obs
    orphan = sorted(cited - ctx)
    if orphan:
        return ("cited_sid_not_in_context (ADR-0006): %s cited but not in the "
                "retrieved context" % orphan), obs
    if doc.get("verified") is not True:
        return "verified=%r -- the verifier did not affirm this answer" % doc.get(
            "verified"), obs
    return None, obs


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--draws", type=int, default=5,
                    help="draws for the cited-SID witness (default 5). Each one "
                         "is a real LM call and one slot of the anonymous rate "
                         "limit (RATE_LIMIT, default 10/day, backend/main.py:398).")
    ap.add_argument("--skip-witness", action="store_true",
                    help="record the x5 witness NOT OBSERVABLE and serve no "
                         "requests. Exits 2: the acceptance is then incomplete.")
    args = ap.parse_args(argv)

    # --- 1-2. imageID x2 ---------------------------------------------------
    image_id_check("api imageID", "gya-frontend-api", API_REPO, API_DIGEST)
    image_id_check("ui imageID", "gya-frontend-ui", UI_REPO, UI_DIGEST)

    # --- 3. did the flag actually LAND in the running container? -----------
    # Not the same question as the imageID above, and this is the one item
    # 0.3.2 had no analogue for.
    #
    # On prod the flag is a ConfigMap key consumed via `envFrom`
    # (templates/api-deployment.yaml:58-62), so it does NOT appear as an
    # explicit `env` entry in the pod spec. The gate run's probe --
    # jsonpath over .spec.template.spec.containers[0].env[?(@.name==FLAG)] --
    # returns EMPTY here, because gya-test's flag was set by `kubectl set env`
    # and prod's comes from the chart. Reading the ConfigMap instead would
    # answer a different question: `envFrom` is resolved at container start, and
    # templates/api-deployment.yaml carries no `checksum/config` annotation
    # (D-007), so an updated ConfigMap and a stale container are a consistent
    # state. The only probe that answers "what did THIS container start with" is
    # the container's own environment.
    r = kubectl("exec", API_DEPLOY, "-c", API_CONTAINER, "--",
                "sh", "-c", "printenv " + FLAG)
    val = r.stdout.strip()
    if r.returncode != 0 and not val:
        record("flag landed in the running container", None,
               "could not exec into %s: %s" % (API_DEPLOY, (r.stderr or "").strip()[:200]))
    elif val == "":
        record("flag landed in the running container", False,
               "%s is UNSET in the container. Unset is a THIRD state (the "
               "code's default), not the same thing as 0, and it is what a "
               "ConfigMap-only update with no pod restart looks like." % FLAG)
    elif val != "1":
        record("flag landed in the running container", False,
               "%s=%r in the container; 0.3.3 ships it as \"1\". The ConfigMap "
               "may already say 1 -- this reads the container, which is what "
               "the process actually got." % (FLAG, val))
    else:
        record("flag landed in the running container", True,
               "%s=1 in the running api container (read from the container's "
               "own environment, not from the ConfigMap)" % FLAG)

    # --- 4. debug captures refuse by default -------------------------------
    status, text = in_pod_http("/api/search", "POST",
                               {"query": "faith", "debug": True})
    if status == 403:
        names_var = "GYA_DEBUG_STAGES" in text
        record("debug 403 by default", names_var,
               "403 and the refusal names the variable" if names_var else
               "403 but the message does not name GYA_DEBUG_STAGES: " + text[:300])
    elif status == 429:
        record("debug 403 by default", None,
               "429 -- rate limited before the debug gate could answer. This "
               "probe cannot speak to the gate.")
    elif status in (401, 422):
        record("debug 403 by default", None,
               "status %s -- rejected before the debug gate could answer "
               "(auth/validation), so this probe cannot speak to the gate." % status)
    elif status == 200:
        record("debug 403 by default", False,
               "200 -- debug captures are ENABLED on prod. This is the "
               "data-exposure channel open; GYA_DEBUG_STAGES is not '0'.")
    else:
        record("debug 403 by default", False, "status %s: %s" % (status, text[:300]))

    # --- 5. the x5 cited-SID witness ---------------------------------------
    name = "cited-SID witness x%d" % args.draws
    if args.skip_witness:
        record(name, None, "--skip-witness: no request served, nothing observed")
    else:
        faults, obs, aborted = [], [], None
        for i in range(args.draws):
            status, text = in_pod_http("/api/search", "POST",
                                       {"query": WITNESS_QUERY})
            if status == 429:
                # A rate limit is a RUN-level fault, not an item error: the
                # remaining draws would measure the limiter. Abort, report
                # inconclusive, never splice a short run into a pass.
                aborted = ("429 on draw %d of %d -- rate limited (anonymous "
                           "limit is RATE_LIMIT, default 10/day). The witness "
                           "did not run; it has not passed." % (i + 1, args.draws))
                break
            if status != 200:
                aborted = ("draw %d returned status %s: %s"
                           % (i + 1, status, text[:200]))
                break
            try:
                doc = json.loads(text)
            except Exception as exc:
                aborted = "draw %d unparseable: %r" % (i + 1, exc)
                break
            fault, o = witness_draw(doc)
            obs.append(o)
            if fault:
                faults.append("draw %d: %s" % (i + 1, fault))

        sets = [tuple(o["cited"]) for o in obs]
        lines = ["%s x%d draws, query id %s" % (name, len(obs), WITNESS_ID)]
        for i, o in enumerate(obs, 1):
            lines.append("                 draw %d: verified=%s refused=%s "
                         "context_sids=%d cited=%s"
                         % (i, o["verified"], o["refused"], o["n_context"],
                            o["cited"]))
        # OBSERVED, never asserted: the answer is model-generated, so an
        # identical SID set across five draws is a stability observation. A gate
        # that failed the release on it would cry wolf on the first deploy and
        # then get relaxed, which is worse than not having it.
        if sets:
            lines.append("                 cited-SID set identical across draws: "
                         "%s  (OBSERVED, not asserted -- %d distinct set(s))"
                         % (len(set(sets)) == 1, len(set(sets))))
        if aborted:
            lines.append("                 ABORTED: " + aborted)
            record(name, None, "\n".join(lines))
        elif faults:
            lines.extend("                 FAULT " + f for f in faults)
            record(name, False, "\n".join(lines))
        else:
            record(name, True, "\n".join(lines))

    # --- 6. /health/stages, read LAST (D-004) ------------------------------
    status, text = in_pod_http("/health/stages")
    if status != 200:
        record("/health/stages", False, "status %s: %s" % (status, text[:300]))
    else:
        try:
            doc = json.loads(text)
            stages, notobs = doc.get("stages", {}), doc.get("not_observable", [])
            bools = all(isinstance(v, bool) for v in stages.values())
            absent = [k for k in ("answer", "verifier") if k not in stages]
            ok = (bools and sorted(notobs) == ["answer", "verifier"]
                  and len(absent) == 2 and len(stages) > 0)
            record("/health/stages", ok,
                   "stages=%s not_observable=%s (answer/verifier absent from "
                   "stages: %s)" % (json.dumps(stages, sort_keys=True),
                                    sorted(notobs), len(absent) == 2))
        except Exception as exc:
            record("/health/stages", False,
                   "unparseable: %r -- %s" % (exc, text[:200]))

    # --- summary -----------------------------------------------------------
    print("=" * 72)
    passed = [n for n, ok, _ in results if ok is True]
    failed = [n for n, ok, _ in results if ok is False]
    unobs = [n for n, ok, _ in results if ok is None]
    print("pass %d   fail %d   not-observable %d"
          % (len(passed), len(failed), len(unobs)))
    for n in failed:
        print("  FAIL           " + n)
    for n in unobs:
        print("  NOT OBSERVABLE " + n)

    print("""
WHAT THIS DOES NOT CHECK (named, not swept)
  - nested-quote citation pairing, and the entity manifest x5. Both read
    `available_entities` / the per-stage capture, which backend/main.py
    populates ONLY when the debug gate allows it. Observing them on prod means
    setting GYA_DEBUG_STAGES=1 there -- opening the exposure channel that item 4
    exists to keep shut. This script will not do that. Item 5 is the part of
    that pair which needs no debug channel, because cited SIDs are in the
    ordinary response body.
  - that the flip is a quality WIN. The gate run passed the pre-registered
    ratchet (zero STABLE-PASS -> STABLE-FAIL, zero must_not_cite); its effect
    clause abstained. Item 5 witnesses that the cited-answer path WORKS with the
    flag on, on prod's corpus. It is not a measurement of whether it is better.
  - prod's corpus. The witness query's twelve-for-twelve record is on gya-test's
    corpus. If it refuses on prod, a corpus difference is the first hypothesis
    and a flag failure is not -- which is why `refused` and `context_sids` are
    printed per draw rather than folded into the verdict.
  - D-004, D-005 and D-006 ride along to prod unfixed; all three are 0.3.4.
    D-006 is pre-existing on prod, so it is not a 0.3.3 regression.
""")
    if failed:
        return 1
    return 2 if unobs else 0


if __name__ == "__main__":
    sys.exit(main())
