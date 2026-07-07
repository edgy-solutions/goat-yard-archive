# ADR-0011: Query Expansion for Narrow Reformed Vocabulary

- **Status:** Accepted
- **Date:** 2026-07-07
- **Deciders:** Chris Nogradi

## Context

[ADR-0010](0010-entity-lookup-semantic-bridge.md) closed the entity-lookup semantic bridge for `covenant_monocovenantal` and `universal_atonement` and named `exclusive_psalmody` as an unsolved case at a different architectural layer. E-6 established that qwen3-embedding represents both `"exclusive psalmody"` and `"Hallel"` correctly *in isolation* — a `"Hallel"` sanity probe returned the entity at rank 2 dist 0.175; the `"Hallel"` anchor exists at MATTHEW 26:30 with the description `"Passover hymn consisting of Psalms 113-118"` — but did NOT connect the two neighborhoods. The theological association ("the Hallel *is* the psalms sung at the Passover, and it's the historical Reformed anchor for the exclusive-psalmody debate") lives in the reader's head, not in the embedding space. ADR-0010's tier-and-threshold cannot manufacture an association the vector does not carry.

ADR-0010 explicitly deferred this class of failure to a separate work item, naming it as a *query-side vocabulary-bridge problem* and listing two plausible shapes: extend BAML's `OptimizeSearchQuery` to rewrite narrow Reformed terms, or add a small domain thesaurus. E-7 (2026-07-07) investigated both options empirically before choosing.

## E-7 investigation — what actually bridges the gap

### E-7.1 — expansion coverage probe

Tested six expansion shapes against the `exclusive_psalmody` failure. Cosine distances measured against the deployed `gya-test` cluster (raw output: `evals/e7_query_expansion_probe/e7_1_expansion_coverage.out`):

| Expansion shape | Query text | Hallel rank | Cosine distance | Confident tier (≤ 0.25)? |
|---|---|---|---|---|
| baseline | `"exclusive psalmody"` | >100 | — | no |
| name-inject | `"exclusive psalmody Hallel"` | 1 | 0.190 | **YES** |
| descriptor-inject | `"exclusive psalmody Psalms 113-118 Passover hymn"` | 1 | 0.210 | **YES** |
| domain-vocab | `"exclusive psalmody psalms singing worship hymn"` | 24 | 0.373 | no |
| rephrase-modern | `"Are Psalms the only songs a church should sing?"` | 59 | 0.496 | no |
| rephrase-passover-focus | `"singing Psalms at Passover Hallel"` | **1** | **0.143** | **YES** |
| rephrase-worship-focus | `"singing psalms in Christian worship"` | 61 | 0.392 | no |

**Load-bearing lesson.** Adding *broad worship vocabulary* (singing, worship, hymn, praise) does NOT bridge the concept-anchor gap — it just enriches the general Reformed-worship neighborhood without pointing at the specific entity. What works is either the *anchor entity name itself* (`Hallel`) or *descriptor tokens that appear in the entity's stored gloss* (`Psalms 113-118`, `Passover hymn`). This is a strong constraint: expansion must contain vocabulary that is embedding-adjacent to the anchor entity's own vector, which was computed from `"<name> - <description>"` at ingest time (see `pipeline/scripts/ingest.py:530-537`).

### E-7.2 — narrow-term inventory

Probed nine additional Reformed-tradition narrow terms to characterize the failure shape (same output):

