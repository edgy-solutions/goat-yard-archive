# ADR-0002: Chapter and Book Prefix Retrieval for Navigation Queries

- **Status:** Proposed
- **Date:** 2026-05-17
- **Deciders:** Chris Nogradi

## Context

The Weaviate `CommentaryChunk` collection stores commentary at three granularities, distinguishable by the `verse_ref` field:

| Granularity | Example `verse_ref` | Source |
|---|---|---|
| Book intro | `"GENESIS"` | [align_verses.py:229](../../pipeline/scripts/align_verses.py#L229) — `pre_ref = f"{book}"` |
| Chapter intro | `"LEVITICUS 16"` | [align_verses.py:250-253](../../pipeline/scripts/align_verses.py#L250-L253) — `spillover_ref = f"{book} {chapter}"` |
| Per-verse | `"LEVITICUS 16:9"` | [align_verses.py:258,287](../../pipeline/scripts/align_verses.py#L258) — `f"{book} {chapter}:{verse_num}"` |

The verse-reference detection path in `search_gill` uses **exact equality** on `verse_ref`, which means a user who types a chapter-level reference (e.g. `"Leviticus 16"`) gets back only the single chapter-intro chunk if one exists, or zero chunks if it doesn't (the latter is handled by a recently-added hybrid-fallback safety net). A user who types a book-level reference (e.g. `"Genesis"`) doesn't currently trigger the verse-ref path at all because the existing regex requires at least one digit after the book name.

### The UX gap

A user trying to read Gill on Genesis 1 by typing `"Genesis 1"` gets only Gill's *introduction* to chapter 1 (1 chunk). They miss Gill's actual commentary on verses 1-31. This is surprising and sparse.

A user typing `"Genesis"` gets the standard hybrid search (no direct lookup at all), which scatters across the entire book based on semantic similarity rather than presenting the book intro plus chapter intros in order.

## Decision

Replace exact-equality `verse_ref` lookup with a **prefix-match** strategy that respects the storage model:

1. **Verse-specific reference** (`John 3:16`) → exact equality (unchanged behavior).
2. **Chapter-only reference** (`Leviticus 16`) → `Filter.by_property("verse_ref").like(f"{canonical_ref}*")` — returns the chapter intro plus every per-verse chunk in that chapter.
3. **Book-only reference** (`Genesis`) → extend the regex to also detect bare book names, then `Filter.by_property("verse_ref").like(f"{book}*")` — returns the book intro plus the chapter intros (and optionally verses, configurable).
4. **Post-sort results by `(chapter, verse)`** so the response reads in canonical order (intro first, then verses sequentially).

The chapter-only and book-only paths supersede the recently-added safety-net hybrid fallback for missing chapter intros — the `like` filter handles intro-missing cases naturally because it matches `LEVITICUS 16:1`, `LEVITICUS 16:2`, ... regardless of whether `LEVITICUS 16` itself is indexed.

### Cap considerations

A chapter-only query can return many chunks (Genesis 1 has 31 verses + intro = 32 candidate chunks). The current top-K cap is 12; for navigation queries we likely want a higher cap (or the full chapter). Recommend a per-mode limit:

- Verse-specific: K=1
- Chapter-only: K=50 (covers any chapter)
- Book-only: K=K_default (12) but ranked to surface intro and chapter intros first

## Alternatives Considered

1. **Leave as-is.** Acceptable if traffic shows users don't type chapter/book references. Cheap.
2. **Multi-query fetch and merge.** Run separate queries for intro and verses, merge in Python. Works but is more code than the `like` filter.
3. **Compound `equal OR startswith` filter.** Functionally equivalent to `like` but less clean.
4. **Treat chapter/book queries as a separate intent** and route them to a different path entirely (similar to the enumeration path in [ADR-0001](0001-enumeration-query-path.md)). Cleaner conceptually but more boilerplate.

## Consequences

### Positive
- Users can navigate Gill at chapter and book granularity naturally.
- Respects the existing three-level storage model rather than hiding two of the three levels.
- Removes the need for the safety-net hybrid fallback in [`search_gill`](../../backend/gill_search.py) for chapter refs, simplifying the code.

### Negative
- Requires extending the verse-reference regex to handle bare book names (currently requires a trailing digit).
- The per-mode K limit adds branching to the retrieval logic.
- Long chapters can return many chunks, which may stress the downstream LLM context window.

### Risks
- The DSPy synthesis prompt may struggle with many similar chunks (full chapter dump) — may need a chapter-mode signature variant that summarizes the chapter intro + samples representative verse commentary, rather than dumping everything.
- A user typing an ambiguous bare word like `"matthew"` (book name) vs as a name lookup needs disambiguation — when does it hit the verse-ref path vs hybrid? Probably treat as book-ref when standalone and lowercase-match against `BIBLE_BOOK_MAP`; otherwise hybrid.

## Implementation Sketch (~30 LOC)

```python
# backend/gill_search.py — replace the exact-equality block
if ":" in verse_part:
    # Specific verse — exact equality, K=1
    ref_filter = Filter.by_property("verse_ref").equal(canonical_ref)
    fetch_limit = 1
else:
    # Chapter-only — prefix match, larger K
    ref_filter = Filter.by_property("verse_ref").like(f"{canonical_ref}*")
    fetch_limit = 50

response = await self.chunks.query.fetch_objects(
    filters=ref_filter,
    limit=fetch_limit,
    ...
)

# Post-sort by (chapter, verse) for natural reading order
results.sort(key=lambda r: _verse_sort_key(r["verse_ref"]))
```

```python
# Extend regex to detect bare book names
BOOK_ONLY_PATTERN = re.compile(r'^\s*((?:\d\s*)?[A-Za-z]+)\s*$', re.IGNORECASE)
# Try book-only match if verse-ref pattern didn't match
```

## Open Questions

- Should book-only queries return the book intro + chapter intros (compact navigation summary), or book intro + chapter intros + selected verses (deeper but noisier)?
- For very long chapters (Psalms 119, Isaiah 53 context), should we truncate or paginate?
- Frontend: should chapter/book responses render differently (e.g. as a structured navigation list) vs being passed through the same DSPy synthesis prompt as theological questions?
