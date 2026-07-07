# ADR-0008: Three-Zone Generation Architecture and Voice-Marked UI

- **Status:** Proposed (revised 2026-06-28 — added Execution Sequencing section after review; the architecture is approved but Phase 1 ships post-generation suppression only, not streaming)
- **Date:** 2026-06-28
- **Deciders:** Chris Nogradi

## Context

Launch-week post-mortem analysis of the `gya-frontend-api` prod log (2026-06-22 through 2026-06-28, 26 `/api/search` requests across 19 unique questions) surfaced a failure mode that is harder to catch than the verbatim-quote violations addressed in [ADR-0006](0006-verbatim-quote-verification.md). The verifier reliably catches quotes that aren't in the source chunk. It does **not** catch the connective framing around those quotes, where the model is free to characterize Gill's doctrinal position in the assistant's own voice without quoting him.

The headline case, observed verbatim in the prod log on 2026-06-22T02:46:

> *"Gill distinguishes between different covenantal administrations while affirming their ultimate unity in grace."*

That sentence has no quotation marks, no `[SID]` tag, no verifier signal. The quoted material around it (verses from Gen 17:7 and Matt 26:28) all verified clean. Yet the sentence itself is the model asserting a doctrinal position label as Gill's view — a label Gill does not himself argue in any of the indexed chunks. The verifier was satisfied because every literal quote was real; the answer was wrong because the model spoke *about* Gill in a way the chunks don't support.

The reviewing agent named this the **Zone 3 violation** — the assistant slanting Gill's position in its own voice. ADR-0006 only protects against violations *inside* the quotation marks. Zone 3 violations sit between the quotation marks, where the verifier has no view.

### Three-zone taxonomy of generated content

A grounded answer has three categorically different kinds of content. The system handles them well only if it treats them as different things:

