# ADR-0014: Fail Loud or Fail Closed, Never Fail Different

- **Status:** Accepted
- **Date:** 2026-07-26
- **Deciders:** Chris Nogradi

## Context

The whole project is built to remove nondeterminism. [ADR-0008](0008-three-zone-generation-and-voice-marked-ui.md) and the ADR-0010→0013 chain took the coin-flips out of the *models'* hands: BAML's entity pick may not gate a deterministic manifest (the standing rule, *"a stochastic component may never be authoritative over a deterministic one"*). The 2026-07-19/20 `universal_atonement` investigation found the same class of nondeterminism one layer down — **in the infrastructure, not the models.**

`get_relevant_entities` (backend/gill_search.py) runs three tiers: (1) `near_vector` on a qwen3 embedding, (2) substring canonical-key, (3) BM25. Tier 1 depends on litellm (the embedding gateway). When litellm blips, Tier 1's embedding call raises, `vector_names` silently goes empty, and Tiers 2/3 run alone — producing a **different manifest built by a different algorithm**, with nothing recording that it happened.

The consequence is not degraded latency; it is a **different answer**. For `"Did Jesus preach a universal atonement?"`:

- **Vector tier healthy** → manifest `[preaching of the Gospel, preachers of the everlasting Gospel, ...]` → retrieval reaches gospel/doctrinal chunks → answer expresses Gill's particular-redemption position ("all the Lord's people").
- **Vector tier degraded** → manifest `[atonement, day of atonement, ...]` → the ceremonial homonym pulls Leviticus ritual chunks → answer collapses to a one-chunk universalist reading.

Same query, same corpus, same code — the *infrastructure's health that second* decided which doctrine the tool preached. This availability→correctness coupling is the worst kind of dependency, and it is exactly what produced the manifest **bimodality** that cost three successive wrong attributions during the investigation: everyone debugged the code because nothing recorded that the infrastructure had silently chosen a different algorithm that hour.

