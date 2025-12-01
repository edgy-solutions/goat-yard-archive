#!/usr/bin/env python3
"""
Fuzzy Match Alignment Script for Grounded Gill Commentary.

This script aligns structured verse data extracted via BAML (from Vision Markdown)
with the original OCR word data (from Tesseract) using fuzzy matching.
It calculates the union bounding box for each verse and handles column splits.
"""

import os
import json
import logging
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from rapidfuzz import fuzz, process

# Import BAML client
from dotenv import load_dotenv
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
        logging.FileHandler('alignment.log', encoding='utf-8')
    ]
)

class AlignmentEngine:
    def __init__(self, extracted_dir: str, output_dir: str):
        self.extracted_dir = Path(extracted_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)
        
    def load_ocr_data(self, page_name: str) -> List[Dict]:
        """Load OCR word data for a specific page."""
        # OCR files are named <page_name>_ocr.json
        ocr_path = self.extracted_dir / f"{page_name}_ocr.json"
        if not ocr_path.exists():
            logging.warning(f"OCR file not found: {ocr_path}")
            return []
            
        with open(ocr_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Expecting data['words'] or list of words
            # Based on spec, it's a list of [text, x, y, w, h] or similar
            # Let's inspect the structure in the first run or assume standard Tesseract output
            # If it's Tesseract TSV converted to JSON, it might be a list of dicts
            # Let's assume it's a list of dicts with 'text', 'bbox' or similar
            # Wait, spec says: `ocr_word_data` (JSONB: List of `[text, x, y, w, h]`)
            # But let's check what's actually in the file.
            # For now, I'll implement a flexible loader or assume the spec is correct.
            return data

    def load_markdown(self, page_name: str) -> str:
        """Load Vision Markdown for a specific page."""
        # Look in the qwen subdirectory
        # TODO: Make this configurable or auto-detect the specific qwen directory
        qwen_dir = self.extracted_dir / "qwen_qwen3-vl-235b-a22b-thinking"
        md_path = qwen_dir / f"{page_name}.md"
        
        if not md_path.exists():
            logging.warning(f"Markdown not found at {md_path}")
            return ""
            
        with open(md_path, 'r', encoding='utf-8') as f:
            return f.read()

    def extract_verses(self, markdown_text: str) -> List[Any]:
        """Extract structured verses using BAML."""
        if not markdown_text:
            return []
        try:
            return b.ExtractVersesFromMarkdown(markdown_text)
        except BamlError as e:
            logging.error(f"BAML Error extraction verses: {e}")
            return []

    def fuzzy_find_phrase(self, phrase: str, words: List[Dict], start_search_idx: int = 0) -> Tuple[int, float]:
        """
        Find the best match for a phrase in the list of words using multiple strategies.
        Returns (index_in_words, score).
        """
        phrase_words = phrase.split()
        if not phrase_words:
            return -1, 0.0
        
        # Extract text from OCR data
        ocr_texts = [w['text'] if isinstance(w, dict) else w[0] for w in words]
        
        # Strategy 1: Try partial ratio matching on windows
        # This works better when the phrase exists but has extra/missing words
        window_size = max(len(phrase_words), 5)  # At least 5 words
        best_score = 0
        best_idx = -1
        
        for i in range(start_search_idx, len(ocr_texts)):
            # Try different window sizes to be more flexible
            for w_size in [window_size, window_size + 5, window_size - 2]:
                if w_size < 1:
                    continue
                current_window = " ".join(ocr_texts[i:i+w_size])
                
                # Use multiple scoring methods
                partial_score = fuzz.partial_ratio(phrase.lower(), current_window.lower())
                token_sort_score = fuzz.token_sort_ratio(phrase.lower(), current_window.lower())
                
                # Take the best score from multiple strategies
                combined_score = max(partial_score, token_sort_score)
                
                if combined_score > best_score:
                    best_score = combined_score
                    best_idx = i
        
        # Strategy 2: If we still haven't found a good match, try process.extractOne
        # This finds the best match across all possible windows
        if best_score < 60:
            # Build candidate windows
            candidates = {}
            for i in range(start_search_idx, len(ocr_texts)):
                window = " ".join(ocr_texts[i:i+window_size])
                candidates[i] = window
            
            if candidates:
                # Find best match using extractOne
                result = process.extractOne(
                    phrase.lower(),
                    candidates,
                    scorer=fuzz.partial_ratio
                )
                if result and result[1] > best_score:
                    best_idx = result[2]  # index is the third element
                    best_score = result[1]
        
        return best_idx, best_score

    def calculate_union_box(self, words_slice: List[Any]) -> Dict[str, int]:
        """Calculate the union bounding box for a slice of words."""
        if not words_slice:
            return None
            
        # Handle different formats: dict or list
        # Spec: [text, x, y, w, h]
        # Actual file might be dicts. I'll handle both.
        
        boxes = []
        for w in words_slice:
            if isinstance(w, dict):
                # Tesseract JSON often has 'bbox': [x, y, w, h] or separate fields
                if 'bbox' in w:
                    boxes.append(w['bbox'])
                elif 'left' in w:
                    boxes.append([w['left'], w['top'], w['width'], w['height']])
            elif isinstance(w, list) and len(w) >= 5:
                boxes.append(w[1:5]) # x, y, w, h
        
        if not boxes:
            return None
            
        x_min = min(b[0] for b in boxes)
        y_min = min(b[1] for b in boxes)
        x_max = max(b[0] + b[2] for b in boxes)
        y_max = max(b[1] + b[3] for b in boxes)
        
        return {
            "x": x_min,
            "y": y_min,
            "w": x_max - x_min,
            "h": y_max - y_min
        }

    def detect_column_split(self, words_slice: List[Any], threshold: int = 500) -> bool:
        """Detect if the words span multiple columns based on X-coordinate variance."""
        if not words_slice:
            return False
            
        x_coords = []
        for w in words_slice:
            if isinstance(w, dict):
                if 'bbox' in w:
                    x_coords.append(w['bbox'][0])
                elif 'left' in w:
                    x_coords.append(w['left'])
            elif isinstance(w, list) and len(w) >= 5:
                x_coords.append(w[1])
                
        if not x_coords:
            return False
            
        # Calculate standard deviation
        std_dev = np.std(x_coords)
        return std_dev > threshold

    def process_page(self, page_name: str):
        logging.info(f"Processing {page_name}...")
        
        ocr_data = self.load_ocr_data(page_name)
        if not ocr_data:
            logging.error(f"No OCR data for {page_name}")
            return
            
        markdown_text = self.load_markdown(page_name)
        verses = self.extract_verses(markdown_text)
        logging.info(f"Extracted {len(verses)} verses from Markdown.")
        print(f"DEBUG: Extracted {len(verses)} verses")
        for v in verses:
            print(f"DEBUG: Verse Ref: {v.verse_ref}")
        
        results = []
        current_idx = 0
        
        for verse in verses:
            # Find start
            start_idx, start_score = self.fuzzy_find_phrase(verse.start_phrase, ocr_data, current_idx)
            
            if start_idx == -1:
                logging.warning(f"Could not find start phrase for {verse.verse_ref}")
                continue
                
            # Find end (search from start_idx)
            # End phrase might be short, so be careful
            end_idx, end_score = self.fuzzy_find_phrase(verse.end_phrase, ocr_data, start_idx)
            
            if end_idx == -1:
                logging.warning(f"Could not find end phrase for {verse.verse_ref}")
                # Fallback: take some reasonable chunk or skip
                continue
                
            # Adjust end_idx to include the end phrase length
            end_phrase_len = len(verse.end_phrase.split())
            end_idx = end_idx + end_phrase_len
            
            # Slice
            word_slice = ocr_data[start_idx:end_idx]
            
            # Geometry
            if self.detect_column_split(word_slice):
                logging.info(f"Detected column split for {verse.verse_ref}")
                # Split into two boxes based on mean X
                x_coords = []
                for w in word_slice:
                    if isinstance(w, dict):
                        if 'bbox' in w:
                            x_coords.append(w['bbox'][0])
                        elif 'left' in w:
                            x_coords.append(w['left'])
                    elif isinstance(w, list) and len(w) >= 5:
                        x_coords.append(w[1])
                
                if x_coords:
                    mean_x = np.mean(x_coords)
                    left_slice = []
                    right_slice = []
                    
                    for w in word_slice:
                        wx = 0
                        if isinstance(w, dict):
                            if 'bbox' in w:
                                wx = w['bbox'][0]
                            elif 'left' in w:
                                wx = w['left']
                        elif isinstance(w, list) and len(w) >= 5:
                            wx = w[1]
                            
                        if wx < mean_x:
                            left_slice.append(w)
                        else:
                            right_slice.append(w)
                    
                    bbox1 = self.calculate_union_box(left_slice)
                    bbox2 = self.calculate_union_box(right_slice)
                    bbox = [b for b in [bbox1, bbox2] if b]
                else:
                    bbox = self.calculate_union_box(word_slice)
            else:
                bbox = self.calculate_union_box(word_slice)
            
            results.append({
                "verse_ref": verse.verse_ref,
                "highlight_box": bbox,
                "start_phrase": verse.start_phrase,
                "end_phrase": verse.end_phrase,
                "match_score": (start_score + end_score) / 2
            })
            
            # Update current_idx to speed up next search
            # But be careful of overlapping or out of order verses (though usually in order)
            current_idx = start_idx
            
        # Save results
        output_path = self.output_dir / f"{page_name}_alignment.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
            
        logging.info(f"Saved alignment to {output_path}")

    def run(self):
        # Iterate over images in extracted_images
        # We use _ocr.json files as the source of truth for pages
        files = list(self.extracted_dir.glob("*_ocr.json"))
        for f in files:
            page_name = f.name.replace("_ocr.json", "")
            self.process_page(page_name)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="extracted_images", help="Input directory")
    parser.add_argument("--out", default="outputs/alignment", help="Output directory")
    parser.add_argument("--test-page", help="Run on a specific page only")
    args = parser.parse_args()
    
    engine = AlignmentEngine(args.dir, args.out)
    
    if args.test_page:
        engine.process_page(args.test_page)
    else:
        engine.run()
