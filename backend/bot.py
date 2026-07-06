
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

# ---------------------------------------------------------------------------
# Zone-3 post-generation suppression (ADR-0008 Phase 1 Step 4).
#
# SHALLOW RUNTIME BACKSTOP — this function catches Gill-anchored assertive
# and negation forms only. It is DELIBERATELY narrow. Two known gaps are
# NOT patched by this scan; they are the semantic judge's territory
# (ADR-0008 Layer 3, Step 5):
#
#   1. Inference-form Zone 3: "these distinctions suggest Gill...",
#      "this shows Gill...", "the passages imply Gill..." — model's
#      systematizing inference from the quotes. Unbounded surface forms.
#      Regex enumeration would be the growing-allowlist treadmill this
#      project refuses to build (see ADR-0008 Notes / substrate hardening).
#
#   2. Pronoun-anchored Zone 3: "he maintains that...", "he holds the...",
#      "his teaching...". Real prose refers back to Gill with pronouns.
#      Adding (Gill|he) anchors would explode false positives on the KJV
#      "he said unto..." quote language pervasive in the corpus. The gap
#      is documented explicitly and left to the semantic judge.
#
# Rate-report both gaps as leak classes when validating. Do NOT declare
# clean by omission. See ADR-0008 Validation Notes for the mandatory
# rate-reporting format.
# ---------------------------------------------------------------------------

_ZONE3_ASSERTIVE_RE = re.compile(
    r"\bGill\s+("
    r"distinguishes|affirms|holds|teaches|argues|supports|advocates|"
    r"maintains|leans\s+toward|takes\s+the\s+\w+\s+position|believes\s+that"
    r")\b",
    re.IGNORECASE,
)
_ZONE3_POSSESSIVE_RE = re.compile(
    r"\bGill's\s+(view|position|stance|teaching|doctrine|opinion)\s+(of|on)\b",
    re.IGNORECASE,
)
# The single blatant new shape from 2026-07-05 covenant run 2 —
# negation-form Zone 3, a direct inversion of the assertive verbs.
_ZONE3_NEGATION_RE = re.compile(
    r"\bGill\s+does\s+not\s+("
    r"treat|conflate|equate|regard|distinguish|affirm|hold|teach|argue|"
    r"support|advocate|maintain|consider|view"
    r")\b",
    re.IGNORECASE,
)

# Quote-adjacent exemption — a Zone-3 verb IS acceptable when it introduces
# a verified quote within 120 chars (e.g., "Gill distinguishes the sign
# from the substance: 'circumcision was...'" [SID]). Applied uniformly to
# all three patterns.
_QUOTE_AFTER_MATCH_RE = re.compile(
    r'["""].{1,200}?["""][^"""\n\[\]]{0,80}\[[A-Z0-9_]+_S\d+\]'
)


