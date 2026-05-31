import os
import subprocess
import time
from typing import Dict, List

import requests
from dagster import In, Nothing, Out, op, job

# Classes the migration knows about. The backup/restore ops filter this list
# down to whatever each Weaviate side actually contains, so a class added or
# dropped on one side doesn't break the promotion.
KNOWN_CLASSES = ["CommentaryChunk", "TheologicalEntity", "GroupSummary"]


def existing_classes(weaviate_url: str, candidates: List[str]) -> List[str]:
    """Query a Weaviate instance for its schema and return only classes from
    `candidates` that actually exist. Avoids the 422 'Unprocessable Entity'
    response Weaviate returns when a backup/restore include lists a class the
    instance doesn't have.
    """
    schema_url = f"{weaviate_url}/v1/schema"
    response = requests.get(schema_url)
    response.raise_for_status()
    schema = response.json() or {}
    present = {cls.get("class") for cls in schema.get("classes") or []}
    return [c for c in candidates if c in present]


def trigger_and_wait_weaviate_backup(url: str, payload: dict, action: str) -> str:
    """
    Triggers a Weaviate backup or restore operation and polls until completion.

    Args:
        url: The full REST endpoint to POST against.
        payload: The JSON payload for the POST request.
        action: Human-readable action name used in logging / exception messages.

    Returns:
        The backup / snapshot id returned by Weaviate.

    Raises:
        Exception: If the Weaviate operation reports a FAILED status.
    """
    response = requests.post(url, json=payload)
    if not response.ok:
        # Weaviate's 422 bodies tell you *which* class or setting it didn't
        # like. raise_for_status alone drops that, leaving an opaque error.
        raise Exception(
            f"Weaviate {action} POST {url} failed: "
            f"status={response.status_code} body={response.text} "
            f"payload={payload}"
        )
    data = response.json()
    backup_id = data["id"]

    # Weaviate restore status lives at the same URL as the restore trigger.
    # Backup status lives at url/{id}.
    if action == "restore":
        status_url = url
    else:
        status_url = f"{url}/{backup_id}"

    while True:
        status_response = requests.get(status_url)
        status_response.raise_for_status()
        status_data = status_response.json()

        current_status = status_data.get("status")
        if current_status == "SUCCESS":
            return backup_id
        elif current_status == "FAILED":
            raise Exception(
                f"Weaviate {action} FAILED for id '{backup_id}': {status_data}"
            )

        time.sleep(5)


@op
def backup_prod_weaviate() -> str:
    """
    Creates a safety-net backup of the Production Weaviate instance.
    Includes whichever of KNOWN_CLASSES are actually present in Prod.
    """
    prod_url = os.getenv("PROD_WEAVIATE_URL", "http://localhost:8080")
    backup_endpoint = f"{prod_url}/v1/backups/s3"

    include = existing_classes(prod_url, KNOWN_CLASSES)
    snapshot_id = f"prod_safety_snapshot_{int(time.time())}"
    payload = {
        "id": snapshot_id,
        "include": include,
    }

    trigger_and_wait_weaviate_backup(backup_endpoint, payload, "backup")
    return snapshot_id


@op
def backup_test_weaviate() -> str:
    """
    Creates a backup of the Test Weaviate instance for promotion to Prod.
    Includes whichever of KNOWN_CLASSES are actually present in Test.
    """
    test_url = os.getenv("TEST_WEAVIATE_URL", "http://localhost:8081")
    backup_endpoint = f"{test_url}/v1/backups/s3"

    include = existing_classes(test_url, KNOWN_CLASSES)
    snapshot_id = f"test_to_prod_snapshot_{int(time.time())}"
    payload = {
        "id": snapshot_id,
        "include": include,
    }

    trigger_and_wait_weaviate_backup(backup_endpoint, payload, "backup")
    return snapshot_id


