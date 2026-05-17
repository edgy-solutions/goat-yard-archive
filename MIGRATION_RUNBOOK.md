# Weaviate Vector Promotion Pipeline (Test -> Prod)

This runbook details how to safely migrate the Weaviate vector database from the Test cluster to Production using our Dagster pipeline.

## Architectural Context
Because S3 APIs (used by the MinIO client) do not support path-based routing, we **cannot** use the public Ingress URLs to transfer the data. We must port-forward directly to the MinIO services locally before running the Dagster job.

## Prerequisites
1. You must have `mcli` (MinIO Client) installed on your local machine.

## Execution Steps

**Step 1: Run the Dagster Pipeline**
1. Open the Dagster UI.
2. Navigate to **Jobs** -> `promote_test_vectors_to_prod`.
3. Click **Launchpad** and execute the job.

**What this Job does automatically:**
1. Backs up Production (Safety Net).
2. Backs up Test (Excluding `GroupSummary` cache).
3. Uses `mcli` to safely mirror the snapshot from `localhost:9000` to `localhost:9001`.
4. Instructs Production Weaviate to ingest the new brain.

## Rollback Procedure
If the restore fails or data looks corrupted in Prod:
1. The Dagster job automatically created a backup named `prod_safety_snapshot`.
2. To roll back, send this exact cURL to the Prod Weaviate instance:
   ```bash
   curl -X POST \
     -H "Content-Type: application/json" \
     -d '{
           "id": "prod_safety_snapshot",
           "config": {
             "Bucket": "weaviate-backups",
             "Endpoint": "gya-minio.gya-prod.svc.cluster.local:9000",
             "UseSSL": false
           }
         }' \
     http://weaviate.gya-prod.svc.cluster.local:80/v1/backups/s3/prod_safety_snapshot/restore
   ```
