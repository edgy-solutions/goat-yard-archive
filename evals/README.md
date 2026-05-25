# Evals

This directory holds the quality-measurement infrastructure for the
project. Two complementary evals live here:

| File | Measures | When to run |
|---|---|---|
| [`entity_extraction_benchmark.py`](entity_extraction_benchmark.py) | Per-model latency / throughput / within-page quality / cross-page consistency of BAML entity extraction | On model upgrades; periodically for drift detection; after BAML prompt changes |
| [`run_eval.py`](run_eval.py) | End-to-end retrieval + synthesis correctness against expert-curated Q&A pairs | Every PR (via CI); on demand |

Both write per-run artifacts to `output/` (gitignored). Both pull
`OPENROUTER_API_KEY` from the repo `.env`.

The rationale for each is captured in:
- [ADR-0004](../docs/adr/0004-reference-eval-set-and-ci-gates.md) — reference eval set + CI gates
- [ADR-0005 Phase 5](../docs/adr/0005-entity-index-audit-and-automated-deduplication.md#phase-5--recurring-cross-model-benchmark-ci-signal-for-model-drift) — cross-model entity benchmark

---

## Entity-extraction benchmark

Runs the BAML `ExtractGillKnowledge` prompt against multiple OpenRouter
models on a fixed 10-page sample. Measures:

- **Within-page quality** — `normalized_name` fill rate, invalid category
  counts, within-page fragmentation.
- **Cross-page consistency** — for entities that appear in ≥2 pages,
  how often do their `name` / `category` / `era` / `normalized_name`
  drift across pages? This is the production failure mode that motivated
  ADR-0005.
- **Speed** — latency per call, tokens/sec throughput, total tokens.

### Why a fixed sample

The 10 pages were chosen for fragmentation-detection value:
- 4 Leviticus 16 pages (scapegoat / Azazel typology — many entities
  recur across these pages).
- 1 NT cross-reference to scapegoat (vol7 page 376).
- 5 diverse pages covering Genesis 1, Mark 3 (Peter), John 1 (John the
  Baptist), and 2 NT scapegoat references.

Keep the sample stable so benchmark numbers remain comparable across
runs. If you change the sample, treat it as a new baseline.

### Setup

```sh
# Point at the dr-voluminous commentary repo (sibling of this one by default)
export COMMENTARY_DATA_DIR=/path/to/dr-voluminous/commentary

# OpenRouter key is read from the repo .env automatically
```

### Run

```sh
# Full run (all 3 models, all 10 pages)
python evals/entity_extraction_benchmark.py

# One model only (fast iteration)
python evals/entity_extraction_benchmark.py --models grok-4.20

# Custom output location
python evals/entity_extraction_benchmark.py --output-dir evals/output/run-2026-05-24
```

### Interpreting the output

- **Within-page numbers** are typically clean for all current frontier
  models (≥99% `normalized_name` fill, zero within-page fragmentation).
  Anomalies here indicate prompt drift or model regression.
- **Cross-page drift** is where the architectural failure mode shows up.
  Numbers in single digits per category are normal; sharp increases
  indicate a model has lost the disambiguation discipline (e.g. flipping
  `BiblicalFigure` ↔ `TypeOrSymbol` across pages for the same entity).
- **Speed** matters because the production pipeline runs this on 7,000+
  pages. The Grok / DeepSeek / Qwen3 gap is roughly 15× — a 60s
  Grok extraction becomes a 15-min Qwen3 extraction.

### When to run

- After bumping the BAML model slug in [`baml_src/main.baml`](../baml_src/main.baml).
- When OpenRouter retires a model (verify the replacement doesn't regress).
- After material changes to [`gill_extract.baml`](../baml_src/gill_extract.baml).
- Quarterly, as a passive drift detector.

Reference baseline from 2026-05-24 (recorded in
[ADR-0005](../docs/adr/0005-entity-index-audit-and-automated-deduplication.md#empirical-validation-2026-05-17-cross-model-test)).

---

## Answer-quality eval (`run_eval.py`)

See the script's `--help` and [ADR-0004](../docs/adr/0004-reference-eval-set-and-ci-gates.md).
Questions live in [`gill_reference_set.jsonl`](gill_reference_set.jsonl).

### Run

```sh
# Default: against the test cluster
python evals/run_eval.py

# Custom endpoint (production, local, etc.)
python evals/run_eval.py --endpoint https://goatyardarchive.org/api/search

# Compare against a baseline (for regression detection)
python evals/run_eval.py --baseline evals/baselines/latest.json

# Subset of questions for fast iteration
python evals/run_eval.py --ids scapegoat_001 logos_001
```

### Reference set conventions

Each entry in `gill_reference_set.jsonl` has these fields:

- `id` — stable identifier (e.g. `scapegoat_001`).
- `question` — what the user types.
- `expected_behavior` — `"answer"` or `"refuse"`.
- `must_cite` — Sentence IDs at least 50% of which must appear in the answer.
- `should_cite` — bonus precision targets (any subset is fine).
- `must_not_cite` — distractors; any presence is a hard fail.
- `reference_summary` — what a correct answer would say (for human review).
- `expert_notes` — context, calibration notes, known edge cases.
- `category` — bucket for the by-category report (`doctrine`, `typology`,
  `refusal_data_absent`, etc.).
- `difficulty` — `easy` / `medium` / `hard`.
- `_provenance` (optional) — `developer_seed` (synthetic) or
  `real_user_query_2026` (pulled from production traces).
- `_needs_curator_review` (optional) — true when `must_cite` is empty and
  a Reformed expert should add ground truth.
- `_corpus_dependency` (optional) — names a Bible book/range that must be
  ingested before `expected_behavior` can flip from `"refuse"` to `"answer"`.
  Used as a forward-marker for future corpus expansion.
- `_flip_when` (optional) — plain-English condition that should trigger a
  re-baseline of this question (paired with `_corpus_dependency`).

### Available books vs eval coverage

The eval set deliberately includes questions whose answers require books
not yet in the corpus (Deuteronomy, Psalms, Hebrews, etc.). These are
marked `expected_behavior: "refuse"` with a `_corpus_dependency` note.
They serve as canaries: when the relevant book is ingested, flipping
`expected_behavior` to `"answer"` re-activates the test.

### Pass/fail rules

- `must_cite` recall ≥ 50% (and at least one if any are required).
- `must_not_cite` violations → hard fail.
- For `expected_behavior: "refuse"`: the system must actually refuse
  (heuristic match against the "I regret..." marker).

### Baselines

Frozen summaries in [`baselines/`](baselines/) are the regression yardstick.
See [`baselines/README.md`](baselines/README.md) for update procedure.

### CI integration

[`.github/workflows/eval.yml`](../.github/workflows/eval.yml) runs this on
`workflow_dispatch` against an operator-provided endpoint. The home-hosted
production endpoint isn't reachable from GitHub-hosted runners by default,
so the workflow is manual until a public staging endpoint is set up.

---

## Output directory

Per-run artifacts go to `output/` (gitignored). To preserve a specific
run, copy its contents into a named subdirectory and commit selectively
(e.g. when establishing a baseline for an ADR).
