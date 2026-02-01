import pytesseract
from PIL import Image
import re
import sys
import json
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
# Configure Tesseract path
# Check for Windows default path, otherwise rely on PATH (Linux/Custom)
windows_tesseract_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
if os.path.exists(windows_tesseract_path):
    pytesseract.pytesseract.tesseract_cmd = windows_tesseract_path

# Determine Bibles directory
# Priority:
# 1. $COMMENTARY_DATA_DIR/../bibles (if env var set)
# 2. Local directory (relative to script)
_env_data_dir = os.getenv("COMMENTARY_DATA_DIR")
if _env_data_dir:
    BIBLES_DIR = Path(_env_data_dir).parent / "bibles"
else:
    BIBLES_DIR = Path(__file__).parent


# Global log file handle
_log_file = None

def log_print(*args, **kwargs):
    """Print to both console and log file if logging is enabled."""
    # Print to console
    print(*args, **kwargs)
    
    # Print to log file if enabled
    if _log_file:
        print(*args, **kwargs, file=_log_file)
        _log_file.flush()  # Ensure it's written immediately

def set_log_file(log_path):
    """Enable logging to a file."""
    global _log_file
    if log_path:
        _log_file = open(log_path, 'w', encoding='utf-8')
        log_print(f"Logging started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log_print(f"Log file: {log_path}")
        log_print("="*80)

def close_log_file():
    """Close the log file if open."""
    global _log_file
    if _log_file:
        log_print("="*80)
        log_print(f"Logging ended at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        _log_file.close()
        _log_file = None

# Import BAML client for Ollama validation
try:
    # Add current directory to path for baml_client import
    script_dir = Path(__file__).parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    
    from baml_client.sync_client import b as baml_client
    from baml_client import types as baml_types
    import baml_py
    BAML_AVAILABLE = True
except ImportError as e:
    BAML_AVAILABLE = False
    log_print(f"Warning: BAML client not available ({e}). Ollama validation will be skipped.")

# Global Bible structure cache
_BIBLE_STRUCTURE = None

# Bible book order (Old Testament + New Testament)
BIBLE_BOOK_ORDER = [
    'GENESIS', 'EXODUS', 'LEVITICUS', 'NUMBERS', 'DEUTERONOMY',
    'JOSHUA', 'JUDGES', 'RUTH', '1 SAMUEL', '2 SAMUEL',
    '1 KINGS', '2 KINGS', '1 CHRONICLES', '2 CHRONICLES',
    'EZRA', 'NEHEMIAH', 'ESTHER', 'JOB', 'PSALMS',
    'PROVERBS', 'ECCLESIASTES', 'SONG OF SOLOMON', 'ISAIAH',
    'JEREMIAH', 'LAMENTATIONS', 'EZEKIEL', 'DANIEL',
    'HOSEA', 'JOEL', 'AMOS', 'OBADIAH', 'JONAH',
    'MICAH', 'NAHUM', 'HABAKKUK', 'ZEPHANIAH', 'HAGGAI',
    'ZECHARIAH', 'MALACHI',
    'MATTHEW', 'MARK', 'LUKE', 'JOHN', 'ACTS',
    'ROMANS', '1 CORINTHIANS', '2 CORINTHIANS', 'GALATIANS',
    'EPHESIANS', 'PHILIPPIANS', 'COLOSSIANS', '1 THESSALONIANS',
    '2 THESSALONIANS', '1 TIMOTHY', '2 TIMOTHY', 'TITUS',
    'PHILEMON', 'HEBREWS', 'JAMES', '1 PETER', '2 PETER',
    '1 JOHN', '2 JOHN', '3 JOHN', 'JUDE', 'REVELATION'
]

def get_next_book(current_book):
    """Get the next book in Bible order."""
    if not current_book:
        return None
    
    current_book_upper = current_book.upper()
    try:
        idx = BIBLE_BOOK_ORDER.index(current_book_upper)
        if idx < len(BIBLE_BOOK_ORDER) - 1:
            return BIBLE_BOOK_ORDER[idx + 1]
    except ValueError:
        pass
    return None

def verse_has_restarted(verse_str):
    """Check if verse has restarted from 1 (returns True for "1", "1-3", "1,2,3", etc.)"""
    if not verse_str:
        return False
    
    verse_str = str(verse_str).strip()
    
    # Check if it starts with 1
    if verse_str == "1":
        return True
    if verse_str.startswith("1-") or verse_str.startswith("1,"):
        return True
    
    return False

BOOK_NAME_TO_USFM = {
    'Genesis': '02-GENhbo.usfm',
    'Exodus': '03-EXOhbo.usfm',
    'Leviticus': '04-LEVhbo.usfm',
    'Numbers': '05-NUMhbo.usfm',
    'Deuteronomy': '06-DEUhbo.usfm',
    'Joshua': '07-JOShbo.usfm',
    'Judges': '08-JDGhbo.usfm',
    'Ruth': '09-RUThbo.usfm',
    '1Samuel': '10-1SAhbo.usfm',
    '1 Samuel': '10-1SAhbo.usfm',
    '2Samuel': '11-2SAhbo.usfm',
    '2 Samuel': '11-2SAhbo.usfm',
    '1Kings': '12-1KIhbo.usfm',
    '1 Kings': '12-1KIhbo.usfm',
    '2Kings': '13-2KIhbo.usfm',
    '2 Kings': '13-2KIhbo.usfm',
    '1Chronicles': '14-1CHhbo.usfm',
    '1 Chronicles': '14-1CHhbo.usfm',
    '2Chronicles': '15-2CHhbo.usfm',
    '2 Chronicles': '15-2CHhbo.usfm',
    'Ezra': '16-EZRhbo.usfm',
    'Nehemiah': '17-NEHhbo.usfm',
    'Esther': '18-ESThbo.usfm',
    'Job': '19-JOBhbo.usfm',
    'Psalms': '20-PSAhbo.usfm',
    'Proverbs': '21-PROhbo.usfm',
    'Ecclesiastes': '22-ECChbo.usfm',
    'SongofSolomon': '23-SNGhbo.usfm',
    'Song of Solomon': '23-SNGhbo.usfm',
    'Isaiah': '24-ISAhbo.usfm',
    'Jeremiah': '25-JERhbo.usfm',
    'Lamentations': '26-LAMhbo.usfm',
    'Ezekiel': '27-EZKhbo.usfm',
    'Daniel': '28-DANhbo.usfm',
    'Hosea': '29-HOShbo.usfm',
    'Joel': '30-JOLhbo.usfm',
    'Amos': '31-AMOhbo.usfm',
    'Obadiah': '32-OBAhbo.usfm',
    'Jonah': '33-JONhbo.usfm',
    'Micah': '34-MIChbo.usfm',
    'Nahum': '35-NAMhbo.usfm',
    'Habakkuk': '36-HABhbo.usfm',
    'Zephaniah': '37-ZEPhbo.usfm',
    'Haggai': '38-HAGhbo.usfm',
    'Zechariah': '39-ZEChbo.usfm',
    'Malachi': '40-MALhbo.usfm',
}

BOOK_NAME_TO_GREEK_USFM = {
    'Matthew': '46-MATgrctr.usfm',
    'St.Matthew': '46-MATgrctr.usfm',
    'St. Matthew': '46-MATgrctr.usfm',
    'StMatthew': '46-MATgrctr.usfm',
    'Mark': '47-MRKgrctr.usfm',
    'St.Mark': '47-MRKgrctr.usfm',
    'St. Mark': '47-MRKgrctr.usfm',
    'StMark': '47-MRKgrctr.usfm',
    'Luke': '48-LUKgrctr.usfm',
    'St.Luke': '48-LUKgrctr.usfm',
    'St. Luke': '48-LUKgrctr.usfm',
    'StLuke': '48-LUKgrctr.usfm',
    'John': '49-JHNgrctr.usfm',
    'St.John': '49-JHNgrctr.usfm',
    'St. John': '49-JHNgrctr.usfm',
    'StJohn': '49-JHNgrctr.usfm',
    'Acts': '50-ACTgrctr.usfm',
    'Romans': '51-ROMgrctr.usfm',
    '1Corinthians': '52-1COgrctr.usfm',
    '1 Corinthians': '52-1COgrctr.usfm',
    '2Corinthians': '53-2COgrctr.usfm',
    '2 Corinthians': '53-2COgrctr.usfm',
    'Galatians': '54-GALgrctr.usfm',
    'Ephesians': '55-EPHgrctr.usfm',
    'Philippians': '56-PHPgrctr.usfm',
    'Colossians': '57-COLgrctr.usfm',
    '1Thessalonians': '58-1THgrctr.usfm',
    '1 Thessalonians': '58-1THgrctr.usfm',
    '2Thessalonians': '59-2THgrctr.usfm',
    '2 Thessalonians': '59-2THgrctr.usfm',
    '1Timothy': '60-1TIgrctr.usfm',
    '1 Timothy': '60-1TIgrctr.usfm',
    '2Timothy': '61-2TIgrctr.usfm',
    '2 Timothy': '61-2TIgrctr.usfm',
    'Titus': '62-TITgrctr.usfm',
    'Philemon': '63-PHMgrctr.usfm',
    'Hebrews': '64-HEBgrctr.usfm',
    'James': '65-JASgrctr.usfm',
    'St.James': '65-JASgrctr.usfm',
    'St. James': '65-JASgrctr.usfm',
    'StJames': '65-JASgrctr.usfm',
    '1Peter': '66-1PEgrctr.usfm',
    '1 Peter': '66-1PEgrctr.usfm',
    '2Peter': '67-2PEgrctr.usfm',
    '2 Peter': '67-2PEgrctr.usfm',
    '1John': '68-1JNgrctr.usfm',
    '1 John': '68-1JNgrctr.usfm',
    '2John': '69-2JNgrctr.usfm',
    '2 John': '69-2JNgrctr.usfm',
    '3John': '70-3JNgrctr.usfm',
    '3 John': '70-3JNgrctr.usfm',
    'Jude': '71-JUDgrctr.usfm',
    'St.Jude': '71-JUDgrctr.usfm',
    'St. Jude': '71-JUDgrctr.usfm',
    'StJude': '71-JUDgrctr.usfm',
    'Revelation': '72-REVgrctr.usfm',
}

# Old Testament books (end at Malachi)
OLD_TESTAMENT_BOOKS = [
    'GENESIS', 'EXODUS', 'LEVITICUS', 'NUMBERS', 'DEUTERONOMY',
    'JOSHUA', 'JUDGES', 'RUTH', '1 SAMUEL', '2 SAMUEL',
    '1 KINGS', '2 KINGS', '1 CHRONICLES', '2 CHRONICLES',
    'EZRA', 'NEHEMIAH', 'ESTHER', 'JOB', 'PSALMS',
    'PROVERBS', 'ECCLESIASTES', 'SONG OF SOLOMON', 'ISAIAH',
    'JEREMIAH', 'LAMENTATIONS', 'EZEKIEL', 'DANIEL',
    'HOSEA', 'JOEL', 'AMOS', 'OBADIAH', 'JONAH',
    'MICAH', 'NAHUM', 'HABAKKUK', 'ZEPHANIAH', 'HAGGAI',
    'ZECHARIAH', 'MALACHI'
]

# New Testament books (start at Matthew)
NEW_TESTAMENT_BOOKS = [
    'MATTHEW', 'MARK', 'LUKE', 'JOHN', 'ACTS',
    'ROMANS', '1 CORINTHIANS', '2 CORINTHIANS', 'GALATIANS',
    'EPHESIANS', 'PHILIPPIANS', 'COLOSSIANS', '1 THESSALONIANS',
    '2 THESSALONIANS', '1 TIMOTHY', '2 TIMOTHY', 'TITUS',
    'PHILEMON', 'HEBREWS', 'JAMES', '1 PETER', '2 PETER',
    '1 JOHN', '2 JOHN', '3 JOHN', 'JUDE', 'REVELATION'
]

def normalize_book_name(book_name):
    """
    Normalize book name by removing common prefixes and cleaning up.
    
    Args:
        book_name: Raw book name from OCR (e.g., "ST. MATTHEW", "St. John", "GENESIS")
    
    Returns:
        Normalized book name in uppercase (e.g., "MATTHEW", "JOHN", "GENESIS")
    """
    if not book_name:
        return None
    
    # Convert to uppercase and strip whitespace
    normalized = book_name.upper().strip()
    
    # Remove "ST." or "ST" prefix (common for New Testament books)
    if normalized.startswith("ST."):
        normalized = normalized[3:].strip()
    elif normalized.startswith("ST "):
        normalized = normalized[2:].strip()
    
    # Remove trailing punctuation
    normalized = normalized.rstrip('.,;:!? ')
    
    # Normalize Roman numerals (I. -> 1, II. -> 2, III. -> 3)
    # Handle "I. CHRONICLES" -> "1 CHRONICLES"
    parts = normalized.split(' ', 1)
    if len(parts) > 1:
        first_word = parts[0].strip('.')
        if first_word == 'I':
            normalized = '1 ' + parts[1]
        elif first_word == 'II':
            normalized = '2 ' + parts[1]
        elif first_word == 'III':
            normalized = '3 ' + parts[1]
    
    return normalized

def is_new_testament(book_name):
    """Check if a book is in the New Testament."""
    if not book_name:
        return False
    normalized = normalize_book_name(book_name)
    return normalized in NEW_TESTAMENT_BOOKS

def is_old_testament(book_name):
    """Check if a book is in the Old Testament."""
    if not book_name:
        return False
    normalized = normalize_book_name(book_name)
    return normalized in OLD_TESTAMENT_BOOKS

def get_usfm_directory():
    """Get the path to the hbo_usfm directory."""
    # Try BIBLES_DIR first
    usfm_dir = BIBLES_DIR / 'hbo_usfm'
    if usfm_dir.exists():
        return usfm_dir
        
    # Fallback to script directory (for backward compatibility if env var not set/valid)
    script_dir = Path(__file__).parent
    usfm_dir = script_dir / 'hbo_usfm'
    return usfm_dir if usfm_dir.exists() else None

def get_greek_usfm_directory(version='grctr'):
    """Get the path to the Greek USFM directory."""
    # Try BIBLES_DIR first
    usfm_dir = BIBLES_DIR / 'grctr_usfm'
    if usfm_dir.exists():
        return usfm_dir
        
    script_dir = Path(__file__).parent
    usfm_dir = script_dir / 'grctr_usfm'
    return usfm_dir if usfm_dir.exists() else None

def get_available_greek_versions():
    """Get list of available Greek USFM versions."""
    greek_dir = get_greek_usfm_directory()
    if not greek_dir or not greek_dir.exists():
        return []
    
    # Check for version-specific directories or extract from filenames
    # Currently only one version (grctr) available
    versions = ['grctr']  # Greek Text Receptus
    return versions

def get_english_usfm_directory():
    """Get the path to the eng-kjv2006_usfm directory."""
    # Try BIBLES_DIR first
    usfm_dir = BIBLES_DIR / 'eng-kjv2006_usfm'
    if usfm_dir.exists():
        return usfm_dir

    script_dir = Path(__file__).parent
    usfm_dir = script_dir / 'eng-kjv2006_usfm'
    return usfm_dir if usfm_dir.exists() else None

def build_bible_structure():
    """
    Build a complete Bible structure from English USFM files.
    Returns a dictionary mapping book names to their chapter/verse structure.
    
    Structure:
    {
        'GENESIS': {
            1: 31,  # Chapter 1 has 31 verses
            2: 25,  # Chapter 2 has 25 verses
            ...
        },
        ...
    }
    """
    global _BIBLE_STRUCTURE
    
    if _BIBLE_STRUCTURE is not None:
        return _BIBLE_STRUCTURE
    
    bible_structure = {}
    eng_usfm_dir = get_english_usfm_directory()
    
    if not eng_usfm_dir:
        log_print("Warning: eng-kjv2006_usfm directory not found")
        return {}
    
    # Mapping from USFM file codes to standard book names
    usfm_to_book_name = {
        'GEN': 'GENESIS', 'EXO': 'EXODUS', 'LEV': 'LEVITICUS', 'NUM': 'NUMBERS', 'DEU': 'DEUTERONOMY',
        'JOS': 'JOSHUA', 'JDG': 'JUDGES', 'RUT': 'RUTH', '1SA': '1 SAMUEL', '2SA': '2 SAMUEL',
        '1KI': '1 KINGS', '2KI': '2 KINGS', '1CH': '1 CHRONICLES', '2CH': '2 CHRONICLES',
        'EZR': 'EZRA', 'NEH': 'NEHEMIAH', 'EST': 'ESTHER', 'JOB': 'JOB', 'PSA': 'PSALMS',
        'PRO': 'PROVERBS', 'ECC': 'ECCLESIASTES', 'SNG': 'SONG OF SOLOMON', 'ISA': 'ISAIAH',
        'JER': 'JEREMIAH', 'LAM': 'LAMENTATIONS', 'EZK': 'EZEKIEL', 'DAN': 'DANIEL',
        'HOS': 'HOSEA', 'JOL': 'JOEL', 'AMO': 'AMOS', 'OBA': 'OBADIAH', 'JON': 'JONAH',
        'MIC': 'MICAH', 'NAM': 'NAHUM', 'HAB': 'HABAKKUK', 'ZEP': 'ZEPHANIAH', 'HAG': 'HAGGAI',
        'ZEC': 'ZECHARIAH', 'MAL': 'MALACHI',
        'MAT': 'MATTHEW', 'MRK': 'MARK', 'LUK': 'LUKE', 'JHN': 'JOHN', 'ACT': 'ACTS',
        'ROM': 'ROMANS', '1CO': '1 CORINTHIANS', '2CO': '2 CORINTHIANS', 'GAL': 'GALATIANS',
        'EPH': 'EPHESIANS', 'PHP': 'PHILIPPIANS', 'COL': 'COLOSSIANS', '1TH': '1 THESSALONIANS',
        '2TH': '2 THESSALONIANS', '1TI': '1 TIMOTHY', '2TI': '2 TIMOTHY', 'TIT': 'TITUS',
        'PHM': 'PHILEMON', 'HEB': 'HEBREWS', 'JAS': 'JAMES', '1PE': '1 PETER', '2PE': '2 PETER',
        '1JN': '1 JOHN', '2JN': '2 JOHN', '3JN': '3 JOHN', 'JUD': 'JUDE', 'REV': 'REVELATION'
    }
    
    # Parse all USFM files
    for usfm_file in eng_usfm_dir.glob('*.usfm'):
        # Extract book code from filename (e.g., "02-GENeng-kjv2006.usfm" -> "GEN")
        filename = usfm_file.stem
        parts = filename.split('-')
        if len(parts) >= 2:
            book_code = parts[1][:3].upper()
            book_name = usfm_to_book_name.get(book_code)
            
            if book_name:
                chapters = {}
                current_chapter = None
                current_verses = set()
                
                try:
                    with open(usfm_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            
                            if line.startswith('\\c '):
                                # Save previous chapter
                                if current_chapter is not None and current_verses:
                                    chapters[current_chapter] = max(current_verses)
                                
                                # Start new chapter
                                current_chapter = int(line[3:].strip())
                                current_verses = set()
                            
                            elif line.startswith('\\v ') and current_chapter is not None:
                                # Extract verse number
                                parts = line[3:].split(None, 1)
                                if parts:
                                    try:
                                        verse_num = int(parts[0])
                                        current_verses.add(verse_num)
                                    except ValueError:
                                        pass
                        
                        # Save last chapter
                        if current_chapter is not None and current_verses:
                            chapters[current_chapter] = max(current_verses)
                    
                    if chapters:
                        bible_structure[book_name] = chapters
                        
                except Exception as e:
                    log_print(f"Warning: Error parsing {usfm_file}: {e}")
    
    _BIBLE_STRUCTURE = bible_structure
    
    if bible_structure:
        log_print(f"\nBible structure loaded: {len(bible_structure)} books indexed for validation")
        log_print(f"Books: {', '.join(sorted(list(bible_structure.keys())[:10]))}...")
    else:
        log_print("\nWarning: Bible structure not loaded - validation will be limited")
    
    return bible_structure

def validate_bible_reference(book_name, chapter, verse):
    """
    Validate if a Bible reference is valid based on the Bible structure.
    
    Args:
        book_name: Book name (string, e.g., "GENESIS")
        chapter: Chapter number (int)
        verse: Verse number, range, or list (string or int), or chapter-spanning notation (e.g., "5:30-32,6:1,2")
    
    Returns:
        dict with keys:
        - 'valid': bool
        - 'errors': list of error messages
        - 'max_chapter': int or None
        - 'max_verse': int or None
    """
    bible = build_bible_structure()
    errors = []
    
    # Normalize book name (strips ST. prefix, etc.)
    book_name_upper = normalize_book_name(book_name) if book_name else None
    
    # Check if book exists
    if not book_name_upper or book_name_upper not in bible:
        valid_books = sorted(bible.keys())
        errors.append(f"Invalid book '{book_name}'. Valid books: {', '.join(valid_books[:5])}...")
        return {'valid': False, 'errors': errors, 'max_chapter': None, 'max_verse': None}
    
    book_data = bible[book_name_upper]
    max_chapter = max(book_data.keys()) if book_data else None
    
    # Check if chapter exists (only if not using chapter-spanning notation)
    verse_str = str(verse) if verse is not None else None
    
    # Check if this is chapter-spanning notation
    if verse_str and ':' in verse_str:
        # Chapter-spanning notation like "5:30-32,6:1,2"
        # Validate each chapter:verse segment
        from verse_notation import parse_verse_notation
        
        try:
            parsed = parse_verse_notation(verse_str)
            if not parsed:
                errors.append(f"Invalid chapter-spanning notation: {verse_str}")
                return {'valid': False, 'errors': errors, 'max_chapter': max_chapter, 'max_verse': None}
            
            # Validate each chapter and its verses
            for span in parsed:
                ch = span['chapter']
                verses = span['verses']
                
                if ch < 1 or ch > max_chapter:
                    errors.append(f"Invalid chapter {ch} in notation {verse_str}. Valid range: 1-{max_chapter}")
                    continue
                
                max_v = book_data.get(ch)
                if max_v is None:
                    errors.append(f"Chapter {ch} not found in {book_name}")
                    continue
                
                invalid_verses = [v for v in verses if v < 1 or v > max_v]
                if invalid_verses:
                    errors.append(f"Invalid verses {invalid_verses} for {book_name} {ch}. Valid range: 1-{max_v}")
            
            # Return validation result for chapter-spanning
            return {'valid': len(errors) == 0, 'errors': errors, 'max_chapter': max_chapter, 'max_verse': None}
            
        except Exception as e:
            errors.append(f"Error parsing chapter-spanning notation '{verse_str}': {e}")
            return {'valid': False, 'errors': errors, 'max_chapter': max_chapter, 'max_verse': None}
    
    # Standard validation for single-chapter notation
    if chapter is not None:
        if chapter < 1 or chapter > max_chapter:
            errors.append(f"Invalid chapter {chapter} for {book_name}. Valid range: 1-{max_chapter}")
            return {'valid': False, 'errors': errors, 'max_chapter': max_chapter, 'max_verse': None}
        
        max_verse = book_data.get(chapter)
        
        # Check verse(s)
        if verse is not None:
            # Parse verse range or list
            if '-' in verse_str:
                # Range like "3-5"
                try:
                    start, end = verse_str.split('-')
                    start_v = int(start.strip())
                    end_v = int(end.strip())
                    
                    if start_v < 1 or end_v > max_verse:
                        errors.append(f"Invalid verse range {verse_str} for {book_name} {chapter}. Valid range: 1-{max_verse}")
                except:
                    errors.append(f"Invalid verse format: {verse_str}")
                    
            elif ',' in verse_str:
                # List like "3,4,5"
                try:
                    verses = [int(v.strip()) for v in verse_str.split(',')]
                    invalid = [v for v in verses if v < 1 or v > max_verse]
                    if invalid:
                        errors.append(f"Invalid verses {invalid} for {book_name} {chapter}. Valid range: 1-{max_verse}")
                except:
                    errors.append(f"Invalid verse format: {verse_str}")
            else:
                # Single verse
                try:
                    v = int(verse_str)
                    if v < 1 or v > max_verse:
                        errors.append(f"Invalid verse {v} for {book_name} {chapter}. Valid range: 1-{max_verse}")
                except:
                    errors.append(f"Invalid verse format: {verse_str}")
        
        return {'valid': len(errors) == 0, 'errors': errors, 'max_chapter': max_chapter, 'max_verse': max_verse}
    
    return {'valid': len(errors) == 0, 'errors': errors, 'max_chapter': max_chapter, 'max_verse': None}

def clean_usfm_text(text):
    """
    Remove USFM markup and Strong's numbers from text, keeping only the actual words.
    
    Args:
        text: Raw USFM text with markup like \\w word|strong="G1234"\\w*
    
    Returns:
        Clean text with only the original language words
    
    Example:
        Input:  "\\w Βίβλος|strong=\"G0976\"\\w* \\w γενέσεως|strong=\"G1078\"\\w*"
        Output: "Βίβλος γενέσεως"
    """
    import re
    
    if not text:
        return text
    
    # Remove footnotes: \f + \fr 2:11 \ft text variant\f*
    # These are textual variant notes that should not appear in the main text
    text = re.sub(r'\\f\s+\+\s+\\fr\s+[^\\]+\\ft\s+[^\\]+\\f\*', '', text)
    
    # Remove \w tags with Strong's numbers: \w word|strong="G####"\w*
    # Pattern: \w followed by word, optional |strong="...", then \w*
    text = re.sub(r'\\w\s+([^|\\]+)\|strong="[^"]+"\s*\\w\*', r'\1', text)
    
    # Remove any remaining \w tags without Strong's numbers
    text = re.sub(r'\\w\s+([^\\]+?)\\w\*', r'\1', text)
    
    # Remove standalone \w and \w* tags
    text = re.sub(r'\\w\*?', '', text)
    
    # Clean up multiple spaces
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

def parse_usfm_file(usfm_path):
    """Parse a USFM file and return a dictionary of chapters and verses."""
    chapters = {}
    current_chapter = None
    
    try:
        with open(usfm_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                if line.startswith('\\c '):
                    current_chapter = int(line[3:].strip())
                    chapters[current_chapter] = {}
                
                elif line.startswith('\\v ') and current_chapter is not None:
                    parts = line[3:].split(None, 1)
                    if len(parts) == 2:
                        verse_num = parts[0]
                        verse_text = parts[1].strip()
                        # Clean USFM markup from verse text
                        verse_text = clean_usfm_text(verse_text)
                        try:
                            chapters[current_chapter][int(verse_num)] = verse_text
                        except ValueError:
                            continue
    except Exception as e:
        log_print(f"Error parsing USFM file {usfm_path}: {e}")
        return {}
    
    return chapters

def get_hebrew_verse_spanning(book_name, verse_notation):
    """
    Extract Hebrew verses from USFM files using chapter-spanning notation.
    
    Args:
        book_name: Name of the book (English)
        verse_notation: Chapter-spanning notation (e.g., "27:42-46,28:1")
    
    Returns:
        Dictionary with verse text organized by chapter:verse keys or None if not found
        Example: {"27:42": "text", "27:43": "text", ..., "28:1": "text"}
    """
    from verse_notation import parse_verse_notation
    
    parsed = parse_verse_notation(verse_notation)
    if not parsed:
        log_print(f"Warning: Could not parse verse notation: {verse_notation}")
        return None
    
    usfm_dir = get_usfm_directory()
    if not usfm_dir:
        log_print("Warning: hbo_usfm directory not found")
        return None
    
    # Normalize book name (strips ST. prefix, etc.)
    book_name_clean = normalize_book_name(book_name)
    book_name_normalized = book_name_clean.replace(' ', '').lower() if book_name_clean else ""
    usfm_filename = None
    for key, value in BOOK_NAME_TO_USFM.items():
        key_normalized = key.replace(' ', '').lower()
        if key_normalized == book_name_normalized:
            usfm_filename = value
            break
    
    if not usfm_filename:
        log_print(f"Warning: Could not find USFM file for book '{book_name}'")
        return None
    
    usfm_path = usfm_dir / usfm_filename
    if not usfm_path.exists():
        log_print(f"Warning: USFM file not found: {usfm_path}")
        return None
    
    chapters_data = parse_usfm_file(usfm_path)
    result = {}
    
    # parsed is a list of dicts: [{'chapter': 27, 'verses': [42,43,44,45,46]}, ...]
    for span in parsed:
        chapter_num = span['chapter']
        verse_list = span['verses']
        
        if chapter_num not in chapters_data:
            log_print(f"Warning: Chapter {chapter_num} not found in {book_name}")
            continue
        
        chapter_verses = chapters_data[chapter_num]
        
        for v in verse_list:
            if v in chapter_verses:
                # Use chapter:verse format as key
                key = f"{chapter_num}:{v}"
                result[key] = chapter_verses[v]
    
    return result if result else None


def get_hebrew_verse(book_name, chapter, verse):
    """
    Extract Hebrew verse(s) from USFM files.
    
    Args:
        book_name: Name of the book (English)
        chapter: Chapter number (int) - may be ignored if verse contains chapter notation
        verse: Verse number or range/list (str or int)
                Examples: 
                - Single chapter: "3", "3-5", "3,4,5"
                - Chapter-spanning: "27:42-46,28:1" (new notation)
    
    Returns:
        Dictionary with verse text or None if not found
    """
    if not book_name or not verse:
        return None
    
    # Check if verse contains chapter-spanning notation (e.g., "27:42-46,28:1")
    verse_str = str(verse)
    if ':' in verse_str:
        log_print(f"DEBUG: Detected chapter-spanning notation: {verse_str}")
        return get_hebrew_verse_spanning(book_name, verse_str)
    
    usfm_dir = get_usfm_directory()
    if not usfm_dir:
        log_print("Warning: hbo_usfm directory not found")
        return None
    
    # Normalize book name (strips ST. prefix, etc.)
    book_name_clean = normalize_book_name(book_name)
    book_name_normalized = book_name_clean.replace(' ', '').lower() if book_name_clean else ""
    usfm_filename = None
    for key, value in BOOK_NAME_TO_USFM.items():
        key_normalized = key.replace(' ', '').lower()
        if key_normalized == book_name_normalized:
            usfm_filename = value
            break
    
    if not usfm_filename:
        log_print(f"Warning: Could not find USFM file for book '{book_name}'")
        return None
    
    usfm_path = usfm_dir / usfm_filename
    if not usfm_path.exists():
        log_print(f"Warning: USFM file not found: {usfm_path}")
        return None
    
    chapters_data = parse_usfm_file(usfm_path)
    
    if chapter not in chapters_data:
        log_print(f"Warning: Chapter {chapter} not found in {book_name}")
        return None
    
    chapter_verses = chapters_data[chapter]
    result = {}
    verse_str = str(verse)
    
    if '-' in verse_str:
        parts = verse_str.split('-')
        if len(parts) == 2:
            try:
                start_verse = int(parts[0])
                end_verse = int(parts[1])
                for v in range(start_verse, end_verse + 1):
                    if v in chapter_verses:
                        result[str(v)] = chapter_verses[v]
            except ValueError:
                pass
    
    elif ',' in verse_str:
        verse_nums = verse_str.split(',')
        for v_str in verse_nums:
            try:
                v = int(v_str.strip())
                if v in chapter_verses:
                    result[str(v)] = chapter_verses[v]
            except ValueError:
                continue
    
    else:
        try:
            v = int(verse_str)
            if v in chapter_verses:
                result[str(v)] = chapter_verses[v]
        except ValueError:
            pass
    
    return result if result else None


def get_greek_verse_spanning(book_name, verse_notation, greek_version='grctr'):
    """
    Extract Greek verses from USFM files using chapter-spanning notation.
    
    Args:
        book_name: Name of the book (English)
        verse_notation: Chapter-spanning notation (e.g., "27:42-46,28:1")
        greek_version: Greek USFM version to use (default: 'grctr')
    
    Returns:
        Dictionary with verse text organized by chapter:verse keys or None if not found
        Example: {"27:42": "text", "27:43": "text", ..., "28:1": "text"}
    """
    from verse_notation import parse_verse_notation
    
    parsed = parse_verse_notation(verse_notation)
    if not parsed:
        log_print(f"Warning: Could not parse verse notation: {verse_notation}")
        return None
    
    usfm_dir = get_greek_usfm_directory(greek_version)
    if not usfm_dir:
        log_print(f"Warning: Greek USFM directory not found for version '{greek_version}'")
        return None
    
    # Normalize book name (strips ST. prefix, etc.)
    book_name_clean = normalize_book_name(book_name)
    book_name_normalized = book_name_clean.replace(' ', '').lower() if book_name_clean else ""
    usfm_filename = None
    for key, value in BOOK_NAME_TO_GREEK_USFM.items():
        key_normalized = key.replace(' ', '').lower()
        if key_normalized == book_name_normalized:
            usfm_filename = value
            break
    
    if not usfm_filename:
        log_print(f"Warning: Could not find Greek USFM file for book '{book_name}'")
        return None
    
    usfm_path = usfm_dir / usfm_filename
    if not usfm_path.exists():
        log_print(f"Warning: Greek USFM file not found: {usfm_path}")
        return None
    
    chapters_data = parse_usfm_file(usfm_path)
    result = {}
    
    for span in parsed:
        chapter_num = span['chapter']
        verse_list = span['verses']
        
        if chapter_num not in chapters_data:
            log_print(f"Warning: Chapter {chapter_num} not found in {book_name}")
            continue
        
        chapter_verses = chapters_data[chapter_num]
        
        for v in verse_list:
            if v in chapter_verses:
                key = f"{chapter_num}:{v}"
                result[key] = chapter_verses[v]
    
    return result if result else None


def get_greek_verse(book_name, chapter, verse, greek_version='grctr'):
    """
    Extract Greek verse(s) from USFM files.
    
    Args:
        book_name: Name of the book (English)
        chapter: Chapter number (int) - may be ignored if verse contains chapter notation
        verse: Verse number or range/list (str or int)
                Examples: 
                - Single chapter: "3", "3-5", "3,4,5"
                - Chapter-spanning: "27:42-46,28:1" (new notation)
        greek_version: Greek USFM version to use (default: 'grctr')
    
    Returns:
        Dictionary with verse text or None if not found
    """
    if not book_name or not verse:
        return None
    
    # Check if verse contains chapter-spanning notation
    verse_str = str(verse)
    if ':' in verse_str:
        log_print(f"DEBUG: Detected chapter-spanning notation for Greek: {verse_str}")
        return get_greek_verse_spanning(book_name, verse_str, greek_version)
    
    usfm_dir = get_greek_usfm_directory(greek_version)
    if not usfm_dir:
        log_print(f"Warning: Greek USFM directory not found for version '{greek_version}'")
        return None
    
    # Normalize book name (strips ST. prefix, etc.)
    book_name_clean = normalize_book_name(book_name)
    book_name_normalized = book_name_clean.replace(' ', '').lower() if book_name_clean else ""
    usfm_filename = None
    for key, value in BOOK_NAME_TO_GREEK_USFM.items():
        key_normalized = key.replace(' ', '').lower()
        if key_normalized == book_name_normalized:
            usfm_filename = value
            break
    
    if not usfm_filename:
        log_print(f"Warning: Could not find Greek USFM file for book '{book_name}'")
        return None
    
    usfm_path = usfm_dir / usfm_filename
    if not usfm_path.exists():
        log_print(f"Warning: Greek USFM file not found: {usfm_path}")
        return None
    
    chapters_data = parse_usfm_file(usfm_path)
    
    if chapter not in chapters_data:
        log_print(f"Warning: Chapter {chapter} not found in {book_name}")
        return None
    
    chapter_verses = chapters_data[chapter]
    result = {}
    verse_str = str(verse)
    
    if '-' in verse_str:
        parts = verse_str.split('-')
        if len(parts) == 2:
            try:
                start_verse = int(parts[0])
                end_verse = int(parts[1])
                for v in range(start_verse, end_verse + 1):
                    if v in chapter_verses:
                        result[str(v)] = chapter_verses[v]
            except ValueError:
                pass
    
    elif ',' in verse_str:
        verse_nums = verse_str.split(',')
        for v_str in verse_nums:
            try:
                v = int(v_str.strip())
                if v in chapter_verses:
                    result[str(v)] = chapter_verses[v]
            except ValueError:
                continue
    
    else:
        try:
            v = int(verse_str)
            if v in chapter_verses:
                result[str(v)] = chapter_verses[v]
        except ValueError:
            pass
    
    return result if result else None


def validate_metadata_with_ollama(image_path, metadata, found_body_verses=None, use_legacy_validation=False):
    """
    Validate OCR metadata using Ollama vision model.
    
    Args:
        image_path: Path to the image file
        metadata: Dictionary with book_name, chapter, verse, page_number
        found_body_verses: Optional list of verses found in the body text (as evidence)
        use_legacy_validation: If True, use the old monolithic prompt.
    
    Returns:
        Validated metadata dictionary or original if validation fails
    """
    if not BAML_AVAILABLE:
        log_print("Skipping Ollama validation (BAML not available)")
        return metadata
    
    try:
        log_print("\nStep 3: Validating metadata with Ollama...")
        
        # Format body verses for prompt
        body_verses_str = None
        if found_body_verses:
            try:
                sorted_v = sorted([int(v) for v in found_body_verses])
                body_verses_str = ", ".join(map(str, sorted_v))
            except:
                body_verses_str = str(found_body_verses)
        
        # Load image for BAML - convert to base64
        import base64
        with open(image_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
        
        # Determine media type from file extension
        ext = os.path.splitext(image_path)[1].lower()
        media_type_map = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp'
        }
        media_type = media_type_map.get(ext, 'image/png')
        
        image = baml_py.Image.from_base64(media_type, image_data)
        
        result = {}
        
        # Call Ollama validation with retry
        max_retries = 2
        for attempt in range(max_retries):
            try:
                if use_legacy_validation:
                    log_print(f"DEBUG: Using LEGACY monolithic validation (Attempt {attempt+1})")
                    # Legacy Monolithic Call
                    baml_metadata = baml_types.Metadata(
                        book_name=metadata.get('book_name'),
                        chapter=metadata.get('chapter'),
                        verse=metadata.get('verse'),
                        page_number=metadata.get('page_number')
                    )
                    
                    validated = baml_client.ValidateOCRMetadata(
                        image=image,
                        ocr_metadata=baml_metadata,
                        body_verses=body_verses_str
                    )
                    
                    book_name = normalize_book_name(validated.book_name) if validated.book_name else None
                    result = {
                        'book_name': book_name,
                        'chapter': validated.chapter,
                        'verse': validated.verse,
                        'page_number': validated.page_number,
                        'is_verse_continuation': getattr(validated, 'no_verse_markers', False) or False
                    }
                else:
                    log_print(f"DEBUG: Using SPLIT validation (Attempt {attempt+1})")
                    
                    # Step 1: Core Metadata (Book, Chapter, Page)
                    log_print("  Step 3a: Validating Core Metadata...")
                    baml_core_metadata = baml_types.MetadataCore(
                        book_name=metadata.get('book_name'),
                        chapter=metadata.get('chapter'),
                        page_number=metadata.get('page_number')
                    )
                    
                    validated_core = baml_client.ValidateMetadataCore(
                        image=image,
                        ocr_metadata=baml_core_metadata
                    )
                    
                    # Step 2: Verse Metadata
                    log_print("  Step 3b: Validating Verse Metadata...")
                    validated_verses = baml_client.ValidateMetadataVerses(
                        image=image,
                        chapter=validated_core.chapter,
                        verse_hint=str(metadata.get('verse', '')),
                        body_verses=body_verses_str
                    )
                    
                    book_name = normalize_book_name(validated_core.book_name) if validated_core.book_name else None
                    result = {
                        'book_name': book_name,
                        'chapter': validated_core.chapter,
                        'verse': validated_verses.verse,
                        'page_number': validated_core.page_number,
                        'is_verse_continuation': getattr(validated_verses, 'no_verse_markers', False) or False
                    }
                
                log_print(f"DEBUG: Extracted is_verse_continuation: {result['is_verse_continuation']}")
                
                # Quality Check: Did we lose significant data?
                is_bad_result = False
                
                # Check for "Total Wipeout" (All None)
                if not any(result.values()):
                    log_print(f"DEBUG: Ollama returned all Nones (Attempt {attempt+1}/{max_retries})")
                    is_bad_result = True
                else:
                    # Check for "Significant Loss"
                    if metadata.get('book_name') and metadata.get('chapter') and not result.get('book_name') and not result.get('chapter'):
                        log_print(f"DEBUG: Ollama dropped Book and Chapter (Attempt {attempt+1}/{max_retries})")
                        is_bad_result = True
                
                if is_bad_result:
                    if attempt < max_retries - 1:
                        log_print("Retrying Ollama validation...")
                        continue
                    else:
                        log_print("Ollama failed to provide valid metadata after retries. Falling back to OCR.")
                        return metadata
                
                # If we get here, result is acceptable
                break
                
            except Exception as e:
                log_print(f"Warning: Ollama attempt {attempt+1} failed: {e}")
                if attempt == max_retries - 1:
                     log_print("Using original OCR metadata")
                     return metadata
        
        # Normalize mixed verse notation if present
        if result.get('verse') and result.get('chapter'):
            normalized_verse = normalize_mixed_verse_notation(result['verse'], result['chapter'])
            if normalized_verse != result['verse']:
                result['verse'] = normalized_verse
        
        # Check if anything changed
        changes = []
        for key in ['book_name', 'chapter', 'verse', 'page_number']:
            old_val = metadata.get(key)
            new_val = result.get(key)
            if old_val != new_val:
                changes.append(f"{key}: {old_val} -> {new_val}")
        
        if changes:
            log_print(f"Ollama corrected metadata:")
            for change in changes:
                log_print(f"  - {change}")
        else:
            log_print("Ollama confirmed metadata is correct")
        
        return result
        
    except Exception as e:
        log_print(f"Warning: Ollama validation failed: {e}")
        log_print("Using original OCR metadata")
        return metadata

def extract_text_with_layout(image_path, lang='eng'):
    """Extract text from image with layout information using pytesseract."""
    img = Image.open(image_path)
    tsv_data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, lang=lang)
    return tsv_data, img.width, img.height

def save_ocr_json(tsv_data, output_path):
    """Save complete OCR data with bounding boxes to JSON file."""
    n_boxes = len(tsv_data['text'])
    ocr_data = []
    for i in range(n_boxes):
        text = tsv_data['text'][i].strip()
        if text:
            ocr_data.append({
                'text': text,
                'left': tsv_data['left'][i],
                'top': tsv_data['top'][i],
                'width': tsv_data['width'][i],
                'height': tsv_data['height'][i],
                'conf': tsv_data['conf'][i],
                'line_num': tsv_data['line_num'][i],
                'word_num': tsv_data['word_num'][i],
                'block_num': tsv_data['block_num'][i],
                'par_num': tsv_data['par_num'][i]
            })
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(ocr_data, f, indent=2, ensure_ascii=False)
    return ocr_data

def roman_to_decimal(roman):
    """Convert a Roman numeral to decimal."""
    roman = roman.upper().strip()
    roman_numerals = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    total = 0
    prev_value = 0
    for char in reversed(roman):
        if char not in roman_numerals:
            return None
        value = roman_numerals[char]
        if value < prev_value:
            total -= value
        else:
            total += value
        prev_value = value
    return total

def correct_ocr_errors(text):
    """Correct common OCR misinterpretations."""
    # Common OCR corrections
    corrections = {
        'LV.': 'IV.',  # L often misread as I
        'LI.': 'II.',  # L often misread as I
        'LII.': 'III.',
        'LIII.': 'IIII.',
        'LIV.': 'IIV.',
        'LX.': 'IX.',
        'LXI.': 'IXI.',
        'T.': 'I.',    # T often misread as I
        'TI.': 'II.',
        'TII.': 'III.',
        'Y.': 'I.',    # Y often misread as I
        'YI.': 'II.',
        'YII.': 'III.',
        'τ': 'I.',     # Greek tau misread as I (multilingual OCR)
        'Τ': 'I.',     # Greek uppercase Tau
        # Add more corrections as needed
    }
    
    corrected = text
    for wrong, right in corrections.items():
        corrected = corrected.replace(wrong, right)
    
    return corrected


def correct_verse_ocr_errors(verse_parts, max_gap=10):
    """
    Correct common OCR errors in verse numbers, particularly '9' misread as '2'.
    Detects when consecutive verse numbers have unrealistic gaps and tries correction.
    
    Note: Only applies correction for VERY large gaps (>25) to avoid false positives.
    Moderate gaps (10-25) may be legitimate sparse verse ranges in commentary.
    
    Args:
        verse_parts: List of verse number strings
        max_gap: Maximum reasonable gap between consecutive verses (default: 10)
    """
    if len(verse_parts) < 2:
        return verse_parts
    
    corrected = []
    for i, part in enumerate(verse_parts):
        if not part.isdigit():
            corrected.append(part)
            continue
        
        current = int(part)
        corrected_part = part
        
        # Check against previous verse
        if i > 0 and corrected[-1].isdigit():
            prev = int(corrected[-1])
            gap = current - prev
            
            # Suspiciously large gap (e.g., 25 -> 96, or 21 -> 99)
            # Only correct for VERY large gaps (>25) to avoid false positives on sparse ranges
            if gap > 25:  # Changed from max_gap (10) to 25 to be more conservative
                # Try replacing '9' with '2' in current verse
                if '9' in part:
                    # Try replacing all 9s first (for cases like "99" -> "22")
                    test_all = part.replace('9', '2')
                    if test_all.isdigit():
                        test_val = int(test_all)
                        test_gap = test_val - prev
                        
                        if 0 < test_gap <= max_gap:
                            log_print(f"DEBUG: OCR correction: verse {part} -> {test_all} (gap {gap} -> {test_gap})")
                            corrected_part = test_all
                        else:
                            # If replacing all doesn't work, try just first '9'
                            test_first = part.replace('9', '2', 1)
                            if test_first.isdigit():
                                test_val = int(test_first)
                                test_gap = test_val - prev
                                
                                if 0 < test_gap <= max_gap:
                                    log_print(f"DEBUG: OCR correction: verse {part} -> {test_first} (gap {gap} -> {test_gap})")
                                    corrected_part = test_first
        
        # Check against next verse
        if i < len(verse_parts) - 1 and verse_parts[i + 1].isdigit():
            next_val = int(verse_parts[i + 1])
            gap = next_val - current
            
            # Large gap to next verse (only for very large gaps)
            if gap > 25:
                # Try replacing '9' with '2' in next verse (will be corrected when we get there)
                pass  # Will be handled when we process the next verse
        
        corrected.append(corrected_part)
    
    return corrected


def combine_verse_list_boxes(boxes, start_index):
    """Combine consecutive boxes that form a verse list like '3,' + '4.' = '3,4'."""
    log_print(f"DEBUG: combine_verse_list_boxes called with start_index={start_index}, len(boxes)={len(boxes)}")
    
    if start_index >= len(boxes):
        log_print(f"DEBUG: start_index >= len(boxes), returning None")
        return None, start_index
    
    verse_parts = []
    current_index = start_index
    
    # Look for patterns like "3,", "4.", "5,", etc.
    while current_index < len(boxes):
        box = boxes[current_index]
        text = box['text'].strip()
        log_print(f"DEBUG:   Checking box {current_index}: '{text}'")
        
        # Check if this looks like part of a verse list
        if re.match(r'^[0-9IVXLCDM]+[,.]?$', text, re.IGNORECASE):
            verse_part = text.replace('.', '').replace(',', '')
            verse_parts.append(verse_part)
            log_print(f"DEBUG:   Matched! Added '{verse_part}' to list")
            current_index += 1
            
            # If this text ends with a period, it's likely the end of the list
            if text.endswith('.'):
                log_print(f"DEBUG:   Text ends with period, stopping")
                break
        else:
            log_print(f"DEBUG:   No match, stopping")
            break
    
    if verse_parts:
        log_print(f"DEBUG: Before OCR correction: {verse_parts}")
        # Apply OCR correction for common '9' -> '2' error
        verse_parts = correct_verse_ocr_errors(verse_parts)
        
        # Join the parts with commas
        combined_verse = ','.join(verse_parts)
        log_print(f"DEBUG: Combined verse list from boxes: {verse_parts} -> {combined_verse}")
        return combined_verse, current_index
    
    log_print(f"DEBUG: No verse parts found, returning None")
    return None, start_index


def parse_verse_text(verse_text):
    """Parse verse text that may contain ranges (10-19) or lists (1,2)."""
    verse_text = verse_text.strip()
    
    # Remove trailing commas and periods first
    verse_text = verse_text.rstrip('.,')
    
    # Replace various dash characters with standard hyphen for easier processing
    # Include multiple dash types and use character codes if needed
    verse_text = verse_text.replace('\u2014', '-')  # Em dash
    verse_text = verse_text.replace('\u2013', '-')  # En dash
    verse_text = verse_text.replace('—', '-')  # Em dash (another encoding)
    verse_text = verse_text.replace('–', '-')  # En dash (another encoding)
    verse_text = verse_text.replace('―', '-')  # Horizontal bar
    verse_text = verse_text.replace('~', '-')  # Tilde (OCR often misreads dashes as tildes)
    
    # Handle ranges like "10-19", "I-V"
    range_patterns = [
        r'^([IVXLCDM0-9]+)-([IVXLCDM0-9]+)$',
        r'^([IVXLCDM0-9]+)\s*-\s*([IVXLCDM0-9]+)$'
    ]
    
    for pattern in range_patterns:
        match = re.match(pattern, verse_text, re.IGNORECASE)
        if match:
            start_verse = match.group(1)
            end_verse = match.group(2)
            
            # Try to parse as Roman numerals first, then as regular numbers
            start_num = roman_to_decimal(start_verse)
            if start_num is None and start_verse.isdigit():
                start_num = int(start_verse)
            
            end_num = roman_to_decimal(end_verse)
            if end_num is None and end_verse.isdigit():
                end_num = int(end_verse)
            
            if start_num and end_num:
                # Check for reversed range (OCR error like "49-46" should be "42-46")
                if start_num > end_num:
                    log_print(f"DEBUG: Detected reversed range {start_num}-{end_num}, attempting OCR correction")
                    # Try replacing 9 with 2 in start number
                    start_str = str(start_num)
                    if '9' in start_str:
                        corrected_start = start_str.replace('9', '2')
                        if corrected_start.isdigit():
                            corrected_start_num = int(corrected_start)
                            if corrected_start_num < end_num:
                                log_print(f"DEBUG: Corrected reversed range: {start_num}-{end_num} -> {corrected_start_num}-{end_num}")
                                start_num = corrected_start_num
                
                # Apply OCR correction to detect common 9→2 errors in ranges
                corrected = correct_verse_ocr_errors([str(start_num), str(end_num)])
                if corrected and len(corrected) == 2:
                    return f"{corrected[0]}-{corrected[1]}"
                return f"{start_num}-{end_num}"
    
    # Handle lists like "1,2", "I,II", "1, 2"
    list_patterns = [
        r'^([IVXLCDM0-9]+)\s*,\s*([IVXLCDM0-9]+)(?:\s*,\s*([IVXLCDM0-9]+))*',
        r'^([IVXLCDM0-9]+),([IVXLCDM0-9]+)(?:,([IVXLCDM0-9]+))*'
    ]
    
    for pattern in list_patterns:
        match = re.match(pattern, verse_text, re.IGNORECASE)
        if match:
            verses = []
            for group in match.groups():
                if group:
                    # Try Roman numeral first, then regular number
                    verse_num = roman_to_decimal(group.strip())
                    if verse_num is None and group.strip().isdigit():
                        verse_num = int(group.strip())
                    if verse_num:
                        verses.append(str(verse_num))
            
            if verses:
                return ",".join(verses)
    
    # Handle single verse (existing logic)
    if re.match(r'^[IVXLCDM]+$', verse_text, re.IGNORECASE):
        verse_num = roman_to_decimal(verse_text)
        if verse_num:
            return str(verse_num)
    elif verse_text.isdigit():
        return verse_text
    
    return None


def extract_multi_chapter_span(boxes, book_name=None):
    """
    Detect chapter-spanning pattern: CH. XXVII. V. 42-46. XXVIII. V. 1
    Returns (first_chapter, verse_notation) or (None, None) if not found.
    
    verse_notation will be in new format: "27:42-46,28:1"
    """
    if not boxes or len(boxes) < 6:  # Need at least CH. ch1 V. v1 ch2 V. v2
        return None, None
    
    sorted_boxes = sorted(boxes, key=lambda b: b['x'])
    
    # Look for pattern: CH. <ch1> V. <v1> <ch2> V. <v2>
    i = 0
    while i < len(sorted_boxes) - 5:
        # Step 1: Find CH. marker
        if not re.match(r'^CH\.?', sorted_boxes[i]['text'], re.IGNORECASE):
            i += 1
            continue
        
        log_print(f"DEBUG: Checking for multi-chapter span starting at box {i}")
        
        # Step 2: Find first chapter number
        ch1 = None
        j = i + 1
        while j < min(i + 3, len(sorted_boxes)):
            text = sorted_boxes[j]['text'].strip()
            if re.match(r'^[IVXLCDM]+\.?$', text, re.IGNORECASE):
                ch1 = roman_to_decimal(text.replace('.', ''))
                if ch1:
                    log_print(f"DEBUG: Found first chapter: {ch1}")
                    break
            j += 1
        
        if not ch1:
            i += 1
            continue
        
        # Step 3: Find first V. marker
        v1_idx = None
        while j < min(i + 5, len(sorted_boxes)):
            if re.match(r'^V\.?$', sorted_boxes[j]['text'], re.IGNORECASE):
                v1_idx = j
                log_print(f"DEBUG: Found first V. marker at {j}")
                break
            j += 1
        
        if v1_idx is None:
            i += 1
            continue
        
        # Step 4: Find first verse(s)
        v1 = None
        j = v1_idx + 1
        while j < min(v1_idx + 3, len(sorted_boxes)):
            text = sorted_boxes[j]['text'].strip()
            v1 = parse_verse_text(text)
            if v1:
                log_print(f"DEBUG: Found first verse(s): {v1}")
                break
            j += 1
        
        if not v1:
            i += 1
            continue
        
        # Step 5: Find second chapter number (no CH. marker, just roman numeral)
        ch2 = None
        ch2_box_idx = None
        j += 1
        while j < min(v1_idx + 5, len(sorted_boxes)):
            text = sorted_boxes[j]['text'].strip()
            if re.match(r'^[IVXLCDM]+\.?$', text, re.IGNORECASE) and not re.match(r'^V\.?$', text, re.IGNORECASE):
                ch2 = roman_to_decimal(text.replace('.', ''))
                if ch2:
                    # Allow same chapter number if OCR error (e.g., XXVII→XXVIII)
                    # Validation will handle sequential correctness
                    log_print(f"DEBUG: Found second chapter: {ch2}" + (f" (same as first, likely OCR error)" if ch2 == ch1 else ""))
                    ch2_box_idx = j
                    break
            j += 1
        
        if not ch2:
            i += 1
            continue
        
        j = ch2_box_idx
        
        # Step 6: Find second V. marker
        v2_idx = None
        while j < min(v1_idx + 7, len(sorted_boxes)):
            if re.match(r'^V\.?$', sorted_boxes[j]['text'], re.IGNORECASE):
                v2_idx = j
                log_print(f"DEBUG: Found second V. marker at {j}")
                break
            j += 1
        
        if v2_idx is None:
            i += 1
            continue
        
        # Step 7: Find second verse(s)
        v2 = None
        j = v2_idx + 1
        while j < min(v2_idx + 3, len(sorted_boxes)):
            text = sorted_boxes[j]['text'].strip()
            v2 = parse_verse_text(text)
            if v2:
                log_print(f"DEBUG: Found second verse(s): {v2}")
                break
            j += 1
        
        if not v2:
            i += 1
            continue
        
        # Success! Build chapter-spanning notation
        # VALIDATION: Check if ch2 is valid
        if book_name and ch2:
            bible = build_bible_structure()
            norm_book = normalize_book_name(book_name)
            if norm_book and norm_book in bible:
                max_ch = max(bible[norm_book].keys())
                
                # Check 1: Exceeds max chapter
                is_invalid = False
                if ch2 > max_ch:
                    log_print(f"DEBUG: Detected chapter {ch2} exceeds max {max_ch} for {book_name}")
                    is_invalid = True
                
                # Check 2: Non-sequential jump (e.g., 21 -> 69)
                # Allow ch1 (same), ch1+1 (next), maybe ch1+2?
                # But 69 is definitely wrong.
                if ch2 > ch1 + 1:
                     log_print(f"DEBUG: Detected suspicious chapter jump {ch1} -> {ch2}")
                     # Only flag as invalid if it's a huge jump (>5) or exceeds max
                     if ch2 > ch1 + 5:
                         is_invalid = True
                
                if is_invalid:
                    # Correction Logic
                    # If v2 is 1 (or small), assume it's the next chapter
                    if ch1 < max_ch:
                        corrected_ch2 = ch1 + 1
                        log_print(f"DEBUG: Correcting invalid/non-sequential chapter {ch2} -> {corrected_ch2}")
                        ch2 = corrected_ch2
                    else:
                        # At end of book?
                        log_print(f"DEBUG: Cannot correct chapter (already at limit)")

        verse_notation = f"{ch1}:{v1},{ch2}:{v2}"
        log_print(f"DEBUG: Multi-chapter span detected: {verse_notation}")
        return ch1, verse_notation
    
    return None, None


def extract_chapter_verse_from_boxes(boxes, book_name=None):
    """Extract chapter and verse from a list of boxes, handling multi-box patterns."""
    if not boxes:
        return None, None
    
    # First, try to detect chapter-spanning pattern
    chapter, verse_notation = extract_multi_chapter_span(boxes, book_name)
    if chapter and verse_notation:
        log_print(f"DEBUG: Using multi-chapter notation: ch={chapter}, verse={verse_notation}")
        return chapter, verse_notation
    
    # Sort boxes by x-position (left to right)
    sorted_boxes = sorted(boxes, key=lambda b: b['x'])
    
    # Apply OCR corrections to all boxes
    corrected_boxes = []
    for box in sorted_boxes:
        corrected_text = correct_ocr_errors(box['text'])
        corrected_box = box.copy()
        corrected_box['text'] = corrected_text
        corrected_boxes.append(corrected_box)
        if corrected_text != box['text']:
            log_print(f"DEBUG: OCR correction: '{box['text']}' -> '{corrected_text}'")
    
    sorted_boxes = corrected_boxes
    
    log_print(f"DEBUG: Searching for chapter/verse in {len(sorted_boxes)} boxes:")
    for i, box in enumerate(sorted_boxes):
        log_print(f"  {i}: '{box['text']}' at x={box['x']}")
    
    # First try single-box patterns
    single_box_patterns = [
        r'CH\.?\s*([IVXLCDM]+)[\s.]*V\.?\s*([IVXLCDM]+)',
        r'Ch\.?\s*([IVXLCDM]+)[\s.]*V\.?\s*([IVXLCDM]+)',
        r'CAP\.?\s*([IVXLCDM]+)[\s.]*V\.?\s*([IVXLCDM]+)',
    ]
    
    for box in sorted_boxes:
        for pattern in single_box_patterns:
            match = re.search(pattern, box['text'], re.IGNORECASE)
            if match:
                chapter = roman_to_decimal(match.group(1))
                verse = roman_to_decimal(match.group(2))
                log_print(f"DEBUG: Single-box pattern found Ch.{chapter} V.{verse} in: '{box['text']}'")
                return chapter, verse
    
    # Try multi-box patterns
    chapter = None
    verse = None
    i = 0
    
    while i < len(sorted_boxes):
        box = sorted_boxes[i]
        text = box['text'].strip()
        
        # Look for chapter marker (with or without appended number)
        ch_match = re.search(r'^CH\.?([IVXLCDM]+)?', text, re.IGNORECASE)
        if ch_match:
            log_print(f"DEBUG: Found chapter marker in '{text}' at position {i}")
            
            # Check if chapter number is appended to marker
            if ch_match.group(1):
                chapter = roman_to_decimal(ch_match.group(1))
                log_print(f"DEBUG: Chapter {chapter} found appended to marker")
            else:
                # Look in next few boxes for chapter number or chapter+verse combination
                for j in range(i + 1, min(i + 4, len(sorted_boxes))):
                    next_box = sorted_boxes[j]
                    next_text = next_box['text'].strip()
                    
                    # Check if it's a chapter+verse combination like "IV." (I + V.)
                    cv_match = re.match(r'^([IVXLCDM]+)V\.?$', next_text, re.IGNORECASE)
                    if cv_match:
                        chapter = roman_to_decimal(cv_match.group(1))
                        if chapter:
                            log_print(f"DEBUG: Chapter {chapter} found in combined box: '{next_text}' (interpreted as {cv_match.group(1)} + V.)")
                            # This box contains both chapter and verse marker
                            # Now we need to look for the verse numbers in the following boxes
                            i = j
                            # Set a flag to indicate we found the verse marker embedded
                            found_embedded_verse_marker = True
                            break
                    # Check if it's just a Roman numeral (chapter only)
                    elif re.match(r'^[IVXLCDM]+\.?$', next_text, re.IGNORECASE):
                        # If it's a verse marker (just "V."), continue to verse search
                        if re.match(r'^V\.?$', next_text, re.IGNORECASE):
                            log_print(f"DEBUG: Found verse marker '{next_text}' without valid chapter number")
                            i = j  # Move to verse marker position
                            break
                        
                        chapter = roman_to_decimal(next_text.replace('.', ''))
                        if chapter:
                            i = j  # Move index to this position
                            log_print(f"DEBUG: Chapter {chapter} found in separate box: '{next_text}'")
                            break
                    # If we hit a verse marker, continue to search for verses (even without chapter)
                    elif re.match(r'^V\.', next_text, re.IGNORECASE):
                        log_print(f"DEBUG: Found verse marker '{next_text}' - chapter unknown, will search for verses")
                        i = j
                        break
            
            # Search for verses if we found a chapter, or if we found chapter/verse markers
            # This allows extracting verses even when chapter number is unknown
            # (validation in Step 4-5 will fill in missing chapter from previous page)
            if True:  # Always search for verses after finding CH. or V. markers
                # Check if we found an embedded verse marker (like "IV." = I + V.)
                # In this case, i points to the box with the embedded marker
                # We need to look for verse numbers starting from the next box
                
                # Now look for verse marker and number
                verse_search_start = i + 1
                
                for k in range(verse_search_start, min(verse_search_start + 4, len(sorted_boxes))):
                    verse_box = sorted_boxes[k]
                    verse_text = verse_box['text'].strip()
                    log_print(f"DEBUG: Checking box {k} for verses: '{verse_text}'")
                    
                    # Check for verse marker with appended number/range/list
                    # Allow for OCR errors like "EV.21" where E is noise before V
                    v_match = re.search(r'[IV]V?\.?(.+)', verse_text, re.IGNORECASE)
                    log_print(f"DEBUG:   Pattern 1 ([IV]V?\\.?(.+)): match={v_match is not None}")
                    if v_match and v_match.start() <= 1:  # V should be near the start (allow 1 char before)
                        verse_part = v_match.group(1)
                        verse = parse_verse_text(verse_part)
                        if verse:
                            log_print(f"DEBUG: Verse {verse} found appended to marker: '{verse_text}'")
                            break
                    
                    # Check for standalone verse marker (including OCR errors like "EV." for "V.")
                    verse_marker_match = re.search(r'[A-Z]?V\.?$', verse_text, re.IGNORECASE)
                    log_print(f"DEBUG:   Pattern 2 ([A-Z]?V\\.?$): match={verse_marker_match is not None}")
                    if verse_marker_match:
                        log_print(f"DEBUG: Found verse marker '{verse_text}' at position {k}")
                        # Try to combine multiple boxes for verse list
                        combined_verse, next_index = combine_verse_list_boxes(sorted_boxes, k + 1)
                        if combined_verse:
                            verse = combined_verse
                            log_print(f"DEBUG: Combined verse list: {verse}")
                            break
                        else:
                            # Look for verse number/range/list in next boxes (fallback)
                            for l in range(k + 1, min(k + 3, len(sorted_boxes))):
                                num_box = sorted_boxes[l]
                                num_text = num_box['text'].strip()
                                log_print(f"DEBUG: Trying to parse verse from: '{num_text}'")
                                
                                verse = parse_verse_text(num_text)
                                if verse:
                                    log_print(f"DEBUG: Verse {verse} found in separate box: '{num_text}'")
                                    break
                                else:
                                    log_print(f"DEBUG: Could not parse verse from: '{num_text}'")
                        break
                    
                    # If no verse marker found, try to parse directly as verse numbers/range
                    # This handles cases like "21—24." or "3,4" in a single box
                    if not v_match and not verse_marker_match:
                        # First try to parse as a complete verse range/list in this box
                        verse = parse_verse_text(verse_text)
                        if verse:
                            log_print(f"DEBUG: Verse {verse} parsed directly from box: '{verse_text}'")
                            break
                        
                        # If that fails, try to combine multiple boxes (like "3,", "4.", "5,")
                        log_print(f"DEBUG: Could not parse '{verse_text}' directly, trying to combine verse list from position {k}")
                        combined_verse, next_index = combine_verse_list_boxes(sorted_boxes, k)
                        if combined_verse:
                            verse = combined_verse
                            log_print(f"DEBUG: Combined verse list without explicit marker: {verse}")
                            break
                
                if chapter and verse:
                    return chapter, verse
        
        i += 1
    
    log_print(f"DEBUG: Multi-box search result: chapter={chapter}, verse={verse}")
    return chapter, verse


def extract_header_info(tsv_data, img_width, img_height):
    """Extract book name, chapter/verse, and page number from header area."""
    n_boxes = len(tsv_data['text'])
    
    # Collect all text boxes
    boxes = []
    for i in range(n_boxes):
        text = tsv_data['text'][i].strip()
        if text:
            boxes.append({
                'text': text,
                'x': tsv_data['left'][i],
                'y': tsv_data['top'][i],
                'width': tsv_data['width'][i],
                'height': tsv_data['height'][i]
            })
    
    if not boxes:
        return {'book_name': None, 'chapter': None, 'verse': None, 'page_number': None}
    
    # Sort by Y position
    boxes.sort(key=lambda b: b['y'])
    min_y = boxes[0]['y']
    
    log_print(f"DEBUG: Minimum Y: {min_y}")
    log_print(f"DEBUG: First 10 boxes:")
    for i, box in enumerate(boxes[:10]):
        log_print(f"  {i}: '{box['text']}' at x={box['x']}, y={box['y']}")
    
    # Get topmost boxes with larger tolerance
    y_tolerance = 50
    topmost_boxes = [b for b in boxes if abs(b['y'] - min_y) <= y_tolerance]
    
    log_print(f"\nDEBUG: Topmost boxes (y ~= {min_y} ± {y_tolerance}):")
    for box in topmost_boxes:
        log_print(f"  '{box['text']}' at x={box['x']}, y={box['y']}")
    
    if not topmost_boxes:
        return {'book_name': None, 'chapter': None, 'verse': None, 'page_number': None}
    
    # Sort by X position
    topmost_boxes.sort(key=lambda b: b['x'])
    
    # Categorize boxes by position (left, center, right thirds)
    left_boundary = img_width / 3
    right_boundary = 2 * img_width / 3
    
    left_boxes = [b for b in topmost_boxes if b['x'] < left_boundary]
    center_boxes = [b for b in topmost_boxes if left_boundary <= b['x'] <= right_boundary]
    right_boxes = [b for b in topmost_boxes if b['x'] > right_boundary]
    
    log_print(f"\nDEBUG: Spatial categorization (img_width={img_width}):")
    log_print(f"  Left boxes ({len(left_boxes)}): {[b['text'] for b in left_boxes]}")
    log_print(f"  Center boxes ({len(center_boxes)}): {[b['text'] for b in center_boxes]}")
    log_print(f"  Right boxes ({len(right_boxes)}): {[b['text'] for b in right_boxes]}")
    
    # Find book name from center boxes
    book_name = None
    if center_boxes:
        # Find the box closest to center
        center_x = img_width / 2
        center_box = min(center_boxes, key=lambda b: abs((b['x'] + b['width']/2) - center_x))
        book_name = center_box['text'].replace('.', '').strip()
        log_print(f"DEBUG: Book name found: '{book_name}'")
    
    # Find page number and determine its side
    page_number = None
    page_side = None
    
    for side, boxes_list in [('left', left_boxes), ('right', right_boxes)]:
        for i, box in enumerate(boxes_list):
            # More selective page number detection - avoid verse patterns
            text = box['text'].strip()
            
            # Skip if it looks like a verse (contains comma or ends with comma/period suggesting list)
            if ',' in text or re.match(r'^[0-9]+[,.]$', text):
                log_print(f"DEBUG: Skipping '{text}' - looks like verse list item")
                continue
            
            # Skip if it's too close to chapter/verse markers
            if any(re.search(r'CH\.|V\.', other_box['text'], re.IGNORECASE)
                   for other_box in boxes_list if abs(other_box['x'] - box['x']) < 200):
                log_print(f"DEBUG: Skipping '{text}' - too close to CH./V. markers")
                continue
            
            # Skip if this number is part of a sequence (e.g., "5" followed by "6." = verse list)
            # Check if there are other numbers nearby that suggest a list
            nearby_numbers = []
            for j, other_box in enumerate(boxes_list):
                if i != j and abs(other_box['x'] - box['x']) < 300:  # Within 300 pixels
                    if re.match(r'^[0-9]+[,.]?$', other_box['text'].strip()):
                        nearby_numbers.append(other_box['text'].strip())
            
            if nearby_numbers:
                log_print(f"DEBUG: Skipping '{text}' - nearby numbers suggest verse list: {nearby_numbers}")
                continue
            
            page_match = re.match(r'^\s*(\d+)\s*$', text)
            if page_match:
                page_number = int(page_match.group(1))
                page_side = side
                log_print(f"DEBUG: Page number {page_number} found on {side} side in: '{box['text']}'")
                break
        if page_number:
            break
    
    # Search for chapter/verse in the opposite area
    chapter = None
    verse = None
    
    # Include center boxes that might contain chapter markers (CH., roman numerals)
    chapter_related_center = [b for b in center_boxes 
                              if re.search(r'CH\.|^[IVXLCDM]+\.?$', b['text'], re.IGNORECASE)
                              and b['text'].strip().upper() != book_name.upper()]
    
    if page_side == 'left':
        cv_boxes = chapter_related_center + right_boxes
        log_print(f"DEBUG: Page number on left, searching for chapter/verse in {len(chapter_related_center)} center boxes + {len(right_boxes)} right boxes")
    elif page_side == 'right':
        cv_boxes = chapter_related_center + left_boxes
        log_print(f"DEBUG: Page number on right, searching for chapter/verse in {len(chapter_related_center)} center boxes + {len(left_boxes)} left boxes")
    else:
        # Fallback: search all boxes
        cv_boxes = center_boxes + left_boxes + right_boxes
        log_print(f"DEBUG: Page number not found, searching all boxes for chapter/verse")
    
    if cv_boxes:
        chapter, verse = extract_chapter_verse_from_boxes(cv_boxes, book_name)
    
    log_print(f"\nDEBUG: Final result: book='{book_name}', ch={chapter}, v={verse}, page={page_number}\n")
    
    return {
        'book_name': book_name,
        'chapter': chapter,
        'verse': verse,
        'page_number': page_number
    }

def group_by_lines(tsv_data):
    """Group words by their line numbers from Tesseract."""
    lines = {}
    n_boxes = len(tsv_data['text'])
    
    for i in range(n_boxes):
        text = tsv_data['text'][i].strip()
        if text:
            line_num = tsv_data['line_num'][i]
            block_num = tsv_data['block_num'][i]
            par_num = tsv_data['par_num'][i]
            line_id = (block_num, par_num, line_num)
            
            word_data = {
                'text': text,
                'x': tsv_data['left'][i],
                'y': tsv_data['top'][i],
                'width': tsv_data['width'][i],
                'height': tsv_data['height'][i]
            }
            
            if line_id not in lines:
                lines[line_id] = []
            lines[line_id].append(word_data)
    
    line_list = []
    for line_id, words in lines.items():
        words.sort(key=lambda w: w['x'])
        avg_y = sum(w['y'] for w in words) / len(words)
        line_list.append({
            'words': words,
            'y': avg_y,
            'height': max(w['height'] for w in words)
        })
    
    line_list.sort(key=lambda l: l['y'])
    return line_list

def merge_lines_by_y_position(line_list, tolerance=0.5):
    """Merge lines that are at the same Y position."""
    if not line_list:
        return []
    
    merged_lines = []
    current_group = [line_list[0]]
    
    for i in range(1, len(line_list)):
        line = line_list[i]
        prev_line = current_group[0]
        y_diff = abs(line['y'] - prev_line['y'])
        avg_height = (line['height'] + prev_line['height']) / 2
        
        if y_diff < avg_height * tolerance:
            current_group.append(line)
        else:
            merged_lines.append(merge_line_group(current_group))
            current_group = [line]
    
    if current_group:
        merged_lines.append(merge_line_group(current_group))
    
    return merged_lines

def merge_line_group(line_group):
    """Merge multiple lines that are on the same visual line."""
    all_words = []
    for line in line_group:
        all_words.extend(line['words'])
    all_words.sort(key=lambda w: w['x'])
    return all_words

def calculate_page_center(lines):
    """Calculate the center divider of the page."""
    if not lines:
        return None
    
    left_edges = []
    right_edges = []
    
    for line in lines:
        if not line:
            continue
        for word in line:
            left_edges.append(word['x'])
            right_edges.append(word['x'] + word['width'])
    
    if not left_edges or not right_edges:
        return None
    
    avg_left = sum(left_edges) / len(left_edges)
    avg_right = sum(right_edges) / len(right_edges)
    center_x = (avg_left + avg_right) / 2
    
    return center_x

def split_line_by_center(line, center_x):
    """Split a line into left and right columns."""
    left_words = []
    right_words = []
    
    for word in line:
        word_center = word['x'] + word['width'] / 2
        if word_center < center_x:
            left_words.append(word)
        else:
            right_words.append(word)
    
    return left_words, right_words

def calculate_avg_char_width(lines):
    """Estimate average character width from word data."""
    total_chars = 0
    total_width = 0
    
    for line in lines:
        for word in line:
            char_count = len(word['text'])
            if char_count > 0:
                total_chars += char_count
                total_width += word['width']
    
    if total_chars > 0:
        return total_width / total_chars
    return 10

def reconstruct_line_with_spacing(line, avg_char_width):
    """Reconstruct a line with proper spacing."""
    if not line:
        return ""
    
    result = []
    prev_x_end = line[0]['x']
    
    for i, word in enumerate(line):
        if i > 0:
            gap = word['x'] - prev_x_end
            num_spaces = max(1, int(gap / avg_char_width))
            result.append(' ' * num_spaces)
        
        result.append(word['text'])
        prev_x_end = word['x'] + word['width']
    
    return ''.join(result)

def find_right_column_start(lines, center_x):
    """Find the consistent starting position for right column text."""
    right_starts = []
    
    for line in lines:
        if not line:
            continue
        for word in line:
            word_center = word['x'] + word['width'] / 2
            if word_center >= center_x:
                right_starts.append(word['x'])
                break
    
    if not right_starts:
        return None
    return sum(right_starts) / len(right_starts)

def calculate_right_col_position(lines, avg_char_width, center_x):
    """Calculate the right column character position."""
    max_left_length = 0
    
    for line in lines:
        if not line:
            continue
        left_words, _ = split_line_by_center(line, center_x)
        if left_words:
            left_text = reconstruct_line_with_spacing(left_words, avg_char_width)
            max_left_length = max(max_left_length, len(left_text))
    
    return max_left_length + 4

def lines_to_paragraphs(lines, avg_char_width, center_x, right_col_start, right_col_char_pos=80):
    """Convert lines to paragraphs with proper spacing and aligned columns."""
    if not lines:
        return []
    
    paragraphs = []
    current_para = []
    prev_line_bottom = 0
    
    for line in lines:
        if not line:
            continue
        
        left_words, right_words = split_line_by_center(line, center_x)
        left_text = reconstruct_line_with_spacing(left_words, avg_char_width) if left_words else ""
        right_text = reconstruct_line_with_spacing(right_words, avg_char_width) if right_words else ""
        
        if right_text:
            left_length = len(left_text)
            padding_needed = max(right_col_char_pos - left_length, 2)
            line_text = left_text + (' ' * padding_needed) + right_text
        else:
            line_text = left_text
        
        line_y = min(word['y'] for word in line)
        line_height = max(word['height'] for word in line)
        
        if prev_line_bottom > 0:
            gap = line_y - prev_line_bottom
            if gap > line_height * 1.5:
                if current_para:
                    paragraphs.append('\n'.join(current_para))
                    current_para = []
        
        current_para.append(line_text)
        prev_line_bottom = line_y + line_height
    
    if current_para:
        paragraphs.append('\n'.join(current_para))
    
    return paragraphs

def format_as_markdown(paragraphs):
    """Format paragraphs as markdown."""
    markdown = []
    for para in paragraphs:
        markdown.append("```")
        markdown.append(para)
        markdown.append("```")
        markdown.append("")
    return '\n'.join(markdown)

def find_verse_markers_in_ocr(ocr_data):
    """
    Find verse markers (Ver. X) in OCR boxes throughout the page.
    Only matches "Ver." (case-sensitive, capital V) at the beginning of lines
    in the left or right columns (not center).
    
    Args:
        ocr_data: Dict with 'text' list and other OCR data
    
    Returns:
        Set of verse numbers found (as integers)
    """
    import re
    
    if 'text' not in ocr_data or 'left' not in ocr_data:
        return set()
    
    verses_found = set()
    verses_ordered = []  # List to preserve order and duplicates
    text_boxes = ocr_data['text']
    
    # Get image width to determine columns
    # Assuming we have left positions, calculate center
    left_positions = ocr_data['left']
    widths = ocr_data.get('width', [])
    if len(left_positions) > 0:
        # Calculate actual page width
        max_x = max(left_positions[i] + (widths[i] if i < len(widths) else 0)
                    for i in range(len(left_positions)) if left_positions[i] is not None)
        center_x = max_x / 2
        
        # Use a minimal margin (0.05%) to only exclude content at the exact center line
        # Commentary pages have right columns starting extremely close to center (within 5-10px)
        # This margin (~1-2 pixels) only excludes truly centered single characters/thin dividers
        center_margin = max_x * 0.0005
    else:
        return set(), []
    
    # Pattern to match "Ver" (case-sensitive!) with optional punctuation, followed by numbers
    # Must be at start of text (after optional whitespace)
    # Matches: "Ver." "Ver," "Ver" "Ver " followed by digits
    verse_pattern = re.compile(r'^\s*Ver[.,\s]*(\d+)')  # No re.IGNORECASE - case sensitive!
    
    # Search each box
    ver_boxes_checked = 0
    ver_boxes_matched = 0
    boxes_skipped_no_text = 0
    boxes_skipped_no_position = 0
    boxes_skipped_center = 0
    
    for i, text in enumerate(text_boxes):
        if not text or text.strip() == '':
            boxes_skipped_no_text += 1
            continue
        
        # Get x position of this box
        x_pos = left_positions[i] if i < len(left_positions) else None
        if x_pos is None:
            boxes_skipped_no_position += 1
            continue
        
        # Skip if box is in center area (we only want left/right columns)
        if abs(x_pos - center_x) < center_margin:
            # Check if this center box contains "Ver" (we might be excluding too much)
            if "Ver" in text or "ver" in text.lower():
                log_print(f"DEBUG: SKIPPED center box {i}: '{text}' at x={x_pos} (center={center_x}, margin={center_margin})")
            boxes_skipped_center += 1
            continue
        
        # Check ALL boxes for "Ver" (case-insensitive) to see what we're finding
        if "ver" in text.lower():
            ver_boxes_checked += 1
            log_print(f"DEBUG: Found 'Ver' in box {i}: '{text}' at x={x_pos}")
        
        # Check if text starts with "Ver." (case-sensitive)
        match = verse_pattern.match(text)
        if match:
            ver_boxes_matched += 1
            try:
                verse_num = int(match.group(1))
                verses_found.add(verse_num)
                verses_ordered.append(verse_num)
                column = "left" if x_pos < center_x else "right"
                log_print(f"DEBUG: Found verse marker 'Ver. {verse_num}' in {column} column, OCR box {i}: '{text[:50]}'")
            except ValueError:
                pass
        
        # Also check if current box starts with "Ver" and next box starts with a number
        # This handles the case where the pattern spans boxes
        if i < len(text_boxes) - 1:
            # Match "Ver.", "Ver,", "Ver" with optional trailing punctuation/space
            if re.match(r'^\s*Ver[.,\s]*$', text):  # Box contains just "Ver" with optional punctuation
                next_text = text_boxes[i + 1]
                next_x = left_positions[i + 1] if i + 1 < len(left_positions) else None
                
                # Check if next box is in the same column (not center) AND same side as Ver.
                if next_text and next_x is not None and abs(next_x - center_x) >= center_margin:
                    # Verify next box is in SAME column as 'Ver.' box
                    # BUT: Allow spanning if both boxes are close to center (within 150px)
                    # This handles cases where "Ver." is at column edge and number spans to next column
                    ver_distance_from_center = abs(x_pos - center_x)
                    next_distance_from_center = abs(next_x - center_x)
                    
                    if ver_distance_from_center < 150 or next_distance_from_center < 150:
                        # At least one box is close to center - allow spanning
                        pass
                    else:
                        # Both boxes far from center - must be same column
                        ver_is_left = x_pos < center_x
                        next_is_left = next_x < center_x
                        if ver_is_left != next_is_left:
                            # Different columns - skip this match
                            continue
                    # More flexible pattern - strip trailing periods and parse
                    next_clean = next_text.strip().rstrip('.,')
                    
                    # Apply OCR corrections for common verse number misreads
                    # "1" often misread as "t", "l", "I", "|"
                    if next_clean.lower().startswith('t') or next_clean.lower().startswith('l') or next_clean.startswith('I') or next_clean.startswith('|'):
                        # Try replacing first char with '1'
                        corrected = '1' + next_clean[1:]
                        match = re.match(r'^(\d+)', corrected)
                        if match:
                            log_print(f"DEBUG: OCR correction for verse number: '{next_clean}' -> '{corrected}'")
                            next_clean = corrected
                    
                    match = re.match(r'^(\d+)', next_clean)
                    if match:
                        try:
                            verse_num = int(match.group(1))
                            verses_found.add(verse_num)
                            verses_ordered.append(verse_num)
                            column = "left" if x_pos < center_x else "right"
                            log_print(f"DEBUG: Found verse marker 'Ver. {verse_num}' spanning boxes {i}-{i+1} in {column} column")
                        except ValueError:
                            pass
    
    # Apply OCR correction to found verses (9 -> 2 error)
    corrected_verses = set()
    verse_list = sorted(verses_found)
    verse_strs = correct_verse_ocr_errors([str(v) for v in verse_list])
    for v_str in verse_strs:
        if v_str.isdigit():
            corrected_verses.add(int(v_str))
    
    log_print(f"DEBUG: Searched {len(text_boxes)} boxes:")
    log_print(f"  - Skipped {boxes_skipped_no_text} (no text)")
    log_print(f"  - Skipped {boxes_skipped_no_position} (no position)")
    log_print(f"  - Skipped {boxes_skipped_center} (center area)")
    log_print(f"  - Found {ver_boxes_checked} boxes containing 'Ver'")
    log_print(f"  - Matched {ver_boxes_matched} verse patterns")
    
    if corrected_verses != verses_found:
        log_print(f"DEBUG: Applied OCR corrections to verse markers: {sorted(verses_found)} -> {sorted(corrected_verses)}")
        verses_found = corrected_verses
    
    # NEW: Spatial Consistency Check
    # Filter out verses that are spatially out of order (e.g. 1 -> 9 -> 3 in the same column)
    # verses_ordered preserves the physical reading order (top-down, left-right)
    # We look for local spikes that violate the monotonic increase of verses
    if len(verses_ordered) >= 3:
        spatially_invalid = set()
        for i in range(1, len(verses_ordered) - 1):
            prev = verses_ordered[i-1]
            curr = verses_ordered[i]
            next_v = verses_ordered[i+1]
            
            # Check for pattern: Low -> High -> Low (Spike)
            # e.g. 1 -> 9 -> 3
            # We assume verses generally increase. Decreases usually mean chapter change (High -> 1) or column wrap.
            
            # If current is significantly higher than BOTH neighbors
            if curr > prev and curr > next_v:
                # Calculate jumps
                jump_up = curr - prev
                jump_down = curr - next_v
                
                # If both jumps are "significant" (e.g. > 2), it's likely an OCR error or outlier
                # But allow for chapter resets (e.g. 52 -> 1 is valid, but 1 -> 52 -> 3 is not)
                # Wait, 1 -> 52 -> 3 IS a spike. 
                # What about 52 -> 1 -> 2? (High -> Low -> High). Valid chapter reset.
                # What about 30 -> 31 -> 1? (High -> High -> Low). Valid.
                
                # We specifically look for "High Middle" spike.
                if jump_up > 2 and jump_down > 2:
                    # Also check if prev and next are "close" to each other
                    # e.g. 1 -> 9 -> 3 (1 and 3 are close)
                    if abs(next_v - prev) <= 5:
                         log_print(f"DEBUG: Spatially invalid verse detected: {curr} (between {prev} and {next_v}). Removing.")
                         spatially_invalid.add(curr)
        
        if spatially_invalid:
            verses_found = verses_found - spatially_invalid
            # Clean up verses_ordered too for consistency (though not strictly used below)
            verses_ordered = [v for v in verses_ordered if v not in spatially_invalid]
    
    # Additional check: Correct outliers by inferring the correct verse number
    # Use known OCR error pattern: 2 -> 9 (e.g., 22 -> 29)
    # E.g., [21, 23, 24, 29] -> check if 29 contains '9' -> try 22 -> [21, 22, 23, 24]
    # 
    # IMPORTANT: 
    # 1. Detect chapter transitions to avoid false outlier detection
    # 2. Detect sparse verse ranges (commentary may only mark some verses)
    #    If first and last verses suggest a range, keep intermediate "outliers"
    if len(verses_found) >= 3:
        sorted_verses = sorted(verses_found)
        
        # Detect likely chapter transition (two patterns)
        # Only detect if we have a small number of verses (<=5), suggesting partial page overlap
        has_chapter_transition = False
        
        # Pattern 1: [1, 2, ..., N] or [1, 3, ..., N] where N >> rest (last verses from PREVIOUS chapter)
        # Also handles sparse low verses like [1, 3] with high verses [17, 18]
        if sorted_verses[0] == 1 and len(sorted_verses) >= 2 and len(sorted_verses) <= 15:
            # Separate low verses (≤10) from high verses (>10)
            low_verses = [v for v in sorted_verses if v <= 10]
            high_verses = [v for v in sorted_verses if v > 10]
            
            # If we have both low and high verses with a significant gap
            if low_verses and high_verses:
                gap = min(high_verses) - max(low_verses)
                if gap > 5:  # Significant gap suggests chapter transition
                    has_chapter_transition = True
                    log_print(f"DEBUG: Detected chapter transition (Pattern 1): low verses {low_verses} from new chapter, high verses {high_verses} likely from previous chapter")
        
        # Pattern 2: [N, N+1, ..., 1] where 1 is at end (first verse from NEXT chapter)
        # Check if: sorted list has 1 in it, and the verses AFTER removing 1 are sequential and high
        if not has_chapter_transition and 1 in sorted_verses and len(sorted_verses) >= 2 and len(sorted_verses) <= 15:
            # Remove verse 1 and check if remaining verses are sequential and high
            verses_without_1 = [v for v in sorted_verses if v != 1]
            
            if len(verses_without_1) >= 1 and verses_without_1[0] > 10:
                # Check if verses (without 1) are sequential
                sequential_high = True
                for i in range(len(verses_without_1) - 1):
                    if verses_without_1[i + 1] - verses_without_1[i] != 1:
                        sequential_high = False
                        break
                
                if sequential_high:
                    has_chapter_transition = True
                    log_print(f"DEBUG: Detected chapter transition (Pattern 2): verses {verses_without_1} are sequential and high, verse 1 likely from next chapter")
        
        # Check for sparse verse range pattern
        # If first and last verses are far apart but sequential verses exist in between,
        # this suggests a sparse commentary that only marks some verses in a range
        is_sparse_range = False
        if not has_chapter_transition and len(sorted_verses) >= 3:
            first_v = sorted_verses[0]
            last_v = sorted_verses[-1]
            verse_span = last_v - first_v + 1  # Total verses in range
            actual_count = len(sorted_verses)  # Actual markers found
            
            # If we have < 50% of verses in the range, it's sparse
            # AND the range is reasonable (< 30 verses for commentary)
            if verse_span <= 30 and actual_count < (verse_span * 0.5):
                # Check if there are some sequential verses at the start
                # This confirms it's not just random outliers
                sequential_start = 0
                for j in range(min(3, len(sorted_verses) - 1)):
                    if sorted_verses[j + 1] - sorted_verses[j] == 1:
                        sequential_start += 1
                
                if sequential_start >= 2:  # At least 2-3 sequential verses
                    is_sparse_range = True
                    log_print(f"DEBUG: Detected sparse verse range: {first_v}-{last_v} with {actual_count}/{verse_span} markers ({actual_count/verse_span*100:.0f}%)")
                    log_print(f"DEBUG: Keeping all markers as-is, skipping outlier correction")
        
        corrected = []
        
        for i, v in enumerate(sorted_verses):
            # Check if this verse is an outlier by examining gaps
            if i > 0:
                prev = sorted_verses[i - 1]
                gap_to_prev = v - prev
            else:
                gap_to_prev = 1  # First verse
            
            if i < len(sorted_verses) - 1:
                next_v = sorted_verses[i + 1]
                gap_to_next = next_v - v
            else:
                gap_to_next = 1  # Last verse
            
            # Detect outliers: gap > 2 suggests OCR error
            # BUT: Skip outlier detection if:
            # 1. This looks like a chapter transition
            # 2. This is a sparse verse range (commentary only marks some verses)
            is_outlier = False
            
            # Skip all outlier detection for sparse ranges
            if is_sparse_range:
                is_outlier = False
            # Don't treat boundary verses as outliers if we detected chapter transition
            elif has_chapter_transition:
                # Pattern 1: [1, 2, ..., N] - skip last verse (N from previous chapter)
                # Pattern 2: [N, N+1, ..., 1] - skip last verse (1 from next chapter)
                if i == len(sorted_verses) - 1:
                    is_outlier = False
            elif i > 0 and i < len(sorted_verses) - 1:
                # Middle verse: large gaps on BOTH sides
                if gap_to_prev > 2 and gap_to_next > 2:
                    is_outlier = True
            elif i == len(sorted_verses) - 1 and i > 0:
                # Last verse: large gap from previous
                if gap_to_prev > 2:
                    is_outlier = True
            elif i == 0 and len(sorted_verses) > 1:
                # First verse: large gap to next
                if gap_to_next > 2:
                    is_outlier = True
            
            if is_outlier:
                log_print(f"DEBUG: Outlier detected: {v} (gap_prev={gap_to_prev}, gap_next={gap_to_next})")
                
                # Try OCR correction: replace 9 with 2 and see if it fits the sequence
                v_str = str(v)
                correction_applied = False
                
                if '9' in v_str:
                    # Try replacing 9 with 2 (common OCR error)
                    corrected_str = v_str.replace('9', '2')
                    try:
                        corrected_v = int(corrected_str)
                        log_print(f"DEBUG: Trying 9->2 OCR correction: {v} -> {corrected_v}")
                        
                        # Check if corrected value fits in the sequence (gap fill OR boundary extension)
                        # 1. Check if it fills a gap
                        fits_sequence = False
                        # Wait, v is the outlier. sorted_verses has it.
                        other_verses = sorted([x for x in sorted_verses if x != v])
                        
                        if not other_verses:
                             # If this is the only verse, we can't validate sequence. Assume valid if sensible?
                             # Or just trust OCR correction if it looks like a verse?
                             # For safety, require context.
                             pass
                        else:
                             # Check 1: Fills gap
                             for j in range(len(other_verses) - 1):
                                 if other_verses[j] < corrected_v < other_verses[j+1]:
                                     gap = other_verses[j+1] - other_verses[j]
                                     # Ideally gap should be 2 for a single insertion (28, 30 -> 29)
                                     # But if gap is larger, it still fits better than 98
                                     fits_sequence = True
                                     log_print(f"DEBUG: Corrected value {corrected_v} fills gap between {other_verses[j]} and {other_verses[j+1]}")
                                     break
                            
                             # Check 2: Extends start (29, 30 -> 28)
                             if not fits_sequence:
                                 if abs(corrected_v - other_verses[0]) == 1:
                                     fits_sequence = True
                                     log_print(f"DEBUG: Corrected value {corrected_v} extends sequence start (before {other_verses[0]})")
                                 
                             # Check 3: Extends end (29, 30 -> 31)
                             if not fits_sequence:
                                 if abs(corrected_v - other_verses[-1]) == 1:
                                     fits_sequence = True
                                     log_print(f"DEBUG: Corrected value {corrected_v} extends sequence end (after {other_verses[-1]})")
                        
                        if fits_sequence:
                            # Verify it doesn't duplicate
                            if corrected_v not in other_verses:
                                log_print(f"DEBUG: Replacing outlier {v} with {corrected_v} (9->2 OCR correction)")
                                corrected.append(corrected_v)
                                correction_applied = True
                                break
                    except ValueError:
                        pass
                
                if correction_applied:
                    continue
                
                # If OCR correction didn't work, try to infer from sequence
                # Look for gaps of >1 in the sequence to find missing verse
                if i == len(sorted_verses) - 1 and i > 0:
                    # Last verse is outlier - check for gap before it
                    
                    # Check if gap is too large to just be "next verse"
                    if v - sorted_verses[i-1] > 5:
                         log_print(f"DEBUG: Large gap detected at end ({sorted_verses[i-1]} -> {v}), keeping outlier")
                         corrected.append(v)
                         continue

                    for j in range(len(sorted_verses) - 1):
                        if sorted_verses[j + 1] - sorted_verses[j] > 1:
                            # Found a gap - infer missing verse
                            inferred = sorted_verses[j] + 1
                            log_print(f"DEBUG: Replacing outlier {v} with inferred verse {inferred} (fills gap after {sorted_verses[j]})")
                            corrected.append(inferred)
                            break
                    else:
                        # No gap found, keep it
                        corrected.append(v)
                elif i < len(sorted_verses) - 1 and i > 0:
                    # Middle outlier - infer from neighbors
                    # ONLY infer if the gap is small (OCR error likely). If gap is large, it's a jump.
                    if v - prev > 5:
                         log_print(f"DEBUG: Large gap detected ({prev} -> {v}), keeping outlier (likely sparse/jump)")
                         corrected.append(v)
                    else:
                        inferred = prev + 1
                        log_print(f"DEBUG: Replacing outlier {v} with inferred verse {inferred} (sequential after {prev})")
                        corrected.append(inferred)
                else:
                    # Keep the original
                    corrected.append(v)
            else:
                corrected.append(v)
        
        if corrected != sorted_verses:
            verses_found = set(corrected)
            log_print(f"DEBUG: After correcting outliers: {sorted(verses_found)}")
            
            # Propagate corrections to verses_ordered
            # Just create a map of original -> corrected
            correction_map = {}
            for orig, corr in zip(sorted_verses, corrected):
                if orig != corr:
                    correction_map[orig] = corr
            
            if correction_map:
                new_ordered = []
                for v in verses_ordered:
                    new_ordered.append(correction_map.get(v, v))
                verses_ordered = new_ordered

    return verses_found, verses_ordered


def reconstruct_multi_chapter_verses(verses_ordered, prev_ch, current_ch=None, prev_book=None, prev_last_v=None):
    """
    Reconstructs chapter-spanning verse notation from an ordered list of verses,
    detecting duplicate resets (e.g., 1, 2, 8, 1, 2, 3 -> Ch X:1-8, Ch Y:1-3)
    AND interleaved verses (e.g., 52, 1, 2, 53, 54 -> Ch 1:52, Ch 2:1-2, Ch 1:53-54).
    
    Args:
        verses_ordered: List of ints in order of appearance (e.g., [6, 7, 8, 1, 1, 8])
        prev_ch: The chapter number of the previous page (base context)
        current_ch: Optional current chapter from header (if reliable)
        prev_last_v: The last verse number from the previous page (to detect resets)
    
    Returns:
        String (e.g., "36:6-8,37:1-8,38:1-8") or None if no complex structure detected.
    """
    if not verses_ordered or len(verses_ordered) < 2:
        return None
        
    # Detect Resets and Interleaved Jumps
    segments = []
    current_segment = [verses_ordered[0]]
    
    # Store relationship: segment_index -> parent_segment_index (for interleaved chapters)
    # If segment i maps to j, it means segment i continues the chapter of segment j
    segment_links = {} 
    
    for i in range(1, len(verses_ordered)):
        v = verses_ordered[i]
        prev_v = verses_ordered[i-1]
        
        is_reset = False
        is_jump_back = False
        target_link_idx = None
        
        # 1. Reset Detection (Drop in value)
        if v < prev_v:
            # Drop in value
            if v <= 5: # Restarting at beginning
                 is_reset = True
        elif v == prev_v and v <= 5 and v == 1:
            # Duplicate 1 -> 1.
            is_reset = True
            
        # 2. Interleaved Jump Detection (Jump UP to match previous segment)
        # Ex: Seg 0: [52]. Current Seg: [1, 2]. v: 53.
        # 53 >> 2 (gap > 10). 53 is close to 52 (gap ~ 1).
        if not is_reset and segments:
            # Check against the END of previous segments
            for seg_idx, seg in enumerate(segments):
                last_v_in_seg = seg[-1]
                # If v continues a previous segment (gap ~ 1)
                if abs(v - last_v_in_seg) <= 2:
                    # And v is significantly different from current local context
                    if abs(v - prev_v) > 10:
                        is_jump_back = True
                        target_link_idx = seg_idx
                        break
        
        # 3. Interleaved Continuation (Jump UP to match prev_last_v from previous page)
        # Ex: Page starts Ch 5:1, 2. Then has Ch 4:49. (prev_last_v=34).
        # v=49. prev_v=2. Gap=47.
        # 49 > prev_last_v (34). Gap 15. Plausible continuation.
        if not is_reset and not is_jump_back and prev_last_v:
             if v - prev_v > 15: # Large gap in current sequence
                 # Does it fit continuation of prev page?
                 # Must be greater than prev_last_v (to avoid backtracking dupes)
                 if v > prev_last_v and (v - prev_last_v) < 30:
                     # It aligns with previous page logic, treat as split
                     # We don't link it to a segment idx because prev page is "virtual"
                     is_jump_back = True 
                     # target_link_idx remains None, implying link to "Base Context"
                     
        if is_reset:
            segments.append(current_segment)
            current_segment = [v]
        elif is_jump_back:
            segments.append(current_segment)
            # Record link: The NEW segment (which will be at len(segments)) links to target_link_idx
            if target_link_idx is not None:
                segment_links[len(segments)] = target_link_idx
            current_segment = [v]
        else:
            current_segment.append(v)
    
    segments.append(current_segment)
    
    if len(segments) == 1:
        return None # No resets/jumps found, not a multi-chapter sequence (use standard logic)
        
    # Assign chapters to segments
    start_ch = prev_ch if prev_ch else 1
    
    # Check if first segment resets to 1 (implying new chapter relative to prev_ch)
    # Use prev_last_v to make a better decision
    current_ch_assignment = start_ch
    
    segment_chapters = {}
    seg0_start = segments[0][0]
    
    # Logic: If we start at 1, and previous page ended at a high verse (e.g. > 1), 
    # then we likely moved to next chapter.
    # Ex: Num 4:34 -> Num 5:1.
    if seg0_start == 1 and prev_last_v and prev_last_v > 1:
         current_ch_assignment = start_ch + 1
         log_print(f"DEBUG: reconstruction detected start at 1 after {prev_last_v} -> Start Ch {current_ch_assignment}")
    # Fallback to simple check if prev_last_v not provided
    elif seg0_start == 1 and prev_ch:
         # Ambiguous without prev_last_v, but usually 1 means new chapter if reading sequentially
         pass

    segment_chapters[0] = current_ch_assignment
    
    # Assign rest based on sequence or links
    for i in range(1, len(segments)):
        if i in segment_links:
            # Linked segment - use same chapter as parent
            parent_idx = segment_links[i]
            segment_chapters[i] = segment_chapters.get(parent_idx, start_ch)
        else:
            # Implicitly a detected reset or distinct segment
            
            # Check for Interleaved "Jump Back" to Previous Chapter context
            # Case: We started at Ch 5 (current_ch_assignment > prev_ch).
            # We see a segment starting with '49'. 
            # 49 is likely Ch 4 (prev_ch).
            seg_start = segments[i][0]
            
            # If we seemingly moved forward (start_ch > prev_ch)
            # but this segment looks like it belongs to prev_ch?
            # Heuristic: Segment start is "Large" (> 10) and distinct from current context.
            if current_ch_assignment > prev_ch:
                # We are technically in "Next Chapter" mode (e.g. Ch 5)
                # If we see a large verse that fits "Previous Chapter" context?
                # E.g. 49.
                if seg_start > 15: # Arbitrary "non-start" threshold
                     # Check if it connects to prev_last_v?
                     # prev_last_v=34. seg_start=49. Gap 15. Not close.
                     # But it is certainly NOT Ch 5:49 (if Ch 5 just started).
                     # Assume it falls back to prev_ch.
                     segment_chapters[i] = prev_ch
                     continue

            # Default: Increment chapter from previous segment?
            # Or increment from 'start_ch' + i?
            # If we had [1,2] (Ch 5) -> [49] (Ch 4)
            # Next segment [3] should be Ch 5 (matches Seg 0).
            # Detecting linkage to Seg 0 would be handled by 'segment_links' IF abs(3-2)<=2.
            # So if it IS linked, we already handled it.
            
            # Revised Logic:
            # Check if this "reset" is actually just out-of-order verses in the SAME chapter.
            # Ex: [1, 9] -> [3]. 3 < 9 (reset), but 3 > 1 (start of prev).
            # This implies 3 is just interleaved in the same range.
            
            prev_seg_start = segments[i-1][0]
            if seg_start > prev_seg_start:
                # Likely same chapter, just messy order
                segment_chapters[i] = segment_chapters[i-1]
                log_print(f"DEBUG: reconstruction: Segment {i} start {seg_start} > Prev start {prev_seg_start} -> Treating as SAME chapter {segment_chapters[i]}")
            else:
                 # Likely new chapter (e.g. 1 after 1, or 1 after 16)
                prev_seg_ch = segment_chapters[i-1]
                segment_chapters[i] = prev_seg_ch + 1
                log_print(f"DEBUG: reconstruction: Segment {i} start {seg_start} <= Prev start {prev_seg_start} -> Treating as NEW chapter {segment_chapters[i]}")
            
    
    # Sort and Merge Segments for Logical Sequential Output
    # The physical reading order (Left Col -> Right Col) might have produced interleaved chapters (Ch 1 -> Ch 2 -> Ch 1).
    # We must reorganize this into logical order: Ch 1 (all parts) -> Ch 2 (all parts).
    
    # 1. Flatten all verses into (chapter, verse) tuples
    all_verses_with_ch = []
    for i, seg in enumerate(segments):
        ch = segment_chapters[i]
        for v in seg:
            all_verses_with_ch.append((ch, v))
            
    # 2. Sort by Chapter, then Verse
    all_verses_with_ch.sort(key=lambda x: (x[0], x[1]))
    
    # 3. Re-group into segments by chapter
    if not all_verses_with_ch:
        return None
        
    merged_parts = []
    current_ch = all_verses_with_ch[0][0]
    current_verses = [all_verses_with_ch[0][1]]
    
    for i in range(1, len(all_verses_with_ch)):
        next_ch, next_v = all_verses_with_ch[i]
        
        if next_ch == current_ch:
            # Same chapter, append verse if not duplicate
            if next_v != current_verses[-1]:
                current_verses.append(next_v)
        else:
            # New chapter, flush current
            merged_parts.append((current_ch, current_verses))
            current_ch = next_ch
            current_verses = [next_v]
            
    merged_parts.append((current_ch, current_verses))
    
    # Format Result
    result_parts = []
    for ch, seg_unique in merged_parts:
        if len(seg_unique) == 1:
            v_str = str(seg_unique[0])
        else:
            # Check for sequential
            is_seq = True
            for k in range(len(seg_unique)-1):
                 if seg_unique[k+1] - seg_unique[k] != 1:
                     is_seq = False
                     break
            if is_seq:
                v_str = f"{seg_unique[0]}-{seg_unique[-1]}"
            else:
                 v_str = ",".join(map(str, seg_unique))
        
        result_parts.append(f"{ch}:{v_str}")
        
    return ",".join(result_parts)


def validate_verses_against_content(metadata_verse, found_verses):
    """
    Validate that the verse(s) in metadata appear in the actual content.
    
    Args:
        metadata_verse: Verse from metadata (can be "3", "3-5", "3,4,5", or chapter-spanning "27:42-46,28:1")
        found_verses: Set of verse numbers found in OCR content (without chapter info)
    
    Returns:
        dict with keys:
        - 'valid': bool (True if at least some verses match)
        - 'all_found': bool (True if ALL verses were found)
        - 'missing_verses': list of verses in metadata but not found in content
        - 'confidence': float (0.0 to 1.0, ratio of verses found)
    """
    if not metadata_verse or not found_verses:
        return {'valid': False, 'all_found': False, 'missing_verses': [], 'confidence': 0.0}
    
    # Parse metadata verse into individual verse numbers
    metadata_verse_str = str(metadata_verse).strip()
    expected_verses = set()
    
    try:
        # Check if this is chapter-spanning notation (contains ':')
        if ':' in metadata_verse_str:
            # New format: "27:42-46,28:1"
            # Parse using verse_notation module
            from verse_notation import parse_verse_notation
            
            parsed = parse_verse_notation(metadata_verse_str)
            if parsed:
                # Extract verse numbers from all chapters
                # Note: Verse markers don't have chapter info, so we just collect verse numbers
                for span in parsed:
                    verses = span['verses']
                    expected_verses.update(verses)
                log_print(f"DEBUG: Parsed chapter-spanning notation '{metadata_verse_str}' -> verses {sorted(expected_verses)}")
            else:
                log_print(f"WARNING: Could not parse chapter-spanning notation: {metadata_verse_str}")
                return {'valid': False, 'all_found': False, 'missing_verses': [], 'confidence': 0.0}
        elif '-' in metadata_verse_str:
            # Range like "3-5"
            parts = metadata_verse_str.split('-')
            start = int(parts[0].strip())
            end = int(parts[1].strip())
            expected_verses = set(range(start, end + 1))
        elif ',' in metadata_verse_str:
            # List like "3,4,5"
            expected_verses = {int(v.strip()) for v in metadata_verse_str.split(',')}
        else:
            # Single verse
            expected_verses = {int(metadata_verse_str)}
    except ValueError as e:
        log_print(f"WARNING: Could not parse verse notation '{metadata_verse_str}': {e}")
        return {'valid': False, 'all_found': False, 'missing_verses': [], 'confidence': 0.0}
    
    # Check which expected verses were found
    found_in_content = expected_verses & found_verses
    missing = expected_verses - found_verses
    
    confidence = len(found_in_content) / len(expected_verses) if expected_verses else 0.0
    
    return {
        'valid': len(found_in_content) > 0,  # At least one verse found
        'all_found': len(missing) == 0,      # All verses found
        'missing_verses': sorted(list(missing)),
        'confidence': confidence
    }


def process_image(image_path, output_path=None, lang='eng', right_col_char_pos=None, validate_ollama=False, prev_metadata=None, use_legacy_validation=False):
    """Main function to process image and generate markdown."""
    log_print(f"Processing image: {image_path}")
    log_print(f"Content language: {lang}\n")
    
    if output_path:
        base_name = os.path.splitext(output_path)[0]
    else:
        base_name = os.path.splitext(image_path)[0]
    
    # Step 1: Run OCR with English only to extract metadata
    log_print(f"Step 1: Running OCR with English to extract metadata...")
    tsv_data_eng, img_width, img_height = extract_text_with_layout(image_path, 'eng')
    header_info = extract_header_info(tsv_data_eng, img_width, img_height)
    log_print(f"Initial metadata: book={header_info['book_name']}, ch={header_info['chapter']}, v={header_info['verse']}, page={header_info['page_number']}")
    
    # Save original header verse for later comparison with Ollama
    original_header_verse = header_info.get('verse')
    
    # Step 2: Find verse markers in English OCR to validate and correct verses
    log_print(f"\nStep 2: Searching for verse markers in body to validate verses...")
    found_verses, verses_ordered = find_verse_markers_in_ocr(tsv_data_eng)
    if not found_verses: found_verses = set()
    if not verses_ordered: verses_ordered = []
    
    if found_verses:
        log_print(f"Found {len(found_verses)} verse markers in body: {sorted(found_verses)}")
        
        # Apply OCR correction to detected verses (9 -> 2)
        verse_list = sorted(found_verses)
        corrected_verse_strs = correct_verse_ocr_errors([str(v) for v in verse_list])
        corrected_verses = [int(v) for v in corrected_verse_strs if v.isdigit()]
        
        if corrected_verses != verse_list:
            log_print(f"After OCR correction: {corrected_verses}")
            found_verses = set(corrected_verses)
        
        # Generate verse range/list from body markers
        # Check if this looks like a chapter transition
        sorted_found = sorted(found_verses)
        min_v = min(found_verses)
        max_v = max(found_verses)
        
        # Detect chapter transition patterns
        has_transition = False
        
        # Pattern 1: [1, 2, ..., N] or [1, 3, ..., N] - verses from new chapter + verses from prev
        # Separate low verses (≤10) from high verses (>10)
        if sorted_found[0] == 1 and len(sorted_found) >= 2 and len(sorted_found) <= 5 and max_v > 10:
            low_verses = [v for v in sorted_found if v <= 10]
            high_verses = [v for v in sorted_found if v > 10]
            
            # If we have both low and high verses with a significant gap
            if low_verses and high_verses:
                gap = min(high_verses) - max(low_verses)
                if gap > 5:  # Significant gap suggests chapter transition
                    has_transition = True
                    new_ch_verses = low_verses
                    prev_ch_verses_body = high_verses
        
        # Pattern 2: [N, N+1, ..., 1] - verses from prev chapter + first verse from next
        if not has_transition and 1 in sorted_found and len(sorted_found) >= 2:
            verses_without_1 = [v for v in sorted_found if v != 1]
            if verses_without_1 and verses_without_1[0] > 10:
                # Check if sequential (without verse 1)
                sequential = all(verses_without_1[i + 1] - verses_without_1[i] == 1 
                               for i in range(len(verses_without_1) - 1))
                if sequential:
                    has_transition = True
                    prev_ch_verses = verses_without_1
                    next_ch_verse = 1
        
        # Check for sparse range (same logic as outlier detection)
        is_sparse_range = False
        if not has_transition and len(sorted_found) >= 3:
            verse_span = max_v - min_v + 1
            actual_count = len(sorted_found)
            if verse_span <= 30 and actual_count < (verse_span * 0.5):
                sequential_start = sum(1 for j in range(min(3, len(sorted_found) - 1)) 
                                     if sorted_found[j + 1] - sorted_found[j] == 1)
                if sequential_start >= 2:
                    is_sparse_range = True
        
        # Format verse string based on detection
        if has_transition:
            # Get current chapter from header
            current_ch = header_info.get('chapter')
            if current_ch:
                # Determine which pattern and format accordingly
                if 'prev_ch_verses_body' in locals():
                    # Pattern 1: High numbers (prev/current) + Low numbers (current/next)
                    # We need to decide if header ch is the "High" ones or the "Low" ones.
                    
                    # Heuristic: Check intersection with header verses
                    # If header has specific verses, use them. If not, check "Start vs End" logic.
                    high_is_header = True # Default assumption
                    
                    # 1. Preferred: Check against previous metadata if available (Contextual Continuity)
                    used_prev_meta = False
                    if prev_metadata and prev_metadata.get('chapter') and prev_metadata.get('verse'):
                        try:
                            prev_ch = int(prev_metadata['chapter'])
                            # Parse last verse from prev metadata
                            prev_v_str = str(prev_metadata['verse'])
                            prev_last_v = 0
                            if ',' in prev_v_str:
                                prev_last_v = int(prev_v_str.split(',')[-1])
                            elif '-' in prev_v_str:
                                prev_last_v = int(prev_v_str.split('-')[-1])
                            else:
                                prev_last_v = int(prev_v_str)
                            
                            # Check continuity with High Verses (e.g. Prev=23, High=[24,25])
                            min_high = min(prev_ch_verses_body)
                            if abs(min_high - prev_last_v) <= 5: # Reasonable gap
                                # High verses continue previous chapter
                                # So High Verses = prev_ch. 
                                # If Header == prev_ch, then High = Header -> high_is_header = True
                                # If Header == prev_ch + 1, then High != Header -> high_is_header = False (High is prev ch)
                                
                                if current_ch == prev_ch:
                                    high_is_header = True
                                    used_prev_meta = True
                                    log_print(f"DEBUG: derived high_is_header=True from prev_metadata continuity (Prev Ch {prev_ch} -> High Verses {min_high})")
                                elif current_ch == prev_ch + 1:
                                    high_is_header = False
                                    used_prev_meta = True
                                    log_print(f"DEBUG: derived high_is_header=False from prev_metadata continuity (Prev Ch {prev_ch} -> High Verses {min_high}, Header is Ch {current_ch})")
                        except:
                            pass

                    # 2. Fallback: Header Correlation (if no prev metadata or ambiguous)
                    if not used_prev_meta and header_info.get('verse'):
                        # Check overlap with high verses
                        # Quick parse of header verse string
                        h_verses = set()
                        try:
                            if ',' in str(header_info['verse']):
                                h_verses = {int(v.strip()) for v in str(header_info['verse']).split(',') if v.strip().isdigit()}
                            elif '-' in str(header_info['verse']):
                                # Simple range check
                                parts = str(header_info['verse']).split('-')
                                if len(parts) == 2 and parts[0].strip().isdigit():
                                    h_verses = {int(parts[0].strip())} # Just check start
                            elif str(header_info['verse']).isdigit():
                                h_verses = {int(header_info['verse'])}
                        except:
                            pass
                        
                        # proper set intersection
                        if h_verses:
                            high_match = len(h_verses.intersection(set(prev_ch_verses_body)))
                            low_match = len(h_verses.intersection(set(new_ch_verses)))
                            
                            if high_match > low_match:
                                high_is_header = True
                                log_print(f"DEBUG: Header verses correlate with high verses -> Transition is Ch {current_ch} -> {current_ch + 1}")
                            elif low_match > high_match:
                                high_is_header = False
                                log_print(f"DEBUG: Header verses correlate with low verses -> Transition is Ch {current_ch - 1} -> {current_ch}")
                            else:
                                # Ambiguous or neither. Fallback to default heuristic:
                                # If header says "24,25", and we find 1,2 ... "24,25" is usually the bulk.
                                # Gill headers usually describe the START or BULK.
                                # If High numbers are > 10, they sort of imply they are the main content if they match header.
                                pass

                    if high_is_header:
                        # Header = High Verses (current). Low Verses = Next Chapter.
                        # Ex: Header=Ch2, Body=[24,25] (High), [1,2] (Low). -> 2:24-25, 3:1-2
                        new_verses_str = f"{min(new_ch_verses)}-{max(new_ch_verses)}" if len(new_ch_verses) > 1 else str(new_ch_verses[0])
                        prev_verses_str = f"{min(prev_ch_verses_body)}-{max(prev_ch_verses_body)}" if len(prev_ch_verses_body) > 1 else str(prev_ch_verses_body[0])
                        body_verse = f"{current_ch}:{prev_verses_str},{current_ch + 1}:{new_verses_str}"
                    else:
                        # Original Logic: Header = Low Verses (current). High Verses = Prev Chapter.
                        # Ex: Header=Ch3, Body=[24,25] (High), [1,2] (Low). -> 2:24-25, 3:1-2
                        
                        # Check for Book Transition
                        is_book_transition_page = False
                        if prev_metadata and prev_metadata.get('book_name'):
                            curr_b = header_info.get('book_name') or prev_metadata.get('book_name')
                            if curr_b and curr_b != prev_metadata.get('book_name'):
                                is_book_transition_page = True
                                log_print(f"DEBUG: Book Transition Detected ({prev_metadata.get('book_name')} -> {curr_b}). Ignoring previous book verses in metadata.")
                        
                        new_verses_str = f"{min(new_ch_verses)}-{max(new_ch_verses)}" if len(new_ch_verses) > 1 else str(new_ch_verses[0])
                        
                        if is_book_transition_page:
                            # If book changed, the "High Verses" belong to the PREVIOUS book.
                            # We can't include them in the CURRENT book's metadata.
                            # So just output the new verses.
                            body_verse = f"{current_ch}:{new_verses_str}"
                        else:
                            prev_verses_str = f"{min(prev_ch_verses_body)}-{max(prev_ch_verses_body)}" if len(prev_ch_verses_body) > 1 else str(prev_ch_verses_body[0])
                            body_verse = f"{current_ch - 1}:{prev_verses_str},{current_ch}:{new_verses_str}"
                else:
                    # Pattern 2: prev chapter verses + next chapter first verse
                    # Usually means Header = Current (High numbers), found `1`.
                    prev_verses_str = f"{min(prev_ch_verses)}-{max(prev_ch_verses)}" if len(prev_ch_verses) > 1 else str(prev_ch_verses[0])
                    body_verse = f"{current_ch}:{prev_verses_str},{current_ch + 1}:{next_ch_verse}"
            else:
                # Fallback to simple range if no chapter info
                body_verse = f"{min_v}-{max_v}" if max_v > min_v else str(min_v)
        elif is_sparse_range:
            # Sparse range - use first-last notation even with gaps
            # The markers suggest endpoints, intermediate verses may not be marked
            body_verse = f"{min_v}-{max_v}"
            log_print(f"DEBUG: Sparse range detected in body markers: {min_v}-{max_v} (found {len(sorted_found)} of {max_v - min_v + 1} verses)")
        else:
            # No chapter transition - simple range
            body_verse = f"{min_v}-{max_v}" if max_v > min_v else str(min_v)
        
        if header_info['verse']:
            # Header has verse - validate against body
            verse_validation = validate_verses_against_content(header_info['verse'], found_verses)
            log_print(f"Header verse '{header_info['verse']}' validation: {verse_validation['confidence']:.1%} confidence")
            
            # Only replace header if:
            # 1. Header has obvious error (wrong order like "19-16")
            # 2. Body found MORE verses than header
            # 3. Confidence is very low (< 25%) AND body has complete sequential range
            
            header_verse_str = str(header_info['verse'])
            should_replace = False
            reason = ""
            
            # Check for wrong order (e.g., "19-16")
            if '-' in header_verse_str:
                parts = header_verse_str.split('-')
                try:
                    start, end = int(parts[0]), int(parts[1])
                    if start > end:
                        should_replace = True
                        reason = "wrong order"
                except:
                    pass
            
            # Check if body found MORE verses
            if not should_replace:
                try:
                    if '-' in header_verse_str:
                        parts = header_verse_str.split('-')
                        header_verse_count = int(parts[1]) - int(parts[0]) + 1
                    elif ',' in header_verse_str:
                        header_verse_count = len(header_verse_str.split(','))
                    else:
                        header_verse_count = 1
                    
                    body_verse_count = len(found_verses)
                    
                    if body_verse_count > header_verse_count:
                        should_replace = True
                        reason = f"body has more verses ({body_verse_count} vs {header_verse_count})"
                except:
                    pass
            
            # Check for very low confidence with complete body range
            if not should_replace and verse_validation['confidence'] < 0.25:
                # Body has complete sequential range?
                expected_body_verses = set(range(min_v, max_v + 1))
                if found_verses == expected_body_verses:
                    should_replace = True
                    reason = f"very low confidence ({verse_validation['confidence']:.1%}) and body has complete range"
            
            if should_replace:
                log_print(f"Replacing header verse ({reason}): {header_info['verse']} -> {body_verse}")
                header_info['verse'] = body_verse
            else:
                log_print(f"Keeping header verse '{header_info['verse']}' (confidence: {verse_validation['confidence']:.1%})")
        else:
            # Header has no verse - infer from body
            log_print(f"Header missing verse, inferring from body: {body_verse}")
            header_info['verse'] = body_verse
    else:
        log_print("No verse markers found in body")
        if not header_info['verse']:
            log_print("WARNING: No verse found in header or body")
    
    # Step 3: Validate metadata with Ollama if requested
    if validate_ollama:
        log_print(f"\nStep 3: Validating with Ollama...")
        header_info = validate_metadata_with_ollama(image_path, header_info, found_verses, use_legacy_validation=use_legacy_validation)
        log_print(f"After Ollama: book={header_info['book_name']}, ch={header_info['chapter']}, v={header_info['verse']}, page={header_info['page_number']}")
        
        # Validate Ollama result against body verse markers and Bible structure
        if found_verses and header_info.get('verse'):
            log_print(f"\nValidating Ollama result against body verse markers...")
            verse_validation = validate_verses_against_content(header_info['verse'], found_verses)
            log_print(f"Ollama verse '{header_info['verse']}' validation: {verse_validation['confidence']:.1%} confidence")
            
            # If Ollama result doesn't match body verses well, consider correction
            # BUT: Trust header+Ollama agreement over incomplete body markers
            # AND: For sparse ranges, trust Ollama more if it found the correct endpoints
            should_correct_ollama = False
            
            if verse_validation['confidence'] < 0.75:
                # First priority: Check if Ollama matches original header
                # When both header and Ollama agree, body markers may be incomplete (OCR errors)
                ollama_verse_str = str(header_info.get('verse', ''))
                if original_header_verse and ollama_verse_str == original_header_verse:
                    # Check for "Unreasonably Large Range" (e.g., 1-43 on a single page)
                    # If range > 20 verses and confidence < 20%, do NOT trust it.
                    is_large_range = False
                    try:
                        if '-' in ollama_verse_str and ':' not in ollama_verse_str:
                            parts = ollama_verse_str.split('-')
                            if len(parts) == 2:
                                start, end = int(parts[0]), int(parts[1])
                                if (end - start + 1) > 20:
                                    is_large_range = True
                    except:
                        pass
                    
                    if is_large_range and verse_validation['confidence'] < 0.2:
                        log_print(f"DEBUG: Header/Ollama agree on '{ollama_verse_str}' but range is large (>20) and confidence low ({verse_validation['confidence']:.1%}) - REJECTING trust")
                        should_correct_ollama = True
                    else:
                        log_print(f"DEBUG: Ollama matches original header '{original_header_verse}' - trusting header+Ollama over body markers")
                        should_correct_ollama = False
                # Second priority: Check if Ollama has a range that CONTAINS all sequential body markers
                # This suggests body markers are incomplete (OCR failures), not that Ollama is wrong
                elif '-' in ollama_verse_str and ':' not in ollama_verse_str:
                    try:
                        parts = ollama_verse_str.split('-')
                        if len(parts) == 2:
                            ollama_first = int(parts[0])
                            ollama_last = int(parts[1])
                            sorted_body = sorted(found_verses)
                            
                            # Check if ALL body markers are within Ollama's range
                            all_within_range = all(ollama_first <= v <= ollama_last for v in sorted_body)
                            
                            # Check if body markers are sequential (no gaps)
                            is_sequential = all(sorted_body[i+1] - sorted_body[i] == 1 
                                              for i in range(len(sorted_body) - 1))
                            
                            if all_within_range and is_sequential:
                                # Ollama's range naturally extends the sequential body markers
                                log_print(f"DEBUG: Ollama range {ollama_first}-{ollama_last} contains all sequential body markers {sorted_body} - trusting Ollama (body likely incomplete)")
                                should_correct_ollama = False
                            else:
                                should_correct_ollama = True
                        else:
                            should_correct_ollama = True
                    except:
                        should_correct_ollama = True
                # Third priority: Check if Ollama found a range that matches our sparse range detection
                elif is_sparse_range and '-' in ollama_verse_str:
                    # Parse Ollama's range
                    try:
                        if ':' not in ollama_verse_str:  # Simple range
                            parts = ollama_verse_str.split('-')
                            if len(parts) == 2:
                                ollama_first = int(parts[0])
                                ollama_last = int(parts[1])
                                # If Ollama found same endpoints as body markers, trust it!
                                if ollama_first == min_v and ollama_last == max_v:
                                    log_print(f"DEBUG: Ollama found correct sparse range {min_v}-{max_v}, keeping Ollama result")
                                    should_correct_ollama = False
                                else:
                                    should_correct_ollama = True
                            else:
                                should_correct_ollama = True
                        else:
                            should_correct_ollama = True
                    except:
                        should_correct_ollama = True
                else:
                    should_correct_ollama = True
            
            if should_correct_ollama:
                sorted_found = sorted(found_verses)
                
                # Check if this looks like a chapter transition
                # Use robust reconstruction first if we have ordered verses
                multi_ch_verse = None
                if verses_ordered:
                    base_chapter = 1
                    prev_last_v = None

                    if prev_metadata and prev_metadata.get('chapter'):
                        base_chapter = int(prev_metadata['chapter'])
                        # Check if we should increment chapter based on verse reset
                        # If first found verse is 1, and previous chapter ended at high number (>1),
                        # then this is likely a new chapter.
                        try:
                            prev_v_str = str(prev_metadata.get('verse', ''))
                            prev_last_v = 0
                            if '-' in prev_v_str:
                                prev_last_v = int(prev_v_str.split('-')[-1])
                            elif ',' in prev_v_str: # Handle lists/complex too? rough check
                                prev_last_v = int(prev_v_str.split(',')[-1].split('-')[-1])
                            else:
                                prev_last_v = int(prev_v_str)
                            
                            if verses_ordered[0] == 1 and prev_last_v > 1:
                                log_print(f"DEBUG: Verse reset detected (Prev Ch {base_chapter} ended at {prev_last_v}, New Page starts at 1) -> Will be handled by multi-chapter reconstruction")
                                # Do NOT increment base_chapter here. Let reconstruct function decide.
                                # base_chapter += 1
                        except:
                            pass
                    elif header_info.get('chapter'):
                        base_chapter = int(header_info['chapter'])
                        
                    multi_ch_verse = reconstruct_multi_chapter_verses(
                        verses_ordered, 
                        prev_ch=base_chapter,
                        current_ch=header_info.get('chapter'),
                        prev_last_v=prev_last_v
                    )
                
                if multi_ch_verse:
                    log_print(f"Correcting Ollama result based on multi-chapter analysis:")
                    log_print(f"  {header_info['verse']} -> {multi_ch_verse}")
                    header_info['verse'] = multi_ch_verse
                # (verses start from 1 with high verses mixed in)
                elif sorted_found[0] == 1 and len(sorted_found) >= 2 and sorted_found[-1] > 10:
                    # Chapter transition: high verses (>10) are from previous chapter
                    new_chapter_verses = [v for v in sorted_found if v <= 10]
                    prev_chapter_verses = [v for v in sorted_found if v > 10]
                    
                    # Get chapters from Ollama result if it's chapter-spanning
                    current_verse_str = str(header_info.get('verse', ''))
                    if ':' in current_verse_str and ',' in current_verse_str:
                        # Extract chapters from notation like "23:20-24,24:1-2"
                        try:
                            from verse_notation import parse_verse_notation
                            parsed = parse_verse_notation(current_verse_str)
                            if len(parsed) >= 2:
                                prev_ch = parsed[0]['chapter']
                                current_ch = parsed[-1]['chapter']
                            else:
                                # Fallback to metadata chapter
                                current_ch = header_info.get('chapter')
                                prev_ch = current_ch - 1 if current_ch and current_ch > 1 else None
                        except:
                            # Fallback to metadata chapter
                            current_ch = header_info.get('chapter')
                            prev_ch = current_ch - 1 if current_ch and current_ch > 1 else None
                    else:
                        # Use metadata chapter and assume previous is ch-1
                        current_ch = header_info.get('chapter')
                        prev_ch = current_ch - 1 if current_ch and current_ch > 1 else None
                    
                    if prev_ch and current_ch:
                        # Format: "prev_ch:prev_verses,current_ch:new_verses"
                        if len(new_chapter_verses) == 1:
                            new_verses_str = str(new_chapter_verses[0])
                        else:
                            new_verses_str = f"{min(new_chapter_verses)}-{max(new_chapter_verses)}"
                        
                        if len(prev_chapter_verses) == 1:
                            prev_verses_str = str(prev_chapter_verses[0])
                        else:
                            prev_verses_str = f"{min(prev_chapter_verses)}-{max(prev_chapter_verses)}"
                        
                        corrected_verse = f"{prev_ch}:{prev_verses_str},{current_ch}:{new_verses_str}"
                        log_print(f"Correcting Ollama result based on body verse markers:")
                        log_print(f"  {header_info['verse']} -> {corrected_verse}")
                        header_info['verse'] = corrected_verse
                else:
                    # No chapter transition, use simple range OR sparse list
                    sorted_v = sorted(found_verses)
                    min_v = sorted_v[0]
                    max_v = sorted_v[-1]
                    
                    # Detect if we should use sparse notation (e.g., "17,84-88")
                    # Check for gaps > 5 verses
                    has_large_gaps = False
                    for i in range(len(sorted_v) - 1):
                        if sorted_v[i+1] - sorted_v[i] > 5:
                            has_large_gaps = True
                            break
                    
                    if has_large_gaps:
                        # Construct sparse string
                        parts = []
                        current_part = [sorted_v[0]]
                        for i in range(1, len(sorted_v)):
                            if sorted_v[i] - sorted_v[i-1] > 5:
                                # New part, flush old
                                if len(current_part) == 1:
                                    parts.append(str(current_part[0]))
                                else:
                                    parts.append(f"{current_part[0]}-{current_part[-1]}")
                                current_part = [sorted_v[i]]
                            else:
                                current_part.append(sorted_v[i])
                        # Flush last part
                        if len(current_part) == 1:
                            parts.append(str(current_part[0]))
                        else:
                            parts.append(f"{current_part[0]}-{current_part[-1]}")
                        
                        body_verse = ",".join(parts)
                        log_print(f"DEBUG: Detected sparse range with gaps: {body_verse}")
                    else:
                        # Standard range
                        body_verse = f"{min_v}-{max_v}" if max_v > min_v else str(min_v)
                    log_print(f"Correcting Ollama result based on body verse markers:")
                    log_print(f"  {header_info['verse']} -> {body_verse}")
                    header_info['verse'] = body_verse
    
    # Create basic metadata
    metadata = {
        'book_name': header_info['book_name'],
        'chapter': header_info['chapter'],
        'verse': header_info['verse'],
        'page_number': header_info['page_number'],
        'is_verse_continuation': header_info.get('is_verse_continuation')
    }
    
    # Steps 4-5: Validate against previous metadata and Bible structure
    if prev_metadata:
        log_print("\nStep 4-5: Validating against previous metadata and Bible structure...")
        # Pass found_verses from Step 2 to avoid re-finding them
        metadata = validate_and_correct_metadata(metadata, prev_metadata, tsv_data_eng, found_verses)
    
    # Step 6: Add Hebrew or Greek verses to validated metadata based on book
    book_name = metadata.get('book_name')
    chapter = metadata.get('chapter')
    verse = metadata.get('verse')
    
    hebrew_verses = None
    greek_verses = None
    
    if book_name and chapter and verse:
        if is_old_testament(book_name):
            log_print("\nStep 6: Extracting Hebrew verses from USFM...")
            hebrew_verses = get_hebrew_verse(book_name, chapter, verse)
            if hebrew_verses:
                log_print(f"Found {len(hebrew_verses)} Hebrew verse(s)")
        elif is_new_testament(book_name):
            log_print("\nStep 6: Extracting Greek verses from USFM...")
            # Check for available Greek versions
            available_versions = get_available_greek_versions()
            if not available_versions:
                log_print("Warning: No Greek USFM versions available")
            elif len(available_versions) == 1:
                greek_version = available_versions[0]
                log_print(f"Using Greek version: {greek_version}")
                greek_verses = get_greek_verse(book_name, chapter, verse, greek_version)
                if greek_verses:
                    log_print(f"Found {len(greek_verses)} Greek verse(s)")
            else:
                # Multiple versions available - prompt user
                log_print(f"\nAvailable Greek versions: {', '.join(available_versions)}")
                log_print("Using default version: grctr")
                greek_version = 'grctr'
                greek_verses = get_greek_verse(book_name, chapter, verse, greek_version)
                if greek_verses:
                    log_print(f"Found {len(greek_verses)} Greek verse(s)")
        else:
            log_print(f"\nStep 6: Book '{book_name}' not recognized as OT or NT, skipping original language extraction")
    
    metadata['hebrew_text'] = hebrew_verses
    metadata['greek_text'] = greek_verses
    
    # Step 7: Save final metadata
    log_print(f"DEBUG: Final Metadata Content: {json.dumps(metadata, indent=2, ensure_ascii=False)}")
    json_path = base_name + '_metadata.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    log_print(f"Step 7: Final metadata saved to {os.path.basename(json_path)}")
    
    # Step 8: Run OCR with specified language for full content
    log_print(f"\nStep 8: Running OCR with '{lang}' for full content...")
    tsv_data, img_width, img_height = extract_text_with_layout(image_path, lang)
    
    ocr_json_path = base_name + '_ocr.json'
    save_ocr_json(tsv_data, ocr_json_path)
    log_print(f"OCR data saved to {os.path.basename(ocr_json_path)}")
    
    # Step 9: Generate and save Markdown
    log_print(f"\nStep 9: Generating markdown...")
    line_list = group_by_lines(tsv_data)
    merged_lines = merge_lines_by_y_position(line_list)
    avg_char_width = calculate_avg_char_width(merged_lines)
    center_x = calculate_page_center(merged_lines)
    
    if center_x:
        right_col_start = find_right_column_start(merged_lines, center_x)
        if right_col_char_pos is None:
            right_col_char_pos = calculate_right_col_position(merged_lines, avg_char_width, center_x)
        paragraphs = lines_to_paragraphs(merged_lines, avg_char_width, center_x, right_col_start, right_col_char_pos)
    else:
        paragraphs = []
        for line in merged_lines:
            if line:
                line_text = reconstruct_line_with_spacing(line, avg_char_width)
                paragraphs.append(line_text)
    
    markdown_output = format_as_markdown(paragraphs)
    markdown_path = base_name + '.md'
    with open(markdown_path, 'w', encoding='utf-8') as f:
        f.write(markdown_output)
    log_print(f"Markdown saved to {os.path.basename(markdown_path)}")
    
    return metadata


def load_previous_metadata(prev_metadata_path):
    """Load previous page metadata for validation."""
    try:
        with open(prev_metadata_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log_print(f"Warning: Could not load previous metadata from {prev_metadata_path}: {e}")
        return None


def normalize_mixed_verse_notation(verse_str, current_chapter):
    """
    Normalize mixed verse notation where some segments have chapter markers and some don't.
    
    Example: "30-32,6:1,2" with chapter 5 becomes "5:30-32,6:1-2"
    
    Args:
        verse_str: Verse string that may be in mixed format
        current_chapter: The current chapter number to apply to segments without markers
    
    Returns:
        Normalized verse notation string
    """
    if not verse_str or not current_chapter:
        return verse_str
    
    verse_str = str(verse_str)
    
    # Check if it's mixed format (contains : but not all segments have it)
    if ':' not in verse_str:
        # No chapter markers at all - this is standard format
        return verse_str
    
    # Split by comma BUT keep track of which segments belong to which chapter
    # "30-32,6:1,2" should become "5:30-32,6:1-2" not "5:30-32,6:1,5:2"
    segments = verse_str.split(',')
    normalized_segments = []
    last_chapter = current_chapter
    pending_verses = []
    
    for i, segment in enumerate(segments):
        segment = segment.strip()
        
        if ':' in segment:
            # Flush any pending verses with previous chapter
            if pending_verses:
                verse_part = ','.join(pending_verses)
                normalized_segments.append(f"{last_chapter}:{verse_part}")
                pending_verses = []
            
            # Extract chapter and verse from this segment
            ch_str, v_part = segment.split(':', 1)
            try:
                last_chapter = int(ch_str)
                # Add verses to pending (might be followed by more verses for this chapter)
                pending_verses.append(v_part)
            except ValueError:
                # Invalid chapter, just add as-is
                normalized_segments.append(segment)
        else:
            # No chapter marker - add to pending verses for last_chapter
            pending_verses.append(segment)
    
    # Flush remaining pending verses
    if pending_verses:
        verse_part = ','.join(pending_verses)
        # If this is the very first segment and has no chapter, use current_chapter
        if not normalized_segments and last_chapter == current_chapter:
            normalized_segments.append(f"{current_chapter}:{verse_part}")
        else:
            normalized_segments.append(f"{last_chapter}:{verse_part}")
    
    normalized = ','.join(normalized_segments)
    
    if normalized != verse_str:
        log_print(f"DEBUG: Normalized mixed verse format: '{verse_str}' -> '{normalized}'")
    
    return normalized


def extract_first_verse_from_notation(verse_notation):
    """
    Extract first chapter:verse from notation.
    
    Args:
        verse_notation: String like "27:42-46" or "27:42-46,28:1"
    
    Returns:
        (chapter, verse) tuple or (None, None)
    """
    if not verse_notation:
        return None, None
    
    try:
        verse_str = str(verse_notation).strip()
        
        # Check if it's chapter-spanning notation (contains :)
        if ':' in verse_str:
            # Parse first segment
            first_segment = verse_str.split(',')[0].strip()
            
            # Extract chapter:verse
            ch_str, v_part = first_segment.split(':', 1)
            chapter = int(ch_str.strip())
            
            # Extract first verse from range or single
            # Clean v_part of any extraneous characters
            v_part = v_part.strip()
            if '-' in v_part:
                first_v = v_part.split('-')[0].strip()
                # Remove any trailing commas or non-digit characters
                first_v = ''.join(c for c in first_v if c.isdigit())
                verse = int(first_v) if first_v else None
            else:
                # Remove any trailing commas or non-digit characters
                v_part = ''.join(c for c in v_part if c.isdigit())
                verse = int(v_part) if v_part else None
            
            return chapter, verse if verse else None
        else:
            # Old format (no chapter marker)
            if '-' in verse_str:
                first_v = verse_str.split('-')[0].strip()
                # Remove any non-digit characters
                first_v = ''.join(c for c in first_v if c.isdigit())
                verse = int(first_v) if first_v else None
            elif ',' in verse_str:
                first_v = verse_str.split(',')[0].strip()
                # Remove any non-digit characters
                first_v = ''.join(c for c in first_v if c.isdigit())
                verse = int(first_v) if first_v else None
            else:
                # Remove any non-digit characters
                verse_str = ''.join(c for c in verse_str if c.isdigit())
                verse = int(verse_str) if verse_str else None
            
            return None, verse
    except Exception as e:
        log_print(f"WARNING: Error parsing verse notation '{verse_notation}': {e}")
        return None, None


def extract_last_verse_from_notation(verse_notation):
    """
    Extract last chapter:verse from notation.
    
    Args:
        verse_notation: String like "27:42-46" or "27:42-46,28:1"
    
    Returns:
        (chapter, verse) tuple or (None, None)
    """
    if not verse_notation:
        return None, None
    
    try:
        verse_str = str(verse_notation).strip()
        
        # Check if it's chapter-spanning notation (contains :)
        if ':' in verse_str:
            # Parse last segment
            last_segment = verse_str.split(',')[-1].strip()
            
            # Extract chapter:verse
            if ':' in last_segment:
                ch_str, v_part = last_segment.split(':', 1)
                chapter = int(ch_str.strip())
            else:
                # No chapter marker in last segment, need to find from previous segment
                return None, None
            
            # Extract last verse from range or single
            # Clean v_part of any extraneous characters
            v_part = v_part.strip()
            if '-' in v_part:
                last_v = v_part.split('-')[-1].strip()
                # Remove any trailing commas or non-digit characters
                last_v = ''.join(c for c in last_v if c.isdigit())
                verse = int(last_v) if last_v else None
            else:
                # Remove any trailing commas or non-digit characters
                v_part = ''.join(c for c in v_part if c.isdigit())
                verse = int(v_part) if v_part else None
            
            return chapter, verse if verse else None
        else:
            # Old format (no chapter marker)
            # Split by comma first to get the last segment
            last_segment = verse_str.split(',')[-1].strip()
            
            if '-' in last_segment:
                last_v = last_segment.split('-')[-1].strip()
                # Remove any non-digit characters
                last_v = ''.join(c for c in last_v if c.isdigit())
                verse = int(last_v) if last_v else None
            else:
                # Remove any non-digit characters
                last_v_str = ''.join(c for c in last_segment if c.isdigit())
                verse = int(last_v_str) if last_v_str else None
            
            return None, verse
    except Exception as e:
        log_print(f"WARNING: Error parsing verse notation '{verse_notation}': {e}")
        return None, None


def validate_and_correct_metadata(current_metadata, prev_metadata, ocr_data=None, found_verses=None):
    """
    Validate current metadata against previous page and auto-correct obvious errors.
    Uses Bible structure to validate book names, chapter ranges, and verse ranges.
    Also validates verses against content markers (Ver. X) found in OCR.
    Supports chapter-spanning notation (e.g., "27:42-46,28:1").
    
    Args:
        current_metadata: Current page metadata
        prev_metadata: Previous page metadata
        ocr_data: Optional OCR data for content-based validation
        found_verses: Optional list of verse markers found in content
    """
    if not prev_metadata:
        return current_metadata
    
    log_print(f"\nDEBUG: Validating against previous metadata:")
    log_print(f"  Previous: book={prev_metadata.get('book_name')}, ch={prev_metadata.get('chapter')}, v={prev_metadata.get('verse')}, page={prev_metadata.get('page_number')}")
    log_print(f"  Current:  book={current_metadata.get('book_name')}, ch={current_metadata.get('chapter')}, v={current_metadata.get('verse')}, page={current_metadata.get('page_number')}, continuation={current_metadata.get('is_verse_continuation')}")
    
    corrected = current_metadata.copy()
    corrections_made = []
    
    # Step 1: Validate against Bible structure
    curr_book = corrected.get('book_name')
    curr_chapter = corrected.get('chapter')
    curr_verse = corrected.get('verse')
    prev_book = prev_metadata.get('book_name')
    prev_chapter = prev_metadata.get('chapter')
    prev_verse = prev_metadata.get('verse')
    
    # Detect if this is likely a book or chapter transition based on verse restart
    verse_restarted = verse_has_restarted(curr_verse)
    
    if curr_book or curr_chapter or curr_verse:
        validation = validate_bible_reference(curr_book, curr_chapter, curr_verse)
        bible_struct = build_bible_structure()
        
        if not validation['valid']:
            log_print(f"\nDEBUG: Bible structure validation errors:")
            for error in validation['errors']:
                log_print(f"  - {error}")
            
            # SMART CORRECTION LOGIC
            
            # Case 1: Book is invalid/unreadable AND verse has restarted from 1
            # This suggests a new book has started
            if curr_book:
                if curr_book.upper() not in bible_struct and verse_restarted:
                    next_book = get_next_book(prev_book)
                    if next_book:
                        log_print(f"DEBUG: Verse restarted and book invalid -> assuming transition to next book: {next_book}")
                        corrections_made.append(f"book: {curr_book} -> {next_book} (verse restart suggests new book)")
                        corrected['book_name'] = next_book
                        curr_book = next_book # Update local variable
                        corrected['book_warning'] = f"OCR detected invalid book '{curr_book}', verse restart suggests {next_book}"
                        # Also reset chapter to 1 when transitioning to new book
                        if curr_chapter != 1:
                            corrections_made.append(f"chapter: {curr_chapter} -> 1 (new book)")
                            corrected['chapter'] = 1
                elif curr_book.upper() not in bible_struct:
                    # Book invalid but no verse restart - use previous book
                    if prev_book:
                        corrections_made.append(f"book: {curr_book} -> {prev_book} (invalid book name)")
                        corrected['book_name'] = prev_book
                        curr_book = prev_book # Update local variable
                        corrected['book_warning'] = f"OCR detected invalid book '{curr_book}', using previous book"
            
            # Case 2: Chapter is invalid/missing AND verse has restarted from 1
            # This suggests chapter has transitioned to next chapter
            elif not curr_chapter or (curr_chapter and validation['max_chapter'] and curr_chapter > validation['max_chapter']):
                if verse_restarted and prev_chapter:
                    next_chapter = prev_chapter + 1
                    # Verify next chapter is valid for current book
                    curr_book_for_check = corrected.get('book_name') or prev_book
                    if curr_book_for_check:
                        book_validation = validate_bible_reference(curr_book_for_check, next_chapter, None)
                        if book_validation['valid']:
                            log_print(f"DEBUG: Verse restarted and chapter invalid -> assuming next chapter: {next_chapter}")
                            corrections_made.append(f"chapter: {curr_chapter} -> {next_chapter} (verse restart suggests new chapter)")
                            corrected['chapter'] = next_chapter
                            corrected['chapter_warning'] = f"OCR detected chapter {curr_chapter}, verse restart suggests {next_chapter}"
                        else:
                            # Next chapter would be out of range - might be new book
                            if prev_book:
                                next_book = get_next_book(prev_book)
                                if next_book:
                                    log_print(f"DEBUG: Verse restarted, chapter invalid, and next chapter out of range -> new book: {next_book}")
                                    corrections_made.append(f"book: {corrected.get('book_name')} -> {next_book} (chapter overflow + verse restart)")
                                    corrected['book_name'] = next_book
                                    curr_book = next_book # Update local variable
                                    corrected['chapter'] = 1
                                    corrected['book_warning'] = f"Chapter exceeded max, verse restart suggests new book {next_book}"
            
            # Case 3: Chapter is out of range but no verse restart - use previous chapter
            elif curr_chapter and validation['max_chapter']:
                if curr_chapter > validation['max_chapter']:
                    if prev_chapter and prev_chapter <= validation['max_chapter']:
                        corrections_made.append(f"chapter: {curr_chapter} -> {prev_chapter} (out of range)")
                        corrected['chapter'] = prev_chapter
                        corrected['chapter_warning'] = f"OCR detected chapter {curr_chapter} but max is {validation['max_chapter']}"
            
            # Case 4: Verse is out of range - clamp to max
            # Error format: "Invalid verse range START-END for BOOK CH. Valid range: 1-MAX"
            for error in validation['errors']:
                if "Invalid verse range" in error and "Valid range:" in error:
                    try:
                        # Extract valid max
                        valid_part = error.split('Valid range:')[1].strip()
                        if '-' in valid_part:
                            max_verse = int(valid_part.split('-')[1])
                            
                            # Parse current verse
                            curr_v_str = str(curr_verse)
                            new_v_str = curr_v_str
                            
                            if '-' in curr_v_str:
                                start_v = int(curr_v_str.split('-')[0])
                                end_v = int(curr_v_str.split('-')[1])
                                
                                if end_v > max_verse:
                                    if start_v > max_verse:
                                        # Entire range is invalid? Maybe wrong chapter.
                                        # But if we can't fix chapter, clamp to max? 
                                        # Or if start_v > max_verse, it's totally wrong.
                                        pass 
                                    else:
                                        # Clamp end
                                        new_v_str = f"{start_v}-{max_verse}"
                                        log_print(f"DEBUG: Clamping verse range to max: {curr_v_str} -> {new_v_str}")
                                        corrections_made.append(f"verse: {curr_v_str} -> {new_v_str} (exceeds max {max_verse})")
                                        corrected['verse'] = new_v_str
                                        corrected['verse_warning'] = f"Clamped verse range to chapter maximum {max_verse}"
                    except Exception as e:
                        log_print(f"DEBUG: Failed to auto-correct verse range: {e}")
            
            # Re-validate after corrections
            curr_book = corrected.get('book_name')
            curr_chapter = corrected.get('chapter')
            curr_verse = corrected.get('verse')
            validation = validate_bible_reference(curr_book, curr_chapter, curr_verse)
            
            if not validation['valid']:
                log_print(f"DEBUG: Still invalid after corrections: {validation['errors']}")
    
    # Validate and correct page number
    if prev_metadata.get('page_number') is not None:
        expected_page = prev_metadata['page_number'] + 1
        if current_metadata.get('page_number') != expected_page:
            corrections_made.append(f"page: {current_metadata.get('page_number')} -> {expected_page}")
            corrected['page_number'] = expected_page
    
    # Validate and correct book name
    prev_book = prev_metadata.get('book_name')
    curr_book = corrected.get('book_name')
    if prev_book:
        if not curr_book:
            # If current book missing, use previous
            corrections_made.append(f"book: None -> {prev_book}")
            corrected['book_name'] = prev_book
            curr_book = prev_book # Update local variable for downstream logic
        elif curr_book != prev_book:
            # Book should only change if chapter restarts to 1
            if corrected.get('chapter') != 1:
                corrections_made.append(f"book: {curr_book} -> {prev_book}")
                corrected['book_name'] = prev_book
                curr_book = prev_book # Update local variable for downstream logic
    
    # Validate and correct chapter
    prev_chapter = prev_metadata.get('chapter')
    curr_chapter = current_metadata.get('chapter')
    prev_v = prev_metadata.get('verse') # Need this early
    
    # Calculate effective previous chapter from verse notation
    # If prev verse string is "2:24,3:1-2", effective end chapter is 3.
    # If prev verse string is "10:26-29,11:1,2", effective end chapter is 11.
    effective_prev_ch = prev_chapter
    if prev_chapter and prev_v and ':' in str(prev_v):
         try:
             # Iterate through all segments to track chapter context
             segments = str(prev_v).split(',')
             current_context_ch = prev_chapter
             for seg in segments:
                 seg = seg.strip()
                 if ':' in seg:
                     ch_part = seg.split(':')[0]
                     if ch_part.isdigit():
                         current_context_ch = int(ch_part)
             effective_prev_ch = current_context_ch
             log_print(f"DEBUG: Calculated effective_prev_ch={effective_prev_ch} from '{prev_v}'")
         except:
             pass

    same_book = (prev_book == curr_book)
    
    if same_book and prev_chapter is not None and curr_chapter is not None:
        # Chapter should be same or +1 relative to EITHER the start chapter or the end chapter of previous page
        # This handles cases where prev page spans chapters (e.g. 31 -> 32) so next page can be 33
        valid_chapters = {prev_chapter, prev_chapter + 1}
        if effective_prev_ch:
            valid_chapters.add(effective_prev_ch)
            valid_chapters.add(effective_prev_ch + 1)
            
        if curr_chapter not in valid_chapters:
            # If current seems wrong, keep previous chapter (or effective previous)
            # Prefer effective_prev_ch if available and > prev_chapter
            target_ch = effective_prev_ch if effective_prev_ch and effective_prev_ch > prev_chapter else prev_chapter
            
            corrections_made.append(f"chapter: {curr_chapter} -> {target_ch} (invalid jump from {prev_chapter}/{effective_prev_ch})")
            corrected['chapter'] = target_ch
        
        # New check: False Positive Chapter Change Detection
        # If chapter increased (Ch 1 -> 2), but verses are sequential (16 -> 17) and NOT starting at 1
        # Then it's likely NOT a chapter change.
        elif curr_chapter == prev_chapter + 1 or (effective_prev_ch and curr_chapter == effective_prev_ch + 1):
             curr_v = current_metadata.get('verse') # prev_v already retrieved

            
             # Only flag as false positive if we are NOT continuing from a spanned chapter
             # If effective_prev_ch == curr_chapter (e.g. 3 == 3), then we are just continuing Ch 3.
             if effective_prev_ch != curr_chapter:
                 if prev_v and curr_v:
                     try:
                         # Get last verse of prev
                         # Get last verse of prev
                         p_last = -1
                         p_str = str(prev_v).strip()
                         # Handle chapter-spanning notation like "31:18,32:1" -> extract "32:1" -> "1"
                         if ',' in p_str: p_str = p_str.split(',')[-1]
                         if ':' in p_str: p_str = p_str.split(':')[-1]
                         if '-' in p_str: p_str = p_str.split('-')[-1]
                         
                         p_str = ''.join(c for c in p_str if c.isdigit())
                         if p_str: p_last = int(p_str)

                         # Get first verse of curr
                         c_first = -1
                         if ',' in str(curr_v): c_first = int(str(curr_v).split(',')[0])
                         elif '-' in str(curr_v): c_first = int(str(curr_v).split('-')[0])
                         elif ':' in str(curr_v): # Handle 2:17-21
                             # If it has chapter, we need to respect the notation...
                             # BUT if the notation was GENERATED based on the wrong chapter assumption?
                             # The notation "2:17-21" comes from our previous logic.
                             # If we strip the chapter...
                             first_part = str(curr_v).split(',')[0]
                             if ':' in first_part: c_first = int(first_part.split(':')[1].split('-')[0])
                             else: c_first = int(first_part.split('-')[0])
                         else: c_first = int(curr_v)

                         if p_last > 0 and c_first > 0:
                             diff = c_first - p_last
                             if diff == 1 and c_first > 1:
                                 # Sequential verses (16->17) across chapter change (1->2).
                                 # This is suspicious. Chapter changes usually reset to 1.
                                 # UNLESS the previous chapter ENDED at 16? 
                                 # We can check max verses if we have the book.
                                 
                                 is_valid_transition = False
                                 current_book_name = corrected.get('book_name') or prev_book
                                 if current_book_name:
                                     bible = build_bible_structure()
                                     if current_book_name.upper() in bible:
                                         max_v_prev = bible[current_book_name.upper()].get(prev_chapter, 999)
                                         if p_last >= max_v_prev:
                                             is_valid_transition = True # It ended exactly at max
                                 
                                 if not is_valid_transition:
                                     log_print(f"DEBUG: False Positive Chapter Change detected: Ch {effective_prev_ch}->{curr_chapter} but verses {p_last}->{c_first} are sequential")
                                     corrections_made.append(f"chapter: {curr_chapter} -> {effective_prev_ch} (sequential verses)")
                                     corrected['chapter'] = effective_prev_ch
                     except:
                         pass

    elif prev_chapter is not None and curr_chapter is None:
        # If current chapter missing, use previous
        corrections_made.append(f"chapter: None -> {prev_chapter}")
        corrected['chapter'] = prev_chapter
    
    # Validate and correct verse
    prev_verse = prev_metadata.get('verse')
    curr_verse = current_metadata.get('verse')
    
    if prev_verse and curr_verse:
        # Extract last chapter:verse from previous page
        last_prev_ch, last_prev_verse = extract_last_verse_from_notation(prev_verse)
        
        # Extract first chapter:verse from current page
        first_curr_ch, first_curr_verse = extract_first_verse_from_notation(curr_verse)
        
        if last_prev_verse and first_curr_verse:
            verse_diff = first_curr_verse - last_prev_verse
            
            # Get current chapter (after any corrections)
            final_curr_chapter = corrected.get('chapter', current_metadata.get('chapter'))
            
            # Determine if chapters changed
            # If notation contains chapter markers, use those; otherwise use metadata chapter
            prev_chapter_for_compare = last_prev_ch if last_prev_ch is not None else prev_chapter
            curr_chapter_for_compare = first_curr_ch if first_curr_ch is not None else final_curr_chapter
            
            log_print(f"DEBUG: Verse comparison: prev={prev_chapter_for_compare}:{last_prev_verse}, curr={curr_chapter_for_compare}:{first_curr_verse}")
            
            # Step 0: Detect suspicious patterns that suggest OCR errors in chapter-spanning notation
            # Pattern: "Ch:V1-V2,Ch:1" where V2 is high (e.g., 42-46) and next is verse 1
            # This strongly suggests chapter transition: should be "Ch:V1-V2,(Ch+1):1"
            curr_verse_str = str(curr_verse)
            if ':' in curr_verse_str and ',' in curr_verse_str:
                # Parse segments
                segments = curr_verse_str.split(',')
                if len(segments) == 2:
                    # Check if both segments have same chapter
                    seg1_parts = segments[0].split(':')
                    seg2_parts = segments[1].split(':')
                    
                    if len(seg1_parts) == 2 and len(seg2_parts) == 2:
                        ch1 = int(seg1_parts[0])
                        ch2 = int(seg2_parts[0])
                        
                        # Extract verses from each segment
                        v1_part = seg1_parts[1]
                        v2_part = seg2_parts[1]
                        
                        # Check if second segment starts with verse 1 and same chapter
                        if ch1 == ch2 and v2_part.startswith('1'):
                            # Get the last verse from first segment
                            if '-' in v1_part:
                                last_v1 = int(v1_part.split('-')[-1])
                            else:
                                last_v1 = int(v1_part)
                            
                            # If last verse is > 20 (suggesting end of chapter), this is likely OCR error
                            if last_v1 > 20:
                                log_print(f"DEBUG: Suspicious pattern detected: {ch1}:{v1_part} followed by {ch2}:{v2_part}")
                                log_print(f"DEBUG: Verses ending at {last_v1} followed by verse 1 suggests chapter transition")
                                
                                # Use Bible structure to determine which chapter is wrong
                                # Check if ch1 can have the verse range specified
                                bible_struct = build_bible_structure()
                                current_book = corrected.get('book_name') or prev_book
                                
                                correct_ch1 = ch1
                                correct_ch2 = ch1 + 1
                                
                                if current_book and current_book.upper() in bible_struct:
                                    book_chapters = bible_struct[current_book.upper()]
                                    
                                    # Check if ch1 can accommodate the verses (e.g., 42-46)
                                    if ch1 in book_chapters:
                                        max_verses_ch1 = book_chapters[ch1]
                                        
                                        # Check if the verse range is valid for ch1
                                        if last_v1 > max_verses_ch1:
                                            # Verses don't fit in ch1! Ch1 must be wrong.
                                            log_print(f"DEBUG: Chapter {ch1} only has {max_verses_ch1} verses, but notation has verses up to {last_v1}")
                                            log_print(f"DEBUG: First chapter must be incorrect")
                                            
                                            # Try previous chapter if it can accommodate these verses
                                            if prev_chapter and prev_chapter in book_chapters:
                                                max_verses_prev = book_chapters[prev_chapter]
                                                if last_v1 <= max_verses_prev:
                                                    # Previous chapter can accommodate! Use it.
                                                    correct_ch1 = prev_chapter
                                                    correct_ch2 = prev_chapter + 1
                                                    log_print(f"DEBUG: Chapter {prev_chapter} has {max_verses_prev} verses - using it as first chapter")
                                                else:
                                                    # Even previous chapter can't accommodate
                                                    # Try ch1-1
                                                    if ch1 - 1 in book_chapters:
                                                        max_verses_ch1_minus_1 = book_chapters[ch1 - 1]
                                                        if last_v1 <= max_verses_ch1_minus_1:
                                                            correct_ch1 = ch1 - 1
                                                            correct_ch2 = ch1
                                                            log_print(f"DEBUG: Chapter {ch1-1} has {max_verses_ch1_minus_1} verses - using it")
                                            else:
                                                # No prev_chapter, try ch1-1
                                                if ch1 - 1 in book_chapters:
                                                    max_verses_ch1_minus_1 = book_chapters[ch1 - 1]
                                                    if last_v1 <= max_verses_ch1_minus_1:
                                                        correct_ch1 = ch1 - 1
                                                        correct_ch2 = ch1
                                                        log_print(f"DEBUG: Chapter {ch1-1} has {max_verses_ch1_minus_1} verses - using it")
                                        else:
                                            # Ch1 can accommodate the verses, so ch1 is correct
                                            log_print(f"DEBUG: Chapter {ch1} has {max_verses_ch1} verses, can accommodate verses up to {last_v1}")
                                            correct_ch1 = ch1
                                            correct_ch2 = ch1 + 1
                                    else:
                                        # Ch1 not in Bible structure, fall back to previous chapter logic
                                        log_print(f"DEBUG: Chapter {ch1} not found in Bible structure for {current_book}")
                                        if prev_chapter:
                                            correct_ch1 = prev_chapter
                                            correct_ch2 = prev_chapter + 1
                                else:
                                    # No Bible structure available, use simple heuristics
                                    log_print(f"DEBUG: No Bible structure available for {current_book}")
                                    if prev_chapter and prev_chapter == ch1 - 1:
                                        correct_ch1 = ch1
                                        correct_ch2 = ch1 + 1
                                    elif prev_chapter:
                                        correct_ch1 = prev_chapter
                                        correct_ch2 = prev_chapter + 1
                                    else:
                                        correct_ch1 = ch1
                                        correct_ch2 = ch1 + 1
                                
                                log_print(f"DEBUG: Correcting: {ch1}:{v1_part},{ch2}:{v2_part} -> {correct_ch1}:{v1_part},{correct_ch2}:{v2_part}")
                                
                                # Correct the notation
                                corrected_verse = f"{correct_ch1}:{v1_part},{correct_ch2}:{v2_part}"
                                corrected['verse'] = corrected_verse
                                corrections_made.append(f"verse: {curr_verse} -> {corrected_verse} (OCR error: chapter should change)")
                                corrected['verse_warning'] = f"OCR read both chapters as {ch1}, corrected to {correct_ch1},{correct_ch2} based on verse pattern and previous chapter"
                                
                                # Also update metadata chapter if first chapter was corrected
                                if correct_ch1 != ch1 and corrected.get('chapter') == ch1:
                                    corrected['chapter'] = correct_ch1
                                    corrections_made.append(f"chapter: {ch1} -> {correct_ch1} (corrected based on verse pattern)")
                                
                                # Update for subsequent checks
                                curr_verse_str = corrected_verse
                                curr_verse = corrected_verse
                                # Re-extract chapter/verse after correction
                                first_curr_ch, first_curr_verse = extract_first_verse_from_notation(corrected_verse)
                                curr_chapter_for_compare = first_curr_ch if first_curr_ch is not None else final_curr_chapter
            
            # Step 1: Check for overlap - current should never start at or before previous ending
            # BUT: Only check if we're in the SAME book and SAME chapter (changes reset verse numbers)
            if first_curr_verse <= last_prev_verse:
                # First check: Did the BOOK change?
                if prev_book and curr_book and prev_book != curr_book:
                    # Book changed - verse reset is expected (Genesis → Exodus, etc.)
                    log_print(f"DEBUG: Book changed from {prev_book} to {curr_book}, verse reset to {first_curr_verse} is expected")
                # Second check: Did the chapter change? (using chapter from notation if available)
                elif (prev_chapter_for_compare is not None and curr_chapter_for_compare is not None and 
                    curr_chapter_for_compare != prev_chapter_for_compare):
                    # Chapter changed - verse reset is expected
                    log_print(f"DEBUG: Chapter changed from {prev_chapter_for_compare} to {curr_chapter_for_compare}, verse reset to {first_curr_verse} is expected")
                elif prev_chapter_for_compare is None or curr_chapter_for_compare is None:
                    # Unknown chapter - skip overlap check
                    log_print(f"DEBUG: Cannot verify overlap - chapter unknown (prev={prev_chapter_for_compare}, curr={curr_chapter_for_compare})")
                else:
                    # Check if this is a valid continuation
                    is_continuation = current_metadata.get('is_verse_continuation', False)
                    
                    if is_continuation:
                        log_print(f"DEBUG: Verse overlap detected but allowed due to no_verse_markers=True")
                    else:
                        # Same book and same chapter - this is a real overlap
                        log_print(f"DEBUG: Verse overlap detected: prev ends at {last_prev_verse}, current starts at {first_curr_verse}")
                        expected_verse = last_prev_verse + 1
                        
                        # Remove overlapping verses instead of blindly shifting
                        if ',' in curr_verse_str:
                            # It's a list - remove overlapping verses
                            # robustly handle prefixes like "10:1"
                            verse_nums = []
                            for v in curr_verse_str.split(','):
                                v_clean = v.strip()
                                if ':' in v_clean:
                                    v_clean = v_clean.split(':')[-1]
                                if '-' in v_clean: # Handle range in list?
                                     v_clean = v_clean.split('-')[0] # just take start for simplicty or ignore
                                if v_clean.isdigit():
                                    verse_nums.append(int(v_clean))

                            non_overlapping = [v for v in verse_nums if v >= expected_verse]
                            
                            if non_overlapping:
                                corrected_verse = ','.join(str(v) for v in non_overlapping)
                                log_print(f"DEBUG: Removed overlapping verses: {verse_nums} -> {non_overlapping}")
                            else:
                                # All verses overlap - shift to expected range
                                num_verses = len(verse_nums)
                                corrected_verses = [str(expected_verse + i) for i in range(num_verses)]
                                corrected_verse = ','.join(corrected_verses)
                                log_print(f"DEBUG: All verses overlapped, shifted: {verse_nums} -> {corrected_verses}")
                        elif '-' in curr_verse_str:
                            # It's a range - adjust to start at expected_verse
                            parts = curr_verse_str.split('-')
                            
                            # Clean start/end parts of chapter prefixes
                            start_str = parts[0].strip()
                            if ':' in start_str: start_str = start_str.split(':')[-1]
                            
                            end_str = parts[1].strip()
                            if ':' in end_str: end_str = end_str.split(':')[-1]
                            
                            try:
                                range_start = int(start_str)
                                range_end = int(end_str)
                                
                                if range_end >= expected_verse:
                                    # Keep non-overlapping part of range
                                    corrected_verse = f"{expected_verse}-{range_end}"
                                    log_print(f"DEBUG: Trimmed overlapping range: {range_start}-{range_end} -> {expected_verse}-{range_end}")
                                else:
                                    # Entire range overlaps - shift it
                                    range_size = range_end - range_start
                                    corrected_verse = f"{expected_verse}-{expected_verse + range_size}"
                                    log_print(f"DEBUG: Entire range overlapped, shifted: {range_start}-{range_end} -> {corrected_verse}")
                            except ValueError:
                                log_print(f"DEBUG: Could not parse range values from {curr_verse_str} - skipping fix")
                                corrected_verse = curr_verse_str
                        else:
                            # Single verse overlaps - replace with expected
                            corrected_verse = str(expected_verse)
                            log_print(f"DEBUG: Single verse overlapped, replaced: {first_curr_verse} -> {expected_verse}")
                        
                        corrections_made.append(f"verse: {curr_verse} -> {corrected_verse} (removed overlap with previous ending at {last_prev_verse})")
                        corrected['verse'] = corrected_verse
                        corrected['verse_warning'] = f"OCR detected {curr_verse} but corrected to {corrected_verse} to remove overlap with previous verse {last_prev_verse}"
                        
                        # Update curr_verse_str for gap detection
                        curr_verse_str = corrected_verse
                        curr_verse = corrected_verse
            
            # Step 2: Check for unrealistic gaps (after overlap correction)
            # Only check gaps if we're in the SAME book AND SAME chapter (not after book/chapter changes)
            # Use chapter from notation if available, otherwise use metadata chapter
            same_book = (prev_book is not None and curr_book is not None and prev_book == curr_book)
            same_chapter = (prev_chapter_for_compare is not None and curr_chapter_for_compare is not None and 
                          curr_chapter_for_compare == prev_chapter_for_compare)
            
            log_print(f"DEBUG: Gap detection - same_book={same_book}, same_chapter={same_chapter} (prev_book={prev_book}, curr_book={curr_book}, prev_ch={prev_chapter_for_compare}, curr_ch={curr_chapter_for_compare})")
            
            if same_book and same_chapter:
                # Re-parse the potentially corrected verse string
                # First, strip chapter prefix if present (e.g., "27:2-9" -> "2-9")
                verse_only_str = curr_verse_str
                if ':' in curr_verse_str:
                    # Chapter-spanning notation - extract just the verses from current chapter
                    # For notation like "27:2-9", take the part after the colon
                    # For notation like "26:32-35,27:1", we already extracted first_curr_verse
                    if ',' in curr_verse_str:
                        # Multi-chapter: use the verse we already extracted
                        verse_only_str = str(first_curr_verse)
                    else:
                        # Single chapter with notation like "27:2-9"
                        parts = curr_verse_str.split(':', 1)
                        if len(parts) == 2:
                            verse_only_str = parts[1]
                
                # Now parse the verse-only string
                if ',' in verse_only_str:
                    verse_parts = [int(v.strip()) for v in verse_only_str.split(',') if v.strip().isdigit()]
                elif '-' in verse_only_str:
                    try:
                        start, end = verse_only_str.split('-')
                        verse_parts = list(range(int(start.strip()), int(end.strip()) + 1))
                    except ValueError:
                        # If parsing fails, skip gap detection
                        verse_parts = []
                else:
                    verse_parts = [int(verse_only_str)] if verse_only_str.isdigit() else []
                
                # Check if range is unreasonably large (e.g., "25-96" = 72 verses on one page!)
                if '-' in verse_only_str and len(verse_parts) > 10:
                    log_print(f"DEBUG: Unreasonably large range detected: {curr_verse_str} ({len(verse_parts)} verses)")
                    
                    # Correct based on OCR body markers if available
                    expected_verse = last_prev_verse + 1
                    
                    found_in_range = [v for v in verse_parts if v in found_verses]
                    if found_in_range:
                        # Use the highest verse actually found in the OCR body
                        max_found = max(found_in_range)
                        log_print(f"DEBUG: Found verses in large range: {min(found_in_range)}-{max_found}. Correcting end to {max_found}")
                        corrected_verse = f"{expected_verse}-{max_found}"
                    else:
                        # Fallback: Assume just 2 verses if we can't verify body content
                        corrected_verse = f"{expected_verse}-{expected_verse + 1}"
                    
                    corrections_made.append(f"verse: {curr_verse} -> {corrected_verse} (unreasonably large range)")
                    corrected['verse'] = corrected_verse
                    corrected['verse_warning'] = f"OCR detected {curr_verse} but corrected to {corrected_verse} (range too large)"
                
                # Check for gaps within a list (not range)
                elif ',' in verse_only_str and len(verse_parts) >= 2:
                    # Check gaps between consecutive verses in the list
                    for i in range(len(verse_parts) - 1):
                        gap = verse_parts[i + 1] - verse_parts[i]
                        if gap > 10:
                            log_print(f"DEBUG: Large internal verse gap detected: {verse_parts[i]} -> {verse_parts[i+1]} (gap: {gap})")
                            
                            # Reconstruct the list with sequential verses
                            expected_verse = last_prev_verse + 1
                            corrected_verses = [str(expected_verse + j) for j in range(len(verse_parts))]
                            corrected_verse = ','.join(corrected_verses)
                            
                            corrections_made.append(f"verse: {curr_verse} -> {corrected_verse} (internal gap detected)")
                            corrected['verse'] = corrected_verse
                            corrected['verse_warning'] = f"OCR detected {curr_verse} but auto-corrected to {corrected_verse} based on previous verse {last_prev_verse}"
                            break
                
                # Also check gap from previous to current (applies to ranges/lists too)
                # Check if first verse in current page has a gap from last verse of previous page
                elif verse_diff > 1:
                    log_print(f"DEBUG: A verse gap detected: {last_prev_verse} -> {first_curr_verse} (gap: {verse_diff})")
                    
                    # Check if the missing verse was actually found in the OCR body but dropped by Ollama
                    missing_verse = last_prev_verse + 1
                    restored = False
                    
                    if found_verses and missing_verse in found_verses:
                        log_print(f"DEBUG: Missing verse {missing_verse} found in OCR body! Restoring it...")
                        
                        # Prepend missing verse to current verse string
                        if '-' in curr_verse_str and not ':' in curr_verse_str:
                             # Extend range: "17-19" -> "16-19"
                             # Verify current start is missing_verse + 1?
                             if first_curr_verse == missing_verse + 1:
                                 new_verse_str = f"{missing_verse}-{curr_verse_str.split('-')[-1]}"
                                 restored = True
                        elif ',' in curr_verse_str and not ':' in curr_verse_str:
                             # Add to list: "17,19" -> "16,17,19"
                             new_verse_str = f"{missing_verse},{curr_verse_str}"
                             restored = True
                        elif curr_verse_str.isdigit():
                             # Single verse: "17" -> "16,17"
                             if first_curr_verse == missing_verse + 1:
                                 new_verse_str = f"{missing_verse}-{first_curr_verse}" # consecutive
                             else:
                                 new_verse_str = f"{missing_verse},{curr_verse_str}"
                             restored = True
                        
                        if restored:
                            corrections_made.append(f"verse: {curr_verse_str} -> {new_verse_str} (restored missing verse {missing_verse} from OCR)")
                            corrected['verse'] = new_verse_str
                            corrected['verse_warning'] = f"Restored missing verse {missing_verse} detected in OCR body but dropped by validation"
                    
                    if not restored:
                        # Standard gap correction (shifting)
                        
                        # CRITICAL CHECK: Is the detected start verse actually in the body?
                        # If so, the gap is likely real (sparse commentary), so DO NOT correct it.
                        is_start_confirmed = False
                        if found_verses and first_curr_verse in found_verses:
                             log_print(f"DEBUG: Start verse {first_curr_verse} confirmed in body markers. Skipping gap correction (gap is real).")
                             is_start_confirmed = True
                        
                        if not is_start_confirmed:
                            expected_verse = last_prev_verse + 1
                        
                            # Correct the first verse in the notation
                            # Correct the first verse in the notation
                            if ':' in curr_verse_str:
                                # Chapter-spanning notation like "25:34,26:1-2"
                                # Replace the first verse number while preserving the structure
                                from verse_notation import parse_verse_notation, format_verse_notation
                                try:
                                    parsed = parse_verse_notation(curr_verse_str)
                                    if parsed and len(parsed[0]['verses']) > 0:
                                        # Replace first verse
                                        parsed[0]['verses'][0] = expected_verse
                                        # Reconstruct notation
                                        parts = []
                                        for span in parsed:
                                            ch = span['chapter']
                                            verses = span['verses']
                                            if len(verses) == 1:
                                                v_str = str(verses[0])
                                            elif len(verses) == 2:
                                                v_str = f"{verses[0]},{verses[1]}"
                                            else:
                                                v_str = f"{verses[0]}-{verses[-1]}"
                                            parts.append(f"{ch}:{v_str}")
                                        corrected_verse = ','.join(parts)
                                except:
                                    # Fallback to simple replacement
                                    corrected_verse = str(expected_verse)
                            elif '-' in verse_only_str:
                                # Range - only adjust START to fix gap, keep END unchanged
                                # The ending verse is likely correct (from body markers/header)
                                # Only the starting verse was missed (OCR failure)
                                # Only the starting verse was missed (OCR failure)
                                parts = verse_only_str.split('-')
                                new_start = expected_verse
                                new_end = int(parts[1])  # Keep original ending
                                corrected_verse = f"{new_start}-{new_end}"
                                log_print(f"DEBUG: Adjusted range start to fix gap: {verse_only_str} -> {corrected_verse}")
                            elif ',' in verse_only_str:
                                # List like "34,36", correct first to expected
                                parts = verse_only_str.split(',')
                                parts[0] = str(expected_verse)
                                corrected_verse = ','.join(parts)
                            else:
                                # Single verse
                                corrected_verse = str(expected_verse)
                            
                            corrections_made.append(f"verse: {curr_verse} -> {corrected_verse} (large gap from {last_prev_verse}, expected {expected_verse})")
                            corrected['verse'] = corrected_verse
                            corrected['verse_warning'] = f"OCR detected {curr_verse} but auto-corrected to {corrected_verse} based on previous verse {last_prev_verse}"
            else:
                log_print(f"DEBUG: Book or chapter changed - skipping gap detection (verses can restart at 1)")
    
    # Note: Verse content validation already done in Step 2 (passed via found_verses parameter)
    # No need to re-run find_verse_markers_in_ocr() here
    
    if corrections_made:
        log_print(f"\nDEBUG: Corrections applied based on previous metadata:")
        for correction in corrections_made:
            log_print(f"  - {correction}")
    else:
        log_print(f"DEBUG: No corrections needed - metadata validated successfully")
    
    # Step Final: Synchronize verse notation with corrected chapter
    # If chapter was corrected (e.g. 20 -> 25) but verse string still has old chapter (20:53-55), update it.
    final_ch = corrected.get('chapter')
    final_v_str = str(corrected.get('verse', ''))
    
    if final_ch and ':' in final_v_str:
        # Check if the main chapter is already explicitly present in the verse string
        # If so, we assume the string is already absolute/correct and likely spans chapters
        # E.g. final_ch=25, str="24:25,25:1" -> 25 is present, so don't shift 24->25
        is_main_ch_present = False
        for part in final_v_str.split(','):
            if part.strip().startswith(f"{final_ch}:"):
                is_main_ch_present = True
                break
        
        if is_main_ch_present:
             log_print(f"DEBUG: Main chapter {final_ch} found in verse string '{final_v_str}' - skipping synchronization")
        else:
            # Check the first chapter prefix in the verse string
            first_part = final_v_str.split(',')[0]
            if ':' in first_part:
                try:
                    v_ch_str = first_part.split(':')[0]
                    v_ch = int(v_ch_str)
                    
                    if v_ch != final_ch:
                        # Chapter mismatch detected!
                        diff = final_ch - v_ch
                        log_print(f"DEBUG: Synchronizing verse notation chapters: {v_ch} -> {final_ch} (offset {diff})")
                        
                        # Shift all chapter prefixes in the string
                        new_parts = []
                        for parts in final_v_str.split(','):
                            if ':' in parts:
                                c_str, v_rest = parts.split(':', 1)
                                if c_str.strip().isdigit():
                                    new_c = int(c_str) + diff
                                    new_parts.append(f"{new_c}:{v_rest}")
                                else:
                                    new_parts.append(parts)
                            else:
                                new_parts.append(parts)
                        
                        new_v_final = ','.join(new_parts)
                        corrections_made.append(f"verse notation: {final_v_str} -> {new_v_final} (sync with chapter {final_ch})")
                        corrected['verse'] = new_v_final
                        corrected['verse_warning'] = f"Synchronized verse notation chapters with main chapter {final_ch}"
                except Exception as e:
                    log_print(f"DEBUG: Failed to sync verse chapters: {e}")
    
    return corrected


def discover_images_in_directory(start_image_path):
    """
    Discover all image files in the same directory as the start image.
    
    Args:
        start_image_path: Path to the starting image file
    
    Returns:
        List of image file paths in the directory
    """
    image_dir = os.path.dirname(os.path.abspath(start_image_path))
    image_extensions = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp'}
    
    images = []
    for filename in os.listdir(image_dir):
        if os.path.splitext(filename)[1].lower() in image_extensions:
            images.append(os.path.join(image_dir, filename))
    
    return images


def get_page_number_from_filename(image_path):
    """
    Extract page number from image filename.
    Looks for patterns like 'page90', 'page_90', 'p90', etc.
    
    Args:
        image_path: Path to the image file
    
    Returns:
        Page number (int) or None if not found
    """
    filename = os.path.basename(image_path)
    
    # Try various patterns: page90, page_90, p90, etc.
    import re
    patterns = [
        r'page[_\s]*(\d+)',  # page90, page_90, page 90
        r'p[_\s]*(\d+)',     # p90, p_90, p 90
        r'(\d+)',            # any number in filename
    ]
    
    for pattern in patterns:
        match = re.search(pattern, filename, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except:
                pass
    
    return None


def get_page_number_from_metadata(image_path):
    """
    Extract page number from an image's metadata JSON file.
    Falls back to filename if metadata doesn't exist.
    
    Args:
        image_path: Path to the image file
    
    Returns:
        Page number (int) or None if not found
    """
    base_name = os.path.splitext(image_path)[0]
    metadata_path = base_name + '_metadata.json'
    
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
                page_num = metadata.get('page_number')
                if page_num is not None:
                    return page_num
        except:
            pass
    
    # Fall back to filename
    return get_page_number_from_filename(image_path)


def sort_images_by_page_number(images):
    """
    Sort images by their page numbers extracted from filenames.
    This ensures sequential filename-based processing (page90, page91, page92, etc.)
    Falls back to alphabetical filename sorting if no page number found.
    
    Args:
        images: List of image file paths
    
    Returns:
        Sorted list of (image_path, page_number) tuples
    """
    images_with_pages = []
    images_without_pages = []
    
    for img in images:
        # Use filename-based page number for sorting (not metadata)
        page_num = get_page_number_from_filename(img)
        if page_num is not None:
            images_with_pages.append((img, page_num))
        else:
            images_without_pages.append((img, None))
    
    # Sort images with page numbers numerically
    images_with_pages.sort(key=lambda x: x[1])
    
    # Sort images without page numbers alphabetically by filename
    images_without_pages.sort(key=lambda x: os.path.basename(x[0]))
    
    return images_with_pages + images_without_pages


def batch_process_images(start_image_path, lang='eng', right_col_char_pos=None, 
                        validate_ollama=False, max_pages=None, 
                        stop_on_book_change=False, stop_on_chapter_change=False,
                        continue_on_error=False,
                        start_page=None, start_book=None, start_chapter=None, start_verse=None,
                        book_only=None, use_legacy_validation=False):
    """
    Process multiple images in sequence, chaining metadata validation.
    
    Args:
        start_image_path: Path to the starting image
        lang: Tesseract language
        right_col_char_pos: Right column character position
        validate_ollama: Whether to validate with Ollama
        max_pages: Maximum number of pages to process
        stop_on_book_change: Stop when book changes
        stop_on_chapter_change: Stop when chapter changes
        continue_on_error: Continue processing on errors (default: abort)
        start_page: Expected page number for first image (for validation seeding)
        start_book: Expected book name for first image (for validation seeding)
        start_chapter: Expected chapter for first image (for validation seeding)
        start_verse: Expected starting verse for first image (for validation seeding)
    
    Returns:
        Number of images processed
    """
    log_print(f"\n{'='*80}")
    log_print(f"BATCH PROCESSING MODE")
    log_print(f"{'='*80}")
    
    # Discover all images in the directory
    log_print(f"\nDiscovering images in directory...")
    all_images = discover_images_in_directory(start_image_path)
    log_print(f"Found {len(all_images)} image files")
    
    # Sort by page number
    log_print(f"Sorting images by page number...")
    sorted_images = sort_images_by_page_number(all_images)
    
    # Find starting position
    start_abs_path = os.path.abspath(start_image_path)
    start_index = 0
    for i, (img_path, page_num) in enumerate(sorted_images):
        if os.path.abspath(img_path) == start_abs_path:
            start_index = i
            break
    
    # Auto-load previous metadata if not provided and not starting from beginning
    # This is useful if resuming a batch process from a middle image
    prev_metadata = None # Initialize prev_metadata here, it will be overwritten by seed_expectations if present
    if start_index > 0 and not (start_page or start_book or start_chapter or start_verse):
        prev_image_path_tuple = sorted_images[start_index - 1]
        prev_image_path = prev_image_path_tuple[0] # Get the actual path from the tuple
        
        # Construct metadata path, assuming common image extensions
        base_name = os.path.splitext(prev_image_path)[0]
        prev_meta_path = base_name + '_metadata.json'
        
        if os.path.exists(prev_meta_path):
            try:
                log_print(f"Auto-loading previous metadata from: {os.path.basename(prev_meta_path)}")
                with open(prev_meta_path, 'r', encoding='utf-8') as f:
                    prev_metadata = json.load(f)
            except Exception as e:
                log_print(f"Warning: Failed to auto-load previous metadata: {e}")
    
    log_print(f"Starting from image {start_index + 1} of {len(sorted_images)}: {os.path.basename(start_image_path)}")
    
    if max_pages:
        log_print(f"Maximum pages to process: {max_pages}")
    if stop_on_book_change:
        log_print(f"Will stop when book changes")
    if stop_on_chapter_change:
        log_print(f"Will stop when chapter changes")
    
    log_print(f"\n{'='*80}\n")
    
    # Process images sequentially
    # Process images sequentially
    # prev_metadata = None # <--- This line was wiping out our auto-loaded metadata! Removed.
    
    # Store seed expectations separately for fallback
    seed_expectations = {}
    
    # Create seed metadata if start parameters provided
    if start_page or start_book or start_chapter or start_verse:
        log_print(f"Using seed metadata for validation:")
        if start_page:
            log_print(f"  Expected starting page: {start_page}")
            seed_expectations['page_number'] = start_page
        if start_book:
            log_print(f"  Expected starting book: {start_book}")
            seed_expectations['book_name'] = start_book
        if start_chapter:
            log_print(f"  Expected starting chapter: {start_chapter}")
            seed_expectations['chapter'] = start_chapter
        if start_verse:
            log_print(f"  Expected starting verse: {start_verse}")
            seed_expectations['verse'] = start_verse
        
        # Create synthetic previous metadata (one page/verse before)
        prev_metadata = {}
        if start_page:
            prev_metadata['page_number'] = start_page - 1
        if start_book:
            prev_metadata['book_name'] = start_book
        if start_chapter:
            prev_metadata['chapter'] = start_chapter
        if start_verse:
            # Parse verse to get the starting number
            verse_str = str(start_verse)
            if '-' in verse_str:
                # It's a range, use the first number minus 1
                first_verse = int(verse_str.split('-')[0])
                if first_verse > 1:
                    prev_metadata['verse'] = str(first_verse - 1)
                # Don't set verse if starting at verse 1 (no previous verse exists)
            elif ',' in verse_str:
                # It's a list, use the first number minus 1
                first_verse = int(verse_str.split(',')[0])
                if first_verse > 1:
                    prev_metadata['verse'] = str(first_verse - 1)
                # Don't set verse if starting at verse 1
            else:
                # Single verse
                start_v = int(verse_str)
                if start_v > 1:
                    prev_metadata['verse'] = str(start_v - 1)
                # Don't set verse if starting at verse 1
        
        log_print(f"  Created synthetic previous metadata: {prev_metadata}")
        log_print(f"\n{'='*80}\n")
    
    initial_book = None
    initial_chapter = None
    processed_count = 0
    
    for i in range(start_index, len(sorted_images)):
        img_path, page_num = sorted_images[i]
        
        # Check max_pages limit
        if max_pages and processed_count >= max_pages:
            log_print(f"\n{'='*80}")
            log_print(f"Reached maximum page limit ({max_pages})")
            log_print(f"{'='*80}\n")
            break
        
        log_print(f"\n{'='*80}")
        log_print(f"Processing image {processed_count + 1}")
        if max_pages:
            log_print(f"Progress: {processed_count + 1}/{max_pages}")
        log_print(f"File: {os.path.basename(img_path)}")
        if page_num:
            log_print(f"Current page: {page_num}")
        log_print(f"{'='*80}\n")
        
        # Check if we are seeking a specific book
        seeking_book = False
        if book_only:
            # Check if we have identified the current book yet
            # We need to process the image to get metadata OR verify against known pattern
            # For efficiency, we can try to peek at existing metadata first
            seeking_book = True # Default to seeking until verified
            
            # Optimization: Check for existing metadata first to avoid OCR if skipping
            temp_metadata = {}
            if get_page_number_from_metadata(img_path): # Use existing function strictly? No, let's load it manually
                base_name = os.path.splitext(img_path)[0]
                meta_path = base_name + '_metadata.json'
                if os.path.exists(meta_path):
                     try:
                        with open(meta_path, 'r', encoding='utf-8') as f:
                            temp_metadata = json.load(f)
                     except: 
                        pass
            
            # If we don't have metadata, we MUST process the image to know the book
            # But we can do a lighter pass? No, process_image does it all.
            # So we will proceed to process logic, but check the result before saving/counting?
            # Actually, process_image does the saving. 
            # We'll just let it process. If it's the wrong book, we ignore/skip "counting" it or just log it?
            # Better: if we find it's the wrong book AFTER processing, and we haven't started our target book yet, we ignore it.
            # If we HAVE started, and it's wrong, we stop.
            pass

        # Process the image (all steps 1-9 are done in process_image)
        try:
            metadata = process_image(img_path, None, lang, right_col_char_pos, validate_ollama, prev_metadata, use_legacy_validation)
            
            # Apply book filter logic
            if book_only:
                current_book = metadata.get('book_name')
                
                # Normalize names for comparison
                target_book_norm = book_only.lower().strip()
                current_book_norm = current_book.lower().strip() if current_book else ""
                
                # Check for match (fuzzy or exact)
                is_match = target_book_norm in current_book_norm or current_book_norm in target_book_norm
                
                if not initial_book: # Function-scope var to track if we have STARTED matching
                    if is_match:
                         log_print(f"FOUND TARGET BOOK: '{current_book}' (matches '{book_only}') - Starting batch sequence.")
                         initial_book = current_book # Mark as started
                    else:
                         log_print(f"Skipping page in '{current_book}' (Seeking '{book_only}')...")
                         # Do not increment processed_count? 
                         # Actually, we processed it (compute used), but effectively skipped the "batch" logic.
                         continue
                else:
                    # We have already started processing the target book.
                    # If this page does NOT match, we are done.
                    if not is_match and current_book: 
                        # Allow some tolerance for "None" books (failed OCR) inside a batch?
                        # If explicitly different book:
                        log_print(f"\n{'='*80}")
                        log_print(f"STOPPING: Finished target book '{initial_book}' (Switching to '{current_book}')")
                        log_print(f"{'='*80}\n")
                        break
            
            # Apply seed expectations as fallback for first image if detection failed
            if processed_count == 0 and seed_expectations:
                if not metadata.get('page_number') and 'page_number' in seed_expectations:
                    log_print(f"Applying seed expectation: page_number = {seed_expectations['page_number']}")
                    metadata['page_number'] = seed_expectations['page_number']
                if not metadata.get('book_name') and 'book_name' in seed_expectations:
                    log_print(f"Applying seed expectation: book_name = {seed_expectations['book_name']}")
                    metadata['book_name'] = seed_expectations['book_name']
                if not metadata.get('chapter') and 'chapter' in seed_expectations:
                    log_print(f"Applying seed expectation: chapter = {seed_expectations['chapter']}")
                    metadata['chapter'] = seed_expectations['chapter']
                if not metadata.get('verse') and 'verse' in seed_expectations:
                    log_print(f"Applying seed expectation: verse = {seed_expectations['verse']}")
                    metadata['verse'] = seed_expectations['verse']
                    
                    # Re-extract Hebrew verses with corrected metadata
                    if metadata.get('book_name') and metadata.get('chapter'):
                        hebrew_verses = get_hebrew_verse(
                            metadata['book_name'],
                            metadata['chapter'],
                            metadata['verse']
                        )
                        if hebrew_verses:
                            metadata['hebrew_text'] = hebrew_verses
                            log_print(f"Re-extracted {len(hebrew_verses)} Hebrew verse(s) after applying seed expectations")
                    
                    # Save corrected metadata
                    base_name = os.path.splitext(img_path)[0]
                    json_path = base_name + '_metadata.json'
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(metadata, f, indent=2, ensure_ascii=False)
                    log_print(f"Updated metadata saved with seed expectations")
            

            
            # Store initial book/chapter for comparison
            if processed_count == 0:
                initial_book = metadata.get('book_name')
                initial_chapter = metadata.get('chapter')
            
            # Check stopping conditions
            current_book = metadata.get('book_name')
            current_chapter = metadata.get('chapter')
            
            if stop_on_book_change and current_book and initial_book:
                if current_book != initial_book:
                    log_print(f"\n{'='*80}")
                    log_print(f"STOPPING: Book changed from '{initial_book}' to '{current_book}'")
                    log_print(f"{'='*80}\n")
                    break
            
            if stop_on_chapter_change and current_chapter and initial_chapter:
                if current_chapter != initial_chapter:
                    log_print(f"\n{'='*80}")
                    log_print(f"STOPPING: Chapter changed from {initial_chapter} to {current_chapter}")
                    log_print(f"{'='*80}\n")
                    break
            
            # Update for next iteration
            prev_metadata = metadata
            processed_count += 1
            
        except Exception as e:
            log_print(f"\nERROR processing {os.path.basename(img_path)}: {e}")
            import traceback
            traceback.print_exc()
            
            if continue_on_error:
                log_print(f"WARNING: Continuing with next image (metadata chain broken)\n")
                # Reset prev_metadata to prevent cascading errors
                prev_metadata = None
                continue
            else:
                log_print(f"ABORTING: Cannot continue without valid metadata from previous page\n")
                log_print(f"\n{'='*80}")
                log_print(f"BATCH PROCESSING ABORTED")
                log_print(f"Successfully processed {processed_count} images before error")
                log_print(f"To continue processing despite errors, use --continue-on-error flag")
                log_print(f"{'='*80}\n")
                return processed_count
    
    log_print(f"\n{'='*80}")
    log_print(f"BATCH PROCESSING COMPLETE")
    log_print(f"Processed {processed_count} images")
    log_print(f"{'='*80}\n")
    
    return processed_count


if __name__ == "__main__":
    if len(sys.argv) < 2:
        log_print("Usage: python script.py <image_path> [output_path] [OPTIONS]")
        log_print("\nOutput files created:")
        log_print("  <base>_metadata.json - Metadata with book/chapter/verse/page info")
        log_print("  <base>.md            - Formatted markdown with columns")
        log_print("  <base>_ocr.json      - Complete OCR data with bounding boxes")
        log_print("\nSingle Image Processing Options:")
        log_print("  --lang LANG              - Tesseract language (default: eng)")
        log_print("  --right-col POS          - Right column character position")
        log_print("  --prev-metadata PATH     - Previous page metadata JSON for validation")
        log_print("  --validate-ollama        - Validate metadata using Ollama vision model")
        log_print("  --legacy-validation      - Use legacy monolithic validation logic")
        log_print("\nBatch Processing Options:")
        log_print("  --batch                  - Process all images in directory starting from given image")
        log_print("  --max-pages N            - Maximum number of pages to process in batch mode")
        log_print("  --stop-on-book-change    - Stop batch processing when book changes")
        log_print("  --stop-on-chapter-change - Stop batch processing when chapter changes")
        log_print("  --continue-on-error      - Continue processing on errors (default: abort)")
        log_print("  --start-page N           - Expected page number for first image (for validation)")
        log_print("  --start-book NAME        - Expected book name for first image (for validation)")
        log_print("  --start-chapter N        - Expected chapter for first image (for validation)")
        log_print("  --start-verse N          - Expected verse for first image (for validation)")
        log_print("  --log-file PATH          - Log all output to specified file")
        sys.exit(1)
    
    image_path = sys.argv[1]
    output_path = None
    lang = 'eng'
    right_col_char_pos = None
    prev_metadata_path = None
    validate_ollama = False
    batch_mode = False
    max_pages = None
    stop_on_book_change = False
    stop_on_chapter_change = False
    continue_on_error = False
    start_page = None
    start_book = None
    start_chapter = None
    start_verse = None
    book_only = None
    log_file_path = None
    use_legacy_validation = False
    
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == '--lang' and i + 1 < len(sys.argv):
            lang = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--right-col' and i + 1 < len(sys.argv):
            right_col_char_pos = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == '--prev-metadata' and i + 1 < len(sys.argv):
            prev_metadata_path = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--validate-ollama':
            validate_ollama = True
            i += 1
        elif sys.argv[i] == '--legacy-validation':
            use_legacy_validation = True
            i += 1
        elif sys.argv[i] == '--batch':
            batch_mode = True
            i += 1
        elif sys.argv[i] == '--max-pages' and i + 1 < len(sys.argv):
            max_pages = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == '--stop-on-book-change':
            stop_on_book_change = True
            i += 1
        elif sys.argv[i] == '--stop-on-chapter-change':
            stop_on_chapter_change = True
            i += 1
        elif sys.argv[i] == '--continue-on-error':
            continue_on_error = True
            i += 1
        elif sys.argv[i] == '--start-page' and i + 1 < len(sys.argv):
            start_page = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == '--start-book' and i + 1 < len(sys.argv):
            start_book = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--start-chapter' and i + 1 < len(sys.argv):
            start_chapter = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == '--start-verse' and i + 1 < len(sys.argv):
            start_verse = sys.argv[i + 1]
            i += 2
        elif (sys.argv[i] == '--log-file' or sys.argv[i] == '-log-file') and i + 1 < len(sys.argv):
            log_file_path = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--book-only' and i + 1 < len(sys.argv):
            book_only = sys.argv[i + 1]
            i += 2
        else:
            output_path = sys.argv[i]
            i += 1
    
    # Set up logging if requested
    if log_file_path:
        set_log_file(log_file_path)
    
    try:
        # Batch processing mode
        if batch_mode:
            batch_process_images(
                image_path, 
                lang=lang, 
                right_col_char_pos=right_col_char_pos,
                validate_ollama=validate_ollama,
                max_pages=max_pages,
                stop_on_book_change=stop_on_book_change,
                stop_on_chapter_change=stop_on_chapter_change,
                continue_on_error=continue_on_error,
                start_page=start_page,
                start_book=start_book,
                start_chapter=start_chapter,
                start_verse=start_verse,
                book_only=book_only,
                use_legacy_validation=use_legacy_validation
            )
        else:
            # Single image processing mode
            # Load previous metadata if provided
            prev_metadata = None
            if prev_metadata_path:
                prev_metadata = load_previous_metadata(prev_metadata_path)
            
            # Process image (all steps 1-9 are done in process_image)
            metadata = process_image(image_path, output_path, lang, right_col_char_pos, validate_ollama, prev_metadata)
    finally:
        # Ensure log file is closed
        close_log_file()