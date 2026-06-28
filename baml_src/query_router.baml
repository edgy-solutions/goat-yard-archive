// BAML Schema for Query Expansion and Routing
// Translates modern user queries into Gill-friendly theological terms

class OptimizedQuery {
    expanded_search_terms string @description("A rich search string that MUST begin with the user's original query verbatim, then add 18th-century theological synonyms John Gill would use, comma-separated. Example: input 'Christophany' -> output 'Christophany, The Angel of the Lord, appearance of the Son of God, divine manifestation'. Example: input 'singing psalms' -> output 'singing psalms, psalmody, vocal music in worship, the Hallel, psalms and hymns'.")
    official_entities string[] @description("A list of official graph entities mapped from the query based on the provided manifest. Return an empty list if none of the offered entities match the query's subject.")
}

function OptimizeSearchQuery(user_query: string, available_entities: string[]) -> OptimizedQuery {
  client LocalRouter
  prompt #"
    You are a theological search translator for the John Gill Archive (18th-century Calvinist/Baptist theology).

    YOUR JOB has two parts:

    1. **QUERY EXPANSION**: Expand the user's modern search terms into 18th-century synonyms that John Gill would likely use in his commentary. The expansion MUST begin with the user's original query verbatim, then add synonyms separated by commas.
       - Example: input 'Christophany' -> output 'Christophany, The Angel of the Lord, appearance of the Son of God, divine manifestation'
       - Example: input 'Rapture' -> output 'Rapture, the coming of Christ, the gathering of the saints, the resurrection'
       - Example: input 'singing psalms' -> output 'singing psalms, psalmody, vocal music in worship, the Hallel, psalms and hymns'
       - **Names of biblical figures the scripture leaves unnamed.** This rule
         applies ONLY when the user is asking for a *name* the *Bible itself
         does not give* — for example: the two thieves crucified with Jesus,
         the Magi, the rich man in Lazarus's parable, the Pharaoh of the
         Exodus, the Samaritan woman at the well. For these, expand toward
         'tradition,' 'Papist tradition,' 'named in tradition,' 'feast day,'
         'catalogue of saints,' and include known traditional names if you
         can recall them.
         Example: input 'Names of the two thieves' -> output 'Names of the two thieves, Disma, Dysmas, penitent thief, Papist tradition, named in tradition, catalogue of saints, feast day'.

         This rule does NOT apply to:
           * Named historical figures (Aquinas, Augustine, Calvin, Luther,
             Bellarmine). They already have names; the user is asking about
             their views, not their identity. Expand using their actual
             theological vocabulary, not 'Papist tradition.'
           * Modern doctrinal labels or technical theological terms
             (exclusive psalmody, monocovenantal, supralapsarianism,
             paedobaptism). They are not figures at all. Expand using
             period-equivalent doctrinal vocabulary Gill would use.

    2. **ENTITY MAPPING**: Map the user's concepts to whichever of these official database entities match the query's subject. Return an empty list ONLY if none of the offered entities match the subject; do not return an empty list as a way to opt out of the task.
    {{ available_entities }}

    {{ ctx.output_format }}

    FORMAT: Output ONLY the raw JSON object. Do not include any markdown formatting (` ```json `), do not include any preamble, and do not include any explanations. Start immediately with { and end with }.

    The user's query to expand is below. Expand THIS text, and map THIS query's subject to the entities listed above:
    <query>{{ user_query }}</query>
  "#
}
