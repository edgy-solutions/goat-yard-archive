import os
from dagster import Definitions, ScheduleDefinition, define_asset_job, load_assets_from_modules
from dagster_slack import SlackResource

from . import assets
from .migration import promote_test_vectors_to_prod

all_assets = load_assets_from_modules([assets])

# Daily Zone-3 judge report — the sampler that gates Step 6 (ADR-0008).
# Scheduled explicitly per the 2026-07-06 review because Step 6's baseline
# is meaningful only if 5b runs on a continuous cadence, not scattered
# manual triggers ("the asset exists and can be triggered" is NOT the
# same as "the asset ran daily for seven days").
daily_zone3_job = define_asset_job(
    "daily_zone3_job",
    selection=["daily_zone3_judge_report"],
)
daily_zone3_schedule = ScheduleDefinition(
    job=daily_zone3_job,
    # 12:00 UTC = 07:00 CT / 08:00 ET; a rolling 24h window from the
    # prior noon UTC. Change via ZONE3_SAMPLER_CRON env if needed
    # (five-field cron, UTC).
    cron_schedule=os.getenv("ZONE3_SAMPLER_CRON", "0 12 * * *"),
    execution_timezone="UTC",
    name="daily_zone3_schedule",
)

defs = Definitions(
    assets=all_assets,
    jobs=[promote_test_vectors_to_prod, daily_zone3_job],
    schedules=[daily_zone3_schedule],
    resources={
        "slack": SlackResource(token=os.getenv("SLACK_BOT_TOKEN")),
    },
)
