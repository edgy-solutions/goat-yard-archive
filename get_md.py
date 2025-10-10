import pytesseract
from PIL import Image
import re
import sys
import json
import os
pytesseract.pytesseract.tesseract_cmd = 'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'

def extract_text_with_layout(image_path, lang='eng'):
    """Extract text from image with layout information using pytesseract."""
    img = Image.open(image_path)
    tsv_data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, lang=lang)
    return tsv_data, img.width, img.height

def save_ocr_json(tsv_data, output_path):
    """Save complete OCR data with bounding boxes to JSON file."""
    n_boxes = len(tsv_data['text'])
    ocr_data = []
    for i in range(n_boxes):
        text = tsv_data['text'][i].strip()
        if text:
            ocr_data.append({
                'text': text,
                'left': tsv_data['left'][i],
                'top': tsv_data['top'][i],
                'width': tsv_data['width'][i],
                'height': tsv_data['height'][i],
                'conf': tsv_data['conf'][i],
                'line_num': tsv_data['line_num'][i],
                'word_num': tsv_data['word_num'][i],
                'block_num': tsv_data['block_num'][i],
                'par_num': tsv_data['par_num'][i]
            })
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(ocr_data, f, indent=2, ensure_ascii=False)
    return ocr_data

def roman_to_decimal(roman):
    """Convert a Roman numeral to decimal."""
    roman = roman.upper().strip()
    roman_numerals = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    total = 0
    prev_value = 0
    for char in reversed(roman):
        if char not in roman_numerals:
            return None
        value = roman_numerals[char]
        if value < prev_value:
            total -= value
        else:
            total += value
        prev_value = value
    return total

def correct_ocr_errors(text):
    """Correct common OCR misinterpretations."""
    # Common OCR corrections
    corrections = {
        'LV.': 'IV.',  # L often misread as I
        'LI.': 'II.',  # L often misread as I
        'LII.': 'III.',
        'LIII.': 'IIII.',
        'LIV.': 'IIV.',
        'LX.': 'IX.',
        'LXI.': 'IXI.',
        'T.': 'I.',    # T often misread as I
        'TI.': 'II.',
        'TII.': 'III.',
        'Y.': 'I.',    # Y often misread as I
        'YI.': 'II.',
        'YII.': 'III.',
        'τ': 'I.',     # Greek tau misread as I (multilingual OCR)
        'Τ': 'I.',     # Greek uppercase Tau
        # Add more corrections as needed
    }
    
    corrected = text
    for wrong, right in corrections.items():
        corrected = corrected.replace(wrong, right)
    
    return corrected


def combine_verse_list_boxes(boxes, start_index):
    """Combine consecutive boxes that form a verse list like '3,' + '4.' = '3,4'."""
    if start_index >= len(boxes):
        return None, start_index
    
    verse_parts = []
    current_index = start_index
    
    # Look for patterns like "3,", "4.", "5,", etc.
    while current_index < len(boxes):
        box = boxes[current_index]
        text = box['text'].strip()
        
        # Check if this looks like part of a verse list
        if re.match(r'^[0-9IVXLCDM]+[,.]?$', text, re.IGNORECASE):
            verse_parts.append(text.replace('.', '').replace(',', ''))
            current_index += 1
            
            # If this text ends with a period, it's likely the end of the list
            if text.endswith('.'):
                break
        else:
            break
    
    if verse_parts:
        # Join the parts with commas
        combined_verse = ','.join(verse_parts)
        print(f"DEBUG: Combined verse list from boxes: {verse_parts} -> {combined_verse}")
        return combined_verse, current_index
    
    return None, start_index


