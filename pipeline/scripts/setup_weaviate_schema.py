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
from weaviate.classes.config import Configure, Property, DataType, ReferenceProperty, Tokenization

def setup_weaviate_schema():
    """Initialize Weaviate collections."""
    weaviate_url = os.getenv("WEAVIATE_URL", "localhost")
    weaviate_port = int(os.getenv("WEAVIATE_PORT", 80))
    
    # Connect to Weaviate
    print(f"Connecting to Weaviate at {weaviate_url} (Port {weaviate_port})...")
    headers = {}
    if os.getenv("OPENROUTER_API_KEY"):
         headers["X-OpenAI-Api-Key"] = os.getenv("OPENROUTER_API_KEY")
    
    if weaviate_url != "localhost":
         http_host = weaviate_url.replace("http://", "").replace("https://", "").split(":")[0]
         http_port = int(weaviate_url.split(":")[-1]) if ":" in weaviate_url else 80
         
         grpc_host = os.getenv("WEAVIATE_GRPC_HOST", http_host)
         grpc_port = int(os.getenv("WEAVIATE_GRPC_PORT", "50051"))
         print(f"gRPC Target: {grpc_host}:{grpc_port}")

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
                # Ensure the vectorizer is set (matches your Chunk config)
                vectorizer_config=Configure.Vectorizer.none(),
                properties=[
                    Property(
                        name="name",
                        data_type=DataType.TEXT,
                        description="Entity name as it appears in the source text",
                        vectorize_property_name=False
                        # Default tokenization (word) is good here
                    ),
                    Property(
                        name="search_key",
                        data_type=DataType.TEXT,
                        description=(
                            "Deterministic canonical key for matching: "
                            "lowercased + alphanumeric-only form of name. "
                            "Used by get_relevant_entities for substring lookup. "
                            "Populated by code, never by the LLM. See ADR-0005."
                        ),
                        skip_vectorization=True,
                        tokenization=Tokenization.FIELD
                    ),
                    Property(
                        name="description",
                        data_type=DataType.TEXT,
                        description="Short context extracted by BAML",
                        # We WANT to vectorize this
                    ),
                    Property(
                        name="category",
                        data_type=DataType.TEXT,
                        description=(
                            "Primary entity category (e.g. BiblicalFigure). "
                            "Kept for backward compatibility — new code prefers `categories`."
                        ),
                        skip_vectorization=True,
                        tokenization=Tokenization.FIELD
                    ),
                    Property(
                        name="categories",
                        data_type=DataType.TEXT_ARRAY,
                        description=(
                            "All category labels the LLM has assigned to this entity "
                            "across pages (e.g. ['TypeOrSymbol', 'OriginalWord']). "
                            "Same biblical reality can be perceived multiple ways; "
                            "accumulate rather than fork. See ADR-0005."
                        ),
                        skip_vectorization=True,
                        tokenization=Tokenization.FIELD
                    ),
                    Property(
                        name="normalized_name",
                        data_type=DataType.TEXT,
                        description=(
                            "Human-readable display form, computed deterministically "
                            "by code from `name` (title-case, hyphen-strip). "
                            "Distinct from `search_key`. See ADR-0005."
                        ),
                        skip_vectorization=True,
                        tokenization=Tokenization.FIELD
                    ),
                    Property(
                        name="biblical_era",
                        data_type=DataType.TEXT,
                        description="Era (e.g., OldTestament, NewTestament)",
                        skip_vectorization=True,
                        tokenization=Tokenization.FIELD
                    ),
                    Property(
                        name="role",
                        data_type=DataType.TEXT,
                        description="Disambiguating role (e.g., 'Patriarch')",
                        # Vectorize this so "Husband of Mary" adds meaning!
                    )
                ]
            )
            print("Created TheologicalEntity collection")

        # 2. CommentaryChunk
        if not client.collections.exists("CommentaryChunk"):
            client.collections.create(
                name="CommentaryChunk",
                description="Commentary content for a specific verse",
                # Configure Vectorizer (assuming using text2vec-transformers or openai)
                vectorizer_config=Configure.Vectorizer.none(),
                properties=[
                    Property(
                        name="content", 
                        data_type=DataType.TEXT,
                        description="Full commentary text for this verse"
                    ),
                    Property(
                        name="lemma",
                        data_type=DataType.TEXT,
                        description="The lemma phrases (e.g., 'And he said... ]') extracted from the start of the commentary.",
                        skip_vectorization=True
                    ),
                    Property(
                        name="verse_ref", 
                        data_type=DataType.TEXT,
                        description="Verse reference (e.g., 'GEN 46:06')",
                        tokenization=Tokenization.FIELD,
                        skip_vectorization=True
                    ),
                    Property(
                        name="scripture_refs",
                        data_type=DataType.TEXT_ARRAY,
                        description="Cross-referenced bible verses (e.g. ['ISA_53_06'])",
                        skip_vectorization=True,
                        index_filterable=False # Optimization: unlikely to filter by exact list, but maybe contains? Leave index_filterable=True default is fine for array? 
                        # Actually standard filter is fine for contains.
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
                        skip_vectorization=True,
                        index_filterable=False,
                        index_searchable=False
                    ),
                    Property(
                        name="sentence_data",
                        data_type=DataType.TEXT, # Stored as JSON string (json.dumps on ingest, json.loads on search)
                        description="Serialized sentence-level segmentation JSON",
                        skip_vectorization=True,
                        index_filterable=False,
                        index_searchable=False
                    ),
                    Property(
                        name="footnotes",
                        data_type=DataType.TEXT_ARRAY,
                        description="Extracted footnotes related to this chunk",
                        skip_vectorization=True
                    ),
                    Property(
                        name="needs_boundary_resolution",
                        data_type=DataType.BOOL,
                        description="Flagged true if the LLM encountered a pronoun it could not resolve due to a page boundary cold-start.",
                        skip_vectorization=True
                    ),
                    Property(
                        name="entities",
                        data_type=DataType.TEXT_ARRAY,
                        description="De-normalized entity names for BM25 boosting",
                        index_searchable=True
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
