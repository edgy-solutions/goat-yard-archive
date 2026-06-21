// BAML Schema for Query Expansion and Routing
// Translates modern user queries into Gill-friendly theological terms

class OptimizedQuery {
    expanded_search_terms string @description("A rich search string combining the user's modern terms with 18th-century theological synonyms John Gill would use (e.g., 'Christophany' -> 'Angel of the Lord, divine appearance').")
    official_entities string[] @description("A list of official graph entities mapped from the query based on the provided manifest. Return an empty list if none match.")
}

function OptimizeSearchQuery(user_query: string, available_entities: string[]) -> OptimizedQuery {
  client LocalRouter
  prompt #"
    You are a theological search translator for the John Gill Archive (18th-century Calvinist/Baptist theology).
    The user asked: {{ user_query }}
    
    1. **QUERY EXPANSION**: Expand their modern search terms into 18th-century synonyms that John Gill would likely use in his commentary.
       - Example: 'Christophany' -> 'The Angel of the Lord, appearance of the Son of God, divine manifestation'
       - Example: 'Rapture' -> 'The coming of Christ, the gathering of the saints, the resurrection'
       - **Names of biblical figures the scripture leaves unnamed** (the two thieves
         crucified with Jesus, the Magi, the rich man in Lazarus's parable, etc.):
         expand toward 'tradition,' 'Papist tradition,' 'named in tradition,' 'feast day,'
         'catalogue of saints,' and include known traditional names if you can recall them.
         Example: 'Names of the two thieves' -> 'Disma, Dysmas, penitent thief,
         Papist tradition, named in tradition, catalogue of saints, feast day'.
    
    2. **ENTITY MAPPING**: Map their concepts to these official database entities if applicable:
    {{ available_entities }}
  
    {{ ctx.output_format }}

    CRITICAL: You must output ONLY the raw JSON object. Do not include any markdown formatting (` ```json `), do not include any preamble, and do not include any explanations. Start immediately with { and end with }.
  "#
}
