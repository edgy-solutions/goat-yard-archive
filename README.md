# Dr. Voluminous: The Digital Archives of Dr. John Gill

## Backend Architecture & Request Flow

This system uses a **Retrieval-Augmented Generation (RAG)** pipeline to provide grounded, theological answers based on the writings of Dr. John Gill. The backend assumes the persona of an 18th-century contemporary to maintain tonal consistency.

### The Pipeline Steps

1.  **User Inquiry**
    *   The user submits a natural language query (e.g., *"What is the covenant of grace?"*) via the frontend.
    *   Requests are rate-limited (10/day for anonymous users, 100/day for specialized accounts).

2.  **Vector Search & Retrieval (Weaviate)**
    *   **Entity Extraction**: The query is scanned using regex and heuristics to identify potential theological entities (e.g., "Abraham", "Moses"). These are verified against the specific `TheologicalEntity` collection in Weaviate.
    *   **Verse Detection**: The system detects Bible verse references (e.g., "Matthew 7:27") using strict regex patterns to distinguish them from general text.
    *   **Hybrid Search**: A query is executed against the `CommentaryChunk` collection in Weaviate.
        *   It uses **Hybrid Search** (combining sparse keyword matching with dense vector embedding similarity).
        *   If specific **Entities** or **Verses** were detected, distinct filters are applied to prioritize or restrict results to those relevant sections.
    *   **Result**: The system retrieves the top 5 most relevant text chunks, complete with metadata (Volume, Page, Scan Coordinates).

3.  **LLM Generation (DSPy)**
    *   **Context Assembly**: The retrieved chunks are formatted into a structured context block using **Sentence-Level Granularity**. Each sentence is given a globally unique ID (e.g., `[GEN_46_06_S01]`) so the model can cite exact sentences rather than just the whole page.
    *   **Persona Injection**: The LLM (powered by `deepseek-chat` via OpenRouter) is prompted with a specific **DSPy Signature** (`GillSignature`). It is instructed to:
        *   Adopt the voice of an 18th-century academic contemporary.
        *   Base the answer *only* on the provided context.
        *   Cite the specific **Sentence ID** (`[GEN_46_06_S01]`) for every claim.
        *   Refer to Dr. Gill in the third person.
    *   **Generation**: The model generates a theological summary and a list of specific sentence citations. This allows the frontend to highlight the *exact sentence* used as evidence.

4.  **Verification (The Critic)**
    *   **Format Check**: The `GroundedGillBot` module parses the model's output to ensure citations match the expected **Sentence ID** format (e.g., `[GEN_46_06_S01]`).
    *   **Hallucination Check (Grounding)**: The system iterates through every citation provided by the AI. It verifies that **every cited source actually exists** in the list of chunks retrieved in Step 2.
    *   **Outcome**:
        *   If valid, the response is marked `verified: true` and returned to the user.
        *   If the model cites a source it wasn't given (a hallucination), the verification fails, preventing misleading references.

### Systems Diagram

```mermaid
graph TD
    User([User Query]) --> API[FastAPI /search Endpoint];
    
    subgraph "Retrieval Engine (gill_search.py)"
        API --> Analysis{Query Analysis};
        Analysis -->|Extract| Entity[Entity Lookup];
        Analysis -->|Parse| Verse[Verse Regex];
        Entity --> Hybrid[Weaviate Hybrid Search];
        Verse --> Hybrid;
        Analysis -->|Raw Query| Hybrid;
        Hybrid -->|Top 5 Chunks| Chunks[(Commentary Chunks)];
    end

    subgraph "Generation (bot.py)"
        Chunks --> Formatter[Context Formatter];
        Formatter -->|Context + Query| DSPy[DSPy Module];
        DSPy -->|Prompt| LLM[LLM (DeepSeek-Chat)];
        LLM -->|Answer + Citations| Prediction[Raw Prediction];
    end

    subgraph "Verification"
        Prediction --> Critic[GroundedGillBot Critic];
        Critic -->|Verify Citations exist in Context| Check{Valid?};
        Check -->|Yes| Verified[Verified Response];
        Check -->|No| Error[Unverified / Error];
    end

    Verified --> Client[Frontend UI];
```

## Ingestion Pipeline & Data Schema

The system relies on a sophisticated ingestion pipeline to transform raw OCR text into a structured, searchable knowledge graph.

### 1. The Data Schema (Weaviate)

The database consists of two primary collections that form a **Knowledge Graph**:

#### `CommentaryChunk` (The Content)
Stores the actual text of the commentary, sliced by Bible verse.
*   **`content`** (Text): The commentary text for a specific verse.
*   **`verse_ref`** (Text): Canonical reference, e.g., "MATTHEW 7:27".
*   **`scan_json`** (JSON): Coordinates specifying where this text appears in the original physical books (Volume, Page, X/Y boxes) for UI highlighting.
*   **`sentence_data`** (JSON, `index=False`): Array of sentence objects (`{sentence_id, text, index}`) enabling precise citations (e.g., `GEN_46_06_S01`).
*   **`mentions_entity`** (Cross-Reference): A graph link to `TheologicalEntity` objects mentioned in this chunk.
*   **`footnotes`** (Array): Extracted footnotes resolved from the bottom of the page back to their context.

#### `TheologicalEntity` (The Graph Nodes)
Represents people, places, and concepts to enable "Graph-RAG" (Graph-Augmented Retrieval).
*   **`name`**: The entity name (e.g., "Aben Ezra"). Vectorized for semantic search.
*   **`description`**: Short BAML-extracted context. Vectorized for semantic grounding.
*   **`category`**: The type of entity (e.g., "BiblicalFigure"). Uses **Field Tokenization**.
*   **`biblical_era`**: (Disambiguation) e.g., "OldTestament" vs "NewTestament". 
*   **`role`**: (Disambiguation) e.g., "Patriarch" vs "Husband of Mary".
*   **`normalized_name`**: Unique ID seed. For ambiguous names (Joseph, Mary), this is combined with Era/Role to generate distinct nodes (e.g., `JOSEPH_OT_PATRIARCH` vs `JOSEPH_NT_HUSBAND`).

### 2. Ingestion Workflow

The `scripts/ingest.py` and `normalize_markdown.py` scripts handle the transformation:

1.  **Normalization (LLM-based)**
    *   Raw OCR text is often messy. We use a specialized LLM pipeline (`normalize_markdown.py`) to fix 18th-century formatting errors (e.g., specific "Lemma" headers like `Ver. 6.`) while strictly preserving Hebrew/Greek text.
    *   It uses a "Critic" loop to verify that the LLM didn't hallucinate or remove content.

2.  **Verse Alignment (Fuzzy Matching)**
    *   The system uses `rapidfuzz` to locate the exact start and end of every Bible verse within the continuous commentary text.
    *   It handles **Page Spanning**: If a verse starts on page 100 and ends on page 101, the system stitches the text together and merges the visual highlight boxes from both pages.

3.  **Graph Construction (BAML)**
    *   As text is processed, **BAML** (Better Another Modeling Language) is used to extract entities (e.g., "The Chaldee Paraphrase says...").
    *   These entities are deduplicated and inserted into `TheologicalEntity`.
    *   The `CommentaryChunk` is then linked to these entities, creating a traversable graph (e.g., "Find all commentary mentioning *Gamaliel*").

