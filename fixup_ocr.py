"""
Fix up OCR using vision model markdown output.

This script:
1. Loads the reindexed OCR JSON
2. Loads the vision model markdown
3. Tokenizes the markdown into words
4. Uses fuzzy matching to align OCR words with markdown words
5. Fixes obvious OCR errors where the markdown has a better reading
6. Saves the fixed-up OCR as {page_name}_fixedup.json

Note: Does not merge hyphenated words, just fixes individual word errors.
"""

import json
import re
import argparse
from pathlib import Path
from typing import List, Dict, Tuple
from rapidfuzz import fuzz


def load_reindexed_ocr(page_name: str, extracted_dir: Path) -> List[Dict]:
    """Load reindexed OCR JSON."""
    ocr_path = extracted_dir / f"{page_name}_reindexed.json"
    with open(ocr_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_markdown(page_name: str, markdown_dir: Path) -> str:
    """Load vision model markdown."""
    md_path = markdown_dir / f"{page_name}.md"
    with open(md_path, 'r', encoding='utf-8') as f:
        return f.read()


def tokenize_markdown(markdown: str) -> List[str]:
    """
    Extract words from markdown, removing markdown syntax.
    Preserves hyphenated words as single tokens.
    """
    # Remove markdown links, footnotes, formatting
    text = re.sub(r'\[.*?\]\(.*?\)', '', markdown)  # links
    text = re.sub(r'\[\^.*?\]', '', text)  # footnotes
    text = re.sub(r'\*\*?|__?', '', text)  # bold/italic
    text = re.sub(r'#+\s*', '', text)  # headers
    text = re.sub(r'`.*?`', '', text)  # code
    
    # Split into words, keeping punctuation attached
    # Match word characters, hyphens, and apostrophes
    words = re.findall(r"[\w'-]+[.,;:!?]?|[.,;:!?]", text)
    
    # Filter out empty strings and pure punctuation that's too short
    words = [w for w in words if w and len(w) > 0]
    
    return words


def fix_word(ocr_word: str, md_words: List[str], window_start: int, window_size: int = 20) -> Tuple[str, bool]:
    """
    Try to find a matching word in the markdown window and fix if better match found.
    Returns (fixed_word, was_changed).
    """
    if not ocr_word or len(ocr_word) < 2:
        return ocr_word, False
    
    ocr_lower = ocr_word.lower()
    
    # Look in a window of markdown words around expected position
    window_end = min(window_start + window_size, len(md_words))
    window = md_words[max(0, window_start - 5):window_end]
    
    best_match = None
    best_score = 0
    
    for md_word in window:
        if not md_word or len(md_word) < 2:
            continue
        
        md_lower = md_word.lower()
        
        # Calculate similarity
        score = fuzz.ratio(ocr_lower, md_lower)
        
        # Only consider as potential fix if:
        # 1. High similarity (but not identical - no need to fix)
        # 2. Similar length
        if score > 70 and score < 100:
            if abs(len(ocr_word) - len(md_word)) <= 2:
                if score > best_score:
                    best_score = score
                    best_match = md_word
    
    # Apply fix if we found a good match
    if best_match and best_score >= 80:
        # Transfer case from OCR to fixed word
        if ocr_word[0].isupper():
            fixed = best_match[0].upper() + best_match[1:].lower()
        else:
            fixed = best_match.lower()
        
        # Keep trailing punctuation from OCR if different
        if ocr_word[-1] in '.,;:!?' and best_match[-1] not in '.,;:!?':
            fixed += ocr_word[-1]
        
        return fixed, True
    
    return ocr_word, False


def fixup_ocr(ocr_words: List[Dict], md_words: List[str]) -> Tuple[List[Dict], int]:
    """
    Fix up OCR words using markdown as reference.
    Returns (fixed_words, num_fixes).
    """
    fixed_words = []
    num_fixes = 0
    md_idx = 0  # Track position in markdown
    
    for ocr_word in ocr_words:
        original_text = ocr_word['text']
        fixed_text, was_fixed = fix_word(original_text, md_words, md_idx)
        
        if was_fixed:
            num_fixes += 1
            new_word = ocr_word.copy()
            new_word['text'] = fixed_text
            new_word['original_text'] = original_text
            fixed_words.append(new_word)
        else:
            fixed_words.append(ocr_word)
        
        # Advance markdown index (rough alignment)
        md_idx += 1
    
    return fixed_words, num_fixes


def save_fixedup(words: List[Dict], page_name: str, output_dir: Path):
    """Save fixed-up OCR to JSON file."""
    output_path = output_dir / f"{page_name}_fixedup.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(words, f, indent=2, ensure_ascii=False)
    print(f"Saved: {output_path}")
    return output_path


def process_page(page_name: str, extracted_dir: Path, markdown_dir: Path):
    """Process a single page."""
    print(f"\nProcessing {page_name}...")
    
    # Load reindexed OCR
    try:
        ocr_words = load_reindexed_ocr(page_name, extracted_dir)
    except FileNotFoundError:
        print(f"  ERROR: Reindexed OCR not found. Run reindex_ocr.py first.")
        return
    print(f"  Loaded {len(ocr_words)} OCR words")
    
    # Load markdown
    try:
        markdown = load_markdown(page_name, markdown_dir)
    except FileNotFoundError:
        print(f"  ERROR: Markdown not found at {markdown_dir}")
        return
    
    # Tokenize markdown
    md_words = tokenize_markdown(markdown)
    print(f"  Loaded {len(md_words)} markdown words")
    
    # Fix up OCR
    fixed_words, num_fixes = fixup_ocr(ocr_words, md_words)
    print(f"  Fixed {num_fixes} words ({100*num_fixes/len(ocr_words):.1f}%)")
    
    # Show some examples of fixes
    if num_fixes > 0:
        print("  Examples:")
        count = 0
        for w in fixed_words:
            if 'original_text' in w:
                print(f"    '{w['original_text']}' -> '{w['text']}'")
                count += 1
                if count >= 5:
                    break
    
    # Save
    save_fixedup(fixed_words, page_name, extracted_dir)


def main():
    parser = argparse.ArgumentParser(description='Fix up OCR using vision model markdown')
    parser.add_argument('--page', type=str, help='Specific page to process')
    parser.add_argument('--extracted-dir', type=str, default='extracted_images', help='OCR directory')
    parser.add_argument('--markdown-dir', type=str, 
                       default='extracted_images/qwen_qwen3-vl-235b-a22b-thinking',
                       help='Vision model markdown directory')
    args = parser.parse_args()
    
    extracted_dir = Path(args.extracted_dir)
    markdown_dir = Path(args.markdown_dir)
    
    if args.page:
        process_page(args.page, extracted_dir, markdown_dir)
    else:
        # Process all pages with reindexed OCR
        for ocr_file in extracted_dir.glob('*_reindexed.json'):
            page_name = ocr_file.stem.replace('_reindexed', '')
            process_page(page_name, extracted_dir, markdown_dir)


if __name__ == '__main__':
    main()
