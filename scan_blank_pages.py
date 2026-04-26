import pathlib
import re
import json
from collections import defaultdict


def find_blank_pages(vol_name: str):
    """
    Scans a volume for pages that the vision model flagged as having
    'no extractable text' or blank/decorative pages.
    """
    base_dir = pathlib.Path(f'/root/git/dr-voluminous/commentary/{vol_name}')
    qwen_dir = base_dir / 'qwen_qwen3-vl-235b-a22b-thinking'

    if not qwen_dir.exists():
        print(f"Qwen directory not found for {vol_name}")
        return []

    # Patterns that indicate a blank/decorative page from the vision model
    blank_patterns = [
        re.compile(r'no\s+extractable\s+text', re.IGNORECASE),
        re.compile(r'no\s+text\s+to\s+extract', re.IGNORECASE),
        re.compile(r'blank\s+page', re.IGNORECASE),
        re.compile(r'decorative\s+(initial|letter|page)', re.IGNORECASE),
        re.compile(r'no\s+content\s+to\s+convert', re.IGNORECASE),
        re.compile(r'ornamental\s+(design|floral|border)', re.IGNORECASE),
        re.compile(r'image\s+contains\s+(only|just)\s*[^\n]*(?:illustration|decoration|ornament)', re.IGNORECASE),
    ]

    blank_pages = []

    md_files = sorted(qwen_dir.glob('*.md'))
    for md_file in md_files:
        # Skip normalized files, we want the raw vision model output
        if '_normalized' in md_file.name:
            continue

        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for blank page indicators
        is_blank = any(p.search(content) for p in blank_patterns)

        # Also check if the file is extremely short (less than 100 chars after stripping)
        stripped = content.strip()
        very_short = len(stripped) < 100

        # Check OCR file size / word count
        page_stem = md_file.stem  # e.g. page882_image7
        ocr_file = base_dir / f'{page_stem}_ocr.json'
        ocr_empty = False
        if ocr_file.exists():
            try:
                with open(ocr_file, 'r') as f:
                    ocr_data = json.load(f)
                if not ocr_data:
                    ocr_empty = True
            except:
                pass

        if is_blank or (very_short and ocr_empty):
            # Get file size of the PNG
            png_file = base_dir / f'{page_stem}.png'
            png_size = png_file.stat().st_size if png_file.exists() else 0

            # Get the "reason" snippet
            reason = "Vision model reported no extractable text"
            if is_blank:
                for p in blank_patterns:
                    match = p.search(content)
                    if match:
                        start = max(0, match.start() - 40)
                        end = min(len(content), match.end() + 40)
                        reason = content[start:end].replace('\n', ' ')
                        break
            elif very_short and ocr_empty:
                reason = f"Very short markdown ({len(stripped)} chars) + empty OCR"

            blank_pages.append({
                'page': page_stem,
                'png_size_kb': round(png_size / 1024, 1),
                'md_char_count': len(stripped),
                'ocr_empty': ocr_empty,
                'reason': reason,
            })

    return blank_pages


def main():
    print("=" * 80)
    print("BLANK / DECORATIVE PAGE AUDIT TRAIL")
    print("=" * 80)

    for vol in ['volume1', 'volume7']:
        pages = find_blank_pages(vol)
        print(f"\n{'=' * 80}")
        print(f"{vol.upper()}: {len(pages)} blank/decorative pages found")
        print("=" * 80)

        if not pages:
            print("  No blank pages detected.")
            continue

        # Group by reason for easier reading
        by_reason = defaultdict(list)
        for p in pages:
            by_reason[p['reason']].append(p)

        for reason, items in by_reason.items():
            print(f"\n  Reason: {reason}")
            for item in items:
                print(f"    - {item['page']}: PNG={item['png_size_kb']}KB, MD={item['md_char_count']} chars, OCR_empty={item['ocr_empty']}")

    print(f"\n{'=' * 80}")
    print("AUDIT COMPLETE")
    print("=" * 80)
    print("\nThese pages are safe to skip during alignment/ingestion.")
    print("They contain decorative initials, chapter headings, or blank pages.")


if __name__ == "__main__":
    main()
