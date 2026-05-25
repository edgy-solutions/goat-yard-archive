#!/usr/bin/env python3
"""
Weaviate Ingestion Pipeline for Gill Commentary.

This script processes aligned commentary pages and ingests them into Weaviate with:
- Fuzzy slicing to extract verse-specific commentary
- Handling of spanning verses across pages
- Sentence segmentation using NLTK
- Entity extraction via BAML
- Footnote extraction and resolution
- Knowledge graph construction
"""

import os
import sys
import time
import json
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import nltk
from rapidfuzz import fuzz, process as fuzz_process
import requests
import weaviate
import weaviate.classes as wvc

def get_ollama_embedding(text: str, url: str = "http://localhost:11434/api/embeddings", model_name: str = "qwen3-embedding") -> list[float]:
    """Fetches an embedding vector from the local Ollama instance."""
    payload = {
        "model": model_name,
        "prompt": text
    }
    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()
    vec = response.json().get("embedding", [])
    if not vec:
        raise ValueError(f"Ollama model '{model_name}' returned empty embedding.")
    return vec

from dotenv import load_dotenv
import networkx as nx
import matplotlib.pyplot as plt


# Import BAML client
from baml_client.sync_client import b
from baml_py.errors import BamlError

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('ingestion.log', encoding='utf-8')
    ]
)

# Download NLTK data if not present
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    logging.info("Downloading NLTK punkt tokenizer...")
    nltk.download('punkt', quiet=True)


