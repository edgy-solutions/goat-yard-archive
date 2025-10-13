#!/usr/bin/env python3
"""
Helper functions for chapter:verse notation

New notation supports:
- Single chapter: "27:42-46" (chapter 27, verses 42-46)
- Chapter-spanning: "27:42-28:1" (from ch 27 v42 through ch 28 v1)
- List: "27:5,6,7" or "27:42-46,28:1-3"
"""

import re
from typing import Tuple, List, Optional, Dict

def parse_verse_notation(notation: str) -> List[Dict[str, any]]:
    """
    Parse chapter:verse notation into list of chapter/verse dictionaries.
    
    Args:
        notation: String like "27:42-46" or "27:42-46,28:1" or "27:5,6,7"
    
    Returns:
        List of dicts with 'chapter' and 'verses' keys
        
    Examples:
        "27:42-46" -> [{'chapter': 27, 'verses': [42,43,44,45,46]}]
        "27:42-46,28:1" -> [{'chapter': 27, 'verses': [42,43,44,45,46]}, 
                           {'chapter': 28, 'verses': [1]}]
        "27:5,6,7" -> [{'chapter': 27, 'verses': [5,6,7]}]
    """
    if not notation:
        return []
    
    # Split by comma to get chapter:verse segments
    segments = notation.split(',')
    
    # Group verses by chapter
    verses_by_ch = {}
    current_ch = None
    
    for segment in segments:
        segment = segment.strip()
        
        # Check if this segment has a chapter marker
        if ':' in segment:
            # Extract chapter and verse part
            parts = segment.split(':', 1)
            if len(parts) != 2:
                # Invalid format, skip this segment
                continue
            ch_str, v_part = parts
            try:
                current_ch = int(ch_str)
            except ValueError:
                # Invalid chapter number, skip
                continue
            
            # Parse verse part (could be single, range, or list)
            if '-' in v_part:
                # Range like "42-46" or cross-chapter like "42-28:1" (legacy)
                # Note: Our new format is "27:42-46,28:1" so this shouldn't happen
                # But handle it just in case
                parts = v_part.split('-')
                if ':' in parts[1]:
                    # Cross-chapter range (not our standard format, but handle it)
                    start_v = int(parts[0])
                    # Just add the start verse, the next segment will handle the end
                    verse_list = [start_v]
                else:
                    # Same-chapter range like "42-46"
                    start_v, end_v = map(int, v_part.split('-'))
                    verse_list = list(range(start_v, end_v + 1))
            else:
                # Single verse
                verse_list = [int(v_part)]
            
            if current_ch not in verses_by_ch:
                verses_by_ch[current_ch] = []
            verses_by_ch[current_ch].extend(verse_list)
        else:
            # No chapter marker, assume it's a verse for the current chapter
            if current_ch is None:
                # No chapter context, skip
                continue
            
            if '-' in segment:
                # Range
                start_v, end_v = map(int, segment.split('-'))
                verse_list = list(range(start_v, end_v + 1))
            else:
                # Single verse
                verse_list = [int(segment)]
            
            if current_ch not in verses_by_ch:
                verses_by_ch[current_ch] = []
            verses_by_ch[current_ch].extend(verse_list)
    
    # Convert to list of dicts
    result = []
    for ch in sorted(verses_by_ch.keys()):
        result.append({
            'chapter': ch,
            'verses': sorted(verses_by_ch[ch])
        })
    
    return result


def format_verse_notation(chapter: int, verse: str) -> str:
    """
    Convert old (chapter, verse) format to new notation.
    
    Args:
        chapter: Chapter number
        verse: Verse string (e.g., "42-46" or "5,6,7")
        
    Returns:
        New notation string (e.g., "27:42-46" or "27:5,6,7")
    """
    if not verse:
        return f"{chapter}:1"
    
    return f"{chapter}:{verse}"


def format_spanning_notation(start_chapter: int, start_verse: str, 
                            end_chapter: int, end_verse: str) -> str:
    """
    Create chapter-spanning notation.
    
    Args:
        start_chapter: Starting chapter
        start_verse: Starting verse(s) in that chapter
        end_chapter: Ending chapter  
        end_verse: Ending verse(s) in that chapter
        
    Returns:
        Spanning notation like "27:42-46,28:1" or "27:42-28:1"
    """
    if start_chapter == end_chapter:
        return format_verse_notation(start_chapter, f"{start_verse}-{end_verse}")
    
    # Spanning chapters
    # If end_verse is a single number, can use compact notation
    if end_verse.isdigit():
        return f"{start_chapter}:{start_verse}-{end_chapter}:{end_verse}"
    else:
        return f"{start_chapter}:{start_verse},{end_chapter}:{end_verse}"


def extract_chapter_verse(notation: str) -> Tuple[Optional[int], Optional[str]]:
    """
    Extract primary chapter and verse string from notation.
    For backward compatibility with code expecting separate fields.
    
    Args:
        notation: New notation like "27:42-46" or "27:42-28:1"
        
    Returns:
        (chapter, verse_string) tuple
        For "27:42-46" returns (27, "42-46")
        For "27:42-28:1" returns (27, "42-46,28:1") or similar representation
    """
    if not notation:
        return None, None
    
    # Find first chapter number
    match = re.match(r'(\d+):', notation)
    if not match:
        return None, notation
    
    chapter = int(match.group(1))
    
    # Extract verse part (everything after first colon)
    verse_part = notation[match.end():]
    
    return chapter, verse_part


def is_chapter_spanning(notation: str) -> bool:
    """
    Check if notation spans multiple chapters.
    
    Args:
        notation: Verse notation string
        
    Returns:
        True if it spans chapters, False otherwise
    """
    if not notation:
        return False
    
    # Count chapter markers (:)
    # More than one chapter marker means spanning
    return notation.count(':') > 1


# Test the functions
if __name__ == '__main__':
    print("Testing verse notation helpers")
    print("=" * 50)
    
    # Test parsing
    test_cases = [
        "27:42-46",
        "27:42-46,28:1",  # This is our actual format for chapter-spanning
        "27:5,6,7",
        "1:1",
    ]
    
    for notation in test_cases:
        parsed = parse_verse_notation(notation)
        spanning = is_chapter_spanning(notation)
        ch, v = extract_chapter_verse(notation)
        print(f"\n{notation}")
        print(f"  Parsed: {parsed[:5]}..." if len(parsed) > 5 else f"  Parsed: {parsed}")
        print(f"  Spanning: {spanning}")
        print(f"  Extract: chapter={ch}, verse={v}")
    
    # Test formatting
    print("\n\nTesting formatting")
    print("=" * 50)
    print(f"format_verse_notation(27, '42-46') = {format_verse_notation(27, '42-46')}")
    print(f"format_spanning_notation(27, '42-46', 28, '1') = {format_spanning_notation(27, '42-46', 28, '1')}")
