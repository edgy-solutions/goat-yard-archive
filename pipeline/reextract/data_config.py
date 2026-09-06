"""Single source of the re-extraction DATA ROOT.

`pipeline/reextract` is code-only. Every scan, extraction output, verdict, console, and data-bearing
doc lives in the PRIVATE dr-voluminous repo (`reextract_vol1/`) — never in this public repo. Scripts
resolve their data paths through `data_path(...)` so the location is ONE config value, not a hundred
hard-coded references, and so nothing writes data back into the code tree.

Override the root with the `REEXTRACT_DATA_ROOT` env var; the default points at the local dr-voluminous
checkout. Layout under the root mirrors the old in-tree layout (`audits/`, `truthset_review/`, ...).
"""
import os
from pathlib import Path

DATA_ROOT = Path(os.environ.get(
    "REEXTRACT_DATA_ROOT", r"C:/Users/cnogr/git/dr-voluminous/reextract_vol1"))

def data_path(*parts):
    """Resolve a path under the data root, e.g. data_path('audits', 'agent_session.jsonl')."""
    return DATA_ROOT.joinpath(*parts)
