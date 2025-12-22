# Specification: Grounded Gill Commentary (RAG + Vision)

## 1\. Objective

To build a Retrieval Augmented Generation (RAG) system for John Gill’s *Exposition of the Entire Bible* that prioritizes **forensic accuracy** and **source transparency**.

  * **Input:** Natural language theological questions.
  * **Output:** A synthesized answer in Gill’s voice, strictly cited.
  * **Validation:** Every citation deep-links to the original scanned page image, highlighting the exact text used.

-----

## 2\. System Architecture

### 2.1 The Stack

  * **Language:** Python 3.11+
  * **Orchestration/Logic:** `DSPy` (Declarative Self-improving Python)
  * **Data Extraction:** `BAML` + `Tesseract` + `Vision Model (GPT-4o/Claude 3.5)`
  * **Database (Hybrid):** `Weaviate` (Cloud or Docker) OR `Postgres` (with `pgvector` + `pg_trgm`)
  * **Frontend:** React / Next.js (Split-pane View)

### 2.2 High-Level Data Flow

1.  **Ingestion:** PDF $\to$ Tesseract (Geometry) + Vision (Semantics) $\to$ BAML (Structure) $\to$ Fuzzy Align $\to$ DB.
2.  **Retrieval:** User Query $\to$ Hybrid Search (Keyword + Vector) $\to$ Top K Chunks.
3.  **Synthesis:** DSPy Module $\to$ Generation $\to$ Assertion Loop (Critic) $\to$ Final Answer.
4.  **Display:** UI renders Answer + Image Viewer with Canvas Overlay.

-----

## 3\. Data Models (Schema)

### 3.1 Physical Layer (`scan_registry`)

*Stores the raw image data and OCR geometry.*

| Field | Type | Description |
| :--- | :--- | :--- |
| `page_id` | PK (String) | Unique ID (e.g., `GILL_VOL1_P450`). |
| `volume` | Int | Volume number. |
| `page_number` | Int | Printed page number. |
| `image_url` | String | S3/Blob URL to the web-optimized JPG. |
| `ocr_word_data` | JSONB | Raw output from Tesseract (List of `[text, x, y, w, h]`). |

### 3.2 Logical Layer (`commentary_chunks`)

*Stores the semantic meaning and the glue to the physical layer.*

| Field | Type | Description |
| :--- | :--- | :--- |
| `chunk_id` | PK (UUID) | Unique ID. |
| `verse_ref` | String | Standardized ref (e.g., `MAT_03_16`). |
| `text_content` | Text | Clean, semantic text (from Vision model). |
| `embedding` | Vector | 1536d (OpenAI) or 1024d (Voyage/Cohere). |
| `scan_metadata` | JSONB | **The Golden Thread**. See structure below. |

**`scan_metadata` JSON Structure:**

```json
[
  {
    "page_id": "GILL_VOL1_P450",
    "is_partial": true,  // Does the verse span multiple pages?
    "highlight_box": [100, 450, 600, 800] // [x, y, w, h] Union Box
  },
  {
    "page_id": "GILL_VOL1_P451", // Next page if verse wraps
    "is_partial": true,
    "highlight_box": [100, 50, 600, 150]
  }
]
```

-----

## 4\. Pipeline 1: Ingestion (The "Alignment" Engine)

**Goal:** Create the `highlight_box` by merging clean Vision text with noisy Tesseract geometry.

### 4.1 Step-by-Step Logic

1.  **Pre-processing:**
      * Run `Tesseract` on Page Image $\to$ Get `ocr_word_data` (noisy).
      * Run `Vision Model` on Page Image $\to$ Get raw markdown.
2.  **Extraction (BAML):**
      * Pass Vision Markdown to BAML.
      * **Task:** Extract list of verses present on the page.
      * **Output:** `[{ "ref": "MAT 03:16", "start_phrase": "And Jesus...", "end_phrase": "...dove." }]`.
