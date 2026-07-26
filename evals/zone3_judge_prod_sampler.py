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
    # ADR-0014 entity-lookup mode ("full" | "degraded_no_vector"). A
    # degraded reading means the entity vector tier (litellm enrichment)
    # was down for that request and the boost was suppressed. A non-zero
    # daily count = a litellm blip that morning, surfaced instead of
    # silently reshaping retrieval.
    entity_lookup_mode: str = "full"
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
    # ADR-0014: count of sampled answers served in degraded entity-lookup
    # mode (vector tier / litellm enrichment down, boost suppressed).
    # Non-zero => an infra blip that window; surfaced in Slack so it
    # announces itself the same morning.
    entity_lookup_degraded_count: int = 0
    commit_sha_summary_line: str = ""
    # Two supported-rate flavors reported side-by-side per the 2026-07-06
    # review correction. The gap between them IS the visible measure of
    # judge marginal-noise on the class the supported rate is meant to
    # measure. Collapsing N=3 to a single threshold would throw away the
    # exact information the multi-judge design preserves.
    #   majority_supported_rate — fraction with >=2 of 3 flagged supported.
    #     The stability signal; a real week-over-week rise means erosion
    #     the judge sees consistently.
    #   any_flag_supported_rate — fraction with >=1 of 3 flagged supported.
    #     The sensitivity signal; catches marginal cases the judge only
    #     sometimes sees.
    # gap = any_flag_rate - majority_rate. High gap = judge is coin-
    # flipping on the boundary. Wide gap over time = shape drifting into
    # marginal territory.
    majority_supported_rate: float = 0.0
    any_flag_supported_rate: float = 0.0
    supported_rate_gap: float = 0.0


# ---------------------------------------------------------------------------
# Langfuse extraction — kept isolated so the sampler is testable with a
# mock trace list. Imports Langfuse lazily so the module loads without
# the dep installed.
# ---------------------------------------------------------------------------

def _langfuse_read_client():
    """Return the Langfuse SDK's read-side client (langfuse.api.trace /
    langfuse.api.observations). Kept as its own helper because the SDK's
    read API is nested and the write-side API (Langfuse.update_current_trace
    etc.) does not include the read methods.

    IMPORTANT: earlier drafts of this sampler AND the pre-existing
    `daily_rag_diagnostic` asset call `langfuse.get_traces(...)`, which
    does NOT exist in the current Langfuse Python SDK. That call fails
    at runtime with `AttributeError: 'Langfuse' object has no attribute
    'get_traces'`. The read API is `c.api.trace.list(...)` and
    `c.api.observations.get_many(trace_id=...)`. See the Langfuse SDK's
    `FernLangfuse` client under `langfuse.api.client`.
    """
    from langfuse import Langfuse  # noqa: WPS433
    return Langfuse()


def fetch_recent_traces(
    hours: int = LOOKBACK_HOURS,
    name: Optional[str] = None,
    tags: Optional[List[str]] = None,
    max_pages: int = 10,
) -> List[Any]:
    """Fetch Langfuse traces for the last N hours via c.api.trace.list.
    Returns raw trace objects; extract_answer_samples turns them into
    AnswerSample rows."""
    lf = _langfuse_read_client()
    now = datetime.now(timezone.utc)
    from_ts = now - timedelta(hours=hours)
    kwargs: Dict[str, Any] = {
        "from_timestamp": from_ts,
        "to_timestamp": now,
        "limit": 50,
    }
    if name:
        kwargs["name"] = name
    if tags:
        kwargs["tags"] = tags
    traces: List[Any] = []
    for page in range(1, max_pages + 1):
        response = lf.api.trace.list(page=page, **kwargs)
        batch = getattr(response, "data", []) or []
        if not batch:
            break
        traces.extend(batch)
        if len(batch) < kwargs["limit"]:
            break
    return traces


