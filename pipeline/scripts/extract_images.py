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
    
    Returns:
        int: Total number of images that failed to process.
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

    failed_images = 0

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

            try:
                # Render the image to a Pixmap instead of extracting the raw XREF stream.
                # Extracting raw streams on 1,000 page PDFs exhausts C-level file handles internally in PyMuPDF
                # causing random "document closed" errors. Pixmaps are safely managed.
                pix = fitz.Pixmap(doc, xref)
                
                # If image is CMYK, convert to RGB first because Pillow handles RGB better
                if pix.n >= 5:
                    cmyk = pix
                    pix = fitz.Pixmap(fitz.csRGB, cmyk)
                    del cmyk # Free original
                    
                image_ext = "png" # Force PNG standardization for the pipeline
                image_bytes = pix.tobytes("png")

                # Open the image using PIL (Pillow)
                image = Image.open(io.BytesIO(image_bytes))

                # Save the image with volume-aware naming
                # Format: page{page_num}_image{volume}.{ext}
                image_filename = os.path.join(
                    output_dir, 
                    f"page{page_num + 1}_image{volume}.{image_ext}"
                )
                image.save(image_filename)
                print(f"Saved: {image_filename}")
                
                # Close PIL image to release memory
                image.close()
                del image_bytes
                del pix
                
            except Exception as e:
                print(f"Error processing image {img_index + 1} on page {page_num + 1}: {e}")
                failed_images += 1
            
        # Free page object reference explicitly per PyMuPDF best practices on massive documents
        del page
    
    try:
        # On massive PDFs, PyMuPDF sometimes aggressively garbage collects the C-pointer
        # before this explicit close(), throwing a ValueError: document closed.
        if not doc.is_closed:
            doc.close()
    except Exception as e:
        print(f"Warning on document close (safely ignored): {e}")
        
    print(f"\n✅ Extraction complete: {page_num + 1} pages processed ({failed_images} failures)")
    print(f"   Output directory: {output_dir}")
    return failed_images


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
        failed = extract_images_from_pdf(
            pdf_path=pdf_path,
            volume=args.volume,
            output_dir=args.output_dir
        )
        
        if failed > 0:
            print(f"Error: {failed} images failed to process.")
            exit(1)
        
    except FileNotFoundError as e:
        print(f"Error: {e}")
        exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        exit(1)