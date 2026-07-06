"""Daily Zone-3 judge sampler over sampled production traffic (ADR-0008
Phase 1 Step 5b).

Queries Langfuse for the last N hours of `/api/search` generations,
applies the calibrated Zone-3 judge to each answer, and returns a
structured report ready for Slack formatting. Kept as pure module-level
functions so it can be unit-tested without Dagster / Langfuse mocks and
so the Dagster asset stays a thin wrapper.

SPEC (locked in the 2026-07-06 review):

  - N=3 multi-judge per answer for the supported rate. The identical-
    input verdict flip observed on 2026-07-06 (`Regarding the covenant
    with Noah, Gill clarifies:` classified `none` on one run and
    `supported` on another with identical text at temperature 0) proves
    single-judge rates carry per-answer noise that would swamp the
    erosion signal the supported rate exists to detect. Report the
    aggregate distribution, not per-answer verdicts.

  - Unsupported gate: `any_of_3 == unsupported` → escalate for human
    eyeball. Bias toward sensitivity per review; the credibility-harm
    class doesn't tolerate false-negatives.

  - Report the pod commit SHA that generated the sampled traffic. This
    is the permanent fix for the stale-prod trap — every daily post
    announces which build was serving. Mixed-SHA windows are broken
    down by build.

  - Include amendment excision counts (trailing-prose fires, disclaimer-
    preservation fires) — the sampler is how the amendments finally get
    exercised on real traffic. State-drift smoke can't produce the
    triggering shapes reliably; production over a week will.

  - Do NOT track disclaimer-position heuristics or verse-local-verb
    calibration rules yet. Both were flagged as follow-ups to be
    designed against the corpus of marginal shapes THIS sampler
    collects, not guessed at now.
"""
from __future__ import annotations

import os
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from evals.zone3_judge import judge_answer


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# N=3 per the review's spec correction. If the identical-input flip
# recurs at scale, this could grow to 5 to tighten the distribution,
# but 3 is where the erosion signal separates from the noise floor
# and the cost stays trivial.
JUDGE_RUNS_PER_ANSWER = 3

# How far back to look. The daily job runs every 24h; a rolling 24h
# window matches the cadence.
LOOKBACK_HOURS = 24

# Cap per daily run so an unusually busy day doesn't blow the judge
# budget. At current volume the cap is well above expected traffic;
# if hit, note it in the report.
MAX_ANSWERS_PER_RUN = 200


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class AnswerSample:
    """One sampled production answer plus its judge-N=3 aggregate."""
    trace_id: str
    question: str
    answer: str
    commit_sha: str
    timestamp: str
    # Amendment excision metrics recorded by main.py in the generation
    # observation's metadata. Missing counts default to 0.
    excision_count: int = 0
    trailing_prose_excised: int = 0
    disclaimer_preserved: int = 0
    other_excised: int = 0
    # N=3 judge results
    verdicts: List[str] = field(default_factory=list)  # ["none"|"supported"|"unsupported", ...]
    reasoning_samples: List[str] = field(default_factory=list)
    judge_errors: List[str] = field(default_factory=list)

    @property
    def escalate_unsupported(self) -> bool:
        """Any single unsupported flag triggers escalation per review."""
        return any(v == "unsupported" for v in self.verdicts)

    @property
    def supported_count(self) -> int:
        return sum(1 for v in self.verdicts if v == "supported")

    @property
    def supported_ratio(self) -> str:
        n = len(self.verdicts) or 1
        return f"{self.supported_count}/{n}"


@dataclass
class DailyReport:
    window_start: str
    window_end: str
    total_answers_sampled: int
    max_answers_hit: bool
    per_commit_sha: Dict[str, Dict[str, Any]]  # sha -> {count, escalations, supported_rates, ...}
    escalations: List[AnswerSample]
    total_trailing_prose_excised: int
    total_disclaimer_preserved: int
    total_other_excised: int
    judge_error_count: int
    commit_sha_summary_line: str


