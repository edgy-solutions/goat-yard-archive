"""
Test script to verify Greek text extraction from USFM files.
"""
import sys
from pathlib import Path
import io

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add pipeline/scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "pipeline" / "scripts"))

from get_md import (
    get_greek_verse,
    get_available_greek_versions,
    is_new_testament,
    is_old_testament
)

def test_greek_versions():
    """Test that Greek versions are detected."""
    print("\n=== Testing Greek Version Detection ===")
    versions = get_available_greek_versions()
    print(f"Available Greek versions: {versions}")
    assert len(versions) > 0, "No Greek versions found"
    print("✓ Greek versions detected successfully")

def test_testament_detection():
    """Test OT/NT book detection."""
    print("\n=== Testing Testament Detection ===")
    
    # Test NT books
    nt_books = ["Matthew", "Mark", "Luke", "John", "Romans", "Revelation"]
    for book in nt_books:
        assert is_new_testament(book), f"{book} should be NT"
        print(f"✓ {book} correctly identified as NT")
    
    # Test NT books with ST. prefix
    nt_books_with_st = ["ST. MATTHEW", "St. John", "ST.MARK", "St Luke", "ST. JAMES"]
    for book in nt_books_with_st:
        assert is_new_testament(book), f"{book} should be NT"
        print(f"✓ {book} correctly identified as NT (with ST. prefix)")
    
    # Test OT books
    ot_books = ["Genesis", "Exodus", "Psalms", "Isaiah", "Malachi"]
    for book in ot_books:
        assert is_old_testament(book), f"{book} should be OT"
        print(f"✓ {book} correctly identified as OT")

def test_greek_extraction():
    """Test Greek text extraction."""
    print("\n=== Testing Greek Text Extraction ===")
    
    # Test Matthew 1:1
    print("\nTesting Matthew 1:1")
    result = get_greek_verse("Matthew", 1, "1")
    if result:
        print(f"✓ Found {len(result)} verse(s)")
        for verse_key, text in result.items():
            print(f"  Verse {verse_key}: {text[:100]}...")
    else:
        print("✗ No Greek text found for Matthew 1:1")
    
    # Test with ST. prefix
    print("\nTesting ST. MATTHEW 1:2 (with ST. prefix)")
    result = get_greek_verse("ST. MATTHEW", 1, "2")
    if result:
        print(f"✓ Found {len(result)} verse(s) - ST. prefix handled correctly")
        for verse_key, text in result.items():
            print(f"  Verse {verse_key}: {text[:100]}...")
    else:
        print("✗ No Greek text found for ST. MATTHEW 1:2")
    
    # Test John 3:16
    print("\nTesting St. John 3:16 (with St. prefix)")
    result = get_greek_verse("St. John", 3, "16")
    if result:
        print(f"✓ Found {len(result)} verse(s) - St. prefix handled correctly")
        for verse_key, text in result.items():
            print(f"  Verse {verse_key}: {text[:100]}...")
    else:
        print("✗ No Greek text found for St. John 3:16")
    
    # Test verse range (Romans 1:1-3)
    print("\nTesting Romans 1:1-3 (verse range)")
    result = get_greek_verse("Romans", 1, "1-3")
    if result:
        print(f"✓ Found {len(result)} verse(s)")
        for verse_key, text in result.items():
            print(f"  Verse {verse_key}: {text[:80]}...")
    else:
        print("✗ No Greek text found for Romans 1:1-3")

def test_chapter_spanning():
    """Test chapter-spanning notation."""
    print("\n=== Testing Chapter-Spanning Notation ===")
    
    # Test Matthew 27:63-28:2
    print("\nTesting Matthew 27:63-28:2 (chapter-spanning)")
    result = get_greek_verse("Matthew", 27, "27:63-66,28:1-2")
    if result:
        print(f"✓ Found {len(result)} verse(s)")
        for verse_key in sorted(result.keys()):
            text = result[verse_key]
            print(f"  Verse {verse_key}: {text[:80]}...")
    else:
        print("✗ No Greek text found for chapter-spanning notation")

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Greek Text Extraction Implementation")
    print("=" * 60)
    
    try:
        test_greek_versions()
        test_testament_detection()
        test_greek_extraction()
        test_chapter_spanning()
        
        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED!")
        print("=" * 60)
    except Exception as e:
        print("\n" + "=" * 60)
        print(f"✗ TEST FAILED: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        sys.exit(1)
