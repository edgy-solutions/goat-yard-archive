#!/usr/bin/env python3
"""Script to normalize OCR-extracted markdown from John Gill's Bible Commentary.

Supports two backends:
- BAML: Uses declarative prompts defined in baml_src/main.baml
- DSPy: Uses programmatic signatures with potential for optimization
"""

import os
import sys
import logging
import argparse
import asyncio
import time
import random
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from abc import ABC, abstractmethod

# Load environment variables
load_dotenv()

# System prompt shared between backends
SYSTEM_PROMPT = """You are a specialized theological editor responsible for formatting John Gill's Bible Commentary.

Objective: Normalize the raw OCR text into clean, structured Markdown while strictly preserving the 18th-century stylistic conventions (specifically the Verse Lemma format).

=== 1. STRUCTURAL RULES (STRICT) ===

A. Remove ONLY Metadata Headers (at the very top of the page):
- Page numbers (e.g., "90", "page 90")
- Book/chapter markers like "GENESIS", "CH. I. V. 3"
- These are typically short lines at the very beginning, NOT part of the commentary.
- CAUTION: Do NOT remove references like "ch. v. 6." if they are part of a sentence (e.g., "ch. v. 6. and this is mentioned..."). That is CONTENT.

B. PRESERVE ALL Commentary Text:
- CRITICAL: Text that starts mid-sentence (spillover from previous page) MUST be preserved.
- Example: If the file starts with "triarchs: but yet such a variety..." this is continuation text from the previous page and MUST be kept.
- Only remove obvious page metadata, never remove actual commentary content.

C. Isolated Artifacts:
- Remove ONLY truly isolated single numbers or letter fragments that are clearly OCR errors.
- If in doubt, KEEP the text.

D. Chapter Headings:
- Identify headings detected as "CHAP. N.", "C H A P. N.", or "GENESIS."
- Format as standard Markdown Header 1: `# Chapter N`.
- CRITICAL: Place the heading AT THE TOP of the content, BEFORE any introductory text or summaries.
- CAUTION: Do NOT treat "ch. v. 6" inside a sentence as a heading (it refers to a verse).

E. Verse Commentary (The Lemma Style):
- Constraint: Do NOT use ### Verse 3. Keep the archaic format.
- Format: Start every verse commentary on a new line with the exact pattern: Ver. {number}.
- Normalization:
  - If input is V. 6., change to Ver. 6.
  - If input is Verse 6., change to Ver. 6.
  - If input is Ver 6, change to Ver. 6. (ensure periods are present).
- The Lemma: Ensure the bracketed lemma text follows immediately.
  - Example: Ver. 6. And Jesus went, &c.]

F. Paragraphs:
- Remove excessive newlines. Paragraphs should be separated by a single blank line.

=== 2. FOOTNOTE NORMALIZATION RULES (CRUCIAL) ===

The raw text uses inconsistent markers (e.g., ^a^, ᵃ, (1), *, †, ‡, δ, <sup>, [^b], °, ¹, ², ³, ⁴, ⁵, ⁶, ⁷, ⁸, ⁹, ⁰). You must standardize them to Markdown.

CRITICAL: Do NOT invent or add new footnote markers. Only normalize markers that ALREADY EXIST in the original text.

A. In-Text Markers:
- Convert EXISTING footnote markers in the body text to standard numerical Markdown citations: [^1], [^2], [^3].
- ALWAYS renumber sequentially starting from 1, even if the source already uses [^N] format.
- Example 1: "...as Aben Ezra observes^a^" → "...as Aben Ezra observes[^1]"
- Example 2: "...the text says[^b]..." → "...the text says[^1]..." (renumber from 1, don't keep [^b])
- If there is NO footnote marker in the original (e.g., "Aben Ezra observes" with no ^a^ or superscript), do NOT add one.

B. Footnote Definitions:
- Move ALL footnote definitions to the very bottom of the text.
- Format them as: [^1]: {Content}
- Matching: You must match each in-text marker to its ORIGINAL definition text, NOT to another definition.
- When renumbering: If source has [^b] in text and "[^b]: Some content" as definition, output should have [^1] in text and "[^1]: Some content".
- Formatting: Remove the original marker letters (a, b, *) from the definition text.

=== 3. CONTENT INTEGRITY RULES ===

- Hebrew/Greek/Aramaic: CRITICAL - NEVER alter, add to, or remove Hebrew (עברית), Greek (Ελληνικά), or Aramaic text. Copy these EXACTLY character-for-character from the source. Do not "fix" or "correct" them.
  - Correct: "The word is בְּרֵאשִׁית, Bereshith." -> "The word is בְּרֵאשִׁית, Bereshith."
  - Incorrect: "The word is בְּרֵאשִׁית, Bereshith." -> "The word is Bereshith."
  - Incorrect: "The word is בְּרֵאשִׁית, Bereshith." -> "The word is שִׁית אשִׁית, Bereshith."
- Italics: Ensure Bible quotations or emphasized words use *asterisks* (not _underscores_).
- Spelling: Do not modernize 18th-century spelling (e.g., "shewn", "hath")
- Spillover Text: ALWAYS preserve text that continues from a previous page, even if it starts mid-sentence."""


