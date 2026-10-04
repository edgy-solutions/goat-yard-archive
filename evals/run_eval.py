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
import hashlib
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


# One source of truth for "this response is not an answer". backend/degradation.py is
# import-safe standalone (no relative imports, no deps) precisely so this harness can share
# the constant instead of carrying its own copy to drift against.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from degradation import (  # noqa: E402
    DEGRADED_LLM_TIMEOUT,
    DEGRADED_UPSTREAM_RATE_LIMIT,
    LM_CACHE_DISABLED_ENV,
    is_degraded_answer,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_state import corpus_run_block, corpus_state  # noqa: E402

# Degradation reasons this harness assigns itself (the backend assigns the rest).
DEGRADED_HARNESS_TIMEOUT = "harness_read_timeout"
DEGRADED_UNLABELLED = "llm_timeout_detected_by_text"


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
    # Non-None when the pipeline returned a placeholder instead of an answer. Such a run is
    # an ERROR, never a FAIL: the model was never asked the question, so its content tells
    # you nothing about the system under test. Scoring these as wrong answers is what made
    # the 2026-09-20 flag-on arm report a 60.7% pass rate it had not measured.
    degraded: Optional[str] = None
    # Reported by the backend. A run on a cache-enabled process may be a replay of an
    # earlier identical request rather than a fresh sample.
    lm_cache_enabled: Optional[bool] = None
    # The OpenRouter provider pin the backend reports for this run. Two arms compared as a
    # difference must agree on it: temperature 0 is deterministic within a provider, not
    # across two, and deepseek-chat has providers at different quantizations.
    provider_pin: Optional[object] = None
    # The endpoint's per-call witness of what served THIS run: client, model requested and
    # returned, the temperature actually on the wire, the pin sent, the provider that answered.
    # `provider_pin` above is the process CONFIGURATION; this is the call. A run with no record
    # cannot be cited for a pinned comparison, which is why its absence is an integrity
    # violation rather than a blank column.
    answer_lm: Optional[dict] = None
    generation_seconds: Optional[float] = None

    # BAML pipeline stage health for THIS run (query expansion, entity lookup, verifier).
    # `stages` on the wire is only populated when the backend honors debug=True and even then
    # is Optional[dict] -- absent entirely on an older backend -- so these are always read
    # defensively in score() and never raise. Without this, an arm where BAML query expansion
    # is erroring on every call (e.g. a missing LITELLM_PROXY_URL) still reported
    # integrity.violations == [] because the signal existed only on the one response written
    # to the per-question artifact, never per run and never rolled up.
    expansion_error: bool = False
    expansion_fallback: Optional[str] = None
    entity_lookup_mode: Optional[str] = None
    verification_failure: bool = False

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


# A 429 is not a property of the question, it is a property of the run. The backend's
# anonymous limiter is a per-day window (RATE_LIMIT, default 10/day), so once it trips
# nothing later in the arm can succeed. On 2026-09-27 the flag-off arm recorded 25 of 28
# questions as ERROR for that one reason and still wrote a report with a pass rate over the
# three questions that got through. Errors out of the denominator was the right rule and it
# held; it just cannot rescue a run whose endpoint stopped answering. Abort instead.
RUN_LEVEL_STATUSES = {429}
# Consecutive questions on which EVERY run was unscoreable. One such question can be
# legitimate - a hard question that times out three times running. Two in a row means the
# path under the harness has stopped answering, and continuing only spends requests to
# manufacture NO-DATA. On 2026-09-27 a kubectl port-forward dropped mid-arm and the flag-off
# run carried on through five more questions, one of which was a refusal gate; the arm looked
# complete and was hollow exactly where the decision lived.
MAX_CONSECUTIVE_DEAD_QUESTIONS = 2
# Degradation labels that are a property of the RUN, not of the question, in exactly the sense
# RUN_LEVEL_STATUSES means it. The UPSTREAM provider refusing to serve poisons every later
# question the same way our own limiter does.
#
# Why this is a separate gate and not covered by the HTTP one: measured 2026-09-27 in
# nf2_20260927/real_garden_genesis_3_24_misattribution_001.json, an upstream 429 reached this
# harness as HTTP 200 with "Error generating answer: litellm.RateLimitError: ..." formatted into
# the answer field, degraded=None, and was scored overall_pass=False. The status line said
# success, so the gate below never looked. The backend now labels it at the point of degradation
# (backend/degradation.py classify_generation_exception) and this set is the consumer.
RUN_LEVEL_DEGRADATIONS = {DEGRADED_UPSTREAM_RATE_LIMIT}
RUN_LEVEL_DEGRADATION_HINT = (
    "the UPSTREAM provider refused to serve. This is the provider's limit, not the backend's "
    "own limiter, so raising RATE_LIMIT will not help: wait out the window, or run against a "
    "different provider and record that you did. Every remaining question would hit the same "
    "wall, and each one would be an ERROR for a reason that has nothing to do with the system "
    "under test."
)
RUN_LEVEL_ABORT_HINT = (
    "the endpoint's rate limit is exhausted for this window (backend RATE_LIMIT, default "
    "10/day for anonymous callers). Raise it for the run or authenticate. Scored results "
    "cannot continue on this endpoint: every remaining question would be an ERROR for a "
    "reason that has nothing to do with the system under test."
)


def dead_question(runs: List["QuestionResult"]) -> bool:
    """True when no run of this question produced a scoreable response."""
    return bool(runs) and all(r.error or r.degraded for r in runs)


def run_level_fault(result: "QuestionResult") -> Optional[str]:
    """Reason to stop the whole run, or None to carry on with the next question."""
    if result.api_status in RUN_LEVEL_STATUSES:
        return f"HTTP {result.api_status}: {RUN_LEVEL_ABORT_HINT}"
    if result.degraded in RUN_LEVEL_DEGRADATIONS:
        return f"DEGRADED ({result.degraded}): {RUN_LEVEL_DEGRADATION_HINT}"
    return None


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
        result.degraded = response.get("_degraded")
        result.api_status = response.get("_status", 0)
        return result

    result.api_status = response.get("_status", 200)
    result.answer = response.get("answer", "") or ""
    result.lm_cache_enabled = response.get("lm_cache_enabled")
    result.provider_pin = response.get("openrouter_provider_pin")
    result.answer_lm = response.get("answer_lm")
    result.generation_seconds = response.get("generation_seconds")

    stages = response.get("stages")
    if isinstance(stages, dict):
        result.expansion_error = bool(stages.get("baml_error"))
        result.expansion_fallback = stages.get("baml_fallback")
        result.entity_lookup_mode = stages.get("entity_lookup_mode")
        result.verification_failure = bool(stages.get("verification_failure"))

    # Degradation check goes here - before refusal detection, before citation scoring.
    # Order is the whole point: a timeout fallback contains no [SID] citations, so a
    # content scorer reading it first concludes "refused" or "cited nothing" and produces a
    # number. Return early so no expectation is ever compared against a non-answer.
    degraded = response.get("degraded")
    if not degraded and is_degraded_answer(result.answer):
        # The backend predates the structured field, or is mis-deployed. Refuse to score it
        # rather than trusting a silent success.
        degraded = DEGRADED_UNLABELLED
    if degraded:
        result.degraded = degraded
        result.error = f"DEGRADED ({degraded}): pipeline returned a placeholder, not an answer"
        return result
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
            # debug=True so the response carries `stages`, which is where the structured
            # BAML fields (zone3_notes among them) live. Without it those fields are
            # generated and thrown away, and a prediction written against them cannot be
            # scored at all - which is what happened on 2026-09-20.
            r = client.post(endpoint, headers=headers, json={"query": question, "debug": True})
        try:
            data = r.json()
        except Exception:
            return {"_error": f"non-JSON response (status {r.status_code}): {r.text[:200]}"}
        data["_status"] = r.status_code
        if r.status_code != 200:
            data["_error"] = f"HTTP {r.status_code}: {r.text[:200]}"
        return data
    except httpx.TimeoutException as e:
        # The harness gave up waiting. Same category as a server-side timeout: no answer
        # was produced, so there is nothing to score.
        return {"_error": f"{type(e).__name__}: {e}", "_degraded": DEGRADED_HARNESS_TIMEOUT}
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


