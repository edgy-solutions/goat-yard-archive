# ADR-0012: Poisoned-Manifest Fallback Suppression

- **Status:** Accepted
- **Date:** 2026-07-12
- **Deciders:** Chris Nogradi

## Context

[ADR-0008](0008-three-zone-generation-and-voice-marked-ui.md) Step 2b introduced a structural sentinel that classifies BAML's `OptimizeSearchQuery` output as a punt when any of three signals fires:

- `empty_expansion` — BAML returned no query rewrite text.
- `no_query_terms_present` — BAML rewrote but dropped every content token from the user's query.
- `entities_given_none_returned` — BAML received a manifest of ≥1 candidate entities and returned **zero** in its output.

When the sentinel trips, control falls through to ADR-0008 Step 2d — a "dedup-only" fallback that uses the raw user query as the retrieval text and passes the deduplicated `available_entity_names` (the manifest from `get_relevant_entities`) as the entity boost to `search_gill`.

The 2026-07-12 [ADR-0011 v2](0011-query-expansion-for-narrow-reformed-vocabulary.md) investigation exposed a cascading failure that the sentinel *detects* but structurally *cannot rescue* under this fallback shape:

1. A narrow-vocabulary query outside the thesaurus (typo `exlusive psalmody`; unknown term `means of grace`) misses the ADR-0011 expansion tiers.
2. `get_relevant_entities` returns a manifest of BM25-adjacent noise — for `exlusive psalmody`, it surfaced `[Ben Zeta, Judea, Megilla, Megillah, world to come]` (Aramaic/Talmudic false-positives from footnotes); for `means of grace`, `[covenant of grace, dew of heaven, divine grace, election of grace, sovereign grace]` (grace-substring-matched but conceptually adjacent-not-same).
3. BAML's picker examines the manifest, decides *no entity in it fits the query*, and returns an empty `official_entities` list. The sentinel correctly classifies this as `entities_given_none_returned`.
4. The dedup-only fallback then **re-injects those same rejected entities as the entity boost**. `search_gill` builds its BM25 boost text as `raw_query + " " + " ".join(entities)` and Weaviate's `entities^3` field boost triples the score contribution from chunks carrying those entities.
5. Retrieval lands on chunks that match the *rejected* entities but not the user's actual query. The 2026-07-12 UI incident: `exlusive psalmody` → JOHN 3:25 (a chunk about the *Jewish baptism dispute*, matching `Megilla` and Jewish PeopleGroup entities). `means of grace` → GENESIS 6:8 (Noah found grace, matching `covenant of grace` / `divine grace`).

The trace signal was already there — `stages_capture.baml_punt_reasons: ['entities_given_none_returned']` — but the fallback branched on the exception rather than the *reason*, so the load-bearing signal about manifest quality was recorded and then ignored.

The reviewer named the load-bearing property: **"BAML rejecting the whole manifest is manifest-quality evidence, and boosting on rejected entities is worse than not boosting at all."** ADR-0011 v2 fixes the typo case at the thesaurus layer (five curated terms). This ADR fixes the class — every narrow-vocabulary term that ever droughts the manifest, most of which will never be in the thesaurus.

## Decision

Dispatch the fallback in [`backend/main.py`](../../backend/main.py) on the specific punt reason recorded in `_punt_reasons`. Track `_punt_reasons` in a scope visible to the `except` block so the fallback can read it.

- **Case A — `entities_given_none_returned` is present**: BAML looked at the manifest and rejected every entry. Reusing those entries as the entity boost injects known-wrong signal into retrieval. **Suppress the entity boost entirely** by setting `mapped_entities = []`. `search_gill` will run pure hybrid (BM25 + qwen3 vector) with no entity anchor. Log the fallback kind as `poisoned_manifest_suppressed` for observability.

- **Case B — other punt reasons or a raw BAML exception**: The manifest itself may still be useful; only the query rewrite failed. Keep the ADR-0008 Step 2d dedup-only fallback unchanged. Log the fallback kind as `dedup_only`.

The two branches are load-bearing distinct: dropping the boost when BAML rejected the manifest converts a *confidently wrong* answer into an *honest weak* answer. Keeping the boost when BAML failed for other reasons preserves the entity signal for cases where it's still valid.

## Evidence — E-9.1 boost-suppression verification

The verification harness (`evals/e9_poisoned_manifest_probe/e9_1_boost_suppression.py`) calls `search_gill` directly with the poisoned manifest vs an empty entity list, holding query and cluster constant, for two drought-shaped queries collected against the deployed pod running commit `f019969` (pre-Fix-2).

### Case A: `"means of grace"` — chunk quality improves

Poisoned manifest (BAML rejected): `[covenant of grace, dew of heaven, divine grace, election of grace, sovereign grace]`.

