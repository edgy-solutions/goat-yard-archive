# CORPUS CHANGED MID-RUN was a false positive. The read path corrupts; the corpus did not move.

2026-10-04, Lane A. Subject: the violation that voided
`evals/output/off_vs_on_20261004/off`, recorded there as

```
CORPUS CHANGED MID-RUN ... chunks=7294 text=6cbb33635352 vec=a1e37d2f12c7
                        ->  chunks=7294 text=6cbb33635352 vec=0b903608df60
```

**Verdict: nothing wrote to gya-test. The vector fingerprint moved because the
read of it is not deterministic.** The corpus axis of that arm is clean. It
remains void on the git axis alone — four documentation commits of mine landed
while it was scoring.

## Retraction, first

I previously wrote, and committed, that this was "a real re-embedding, not an
instrument artifact", and justified it by saying I had read the hashing code
rather than assuming. That justification was real and the conclusion drawn from
it was wrong. What I verified was that the **fold** is order-independent
(XOR, `corpus_fingerprint.py:46-53`) and float-tolerant (round to 6 decimals,
`:39-44`). Both are true. Neither says anything about whether the bytes handed
to the fold were the bytes the server sent. I checked the arithmetic and never
checked the input. "Identical text sha, identical counts, 7294/7294 vectors
hashed both times" is consistent with a re-embedding and equally consistent
with a handful of corrupted reads, and I did not notice that the evidence did
not discriminate.

The two candidate explanations were put to me as (A) the fingerprint method
moved, (B) something really wrote. I had asserted B without excluding A.

## Check 1 — nothing has written since May

`_lastUpdateTimeUnix` over every object in both collections, read-only,
cursor-paged (`scratchpad/probe_times.py`):

| collection | objects | unique ids | max last update | written on 2026-10-04 |
|---|---|---|---|---|
| `CommentaryChunk` | 7294 | 7294 | 2026-05-25T01:47:38.136Z | **0** |
| `TheologicalEntity` | 8433 | 8433 | 2026-05-25T01:47:38.160Z | **0** |

The most recent write to gya-test predates the run by 132 days. Zero objects
were written on 2026-10-04 at all, let alone inside the window. **Hypothesis B
is dead**, and it died without needing to find a culprit — which is the point
of asking the database instead of hunting for a job.

The same scan is also the pagination test: unique ids equal the aggregate count
in both collections, so the `after` cursor neither skips nor double-counts. Two
of the mechanisms that could have produced A — cursor drift, and a quantized
vector cache (`pq`, `bq`, `sq` are all `enabled: false`, and `vectorizer: none`
so the server cannot re-embed on read) — are excluded.

## Check 2 — the same object, read twice, is not the same

Two fresh samples of all 7294 chunks through the exact path the eval used
(`fingerprint_rest.stream_chunks`, `limit=20`, `include=vector`), keyed by uuid
instead of folded (`scratchpad/probe_vectors.py`):

```
id SETS identical  : True
id ORDER identical : True
DIGEST DIFFERS on  : 7 of 7294
```

And the seven are not different embeddings. They are **malformed arrays**:

```
079dcd23-...  len 4097 / 4096   199 of 4097 elements differ
22e050b5-...  len 4096 / 4094  3963 of 4096
30ba80a2-...  len 4096 / 4096    86 of 4096
7c577f1b-...  len 4099 / 4096  3422 of 4099
a1e4207b-...  len 4096 / 4096     6 of 4096
```

A 4096-dimension embedding cannot have 4094, 4097 or 4099 elements. The element
values give the mechanism away too: `1`, `0.01`, `0.03017` appearing where
floats belong, and the same number at two precisions in the two samples
(`-0.02981594` vs `-0.0298159417664611`).

Note `30ba80a2` and `a1e4207b`: **correct length, wrong contents.** A structural
length check is necessary and not sufficient.

## Where the corruption enters

One object that disagreed, probed directly (`scratchpad/probe_corrupt.py`):

| read | fetches | vector length | distinct raw-body SHA |
|---|---|---|---|
| single object by id (55 KB) | 10 | 4096 every time | 1 |
| the 20-object page containing it (1.1 MB) | 10 | 4096 ×8, one parse failure | **2** |

The parse failure is `JSONDecodeError: Expecting ',' delimiter: line 1 column
65744` — 207 bytes past 64 KiB.

The server is not the source. `curl` returned byte-identical bodies on 50 of 50
fetches of that page. Python clients did not:

```
truth (curl)              : 1119130 bytes aee96d7fd163, stable 50/50
httpx.get (as used today) : corrupt  2/40
urllib3.PoolManager       : corrupt  8/40
requests.get              : corrupt  0/40
httpx.Client (reused)     : corrupt  0/40
httpx.stream iter_raw     : corrupt  0/40
```

Captured mutation, diffed against curl's bytes (`scratchpad/probe_mutation.py`,
httpx 0.28.1 / h11 0.16.0):

```
same total length (1119130), 18091 bytes differ, span 394800
first differing offset 585293
the corrupt segment is a VERBATIM COPY of the same body at offset 55027 (delta -530266)
```

So the body is reassembled with an earlier block re-emitted over a later
region, preserving total length. Sometimes that breaks the JSON and is visible;
usually it lands inside the 4096-float array — more than 99% of the body's
bytes — and produces valid JSON with a wrong vector. Then the XOR fold converts
it into a corpus-identity verdict that names nothing.