class GillIngestionEngine:
    """Orchestrates the ingestion of Gill Commentary into Weaviate."""
    
    def __init__(self, weaviate_host: str = "localhost", weaviate_port: int = 80, ollama_url: str = "http://localhost:11434/api/embeddings", ollama_model: str = "qwen3-embedding"):
        """Initialize the ingestion engine."""
        # Connect to Weaviate with env var support
        weaviate_url = os.getenv("WEAVIATE_URL")
        weaviate_api_key = os.getenv("WEAVIATE_API_KEY")
        
        # Prepare headers for modules
        headers = {}
        if os.getenv("OPENROUTER_API_KEY"):
            headers["X-OpenAI-Api-Key"] = os.getenv("OPENROUTER_API_KEY")
            headers["X-OpenAI-BaseURL"] = "https://openrouter.ai/api/v1"
            
        if weaviate_url:
            logging.info(f"Connecting to Weaviate at {weaviate_url}")
            
            http_host = weaviate_url.replace("http://", "").replace("https://", "").split(":")[0]
            http_port = int(weaviate_url.split(":")[-1]) if ":" in weaviate_url else 80
            
            # Allow gRPC override
            grpc_host = os.getenv("WEAVIATE_GRPC_HOST", http_host)
            grpc_port = int(os.getenv("WEAVIATE_GRPC_PORT", "50051"))
            
            logging.info(f"gRPC Target: {grpc_host}:{grpc_port}")

            self.client = weaviate.connect_to_custom(
                http_host=http_host,
                http_port=http_port,
                http_secure=weaviate_url.startswith("https"),
                grpc_host=grpc_host,
                grpc_port=grpc_port,
                grpc_secure=weaviate_url.startswith("https"),
                headers=headers,
                auth_credentials=weaviate.auth.AuthApiKey(weaviate_api_key) if weaviate_api_key else None,
                skip_init_checks=True # Often needed for complex network setups
            )
        else:
            self.client = weaviate.connect_to_local(
                host=weaviate_host,
                port=weaviate_port,
                grpc_port=50051,
                headers=headers
            )
            
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
            
        # Get collection references
        self.entities = self.client.collections.get("TheologicalEntity")
        self.chunks = self.client.collections.get("CommentaryChunk")
        
        # Cache for entity deduplication
        self.entity_cache: Dict[Tuple[str, str], str] = {}  # (name, category) -> UUID
        
        self.has_failures = False
        
        logging.info(f"Connected to Weaviate")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            self.client.close()
    
    def parse_page_info(self, page_name: str, volume_override: int = None) -> Tuple[int, int]:
        """Parse volume and page number from filename."""
        if volume_override:
             # If override is provided, use it for volume, parse page num from name
             parts = page_name.split("_")
             if len(parts) >= 1:
                 # page100_image1 -> page100 -> 100
                 # Try to extract number from first part
                 try:
                     page_str = parts[0].replace("page", "")
                     return volume_override, int(page_str)
                 except:
                     pass

        # Try parsing standard formats
        parts = page_name.split("_")
        
        # Case 1: vol1_page100_image1 (New standardized format)
        if len(parts) >= 3 and parts[0].startswith("vol") and "page" in parts[1]:
            try:
                extracted_vol = int(parts[0].replace("vol", ""))
                extracted_page = int(parts[1].replace("page", ""))
                # Prefer override if given, else extracted
                return (volume_override if volume_override else extracted_vol), extracted_page
            except:
                pass

        # Case 2: page100_image1 (Legacy format)
        if len(parts) >= 2 and "page" in parts[0]:
            try:
                page_num = int(parts[0].replace("page", ""))
                extracted_vol = 1
                if "image" in parts[1]:
                    try:
                        extracted_vol = int(parts[1].replace("image", "").replace(".png", ""))
                    except:
                        pass
                return (volume_override if volume_override else extracted_vol), page_num
            except:
                pass

        # Default fallback
        logging.warning(f"Could not parse volume/page from {page_name}. Defaulting to (Volume 1, Page 0) unless overridden.")
        return (volume_override if volume_override else 1), 0
    
    def load_adjacent_markdown(self, page_name: str, qwen_dir: Path) -> Tuple[str, str, str]:
        """
        Load current page and adjacent pages for cross-page verse handling.
        Prioritizes _normalized.md files if they exist, falling back to .md.
        """
        def load_file(p_name: str) -> str:
            # Try normalized first
            norm_path = qwen_dir / f"{p_name}_normalized.md"
            if norm_path.exists():
                with open(norm_path, 'r', encoding='utf-8') as f:
                    return f.read()
            
            # Fallback to raw
            raw_path = qwen_dir / f"{p_name}.md"
            if raw_path.exists():
                with open(raw_path, 'r', encoding='utf-8') as f:
                    return f.read()
            return ""

        # Parse page number
        volume, page_num = self.parse_page_info(page_name)
        
        # Load pages
        current_md = load_file(page_name)
        
        prev_page_name = f"page{page_num - 1}_image{volume}"
        prev_md = load_file(prev_page_name)
        
        next_page_name = f"page{page_num + 1}_image{volume}"
        next_md = load_file(next_page_name)
        
        return prev_md, current_md, next_md

    def find_phrase_index(self, text: str, phrase: str, start_search_idx: int = 0) -> int:
        """Find the starting index of a fuzzy match for a phrase."""
        if not phrase:
            return -1
            
        remaining_text = text[start_search_idx:]
        if not remaining_text:
            return -1
            
        # Use rapidfuzz alignment for O(N) matching
        alignment = fuzz.partial_ratio_alignment(phrase.lower(), remaining_text.lower())
        
        if alignment and alignment.score >= 80:
            return start_search_idx + alignment.dest_start
            
        return -1

    def slice_verse_text(self, full_text: str, start_phrase: str, stop_phrase: Optional[str], end_fallback: str) -> Optional[str]:
        """
        Extract text from start_phrase to stop_phrase (start of next verse).
        If stop_phrase is None, uses end_fallback (end of current verse from alignment).
        """
        # Find Start
        start_idx = self.find_phrase_index(full_text, start_phrase)
        if start_idx == -1:
            logging.warning(f"Could not find start phrase: {start_phrase[:30]}...")
            return None
            
        # Find Stop
        end_idx = -1
        if stop_phrase:
            # Look for stop phrase AFTER start phrase
            # We want to stop AT the stop phrase (start of next verse), so we don't include it.
            # But duplicate headers happen? Assume next match is correct.
            next_verse_start_idx = self.find_phrase_index(full_text, stop_phrase, start_search_idx=start_idx + len(start_phrase))
            if next_verse_start_idx != -1:
                end_idx = next_verse_start_idx
            
        if end_idx == -1:
            # Fallback: Use alignment end phrase
             # Look for end phrase
             match_end_idx = self.find_phrase_index(full_text, end_fallback, start_search_idx=start_idx)
             if match_end_idx != -1:
                 # Include the end phrase
                 end_idx = match_end_idx + len(end_fallback)
             else:
                 # Last resort: Take a reasonable chunk? Or fail.
                 # Failing is better than hallucinating.
                 # But if we found start, maybe take lines?
                 pass

        if end_idx != -1 and end_idx > start_idx:
            extracted = full_text[start_idx:end_idx].strip()
            return extracted
            
        return None

    def extract_footnotes(self, text: str, current_md: str, next_md: str = "") -> List[str]:
        """
        Extract footnote definitions for references found in the text.
        
        For spanning verses, we need to determine which PAGE each reference is on,
        since footnote IDs reset per-page in the original work.
        
        Strategy:
        1. Find where current_md ends in the merged context
        2. For each ref in `text`, find its position
        3. If ref appears in portion from current_md -> search current_md for definition
        4. If ref appears in portion from next_md -> search next_md for definition
        """
        # Find refs like [^1], [^12] but NOT followed by a colon (which would indicate a definition)
        refs = re.findall(r'\[\^(\d+)\](?!:)', text)
        footnotes = []
        unique_refs = sorted(list(set(refs)), key=lambda x: int(x))
        
        # Determine page boundary in the merged text
        # We search `text` against both pages to determine affinity
        current_boundary = len(current_md)
        merged_context = current_md + "\n" + next_md
        
        for ref in unique_refs:
            ref_pattern = re.compile(rf'\[\^{ref}\](?!:)')
            
            # Find where this ref appears in the sliced text
            # Then map that to the merged context to determine page affinity
            ref_match_in_text = ref_pattern.search(text)
            if not ref_match_in_text:
                continue
                
            # Find this reference's position in the merged context
            # Use fuzzy matching since text was sliced from merged context
            ref_pos_in_merged = merged_context.find(text[:50])  # Use start of text as anchor
            if ref_pos_in_merged == -1:
                ref_pos_in_merged = 0
            
            actual_ref_pos = ref_pos_in_merged + ref_match_in_text.start()
            
            # Determine which page to search for definition
            if actual_ref_pos < current_boundary:
                # Reference is on current page, search current_md for definition
                search_context = current_md
                logging.debug(f"Footnote [{ref}] on current page")
            else:
                # Reference is on next page, search next_md for definition
                search_context = next_md if next_md else current_md
                logging.debug(f"Footnote [{ref}] on next page")
            
            # Search for definition [^ref]: ... at start of line
            def_pattern = re.compile(rf"^\[\^{ref}\]:\s*(.*)", re.MULTILINE)
            match = def_pattern.search(search_context)
            if match:
                defn = match.group(1).strip()
                footnotes.append(f"[{ref}] {defn}")
            else:
                # Fallback: try the other page if not found
                fallback_context = next_md if search_context == current_md else current_md
                match = def_pattern.search(fallback_context)
                if match:
                    defn = match.group(1).strip()
                    footnotes.append(f"[{ref}] {defn}")
                    logging.debug(f"Footnote [{ref}] found in fallback context")
        
        return footnotes

    def process_sentences(self, verse_ref: str, full_text: str) -> Tuple[List[Dict[str, Any]], str]:
        """Segment text into sentences better handling abbreviations. Returns (sentences, lemma_text)."""
        safe_ref = verse_ref.replace(" ", "_").replace(":", "_")
        lemma_text = ""
        
        # 1. Detect and Strip Lemma (Header Phrase ending in ']')
        # Regex: Start of string, non-greedy match until first ']', followed by optional whitespace
        # Example: "[Mat 5:1] And he said... ] Then he..." -> Lemma: "And he said... ]", Text: "Then he..."
        match = re.match(r'^(.*?\])\s*', full_text)
        if "]" in full_text and match:
             lemma_text = match.group(1) # Capture the lemma
             full_text = full_text[match.end():] # Slice after the match
        
        # Configure Tokenizer with Custom Abbreviations
        # We load the default English tokenizer
        try:
            tokenizer = nltk.data.load('tokenizers/punkt/english.pickle')
            # Add common biblical & theological abbreviations
            abbrevs = {
                'gen', 'exod', 'lev', 'num', 'deut', 'josh', 'judg', 'ruth', 'sam', 'kgs', 'chron', 'ezra', 'neh', 'esth', 'job', 'ps', 'prov', 'eccl', 'cant', 'isa', 'jer', 'lam', 'ezek', 'dan', 'hos', 'joel', 'amos', 'obad', 'jon', 'mic', 'nah', 'hab', 'zeph', 'hag', 'zech', 'mal',
                'matt', 'rom', 'cor', 'gal', 'eph', 'phil', 'col', 'thess', 'tim', 'titus', 'phlm', 'heb', 'jas', 'pet', 'john', 'jude', 'rev',
                'ver', 'vol', 'chap', 'sect', 'bk', 'lib', 'cap', 'ibid', 'id', 'vid', 'viz', 'sc', 'eq', 'cf', 'vs', 'mss', 'obj',
                # Roman Numerals (Common in Gill for Chapters)
                'i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x', 'xi', 'xii', 'xiii', 'xiv', 'xv', 'xvi', 'xvii', 'xviii', 'xix', 'xx',
                'xxi', 'xxii', 'xxiii', 'xxiv', 'xxv', 'xxvi', 'xxvii', 'xxviii', 'xxix', 'xxx', 'xxxi', 'xxxii', 'xxxiii', 'xxxiv', 'xxxv', 
                'xxxvi', 'xxxvii', 'xxxviii', 'xxxix', 'xl', 'xli', 'xlii', 'xliii', 'xliv', 'xlv', 'xlvi', 'xlvii', 'xlviii', 'xlix', 'l'
            }
            tokenizer._params.abbrev_types.update(abbrevs)
            raw_sentences = tokenizer.tokenize(full_text)
        except Exception as e:
            logging.warning(f"Failed to configure custom tokenizer: {e}. Falling back to default.")
            raw_sentences = nltk.sent_tokenize(full_text)

        # Heuristic Post-Processing: Merge sentences starting with lowercase
        merged_sentences = []
        if raw_sentences:
            merged_sentences.append(raw_sentences[0])
            
            for i in range(1, len(raw_sentences)):
                curr = raw_sentences[i]
                prev = merged_sentences[-1]
                
                # Check 1: Starts with lowercase (continuations)
                # Check 2: Previous ended with common abbrv
                if curr[0].islower() or (prev.strip().endswith('.') and len(prev.split()[-1]) <= 3 and prev.split()[-1].lower().replace('.','') in abbrevs):
                     merged_sentences[-1] = f"{prev} {curr}"
                else:
                     merged_sentences.append(curr)
        
        sentences = merged_sentences
        
        structured_data = []
        for i, txt in enumerate(sentences):
            structured_data.append({
                "sentence_id": f"{safe_ref}_S{i:02d}",
                "text": txt.strip(),
                "index": i
            })
        
        return structured_data, lemma_text
    
    def extract_verse_number(self, verse_ref: str) -> str:
        """Extract verse number from reference."""
        if ":" in verse_ref:
            return verse_ref.split(":")[1].lstrip("0")
        return ""
    
    @staticmethod
    def compute_search_key(name: str) -> str:
        """
        Canonical lookup key: lowercased, with everything that isn't a Unicode
        letter or digit stripped. Spaces, hyphens, punctuation, and combining
        marks (e.g. Hebrew niqqud, Greek accents) are removed.

        Examples:
          'scape-goat'           -> 'scapegoat'
          'Scape-goat'           -> 'scapegoat'
          'Day of Atonement'     -> 'dayofatonement'
          'Aben Ezra'            -> 'abenezra'
          'דְּבָרֵי סוֹפְרִים'      -> 'דבריסופרים'   (niqqud stripped as combining marks)
          'λόγος'                -> 'λόγος'        (Greek letters kept)

        Using str.isalnum() rather than a regex like [a-z0-9] so that non-Latin
        scripts (Hebrew, Greek, Arabic) produce meaningful keys instead of empty
        strings. Empty-string keys are a fragmentation hazard — see ADR-0005.

        This is the value used by get_relevant_entities for substring matching
        AND by get_or_create_entity for deduplication. Code computes it; the LLM
        never produces it.
        """
        return "".join(c for c in (name or "").lower() if c.isalnum())

    @staticmethod
    def compute_display_normalized_name(name: str) -> str:
        """
        Human-readable display form of an entity name. Distinct from search_key.

        We DON'T try to be clever (e.g. 'Christ' -> 'Jesus Christ') because that
        kind of canonicalization is what we just removed from BAML for being
        unreliable. The display form is just a cleaned version of the raw name:
        stripped, hyphens preserved, whitespace collapsed.
        """
        return re.sub(r"\s+", " ", (name or "").strip())

    def get_or_create_entity(
        self,
        name: str,
        category: str,
        normalized_name: Optional[str] = None,  # kept for backwards-compat; ignored if provided
        description: Optional[str] = None,
        biblical_era: Optional[str] = None,
        role: Optional[str] = None,
    ) -> Optional[str]:
        """
        Get-or-create an entity, deduplicating by (search_key, biblical_era).

        Same biblical reality (regardless of casing, hyphenation, or category-
        perception) collapses to one graph node. Categories accumulate on that
        node rather than forking it. See ADR-0005 Phase 2.

        Note: the `normalized_name` parameter is accepted for backwards
        compatibility but is ignored; code computes both `search_key` and the
        display `normalized_name` deterministically from `name`.
        """
        safe_name = str(name)
        safe_category = str(category)
        safe_desc = str(description) if description else None
        safe_era = str(biblical_era) if biblical_era else "NotApplicable"
        safe_role = str(role) if role else None
        search_key = self.compute_search_key(safe_name)
        display_normalized_name = self.compute_display_normalized_name(safe_name)

        if not search_key:
            logging.warning(f"Skipping entity with empty search_key: name={safe_name!r}")
            return None

        # Cache lookup key — same biblical reality is one entry regardless of category.
        cache_key = (search_key, safe_era)
        if cache_key in self.entity_cache:
            cached_uuid = self.entity_cache[cache_key]
            # Even on cache hit, ensure this category is present on the entity.
            self._ensure_category_on_entity(cached_uuid, safe_category)
            return cached_uuid

        # Deterministic UUID derived from (search_key, era). Removes the previous
        # primitives' dependence on the LLM-supplied role and category.
        import weaviate.util
        entity_uuid = weaviate.util.generate_uuid5({
            "search_key": search_key,
            "biblical_era": safe_era,
        })

        # Probe Weaviate by UUID — fastest path when the entity already exists
        # at this exact (search_key, era).
        try:
            existing = self.entities.query.fetch_object_by_id(entity_uuid)
        except Exception as e:
            logging.warning(f"Error probing entity by UUID: {e}")
            existing = None

        # Fallback probe: legacy entities (pre-Phase-1) may have been written
        # with a different UUID scheme but happen to share the same (search_key, era).
        # If the backfill has run and populated search_key on those legacy rows,
        # we can find them. If not, the worst case is we briefly create a new
        # entity and the backfill merges it later.
        if not existing:
            try:
                results = self.entities.query.fetch_objects(
                    filters=(
                        wvc.query.Filter.by_property("search_key").equal(search_key) &
                        wvc.query.Filter.by_property("biblical_era").equal(safe_era)
                    ),
                    limit=1,
                )
                if results.objects:
                    legacy_uuid = str(results.objects[0].uuid)
                    self.entity_cache[cache_key] = legacy_uuid
                    self._ensure_category_on_entity(legacy_uuid, safe_category)
                    return legacy_uuid
            except Exception as e:
                logging.warning(f"Error searching legacy entity: {e}")

        if existing:
            # Already at the canonical UUID — just make sure this category is present.
            self.entity_cache[cache_key] = str(entity_uuid)
            self._ensure_category_on_entity(str(entity_uuid), safe_category)
            return str(entity_uuid)

        # Create new
        try:
            vector_text = safe_name
            if safe_desc:
                vector_text += f" - {safe_desc}"
            use_client_vectorization = os.getenv("USE_CLIENT_SIDE_VECTORIZATION", "true").lower() == "true"
            entity_vector = (
                get_ollama_embedding(vector_text, url=self.ollama_url, model_name=self.ollama_model)
                if use_client_vectorization else None
            )

            insert_kwargs = {
                "properties": {
                    "name": safe_name,
                    "search_key": search_key,
                    "category": safe_category,           # kept for backwards-compat
                    "categories": [safe_category],       # the new accumulating field
                    "normalized_name": display_normalized_name,
                    "description": safe_desc,
                    "biblical_era": safe_era,
                    "role": safe_role,
                },
                "uuid": entity_uuid,
            }
            if entity_vector:
                insert_kwargs["vector"] = entity_vector

            try:
                self.entities.data.insert(**insert_kwargs)
                logging.info(f"Created Entity: {safe_name} ({safe_category}) -> {entity_uuid}")
            except weaviate.exceptions.UnexpectedStatusCodeError as e:
                if e.status_code == 422:
                    self.entities.data.replace(**insert_kwargs)
                    logging.info(f"Replaced Entity: {safe_name} ({safe_category}) -> {entity_uuid}")
                else:
                    raise

            uuid_str = str(entity_uuid)
            self.entity_cache[cache_key] = uuid_str
            return uuid_str
        except Exception as e:
            logging.error(f"Error creating entity {name}: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return None

    def _ensure_category_on_entity(self, entity_uuid: str, category: str) -> None:
        """If `category` is not already in the entity's `categories` array, append it."""
        try:
            obj = self.entities.query.fetch_object_by_id(entity_uuid)
            if not obj:
                return
            existing = obj.properties.get("categories") or []
            if not isinstance(existing, list):
                existing = []
            if category in existing:
                return
            new_categories = existing + [category]
            self.entities.data.update(
                uuid=entity_uuid,
                properties={"categories": new_categories},
            )
            logging.debug(f"Appended category '{category}' to entity {entity_uuid} (now {new_categories})")
        except Exception as e:
            logging.warning(f"Failed to ensure category on entity {entity_uuid}: {e}")

    class EntityStub:
        def __init__(self, name, category, normalized_name=None, description=None, biblical_era=None, role=None):
            self.name = name
            self.category = category
            self.normalized_name = normalized_name
            self.description = description
            self.biblical_era = biblical_era
            self.role = role

    def load_entities_from_cache(self, cache_file: Path) -> List[Any]:
        """Load entities from local JSON cache file."""
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return [self.EntityStub(**item) for item in data]
        except Exception as e:
            logging.warning(f"Error loading entity cache {cache_file}: {e}")
            return []

    def save_entities_to_cache(self, entities: List[Any], cache_file: Path):
        """Save extracted entities to local JSON cache file."""
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            # normalized_name is no longer in the BAML schema (see ADR-0005);
            # we omit it from the cache too. Code computes search_key downstream.
            data = [
                {
                    "name": e.name,
                    "category": e.category,
                    "description": getattr(e, 'description', None),
                    "biblical_era": getattr(e, 'biblical_era', None),
                    "role": getattr(e, 'role', None)
                }
                for e in entities
            ]
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            logging.info(f"Saved {len(data)} entities to cache: {cache_file.name}")
        except Exception as e:
            logging.error(f"Error saving entity cache {cache_file}: {e}")

    def is_citation_mistake(self, entity_name: str) -> bool:
        """
        Detects if an entity is actually a scripture citation.
        Matches: 
          - "Rom. i. 4"
          - "Mark xvi. 11"
          - "Gen 4:5"
          - "1 Cor. v. 1"
        """
        # 1. Cleaning: Strip whitespace
        name = entity_name.strip()
        
        # 2. The "Book Chapter" Regex
        # Looks for:
        #  - Optional number prefix (1 Cor, 2 Kings) -> (?:[1-3]\s+)?
        #  - Name (Rom, Gen) -> [A-Z][a-z]+
        #  - Optional dot -> \.?
        #  - Whitespace -> \s+
        #  - Chapter (digits or roman numerals) -> ([0-9]+|[ivxlcIVXLC]+)
        citation_pattern = r"^(?:[1-3]\s+)?[A-Z][a-z]+\.?\s+([0-9]+|[ivxlcIVXLC]+)"
        
        # 3. Check Match
        import re
        if re.match(citation_pattern, name):
            return True
            
        return False

    
    def extract_entities(self, commentary_text: str, previous_entities: str = None) -> Tuple[List[Any], List[str]]:
        """Use BAML to extract entities from commentary text."""
        try:
            result = b.ExtractGillKnowledge(commentary_text, previous_entities=previous_entities)
            # Handle new return structure (ExtractionResult)
            if hasattr(result, 'entities'):
                 return result.entities, getattr(result, 'cross_references', [])
            return result, [] # Fallback if direct list (shouldn't happen with new BAML)
        except BamlError as e:
            logging.error(f"BAML error extracting entities: {e}")
            return [], []
            
    def load_alignment_json(self, page_name: str, alignment_dir: Path) -> List[Dict]:
        path = alignment_dir / f"{page_name}_alignment.json"
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []

    def parse_verse_ref(self, ref: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Parses 'BOOK CHAPTER:VERSE' into ('BOOK', 'CHAPTER:VERSE').
        Handles numeric prefixes like '1 JOHN 1:1'.
        """
        if not ref:
            return None, None
            
        import re
        # Match "BOOK NAME" "CHAPTER:VERSE" OR "BOOK NAME" "CHAPTER"
        # The chapter:verse (or just chapter) is always at the end
        match = re.search(r'^(.*?)\s+(\d+(?::\d+)?)$', ref)
        if match:
            return match.group(1).strip(), match.group(2).strip()
            
        return None, None

    def process_page(self, page_name: str, data_dir: Path, alignment_dir: Path, qwen_dir: Path, volume_override: int = None, recycle_entities: bool = False, entity_cache_dir: Optional[Path] = None) -> int:
        """Process a single page and ingest into Weaviate."""
        logging.info(f"Processing {page_name}...")
        
        volume, page_num = self.parse_page_info(page_name, volume_override)
        
        # Setup Cache Path
        if entity_cache_dir:
            # Namespace cache by Volume to avoid collisions
            cache_file = entity_cache_dir / f"vol{volume}_{page_name}_entities.json"
        else:
            cache_file = None


        
        # Load Entity Cache for this Page
        page_entity_cache = {}
        cache_dirty = False
        
        if cache_file and cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    page_entity_cache = json.load(f)
                logging.info(f"Loaded entity cache for {page_name}")
            except Exception as e:
                logging.warning(f"Failed to load cache {cache_file}: {e}")

        verse_entity_map = {}
        if recycle_entities:
             logging.info("♻️ Recycling Entities: Fetching existing links...")
             try:
                existing = self.chunks.query.fetch_objects(
                    filters=(wvc.query.Filter.by_property("page_number").equal(page_num) & 
                            wvc.query.Filter.by_property("volume").equal(volume)),
                    limit=1000, # Max per page
                    return_properties=["verse_ref"],
                    return_references=[wvc.query.QueryReference(link_on="mentions_entity")]
                )
                for obj in existing.objects:
                    ref = obj.properties.get("verse_ref")
                    if obj.references.get("mentions_entity"):
                         # Just need UUIDs
                         uuids = [str(o.uuid) for o in obj.references["mentions_entity"].objects]
                         verse_entity_map[ref] = uuids
                logging.info(f"♻️ Found existing entities for {len(verse_entity_map)} verses.")
             except Exception as e:
                 logging.warning(f"Failed to fetch existing entities: {e}")

        # Delete existing chunks
        try:
             self.chunks.data.delete_many(
                where=wvc.query.Filter.by_property("page_number").equal(page_num) & 
                      wvc.query.Filter.by_property("volume").equal(volume)
            )
             logging.info(f"Deleted existing chunks for Vol {volume} Page {page_num}")
        except Exception as e:
             logging.warning(f"Failed to delete existing chunks: {e}")
        
        # Load metadata
        metadata_path = data_dir / f"{page_name}_metadata.json"
        if not metadata_path.exists():
            logging.warning(f"Metadata not found: {metadata_path}")
            return 0
        
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        # Load alignments
        alignments = self.load_alignment_json(page_name, alignment_dir)
        if not alignments:
             logging.warning(f"No alignments found for {page_name}")
             return 0

        # Get file-specific volume for filename construction
        file_volume, _ = self.parse_page_info(page_name) 

        # Load previous page alignments (to detect spillover)
        prev_page_name = f"page{page_num - 1}_image{file_volume}"
        
        prev_alignments = self.load_alignment_json(prev_page_name, alignment_dir)
        prev_verse_refs = {a.get("verse_ref") for a in prev_alignments if a.get("verse_ref")}

        # Load next page alignments for lookahead
        next_page_name = f"page{page_num + 1}_image{file_volume}"
        next_alignments = self.load_alignment_json(next_page_name, alignment_dir)
        
        # Load Markdown Text (Current + Next for spanning)
        prev_md, current_md, next_md = self.load_adjacent_markdown(page_name, qwen_dir)
        full_context_text = current_md + "\n" + next_md
        
        chunks_ingested = 0
        recent_entities = []
        
        for i, alignment in enumerate(alignments):
            verse_ref = alignment.get("verse_ref")
            
            # Skip if this verse started on the previous page
            if verse_ref in prev_verse_refs:
                logging.info(f"Skipping {verse_ref} on {page_name} (handled by previous page)")
                continue
                
            start_phrase = alignment.get("start_phrase")
            end_fallback = alignment.get("end_phrase") # Use this if we can't find next verse
            
            # Handle 'boxes' list (new format) or 'highlight_box' (old format)
            highlight_box = alignment.get("highlight_box")
            boxes = alignment.get("boxes")
            
            scan_data = None
            if boxes and isinstance(boxes, list) and len(boxes) > 0:
                scan_data = boxes
            elif highlight_box:
                scan_data = highlight_box
            
            if not all([verse_ref, start_phrase]):
                continue
                
            # Determine Stop Phrase & Check Next Page for Spanning Boxes
            stop_phrase = None
            next_page_boxes = None
            
            if i + 1 < len(alignments):
                stop_phrase = alignments[i+1].get("start_phrase")
            elif next_alignments:
                # Check next page for continuation of THIS verse
                for next_align in next_alignments:
                    if next_align.get("verse_ref") == verse_ref:
                         # Found continuation!
                         nb = next_align.get("boxes") or next_align.get("highlight_box")
                         if nb:
                             if isinstance(nb, list) and len(nb) > 0 and isinstance(nb[0], list):
                                  # Already list of lists?
                                  next_page_boxes = nb
                             elif isinstance(nb, dict):
                                  next_page_boxes = [nb]
                             elif isinstance(nb, list):
                                  next_page_boxes = nb
                         
                         # CRITICAL FIX: Update end_fallback to the end of the NEXT page's chunk
                         # This allows the slicer to capture the full text if "stop_phrase" (next verse) isn't found
                         if next_align.get("end_phrase"):
                             end_fallback = next_align.get("end_phrase")
                             logging.info(f"  extended end_fallback for {verse_ref} to next page")
                    
                    if next_align.get("verse_ref") != verse_ref and not stop_phrase:
                        # This is the start of the Next verse, so our stop phrase is its start
                        stop_phrase = next_align.get("start_phrase")
                        # Don't break immediately if we are looking for continuation, 
                        # but typically continuation comes before next verse.
                        
            # Construct Composite Scan Data
            # Format: [ { "vol": 1, "page": 100, "boxes": [...] }, ... ]
            
            final_scan_data = []
            
            # Current Page
            if scan_data:
                 # Normalize scan_data to list of boxes
                 current_boxes_norm = scan_data if isinstance(scan_data, list) else [scan_data]
                 final_scan_data.append({
                     "vol": volume,
                     "page": page_num,
                     "boxes": current_boxes_norm
                 })
            
            # Next Page (if spanning)
            if next_page_boxes:
                 # CRITICAL FIX: Use the 'volume' variable which respects the override!
                 # Do NOT re-parse from filename as it might default to Vol 1 (legacy heuristic).
                 final_scan_data.append({
                     "vol": volume,
                     "page": page_num + 1,
                     "boxes": next_page_boxes
                 })
                 logging.info(f"Merged spanning boxes for {verse_ref} (Page {page_num} -> {page_num+1})")

            # Update scan_data variable for insertion
            # If we have structured data, use it. If effectively empty, None.
            scan_data_to_store = final_scan_data if final_scan_data else None
            
            # Slice Text
            commentary_text = self.slice_verse_text(full_context_text, start_phrase, stop_phrase, end_fallback)
            
            if not commentary_text:
                logging.warning(f"Could not extract text for {verse_ref}")
                continue
            
            # Extract Footnotes
            # Pass current_md and next_md separately so we can match refs to correct page definitions
            footnotes = self.extract_footnotes(commentary_text, current_md, next_md)
            
            # Clean text (remove footnotes and next-verse headers)
            commentary_text = self.clean_text(commentary_text)
            
            # Blob Strategy: Append footnotes to the content so they are vector-searchable, 
            # while keeping the 'footnotes' array separate for UI display.
            vector_content = commentary_text
            if footnotes:
                vector_content += "\n\nFootnotes:\n" + "\n".join(footnotes)
            
            # Process sentences
            sentence_data, lemma = self.process_sentences(verse_ref, commentary_text)
            
            # Meta extraction
            # Meta extraction
            parts = verse_ref.split()
            book = parts[0] if parts else metadata.get("book_name", "")
            
            # Handle Book Intro (e.g. "GENESIS")
            if len(parts) == 1:
                # No chapter/verse part
                chapter_val = metadata.get("chapter", 0)
                try:
                     # If metadata is empty string or None, default to 0
                    chapter = int(chapter_val) if chapter_val else 0
                except:
                    chapter = 0
            else:
                chapter_verse = parts[1]
                if ":" in chapter_verse:
                    try:
                        chapter = int(chapter_verse.split(":")[0])
                    except:
                        chapter = 0
                else:
                    # Case: "GENESIS 1" -> parts[1] is "1"
                    try:
                        chapter = int(chapter_verse)
                    except:
                        # Fallback for "GENESIS Intro" -> "Intro" is not int
                        chapter = 0
            
            verse_num = self.extract_verse_number(verse_ref)
            hebrew_data = metadata.get("hebrew_text") or {}
            greek_data = metadata.get("greek_text") or {}
            original_snippet = hebrew_data.get(verse_num, "") or greek_data.get(verse_num, "")
            
            # Extract Entities
            entity_uuids = []
            serialized_ents = []
            
            if recycle_entities and verse_ref in verse_entity_map:
                entity_uuids = verse_entity_map[verse_ref]
            else:
                # Check Cache
                if verse_ref in page_entity_cache:
                    logging.info(f"🟢 Cache HIT for {verse_ref}")
                    raw_ents = page_entity_cache[verse_ref]
                    for ent_dict in raw_ents:
                        uuid = self.get_or_create_entity(
                            ent_dict.get("name"), 
                            ent_dict.get("category"), 
                            ent_dict.get("normalized_name"),
                            ent_dict.get("description"),
                            ent_dict.get("biblical_era"),
                            ent_dict.get("role")
                        )
                        if uuid:
                            entity_uuids.append(uuid)
                    serialized_ents = raw_ents
                else:
                    logging.info(f"⚪ Cache MISS for {verse_ref}")
                    # LLM Extraction with rolling context hint for pronoun resolution
                    context_hint = ", ".join(recent_entities) if recent_entities else "None yet."
                    extracted_data, cross_refs = self.extract_entities(commentary_text, previous_entities=context_hint)
                    extracted_entities = extracted_data # ExtractGillKnowledge returns ExtractionResult
                    
                    # Detect if LLM flagged unresolved pronouns at page boundary
                    needs_resolution = any(ent.name == "UNRESOLVED_PRONOUN" for ent in extracted_entities)
                    
                    # Store in Cache
                    for entity in extracted_entities:
                        # REGEX GUARD: Check for "Fake People" (actually citations)
                        if self.is_citation_mistake(entity.name):
                            logging.info(f"🧹 Sweeping away citation artifact: '{entity.name}'")
                            # Add to cross_refs if possible, or just skip
                            if 'cross_refs' in locals():
                                # Normalize slightly if we want, but just appending is better than making a fake person
                                cross_refs.append(entity.name) 
                            continue

                        # Process and store
                        # Try to get description/role/era safely
                        desc = getattr(entity, 'description', None)
                        era = getattr(entity, 'biblical_era', None)
                        role = getattr(entity, 'role', None)
                        
                        # CRITICAL FIX: Do not create a graph node for the IOU flag!
                        if entity.name != "UNRESOLVED_PRONOUN":
                            # `normalized_name` is no longer extracted by BAML — passed as None;
                            # get_or_create_entity computes search_key + display normalized_name from `name`.
                            uuid = self.get_or_create_entity(entity.name, entity.category, None, desc, era, role)
                            if uuid:
                                entity_uuids.append(uuid)
                        
                        serialized_ents.append({
                            "name": entity.name, 
                            "category": entity.category, 
                            "normalized_name": entity.normalized_name,
                            "description": desc,
                            "biblical_era": era,
                            "role": role
                        })
                        
                        # Update rolling buffer for coreference resolution
                        if entity.name != "UNRESOLVED_PRONOUN" and entity.name not in recent_entities:
                            recent_entities.append(entity.name)
                    
                    # Trim buffer to last 10 explicit entities
                    recent_entities = recent_entities[-10:]
                    
                    page_entity_cache[verse_ref] = serialized_ents
                    cache_dirty = True
            
            # Ingest with retry logic
            MAX_RETRIES = 5
            use_client_vectorization = os.getenv("USE_CLIENT_SIDE_VECTORIZATION", "true").lower() == "true"
            inserted_successfully = False
            for attempt in range(MAX_RETRIES):
                try:
                    # Conditionally use Client-Side Vectorization
                    chunk_vector = get_ollama_embedding(vector_content, url=self.ollama_url, model_name=self.ollama_model) if use_client_vectorization else None
                    
                    insert_kwargs = {
                        "properties": {
                            "content": vector_content,
                            "verse_ref": verse_ref,
                            "book": self.parse_verse_ref(verse_ref)[0] if verse_ref else None,
                            "chapter": int(self.parse_verse_ref(verse_ref)[1].split(':')[0]) if self.parse_verse_ref(verse_ref)[1] else 0,
                            "volume": volume,
                            "page_number": page_num,
                            "lemma": lemma, # Store the extracted lemma for UI display
                            "scan_json": json.dumps(scan_data_to_store) if scan_data_to_store else None,
                            "sentence_data": json.dumps(sentence_data), # Serialized JSON blob
                            "footnotes": footnotes,
                            "scripture_refs": cross_refs if 'cross_refs' in locals() and cross_refs else None,
                            "needs_boundary_resolution": needs_resolution if 'needs_resolution' in locals() else False,
                            "entities": [ent['name'] for ent in serialized_ents if ent['name'] != "UNRESOLVED_PRONOUN"]
                        },
                        "uuid": weaviate.util.generate_uuid5({"verse_ref": verse_ref}) # Explicit UUID ensures idempotent retries
                    }
                    if entity_uuids:
                        insert_kwargs["references"] = {"mentions_entity": entity_uuids}
                    if chunk_vector:
                        insert_kwargs["vector"] = chunk_vector
                        
                    try:
                        self.chunks.data.insert(**insert_kwargs)
                        logging.debug(f"Ingested {verse_ref}")
                    except weaviate.exceptions.UnexpectedStatusCodeError as e:
                        if e.status_code == 422:
                            # If 422 (already exists), update/replace it instead
                            self.chunks.data.replace(**insert_kwargs)
                            logging.debug(f"🔄 Updated {verse_ref}")
                        else:
                            raise
                    
                    chunks_ingested += 1
                    inserted_successfully = True
                    break # Success!
                    
                except Exception as e:
                    if attempt == MAX_RETRIES - 1:
                        logging.error(f"Error ingesting {verse_ref} after {MAX_RETRIES} attempts: {e}")
                        self.has_failures = True
                    else:
                        delay = 2 ** attempt # 1s, 2s, 4s, 8s...
                        logging.warning(f"Weaviate busy/timeout inserting {verse_ref}. Retrying in {delay}s... (Attempt {attempt+1}/{MAX_RETRIES}) (Error: {e})")
                        time.sleep(delay)
        
        if cache_dirty and cache_file:
             try:
                 with open(cache_file, 'w', encoding='utf-8') as f:
                     json.dump(page_entity_cache, f, indent=2)
                 logging.info(f"💾 Saved entity cache for {page_name}")
             except Exception as e:
                 logging.error(f"Failed to save cache {cache_file}: {e}")

        return chunks_ingested
    
    def run_batch(self, data_dir: str, alignment_dir: str, qwen_subdir: str = "qwen_qwen3-vl-235b-a22b-thinking", page_filter: str = None, volume_override: int = None, recycle_entities: bool = False, limit: int = None, entity_cache_dir: str = "outputs/entities"):
        """Process all pages, optionally filtering by page name."""
        data_path = Path(data_dir)
        alignment_path = Path(alignment_dir)
        qwen_path = data_path / qwen_subdir
        cache_path = Path(entity_cache_dir)
        
        if not cache_path.exists():
            cache_path.mkdir(parents=True, exist_ok=True)
        
        alignment_files = list(alignment_path.glob("*_alignment.json"))
        
        # Sort files to ensure deterministic order for "first N" testing
        alignment_files.sort(key=lambda x: str(x.name))
        
        if page_filter:
            alignment_files = [f for f in alignment_files if f.name.replace("_alignment.json", "") == page_filter]
            logging.info(f"Filtered to {len(alignment_files)} files matching {page_filter}")
        else:
            logging.info(f"Found {len(alignment_files)} alignment files")

        if limit:
            logging.info(f"Limiting to first {limit} pages.")
            alignment_files = alignment_files[:limit]
        
        total_chunks = 0
        processed_pages = 0
        
        for align_file in alignment_files:
            page_name = align_file.name.replace("_alignment.json", "")
            try:
                chunks = self.process_page(page_name, data_path, alignment_path, qwen_path, volume_override, recycle_entities, cache_path)
                total_chunks += chunks
                processed_pages += 1
                if processed_pages % 10 == 0:
                    logging.info(f"Progress: {processed_pages}/{len(alignment_files)} pages, {total_chunks} chunks")
            except Exception as e:
                logging.error(f"Error processing {page_name}: {e}")
                
        logging.info(f"✅ Ingestion complete: {processed_pages} pages, {total_chunks} chunks")
        return total_chunks

    def clean_text(self, text: str) -> str:
        """
        Clean the commentary text:
        1. Remove footnote definitions (e.g. [^1]: ...)
        2. Remove trailing 'Ver. N.' or 'Verse N.' headers that belong to the next section.
        """
        # 1. Remove footnote definitions
        cleaned = re.sub(r'^\s*\[\^\d+\]:.*$', '', text, flags=re.MULTILINE)
        
        # 2. Collapse excessive newlines (often left by footnote removal)
        # 3 or more newlines -> 2 newlines (max 1 blank line)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        
        # 3. Merge split sentences (Basic Heuristic)
        # If line ends with non-terminal punctuation (char other than . ? ! " ' : or ]) 
        # AND next line starts with a word char (and not a bullet point or header), join them.
        # This fixes "as the \n\n Persic" -> "as the Persic" 
        # (Looking for spaces between newlines too)
        
        def merge_match(match):
            # match.group(1) is the preceding char
            # match.group(2) is the following char
            return f"{match.group(1)} {match.group(2)}"

        # Negative lookbehind for terminal chars: (?<![.?!;:"\]])
        # Followed by 1+ newlines and whitespace
        # Followed by a word char (but not a dash/bullet)
        # This is tricky with regex lookbehinds. Simpler to match the gap context.
        
        # Match: (Non-terminal char) (newlines) (Start of word)
        # Exclude common abbreviations if needed, but for now assuming clean text.
        # Using [^\.?!;:"\]] to match any char that is NOT a sentence ender. 
        # But we need to capture it to put it back.
        
        cleaned = re.sub(
            r'([^\.\?!;:"\]\)\s])\s*\n+\s*([a-zA-Z0-9])', 
            r'\1 \2', 
            cleaned
        )

        
        # 4. Remove trailing Verse headers (e.g. "Ver. 35." at end of string)
        # Matches "Ver. 35." or "Verse 35." optionally preceded by newlines, at the very end
        cleaned = re.sub(r'\n+\s*(?:Ver|Verse)\.?\s*\d+\.?\s*$', '', cleaned, flags=re.IGNORECASE)
        
        return cleaned.strip()

    def visualize_connections(self, limit: int = 50, output_file: str = "graph_debug.pdf"):
        """
        Generate a network graph visualization of chunks and their linked entities.
        Uses networkx to build the graph and matplotlib to save it as PDF.
        """
        logging.info(f"Generating graph visualization (limit={limit})...")
        
        try:
            # Fetch recent chunks with their entity references
            response = self.chunks.query.fetch_objects(
                limit=limit,
                return_properties=["verse_ref", "book"],
                return_references=[
                    wvc.query.QueryReference(
                        link_on="mentions_entity",
                        return_properties=["name", "category"]
                    )
                ]
            )
            
            if not response.objects:
                logging.warning("No data found to visualize.")
                return

            G = nx.DiGraph()
            
            chunk_nodes = []
            entity_nodes = []
            
            for obj in response.objects:
                verse_ref = obj.properties.get("verse_ref", "Unknown")
                
                # Add Chunk Node
                G.add_node(verse_ref, type="chunk", label=verse_ref)
                chunk_nodes.append(verse_ref)
                
                # Add Edges to Entities
                if obj.references.get("mentions_entity"):
                    for ent in obj.references["mentions_entity"].objects:
                        name = ent.properties.get("name")
                        category = ent.properties.get("category")
                        node_id = f"{name} ({category})"
                        
                        G.add_node(node_id, type="entity", label=name)
                        entity_nodes.append(node_id)
                        G.add_edge(verse_ref, node_id)
            
            logging.info(f"Graph built: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges.")
            
            if G.number_of_nodes() == 0:
                logging.info("Graph is empty.")
                return

            # Draw
            plt.figure(figsize=(12, 12))
            try:
                pos = nx.spring_layout(G, k=0.5, iterations=50)
                
                # Draw Chunks (Blue square)
                nx.draw_networkx_nodes(G, pos, nodelist=[n for n in chunk_nodes if n in G], node_color='skyblue', node_size=1500, node_shape='s', alpha=0.8)
                
                # Draw Entities (Green circle)
                nx.draw_networkx_nodes(G, pos, nodelist=[n for n in entity_nodes if n in G], node_color='lightgreen', node_size=1000, alpha=0.8)
                
                # Draw Edges
                nx.draw_networkx_edges(G, pos, width=1.0, alpha=0.5, arrows=True)
                
                # Labels
                labels = {n: n for n in G.nodes()}
                nx.draw_networkx_labels(G, pos, labels, font_size=8)
                
                plt.title("Weaviate Connection Graph (Sample)")
                plt.axis('off')
                
                plt.savefig(output_file, format="pdf", bbox_inches="tight")
                plt.close()
                logging.info(f"Graph saved to {output_file}")
            except Exception as e:
                 logging.error(f"Drawing failed: {e}")
            
        except Exception as e:
            logging.error(f"Visualization failed: {e}")

if __name__ == "__main__":
    # Base paths
    BASE_DIR = Path(os.getenv("COMMENTARY_DATA_DIR", os.getcwd()))
    
    DEFAULT_DATA_DIR = BASE_DIR / "volume1"
    DEFAULT_ALIGN_DIR = BASE_DIR / "artifacts" / "alignment" / "genesis"
    DEFAULT_ENTITY_DIR = BASE_DIR / "artifacts" / "entities"

    import argparse
    parser = argparse.ArgumentParser(description="Ingest Gill Commentary")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="Source data directory")
    parser.add_argument("--alignment-dir", default=str(DEFAULT_ALIGN_DIR), help="Alignment output directory")
    parser.add_argument("--weaviate-host", default="localhost", help="Weaviate host")
    parser.add_argument("--weaviate-port", type=int, default=80, help="Weaviate port")
    parser.add_argument("--page", help="Process only a specific page")
    parser.add_argument("--visualize", action="store_true", help="Generate PDF graph of current data")
    parser.add_argument("--volume", type=int, help="Override volume number")
    parser.add_argument("--recycle-entities", action="store_true", help="Reuse existing entities from DB (skips LLM)")
    parser.add_argument("--limit", type=int, help="Limit number of pages to process (for testing)")
    parser.add_argument("--entity-cache-dir", default=str(DEFAULT_ENTITY_DIR), help="Directory to cache entity extraction results")
    parser.add_argument("--ollama-url", default="http://localhost:11434/api/embeddings", help="Ollama embeddings API URL")
    parser.add_argument("--ollama-model", default="qwen3-embedding", help="Ollama model name for embeddings")
    
    args = parser.parse_args()
    
    # Intelligently derive volume from data_dir if not explicitly provided
    if not args.volume:
        try:
            data_path_name = Path(args.data_dir).resolve().name
            if 'volume' in data_path_name.lower():
                extracted = data_path_name.lower().replace('volume', '')
                if extracted.isdigit():
                    args.volume = int(extracted)
                    logging.info(f"Automatically derived Volume {args.volume} from data directory '{data_path_name}'")
        except Exception as e:
            logging.warning(f"Could not automatically detect volume from data-dir {args.data_dir}: {e}")
            
    print(f"Starting Ingestion Engine (Target Volume: {args.volume or 'Unknown'})")
    
    with GillIngestionEngine(args.weaviate_host, args.weaviate_port, args.ollama_url, args.ollama_model) as engine:
        if args.visualize:
            engine.visualize_connections()
        elif args.page:
            # Auto-detect qwen dir logic
            base_data = Path(args.data_dir)
            qwen_dir = next(base_data.glob("qwen*"), None)
            if not qwen_dir:
                qwen_dir = base_data / "qwen_qwen3-vl-235b-a22b-thinking"
             
            chunks = engine.process_page(
                args.page,
                base_data,
                Path(args.alignment_dir),
                qwen_dir,
                args.volume,
                args.recycle_entities,
                Path(args.entity_cache_dir)
            )
            print(f"[OK] Test complete: {chunks} chunks ingested for {args.page}")
        else:
            base_data = Path(args.data_dir)
            qwen_dir = next(base_data.glob("qwen*"), base_data / "qwen_qwen3-vl-235b-a22b-thinking")
            chunks = engine.run_batch(args.data_dir, args.alignment_dir, qwen_dir.name, None, args.volume, args.recycle_entities, args.limit, args.entity_cache_dir)
            print(f"[OK] Batch complete: {chunks} chunks total")
        
        if engine.has_failures:
            print("[ERROR] Ingestion finished with errors.")
            sys.exit(1)
