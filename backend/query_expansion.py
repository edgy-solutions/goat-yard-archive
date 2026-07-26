"""Narrow-vocabulary expansion for Reformed-tradition queries.

E-7 (2026-07-07) established that qwen3-embedding represents narrow
Reformed-tradition terms (e.g. 'exclusive psalmody') in different
embedding neighborhoods than their anchor entities in Gill's corpus
(e.g. 'Hallel'), even though both concepts exist in the vector space.
The theological association between the modern term and Gill's usage
lives in the reader's head, not in the embedding space; ADR-0010's
confident-vector tier cannot manufacture the connection.

This module bridges those associations at the query-preprocessing
layer, before `get_relevant_entities` runs. It applies a fixed
thesaurus of known Reformed-vocabulary colligations, appending
anchor-tokens (entity names or gloss-adjacent phrases Gill actually
uses) so that the entity-lookup vector, substring, and BM25 tiers all
see vocabulary they can reach.

The thesaurus is deterministic and small on purpose:
  - Reformed-narrow vocabulary is finite and stable (a couple dozen
    terms across covenant/soteriology/worship categories).
  - Every entry is testable: E-7.1 probes verify the entity actually
    surfaces after expansion.
  - Adding an entry does not require LLM prompt tuning — just append.
  - Removing an entry is a one-line change and cannot regress in
    unexpected ways at query time.

An LLM-driven generalization (BAML `ExpandNarrowVocabulary` prompt) is
possible later, but E-7 found this class of failure is enumerable, so
a thesaurus is the right first pass. See ADR-0011.

Discovery process for new entries:
  1. A narrow-vocabulary query fails at eval or in the prod log.
  2. Run E-7.1 probe (`evals/e7_query_expansion_probe/`) to identify
     the anchor entity in Gill's corpus.
  3. Consult a citable scholarly reference (see ADR-0011 section
     "Near-term follow-up: ground thesaurus entries in a citable
     reference") for the term's canonical historical vocabulary. Do
     NOT rely on parametric knowledge alone — the whole tool refuses
     that trust model elsewhere and the thesaurus should not be the
     exception.
  4. Add an entry with BOTH `justification` (E-7.1 probe result —
     empirical grounding) AND `source` (scholarly reference —
     provenance grounding). The existing five entries predate the
     source-grounding requirement and carry only `justification`;
     they will be retroactively audited (ADR-0011 follow-up).
  5. Re-run E-7 validation to confirm the expansion bridges.
  6. Commit the thesaurus change with the E-7 evidence.

Standing principle (ADR-0011): source for the bridge, not source in
the tool. Any citable reference may inform the thesaurus at build
time; its content may not appear in a runtime answer. Only Gill's
verified words and the model's owned reading of the user's question
touch the answer.
"""
from __future__ import annotations

import math
import re
from typing import Awaitable, Callable, Optional

import regex  # third-party — supports {e<=1} fuzzy syntax


# ADR-0011 v3 constants — DERIVED from E-8.1 probe (2026-07-12) and
# refined after the 2026-07-12 'exclusive psalmist' incident.
#
#   FUZZY_EDIT_DISTANCE — Levenshtein tolerance for the fuzzy substring
#     match. 1 catches every single-char typo (exlusive, paktum) and
#     single-char inflection shifts. 2 would collide with terms in the
#     neighborhood ('imputation' <-> 'reputation' at edit distance 2).
#
#   VECTOR_MATCH_THRESHOLD — cosine distance ceiling for the vector
#     auto-fire tier (added in v3). E-8.1 measurement: no should-NOT
#     falls under 0.15 for any key (closest is 'covenant of grace' at
#     0.174 from 'pactum salutis'). Catches bare inflections that
#     fuzzy edit-1 misses because they're morphological variants with
#     >1 character difference — e.g. 'exclusive psalmist' at 0.102 to
#     'exclusive psalmody'. The reviewer's original rationale, reinstated
#     after E-8.1 was re-read with the tight-cutoff rule in mind.
#
#   SPAN_LENGTHS — the window sizes tried for the span-based vector
#     match. Wrapped queries dilute the whole-query embedding (Chris's
#     'was gill an exclusive psalmist?' sits at 0.30, above threshold)
#     but their concept-carrying substring is still tight — 2-3 word
#     spans of the same query re-check the tight regions independently.
#     'exclusive psalmist' as a 2-word span inside the wrapping still
#     measures 0.102 against the key.
#
#   NEAR_MISS_LOG_MAX — observability window. Distances in
#     (VECTOR_MATCH_THRESHOLD, NEAR_MISS_LOG_MAX] don't auto-fire;
#     they get logged for observability so paraphrase shapes real
#     traffic uses are visible in Langfuse metadata.
FUZZY_EDIT_DISTANCE = 1
VECTOR_MATCH_THRESHOLD = 0.15
SPAN_LENGTHS = (2, 3)
NEAR_MISS_LOG_MAX = 0.40


