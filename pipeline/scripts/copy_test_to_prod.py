#!/usr/bin/env python3
"""
Copy CommentaryChunk + TheologicalEntity from test Weaviate to prod Weaviate
via the REST/gRPC API, bypassing the backup/restore path.

We fell back to this because test's S3 backup contains a corrupt HNSW snapshot
segment from April that fails to inflate during restore on prod. Reads via
iterator() bypass HNSW entirely (they hit the object store), so streaming
copy gets us a clean prod populated with test's current vectors.

Steps:
  1. Connect to test + prod
  2. Drop prod's CommentaryChunk + TheologicalEntity classes
  3. Recreate prod schema in the ADR-0005 form (search_key + categories)
  4. Stream TheologicalEntity from test -> prod with vectors
  5. Stream CommentaryChunk from test -> prod with vectors (refs deferred)
  6. Stream mentions_entity refs from test -> prod

Required env:
  TEST_WEAVIATE_URL          e.g. http://192.168.1.54:80
  TEST_WEAVIATE_GRPC_HOST    e.g. 192.168.1.53
  TEST_WEAVIATE_GRPC_PORT    e.g. 50051
  PROD_WEAVIATE_URL          e.g. http://192.168.1.52:80
  PROD_WEAVIATE_GRPC_HOST    e.g. 192.168.1.51
  PROD_WEAVIATE_GRPC_PORT    e.g. 50051

Optional:
  COPY_BATCH_SIZE  (default 200)
  SKIP_SCHEMA_RESET  (set to 1 to skip step 2-3; resume after partial run)
  RESUME            (set to 1 to skip schema reset AND skip objects already on prod)
  DRY_RUN          (set to 1: read-only, counts test objects + refs, does not touch prod)
  READ_VIA_REST    (set to 1 to read from test via REST instead of gRPC iterator;
                    use when gRPC fails with "Exception deserializing response" on a
                    specific object whose content trips the protobuf serializer)
"""

import logging
import os
import sys
import time
from typing import Iterable

import requests
import weaviate
from weaviate.classes.config import (
    Configure,
    DataType,
    Property,
    ReferenceProperty,
    Tokenization,
)
from weaviate.classes.init import AdditionalConfig, Timeout
from weaviate.classes.query import QueryReference

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("copy")


def _connect(role: str) -> weaviate.WeaviateClient:
    url = os.environ[f"{role}_WEAVIATE_URL"]
    grpc_host = os.environ[f"{role}_WEAVIATE_GRPC_HOST"]
    grpc_port = int(os.environ[f"{role}_WEAVIATE_GRPC_PORT"])
    http_host = url.replace("http://", "").replace("https://", "").split(":")[0]
    http_port = int(url.split(":")[-1]) if ":" in url.replace("http://", "").replace("https://", "") else 80
    log.info(f"{role}: http={http_host}:{http_port} grpc={grpc_host}:{grpc_port}")
    return weaviate.connect_to_custom(
        http_host=http_host,
        http_port=http_port,
        http_secure=url.startswith("https"),
        grpc_host=grpc_host,
        grpc_port=grpc_port,
        grpc_secure=url.startswith("https"),
        skip_init_checks=True,
        # Default grpc deadlines are too tight for include_vector reads + bulk
        # batch inserts. Bump generously; reads/writes are LAN-bound, not slow.
        additional_config=AdditionalConfig(
            timeout=Timeout(init=30, query=300, insert=300),
        ),
    )