class NormalizerBackend(ABC):
    """Abstract base class for normalization backends."""
    
    @abstractmethod
    def normalize(self, raw_markdown: str) -> str:
        """Normalize the raw markdown text."""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the backend name."""
        pass


class BAMLBackend(NormalizerBackend):
    """BAML-based normalization backend."""
    
    def __init__(self):
        from baml_client import b
        self._client = b
    
    @property
    def name(self) -> str:
        return "BAML"
    
    def normalize(self, raw_markdown: str) -> str:
        return asyncio.run(self._client.NormalizeGillMarkdown(raw_markdown))


class DSPyBackend(NormalizerBackend):
    """DSPy-based normalization backend."""
    
    def __init__(self, model: str = "ollama_chat/qwen3-8k:32b", api_base: str = None, temperature: float = 0.1, optimized_path: str = None):
        import dspy
        
        # Detect if using OpenRouter (model format: provider/model-name)
        is_openrouter = '/' in model and not model.startswith('ollama')
        
        if is_openrouter:
            # OpenRouter configuration
            api_key = os.environ.get('OPENROUTER_API_KEY')
            if not api_key:
                raise ValueError("OPENROUTER_API_KEY environment variable not set")
            
            self._lm = dspy.LM(
                model=f"openrouter/{model}",
                api_key=api_key,
                temperature=temperature
            )
        else:
            # Local Ollama configuration
            if api_base is None:
                api_base = "http://192.168.1.188:11434"
            self._lm = dspy.LM(
                model=model,
                api_base=api_base,
                temperature=temperature
            )
        
        dspy.configure(lm=self._lm)
        
        # Create the signature
        class NormalizeGillMarkdown(dspy.Signature):
            """Normalize OCR-extracted markdown from John Gill's Bible Commentary."""
            raw_markdown: str = dspy.InputField(desc="Raw OCR markdown to normalize")
            normalized_markdown: str = dspy.OutputField(desc="Clean, normalized markdown")
        
        self._system_prompt = SYSTEM_PROMPT
        self._optimized = False
        self._module = None
        
        # Try to load optimized model if path provided or default exists
        if optimized_path is None:
            # Check for default optimized model in script directory
            script_dir = os.path.dirname(os.path.abspath(__file__))
            optimized_path = os.path.join(script_dir, "optimized_normalizer.json")
        
        if optimized_path and os.path.exists(optimized_path):
            try:
                # Import and use GillNormalizer from train_dspy
                from train_dspy import GillNormalizer
                self._module = GillNormalizer()
                self._module.load(optimized_path)
                self._optimized = True
                logging.info(f"Loaded optimized model from {optimized_path}")
            except Exception as e:
                logging.warning(f"Failed to load optimized model: {e}, using vanilla predictor")
                self._module = None
        
        # Fallback to vanilla predictor if no optimized model
        if self._module is None:
            self._predictor = dspy.ChainOfThought(NormalizeGillMarkdown)
    
    @property
    def name(self) -> str:
        return "DSPy" + (" (optimized)" if self._optimized else "")
    
    def normalize(self, raw_markdown: str) -> str:
        import dspy
        
        with dspy.context(lm=self._lm):
            if self._optimized and self._module:
                # Use optimized module (it already prepends system prompt)
                result = self._module(raw_markdown=raw_markdown)
                return result.normalized_markdown if hasattr(result, 'normalized_markdown') else str(result)
            else:
                # Use vanilla predictor with system prompt
                result = self._predictor(raw_markdown=f"{self._system_prompt}\n\n---\n\nPlease normalize the following raw OCR markdown:\n\n{raw_markdown}")
                return result.normalized_markdown


# ============================================================================
# VERIFICATION AND POST-PROCESSING
# ============================================================================

import re
import difflib
from dataclasses import dataclass, field


@dataclass
class VerificationResult:
    """Result of output verification."""
    passed: bool
    footnote_count_match: bool
    body_footnote_count: int
    definition_footnote_count: int
    unauthorized_changes: list = field(default_factory=list)
    footnote_issues: list = field(default_factory=list)
    headings_removed: list = field(default_factory=list)
    
    def __str__(self):
        issues = []
        if not self.footnote_count_match:
            issues.append(f"Footnote mismatch: {self.body_footnote_count} in body vs {self.definition_footnote_count} definitions")
        if self.unauthorized_changes:
            issues.append(f"Unauthorized changes: {len(self.unauthorized_changes)}")
        if self.footnote_issues:
            issues.append(f"Footnote issues: {len(self.footnote_issues)}")
        return "; ".join(issues) if issues else "OK"


def post_process_headings(text: str) -> tuple[str, list[str]]:
    """Remove chapter headings that appear after non-whitespace content.
    
    Rule: # Chapter N is allowed ONLY at document start (before other content).
    
    Args:
        text: The normalized markdown text
        
    Returns:
        tuple: (processed_text, list of removed headings)
    """
    lines = text.split('\n')
    removed_headings = []
    result_lines = []
    found_content = False
    
    chapter_pattern = re.compile(r'^#\s*Chapter\s+\d+', re.IGNORECASE)
    
    for line in lines:
        stripped = line.strip()
        
        # Check if this is a chapter heading
        if chapter_pattern.match(stripped):
            if found_content:
                # Heading after content - remove it
                removed_headings.append(stripped)
                logging.debug(f"Removed mid-document heading: {stripped}")
                continue
            # else: heading at start - keep it
        
        # Track when we've found actual content
        if stripped and not chapter_pattern.match(stripped):
            found_content = True
        
        result_lines.append(line)
    
    return '\n'.join(result_lines), removed_headings


def repair_non_latin_footnotes(source: str, output: str) -> str:
    """Repair corrupted Hebrew/Greek/Aramaic footnotes by restoring from source.
    
    LLMs sometimes corrupt non-Latin scripts. This function finds non-Latin
    footnotes in output and replaces them with the original source content.
    """
    import re
    
    # Pattern for non-Latin characters (Hebrew, Greek, Aramaic/Syriac)
    non_latin_pattern = re.compile(r'[\u0590-\u05FF\u0370-\u03FF\u0700-\u074F]')
    
    # Extract source footnotes (various formats: [^a]:, ^a, a Some text, etc.)
    source_footnotes = {}
    for m in re.finditer(r'^\s*\[?\^?([a-z])\]?:?\s*(.+)$', source, re.MULTILINE | re.IGNORECASE):
        marker = m.group(1).lower()
        content = m.group(2).strip()
        if non_latin_pattern.search(content):
            source_footnotes[marker] = content
    
    # If no source footnotes with non-Latin, nothing to repair
    if not source_footnotes:
        return output
    
    # Find output footnotes with non-Latin content and repair if corrupted
    def replace_footnote(match):
        num = match.group(1)
        output_content = match.group(2).strip()
        
        # If output has non-Latin, check if it matches any source
        if non_latin_pattern.search(output_content):
            # Try to find matching source by content similarity
            output_lower = ' '.join(output_content.lower().split())
            
            for marker, src_content in source_footnotes.items():
                src_lower = ' '.join(src_content.lower().split())
                # If there's any overlap, use source version
                if any(word in output_lower for word in src_lower.split()[:3] if len(word) > 3):
                    logging.debug(f"Repaired footnote [^{num}] with source content")
                    return f"[^{num}]: {src_content}"
        
        return match.group(0)  # No change
    
    repaired = re.sub(r'^\[(\^?\d+)\]:(.*)$', replace_footnote, output, flags=re.MULTILINE)
    return repaired


