#!/usr/bin/env python3
"""
End-to-end answer-quality eval against the expert-curated reference set.

Reads `evals/gill_reference_set.jsonl`, hits the configured /api/search
endpoint per question, scores the response against the question's
expectations, and emits a per-question report + summary.

See ADR-0004 for the design (eval set format, scoring metrics, CI gates).

Usage:
    # Run against the test cluster (default endpoint)
    python evals/run_eval.py

    # Run against a custom endpoint
    python evals/run_eval.py --endpoint http://localhost:8000/api/search

    # Save outputs to a specific run directory (for CI artifacts / baselines)
    python evals/run_eval.py --output-dir evals/output/baseline-2026-05-24

    # Subset of questions (fast iteration)
    python evals/run_eval.py --ids scapegoat_001 logos_001

    # Compare against a baseline file (for CI regression gates)
    python evals/run_eval.py --baseline evals/baselines/2026-05-24.json
"""

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REF_SET = REPO_ROOT / "evals" / "gill_reference_set.jsonl"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "evals" / "output" / "run"
DEFAULT_ENDPOINT = "http://test.chart-example.local/api/search"

# Refusal-detection heuristic: the bot replies with this exact phrase when
# context is empty/unrelated. Matches the constant in backend/bot.py.
REFUSAL_MARKERS = (
    "regret that the provided extracts",
    "do not appear to address this specific inquiry",
)


def is_refusal(answer: str) -> bool:
    a = (answer or "").lower()
    return any(m in a for m in REFUSAL_MARKERS)


def normalize_citation(c: str) -> str:
    """Lossy normalization for sentence-ID comparison: strip brackets, uppercase, collapse leading zeros."""
    s = (c or "").strip().strip("[]").upper()
    parts = s.split("_")
    norm = []
    for p in parts:
        if p.isdigit():
            norm.append(str(int(p)))
        elif p.startswith("S") and p[1:].isdigit():
            norm.append(f"S{int(p[1:])}")
        else:
            norm.append(p)
    return "_".join(norm)


def citation_set(items: List[str]) -> set:
    return {normalize_citation(c) for c in (items or []) if c}


# Bracket pattern matches the frontend's citation parsing — comma-separated
# Sentence IDs in a single bracket like [JOHN_1_42_S03, JOHN_1_42_S04] are
# normal model output, and range-style [GENESIS_1_1_S02-S04] expands to
# S02..S04. Lowercase letters are tolerated because the model occasionally
# produces non-canonical IDs (e.g. [GENESIS_1_End_S00]) — the SID_FORMAT_RE
# below still requires uppercase, so those just get dropped silently.
BRACKET_RE = re.compile(r"\[([A-Za-z0-9_, -]+)\]")
SID_FORMAT_RE = re.compile(r"^[A-Z0-9_]+_S\d+$")
RANGE_RE = re.compile(r"^([A-Z0-9_]+)_S(\d+)-S(\d+)$")


def _expand_range(sid: str) -> List[str]:
    """Expand a range like GENESIS_1_1_S02-S04 to ['GENESIS_1_1_S02', '..._S03',
    '..._S04']. Non-ranges return as-is."""
    m = RANGE_RE.match(sid)
    if not m:
        return [sid]
    prefix, start, end = m.group(1), int(m.group(2)), int(m.group(3))
    return [f"{prefix}_S{i:02d}" for i in range(start, end + 1)]


def extract_sentence_ids(answer: str) -> List[str]:
    """The API response's `citations` field is [Vol N, p. M]-style page citations;
    the actual Sentence IDs the eval cares about appear INLINE in the answer text.
    Match bracketed groups of one-or-more Sentence IDs, handle comma-separated
    and range notation the same way the frontend does."""
    ids: List[str] = []
    for group in BRACKET_RE.findall(answer or ""):
        for part in group.split(","):
            part = part.strip()
            if not part:
                continue
            for sid in _expand_range(part):
                if SID_FORMAT_RE.match(sid):
                    ids.append(f"[{sid}]")
    return ids


