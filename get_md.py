import pytesseract
from PIL import Image
import re
import sys
import json
import os
from pathlib import Path
from datetime import datetime
pytesseract.pytesseract.tesseract_cmd = 'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'

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

def get_usfm_directory():
    """Get the path to the hbo_usfm directory."""
    script_dir = Path(__file__).parent
    usfm_dir = script_dir / 'hbo_usfm'
    return usfm_dir if usfm_dir.exists() else None

def get_english_usfm_directory():
    """Get the path to the eng-kjv2006_usfm directory."""
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
        verse: Verse number, range, or list (string or int)
    
    Returns:
        dict with keys:
        - 'valid': bool
        - 'errors': list of error messages
        - 'max_chapter': int or None
        - 'max_verse': int or None
    """
    bible = build_bible_structure()
    errors = []
    
    # Normalize book name
    book_name_upper = book_name.upper() if book_name else None
    
    # Check if book exists
    if not book_name_upper or book_name_upper not in bible:
        valid_books = sorted(bible.keys())
        errors.append(f"Invalid book '{book_name}'. Valid books: {', '.join(valid_books[:5])}...")
        return {'valid': False, 'errors': errors, 'max_chapter': None, 'max_verse': None}
    
    book_data = bible[book_name_upper]
    max_chapter = max(book_data.keys()) if book_data else None
    
    # Check if chapter exists
    if chapter is not None:
        if chapter < 1 or chapter > max_chapter:
            errors.append(f"Invalid chapter {chapter} for {book_name}. Valid range: 1-{max_chapter}")
            return {'valid': False, 'errors': errors, 'max_chapter': max_chapter, 'max_verse': None}
        
        max_verse = book_data.get(chapter)
        
        # Check verse(s)
        if verse is not None:
            verse_str = str(verse)
            
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
                        try:
                            chapters[current_chapter][int(verse_num)] = verse_text
                        except ValueError:
                            continue
    except Exception as e:
        log_print(f"Error parsing USFM file {usfm_path}: {e}")
        return {}
    
    return chapters

def get_hebrew_verse(book_name, chapter, verse):
    """
    Extract Hebrew verse(s) from USFM files.
    
    Args:
        book_name: Name of the book (English)
        chapter: Chapter number (int)
        verse: Verse number or range/list (str or int)
                Examples: "3", "3-5", "3,4,5"
    
    Returns:
        Dictionary with verse text or None if not found
    """
    if not book_name or not chapter or not verse:
        return None
    
    usfm_dir = get_usfm_directory()
    if not usfm_dir:
        log_print("Warning: hbo_usfm directory not found")
        return None
    
    book_name_normalized = book_name.strip().replace(' ', '').lower()
    usfm_filename = None
    for key, value in BOOK_NAME_TO_USFM.items():
        if key.lower() == book_name_normalized:
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

def validate_metadata_with_ollama(image_path, metadata):
    """
    Validate OCR metadata using Ollama vision model.
    
    Args:
        image_path: Path to the image file
        metadata: Dictionary with book_name, chapter, verse, page_number
    
    Returns:
        Validated metadata dictionary or original if validation fails
    """
    if not BAML_AVAILABLE:
        log_print("Skipping Ollama validation (BAML not available)")
        return metadata
    
    try:
        log_print("\nStep 3: Validating metadata with Ollama...")
        
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
        
        # Convert metadata to BAML Metadata type
        baml_metadata = baml_types.Metadata(
            book_name=metadata.get('book_name'),
            chapter=metadata.get('chapter'),
            verse=metadata.get('verse'),
            page_number=metadata.get('page_number')
        )
        
        # Call Ollama validation
        validated = baml_client.ValidateOCRMetadata(
            image=image,
            ocr_metadata=baml_metadata
        )
        
        # Convert back to dictionary
        result = {
            'book_name': validated.book_name.upper(),
            'chapter': validated.chapter,
            'verse': validated.verse,
            'page_number': validated.page_number
        }
        
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


def correct_verse_ocr_errors(verse_parts):
    """
    Correct common OCR errors in verse numbers, particularly '9' misread as '2'.
    Detects when consecutive verse numbers have unrealistic gaps (>5) and tries correction.
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
            
            # Suspiciously large gap (e.g., 25 -> 96)
            if gap > 5:
                # Try replacing '9' with '2' in current verse
                if '9' in part:
                    test_part = part.replace('9', '2', 1)  # Replace first '9' only
                    if test_part.isdigit():
                        test_val = int(test_part)
                        test_gap = test_val - prev
                        
                        # If corrected gap is reasonable (1-5), use it
                        if 0 < test_gap <= 5:
                            log_print(f"DEBUG: OCR correction: verse {part} -> {test_part} (gap {gap} -> {test_gap})")
                            corrected_part = test_part
        
        # Check against next verse
        if i < len(verse_parts) - 1 and verse_parts[i + 1].isdigit():
            next_val = int(verse_parts[i + 1])
            gap = next_val - current
            
            # Large gap to next verse
            if gap > 5:
                # Try replacing '9' with '2' in next verse (will be corrected when we get there)
                pass  # Will be handled when we process the next verse
        
        corrected.append(corrected_part)
    
    return corrected


