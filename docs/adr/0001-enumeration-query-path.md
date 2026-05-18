# ADR-0001: Separate Query Path for Enumeration Questions

- **Status:** Proposed
- **Date:** 2026-05-17
- **Deciders:** Chris Nogradi

## Context

The current `/api/search` pipeline answers every question via a single path:

1. BAML expands the user query into 18th-century synonyms + maps to graph entities.
2. `search_gill` runs a hybrid (BM25 + dense vector) retrieval over the chunk index, returns top-K sentences (currently 12).
3. DSPy synthesizes an answer grounded in those K chunks.

This pipeline is well-suited to "what does Gill say about X" questions, where the answer is a synthesis of the most relevant passages. It is **structurally wrong** for *enumeration* questions — "how many Xs were there", "list all Xs", "what are the names of the Xs" — because those questions require the *complete set* of X, not the K most-frequently-mentioned sentences containing X.

### Concrete failure

Test query (log.md, 2026-05-17): *"how many simons were there?"*

After upstream improvements (substring matching in [`get_relevant_entities`](../../backend/gill_search.py)), the BAML entity manifest correctly included **ten** distinct Simons:

```
Simon, Simon the Pharisee, Simon the Canaanite, Simon the Cyrenian,
Simon the leper, Simon Magus, Simon, son of Giora, Simon ben Camhith,
Simon Bar-Jona, Simon Maccabeus
```

But hybrid retrieval returned the top-12 *sentences*, and those sentences cluster around whichever Simons Gill writes about most prolifically (Peter, the Pharisee). The model correctly cited **four** distinct Simons — the only ones it had grounded chunks for. The answer was honest but incomplete; the corpus knew about ten.

No tweak to top-K, alpha, or prompt softening can fix this. Top-K=100 would still give a chunk distribution skewed to the most-discussed Simons; the rare ones (Maccabeus, ben Camhith) would never accumulate enough chunks to be enumerable. **The retrieval primitive is wrong for the question.**

## Decision

Add a second query path specifically for enumeration questions. Detect intent on the user query; when triggered, bypass top-K hybrid retrieval and instead use the **entity index** as the answer set, with per-entity chunk fetches purely for grounding citations.

### Pipeline (enumeration mode)

1. **Intent detection** — regex on the user query for enumeration markers:
   - `^(how many|list|name|enumerate)\b`
   - `^(who are|what are) the\b`
   - `^all the\b`
   - false-positive guard: questions about quantity-as-property ("how many years did X reign") fall through to the standard path.
2. **Entity resolution** — reuse `get_relevant_entities` (already does substring + BM25). Returns the canonical set.
3. **Per-entity grounding fetch** — for each entity in the set, fetch 1 representative chunk where the entity is linked. Aggregate into a flat structured context block:
   ```
   Simon Peter — [JOHN_1_42_S03] "...Cephas, which is, by interpretation, a stone..."
   Simon the Canaanite — [MATTHEW_10_4_S01] "...also called Zelotes..."
   Simon Magus — [ACTS_8_9_S00] "..."
   ...
   ```
4. **Enumeration DSPy signature** — new signature whose contract is *"given this list of N entities with one representative excerpt each, produce an enumerated answer that names each one with its citation."* Distinct from the existing synthesis signature.
5. **Answer formatting** — bullet list or numbered list; one citation per entity.

### What this is NOT

- **Not** a replacement for the existing RAG path. Most questions still go through the original pipeline.
- **Not** a graph-traversal feature. Pure entity-index lookup; no relationship walks.
- **Not** an unconstrained enumeration — bounded by what the entity index contains. The model still cannot enumerate Simons the corpus has never indexed.

## Consequences

### Positive
- Correct answers for the class of questions that top-K RAG structurally cannot answer.
- Each entity gets a citation, so the answer remains grounded and verifiable.
- Reuses the existing substring-matched entity lookup — no new index needed.

