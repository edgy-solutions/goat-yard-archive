import os
import subprocess
from typing import List

from dagster import (
    AssetExecutionContext,
    DynamicPartitionsDefinition,
    StaticPartitionsDefinition,
    MultiPartitionsDefinition,
    asset,
    AssetDep,
    AllPartitionMapping,
    MultiPartitionMapping,
    DimensionPartitionMapping,
    IdentityPartitionMapping,
)

# 1. Define Partitions
# Static partition for Volumes 1 through 9
volume_partitions = StaticPartitionsDefinition([str(i) for i in range(1, 10)])

# Dynamic partition for Pages
page_partitions = DynamicPartitionsDefinition(name="page_partitions")

# Multi-partition combining both
volume_page_partitions = MultiPartitionsDefinition(
    {
        "volume": volume_partitions,
        "page": page_partitions,
    }
)

# Base directory for data
COMMENTARY_DATA_DIR = os.getenv("COMMENTARY_DATA_DIR", "/data/commentary")
PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(PIPELINE_DIR, "scripts")


# 2. Helper function for running subprocess and piping logs to Dagster context
def run_cli_script(context: AssetExecutionContext, cmd: List[str], cwd: str = None):
    """
    Runs a shell command via subprocess, piping output to the Dagster context logger.
    """
    cmd_str = " ".join(cmd)
    context.log.info(f"Running command: {cmd_str}")
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=cwd
    )
    
    # Stream output to Dagster log
    for line in process.stdout:
        context.log.info(line.strip())
        
    process.wait()
    
    if process.returncode != 0:
        raise Exception(f"Command failed with return code {process.returncode}")


# 3. Asset Definitions

@asset(partitions_def=volume_partitions)
def extract_images(context: AssetExecutionContext):
    """
    Scope: Per Volume
    Extracts images for a volume and yields a DynamicPartitionsRequest to add pages.
    """
    volume = context.partition_key
    
    cmd = ["python", os.path.join(SCRIPTS_DIR, "extract_images.py"), volume]
    
    # Run the script
    run_cli_script(context, cmd)
    
    # After extraction, determine which pages were created.
    # We simulate reading the directory to find the generated pages.
    volume_dir = os.path.join(COMMENTARY_DATA_DIR, f"volume{volume}")
    
    discovered_pages = []
    if os.path.exists(volume_dir):
        for filename in os.listdir(volume_dir):
            if filename.startswith("page") and filename.endswith("_image.png"):
                # Extract the page identifier, e.g. "100" from "page100_image.png"
                # Since downstream scripts use {y} as "100" (or similar depending on script args)
                page_id = filename.split("_image")[0].replace("page", "")
                if page_id not in discovered_pages:
                    discovered_pages.append(page_id)
                    
    # Ensure partition keys are strings and unique
    partition_keys_to_add = [str(p) for p in set(discovered_pages)]
    context.log.info(f"Discovered {len(partition_keys_to_add)} pages for volume {volume}: {partition_keys_to_add}")
    
    # Add these new page partitions to the instance directly
    if partition_keys_to_add:
        context.instance.add_dynamic_partitions(
            partitions_def_name="page_partitions",
            partition_keys=partition_keys_to_add
        )


@asset(partitions_def=volume_page_partitions)
def get_md(context: AssetExecutionContext, extract_images):
    """
    Scope: Per Volume + Page
    get_md.py --image "volume{x}/page{y}_image.png"
    """
    volume = context.partition_key.keys_by_dimension["volume"]
    page = context.partition_key.keys_by_dimension["page"]
    
    image_path = f"volume{volume}/page{page}_image.png"
    cmd = ["python", os.path.join(SCRIPTS_DIR, "get_md.py"), "--image", image_path]
    
    run_cli_script(context, cmd)


@asset(partitions_def=volume_page_partitions)
def read_images_baml(context: AssetExecutionContext, get_md):
    """
    Scope: Per Volume + Page
    read_images_baml.py --pages {y}
    """
    page = context.partition_key.keys_by_dimension["page"]
    
    cmd = ["python", os.path.join(SCRIPTS_DIR, "read_images_baml.py"), "--pages", page]
    
    run_cli_script(context, cmd)


@asset(partitions_def=volume_page_partitions)
def reindex_ocr(context: AssetExecutionContext, read_images_baml):
    """
    Scope: Per Volume + Page
    reindex_ocr.py --extracted-dir "$COMMENTARY_DATA_DIR/volume{x}" --page {y}
    """
    volume = context.partition_key.keys_by_dimension["volume"]
    page = context.partition_key.keys_by_dimension["page"]
    
    extracted_dir = os.path.join(COMMENTARY_DATA_DIR, f"volume{volume}")
    
    cmd = [
        "python", os.path.join(SCRIPTS_DIR, "reindex_ocr.py"), 
        "--extracted-dir", extracted_dir, 
        "--page", page
    ]
    
    run_cli_script(context, cmd)


