# ADR-0004: Reference Eval Set and CI Gates

- **Status:** Proposed
- **Date:** 2026-05-17
- **Deciders:** Chris Nogradi

## Context

The system currently has no quantitative measurement of answer quality. Every change to prompts, retrieval parameters, or models is evaluated by manual log inspection. In a single recent session (2026-05-17), we made six interrelated changes (refusal prompt softening, substring entity matching, top-K bump, alpha tuning, embedding-pollution removal, plumb-through of original query) and verified them by running four test questions by hand and reading the responses.

This approach does not scale and has specific risks for this domain:

1. **Theological accuracy is unusually hard to spot-check.** A fluent, well-cited answer can subtly misrepresent Gill's Calvinist precision (e.g. conflating "elected unto salvation" with "called to salvation"); manual review catches obvious failures but routinely misses subtle drift.
2. **Regression detection is purely intuitive.** When we fixed Logos and Sheep, we relied on memory to confirm Peter and John didn't regress. With dozens of edge cases, this becomes impossible.
3. **All other proposed improvements need this to be useful.** Reranking ([ADR-0003](0003-cross-encoder-reranking.md)), enumeration mode ([ADR-0001](0001-enumeration-query-path.md)), entity auto-dedup ([ADR-0005](0005-entity-index-audit-and-automated-deduplication.md)), and verbatim verification ([ADR-0006](0006-verbatim-quote-verification.md)) all require a way to measure whether they help. Without that measurement, each is a guess.

Without an eval set, **the project cannot honestly claim faithfulness to Gill** — only that no obvious failure has been spotted by the developer.

## Decision

Build a small, expert-curated reference eval set and integrate it into CI.

### The reference set

- **Size:** 30-50 question-answer pairs initially. Grow over time as failure modes are discovered.
- **Curator:** A Reformed pastor, seminary professor, or other expert with first-hand knowledge of Gill's commentary. This is the most expensive and most valuable part — synthetic or LLM-generated eval data is *not* a substitute (it produces self-referential evals that don't catch real-world question types).
- **Format:** JSONL at `evals/gill_reference_set.jsonl`. Each row:
  ```json
  {
    "id": "logos_001",
    "question": "What does the word 'Logos' mean in the first chapter of John?",
    "expected_behavior": "answer",            // "answer" | "refuse"
    "must_cite": ["[JOHN_1_1_S00]", "[JOHN_1_14_S00]"],
    "should_cite": ["[JOHN_1_18_S00]"],       // bonus precision
    "must_not_cite": ["[LEVITICUS_16_9_S00]"], // distractors
    "reference_summary": "Gill identifies the Logos with the eternal Word of God, the second person of the Trinity...",
    "expert_notes": "Watch for conflation with Philo's usage; Gill distinguishes them.",
    "difficulty": "medium",                    // "easy" | "medium" | "hard"
    "category": "definition"                   // for failure-mode slicing
  }
  ```
- **Categories** to ensure coverage: definition, person, doctrine, typology, enumeration, scripture-reference, partial-match, refusal-expected.

### The eval runner

- Script at `evals/run_eval.py` that hits `/api/search` for each question, scores against the reference, emits a markdown report.
- **Scored metrics:**
  - Refusal correctness: did the system refuse iff `expected_behavior == "refuse"`?
  - Citation recall: of `must_cite`, how many appear in the response?
  - Citation precision: of cited Sentence IDs, how many appear in `must_cite ∪ should_cite`?
  - Citation purity: any `must_not_cite` present? (binary fail)
  - Optional: LLM-judge for answer quality vs `reference_summary` (gated behind a flag because it adds latency/cost).
- Tracks scores per category for failure-mode visibility.

### CI integration

- GitHub Action runs the eval on every PR that touches `backend/`, `baml_src/`, or `pipeline/`.
- Compares scores to baseline (main branch). Surfaces diff in PR comment with per-category breakdown.
- **Hard fail** the PR if any `must_not_cite` is violated or if overall pass rate drops by more than a threshold (e.g. 5%).
- **Soft warn** on other regressions; require human review.
- Eval scores persisted as CI artifact for historical tracking.

