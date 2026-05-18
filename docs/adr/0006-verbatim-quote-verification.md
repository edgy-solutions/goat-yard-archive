# ADR-0006: Verbatim Quote Verification

- **Status:** Proposed
- **Date:** 2026-05-17
- **Deciders:** Chris Nogradi

## Context

On 2026-05-17 the answer generation path in [`backend/bot.py`](../../backend/bot.py) was switched to **verbatim mode**: the model no longer paraphrases Gill in a fake 18th-century academic voice. Instead, the system:

- Speaks in plain modern English as a present-day research assistant (its own voice).
- Quotes Gill **verbatim** inside quotation marks, with the Sentence ID placed immediately after the closing quote.
- Uses minimal connective framing between quotes.

The contract is: framing is the system's; quoted content is Gill's. The user must always be able to distinguish.

This is enforced **by prompt instruction only**. The model is told not to paraphrase Gill into modern language, not to smooth his 18th-century English, and to preserve his spelling, capitalization, and italics markers. There is no post-generation verification that the quoted text actually appears verbatim in the source chunks.

### Why this matters

LLMs love to "improve" archaic text. Common failure modes that prompt-only enforcement cannot prevent:

- **Subtle modernization in quote marks.** "And he saith unto him" → "And he said to him" (model thinks it's helping the reader; produces a quote that looks verbatim but isn't).
- **Typo "correction" of OCR artifacts.** Gill's text has occasional OCR errors that should be preserved (the original scan is the ground truth via `scan_json`); the model may silently fix them.
- **Concatenating two non-adjacent fragments.** Model quotes a sentence that combines material from sentences 5 and 7 of the same chunk, dropping sentence 6.
- **Confident attribution to the wrong Sentence ID.** Quote-then-cite, where the citation points at a chunk that doesn't contain the quoted text.

These failures produce *fake Gill in disguise*: a fluent, well-cited answer that misrepresents what Gill actually wrote. They are **harder to detect than the old fake-Gill-voice problem** because they look right at first glance. Catching them requires substring verification against the source chunks.

### Existing verification (insufficient)

