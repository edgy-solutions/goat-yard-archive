# ADR-0005: Entity Index Audit and Automated Deduplication

- **Status:** Proposed
- **Date:** 2026-05-17
- **Deciders:** Chris Nogradi

## Context

The `TheologicalEntity` collection is the foundation underneath the entire query pipeline:

- BAML's `OptimizeSearchQuery` maps user concepts to entities by selecting from a manifest of ~50 BM25-ranked candidates.
- `get_relevant_entities` substring-matches user query tokens against entity names ([ADR not written, shipped 2026-05-17](../../backend/gill_search.py)).
- Chunks are denormalized with `entities^3` boost in BM25 and cross-referenced via `mentions_entity` for graph traversal.

The extraction *contract* is solid. [`gill_extract.baml`](../../baml_src/gill_extract.baml) defines 11 categories (Doctrine, Heresy, BiblicalFigure, HistoricalFigure, CitedAuthority, PeopleGroup, Location, TimePeriod, OriginalWord, ManuscriptOrVersion, TypeOrSymbol) plus a `biblical_era` and `role` field for the "Joseph fix" (disambiguating OT Joseph from NT Joseph). Deterministic UUIDs in [`ingest.py:407-510`](../../pipeline/scripts/ingest.py#L407-L510) auto-merge entities across pages when `(normalized_name, era, role)` match.

But the *execution* of that contract over 7,000+ pages depends on BAML producing consistent metadata tuples, and there is real evidence it does not:

- Query logs show noisy entities ranking in top-50 manifests for theological questions ("Aben Ezra", "Scolopendra", "Nedal") — strongly suggesting fragmentation, where a single concept is split across many low-frequency entity rows.
- Dedup is currently **manual**: [`deduplicate_entities.py`](../../pipeline/scripts/deduplicate_entities.py) provides a `scan` that lists collisions and a `merge <KEEP> <DELETE>` command that resolves them one pair at a time. No automated rules.
- The dedup primitive only catches fragmentation where `(normalized_name, era, role)` differ. If page 200 extracts Peter with `role="Apostle"` and page 450 extracts him with `role="Disciple of Christ"`, they get different UUIDs — same person, two graph nodes — and the manual scan flags them after the fact.

Additionally:

- **The per-page entity JSON caches are not checked into this repo.** They live at `$COMMENTARY_DATA_DIR/artifacts/entities/*.json` per [`recover_entities.py:9`](../../pipeline/scripts/recover_entities.py#L9). Despite a stated intent to make them auditable, they are not visible in the git tree. This means the entity layer that everything else depends on cannot be reviewed or diffed.
- **No precision/recall metric exists for entity extraction.** What fraction of distinct biblical persons in (say) Matthew have a unique entity row? What fraction are missing? What fraction are fragmented? Currently unknown.

## Decision

A four-phase plan to make the entity index visible, measurable, and self-cleaning.

### Phase 1: Make the entity index visible

- Snapshot the per-page entity caches to a versioned location:
  - **Option A (preferred):** MinIO bucket with versioning enabled; snapshot script committed to the pipeline.
  - **Option B:** Git LFS in this repo, with a periodic Dagster asset that commits the snapshot.
- Add a `audit_entities.py` script that summarizes the index: total entity count, distribution by category, top 50 most-cited entities, top 50 entities with single-chunk references (probable fragmentation candidates).
- Output: a human-readable markdown report at `evals/entity_audit_YYYY-MM-DD.md` per snapshot.

### Phase 2: Measure entity quality

- Build a ground-truth eval set of ~50 representative pages (mix of OT/NT, well-known/obscure passages).
- Manually tag the entities a domain expert expects to be extracted from each page.
- Run the extraction over those pages and compute:
  - **Precision:** of extracted entities, what fraction are correctly extracted real entities?
  - **Recall:** of expected entities, what fraction were extracted?
  - **Fragmentation rate:** how often is one logical entity split across multiple rows?
  - **Misclassification rate:** entities placed in the wrong category.
- This is analogous to (and could share infrastructure with) the answer-quality eval in [ADR-0004](0004-reference-eval-set-and-ci-gates.md).

### Phase 3: Automated dedup with rule-based auto-merge

Extend `deduplicate_entities.py` with an `auto_merge` command that applies safe rules without human review, escalating ambiguous cases to manual review:

| Auto-merge if... | Rationale |
|---|---|
| `normalized_name` matches AND `biblical_era` matches AND role embedding cosine > 0.85 | Same person + same era + semantically same role |
| `normalized_name` matches AND `biblical_era` matches AND one entity has empty `role` | Empty role is unrestrictive; merge into the more-specific one |
| `name` matches case-insensitively AND `category == "OriginalWord"` AND `biblical_era == "NotApplicable"` | Hebrew/Greek transliterations rarely have ambiguity |

Flag for manual review (don't auto-merge):
- Same `normalized_name` + same `biblical_era` but role embeddings far apart (legitimate distinct figures: "James son of Zebedee" vs "James son of Alphaeus").
- Same `name` across different `category` values (e.g. "Logos" as Doctrine vs as OriginalWord — these may legitimately be distinct).

### Phase 4: Schedule auto-merge as a Dagster asset

Make the rule-based auto-merge a recurring asset (e.g. weekly) rather than a one-shot manual run. Phase 2 metrics tracked over time confirm it doesn't degrade index quality.

## Alternatives Considered

1. **Continue manual scan-and-merge.** Doesn't scale to a 9-volume, ~7000-page corpus. Fragmentation accumulates faster than humans clear it.
2. **Re-extract everything with a stricter BAML prompt.** Possible quality improvement at substantial cost (re-running vision OCR over thousands of images). Uncertain whether the marginal improvement is worth the dollar cost.
3. **LLM-based pairwise entity merge** ("are these the same entity? yes/no"). Higher quality than rule-based at a per-pair cost; usable for the "manual review" tier in Phase 3 to accelerate human curation.
4. **Migrate to a managed entity-linking service** (e.g. Wikidata-linked NER). Theologically specific entities ("Simon Maccabeus", "Aben Ezra", "scapegoat") have weak coverage in general-purpose KBs; would be a downgrade.

## Consequences

### Positive
- Entity index becomes auditable (Phase 1), measurable (Phase 2), self-cleaning (Phases 3-4).
- Substring matching and BAML mapping operate on a cleaner foundation; downstream improvements ([ADR-0001](0001-enumeration-query-path.md), [ADR-0003](0003-cross-encoder-reranking.md)) become more reliable.
- The "Aben Ezra ranks top-50 for unrelated questions" failure mode becomes diagnosable rather than mysterious.

### Negative
- Phase 1 alone is substantial work (storage, snapshot tooling, audit script).
- Phase 2 needs the same kind of expert time as [ADR-0004](0004-reference-eval-set-and-ci-gates.md) — and probably the same expert.
- Phase 3 auto-merge can make mistakes; need an undo mechanism (deterministic UUIDs mean we cannot trivially "un-merge").

### Risks
- **Aggressive auto-merge collapses legitimate distinct entities.** Mitigation: rules are conservative; ambiguous cases stay in manual queue; spot-check merges weekly until trust builds.
- **The "manual review" queue becomes a backlog nobody addresses.** Mitigation: surface queue size in a dashboard; gate the Phase 4 schedule on queue depth.
- **Snapshotting to MinIO without versioning loses history.** Mitigation: enable bucket versioning at setup.

## Open Questions

- **Where do the snapshots live?** MinIO with versioning is technically cleanest but adds infrastructure assumption; git LFS in this repo is simpler but couples entity history to source history.
- **Who is the entity quality curator?** Same person as the [ADR-0004](0004-reference-eval-set-and-ci-gates.md) eval curator? If so, scope the time commitment realistically.
- **Should the substring matching in [`get_relevant_entities`](../../backend/gill_search.py) (shipped this session) be turned into a *first-class* feature rather than a substring hack?** A proper inverted-index on entity tokens (alongside BM25) would be cleaner. This is a Phase 5 if Phase 1-4 prove valuable.

## Dependencies

- Phase 2 quality measurement reuses infrastructure from [ADR-0004](0004-reference-eval-set-and-ci-gates.md).
- All four phases should be implemented before relying on entity-based features for enumeration ([ADR-0001](0001-enumeration-query-path.md)) — that ADR's effectiveness is bounded by entity-index quality.
