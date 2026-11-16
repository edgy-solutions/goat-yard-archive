# Addendum — what varies between the five draws: three channels, and the discriminator in §5 can only see one

Lane A1 / session 2102d9d0

Answering Chris's overnight item 3 (2026-11-15). This is an addendum to
[`X5_WITNESS_VARIATION_laneA1_20261115.md`](X5_WITNESS_VARIATION_laneA1_20261115.md),
not a replacement. The parent note's two findings stand: the variation is at or
before retrieval, and generation is unmeasured. What is added here is read from
the retrieval code, which the parent note did not open, and it changes the
experiment §5 proposes.

Still **no measurement**. No prod call, no debug channel, no model run. Every
claim below is a read of `backend/main.py` and `backend/gill_search.py` at
`release-0.3.3`, with line numbers.

---

## 1. The chunk SET varied. The mechanism, exactly

`main.py:719` calls `search_gill(..., limit=12, ...)`. The chunk count is a
**constant**, so the three distinct `context_sids` totals the witness printed —
37, 37, 36, 33, 33 — cannot be a count of chunks. They are totals of
`sentence_data` entries **summed over twelve chunks** (`main.py:750-757`).
Twelve chunks summing to three different sentence totals means **at least three
distinct chunk sets** were retrieved. Not a different ranking of one set: a
different membership.

This is firmer than "three different context sizes" — it is a fixed
denominator, which is what makes the differing numerator proof rather than
suggestion.

## 2. Ranking drift is already neutralised, which makes "generation varies" a CLEAN hypothesis

`main.py:741` sorts every result before anything consumes it:

```python
raw_results.sort(key=lambda c: (_first_sid(c), c.get("chunk_id", "")))
```

The comment beside it says why — Weaviate hybrid scores drift by tiny FP
amounts between identical queries, so the same set can arrive in different
orders, and the bot is sensitive to context ordering. The consequence for this
question: **whenever two draws retrieve the same chunk set, the bot's prompt is
byte-identical**, ranking drift and all.

So draws 1 and 2 (`context_sids` 37 both) and draws 4 and 5 (33 both) are the
informative pairs. If either pair's set is equal, that pair's differing
citations are **generation**, measured — because the only thing left that could
differ is the sampling inside the answer LM. If the sets differ, the question
stays upstream. One hash per draw of the sorted SID set decides it, and the
witness already computes the set and prints only its length.

**Equal length is not equal set.** The pairing above is a hypothesis to test,
not a result.

## 3. Three input channels feed retrieval, and they are NOT interchangeable

`gill_search.py:159-181` builds two different strings from the same frame:

