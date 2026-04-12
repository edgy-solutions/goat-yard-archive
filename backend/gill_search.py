
import os
import re
import json
import logging
import litellm
import weaviate
import weaviate.classes as wvc
from typing import List, Dict, Any, Optional
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

             self.client = weaviate.connect_to_custom(
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
            self.client = weaviate.connect_to_local(headers=headers)
            
        self.chunks = self.client.collections.get("CommentaryChunk")
        self.entities = self.client.collections.get("TheologicalEntity")
        
    def close(self):
        self.client.close()

    def _get_embedding(self, text: str) -> List[float]:
        import litellm
        # We point to the LiteLLM Proxy we just set up
        api_base = os.getenv("LITELLM_PROXY_URL", "http://localhost:4000")
        
        try:
            response = litellm.embedding(
                model="openai/qwen3-embedding",
                input=[text],
                api_base=api_base,
                metadata={
                    "generation_name": "gill-search-query",
                    "environment": os.getenv("APP_ENV", "development")
                }
            )
            return response.data[0]['embedding']
        except Exception as e:
            logging.error(f"LiteLLM Gateway Failure: {e}")
            raise Exception("Theology Vector Engine is currently offline")

    def extract_potential_entities(self, query: str) -> List[str]:
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
                    response = self.entities.query.fetch_objects(
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

    def search_gill(self, query: str, entities: List[str] = None, limit: int = 5, volume_filter: int = None) -> List[Dict[str, Any]]:
        """
        Perform Hybrid Search + Graph Boost.
        """
        print(f"Searching for: {query}")
        
        # 1. Entity Extraction (Fallback if not provided)
        detected_entities = entities if entities is not None else self.extract_potential_entities(query)
        print(f"Detected entities: {detected_entities}")
        
        # 2. Build the Enhanced Query for BM25 Boosting (Step 3A)
        enhanced_query = query
        if detected_entities:
            entity_string = " ".join(detected_entities)
            enhanced_query = f"{query} {entity_string}"
            print(f"Enhanced query for boost: {enhanced_query}")

        query_vector = self._get_embedding(enhanced_query)

        weaviate_filters = None
        if volume_filter:
            weaviate_filters = wvc.query.Filter.by_property("volume").equal(volume_filter)
        
        # 2b. Verse Reference Detection (Exact Lookup)
        # Regex for "Book Chapter:Verse" (e.g. Matthew 7:27, Genesis 1:1)
        ref_match = re.search(r'\b(((?:\d\s*)?[A-Za-z]+)\.?\s+(\d+(?::\d+)?))\b', query, re.IGNORECASE)
        
        if ref_match:
            raw_book = ref_match.group(2).lower()
            raw_book = re.sub(r'\s+', ' ', raw_book)
            verse_part = ref_match.group(3)
            
            if raw_book in BIBLE_BOOK_MAP:
                canonical_ref = f"{BIBLE_BOOK_MAP[raw_book]} {verse_part}"
                print(f"Detected verse reference: {canonical_ref}")
                
                ref_filter = wvc.query.Filter.by_property("verse_ref").equal(canonical_ref)
                
                print(f"Executing Direct Lookup for {canonical_ref}")
                response = self.chunks.query.fetch_objects(
                    filters=ref_filter,
                    limit=limit,
                    return_properties=["content", "verse_ref", "page_number", "volume", "scan_json", "footnotes", "sentence_data", "lemma"],
                    return_references=[wvc.query.QueryReference(link_on="mentions_entity")]
                )
            else:
                 # Fallback if map fails
                 response = self.chunks.query.hybrid(
                    query=enhanced_query,
                    vector=query_vector,
                    alpha=0.5, # Step 2: Golden Ratio
                    query_properties=["content", "verse_ref", "entities^3"], # Step 3B: Entity Boost
                    filters=weaviate_filters,
                    limit=limit,
                    return_properties=["content", "verse_ref", "page_number", "volume", "scan_json", "footnotes", "sentence_data", "lemma"],
                    return_references=[wvc.query.QueryReference(link_on="mentions_entity")],
                    return_metadata=wvc.query.MetadataQuery(score=True, explain_score=True)
                )
        else:
            # 3. Retrieval (Hybrid) - Step 2 & 3
            response = self.chunks.query.hybrid(
                query=enhanced_query,
                vector=query_vector,
                alpha=0.5, # Step 2: Golden Ratio
                query_properties=["content", "verse_ref", "entities^3"], # Step 3B: Entity Boost
                filters=weaviate_filters,
                limit=limit,
                return_properties=["content", "verse_ref", "page_number", "volume", "scan_json", "footnotes", "sentence_data", "lemma"],
                return_references=[wvc.query.QueryReference(link_on="mentions_entity")],
                return_metadata=wvc.query.MetadataQuery(score=True, explain_score=True)
            )
        
        if ref_match and 'canonical_ref' in locals():
            # If we successfully identified a canonical reference (e.g. MATTHEW 7:27),
            # we should strictly police the results to ensure we don't return "27:7" for "7:27".
            target_ref = canonical_ref
        elif ref_match:
             # If we matched regex but failed map, we might rely on the raw string, 
             # but "mat 7:27" != "MATTHEW 7:27", so strict equality fails.
             # In fallback mode, we should probably disable strict post-filtering or handle it better.
             target_ref = None # Disable strict filter if we couldn't map it canonical
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

    def get_available_books(self) -> List[str]:
        """Fetch distinct books from the database."""
        try:
            # Aggregate distinct 'book' values
            # Using Weaviate v4 syntax
            response = self.chunks.aggregate.over_all(group_by="book")
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

    def get_top_entities(self, limit: int = 20) -> List[str]:
        """Fetch a list of common entities for query routing."""
        try:
            # Simple fetch of top entities by name
            response = self.entities.query.fetch_objects(limit=limit)
            return [obj.properties.get("name") for obj in response.objects if obj.properties.get("name")]
        except Exception as e:
            print(f"Error fetching entities: {e}")
            return ["Jesus Christ", "Apostle Paul", "Old Testament saints"]

if __name__ == "__main__":
    # Test
    from dotenv import load_dotenv
    load_dotenv()
    engine = GillSearchEngine()
    results = engine.search_gill("What does he say about Cain?")
    for r in results:
        print(f"\n{r['verse_ref']} {r['citation']}")
        print(r['content'][:100] + "...")
    engine.close()
