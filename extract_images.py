import fitz  # PyMuPDF library
import io
import os
import argparse
from pathlib import Path
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

# Base configuration
BASE_DIR = Path(os.getenv("COMMENTARY_DATA_DIR", os.getcwd()))
DEFAULT_DOCS_DIR = BASE_DIR / "docs"



def find_volume_pdf(volume: int, docs_dir: str = None) -> str:
    """
    Find the PDF file for a specific volume in the docs directory.
    
    Args:
        volume (int): Volume number to find
        docs_dir (str): Directory containing PDF files
        
    Returns:
        str: Path to the PDF file
        
    Raises:
        FileNotFoundError: If no matching PDF is found
    """
    if docs_dir is None:
        docs_dir = str(DEFAULT_DOCS_DIR)
        
    docs_path = Path(docs_dir)
    
    if not docs_path.exists():
        raise FileNotFoundError(f"Docs directory not found: {docs_dir}")
    
    # Search for PDF with volume number in filename
    # Expected format: "...Volume {volume}.pdf" or "...Vol {volume}.pdf"
    for pdf_file in docs_path.glob("*.pdf"):
        filename = pdf_file.name.lower()
        
        # Check for "volume X" or "vol X" patterns
        if f"volume {volume}" in filename or f"vol {volume}" in filename or f"volume{volume}" in filename:
            print(f"Found PDF for Volume {volume}: {pdf_file.name}")
            return str(pdf_file)
    
    raise FileNotFoundError(
        f"Could not find PDF for Volume {volume} in {docs_dir}. "
        f"Expected filename to contain 'Volume {volume}' or 'Vol {volume}'"
    )


def extract_images_from_pdf(pdf_path: str, volume: int, output_dir: str = None):
    """
    Extracts images from a PDF file and saves them to a specified directory.

    Args:
        pdf_path (str): The path to the input PDF file.
        volume (int): Volume number (used in output directory naming).
        output_dir (str): The directory where extracted images will be saved.
                         If None, uses "extracted_images_<volume>".
    """
    # Default output directory based on volume
    if output_dir is None:
        # Default to volume{N} in the data directory
        output_dir = str(BASE_DIR / f"volume{volume}")
    
    try:
        doc = fitz.open(pdf_path)
    except fitz.fitz.FileError:
        print(f"Error: Could not open PDF file at {pdf_path}. Please check the path.")
        return

    # Create output directory if it doesn't exist
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created output directory: {output_dir}")

    for page_num in range(len(doc)):
        page = doc[page_num]
        image_list = page.get_images(full=True)

        if image_list:
            print(f"Found {len(image_list)} images on page {page_num + 1}")
        else:
            print(f"No images found on page {page_num + 1}")
            continue

        for img_index, img_info in enumerate(image_list):
            xref = img_info[0]  # Get the XREF of the image
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]

            try:
                # Open the image using PIL (Pillow)
                image = Image.open(io.BytesIO(image_bytes))

                # Save the image with volume-aware naming
                # Format: page{page_num}_image{volume}.{ext}
                # This matches the expected format for ingestion pipeline
                image_filename = os.path.join(
                    output_dir, 
                    f"page{page_num + 1}_image{volume}.{image_ext}"
                )
                image.save(image_filename)
                print(f"Saved: {image_filename}")
            except Exception as e:
                print(f"Error processing image {img_index + 1} on page {page_num + 1}: {e}")

    doc.close()
    print(f"\n✅ Extraction complete: {len(doc)} pages processed")
    print(f"   Output directory: {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract images from Gill Commentary PDF volumes"
    )
    parser.add_argument(
        "volume",
        type=int,
        help="Volume number to extract (e.g., 1 for Volume 1, 7 for Volume 7)"
    )
    parser.add_argument(
        "--docs-dir",
        default=None,
        help="Directory containing PDF files (default: $COMMENTARY_DATA_DIR/docs)"
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory (default: $COMMENTARY_DATA_DIR/volume<volume>)"
    )
    parser.add_argument(
        "--pdf-path",
        help="Direct path to PDF file (bypasses auto-detection)"
    )
    
    args = parser.parse_args()
    
    try:
        # Get PDF path (either from argument or auto-detect)
        if args.pdf_path:
            pdf_path = args.pdf_path
            print(f"Using specified PDF: {pdf_path}")
        else:
            pdf_path = find_volume_pdf(args.volume, args.docs_dir)
        
        # Extract images
        extract_images_from_pdf(
            pdf_path=pdf_path,
            volume=args.volume,
            output_dir=args.output_dir
        )
        
    except FileNotFoundError as e:
        print(f"Error: {e}")
        exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        exit(1)