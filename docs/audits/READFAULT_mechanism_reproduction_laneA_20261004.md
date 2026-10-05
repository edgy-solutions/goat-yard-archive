# The vector read fault: a reproduction, and where the mechanism is

**Lane A, 2026-10-04.** Ruling 1c of the same date: *"Locate the read-corruption mechanism
(client, hop, response size) with a reproduction; until found, note that any Python path that
reads vectors back inherits it."* The note is committed (`56466e8`, `fingerprint_rest.py`
docstring). This is the reproduction.

**It reproduces, at a rate that makes a full-corpus vector sample unobtainable from this
instance.** The mechanism is not yet named, but one measurement eliminates the hypothesis I
would have bet on.

## Method

READ-ONLY against the **test** corpus, `192.168.1.54:80`. Production (`192.168.1.52`) was never
addressed. GET only; no writes, no deletes.

The corpus was paged exactly as the eval sampler pages it (`limit=20&include=vector`) and every
page was fetched **three** times. Three rather than two because two reads that disagree cannot
say which one is wrong, and the claim already on the record -- "the start sample's digest is the
suspect" -- is itself a claim about which read is the outlier. Recorded per page: the rounded
vector digest per uuid per read, the response **body length** of each fetch, elapsed time, and
object count. Predictions P1-P5 were written into the probe header before launch.

Scope: 365 pages, 7294 objects, 1095 reads, one pass.

## What was measured

| | count | rate |
|---|---|---|
| reads that did not parse as JSON at all | 19 of 1095 | **1.74% per read** |
| objects whose vector digest genuinely disagreed across reads | 8 of 7294 | **0.11% per object** |
| reads that were parseable but carried a corrupted vector | 8 of 1095 | **0.73% per read** |
| **damaged reads, either way** | **27 of 1095** | **2.47% per read** |
| pages with at least one damaged read | 27 of 365 | 7.4% |

The eight real disagreements, by shape: **4 `length`** (4096 against 4095, 4097, 4097, 4098),
**2 `elements`**, and 2 that cannot be shaped because only two reads of that page survived and a
1-1 tie has no majority (see instrument defects).

## The one thing that is now ruled out

**Every read of every affected page returned the identical body length. 0 of 380 records showed
a byte-length difference between reads -- including all 19 reads that could not be parsed.**

A body that fails to parse at *exactly* the length of the two bodies that parse fine is not a
truncated body. Truncation was the live hypothesis -- it is the pending root-cause item for the
other truncation defect in this lane -- and it is wrong here. What the data shows instead:

- the response is always the **right size**, and sometimes has the **wrong contents**
- the two shaped `elements` faults are **perfectly contiguous runs**: indices 607-880 (274 of
  4096 elements, max delta 0.078) and 1907-1912 (6 elements, max delta 0.061). Not scattered
  singletons, and not whole-vector replacement.
- `length` faults land at 4096 plus or minus 1-2 elements, which is what a damaged block
  containing a different number of commas does to a JSON array

Same length, wrong contents, in one contiguous block: that is a **buffer or chunk reassembly**
signature, not a database returning different values. Weaviate is serialising the same object;
something between its socket and the parsed Python object is putting a block of the wrong bytes
into a correctly sized buffer. The remaining candidates are the client (httpx and its decoder)
and the hop -- `:80` on `.54` is an ingress, not the engine port.

Two consistency checks that support treating corruption as per-read and independent:

- all 19 parse failures were **1 of 3** reads, never 2 of 3. At p=1.74% independent, the expected
  count of 2-of-3 events across 365 pages is 0.31, so observing none is consistent.
- the 27 affected pages are spread across the walk (first at page 22; faults at 72, 86, 112, 114,
  173, 190, 221, 357; last at 365). No clustering: not a warm-up, not a late degradation.

## Predictions, scored

| | prediction | verdict |
|---|---|---|
| P1 | at least one uuid disagrees across a full-corpus pass | **HELD** -- 8 |
| P2 | the shape is `elements` with a CONTIGUOUS run, not scattered singletons | **PARTIAL** -- contiguity held 2 of 2, and perfectly. But `elements` is **not** the dominant shape: `length` outnumbers it 4 to 2. I predicted the right geometry and the wrong symptom. |
| P3 | 2 of 3 reads agree and 1 is the outlier | **HELD where measurable** -- 6 of 6 three-read cases had majority 2, outlier 1. Not measurable for the other 2, by a defect in my own probe. |
| P4 | faulting pages are NOT distinguishable by body size at `limit=20` | **HELD, and stronger than predicted** -- not merely indistinguishable between pages but identical *within* a page across reads, which is the finding above. Partly on trust: per-page sizes for clean pages were not serialised, so "faulting versus clean" is argued from the 796k-1178k spread rather than shown from a saved distribution. |
| P5 | the rate is low: order 1 in 100 pages | **FALSIFIED** -- worse by an order of magnitude. Digest disagreements alone are 8 across 365 pages (1 in 46); damaged reads of any kind affect 27 of 365 pages (1 in 14). |

