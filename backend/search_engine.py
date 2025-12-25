
import os
import re
import json
import logging
import weaviate
import weaviate.classes as wvc
from typing import List, Dict, Any, Optional

class GillSearchEngine:
    def __init__(self):
        # reuse connection logic from ingest.py (simplified)
        weaviate_url = os.getenv("WEAVIATE_URL", "localhost")
        weaviate_port = int(os.getenv("WEAVIATE_PORT", 8080))
        
        headers = {}
        if os.getenv("OPENROUTER_API_KEY"):
            headers["X-OpenAI-Api-Key"] = os.getenv("OPENROUTER_API_KEY")

        print(f"Connecting to Weaviate at {weaviate_url}:{weaviate_port}")
        if weaviate_url != "localhost":
             self.client = weaviate.connect_to_custom(
                http_host=weaviate_url.replace("http://", "").replace("https://", "").split(":")[0],
                http_port=80,
                http_secure=False,
                grpc_host=weaviate_url.replace("http://", "").replace("https://", "").split(":")[0],
                grpc_port=50051,
                grpc_secure=False,
                headers=headers
            )
        else:
            self.client = weaviate.connect_to_local(headers=headers)
            
        self.chunks = self.client.collections.get("CommentaryChunk")
        self.entities = self.client.collections.get("TheologicalEntity")
        
    def close(self):
        self.client.close()

    def extract_potential_entities(self, query: str) -> List[str]:
        """
        Identify potential entities in the query.
        For now, we look for Capitalized Words and verify if they exist in DB.
        """
        # Simple regex for Capitalized phrases (e.g. "John Gill", "Socinus", "God")
        # Ignoring common stop words if necessary, but Weaviate handles that generally.
        caps = re.findall(r'\b[A-Z][a-z]+\b', query)
        verified_entities = []
        
        for cap in caps:
            # Check existence in Weaviate (exact match for speed)
            # This is the "Lightweight" check
            response = self.entities.query.fetch_objects(
                filters=wvc.query.Filter.by_property("name").equal(cap),
                limit=1
            )
            if response.objects:
                verified_entities.append(cap)
                
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
            # We construct a Filter
            entity_filters = []
            for ent in entities:
                entity_filters.append(
                    wvc.query.Filter.by_ref("mentions_entity").by_property("name").equal(ent)
                )
            
            # OR logic? If query has "Adam and Eve", we might want either? 
            # Let's assume OR for now if multiple.
            if len(entity_filters) > 1:
                filters = wvc.query.Filter.any_of(entity_filters)
            else:
                filters = entity_filters[0]

        # 3. Retrieval (Hybrid)
        response = self.chunks.query.hybrid(
            query=query,
            query_properties=["content"],
            filters=filters,
            limit=limit,
            return_properties=["content", "verse_ref", "page_number", "volume", "scan_json"],
            return_references=[
                 wvc.query.QueryReference(
                        link_on="mentions_entity",
                        return_properties=["name"]
                    )
            ]
        )
        
        results = []
        for obj in response.objects:
            # Parse scan_json safety
            scan_box = None
            if obj.properties.get("scan_json"):
                try:
                    scan_box = json.loads(obj.properties["scan_json"])
                except:
                    pass
            
            # Format output
            results.append({
                "chunk_id": str(obj.uuid),
                "content": obj.properties.get("content"),
                "verse_ref": obj.properties.get("verse_ref"),
                "citation": f"[Vol {obj.properties.get('volume')}, p. {obj.properties.get('page_number')}]",
                "vol": obj.properties.get('volume'),
                "page": obj.properties.get('page_number'),
                "scan": scan_box,
                "score": obj.metadata.score if (obj.metadata and obj.metadata.score is not None) else 0.0
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