### Negative
- New code path doubles the surface area of `/api/search`. Intent detection becomes a load-bearing classifier.
- Per-entity grounding fetch is N queries (one per entity). For a 10-entity result this is ~10 Weaviate calls; needs to be parallelized.
- Near-duplicates in the entity index (e.g. "Simon Peter" and "Simon Bar-Jona" naming the same person) will be enumerated as separate items unless we add a canonicalization pass — likely a follow-up.
- Intent detector will have false negatives ("Who all did Jesus heal?" — doesn't match the regex) and false positives ("How many days did the flood last?" — matches but is not enumeration). Acceptable for v1; refine based on usage.

### Risks
- The enumeration set's quality is bounded by the entity-index quality. If the index is missing entries (e.g. Simon of Cyrene not present as a distinct entity), the answer will silently undercount. Worth auditing the entity index coverage before relying on this for "how many" answers in production.
- If the model conflates entity-set enumeration with chunk-grounded synthesis, it may hallucinate facts about entities it has no chunks for. The DSPy signature must constrain output to "list these entities; do not invent properties not present in the per-entity excerpt."

## Alternatives Considered

1. **Increase top-K and hope coverage improves.** Rejected — top-K scales the volume of the most-relevant chunks, not the diversity of entities covered. Empirically, the failing case had the right entities in the manifest; the retrieval just didn't surface them as sentences.
2. **Re-rank by entity coverage.** Take top-50 chunks, re-rank to maximize unique entity coverage. Possible but adds complexity to the existing path and degrades quality for non-enumeration questions; cleaner to fork the path.
3. **Let the LLM do the enumeration with a wider entity manifest.** I.e. just pass the substring-matched entity list directly to DSPy with instructions to enumerate. Rejected — produces ungrounded enumeration (no per-entity citation), and the answer would essentially be a paraphrase of the manifest with the model's prior, defeating the citation-required design.

## Implementation Sketch (~50 LOC)

```python
# backend/main.py — at top of /api/search, before BAML
ENUM_PATTERNS = [
    r"^how many\b",
    r"^list\b",
    r"^(who|what) are the\b",
    r"^name (the|all)\b",
]
is_enum = any(re.match(p, req.query.strip().lower()) for p in ENUM_PATTERNS)

if is_enum:
    entities = await search_engine.get_relevant_entities(req.query, limit=50)
    contexts = await search_engine.fetch_entity_excerpts(entities)  # new method
    pred = await asyncio.to_thread(enum_bot, question=req.query, entity_contexts=contexts)
    return SearchResponse(answer=pred.answer, citations=pred.citations, evidence=...)

# else: existing pipeline unchanged
```

```python
# backend/gill_search.py — new method
async def fetch_entity_excerpts(self, entity_names: List[str], per_entity: int = 1):
    """For each entity, fetch its top-N representative chunks for grounding."""
    # Parallel fanout; per-entity filter on mentions_entity cross-ref
    ...
```

```python
# backend/bot.py — new signature
class EnumerationSignature(dspy.Signature):
    """List each entity with its representative excerpt's Sentence ID.
    Do not invent properties; only state what each excerpt explicitly says.
    """
    entity_contexts = dspy.InputField(...)
    question = dspy.InputField(...)
    answer = dspy.OutputField(...)
    citations = dspy.OutputField(...)
```

## Open Questions

- Should near-duplicate entities be merged (e.g. "Simon Peter" + "Simon Bar-Jona" + "Cephas" → one)? Likely yes for human-friendly answers, but requires an alias table or LLM dedup step.
- What's the right `per_entity` chunk count? `1` is minimal; `2-3` would give the model more to work with at the cost of context length and latency.
- Should the existing standard path also use the enumeration entity manifest as a hint when intent is ambiguous?
- Telemetry: tag enumeration-path traces distinctly in Langfuse so we can measure pass rate separately from the synthesis path.
