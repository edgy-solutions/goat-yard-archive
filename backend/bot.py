
import dspy
import re
from typing import List, Dict, Optional, Tuple

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

# Matches `"quoted text" ...up to 80 chars... [SENTENCE_ID]`.
#
# The GillSignature contract asks the model to place the Sentence ID
# immediately after the closing quote, but the model legitimately writes
# things like `"verbatim phrase" explanatory framing [SID]` and we don't
# want the verifier to lose the pair because of a few words of narration.
#
# The intervening gap excludes:
#   - quote chars (`"` / `“` / `”`) — to avoid pairing across two quotes
#   - newlines — quote-cite pairs shouldn't span paragraph breaks
#   - `[` and `]` — so we can't accidentally jump over an unrelated bracket
#     (e.g. `[work]`-style clarifications or another sentence ID earlier
#     in the line) and pair with a citation further down the answer
#
# If we ever see the model attaching real Gill quotes to citations *more
# than 80 chars away*, we'd revisit the limit. For now this catches the
# legitimate-quote-with-inline-explanation pattern without inviting
# silent mis-pairing.
QUOTE_WITH_CITE_RE = re.compile(
    r'["“”]([^"“”]+)["“”][^"“”\n\[\]]{0,80}\[([A-Z0-9_]+_S\d+)\]'
)

# Tokens we strip during normalization.
_ITALICS_RE = re.compile(r"\*([^*]+)\*")
_FOOTNOTE_REF_RE = re.compile(r"\[\^[A-Za-z0-9_]+\]")
_WHITESPACE_RE = re.compile(r"\s+")
# Anything that isn't a Unicode letter or digit is treated as a word boundary.
# Hyphens, punctuation, curly quotes, brackets, etc. all collapse to spaces so
# that "scape-goat" and "scapegoat" normalize the same way, and ":" vs ";" vs ","
# stop being a verification failure.
_NON_WORD_RE = re.compile(r"[^\w\s]", re.UNICODE)


def _normalize_for_quote_match(text: str) -> str:
    """Make the quoted text and the source text comparable.

    The goal is to verify that the model isn't paraphrasing while putting
    quote marks around its paraphrase. Differences that are NOT paraphrase —
    punctuation, hyphenation, italics, footnote refs, curly vs straight
    quotes — should not cause verification failures.

    Normalization steps:
    - Strip markdown italics markers (`*x*` -> `x`) and underscores.
    - Strip `[^N]` footnote refs entirely.
    - Lowercase (Gill's capitalization is meaningful for display, not for
      identifying which sentence the model is quoting from).
    - Replace ALL punctuation (and hyphens) with whitespace. This deliberately
      collapses `:`/`;`/`,`, `scape-goat`/`scapegoat`, and any KJV vs Gill
      punctuation variations. The model regularly switches between these
      without changing the words; word content is what we verify.
    - Collapse whitespace runs to a single space and strip leading/trailing
      whitespace.
    """
    if not text:
        return ""
    s = text
    s = _ITALICS_RE.sub(r"\1", s)
    s = s.replace("_", " ")
    s = _FOOTNOTE_REF_RE.sub("", s)
    s = s.lower()
    s = _NON_WORD_RE.sub(" ", s)
    s = _WHITESPACE_RE.sub(" ", s).strip()
    return s