def combine_verse_list_boxes(boxes, start_index):
    """Combine consecutive boxes that form a verse list like '3,' + '4.' = '3,4'."""
    if start_index >= len(boxes):
        return None, start_index
    
    verse_parts = []
    current_index = start_index
    
    # Look for patterns like "3,", "4.", "5,", etc.
    while current_index < len(boxes):
        box = boxes[current_index]
        text = box['text'].strip()
        
        # Check if this looks like part of a verse list
        if re.match(r'^[0-9IVXLCDM]+[,.]?$', text, re.IGNORECASE):
            verse_parts.append(text.replace('.', '').replace(',', ''))
            current_index += 1
            
            # If this text ends with a period, it's likely the end of the list
            if text.endswith('.'):
                break
        else:
            break
    
    if verse_parts:
        # Apply OCR correction for common '9' -> '2' error
        verse_parts = correct_verse_ocr_errors(verse_parts)
        
        # Join the parts with commas
        combined_verse = ','.join(verse_parts)
        log_print(f"DEBUG: Combined verse list from boxes: {verse_parts} -> {combined_verse}")
        return combined_verse, current_index
    
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


def extract_chapter_verse_from_boxes(boxes):
    """Extract chapter and verse from a list of boxes, handling multi-box patterns."""
    if not boxes:
        return None, None
    
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
                        # Skip if it's clearly a verse marker (just "V.")
                        if re.match(r'^V\.?$', next_text, re.IGNORECASE):
                            log_print(f"DEBUG: Skipping '{next_text}' - likely verse marker, not chapter")
                            break
                        
                        chapter = roman_to_decimal(next_text.replace('.', ''))
                        if chapter:
                            i = j  # Move index to this position
                            log_print(f"DEBUG: Chapter {chapter} found in separate box: '{next_text}'")
                            break
                    # Stop if we hit a standalone verse marker
                    elif re.match(r'^V\.', next_text, re.IGNORECASE):
                        break
            
            if chapter:
                # Check if we found an embedded verse marker (like "IV." = I + V.)
                # In this case, i points to the box with the embedded marker
                # We need to look for verse numbers starting from the next box
                
                # Now look for verse marker and number
                verse_search_start = i + 1
                
                for k in range(verse_search_start, min(verse_search_start + 4, len(sorted_boxes))):
                    verse_box = sorted_boxes[k]
                    verse_text = verse_box['text'].strip()
                    
                    # Check for verse marker with appended number/range/list
                    v_match = re.search(r'^[IV]V?\.?(.+)', verse_text, re.IGNORECASE)
                    if v_match:
                        verse_part = v_match.group(1)
                        verse = parse_verse_text(verse_part)
                        if verse:
                            log_print(f"DEBUG: Verse {verse} found appended to marker: '{verse_text}'")
                            break
                    
                    # Check for standalone verse marker
                    elif re.match(r'^[IV]V?\.?$', verse_text, re.IGNORECASE):
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
                    
                    # If no verse marker found, try to parse directly as verse numbers
                    # This handles the case where we already found the verse marker embedded (like in "IV.")
                    # and the next boxes contain the verse numbers directly (like "3,", "4.")
                    else:
                        log_print(f"DEBUG: No verse marker in '{verse_text}', trying to combine verse list from position {k}")
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
    
    if page_side == 'left':
        cv_boxes = right_boxes
        log_print(f"DEBUG: Page number on left, searching for chapter/verse on right")
    elif page_side == 'right':
        cv_boxes = left_boxes
        log_print(f"DEBUG: Page number on right, searching for chapter/verse on left")
    else:
        # Fallback: search all non-center boxes
        cv_boxes = left_boxes + right_boxes
        log_print(f"DEBUG: Page number not found, searching all non-center boxes for chapter/verse")
    
    if cv_boxes:
        chapter, verse = extract_chapter_verse_from_boxes(cv_boxes)
    
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
    text_boxes = ocr_data['text']
    
    # Get image width to determine columns
    # Assuming we have left positions, calculate center
    left_positions = ocr_data['left']
    if len(left_positions) > 0:
        max_x = max(left_positions[i] + ocr_data['width'][i] if i < len(ocr_data['width']) else left_positions[i] 
                    for i in range(len(left_positions)) if left_positions[i] is not None)
        center_x = max_x / 2
        center_margin = max_x * 0.15  # 15% margin around center
    else:
        return set()
    
    # Pattern to match "Ver." (case-sensitive!) followed by numbers
    # Must be at start of text (after optional whitespace)
    verse_pattern = re.compile(r'^\s*Ver\.\s*(\d+)')  # No re.IGNORECASE - case sensitive!
    
    # Search each box
    for i, text in enumerate(text_boxes):
        if not text or text.strip() == '':
            continue
        
        # Get x position of this box
        x_pos = left_positions[i] if i < len(left_positions) else None
        if x_pos is None:
            continue
        
        # Skip if box is in center area (we only want left/right columns)
        if abs(x_pos - center_x) < center_margin:
            continue
        
        # Check if text starts with "Ver." (case-sensitive)
        match = verse_pattern.match(text)
        if match:
            try:
                verse_num = int(match.group(1))
                verses_found.add(verse_num)
                column = "left" if x_pos < center_x else "right"
                log_print(f"DEBUG: Found verse marker 'Ver. {verse_num}' in {column} column, OCR box {i}: '{text[:50]}'")
            except ValueError:
                pass
        
        # Also check if current box starts with "Ver." and next box starts with a number
        # This handles the case where the pattern spans boxes
        if i < len(text_boxes) - 1:
            if re.match(r'^\s*Ver\.\s*$', text):  # Ends with "Ver." at start of line
                next_text = text_boxes[i + 1]
                if next_text:
                    match = re.match(r'^\s*(\d+)', next_text)
                    if match:
                        try:
                            verse_num = int(match.group(1))
                            verses_found.add(verse_num)
                            column = "left" if x_pos < center_x else "right"
                            log_print(f"DEBUG: Found verse marker 'Ver. {verse_num}' spanning boxes {i}-{i+1} in {column} column")
                        except ValueError:
                            pass
    
    return verses_found


