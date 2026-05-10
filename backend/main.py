
import os
import uvicorn
import dspy
import litellm
import json
import warnings
import asyncio
from langfuse import Langfuse
# from langfuse.decorators import langfuse_context (Not found in installed version)
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Any

# Import our modules
from .gill_search import GillSearchEngine
from .bot import GroundedGillBot
from baml_client.async_client import b
from .database import init_db
from .webhooks import router as webhook_router
from .bible_api import router as bible_router
from .auth import get_optional_user_id, security
from .bible_mapping import format_book_ranges

# Rate Limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Filter Pydantic Warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

# Global Langfuse client for feedback endpoint
langfuse_client = None
try:
    if os.getenv("LANGFUSE_PUBLIC_KEY"):
        langfuse_client = Langfuse()
except Exception:
    pass

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("--- STARTUP EVENT FIRED ---")
    global search_engine, bot, lm_auth, lm_anon
    
    # 0. Langfuse / Litellm Setup
    try:
        if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
            print("Initializing Langfuse integration for TitleLLM/DSPy...")
            # Disable auto-callbacks as they cause AttributeError with current versions
            litellm.success_callback = [] 
            litellm.failure_callback = []
        else:
            print("Langfuse keys not found. Tracing disabled.")
    except Exception as e:
        print(f"Failed to init Langfuse: {e}")

    # 1. Search Engine
    try:
        init_db()
        search_engine = GillSearchEngine()
        await search_engine.connect()
        print("Search Engine initialized.")
    except Exception as e:
        print(f"Failed to init Search Engine/DB: {e}")

    # 2. DSPy Bot (Dual Key Logic)
    try:
        key_main = os.getenv("OPENROUTER_API_KEY")
        key_anon_check = os.getenv("OPENROUTER_API_KEY_ANON") or key_main # Fallback to main if no anon key

        if key_main:
            # Initialize Auth LM with usage flag
            lm_auth = dspy.LM(
                model="openai/deepseek/deepseek-chat",
                api_key=key_main,
                api_base="https://openrouter.ai/api/v1",
                extra_body={"usage": {"include": True}}
            )
            
            # Initialize Anon LM (might be same key)
            lm_anon = dspy.LM(
                model="openai/deepseek/deepseek-chat",
                api_key=key_anon_check,
                api_base="https://openrouter.ai/api/v1",
                extra_body={"usage": {"include": True}}
            )
            
            # Default helper configuration (just for consistency, context managers override this)
            dspy.settings.configure(lm=lm_anon) 
            
            bot = GroundedGillBot()
            print(f"DSPy Bot initialized. Dual Keys Active: {key_main != key_anon_check}")
        else:
            print("Warning: OPENROUTER_API_KEY not found. Bot disabled.")
            
    except Exception as e:
        print(f"Failed to init Bot: {e}")

    yield

    if search_engine:
        await search_engine.close()

app = FastAPI(title="Gill Commentary API", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, custom_rate_limit_handler)
app.include_router(webhook_router)
app.include_router(bible_router)

# Auth Middleware
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # Attempt to extract User ID from header (Basic parse, full verify in Auth module if desired)
    auth_header = request.headers.get("Authorization")
    request.state.user_id = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        from .auth import PyJWKClient, jwt, CLERK_ISSUER
        if CLERK_ISSUER:
            try:
                # Optimized: In prod, cache JWKs. PyJWKClient does caching.
                jwks_client = PyJWKClient(f"{CLERK_ISSUER}/.well-known/jwks.json", cache_keys=True)
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



# Models
class SearchRequest(BaseModel):
    query: str
    volume_limit: Optional[int] = None

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
    sentence_data: Optional[List[Any]] = [] # New field for highlighting
    lemma: Optional[str] = None # New Lemma field
    score: float

class SearchResponse(BaseModel):
    answer: str
    citations: List[str]
    evidence: List[EvidenceItem]
    verified: bool
    expanded_query: Optional[str] = None
    mapped_entities: Optional[List[str]] = []
    trace_id: Optional[str] = None

class FeedbackRequest(BaseModel):
    trace_id: str
    score: int
    issue_type: str = ""
    comment: str = ""
