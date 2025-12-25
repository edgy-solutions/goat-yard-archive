
import os
import uvicorn
import dspy
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Any

# Import our modules
from .gill_search import GillSearchEngine
from .bot import GroundedGillBot

app = FastAPI(title="Gill Commentary API")
print(f"--- LOADING BACKEND/MAIN.PY FROM: {__file__} ---")

# CORS (Allow Frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Engine & Bot
search_engine = None
bot = None

@app.on_event("startup")
def startup():
    print("--- STARTUP EVENT FIRED ---")
    global search_engine, bot
    
    # 1. Search Engine
    try:
        search_engine = GillSearchEngine()
        print("Search Engine initialized.")
    except Exception as e:
        print(f"Failed to init Search Engine: {e}")

    # 2. DSPy Bot
    try:
        key = os.getenv("OPENROUTER_API_KEY")
        if key:
            # Using a capable model for reasoning
            lm = dspy.LM("openrouter/deepseek/deepseek-chat", api_key=key, api_base="https://openrouter.ai/api/v1")
            dspy.configure(lm=lm)
            bot = GroundedGillBot()
            print("DSPy Bot initialized.")
        else:
            print("Warning: OPENROUTER_API_KEY not found. Bot disabled.")
    except Exception as e:
        print(f"Failed to init Bot: {e}")

@app.on_event("shutdown")
def shutdown():
    if search_engine:
        search_engine.close()

# Models
class SearchRequest(BaseModel):
    query: str

class EvidenceItem(BaseModel):
    chunk_id: str
    content: str
    verse_ref: Optional[str] = None
    citation: str
    vol: int
    page: int
    scan: Optional[Any]
    footnotes: Optional[List[str]] = []
    entities: Optional[List[str]] = []
    score: float

class SearchResponse(BaseModel):
    answer: str
    citations: List[str]
    evidence: List[EvidenceItem]
    verified: bool

@app.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest):
    if not search_engine:
        raise HTTPException(status_code=500, detail="Search Engine not initialized")
    
    # 1. Retrieve Evidence
    raw_results = search_engine.search_gill(req.query, limit=5)
    
    if not raw_results:
        return SearchResponse(
            answer="No relevant commentary found.",
            citations=[],
            evidence=[],
            verified=True
        )

    # 2. Generate Answer (if Bot available)
    answer = "LLM Generation disabled (No Key)."
    citations = []
    verified = False
    
    if bot:
        try:
            # Forward pass
            # Forward pass
            # FORCE DEBUG CHECK
            pred = bot(question=req.query, context_chunks=raw_results)
            answer = pred.answer
            citations = pred.citations
            verified = True
                 
        except Exception as e:
            if "Assert" in type(e).__name__ or isinstance(e, AssertionError):
                  answer = f"Generated answer could not be verified against sources.\nError: {e}"
                  verified = False
            else:
                  answer = f"Error generating answer: {e}"
                  verified = False
    
    # Format Evidence
    evidence_list = []
    for r in raw_results:
        evidence_list.append(EvidenceItem(
            chunk_id=r["chunk_id"],
            content=r["content"],
            verse_ref=r.get("verse_ref"),
            citation=r["citation"],
            vol=int(r["vol"]) if r["vol"] else 0,
            page=int(r["page"]) if r["page"] else 0,
            scan=r["scan"],
            footnotes=r.get("footnotes", []),
            entities=r.get("entities", []),
            score=r["score"]
        ))

    if evidence_list:
        print(f"DEBUG: First Evidence Item Entities: {evidence_list[0].entities}")

    return SearchResponse(
        answer=answer,
        citations=citations,
        evidence=evidence_list,
        verified=verified
    )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