| Zone | What it is | Shown to user? | How its faithfulness is enforced |
|---|---|---|---|
| **Zone 1** | The model's voice interpreting the user's request — bridging modern terminology to Gill's idiom, orienting the reader between quotes. | **Yes**, explicitly labeled as the model's voice (not Gill's). | Voice attribution in the UI. Honest because *we never claim Gill said it*. |
| **Zone 2** | Gill's verbatim words, with no interpretation. | **Yes**, with per-quote verification chips. | Verbatim verification (ADR-0006) — substring match against the chunk's actual text. |
| **Zone 3** | The model's slant on Gill — characterizing his position, summarizing his teaching in the assistant's own assertive voice. | **No, never.** | Zoning prompt (prevention) + per-unit runtime classification (detection) + offline semantic eval (proof). |

The crucial property: **Zone 3 is forbidden output, not flagged output.** Earlier UI mockups proposed a "red lane" that would display Zone-3 sentences with a "this is the machine characterizing Gill" warning. That compromise was rejected: showing flagged Zone 3 still surfaces the forbidden thing wearing a label. A reader scanning the answer would still register "Gill distinguishes..." as the takeaway. The harder, more honest design is to kill Zone 3 before the user sees it.

### Two leak paths to mitigate

Zone 3 doesn't have its own UI slot, but the model will try to write it somewhere if the prompt doesn't channel the impulse. The two leak paths:

1. **Zone 3 → Zone 1.** The model slants while writing the interpretive bridge. Acceptable when Zone 1 is clearly labeled as the model's voice — at worst the user sees the machine's opinion attributed to the machine. Mitigation: voice labeling in the UI.
2. **Zone 3 → Zone 2 framing.** The model wraps a verified Gill quote in a sentence that asserts a Gill position. The quote verifies; the sentence around it does not. This is the **dangerous** leak — the covenant case. The verifier doesn't catch it because it only checks the quoted span. Mitigation: per-unit runtime classification of the connective tissue around each quote.

This ADR addresses leak path 2. Leak path 1 is handled by the UI decision below.

## Decision

Implement a three-layer defense covering generation, runtime, and offline eval, with a voice-marked UI that makes Zone 1 and Zone 2 visually distinct.

### Layer 1 — Generation: the zoning prompt

The bot prompt in `backend/bot.py` is extended to teach the model the three-zone taxonomy explicitly:

- **Zone 1 is allowed**, owned as the model's voice — bridging modern terms to Gill's idiom, orienting between quotes. The model says *"the modern term X relates to Gill's discussion of Y"* not *"Gill says X is Y"*.
- **Zone 2 is the substantive content** — verbatim Gill quotes inside quotation marks, with `[SID]` immediately after each closing quote, per ADR-0006. Connective tissue around a quote may NOT assert a Gill-position; it may only orient the reader.
- **Zone 3 is forbidden** — the model must not characterize Gill's stance, doctrine, position, or opinion in its own assertive voice. Examples of forbidden patterns: *"Gill distinguishes / affirms / argues / holds / teaches / supports / leans toward [position]"*, *"Gill's view of X is..."*, *"Gill takes the [label] position"*.

The prompt also instructs the model on two **refusal modes** (a category problem named in this round of post-mortem):

- **Informative refusal** for corpus-adjacent misses (Aquinas, the psalmody-debate question): explain the specific gap in Zone-1 voice, surface adjacent material with disclaimer, never characterize Gill on the subject. Replaces the current canned line for this category.
- **Flat refusal** for true category errors (JavaScript for-loop, "did Esau eat pizza"): the canned line, no fishing for tangentially-related chunks (avoid the lentil trap).

#### Optional: the Zone-3 release valve (deferred — see Execution Sequencing)

Instruction-tuned models *may* comply better when given a channel for an impulse than when flatly forbidden. A future experiment could instruct the model to emit its Zone-3 slant into a designated discardable field (e.g., a `<interpretation>...</interpretation>` block) that the backend strips before the response leaves the API. The field would double as ground truth for the runtime classifier and the offline eval.

**This is exploratory and does NOT ship with the Phase 1 zoning prompt.** It carries a real serialization-leak risk (if the backend strip ever misses, forbidden text lands in `response.answer` verbatim) and an empirical-effectiveness question (does it actually reduce Zone-2 leakage?). It must be A/B'd in isolation against the no-valve prompt, and must ship with an integration test that asserts the discardable field is absent from the API response — both *before* it touches the production prompt. See Execution Sequencing item 9.

### Layer 2 — Runtime: gated-stream verification

The bot output is streamed from the model to the backend, buffered into per-unit chunks, verified mechanically, and released to the UI **only after the unit clears all gates**. This solves three problems at once: it eliminates the 30-second blank-screen wait by progressively rendering verified content, it keeps Zone-3 leaks from reaching the eye, and it applies the verbatim check at the moment it can still affect what the user sees.

#### Unit boundary

A unit is `framing + quote + [SID]`. The SID token is the boundary marker — the system buffers tokens from the model until it sees a complete closing `[SID]` tag, then has a releasable unit. This reuses the structure that ADR-0006 already established for citation; the SID architecture doubles as the streaming-verification delimiter.

For framing-only segments (Zone 1 bridge text, or framing between quotes that doesn't precede a quote yet), the unit boundary is a sentence terminator (`.` `!` `?` followed by newline or another framing sentence). These segments still receive runtime checks but cannot be quote-verified (no quote to check).

#### Per-unit checks (mechanical only — no model calls in the critical path)

1. **Verbatim quote check (ADR-0006).** difflib substring match of the normalized quote against the cited chunk. Pass → green chip. Soft fail repairable by difflib → green with telemetry. Hard fail → release the span with the amber/unverified chip. **Do not stall the stream to attempt LLM-repair** — that puts a multi-second model call on the critical path and visibly hangs the stream mid-answer. Repair, if attempted at all, happens off-path.

2. **Lexical Zone-3 scan.** The framing portion of the unit (the words preceding the quote, plus any free-standing framing sentence) is scanned for a fixed list of **characterization verbs applied to a Gill subject**:

   | Trigger pattern | Example |
   |---|---|
   | `Gill (distinguishes\|affirms\|holds\|teaches\|argues\|supports\|advocates\|maintains\|leans toward\|takes the \w+ position)` | "Gill distinguishes between..." |
   | `Gill's (view\|position\|stance\|teaching\|doctrine\|opinion) (of\|on)` | "Gill's view of eternal justification..." |
   | `Gill (himself\|here) (?:says\|believes\|holds)` (when not introducing a verified quote within 80 chars) | "Gill himself believes..." |

   On a trigger: the offending sentence is **excised** from the unit before it streams to the UI. This is the run-time enforcement of "Zone 3 is forbidden output." A telemetry event records the excision for later review. If the model returned a discardable Zone-3 field (the release-valve option), the excised sentence is appended there for review; otherwise it is dropped.

3. **Binary Zone-3 classifier (small local model).** For each unit, a small classifier model (gemma4:e4b is the candidate) is given the prompt: *"Does this sentence characterize Gill's doctrinal position in the assistant's own voice, beyond what the quoted text supports? Yes/No."* If yes, the sentence is excised the same way as a lexical trigger. The binary scope is critical: this is a structural classification ("is there an own-voice Gill-stance assertion") not a faithfulness judgment ("is the assertion theologically correct"). The binary version is a tractable task for a small model in a way the open-ended faithfulness check is not. **Latency budget for this check: < 200 ms per unit.** If it exceeds, the unit streams without the semantic gate (lexical gate still applies) and an alert fires.

The runtime stream is fluent only if every gate is mechanical or sub-second. A model call slower than ~200 ms in the critical path reintroduces the latency we are trying to kill, one unit at a time.

### Layer 3 — Offline eval: semantic Zone-3 check with a good model

The runtime classifier is constrained to a fast local model. The offline eval is not.

The `must_not_express` lexical check in `evals/run_eval.py` is extended with a **semantic Zone-3 judge** that uses DeepSeek (the same model the bot uses, but called offline without latency budget). The judge prompt: *"Does the following answer state Gill's position on \[topic\] in the assistant's own voice, beyond what a verbatim quote in the answer substantiates?"* This runs across the full eval set on every prompt change. It is the **proof** layer: any time the zoning prompt is modified, the full eval re-runs through the semantic judge, and a regression on the covenant/exclusive_psalmody-class cases blocks merge.

This layer's role is precisely what runtime cannot do: subtle, latency-tolerant, high-accuracy semantic faithfulness judgment, on a controlled test set, with the better model.

### Layer 4 — UI: voice-marked gutter rendering

The UI design that survived design review on the worst case (the Garden answer with one unverified quote, the covenant answer with all-verified-quotes-plus-bad-synthesis):

#### Gutter model

A vertical rule on the left edge of the answer column marks the voice of each block:

- **Blue rule + small "interpretation" label** → Zone 1, the model's bridge or framing. The user sees instantly that this is the system speaking *about* the question, not Gill.
- **Neutral / parchment rule** → Zone 2, Gill's verbatim words. The serif typeface and the rule together signal "this is the source talking."
- **No red lane.** Zone 3 is not displayed; there is nothing to render. If the runtime gates excise a Zone-3 sentence, the user simply sees the sentence missing — and ideally, the zoning prompt prevented it from being emitted at all, so excision is the rare backstop.

The gutter was chosen over the "inline-highlight tint" alternative because it scales to long answers (Word of God, baptism) without the highlighter-explosion effect, it reads as the apparatus of a scholarly critical edition (on-brand for the Puritan Board audience), and it makes the voice boundary **structural** rather than decorative — a quote is in the Gill lane or it isn't, with no ambiguous in-between.

#### Per-quote verification, separately from voice

Voice marking (which lane) and verification marking (verified-verbatim or not) are **two independent visual dimensions**. A neutral parchment lane says "this is Gill"; the inline chip on the quote says "we verified" (green check) or "we couldn't verify" (amber warning). The Garden case renders the four real Gill quotes with green chips and the misattributed Gen 3:24 span with an amber chip and a short inline explanation — the user sees exactly which span is shaky, not just "something in here is."

#### Theme-aware tokens, not hardcoded hex

The mockup review surfaced that hardcoded parchment/amber hex values break in dark mode. The production CSS must use mode-aware design tokens (`--surface-quote-verified`, `--surface-quote-unverified`, `--accent-zone1-voice`) so the tints flip with the theme. Any color that carries meaning in the UI must be defined as a token, not a literal — this is a hard rule for accessibility and correctness across light/dark.

#### What the UI does NOT do

The UI cannot police whether the model's Zone-1 voice is theologically accurate. It can mark voice; it cannot mark faithfulness of the model's *own* claims about anything. That guarantee comes from the zoning prompt (prevention) and the offline semantic judge (proof). The UI's job is the visible boundary; it does not, and cannot, replace the verification pipeline.

## Alternatives Considered

1. **Two literal boxes (LLM-voice on top, Gill-voice on bottom).** Rejected: the most readable answers interleave framing and quote ("work Gill describes as 'nothing else but to study...'") — hard segregation breaks the narrative flow that makes answers readable. The natural unit of voice attribution is the quote, not the section.

2. **Inline highlight (parchment background tint on every Gill span).** Reasonable for short answers, gets noisy on long ones (baptism, 64 chunks). Chosen as a fallback or for specific contexts; the gutter is the default.

3. **Surface the raw `reasoning` field to users.** The model's reasoning trace is *itself* unverified, un-zoned, own-voice synthesis — exactly the Zone 3 territory we are trying to constrain. Surfacing it smuggles the forbidden thing onto the screen through the back door of refusal explanations. The Aquinas reasoning happens to be clean; the covenant reasoning is full of "Gill distinguishes...". Reasoning stays internal/debug; the *refusal text* gets richer under the same zoning constraints (the informative-refusal mode).

4. **Flag Zone 3 with a red "characterization" lane instead of excising.** Tempting because it's transparent. Rejected because showing flagged Zone 3 still puts the forbidden assertion on the screen — a reader skimming the answer registers "Gill distinguishes..." as the takeaway regardless of the warning around it. The honest design is to kill the sentence, not decorate it. (This decision was the user's correction of an earlier reviewing-agent proposal.)

5. **Verify-then-stream the whole answer.** Generate fully, verify fully, then stream the verified result. Simpler than gated streaming. Rejected because the user still waits 20-30 seconds for the first token. Gated streaming gives true progressive rendering — the first verified quote can render while the third is still generating — at no trust cost.

6. **Stream raw to the UI, verify in parallel, retroactively flag.** The architecture that exposes unverified content to the user's eyes first. Rejected: shows the user the violation before catching it. Wrong direction for the trust model.

7. **Use the runtime semantic classifier for full faithfulness judgment instead of binary structural classification.** Rejected based on this week's gemma behavior: the same model that returned `{}` for "Who is Peter?", over-expanded "Aquinas" to "Papist tradition," and produced "Please provide the modern search terms" as an expansion cannot be trusted to be the reliable arbiter of subtle theological faithfulness. Binary structural classification ("is there an own-voice Gill-stance assertion here, Y/N?") is a far tractable task than open-ended faithfulness judgment; that's why the runtime check is scoped to it and the semantic judge runs offline with a better model.

8. **Skip the zoning prompt and rely entirely on runtime detection.** Rejected: prevention is cheaper and more reliable than detection. The right outcome is that the model doesn't emit "Gill distinguishes..." at all because the prompt makes it harder, not that we catch and excise it after. Runtime is the backstop; the prompt is the prevention.

## Consequences

### Positive

- **Closes the covenant-class gap** that ADR-0006 cannot reach. Verbatim verification protects the quoted span; this ADR protects the framing around it.
- **Progressive rendering** as a byproduct of gated streaming — the 30-second wait visible to launch-week users disappears.
- **Voice is visually unmistakable.** A user can tell at a glance which sentences are the machine talking and which are Gill — the system promise made structural.
- **Per-quote verification visibility.** The amber/green chip per span turns "some are scary" into a precise affordance — the scary span is flagged in place, not the whole answer.
- **Refusal path becomes informative** in the corpus-adjacent cases (Aquinas, psalmody-debate). The intellectual work the model does to recognize a corpus gap reaches the user instead of being discarded behind the canned line.
- **Layered defense reduces single-point-of-failure risk.** Prompt + runtime mechanical + runtime lexical + runtime binary classifier + offline semantic judge — each layer catches what the others miss.

### Negative

- **Gated streaming is new plumbing.** DSPy's current output mode is non-streaming; the bot's prediction path needs to be reworked to emit tokens. Substantive engineering, not a small change. Feasibility check (does DSPy/DeepSeek support streaming via litellm) is a prerequisite.
- **Runtime checks add per-unit latency.** Each gate is cheap (difflib < 50 ms, lexical scan < 5 ms, binary classifier target < 200 ms) but they compound across many units. A 10-quote answer adds 1-2 s of gate latency total, partially absorbed by streaming overlap with generation.
- **Excised Zone-3 sentences leave visual gaps.** A reader who would see "Gill distinguishes... [then a quote]" now sees "[the quote]" with no preamble. Mitigation: the zoning prompt should produce Zone-1 framing for these positions, so the slot fills with bridge prose; excision is a last-resort backstop.
- **Voice-marking design depends on theme-aware CSS tokens.** Hardcoded hex breaks in dark mode (caught during mockup review). Implementation discipline required.

### Risks

- **The runtime binary classifier is unreliable.** Gemma's behavior this week justifies skepticism. Mitigation: before deploying, run an offline calibration suite — give the classifier 50 known-Zone-3 sentences (the covenant pattern, the eternal-justification pattern) and 50 known-clean Zone-1 sentences (the John 6:37 framing). Reliable classification (> 95% accuracy on the held-out set) is a precondition for shipping the runtime classifier. If accuracy is below threshold, the runtime layer falls back to lexical-only and the offline semantic judge becomes the sole authoritative check.
- **Lexical scan false-positives over-excise.** "Gill distinguishes" can be a legitimate Zone-1 introduction *to a verified quote* ("Gill distinguishes the sign from the substance: 'circumcision was the sign of the covenant...'"). Mitigation: the lexical trigger fires only when the characterization verb is NOT followed by a quotation mark within 80 characters. Same window as the existing `QUOTE_WITH_CITE_RE` pattern from ADR-0006.
- **The release-valve discardable field could leak through API serialization.** If the model emits `<interpretation>` content and the backend forgets to strip it before returning the SearchResponse, the forbidden text lands in `response.answer` verbatim. Mitigation: strip the field in `backend/bot.py` immediately after parsing, before constructing the Prediction. Add an integration test that posts a deliberately-Zone-3-heavy generation and asserts the discardable field is absent from the API response.
- **Streaming protocols differ across LLM providers.** OpenRouter exposes Server-Sent Events for DeepSeek; gemma via Ollama exposes a similar stream. The backend must handle both, and FastAPI's `StreamingResponse` has its own conventions. Implementation complexity is moderate.
- **The gutter UI assumes a wide-enough viewport.** On mobile, a vertical rule + label in a side gutter compresses awkwardly. The mobile fallback is the inline-tint variant of voice marking, which the gutter explicitly chose against for desktop. Both designs must coexist.

## Implementation Sketch

### Prompt-level (Phase 1)

```python
# backend/bot.py — additions to GillSignature docstring

THREE_ZONE_INSTRUCTIONS = """
Your output has three categorically different kinds of content. You must treat
them as different things:

  ZONE 1 (allowed, plain modern English, your own voice):
    Interpretive framing — bridging the user's modern question to Gill's
    18th-century idiom, orienting between quotes. You may say:
      "the modern question of X relates to Gill's discussion of Y"
      "in the indexed material, this connects to..."
    You may NOT use this zone to assert Gill's position. You bridge; you
    don't characterize.

  ZONE 2 (allowed, Gill's verbatim words):
    Direct quotations from the retrieved chunks, inside quotation marks,
    with [SID] immediately after the closing quote. NEVER paraphrase, NEVER
    modernize, NEVER smooth Gill's English. The [SID] must follow a
    verbatim quote from THAT exact chunk's text — never follow paraphrase,
    summary, or a quote drawn from a different chunk.

  ZONE 3 (FORBIDDEN — do not emit):
    Characterizing Gill's position, doctrine, view, stance, or teaching in
    your own assertive voice. Examples of forbidden patterns:
      "Gill distinguishes / affirms / argues / holds / teaches / supports
       / leans toward / takes the [position] view"
      "Gill's view of X is..."
      "Gill's position on X is..."
    Quote what he says; never characterize what he holds. If you cannot
    answer without characterizing, use the informative-refusal pattern
    instead.

REFUSAL MODES:
  Informative refusal — corpus-adjacent miss (the retrieved chunks contain
    topically-related material but not the specific subject asked):
      State the specific gap in Zone-1 voice ("the indexed corpus does not
      contain Gill's commentary on X"), surface adjacent material with a
      Zone-1 disclaimer ("the nearest indexed material is Y, here: [quote
      cited to Z] — different from what you asked but related"), and DO
      NOT characterize Gill's position on X.

  Flat refusal — category error / off-topic / abuse (the question is
    simply not in the domain):
      Reply exactly: "I regret that the provided extracts from the
      Doctor's writings do not appear to address this specific inquiry.
      Could it be that you are looking for something not in the library
      ({available_books})?" Provide an empty citation list. Do not fish
      for tangentially-related chunks (do not produce the lentil trap
      where "Esau eating pizza" turns into "Esau ate lentils").
"""
```

### Runtime-level Phase 1 (post-generation suppression — synchronous, no streaming)

This is the version that ships with the Phase 1 zoning prompt. It runs on the complete `pred.answer` inside `forward()` after quote verification but before the `dspy.Prediction` is returned. No new modules, no streaming plumbing.

```python
# backend/bot.py — inside GroundedGillBot.forward(), after quote verification

import re

ZONE3_TRIGGER_RE = re.compile(
    r"\bGill\s+("
    r"distinguishes|affirms|holds|teaches|argues|supports|advocates|"
    r"maintains|leans\s+toward|takes\s+the\s+\w+\s+position|believes\s+that"
    r")\b",
    re.IGNORECASE,
)
ZONE3_POSSESSIVE_RE = re.compile(
    r"\bGill's\s+(view|position|stance|teaching|doctrine|opinion)\s+(of|on)\b",
    re.IGNORECASE,
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def _suppress_zone3(answer: str) -> tuple[str, list[str]]:
    """Excise Zone-3 sentences from the finished answer. Returns (cleaned, excised).

    A Zone-3 sentence trips ZONE3_TRIGGER_RE or ZONE3_POSSESSIVE_RE AND is
    NOT immediately followed by a verified quote (the QUOTE_WITH_CITE_RE
    pattern). The "followed by quote" exemption protects legitimate Zone-1
    bridges like 'Gill distinguishes the sign from the substance: "...".'
    """
    sentences = _SENTENCE_SPLIT_RE.split(answer)
    kept, excised = [], []
    for s in sentences:
        if ZONE3_TRIGGER_RE.search(s) or ZONE3_POSSESSIVE_RE.search(s):
            # Exempt if the sentence introduces a quote within 80 chars of the trigger
            if not _trigger_introduces_quote(s):
                excised.append(s)
                continue
        kept.append(s)
    return " ".join(kept), excised


def _trigger_introduces_quote(sentence: str) -> bool:
    """Does the Zone-3-flagged sentence immediately introduce a verified quote?"""
    m = ZONE3_TRIGGER_RE.search(sentence) or ZONE3_POSSESSIVE_RE.search(sentence)
    if m is None:
        return False
    tail = sentence[m.end():]
    return bool(QUOTE_WITH_CITE_RE.search(tail[:120]))


# In forward(), after the existing _repair_quotes_in_answer() block:
cleaned_answer, excised = _suppress_zone3(repaired_answer)
if excised:
    print(f"[ZONE3 SUPPRESSION] Excised {len(excised)} sentence(s): {excised}")
    # Telemetry hook — record for later review (the lexical-scan corpus that
    # informs the offline judge calibration and the eventual streaming gate)
repaired_answer = cleaned_answer
```

The binary classifier (the Layer-2 secondary gate) attaches to this same hook: if calibrated > 95% on the held-out set, it runs after the lexical pass on any sentence that didn't trip the lexical trigger but is in Zone-1 framing position. Same synchronous interface.

### Runtime-level Phase 2 (streaming proper — deferred, see Execution Sequencing)

The streaming sketch below is the *Phase 2* version, deferred until the four feasibility checks land. It is the same enforcement logic re-shaped to run mid-stream against token-buffered units. Recorded here as the architectural target.

```python
# backend/streaming.py — new module (Phase 2, deferred)

import asyncio, re
from typing import AsyncIterator, Optional

QUOTE_WITH_CITE_RE = re.compile(r'["""]([^"""]+)["""][^"""\n\[\]]{0,80}\[([A-Z0-9_]+_S\d+)\]')

# Lexical Zone-3 triggers — fires on characterization verbs applied to Gill,
# when NOT immediately introducing a verified quote.
ZONE3_TRIGGER_RE = re.compile(
    r"\bGill\s+("
    r"distinguishes|affirms|holds|teaches|argues|supports|advocates|"
    r"maintains|leans\s+toward|takes\s+the\s+\w+\s+position|believes\s+that"
    r")\b",
    re.IGNORECASE,
)
ZONE3_POSSESSIVE_RE = re.compile(
    r"\bGill's\s+(view|position|stance|teaching|doctrine|opinion)\s+(of|on)\b",
    re.IGNORECASE,
)


async def gated_stream(
    raw_stream: AsyncIterator[str],
    chunks_by_sid: dict,
    zone3_classifier: Optional[callable] = None,
) -> AsyncIterator[dict]:
    """Buffer raw model tokens, emit verified units to UI.

    Yields events of the form:
      {"type": "framing", "text": "...", "voice": "zone1"}
      {"type": "quote",   "text": "...", "sid": "[X_Y_S0]", "verified": True/False}
      {"type": "excised", "reason": "lexical_zone3_trigger"}  (telemetry only)
    """
    buffer = ""
    async for token in raw_stream:
        buffer += token
        # Try to extract one complete unit
        while True:
            unit = _try_extract_unit(buffer)
            if unit is None:
                break
            framing, quote, sid, remaining = unit
            buffer = remaining

            # Gate 1: lexical Zone-3 scan on framing
            if _trips_lexical_zone3(framing, quote):
                yield {"type": "excised", "reason": "lexical_zone3_trigger",
                       "excised_text": framing}
                framing = ""  # drop the offending sentence

            # Gate 2: binary Zone-3 classifier (if available, < 200ms budget)
            if zone3_classifier and framing:
                if await asyncio.wait_for(zone3_classifier(framing), timeout=0.2):
                    yield {"type": "excised", "reason": "binary_classifier",
                           "excised_text": framing}
                    framing = ""

            # Release framing (Zone 1)
            if framing:
                yield {"type": "framing", "text": framing, "voice": "zone1"}

            # Gate 3: verbatim quote check (Zone 2)
            verified = _verify_quote(quote, chunks_by_sid.get(sid, ""))
            yield {"type": "quote", "text": quote, "sid": sid, "verified": verified}


def _trips_lexical_zone3(framing: str, quote: str) -> bool:
    """Fire on Zone-3 verb in framing UNLESS followed by a verified quote."""
    if quote:  # Framing immediately introduces a verified quote — likely OK
        return False
    return bool(ZONE3_TRIGGER_RE.search(framing) or ZONE3_POSSESSIVE_RE.search(framing))


def _verify_quote(quote: str, source: str) -> bool:
    """Reuse the normalization + substring check from ADR-0006."""
    from backend.bot import _normalize_for_quote_match  # existing
    return _normalize_for_quote_match(quote) in _normalize_for_quote_match(source)


def _try_extract_unit(buffer: str):
    """Pull off (framing, quote, sid, remaining) if buffer contains a complete
    [SID] tag, else return None."""
    m = QUOTE_WITH_CITE_RE.search(buffer)
    if m is None:
        # Maybe a framing-only sentence terminator?
        if re.search(r"[.!?]\s+$|[.!?]\n", buffer):
            framing = buffer
            return (framing, "", "", "")
        return None
    framing = buffer[:m.start()].strip()
    quote = m.group(1).strip()
    sid = f"[{m.group(2)}]"
    remaining = buffer[m.end():]
    return (framing, quote, sid, remaining)
```

### Offline eval (Phase 1)

`evals/run_eval.py` already supports `must_express` / `must_not_express` ([per ADR-0004 evolution](0004-reference-eval-set-and-ci-gates.md)). The Phase-0 commit on 2026-06-28 added the post-launch failure cases (`real_covenant_monocovenantal_001`, `real_garden_genesis_3_24_misattribution_001`, `real_exclusive_psalmody_001`, etc.) that encode the lexical Zone-3 triggers as `must_not_express`. The semantic judge upgrade (Layer 3) is a follow-on that calls DeepSeek with a binary Zone-3 prompt per answer and records the result alongside the lexical check.

### UI (Phase 2, dependent on streaming plumbing)

`frontend/src/components/AnswerBlock.tsx` (new) renders the streamed events from the gated stream:

- `framing` events → blue-rule block with "interpretation" label
- `quote` events → neutral parchment-rule block with serif text + per-span verification chip (green = verified, amber = unverified)
- `excised` events → debug-only (not rendered in production UI)

Theme tokens go in `frontend/src/styles/zoning.css`:

```css
:root {
  --rule-zone1: var(--color-accent-blue);
  --rule-zone2: var(--color-surface-parchment);
  --surface-quote-verified: var(--color-surface-neutral);
  --surface-quote-unverified: var(--color-surface-warning-subtle);
  --chip-verified: var(--color-success);
  --chip-unverified: var(--color-warning);
}
@media (prefers-color-scheme: dark) {
  /* Tokens redefined to flip with theme. Mandatory — see ADR. */
}
```

## Open Questions

- **Does DSPy/DeepSeek via LiteLLM support streaming today?** Feasibility blocker for the runtime layer. If not, Phase 1 ships prompt + offline eval; gated streaming defers to Phase 2 with a small plumbing addition.
- **What's the correct latency budget for the binary classifier?** 200 ms is the stated target; calibrate against gemma's observed first-token-time when given a 100-token framing input. If gemma can't hit 200 ms reliably, the runtime classifier is dropped from the critical path and the lexical scan + offline judge carry the load.
- **Does the release-valve discardable field meaningfully reduce Zone-2 leakage?** Empirical question. Run a paired-A/B offline: same prompt with and without the discardable field, score how often the model produces a Zone-3 sentence in the visible content. If the gains are marginal, drop the field for simplicity.
- **How do we handle Zone-3 violations the model produces *despite* the prompt and gates?** The runtime layer excises; the offline eval flags. But the model may produce a span where lexical doesn't trigger, the classifier misclassifies, and the verifier has no view (because the violation isn't in a quote). The proper answer is that no single layer is sufficient — the prompt makes such violations rare, the classifier catches the common shapes, the lexical catches the obvious patterns, the offline judge catches the rest with high accuracy across the test set. The combination is the guarantee, not any single layer.
- **What is the right UI affordance when the streamed answer has many excisions?** A user might see "[quote]. [quote]. [quote]" with no connective tissue if the model relies heavily on Zone-3 framing and the gates excise it all. That's degraded UX; the prompt should make this rare, but the UI may need a fallback rendering ("connective framing was suppressed; quotes follow").

