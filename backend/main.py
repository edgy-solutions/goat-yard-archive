
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
from .query_expansion import expand_query, init_vector_thesaurus
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

# ---------------------------------------------------------------------------
# BAML output sentinel (ADR-0008 step 2b/2c).
#
# Three STRUCTURAL signals catch BAML punts that the prompt-prevention work
# in step 2a doesn't already foreclose. They trip the fallback by raising;
# the except block downstream then applies the dedup-only entity fallback
# (step 2d).
#
# A separate pair of LEXICAL regexes is kept as diagnostic logging ONLY — they
# never trip the sentinel. Maintaining a growing regex allowlist of bad
# phrasings is the symptom-chasing treadmill the ADR explicitly rejects;
# refining the prompt (step 2a) is what closes the gap, not adding regexes.
# ---------------------------------------------------------------------------
_QUERY_STOPWORDS = frozenset({
    "the","of","a","an","is","are","was","were","be","been","being",
    "what","who","whom","whose","when","where","why","how","which",
    "does","did","do","done","has","have","had","can","could","would",
    "should","may","might","will","shall",
    "about","in","on","at","for","to","from","with","by","as","into",
    "and","or","but","not","no","so","then","than","that","this","these","those",
    "i","you","he","she","it","we","they","me","him","her","us","them",
    "my","your","his","its","our","their",
    "tell","say","said","says",
})

_BAML_LEXICAL_DIAG_IMPERATIVE = re.compile(
    r"\b(please|could you|kindly|can you)\s+\w{0,15}\s*"
    r"(provide|share|specify|clarify|give|tell|let me know)\b",
    re.IGNORECASE,
)
_BAML_LEXICAL_DIAG_META = re.compile(
    r"\b("
    r"search\s+terms?|your\s+query|you\s+wish\s+to|you\s+want\s+to|"
    r"theological\s+synonyms|18th[-\s]century\s+synonyms|"
    r"the\s+modern\s+terms?|provide\s+the\s+modern"
    r")\b",
    re.IGNORECASE,
)


def _query_content_tokens(query: str) -> set:
    """Lowercased alphabetic-leading tokens of length >= 2 with stopwords
    removed. Used by the structural sentinel's query-terms-present check
    (the workhorse signal). Reliable ONLY when the BAML prompt mandates
    input-echo (ADR-0008 step 2a) — pre-echo, an expansion lacking the
    query is not necessarily a punt."""
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9]+", (query or "").lower())
    return {t for t in tokens if len(t) >= 2 and t not in _QUERY_STOPWORDS}


