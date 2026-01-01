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

    # 2. Try MinIO (Fallback) - Only if enabled/needed
    # (Stripped for brevity, can re-add if needed, but local is primary path)
    print("Bible API: Local index not found. Skipping MinIO fallback (ensure file is generated).")

# Initial Load
load_bible_index()

# Only used if standard python int() fails on a roman numeral
def roman_to_int(s):
    """
    Parses a lowercase roman numeral string into an integer.
    Handles standard additive notation (ix, iv, etc).
    """
    if not s: return 0
    if s.isdigit(): return int(s)
    
    rom_val = {'i': 1, 'v': 5, 'x': 10, 'l': 50, 'c': 100, 'd': 500, 'm': 1000}
    int_val = 0
    s = s.lower()
    
    for i in range(len(s)):
        if i > 0 and rom_val.get(s[i], 0) > rom_val.get(s[i - 1], 0):
            int_val += rom_val.get(s[i], 0) - 2 * rom_val.get(s[i - 1], 0)
        else:
            int_val += rom_val.get(s[i], 0)
            
    return int_val

# Comprehensive Mapping from Abbr -> Full Name (Key in JSON)
# IMPORTANT: Keys in kjv_fast_lookup.json are predominantly standard USFM (e.g., "PSA", "ISA", "1SA")
# unless build_bible_index.py successfully mapped them.
# The USFM_TO_FULL map in build script was incomplete (missing OT), so most OT books are stored as "ISA", "PSA", etc.
# NT books like MATTHEW are likely full names if they were in the map.

BOOK_MAP = {
    # OLD TESTAMENT (Mostly USFM codes because build script map was partial)
    "gen": "GENESIS", "exod": "EXODUS", "lev": "LEVITICUS", "num": "NUMBERS", "deut": "DEUTERONOMY",
    "josh": "JOSH", "judg": "JUDG", "ruth": "RUTH",
    "1 sam": "1SA", "2 sam": "2SA", "sam": "1SA", 
    "1 kgs": "1KI", "2 kgs": "2KI", "kgs": "1KI",
    "1 chr": "1CH", "2 chr": "2CH", "chr": "1CH",
    "ezra": "EZR", "neh": "NEH", "est": "EST",
    "job": "JOB", "ps": "PSA", "psal": "PSA", "psa": "PSA", "psalm": "PSA", "psalms": "PSA",
    "prov": "PRO", "eccl": "ECC", "cant": "SNG", # USFM for Song of Sol is SNG
    "isa": "ISA", "jer": "JER", "lam": "LAM", "ezek": "EZK", "dan": "DAN",
    "hos": "HOS", "joel": "JOL", "amos": "AMO", "obad": "OBA", "jon": "JON", "mic": "MIC",
    "nah": "NAM", "hab": "HAB", "zeph": "ZEP", "hag": "HAG", "zech": "ZEC", "mal": "MAL",
    
    # NEW TESTAMENT (Mapped to Full Names in build script)
    "matt": "MATTHEW", "mat": "MATTHEW", "mt": "MATTHEW", 
    "mark": "MARK", "mrk": "MARK", "mk": "MARK",
    "luke": "LUKE", "luk": "LUKE", "lk": "LUKE",
    "john": "JOHN", "jhn": "JOHN", "jn": "JOHN",
    "acts": "ACTS", "act": "ACTS",
    "rom": "ROMANS", "rom": "ROMANS",
    "1 cor": "1 CORINTHIANS", "2 cor": "2 CORINTHIANS", "cor": "1 CORINTHIANS",
    "gal": "GALATIANS", "eph": "EPHESIANS", "phil": "PHILIPPIANS", "col": "COLOSSIANS",
    "1 thess": "1 THESSALONIANS", "2 thess": "2 THESSALONIANS", "thess": "1 THESSALONIANS",
    "1 tim": "1 TIMOTHY", "2 tim": "2 TIMOTHY", "tim": "1 TIMOTHY",
    "tit": "TITUS", "phm": "PHILEMON",
    "heb": "HEBREWS", "jas": "JAMES", 
    "1 pet": "1 PETER", "2 pet": "2 PETER", "pet": "1 PETER",
    "1 john": "1 JOHN", "2 john": "2 JOHN", "3 john": "3 JOHN",
    "jude": "JUDE", "rev": "REVELATION"
}

def normalize_reference(ref: str) -> str:
    """
    Smart fuzzy parsing of references like:
    "Psal. xxxiii. 6" -> "PSALMS 33:6"
    "2 Cor. iv. 6" -> "2 CORINTHIANS 4:6"
    """
    # 1. Clean up chars
    # Replace periods with spaces, remove excess usage
    clean = ref.replace('.', ' ').replace(':', ' ').strip()
    # Normalize whitespace
    clean = re.sub(r'\s+', ' ', clean)
    
    parts = clean.split()
    if len(parts) < 2: return ref
    
    # Parse parts from right to left: [Verse] [Chapter] [Book...]
    # Case: "2 Cor 4 6" -> Verse=6, Chap=4, Book="2 Cor"
    # Case: "John 3 16" -> Verse=16, Chap=3, Book="John"
    # Case: "Judges 4" -> Verse?, Chap=4? No, assume Ref is always Chap:Verse. 
    # If standard Gill ref, it is always Book Chap Verse.
    
    verse_part = parts[-1]
    chapter_part = parts[-2]
    book_parts = parts[:-2]
    
    # Reassemble book key
    book_key = " ".join(book_parts).lower()
    
    # 1. Normalize Book
    book_norm = BOOK_MAP.get(book_key, book_key.upper())
    
    # 2. Normalize Chapter (Roman)
    chapter_num = roman_to_int(chapter_part) if not chapter_part.isdigit() else int(chapter_part)
    
    # 3. Normalize Verse
    verse_num = int(verse_part) if verse_part.isdigit() else verse_part
    
    return f"{book_norm} {chapter_num}:{verse_num}"

@router.get("/api/verse/{ref}")
def get_verse_text(ref: str):
    """
    Returns verse text.
    First tries strict lookup.
    Then tries normalization.
    """
    # 0. Raw Decode is handled by FastAPI
    ref = ref.strip()
    
    # 1. Direct Lookup (e.g. if frontend sent "GENESIS 1:1")
    if ref in BIBLE_MAP:
        return {"ref": ref, "text": BIBLE_MAP[ref]}
        
    # 2. Normalize
    try:
        norm_ref = normalize_reference(ref)
        if norm_ref in BIBLE_MAP:
            return {"ref": norm_ref, "text": BIBLE_MAP[norm_ref]}
    except Exception as e:
        print(f"Verse Normalize Error for {ref}: {e}")
        pass
        
    # 3. Fail gracefully
    raise HTTPException(status_code=404, detail=f"Verse not found: {ref} (Normalized: {norm_ref if 'norm_ref' in locals() else 'Failed'})")
