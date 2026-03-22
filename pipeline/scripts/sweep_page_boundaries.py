#!/usr/bin/env python3
import os
import sys
import logging
import json
import weaviate
import weaviate.classes as wvc
from baml_client.sync_client import b

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def run_sweeper(volume: int):
    logging.info(f"Starting Boundary Sweeper for Volume {volume}...")
    
    # 1. Connect to Weaviate
    weaviate_url = os.getenv("WEAVIATE_URL", "localhost")
    headers = {}
    if os.getenv("OPENROUTER_API_KEY"):
        headers["X-OpenAI-Api-Key"] = os.getenv("OPENROUTER_API_KEY")

    if weaviate_url != "localhost":
        http_host = weaviate_url.replace("http://", "").replace("https://", "").split(":")[0]
        http_port = int(weaviate_url.split(":")[-1]) if ":" in weaviate_url else 80
        grpc_host = os.getenv("WEAVIATE_GRPC_HOST", http_host)
        grpc_port = int(os.getenv("WEAVIATE_GRPC_PORT", "50051"))
        
        client = weaviate.connect_to_custom(
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
        client = weaviate.connect_to_local(headers=headers)
        
    chunks = client.collections.get("CommentaryChunk")
    entities_col = client.collections.get("TheologicalEntity")
    
    try:
        # 2. Find the "Sticky Notes" (Flagged Chunks)
        flagged_response = chunks.query.fetch_objects(
            filters=(
                wvc.query.Filter.by_property("volume").equal(volume) &
                wvc.query.Filter.by_property("needs_boundary_resolution").equal(True)
            ),
            limit=500,
            return_properties=["content", "verse_ref", "page_number", "entities"]
        )
        
        flagged_chunks = flagged_response.objects
        logging.info(f"Found {len(flagged_chunks)} chunks needing boundary resolution.")
        
        if not flagged_chunks:
            return

        resolved_count = 0
        
        for chunk in flagged_chunks:
            chunk_id = chunk.uuid
            current_text = chunk.properties.get("content", "")
            verse_ref = chunk.properties.get("verse_ref")
            page_number = chunk.properties.get("page_number")
            current_entities = chunk.properties.get("entities", []) or []
            
            logging.info(f"Resolving boundary for {verse_ref} on page {page_number}...")
            
            # 3. Fetch the Previous Page's Context
            prev_page = page_number - 1
            prev_response = chunks.query.fetch_objects(
                filters=(
                    wvc.query.Filter.by_property("volume").equal(volume) &
                    wvc.query.Filter.by_property("page_number").equal(prev_page)
                ),
                limit=50,
                return_properties=["content", "verse_ref"],
                return_references=[wvc.query.QueryReference(link_on="mentions_entity")]
            )
            
            if not prev_response.objects:
                logging.warning(f"Could not find previous page ({prev_page}) for {verse_ref}. Skipping.")
                continue
                
            # Find the best preceding chunk
            prev_chunk = next((c for c in prev_response.objects if c.properties.get("verse_ref") == verse_ref), None)
            if not prev_chunk:
                prev_chunk = prev_response.objects[-1]
                
            prev_text = prev_chunk.properties.get("content", "")
            
            # Extract entity names from graph edges
            prev_entities = []
            if prev_chunk.references and "mentions_entity" in prev_chunk.references:
                for ent_ref in prev_chunk.references["mentions_entity"].objects:
                    name = ent_ref.properties.get("name")
                    if name: prev_entities.append(name)
            
            if not prev_entities:
                logging.info(f"No entities to carry over from previous chunk. Clearing flag.")
                chunks.data.update(uuid=chunk_id, properties={"needs_boundary_resolution": False})
                continue

            # 4. Ask BAML to solve the puzzle
            try:
                resolution = b.ResolveBoundaryPronouns(
                    unresolved_text=current_text,
                    previous_text=prev_text,
                    previous_entities=prev_entities
                )
                
                new_names = resolution.resolved_entity_names
                if new_names:
                    logging.info(f"BAML resolved pronouns to: {new_names}")
                    
                    # 5. Look up UUIDs
                    uuids_to_link = []
                    for name in new_names:
                        ent_search = entities_col.query.fetch_objects(
                            filters=wvc.query.Filter.by_property("name").equal(name),
                            limit=1
                        )
                        if ent_search.objects:
                            uuids_to_link.append(ent_search.objects[0].uuid)
                    
                    # 6. Apply Fix
                    if uuids_to_link:
                        chunks.data.reference_add(
                            from_uuid=chunk_id,
                            from_property="mentions_entity",
                            to=uuids_to_link
                        )
                    
                    updated_entities_list = list(set(current_entities + new_names))
                    chunks.data.update(
                        uuid=chunk_id,
                        properties={
                            "needs_boundary_resolution": False,
                            "entities": updated_entities_list
                        }
                    )
                    resolved_count += 1
                else:
                    chunks.data.update(uuid=chunk_id, properties={"needs_boundary_resolution": False})
                    
            except Exception as e:
                logging.error(f"Failed to resolve with BAML: {e}")

        logging.info(f"Sweep complete! Resolved {resolved_count} boundary issues.")

    finally:
        if client:
            client.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--volume", type=int, required=True)
    args = parser.parse_args()
    run_sweeper(args.volume)
