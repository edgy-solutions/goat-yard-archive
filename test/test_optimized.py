"""Quick test of the optimized DSPy model."""
import os
import dspy
from train_dspy import GillNormalizer
from normalize_markdown import verify_normalization

print("Setting up LM...")
api_key = os.environ.get('OPENROUTER_API_KEY')
lm = dspy.LM(model='openrouter/deepseek/deepseek-chat', api_key=api_key, temperature=0.0)
dspy.configure(lm=lm)

print("Loading optimized model...")
optimized = GillNormalizer()
optimized.load('optimized_normalizer.json')
print("Model loaded!")

# Test on page 95
source_path = r'C:\Users\cnogr\git\extract\extracted_images\qwen_qwen3-vl-235b-a22b-thinking\page95_image1.md'
print(f"\nTesting: {os.path.basename(source_path)}")

with open(source_path, 'r', encoding='utf-8') as f:
    source = f.read()

print(f"Source length: {len(source)} chars")
print("Running inference...")

result = optimized(raw_markdown=source)
pred_text = result.normalized_markdown if hasattr(result, 'normalized_markdown') else str(result)

print(f"Output length: {len(pred_text)} chars")

verification = verify_normalization(source, pred_text)
print(f"\nVerification passed: {verification.passed}")
print(f"Footnote count match: {verification.footnote_count_match}")
print(f"Body footnotes: {verification.body_footnote_count}")

if verification.footnote_issues:
    print(f"Issues: {verification.footnote_issues}")
else:
    print("No issues!")