## The cost of the ruling-1b guard, measured

This is the number ruling 1b said it did not have. `stream_chunks` now reads every vector-bearing
page twice and refuses the sample when the two reads disagree on the rounded digest.

Parse failures are **not** the cost: `_fetch_page` already retries them and they recover
(`json_decode_retry`). The cost is the parseable-but-corrupted read, at 0.73% per read. Two reads
per page across 365 pages gives roughly 5.3 expected disagreements, so

> **a full-corpus vector sample refuses with probability about 99.5%.**

That is not a reason to loosen the guard. It is the measurement that says **the eval's corpus
fingerprint over vectors is not obtainable from this instance** until the read path is fixed. The
guard converted a silent 0.11% poisoning of the start sample -- which is what produced the false
"the corpus changed during the run" on both attempt-5 arms -- into a loud refusal. The honest
state is "cannot sample", and that is now what it says.

The repair the data *would* support, and which I am not making because the ruling forbade it:
read until two reads agree. 6 of 6 shaped cases had a clean 2-1 majority, so the majority read is
recoverable. That is a decision about what the sample means, not a code tidy-up, and it belongs
to Chris.

## Defects in my own instrument, named

1. **The probe conflated two different faults.** Its unstable counter fired whenever
   `len(vals) != K`, so a page where one read failed to *parse* flagged all 20 of its objects
   even though the two surviving reads agreed. 372 of the 380 raw records are this artifact --
   the headline `n_unstable: 380` is 19 pages times 20 objects, less the short last page -- and
   the real number is 8. A counter that cannot tell "a read was lost" from "two reads disagreed"
   is the same class of defect this lane keeps finding: an absence scored as an observation.
2. **A two-read tie produces no shape.** With 2 surviving reads and 2 distinct digests the
   majority is 1, no read is an outlier, and the disagreement shape is never computed. 2 of the
   8 real faults are therefore unshaped, and P3 is unmeasurable for them.
3. **Raw bodies were not retained on a fault**, so the most discriminating test available cannot
   be run from this data: whether the corrupted block aligns to a buffer boundary (64 KiB, 16
   KiB) within the body. Per-page sizes for clean pages were not serialised either, which is why
   P4 is partly argued rather than shown.

## What this does NOT solve

- **The mechanism is still not named.** This eliminates truncation and localises the fault to
  "something between the engine's socket and the parsed object, preserving length". Client versus
  hop is not decided, and *nothing here identifies a line of code to change*.
- **The note in `fingerprint_rest.py` stands.** Every Python path that reads vectors back still
  inherits this: the eval sampler, the re-read in `fetch_objects`, the ingestion verifier. A
  0.73% per-read corruption rate means any single unverified read of a vector is wrong about 1
  time in 137, silently.
- **One pass, one client, one endpoint.** The rates above are a single full-corpus walk from one
  machine through one ingress with httpx. They are not known to hold for another client, another
  hop, or `limit` other than 20.
- **Nothing is known about the production corpus.** `192.168.1.52` was not addressed and must not
  be. If the mechanism is the client or this lane's hop, production reads inherit it too; if it is
  this instance's ingress, they may not. That is unmeasured, not reassuring.

## The next experiment, and why it is the discriminating one

Three arms over the same page set, holding everything else fixed, with **raw bodies retained on
every fault**:

1. **a different client** (curl, or a raw socket read) -- separates httpx and its decoder from
   the hop. If curl is clean on the same pages through the same ingress, it is the client.
2. **`limit=1` and `limit=5`** (bodies of roughly 55 KB and 280 KB instead of 1.1 MB) --
   separates a size-dependent mechanism from a per-response one. A rate that falls with body size
   implicates a buffer; a flat per-response rate does not.
3. **block alignment of the corrupted run** in the retained bodies -- a run starting at a
   multiple of 16 KiB or 64 KiB names the buffer directly.

Arm 2 is the cheapest and the most likely to be decisive, and arm 1 needs no Python at all.