def validate_verses_against_content(metadata_verse, found_verses):
    """
    Validate that the verse(s) in metadata appear in the actual content.
    
    Args:
        metadata_verse: Verse from metadata (can be "3", "3-5", "3,4,5")
        found_verses: Set of verse numbers found in OCR content
    
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
        if '-' in metadata_verse_str:
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
    except ValueError:
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


def process_image(image_path, output_path=None, lang='eng', right_col_char_pos=None, validate_ollama=False, prev_metadata=None):
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
    
    # Step 2: Find verse markers in English OCR to validate and correct verses
    log_print(f"\nStep 2: Searching for verse markers in body to validate verses...")
    found_verses = find_verse_markers_in_ocr(tsv_data_eng) or set()
    
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
        min_v = min(found_verses)
        max_v = max(found_verses)
        body_verse = f"{min_v}-{max_v}" if max_v > min_v else str(min_v)
        
        if header_info['verse']:
            # Header has verse - validate against body
            verse_validation = validate_verses_against_content(header_info['verse'], found_verses)
            log_print(f"Header verse '{header_info['verse']}' validation: {verse_validation['confidence']:.1%} confidence")
            
            # Use body verse if header confidence is low
            if not verse_validation['valid'] or verse_validation['confidence'] < 0.5:
                log_print(f"Using body verse: {header_info['verse']} -> {body_verse}")
                header_info['verse'] = body_verse
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
        header_info = validate_metadata_with_ollama(image_path, header_info)
        log_print(f"After Ollama: book={header_info['book_name']}, ch={header_info['chapter']}, v={header_info['verse']}, page={header_info['page_number']}")
    
    # Create basic metadata
    metadata = {
        'book_name': header_info['book_name'],
        'chapter': header_info['chapter'],
        'verse': header_info['verse'],
        'page_number': header_info['page_number']
    }
    
    # Steps 4-5: Validate against previous metadata and Bible structure
    if prev_metadata:
        log_print("\nStep 4-5: Validating against previous metadata and Bible structure...")
        # Pass found_verses from Step 2 to avoid re-finding them
        metadata = validate_and_correct_metadata(metadata, prev_metadata, tsv_data_eng, found_verses)
    
    # Step 6: Add Hebrew verses to validated metadata
    log_print("\nStep 6: Extracting Hebrew verses from USFM...")
    hebrew_verses = None
    if metadata.get('book_name') and metadata.get('chapter') and metadata.get('verse'):
        hebrew_verses = get_hebrew_verse(
            metadata['book_name'],
            metadata['chapter'],
            metadata['verse']
        )
        if hebrew_verses:
            log_print(f"Found {len(hebrew_verses)} Hebrew verse(s)")
    
    metadata['hebrew_text'] = hebrew_verses
    
    # Step 7: Save final metadata
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


def validate_and_correct_metadata(current_metadata, prev_metadata, ocr_data=None, found_verses=None):
    """
    Validate current metadata against previous page and auto-correct obvious errors.
    Uses Bible structure to validate book names, chapter ranges, and verse ranges.
    Also validates verses against content markers (Ver. X) found in OCR.
    
    Args:
        current_metadata: Current page metadata
        prev_metadata: Previous page metadata
        ocr_data: Optional OCR data for content-based validation
    """
    if not prev_metadata:
        return current_metadata
    
    log_print(f"\nDEBUG: Validating against previous metadata:")
    log_print(f"  Previous: book={prev_metadata.get('book_name')}, ch={prev_metadata.get('chapter')}, v={prev_metadata.get('verse')}, page={prev_metadata.get('page_number')}")
    log_print(f"  Current:  book={current_metadata.get('book_name')}, ch={current_metadata.get('chapter')}, v={current_metadata.get('verse')}, page={current_metadata.get('page_number')}")
    
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
                                    corrected['chapter'] = 1
                                    corrected['book_warning'] = f"Chapter exceeded max, verse restart suggests new book {next_book}"
            
            # Case 3: Chapter is out of range but no verse restart - use previous chapter
            elif curr_chapter and validation['max_chapter']:
                if curr_chapter > validation['max_chapter']:
                    if prev_chapter and prev_chapter <= validation['max_chapter']:
                        corrections_made.append(f"chapter: {curr_chapter} -> {prev_chapter} (out of range)")
                        corrected['chapter'] = prev_chapter
                        corrected['chapter_warning'] = f"OCR detected chapter {curr_chapter} but max is {validation['max_chapter']}"
            
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
    curr_book = current_metadata.get('book_name')
    if prev_book:
        if not curr_book:
            # If current book missing, use previous
            corrections_made.append(f"book: None -> {prev_book}")
            corrected['book_name'] = prev_book
        elif curr_book != prev_book:
            # Book should only change if chapter restarts to 1
            if corrected.get('chapter') != 1:
                corrections_made.append(f"book: {curr_book} -> {prev_book}")
                corrected['book_name'] = prev_book
    
    # Validate and correct chapter
    prev_chapter = prev_metadata.get('chapter')
    curr_chapter = current_metadata.get('chapter')
    if prev_chapter is not None and curr_chapter is not None:
        # Chapter should be same or +1
        if curr_chapter not in [prev_chapter, prev_chapter + 1]:
            # If current seems wrong, keep previous chapter
            corrections_made.append(f"chapter: {curr_chapter} -> {prev_chapter}")
            corrected['chapter'] = prev_chapter
    elif prev_chapter is not None and curr_chapter is None:
        # If current chapter missing, use previous
        corrections_made.append(f"chapter: None -> {prev_chapter}")
        corrected['chapter'] = prev_chapter
    
    # Validate and correct verse
    prev_verse = prev_metadata.get('verse')
    curr_verse = current_metadata.get('verse')
    
    if prev_verse and curr_verse:
        # Extract last verse number from previous page
        prev_verse_str = str(prev_verse)
        if '-' in prev_verse_str:
            # Range: get the end number
            last_prev_verse = int(prev_verse_str.split('-')[-1])
        elif ',' in prev_verse_str:
            # List: get the last number
            last_prev_verse = int(prev_verse_str.split(',')[-1])
        else:
            # Single verse
            last_prev_verse = int(prev_verse_str) if str(prev_verse_str).isdigit() else None
        
        # Extract first verse number from current page
        curr_verse_str = str(curr_verse)
        if '-' in curr_verse_str:
            first_curr_verse = int(curr_verse_str.split('-')[0])
        elif ',' in curr_verse_str:
            first_curr_verse = int(curr_verse_str.split(',')[0])
        else:
            first_curr_verse = int(curr_verse_str) if str(curr_verse_str).isdigit() else None
        
        if last_prev_verse and first_curr_verse:
            # Current verse should be within reasonable range of previous
            # Allow: same verse (continuation), next verse, or skip max 2-3 verses
            verse_diff = first_curr_verse - last_prev_verse
            
            if verse_diff > 3 or verse_diff < -1:
                # Verse jump seems too large, likely OCR error
                # Correct to expected verse(s)
                expected_verse = last_prev_verse + 1
                
                # Try to infer the correct verse range/list
                if ',' in curr_verse_str:
                    # It's a list, adjust each number
                    num_verses = len(curr_verse_str.split(','))
                    corrected_verses = [str(expected_verse + i) for i in range(num_verses)]
                    corrected_verse = ','.join(corrected_verses)
                elif '-' in curr_verse_str:
                    # It's a range, adjust both numbers
                    range_size = int(curr_verse_str.split('-')[1]) - int(curr_verse_str.split('-')[0])
                    corrected_verse = f"{expected_verse}-{expected_verse + range_size}"
                else:
                    # Single verse
                    corrected_verse = str(expected_verse)
                
                corrections_made.append(f"verse: {curr_verse} -> {corrected_verse} (large jump from {last_prev_verse}, expected {expected_verse})")
                corrected['verse'] = corrected_verse
                corrected['verse_warning'] = f"OCR detected {curr_verse} but auto-corrected to {corrected_verse} based on previous verse {last_prev_verse}"
    
    # Note: Verse content validation already done in Step 2 (passed via found_verses parameter)
    # No need to re-run find_verse_markers_in_ocr() here
    
    if corrections_made:
        log_print(f"\nDEBUG: Corrections applied based on previous metadata:")
        for correction in corrections_made:
            log_print(f"  - {correction}")
    else:
        log_print(f"DEBUG: No corrections needed - metadata validated successfully")
    
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
                        start_page=None, start_book=None, start_chapter=None, start_verse=None):
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
    
    log_print(f"Starting from image {start_index + 1} of {len(sorted_images)}: {os.path.basename(start_image_path)}")
    
    if max_pages:
        log_print(f"Maximum pages to process: {max_pages}")
    if stop_on_book_change:
        log_print(f"Will stop when book changes")
    if stop_on_chapter_change:
        log_print(f"Will stop when chapter changes")
    
    log_print(f"\n{'='*80}\n")
    
    # Process images sequentially
    prev_metadata = None
    
    # Create seed metadata if start parameters provided
    if start_page or start_book or start_chapter or start_verse:
        log_print(f"Using seed metadata for validation:")
        if start_page:
            log_print(f"  Expected starting page: {start_page}")
        if start_book:
            log_print(f"  Expected starting book: {start_book}")
        if start_chapter:
            log_print(f"  Expected starting chapter: {start_chapter}")
        if start_verse:
            log_print(f"  Expected starting verse: {start_verse}")
        
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
                prev_metadata['verse'] = str(max(1, first_verse - 1))
            elif ',' in verse_str:
                # It's a list, use the first number minus 1
                first_verse = int(verse_str.split(',')[0])
                prev_metadata['verse'] = str(max(1, first_verse - 1))
            else:
                # Single verse
                prev_metadata['verse'] = str(max(1, int(verse_str) - 1))
        
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
        
        # Process the image (all steps 1-9 are done in process_image)
        try:
            metadata = process_image(img_path, None, lang, right_col_char_pos, validate_ollama, prev_metadata)
            
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
            log_print(f"Continuing with next image...\n")
            continue
    
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
        log_print("\nBatch Processing Options:")
        log_print("  --batch                  - Process all images in directory starting from given image")
        log_print("  --max-pages N            - Maximum number of pages to process in batch mode")
        log_print("  --stop-on-book-change    - Stop batch processing when book changes")
        log_print("  --stop-on-chapter-change - Stop batch processing when chapter changes")
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
    start_page = None
    start_book = None
    start_chapter = None
    start_verse = None
    log_file_path = None
    
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
                start_page=start_page,
                start_book=start_book,
                start_chapter=start_chapter,
                start_verse=start_verse
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