def _suppress_zone3(answer: str) -> Tuple[str, List[dict]]:
    """Post-generation Zone-3 sweep. Returns (cleaned_answer, excised_records).

    Splits the answer paragraph-by-paragraph, then sentence-by-sentence.
    Any sentence matching an assertive-verb, possessive, or negation
    pattern is:

      - Kept (with an "exempted" record) if a verified quote follows the
        match within 120 chars (legitimate Zone-1 introduction of a
        Zone-2 quote — the covenant-flagship shape).
      - Replaced with a neutral template if the sentence was introducing
        content (ends with ':' or is followed by a numbered list or a
        quote). Prevents orphaned "For example..." openings after
        excision. See ADR-0008 Consequences / Negative.
      - Excised outright otherwise.

    See ADR-0008 Validation Notes for the mandatory rate-reporting
    format — this function catches shallow residue only.
    """
    if not answer:
        return answer, []

    paragraphs = re.split(r"(\n\s*\n)", answer)
    excised: List[dict] = []
    out: List[str] = []

    for i, para in enumerate(paragraphs):
        if i % 2 == 1:
            out.append(para)
            continue

        text = para
        working = []
        cursor = 0
        sent_index = 0

        for sentence, sent_end in _iter_sentences(text):
            sentence_end = cursor + sent_end
            cursor = sentence_end
            this_sent_index = sent_index
            sent_index += 1

            trip = _zone3_trip(sentence)
            if not trip:
                working.append(sentence)
                continue

            # Exemption: quote within 120 chars after the match (checked
            # across the whole answer starting from the sentence, not just
            # this paragraph, so that colon-then-list-then-quote structures
            # like the covenant opener land inside the exemption window).
            paragraph_tail = text[sentence_end:]
            downstream = paragraph_tail
            for j in range(i + 1, min(i + 4, len(paragraphs))):
                downstream += paragraphs[j]
            window = (sentence[trip["match_end"]:] + downstream)[:120]
            if _QUOTE_AFTER_MATCH_RE.search(window):
                excised.append({
                    "paragraph_index": i,
                    "pattern": trip["pattern"],
                    "matched": trip["matched"],
                    "sentence": sentence.strip(),
                    "action": "exempted_quote_adjacent",
                })
                working.append(sentence)
                continue

            is_paragraph_opener = (this_sent_index == 0)
            replacement, tail_edit = _template_for_content_introducer(
                sentence, paragraph_tail, paragraphs, i, is_paragraph_opener
            )
            action = "template_replaced" if replacement is not None else "excised"
            excised.append({
                "paragraph_index": i,
                "pattern": trip["pattern"],
                "matched": trip["matched"],
                "sentence": sentence.strip(),
                "action": action,
                "replacement": replacement,
                "tail_edit": tail_edit,
            })
            if replacement is not None:
                working.append(replacement)
            elif tail_edit is not None:
                # Strip an orphaning transition ("For example, " / "Similarly, ")
                # from the immediate next-sentence continuation so the sweep
                # doesn't leave a dangling connective.
                pass  # tail_edit applied below by rewriting cursor position

        assembled = "".join(working)
        # If any excision recorded a tail_edit, apply it to the assembled text
        for rec in excised:
            if rec.get("action") == "excised" and rec.get("tail_edit"):
                assembled = _apply_tail_edit(assembled, rec["tail_edit"])
        out.append(assembled)

    return "".join(out), excised


# Structural bookend enforcement (ADR-0008 Layer 2 amendment 2026-07-06).
#
# The bookend rule in the Step-3 prompt declares that answers end on the
# final verbatim quote + [SID]. This function enforces that as an INVARIANT
# rather than a request: any substantive prose after the final citation is
# trailing editorializing — the empirically-observed site of closer
# violations that route around the lexical assertive/negation sweep
# ("emphasizing its distinctiveness from the old covenant" trailing a
# Matthew 26:28 citation).
#
# Positional, not lexical. Cannot be routed around by rephrasing — any
# closer prose after the final [SID] is excised regardless of its wording.
# Answers with no citations (flat refusals) are left alone.
_LAST_SID_RE = re.compile(r"\[[A-Z0-9_]+_S\d+\]")


def _strip_trailing_prose(answer: str) -> Tuple[str, List[dict]]:
    """Excise substantive prose that follows the final quote-anchoring
    [SID] in the answer. Returns (cleaned_answer, excised_records)."""
    if not answer:
        return answer, []
    matches = list(_LAST_SID_RE.finditer(answer))
    if not matches:
        # No citations at all — flat refusal or similar. Leave alone.
        return answer, []
    last_end = matches[-1].end()
    tail = answer[last_end:]
    # Any 2+ letter alphabetic word after the final [SID] counts as
    # substantive trailing prose. A trailing period, whitespace, or paren
    # alone does not.
    if not re.search(r"[A-Za-z]{2,}", tail):
        return answer, []
    excised_text = tail.rstrip()
    # Retain a single trailing period after the citation for readability.
    cleaned = answer[:last_end] + "."
    return cleaned, [{
        "action": "trailing_prose_excised",
        "pattern": "structural_bookend",
        "matched": "prose after final [SID]",
        "sentence": excised_text[:400],
    }]


def _iter_sentences(paragraph: str):
    """Yield (sentence_with_trailing_ws, end_offset) tuples covering the
    whole paragraph text. Splits on sentence terminators (.!?) followed
    by whitespace, and additionally treats a trailing colon as a
    boundary so a "Gill distinguishes ...:" opener that leads into a
    quote or list is treated as its own sentence rather than continuing
    into whatever follows."""
    if not paragraph:
        return
    boundary_re = re.compile(r"(?<=[.!?:])\s+")
    prev = 0
    for m in boundary_re.finditer(paragraph):
        end = m.end()
        yield paragraph[prev:end], end - prev
        prev = end
    if prev < len(paragraph):
        tail = paragraph[prev:]
        yield tail, len(tail)


