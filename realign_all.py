
import os
import re
from pathlib import Path
from align_verses import VerseAligner
import logging

def main():
    logging.basicConfig(level=logging.INFO)
    
    # directories to scan
    base_dir = Path("outputs/alignment")
    # Map output subdir to source directory
    subdir_map = {
        "genesis": "extracted_images",
        "matthew": "extracted_images_7"
    }
    
    files_to_process = []
    
    for subdir, source_dir in subdir_map.items():
        # Source directory to scan for pages
        src_path = Path(source_dir)
        if not src_path.exists():
            print(f"Source Directory not found: {src_path}")
            continue
            
        # Output directory
        out_subdir = base_dir / subdir
        out_subdir.mkdir(parents=True, exist_ok=True)
        
        print(f"Scanning {src_path} for pages...")
        
        # Scan for metadata files to identify pages
        for filename in os.listdir(src_path):
            if filename.endswith("_metadata.json"):
                # Extract page name (remove _metadata.json)
                page_name = filename.replace("_metadata.json", "")
                
                # We want to process ALL pages found in source, 
                # putting results into out_subdir
                files_to_process.append((page_name, out_subdir, source_dir))
    
    print(f"Found {len(files_to_process)} pages to align.")
    
    for i, (page_name, output_dir, source_dir) in enumerate(files_to_process):
        print(f"[{i+1}/{len(files_to_process)}] Processing {page_name} (Source: {source_dir})...")
        
        try:
            # Initialize aligner for this specific source directory
            aligner = VerseAligner(extracted_dir=source_dir)
            
            # Process page
            results = aligner.process_page(page_name, debug=True)
            
            # generated file is in flat outputs/alignment dir usually?
            # VerseAligner defaults output_dir="outputs/alignment" in init.
            # So files are at outputs/alignment/{page_name}_alignment.json
            
            flat_output = base_dir / f"{page_name}_alignment.json"
            flat_debug = base_dir / f"{page_name}_debug.png"
            
            # Move to correct subdir
            dest_json = output_dir / f"{page_name}_alignment.json"
            dest_png = output_dir / f"{page_name}_debug.png"
            
            if flat_output.exists():
                flat_output.replace(dest_json)
                print(f"  Saved to: {dest_json}")
                
            if flat_debug.exists():
                flat_debug.replace(dest_png)
                print(f"  Debug image: {dest_png}")
                
        except Exception as e:
            print(f"  FAILED {page_name}: {e}")

if __name__ == "__main__":
    main()
