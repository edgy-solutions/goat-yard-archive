# What varies between the five witness draws — from the code path

Lane A1 / session 2102d9d0

**Question (ruling, 2026-11-15):** the x5 witness on `predestination_001`
returned five distinct cited-SID sets, `context_sids` 33 to 37,
`JOHN_6_37_S00` and `JOHN_6_39_S00` in all five, `verified=True` on every draw.
Report what varies between draws — expansion, retrieval, or generation — from
the code path. No fix. And say whether the 0.3.1 determinism claim covered this
or only the entity manifest.

## The observation, as printed

| draw | `context_sids` | cited |
|---|---|---|
| 1 | 37 | `J6:37_S00`, `J6:37_S01`, `J6:39_S00`, `LUKE_10:20_S00` |
| 2 | 37 | `J6:37_S00`, `J6:37_S01`, `J6:39_S00`, `J6:45_S02`, `MATT_18:14_S02` |
| 3 | 36 | `J6:37_S00`, `J6:37_S01`, `J6:39_S00`, `J6:45_S02`, `LUKE_10:20_S00`, `MATT_18:14_S02` |
| 4 | 33 | `J6:37_S00`, `J6:39_S00`, `J8:47_S00`, `LUKE_10:20_S00`, `MATT_11:26_S00` |
| 5 | 33 | `J6:37_S00`, `J6:37_S01`, `J6:39_S00`, `J8:47_S00`, `LUKE_10:20_S00`, `MATT_11:26_S00` |

All five: `verified=True`, `refused=False`, and every cited SID inside **that
draw's own** retrieved context (the subset check passed five times).

## 1. The variation is at or before RETRIEVAL. That part is proven.

`context_sids` counts sentence ids in `evidence[*].sentence_data`
(`evals/accept_0_3_3.py:243`). `evidence_objects` is built in `backend/main.py`
at **lines 793–809, from `raw_results`** — and the generation block does not
start until **line 811** (`if bot:`). So the evidence in the response is the
**retrieval result, untouched by the answer LM**.

Therefore: three different context sizes (33, 36, 37) are three different
**retrieved chunk sets**. The retrieval limit is 5 chunks
(`gill_search.py:137`), sentences-per-chunk is a property of the stored chunk,
so a count that moves means the chunk set moved — one swap at the rank-5
boundary is enough to move it by four sentences.

**Variation upstream of generation: established.**

## 2. Expansion or retrieval — this output cannot say which, and both are live

Two candidates, both in the code:

- **(a) The query itself changed.** `backend/main.py:495` sets
  `search_text = optimized_query.expanded_search_terms`, from
  `b.OptimizeSearchQuery` — an **LLM call** (`baml_src/query_router.baml:9`,
  `client LocalRouter`, i.e. the LiteLLM proxy, `temperature 0.0`). A different
  expansion is a different retrieval query and a different embedding, hence a
  different chunk set. Temperature 0.0 is greedy decoding, **not
  reproducibility**: it fixes the sampling rule, not the logits, and nothing in
  the path pins a seed, a provider or a batch.
- **(b) The query was identical and retrieval moved anyway.** The code concedes
  the mechanism itself, at `main.py:727`: *"Weaviate hybrid scores can drift by
  tiny FP amounts between identical queries, so the same chunk SET can arrive
  in different orders."* That comment claims only **reordering**, and it is the
  reason the `raw_results.sort` freeze exists. A drift large enough to cross
  the rank-5 cut would change the **set**, which is the stronger claim the
  comment does not make and which nothing here measures.

The two are not distinguishable from the acceptance output, because the only
retrieval fact it prints is a count.

## 3. Generation is NOT isolated by this run — the count is not the set

Draws 1 and 2 both report `context_sids=37` and cite differently, which looks
like the answer LM choosing differently from one context. It is not that yet:
the script prints `len(ctx)`, and **two sets of equal size need not be the same
set**. Same for draws 4 and 5 at 33.

So nothing in this output shows generation varying. Which is not a claim that
it does not: the answer runs on `GillAnswerLM`
(`baml_src/gill_answer.baml:13`) — `deepseek/deepseek-chat` over OpenRouter at
`temperature 0.0`, a mixture-of-experts model behind a routing layer, where
greedy decoding is reproducible only if the expert routing, the kernels and the
provider are. None of that is pinned, so generation variation is **a priori
expected and here unmeasured.**

