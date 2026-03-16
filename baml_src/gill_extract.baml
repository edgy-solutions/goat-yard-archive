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

  Unknown             // Use ONLY for UNRESOLVED_PRONOUNs
}

// 2. The Entity Structure
// 👇 NEW: Helper Enum for Disambiguation
enum BiblicalEra {
  OldTestament
  NewTestament
  Intertestamental
  ChurchHistory
  NotApplicable
}

class GillEntity {
  name string @description("The entity name as it appears")
  category EntityCategory @description("The category this entity belongs to")
  
  // 👇 CRITICAL FOR DISAMBIGUATION (The "Joseph" Fix)
  biblical_era BiblicalEra @description("If a person, which era do they belong to? Use NotApplicable for concepts.")
  role string? @description("Specific role to distinguish same-named figures (e.g., 'Patriarch', 'Apostle', 'Husband of Mary').")

  normalized_name string? @description("Normalize: 'Christ' -> 'Jesus Christ'. For 'Joseph', leave as 'Joseph' and let era/role disambiguate.")
  description string? @description("A short 5-10 word context.")
}

// 👇 NEW: Wrapper Class to catch Scripture Links
class ExtractionResult {
  entities GillEntity[]
  cross_references string[] @description("List of other Bible verses referenced in this text, normalized to 'BOOK_CH_VS' (e.g., 'ISA_53_06').")
}

// 3. The Extraction Function
function ExtractGillKnowledge(commentary_text: string, previous_entities: string?) -> ExtractionResult {
  client OpenRouterText
  
  prompt #"
    Analyze this commentary by John Gill. Extract key entities and scripture references.
    
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
    
    **DISAMBIGUATION INSTRUCTIONS:**
    - For common names (Mary, Joseph, John, James, Saul), you MUST fill the 'biblical_era' and 'role' fields accurately.
    - Example: "Joseph was sold" -> era: OldTestament, role: "Patriarch/Son of Jacob"
    - Example: "Joseph took the child" -> era: NewTestament, role: "Husband of Mary"
    - **INTRA-ERA COLLISIONS:** If a name refers to multiple people in the SAME era (e.g. multiple Zechariahs in OT, multiple Marys in NT), you MUST specify their distinct identity in the 'role' field.
      - BAD: name="Zechariah", role="Biblical Figure"
      - GOOD: name="Zechariah", role="Prophet / Son of Berechiah"
      - GOOD: name="Zechariah", role="Priest / Son of Jehoiada"
    - **WATCH FOR TYPOLOGY:** Gill frequently compares OT figures to NT figures. If he mentions "Joseph" (NT) inside a commentary on "Joseph" (OT), extract them as TWO SEPARATE entities.

    **CRITICAL RULE: SCRIPTURE CITATIONS VS. ENTITIES**
    Gill frequently abbreviates Bible books (e.g., "Rom. i. 4", "Mark xvi. 11").
    
    1. **CHECK THE PATTERN:** Does the "Name" look like a book abbreviation followed by numbers (Roman or Digit)?
       - "Rom. i. 4" -> This is a CITATION.
       - "Mark xvi. 11" -> This is a CITATION.
       - "Mark" (alone) -> This is a BIBLICAL FIGURE.
       
    2. **THE ACTION:** - If it is a CITATION: Add it to the 'cross_references' list. **DO NOT** create a GillEntity for it.
       - If it is a PERSON: Create a GillEntity with category 'BiblicalFigure'.
       
    **Ambiguity Check:** "Mark" is a person. "Mark xvi." is a book. Distinguish them by looking for the chapter numbers immediately following.

    **SCRIPTURE REFERENCES:**
    - Extract any direct bible verses Gill cites to support his argument.
    - Normalize them to the format: BOOK_CHAPTER_VERSE (e.g., MAT_03_16).
    
    **PRONOUN RESOLUTION:**
    If the text relies on pronouns ('he', 'they', 'the king') rather than explicit names, review the `previous_entities` list provided below.
    - If context clearly aligns the pronoun with a previous entity, extract that specific name.
    - **IF AND ONLY IF** you cannot confidently resolve the pronoun using the provided context, return the exact string "UNRESOLVED_PRONOUN" as the `name` of a Theological Entity.
    
    Previous Entities (Context Hint):
    {{ previous_entities }}

    Commentary Text:
    {{ commentary_text }}
    
    {{ ctx.output_format }}
  "#
}
