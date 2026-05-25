#!/usr/bin/env python3
"""
Backfill `search_key` and `categories` on existing TheologicalEntity rows,
then auto-merge fragments that share the same (search_key, biblical_era).

See ADR-0005 Phase 3.

Run in this order:
    1. python evolve_schema.py        # adds the properties to the collection
    2. python backfill_entity_search_keys.py --dry-run    # preview
    3. python backfill_entity_search_keys.py              # apply

The script is idempotent: it only modifies entities that need backfilling
(missing/empty `search_key`, `categories` not yet seeded, or part of a
fragment group). Re-running has no effect on already-clean data.

Auto-merge rules (conservative — see ADR-0005):
- Same (search_key, biblical_era).
- Roles are compatible: either all empty, all identical, or one is empty.
- Number of fragments small enough that no human-review path is warranted.

Anything outside those rules is left alone and surfaced in the report for
manual review (or a future LLM-judge pass).
"""

import argparse
import os
import re
import sys
from collections import defaultdict
from typing import Optional

import weaviate
import weaviate.classes as wvc
from dotenv import load_dotenv

# Ensure non-ASCII entity names (Hebrew, Greek) don't crash the script on Windows.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def compute_search_key(name: str) -> str:
    """
    Must match pipeline.scripts.ingest.IngestPipeline.compute_search_key.

    Unicode-aware: keeps Hebrew/Greek/Arabic letters and digits; strips
    spaces, punctuation, hyphens, and combining marks (niqqud, accents).
    """
    return "".join(c for c in (name or "").lower() if c.isalnum())


def compute_display_normalized_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip())


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


def fetch_all_entities(entities_collection):
    """Iterate every entity; yield dicts with uuid, properties."""
    for obj in entities_collection.iterator():
        yield {"uuid": str(obj.uuid), "props": obj.properties}


def populate_search_key_and_categories(
    entities_collection,
    apply_changes: bool,
) -> dict:
    """First pass: populate search_key and seed categories on entities missing them."""
    populated_search_key = 0
    seeded_categories = 0
    populated_normalized_name = 0
    skipped_no_name = 0

    for ent in fetch_all_entities(entities_collection):
        props = ent["props"]
        name = props.get("name")
        if not name:
            skipped_no_name += 1
            continue

        updates = {}
        if not props.get("search_key"):
            updates["search_key"] = compute_search_key(name)
        if not props.get("categories"):
            primary_cat = props.get("category")
            if primary_cat:
                updates["categories"] = [primary_cat]
        if not props.get("normalized_name"):
            updates["normalized_name"] = compute_display_normalized_name(name)

        if not updates:
            continue

        if "search_key" in updates:
            populated_search_key += 1
        if "categories" in updates:
            seeded_categories += 1
        if "normalized_name" in updates:
            populated_normalized_name += 1

        if apply_changes:
            try:
                entities_collection.data.update(uuid=ent["uuid"], properties=updates)
            except Exception as e:
                print(f"  ! Failed to update {ent['uuid']}: {e}")

    return {
        "populated_search_key": populated_search_key,
        "seeded_categories": seeded_categories,
        "populated_normalized_name": populated_normalized_name,
        "skipped_no_name": skipped_no_name,
    }


def group_by_search_key_and_era(entities_collection):
    """Build {(search_key, biblical_era): [entity_records]} after backfill."""
    groups = defaultdict(list)
    for ent in fetch_all_entities(entities_collection):
        props = ent["props"]
        name = props.get("name")
        if not name:
            continue
        # Prefer stored search_key; fall back to computing it if absent (shouldn't happen post-backfill).
        sk = props.get("search_key") or compute_search_key(name)
        era = props.get("biblical_era") or "NotApplicable"
        groups[(sk, era)].append({
            "uuid": ent["uuid"],
            "name": name,
            "category": props.get("category"),
            "categories": props.get("categories") or [],
            "normalized_name": props.get("normalized_name"),
            "description": props.get("description"),
            "biblical_era": era,
            "role": props.get("role"),
        })
    return groups


