#!/usr/bin/env python3
"""
Entity Deduplication Script

This script helps manage the "fragmentation" risk of the "Always Disambiguate" strategy.
It scans Weaviate for entities that share the same Name and Era but have different IDs (due to different roles).

Usage:
    python deduplicate_entities.py scan
    python deduplicate_entities.py merge <KEEP_UUID> <DELETE_UUID>
"""

import os
import sys
import logging
import weaviate
import weaviate.classes as wvc
from dotenv import load_dotenv
from collections import defaultdict
from typing import List, Dict

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

def connect_to_weaviate():
    weaviate_url = os.getenv("WEAVIATE_URL")
    weaviate_api_key = os.getenv("WEAVIATE_API_KEY")
    
    headers = {}
    if os.getenv("OPENROUTER_API_KEY"):
         headers["X-OpenAI-Api-Key"] = os.getenv("OPENROUTER_API_KEY")

    if weaviate_url:
        http_host = weaviate_url.replace("http://", "").replace("https://", "").split(":")[0]
        http_port = int(weaviate_url.split(":")[-1]) if ":" in weaviate_url else 80
        grpc_host = os.getenv("WEAVIATE_GRPC_HOST", http_host)
        grpc_port = int(os.getenv("WEAVIATE_GRPC_PORT", "50051"))
        
        return weaviate.connect_to_custom(
            http_host=http_host,
            http_port=http_port,
            http_secure=weaviate_url.startswith("https"),
            grpc_host=grpc_host,
            grpc_port=grpc_port,
            grpc_secure=weaviate_url.startswith("https"),
            headers=headers,
            auth_credentials=weaviate.auth.AuthApiKey(weaviate_api_key) if weaviate_api_key else None,
            skip_init_checks=True
        )
    else:
        return weaviate.connect_to_local(headers=headers)

def scan_duplicates(client):
    """Scans for potential duplicates (Same Name + Same Era)."""
    entities = client.collections.get("TheologicalEntity")
    
    logging.info("Scanning Theological Entities for fragmentation...")
    
    # Fetch all entities (paginated)
    # Note: For massive graphs, cursor API is better, but this is fine for ~10k nodes
    all_objects = []
    for obj in entities.iterator():
        all_objects.append(obj)
        
    logging.info(f"Analyzed {len(all_objects)} entities.")
    
    # Group by Name + Era
    groups = defaultdict(list)
    for obj in all_objects:
        name = obj.properties.get("name", "").lower()
        era = obj.properties.get("biblical_era", "Unknown")
        key = (name, era)
        groups[key].append(obj)
        
    # Report collisions
    found_duplicates = False
    for (name, era), items in groups.items():
        if len(items) > 1:
            if not found_duplicates:
                print("\n⚠️  POTENTIAL FRAGMENTATION DETECTED ⚠️\n" + "="*50)
                found_duplicates = True
            
            print(f"\nEntity: '{name.title()}' (Era: {era}) has {len(items)} variants:")
            for item in items:
                role = item.properties.get("role", "No Role")
                norm_name = item.properties.get("normalized_name", "")
                print(f"  - UUID: {item.uuid}")
                print(f"    Role: {role}")
                print(f"    ID:   {norm_name}")
                print(f"    Desc: {str(item.properties.get('description', ''))[:50]}...")
            print("-" * 30)

    if not found_duplicates:
        print("\n✅ No obvious fragmentation found (based on Name + Era). graph looks clean.")
    else:
        print("\nTo fix these, run: python deduplicate_entities.py merge <KEEP_UUID> <DELETE_UUID>")

def merge_entities(client, keep_uuid_str, delete_uuid_str):
    """Merges two entities: Re-links chunks from Delete -> Keep, then deletes Delete."""
    chunks = client.collections.get("CommentaryChunk")
    entities = client.collections.get("TheologicalEntity")
    
    print(f"Merging {delete_uuid_str} -> {keep_uuid_str}...")
    
    # 1. Update references in CommentaryChunk
    # We need to find all chunks that reference the 'delete_uuid'
    # Graph update in Weaviate can be tricky. We query for parents.
    
    response = chunks.query.fetch_objects(
        return_references=[wvc.query.QueryReference(link_on="mentions_entity")],
        filters=wvc.query.Filter.by_ref("mentions_entity").by_id().equal(delete_uuid_str),
        limit=10000 
    )
    
    affected_chunks = response.objects
    print(f"Found {len(affected_chunks)} chunks linking to the duplicate entity.")
    
    from weaviate.classes.data import DataReference
    
    for chunk in affected_chunks:
        # Weaviate requires replacing the reference list or adding to it.
        # Simplest approach: Add reference to KEEP, Remove reference to DELETE.
        
        # Add link to Keep
        chunks.data.reference_add(
            from_uuid=chunk.uuid,
            from_property="mentions_entity",
            to=keep_uuid_str
        )
        
        # Remove link to Delete
        chunks.data.reference_delete(
            from_uuid=chunk.uuid,
            from_property="mentions_entity",
            to=delete_uuid_str
        )
        print(f"  - Updated Chunk {chunk.uuid}: Swapped refs.")

    # 2. Delete the duplicate entity
    entities.data.delete_by_id(delete_uuid_str)
    print(f"✅ Deleted fragmented entity: {delete_uuid_str}")
    print("Merge complete.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python deduplicate_entities.py scan")
        print("  python deduplicate_entities.py merge <KEEP_UUID> <DELETE_UUID>")
        sys.exit(1)
        
    command = sys.argv[1]
    
    with connect_to_weaviate() as client:
        if command == "scan":
            scan_duplicates(client)
        elif command == "merge" and len(sys.argv) == 4:
            merge_entities(client, sys.argv[2], sys.argv[3])
        else:
            print("Invalid arguments.")
