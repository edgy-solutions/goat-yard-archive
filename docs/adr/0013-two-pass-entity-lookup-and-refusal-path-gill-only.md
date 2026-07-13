# ADR-0013: Two-Pass Entity Lookup + Refusal-Path Gill-Only Constraint

- **Status:** Accepted
- **Date:** 2026-07-12 (evening)
- **Deciders:** Chris Nogradi

## Context

The 2026-07-12 `exclusive psalmist` failure (see [ADR-0011 v3 amendment](0011-query-expansion-for-narrow-reformed-vocabulary.md#amendment-2026-07-12-evening-v3-vector-tier-reinstated--span-based-matching)) surfaced two distinct architectural gaps in the pipeline, both worth closing regardless of whether the thesaurus tier catches every query:

1. **Entity lookup runs before BAML expansion.** The pipeline currently calls `get_relevant_entities(lookup_query)` first, then feeds the manifest to BAML's `OptimizeSearchQuery`. When the raw query is a narrow concept ("exclusive psalmody") the entity index returns lexical false-positives (Aramaic Talmudic footnote entities, or a mis-disambiguated `Psalmist` biblical figure) rather than the semantically-adjacent concept entities Gill actually uses (`Hallel`, `Book of Psalms`). BAML's expansion — which is expressly good at producing 18th-century-vocabulary paraphrases of modern doctrinal terms — is only used for retrieval text, not entity discovery. The expansion capability is present but structurally under-used.

2. **Informative-refusal path pads with Scripture-verse quotations.** The 2026-07-12 UI answer for `"was gill an exclusive psalmist?"` returned three "nearest indexed material" citations — every one of them a Scripture verse embedded in Gill's commentary (John 2:17 quoting Psalm 69, Luke 20:42 quoting Psalm 110, Mark 12:36 quoting Psalm 110). The chunk-verification path validated these correctly (they *are* substrings of the retrieved chunks), so the amber "Unverified" chip fired only on the answer-shape-level, not the citation-level. The user sees Scripture verses presented as Gill's teaching-adjacent material for a question about Gill's doctrinal position. That is a *lentil trap* in a different form: fishing for tangential material to look helpful when the honest answer is "no Gill commentary on this subject."

## Decision

### Part A — Two-pass entity lookup with manifest union

In [`backend/main.py`](../../backend/main.py), after BAML's `OptimizeSearchQuery` returns successfully, invoke `get_relevant_entities` a second time on `optimized_query.expanded_search_terms`. Union the resulting manifest with BAML's picked entities (`mapped_entities`), deduplicated by lowercase-name, preserving first-appearance order so BAML's picks lead the boost text. Pass the union to `search_gill` as the `entities` argument.

```python
second_pass_entities = await search_engine.get_relevant_entities(query=search_text)
# Union: BAML's picks (highest signal) first, then semantic-recall additions.
# Dedup by lowercase-name; preserve first-appearance order.
_union = dedup(list(mapped_entities or []) + list(second_pass_entities or []))
mapped_entities = _union if _union else mapped_entities
```

The mechanism is *automatic bridging*: BAML expresses the modern concept in Gill's vocabulary (e.g., `"exclusive psalmody"` → `"psalm singing, musical praise, sacred music, liturgical song"`), and the second-pass entity lookup finds Hallel and Book of Psalms because their descriptions are embedding-adjacent to *that* vocabulary — no curation, no thesaurus entry, no manual mapping.

**Interaction with existing failure paths:**
- If BAML punts with `entities_given_none_returned`, we take the ADR-0012 poisoned-manifest suppression path and never reach the two-pass block. Correct.
- If BAML punts with `empty_expansion` or `no_query_terms_present`, we take the dedup-only fallback and never reach the two-pass block. Correct (BAML didn't produce a usable expansion; nothing to lookup).
- If BAML succeeds with a good expansion, two-pass adds semantic-recall entities to the boost.
- If BAML succeeds with a *wrong-direction* expansion (like the `"Psalter author, poet of David"` case), two-pass adds those wrongly-directed entities to the boost. This is a real risk; the mitigation is that the union preserves BAML's picks first and adds only new entities, so the boost is diluted with noise rather than replaced by it. The thesaurus fix (ADR-0011 v3) is what prevents mis-disambiguation upstream.

Stages metadata: `stages_capture["second_pass_entities"]` records what the second pass returned, alongside the existing `available_entities` and `baml_entities` fields, so a future incident can trace whether the second pass helped, hurt, or was silent.

### Part B — Gill-only constraint in the informative-refusal path

Extend the [`backend/bot.py`](../../backend/bot.py) informative-refusal instruction to explicitly forbid surfacing Scripture-verse-shape sentences as "nearest indexed material":

> The surfaced adjacent material must be Gill's own commentary — his doctrinal statements, interpretations, exposition, or historical explanation. It must NOT be a Scripture-verse quotation Gill is about to comment on. Sentences shaped like biblical text ("his disciples remembered that it was written, X", "And David himself saith in the book of Psalms, Y", "For it is written, Z") are Scripture-verse citations embedded in Gill's flow, not Gill's own commentary. Surfacing them as "the nearest indexed material" is a lentil trap in a different form: it presents Scripture as though it were Gill's teaching on the subject asked.
>
> If the only material available for a subject is Scripture-verse-shape sentences that happen to mention adjacent concepts, choose FLAT REFUSAL instead. The corpus has no Gill commentary on the subject; that is the honest report. Padding a refusal with Scripture verses is dishonest whether or not the citation resolves correctly.

The choice between informative-refusal and flat-refusal is now Gill-material-only: informative refusal *requires* Gill commentary to surface. Absence of Gill commentary routes to flat refusal.

## Consequences

**Positive:**
- Two-pass entity lookup makes BAML's expansion capability structurally load-bearing. Concept-heavy queries (paraphrases, doctrinal labels the thesaurus doesn't know about) get semantic entity recall without human curation.
- The `stages_capture["second_pass_entities"]` trace makes the two-pass contribution observable per query. If the second pass never adds anything useful in real traffic, the mechanism can be turned off cheaply; if it repeatedly adds the load-bearing entity, the value is measurable.
- Informative refusals now degrade honestly. A query about a subject Gill doesn't cover surfaces "no Gill commentary" rather than padded Scripture quotes.
- Combined with ADR-0011 v3 (span-based vector match) and ADR-0012 (poisoned-manifest suppression), the pipeline now has four automatic mechanisms — exact/fuzzy/vector thesaurus + BAML-fed semantic entity lookup + poisoned-manifest suppression + Gill-only refusal — each covering the others' failure modes with no curation step required.

**Negative:**
- Two-pass entity lookup adds one extra Weaviate call per successful-BAML query. Measured ~200–500ms in E-9.1 range; acceptable given the failure-mode reduction.
- If BAML expands in a wrong direction (like the failing case's `"Psalter author, poet of David"`), the second-pass lookup adds wrong-direction entities. The union structure minimizes the effect (BAML's picks lead) but does not eliminate it. Mitigation: ADR-0011 v3 span-based match reduces the frequency of wrong-direction BAML disambiguation by injecting anchor tokens for morphological variants.
- The refusal-path constraint may increase the frequency of flat refusals for subjects Gill only touches on tangentially. This is a UX shift but a truthful one — the pre-fix "here's a Scripture verse that mentions Psalms" was misleading, and the amber "Unverified" chip was already flagging it as such.

**Neutral (worth naming):**
- `search_gill` with the enlarged manifest still gets the same enhanced_query boost text, just with more entity names concatenated. BM25 scoring may shift for boundary cases.
- The refusal-path constraint is prompt-level, not code-level; a future prompt refactor must preserve the Gill-only rule or the fix regresses silently. The [ADR-0011 v3 amendment](0011-query-expansion-for-narrow-reformed-vocabulary.md) documents the same class of concern for the thesaurus.

## Amendment 2026-07-13 (v2): fix the substring bug at the root; drop the conditional

### Correction to the earlier hotfix

An earlier hotfix (commit `15bbec2`) gated the two-pass on `expansion_matches` being empty — "only run when thesaurus missed." That was a workaround for the substring-bug symptom, not a fix. The reviewer flagged it: *"the fix treats the symptom … the substring pass matches on arbitrary short tokens … the substring pass has been in there since ADR-0005 which means this noise has always been present on any query containing a short common token, silently degrading manifests you never inspected. The two-pass didn't create the bug; it just made it loud enough to catch."*

This amendment fixes the substring pass itself and drops the conditional.

### The real bug

[`backend/gill_search.py get_relevant_entities`](../../backend/gill_search.py) has a Tier 2 substring pass that tokenizes the query with `re.findall(r"[A-Za-z]{4,}", query)`. Four characters is the length floor. Common short English theological tokens — `book`, `life`, `word`, `name`, `day`, `way`, `son`, `law`, `sin`, `god`, `lord`, `holy`, `faith` — all pass the filter, and each substring-matches every entity whose canonical (space-stripped) key contains it. `book` matches `bookofpsalms` (right), and also `bookofwisdom`, `bookoflife`, `sealedbook`, `authorsofaneditionofthebookofzohar` (all noise).

This has been present *on every query* since ADR-0005 (May 2026). The first-pass entity lookup's `MANIFEST_TOTAL_CAP = 5` masked the damage — noise was truncated below the cap. The two-pass added *after* the cap without capping itself, so noise leaked in and the flood was visible for the first time.

### The fix

Raise the substring pass length floor from 4 to 5:

```python
# backend/gill_search.py, Tier 2 substring pass
for tok in re.findall(r"[A-Za-z]{5,}", query):
    ...
    if t_key.endswith("s") and len(t_key) > 5:
        candidates.add(t_key[:-1])
```

Rationale: legitimate distinctive query tokens for compound entities are structurally longer than the generic-word tokens that flood — `psalms` (6), `wisdom` (6), `atonement` (9), `covenant` (8), `scapegoat` (9). Single-word entities whose names ARE 4 characters (Cain, Adam, Ruth, Paul, Mary) are covered by Tier 3 BM25's word-token match on the entity `name` field — the substring path is redundant for them anyway. The 5-char floor removes the flood without breaking any known valid lookup.

### Empirical verification

Against the live gya-test Weaviate, `get_relevant_entities` for the psalmist BAML expansion `"was gill an exclusive psalmist?, Book of Psalms, Psalter, hymns, songs of David"`:

- BEFORE fix: `[Psalmist, authors of an edition of the book of Zohar, book of Wisdom, book of life, sealed book]`
- AFTER fix:  `[Book of Psalms, Psalmist, David, times of David, house of David]`

All David-related after the fix — legitimately concept-adjacent to a "psalmist" query, not noise.

### Two-pass conditional dropped

Once the substring pass is clean, the reason for gating the two-pass evaporated. The conditional (`if not expansion_matches: run`) had one honest justification: *the other path was broken.* Dropping it restores ADR-0013 Part A to its originally-stated design: the two-pass is the automated concept-bridge, and it runs for *every* successful-BAML query. The reviewer's guidance was correct: rules whose real reason is "the other path is broken" tend to outlive the breakage and calcify as architecture nobody can explain.

### End-to-end verification (both branches)

**Thesaurus-fires branch** (`was gill an exclusive psalmist?`):
- Raw manifest: `[Hebrew Hallel, Hallel, Book of Psalms, Psalmist, passover]` — anchored by v3 span-match.
- Two-pass manifest: `[Book of Psalms, Psalmist, David, times of David, house of David]`.
- Union: 8 entities, all Hallel/Psalm/David-adjacent.
- Retrieval: MATTHEW 26:30 lands rank 4, score 0.558 — within the bot's top-5 window.

**Paraphrase-drought branch** (`should we sing only psalms in worship?`, no thesaurus match):
- Raw manifest: `[Psalmist, Book of Psalms, worship of the sun and moon, true worship of God, worshippers of Baal]` — worship-adjacent.
- Two-pass manifest: `[worship of the sun and moon, true worship of God, worshippers of Baal, Book of Psalms, music]` — adds `music` as new.
- Union: 6 entities. Retrieval covers Psalm-singing and worship material honestly.

The concept bridge now works on both branches for the same reason: no substring flood, no calcified workaround.

### The length floor is a stopgap, not the structural fix (live follow-up)

Raising the floor 4→5 closes the *observed* failures (`book`, `life`, `word`, `name`) and preserves the tokens we need (`psalms`, `wisdom`, `covenant`). But it is a proxy for the property actually wanted: **word-boundary matching on the canonical key**, not token length. Five-character common theological words exist and will re-open the class the first time a query expansion contains one — `grace`, `faith`, `blood`, `bread`, `light`, `flesh`, `glory`, `works`, `laws`. Each is a substring of legitimate compound entities (`bread` → `bread of life`; `grace` → `X of grace`) and a common English token. So the class is **narrowed, not closed**.

The structural fix — the one the substring bug actually calls for — is to match query tokens against the canonical key at word boundaries rather than as arbitrary substrings: a token should match `bread of life` only if `bread` aligns with a word in the key, not if it appears anywhere inside `sealedbread...`. That is a live follow-up, not a closed one. The 4→5 floor buys time; word-boundary matching ends the story. Recorded here so nobody reads "root fix" and stops thinking — the *observed* root cause is fixed, the *structural* root cause is narrowed.

### Observed retrieval margin (N=5 stability baseline)

For the motivating query `"was gill an exclusive psalmist?"`, retrieval was run N=5 against the live gya-test Weaviate with the fixed clean union `[Hallel (Hebrew), Hallel, Book of Psalms, Psalmist, passover, David, times of David, house of David]`:

| Run | MATTHEW 26:30 rank | score |
|---|---|---|
| 1 | 4 | 0.555 |
| 2 | 4 | 0.558 |
| 3 | 4 | 0.555 |
| 4 | 4 | 0.555 |
| 5 | 4 | 0.555 |

**Stable rank 4, score 0.555–0.558** — the sub-0.003 variance is the embedding service round-robining across the two Ollama nodes (.179/.188) per the litellm config. It does NOT drift toward the window edge. The bot retrieves `limit=12` (main.py:577), so rank 4 sits comfortably in the middle third of the window it sees, not at the margin.

Honest secondary observation: the top-3 in every run are David-quotes-a-psalm verses (LUKE 20:42 "David himself saith in the book of Psalms", MATTHEW 23:43, LUKE 1:32), not the Hallel commentary. The two-pass added `David / times of David / house of David` because BAML expanded "psalmist" → "songs of David", and those entities pull David-psalm chunks above the Hallel material. The two-pass is a *net* help — without it MATTHEW 26:30 was past rank 6 (drought); with it, stable rank 4 — but it crowds the top with David-quote material. If future evidence shows the David-crowding degrades answer quality, the fix is at the BAML-expansion or the entity-boost-weighting layer, not here. Recorded as the observed baseline so a future regression has a number to be measured against.

## Amendment 2026-07-13 (Part C): anchor the entity boost on the raw manifest

### The bug the substring fix revealed underneath itself

After the substring root fix (`04ca662`) deployed, a full-pipeline N=5 of `"was gill an exclusive psalmist?"` against the live pod showed MATTHEW 26:30 **ABSENT** in all five runs — contradicting the offline retrieval test that had it at stable rank 4. The offline test had hand-built the entity union to include the raw manifest; the deployed pipeline did not.

The trace showed the divergence precisely:

- **Raw manifest** (`available_entities`, surfaced by the thesaurus anchor tokens on `lookup_query`): `[Book of Psalms, Hallel, Psalmist, passover, הַלֵּל טָעוּן]` — the English `Hallel` entity is present at position 2.
- **`baml_entities`** (what the boost actually used = BAML's `official_entities` ∪ second-pass): `[Book of Psalms, Psalmist, הַלֵּל טָעוּן]` — the English `Hallel` is **gone**.

Per the E-1 entity survey, MATTHEW 26:30 is linked to the **English `Hallel`** entity `[TypeOrSymbol]` ("Passover hymn consisting of Psalms 113-118"). BAML's pick had deduplicated the English and Hebrew Hallel forms down to only the Hebrew — exactly the wrong choice for retrieval, because the English one carries the MATT 26:30 link. Without it in the boost, MATT 26:30 lost its `entities^3` boost and fell out of retrieval entirely — a drought, non-deterministically (run 2 produced a different second-pass and a refusal), on the exact query the whole thesaurus effort was built to answer.

### The architectural flaw

BAML's `official_entities` was the **sole source** for the entity boost (unioned with second-pass, but both post-BAML). BAML's pick is a lossy, non-deterministic filter over the candidate manifest. Anchoring the boost on it means any entity BAML fails to echo — including one the thesaurus deliberately surfaced via anchor tokens — is silently discarded. The thesaurus did its job (Hallel was in the raw manifest); BAML undid it.

### The fix

Union **three** sources for the entity boost, raw manifest first:

```python
for _name in (
    list(available_entity_names or [])   # raw manifest — thesaurus-anchored, highest signal
    + list(mapped_entities or [])        # BAML's canonicalized picks — may add canonical names
    + list(second_pass_entities or [])   # concept recall from BAML's expansion
):
    dedup and preserve first-appearance order
```

No single lossy stage can now discard a load-bearing entity. All three sources are individually cap-bounded (`MANIFEST_TOTAL_CAP = 5`), so the union stays small — the psalmist query's union is 5 entities, not a return to the pre-ADR-0010 flood.

### Verification

Offline, holding the BAML expansion text constant, boost = current (BAML-only) vs fixed (raw-manifest-anchored):

| Boost source | MATTHEW 26:30 |
|---|---|
| Current (BAML picks ∪ second-pass) | **ABSENT** |
| Fixed (raw manifest ∪ BAML ∪ second-pass) | **rank 4, 0.413** |

N=5 retrieval stability with the fixed union: rank 4 every run, score 0.416–0.417. Stable, not fragile.

Full-pipeline N=5 against the deployed pod pending redeploy of this commit.

### The general principle — a stochastic component may never subtract from a deterministic one

The precise flaw is larger than the psalmody case: **the pipeline let a stochastic component veto a deterministic one.** The entity lookup — thesaurus anchor, vector tier, substring pass, all the deterministic machinery of ADR-0010/0011/0013 — surfaces the correct manifest. Then BAML, a small unreliable model whose failure modes are catalogued across ADR-0008 (empty `{}`, meta-text punts, role confusion, dropping entities it was handed), decides *which of those entities survive*, and whatever it silently omits is gone. Every upstream guarantee — deterministic thesaurus, provable no-false-bridge, grounded entries — is nullified by a downstream coin-flip.

The principle that generalizes past this bug: **BAML's `official_entities` is additive, never subtractive.** BAML may *add* canonical names it maps; it may not *remove* an entity the deterministic lookup found. The boost is anchored on the raw manifest; every stage contributes; no stage's omission is authoritative. Same "amplifier not foundation" lesson as ADR-0012, applied to the opposite failure: there a bad manifest was suppressed; here a good entity must not be droppable by a downstream filter.

### Telemetry — how much BAML has been dropping (the "silently since May" number)

The entity fields are only in `stages_capture` (debug responses), never logged to Langfuse, so no historical organic-traffic analysis was possible — the drop has been invisible since the entity boost shipped. Measured empirically across 10 diverse queries against the deployed pod (`available_entities` vs `baml_entities`):

| Query | lookup surfaced | dropped before boost | dropped entities |
|---|---|---|---|
| was gill an exclusive psalmist? | 5 | **3** | hallel, passover, הַלֵּל טָעוּן |
| exclusive psalmody | 5 | **5** | (BAML punted `entities_given_none_returned` — all 5, incl. hallel) |
| universal atonement in Christ | 5 | 0 | — |
| is the covenant of grace monocovenantal | 5 | 0 | — |
| what does Gill say about Cain | 3 | 2 | arabic writers, offspring of cain |
| what does Gill say about baptism | 5 | 0 | — |
| who was Melchizedek | 2 | 1 | wine of his love |
| the scapegoat ritual | 5 | 3 | ruler, spiritual reign of christ, strangers |
| what does Gill say about the Sabbath | 5 | 0 | — |
| monergism in salvation | 5 | 2 | distinguishing grace, free grace of God |

**6 of 10 queries lost at least one lookup entity. 16 of 45 total entities (36%) were dropped before the boost.** On the two psalmody phrasings the dropped set included the load-bearing `hallel`. This has been degrading retrieval on roughly a third of queries since the entity boost shipped, invisibly, because nobody compared the two fields — the same "silently damaging since May" shape as the substring bug, one layer over, now quantified rather than assumed.

Part C (raw-manifest-anchored union) reduces the *net* drop to zero for the BAML-success path: every lookup entity now survives into the boost.

### Open question for a follow-up (c): should BAML pick entities at all?

The telemetry raises the reviewer's sharper question: what is BAML's entity *pick* for, now? The lookup already returns query-relevant entities by deterministic BM25 + vector + substring matching. BAML is being asked to re-filter a list *already filtered by relevance*, using a model that drops a load-bearing entity 36% of the time. On this evidence the pick is net-subtractive — it removes value (the dropped Hallel) more reliably than it adds it.

The counter-argument — BAML's pick can *deprioritize* lookup entities that don't fit the query's actual subject — is weaker than it looks: E-6/E-8 showed the lookup's precision is better governed by thresholds and caps (which now exist) than by a small model's judgment. Part C makes BAML additive-only, which captures most of the benefit. The remaining decision is whether to remove BAML's entity-mapping role *entirely* — letting the lookup own the manifest, which would also retire the `entities_given_none_returned` punt reason and the ADR-0012 poisoned-manifest machinery as a category, and shrink the gemma prompt (already fought down for reliability). BAML would keep the job it is genuinely good at — query expansion into 18th-century vocabulary — and stop doing the job it keeps failing at.

There is one wrinkle the telemetry surfaced that must be resolved first: for `"exclusive psalmody"`, BAML punted `entities_given_none_returned` on a manifest that was actually GOOD (contained hallel, book of psalms, passover). ADR-0012 currently reads that punt as "manifest is poison → suppress boost." That's the wrong reading when the thesaurus fired (a strong signal the manifest is anchored). The clean refinement: trust the raw manifest when `expansion_matches` is non-empty even if BAML punts; suppress only when the thesaurus droughted AND BAML rejected. Recorded as the (c) follow-up — not landed in this commit, which is scoped to making the success-path boost lossless.

### What the earlier commits still stand on

- ADR-0011 v3 (span-based vector match) is unchanged and load-bearing for morphological variants like `psalmist`.
- ADR-0013 Part A (two-pass) is now unconditional and works because the substring bug is fixed.
- ADR-0013 Part B (refusal-path Gill-only) is unchanged and shipped correctly.
- ADR-0012 (poisoned-manifest suppression) is unchanged and still the honest floor.

## References

- [ADR-0008](0008-three-zone-generation-and-voice-marked-ui.md) — three-zone taxonomy and the informative-refusal path this ADR constrains.
- [ADR-0011](0011-query-expansion-for-narrow-reformed-vocabulary.md) — thesaurus + v3 vector-tier fix; complementary to Part A above.
- [ADR-0012](0012-poisoned-manifest-fallback-suppression.md) — poisoned-manifest suppression; interacts with Part A's two-pass path.
- The 2026-07-12 `exclusive psalmist` incident trace: Langfuse trace ID `2c3999a51652cc7feb10fe7fc5b10927`.
