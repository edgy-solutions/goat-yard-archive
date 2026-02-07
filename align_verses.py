#!/usr/bin/env python3
"""
Verse Alignment Script for Grounded Gill Commentary.

Uses margin detection and fuzzy phrase matching to find bounding boxes
for verse commentary text in two-column OCR data.

Configurable via COMMENTARY_DATA_DIR env var.
"""
import os
import json
import asyncio
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from rapidfuzz import fuzz
from dotenv import load_dotenv
import re

load_dotenv()

# Get configurable base path
BASE_DIR = Path(os.getenv("COMMENTARY_DATA_DIR", os.getcwd()))


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('alignment.log', encoding='utf-8')
    ]
)

# Import BAML client
from baml_client import b
from baml_client.types import VerseChunk

class VerseAligner:
    """Aligns verse chunks to OCR bounding boxes."""
    
    def __init__(self, extracted_dir: str = None, output_dir: str = None):
        if extracted_dir is None:
            extracted_dir = BASE_DIR / "volume1"
            
        self.extracted_dir = Path(extracted_dir)
            
        if output_dir is None:
            # Default to alignment/volumeX if input is volumeX
            base_align = BASE_DIR / "artifacts" / "alignment"
            dir_name = self.extracted_dir.name
            
            # If input directory is 'volumeX', output to 'alignment/volumeX'
            if "volume" in dir_name.lower():
                output_dir = base_align / dir_name
            else:
                # Fallback to root alignment folder
                output_dir = base_align
            
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)
        
        # Configuration
        self.y_tolerance = 30  # Pixels for line grouping
        self.header_y_threshold = 650  # Skip words above this Y
        self.footnote_indent = 50  # Footnotes are indented this much from margin
        self.fuzzy_threshold = 50  # Match score threshold
        
        # Regex for verse markers in normalized markdown
        # Matches "Ver. 1." or "Ver. 12." and captures content until next "Ver." or end of string
        self.verse_pattern = re.compile(r'Ver\.\s*(\d+)\.\s*(.*?)(?=Ver\.\s*\d+\.|$)', re.DOTALL)
    
    def load_metadata(self, page_name: str) -> Dict:
        """Load metadata JSON for a page to get book/chapter info."""
        meta_path = self.extracted_dir / f"{page_name}_metadata.json"
        
        if not meta_path.exists():
            logging.warning(f"Metadata not found: {meta_path}")
            return {}
            
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Failed to load metadata: {e}")
            return {}
    
    def load_ocr(self, page_name: str) -> List[Dict]:
        """
        Load OCR JSON for a page.
        Prefers fixedup > reindexed > raw OCR.
        """
        # Try fixedup first (reindexed + vision model corrections)
        fixedup_path = self.extracted_dir / f"{page_name}_fixedup.json"
        reindexed_path = self.extracted_dir / f"{page_name}_reindexed.json"
        raw_path = self.extracted_dir / f"{page_name}_ocr.json"
        
        if fixedup_path.exists():
            ocr_path = fixedup_path
            logging.info(f"Using fixed-up OCR: {fixedup_path}")
        else:
            # If fixedup doesn't exist, ensure reindexed exists (generating from raw if necessary)
            if not reindexed_path.exists():
                if raw_path.exists():
                    logging.warning(f"Reindexed OCR not found for {page_name}. Auto-generating...")
                    try:
                        import reindex_ocr
                        # We need to make sure reindex_ocr can be imported or is in path
                        # Assuming it's in the same directory
                        reindex_ocr.process_page(page_name, self.extracted_dir)
                        
                        if not reindexed_path.exists():
                            raise FileNotFoundError(f"Failed to generate reindexed OCR: {reindexed_path}")
                            
                        logging.info(f"Successfully generated: {reindexed_path}")
                    except Exception as e:
                        logging.error(f"Error running reindexer: {e}")
                        raise
                else:
                    raise FileNotFoundError(f"Raw OCR not found for {page_name}: {raw_path}")
            
            logging.info(f"Using reindexed OCR: {reindexed_path}")
            ocr_path = reindexed_path
        
        with open(ocr_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Normalize to consistent format
        words = []
        for item in data:
            if isinstance(item, dict) and 'text' in item:
                left = item.get('left', 0)
                top = item.get('top', 0)
                width = item.get('width', 0)
                height = item.get('height', 0)
                words.append({
                    'text': item.get('text', ''),
                    'left': left,
                    'right': left + width,
                    'top': top,
                    'bottom': top + height,
                    'idx': len(words)
                })
        return words
    
    def load_markdown(self, page_name: str) -> str:
        """Load markdown text for a page from vision model output."""
        # Try vision model output directory first (qwen subdirectory)
        vision_dirs = list(self.extracted_dir.glob("qwen*"))
        if vision_dirs:
            # Try normalized markdown first
            norm_md_path = vision_dirs[0] / f"{page_name}_normalized.md"
            if norm_md_path.exists():
                logging.info(f"Using normalized markdown: {norm_md_path}")
                with open(norm_md_path, 'r', encoding='utf-8') as f:
                    return f.read()

            # Fallback to raw markdown in vision dir
            md_path = vision_dirs[0] / f"{page_name}.md"
            if md_path.exists():
                logging.info(f"Using vision model markdown: {md_path}")
                with open(md_path, 'r', encoding='utf-8') as f:
                    return f.read()
        
        # Fall back to main directory
        md_path = self.extracted_dir / f"{page_name}.md"
        if not md_path.exists():
            raise FileNotFoundError(f"Markdown not found: {md_path}")
        
        with open(md_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def extract_verses_regex(self, text: str, metadata: Dict) -> List[Dict]:
        """
        Extract verses using Regex from normalized markdown.
        Captures spillover text (before first marker) as the start verse from metadata.
        """
        logging.info(f"Extracting verses regex. Metadata keys: {list(metadata.keys())}")
        verses = []
        book = metadata.get('book_name', 'Unknown')
        chapter = metadata.get('chapter', '?')
        verse_range = metadata.get('verse', '')
        
        # Try to parse start verse from metadata (e.g. "18-22" -> "18")
        start_verse_ref = "?"
        if verse_range:
            parts = verse_range.split('-')
            if parts and parts[0].strip().isdigit():
                start_verse_ref = parts[0].strip()
        
        # Remove footnote definitions from the end of the text
        # They typically start with [^1]: ...
        # Find the first occurrence of a footnote definition and truncate text there
        footnote_match = re.search(r'\n\s*\[\^\d+\]:', text)
        if footnote_match:
            text = text[:footnote_match.start()]
            
        matches = list(self.verse_pattern.finditer(text))
        
        # Handle spillover text (content before first "Ver.")
        if matches:
            first_match_start = matches[0].start()
            if first_match_start > 0:
                spillover_content = text[:first_match_start].strip()
                if spillover_content:
                    # Determine verse number for spillover
                    # It should be the verse BEFORE the first actual match
                    try:
                        first_verse_num = int(matches[0].group(1))
                        if first_verse_num == 1:
                            # Check for specific "Chapter" header in spillover to split Book Intro / Prev Chapter from Chapter Intro
                            # Matches "# Chapter I", "# Chapter 1", etc.
                            header_match = re.search(r'(?m)^#\s*Chapter\s+[IVXLC\d]+', spillover_content)
                            
                            if header_match:
                                # Found header! Split.
                                split_idx = header_match.start()
                                pre_content = spillover_content[:split_idx].strip()
                                post_content = spillover_content[split_idx:].strip()

                                if pre_content:
                                    # Determine ref for the pre-content
                                    pre_ref = f"{book}" # Book Intro (e.g. "GENESIS")
                                    try:
                                        c_int = int(chapter)
                                        if c_int > 1:
                                            pre_ref = f"{book} {c_int - 1} End"
                                    except:
                                        pass
                                    
                                    verses.append(self._create_verse_chunk(pre_content, pre_ref))
                                
                                # The rest is the distinct Chapter Intro
                                # FIX: Strip the 'Chapter X' header itself from the content to avoid redundancy
                                # post_content starts at split_idx (the start of '# Chapter...').
                                # We want to remove that line.
                                # Split by newline, skip the first line (the header), rejoin.
                                post_lines = post_content.split('\n')
                                if len(post_lines) > 0 and 'Chapter' in post_lines[0]:
                                     # Drop the header line
                                     post_content = '\n'.join(post_lines[1:]).strip()
                                
                                spillover_content = post_content
                                spillover_ref = f"{book} {chapter}"
                            else:
                                # No header split found, treat all as intro
                                spillover_ref = f"{book} {chapter}"

                        else:
                            # Normal spillover from previous verse
                            spillover_num = first_verse_num - 1
                            spillover_ref = f"{book} {chapter}:{spillover_num}"
                    except ValueError:
                        # Fallback to metadata start if parsing fails
                        spillover_ref = f"{book} {chapter}:{start_verse_ref}"

                    verses.append(self._create_verse_chunk(
                        spillover_content, 
                        spillover_ref
                    ))
        elif text.strip():
            # No markers found, treat whole text as one chunk (belonging to start verse)
            verses.append(self._create_verse_chunk(
                text.strip(),
                f"{book} {chapter}:{start_verse_ref}"
            ))
            return [v for v in verses if v]
        
        # Handle matches
        found_verse_nums = set()
        for match in matches:
            verse_num = match.group(1)
            content = match.group(2).strip()
            
            if not content:
                continue
            
            found_verse_nums.add(int(verse_num))
            verses.append(self._create_verse_chunk(
                content,
                f"{book} {chapter}:{verse_num}"
            ))
            
        # Validation: Check for missing verses based on metadata range
        if verse_range:
            parts = verse_range.split('-')
            if len(parts) >= 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
                start_v = int(parts[0].strip())
                end_v = int(parts[1].strip())
                expected_verses = set(range(start_v, end_v + 1))
                
                # Check what we found
                missing_verses = expected_verses - found_verse_nums
                
                with open("debug_missing_verses.txt", "w") as df:
                    df.write(f"Verse Range: {verse_range}\n")
                    df.write(f"Expected: {expected_verses}\n")
                    df.write(f"Found: {found_verse_nums}\n")
                    df.write(f"Missing: {missing_verses}\n")
                
                if missing_verses:
                    sorted_missing = sorted(list(missing_verses))
                    logging.warning(f"  [Verify] Expected: {start_v}-{end_v}, Found: {sorted(list(found_verse_nums))}")
                    logging.warning(f"  [Verify] Missing markers: {sorted_missing}")
                    logging.warning(f"  (These may be merged into the previous verse or spillover due to missing 'Ver.' labels)")

        return [v for v in verses if v]

    def _create_verse_chunk(self, content: str, ref: str) -> Dict:
        """Helper to create verse chunk dict."""
        # Clean up content (remove newlines, extra spaces)
        content_clean = ' '.join(content.split())
        words = content_clean.split()
        
        if not words:
            return None
            
        start_phrase = ' '.join(words[:15]) # First ~15 words
        end_phrase = ' '.join(words[-15:])  # Last ~15 words
        
        return {
            'verse_ref': ref,
            'start_phrase': start_phrase,
            'end_phrase': end_phrase
        }

    def extract_verses(self, markdown_text: str, page_name: str = None) -> List[Dict]:
        """
        Extract verse chunks using Regex first, falling back to BAML.
        """
        if not markdown_text:
            return []

        # Try Regex first if we have page context
        if page_name:
            metadata = self.load_metadata(page_name)
            regex_verses = self.extract_verses_regex(markdown_text, metadata)
            
            if regex_verses:
                logging.info(f"Extracted {len(regex_verses)} verses via Regex")
                return regex_verses
            else:
                logging.warning("Regex extraction returned no verses, falling back to BAML")

        # Fallback to BAML
        try:
            # BAML function is async, wrap with asyncio.run()
            baml_verses = asyncio.run(b.ExtractVersesFromMarkdown(markdown_text))
            logging.info(f"Extracted {len(baml_verses)} verses via BAML")
            return [{'verse_ref': v.verse_ref, 'start_phrase': v.start_phrase, 'end_phrase': v.end_phrase} 
                    for v in baml_verses]
        except Exception as e:
            logging.error(f"BAML extraction failed: {e}")
            return []

    
    def group_into_lines(self, words: List[Dict]) -> List[List[Dict]]:
        """Group words into lines based on TOP coordinate proximity."""
        if not words:
            return []
        
        sorted_words = sorted(words, key=lambda w: (w['top'], w['left']))
        lines = []
        
        for word in sorted_words:
            placed = False
            for line in lines:
                for existing in line:
                    if abs(word['top'] - existing['top']) <= self.y_tolerance:
                        line.append(word)
                        placed = True
                        break
                if placed:
                    break
            if not placed:
                lines.append([word])
        
        return lines
    
    def detect_column_bounds(self, words: List[Dict]) -> Dict:
        """
        Detect column boundaries using leftmost/rightmost word averaging.
        Returns dict with left_col and right_col, each having 'left', 'right' edges.
        """
        if not words:
            return {'left_col': {'left': 0, 'right': 0}, 'right_col': {'left': 0, 'right': 0}}
        
        # Global bounds
        all_left = min(w['left'] for w in words)
        all_right = max(w['right'] for w in words)
        page_width = all_right - all_left
        column_split = all_left + (page_width * 0.48)
        
        # Split into columns
        left_words = [w for w in words if w['left'] < column_split]
        right_words = [w for w in words if w['left'] >= column_split]
        
        # Group into lines
        left_lines = self.group_into_lines(left_words)
        right_lines = self.group_into_lines(right_words)
        
        # Get leftmost and rightmost per line
        def get_edge_words(lines):
            leftmost = []
            rightmost = []
            for line in lines:
                if line:
                    leftmost.append(min(line, key=lambda w: w['left']))
                    rightmost.append(max(line, key=lambda w: w['right']))
            return leftmost, rightmost
        
        left_leftmost, left_rightmost = get_edge_words(left_lines)
        right_leftmost, right_rightmost = get_edge_words(right_lines)
        
        # Compute averages
        def avg(lst, key):
            if not lst:
                return 0
            return sum(w[key] for w in lst) / len(lst)
        
        return {
            'left_col': {
                'left': avg(left_leftmost, 'left'),
                'right': avg(left_rightmost, 'right')
            },
            'right_col': {
                'left': avg(right_leftmost, 'left'),
                'right': avg(right_rightmost, 'right')
            },
            'column_split': column_split,
            'header_y': self.header_y_threshold
        }
    

    
    def is_body_word(self, word: Dict, bounds: Dict) -> bool:
        """Check if word is in body text (not header).
        
        Note: Footnote filtering happens in reindex_ocr.py, not here.
        The reindexed OCR places footnotes after body text, so we don't
        need to filter them here - we just skip the header.
        """
        # Skip header
        if word['top'] < bounds['header_y']:
            return False
        
        return True
    
    def fuzzy_find_phrase(self, phrase: str, words: List[Dict], 
                          start_idx: int = 0, bounds: Dict = None,
                          is_end_phrase: bool = False) -> Tuple[int, int, float]:
        """
        Find phrase in words using cascading threshold fuzzy matching.
        
        Strategy:
        1. Try FULL phrase with high threshold (80%)
        2. Back off in increments (70%, 60%, 50%, 40%) until match found
        
        Returns (start_word_idx, end_word_idx, score).
        """
        if not phrase or not words:
            return -1, -1, 0.0
        
        phrase_words = phrase.split()
        if len(phrase_words) == 0:
            return -1, -1, 0.0
        
        # Filter to body words only (skip footnotes and headers)
        body_indices = []
        for i, w in enumerate(words):
            if i >= start_idx:
                # Skip words marked as footnotes
                if w.get('is_footnote', False):
                    continue
                if bounds is None or self.is_body_word(w, bounds):
                    body_indices.append(i)
        
        # Cascading thresholds: try high first, back off
        thresholds = [80, 70, 60, 50, 40]
        best_score = 0.0
        
        for threshold in thresholds:
            # Use FULL phrase for this threshold attempt
            search_phrase = ' '.join(phrase_words)
            window_size = len(phrase_words)
            
            if len(body_indices) < window_size:
                continue
            
            best_score = 0
            best_start = -1
            best_end = -1
            
            # Slide window over body words
            for i in range(len(body_indices) - window_size + 1):
                window_indices = body_indices[i:i + window_size]
                
                # First-word check: ensure the first word matches reasonably well
                # This prevents 'who' from matching 'And' in phrase starts
                #first_ocr = words[window_indices[0]]['text'].lower().strip('.,;:!?"\'')
                #first_phrase = phrase_words[0].lower().strip('.,;:!?"\'')
                #first_word_score = fuzz.ratio(first_ocr, first_phrase)
                #if first_word_score < 60:  # First word must have decent match
                #   continue
                
                window_text = ' '.join(words[idx]['text'] for idx in window_indices)
                
                score = fuzz.ratio(search_phrase.lower(), window_text.lower())
                
                if score > best_score:
                    best_score = score
                    best_start = window_indices[0]
                    best_end = window_indices[-1]
            
            # If we found a match above this threshold, return it
            if best_score >= threshold:
                logging.debug(f"  Matched at threshold {threshold}% with score {best_score:.1f}")
                return best_start, best_end, best_score
            
            # If no match at this threshold, try fewer words (back off window size)
            if threshold <= 60:  # Only back off window size at lower thresholds
                for fewer_words in [min(15, len(phrase_words)), min(10, len(phrase_words)), min(7, len(phrase_words))]:
                    if fewer_words >= len(phrase_words):
                        continue  # Already tried full phrase
                    
                    if is_end_phrase:
                        search_phrase = ' '.join(phrase_words[-fewer_words:])
                    else:
                        search_phrase = ' '.join(phrase_words[:fewer_words])
                    
                    window_size = fewer_words
                    
                    if len(body_indices) < window_size:
                        continue
                    
                    best_score = 0
                    best_start = -1
                    best_end = -1
                    
                    for i in range(len(body_indices) - window_size + 1):
                        window_indices = body_indices[i:i + window_size]
                        window_text = ' '.join(words[idx]['text'] for idx in window_indices)
                        
                        score = fuzz.ratio(search_phrase.lower(), window_text.lower())
                        
                        if score > best_score:
                            best_score = score
                            best_start = window_indices[0]
                            best_end = window_indices[-1]
                    
                    if best_score >= threshold:
                        logging.debug(f"  Matched with {fewer_words} words at {threshold}% score {best_score:.1f}")
                        return best_start, best_end, best_score
        
        return -1, -1, best_score

    
    def fuzzy_find_phrase_bounded(self, phrase: str, words: List[Dict], 
                                   start_idx: int, max_end_idx: int, 
                                   bounds: Dict = None) -> Tuple[int, int, float]:
        """
        Find the BEST match for phrase within bounded range [start_idx, max_end_idx].
        
        Unlike fuzzy_find_phrase, this searches the ENTIRE range and returns the BEST match
        (highest score) within the bounds. This prevents false positive matches earlier
        when the true match is later in the range.
        
        Returns (match_start_idx, match_end_idx, score).
        """
        if not phrase or not words:
            return -1, -1, 0.0
        
        phrase_words = phrase.split()
        if len(phrase_words) == 0:
            return -1, -1, 0.0
        
        # Filter to body words within the range (skip footnotes and headers)
        body_indices = []
        for i, w in enumerate(words):
            if start_idx <= i <= max_end_idx:
                # Skip words marked as footnotes
                if w.get('is_footnote', False):
                    continue
                if bounds is None or self.is_body_word(w, bounds):
                    body_indices.append(i)
        
        if not body_indices:
            return -1, -1, 0.0
        
        # Use full phrase for matching
        search_phrase = ' '.join(phrase_words)
        window_size = len(phrase_words)
        
        if len(body_indices) < window_size:
            return -1, -1, 0.0
        
        best_score = 0
        best_start = -1
        best_end = -1
        
        # Search through all possible windows in the range
        for i in range(len(body_indices) - window_size + 1):
            window_indices = body_indices[i:i + window_size]
            
            # Ensure the match ends within bounds
            if window_indices[-1] > max_end_idx:
                continue
            
            window_text = ' '.join(words[idx]['text'] for idx in window_indices)
            score = fuzz.ratio(search_phrase.lower(), window_text.lower())
            
            if score > best_score:
                best_score = score
                best_start = window_indices[0]
                best_end = window_indices[-1]
        
        # Return best match if above minimum threshold (40%)
        if best_score >= 40:
            return best_start, best_end, best_score
        
        return -1, -1, best_score

    def get_word_column(self, word: Dict, bounds: Dict) -> str:
        """Determine which column a word is in."""
        if word['left'] < bounds['column_split']:
            return 'left'
        return 'right'
    
    def calculate_boxes(self, start_idx: int, end_idx: int, 
                        words: List[Dict], bounds: Dict) -> List[Dict]:
        """
        Calculate bounding box(es) for the word range.
        Uses actual word positions for left/right bounds (verse-specific).
        Returns 1 box if same column, 2 boxes if spanning columns.
        """
        if start_idx < 0 or end_idx < 0:
            return []
        
        start_word = words[start_idx]
        end_word = words[end_idx]
        
        start_col = self.get_word_column(start_word, bounds)
        end_col = self.get_word_column(end_word, bounds)
        
        # Collect all words in range, excluding footnotes
        # Only skip words that are marked as footnotes by the fixup algorithm
        # Don't use hardcoded Y threshold since body text can extend past Y=4000
        range_words = []
        for i in range(start_idx, end_idx + 1):
            w = words[i]
            # Skip if marked as footnote
            if w.get('is_footnote', False):
                continue
            # Skip if not body word (header check)
            if not self.is_body_word(w, bounds):
                continue
            range_words.append(w)
        
        if not range_words:
            return []
        
        # Group range words into lines
        range_lines = self.group_into_lines(range_words)
        
        # Get leftmost and rightmost word from each line
        def get_line_bounds(line_words):
            """Get the leftmost left and rightmost right from a line's words."""
            if not line_words:
                return None, None
            leftmost = min(w['left'] for w in line_words)
            rightmost = max(w['right'] for w in line_words)
            return leftmost, rightmost
        
        if start_col == end_col:
            # Single column - one box using actual word bounds
            min_left = min(w['left'] for w in range_words)
            max_right = max(w['right'] for w in range_words)
            min_top = min(w['top'] for w in range_words)
            max_bottom = max(w['bottom'] for w in range_words)
            
            return [{
                'x': int(min_left),
                'y': int(min_top),
                'w': int(max_right - min_left),
                'h': int(max_bottom - min_top)
            }]
        else:
            # Spanning columns - two boxes
            # Split words by column
            left_words = [w for w in range_words if self.get_word_column(w, bounds) == 'left']
            right_words = [w for w in range_words if self.get_word_column(w, bounds) == 'right']
            
            boxes = []
            
            # Left column box using actual word bounds
            if left_words:
                boxes.append({
                    'x': int(min(w['left'] for w in left_words)),
                    'y': int(min(w['top'] for w in left_words)),
                    'w': int(max(w['right'] for w in left_words) - min(w['left'] for w in left_words)),
                    'h': int(max(w['bottom'] for w in left_words) - min(w['top'] for w in left_words))
                })
            
            # Right column box using actual word bounds
            if right_words:
                boxes.append({
                    'x': int(min(w['left'] for w in right_words)),
                    'y': int(min(w['top'] for w in right_words)),
                    'w': int(max(w['right'] for w in right_words) - min(w['left'] for w in right_words)),
                    'h': int(max(w['bottom'] for w in right_words) - min(w['top'] for w in right_words))
                })
            
            return boxes

    
    def generate_debug_image(self, page_name: str, results: List[Dict], words: List[Dict] = None, bounds: Dict = None):
        """Generate debug image with yellow highlight boxes and footnote regions overlaid."""
        try:
            from PIL import Image, ImageDraw
            
            # Find image file
            for ext in ['.png', '.jpg', '.jpeg']:
                img_path = self.extracted_dir / f"{page_name}{ext}"
                if img_path.exists():
                    break
            else:
                logging.warning(f"No image found for {page_name}")
                return
            
            img = Image.open(img_path).convert('RGBA')
            
            # Create overlay for transparency
            overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            
            # Draw footnote regions first (so verse highlights appear on top)
            if words and bounds:
                self._draw_footnote_regions(draw, words, bounds)
            
            # Yellow highlight with transparency (like a real highlighter)
            highlight_color = (255, 255, 0, 80)  # Yellow with 80/255 opacity
            outline_color = (200, 150, 0, 255)   # Darker gold/orange for outline
            
            for result in results:
                for box in result.get('boxes', []):
                    x, y, w, h = box['x'], box['y'], box['w'], box['h']
                    draw.rectangle([x, y, x + w, y + h], fill=highlight_color, outline=outline_color, width=3)
            
            # Draw verse markers (colored by confidence)
            for result in results:
                verse_ref = result.get('verse_ref', '')
                start_idx = result.get('start_idx', 0)
                score = result.get('score', 0)
                
                # High confidence -> Green, Low -> Red
                if score >= 60:
                    marker_color = (0, 255, 0, 255)  # Green
                else:
                    marker_color = (255, 0, 0, 255)  # Red
                
                # Extract verse number from ref (e.g. "GENESIS 48:18" -> "18")
                match = re.search(r':(\d+)$', verse_ref)
                if match and start_idx > 0:
                    verse_num = match.group(1)
                    
                    # Search backwards for marker (Ver. N.)
                    # Typically 1-3 words: "Ver.", "18." or "Ver", ".", "18", "."
                    marker_words = []
                    search_limit = 5
                    found_num = False
                    found_ver = False
                    
                    # Look back up to search_limit words
                    current_idx = start_idx - 1
                    words_checked = 0
                    
                    possible_marker_words = []
                    
                    while current_idx >= 0 and words_checked < search_limit:
                        w = words[current_idx]
                        txt = w['text'].strip('.,;:').lower()
                        
                        # Add to potential marker chain
                        possible_marker_words.append(w)
                        
                        if txt == verse_num:
                            found_num = True
                        elif 'ver' in txt or 'v' == txt:
                            found_ver = True
                        
                        # If we found both parts, stop
                        if found_num and found_ver:
                            marker_words = possible_marker_words
                            break
                            
                        current_idx -= 1
                        words_checked += 1
                        
                    if marker_words:
                        # Calculate box for marker words
                        min_x = min(w['left'] for w in marker_words)
                        min_y = min(w['top'] for w in marker_words)
                        max_x = max(w['right'] for w in marker_words)
                        max_y = max(w['bottom'] for w in marker_words)
                        
                        # Draw box for "Ver. XX."
                        draw.rectangle([min_x, min_y, max_x, max_y], 
                                     outline=marker_color, width=4)
                    else:
                        logging.warning(f"  [Debug Image] Marker for {verse_ref} not found near index {start_idx}")

            # Composite overlay onto image
            img = Image.alpha_composite(img, overlay)
            
            debug_path = self.output_dir / f"{page_name}_debug.png"
            img.save(debug_path)
            logging.info(f"Debug image saved: {debug_path}")
            
        except Exception as e:
            logging.error(f"Debug image generation failed: {e}")
    
    def _draw_footnote_regions(self, draw, words: List[Dict], bounds: Dict):
        """Draw semi-transparent footnote regions on the debug image."""
        from reindex_ocr import group_into_lines, find_column_margin, find_footnote_start
        
        # Get page dimensions
        all_top = min(w['top'] for w in words)
        all_bottom = max(w['bottom'] for w in words)
        all_left = min(w['left'] for w in words)
        all_right = max(w['right'] for w in words)
        
        column_split = bounds['column_split']
        header_y = all_top + ((all_bottom - all_top) * 0.03)
        
        # Split into columns
        left_words = [w for w in words if w['left'] < column_split and w['top'] > header_y]
        right_words = [w for w in words if w['left'] >= column_split and w['top'] > header_y]
        
        # Group into lines
        left_lines = group_into_lines(left_words)
        right_lines = group_into_lines(right_words)
        
        # Find margins and footnote starts
        left_margin = find_column_margin(left_lines)
        right_margin = find_column_margin(right_lines)
        
        left_fn_start = find_footnote_start(left_lines, left_margin)
        right_fn_start = find_footnote_start(right_lines, right_margin)
        
        # Draw left footnote region (red, transparent) - use actual word positions
        if left_fn_start < len(left_lines):
            fn_lines = left_lines[left_fn_start:]
            if fn_lines:
                min_y = min(min(w['top'] for w in line) for line in fn_lines)
                max_y = max(max(w['bottom'] for w in line) for line in fn_lines)
                # Use actual rightmost word position from footnote words
                max_x = max(max(w['right'] for w in line) for line in fn_lines)
                draw.rectangle([all_left, min_y, max_x, max_y], 
                              fill=(255, 0, 0, 60), outline=(255, 0, 0, 200), width=2)
        
        # Draw right footnote region (blue, transparent) - start at right_margin
        if right_fn_start < len(right_lines):
            fn_lines = right_lines[right_fn_start:]
            if fn_lines:
                min_y = min(min(w['top'] for w in line) for line in fn_lines)
                max_y = max(max(w['bottom'] for w in line) for line in fn_lines)
                draw.rectangle([right_margin, min_y, all_right, max_y], 
                              fill=(0, 0, 255, 60), outline=(0, 0, 255, 200), width=2)
    
    def process_page(self, page_name: str, debug: bool = False, overwrite: bool = False) -> List[Dict]:
        """Process a single page and return alignment results."""
        output_path = self.output_dir / f"{page_name}_alignment.json"
        
        if output_path.exists() and not overwrite:
            logging.info(f"Skipping {page_name} - Output exists (use --overwrite to force)")
            return []
            
        logging.info(f"Processing {page_name}...")
        
        # Load data
        try:
            words = self.load_ocr(page_name)
            markdown = self.load_markdown(page_name)
        except FileNotFoundError as e:
            logging.error(str(e))
            return []
        
        logging.info(f"Loaded {len(words)} words")
        
        # Detect column bounds
        bounds = self.detect_column_bounds(words)
        logging.info(f"Column bounds: L={bounds['left_col']}, R={bounds['right_col']}")
        
        # Extract verses using Regex/BAML
        verses = self.extract_verses(markdown, page_name)
        if not verses:
            logging.warning("No verses extracted")
            return []
        
        results = []
        
        # === PASS 1: Find all verse START positions ===
        verse_starts = []
        last_end_idx = 0
        
        for verse in verses:
            verse_ref = verse['verse_ref']
            start_phrase = verse['start_phrase']
            
            # Find start phrase
            start_idx, start_end, start_score = self.fuzzy_find_phrase(
                start_phrase, words, last_end_idx, bounds
            )
            
            if start_idx >= 0:
                verse_starts.append({
                    'verse': verse,
                    'start_idx': start_idx,
                    'start_end': start_end,
                    'start_score': start_score
                })
                last_end_idx = start_idx + 1  # Move forward to avoid overlapping
                logging.info(f"  Start found for {verse_ref}: idx={start_idx}, score={start_score:.0f}")
                
                if start_score < 60:
                    logging.warning(f"  [Low Confidence] {verse_ref} matched with score {start_score:.1f}. Check OCR quality.")
            else:
                logging.warning(f"  Start not found for {verse_ref} (score={start_score:.1f})")
        
        # === PASS 2: Find END positions, searching BACKWARDS from next verse start ===
        for i, vs in enumerate(verse_starts):
            verse = vs['verse']
            verse_ref = verse['verse_ref']
            start_idx = vs['start_idx']
            end_phrase = verse['end_phrase']
            
            # Determine the search boundary for end phrase
            # End must be BEFORE the next verse's start (or end of body text)
            if i + 1 < len(verse_starts):
                max_end_idx = verse_starts[i + 1]['start_idx'] - 1
            else:
                # Last verse - search to end of body text (exclude footnotes)
                max_end_idx = len(words) - 1
            
            logging.info(f"Processing {verse_ref}")
            logging.info(f"  Start: '{verse['start_phrase'][:50]}...'")
            logging.info(f"  End: '...{end_phrase[-50:]}'")
            logging.info(f"  Search range: {start_idx} to {max_end_idx}")
            
            # Find end phrase, but only consider matches within the valid range
            # We search forward but validate the match is before max_end_idx
            end_start, end_end, end_score = self.fuzzy_find_phrase_bounded(
                end_phrase, words, start_idx, max_end_idx, bounds
            )
            
            if end_end < 0:
                logging.warning(f"  End phrase not found (score={end_score:.1f})")
                continue
            
            # Calculate boxes
            boxes = self.calculate_boxes(start_idx, end_end, words, bounds)
            
            if boxes:
                result = {
                    'verse_ref': verse_ref,
                    'start_phrase': verse['start_phrase'],
                    'end_phrase': end_phrase,
                    'start_idx': start_idx,
                    'end_idx': end_end,
                    'start_idx': start_idx,
                    'end_idx': end_end,
                    'score': start_score,
                    'boxes': boxes
                }
                results.append(result)
                
                logging.info(f"  Found: idx={start_idx}-{end_end}, boxes={len(boxes)}")
                for box in boxes:
                    logging.info(f"    Box: x={box['x']}, y={box['y']}, w={box['w']}, h={box['h']}")
            else:
                logging.warning(f"  No valid boxes calculated")
        
        # Save results
        output_path = self.output_dir / f"{page_name}_alignment.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        logging.info(f"Saved: {output_path}")
        
        # Generate debug image with footnote regions
        if debug and results:
            self.generate_debug_image(page_name, results, words, bounds)
        
        return results
    
    def run(self, debug: bool = False, overwrite: bool = False):
        """Process all pages."""
        md_files = sorted(list(self.extracted_dir.glob("*.md")))
        for md_file in md_files:
            page_name = md_file.stem
            self.process_page(page_name, debug, overwrite)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Align verses to OCR bounding boxes")
    parser.add_argument("--dir", default=None, help="Input directory (default: $COMMENTARY_DATA_DIR/volume1)")
    parser.add_argument("--out", default=None, help="Output directory (default: $COMMENTARY_DATA_DIR/artifacts/alignment)")
    parser.add_argument("--test-page", help="Process single page for testing")
    parser.add_argument("--debug", action="store_true", help="Generate debug images")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output files")
    args = parser.parse_args()
    
    aligner = VerseAligner(args.dir, args.out)
    
    if args.test_page:
        # Always overwrite for explicit single page test
        aligner.process_page(args.test_page, args.debug, overwrite=True)
    else:
        aligner.run(args.debug, args.overwrite)
