# D-002 — A vector read comes back corrupted, about once in forty pages

**Status:** open, reproduced, mechanism not isolated. Not fixed.
**Found:** Lane A, 2026-10-04, while auditing a `vector_sha256` mismatch between two
fingerprints of a corpus nobody had written to. Reproduction and full numbers:
`docs/audits/READFAULT_mechanism_reproduction_laneA_20261004.md`; the false positive that started
it: `docs/audits/READFAULT_corpus_vector_sha_false_positive_20261004.md`; the eight faults
themselves: `docs/audits/READFAULT_evidence_8_faults_20261004.json`.
Opened as its own defect per the ruling of 2026-10-04, which also retired the double-read guard
that had been standing in for a diagnosis (see "What was retired" below).

## The defect

Reading objects with their vectors from the **test** corpus (`192.168.1.54:80`, class
`CommentaryChunk`) over REST with httpx, `limit=20`, returns a damaged response at a rate that is
not negligible. One full-corpus pass — 365 pages, 7294 objects, 1095 reads, three reads per page:

| | measured | rate |
|---|---|---|
| reads that did not parse as JSON at all | 19 of 1095 | **1.74% per read** |
| reads parseable but carrying a corrupted vector | 8 of 1095 | **0.73% per read** |
| objects whose vector digest genuinely disagreed across reads | 8 of 7294 | **0.11% per object** |
| **damaged reads, either way** | **27 of 1095** | **2.47% per read** |
| pages with at least one damaged read | 27 of 365 | **7.4%** — one page in fourteen |

The eight real disagreements, by shape: **four `length`** (4096 elements against 4095, 4097,
4097, 4098), **two `elements`**, and two unshaped. The two shaped `elements` faults are
**perfectly contiguous runs** — indices 607–880 (274 of 4096 elements, max delta 0.078) and
1907–1912 (6 elements, max delta 0.061). Not scattered, not a rounding artifact.

Faults are spread evenly across the pass (first at page 1, last at 365): not a warm-up, not a
late degradation, not clustered.

## Why it is its own class, not "the network is unreliable"

An unreliable network drops or truncates. This does neither, and that is the whole point:

- **Truncation is ruled out, measured.** Every read of every affected page returned the
  *identical body length* — 0 of 380 records showed a body-length difference, including all 19
  that failed to parse. A short read is not what is happening.
- **A wrong-length vector arrives inside a correct-length body.** 4095 or 4097 floats where 4096
  were written, in a response of exactly the expected size. Something reassembled a buffer, it did
  not lose one.
- **The corruption is contiguous.** A 274-element run with deltas under 0.08 is a chunk of one
  response pasted where another belonged, not noise and not a different embedding.

Taken together the signature is **buffer or chunk reassembly, somewhere between the database's
response and the parsed Python object** — not the stored data. Nothing in the evidence suggests
Weaviate is serving different vectors; it suggests this lane does not always read the ones it
serves.

## Why it matters even though it is "only" a read

1. **It fabricates a write.** A `vector_sha256` computed over a corrupted read differs from one
   computed over a clean read of *the same unchanged corpus*. That is a false "the corpus moved
   mid-run", which under the integrity gate is a non-zero exit on a sound run. This is how the
   defect was found.
2. **A digest cannot audit its own fetch.** The fold's arithmetic was correct throughout; it was
   the input that was wrong. Any check whose only witness is a hash over a single read inherits
   this, silently.
3. **At 2.47% per read, a guard that refuses on any disagreement refuses almost always.** Over
   365 pages the expected number of disagreements is about 5.3, so **a full-corpus vector sample
   refuses with probability about 99.5%.** Its output is the *absence* of a sample.

## What is not known

- **The mechanism.** Remaining candidates are **httpx (or its decoder)** and **the `.54:80`
  ingress hop**. Nothing yet separates them.
- **Whether it generalises.** One pass, one client, one endpoint, one `limit`. The rates are not
  known to hold for another client, another hop, or `limit` other than 20.
- **Production.** `192.168.1.52` was **not addressed and must not be.** If the cause is the client
  or a shared hop, production reads inherit this; if it is this instance's ingress, they may not.
  That is unmeasured, not reassuring.
- **Whether gRPC retrieval is affected.** The product's retrieval path is gRPC; every number here
  is REST. Unmeasured.

## The discriminating next experiment

Three arms over the same page set, everything else fixed, **raw bodies retained on every fault**:

1. **a different client** (curl, or a raw socket read) — separates httpx and its decoder from the
   hop. Clean curl on the same pages through the same ingress names the client. Needs no Python.
2. **`limit=1` and `limit=5`** (bodies near 55 KB and 280 KB instead of 1.1 MB) — separates a
   size-dependent mechanism from a per-response one. A rate that falls with body size implicates a
   buffer; a flat per-response rate does not. Cheapest, and most likely to be decisive.
3. **block alignment of the corrupted run** in the retained bodies — a run starting at a multiple
   of 16 KiB or 64 KiB names the buffer directly.

## What was retired because of this, and what replaced it

- **Retired:** the double-read guard in `backend/fingerprint_rest.py` (`stream_chunks` fetched
  every vector page twice and emitted `vector_unstable`). It worked — and that is why it is gone:
  at a ~99.5% refusal probability it converted a defect in the read into a *missing measurement*.
  Its tests now assert its absence with the loss named
  (`backend/test_fingerprint_rest.py`), so there is a record that the behaviour existed.
- **Kept:** `vector_disagreement`, which names the SHAPE of a disagreement. It is pure, it is what
  `evals/probe_read_fault.py` is built on, and it is the instrument for the arms above.
- **Kept:** the dim-anomaly retry. It repairs a structurally detectable malformation; it is not a
  reproducibility check on a correct-length read, so it is not part of the retirement.
- **Replaced:** the mid-run corpus check no longer reads vectors at all. It is **text sha + chunk
  count + max `last_update`** (`evals/corpus_state.MID_RUN_FIELDS`). The stamp replaces the vector
  hash as the witness of a write that leaves the text identical. It is weaker and says so: a write
  is **detected, not attributed**, and nothing claims the embeddings are what moved.

## What this does NOT solve

- The mechanism is unnamed, so **nothing here is fixed** — the vector channel is simply no longer
  on the mid-run path. A deliberate vector read (a re-vectorisation audit, a retrieval
  investigation) still walks straight into this at 2.47% per read.
- The mid-run replacement **cannot attribute** a detected write to objects, and cannot say the
  embeddings changed. A stamp-only move with byte-identical text is a write that
  `classify_change` still does not name.
- If a corpus carries **no readable `last_update` stamps**, the mid-run check is unknowable, not
  clean. That is honest, but it is also a blind spot on any engine version that omits them.
- Production is unmeasured and stays that way until someone with authority to address
  `192.168.1.52` decides otherwise.
