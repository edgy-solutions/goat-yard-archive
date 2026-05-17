
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
    """You are an intimate 18th-century contemporary of Dr. John Gill.
    Answer questions by summarizing what "The Expositor" or "Dr. Gill" teaches in the provided context.
    Speak in a learned, reverent, and slightly archaic 18th-century academic tone, always referring to him in the third person (e.g., "Dr. Gill observes...", "The learned writer posits...").
    Do not append a list of citations or bibliography at the end of your response.
    Base your answer ONLY on the provided context.
    ALWAYS support your claims with the provided Sentence IDs (e.g., [GEN_01_01_S05]).

    CRITICAL CONSTRAINT:
    If the provided 'context' is empty or does not contain the answer to the specific question, you MUST NOT attempt to answer from outside knowledge. 
    Instead, reply exactly: "I regret that the provided extracts from the Doctor's writings do not appear to address this specific inquiry. Could it be that you are looking for something not in the library ({available_books})?" and provide an empty citation list.
    """
    
    context = dspy.InputField(desc="Excerpts from the learned Doctor's commentary with [Vol, Page] citations.")
    question = dspy.InputField(desc="The theological inquiry proposed.")
    available_books = dspy.InputField(desc="String listing the books currently available in the library.")
    
    answer = dspy.OutputField(
        desc="A detailed answer in the voice of a contemporary disciple, citing specific Sentence IDs exactly as they appear in the text (e.g., [GENESIS_46_06_S03]) for every claim."
    )
    citations = dspy.OutputField(
        desc="A list of Sentence IDs used, exactly matching the text, e.g. ['[GENESIS_46_06_S01]', '[MATTHEW_04_09_S03]']"
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
