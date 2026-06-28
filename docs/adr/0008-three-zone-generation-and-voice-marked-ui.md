# ADR-0008: Three-Zone Generation Architecture and Voice-Marked UI

- **Status:** Proposed
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

#### Optional: the Zone-3 release valve

Instruction-tuned models tend to comply better when given a channel for an impulse than when flatly forbidden. The prompt MAY optionally instruct the model to emit its Zone-3 slant into a designated discardable field (e.g., a `<interpretation>...</interpretation>` block or a tagged Zone-3 segment) that the backend strips before the response leaves the API. The field doubles as ground truth for the runtime classifier and the offline eval — what the model *wanted* to say about Gill's position, recoverable from logs without ever reaching the user. This is exploratory; we will measure whether it improves Zone-2 cleanliness relative to flat prohibition.

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

### Runtime-level (Phase 1.5 or 2)

```python
# backend/streaming.py — new module

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

## Related ADRs

- [ADR-0004: Reference eval set and CI gates](0004-reference-eval-set-and-ci-gates.md) — the eval framework this ADR extends with semantic Zone-3 judgment.
- [ADR-0006: Verbatim quote verification](0006-verbatim-quote-verification.md) — the verifier that protects Zone 2; this ADR extends protection to the framing around it.
- [ADR-0007: Availability and outage fallback](0007-availability-and-outage-fallback.md) — the SPA shell that will host the gutter UI.

## Notes

This ADR is the architecture for the Phase 1 work item from the post-launch fix sequence (see `c:/tmp/post-launch-analysis/POST_LAUNCH_ANALYSIS.md` and the Phase 0 commits adding `real_covenant_monocovenantal_001`, `real_garden_genesis_3_24_misattribution_001`, `real_singing_psalms_001`, `real_matthew_28_17_period_001`, `real_gill_aquinas_001`, `real_exclusive_psalmody_001` to the reference set). The Phase 0 instrument was specifically designed to catch what this ADR's architecture is designed to prevent.

A validation discipline that the design process surfaced and that should be carried into implementation: **multi-run live A/B against the deployed system, not single-run live or frozen-log rescore alone.** State drift means a single live run after the fix can't distinguish "fix worked" from "bug dormant." The fix is validated only when (a) the pre-fix prompt produces Zone-3 violations across N runs of `covenant_monocovenantal` and `exclusive_psalmody`, AND (b) the post-fix prompt produces zero across the same N runs.
