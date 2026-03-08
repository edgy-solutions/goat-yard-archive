# Feature Plan: Ingestion-Time Pronoun Resolution

## The Problem
When a user asks complex questions, they often search for specific terms that John Gill doesn't use in every paragraph. Gill frequently relies on pronouns ("He believed God") for entire passages. Because the current extraction prompt limits Theological Entities to explicit mentions, Weaviate's `mentions_entity` Graph Edge is never created for these paragraphs. This forces search queries to execute without strict Semantic Routing, leading to inaccurate Vector ranking.

## The Solution
Instead of applying a "Soft-Boost" band-aid at search time, implement **Coreference Resolution** directly into the Data Ingestion pipeline. By providing the LLM with a trailing "Memory" of previously extracted entities for the current chapter or page, we can instruct BAML to link generic pronouns back to explicit database objects natively.

### Step 1: Python Context Buffer (`ingest.py`)
1. Create a `recent_entities` buffer list before parsing chunks on a given page.
2. When iterating over `parsed_verses`, pass `recent_entities[-10:]` (the last 10 unique entities) as a parameter into the `extract_entities()` wrapper function.
3. Once the LLM returns the structured BAML entities for a chunk, append them to the `recent_entities` list for the *next* chunk.

### Step 2: BAML Prompt Modification (`gill_extract.baml`)
1. Update the `ExtractGillKnowledge` function signature to accept a secondary `previous_entities: string?` hint argument.
2. Add a new explicit instruction block for **PRONOUN RESOLUTION**:
   > *If the text predominantly relies on pronouns ("he", "the king") rather than explicit names, review the `Previous Entities` list provided in the prompt. If context clearly aligns the pronoun with one of the previously extracted Gill Entities (e.g., "he" refers to "Abraham"), extract the specific name (e.g., "Abraham") as the Theological Entity for this text segment.*

### Step 3: Graph Construction
1. Weaviate will automatically detect the returned entity (e.g., "Abraham"), query the cache, and create the `mentions_entity` Graph Edge for that chunk.
2. At search time, strict filtering via Semantic Entity matching will flawlessly execute with zero missing nodes.

## Pros & Cons
**Pros:** 
- The absolute mathematically "perfect" RAG design.
- Extracted entities are 100% accurate explicitly attached to the correct chunks.
- No slow LLM routing or additional code is required on the `/api/search` server payload.

**Cons:** 
- Requires re-ingesting the Weaviate Database volume by volume to backfill the missing edges.
- BAML prompt usage tokens increase marginally, as the context hint array is appended to every execution round trip per verse chunk.