def integrity_report_lines(summary: dict) -> List[str]:
    """The `Run integrity` section of report.md. A separate function so it can be born-tested
    against a hand-built summary, and because a report that renders the pass rate but not the
    provisional flag is how a provisional arm gets quoted as a result.
    """
    integ = summary.get("integrity") or {}
    git = integ.get("git") or {}
    corpus = integ.get("corpus") or {}
    provisional = bool(git.get("provisional") or corpus.get("provisional"))
    out = ["\n## Run integrity\n\n"]
    if provisional:
        out.append("> **THIS RUN IS PROVISIONAL.** It may withdraw an earlier claim but asserts "
                   "nothing new, and it cannot be cited in an ADR or a tier change.\n\n")
    else:
        out.append("Clean on both axes: the code did not move and the corpus did not move.\n\n")
    out.append("| axis | at start | at end | moved during run |\n|---|---|---|---|\n")
    out.append("| code | `%s`%s | `%s`%s | %s |\n" % (
        str(git.get("at_start", {}).get("head", "?"))[:12],
        " DIRTY" if git.get("at_start", {}).get("dirty") else "",
        str(git.get("at_end", {}).get("head", "?"))[:12],
        " DIRTY" if git.get("at_end", {}).get("dirty") else "",
        git.get("changed_during_run")))
    out.append("| corpus | %s | %s | %s |\n" % (
        _corpus_cell(corpus.get("at_start") or {}),
        _corpus_cell(corpus.get("at_end") or {}),
        "unknown (not established at both ends)"
        if corpus.get("changed_during_run") is None else corpus.get("changed_during_run")))
    out.append("\nCorpus comparison scope: %s\n" % (corpus.get("comparison_scope") or "not recorded"))
    if corpus.get("skipped"):
        out.append("\nThe corpus fingerprint was SKIPPED for this run (--corpus-fingerprint skip): "
                   "it cannot say which corpus it scored.\n")
    for v in (integ.get("violations") or []):
        out.append("\n- **VIOLATION:** %s\n" % v)
    return out


def _corpus_cell(st: dict) -> str:
    if not st.get("available"):
        return "unread: %s" % (st.get("unavailable_reason") or "not recorded")
    return "%s chunks, text `%s`, vec `%s`" % (
        st.get("chunk_count"), str(st.get("content_sha256"))[:12],
        str(st.get("vector_sha256"))[:12] if st.get("vector_sha256") else "not hashed")


def write_markdown_report(results: List[QuestionResult], out_path: Path, summary: dict) -> None:
    lines = ["# Eval Report\n"]
    lines.append(f"**Pass rate:** {summary['passed']}/{summary['total']} ({summary['pass_pct']:.1f}%)  \n")
    lines.append(f"**Refusal correctness:** {summary['refusal_correct']}/{summary['total']}  \n")
    lines.append(f"**must_not_cite violations:** {summary['must_not_cite_violations']} (HARD FAIL if >0)  \n")
    lines.append(f"**Denominator:** {summary['denominator']} - {summary['total']} of "
                 f"{summary['attempted']} attempted  \n")
    lines.append(f"**Errors (excluded from every rate above):** {summary['errors']}, "
                 f"of which degraded (placeholder, never asked): {summary['degraded']}  \n")
    lines.append(f"**Endpoint:** `{summary['endpoint']}`  \n")
    lines.append(f"**Generated:** {summary['timestamp']}\n")

    lines.extend(integrity_report_lines(summary))

    # By-category breakdown
    lines.append("\n## By category\n\n| Category | Pass | Total | Pct |\n|---|---:|---:|---:|\n")
    for cat, stats in sorted(summary["by_category"].items()):
        lines.append(f"| {cat} | {stats['pass']} | {stats['total']} | {stats['pct']:.0f}% |\n")

    # Per-question detail
    lines.append("\n## Per-question results\n")
    for r in results:
        status = ("ERROR - NOT SCORED" if r.error and not r.degraded else
                  f"DEGRADED ({r.degraded}) - NOT SCORED" if r.degraded else
                  "PASS" if r.overall_pass else
                  "REFUSED OK" if r.expected_behavior == "refuse" and r.refusal_correct else
                  "FAIL")
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
    # Every rate below is over SCORED questions only. A question whose run errored or
    # degraded was never asked-and-answered, so counting it as a denominator member reports
    # a pass rate for a measurement that did not happen. Errors are reported separately and
    # `attempted` keeps the total visible so nothing is quietly dropped.
    attempted = len(results)
    errored = [r for r in results if r.error]
    scored = [r for r in results if not r.error]
    total = len(scored)
    passed = sum(1 for r in scored if r.overall_pass)
    refusal_correct = sum(1 for r in scored if r.refusal_correct)
    must_not_cite_violations = sum(1 for r in scored if r.must_not_cite_violated)
    errors = len(errored)
    degraded = sum(1 for r in errored if r.degraded)

    error_detail = [
        {"id": r.id, "category": r.category, "degraded": r.degraded, "error": r.error}
        for r in errored
    ]

    by_category = defaultdict(lambda: {"pass": 0, "total": 0})
    for r in scored:
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
        "attempted": attempted,
        "total": total,
        "denominator": "scored questions (errors and degraded runs excluded)",
        "passed": passed,
        "pass_pct": (100.0 * passed / total) if total else 0,
        "refusal_correct": refusal_correct,
        "must_not_cite_violations": must_not_cite_violations,
        "errors": errors,
        "degraded": degraded,
        "error_detail": error_detail,
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


# A cache replay returns in microseconds. A real generation against OpenRouter does not.
# Anything below this is a replay or a no-op, not a sample.
MIN_REAL_GENERATION_SECONDS = 0.05

# Sent once before the first scored question, through the app's own /api/search path, so the
# embedding model is resident and the first scored latency is not a cold-start outlier. It
# deliberately goes through the application rather than addressing any Ollama host directly:
# the embedding fleet in the LiteLLM model_list is 192.168.1.179/.188 (endpoints E and F,
# reserved - see gpu-servers.md), which this harness must never address. The keep_alive pin
# for those models is declared where the routing is declared (chart model_list carries
# `keep_alive: -1`, duplicated into extra_body for the chat route); it is not the harness's
# to send.
WARMUP_QUERY = "warmup request, not scored: what is this commentary?"
KEEP_ALIVE_PIN_NOTE = (
    "declared at the LiteLLM routing layer (model_list keep_alive: -1, duplicated into "
    "extra_body for the chat route); harness sends no direct-host keep_alive because the "
    "embedding fleet is endpoints E/F (reserved)"
)