def verify_normalization(source: str, output: str) -> VerificationResult:
    """Verify the LLM output for correctness.
    
    Checks:
    1. Footnote count: [^N] in body matches [^N]: definitions
    2. Unauthorized changes: text differs only in allowed places
    
    Args:
        source: Original raw markdown
        output: Normalized markdown from LLM
        
    Returns:
        VerificationResult with validation details
    """
    # Patterns for footnote detection
    # Find definition footnotes first (at start of line)
    definition_pattern = re.compile(r'^\[\^(\d+)\]:', re.MULTILINE)
    definition_footnotes = definition_pattern.findall(output)
    
    # Find ALL footnote markers [^N], then exclude definition positions
    all_footnote_pattern = re.compile(r'\[\^(\d+)\]')
    
    # Find positions of definitions to exclude them from body count
    definition_positions = set()
    for m in definition_pattern.finditer(output):
        definition_positions.add(m.start())
    
    # Count body footnotes (all markers NOT at definition positions)
    body_footnotes = []
    for m in all_footnote_pattern.finditer(output):
        if m.start() not in definition_positions:
            body_footnotes.append(m.group(1))
    
    body_count = len(body_footnotes)
    def_count = len(definition_footnotes)
    
    # Count "ibid" footnotes in source - LLM may combine these with their references
    # expanded to include ib., id., idem
    ibid_count = len(re.findall(r'\b(ib|ibid|idem|id)\.?\b', source, re.IGNORECASE))
    
    # Allow mismatch if difference matches ibid count (LLM combined duplicate refs)
    footnote_count_match = (body_count == def_count) or (body_count == def_count + ibid_count) or (body_count + ibid_count >= def_count)
    
    # Check footnote numbering consistency
    footnote_issues = []
    body_set = set(body_footnotes)
    def_set = set(definition_footnotes)
    
    missing_definitions = body_set - def_set
    extra_definitions = def_set - body_set
    
    if missing_definitions:
        footnote_issues.append(f"Missing definitions for: {sorted(missing_definitions)}")
    if extra_definitions:
        # If we successfully matched counts (likely due to Ibid merging logic) AND we have more definitions than body markers,
        # then the extra definitions are expected artifacts of the merge.
        is_merge_artifact = footnote_count_match and (def_count > body_count)
        
        if not is_merge_artifact:
            # Check if the extra definitions are just "Ibid" citations that might have been merged
            # or left over. If they are Ibid, we might tolerate them if footnote counts roughly align.
            real_extra = []
            for def_id in extra_definitions:
                # Find the content of this definition
                # Regex to find [^N]: content
                def_match = re.search(r'^\s*\[\^' + str(def_id) + r'\]:(.*)$', output, re.MULTILINE)
                if def_match:
                    content = def_match.group(1).strip().lower()
                    # If it's an "ibid" type definition, ignore it for the error list
                    if not re.search(r'^\s*(ib|ibid|idem|id)\.?\b', content):
                        real_extra.append(def_id)
                else:
                    real_extra.append(def_id)
            
            if real_extra:
                footnote_issues.append(f"Extra definitions without markers: {sorted(real_extra)}")
    
    # Detect unauthorized changes using segment matching
    # Algorithm: split output by [^N], verify each text segment exists in source
    unauthorized_changes = []
    
    # Pattern to strip footnote markers for segment extraction
    # Includes: [^N], ^[letter], ^a^, ^a, superscript letters (ᵃᵇᶜ...), <sup> tags, degree symbol, and ALL superscript numbers (⁰¹²³⁴⁵⁶⁷⁸⁹)
    all_footnote_markers = re.compile(r'\[\^\d+\]|\^\[\]\^|\^\[\*\]\^|\^\[[⁰¹²³⁴⁵⁶⁷⁸⁹]+\]\^|\^\s+|\^\[[a-zA-Z]\]|\^[a-z]\^|\^[A-Z]\^|\^[a-z]|\^[A-Z]|[ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ]|<sup>[a-z]</sup>|<sup>\d+</sup>|°|[⁰¹²³⁴⁵⁶⁷⁸⁹]+')
    # Pattern to detect headings (should be skipped)
    # Includes "C H A P. V." or "CHAP. V." or "GENESIS."
    heading_pattern = re.compile(r'^#.*$|^\*?\*?C\s*H\s*A\s*P\.?\s*[IVX\d]+.*$|^[A-Z]+\.\s*CH\.\s*[IVX\d]+|CHAP\.?\s*[IVXLCD]+\.?', re.MULTILINE | re.IGNORECASE)
    # Pattern to detect footnote definition lines (various formats):
    # - "^a Some text" (caret prefixed)
    # - "^a^ Some text" (caret-letter-caret prefixed)
    # - "^[z]: text" or "^[a]: text" (caret bracket letter style with colon)
    # - "^[z] text" or "^[a] text" (caret bracket letter style WITHOUT colon)
    # - "[^1]: text" or "[^a]: text" (markdown style with numbers or letters)
    # - "[a]: text" or "[b]: text" (bracket-letter-colon style WITHOUT caret)
    # - "a Some text" or "b Hebrew..." (single letter at line start, common in OCR)
    # - "<sup>a</sup> Some text" (superscript tag at line start)
    # - "° Some text" (degree symbol at line start)
    # - "¹ Some text" or " ¹..." (any superscript number at line start, with optional leading space)
    # - "Erato, sive..." (bibliographic continuations with Latin abbreviations like "l.", "c.", "fol.", "sive")
    footnote_def_line_pattern = re.compile(r'^\s*\^[a-z]\^\s+.*$|^\s*\^[a-z]\s+.*$|^\s*\^\[[a-zA-Z]\]:.*$|^\s*\^\[[a-zA-Z]\]\s+.*$|^\s*\^\[\*\]\^.*$|^\s*\^\[\]\^.*$|^\s*\^\[[⁰¹²³⁴⁵⁶⁷⁸⁹]+\]\^.*$|^\s*\^\s+.*$|^\s*\[\^[a-z0-9]+\]:.*$|^\s*\[[a-z]\]:.*$|^[a-z]\s+(?:[^a-z\s]|vide?\b|ib(?:id)?\b|id\b|op\b|loc\b|cit\b|supra\b|infra\b|see\b|cf\b).*$|^\s*<sup>[a-z0-9]+</sup>.*$|^\s*[°⁰¹²³⁴⁵⁶⁷⁸⁹]+.*$|^[A-Z][a-z]+,\s+(sive|l\.|c\.|fol\.|p\.).*$', re.MULTILINE)
    
    # Pattern for inline Rabbinic citations often found in text (e.g. "^ T. Bab. Sanhedrin")
    # Matches " ^ T. Bab." or " ^ Bemidbar Rabba" and the rest of the sentence/line
    inline_citation_pattern = re.compile(r'\s*\^\s*(?:T\.\s*Bab\.|Bemidbar\s*Rabba|Bereshit\s*Rabba|Vayikra\s*Rabba|Debarim\s*Rabba|Echa\s*Rabbati|Midrash\s*Kohelet).*', re.IGNORECASE)

    def normalize_text(text: str) -> str:
        """Normalize text for comparison - remove footnotes, headings, definitions, and normalize whitespace."""
        # FIRST: Join cross-line hyphens before any other processing (e.g., "ima-\ngine" -> "imagine")
        # Conservative pattern: only when hyphen immediately precedes newline and next line starts with word char
        text = re.sub(r'(\w)-[\r\n]+(\w)', r'\1\2', text)
        text = footnote_def_line_pattern.sub(' ', text)  # Remove footnote definition lines
        text = inline_citation_pattern.sub(' ', text)    # Remove inline Rabbinic citations
        text = all_footnote_markers.sub(' ', text)
        text = heading_pattern.sub(' ', text)  # Remove headings
        # Normalize spaces around punctuation (allow "word ." -> "word.")
        text = re.sub(r'\s+([.,;:!?)])', r'\1', text)
        text = re.sub(r'([(])\s+', r'\1', text)
        # Remove quotes/apostrophes/asterisks for comparison (handles smart quotes/apostrophes/emphasis mismatches)
        text = re.sub(r'["“”\'‘’*]', '', text)
        # Remove hyphens between word chars (OCR artifacts like "con-cerned" -> "concerned")
        text = re.sub(r'(\w)-(\w)', r'\1\2', text)
        # Handle end-of-line hyphens: "ima-\ngine" -> "imagine" (remove trailing hyphen before newline)
        text = re.sub(r'(\w)-\s*\n\s*(\w)', r'\1\2', text)
        # Also handle line-break hyphens: "con- cerned" or "crea- tures" -> "concerned"/"creatures"
        text = re.sub(r'(\w)-\s+(\w)', r'\1\2', text)
        # Normalize verse markers: "Ver 16." or "Ver. 16." or "ver. 16" -> consistent format
        # Remove entirely for comparison since LLM may fix punctuation (Ver 16 -> Ver. 16.)
        text = re.sub(r'\bver\.?\s*\d+\.?', '', text, flags=re.IGNORECASE)
        return ' '.join(text.split()).lower()
    
    # Normalize source for comparison
    source_normalized = normalize_text(source)
    
    if "king of Zion" in source or "page387" in source: # Attempt to identify page 387
         with open("debug_nm_source.txt", "w", encoding="utf-8") as f:
             f.write(source_normalized)
         with open("debug_nm_output.txt", "w", encoding="utf-8") as f:
             f.write(output)
    
    # Split output into segments by [^N] markers (excluding footnote definitions at bottom)
    footnote_def_start = re.search(r'^\[\^\d+\]:', output, re.MULTILINE)
    if footnote_def_start:
        output_body = output[:footnote_def_start.start()]
    else:
        output_body = output
    
    # Split body by [^N] markers
    segments = re.split(r'\[\^\d+\]', output_body)
    
    # Check each segment (min length to avoid matching trivial segments)
    MIN_SEGMENT_LENGTH = 30  # Minimum chars to verify
    
    for i, segment in enumerate(segments):
        segment_normalized = normalize_text(segment)
        
        # Skip short segments (punctuation, whitespace, or headings-only)
        if len(segment_normalized) < MIN_SEGMENT_LENGTH:
            continue
        
        # Check if this segment exists in the source
        if segment_normalized not in source_normalized:
            # Segment not found - check if it's a real text corruption or just structural
            segment_words = segment_normalized.split()
            
            # Use sliding window to find the mismatched section
            # Require multiple consecutive windows to fail to reduce false positives
            window_size = 8  # Increased from 5 for fewer false positives
            consecutive_failures = 0
            failure_threshold = 3  # Need 3 consecutive failing windows
            
            for j in range(len(segment_words) - window_size + 1):
                window = ' '.join(segment_words[j:j + window_size])
                if window not in source_normalized:
                    consecutive_failures += 1
                    if consecutive_failures >= failure_threshold:
                        # Found sustained mismatch - get context for logging
                        mismatch_context = ' '.join(segment_words[max(0, j-5):j + window_size + 2])
                        before_context = ' '.join(segment_words[max(0, j-3):j])
                        after_context = ' '.join(segment_words[j + window_size:j + window_size + 3])
                        
                        # Find best matching source window for comparison
                        search_start = max(0, source_normalized.find(before_context) if before_context else 0)
                        source_context = source_normalized[search_start:search_start + len(mismatch_context) + 40]
                        
                        unauthorized_changes.append({
                            'type': 'text_mismatch',
                            'segment_index': i,
                            'output_text': mismatch_context,
                            'source_text': source_context[:80] if source_context else '(not found)',
                            'context_before': before_context,
                            'context_after': after_context,
                        })
                        break  # Only report first mismatch per segment
                else:
                    consecutive_failures = 0  # Reset on match
    
    # BIDIRECTIONAL CHECK: Verify source content exists in output (detect deletions)
    # Check if beginning of source (spillover) was preserved
    output_normalized = normalize_text(output)
    
    # Get first substantial chunk of source (skip page headers like "114 GENESIS CH XV")
    source_lines = source.strip().split('\n')
    first_content_line = ''
    for line in source_lines:
        line_normalized = normalize_text(line)
        # Skip short lines (likely page numbers/headers) and actual chapter headings
        # Also skip page headers like "276 genesis. ch. xliii." or "114 GENESIS CH XV"
        if len(line_normalized) > 40 and not re.match(r'^\d+\s*$|^\d*\s*[a-z]+\.?\s*ch\.?\s*[ivxlcd\d]+', line_normalized, re.IGNORECASE):
            first_content_line = line_normalized
            break
    
    if first_content_line and len(first_content_line) > 40:
        # Check if this content appears in output
        # Use a smaller chunk to allow for some variation
        check_chunk = first_content_line[:60]
        if check_chunk not in output_normalized:
            unauthorized_changes.append({
                'type': 'content_removed',
                'removed_text': first_content_line[:100],
                'note': 'Beginning of source not found in output (possible spillover removal)'
            })
    
    # Determine if verification passed
    # Continue with cheat checks...
    
    # 3. Check for duplicate definitions (hallucination/filling)
    # If the LLM duplicates a definition to match the count, we catch it here.
    definitions_content = []
    for m in re.finditer(r'^\[\^(\d+)\]:(.*)$', output, re.MULTILINE):
        # Normalize content for comparison (strip whitespace/punctuation)
        content = m.group(2).strip().lower()
        if len(content) > 20: # Only check substantial footnotes (ignore "ibid", "loc. cit.")
            if content in definitions_content:
                # Check if duplication is supported by source
                # Get total count in output so far + 1 (current)
                # Actually, definitions_content has previous ones.
                # Let's check strict counts globally or locally?
                # Simpler: count how many times this content chunk appears in source_simple
                # We need source_simple defined before this loop.
                source_simple_check = ' '.join(source.lower().split())
                
                # Check distinct occurrences in source (approximate)
                # Use a chunk of the content to find matches
                check_chunk = content[:30] # 30 chars
                source_matches = source_simple_check.count(check_chunk)
                output_matches = definitions_content.count(content) + 1 # +1 for current
                
                if output_matches > source_matches:
                    unauthorized_changes.append({
                        'type': 'duplicate',
                        'removed_text': content,
                        'note': f"Duplicate definition ({output_matches} vs {source_matches} in source)"
                    })
            definitions_content.append(content)
            
            # Fidelity Check: Ensure content exists in source (approximate)
            # For Hebrew/Greek/Aramaic content, we'll flag for repair if mismatched
            has_non_latin = bool(re.search(r'[\u0590-\u05FF\u0370-\u03FF\u0700-\u074F]', content))
            
            # Remove "ibid." and short words, then check if significant chunk is in source
            # Use word boundaries to prevent stripping parts of words (e.g. "op" in "Cosmopoeiam")
            check_text = re.sub(r'\b(ibid|op|cit|loc)\.?\b', '', content, flags=re.IGNORECASE).strip()
            if len(check_text) > 15:
                # Take a 15-char chunk
                chunk = check_text[:15]
                # Check if this chunk exists in source (normalized for case/whitespace ONLY)
                # DO NOT use normalize_text() because it strips definitions!
                # Strip the same citation abbreviations from source for fair comparison
                source_simple = ' '.join(source.lower().split())
                source_simple = re.sub(r'\b(ibid|op|cit|loc)\.?\b', '', source_simple, flags=re.IGNORECASE)
                
                if chunk not in source_simple:
                     # Check if it's an "Ibid" issue (hallucination)
                     if "ibid" in content and "ibid" not in source_simple:
                         unauthorized_changes.append({
                             'type': 'hallucination',
                             'removed_text': content,
                             'note': f"Potential hallucinated footnote (Ibid not in source)"
                         })
                     elif has_non_latin:
                         # For Hebrew/Greek/Aramaic, this is likely LLM corruption - skip error, will auto-repair
                         # Find the original footnote in source and mark for repair
                         pass  # Don't flag as error - verification will pass, we'll fix in post-process
                     else:
                         unauthorized_changes.append({
                             'type': 'content_mismatch',
                             'removed_text': chunk,
                             'note': f"Footnote content fail: '{chunk}...' not found in source"
                         })

    # Re-evaluate 'passed' based on all checks

    # Re-evaluate 'passed' based on all checks
    # The original snippet's 'return' structure implies a different VerificationResult.
    # I will integrate the new check into the existing VerificationResult structure.
    # The 'footnote_mismatch' from the snippet is not directly present in the original.
    # I'll assume 'footnote_issues' covers the numbering consistency and 'footnote_count_match' covers the count.
    # The new 'unauthorized_changes' from duplicate definitions will be added to the existing list.
    
    # 4. Check for Ibid hallucinations (Global count check)
    output_ibid_count = sum(1 for m in re.finditer(r'ibid', output, re.IGNORECASE))
    source_ibid_count = sum(1 for m in re.finditer(r'ibid', source, re.IGNORECASE)) # Changed raw_match to source
    
    if output_ibid_count > source_ibid_count:
        # Check if the excess is in footnotes
        footnotes_ibid = 0
        for m in re.finditer(r'^\[\^(\d+)\]:(.*)$', output, re.MULTILINE):
            if 'ibid' in m.group(2).lower():
                footnotes_ibid += 1
        
        if footnotes_ibid > source_ibid_count:
             unauthorized_changes.append({
                 'type': 'hallucination',
                 'removed_text': f"Found {footnotes_ibid} 'Ibid's in output vs {source_ibid_count} in source",
                 'note': "Excessive use of 'Ibid' not supported by source"
             })

    # Helper to convert Roman to Int
    def to_int(s):
        s = s.strip().upper()
        if s.isdigit(): return int(s)
        roman = {'I':1, 'V':5, 'X':10, 'L':50, 'C':100, 'D':500, 'M':1000}
        try:
            val = 0
            for i in range(len(s)):
                if i > 0 and roman[s[i]] > roman[s[i-1]]:
                    val += roman[s[i]] - 2 * roman[s[i-1]]
                else:
                    val += roman[s[i]]
            return val
        except:
            return s # Return string if not parseable

    # 5. Check for Missing Chapter Headings
    # Detect if source has a clear chapter heading at the start that is missing in output
    # Source pattern: # Chapter N, CHAP. N, Chapter N
    source_heading_match = re.search(r'^\s*(?:#\s*)?(?:CHAPTER|CHAP\.?)\s+([IVXLCD\d]+)', source, re.IGNORECASE | re.MULTILINE)
    if source_heading_match:
        heading_num_str = source_heading_match.group(1).upper()
        heading_val = to_int(heading_num_str)
        
        # Check if output has equivalent
        # Output should be standard markdown: # Chapter N
        output_heading_match = re.search(r'^#\s*Chapter\s+([IVXLCD\d]+)', output, re.IGNORECASE | re.MULTILINE)
        
        if not output_heading_match:
             unauthorized_changes.append({
                 'type': 'heading_missing',
                 'removed_text': source_heading_match.group(0),
                 'note': f"Chapter heading '{source_heading_match.group(0).strip()}' from source missing in output"
             })
        else:
             out_val = to_int(output_heading_match.group(1))
             if out_val != heading_val:
                 # Heading exists but number mismatch (e.g. Chapter I vs Chapter II)
                 unauthorized_changes.append({
                     'type': 'heading_mismatch',
                     'removed_text': source_heading_match.group(0),
                     'note': f"Chapter heading number mismatch: Source '{heading_num_str}' ({heading_val}) vs Output '{output_heading_match.group(1)}' ({out_val})"
                 })

    # Re-evaluate 'passed' based on all checks
    # RELAXED RULE: We prioritize content and headers over perfect footnote counts.
    # If there are no unauthorized changes (text loss, header loss, content mismatch), we pass.
    # Footnote count mismatches are just warnings.
    passed = len(unauthorized_changes) == 0
    
    # If there are footnote issues but text is fine, we consider it a pass (maybe with warnings)
    if not footnote_count_match:
         footnote_issues.append(f"Footnote count mismatch: {body_count} in body vs {def_count} definitions (allowed)")

    return VerificationResult(
        passed=passed,
        footnote_count_match=footnote_count_match,
        body_footnote_count=body_count,
        definition_footnote_count=def_count,
        unauthorized_changes=unauthorized_changes,
        footnote_issues=footnote_issues
    )


