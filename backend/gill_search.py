
import os
import re
import json
import logging
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
             from urllib.parse import urlparse
             parsed = urlparse(weaviate_url)
             
             # Handle cases where user might provide just "host:port" without scheme
             if not parsed.scheme and not parsed.netloc:
                 # Fallback for bare "host:port"
                 if "://" not in weaviate_url:
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
                     # Should have been caught by urlparse if it had scheme
                     http_host = weaviate_url
                     http_port = int(os.getenv("WEAVIATE_PORT", 80))
             else:
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

    def search_gill(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Perform Hybrid Search + Graph Boost.
        """
        print(f"Searching for: {query}")
        
        # 1. Entity Extraction
        entities = self.extract_potential_entities(query)
        print(f"Detected entities: {entities}")
        
        filters = None
        # 2. The Graph Boost (Filter)
        # If entities found, we prioritize chunks mentioning them?
        # The instruction says: "If an entity was found... apply a filter to the query to prioritize chunks..."
        # Weaviate Hybrid search doesn't have "boost" via filter easily, 
        # but we can use 'move_to' concept or just hard filter if the user *only* wants that entity.
        # However, usually "prioritize" means boost.
        # But let's follow the simple instruction: "apply a filter... to prioritize". 
        # Maybe it implies filtering to *only* those that mention it? 
        # Or maybe it means using the entity name in the hybrid search query with higher alpha?
        # I will use a filter if entities are found, to narrow the scope. This is safer for "Grounding".
        
        if entities:
            # Create a filter where 'mentions_entity' has 'name' equal to any found entity
            entity_filters = []
            for ent in entities:
                entity_filters.append(
                    wvc.query.Filter.by_ref("mentions_entity").by_property("name").equal(ent)
                )
            
            if len(entity_filters) > 1:
                filters = wvc.query.Filter.any_of(entity_filters)
            else:
                filters = entity_filters[0]

        # 2b. Verse Reference Detection (Exact Lookup)
        # Regex for "Book Chapter:Verse" (e.g. Matthew 7:27, Genesis 1:1)
        # We try to match standard format. If found, we PRIORITIZE/FILTER by it.
        # 2b. Verse Reference Detection (Exact Lookup)
        # Regex for "Book Chapter:Verse" (e.g. Matthew 7:27, Mat 7:27, 2 Cor 1:1, Ecc 1:2)
        # Matches: Optional digit prefix, followed by letters, optional dot, followed by numbers.
        # Captures: 1. Full Ref string (ignored mostly), 2. Book Part, 3. Verse Part
        
        # Regex explanation:
        # \b                Phrase boundary
        # (                 Group 1: Capture whole thing for debugging logic if needed
        #  ((?:\d\s*)?[A-Za-z]+)   Group 2: Book Name (Optional digit + space, then letters). E.g. "1 John", "Mat"
        #  \.?                  Optional dot (Mat.)
        #  \s+                  Space
        #  (\d+:\d+)            Group 3: Chapter:Verse
        # )
        ref_match = re.search(r'\b(((?:\d\s*)?[A-Za-z]+)\.?\s+(\d+:\d+))\b', query, re.IGNORECASE)
        
        if ref_match:
            raw_book = ref_match.group(2).lower() # Group 2 is the Book part
            # handle cases like "1   john" -> "1 john" (normalize spaces)
            raw_book = re.sub(r'\s+', ' ', raw_book)
            
            verse_part = ref_match.group(3)
            
            if raw_book in BIBLE_BOOK_MAP:
                canonical_ref = f"{BIBLE_BOOK_MAP[raw_book]} {verse_part}"
                print(f"Detected verse reference: {canonical_ref} (from {ref_match.group(0)})")
                
                ref_filter = wvc.query.Filter.by_property("verse_ref").equal(canonical_ref)
                
                print(f"Executing Direct Lookup for {canonical_ref}")
                response = self.chunks.query.fetch_objects(
                    filters=ref_filter,
                    limit=limit,
                    return_properties=["content", "verse_ref", "page_number", "volume", "scan_json", "footnotes"],
                    return_references=[wvc.query.QueryReference(link_on="mentions_entity")]
                )
            else:
                 # Fallback if map fails (unlikely due to regex)
                 print(f"Warning: Could not map book '{raw_book}'")
                 response = self.chunks.query.hybrid(
                    query=query,
                    query_properties=["content", "verse_ref"],
                    filters=filters,
                    limit=limit,
                    return_properties=["content", "verse_ref", "page_number", "volume", "scan_json", "footnotes"],
                    return_references=[wvc.query.QueryReference(link_on="mentions_entity")]
                )
        else:
            # 3. Retrieval (Hybrid)
            response = self.chunks.query.hybrid(
                query=query,
                query_properties=["content", "verse_ref"],
                filters=filters,
                limit=limit,
                return_properties=["content", "verse_ref", "page_number", "volume", "scan_json", "footnotes"],
                return_references=[wvc.query.QueryReference(link_on="mentions_entity")]
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
            vol_val = obj.properties.get('volume')
            page_val = obj.properties.get('page_number')
            try:
                if vol_val is not None: vol_val = int(vol_val)
                if page_val is not None: page_val = int(page_val)
            except:
                pass

            results.append({
                "chunk_id": str(obj.uuid),
                "content": obj.properties.get("content"),
                "verse_ref": extracted_ref,
                "citation": f"[Vol {vol_val}, p. {page_val}]",
                "vol": vol_val,
                "page": page_val,
                "scan": scan_box,
                "footnotes": obj.properties.get("footnotes", []),
                "entities": entity_names,
                "score": obj.metadata.score if (obj.metadata and obj.metadata.score is not None) else 1.0 # Boost score for lookup
            })
            
        return results

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