def preflight(endpoint: str, auth: Optional[str], timeout: float, n_runs: int,
              allow_lm_cache: bool, do_warmup: bool,
              require_provider_pin: bool = False,
              allow_unset_temperature: bool = False) -> tuple:
    """Warm the path and verify run integrity BEFORE any question is scored.

    Returns (warmup_info, exit_code). A nonzero exit_code means: do not score anything.
    Aborting here is the point. On 2026-09-20 an in-process LM cache silently collapsed
    N=3 to N=1 and the run still printed a stability block - three hours to produce a
    number that measured one sample. The condition was visible in the first response.
    """
    info = {"warmup_ran": do_warmup, "keep_alive_pin": KEEP_ALIVE_PIN_NOTE}
    if not do_warmup:
        print("Warmup    : SKIPPED (--no-warmup); first scored latency includes cold start.\n")
        return info, 0

    print(f"Warmup    : one unscored request (embedding + generation), wall {timeout:.0f}s ...",
          flush=True)
    t0 = time.perf_counter()
    resp = call_endpoint(endpoint, WARMUP_QUERY, auth, timeout)
    info["warmup_seconds"] = round(time.perf_counter() - t0, 2)
    info["warmup_degraded"] = (resp.get("degraded") or resp.get("_degraded")
                               or (DEGRADED_UNLABELLED
                                   if is_degraded_answer(resp.get("answer") or "") else None))
    info["warmup_error"] = resp.get("_error")
    info["lm_cache_enabled"] = resp.get("lm_cache_enabled")
    info["openrouter_provider_pin"] = resp.get("openrouter_provider_pin")
    info["answer_lm"] = resp.get("answer_lm")
    # Query-expansion health is visible on the warmup response too, not just per scored run --
    # this is the cheapest place to catch it, before any question is asked. Loud, not fatal:
    # see check_run_integrity / stage_health_block for why this must never abort.
    warmup_stages = resp.get("stages")
    if isinstance(warmup_stages, dict) and warmup_stages.get("baml_error"):
        print(f"WARNING: the warmup response shows a BAML query-expansion error: "
              f"{warmup_stages.get('baml_error')!r} "
              f"(fallback={warmup_stages.get('baml_fallback')!r}). Every scored run in this arm "
              f"may be silently falling back. Check LITELLM_PROXY_URL on the server.")
    print(f"            {info['warmup_seconds']}s"
          + (f"  ERROR: {info['warmup_error']}" if info["warmup_error"] else "")
          + (f"  DEGRADED: {info['warmup_degraded']}" if info["warmup_degraded"] else ""))

    if resp.get("_status") in RUN_LEVEL_STATUSES:
        print("            " + RUN_LEVEL_ABORT_HINT)
    if info["warmup_error"] or info["warmup_degraded"]:
        print("            Warmup did not complete. The path is not healthy; scored results "
              "would be contaminated by the same condition.")
        return info, 2

    cache = info["lm_cache_enabled"]
    if n_runs > 1 and not allow_lm_cache:
        if cache is None:
            print(f"\nABORT: the endpoint did not report `lm_cache_enabled`. With --runs "
                  f"{n_runs} this harness cannot verify that the N runs are N samples "
                  f"rather than one sample replayed. Deploy a backend that reports the "
                  f"field, or pass --allow-lm-cache to record the runs as unverified.")
            return info, 3
        if cache is True:
            print(f"\nABORT: the endpoint has its LM cache ENABLED. With --runs {n_runs} the "
                  f"repeated runs would be cache replays of the first, and the stability "
                  f"block would report N/N agreement it never measured. Restart the server "
                  f"with {LM_CACHE_DISABLED_ENV}=1, or pass --allow-lm-cache.")
            return info, 3
        print("            LM cache: DISABLED on the endpoint (N runs are N samples).")

    pin = info.get("openrouter_provider_pin")
    if pin:
        print(f"            Provider PINNED: {pin}")
    elif n_runs > 1:
        # Not fatal by default: a single-arm run is still a valid measurement of itself.
        # Fatal for a comparison, because an unpinned arm mixes providers at different
        # quantizations and any small delta is unattributable.
        print("            Provider: UNPINNED. deepseek-chat has providers at different "
              "quantizations; a delta between two unpinned arms is not attributable to the "
              "change under test. Set OPENROUTER_PROVIDER_ORDER on the server.")
        if require_provider_pin:
            print("\nABORT: --require-provider-pin was given and the endpoint reports no pin.")
            return info, 3

    # Ruling 2: what the process is CONFIGURED with is not what served the call. The warmup
    # response is the cheapest place to find out whether the endpoint can say, and it catches
    # the specific hole that cost a day: the harness is run from one checkout while the SERVER
    # was started from another, so the code under test is not the code being committed. The
    # dirty-tree gate reads the harness's tree and is blind to the server's; this is not.
    alm = info.get("answer_lm")
    if not isinstance(alm, dict):
        print("\nABORT: the endpoint did not report `answer_lm` on the warmup response. It "
              "cannot say what model, temperature or provider served the call, so no arm from it "
              "can be cited for a pinned comparison. The usual cause is a server started from a "
              "different checkout than the harness. Restart the server from this working tree.")
        return info, 3

    print(f"            Answer LM: {alm.get('path')}/{alm.get('client')} "
          f"model={alm.get('model_returned') or alm.get('model_requested')} "
          f"temperature={alm.get('temperature_on_the_wire')} "
          f"served_by={alm.get('provider_served')} pin_honored={alm.get('pin_honored')}")

    # Ruling (2026-09-28, Chris): a run without an explicit temperature must refuse. The
    # OFF (DSPy) answer path historically sent NO temperature field while the BAML path
    # sends 0, so every OFF-vs-ON arm varied two things at once -- see
    # docs/audits/RESULT_temperature_check_laneA_20260928.md for the measured effect. 0.0 is
    # a valid EXPLICIT value and is falsy, so this is an isinstance check, never a
    # truthiness check.
    warmup_temp = alm.get("temperature_on_the_wire")
    temp_is_explicit = isinstance(warmup_temp, (int, float)) and not isinstance(warmup_temp, bool)
    if not temp_is_explicit:
        if not allow_unset_temperature:
            print(f"\nABORT: the warmup's answer_lm reported "
                  f"temperature_on_the_wire={warmup_temp!r} -- not an explicit numeric value. "
                  f"An unset temperature means the provider's own default applies and is not "
                  f"recorded, which is the confound measured in "
                  f"docs/audits/RESULT_temperature_check_laneA_20260928.md. Set "
                  f"GILL_ANSWER_TEMPERATURE=0 on the server (read at process start inside "
                  f"`lifespan` in backend/main.py -- the server must be RESTARTED for this to "
                  f"take effect), or pass --allow-unset-temperature if you deliberately want an "
                  f"unpinned-temperature run.")
            return info, 3
        print(f"WARNING: temperature_on_the_wire={warmup_temp!r} is not an explicit numeric "
              f"value and --allow-unset-temperature was passed. This run's temperature is "
              f"UNPINNED: the provider's own default applies and is not recorded, which is the "
              f"confound measured in docs/audits/RESULT_temperature_check_laneA_20260928.md.")

    if alm.get("pin_honored") is False:
        print(f"\nABORT: the warmup was served by {alm.get('provider_served')!r}, which is "
              f"OUTSIDE the pin {alm.get('provider_pin')!r}. The pin was sent and not honored; "
              f"every run of this arm would be on an unintended provider.")
        return info, 3
    if alm.get("provider_served") is None:
        print(f"            Provider served: UNREADABLE "
              f"({alm.get('provider_served_source')}). The pin cannot be verified on this arm; "
              f"unchecked is not honored.")
    return info, 0