def parse_verse_text(verse_text):
    """Parse verse text that may contain ranges (10-19) or lists (1,2)."""
    verse_text = verse_text.strip()
    
    # Remove trailing commas and periods first
    verse_text = verse_text.rstrip('.,')
    
    # Replace various dash characters with standard hyphen for easier processing
    # Include multiple dash types and use character codes if needed
    verse_text = verse_text.replace('\u2014', '-')  # Em dash
    verse_text = verse_text.replace('\u2013', '-')  # En dash
    verse_text = verse_text.replace('—', '-')  # Em dash (another encoding)
    verse_text = verse_text.replace('–', '-')  # En dash (another encoding)
    verse_text = verse_text.replace('―', '-')  # Horizontal bar
    
    # Handle ranges like "10-19", "I-V"
    range_patterns = [
        r'^([IVXLCDM0-9]+)-([IVXLCDM0-9]+)$',
        r'^([IVXLCDM0-9]+)\s*-\s*([IVXLCDM0-9]+)$'
    ]
    
    for pattern in range_patterns:
        match = re.match(pattern, verse_text, re.IGNORECASE)
        if match:
            start_verse = match.group(1)
            end_verse = match.group(2)
            
            # Try to parse as Roman numerals first, then as regular numbers
            start_num = roman_to_decimal(start_verse)
            if start_num is None and start_verse.isdigit():
                start_num = int(start_verse)
            
            end_num = roman_to_decimal(end_verse)
            if end_num is None and end_verse.isdigit():
                end_num = int(end_verse)
            
            if start_num and end_num:
                return f"{start_num}-{end_num}"
    
    # Handle lists like "1,2", "I,II", "1, 2"
    list_patterns = [
        r'^([IVXLCDM0-9]+)\s*,\s*([IVXLCDM0-9]+)(?:\s*,\s*([IVXLCDM0-9]+))*',
        r'^([IVXLCDM0-9]+),([IVXLCDM0-9]+)(?:,([IVXLCDM0-9]+))*'
    ]
    
    for pattern in list_patterns:
        match = re.match(pattern, verse_text, re.IGNORECASE)
        if match:
            verses = []
            for group in match.groups():
                if group:
                    # Try Roman numeral first, then regular number
                    verse_num = roman_to_decimal(group.strip())
                    if verse_num is None and group.strip().isdigit():
                        verse_num = int(group.strip())
                    if verse_num:
                        verses.append(str(verse_num))
            
            if verses:
                return ",".join(verses)
    
    # Handle single verse (existing logic)
    if re.match(r'^[IVXLCDM]+$', verse_text, re.IGNORECASE):
        verse_num = roman_to_decimal(verse_text)
        if verse_num:
            return str(verse_num)
    elif verse_text.isdigit():
        return verse_text
    
    return None