def _create_schema(prod: weaviate.WeaviateClient) -> None:
    """Drop and recreate prod's two collections in the ADR-0005 shape.
    Order matters: CommentaryChunk references TheologicalEntity, so drop chunks
    first and create entities first.
    """
    for name in ("CommentaryChunk", "TheologicalEntity"):
        if prod.collections.exists(name):
            log.info(f"dropping prod.{name}")
            prod.collections.delete(name)

    log.info("creating prod.TheologicalEntity")
    prod.collections.create(
        name="TheologicalEntity",
        description="Entities extracted from Gill's Commentary",
        vectorizer_config=Configure.Vectorizer.none(),
        properties=[
            Property(name="name", data_type=DataType.TEXT, vectorize_property_name=False),
            Property(
                name="search_key",
                data_type=DataType.TEXT,
                skip_vectorization=True,
                tokenization=Tokenization.FIELD,
            ),
            Property(name="description", data_type=DataType.TEXT),
            Property(
                name="category",
                data_type=DataType.TEXT,
                skip_vectorization=True,
                tokenization=Tokenization.FIELD,
            ),
            Property(
                name="categories",
                data_type=DataType.TEXT_ARRAY,
                skip_vectorization=True,
                tokenization=Tokenization.FIELD,
            ),
            Property(
                name="normalized_name",
                data_type=DataType.TEXT,
                skip_vectorization=True,
                tokenization=Tokenization.FIELD,
            ),
            Property(
                name="biblical_era",
                data_type=DataType.TEXT,
                skip_vectorization=True,
                tokenization=Tokenization.FIELD,
            ),
            Property(name="role", data_type=DataType.TEXT),
        ],
    )

    log.info("creating prod.CommentaryChunk")
    prod.collections.create(
        name="CommentaryChunk",
        description="Commentary content for a specific verse",
        vectorizer_config=Configure.Vectorizer.none(),
        properties=[
            Property(name="content", data_type=DataType.TEXT),
            Property(name="lemma", data_type=DataType.TEXT, skip_vectorization=True),
            Property(
                name="verse_ref",
                data_type=DataType.TEXT,
                skip_vectorization=True,
                tokenization=Tokenization.FIELD,
            ),
            Property(
                name="scripture_refs",
                data_type=DataType.TEXT_ARRAY,
                skip_vectorization=True,
                index_filterable=False,
            ),
            Property(name="book", data_type=DataType.TEXT, skip_vectorization=True),
            Property(name="chapter", data_type=DataType.INT, skip_vectorization=True),
            Property(name="volume", data_type=DataType.INT, skip_vectorization=True),
            Property(name="page_number", data_type=DataType.INT, skip_vectorization=True),
            Property(
                name="original_text_snippet",
                data_type=DataType.TEXT,
                skip_vectorization=True,
            ),
            Property(
                name="scan_json",
                data_type=DataType.TEXT,
                skip_vectorization=True,
                index_filterable=False,
                index_searchable=False,
            ),
            Property(
                name="sentence_data",
                data_type=DataType.TEXT,
                skip_vectorization=True,
                index_filterable=False,
                index_searchable=False,
            ),
            Property(name="footnotes", data_type=DataType.TEXT_ARRAY, skip_vectorization=True),
            Property(
                name="needs_boundary_resolution",
                data_type=DataType.BOOL,
                skip_vectorization=True,
            ),
            Property(name="entities", data_type=DataType.TEXT_ARRAY, index_searchable=True),
        ],
        references=[
            ReferenceProperty(
                name="mentions_entity",
                target_collection="TheologicalEntity",
            )
        ],
    )


def _vector_of(obj) -> list:
    """Iterator returns vectors as {'default': [...]}; unwrap to a flat list."""
    v = obj.vector
    if isinstance(v, dict):
        return v.get("default") or v.get("") or next(iter(v.values()), None)
    return v


class _RestObj:
    """Duck-typed shim that mimics the parts of weaviate-client's Object that
    _copy_objects touches, so REST iteration can plug into the same code."""

    __slots__ = ("uuid", "properties", "vector")

    def __init__(self, uuid: str, properties: dict, vector: list | None) -> None:
        self.uuid = uuid
        self.properties = properties
        self.vector = vector


def _iter_via_rest(test_url: str, class_name: str) -> Iterable[_RestObj]:
    """Stream objects from test via the REST /v1/objects cursor API. Bypasses
    the gRPC path entirely, which is needed when a specific object's content
    trips the gRPC protobuf serializer (StatusCode.INTERNAL / "Exception
    deserializing response").
    """
    after: str | None = None
    while True:
        params = {
            "class": class_name,
            "limit": 25,
            "include": "vector",
        }
        if after is not None:
            params["after"] = after
        r = requests.get(f"{test_url}/v1/objects", params=params, timeout=60)
        r.raise_for_status()
        body = r.json()
        objs = body.get("objects") or []
        if not objs:
            return
        for o in objs:
            yield _RestObj(
                uuid=o["id"],
                properties=o.get("properties") or {},
                vector=o.get("vector"),
            )
        after = objs[-1]["id"]


def _existing_prod_uuids(prod_client, name: str) -> set[str]:
    col = prod_client.collections.get(name)
    log.info(f"querying existing prod.{name} UUIDs for resume...")
    seen: set[str] = set()
    t0 = time.time()
    for obj in col.iterator(include_vector=False, cache_size=200):
        seen.add(str(obj.uuid))
    log.info(f"  prod.{name}: {len(seen)} existing in {time.time() - t0:.1f}s")
    return seen


def _copy_objects(
    src_client,
    dst_client,
    name: str,
    batch_size: int,
    resume: bool,
    read_via_rest: bool,
    test_url: str,
) -> int:
    dst = dst_client.collections.get(name)
    skip_uuids: set[str] = _existing_prod_uuids(dst_client, name) if resume else set()
    total = 0
    skipped = 0
    t0 = time.time()
    # cache_size=10 chosen because vectors are 4096-dim float (16KB each).
    # Larger pages with include_vector trip a server-side deadline on test.
    if read_via_rest:
        log.info(f"  {name}: reading via REST (gRPC bypass)")
        source = _iter_via_rest(test_url, name)
    else:
        source = src_client.collections.get(name).iterator(
            include_vector=True, cache_size=10
        )
    with dst.batch.fixed_size(batch_size=batch_size) as batch:
        for obj in source:
            if str(obj.uuid) in skip_uuids:
                skipped += 1
                continue
            batch.add_object(
                uuid=obj.uuid,
                properties=obj.properties,
                vector=_vector_of(obj),
            )
            total += 1
            if (total + skipped) % 1000 == 0:
                log.info(
                    f"  {name}: {total} copied / {skipped} skipped "
                    f"({total / max(time.time() - t0, 0.001):.0f}/s)"
                )
    failed = dst.batch.failed_objects
    if failed:
        log.error(f"{name}: {len(failed)} object failures; sample: {failed[0]}")
    log.info(
        f"{name}: done — {total} copied, {skipped} skipped in {time.time() - t0:.1f}s"
    )
    return total


