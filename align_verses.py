#!/usr/bin/env python3
"""
Verse Alignment Script for Grounded Gill Commentary.

Uses margin detection and fuzzy phrase matching to find bounding boxes
for verse commentary text in two-column OCR data.
"""
import json
import asyncio
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from rapidfuzz import fuzz
from dotenv import load_dotenv

load_dotenv()

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
    
    def __init__(self, extracted_dir: str = "extracted_images", output_dir: str = "outputs/alignment"):
        self.extracted_dir = Path(extracted_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)
        
        # Configuration
        self.y_tolerance = 30  # Pixels for line grouping
        self.header_y_threshold = 650  # Skip words above this Y
        self.footnote_indent = 50  # Footnotes are indented this much from margin
        self.fuzzy_threshold = 50  # Match score threshold
    
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
        elif reindexed_path.exists():
            ocr_path = reindexed_path
            logging.info(f"Using reindexed OCR: {reindexed_path}")
        elif raw_path.exists():
            ocr_path = raw_path
            logging.info(f"Using raw OCR: {raw_path}")
        else:
            raise FileNotFoundError(f"OCR not found: {raw_path}")
        
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
    
    def extract_verses(self, markdown_text: str) -> List[Dict]:
        """
        Extract verse chunks using BAML.
        Always uses fresh BAML extraction to ensure accurate data.
        """
        if not markdown_text:
            return []
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
        
        # Filter to body words only
        body_indices = []
        for i, w in enumerate(words):
            if i >= start_idx:
                if bounds is None or self.is_body_word(w, bounds):
                    body_indices.append(i)
        
        # Cascading thresholds: try high first, back off
        thresholds = [80, 70, 60, 50, 40]
        
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
        
        # Filter to body words within the range
        body_indices = []
        for i, w in enumerate(words):
            if start_idx <= i <= max_end_idx:
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
        
        # Collect all words in range
        range_words = [words[i] for i in range(start_idx, end_idx + 1)
                       if self.is_body_word(words[i], bounds)]
        
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
    
    def process_page(self, page_name: str, debug: bool = False) -> List[Dict]:
        """Process a single page and return alignment results."""
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
        
        # Extract verses using BAML
        verses = self.extract_verses(markdown)
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
    
    def run(self, debug: bool = False):
        """Process all pages."""
        md_files = list(self.extracted_dir.glob("*.md"))
        for md_file in md_files:
            page_name = md_file.stem
            self.process_page(page_name, debug)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Align verses to OCR bounding boxes")
    parser.add_argument("--dir", default="extracted_images", help="Input directory")
    parser.add_argument("--out", default="outputs/alignment", help="Output directory")
    parser.add_argument("--test-page", help="Process single page for testing")
    parser.add_argument("--debug", action="store_true", help="Generate debug images")
    args = parser.parse_args()
    
    aligner = VerseAligner(args.dir, args.out)
    
    if args.test_page:
        aligner.process_page(args.test_page, args.debug)
    else:
        aligner.run(args.debug)
