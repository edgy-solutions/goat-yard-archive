import fitz  # PyMuPDF library
import io
from PIL import Image

def extract_images_from_pdf(pdf_path, output_dir="extracted_images"):
    """
    Extracts images from a PDF file and saves them to a specified directory.

    Args:
        pdf_path (str): The path to the input PDF file.
        output_dir (str): The directory where extracted images will be saved.
    """
    try:
        doc = fitz.open(pdf_path)
    except fitz.fitz.FileError:
        print(f"Error: Could not open PDF file at {pdf_path}. Please check the path.")
        return

    # Create output directory if it doesn't exist
    import os
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

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

                # Save the image
                image_filename = os.path.join(output_dir, f"page{page_num + 1}_image{img_index + 1}.{image_ext}")
                image.save(image_filename)
                print(f"Saved: {image_filename}")
            except Exception as e:
                print(f"Error processing image {img_index + 1} on page {page_num + 1}: {e}")

    doc.close()

# Example usage:
if __name__ == "__main__":
    pdf_file = "9781579784768_An Exposition of the Old and New Testaments - Volume 1.pdf"  # Replace with your PDF file name
    extract_images_from_pdf(pdf_file)