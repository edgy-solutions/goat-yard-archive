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
from baml_py import Image, Collector
from baml_py.baml_py import ClientRegistry
from baml_py.internal_monkeypatch import BamlClientHttpError
from baml_py.errors import BamlValidationError

# Load environment variables from .env file
load_dotenv()


import re
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock


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


class BAMLOutputCapture:
    """Capture BAML output and extract token information."""
    def __init__(self):
        self.last_output = ""
        self.last_tokens = None
        
    def write(self, data):
        self.last_output += data
        # Look for BAML token information
        # Pattern: "Tokens(in/out): 14887/3891"
        match = re.search(r'Tokens\(in/out\):\s*(\d+)/(\d+)', data)
        if match:
            self.last_tokens = {
                'prompt_tokens': int(match.group(1)),
                'completion_tokens': int(match.group(2))
            }
    
    def flush(self):
        pass
    
    def get_tokens_and_reset(self):
        """Get captured tokens and reset for next call."""
        tokens = self.last_tokens
        self.last_tokens = None
        self.last_output = ""
        return tokens


def setup_logging(output_dir, model_name):
    """Setup logging to both file and console, and create BAML output capture.
    
    Uses OS-level file descriptor duplication to capture BAML's native output.
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    model_safe = model_name.replace('/', '_')
    log_filename = f"processing_{model_safe}_{timestamp}.log"
    log_path = output_dir / log_filename
    
    # Clear existing handlers
    logger = logging.getLogger()
    logger.handlers.clear()
    
    # Open log file for writing
    log_file = open(log_path, 'w', encoding='utf-8', buffering=1)  # Line buffered
    
    # Save original stdout/stderr file descriptors
    stdout_fd = sys.stdout.fileno()
    stderr_fd = sys.stderr.fileno()
    
    # Save original stdout/stderr for later use
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    
    # Duplicate the original stdout/stderr file descriptors
    stdout_dup = os.dup(stdout_fd)
    stderr_dup = os.dup(stderr_fd)
    
    # Create BAML output capture that wraps the original stdout
    baml_capture = BAMLOutputCapture()
    
    # Create a custom class that writes to multiple destinations at OS level
    class MultiWriter:
        def __init__(self, *streams):
            self.streams = streams
        
        def write(self, data):
            for stream in self.streams:
                try:
                    stream.write(data)
                    stream.flush()
                except:
                    pass
            return len(data)
        
        def flush(self):
            for stream in self.streams:
                try:
                    stream.flush()
                except:
                    pass
        
        def fileno(self):
            return stdout_fd
    
    # Create console writer using duplicated file descriptor
    console_stream = os.fdopen(stdout_dup, 'w', encoding='utf-8', buffering=1)
    
    # Replace sys.stdout/stderr with multi-writer
    sys.stdout = MultiWriter(console_stream, log_file, baml_capture)
    sys.stderr = MultiWriter(console_stream, log_file)
    
    # Also redirect at OS level - this captures BAML's native Rust output
    os.dup2(log_file.fileno(), stdout_fd)
    os.dup2(log_file.fileno(), stderr_fd)
    
    # Create handlers for Python logging - write to our MultiWriter
    # This ensures Python logs go to both console and file
    console_handler = logging.StreamHandler(sys.stdout)
    
    # Set format
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    
    # Configure root logger with just the one handler
    # It will write to sys.stdout which is our MultiWriter (console + file + capture)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[console_handler],
        force=True
    )
    
    # Set BAML logging environment variable to INFO level
    os.environ['BAML_LOG'] = 'info'
    
    return str(log_path), baml_capture


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


def call_baml_with_retry(baml_image, book, chapter, verse, page_number, hebrew_text, ocr_text, collector, max_retries=10):
    """Call BAML ExtractTextFromImage with robust retry logic and exponential backoff with jitter.
    
    Args:
        baml_image: BAML image object
        book, chapter, verse, page_number: Metadata strings
        hebrew_text, ocr_text: Optional context strings
        collector: BAML Collector instance for tracking metrics
        max_retries: Maximum number of retry attempts (default: 10)
        
    Returns:
        str: Extracted text
        
    Raises:
        Exception: If all retry attempts fail
    """
    base_delay = 5  # Start with 5 second delay (increased from 2)
    max_delay = 120  # Cap at 120 seconds (increased from 60)
    
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
                ocr_text=ocr_text,
                baml_options={"collector": collector}
            )
            
            # Success!
            if attempt > 0:
                logging.info(f"✓ Succeeded after {attempt} retries")
            return extracted_text
            
        except (BamlClientHttpError, BamlValidationError) as e:
            error_msg = str(e)
            is_retryable = False
            reason = "unknown error"
            
            # Check if this is a retryable error
            if "Failed to parse JSON" in error_msg and "EOF" in error_msg:
                is_retryable = True
                reason = "truncated JSON response"
            elif "ConnectionReset" in error_msg or "Connection reset" in error_msg:
                is_retryable = True
                reason = "connection reset"
            elif ("Http2" in error_msg or "HTTP/2" in error_msg) and ("Reset" in error_msg or "PROTOCOL_ERROR" in error_msg):
                is_retryable = True
                reason = "HTTP/2 protocol error"
            elif "Could not read response body" in error_msg:
                is_retryable = True
                reason = "response read error"
            elif "status_code=500" in error_msg or "status_code=502" in error_msg or "status_code=503" in error_msg:
                is_retryable = True
                reason = "server error"
            elif "status_code=504" in error_msg:
                is_retryable = True
                reason = "gateway timeout"
            elif "timeout" in error_msg.lower():
                is_retryable = True
                reason = "timeout"
            elif "status_code=429" in error_msg:
                is_retryable = True
                reason = "rate limit"
            elif "ConnectError" in error_msg or "NetworkError" in error_msg:
                is_retryable = True
                reason = "network error"
            
            if is_retryable and attempt < max_retries - 1:
                # Calculate exponential backoff with jitter
                base_backoff = min(base_delay * (2 ** attempt), max_delay)
                # Add random jitter (±25%) to prevent thundering herd
                jitter = base_backoff * (0.75 + random.random() * 0.5)
                delay = min(jitter, max_delay)
                
                logging.warning(f"BAML call failed ({reason}), retrying in {delay:.1f}s... (attempt {attempt + 1}/{max_retries})")
                logging.debug(f"Error details: {error_msg[:500]}")
                time.sleep(delay)
            else:
                # Not retryable or out of retries
                if not is_retryable:
                    logging.error(f"Non-retryable error: {error_msg[:500]}")
                else:
                    logging.error(f"Max retries ({max_retries}) exceeded. Last error: {reason}")
                raise
                
        except Exception as e:
            # Catch-all for unexpected errors - some might still be retryable
            error_msg = str(e)
            error_type = type(e).__name__
            
            # Check if it's a network-related error that should be retried
            if any(keyword in error_msg.lower() for keyword in ['connection', 'network', 'timeout', 'reset', 'refused']):
                if attempt < max_retries - 1:
                    base_backoff = min(base_delay * (2 ** attempt), max_delay)
                    jitter = base_backoff * (0.75 + random.random() * 0.5)
                    delay = min(jitter, max_delay)
                    logging.warning(f"Network error ({error_type}), retrying in {delay:.1f}s... (attempt {attempt + 1}/{max_retries})")
                    logging.debug(f"Error details: {error_msg[:500]}")
                    time.sleep(delay)
                    continue
            
            # Truly unexpected error
            logging.error(f"Unexpected error (non-retryable): {error_type}: {error_msg[:500]}")
            raise
    
    # Should never reach here, but just in case
    raise Exception(f"Failed after {max_retries} attempts")


def extract_metrics_from_collector(collector, model_pricing):
    """Extract token counts and calculate cost from BAML Collector.
    
    Args:
        collector: BAML Collector instance
        model_pricing: Dict with pricing information
        
    Returns:
        dict: Metrics including tokens and cost, or None if unavailable
    """
    try:
        if not collector:
            return None
        
        # Try using collector.usage directly (newer BAML API)
        usage = collector.usage
        
        if not usage:
            # Fall back to collector.last.usage if needed
            if hasattr(collector, 'last') and collector.last:
                usage = collector.last.usage
        
        if not usage:
            return None
        
        # Extract token counts from usage object
        # Try different attribute names that OpenRouter might use
        prompt_tokens = (getattr(usage, 'input_tokens', None) or 
                        getattr(usage, 'prompt_tokens', None) or 0)
        completion_tokens = (getattr(usage, 'output_tokens', None) or 
                            getattr(usage, 'completion_tokens', None) or 0)
        total_tokens = getattr(usage, 'total_tokens', None) or (prompt_tokens + completion_tokens)
        
        # Calculate cost
        cost = calculate_cost(prompt_tokens, completion_tokens, model_pricing)
        
        # Get latency from collector.last if available
        latency_s = 0
        model_name = 'unknown'
        if hasattr(collector, 'last') and collector.last:
            latency_ms = getattr(collector.last, 'latency_ms', 0) or 0
            latency_s = latency_ms / 1000.0
            model_name = getattr(collector.last, 'model_name', 'unknown') or 'unknown'
        
        return {
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
            'total_tokens': total_tokens,
            'cost': cost,
            'latency_s': latency_s,
            'model': model_name
        }
    except Exception as e:
        logging.debug(f"Error extracting metrics from collector: {e}")
        return None


def calculate_cost(prompt_tokens, completion_tokens, model_pricing):
    """Calculate cost based on token counts and model pricing.
    
    Args:
        prompt_tokens: Number of prompt tokens
        completion_tokens: Number of completion tokens
        model_pricing: Dict with 'prompt', 'completion', and 'image' pricing per token
        
    Returns:
        float: Total cost in dollars
    """
    if not model_pricing:
        return 0.0
    
    prompt_cost = float(model_pricing.get('prompt', 0)) * prompt_tokens
    completion_cost = float(model_pricing.get('completion', 0)) * completion_tokens
    image_cost = float(model_pricing.get('image', 0))
    
    return prompt_cost + completion_cost + image_cost


def process_single_image(png_file, metadata, output_dir, model_pricing, baml_capture):
    """Process a single image and return metrics.
    
    Args:
        png_file: Path to the PNG file
        metadata: Metadata dict for the image
        output_dir: Directory for output files
        model_pricing: Pricing information
        baml_capture: BAML output capture instance
        
    Returns:
        dict: Metrics for this image including tokens and cost
    """
    try:
        book = metadata.get('book', 'Unknown')
        chapter = metadata.get('chapter', 'Unknown')
        verse = metadata.get('verse', 'Unknown')
        page_number = metadata.get('page_number', 'Unknown')
        
        logging.info(f"Processing: {png_file.name} - {book} {chapter}:{verse} (Page {page_number})")
        
        # Load OCR markdown if available
        ocr_markdown = load_ocr_markdown(png_file)
        if ocr_markdown:
            logging.debug(f"Loaded OCR markdown ({len(ocr_markdown)} characters)")
        
        # Extract and format Hebrew verses from metadata
        hebrew_text_dict = metadata.get('hebrew_text', {})
        hebrew_verses = format_hebrew_verses(hebrew_text_dict)
        if hebrew_verses:
            logging.debug(f"Loaded Hebrew text for {len(hebrew_text_dict)} verse(s)")
        
        # Create BAML image from file
        with open(png_file, 'rb') as f:
            import base64
            image_b64 = base64.b64encode(f.read()).decode('utf-8')
        baml_image = Image.from_base64("image/png", image_b64)
        
        # Create a collector for this image
        collector = Collector(name=f"{png_file.stem}")
        
        # Call BAML with enhanced context and retry logic
        logging.info(f"Calling BAML for {png_file.name}...")
        extracted_text = call_baml_with_retry(
            baml_image=baml_image,
            book=str(book),
            chapter=str(chapter),
            verse=str(verse),
            page_number=str(page_number),
            hebrew_text=hebrew_verses if hebrew_verses else None,
            ocr_text=ocr_markdown if ocr_markdown else None,
            collector=collector,
            max_retries=10
        )
        
        logging.info(f"✓ {png_file.name}: Extracted {len(extracted_text)} characters")
        
        # Extract metrics from collector
        metrics = extract_metrics_from_collector(collector, model_pricing)
        
        if metrics:
            prompt_tokens = metrics['prompt_tokens']
            completion_tokens = metrics['completion_tokens']
            total_tokens = metrics['total_tokens']
            cost = metrics['cost']
            latency_s = metrics['latency_s']
            
            logging.info(f"{png_file.name}: {prompt_tokens:,}+{completion_tokens:,}={total_tokens:,} tokens, ${cost:.6f}, {latency_s:.1f}s")
        else:
            # Fallback to BAML output capture
            tokens_from_baml = baml_capture.get_tokens_and_reset()
            
            if tokens_from_baml:
                prompt_tokens = tokens_from_baml['prompt_tokens']
                completion_tokens = tokens_from_baml['completion_tokens']
                total_tokens = prompt_tokens + completion_tokens
                cost = calculate_cost(prompt_tokens, completion_tokens, model_pricing)
                latency_s = 0
                
                logging.info(f"{png_file.name}: {prompt_tokens:,}+{completion_tokens:,}={total_tokens:,} tokens, ${cost:.6f}")
            else:
                logging.warning(f"{png_file.name}: Could not extract metrics")
                prompt_tokens = 0
                completion_tokens = 0
                total_tokens = 0
                cost = 0.0
                latency_s = 0
        
        # Save results
        output_file = output_dir / png_file.with_suffix('.md').name
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(extracted_text)
        logging.info(f"✓ {png_file.name}: Saved to {output_file.name}")
        
        # Return metrics
        return {
            'file': png_file.name,
            'success': True,
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
            'total_tokens': total_tokens,
            'cost': cost,
            'latency_s': latency_s
        }
        
    except Exception as e:
        logging.error(f"✗ {png_file.name}: {type(e).__name__}: {str(e)[:200]}")
        logging.exception(f"Exception details for {png_file.name}:")
        
        return {
            'file': png_file.name,
            'success': False,
            'error': str(e),
            'prompt_tokens': 0,
            'completion_tokens': 0,
            'total_tokens': 0,
            'cost': 0.0,
            'latency_s': 0
        }


def process_images_with_baml(api_key, directory_path="extracted_images", model_name="qwen/qwen3-vl-235b-a22b-thinking", 
                             model_pricing=None, book_filter=None, chapter_start=None, chapter_end=None, max_workers=1):
    """Process images using BAML for text extraction.
    
    Args:
        api_key: OpenRouter API key
        directory_path: Directory containing images
        model_name: Model to use
        model_pricing: Pricing information
        book_filter: Optional book name filter
        chapter_start: Optional starting chapter
        chapter_end: Optional ending chapter
        max_workers: Number of concurrent workers (default: 1 for sequential processing)
    """
    
    # Set API key as environment variable for BAML to use
    os.environ["OPENROUTER_API_KEY"] = api_key
    
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
    log_path, baml_capture = setup_logging(output_dir, model_name)
    
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
    metrics_lock = Lock()  # Thread-safe metrics writing
    
    # Prepare list of images with metadata
    images_to_process = [(png_file, load_metadata(png_file)) for png_file in png_files]
    
    logging.info("")
    logging.info("="*60)
    logging.info(f"Starting processing with {max_workers} worker(s)")
    logging.info("="*60)
    
    # Process images in parallel or sequentially
    all_results = []
    
    if max_workers == 1:
        # Sequential processing
        for i, (png_file, metadata) in enumerate(images_to_process, 1):
            logging.info("")
            logging.info(f"[{i}/{len(images_to_process)}] Processing {png_file.name}")
            result = process_single_image(png_file, metadata, output_dir, model_pricing, baml_capture)
            all_results.append(result)
            
            # Write metrics immediately
            metrics_entry = {
                "timestamp": datetime.now().isoformat(),
                "file": result['file'],
                "model": model_name,
                "tokens": {
                    "prompt": result['prompt_tokens'],
                    "completion": result['completion_tokens'],
                    "total": result['total_tokens']
                },
                "cost": result['cost'],
                "success": result['success']
            }
            if not result['success']:
                metrics_entry['error'] = result.get('error', 'Unknown error')
            
            with open(metrics_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(metrics_entry) + '\n')
    else:
        # Parallel processing
        logging.info(f"Using ThreadPoolExecutor with {max_workers} workers")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_image = {}
            for i, (png_file, metadata) in enumerate(images_to_process, 1):
                future = executor.submit(process_single_image, png_file, metadata, output_dir, model_pricing, baml_capture)
                future_to_image[future] = (i, png_file.name)
            
            # Collect results as they complete
            completed = 0
            for future in as_completed(future_to_image):
                completed += 1
                i, filename = future_to_image[future]
                
                try:
                    result = future.result()
                    all_results.append(result)
                    
                    # Write metrics with thread safety
                    metrics_entry = {
                        "timestamp": datetime.now().isoformat(),
                        "file": result['file'],
                        "model": model_name,
                        "tokens": {
                            "prompt": result['prompt_tokens'],
                            "completion": result['completion_tokens'],
                            "total": result['total_tokens']
                        },
                        "cost": result['cost'],
                        "success": result['success']
                    }
                    if not result['success']:
                        metrics_entry['error'] = result.get('error', 'Unknown error')
                    
                    with metrics_lock:
                        with open(metrics_file, 'a', encoding='utf-8') as f:
                            f.write(json.dumps(metrics_entry) + '\n')
                    
                    logging.info(f"Progress: {completed}/{len(images_to_process)} completed")
                    
                except Exception as e:
                    logging.error(f"Unexpected error getting result for {filename}: {e}")
                    all_results.append({
                        'file': filename,
                        'success': False,
                        'error': str(e),
                        'prompt_tokens': 0,
                        'completion_tokens': 0,
                        'total_tokens': 0,
                        'cost': 0.0,
                        'latency_s': 0
                    })
    
    # Aggregate results
    total_cost = sum(r['cost'] for r in all_results)
    total_prompt_tokens = sum(r['prompt_tokens'] for r in all_results)
    total_completion_tokens = sum(r['completion_tokens'] for r in all_results)
    successful_images = sum(1 for r in all_results if r['success'])
    failed_images = len(all_results) - successful_images
    
    # Print summary
    logging.info("\n" + "="*60)
    logging.info("PROCESSING SUMMARY")
    logging.info("="*60)
    logging.info(f"Total images: {len(all_results)}")
    logging.info(f"Successful: {successful_images}")
    if failed_images > 0:
        logging.info(f"Failed: {failed_images}")
    logging.info(f"Total tokens: {total_prompt_tokens:,} prompt + {total_completion_tokens:,} completion = {total_prompt_tokens + total_completion_tokens:,} total")
    if model_pricing:
        logging.info(f"Total cost: ${total_cost:.6f}")
        if successful_images > 0:
            logging.info(f"Average cost per image: ${total_cost/successful_images:.6f}")
    logging.info(f"Metrics saved to: {metrics_file}")
    logging.info(f"Log file: {log_path}")
    logging.info("="*60)
    logging.info("SESSION COMPLETED")


# Load API key from environment variables
API_KEY = os.getenv("OPENROUTER_API_KEY", "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")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract text from images using BAML and OpenRouter")
    parser.add_argument("--directory", "-d", default="extracted_images", 
                       help="Directory containing images to process")
    parser.add_argument("--model", "-m", default="qwen/qwen3-vl-235b-a22b-thinking",
                       help="Model to use for text extraction")
    parser.add_argument("--book", "-b", help="Filter by book name (e.g., Genesis)")
    parser.add_argument("--chapter-start", "-cs", type=int, help="Start chapter (inclusive)")
    parser.add_argument("--chapter-end", "-ce", type=int, help="End chapter (inclusive)")
    parser.add_argument("--workers", "-w", type=int, default=1,
                       help="Number of concurrent workers (default: 1). Use 2-4 for parallel processing.")
    
    args = parser.parse_args()
    
    # Validate workers
    if args.workers < 1:
        print("Error: --workers must be at least 1")
        exit(1)
    if args.workers > 10:
        print("Warning: Using more than 10 workers may cause rate limiting or instability")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            exit(0)
    
    # Set model pricing (approximate values for qwen3-vl-235b-a22b-thinking)
    # Update these based on OpenRouter's pricing page: https://openrouter.ai/models
    model_pricing = {
        'prompt': 0.000005,  # $5 per 1M tokens
        'completion': 0.000015,  # $15 per 1M tokens
        'image': 0.0  # Additional per-image cost if any
    }
    
    process_images_with_baml(
        api_key=API_KEY,
        directory_path=args.directory,
        model_name=args.model,
        model_pricing=model_pricing,
        book_filter=args.book,
        chapter_start=args.chapter_start,
        chapter_end=args.chapter_end,
        max_workers=args.workers
    )