**Verdict on the decomposition: retrieval-set variation is proven; whether it
originates in the expansion LLM or in hybrid scoring is open; generation is
unmeasured.** A one-line change to the witness would close the second half of
that — see §5.

## 4. The 0.3.1 claim covered the entity manifest. Only that.

`docs/releases/0.3.2.md` names what 0.3.1 shipped, in the ship table:

> `c9186b1` — Tier-2 entity manifest is a pure function of (query, corpus) — a
> poisoned manifest no longer leaks across requests.

That is the whole scope: the **candidate ORDER inside the entity manifest**.
`backend/gill_search.py:535-566` records the incident and the measurement:
candidates were a `set`, iterated directly, and *"iteration order over a set of
str is randomized per PROCESS (PYTHONHASHSEED), so the same question returned a
different manifest from one server process to the next **while being perfectly
stable inside any one process**"* — measured 30/30 with the good order, 0/30
with the bad one, **zero variation inside any process**.

Two consequences for the witness:

- The five draws hit **one pod** (acceptance items 1 and 2: 1/1 pods), so one
  process, one hash seed. The 0.3.1 defect **cannot** be what moved these
  draws, and these draws are **not** evidence against the 0.3.1 fix. Neither
  confirms nor contradicts it; the axis it fixed is not the axis that moved.
- The claim never reached the retrieval query or the answer. ADR-0013's
  standing rule is about **authority** — *"a stochastic component may never be
  authoritative over a deterministic one"* — and ADR-0013 §"what is BAML's
  entity pick for" settles the division explicitly: *"the lookup owns the
  manifest, gemma keeps query-expansion."* The retrieval query is a **stochastic
  product by design, deliberately.** So five distinct cited-SID sets are the
  **uncovered remainder** of that decision, not a regression against it.

Nothing in 0.3.1, 0.3.2 or 0.3.3 ever claimed the cited-SID set is stable, and
the acceptance script says so where it reports it: *"cited-SID set identical
across draws: False (OBSERVED, not asserted)."* The check that is asserted —
every cited SID inside that draw's retrieved context — passed five times. **The
run is a pass on what it asserts.** Whether answer-level reproducibility ought
to be a claim is a product decision, and it is Chris's, not this lane's.

## 5. What would settle it — at zero prod exposure

The per-stage witnesses **already exist** and are exactly the right ones.
`main.py:742-760` records, into `stages_capture`: `lookup_query`,
`enhanced_query`, `embedding_input`, `embedding_hash`, `retrieval_sids_set`
(sorted — set equality) and `retrieval_sids_ordered` (sequence equality —
*"catches same chunks, different ranking"*), plus
`retrieval_chunk_ids_ordered`.

- **The clean experiment: five draws on gya-test with `GYA_DEBUG_STAGES=1`.**
  `embedding_hash` identical across draws ⇒ the expansion did not move, and the
  variation is retrieval-side; `embedding_hash` moving ⇒ the expansion LLM is
  the source. `retrieval_sids_set` equal while the citations differ ⇒ generation
  varies, measured rather than assumed. One run decomposes all three stages.
  **On gya-test only** — observing them on prod means opening the capture
  channel that acceptance item 4 exists to keep shut, which is the trade the
  script already refuses to make.
- **The cheap half, needing no debug channel at all:** have the witness print a
  hash of the **sorted context SID set** per draw instead of only its length.
  `context_sids()` already returns the set; only `len` is reported. That alone
  separates "same context, different citations" from "different context", on
  prod, out of the ordinary response body. Scoped as a 0.3.4 item.

No fix in this note, per the ruling.

## What this note does NOT establish

- **Which of expansion and retrieval moved.** Two live candidates, both with
  code support; the output cannot choose, and I have not run the experiment
  that would.
- **That generation varies.** It is expected to and is unmeasured. The
  equal-count draws do not show it, because equal counts are not equal sets.
- **That any draw was wrong.** Five different well-cited answers to one
  question are five passes of the check that was asserted. Nothing here grades
  the answers against each other, and the gate's quality clause abstained.
- **Anything about prod's corpus versus gya-test's.** The twelve-for-twelve
  record for this query is on gya-test. These five draws are the first
  observation of the query on prod's corpus, and they are a liveness
  observation, not a comparison.
- **Anything measured on prod with the debug channel open.** It stayed shut.