def extract_chapter_verse_from_boxes(boxes):
    """Extract chapter and verse from a list of boxes, handling multi-box patterns."""
    if not boxes:
        return None, None
    
    # Sort boxes by x-position (left to right)
    sorted_boxes = sorted(boxes, key=lambda b: b['x'])
    
    # Apply OCR corrections to all boxes
    corrected_boxes = []
    for box in sorted_boxes:
        corrected_text = correct_ocr_errors(box['text'])
        corrected_box = box.copy()
        corrected_box['text'] = corrected_text
        corrected_boxes.append(corrected_box)
        if corrected_text != box['text']:
            print(f"DEBUG: OCR correction: '{box['text']}' -> '{corrected_text}'")
    
    sorted_boxes = corrected_boxes
    
    print(f"DEBUG: Searching for chapter/verse in {len(sorted_boxes)} boxes:")
    for i, box in enumerate(sorted_boxes):
        print(f"  {i}: '{box['text']}' at x={box['x']}")
    
    # First try single-box patterns
    single_box_patterns = [
        r'CH\.?\s*([IVXLCDM]+)[\s.]*V\.?\s*([IVXLCDM]+)',
        r'Ch\.?\s*([IVXLCDM]+)[\s.]*V\.?\s*([IVXLCDM]+)',
        r'CAP\.?\s*([IVXLCDM]+)[\s.]*V\.?\s*([IVXLCDM]+)',
    ]
    
    for box in sorted_boxes:
        for pattern in single_box_patterns:
            match = re.search(pattern, box['text'], re.IGNORECASE)
            if match:
                chapter = roman_to_decimal(match.group(1))
                verse = roman_to_decimal(match.group(2))
                print(f"DEBUG: Single-box pattern found Ch.{chapter} V.{verse} in: '{box['text']}'")
                return chapter, verse
    
    # Try multi-box patterns
    chapter = None
    verse = None
    i = 0
    
    while i < len(sorted_boxes):
        box = sorted_boxes[i]
        text = box['text'].strip()
        
        # Look for chapter marker (with or without appended number)
        ch_match = re.search(r'^CH\.?([IVXLCDM]+)?', text, re.IGNORECASE)
        if ch_match:
            print(f"DEBUG: Found chapter marker in '{text}' at position {i}")
            
            # Check if chapter number is appended to marker
            if ch_match.group(1):
                chapter = roman_to_decimal(ch_match.group(1))
                print(f"DEBUG: Chapter {chapter} found appended to marker")
            else:
                # Look in next few boxes for chapter number or chapter+verse combination
                for j in range(i + 1, min(i + 4, len(sorted_boxes))):
                    next_box = sorted_boxes[j]
                    next_text = next_box['text'].strip()
                    
                    # Check if it's a chapter+verse combination like "IV." (I + V.)
                    cv_match = re.match(r'^([IVXLCDM]+)V\.?$', next_text, re.IGNORECASE)
                    if cv_match:
                        chapter = roman_to_decimal(cv_match.group(1))
                        if chapter:
                            print(f"DEBUG: Chapter {chapter} found in combined box: '{next_text}' (interpreted as {cv_match.group(1)} + V.)")
                            # This box contains both chapter and verse marker
                            # Now we need to look for the verse numbers in the following boxes
                            i = j
                            # Set a flag to indicate we found the verse marker embedded
                            found_embedded_verse_marker = True
                            break
                    # Check if it's just a Roman numeral (chapter only)
                    elif re.match(r'^[IVXLCDM]+\.?$', next_text, re.IGNORECASE):
                        # Skip if it's clearly a verse marker (just "V.")
                        if re.match(r'^V\.?$', next_text, re.IGNORECASE):
                            print(f"DEBUG: Skipping '{next_text}' - likely verse marker, not chapter")
                            break
                        
                        chapter = roman_to_decimal(next_text.replace('.', ''))
                        if chapter:
                            i = j  # Move index to this position
                            print(f"DEBUG: Chapter {chapter} found in separate box: '{next_text}'")
                            break
                    # Stop if we hit a standalone verse marker
                    elif re.match(r'^V\.', next_text, re.IGNORECASE):
                        break
            
            if chapter:
                # Check if we found an embedded verse marker (like "IV." = I + V.)
                # In this case, i points to the box with the embedded marker
                # We need to look for verse numbers starting from the next box
                
                # Now look for verse marker and number
                verse_search_start = i + 1
                
                for k in range(verse_search_start, min(verse_search_start + 4, len(sorted_boxes))):
                    verse_box = sorted_boxes[k]
                    verse_text = verse_box['text'].strip()
                    
                    # Check for verse marker with appended number/range/list
                    v_match = re.search(r'^[IV]V?\.?(.+)', verse_text, re.IGNORECASE)
                    if v_match:
                        verse_part = v_match.group(1)
                        verse = parse_verse_text(verse_part)
                        if verse:
                            print(f"DEBUG: Verse {verse} found appended to marker: '{verse_text}'")
                            break
                    
                    # Check for standalone verse marker
                    elif re.match(r'^[IV]V?\.?$', verse_text, re.IGNORECASE):
                        print(f"DEBUG: Found verse marker '{verse_text}' at position {k}")
                        # Try to combine multiple boxes for verse list
                        combined_verse, next_index = combine_verse_list_boxes(sorted_boxes, k + 1)
                        if combined_verse:
                            verse = combined_verse
                            print(f"DEBUG: Combined verse list: {verse}")
                            break
                        else:
                            # Look for verse number/range/list in next boxes (fallback)
                            for l in range(k + 1, min(k + 3, len(sorted_boxes))):
                                num_box = sorted_boxes[l]
                                num_text = num_box['text'].strip()
                                print(f"DEBUG: Trying to parse verse from: '{num_text}'")
                                
                                verse = parse_verse_text(num_text)
                                if verse:
                                    print(f"DEBUG: Verse {verse} found in separate box: '{num_text}'")
                                    break
                                else:
                                    print(f"DEBUG: Could not parse verse from: '{num_text}'")
                        break
                    
                    # If no verse marker found, try to parse directly as verse numbers
                    # This handles the case where we already found the verse marker embedded (like in "IV.")
                    # and the next boxes contain the verse numbers directly (like "3,", "4.")
                    else:
                        print(f"DEBUG: No verse marker in '{verse_text}', trying to combine verse list from position {k}")
                        combined_verse, next_index = combine_verse_list_boxes(sorted_boxes, k)
                        if combined_verse:
                            verse = combined_verse
                            print(f"DEBUG: Combined verse list without explicit marker: {verse}")
                            break
                
                if chapter and verse:
                    return chapter, verse
        
        i += 1
    
    print(f"DEBUG: Multi-box search result: chapter={chapter}, verse={verse}")
    return chapter, verse


