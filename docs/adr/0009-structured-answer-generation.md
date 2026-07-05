# ADR-0009: Structured Answer Generation

- **Status:** Proposed (sequencing note: build ONLY after ADR-0008 Phase 1 Steps 4–6 complete on the current architecture)
- **Date:** 2026-07-05
- **Deciders:** Chris Nogradi

## Context

Phase 1 of ADR-0008 (three-zone generation) enforces the zones by *discipline*: prompt instructions telling the model what not to write into free prose, then a shallow lexical scan and a semantic judge hunting violations. The Step-3 covenant flagship (see ADR-0008's Validation Notes) proved the prompt shifts what the model reaches for — from Westminster-import synthesis to Gill's own verse-anchored distinctions — but two subsequent findings surfaced simultaneously:

1. **Same-query non-determinism produces different Zone-3 shapes across runs.** The 2026-07-05 covenant re-run produced *"These distinctions suggest Gill does not treat all covenants as one unified 'monocovenantal' system"* — an inference-form Zone-3 phrasing the assertive-verb lexical scan cannot catch. Every regex added invites a new invented phrasing that routes around it. That's the growing-regex-allowlist treadmill this project has explicitly refused elsewhere.

2. **Verifier extraction fragility and streaming unit-boundary complexity persist** from ADR-0006 and ADR-0008 respectively — both of them consequences of the answer being unstructured prose that has to be regex-parsed after generation. The gutter UI (ADR-0008 Layer 4) also has to reconstruct voice and quote boundaries from the same prose.

Free prose is the common cause of all three problems. The zones are defined crisply enough (Zone 1 owned interpretation / Zone 2 Gill verbatim / Zone 3 forbidden slant) to become *fields*. If the output schema has no field for Zone 3, "Gill's position on the covenant of grace is..." has nowhere to live: it becomes structurally homeless. Attack surface shrinks; verification simplifies; streaming and UI fall out for free.

## Decision

Replace the free-prose `answer` string emitted by `GillSignature` with a **structured schema** enforced by BAML (bot side, DeepSeek). The schema has a slot for the owned interpretive bridge, a repeated slot for each verbatim quote with its structural neighbors, an optional refusal variant, and — pending A/B — a `zone3_notes` sinkhole that never renders to the UI but IS logged for observability.

### Sketch

```baml
class GillAnswer {
    zone1_interpretation string?     @description("Model's owned bridge from user's modern phrasing to Gill's idiom. Emitted only when mapping a modern term to a period equivalent. NEVER claims a position Gill holds.")

    phrases Zone2Phrase[]            @description("Ordered list of quote units. Each unit is one framing + one verbatim quote + one SID. Empty list if the response is a refusal.")

    refusal GillRefusal?             @description("Present when the answer is a refusal. Mode declares which shape.")

    zone3_notes string?              @description("Model's own read of Gill's overall position. NEVER RENDERED to the UI. Logged only. See A/B mitigation below.")
}

class Zone2Phrase {
    framing string                   @description("Orienting words leading into the quote. Names the verse or notes the connection. May NOT state any position Gill holds. Max ~25 words.")
    gill_quote string?               @description("Verbatim Gill text, inside quotation marks. NEVER paraphrased. Populated OR scripture_quote is, not both.")
    scripture_quote string?          @description("KJV/verse text quoted separately from Gill's commentary. Distinct field so the verifier can check against the biblical source rather than the Gill chunk.")
    ref string                       @description("SID such as [MATTHEW_26_28_S01]. Must match the source of gill_quote or scripture_quote.")
}

class GillRefusal {
    mode string                      @description("'informative' for corpus-adjacent miss, 'flat' for category error / off-topic / abuse.")
    gap_statement string             @description("Zone-1 owned statement of what the corpus does not contain. E.g. 'the indexed corpus does not contain Gill's commentary on Thomas Aquinas'.")
    adjacent_phrases Zone2Phrase[]   @description("Adjacent material surfaced with disclaimer. Empty for flat refusal.")
}
```

### What structure does

- **Zone 3 has no slot.** *"Gill's position on X is..."* cannot be emitted into a `framing` field described as "orienting words only, may NOT state any position Gill holds," because that description is part of the prompt the schema generates. Not eliminated — see Limits — but categorically shrunk.
- **Verification is a per-field loop, not a regex-extraction pass.** For each `Zone2Phrase`: difflib `gill_quote` against the chunk for `ref`. No 80-char quote-and-SID pairing, no missed pairings when the model deviates from the format.
- **Scripture-vs-Gill disambiguated structurally.** The 2026-06-22 Garden failure (a Scripture quote cited to a Gill SID, verifier flagged no-Gill-quote) becomes unrepresentable — the model declares which source, the verifier checks against the right source. Garden class of confusion goes away.
- **Streaming unit boundary is native.** Each `Zone2Phrase` is a natively delimited unit. BAML supports streaming structured output per-field, so the gated-streaming design deferred in ADR-0008 Phase 2 gets its missing enabler.
- **Gutter UI renders directly.** `zone1_interpretation` → interpretation callout. `phrases[].framing` → Zone-1 lane. `phrases[].gill_quote` → Zone-2 lane with verified chip from per-phrase verifier result. No parsing.
- **Informative-vs-flat refusal is enforced by shape.** `refusal.mode = 'informative'` requires `adjacent_phrases` non-empty AND `gap_statement` present; `refusal.mode = 'flat'` disallows adjacent_phrases. The distinction becomes structural, not prompt-honored.

### The release valve, done safely

The `zone3_notes` field is the schema-safe version of the ADR-0008 release valve. Two properties make it categorically safer than the deferred prose version:

1. **"Can't fail" instead of "forgot to strip."** The renderer simply has no path from `zone3_notes` to the UI. There is no strip-step to forget. Integration test is one assertion: the field is absent from the SearchResponse serialized to the user.
2. **Free telemetry.** Logged to the same store as the daily RAG diagnostic. Three uses, all cheap:
   - **Training data for the semantic judge.** Step 5 needs labeled Zone-3 examples; the valve manufactures them continuously.
   - **Per-answer leak detector.** If `zone3_notes` contains a claim about Gill's position AND a `phrases[].framing` field contains a paraphrase of that claim, that's a leak — detectable by comparing the model's own two outputs. Catches phrasing-inventions the lexical scan misses.
   - **Drift monitor.** If `zone3_notes` is routinely wild (confident systematic claims far beyond what the quotes support), that's a signal the prompt's prevention is straining; a real diagnostic, not silent success.

## Limits (what structure does NOT do)

- **The framing field is still free text.** Nothing stops the model writing *"which shows Gill rejected monocovenantalism"* into a `framing` slot. Structure makes Zone-3 content **homeless and small**, not impossible. The lexical scan and semantic judge from ADR-0008 Layers 2 and 3 remain necessary — but now they run over tiny labeled 25-word strings instead of open prose, which is dramatically more tractable for both the shallow lexical layer and the deep semantic judge. Do not let anyone frame this as "structure replaces the Zone-3 checks."
- **Fluency risk.** Forcing structure sometimes produces stilted, list-shaped answers. Calibration target is the John 6:37 answer under the current prose architecture — flowing framing-quote-framing-quote. The tuple structure maps onto that interleaving fine IF the connectives are written well AND the renderer joins them into prose seamlessly — but that's an empirical question, not proven. A/B required.
- **Model compliance.** DeepSeek is bot-side, not gemma; DeepSeek handles nested structured output far better than the model that failed a two-field schema all through Phase 1 substrate work. Still needs testing, especially for partial/malformed structure — degradation path must be defined.
- **Zone-3 valve is exploratory.** Even in the schema-safe form, whether the valve reduces framing-field leakage vs. increases it (by legitimizing position-characterizing as part of the task) is an empirical question about DeepSeek under this schema, not something reasonable-out. Ships only if isolated A/B shows it earns its place.

## Alternatives Considered

1. **Extend the ADR-0008 Layer 2 lexical scan to cover inference-form and negation Zone-3 patterns.** Rejected: the run-1/run-2 covenant divergence proves the model invents phrasings; every pattern grows the treadmill; the pattern space has no complete closure. Same lesson as the BAML sentinel (ADR-0008 Notes / substrate hardening arc).
2. **Ship a two-box UI (Gill lane / model lane) with the current prose answer.** Rejected earlier in ADR-0008 for readability; also doesn't address the verifier fragility or the streaming unit-boundary problem. Structure attacks all three at once.
3. **Post-hoc restructure — LLM pass converts prose to structure after the bot answers.** Rejected: doubles model calls, adds a new fragility layer (the restructure LLM can hallucinate), and doesn't shrink the Zone-3 attack surface at generation time (where it matters). Structure must be the *generation* target, not a post-processor.

## Consequences

### Positive

- **Zone-3 attack surface categorically shrinks.** No slot for systematizing claims; the surface reduces to short labeled connective strings that lexical and semantic layers can judge tractably.
- **Verifier simplifies.** Per-field loop replaces regex extraction from prose. Garden-class Scripture-vs-Gill confusion becomes unrepresentable.
- **Streaming unit boundary solved.** Each `Zone2Phrase` is native. BAML per-field streaming is the plumbing.
- **Gutter UI renders directly.** Structure IS the render events.
- **Refusal modes become structural.** `mode = 'informative'` enforced by shape (adjacent_phrases non-empty), not by prompt-honoring.
- **Release valve becomes safe** — no strip-and-forget failure mode; free training/leak/drift telemetry.

### Negative

- **Fluency A/B is a real risk.** If DeepSeek's structured output reads as a numbered list of quote-cards instead of interleaving prose, this is a step backward on readability.
- **Prompt migration is substantial.** The current `GillSignature` docstring (Step 3) has to be rewritten as field descriptions; the bot's `forward()` has to switch from parsing prose to consuming a Pydantic object.
- **DeepSeek compliance is not zero-risk.** Nested structured output failure modes need a defined degradation path (retry? fall back to prose? refuse?).

### Risks

- **Fluency loss undetected.** Mitigation: John 6:37 A/B is the calibration gate; if structured reads worse, defer or rework.
- **Release valve worsens overall leakage.** Mitigation: isolated A/B — schema WITH and WITHOUT `zone3_notes`, measure Zone-3 leakage in rendered fields; drop the field if the valve doesn't earn its place.
- **Structured output invalidates ADR-0006 verifier assumptions.** The verifier is currently regex-based on prose. The structured path replaces the verifier entirely — a per-field difflib loop. Any downstream code depending on the verifier's regex behavior needs auditing.

## Implementation Sketch

### Phase 2.1 — DeepSeek compliance smoke (feasibility gate)

Before writing the migration, verify DeepSeek reliably emits the schema. One-shot compliance test against 10 diverse queries (mix of clean-answer, informative-refusal, flat-refusal shapes). Pass = 10/10 structurally valid JSON with populated required fields.

### Phase 2.2 — John 6:37 fluency A/B

Reassemble the current prose John 6:37 answer from a manually-authored structured version, render both through the target UI (or a text approximation), and compare readability. Pass = structured reads no worse than prose on 3 independent readers, or reads clearly better.

### Phase 2.3 — Migration

- Replace `GillSignature` docstring with field descriptions on `GillAnswer`
- Rewrite `GroundedGillBot.forward()` to consume the Pydantic object instead of parsing prose
- Rewrite the verifier as a per-field difflib loop
- Rewrite the gutter renderer to consume structured events

### Phase 2.4 — Release valve A/B

Isolated same-schema-with-and-without `zone3_notes` comparison, measure Zone-3 leakage in rendered fields across N=10 runs on covenant / aquinas / exclusive_psalmody. Ship the field only if leakage decreases; drop otherwise.

### Phase 2.5 — Streaming enablement

With the schema in place, the gated-streaming design deferred in ADR-0008 Phase 2 becomes tractable. Per-phrase yield, per-phrase verify, per-phrase render.

## Open Questions

- Does DeepSeek reliably emit nested structured output at production quality? (Compliance smoke)
- Does structured output read as fluently as current prose on interleaved framing-quote answers? (John 6:37 A/B)
- Does the release valve reduce framing-field leakage on net, or does legitimizing position-characterizing make the model do more of it elsewhere? (Valve isolated A/B)
- What's the degradation path when DeepSeek emits malformed structured output? Retry / fall to prose / flat-refuse?
- How does the informative-refusal `adjacent_phrases` field interact with cases where the semantic-similarity path surfaces genuinely-relevant material but the entity-boost path doesn't? (Cross-references the entity-lookup two-layer investigation.)

## Related ADRs

- [ADR-0006: Verbatim quote verification](0006-verbatim-quote-verification.md) — the regex-based prose verifier this ADR simplifies to a per-field loop.
- [ADR-0008: Three-zone generation and voice-marked UI](0008-three-zone-generation-and-voice-marked-ui.md) — the discipline-based Zone architecture this ADR structuralizes.
- The gated-streaming design from ADR-0008 Layer 2 Phase 2 becomes tractable via per-phrase yield.
- The gutter UI from ADR-0008 Layer 4 renders directly from `phrases[]`.

## Notes

The insight that made this ADR possible was empirical, not analytical. The 2026-07-05 covenant re-verification produced a run-1 answer that verified faithful end-to-end (the Step-3 flagship win) and a run-2 answer that slipped a Zone-3 inference-form phrasing the entire planned lexical scan would have missed. The reviewer's observation: "the lesson from the BAML sentinel applies exactly: enumerate required properties, not forbidden phrasings — and where you can't define a required property, use the semantic layer, not a longer regex." That framing pointed at structure — a schema is required-properties enforcement at generation time, upstream of both regex and semantic layers. The zones defined crisply enough to become fields is the design that dissolves the free-prose problem into the schema.

### Additional evidence (Step 4 wired-in smoke, 2026-07-05)

After Step 4 (`_suppress_zone3()`) landed and rolled to the test cluster, four consecutive covenant queries produced a Zone-3 shape the lexical scan does not target and cannot target without exploding false positives:

> *"Gill does not use the term 'monocovenantal,' but **he distinguishes** the covenant of grace from other covenants... In Matthew 26:28, he describes the 'new testament' as 'a new dispensation, or administration of the covenant of grace,' ratified by Christ's blood. **This suggests Gill views the covenant of grace as a distinct, enduring covenant, though administered differently across time.**"*

Three shapes appear:
- **`he distinguishes`** — pronoun-anchored assertive form. Adding `(Gill|he)` anchors to the lexical scan would explode false positives on KJV *"he said unto..."* language in surrounding quotes.
- **`Gill views X as Y`** — verb-form of a Zone-3 possessive pattern (*"Gill's view of X"*). Adding *"views/regards/treats X as Y"* to the pattern set adds surface without closing the space.
- **`This suggests Gill...`** — inference-form. Unbounded phrasing variants.

Each is a distinct anaphora / verb-form / inference construction. Enumerating them lexically is the growing-allowlist treadmill. In the structured schema of this ADR, all three become **structurally homeless**: *"he distinguishes the covenant of grace from other covenants"* has to fit inside a 10-word `Zone2Phrase.framing` field whose declared contract is *"orienting words only; never a claim about what Gill holds"*, and the closing systematizing sentence *"This suggests Gill views..."* has nowhere to live — no field carries prose-tier reflective claims. The classifier's job shrinks from "read this 800-token prose for Zone-3 patterns of unbounded shape" to "read this 10-word framing string against its declared contract." That's tractable even for a small model.

This is the permanent answer to the state-drift observation: not a smarter regex (bounded by imagination) and not even a smarter judge (bounded by prompt attention over long text), but **removing the open prose the regex was asked to police**.

### Related instrument design that this ADR extends

The Step 5 semantic judge is being spec'd as a **three-way classifier** reporting **two independent rates** (see ADR-0008 Validation Notes for the concrete design): (1) is there own-voice characterization of Gill's position? — the *zone-contract* / discipline-erosion metric; (2) if so, is it substantiated by the quoted material? — the *faithfulness* / harm metric. Combined as *unsupported-characterization-rate* (credibility signal, target ~0) and *supported-characterization-rate* (prompt-compliance drift indicator).

That instrument survives into the structured schema world unchanged. Under structure, the *unsupported-characterization-rate* stays roughly what it is now (the framing fields are still free strings that can technically house unsupported claims). The *supported-characterization-rate* drops materially — the schema's field descriptions actively teach the model that framing is orienting-only, so much of what today lands as "supported characterization in prose" gets structurally routed either into a quote (Zone 2) or into `zone3_notes` (the log-only sinkhole, if the release-valve A/B favors it). The two-rate reporting stays honest across the migration; the numbers move for interpretable reasons.

### Sequencing

Sequencing is load-bearing: do NOT swap the output architecture mid-Phase-1. Steps 4–6 complete on the current architecture; the lexical backstop and semantic judge are still needed in the structured world (structure shrinks the surface, does not eliminate it); nothing built during Phase 1 becomes wasted. This ADR files the design; Phase 2 executes it.
