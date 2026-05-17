import os
import subprocess
import time
from typing import Dict

import requests
from dagster import In, Nothing, Out, op, job


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
    response.raise_for_status()
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
    Includes CommentaryChunk, TheologicalEntity, and GroupSummary.
    """
    prod_url = os.getenv("PROD_WEAVIATE_URL", "http://localhost:8080")
    backup_endpoint = f"{prod_url}/v1/backups/s3"

    snapshot_id = f"prod_safety_snapshot_{int(time.time())}"
    payload = {
        "id": snapshot_id,
        "include": ["CommentaryChunk", "TheologicalEntity", "GroupSummary"],
    }

    trigger_and_wait_weaviate_backup(backup_endpoint, payload, "backup")
    return snapshot_id


@op
def backup_test_weaviate() -> str:
    """
    Creates a backup of the Test Weaviate instance for promotion to Prod.
    Includes CommentaryChunk and TheologicalEntity (excludes GroupSummary).
    """
    test_url = os.getenv("TEST_WEAVIATE_URL", "http://localhost:8081")
    backup_endpoint = f"{test_url}/v1/backups/s3"

    snapshot_id = f"test_to_prod_snapshot_{int(time.time())}"
    payload = {
        "id": snapshot_id,
        "include": ["CommentaryChunk", "TheologicalEntity"],
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

    commands = [
        [mc_bin, "alias", "set", "test_minio", test_minio_endpoint, test_user, test_pass],
        [mc_bin, "alias", "set", "prod_minio", prod_minio_endpoint, prod_user, prod_pass],
        [
            mc_bin,
            "mirror",
            "--overwrite",
            f"test_minio/weaviate-backups/{test_backup_id}",
            f"prod_minio/weaviate-backups/{test_backup_id}",
        ],
    ]

    for cmd in commands:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(
                f"{mc_bin} command failed: {' '.join(cmd)}\n"
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

    # --- NEW: Drop the existing classes so Weaviate allows the restore ---
    classes_to_drop = ["CommentaryChunk", "TheologicalEntity", "GroupSummary"]
    for class_name in classes_to_drop:
        delete_url = f"{prod_url}/v1/schema/{class_name}"
        res = requests.delete(delete_url)
        # 200 means deleted successfully. 400/404 means it didn't exist anyway.
        if res.status_code not in (200, 400, 404):
            raise Exception(f"Failed to drop {class_name} in Prod: {res.text}")
    # ---------------------------------------------------------------------

    restore_endpoint = f"{prod_url}/v1/backups/s3/{test_backup_id}/restore"
    
    # We explicitly tell it which classes to restore just to be safe
    payload: Dict[str, object] = {
        "include": ["CommentaryChunk", "TheologicalEntity", "GroupSummary"]
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