def extract_header_info(tsv_data, img_width, img_height):
    """Extract book name, chapter/verse, and page number from header area."""
    n_boxes = len(tsv_data['text'])
    
    # Collect all text boxes
    boxes = []
    for i in range(n_boxes):
        text = tsv_data['text'][i].strip()
        if text:
            boxes.append({
                'text': text,
                'x': tsv_data['left'][i],
                'y': tsv_data['top'][i],
                'width': tsv_data['width'][i],
                'height': tsv_data['height'][i]
            })
    
    if not boxes:
        return {'book_name': None, 'chapter': None, 'verse': None, 'page_number': None}
    
    # Sort by Y position
    boxes.sort(key=lambda b: b['y'])
    min_y = boxes[0]['y']
    
    print(f"DEBUG: Minimum Y: {min_y}")
    print(f"DEBUG: First 10 boxes:")
    for i, box in enumerate(boxes[:10]):
        print(f"  {i}: '{box['text']}' at x={box['x']}, y={box['y']}")
    
    # Get topmost boxes with larger tolerance
    y_tolerance = 50
    topmost_boxes = [b for b in boxes if abs(b['y'] - min_y) <= y_tolerance]
    
    print(f"\nDEBUG: Topmost boxes (y ~= {min_y} ± {y_tolerance}):")
    for box in topmost_boxes:
        print(f"  '{box['text']}' at x={box['x']}, y={box['y']}")
    
    if not topmost_boxes:
        return {'book_name': None, 'chapter': None, 'verse': None, 'page_number': None}
    
    # Sort by X position
    topmost_boxes.sort(key=lambda b: b['x'])
    
    # Categorize boxes by position (left, center, right thirds)
    left_boundary = img_width / 3
    right_boundary = 2 * img_width / 3
    
    left_boxes = [b for b in topmost_boxes if b['x'] < left_boundary]
    center_boxes = [b for b in topmost_boxes if left_boundary <= b['x'] <= right_boundary]
    right_boxes = [b for b in topmost_boxes if b['x'] > right_boundary]
    
    print(f"\nDEBUG: Spatial categorization (img_width={img_width}):")
    print(f"  Left boxes ({len(left_boxes)}): {[b['text'] for b in left_boxes]}")
    print(f"  Center boxes ({len(center_boxes)}): {[b['text'] for b in center_boxes]}")
    print(f"  Right boxes ({len(right_boxes)}): {[b['text'] for b in right_boxes]}")
    
    # Find book name from center boxes
    book_name = None
    if center_boxes:
        # Find the box closest to center
        center_x = img_width / 2
        center_box = min(center_boxes, key=lambda b: abs((b['x'] + b['width']/2) - center_x))
        book_name = center_box['text'].replace('.', '').strip()
        print(f"DEBUG: Book name found: '{book_name}'")
    
    # Find page number and determine its side
    page_number = None
    page_side = None
    
    for side, boxes_list in [('left', left_boxes), ('right', right_boxes)]:
        for i, box in enumerate(boxes_list):
            # More selective page number detection - avoid verse patterns
            text = box['text'].strip()
            
            # Skip if it looks like a verse (contains comma or ends with comma/period suggesting list)
            if ',' in text or re.match(r'^[0-9]+[,.]$', text):
                print(f"DEBUG: Skipping '{text}' - looks like verse list item")
                continue
            
            # Skip if it's too close to chapter/verse markers
            if any(re.search(r'CH\.|V\.', other_box['text'], re.IGNORECASE)
                   for other_box in boxes_list if abs(other_box['x'] - box['x']) < 200):
                print(f"DEBUG: Skipping '{text}' - too close to CH./V. markers")
                continue
            
            # Skip if this number is part of a sequence (e.g., "5" followed by "6." = verse list)
            # Check if there are other numbers nearby that suggest a list
            nearby_numbers = []
            for j, other_box in enumerate(boxes_list):
                if i != j and abs(other_box['x'] - box['x']) < 300:  # Within 300 pixels
                    if re.match(r'^[0-9]+[,.]?$', other_box['text'].strip()):
                        nearby_numbers.append(other_box['text'].strip())
            
            if nearby_numbers:
                print(f"DEBUG: Skipping '{text}' - nearby numbers suggest verse list: {nearby_numbers}")
                continue
            
            page_match = re.match(r'^\s*(\d+)\s*$', text)
            if page_match:
                page_number = int(page_match.group(1))
                page_side = side
                print(f"DEBUG: Page number {page_number} found on {side} side in: '{box['text']}'")
                break
        if page_number:
            break
    
    # Search for chapter/verse in the opposite area
    chapter = None
    verse = None
    
    if page_side == 'left':
        cv_boxes = right_boxes
        print(f"DEBUG: Page number on left, searching for chapter/verse on right")
    elif page_side == 'right':
        cv_boxes = left_boxes
        print(f"DEBUG: Page number on right, searching for chapter/verse on left")
    else:
        # Fallback: search all non-center boxes
        cv_boxes = left_boxes + right_boxes
        print(f"DEBUG: Page number not found, searching all non-center boxes for chapter/verse")
    
    if cv_boxes:
        chapter, verse = extract_chapter_verse_from_boxes(cv_boxes)
    
    print(f"\nDEBUG: Final result: book='{book_name}', ch={chapter}, v={verse}, page={page_number}\n")
    
    return {
        'book_name': book_name,
        'chapter': chapter,
        'verse': verse,
        'page_number': page_number
    }

