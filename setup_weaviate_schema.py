#!/usr/bin/env python3
"""
Weaviate Schema Setup for Gill Commentary Knowledge Graph.

This script initializes the Weaviate collections for:
1. TheologicalEntity - Knowledge graph nodes
2. CommentaryChunk - Searchable commentary content with sentence granularity
"""

import weaviate
import weaviate.classes as wvc
from weaviate.classes.config import Configure, Property, DataType, ReferenceProperty
import os
from dotenv import load_dotenv

load_dotenv()

def setup_weaviate_schema():
    """Initialize Weaviate collections for Gill Commentary."""
    
    # Connect to Weaviate
    weaviate_url = os.getenv("WEAVIATE_URL")
    weaviate_api_key = os.getenv("WEAVIATE_API_KEY")
    
    if weaviate_url:
        print(f"Connecting to Weaviate at {weaviate_url}")
        headers = {}
        if weaviate_api_key:
            headers["X-OpenAI-Api-Key"] = os.getenv("OPENROUTER_API_KEY") # Pass LLM key if needed for modules
            headers["X-OpenAI-BaseURL"] = "https://openrouter.ai/api/v1"
            
        client = weaviate.connect_to_custom(
            http_host=weaviate_url.replace("http://", "").replace("https://", "").split(":")[0],
            http_port=int(weaviate_url.split(":")[-1]) if ":" in weaviate_url else 80,
            http_secure=weaviate_url.startswith("https"),
            grpc_host=weaviate_url.replace("http://", "").replace("https://", "").split(":")[0],
            grpc_port=50051, # specific GRPC port usually needed
            grpc_secure=weaviate_url.startswith("https"),
            headers=headers,
            auth_credentials=weaviate.auth.AuthApiKey(weaviate_api_key) if weaviate_api_key else None
        )
    else:
        print("Connecting to local Weaviate at localhost:8080")
        client = weaviate.connect_to_local(
            host="localhost",
            port=8080,
            grpc_port=50051
        )
    
    try:
        print("Connected to Weaviate")
        
        # Delete existing collections if they exist (for clean slate)
        if client.collections.exists("TheologicalEntity"):
            client.collections.delete("TheologicalEntity")
            print("Deleted existing TheologicalEntity collection")
            
        if client.collections.exists("CommentaryChunk"):
            client.collections.delete("CommentaryChunk")
            print("Deleted existing CommentaryChunk collection")
        
        # Create TheologicalEntity collection (Knowledge Graph Nodes)
        theological_entity = client.collections.create(
            name="TheologicalEntity",
            description="Entities extracted from Gill's Commentary (people, places, doctrines, etc.)",
            vectorizer_config=Configure.Vectorizer.none(),  # No vectorization needed for entities
            properties=[
                Property(
                    name="name",
                    data_type=DataType.TEXT,
                    description="The entity name as it appears in the text"
                ),
                Property(
                    name="category",
                    data_type=DataType.TEXT,
                    description="Entity category (Doctrine, BiblicalFigure, Location, etc.)"
                ),
                Property(
                    name="normalized_name",
                    data_type=DataType.TEXT,
                    description="Normalized form for deduplication (e.g., 'Christ' -> 'Jesus Christ')"
                ),
            ]
        )
        print("✓ Created TheologicalEntity collection")
        
        # Create CommentaryChunk collection (Searchable Content)
        commentary_chunk = client.collections.create(
            name="CommentaryChunk",
            description="Searchable commentary chunks with verse-level granularity and sentence segmentation",
            vectorizer_config=Configure.Vectorizer.text2vec_transformers(
                vectorize_collection_name=False
            ),
            properties=[
                Property(
                    name="content",
                    data_type=DataType.TEXT,
                    description="The full commentary text for this verse",
                    vectorize_property_name=False,
                    skip_vectorization=False  # This gets vectorized
                ),
                Property(
                    name="verse_ref",
                    data_type=DataType.TEXT,
                    description="Verse reference (e.g., 'GEN 46:06')",
                    vectorize_property_name=False,
                    skip_vectorization=True
                ),
                Property(
                    name="book",
                    data_type=DataType.TEXT,
                    description="Book name (e.g., 'GENESIS')",
                    vectorize_property_name=False,
                    skip_vectorization=True
                ),
                Property(
                    name="chapter",
                    data_type=DataType.INT,
                    description="Chapter number",
                    vectorize_property_name=False,
                    skip_vectorization=True
                ),
                Property(
                    name="volume",
                    data_type=DataType.INT,
                    description="Volume number (parsed from image filename)",
                    vectorize_property_name=False,
                    skip_vectorization=True
                ),
                Property(
                    name="page_number",
                    data_type=DataType.INT,
                    description="Page number (parsed from image filename)",
                    vectorize_property_name=False,
                    skip_vectorization=True
                ),
                Property(
                    name="original_text_snippet",
                    data_type=DataType.TEXT,
                    description="Hebrew or Greek text snippet from metadata",
                    vectorize_property_name=False,
                    skip_vectorization=True
                ),
                Property(
                    name="scan_json",
                    data_type=DataType.TEXT,
                    description="Serialized JSON of highlight_box for frontend rendering",
                    vectorize_property_name=False,
                    skip_vectorization=True
                ),
                Property(
                    name="sentence_data",
                    data_type=DataType.OBJECT_ARRAY,
                    description="Sentence-level segmentation with IDs",
                    nested_properties=[
                        Property(name="sentence_id", data_type=DataType.TEXT),
                        Property(name="text", data_type=DataType.TEXT),
                        Property(name="index", data_type=DataType.INT)
                    ],
                    vectorize_property_name=False,
                    skip_vectorization=True
                ),
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
    setup_weaviate_schema()
