# ADR-0010: Entity Lookup Semantic Bridge

- **Status:** Accepted
- **Date:** 2026-07-07
- **Deciders:** Chris Nogradi

## Context

The launch-week post-mortem (see [ADR-0008](0008-three-zone-generation-and-voice-marked-ui.md)) surfaced three question shapes that produced credibility-harmful answers: `covenant_monocovenantal`, `universal_atonement`, and `exclusive_psalmody`. ADR-0008 Phase 1 shipped the generation-side fix (post-generation Zone-3 suppression, sweep, semantic judge, controlled A/B) and returned Phase 1 with zero credibility-harm across 15 fresh runs of the three flagship queries. But Phase 1's write-up recorded the retrieval-layer failure as still open: on `exclusive_psalmody` and `universal_atonement`, the bot was working from a manifest of entities that either didn't include the right anchor (Hallel, for psalmody) or included the right anchor buried in dozens of tangentially-relevant others (the "manifest flood" behind the 2026-06-21 universal_atonement bug).

The two-layer entity investigation (E-1 through E-6, 2026-07-07) went in with a prior that the extraction pipeline was concept-poor — that Layer 2 (ingestion) was returning proper nouns and skipping doctrinal concepts. The evidence killed the prior:

- E-1 survey of 1,699 extracted entity files: **12 categories, 52,955 mentions, 8,264 unique names**, with meaningful concept coverage — `Doctrine` 4.8%, `TypeOrSymbol` 3.9%, `Heresy` 0.5%, `OriginalWord` 3.3%.
- The known-relevant concept entities for the three flagship cases all exist:
  - `Hallel` **[TypeOrSymbol]** at `MATTHEW 26:30` with the description `"Passover hymn consisting of Psalms 113-118"` (E-1.2)
  - `covenant of grace` **[Doctrine]** at `GENESIS 9:9` and `MATTHEW 26:28`; `everlasting covenant` **[Doctrine]** at `GENESIS 17:7`
  - `Atonement`, `election`, `justification` **[Doctrine]** across multiple pages
- E-2: `pipeline/scripts/ingest.py:530-537` embeds `"<name> - <description>"` with `qwen3-embedding` and stores the vector on every `TheologicalEntity`. Vectors are already present in the collection.
- E-3: `backend/gill_search.py:get_relevant_entities` (pre-this-ADR) had two paths — BM25 over entity names, and `search_key LIKE *canonical_token*` substring — both purely lexical. Neither ever asked the vector that was sitting one API call away.

The diagnosis reversed: **Layer 2 is clean; the failure is Layer 1**, one function, one missing API call.

## E-6 diagnostic probe — what the vector actually knows

Before writing the fix, a diagnostic probe against the deployed `gya-test` cluster measured what `near_vector` on `TheologicalEntity` returns for the three in-domain flagship queries plus two out-of-domain queries. Top-K=100 with cosine distance printed at each rank, including per-rank distance-jump analysis to identify score cliffs. Raw output persisted in the session scratchpad as `e6_near_vector_probe.out` and `e6_bm25_baseline.out`.

### Distance distribution

| Regime | Top-1 distance range | Read |
|---|---|---|
| Sanity (direct name / gloss) | 0.16 – 0.21 | Vector cleanly identifies the target with a visible cliff at rank 1→2 (+0.05 to +0.07) |
| In-domain conceptual, target reachable | 0.18 – 0.29 | E.g. `"universal atonement in Christ"` → `atonement` at 0.181, rank 1 |
| In-domain conceptual, target unreachable | 0.25 (first hit) | E.g. `"exclusive psalmody"` → top-1 is `music` at 0.252, Hallel is past rank 100 |
| Out-of-domain with theological words | 0.34 (Esau pizza) | Vector correctly returns Esau-family entities; distance overlaps with in-domain tail |
| Out-of-domain technical | 0.50+ (for-loop-in-JavaScript) | Cleanly separable from every in-domain regime |

### The two structural findings

**One: qwen3-embedding represents the entities correctly.** Sanity probes for `"Hallel"`, `"Passover hymn consisting of Psalms 113-118"`, `"universal atonement"`, and `"covenant of grace"` all surface their targets at rank 1 or 2 with distances 0.16 – 0.22. The vector layer is not broken.