# ---------------------------------------------------------------------------
# Langfuse extraction — kept isolated so the sampler is testable with a
# mock trace list. Imports Langfuse lazily so the module loads without
# the dep installed.
# ---------------------------------------------------------------------------

def fetch_recent_traces(
    hours: int = LOOKBACK_HOURS,
    tags: Optional[List[str]] = None,
    max_pages: int = 10,
) -> List[Any]:
    """Fetch Langfuse traces for the last N hours. Returns raw trace
    objects; extract_answer_samples turns them into AnswerSample rows."""
    from langfuse import Langfuse  # noqa: WPS433
    langfuse = Langfuse()
    now = datetime.now(timezone.utc)
    from_ts = now - timedelta(hours=hours)
    kwargs: Dict[str, Any] = {
        "from_timestamp": from_ts,
        "to_timestamp": now,
    }
    if tags:
        kwargs["tags"] = tags
    traces: List[Any] = []
    page = 1
    while page <= max_pages:
        response = langfuse.get_traces(page=page, **kwargs)
        batch = getattr(response, "data", []) or []
        if not batch:
            break
        traces.extend(batch)
        if len(batch) < 50:
            break
        page += 1
    return traces


def extract_answer_samples(traces: List[Any]) -> List[AnswerSample]:
    """Extract AnswerSample rows from Langfuse trace objects. Skips
    traces without a bot_forward generation or without a text answer."""
    samples: List[AnswerSample] = []
    for trace in traces:
        try:
            # Trace-level metadata carries commit_sha (attached in main.py).
            md = trace.metadata or {} if hasattr(trace, "metadata") else {}
            commit_sha = md.get("commit_sha", "unknown") if isinstance(md, dict) else "unknown"

            # Question lives at trace.input.
            question = ""
            tin = getattr(trace, "input", None)
            if isinstance(tin, str):
                question = tin
            elif isinstance(tin, dict):
                question = tin.get("query") or tin.get("question") or ""

            # Answer + zone3 counts live in the bot_forward generation
            # observation. Fetch the full trace so we can walk it.
            from langfuse import Langfuse  # noqa: WPS433
            langfuse = Langfuse()
            try:
                full = langfuse.get_trace(trace.id)
            except Exception:
                full = trace

            observations = getattr(full, "observations", None) or []
            answer = ""
            gen_md: Dict[str, Any] = {}
            for obs in observations:
                if getattr(obs, "name", "") == "bot_forward":
                    out = getattr(obs, "output", None)
                    if isinstance(out, str):
                        answer = out
                    elif isinstance(out, dict):
                        answer = out.get("answer") or out.get("text") or ""
                    obs_md = getattr(obs, "metadata", None) or {}
                    if isinstance(obs_md, dict):
                        gen_md = obs_md
                    break

            if not answer:
                continue

            # Prefer generation-level commit_sha if present (the trace-
            # level metadata may not always be filled).
            commit_sha = gen_md.get("commit_sha", commit_sha)

            samples.append(AnswerSample(
                trace_id=str(getattr(trace, "id", "")),
                question=question[:400],
                answer=answer,
                commit_sha=str(commit_sha) or "unknown",
                timestamp=str(getattr(trace, "timestamp", "")),
                excision_count=int(gen_md.get("zone3_excision_count", 0) or 0),
                trailing_prose_excised=int(gen_md.get("zone3_trailing_prose_excised", 0) or 0),
                disclaimer_preserved=int(gen_md.get("zone3_disclaimer_preserved", 0) or 0),
                other_excised=int(gen_md.get("zone3_other_excised", 0) or 0),
            ))
        except Exception as e:
            print(f"[SAMPLER] skipping trace due to extraction error: {e}")
            continue
    return samples


# ---------------------------------------------------------------------------
# Judge orchestration — multi-judge N=3 per sample
# ---------------------------------------------------------------------------

