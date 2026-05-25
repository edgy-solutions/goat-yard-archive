
import dspy
import re
from typing import List, Dict

# Define Signature
# Load KJV Data (Global Cache)
import json
import os
# Import shared KJV Index from bible_api (which handles MinIO fallback)
try:
    from .bible_api import BIBLE_MAP as KJV_DATA
except ImportError:
    # Fallback/Safeguard during testing or if circle import issues
    KJV_DATA = {}
    print("Warning: Could not import BIBLE_MAP from bible_api")


# ---------------------------------------------------------------------------
# Verbatim quote verification (see ADR-0006).
#
# Verbatim mode (ADR-0006 companion to the GillSignature contract) promises
# the user that anything inside double-quotes in the answer appears verbatim
# in Gill's source. These helpers check that promise post-generation. The
# model has a tendency — even when instructed otherwise — to silently
# modernize spelling, drop archaic markers, or stitch fragments together;
# without verification, those slips produce fake-Gill in disguise.
# ---------------------------------------------------------------------------

# Matches `"quoted text" [SENTENCE_ID]` — Sentence ID immediately after the
# closing quote mark per the GillSignature output contract. The Sentence ID
# pattern (BOOK_CH_VS_Snn) allows alphanumerics and underscores in the BOOK.
QUOTE_WITH_CITE_RE = re.compile(
    r'["“”]([^"“”]+)["“”]\s*\[([A-Z0-9_]+_S\d+)\]'
)

# Tokens we strip during normalization (whitespace differences, markdown
# italics, footnote refs, curly quotes, leading/trailing punctuation).
_ITALICS_RE = re.compile(r"\*([^*]+)\*")
_FOOTNOTE_REF_RE = re.compile(r"\[\^[A-Za-z0-9_]+\]")
_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_for_quote_match(text: str) -> str:
    """Make the quoted text and the source text comparable.

    Normalizations applied:
    - Lowercase (Gill's capitalization is meaningful for display but not for
      verbatim-detection).
    - Strip `*italics*` and `_italics_` markdown markers.
    - Strip `[^1]` footnote refs (model often drops them when quoting).
    - Normalize curly quotes -> straight quotes.
    - Collapse all whitespace runs to a single space.
    - Strip leading/trailing whitespace and most punctuation (mid-sentence
      quotes typically don't carry their terminal punctuation).
    """
    if not text:
        return ""
    s = text
    s = _ITALICS_RE.sub(r"\1", s)
    s = s.replace("_", " ")
    s = _FOOTNOTE_REF_RE.sub("", s)
    s = s.replace("“", '"').replace("”", '"')
    s = s.replace("‘", "'").replace("’", "'")
    s = s.lower()
    s = _WHITESPACE_RE.sub(" ", s).strip()
    s = s.strip("\"'.,;:!? ")
    return s


def _build_chunks_by_sid(context_chunks: List[dict]) -> Dict[str, str]:
    """Build {sentence_id_in_brackets: source_text} from the retrieved chunks.

    The "source text" for each Sentence ID is the FULL CHUNK content the SID
    belongs to — concatenation of all sentence_data texts plus the chunk's KJV
    scripture (if available). This is intentionally broader than just that
    one sentence's text because:

    - The model legitimately stitches quotes across consecutive sentences of
      the same chunk (sentence-level granularity is finer than typical
      readable-quote granularity).
    - The model legitimately quotes the KJV scripture that Gill himself
      cites in the same chunk.

    Strict per-sentence verification produced too many false positives; per-
    chunk verification keeps the architectural promise (quoted text appears
    in Gill's verbatim source for the cited verse) while avoiding the
    cross-sentence-boundary false positives.
    """
    out: Dict[str, str] = {}
    for chunk in context_chunks:
        # Build the chunk's full searchable text once.
        parts = []
        # Scripture (Gill quotes the verse he's commenting on at the top).
        verse_ref = chunk.get("verse_ref", "")
        try:
            scripture = KJV_DATA.get(verse_ref) if verse_ref else None
            if scripture:
                parts.append(scripture)
        except Exception:
            pass
        # All sentence-granularity texts in the chunk.
        sentence_ids: List[str] = []
        for sent in (chunk.get("sentence_data") or []):
            sid = sent.get("sentence_id")
            text = sent.get("text") or ""
            if sid:
                sentence_ids.append(f"[{sid}]")
            if text:
                parts.append(text)
        # Fallback to the chunk's combined `content` if sentence_data is missing.
        if not sentence_ids and chunk.get("content"):
            parts.append(chunk["content"])
        combined = " ".join(parts)
        for sid_bracketed in sentence_ids:
            out[sid_bracketed] = combined
    return out


