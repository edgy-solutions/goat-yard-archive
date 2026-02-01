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
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

# Base configuration
BASE_DIR = Path(os.getenv("COMMENTARY_DATA_DIR", os.getcwd()))
# Default to volume1 for generic usage, matching other scripts
DEFAULT_EXTRACTED_DIR = BASE_DIR / "volume1"
DEFAULT_MARKDOWN_DIR = DEFAULT_EXTRACTED_DIR / "qwen_qwen3-vl-235b-a22b-thinking"
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


def load_metadata(page_name: str, extracted_dir: Path) -> Optional[Dict]:
    """Load page metadata JSON if available."""
    meta_path = extracted_dir / f"{page_name}_metadata.json"
    if meta_path.exists():
        with open(meta_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def is_header_word(word: Dict, metadata: Optional[Dict], header_y_threshold: float) -> bool:
    """
    Check if a word is likely a header word based on metadata and position.
    
    Header words are:
    - Page numbers (match metadata page_number)
    - Book name (match metadata book_name like "GENESIS")
    - Chapter/verse indicators (like "CH. II. V. 9")
    - Words in the top region of the page (above header_y_threshold)
    """
    if word.get('top', 0) > header_y_threshold:
        return False  # Not in header region
    
    word_text = word.get('text', '').upper().strip('.,;:!?"\'')
    
    # Check against metadata if available
    if metadata:
        # Check page number
        page_num = str(metadata.get('page_number', ''))
        if word_text == page_num:
            return True
        
        # Check book name
        book_name = metadata.get('book_name', '').upper()
        if word_text == book_name or word_text.rstrip('.') == book_name:
            return True
        
        # Check chapter (roman numeral or number)
        chapter = metadata.get('chapter')
        if chapter:
            roman_numerals = {1: 'I', 2: 'II', 3: 'III', 4: 'IV', 5: 'V', 
                            6: 'VI', 7: 'VII', 8: 'VIII', 9: 'IX', 10: 'X'}
            if str(chapter) == word_text or roman_numerals.get(chapter, '') == word_text:
                return True
    
    # Common header patterns regardless of metadata
    if word_text in ['CH', 'CH.', 'V', 'V.', 'VER', 'VER.']:
        return True
    
    return False


def tokenize_markdown(markdown: str) -> Tuple[List[str], List[str]]:
    """
    Extract words from markdown, separating body text from footnote content.
    
    Footnote lines are those starting with ^a, ^b, etc. (footnote definitions).
    These are separated so we can match OCR body to markdown body first,
    then match OCR footnotes to markdown footnotes.
    
    Returns (body_words, footnote_words).
    """
    lines = markdown.split('\n')
    body_lines = []
    footnote_lines = []
    
    for line in lines:
        stripped = line.strip()
        # Footnote definition lines: either "^letter" or "[^letter]:" format
        if re.match(r'^\^[a-zA-Z0-9]', stripped) or re.match(r'^\[\^[a-zA-Z0-9]+\]:', stripped):
            footnote_lines.append(line)
        else:
            # Remove inline footnote references like ^a, ^b, [^c] from body
            clean_line = re.sub(r'\^[a-zA-Z0-9]+', '', line)
            clean_line = re.sub(r'\[\^[a-zA-Z0-9]+\]', '', clean_line)
            body_lines.append(clean_line)
    
    def clean_and_tokenize(text: str) -> List[str]:
        text = re.sub(r'\[.*?\]\(.*?\)', '', text)  # links
        text = re.sub(r'\[\^.*?\]', '', text)  # footnote refs
        text = re.sub(r'\*\*?|__?', '', text)  # bold/italic
        text = re.sub(r'#+\s*', '', text)  # headers
        text = re.sub(r'`.*?`', '', text)  # code
        text = re.sub(r'<[^>]+>', '', text)  # HTML tags
        words = re.findall(r"[\w'-]+[.,;:!?]?|[.,;:!?]", text)
        return [w for w in words if w and len(w) > 0]
    
    body_words = clean_and_tokenize('\n'.join(body_lines))
    footnote_words = clean_and_tokenize('\n'.join(footnote_lines))
    
    return body_words, footnote_words



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
        return ocr_words, [], 0
    
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
        
        # Check for hyphenated word: OCR "some-" + "thing" = MD "something"
        elif word_text.endswith('-') and ocr_idx + 1 < len(ocr_words) and md_idx < len(md_words):
            next_ocr = ocr_words[ocr_idx + 1]['text']
            combined = word_text.rstrip('-') + next_ocr
            combined_score = word_match_score(combined, md_words[md_idx])
            
            if combined_score >= 60:
                # Match! Keep both OCR words separate (preserve spatial order)
                # but mark as body text
                fixed_word1 = ocr_word.copy()
                fixed_word2 = ocr_words[ocr_idx + 1].copy()
                body_words.append(fixed_word1)
                body_words.append(fixed_word2)
                ocr_idx += 2
                md_idx += 1
            else:
                # Try other matching strategies
                score = 0  # Reset to trigger fallback below
        
        # Check for fused word: OCR "wordword" = MD "word" + "word"
        elif md_idx + 1 < len(md_words):
            fused_md = md_words[md_idx] + md_words[md_idx + 1]
            fused_score = word_match_score(word_text, fused_md)
            
            if fused_score >= 60:
                # Match! Add space to OCR word text but keep same coords
                fixed_word = ocr_word.copy()
                # Insert space at the likely split point
                split_pos = len(md_words[md_idx])
                if split_pos < len(word_text):
                    fixed_word['text'] = word_text[:split_pos] + ' ' + word_text[split_pos:]
                    fixed_word['original_text'] = word_text
                    num_spelling_fixes += 1
                body_words.append(fixed_word)
                ocr_idx += 1
                md_idx += 2  # Skip both MD words
            else:
                score = 0  # Reset to trigger fallback
        
        if score < 60:
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
    
    return body_words, footnote_candidates, num_spelling_fixes


def fixup_ocr_with_footnotes(ocr_words: List[Dict], body_md_words: List[str], 
                              footnote_md_words: List[str]) -> Tuple[List[Dict], int, int]:
    """
    Fix up OCR with footnote content checking.
    
    After initial matching, checks if any body words match the markdown footnote
    content. Words that match footnote content are moved to the footnote section.
    """
    # First pass: match against body markdown
    body_words, footnote_candidates, num_spelling = fixup_ocr(ocr_words, body_md_words)
    
    # Second pass: detect words with Y position significantly out of sequence
    # If a word's Y is far from its neighbors in the body sequence, it's likely a footnote
    # that matched body text but is spatially in the footnote region
    if len(body_words) > 3:
        y_gap_threshold = 500  # Pixels - if Y jumps by more than this, likely footnote
        
        new_body = []
        for i, word in enumerate(body_words):
            # Get the expected Y from neighboring words
            neighbor_ys = []
            for offset in [-3, -2, -1, 1, 2, 3]:
                ni = i + offset
                if 0 <= ni < len(body_words):
                    neighbor_ys.append(body_words[ni]['top'])
            
            if neighbor_ys:
                avg_neighbor_y = sum(neighbor_ys) / len(neighbor_ys)
                y_diff = abs(word['top'] - avg_neighbor_y)
                
                # If this word's Y is way off from neighbors, it's probably a footnote
                if y_diff > y_gap_threshold:
                    footnote_candidates.append(word)
                else:
                    new_body.append(word)
            else:
                new_body.append(word)
        body_words = new_body
    
    # Mark words with is_footnote flag
    for word in body_words:
        word['is_footnote'] = False
    for word in footnote_candidates:
        word['is_footnote'] = True
    
    # Combine: body first, then footnotes
    result = body_words + footnote_candidates
    
    # Update reading indices
    for i, word in enumerate(result):
        word['reading_index'] = i
    
    return result, num_spelling, len(footnote_candidates)


def save_fixedup(words: List[Dict], page_name: str, output_dir: Path):
    """Save fixed-up OCR to JSON file."""
    output_path = output_dir / f"{page_name}_fixedup.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(words, f, indent=2, ensure_ascii=False)
    print(f"Saved: {output_path}")
    return output_path


def process_page(page_name: str, extracted_dir: Path, markdown_dir: Path, overwrite: bool = False):
    """Process a single page."""
    output_path = extracted_dir / f"{page_name}_fixedup.json"
    if output_path.exists() and not overwrite:
        print(f"Skipping {page_name} (output exists)")
        return

    print(f"\nProcessing {page_name}...")
    
    # Load reindexed OCR
    try:
        ocr_words = load_reindexed_ocr(page_name, extracted_dir)
    except FileNotFoundError:
        print(f"  ERROR: Reindexed OCR not found. Run reindex_ocr.py first.")
        return
    print(f"  Loaded {len(ocr_words)} OCR words")
    
    # Load metadata for header detection
    metadata = load_metadata(page_name, extracted_dir)
    if metadata:
        print(f"  Metadata: page={metadata.get('page_number')}, book={metadata.get('book_name')}")
    
    # Load markdown
    try:
        markdown = load_markdown(page_name, markdown_dir)
    except FileNotFoundError:
        print(f"  ERROR: Markdown not found at {markdown_dir}")
        return
    
    # Pre-filter header words using metadata
    # Header words are in the top 3% of the page and match metadata patterns
    if ocr_words:
        all_y = [w['top'] for w in ocr_words]
        min_y = min(all_y)
        max_y = max(all_y)
        header_y_threshold = min_y + ((max_y - min_y) * 0.03)  # Top 3%
        
        body_ocr_words = []
        header_words = []
        for word in ocr_words:
            if is_header_word(word, metadata, header_y_threshold):
                word_copy = word.copy()
                word_copy['is_header'] = True
                header_words.append(word_copy)
            else:
                body_ocr_words.append(word)
        
        if header_words:
            print(f"  Excluded {len(header_words)} header words: {[w['text'][:10] for w in header_words[:5]]}")
    else:
        body_ocr_words = ocr_words
        header_words = []
    
    # Tokenize markdown - separate body from footnotes
    body_md_words, footnote_md_words = tokenize_markdown(markdown)
    print(f"  Markdown: {len(body_md_words)} body words, {len(footnote_md_words)} footnote words")
    
    # Fix up OCR - match body OCR against body markdown, then check footnotes
    fixed_words, num_spelling, num_footnotes = fixup_ocr_with_footnotes(
        body_ocr_words, body_md_words, footnote_md_words)
    
    # Add header words back at the beginning, marked as is_header=True
    # They stay at their original positions for bounding box calculation
    for word in header_words:
        word['is_footnote'] = False
    result_words = header_words + fixed_words
    
    # Update reading indices
    for i, word in enumerate(result_words):
        word['reading_index'] = i
    
    print(f"  Fixed {num_spelling} spelling errors ({100*num_spelling/len(ocr_words):.1f}%)")
    print(f"  Moved {num_footnotes} words to footnotes ({100*num_footnotes/len(ocr_words):.1f}%)")
    
    # Save
    save_fixedup(result_words, page_name, extracted_dir)


def main():
    parser = argparse.ArgumentParser(description='Fix up OCR using vision model markdown')
    parser.add_argument('--page', type=str, help='Specific page to process')
    parser.add_argument('--extracted-dir', type=str, default=str(DEFAULT_EXTRACTED_DIR), 
                       help='OCR directory (default: $COMMENTARY_DATA_DIR/volume1)')
    parser.add_argument('--markdown-dir', type=str, 
                       default=str(DEFAULT_MARKDOWN_DIR),
                       help='Vision model markdown directory (default: $COMMENTARY_DATA_DIR/volume1/qwen_qwen3...)')
    parser.add_argument('--overwrite', action='store_true', help='Overwrite existing files')
    args = parser.parse_args()
    
    extracted_dir = Path(args.extracted_dir)
    markdown_dir = Path(args.markdown_dir)
    
    if args.page:
        process_page(args.page, extracted_dir, markdown_dir, args.overwrite)
    else:
        for ocr_file in extracted_dir.glob('*_reindexed.json'):
            page_name = ocr_file.stem.replace('_reindexed', '')
            process_page(page_name, extracted_dir, markdown_dir, args.overwrite)


if __name__ == '__main__':
    main()