@dataclass
class QuestionResult:
    id: str
    question: str
    category: str
    difficulty: str
    expected_behavior: str

    # API response fields
    api_status: int = 0
    answer: str = ""
    cited_ids: List[str] = field(default_factory=list)
    elapsed_s: float = 0.0
    error: Optional[str] = None

    # Scoring outcomes
    refusal_correct: bool = False
    must_cite_recall: float = 0.0  # fraction of must_cite present
    should_cite_recall: float = 0.0  # fraction of should_cite present
    must_not_cite_violated: bool = False
    must_cite_missing: List[str] = field(default_factory=list)
    must_not_cite_hits: List[str] = field(default_factory=list)
    # Lexical semantic checks (fix #5). must_express requires every listed
    # phrase (or one alternative from each OR-group) to appear in the answer;
    # must_not_express forbids any listed phrase from appearing. Designed to
    # catch theological flattening / confabulation that pure citation scoring
    # cannot see — e.g. an answer that earns must_cite_recall=1.0 but states
    # a generic-Reformed position as Gill's distinctive view.
    must_express_ok: bool = True
    must_express_missing: List[str] = field(default_factory=list)
    must_not_express_ok: bool = True
    must_not_express_hits: List[str] = field(default_factory=list)
    # Post-launch quote-placement guard (Phase 0). When a reference entry sets
    # `must_be_verified: true`, the response's API-layer `verified` flag must
    # be True (no `quote_failures` from the pipeline verifier). Defaults to
    # True for answer-expected questions so any case where the model attaches
    # a [SID] to text not present in that chunk turns the score red — even
    # when no specific substring is forbidden. Catches the Garden / Word-of-God
    # category where the bug is structural (citation placement), not lexical.
    must_be_verified_ok: bool = True
    must_be_verified_skipped: bool = False
    overall_pass: bool = False