@asset(partitions_def=volume_page_partitions)
def fixup_ocr(context: AssetExecutionContext, reindex_ocr):
    """
    Scope: Per Volume + Page
    fixup_ocr.py --extracted-dir "$COMMENTARY_DATA_DIR/volume{x}" 
                 --markdown-dir "$COMMENTARY_DATA_DIR/volume{x}/qwen_qwen3-vl-235b-a22b-thinking" 
                 --page {y}
    """
    volume = context.partition_key.keys_by_dimension["volume"]
    page = context.partition_key.keys_by_dimension["page"]
    
    extracted_dir = os.path.join(COMMENTARY_DATA_DIR, f"volume{volume}")
    markdown_dir = os.path.join(extracted_dir, "qwen_qwen3-vl-235b-a22b-thinking")
    
    cmd = [
        "python", os.path.join(SCRIPTS_DIR, "fixup_ocr.py"), 
        "--extracted-dir", extracted_dir,
        "--markdown-dir", markdown_dir,
        "--page", page
    ]
    
    run_cli_script(context, cmd)


@asset(partitions_def=volume_page_partitions)
def normalize_markdown(context: AssetExecutionContext, fixup_ocr):
    """
    Scope: Per Volume + Page
    normalize_markdown.py --dir "$COMMENTARY_DATA_DIR/volume{x}/qwen_qwen3-vl-235b-a22b-thinking" 
                          --force --backend dspy --model deepseek/deepseek-chat --page {y}
    """
    volume = context.partition_key.keys_by_dimension["volume"]
    page = context.partition_key.keys_by_dimension["page"]
    
    markdown_dir = os.path.join(COMMENTARY_DATA_DIR, f"volume{volume}", "qwen_qwen3-vl-235b-a22b-thinking")
    
    cmd = [
        "python", os.path.join(SCRIPTS_DIR, "normalize_markdown.py"),
        "--dir", markdown_dir,
        "--force",
        "--backend", "dspy",
        "--model", "deepseek/deepseek-chat",
        "--page", page
    ]
    
    run_cli_script(context, cmd)


@asset(partitions_def=volume_page_partitions)
def verify_existing(context: AssetExecutionContext, normalize_markdown):
    """
    Scope: Per Volume + Page
    verify_existing.py --page {y}
    """
    page = context.partition_key.keys_by_dimension["page"]
    
    cmd = ["python", os.path.join(SCRIPTS_DIR, "verify_existing.py"), "--page", page]
    
    run_cli_script(context, cmd)


@asset(partitions_def=volume_page_partitions)
def align_verses(context: AssetExecutionContext, verify_existing):
    """
    Scope: Per Volume + Page
    align_verses.py --dir "$COMMENTARY_DATA_DIR/volume{x}" --page {y}
    """
    volume = context.partition_key.keys_by_dimension["volume"]
    page = context.partition_key.keys_by_dimension["page"]
    
    extracted_dir = os.path.join(COMMENTARY_DATA_DIR, f"volume{volume}")
    
    cmd = [
        "python", os.path.join(SCRIPTS_DIR, "align_verses.py"), 
        "--dir", extracted_dir, 
        "--page", page
    ]
    
    run_cli_script(context, cmd)


@asset(partitions_def=volume_page_partitions)
def ingest(context: AssetExecutionContext, align_verses):
    """
    Scope: Per Volume + Page
    ingest.py --data-dir "$COMMENTARY_DATA_DIR/volume{x}" 
              --alignment-dir "$COMMENTARY_DATA_DIR/artifacts/alignment/volume{x}" 
              --page {y}
    """
    volume = context.partition_key.keys_by_dimension["volume"]
    page = context.partition_key.keys_by_dimension["page"]
    
    data_dir = os.path.join(COMMENTARY_DATA_DIR, f"volume{volume}")
    alignment_dir = os.path.join(COMMENTARY_DATA_DIR, "artifacts", "alignment", f"volume{volume}")
    
    cmd = [
        "python", os.path.join(SCRIPTS_DIR, "ingest.py"),
        "--data-dir", data_dir,
        "--alignment-dir", alignment_dir,
        "--page", page
    ]
    
    run_cli_script(context, cmd)


@asset(
    partitions_def=volume_partitions,
    deps=[AssetDep("get_md", partition_mapping=MultiPartitionMapping({
        "volume": DimensionPartitionMapping("volume", IdentityPartitionMapping()),
        "page": DimensionPartitionMapping("page", AllPartitionMapping())
    }))]
)
def verify_verse_continuity_validation(context: AssetExecutionContext):
    """
    Scope: Per Volume
    verify_verse_continuity.py "$COMMENTARY_DATA_DIR/volume{x}"
    Validates the generated _metadata.json files to ensure no verses are missing from the volume sequence.
    """
    volume = context.partition_key
    volume_dir = os.path.join(COMMENTARY_DATA_DIR, f"volume{volume}")
    
    cmd = [
        "python", os.path.join(SCRIPTS_DIR, "verify_verse_continuity.py"),
        volume_dir
    ]
    
    run_cli_script(context, cmd)


