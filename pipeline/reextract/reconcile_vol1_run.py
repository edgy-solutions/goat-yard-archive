"""Post-run reconciliation for the frozen-config vol1 apparatus run — the born-test that PROVES the
958-page output is the same pipeline the 47-page truthset was adjudicated against. Two checks:

  1. CENSUS RE-GENERATION — recompute the status census from the run and diff it against the 2026-08-10
     numbers (no_apparatus 107 / OK 215 / ANCHOR_FLAGGED 611 / STITCH_VIOLATION 25). Every drift must be
     explainable by a NAMED config change (crop_gate, per-note, Build 3/5) — this script reports the
     drift; the human names the cause.

  2. TRUTHSET DIFF (the real gate) — on the 47 truthset pages, compare the run's per-note text to the
     truthset run's own extraction (manifest `extracted`, the readings that were then adjudicated).
     Agreement = same pipeline. Each disagreement is classified: `variance` (high token overlap, a
     stochastic transcription wobble — expected, bounded, counted) or `drift` (low overlap or a note-count
     mismatch — the pipeline is NOT what you think). The drift count goes in the acceptance claim beside
     the concordance. Also reported: correctness vs the SIGNED verdict (take-extracted/keep-stored/neither),
     which prices accuracy against adjudicated truth but is not the same-pipeline test.

Reads the run output + truthset artifacts from the private data root (data_config). Runs on partial output
(reports coverage); the final numbers come when the run completes. No writes, no mutation."""
import sys, io, json, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from data_config import data_path

RUN = Path(sys.argv[1]) if len(sys.argv) > 1 else data_path("vol1_apparatus.jsonl")
MANIFEST = data_path("audits", "sitting_manifest_span_adjudication.json")
RESIDUE = data_path("audits", "chris_sitting_b_residue_20260823.jsonl")
AGENT = data_path("audits", "agent_session_20260823.jsonl")
CHRIS = data_path("audits", "chris_sitting_b_20260823.jsonl")
CENSUS_0810 = {"no_apparatus": 107, "OK": 215, "ANCHOR_FLAGGED": 611, "STITCH_VIOLATION": 25}

def load(p):
    return [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()] if Path(p).exists() else []

def verdicts(p):
    return {r["span_id"]: r for r in load(p) if r.get("kind") != "sitting_manifest"}

def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip())

def token_overlap(a, b):
    ta, tb = set(re.findall(r"\w+", a)), set(re.findall(r"\w+", b))
    return len(ta & tb) / max(1, len(ta | tb))

def main():
    run = [r for r in load(RUN)]
    header = next((r for r in run if r.get("kind") == "config_header"), None)
    pages = {r["page"]: r for r in run if r.get("kind") != "config_header"}
    print(f"=== run: {RUN}")
    if header:
        print(f"config_header: git {header.get('git_head','?')[:12]} · profile {header.get('profile_sha16','?')}")
    print(f"pages present: {len(pages)}/958\n")

    # 1. CENSUS
    from collections import Counter
    cen = Counter(p["status"] for p in pages.values())
    print("--- 1. census re-generation (vs 2026-08-10) ---")
    for k in ("no_apparatus", "OK", "ANCHOR_FLAGGED", "STITCH_VIOLATION"):
        now, old = cen.get(k, 0), CENSUS_0810[k]
        d = now - old
        print(f"  {k:18} run={now:4}  08-10={old:4}  drift={d:+d}")
    other = {k: v for k, v in cen.items() if k not in CENSUS_0810}
    if other: print(f"  other statuses: {dict(other)}")
    print("  (drift is expected — the 08-10 run predates crop_gate/per-note/Build3-5; name each cause)\n")

    # 2. TRUTHSET DIFF
    man = json.load(io.open(MANIFEST, encoding="utf-8")) if Path(MANIFEST).exists() else {}
    spans = {s["span_id"]: s for s in man.get("disagreement", []) + man.get("agreed_sample", [])}
    residue = verdicts(RESIDUE); agent = verdicts(AGENT)
    def signed_reading(sid, s):
        v = residue.get(sid) or agent.get(sid)          # residue settles disagreements; agent carries agreed + concordant
        if not v: return None, None
        ch = v["chosen"]
        if ch in ("take-extracted", "confirm", "correlated-error"): return s["extracted"], ch
        if ch == "keep-stored": return s["stored"], ch
        if ch == "neither": return (v.get("disputed_span_correction") or ""), ch
        return None, ch

    tset_pages = sorted({s["page"] for s in spans.values()})
    present = [p for p in tset_pages if p in pages]
    print(f"--- 2. truthset diff ({len(spans)} spans across {len(tset_pages)} pages; {len(present)} pages in run so far) ---")
    repro_ok = variance = drift = missing = 0
    correctness_ok = 0; scored = 0
    diffs = []
    for sid, s in spans.items():
        pg = s["page"]
        if pg not in pages: missing += 1; continue
        idx = int(sid.split(":n")[1])
        notes = pages[pg].get("notes") or []
        if idx >= len(notes):                            # note-count mismatch = structural drift
            drift += 1; diffs.append((sid, "drift", "note-count mismatch", "", "")); continue
        run_text = norm(notes[idx]["text"]); extracted = norm(s["extracted"])
        # same-pipeline: run vs the truthset's own extraction
        if run_text == extracted:
            repro_ok += 1
        else:
            ov = token_overlap(run_text, extracted)
            if ov >= 0.6:
                variance += 1; kind = "variance"
            else:
                drift += 1; kind = "drift"
            diffs.append((sid, kind, f"overlap {ov:.2f}", extracted[:60], run_text[:60]))
        # correctness vs signed verdict
        signed, ch = signed_reading(sid, s)
        if signed is not None:
            scored += 1
            if ch == "neither":
                if norm(signed) and norm(signed) in run_text: correctness_ok += 1
            elif run_text == norm(signed): correctness_ok += 1

    print(f"  REPRODUCTION (run vs truthset-extracted): {repro_ok} match · {variance} variance · {drift} DRIFT · {missing} pages-not-yet-run")
    print(f"  -> same-pipeline gate: DRIFT must be ~0. Current drift = {drift}"
          + ("  [PASS so far]" if drift == 0 else "  [INVESTIGATE]"))
    if scored:
        print(f"  CORRECTNESS (run vs signed verdict): {correctness_ok}/{scored} match the adjudicated-correct reading")
    if diffs:
        print("\n  disagreements (span · class · detail):")
        for sid, kind, detail, exp, got in sorted(diffs, key=lambda d: (d[1] != "drift", d[0])):
            print(f"    {sid:11} {kind:8} {detail}")
            if exp: print(f"        truthset: {exp!r}\n        run     : {got!r}")
    print(f"\nThe number for the acceptance claim: reproduction DRIFT = {drift} "
          f"(of {len(spans)-missing} truthset spans scored); variance = {variance}.")

if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    main()