def group_by_lines(tsv_data):
    """Group words by their line numbers from Tesseract."""
    lines = {}
    n_boxes = len(tsv_data['text'])
    
    for i in range(n_boxes):
        text = tsv_data['text'][i].strip()
        if text:
            line_num = tsv_data['line_num'][i]
            block_num = tsv_data['block_num'][i]
            par_num = tsv_data['par_num'][i]
            line_id = (block_num, par_num, line_num)
            
            word_data = {
                'text': text,
                'x': tsv_data['left'][i],
                'y': tsv_data['top'][i],
                'width': tsv_data['width'][i],
                'height': tsv_data['height'][i]
            }
            
            if line_id not in lines:
                lines[line_id] = []
            lines[line_id].append(word_data)
    
    line_list = []
    for line_id, words in lines.items():
        words.sort(key=lambda w: w['x'])
        avg_y = sum(w['y'] for w in words) / len(words)
        line_list.append({
            'words': words,
            'y': avg_y,
            'height': max(w['height'] for w in words)
        })
    
    line_list.sort(key=lambda l: l['y'])
    return line_list

def merge_lines_by_y_position(line_list, tolerance=0.5):
    """Merge lines that are at the same Y position."""
    if not line_list:
        return []
    
    merged_lines = []
    current_group = [line_list[0]]
    
    for i in range(1, len(line_list)):
        line = line_list[i]
        prev_line = current_group[0]
        y_diff = abs(line['y'] - prev_line['y'])
        avg_height = (line['height'] + prev_line['height']) / 2
        
        if y_diff < avg_height * tolerance:
            current_group.append(line)
        else:
            merged_lines.append(merge_line_group(current_group))
            current_group = [line]
    
    if current_group:
        merged_lines.append(merge_line_group(current_group))
    
    return merged_lines

def merge_line_group(line_group):
    """Merge multiple lines that are on the same visual line."""
    all_words = []
    for line in line_group:
        all_words.extend(line['words'])
    all_words.sort(key=lambda w: w['x'])
    return all_words

def calculate_page_center(lines):
    """Calculate the center divider of the page."""
    if not lines:
        return None
    
    left_edges = []
    right_edges = []
    
    for line in lines:
        if not line:
            continue
        for word in line:
            left_edges.append(word['x'])
            right_edges.append(word['x'] + word['width'])
    
    if not left_edges or not right_edges:
        return None
    
    avg_left = sum(left_edges) / len(left_edges)
    avg_right = sum(right_edges) / len(right_edges)
    center_x = (avg_left + avg_right) / 2
    
    return center_x

def split_line_by_center(line, center_x):
    """Split a line into left and right columns."""
    left_words = []
    right_words = []
    
    for word in line:
        word_center = word['x'] + word['width'] / 2
        if word_center < center_x:
            left_words.append(word)
        else:
            right_words.append(word)
    
    return left_words, right_words

