import os
import base64
import json
import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime
from baml_client.sync_client import b as baml_client
import baml_py
import requests

def setup_logging(output_dir, model_name):
    """Setup logging to both file and console.
    
    Args:
        output_dir (Path): Directory where log file will be saved
        model_name (str): Name of the model being used
        
    Returns:
        str: Path to the log file
    """
    # Create log filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    model_safe = model_name.replace('/', '_')
    log_filename = f"processing_{model_safe}_{timestamp}.log"
    log_path = output_dir / log_filename
    
    # Clear any existing handlers
    logger = logging.getLogger()
    logger.handlers.clear()
    
    # Configure logging with force=True to override any existing config
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ],
        force=True
    )
    
    return str(log_path)

def load_metadata(image_path):
    """Load metadata for an image from its corresponding JSON file.
    
    Args:
        image_path (Path): Path to the image file
        
    Returns:
        dict or None: Metadata dict if file exists, None otherwise
    """
    # Remove extension and add _metadata.json
    metadata_path = image_path.with_suffix('').with_suffix('').parent / f"{image_path.stem}_metadata.json"
    
    if metadata_path.exists():
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"Failed to load metadata for {image_path.name}: {e}")
    return None

def load_ocr_markdown(image_path):
    """Load OCR markdown file for an image.
    
    Args:
        image_path (Path): Path to the image file
        
    Returns:
        str or None: Markdown content if file exists, None otherwise
    """
    # Try to find matching .md file
    md_path = image_path.with_suffix('.md')
    
    if md_path.exists():
        try:
            with open(md_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logging.warning(f"Failed to load OCR markdown for {image_path.name}: {e}")
    return None

def format_hebrew_verses(hebrew_text_dict):
    """Format Hebrew verses from metadata into a readable string.
    
    Args:
        hebrew_text_dict (dict): Dictionary mapping verse numbers to Hebrew text
        
    Returns:
        str: Formatted Hebrew verses
    """
    if not hebrew_text_dict:
        return ""
    
    lines = []
    for verse_num, hebrew in sorted(hebrew_text_dict.items(), key=lambda x: str(x[0])):
        lines.append(f"Verse {verse_num}: {hebrew}")
    return "\n".join(lines)

def matches_filter(metadata, book_filter=None, chapter_start=None, chapter_end=None):
    """Check if metadata matches the given filters.
    
    Args:
        metadata (dict): Image metadata
        book_filter (str): Book name to filter by (case-insensitive)
        chapter_start (int): Starting chapter (inclusive)
        chapter_end (int): Ending chapter (inclusive)
        
    Returns:
        bool: True if metadata matches all filters
    """
    if not metadata:
        return False
    
    # Check book filter
    if book_filter:
        book_name = metadata.get('book_name', '')
        if book_name.upper() != book_filter.upper():
            return False
    
    # Check chapter range
    chapter = metadata.get('chapter')
    if chapter is None:
        return False
        
    if chapter_start is not None and chapter < chapter_start:
        return False
    if chapter_end is not None and chapter > chapter_end:
        return False
    
    return True

def process_images_with_openrouter(api_key, directory_path, model_name="qwen/qwen3-vl-235b-a22b-thinking", model_pricing=None, 
                                  book_filter=None, chapter_start=None, chapter_end=None):
    """
    Process all PNG images in a directory using OpenRouter API via BAML
    
    Args:
        api_key (str): Your OpenRouter API key
        directory_path (str): Path to directory containing PNG images
        model_name (str): OpenRouter model to use
        model_pricing (dict): Pricing information for the model
        book_filter (str): Optional book name filter
        chapter_start (int): Optional starting chapter (inclusive)
        chapter_end (int): Optional ending chapter (inclusive)
    """
    
    # Get all PNG files in the directory
    all_png_files = list(Path(directory_path).glob("*.png"))
    
    if not all_png_files:
        logging.warning(f"No PNG files found in {directory_path}")
        return
    
    # Filter images based on metadata
    png_files = []
    skipped_no_metadata = 0
    skipped_filtered = 0
    
    for png_file in all_png_files:
        metadata = load_metadata(png_file)
        
        if metadata is None:
            skipped_no_metadata += 1
            continue
        
        if matches_filter(metadata, book_filter, chapter_start, chapter_end):
            png_files.append((png_file, metadata))
        else:
            skipped_filtered += 1
    
    if not png_files:
        # We'll log this after logging is set up
        pass
    
    # Create output directory named after the model
    # Replace slashes with underscores for valid directory name
    model_dir_name = model_name.replace("/", "_")
    output_dir = Path(directory_path) / model_dir_name
    output_dir.mkdir(exist_ok=True)
    
    # Setup logging to output directory (must be done before any logging calls)
    log_path = setup_logging(output_dir, model_name)
    
    # Now we can start logging
    logging.info("="*60)
    logging.info("IMAGE PROCESSING SESSION STARTED")
    logging.info("="*60)
    logging.info(f"Model: {model_name}")
    logging.info(f"Output directory: {output_dir}")
    logging.info(f"Log file: {log_path}")
    logging.info("="*60)
    
    # Log the filtering information
    if book_filter or chapter_start or chapter_end:
        logging.info("")
        logging.info("="*60)
        logging.info("FILTER APPLIED:")
        if book_filter:
            logging.info(f"  Book: {book_filter}")
        if chapter_start is not None or chapter_end is not None:
            if chapter_start == chapter_end:
                logging.info(f"  Chapter: {chapter_start}")
            else:
                start_str = str(chapter_start) if chapter_start is not None else "beginning"
                end_str = str(chapter_end) if chapter_end is not None else "end"
                logging.info(f"  Chapters: {start_str} to {end_str}")
        logging.info("="*60)
    
    logging.info(f"\nFound {len(all_png_files)} total images")
    logging.info(f"Skipped {skipped_no_metadata} images without metadata")
    logging.info(f"Skipped {skipped_filtered} images not matching filters")
    logging.info(f"Processing {len(png_files)} images")
    
    # Check if we have images to process
    if not png_files:
        logging.warning("No images to process after applying filters")
        logging.info("="*60)
        logging.info("SESSION ENDED - No images to process")
        logging.info("="*60)
        return
    
    # Initialize metrics tracking
    metrics_file = output_dir / "metrics.jsonl"
    total_cost = 0.0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_images = 0
    
    # Get BAML prompt template to send directly to OpenRouter
    from baml_client.sync_client import b as sync_baml_client
    
    for png_file, metadata in png_files:
        # Display metadata info
        book = metadata.get('book_name', 'Unknown')
        chapter = metadata.get('chapter', '?')
        verse = metadata.get('verse', '?')
        page_number = metadata.get('page_number', '?')
        logging.info("\n" + "="*60)
        logging.info(f"Processing: {png_file.name}")
        logging.info(f"Book: {book}, Chapter: {chapter}, Verse: {verse}, Page: {page_number}")
        logging.info("="*60)
        try:
            # Read and encode the image
            with open(png_file, "rb") as image_file:
                image_data = base64.b64encode(image_file.read()).decode('utf-8')
            
            # Load OCR markdown if available
            ocr_markdown = load_ocr_markdown(png_file)
            
            # Extract Hebrew verses from metadata
            hebrew_text_dict = metadata.get('hebrew_text', {})
            hebrew_verses = format_hebrew_verses(hebrew_text_dict)
            
            # Build enhanced prompt with metadata context (matching BAML ExtractTextFromImage)
            prompt_parts = []
            
            # Base instruction from BAML - updated to ensure single-column output
            prompt_parts.append("Extract the text from the image in markdown format. Some words might be in Greek, Hebrew or Arabic, especially in footnotes, please include these words in their proper language. Please link the footnote to its place in the text.")
            
            prompt_parts.append("\nIMPORTANT: The image has TWO COLUMNS but you must MERGE them into a SINGLE continuous text output. Read the left column completely from top to bottom first, then continue with the right column from top to bottom. Handle text that is hyphenated from one column to the other by combining the hyphenated word. Do NOT preserve the two-column layout in your output - provide a single flowing text.")
            
            prompt_parts.append("\nFOOTNOTES: The footnotes ONLY use lower case lettering (a, b, c, etc.). There can be duplicate footnote letters when they are reused in different paragraphs. Include all footnotes at the end of their respective paragraph or section, properly linked with their lowercase letter markers.")
            
            # Add context about OCR output
            if ocr_markdown:
                prompt_parts.append("\nThe output of an OCR tool is attached below and should be ONLY used to maintain accuracy in matching the original word for word since it gets some words wrong. The OCR often fails to detect the footnote lettering. OCR also struggles with the languages so use the image for those.")
            
            # Add context about Hebrew text
            if hebrew_verses:
                prompt_parts.append("\nOriginal Hebrew verse the commentary is referring to is provided as a reference to use the Hebrew in the text is properly interpreted. Please match the Hebrew letter order as it is in the image and reference.")
            
            # Add metadata context
            prompt_parts.append("\n\n=== METADATA ===")
            prompt_parts.append(f"Book: {book}")
            prompt_parts.append(f"Chapter: {chapter}")
            prompt_parts.append(f"Verse(s): {verse}")
            prompt_parts.append(f"Page Number: {page_number}")
            
            # Add Hebrew text if available
            if hebrew_verses:
                prompt_parts.append("\n=== ORIGINAL HEBREW VERSES ===")
                prompt_parts.append(hebrew_verses)
            
            # Add OCR markdown if available
            if ocr_markdown:
                prompt_parts.append("\n\n=== OCR OUTPUT (For Reference Only) ===")
                prompt_parts.append(ocr_markdown)
            
            prompt_text = "\n".join(prompt_parts)
            
            payload = {
                "model": model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": prompt_text
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_data}"
                                }
                            }
                        ]
                    }
                ]
            }
            
            # Send request to OpenRouter with timeout
            logging.info(f"Sending request to OpenRouter API...")
            
            try:
                response = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json=payload,
                    timeout=300,  # 5 minute timeout
                    stream=False  # Ensure we get the full response
                )
                
                logging.info(f"Received response with status code: {response.status_code}")
                
                if response.status_code == 200:
                    # Log response headers and size
                    content_type = response.headers.get('content-type', 'unknown')
                    logging.info(f"Response content-type: {content_type}")
                    response_size = len(response.content)
                    logging.info(f"Response size: {response_size} bytes")
                    
                    # Try to parse JSON
                    try:
                        result = response.json()
                        extracted_text = result['choices'][0]['message']['content']
                        logging.info(f"Successfully extracted text ({len(extracted_text)} characters)")
                        
                        # Extract usage information
                        usage = result.get('usage', {})
                        prompt_tokens = usage.get('prompt_tokens', 0)
                        completion_tokens = usage.get('completion_tokens', 0)
                        total_tokens = usage.get('total_tokens', 0)
                        
                        # Calculate cost if pricing is available
                        cost = 0.0
                        if model_pricing:
                            prompt_cost = float(model_pricing.get('prompt', 0)) * prompt_tokens
                            completion_cost = float(model_pricing.get('completion', 0)) * completion_tokens
                            image_cost = float(model_pricing.get('image', 0))
                            cost = prompt_cost + completion_cost + image_cost
                        
                        # Update totals
                        total_cost += cost
                        total_prompt_tokens += prompt_tokens
                        total_completion_tokens += completion_tokens
                        total_images += 1
                        
                        # Display metrics
                        logging.info(f"Tokens: {prompt_tokens} prompt + {completion_tokens} completion = {total_tokens} total")
                        if model_pricing:
                            logging.info(f"Cost: ${cost:.6f}")
                        preview = extracted_text[:200] + "..." if len(extracted_text) > 200 else extracted_text
                        logging.info(f"Preview: {preview}")
                        
                        # Save results to file in model-specific directory
                        output_file = output_dir / png_file.with_suffix('.md').name
                        with open(output_file, 'w', encoding='utf-8') as f:
                            f.write(extracted_text)
                        logging.info(f"Results saved to: {output_file}")
                        
                        # Log metrics to JSONL file
                        metrics_entry = {
                            "timestamp": datetime.now().isoformat(),
                            "file": png_file.name,
                            "model": model_name,
                            "tokens": {
                                "prompt": prompt_tokens,
                                "completion": completion_tokens,
                                "total": total_tokens
                            },
                            "cost": cost,
                            "success": True
                        }
                        with open(metrics_file, 'a', encoding='utf-8') as f:
                            f.write(json.dumps(metrics_entry) + '\n')
                        
                    except json.JSONDecodeError as e:
                        error_msg = f"Failed to parse JSON response for {png_file.name}: {e}"
                        logging.error(error_msg)
                        logging.error(f"Response length: {len(response.text)} characters")
                        
                        # Log first and last 500 chars of response for debugging
                        response_start = response.text[:500] if len(response.text) > 500 else response.text
                        response_end = "..." + response.text[-500:] if len(response.text) > 500 else ""
                        logging.error(f"Response start: {response_start}")
                        if response_end:
                            logging.error(f"Response end: {response_end}")
                        
                        # Save the problematic response to a file for debugging
                        error_response_file = output_dir / f"{png_file.stem}_error_response.txt"
                        with open(error_response_file, 'w', encoding='utf-8') as f:
                            f.write(response.text)
                        logging.error(f"Full response saved to: {error_response_file}")
                        
                        # Log error to metrics
                        metrics_entry = {
                            "timestamp": datetime.now().isoformat(),
                            "file": png_file.name,
                            "model": model_name,
                            "error": f"JSON decode error at line {e.lineno} col {e.colno}: {str(e)}",
                            "success": False
                        }
                        with open(metrics_file, 'a', encoding='utf-8') as f:
                            f.write(json.dumps(metrics_entry) + '\n')
                        continue  # Skip to next image
                    
                else:
                    error_msg = f"Error processing {png_file.name}: {response.status_code}"
                    logging.error(error_msg)
                    logging.error(f"Response: {response.text[:500]}")
                    
                    # Log error to metrics
                    metrics_entry = {
                        "timestamp": datetime.now().isoformat(),
                        "file": png_file.name,
                        "model": model_name,
                        "error": f"{response.status_code}: {response.text[:200]}",
                        "success": False
                    }
                    with open(metrics_file, 'a', encoding='utf-8') as f:
                        f.write(json.dumps(metrics_entry) + '\n')
                        
            except requests.exceptions.JSONDecodeError as e:
                # Handle JSON decode errors from requests library
                error_msg = f"JSON decode error for {png_file.name}: {e}"
                logging.error(error_msg)
                logging.error(f"This usually means the response was truncated or malformed")
                
                # Try to get raw response if available
                try:
                    raw_text = response.text if 'response' in locals() else 'Response not available'
                    logging.error(f"Raw response length: {len(raw_text)} characters")
                    
                    # Save problematic response
                    error_response_file = output_dir / f"{png_file.stem}_json_error_response.txt"
                    with open(error_response_file, 'w', encoding='utf-8') as f:
                        f.write(raw_text)
                    logging.error(f"Full response saved to: {error_response_file}")
                except:
                    pass
                
                # Log error to metrics
                metrics_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "file": png_file.name,
                    "model": model_name,
                    "error": f"JSON decode error: {str(e)}",
                    "success": False
                }
                with open(metrics_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(metrics_entry) + '\n')
                continue
                
        except requests.exceptions.Timeout:
            error_msg = f"Request timeout for {png_file.name} after 300 seconds"
            logging.error(error_msg)
            
            # Log timeout to metrics
            metrics_entry = {
                "timestamp": datetime.now().isoformat(),
                "file": png_file.name,
                "model": model_name,
                "error": "Request timeout (300s)",
                "success": False
            }
            with open(metrics_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(metrics_entry) + '\n')
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Request error for {png_file.name}: {str(e)}"
            logging.error(error_msg)
            
            # Log request error to metrics
            metrics_entry = {
                "timestamp": datetime.now().isoformat(),
                "file": png_file.name,
                "model": model_name,
                "error": f"Request error: {str(e)}",
                "success": False
            }
            with open(metrics_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(metrics_entry) + '\n')
                
        except Exception as e:
            logging.exception(f"Failed to process {png_file.name}: {str(e)}")
            
            # Log exception to metrics
            metrics_entry = {
                "timestamp": datetime.now().isoformat(),
                "file": png_file.name,
                "model": model_name,
                "error": str(e),
                "success": False
            }
            with open(metrics_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(metrics_entry) + '\n')
    
    # Print summary
    logging.info("\n" + "="*60)
    logging.info("PROCESSING SUMMARY")
    logging.info("="*60)
    logging.info(f"Images processed: {total_images}")
    logging.info(f"Total tokens: {total_prompt_tokens} prompt + {total_completion_tokens} completion = {total_prompt_tokens + total_completion_tokens} total")
    if model_pricing:
        logging.info(f"Total cost: ${total_cost:.6f}")
    logging.info(f"Metrics saved to: {metrics_file}")
    logging.info(f"Log file: {log_path}")
    logging.info("="*60)
    logging.info("SESSION COMPLETED")