def run_level_tally(run_ledger: Dict[str, List["QuestionResult"]]) -> dict:
    """Count RUNS, not questions.

    summarize() reports one representative result per question, so a question that survived
    a partial failure contributes nothing to its error/degraded counters. Predictions about
    the harness ("<= 6 degraded runs across 168") are written in runs, and a summary that
    cannot answer them sends you to the raw log to score your own prediction.
    """
    runs = [r for rs in run_ledger.values() for r in rs]
    degraded = sum(1 for r in runs if r.degraded)
    errored = sum(1 for r in runs if r.error and not r.degraded)
    return {
        "total": len(runs),
        "scored": sum(1 for r in runs if not r.error),
        "degraded": degraded,
        "errored": errored,
        "counts": "runs, not questions; degraded and errored are disjoint",
    }


def classify_stability(scored_passes: List[bool], n_runs: int) -> str:
    """Stability label from the SCORED runs of one question.

    `scored_passes` holds one entry per run that produced an answer - errored and degraded
    runs are absent, not False. An empty list is NO-DATA: the question was never measured,
    so it is neither stable nor flaky, and above all not a failure.
    """
    if not scored_passes:
        return "NO-DATA"
    if all(scored_passes):
        return "STABLE-PASS"
    if not any(scored_passes):
        return "STABLE-FAIL"
    return "FLAKY"


ANSWER_LM_KEYS = ("path", "client", "model_requested", "model_returned",
                  "temperature_on_the_wire", "provider_pin", "provider_served",
                  "provider_served_source", "pin_honored")


def answer_lm_rows(run_ledger: Dict[str, List[QuestionResult]]) -> tuple:
    """(records, qids missing a record) over the runs that were actually SCORED.

    Errored and degraded runs are excluded: the model was never asked, so the absence of a
    per-call record there is not a gap in the evidence, and counting it as one would make a
    timeout read as a mis-configured endpoint.
    """
    rows, missing = [], []
    for qid, runs in run_ledger.items():
        for r in runs:
            if r.error or r.degraded:
                continue
            if isinstance(r.answer_lm, dict):
                rows.append(r.answer_lm)
            else:
                missing.append(qid)
    return rows, sorted(set(missing))


def _served_counts(distinct: List[dict]) -> Dict[Any, int]:
    """{provider_served: scored runs}, skipping rows that did not report one."""
    out: Dict[Any, int] = {}
    for d in distinct:
        served = d.get("provider_served")
        if served in (None, ""):
            continue
        out[served] = out.get(served, 0) + d["runs"]
    return out


def answer_lm_tally(run_ledger: Dict[str, List[QuestionResult]]) -> dict:
    """Distinct (client, model, temperature, pin, provider served) combinations across the arm.

    Ruling 2: the arm has to be able to say what served it. One row means one configuration
    throughout. More than one row means the arm is a mixture -- which is a fact about the arm,
    not about the code under test, and the summary has to carry it either way.
    """
    rows, missing = answer_lm_rows(run_ledger)
    counts: Dict[str, list] = {}
    for rec in rows:
        sub = {k: rec.get(k) for k in ANSWER_LM_KEYS}
        key = json.dumps(sub, sort_keys=True, default=str)
        counts.setdefault(key, [sub, 0])[1] += 1
    distinct = [dict(sub, runs=n) for sub, n in
                sorted(counts.values(), key=lambda pair: (-pair[1], json.dumps(pair[0], sort_keys=True, default=str)))]
    return {
        "scored_runs_with_a_record": len(rows),
        "questions_missing_a_record": missing,
        "distinct": distinct,
        # Separate counts on purpose. False is a measured violation; None is "not checkable from
        # what we have" -- an unpinned call, or a response whose provider could not be read.
        "runs_pin_honored_false": sum(d["runs"] for d in distinct if d.get("pin_honored") is False),
        "runs_pin_unchecked": sum(d["runs"] for d in distinct if d.get("pin_honored") is None),
        # Served provider, counted independently of the pin. An UNPINNED arm has one pin
        # value (None) and pin_honored None on every run, so neither pin gate above can
        # see a two-provider mixture. floor_20260928 was served DeepInfra 61 / StreamLake
        # 17 in arm A and 39 / 39 in arm B, and reported no violation for it.
        "runs_by_provider_served": {
            str(k): v for k, v in sorted(_served_counts(distinct).items())
        },
        "distinct_provider_served": sorted(str(k) for k in _served_counts(distinct)),
    }


def answer_temperature_block(run_ledger: Dict[str, List[QuestionResult]]) -> dict:
    """Distinct `temperature_on_the_wire` values seen across the arm, split into explicit
    (a number was sent -- 0.0 counts), absent (the endpoint recorded that no field was sent),
    and unrecorded (no answer_lm record, or no `temperature_on_the_wire` key in it).

    Only SCORED runs count -- see answer_lm_rows for why an errored or degraded run is not a
    gap in the evidence. Ruling (2026-09-28, Chris): a run without an explicit temperature must
    refuse, and 0.0 is a valid explicit value that is falsy -- every branch below is an
    isinstance check, never a truthiness check, so the exact value now required cannot fall
    silently into "absent".
    """
    values = []
    runs_explicit = 0
    runs_absent = 0
    runs_unrecorded = 0
    for runs in run_ledger.values():
        for r in runs:
            if r.error or r.degraded:
                continue
            alm = r.answer_lm
            if isinstance(alm, dict) and "temperature_on_the_wire" in alm:
                temp = alm["temperature_on_the_wire"]
                values.append(temp)
                if isinstance(temp, (int, float)) and not isinstance(temp, bool):
                    runs_explicit += 1
                elif temp == "<absent from optional_params>":
                    runs_absent += 1
                else:
                    runs_unrecorded += 1
            else:
                runs_unrecorded += 1
    return {
        "distinct": sorted(set(values), key=repr),
        "runs_explicit": runs_explicit,
        "runs_absent": runs_absent,
        "runs_unrecorded": runs_unrecorded,
    }


def stage_health_block(run_ledger: Dict[str, List[QuestionResult]]) -> dict:
    """Per-stage LM health across the arm: BAML query expansion, entity lookup mode, and the
    quote-placement verifier -- the pipeline stages between the answer LM and the score. Query
    expansion has been erroring on this machine (missing LITELLM_PROXY_URL) on nearly every
    call, and every published arm still reported integrity.violations == [] because the signal
    lived only on the single response written to the per-question artifact and was never rolled
    up across runs. See QuestionResult.expansion_error / score() for where this is captured.

    Only SCORED runs count -- see answer_temperature_block for why an errored or degraded run
    is not a gap in the evidence, it is simply not a measurement.
    """
    scored = [r for runs in run_ledger.values() for r in runs if not r.error and not r.degraded]
    errored = sum(1 for r in scored if r.expansion_error)
    fallbacks = sorted({(r.expansion_fallback if r.expansion_fallback is not None else "<none>")
                         for r in scored})
    modes = sorted({r.entity_lookup_mode for r in scored}, key=repr)
    mode_counts: Dict[str, int] = {}
    for r in scored:
        mode_counts[r.entity_lookup_mode] = mode_counts.get(r.entity_lookup_mode, 0) + 1
    return {
        "scored_runs": len(scored),
        "expansion": {
            "errored": errored,
            "healthy": len(scored) - errored,
            "distinct_fallback": fallbacks,
        },
        "entity_lookup": {
            "distinct_mode": modes,
            "counts": mode_counts,
        },
        "verifier": {"failures": sum(1 for r in scored if r.verification_failure)},
    }


