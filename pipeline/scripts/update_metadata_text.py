"""
Utility script to update existing metadata files with cleaned Greek/Hebrew text.

This script re-extracts the Greek/Hebrew verses from USFM files using the new
clean_usfm_text() function, updating metadata files to have clean text without
USFM markup and Strong's numbers.

Usage:
    python update_metadata_text.py <directory>
    
    Or for a single file:
    python update_metadata_text.py <metadata_file.json>
"""

import sys
import json
from pathlib import Path
import io

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from get_md import (
    get_greek_verse,
    get_hebrew_verse,
    is_new_testament,
    is_old_testament,
    log_print
)

def update_metadata_file(metadata_path):
    """Update a single metadata file with cleaned text."""
    try:
        # Read existing metadata
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        book_name = metadata.get('book_name')
        chapter = metadata.get('chapter')
        verse = metadata.get('verse')
        
        if not (book_name and chapter and verse):
            print(f"Skipping {metadata_path.name}: Missing book/chapter/verse")
            return False
        
        # Check if text needs updating (has USFM markup)
        needs_update = False
        
        if metadata.get('greek_text'):
            # Check if any verse has USFM markup (Strong's numbers, \w tags, or footnotes)
            for v_text in metadata['greek_text'].values():
                if '\\w' in str(v_text) or '|strong=' in str(v_text) or '\\f' in str(v_text):
                    needs_update = True
                    break
        
        if metadata.get('hebrew_text'):
            for v_text in metadata['hebrew_text'].values():
                if '\\w' in str(v_text) or '|strong=' in str(v_text) or '\\f' in str(v_text):
                    needs_update = True
                    break
        
        if not needs_update:
            print(f"Skipping {metadata_path.name}: Already has clean text")
            return False
        
        # Re-extract text with cleaning
        if is_new_testament(book_name):
            print(f"Updating Greek text for {book_name} {chapter}:{verse}")
            greek_verses = get_greek_verse(book_name, chapter, verse)
            metadata['greek_text'] = greek_verses
            
        elif is_old_testament(book_name):
            print(f"Updating Hebrew text for {book_name} {chapter}:{verse}")
            hebrew_verses = get_hebrew_verse(book_name, chapter, verse)
            metadata['hebrew_text'] = hebrew_verses
        
        # Save updated metadata
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Updated {metadata_path.name}")
        return True
        
    except Exception as e:
        print(f"✗ Error updating {metadata_path.name}: {e}")
        return False

def update_directory(directory):
    """Update all metadata files in a directory."""
    directory = Path(directory)
    
    if not directory.is_dir():
        print(f"Error: {directory} is not a directory")
        return
    
    # Find all metadata files
    metadata_files = list(directory.glob('*_metadata.json'))
    
    if not metadata_files:
        print(f"No metadata files found in {directory}")
        return
    
    print(f"Found {len(metadata_files)} metadata files")
    print("=" * 60)
    
    updated_count = 0
    skipped_count = 0
    error_count = 0
    
    for metadata_file in sorted(metadata_files):
        result = update_metadata_file(metadata_file)
        if result:
            updated_count += 1
        elif result is False:
            skipped_count += 1
        else:
            error_count += 1
    
    print("=" * 60)
    print(f"Complete: {updated_count} updated, {skipped_count} skipped, {error_count} errors")

def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    
    path = Path(sys.argv[1])
    
    if not path.exists():
        print(f"Error: {path} does not exist")
        sys.exit(1)
    
    if path.is_file():
        # Update single file
        if path.name.endswith('_metadata.json'):
            print(f"Updating single file: {path}")
            update_metadata_file(path)
        else:
            print(f"Error: {path} is not a metadata file (*_metadata.json)")
            sys.exit(1)
    elif path.is_dir():
        # Update directory
        update_directory(path)
    else:
        print(f"Error: {path} is neither a file nor directory")
        sys.exit(1)

if __name__ == "__main__":
    main()
