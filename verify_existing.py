#!/usr/bin/env python3
"""Quick script to verify existing normalized files."""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')
from normalize_markdown import verify_normalization, post_process_headings
from pathlib import Path
import logging

# Find normalized files across all extracted_images* directories
base_path = Path(r'C:\Users\cnogr\git\extract')
grand_passed = 0
grand_failed = 0
dir_summaries = []

# Scan directories
dirs_to_scan = sorted([d for d in base_path.glob('extracted_images*') if d.is_dir()])
logging.info(f"Found {len(dirs_to_scan)} directories to scan: {[d.name for d in dirs_to_scan]}")

for img_dir in dirs_to_scan:
    print(f"\n{'='*60}")
    print(f"DIRECTORY: {img_dir.name}")
    print(f"{'='*60}")
    
    normalized_files = sorted(list(img_dir.rglob('*_normalized.md')))
    
    # Filter files if argument provided
    if len(sys.argv) > 1:
        filter_str = sys.argv[1]
        normalized_files = [f for f in normalized_files if filter_str in f.name]
    
    if not normalized_files:
        if len(sys.argv) > 1:
            print(f"  No files matching '{sys.argv[1]}' found in {img_dir.name}.")
        else:
            print("  No normalized files found.")
        continue
        
    local_passed = 0
    local_failed = 0
    
    for norm_file in normalized_files:
        source_file = norm_file.parent / norm_file.name.replace('_normalized', '')
        if not source_file.exists():
            continue
        
        try:
            source = source_file.read_text(encoding='utf-8')
            output = norm_file.read_text(encoding='utf-8')
        except Exception as e:
            print(f"Error reading {norm_file.name}: {e}")
            local_failed += 1
            continue

        # Run verification
        result = verify_normalization(source, output)
        
        status = '✓' if result.passed else '✗'
        print(f'{status} {norm_file.name}: {result}')
        
        if 'page387' in norm_file.name: # Changed from str(source) to norm_file.name as per instruction
            # Debug print - masked
            pass
        
        if result.passed:
            local_passed += 1
        else:
            local_failed += 1
            print(f"✗ {norm_file.name}: Unauthorized changes: {len(result.unauthorized_changes)}")
            # Print details of unauthorized changes with diff-style output
            for change in result.unauthorized_changes:
                c_type = change.get('type', 'unknown')
                note = change.get('note', '')
                output_text = change.get('removed_text', '') or change.get('output_text', '')
                source_text = change.get('source_text', '')
                if source_text:
                    print(f"    [{c_type}] {note}")
                    print(f"      OUT: {output_text[:60]}...")
                    print(f"      SRC: {source_text[:60]}...")
                else:
                    print(f"    [{c_type}] {note} ({output_text[:50]}...)")
            
            if result.footnote_issues:
                print(f"    Footnote issues: {len(result.footnote_issues)}")
    
    dir_summaries.append({'name': img_dir.name, 'passed': local_passed, 'failed': local_failed})
    print(f"\n--- {img_dir.name} Summary ---")
    print(f"Passed: {local_passed}")
    print(f"Failed: {local_failed}")
    
    grand_passed += local_passed
    grand_failed += local_failed

print(f"\n{'='*60}")
print(f"FINAL REPORT")
print(f"{'='*60}")
for summary in dir_summaries:
    print(f"{summary['name']:<35} Passed: {summary['passed']:<5} Failed: {summary['failed']:<5}")
print(f"{'-'*60}")
print(f"{'GRAND TOTAL':<35} Passed: {grand_passed:<5} Failed: {grand_failed:<5}")
print(f"Total Files: {grand_passed + grand_failed}")