def check_run_integrity(run_ledger: Dict[str, List[QuestionResult]], allow_lm_cache: bool,
                         allow_unset_temperature: bool = False) -> list:
    """Post-run assertion: every scored run was its own generation, not a replay."""
    violations = []
    for qid, runs in run_ledger.items():
        scored = [r for r in runs if not r.error]
        if not scored:
            continue
        if not allow_lm_cache:
            replays = [r for r in scored
                       if r.generation_seconds is not None
                       and r.generation_seconds < MIN_REAL_GENERATION_SECONDS]
            if replays:
                violations.append(
                    f"{qid}: {len(replays)}/{len(scored)} scored run(s) generated in "
                    f"<{MIN_REAL_GENERATION_SECONDS}s - cache replay, not a sample")
            cached = [r for r in scored if r.lm_cache_enabled]
            if cached:
                violations.append(f"{qid}: {len(cached)} scored run(s) on a cache-enabled endpoint")
    # A provider pin that CHANGES mid-run means the arm spans two numeric builds of the
    # model. That is not a sample of one system; it is a mixture, and it was invisible
    # before this check because OpenRouter names the provider only when it errors.
    pins = {json.dumps(r.provider_pin, sort_keys=True)
            for rs in run_ledger.values() for r in rs if not r.error}
    if len(pins) > 1:
        violations.append(
            f"the provider pin changed during the run ({len(pins)} distinct values: "
            f"{sorted(pins)}) - the arm spans more than one provider configuration")
    # Ruling 2. A pin SENT is not a pin HONORED: OpenRouter echoes the serving provider, so a
    # violation is measurable and must abort rather than be read past in a summary. `None` is
    # not a violation -- see answer_lm_record.pin_honored for why it is a third state.
    lm = answer_lm_tally(run_ledger)
    if lm["runs_pin_honored_false"]:
        served = sorted({str(d.get("provider_served")) for d in lm["distinct"]
                         if d.get("pin_honored") is False})
        violations.append(
            f"{lm['runs_pin_honored_false']} scored run(s) were served by a provider OUTSIDE "
            f"the pin ({', '.join(served)}) - the pin was sent and not honored")
    # A gate has to be able to see the failure it was built for. The two gates above watch
    # the PIN; this one watches what actually served the calls, which is the thing that
    # changes the measurement. Not gated behind the pin being set, because the arms that
    # motivated it had no pin at all.
    served = lm["distinct_provider_served"]
    if len(served) > 1:
        mix = ", ".join(f"{k}={v}" for k, v in sorted(lm["runs_by_provider_served"].items()))
        violations.append(
            f"the arm was served by {len(served)} different providers ({mix}) - "
            f"temperature 0 is deterministic WITHIN a provider, not across two, so this "
            f"arm measures a provider mixture as though it were model behaviour. Pin it "
            f"with OPENROUTER_PROVIDER_ORDER (see backend/degradation.py provider_pin).")
    if lm["questions_missing_a_record"]:
        miss = lm["questions_missing_a_record"]
        violations.append(
            f"{len(miss)} question(s) produced a scored run with no per-call answer_lm record "
            f"({', '.join(miss[:6])}{' ...' if len(miss) > 6 else ''}) - the endpoint cannot "
            f"say what served them, so this arm cannot be cited for a pinned comparison")
    temp = answer_temperature_block(run_ledger)
    if not allow_unset_temperature and (temp["runs_absent"] + temp["runs_unrecorded"]) > 0:
        violations.append(
            f"{temp['runs_absent']} scored run(s) sent no explicit temperature and "
            f"{temp['runs_unrecorded']} scored run(s) have no recorded temperature at all - an "
            f"unpinned temperature is the confound measured in "
            f"docs/audits/RESULT_temperature_check_laneA_20260928.md. Pass "
            f"--allow-unset-temperature if this is deliberate.")
    # Not an abort, and not gated behind a flag: the BAML query-expansion path is down on
    # this machine right now (missing LITELLM_PROXY_URL) and aborting every run over it would
    # brick the harness while that's true. This only records the arm as not-clean and names
    # the count, so it can never be silently compared against an arm with different expansion
    # health -- see stage_health_block.
    stage_health = stage_health_block(run_ledger)
    if stage_health["expansion"]["errored"] > 0:
        violations.append(
            f"{stage_health['expansion']['errored']}/{stage_health['scored_runs']} scored "
            f"run(s) had a BAML query-expansion error - this arm is not comparable against "
            f"an arm with different expansion health")
    return violations


def git_state() -> Dict[str, Any]:
    """HEAD and dirtiness of the tree the harness is running from, asked of git itself.

    `git_head` alone over a dirty tree is decoration: it names a commit whose contents are not what
    ran. So `dirty` comes from `git status --porcelain`, which already knows about autocrlf and
    whatever else this platform does to line endings -- hand-rolling that check is how a clean tree
    gets reported as dirty and a dirty one as clean.

    Captured at run START and again at run END, because on 2026-09-27 noise-floor arm 2 had three
    commits land mid-run and nothing in the artifact recorded it; the deviation had to be
    reconstructed afterwards from commit timestamps. Two samples make that visible in the run's own
    output. An error is RECORDED, not swallowed: a summary that cannot say what it ran is worse than
    one that says it could not find out.
    """
    import subprocess
    out: Dict[str, Any] = {}
    for key, cmd in (("head", ["git", "rev-parse", "HEAD"]),
                     ("porcelain", ["git", "status", "--porcelain"])):
        try:
            r = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=30)
        except Exception as exc:  # git missing, or not a repo
            out[key + "_error"] = f"{type(exc).__name__}: {exc}"
            continue
        if r.returncode != 0:
            out[key + "_error"] = (r.stderr or "").strip()[:200] or f"rc={r.returncode}"
            continue
        if key == "head":
            out["head"] = r.stdout.strip()
        else:
            lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
            out["dirty"] = bool(lines)
            out["dirty_paths"] = len(lines)
            # The paths themselves, capped: which files were dirty is the whole question when a
            # result has to be judged provisional or not.
            out["dirty_sample"] = [ln[:120] for ln in lines[:20]]
    return out


def dirty_tree_refusal(at_start: Dict[str, Any], allow_dirty: bool) -> Optional[str]:
    """The message that aborts a run over a dirty tree, or None to proceed.

    Ruling 1 (2026-09-27, Chris), binding on both lanes: a run is clean only if git_state() at
    start and at end are both clean and identical. The END half cannot be a gate -- by then the
    run has happened -- so it is recorded in `integrity.git.provisional` and printed loudly. The
    START half can be, and is: on 2026-09-27 both noise-floor arms ran over a dirty tree and the
    pair is permanently provisional as a result. Recording the fact was not enough to prevent it.

    A pure function returning a string rather than an inline sys.exit, so the refusal can be
    born-tested without running an eval.
    """
    if not at_start.get("dirty"):
        return None
    n = at_start.get("dirty_paths", "?")
    sample = "\n".join("    " + ln for ln in at_start.get("dirty_sample", [])[:10])
    if allow_dirty:
        print(f"WARNING: tree is DIRTY ({n} path(s)) and --allow-dirty-tree was passed. This run "
              f"is PROVISIONAL: it may withdraw an earlier claim but asserts nothing new, and it "
              f"cannot be cited in an ADR or a tier change.")
        return None
    return (f"REFUSING to start: the working tree is DIRTY ({n} path(s))."
            f"\n{sample}\n"
            f"Ruling 1: a run is clean only if git_state() at start and end are both clean and "
            f"identical. Commit (or stash) first, then rerun -- a provisional arm cannot be "
            f"compared against a clean one. Pass --allow-dirty-tree if you deliberately want a "
            f"provisional run, and expect it to be labelled one.")


