#!/usr/bin/env python3
"""Script to read images and extract text using OpenRouter's vision models via BAML."""

import os
import sys
import json
import logging
import argparse
import requests
import time
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from baml_client.sync_client import b
from baml_py import Image
from baml_py.baml_py import ClientRegistry
from baml_py.internal_monkeypatch import BamlClientHttpError

# Load environment variables from .env file
load_dotenv()


class TeeStream:
    """A stream that writes to multiple destinations."""
    def __init__(self, *streams):
        self.streams = streams
    
    def write(self, data):
        for stream in self.streams:
            stream.write(data)
            stream.flush()
    
    def flush(self):
        for stream in self.streams:
            stream.flush()


def setup_logging(output_dir, model_name):
    """Setup logging to both file and console."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    model_safe = model_name.replace('/', '_')
    log_filename = f"processing_{model_safe}_{timestamp}.log"
    log_path = output_dir / log_filename
    
    # Clear existing handlers
    logger = logging.getLogger()
    logger.handlers.clear()
    
    # Open log file for direct writing (for BAML logs that go to stdout)
    log_file = open(log_path, 'w', encoding='utf-8')
    
    # Create a tee stream that writes to both console and file
    tee_stdout = TeeStream(sys.stdout, log_file)
    tee_stderr = TeeStream(sys.stderr, log_file)
    
    # Redirect stdout and stderr to capture BAML logs
    sys.stdout = tee_stdout
    sys.stderr = tee_stderr
    
    # Create handlers for Python logging
    file_handler = logging.FileHandler(log_path, encoding='utf-8')
    console_handler = logging.StreamHandler(tee_stdout)
    
    # Set format
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[file_handler, console_handler],
        force=True
    )
    
    # Set BAML logging environment variable to INFO level
    os.environ['BAML_LOG'] = 'info'
    
    return str(log_path)


def load_metadata(image_path):
    """Load metadata for an image from its corresponding JSON file."""
    # Metadata files are named: <image_name>_metadata.json
    json_path = image_path.parent / f"{image_path.stem}_metadata.json"
    if json_path.exists():
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Normalize key names: book_name -> book
            if 'book_name' in data and 'book' not in data:
                data['book'] = data['book_name']
            return data
    return None


def load_ocr_markdown(image_path):
    """Load OCR markdown if available."""
    # OCR markdown files have the same name as image but with .md extension
    md_path = image_path.with_suffix('.md')
    if md_path.exists():
        with open(md_path, 'r', encoding='utf-8') as f:
            return f.read()
    return None


def format_hebrew_verses(hebrew_dict):
    """Format Hebrew verses from metadata."""
    if not hebrew_dict:
        return ""
    
    verses = []
    for verse_num, verse_text in sorted(hebrew_dict.items(), key=lambda x: int(x[0])):
        verses.append(f"{verse_num}. {verse_text}")
    
    return "\n".join(verses)


def matches_filter(metadata, book_filter, chapter_start, chapter_end):
    """Check if image matches the filtering criteria."""
    if not metadata:
        return False
    
    book = metadata.get('book', '')
    chapter = metadata.get('chapter')
    
    if book_filter and book.lower() != book_filter.lower():
        return False
    
    if chapter is not None:
        if chapter_start is not None and chapter < chapter_start:
            return False
        if chapter_end is not None and chapter > chapter_end:
            return False
    
    return True


def call_baml_with_retry(baml_image, book, chapter, verse, page_number, hebrew_text, ocr_text, max_retries=5):
    """Call BAML ExtractTextFromImage with retry logic and exponential backoff.
    
    Args:
        baml_image: BAML image object
        book, chapter, verse, page_number: Metadata strings
        hebrew_text, ocr_text: Optional context strings
        max_retries: Maximum number of retry attempts (default: 5)
        
    Returns:
        str: Extracted text
        
    Raises:
        Exception: If all retry attempts fail
    """
    base_delay = 2  # Start with 2 second delay
    max_delay = 60  # Cap at 60 seconds
    
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                logging.info(f"Retry attempt {attempt}/{max_retries-1}")
            
            extracted_text = b.ExtractTextFromImage(
                baml_image,
                book=book,
                chapter=chapter,
                verse=verse,
                page_number=page_number,
                hebrew_text=hebrew_text,
                ocr_text=ocr_text
            )
            
            # Success!
            if attempt > 0:
                logging.info(f"Succeeded after {attempt} retries")
            return extracted_text
            
        except BamlClientHttpError as e:
            error_msg = str(e)
            is_retryable = False
            
            # Check if this is a retryable error
            if "Failed to parse JSON" in error_msg and "EOF" in error_msg:
                is_retryable = True
                reason = "truncated JSON response"
            elif "status_code=500" in error_msg or "status_code=502" in error_msg or "status_code=503" in error_msg:
                is_retryable = True
                reason = "server error"
            elif "timeout" in error_msg.lower():
                is_retryable = True
                reason = "timeout"
            elif "status_code=429" in error_msg:
                is_retryable = True
                reason = "rate limit"
            
            if is_retryable and attempt < max_retries - 1:
                # Calculate exponential backoff delay
                delay = min(base_delay * (2 ** attempt), max_delay)
                logging.warning(f"BAML call failed ({reason}), retrying in {delay}s... (attempt {attempt + 1}/{max_retries})")
                logging.debug(f"Error details: {error_msg[:500]}")
                time.sleep(delay)
            else:
                # Not retryable or out of retries
                if not is_retryable:
                    logging.error(f"Non-retryable error: {error_msg[:500]}")
                else:
                    logging.error(f"Max retries ({max_retries}) exceeded")
                raise
                
        except Exception as e:
            # Unexpected error, don't retry
            logging.error(f"Unexpected error (non-retryable): {type(e).__name__}: {str(e)[:500]}")
            raise
    
    # Should never reach here, but just in case
    raise Exception(f"Failed after {max_retries} attempts")


def fetch_latest_generation_cost(provisioning_key, model_name, start_time, max_wait_seconds=10):
    """Fetch the cost of the latest generation from OpenRouter activity API.
    
    Note: Requires a provisioning key (not the regular API key).
    Get it from: https://openrouter.ai/settings/keys
    """
    url = "https://openrouter.ai/api/v1/activity"
    headers = {
        "Authorization": f"Bearer {provisioning_key}",
        "Content-Type": "application/json"
    }
    
    end_time = time.time() + max_wait_seconds
    attempt = 0
    
    while time.time() < end_time:
        attempt += 1
        try:
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                activity_data = response.json()
                items = activity_data.get('data', [])
                
                # Log diagnostic info on first attempt
                if attempt == 1:
                    logging.info(f"Activity API returned {len(items)} items")
                    if items:
                        logging.info(f"Most recent activity: model={items[0].get('model')}, created_at={items[0].get('created_at')}")
                
                for item in items:
                    item_model = item.get('model', '')
                    item_created_at_str = item.get('created_at', '')
                    
                    # Check if model matches
                    if item_model == model_name:
                        if item_created_at_str:
                            # Parse timestamp - handle both with and without timezone
                            try:
                                if '+' in item_created_at_str:
                                    # Remove timezone for comparison
                                    created_at = datetime.fromisoformat(item_created_at_str.replace('+00:00', ''))
                                else:
                                    created_at = datetime.fromisoformat(item_created_at_str)
                                
                                # Make comparison timezone-agnostic
                                time_diff = (created_at - start_time).total_seconds()
                                
                                if time_diff >= -5 and time_diff < 180:  # Allow 5s buffer before, up to 3 minutes after
                                    logging.info(f"Found matching generation: {item.get('generation_id')} (time_diff={time_diff:.1f}s)")
                                    return {
                                        'generation_id': item.get('generation_id'),
                                        'tokens_prompt': item.get('tokens_prompt', 0),
                                        'tokens_completion': item.get('tokens_completion', 0),
                                        'cost': item.get('usage', 0.0),
                                        'created_at': item_created_at_str,
                                    }
                                elif attempt == 1:
                                    logging.info(f"Found model {model_name} but time_diff={time_diff:.1f}s is outside window")
                            except Exception as e:
                                logging.info(f"Error parsing timestamp {item_created_at_str}: {e}")
                                continue
            else:
                logging.warning(f"Activity API returned status {response.status_code}: {response.text[:200]}")
            
            time.sleep(1)
            
        except Exception as e:
            logging.warning(f"Error fetching activity data: {e}")
            time.sleep(1)
    
    logging.info(f"No matching generation found after {attempt} attempts over {max_wait_seconds}s")
    return None


def process_images_with_baml(api_key, provisioning_key, directory_path="extracted_images", model_name="qwen/qwen3-vl-235b-a22b-thinking", 
                             book_filter=None, chapter_start=None, chapter_end=None):
    """Process images using BAML for text extraction."""
    
    # Set API key as environment variable for BAML to use
    os.environ["OPENROUTER_API_KEY"] = api_key
    
    # Validate provisioning key is available
    if not provisioning_key or provisioning_key == "your-provisioning-key-here":
        logging.warning("No valid provisioning key found. Cost metrics will not be available.")
        logging.warning("Add OPENROUTER_PROVISIONING_KEY to .env file to enable cost tracking.")
    
    # Filter and collect PNG files
    all_png_files = list(Path(directory_path).glob("*.png"))
    png_files = []
    skipped_no_metadata = 0
    skipped_filtered = 0
    
    for png_file in all_png_files:
        metadata = load_metadata(png_file)
        
        # ALWAYS require metadata - skip any image without it
        if metadata is None:
            skipped_no_metadata += 1
            continue
        
        # If filters are specified, check if metadata matches
        if book_filter or chapter_start or chapter_end:
            if matches_filter(metadata, book_filter, chapter_start, chapter_end):
                png_files.append(png_file)
            else:
                skipped_filtered += 1
        else:
            # No filters - process all images that have metadata
            png_files.append(png_file)
    
    if not png_files:
        pass
    
    # Create output directory
    model_dir_name = model_name.replace("/", "_")
    output_dir = Path(directory_path) / model_dir_name
    output_dir.mkdir(exist_ok=True)
    
    # Setup logging
    log_path = setup_logging(output_dir, model_name)
    
    logging.info("="*60)
    logging.info("IMAGE PROCESSING SESSION STARTED")
    logging.info("="*60)
    logging.info(f"Model: {model_name}")
    logging.info(f"Output directory: {output_dir}")
    logging.info(f"Log file: {log_path}")
    logging.info("="*60)
    
    # Log filtering info
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
    
    # Process each image
    for i, png_file in enumerate(png_files, 1):
        logging.info("")
        logging.info("="*60)
        logging.info(f"Processing image {i}/{len(png_files)}: {png_file.name}")
        logging.info("="*60)
        
        try:
            # Load metadata (required)
            metadata = load_metadata(png_file)
            book = metadata.get('book', 'Unknown')
            chapter = metadata.get('chapter', 'Unknown')
            verse = metadata.get('verse', 'Unknown')
            page_number = metadata.get('page_number', 'Unknown')
            logging.info(f"Metadata: {book} {chapter}:{verse} (Page {page_number})")
            
            # Load OCR markdown if available
            ocr_markdown = load_ocr_markdown(png_file)
            if ocr_markdown:
                logging.info(f"Loaded OCR markdown ({len(ocr_markdown)} characters)")
            
            # Extract and format Hebrew verses from metadata
            hebrew_text_dict = metadata.get('hebrew_text', {})
            hebrew_verses = format_hebrew_verses(hebrew_text_dict)
            if hebrew_verses:
                logging.info(f"Loaded Hebrew text for {len(hebrew_text_dict)} verse(s)")
            
            # Create BAML image from file
            with open(png_file, 'rb') as f:
                import base64
                image_b64 = base64.b64encode(f.read()).decode('utf-8')
            baml_image = Image.from_base64("image/png", image_b64)
            
            # Record start time for activity API lookup
            start_time = datetime.utcnow()
            
            # Call BAML with enhanced context and retry logic
            logging.info("Calling BAML ExtractTextFromImage with metadata, Hebrew, and OCR context...")
            # Note: BAML uses the client defined in main.baml (OpenRouter client)
            # The model cannot be dynamically changed per call in current BAML version
            extracted_text = call_baml_with_retry(
                baml_image=baml_image,
                book=str(book),
                chapter=str(chapter),
                verse=str(verse),
                page_number=str(page_number),
                hebrew_text=hebrew_verses if hebrew_verses else None,
                ocr_text=ocr_markdown if ocr_markdown else None,
                max_retries=5  # Allow up to 5 attempts
            )
            
            logging.info(f"Successfully extracted text ({len(extracted_text)} characters)")
            preview = extracted_text[:200] + "..." if len(extracted_text) > 200 else extracted_text
            logging.info(f"Preview: {preview}")
            
            # Fetch cost from activity API (only if provisioning key is available)
            if provisioning_key and provisioning_key != "your-provisioning-key-here":
                logging.info("Fetching cost data from OpenRouter activity API...")
                generation_info = fetch_latest_generation_cost(provisioning_key, model_name, start_time)
            else:
                generation_info = None
            
            if generation_info:
                prompt_tokens = generation_info.get('tokens_prompt', 0)
                completion_tokens = generation_info.get('tokens_completion', 0)
                total_tokens = prompt_tokens + completion_tokens
                cost = generation_info.get('cost', 0.0)
                generation_id = generation_info.get('generation_id', 'unknown')
                
                logging.info(f"Generation ID: {generation_id}")
                logging.info(f"Tokens: {prompt_tokens} prompt + {completion_tokens} completion = {total_tokens} total")
                logging.info(f"Cost: ${cost:.6f}")
                
                total_cost += cost
                total_prompt_tokens += prompt_tokens
                total_completion_tokens += completion_tokens
                total_images += 1
            else:
                logging.warning("Could not fetch cost data from activity API")
                prompt_tokens = 0
                completion_tokens = 0
                total_tokens = 0
                cost = 0.0
                generation_id = 'unknown'
                total_images += 1
            
            # Save results
            output_file = output_dir / png_file.with_suffix('.md').name
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(extracted_text)
            logging.info(f"Results saved to: {output_file}")
            
            # Log metrics
            metrics_entry = {
                "timestamp": datetime.now().isoformat(),
                "file": png_file.name,
                "model": model_name,
                "generation_id": generation_id,
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
            
        except Exception as e:
            error_msg = f"Error processing {png_file.name}: {str(e)}"
            logging.error(error_msg)
            logging.exception("Exception details:")
            
            metrics_entry = {
                "timestamp": datetime.now().isoformat(),
                "file": png_file.name,
                "model": model_name,
                "error": str(e),
                "success": False
            }
            with open(metrics_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(metrics_entry) + '\n')
            continue
    
    # Print summary
    logging.info("")
    logging.info("="*60)
    logging.info("PROCESSING COMPLETE")
    logging.info("="*60)
    logging.info(f"Total images processed: {total_images}")
    logging.info(f"Total tokens: {total_prompt_tokens + total_completion_tokens:,}")
    logging.info(f"  - Prompt tokens: {total_prompt_tokens:,}")
    logging.info(f"  - Completion tokens: {total_completion_tokens:,}")
    logging.info(f"Total cost: ${total_cost:.6f}")
    if total_images > 0:
        logging.info(f"Average cost per image: ${total_cost/total_images:.6f}")
    logging.info(f"Metrics saved to: {metrics_file}")
    logging.info("="*60)


# Load API keys from environment variables
API_KEY = os.getenv("OPENROUTER_API_KEY", "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")
PROVISIONING_KEY = os.getenv("OPENROUTER_PROVISIONING_KEY", "")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract text from images using BAML and OpenRouter")
    parser.add_argument("--directory", "-d", default="extracted_images", 
                       help="Directory containing images to process")
    parser.add_argument("--model", "-m", default="qwen/qwen3-vl-235b-a22b-thinking",
                       help="Model to use for text extraction")
    parser.add_argument("--book", "-b", help="Filter by book name (e.g., Genesis)")
    parser.add_argument("--chapter-start", "-cs", type=int, help="Start chapter (inclusive)")
    parser.add_argument("--chapter-end", "-ce", type=int, help="End chapter (inclusive)")
    
    args = parser.parse_args()
    
    process_images_with_baml(
        api_key=API_KEY,
        provisioning_key=PROVISIONING_KEY,
        directory_path=args.directory,
        model_name=args.model,
        book_filter=args.book,
        chapter_start=args.chapter_start,
        chapter_end=args.chapter_end
    )
