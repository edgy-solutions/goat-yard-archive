import os
import json
import glob
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def load_bible_index(path="kjv_fast_lookup.json"):
    if not os.path.exists(path):
        # Try finding it in backend or typical locations
        possible = ["kjv_fast_lookup.json", "backend/kjv_fast_lookup.json", "../kjv_fast_lookup.json"]
        for p in possible:
             if os.path.exists(p):
                 path = p
                 break
    
    if not os.path.exists(path):
        print(f"ERROR: Could not find KJV index at {path}")
        return None
        
    print(f"Loading Bible Index from {path}...")
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def parse_verse_string(v_str):
    """Parse '1', '1-5', '1,3,5' into a set of integers."""
    verses = set()
    s = str(v_str).strip()
    if not s or s.lower() == 'none':
        return verses
        
    try:
        if ':' in s:
            parts = s.split(',')
            for p in parts:
                if ':' in p:
                     pass # handled in complex
                else:
                    if '-' in p:
                        start, end = map(int, p.split('-'))
                        verses.update(range(start, end + 1))
                    else:
                        verses.add(int(p))
    except:
        pass
    return verses

def parse_verse_complex(chapter_context, v_str):
    """
    Returns a list of (chapter, verse_num) tuples.
    If v_str is simple ("1-5"), uses chapter_context.
    If v_str is complex ("2:17, 3:1"), uses explicit chapters.
    """
    results = set()
    s = str(v_str).strip()
    if not s or s.lower() == 'none':
        return results

    # Split by comma first
    parts = s.split(',')
    
    for p in parts:
        p = p.strip()
        current_ch = chapter_context
        
        # Check for explicit chapter "3:1-5"
        if ':' in p:
            try:
                ch_str, v_part = p.split(':')
                current_ch = int(ch_str)
                p = v_part
            except:
                continue
        
        # Now parse verse part "1-5" or "1"
        try:
            if '-' in p:
                start, end = map(int, p.split('-'))
                for v in range(start, end + 1):
                    results.add((current_ch, v))
            else:
                results.add((current_ch, int(p)))
        except:
            pass # ignore parse errors for now
            
    return results

def audit_volume(volume_path, bible_index):
    print(f"\nScanning {volume_path}...")
    
    # Store found verses: { Book: { Chapter: {Set of Verses} } }
    found_data = {}
    
    files = sorted(list(Path(volume_path).glob("*_metadata.json")))
    print(f"Found {len(files)} metadata files.")
    
    for f in files:
        try:
            with open(f, 'r', encoding='utf-8') as jf:
                meta = json.load(jf)
            
            book = meta.get('book_name')
            chapter = meta.get('chapter')
            verse = meta.get('verse')
            
            if not book or not verse:
                continue
                
            book = book.upper() # Normalize
            
            # Parse verses
            ch_context = int(chapter) if chapter else 0
            
            parsed_cv = parse_verse_complex(ch_context, verse)
            
            if book not in found_data:
                found_data[book] = {}
            
            for (ch, v) in parsed_cv:
                if ch == 0: continue # Skip if no chapter resolved
                
                if ch not in found_data[book]:
                    found_data[book][ch] = set()
                found_data[book][ch].add(v)
                
        except Exception as e:
            # print(f"Skipping {f.name}: {e}")
            pass

    # Build Expected Structure locally from the map keys
    expected_structure = {} # Book -> { Chapter -> MaxVerse }
    
    # Heuristic: Scan all keys in bible_index to build expected structure
    for key in bible_index.keys():
        # Key format "Genesis 1:1" or "GEN 1:1" or "GENESIS 1:1"
        try:
            parts = key.rsplit(' ', 1)
            book_name = parts[0].upper()
            cv = parts[1]
            c_str, v_str = cv.split(':')
            ch = int(c_str)
            v = int(v_str)
            
            if book_name not in expected_structure:
                expected_structure[book_name] = {}
            if ch not in expected_structure[book_name]:
                expected_structure[book_name][ch] = 0
            
            if v > expected_structure[book_name][ch]:
                expected_structure[book_name][ch] = v
        except:
            pass

    # Now Compare
    total_gaps = 0
    
    for book in sorted(found_data.keys()):
        # Try fuzzy match for book name logic could be here, but let's assume strict first
        if book not in expected_structure:
            # Try removing periods or fuzzy
            if book.replace('.', '') in expected_structure:
                 book_key = book.replace('.', '')
            else:
                 print(f"\n[WARNING] Book '{book}' found in metadata but not in KJV Index (Spelling mismatch?)")
                 continue
        else:
            book_key = book
            
        print(f"\nAudit for {book} (Matched KJV: {book_key}):")
        book_gaps = 0
        
        found_chapters = sorted(found_data[book].keys())
        if not found_chapters:
            continue
            
        min_ch = min(found_chapters)
        max_ch = max(found_chapters)
        
        for ch in range(min_ch, max_ch + 1):
            if ch not in expected_structure[book_key]:
                continue
                
            max_v = expected_structure[book_key][ch]
            found_v_set = found_data[book].get(ch, set())
            
            missing_v = []
            for v in range(1, max_v + 1):
                if v not in found_v_set:
                    missing_v.append(v)
            
            if missing_v:
                # Group consecutive numbers for cleaner output
                ranges = []
                import itertools
                for k, g in itertools.groupby(enumerate(missing_v), lambda ix: ix[0] - ix[1]):
                    group = list(map(lambda ix: ix[1], g))
                    if len(group) == 1:
                        ranges.append(str(group[0]))
                    else:
                        ranges.append(f"{group[0]}-{group[-1]}")
                
                print(f"  Chapter {ch} Missing: {', '.join(ranges)} (Expected 1-{max_v})")
                book_gaps += len(missing_v)
                total_gaps += len(missing_v)
        
        if book_gaps == 0:
            print(f"  OK (Chapters {min_ch}-{max_ch} fully covered)")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("volume_path", nargs="?", default=".", help="Path to volume directory")
    args = parser.parse_args()
    
    # Find vol dirs
    search_dirs = []
    
    # If CWD has metadata files, assume it IS a volume dir
    if glob.glob("*.json") and "volume" not in os.getcwd():
         # Maybe user is INSIDE volume1?
         pass

    if args.volume_path == ".":
        # Check if we are in a volume dir
        if glob.glob("*_metadata.json"):
            search_dirs.append(os.getcwd())
        
        # Check for volume* dirs
        search_dirs.extend(glob.glob("volume*"))
        search_dirs.extend(glob.glob("commentary/volume*"))
        
        env_data = os.getenv("COMMENTARY_DATA_DIR")
        if env_data:
            search_dirs.append(env_data)
            search_dirs.extend(glob.glob(os.path.join(env_data, "volume*")))
            search_dirs.extend(glob.glob(os.path.join(env_data, "commentary/volume*")))
    else:
        search_dirs = [args.volume_path]
        
    # Dedupe
    search_dirs = list(set([os.path.abspath(d) for d in search_dirs if os.path.exists(d) and os.path.isdir(d)]))
    
    # Filter for dirs that actually contain metadata
    valid_dirs = []
    for d in search_dirs:
        if list(Path(d).glob("*_metadata.json")):
            valid_dirs.append(d)
    
    if not valid_dirs:
        print("No directories with metadata files found. Please provide a path.")
        if search_dirs:
            print(f"Checked: {search_dirs}")
        exit(1)
        
    index = load_bible_index()
    if not index:
        exit(1)
        
    for d in valid_dirs:
        print(f"checking {d}")
        audit_volume(d, index)