## Execution Sequencing (added 2026-06-28 after review)

The four-layer architecture above is the recorded plan. **Its execution is split into two phases that must be sequenced carefully**, because the layers entangle if implemented together and one of them (Layer 2's streaming half) carries four unvalidated dependencies the others do not.

### The key un-conflation

Re-read Layer 2 carefully. It bundles two separable things:

1. **Zone-3 suppression mechanics** — the lexical scan and binary classifier that detect and excise own-voice characterization sentences.
2. **The streaming serving path** — token-buffering, unit-boundary parsing, async event yielding to the UI.

**The Zone-3 suppression does not require streaming.** The lexical scan and the binary classifier can be invoked on the *complete generated answer*, post-generation, before the API returns the response. The faithfulness guarantee is identical whether the check runs token-by-token mid-generation or runs on the finished prediction at the end of `forward()`. Streaming only changes *when* the check fires (mid-stream vs post-generation) and *whether the user gets progressive rendering* — neither affects whether Zone 3 reaches the eye.

This means **the trust-improving half of Layer 2 ships with no serving-path changes**. The streaming-rearchitecture half is a separate, later, optional UX project gated on its own feasibility checks.

### Phase 1 (do now — no new architecture)

1. **Verse-reference parser fix** (independent of Layer 1). Loosen `gill_search.py`'s regex to accept `.` as a verse separator: `\d+(?:[:.]\d+)?`. Two-line change. Validation: paired colon-vs-period query against deployed system; both should resolve via direct-lookup. **Ships before the zoning work** — it's a common-shape user fix (Matthew 28.17 → confident false refusal on the launch-week log) and it has zero interaction with anything else in this ADR.

2. **BAML hardening** (also independent of Layer 1). Sanity-check the BAML output for the known failure modes — empty expansion, the literal "Please provide the modern search terms" self-clarifying response, the REPORTED-TRADITIONS over-generalization on named historical figures (Aquinas). Treat each as a BAML failure; fall through to dedup-only entity boost (no full entity dump — that was the 2026-06-22 universal-atonement amplification). Narrow REPORTED TRADITIONS to biblical unnamed figures only. **Ships before the zoning work** for a substantive reason: BAML failures currently poison the retrieval substrate the zoning prompt operates on, which would muddy the zoning multi-run A/B (a covenant or psalmody run might fail for retrieval reasons not zoning reasons). Clean the input layer first.

3. **Layer 1 — the zoning prompt.** Add the three-zone teaching and the two refusal modes to the `GillSignature` docstring in `backend/bot.py`. **Do not include the release-valve discardable field at this stage** — see below.

4. **Layer 2 (suppression only, NOT streaming) — post-generation Zone-3 sweep.** Implement `_suppress_zone3()` as a function called on the complete `pred.answer` inside `forward()`, after quote verification but before returning the `dspy.Prediction`. The function runs the lexical scan and (optionally) the binary classifier on the finished text, excises matched sentences, returns the cleaned answer. This delivers Layer 2's enforcement behavior — Zone 3 never reaches the user — without one byte of streaming plumbing. No `streaming.py` module. No async event yielding. No SID-buffered units. Just a synchronous string-in / string-out function on a finished prediction.

5. **Layer 3 — offline semantic judge.** Extend `evals/run_eval.py` to call DeepSeek with the binary Zone-3 prompt on the answer field, alongside the existing `must_not_express` lexical check. Runs on the 28-case eval set on every prompt change. Latency-free because it's offline.

6. **Multi-run A/B validation.** Pre-fix and post-fix N=5 each on `covenant_monocovenantal`, `aquinas`, `exclusive_psalmody`. **Hard pass criterion** — and this is load-bearing, not a gesture:
   - **Conclusive pass:** pre-fix runs produce Zone-3 violations across at least 3 of 5 instances AND post-fix runs produce zero violations across all 5.
   - **Conclusive fail:** post-fix runs produce ANY Zone-3 violations.
   - **Inconclusive:** pre-fix runs produce zero violations (the bug is dormant due to state drift). When inconclusive, validation falls back to scoring the captured prod-log known-bad answer against the new instrument AND a prompt-construction review by a second reader. **Inconclusive must not be written up as a pass.** The result is "fix shipped, validation inconclusive, regression risk monitored."

### Phase 2 (defer — gated on feasibility)

7. **Layer 2 streaming proper.** Token-buffered SID-bounded units, mechanical gates only in the critical path, async event yielding. Gated on:
   - Feasibility check: does DSPy/DeepSeek via LiteLLM support streaming today?
   - Latency check: can the small binary classifier hit < 200 ms reliably on representative framing inputs?
   - Accuracy check: does the binary classifier reach > 95% accuracy on the 100-sentence calibration suite (50 known Zone-3 + 50 known Zone-1)?
   - Unit-boundary check: does the proposed regex handle real streamed tokens (interleaved partial markdown, edge cases) without corruption?

   Failure on any → streaming deferred further. The post-generation suppression from Phase 1 continues to carry the runtime faithfulness load.

8. **Layer 4 — gutter UI.** Depends on streaming events. Builds on the streaming plumbing.

9. **The release-valve `<interpretation>` discardable field.** Separate isolated A/B: same prompt with-and-without the field, measure Zone-2 cleanliness delta on the existing eval set. The serialization-leak risk identified in the Risks section requires an integration test asserting the field is absent from `response.answer` *before* the prompt change ships. **Do not bundle into Phase 1's prompt change.** A failed release-valve experiment must not block the zoning prompt.

### The principle being enforced

Three layers of an architectural ADR can ship with no new serving-path code, no new modules, no streaming, no UI work. The fourth layer is a UX optimization that arrives later when its prerequisites validate. This decoupling is the load-bearing decision: it lets the credibility-improving fix ship this week, validated by the multi-run A/B discipline, without the gravitational pull of the streaming-rearchitecture stalling the prompt work behind four unvalidated dependencies.

The ADR records the full architecture so the later phase has a written plan; the Execution Sequencing records that the full architecture does not all ship at once, and which half ships first.

## Validation Notes (added 2026-07-05 after Step 3 live smoke)

Post-launch analysis identified the covenant_monocovenantal query as the flagship Zone-3 case. The 2026-06-22 prod-log answer read:

> *"Gill distinguishes between different covenantal administrations while affirming their ultimate unity in grace."*

No quotes, no [SID], no verifier signal — pure Zone-3 systematizing in the model's own voice. The Step-3 zoning prompt landed 2026-07-01 and was smoked against the same query on the test cluster (single run 1 of 2 captured verbatim, all quotes confirmed `Verified: True` by the ADR-0006 difflib verifier, no `unverified_sentence_ids`):

> *"Gill distinguishes the covenant of grace from other covenants in the following ways:*
>
> *1. On the Noahic covenant: 'Not the covenant of grace in Christ, but of the preservation of the creatures in common, a promise that they should not be destroyed any more by a flood' [GENESIS_9_9_S00].*
>
> *2. On the covenant of circumcision: 'The covenant of circumcision, so called from the token of it, which God is said to make or give, being his own constitution, and depended on his sovereign will and pleasure' [GENESIS_17_2_S00].*
>
> *3. On the Mosaic covenant: 'The blood of the covenant, which the Lord hath made with you concerning all these words; being a ratification of the covenant on both sides, having been sprinkled both upon the altar, and upon the people' [EXODUS_24_8_S00]. Gill contrasts this with the new covenant: 'But the second covenant, or the new administration of the covenant of grace, for which reason it is called the New Testament, is exhibited and established in the blood of Christ the testator' [MATTHEW_26_28_S01].*
>
> *4. On the everlasting nature of the covenant of grace: 'For an everlasting covenant; to his natural seed... and to all his spiritual seed, with respect to the spiritual blessings of it, which are everlasting, and are never taken away, or become void' [GENESIS_17_7_S00].*
>
> *5. On the covenant's fulfillment in Christ: 'Which is shed for many, for the remission of sins; that is, was very shortly to be shed, and since has been, for all the elect of God... whereby the full forgiveness of all their sins was procured' [MATTHEW_26_28_S03]."*

Reading the answer against the raw Genesis 9:9 chunk confirmed the framing is faithful, not merely more cautious: *"And I, behold, I establish my covenant with you, &c.] **Not the covenant of grace in Christ, but of the preservation of the creatures in common**, a promise that they should not be destroyed any more by a flood..."* Gill himself is doing the distinguishing in his own verse commentary. The Step-3 opener (*"Gill distinguishes the covenant of grace from other covenants"*) uses a forbidden Zone-3 verb but summarizes a claim genuinely supported by every quote that follows.

### The concrete finding worth naming

**"Administration of the covenant of grace" is Gill's own verse-local language, not an imported systematic label.** The Matt 26:28 quote returned by the Step-3 answer reads verbatim: *"the new administration of the covenant of grace, for which reason it is called the New Testament, is exhibited and established in the blood of Christ..."* Gill himself uses "administration" language at Matt 26:28.

The 2026-06-22 launch-week sin was NOT the vocabulary. It was **taking Gill's verse-local usage and systematizing it into a tradition-level label** — the "ultimate unity in grace" thesis dressed in "administrations" language, unmoored from any specific quote, presented as Gill's overall doctrinal position. Zone 3 is precisely: elevating Gill's verse-anchored vocabulary into a systematic position claim the quotes don't collectively support. This is a more precise empirical definition of Zone 3 than the original definition in this ADR, discovered by reading run 1 against the source rather than by writing.

### Non-determinism observed — validates the multi-run discipline

A second run of the same query (2026-07-05, same seed=0, same prompt) produced a substantively different answer with a different quote set AND a new Zone-3 pattern in the closing sentence:

> *"These distinctions suggest Gill does not treat all covenants as one unified 'monocovenantal' system."*

This slips the assertive-verb pattern set (`distinguishes/affirms/holds/teaches/supports/advocates/maintains/leans/takes`) — the phrasing *"these distinctions suggest Gill does not treat"* is an inference-form Zone-3 pattern the current lexical scan will not catch. Single-run testing under-reports the Zone-3 rate.

### Implications for the layer assignments

- **Layer 1 (prompt) works.** Run 1 was faithful; the prompt shifted what the model reached for — from Westminster-import synthesis to Gill's own verse-anchored distinctions.
- **Layer 2 (runtime lexical) stays narrow-by-design.** Assertive-verb set catches the shallow residue (run 1's `distinguishes` opener). Attempting to also catch inference-form patterns (*"these X suggest Gill..."*, *"Gill does not treat X as Y"*) is the growing-regex-allowlist treadmill this project has explicitly refused elsewhere (BAML sentinel). The lexical scan ships documented as the shallow runtime backstop, NOT as complete.
- **Layer 3 (offline semantic judge) is the real Zone-3 authority** — and gains scope: run async over sampled production answers to Slack (daily, matching the daily_rag_diagnostic pattern), not only over the eval set. That's the net for phrasing-inventions on real traffic — the answers users actually received. Cheap once the judge exists; disproportionate value.

### Layer 3 judge design: three-way classifier, two independent rates

Added 2026-07-05 after Step 4 wired-in smoke evidence. The Step-4 batch produced a covenant answer with three Zone-3 shape variants the lexical scan does not target (pronoun-anchored `he distinguishes`, verb-form `Gill views X as Y`, inference-form `This suggests Gill views...`), most of them true-claim-in-forbidden-shape backed by verified quotes. Spec'ing the judge as a binary "fire on unsupported characterization" would report clean while the model drifts into constantly characterizing truly — until one such characterization is false and the discipline has eroded months prior with no instrument watching.

The judge must answer **two independent questions** per answer:

1. **Is there own-voice characterization of Gill's position?** ("Gill affirms/holds/views/distinguishes/does not treat/etc. X as Y", or pronoun-anchored equivalents, or inference-headed "This/These suggest(s) Gill...") — the **zone-contract question**, measuring prompt-discipline erosion. Yes/no.

2. **If yes: is the characterization substantiated by verbatim material in the answer?** — the **faithfulness question**, measuring actual harm risk. Answer must exist in verbatim quotes the answer already presents (not from external knowledge). Yes/no.

Three-way class per answer:
- `none` — no characterization
- `supported` — characterization present AND substantiated by the quotes
- `unsupported` — characterization present AND NOT substantiated

Two rates reported per run of the eval / per daily production sample (corrected 2026-07-06 — see the drift-correction note below):

- `unsupported_characterization_rate` = **credibility-harm metric**. Target 0. **Hard CI gate.** Firing means Gill's position is being misrepresented — user gets misinformed.
- `supported_characterization_rate` = **ratcheted violation count**. Also target 0. NOT a "compliance monitor" — a violation rate to drive down. Both classes are Zone-3 violations per the core ADR: interpretation of Gill is forbidden AT ALL; accurate interpretation is not permitted, it is a lesser severity of the same violation. The severity split exists so the CI gate can block on credibility harm while the supported count is driven toward zero by prompt pressure and, structurally, by ADR-0009.

Without both rates, drift into "true characterization all the time" reads as clean until the day it's false. With both rates, the erosion is measurable weeks before it becomes a credibility incident.

The judge prompt sketch (for `evals/run_eval.py` extension and the async production sampler):

> *You will read one answer from an assistant that surfaces John Gill's commentary via verbatim quotes. Your task has two independent parts, answered in a strict JSON output.*
>
> *Part 1: Does the answer contain any sentence characterizing Gill's overall position, doctrine, view, stance, or teaching in the assistant's own voice (whether anchored as "Gill", "he", or by inference like "these distinctions suggest Gill...")? Answer yes/no.*
>
> *Part 2: If yes to Part 1, list each such characterizing sentence, and for each, judge whether the characterization is substantiated by the verbatim quoted material in this answer (not by external theological knowledge, only by what the answer itself presents). Answer supported/unsupported per sentence.*
>
> *Output JSON: `{"any_characterization": bool, "characterizations": [{"sentence": str, "substantiated": bool}]}`.*

Combined report structure per answer: `class` ∈ {none, supported, unsupported} (supported if all characterizations substantiated; unsupported if any is not). Rates aggregated across the run.

### Drift correction (2026-07-06)

Between the initial Layer-3 spec and this correction, the reporting language for the two rates drifted. The first version framed `unsupported` as "credibility metric, alert-worthy" and `supported` as "prompt-compliance metric — not a bug, tracks how hard the model is straining." That framing softened into a permission taxonomy — one class was violation, one was drift-to-monitor. That reading contradicts the core ADR: **the zone contract forbids interpretation of Gill at all.** The severity split is a measurement axis for how to prioritize enforcement, NOT a permission axis where "accurate interpretation" is tolerated behavior.

The corrected reading is above (both classes = violations, target zero for both, hard gate on `unsupported`). The three-way classifier survives unchanged as an instrument.

The drift matters as a pattern, not just a wording fix. The whole reason ADR-0009's structural elimination is the endgame is that discipline expressed as a rule can slide; discipline expressed as an unrepresentable state cannot. The correction restores the record to the design; ADR-0009 is where the record and the behavior stop being separable at all.

### Layer-2 amendments (added 2026-07-06 after Step-3 tightening smoke)

Two structural additions to `_suppress_zone3` after the smoke evidence:

1. **`_strip_trailing_prose` — the bookend rule as an invariant.** Any substantive prose (2+ alphabetic characters) after the final `[SID]` in the answer is trailing editorializing — the empirically-observed site of closer violations that route around the assertive/negation lexical sweep because they lack a Gill-verb anchor (e.g., *"emphasizing its distinctiveness from the old covenant"* trailing a citation). This is a **positional** check, not lexical: cannot be routed around by rephrasing, because any closer prose after the final citation is excised regardless of its wording. Answers with no citations (flat refusals) are left alone. Wired to run after the assertive/negation sweep on the finalized answer inside `forward()`. This is the same "enforce required structure" move as the BAML sentinel — don't enumerate bad shapes, require the good shape.

2. **Disclaimer-but preservation template.** Detects the compound `Gill does not use the (modern) term "X"[,] but [Zone-3 clause]` and, when the sweep fires on the thesis in the but-clause, replaces the whole sentence with just the disclaimer clause (`Gill does not use the term "X".`). Prevents the sweep from eating the unprompted anachronism disclaimer that emerged on covenant and psalmody — a preservation not just of prose but of the best Zone-1 behavior the prompt has produced. Handles both American typography (comma inside the closing quote) and British (comma outside).

Neither is a growing-regex-allowlist add: the trailing-prose check is a single positional property (answer ends on `[SID]`); the disclaimer branch is a single compound-shape recognizer that either fires or doesn't. No new lexical patterns; no new adversarial surface to chase.

### Bookend rule (added 2026-07-06 — the empirically observed violation site)

Every Zone-3 violation caught in production or testing has been a bookend. The launch covenant opener ("Gill distinguishes between different covenantal administrations while affirming their ultimate unity in grace"). The run-2 closer ("These distinctions suggest Gill does not treat all covenants as one unified 'monocovenantal' system"). The current-pod closer ("This suggests Gill views the covenant of grace as..."). The prod psalmody closer ("These examples illustrate Gill's view of singing as integral to worship"). The flagship opener ("Gill distinguishes the covenant of grace from other covenants in the following ways:"). Openers and closers, every single one — the model wants to open with a thesis and close with a synthesis, and the quote-bearing middle is consistently clean.

Enforcement in the Step-3 prompt (see `backend/bot.py::GillSignature`): open with the Zone-1 navigational bridge (or the Zone-1 gap statement for a refusal) and nothing else — no thesis about what Gill holds. Close on the final verbatim quote + [SID] — no concluding paragraph, no synthesis, no "these examples illustrate", no "this suggests". The reader closes the loop themselves; that is the entire design of this tool.

The judge tracks bookend `position` on each detected characterization so drift into the middle (should it occur) is separable from the bookend rate.

### Label-import rule (added 2026-07-06)

Locating Gill relative to a MODERN doctrinal label or systematic category that appears in NONE of the retrieved quotes is `unsupported`, even when phrased as a negation ("does not take the monocovenantal position") and even when the answer's shown distinctions might seem to derivably support the mapping. The mapping onto the modern category is itself an interpretation the quotes must supply, not one the model supplies. Fixed the run-2 closer classification; calibrated 6/6 with 100% consistency across the labeled examples on 2026-07-06.

### Zone-1 constraint (added 2026-07-06)

The Zone-1 bridge is also in scope for the leading-bias check. A permitted bridge maps the question to the material navigationally: *"'Monocovenantal' is a modern term Gill doesn't use; his material treating the covenant of grace in relation to other covenants follows."* A forbidden bridge predicts the verdict before Gill speaks: *"Your question about monocovenantalism relates to Gill's distinctions between covenants."* The word *distinctions* has already asserted a Gill position — Zone 3 wearing Zone 1 grammar.

### The design in three lines

- The model interprets the USER's question in Zone 1 — shown, owned, purely navigational.
- Gill speaks verbatim in Zone 2 — shown, verified by ADR-0006 + the Step-4 sweep + this judge.
- The model's interpretation of Gill (Zone 3) — TODAY (prose world) has no designated place: strict policy is don't emit (prompt), excise leaks (sweep), count survivors (judge). END-STATE (ADR-0009 schema world) lives in a `zone3_notes` field with no path to the screen, kept as telemetry for the judge's calibration and as a per-answer leak detector via cross-referencing against rendered fields. The release valve remains a Phase-2 A/B hypothesis; adopted only if the with-valve arm shows less Zone-3 leakage in the rendered fields than the without-valve arm.

The asymmetry is the product, not a compromise. Interpreting the user is necessary — bridging "monocovenantal" or "exclusive psalmody" into Gill's idiom is the entire reason the tool beats a page scan. Interpreting Gill is the one thing the tool promises never to do — that's the difference between it and every chatbot, and it's what lets a reader trust an amber badge and a green one.

### Step 6 re-scoping (added 2026-07-06 after low-traffic reality check)

Original framing gated Step 6's formal multi-run A/B on "a week of production rates" from the 5b sampler. That gate was a category error. It conflated:

  - the **formal A/B experiment** — a controlled multi-run measurement on the flagship cases (`covenant_monocovenantal`, `gill_aquinas`, `exclusive_psalmody`), which measures the fix's effect on chosen inputs
  - **ongoing production monitoring** — an opportunistic instrument that catches whatever real queries happen to appear

They answer different questions. The tool is very infrequently used; real production volume is low enough that a "week of production rates" would collect ~20 answers, not a rate. Gating the formal proof on that data was gating it on data that won't arrive.

Re-scoped:

**Step 6 (the formal A/B) is a controlled experiment, runnable now.** Pre-fix and post-fix N=5 runs on each of the three flagship cases against the settled post-`2f2d975` configuration. The pre-fix substrate is captured from prod-log rescore + frozen eval-set answers from the 2026-06-22 launch. Post-fix runs against the deployed test cluster. Pass criteria remain as originally specified in the ADR (`unsupported_characterization_rate == 0` in ≥3/5 pre-fix and 0/5 post-fix). No production traffic needed.

**Ongoing monitoring runs indefinitely as two permanent instruments** (Phase 1 Steps 5b + 5c, both scheduled daily at 12:00/12:30 UTC in `pipeline/__init__.py`):

- **5b — Zone-3 production sampler**: queries Langfuse for the last 24h of `/api/search` traces, applies the calibrated judge N=3 per answer, reports the majority-vs-any-flag distribution, fires an escalation alert on any single unsupported flag. Opportunistic; at low traffic it may report 0-3 answers per day. Value = catches real user impact when it happens.
- **5c — Zone-3 eval-set replay**: runs the 28 curated eval cases through the deployed bot daily and judges them the same way. 84 controlled verdicts/day regardless of traffic. Value = watches judge stability and prompt drift over time on inputs we chose. Same report shape as 5b so they're directly comparable.

Both post a daily record. Both also emit a **separate high-visibility escalation alert** (not buried in the daily summary) when any answer classifies unsupported — the safety-net that works at any traffic level without depending on a human reading Slack. Optional at-mention via `ZONE3_ESCALATION_MENTION` env.

The distinction the review named: 5c measures whether the instrument and substrate are stable; 5b measures whether real answers are faithful. 5c doesn't replace 5b — it fills the low-traffic gap while 5b captures whatever real queries trickle in.

### Step 6 results — the formal proof-of-record (executed 2026-07-07)

Ran the controlled A/B on the three flagship cases against the settled post-`2f2d975` configuration. Pre-fix baseline was the 2026-06-22 launch-week prod-log answers (frozen, small N); post-fix was N=5 fresh runs against the deployed test cluster at commit `128d22a`. Every answer judged N=3 by the calibrated Zone-3 judge (Claude Sonnet 4), classified by majority-of-3. The five covenant post-fix answers were also read end-to-end against the source before writing this up — the rate is the proxy, the text is the truth.

**Per-case results:**

| Case | Pre-fix (frozen) | Post-fix (N=5 fresh) | Verdict |
|---|---|---|---|
| covenant_monocovenantal | The launch-week Zone-3 exemplar (*"Gill distinguishes between different covenantal administrations while affirming their ultimate unity in grace"*) — 1/1 unsupported | **0/5 unsupported**, 5/5 supported (mild navigational residue — see the read below) | **PASS** — the specific launch-week violation is eliminated; the settled config produced zero unsupported characterization across five fresh runs |
| gill_aquinas | 2 flat canned refusals (unhelpfully silent on a query where the corpus HAS Philip Aquinas material) | **0/5 unsupported**, 5/5 none, 3/5 informative shape | **PASS** — tool went from silent to helpfully honest without introducing credibility-harm |
| exclusive_psalmody | 3 flat canned refusals (unhelpfully silent on the most-refused topic from real launch traffic) | **0/5 unsupported**, 5/5 none, 5/5 informative shape | **PASS** — same shape transformation, cleaner (5/5 informative) |

**Note on the covenant claim precision.** Pre-fix N=1 cannot establish a rate — one captured launch-week answer is enough to establish that the old configuration *produced* the violation (the answer is the evidence), but the strong claim is scoped correctly: the specific documented Zone-3 violation is eliminated, and the post-fix produces no unsupported characterization across N=5 fresh runs. That's the defensible form.

**Overall: 0/15 unsupported across all post-fix runs.** No escalation-worthy answers under the drift-corrected ADR.

#### The read of the five covenant post-fix answers

Before certifying the ADR, read all five verbatim end-to-end against the source, checking three things the rates can't:

**Faithfulness — verse-anchored, and the distinctions are Gill's own.** Every run surfaces the same three quotes: Gen 9:9 (*"Not the covenant of grace in Christ, but of the preservation of the creatures in common..."* — Gill himself performing the "Not X, but Y" distinction in the quoted text), Gen 17:7 (Gill's own natural-vs-spiritual seed distinction), Matt 26:28 (Gill's own verse-local "administration of the covenant of grace" language, verbatim). The API's verifier passed every quote. The distinctions the answer *names* are literally enacted in the quoted material.

**Severity of the `supported` residual — mild navigational, not systematizing.** The characterization in every run is the opener: *"Gill does not use the term 'monocovenantal,' but he distinguishes the covenant of grace from other covenants."* This is a permitted Zone-1 anachronism disclaimer (first clause) plus a mild pronoun-anchored `he distinguishes` (second clause). The judge correctly flags the second clause as characterization — it IS interpretation — but it's the mildest possible form: it summarizes what the quotes will *show*, uses `he` (semantic-judge territory), doesn't systematize, and adds no content beyond what the quotes literally enact. This is qualitatively different from both the launch-week violation (which added the "ultimate unity in grace" thesis unmoored from any quote) and the run-2-style inference-form closer (which would map onto the modern "monocovenantal" label). It's exactly the residue that has no field to live in under ADR-0009's schema — hence the schema is the structural fix, not a prompt turn.

**Readability — John 6:37 register held.** Fluent framing-quote-framing-quote prose. Not a numbered list. Not stilted. Runs 1, 3, 5 are byte-identical (874 chars — KV-cache determinism); runs 2 and 4 vary slightly in retrieval order but read the same register. The readability trade the bookend rule required has held on the case most likely to have broken it.

#### What the A/B formally proves about the fix

1. **The covenant question that produced launch week's tradition-misrepresenting synthesis now returns faithful, verbatim, verse-anchored Gill** with only a mild navigational opener as residual — the same question, closed from the source it opened against.
2. **The tool went from unhelpfully silent to helpfully honest** on aquinas and exclusive_psalmody — two query classes that produced flat canned refusals at launch despite the corpus having adjacent material. Post-fix surfaces that material in the informative-refusal shape with zero credibility-harm violations introduced. The psalmody transformation is especially load-bearing given psalmody was the most-refused topic in real launch traffic.
3. **The residual on covenant is stable, low-harm, and honestly monitored** — mild pronoun-anchored navigational openers that summarize enacted distinctions. Not on fire. Not degrading. Structurally eliminated in Phase 2.

Step 6 is the formal proof-of-record the ADR was designed to produce. Phase 1 is complete on its own terms — both what it stopped (harm) and what it enabled (help). Phase 2 (ADR-0009 structured answer generation) is where the mild residual gets structurally eliminated rather than prompt-suppressed; it deserves its own dedicated phase, not a piecemeal start alongside other work.

### Zone-3 leak rate reporting (mandatory, not optional)

Step 4's validation MUST be an N=5 multi-run A/B on `covenant_monocovenantal`, `gill_aquinas`, and `exclusive_psalmody`, with **honest rate reporting**. Pass criteria:

- Assertive-form Zone 3 (lexical class): zero across all post-suppression runs
- Inference-form Zone 3 (semantic-judge class): reported as leak rate X/N, with the semantic judge named as its designated catch — NOT declared clean by omission

"Step 4 shipped, covenant clean" without the rate breakdown is the dormant-bug trap in a new disguise. Report what the lexical layer catches; report what escapes; name what will catch what escapes; do not conflate silence with cleanliness.

## Related ADRs

- [ADR-0004: Reference eval set and CI gates](0004-reference-eval-set-and-ci-gates.md) — the eval framework this ADR extends with semantic Zone-3 judgment.
- [ADR-0006: Verbatim quote verification](0006-verbatim-quote-verification.md) — the verifier that protects Zone 2; this ADR extends protection to the framing around it.
- [ADR-0007: Availability and outage fallback](0007-availability-and-outage-fallback.md) — the SPA shell that will host the gutter UI.
- **ADR-0009 (forthcoming): Structured answer generation** — Phase 2 architecture that supersedes the gated-streaming unit-boundary design (structure provides units natively), simplifies the ADR-0006 verifier to per-field checks, and shrinks (but does not eliminate) the Zone-3 surface. Includes the schema-safe release valve as a log-don't-discard field. Sequenced after Phase 1 Steps 4–6 complete on the current architecture.

## Notes

This ADR is the architecture for the Phase 1 work item from the post-launch fix sequence (see `c:/tmp/post-launch-analysis/POST_LAUNCH_ANALYSIS.md` and the Phase 0 commits adding `real_covenant_monocovenantal_001`, `real_garden_genesis_3_24_misattribution_001`, `real_singing_psalms_001`, `real_matthew_28_17_period_001`, `real_gill_aquinas_001`, `real_exclusive_psalmody_001` to the reference set). The Phase 0 instrument was specifically designed to catch what this ADR's architecture is designed to prevent.

A validation discipline that the design process surfaced and that should be carried into implementation: **multi-run live A/B against the deployed system, not single-run live or frozen-log rescore alone.** State drift means a single live run after the fix can't distinguish "fix worked" from "bug dormant." The fix is validated only when (a) the pre-fix prompt produces Zone-3 violations across N runs of `covenant_monocovenantal` and `exclusive_psalmody`, AND (b) the post-fix prompt produces zero across the same N runs.
