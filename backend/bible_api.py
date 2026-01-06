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

    # 2. Try MinIO (Fallback) - HTTP Fetch via Service/Ingress
    print("Bible API: Local index not found. Attempting download from MinIO...")
    try:
        import requests
        # Default to internal K8s service URL (http://minio:9000)
        # Frontend uses ingress/scans, which maps to minio service.
        # We can simulate this internally by accessing the service directly.
        # Using "scans" bucket name in path.
        minio_base = os.getenv("MINIO_HTTP_ENDPOINT", "http://minio:9000")
        url = f"{minio_base}/scans/kjv_fast_lookup.json"
        
        print(f"Bible API: Downloading from {url}...")
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            BIBLE_MAP = response.json()
            print(f"Bible API: Successfully loaded {len(BIBLE_MAP)} verses from remote.")
            return
        else:
            print(f"Bible API: Failed to download. Status: {response.status_code}")
            
    except Exception as e:
        print(f"Bible API: Remote fetch failed: {e}")

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

# Comprehensive mapping: Common abbreviations -> USFM codes
# USFM codes are the primary keys in kjv_fast_lookup.json (e.g., "JDG 11:4")
# Source: get_md.py usfm_to_book_name

BOOK_MAP = {
    # OLD TESTAMENT
    "gen": "GEN", "genesis": "GEN",
    "exod": "EXO", "exodus": "EXO", "ex": "EXO",
    "lev": "LEV", "leviticus": "LEV",
    "num": "NUM", "numbers": "NUM", "numb": "NUM",
    "deut": "DEU", "deuteronomy": "DEU",
    "josh": "JOS", "joshua": "JOS",
    "judg": "JDG", "judges": "JDG",
    "ruth": "RUT",
    "1 sam": "1SA", "2 sam": "2SA", "sam": "1SA", "1 samuel": "1SA", "2 samuel": "2SA",
    "1 kgs": "1KI", "2 kgs": "2KI", "kgs": "1KI", "1 kings": "1KI", "2 kings": "2KI",
    "1 chr": "1CH", "2 chr": "2CH", "chr": "1CH", "1 chronicles": "1CH", "2 chronicles": "2CH",
    "ezra": "EZR", "ezr": "EZR",
    "neh": "NEH", "nehemiah": "NEH",
    "est": "EST", "esther": "EST",
    "job": "JOB",
    "ps": "PSA", "psal": "PSA", "psa": "PSA", "psalm": "PSA", "psalms": "PSA",
    "prov": "PRO", "proverbs": "PRO",
    "eccl": "ECC", "ecclesiastes": "ECC",
    "cant": "SNG", "song": "SNG", "song of solomon": "SNG",
    "isa": "ISA", "isaiah": "ISA",
    "jer": "JER", "jeremiah": "JER",
    "lam": "LAM", "lamentations": "LAM",
    "ezek": "EZK", "ezekiel": "EZK",
    "dan": "DAN", "daniel": "DAN",
    "hos": "HOS", "hosea": "HOS",
    "joel": "JOL",
    "amos": "AMO",
    "obad": "OBA", "obadiah": "OBA",
    "jon": "JON", "jonah": "JON",
    "mic": "MIC", "micah": "MIC",
    "nah": "NAM", "nahum": "NAM",
    "hab": "HAB", "habakkuk": "HAB",
    "zeph": "ZEP", "zephaniah": "ZEP",
    "hag": "HAG", "haggai": "HAG",
    "zech": "ZEC", "zechariah": "ZEC",
    "mal": "MAL", "malachi": "MAL",
    
    # NEW TESTAMENT
    "matt": "MAT", "mat": "MAT", "mt": "MAT", "matthew": "MAT",
    "mark": "MRK", "mrk": "MRK", "mk": "MRK",
    "luke": "LUK", "luk": "LUK", "lk": "LUK",
    "john": "JHN", "jhn": "JHN", "jn": "JHN",
    "acts": "ACT", "act": "ACT",
    "rom": "ROM", "romans": "ROM",
    "1 cor": "1CO", "2 cor": "2CO", "cor": "1CO", "1 corinthians": "1CO", "2 corinthians": "2CO",
    "gal": "GAL", "galatians": "GAL",
    "eph": "EPH", "ephesians": "EPH",
    "phil": "PHP", "philippians": "PHP",
    "col": "COL", "colossians": "COL",
    "1 thess": "1TH", "2 thess": "2TH", "thess": "1TH", "1 thessalonians": "1TH", "2 thessalonians": "2TH",
    "1 tim": "1TI", "2 tim": "2TI", "tim": "1TI", "1 timothy": "1TI", "2 timothy": "2TI",
    "tit": "TIT", "titus": "TIT",
    "phm": "PHM", "philemon": "PHM",
    "heb": "HEB", "hebrews": "HEB",
    "jas": "JAS", "james": "JAS",
    "1 pet": "1PE", "2 pet": "2PE", "pet": "1PE", "1 peter": "1PE", "2 peter": "2PE",
    "1 john": "1JN", "2 john": "2JN", "3 john": "3JN",
    "jude": "JUD",
    "rev": "REV", "revelation": "REV"
}