**Two: the vector does NOT know the phrase `exclusive psalmody` refers to the entity `Hallel`.** Both terms exist in the embedding space, but the edge between them (that the *Hallel* is the psalms sung at the Passover and thus is the historical Reformed anchor for the exclusive-psalmody debate) is *theological knowledge*, not lexical or embedding proximity. No lookup fix at Layer 1 reaches an association the vector space does not contain. Threshold-and-cap architecture cannot manufacture the association; only query-side expansion can.

### BM25 counterfactual (baseline)

For the same three in-domain queries, the pre-this-ADR lookup returned:

| Query | Target | Pre (BM25+substring) | Post (this ADR) |
|---|---|---|---|
| `"exclusive psalmody"` | Hallel | rank — of 1 (only hit `key of David`, matched `exclusive`); Hallel absent | rank — of ≤5; Hallel absent. **No regression, no fix.** |
| `"universal atonement in Christ"` | Atonement | rank 2 in a 69-entity flood; top-1 wrong (`satisfaction of Christ`) | rank 1 of ≤5, tightly-scoped Reformed-soteriology manifest. **Strict improvement.** |
| `"is the covenant of grace monocovenantal"` | covenant of grace | rank 11 in a 32-entity flood; top-1 wrong (`covenant of salt`) | rank ~5 of ≤5, covenant-adjacent manifest. **Strict improvement.** |

## Decision

Add a **confident vector tier** to `get_relevant_entities` and tighten the total manifest size, ordered by confidence and capped for BAML's `OptimizeSearchQuery` to work with a small, high-precision list.

### The three tiers, merged in confidence order

1. **Confident vector** — `near_vector` on the qwen3-embedding of the query, cosine distance ≤ `VECTOR_CONFIDENT_DIST_MAX = 0.25`, cap `VECTOR_TIER_CAP = 3`. Silent when the vector is not confident; does not attempt to fill this tier from the middle band.

2. **Substring canonical-key** — unchanged from ADR-0005 Phase 4. Bridges casing/punctuation variations (`scapegoat` → `scape-goat`) via `search_key LIKE *canonical_token*`.

3. **BM25 name-token** — `entities.query.bm25` capped at 3, kept as belt-and-suspenders for proper-noun hits the vector misses. (The 2026-05-17 Simons enumeration case shape.)

Dedup by lowercase-name across all three tiers. Total union capped at `MANIFEST_TOTAL_CAP = 5`.

### The constants are derived, not chosen

The three constants (`0.25`, `3`, `5`) are pinned against the E-6 distance distributions, not eyeballed:

- **`VECTOR_CONFIDENT_DIST_MAX = 0.25`.** Sanity + strong in-domain top-1s land 0.16 – 0.22. The observed vector-side false-positive that motivated the strict threshold (`exclusive psalmody` → `music` at 0.252) sits just above 0.25 — so 0.25 excludes it for free. Consequence: some in-domain queries with dilute phrasing (extra question-words, function words) land above 0.25 and get **no** vector boost. This is intentional: silence at Layer 1 is safer than admitting middle-band noise, and the query is not made worse than the pre-ADR state (which had no vector at all).

- **`VECTOR_TIER_CAP = 3`.** E-6 found the genuinely-adjacent hits are the first 1 – 3 with a visible score cliff after; anything past 3 in the confident tier is tail noise that would nudge retrieval toward the wrong chunk.

- **`MANIFEST_TOTAL_CAP = 5`.** Lower than the pre-fix `limit=50` to prevent the manifest flood behind the 2026-06-21 `universal_atonement` bug. BAML's `OptimizeSearchQuery` picks 3 entities from the manifest; a manifest of 5 gives it a real choice without room for a soft-positive to accidentally lead.

**Re-tune these only after re-running E-6 with fresh probe queries** (`scratchpad/e6_near_vector_probe.py` + `scratchpad/e6_bm25_baseline.py`). The distance distributions are what these numbers derive from; changing them without new distributions is a guess.

## What this ADR does NOT solve

**`exclusive_psalmody` remains an open failure mode after this ADR ships.** The vector alone cannot reach an association the qwen3-embedding space does not contain. E-6 established that the vector layer represents `Hallel` correctly (rank 2 on a direct `"Hallel"` probe at 0.175) and represents `"exclusive psalmody"` in a Reformed-worship neighborhood, but the two neighborhoods do not overlap — the semantic bridge is *theological*, not embedding-adjacent.

The fix that solves this is a separate work item at a different architectural layer: **query-side vocabulary expansion**. Concretely, either:

- Extend BAML's `OptimizeSearchQuery` to rewrite Reformed-doctrine-specific narrow vocabulary into descriptive phrasings before the entity manifest is fetched (e.g., `"exclusive psalmody"` → `"Psalms singing worship of God hymn Hallel"`), or
- Add a small domain-thesaurus pre-pass keyed on known Reformed-tradition colligations, tuned against the eval set.

This work is **out of scope for this ADR** and will be its own ADR when it lands. This ADR's contribution to `exclusive_psalmody` is *no regression* — the vector is silent (target above threshold), so the manifest is what BM25 and substring would have produced anyway. That is the honest posture: retrieval is a *strict improvement* on two of three flagship cases and a *no-op* on the third.

The `exclusive_psalmody` end-to-end failure remains covered upstream by ADR-0008 Phase 1 (the Zone-3 suppression sweep, semantic judge, and controlled A/B), which shipped zero credibility-harm across 15 runs of the flagship queries including psalmody by escaping to the informative-refusal shape rather than fabricating a synthesis. This ADR does not weaken that gate.

## Evidence — post-fix validation (E-6b)

Before the commit landed, an end-to-end verification harness (`evals/e6_entity_lookup_probe/e6b_post_fix_validation.py`) ran the exact tiered-merge logic against the deployed `gya-test` Weaviate cluster and printed the manifest each of the five probe queries would produce. Results (verbatim from `e6b_post_fix_validation.out`):

| Query | Target | In manifest? | Rank | Full manifest (post-cap) |
|---|---|---|---|---|
| `"universal atonement in Christ"` | Atonement | **YES** | **1** | `atonement`, `satisfaction of Christ`, `propitiation`, `day of atonement`, `Universal History` |
| `"is the covenant of grace monocovenantal"` | covenant of grace | **YES** | **1** | `covenant of grace`, `covenant of works`, `covenant of conservation`, `everlasting covenant`, `Angel of the covenant` |
| `"exclusive psalmody"` | Hallel | **no** | — | `key of David` (single entity, all tiers otherwise empty; Hallel remains unreachable per the ADR caveat) |
| `"how do I write a for loop in javascript"` | (OOD) | — | — | `Jewish writers`, `Arabic writers`, `Phœnician writers`, `eastern writers`, `Arabic writer` (bounded noise from `write` substring match) |
| `"did Esau eat pizza"` | (OOD) | — | — | `Esau`, `Jaalam`, `Reuel`, `Jeush` (correct Esau-family; 4 entities, under cap) |

**Interpretation:**
- **2 of 3 in-domain: target lands at manifest rank 1** — the strict improvement the ADR claims is verified evidence, not asserted.
- **1 of 3 in-domain: target absent** — `exclusive_psalmody` behaves exactly as the ADR's caveat describes. The confident-vector tier is empty (top-1 candidate `music` at distance 0.252, just outside the 0.25 threshold), substring is empty (`exclusive` and `psalmody` are not substrings of any entity's search_key), BM25 returns 1 lexical accident. Fixing psalmody is a separate work item.
- **OOD queries are bounded**: 5-entity manifest ceiling holds, and where the query contains a legitimate entity name (Esau) the manifest is correctly on-target.

The soft-positive the reviewer named as risk (`Universal History` in slot 5 of `universal_atonement`) does appear once — surfaced by the `universal` substring token. It is a single entity out of 5; the downstream BAML `OptimizeSearchQuery` picker chooses 3, and a 4-of-5 correctly-scoped manifest is a materially better input to that picker than the pre-fix 32-of-69 flood.

### E-6c — end-to-end retrieval verification

E-6b proves the manifest changed; the reviewer named the residual risk that a smaller manifest could shrink total boost signal and *reduce* retrieval quality even while improving precision. A second harness (`e6c_end_to_end_retrieval.py`) resolves that by calling `search_gill` directly with the pre-fix vs post-fix manifest, holding query and cluster constant, and reading the top-5 retrieved chunks. Results (raw in `e6c_end_to_end_retrieval.out`):

**`universal_atonement`** — post-fix is a strict improvement at the retrieval layer:

| Rank | PRE-fix retrieved | POST-fix retrieved |
|---|---|---|
| 1 | LUKE 23:31 (green tree metaphor) | **LEVITICUS 4:26** (burn fat on altar of burnt-offering) |
| 2 | NUMBERS 15:28 (priest atonement for ignorance) | NUMBERS 15:28 (same — overlap) |
| 3 | MARK 2:7 (who can forgive sins) | **LEVITICUS 23:28** (Day of Atonement statute) |
| 4 | MATTHEW 18:27 (unforgiving servant) | **NUMBERS 15:25** (Gill: "a type of Christ") |
| 5 | JOHN 3:16 (Gill's Calvinist "world" exposition) | NUMBERS 7:86 (golden spoons, tangential) |

Pre-fix retrieved 2/5 chunks directly on Old Testament atonement; the rest were broad Christ-adjacent verses surfaced by the `christ` substring token flood. Post-fix retrieved 4/5 chunks directly on OT atonement ceremony — the actual ground on which Gill exposits the doctrine.

**`covenant_monocovenantal`** — post-fix is same or slightly better, contrary to first appearances:

| Rank | PRE-fix retrieved | POST-fix retrieved |
|---|---|---|
| 1 | GENESIS 9:10 | GENESIS 9:10 (overlap) |
| 2 | GENESIS 9:9 | GENESIS 9:9 (overlap) |
| 3 | JOHN 6:47 | NUMBERS 25:12 |
| 4 | NUMBERS 25:12 | JOHN 6:47 (overlap) |
| 5 | MATTHEW 26:28 (blood of the new testament) | **GENESIS 9:12** ("this is the token of the covenant") |

The one distributional shift: post-fix loses MATTHEW 26:28 (covenant of grace affirmation) and picks up GENESIS 9:12. Reading Gill's text on both:

- GENESIS 9:9, 9:10, 9:12 all contain Gill *explicitly* disambiguating: `"Not the covenant of grace in Christ, but of the preservation of the creatures in common"`, `"this was not the covenant of grace, but of conservation"`.
- For the specific question "is Gill's covenant of grace monocovenantal?", three Gill-disambiguates-covenants chunks are more directly load-bearing than two + one covenant-of-grace affirmation. The distribution shift is a refocus toward Gill's antimonocovenantalism-in-action, not a loss.

The reviewer's failure mode (smaller manifest → weaker boost → worse retrieval) did not materialize. The boost concentrates on the right chunks rather than spreading across a flood.

## Consequences

**Positive:**
- `universal_atonement` and `covenant_monocovenantal` queries now surface their concept-anchor entity in a manifest of ≤5 tightly-scoped candidates instead of ≤50 tangentially-related ones.
- The manifest flood that caused the 2026-06-21 `universal_atonement` bug is structurally prevented — even if BAML's picker misfires, the maximum harm is a 5-entity boost, not a 50-entity boost.
- OOD queries (`for loop in javascript`) that formerly returned BM25 flood of Hebrew "I AM" tokens now return whatever the vector's confident tier says (empty at 0.25 threshold), plus BM25's top-3 — still noisy but bounded.
- The lookup now uses infrastructure that was already paid for: qwen3-embedding vectors on every entity, computed at ingest time (ADR-0005 lineage).

**Negative:**
- Callers relying on a larger manifest (e.g., ADR-0001's enumeration path, not yet shipped as code) must pass `limit=<N>` explicitly.
- The confident-tier silence for dilute-phrased in-domain queries (target above 0.25) means the vector adds no value there — the fix's benefit is uneven across query shapes.
- Adds one embedding call per user query — offset by the smaller manifest reducing BAML's downstream work.

**Neutral (worth naming):**
- `exclusive_psalmody` is not improved and not regressed. The commit message and any downstream write-up must not imply it is fixed.

## References

- [ADR-0005](0005-entity-index-audit-and-automated-deduplication.md) — the entity index and `search_key` canonical form that Tier 2 relies on.
- [ADR-0008](0008-three-zone-generation-and-voice-marked-ui.md) — the generation-side gate that keeps `exclusive_psalmody` credibility-safe until this ADR's sibling (query expansion) ships.
- Probe artifacts under [`evals/e6_entity_lookup_probe/`](../../evals/e6_entity_lookup_probe/):
  - `e6_near_vector_probe.{py,out}` + `e6_near_vector_results.json` — distance distributions and score-cliff analysis for K=100 across five queries.
  - `e6_bm25_baseline.{py,out}` + `e6_bm25_baseline_results.json` — counterfactual (what current lookup returns).
  - `e6b_post_fix_validation.{py,out}` + `e6b_post_fix_results.json` — the tiered-merge manifest each query produces after the fix.
  - `e6c_end_to_end_retrieval.{py,out}` + `e6c_end_to_end_results.json` — pre vs post retrieval, top-5 chunks per query, isolates the manifest's effect on `search_gill` output.
  - All re-runnable when the corpus expands or the qwen3 model changes.
