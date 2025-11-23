"""
Test script to verify USFM markup cleaning.
"""
import sys
from pathlib import Path
import io

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from get_md import clean_usfm_text, get_greek_verse, get_hebrew_verse

def test_clean_usfm_text():
    """Test the USFM cleaning function."""
    print("\n=== Testing USFM Text Cleaning ===")
    
    # Test Greek text with Strong's numbers
    greek_input = "\\w Βίβλος|strong=\"G0976\"\\w* \\w γενέσεως|strong=\"G1078\"\\w* \\w Ἰησοῦ|strong=\"G2424\"\\w* \\w Χριστοῦ|strong=\"G5547\"\\w*"
    expected_greek = "Βίβλος γενέσεως Ἰησοῦ Χριστοῦ"
    result_greek = clean_usfm_text(greek_input)
    
    print(f"\nInput:    {greek_input[:100]}...")
    print(f"Expected: {expected_greek}")
    print(f"Result:   {result_greek}")
    assert result_greek == expected_greek, f"Greek cleaning failed"
    print("✓ Greek text cleaned successfully")
    
    # Test with mixed markup (some words without Strong's)
    mixed_input = "\\w Ἀβραὰμ|strong=\"G0011\"\\w* ἐγέννησε \\w τὸν|strong=\"G3588\"\\w* \\w Ἰσαάκ|strong=\"G2464\"\\w*"
    expected_mixed = "Ἀβραὰμ ἐγέννησε τὸν Ἰσαάκ"
    result_mixed = clean_usfm_text(mixed_input)
    
    print(f"\nMixed Input:  {mixed_input}")
    print(f"Expected:     {expected_mixed}")
    print(f"Result:       {result_mixed}")
    assert result_mixed == expected_mixed, f"Mixed markup cleaning failed"
    print("✓ Mixed markup cleaned successfully")
    
    # Test with footnotes (textual variants)
    footnote_input = "\\w Καὶ|strong=\"G2532\"\\w* \\w ἐλθόντες|strong=\"G2064\"\\w* \\w εἰς|strong=\"G1519\"\\w* \\w τὴν|strong=\"G3588\"\\w* \\w οἰκίαν|strong=\"G3614\"\\w*, \\f + \\fr 2:11 \\ft εὗρον ¦ εἶδον SCR\\f*\\w εὗρον|strong=\"G2147\"\\w* \\w τὸ|strong=\"G3588\"\\w* \\w παιδίον|strong=\"G3813\"\\w*"
    expected_footnote = "Καὶ ἐλθόντες εἰς τὴν οἰκίαν, εὗρον τὸ παιδίον"
    result_footnote = clean_usfm_text(footnote_input)
    
    print(f"\nFootnote Input:  {footnote_input[:80]}...")
    print(f"Expected:        {expected_footnote}")
    print(f"Result:          {result_footnote}")
    assert result_footnote == expected_footnote, f"Footnote cleaning failed: got '{result_footnote}'"
    print("✓ Footnote markup cleaned successfully")

def test_greek_extraction_cleaned():
    """Test that Greek extraction now returns clean text."""
    print("\n=== Testing Greek Extraction with Clean Text ===")
    
    # Test Matthew 1:1
    print("\nTesting Matthew 1:1")
    result = get_greek_verse("Matthew", 1, "1")
    
    if result:
        verse_text = result.get("1", "")
        print(f"Extracted text: {verse_text[:100]}...")
        
        # Check that it doesn't contain USFM markup
        assert "\\w" not in verse_text, "Text still contains \\w tags"
        assert "|strong=" not in verse_text, "Text still contains Strong's numbers"
        assert "\\w*" not in verse_text, "Text still contains \\w* tags"
        
        # Check that it contains Greek text
        assert "Βίβλος" in verse_text, "Greek text not found"
        assert "γενέσεως" in verse_text, "Greek text not found"
        
        print("✓ Greek text extracted without USFM markup")
    else:
        print("✗ Failed to extract Greek text")
        raise Exception("Greek extraction failed")

def test_hebrew_extraction_cleaned():
    """Test that Hebrew extraction also returns clean text."""
    print("\n=== Testing Hebrew Extraction with Clean Text ===")
    
    # Test Genesis 1:1
    print("\nTesting Genesis 1:1")
    result = get_hebrew_verse("Genesis", 1, "1")
    
    if result:
        verse_text = result.get("1", "")
        print(f"Extracted text: {verse_text[:100]}...")
        
        # Check that it doesn't contain USFM markup
        assert "\\w" not in verse_text, "Text still contains \\w tags"
        assert "|strong=" not in verse_text, "Text still contains Strong's numbers"
        assert "\\w*" not in verse_text, "Text still contains \\w* tags"
        
        print("✓ Hebrew text extracted without USFM markup")
    else:
        print("✗ Failed to extract Hebrew text")
        raise Exception("Hebrew extraction failed")

if __name__ == "__main__":
    print("=" * 60)
    print("Testing USFM Markup Cleaning")
    print("=" * 60)
    
    try:
        test_clean_usfm_text()
        test_greek_extraction_cleaned()
        test_hebrew_extraction_cleaned()
        
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