def _zone3_trip(sentence: str) -> Optional[dict]:
    for name, pattern in [
        ("assertive", _ZONE3_ASSERTIVE_RE),
        ("possessive", _ZONE3_POSSESSIVE_RE),
        ("negation", _ZONE3_NEGATION_RE),
    ]:
        m = pattern.search(sentence)
        if m:
            return {"pattern": name, "matched": m.group(0), "match_end": m.end()}
    return None


_LIST_LEAD_RE = re.compile(r"^\s*(\d+\.|[-*•])\s+")
_QUOTE_LEAD_RE = re.compile(r"""^\s*["“]""")
# Anachronism-disclaimer + but + Zone-3 clause. The excise-the-whole-sentence
# rule was eating the best Zone-1 behavior the prompt produces (the
# unprompted 'Gill does not use the modern term X' anachronism disclaimer)
# when the model attached a thesis to it with 'but'. Detects the compound
# and preserves the disclaimer clause alone.
_DISCLAIMER_BUT_RE = re.compile(
    r"^\s*(Gill\s+(?:does\s+not|doesn't)\s+(?:use|employ)\s+the\s+"
    r"(?:modern\s+)?(?:term|word|phrase)\s+"
    r"[\"“'‘][^\"”'’]+[\"”'’]"
    r"(?:\s+in\s+[^,]+)?)"
    # Comma may live inside the closing quote (American typography) or
    # outside it (British). Either shape allowed before 'but'.
    r"[,\s]*but\s+",
    re.IGNORECASE,
)
# Orphaning transitions — clauses whose antecedent was excised. If the
# next-content starts with one of these, the transition itself must go
# so the sweep doesn't leave a dangling connective. Applied as a tail
# edit when the surviving prose starts with these words.
_ORPHAN_TRANSITION_RE = re.compile(
    r"^\s*(For example,|Similarly,|Additionally,|Moreover,|Furthermore,|"
    r"Also,|First,|Second,|Third,|Fourth,|Fifth,|Finally,|Notably,|"
    r"Importantly,|In particular,|Specifically,|Consider),?\s+",
    re.IGNORECASE,
)


def _template_for_content_introducer(
    sentence: str,
    paragraph_tail: str,
    paragraphs: List[str],
    para_index: int,
    is_paragraph_opener: bool,
) -> Tuple[Optional[str], Optional[dict]]:
    """Decide how to handle an excised sentence.

    Returns (replacement, tail_edit):
      - (replacement, None): substitute the excised sentence with a neutral
        template lead-in that flows into the surviving content.
      - (None, tail_edit): excise cleanly AND apply the tail_edit dict to
        strip an orphaning transition ("For example, ") from the next
        surviving sentence.
      - (None, None): excise cleanly with no tail edit.
    """
    trimmed = sentence.rstrip()
    trailing_ws = sentence[len(trimmed):]
    ends_with_colon = trimmed.endswith(":")

    # (a0) Disclaimer-but-thesis compound: preserve the disclaimer clause.
    # Highest-priority branch — takes precedence over everything else so the
    # sweep does not eat the unprompted anachronism disclaimer that emerged
    # on covenant and psalmody. Runs BEFORE the next_content-based branches
    # because it's a structural property of the excised sentence itself,
    # independent of what follows.
    m = _DISCLAIMER_BUT_RE.match(sentence)
    if m:
        disclaimer_clause = m.group(1)
        # American typography puts the compound-sentence comma INSIDE the
        # closing quote ("monocovenantal,") — that comma is punctuation from
        # the sentence's structure, not part of the term. Strip it when it
        # appears at the end of the captured disclaimer.
        disclaimer_clause = re.sub(r",(?=[\"”'’]$)", "", disclaimer_clause)
        disclaimer_clause = disclaimer_clause.rstrip(" ,")
        return f"{disclaimer_clause}." + trailing_ws, None

    next_content = paragraph_tail.lstrip()
    if not next_content:
        for j in range(para_index + 1, min(para_index + 4, len(paragraphs))):
            candidate = paragraphs[j].lstrip() if j % 2 == 0 else ""
            if candidate:
                next_content = candidate
                break

    if not next_content:
        return None, None

    # (a) List continuation: neutral list-header template
    if _LIST_LEAD_RE.match(next_content):
        return "Gill's commentary includes the following:" + trailing_ws, None
    # (b) Quote continuation: quote-introduction template
    if _QUOTE_LEAD_RE.match(next_content):
        return "On this passage, Gill writes:" + trailing_ws, None
    # (c) Colon-terminated intro: neutral list-header template
    if ends_with_colon:
        return "Gill's commentary includes the following:" + trailing_ws, None
    # (d) Paragraph opener with more content: prevent "For example..." orphan
    if is_paragraph_opener:
        # If the next content begins with an orphaning transition, strip
        # that transition alongside the excision — cleaner than a template.
        if _ORPHAN_TRANSITION_RE.match(next_content):
            return None, {
                "action": "strip_transition",
                "transition_pattern": _ORPHAN_TRANSITION_RE.pattern,
            }
        # Otherwise substitute a neutral prose-header that flows into the
        # surviving content.
        return "Gill's commentary on this subject includes several relevant passages." + trailing_ws, None
    # (e) Mid-paragraph excision with orphaning transition next: strip it
    if _ORPHAN_TRANSITION_RE.match(next_content):
        return None, {
            "action": "strip_transition",
            "transition_pattern": _ORPHAN_TRANSITION_RE.pattern,
        }
    return None, None


