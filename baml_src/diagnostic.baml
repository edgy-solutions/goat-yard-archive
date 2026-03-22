// BAML Schema for RAG Failure Diagnostics

enum FailureCategory {
    ManifestBlock        // Info was in context, but available_books list blocked the LLM
    RetrievalMiss        // Weaviate returned chunks that didn't contain the answer
    TrueSilence          // The info actually isn't in the Gill Archive at all
    LLMLaziness          // The info was there, but the LLM missed it
}

class RAGAnalysis {
    category FailureCategory
    reasoning string @description("Brief explanation of why this category was chosen")
    fix_action string @description("Suggested fix (e.g., 'Add synonym for X' or 'Update book list')")
}

function AnalyzeRAGFailure(question: string, context: string, manifest: string) -> RAGAnalysis {
  client "openai/deepseek/deepseek-chat" // User prefers deepseek/deepseek-chat for this project
  prompt #"
    Review this RAG failure for the John Gill Archive.
    
    USER QUESTION: {{ question }}
    WEAVIATE CONTEXT: {{ context }}
    AVAILABLE BOOKS: {{ manifest }}

    Analyze why the system gave a 'No Information' response or failed to answer correctly.
    {{ ctx.output_format }}
  "#
}