def score(q: dict, response: dict, elapsed: float) -> QuestionResult:
    result = QuestionResult(
        id=q["id"],
        question=q["question"],
        category=q.get("category", "unknown"),
        difficulty=q.get("difficulty", "unknown"),
        expected_behavior=q.get("expected_behavior", "answer"),
        elapsed_s=round(elapsed, 2),
    )
    if "_error" in response:
        result.error = response["_error"]
        return result

    result.api_status = response.get("_status", 200)
    result.answer = response.get("answer", "") or ""
    # Sentence IDs are inline in the answer text, not in the API's `citations`
    # field (which holds page-level [Vol N, p. M] citations).
    result.cited_ids = extract_sentence_ids(result.answer)

    cited = citation_set(result.cited_ids)
    must_cite = citation_set(q.get("must_cite", []))
    should_cite = citation_set(q.get("should_cite", []))
    must_not_cite = citation_set(q.get("must_not_cite", []))

    # Refusal correctness
    answered = not is_refusal(result.answer)
    if result.expected_behavior == "refuse":
        result.refusal_correct = not answered
    else:
        result.refusal_correct = answered

    # Citation scoring (only meaningful for non-refusal questions)
    if must_cite:
        present = must_cite & cited
        result.must_cite_recall = round(len(present) / len(must_cite), 3)
        result.must_cite_missing = sorted(must_cite - cited)
    else:
        result.must_cite_recall = 1.0  # nothing required

    if should_cite:
        present = should_cite & cited
        result.should_cite_recall = round(len(present) / len(should_cite), 3)
    else:
        result.should_cite_recall = 1.0

    if must_not_cite:
        violations = must_not_cite & cited
        if violations:
            result.must_not_cite_violated = True
            result.must_not_cite_hits = sorted(violations)

    # Lexical semantic checks (fix #5). must_express is a list whose items
    # may be either a bare string (required substring) or a list of strings
    # (OR-group — any one alternative satisfies the slot). All slots must
    # match for must_express_ok. must_not_express is a flat list of forbidden
    # substrings — any match fails must_not_express_ok.
    ans_lower = result.answer.lower()
    must_express = q.get("must_express", []) or []
    missing_express: List[str] = []
    for item in must_express:
        if isinstance(item, list):
            if not any(alt.lower() in ans_lower for alt in item):
                missing_express.append("OR(" + " | ".join(item) + ")")
        else:
            if item.lower() not in ans_lower:
                missing_express.append(item)
    result.must_express_ok = len(missing_express) == 0
    result.must_express_missing = missing_express

    must_not_express = q.get("must_not_express", []) or []
    hits_not_express: List[str] = [t for t in must_not_express if t.lower() in ans_lower]
    result.must_not_express_ok = len(hits_not_express) == 0
    result.must_not_express_hits = hits_not_express

    # Verifier-flag gate (Phase 0 quote-placement guard). The reference entry
    # opts in via `must_be_verified: true` (default true for answer-expected
    # questions). When the API response carries `verified=False`, the model
    # attached at least one [SID] to text that the pipeline verifier could
    # not authenticate against the cited chunk's content — that's the Garden
    # category bug. Skipped when the reference entry sets `must_be_verified:
    # false` (e.g. legacy entries that pre-date the verifier).
    must_be_verified_default = result.expected_behavior == "answer"
    must_be_verified = q.get("must_be_verified", must_be_verified_default)
    if not must_be_verified:
        result.must_be_verified_skipped = True
        result.must_be_verified_ok = True
    else:
        api_verified = response.get("verified", True)  # default True if absent
        result.must_be_verified_ok = bool(api_verified)

    # Overall pass: refusal correct, must_cite met (>= 50%), no must_not_cite
    # violations, lexical semantic checks pass, verifier flag clean.
    must_cite_pass = result.must_cite_recall >= 0.5 if q.get("must_cite") else True
    if result.expected_behavior == "refuse":
        result.overall_pass = (
            result.refusal_correct
            and result.must_express_ok
            and result.must_not_express_ok
        )
    else:
        result.overall_pass = (
            result.refusal_correct
            and must_cite_pass
            and not result.must_not_cite_violated
            and result.must_express_ok
            and result.must_not_express_ok
            and result.must_be_verified_ok
        )
    return result


def call_endpoint(endpoint: str, question: str, auth: Optional[str], timeout: float) -> dict:
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = f"Bearer {auth}"
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(endpoint, headers=headers, json={"query": question})
        try:
            data = r.json()
        except Exception:
            return {"_error": f"non-JSON response (status {r.status_code}): {r.text[:200]}"}
        data["_status"] = r.status_code
        if r.status_code != 200:
            data["_error"] = f"HTTP {r.status_code}: {r.text[:200]}"
        return data
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {e}"}


def load_reference_set(path: Path, ids: Optional[List[str]]) -> List[dict]:
    if not path.exists():
        raise SystemExit(f"Reference set not found: {path}")
    questions = []
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                q = json.loads(line)
            except json.JSONDecodeError as e:
                raise SystemExit(f"{path}:{i}: invalid JSON — {e}")
            if "id" not in q or "question" not in q:
                raise SystemExit(f"{path}:{i}: missing required field id/question")
            questions.append(q)
    if ids:
        wanted = set(ids)
        unknown = wanted - {q["id"] for q in questions}
        if unknown:
            raise SystemExit(f"Unknown question IDs: {sorted(unknown)}")
        questions = [q for q in questions if q["id"] in wanted]
    return questions