def git_run_block(at_start: Dict[str, Any], at_end: Dict[str, Any]) -> Dict[str, Any]:
    """The `integrity.git` block. A function rather than a dict literal inside main() so the
    comparison can be born-tested: asserting that the SOURCE contains "changed_during_run" proves
    nothing about whether it is ever True."""
    return {
        "at_start": at_start,
        "at_end": at_end,
        "changed_during_run": at_start != at_end,
        "provisional": bool(at_start.get("dirty") or at_end.get("dirty")
                            or at_start != at_end
                            or any(k.endswith("_error") for k in at_start)),
        "note": "provisional means this run cannot be cited in an ADR or a tier change (ruling 4): "
                "the tree was dirty, or HEAD/the tree moved WHILE questions were being scored, or "
                "git state could not be read at all",
    }


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--endpoint", default=os.getenv("EVAL_ENDPOINT", DEFAULT_ENDPOINT),
                        help="The /api/search endpoint to evaluate.")
    parser.add_argument("--reference-set", default=str(DEFAULT_REF_SET),
                        help="Path to JSONL reference set.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR),
                        help="Directory to write per-question results, summary.json, report.md.")
    parser.add_argument("--ids", nargs="*", help="Run only these question IDs.")
    parser.add_argument("--runs", type=int, default=5,
                        help="Run each question N times and report per-question stability. "
                             "The eval binary carries +-several-question run-to-run noise from "
                             "generation nondeterminism at the verbatim-verification/paraphrase "
                             "boundary (ADR-0014 meta-finding). With --runs > 1 a question is "
                             "classified STABLE-PASS (N/N), STABLE-FAIL (0/N), or FLAKY (mixed). "
                             "Regression claims should be made only on STABLE questions; FLAKY is "
                             "the noise band. Default 5 per ruling 1 (2026-09-27): the pinned "
                             "floor pair showed N=3 cannot discriminate a question at p~0.83 "
                             "from a deterministic pass (3/3 about 58%% of the time), and that "
                             "is the whole of the 10 class changes measured between two "
                             "IDENTICAL arms. N=1 classifies nothing at all.")
    parser.add_argument("--baseline", help="Path to baseline summary JSON for regression comparison.")
    parser.add_argument("--timeout", type=float, default=200.0,
                        help="Per-question HARNESS timeout in seconds. Must exceed the server's "
                             "own generation wall (LLM_WALL_SECONDS, 180s) so a server-side "
                             "timeout arrives as a labelled degraded response rather than as a "
                             "harness read timeout with no detail.")
    parser.add_argument("--require-provider-pin", action="store_true",
                        help="abort unless the endpoint reports a pinned model provider. Use for "
                             "any arm whose result will be compared against another arm.")
    parser.add_argument("--allow-lm-cache", action="store_true",
                        help="Permit scoring against an endpoint whose LM cache is enabled. "
                             "With --runs > 1 this makes the extra runs cache replays of the "
                             "first, so stability figures are meaningless; the run is recorded "
                             "as unverified. Off by default, and the harness aborts instead.")
    parser.add_argument("--no-warmup", action="store_true",
                        help="Skip the unscored warmup request. The first scored question then "
                             "carries any model cold-start in its latency.")
    parser.add_argument("--regression-threshold", type=float, default=5.0,
                        help="Pass-rate drop (percentage points) that triggers a hard fail vs baseline.")
    parser.add_argument("--allow-dirty-tree", action="store_true",
                        help="Permit starting over a dirty working tree. The run is then "
                             "PROVISIONAL (ruling 1): it may withdraw an earlier claim but "
                             "asserts nothing new, and cannot be cited in an ADR or a tier "
                             "change. Off by default, and the harness aborts instead.")
    parser.add_argument("--allow-unset-temperature", action="store_true",
                        help="Permit starting when the answer path sends no explicit "
                             "temperature. Without this flag the harness REFUSES: an unset "
                             "temperature means the provider's own default applies and is not "
                             "recorded, so the run cannot say what generated it. This is the "
                             "OFF-vs-ON confound (DSPy sent none, BAML sends 0) measured in "
                             "docs/audits/RESULT_temperature_check_laneA_20260928.md, where the "
                             "effect was large -- 0%% is a valid explicit value and is not the "
                             "same thing as unset. Off by default, and the harness aborts "
                             "instead.")
    parser.add_argument("--corpus-fingerprint", choices=("vectors", "text", "skip"),
                        default="vectors",
                        help="Fingerprint the Weaviate corpus at run start and end and record it in integrity.corpus (ruling 1). `vectors` hashes text AND embeddings (measured 80s per sample against 7294 chunks) and is the only setting that can see a re-vectorisation; `text` hashes text only (7s) and is blind to one; `skip` records nothing and makes the run PROVISIONAL, like --allow-dirty-tree.")
    parser.add_argument("--auth-token", default=os.getenv("EVAL_AUTH_TOKEN"),
                        help="Optional Bearer token for authenticated endpoint testing.")
    args = parser.parse_args(argv)

    load_dotenv(REPO_ROOT / ".env")

    git_at_start = git_state()
    refusal = dirty_tree_refusal(git_at_start, args.allow_dirty_tree)
    if refusal:
        print(refusal)
        print("Nothing was scored.")
        return 2
    questions = load_reference_set(Path(args.reference_set), args.ids)
    out_dir = Path(args.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Endpoint  : {args.endpoint}")
    print(f"Questions : {len(questions)}")
    print(f"Output dir: {out_dir}\n")

    n_runs = max(1, args.runs)

    warmup_info, pre_rc = preflight(args.endpoint, args.auth_token, args.timeout, n_runs,
                                    args.allow_lm_cache, not args.no_warmup,
                                    args.require_provider_pin,
                                    args.allow_unset_temperature)
    if pre_rc:
        print("Nothing was scored. Fix the condition above and rerun.")
        return pre_rc

    # Sampled AFTER preflight: preflight refuses runs (a missing answer_lm record, an
    # unpinned provider, a live LM cache) and a refused run must not first spend 80s
    # fingerprinting a corpus nothing will be scored against. It is still before the
    # first scored question, which is the property that matters.
    corpus_skip = args.corpus_fingerprint == "skip"
    if corpus_skip:
        corpus_at_start = None
        print("Corpus    : fingerprint SKIPPED (--corpus-fingerprint skip) -- this run is "
              "PROVISIONAL and cannot be cited.")
    else:
        _vec = args.corpus_fingerprint == "vectors"
        print(f"Corpus    : fingerprinting (vectors={_vec}) ...", end=" ", flush=True)
        corpus_at_start = corpus_state(include_vectors=_vec)
        if corpus_at_start["available"]:
            print(f"{corpus_at_start['chunk_count']} chunks, text "
                  f"{str(corpus_at_start['content_sha256'])[:12]}, vec "
                  f"{str(corpus_at_start['vector_sha256'])[:12]} "
                  f"({corpus_at_start['seconds']}s)")
        else:
            print(f"UNREAD: {corpus_at_start['unavailable_reason']}")
            print("    The run proceeds -- retrieval reaches Weaviate over gRPC and this read "
                  "is REST -- but it is PROVISIONAL: it cannot state which corpus it scored.")

    results: List[QuestionResult] = []
    # Per-question run ledger. Full results, not booleans: a run that errored or degraded is
    # not a False, it is an absence, and stability must be computed over what was measured.
    run_ledger: Dict[str, List[QuestionResult]] = {}
    abort_reason: Optional[str] = None
    consecutive_dead = 0
    for i, q in enumerate(questions, 1):
        print(f"[{i:2d}/{len(questions)}] {q['id']}: {q['question'][:70]}...", flush=True)
        runs: List[QuestionResult] = []
        responses = []
        for run_idx in range(n_runs):
            t0 = time.perf_counter()
            response = call_endpoint(args.endpoint, q["question"], args.auth_token, args.timeout)
            elapsed = time.perf_counter() - t0
            r = score(q, response, elapsed)
            runs.append(r)
            responses.append(response)
            if n_runs > 1:
                verdict = ("ERROR" if r.error and not r.degraded else
                           f"DEGRADED ({r.degraded})" if r.degraded else
                           "PASS" if r.overall_pass else "FAIL")
                gen = ("" if r.generation_seconds is None
                       else f"  gen={r.generation_seconds:.2f}s")
                print(f"     run {run_idx+1}/{n_runs}: {verdict}{gen}", flush=True)
            abort_reason = run_level_fault(r)
            if abort_reason:
                break
        run_ledger[q["id"]] = runs
        if dead_question(runs):
            consecutive_dead += 1
            if not abort_reason and consecutive_dead >= MAX_CONSECUTIVE_DEAD_QUESTIONS:
                abort_reason = (
                    f"{consecutive_dead} consecutive questions produced no scoreable run at "
                    f"all. The path under the harness has stopped answering; every further "
                    f"question would be NO-DATA for a reason that has nothing to do with the "
                    f"system under test. Last error: {runs[-1].error}"
                )
        else:
            consecutive_dead = 0
        if abort_reason:
            print()
            print("ABORTED: " + abort_reason)
            print("No report and no summary are written. The remaining questions were never "
                  "asked, and a summary over the few that got through would describe a run "
                  "that did not happen.")
            # The per-question files already on disk STAY. Deleting a measurement that was
            # actually taken is a silent drop. But the floor report's own complaint was that
            # the leftover directory looked like a run to a later reader, so the fragments are
            # kept AND named: a marker file, so nothing has to infer the state of this
            # directory from what happens to be missing.
            last = runs[-1] if runs else None
            marker = {
                "aborted": True,
                "reason": abort_reason,
                "at": {"question_id": q["id"], "question_index": i,
                       "of_questions": len(questions),
                       "runs_attempted_on_this_question": len(runs), "of_runs": n_runs},
                "last_run": ({"api_status": last.api_status, "degraded": last.degraded,
                              "error": last.error} if last else None),
                "question_files_present": sorted(
                    f.stem for f in out_dir.glob("*.json") if f.name != "ABORTED.json"),
                "what_this_directory_is": (
                    "NOT A RUN. There is no summary.json and no report.md, and there never "
                    "will be for this attempt. The per-question files are the questions that "
                    "were asked before the abort; they are kept because a measurement that was "
                    "taken must not be deleted, NOT because they constitute a result. Do not "
                    "publish this directory and do not compare against it. Rerun from the top."),
                "ruling": "2026-09-27 ruling 4 follow-through: a run-level fault leaves a marker",
            }
            (out_dir / "ABORTED.json").write_text(
                json.dumps(marker, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"Wrote {out_dir / 'ABORTED.json'}: "
                  f"{len(marker['question_files_present'])} question file(s) kept and marked "
                  f"as fragments, not as a run.")
            return 5

        # Representative row: the last SCORED run. A trailing timeout used to become the row
        # for the whole question, which is how a placeholder response ended up scored as a
        # content failure. If nothing scored, the row carries the error and is excluded.
        scored_runs = [r for r in runs if not r.error]
        last_r = scored_runs[-1] if scored_runs else runs[-1]
        last_response = responses[runs.index(last_r)]
        results.append(last_r)

        # Per-question raw record: the representative run, plus every run's verdict so an
        # error is visible in the artifact and not just in the console.
        (out_dir / f"{q['id']}.json").write_text(
            json.dumps({"question": q, "response": last_response, "score": asdict(last_r),
                        "run_passes": [bool(r.overall_pass) for r in scored_runs],
                        "runs": [{"pass": bool(r.overall_pass), "error": r.error,
                                  "degraded": r.degraded, "elapsed_s": r.elapsed_s,
                                  "generation_seconds": r.generation_seconds,
                                  "answer_sha16": (hashlib.sha256((r.answer or "").encode("utf-8")).hexdigest()[:16]
                                                    if (r.answer or "") else None),
                                  "answer_chars": len(r.answer or ""),
                                  "temperature_on_the_wire": ((r.answer_lm or {}).get("temperature_on_the_wire")
                                                                if isinstance(r.answer_lm, dict) else None),
                                  "provider_served": ((r.answer_lm or {}).get("provider_served")
                                                       if isinstance(r.answer_lm, dict) else None),
                                  "provider_pin": ((r.answer_lm or {}).get("provider_pin")
                                                    if isinstance(r.answer_lm, dict) else None),
                                  "pin_honored": ((r.answer_lm or {}).get("pin_honored")
                                                   if isinstance(r.answer_lm, dict) else None),
                                  "expansion_error": r.expansion_error,
                                  "expansion_fallback": r.expansion_fallback,
                                  "entity_lookup_mode": r.entity_lookup_mode,
                                  "verification_failure": r.verification_failure}
                                 for r in runs]},
                       indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        if n_runs > 1:
            n_valid = len(scored_runs)
            n_pass = sum(1 for r in scored_runs if r.overall_pass)
            label = classify_stability([bool(r.overall_pass) for r in scored_runs], n_runs)
            suffix = f"  ({n_runs - n_valid} of {n_runs} runs unscoreable)" if n_valid < n_runs else ""
            print(f"   [{label}] {n_pass}/{n_valid} passed{suffix}")
        else:
            status = "PASS" if last_r.overall_pass else "FAIL"
            if last_r.error:
                print(f"   [{status}] error: {last_r.error}")
            else:
                print(
                    f"   [{status}] refusal_ok={last_r.refusal_correct}  "
                    f"must_cite={last_r.must_cite_recall:.0%}  "
                    f"should_cite={last_r.should_cite_recall:.0%}  "
                    f"latency={last_r.elapsed_s}s"
                    + (f"  must_not_cite_HIT={last_r.must_not_cite_hits}" if last_r.must_not_cite_violated else "")
                )

    summary = summarize(results, args.endpoint)
    # ADR-0014 stability block: classify each question across the N runs so
    # a code change is gated on STABLE flips (the path touched), not on the
    # noisy total. FLAKY questions are the run-to-run noise band and must
    # not be counted as regressions.
    summary["warmup"] = warmup_info
    # `errors`/`degraded` in summarize() are QUESTION-scoped: they count questions whose
    # scored result died. A question that still classified (one timeout out of three runs)
    # never reaches them, so run-level degradation was invisible - and predictions about
    # this harness are written in RUNS. Count runs here, where the ledger exists.
    summary["runs"] = run_level_tally(run_ledger)
    integrity_violations = check_run_integrity(run_ledger, args.allow_lm_cache,
                                               args.allow_unset_temperature)
    summary["integrity"] = {
        "lm_cache_allowed": bool(args.allow_lm_cache),
        "openrouter_provider_pin": warmup_info.get("openrouter_provider_pin"),
        "min_real_generation_seconds": MIN_REAL_GENERATION_SECONDS,
        "violations": integrity_violations,
    }
    summary["answer_lm"] = answer_lm_tally(run_ledger)
    summary["integrity"]["git"] = git_run_block(git_at_start, git_state())
    summary["integrity"]["answer_temperature"] = answer_temperature_block(run_ledger)
    summary["integrity"]["stage_health"] = stage_health_block(run_ledger)
    if corpus_skip:
        _unread = {"available": False,
                   "unavailable_reason": "unavailable:--corpus-fingerprint-skip",
                   "weaviate_url": None, "include_vectors": False, "counts": None,
                   "chunk_count": None, "content_sha256": None, "vector_sha256": None,
                   "n_hashed": None, "n_vectors_hashed": None, "seconds": None}
        summary["integrity"]["corpus"] = corpus_run_block(_unread, _unread, skipped=True)
    else:
        summary["integrity"]["corpus"] = corpus_run_block(
            corpus_at_start,
            corpus_state(include_vectors=args.corpus_fingerprint == "vectors"),
            skipped=False)
    _c = summary["integrity"]["corpus"]
    # A corpus that MOVED is a violation: the arm measured a moving target. A corpus that
    # could not be READ is provisional only -- see corpus_state for why the two are not the
    # same severity, and why neither is ever reported as "unchanged".
    integrity_violations.extend(_c["violations"])
    summary["integrity"]["violations"] = integrity_violations
    if _c["changed_during_run"]:
        print("")
        print("*** THE CORPUS CHANGED WHILE THIS RUN WAS SCORING (ruling 1) ***")
        for v in _c["violations"]:
            print("    " + v)
    elif _c["changed_during_run"] is None:
        print("")
        print("Corpus state was NOT established at both ends: "
              + str(_c["at_start"].get("unavailable_reason") or "")
              + " / " + str(_c["at_end"].get("unavailable_reason") or ""))
        print("    This run is PROVISIONAL on the corpus axis. It is not a violation: the\n"
              "    answers that were scored were really scored.")
    else:
        print(f"Corpus is UNCHANGED across the run ({_c['comparison_scope']}): "
              f"{_c['at_start']['chunk_count']} chunks, text "
              f"{str(_c['at_start']['content_sha256'])[:12]}.")
    _g = summary["integrity"]["git"]
    if _g["provisional"]:
        print("")
        print("*** THIS RUN IS PROVISIONAL (ruling 1) ***")
        print(f"    dirty at start: {_g['at_start'].get('dirty')}   "
              f"dirty at end: {_g['at_end'].get('dirty')}   "
              f"HEAD or tree moved mid-run: {_g['changed_during_run']}")
        print("    It may withdraw an earlier claim but asserts nothing new, and cannot be cited")
        print("    in an ADR or a tier change.")
    else:
        print("")
        print("Run is CLEAN: tree clean and identical at start and end (ruling 1).")
    if n_runs > 1:
        # Classification is over SCORED runs only. A question with no scored run is NO-DATA:
        # not a STABLE-FAIL, not FLAKY, not anything. Calling it STABLE-FAIL is how two
        # unscoreable refusal questions were read as a refusal-gate regression on 2026-09-20.
        valid = {qid: [bool(r.overall_pass) for r in runs if not r.error]
                 for qid, runs in run_ledger.items()}
        labels = {qid: classify_stability(p, n_runs) for qid, p in valid.items()}
        no_data = [qid for qid, lab in labels.items() if lab == "NO-DATA"]
        stable_pass = [qid for qid, lab in labels.items() if lab == "STABLE-PASS"]
        stable_fail = [qid for qid, lab in labels.items() if lab == "STABLE-FAIL"]
        flaky = [(qid, sum(valid[qid]), len(valid[qid]))
                 for qid, lab in labels.items() if lab == "FLAKY"]
        partial = {qid: f"{len(p)}/{n_runs} runs scoreable"
                   for qid, p in valid.items() if p and len(p) < n_runs}
        summary["runs_per_question"] = n_runs
        summary["stability"] = {
            "stable_pass": len(stable_pass),
            "stable_fail": len(stable_fail),
            "flaky": len(flaky),
            "no_data": len(no_data),
            "flaky_detail": {qid: f"{np}/{tot}" for qid, np, tot in flaky},
            "stable_fail_ids": sorted(stable_fail),
            "no_data_ids": sorted(no_data),
            "partial_detail": partial,
            "classified_over": "scored runs only; unscoreable runs are not failures",
        }

    print(f"\n{'='*70}\nSUMMARY\n{'='*70}")
    print(f"Questions attempted      : {summary['attempted']}")
    print(f"Questions scored         : {summary['total']}  (the denominator below)")
    print(f"Pass rate                : {summary['passed']}/{summary['total']} ({summary['pass_pct']:.1f}%)")
    print(f"Refusal correctness      : {summary['refusal_correct']}/{summary['total']}")
    print(f"must_not_cite violations : {summary['must_not_cite_violations']}")
    print(f"Questions with no score  : {summary['errors']}  of which degraded: {summary['degraded']}")
    rt = summary.get("runs")
    if rt:
        print(f"Runs                     : {rt['total']} total, {rt['scored']} scored, "
              f"{rt['degraded']} degraded, {rt['errored']} errored")
    for e in summary["error_detail"]:
        print(f"    {e['id']:40} {e['degraded'] or 'error'}: {e['error']}")
    _lm = summary.get("answer_lm") or {}
    if _lm.get("distinct"):
        print(f"\nAnswer LM (per call, {_lm['scored_runs_with_a_record']} scored run(s) recorded):")
        for d in _lm["distinct"]:
            print(f"  {d['runs']:>3} run(s)  {d.get('path')}/{d.get('client')}  "
                  f"model={d.get('model_returned') or d.get('model_requested')}  "
                  f"temperature={d.get('temperature_on_the_wire')}  "
                  f"served_by={d.get('provider_served')}  pin_honored={d.get('pin_honored')}")
            print(f"           provider_served_source={d.get('provider_served_source')}")
        if len(_lm["distinct"]) > 1:
            print("  MORE THAN ONE CONFIGURATION served this arm - it is a mixture, not a sample.")
        if _lm.get("runs_pin_unchecked"):
            print(f"  {_lm['runs_pin_unchecked']} run(s) UNCHECKED against a pin (unpinned, or the "
                  f"serving provider could not be read). Unchecked is not honored.")
    elif _lm.get("questions_missing_a_record"):
        print(f"\nAnswer LM: NO per-call record on any scored run "
              f"({len(_lm['questions_missing_a_record'])} question(s)). The endpoint predates the "
              f"field or is mis-deployed; this arm cannot be cited for a pinned comparison.")
    if integrity_violations:
        print("RUN INTEGRITY VIOLATIONS (results are not samples):")
        for v in integrity_violations:
            print(f"    {v}")
    if n_runs > 1:
        st = summary["stability"]
        print(f"\nStability (N={n_runs} runs/question):")
        print(f"  STABLE-PASS : {st['stable_pass']}")
        print(f"  STABLE-FAIL : {st['stable_fail']}")
        print(f"  FLAKY       : {st['flaky']}  <- run-to-run noise band; NOT regressions")
        print(f"  NO-DATA     : {st['no_data']}  <- no scoreable run; NOT failures")
        for qid in st["no_data_ids"]:
            print(f"      {qid:40} 0/{n_runs} runs scoreable")
        if st["partial_detail"]:
            print("  Partially scored (classified on fewer than N runs):")
            for qid, note in sorted(st["partial_detail"].items()):
                print(f"      {qid:40} {note}")
        if st["flaky_detail"]:
            # Own heading: this list is a PASS fraction, the partial list above is a
            # RUNS-SCOREABLE fraction. Printed bare under one heading, the same qid in
            # both read as a self-contradiction.
            print("  FLAKY detail (runs passed / runs scored):")
            for qid, ratio in sorted(st["flaky_detail"].items()):
                print(f"      {qid:40} {ratio} passed")
        print("  Gate a code change on STABLE-PASS->STABLE-FAIL flips (the path "
              "touched), not on the pass-rate total.")
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
    # Hard-fail on must_not_cite violations, and on any run-integrity violation: a run whose
    # samples were cache replays must not exit 0 and be cited as a measurement.
    if integrity_violations:
        return 4
    return 1 if summary["must_not_cite_violations"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
