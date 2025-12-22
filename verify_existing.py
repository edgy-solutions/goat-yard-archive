#!/usr/bin/env python3
"""Quick script to verify existing normalized files."""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')
from normalize_markdown import verify_normalization, post_process_headings
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')

dir_path = Path(r'C:\Users\cnogr\git\extract\extracted_images\qwen_qwen3-vl-235b-a22b-thinking')

# Find normalized files
normalized_files = list(dir_path.glob('*_normalized.md'))

passed = 0
failed = 0

for norm_file in sorted(normalized_files):
    source_file = norm_file.parent / norm_file.name.replace('_normalized', '')
    if not source_file.exists():
        continue
    
    source = source_file.read_text(encoding='utf-8')
    output = norm_file.read_text(encoding='utf-8')
    
    # Run verification
    result = verify_normalization(source, output)
    
    status = '✓' if result.passed else '✗'
    print(f'{status} {norm_file.name}: {result}')
    
    if result.passed:
        passed += 1
    else:
        failed += 1
        print(f"✗ {norm_file.name}: Unauthorized changes: {len(result.unauthorized_changes)}")
        # Print details of unauthorized changes
        for change in result.unauthorized_changes:
            c_type = change.get('type', 'unknown')
            note = change.get('note', '')
            text = change.get('removed_text', '') or change.get('output_text', '')
            print(f"    [{c_type}] {note} ({text[:50]}...)")
        
        if result.footnote_issues:
            print(f"    Footnote issues: {len(result.footnote_issues)}")

print(f'\n--- Summary ---')
print(f'Passed: {passed}')
print(f'Failed: {failed}')