def _build_chunks_by_sid(context_chunks: List[dict]) -> Dict[str, Dict[str, str]]:
    """Build {sentence_id_in_brackets: {"gill": ..., "kjv": ...}} from chunks.

    Sources are kept separate so verification can track quote provenance:

    - "gill": all sentence_data texts in the chunk, concatenated. This is the
      portion that's authored by Gill (his commentary on the verse).
    - "kjv": the KJV scripture text for the chunk's verse_ref, if any.

    Why separated:
    The faithfulness contract is "every Gill citation needs at least one
    verbatim Gill quote attached." KJV quotes inside quotation marks are
    welcome on their own merits, but they don't substitute for actually
    quoting Gill when his sentence ID is cited. By tracking which source a
    matched quote came from, we can fail an answer that only attaches KJV
    quotes (or no quotes at all) to a Gill citation — Gill ends up
    summarized rather than quoted, which is what the verifier is for.

    Why the chunk's full Gill text (not just one sentence):
    The model legitimately stitches quotes across consecutive sentences of
    the same chunk, so per-sentence verification produces false positives.
    """
    out: Dict[str, Dict[str, str]] = {}
    for chunk in context_chunks:
        verse_ref = chunk.get("verse_ref", "")
        kjv = ""
        try:
            scripture = KJV_DATA.get(verse_ref) if verse_ref else None
            if scripture:
                kjv = scripture
        except Exception:
            pass

        gill_parts: List[str] = []
        sentence_ids: List[str] = []
        for sent in (chunk.get("sentence_data") or []):
            sid = sent.get("sentence_id")
            text = sent.get("text") or ""
            if sid:
                sentence_ids.append(f"[{sid}]")
            if text:
                gill_parts.append(text)
        # Fallback to the chunk's combined `content` if sentence_data is missing.
        if not sentence_ids and chunk.get("content"):
            gill_parts.append(chunk["content"])
        gill = " ".join(gill_parts)

        for sid_bracketed in sentence_ids:
            out[sid_bracketed] = {"gill": gill, "kjv": kjv}
    return out


# Permissive sid extractor used post-verification to find all Gill citations
# in the answer text — including those NOT attached to a quote — so we can
# enforce "every cited SID has at least one Gill quote attached."
_ANY_CITE_RE = re.compile(r'\[([A-Z0-9_]+_S\d+)\]')


_ELLIPSIS_RE = re.compile(r"\.{3,}|…")
_BRACKETED_RE = re.compile(r"\[[^\]]*\]")
_PARENTHESIZED_RE = re.compile(r"\([^)]*\)")


def _try_repair_quote_difflib(quote_raw: str, source_text: str, min_coverage: float = 0.5) -> Optional[str]:
    """Fast deterministic quote repair using difflib's longest-common-subsequence.

    Returns the verbatim source span the model was paraphrasing, if confidence is
    high enough. None if the alignment isn't clear and we should leave the case
    for the LLM fallback (or `verified=False`).

    Algorithm:
    1. Find matching blocks between quote and source via SequenceMatcher.
    2. Filter out trivially-short matches (< 8 chars).
    3. If matched characters cover >= `min_coverage` of the quote, take the
       source span from the start of the first matching block to the end of
       the last — this captures "what the model was paraphrasing", verbatim.
    4. Sanity-check length: between 30% and 250% of the original quote length.
    """
    if not quote_raw or not source_text:
        return None
    from difflib import SequenceMatcher

    source_lower = source_text.lower()
    quote_lower = quote_raw.lower()

    # Compare against source (a) and quote (b) so matching-block .a indices are
    # source positions — we'll splice from the raw source for verbatim output.
    matcher = SequenceMatcher(None, source_lower, quote_lower, autojunk=False)
    blocks = [b for b in matcher.get_matching_blocks() if b.size >= 8]
    if not blocks:
        return None

    matched_chars = sum(b.size for b in blocks)
    if matched_chars / len(quote_lower) < min_coverage:
        return None

    blocks.sort(key=lambda b: b.a)
    source_start = blocks[0].a
    source_end = blocks[-1].a + blocks[-1].size
    repaired = source_text[source_start:source_end]

    # Length sanity: don't claim a repair that's wildly off from the model's
    # intended span.
    if not (0.3 * len(quote_raw) <= len(repaired) <= 2.5 * len(quote_raw)):
        return None

    # Defensive: extracted-from-source so this should always pass; included
    # because boundary-case bugs would otherwise silently substitute hallucination.
    if repaired not in source_text:
        return None

    return repaired


def _try_repair_quote_llm(quote_raw: str, source_text: str) -> Optional[str]:
    """LLM fallback for ambiguous quote repairs that difflib couldn't resolve.

    Calls BAML's RepairQuote on the LocalRouter (fast local model). Verifies the
    LLM's proposed repair is actually a substring of the source before accepting
    — if the LLM hallucinated, we discard. Returns the verbatim source substring
    or None.
    """
    try:
        # Local import to avoid circular import at module load.
        from baml_client.sync_client import b
        result = b.RepairQuote(model_quote=quote_raw, source_text=source_text)
        repaired = result.repaired_quote
        if not repaired:
            return None
        # Defensive: the LLM might hallucinate; require the proposed repair to
        # actually be present in the source text.
        if repaired not in source_text:
            return None
        return repaired
    except Exception as e:
        print(f"DEBUG: BAML RepairQuote failed: {e}")
        return None


