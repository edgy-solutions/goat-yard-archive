# ST. Prefix Handling for New Testament Books

## Problem
The `get_md.py` script was not properly handling New Testament books when they were prefixed with "ST." (e.g., "ST. MATTHEW", "St. John", "ST.MARK") in the OCR extracted text. This is a common pattern in Bible commentaries.

## Solution
Added comprehensive ST. prefix normalization throughout the script:

### 1. New Function: `normalize_book_name()`
Created a central normalization function that:
- Removes "ST." and "ST " prefixes (case-insensitive)
- Strips trailing punctuation
- Converts to uppercase for consistent comparison

```python
def normalize_book_name(book_name):
    """
    Normalize book name by removing common prefixes and cleaning up.
    
    Args:
        book_name: Raw book name from OCR (e.g., "ST. MATTHEW", "St. John", "GENESIS")
    
    Returns:
        Normalized book name in uppercase (e.g., "MATTHEW", "JOHN", "GENESIS")
    """
```

### 2. Updated Testament Detection Functions
Both `is_new_testament()` and `is_old_testament()` now use `normalize_book_name()`:

```python
def is_new_testament(book_name):
    if not book_name:
        return False
    normalized = normalize_book_name(book_name)
    return normalized in NEW_TESTAMENT_BOOKS
```

### 3. Enhanced Greek USFM Mapping
Added entries for common ST. prefix variations:

```python
BOOK_NAME_TO_GREEK_USFM = {
    'Matthew': '46-MATgrctr.usfm',
    'St.Matthew': '46-MATgrctr.usfm',
    'St. Matthew': '46-MATgrctr.usfm',
    'StMatthew': '46-MATgrctr.usfm',
    # ... and so on for all Gospel books, James, and Jude
}
```

### 4. Updated All USFM Lookup Functions
Modified the following functions to use normalized book names:
- `get_hebrew_verse_spanning()`
- `get_hebrew_verse()`
- `get_greek_verse_spanning()`
- `get_greek_verse()`

### 5. Updated Validation Functions
- `validate_bible_reference()` - Now normalizes book names before validation
- `validate_metadata_with_ollama()` - Normalizes Ollama's returned book names

## Examples of Supported Formats

All of these will now correctly resolve to "MATTHEW":
- `MATTHEW`
- `Matthew`
- `ST. MATTHEW`
- `St. Matthew`
- `ST.MATTHEW`
- `StMatthew`
- `St Matthew` (without period)

## Test Results

✅ All tests pass:
- Testament detection with and without ST. prefix
- Greek text extraction with ST. prefix
- Hebrew text extraction (unchanged)
- Chapter-spanning notation
- Verse ranges and lists

## Files Modified

1. **get_md.py**:
   - Added `normalize_book_name()` function
   - Updated `is_new_testament()` and `is_old_testament()`
   - Updated all USFM lookup functions
   - Enhanced `BOOK_NAME_TO_GREEK_USFM` mapping
   - Updated validation functions

2. **test_greek_extraction.py**:
   - Added tests for ST. prefix handling
   - Tests for various prefix formats

## Usage

No changes required in your workflow! The script now automatically handles ST. prefixes transparently:

```python
# These all work identically now:
get_greek_verse("Matthew", 1, "1")
get_greek_verse("ST. MATTHEW", 1, "1")
get_greek_verse("St. Matthew", 1, "1")

# Testament detection also works:
is_new_testament("ST. JOHN")  # Returns True
is_new_testament("John")       # Returns True
```

## Impact

This fix ensures that:
- OCR extraction from commentaries with "ST." prefixes works correctly
- Greek text is properly extracted for NT books regardless of prefix
- Metadata validation handles prefixed names correctly
- Bible structure validation works with prefixed names
