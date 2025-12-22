"""Check different window sizes for phrase matching."""
import json
from rapidfuzz import fuzz

# Load fixed-up OCR
with open('extracted_images/page100_image1_fixedup.json', 'r', encoding='utf-8') as f:
    words = json.load(f)

# V31 start: find "And God saw every thing"
print("=== Finding 'And God saw' ===")
for i, w in enumerate(words[:150]):
    if 'And' in w['text'] and i < len(words) - 3:
        next_words = ' '.join(words[j]['text'] for j in range(i, min(i+5, len(words))))
        if 'God' in next_words and 'saw' in next_words:
            print(f"  idx {i}: top={w['top']:.0f} | '{next_words}'")

# V31 end: find the TRUE end "resurrection are 3000 years"
print("\n=== Finding 'resurrection are 3000 years' ===")
for i in range(len(words) - 4):
    if 'resurrection' in words[i]['text'].lower():
        context = ' '.join(words[j]['text'] for j in range(i, min(i+6, len(words))))
        if '3000' in context:
            col = "L" if words[i]['left'] < 1873 else "R"
            print(f"  idx {i}: {col} top={words[i]['top']:.0f} | '{context}'")

# Try matching with 10 words instead of 7
v31_end = "and from this thy age unto the resurrection are 3000 years"
print(f"\n=== Full phrase matching (all {len(v31_end.split())} words) ===")
end_words = v31_end.split()
for i in range(len(words) - len(end_words)):
    window = ' '.join(words[j]['text'] for j in range(i, i+len(end_words)))
    score = fuzz.ratio(v31_end.lower(), window.lower())
    if score >= 50:
        col = "L" if words[i]['left'] < 1873 else "R"
        print(f"  idx {i}: score={score:.1f}, col={col}, top={words[i]['top']:.0f}")
        print(f"    '{window[:80]}...'")
