import os
from dagster import Definitions, load_assets_from_modules
from dagster_slack import SlackResource

from . import assets

all_assets = load_assets_from_modules([assets])

defs = Definitions(
    assets=all_assets,
    resources={
        "slack": SlackResource(token=os.getenv("SLACK_BOT_TOKEN")),
    },
)
