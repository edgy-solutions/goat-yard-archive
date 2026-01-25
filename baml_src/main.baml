// BAML configuration for OCR metadata validation with Ollama

// Define the metadata structure
class Metadata {
  book_name string? @description("The book name found at the top center of the image")
  chapter int? @description("The chapter number (converted from Roman numerals to decimal). For chapter-spanning pages, this is the first chapter.")
  verse string? @description("The verse number, range (e.g. '1-3'), list (e.g. '1,2,3'), or chapter-spanning notation")
  page_number int? @description("The page number found at top left or top right")
  no_verse_markers bool? @description("Set to true ONLY if there are NO verse (Ver.) markers on this page except in header.")
}

// Define the extracted text structure for OpenRouter
class ExtractedText {
  text string @description("The extracted text from the image")
}

// Define the Ollama client using OpenAI-compatible endpoint
client<llm> Ollama {
  provider openai
  options {
    model "qwen2.5vl:32b"
    base_url "http://192.168.1.188:11434/v1"
    api_key "ollama"
    temperature 0.1
    options: {
      num_ctx: 2048
    }
  }
}

// Define the Ollama client for oss-gpt:20b (text normalization)
client<llm> OllamaGPT {
  provider openai
  options {
    model "qwen3-8k:32b"
    base_url "http://192.168.1.188:11434/v1"
    api_key "ollama"
    temperature 0.1
  }
}

// Define the OpenRouter client
client<llm> OpenRouter {
  provider openai
  options {
    base_url "https://openrouter.ai/api/v1"
    api_key env.OPENROUTER_API_KEY
    model "qwen/qwen3-vl-235b-a22b-thinking"
  }
}

// Define the OpenRouter client for text-only tasks
client<llm> OpenRouterText {
  provider openai
  options {
    base_url "https://openrouter.ai/api/v1"
    api_key env.OPENROUTER_API_KEY
    model "x-ai/grok-4.1-fast"
  }
}

// Define the validation function
function ValidateOCRMetadata(
  image: image,
  ocr_metadata: Metadata,
  body_verses: string?
) -> Metadata {
  client Ollama
  
  prompt #"
    Please check the OCR metadata returned below for accuracy in the reported page number, book, chapter and verse this image is referring to. These will all be found at the top of the image. The page number will be either on the top far left or top far right. The book will be in the top center. And the chapter and verse will be on the opposite side of the page number in the format of 'CH. <roman numeral chapter> V. <verse number, range or list>'. Numbers should be converted to decimal. Be careful to interpret numbers properly because the font used is curly and thus 2 is often confused for 9. Verses can also be derived from the references in the text body which look like 'Ver. <verse number>'.
    
    VERSE FORMATTING:
    - Single verse: "3"
    - Range: "3-5" (verses 3 through 5)
    - List: "3,4,5" (specific verses)
    - Chapter-spanning: "27:42-46,28:1" (verses 42-46 of chapter 27, then verse 1 of chapter 28)
    
    CHAPTER-SPANNING PAGES:
    Some pages span multiple chapters. The header will show two chapter markers:
    "CH. XXVII. V. 42-46. XXVIII. V. 1" should be formatted as "27:42-46,28:1"
    For chapter-spanning pages, set the chapter field to the FIRST chapter number (27 in this example).
    
    Current OCR Metadata:
    - Book: {{ ocr_metadata.book_name }}
    - Chapter: {{ ocr_metadata.chapter }}
    - Detected Header Verses: {{ ocr_metadata.verse }}
   {% if body_verses %}
    - Detected Body Verses: {{ body_verses }}
   {% endif %}
    - Page: {{ ocr_metadata.page_number }}
       
    Please review the image and provide the corrected metadata if any errors are found. If the OCR is correct, return the same values. Pay special attention to:
    1. Distinguishing between 2 and 9 in the curly font
    2. Correctly parsing chapter-spanning headers into the chapter:verse notation
    3. Ensuring the chapter field reflects the first chapter in chapter-spanning pages
    {% if body_verses %}
    4. Reconciling header range with detected body verses by using these body verses as a strong hint. 
      - If the header says "10-15" but body verses are exactly "10, 11, 12, 13" (and page layout suggests end of section), the header might be wrong or reading a smudge.
      - If the body verses are sequential and consistent, favor them over a mismatched header.
    {% endif %}
    
    {{ _.role("user") }}
    {{ image }}
    
    {{ ctx.output_format }}
  "#
}

