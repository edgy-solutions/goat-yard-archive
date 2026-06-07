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

## 4. Outage fallback — Tier 1 in-app graceful degradation

**ADR:** [ADR-0007](docs/adr/0007-availability-and-outage-fallback.md) (revised 2026-05-25 — see ADR for the rationale shift from separate-maintenance-page to in-app degradation)
**Effort:** ~4-6 hours (slightly more upfront than the original Worker-based design, in exchange for simpler architecture + better UX)
**Why for launch:** Home ISP outages will happen. A Puritan Board thread
landing on a 5xx error during a 24-hour outage costs more than the
outage itself. Graceful in-app degradation feels like a transient app
error ("we're briefly unable to reach the commentary index") rather
than "this site is broken" — meaningfully better for the audience.

### Tasks

**Cloudflare Pages setup (frontend hosting):**
- [ ] Connect this GitHub repo to a new Cloudflare Pages project.
- [ ] Build command: `cd frontend && npm install && npm run build`;
      output dir: `frontend/dist`.
- [ ] Set build-time env vars on Pages: `VITE_CLERK_PUBLISHABLE_KEY`,
      `VITE_POSTHOG_KEY`, `VITE_POSTHOG_HOST`, `VITE_API_BASE`
      (e.g. `https://goatyardarchive.org/api`).
- [ ] Verify the deploy serves successfully at the Pages default URL.

**DNS / routing:**
- [ ] On the goatyardarchive.org zone:
      - `/api/*` → home origin (existing routing)
      - everything else → Cloudflare Pages
- [ ] Verify with curl: `/api/health` hits home, `/index.html` hits Pages.

**Frontend resilience changes (in `frontend/`):**
- [ ] Add a fetch wrapper that catches network errors / 5xx / timeouts
      and exposes them as a typed error to React.
- [ ] Create a `<BackendUnavailable />` component matching the site's
      tone (one or two sentences, GitHub link, contact info).
- [ ] Wire all API-dependent surfaces to render `<BackendUnavailable />`
      on errors rather than empty / spinner-stuck states.
- [ ] Cache `/api/books` in localStorage with a TTL so the app's chrome
      renders during cold-start outages.

**Runtime config migration:**
- [ ] Read `VITE_*` env vars in `src/config.ts` via `import.meta.env`.
- [ ] Remove the server-side `__RUNTIME_CONFIG__` injection from
      `index.html` (no longer needed once SPA is on Pages).

**Observability:**
- [ ] Cloudflare alert: 5xx rate from origin > 20% over 5 min →
      existing Slack channel.
- [ ] Optional: PostHog event for `BackendUnavailable` renders per
      session.

**Pre-launch smoke test:**
- [ ] Stop backend pod, reload the site — SPA should load from Pages
      and immediately render `<BackendUnavailable />` on the search page.
- [ ] Confirm `/api/search` returns 502 (Cloudflare default), which the
      SPA's fetch wrapper catches and renders the unavailable state for.
- [ ] Restart backend pod; verify the SPA returns to normal on retry
      without a full page reload.

### Done when
Stopping the home backend pod still shows users a working site (chrome,
navigation, branding) with a clear inline "temporarily unavailable"
message; restarting brings normal operation back without manual
Cloudflare action.

---

## Post-launch (intentionally deferred)

Captured here so they don't get lost, but **not blocking the launch**.

### Top priority: blue/green deploy for safe promotion

Current promote flow is one-instance: wipe prod Weaviate, copy from test
into prod live storage, helm-upgrade backend with new image tag.
Recoverable (we have safety snapshots) but visible to users if something
fails mid-way.

Target architecture:

- **Two Weaviate statefulsets** in gya-backend (`weaviate-blue`,
  `weaviate-green`), each with its own PVC.
- **Two backend deployments** in gya-frontend, one per color, each with
  `WEAVIATE_URL` pointing at its color's service.
- **Two label-selector services**: `weaviate-live` and
  `gya-frontend-api-live` select on `live=true`. The cloudflared tunnel +
  Worker route `goatyardarchive.org/api/*` only ever hits these live
  services.
