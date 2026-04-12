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
    MultiToSingleDimensionPartitionMapping,
    MaterializeResult,
    MetadataValue,
)
from dagster_slack import SlackResource

# 1. Define Partitions
# Static partition for Volumes 1 through 9
volume_partitions = StaticPartitionsDefinition([str(i) for i in range(1, 10)])

# Dynamic partition for Pages
page_partitions = DynamicPartitionsDefinition(name="page_partitions")

# Multi-partition combining both
volume_page_partitions = MultiPartitionsDefinition(
    {
        "1_volume": volume_partitions,
        "2_page": page_partitions,
    }
)

# Base directory for data
COMMENTARY_DATA_DIR = os.getenv("COMMENTARY_DATA_DIR", "/data/commentary")
PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(PIPELINE_DIR, "scripts")


# 2. Helper function for running subprocess and piping logs to Dagster context
def run_cli_script(context: AssetExecutionContext, cmd: List[str], cwd: str = None) -> str:
    """
    Runs a shell command via subprocess, piping output to the Dagster context logger.
    Returns the full stdout as a string.
    """
    cmd_str = " ".join([str(c) for c in cmd])
    context.log.info(f"Running command: {cmd_str}")
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=cwd
    )
    
    lines = []
    # Stream output to Dagster log
    for line in process.stdout:
        stripped = line.strip()
        context.log.info(stripped)
        lines.append(stripped)
        
    process.wait()
    
    if process.returncode != 0:
        raise Exception(f"Command failed with return code {process.returncode}")
        
    return "\n".join(lines)


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
        # Look for files like page100_image7.png
        suffix = f"_image{volume}.png"
        for filename in os.listdir(volume_dir):
            if filename.startswith("page") and filename.endswith(suffix):
                # Extract the page identifier, e.g. "100" from "page100_image7.png"
                page_id = filename.replace("page", "").replace(suffix, "")
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


@asset(partitions_def=volume_page_partitions, deps=["extract_images"])
def get_md(context: AssetExecutionContext):
    """
    Scope: Per Volume + Page
    get_md.py --image "volume{x}/page{y}_image.png"
    """
    volume = context.partition_key.keys_by_dimension["1_volume"]
    page = context.partition_key.keys_by_dimension["2_page"]
    
    # --- GHOST PARTITION SHIELD ---
    base_image_path = os.path.join(COMMENTARY_DATA_DIR, f"volume{volume}", f"page{page}_image{volume}.png")
    if not os.path.exists(base_image_path):
        context.log.info(f"Ghost partition detected for Vol {volume} Page {page}. Skipping.")
        return
    # ------------------------------
    
    # get_md.py expects: python get_md.py [image_path] [optional_args]
    # No --image flag, it's a positional argument.
    image_path = os.path.join(COMMENTARY_DATA_DIR, f"volume{volume}", f"page{page}_image{volume}.png")
    cmd = ["python", os.path.join(SCRIPTS_DIR, "get_md.py"), image_path]
    
    run_cli_script(context, cmd)


@asset(
    partitions_def=volume_page_partitions,
    op_tags={"dagster/concurrency_key": "openrouter"},
    deps=["get_md"]
)
def read_images_baml(context: AssetExecutionContext):
    """
    Scope: Per Volume + Page
    read_images_baml.py --pages {y}
    """
    volume = context.partition_key.keys_by_dimension["1_volume"]
    page = context.partition_key.keys_by_dimension["2_page"]
    
    # --- GHOST PARTITION SHIELD ---
    base_image_path = os.path.join(COMMENTARY_DATA_DIR, f"volume{volume}", f"page{page}_image{volume}.png")
    if not os.path.exists(base_image_path):
        context.log.info(f"Ghost partition detected for Vol {volume} Page {page}. Skipping.")
        return
    # ------------------------------
    
    directory = os.path.join(COMMENTARY_DATA_DIR, f"volume{volume}")
    cmd = [
        "python", os.path.join(SCRIPTS_DIR, "read_images_baml.py"), 
        "--directory", directory,
        "--pages", page
    ]
    
    run_cli_script(context, cmd)


