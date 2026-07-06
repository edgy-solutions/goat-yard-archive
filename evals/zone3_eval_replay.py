"""Daily eval-set replay Zone-3 judge (ADR-0008 Phase 1 Step 5c).

Runs the 28 curated eval-set questions through the deployed bot every
day and judges each resulting answer N=3 times. This is the CONTROLLED
instrument that complements the 5b production sampler:

  - 5b measures REALITY: are real user answers faithful?
  - 5c (this) measures the INSTRUMENT: does the same eval case's verdict
    flip over time? Is the bot's answer to a fixed question changing
    shape? Is the majority-vs-any-flag gap stable, widening, narrowing?

5c is not a substitute for 5b — real users don't ask the eval-set
questions, and the violations that matter most are the ones on queries
we haven't seen. But at low traffic (the covenant flagship was found in
real traffic, not in the eval set), 5b's daily sample can go multiple
days seeing 0-3 answers; 5c gives 28 controlled answers × 3 judges =
84 verdicts per day of consistent measurement, on inputs we chose.

DESIGN CORRECTION FROM 2026-07-06 REVIEW:

  Step 6 was originally gated on 'a week of production rates' — that
  gate was a category error, conflating the formal A/B experiment
  (controlled, runnable now) with ongoing production monitoring
  (opportunistic, runs indefinitely). Step 6 doesn't need production
  traffic; it needs controlled multi-run on the flagship cases, which
  5c's methodology already provides. Decoupled: run Step 6 when ready;
  let 5b + 5c run as permanent monitors.

Reports the same DailyReport shape as 5b so the two are directly
comparable. The Slack post distinguishes the source ('eval_replay' vs
'production') in its header.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import httpx

from evals.zone3_judge_prod_sampler import (
    AnswerSample,
    DailyReport,
    aggregate,
    format_slack_blocks as _format_slack_blocks_prod,
    JUDGE_RUNS_PER_ANSWER,
    judge_sample_n_times,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REF_SET = REPO_ROOT / "evals" / "gill_reference_set.jsonl"

# For a Dagster job running inside the k3s cluster, use in-cluster DNS.
# For local dev, override to http://localhost:8001/api/search after
# kubectl port-forward.
DEFAULT_ENDPOINT = os.getenv(
    "ZONE3_EVAL_REPLAY_ENDPOINT",
    "http://gya-frontend-api.gya-test.svc.cluster.local:8000/api/search",
)

# How many eval cases to run each day. All 28 is roughly 28 × ~10s API
# + 28 × 3 × ~3s judge = ~9-15 minutes total. Fine for a daily cron.
MAX_CASES_PER_DAY = 30


def load_eval_cases(path: Path = DEFAULT_REF_SET, ids: Optional[List[str]] = None) -> list:
    """Load the eval reference set. If ids given, filter to that subset."""
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        c = json.loads(line)
        if ids is not None and c.get("id") not in ids:
            continue
        cases.append(c)
    return cases


def _run_query(endpoint: str, question: str, timeout: float = 180.0) -> dict:
    """Fire one /api/search request. Returns the response dict + debug
    stages so we can pick up commit_sha and excision counts."""
    with httpx.Client(timeout=timeout) as client:
        r = client.post(endpoint, json={"query": question, "debug": True})
        r.raise_for_status()
        return r.json()


def _extract_sample_from_response(case: dict, resp: dict) -> Optional[AnswerSample]:
    """Turn one API response into an AnswerSample. Returns None on empty
    answers so downstream aggregation doesn't count nothing-answers."""
    answer = resp.get("answer") or ""
    if not answer:
        return None
    stages = resp.get("stages") or {}
    excisions = stages.get("zone3_excisions") or []
    trailing = sum(
        1 for e in excisions if e.get("action") == "trailing_prose_excised"
    )
    disclaimer = sum(
        1 for e in excisions
        if e.get("action") == "template_replaced"
        and "does not use" in (e.get("replacement") or "").lower()
    )
    other = len(excisions) - trailing - disclaimer

    # The API doesn't return commit_sha directly; the eval replay knows
    # which pod it hit via the endpoint config. For the report shape,
    # tag with the endpoint's declared target (test / prod) so the
    # Slack post says WHERE the answers came from. commit_sha may still
    # appear in stages if the API ever surfaces it; prefer that if so.
    commit_sha = stages.get("commit_sha") or os.getenv("ZONE3_EVAL_REPLAY_TAG", "eval_replay")

    return AnswerSample(
        trace_id=case.get("id") or "eval",
        question=case.get("question", "")[:400],
        answer=answer,
        commit_sha=str(commit_sha),
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        excision_count=len(excisions),
        trailing_prose_excised=trailing,
        disclaimer_preserved=disclaimer,
        other_excised=other,
    )


def build_eval_replay_report(
    endpoint: str = DEFAULT_ENDPOINT,
    ref_set_path: Path = DEFAULT_REF_SET,
    ids: Optional[List[str]] = None,
) -> DailyReport:
    """Run each eval case through the bot, judge N=3, aggregate.
    Same DailyReport shape as 5b so the reports are directly
    comparable."""
    cases = load_eval_cases(path=ref_set_path, ids=ids)
    if len(cases) > MAX_CASES_PER_DAY:
        cases = cases[:MAX_CASES_PER_DAY]

    now = datetime.now(timezone.utc)
    window_end = now.isoformat(timespec="minutes")
    # For eval replay the "window" is just the run-time snapshot, but
    # keep the same field names so 5b and 5c reports render identically.
    window_start = now.isoformat(timespec="minutes")

    samples: List[AnswerSample] = []
    for i, case in enumerate(cases):
        question = case.get("question")
        if not question:
            continue
        try:
            resp = _run_query(endpoint, question)
        except Exception as e:
            print(f"[EVAL_REPLAY] {case.get('id')}: request failed: {e}")
            continue
        s = _extract_sample_from_response(case, resp)
        if s is None:
            continue
        judge_sample_n_times(s)
        samples.append(s)
        if (i + 1) % 5 == 0:
            print(f"[EVAL_REPLAY] {i+1}/{len(cases)} judged")

    return aggregate(samples, window_start=window_start, window_end=window_end)


def format_slack_blocks(report: DailyReport) -> list:
    """Same Slack layout as 5b's production report, prefixed with an
    'eval-set replay' header so recipients can tell the two apart."""
    blocks = _format_slack_blocks_prod(report)
    # Replace the header with the eval-replay one
    if blocks and blocks[0].get("type") == "header":
        blocks[0] = {
            "type": "header",
            "text": {"type": "plain_text", "text": "🧪 GYA Daily Zone-3 — Eval-Set Replay"},
        }
    return blocks
