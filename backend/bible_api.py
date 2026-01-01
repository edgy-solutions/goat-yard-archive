import json
import os
import re
from fastapi import APIRouter, HTTPException

router = APIRouter()

# Load Bible into memory on startup
BIBLE_MAP = {}

def load_bible_index():
    global BIBLE_MAP
    # 1. Try Local Filesystem
    possible_paths = ["kjv_fast_lookup.json", "../kjv_fast_lookup.json", "backend/kjv_fast_lookup.json"]
    for p in possible_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    BIBLE_MAP = json.load(f)
                print(f"Bible API: Loaded {len(BIBLE_MAP)} verses from local: {p}")
                return
            except Exception as e:
                print(f"Bible API: Error reading local file {p}: {e}")

    # 2. Try MinIO (Fallback)
    print("Bible API: Local index not found. Attempting MinIO download...")
    try:
        from minio import Minio
        # Import config from env (relying on main.py env vars or dotenv)
        # We need to construct the client here as we might be imported before main
        endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
        access = os.getenv("MINIO_ROOT_USER", "minio") 
        secret = os.getenv("MINIO_ROOT_PASSWORD", "!mandy77")
        bucket = os.getenv("MINIO_BUCKET_NAME", "scans")
        
        client = Minio(endpoint, access, secret, secure=False)
        response = client.get_object(bucket, "kjv_fast_lookup.json")
        try:
             content = response.read()
             BIBLE_MAP = json.loads(content)
             print(f"Bible API: Loaded {len(BIBLE_MAP)} verses from MinIO: {bucket}/kjv_fast_lookup.json")
             
             # Optional: Cache it locally for next time?
             # with open("kjv_fast_lookup.json", "w", encoding="utf-8") as f:
             #    json.dump(BIBLE_MAP, f)
        finally:
             response.close()
             
    except Exception as e:
        print(f"Bible API Error: Could not load index from MinIO: {e}")

# Initial Load
load_bible_index()

# Roman Numeral Helper (Simple 1-150 range covers most Bible chapters)
ROMAN_MAP = {
    'i': 1, 'ii': 2, 'iii': 3, 'iv': 4, 'v': 5, 'vi': 6, 'vii': 7, 'viii': 8, 'ix': 9, 'x': 10,
    'xi': 11, 'xii': 12, 'xiii': 13, 'xiv': 14, 'xv': 15, 'xvi': 16, 'xvii': 17, 'xviii': 18, 'xix': 19, 'xx': 20,
    'xxi': 21, 'xxii': 22, 'xxiii': 23, 'xxiv': 24, 'xxv': 25, 'xxvi': 26, 'xxvii': 27, 'xxviii': 28, 'xxix': 29, 'xxx': 30,
    'xl': 40, 'l': 50, 'lx': 60, 'lxx': 70, 'lxxx': 80, 'xc': 90, 'c': 100, 'ci': 101, 'cx': 110, 'cl': 150
}
# Fallback to book map if needed
BOOK_MAP = {
    "matt": "MATTHEW", "mat": "MATTHEW", "mt": "MATTHEW",
    "mark": "MARK", "mrk": "MARK", "mk": "MARK",
    "luke": "LUKE", "luk": "LUKE", "lk": "LUKE",
    "john": "JOHN", "jhn": "JOHN", "jn": "JOHN",
    "acts": "ACTS", "act": "ACTS",
    "rom": "ROMANS", "rom": "ROMANS",
    "gen": "GENESIS", "exod": "EXODUS", "lev": "LEVITICUS", "num": "NUMBERS", "deut": "DEUTERONOMY"
}

def parse_roman(s):
    """Simple roman to int converter."""
    s = s.lower().strip('.')
    if s.isdigit(): return int(s)
    
    # Try direct map
    if s in ROMAN_MAP: return ROMAN_MAP[s]
    
    # Basic additive parsing (very simple, assumes valid roman)
    # Proper parsing is complex, but for "cxix" (119) we might need a library if map fails.
    # For now, stick to map or return string for fuzzy match?
    # Actually, let's just use the map for commons.
    return s

def normalize_reference(ref: str) -> str:
    """
    Converts "Mark xvi. 11" -> "MARK 16:11"
    """
    # Remove periods and extra spaces
    clean = ref.replace('.', ' ').strip()
    parts = clean.split()
    
    # Heuristic: [BOOK] [CHAPTER] [VERSE]
    # "Mark xvi 11" -> ["Mark", "xvi", "11"]
    # "1 Cor 13 4" -> ["1", "Cor", "13", "4"] ?
    
    if len(parts) < 2: return ref
    
    verse = parts[-1]
    chapter = parts[-2]
    
    # Book is everything before
    book_raw = " ".join(parts[:-2]).lower()
    
    # Handle "1 Cor" vs "Cor"
    # Map Check
    book_norm = BOOK_MAP.get(book_raw, book_raw.upper())
    
    # Roman / Chapter Normalize
    # If chapter is Roman, convert
    chapter_num = chapter
    if not chapter.isdigit():
        # Try Roman
        if chapter.lower() in ROMAN_MAP:
             chapter_num = str(ROMAN_MAP[chapter.lower()])
    
    return f"{book_norm} {chapter_num}:{verse}"

@router.get("/api/verse/{ref}")
def get_verse_text(ref: str):
    """
    Input: "ROM_1_4" or "Rom. i. 4" (Needs normalization)
    Output: {"text": "And declared to be..."}
    """
    # 1. Direct Lookup (Fastest)
    if ref in BIBLE_MAP:
        return {"ref": ref, "text": BIBLE_MAP[ref]}
        
    # 2. Normalize and Lookup
    norm_ref = normalize_reference(ref)
    
    # Try normalized
    if norm_ref in BIBLE_MAP:
         return {"ref": norm_ref, "text": BIBLE_MAP[norm_ref]}
         
    # Try finding close match?
    # For now, strict.
    
    raise HTTPException(status_code=404, detail=f"Verse not found: {norm_ref}")