def calculate_avg_char_width(lines):
    """Estimate average character width from word data."""
    total_chars = 0
    total_width = 0
    
    for line in lines:
        for word in line:
            char_count = len(word['text'])
            if char_count > 0:
                total_chars += char_count
                total_width += word['width']
    
    if total_chars > 0:
        return total_width / total_chars
    return 10

def reconstruct_line_with_spacing(line, avg_char_width):
    """Reconstruct a line with proper spacing."""
    if not line:
        return ""
    
    result = []
    prev_x_end = line[0]['x']
    
    for i, word in enumerate(line):
        if i > 0:
            gap = word['x'] - prev_x_end
            num_spaces = max(1, int(gap / avg_char_width))
            result.append(' ' * num_spaces)
        
        result.append(word['text'])
        prev_x_end = word['x'] + word['width']
    
    return ''.join(result)

def find_right_column_start(lines, center_x):
    """Find the consistent starting position for right column text."""
    right_starts = []
    
    for line in lines:
        if not line:
            continue
        for word in line:
            word_center = word['x'] + word['width'] / 2
            if word_center >= center_x:
                right_starts.append(word['x'])
                break
    
    if not right_starts:
        return None
    return sum(right_starts) / len(right_starts)

def calculate_right_col_position(lines, avg_char_width, center_x):
    """Calculate the right column character position."""
    max_left_length = 0
    
    for line in lines:
        if not line:
            continue
        left_words, _ = split_line_by_center(line, center_x)
        if left_words:
            left_text = reconstruct_line_with_spacing(left_words, avg_char_width)
            max_left_length = max(max_left_length, len(left_text))
    
    return max_left_length + 4

def lines_to_paragraphs(lines, avg_char_width, center_x, right_col_start, right_col_char_pos=80):
    """Convert lines to paragraphs with proper spacing and aligned columns."""
    if not lines:
        return []
    
    paragraphs = []
    current_para = []
    prev_line_bottom = 0
    
    for line in lines:
        if not line:
            continue
        
        left_words, right_words = split_line_by_center(line, center_x)
        left_text = reconstruct_line_with_spacing(left_words, avg_char_width) if left_words else ""
        right_text = reconstruct_line_with_spacing(right_words, avg_char_width) if right_words else ""
        
        if right_text:
            left_length = len(left_text)
            padding_needed = max(right_col_char_pos - left_length, 2)
            line_text = left_text + (' ' * padding_needed) + right_text
        else:
            line_text = left_text
        
        line_y = min(word['y'] for word in line)
        line_height = max(word['height'] for word in line)
        
        if prev_line_bottom > 0:
            gap = line_y - prev_line_bottom
            if gap > line_height * 1.5:
                if current_para:
                    paragraphs.append('\n'.join(current_para))
                    current_para = []
        
        current_para.append(line_text)
        prev_line_bottom = line_y + line_height
    
    if current_para:
        paragraphs.append('\n'.join(current_para))
    
    return paragraphs

def format_as_markdown(paragraphs):
    """Format paragraphs as markdown."""
    markdown = []
    for para in paragraphs:
        markdown.append("```")
        markdown.append(para)
        markdown.append("```")
        markdown.append("")
    return '\n'.join(markdown)

