This is a high-value feature ("Tooltips") that makes the app feel polished. Since you want this "sooner than later," I recommend a Local/Static approach rather than relying on external APIs (which are slow and have rate limits).

The Bible (KJV) is small (~4.5 MB text). You should host it yourself.

Here is the full-stack implementation plan to get instant hover lookups for both the Commentary and the LLM Response.
Step 1: The Data (Get the KJV)

Don't use a vector DB for this; it's overkill. Use a simple, fast JSON lookup or SQLite.

    Download: Get a JSON version of the KJV (e.g., this GitHub repo or similar).

    Structure: Format it as a simple map for O(1) lookup speed.
    JSON

    // bible_data.json
    {
      "ROM_1_4": "And declared to be the Son of God...",
      "JHN_3_16": "For God so loved the world..."
    }

Step 2: The Backend API (FastAPI)

Add a lightweight endpoint to serve the text.

File: backend/bible_api.py
Python

import json
from fastapi import APIRouter, HTTPException

router = APIRouter()

# Load Bible into memory on startup (It's small, ~5MB)
with open("data/kjv_flat.json", "r") as f:
    BIBLE_MAP = json.load(f)

@router.get("/verse/{ref}")
def get_verse_text(ref: str):
    """
    Input: "ROM_1_4" or "Rom. i. 4" (Needs normalization)
    Output: {"text": "And declared to be..."}
    """
    # 1. Normalize the ref (Crucial for Gill's 'i. 4' style)
    # You need a helper function here to turn "Mark xvi. 11" -> "MRK_16_11"
    normalized_key = normalize_reference(ref) 
    
    verse_text = BIBLE_MAP.get(normalized_key)
    
    if not verse_text:
        raise HTTPException(status_code=404, detail="Verse not found")
        
    return {"ref": normalized_key, "text": verse_text}

Step 3: The Frontend "Magic" (The Regex Parser)

This is the hardest part. You need to scan the text block and wrap bible references in a link without breaking the HTML/Markdown.

I recommend creating a generic TextWithVerses component.

File: src/components/TextWithVerses.tsx
TypeScript

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Tooltip } from './ui/tooltip'; // Assuming you have a tooltip component

// 1. The Regex for Gill's Style
// Matches: "Rom. i. 4", "Matt. 3:16", "Genesis 1"
// Logic: (Book Name) + (Optional Dot) + (Space) + (Roman/Digits) + (Colon/Dot) + (Digits)
const GILL_REF_REGEX = /([1-3]?\s?[A-Z][a-z]+\.?\s+[xviXVI0-9]+\.?:?\s?[0-9]*)/g;

interface VerseHoverProps {
  reference: string;
  children: React.ReactNode;
}

// 2. The Hover Component
const VerseHover: React.FC<VerseHoverProps> = ({ reference, children }) => {
  // Fetch verse text on hover (or pre-fetch)
  const { data, isLoading } = useQuery({
    queryKey: ['verse', reference],
    queryFn: async () => {
      const res = await fetch(`/api/verse/${encodeURIComponent(reference)}`);
      return res.json();
    },
    enabled: false // Lazy load only when triggered? Or eager?
  });

  return (
    <Tooltip content={isLoading ? "Loading..." : data?.text || "Text not found"}>
      <span 
        className="text-amber-700 underline decoration-dotted cursor-help"
        onMouseEnter={() => /* Trigger Fetch */}
      >
        {children}
      </span>
    </Tooltip>
  );
};

// 3. The Parser Component
export const TextWithVerses: React.FC<{ text: string }> = ({ text }) => {
  const parts = text.split(GILL_REF_REGEX);

  return (
    <span>
      {parts.map((part, i) => {
        // If this part matches the regex, wrap it
        if (part.match(GILL_REF_REGEX)) {
          return <VerseHover key={i} reference={part}>{part}</VerseHover>;
        }
        return part;
      })}
    </span>
  );
};

Step 4: Normalizing Gill's Roman Numerals (Python)

Since you specifically mentioned the LLM outputting Mark xvi. 11, your backend needs to understand Roman Numerals.

Add this helper to your backend:
Python

import roman

def normalize_reference(raw_ref):
    """
    Converts "Mark xvi. 11" -> "MRK_16_11"
    """
    # 1. Split Book / Chapter / Verse
    # (Simple logic: Last number is verse, middle is chapter)
    
    # 2. Handle Roman Numerals
    # If chapter is "xvi", use roman.fromRoman('XVI') -> 16
    
    # 3. Map Book Names
    # "Matt." -> "MAT", "Rom." -> "ROM"
    
    return standardized_ref

