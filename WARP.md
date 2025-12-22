# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project overview

This repository implements a pipeline for extracting commentary text from scanned Bible PDFs into cleaned, structured markdown with rich metadata and original-language verses. The workflow combines:
- Local OCR (Tesseract via `pytesseract`)
- USFM source texts for Hebrew, Greek, and English
- LLM-based validation and extraction orchestrated through BAML

High-level flow:
- **PDF → images**: `extract_images.py` uses PyMuPDF (`fitz`) and Pillow to extract page images into an output directory (default `extracted_images_7/`).
- **Images → metadata**: `get_md.py` runs OCR on page images, infers book/chapter/verse/page metadata, optionally validates it with an Ollama-backed BAML function, and writes `<image>_metadata.json` plus optional OCR markdown.
- **USFM verse lookup & cleaning**: helpers in `get_md.py` read from `eng-kjv2006_usfm/`, `grctr_usfm/`, and `hbo_usfm/`, normalize book names, and produce clean Greek/Hebrew text by stripping USFM markup, Strong’s numbers, and footnotes.
- **Images + metadata → final markdown**: `read_images_baml.py` (preferred) and the legacy `read_images.py` load images and metadata and call a vision LLM to produce single-column markdown with linked footnotes, using metadata, OCR output, and original-language verses as context.
- **Backfill & maintenance utilities**: scripts such as `update_metadata_text.py` and tests in `test_*.py` keep existing metadata in sync with the latest USFM-cleaning logic and guard against regressions.

## Key directories and files

### BAML configuration and client

- `baml_src/main.baml`
  - Defines the `Metadata` class (book, chapter, verse, page_number) used for OCR header metadata.
  - Defines two key BAML functions:
    - `ValidateOCRMetadata(image, ocr_metadata: Metadata) -> Metadata`
      - Uses the `Ollama` client (OpenAI-compatible endpoint) to inspect the image header and correct the OCR-derived metadata, including chapter-spanning notation like `"27:42-46,28:1"`.
    - `ExtractTextFromImage(image, book?, chapter?, verse?, page_number?, hebrew_text?, greek_text?, ocr_text?) -> string`
      - Uses the `OpenRouter` client (vision LLM) and a rich prompt that:
        - Forces a **single-column** output by reading the left column top-to-bottom, then the right column.
        - Preserves Greek/Hebrew/Arabic segments, especially in footnotes.
        - Normalizes footnote lettering (lowercase a/b/c, etc.) and appends footnotes after their paragraph/section.
        - Optionally inlines metadata, original Hebrew/Greek verses, and OCR output as context blocks.
- `baml_client/`
  - Auto-generated Python client for the BAML spec.
  - `sync_client.py` / `async_client.py`: expose `ExtractTextFromImage` and `ValidateOCRMetadata` to Python.
  - `__init__.py` ensures the installed `baml-py` version matches the generator and re-exports client objects.
  - **Do not edit files in `baml_client/` directly**; instead, edit `baml_src/main.baml` and regenerate.

### OCR and metadata pipeline

- `get_md.py`
  - Central script for generating and validating metadata for a page image.
  - Key responsibilities:
    - Configures Tesseract via `pytesseract.pytesseract.tesseract_cmd` (currently hard-coded to `C:\\Program Files\\Tesseract-OCR\\tesseract.exe`).
    - Provides logging helpers (`log_print`, `set_log_file`, `close_log_file`) to mirror output to a timestamped log file.
    - Maintains a canonical `BIBLE_BOOK_ORDER` and helper functions such as `get_next_book` and `verse_has_restarted`.
    - Normalizes book names (e.g., handling `"ST. MATTHEW"`, `"St. John"`, etc.) via `normalize_book_name()`, which feeds `is_old_testament()` / `is_new_testament()` and USFM lookups.
    - Parses USFM source files to fetch Hebrew and Greek verses, using `clean_usfm_text()` to:
      - Strip USFM word markers (`\w`, `\w*`).
      - Remove Strong’s numbers (`|strong="G####"` / `|strong="H####"`).
      - Remove textual-variant footnotes (`\f ... \f*`).
      - Normalize whitespace while preserving actual words, punctuation, and ordering.
    - Integrates with BAML (when available) to:
      - Call `ValidateOCRMetadata` via the synchronous client if `--validate-ollama` is requested.
      - Use corrected book/chapter/verse/page when fetching Hebrew verses and writing metadata.
  - Writes metadata JSON sidecars next to images (e.g., `page100_image1_metadata.json`) containing fields like `book_name`, `chapter`, `verse`, `page_number`, `hebrew_text`, etc.