@asset(partitions_def=volume_page_partitions, deps=["read_images_baml"])
def reindex_ocr(context: AssetExecutionContext):
    """
    Scope: Per Volume + Page
    reindex_ocr.py --extracted-dir "$COMMENTARY_DATA_DIR/volume{x}" --page {y}
    """
    volume = context.partition_key.keys_by_dimension["1_volume"]
    page = context.partition_key.keys_by_dimension["2_page"]
    
    # --- GHOST PARTITION SHIELD ---
    base_image_path = os.path.join(COMMENTARY_DATA_DIR, f"volume{volume}", f"page{page}_image{volume}.png")
    if not os.path.exists(base_image_path):
        context.log.info(f"Ghost partition detected for Vol {volume} Page {page}. Skipping.")
        return
    # ------------------------------
    
    extracted_dir = os.path.join(COMMENTARY_DATA_DIR, f"volume{volume}")
    page_name = f"page{page}_image{volume}"
    
    cmd = [
        "python", os.path.join(SCRIPTS_DIR, "reindex_ocr.py"), 
        "--extracted-dir", extracted_dir, 
        "--page", page_name
    ]
    
    run_cli_script(context, cmd)


@asset(partitions_def=volume_page_partitions, deps=["reindex_ocr"])
def fixup_ocr(context: AssetExecutionContext):
    """
    Scope: Per Volume + Page
    fixup_ocr.py --extracted-dir "$COMMENTARY_DATA_DIR/volume{x}" 
                 --markdown-dir "$COMMENTARY_DATA_DIR/volume{x}/qwen_qwen3-vl-235b-a22b-thinking" 
                 --page {y}
    """
    volume = context.partition_key.keys_by_dimension["1_volume"]
    page = context.partition_key.keys_by_dimension["2_page"]
    
    # --- GHOST PARTITION SHIELD ---
    base_image_path = os.path.join(COMMENTARY_DATA_DIR, f"volume{volume}", f"page{page}_image{volume}.png")
    if not os.path.exists(base_image_path):
        context.log.info(f"Ghost partition detected for Vol {volume} Page {page}. Skipping.")
        return
    # ------------------------------
    
    extracted_dir = os.path.join(COMMENTARY_DATA_DIR, f"volume{volume}")
    markdown_dir = os.path.join(extracted_dir, "qwen_qwen3-vl-235b-a22b-thinking")
    page_name = f"page{page}_image{volume}"
    
    cmd = [
        "python", os.path.join(SCRIPTS_DIR, "fixup_ocr.py"), 
        "--extracted-dir", extracted_dir,
        "--markdown-dir", markdown_dir,
        "--page", page_name
    ]
    
    run_cli_script(context, cmd)


@asset(
    partitions_def=volume_page_partitions,
    op_tags={"dagster/concurrency_key": "openrouter"},
    deps=["fixup_ocr"]
)
def normalize_markdown(context: AssetExecutionContext):
    """
    Scope: Per Volume + Page
    normalize_markdown.py --dir "$COMMENTARY_DATA_DIR/volume{x}/qwen_qwen3-vl-235b-a22b-thinking" 
                          --force --backend dspy --model deepseek/deepseek-chat --page {y}
    """
    volume = context.partition_key.keys_by_dimension["1_volume"]
    page = context.partition_key.keys_by_dimension["2_page"]
    
    # --- GHOST PARTITION SHIELD ---
    base_image_path = os.path.join(COMMENTARY_DATA_DIR, f"volume{volume}", f"page{page}_image{volume}.png")
    if not os.path.exists(base_image_path):
        context.log.info(f"Ghost partition detected for Vol {volume} Page {page}. Skipping.")
        return
    # ------------------------------
    
    markdown_dir = os.path.join(COMMENTARY_DATA_DIR, f"volume{volume}", "qwen_qwen3-vl-235b-a22b-thinking")
    markdown_file = os.path.join(markdown_dir, f"page{page}_image{volume}.md")
    
    cmd = [
        "python", os.path.join(SCRIPTS_DIR, "normalize_markdown.py"),
        "--file", markdown_file,
        "--force",
        "--backend", "dspy",
        "--model", "deepseek/deepseek-chat"
    ]
    
    # Run the script and capture output
    output = run_cli_script(context, cmd)
    
    metadata = {"Status": "✅ Success"}
    if "Already normalized" in output or "Skipping" in output:
        metadata["Status"] = "ℹ️ Skipped - Already normalized"
        
    return MaterializeResult(metadata=metadata)


@asset(partitions_def=volume_page_partitions, deps=["normalize_markdown"])
def verify_existing(context: AssetExecutionContext):
    """
    Scope: Per Volume + Page
    verify_existing.py --page {y}
    """
    volume = context.partition_key.keys_by_dimension["1_volume"]
    page = context.partition_key.keys_by_dimension["2_page"]
    
    # --- GHOST PARTITION SHIELD ---
    base_image_path = os.path.join(COMMENTARY_DATA_DIR, f"volume{volume}", f"page{page}_image{volume}.png")
    if not os.path.exists(base_image_path):
        context.log.info(f"Ghost partition detected for Vol {volume} Page {page}. Skipping.")
        return
    # ------------------------------
    
    page_name = f"page{page}_image{volume}"
    
    cmd = [
        "python", os.path.join(SCRIPTS_DIR, "verify_existing.py"), 
        "--page", page_name
    ]
    
    run_cli_script(context, cmd)