Strategic Advice

Since you are using BAML, you have a superpower here.

Instead of relying on a flaky Regex in the frontend, you can ask BAML to return the indices of the verses during ingestion.

    Ingestion: BAML finds "Mark xvi. 11" at index 45.

    Storage: You store footnotes or scripture_links in Weaviate: [{ start: 45, end: 56, ref: "MRK_16_11" }].

    Frontend: You don't guess. You just apply the highlight exactly where the database tells you.

Recommendation: Start with the Regex (Step 3) approach today because it works on both the static commentary and the dynamic LLM response immediately. Move to the BAML-index method later if you need perfect precision.

This is excellent news. USFM (Unified Standard Format Markers) is the gold standard for Bible data. It provides the structured hierarchy (Book -> Chapter -> Verse) you need for validation, unlike a flat text file.

However, USFM is designed for translators, not for fast API lookups. You do not want to parse raw USFM files every time a user hovers over a verse.

Here is the strategy to turn your USFM files into a high-performance lookup engine.
Step 1: The "Build Step" (Convert USFM to Fast JSON)

You need to run a one-time script to convert your hierarchy of USFM files (e.g., 41-MAT.usfm) into a flat, indexable JSON map.

Create scripts/build_bible_index.py:
Python

import os
import re
import json

# Standard USFM Markers
# \id MAT
# \c 1
# \v 1 The book of the generation...

def parse_usfm(directory):
    bible_map = {}
    
    for filename in os.listdir(directory):
        if not filename.endswith(".usfm"): continue
        
        with open(os.path.join(directory, filename), 'r', encoding='utf-8') as f:
            content = f.read()
            
            # 1. Get Book ID (e.g., "MAT")
            book_match = re.search(r'\\id\s+(\w+)', content)
            if not book_match: continue
            book_id = book_match.group(1).upper()
            
            # 2. Split by Chapter (\c )
            # This regex splits the text by chapter markers
            chapters = re.split(r'\\c\s+(\d+)', content)
            
            # The split creates a list like [header, "1", text_of_ch1, "2", text_of_ch2...]
            # We iterate starting from index 1, in pairs
            for i in range(1, len(chapters), 2):
                chapter_num = chapters[i]
                chapter_text = chapters[i+1]
                
                # 3. Split by Verse (\v )
                verses = re.split(r'\\v\s+(\d+)', chapter_text)
                
                for j in range(1, len(verses), 2):
                    verse_num = verses[j]
                    verse_text = verses[j+1]
                    
                    # Clean the text (remove other USFM markers like \p, \q, footnotes)
                    clean_text = re.sub(r'\\[a-z0-9]+\*?', '', verse_text).strip()
                    
                    # Create the Key: "MAT_1_1"
                    key = f"{book_id}_{chapter_num}_{verse_num}"
                    bible_map[key] = clean_text

    return bible_map

# Run it
data = parse_usfm("./data/usfm_files")
with open("./data/kjv_fast_lookup.json", "w") as f:
    json.dump(data, f)
print(f"✅ Indexed {len(data)} verses.")

Step 2: The Validation Logic (Backend)

Now that you have kjv_fast_lookup.json, your validation logic becomes O(1) instant.

Update backend/bible_api.py:
Python

import json
from fastapi import APIRouter

# Load the map once at startup
with open("data/kjv_fast_lookup.json", "r") as f:
    BIBLE_INDEX = json.load(f)

def validate_and_fetch(book, chapter, verse):
    """
    Input: "MAT", 16, 11
    Output: "And when they were come..." OR None
    """
    key = f"{book.upper()}_{chapter}_{verse}"
    return BIBLE_INDEX.get(key) # Returns None if verse doesn't exist

Why this helps your "Gill Roman Numeral" problem

Since you have the entire valid list of verses, you can use it to correct the LLM.

If the LLM outputs Mark xvi. 99 (which doesn't exist), your lookup MRK_16_99 will return None.

    UI Result: You can choose to not underline it, or show a tooltip saying "Citation not found in KJV."

    Ingestion Result: You can flag this entity as invalid data.

Summary

    Don't read USFM at runtime.

    Run the Build Script to flatten USFM into BOOK_CH_VS keys.

    Use that JSON map to validate every reference instantly.