- `verse_notation.py`
  - Encapsulates parsing and normalization of verse notation strings used in metadata and BAML prompts.
  - Handles:
    - Single verses (`"3"`).
    - Ranges (`"3-5"`).
    - Lists (`"3,4,5"`).
    - Chapter-spanning notation (`"27:42-46,28:1"` for verses 42–46 of chapter 27 and verse 1 of chapter 28).
  - Used by `get_md.py` and tests to interpret and validate complex verse ranges.

### Image → markdown extraction scripts

- `read_images_baml.py` (preferred extractor)
  - Uses `baml_client`’s `ExtractTextFromImage` for each image.
  - Reads image metadata JSON, original Hebrew/Greek text, and optional OCR `.md` content to build the BAML call.
  - Supports filtering by:
    - `--directory/-d` (default: `extracted_images`).
    - `--model/-m` (OpenRouter model name, default from `main.baml`).
    - `--book/-b`, `--chapter-start/-cs`, `--chapter-end/-ce` to select subsets of pages.
  - Tracks usage and cost by polling the OpenRouter Activity API after each call, writing:
    - A `metrics.jsonl` file (one JSON record per image with timestamp, model, tokens, and cost).
    - A session log `processing_<model>_<timestamp>.log` with filtering decisions, per-image processing details, costs, and warnings.
  - Writes one markdown file per processed image (`<image_name>.md`).

- `read_images.py` (legacy extractor)
  - Older script that talks to OpenRouter directly using constructed HTTP payloads instead of BAML.
  - Provides the original implementation of image filtering by book and chapter, as documented in `FILTERING_README.md`.
  - Kept for reference and as a non-BAML fallback; new work should prefer `read_images_baml.py`.

### Data directories

- `eng-kjv2006_usfm/`, `grctr_usfm/`, `hbo_usfm/`
  - USFM source texts for English KJV, Greek, and Hebrew used by `get_md.py` when pulling canonical verses.
- `extracted_images/`, `extracted_images_7/`
  - Working directories where `extract_images.py` and downstream scripts read/write:
    - `page{N}_image{M}.png` page images.
    - `page{N}_image{M}_metadata.json` metadata sidecars.
    - `page{N}_image{M}.md` OCR or LLM-generated markdown.
- `backup/`, `outputs/`, `ocr/`
  - Miscellaneous intermediate outputs, logs, or historical artifacts; check contents before assuming they’re authoritative.

### Utilities and tests

- `extract_images.py`
  - Opens a PDF via PyMuPDF and writes each embedded image as `page{page}_image{index}.{ext}` to an output directory (default `extracted_images_7/`).
- `update_metadata_text.py`
  - Walks one file or directory of existing metadata JSON files and re-populates the Greek/Hebrew text fields using the current `clean_usfm_text()` and verse lookup logic.
  - Skips files that are already in the new cleaned format.
- `test_usfm_cleaning.py`, `test_greek_extraction.py`, `test_footnote_fix.py`
  - Pytest-style tests that:
    - Verify USFM cleaning removes markup and Strong’s numbers.
    - Verify ST-prefix normalization (e.g., `"ST. MATTHEW"`) and verse extraction across Hebrew/Greek.
    - Verify USFM footnote removal.

## Commands

### Environment and setup

- This is a Python project; a local virtual environment is already present as `.venv/`.
  - On Windows PowerShell, you can activate it from the repo root with:
    - `.\u005c.venv\Scripts\Activate.ps1`
- Ensure Tesseract OCR is installed and available at the path used in `get_md.py` (currently `C:\\Program Files\\Tesseract-OCR\\tesseract.exe`). Update that constant if your installation lives elsewhere.
- The BAML Python runtime must be installed for any BAML-dependent scripts:
  - `pip install baml-py`

### Regenerating the BAML client

After editing `baml_src/main.baml`, regenerate the client code in `baml_client/`.

Common options:
- If `baml-cli` is available in the virtualenv:
  - `.venv\Scripts\baml-cli.exe generate`
