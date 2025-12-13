"""
Fix up OCR using vision model markdown output.

Key approach: Follow vision markdown text strictly as source of truth.
1. Walk through OCR words matching to markdown sequence
2. When a word doesn't match expected position, tag as potential footnote
3. Keep checking until a 3-word sequence matches markdown
4. Backtrack to align any missed body words
5. Move all tagged non-matching words to footnote section
"""

import json
import re
import argparse
from pathlib import Path
from typing import List, Dict, Tuple, Optional
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
    """Extract words from markdown, preserving order."""
    text = markdown
    text = re.sub(r'\[.*?\]\(.*?\)', '', text)  # links
    text = re.sub(r'\[\^.*?\]', '', text)  # footnote refs
    text = re.sub(r'\*\*?|__?', '', text)  # bold/italic
    text = re.sub(r'#+\s*', '', text)  # headers
    text = re.sub(r'`.*?`', '', text)  # code
    text = re.sub(r'<[^>]+>', '', text)  # HTML tags
    
    words = re.findall(r"[\w'-]+[.,;:!?]?|[.,;:!?]", text)
    return [w for w in words if w and len(w) > 0]


def word_match_score(ocr_word: str, md_word: str) -> float:
    """Calculate match score between OCR word and markdown word."""
    if not ocr_word or not md_word:
        return 0
    ocr_lower = ocr_word.lower().strip('.,;:!?"\'')
    md_lower = md_word.lower().strip('.,;:!?"\'')
    if not ocr_lower or not md_lower:
        return 0
    return fuzz.ratio(ocr_lower, md_lower)


def find_sequence_match(ocr_words: List[Dict], ocr_start: int, 
                        md_words: List[str], md_start: int,
                        window_size: int = 3, search_range: int = 50) -> Optional[Tuple[int, int]]:
    """
    Find where OCR sequence matches markdown sequence.
    Looks for a window_size word sequence that matches.
    Returns (ocr_idx, md_idx) where match starts, or None.
    """
    if ocr_start >= len(ocr_words) - window_size:
        return None
    
    # Get OCR words to match
    ocr_sequence = [ocr_words[i]['text'] for i in range(ocr_start, min(ocr_start + window_size, len(ocr_words)))]
    
    # Search in markdown
    for md_idx in range(md_start, min(md_start + search_range, len(md_words) - window_size + 1)):
        scores = []
        for i, ocr_word in enumerate(ocr_sequence):
            if md_idx + i < len(md_words):
                score = word_match_score(ocr_word, md_words[md_idx + i])
                scores.append(score)
        
        if scores and len(scores) == window_size:
            avg_score = sum(scores) / len(scores)
            if avg_score >= 60:  # Good sequence match
                return (ocr_start, md_idx)
    
    return None


def fix_word_spelling(ocr_text: str, reference_text: str) -> Tuple[str, bool]:
    """Fix OCR word spelling using reference."""
    if not ocr_text or not reference_text or len(ocr_text) < 2:
        return ocr_text, False
    
    score = fuzz.ratio(ocr_text.lower(), reference_text.lower())
    
    if 80 <= score < 100 and abs(len(ocr_text) - len(reference_text)) <= 2:
        if ocr_text[0].isupper():
            fixed = reference_text[0].upper() + reference_text[1:].lower()
        else:
            fixed = reference_text.lower()
        
        if ocr_text[-1] in '.,;:!?' and reference_text[-1] not in '.,;:!?':
            fixed += ocr_text[-1]
        
        return fixed, True
    
    return ocr_text, False


def fixup_ocr(ocr_words: List[Dict], md_words: List[str]) -> Tuple[List[Dict], int, int]:
    """
    Fix up OCR words by following vision markdown strictly.
    
    Algorithm:
    1. Walk through OCR words, matching to markdown sequence
    2. When match fails, tag word as potential footnote
    3. Keep tagging until we find a 3-word sequence match
    4. Resume normal matching from there
    5. Move all tagged words to footnote section at end
    """
    if not ocr_words or not md_words:
        return ocr_words, 0, 0
    
    body_words = []
    footnote_candidates = []
    num_spelling_fixes = 0
    
    ocr_idx = 0
    md_idx = 0
    
    while ocr_idx < len(ocr_words):
        ocr_word = ocr_words[ocr_idx]
        word_text = ocr_word['text']
        
        # Try to match current OCR word to expected markdown position
        if md_idx < len(md_words):
            score = word_match_score(word_text, md_words[md_idx])
        else:
            score = 0
        
        if score >= 60:
            # Good match - add to body
            fixed_word = ocr_word.copy()
            fixed_text, was_fixed = fix_word_spelling(word_text, md_words[md_idx])
            if was_fixed:
                fixed_word['text'] = fixed_text
                fixed_word['original_text'] = word_text
                num_spelling_fixes += 1
            
            body_words.append(fixed_word)
            ocr_idx += 1
            md_idx += 1
        else:
            # No match - this could be a footnote word mixed in
            # Try to find where we can resync with markdown
            resync = find_sequence_match(ocr_words, ocr_idx + 1, md_words, md_idx, 
                                         window_size=3, search_range=30)
            
            if resync:
                resync_ocr, resync_md = resync
                
                # Words from ocr_idx to resync_ocr-1 are footnotes
                for i in range(ocr_idx, resync_ocr):
                    footnote_candidates.append(ocr_words[i].copy())
                
                # Continue from resync point
                ocr_idx = resync_ocr
                md_idx = resync_md
            else:
                # Can't resync - tag current as footnote and continue
                footnote_candidates.append(ocr_word.copy())
                ocr_idx += 1
                # Don't advance md_idx - try to match next OCR word to same md position
    
    # Combine: body first, then footnotes
    result = body_words + footnote_candidates
    
    # Update reading indices
    for i, word in enumerate(result):
        word['reading_index'] = i
    
    return result, num_spelling_fixes, len(footnote_candidates)


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
    print(f"  Markdown: {len(md_words)} words")
    
    # Fix up OCR
    fixed_words, num_spelling, num_footnotes = fixup_ocr(ocr_words, md_words)
    print(f"  Fixed {num_spelling} spelling errors ({100*num_spelling/len(ocr_words):.1f}%)")
    print(f"  Moved {num_footnotes} words to footnotes ({100*num_footnotes/len(ocr_words):.1f}%)")
    
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
        for ocr_file in extracted_dir.glob('*_reindexed.json'):
            page_name = ocr_file.stem.replace('_reindexed', '')
            process_page(page_name, extracted_dir, markdown_dir)


if __name__ == '__main__':
    main()
