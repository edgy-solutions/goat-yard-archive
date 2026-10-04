# VOID — every eval arm on disk ran without query expansion

**Lane A, 2026-10-04.** Records the production check and executes the ruling that came with it:

> `LITELLM_PROXY_URL` is set in the prod API pod, so expansion is live there; the missing variable
> was eval-launch only. Record that in the handoff and mark every arm that ran without expansion as
> void. Prod pod logs carry only uvicorn access lines, no app logging, so nothing can be verified
> from them.

## The census is derived, not remembered

`evals/expansion_census.py` walks every arm directory and reports expansion health per arm. Run over
both roots (`evals/output/` worktree-local, and the published copies in the private repo):

| arm | questions | expansion errored | not recorded | healthy | cause |
| --- | --- | --- | --- | --- | --- |
| `adr0009_flag/off_20260927c` | 28 | 23 | 5 | **0** | missing env var |
| `adr0009_flag/off_20260927d` | 28 | 28 | 0 | **0** | missing env var |
| `adr0009_flag/on_20260927d` | 28 | 28 | 0 | **0** | missing env var |
| `adr0009_flag/rerun_off_20260927` | 28 | 3 | 25 | **0** | missing env var |
| `noise_floor/nf1_20260927` | 28 | 28 | 0 | **0** | missing env var |
| `noise_floor/nf2_20260927` | 28 | 28 | 0 | **0** | missing env var |
| `pinned_floor/pf1_20260927` | 28 | 28 | 0 | **0** | missing env var |
| `pinned_floor/pf2_20260927` | 28 | 28 | 0 | **0** | missing env var |
| `temperature_check/t0_20260927` | 13 | 13 | 0 | **0** | missing env var |
| `temperature_check/tu_20260927` | 13 | 13 | 0 | **0** | missing env var |
| `temperature_check/tu_provisional_20260927` | 13 | 13 | 0 | **0** | missing env var |
| `temperature_check/scapegoat_t0_replicate_20260928` | 1 | 1 | 0 | **0** | missing env var |
| `floor_20260928/armA` | 13 (78 runs) | 78 runs | 0 | **0** | missing env var |
| `floor_20260928/armB` | 13 (78 runs) | 78 runs | 0 | **0** | missing env var |

**14 arms, 266 questions, zero evidence of healthy expansion anywhere, and exactly one cause in
every single record:** `LLM client 'LocalRouter' requires environment variable 'LITELLM_PROXY_URL'
to be set but it is not`. No 404, no 429, no timeout, no second cause.

Granularity note: the two floor arms carry `expansion_error` per run (the field landed in
`77d3b30`). Every older arm carries it only on the representative response, so for those twelve
"zero healthy" is a representative-level statement — one run of three or six per question, not all
of them. It is not a weaker statement about the arms' validity, because the cause is a server
process-level missing variable, not a per-request flake.

## Two corrections to my own earlier documents

**1. `RESULT_entity_lookup_determinism_laneA_20260928.md` claimed "`rerun_off_20260927` 25/28
healthy, `off_20260927c` 5/28".** That is wrong. Those were questions with **no stages record at
all** — unknown — and I counted them as healthy expansion. The corrected reading is 0 healthy and
25 unknown, 0 healthy and 5 unknown.

The claim appeared in the section arguing that the stage-health gate was needed. Folding silence
into health is precisely the failure the gate exists to prevent, and I committed it in the document
that argued for the gate. The gate's justification survives and is stronger stated correctly: before
it, the record could not distinguish *healthy* from *never recorded*, and the published arms
reported `violations: []` either way.

**2. `PREDICTION_off_vs_off_floor_laneA_20260928.md` claimed "BAML query expansion 404s on model
routing, not on a missing URL".** Also wrong, and it was wrong at the moment it was locked. Every
recorded expansion error in every arm, including the two arms that prediction governed, is the
missing-variable error. Nothing 404'd.

