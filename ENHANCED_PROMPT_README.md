# Enhanced Prompt with Context

The `read_images.py` script now includes rich contextual information in the prompt sent to the vision model, significantly improving extraction accuracy.

## What's Included in the Prompt

### 1. **Base Instructions**
The original extraction instructions for handling old English, footnotes, and multilingual text.

### 2. **Metadata Context**
Automatically included from the `*_metadata.json` file:
- **Book name**: e.g., GENESIS, EXODUS
- **Chapter number**: e.g., 1, 2, 3
- **Verse(s)**: e.g., "31", "1-3", "27:42-46,28:1"
- **Page number**: e.g., 12, 13

### 3. **Hebrew Text**
The actual Hebrew verses for the page from the metadata file. This helps the model:
- Verify it's extracting the correct verses
- Identify Hebrew characters or quotations in the English text
- Cross-reference content for accuracy

### 4. **OCR Preliminary Extraction**
If a matching `.md` file exists (from previous OCR), it's included as a reference. The model can use this to:
- Identify difficult-to-read or ambiguous text
- Verify uncertain characters
- Handle complex layouts more accurately
- **Note**: The model is instructed to prioritize the actual image over the OCR

## Example Enhanced Prompt

```
Please extract the original text from the image. Please extract it exactly as it is in the image. Do not change anything. Please make sure you keep the older English used in the image such as the use of 'nay' and all footnotes. Also notice that footnotes might extend from the left column to the right column if the left column footnote terminates with a dash. Also note that the text is mostly English but does contain Latin, Greek, Hebrew and Arabic especially in footnotes.

=== METADATA CONTEXT ===
Book: GENESIS
Chapter: 1
Verse(s): 31
Page Number: 12

=== HEBREW TEXT FOR THESE VERSES ===
Verse 31: וַיַּ֤רְא אֱלֹהִים֙ אֶת־כָּל־אֲשֶׁ֣ר עָשָׂ֔ה וְהִנֵּה־טֹ֖וב מְאֹ֑ד וֽ͏ַיְהִי־עֶ֥רֶב וֽ͏ַיְהִי־בֹ֖קֶר יֹ֥ום הַשִּׁשִּֽׁי׃ פ

Note: The Hebrew text above corresponds to the verses on this page. This can help verify the content and identify any Hebrew characters or quotations in the English text.

=== OCR PRELIMINARY EXTRACTION ===
Below is a preliminary OCR extraction of this image. Use it as a reference to help identify difficult-to-read text, but prioritize the actual image content for accuracy:

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
