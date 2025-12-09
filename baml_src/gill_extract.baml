// BAML Schema for Gill Knowledge Graph Entity Extraction

// 1. Define the Categories for the Knowledge Graph
enum EntityCategory {
  // Theology
  Doctrine            // e.g., Justification, Election
  Heresy              // e.g., Socinianism, Sabellianism
  TypeOrSymbol        // e.g., The Rock, Scarlet Thread

  // Persons (Granular)
  BiblicalFigure      // e.g., Abraham, Moses, Peter
  HistoricalFigure    // e.g., Alexander the Great, Nero
  CitedAuthority      // e.g., Josephus, R. Solomon Jarchi, Maimonides
  PeopleGroup         // e.g., Pharisees, Chaldeans

  // Context
  Location            // e.g., Canaan, River Jordan, Ephesus
  TimePeriod          // e.g., "The 70th Week", "Reign of Tiberius"
  
  // Scholarship
  OriginalWord        // Hebrew/Greek words defined (e.g., "Sheol", "Logos")
  ManuscriptOrVersion // e.g., Septuagint, Vulgate, Targum
}

// 2. The Entity Structure
class GillEntity {
  name string @description("The entity name as it appears in the text")
  category EntityCategory @description("The category this entity belongs to")
  normalized_name string? @description("Normalize variations (e.g., 'Christ' -> 'Jesus Christ', 'the Lord' -> 'Jesus Christ')")
}

// 3. The Extraction Function
function ExtractGillKnowledge(commentary_text: string) -> GillEntity[] {
  client OpenRouterText
  
  prompt #"
    Analyze the following commentary by John Gill and extract key entities to build a Knowledge Graph.
    
    **CRITICAL DISTINCTIONS:**
    - 'BiblicalFigure': People who appear IN the Bible narrative (Abraham, Moses, Peter, Jesus, etc.)
    - 'CitedAuthority': Scholars, Rabbis, or historians that GILL QUOTES (Josephus, Maimonides, Jerome, etc.)
    - 'OriginalWord': Hebrew or Greek words that Gill defines or explains (mark the transliterated word)
    - 'Location': Physical places mentioned
    - 'TimePeriod': Historical periods or eras
    - 'Doctrine': Theological concepts (Justification, Election, Trinity, etc.)
    - 'Heresy': False teachings Gill refutes
    - 'TypeOrSymbol': Biblical types/symbols (The Rock = Christ, Manna = Word of God, etc.)
    - 'HistoricalFigure': Non-biblical historical persons mentioned
    - 'PeopleGroup': Ethnic or religious groups (Pharisees, Sadducees, Chaldeans, etc.)
    - 'ManuscriptOrVersion': Biblical manuscripts or versions (Septuagint, Vulgate, Targum, etc.)
    
    **NORMALIZATION RULES:**
    - For Jesus: Normalize "Christ", "the Lord", "our Saviour" -> "Jesus Christ"
    - For God: Normalize "the Lord", "Jehovah", "the Almighty" -> "God"
    - For locations: Use standard names (e.g., "the land of Canaan" -> "Canaan")
    - For cited authorities: Include title if mentioned (e.g., "R. Solomon Jarchi", "Josephus")
    
    **IMPORTANT:**
    - Only extract entities that are EXPLICITLY mentioned in the text
    - Do NOT extract pronouns or generic references unless they can be clearly resolved
    - For OriginalWord, extract the transliterated Hebrew/Greek, not the English translation
    
    Commentary Text:
    {{ commentary_text }}
    
    {{ ctx.output_format }}
  "#
}