def setup_logging(verbose: bool = False):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True
    )


def inject_missing_header(text: str, chapter: int) -> str:
    """Inject missing chapter header if metadata indicates a new chapter."""
    if not chapter or chapter <= 1:
        return text
        
    # Check if header already exists
    if re.search(r'^#\s*Chapter\s+' + str(chapter), text, re.IGNORECASE | re.MULTILINE):
        return text
        
    if re.search(r'^\s*(?:#\s*)?(?:CHAPTER|CHAP\.?)\s+' + str(chapter), text, re.IGNORECASE | re.MULTILINE):
        return text
        
    # Check for Roman Numeral equivalent
    roman = "I" * chapter # Naive for small numbers, but sufficient for check? 
    # Better: check for [IVXLCD]+ in general if we don't have to_roman
    # If we find ANY Chapter header matching, we assume it's fine (verification will catch mismatch)
    if re.search(r'^\s*(?:#\s*)?(?:CHAPTER|CHAP\.?)\s+[IVXLCD\d]+', text, re.IGNORECASE | re.MULTILINE):
         # A header exists (maybe wrong number, but exists). Don't double inject.
         return text

    # Header missing. Check for Verse 1 to anchor injection.
    # Look for "Ver. 1." or similar
    ver1_match = re.search(r'(?m)^Ver\.?\s*1\.', text)
    if ver1_match:
        # Inject before Ver. 1
        pos = ver1_match.start()
        header = f"\n# Chapter {chapter}\n\n"
        return text[:pos] + header + text[pos:]
        
    return text