| Narrow query | Candidate anchor | Vector rank | Distance | Read |
|---|---|---|---|---|
| `sabbatarian` | `Sabbath` | 1 | 0.219 | **Reachable** — no expansion needed |
| `covenant of redemption` | `covenant engagements` | 1 | 0.207 | **Reachable** — no expansion needed |
| `federal headship` | `federal head` | 1 | 0.252 | Marginal — 0.002 above threshold |
| `effectual calling` | `internal call` | 1 | 0.258 | Marginal — sits just above threshold |
| `exclusive psalmody` | `Hallel` | >100 | — | **Needs expansion** |
| `pactum salutis` | `covenant engagements` | 70 | 0.309 | **Needs expansion** (Latin ↔ English) |
| `monergism` | `electing grace` | >100 | — | **Needs expansion** (modern label ↔ Reformed idiom) |
| `regulative principle` | (no clean anchor) | >100 | — | **Needs expansion** (concept ↔ Puritan phrasing) |
| `imputation` | `justifying righteousness of Christ` | >100 | — | **Needs expansion** (ambiguous term — of sin or of righteousness) |

The failure shape is **stable and enumerable** across three categories:
- **Latin ↔ English pairs** (`pactum salutis` ↔ `covenant of redemption`).
- **Modern-label ↔ Reformed-idiom** (`monergism` ↔ `electing grace`; `regulative principle` ↔ `ordinances of the Gospel`).
- **Concept ↔ anchor-entity** (`exclusive psalmody` ↔ `Hallel`).

Reformed tradition has a finite, relatively stable narrow vocabulary. This shape argues against an LLM-driven generalizer (BAML `ExpandNarrowVocabulary`) as the first move: the mappings are deterministic, small in number, verifiable per-entry against the E-7 probes, and grow slowly.

## Decision

Ship a **deterministic thesaurus** at [`backend/query_expansion.py`](../../backend/query_expansion.py) applied to the user's raw query **before** `get_relevant_entities` runs. The expanded query is used **only** for entity lookup; BAML's `OptimizeSearchQuery` still sees the raw query so it does not over-emphasize the appended anchor tokens.

### Thesaurus structure

Each entry maps a narrow term (matched case-insensitive with `\b` word boundaries) to a list of anchor tokens plus a justification pointing to the specific E-7 probe evidence:

```python
THEOLOGICAL_THESAURUS = {
    "exclusive psalmody": {
        "anchor_tokens": ["Hallel", "Passover", "Psalms 113 118"],
        "justification": (
            "'singing Psalms at Passover Hallel' -> Hallel rank 1 dist 0.143. "
            "Hallel is the Passover hymn (Ps 113-118) at MATTHEW 26:30..."
        ),
    },
    # ... four more entries: pactum salutis, monergism, regulative principle, imputation.
}
```

### Pipeline integration

Single point of injection in `backend/main.py`, immediately before the entity-lookup call:

```python
lookup_query, expansion_matches = expand_query(req.query)
available_entity_names = await search_engine.get_relevant_entities(query=lookup_query)
```

`expansion_matches` is threaded into:
- `stages_capture` for the determinism/replay harness.
- Langfuse trace metadata under `query_expansion_matches`, so the daily Zone-3 sampler (ADR-0008 Phase 1 Step 5b) can see which traces had expansion applied when auditing production.

### Design rationale — thesaurus over LLM generalizer

| Option | Chosen | Why |
|---|---|---|
| Deterministic thesaurus (chosen) | ✓ | Reformed narrow vocabulary is finite (~20 terms); each entry is testable per E-7.1 shape; deterministic at query time; easy to add or remove; transparent under review |
| Extend BAML `OptimizeSearchQuery` | ✗ (deferred) | LLM overkill for enumerable mappings; brittle to prompt drift; harder to test regressions; may over-expand into hallucinated anchors |
| Hybrid (thesaurus + LLM fallback for unknown terms) | ✗ (deferred) | Adds a second failure mode to debug; wait for real evidence that the thesaurus fails to generalize |

If a future narrow-vocabulary query surfaces at eval time and does not fit the thesaurus, the correct response is (a) run E-7.1 to identify the anchor, (b) add a thesaurus entry with justification, (c) commit — same discovery loop that produced the initial five entries.

## Evidence — E-7.5 end-to-end validation

