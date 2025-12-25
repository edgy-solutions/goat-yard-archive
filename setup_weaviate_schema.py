#!/usr/bin/env python3
"""
Weaviate Schema Setup for Gill Commentary Knowledge Graph.

This script initializes the Weaviate collections for:
1. TheologicalEntity - Knowledge graph nodes
2. CommentaryChunk - Searchable commentary content with sentence granularity
"""

import os
import weaviate
import weaviate.classes as wvc
from weaviate.classes.config import Configure, Property, DataType, ReferenceProperty

def setup_weaviate_schema():
    """Initialize Weaviate collections."""
    weaviate_url = os.getenv("WEAVIATE_URL", "localhost")
    weaviate_port = int(os.getenv("WEAVIATE_PORT", 8080))
    
    # Connect to Weaviate
    print(f"Connecting to Weaviate at {weaviate_url}:{weaviate_port}...")
    headers = {}
    if os.getenv("OPENROUTER_API_KEY"):
         headers["X-OpenAI-Api-Key"] = os.getenv("OPENROUTER_API_KEY")
    
    if weaviate_url != "localhost":
         client = weaviate.connect_to_custom(
            http_host=weaviate_url.replace("http://", "").replace("https://", "").split(":")[0],
            http_port=80,
            http_secure=False,
            grpc_host=weaviate_url.replace("http://", "").replace("https://", "").split(":")[0],
            grpc_port=50051,
            grpc_secure=False,
            headers=headers
        )
    else:
        client = weaviate.connect_to_local(headers=headers)
        
    try:
        # Delete existing collections (for clean slate)
        # Uncomment these lines to reset schema
        client.collections.delete("TheologicalEntity")
        client.collections.delete("CommentaryChunk")
        
        # 1. TheologicalEntity
        if not client.collections.exists("TheologicalEntity"):
            client.collections.create(
                name="TheologicalEntity",
                description="Entities extracted from Gill's Commentary",
                properties=[
                    Property(
                        name="name", 
                        data_type=DataType.TEXT,
                        description="Entity name as it appears",
                        vectorize_property_name=False
                    ),
                    Property(
                        name="category", 
                        data_type=DataType.TEXT,
                        description="Entity Category (e.g., BiblicalFigure)",
                        skip_vectorization=True
                    ),
                    Property(
                        name="normalized_name", 
                        data_type=DataType.TEXT, 
                        description="Normalized form for deduplication",
                        skip_vectorization=True
                    )
                ]
            )
            print("✓ Created TheologicalEntity collection")

        # 2. CommentaryChunk
        if not client.collections.exists("CommentaryChunk"):
            client.collections.create(
                name="CommentaryChunk",
                description="Commentary content for a specific verse",
                # Configure Vectorizer (assuming using text2vec-transformers or openai)
                vectorizer_config=Configure.Vectorizer.text2vec_transformers(),
                properties=[
                    Property(
                        name="content", 
                        data_type=DataType.TEXT,
                        description="Full commentary text for this verse"
                    ),
                    Property(
                        name="verse_ref", 
                        data_type=DataType.TEXT,
                        description="Verse reference (e.g., 'GEN 46:06')",
                        skip_vectorization=True
                    ),
                    Property(
                        name="book", 
                        data_type=DataType.TEXT,
                        description="Book name (e.g., 'GENESIS')",
                        skip_vectorization=True
                    ),
                    Property(
                        name="chapter", 
                        data_type=DataType.INT,
                        description="Chapter number",
                        skip_vectorization=True
                    ),
                    Property(
                        name="volume", 
                        data_type=DataType.INT,
                        skip_vectorization=True
                    ),
                    Property(
                        name="page_number", 
                        data_type=DataType.INT,
                        skip_vectorization=True
                    ),
                    Property(
                        name="original_text_snippet", 
                        data_type=DataType.TEXT,
                        description="Hebrew/Greek snippet",
                        skip_vectorization=True
                    ),
                    Property(
                        name="scan_json", 
                        data_type=DataType.TEXT,
                        description="Serialized highlight box JSON",
                        skip_vectorization=True
                    ),
                    Property(
                        name="sentence_data",
                        data_type=DataType.OBJECT_ARRAY,
                        description="Sentence-level segmentation",
                        nested_properties=[
                            Property(name="sentence_id", data_type=DataType.TEXT),
                            Property(name="text", data_type=DataType.TEXT),
                            Property(name="index", data_type=DataType.INT)
                        ]
                    ),
                    Property(
                        name="footnotes",
                        data_type=DataType.TEXT_ARRAY,
                        description="Extracted footnotes related to this chunk",
                        skip_vectorization=True
                    )
                ],
                references=[
                    ReferenceProperty(
                        name="mentions_entity",
                        target_collection="TheologicalEntity",
                        description="Entities mentioned in this commentary chunk"
                    )
                ]
            )
            print("✓ Created CommentaryChunk collection")
            
        print("\n✅ Weaviate schema setup complete!")
        print(f"Collections: {client.collections.list_all()}")
        
    finally:
        client.close()

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    setup_weaviate_schema()