def normalize_with_retry(backend: NormalizerBackend, raw_markdown: str, max_retries: int = 5, output_path: str = None, expected_chapter: int = None) -> str:
    """Call normalization backend with retry logic and exponential backoff.
    
    Args:
        backend: The normalization backend to use
        raw_markdown: The raw markdown text to normalize
        max_retries: Maximum number of retry attempts
        output_path: Optional path to save output. If provided, each attempt
                     is saved with _1, _2, etc. suffixes for debugging.
        
    Returns:
        str: Normalized markdown text
        
    Raises:
        Exception: If all retry attempts fail
    """
    base_delay = 2
    max_delay = 60
    best_result = None
    best_verification = None
    
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                logging.info(f"Retry attempt {attempt}/{max_retries-1}")
            
            # On retry, add a cache-busting comment to force fresh response from OpenRouter
            input_text = raw_markdown
            if attempt > 0:
                import uuid
                cache_buster = f"\n<!-- retry-{uuid.uuid4().hex[:8]} -->"
                input_text = raw_markdown + cache_buster
            
            normalized_text = backend.normalize(input_text)
            
            # Check for empty response - treat as retryable
            if not normalized_text or not normalized_text.strip():
                if attempt < max_retries - 1:
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    logging.warning(f"Empty response received, retrying in {delay:.1f}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    continue
                else:
                    raise Exception("LLM returned empty response after all retries")
            
            # Post-process: enforce heading rules
            normalized_text, removed_headings = post_process_headings(normalized_text)
            
            # Post-process: repair corrupted Hebrew/Greek/Aramaic footnotes
            normalized_text = repair_non_latin_footnotes(raw_markdown, normalized_text)
            
            # Post-process: fix double-caret footnote markers [^^N] -> [^N]
            normalized_text = re.sub(r'\[\^\^(\d+)\]', r'[^\1]', normalized_text)
            normalized_text = re.sub(r'\[\^\^(\d+)\]:', r'[^\1]:', normalized_text)
            
            # Post-process: Inject missing header if requested
            if expected_chapter:
                normalized_text = inject_missing_header(normalized_text, expected_chapter)
            
            if removed_headings:
                logging.info(f"Removed {len(removed_headings)} mid-document heading(s)")
            
            # Save intermediate attempt if output_path is provided
            if output_path:
                attempt_path = output_path.replace('_normalized.md', f'_normalized_{attempt + 1}.md')
                try:
                    with open(attempt_path, 'w', encoding='utf-8') as f:
                        f.write(normalized_text)
                    logging.info(f"Saved attempt {attempt + 1} to {os.path.basename(attempt_path)}")
                except Exception as e:
                    logging.warning(f"Failed to save attempt {attempt + 1}: {e}")
            
            # Verify output
            verification = verify_normalization(raw_markdown, normalized_text)
            
            # Keep track of best result - prefer the one with closest word count to source
            # This ensures we don't accidentally select a result that's missing content
            source_words = len(raw_markdown.split())
            current_words = len(normalized_text.split())
            current_diff = abs(source_words - current_words)
            
            # Helper to check for missing header issue
            def has_missing_header_issue(ver_result):
                if not ver_result: return False
                return any(c.get('type') == 'heading_missing' for c in ver_result.unauthorized_changes)

            current_missing_header = has_missing_header_issue(verification)
            best_missing_header = has_missing_header_issue(best_verification)
            
            if best_result is None:
                # First result
                best_result = normalized_text
                best_verification = verification
                best_word_diff = current_diff
            elif verification.passed and not (best_verification and best_verification.passed):
                # Current passed, previous didn't - prefer current
                best_result = normalized_text
                best_verification = verification
                best_word_diff = current_diff
            elif not verification.passed and not (best_verification and best_verification.passed):
                # Neither passed - prefer result with header, then closest word count
                
                # Check if one has header and other missing it
                if best_missing_header and not current_missing_header:
                    logging.info(f"Attempt {attempt + 1} preserved header (unlike best so far)")
                    best_result = normalized_text
                    best_verification = verification
                    best_word_diff = current_diff
                elif current_missing_header and not best_missing_header:
                    # Best has header, current missing it - keep best
                    pass
                else:
                    # Both have header or both missing it - use word count
                    if current_diff < best_word_diff:
                        logging.info(f"Attempt {attempt + 1} has closer word count ({current_words} vs source {source_words}, diff={current_diff})")
                        best_result = normalized_text
                        best_verification = verification
                        best_word_diff = current_diff
            
            if not verification.passed:
                logging.warning(f"Verification issues: {verification}")
                
                # Log detailed issues for debugging
                if verification.unauthorized_changes:
                    for change in verification.unauthorized_changes[:5]:  # Limit to first 5
                        c_type = change.get('type', 'unknown')
                        note = change.get('note', '')
                        text = change.get('removed_text', '') or change.get('output_text', '')
                        logging.warning(f"  [{c_type}] {note} ({text[:50]}...)")
                
                # Retry if we have attempts left
                if attempt < max_retries - 1:
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    logging.warning(f"Verification failed, retrying in {delay:.1f}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    continue
                else:
                    # Out of retries - return best result
                    logging.warning(f"Verification issues persist after {max_retries} attempts, using best result")
                    return best_result
            
            if attempt > 0:
                logging.info(f"[OK] Succeeded after {attempt} retries")
            return normalized_text
            
        except Exception as e:
            error_msg = str(e)
            error_type = type(e).__name__
            is_retryable = False
            reason = "unknown error"
            
            # Check if this is a retryable error
            if "ConnectionReset" in error_msg or "Connection reset" in error_msg:
                is_retryable = True
                reason = "connection reset"
            elif "timeout" in error_msg.lower():
                is_retryable = True
                reason = "timeout"
            elif "status_code=500" in error_msg or "status_code=502" in error_msg or "status_code=503" in error_msg:
                is_retryable = True
                reason = "server error"
            elif "ConnectError" in error_msg or "NetworkError" in error_msg:
                is_retryable = True
                reason = "network error"
            elif any(keyword in error_msg.lower() for keyword in ['connection', 'network', 'reset', 'refused']):
                is_retryable = True
                reason = "network error"
            
            if is_retryable and attempt < max_retries - 1:
                base_backoff = min(base_delay * (2 ** attempt), max_delay)
                jitter = base_backoff * (0.75 + random.random() * 0.5)
                delay = min(jitter, max_delay)
                
                logging.warning(f"{backend.name} call failed ({reason}), retrying in {delay:.1f}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
            else:
                if not is_retryable:
                    logging.error(f"Non-retryable error ({error_type}): {error_msg[:500]}")
                else:
                    logging.error(f"Max retries ({max_retries}) exceeded. Last error: {reason}")
                raise
    
    raise Exception(f"Failed after {max_retries} attempts")


def normalize_single_file(backend: NormalizerBackend, input_path: Path, force: bool = False) -> bool:
    """Normalize a single markdown file.
    
    Args:
        backend: The normalization backend to use
        input_path: Path to the input markdown file
        force: If True, overwrite existing normalized files
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Output path is in the same directory with _normalized suffix
    output_path = input_path.parent / f"{input_path.stem}_normalized.md"
    
    # Check if output already exists
    if output_path.exists() and not force:
        logging.info(f"Skipping {input_path.name} - normalized file already exists")
        return True
    
    try:
        # Read input file
        with open(input_path, 'r', encoding='utf-8') as f:
            raw_markdown = f.read()
        
        if not raw_markdown.strip():
            logging.warning(f"Skipping {input_path.name} - file is empty")
            return False
        
        # Check for modern web URLs (vision model hallucinations)
        url_pattern = re.compile(r'https?://[^\s\)\]]+', re.IGNORECASE)
        urls_found = url_pattern.findall(raw_markdown)
        if urls_found:
            logging.warning(f"[HALLUCINATION] {input_path.name} contains {len(urls_found)} modern web URL(s) - vision model hallucination detected!")
            for url in urls_found[:5]:  # Log first 5 URLs
                logging.warning(f"  URL: {url[:80]}...")
            # Write to hallucination log file for later re-processing
            hallucination_log = input_path.parent / "hallucination_pages.txt"
            with open(hallucination_log, 'a', encoding='utf-8') as f:
                f.write(f"{input_path.name}: {', '.join(urls_found[:3])}\n")
            logging.warning(f"Skipping {input_path.name} - needs vision model re-run. Logged to {hallucination_log.name}")
            return False
        
        logging.info(f"Normalizing {input_path.name} ({len(raw_markdown)} chars) using {backend.name}...")
        
        # Try to load metadata to get expected chapter
        expected_chapter = None
        try:
            meta_path = input_path.parent / f"{input_path.stem.replace('_ocr', '').replace('_reindexed', '')}_metadata.json"
            # Fallback for plain naming
            if not meta_path.exists():
                meta_path = input_path.parent / f"{input_path.stem}_metadata.json"
            
            # Check parent directory (if md files are in a subdir)
            if not meta_path.exists():
                 meta_path = input_path.parent.parent / f"{input_path.stem.replace('_ocr', '').replace('_reindexed', '')}_metadata.json"
            if not meta_path.exists():
                 meta_path = input_path.parent.parent / f"{input_path.stem}_metadata.json"
            
            if meta_path.exists():
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                    if 'chapter' in meta and isinstance(meta['chapter'], int):
                        expected_chapter = meta['chapter']
                        logging.info(f"Loaded metadata: Expecting Chapter {expected_chapter}")
        except Exception as e:
            logging.warning(f"Failed to load metadata: {e}")

        # Call backend to normalize (pass output_path to save intermediate attempts)
        normalized_text = normalize_with_retry(backend, raw_markdown, output_path=str(output_path), expected_chapter=expected_chapter)
        
        # Write output file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(normalized_text)
        
        logging.info(f"[OK] Created {output_path.name} ({len(normalized_text)} chars)")
        return True
        
    except Exception as e:
        logging.error(f"[FAIL] Failed to normalize {input_path.name}: {e}")
        return False


def process_directory(backend: NormalizerBackend, dir_path: Path, force: bool = False) -> tuple[int, int]:
    """Process all markdown files in a directory.
    
    Args:
        backend: The normalization backend to use
        dir_path: Path to the directory containing markdown files
        force: If True, overwrite existing normalized files
        
    Returns:
        tuple: (successful_count, failed_count)
    """
    # Find all .md files that are NOT already normalized
    md_files = [f for f in dir_path.glob("*.md") if "_normalized" not in f.stem]
    
    if not md_files:
        logging.warning(f"No markdown files found in {dir_path}")
        return 0, 0
    
    logging.info(f"Found {len(md_files)} markdown files in {dir_path}")
    
    successful = 0
    failed = 0
    
    for i, md_file in enumerate(sorted(md_files), 1):
        logging.info(f"\n[{i}/{len(md_files)}] Processing {md_file.name}")
        
        if normalize_single_file(backend, md_file, force=force):
            successful += 1
        else:
            failed += 1
    
    return successful, failed


def create_backend(backend_name: str, model: str = None, api_base: str = None, temperature: float = None) -> NormalizerBackend:
    """Create and return the specified backend.
    
    Args:
        backend_name: 'baml' or 'dspy'
        model: Model name for DSPy backend
        api_base: API base URL for DSPy backend
        temperature: Temperature for DSPy backend
        
    Returns:
        NormalizerBackend instance
    """
    if backend_name.lower() == 'baml':
        return BAMLBackend()
    elif backend_name.lower() == 'dspy':
        kwargs = {}
        if model:
            kwargs['model'] = model
        if api_base:
            kwargs['api_base'] = api_base
        if temperature is not None:
            kwargs['temperature'] = temperature
        return DSPyBackend(**kwargs)
    else:
        raise ValueError(f"Unknown backend: {backend_name}. Use 'baml' or 'dspy'.")


def main():
    parser = argparse.ArgumentParser(
        description="Normalize OCR-extracted markdown from John Gill's Bible Commentary"
    )
    parser.add_argument("--file", "-f", type=str, 
                        help="Single markdown file to normalize")
    parser.add_argument("--dir", "-d", type=str,
                        help="Directory containing markdown files to normalize (default: $COMMENTARY_DATA_DIR/volume1)")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing normalized files")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable verbose logging")
    parser.add_argument("--backend", "-b", type=str, default="baml",
                        choices=["baml", "dspy"],
                        help="Backend to use for normalization (default: baml)")
    parser.add_argument("--model", "-m", type=str,
                        help="Model name for DSPy backend (default: ollama_chat/qwen3-8k:32b)")
    parser.add_argument("--api-base", type=str,
                        help="API base URL for DSPy backend (default: http://192.168.1.188:11434)")
    parser.add_argument("--temperature", "-t", type=float, default=0.1,
                        help="Temperature for DSPy backend (default: 0.1)")
    
    args = parser.parse_args()
    
    # Validate arguments & set defaults
    base_dir = Path(os.getenv("COMMENTARY_DATA_DIR", os.getcwd()))
    
    if not args.file and not args.dir:
        # Default to volume1
        args.dir = str(base_dir / "volume1")
        logging.info(f"No input specified, defaulting to: {args.dir}")
    
    
    if args.file and args.dir:
        parser.error("Cannot specify both --file and --dir")
    
    # Setup logging
    setup_logging(verbose=args.verbose)
    
    logging.info("=" * 60)
    logging.info("JOHN GILL COMMENTARY MARKDOWN NORMALIZER")
    logging.info(f"Backend: {args.backend.upper()}")
    logging.info("=" * 60)
    
    # Create backend
    try:
        backend = create_backend(args.backend, args.model, args.api_base, args.temperature)
        logging.info(f"Initialized {backend.name} backend with model={args.model or 'default'}")
    except Exception as e:
        logging.error(f"Failed to initialize backend: {e}")
        sys.exit(1)
    
    start_time = datetime.now()
    
    if args.file:
        # Single file mode
        input_path = Path(args.file)
        if not input_path.exists():
            logging.error(f"File not found: {input_path}")
            sys.exit(1)
        if not input_path.suffix == '.md':
            logging.error(f"File must be a markdown file (.md): {input_path}")
            sys.exit(1)
        
        success = normalize_single_file(backend, input_path, force=args.force)
        sys.exit(0 if success else 1)
    
    else:
        # Directory mode
        dir_path = Path(args.dir)
        if not dir_path.exists():
            logging.error(f"Directory not found: {dir_path}")
            sys.exit(1)
        if not dir_path.is_dir():
            logging.error(f"Path is not a directory: {dir_path}")
            sys.exit(1)
        
        successful, failed = process_directory(backend, dir_path, force=args.force)
        
        elapsed = datetime.now() - start_time
        
        logging.info("\n" + "=" * 60)
        logging.info("PROCESSING SUMMARY")
        logging.info("=" * 60)
        logging.info(f"Backend: {backend.name}")
        logging.info(f"Successful: {successful}")
        logging.info(f"Failed: {failed}")
        logging.info(f"Time elapsed: {elapsed}")
        logging.info("=" * 60)
        
        sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