| channel | enters the BM25 string | enters the embedding |
|---|---|---|
| `original_query` (the user's text, fixed) | yes | yes |
| `search_text` — the BAML expansion (`main.py:495`) | yes | yes |
| `mapped_entities` — the entity manifest | **yes** (`" ".join(detected_entities)`) | **no** |

The code states the exclusion deliberately: *"Embedding input: original_query +
BAML expansion (NO entity names)"*. So the entity set reaches retrieval through
**one half of the hybrid only** — the BM25 half, boosted by
`query_properties=["content", "verse_ref", "entities^3"]` (`gill_search.py:232`).

And that half carries the larger weight: **`alpha=0.35`**
(`gill_search.py:231`). In Weaviate, alpha is the vector share, so this hybrid
is roughly **65% BM25**. The channel that `embedding_hash` cannot see is the
channel with more leverage over the top-12.

## 4. Therefore §5's discriminator, as written, can mis-attribute

The parent note says:

> `embedding_hash` identical across draws ⇒ the expansion did not move, and the
> variation is retrieval-side

The first clause holds for the **embedding input**. The inference does not hold
for "the retrieval inputs were identical", because an entity-set change is
invisible to that hash by construction. A draw set with identical
`embedding_hash` and a different `mapped_entities` would be read as
"retrieval-side drift" when the actual mover is **upstream**, in the manifest.

The fix is not a new instrument. `main.py:598-599` already captures
`baml_expansion` (the expansion text) and `baml_entities` (the manifest,
sorted), and `gill_search.py:186-189` captures `enhanced_query` — the BM25
string, which is the one place all three channels appear together. The
experiment must compare **all four**: `baml_expansion`, `baml_entities`,
`enhanced_query`, `embedding_hash`. Any one of them alone is a partial view,
and the two that would most plausibly move are the two §5 omits.

## 5. A mechanism that would produce exactly this, available in the code

Not offered as the cause. Offered because it is a path by which the manifest
moves while the embedding hash does not, and it should be checked before
anything is attributed to Weaviate:

- `get_relevant_entities` tier 1 is `near_vector` on the entity index with
  **`distance <= 0.25`, cap 3** (`gill_search.py:497-502`, the cutoff itself
  at `VECTOR_CONFIDENT_DIST_MAX`, `:409`). A fixed cutoff over a continuous
  score is a **threshold**: an entity sitting near 0.25 flips in or out on a
  difference far smaller than anything a reader would call a change.
- **The code records a real query landing 0.002 from it.**
  `gill_search.py:397-399`: *"(`exclusive psalmody` -> `music` at 0.252) sits
  just above 0.25, so 0.25 excludes it for free."* That comment was written to
  justify the cutoff, and it doubles as evidence that live queries do sit in its
  immediate neighbourhood. A threshold with traffic that close to it is not a
  hypothetical flip.
- Its input is an embedding of its own (`self._get_embedding(query)`,
  `lookup_query` at `main.py:452`), produced by the enrichment tier — a
  separate model call from `search_gill`'s.
- One flipped entity changes `" ".join(detected_entities)`, which changes the
  BM25 string, which is 65% of the hybrid, which can change the top-12 — with
  `embedding_input` **byte-identical** and `embedding_hash` therefore equal.
- And there is a **second** lookup: `main.py:533` calls
  `get_relevant_entities(query=search_text)` on the expansion output, so
  expansion variation also propagates into a second manifest. Two channels, one
  of them fed by the other.

This is a decomposition, not a diagnosis. Whether any entity actually sat near
the cutoff on these five draws is unmeasured, and the ANN lookup over a static
index with a fixed vector is itself deterministic — the candidate wobble is in
the **embedding call**, not in the search.

## 6. The answer to the question as asked

**What varies between the five draws, established:** the retrieved chunk set,
at a fixed limit of twelve — at least three distinct sets across five draws.
That is the whole of what the printed output supports.

**What cannot be said from this output:** which channel moved. There are three
candidates, not two, and they are ordered here by how much of the hybrid they
touch rather than by likelihood:

1. the **entity manifest** (BM25 half, `entities^3`, ~65% weight, invisible to
   `embedding_hash`, and gated by a 0.25 threshold with a cap of 3);
2. the **expansion text** (both halves, and it feeds a second manifest lookup);
3. the **embedding call** itself, and Weaviate's own hybrid evaluation.

**What is now cheap to settle, and was not before:** generation. The pairs with
equal `context_sids` make it a one-hash question, on prod, in the ordinary
response body, with no debug channel — and that instrument is already scoped as
0.3.4 item 7.

**What is not settled by the existing proposal:** the three-way attribution
above, if the §5 experiment is run comparing `embedding_hash` alone. Compare
the four captures, or the run names a cause it did not measure.

---

## What this addendum does NOT establish

- **No measurement of any kind.** Five line-numbered reads of two files. If a
  reader takes the §5 experiment and runs it, this addendum changes what gets
  compared; it produces no numbers itself.
- **Not** that the manifest did vary. Nothing here observed `mapped_entities`
  on any of the five draws; the acceptance output does not carry it, and
  obtaining it on prod needs the capture channel acceptance item 4 keeps shut.
- **Not** that generation does not vary. It remains unmeasured. §2 makes it
  *testable*, which is a different claim.
- **Not** a retraction of the parent note. Its two findings stand; the parent's
  §5 discriminator is narrowed, not withdrawn, and `embedding_hash` remains the
  right witness for the channel it watches.
- **Not** a statement that `alpha=0.35` means "65% of the outcome". It is the
  weight on the BM25 score in the fusion, not a share of the result set, and
  the rank a chunk lands at is not a linear function of it.
- **Not** applicable to prod's corpus specifically. These are code reads; the
  five draws were on prod, and the corpus difference the acceptance note already
  flags is untouched by anything here.
