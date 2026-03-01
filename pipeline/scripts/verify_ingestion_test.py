import weaviate
import os
from dotenv import load_dotenv
import json
import re

load_dotenv()

# Connect to local Weaviate
client = weaviate.connect_to_local()

try:
    # Get collections
    try:
        chunks = client.collections.get("CommentaryChunk")
        entities = client.collections.get("TheologicalEntity")
    except Exception as e:
        print(f"Error getting collections: {e}")
        exit(1)

    # Count objects
    chunk_count = chunks.aggregate.over_all(total_count=True).total_count
    entity_count = entities.aggregate.over_all(total_count=True).total_count

    print(f"\nVerification Results:")
    print(f"---------------------")
    print(f"Total CommentaryChunks: {chunk_count}")
    print(f"Total TheologicalEntity: {entity_count}")

    # Inspect All Chunks
    if chunk_count > 0:
        print(f"\nChunk Analysis:")
        all_chunks = chunks.query.fetch_objects(
            limit=50,
            return_properties=["verse_ref", "content", "footnotes"],
            return_references=[
                weaviate.classes.query.QueryReference(
                    link_on="mentions_entity",
                    return_properties=["name", "category"]
                )
            ]
        ).objects

        # Verify for residual footnotes
        print(f"\nChecking for residual footnotes in all fetched objects...")
        residual_footnotes = 0
        residual_headers = 0
        
        for obj in all_chunks:
            content = obj.properties.get('content', '')
            # Check for footnotes
            if re.search(r'^\s*\[\^\d+\]:', content, re.MULTILINE):
                residual_footnotes += 1
            
            # Check for Verse headers at end
            if re.search(r'\n+\s*(?:Ver|Verse)\.?\s*\d+\.?\s*$', content, re.IGNORECASE):
                residual_headers += 1
                
        if residual_footnotes > 0:
            print(f"  [FAILURE] Found {residual_footnotes} chunks with residual footnote definitions.")
        else:
            print(f"  [SUCCESS] No residual footnote definitions found.")
            
        if residual_headers > 0:
            print(f"  [FAILURE] Found {residual_headers} chunks with residual Verse headers (Ver. N).")
        else:
            print(f"  [SUCCESS] No residual Verse headers found at end of content.")

        for sample in list(all_chunks)[:5]:
            print(f"\n  Verse: {sample.properties.get('verse_ref')}")
            content = sample.properties.get('content', '')
            print(f"  Content Start: {content[:100]!r}")
            print(f"  Content End:   {content[-100:]!r}")
            
            if sample.references.get("mentions_entity"):
                print(f"  Linked Entities ({len(sample.references['mentions_entity'].objects)})")
            
            footnotes = sample.properties.get("footnotes")
            if footnotes:
                print(f"  Footnotes: {footnotes}")
            else:
                print("  No footnotes.")

finally:
    client.close()