This is the **fourth** silent boundary found by accident (after the substring flood, BAML's entity drops, and the dead `daily_rag_diagnostic`) — each present for months, each a stage that logged only one side. The instrumentation audit item ("find the fourth boundary logging one side") found itself in the wild.

## Decision

### The design law

> **Fail loud, or fail closed — never fail different.**

A fallback that produces materially different behavior is not graceful degradation; it is **silent substitution** — a different, worse system wearing the same API. Graceful degradation is when the degraded output is a *strict subset* or a *visibly-weaker version* of the healthy output, produced the same way every time, and **marked**. Substring-only entity lookup is not that: E-9 (poisoned-manifest suppression) already proved a bad manifest is worse than no manifest, and the substring-only manifest is precisely the bad-manifest condition (the ceremonial collapse). So the old fallback wasn't a lesser service — it was a different one.

This law sits beside the standing rule as the second half of the project's architecture:
- *A stochastic component may never be authoritative over a deterministic one* — took the coin-flips out of the models' hands.
- *Fail loud or fail closed, never fail different* — takes them out of the infrastructure's.

### Dependency classification

Every external dependency is classified, explicitly, as one of two kinds. No fallback may be written without deciding which kind the dependency is.

- **Load-bearing** — the retrieval substrate itself. **Fail closed** with an honest error; there is no deterministic floor beneath it.
  - Weaviate (the corpus / chunk index).
  - The **query embedding** in `search_gill` — the dense side of hybrid retrieval. `_get_embedding` raises `"Theology Vector Engine is currently offline"` and `search_gill` does not catch it, so a full litellm outage already fails the request closed. Correct and unchanged.

- **Enrichment** — a signal that *improves* retrieval but is not required for it. **Degrade to the deterministic floor, and mark the mode.**
  - The **entity vector tier** in `get_relevant_entities`. When its embedding fails, the manifest it would have built is unavailable. The floor is: **no entity boost** (raw query + BAML expansion hybrid retrieval, which is the same every time), not the substring-only manifest.

The key operational nuance: because `search_gill`'s query embedding is load-bearing, a *full* litellm outage fails the request closed one step later regardless. The entity-tier degradation only bites in the **transient-blip window** where the entity-tier embedding fails but `search_gill`'s recovers — which is exactly the window that produced the observed bimodality.

### Implementation

1. **`get_relevant_entities` returns `(names, mode)`** where `mode ∈ {"full", "degraded_no_vector"}`. The flag starts `True`, is cleared only in the vector-tier `except`, so `"full"` means the vector tier executed (even if it found zero confident matches — a healthy "no hit" is not a degradation).

2. **Fail-anchored gate in `main.py`.** When `entity_lookup_mode != "full"`, `mapped_entities` is forced to `[]` immediately before `search_gill`, **overriding** every upstream boost decision (ADR-0013 Part C/D, ADR-0012), because all of them trusted a manifest built by a tier that wasn't running. Retrieval proceeds on the deterministic floor. Logged as `baml_fallback: "vector_tier_degraded_suppressed"`.

3. **Instrumentation on every request.** `entity_lookup_mode` is written to `stages_capture` and to Langfuse trace metadata. The daily Zone-3 sampler (ADR-0008 Step 5b) counts `degraded_no_vector` answers per window and surfaces the count in the Slack report with a ⚠️ at >0 — so a litellm blip announces itself the same morning instead of surfacing as a theological error weeks later.

### Why anchored degradation, not fail-closed-entirely, for the entity tier

Three policies were weighed for the litellm-down case:

| Policy | Behavior | Verdict |
|---|---|---|
| Fail different (old) | substring-only manifest → boost on ceremonial lexical noise → possibly-wrong answer, indistinguishable from healthy | The bug. Now proven harmful. |
| Fail closed entirely | refuse the request | Honest but harsher than needed — denies users the verse-lookup (pure regex) and thesaurus (pure string-match) paths that are entirely litellm-independent and still correct. |
| **Anchored degradation** (chosen) | drop the boost, retrieve on raw + expansion, mark the mode | Deterministic, honest, still useful. Consistent with E-9: *when the signal is bad, no boost beats bad boost.* |

Anchored degradation is the same policy as ADR-0012's poisoned-manifest suppression, extended from *"gemma rejected the manifest"* to *"the infra that builds good manifests is unavailable."* When the reliable path can't run, run **less**, not **different**. The `means of grace` evidence (raw-query retrieval scored 0.712→0.731 *without* any boost) shows the floor is frequently good enough — the boost was always an amplifier, not a foundation.

**Queueing** (defer the request until litellm returns) is explicitly out of scope and, on reflection, the wrong shape: it converts an infra outage into a user-state, delivery, and staleness problem to preserve an *enrichment* tier the system already has a deterministic floor beneath. This tool does not manage user state; anchored degradation gets ~90% of the value with zero new state.

## Evidence

- Mode detection verified offline: a forced embedding failure flips `mode` to `degraded_no_vector`; the healthy path returns `"full"`. During testing, litellm was genuinely down, which reproduced the exact ceremonial manifest `[atonement, day of atonement, ...]` live — the mechanism confirmed against a real degradation, not a mock.
- Sampler wiring verified: `aggregate` counts degraded samples; `format_slack_blocks` renders the ⚠️ line at >0, healthy line at 0.
- The change is **inert under healthy operation** — when `mode == "full"` the gate never fires and behavior is byte-identical, so it cannot regress the eval under normal litellm health. Under degradation it replaces bad-boost with no-boost, which E-9 established is ≥. Safe by construction.

## Closed in the completion commit (same law, two more violations)

Both items originally filed here as follow-ups were closed immediately rather than left as someday-reviews — the law is only a law if known violations get shut while they're cheap:

- **The hardcoded empty-lookup default (fifth "fail different"), removed.** `get_relevant_entities` used to inject `["Jesus Christ", "Apostle Paul", "Old Testament saints"]` when no tier matched — a *fabricated* manifest that then boosted retrieval toward Jesus/Paul chunks precisely on the drought case, when the honest signal was "no entity anchor exists." Its fingerprint was visible in the pre-fix `pxlusive psalmoly` trace (Jesus/Paul apocalyptic material at the top). Now: empty lookup → empty manifest → no boost, same E-9 logic. The caller retrieves on the raw + expansion floor.
- **The thesaurus vector tier, made loud.** `expand_query` (ADR-0011 v3) shares the litellm dependency and silently emptied its vector/span tier on embed failure — a "fail different" the entity-mode gate misses in the transient-blip case where the thesaurus embed fails but `get_relevant_entities`' succeeds. Now `expand_query` returns `vector_degraded`, and main.py folds it into `entity_lookup_mode`: *either* vector tier degrading marks the request degraded and suppresses the boost. The exact/fuzzy tiers (pure string-matching, litellm-independent) still fire, so a well-spelled query is unaffected. With both closed, **the law has zero known open violations.**

## What this ADR does NOT solve

- Retroactive caveat: **any committed probe evidence whose result depends on manifest composition is mode-ambiguous** — E-6b manifests, E-9 verifications, and the E-11 sweep each ran in whatever litellm health dictated that hour, unrecorded. E-11's `atonement` "no hijack" verdict is explicitly conditional on a healthy tier. Those evidence sections should carry a one-line note: *"manifest-dependent; predates mode instrumentation — re-run with mode recorded before treating as unconditional."*

## Consequences

**Positive:**
- Infrastructure health can no longer silently change which answer a user gets. The failure announces itself (Slack ⚠️) or fails closed (load-bearing), never disguises itself as a plausible different answer.
- The bimodality that cost three wrong attributions is eliminated: degraded mode is now a recorded, single, weaker-but-consistent floor.
- The dependency-classification exercise is the instrumentation audit's constructive form: every external dependency now has a declared answer to *"what happens when you're gone — loud, closed, or different?"* and *different* is a bug by policy.

**Negative:**
- During a litellm blip, entity-boosted queries lose the boost and get weaker (but honest, and marked) retrieval. Acceptable — the alternative was a wrong doctrinal answer.
- One more field on every trace and one more Slack line. Negligible.

**Neutral:**
- Eval-gating per the reinstated discipline — **RUN and RECORDED 2026-07-26**, and it did NOT show the predicted no-delta, which is exactly why the discipline says run-don't-waive. The gate (831e116, test) scored 13/28 vs the 13-day-old cleanrun's 18/28, five questions flipping PASS→FAIL. Investigated via ADR-0014's own instrumentation rather than assumed:
  - All five flipped questions ran `entity_lookup_mode = "full"` (the fail-anchored gate never fired) with populated manifests (the empty-default removal never triggered). So neither ADR-0014 change touched their code path.
  - The answers are correct: `moses_death` returned *"Moses died in the mountains of Abarim, before Nebo [NUMBERS_33_47_S00]"* — right answer, required citation present (`must_cite_missing=[]`), failing only on `verif_ok=False` (the bot paraphrased, the verbatim verifier flagged it). `exclusive_psalmody` returned the correct verified Hallel exposition.
  - `scapegoat` flipped FAIL→PASS across two consecutive runs on the same build — direct evidence of run-to-run generation variance.
  - Conclusion: the delta is **generation-variance at the verbatim-verification / paraphrase boundary** (the peter-class Zone-2 issue), not an ADR-0014 retrieval regression. ADR-0014 is confirmed inert under healthy litellm, as designed — the instrumentation proved it in minutes.
- **Meta-finding for the discipline:** the eval binary carries ±several-question run-to-run noise from generation nondeterminism at the verified boundary. Single-run before/after comparisons (including this whole attribution exercise) inherit that noise. The correct gate is not "did the number move" but "did any flipped question flip *because of the code path touched*" — answerable via the mode/manifest instrumentation, as here. A 1–2 (or more) question delta with correct answers and unchanged code paths is noise, not regression.

## References

- Standing rule origin: [ADR-0013](0013-two-pass-entity-lookup-and-refusal-path-gill-only.md) ("a stochastic component may never be authoritative over a deterministic one").
- [ADR-0012](0012-poisoned-manifest-fallback-suppression.md) — the "bad signal → no boost" policy this ADR extends from gemma-rejection to infra-unavailability.
- The `universal_atonement` / ceremonial-homonym investigation and the E-11 sweep (`evals/e11_ceremonial_homonym_sweep/`) that surfaced the bimodality.
