# ADR-0003: Query-Time Cross-Encoder Reranking

- **Status:** Proposed
- **Date:** 2026-05-17
- **Deciders:** Chris Nogradi

## Context

After hybrid retrieval, the current pipeline sorts candidates by Weaviate's hybrid score (a fusion of BM25 keyword score and vector cosine similarity), then truncates to top-K. This score is fast but coarse: it does not score each `(user_query, candidate_chunk)` pair with attention. It also operates on the *enhanced* BM25 string and the BAML-expanded embedding — both transformations that broaden recall at the cost of precision.

The standard remedy in modern RAG pipelines is a **cross-encoder reranker**: a model that takes the literal user query and a single chunk, attends over both jointly, and produces a precise relevance score. Industry-standard implementations include BGE-reranker-base, Cohere Rerank, and Voyage rerank-2.

### When this matters

In the session logs that prompted these ADRs, several failures had the form *"retrieval pulled adjacent-but-wrong material"*:
- Scapegoat query (before original-words fix) → got generic atonement chunks, not Leviticus 16
- Sheep / "lay down my life" query → got Christ-as-shepherd chunks but not John 10
- Logos query → returned reasonable chunks but ranked Philo's secondary commentary above Gill's primary definition

Many of these failures could be improved at the *reranking* layer even if the underlying retrieval is unchanged. A cross-encoder scoring `"What is the spiritual meaning of the scapegoat?"` against each candidate would surface the Leviticus 16 chunks above generic atonement chunks even when both are retrieved.

## Decision

Insert a cross-encoder reranking step between hybrid retrieval and DSPy synthesis. Specifically:

1. **Increase hybrid retrieval limit** from 12 to ~50 candidates.
2. **Score each candidate** with the cross-encoder using `(original_user_query, candidate.content)` pairs. Use the **original** user query, not the BAML expansion — the reranker is the place where precision matters most.
3. **Truncate to top-K=12** by reranker score for downstream synthesis.
4. **Configurable via env var** (`RERANKER_ENABLED=true|false`) for clean A/B comparison once eval infrastructure exists ([ADR-0004](0004-reference-eval-set-and-ci-gates.md)).
5. **Model choice:** start with BGE-reranker-base (local, no API cost, ~100ms for 50 candidates on CPU; faster on GPU). Cohere Rerank API is the fallback if local inference latency is unacceptable.

## Alternatives Considered

1. **Skip reranking, rely on hybrid score.** Status quo. Cheap, but caps precision at whatever the hybrid fusion produces.
2. **LLM-based reranker.** Use DeepSeek to score relevance ("is this passage relevant to the question? 1-10"). Quality is excellent but slow (10s+ for 50 candidates) and expensive (50 LLM calls per query).
3. **Train a custom reranker on Gill QA pairs.** Most powerful but requires the eval set ([ADR-0004](0004-reference-eval-set-and-ci-gates.md)) plus labeled training data plus ML ops. Best as a phase 2 follow-up after the off-the-shelf reranker proves valuable.
4. **MMR (Maximal Marginal Relevance) re-ranking.** Different goal — diversifies results rather than improving precision. Useful for enumeration queries ([ADR-0001](0001-enumeration-query-path.md)) but not for theological questions where the most relevant 12 chunks are usually clustered.

## Consequences

### Positive
- Substantial precision improvement on questions where retrieval returns adjacent-but-wrong material.
- Orthogonal to current pipeline — no other code changes required.
- Well-trodden pattern; minimal implementation risk.
- Enables future precision-vs-recall tuning (raise hybrid recall to 100 candidates, reranker filters down to 12).

### Negative
- Adds ~100-300ms latency per query (depending on model, candidate count, and CPU/GPU).
- Introduces a model dependency; local model needs deployment alongside Weaviate.
- Total query latency is already ~10-25s for cold cache (BAML expansion dominates); reranker is a small marginal addition but should be measured.

### Risks
- A poorly-chosen reranker can be *worse* than no reranker (the literature has examples). **Mitigation:** require eval-set comparison before defaulting to on.
- Local model inference on CPU may be too slow for production. **Mitigation:** GPU deployment or Cohere API fallback.
- Reranker may itself be biased toward certain phrasings; needs spot-check against verbatim mode outputs to ensure it's not silently reordering things in surprising ways.

## Implementation Sketch (~40 LOC)

```python
# backend/gill_search.py
from sentence_transformers import CrossEncoder

class GillSearchEngine:
    def __init__(self):
        ...
        self.reranker = None
        if os.getenv("RERANKER_ENABLED", "false").lower() == "true":
            self.reranker = CrossEncoder("BAAI/bge-reranker-base")

    async def _rerank(self, query: str, candidates: List[Dict]) -> List[Dict]:
        if not self.reranker or not candidates:
            return candidates
        pairs = [(query, c["content"]) for c in candidates]
        scores = self.reranker.predict(pairs)
        for c, s in zip(candidates, scores):
            c["rerank_score"] = float(s)
        return sorted(candidates, key=lambda c: c["rerank_score"], reverse=True)

    async def search_gill(self, query, ..., original_query=None):
        # Existing hybrid retrieval with raised limit
        candidates = await ...  # limit ~50
        # Rerank with the literal user query
        rerank_query = original_query or query
        candidates = await self._rerank(rerank_query, candidates)
        # Truncate to top-K for synthesis
        return candidates[:12]
```

## Open Questions

- Local CPU inference vs Cohere API vs vLLM-served local model — what's the latency budget?
- Should rerank score be exposed in the API response for debugging / frontend display?
- For chapter/book navigation queries ([ADR-0002](0002-chapter-and-book-prefix-retrieval.md)), reranking is probably skipped (navigation queries aren't ranked by relevance). Confirm via flag.
- Does reranking interact with the enumeration path ([ADR-0001](0001-enumeration-query-path.md))? Probably not — enumeration doesn't use top-K retrieval at all.

## Dependencies

- Best validated with the eval set from [ADR-0004](0004-reference-eval-set-and-ci-gates.md). Implementing without measurement is a gamble.