def _repair_quotes_in_answer(
    answer: str, chunks_by_sid: Dict[str, Dict[str, str]]
) -> Tuple[str, List[dict], List[dict]]:
    """Hybrid quote repair + provenance-aware verification.

    Per quote match `"text" [SID]`:
      1. Try to match against Gill commentary (sources["gill"]) — if it lands,
         the SID has been "satisfied" by a Gill quote.
      2. Else try to match against KJV (sources["kjv"]) — the quote is valid
         (KJV is welcome) but doesn't satisfy the SID's Gill-quote obligation.
      3. Else try difflib/LLM repair against the combined source; if the
         repaired span lands in Gill text, that satisfies the SID.
      4. Else: quote_not_verbatim failure.

    After all quote/cite pairs are processed, scan the answer for any [SID]
    references (with or without an attached quote) and check: every cited
    Gill SID must have at least one Gill-side quote attached. If not, emit
    a no_gill_quote_for_citation failure — Gill was summarized, not quoted.

    Returns (repaired_answer, repairs, failures).
    """
    repairs: List[dict] = []
    failures: List[dict] = []
    sids_with_gill_quote: set[str] = set()

    def _replace(match: "re.Match[str]") -> str:
        quote_raw = match.group(1)
        sid = f"[{match.group(2)}]"
        sources = chunks_by_sid.get(sid)
        if sources is None:
            failures.append({
                "quote": quote_raw[:120],
                "sentence_id": sid,
                "reason": "cited_sid_not_in_context",
            })
            return match.group(0)

        gill_src = sources.get("gill", "")
        kjv_src = sources.get("kjv", "")
        gill_norm = _normalize_for_quote_match(gill_src)
        kjv_norm = _normalize_for_quote_match(kjv_src)

        # 1) Direct Gill match — satisfies the SID's obligation, leave text alone.
        if _quote_in_source(quote_raw, gill_norm):
            sids_with_gill_quote.add(sid)
            return match.group(0)

        # 2) Direct KJV match — valid quote, doesn't satisfy Gill obligation.
        if kjv_norm and _quote_in_source(quote_raw, kjv_norm):
            return match.group(0)

        # 3) Repair against the combined source. Track which half the
        # repaired span actually came from so we know whether to credit it
        # toward the SID's Gill-quote obligation.
        combined = (gill_src + " \n " + kjv_src).strip()
        repaired = _try_repair_quote_difflib(quote_raw, combined)
        repair_source = "difflib" if repaired else None
        if not repaired:
            repaired = _try_repair_quote_llm(quote_raw, combined)
            repair_source = "llm" if repaired else None

        if repaired:
            # Flatten any internal whitespace runs (including newlines from
            # the source chunk text) to a single space. Without this, splicing
            # a repaired span containing a "\n" into the answer produces a
            # stray paragraph break — the frontend splits on "\n" and renders
            # each segment as its own div with margin-bottom, which displays
            # as an orphaned period after a blank line.
            repaired = _WHITESPACE_RE.sub(" ", repaired).strip()
            # Determine provenance of the repaired span. Substring check
            # against the gill source is enough — if the model was
            # paraphrasing a Gill phrase, the repair lands in gill_src; if it
            # was paraphrasing KJV, it lands in kjv_src.
            if repaired and repaired in gill_src:
                sids_with_gill_quote.add(sid)
            repairs.append({
                "quote": quote_raw[:120],
                "repaired": repaired[:120],
                "sentence_id": sid,
                "source": repair_source,
            })
            return match.group(0).replace(quote_raw, repaired, 1)

        failures.append({
            "quote": quote_raw[:120],
            "sentence_id": sid,
            "reason": "quote_not_verbatim",
        })
        return match.group(0)

    repaired_answer = QUOTE_WITH_CITE_RE.sub(_replace, answer)

    # Faithfulness pass: every cited Gill SID needs at least one Gill quote.
    # Catches the failure mode where the model attaches only KJV quotes — or
    # nothing at all — to a Gill citation, summarizing Gill rather than
    # quoting him.
    cited_sids = {f"[{m.group(1)}]" for m in _ANY_CITE_RE.finditer(answer or "")}
    for sid in sorted(cited_sids):
        if sid not in chunks_by_sid:
            # 'cited_sid_not_in_context' was already added above if a quote
            # was attached; bare citations to a non-existent SID we skip
            # because the upstream citation validator already rejects them.
            continue
        if sid in sids_with_gill_quote:
            continue
        failures.append({
            "quote": "",
            "sentence_id": sid,
            "reason": "no_gill_quote_for_citation",
        })

    return repaired_answer, repairs, failures


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

    DISCLAIMED / PARTIAL ANSWERS
    Sometimes Gill addresses the user's topic but does not provide the exact, definitive
    answer the question asks for — he may mention a tradition without endorsing it,
    discuss the question itself without resolving it, cite competing views, or treat the
    surrounding context without committing to the precise point asked. Treat these the
    same as a normal answer: surface what Gill DOES say, with framing that names exactly
    what he doesn't commit to. Do NOT refuse just because Gill is non-committal.

    The shape of a disclaimed answer:
      "Gill does not [commit to / name / specify] X in his own voice. On [verse],
       however, he [notes / cites / mentions] [the relevant content with appropriate
       hedge]: <Gill's verbatim words> [SENTENCE_ID]."

    This pattern applies whenever the retrieved context contains material on the
    question's subject without resolving it definitively — e.g. the corpus mentions a
    tradition, an opposing view, a hypothesis, or a related discussion. Surface that
    material faithfully; do not bury it behind a refusal.

    WHEN TO REFUSE
    Refuse ONLY when the retrieved context truly does not touch the subject at all —
    e.g. the user asks about a doctrine and retrieval returned passages about an
    entirely unrelated person, place, or topic. If Gill discusses the subject — even
    partially, even with disclaimers, even by citing others' views — answer; do not
    refuse. In a genuine refusal case — and only then — reply exactly: "I regret that the
    provided extracts from the Doctor's writings do not appear to address this specific
    inquiry. Could it be that you are looking for something not in the library
    ({available_books})?" and provide an empty citation list.

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
        # Verbatim quote verification + hybrid repair (ADR-0006).
        # ---------------------------------------------------------
        # The GillSignature contract promises that every double-quoted span in
        # the answer appears verbatim in Gill's source. When the model drifts
        # (paraphrases, inserts clarifying words, drops punctuation), the
        # hybrid pipeline tries to recover the verbatim source:
        #
        # 1. Normalization-based substring check (lowercase, punctuation
        #    stripped, hyphens collapsed) — passes the simple cases.
        # 2. difflib repair — finds the source span the model was paraphrasing
        #    when at least 50% of the quote's characters align to source.
        #    Deterministic, ~0ms.
        # 3. LLM repair via BAML's RepairQuote on the LocalRouter — handles
        #    ambiguous cases that difflib can't. ~0.5-1.5s, gated by a
        #    defensive check that the LLM's proposed repair is actually in
        #    the source (rejects hallucinated repairs).
        # 4. Unrepairable cases set quote_failures so main.py can surface
        #    verified=False, but the model's text stays in the answer.
        #
        # The answer text is mutated in place to substitute verbatim source
        # spans for any successfully-repaired quotes — the user sees Gill's
        # actual words rather than the model's drift.
        chunks_by_sid = _build_chunks_by_sid(context_chunks)
        repaired_answer, quote_repairs, quote_failures = _repair_quotes_in_answer(pred.answer, chunks_by_sid)

        if quote_repairs:
            n_difflib = sum(1 for r in quote_repairs if r["source"] == "difflib")
            n_llm = sum(1 for r in quote_repairs if r["source"] == "llm")
            print(f"DEBUG: Quote repairs applied: {len(quote_repairs)} ({n_difflib} difflib, {n_llm} llm)")
            for r in quote_repairs:
                print(f"  {r['sentence_id']}: {r['quote'][:60]!r} -> {r['repaired'][:60]!r} via {r['source']}")
        if quote_failures:
            print(f"DEBUG: Unrepairable quote failures (verified=False): {quote_failures}")

        return dspy.Prediction(
            answer=repaired_answer,
            citations=citations_list,
            quote_failures=quote_failures,
            quote_repairs=quote_repairs,
        )

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
