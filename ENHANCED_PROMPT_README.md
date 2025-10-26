# Enhanced Prompt with Context

The `read_images.py` script now uses the same prompt as defined in the BAML configuration (`ExtractTextFromImage`), with additional contextual information to significantly improve extraction accuracy.

## What's Included in the Prompt

### 1. **Base Instructions** (from BAML)
Extract the text from the image in markdown format with specific handling for:
- **Multilingual text**: Greek, Hebrew, and Arabic (especially in footnotes)
- **Footnote linking**: Connect footnotes to their references in the text
- **Two-column layout**: Handle hyphenation across columns
- **Footnote lettering**: Lower case letters only, can be duplicated across paragraphs

### 2. **OCR Context** (conditional)
If an OCR `.md` file exists, the prompt explains its purpose:
- Use ONLY for word-for-word accuracy
- OCR often misses footnote lettering
- OCR struggles with non-English languages (use image instead)

### 3. **Hebrew Context** (conditional)
If Hebrew verses are available:
- Original Hebrew verses are provided as reference
- Model should match Hebrew letter order as shown in image

### 4. **Metadata**
Automatically included from the `*_metadata.json` file:
- **Book name**: e.g., GENESIS, EXODUS
- **Chapter number**: e.g., 1, 2, 3
- **Verse(s)**: e.g., "31", "1-3", "27:42-46,28:1"
- **Page number**: e.g., 12, 13

### 5. **Original Hebrew Verses** (if available)
The actual Hebrew verses for the page from the metadata file.

### 6. **OCR Output** (if available)
The complete OCR markdown content for reference.

## Example Enhanced Prompt

```
Extract the text from the image in markdown format. Some words might be in Greek, Hebrew or Arabic, especially in footnotes, please include these words in their proper language. Please link the footnote to its place in the text. Be careful to notice that the page has two columns and thus the text and footnotes might be hyphenated from one column to the other. Also the footnotes ONLY use lower case lettering. There can be duplicate footnote letters when they are reused in the different paragraphs.

The output of an OCR tool is attached below and should be ONLY used to maintain accuracy in matching the original word for word since it gets some words wrong. The OCR often fails to detect the footnote lettering. OCR also struggles with the languages so use the image for those.

Original Hebrew verse the commentary is referring to is provided as a reference to use the Hebrew in the text is properly interpreted. Please match the Hebrew letter order as it is in the image and reference.

=== METADATA ===
Book: GENESIS
Chapter: 1
Verse(s): 31
Page Number: 12

=== ORIGINAL HEBREW VERSES ===
Verse 31: וַיַּ֤רְא אֱלֹהִים֙ אֶת־כָּל־אֲשֶׁ֣ר עָשָׂ֔ה וְהִנֵּה־טֹ֖וב מְאֹ֑ד וֽ͏ַיְהִי־עֶ֥רֶב וֽ͏ַיְהִי־בֹ֖קֶר יֹ֥ום הַשִּׁשִּֽׁי׃ פ

=== OCR OUTPUT (For Reference Only) ===
[OCR markdown content here]
```

## Benefits

### **Improved Accuracy**
- The model knows exactly what content to expect
- Hebrew text provides verification of verse numbers and content
- OCR reference helps with ambiguous characters

### **Better Context Understanding**
- Book and chapter information helps the model understand the biblical context
- Verse numbers help identify where content should start/end
- Page numbers provide additional verification

### **Handling Edge Cases**
- Chapter-spanning pages (e.g., "27:42-46,28:1") are clearly indicated
- Footnotes that span columns are better handled with OCR reference
- Complex layouts with multiple languages benefit from Hebrew context

### **Quality Control**
- Easier to verify extraction accuracy
- Hebrew text can be used to validate verse identification
- OCR provides a baseline for comparison

## File Requirements

For maximum benefit, ensure each image has:

1. **Required**: `*_metadata.json` - Contains book, chapter, verse, page, and Hebrew text
2. **Optional**: `*.md` - Previous OCR extraction for reference

Example file structure:
```
page100_image1.png
page100_image1_metadata.json
page100_image1.md
```

## Token Usage Impact

**Note**: Including metadata and OCR will increase prompt token count:
- Metadata adds: ~50-100 tokens
- Hebrew text adds: ~50-200 tokens per verse
- OCR markdown adds: ~500-2000 tokens depending on page length

This typically increases cost by $0.0001-$0.0005 per image but significantly improves accuracy, especially for complex pages.

## How It Works

The script automatically:
1. Loads metadata from `*_metadata.json`
2. Extracts Hebrew verses from the metadata
3. Looks for matching `.md` file
4. Constructs an enhanced prompt with all available context
5. Sends to the vision model

No configuration needed - it just works!
