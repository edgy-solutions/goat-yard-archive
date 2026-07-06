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
def entity_normalization_global(context: AssetExecutionContext):
    """
    Scope: Global
    Backfill search_key + categories on existing entities, then auto-merge fragments.

    Implements ADR-0005 Phase 3. Replaces the old scan_duplicate_entities_global
    (which only WARNED about fragmentation); this asset actively fixes it
    according to the conservative auto-merge rules in
    backfill_entity_search_keys.py.

    Idempotent: re-runs only touch entities that need backfilling or auto-merging.
    Surfaces flagged-for-review groups (incompatible roles) as Dagster metadata
    so they're visible without grepping logs.
    """
    cmd = [
        "python", os.path.join(SCRIPTS_DIR, "backfill_entity_search_keys.py"),
    ]
    output = run_cli_script(context, cmd)

    import re
    metadata = {"Status": "Success"}

    m = re.search(r"populated search_key on\s*:\s*(\d+)", output)
    if m:
        metadata["search_key Populated"] = int(m.group(1))
    m = re.search(r"seeded categories on\s*:\s*(\d+)", output)
    if m:
        metadata["categories Seeded"] = int(m.group(1))
    m = re.search(r"groups auto-merged\s*:\s*(\d+)", output)
    if m:
        metadata["Groups Auto-Merged"] = int(m.group(1))
    m = re.search(r"fragment entities removed\s*:\s*(\d+)", output)
    if m:
        metadata["Fragments Removed"] = int(m.group(1))
    m = re.search(r"chunk references repointed\s*:\s*(\d+)", output)
    if m:
        metadata["Chunk Refs Repointed"] = int(m.group(1))
    m = re.search(r"groups flagged for review\s*:\s*(\d+)", output)
    if m:
        flagged = int(m.group(1))
        metadata["Flagged For Review"] = flagged
        if flagged > 0:
            metadata["Status"] = f"Success - {flagged} group(s) need manual review"

    return MaterializeResult(metadata=metadata)


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

    # 1. Fetch traces from last 24h that failed (score = 0).
    # Bug fix 2026-07-06: previous code called langfuse.get_traces(...)
    # which does NOT exist in the current SDK — the read-side API lives
    # under langfuse.api.trace.list(...) and langfuse.api.trace.get(...).
    # This asset was silently broken since a Langfuse SDK upgrade;
    # corrected in the same pass that ships the Zone-3 5b + 5c samplers.
    env_tag = os.getenv("APP_ENV", "production")
    traces = []
    page = 1
    while True:
        traces_response = langfuse.api.trace.list(
            tags=[env_tag, "v7_launch"],
            page=page,
            limit=50,
        )
        batch = getattr(traces_response, "data", []) or []
        # Filter to failed traces (retrieval_success score == 0) client-side;
        # the current SDK's list() doesn't take score filters directly.
        for t in batch:
            scores = getattr(t, "scores", None) or []
            hit = any(
                (getattr(s, "name", None) == "retrieval_success"
                 and getattr(s, "value", None) == 0)
                for s in scores
            )
            if hit:
                traces.append(t)
        if not batch:
            break
        if len(batch) < 50 or page >= 10:
            break
        page += 1

    reports_data = []

    for trace in traces:
        question = trace.input if isinstance(trace.input, str) else trace.input.get("query", "Unknown Query") if isinstance(trace.input, dict) else "Unknown Query"

        # Discover weaviate retrieval output
        retrieval_context = "No context found in trace"
        try:
            full_trace = langfuse.api.trace.get(trace_id=trace.id)
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