def judge_sample_n_times(
    sample: AnswerSample,
    n: int = JUDGE_RUNS_PER_ANSWER,
) -> AnswerSample:
    """Run the calibrated judge on the sample N times and record the
    verdicts. Judge errors are logged (do NOT auto-classify as
    unsupported — that would poison the credibility metric with
    instrument noise)."""
    for _ in range(n):
        r = judge_answer(sample.answer)
        if r.error:
            sample.judge_errors.append(r.error)
            continue
        sample.verdicts.append(r.cls)
        # Grab one reasoning line as a spot-check for the Slack post
        # when the aggregate lands supported/unsupported.
        for c in r.characterizations:
            if not c.substantiated:
                sample.reasoning_samples.append(
                    f"[{c.anchor}/{c.position}] {c.sentence[:120]} — {c.reasoning[:160]}"
                )
                break
    return sample


def aggregate(samples: List[AnswerSample], window_start: str, window_end: str) -> DailyReport:
    """Aggregate the per-sample results into a DailyReport."""
    by_sha: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "count": 0,
        "supported_distribution": Counter(),  # supported_ratio -> count
        "unsupported_escalations": 0,
        "trailing_prose_excised": 0,
        "disclaimer_preserved": 0,
        "other_excised": 0,
    })
    escalations: List[AnswerSample] = []
    total_trailing = 0
    total_disclaimer = 0
    total_other = 0
    judge_error_count = 0
    for s in samples:
        by_sha[s.commit_sha]["count"] += 1
        by_sha[s.commit_sha]["supported_distribution"][s.supported_ratio] += 1
        if s.escalate_unsupported:
            by_sha[s.commit_sha]["unsupported_escalations"] += 1
            escalations.append(s)
        by_sha[s.commit_sha]["trailing_prose_excised"] += s.trailing_prose_excised
        by_sha[s.commit_sha]["disclaimer_preserved"] += s.disclaimer_preserved
        by_sha[s.commit_sha]["other_excised"] += s.other_excised
        total_trailing += s.trailing_prose_excised
        total_disclaimer += s.disclaimer_preserved
        total_other += s.other_excised
        judge_error_count += len(s.judge_errors)

    # Convert Counters to plain dicts for serialization
    for sha_data in by_sha.values():
        sha_data["supported_distribution"] = dict(sha_data["supported_distribution"])

    # Build the SHA summary line for the report header
    sha_counts = sorted(
        ((sha, data["count"]) for sha, data in by_sha.items()),
        key=lambda x: -x[1],
    )
    if len(sha_counts) == 1:
        commit_sha_summary = f"{sha_counts[0][0][:12]} ({sha_counts[0][1]} answers)"
    elif not sha_counts:
        commit_sha_summary = "(no traffic)"
    else:
        commit_sha_summary = ", ".join(
            f"{sha[:12]}({n})" for sha, n in sha_counts[:4]
        )
        if len(sha_counts) > 4:
            commit_sha_summary += f", +{len(sha_counts)-4} more"

    return DailyReport(
        window_start=window_start,
        window_end=window_end,
        total_answers_sampled=len(samples),
        max_answers_hit=len(samples) >= MAX_ANSWERS_PER_RUN,
        per_commit_sha=dict(by_sha),
        escalations=escalations,
        total_trailing_prose_excised=total_trailing,
        total_disclaimer_preserved=total_disclaimer,
        total_other_excised=total_other,
        judge_error_count=judge_error_count,
        commit_sha_summary_line=commit_sha_summary,
    )


# ---------------------------------------------------------------------------
# Slack block formatting
# ---------------------------------------------------------------------------