def extract_answer_samples(traces: List[Any]) -> List[AnswerSample]:
    """Extract AnswerSample rows from Langfuse trace objects. Skips
    traces without a bot_forward generation or without a text answer.

    Prefers observation-level metadata for commit_sha (that's where
    main.py attaches it on the `bot_forward` generation) and falls back
    to trace-level metadata."""
    lf = _langfuse_read_client()
    samples: List[AnswerSample] = []
    for trace in traces:
        try:
            trace_md_raw = getattr(trace, "metadata", None) or {}
            trace_md = trace_md_raw if isinstance(trace_md_raw, dict) else {}
            trace_sha = str(trace_md.get("commit_sha", "unknown"))

            tin = getattr(trace, "input", None)
            if isinstance(tin, str):
                question = tin
            elif isinstance(tin, dict):
                question = tin.get("query") or tin.get("question") or ""
            else:
                question = ""

            # Fetch the full trace (with observations expanded) to walk
            # observations and pull the bot_forward generation's output.
            trace_id = getattr(trace, "id", None)
            if not trace_id:
                continue
            try:
                full = lf.api.trace.get(trace_id=trace_id)
            except Exception as e:
                print(f"[SAMPLER] skipping trace {trace_id}: get() failed: {e}")
                continue

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
                    obs_md_raw = getattr(obs, "metadata", None) or {}
                    if isinstance(obs_md_raw, dict):
                        gen_md = obs_md_raw
                    break

            if not answer:
                continue

            commit_sha = str(gen_md.get("commit_sha", trace_sha)) or "unknown"

            samples.append(AnswerSample(
                trace_id=str(trace_id),
                question=question[:400],
                answer=answer,
                commit_sha=commit_sha,
                timestamp=str(getattr(trace, "timestamp", "")),
                excision_count=int(gen_md.get("zone3_excision_count", 0) or 0),
                trailing_prose_excised=int(gen_md.get("zone3_trailing_prose_excised", 0) or 0),
                disclaimer_preserved=int(gen_md.get("zone3_disclaimer_preserved", 0) or 0),
                other_excised=int(gen_md.get("zone3_other_excised", 0) or 0),
                entity_lookup_mode=str(gen_md.get("entity_lookup_mode", "full") or "full"),
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
    # Global (across-SHA) counts for the two supported rates
    global_majority_flagged = 0
    global_any_flagged = 0
    global_judged = 0
    for s in samples:
        by_sha[s.commit_sha]["count"] += 1
        by_sha[s.commit_sha]["supported_distribution"][s.supported_ratio] += 1
        # Per-SHA majority and any-flag counts
        n_verdicts = len(s.verdicts)
        n_supported = s.supported_count
        by_sha[s.commit_sha]["judged"] = by_sha[s.commit_sha].get("judged", 0) + (1 if n_verdicts else 0)
        if n_verdicts:
            global_judged += 1
            if n_supported >= 2:  # majority of 3
                by_sha[s.commit_sha]["majority_flagged"] = by_sha[s.commit_sha].get("majority_flagged", 0) + 1
                global_majority_flagged += 1
            if n_supported >= 1:
                by_sha[s.commit_sha]["any_flagged"] = by_sha[s.commit_sha].get("any_flagged", 0) + 1
                global_any_flagged += 1
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

    majority_rate = (global_majority_flagged / global_judged) if global_judged else 0.0
    any_flag_rate = (global_any_flagged / global_judged) if global_judged else 0.0

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
        entity_lookup_degraded_count=sum(
            1 for s in samples if s.entity_lookup_mode != "full"
        ),
        commit_sha_summary_line=commit_sha_summary,
        majority_supported_rate=majority_rate,
        any_flag_supported_rate=any_flag_rate,
        supported_rate_gap=any_flag_rate - majority_rate,
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

    # Global supported-rate DISTRIBUTION per the 2026-07-06 review
    # correction. Both rates reported side-by-side; the gap between them
    # is the visible measure of judge marginal-noise. Do not collapse
    # to a single boolean per answer — that throws away the exact info
    # the multi-judge design preserves.
    m_pct = report.majority_supported_rate * 100
    a_pct = report.any_flag_supported_rate * 100
    gap_pct = report.supported_rate_gap * 100
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                "*Supported-characterization rate (both thresholds — see the gap):*\n"
                f"  • *majority* (>=2 of 3 judge runs): `{m_pct:.1f}%` — stable-signal rate\n"
                f"  • *any-flag* (>=1 of 3 judge runs): `{a_pct:.1f}%` — sensitivity-signal rate\n"
                f"  • *marginal-noise gap*: `{gap_pct:.1f} pp` — how much of the "
                "any-flag rate is coin-flippy shape\n"
                "  _Both rates are violation counts per the core ADR; target zero for both. "
                "Gap widening over time indicates shape drift into marginal territory._"
            ),
        },
    })
    blocks.append({"type": "divider"})

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

    # ADR-0014 — entity-lookup degraded mode. Non-zero means litellm (the
    # entity vector tier's enrichment infra) blipped this window and the
    # boost was suppressed to hold determinism. An outage announces itself
    # the same morning instead of surfacing as a theological error weeks
    # later. A ⚠️ is used at >0 so it reads at a glance.
    _deg = report.entity_lookup_degraded_count
    _deg_icon = "⚠️ " if _deg > 0 else ""
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                f"*{_deg_icon}Entity-lookup mode (ADR-0014 fail-anchored):*\n"
                f"  • degraded_no_vector answers this window: `{_deg}` / `{report.total_answers_sampled}`"
                + ("  — litellm/vector-tier blip; boost suppressed, retrieval on deterministic floor"
                   if _deg > 0 else "  — vector tier healthy all window")
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
        judged = data.get("judged", 0) or 1
        m_flagged = data.get("majority_flagged", 0)
        a_flagged = data.get("any_flagged", 0)
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Build `{sha[:12]}` — {data['count']} answers*\n"
                    f"  supported-verdict distribution (N=3): {dist_line}\n"
                    f"  majority-supported: `{m_flagged}/{judged}` "
                    f"({(m_flagged / judged * 100):.1f}%)  •  "
                    f"any-flag: `{a_flagged}/{judged}` "
                    f"({(a_flagged / judged * 100):.1f}%)\n"
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