- **Preview hostname**: `preview.goatyardarchive.org` tunnel hostname
  routes to the *standby* color so we can validate it under real DNS +
  TLS before the swap.
- **Promotion script** (in `pipeline/scripts/promote_blue_green.py` or
  similar): determines standby color, wipes its data, runs
  `copy_test_to_prod.py` against the standby's Weaviate URL, applies the
  new helm release to the standby, runs evals against `preview.`, then
  flips `live=true` labels atomically.
- **Rollback**: re-flip the labels. Old color's data and pods are
  preserved until next promotion overwrites them.

Estimated effort: ~1 focused day. Best done after the launch settles and
the existing single-instance flow has caused at least one minor incident
that motivates the work.

CI alignment (also blocked on this): with blue/green in place we can wire
GitHub Actions to push to standby on tag, gating the live swap on a
manual approval step. Without blue/green, tag-driven deploy is a foot-gun
because it would touch the live path directly. Either set up a
self-hosted runner on the launchpad, ArgoCD / Flux in the cluster, or a
simple poll-based agent so the helm side can be automated too.

### Known regressions / behaviors to investigate
- [ ] **Verifier prompt tightening (fallback if regex over-pairs).** The
      quote/citation regex was widened to allow up to 80 chars of narration
      between a quote and its `[SID]` because the model legitimately writes
      `"verbatim" framing [SID]`. If real-world traffic shows the looser
      gap causing silent mis-pairing (a quote getting attributed to the
      wrong nearby SID), the fallback is to add explicit "do NOT" examples
      to GillSignature instead — e.g. `Wrong: "quote" explanation [SID].
      Right: "quote" [SID] explanation.` Holding off on the prompt change
      preemptively because more instructions = more surface area for the
      model to misinterpret something else.
- [ ] **Verifier refinement: every Gill citation needs at least one Gill
      quote.** Today the verifier checks each `"quote" [SID]` pair as a
      substring match against the chunk's combined KJV+commentary source.
      That catches paraphrased "quotes" but not the more subtle failure
      where the model attaches *only* KJV quotes (or no quote at all) to a
      Gill citation — Gill is summarized rather than quoted. The Garden
      query (2026-06-07) hit this: `[GENESIS_3_24_S00]` was cited with no
      quote attached, `[GENESIS_3_23_S00]` only had KJV quotes attached,
      and `[GENESIS_2_15_S00]` only had a KJV paraphrase. The chunk
      already cleanly separates Gill's commentary from the KJV header, so
      the fix is to track quote provenance (Gill vs KJV) during
      verification and fail when a cited SID has no Gill-side match. KJV
      quotes remain fully valid as quotes — they just don't satisfy the
      "must quote Gill" obligation that goes with citing him.
- [ ] **`real_ishmael_circumcision_001`** in the eval set fails the same
      way as `two_thieves_001`: refuses with "the provided extracts do
      not appear to address this specific inquiry" when the calibration
      expects an answer. Two consecutive isolated re-runs reproduced the
      refusal deterministically — likely a retrieval issue specific to
      the question phrasing (multi-clause + Bible reference numbers in
      the body). Investigate alongside two_thieves.
- [ ] **`two_thieves_001`** in the eval set fails (refuses instead of
      answering). Calibration was flipped to `expected=answer` after we
      observed Gill *does* discuss the Papist Disma tradition on
      Luke 23:43. The bot in prod still refuses — likely the
      LUKE_23_43_S05 chunk isn't surfacing in retrieval for the way the
      question is phrased. Investigate: run the query, dump the retrieved
      chunk IDs, see if Disma chunk appears at all.
- [ ] **Test Weaviate's HNSW snapshot was corrupt** (caused the original
      backup-based migration to fail). Fixed by deleting the corrupt
      snapshot file + restarting test Weaviate. **Verify the next
      backup→restore cycle on test works end-to-end** before the next
      promote. The Dagster `promote_test_vectors_to_prod` job should
      succeed without falling back to `copy_test_to_prod.py`.

### Deferred ADRs
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