3.  **Alignment (Python/RapidFuzz):**
      * For each Verse:
          * Fuzzy match `start_phrase` against `ocr_word_data` stream $\to$ Get `Start_Index`.
          * Fuzzy match `end_phrase` against `ocr_word_data` stream $\to$ Get `End_Index`.
          * Slice `ocr_word_data[Start_Index : End_Index]`.
4.  **Geometry Calculation:**
      * Calculate Union Rectangle of sliced boxes: `Min(x), Min(y), Max(x+w), Max(y+h)`.
      * **Constraint Check:** If `StandardDeviation(x)` \> Threshold, detect **Column Split**. Return two boxes instead of one.
5.  **Storage:** Write to `commentary_chunks` table.

-----

## 5\. Pipeline 2: Runtime (The "Critic" Engine)

**Goal:** Answer the user's question and force citations that exist in the DB.

### 5.1 Retrieval Strategy

  * **Query Analysis:** Extract theological keywords (e.g., "Supralapsarianism").
  * **Hybrid Search:**
      * `alpha=0.5` (Equal weight to Keyword and Vector).
      * Retrieve Top 10 chunks.

### 5.2 DSPy Module Specification

  * **Signature:** `context, question -> answer, cited_page_ids`
  * **Model:** GPT-4o or Claude 3.5 Sonnet (needed for high reasoning).

**The Logic Loop (Code Spec):**

```python
class GroundedGillBot(dspy.Module):
    # ... init ...
    def forward(self, question, context):
        # Pass 1: Generate
        pred = self.generate(question, context)
        
        # Assertion 1: Format Check
        dspy.Assert(
            len(pred.cited_page_ids) > 0,
            "No citations found. You must cite the 'page_id' metadata.",
            allow_backtrack=True
        )
        
        # Assertion 2: Hallucination Check
        valid_ids = [c.page_id for c in context]
        dspy.Assert(
            all(pid in valid_ids for pid in pred.cited_page_ids),
            f"Invalid Citation. Only use: {valid_ids}",
            allow_backtrack=True
        )
        
        return pred
```

-----

## 6\. Frontend Specification

### 6.1 Layout

  * **Left Pane (50%):** Chat Interface.
      * Messages bubble list.
      * Citations rendered as buttons: `<button>[Vol 1, Pg 450]</button>`.
  * **Right Pane (50%):** Evidence Viewer.
      * Lazy-loaded Image Component.

### 6.2 The Viewer Component (`ScanViewer.tsx`)

  * **Props:** `imageUrl`, `highlightBox` (Array), `scale` (for zoom).
  * **Rendering:**
    1.  Render `<img>`.
    2.  Render `<canvas>` or absolute `<div>` overlays on top.
    3.  **Coordinate Mapping:** Ensure backend coordinates (usually relative to full resolution) scale correctly to the displayed CSS width/height.
    <!-- end list -->
      * *Formula:* `display_x = (original_x / original_width) * display_width`

### 6.3 Confidence UI

  * If DSPy Assertion backtracks \> 2 times, tag the response with a yellow "⚠️ Low Confidence" badge.
  * If citations match perfectly, tag with green "✅ Verified Source."

-----

## 7\. Implementation Roadmap

### Phase 1: Ingestion Core (Python)

  - [ ] Run Tesseract on 1 Volume.
  - [ ] Run Vision Model on 1 Volume.
  - [ ] Implement `fuzzymatch_alignment.py`.
  - [ ] Verify bounding boxes visually (generate debug images with drawn boxes).

### Phase 2: Database & Retrieval

  - [ ] Setup Weaviate/Postgres.
  - [ ] Write the BAML ingestion script to populate DB.
  - [ ] Test Hybrid Search (ensure "baptism" returns relevant chunks).

### Phase 3: The Brain (DSPy)

  - [ ] Define `GillSignature`.
  - [ ] Implement `GroundedGillBot` with Assertions.
  - [ ] Create a small "Golden Dataset" of 20 QA pairs to compile/optimize the DSPy prompt.

### Phase 4: UI Integration

  - [ ] Build Split-pane layout.
  - [ ] Wire up "Click Citation" $\to$ "Fetch Image + Coordinates".
  - [ ] Implement canvas highlighting.