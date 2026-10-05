"""Score the 16 locked noise-floor predictions (sha16 5ab1cfe0ac2a6485) against the two arms.

Run from the goatyard-laneA worktree root. Prints one line per prediction with HELD / FALSIFIED /
PARTIAL and the observed value. PARTIAL means the recorded artifacts cannot cover the prediction as
worded, and it says what is missing rather than scoring the narrower thing as a pass.

NOTE (ruling 1, 2026-09-27): nf1/nf2 are RETIRED as a baseline -- see
docs/audits/RETIRED_noise_floor_laneA_20260927.md. This script still defaults to those two
directories on purpose, because scoring that locked prediction is the one thing the pair is still
for. Its output is calibration history, not a measurement of the system: do not carry any number
it prints forward as a floor or a comparison point. The floor of record is pf1/pf2
(docs/audits/RESULT_pinned_floor_laneA_20260927.md).
"""
import io, json, os, statistics, sys

A = sys.argv[1] if len(sys.argv) > 2 else "evals/output/noise_floor/nf1_20260927"
B = sys.argv[2] if len(sys.argv) > 2 else "evals/output/noise_floor/nf2_20260927"
SELFTEST = len(sys.argv) > 2
SP, SF, FLAKY, ND = "STABLE-PASS", "STABLE-FAIL", "FLAKY", "NO-DATA"

def cls(rp):
    ps = [p for p in (rp or []) if p is not None]
    if not ps: return ND
    if all(ps): return SP
    if not any(ps): return SF
    return FLAKY

def load(d):
    qs, runs = {}, []
    for n in sorted(os.listdir(d)):
        if not n.endswith(".json") or n == "summary.json": continue
        r = json.load(io.open(os.path.join(d, n), encoding="utf-8"))
        sc, rs = r.get("score") or {}, r.get("response") or {}
        qid = sc.get("id") or n[:-5]
        qs[qid] = {"class": cls(r.get("run_passes")), "rp": r.get("run_passes") or [],
                   "refusal_correct": sc.get("refusal_correct"),
                   "must_not_cite_violated": sc.get("must_not_cite_violated"),
                   "answer_len": len(rs.get("answer") or ""),
                   "partial": rs.get("partial_match_sids"),
                   "resp_keys": sorted(rs.keys())}
        runs += (r.get("runs") or [])
    s = json.load(io.open(os.path.join(d, "summary.json"), encoding="utf-8"))
    return {"q": qs, "runs": runs, "s": s}

def pin(a):
    return (a["s"].get("integrity") or {}).get("openrouter_provider_pin")

a, b = load(A), load(B)
rows = []
def say(tag, text, ok, obs):
    rows.append((tag, "HELD" if ok is True else ("FALSIFIED" if ok is False else "PARTIAL"), text, obs))

ids = sorted(set(a["q"]) & set(b["q"]))
assert set(a["q"]) == set(b["q"]), ("question sets differ", sorted(set(a["q"]) ^ set(b["q"])))
changes = [i for i in ids if a["q"][i]["class"] != b["q"][i]["class"]]
flips = [i for i in ids if {a["q"][i]["class"], b["q"][i]["class"]} == {SP, SF}]
say("P1", "class changes 3-8", 3 <= len(changes) <= 8, f"{len(changes)}: {changes}")
say("P2", "SP<->SF flips 0-2", len(flips) <= 2, f"{len(flips)}: {flips}")

integ = [(x["s"].get("integrity") or {}) for x in (a, b)]
cache = [i.get("lm_cache_allowed") for i in integ]
say("P3", "both arms lm_cache off + pin recorded",
    cache == [False, False] and pin(a) == pin(b) == {"order": ["streamlake"], "allow_fallbacks": False},
    f"lm_cache_allowed={cache} pinA={pin(a)} pinB={pin(b)}")
viol = [i.get("violations") for i in integ]
say("P4", "0 integrity violations both arms", viol == [[], []], f"{viol}")

