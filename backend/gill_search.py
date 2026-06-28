
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

    async def get_relevant_entities(self, query: str, limit: int = 50) -> List[str]:
        """
        Fetch a list of relevant entities for query routing.

        Combines BM25 ranking with substring matching against the deterministic
        `search_key` property (see ADR-0005 Phase 4). The user's tokens are
        canonicalized the same way (`re.sub(r'[^a-z0-9]', '', token.lower())`)
        so 'scapegoat' matches 'scape-goat' / 'Scape-goat' / etc. without needing
        casing or punctuation variants.
        """
        bm25_names: List[str] = []
        try:
            response = await self.entities.query.bm25(query=query, limit=limit)
            bm25_names = [
                obj.properties.get("name")
                for obj in response.objects
                if obj.properties.get("name")
            ]
        except Exception as e:
            print(f"Error fetching entities (BM25): {e}")

        # Substring pre-pass against the canonical search_key — surface entities
        # whose canonical key contains any significant canonicalized query token.
        seen = set(bm25_names)
        substring_names: List[str] = []

        candidates = set()
        for tok in re.findall(r"[A-Za-z]{4,}", query):
            t_lower = tok.lower()
            if t_lower in self._ENTITY_LOOKUP_STOPWORDS:
                continue
            # Canonicalize: lowercase + alphanumeric-only (Unicode-aware), matching
            # the search_key computation in ingest.py.compute_search_key.
            t_key = "".join(c for c in t_lower if c.isalnum())
            if not t_key:
                continue
            candidates.add(t_key)
            # Naive plural handling: also try the singular form.
            if t_key.endswith("s") and len(t_key) > 4:
                candidates.add(t_key[:-1])

        for cand in candidates:
            pattern = f"*{cand}*"
            try:
                response = await self.entities.query.fetch_objects(
                    filters=wvc.query.Filter.by_property("search_key").like(pattern),
                    limit=25,
                )
            except Exception as e:
                print(f"Substring entity lookup failed for '{pattern}': {e}")
                continue
            for obj in response.objects:
                name = obj.properties.get("name")
                if name and name not in seen:
                    seen.add(name)
                    substring_names.append(name)

        combined = bm25_names + substring_names
        if not combined:
            return ["Jesus Christ", "Apostle Paul", "Old Testament saints"]
        return combined

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