@asset(partitions_def=volume_page_partitions, deps=["verify_existing"])
def align_verses(context: AssetExecutionContext):
    """
    Scope: Per Volume + Page
    align_verses.py --dir "$COMMENTARY_DATA_DIR/volume{x}" --page {y}
    """
    volume = context.partition_key.keys_by_dimension["1_volume"]
    page = context.partition_key.keys_by_dimension["2_page"]
    
    # --- GHOST PARTITION SHIELD ---
    base_image_path = os.path.join(COMMENTARY_DATA_DIR, f"volume{volume}", f"page{page}_image{volume}.png")
    if not os.path.exists(base_image_path):
        context.log.info(f"Ghost partition detected for Vol {volume} Page {page}. Skipping.")
        return
    # ------------------------------
    
    extracted_dir = os.path.join(COMMENTARY_DATA_DIR, f"volume{volume}")
    page_name = f"page{page}_image{volume}"
    # align_verses expects positional arguments if none specified, but we'll use --page
    cmd = [
        "python", os.path.join(SCRIPTS_DIR, "align_verses.py"), 
        "--dir", extracted_dir, 
        "--page", page_name
    ]
    
    # Run the script and capture output
    output = run_cli_script(context, cmd)
    
    import re
    metadata = {"Status": "✅ Success"}
    
    # Check for "No Verses Found:  1" (or similar)
    no_verses_match = re.search(r"No Verses Found:\s+([1-9]\d*)", output)
    if no_verses_match:
        metadata["Status"] = "⚠️ Warning - No verses found"
        metadata["Warning Details"] = f"{no_verses_match.group(1)} pages had 0 verses"
        
    return MaterializeResult(metadata=metadata)


@asset(
    partitions_def=volume_page_partitions,
    deps=["align_verses"],
    op_tags={"dagster/concurrency_key": "weaviate_ingest"}
)
def ingest(context: AssetExecutionContext):
    """
    Scope: Per Volume + Page
    ingest.py --data-dir "$COMMENTARY_DATA_DIR/volume{x}" 
              --alignment-dir "$COMMENTARY_DATA_DIR/artifacts/alignment/volume{x}" 
              --page {y}
    """
    volume = context.partition_key.keys_by_dimension["1_volume"]
    page = context.partition_key.keys_by_dimension["2_page"]
    
    # --- GHOST PARTITION SHIELD ---
    base_image_path = os.path.join(COMMENTARY_DATA_DIR, f"volume{volume}", f"page{page}_image{volume}.png")
    if not os.path.exists(base_image_path):
        context.log.info(f"Ghost partition detected for Vol {volume} Page {page}. Skipping.")
        return
    # ------------------------------
    
    data_dir = os.path.join(COMMENTARY_DATA_DIR, f"volume{volume}")
    alignment_dir = os.path.join(COMMENTARY_DATA_DIR, "artifacts", "alignment", f"volume{volume}")
    page_name = f"page{page}_image{volume}"
    
    cmd = [
        "python", os.path.join(SCRIPTS_DIR, "ingest.py"),
        "--data-dir", data_dir,
        "--alignment-dir", alignment_dir,
        "--page", page_name,
        "--volume", str(volume),
        "--ollama-url", os.getenv("OLLAMA_URL", "http://localhost:11434/api/embeddings"),
        "--ollama-model", os.getenv("OLLAMA_MODEL", "qwen3-embedding")
    ]
    
    # Run the script and capture output
    output = run_cli_script(context, cmd)
    
    import re
    metadata = {"Status": "✅ Success"}
    
    # Parse chunk count: "[OK] Test complete: 5 chunks ingested for page1"
    # or "[OK] Batch complete: 10 chunks total"
    chunk_match = re.search(r"(\d+) chunks (?:ingested|total)", output)
    if chunk_match:
        chunk_count = int(chunk_match.group(1))
        metadata["Chunks Ingested"] = chunk_count
        if chunk_count == 0:
            metadata["Status"] = "⚠️ Warning - 0 Chunks"
            
    if "Metadata not found" in output:
        metadata["Status"] = "⚠️ Warning - No upstream data (metadata missing)"
        
    return MaterializeResult(metadata=metadata)