def get_available_models(api_key):
    """Get list of available models from OpenRouter that support image input
    
    Returns:
        tuple: (models_dict, pricing_dict) where models_dict maps model_id to model_name,
               and pricing_dict maps model_id to pricing info
    """
    try:
        response = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers={
                "Authorization": f"Bearer {api_key}"
            }
        )
        
        if response.status_code == 200:
            models_data = response.json()
            # Filter for models that support vision/images
            vision_models = {}
            pricing_info = {}
            
            for model in models_data.get('data', []):
                model_id = model.get('id', '')
                model_name = model.get('name', model_id)
                architecture = model.get('architecture', {})
                
                # Check if model supports image input
                has_vision = False
                
                # Method 1: Check input_modalities for 'image'
                input_modalities = architecture.get('input_modalities', [])
                if 'image' in input_modalities:
                    has_vision = True
                
                # Method 2: Check modality field
                modality = architecture.get('modality', '')
                if 'vision' in modality.lower() or 'multimodal' in modality.lower():
                    has_vision = True
                
                # Method 3: Check known vision model patterns in ID
                vision_keywords = ['vision', 'gpt-4-turbo', 'gpt-4o', 'claude-3', 'gemini-1.5', 
                                  'gemini-2', 'gemini-pro-vision', 'llama-3.2', 'pixtral', 
                                  'qwen-vl', 'qwen2-vl', 'qwen2.5-vl', 'glm-4v']
                if any(keyword in model_id.lower() for keyword in vision_keywords):
                    has_vision = True
                
                if has_vision:
                    vision_models[model_id] = model_name
                    pricing_info[model_id] = model.get('pricing', {})
            
            return vision_models, pricing_info
        else:
            logging.warning(f"Failed to fetch models from OpenRouter (status {response.status_code})")
            logging.info("Falling back to default model list")
            return get_fallback_models(), {}
    except Exception as e:
        logging.warning(f"Error fetching models from OpenRouter: {e}")
        logging.info("Falling back to default model list")
        return get_fallback_models(), {}