def _apply_tail_edit(assembled: str, tail_edit: dict) -> str:
    """Apply a recorded tail_edit to the assembled paragraph text.
    Currently supports stripping an orphaning transition from the first
    surviving sentence."""
    if tail_edit.get("action") != "strip_transition":
        return assembled
    # Strip the transition from the start of the assembled paragraph (after
    # any leading whitespace).
    stripped = assembled.lstrip()
    lead_ws = assembled[: len(assembled) - len(stripped)]
    m = _ORPHAN_TRANSITION_RE.match(stripped)
    if not m:
        return assembled
    after = stripped[m.end():]
    if after and after[0].islower():
        after = after[0].upper() + after[1:]
    return lead_ws + after


class GillSignature(dspy.Signature):
    """You are a present-day research assistant helping a user explore Dr. John Gill's
    "An Exposition of the Old and New Testaments" (1746-1763). You are NOT Dr. Gill.
    You do NOT speak in his voice, his style, or as his contemporary. You speak in plain
    modern English as a neutral guide. The user must always be able to tell which words
    are Gill's and which are yours: yours are plain modern framing; his are verbatim
    quotations in quotation marks with a Sentence ID.

    ZONES OF VOICE (CRITICAL)
    Your output has three categorically different kinds of content. The core rule:
    you interpret the USER's question. You do NOT interpret Gill. Gill speaks for
    himself through verbatim quotes.

      ZONE 1 — your voice, interpreting the USER'S QUESTION (never Gill).
        ALLOWED, and labeled as yours. The bridge maps the user's modern phrasing
        to where Gill's material lives — NAVIGATIONALLY: where the material is,
        what it concerns. The bridge NEVER predicts what Gill's material will show
        or forecasts the verdict. It points at material; the material speaks.

        Example (PERMITTED — pure navigation):
          "'Monocovenantal' is a modern term Gill doesn't use; his material
           treating the covenant of grace in relation to other covenants follows."

        Example (FORBIDDEN — leading, even though it uses Zone-1 grammar):
          "Your question about monocovenantalism relates to Gill's distinctions
           between covenants."
        The word 'distinctions' has already asserted a Gill position before Gill
        has spoken. That is Zone 3 wearing Zone 1 grammar.

        Zone 1 may acknowledge that a modern term is not Gill's, may identify what
        material follows, and may state a corpus gap in a refusal. It MAY NOT tell
        the reader what to conclude, what Gill holds, or what the quotes will show.

      ZONE 2 — Gill's verbatim words. THE SUBSTANTIVE CONTENT.
        Always inside quotation marks with [SID] immediately after the closing quote.
        Never paraphrase, never modernize, never smooth Gill's English. The framing
        around a quote may orient the reader but may not assert what Gill holds.

      ZONE 3 — your interpretation of Gill. FORBIDDEN. DO NOT EMIT.
        Interpretation of Gill is forbidden AT ALL. Not "forbidden when wrong" —
        forbidden even when accurate. An accurate interpretation of Gill is still
        an interpretation you have supplied, and the reader must reach it from
        Gill's own quoted words, not from you telling them what Gill's words mean.

        Forbidden shapes (any of these is a Zone-3 violation, regardless of
        whether the underlying claim is true):

          (a) Assertive: "Gill distinguishes / affirms / argues / holds / teaches
              / supports / advocates / maintains / leans toward / takes the [X]
              position / believes that / views X as Y / treats X as Y".
          (b) Possessive: "Gill's view / position / stance / teaching / doctrine
              / opinion of X" / "Gill's material addresses X differently from Y".
          (c) Pronoun-anchored (same content, referring to Gill via 'he/his'):
              "he distinguishes / he views / his view / his teaching".
          (d) Inference-headed: "These distinctions suggest Gill..." / "This
              shows Gill..." / "The passages imply Gill..." / "These examples
              illustrate Gill's view of X".
          (e) Label-import: locating Gill relative to a MODERN doctrinal label or
              systematic category appearing in NONE of the retrieved quotes.
              Examples of modern labels: 'monocovenantal', 'supralapsarian',
              'amillennial', 'paedobaptist', 'the regulative principle',
              'compatibilism'. Forbidden shape: "Gill does not take the
              monocovenantal position" — the label mapping is itself an
              interpretation the quotes must supply, not one you supply, and the
              negation form does not exempt it.

        If you cannot answer without interpreting Gill in any of these ways, use
        the informative-refusal mode below. Refusal here does not authorize you
        to slant either.

    BOOKEND RULE (CRITICAL — the empirically-observed violation site)
    Zone 3 violations in this system appear almost exclusively at bookends:
    thesis openers ("Gill distinguishes X from Y in the following ways:") and
    synthesis closers ("These distinctions suggest Gill..." / "This illustrates
    Gill's view of X"). The middle — framing-quote-framing-quote — is
    consistently clean. Two hard rules follow:

      OPENING: the answer opens with the Zone-1 navigational bridge (or with the
        Zone-1 gap statement, for refusals), and nothing else. No opening
        sentence characterizing what Gill holds. No thesis before the first
        quote.

      CLOSING: the answer ends after the final verbatim quote and its [SID]. No
        concluding paragraph. No "these examples illustrate", no "this suggests",
        no "in sum". No synthesis. If you find yourself wanting to summarize what
        the quotes just taught, STOP. That summary is the reader's job.

    The reader closes the loop themselves. That is the entire design of this
    tool: the reader meets Gill, not a summary of Gill.

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

    REPORTED TRADITIONS
    Some questions ask for information (names, dates, places) that Gill addresses
    only by reporting a tradition he mentions without himself endorsing it — most
    commonly a Papist or Jewish tradition, occasionally patristic. Example: the
    question "What were the names of the two thieves?" finds Gill on Luke 23:43
    reporting the Papist tradition naming the penitent thief 'Disma' with a feast
    day on March 25. In these cases, do NOT refuse just because Gill himself
    isn't asserting the claim. Surface the tradition with EXPLICIT attribution
    to its source ("Gill reports the Papist tradition that..." or "Gill does not
    name them himself, but on Luke 23:43 he notes the tradition that..."),
    include the verbatim quote, and provide the citation. The user is better
    served knowing what Gill reports — clearly attributed as tradition rather
    than as Gill's own claim — than getting a refusal that conceals it.

    TWO REFUSAL MODES
    Choose based on what retrieval actually returned, NOT on whether you can confidently
    answer the literal question.

      INFORMATIVE REFUSAL — corpus-adjacent miss.
        The retrieved context contains material topically related to the question but
        does not directly address the specific subject asked. Examples: a question
        about "exclusive psalmody" where retrieval surfaces Christ and the disciples
        singing the Hallel but no commentary by Gill arguing the psalmody position;
        a question about a named figure (Aquinas) where retrieval surfaces a different
        person of similar name (Philip Aquinas, the Hebrew lexicographer).

        Reply with:
          (a) The specific gap in Zone-1 voice: "the indexed corpus does not contain
              Gill's commentary on X" or "Gill does not argue the [position] in the
              indexed material" or "the only X in the indexed material is Philip X,
              a different person from the [Thomas X / etc.] you are asking about".
          (b) Surface the adjacent material verbatim with a Zone-1 disclaimer:
              "the nearest indexed material is Y, here:" then verbatim quote with [SID].
              Cite it properly.
          (c) Do NOT characterize Gill's position on the un-answerable subject
              (Zone 3 violation). The corpus gap is what you are reporting, not Gill's
              view. Refusal here does not authorize you to slant.

      FLAT REFUSAL — category error / off-topic / abuse.
        The question is simply not in the domain: a programming question, a question
        about a person not in the corpus and no related material exists, an anachronism
        ("did Esau eat pizza"). Reply exactly: "I regret that the provided extracts
        from the Doctor's writings do not appear to address this specific inquiry.
        Could it be that you are looking for something not in the library
        ({available_books})?" Provide an empty citation list. Do NOT fish for
        tangentially-related chunks (no lentil trap — do not turn "did Esau eat pizza"
        into a discussion of lentils).

      How to choose: if retrieval brought back substantive on-topic material but not
      the specific claim asked, choose informative. If retrieval is empty or contains
      only off-topic material with no doctrinal/biblical connection, choose flat.

    YOU MUST NOT
    - Speak in Gill's voice or pretend to be him or his contemporary.
    - Interpret Gill in any of the forbidden Zone-3 shapes above (assertive,
      possessive, pronoun-anchored, inference-headed, or label-import). This
      remains forbidden EVEN WHEN THE INTERPRETATION IS ACCURATE. Accurate
      interpretation is not permitted; it is a lesser severity of the same
      violation. The reader must reach every conclusion about Gill from Gill's
      own quoted words, never from your framing.
    - Open with a thesis about what Gill holds, or close with a synthesis of what
      the quotes show. See the BOOKEND RULE above — this is the empirically-
      observed violation site, and the enforcement is strict.
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
            return dspy.Prediction(answer=pred.answer, citations=[], raw_answer=pred.answer)

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

        # Zone-3 post-generation sweep (ADR-0008 Phase 1 Step 4).
        # SHALLOW runtime backstop — catches Gill-anchored assertive and
        # negation forms only. Inference-form and pronoun-anchored Zone 3
        # are documented as semantic-judge territory (Step 5), NOT patched
        # here. Every excision is logged for observability. See ADR-0008
        # Validation Notes for the rate-reporting requirement.
        pre_sweep_answer = repaired_answer
        repaired_answer, zone3_excisions = _suppress_zone3(repaired_answer)
        # Structural bookend enforcement (ADR-0008 Layer 2 amendment
        # 2026-07-06). Runs after the lexical sweep; catches closer
        # editorializing that lexical layer cannot see because it lacks a
        # Gill-verb anchor ("emphasizing its distinctiveness..." trailing a
        # citation). Positional check, not lexical — cannot be routed
        # around by rephrasing.
        repaired_answer, trailing_excisions = _strip_trailing_prose(repaired_answer)
        if trailing_excisions:
            zone3_excisions = list(zone3_excisions) + trailing_excisions
        if zone3_excisions:
            print(f"DEBUG: Zone-3 sweep — {len(zone3_excisions)} record(s):")
            for rec in zone3_excisions:
                print(f"  action={rec['action']} pattern={rec['pattern']} "
                      f"matched={rec['matched']!r}")

        return dspy.Prediction(
            answer=repaired_answer,
            citations=citations_list,
            quote_failures=quote_failures,
            quote_repairs=quote_repairs,
            # Zone-3 sweep records — main.py can put these in stages_capture
            # so the daily diagnostic + observability layer see excisions in
            # real traffic (Step 5 async production sampling will build on
            # this signal).
            zone3_excisions=zone3_excisions,
            # Pre-sweep answer text preserved so the daily diagnostic can
            # compare pre/post per-answer without re-running generation.
            pre_zone3_sweep_answer=pre_sweep_answer,
            # Expose the model's reasoning so main.py / the frontend can show
            # users *what the model considered* when it produces a refusal.
            # The reasoning often names specific Sentence IDs the model
            # identified as relevant but chose not to commit to — surfacing
            # that turns an opaque refusal into an actionable starting point.
            reasoning=getattr(pred, "reasoning", "") or "",
            # Pre-verifier model output. Used by the determinism harness to
            # distinguish "bot LLM produced different text" from "verifier
            # repaired differently" when comparing across runs.
            raw_answer=pred.answer,
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