Neither correction rescues an arm. Both make the fault more uniform than I described it: it was not
a varying rate across arms, it was total and single-caused throughout.

## What is void

**All fourteen arms above, and every number computed from them.** Specifically retired as evidence:

- **The 8-of-78 floor** (`RESULT_off_vs_off_floor_laneA_20260928.md`) and the pooled 63/78 figures.
- **The 14-of-78 prior null** and the pooled 55/78 figures (`noise_floor`, `pinned_floor`).
- **The temperature-check numbers**, already retracted on other grounds in
  `ADDENDUM_temperature_check_laneA_20260928.md`.
- **The ADR-0009 flag decision's evidence** (`off_20260927d` / `on_20260927d`, 85 requests per arm).
  The decision itself — the flag **stays OFF** — is the conservative default and nothing acts on the
  void evidence, so no production behavior needs reverting. But the decision is no longer *earned*,
  and re-earning it is the OFF-vs-ON rerun that is next in the queue.

Every one of these ran with the query-expansion stage dead and a `dedup_only` fallback standing in
for it. Production runs that stage live. None of them measures production.

## What is NOT void

**`5c93b28`, the entity-determinism fix.** Its correctness does not rest on any arm. It was
established by three measurements, none of which traverses the expansion stage:

1. 10 unit tests over `_substring_candidates` / `_rank_candidates`, pure functions, no network.
2. A 20-process comparison of the old and new candidate construction side by side, no network:
   old 2 distinct orders, new 1.
3. A 7-seed live probe calling `get_relevant_entities` and reading its output directly: 70/70, one
   distinct manifest.

**But the void review found a scope limit in it that I had not stated.** There are *two* entity
lookups per request:

- **First pass** (`backend/main.py:513`) is fed by `lookup_query` from the **thesaurus** expansion —
  deterministic regex plus a vector match at a fixed threshold. BAML never sees it, and it is
  unaffected by expansion health. This is the manifest the entity boost is anchored on (ADR-0013
  Part C), and it is the one the fix makes a pure function of `(query, corpus)`.
- **Second pass** (`backend/main.py:585`) runs `get_relevant_entities(query=search_text)` where
  `search_text` is **BAML's** expansion. With expansion dead, `search_text` never existed, so
  **this lookup never executed in any of the fourteen arms.** In production it does execute.

The fix applies to the second pass identically — the manifest is a pure function of
`(search_text, corpus)` — but `search_text` is stochastic LM output, so the second-pass manifest can
legitimately vary in production, and a non-`full` second-pass mode downgrades the whole request's
`entity_lookup_mode` (`backend/main.py:595`). That is not a regression of this fix and must not be
read as one. The release acceptance test therefore reads the **first-pass** manifest
(`stages.available_entities`); see `docs/releases/RELEASE_0.3.1.md`.

**The A2 geometry and marker work** (`c52e71e`, `a54ec68`, `8543985`) is unaffected — no LM stage
is involved.

## What this does NOT solve

- **Nothing here replaces an arm.** The void list has no substitute; re-measurement is the next
  item, and it has to be predicted and run after the provider pin.
- **Post-fix production behavior has never been measured here under any configuration.** With
  expansion live, `search_text` exists for the first time in this lane's history: the second-pass
  lookup runs, the BAML entity path and its boost telemetry activate, and the embedding input can
  change. The floor must be re-measured with expansion healthy, not adjusted.
- **Production cannot be verified from pod logs** — uvicorn access lines only. Until a stage-health
  route ships, the only way to read the running server's stages is `debug: true` on
  `POST /api/search`, which any client can set (`backend/main.py:386`, no gate). That is how the
  release acceptance test works, and it is also a standing disclosure worth a separate decision.
- **The eval-launch variable is still unset here**, deliberately: `.env` is not mine to touch, and
  the next arm pair must set it at launch and record that it did. An arm that does not record
  expansion health is void by this same rule.
- **This says nothing about whether expansion being live will change any score.** It changes what
  the measurement *is*. The direction is unknown and unpredicted.