| Rank | BEFORE Fix 2 (poisoned boost) | AFTER Fix 2 (no boost) |
|---|---|---|
| 1 | MARK 4:7 score **0.712** | MARK 4:7 score **0.731** |
| 2 | GENESIS 6:8 (Noah found grace) | JOHN 3:20 |
| 3 | MATTHEW 25:9 | MATTHEW 13:12 |
| 4 | MATTHEW 20:23 | MATTHEW 25:9 |
| 5 | MATTHEW 13:12 | MARK 8:23 |

MARK 4:7 is Gill's actual `"was not the means of grace"` commentary — retrieved by both paths, but its score *improves* after the fix because it no longer competes with the poisoned boost. GENESIS 6:8 (Noah-found-grace, an off-topic hit surfaced only by the `covenant of grace` / `divine grace` entity boost) is dropped.

### Case B: `"pxlusive psalmoly"` — total retrieval shift, no false anchor

Deliberate edit-distance-≥2 typo; guaranteed to drought both the exact and fuzzy thesaurus tiers. Poisoned manifest (the `get_relevant_entities` hardcoded fallback): `[Jesus Christ, Apostle Paul, Old Testament saints]`.

| Rank | BEFORE Fix 2 | AFTER Fix 2 |
|---|---|---|
| 1 | MATTHEW 24:12 score 0.650 | MARK 10 score 0.350 |
| 2 | LUKE 19:16 score 0.593 | EXODUS 15:11 score 0.248 |
| 3 | MATTHEW 26:44 score 0.560 | MATTHEW 21:9 score 0.188 |
| 4 | MARK 16:17 score 0.543 | MATTHEW 10:27 score 0.170 |
| 5 | MATTHEW 24:10 score 0.515 | EXODUS 15:1 score 0.167 |

**Zero overlap.** Pre-fix retrieval is confidently on Jesus/Paul apocalyptic material driven by the boost. Post-fix retrieval is much lower-scored (top-1 = 0.35 vs 0.65) — a truthful signal that retrieval is uncertain — AND actually surfaces psalmody-adjacent chunks the poisoned boost had been overriding: **EXODUS 15:1** is the Song of Moses, the first song recorded in Scripture; **MATTHEW 21:9** contains the Hosanna Psalm-118:25 material.

The pattern is: with the poisoned boost, retrieval was *confidently wrong*. Without it, retrieval is *honestly weak* — and the honestly weak result is closer to the concept the user actually asked about.

## What this ADR does NOT solve

- **Downstream generation is still LLM-driven.** A weak retrieval passed to the bot may still produce an answer. The bot's DSPy pipeline includes ADR-0006 verbatim-quote verification, which forces citations to substring-match the retrieved chunk, so a weak retrieval cannot produce a confidently-wrong Gill quote — but it can still produce a soft refusal that surfaces the low-confidence chunks. That's the honest-degradation behavior we want.
- **Terms in the thesaurus still cliff on non-fuzzy-catchable shapes** (inflections, paraphrases). The ADR-0011 v2 near-miss log covers those cases for observability; grow the thesaurus from the log.
- **The `no_query_terms_present` punt** does not trigger boost suppression under this fix. If BAML dropped every user token but the manifest is fine, we still boost. If empirical evidence later shows the manifest is *also* poisoned in these cases, extend the dispatch to include this reason.

## Consequences

**Positive:**
- Every drought-shaped narrow-vocabulary query — five thesaurus terms today, unbounded set at steady state — now degrades honestly instead of injecting a false anchor.
- The BAML sentinel signal (`baml_punt_reasons`) becomes load-bearing rather than merely diagnostic. Traces now record which fallback path fired (`stages_capture.baml_fallback`), so a future incident is one Langfuse query away from the correct diagnosis.
- MARK 4:7's score *improves* on `means of grace` post-fix — real signal is no longer competing with false signal.

**Negative:**
- Weak retrievals produce weak answers rather than confident-looking ones. To an untrained reader, `"I don't have this in the corpus"` may feel like a regression from a `"here's a broadly-adjacent quote"` fake. It isn't — the fake was wrong — but the UX shift is real. The frontend's "Verified Source" chip semantics still hold: when the bot cites a chunk, it's still verified against the corpus.
- Doesn't help queries where the manifest happens to be topically correct but BAML disengages for other reasons; those still take the dedup-only path.

**Neutral (worth naming):**
- `search_gill` with `entities=[]` still gets the *user's raw query* as BM25 input and the query embedding for the vector side. Retrieval is not disabled; only the entity-boost lever is neutralized.
- This ADR's fix is intentionally at the fallback dispatch, not at `get_relevant_entities` itself. The lookup can still be improved (priority-anchor insertion, less-noisy substring match), but those are separate work items with different tradeoffs.

## References

- [ADR-0008](0008-three-zone-generation-and-voice-marked-ui.md) — sentinel + Step 2d fallback that this ADR modifies.
- [ADR-0011 v2](0011-query-expansion-for-narrow-reformed-vocabulary.md) — thesaurus fuzzy tier + near-miss log; complementary but scoped to five curated terms.
- Probes and evidence:
  - `evals/e9_poisoned_manifest_probe/e9_1_boost_suppression.{py,out}` + `e9_1_boost_suppression_results.json`
