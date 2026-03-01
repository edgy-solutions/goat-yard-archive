"""Quick test of the optimized DSPy model."""
import os
import dspy
import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'pipeline', 'scripts'))

from train_dspy import GillNormalizer
from normalize_markdown import verify_normalization

print("Setting up LM...")
api_key = os.environ.get('OPENROUTER_API_KEY')
lm = dspy.LM(model='openrouter/deepseek/deepseek-chat', api_key=api_key, temperature=0.0)
dspy.configure(lm=lm)

print("Loading optimized model...")
optimized = GillNormalizer()
optimized.load(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'pipeline', 'models', 'optimized_normalizer.json'))
print("Model loaded!")

# Test on page 95
base_dir = os.environ.get('COMMENTARY_DATA_DIR', '.')
source_path = os.environ.get('TEST_MARKDOWN_FILE', os.path.join(base_dir, 'volume1', 'page95_image1.md'))
print(f"\nTesting: {os.path.basename(source_path)}")

if not os.path.exists(source_path):
    print(f"Skipping file read; test markdown file {source_path} not found.")
    print("Set TEST_MARKDOWN_FILE environment variable to explicitly test inference.")
    import sys
    sys.exit(0)

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
