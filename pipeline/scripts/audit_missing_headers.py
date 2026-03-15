import os
import re
import json
import glob
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def audit_directory(base_dir, volume_name):
    print(f"--- Auditing {volume_name} ({base_dir}) ---")
    
    # normalized files are usually in a subdirectory like qwen_qwen3-vl-235b-a22b-thinking
    # identifying that subdir
    normalized_subdirs = list(Path(base_dir).glob("*qwen*"))
    if not normalized_subdirs:
        print(f"No normalized subdirectory found in {base_dir}")
        return

    normalized_dir = normalized_subdirs[0]
    print(f"Checking normalized files in: {normalized_dir}")

    # Find all metadata files in the base dir
    metadata_files = list(Path(base_dir).glob("*_metadata.json"))
    
    missing_headers = []
    checked_count = 0

    for meta_file in metadata_files:
        try:
            with open(meta_file, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            
            # Check if this page is a Chapter Start
            # Logic: verse "1" (string or int) and chapter > 1 (Chapter 1 usually handled differently or doesn't have spillover issues same way)
            # Actually user asked for "where chapter heading is missing", likely for any chapter.
            
            chapter = meta.get('chapter')
            verse = meta.get('verse')
            
            # Normalize verse to string for comparison
            verse_str = str(verse).strip()
            
            # Define base_name early
            base_name = meta_file.stem.replace('_metadata', '')

            if verse_str in ["1", "01", "1.0"] or verse == 1:
                print(f"  [CHECKING] {base_name} (Chapter {chapter}, Verse {verse})")
                checked_count += 1
                
                # Construct expected normalized filename
                normalized_file = normalized_dir / f"{base_name}_normalized.md"
                
                if not normalized_file.exists():
                     print(f"  [WARNING] Normalized file not found: {normalized_file}")
                     continue

                with open(normalized_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Check for Header
                # Relaxed regex: # Chapter N or # CHAP. N
                if not re.search(r'^#\s*Chapter\s+\d+|#\s*CHAP\.?\s+\d+|#\s*Chapter\s+[IVXLCD]+', content, re.IGNORECASE | re.MULTILINE):
                     missing_headers.append({
                         'file': normalized_file,
                         'chapter': chapter,
                         'page': meta.get('page_number')
                     })
            else:
                 pass # Skip non-chapter-start pages silently to avoid spam


        except Exception as e:
            print(f"Error reading {meta_file}: {e}")

    print(f"Checked {checked_count} chapter-start pages.")
    if missing_headers:
        print(f"FOUND {len(missing_headers)} PAGES MISSING HEADERS:")
        for miss in missing_headers:
            print(f"  [MISSING] Chapter {miss['chapter']} on Page {miss['page']}: {miss['file'].name}")
            # print(f"    Path: {miss['file']}")
    else:
        print("MATCHED: All checked chapter-start pages have headers.")
    print("\n")
    return len(missing_headers)

if __name__ == "__main__":
    # Base paths
    missing_found = 0
    # Genesis (Vol 1)
    vol1_path = BASE_DIR / "volume1"
    if vol1_path.exists():
        missing_found += audit_directory(vol1_path, "Genesis (Vol 1)")
    
    # Matthew (Vol 7)
    vol7_path = BASE_DIR / "volume7"
    if vol7_path.exists():
        missing_found += audit_directory(vol7_path, "Matthew (Vol 7)")
        
    if missing_found > 0:
        import sys
        sys.exit(1)