# Narrow-term -> anchor tokens.
#
# `narrow_term` is matched as a case-insensitive whole-phrase substring in
# the user's raw query (bounded by word boundaries so 'imputation' does
# not match 'reputation').
#
# `anchor_tokens` is a list of token strings appended to the query. Each
# was verified by an E-7.1 probe against gya-test (2026-07-07) as
# bringing its anchor entity into the confident vector tier (distance
# <= 0.25) at the top of near_vector.
#
# Justifications point to the specific Gill anchor and its distance
# after expansion. Re-run E-7.1 when the corpus changes.
THEOLOGICAL_THESAURUS: dict[str, dict] = {
    "exclusive psalmody": {
        "anchor_tokens": ["Hallel", "Passover", "Psalms 113 118"],
        "justification": (
            "'singing Psalms at Passover Hallel' -> Hallel rank 1 dist 0.143. "
            "Hallel is the Passover hymn (Ps 113-118) at MATTHEW 26:30; "
            "the historical Reformed anchor for the exclusive-psalmody debate."
        ),
    },
    "pactum salutis": {
        "anchor_tokens": ["covenant of redemption", "covenant engagements"],
        "justification": (
            "Latin ↔ English pair. Vector direct-hit for 'covenant of redemption' "
            "reaches 'covenant engagements' at rank 1 dist 0.207 (E-6). Latin form "
            "'pactum salutis' lands at rank 70 dist 0.309 — needs English bridge."
        ),
    },
    "monergism": {
        "anchor_tokens": ["electing grace", "salvation by grace alone"],
        "justification": (
            "Modern label for the Reformed doctrine Gill exposits as electing "
            "grace / effectual calling. Bare 'monergism' returns scattered top-5 "
            "(libertinism, special adoption, mystical union); anchor bridge needed."
        ),
    },
    "regulative principle": {
        "anchor_tokens": ["ordinances of the Gospel", "worship of God"],
        "justification": (
            "Puritan/Reformed principle governing worship. Bare term returns "
            "golden-rule / civil-magistrate top-5. Bridged by pointing at Gill's "
            "'ordinances of the Gospel' and 'true worship of God' entities."
        ),
    },
    "imputation": {
        "anchor_tokens": ["justifying righteousness of Christ", "imputation of sin"],
        "justification": (
            "Bare 'imputation' distances all above 0.42. Imputation-of-Christ's-"
            "righteousness is a Doctrine entity; imputation-of-sin is a distinct "
            "TypeOrSymbol entity. Add both anchors so downstream can select."
        ),
    },
}


def _phrase_pattern(term: str) -> re.Pattern:
    """Build a whole-phrase case-insensitive matcher for `term`.

    Uses \b word boundaries so 'imputation' does not match 'reputation'.
    """
    escaped = re.escape(term)
    return re.compile(rf"\b{escaped}\b", re.IGNORECASE)


_COMPILED = {term: _phrase_pattern(term) for term in THEOLOGICAL_THESAURUS}


def _fuzzy_pattern(term: str) -> regex.Pattern:
    """Fuzzy Levenshtein pattern matching `term` inside a longer query.

    Uses the `regex` module's `{e<=N}` fuzzy syntax. Matches the term as
    a substring within the query, tolerating up to FUZZY_EDIT_DISTANCE
    edits. `\\b` boundaries ensure we don't fuzzy-match a fragment of a
    longer word — the term is matched as a token span.

    This catches Chris's 2026-07-12 incident case: the raw query
    "what was gill's opinion on the exlusive psalmody debate?" contains
    'exlusive psalmody' (edit distance 1 from 'exclusive psalmody') as
    a substring, so this pattern matches it while the exact regex does
    not.
    """
    escaped = regex.escape(term)
    return regex.compile(
        rf"\b({escaped}){{e<={FUZZY_EDIT_DISTANCE}}}\b",
        regex.IGNORECASE | regex.BESTMATCH,
    )


