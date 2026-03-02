import os
import json
from pathlib import Path
from dotenv import load_dotenv

def run_recovery():
    load_dotenv()
    base_dir = Path(os.getenv("COMMENTARY_DATA_DIR", os.getcwd()))
    entities_dir = base_dir / "artifacts" / "entities"
    
    if not entities_dir.exists():
        print(f"Directory not found: {entities_dir}")
        return

    VOL7_BOOKS = {"MATTHEW", "MARK", "LUKE", "JOHN"}
    VOL1_BOOKS = {"GENESIS", "EXODUS", "LEVITICUS", "NUMBERS", "DEUTERONOMY"}

    processed_count = 0
    recovered_count = 0

    print(f"Scanning {entities_dir} for mixed entity cache files...")

    # We specifically target files prepended with "vol1_" that might contain vol7 data
    # (Or just scan ALL json files to be safe and re-route their prefixes based on strict layout)
    for file_path in entities_dir.glob("*.json"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            # Dictionary split logic
            vol1_data = {}
            vol7_data = {}
            
            needs_split = False
            
            for verse_ref, entities in data.items():
                book = verse_ref.split()[0].upper()
                if book in VOL7_BOOKS:
                    vol7_data[verse_ref] = entities
                    if "vol1_" in file_path.name:
                        needs_split = True
                else:
                    vol1_data[verse_ref] = entities
                    if "vol7_" in file_path.name:
                        needs_split = True
                    
            if needs_split:
                # Prepare base name without the volX_ prefix so we can construct strictly correct names
                parts = file_path.name.split("_", 1)
                
                if len(parts) == 2 and parts[0].startswith("vol"):
                    base_name = parts[1]
                else:
                    base_name = file_path.name
                
                vol1_filepath = entities_dir / f"vol1_{base_name}"
                vol7_filepath = entities_dir / f"vol7_{base_name}"
                
                # Write Vol 1 back cleanly
                if vol1_data:
                    # Merge if exists and not the current file
                    if vol1_filepath.exists() and vol1_filepath != file_path:
                        with open(vol1_filepath, "r", encoding="utf-8") as f:
                            existing = json.load(f)
                            existing.update(vol1_data)
                            vol1_data = existing
                    
                    with open(vol1_filepath, "w", encoding="utf-8") as f:
                        json.dump(vol1_data, f, indent=2)
                elif vol1_filepath.exists() and vol1_filepath == file_path:
                    vol1_filepath.unlink() # Remove if we drained it completely of vol1 elements
                    
                # Write Vol 7 out cleanly
                if vol7_data:
                    if vol7_filepath.exists() and vol7_filepath != file_path:
                        with open(vol7_filepath, "r", encoding="utf-8") as f:
                            existing = json.load(f)
                            existing.update(vol7_data)
                            vol7_data = existing
                            
                    with open(vol7_filepath, "w", encoding="utf-8") as f:
                        json.dump(vol7_data, f, indent=2)
                elif vol7_filepath.exists() and vol7_filepath == file_path:
                    vol7_filepath.unlink() # Remove if we drained it completely of vol7 elements
                    
                # If we completely mapped this to NEW files and the original wasn't one of them, delete it.
                if file_path != vol1_filepath and file_path != vol7_filepath:
                    file_path.unlink()
                        
                processed_count += 1
                recovered_count += len(vol7_data)
                print(f"[RECOVERED] Sliced {file_path.name} -> Vol 1: {len(vol1_data)} items, Vol 7: {len(vol7_data)} items")
                
        except Exception as e:
            print(f"Error processing {file_path.name}: {e}")

    print(f"\nDone! Successfully split and repaired {processed_count} mixed volume entity files.")
    print(f"Salvaged {recovered_count} entity verses for Volume 7.")

if __name__ == "__main__":
    run_recovery()
