
import dspy
import re
from typing import List

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