def process_image(image_path, output_path=None, lang='eng', right_col_char_pos=None):
    """Main function to process image and generate markdown."""
    print(f"Processing image: {image_path}")
    print(f"Language: {lang}")
    
    tsv_data, img_width, img_height = extract_text_with_layout(image_path, lang)
    
    if output_path:
        base_name = os.path.splitext(output_path)[0]
    else:
        base_name = os.path.splitext(image_path)[0]
    
    ocr_json_path = base_name + '_ocr.json'
    save_ocr_json(tsv_data, ocr_json_path)
    print(f"Raw OCR data saved to: {ocr_json_path}")
    
    header_info = extract_header_info(tsv_data, img_width, img_height)
    
    line_list = group_by_lines(tsv_data)
    merged_lines = merge_lines_by_y_position(line_list)
    avg_char_width = calculate_avg_char_width(merged_lines)
    center_x = calculate_page_center(merged_lines)
    
    if center_x:
        print(f"Page center calculated at X={center_x:.0f} (image width: {img_width})")
        right_col_start = find_right_column_start(merged_lines, center_x)
        if right_col_start:
            print(f"Right column starts at X={right_col_start:.0f}")
        
        if right_col_char_pos is None:
            right_col_char_pos = calculate_right_col_position(merged_lines, avg_char_width, center_x)
            print(f"Calculated right column character position: {right_col_char_pos}")
        else:
            print(f"Using specified right column character position: {right_col_char_pos}")
        
        paragraphs = lines_to_paragraphs(merged_lines, avg_char_width, center_x, right_col_start, right_col_char_pos)
    else:
        print("Could not calculate page center")
        paragraphs = []
        for line in merged_lines:
            if line:
                line_text = reconstruct_line_with_spacing(line, avg_char_width)
                paragraphs.append(line_text)
    
    markdown_output = format_as_markdown(paragraphs)
    markdown_path = base_name + '.md'
    with open(markdown_path, 'w', encoding='utf-8') as f:
        f.write(markdown_output)
    print(f"Markdown saved to: {markdown_path}")
    
    metadata = {
        'input_file': os.path.basename(image_path),
        'markdown_file': os.path.basename(markdown_path),
        'ocr_file': os.path.basename(ocr_json_path),
        'book_name': header_info['book_name'],
        'chapter': header_info['chapter'],
        'verse': header_info['verse'],
        'page_number': header_info['page_number']
    }
    
    print(f"\nExtracted metadata: {json.dumps(metadata, indent=2)}")
    
    json_path = base_name + '_metadata.json' if not output_path else output_path
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    print(f"Metadata saved to: {json_path}")
    
    return metadata