- If you prefer to invoke via Python (as used in docs):
  - `python -c "from baml_py import invoke_runtime_cli; import sys; sys.argv = ['baml', 'generate']; invoke_runtime_cli()"`

Do **not** edit files under `baml_client/` directly; re-run the generator instead.

### Running tests

Tests are simple `pytest` modules in the repo root.

- Run the full suite from the project root:
  - `python -m pytest`
- Run a single test file:
  - `python -m pytest test_greek_extraction.py`
- Run a specific test within a file (pattern match):
  - `python -m pytest test_usfm_cleaning.py -k "hebrew"`

There is no dedicated linting or formatting configuration checked into this repo; use your preferred tools as needed.

### Core workflows

#### 1. Extract images from a PDF

- Edit `extract_images.py` if needed to point `pdf_file` at the desired source PDF.
- Then run from the project root:
  - `python extract_images.py`
- Images will be written into `extracted_images_7/` (by default) as `page{page}_image{index}.png`.

#### 2. Generate metadata for a page image

- Basic OCR + metadata extraction for a single image:
  - `python get_md.py path\to\page_image.png`
- With Ollama-based metadata validation:
  - `python get_md.py path\to\page_image.png --validate-ollama`
- With custom OCR language configuration (example from docs):
  - `python get_md.py path\to\page_image.png --lang "eng+heb" --validate-ollama`

The script will produce a `<image>_metadata.json` file containing book name, chapter, verse notation (including chapter-spanning patterns), page number, and cleaned Hebrew/Greek text where available.

#### 3. Backfill existing metadata with cleaned text

Use `update_metadata_text.py` to apply the latest USFM-cleaning logic to older metadata JSON files.

Examples:
- Update a single metadata file:
  - `python update_metadata_text.py path\to\file_metadata.json`
- Update all metadata files in a directory tree:
  - `python update_metadata_text.py path\to\directory`

#### 4. Extract commentary text with BAML (preferred)

Use `read_images_baml.py` to process images and their metadata into final markdown using BAML + OpenRouter.

Common patterns (from `BAML_INTEGRATION_README.md`):
- Process all images in the default directory:
  - `python read_images_baml.py`
- Restrict to a specific book and chapter range:
  - `python read_images_baml.py -b Genesis -cs 1 -ce 3`
- Override the model:
  - `python read_images_baml.py -m qwen/qwen3-vl-235b-a22b-thinking`
- Use a custom image directory:
  - `python read_images_baml.py -d ./my_images`

Outputs include one markdown file per image plus a `metrics.jsonl` file and a `processing_<model>_<timestamp>.log` summarizing filtering and cost/usage information.

#### 5. Legacy extraction script (non-BAML)

The older `read_images.py` script provides a direct OpenRouter integration and the original implementation of image filtering by book and chapter.

Typical usage (from `FILTERING_README.md`):
- Process all images with metadata in the default directory:
  - `python read_images.py`
- Filter by book:
  - `python read_images.py --book Genesis`
- Filter by chapter range:
  - `python read_images.py --chapter-start 1 --chapter-end 3`
- Combine filters and shorthand flags:
  - `python read_images.py -b Exodus -cs 20 -ce 40`

Prefer `read_images_baml.py` for new work; keep `read_images.py` as a reference and fallback.

### External services and configuration notes

- **OpenRouter**
  - `OpenRouter` in `main.baml` is configured as an OpenAI-compatible client against `https://openrouter.ai/api/v1`.
  - Calls rely on the `OPENROUTER_API_KEY` environment variable being set in the runtime environment.
  - Cost and token usage are tracked by polling the OpenRouter Activity API in `read_images_baml.py`.

- **Ollama / vision model for metadata validation**
  - The `Ollama` client in `main.baml` targets an OpenAI-compatible endpoint (currently a local/remote instance serving `qwen2.5vl:32b`).
  - If you change model or base URL, update the `client<llm> Ollama` block in `baml_src/main.baml` and regenerate the client.
  - `get_md.py` uses BAML’s `ValidateOCRMetadata` function when run with `--validate-ollama` to correct book/chapter/verse/page metadata.

- **Tesseract**
  - `get_md.py` assumes a Windows Tesseract install at `C:\\Program Files\\Tesseract-OCR\\tesseract.exe`.
  - Update `pytesseract.pytesseract.tesseract_cmd` if Tesseract lives in a different location on your machine.