[`forward()` in bot.py:150-228](../../backend/bot.py#L150-L228) already checks:
- Refusal-detection heuristics (catch "I regret..." style responses).
- Citation existence (do the cited Sentence IDs resolve to real chunks?).
- Hallucination guard: if a detailed answer has no citations, fail verification.

None of these check that the **quoted text itself** matches the chunk it cites.

## Decision

Add post-generation verbatim verification to `GroundedGillBot.forward()`:

### Algorithm

1. **Extract quoted segments** from the model's `answer`. Match anything inside `"..."` followed by a Sentence ID — pattern: `"([^"]+)"\s*\[([A-Z0-9_]+)\]`.
2. **For each quoted segment `(quote_text, sentence_id)`:**
   - Look up the source chunk containing that `sentence_id` from the context formatted by `forward()`.
   - Normalize both `quote_text` and the chunk text (lowercase, collapse whitespace, strip italics markers like `*...*`, strip footnote markers like `[^1]`).
   - Check that `normalized_quote` appears as a substring of `normalized_chunk`.
3. **If any quote fails verification:**
   - Option A (strict): mark response as `verified=False` with a specific error indicating which quote didn't match.
   - Option B (lenient): strip the offending quote from the answer; keep the rest; log the violation.
   - Option C (regenerate): retry generation with a stricter prompt that includes the failing quote and the source it was supposed to match.

Recommended: **Option A initially** (fail fast, surface violations), with telemetry on which segments fail. Once we have data on failure patterns, decide whether to upgrade to Option C.

### Normalization rules (initial)

| Transform | Reason |
|---|---|
| Lowercase | Gill's capitalization is theologically meaningful but should not break verification |
| Collapse internal whitespace | LLMs reflow whitespace; the content is what matters |
| Strip `*...*` markdown italics markers | Gill's italics survive in our chunks as markdown; the model may quote with or without |
| Strip `[^N]` footnote refs | Model often drops footnote markers when quoting |
| Strip leading/trailing punctuation | Mid-sentence quotes often omit terminal punctuation |
| Normalize curly quotes to straight | `"` vs `"` divergence |

### What this does NOT verify

- **Semantic faithfulness** — whether the framing accurately characterizes the quoted content. (E.g. "Gill says X is wrong:" followed by a quote that is more nuanced than "wrong".) That requires LLM-judge or human review.
- **Coverage** — whether the quotes selected actually address the user's question. (Reranker addresses retrieval; eval set addresses answers.)
- **Quote-citation alignment** — covered indirectly because we look up the quote in the cited chunk's text, but the model could cite chunk A while quoting chunk B's text. Should also do a cross-check.

## Alternatives Considered

1. **Trust the prompt.** Status quo for verbatim mode. Cheapest, no enforcement, opaque failures.
2. **Embedding-similarity check.** Compute embedding(quote) · embedding(chunk_sentence); accept if > 0.95. Catches semantic similarity but allows fluent paraphrase ("verily I say" → "truly I tell you" passes). Defeats the purpose of verbatim mode.
3. **Strict character-level equality.** Reject any quote not byte-identical to source. Highest fidelity, lowest tolerance. Likely to false-positive on benign formatting differences (footnotes, italics, curly quotes).
4. **Retry-on-failure loop.** When verification fails, regenerate with the failing segment and source explicitly shown. Higher latency, potentially higher quality.

## Consequences

### Positive
- Verbatim mode becomes **verified**, not just promised.
- The system can no longer silently produce fake Gill in quote marks.
- Telemetry on quote-verification failures becomes a signal for: prompt drift, retrieval miscalibration, model regression after upgrades.

### Negative
- Adds compute per response (substring matches over 12 chunks × N quoted segments). Cheap but nonzero.
- False positives if Gill's source text has formatting markers the normalizer doesn't strip; needs calibration against real outputs.
- Strict-mode rejections produce a worse user experience than silent paraphrase ("Verification Failed: quote did not match source"). UX consideration.

### Risks
- **Over-strict normalization** rejects legitimate quotes. Mitigation: start lenient, tighten as failure data accumulates.
- **The model learns to inline shorter quotes** to avoid verification failures, eroding the value of verbatim mode. Mitigation: track quote-length distribution over time.
- **Calibration is hard without the eval set** ([ADR-0004](0004-reference-eval-set-and-ci-gates.md)). The right threshold for "lenient enough" depends on labeled examples.

## Implementation Sketch (~50 LOC)

```python
# backend/bot.py — within GroundedGillBot.forward()
import re

QUOTE_PATTERN = re.compile(r'"([^"]+)"\s*\[([A-Z0-9_]+)\]')

def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\*([^*]+)\*", r"\1", text)      # strip italics
    text = re.sub(r"\[\^[\d]+\]", "", text)          # strip footnote refs
    text = re.sub(r"[‘’“”]", '"', text)  # curly→straight
    text = re.sub(r"\s+", " ", text).strip()
    return text

def _verify_quotes(answer: str, chunks_by_sid: Dict[str, str]) -> List[Dict]:
    """Returns list of failures: [{quote, sentence_id, reason}]"""
    failures = []
    for match in QUOTE_PATTERN.finditer(answer):
        quote, sid = match.group(1), f"[{match.group(2)}]"
        source = chunks_by_sid.get(sid)
        if not source:
            failures.append({"quote": quote, "sentence_id": sid, "reason": "cited_sid_not_in_context"})
            continue
        if _normalize(quote) not in _normalize(source):
            failures.append({"quote": quote, "sentence_id": sid, "reason": "quote_not_verbatim"})
    return failures

# In forward(), after prediction:
chunks_by_sid = {}  # built from sentence_data of context_chunks
failures = _verify_quotes(pred.answer, chunks_by_sid)
if failures:
    return dspy.Prediction(
        answer=f"Verification Failed: {len(failures)} quotation(s) did not match Gill's text verbatim. {failures[0]['reason']}: \"{failures[0]['quote'][:80]}...\"",
        citations=[]
    )
```

## Open Questions

- **Strict vs lenient default?** Probably strict initially with telemetry, then adjust based on data.
- **Should partial-quote matches be allowed?** E.g. the model quotes 80% of a long sentence with one word elided in the middle. Substring match would fail; semantically the quote is faithful. Edge case worth deciding before deployment.
- **How to surface verification failures in the API response?** New field like `quote_verification: {passed: bool, failed_quotes: [...]}` for frontend display? Or just bake into existing `verified: bool`?
- **Interaction with chapter-prefix retrieval ([ADR-0002](0002-chapter-and-book-prefix-retrieval.md)):** chapter dumps return many chunks; verification cost scales with quote count, not chunk count, so should remain cheap. Confirm.

## Dependencies

- Best calibrated against the eval set from [ADR-0004](0004-reference-eval-set-and-ci-gates.md). Implementing without that risks setting the wrong strictness threshold.
- Companion to the verbatim mode shipped this session (not formalized as an ADR — it was a direct user-requested fix).