deg = sum(1 for r in a["runs"] + b["runs"] if r.get("degraded"))
say("P5", "<=6 degraded of 168", deg <= 6, f"{deg} of {len(a['runs']) + b['runs'].__len__()}")
nd = [i for i in ids if ND in (a["q"][i]["class"], b["q"][i]["class"])]
say("P6", "0 NO-DATA both arms", not nd, f"{nd or 'none'}")

pa = sum(1 for i in ids if a["q"][i]["class"] == SP)
pb = sum(1 for i in ids if b["q"][i]["class"] == SP)
# P7 as worded ("each arm passes 14-19 of 28") is AMBIGUOUS between two counts the harness keeps:
# the representative-run pass count and the STABLE-PASS class count. Both are scored, because I
# wrote the prediction and cannot pick the flattering reading after the fact.
# Ruling 2, 2026-10-04: summary["passed"] is now over RUNS (28 questions x N runs), which is NOT
# the count P7 was written against and would be scored against a band of 14-19 that cannot apply
# to it. Read the representative count by name; in a summary written before the ruling that count
# is what `passed` held, and `pass_basis` is how the two are told apart.
def rep_passed(s):
    if "representative_passed" in s:
        return s["representative_passed"]
    assert s.get("pass_basis") is None, "post-ruling summary with no representative_passed"
    return s.get("passed")

sa, sb = rep_passed(a["s"]), rep_passed(b["s"])
say("P7", "each arm passes 14-19 of 28 [BOTH readings]",
    14 <= pa <= 19 and 14 <= pb <= 19 and 14 <= (sa or 0) <= 19 and 14 <= (sb or 0) <= 19,
    f"representative A={sa} B={sb} | STABLE-PASS A={pa} B={pb}  (band 14-19 under either reading)")
say("P8", "|delta passes| <= 3", abs(pa - pb) <= 3, f"|{pa}-{pb}|={abs(pa-pb)}")
fa = sum(1 for i in ids if a["q"][i]["class"] == FLAKY)
fb = sum(1 for i in ids if b["q"][i]["class"] == FLAKY)
say("P9", "FLAKY 8-14 per arm", 8 <= fa <= 14 and 8 <= fb <= 14, f"A={fa} B={fb}")

rwa = {i for i in ids if a["q"][i]["refusal_correct"] is False and a["q"][i]["class"] != ND}
rwb = {i for i in ids if b["q"][i]["refusal_correct"] is False and b["q"][i]["class"] != ND}
rca, rcb = len(ids) - len(rwa), len(ids) - len(rwb)
say("P10", "refusal-correct 26-28 per arm AND set diff <= 1",
    26 <= rca <= 28 and 26 <= rcb <= 28 and len(rwa ^ rwb) <= 1,
    f"A={rca} B={rcb} wrongA={sorted(rwa)} wrongB={sorted(rwb)} symdiff={sorted(rwa ^ rwb)}")
mnc = [x["s"].get("must_not_cite_violations") for x in (a, b)]
say("P11", "0 must_not_cite violations", mnc == [0, 0], f"{mnc}")

# P12 as worded is NOT checkable from the arm directories. `zone3_notes` lives in the server's
# structured_meta and bot.py:1059-1063 prints it as DEBUG while explicitly NOT rendering it, so it
# never enters the HTTP response. My first probe looked for it in the response keys and found 0 of
# 56 -- a clean zero from a probe that could not have seen the field anywhere. The companion
# assertion caught it: the same probe found 0 occurrences on the ON arm, where the behavior is
# known to exist. So P12 is scored against the SERVER LOGS, with the companion assertion kept.
import re
def logcount(path, needle):
    if not os.path.exists(path): return None
    return sum(1 for line in io.open(path, encoding="utf-8", errors="replace") if needle in line)
