# AI Workspace Guardrails & Workflow Guide (`AGENTS.md`)

This document is to be utilized by autonomous agents navigating the repository to avoid catastrophic mistakes, enforce workflow safety, and provide technical guidance when executing the ingestion data pipelines.

## Critical Safety Restrictions
1. **Do not destruct pipeline data**. Never execute `rm -rf` against `extracted_images/` or any `volumeN/` output directory without explicit instruction.
2. **Weaviate Data**. `ingest.py` pushes aggressively to Weaviate. If you re-ingest data, understand that it will either update or duplicate entities. Be extremely careful when executing `purge_weaviate.py`.
3. **BAML Runtime Generation**. If you change `baml_src/main.baml`, you *must* run `baml-cli generate` inside the Python virtual environment before deploying or testing dependent logic (`get_md.py`, `read_images_baml.py`).
4. **Dagster**. The primary data extraction processes have been relocated to `gill_commentary_pipeline/scripts/` and wrapped within Dagster (`assets.py`). Use `dagster dev` to execute the pipeline over orchestrating individual scripts with ad-hoc Python loops unless testing logic for `--page`.

---

## 🚀 The Ingestion Runbook

The pipeline transforms raw PDFs of John Gill's Commentary into a vector database full of strict references to coordinates and verses.

*All scripts are executed against `gill_commentary_pipeline/scripts/*` or via Dagster.*

### Step 1: Source Extraction
- **Action**: Extract PNGs from PDF.
- **Subprocess**: `extract_images.py [Volume_Int]`
- **Yields**: `pageXXX_imageY.png` in `volumeX/`.

### Step 2: Meta/OCR Generation
- **Action**: Extracts metadata and Tesseract word-level bounding boxes.
- **Subprocess**: `get_md.py --image path/to/page.png [--validate-ollama]`
- **Yields**: `_metadata.json` (resolving Chapter/Verse/Page natively and via USFM original texts) & `_ocr.json`.

### Step 3: Vision Model Text Extraction
- **Action**: Extracts markdown explicitly through BAML integration (OpenRouter).
- **Subprocess**: `read_images_baml.py [-b Book] [-cs ChapterStart] [-ce ChapterEnd] [--page page_ID]`
- **Yields**: Raw `.md` text representing the page image in strictly single-column layout, moving footnotes cleanly.

### Step 4: OCR Fixup / Reindex
- **Action**: Uses text as ground truth to order and normalize spatial data.
- **Subprocess 1**: `reindex_ocr.py` translates columns into coherent flow.
- **Subprocess 2**: `fixup_ocr.py` bridges the Vision LLM strings (`.md`) to the ordered Tesseract boxes (`_reindexed.json`), emitting `_fixedup.json`.

### Step 5: Markdown Normalization & Verification (Optional)
- **Action**: Fixes broken 18th-century ligatures via DeepSeek DSPy logic.
- **Subprocess 1**: `normalize_markdown.py --dir [.../qwen_...] --backend dspy --model deepseek/deepseek-chat`
- **Subprocess 2**: `verify_existing.py` checks against sources to catch hallucinations.

### Step 6: Verse Alignment
- **Action**: Slices the page content down into isolated verses, mapping coordinates specifically for UI highlighting rendering later.
- **Subprocess**: `align_verses.py --dir volumeX/` -> outputs to `artifacts/alignment/volumeX/`.

### Step 7: Final DB Ingestion
- **Action**: Pushes data to `Weaviate` locally.
- **Subprocess**: `ingest.py --data-dir volumeX/ --alignment-dir artifacts/alignment/volumeX/`
- **Output**: Populates `TheologicalEntity` vertices (BAML extraction) and `CommentaryChunk` edges inside the Database.
- **Disambiguation Note**: Relies on a "Lookup-Before-Create" pattern or BAML's `biblical_era`/`role` metadata to prevent merging ambiguous entities (e.g., `JOSEPH_OT` vs `JOSEPH_NT`).

*Warning: Step 7 natively creates `Sentence-Level Granularity` inside Weaviate explicitly needed by the `DSPy` Retrieval QA Bot.*

## 🧪 Quick Test/Verification Tasks
- Verify BAML function syntax is safe: `baml-cli check`.
- Query current LLM cost stats from pipeline ingestion runs: `cat metrics.jsonl`.
- Confirm USFM clean status: `python -m pytest test_usfm_cleaning.py`.
