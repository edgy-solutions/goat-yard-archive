"""Quick test to verify footnote removal works."""
import sys
import io
from pathlib import Path

# Fix encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, str(Path(__file__).parent.parent / "pipeline" / "scripts"))

from get_md import get_greek_verse

# Test Matthew 2:11 which has a footnote
print("Testing Matthew 2:11 (has footnote in USFM)")
result = get_greek_verse("Matthew", 2, "11")

if result:
    verse_11 = result.get("11", "")
    print(f"\nExtracted text (first 150 chars):")
    print(verse_11[:150])
    
    # Check for footnote markers
    has_footnote_marker = "\\f" in verse_11
    
    print(f"\nHas footnote marker (\\f): {has_footnote_marker}")
    
    if has_footnote_marker:
        print("❌ FAILED: Footnote markers still present!")
        print(f"Full text: {verse_11}")
    else:
        print("✓ SUCCESS: Footnote markers removed!")
else:
    print("❌ FAILED: Could not extract verse")
