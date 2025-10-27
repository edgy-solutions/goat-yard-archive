# BAML Integration for Image Text Extraction

## Overview

The new `read_images_baml.py` script uses the BAML library to handle all prompt management and API calls to OpenRouter, simplifying the code and making it more maintainable.

## Key Differences from Original Script

### **1. BAML Handles All Prompts**
- The prompt is defined in `baml_src/main.baml` in the `ExtractTextFromImage` function
- No need to construct prompts manually in Python code
- BAML automatically handles image encoding and API communication

### **2. Cost Tracking via Activity API**
Since BAML abstracts the API response, we fetch cost data from OpenRouter's Activity API:
- Script records timestamp before BAML call
- After BAML returns, queries Activity API for matching generation
- Extracts cost, tokens, and generation_id from activity data
- Falls back gracefully if activity data isn't available yet

### **3. Simplified Code Structure**
```python
# Old approach (manual API calls)
payload = {...}
response = requests.post(url, json=payload)
result = response.json()
text = result['choices'][0]['message']['content']

# New approach (BAML)
baml_image = Image.from_path(str(png_file))
extracted_text = b.ExtractTextFromImage(baml_image, {...})
```

## Usage

### **Basic Usage**
```bash
python read_images_baml.py
```

### **With Filters**
```bash
# Process specific book and chapter
python read_images_baml.py -b Genesis -cs 1 -ce 3

# Process with specific model
python read_images_baml.py -m qwen/qwen3-vl-235b-a22b-thinking

# Custom directory
python read_images_baml.py -d ./my_images
```

### **Command-Line Options**
- `-d, --directory`: Directory containing images (default: `extracted_images`)
- `-m, --model`: Model to use (default: `qwen/qwen3-vl-235b-a22b-thinking`)
- `-b, --book`: Filter by book name (e.g., Genesis)
- `-cs, --chapter-start`: Start chapter (inclusive)
- `-ce, --chapter-end`: End chapter (inclusive)

## Activity API Integration

### **How It Works**
1. Script records `start_time = datetime.utcnow()` before BAML call
2. BAML makes the API call and returns extracted text
3. Script queries OpenRouter Activity API:
   ```
   GET https://openrouter.ai/api/v1/activity
   ```
4. Finds matching generation by:
   - Model name match
   - Timestamp within 2 minutes of start_time
5. Extracts cost and token data from activity response

### **Activity API Response Fields Used**
```json
{
  "generation_id": "gen-1761521740-...",
  "model": "qwen/qwen3-vl-235b-a22b-thinking",
  "tokens_prompt": 4369,
  "tokens_completion": 4953,
  "usage": 0.0107241,  // Cost in dollars
  "created_at": "2025-10-26T23:36:56.132102+00:00"
}
```

### **Fallback Behavior**
- Waits up to 10 seconds for generation to appear in activity log
- If not found, logs warning and continues with cost=0
- Processing continues regardless of cost fetch success

## Metadata Handling

### **With Filters**
When filters are specified (`--book`, `--chapter-start`, `--chapter-end`):
- Only processes images WITH metadata that match the filter
- Skips images without metadata

### **Without Filters**
When no filters specified:
- Processes ALL images regardless of metadata
- Logs "No metadata available" for images without metadata

## Prompt Management

The prompt is defined in `baml_src/main.baml`:

```baml
function ExtractTextFromImage(image: image) -> string {
  client OpenRouter
  
  prompt #"
    Extract the text from the image in markdown format...
    
    IMPORTANT: The image has TWO COLUMNS but you must MERGE them...
    
    FOOTNOTES: The footnotes ONLY use lower case lettering...
    
    {{ _.role("user") }}
    {{ image }}
  "#
}
```

### **Updating the Prompt**
1. Edit `baml_src/main.baml`
2. Regenerate client: `.venv\Scripts\baml-cli.exe generate`
3. Run script - changes take effect immediately

## Output Files

### **Metrics File** (`metrics.jsonl`)
```json
{
  "timestamp": "2025-10-26T19:56:16.123456",
  "file": "page001.png",
  "model": "qwen/qwen3-vl-235b-a22b-thinking",
  "generation_id": "gen-1761521740-...",
  "tokens": {
    "prompt": 4369,
    "completion": 4953,
    "total": 9322
  },
  "cost": 0.0107241,
  "success": true
}
```

### **Log File** (`processing_<model>_<timestamp>.log`)
- Session start/end
- Filtering information
- Per-image processing details
- Cost and token information
- Errors and warnings

### **Extracted Text** (`<image_name>.md`)
- Markdown formatted text
- One file per processed image

## Advantages

### **1. Maintainability**
- Prompts managed in BAML files (version controlled, easy to edit)
- No manual payload construction
- Automatic error handling by BAML library

### **2. Consistency**
- Single source of truth for prompts (BAML file)
- No risk of script and BAML file getting out of sync

### **3. Flexibility**
- Easy to switch models via command line
- Can add new BAML functions without changing Python code
- Prompt updates only require BAML regeneration

### **4. Robustness**
- BAML handles retries and connection issues
- Activity API provides authoritative cost data
- Graceful fallback if cost fetch fails

## Migration from Original Script

The original `read_images.py` still works but uses manual API calls. To migrate:

1. **Update your workflow** to use `read_images_baml.py`
2. **Keep the same command-line arguments** (compatible)
3. **Prompts now managed** in `baml_src/main.baml`
4. **Cost tracking** via Activity API instead of direct response

## Troubleshooting

### **"Could not fetch cost data from activity API"**
- Generation hasn't appeared in activity log yet (rare)
- Processing continues with cost=0
- Check OpenRouter dashboard for actual costs

### **"No images to process after applying filters"**
- Images don't have metadata JSON files
- Metadata doesn't match filter criteria
- Run without filters to process all images

### **BAML errors**
- Check `OPENROUTER_API_KEY` is set correctly
- Verify BAML client is generated: `baml-cli generate`
- Check model name is valid for OpenRouter

## Future Enhancements

Possible improvements:
1. Add retry logic for activity API fetch
2. Cache activity API responses to reduce API calls
3. Support batching multiple images per API call
4. Add streaming support for real-time output
5. Integrate OCR and Hebrew text into BAML function parameters
