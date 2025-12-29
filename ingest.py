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
import json
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import nltk
from rapidfuzz import fuzz, process as fuzz_process
import weaviate
import weaviate.classes as wvc
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
    
    def __init__(self, weaviate_host: str = "localhost", weaviate_port: int = 80):
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
            
        # Get collection references
        self.entities = self.client.collections.get("TheologicalEntity")
        self.chunks = self.client.collections.get("CommentaryChunk")
        
        # Cache for entity deduplication
        self.entity_cache: Dict[Tuple[str, str], str] = {}  # (name, category) -> UUID
        
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

        parts = page_name.split("_")
        if len(parts) >= 2:
            page_num = int(parts[0].replace("page", ""))
            volume = int(parts[1].replace("image", ""))
            return volume, page_num
        return 1, 0  # Default fallback
    
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

    def extract_footnotes(self, text: str, context_text: str) -> List[str]:
        """Extract footnote definitions for references found in the text."""
        # Find refs like [^1], [^12] but NOT followed by a colon (which would indicate a definition)
        refs = re.findall(r'\[\^(\d+)\](?!:)', text)
        footnotes = []
        unique_refs = sorted(list(set(refs)), key=lambda x: int(x))
        
        for ref in unique_refs:
            # Search for definition [^ref]: ... at start of line
            pattern = re.compile(rf"^\[\^{ref}\]:\s*(.*)", re.MULTILINE)
            match = pattern.search(context_text)
            if match:
                defn = match.group(1).strip()
                footnotes.append(f"[{ref}] {defn}")
        
        return footnotes

    def process_sentences(self, verse_ref: str, full_text: str) -> List[Dict[str, Any]]:
        """Segment text into sentences and generate structured sentence data."""
        safe_ref = verse_ref.replace(" ", "_").replace(":", "_")
        sentences = nltk.sent_tokenize(full_text)
        
        structured_data = []
        for i, txt in enumerate(sentences):
            structured_data.append({
                "sentence_id": f"{safe_ref}_S{i:02d}",
                "text": txt.strip(),
                "index": i
            })
        
        return structured_data
    
    def extract_verse_number(self, verse_ref: str) -> str:
        """Extract verse number from reference."""
        if ":" in verse_ref:
            return verse_ref.split(":")[1].lstrip("0")
        return ""
    
    def get_or_create_entity(self, name: str, category: str, normalized_name: Optional[str] = None) -> str:
        """Get existing entity UUID or create new entity."""
        cache_key = (normalized_name or name, category)
        if cache_key in self.entity_cache:
            return self.entity_cache[cache_key]
        
        try:
            results = self.entities.query.fetch_objects(
                filters=(
                    wvc.query.Filter.by_property("name").equal(name) &
                    wvc.query.Filter.by_property("category").equal(category)
                ),
                limit=1
            )
            
            if results.objects:
                uuid = str(results.objects[0].uuid)
                self.entity_cache[cache_key] = uuid
                return uuid
        except Exception as e:
            logging.warning(f"Error searching for entity: {e}")
        
        try:
            uuid = self.entities.data.insert({
                "name": name,
                "category": category,
                "normalized_name": normalized_name
            })
            
            uuid_str = str(uuid)
            self.entity_cache[cache_key] = uuid_str
            return uuid_str
        except Exception as e:
            logging.error(f"Error creating entity {name}: {e}")
            return None
    
    def extract_entities(self, commentary_text: str) -> List[Any]:
        """Use BAML to extract entities from commentary text."""
        try:
            entities = b.ExtractGillKnowledge(commentary_text)
            return entities if entities else []
        except BamlError as e:
            logging.error(f"BAML error extracting entities: {e}")
            return []
            
    def load_alignment_json(self, page_name: str, alignment_dir: Path) -> List[Dict]:
        path = alignment_dir / f"{page_name}_alignment.json"
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []

    def process_page(self, page_name: str, data_dir: Path, alignment_dir: Path, qwen_dir: Path, volume_override: int = None, recycle_entities: bool = False) -> int:
        """Process a single page and ingest into Weaviate."""
        logging.info(f"Processing {page_name}...")
        
        volume, page_num = self.parse_page_info(page_name, volume_override)
        
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
                 file_volume, _ = self.parse_page_info(page_name) # Ensure consistent volume
                 final_scan_data.append({
                     "vol": file_volume,
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
            # We look for definitions in both current and next page (as the ref could be anywhere)
            footnotes = self.extract_footnotes(commentary_text, full_context_text)
            
            # Clean text (remove footnotes and next-verse headers)
            commentary_text = self.clean_text(commentary_text)
            
            # Process sentences
            sentence_data = self.process_sentences(verse_ref, commentary_text)
            
            # Meta extraction
            parts = verse_ref.split()
            book = parts[0] if parts else metadata.get("book_name", "")
            chapter_verse = parts[1] if len(parts) > 1 else ":"
            chapter = int(chapter_verse.split(":")[0]) if ":" in chapter_verse else metadata.get("chapter", 0)
            
            verse_num = self.extract_verse_number(verse_ref)
            hebrew_data = metadata.get("hebrew_text") or {}
            greek_data = metadata.get("greek_text") or {}
            original_snippet = hebrew_data.get(verse_num, "") or greek_data.get(verse_num, "")
            
            # Extract Entities
            entity_uuids = []
            if recycle_entities and verse_ref in verse_entity_map:
                entity_uuids = verse_entity_map[verse_ref]
                # If map has them, great. If we want hybrid (recycle + new), 
                # we'd need to extract too. But "recycle" implies skipping LLM.
            else:
                entities = self.extract_entities(commentary_text)
                for entity in entities:
                    uuid = self.get_or_create_entity(entity.name, entity.category, entity.normalized_name)
                    if uuid:
                        entity_uuids.append(uuid)
            
            # Ingest
            try:
                self.chunks.data.insert({
                    "content": commentary_text,
                    "verse_ref": verse_ref,
                    "book": book,
                    "chapter": chapter,
                    "volume": volume,
                    "page_number": page_num,
                    "original_text_snippet": original_snippet,
                    "scan_json": json.dumps(scan_data_to_store) if scan_data_to_store else None,
                    "sentence_data": sentence_data,
                    "footnotes": footnotes
                }, references={
                    "mentions_entity": entity_uuids
                } if entity_uuids else None)
                
                chunks_ingested += 1
                logging.debug(f"Ingested {verse_ref}")
                
            except Exception as e:
                logging.error(f"Error ingesting {verse_ref}: {e}")
        
        return chunks_ingested
    
    def run_batch(self, data_dir: str, alignment_dir: str, qwen_subdir: str = "qwen_qwen3-vl-235b-a22b-thinking", page_filter: str = None, volume_override: int = None, recycle_entities: bool = False, limit: int = None):
        """Process all pages, optionally filtering by page name."""
        data_path = Path(data_dir)
        alignment_path = Path(alignment_dir)
        qwen_path = data_path / qwen_subdir
        
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
                chunks = self.process_page(page_name, data_path, alignment_path, qwen_path, volume_override, recycle_entities)
                total_chunks += chunks
                processed_pages += 1
                if processed_pages % 10 == 0:
                    logging.info(f"Progress: {processed_pages}/{len(alignment_files)} pages, {total_chunks} chunks")
            except Exception as e:
                logging.error(f"Error processing {page_name}: {e}")
                
        logging.info(f"✅ Ingestion complete: {processed_pages} pages, {total_chunks} chunks")

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
    import argparse
    parser = argparse.ArgumentParser(description="Ingest Gill Commentary")
    parser.add_argument("--data-dir", default="extracted_images", help="Source data directory")
    parser.add_argument("--alignment-dir", default="outputs/alignment/genesis", help="Alignment output directory")
    parser.add_argument("--weaviate-host", default="localhost", help="Weaviate host")
    parser.add_argument("--weaviate-port", type=int, default=80, help="Weaviate port")
    parser.add_argument("--test-page", help="Process only a specific page")
    parser.add_argument("--visualize", action="store_true", help="Generate PDF graph of current data")
    parser.add_argument("--volume", type=int, help="Override volume number")
    parser.add_argument("--recycle-entities", action="store_true", help="Reuse existing entities from DB (skips LLM)")
    parser.add_argument("--limit", type=int, help="Limit number of pages to process (for testing)")
    
    args = parser.parse_args()
    
    with GillIngestionEngine(args.weaviate_host, args.weaviate_port) as engine:
        if args.visualize:
            engine.visualize_connections()
        elif args.test_page:
            # Auto-detect qwen dir logic
            base_data = Path(args.data_dir)
            qwen_dir = next(base_data.glob("qwen*"), None)
            if not qwen_dir:
                qwen_dir = base_data / "qwen_qwen3-vl-235b-a22b-thinking"
             
            chunks = engine.process_page(
                args.test_page,
                base_data,
                Path(args.alignment_dir),
                qwen_dir,
                args.volume,
                args.recycle_entities
            )
            print(f"✅ Test complete: {chunks} chunks ingested for {args.test_page}")
        else:
            base_data = Path(args.data_dir)
            qwen_dir = next(base_data.glob("qwen*"), base_data / "qwen_qwen3-vl-235b-a22b-thinking")
            chunks = engine.run_batch(args.data_dir, args.alignment_dir, qwen_dir.name, None, args.volume, args.recycle_entities, args.limit)
            print(f"✅ Batch complete: {chunks} chunks total")