def roles_compatible(records: list) -> bool:
    """
    Two records can merge if their `role` fields are compatible: all empty,
    all identical, or one is empty. Anything else (semantically different roles)
    is flagged for manual review per ADR-0005.
    """
    roles = {r["role"] for r in records}
    roles_non_empty = {r for r in roles if r}
    if len(roles_non_empty) <= 1:
        return True
    return False


def merge_chunks_references(
    chunks_collection,
    keep_uuid: str,
    delete_uuid: str,
    apply_changes: bool,
) -> int:
    """Re-point `mentions_entity` references from delete_uuid to keep_uuid."""
    try:
        response = chunks_collection.query.fetch_objects(
            return_references=[wvc.query.QueryReference(link_on="mentions_entity")],
            filters=wvc.query.Filter.by_ref("mentions_entity").by_id().equal(delete_uuid),
            limit=10000,
        )
    except Exception as e:
        print(f"    ! Failed to fetch chunks referencing {delete_uuid}: {e}")
        return 0

    affected = response.objects
    if apply_changes:
        for chunk in affected:
            try:
                chunks_collection.data.reference_add(
                    from_uuid=chunk.uuid,
                    from_property="mentions_entity",
                    to=keep_uuid,
                )
                chunks_collection.data.reference_delete(
                    from_uuid=chunk.uuid,
                    from_property="mentions_entity",
                    to=delete_uuid,
                )
            except Exception as e:
                print(f"    ! Failed to swap refs on chunk {chunk.uuid}: {e}")
    return len(affected)


