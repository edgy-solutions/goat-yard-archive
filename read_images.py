import os
import base64
import json
from pathlib import Path
from baml_client.sync_client import b as baml_client
import baml_py

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

def get_available_models():
    """Get list of available models that support image input"""
    # Common models that support image input
    return {
        "1": "z-ai/glm-4.5v",
        "2": "anthropic/claude-3-sonnet",
        "3": "anthropic/claude-3-haiku",
        "4": "openai/gpt-4o",
        "5": "openai/gpt-4o-mini"
    }

# Configuration
API_KEY = "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"     # Replace with your actual API key
DIRECTORY_PATH = "./images"  # Replace with your directory path

if __name__ == "__main__":
    # Show available models
    models = get_available_models()
    print("Available models that support image input:")
    for key, model in models.items():
        print(f"{key}. {model}")
    
    # Let user choose a model
    choice = input("\nSelect a model (1-5) or enter custom model name: ").strip()
    
    if choice in models:
        selected_model = models[choice]
    else:
        selected_model = choice  # Allow custom model input
    
    print(f"Using model: {selected_model}")
    
    # Run the processing
    process_images_with_openrouter(API_KEY, DIRECTORY_PATH, selected_model)