// Define the image text extraction function for OpenRouter
function ExtractTextFromImage(
  image: image,
  book: string?,
  chapter: string?,
  verse: string?,
  page_number: string?,
  hebrew_text: string?,
  greek_text: string?,
  ocr_text: string?
) -> string {
  client OpenRouter
  
  prompt #"
    Extract the text from the image in markdown format. Some words might be in Greek, Hebrew or Arabic, especially in footnotes, please include these words in their proper language. Please link the footnote to its place in the text.
    
    IMPORTANT: The image has TWO COLUMNS but you must MERGE them into a SINGLE continuous text output. Read the left column completely from top to bottom first, then continue with the right column from top to bottom. Handle text that is hyphenated from one column to the other by combining the hyphenated word. Do NOT preserve the two-column layout in your output - provide a single flowing text.
    
    FOOTNOTES: The footnotes ONLY use lower case lettering (a, b, c, etc.). There can be duplicate footnote letters when they are reused in different paragraphs. Include all footnotes at the end of their respective paragraph or section, properly linked with their lowercase letter markers.
    
    {% if ocr_text %}
    The output of an OCR tool is attached below and should be ONLY used to maintain accuracy in matching the original word for word since it gets some words wrong. The OCR often fails to detect the footnote lettering. OCR also struggles with the languages so use the image for those.
    {% endif %}
    
    {% if hebrew_text %}
    Original Hebrew verse the commentary is referring to is provided as a reference to ensure the Hebrew in the text is properly interpreted. Please match the Hebrew letter order as it is in the image and reference.
    {% endif %}
    
    {% if greek_text %}
    Original Greek verse the commentary is referring to is provided as a reference to ensure the Greek in the text is properly interpreted. Please match the Greek letter order as it is in the image and reference.
    {% endif %}
    
    {% if book or chapter or verse or page_number %}
    
    === METADATA ===
    {% if book %}Book: {{ book }}
    {% endif %}{% if chapter %}Chapter: {{ chapter }}
    {% endif %}{% if verse %}Verse(s): {{ verse }}
    {% endif %}{% if page_number %}Page Number: {{ page_number }}
    {% endif %}{% endif %}
    
    {% if hebrew_text %}
    
    === ORIGINAL HEBREW VERSES ===
    {{ hebrew_text }}
    {% endif %}
    
    {% if greek_text %}
    
    === ORIGINAL GREEK VERSES ===
    {{ greek_text }}
    {% endif %}
    
    {% if ocr_text %}
    
    === OCR OUTPUT (For Reference Only) ===
    {{ ocr_text }}
    {% endif %}
    
    {{ _.role("user") }}
    {{ image }}
  "#
}

// Define the verse chunk structure for alignment
class VerseChunk {
  verse_ref string @description("Standardized verse reference, e.g., 'MAT 03:16'. Use 3-letter book codes (GEN, EXO, MAT, etc.)")
  start_phrase string @description("Unique starting phrase of the commentary for this verse (approx 5-10 words). Must be verbatim from the text.")
  end_phrase string @description("Unique ending phrase of the commentary for this verse (approx 5-10 words). Must be verbatim from the text.")
}

// Define the verse extraction function
function ExtractVersesFromMarkdown(
  markdown_text: string
) -> VerseChunk[] {
  client OpenRouterText
  
  prompt #"
    Analyze the following commentary text and split it into verse chunks. Each chunk corresponds to a specific verse reference (e.g., "Ver. 1.", "Ver. 2.").
    
    CRITICAL: You must extract EVERY single verse found in the text. Do not skip any.
    
    - Look for explicit markers like "Ver. 31."
    - If there is text before the first explicit marker that belongs to a previous verse, extract it as a separate chunk and infer the verse reference (e.g., if "Ver. 31" follows, the previous text is likely "Ver. 30").
    - Do not stop after the first verse. Process the entire text.
    
    For each verse chunk:
    1. Identify the verse reference. Convert it to a standardized format (e.g., "GEN 01:01").
    2. Extract the first 10-15 words IMMEDIATELY after the verse marker (e.g., "Ver. 31.") as the `start_phrase`. This often includes the QUOTED VERSE TEXT (which may be in italics or marked with * or brackets) followed by commentary. DO NOT skip the verse quotation.
    3. Extract the last 10-15 words of the commentary text for that verse as the `end_phrase`.
    
    CRITICAL: The `start_phrase` and `end_phrase` MUST be EXACT substrings from the provided text. Do not paraphrase or modify them. They will be used for fuzzy matching against the original OCR data.
    
    If a chunk covers multiple verses (e.g., "Ver. 4, 5."), create a separate entry for each verse if possible, or one entry with the combined range if the text is merged. Ideally, split them if the text clearly delineates them. If the text is a single block for multiple verses, use the range in the ref (e.g., "GEN 01:04-05").
    
    Input Text:
    {{ markdown_text }}
    
    {{ _.role("user") }}
    Extract the verse chunks.
    
    {{ ctx.output_format }}
  "#
}