@app.post("/api/search", response_model=SearchResponse)
@limiter.limit("100/day", key_func=auth_limit_key)
@limiter.limit(lambda: os.getenv("RATE_LIMIT", "10/day"), key_func=anon_limit_key)
async def search(request: Request, req: SearchRequest):
    # Set User ID in Langfuse Trace
    # if hasattr(request.state, "user_id") and request.state.user_id:
    #     langfuse_context.update_current_trace(user_id=request.state.user_id)
    # else:
    #     # Try finding anon IP
    #     ip = get_real_remote_address(request)
    #     langfuse_context.update_current_trace(user_id=f"anon-{ip}")

    if not search_engine:
        raise HTTPException(status_code=500, detail="Search Engine not initialized")
    
    # 1. Optimize and Expand Query (Enterprise Search Upgrade)
    available_entity_names = await search_engine.get_relevant_entities(query=req.query, limit=50)
    
    try:
        optimized_query = await b.OptimizeSearchQuery(
            user_query=req.query,
            available_entities=available_entity_names
        )
        search_text = optimized_query.expanded_search_terms
        mapped_entities = optimized_query.official_entities
        print(f"BAML Optimized Query: {search_text}")
        print(f"BAML Mapped Entities: {mapped_entities}")
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        print(f"BAML Optimization failed, falling back to raw query:\n{error_msg}")
        search_text = req.query
        mapped_entities = None

    # 2. Retrieve Evidence
    raw_results = await search_engine.search_gill(
        query=search_text, 
        entities=mapped_entities, 
        limit=5,
        volume_filter=req.volume_limit
    )
    if raw_results:
        import logging
        logging.error(f"DEBUG MAIN: First result lemma: '{raw_results[0].get('lemma')}'")
        logging.error(f"DEBUG MAIN: First result keys: {raw_results[0].keys()}")
    # span.update(metadata={"hit_count": len(raw_results)})
    
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
    
    # MANUAL MAPPING TO ENSURE LEMMA IS NOT LOST
    evidence_objects = []
    for r in raw_results:
        ev = EvidenceItem(
            chunk_id=r["chunk_id"],
            content=r["content"],
            verse_ref=r.get("verse_ref"),
            citation=r["citation"],
            vol=r["vol"],
            page=r["page"],
            scan=r.get("scan"),
            footnotes=r.get("footnotes", []),
            entities=r.get("entities", []),
            sentence_data=r.get("sentence_data", []),
            lemma=r.get("lemma"), # EXPLICIT
            score=r["score"]
        )
        evidence_objects.append(ev)

    if bot:
        try:
            # Select LM based on auth status
            # Use lm_auth if user is signed in, otherwise lm_anon
            target_lm = lm_auth if (hasattr(request.state, "user_id") and request.state.user_id) else lm_anon
            
            # Use specific LM context for this request
            with dspy.context(lm=target_lm):
                trace_name = "dspy_generation"
                user_id = request.state.user_id if request.state.user_id else f"anon-{get_real_remote_address(request)}"
                
                # Manual trace management for better control
                # We use the raw client instance `lf` created safely above inside `search` (Wait, I need to instantiate it here or outside)
                # Actually, best practice is to instantiate a fresh client per request if relying on env vars, to pick up latest config or context?
                # But typically `Langfuse()` is lightweight.
                
                lf_client = None
                if os.getenv("LANGFUSE_PUBLIC_KEY"):
                    try:
                        lf_client = Langfuse()
                    except:
                        lf_client = None

                generation = None
                
                # Context managed generation
                # We check if client is available. If so, we use it.
                # If not, we just run the bot.
                
                if lf_client:
                    # Create context manager for generation
                    gen_ctx = lf_client.start_as_current_observation(
                        name="bot_forward",
                        metadata={"volume_limit": req.volume_limit},
                        as_type="generation"
                    )
                    # We manually enter the context
                    generation = gen_ctx.__enter__()
                    # Update generation with input/metadata immediately
                    if generation:
                        generation.update(input=req.query)
                        # We cannot set user_id on a generation typically, it belongs to the trace.
                        # But we can try setting it on the context via `lf_client.update_current_trace(user_id=...)`
                        # However, for now let's skip setting user_id on generation explicitly as it inherits from trace.
                        lf_client.update_current_trace(user_id=user_id)
                else:
                    gen_ctx = None
                    generation = None

                try:
                    import time
                    # Fetch available books for refusal context (Cached with 5-minute TTL)
                    now = time.time()
                    cache_time = getattr(app.state, "available_books_time", 0)
                    if not getattr(app.state, "available_books", None) or (now - cache_time > 300):
                         try:
                             app.state.available_books = await search_engine.get_available_books()
                             app.state.available_books_time = now
                         except Exception as e:
                             print(f"Error fetching books for cache: {e}")
                             app.state.available_books = ["Genesis", "Matthew"]
                    
                    books = app.state.available_books
                    available_books_str = ", ".join(books) if books else "Unknown"

                    pred = await asyncio.to_thread(bot, question=req.query, context_chunks=raw_results, available_books=available_books_str)
                    answer = pred.answer
                    citations = pred.citations
                    verified = True
                    
                    if generation:
                        generation.update(output=answer)
                    
                    # Capture trace_id for feedback loop
                    trace_id = generation.trace_id if generation else None
                        
                except Exception as e:
                    if generation:
                         generation.update(level="ERROR", status_message=str(e))
                    raise e
                    
                finally:
                    # --- DEBUG LOGGING & USAGE TRACKING ---
                    if hasattr(target_lm, "history") and target_lm.history:
                        last_run = target_lm.history[-1]
                        
                        # Console Debug First
                        print("\n" + "="*50)
                        print(" [DSPy INTERACTION LOG] ")
                        print("="*50)
                        
                        # ... Log Prompt ...
                        if "messages" in last_run:
                            print("\n--- PROMPT / MESSAGES ---")
                            for m in last_run["messages"]:
                                print(f"[{m.get('role','').upper()}]: {m.get('content','')}")
                        else:
                            print(last_run.get("prompt", "No prompt"))
                        
                        # ... Log Response ...
                        print("\n--- RESPONSE ---")
                        try:
                            resp_obj = last_run.get("response")
                            if hasattr(resp_obj, "choices"):
                                    print(resp_obj.choices[0].message.content)
                            else:
                                    print(resp_obj)
                        except:
                            print("Could not parse response object")
                        
                        # Usage
                        usage = last_run.get("usage")
                        print("\n--- USAGE ---")
                        print(f"Usage: {usage}")
                        print("="*50 + "\n")

                        # Update Langfuse Generation Usage
                        if generation and usage:
                            cost_details = last_run.get("cost_details", {})
                            lf_usage = {
                                "input": usage.get("prompt_tokens"),
                                "output": usage.get("completion_tokens"),
                                "total": usage.get("total_tokens"),
                                "unit": "TOKENS", 
                            }
                            lf_cost = {
                                "total": usage.get("cost"),
                                "input": cost_details.get("upstream_inference_prompt_cost"),
                                "output": cost_details.get("upstream_inference_completions_cost")
                            }
                            
                            model_name = last_run.get("model") or "deepseek-chat"
                            generation.update(usage_details=lf_usage, cost_details=lf_cost, model=model_name)
                    
                    if gen_ctx:
                        gen_ctx.__exit__(None, None, None)
                    
                    if lf_client:
                        import asyncio
                        await asyncio.sleep(0.5) 
                        lf_client.flush()
                # ---------------------
                
            # Update trace metadata and score
            if lf_client and generation:
                try:
                    meta_books = locals().get("available_books_str", "Unknown")
                    env_tag = os.getenv("APP_ENV", "production")
                    lf_client.update_current_trace(
                        metadata={
                            "available_books": meta_books, 
                            "volume_context": "all",
                            "baml_expanded_query": search_text,
                            "baml_mapped_entities": mapped_entities
                        }, 
                        tags=[env_tag, "v7_launch"]
                    )
                    if "I regret that" in answer:
                        lf_client.create_score(trace_id=generation.trace_id, name="retrieval_success", value=0, comment="Guardrail triggered: Empty context or manifest mismatch")
                    else:
                        lf_client.create_score(trace_id=generation.trace_id, name="retrieval_success", value=1)
                except Exception as ex:
                    print(f"Failed to update Langfuse trace metadata/score: {ex}")

        except Exception as e:
            if "Assert" in type(e).__name__ or isinstance(e, AssertionError):
                  answer = f"Generated answer could not be verified against sources.\nError: {e}"
                  verified = False
            else:
                  answer = f"Error generating answer: {e}"
                  verified = False

    # ---------------------
    
    # 3. Final Verification and Response Formatting
    # Ensure verified flag is set correctly based on final answer
    if "Verification Failed:" in answer:
        verified = False
        
    if evidence_objects:
        print(f"DEBUG: First Evidence Item Entities: {evidence_objects[0].entities}")
    
    # Extract citations for the response
    final_citations = [ev.citation for ev in evidence_objects]

    return SearchResponse(
        answer=answer,
        citations=final_citations,
        evidence=evidence_objects,
        verified=verified,
        expanded_query=search_text,
        mapped_entities=mapped_entities,
        trace_id=trace_id if 'trace_id' in locals() else None
    )

@app.get("/api/books")
async def get_books():
    """Return list of available books in the index."""
    if not search_engine:
        # Fallback if engine down
        return {"books": ["Genesis", "Matthew"]}
    raw_books = await search_engine.get_available_books()
    return {"books": format_book_ranges(raw_books)}

@app.post("/api/feedback")
async def feedback(req: FeedbackRequest):
    """Receive user feedback and score the Langfuse trace."""
    if not langfuse_client:
        raise HTTPException(status_code=503, detail="Feedback system not configured")
    
    full_comment = f"{req.issue_type}: {req.comment}" if req.issue_type else req.comment
    
    try:
        langfuse_client.create_score(
            trace_id=req.trace_id,
            name="retrieval_success",
            value=req.score,
            comment=full_comment
        )
        return {"status": "ok"}
    except Exception as e:
        print(f"Failed to submit feedback score: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to record feedback: {e}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