def format_slack_blocks(report: DailyReport) -> List[Dict[str, Any]]:
    """Render the DailyReport as Slack blocks. Kept as a pure function
    so the block structure is unit-testable without a Slack client."""
    blocks: List[Dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🎯 GYA Daily Zone-3 Judge Report"},
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Window:* {report.window_start} → {report.window_end}\n"
                    f"*Traffic:* {report.total_answers_sampled} answers sampled\n"
                    f"*Build(s) serving:* `{report.commit_sha_summary_line}`\n"
                    f"*Judge runs:* N={JUDGE_RUNS_PER_ANSWER} per answer "
                    f"({report.judge_error_count} judge errors)"
                ),
            },
        },
        {"type": "divider"},
    ]

    # Amendment excision counts — how the runtime layer's amendments
    # actually get exercised in production.
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                "*Runtime sweep — amendment excisions (real traffic):*\n"
                f"  • trailing_prose_excised: `{report.total_trailing_prose_excised}`\n"
                f"  • disclaimer_preserved (compound but-thesis): `{report.total_disclaimer_preserved}`\n"
                f"  • other zone3 excisions: `{report.total_other_excised}`"
            ),
        },
    })
    blocks.append({"type": "divider"})

    # Per-SHA breakdown
    for sha, data in sorted(report.per_commit_sha.items(), key=lambda x: -x[1]["count"]):
        supported_dist = data["supported_distribution"]
        # Order by numerator descending so "3/3" comes first
        parts = sorted(supported_dist.items(), key=lambda kv: (-int(kv[0].split('/')[0]), kv[0]))
        dist_line = ", ".join(f"`{k}` → {v}" for k, v in parts) or "(no answers)"
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Build `{sha[:12]}` — {data['count']} answers*\n"
                    f"  supported-verdict distribution across N=3 judge runs: {dist_line}\n"
                    f"  unsupported escalations (any_of_3): *{data['unsupported_escalations']}*"
                ),
            },
        })

    # Escalations — bias toward sensitivity per review
    if report.escalations:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*🚨 Escalations (any single judge run flagged UNSUPPORTED — human eyeball):*",
            },
        })
        for e in report.escalations[:10]:
            unsup_count = sum(1 for v in e.verdicts if v == "unsupported")
            reasoning = e.reasoning_samples[0] if e.reasoning_samples else "(no reasoning captured)"
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Q:* _{e.question[:180]}_\n"
                        f"*Verdicts:* {e.verdicts} ({unsup_count} unsupported)\n"
                        f"*Sample reasoning:* {reasoning[:200]}\n"
                        f"*Build:* `{e.commit_sha[:12]}`  *Trace:* `{e.trace_id[:16]}`"
                    ),
                },
            })
            blocks.append({"type": "divider"})
        if len(report.escalations) > 10:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"...and *{len(report.escalations) - 10}* more escalations not shown.",
                },
            })
    else:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "✅ *Zero unsupported escalations.* Credibility gate held across the window.",
            },
        })

    if report.max_answers_hit:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"⚠️ *MAX_ANSWERS_PER_RUN cap ({MAX_ANSWERS_PER_RUN}) reached.* "
                    "Traffic exceeded the sampler's daily budget — actual rates may be higher."
                ),
            },
        })

    return blocks


# ---------------------------------------------------------------------------
# Top-level orchestrator — the Dagster asset calls this
# ---------------------------------------------------------------------------

def build_report(hours: int = LOOKBACK_HOURS) -> DailyReport:
    """Fetch → extract → judge N=3 → aggregate. Returns a DailyReport
    ready for Slack formatting."""
    now = datetime.now(timezone.utc)
    window_end = now.isoformat(timespec="minutes")
    window_start = (now - timedelta(hours=hours)).isoformat(timespec="minutes")

    traces = fetch_recent_traces(hours=hours)
    samples = extract_answer_samples(traces)
    # Cap
    if len(samples) > MAX_ANSWERS_PER_RUN:
        samples = samples[:MAX_ANSWERS_PER_RUN]

    for i, s in enumerate(samples):
        judge_sample_n_times(s)
        # Log progress every 20 samples so the Dagster run's logs show life
        if (i + 1) % 20 == 0:
            print(f"[SAMPLER] judged {i+1}/{len(samples)} answers")

    return aggregate(samples, window_start=window_start, window_end=window_end)
