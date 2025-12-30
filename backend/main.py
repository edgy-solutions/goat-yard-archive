
import os
import uvicorn
import dspy
import json
import litellm
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Any

# Import our modules
from .gill_search import GillSearchEngine
from .bot import GroundedGillBot
from .database import init_db
from .webhooks import router as webhook_router
from .auth import get_optional_user_id, security

# Rate Limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Rate Limit Keys
def auth_limit_key(request: Request):
    """Returns user ID if authenticated, else None (skips limit)"""
    if hasattr(request.state, "user_id") and request.state.user_id:
        return f"user:{request.state.user_id}"
    return None

# Proxy-Aware IP Resolution
def get_real_remote_address(request: Request) -> str:
    """
    Resolves the real client IP, prioritizing headers set by proxies
    (Cloudflare, Ingress, etc.).
    """
    # 1. Cloudflare
    if "cf-connecting-ip" in request.headers:
        return request.headers["cf-connecting-ip"]
    
    # 2. X-Forwarded-For (Standard)
    # The first IP in the list is the original client
    if "x-forwarded-for" in request.headers:
        return request.headers["x-forwarded-for"].split(",")[0].strip()
        
    # 3. X-Real-IP
    if "x-real-ip" in request.headers:
        return request.headers["x-real-ip"]
        
    # 4. Fallback to direct connection
    return get_remote_address(request) or "127.0.0.1"

def anon_limit_key(request: Request):
    """Returns IP if anonymous, else None (skips limit)"""
    if hasattr(request.state, "user_id") and request.state.user_id:
        return None
    return get_real_remote_address(request)

# Use the proxy-aware function for the global limiter
limiter = Limiter(key_func=get_real_remote_address)
# Custom Rate Limit Handler (Dr. Gill's Tone)
async def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "detail": (
                "My dear friend, it appears you have exhausted your daily allowance of ten inquiries per day. "
                "To continue our study of the Scriptures together, I pray you would join our number by signing in, "
                "that we may search the deep things of God without constraint."
            )
        }
    )