def _verify_quotes(answer: str, chunks_by_sid: Dict[str, str]) -> List[dict]:
    """Return a list of failed-quote dicts. Empty list = all quotes verified.

    Each failure dict has: quote, sentence_id, reason. Reasons:
    - 'cited_sid_not_in_context': the Sentence ID after the quote isn't in any
      retrieved chunk (the existing citation validator already catches this,
      but harmless to repeat here for defense-in-depth).
    - 'quote_not_verbatim': the normalized quoted text isn't a substring of
      the normalized source. Strong signal the model paraphrased while
      putting quote marks around the paraphrase.

    Handles model conventions:
    - Ellipsis (`...` or `…`) inside a quote: split and verify each part
      independently against the source. The model uses ellipsis to elide
      middle phrasing while attributing the rest to Gill.
    - Bracketed insertions like `[work]` or parenthetical clarifications:
      try a fallback match with the bracketed/parenthesized content stripped.
    """
    failures: List[dict] = []
    for match in QUOTE_WITH_CITE_RE.finditer(answer or ""):
        quote_raw = match.group(1)
        sid = f"[{match.group(2)}]"
        source = chunks_by_sid.get(sid)
        if source is None:
            failures.append({
                "quote": quote_raw[:120],
                "sentence_id": sid,
                "reason": "cited_sid_not_in_context",
            })
            continue
        ns = _normalize_for_quote_match(source)
        if _quote_in_source(quote_raw, ns):
            continue
        failures.append({
            "quote": quote_raw[:120],
            "sentence_id": sid,
            "reason": "quote_not_verbatim",
        })
    return failures


_ELLIPSIS_RE = re.compile(r"\.{3,}|…")
_BRACKETED_RE = re.compile(r"\[[^\]]*\]")
_PARENTHESIZED_RE = re.compile(r"\([^)]*\)")


def _quote_in_source(quote_raw: str, normalized_source: str) -> bool:
    """Check if `quote_raw` is verbatim in `normalized_source` under several
    matching strategies: direct, ellipsis-split, and bracket-stripped.
    """
    def _check(q: str) -> bool:
        nq = _normalize_for_quote_match(q)
        return bool(nq) and nq in normalized_source

    # Strategy 1: direct match (handles the simple, clean case).
    if _check(quote_raw):
        return True

    # Strategy 2: ellipsis-split. The model uses "...text continues..." to
    # elide; require every segment to appear, in order, in the source.
    parts = [p for p in _ELLIPSIS_RE.split(quote_raw) if p.strip()]
    if len(parts) > 1:
        cursor = 0
        all_in_order = True
        for part in parts:
            nq = _normalize_for_quote_match(part)
            if not nq:
                continue
            idx = normalized_source.find(nq, cursor)
            if idx < 0:
                all_in_order = False
                break
            cursor = idx + len(nq)
        if all_in_order:
            return True

    # Strategy 3: strip bracketed/parenthesized insertions (e.g. "[work]",
    # "(Christ and His righteousness)") and try again. Model uses these to
    # clarify referents but they aren't in Gill's text.
    stripped = _PARENTHESIZED_RE.sub("", _BRACKETED_RE.sub("", quote_raw)).strip()
    if stripped and stripped != quote_raw and _check(stripped):
        return True

    return False