def normalize_reference(ref: str) -> list[str]:
    """
    Smart fuzzy parsing of references like:
    "Psal. xxxiii. 6" -> ["PSA 33:6"]
    "2 Cor. iv. 6" -> ["2CO 4:6"]
    "Heb. ii. 14,15." -> ["HEB 2:14", "HEB 2:15"]
    "Joshua iii. 15, 16, 17" -> ["JOS 3:15", "JOS 3:16", "JOS 3:17"]
    """
    # 1. Pre-clean: strip trailing periods
    ref = ref.strip().rstrip('.')
    
    # 2. Compress verse lists: "15, 16" -> "15,16" (remove space after comma if between digits)
    # This prepares the verse part to be a single token for splitting
    clean = re.sub(r'(?<=\d),\s+(?=\d)', ',', ref)
    
    # 3. Replace periods and colons with spaces
    clean = clean.replace('.', ' ').replace(':', ' ')
    
    # 4. Replace remaining ", " with space (likely book separator like "Gen, 1")
    clean = re.sub(r',\s+', ' ', clean)
    
    # 5. Normalize whitespace
    clean = re.sub(r'\s+', ' ', clean).strip()
    
    parts = clean.split()
    if len(parts) < 2: return [ref]
    
    # Parse parts from right to left: [VersePart] [Chapter] [Book...]
    # VersePart might be "14,15" due to step 2
    
    verse_part = parts[-1]
    chapter_part = parts[-2]
    book_parts = parts[:-2]
    
    # Reassemble book key
    book_key = " ".join(book_parts).lower()
    
    # Normalize Book
    book_norm = BOOK_MAP.get(book_key, book_key.upper())
    
    # Normalize Chapter (Roman)
    chapter_num = roman_to_int(chapter_part) if not chapter_part.isdigit() else int(chapter_part)
    
    # Normalize Verses (split by comma)
    verse_nums = verse_part.split(',')
    
    results = []
    for v_str in verse_nums:
        if not v_str: continue
        v_num = int(v_str) if v_str.isdigit() else v_str
        results.append(f"{book_norm} {chapter_num}:{v_num}")
        
    return results

@router.get("/api/verse/{ref}")
def get_verse_text(ref: str):
    """
    Returns verse text.
    First tries strict lookup.
    Then tries normalization (handling ranges).
    """
    # 0. Raw Decode is handled by FastAPI
    ref = ref.strip()
    
    # 1. Direct Lookup (e.g. if frontend sent "GENESIS 1:1" or a specific key)
    if ref in BIBLE_MAP:
        return {"ref": ref, "text": BIBLE_MAP[ref]}
        
    # 2. Normalize (returns list of keys)
    try:
        norm_refs = normalize_reference(ref)
        
        texts = []
        found_any = False
        primary_ref = None
        
        for nr in norm_refs:
            if nr in BIBLE_MAP:
                if primary_ref is None: primary_ref = nr
                texts.append(BIBLE_MAP[nr])
                found_any = True
            # We skip missing verses in the range gracefully
            
        if found_any:
            # Construct a display ref from the first found
            display_ref = primary_ref
            if len(texts) > 1:
                display_ref += "..." 
            
            return {"ref": display_ref, "text": " ".join(texts)}
            
    except Exception as e:
        print(f"Verse Normalize Error for {ref}: {e}")
        pass
        
    # 3. Fail gracefully
    raise HTTPException(status_code=404, detail=f"Verse not found: {ref}")
