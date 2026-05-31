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

// -----------------------------------------------------------------------------
// Quote Repair (ADR-0006 follow-up): when verbatim verification fails on a
// model-produced quote (it paraphrased, added words, dropped words), find the
// substring of the source that the model was paraphrasing and return it
// verbatim. The bot then substitutes the verbatim text into the answer so the
// user sees Gill's actual words rather than the model's drift.
//
// This is the LLM-side fallback for the hybrid repair pipeline; difflib runs
// first for the simple cases (small word edits) and only ambiguous cases reach
// here. LocalRouter is used for speed/cost — the task is small and constrained.
// -----------------------------------------------------------------------------

class RepairedQuote {
    repaired_quote string? @description("The substring of the source text that the model was paraphrasing, returned VERBATIM with the source's original wording, punctuation, capitalization, and spelling. null if no clear correspondent passage exists in the source.")
}

function RepairQuote(model_quote: string, source_text: string) -> RepairedQuote {
    client LocalRouter
    prompt #"
        A theological commentary AI quoted a passage from John Gill's 18th-century commentary, but its quote has drifted from the verbatim source — the AI may have paraphrased a word, dropped a word, added a clarifying prefix, or stitched two non-contiguous fragments.

        Your job: identify the substring of the SOURCE TEXT that the AI was paraphrasing, and return that substring VERBATIM (character-for-character) as it appears in the source.

        STRICT RULES:
        - The repaired_quote must be a verbatim substring of the SOURCE TEXT. Do not add, remove, or substitute any characters.
        - Do not modernize spelling. Preserve archaic forms (e.g. "shew", "hath", "doth").
        - Do not change punctuation. Preserve the source's exact use of commas, semicolons, colons.
        - Do not change capitalization.
        - If the source has italics markers like *word* or footnote markers like [^1], INCLUDE them as they appear in source.
        - Preserve the AI's intended span — don't return a much longer or shorter passage than they were trying to quote.

        If the source contains NO substring that clearly corresponds to the AI's quote (e.g. the AI invented content not present in the source at all), set repaired_quote to null.

        AI's QUOTE (potentially paraphrased):
        {{ model_quote }}

        SOURCE TEXT (verbatim Gill commentary):
        {{ source_text }}

        {{ ctx.output_format }}
    "#
}
