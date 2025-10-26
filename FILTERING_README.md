# Image Filtering by Book and Chapter

The `read_images.py` script now supports filtering images by book name and chapter range using command-line arguments.

## Requirements

- Each image must have a corresponding `*_metadata.json` file
- Metadata file should contain: `book_name`, `chapter`, `verse`, `page_number`
- Images without metadata files will be automatically skipped

## Command-Line Options

```
--book, -b          Filter by book name (case-insensitive, e.g., Genesis, Exodus)
--chapter-start     Starting chapter number (inclusive)
--chapter-end       Ending chapter number (inclusive)
--directory, -d     Directory containing images (default: ./extracted_images)
```

## Usage Examples

### Process all images with metadata
```bash
python read_images.py
```

### Process only Genesis images
```bash
python read_images.py --book Genesis
```
or
```bash
python read_images.py -b Genesis
```

### Process Genesis chapters 1-3
```bash
python read_images.py --book Genesis --chapter-start 1 --chapter-end 3
```

### Process only chapter 5 (any book)
```bash
python read_images.py --chapter-start 5 --chapter-end 5
```

### Process from chapter 10 onwards (any book)
```bash
python read_images.py --chapter-start 10
```

### Process up to chapter 5 (any book)
```bash
python read_images.py --chapter-end 5
```

### Process Exodus chapters 20-40
```bash
python read_images.py -b Exodus -cs 20 -ce 40
```

## Output Display

When filters are applied, the script shows:

```
============================================================
FILTER APPLIED:
  Book: Genesis
  Chapters: 1 to 3
============================================================

Found 248 total images
Skipped 0 images without metadata
Skipped 220 images not matching filters
Processing 28 images

============================================================
Processing: page100_image1.png
Book: GENESIS, Chapter: 1, Verse: 31
============================================================
```

## Metadata File Format

Expected metadata file format (e.g., `page100_image1_metadata.json`):

```json
{
  "book_name": "GENESIS",
  "chapter": 1,
  "verse": "31",
  "page_number": 12,
  "hebrew_text": {
    "31": "..."
  }
}
```

## Notes

- Book names are case-insensitive (Genesis, GENESIS, genesis all work)
- Images without metadata files are automatically skipped (not processed)
- If no filters are specified, all images with metadata will be processed
- Chapter ranges are inclusive (both start and end chapters are processed)
- You can specify just `--chapter-start` or just `--chapter-end` for open-ended ranges