def _copy_refs(src_client, dst_client, batch_size: int) -> int:
    src = src_client.collections.get("CommentaryChunk")
    dst = dst_client.collections.get("CommentaryChunk")
    total = 0
    chunks_with_refs = 0
    t0 = time.time()
    with dst.batch.fixed_size(batch_size=batch_size) as batch:
        for obj in src.iterator(
            return_references=QueryReference(link_on="mentions_entity"),
            cache_size=50,
        ):
            refs = obj.references.get("mentions_entity") if obj.references else None
            if not refs or not refs.objects:
                continue
            chunks_with_refs += 1
            for ref in refs.objects:
                batch.add_reference(
                    from_uuid=obj.uuid,
                    from_collection="CommentaryChunk",
                    from_property="mentions_entity",
                    to=ref.uuid,
                )
                total += 1
            if chunks_with_refs % 500 == 0:
                log.info(
                    f"  refs: {chunks_with_refs} chunks, {total} edges "
                    f"({total / (time.time() - t0):.0f}/s)"
                )
    failed = dst.batch.failed_references
    if failed:
        log.error(f"refs: {len(failed)} edge failures; sample: {failed[0]}")
    log.info(f"refs: done — {total} edges in {time.time() - t0:.1f}s")
    return total


def _dry_run(test: weaviate.WeaviateClient) -> None:
    """Read-only pass: streams every object from test WITH vectors so we
    prove the entire dataset is readable before the real run drops prod's
    schema. Touches only TEST, never PROD.

    Runs the same iterator path the real copy uses (include_vector=True,
    cache_size=10) so any per-page deadline or corrupt-object surfaces here
    instead of mid-copy when prod is half-empty.
    """
    for name in ("TheologicalEntity", "CommentaryChunk"):
        col = test.collections.get(name)
        n = 0
        bad_vec = 0
        vec_dim = None
        t0 = time.time()
        for obj in col.iterator(include_vector=True, cache_size=10):
            n += 1
            v = _vector_of(obj)
            if not v:
                bad_vec += 1
            elif vec_dim is None:
                vec_dim = len(v)
            if n % 1000 == 0:
                log.info(f"  {name}: read {n} ({n / (time.time() - t0):.0f}/s)")
        log.info(
            f"{name}: total={n} vec_dim={vec_dim} bad_vec={bad_vec} "
            f"in {time.time() - t0:.1f}s"
        )

    chunks = test.collections.get("CommentaryChunk")
    chunks_with_refs = 0
    total_refs = 0
    no_ref_chunks = 0
    t0 = time.time()
    for obj in chunks.iterator(
        return_references=QueryReference(link_on="mentions_entity")
    ):
        refs = obj.references.get("mentions_entity") if obj.references else None
        if refs and refs.objects:
            chunks_with_refs += 1
            total_refs += len(refs.objects)
        else:
            no_ref_chunks += 1
    log.info(
        f"refs: chunks_with_refs={chunks_with_refs} no_ref_chunks={no_ref_chunks} "
        f"total_edges={total_refs} in {time.time() - t0:.1f}s"
    )


def main() -> int:
    batch_size = int(os.getenv("COPY_BATCH_SIZE", "200"))
    resume = os.getenv("RESUME", "0") == "1"
    skip_schema = resume or os.getenv("SKIP_SCHEMA_RESET", "0") == "1"
    dry_run = os.getenv("DRY_RUN", "0") == "1"
    read_via_rest = os.getenv("READ_VIA_REST", "0") == "1"
    test_url = os.environ["TEST_WEAVIATE_URL"]

    test = _connect("TEST")
    prod = None if dry_run else _connect("PROD")
    try:
        log.info("test classes: %s", [c for c in test.collections.list_all().keys()])
        if dry_run:
            log.info("DRY_RUN=1: read-only pass, prod will not be touched")
            _dry_run(test)
            return 0

        log.info("prod classes (before): %s", [c for c in prod.collections.list_all().keys()])

        if skip_schema:
            log.info("schema reset skipped (RESUME or SKIP_SCHEMA_RESET set)")
        else:
            _create_schema(prod)

        log.info("=== copying TheologicalEntity ===")
        _copy_objects(test, prod, "TheologicalEntity", batch_size, resume, read_via_rest, test_url)

        log.info("=== copying CommentaryChunk (objects only) ===")
        _copy_objects(test, prod, "CommentaryChunk", batch_size, resume, read_via_rest, test_url)

        log.info("=== copying mentions_entity references ===")
        _copy_refs(test, prod, batch_size)

        log.info("prod classes (after): %s", [c for c in prod.collections.list_all().keys()])
        return 0
    finally:
        test.close()
        if prod is not None:
            prod.close()


if __name__ == "__main__":
    sys.exit(main())
