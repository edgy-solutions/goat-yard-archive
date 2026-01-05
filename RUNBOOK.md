# Extraction Pipeline Runbook

This document outlines the full end-to-end pipeline for processing Gill Commentary volumes, from raw PDF to database ingestion.

## Pipeline Overview

1.  **Source Extraction**: Extract page images from PDF.
2.  **Metadata & Raw OCR**: Generate metadata and initial OCR bounding boxes.
3.  **Vision Model Extraction**: Extract high-quality text using Vision LLMs.
4.  **OCR Post-Processing**: Reorder and fix OCR data using Vision text as the "source of truth".
5.  **Normalization**: cleaning up Vision output (optional/parallel).
6.  **Alignment**: Map verse text to exact bounding boxes on the page.
7.  **Ingestion**: Load aligned data into the database and vector store.

---

## 1. Source Extraction
**Script:** `extract_images.py`
**Input:** PDF Volume (e.g., `docs/Volume7.pdf`)
**Output:** PNG Images in `volume7/`

Extracts individual pages as high-resolution PNGs.

```powershell
python extract_images.py 7
# Output: $COMMENTARY_DATA_DIR/volume7/page403_image7.png
```

---

## 2. Metadata & Raw OCR Generation
**Script:** `get_md.py`
**Input:** PNG Images
**Output:** `_metadata.json` and `_ocr.json` (Tesseract)

Performs two critical functions:
1.  **Metadata**: Identifies Book, Chapter, Verse, and Page Number from header text.
2.  **Raw OCR**: Runs Tesseract to generate word-level bounding boxes (`_ocr.json`).

*Note: This step is a prerequisite for Vision extraction as it generates the required metadata.*

```powershell
# Run on specific image
python get_md.py --image "volume7/page403_image7.png"

# Batch run (usually orchestrated via shell script or manual loop)
# Checks for existing files by default
```

---

## 3. Vision Model Extraction
**Script:** `read_images_baml.py` (Preferred) or `read_images.py`
**Input:** PNG Images + `_metadata.json`
**Output:** Raw Markdown (`.md`) in `volume7/qwen_qwen3.../`

Uses OpenRouter/BAML vision models (e.g., Qwen) to extract raw markdown from page images. This text is high quality but fails to provide bounding boxes.

```powershell
# Process all specific pages
python read_images_baml.py --pages 403

# Process all images in default directory
python read_images_baml.py
```

**Options:**
- `--pages`: Comma-separated list of page numbers.
- `--model`: Defaults to `qwen/qwen3-vl-235b-a22b-thinking`.

---

## 4. OCR Post-Processing
These intermediate scripts refine the raw Tesseract OCR to match the high-quality Vision text.

### 4a. Reindex OCR
**Script:** `reindex_ocr.py`
**Input:** `_ocr.json` (Raw Tesseract)
**Output:** `_reindexed.json` (Corrected Reading Order)

Sorts the raw Tesseract bounding boxes into logical reading order (Column 1 -> Column 2 -> Footnotes), fixing chaos caused by multi-column layouts.

```powershell
python reindex_ocr.py --extracted-dir "$COMMENTARY_DATA_DIR/volume7"
```

### 4b. Fixup OCR
**Script:** `fixup_ocr.py`
**Input:** `_reindexed.json` + `_normalized.md` (or raw `.md` from Vision)
**Output:** `_fixedup.json`

Merges the spatial data (OCR) with the correct text (Vision Markdown). It aligns the OCR words sequences "Vision Text", effectively giving us "Vision Accuracy" with "OCR Coordinates".

```powershell
python fixup_ocr.py --extracted-dir "$COMMENTARY_DATA_DIR/volume7" --markdown-dir "$COMMENTARY_DATA_DIR/volume7/qwen_qwen3-vl-235b-a22b-thinking"
```

---

## 5. Normalization
**Script:** `normalize_markdown.py`
**Input:** Raw Markdown (`.md`)
**Output:** `_normalized.md`

Cleans up the raw vision model output using an LLM (typically DeepSeek) to fix split words, formatting, and other artifacts.

```powershell
python normalize_markdown.py --dir "$COMMENTARY_DATA_DIR/volume7/qwen_qwen3-vl-235b-a22b-thinking" --force --backend dspy --model deepseek/deepseek-chat
```

---

## 6. Verification
**Script:** `verify_existing.py`
**Input:** `_normalized.md`
**Output:** Verification Report

Checks normalized files against source logic to detect hallucinations or content/footnote mismatches.

```powershell
python verify_existing.py
```

---

## 7. Verse Alignment
**Script:** `align_verses.py`
**Input:** `_fixedup.json` (or `_reindexed.json`) + `_metadata.json`
**Output:** `artifacts/alignment/volume7/...` (Verse-level JSONs)

Identifies the exact bounding box on the page for each verse. It uses the "Fixed Up" OCR data to perform fuzzy text matching against the known Verse text.

```powershell
python align_verses.py --dir "$COMMENTARY_DATA_DIR/volume7"
```

---

## 8. Database Ingestion
**Script:** `ingest.py`
**Input:** `artifacts/alignment/...` + `volume7` (for images)
**Output:** Populates Weaviate and Neo4j

Final step. Takes the aligned verse data and images, creating:
1.  **SourceSlide**: The image crop of the verse.
2.  **Verse Entity**: The text and metadata in the database.

```powershell
python ingest.py --data-dir "$COMMENTARY_DATA_DIR/volume7" --alignment-dir "$COMMENTARY_DATA_DIR/artifacts/alignment/volume7"
```
