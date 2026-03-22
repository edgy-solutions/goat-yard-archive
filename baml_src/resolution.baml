// BAML Schema for Page Boundary Pronoun Resolution
// Resolves "He"/"They" across physical page splits by looking at previous context

class ResolvedPronoun {
    resolved_entity_names string[] @description("The actual names of the entities that the pronoun refers to, selected strictly from the previous_entities list.")
}

function ResolveBoundaryPronouns(unresolved_text: string, previous_text: string, previous_entities: string[]) -> ResolvedPronoun {
  client OpenRouterText
  prompt #"
    You are an expert in John Gill's 18th-century theological writings.
    We have a text chunk that starts with an unresolved pronoun (like "He", "They", or "The Apostle") because it was split across a physical page boundary.
    
    PREVIOUS PAGE CONTEXT:
    {{ previous_text }}
    
    ENTITIES MENTIONED ON PREVIOUS PAGE:
    {{ previous_entities }}
    
    CURRENT TEXT (STARTS WITH PRONOUN):
    {{ unresolved_text }}
    
    Identify who the pronouns in the CURRENT TEXT are referring to, based on the PREVIOUS PAGE CONTEXT.
    Return ONLY the exact entity names from the provided list. If none match, return an empty list.
    {{ ctx.output_format }}
  "#
}