@asset(group_name="operations", required_resource_keys={"slack"})
def daily_eval_zone3_report(context: AssetExecutionContext):
    """Daily eval-set replay Zone-3 judge (ADR-0008 Phase 1 Step 5c).

    The controlled-baseline instrument that complements the 5b production
    sampler. Runs the 28 curated eval-set questions through the deployed
    bot and judges each answer N=3 times. Same DailyReport shape as 5b
    so the reports are directly comparable.

    Value at low traffic: 5b can go days seeing 0-3 answers; 5c gives
    28 controlled answers × 3 judges = 84 verdicts of consistent
    measurement daily, on inputs we chose. Together they cover both
    'is the instrument stable on my substrate?' and 'is real traffic
    faithful?' — two different questions.

    Also fires the escalation alert on any unsupported flag (bias
    toward sensitivity per the review's discipline).
    """
    try:
        from evals.zone3_eval_replay import build_eval_replay_report, format_slack_blocks
        from evals.zone3_judge_prod_sampler import post_escalation_alert
    except ImportError as e:
        context.log.warning(f"Eval-replay import failed: {e}")
        return MaterializeResult(
            metadata={"status": "skipped", "reason": f"missing dependency: {e}"}
        )

    slack: SlackResource = context.resources.slack
    report = build_eval_replay_report()
    blocks = format_slack_blocks(report)

    target_channel = os.getenv("SLACK_DIAGNOSTICS_CHANNEL", "#gya-bot-testing")
    try:
        slack.get_client().chat_postMessage(
            channel=target_channel,
            blocks=blocks,
            text="Daily Zone-3 Eval-Set Replay",
        )
    except Exception as e:
        context.log.warning(f"Slack post failed: {e}")

    # Separate high-visibility alert if any escalations. Fires
    # independently of anyone reading the summary — the safety net that
    # works at any traffic level.
    if report.escalations:
        try:
            post_escalation_alert(
                slack_client=slack.get_client(),
                channel=target_channel,
                report=report,
                source_label="eval_replay",
            )
        except Exception as e:
            context.log.warning(f"Escalation alert failed: {e}")

    return MaterializeResult(
        metadata={
            "cases_run": report.total_answers_sampled,
            "unsupported_escalations": len(report.escalations),
            "majority_supported_rate": round(report.majority_supported_rate, 4),
            "any_flag_supported_rate": round(report.any_flag_supported_rate, 4),
            "supported_rate_gap": round(report.supported_rate_gap, 4),
            "trailing_prose_excised": report.total_trailing_prose_excised,
            "disclaimer_preserved": report.total_disclaimer_preserved,
            "other_zone3_excised": report.total_other_excised,
            "judge_errors": report.judge_error_count,
            "slack_sent_to": target_channel,
        }
    )


@asset(group_name="operations", required_resource_keys={"slack"})
def daily_zone3_judge_report(context: AssetExecutionContext):
    """Daily Zone-3 semantic judge over sampled production traffic
    (ADR-0008 Phase 1 Step 5b).

    Queries Langfuse for the last 24h of /api/search generations, applies
    the calibrated Zone-3 judge N=3 times per answer (per the 2026-07-06
    review's correction — single-judge rates carry per-answer noise that
    would swamp the erosion signal supported_characterization_rate exists
    to detect), and posts a Slack summary with:

      - Pod commit SHA(s) that generated the sampled traffic (permanent
        fix for the stale-prod trap — every daily post announces which
        build was serving)
      - Amendment excision counts (trailing-prose fires, disclaimer
        preservations) — how the runtime layer's amendments actually get
        exercised on real traffic
      - Per-SHA supported-verdict distribution across N=3 judge runs
      - Escalations: any answer where at least one of the 3 judge runs
        flagged unsupported (credibility-harm bias toward sensitivity
        per review)

    Kept as a thin wrapper over `evals.zone3_judge_prod_sampler.build_report`
    so all logic is unit-testable without Dagster + Langfuse mocks.
    """
    try:
        from evals.zone3_judge_prod_sampler import (
            build_report, format_slack_blocks, post_escalation_alert,
        )
    except ImportError as e:
        context.log.warning(f"Zone-3 sampler import failed: {e}")
        return MaterializeResult(
            metadata={"status": "skipped", "reason": f"missing dependency: {e}"}
        )

    slack: SlackResource = context.resources.slack
    report = build_report(hours=24)
    blocks = format_slack_blocks(report)

    target_channel = os.getenv("SLACK_DIAGNOSTICS_CHANNEL", "#gya-bot-testing")
    try:
        slack.get_client().chat_postMessage(
            channel=target_channel,
            blocks=blocks,
            text="Daily Zone-3 Judge Report",
        )
    except Exception as e:
        context.log.warning(f"Slack post failed (report metadata still returned): {e}")

    # Separate high-visibility escalation alert. Fires whether or not
    # anyone reads the daily summary — this is the safety net that
    # works at any traffic level (including zero real traffic on a
    # low-volume tool). Bias toward sensitivity per review: any single
    # unsupported flag on any answer triggers the alert.
    if report.escalations:
        try:
            post_escalation_alert(
                slack_client=slack.get_client(),
                channel=target_channel,
                report=report,
                source_label="production",
            )
        except Exception as e:
            context.log.warning(f"Escalation alert failed: {e}")

    return MaterializeResult(
        metadata={
            "answers_sampled": report.total_answers_sampled,
            "commit_shas": report.commit_sha_summary_line,
            "unsupported_escalations": len(report.escalations),
            "majority_supported_rate": round(report.majority_supported_rate, 4),
            "any_flag_supported_rate": round(report.any_flag_supported_rate, 4),
            "supported_rate_gap": round(report.supported_rate_gap, 4),
            "trailing_prose_excised": report.total_trailing_prose_excised,
            "disclaimer_preserved": report.total_disclaimer_preserved,
            "other_zone3_excised": report.total_other_excised,
            "judge_errors": report.judge_error_count,
            "max_cap_hit": report.max_answers_hit,
            "slack_sent_to": target_channel,
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