app = FastAPI(title="Gill Commentary API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, custom_rate_limit_handler)
app.include_router(webhook_router)

# Auth Middleware
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # Attempt to extract User ID from header (Basic parse, full verify in Auth module if desired)
    # Ideally reuse auth logic. Here we do a quick check or full check?
    # Used for Rate Limiting.
    auth_header = request.headers.get("Authorization")
    request.state.user_id = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        # We need to verify logic. Since middleware fails hard if we import heavy logic,
        # we can try to use a utility.
        # Importing logic from auth.py
        from .auth import PyJWKClient, jwt, CLERK_ISSUER
        if CLERK_ISSUER:
            try:
                # Optimized: In prod, cache JWKs. PyJWKClient does caching.
                jwks_client = PyJWKClient(f"{CLERK_ISSUER}/.well-known/jwks.json")
                signing_key = jwks_client.get_signing_key_from_jwt(token)
                data = jwt.decode(token, signing_key.key, algorithms=["RS256"], issuer=CLERK_ISSUER, options={"verify_aud": False})
                request.state.user_id = data.get("sub")
            except:
                pass 
    
    response = await call_next(request)
    return response
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
lm_auth = None
lm_anon = None

@app.on_event("startup")
def startup():
    print("--- STARTUP EVENT FIRED ---")
    global search_engine, bot, lm_auth, lm_anon
    
    # 1. Search Engine
    try:
        init_db()
        search_engine = GillSearchEngine()
        print("Search Engine initialized.")
    except Exception as e:
        print(f"Failed to init Search Engine/DB: {e}")

    # 2. DSPy Bot (Dual Key Logic)
    try:
        key_main = os.getenv("OPENROUTER_API_KEY")
        key_anon = os.getenv("OPENROUTER_API_KEY_ANON") or key_main # Fallback to main if no anon key

        if key_main:
            # Initialize Auth LM
            lm_auth = dspy.LM("openrouter/deepseek/deepseek-chat", api_key=key_main, api_base="https://openrouter.ai/api/v1")
            
            # Initialize Anon LM (might be same key)
            lm_anon = dspy.LM("openrouter/deepseek/deepseek-chat", api_key=key_anon, api_base="https://openrouter.ai/api/v1")
            
            # Default helper configuration (just for consistency, context managers override this)
            dspy.configure(lm=lm_anon) 
            
            bot = GroundedGillBot()
            print(f"DSPy Bot initialized. Dual Keys Active: {key_main != key_anon}")
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

@app.post("/api/search")
@limiter.limit("100/day", key_func=auth_limit_key)
@limiter.limit(lambda: os.getenv("RATE_LIMIT", "10/day"), key_func=anon_limit_key)
async def search(request: Request, req: SearchRequest):
    if not search_engine:
        raise HTTPException(status_code=500, detail="Search Engine not initialized")
    
    async def event_generator():
        # 1. Retrieve Evidence
        raw_results = search_engine.search_gill(req.query, limit=5)
        
        # Format and Send Evidence Immediately
        evidence_list = []
        context_str = ""
        valid_citations = set()
        
        if raw_results:
            for r in raw_results:
                ev_item = EvidenceItem(
                    chunk_id=r["chunk_id"],
                    content=r["content"],
                    verse_ref=r.get("verse_ref"),
                    citation=r.get("citation", "Unknown"),
                    vol=r.get("vol", 1),
                    page=r.get("page", 0),
                    scan=r.get("scan_json"), # Can be list or highlight object
                    footnotes=r.get("footnotes", []),
                    entities=r.get("entities", []),
                    score=r["score"]
                )
                evidence_list.append(ev_item)
                
                # Build Context for LLM
                citation_tag = r.get("citation", "Unknown")
                valid_citations.add(citation_tag)
                verse_ref_str = r.get("verse_ref", "")
                text = r.get("content", "")
                context_str += f"Source {citation_tag} ({verse_ref_str}): {text}\n\n"
        
        # Yield Evidence Block
        # We use json.dumps with 'default' to handle Pydantic models if needed, but evidence_list is list of models
        # iterating models manually is safer or use model_dump
        ev_dicts = [e.model_dump() for e in evidence_list]
        yield json.dumps({"type": "evidence", "data": ev_dicts}) + "\n"
        
        if not raw_results:
            yield json.dumps({"type": "chunk", "text": "No relevant commentary found."}) + "\n"
            yield json.dumps({"type": "result", "verified": True, "citations": []}) + "\n"
            return

        # 2. Generate Answer (Streaming)
        answer_accum = ""
        
        if bot:
            try:
                # Select LM
                target_lm = lm_auth if (hasattr(request.state, "user_id") and request.state.user_id) else lm_anon
                
                # Manually Construct Prompt to mimic the Signature
                system_prompt = (
                    "You are an intimate 18th-century contemporary of Dr. John Gill. "
                    "Answer questions by summarizing what \"The Expositor\" or \"Dr. Gill\" teaches in the provided context. "
                    "Speak in a learned, reverent, and slightly archaic 18th-century academic tone, always referring to him in the third person. "
                    "Do not append a list of citations or bibliography at the end of your response. "
                    "Base your answer ONLY on the provided context."
                )
                
                full_prompt = f"{system_prompt}\n\nContext:\n{context_str}\n\nQuestion: {req.query}\n\nAnswer:"
                
                # Stream Generation
                # Bypass DSPy stream wrapper issue by calling litellm directly
                # Resolve Key
                api_key = os.getenv("OPENROUTER_API_KEY")
                if target_lm == lm_anon:
                    api_key = os.getenv("OPENROUTER_API_KEY_ANON") or api_key
                
                response = litellm.completion(
                    model=target_lm.model,
                    messages=[{"role": "user", "content": full_prompt}],
                    api_key=api_key,
                    base_url="https://openrouter.ai/api/v1",
                    stream=True
                )
                
                for chunk in response:
                    content = chunk.choices[0].delta.content
                    if content:
                        yield json.dumps({"type": "chunk", "text": content}) + "\n"
                        answer_accum += content
                        
                # 3. Verification
                citations_found = []
                verified = True
                
                import re
                citations_found = re.findall(r"\[Vol \d+, p\. \d+\]", answer_accum)
                
                for cit in citations_found:
                    if cit not in valid_citations:
                        verified = False
                        yield json.dumps({"type": "chunk", "text": f"\n\n[Warning: Citation {cit} not found in source text]"}) + "\n"
                
                yield json.dumps({"type": "result", "verified": verified, "citations": citations_found}) + "\n"
                
            except Exception as e:
                yield json.dumps({"type": "chunk", "text": f"\nError generating answer: {e}"}) + "\n"
                yield json.dumps({"type": "result", "verified": False, "citations": []}) + "\n"
        else:
             yield json.dumps({"type": "chunk", "text": "LLM Generation disabled (No Key)."}) + "\n"
             yield json.dumps({"type": "result", "verified": False, "citations": []}) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
