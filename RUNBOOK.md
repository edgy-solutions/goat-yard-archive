# Extraction Pipeline Runbook

This document outlines the standard workflows for extracting, normalizing, and verifying markdown content from images.

## 1. Vision Model Extraction
**Script:** `read_images_baml.py`
**Purpose:** Uses OpenRouter/BAML vision models (e.g., Qwen) to extract raw markdown from page images.

### Common Commands

**Process specific pages (e.g., to fix specific failures):**
```powershell
python read_images_baml.py --pages 337,341,386,389 --force
```

**Process all images:**
```powershell
python read_images_baml.py
```

**Options:**
- `--pages`: Comma-separated list of page numbers to process (e.g. `100,101`).
- `--force`: Overwrite existing extraction files.
- `--model`: Specify model (default: `qwen/qwen3-vl-235b-a22b-thinking`).
- `--workers`: Number of parallel workers (default: 1).

---

## 2. Normalization
**Script:** `normalize_markdown.py`
**Purpose:** Cleans up the raw vision model output using an LLM (typically DeepSeek via Ollama/DSPy) to fix split words, formatting, and other OCR artifacts.

### Common Commands

**Normalize a specific file (Recommended for targeted fixes):**
```powershell
python normalize_markdown.py --file "extracted_images\qwen_qwen3-vl-235b-a22b-thinking\page337_image1.md" --force --backend dspy --model deepseek/deepseek-chat
```

**Normalize all files in a directory:**
```powershell
python normalize_markdown.py --dir "extracted_images\qwen_qwen3-vl-235b-a22b-thinking" --force --backend dspy --model deepseek/deepseek-chat
```

**Options:**
- `--file <path>`: Path to a single markdown file to normalize.
- `--dir <path>`: Path to directory of markdown files.
- `--force`: Overwrite existing `_normalized.md` files.
- `--backend`: Selection of backend, use `dspy` for local Ollama.
- `--model`: Model name for DSPy backend. **Always use** `deepseek/deepseek-chat` for this project.

---

## 3. Verification
**Script:** `verify_existing.py`
**Purpose:** Checks normalized files against the source logic to detect "hallucinations" (unauthorized changes) and content mismatches.

### Common Commands

**Run full verification:**
```powershell
python verify_existing.py
```

**Run verification and grep for specific page:**
```powershell
python verify_existing.py 2>&1 | Select-String "page337"
```

### Output Interpretation
- **OK**: File passed verification.
- **Unauthorized changes**: The normalized text differs significantly from the source in a way that wasn't expected (potential hallucination).
- **Text Mismatch**: Specific lines where source and output differ.
- **Footnote Mismatch**: Discrepancy between footnote markers references and definitions.