**And `fingerprint_rest.py` hides the visible half.** Its 5-attempt retry loop
catches the JSON decode error and silently re-fetches, so only the
undetectable form of the corruption survives into the fingerprint. A retry
nobody counts is a measurement nobody can audit.

### What is NOT established

Which layer actually corrupts. curl is a separate process with a separate
socket, so "curl is clean" does not localise the fault to a Python library. The
clean Python rows are 0/40 against a base rate of roughly 5%, which is not
evidence of a fix — at that rate 0/40 happens by chance about one time in eight.
**I am not claiming a remedy of "use a different client", and the fix below
deliberately does not switch clients.** `urllib3` being worse than `httpx`
while `requests` (which sits on urllib3) is clean does not fit a simple
library-blame story, and I would need a far larger sample and a packet capture
to say more.

## Check 3 — no lane wrote anything, ever

Every `tool_use` of `Bash`/`PowerShell` across every session log in
`c--Users-cnogr-git-goat-yard-archive` (all lanes share that one project
directory — there is no separate `laneA`/`laneB`/`laneA2` project dir, and the
scan covered the subagent transcripts too), matched against a
Weaviate-write vocabulary: `ingest.py`, `purge_weaviate`, `/v1/batch`,
`.data.insert/replace/update/delete`, `collections.create/delete`, batch
contexts, a write verb aimed at `192.168.1.5x`, `dagster asset materialize`.

11 matches, **all false positives**: `grep`/`sed`/`cat` of the scripts' source,
and my own three scan commands quoting the pattern list. One match falls inside
the run window and it is mine: a `curl -X POST .../v1/graphql` carrying
`{Aggregate{CommentaryChunk{meta{count}}...}}` — an aggregate count, a read.

A first pass with a looser pattern produced 504 lines and told me nothing; it
was matching Python `.replace(` and `.update(` in ordinary document editing.
Worth recording: a scan whose hits are mostly its own vocabulary is not a scan.

## The fix

Per-object attribution, so a fingerprint change can never again be a verdict
about a corpus that nothing can check. Specified in
`scratchpad/SPEC_fingerprint_attribution.md`:

- `fingerprint()` keeps the folds and adds `per_object` (uuid to text digest,
  vector digest, dim, `last_update_ms`), `dim_histogram`, `vector_dim`,
  `dim_anomalies`.
- `classify_change()` sorts a difference into `added` / `removed` /
  `rewritten` / `read_fault`. The discriminator is the one the database already
  owns: **a stored object cannot change without its `last_update_ms` changing**,
  so a digest difference at an identical update timestamp is a bad read, and a
  digest difference at a different timestamp is a write.
- A read fault is **provisional, not a violation**, names the uuids, and says
  the remedy is a re-read. A real change stays the violation it is.
- An unknowable timestamp (`None` on either side) counts as `rewritten`, never
  as a read fault. Unknowable is not benign — same rule as UNCHECKED IS NOT
  HONORED in the scored-run preflight.
- `corpus_changed` returns `None`, not `False`, for a read-fault-only
  difference. Claiming the corpus held still would be the same silent pass in
  the other direction.
- `stream_chunks` validates each page structurally against the modal dim and
  re-fetches an anomalous page, and every retry — including the JSON-decode
  retry that has been swallowing the visible failures — is counted on a
  `faults` list the caller can read.
- The `per_object` map goes to `corpus_objects_at_{start,end}.json` sidecars,
  registered in `run_dir.NON_QUESTION_FILES` so they cannot become phantom
  questions.

## What this does NOT solve

- **The corruption itself is untouched.** This change makes a bad read
  *detectable and named*; it does not stop one happening. Any other consumer of
  a large Weaviate page over a Python HTTP client in this environment is still
  exposed, and nothing in the repo currently checks them.
- **The root cause is unidentified.** Client library, Windows socket layer,
  something between — not established, and the six-path table above is too
  small to localise it. A packet capture against a known-stable server is the
  next real step, and it is not taken here.
- **Structural length validation is not a complete detector.** Two of the seven
  corrupted vectors had exactly 4096 elements. The `last_update_ms`
  discriminator is what carries the detection; the dim check is a cheap first
  net.
- **The discriminator trusts `lastUpdateTimeUnix`.** It is read over the same
  corruptible transport as everything else, and `indexTimestamps` is `None` on
  both collections so it cannot be queried or sorted server-side. A corrupted
  timestamp would misclassify a read fault as a rewrite — which fails toward
  "void the arm", the safe direction, but it is still a claim resting on the
  channel it is auditing.
- **This says nothing about the OFF arm's scores.** They remain uncitable: HEAD
  moved mid-run. One axis being exonerated does not un-void an arm.

## Consequences for the OFF arm

| axis | before today | now |
|---|---|---|
| expansion | 65/65 healthy, no fallback | unchanged, holds |
| corpus | **violation: changed mid-run** | **clean — false positive, retracted** |
| git | provisional: HEAD moved mid-run | unchanged, still void |

The rerun still has to happen, and the reason is now one fault, not two: freeze
HEAD for the whole run. There is no re-embedding to hunt for, and no mystery
writer to find.