def _baml_output_punt_reasons(
    *,
    user_query: str,
    expansion: str,
    given_entities,
    returned_entities,
):
    """Return a list of structural-signal names that classify the BAML
    output as a punt. Empty list means accept the output. Lexical
    diagnostics are logged as a side effect but never appended to the
    returned list."""
    reasons = []

    if not (expansion or "").strip():
        reasons.append("empty_expansion")

    qtoks = _query_content_tokens(user_query)
    if qtoks:
        exp_lower = (expansion or "").lower()
        if not any(t in exp_lower for t in qtoks):
            reasons.append("no_query_terms_present")

    if given_entities and not returned_entities:
        reasons.append("entities_given_none_returned")

    diag_hits = []
    if _BAML_LEXICAL_DIAG_IMPERATIVE.search(expansion or ""):
        diag_hits.append("imperative_pattern")
    if _BAML_LEXICAL_DIAG_META.search(expansion or ""):
        diag_hits.append("meta_vocab")
    if diag_hits:
        print(
            f"[BAML LEXICAL DIAG] log-only, not tripping: hits={diag_hits} "
            f"user_query={user_query!r} expansion={(expansion or '')[:200]!r}"
        )

    return reasons


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

    # 1b. Vector thesaurus (ADR-0011 v2). Precompute embeddings for each
    #     narrow-vocabulary key so per-query expansion is one embed call +
    #     N in-memory cosine distances. Failure here degrades gracefully
    #     to exact-only matching — the pre-v2 behavior — not a request-
    #     path crash.
    try:
        if search_engine is not None:
            await init_vector_thesaurus(search_engine._get_embedding)
        else:
            print("[EXPANSION INIT] search engine unavailable; vector tier disabled")
    except Exception as e:
        print(f"[EXPANSION INIT] failed: {e}; vector tier disabled")

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
    # When True, response includes a `stages` dict with per-stage I/O captures
    # (BAML expansion, embedding hash, retrieved chunk SIDs, bot raw answer)
    # so the determinism harness can pinpoint which stage flips between runs.
    debug: bool = False

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
    # Per-stage I/O snapshot, populated only when request.debug=True. Used by
    # evals/determinism_harness.py to compare stage outputs across runs and
    # isolate which stage introduces variance.
    stages: Optional[dict] = None

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

    # Per-stage capture for the determinism harness — only populated when
    # req.debug=True so production traffic is unaffected.
    stages_capture: Optional[dict] = {} if req.debug else None
    if stages_capture is not None:
        stages_capture["question"] = req.query

    # 1. Optimize and Expand Query (Enterprise Search Upgrade)
    # 1a. Narrow-vocabulary expansion (ADR-0011 v2, 2026-07-12). Bridges
    #     Reformed-tradition terms that qwen3-embedding does not associate
    #     with Gill's anchor entities. Two-tier: exact regex first
    #     (deterministic, cheapest), then cosine-distance vector match at
    #     <=0.15 for typos/inflections/reorderings (E-8.1 derived). The
    #     v1 exact-only design cliffed on a single-char typo — 'exlusive
    #     psalmody' -> drought. v2 removes that cliff for typos; near-
    #     misses (0.15 < d <= 0.40) are logged for observability so
    #     paraphrases traffic actually uses can be promoted to explicit
    #     thesaurus entries over time. The expanded form is used ONLY for
    #     entity lookup; BAML still sees the raw user query.
    lookup_query, expansion_matches, expansion_near_misses, _thesaurus_vector_degraded = await expand_query(
        req.query,
        embed_fn=search_engine._get_embedding if search_engine is not None else None,
    )
    if expansion_matches:
        print(f"[EXPANSION] matched narrow terms: {expansion_matches}")
        print(f"[EXPANSION] lookup query: {lookup_query!r}")
    if expansion_near_misses:
        print(f"[EXPANSION] near-misses (log-only, no expansion): {expansion_near_misses}")
    if stages_capture is not None:
        stages_capture["expansion_matches"] = expansion_matches
        stages_capture["expansion_near_misses"] = expansion_near_misses
        stages_capture["lookup_query"] = lookup_query

    t1 = time.perf_counter()
    available_entity_names, entity_lookup_mode = await search_engine.get_relevant_entities(query=lookup_query)
    t2 = time.perf_counter()
    print(f"[TIMING] get_relevant_entities: {t2-t1:.3f}s")
    # ADR-0014: fold thesaurus vector-tier degradation into the overall
    # mode. The thesaurus and entity vector tiers share the litellm
    # dependency; either degrading means the manifest was built without
    # full vector anchoring, so the boost must be suppressed. Catches the
    # transient-blip case where the thesaurus embed failed but the entity
    # embed succeeded (entity mode would read "full" on its own).
    if _thesaurus_vector_degraded and entity_lookup_mode == "full":
        entity_lookup_mode = "degraded_no_vector"
        print("[ENTITY LOOKUP] thesaurus vector tier degraded -> marking request degraded (ADR-0014)")
    if entity_lookup_mode != "full":
        print(f"[ENTITY LOOKUP] mode={entity_lookup_mode} — entity boost will be suppressed (ADR-0014 fail-anchored)")
    if stages_capture is not None:
        stages_capture["available_entities"] = sorted(available_entity_names) if available_entity_names else []
        stages_capture["entity_lookup_mode"] = entity_lookup_mode
    
    # Track punt reasons across the try/except so the fallback can
    # dispatch on which sentinel signal fired (ADR-0012 poisoned-manifest
    # suppression vs dedup-only fallback).
    _punt_reasons: list[str] = []
    # Entity-boost telemetry, populated in the BAML-success path. Defaults
    # cover the punt/exception paths where BAML produced no usable pick.
    entity_boost_telemetry: dict = {
        "entity_lookup_count": len(available_entity_names or []),
        "entity_baml_pick_count": 0,
        "entity_baml_dropped_count": 0,
        "entity_baml_dropped": [],
    }
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

        # Structural sentinel (ADR-0008 step 2b). Three signals catch BAML
        # punts the 2a prompt-prevention didn't already foreclose. Tripping
        # routes to the fallback in the except block (see ADR-0012 for
        # the punt-reason-based dispatch).
        _punt_reasons = _baml_output_punt_reasons(
            user_query=req.query,
            expansion=search_text,
            given_entities=list(available_entity_names or []),
            returned_entities=list(mapped_entities or []),
        )
        if _punt_reasons:
            print(
                f"[BAML SENTINEL] Output classified as punt: reasons={_punt_reasons} "
                f"user_query={req.query!r} expansion={(search_text or '')[:300]!r} "
                f"returned_entities={mapped_entities!r}"
            )
            if stages_capture is not None:
                stages_capture["baml_punt_reasons"] = _punt_reasons
            raise ValueError(f"BAML output structurally punted: {_punt_reasons}")

        # ADR-0013 Part A: two-pass entity lookup. Always runs when
        # BAML's expansion differs from the raw query. The substring-
        # noise regression that led to the 2026-07-13 hotfix has been
        # fixed at the source (get_relevant_entities length-5 floor),
        # so the two-pass no longer surfaces book-of-X flood from
        # common English tokens in BAML's paraphrase. The conditional
        # gating "only run when thesaurus missed" that the hotfix
        # introduced has been removed — it was a workaround for the
        # substring bug and is not justified on its own merits.
        second_pass_entities: list[str] = []
        try:
            if search_text and search_text.strip() and search_text.strip() != req.query.strip():
                _tp0 = time.perf_counter()
                second_pass_entities, _second_pass_mode = await search_engine.get_relevant_entities(query=search_text)
                _tp1 = time.perf_counter()
                print(f"[TIMING] two-pass entity lookup: {_tp1-_tp0:.3f}s")
                print(f"[TWO-PASS] baml_expansion manifest: {second_pass_entities}")
                # If EITHER lookup degraded, the whole manifest is untrustworthy.
                if _second_pass_mode != "full":
                    entity_lookup_mode = _second_pass_mode
        except Exception as _tp_err:
            print(f"[TWO-PASS] second-pass entity lookup failed: {_tp_err}")

        # ADR-0013 Part C (2026-07-13): anchor the entity boost on the
        # RAW MANIFEST, not on BAML's picks.
        #
        # BAML's `official_entities` is a lossy, non-deterministic filter
        # over the candidate manifest. Using it as the SOLE source for
        # the entity boost means any entity BAML fails to echo is lost —
        # even one the thesaurus deliberately surfaced. The 2026-07-13
        # psalmist incident: the raw manifest correctly contained the
        # English `Hallel` entity (which MATTHEW 26:30 is linked to,
        # surfaced by the thesaurus anchor tokens), but BAML's pick
        # dropped it and kept only the Hebrew form. Result: MATT 26:30
        # lost its entities^3 boost and fell out of retrieval entirely —
        # a drought, non-deterministically, on the exact query the
        # thesaurus fix was built for.
        #
        # Fix: union THREE sources, raw manifest first (highest signal —
        # it's what get_relevant_entities found on the thesaurus-anchored
        # lookup_query), then BAML's canonicalized picks (may add
        # canonical names), then second-pass concept recall. No single
        # lossy stage can now discard a load-bearing entity. All three
        # are individually cap-bounded (MANIFEST_TOTAL_CAP=5 each), so
        # the union stays small — no return to the pre-ADR-0010 flood.
        # Telemetry: capture what BAML's raw pick would have dropped from
        # the deterministic manifest, BEFORE the Part C union recovers it.
        # Logged to Langfuse on every request (not just debug) so this
        # stage boundary is permanently visible — the counter-move to the
        # "invisible since May" pattern (substring flood, this drop, the
        # dead rag-diagnostic were all silent because a boundary logged
        # only one side). If a future change reintroduces a subtractive
        # path, entity_baml_dropped_count stops being 0 and shows up.
        _baml_raw_pick = set((n or "").strip().lower() for n in (mapped_entities or []))
        _lookup_set = set((n or "").strip().lower() for n in (available_entity_names or []))
        _sp_set = set((n or "").strip().lower() for n in (second_pass_entities or []))
        _dropped_by_baml = _lookup_set - _baml_raw_pick - _sp_set
        entity_boost_telemetry = {
            "entity_lookup_count": len(_lookup_set),
            "entity_baml_pick_count": len(_baml_raw_pick),
            "entity_baml_dropped_count": len(_dropped_by_baml),
            "entity_baml_dropped": sorted(_dropped_by_baml),
        }

        _seen_union: set[str] = set()
        _union: list[str] = []
        for _name in (
            list(available_entity_names or [])
            + list(mapped_entities or [])
            + list(second_pass_entities or [])
        ):
            _key_l = (_name or "").strip().lower()
            if _key_l and _key_l not in _seen_union:
                _seen_union.add(_key_l)
                _union.append(_name)
        mapped_entities = _union if _union else mapped_entities

        if stages_capture is not None:
            stages_capture["baml_expansion"] = search_text
            stages_capture["baml_entities"] = sorted(mapped_entities) if mapped_entities else []
            stages_capture["second_pass_entities"] = sorted(second_pass_entities) if second_pass_entities else []
            stages_capture["entity_boost_telemetry"] = entity_boost_telemetry
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        print(f"BAML Optimization failed, falling back to raw query:\n{error_msg}")
        search_text = req.query

        # ADR-0012 punt-reason-based fallback dispatch, REFINED 2026-07-13
        # (ADR-0013 Part D) to respect the thesaurus-fired signal.
        #
        # Case A — `entities_given_none_returned`:
        #     BAML returned zero entities from the manifest it was handed.
        #     ADR-0012 originally read this as "manifest is poison ->
        #     suppress boost." But the entity-drop telemetry disconfirmed
        #     the premise: BAML punts `entities_given_none_returned` even
        #     on GOOD manifests (the 'exclusive psalmody' / 'exclusive
        #     psalmist' case punts on a manifest containing Hallel,
        #     passover, Book of Psalms). The punt is a gemma coin-flip,
        #     not reliable evidence about manifest quality.
        #
        #     Dispatch on the DETERMINISTIC signal instead:
        #       A1 — thesaurus fired (expansion_matches non-empty): the
        #            manifest was built from an anchored lookup_query and
        #            is trustworthy. BAML's punt may NOT veto it (same
        #            principle as Part C: a stochastic component may not
        #            subtract from a deterministic anchored manifest).
        #            Boost on the raw manifest.
        #       A2 — thesaurus droughted (expansion_matches empty) AND
        #            BAML rejected: genuine poison risk (the 'means of
        #            grace' -> [covenant of grace, dew of heaven, ...]
        #            lexical-noise case). Suppress the boost, ADR-0012
        #            behavior preserved for the case it was built for.
        #
        # Case B — other punts (empty_expansion, no_query_terms_present)
        #     or a raw BAML exception: manifest may be fine, only the
        #     rewrite failed. Dedup-only fallback (ADR-0008 step 2d).
        if "entities_given_none_returned" in _punt_reasons:
            if expansion_matches:
                # A1 — anchored manifest, trust it despite BAML's punt.
                _seen, _deduped = set(), []
                for _e_name in (available_entity_names or []):
                    _key = _e_name.strip().lower()
                    if _key and _key not in _seen:
                        _seen.add(_key)
                        _deduped.append(_e_name)
                mapped_entities = _deduped if _deduped else None
                fallback_kind = "anchored_manifest_trusted"
                print(
                    "[BAML FALLBACK] entities_given_none_returned BUT thesaurus "
                    f"fired ({len(expansion_matches)} match) -> trusting anchored "
                    f"manifest (ADR-0013 Part D): {mapped_entities}"
                )
            else:
                # A2 — genuine poison risk, suppress (ADR-0012 preserved).
                mapped_entities = []
                fallback_kind = "poisoned_manifest_suppressed"
                print(
                    "[BAML FALLBACK] entities_given_none_returned + thesaurus "
                    "droughted -> suppressing entity boost (ADR-0012). Retrieval "
                    "runs on hybrid BM25+vector alone with no entity anchor."
                )
        else:
            # Dedup-only fallback (ADR-0008 step 2d). The per-query relevant
            # entity set returned by get_relevant_entities is already filtered
            # for this query by BM25 — what we strip is the case-insensitive
            # duplicates the lookup produces (Peter x2, Jona x2, Book of Psalms
            # x2 etc., observed pre-launch). NOT a global manifest dump — the
            # 2026-06-21 universal_atonement amplification was that pathology.
            _seen, _deduped = set(), []
            for _e_name in (available_entity_names or []):
                _key = _e_name.strip().lower()
                if _key and _key not in _seen:
                    _seen.add(_key)
                    _deduped.append(_e_name)
            mapped_entities = _deduped if _deduped else None
            fallback_kind = "dedup_only"

        if stages_capture is not None:
            stages_capture["baml_expansion"] = None
            stages_capture["baml_entities"] = sorted(mapped_entities) if mapped_entities else []
            stages_capture["baml_error"] = str(e)
            stages_capture["baml_fallback"] = fallback_kind

    # ADR-0014 fail-anchored gate. If the entity lookup degraded (vector
    # tier / litellm enrichment infra down for that call), the manifest —
    # whatever Part C/D/ADR-0012 produced from it — is untrustworthy: it is
    # the substring/BM25-only manifest that E-9/E-11 proved is materially
    # different and worse (ceremonial-homonym collapse). Design law: never
    # fail different. Suppress the entity boost entirely and retrieve on the
    # deterministic floor (raw query + BAML expansion hybrid, no entity
    # anchor). This OVERRIDES every upstream boost decision because they all
    # trusted a manifest built by a tier that wasn't running.
    #
    # Note: a FULL litellm outage fails the request closed one line below,
    # because search_gill's own query embedding is load-bearing and raises.
    # This gate only affects the transient-blip window where the entity-tier
    # embedding failed but search_gill's succeeds — exactly the window that
    # produced the 2026-07 manifest bimodality.
    if entity_lookup_mode != "full":
        mapped_entities = []
        if stages_capture is not None:
            stages_capture["baml_fallback"] = "vector_tier_degraded_suppressed"
        print("[ADR-0014] entity lookup degraded -> entity boost suppressed; "
              "retrieval on deterministic floor (raw + expansion, no boost).")

    # 2. Retrieve Evidence
    t5 = time.perf_counter()
    retrieval_debug: dict = {}
    raw_results = await search_engine.search_gill(
        query=search_text,
        entities=mapped_entities,
        limit=12,
        volume_filter=req.volume_limit,
        original_query=req.query,
        _debug_capture=retrieval_debug if stages_capture is not None else None,
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

    if stages_capture is not None:
        stages_capture["embedding_input"] = retrieval_debug.get("embedding_input")
        stages_capture["enhanced_query"] = retrieval_debug.get("enhanced_query")
        stages_capture["embedding_hash"] = retrieval_debug.get("embedding_hash")
        stages_capture["embedding_first_5"] = retrieval_debug.get("embedding_first_5")
        stages_capture["embedding_len"] = retrieval_debug.get("embedding_len")
        # Retrieved chunk SIDs in two views: sorted (set equality) and ordered
        # (sequence equality — catches "same chunks, different ranking").
        all_sids_ordered = []
        all_sids_set = set()
        for r in raw_results:
            for sd in (r.get("sentence_data") or []):
                sid = sd.get("sentence_id") if isinstance(sd, dict) else None
                if sid:
                    all_sids_ordered.append(sid)
                    all_sids_set.add(sid)
        stages_capture["retrieval_sids_set"] = sorted(all_sids_set)
        stages_capture["retrieval_sids_ordered"] = all_sids_ordered
        stages_capture["retrieval_chunk_ids_ordered"] = [r.get("chunk_id", "") for r in raw_results]

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
                        metadata={
                            "volume_limit": req.volume_limit,
                            # Commit SHA baked in at build time (Dockerfile
                            # ARG). The daily Zone-3 judge sampler reads
                            # this to name which build generated the
                            # traffic it's judging. Permanent protection
                            # against the stale-prod trap.
                            "commit_sha": os.getenv("COMMIT_SHA", "unknown"),
                            # ADR-0011 v2 expansion trace. Each entry is
                            # {term, method, distance} — method is 'exact'
                            # or 'vector', distance is 0.0 for exact and
                            # cosine distance for vector. Near-misses are
                            # log-only paraphrase-shape queries in the
                            # observability window used to grow the
                            # thesaurus from real traffic.
                            "query_expansion_matches": expansion_matches,
                            "query_expansion_near_misses": expansion_near_misses,
                        },
                        as_type="generation"
                    )
                    generation = gen_ctx.__enter__()
                    if generation:
                        generation.update(input=req.query)
                        lf_client.update_current_trace(
                            user_id=user_id,
                            metadata={
                                "commit_sha": os.getenv("COMMIT_SHA", "unknown"),
                                "query_expansion_matches": expansion_matches,
                                "query_expansion_near_misses": expansion_near_misses,
                                # Entity-boost boundary telemetry (ADR-0013).
                                # entity_baml_dropped_count > 0 means BAML's
                                # pick dropped a lookup entity that Part C
                                # then recovered — a live count of how often
                                # the lossy filter fires, visible per trace.
                                "entity_lookup_count": entity_boost_telemetry["entity_lookup_count"],
                                "entity_baml_dropped_count": entity_boost_telemetry["entity_baml_dropped_count"],
                                "entity_baml_dropped": entity_boost_telemetry["entity_baml_dropped"],
                                # ADR-0014 fail-anchored mode. "full" on a
                                # healthy request; "degraded_no_vector" when
                                # the entity vector tier's embedding failed
                                # (litellm enrichment blip) and the boost was
                                # suppressed. Surfaced in the daily Slack
                                # count so an infra blip announces itself.
                                "entity_lookup_mode": entity_lookup_mode,
                            },
                        )
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
                    if stages_capture is not None:
                        stages_capture["bot_raw_answer"] = getattr(pred, "raw_answer", None) or pred.answer
                        stages_capture["bot_final_answer"] = pred.answer
                        stages_capture["bot_citations"] = sorted(pred.citations) if pred.citations else []
                        stages_capture["bot_reasoning"] = getattr(pred, "reasoning", "") or ""
                        # Zone-3 sweep observability (ADR-0008 Phase 1 Step 4).
                        # Records surface via debug=True so the daily diagnostic
                        # + Step 5 semantic judge can measure lexical excision
                        # rates alongside their own outputs.
                        stages_capture["zone3_excisions"] = getattr(pred, "zone3_excisions", None) or []
                        stages_capture["bot_pre_sweep_answer"] = getattr(pred, "pre_zone3_sweep_answer", None)
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
                        # Zone-3 sweep observability (ADR-0008 Phase 1 Steps 4
                        # + 5b). The daily Zone-3 judge sampler reads these
                        # counts alongside the answer text so amendment
                        # excisions become measurable on real traffic — the
                        # validation state-drift smoke can't produce.
                        z3_excisions = getattr(pred, "zone3_excisions", None) or []
                        n_trailing = sum(
                            1 for e in z3_excisions
                            if e.get("action") == "trailing_prose_excised"
                        )
                        n_disclaimer_preserved = sum(
                            1 for e in z3_excisions
                            if e.get("action") == "template_replaced"
                            and "does not use" in (e.get("replacement") or "").lower()
                        )
                        n_other_excised = len(z3_excisions) - n_trailing - n_disclaimer_preserved
                        generation.update(
                            output=answer,
                            metadata={
                                "zone3_excision_count": len(z3_excisions),
                                "zone3_trailing_prose_excised": n_trailing,
                                "zone3_disclaimer_preserved": n_disclaimer_preserved,
                                "zone3_other_excised": n_other_excised,
                            },
                        )
                    
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
                                    # corpus fingerprint: which corpus version served this trace. The
                                    # ingestion SHA is the cheap per-request marker; the full content hash
                                    # + prod/test in-sync check ride the daily Slack report (fingerprint_rest).
                                    "corpus_ingestion_sha": os.getenv("INGESTION_SHA", "unstamped"),
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
        trace_id=trace_id if 'trace_id' in locals() else None,
        stages=stages_capture,
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
