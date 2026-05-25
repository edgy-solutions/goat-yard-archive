# Launch Checklist — Puritan Board Launch

The four items below are the gates between current state and a public
launch on Puritan Board. Each links to its ADR for the architectural
reasoning and implementation sketch.

Estimated total effort: **~10 hours** of focused work.

Do them roughly in this order, since #2 builds on #1 and #3 calibrates
against #2.

---

## 1. Cross-model entity-extraction benchmark — promote to `evals/`

**ADR:** [ADR-0005 Phase 5](docs/adr/0005-entity-index-audit-and-automated-deduplication.md#phase-5--recurring-cross-model-benchmark-ci-signal-for-model-drift)
**Effort:** ~1 hour
**Why for launch:** Free quality signal. When OpenRouter rotates Grok 4.20
to the next slug (and they will), this is your one-command check that
the replacement doesn't regress cross-page consistency.

### Tasks
- [ ] Move `c:\tmp\entity_model_compare.py` to `evals/entity_extraction_benchmark.py`.
- [ ] Commit the fixed 10-page sample list (currently inline in the script).
- [ ] Document how to run it and what the metrics mean in a short
      `evals/README.md`.
- [ ] Optional: add a Dagster manual-trigger asset that runs it.

### Done when
A new contributor can `python evals/entity_extraction_benchmark.py` and
get a per-model report of within-page quality + cross-page drift counts,
in under 20 minutes.

---

## 2. Reference eval set + CI scaffolding — minimum viable

**ADR:** [ADR-0004](docs/adr/0004-reference-eval-set-and-ci-gates.md)
**Effort:** ~4 hours
**Why for launch:** Without this, every change is unmeasured. Even 10
developer-best-guess questions is much better than zero. The eval set
grows post-launch as Reformed pastors on Puritan Board surface real
failure modes.

### Tasks
- [ ] Create `evals/gill_reference_set.jsonl` with the format from
      ADR-0004 (id, question, expected_behavior, must_cite, should_cite,
      must_not_cite, reference_summary, category, difficulty).
- [ ] Seed with 10 questions covering the categories we already know:
      - scapegoat (TypeOrSymbol / partial match)
      - Logos (definition / partial match)
      - sheep / "I lay down my life" (typology / partial match)
      - how many Simons (enumeration)
      - two thieves (refusal — Gill doesn't name them)
      - who is Peter (person)
      - who is John (person — disambiguation)
      - what is the Day of Atonement (doctrine)
      - what is justification (doctrine)
      - explain Genesis 1:1 (verse-specific)
- [ ] Write `evals/run_eval.py` that hits `/api/search` per question,
      scores refusal correctness + citation overlap, emits a markdown
      report.
- [ ] Add a GitHub Action that runs the eval on every PR touching
      `backend/`, `baml_src/`, or `pipeline/`. Hard-fail on
      `must_not_cite` violations; soft-warn on score regressions.
- [ ] Run baseline against current `main` and commit the scores as the
      initial benchmark.

### Done when
A PR that introduces a regression on a known-good question is caught in
CI rather than in production.

---

## 3. Verbatim quote verification

**ADR:** [ADR-0006](docs/adr/0006-verbatim-quote-verification.md)
**Effort:** ~3 hours
**Why for launch:** Quote integrity is the project's faithfulness
contract. The Puritan Board audience will copy-paste quoted lines into
Gill PDFs to verify. If the model ever slips into paraphrase-with-
quote-marks, this is the safeguard that catches it before a user does.

### Tasks
- [ ] Add `_normalize` + `_verify_quotes` helpers in
      `backend/bot.py` per ADR-0006's implementation sketch.
- [ ] Wire into `GroundedGillBot.forward()` after the existing citation
      checks.
- [ ] Start in strict mode (return "Verification Failed" on any
      paraphrased quote). Telemetry on which quotes fail will inform
      whether to relax.
- [ ] Add `quote_verification` to the API response object so the
      frontend can surface the result.
- [ ] Run the 10-question eval set (from #2) and confirm no false-
      positive rejections on known-good answers. Tune normalization
      (italics markers, footnote refs) if any legitimate quotes are
      rejected.

### Done when
The eval set passes with verification enabled, AND the test set you
re-ran earlier this session (scapegoat / Logos / sheep / Simons) all
still produce verbatim answers without verification failures.

---

## 4. Outage fallback — Tier 1 static maintenance page

**ADR:** [ADR-0007](docs/adr/0007-availability-and-outage-fallback.md)
**Effort:** ~2 hours
**Why for launch:** Home ISP outages will happen. A Puritan Board thread
landing on a 5xx error during a 24-hour outage costs more than the
outage itself. A dignified maintenance page is not a credibility hit;
silent failure is.

### Tasks
- [ ] Create `frontend-fallback/index.html` matching the live site's
      visual style. Brief outage message, Gill-flavored tone, link to
      GitHub repo. Pure static HTML/CSS — no JavaScript that depends on
      a backend.
- [ ] Deploy to Cloudflare Pages as `gya-fallback.pages.dev` (or chosen
      subdomain).
- [ ] Add a Cloudflare Worker (or Page Rule) on goatyardarchive.org
      that healthchecks `/health` and rewrites to the fallback when
      origin is unreachable. Cache health state ~30s, require 2+
      consecutive failures before flipping (avoid oscillation).
- [ ] Set up a Cloudflare alert: 5xx rate from origin > 20% over 5 min
      → existing Slack channel.
- [ ] Pre-launch smoke test:
      - [ ] Stop backend pod, confirm fallback serves within 60s.
      - [ ] Confirm `/api/search` during outage returns either the
            fallback page OR a graceful JSON error based on `Accept`
            header (not raw 502).
      - [ ] Restart backend pod, confirm return to live within 60s.

### Done when
Stopping the home backend pod produces a maintenance page within 60
seconds, and restarting brings the site back within 60 seconds, with no
manual Cloudflare action required.

---

## Post-launch (intentionally deferred)

Captured here so they don't get lost, but **not blocking the launch**.

- [ADR-0003](docs/adr/0003-cross-encoder-reranking.md) — Cross-encoder
  reranker for precision improvement. Best with eval-set feedback from
  real Puritan Board questions guiding what to tune.
- [ADR-0002](docs/adr/0002-chapter-and-book-prefix-retrieval.md) —
  Chapter/book navigation queries. Add if Langfuse traces show users
  type these.
- [ADR-0001](docs/adr/0001-enumeration-query-path.md) — Enumeration
  questions ("how many X", "list all Y"). Defer unless the eval set
  reveals it as a frequent gap.
- [ADR-0005 Phase 6](docs/adr/0005-entity-index-audit-and-automated-deduplication.md#phase-6-deferred--targeted-enrichment-with-qwen3)
  — Qwen3 enrichment pass for theologically-dense pages.
- [ADR-0005 Phase 7](docs/adr/0005-entity-index-audit-and-automated-deduplication.md#phase-7-deferred--quality-measurement-and-re-extraction-triage)
  — Entity quality measurement with expert ground truth.
- [ADR-0007 Tier 2](docs/adr/0007-availability-and-outage-fallback.md#tier-2--cold-backup-on-cheap-arm-cloud-deferred)
  — Cold backup on cheap ARM cloud. Trigger: 2+ outages > 12 hours
  each in a 90-day window, OR an outage during peak Puritan Board
  traffic.
