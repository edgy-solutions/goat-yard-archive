"""Test phrase matching scores at different positions."""
import json
from rapidfuzz import fuzz

with open('extracted_images/page108_image1_fixedup.json', 'r', encoding='utf-8') as f:
    words = json.load(f)

# The end phrase to match
end_phrase = "who was the first, which with Pythagoras was the highest wisdom, who imposed names on all things?"
phrase_words = end_phrase.split()
window_size = len(phrase_words)

print(f"End phrase has {window_size} words")
print(f"Phrase: {end_phrase[:50]}...")

# Check score at different positions
positions_to_check = [505, 510, 513, 518, 520]

# Get body indices (non-footnote)
body_indices = [i for i, w in enumerate(words) if not w.get('is_footnote', False) and not w.get('is_header', False)]

print(f"\nTotal body words: {len(body_indices)}")

# Find where in body_indices position 513 is
for pos in positions_to_check:
    if pos in body_indices:
        bi = body_indices.index(pos)
        # Get window starting at this body index
        if bi + window_size <= len(body_indices):
            window_indices = body_indices[bi:bi + window_size]
            window_text = ' '.join(words[idx]['text'] for idx in window_indices)
            score = fuzz.ratio(end_phrase.lower(), window_text.lower())
            print(f"\nPos {pos} (bi={bi}):")
            print(f"  Window text: {window_text[:80]}...")
            print(f"  Score: {score}")

# Find the best match
print("\n=== Finding best match ===")
best_score = 0
best_pos = -1
for i in range(len(body_indices) - window_size + 1):
    window_indices = body_indices[i:i + window_size]
    window_text = ' '.join(words[idx]['text'] for idx in window_indices)
    score = fuzz.ratio(end_phrase.lower(), window_text.lower())
    if score > best_score:
        best_score = score
        best_pos = window_indices[0]
        best_i = i

print(f"Best match at idx {best_pos} (bi={best_i}) with score {best_score}")
window_indices = body_indices[best_i:best_i + window_size]
window_text = ' '.join(words[idx]['text'] for idx in window_indices)
print(f"Window: {window_text[:100]}...")
