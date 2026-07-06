import os
from dagster import Definitions, ScheduleDefinition, define_asset_job, load_assets_from_modules
from dagster_slack import SlackResource

from . import assets
from .migration import promote_test_vectors_to_prod

all_assets = load_assets_from_modules([assets])

# Daily Zone-3 observability (ADR-0008 Phase 1 Steps 5b + 5c).
#
# Two ASSETS, two SCHEDULES — measuring different things per the
# 2026-07-06 review's correction:
#
#   5b (daily_zone3_judge_report) — measures REALITY: are real user
#     answers faithful? Opportunistic sampling; may see 0-3 answers
#     per day on this low-traffic tool. Escalation fires whenever it
#     catches an unsupported flag, regardless of volume.
#
#   5c (daily_eval_zone3_report) — measures the INSTRUMENT: does the
#     same eval case's verdict flip over time? Is the majority-vs-
#     any-flag gap stable, widening, narrowing? 28 controlled answers ×
#     3 judges = 84 verdicts of consistent measurement daily, on inputs
#     we chose. Fills the low-traffic gap for the substrate/judge
#     stability question that 5b can't answer at this volume.
#
# 5c is NOT a substitute for 5b; the reviewer was explicit. Real users
# don't ask the 28 eval questions, and the violations that matter most
# are the ones on queries we haven't seen. They run side-by-side.
daily_zone3_job = define_asset_job(
    "daily_zone3_job",
    selection=["daily_zone3_judge_report"],
)
daily_zone3_schedule = ScheduleDefinition(
    job=daily_zone3_job,
    cron_schedule=os.getenv("ZONE3_SAMPLER_CRON", "0 12 * * *"),
    execution_timezone="UTC",
    name="daily_zone3_schedule",
)

daily_eval_zone3_job = define_asset_job(
    "daily_eval_zone3_job",
    selection=["daily_eval_zone3_report"],
)
daily_eval_zone3_schedule = ScheduleDefinition(
    job=daily_eval_zone3_job,
    # 12:30 UTC — offset 30min from 5b so they don't stampede the judge
    # API. Override via ZONE3_EVAL_REPLAY_CRON.
    cron_schedule=os.getenv("ZONE3_EVAL_REPLAY_CRON", "30 12 * * *"),
    execution_timezone="UTC",
    name="daily_eval_zone3_schedule",
)

defs = Definitions(
    assets=all_assets,
    jobs=[promote_test_vectors_to_prod, daily_zone3_job, daily_eval_zone3_job],
    schedules=[daily_zone3_schedule, daily_eval_zone3_schedule],
    resources={
        "slack": SlackResource(token=os.getenv("SLACK_BOT_TOKEN")),
    },
)
