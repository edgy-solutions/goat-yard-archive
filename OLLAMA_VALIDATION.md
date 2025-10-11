# Ollama Metadata Validation

This document describes the Ollama integration for validating OCR-extracted metadata.

## Overview

The script now supports optional validation of OCR metadata (book, chapter, verse, page number) using Ollama's vision model. This helps correct OCR errors by having a vision LLM review the image and extracted metadata.

## Setup

### 1. Install Dependencies

The BAML Python library has already been installed:
```bash
pip install baml-py
```

### 2. Install and Start Ollama

1. Download and install Ollama from https://ollama.ai
2. Pull the required model:
   ```bash
   ollama pull gpt-oss:20b
   ```
3. Start Ollama (it usually runs automatically, or run `ollama serve`)

### 3. BAML Configuration

The BAML configuration is located in `baml_src/main.baml` and defines:
- The Ollama client with `gpt-oss:20b` model
- The `ValidateOCRMetadata` function
- The `Metadata` class structure

The generated Python client is in the `baml_client/` directory.

## Usage

### Basic Usage (without validation)
```bash
python get_md.py images/page90_image1.png
```

### With Ollama Validation
```bash
python get_md.py images/page90_image1.png --validate-ollama
```

### Full Example with All Options
```bash
python get_md.py images/page90_image1.png --lang "eng+heb" --validate-ollama
```

## How It Works

1. **Step 1**: OCR with English only to extract metadata
   - Extracts book name, chapter, verse, and page number
   
2. **Step 2**: Ollama Validation (if `--validate-ollama` is used)
   - Sends the image and extracted metadata to Ollama
   - The vision model reviews the top of the image
   - Returns corrected metadata if any errors are found
   
3. **Step 3**: OCR with specified language(s) for content
   - Processes the full page content with multilingual support
   
4. **Step 4**: Hebrew verse extraction
   - Uses the validated metadata to fetch Hebrew verses from USFM files

## Output

When validation is enabled, you'll see output like:

```
Step 1: Running OCR with English to extract metadata...
Metadata extracted: book=GENESIS, ch=1, v=7-11, page=6

Step 3: Validating metadata with Ollama...
Ollama confirmed metadata is correct
```

Or if corrections are made:
```
Step 3: Validating metadata with Ollama...
Ollama corrected metadata:
  - chapter: 1 -> 2
  - verse: 7-11 -> 1-5
```

## Troubleshooting

### "BAML client not available"
- Run: `pip install baml-py`
- Regenerate client: `python -c "from baml_py import invoke_runtime_cli; import sys; sys.argv = ['baml', 'generate']; invoke_runtime_cli()"`

### "Ollama validation failed"
- Ensure Ollama is running: `ollama list` should show `gpt-oss:20b`
- Check Ollama is accessible: `curl http://localhost:11434`
- The script will fall back to OCR metadata if Ollama fails

### Changing the Model

Edit `baml_src/main.baml` and change the model name:
```baml
client<llm> Ollama {
  provider ollama
  options {
    model "your-model-name"  // Change this
    base_url "http://localhost:11434"
    temperature 0.1
  }
}
```

Then regenerate the client:
```bash
python -c "from baml_py import invoke_runtime_cli; import sys; sys.argv = ['baml', 'generate']; invoke_runtime_cli()"
```

## Performance Notes

- Validation adds ~2-5 seconds per image (depending on model)
- Use `--validate-ollama` only when you need higher accuracy
- For batch processing of many images, consider validating only problematic pages