SRV = os.environ.get("NF_SRV_DIR", "")
on_ref  = logcount(os.path.join(SRV, "server_on_d.log"), "zone3_notes")
nf1_log = logcount(os.path.join(SRV, "server_nf1.log"), "zone3_notes")
nf2_log = logcount(os.path.join(SRV, "serve_nf2.log"), "zone3_notes")
probe_works = bool(on_ref)
say("P12", "zone3_notes never non-empty on either OFF arm (flag did not leak)",
    (nf1_log == 0 and nf2_log == 0) if probe_works and nf1_log is not None else None,
    f"server-log occurrences: nf1={nf1_log} nf2={nf2_log}; companion assertion on the ON-arm log "
    f"= {on_ref} (probe can see the field where it exists: {probe_works}). "
    f"NOT checkable from the arm JSON at all -- the field is never rendered into the response.")

# Found while fixing P12, and NOT predicted: the Zone-3 EXCISION sweep (_suppress_zone3, a
# different mechanism from zone3_notes) fires on the OFF arm too.
sweep = {"nf1": logcount(os.path.join(SRV, "server_nf1.log"), "Zone-3 sweep"),
         "nf2": logcount(os.path.join(SRV, "serve_nf2.log"), "Zone-3 sweep"),
         "off_d": logcount(os.path.join(SRV, "server_off_d.log"), "Zone-3 sweep"),
         "on_d": logcount(os.path.join(SRV, "server_on_d.log"), "Zone-3 sweep")}
say("UNPREDICTED", "Zone-3 excision sweep fires on OFF (bears on item (d))", None, f"{sweep}")

pna = [i for i in ids if a["q"][i]["partial"]]
pnb = [i for i in ids if b["q"][i]["partial"]]
say("P13", "partial_match_sids empty 28/28 both arms", not pna and not pnb,
    f"nonempty A={pna or 'none'} B={pnb or 'none'} (persisted response only, 28 of 84 runs)")

g = "real_garden_genesis_3_24_misattribution_001"
say("P14", "garden STABLE-FAIL 0/3 both arms",
    a["q"][g]["class"] == b["q"][g]["class"] == SF,
    f"A={a['q'][g]['class']} {a['q'][g]['rp']} / B={b['q'][g]['class']} {b['q'][g]['rp']}")

ma = statistics.median([a["q"][i]["answer_len"] for i in ids if a["q"][i]["answer_len"]])
mb = statistics.median([b["q"][i]["answer_len"] for i in ids if b["q"][i]["answer_len"]])
say("P15", "median answer length within +/-15%", abs(mb - ma) / ma <= 0.15 if ma else None,
    f"A={ma} B={mb} delta={100*(mb-ma)/ma:+.1f}%" if ma else "A median 0")
say("P16", "both summary.json record the identical pin", pin(a) == pin(b) and pin(a) is not None,
    f"A={pin(a)} B={pin(b)}")

w = max(len(r[3]) for r in rows)
print("=" * 100)
print("PREDICTION SCORING  sha16 5ab1cfe0ac2a6485   nf1 vs nf2, OFF vs OFF")
print("=" * 100)
for tag, verdict, text, obs in rows:
    print(f"{tag:4s} {verdict:10s} {text}")
    print(f"     observed: {obs}")
held = sum(1 for r in rows if r[1] == "HELD")
print("-" * 100)
print(f"HELD {held} / {len(rows)}   FALSIFIED {sum(1 for r in rows if r[1]=='FALSIFIED')}   "
      f"PARTIAL {sum(1 for r in rows if r[1]=='PARTIAL')}")
if SELFTEST:
    print("SELFTEST MODE: same-arm-vs-itself; P1 MUST read FALSIFIED (0 changes) or the detector is stuck")
    raise SystemExit(0)
json.dump([{"id": t, "verdict": v, "claim": c, "observed": o} for t, v, c, o in rows],
          io.open("evals/output/noise_floor/prediction_scoring_20260927.json", "w", encoding="utf-8"),
          indent=2)