@asset(deps=[AssetDep("ingest", partition_mapping=AllPartitionMapping())])
def verify_db_ingestion_global(context: AssetExecutionContext):
    """
    Scope: Global
    verify_ingestion_test.py
    Hits the local Weaviate DB and asserts that chunks aren't lingering with unresolved footnotes or format issues.
    """
    cmd = ["python", os.path.join(SCRIPTS_DIR, "verify_ingestion_test.py")]
    
    # Weaviate testing script runs fast
    run_cli_script(context, cmd)


@asset(deps=[AssetDep("get_md", partition_mapping=AllPartitionMapping())])
def optimize_dspy_normalizer(context: AssetExecutionContext):
    """
    Scope: Global / Ad-hoc
    train_dspy.py
    Retrains the LLM prompt using DSPy's BootstrapFewShot optimizer.
    """
    # Assuming volume 1 qwen for training examples as a default
    examples_dir = os.path.join(COMMENTARY_DATA_DIR, "volume1", "qwen_qwen3-vl-235b-a22b-thinking")
    
    if not os.path.exists(examples_dir):
        context.log.warning(f"Training directory not found at {examples_dir}. Skipping.")
        return
        
    cmd = [
        "python", os.path.join(SCRIPTS_DIR, "train_dspy.py"),
        "--dir", examples_dir
    ]
    
    run_cli_script(context, cmd)


@asset(partitions_def=volume_partitions)
def verify_markdown_headers_validation(context: AssetExecutionContext):
    """
    Scope: Per Volume
    audit_missing_headers.py
    Explicitly scans each page in the partition to confirm the LLM output properly attached `# CHAP.` headers to the raw `.md` data.
    """
    volume = context.partition_key
    volume_dir = os.path.join(COMMENTARY_DATA_DIR, f"volume{volume}")
    
    if not os.path.exists(volume_dir):
        context.log.warning(f"Data directory not found for Volume {volume}. Skipping.")
        return
        
    cmd = [
        "python", os.path.join(SCRIPTS_DIR, "audit_missing_headers.py"),
        volume_dir
    ]
    
    # Passing the directory to the script requires the script to accept it if it was modified, 
    # but the script actually hardcodes volumes internally using COMMENTARY_DATA_DIR. 
    # To be safe and utilize the partition naturally, we can set the env var for the subprocess.
    env = os.environ.copy()
    env["COMMENTARY_DATA_DIR"] = volume_dir
    
    context.log.info(f"Running command: {' '.join(cmd)}")
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=None, env=env
    )
    for line in process.stdout:
        context.log.info(line.strip())
    process.wait()
    if process.returncode != 0:
        raise Exception(f"Command failed with return code {process.returncode}")


@asset(deps=[AssetDep("ingest", partition_mapping=AllPartitionMapping())])
def scan_duplicate_entities_global(context: AssetExecutionContext):
    """
    Scope: Global
    deduplicate_entities.py scan
    Continuously hits Weaviate to warn the pipeline UI if fragmented entities (same name/era) start occurring inside the graph unexpectedly.
    """
    cmd = [
        "python", os.path.join(SCRIPTS_DIR, "deduplicate_entities.py"),
        "scan"
    ]
    
    run_cli_script(context, cmd)


@asset
def build_kjv_fast_lookup_global(context: AssetExecutionContext):
    """
    Scope: Global
    build_bible_index.py
    Builds the flat JSON KJV Index `kjv_fast_lookup.json` acting as the O(1) Verse API.
    """
    cmd = [
        "python", os.path.join(SCRIPTS_DIR, "build_bible_index.py")
    ]
    
    run_cli_script(context, cmd)


@asset(
    partitions_def=volume_partitions,
    deps=[
        "extract_images", 
        AssetDep("build_kjv_fast_lookup_global", partition_mapping=AllPartitionMapping())
    ]
)
def upload_to_minio(context: AssetExecutionContext, build_kjv_fast_lookup_global):
    """
    Scope: Per Volume
    setup_minio.py
    Syncs the newly built `kjv_fast_lookup.json` map natively and the volume's `scans` into the MinIO bucket alongside global frontend default graphics.
    """
    volume = context.partition_key
    cmd = [
        "python", os.path.join(SCRIPTS_DIR, "setup_minio.py"),
        "--volume", volume
    ]
    
    # Needs to run in repo root because setup_minio.py relies on Path("frontend/public/scans") and Path("kjv_fast_lookup.json")
    cwd = os.path.dirname(PIPELINE_DIR)
    
    run_cli_script(context, cmd, cwd=cwd)
