#!/usr/bin/env python3
"""
Weaviate Ingestion Pipeline for Gill Commentary.

This script processes aligned commentary pages and ingests them into Weaviate with:
- Fuzzy slicing to extract verse-specific commentary
- Sentence segmentation using NLTK
- Entity extraction via BAML
- Knowledge graph construction
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import nltk
from rapidfuzz import fuzz, process as fuzz_process
import weaviate
import weaviate.classes as wvc
from dotenv import load_dotenv

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
    
    def __init__(self, weaviate_host: str = "localhost", weaviate_port: int = 8080):
        """Initialize the ingestion engine."""
        # Connect to Weaviate with env var support
        weaviate_url = os.getenv("WEAVIATE_URL")
        weaviate_api_key = os.getenv("WEAVIATE_API_KEY")
        
        # Prepare headers for modules (e.g. text2vec-openai via OpenRouter)
        headers = {}
        if os.getenv("OPENROUTER_API_KEY"):
            headers["X-OpenAI-Api-Key"] = os.getenv("OPENROUTER_API_KEY")
            headers["X-OpenAI-BaseURL"] = "https://openrouter.ai/api/v1"
            
        if weaviate_url:
            logging.info(f"Connecting to Weaviate at {weaviate_url}")
            
            self.client = weaviate.connect_to_custom(
                http_host=weaviate_url.replace("http://", "").replace("https://", "").split(":")[0],
                http_port=int(weaviate_url.split(":")[-1]) if ":" in weaviate_url else 80,
                http_secure=weaviate_url.startswith("https"),
                grpc_host=weaviate_url.replace("http://", "").replace("https://", "").split(":")[0],
                grpc_port=50051,
                grpc_secure=weaviate_url.startswith("https"),
                headers=headers,
                auth_credentials=weaviate.auth.AuthApiKey(weaviate_api_key) if weaviate_api_key else None
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
    
    def parse_page_info(self, page_name: str) -> Tuple[int, int]:
        """
        Parse volume and page number from filename.
        
        Args:
            page_name: e.g., "page100_image1" (volume 1) or "page250_image7" (volume 7)
            
        Returns:
            Tuple of (volume, page_number)
        """
        # Extract image number as volume indicator
        # Format: page{number}_image{volume}
        parts = page_name.split("_")
        if len(parts) >= 2:
            page_num = int(parts[0].replace("page", ""))
            volume = int(parts[1].replace("image", ""))
            return volume, page_num
        return 1, 0  # Default fallback
    
    def load_adjacent_markdown(self, page_name: str, qwen_dir: Path) -> Tuple[str, str, str]:
        """
        Load current page and adjacent pages for cross-page verse handling.
        
        Args:
            page_name: Current page identifier
            qwen_dir: Directory containing markdown files
            
        Returns:
            Tuple of (previous_md, current_md, next_md)
        """
        # Parse page number
        volume, page_num = self.parse_page_info(page_name)
        
        # Load current page
        current_path = qwen_dir / f"{page_name}.md"
        current_md = ""
        if current_path.exists():
            with open(current_path, 'r', encoding='utf-8') as f:
                current_md = f.read()
        
        # Load previous page (if exists)
        prev_page_name = f"page{page_num - 1}_image{volume}"
        prev_path = qwen_dir / f"{prev_page_name}.md"
        prev_md = ""
        if prev_path.exists():
            with open(prev_path, 'r', encoding='utf-8') as f:
                prev_md = f.read()
        
        # Load next page (if exists)
        next_page_name = f"page{page_num + 1}_image{volume}"
        next_path = qwen_dir / f"{next_page_name}.md"
        next_md = ""
        if next_path.exists():
            with open(next_path, 'r', encoding='utf-8') as f:
                next_md = f.read()
        
        return prev_md, current_md, next_md
    
    def fuzzy_slice_text(self, full_text: str, start_phrase: str, end_phrase: str, 
                         prev_text: str = "", next_text: str = "") -> Optional[str]:
        """
        Use fuzzy matching to extract text between start_phrase and end_phrase.
        Handles cross-page verses by searching in adjacent page text.
        
        Args:
            full_text: The complete page markdown text
            start_phrase: The phrase marking the start of the verse commentary
            end_phrase: The phrase marking the end
            prev_text: Previous page markdown (for cross-page start)
            next_text: Next page markdown (for cross-page end)
            
        Returns:
            Extracted text or None if not found
        """
        # Combine with adjacent pages for better boundary detection
        extended_text = prev_text[-500:] + full_text + next_text[:500] if prev_text or next_text else full_text
        offset = len(prev_text[-500:]) if prev_text else 0
        
        # Find start position using partial ratio
        start_result = fuzz_process.extractOne(
            start_phrase.lower(),
            [extended_text[i:i+len(start_phrase)+50].lower() for i in range(len(extended_text))],
            scorer=fuzz.partial_ratio
        )
        
        if not start_result or start_result[1] < 60:
            logging.warning(f"Could not find start phrase: {start_phrase[:50]}...")
            return None
        
        start_idx = start_result[2]
        
        # Find end position (search from start)
        remaining_text = extended_text[start_idx:]
        end_result = fuzz_process.extractOne(
            end_phrase.lower(),
            [remaining_text[i:i+len(end_phrase)+50].lower() for i in range(len(remaining_text))],
            scorer=fuzz.partial_ratio
        )
        
        if not end_result or end_result[1] < 60:
            logging.warning(f"Could not find end phrase: {end_phrase[:50]}...")
            return None
        
        end_idx = start_idx + end_result[2] + len(end_phrase)
        
        # Extract and ensure we're within the actual page bounds (not in adjacent pages)
        extracted = extended_text[start_idx:end_idx].strip()
        
        # If extraction spans into adjacent pages, include the cross-page text
        return extracted
    
    def process_sentences(self, verse_ref: str, full_text: str) -> List[Dict[str, Any]]:
        """
        Segment text into sentences and generate structured sentence data.
        
        Args:
            verse_ref: Verse reference (e.g., "GEN 46:06")
            full_text: The commentary text to segment
            
        Returns:
            List of sentence dictionaries with id, text, and index
        """
        # Normalize ref: "GEN 46:06" -> "GEN_46_06"
        safe_ref = verse_ref.replace(" ", "_").replace(":", "_")
        
        # Tokenize into sentences
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
        """
        Extract verse number from reference.
        
        Args:
            verse_ref: e.g., "GEN 46:06"
            
        Returns:
            Verse number as string (e.g., "6")
        """
        # Split by colon and get the verse part
        if ":" in verse_ref:
            return verse_ref.split(":")[1].lstrip("0")  # Remove leading zeros
        return ""
    
    def get_or_create_entity(self, name: str, category: str, normalized_name: Optional[str] = None) -> str:
        """
        Get existing entity UUID or create new entity.
        
        Args:
            name: Entity name
            category: Entity category
            normalized_name: Normalized name for deduplication
            
        Returns:
            Entity UUID
        """
        # Use normalized name for cache key if available
        cache_key = (normalized_name or name, category)
        
        # Check cache first
        if cache_key in self.entity_cache:
            return self.entity_cache[cache_key]
        
        # Search for existing entity
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
        
        # Create new entity
        try:
            uuid = self.entities.data.insert({
                "name": name,
                "category": category,
                "normalized_name": normalized_name
            })
            
            uuid_str = str(uuid)
            self.entity_cache[cache_key] = uuid_str
            logging.debug(f"Created entity: {name} ({category})")
            return uuid_str
            
        except Exception as e:
            logging.error(f"Error creating entity {name}: {e}")
            return None
    
    def extract_entities(self, commentary_text: str) -> List[Any]:
        """
        Use BAML to extract entities from commentary text.
        
        Args:
            commentary_text: The commentary text to analyze
            
        Returns:
            List of GillEntity objects
        """
        try:
            entities = b.ExtractGillKnowledge(commentary_text)
            return entities if entities else []
        except BamlError as e:
            logging.error(f"BAML error extracting entities: {e}")
            return []
    
    def process_page(self, 
                     page_name: str,
                     data_dir: Path,
                     alignment_dir: Path,
                     qwen_dir: Path) -> int:
        """
        Process a single page and ingest into Weaviate.
        
        Args:
            page_name: Page identifier (e.g., "page100_image1")
            data_dir: Directory containing metadata files
            alignment_dir: Directory containing alignment JSON files
            qwen_dir: Directory containing Vision markdown files
            
        Returns:
            Number of chunks ingested
        """
        logging.info(f"Processing {page_name}...")
        
        # Parse volume and page number from filename
        volume, page_num = self.parse_page_info(page_name)
        
        # Load metadata
        metadata_path = data_dir / f"{page_name}_metadata.json"
        if not metadata_path.exists():
            logging.warning(f"Metadata not found: {metadata_path}")
            return 0
        
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        # Load alignment data
        alignment_path = alignment_dir / f"{page_name}_alignment.json"
        if not alignment_path.exists():
            logging.warning(f"Alignment not found: {alignment_path}")
            return 0
        
        with open(alignment_path, 'r', encoding='utf-8') as f:
            alignments = json.load(f)
        
        # Load Vision markdown with adjacent pages for cross-page handling
        prev_md, full_markdown, next_md = self.load_adjacent_markdown(page_name, qwen_dir)
        
        chunks_ingested = 0
        
        # Process each verse alignment
        for alignment in alignments:
            verse_ref = alignment.get("verse_ref")
            start_phrase = alignment.get("start_phrase")
            end_phrase = alignment.get("end_phrase")
            highlight_box = alignment.get("highlight_box")
            
            if not all([verse_ref, start_phrase, end_phrase]):
                logging.warning(f"Incomplete alignment data for {page_name}")
                continue
            
            # Fuzzy slice the commentary text (with cross-page support)
            commentary_text = self.fuzzy_slice_text(
                full_markdown, start_phrase, end_phrase,
                prev_text=prev_md, next_text=next_md
            )
            
            if not commentary_text:
                logging.warning(f"Could not extract text for {verse_ref}")
                continue
            
            # Process sentences
            sentence_data = self.process_sentences(verse_ref, commentary_text)
            
            # Extract book and chapter from verse_ref
            parts = verse_ref.split()
            book = parts[0] if parts else metadata.get("book_name", "")
            chapter_verse = parts[1] if len(parts) > 1 else ":"
            chapter = int(chapter_verse.split(":")[0]) if ":" in chapter_verse else metadata.get("chapter", 0)
            
            # Get Hebrew/Greek text if available
            verse_num = self.extract_verse_number(verse_ref)
            hebrew_text = metadata.get("hebrew_text", {}).get(verse_num, "")
            greek_text = metadata.get("greek_text", {}).get(verse_num, "")
            original_snippet = hebrew_text or greek_text
            
            # Extract entities
            entities = self.extract_entities(commentary_text)
            
            # Get or create entity UUIDs
            entity_uuids = []
            for entity in entities:
                uuid = self.get_or_create_entity(
                    name=entity.name,
                    category=entity.category,
                    normalized_name=entity.normalized_name
                )
                if uuid:
                    entity_uuids.append(uuid)
            
            # Create CommentaryChunk
            try:
                self.chunks.data.insert({
                    "content": commentary_text,
                    "verse_ref": verse_ref,
                    "book": book,
                    "chapter": chapter,
                    "volume": volume,
                    "page_number": page_num,
                    "original_text_snippet": original_snippet,
                    "scan_json": json.dumps(highlight_box),
                    "sentence_data": sentence_data
                }, references={
                    "mentions_entity": entity_uuids
                } if entity_uuids else None)
                
                chunks_ingested += 1
                logging.debug(f"Ingested {verse_ref} with {len(sentence_data)} sentences and {len(entity_uuids)} entities")
                
            except Exception as e:
                logging.error(f"Error ingesting {verse_ref}: {e}")
        
        return chunks_ingested
    
    def run_batch(self, 
                  data_dir: str,
                  alignment_dir: str, 
                  qwen_subdir: str = "qwen_qwen3-vl-235b-a22b-thinking"):
        """
        Process all pages in the data directory.
        
        Args:
            data_dir: Directory containing source data
            alignment_dir: Directory containing alignment outputs
            qwen_subdir: Subdirectory name for Vision markdown files
        """
        data_path = Path(data_dir)
        alignment_path = Path(alignment_dir)
        qwen_path = data_path / qwen_subdir
        
        # Find all alignment files
        alignment_files = list(alignment_path.glob("*_alignment.json"))
        
        logging.info(f"Found {len(alignment_files)} alignment files to process")
        
        total_chunks = 0
        processed_pages = 0
        
        for align_file in alignment_files:
            page_name = align_file.name.replace("_alignment.json", "")
            
            try:
                chunks = self.process_page(
                    page_name=page_name,
                    data_dir=data_path,
                    alignment_dir=alignment_path,
                    qwen_dir=qwen_path
                )
                total_chunks += chunks
                processed_pages += 1
                
                if processed_pages % 10 == 0:
                    logging.info(f"Progress: {processed_pages}/{len(alignment_files)} pages, {total_chunks} chunks ingested")
                    
            except Exception as e:
                logging.error(f"Error processing {page_name}: {e}")
        
        logging.info(f"✅ Ingestion complete: {processed_pages} pages, {total_chunks} chunks")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Ingest Gill Commentary into Weaviate")
    parser.add_argument("--data-dir", default="extracted_images", help="Source data directory")
    parser.add_argument("--alignment-dir", default="outputs/alignment/genesis", help="Alignment output directory")
    parser.add_argument("--weaviate-host", default="localhost", help="Weaviate host")
    parser.add_argument("--weaviate-port", type=int, default=8080, help="Weaviate port")
    parser.add_argument("--test-page", help="Process only a specific page (for testing)")
    
    args = parser.parse_args()
    
    with GillIngestionEngine(
        weaviate_host=args.weaviate_host,
        weaviate_port=args.weaviate_port
    ) as engine:
        if args.test_page:
            # Test mode: process single page
            chunks = engine.process_page(
                page_name=args.test_page,
                data_dir=Path(args.data_dir),
                alignment_dir=Path(args.alignment_dir),
                qwen_dir=Path(args.data_dir) / "qwen_qwen3-vl-235b-a22b-thinking"
            )
            print(f"✅ Test complete: {chunks} chunks ingested for {args.test_page}")
        else:
            # Batch mode: process all pages
            engine.run_batch(
                data_dir=args.data_dir,
                alignment_dir=args.alignment_dir
            )
