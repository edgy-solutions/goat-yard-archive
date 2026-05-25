# ADR-0005: Entity Index Normalization, Deduplication, and Pipeline Self-Healing

- **Status:** Proposed (revised 2026-05-17 after auditing the live entity index AND running a 10-page cross-model extraction comparison)
- **Date:** 2026-05-17
- **Deciders:** Chris Nogradi

## Context

The `TheologicalEntity` collection is the foundation underneath the entire query pipeline:

- BAML's `OptimizeSearchQuery` maps user concepts to entities by selecting from a manifest of ~50 BM25-ranked candidates.
- `get_relevant_entities` (shipped 2026-05-17) substring-matches user query tokens against entity names.
- Chunks are denormalized with `entities^3` boost in BM25 and cross-referenced via `mentions_entity` for graph traversal.

The extraction *contract* is solid. [`gill_extract.baml`](../../baml_src/gill_extract.baml) defines 11 categories, plus a `biblical_era` and `role` field for the "Joseph fix" (disambiguating OT Joseph from NT Joseph). Deterministic UUIDs in [`ingest.py:407-510`](../../pipeline/scripts/ingest.py#L407-L510) auto-merge entities across pages when `(normalized_name, biblical_era, role, category)` match.

But the *execution* of that contract over 7,000+ pages does not produce the consistent metadata tuples the dedup primitive assumes. This ADR was originally written before we had access to the entity files. Now we do (they live in a sibling repo at `dr-voluminous/commentary/artifacts/entities/`), and an audit produces concrete, named failure cases.

### Audit findings (2026-05-17)

Searching the 1,699 per-page entity JSON files revealed:

**Cross-category fragmentation of the same biblical reality:**
- `Azazel`, `category: "TypeOrSymbol"`, description: *"Goat sent to; possibly Satan"*
- `Azazel`, `category: "OriginalWord"`, description: *"Inscription on lot for scape-goat"*
- Same underlying entity, two graph nodes, because the dedup primitive keys on category.

**Casing fragmentation within the same category:**
- `scape-goat`, `category: "TypeOrSymbol"`, `biblical_era: "OldTestament"`, `normalized_name: null`
- `Scape-goat`, `category: "TypeOrSymbol"`, `normalized_name: null`, description: *"Type of Christ bearing sins into wilderness"*
- Same entity, two graph nodes, because the dedup primitive treats `scape-goat` and `Scape-goat` as different normalized names.

**`normalized_name: null` outputs:**
- Both `scape-goat` entries have `normalized_name: null`. Several other entities in the same file have the same.
- The BAML schema declares this field as `string?` (optional), so the extractor is free to leave it empty when it doesn't have a strong opinion. When `normalized_name` is null, dedup falls back to `name`, which still has the casing/hyphenation variation problem.

**Substring-search miss:**
- The shipped `get_relevant_entities` substring search uses patterns like `*scapegoat*` against the `name` field. That doesn't match `scape-goat` (with hyphen) or `Scape-goat`. So when a user asks "What is the spiritual meaning of the scapegoat?", BAML's entity manifest doesn't include any of the actual scapegoat entities — even though the entities exist in the index.

This last point caused a real, traced, reproducible failure in the 2026-05-17 session logs: the "scapegoat" query refused even though the corpus contains rich Lev 16 commentary linked to scape-goat entities.

### Why this happens — the responsibility split is wrong

The current pipeline asks the LLM (Grok-4.1-fast, per [main.baml:67-75](../../baml_src/main.baml#L67-L75)) to do **both** semantic extraction AND deterministic normalization in the same pass. These are fundamentally different tasks:

- **Semantic extraction** ("what entities are in this passage?", "what's the role?", "what category?") requires reading comprehension. LLMs are good at this. We should keep delegating it.
- **Normalization** ("strip the hyphen", "always pick the singular form", "use the same canonical spelling across all 7,000 pages") requires deterministic transformation. LLMs are unreliable at this. **No model — Grok or otherwise — can guarantee consistency across thousands of independent extractions.** A more rigorous model (Claude, GPT-4o) would do better; it would still fail sporadically; and it would cost 3-5x more for the bulk extraction.

The deeper architectural issue: BAML's schema system can enforce **type constraints** (`string` not null, `enum` member) but cannot enforce **semantic constraints** like "this field must be different from `name`" or "this field must equal the canonical form across all entities". The "non-negotiable" the original architecture wanted is not enforceable at the prompt or schema level. It has to be enforced in code.

## Empirical validation (2026-05-17 cross-model test)

To rule out "the failures are model-quality artifacts; switch to a better model and it goes away", we ran the same extraction prompt against three frontier models across 10 representative pages (Lev 16 cluster + NT cross-references + a Genesis 1 sample). All three produced clean within-page results — and all three drifted across pages on the same kinds of failures present in production. Test script and raw outputs: `c:\tmp\entity_model_compare.py`, `c:\tmp\entity_compare_out\`.

### Within-page quality (10-page averages)

| Model | Avg latency | Throughput | Entities/page | Within-page norm_name fill | Within-page cross-cat dupes |
|---|---:|---:|---:|---:|---:|
| `x-ai/grok-4.20` | 6.8s | 206 tok/s | 21.8 | 99.6% | 0 |
| `deepseek/deepseek-chat` | 102s | 11.7 tok/s | 17.8 | 100% | 0 |
| `qwen/qwen3-235b-a22b-2507` | 79s | 30.5 tok/s | 35.7 | 100% | 0 |

Within a single extraction, every model is essentially clean. The original `normalized_name: null` failures we saw in production data trace to an older, weaker prompt — not to model capability.

### Cross-page drift (the actual failure mode)

| Model | Recurring entities (in ≥2 pages) | Name-form drift | Category drift | Era drift | Normalized_name drift |
|---|---:|---:|---:|---:|---:|
| `x-ai/grok-4.20` | 25 | 2 | 5 | 9 | 8 |
| `deepseek/deepseek-chat` | 21 | 0 | 2 | 10 | 9 |
| `qwen/qwen3-235b-a22b-2507` | 33 | 1 | 3 | 10 | 16 |

**Every model produces meaningful drift.** Concrete examples (one per model):

- **Grok:** `Targum of Jonathan` flips between `CitedAuthority` and `ManuscriptOrVersion` across 5 pages. `Day of Atonement` casing drifts (`Day of Atonement` vs `day of atonement`) across 3 pages.
- **DeepSeek:** `John` normalized as both `"John son of Zebedee"` and `"John the Baptist"` — two different people conflated under one entity. `Azazel` flips between `BiblicalFigure` and `TypeOrSymbol`.
- **Qwen3:** `Christ` flips between `BiblicalFigure` and `TypeOrSymbol` across **9 pages**. `the Lord` normalized as both `"God"` and `"Jesus Christ"` across 5 pages — directly contradicting the prompt's explicit canonicalization rule.

The data is unambiguous: **cross-page consistency is an architectural property, not a model property.** This validates the responsibility-split principle below and the code-side enforcement approach in the Decision section.

### Model role assignments (informed by these results)

Rather than "pick the best model", the test argues for **using each model where it's strongest**:

| Role | Model | Why |
|---|---|---|
| **Bulk extraction** (per-page during ingestion) | **`x-ai/grok-4.20`** | 12-15x faster than alternatives; within-page quality matches; cross-page drift is everyone's problem and handled in code |
| **Auto-merge judge** ("are these two entries the same entity?") in Phase 3 | **`deepseek/deepseek-chat`** | Best at name-form consistency (zero name drift in the test); slow latency doesn't matter for low-volume judgments |
| **Optional enrichment pass** for theologically-dense pages | **`qwen/qwen3-235b-a22b-2507`** | Extracts 60-100% more entities than the others; useful for rabbinic-heavy passages where breadth matters more than throughput; reserve as future work |

Note that `x-ai/grok-4.1-fast` (the model in [main.baml:73](../../baml_src/main.baml#L73) today) returns 404 on OpenRouter — it has been rotated out. Updating the slug to `x-ai/grok-4.20` is an immediate prerequisite regardless of any other change in this ADR.

## The principle this ADR adopts

**Let the LLM do semantic work; let code do deterministic work.** The current design mixes them in a single BAML output struct. The proposed design splits them:

| Field | Computed by | Justification |
|---|---|---|
| `name` | LLM | Verbatim from text — true semantic extraction |
| `category` | LLM (enum) | Requires reading the passage's intent |
| `biblical_era` | LLM (enum) | Requires reading context |
| `role` | LLM | Free-text disambiguator — genuinely subjective |
| `description` | LLM | Free-text summary |
| `cross_references` | LLM | Reading comprehension |
| `normalized_name` | **Code** | Deterministic — code can do it reliably |
| `search_key` | **Code** | Lowercase + alphanumeric strip — pure transformation |
| `dedup_id` | **Code** | Hash of `(search_key, biblical_era)` — not `(name, category, role)` |
| `categories` (array) | **Code, accumulated** | Multiple LLM-extractions of the same entity contribute multiple category labels to the same node |

The current design has the LLM doing 9 of those 10; the proposed design has it doing 6.

## Decision

A backfill-first plan that achieves most of the clean-slate design's benefits without re-extracting 7,000 pages through Grok. Re-extraction is treated as a future option for measured-quality cases, not as a prerequisite.

The phases are sequenced so that the cheapest, safest, highest-value changes ship first. Phases 0 and 1 are independently valuable even before the rest is built — they make future extractions cleaner and the search layer immediately better.

### Phase 0 — Immediate, no-risk cleanup (do now, independent of the rest)

These changes do not depend on schema migration or backfill and can ship today:

- **Update [`main.baml:73`](../../baml_src/main.baml#L73) from `x-ai/grok-4.1-fast` to `x-ai/grok-4.20`.** The current slug returns 404 on OpenRouter — you're already off the live Grok generation. This is a free upgrade.
- **Remove `normalized_name` from the BAML output struct** in [`gill_extract.baml`](../../baml_src/gill_extract.baml). The LLM was unreliable at filling it across pages (see Empirical Validation section — even with strict "MUST fill" instructions, all three tested models drifted). Code computes it deterministically downstream.
  - **Why this is safe today:** [`ingest.py:412`](../../pipeline/scripts/ingest.py#L412) already falls back to `name` when `normalized_name` is None (`base_id = str(normalized_name).upper()... if normalized_name else str(name).upper()...`). Removing the field from BAML output will result in `None` being passed, which the existing code handles. No ingestion break.
  - **What it doesn't fix yet:** existing fragmentation in the live index. That's Phase 3.
- Simplify the BAML prompt — drop the `NORMALIZATION RULES` section and the disambiguation rules that depend on `normalized_name`. Keep the category and era guidance.

This phase was originally listed as Phase 4 (last). Promoting it to Phase 0 because the empirical evidence shows the LLM's `normalized_name` outputs are net-harmful when they drift cross-page, and removing them is a single-line BAML edit with no migration cost.

### Phase 1 — Schema additions

Add to `TheologicalEntity` in [`setup_weaviate_schema.py`](../../pipeline/scripts/setup_weaviate_schema.py):

- **`search_key`** (TEXT, `Tokenization.FIELD`, `skip_vectorization=True`) — canonical lookup key. Populated from `re.sub(r'[^a-z0-9]', '', (normalized_name or name).lower())`. Indexed for `like` matching.
- **`categories`** (TEXT_ARRAY) — accumulating list of category labels. An entity can be both `TypeOrSymbol` and `OriginalWord` (as Azazel is) without forking into separate graph nodes.

The existing `category` field stays for backward compatibility but becomes secondary. Reads prefer `categories` when present.

### Phase 2 — Ingest changes

In [`ingest.py:407 get_or_create_entity`](../../pipeline/scripts/ingest.py#L407):

- **Compute `search_key` deterministically** from the LLM's `name`. With Phase 0 already shipped, `normalized_name` will typically be None from BAML — code uses `name` directly.
- **Change the dedup_id primitive** from `(normalized_name, era, role, category)` to `(search_key, era)`. Same biblical reality → same UUID, regardless of casing, hyphenation, or category-perception variation.
- **Append to `categories` array on collision** rather than creating a new entity. If page 200 said Azazel is `TypeOrSymbol` and page 450 said `OriginalWord`, the merged entity has `categories: ["TypeOrSymbol", "OriginalWord"]`.
- **Compute and populate `normalized_name`** as a human-readable display form, derived from `name` (e.g. title-case, hyphen-strip). This is purely a display-layer field — distinct from `search_key` which is for matching.

### Phase 3 — Backfill script + Dagster asset

New script `pipeline/scripts/backfill_entity_search_keys.py`:

1. Iterate all entities currently in `TheologicalEntity`.
2. Compute `search_key` for each; write it back via `update`.
3. Populate `normalized_name` where null (from `name` via deterministic transformation).
4. Group by `(search_key, biblical_era)`. Within each group:
   - **Auto-merge if** (a) all members have the same `role` or one is null, (b) descriptions are not contradictory (cosine similarity > 0.7 when both present), (c) merging would reduce graph nodes.
   - **For ambiguous merges**, use **`deepseek/deepseek-chat`** as the "are these two entries the same entity?" judge. The 10-page test showed DeepSeek has the strongest within-extraction name-form consistency (zero name drift) — well-suited to pairwise identity judgments. Per-pair latency doesn't matter at this volume.
   - **Flag for human review if** the LLM judge returns "uncertain" or roles are semantically distant (e.g. `James son of Zebedee` vs `James son of Alphaeus` — same search_key + era but legitimately distinct).
   - During merge: union the `categories` arrays, union the descriptions (or pick the longest), redirect all `mentions_entity` references from delete-UUID to keep-UUID, delete the old entity.

New Dagster asset `entity_normalization_global` in [`assets.py`](../../pipeline/assets.py):

- Runs after `ingest` (depends on `AllPartitionMapping` of `ingest`).
- Invokes the backfill script.
- Idempotent — only touches entities missing `search_key` or with detected fragmentation.
- Outputs metrics as `MaterializeResult` metadata: entities backfilled, auto-merges performed, manual-review-queue size.

The existing `scan_duplicate_entities_global` asset is replaced by this new one. The `scan` command in [`deduplicate_entities.py`](../../pipeline/scripts/deduplicate_entities.py) remains as an inspection tool but is no longer the entire dedup strategy.

### Phase 4 — Search update

In [`backend/gill_search.py get_relevant_entities`](../../backend/gill_search.py):

- Change substring search target from `name` to `search_key`.
- Drop the multi-casing pattern variants (`*scapegoat*`, `*Scapegoat*`, `*SCAPEGOAT*`) — `search_key` is always lowercase.
- Drop the middle-third split patterns added in this session — they're no longer needed because `search_key` of `"scape-goat"` is `"scapegoat"`, matching the user's token directly.
- The substring code becomes substantially simpler: one query per significant token, exact substring match against `search_key`.

(This was previously Phase 5; renumbered after Phase 4's promotion to Phase 0.)

### Phase 5 — Recurring cross-model benchmark (CI signal for model drift)

The 10-page extraction comparison script that produced this ADR's empirical evidence should become a recurring benchmark, not a one-shot. As models on OpenRouter rotate (Grok 4.20 → 4.21 → next-gen, etc.), we need to know quickly whether a model update degrades cross-page consistency.

- Promote `entity_model_compare.py` (currently at `c:\tmp\`) to `evals/entity_extraction_benchmark.py`.
- Run on a fixed 10-page sample committed to the repo (or referenced by path into `dr-voluminous`).
- Outputs: per-model latency, throughput, within-page quality, cross-page drift counts.
- Run on-demand via Dagster (manual trigger) or weekly on schedule.
- Pair with [ADR-0004](0004-reference-eval-set-and-ci-gates.md)'s answer-quality eval — together they form the full quality signal for any retrieval or model change.

### Phase 6 (deferred) — Targeted enrichment with Qwen3

The 10-page test showed Qwen3-235B extracts 60-100% more entities per page than Grok or DeepSeek, including legitimate cited authorities the others miss (Talmud sages, minor commentators, etc.). For theologically-dense pages — rabbinic-heavy passages, footnote-laden sections — Qwen3 may surface entities Grok systematically drops.

This is an optional enrichment pass:

- After [ADR-0004](0004-reference-eval-set-and-ci-gates.md) identifies pages or categories where entity recall is low (e.g. cited-authority recall drops below threshold on a Lev 16 page), select those pages.
- Re-extract just those pages with `qwen/qwen3-235b-a22b-2507`.
- Merge new entities into the existing graph via the Phase 3 dedup pipeline.
- Cost: targeted, not corpus-wide. Probably ~50-200 pages out of 7,000.

Only worth doing once Phase 4 (quality measurement) reveals the gap is real.

### Phase 7 (deferred) — Quality measurement and re-extraction triage

Build the expert-tagged ground truth from [ADR-0004](0004-reference-eval-set-and-ci-gates.md) and use it to measure entity extraction precision/recall/fragmentation rate over time. This is the long-term cleanup signal. If Phase 7 reveals systematic extraction misses that backfill cannot recover (e.g. Grok consistently misses certain entity types), that motivates a targeted re-extraction over specific pages — feeding into Phase 6's selection of pages for the Qwen3 pass.

## On the Grok / BAML question (addressing it directly)

**Was Grok the wrong model?** Probably not, but it's a debatable choice and not the load-bearing issue. Grok-4.1-fast is optimized for cost and throughput; it's acceptable for structured extraction at this scale. A more rigorous model would produce ~5-15% fewer fragmentation cases and somewhat more reliable `normalized_name` fills, at 3-5x the bulk-extraction cost. **The fragmentation we observed is not a model-quality problem we can solve by upgrading.** It is a design problem — delegating deterministic work to a probabilistic process.

**Could BAML have been told normalization is non-negotiable?** Partially, and the partial part is not enough. BAML could enforce:

- `normalized_name: string` (required, not nullable) — catches the null case
- Closed enums for `category` and `biblical_era` — already done
- Length minimums, regex patterns on strings — currently not used

BAML cannot enforce:

- "`normalized_name` must canonicalize hyphens"
- "`normalized_name` must be unique across all extractions of the same biblical reality"
- "If 7,000 pages mention Peter, all 7,000 must produce the same `normalized_name`"

The "must" the architecture wanted is a property of *the relationship between extractions across pages*, not of any single extraction. No prompt, no schema, no model alone can guarantee it. **That property has to be enforced by code that sees all extractions.** Which is what Phase 3 does.

## Alternatives Considered

1. **Continue current manual scan-and-merge.** Doesn't scale; fragmentation accumulates faster than humans clear it. Confirmed by the audit findings.
2. **Upgrade to Claude Sonnet or GPT-4o for entity extraction.** Would reduce fragmentation rate by an estimated 5-15% based on instruction-following studies. Cost is 3-5x the original Grok bill. Does not eliminate the fundamental issue; deterministic guarantees still require code-level enforcement.
3. **Re-extract everything with the new BAML schema.** Cleanest theoretical outcome. Substantial cost (vision OCR + LLM extraction across 7,000 pages). The backfill plan achieves an estimated 80% of the benefit without this cost.
4. **LLM-based pairwise entity merge** ("are these the same entity? yes/no") for the manual-review queue. Useful for accelerating Phase 3's flagged-for-review tier. Not a substitute for the rule-based auto-merge — too slow and expensive for the bulk of merges.
5. **Migrate to a managed entity-linking service** (Wikidata, ConceptNet). Theologically specific entities ("Aben Ezra", "Simon Maccabeus", "Scape-goat") have weak coverage in general-purpose KBs. Would degrade quality on the entities that matter most for this corpus.

## Consequences

### Positive
- The substring-search failure on `scape-goat` (and any compound-noun entity) is fixed at the right layer — by normalizing the index, not by patching the query path.
- The cross-category fragmentation of `Azazel` (and any entity perceived as multiple categories) is collapsed into a single graph node carrying both categories.
- The `normalized_name: null` failure mode is eliminated for new and existing entities.
- BAML extraction becomes simpler (one fewer field to fill, one fewer field to validate).
- The pipeline becomes self-healing: new ingestion drift is detected and corrected on every run by the Dagster asset, rather than accumulating until a human notices.

### Negative
- Schema migration on `TheologicalEntity` is a one-time disruptive change (adding two properties). Existing data needs the backfill to populate them. The migration is not zero-downtime.
- The dedup primitive change in `get_or_create_entity` could in principle merge entities that *should* have stayed distinct. Mitigation: the auto-merge rules are conservative; ambiguous cases stay in a review queue; the deterministic-UUID approach means a misguided merge can be re-derived from raw extractions if needed.
- The Dagster asset adds a recurring compute cost (iterating all entities, computing keys, detecting candidate merges). At ~10-50k entities, this is small but non-zero.

### Risks
- **Aggressive auto-merge collapses legitimate distinct entities.** Mitigation: rules require `(search_key, era)` match AND compatible roles AND non-contradictory descriptions. Cases that fail any of those go to manual review, not auto-merge.
- **The manual-review queue becomes a backlog nobody addresses.** Mitigation: surface queue depth as a Dagster asset metric; ADR-0004's eval set will flag regressions if the queue starves the system of useful merges.
- **Search regression on entities whose `name` had meaningful casing.** E.g. `LORD` (all-caps as a stylistic mark of the Tetragrammaton) → search_key `lord` may collide with lowercase usage. Mitigation: spot-check after backfill; if real regressions appear, treat all-caps specially.
- **BAML extraction format change (removing `normalized_name`)** could break downstream code that expects the field. Mitigation: introduce the change as additive (add `categories` array, populate `normalized_name` from code) before removing the BAML field; sunset the field after all consumers are updated.

## Open Questions

- **Threshold for description-cosine in auto-merge:** 0.7 is a guess. Needs empirical tuning against [ADR-0004](0004-reference-eval-set-and-ci-gates.md) once that exists.
- **Should `role` participate in dedup at all?** Current design says no (it's a facet, not an identity-distinguishing field). But `James son of Zebedee` vs `James son of Alphaeus` legitimately have the same `search_key` + `era` and are distinguished only by `role`. The proposed design flags these for manual review rather than auto-merging — but if there are many of them, the queue becomes overwhelming. May need to add role-similarity to the auto-merge decision after measuring.
- **What about entity-extraction misses entirely?** If Grok dropped "Aaron" from a particular Lev 16 page, neither backfill nor merge can recover it. Phase 6 (quality measurement) will surface this; the remedy is targeted re-extraction over specific pages with the new BAML schema, not a corpus-wide rerun.
- **Snapshot strategy for the entity index** (originally Phase 1 of this ADR): now that we know it lives in `dr-voluminous`, we can audit any current snapshot. But a recurring snapshot to MinIO with versioning is still worth doing so the live Weaviate state is recoverable. Treat as a parallel small workstream, not a phase of this ADR.

## Implementation Order

1. **Phase 0** — BAML/model cleanup. Two single-file edits (`main.baml` grok slug, `gill_extract.baml` drop `normalized_name`). Independent of all other phases. Ship today.
2. **Phase 1** — Schema additions to `setup_weaviate_schema.py`. Additive, low risk. Can land independently.
3. **Phase 2** — Ingest changes (`ingest.py`). New entities are normalized at write time. Land after Phase 1 schema is in place.
4. **Phase 3 (initial)** — Backfill script populates `search_key` on existing data and performs initial auto-merge. Validate on a copy of the Weaviate index before running on production.
5. **Phase 4** — Search update (`gill_search.py`). Substring search uses `search_key`. Land after Phase 3 backfill so existing entities have keys populated.
6. **Phase 3 (recurring)** — Wire the backfill as a recurring Dagster asset to catch drift.
7. **Phase 5** — Move the cross-model benchmark script to the repo and schedule it.
8. **Phase 6 / Phase 7** — Deferred. Only after [ADR-0004](0004-reference-eval-set-and-ci-gates.md)'s eval set reveals specific quality gaps worth targeting.

## Dependencies

- Phases 6 and 7 reuse infrastructure from [ADR-0004](0004-reference-eval-set-and-ci-gates.md).
- The shipped substring matching in `get_relevant_entities` (added 2026-05-17) is superseded by Phase 4 — the middle-third split patterns become unnecessary once `search_key` is populated.
- Phase 3's auto-merge LLM judge uses the model configured in [main.baml](../../baml_src/main.baml) for the new role; recommendation is `deepseek/deepseek-chat`. Add as a new BAML client.
- All ADRs depending on entity-index quality ([ADR-0001](0001-enumeration-query-path.md), [ADR-0003](0003-cross-encoder-reranking.md)) become more reliable after this work, but do not strictly require it to ship.
