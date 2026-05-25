# Baselines

Frozen eval summaries used as the comparison point for regression detection.

The CI workflow at [`.github/workflows/eval.yml`](../../.github/workflows/eval.yml)
compares a fresh eval run against the baseline named in the workflow input
(default: `latest.json`).

## How to update a baseline

```sh
# 1. Run the eval locally against your test/prod endpoint
python evals/run_eval.py --output-dir evals/output/baseline-YYYY-MM-DD

# 2. Inspect the report.md and verify the results are what you intend to baseline

# 3. Copy the summary.json into this directory with a dated name
cp evals/output/baseline-YYYY-MM-DD/summary.json evals/baselines/2026-05-24.json

# 4. Update the latest.json symlink (or copy) to point at the new baseline
cp evals/baselines/2026-05-24.json evals/baselines/latest.json

# 5. Commit both files
git add evals/baselines/2026-05-24.json evals/baselines/latest.json
git commit -m "evals: bump baseline to YYYY-MM-DD"
```

## When to update

- After an intentional retrieval / prompt change that improves answer quality
  (verified by manual inspection that the new behavior is correct).
- After a model upgrade that intentionally shifts pass rates.
- After expanding the reference set with new questions.

## When NOT to update

- To paper over a regression introduced by a PR. The PR should be fixed; the
  baseline should not be lowered to accommodate it.
- After a single noisy run. Run the eval 2-3 times before committing a new
  baseline if pass rates are near the regression threshold.

## What's tracked here

Each `*.json` file is the `summary.json` emitted by `run_eval.py`. Per-question
detail (raw responses, individual scores) is intentionally NOT baselined —
those are too volatile to be a useful regression signal at question granularity.
