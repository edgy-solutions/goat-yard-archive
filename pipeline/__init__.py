import os
from dagster import Definitions, load_assets_from_modules
from dagster_slack import SlackResource

from . import assets
from .migration import promote_test_vectors_to_prod

all_assets = load_assets_from_modules([assets])

defs = Definitions(
    assets=all_assets,
    jobs=[promote_test_vectors_to_prod],
    resources={
        "slack": SlackResource(token=os.getenv("SLACK_BOT_TOKEN")),
    },
)