Full run in `evals/e7_query_expansion_probe/e7_5_end_to_end_validation.out`. Phase A tests the manifest change; Phase B reads the actual retrieved chunk text; Phase C is a negative control that non-narrow queries pass through unchanged.

### `exclusive_psalmody` — fully fixed at the retrieval layer

**Phase A — manifest:**
- Raw query: `"exclusive psalmody"` → manifest `[key of David]` (one lexical accident, no Hallel).
- Expanded query: `"exclusive psalmody Hallel Passover Psalms 113 118"` → manifest `[הַלֵּל טָעוּן, Hallel, Lord our God, passover, passover-lamb]`.
- **Hallel is now in the manifest at rank 2**, the Hebrew-form `הַלֵּל טָעוּן` at rank 1. All five entries are Passover/Hallel-adjacent.

**Phase B — retrieval (top-1 chunk, verbatim from `search_gill`):**
- Pre-fix top-1: `[LUKE 11:52]` score 0.650 — Gill on "woe to lawyers." Off-topic.
- **Post-fix top-1: `[MATTHEW 26:30]` score 0.857** — Gill: *"And when they had sung an hymn, &c.] The Hallel, which the Jews were obliged to sing on the night of the passover; for the passover, they say, was הַלֵּל טָעוּן, bound to an [hymn]..."*

The single load-bearing anchor chunk for the exclusive-psalmody debate — absent from every pre-fix retrieval since launch — now lands at rank 1 with a 0.207 score jump above the pre-fix top-1. The bot has authentic ground to answer from.

### `pactum_salutis` — partial fix, complementary to Pauline ingestion

**Phase A — manifest:**
- Raw query: `"what does Gill say about the pactum salutis"` → manifest `[Megilla, Megillah, Chaldee paraphrases, איזהו מה, created angel]` — Latin term matched Aramaic/Talmudic false-positives via BM25 on adjacent tokens.
- Expanded query: `"...pactum salutis covenant of redemption covenant engagements"` → manifest `[covenant of grace, covenant of works, covenant of conservation, everlasting covenant, Angel of the covenant]` — tightly covenant-adjacent.

**Phase B — retrieval:**
- Pre-fix top-5: NUMBERS 20:6, MATTHEW 9:13, JOHN 1:41, MATTHEW 6:31, MARK 4:30. All off-topic.
- Post-fix top-5: GENESIS 9:10 (covenant of conservation), NUMBERS 25:12 (Phinehas covenant), GENESIS 9:11, LUKE 1:72 (mercy promised to fathers), JOHN 6:47.

Post-fix retrieval is *directionally right* — covenant material Gill uses to disambiguate — but Gill's fullest pactum-salutis exposition lives in EPHESIANS 1, TITUS 1:2, and ROMANS 8, none of which are in the currently-ingested volumes (only vol1 Gen–Num and vol7 Matt–John are indexed). **Full closure of `pactum_salutis` requires the Pauline volume ingestion; expansion alone moves the retrieval from off-topic to covenant-adjacent but cannot conjure chunks that don't exist yet in the index.**

### Negative controls — no regression on non-narrow queries

- `"is the covenant of grace monocovenantal"` → no thesaurus match, expansion is a pass-through, manifest identical to ADR-0010's post-fix.
- `"universal atonement in Christ"` → same: no match, no expansion, no regression.

## Interaction with volume ingestion (load-bearing)

The E-7.5 `pactum_salutis` result surfaces the reviewer's 2026-07-07 sequencing note explicitly: **query expansion and volume ingestion close the psalmody-and-adjacent-narrow-vocabulary cluster together, not either alone**. Ingesting Psalms and Pauline volumes into a system that still cannot bridge topical Reformed queries would look like "the ingestion didn't help" — when the actual blocker for topical queries would still be the vocabulary gap this ADR closes. Ingesting the new volumes AFTER this ADR ships means:

