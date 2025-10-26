import os
import base64
import json
import argparse
from pathlib import Path
from datetime import datetime
from baml_client.sync_client import b as baml_client
import baml_py
import requests

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
            print(f"Warning: Failed to load metadata for {image_path.name}: {e}")
    return None

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

def process_images_with_openrouter(api_key, directory_path, model_name="anthropic/claude-3-opus", model_pricing=None, 
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
        print(f"No PNG files found in {directory_path}")
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
    
    # Print filter summary
    if book_filter or chapter_start or chapter_end:
        print(f"\n{'='*60}")
        print(f"FILTER APPLIED:")
        if book_filter:
            print(f"  Book: {book_filter}")
        if chapter_start is not None or chapter_end is not None:
            if chapter_start == chapter_end:
                print(f"  Chapter: {chapter_start}")
            else:
                start_str = str(chapter_start) if chapter_start is not None else "beginning"
                end_str = str(chapter_end) if chapter_end is not None else "end"
                print(f"  Chapters: {start_str} to {end_str}")
        print(f"{'='*60}")
    
    print(f"\nFound {len(all_png_files)} total images")
    print(f"Skipped {skipped_no_metadata} images without metadata")
    print(f"Skipped {skipped_filtered} images not matching filters")
    print(f"Processing {len(png_files)} images")
    
    if not png_files:
        print(f"No images to process after applying filters")
        return
    
    # Create output directory named after the model
    # Replace slashes with underscores for valid directory name
    model_dir_name = model_name.replace("/", "_")
    output_dir = Path(directory_path) / model_dir_name
    output_dir.mkdir(exist_ok=True)
    
    print(f"Output directory: {output_dir}")
    
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
        print(f"\n{'='*60}")
        print(f"Processing: {png_file.name}")
        print(f"Book: {book}, Chapter: {chapter}, Verse: {verse}")
        print(f"{'='*60}")
        try:
            # Read and encode the image
            with open(png_file, "rb") as image_file:
                image_data = base64.b64encode(image_file.read()).decode('utf-8')
            
            # Prepare the payload (same as BAML would send)
            prompt_text = """Please extract the original text from the image. Please extract it exactly as it is in the image. Do not change anything. Please make sure you keep the older English used in the image such as the use of 'nay' and all footnotes. Also notice that footnotes might extend from the left column to the right column if the left column footnote terminates with a dash. Also note that the text is mostly English but does contain Latin, Greek, Hebrew and Arabic especially in footnotes."""
            
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
            
            # Send request to OpenRouter
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                extracted_text = result['choices'][0]['message']['content']
                
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
                print(f"Tokens: {prompt_tokens} prompt + {completion_tokens} completion = {total_tokens} total")
                if model_pricing:
                    print(f"Cost: ${cost:.6f}")
                print(extracted_text[:200] + "..." if len(extracted_text) > 200 else extracted_text)
                
                # Save results to file in model-specific directory
                output_file = output_dir / png_file.with_suffix('.md').name
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(extracted_text)
                print(f"Results saved to: {output_file}")
                
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
                
            else:
                print(f"Error processing {png_file.name}: {response.status_code} - {response.text}")
                
                # Log error to metrics
                metrics_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "file": png_file.name,
                    "model": model_name,
                    "error": f"{response.status_code}: {response.text}",
                    "success": False
                }
                with open(metrics_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(metrics_entry) + '\n')
                
        except Exception as e:
            print(f"Failed to process {png_file.name}: {str(e)}")
            
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
    print(f"\n{'='*60}")
    print(f"PROCESSING SUMMARY")
    print(f"{'='*60}")
    print(f"Images processed: {total_images}")
    print(f"Total tokens: {total_prompt_tokens} prompt + {total_completion_tokens} completion = {total_prompt_tokens + total_completion_tokens} total")
    if model_pricing:
        print(f"Total cost: ${total_cost:.6f}")
    print(f"Metrics saved to: {metrics_file}")
    print(f"{'='*60}")

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
            print(f"Warning: Failed to fetch models from OpenRouter (status {response.status_code})")
            print("Falling back to default model list")
            return get_fallback_models(), {}
    except Exception as e:
        print(f"Warning: Error fetching models from OpenRouter: {e}")
        print("Falling back to default model list")
        return get_fallback_models(), {}

def get_fallback_models():
    """Get fallback list of common models that support image input"""
    return {
        "z-ai/glm-4.5v": "GLM-4.5V",
        "anthropic/claude-3-sonnet": "Claude 3 Sonnet",
        "anthropic/claude-3-haiku": "Claude 3 Haiku",
        "openai/gpt-4o": "GPT-4O",
        "openai/gpt-4o-mini": "GPT-4O Mini"
    }

# Configuration
API_KEY = "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"     # Replace with your actual API key
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
        """
    )
    parser.add_argument('--book', '-b', type=str, help='Filter by book name (e.g., Genesis, Exodus)')
    parser.add_argument('--chapter-start', '-cs', type=int, help='Starting chapter (inclusive)')
    parser.add_argument('--chapter-end', '-ce', type=int, help='Ending chapter (inclusive)')
    parser.add_argument('--directory', '-d', type=str, default=DIRECTORY_PATH, 
                       help=f'Directory containing images (default: {DIRECTORY_PATH})')
    
    args = parser.parse_args()
    
    # Validate chapter range
    if args.chapter_start is not None and args.chapter_end is not None:
        if args.chapter_start > args.chapter_end:
            print("Error: chapter-start must be less than or equal to chapter-end")
            exit(1)
    
    print("Fetching available models from OpenRouter...")
    models, pricing_info = get_available_models(API_KEY)
    
    if not models:
        print("No vision models found. Please check your API key or network connection.")
        exit(1)
    
    # Define popular models order (well-known vision models)
    popular_models_order = [
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