def load_previous_metadata(prev_metadata_path):
    """Load previous page metadata for validation."""
    try:
        with open(prev_metadata_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load previous metadata from {prev_metadata_path}: {e}")
        return None


def validate_and_correct_metadata(current_metadata, prev_metadata):
    """Validate current metadata against previous page and correct if needed."""
    if not prev_metadata:
        return current_metadata
    
    print(f"\nDEBUG: Validating against previous metadata:")
    print(f"  Previous: book={prev_metadata.get('book_name')}, ch={prev_metadata.get('chapter')}, v={prev_metadata.get('verse')}, page={prev_metadata.get('page_number')}")
    print(f"  Current:  book={current_metadata.get('book_name')}, ch={current_metadata.get('chapter')}, v={current_metadata.get('verse')}, page={current_metadata.get('page_number')}")
    
    corrected = current_metadata.copy()
    corrections_made = []
    
    # Validate and correct page number
    if prev_metadata.get('page_number') is not None:
        expected_page = prev_metadata['page_number'] + 1
        if current_metadata.get('page_number') != expected_page:
            corrections_made.append(f"page: {current_metadata.get('page_number')} → {expected_page}")
            corrected['page_number'] = expected_page
    
    # Validate and correct book name
    prev_book = prev_metadata.get('book_name')
    curr_book = current_metadata.get('book_name')
    if prev_book:
        if not curr_book:
            # If current book missing, use previous
            corrections_made.append(f"book: None → {prev_book}")
            corrected['book_name'] = prev_book
        elif curr_book != prev_book:
            # Book should only change if chapter restarts to 1
            if corrected.get('chapter') != 1:
                corrections_made.append(f"book: {curr_book} → {prev_book}")
                corrected['book_name'] = prev_book
    
    # Validate and correct chapter
    prev_chapter = prev_metadata.get('chapter')
    curr_chapter = current_metadata.get('chapter')
    if prev_chapter is not None and curr_chapter is not None:
        # Chapter should be same or +1
        if curr_chapter not in [prev_chapter, prev_chapter + 1]:
            # If current seems wrong, keep previous chapter
            corrections_made.append(f"chapter: {curr_chapter} → {prev_chapter}")
            corrected['chapter'] = prev_chapter
    elif prev_chapter is not None and curr_chapter is None:
        # If current chapter missing, use previous
        corrections_made.append(f"chapter: None → {prev_chapter}")
        corrected['chapter'] = prev_chapter
    
    # Validate and correct verse
    prev_verse = prev_metadata.get('verse')
    curr_verse = current_metadata.get('verse')
    
    if prev_verse and curr_verse:
        # Extract last verse number from previous page
        prev_verse_str = str(prev_verse)
        if '-' in prev_verse_str:
            # Range: get the end number
            last_prev_verse = int(prev_verse_str.split('-')[-1])
        elif ',' in prev_verse_str:
            # List: get the last number
            last_prev_verse = int(prev_verse_str.split(',')[-1])
        else:
            # Single verse
            last_prev_verse = int(prev_verse_str) if str(prev_verse_str).isdigit() else None
        
        # Extract first verse number from current page
        curr_verse_str = str(curr_verse)
        if '-' in curr_verse_str:
            first_curr_verse = int(curr_verse_str.split('-')[0])
        elif ',' in curr_verse_str:
            first_curr_verse = int(curr_verse_str.split(',')[0])
        else:
            first_curr_verse = int(curr_verse_str) if str(curr_verse_str).isdigit() else None
        
        if last_prev_verse and first_curr_verse:
            # Current verse should be within reasonable range of previous
            # Allow: same verse (continuation), next verse, or skip max 2-3 verses
            verse_diff = first_curr_verse - last_prev_verse
            
            if verse_diff > 3 or verse_diff < -1:
                # Verse jump seems too large, likely OCR error
                # Correct to expected verse(s)
                expected_verse = last_prev_verse + 1
                
                # Try to infer the correct verse range/list
                if ',' in curr_verse_str:
                    # It's a list, adjust each number
                    num_verses = len(curr_verse_str.split(','))
                    corrected_verses = [str(expected_verse + i) for i in range(num_verses)]
                    corrected_verse = ','.join(corrected_verses)
                elif '-' in curr_verse_str:
                    # It's a range, adjust both numbers
                    range_size = int(curr_verse_str.split('-')[1]) - int(curr_verse_str.split('-')[0])
                    corrected_verse = f"{expected_verse}-{expected_verse + range_size}"
                else:
                    # Single verse
                    corrected_verse = str(expected_verse)
                
                corrections_made.append(f"verse: {curr_verse} → {corrected_verse} (large jump from {last_prev_verse}, expected {expected_verse})")
                corrected['verse'] = corrected_verse
                corrected['verse_warning'] = f"OCR detected {curr_verse} but auto-corrected to {corrected_verse} based on previous verse {last_prev_verse}"
    
    if corrections_made:
        print(f"\nDEBUG: Corrections applied based on previous metadata:")
        for correction in corrections_made:
            print(f"  - {correction}")
    else:
        print(f"DEBUG: No corrections needed - metadata validated successfully")
    
    return corrected


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py <image_path> [output_path] [--lang LANG] [--right-col POS] [--prev-metadata PATH]")
        print("\nOutput files created:")
        print("  <base>_metadata.json - Metadata with book/chapter/verse/page info")
        print("  <base>.md            - Formatted markdown with columns")
        print("  <base>_ocr.json      - Complete OCR data with bounding boxes")
        print("\nOptional arguments:")
        print("  --lang LANG          - Tesseract language (default: eng)")
        print("  --right-col POS      - Right column character position")
        print("  --prev-metadata PATH - Previous page metadata JSON for validation")
        sys.exit(1)
    
    image_path = sys.argv[1]
    output_path = None
    lang = 'eng'
    right_col_char_pos = None
    prev_metadata_path = None
    
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == '--lang' and i + 1 < len(sys.argv):
            lang = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--right-col' and i + 1 < len(sys.argv):
            right_col_char_pos = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == '--prev-metadata' and i + 1 < len(sys.argv):
            prev_metadata_path = sys.argv[i + 1]
            i += 2
        else:
            output_path = sys.argv[i]
            i += 1
    
    # Load previous metadata if provided
    prev_metadata = None
    if prev_metadata_path:
        prev_metadata = load_previous_metadata(prev_metadata_path)
    
    # Process image
    metadata = process_image(image_path, output_path, lang, right_col_char_pos)
    
    # Validate and correct if previous metadata available
    if prev_metadata:
        metadata = validate_and_correct_metadata(metadata, prev_metadata)
        
        # Save corrected metadata
        if output_path:
            base_name = os.path.splitext(output_path)[0]
        else:
            base_name = os.path.splitext(image_path)[0]
        
        json_path = base_name + '_metadata.json'
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        print(f"\nCorrected metadata saved to: {json_path}")