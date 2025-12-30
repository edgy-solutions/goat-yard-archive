
import os
import uvicorn
import dspy
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
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

@app.post("/api/search", response_model=SearchResponse)
@limiter.limit("100/day", key_func=auth_limit_key)
@limiter.limit(lambda: os.getenv("RATE_LIMIT", "10/day"), key_func=anon_limit_key)
async def search(request: Request, req: SearchRequest):
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
            # Select LM based on auth status
            # Use lm_auth if user is signed in, otherwise lm_anon
            target_lm = lm_auth if (hasattr(request.state, "user_id") and request.state.user_id) else lm_anon
            
            # Use specific LM context for this request
            with dspy.context(lm=target_lm):
                # Forward pass
                pred = bot(question=req.query, context_chunks=raw_results)
                answer = pred.answer
                citations = pred.citations

                # --- DEBUG LOGGING ---
                # Print the actual specific prompts/responses to console for user visibility
                if hasattr(target_lm, "history") and target_lm.history:
                    last_run = target_lm.history[-1]
                    print("\n" + "="*50)
                    print(" [DSPy INTERACTION LOG] ")
                    print("="*50)
                    
                    # Prompt / Messages
                    print("\n--- PROMPT / MESSAGES ---")
                    if "messages" in last_run:
                        for m in last_run["messages"]:
                            role = m.get("role", "unknown").upper()
                            content = m.get("content", "")
                            # Print full content for verification
                            print(f"[{role}]: {content}")
                    else:
                         print(last_run.get("prompt", "No prompt found"))

                    # Response
                    print("\n--- RESPONSE ---")
                    # Try to parse response content safely
                    try:
                        resp_obj = last_run.get("response")
                        if hasattr(resp_obj, "choices"):
                             print(resp_obj.choices[0].message.content)
                        else:
                             print(resp_obj)
                    except:
                        print("Could not parse response object")
                    
                    print("="*50 + "\n")
                # ---------------------
                
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

@app.get("/api/books")
async def get_books():
    """Return list of available books in the index."""
    if not search_engine:
        # Fallback if engine down
        return {"books": ["Genesis", "Matthew"]}
    return {"books": search_engine.get_available_books()}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
