#!/usr/bin/env python3
"""
Non-destructive schema evolution for Weaviate.

Unlike setup_weaviate_schema.py (which deletes-and-recreates collections,
losing all data), this script adds new properties to existing collections
without disturbing the data. Idempotent: safe to re-run.

Currently adds the search_key + categories properties to TheologicalEntity
as defined in ADR-0005 Phase 1.

Usage:
    python evolve_schema.py
"""

import os
import sys

import weaviate
import weaviate.classes as wvc
from dotenv import load_dotenv
from weaviate.classes.config import Property, DataType, Tokenization


def connect_to_weaviate():
    weaviate_url = os.getenv("WEAVIATE_URL", "localhost")
    headers = {}
    if os.getenv("OPENROUTER_API_KEY"):
        headers["X-OpenAI-Api-Key"] = os.getenv("OPENROUTER_API_KEY")

    if weaviate_url != "localhost":
        if "://" in weaviate_url:
            from urllib.parse import urlparse
            parsed = urlparse(weaviate_url)
            http_host = parsed.hostname
            http_port = parsed.port or int(os.getenv("WEAVIATE_PORT", 80))
            secure = weaviate_url.startswith("https")
        else:
            if ":" in weaviate_url:
                http_host = weaviate_url.split(":")[0]
                try:
                    http_port = int(weaviate_url.split(":")[-1])
                except ValueError:
                    http_port = int(os.getenv("WEAVIATE_PORT", 80))
            else:
                http_host = weaviate_url
                http_port = int(os.getenv("WEAVIATE_PORT", 80))
            secure = False

        grpc_host = os.getenv("WEAVIATE_GRPC_HOST", http_host)
        grpc_port = int(os.getenv("WEAVIATE_GRPC_PORT", "50051"))

        print(f"Connecting to Weaviate at {http_host}:{http_port}, gRPC {grpc_host}:{grpc_port}")
        return weaviate.connect_to_custom(
            http_host=http_host,
            http_port=http_port,
            http_secure=secure,
            grpc_host=grpc_host,
            grpc_port=grpc_port,
            grpc_secure=secure,
            headers=headers,
            skip_init_checks=True,
        )
    return weaviate.connect_to_local(headers=headers)


# Properties that should exist on TheologicalEntity. Each tuple is
# (Property definition, property_name) so we can check existence by name.
ENTITY_PROPERTIES_TO_ENSURE = [
    Property(
        name="search_key",
        data_type=DataType.TEXT,
        description=(
            "Deterministic canonical key for matching: lowercased + alphanumeric-only "
            "form of name. Used by get_relevant_entities for substring lookup. "
            "Populated by code, never by the LLM. See ADR-0005."
        ),
        skip_vectorization=True,
        tokenization=Tokenization.FIELD,
    ),
    Property(
        name="categories",
        data_type=DataType.TEXT_ARRAY,
        description=(
            "All category labels the LLM has assigned to this entity across pages "
            "(e.g. ['TypeOrSymbol', 'OriginalWord']). Same biblical reality can be "
            "perceived multiple ways; accumulate rather than fork. See ADR-0005."
        ),
        skip_vectorization=True,
        tokenization=Tokenization.FIELD,
    ),
]


def ensure_properties(collection, target_properties):
    """Add each property in target_properties to the collection if it does not already exist."""
    existing = {p.name for p in collection.config.get().properties}
    added = []
    skipped = []
    for prop in target_properties:
        if prop.name in existing:
            skipped.append(prop.name)
            continue
        print(f"  Adding property: {prop.name}")
        collection.config.add_property(prop)
        added.append(prop.name)
    return added, skipped


def main() -> int:
    load_dotenv()
    client = connect_to_weaviate()
    try:
        if not client.collections.exists("TheologicalEntity"):
            print("ERROR: TheologicalEntity collection does not exist.")
            print("Run setup_weaviate_schema.py first to create the base schema.")
            return 1

        print("\nEvolving TheologicalEntity collection...")
        entities = client.collections.get("TheologicalEntity")
        added, skipped = ensure_properties(entities, ENTITY_PROPERTIES_TO_ENSURE)

        print("\nResult:")
        if added:
            print(f"  Added: {added}")
        if skipped:
            print(f"  Already present (skipped): {skipped}")

        print(
            "\nNote: existing entities now have these properties as null/empty. "
            "Run backfill_entity_search_keys.py to populate them."
        )
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