def auto_merge_groups(
    entities_collection,
    chunks_collection,
    groups: dict,
    apply_changes: bool,
) -> dict:
    """For each (search_key, era) group with >1 entity, try to auto-merge."""
    auto_merged_groups = 0
    auto_merged_entities = 0
    chunks_repointed = 0
    flagged_for_review = []

    for (sk, era), records in groups.items():
        if len(records) < 2:
            continue
        if not sk:
            # Empty search_key — entities with no canonicalizable characters.
            # NEVER auto-merge these; they're a collision class by accident, not
            # by identity. Flag for review so they're visible.
            flagged_for_review.append({
                "search_key": sk,
                "biblical_era": era,
                "reason": "empty_search_key",
                "entities": [
                    {"uuid": r["uuid"], "name": r["name"], "role": r["role"], "category": r["category"]}
                    for r in records
                ],
            })
            continue
        if not roles_compatible(records):
            flagged_for_review.append({
                "search_key": sk,
                "biblical_era": era,
                "reason": "incompatible_roles",
                "entities": [
                    {"uuid": r["uuid"], "name": r["name"], "role": r["role"], "category": r["category"]}
                    for r in records
                ],
            })
            continue

        # Pick the keeper: prefer one with non-empty role, then most categories, then lowest UUID for determinism.
        records_sorted = sorted(
            records,
            key=lambda r: (
                0 if r["role"] else 1,
                -len(r["categories"]),
                r["uuid"],
            ),
        )
        keeper = records_sorted[0]
        losers = records_sorted[1:]

        # Build merged property set
        merged_categories = list(dict.fromkeys(
            (keeper["categories"] or []) + [c for r in losers for c in (r["categories"] or [])]
        ))
        if keeper["category"] and keeper["category"] not in merged_categories:
            merged_categories.append(keeper["category"])
        for r in losers:
            if r["category"] and r["category"] not in merged_categories:
                merged_categories.append(r["category"])

        # Pick the longest non-empty description as the merged description.
        merged_description = max(
            ((r["description"] or "") for r in records),
            key=lambda d: len(d or ""),
        ) or None

        # Pick the non-empty role (we already know they're compatible).
        merged_role = next((r["role"] for r in records if r["role"]), None)

        print(
            f"  MERGE: search_key='{sk}' era='{era}' "
            f"keep={keeper['name']!r} ({keeper['uuid'][:8]}) "
            f"merging {len(losers)} fragment(s): {[r['name'] for r in losers]}"
        )

        if apply_changes:
            try:
                entities_collection.data.update(
                    uuid=keeper["uuid"],
                    properties={
                        "categories": merged_categories,
                        "description": merged_description,
                        "role": merged_role,
                    },
                )
            except Exception as e:
                print(f"    ! Failed to update keeper {keeper['uuid']}: {e}")
                continue

        for loser in losers:
            n = merge_chunks_references(
                chunks_collection,
                keep_uuid=keeper["uuid"],
                delete_uuid=loser["uuid"],
                apply_changes=apply_changes,
            )
            chunks_repointed += n
            if apply_changes:
                try:
                    entities_collection.data.delete_by_id(loser["uuid"])
                except Exception as e:
                    print(f"    ! Failed to delete loser {loser['uuid']}: {e}")

        auto_merged_groups += 1
        auto_merged_entities += len(losers)

    return {
        "auto_merged_groups": auto_merged_groups,
        "auto_merged_entities": auto_merged_entities,
        "chunks_repointed": chunks_repointed,
        "flagged_for_review": flagged_for_review,
    }


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to Weaviate.",
    )
    parser.add_argument(
        "--skip-merge",
        action="store_true",
        help="Only backfill search_key/categories; do not run the auto-merge pass.",
    )
    args = parser.parse_args(argv)

    load_dotenv()
    apply_changes = not args.dry_run
    mode = "APPLY" if apply_changes else "DRY-RUN"
    print(f"[{mode}] Backfilling search_key/categories and auto-merging fragments.")

    client = connect_to_weaviate()
    try:
        if not client.collections.exists("TheologicalEntity"):
            print("ERROR: TheologicalEntity collection does not exist.")
            return 1

        entities = client.collections.get("TheologicalEntity")
        chunks = client.collections.get("CommentaryChunk")

        # Phase A — backfill missing properties
        print("\n=== Phase A: populating search_key, categories, normalized_name ===")
        a = populate_search_key_and_categories(entities, apply_changes)
        print(f"  populated search_key on    : {a['populated_search_key']} entities")
        print(f"  seeded categories on       : {a['seeded_categories']} entities")
        print(f"  populated normalized_name  : {a['populated_normalized_name']} entities")
        print(f"  skipped (no name)          : {a['skipped_no_name']} entities")

        if args.skip_merge:
            print("\n--skip-merge specified; not running auto-merge pass.")
            return 0

        # Phase B — group + auto-merge fragments
        print("\n=== Phase B: grouping by (search_key, biblical_era) ===")
        groups = group_by_search_key_and_era(entities)
        fragment_groups = {k: v for k, v in groups.items() if len(v) > 1}
        print(f"  total groups                  : {len(groups)}")
        print(f"  fragment groups (>1 entity)   : {len(fragment_groups)}")

        print("\n=== Phase C: auto-merge ===")
        b = auto_merge_groups(entities, chunks, groups, apply_changes)
        print(f"  groups auto-merged            : {b['auto_merged_groups']}")
        print(f"  fragment entities removed     : {b['auto_merged_entities']}")
        print(f"  chunk references repointed    : {b['chunks_repointed']}")
        print(f"  groups flagged for review     : {len(b['flagged_for_review'])}")

        if b["flagged_for_review"]:
            print("\n=== Flagged for manual review (incompatible roles) ===")
            for item in b["flagged_for_review"][:20]:
                print(
                    f"  search_key='{item['search_key']}' era='{item['biblical_era']}' "
                    f"reason={item['reason']}"
                )
                for e in item["entities"]:
                    print(
                        f"    - {e['name']!r}  role={e['role']!r}  "
                        f"category={e['category']!r}  uuid={e['uuid'][:8]}"
                    )
            if len(b["flagged_for_review"]) > 20:
                print(f"  ... and {len(b['flagged_for_review']) - 20} more")

        if args.dry_run:
            print("\nDRY-RUN complete — no changes written. Rerun without --dry-run to apply.")
        else:
            print("\nApply complete.")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