def post_escalation_alert(
    slack_client,
    channel: str,
    report: DailyReport,
    source_label: str = "production",
) -> None:
    """Fire a SEPARATE high-visibility Slack alert when the report
    contains any unsupported-classification answers.

    The daily summary Slack post is a record; this is the alert. Fires
    independently of anyone reading the summary, so the safety-net works
    at any traffic level and doesn't depend on a human watching. This is
    the sensitivity path per the 2026-07-06 review: any single of 3
    judge runs flagging unsupported triggers escalation. Optional
    at-mention via ZONE3_ESCALATION_MENTION (e.g. `<!channel>` or
    `<@U01234ABCDE>`) so the alert actually notifies.
    """
    if not report.escalations:
        return
    mention = os.getenv("ZONE3_ESCALATION_MENTION", "").strip()
    prefix = f"{mention} " if mention else ""
    n = len(report.escalations)
    header_text = (
        f"{prefix}🚨 *Zone-3 UNSUPPORTED escalation* — "
        f"{n} answer{'s' if n != 1 else ''} flagged in {source_label} traffic\n"
        f"Window: {report.window_start} → {report.window_end}  •  "
        f"Build(s): `{report.commit_sha_summary_line}`"
    )
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": header_text}},
        {"type": "divider"},
    ]
    for e in report.escalations[:5]:
        unsup_count = sum(1 for v in e.verdicts if v == "unsupported")
        reasoning = e.reasoning_samples[0] if e.reasoning_samples else "(no reasoning captured)"
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Q:* _{e.question[:200]}_\n"
                    f"*Verdicts across N=3 judge runs:* `{e.verdicts}` "
                    f"({unsup_count} unsupported)\n"
                    f"*Sample reasoning:* {reasoning[:240]}\n"
                    f"*Build:* `{e.commit_sha[:12]}`  *Trace:* `{e.trace_id[:16]}`"
                ),
            },
        })
        blocks.append({"type": "divider"})
    if n > 5:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"...and *{n - 5}* more escalations in the daily summary."},
        })
    slack_client.chat_postMessage(
        channel=channel,
        blocks=blocks,
        text=f"Zone-3 unsupported escalation ({source_label})",
    )


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
