// BAML configuration for OCR metadata validation with Ollama

// Define the metadata structure
class Metadata {
  book_name string? @description("The book name found at the top center of the image")
  chapter int? @description("The chapter number (converted from Roman numerals to decimal). For chapter-spanning pages, this is the first chapter.")
  verse string? @description("The verse number, range (e.g. '1-3'), list (e.g. '1,2,3'), or chapter-spanning notation (e.g. '27:42-46,28:1' for verses 42-46 of chapter 27 and verse 1 of chapter 28)")
  page_number int? @description("The page number found at top left or top right")
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

// Define the OpenRouter client
client<llm> OpenRouter {
  provider openai
  options {
    base_url "https://openrouter.ai/api/v1"
    api_key env.OPENROUTER_API_KEY
    model "qwen/qwen3-vl-235b-a22b-thinking"
  }
}

// Define the validation function
function ValidateOCRMetadata(
  image: image,
  ocr_metadata: Metadata
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
    - Verse: {{ ocr_metadata.verse }}
    - Page: {{ ocr_metadata.page_number }}
    
    Please review the image and provide the corrected metadata if any errors are found. If the OCR is correct, return the same values. Pay special attention to:
    1. Distinguishing between 2 and 9 in the curly font
    2. Correctly parsing chapter-spanning headers into the chapter:verse notation
    3. Ensuring the chapter field reflects the first chapter in chapter-spanning pages
    
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
    Original Hebrew verse the commentary is referring to is provided as a reference to use the Hebrew in the text is properly interpreted. Please match the Hebrew letter order as it is in the image and reference.
    {% endif %}
    
    {% if book or chapter or verse or page_number %}
    
    === METADATA ===
    {% if book %}Book: {{ book }}{% endif %}
    {% if chapter %}Chapter: {{ chapter }}{% endif %}
    {% if verse %}Verse(s): {{ verse }}{% endif %}
    {% if page_number %}Page Number: {{ page_number }}{% endif %}
    {% endif %}
    
    {% if hebrew_text %}
    
    === ORIGINAL HEBREW VERSES ===
    {{ hebrew_text }}
    {% endif %}
    
    {% if ocr_text %}
    
    === OCR OUTPUT (For Reference Only) ===
    {{ ocr_text }}
    {% endif %}
    
    {{ _.role("user") }}
    {{ image }}
  "#
}
