"""
Reindex OCR data to reading order.

Fixed algorithm (matching run_left_analysis.py):
1. Split words into LEFT and RIGHT columns FIRST
2. Group each column into lines separately
3. Sort lines by Y position within each column
4. Concatenate: header lines, left column lines, right column lines, footnotes

Reading order:
1. Header/title line (top of page, usually centered)
2. Left column - line by line, words left to right within each line
3. Right column - line by line, words left to right within each line
4. Footnotes (if any, at bottom)

Output: Creates {page_name}_reindexed.json with words in reading order.
"""

import json
import argparse
from pathlib import Path
from typing import List, Dict, Tuple


def load_ocr(page_name: str, extracted_dir: Path) -> List[Dict]:
    """Load OCR JSON and normalize to standard format."""
    ocr_path = extracted_dir / f"{page_name}_ocr.json"
    with open(ocr_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    words = []
    for item in data:
        if isinstance(item, dict) and 'text' in item:
            left = item.get('left', 0)
            top = item.get('top', 0)
            width = item.get('width', 0)
            height = item.get('height', 0)
            words.append({
                'text': item['text'],
                'left': left,
                'right': left + width,
                'top': top,
                'bottom': top + height,
                'width': width,
                'height': height,
                'conf': item.get('conf', 0)
            })
    return words


def detect_layout(words: List[Dict]) -> Dict:
    """Detect page layout: column split, header zone."""
    if not words:
        return {}
    
    # Get page dimensions from word positions
    all_left = min(w['left'] for w in words)
    all_right = max(w['right'] for w in words)
    all_top = min(w['top'] for w in words)
    all_bottom = max(w['bottom'] for w in words)
    
    page_width = all_right - all_left
    page_height = all_bottom - all_top
    
    # Column split at approximately 48% of page width (matching run_left_analysis.py)
    column_split = all_left + (page_width * 0.48)
    
    # Header zone: top ~3% of page (just the top header line with page number, book name)
    header_y = all_top + (page_height * 0.03)
    
    return {
        'page_left': all_left,
        'page_right': all_right,
        'page_top': all_top,
        'page_bottom': all_bottom,
        'column_split': column_split,
        'header_y': header_y
    }


def group_into_lines(word_list: List[Dict], y_tolerance: int = 30) -> List[List[Dict]]:
    """
    Group words into lines based on TOP coordinate proximity.
    This is the same algorithm as run_left_analysis.py.
    """
    if not word_list:
        return []
    
    # Sort by top, then left
    word_list = sorted(word_list, key=lambda w: (w['top'], w['left']))
    lines = []
    
    for word in word_list:
        placed = False
        for line in lines:
            for existing_word in line:
                if abs(word['top'] - existing_word['top']) <= y_tolerance:
                    line.append(word)
                    placed = True
                    break
            if placed:
                break
        if not placed:
            lines.append([word])
    
    # Sort words within each line by left position
    for line in lines:
        line.sort(key=lambda w: w['left'])
    
    # Sort lines by average Y of words in line
    lines.sort(key=lambda line: sum(w['top'] for w in line) / len(line))
    
    return lines


def find_column_margin(lines: List[List[Dict]]) -> float:
    """
    Find the leftmost margin for a column by looking at the leftmost word of each line.
    This is the normal body text margin.
    """
    if not lines:
        return 0
    
    leftmost_positions = [min(w['left'] for w in line) for line in lines if line]
    if not leftmost_positions:
        return 0
    
    # Use the most common leftmost position (mode-like approach using clustering)
    # Sort and take the smallest values as the margin
    leftmost_positions.sort()
    # Use percentile to ignore outliers (footnotes)
    margin_count = max(1, len(leftmost_positions) // 5)
    return sum(leftmost_positions[:margin_count]) / margin_count


def is_verse_line(line: List[Dict]) -> bool:
    """Check if line starts with 'Ver' (verse marker - body text even if indented)."""
    if not line:
        return False
    first_word = line[0]['text'].lower().strip()
    return first_word.startswith('ver')


def find_footnote_start(lines: List[List[Dict]], margin: float, indent_threshold: float = 40, max_search_lines: int = 12) -> int:
    """
    Find the first footnote line using improved algorithm:
    1. Walk backwards from bottom (max 12 lines)
    2. Skip 'Ver' lines (verse markers are body text)
    3. Find first indent, then continue to find topmost indent = footnote start
    4. Non-indented continuation lines are part of footnotes
    5. If no indents found in search range, all is body text
    
    Returns the index of the first footnote line, or len(lines) if no footnotes.
    """
    if not lines:
        return 0
    
    # Start from bottom, limit search
    start_idx = len(lines) - 1
    end_idx = max(0, len(lines) - max_search_lines)
    
    # Phase 1: Find first indented line (that's not a verse marker)
    first_footnote_line = None
    
    for i in range(start_idx, end_idx - 1, -1):
        line = lines[i]
        if not line:
            continue
        
        leftmost = min(w['left'] for w in line)
        indent = leftmost - margin
        is_indented = indent > indent_threshold
        is_verse = is_verse_line(line)
        
        if is_verse:
            continue  # Skip verse markers
        
        if is_indented:
            if first_footnote_line is None:
                first_footnote_line = i
        elif first_footnote_line is not None:
            # We hit non-indented body text after finding footnotes
            # Continue to find topmost indent
            pass
    
    # Phase 2: If we found any indented lines, find the topmost one
    if first_footnote_line is not None:
        topmost_footnote = first_footnote_line
        for i in range(first_footnote_line, end_idx - 1, -1):
            line = lines[i]
            if not line:
                continue
            
            leftmost = min(w['left'] for w in line)
            indent = leftmost - margin
            is_indented = indent > indent_threshold
            is_verse = is_verse_line(line)
            
            if is_verse:
                continue  # Skip verse markers
            
            if is_indented:
                topmost_footnote = i  # This is a footnote start
        
        return topmost_footnote
    
    return len(lines)  # No footnotes found


def reindex_ocr(words: List[Dict], layout: Dict) -> List[Dict]:
    """
    Reindex OCR words in reading order:
    1. Header (centered text at top)
    2. Left column body - line by line (excluding footnotes)
    3. Right column body - line by line (excluding footnotes)
    4. Left column footnotes
    5. Right column footnotes
    
    Footnotes are detected by scanning backwards from bottom to find indented text.
    """
    column_split = layout['column_split']
    header_y = layout['header_y']
    
    # Split words into header vs body
    header_words = []
    left_col_words = []
    right_col_words = []
    
    for word in words:
        y = word['top']
        x = word['left']
        
        if y < header_y:
            header_words.append(word)
        elif x < column_split:
            left_col_words.append(word)
        else:
            right_col_words.append(word)
    
    # Group each column into lines
    header_lines = group_into_lines(header_words)
    left_lines = group_into_lines(left_col_words)
    right_lines = group_into_lines(right_col_words)
    
    # Find margin for each column
    left_margin = find_column_margin(left_lines)
    right_margin = find_column_margin(right_lines)
    
    # Find where footnotes start (scanning backwards from bottom)
    left_footnote_start = find_footnote_start(left_lines, left_margin)
    right_footnote_start = find_footnote_start(right_lines, right_margin)
    
    # Split into body and footnotes
    left_body_lines = left_lines[:left_footnote_start]
    left_footnote_lines = left_lines[left_footnote_start:]
    right_body_lines = right_lines[:right_footnote_start]
    right_footnote_lines = right_lines[right_footnote_start:]
    
    # Flatten in reading order
    result = []
    
    # 1. Header
    for line in header_lines:
        result.extend(line)
    
    # 2. Left column body
    for line in left_body_lines:
        result.extend(line)
    
    # 3. Right column body
    for line in right_body_lines:
        result.extend(line)
    
    # 4. Left footnotes
    for line in left_footnote_lines:
        result.extend(line)
    
    # 5. Right footnotes
    for line in right_footnote_lines:
        result.extend(line)
    
    # Add reading_index to each word
    for idx, word in enumerate(result):
        word['reading_index'] = idx
    
    return result


def save_reindexed(words: List[Dict], page_name: str, output_dir: Path):
    """Save reindexed OCR to JSON file."""
    output_path = output_dir / f"{page_name}_reindexed.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(words, f, indent=2, ensure_ascii=False)
    print(f"Saved: {output_path}")
    return output_path


def process_page(page_name: str, extracted_dir: Path):
    """Process a single page."""
    print(f"\nProcessing {page_name}...")
    
    # Load OCR
    words = load_ocr(page_name, extracted_dir)
    print(f"  Loaded {len(words)} words")
    
    # Detect layout
    layout = detect_layout(words)
    print(f"  Layout: column_split={layout['column_split']:.0f}, header_y={layout['header_y']:.0f}")
    
    # Reindex in reading order
    reindexed = reindex_ocr(words, layout)
    print(f"  Reindexed {len(reindexed)} words")
    
    # Save
    save_reindexed(reindexed, page_name, extracted_dir)
    
    # Show first few words to verify order
    print(f"  First 10 words: {[w['text'] for w in reindexed[:10]]}")


def main():
    parser = argparse.ArgumentParser(description='Reindex OCR data to reading order')
    parser.add_argument('--page', type=str, help='Specific page to process (e.g., page100_image1)')
    parser.add_argument('--extracted-dir', type=str, default='extracted_images', help='Directory with OCR JSON files')
    args = parser.parse_args()
    
    extracted_dir = Path(args.extracted_dir)
    
    if args.page:
        process_page(args.page, extracted_dir)
    else:
        # Process all pages with OCR files
        for ocr_file in extracted_dir.glob('*_ocr.json'):
            page_name = ocr_file.stem.replace('_ocr', '')
            process_page(page_name, extracted_dir)


if __name__ == '__main__':
    main()
