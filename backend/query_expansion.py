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

import re


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


def expand_query(raw_query: str) -> tuple[str, list[str]]:
    """Return (expanded_query, list_of_matched_terms).

    If no narrow-vocabulary term is matched, returns (raw_query, []).
    The expanded query is the raw query with matched terms' anchor
    tokens appended, joined by spaces. The list of matched terms is
    returned so callers can log or trace which entries fired.
    """
    matched = []
    tokens_to_append = []
    for term, entry in THEOLOGICAL_THESAURUS.items():
        if _COMPILED[term].search(raw_query):
            matched.append(term)
            tokens_to_append.extend(entry["anchor_tokens"])
    if not tokens_to_append:
        return raw_query, []
    return f"{raw_query} {' '.join(tokens_to_append)}", matched
