# ADR-0013: Two-Pass Entity Lookup + Refusal-Path Gill-Only Constraint

- **Status:** Accepted
- **Date:** 2026-07-12 (evening)
- **Deciders:** Chris Nogradi

## Context

The 2026-07-12 `exclusive psalmist` failure (see [ADR-0011 v3 amendment](0011-query-expansion-for-narrow-reformed-vocabulary.md#amendment-2026-07-12-evening-v3-vector-tier-reinstated--span-based-matching)) surfaced two distinct architectural gaps in the pipeline, both worth closing regardless of whether the thesaurus tier catches every query:

1. **Entity lookup runs before BAML expansion.** The pipeline currently calls `get_relevant_entities(lookup_query)` first, then feeds the manifest to BAML's `OptimizeSearchQuery`. When the raw query is a narrow concept ("exclusive psalmody") the entity index returns lexical false-positives (Aramaic Talmudic footnote entities, or a mis-disambiguated `Psalmist` biblical figure) rather than the semantically-adjacent concept entities Gill actually uses (`Hallel`, `Book of Psalms`). BAML's expansion — which is expressly good at producing 18th-century-vocabulary paraphrases of modern doctrinal terms — is only used for retrieval text, not entity discovery. The expansion capability is present but structurally under-used.

2. **Informative-refusal path pads with Scripture-verse quotations.** The 2026-07-12 UI answer for `"was gill an exclusive psalmist?"` returned three "nearest indexed material" citations — every one of them a Scripture verse embedded in Gill's commentary (John 2:17 quoting Psalm 69, Luke 20:42 quoting Psalm 110, Mark 12:36 quoting Psalm 110). The chunk-verification path validated these correctly (they *are* substrings of the retrieved chunks), so the amber "Unverified" chip fired only on the answer-shape-level, not the citation-level. The user sees Scripture verses presented as Gill's teaching-adjacent material for a question about Gill's doctrinal position. That is a *lentil trap* in a different form: fishing for tangential material to look helpful when the honest answer is "no Gill commentary on this subject."

## Decision

### Part A — Two-pass entity lookup with manifest union

In [`backend/main.py`](../../backend/main.py), after BAML's `OptimizeSearchQuery` returns successfully, invoke `get_relevant_entities` a second time on `optimized_query.expanded_search_terms`. Union the resulting manifest with BAML's picked entities (`mapped_entities`), deduplicated by lowercase-name, preserving first-appearance order so BAML's picks lead the boost text. Pass the union to `search_gill` as the `entities` argument.

```python
second_pass_entities = await search_engine.get_relevant_entities(query=search_text)
# Union: BAML's picks (highest signal) first, then semantic-recall additions.
# Dedup by lowercase-name; preserve first-appearance order.
_union = dedup(list(mapped_entities or []) + list(second_pass_entities or []))
mapped_entities = _union if _union else mapped_entities
```

The mechanism is *automatic bridging*: BAML expresses the modern concept in Gill's vocabulary (e.g., `"exclusive psalmody"` → `"psalm singing, musical praise, sacred music, liturgical song"`), and the second-pass entity lookup finds Hallel and Book of Psalms because their descriptions are embedding-adjacent to *that* vocabulary — no curation, no thesaurus entry, no manual mapping.

**Interaction with existing failure paths:**
- If BAML punts with `entities_given_none_returned`, we take the ADR-0012 poisoned-manifest suppression path and never reach the two-pass block. Correct.
- If BAML punts with `empty_expansion` or `no_query_terms_present`, we take the dedup-only fallback and never reach the two-pass block. Correct (BAML didn't produce a usable expansion; nothing to lookup).
- If BAML succeeds with a good expansion, two-pass adds semantic-recall entities to the boost.
- If BAML succeeds with a *wrong-direction* expansion (like the `"Psalter author, poet of David"` case), two-pass adds those wrongly-directed entities to the boost. This is a real risk; the mitigation is that the union preserves BAML's picks first and adds only new entities, so the boost is diluted with noise rather than replaced by it. The thesaurus fix (ADR-0011 v3) is what prevents mis-disambiguation upstream.

Stages metadata: `stages_capture["second_pass_entities"]` records what the second pass returned, alongside the existing `available_entities` and `baml_entities` fields, so a future incident can trace whether the second pass helped, hurt, or was silent.

### Part B — Gill-only constraint in the informative-refusal path

Extend the [`backend/bot.py`](../../backend/bot.py) informative-refusal instruction to explicitly forbid surfacing Scripture-verse-shape sentences as "nearest indexed material":

> The surfaced adjacent material must be Gill's own commentary — his doctrinal statements, interpretations, exposition, or historical explanation. It must NOT be a Scripture-verse quotation Gill is about to comment on. Sentences shaped like biblical text ("his disciples remembered that it was written, X", "And David himself saith in the book of Psalms, Y", "For it is written, Z") are Scripture-verse citations embedded in Gill's flow, not Gill's own commentary. Surfacing them as "the nearest indexed material" is a lentil trap in a different form: it presents Scripture as though it were Gill's teaching on the subject asked.
>
> If the only material available for a subject is Scripture-verse-shape sentences that happen to mention adjacent concepts, choose FLAT REFUSAL instead. The corpus has no Gill commentary on the subject; that is the honest report. Padding a refusal with Scripture verses is dishonest whether or not the citation resolves correctly.

The choice between informative-refusal and flat-refusal is now Gill-material-only: informative refusal *requires* Gill commentary to surface. Absence of Gill commentary routes to flat refusal.

## Consequences

**Positive:**
- Two-pass entity lookup makes BAML's expansion capability structurally load-bearing. Concept-heavy queries (paraphrases, doctrinal labels the thesaurus doesn't know about) get semantic entity recall without human curation.
- The `stages_capture["second_pass_entities"]` trace makes the two-pass contribution observable per query. If the second pass never adds anything useful in real traffic, the mechanism can be turned off cheaply; if it repeatedly adds the load-bearing entity, the value is measurable.
- Informative refusals now degrade honestly. A query about a subject Gill doesn't cover surfaces "no Gill commentary" rather than padded Scripture quotes.
- Combined with ADR-0011 v3 (span-based vector match) and ADR-0012 (poisoned-manifest suppression), the pipeline now has four automatic mechanisms — exact/fuzzy/vector thesaurus + BAML-fed semantic entity lookup + poisoned-manifest suppression + Gill-only refusal — each covering the others' failure modes with no curation step required.

**Negative:**
- Two-pass entity lookup adds one extra Weaviate call per successful-BAML query. Measured ~200–500ms in E-9.1 range; acceptable given the failure-mode reduction.
- If BAML expands in a wrong direction (like the failing case's `"Psalter author, poet of David"`), the second-pass lookup adds wrong-direction entities. The union structure minimizes the effect (BAML's picks lead) but does not eliminate it. Mitigation: ADR-0011 v3 span-based match reduces the frequency of wrong-direction BAML disambiguation by injecting anchor tokens for morphological variants.
- The refusal-path constraint may increase the frequency of flat refusals for subjects Gill only touches on tangentially. This is a UX shift but a truthful one — the pre-fix "here's a Scripture verse that mentions Psalms" was misleading, and the amber "Unverified" chip was already flagging it as such.

**Neutral (worth naming):**
- `search_gill` with the enlarged manifest still gets the same enhanced_query boost text, just with more entity names concatenated. BM25 scoring may shift for boundary cases.
- The refusal-path constraint is prompt-level, not code-level; a future prompt refactor must preserve the Gill-only rule or the fix regresses silently. The [ADR-0011 v3 amendment](0011-query-expansion-for-narrow-reformed-vocabulary.md) documents the same class of concern for the thesaurus.

## References

- [ADR-0008](0008-three-zone-generation-and-voice-marked-ui.md) — three-zone taxonomy and the informative-refusal path this ADR constrains.
- [ADR-0011](0011-query-expansion-for-narrow-reformed-vocabulary.md) — thesaurus + v3 vector-tier fix; complementary to Part A above.
- [ADR-0012](0012-poisoned-manifest-fallback-suppression.md) — poisoned-manifest suppression; interacts with Part A's two-pass path.
- The 2026-07-12 `exclusive psalmist` incident trace: Langfuse trace ID `2c3999a51652cc7feb10fe7fc5b10927`.
