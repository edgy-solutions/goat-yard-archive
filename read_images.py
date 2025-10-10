import os
import base64
import requests
import json
from pathlib import Path

def process_images_with_openrouter(api_key, directory_path, prompt, model_name="anthropic/claude-3-opus"):
    """
    Process all PNG images in a directory using OpenRouter API
    
    Args:
        api_key (str): Your OpenRouter API key
        directory_path (str): Path to directory containing PNG images
        prompt (str): The prompt to send with each image
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
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    for png_file in png_files:
        try:
            # Read and encode the image
            with open(png_file, "rb") as image_file:
                image_data = base64.b64encode(image_file.read()).decode('utf-8')
            
            # Prepare the payload
            payload = {
                "model": model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
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
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                extracted_text = result['choices'][0]['message']['content']
                
                print(f"\n=== Results for {png_file.name} ===")
                print(extracted_text[:200] + "..." if len(extracted_text) > 200 else extracted_text)
                
                # Save results to file in model-specific directory
                output_file = output_dir / png_file.with_suffix('.md').name
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(extracted_text)
                print(f"Results saved to: {output_file}")
                
            else:
                print(f"Error processing {png_file.name}: {response.status_code} - {response.text}")
                
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
PROMPT = "Please extract the original text from the image. Please extract it exactly as it is in the image. Do not change anything. Please make sure you keep the older English used in the image such as the use of 'nay' and all footnotes. Also notice that footnotes might extend from the left column to the right column if the left column footnote terminates with a dash. Also note that the text is mostly English but does contain Latin, Greek, Hebrew and Arabic especially in footnotes."

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
    process_images_with_openrouter(API_KEY, DIRECTORY_PATH, PROMPT, selected_model)