### Companion eval: entity-extraction cross-page consistency

The answer-quality eval above measures the full retrieval-to-synthesis pipeline. A complementary eval at the **entity-extraction layer** is described in [ADR-0005 Phase 5](0005-entity-index-audit-and-automated-deduplication.md). That benchmark (prototype at `c:\tmp\entity_model_compare.py`):

- Runs the BAML entity-extraction prompt against multiple models on a fixed ~10-page sample.
- Measures per-model latency, throughput, within-page quality (fill rates, fragmentation), and cross-page drift (same entity extracted with different names, categories, eras across pages).
- Surfaces drift counts as the key metric — production failure modes (e.g. `scape-goat` vs `Scape-goat`, `Azazel` flipping categories) are cross-page consistency failures, not within-page quality failures.

These two evals together give the full quality signal:

| Eval | What it measures | When it should run |
|---|---|---|
| Answer-quality (this ADR) | End-to-end retrieval + synthesis correctness | Every PR touching `backend/`, `baml_src/`, `pipeline/` |
| Entity-extraction benchmark ([ADR-0005](0005-entity-index-audit-and-automated-deduplication.md)) | Per-model extraction quality + cross-page consistency | On-demand for model upgrades; periodic for drift detection |

A shared `evals/` directory holds both. The infrastructure (page sampling, LLM-as-judge utilities) is reusable between them.

## Alternatives Considered

1. **Continue manual log review.** Doesn't scale; no historical tracking; subject to confirmation bias.
2. **LLM-judge only (no human ground truth).** Cheap to build. But the judge is likely to share biases with the bot (same model family), and tends to favor fluent answers regardless of correctness. Useful as a *supplement*, not a substitute.
3. **Synthetic Q&A generated from the corpus.** Tempting but produces self-referential evaluation: questions are derived from passages the system already retrieves easily. Misses real-user question patterns.
4. **Online learning from Langfuse user feedback.** The feedback endpoint already exists. But user feedback is sparse, biased toward complaints, and lacks ground truth. Useful for prioritizing what to add to the eval set; not a substitute for it.

## Consequences

### Positive
- Every change becomes measurable; regressions caught before merge.
- Quality trajectory becomes visible over time (chart of pass rate per release).
- Eval set serves as a contract between developer and theological domain — explicit ground truth.
- Enables principled experimentation: try a reranker, try a different LLM, try a new entity extraction — all on the same yardstick.

### Negative
- Requires expert time. This is real money or real relationship-equity.
- Reference set itself becomes a maintained artifact (refresh as Gill scholarship evolves, as new failure modes are added).
- CI run adds time and cost to every PR (~30 questions × 25s per query = ~15 min, plus LLM token cost).

### Risks
- **A bad reference set is worse than no eval** — if the "correct" answers are themselves wrong, the system optimizes toward wrong answers. **Mitigation:** review every reference answer with a second expert before adding to the set.
- **Expert availability bottleneck.** If only one curator exists, eval set growth stalls. **Mitigation:** document the contribution format clearly so volunteers from the broader Reformed community can submit pairs.
- **Eval set becomes a target.** Engineers optimize toward passing the eval rather than toward general quality. **Mitigation:** keep ~20% of the eval set held-out and rotated periodically.

## Open Questions

- **Who curates?** Cost / time / relationship — needs an explicit owner.
- **How is verbatim-mode scored?** The current verbatim mode produces quotes-with-IDs; the eval can verify the IDs appear, but verifying the quoted text matches verbatim is a separate concern ([ADR-0006](0006-verbatim-quote-verification.md)).
- **What about the BAML expansion layer?** Should the eval set also include "expected BAML expansion" for each question, so changes to query expansion can be measured independently?
- **Refresh cadence?** Annual? When pass rate plateaus? When new failure modes appear in production?

## Dependencies

This ADR is a prerequisite for trustworthy evaluation of [ADR-0001](0001-enumeration-query-path.md), [ADR-0003](0003-cross-encoder-reranking.md), [ADR-0005](0005-entity-index-audit-and-automated-deduplication.md), and [ADR-0006](0006-verbatim-quote-verification.md). Implementing any of those without this is implementing on guess.
