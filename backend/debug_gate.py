"""Is the per-stage debug capture allowed in THIS deployment?

POST /api/search accepts `debug: true`, and the response it produces carries
the bot's raw pre-sweep answer, the Zone-3 excisions, the embedding hash and
first five components, the enhanced query, and the retrieved chunk SIDs. That
is a diagnostic channel into the model's unshown work, and until this gate it
was open on every deployment to any caller who set one boolean.

Its consumers are the eval scripts that ask for `debug: true` AND post it:
evals/run_eval.py (the scored arm -- the structured BAML fields it scores live
in `stages`, so a scored run against a backend without the channel cannot be
scored at all), evals/determinism_harness.py (compares stage outputs across
runs to find which stage flips), evals/zone3_eval_replay.py (the daily monitor
that reads stages['zone3_excisions']) and evals/acceptance_entity_manifest.py.
Four, on this branch. That list is DERIVED, not maintained by hand:
backend/test_debug_gate.py reads evals/ for the debug payload together with an
actual `.post(` and fails if a consumer appears that does not go through
evals/debug_capture.py. On the release line the first version of this docstring
said there was one consumer when there were two, and nothing contradicted it.

DEFAULT OFF, EVERYWHERE, including development. A capture channel that is on
unless someone remembers to turn it off is the arrangement this gate exists to
end, and "dev is safe" is how it got into production in the first place. The
harness sets GYA_DEBUG_STAGES=1 against the backend it is pointed at; the Helm
chart sets it for gya-test and leaves it "0" in values.yaml.

Read per call rather than at import so a test can flip it without reimporting
and so a request is judged by the environment it actually arrives in. Note the
deployment caveat: the pod receives this through envFrom at container start, so
changing it in the cluster needs a rollout restart. It is not a live toggle.
"""

from __future__ import annotations

import os

# Same vocabulary as backend/structured_answer.py's flag reader, so the project
# has one answer to "what counts as on".
TRUE_VALUES = ("1", "true", "yes", "on")

ENV_VAR = "GYA_DEBUG_STAGES"


def stage_debug_allowed() -> bool:
    """True only when GYA_DEBUG_STAGES is explicitly one of TRUE_VALUES."""
    return os.getenv(ENV_VAR, "").strip().lower() in TRUE_VALUES
