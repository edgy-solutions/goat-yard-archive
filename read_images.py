import os
import base64
import json
from pathlib import Path
from baml_client.sync_client import b as baml_client
import baml_py
import requests

def process_images_with_openrouter(api_key, directory_path, model_name="anthropic/claude-3-opus"):
    """
    Process all PNG images in a directory using OpenRouter API via BAML
    
    Args:
        api_key (str): Your OpenRouter API key
        directory_path (str): Path to directory containing PNG images
        model_name (str): OpenRouter model to use
    """
    
    # Get all PNG files in the directory
    png_files = list(Path(directory_path).glob("*.png"))
    
    if not png_files:
        print(f"No PNG files found in {directory_path}")
        return
    
    # Create output directory named after the model
    # Replace slashes with underscores for valid directory name
    model_dir_name = model_name.replace("/", "_")
    output_dir = Path(directory_path) / model_dir_name
    output_dir.mkdir(exist_ok=True)
    
    print(f"Output directory: {output_dir}")
    
    # Create a client registry to override the model
    client_registry = baml_py.ClientRegistry()
    client_registry.add_llm_client(
        "OpenRouter",
        provider="openai",
        options={
            "model": model_name,
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": api_key
        }
    )
    
    # Create a BAML client with the custom registry
    custom_client = baml_client.with_options(client_registry=client_registry)
    
    for png_file in png_files:
        try:
            # Load image for BAML
            image = baml_py.Image.from_path(str(png_file))
            
            # Call BAML function to extract text
            extracted_text = custom_client.ExtractTextFromImage(image=image)
            
            print(f"\n=== Results for {png_file.name} ===")
            print(extracted_text[:200] + "..." if len(extracted_text) > 200 else extracted_text)
            
            # Save results to file in model-specific directory
            output_file = output_dir / png_file.with_suffix('.md').name
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(extracted_text)
            print(f"Results saved to: {output_file}")
                
        except Exception as e:
            print(f"Failed to process {png_file.name}: {str(e)}")

def get_available_models(api_key):
    """Get list of available models from OpenRouter that support image input"""
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
            
            return vision_models
        else:
            print(f"Warning: Failed to fetch models from OpenRouter (status {response.status_code})")
            print("Falling back to default model list")
            return get_fallback_models()
    except Exception as e:
        print(f"Warning: Error fetching models from OpenRouter: {e}")
        print("Falling back to default model list")
        return get_fallback_models()

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
DIRECTORY_PATH = "./images"  # Replace with your directory path

if __name__ == "__main__":
    print("Fetching available models from OpenRouter...")
    models = get_available_models(API_KEY)
    
    if not models:
        print("No vision models found. Please check your API key or network connection.")
        exit(1)
    
    print(f"\nAvailable models that support image input ({len(models)} models):")
    # Create a numbered list for selection
    model_list = list(models.items())
    for idx, (model_id, model_name) in enumerate(model_list[:20], 1):  # Show first 20
        print(f"{idx}. {model_name} ({model_id})")
    
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
    
    # Run the processing
    process_images_with_openrouter(API_KEY, DIRECTORY_PATH, selected_model)
