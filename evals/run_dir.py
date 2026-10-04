"""What is and is not a per-question file inside an eval run directory.

One place, because the knowledge was in four. `run_eval` globs `*.json` to list the questions
present in an aborted run, `compare_arms` globs it to load an arm, `expansion_census` globs it
to tally expansion health, and each carried its OWN hand-maintained exclusion: one knew about
`ABORTED.json`, one about `summary.json`, one about `summary.json` and `PUBLISHED.json`, and no
two agreed. Adding `run_header.json` to the directory would have made it a phantom question in
`compare_arms` (qid "run_header", `run_passes` absent, classified by whatever `classify(None)`
does) and a zero-stage row in the census -- silently, in the tools used to read a measurement.

A new sidecar file must be added HERE and nowhere else. The born-test asserts the three
consumers resolve their exclusion through this module rather than restating a list, so the next
sidecar cannot reintroduce the drift.
"""

# Files that live in a run directory and are NOT a question result.
#   summary.json    -- the run's aggregate, written at the end
#   report.md       -- the human-readable render of it
#   run_header.json -- the provenance header, written BEFORE the first scored question
#   ABORTED.json    -- the run-level fault marker (ruling 4): this directory is not a run
#   PUBLISHED.json  -- publish_run's manifest, present only in a published copy
NON_QUESTION_FILES = frozenset({
    "summary.json",
    "report.md",
    "run_header.json",
    "ABORTED.json",
    "PUBLISHED.json",
})


def is_question_file(name: str) -> bool:
    """True for a per-question result file. Name only; it does not touch the filesystem."""
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    return base.endswith(".json") and base not in NON_QUESTION_FILES


def question_files(names):
    """The per-question files among `names`, sorted. Accepts names or paths."""
    return sorted(n for n in names if is_question_file(str(n)))