class GillSignature(dspy.Signature):
    """You are a present-day research assistant helping a user explore Dr. John Gill's
    "An Exposition of the Old and New Testaments" (1746-1763). You are NOT Dr. Gill.
    You do NOT speak in his voice, his style, or as his contemporary. You speak in plain
    modern English as a neutral guide. The user must always be able to tell which words
    are Gill's and which are yours: yours are plain modern framing; his are verbatim
    quotations in quotation marks with a Sentence ID.

    YOUR JOB
    Surface Gill's actual words in response to the user's question. The retrieved context
    contains direct excerpts from his commentary, each tagged with a Sentence ID like
    [JOHN_1_42_S03]. You must:

    1. Identify which excerpts address the SUBJECT of the user's question (not necessarily
       the exact wording — see PARTIAL MATCHES below).
    2. Quote them VERBATIM inside quotation marks. Do not paraphrase, modernize, summarize,
       or smooth Gill's 18th-century English. Preserve his spelling, capitalization,
       italics markers, and sentence structure exactly as they appear in the context.
    3. Use minimal connective framing in your own plain modern voice — only enough to
       orient the reader (e.g. "On this passage, Gill writes:" or "Gill makes a related
       point at..."). Keep framing brief; let Gill's quotes carry the answer.
    4. Place the Sentence ID immediately after the closing quotation mark of each quote,
       e.g. "...the Logos, or word..." [JOHN_1_42_S03].
    5. Do not append a bibliography or citation list at the end — citations belong inline
       with their quotes.

    PARTIAL MATCHES
    The user's modern phrasing routinely differs from Gill's 18th-century vocabulary. The
    exact term, name, or verse they ask about may not appear literally in the retrieved
    context — yet the SUBJECT may be discussed at length under different wording (a
    synonym, a related doctrine, an alternate name, a parallel passage). When that is so,
    surface the relevant quotes and let your framing point out the connection explicitly
    (e.g. "Gill does not use the modern term 'X' in the retrieved passages, but he
    discusses the same subject as 'Y':"). Do not refuse merely because the exact term is
    absent.

    WHEN TO REFUSE
    Refuse ONLY when the retrieved context is empty or addresses an entirely unrelated
    subject (e.g. the user asks about a doctrine and retrieval returned passages about an
    unrelated person, place, or topic with no doctrinal connection). In that case — and
    only then — reply exactly: "I regret that the provided extracts from the Doctor's
    writings do not appear to address this specific inquiry. Could it be that you are
    looking for something not in the library ({available_books})?" and provide an empty
    citation list.

    YOU MUST NOT
    - Speak in Gill's voice or pretend to be him or his contemporary.
    - Use archaic English in your framing ("Dr. Gill observes...", "The learned writer
      posits...", "verily", "doth", etc.). Plain modern English only for your own words.
    - Paraphrase Gill into modern language even briefly — if you reference what he says,
      quote him directly.
    - Answer from outside knowledge. Only Gill's retrieved words are valid source material.
    - Smooth over Gill's theological precision (he is a specific 18th-century Calvinist;
      preserve the distinctions he draws by quoting his exact wording rather than
      summarizing).
    """

    context = dspy.InputField(desc="Excerpts from Gill's commentary, tagged with Sentence IDs and [Vol, Page] citations.")
    question = dspy.InputField(desc="The user's question.")
    available_books = dspy.InputField(desc="String listing the books currently available in the library.")

    reasoning = dspy.OutputField(
        desc="Scan the context for fragments that address the SUBJECT of the question (not merely fragments that contain the user's exact words). Identify the specific Sentence IDs you intend to quote verbatim. Note any cases where Gill's wording differs significantly from the user's modern phrasing — those are worth flagging in the framing. Only if zero related fragments exist anywhere in the context, state that."
    )
    answer = dspy.OutputField(
        desc="A response in plain modern English that consists primarily of direct VERBATIM quotations from Gill (inside quotation marks, with the Sentence ID placed immediately after each closing quote mark). Minimal connective framing in your own voice — only enough to orient the reader. Never paraphrase Gill; always quote him directly when conveying his words."
    )
    citations = dspy.OutputField(
        desc="A list of Sentence IDs quoted in the answer, exactly matching the text, e.g. ['[GENESIS_46_06_S01]', '[MATTHEW_04_09_S03]']"
    )