def get_fallback_models():
    """Get fallback list of common models that support image input"""
    return {
        "qwen/qwen3-vl-235b-a22b-thinking": "Qwen 3 VL 235B Thinking",
        "z-ai/glm-4.5v": "GLM-4.5V",
        "anthropic/claude-3-sonnet": "Claude 3 Sonnet",
        "anthropic/claude-3-haiku": "Claude 3 Haiku",
        "openai/gpt-4o": "GPT-4O",
        "openai/gpt-4o-mini": "GPT-4O Mini"
    }

# Configuration
API_KEY = os.getenv("OPENROUTER_API_KEY")
DIRECTORY_PATH = "./extracted_images"  # Replace with your directory path

if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='Process images with OpenRouter vision models',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all images with metadata
  python read_images.py
  
  # Process only Genesis images
  python read_images.py --book Genesis
  
  # Process Genesis chapters 1-3
  python read_images.py --book Genesis --chapter-start 1 --chapter-end 3
  
  # Process chapter 5 of any book
  python read_images.py --chapter-start 5 --chapter-end 5
  
  # Process from chapter 10 onwards
  python read_images.py --chapter-start 10
  
  # Process with specific model (skip interactive selection)
  python read_images.py --book Genesis --chapter-start 1 --chapter-end 1 --model qwen/qwen3-vl-235b-a22b-thinking
        """
    )
    parser.add_argument('--book', '-b', type=str, help='Filter by book name (e.g., Genesis, Exodus)')
    parser.add_argument('--chapter-start', '-cs', type=int, help='Starting chapter (inclusive)')
    parser.add_argument('--chapter-end', '-ce', type=int, help='Ending chapter (inclusive)')
    parser.add_argument('--directory', '-d', type=str, default=DIRECTORY_PATH, 
                       help=f'Directory containing images (default: {DIRECTORY_PATH})')
    parser.add_argument('--model', '-m', type=str, 
                       help='Model to use (e.g., qwen/qwen3-vl-235b-a22b-thinking). If not specified, will show interactive selection.')
    
    args = parser.parse_args()
    
    # Validate chapter range
    if args.chapter_start is not None and args.chapter_end is not None:
        if args.chapter_start > args.chapter_end:
            print("Error: chapter-start must be less than or equal to chapter-end")
            exit(1)
    
    # Check if model is specified via command line
    if args.model:
        selected_model = args.model
        print(f"Using model from command line: {selected_model}")
        
        # Fetch pricing for the selected model
        print("Fetching model pricing from OpenRouter...")
        models, pricing_info = get_available_models(API_KEY)
        model_pricing = pricing_info.get(selected_model)
    else:
        # Interactive model selection
        print("Fetching available models from OpenRouter...")
        models, pricing_info = get_available_models(API_KEY)
        
        if not models:
            print("No vision models found. Please check your API key or network connection.")
            exit(1)
        
        # Define popular models order (well-known vision models)
        popular_models_order = [
            'qwen/qwen3-vl-235b-a22b-thinking',  # Default preferred model
            'openai/gpt-4o', 'openai/gpt-4o-mini', 'openai/gpt-4-turbo', 
            'anthropic/claude-3.5-sonnet', 'anthropic/claude-3-sonnet', 'anthropic/claude-3-opus',
            'anthropic/claude-3-haiku', 'google/gemini-2.5-flash', 'google/gemini-2.5-pro',
            'google/gemini-1.5-flash', 'google/gemini-1.5-pro', 'google/gemini-pro-vision',
            'meta-llama/llama-3.2-90b-vision', 'meta-llama/llama-3.2-11b-vision',
            'qwen/qwen2-vl-72b-instruct', 'qwen/qwen2-vl-7b-instruct',
            'mistralai/pixtral-12b', 'mistralai/pixtral-large'
        ]
        
        # Ask user for sorting preference
        print(f"\nFound {len(models)} vision-capable models")
        print("\nSort by:")
        print("1. Popular models first (recommended)")
        print("2. Newest models first")
        print("3. Alphabetical by name")
        
        sort_choice = input("\nSelect sorting (1-3) [default: 1]: ").strip() or "1"
        
        # Sort models based on user choice
        if sort_choice == "1":
            # Sort by popularity (popular models first, then alphabetical)
            def popularity_key(item):
                model_id, model_name = item
                try:
                    # Find the index in popular list, or use large number if not found
                    idx = next((i for i, pm in enumerate(popular_models_order) if pm in model_id), 999)
                    return (idx, model_name.lower())
                except:
                    return (999, model_name.lower())
            model_list = sorted(models.items(), key=popularity_key)
            sort_desc = "popular models first"
        elif sort_choice == "2":
            # API already returns newest first, so keep original order
            model_list = list(models.items())
            sort_desc = "newest first"
        else:
            # Sort alphabetically by name
            model_list = sorted(models.items(), key=lambda x: x[1].lower())
            sort_desc = "alphabetical"
        
        print(f"\nAvailable models that support image input (sorted by {sort_desc}):")
        # Show first 20 models with pricing
        for idx, (model_id, model_name) in enumerate(model_list[:20], 1):
            pricing = pricing_info.get(model_id, {})
            prompt_price = pricing.get('prompt', '0')
            completion_price = pricing.get('completion', '0')
            image_price = pricing.get('image', '0')
            
            # Format pricing display
            if float(prompt_price) > 0 or float(completion_price) > 0:
                # Calculate approximate cost for a typical image (assuming ~1500 prompt tokens, ~1000 completion tokens)
                est_cost = (float(prompt_price) * 1500) + (float(completion_price) * 1000) + float(image_price)
                pricing_str = f" [~${est_cost:.4f}/image]"
            else:
                pricing_str = " [pricing unavailable]"
            
            print(f"{idx}. {model_name}{pricing_str}")
            print(f"    ID: {model_id}")
        
        if len(models) > 20:
            print(f"... and {len(models) - 20} more models")
        
        # Let user choose a model
        choice = input("\nSelect a model number or enter custom model ID: ").strip()
        
        # Check if it's a number selection
        if choice.isdigit():
            choice_num = int(choice)
            if 1 <= choice_num <= len(model_list):
                selected_model = model_list[choice_num - 1][0]  # Get the model ID
            else:
                print(f"Invalid selection. Using first model.")
                selected_model = model_list[0][0]
        else:
            # Allow custom model input
            selected_model = choice
        
        print(f"Using model: {selected_model}")
        
        # Get pricing for selected model
        model_pricing = pricing_info.get(selected_model)
    
    # Display pricing if available
    if model_pricing:
        print(f"Pricing: ${model_pricing.get('prompt', 0)} per prompt token, ${model_pricing.get('completion', 0)} per completion token, ${model_pricing.get('image', 0)} per image")
    
    # Run the processing
    process_images_with_openrouter(
        API_KEY, 
        args.directory, 
        selected_model, 
        model_pricing,
        book_filter=args.book,
        chapter_start=args.chapter_start,
        chapter_end=args.chapter_end
    )