1. `exclusive_psalmody` (already closed on vol7 material — MATT 26:30 IS ingested) benefits directly from Psalms material for verse-anchored psalmody queries (`"Psalm 95"`, `"singing Psalm 100"`) which will now hit rich Gill exposition.
2. `pactum_salutis` closes fully when Ephesians / Titus / Romans-8 chunks land — the expansion is already in place and the manifest is covenant-adjacent, so the retrieval will reach those chunks the moment they exist.
3. Verse-anchored queries against the new material work regardless of the expansion (those go via the direct-verse-lookup path in `search_gill`).

Sequence expansion (this ADR, small, query-side) → then Psalms/Pauline ingestion → and the two together close the narrow-vocabulary cluster the way `covenant_monocovenantal` and `universal_atonement` were closed by ADR-0010. Neither of the two closes the cluster alone.

## What this ADR does NOT solve

- **Novel narrow-vocabulary terms not yet in the thesaurus.** The mitigation is the discovery loop above (E-7.1 probe → add entry → commit). This is by design: the deterministic thesaurus is a set of *verified* mappings, not a generalizer.
- **Marginal-distance cases** (`federal headship` at 0.252, `effectual calling` at 0.258). These sit just above ADR-0010's confident-tier threshold and would benefit from either loosening the threshold to 0.30 (which admits the psalmody-side false-positive back) or an entry-per-marginal-case in the thesaurus. Neither is urgent; deferred.
- **`pactum_salutis` full closure**. Retrieval is directionally right but ultimate anchor chunks require Pauline ingestion. Explicitly noted above; not this ADR's job to conjure them.

## Consequences

**Positive:**
- `exclusive_psalmody` is fixed at the retrieval layer as of this commit — the flagship launch-week failure closes on the current corpus.
- Expansion is fully deterministic; failure modes are debuggable (grep the thesaurus, run E-7.5 on a specific term).
- Langfuse trace metadata carries `query_expansion_matches`, so the daily Zone-3 sampler can distinguish expansion-affected traces if a future issue surfaces.
- Ingestion of Psalms/Pauline volumes is now genuinely unblocked in the way the reviewer flagged — the vocabulary bridge is in place before the new material arrives.

**Negative:**
- Adds a tiny latency to every query (a Python regex sweep — measured negligible in E-7.5 runs).
- The thesaurus requires manual curation as new narrow-vocabulary queries surface. Mitigation: the E-7.1 probe is the discovery tool and is committed.

**Neutral (worth naming):**
- The `covenant engagements` entity for `pactum_salutis` did not land in the top-5 manifest despite being an explicit anchor token, because the cap-5 tier ordering pushed it out in favor of vector/BM25-adjacent `covenant of X` entities. Retrieval was still improved (Genesis 9 covenant chunks vs Talmudic drift). A follow-up work item is *priority-anchor insertion* — a get_relevant_entities parameter that forces thesaurus-derived anchor entities to the top of the manifest bypassing tier ordering. Not urgent for this ADR's target cases.

## References

- [ADR-0010](0010-entity-lookup-semantic-bridge.md) — the retrieval-layer fix this ADR complements. Explicitly named the psalmody case as out-of-scope and pointed here.
- [ADR-0008](0008-three-zone-generation-and-voice-marked-ui.md) — the generation-side gate that kept `exclusive_psalmody` credibility-safe (informative refusals, no Zone-3 fabrication) between launch and this fix.
- Probes and evidence under [`evals/e7_query_expansion_probe/`](../../evals/e7_query_expansion_probe/):
  - `e7_1_expansion_coverage.{py,out}` + `e7_1_expansion_coverage_results.json` — six psalmody expansion shapes + nine narrow-term inventory probes.
  - `e7_5_end_to_end_validation.{py,out}` + `e7_5_end_to_end_results.json` — manifest + retrieval + negative-control validation.
- Sibling work items (sequenced): Psalms/Pauline volume ingestion (unblocked by this ADR); optional priority-anchor insertion in `get_relevant_entities`.