// Define the markdown normalization function for John Gill Commentary
function NormalizeGillMarkdown(raw_markdown: string) -> string {
  client OllamaGPT
  
  prompt #"
    You are a specialized theological editor responsible for formatting John Gill's Bible Commentary.
    
    Objective: Normalize the raw OCR text into clean, structured Markdown while strictly preserving the 18th-century stylistic conventions (specifically the Verse Lemma format).
    
    Input: Raw Markdown text derived from OCR/Vision models (which may contain page headers, varying footnote markers, and layout artifacts).
    Output: Clean, consistent Markdown ready for database ingestion.
    
    === 1. STRUCTURAL RULES (STRICT) ===
    
    A. Remove ONLY Metadata Headers (at the very top of the page):
    - Page numbers (e.g., "90", "page 90")
    - Book/chapter markers like "GENESIS", "CH. I. V. 3"
    - These are typically short lines at the very beginning, NOT part of the commentary.
    
    B. PRESERVE ALL Commentary Text:
    - CRITICAL: Text that starts mid-sentence (spillover from previous page) MUST be preserved.
    - Example: If the file starts with "triarchs: but yet such a variety..." this is continuation text from the previous page and MUST be kept.
    - Only remove obvious page metadata, never remove actual commentary content.
    
    C. Chapter Headings:
    - Format Chapter starts as a standard Markdown Header 1.
    - Input: **CHAP. I.** or CHAP. 1.
    - Output: # Chapter 1
    
    D. Verse Commentary (The Lemma Style):
    - Constraint: Do NOT use ### Verse 3. Keep the archaic format.
    - Format: Start every verse commentary on a new line with the exact pattern: Ver. {number}.
    - Normalization:
      - If input is V. 6., change to Ver. 6.
      - If input is Verse 6., change to Ver. 6.
      - If input is Ver 6, change to Ver. 6. (ensure periods are present).
    - The Lemma: Ensure the bracketed lemma text follows immediately.
      - Example: Ver. 6. And Jesus went, &c.]
    
    E. Paragraphs:
    - Remove excessive newlines. Paragraphs should be separated by a single blank line.
    
    === 2. FOOTNOTE NORMALIZATION RULES (CRUCIAL) ===
    
    The raw text uses inconsistent markers (e.g., ^a^, ᵃ, (1), *, †, <sup>). You must standardize them to Markdown.
    
    CRITICAL: Do NOT invent or add new footnote markers. Only normalize markers that ALREADY EXIST in the original text.
    
    A. In-Text Markers:
    - Convert EXISTING footnote markers in the body text to standard numerical Markdown citations: [^1], [^2], [^3].
    - Number them sequentially starting from 1 for the page.
    - Example: "...as Aben Ezra observes^a^" → "...as Aben Ezra observes[^1]"
    - If there is NO footnote marker in the original (e.g., "Aben Ezra observes" with no ^a^ or superscript), do NOT add one.
    
    B. Footnote Definitions:
    - Move ALL footnote definitions to the very bottom of the text.
    - Format them as: [^1]: {Content}
    - Matching: You must intelligently match the in-text marker to the correct definition based on context or the original marker symbol (e.g., if text has ^a^ and footer has a Vid. Josephus, link them as [^1]).
    - Formatting: Remove the original marker letters (a, b, *) from the definition text.
      - Bad: [^1]: a Vid. Josephus...
      - Good: [^1]: Vid. Josephus...
    - New section markers should start with letter 'a' unless the conversion interpreted them wrong. Spill over markers will follow the lettering order from the previous page potentially resulting in duplicate letters. BE CAREFUL to match them correctly.
    
    === 3. CONTENT INTEGRITY RULES ===
    
    - Hebrew/Greek: NEVER alter or remove Hebrew, Greek, or Arabic text. Keep it exactly as is.
    - Italics: Ensure Bible quotations or emphasized words use *asterisks* (not _underscores_).
    - Spelling: Do not modernize 18th-century spelling (e.g., "shewn", "hath")
    - Spillover Text: ALWAYS preserve text that continues from a previous page, even if it starts mid-sentence.
    
    {{ _.role("user") }}
    
    Please normalize the following raw OCR markdown:
    
    {{ raw_markdown }}
  "#
}
