// BAML Schema for Query Expansion and Routing

class OptimizedQuery {
    expanded_search_terms string @description("MUST begin with the user's original query verbatim, then a comma-separated list of 18th-century theological synonyms John Gill would use for the same subject. E.g. 'Rapture' -> 'Rapture, the coming of Christ, the gathering of the saints, the resurrection'.")
    official_entities string[] @description("Entities from the provided list whose subject matches the query. Empty list only if none genuinely match.")
}

function OptimizeSearchQuery(user_query: string, available_entities: string[]) -> OptimizedQuery {
  client LocalRouter
  prompt #"
    You translate a modern search query into terms John Gill (18th-c. Calvinist Baptist) would use in his commentary.

    Two tasks:
    1. EXPAND: restate the query verbatim, then add comma-separated 18th-century synonyms for the same subject.
    2. MAP: from the entity list below, return those whose subject matches the query (empty list only if none match).

    Examples:
    - 'Rapture' -> 'Rapture, the coming of Christ, the gathering of the saints, the resurrection'
    - 'keeping the sabbath' -> 'keeping the sabbath, the Lord's day, the Christian sabbath, sabbath rest, the fourth commandment'
    - For a person Scripture leaves unnamed (the Magi, the rich man in Lazarus's parable, Pharaoh's daughter), also add tradition terms. E.g. 'the Magi' -> 'the Magi, the wise men, the three kings, named in tradition, Gaspar Melchior Balthasar'. This applies ONLY to unnamed biblical figures — never to named people or to doctrines.

    Output only the raw JSON object, starting with { and ending with }. No markdown, no preamble.

    Map against these entities:
    {{ available_entities }}

    Expand and map THIS query:
    <query>{{ user_query }}</query>

    {{ ctx.output_format }}
  "#
}