@asset(
    partitions_def=volume_partitions,
    deps=[
        AssetDep(
            "get_md", 
            partition_mapping=MultiToSingleDimensionPartitionMapping(partition_dimension_name="1_volume")
        )
    ]
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


@asset(
    partitions_def=volume_partitions,
    deps=[
        AssetDep(
            "read_images_baml", 
            partition_mapping=MultiToSingleDimensionPartitionMapping(partition_dimension_name="1_volume")
        )
    ]
)
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
def upload_to_minio(context: AssetExecutionContext):
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

@asset(group_name="operations", required_resource_keys={"slack"})
def daily_rag_diagnostic(context: AssetExecutionContext):
    """
    Scope: Daily SRE
    Audits failed full-stack traces using an LLM.
    """
    try:
        from langfuse import Langfuse
        from baml_client.sync_client import b as baml_client
    except ImportError as e:
        context.log.warning(f"Could not import Langfuse or BAML for diagnostic: {e}")
        return MaterializeResult(metadata={"status": "skipped", "reason": "missing dependencies"})

    slack: SlackResource = context.resources.slack
    langfuse = Langfuse()
    
    # 1. Fetch traces from last 24h that failed (score = 0)
    env_tag = os.getenv("APP_ENV", "production")
    traces = []
    page = 1
    while True:
        traces_response = langfuse.get_traces(
            tags=[env_tag, "v7_launch"],
            score_name="retrieval_success",
            score_value=0,
            page=page
        )
        batch = getattr(traces_response, "data", [])
        if not batch:
            break
        traces.extend(batch)
        if len(batch) < 50 or page >= 10:  # standard default page size is 50, safety exit at 10 pages just in case
            break
        page += 1

    reports_data = []
    
    for trace in traces:
        question = trace.input if isinstance(trace.input, str) else trace.input.get("query", "Unknown Query") if isinstance(trace.input, dict) else "Unknown Query"
        
        # Discover weaviate retrieval output
        retrieval_context = "No context found in trace"
        try:
            full_trace = langfuse.get_trace(trace.id)
            observations = full_trace.observations if hasattr(full_trace, "observations") else []
            
            for obs in observations:
                if obs.name == "weaviate_retrieval":
                    retrieval_context = str(obs.output)
                    break
        except Exception as e:
             retrieval_context = f"Error fetching observations: {e}"

        manifest = trace.metadata.get("available_books", "Unknown") if trace.metadata else "Unknown"

        try:
            analysis = baml_client.AnalyzeRAGFailure(
                question=question,
                context=retrieval_context,
                manifest=manifest
            )
            reports_data.append({
                "question": question,
                "reasoning": analysis.reasoning,
                "fix_action": analysis.fix_action
            })
        except Exception as e:
            reports_data.append({
                "question": question,
                "reasoning": f"🔴 BAML Inference Error: {e}",
                "fix_action": "Check LLM API status or BAML parameters."
            })

    target_channel = os.getenv("SLACK_DIAGNOSTICS_CHANNEL", "#gya-bot-testing")

    # --- SLACK BLOCK KIT FORMATTING (Enhanced Command Center) ---
    slack_blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "content": "🕵️ GYA Nightly RAG Audit"}
        },
        {"type": "divider"}
    ]

    for item in reports_data:
        slack_blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "content": f"*Question:* _{item['question']}_\n*Diagnosis:* {item['reasoning']}\n*Required Fix:* `{item['fix_action']}`"
            }
        })
        slack_blocks.append({"type": "divider"})

    if not reports_data:
        slack_blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "content": "✅ *All systems nominal.* No RAG failures detected today! 🎉"}
        })

    slack.get_client().chat_postMessage(
        channel=target_channel,
        blocks=slack_blocks,
        text="Daily RAG Audit Report"
    )

    summary_md = "\n\n---\n\n".join([f"### Q: {r['question']}\n{r['reasoning']}\n**Fix:** {r['fix_action']}" for r in reports_data])

    return MaterializeResult(
        metadata={
            "failure_count": len(traces),
            "diagnostic_summary": MetadataValue.md(summary_md or "No failures discovered."),
            "slack_sent_to": target_channel
        }
    )


@asset(
    partitions_def=volume_partitions,
    deps=[
        AssetDep(
            "ingest", 
            partition_mapping=MultiToSingleDimensionPartitionMapping(partition_dimension_name="1_volume")
        )
    ]
)
def sweep_page_boundaries(context: AssetExecutionContext):
    """
    Scope: Per Volume
    sweep_page_boundaries.py --volume {x}
    Executes an LLM pass to resolve broken pronouns across page boundaries once the entire volume is ingested.
    """
    volume = context.partition_key
    
    cmd = [
        "python", os.path.join(SCRIPTS_DIR, "sweep_page_boundaries.py"),
        "--volume", str(volume)
    ]
    
    run_cli_script(context, cmd)