def write_markdown_report(results: List[QuestionResult], out_path: Path, summary: dict) -> None:
    lines = ["# Eval Report\n"]
    lines.append(f"**Pass rate:** {summary['passed']}/{summary['total']} ({summary['pass_pct']:.1f}%)  \n")
    lines.append(f"**Refusal correctness:** {summary['refusal_correct']}/{summary['total']}  \n")
    lines.append(f"**must_not_cite violations:** {summary['must_not_cite_violations']} (HARD FAIL if >0)  \n")
    lines.append(f"**Errors:** {summary['errors']}  \n")
    lines.append(f"**Endpoint:** `{summary['endpoint']}`  \n")
    lines.append(f"**Generated:** {summary['timestamp']}\n")

    # By-category breakdown
    lines.append("\n## By category\n\n| Category | Pass | Total | Pct |\n|---|---:|---:|---:|\n")
    for cat, stats in sorted(summary["by_category"].items()):
        lines.append(f"| {cat} | {stats['pass']} | {stats['total']} | {stats['pct']:.0f}% |\n")

    # Per-question detail
    lines.append("\n## Per-question results\n")
    for r in results:
        status = "PASS" if r.overall_pass else ("REFUSED OK" if r.expected_behavior == "refuse" and r.refusal_correct else "FAIL")
        lines.append(f"\n### `{r.id}` — {status}\n")
        lines.append(f"- **Question:** {r.question}\n")
        lines.append(f"- **Category:** {r.category} / **Difficulty:** {r.difficulty}\n")
        lines.append(f"- **Expected:** {r.expected_behavior} / **Refusal correct:** {r.refusal_correct}\n")
        if r.error:
            lines.append(f"- **Error:** `{r.error}`\n")
            continue
        lines.append(f"- **Latency:** {r.elapsed_s}s\n")
        lines.append(f"- **must_cite recall:** {r.must_cite_recall:.0%}")
        if r.must_cite_missing:
            lines.append(f" (missing: `{r.must_cite_missing}`)")
        lines.append("\n")
        lines.append(f"- **should_cite recall:** {r.should_cite_recall:.0%}\n")
        if r.must_not_cite_violated:
            lines.append(f"- **must_not_cite VIOLATED:** `{r.must_not_cite_hits}`\n")
        if r.answer:
            preview = r.answer[:300].replace("\n", " ")
            lines.append(f"- **Answer preview:** `{preview}{'...' if len(r.answer) > 300 else ''}`\n")
    out_path.write_text("".join(lines), encoding="utf-8")


def summarize(results: List[QuestionResult], endpoint: str) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r.overall_pass)
    refusal_correct = sum(1 for r in results if r.refusal_correct)
    must_not_cite_violations = sum(1 for r in results if r.must_not_cite_violated)
    errors = sum(1 for r in results if r.error)

    by_category = defaultdict(lambda: {"pass": 0, "total": 0})
    for r in results:
        by_category[r.category]["total"] += 1
        if r.overall_pass:
            by_category[r.category]["pass"] += 1
    by_category_out = {
        k: {"pass": v["pass"], "total": v["total"], "pct": (100.0 * v["pass"] / v["total"]) if v["total"] else 0}
        for k, v in by_category.items()
    }

    return {
        "endpoint": endpoint,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total": total,
        "passed": passed,
        "pass_pct": (100.0 * passed / total) if total else 0,
        "refusal_correct": refusal_correct,
        "must_not_cite_violations": must_not_cite_violations,
        "errors": errors,
        "by_category": by_category_out,
    }


