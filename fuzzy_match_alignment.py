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
        ocr_path = self.extracted_dir / f"{page_name}_ocr.json"
        if not ocr_path.exists():
            logging.warning(f"OCR file not found: {ocr_path}")
            return []
            
        with open(ocr_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data

    def load_markdown(self, page_name: str) -> str:
        """Load Vision Markdown for a specific page."""
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

    def fuzzy_find_phrase(self, phrase: str, words: List[Dict], start_search_idx: int = 0, end_search_idx: int = -1) -> Tuple[int, float]:
        """
        Find the best match for a phrase in the list of words using multiple strategies.
        Returns (index_in_words, score).
        """
        phrase_words = phrase.split()
        if not phrase_words:
            return -1, 0.0
        
        # Extract text from OCR data
        ocr_texts = [w['text'] if isinstance(w, dict) else w[0] for w in words]
        
        search_end = len(ocr_texts) if end_search_idx == -1 else end_search_idx
        
        # Strategy 1: Try partial ratio matching on windows
        window_size = max(len(phrase_words), 5)  # At least 5 words
        best_score = 0
        best_idx = -1
        
        for i in range(start_search_idx, search_end):
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
        if best_score < 50: 
            # Build candidate windows
            candidates = {}
            for i in range(start_search_idx, search_end):
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

    def detect_page_grid(self, ocr_data: List[Dict]) -> Tuple[Dict, Dict]:
        """
        Analyze all words on the page to determine the global Left and Right column rails.
        Uses Histogram Peak Detection to find main column starts.
        Returns (left_col, right_col) where each is {'x': int, 'w': int}.
        """
        x_starts = []
        x_ends = []
        
        for w in ocr_data:
            wx, ww, wy = 0, 0, 0
            if isinstance(w, dict):
                 if 'bbox' in w: 
                     wx = w['bbox'][0]
                     ww = w['bbox'][2]
                     wy = w['bbox'][1]
                 elif 'left' in w: 
                     wx = w['left']
                     ww = w['width']
                     wy = w['top']
            elif isinstance(w, list) and len(w) >= 5:
                 wx = w[1]
                 ww = w[3]
                 wy = w[2]
            
            # Filter standard body text (ignore footer and tiny fragments)
            if wy < 3200 and ww > 20:
                x_starts.append(wx)
                x_ends.append(wx + ww)
                
        if not x_starts:
            return {'x': 440, 'w': 1400}, {'x': 1900, 'w': 1400}

        # Histogram for Starts (Bin=50px)
        bins = np.arange(0, 4000, 50)
        hist, edges = np.histogram(x_starts, bins=bins)
        
        # 1. Find Left Column Peak (Search 0-1000)
        # Find bin with max count
        left_peak_idx = np.argmax(hist[:20]) # First 1000px (20 bins * 50)
        l_start = int(edges[left_peak_idx])
        # Refine using median of points in that bin
        l_points = [x for x in x_starts if l_start <= x < l_start + 100]
        if l_points:
            l_start = int(np.median(l_points))
        
        # 2. Find Right Column Peak (Search 1500-3000)
        # Why 1500? Because gutter is likely > 1000.
        # Mask left side
        hist_right = hist.copy()
        hist_right[:30] = 0 # Ignore first 1500px
        
        if np.max(hist_right) > 0:
            right_peak_idx = np.argmax(hist_right)
            r_start = int(edges[right_peak_idx])
            # Refine
            r_points = [x for x in x_starts if r_start <= x < r_start + 100]
            if r_points:
                r_start = int(np.median(r_points))
        else:
            # Fallback if single column? 
            # But user says 2 columns.
            r_start = 1900 # Default fallback based on analysis
        
        # 3. Determine Widths
        # User Strategy: "Average of Right Most Boxes" -> Page Right Edge
        # Let's find the effective Page Width using 95th percentile of all Ends
        page_right_edge = int(np.percentile(x_ends, 95)) if x_ends else 3400
        
        # Grid calculations
        # Add slight padding to rails to avoid clipping text on edges
        padding = 20
        
        l_w = (r_start - l_start) - 30 
        
        r_w = page_right_edge - r_start + padding
        
        # SYMMETRY ENFORCEMENT (RELAXED)
        # Only clamp if right is absurdly wider (> 1.5x)
        if l_w > 0 and r_w > (l_w * 1.5):
             print(f"DEBUG: Clamping Right Width {r_w} to match Left {l_w} * 1.5")
             r_w = int(l_w * 1.2)
        
        left_col = {'x': l_start - padding, 'w': l_w + padding}
        right_col = {'x': r_start - padding, 'w': r_w + padding}
        
        print(f"DEBUG: Grid Detected (Peaks) - L_Start:{l_start} R_Start:{r_start} PageEdge:{page_right_edge}")
        print(f"DEBUG: Rails - Left: {left_col}, Right: {right_col}")
        return left_col, right_col

    def snap_to_grid(self, words_slice: List[Any], left_col: Dict, right_col: Dict) -> List[Dict]:
        """
        Calculate bounding box(es) by determining Y-range from words 
        and snapping X/W to the global grid rails.
        """
        if not words_slice:
            return None
            
        # 1. Determine Y-Range (min top, max bottom) per column
        # Split words into LeftCluster and RightCluster based on CenterMargin
        
        center_margin = (left_col['x'] + left_col['w'] + right_col['x']) / 2
        
        l_words = []
        r_words = []
        
        for w in words_slice:
            wx = 0
            if isinstance(w, dict):
                 if 'bbox' in w: wx = w['bbox'][0]
                 elif 'left' in w: wx = w['left']
            elif isinstance(w, list) and len(w) >= 5:
                 wx = w[1]
            
            if wx < center_margin: 
                l_words.append(w)
            else: 
                r_words.append(w)
            
        final_boxes = []
        
        # Threshold: Verse must have > 5% of its words (and at least 3 words) in a column to trigger a box there.
        total_count = len(words_slice)
        min_words = max(3, int(total_count * 0.05))
        
        if l_words and len(l_words) >= min_words:
            # Calc Y-range for Left
            ly_min = 10000
            ly_max = 0
            for lw in l_words:
                wy, wh = 0, 0
                if isinstance(lw, dict):
                    if 'bbox' in lw:
                        wy = lw['bbox'][1]
                        wh = lw['bbox'][3]
                    elif 'top' in lw:
                        wy = lw['top']
                        wh = lw['height']
                elif isinstance(lw, list):
                    wy, wh = lw[2], lw[4]
                ly_min = min(ly_min, wy)
                ly_max = max(ly_max, wy + wh)
            
            final_boxes.append({
                'x': left_col['x'],
                'y': ly_min,
                'w': left_col['w'],
                'h': ly_max - ly_min
            })

        if r_words and len(r_words) >= min_words:
            # Calc Y-range for Right
            ry_min = 10000
            ry_max = 0
            for rw in r_words:
                wy, wh = 0, 0
                if isinstance(rw, dict):
                    if 'bbox' in rw:
                        wy = rw['bbox'][1]
                        wh = rw['bbox'][3]
                    elif 'top' in rw:
                        wy = rw['top']
                        wh = rw['height']
                elif isinstance(rw, list):
                    wy, wh = rw[2], rw[4]
                ry_min = min(ry_min, wy)
                ry_max = max(ry_max, wy + wh)
            
            final_boxes.append({
                'x': right_col['x'],
                'y': ry_min,
                'w': right_col['w'],
                'h': ry_max - ry_min
            })
            
        return final_boxes

    def generate_debug_image(self, page_name: str, results: List[Dict]):
        """Generate a debug image with bounding boxes drawn."""
        image_path = None
        for ext in ['.png', '.jpg', '.jpeg']:
            p = self.extracted_dir / f"{page_name}{ext}"
            if p.exists():
                image_path = p
                break
        
        if not image_path:
            logging.warning(f"Could not find image for {page_name} to generate debug output.")
            return

        try:
            from PIL import Image, ImageDraw
            
            with Image.open(image_path) as img:
                draw = ImageDraw.Draw(img)
                
                for res in results:
                    bbox = res.get('highlight_box')
                    if bbox:
                        # Normalize to list of bboxes
                        boxes_to_draw = bbox if isinstance(bbox, list) else [bbox]
                        
                        for b in boxes_to_draw:
                            if isinstance(b, dict):
                                x, y, w, h = b['x'], b['y'], b['w'], b['h']
                                draw.rectangle([x, y, x+w, y+h], outline="red", width=3)
                
                # Save to output dir
                debug_path = self.output_dir / f"debug_{page_name}_grid.jpg"
                img.save(debug_path)
                logging.info(f"Saved debug image to {debug_path}")
                
        except ImportError:
            logging.error("PIL not installed. Cannot generate debug images.")
        except Exception as e:
            logging.error(f"Error generating debug image: {e}")

    def run(self, debug: bool = False):
        files = list(self.extracted_dir.glob("*_ocr.json"))
        for f in files:
            page_name = f.name.replace("_ocr.json", "")
            self.process_page(page_name, debug)

    def process_page(self, page_name: str, debug: bool = False):
        logging.info(f"Processing {page_name}...")
        
        ocr_data = self.load_ocr_data(page_name)
        if not ocr_data:
            logging.error(f"No OCR data for {page_name}")
            return
            
        markdown_text = self.load_markdown(page_name)
        verses = self.extract_verses(markdown_text)
        logging.info(f"Extracted {len(verses)} verses from Markdown.")
        
        if not verses:
            return

        # 0. Global Grid Detection
        left_col_def, right_col_def = self.detect_page_grid(ocr_data)
        
        # 0.5. Dynamic Page Bounds (User Request)
        dyn_min_y = 0
        dyn_max_y = 10000
        v0_true_start_idx = -1
        found_bottom_idx = -1
        
        if verses:
             # Find Top
             v0 = verses[0]
             # Loop to find a match that is visibly in the top half (Y < 3000)
             # This avoids catching footnote repeats of the start phrase.
             cur_s = 0
             dyn_min_y = 0 # reset
             
             while cur_s < len(ocr_data):
                 s_idx, s_score = self.fuzzy_find_phrase(v0.start_phrase, ocr_data, cur_s)
                 if s_idx != -1:
                     w = ocr_data[s_idx]
                     wy = w['bbox'][1] if isinstance(w, dict) and 'bbox' in w else (w['top'] if isinstance(w, dict) else w[2])
                     
                     if wy < 3000:
                         # Valid top match
                         dyn_min_y = wy - 10
                         v0_true_start_idx = s_idx
                         print(f"DEBUG: Dynamic Top Limit found at Y={wy} (from '{v0.start_phrase[:15]}...') at index {s_idx}")
                         break
                     else:
                         print(f"DEBUG: Ignoring Top Limit candidate at Y={wy} (Footer/Bottom) -> Continuing search...")
                         cur_s = s_idx + 1
                 else:
                     break
                     
             if dyn_min_y == 0 and s_idx != -1:
                  # Fallback if only footer found? unlikely.
                  pass
             
             # Find Bottom
             v_last = verses[-1]
             # Search near end with explicit loop to find LAST occurrence?
             # fuzzy_find_phrase usually finds FIRST best match?
             # Actually we iterate linear.
             cur = 0
             while cur < len(ocr_data):
                  m_idx, m_score = self.fuzzy_find_phrase(v_last.end_phrase, ocr_data, cur)
                  if m_idx != -1:
                      l_idx = m_idx + len(v_last.end_phrase.split()) - 1
                      if l_idx < len(ocr_data):
                          w = ocr_data[l_idx]
                          wy = w['bbox'][1] + w['bbox'][3] if isinstance(w, dict) and 'bbox' in w else (w['top'] + w['height'] if isinstance(w, dict) else w[2]+w[4])
                          dyn_max_y = wy + 20
                          found_bottom_idx = l_idx
                      cur = m_idx + 1
                  else:
                      break
             
             if dyn_max_y != 10000:
                  print(f"DEBUG: Dynamic Bottom Limit found at Y={dyn_max_y} (from '{v_last.end_phrase[:15]}...')")
        
        # Fallbacks (removed clamp)
        if dyn_min_y == 0: dyn_min_y = 600
        if dyn_max_y == 10000: dyn_max_y = 4500

        # Pass 1: Find all start indices
        verse_starts = []
        current_search_idx = 0
        for i, verse in enumerate(verses):
            if i == 0 and v0_true_start_idx != -1:
                 # Reuse the correctly anchored start index from 'Find Top' step
                 s_idx = v0_true_start_idx
                 s_score = 100
            else:
                 s_idx, s_score = self.fuzzy_find_phrase(verse.start_phrase, ocr_data, current_search_idx)
            
            if s_idx != -1:
                verse_starts.append(s_idx)
            else:
                logging.warning(f"Could not find start phrase for {verse.verse_ref}")
                print(f"DEBUG: Failed to find start for {verse.verse_ref}")
                verse_starts.append(-1)
                
        results = []
        
        # Pass 2: Process verses with constraints
        for i, verse in enumerate(verses):
            start_idx = verse_starts[i]
            
            if start_idx == -1:
                continue
                
            # Determine limit (start of NEXT verse)
            limit_idx = len(ocr_data)
            next_ref = "EndOfPage"
            for j in range(i + 1, len(verses)):
                if verse_starts[j] != -1:
                    limit_idx = verse_starts[j]
                    next_ref = verses[j].verse_ref
                    break
            
            print(f"DEBUG: Processing {verse.verse_ref} | Start: {start_idx} | Limit: {limit_idx} (from {next_ref})")

            # Determine Start Column
            start_w = ocr_data[start_idx]
            sx = start_w['bbox'][0] if isinstance(start_w, dict) and 'bbox' in start_w else (start_w['left'] if isinstance(start_w, dict) else start_w[1])
            sy = start_w['bbox'][1] if isinstance(start_w, dict) and 'bbox' in start_w else (start_w['top'] if isinstance(start_w, dict) else start_w[2])
            
            center_margin = (left_col_def['x'] + left_col_def['w'] + right_col_def['x']) / 2
            start_col = "Left" if sx < center_margin else "Right"
            print(f"DEBUG: {verse.verse_ref} starts in {start_col} column (Y={sy})")

            # Logic for Last Verse (Smart Wrap) vs Normal Verse
            word_slice = []
            
            if next_ref == "EndOfPage":
                 # Smart Last Verse Logic: "Rest of Left" + "All of Right"
                 # This handles the "Right Column is indexed before Left Bottom" scenario
                 print(f"DEBUG: Applying Smart Last Verse Logic for {verse.verse_ref}")
                 
                 # Iterate ALL words to fill geometric buckets
                 # Filter 1: Global Y Constraints
                 for w in ocr_data:
                     wx, wy = 0, 0
                     if isinstance(w, dict):
                        if 'bbox' in w: 
                            wx = w['bbox'][0]
                            wy = w['bbox'][1]
                        elif 'left' in w: 
                            wx = w['left']
                            wy = w['top']
                     elif isinstance(w, list) and len(w) >= 5:
                        wx = w[1]
                        wy = w[2]

                     # Valid Y range check
                     if wy < dyn_min_y or wy > dyn_max_y:
                         continue
                         
                     # Column Logic
                     w_col = "Left" if wx < center_margin else "Right"
                     
                     if w_col == "Right":
                         # Take ALL Right Column words (assuming L->R flow)
                         word_slice.append(w)
                     elif w_col == "Left":
                         # Take Left Column words ONLY if below Start Y
                         # (Allow small buffer for same-line jitter)
                         if wy >= (sy - 15):
                             word_slice.append(w)

            else:
                # Normal Verse Logic (Index Slicing + Spatial Consistency)
                
                # ... same Greedy Search as before ...
                # 1. Forward Search
                f_best_idx = -1
                f_best_score = 0
                s_idx = start_idx
                while s_idx < limit_idx:
                    c_idx, c_score = self.fuzzy_find_phrase(verse.end_phrase, ocr_data, s_idx, limit_idx)
                    if c_idx != -1:
                        end_len = len(verse.end_phrase.split())
                        cand_end = c_idx + end_len
                        if c_score > f_best_score or (c_score == f_best_score and cand_end > f_best_idx):
                            f_best_score = c_score
                            f_best_idx = cand_end
                        s_idx = c_idx + 1 
                    else:
                        break
                
                best_end_idx = f_best_idx if f_best_idx != -1 else limit_idx
                
                # Raw Slice
                raw_slice = ocr_data[start_idx:best_end_idx]
                
                # Determine End Column (approximate from last word)
                end_col = start_col # Default to same
                if raw_slice:
                    last_w = raw_slice[-1]
                    lx = last_w['bbox'][0] if isinstance(last_w, dict) and 'bbox' in last_w else (last_w['left'] if isinstance(last_w, dict) else last_w[1])
                    end_col = "Left" if lx < center_margin else "Right"
                
                # Filter Loop
                for w in raw_slice:
                     wx, wy = 0, 0
                     if isinstance(w, dict):
                        if 'bbox' in w: 
                            wx = w['bbox'][0]
                            wy = w['bbox'][1]
                        elif 'left' in w: 
                            wx = w['left']
                            wy = w['top']
                     elif isinstance(w, list) and len(w) >= 5:
                        wx = w[1]
                        wy = w[2]
                     
                     if wy < dyn_min_y or wy > dyn_max_y: 
                         continue
                         
                     # Spatial Consistency:
                     # If Start=Left and End=Left, reject Right words (interleaved trash)
                     w_col = "Left" if wx < center_margin else "Right"
                     
                     if start_col == "Left" and end_col == "Left" and w_col == "Right":
                         # Skip pollution
                         continue
                     
                     word_slice.append(w)
            
            dropped_words = 0 # Placeholder since we built slice manually/filtered
            
            if not word_slice:
                continue
            
            if verse.verse_ref == "GEN 01:31":
                 # Debug specific words causing top-bound issues
                 print("DEBUG: GEN 01:31 Word Analysis (Top 5 lowest Y):")
                 sorted_y = sorted(word_slice, key=lambda w: w['bbox'][1] if isinstance(w, dict) and 'bbox' in w else (w['top'] if isinstance(w, dict) else w[2]))
                 for i in range(min(5, len(sorted_y))):
                     w = sorted_y[i]
                     txt = w['text'] if isinstance(w, dict) and 'text' in w else (w[0] if isinstance(w, list) else str(w))
                     y_val = w['bbox'][1] if isinstance(w, dict) and 'bbox' in w else (w['top'] if isinstance(w, dict) else w[2])
                     print(f"  - '{txt}' at Y={y_val}")
            
            # GRID SNAPPING GEOMETRY
            bbox = self.snap_to_grid(word_slice, left_col_def, right_col_def)
            print(f"DEBUG: {verse.verse_ref} Final Box(es): {bbox}")
            
            results.append({
                "verse_ref": verse.verse_ref,
                "highlight_box": bbox,
                "start_phrase": verse.start_phrase,
                "end_phrase": verse.end_phrase,
                "match_score": 0 
            })
            
        # Save results
        output_path = self.output_dir / f"{page_name}_alignment.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
            
        logging.info(f"Saved alignment to {output_path}")

        if debug:
            self.generate_debug_image(page_name, results)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="extracted_images", help="Input directory")
    parser.add_argument("--out", default="outputs/alignment", help="Output directory")
    parser.add_argument("--test-page", help="Run on a specific page only")
    parser.add_argument("--debug", action="store_true", help="Generate debug images with bounding boxes")
    args = parser.parse_args()
    
    engine = AlignmentEngine(args.dir, args.out)
    
    if args.test_page:
        engine.process_page(args.test_page, args.debug)
    else:
        engine.run(args.debug)
