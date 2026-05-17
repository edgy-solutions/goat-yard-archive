import json
from pathlib import Path
import os

def clear_spanning_cache(alignment_dir: Path, entity_cache_dir: Path):
    alignment_files = list(alignment_dir.glob("*_alignment.json"))
    alignment_files.sort(key=lambda x: str(x.name))
    
    spanning_verses = []
    
    # Find spanning verses
    for i in range(len(alignment_files) - 1):
        curr_file = alignment_files[i]
        next_file = alignment_files[i+1]
        
        with open(curr_file, 'r') as f:
            curr_data = json.load(f)
        with open(next_file, 'r') as f:
            next_data = json.load(f)
            
        if not curr_data or not next_data:
            continue
            
        last_verse = curr_data[-1].get("verse_ref")
        first_verse = next_data[0].get("verse_ref")
        
        if last_verse and first_verse and last_verse == first_verse:
            # It's a spanning verse!
            spanning_verses.append((curr_file.name.replace("_alignment.json", ""), last_verse))
            
    print(f"Found {len(spanning_verses)} spanning verses.")
    
    # Delete from cache
    deleted_count = 0
    for page_name, verse_ref in spanning_verses:
        # Need to find the cache file. It might be prefixed with volX_
        # Let's just search for it
        cache_files = list(entity_cache_dir.glob(f"*{page_name}_entities.json"))
        for cache_file in cache_files:
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
                
            if verse_ref in cache_data:
                del cache_data[verse_ref]
                with open(cache_file, 'w') as f:
                    json.dump(cache_data, f, indent=2)
                deleted_count += 1
                print(f"Deleted {verse_ref} from {cache_file.name}")
                
    print(f"Successfully cleared {deleted_count} spanning verses from the entity cache.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python clear_spanning_cache.py <alignment_dir> <entity_cache_dir>")
        sys.exit(1)
    clear_spanning_cache(Path(sys.argv[1]), Path(sys.argv[2]))
