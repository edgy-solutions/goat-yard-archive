# The churn source in `get_relevant_entities`: found, fixed, born-tested

> **CORRECTED (2026-10-04)** -- the fix and the born-tests in this document stand; they do not
> depend on any eval arm. Two claims in it are wrong and are corrected in
> [VOID_arms_without_expansion_laneA_20261004.md](VOID_arms_without_expansion_laneA_20261004.md):
> the arm expansion-health rates quoted below counted *unrecorded* as *healthy* (no arm was
> healthy), and the scope limit around the second-pass entity lookup was not stated.

**Lane A, 2026-09-28.** Answers ruling 1 of the 2026-09-28 directive: *"The churn is located:
get_relevant_entities is nondeterministic on identical input (scape-goat vs spiritual*). Diagnose
which tier and why (ANN, tie-break, cache/time, concurrency); make it deterministic or document why
not; born-test with the scapegoat question x10."*

Base: `d1afdec`, clean tree at diagnosis time. Probe query throughout:
`What is the spiritual meaning of the scapegoat?`

## Which tier, and why

**Tier 2 (substring), candidate iteration order.** Not the ANN, not a cache, not concurrency.

`candidates` was built as a `set()` of `str` and iterated directly. **Iteration order over a set of
`str` is randomized per PROCESS** via `PYTHONHASHSEED` — stable inside any one process, different
between processes. The tier order itself was never random
(`combined = vector_names + substring_names + bm25_names`), and
`return (combined[:total_cap], mode)` truncates at `MANIFEST_TOTAL_CAP = 5` **with no sort**, so the
order inside Tier 2 decided which names survived the cap.

The three competing hypotheses were separated by measurement, not argued:

| hypothesis | how it was excluded |
| --- | --- |
| Tier 1 ANN / embedding jitter | `near_vector` returned `[]` in **all 7** probe processes (nothing within `VECTOR_CONFIDENT_DIST_MAX = 0.25`). The whole manifest came from Tier 2. |
| cache / clock / concurrency drift | 10 sequential calls **inside one process** gave `distinct=1` in every one of 7 processes. Nothing drifts within a process. |
| Tier 2 candidate order | The result partitioned **exactly** by the set iteration order. Confirmed below. |

Pre-fix, 7 processes x 10 calls:

| set iteration order | hash seeds | scape-goat in manifest | distinct results within process |
| --- | --- | --- | --- |
| `scapegoat` first | 3, 4, 6 | **10/10** | 1 |
| `spiritual` first | 1, 2, 5, 7 | **0/10** | 1 |

The mechanism, end to end: candidates are `{scapegoat, spiritual}`. Substring matches are
`scapegoat` -> **2** names, `spiritual` -> **23** names (`limit=25` per candidate). With the cap at
5, `scapegoat` first yields `[scape-goat, antitypical scape-goat, + 3 spiritual*]`, Leviticus 16
reaches the answer LM, and `scapegoat_001` scores 6/6. `spiritual` first yields five `spiritual*`
entities, Leviticus 16 never reaches the answer LM, and the model honestly reports the corpus does
not contain it — 0/6. This reproduces both observed manifests exactly.

That is the shape that reads as "flaky eval" and that **no in-process retry can ever surface**:
inside one server process the bug is perfectly reproducible.

## The fix is two changes, not one

Determinism alone would only **freeze the coin**. `sorted()` happens to put `scapegoat` first for
this query and would put the generic token first for some other one. The reason order MATTERED is
that a generic token floods the shared cap and evicts a distinctive token's exact matches.

1. **`_substring_candidates(query)`** returns a `List[str]` deduped in first-appearance order — no
   set in the order-bearing path.
2. **`_rank_candidates(per_candidate)`** orders candidates **distinctive-first**, by
   `(len(matches), candidate)`. A candidate matching 2 entities spends the cap before one matching
   23. The alphabetical tie-break makes the order **total**, so the manifest is a pure function of
   `(query, corpus)` — no process, clock or seed in it.

This is the ADR-0013 2026-07-13 psalmist failure one layer further in: the length floor stopped
SHORT tokens from matching; this stops a long but GENERIC one from crowding out a precise one.

## Born-test

**1. The property fails on the old code for the right reason** (20 processes, no network, both
constructions run side by side in each):

```
OLD distinct orders over 20 processes: 2  ['scapegoat+spiritual', 'spiritual+scapegoat']
NEW distinct orders over 20 processes: 1  ['spiritual+scapegoat']
```