def compare_to_baseline(current: dict, baseline_path: Path, regression_threshold: float = 5.0) -> int:
    """Compare current summary to a baseline summary file. Returns nonzero if a regression triggers a fail."""
    if not baseline_path.exists():
        print(f"\nBaseline {baseline_path} does not exist; nothing to compare.")
        return 0
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    print(f"\n=== Comparison vs baseline ({baseline_path.name}) ===")
    print(f"Baseline pass rate : {baseline.get('pass_pct', 0):.1f}%")
    print(f"Current pass rate  : {current['pass_pct']:.1f}%")
    delta = current["pass_pct"] - baseline.get("pass_pct", 0)
    print(f"Delta              : {delta:+.1f}%")

    fail = False
    if current["must_not_cite_violations"] > 0:
        print(f"HARD FAIL: {current['must_not_cite_violations']} must_not_cite violation(s) in current run.")
        fail = True
    if delta < -regression_threshold:
        print(f"HARD FAIL: pass rate regressed by more than {regression_threshold}%.")
        fail = True
    return 1 if fail else 0


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--endpoint", default=os.getenv("EVAL_ENDPOINT", DEFAULT_ENDPOINT),
                        help="The /api/search endpoint to evaluate.")
    parser.add_argument("--reference-set", default=str(DEFAULT_REF_SET),
                        help="Path to JSONL reference set.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR),
                        help="Directory to write per-question results, summary.json, report.md.")
    parser.add_argument("--ids", nargs="*", help="Run only these question IDs.")
    parser.add_argument("--baseline", help="Path to baseline summary JSON for regression comparison.")
    parser.add_argument("--timeout", type=float, default=120.0, help="Per-question timeout in seconds.")
    parser.add_argument("--regression-threshold", type=float, default=5.0,
                        help="Pass-rate drop (percentage points) that triggers a hard fail vs baseline.")
    parser.add_argument("--auth-token", default=os.getenv("EVAL_AUTH_TOKEN"),
                        help="Optional Bearer token for authenticated endpoint testing.")
    args = parser.parse_args(argv)

    load_dotenv(REPO_ROOT / ".env")

    questions = load_reference_set(Path(args.reference_set), args.ids)
    out_dir = Path(args.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Endpoint  : {args.endpoint}")
    print(f"Questions : {len(questions)}")
    print(f"Output dir: {out_dir}\n")

    results: List[QuestionResult] = []
    for i, q in enumerate(questions, 1):
        print(f"[{i:2d}/{len(questions)}] {q['id']}: {q['question'][:70]}...", flush=True)
        t0 = time.perf_counter()
        response = call_endpoint(args.endpoint, q["question"], args.auth_token, args.timeout)
        elapsed = time.perf_counter() - t0
        r = score(q, response, elapsed)
        results.append(r)

        # Per-question raw response (for debugging)
        (out_dir / f"{q['id']}.json").write_text(
            json.dumps({"question": q, "response": response, "score": asdict(r)}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        status = "PASS" if r.overall_pass else "FAIL"
        if r.error:
            print(f"   [{status}] error: {r.error}")
        else:
            print(
                f"   [{status}] refusal_ok={r.refusal_correct}  "
                f"must_cite={r.must_cite_recall:.0%}  "
                f"should_cite={r.should_cite_recall:.0%}  "
                f"latency={r.elapsed_s}s"
                + (f"  must_not_cite_HIT={r.must_not_cite_hits}" if r.must_not_cite_violated else "")
            )

    summary = summarize(results, args.endpoint)

    print(f"\n{'='*70}\nSUMMARY\n{'='*70}")
    print(f"Pass rate                : {summary['passed']}/{summary['total']} ({summary['pass_pct']:.1f}%)")
    print(f"Refusal correctness      : {summary['refusal_correct']}/{summary['total']}")
    print(f"must_not_cite violations : {summary['must_not_cite_violations']}")
    print(f"Errors                   : {summary['errors']}")
    print(f"\nBy category:")
    for cat, stats in sorted(summary["by_category"].items()):
        print(f"  {cat:30s}  {stats['pass']}/{stats['total']}  ({stats['pct']:.0f}%)")

    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    write_markdown_report(results, out_dir / "report.md", summary)
    print(f"\nWritten:\n  {out_dir / 'summary.json'}\n  {out_dir / 'report.md'}\n  {out_dir}/<id>.json (per-question raw)")

    # Optional baseline comparison
    if args.baseline:
        rc = compare_to_baseline(summary, Path(args.baseline), args.regression_threshold)
        return rc
    # If no baseline, hard-fail only on must_not_cite violations
    return 1 if summary["must_not_cite_violations"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
