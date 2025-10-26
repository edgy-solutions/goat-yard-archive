# Cost Tracking and Metrics in read_images.py

## Features Added

### 1. **Model Selection with Pricing**
- Shows estimated cost per image for each model during selection
- Displays model ID for reference
- Estimated based on typical usage (~1500 prompt tokens, ~1000 completion tokens)
- Helps make cost-informed decisions before processing

### 2. **Per-Image Cost Calculation**
- Displays cost for each image processed
- Shows token breakdown (prompt + completion tokens)
- Real-time cost display during processing

### 3. **Comprehensive Metrics Logging**
Every image processed is logged to `metrics.jsonl` in the model output directory with:
- Timestamp
- Filename
- Model used
- Token usage (prompt, completion, total)
- Calculated cost
- Success/failure status
- Error messages (if any)

### 4. **Processing Summary**
After all images are processed, displays:
- Total images processed
- Total token usage
- Total cost
- Location of metrics file

### 5. **Pricing Information**
- Automatically fetches pricing from OpenRouter API
- Displays pricing in model selection list
- Shows detailed pricing before processing starts
- Calculates costs based on:
  - Prompt tokens
  - Completion tokens
  - Image tokens (if applicable)

## Example Output

### Model Selection
```
Available models that support image input (sorted by popular models first):
1. OpenAI: GPT-4o [~$0.0174/image]
    ID: openai/gpt-4o
2. OpenAI: GPT-4o-mini [~$0.0010/image]
    ID: openai/gpt-4o-mini
3. Anthropic: Claude 3.5 Sonnet [~$0.0210/image]
    ID: anthropic/claude-3.5-sonnet
4. Google: Gemini 2.5 Flash [~$0.0008/image]
    ID: google/gemini-2.5-flash
...

Select a model number or enter custom model ID: 2
Using model: openai/gpt-4o-mini
Pricing: $0.00000015 per prompt token, $0.0000006 per completion token, $0.000217 per image
```

### Processing Output
```
=== Results for page90_image1.png ===
Tokens: 1250 prompt + 850 completion = 2100 total
Cost: $0.002650
GENESIS. [Description...]
Results saved to: ./images/openai_gpt-4o-mini/page90_image1.md

============================================================
PROCESSING SUMMARY
============================================================
Images processed: 5
Total tokens: 6250 prompt + 4250 completion = 10500 total
Total cost: $0.013250
Metrics saved to: ./images/openai_gpt-4o-mini/metrics.jsonl
============================================================
```

## Metrics File Format (JSONL)

Each line in `metrics.jsonl` is a JSON object:

```json
{
  "timestamp": "2025-10-26T14:50:32.123456",
  "file": "page90_image1.png",
  "model": "openai/gpt-4o-mini",
  "tokens": {
    "prompt": 1250,
    "completion": 850,
    "total": 2100
  },
  "cost": 0.00265,
  "success": true
}
```

For errors:
```json
{
  "timestamp": "2025-10-26T14:50:35.789012",
  "file": "page91_image1.png",
  "model": "openai/gpt-4o-mini",
  "error": "400: Bad Request - Image too large",
  "success": false
}
```

## Usage

The script automatically tracks costs when you run it. No additional configuration needed!

```bash
python read_images.py
```

The metrics file can be analyzed later for cost tracking, performance analysis, or debugging.
