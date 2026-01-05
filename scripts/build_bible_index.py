import os
import re
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Standard USFM Markers
# \id MAT
# \c 1
# \v 1 The book of the generation...

def parse_usfm(directory):
    bible_map = {}
    
    if not os.path.exists(directory):
        print(f"Directory not found: {directory}")
        return {}

    for filename in os.listdir(directory):
        if not filename.endswith(".usfm"): continue
        
        filepath = os.path.join(directory, filename)
        print(f"Processing {filename}...")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
            # 1. Get Book ID (e.g., "MAT")
            # Note: The KJV 2006 files might have slightly different header format, 
            # but \id is standard.
            book_match = re.search(r'\\id\s+(\w+)', content)
            if not book_match: 
                print(f"  No book ID found in {filename}")
                continue
            book_id = book_match.group(1).upper()
            
            # 2. Split by Chapter (\c )
            chapters = re.split(r'\\c\s+(\d+)', content)
            
            # The split creates a list like [header, "1", text_of_ch1, "2", text_of_ch2...]
            for i in range(1, len(chapters), 2):
                chapter_num = chapters[i]
                chapter_text = chapters[i+1]
                
                # 3. Split by Verse (\v )
                verses = re.split(r'\\v\s+(\d+)', chapter_text)
                
                for j in range(1, len(verses), 2):
                    verse_num = verses[j]
                    verse_text = verses[j+1]
                    
                    # Clean the text (remove other USFM markers like \p, \q, footnotes)
                    # Clean the text (remove other USFM markers like \p, \q, footnotes)
                    # 1. Remove Strong's numbers: |strong="G1234"
                    # The pattern is |key="value" attached to words
                    clean_text = re.sub(r'\|strong="[^"]*"', '', verse_text)
                    
                    # 2. Aggressive strip of remaining backslash commands (USFM tags) and KJV formatting
                    clean_text = re.sub(r'\\[a-z0-9]+\*?', '', clean_text) # Standard USFM tags
                    clean_text = re.sub(r'\\\+[a-z]+\*?', '', clean_text) # KJV add/trans tags like \+w \+w*
                    clean_text = clean_text.strip()
                    
                    # 3. Collapse multiple spaces
                    clean_text = ' '.join(clean_text.split())
                    
                    # Create the Key: "MAT 1:1" format to match internal VerseRef standard
                    # Or USFM standard "MAT_1_1"? 
                    # Our codebase uses "MATTHEW 1:1" or "GENESIS 1:1".
                    # We need a mapping from "MAT" to "MATTHEW".
                    
                    # For now, let's store it as "MAT 1:1" and "MAT_1_1" to cover bases,
                    # OR update the mapping logic.
                    # The user requested "MAT_1_1" in the example, but ingestion uses full names.
                    # Let's save as "BOOK_CH_VS" (STD) AND "BookName Ch:Vs" if we can map it.
                    
                    # For simple injection, we might need a mapping.
                    # Let's just store the standard USFM ID for now:
                    
                    key = f"{book_id} {chapter_num}:{verse_num}" 
                    bible_map[key] = clean_text
                    
                    # Also add underscores for backup lookup
                    key_us = f"{book_id}_{chapter_num}_{verse_num}"
                    bible_map[key_us] = clean_text

    return bible_map

# Mapping USFM codes to Full Names (for ingest matching)
USFM_TO_FULL = {
    "GEN": "GENESIS", "EXO": "EXODUS", "LEV": "LEVITICUS", "NUM": "NUMBERS", "DEU": "DEUTERONOMY",
    "MAT": "MATTHEW", "MRK": "MARK", "LUK": "LUKE", "JHN": "JOHN", "ACT": "ACTS",
    "ROM": "ROMANS", "1CO": "1 CORINTHIANS", "2CO": "2 CORINTHIANS", "GAL": "GALATIANS", "EPH": "EPHESIANS", "PHP": "PHILIPPIANS", "COL": "COLOSSIANS",
    "1TH": "1 THESSALONIANS", "2TH": "2 THESSALONIANS", "1TI": "1 TIMOTHY", "2TI": "2 TIMOTHY", "TIT": "TITUS", "PHM": "PHILEMON",
    "HEB": "HEBREWS", "JAS": "JAMES", "1PE": "1 PETER", "2PE": "2 PETER", "1JN": "1 JOHN", "2JN": "2 JOHN", "3JN": "3 JOHN", "JUD": "JUDE", "REV": "REVELATION"
}
# (Add OT mappings if needed, but starting with NT/common is safe)

if __name__ == "__main__":
    # Determine Bibles directory
    _env_data_dir = os.getenv("COMMENTARY_DATA_DIR")
    if _env_data_dir:
        BIBLES_DIR = Path(_env_data_dir).parent / "bibles"
    else:
        # Fallback to repo root (assuming script is in scripts/ subdir)
        BIBLES_DIR = Path(__file__).parent.parent
    
    # Adjust path to where files were found: eng-kjv2006_usfm
    input_dir = BIBLES_DIR / "eng-kjv2006_usfm"
    print(f"Reading USFM files from: {input_dir}")
    
    data = parse_usfm(str(input_dir))
    
    # Post-process to add Full Name keys
    expanded_data = {}
    for k, v in data.items():
        expanded_data[k] = v
        
        # Try to convert "MAT 1:1" -> "MATTHEW 1:1"
        try:
            parts = k.split()
            if len(parts) == 2 and ":" in parts[1]:
                book_code = parts[0]
                ref_rest = parts[1]
                if book_code in USFM_TO_FULL:
                    full_name = USFM_TO_FULL[book_code]
                    new_key = f"{full_name} {ref_rest}"
                    expanded_data[new_key] = v
        except:
            pass
            
    with open("kjv_fast_lookup.json", "w", encoding='utf-8') as f:
        json.dump(expanded_data, f, indent=2)
    print(f"✅ Indexed {len(expanded_data)} keys.")
