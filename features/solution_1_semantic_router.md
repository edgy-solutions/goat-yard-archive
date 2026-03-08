# Feature Plan: Semantic Entity Routing

## The Problem
As the Weaviate library grows, rigid string matching (e.g. searching the word "Savior") fails because the database normalizes it to "Jesus Christ" during ingestion. The lack of a match drops the search engine into a massive unstructured vector query, burying perfect answers under less-relevant but mathematically similar paragraphs (the "Lost in the Middle" problem).

## The Solution
Instead of enforcing rigid word-for-word checks against the Knowledge Graph, use Weaviate's native vector properties to dynamically build an Entity "Cheat Sheet", and pass that to a fast LLM router on the `/api/search` endpoint to flawlessly translate User Queries into Graph Nodes.

### Step 1: Vector Scan the Graph (Not Chunks)
1. In `backend/gill_search.py`, update `extract_potential_entities(query)` to completely remove regex string matching.
2. Query the `TheologicalEntity` collection directly using a lightweight `.near_text()` or `.hybrid()` search against the user's raw query string.
3. Limit this to the Top 10 entities (e.g., retrieving `["Jesus Christ", "God", "Holy Spirit"]` when a user searches for "Savior").

### Step 2: The LLM Router
1. Pass the user's query AND the Top 10 Entity "Cheat Sheet" into a fast, cheap LLM (`gpt-4o-mini`, `grok-fast`, etc). 
   - *Prompt: "The user searched for X. Which of these 10 exact Weaviate entities (if any) are they talking about?"*
2. The LLM will flawlessly map synonyms ("Savior") to the exact Database key ("Jesus Christ") because it can securely see the available options.

### Step 3: Execute Precise Graph Search
1. Take the exact returned entities from the Router.
2. Maintain the current Strict Filter (`wvc.query.Filter.by_ref("mentions_entity").by_property("name").equal(ent)`).
3. The Search perfectly isolates only chunks featuring those exact resolved entities, drastically shrinking the haystack before performing the final Vector chunk search.

## Pros & Cons
**Pros:** 
- Fixes the recall issue without rebuilding the database.
- Easily handles synonyms, misspellings, and theological abstractions.

**Cons:** 
- Adds a secondary LLM call to the execution pipeline (adds ~500ms latency to all searches).
- Still suffers from "Missing Edges" if the original ingestion pipeline failed to link a pronoun to an entity.
