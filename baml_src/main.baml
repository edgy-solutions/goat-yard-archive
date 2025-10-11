// BAML configuration for OCR metadata validation with Ollama

// Define the metadata structure
class Metadata {
  book_name string? @description("The book name found at the top center of the image")
  chapter int? @description("The chapter number (converted from Roman numerals to decimal)")
  verse string? @description("The verse number, range (e.g. '1-3'), or list (e.g. '1,2,3')")
  page_number int? @description("The page number found at top left or top right")
}

// Define the Ollama client using OpenAI-compatible endpoint
client<llm> Ollama {
  provider openai
  options {
    model "gemma3:27b"
    base_url "http://192.168.1.188:11434/v1"
    api_key "ollama"
    temperature 0.1
  }
}

// Define the validation function
function ValidateOCRMetadata(
  image: image,
  ocr_metadata: Metadata
) -> Metadata {
  client Ollama
  
  prompt #"
    Please check the OCR metadata returned below for accuracy in the reported page number, book, chapter and verse this image is referring to. These will all be found at the top of the image. The page number will be either on the top far left or top far right. The book will be in the top center. And the chapter and verse will be on the opposite side of the page number in the format of 'CH. <roman numeral chapter> V. <verse number, range or list>'. Numbers should be converted to decimal. Be careful to interpret numbers properly because the font used is curly and thus 2 is often confused for 9.
    
    Current OCR Metadata:
    - Book: {{ ocr_metadata.book_name }}
    - Chapter: {{ ocr_metadata.chapter }}
    - Verse: {{ ocr_metadata.verse }}
    - Page: {{ ocr_metadata.page_number }}
    
    Please review the image and provide the corrected metadata if any errors are found. If the OCR is correct, return the same values.
    
    {{ _.role("user") }}
    {{ image }}
    
    {{ ctx.output_format }}
  "#
}