_FUZZY_COMPILED = {term: _fuzzy_pattern(term) for term in THEOLOGICAL_THESAURUS}


# Precomputed embeddings of each thesaurus KEY (the term itself, not its
# anchor tokens). Populated once at startup by init_vector_thesaurus so
# per-query expansion is a single query embedding + N in-memory cosine
# distances, not N remote embedding calls.
_KEY_EMBEDDINGS: dict[str, list[float]] = {}


async def init_vector_thesaurus(embed_fn: Callable[[str], Awaitable[list[float]]]) -> None:
    """Precompute embeddings for each thesaurus key. Call once at app startup.

    Failure to initialize the vector tier degrades expansion gracefully to
    exact-only — that is the pre-vector behavior (ADR-0011 v1) and is
    strictly better than crashing the request path. Callers should check
    logs at startup if vector matching stops firing unexpectedly.
    """
    global _KEY_EMBEDDINGS
    fresh: dict[str, list[float]] = {}
    for term in THEOLOGICAL_THESAURUS:
        try:
            fresh[term] = await embed_fn(term)
        except Exception as e:
            print(f"[EXPANSION INIT] failed to embed key {term!r}: {e}")
            return  # abort — partial init would produce silently missing matches
    _KEY_EMBEDDINGS = fresh
    print(f"[EXPANSION INIT] vector thesaurus ready with {len(_KEY_EMBEDDINGS)} keys")


def _cosine_distance(a: list[float], b: list[float]) -> float:
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 2.0
    return 1.0 - dot / math.sqrt(na * nb)


def _extract_spans(text: str, lengths: tuple[int, ...] = SPAN_LENGTHS) -> list[str]:
    """Extract contiguous n-word spans from `text` for the given window
    sizes. Words are anything matching `[A-Za-z][A-Za-z']*` — punctuation
    and interrogatives don't contribute to spans. Returns unique spans
    preserving first-appearance order so higher-signal spans (typically
    the concept-carrying substring) rank first.

    For 'was gill an exclusive psalmist?' with lengths=(2,3) this yields:
      'was gill', 'gill an', 'an exclusive', 'exclusive psalmist',
      'was gill an', 'gill an exclusive', 'an exclusive psalmist'
    and the concept-carrying 'exclusive psalmist' is one of them.
    """
    words = re.findall(r"[A-Za-z][A-Za-z']*", text)
    seen: set[str] = set()
    spans: list[str] = []
    for n in lengths:
        for i in range(len(words) - n + 1):
            span = " ".join(words[i : i + n])
            if span.lower() in seen:
                continue
            seen.add(span.lower())
            spans.append(span)
    return spans