@op
def mirror_minio_buckets(prod_backup_id: str, test_backup_id: str) -> bool:
    """
    Mirrors the Test MinIO backup bucket to Prod MinIO using the mc CLI.
    Accepts the backup IDs purely to enforce execution order.
    """
    test_minio_endpoint = os.getenv(
        "TEST_MINIO_ENDPOINT", "http://gya-minio.gya-test:9000"
    )
    prod_minio_endpoint = os.getenv(
        "PROD_MINIO_ENDPOINT", "http://gya-minio.gya-prod:9000"
    )
    test_user = os.getenv("TEST_MINIO_USER", "")
    test_pass = os.getenv("TEST_MINIO_PASS", "")
    prod_user = os.getenv("PROD_MINIO_USER", "")
    prod_pass = os.getenv("PROD_MINIO_PASS", "")

    mc_bin = os.getenv("MINIO_CLIENT_BIN", "mcli")

    # Each entry is (cmd, log_cmd) where log_cmd is what we'll put in error
    # messages — credentials are scrubbed so failures don't leak secrets into
    # Dagster logs.
    commands = [
        (
            [mc_bin, "alias", "set", "test_minio", test_minio_endpoint, test_user, test_pass],
            [mc_bin, "alias", "set", "test_minio", test_minio_endpoint, "***", "***"],
        ),
        (
            [mc_bin, "alias", "set", "prod_minio", prod_minio_endpoint, prod_user, prod_pass],
            [mc_bin, "alias", "set", "prod_minio", prod_minio_endpoint, "***", "***"],
        ),
        (
            [
                mc_bin,
                "mirror",
                "--overwrite",
                f"test_minio/weaviate-backups/{test_backup_id}",
                f"prod_minio/weaviate-backups/{test_backup_id}",
            ],
            None,
        ),
    ]

    for cmd, log_cmd in commands:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            shown = " ".join(log_cmd) if log_cmd is not None else " ".join(cmd)
            raise Exception(
                f"{mc_bin} command failed: {shown}\n"
                f"stdout: {result.stdout}\n"
                f"stderr: {result.stderr}"
            )

    return True


@op
def restore_prod_weaviate(mirror_success: bool, test_backup_id: str) -> str:
    """
    Restores the test snapshot into the Production Weaviate instance.
    """
    if not mirror_success:
        raise Exception("Mirror operation did not succeed, aborting restore.")

    prod_url = os.getenv("PROD_WEAVIATE_URL", "http://localhost:8080")
    test_url = os.getenv("TEST_WEAVIATE_URL", "http://localhost:8081")

    # Drop only the classes that actually exist in Prod, so the restore can
    # recreate them. Skipping missing classes avoids 404s on a fresh side.
    classes_to_drop = existing_classes(prod_url, KNOWN_CLASSES)
    for class_name in classes_to_drop:
        delete_url = f"{prod_url}/v1/schema/{class_name}"
        res = requests.delete(delete_url)
        # 200 means deleted successfully. 400/404 means it didn't exist anyway.
        if res.status_code not in (200, 400, 404):
            raise Exception(f"Failed to drop {class_name} in Prod: {res.text}")

    # Restore whatever Test actually has — that's the set of classes we just
    # mirrored from Test's bucket.
    restore_endpoint = f"{prod_url}/v1/backups/s3/{test_backup_id}/restore"
    payload: Dict[str, object] = {
        "include": existing_classes(test_url, KNOWN_CLASSES)
    }

    snapshot_id = trigger_and_wait_weaviate_backup(
        restore_endpoint, payload, "restore"
    )
    return snapshot_id


@job
def promote_test_vectors_to_prod():
    """
    Dagster Job that migrates Weaviate vectors from Test to Production.

    Execution graph:
        1. backup_prod_weaviate  ──┐
        2. backup_test_weaviate  ──┼──> mirror_minio_buckets ──> restore_prod_weaviate
    """
    prod_backup_id = backup_prod_weaviate()
    test_backup_id = backup_test_weaviate()
    mirror_success = mirror_minio_buckets(prod_backup_id, test_backup_id)
    restore_prod_weaviate(mirror_success, test_backup_id)