class GroundedGillBot(dspy.Module):
    def __init__(self):
        super().__init__()
        self.generate_answer = dspy.ChainOfThought(GillSignature)
        
    def forward(self, question: str, context_chunks: List[dict], available_books: str = "Genesis, Matthew"):
        # 1. Format Context
        # We need to explicitly include the [Vol, Page] metadata in the text so the model can see it.
        formatted_context = ""
        valid_citations = set()
        
        for chunk in context_chunks:
            citation_tag = chunk.get("citation", "Unknown") # e.g. [Vol 1, p. 287]
            verse_ref = chunk.get("verse_ref", "")
            
            # Inject Scripture if available
            scripture_text = KJV_DATA.get(verse_ref)
            if scripture_text:
                formatted_context += f"SOURCE: {verse_ref}\n"
                formatted_context += f"[SCRIPTURE (KJV)]: \"{scripture_text}\"\n\n"
                formatted_context += f"[GILL'S COMMENTARY ({citation_tag})]:\n"
            else:
                formatted_context += f"SOURCE: {verse_ref} ({citation_tag})\n"
            
            # Sentence Granularity
            sentence_data = chunk.get("sentence_data", [])
            
            if sentence_data and isinstance(sentence_data, list):
                # Format: [S01] Text...
                for sent in sentence_data:
                    # Parse sentence ID to get suffix (e.g. GEN_46_06_S01 -> [S01])
                    s_id = sent.get("sentence_id", "")
                    # Use FULL ID to ensure global uniqueness across multiple verses
                    text = sent.get("text", "")
                    formatted_context += f"[{s_id}] {text}\n"
                    valid_citations.add(f"[{s_id}]")
            else:
                 # Fallback to blob
                 text = chunk.get("content", "")
                 if "Footnotes:" in text:
                     # Separate footnotes for clarity
                     main_text, footnotes = text.split("Footnotes:", 1)
                     formatted_context += f"{main_text.strip()}\n"
                     formatted_context += f"FOOTNOTES: {footnotes.strip()}\n"
                 else:
                     formatted_context += f"{text}\n"
            
            formatted_context += "\n"
            
        # 2. Generate
        print(f"DEBUG: Valid Citations in Context: {valid_citations}")
        pred = self.generate_answer(context=formatted_context, question=question, available_books=available_books)
        
        # 3. Assertions (The Critic)
        # Check 1: Format
        # We expect citations to be a list of strings
        # dspy.Suggest/Assert works on the prediction object directly usually
        # But here we do manual checks + dspy.Assert
        
        # We wrap in a helper to use dspy.Assert
        # Note: In dspy 2.5+, assertions are typically part of the pipeline validation.
        # Here we implement it as runtime logic.
        
        # Parse citations if it's a string (sometimes LLMs output string repr of list)
        # Parse citations if it's a string (sometimes LLMs output string repr of list)
        citations = pred.citations
        print(f"DEBUG: Raw Prediction Citations: {citations} (Type: {type(citations)})")
        
        final_citations = []
        import re
        
        # Helper to extract IDs
        def extract_ids(text):
            # Matches [ID] OR just ID (if it follows the pattern)
            # We look for patterns like GEN_1_1_S01, with or without brackets
            # The regex: (?:\[)?([a-zA-Z0-9_]+_S\d+)(?:\])?
            matches = re.findall(r"(?:\[)?([a-zA-Z0-9_]+_S\d+)(?:\])?", text)
            # Re-add brackets for consistency if they're missing, as the rest of the system expects them
            return [f"[{m}]" for m in matches]

        if isinstance(citations, str):
             final_citations = extract_ids(citations)
        elif isinstance(citations, list):
            for item in citations:
                item_str = str(item)
                # Try to extract valid IDs from the item
                found = extract_ids(item_str)
                if found:
                    final_citations.extend(found)
                else:
                    # Fallback: validation might fail later, but keep the raw item to show in error
                    # if it looks remotely like a citation
                    if "[" in item_str and "]" in item_str:
                         final_citations.append(item_str.strip())
        
        # Deduplicate
        citations_list = list(set(final_citations))
        print(f"DEBUG: Parsed Citations: {citations_list}")
        
        # ---------------------------------------------------------
        # CRITICAL FIX: The "No-Free-Lunch" Check
        # ---------------------------------------------------------
        # If citations are empty, we MUST verify the answer is a "Refusal".
        # If the answer is detailed (> 100 chars) but has no citations, it's a hallucination.
        
        if not citations_list:
            # Define what a "Refusal" looks like based on your System Prompt
            is_refusal = (
                "does not appear" in pred.answer.lower() or 
                "not address" in pred.answer.lower() or
                "silent on this" in pred.answer.lower() or
                "regret that" in pred.answer.lower()
            )
            
            if len(pred.answer) > 100 and not is_refusal:
                # Manual Failure (dspy.Suggest missing)
                return dspy.Prediction(
                    answer="Verification Failed: Detailed answer provided without citations. Please retry query.",
                    citations=[]
                )
            
            # If it IS a refusal, we let it pass (Verified Negative)
            return dspy.Prediction(answer=pred.answer, citations=[])

        # ---------------------------------------------------------
        # Standard Checks (Only run if citations exist)
        # ---------------------------------------------------------
        
        # Assertion 1: Format Check
        # Now handled by extraction logic largely, but we double check
        # is_valid_format = all("_S" in c and "[" in c and "]" in c for c in citations_list)
        
        # Assertion 2: Hallucination Check
        citation_found = True
        missing_cits = []
        
        # Helper to normalize ID for comparison (e.g. [GEN_01_01_S01] -> [GEN_1_1_S1])
        def normalize_id_for_cmp(ref):
             # Remove brackets
             s = ref.replace("[", "").replace("]", "")
             parts = s.split('_')
             # Re-assemble with int casting to strip zeros
             try:
                 # Standard format: BOOK_CH_VS_SXX or similar
                 # We just want to strip leading zeros from any numeric component
                 norm_parts = []
                 for p in parts:
                     if p.isdigit():
                         norm_parts.append(str(int(p)))
                     elif p.startswith("S") and p[1:].isdigit():
                          # Handle Sentence ID suffix specially if needed, but int(digit) works for S01 -> S1?
                          # Actually S01 is usually S + digits.
                          norm_parts.append(f"S{int(p[1:])}")
                     else:
                         norm_parts.append(p)
                 return "_".join(norm_parts)
             except:
                 return s

        # Pre-compute valid normalized set
        valid_norm = {normalize_id_for_cmp(v) for v in valid_citations}
        
        for cit in citations_list:
            clean_cit = cit.strip()
            # 1. Exact Match
            if clean_cit in valid_citations:
                continue
            
            # 2. Normalized Match (Zero-padding tolerance)
            if normalize_id_for_cmp(clean_cit) in valid_norm:
                continue
                
            # If neither, it's missing
            citation_found = False
            missing_cits.append(clean_cit)
        
        if not citation_found:
             return dspy.Prediction(
                 answer=f"Verification Failed: Cited sources not found in context. Missing: {missing_cits}",
                 citations=[]
             )

        # ---------------------------------------------------------
        # Verbatim quote verification (ADR-0006).
        # ---------------------------------------------------------
        # The GillSignature contract promises the user that every double-quoted
        # span in the answer appears verbatim in Gill's source. Verify by
        # substring-matching each "quote" [SID] pair against the source text
        # for that Sentence ID (after light normalization for italics, footnote
        # refs, curly quotes, and whitespace).
        chunks_by_sid = _build_chunks_by_sid(context_chunks)
        quote_failures = _verify_quotes(pred.answer, chunks_by_sid)
        if quote_failures:
            print(f"DEBUG: Quote verification failures: {quote_failures}")
            first = quote_failures[0]
            return dspy.Prediction(
                answer=(
                    "Verification Failed: a quoted passage did not match Gill's text verbatim. "
                    f"Sentence ID {first['sentence_id']} — quote: \"{first['quote']}...\" "
                    f"(reason: {first['reason']}). "
                    f"Total unverified quotes: {len(quote_failures)}. "
                    "Please retry the query."
                ),
                citations=[]
            )

        # If we get here, pass
        return dspy.Prediction(answer=pred.answer, citations=citations_list)

if __name__ == "__main__":
    # Test
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    # Configure LM
    # Assuming OpenRouter
    key = os.getenv("OPENROUTER_API_KEY")
    if key:
        lm = dspy.LM("openrouter/deepseek/deepseek-chat", api_key=key, api_base="https://openrouter.ai/api/v1")
        dspy.configure(lm=lm)
    
        bot = GroundedGillBot()
        
        # Mock Context
        ctx = [
            {"citation": "[Vol 1, p. 100]", "content": "God is eternal and infinite."},
            {"citation": "[Vol 1, p. 101]", "content": "The covenant of grace is sure."}
        ]
        
        try:
            res = bot(question="What is the covenant?", context_chunks=ctx)
            print(f"Answer: {res.answer}")
            print(f"Citations: {res.citations}")
        except dspy.DSPyAssertionError as e:
            print(f"Assertion failed: {e}")
