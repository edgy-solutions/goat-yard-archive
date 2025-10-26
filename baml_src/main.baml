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
  image: image
) -> string {
  client OpenRouter
  
  prompt #"
    Please extract the original text from the image. Please extract it exactly as it is in the image. Do not change anything. Please make sure you keep the older English used in the image such as the use of 'nay' and all footnotes. Also notice that footnotes might extend from the left column to the right column if the left column footnote terminates with a dash. Also note that the text is mostly English but does contain Latin, Greek, Hebrew and Arabic especially in footnotes.
    
    {{ _.role("user") }}
    {{ image }}
  "#
}
