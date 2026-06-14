
import os
import re
import uvicorn
import dspy
import litellm
import json
import logging

# Structural refusal detection: a real verbatim answer must contain at least
# one inline [SENTENCE_ID] citation per the GillSignature contract. If the
# answer has zero, it's either the canned refusal or a malformed paraphrase —
# in both cases, we want to surface the model's reasoning to the user instead
# of just showing the refusal text.
_SID_IN_ANSWER_RE = re.compile(r'\[([A-Z0-9_]+_S\d+)\]')
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

# slowapi logs every rate-limit-key returning None at ERROR level with the
# message "Skipping limit: ..." — but returning None is the *documented* way
# to skip a limit (e.g. for anonymous users hitting an auth-gated limit).
# Suppress just that message so real errors stay visible in the log.
class _SuppressSlowapiSkippingLimit(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return "Skipping limit" not in msg

logging.getLogger("slowapi").addFilter(_SuppressSlowapiSkippingLimit())

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
    allow_origins=[
        "https://goatyardarchive.org",
        "https://www.goatyardarchive.org",
        "http://localhost:5173",
        "http://test.chart-example.local"
    ],
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
    # Sentence IDs whose Gill quote could not be verified (paraphrased, KJV-only,
    # or no quote attached at all). Frontend uses this to mark the specific
    # citation pills in the answer text with the warning color + icon, so the
    # user can see *which* part is unverified instead of just the global pill.
    unverified_sentence_ids: List[str] = []
    # Structural refusal detection — True when the answer contains NO inline
    # [SENTENCE_ID] citations (i.e. zero verbatim Gill quotes). Robust to the
    # model varying its refusal wording because it's based on a structural
    # property (citation count), not a string match.
    refused: bool = False
    # The model's reasoning text. Always returned so the frontend can
    # surface it when refused=True — the reasoning often names specific
    # SIDs the model considered but chose not to commit to, which turns
    # an opaque refusal into actionable starting points the user can click.
    reasoning: Optional[str] = None
    # Sentence IDs the model named in its reasoning that ARE in the retrieved
    # context (i.e. real, clickable SIDs). Populated when refused=True so the
    # frontend knows which SIDs to render as amber pills inside the reasoning
    # block. Empty list when reasoning identified nothing relevant either.
    partial_match_sids: List[str] = []
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
    import time
    t0 = time.perf_counter()
    
    if not search_engine:
        raise HTTPException(status_code=500, detail="Search Engine not initialized")
    
    # 1. Optimize and Expand Query (Enterprise Search Upgrade)
    t1 = time.perf_counter()
    available_entity_names = await search_engine.get_relevant_entities(query=req.query, limit=50)
    t2 = time.perf_counter()
    print(f"[TIMING] get_relevant_entities: {t2-t1:.3f}s")
    
    try:
        t3 = time.perf_counter()
        optimized_query = await b.OptimizeSearchQuery(
            user_query=req.query,
            available_entities=available_entity_names
        )
        t4 = time.perf_counter()
        print(f"[TIMING] BAML OptimizeSearchQuery: {t4-t3:.3f}s")
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
    t5 = time.perf_counter()
    raw_results = await search_engine.search_gill(
        query=search_text,
        entities=mapped_entities,
        limit=12,
        volume_filter=req.volume_limit,
        original_query=req.query,
    )
    t6 = time.perf_counter()
    print(f"[TIMING] search_gill (embed+weaviate): {t6-t5:.3f}s")

    # Deterministic chunk ordering. Weaviate hybrid scores can drift by tiny
    # FP amounts between identical queries, so the same chunk SET can arrive
    # in different orders — and the bot LLM is sensitive to context ordering.
    # Sort by first SID with chunk_id as final tiebreaker so the bot prompt
    # is byte-identical whenever retrieval returns the same chunks.
    def _first_sid(chunk):
        sd = chunk.get("sentence_data") or []
        if sd and isinstance(sd, list):
            first = sd[0]
            if isinstance(first, dict):
                sid = first.get("sentence_id") or first.get("sid")
                if sid:
                    return sid
        return chunk.get("verse_ref") or ""
    raw_results.sort(key=lambda c: (_first_sid(c), c.get("chunk_id", "")))
    
    if not raw_results:
        return SearchResponse(
            answer="No relevant commentary found.",
            citations=[],
            evidence=[],
            verified=True
        )

    # 3. Generate Answer (if Bot available)
    answer = "LLM Generation disabled (No Key)."
    citations = []
    verified = False
    unverified_sentence_ids: List[str] = []
    refused: bool = False
    reasoning_text: Optional[str] = None
    partial_match_sids: List[str] = []
    
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
            lemma=r.get("lemma"),
            score=r["score"]
        )
        evidence_objects.append(ev)

    if bot:
        try:
            target_lm = lm_auth if (hasattr(request.state, "user_id") and request.state.user_id) else lm_anon
            
            with dspy.context(lm=target_lm):
                user_id = request.state.user_id if request.state.user_id else f"anon-{get_real_remote_address(request)}"
                
                lf_client = None
                if os.getenv("LANGFUSE_PUBLIC_KEY"):
                    try:
                        lf_client = Langfuse()
                    except:
                        lf_client = None

                generation = None
                
                if lf_client:
                    gen_ctx = lf_client.start_as_current_observation(
                        name="bot_forward",
                        metadata={"volume_limit": req.volume_limit},
                        as_type="generation"
                    )
                    generation = gen_ctx.__enter__()
                    if generation:
                        generation.update(input=req.query)
                        lf_client.update_current_trace(user_id=user_id)
                else:
                    gen_ctx = None
                    generation = None

                try:
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

                    t7 = time.perf_counter()
                    # 90s matches the frontend's per-request timeout. The bot's
                    # LLM-generation step plus the optional LLM-repair fallback
                    # (when difflib can't repair an unverified quote) can push
                    # the total well past 60s on cold cache or with multiple
                    # repairs needed.
                    pred = await asyncio.wait_for(
                        asyncio.to_thread(bot, question=req.query, context_chunks=raw_results, available_books=available_books_str),
                        timeout=90.0
                    )
                    t8 = time.perf_counter()
                    print(f"[TIMING] LLM generation (bot): {t8-t7:.3f}s")
                    
                    answer = pred.answer
                    citations = pred.citations
                    # Hybrid quote repair (ADR-0006): the bot has already
                    # attempted to substitute verbatim source spans for any
                    # paraphrased quotes via difflib + LLM fallback. Surface
                    # both repairs (telemetry on prompt drift) and unrepairable
                    # failures (verified=False signal).
                    quote_failures = getattr(pred, "quote_failures", None) or []
                    quote_repairs = getattr(pred, "quote_repairs", None) or []
                    verified = not quote_failures
                    # Extract the bare sentence_ids (without surrounding brackets)
                    # for the frontend's per-citation styling.
                    unverified_sentence_ids = sorted({
                        (f.get("sentence_id") or "").strip("[]")
                        for f in quote_failures
                        if f.get("sentence_id")
                    } - {""})

                    # Structural refusal detection — does the answer contain any
                    # inline [SENTENCE_ID]? No SID = no verbatim Gill quote = refusal
                    # (or model paraphrase, which we also want to treat as refusal
                    # since we can't verify it). This is robust to refusal wording
                    # variations and doesn't depend on a string match.
                    reasoning_text = (getattr(pred, "reasoning", "") or "")
                    answer_sids = _SID_IN_ANSWER_RE.findall(pred.answer or "")
                    refused = len(answer_sids) == 0
                    # When refused, identify SIDs the model named in its reasoning
                    # that are real (i.e. in the retrieved context). These become
                    # the "you can still click these to read what the model
                    # considered" pills the frontend renders.
                    partial_match_sids: List[str] = []
                    if refused and reasoning_text:
                        # context_chunks is from the upstream search step
                        valid_in_context = {
                            s.get("sentence_id")
                            for chunk in (raw_results or [])
                            for s in (chunk.get("sentence_data") or [])
                            if s.get("sentence_id")
                        }
                        partial_match_sids = sorted({
                            sid for sid in _SID_IN_ANSWER_RE.findall(reasoning_text)
                            if sid in valid_in_context
                        })
                    if (quote_failures or quote_repairs) and generation:
                        generation.update(metadata={
                            "quote_verification_failures": len(quote_failures),
                            "quote_repairs_difflib": sum(1 for r in quote_repairs if r.get("source") == "difflib"),
                            "quote_repairs_llm": sum(1 for r in quote_repairs if r.get("source") == "llm"),
                            "quote_failure_reasons": sorted({f.get("reason", "") for f in quote_failures}),
                        })

                    if generation:
                        generation.update(output=answer)
                    
                    trace_id = generation.trace_id if generation else None
                        
                except asyncio.TimeoutError:
                    if generation:
                        generation.update(level="ERROR", status_message="LLM generation timed out after 60 seconds")
                    answer = "The learned Doctor's quill moves slowly, and the ink has dried before a response could be penned. Please try again."
                    verified = False
                except Exception as e:
                    if generation:
                         generation.update(level="ERROR", status_message=str(e))
                    raise e
                    
                finally:
                    if hasattr(target_lm, "history") and target_lm.history:
                        last_run = target_lm.history[-1]
                        
                        print("\n" + "="*50)
                        print(" [DSPy INTERACTION LOG] ")
                        print("="*50)
                        
                        if "messages" in last_run:
                            print("\n--- PROMPT / MESSAGES ---")
                            for m in last_run["messages"]:
                                print(f"[{m.get('role','').upper()}]: {m.get('content','')}")
                        else:
                            print(last_run.get("prompt", "No prompt"))
                        
                        print("\n--- RESPONSE ---")
                        try:
                            resp_obj = last_run.get("response")
                            if hasattr(resp_obj, "choices"):
                                    print(resp_obj.choices[0].message.content)
                            else:
                                    print(resp_obj)
                        except:
                            print("Could not parse response object")
                        
                        usage = last_run.get("usage")
                        print("\n--- USAGE ---")
                        print(f"Usage: {usage}")
                        print("="*50 + "\n")

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
                    
                    # Trace metadata + tags MUST be set while the gen_ctx span is
                    # still active. update_current_trace relies on the active span
                    # context to know which trace to attach to — once gen_ctx is
                    # exited, "no active span" is logged and the call silently
                    # drops. That's why tags column has been empty in the UI.
                    if lf_client and generation:
                        try:
                            meta_books = locals().get("available_books_str", "Unknown")
                            env_tag = os.getenv("APP_ENV", "production")
                            lf_client.update_current_trace(
                                metadata={
                                    "available_books": meta_books,
                                    "volume_context": "all",
                                    "baml_expanded_query": search_text,
                                    "baml_mapped_entities": mapped_entities,
                                },
                                tags=[env_tag, "v7_launch"],
                            )
                            # create_score takes explicit trace_id, so the active-
                            # span constraint doesn't apply, but we keep it here
                            # alongside the trace update for cohesion.
                            if refused:
                                lf_client.create_score(trace_id=generation.trace_id, name="retrieval_success", value=0, comment="Bot produced no inline-cited answer (refusal or empty quotes)")
                            else:
                                lf_client.create_score(trace_id=generation.trace_id, name="retrieval_success", value=1)
                        except Exception as ex:
                            print(f"Failed to update Langfuse trace metadata/score: {ex}")

                    if gen_ctx:
                        gen_ctx.__exit__(None, None, None)

                    if lf_client:
                        await asyncio.sleep(0.5)
                        lf_client.flush()

        except Exception as e:
            if "Assert" in type(e).__name__ or isinstance(e, AssertionError):
                  answer = f"Generated answer could not be verified against sources.\nError: {e}"
                  verified = False
            else:
                  answer = f"Error generating answer: {e}"
                  verified = False

    tf = time.perf_counter()
    print(f"[TIMING] Total request: {tf-t0:.3f}s")
    
    if "Verification Failed:" in answer:
        verified = False
        
    if evidence_objects:
        print(f"DEBUG: First Evidence Item Entities: {evidence_objects[0].entities}")
    
    final_citations = [ev.citation for ev in evidence_objects]

    return SearchResponse(
        answer=answer,
        citations=final_citations,
        evidence=evidence_objects,
        verified=verified,
        unverified_sentence_ids=unverified_sentence_ids,
        refused=locals().get("refused", False),
        reasoning=locals().get("reasoning_text", None),
        partial_match_sids=locals().get("partial_match_sids", []),
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

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "goat-yard-archive"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
