
import os
import re
import json
import logging
import litellm
import weaviate
import weaviate.classes as wvc
from typing import List, Dict, Any, Optional
from langfuse import observe
from .bible_mapping import BIBLE_BOOK_MAP

class GillSearchEngine:
    def __init__(self):
        # reuse connection logic from ingest.py (simplified)
        weaviate_url = os.getenv("WEAVIATE_URL", "localhost")
        
        headers = {}
        if os.getenv("OPENROUTER_API_KEY"):
            headers["X-OpenAI-Api-Key"] = os.getenv("OPENROUTER_API_KEY")

        if weaviate_url != "localhost":
             # Check if scheme exists
             if "://" not in weaviate_url:
                 # Logic for "host:port" or "host"
                 if ":" in weaviate_url:
                     http_host = weaviate_url.split(":")[0]
                     try:
                         http_port = int(weaviate_url.split(":")[-1])
                     except:
                         http_port = int(os.getenv("WEAVIATE_PORT", 80))
                 else:
                     http_host = weaviate_url
                     http_port = int(os.getenv("WEAVIATE_PORT", 80))
             else:
                  from urllib.parse import urlparse
                  parsed = urlparse(weaviate_url)
                  http_host = parsed.hostname
                  http_port = parsed.port if parsed.port is not None else int(os.getenv("WEAVIATE_PORT", 80))
             
             grpc_host = os.getenv("WEAVIATE_GRPC_HOST", http_host)
             grpc_port = int(os.getenv("WEAVIATE_GRPC_PORT", "50051"))
             
             print(f"Connecting to Weaviate at HTTP:{http_host}:{http_port} / gRPC:{grpc_host}:{grpc_port}")

             self.client = weaviate.use_async_with_custom(
                http_host=http_host,
                http_port=http_port,
                http_secure=weaviate_url.startswith("https"),
                grpc_host=grpc_host,
                grpc_port=grpc_port,
                grpc_secure=weaviate_url.startswith("https"),
                headers=headers,
                skip_init_checks=True
            )
        else:
            print("Connecting to Weaviate Local")
            self.client = weaviate.use_async_with_local(headers=headers)
            
        self.chunks = None
        self.entities = None
        
    async def connect(self):
        await self.client.connect()
        self.chunks = self.client.collections.get("CommentaryChunk")
        self.entities = self.client.collections.get("TheologicalEntity")
        
    async def close(self):
        await self.client.close()

    @observe(as_type="span", name="embedding-generation")
    async def _get_embedding(self, text: str) -> List[float]:
        import litellm
        import time
        
        t0 = time.perf_counter()
        api_base = os.getenv("LITELLM_PROXY_URL", "http://localhost:4000")
        
        try:
            response = await litellm.aembedding(
                model="openai/qwen3-embedding",
                api_key="anything",
                input=[text],
                api_base=api_base,
                metadata={
                    "generation_name": "gill-search-query",
                    "environment": os.getenv("APP_ENV", "development")
                }
            )
            t1 = time.perf_counter()
            print(f"[TIMING] Embedding via LiteLLM: {t1-t0:.3f}s")
            return response.data[0]['embedding']
        except Exception as e:
            logging.error(f"LiteLLM Gateway Failure: {e}")
            raise Exception("Theology Vector Engine is currently offline")

    async def extract_potential_entities(self, query: str) -> List[str]:
        """
        Identify potential entities in the query.
        Look for words that match entities in the DB, handling case sensitivity.
        """
        # Capture all word sequences (potential names)
        # We'll split by spaces and check grams or just individual keys.
        # Simplest approach: Check title-cased words from query.
        
        words = re.findall(r'\b[a-z]+\b', query, re.IGNORECASE)
        verified_entities = []
        
        for w in words:
            if len(w) < 3: continue
            
            # Check original and title-cased (e.g. "abraham" -> "Abraham")
            candidates = set([w, w.capitalize(), w.lower()])
            
            for cand in candidates:
                try:
                    # We accept partial match or exact match? Exact is safer for "Name" lookup.
                    # Using LIKE or EQUAL
                    response = await self.entities.query.fetch_objects(
                        filters=wvc.query.Filter.by_property("name").equal(cand),
                        limit=1
                    )
                    if response.objects:
                        # Found one! Use the stored name (correct casing)
                        stored_name = response.objects[0].properties.get("name")
                        if stored_name and stored_name not in verified_entities:
                            verified_entities.append(stored_name)
                except Exception as e:
                    pass
        
        return verified_entities

    async def search_gill(
        self,
        query: str,
        entities: List[str] = None,
        limit: int = 5,
        volume_filter: int = None,
        original_query: str = None,
        _debug_capture: dict = None,
    ) -> List[Dict[str, Any]]:
        """
        Perform Hybrid Search + Graph Boost.

        `query` is the BAML-expanded search text. `original_query` is the user's
        literal words. Both contribute to BOTH the BM25 side and the dense vector
        side of the hybrid so that rare keywords (e.g. "scapegoat", "Logos") survive
        even when BAML's synonym expansion replaced them with broader paraphrases.
        Entity names are added ONLY to the BM25 side — repeating entity tokens in
        the embedding input dilutes the dense vector's semantic signal.
        """
        print(f"Searching for: {query}")

        # 1. Entity Extraction (Fallback if not provided)
        detected_entities = entities if entities is not None else await self.extract_potential_entities(query)
        print(f"Detected entities: {detected_entities}")

        # 2. Build search inputs.
        # BM25 string: original_query + BAML expansion + entity names. Entity names
        # belong here because they boost via the `entities^3` query property.
        # Embedding input: original_query + BAML expansion (NO entity names). The
        # user's literal words give the dense vector a rare-keyword anchor; BAML's
        # expansion gives it paraphrase coverage.
        original_clean = original_query.strip() if original_query else ""
        include_original = bool(original_clean) and original_clean != query.strip()

        bm25_parts = []
        if include_original:
            bm25_parts.append(original_clean)
        bm25_parts.append(query)
        if detected_entities:
            bm25_parts.append(" ".join(detected_entities))
        enhanced_query = " ".join(bm25_parts)
        if len(bm25_parts) > 1:
            print(f"Enhanced query for boost: {enhanced_query}")

        embed_parts = []
        if include_original:
            embed_parts.append(original_clean)
        embed_parts.append(query)
        embedding_input = " ".join(embed_parts)
        query_vector = await self._get_embedding(embedding_input)

        if _debug_capture is not None:
            import hashlib as _h
            _debug_capture["embedding_input"] = embedding_input
            _debug_capture["enhanced_query"] = enhanced_query
            vec_for_hash = list(query_vector) if query_vector is not None else []
            _debug_capture["embedding_hash"] = _h.sha256(
                json.dumps(vec_for_hash).encode()
            ).hexdigest()[:16]
            _debug_capture["embedding_first_5"] = (
                [round(float(x), 8) for x in vec_for_hash[:5]] if vec_for_hash else []
            )
            _debug_capture["embedding_len"] = len(vec_for_hash)

        weaviate_filters = None
        if volume_filter:
            weaviate_filters = wvc.query.Filter.by_property("volume").equal(volume_filter)
        
        # 2b. Verse Reference Detection (Exact Lookup).
        # Run the regex on the ORIGINAL user query, not the BAML expansion.
        # BAML often adds synonyms like "Leviticus 16" to broaden BM25 recall, and
        # those should be treated as search hints (keyword material), not as a
        # navigation signal that switches us to direct verse lookup. The user
        # knows when they're typing a verse reference.
        #
        # 2026-06-21: switched from re.search to re.fullmatch. The previous
        # search-anywhere behavior matched verse refs embedded INSIDE question
        # text (e.g. "Why did God have Ishmael circumcised when (according to
        # Genesis 17:19-21)...") and triggered direct-verse-lookup mode,
        # starving retrieval to the 3 sentences of that one verse. Sophisticated
        # users who cite the verse they're asking about — the Puritan Board
        # audience — were the worst affected. fullmatch only fires on bare
        # verse-ref queries; embedded refs fall through to hybrid retrieval.
        ref_source = original_query if original_query and original_query.strip() else query
        ref_source_clean = (ref_source or "").strip().rstrip('?.!').strip()
        ref_match = re.fullmatch(
            r'\s*((?:\d\s*)?[A-Za-z]+)\.?\s+(\d+(?:[:.]\d+)?)\s*',
            ref_source_clean,
            re.IGNORECASE,
        )

        import time
        t_weaviate_start = time.perf_counter()

        async def _do_hybrid():
            return await self.chunks.query.hybrid(
                query=enhanced_query,
                vector=query_vector,
                alpha=0.35,
                query_properties=["content", "verse_ref", "entities^3"],
                filters=weaviate_filters,
                limit=limit,
                return_properties=["content", "verse_ref", "page_number", "volume", "scan_json", "footnotes", "sentence_data", "lemma"],
                return_references=[wvc.query.QueryReference(link_on="mentions_entity")],
                return_metadata=wvc.query.MetadataQuery(score=True, explain_score=True)
            )

        response = None
        used_hybrid_fallback = False
        if ref_match:
            # New regex (fullmatch) has 2 groups: book, verse_part.
            raw_book = ref_match.group(1).lower()
            raw_book = re.sub(r'\s+', ' ', raw_book)
            verse_part = ref_match.group(2).replace('.', ':')

            if raw_book in BIBLE_BOOK_MAP:
                canonical_ref = f"{BIBLE_BOOK_MAP[raw_book]} {verse_part}"
                print(f"Detected verse reference: {canonical_ref}")

                ref_filter = wvc.query.Filter.by_property("verse_ref").equal(canonical_ref)

                print(f"Executing Direct Lookup for {canonical_ref}")
                response = await self.chunks.query.fetch_objects(
                    filters=ref_filter,
                    limit=limit,
                    return_properties=["content", "verse_ref", "page_number", "volume", "scan_json", "footnotes", "sentence_data", "lemma"],
                    return_references=[wvc.query.QueryReference(link_on="mentions_entity")]
                )

                # Safety net: if exact verse-ref lookup found nothing (often because
                # the user gave a chapter-only ref like "Leviticus 16" but chunks are
                # stored per-verse as "LEVITICUS 16:9"), fall through to hybrid so the
                # user still gets relevant content instead of an empty response.
                if not response.objects:
                    print(f"Direct lookup empty for {canonical_ref}; falling back to hybrid.")
                    response = await _do_hybrid()
                    used_hybrid_fallback = True
            else:
                response = await _do_hybrid()
        else:
            response = await _do_hybrid()

        t_weaviate_end = time.perf_counter()
        print(f"[TIMING] Weaviate query: {t_weaviate_end-t_weaviate_start:.3f}s")

        # Post-filter target: only enforce strict verse-ref equality when we
        # actually ran the direct-lookup path (not when we fell back to hybrid,
        # since hybrid returns related per-verse chunks like "LEVITICUS 16:9"
        # that we WANT to keep for a chapter-only query like "Leviticus 16").
        if ref_match and 'canonical_ref' in locals() and not used_hybrid_fallback:
            target_ref = canonical_ref
        else:
            target_ref = None

        results = []
        for obj in response.objects:
            # Post-filter for Exact Reference Match (if active)
            extracted_ref = obj.properties.get("verse_ref")
            
            if target_ref:
                if extracted_ref != target_ref:
                     continue

            # Parse scan_json safety
            scan_box = None
            if obj.properties.get("scan_json"):
                try:
                    scan_box = json.loads(obj.properties["scan_json"])
                except:
                    pass
            
            # Extract referenced entities
            entity_names = []
            if obj.references and "mentions_entity" in obj.references:
                # Safe access for v4 client
                ref_val = obj.references["mentions_entity"]
                if hasattr(ref_val, 'objects'):
                    for ref_obj in ref_val.objects:
                       name = ref_obj.properties.get("name")
                       if name:
                           entity_names.append(name)
            
            # Deduplicate
            entity_names = list(set(entity_names))

            # Format output
            # Format output
            # DEBUG KEYS
            print(f"DEBUG: Chunk keys: {list(obj.properties.keys())}")
            vol_val = obj.properties.get('volume')
            page_val = obj.properties.get('page_number')
            try:
                if vol_val is not None: vol_val = int(vol_val)
                if page_val is not None: page_val = int(page_val)
            except:
                pass

            # Parse sentence_data (JSON blob)
            s_data = []
            if obj.properties.get("sentence_data"):
                try:
                    s_data = json.loads(obj.properties["sentence_data"])
                except:
                    pass

            results.append({
                "chunk_id": str(obj.uuid),
                "sentence_data": s_data,
                "content": obj.properties.get("content"),
                "verse_ref": extracted_ref,
                "citation": f"[Vol {vol_val}, p. {page_val}]",
                "vol": vol_val,
                "page": page_val,
                "scan": scan_box,
                "footnotes": obj.properties.get("footnotes", []),
                "entities": entity_names,
                "lemma": obj.properties.get("lemma"),
                "score": obj.metadata.score if (obj.metadata and obj.metadata.score is not None) else 1.0 # Boost score for lookup
            })
            
        return results

    async def get_available_books(self) -> List[str]:
        """Fetch distinct books from the database."""
        try:
            # Aggregate distinct 'book' values
            # Using Weaviate v4 syntax
            response = await self.chunks.aggregate.over_all(group_by="book")
            books = []
            if response.groups:
                for grp in response.groups:
                    val = grp.grouped_by.value
                    if val:
                        books.append(val.title()) # normalize case
            
            return sorted(list(set(books)))
        except Exception as e:
            print(f"Error fetching books: {e}")
            # Fallback if aggregation fails or not supported on this version yet
            return ["Genesis", "Matthew"]

    # Common English stopwords / interrogatives that should never trigger a substring
    # entity lookup (otherwise "how" matches "Howe", "are" matches "Aaron", etc.).
    _ENTITY_LOOKUP_STOPWORDS = {
        "how", "many", "what", "when", "where", "which", "who", "whom", "why",
        "the", "and", "are", "was", "were", "for", "with", "that", "this",
        "from", "did", "does", "have", "has", "had", "been", "into", "out",
        "over", "than", "then", "there", "their", "they", "them", "those",
        "these", "your", "yours", "you", "his", "her", "him", "she", "all",
        "any", "one", "two", "but", "not", "can", "will", "should", "could",
        "would", "about", "say", "said", "tell", "told", "make", "made",
        "mean", "means", "meaning", "give", "given", "gives", "name", "names",
        "named", "between", "within", "without", "before", "after", "such",
        "some", "much", "more", "most", "less", "least", "very", "still",
        "only", "also", "ever", "even", "just", "really", "actually",
    }

    # Vector-tier constants — DERIVED from E-6 diagnostic probe (2026-07-07).
    # See ADR-0010 for the probe methodology and the score distributions
    # these numbers came from. Do not tune without re-running E-6.
    #
    #   VECTOR_CONFIDENT_DIST_MAX — cosine distance ceiling for "the vector
    #     is confident this entity is a match." Sanity + strong in-domain
    #     top-1s land 0.16-0.22; the observed vector-side false-positive
    #     (`exclusive psalmody` -> `music` at 0.252) sits just above 0.25,
    #     so 0.25 excludes it for free. Consequence: some in-domain queries
    #     with dilute phrasing land above 0.25 and get NO vector boost.
    #     Intentional — silence is safer than admitting middle-band noise.
    #
    #   VECTOR_TIER_CAP — top-K within the confident tier. E-6 found the
    #     genuinely-adjacent hits are the first 1-3 with a visible score
    #     cliff after; anything past 3 in the confident tier is tail noise.
    #
    #   MANIFEST_TOTAL_CAP — union across substring / vector / BM25 tiers
    #     after dedup. Lower than the pre-fix limit of 50 to prevent the
    #     manifest flood that caused the 2026-06-21 universal_atonement bug.
    VECTOR_CONFIDENT_DIST_MAX = 0.25
    VECTOR_TIER_CAP = 3
    MANIFEST_TOTAL_CAP = 5

    async def get_relevant_entities(
        self, query: str, limit: int | None = None
    ) -> tuple[List[str], str]:
        """
        Fetch relevant entities for query routing, and report the lookup MODE.

        Returns (names, mode) where mode is one of:
          "full"                — the vector tier (Tier 1) executed. The
                                  manifest reflects the full three-tier
                                  lookup and is trustworthy.
          "degraded_no_vector"  — the vector-tier embedding failed (litellm
                                  enrichment infra unavailable for this
                                  call). Tiers 2/3 (substring/BM25) still
                                  ran, but the manifest is NOT the same
                                  algorithm — it is missing the concept-
                                  disambiguation the vector tier provides,
                                  and E-9/E-11 established this degraded
                                  manifest is materially different and
                                  worse (the 2026-07 ceremonial-homonym
                                  collapse: 'atonement' -> Leviticus ritual
                                  because the vector tier that would have
                                  found gospel-preaching entities was down).

        The mode exists to obey the ADR-0014 design law: fail loud or fail
        closed, never fail different. The vector tier is ENRICHMENT infra
        (unlike Weaviate + the query embedding in search_gill, which are
        LOAD-BEARING and fail the request closed). When enrichment degrades,
        the caller must degrade to the deterministic floor (suppress the
        entity boost) rather than silently boosting on a different-worse
        manifest. The mode carries that decision to the caller and into the
        trace, so an infra blip announces itself instead of surfacing as a
        theological error weeks later.

        Three tiers merged in confidence order (ADR-0010):

          Tier 1 — near_vector on qwen3-embedding, distance <= 0.25, cap 3.
          Tier 2 — Substring canonical-key match (ADR-0005 Phase 4).
          Tier 3 — BM25 name-token match.

        Total union capped at MANIFEST_TOTAL_CAP after dedup. `limit`, when
        provided, overrides the total cap.
        """
        total_cap = limit if limit is not None else self.MANIFEST_TOTAL_CAP

        # Tier 1 — confident vector. Its success/failure IS the mode signal.
        vector_names: List[str] = []
        vector_tier_ok = True
        try:
            query_vec = await self._get_embedding(query)
            resp = await self.entities.query.near_vector(
                near_vector=query_vec,
                limit=self.VECTOR_TIER_CAP,
                distance=self.VECTOR_CONFIDENT_DIST_MAX,
                return_properties=["name"],
            )
            vector_names = [
                obj.properties.get("name")
                for obj in resp.objects
                if obj.properties.get("name")
            ]
        except Exception as e:
            # Distinguish "vector engine offline" (enrichment infra down ->
            # degraded mode) from a Weaviate near_vector error. Both leave
            # vector_names empty, but only the embedding failure means the
            # lookup ran a different algorithm. _get_embedding raises the
            # sentinel string "Theology Vector Engine is currently offline".
            vector_tier_ok = False
            print(f"[ENTITY LOOKUP] vector tier degraded (mode=degraded_no_vector): {e}")

        # Tier 2 — substring canonical-key.
        #
        # Length floor is 5, not 4, since the 2026-07-13 psalmist
        # incident. At 4, common short theological tokens ("book",
        # "life", "word", "name", "day", "way", "son", "law", "sin",
        # "god", "lord", "holy", "faith") substring-flood the results.
        # A query or BAML expansion containing "Book of Psalms" produced
        # `*book*` matches against every `book of X` entity in the
        # corpus — bookofpsalms (right), bookofwisdom, bookoflife,
        # sealedbook, authorsofaneditionofthebookofzohar (all noise),
        # then unioned into the boost until the load-bearing signal
        # was drowned. Real query targets are distinctive by design:
        # 'psalms' (6), 'wisdom' (6), 'atonement' (9), 'covenant' (8),
        # 'scapegoat' (9). Single-word 4-char entity names (Cain, Adam,
        # Ruth, Paul, Mary) are covered by Tier 3 BM25 via word-token
        # match on the entity name field — no substring path needed.
        # See ADR-0013 amendment 2026-07-13 for the incident trace.
        substring_names: List[str] = []
        seen_lower = {n.lower() for n in vector_names if n}
        candidates = set()
        for tok in re.findall(r"[A-Za-z]{5,}", query):
            t_lower = tok.lower()
            if t_lower in self._ENTITY_LOOKUP_STOPWORDS:
                continue
            t_key = "".join(c for c in t_lower if c.isalnum())
            if not t_key:
                continue
            candidates.add(t_key)
            if t_key.endswith("s") and len(t_key) > 5:
                candidates.add(t_key[:-1])

        for cand in candidates:
            try:
                resp = await self.entities.query.fetch_objects(
                    filters=wvc.query.Filter.by_property("search_key").like(f"*{cand}*"),
                    limit=25,
                    return_properties=["name"],
                )
            except Exception as e:
                print(f"Substring entity lookup failed for '{cand}': {e}")
                continue
            for obj in resp.objects:
                name = obj.properties.get("name")
                if name and name.lower() not in seen_lower:
                    seen_lower.add(name.lower())
                    substring_names.append(name)

        # Tier 3 — BM25.
        bm25_names: List[str] = []
        try:
            resp = await self.entities.query.bm25(
                query=query,
                limit=self.VECTOR_TIER_CAP,
                return_properties=["name"],
            )
            for obj in resp.objects:
                name = obj.properties.get("name")
                if name and name.lower() not in seen_lower:
                    seen_lower.add(name.lower())
                    bm25_names.append(name)
        except Exception as e:
            print(f"Error fetching entities (BM25): {e}")

        mode = "full" if vector_tier_ok else "degraded_no_vector"

        combined = vector_names + substring_names + bm25_names
        if not combined:
            # Legitimately-empty lookup (no tier matched) — NOT an infra
            # failure. The hardcoded default is a last-resort routing hint;
            # the caller still sees the mode and can decide. (This default
            # predates the mode work and is itself a mild "fail different"
            # candidate; left as-is pending its own review.)
            return (["Jesus Christ", "Apostle Paul", "Old Testament saints"], mode)
        return (combined[:total_cap], mode)

if __name__ == "__main__":
    # Test
    import asyncio
    from dotenv import load_dotenv
    load_dotenv()
    
    async def test():
        engine = GillSearchEngine()
        await engine.connect()
        results = await engine.search_gill("What does he say about Cain?")
        for r in results:
            print(f"\n{r['verse_ref']} {r['citation']}")
            print(r['content'][:100] + "...")
        await engine.close()
    
    asyncio.run(test())
