"""Score the 9 locked temperature-check predictions (sha16 80068f19794e3061) against the two arms.

    python evals/score_temperature_predictions.py [TU_DIR] [T0_DIR]

Written BEFORE either arm finished, so the thresholds are the locked ones and not thresholds chosen
after seeing the numbers. Prints HELD / FALSIFIED / PARTIAL per prediction with the observed value.
PARTIAL means the recorded artifacts cannot cover the prediction AS WORDED, and it says what is
missing instead of quietly scoring the narrower thing as a pass.
"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

TU = sys.argv[1] if len(sys.argv) > 2 else "evals/output/temperature_check/tu_20260927"
T0 = sys.argv[2] if len(sys.argv) > 2 else "evals/output/temperature_check/t0_20260927"

# The 13, from the pinned floor pooled counts. FIVE_SIXTHS is the subgroup P2 is about.
THE_13 = ["day_of_atonement_001", "john_baptist_001", "real_christophanies_001",
          "real_covenant_grace_001", "real_covenant_monocovenantal_001", "real_election_001",
          "real_garden_genesis_3_24_misattribution_001", "real_imprecatory_psalms_001",
          "real_ishmael_circumcision_001", "real_singing_psalms_001", "scapegoat_001",
          "sheep_001", "simons_count_001"]
FIVE_SIXTHS = ["day_of_atonement_001", "real_christophanies_001", "real_covenant_grace_001",
               "real_covenant_monocovenantal_001", "real_election_001",
               "real_ishmael_circumcision_001", "real_singing_psalms_001", "sheep_001"]
ABSENT = "<absent from optional_params>"


def load(d):
    """{qid: {...}} over SCORED runs only -- degraded and errored runs are not failures."""
    out = {}
    for qid in THE_13:
        p = os.path.join(d, qid + ".json")
        if not os.path.exists(p):
            continue
        j = json.load(open(p, encoding="utf-8"))
        runs = j.get("runs") or []
        scored = [r for r in runs if not r.get("degraded") and not r.get("error")]
        resp = j.get("response") or {}
        al = resp.get("answer_lm") or {}
        out[qid] = {
            "passes": sum(1 for r in scored if r.get("pass")),
            "runs": len(scored),
            "attempted": len(runs),
            "degraded": sum(1 for r in runs if r.get("degraded")),
            "errors": sum(1 for r in runs if r.get("error")),
            "answer": (resp.get("answer") or "").strip(),
            "temp": al.get("temperature_on_the_wire", "<no answer_lm record>"),
        }
    return out


def summary(d):
    p = os.path.join(d, "summary.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def cls(p, n):
    if not n:
        return "NO-DATA"
    return "STABLE-PASS" if p == n else "STABLE-FAIL" if p == 0 else "FLAKY"


def main():
    tu, t0 = load(TU), load(T0)
    su, s0 = summary(TU), summary(T0)
    rows = []

    def row(pid, claim, verdict, observed):
        rows.append((pid, claim, verdict, observed))

    missing = [q for q in THE_13 if q not in tu or q not in t0]
    if missing:
        row("P0", "both arms cover all 13", "FALSIFIED", "missing: " + ", ".join(missing))

    # P1 -- at least 8 of 13 still stochastic in t0
    stoch = [q for q, v in t0.items() if 0 < v["passes"] < v["runs"]]
    row("P1", "temperature 0 does NOT collapse it: >=8 of 13 still stochastic in t0",
        "HELD" if len(stoch) >= 8 else "FALSIFIED",
        "%d stochastic: %s" % (len(stoch), ", ".join(sorted(stoch)) or "none"))

    # P2 -- the 5/6 group does not go clean
    imperfect = [q for q in FIVE_SIXTHS if q in t0 and t0[q]["passes"] < t0[q]["runs"]]
    row("P2", ">=4 of the 8 questions at 5/6 still show a failing run in t0",
        "HELD" if len(imperfect) >= 4 else "FALSIFIED",
        "%d of 8 imperfect: %s" % (len(imperfect), ", ".join(sorted(imperfect)) or "none"))

    # P3 -- the answers still change. Per-RUN text is not persisted (runs[] carries pass/degraded/
    # elapsed only), so the prediction as worded is unmeasurable; the stored FINAL response is one
    # sample per question per arm and that is what gets reported.
    differ = [q for q in THE_13 if q in tu and q in t0 and tu[q]["answer"] != t0[q]["answer"]]
    row("P3", ">=10 of 13 show t0 text differing from every tu run", "PARTIAL",
        "per-run answer text is NOT persisted by the harness -- runs[] holds pass/degraded/elapsed "
        "only. On the ONE stored final response per question per arm, %d of 13 differ: %s"
        % (len(differ), ", ".join(sorted(differ)) or "none"))

    # P4 -- the arms differ on the wire (the companion assertion)
    bad_u = {q: v["temp"] for q, v in tu.items() if v["temp"] != ABSENT}
    bad_0 = {q: v["temp"] for q, v in t0.items() if v["temp"] != 0.0}
    # "every record reads X" is satisfied by an arm with no records at all. An empty set is not
    # evidence that the two arms differed on the wire -- it is the absence of the measurement -- so
    # full coverage of the 13 is part of the verdict, not a footnote under it.
    covered = len(tu) == len(t0) == len(THE_13)
    row("P4", "every t0 record reads 0.0 and every tu record reads absent",
        ("HELD" if not bad_u and not bad_0 else "FALSIFIED") if covered
        else "PARTIAL (no coverage)",
        "tu off-spec: %s | t0 off-spec: %s | coverage: %d+%d questions of %d+%d, and only the "
        "stored FINAL response of each (%d+%d of 78+78 calls carry a record here)"
        % (bad_u or "none", bad_0 or "none", len(tu), len(t0), len(THE_13), len(THE_13),
           len(tu), len(t0)))

    # P6 -- pass counts move but not much
    pu = sum(v["passes"] for v in tu.values())
    p0 = sum(v["passes"] for v in t0.values())
    nu = sum(v["runs"] for v in tu.values())
    n0 = sum(v["runs"] for v in t0.values())
    row("P6", "|t0 - tu| <= 6 of 78 pooled passes",
        "HELD" if abs(p0 - pu) <= 6 else "FALSIFIED",
        "tu %d/%d, t0 %d/%d, delta %+d" % (pu, nu, p0, n0, p0 - pu))

    # P7 -- no STABLE-PASS <-> STABLE-FAIL flip between the arms, gating or not
    flips = []
    for q in THE_13:
        if q not in tu or q not in t0:
            continue
        a, b = cls(tu[q]["passes"], tu[q]["runs"]), cls(t0[q]["passes"], t0[q]["runs"])
        if {a, b} == {"STABLE-PASS", "STABLE-FAIL"}:
            flips.append("%s %s->%s" % (q, a, b))
    row("P7", "no STABLE-PASS <-> STABLE-FAIL flip on any of the 13",
        "HELD" if not flips else "FALSIFIED", "%d flip(s): %s" % (len(flips), flips or "none"))

    # P8 -- integrity.corpus clean on all four samples
    def corpus_ok(s):
        c = ((s.get("integrity") or {}).get("corpus") or {})
        return (c.get("changed_during_run") is False and c.get("provisional") is False
                and c.get("violations") == []), c

    ok_u, cu = corpus_ok(su)
    ok_0, c0 = corpus_ok(s0)
    row("P8", "integrity.corpus clean on all four samples",
        "HELD" if ok_u and ok_0 else "FALSIFIED",
        "tu changed=%s provisional=%s | t0 changed=%s provisional=%s"
        % (cu.get("changed_during_run"), cu.get("provisional"),
           c0.get("changed_during_run"), c0.get("provisional")))

    # P9 -- spend and health. Wall clock is read from the logs, not from here.
    deg = sum(v["degraded"] for v in tu.values()) + sum(v["degraded"] for v in t0.values())
    err = sum(v["errors"] for v in tu.values()) + sum(v["errors"] for v in t0.values())
    calls = sum(v["attempted"] for v in tu.values()) + sum(v["attempted"] for v in t0.values())
    row("P9", "156 scored calls, no degradations, no run-level fault",
        "HELD" if (calls == 156 and deg == 0 and err == 0) else "FALSIFIED",
        "%d attempted, %d degraded, %d errored (wall clock: see the two .log files)"
        % (calls, deg, err))

    print("Temperature check -- prediction scoring (locked sha16 80068f19794e3061)")
    print("tu = %s" % TU)
    print("t0 = %s" % T0)
    print("-" * 100)
    for pid, claim, verdict, observed in rows:
        print("%-3s %-9s %s" % (pid, verdict, claim))
        print("    observed: %s" % observed)
    print("-" * 100)
    n_h = sum(1 for r in rows if r[2] == "HELD")
    n_f = sum(1 for r in rows if r[2] == "FALSIFIED")
    n_p = sum(1 for r in rows if r[2] == "PARTIAL")
    print("HELD %d   FALSIFIED %d   PARTIAL %d   (P5 is scored by compare_arms, run separately)"
          % (n_h, n_f, n_p))

    print("")
    print("Per question, scored runs only:")
    print("%-46s %-8s %-8s" % ("id", "tu", "t0"))
    for q in THE_13:
        a = "%d/%d" % (tu[q]["passes"], tu[q]["runs"]) if q in tu else "-"
        b = "%d/%d" % (t0[q]["passes"], t0[q]["runs"]) if q in t0 else "-"
        print("%-46s %-8s %-8s" % (q, a, b))


if __name__ == "__main__":
    main()