Note the constant the new code settles on is `spiritual+scapegoat` — the **bad** order under the
old code. Determinism by itself would have frozen this question at 0/6. The ranking step is what
makes it correct, which is why the fix is both.

**2. Live, the scapegoat question x10 across the same seven seeds** (`3,1,2,5,7,4,6`):

```
seed=3 distinct=1 scape=10/10    seed=1 distinct=1 scape=10/10
seed=2 distinct=1 scape=10/10    seed=5 distinct=1 scape=10/10
seed=7 distinct=1 scape=10/10    seed=4 distinct=1 scape=10/10
seed=6 distinct=1 scape=10/10

TOTAL 70/70 across 7 processes.  DISTINCT manifests across processes: 1
  ['scape-goat', 'antitypical scape-goat', 'spiritual reign of Christ',
   'spiritual seed', 'spiritual Israel of God']
```

Pre-fix the same seven seeds gave 30/70. The control is in the same output: the probe still prints
the raw set order, and it still varies across exactly the same seed partition (3,4,6 vs 1,2,5,7).
The randomness is untouched; the manifest no longer depends on it.

**3. `backend/test_entity_lookup_order.py`**, 10 tests, plain `__main__` runner (no pytest in this
venv). 10/10 pass on the fix. Run against `HEAD:backend/gill_search.py` in a scratch tree: 0/10.
That run fails on missing attributes, which is the weak form of a born-test — measurement 1 is the
one that carries the property, and measurement 2 is the one the directive asked for.

## Second gate: per-stage LM health in `integrity`

Ruling 2. `evals/run_eval.py` now captures `stages` **per run** — `expansion_error`,
`expansion_fallback`, `entity_lookup_mode`, `verification_failure` — writes them into every `runs[]`
entry, rolls them up in `integrity.stage_health`, and `check_run_integrity` records a violation
naming `N/M scored run(s) had a BAML query-expansion error - this arm is not comparable against an
arm with different expansion health`. `preflight` warns on a warmup `baml_error`, naming
`LITELLM_PROXY_URL`.

It records and refuses-to-call-clean; it does **not** abort, and there is no flag. The expansion
path is down on this machine, and aborting every run over it would brick the harness while that is
true. 105 -> 111 tests, all passing; the 6 new tests fail against `HEAD:evals/run_eval.py`.

The evidence that this gate was needed is not synthetic: every published arm reported
`violations: []` while expansion errored at rates that **differed between arms**
(`rerun_off_20260927` 25/28 healthy, `off_20260927c` 5/28, `off_20260927d` and `on_20260927d` 0/28).
`.env` was not touched.

## What this does NOT solve

- **It does not make past eval numbers comparable retroactively.** Every arm published before today
  was run on the broken lookup. Which seed each server process drew is not recorded anywhere, so no
  past arm can be re-attributed. They are not re-runnable evidence about `scapegoat_001`.
- **It does not establish that this was the only churn source.** It is one proven source, large
  enough to move a question 6/6 to 0/6. The OFF-vs-OFF floor measured next is what says how much
  churn is left.
- **`entity_lookup_mode` is still coarse.** `full` means "the vector tier did not raise", not "the
  manifest was stable" — it read `full` in both the passing and the failing arm while Tier 1
  returned `[]` in all 7 probe processes. The stage-health block now records the value per run, so
  the coarseness is at least visible in the data; a distinct mode for "vector tier matched nothing"
  is the next instrument and was deliberately NOT added mid-measurement.
- **No per-tier attribution yet.** The record still cannot distinguish "the vector tier returned
  different neighbours" from "the vector tier returned nothing above 0.25 and substring filled the
  slots". Those have different fixes.
- **`limit=25` per candidate is unchanged.** Ranking decides who spends the cap; it does not stop a
  single very generic candidate from filling all 5 slots when it is the only candidate.
- **A latent sibling is left in place.** `extract_potential_entities`
  (`backend/gill_search.py:97`) iterates `set([w, w.capitalize(), w.lower()])` with the same shape.
  It has **zero callers** — dead code. Fixing untested dead code was out of scope; it is named here
  so it is not mistaken for safe.
- **Nothing here is a claim about temperature.** The pin stays; no stability claim.

## Artifacts

- `backend/gill_search.py` — `_substring_candidates`, `_rank_candidates`, incident comment.
- `backend/test_entity_lookup_order.py` — 10 tests.
- `evals/run_eval.py`, `evals/test_run_eval_harness.py` — stage-health block and 6 tests.
- Retraction this builds on: `docs/audits/ADDENDUM_temperature_check_laneA_20260928.md`.
