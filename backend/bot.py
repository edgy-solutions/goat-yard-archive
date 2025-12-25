
import dspy
import re
from typing import List

# Define Signature
class GillSignature(dspy.Signature):
    """Answer questions about John Gill's commentary based ONLY on the provided context."""
    
    context = dspy.InputField(desc="Excerpts from the commentary with [Vol, Page] citations.")
    question = dspy.InputField(desc="The user's theological question.")
    
    answer = dspy.OutputField(desc="A detailed answer citing the specific volumes and pages.")
    citations = dspy.OutputField(desc="A list of citations used, e.g. ['[Vol 1, p. 104]', '[Vol 2, p. 50]']")

class GroundedGillBot(dspy.Module):
    def __init__(self):
        super().__init__()
        self.generate_answer = dspy.ChainOfThought(GillSignature)
        
    def forward(self, question: str, context_chunks: List[dict]):
        # 1. Format Context
        # We need to explicitly include the [Vol, Page] metadata in the text so the model can see it.
        formatted_context = ""
        valid_citations = set()
        
        for chunk in context_chunks:
            citation_tag = chunk.get("citation", "Unknown") # e.g. [Vol 1, p. 287]
            valid_citations.add(citation_tag)
            text = chunk.get("content", "")
            formatted_context += f"Source {citation_tag}: {text}\n\n"
            
        # 2. Generate
        pred = self.generate_answer(context=formatted_context, question=question)
        
        # 3. Assertions (The Critic)
        # Check 1: Format
        # We expect citations to be a list of strings
        # dspy.Suggest/Assert works on the prediction object directly usually
        # But here we do manual checks + dspy.Assert
        
        # We wrap in a helper to use dspy.Assert
        # Note: In dspy 2.5+, assertions are typically part of the pipeline validation.
        # Here we implement it as runtime logic.
        
        # Parse citations if it's a string (sometimes LLMs output string repr of list)
        citations_list = pred.citations
        if isinstance(citations_list, str):
            # Use regex to find all valid citations of format [Vol X, p. Y]
            # This is safer than splitting by comma which breaks the citation itself
            import re
            citations_list = re.findall(r"\[Vol \d+, p\. \d+\]", citations_list)

        # Assertion 1: Format Check
        # Regex for [Vol X, p. Y]
        fmt_pattern = re.compile(r"\[Vol \d+, p\. \d+\]")
        for cit in citations_list:
            if not fmt_pattern.match(cit):
                raise AssertionError(f"Citation '{cit}' does not match format [Vol X, p. Y].")
            
        # Assertion 2: Hallucination Check
        # Every cited source must be in valid_citations (from context)
        for cit in citations_list:
            # We strip whitespace to be lenient
            cit_clean = cit.strip()
            # We allow partial match if really needed, but strict is better for grounding.
            # actually strict equality is best given we formatted it.
            if cit_clean not in valid_citations:
                raise AssertionError(f"Citation '{cit_clean}' was not found in the provided context sources: {valid_citations}")
            
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
