# USFM Markup Cleaning for Greek and Hebrew Text

## Problem
The Greek and Hebrew text in metadata files contained USFM markup and Strong's concordance numbers, making it difficult to read:

**Before:**
```json
{
  "greek_text": {
    "1": "\\w Βίβλος|strong=\"G0976\"\\w* \\w γενέσεως|strong=\"G1078\"\\w* \\w Ἰησοῦ|strong=\"G2424\"\\w* \\w Χριστοῦ|strong=\"G5547\"\\w*"
  }
}
```

## Solution
Added automatic USFM markup cleaning to extract only the actual Greek/Hebrew words.

**After:**
```json
{
  "greek_text": {
    "1": "Βίβλος γενέσεως Ἰησοῦ Χριστοῦ, υἱοῦ Δαβίδ, υἱοῦ Ἀβραάμ."
  }
}
```

### What Gets Removed
The `clean_usfm_text()` function removes:
- `\w` and `\w*` tags (USFM word markers)
- `|strong="G####"` annotations (Strong's concordance numbers)
- `|strong="H####"` annotations (for Hebrew)
- Extra whitespace

### What's Preserved
- All original language words (Greek/Hebrew)
- Punctuation (commas, periods, etc.)
- Word order and spacing

## Implementation

### New Function: `clean_usfm_text()`
```python
def clean_usfm_text(text):
    """
    Remove USFM markup and Strong's numbers from text, keeping only the actual words.
    
    Example:
        Input:  "\\w Βίβλος|strong=\"G0976\"\\w* \\w γενέσεως|strong=\"G1078\"\\w*"
        Output: "Βίβλος γενέσεως"
    """
```

### Integration
The cleaning is automatically applied in `parse_usfm_file()`, which is called by:
- `get_hebrew_verse()`
- `get_hebrew_verse_spanning()`
- `get_greek_verse()`
- `get_greek_verse_spanning()`

This means **all** Hebrew and Greek text extraction now returns clean text automatically.

## Files Modified

1. **get_md.py**:
   - Added `clean_usfm_text()` function
   - Updated `parse_usfm_file()` to clean verse text automatically

2. **Created test_usfm_cleaning.py**:
   - Tests USFM cleaning function
   - Verifies Greek extraction returns clean text
   - Verifies Hebrew extraction returns clean text

## Test Results

✅ All tests pass:
- Direct USFM cleaning function works correctly
- Greek text extraction (Matthew 1:1) - clean
- Hebrew text extraction (Genesis 1:1) - clean
- Mixed markup handling (some words with/without Strong's) - clean

## Updating Existing Metadata Files

**Important:** Existing metadata files will still have the old format with markup. To update them:

### Option 1: Regenerate Specific Files
Run `get_md.py` on the original images again:
```bash
python get_md.py <image_path>
```

### Option 2: Batch Update Script
If you have many files to update, you can create a script to:
1. Read each metadata.json file
2. Load the book/chapter/verse info
3. Re-extract the Greek/Hebrew text using the updated functions
4. Save the cleaned metadata

### Option 3: Process Only New Images
Simply continue processing new images - they will automatically have clean text.

## Benefits

1. **Cleaner Metadata**: Easier to read and use the Greek/Hebrew text
2. **Better for BAML**: The LLM receives clean text without technical markup
3. **Smaller Files**: Removing markup reduces JSON file size
4. **More Readable**: Humans can actually read the original language text
5. **Consistent Format**: All text uses the same clean format

## Example Usage

```python
# Extract clean Greek text
greek_verses = get_greek_verse("Matthew", 1, "1-3")
print(greek_verses["1"])
# Output: "Βίβλος γενέσεως Ἰησοῦ Χριστοῦ, υἱοῦ Δαβίδ, υἱοῦ Ἀβραάμ."

# Extract clean Hebrew text
hebrew_verses = get_hebrew_verse("Genesis", 1, "1")
print(hebrew_verses["1"])
# Output: "בְּרֵאשִׁ֖ית בָּרָ֣א אֱלֹהִ֑ים אֵ֥ת הַשָּׁמַ֖יִם וְאֵ֥ת הָאָֽרֶץ׃"
```

## Backward Compatibility

The changes are fully backward compatible:
- Old metadata files still work (they just have extra markup)
- New metadata files have clean text
- BAML processing works with both formats
- No changes needed to calling code
