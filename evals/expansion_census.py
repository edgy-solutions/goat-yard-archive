"""Derive per-arm query-expansion health from eval output on disk.

Ruling 2026-10-04: LITELLM_PROXY_URL is set in the production API pod, so
expansion is live there; the missing variable was eval-launch only. Every arm
that ran WITHOUT expansion is void. This script derives which arms those are
instead of trusting a remembered number -- the first attempt at that number,
in RESULT_entity_lookup_determinism_laneA_20260928.md, counted questions with
no stages record at all as "healthy expansion". Silence is not health.

Granularity differs by arm age:
  * arms run after evals/run_eval.py gained stage capture (77d3b30) carry
    expansion_error PER RUN in runs[].
  * older arms carry it only on the representative response
    (response.stages.baml_error) -- one run of N, so "no healthy question"
    there is a representative-level statement.

Usage: python evals/expansion_census.py DIR [DIR ...]
Counts only. No query text, no answer text.
"""
import json
import os
import re
import sys

from run_dir import question_files


def error_class(msg: str) -> str:
    """Bucket a BAML expansion error without echoing its text."""
    m = msg or ""
    if "requires environment variable" in m:
        tail = m[m.index("requires environment variable"):]
        var = re.search(r"'([A-Z0-9_]+)'", tail)
        return "missing_env_var:" + (var.group(1) if var else "unknown")
    if "404" in m:
        return "http_404"
    if "429" in m:
        return "http_429"
    if "timeout" in m.lower():
        return "timeout"
    return "other"


def census(root: str):
    rows = []
    for dirpath, _dirnames, filenames in os.walk(root):
        qfiles = question_files(filenames)
        n_q = run_ok = run_err = run_nofield = 0
        rep_ok = rep_err = rep_nostages = 0
        causes = {}
        for f in sorted(qfiles):
            try:
                rec = json.load(open(os.path.join(dirpath, f), encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(rec, dict) or "question" not in rec:
                continue
            n_q += 1
            for r in rec.get("runs") or []:
                if not isinstance(r, dict):
                    continue
                if "expansion_error" not in r:
                    run_nofield += 1
                elif r.get("expansion_error"):
                    run_err += 1
                else:
                    run_ok += 1
            resp = rec.get("response")
            stages = resp.get("stages") if isinstance(resp, dict) else None
            if not isinstance(stages, dict):
                rep_nostages += 1
            elif stages.get("baml_error"):
                rep_err += 1
                key = error_class(str(stages["baml_error"]))
                causes[key] = causes.get(key, 0) + 1
            else:
                rep_ok += 1
        if n_q:
            rows.append(dict(arm=os.path.relpath(dirpath, root), n_q=n_q,
                             run_ok=run_ok, run_err=run_err, run_nofield=run_nofield,
                             rep_ok=rep_ok, rep_err=rep_err, rep_nostages=rep_nostages,
                             causes=causes))
    return rows


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    total_ok = 0
    print("arm | n_q | run_ok | run_err | run_nofield | rep_ok | rep_err | rep_nostages | causes")
    for root in argv[1:]:
        if not os.path.isdir(root):
            print("MISSING %s" % root)
            continue
        for row in census(root):
            total_ok += row["run_ok"] + row["rep_ok"]
            print("%-46s | %3d | %4d | %4d | %4d | %3d | %3d | %3d | %s" % (
                row["arm"], row["n_q"], row["run_ok"], row["run_err"], row["run_nofield"],
                row["rep_ok"], row["rep_err"], row["rep_nostages"], row["causes"] or "-"))
    print()
    print("arms with ANY evidence of healthy expansion: %s"
          % ("none" if total_ok == 0 else "SOME (total_ok=%d)" % total_ok))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