async def expand_query(
    raw_query: str,
    embed_fn: Optional[Callable[[str], Awaitable[list[float]]]] = None,
) -> tuple[str, list[dict], list[dict]]:
    """Return (expanded_query, matches, near_misses).

    Three deterministic auto-fire tiers plus an observation-only tier
    (ADR-0011 v3, 2026-07-12 evening — refined after the 'exclusive
    psalmist' incident):

      Tier 1 — EXACT regex on whole-phrase word boundaries. Cheapest,
               highest precision. Handles the well-spelled case.
      Tier 2 — FUZZY substring at Levenshtein <= FUZZY_EDIT_DISTANCE
               (1). Catches typos anywhere in the query, including
               when the term is wrapped in a longer question form.
               Handles 'exlusive psalmody' inside "what was gill's
               opinion on the exlusive psalmody debate?".
      Tier 3 — VECTOR at cosine <= VECTOR_MATCH_THRESHOLD (0.15) on
               EITHER the whole query OR any 2-3 word span extracted
               from the query. Catches inflections and morphological
               variants that fuzzy edit-1 misses because they differ
               by >1 character (psalmody vs psalmist is edit-3+, but
               semantically almost identical — 0.102 apart in qwen3).
               Span-based match catches wrapped inflections like
               'was gill an exclusive psalmist?' where the whole-
               query embedding dilutes (0.30) but the concept-carrying
               2-word span stays tight (0.102).
      Observation only — cosine <= NEAR_MISS_LOG_MAX (0.40) on the
               whole query, for unmatched keys. Logged for growth
               signal, never fires.

    E-8.1 verified no should-NOT-match query lands under 0.15 for any
    key (closest is 'covenant of grace' at 0.174 from 'pactum
    salutis'). The vector tier is architecturally constrained from
    firing the wrong bridge.

    `matches` is a list of dicts: {term, method, distance, ...}. method
    is 'exact' (distance 0.0), 'fuzzy' (distance is Levenshtein edit
    count as float, plus matched_span), or 'vector' (distance is cosine,
    plus matched_span which is either 'query' or the specific span).
    """
    matches: list[dict] = []
    matched_terms: set[str] = set()

    # ---- Tier 1: EXACT regex ----
    for term in THEOLOGICAL_THESAURUS:
        if _COMPILED[term].search(raw_query):
            matches.append({"term": term, "method": "exact", "distance": 0.0})
            matched_terms.add(term)

    # ---- Tier 2: FUZZY substring (Levenshtein <= 1) ----
    for term in THEOLOGICAL_THESAURUS:
        if term in matched_terms:
            continue
        m = _FUZZY_COMPILED[term].search(raw_query)
        if m:
            subs, ins, dels = m.fuzzy_counts
            edits = subs + ins + dels
            matches.append({
                "term": term, "method": "fuzzy",
                "distance": float(edits),
                "matched_span": m.group(0),
            })
            matched_terms.add(term)

    # ---- Tier 3: VECTOR (whole query + 2-3 word spans) ----
    # Also collects observation-only near-misses on the same embedding.
    #
    # ADR-0014: this tier shares the litellm dependency with the entity
    # vector tier. When embed_fn raises, the tier silently empties — the
    # same "fail different" the entity tier had, and NOT caught by the
    # entity-lookup-mode gate in the transient-blip case where this embed
    # fails but get_relevant_entities' succeeds. So report degradation via
    # `vector_degraded`; the caller folds it into the overall mode and
    # suppresses the boost, keeping the law consistent across both tiers.
    near_misses: list[dict] = []
    vector_degraded = False
    if _KEY_EMBEDDINGS and embed_fn is not None:
        # First: whole query.
        try:
            query_vec = await embed_fn(raw_query)
        except Exception as e:
            print(f"[EXPANSION] vector tier degraded — embed_fn failed: {e}")
            query_vec = None
            vector_degraded = True

        if query_vec is not None:
            for term, key_vec in _KEY_EMBEDDINGS.items():
                if term in matched_terms:
                    continue
                d = _cosine_distance(query_vec, key_vec)
                if d <= VECTOR_MATCH_THRESHOLD:
                    matches.append({
                        "term": term, "method": "vector",
                        "distance": round(d, 4),
                        "matched_span": "query",
                    })
                    matched_terms.add(term)
                elif d <= NEAR_MISS_LOG_MAX:
                    near_misses.append({"term": term, "distance": round(d, 4)})

            # Second: 2-3 word spans of the query, only for keys not yet
            # matched. Concept-carrying substrings inside wrapped
            # questions ('exclusive psalmist' inside "was gill an
            # exclusive psalmist?") stay tight against the key even
            # when the whole query dilutes.
            unmatched_terms = [t for t in THEOLOGICAL_THESAURUS if t not in matched_terms]
            if unmatched_terms:
                for span in _extract_spans(raw_query):
                    try:
                        span_vec = await embed_fn(span)
                    except Exception as e:
                        print(f"[EXPANSION] span embed failed for {span!r}: {e}")
                        vector_degraded = True
                        continue
                    for term in list(unmatched_terms):
                        if term in matched_terms:
                            continue
                        d = _cosine_distance(span_vec, _KEY_EMBEDDINGS[term])
                        if d <= VECTOR_MATCH_THRESHOLD:
                            matches.append({
                                "term": term, "method": "vector",
                                "distance": round(d, 4),
                                "matched_span": span,
                            })
                            matched_terms.add(term)
                            unmatched_terms.remove(term)
                    if not unmatched_terms:
                        break  # every key matched, stop scanning spans

    # Sort near-misses by distance ascending — closest suspect first.
    near_misses.sort(key=lambda x: x["distance"])

    # Assemble expanded query.
    if not matches:
        return raw_query, [], near_misses, vector_degraded
    tokens_to_append: list[str] = []
    for m in matches:
        tokens_to_append.extend(THEOLOGICAL_THESAURUS[m["term"]]["anchor_tokens"])
    return f"{raw_query} {' '.join(tokens_to_append)}", matches, near_misses, vector_degraded
