# D-005 — `/health/stages` gives a designed suppression and a stage fault the same value

**Status**: open. Scheduled for 0.3.4 by ruling (Chris, 2026-10-25, item 2),
together with [D-004](D-004-cold-process-stage-health-false-alarm.md).
**Found**: 2026-10-25, reading the 0.3.2 production acceptance.
**Affects**: 0.3.2 and 0.3.3 identically — `backend/stage_health.py` is
byte-identical across them, and all four fallback kinds predate both.
**Sibling**: D-004 is the *zero-observation* conflation (nothing has run yet
reads as a fault). This is the *designed-outcome* conflation (the system did
exactly what it was specified to do, and that reads as a fault too). Same
endpoint, same `false`, different causes — which is why they are two entries.

## What happens

The production acceptance returned `{"entity_lookup": true, "expansion": false}`
on a healthy release. Expansion had **run and succeeded**: BAML returned four
usable terms in 6.27s. It returned no entities, the structural sentinel at
`backend/main.py:518` deliberately raised on that (ADR-0008 step 2b), the
fallback dispatch took the designed branch for it, and `record_request` counted
an `expansion_error`. Nothing was broken, and the flag read exactly as it reads
when something is.

## The four fallback kinds, and what each one means

`stages["expansion"]` is false if `errored > 0` **or** `fallbacks > 0`
(`backend/stage_health.py`, the expansion computation). The four kinds that can
set `fallbacks`:

| kind | site | what it means | is it a fault? |
|---|---|---|---|
| `anchored_manifest_trusted` | `main.py:647`, inside `except` | ADR-0013 Part D: the punt was a coin-flip, the thesaurus fired, so the anchored manifest is kept | **no — the system RECOVERED** |
| `poisoned_manifest_suppressed` | `main.py:656`, inside `except` | ADR-0012: punt plus thesaurus drought, so the entity boost is suppressed on purpose | no — designed suppression |
| `dedup_only` | `main.py:676`, inside `except` | ADR-0008 step 2d: case-insensitive duplicates stripped from the lookup's manifest | no — routine normalisation |
| `vector_tier_degraded_suppressed` | `main.py:709`, **outside** `except` | ADR-0014: the entity tier's embedding call degraded, so the manifest is untrustworthy and the boost is suppressed | the fault is **in another stage** |

Three consequences follow, none of them a 0.3.2 or 0.3.3 regression:

1. **`false` spans at least four meanings**: the stage faulted; a designed
   suppression fired; a designed *recovery* worked; and (D-004) nothing has run
   yet. `false` is the value that pages someone, so it has to mean one thing.
2. **One fault can read as two unhealthy stages.** When the entity tier
   degrades, `entity_lookup` goes false on its own mode counter *and* ADR-0014
   drives `expansion` false through `vector_tier_degraded_suppressed`. A
   consumer counting unhealthy stages double-counts a single infrastructure
   blip.
3. **`anchored_manifest_trusted` is the sharpest case.** It is the branch that
   exists *because* the punt is unreliable, and taking it successfully is the
   good outcome. It still reports the stage unhealthy.

## A false comment, corrected here

`backend/stage_health.py`'s comment above the expansion computation says a
fallback is only ever recorded in the BAML-expansion `except` block, so
"fallbacks without errored should be impossible", and keeps the condition
defensively anyway. The guard is right; **the stated reason is wrong.**
`vector_tier_degraded_suppressed` is assigned at `main.py:709`, after the
`except`, and `main.py`'s own comment there says it "can fire on the
BAML-success path too (no exception, so fallback_kind would otherwise be
unset)". So fallback-without-error is not merely possible, it is a documented
path. Nothing behaves wrongly because of the comment — the condition already
covers it — but the comment is what a reader uses to decide whether the OR arm
matters, and it tells them it does not.

A first version of the 0.3.2 release record said two fallback kinds fire on the
BAML-success path. Only one can; the other three are inside the `except`. That
line is corrected in `docs/releases/RELEASE_0.3.2.md` on `release-0.3.2`, and
the correction is recorded here so the wrong count is not carried forward.

## Fix, as ruled

1. **A third state for every stage that can suppress by design**, alongside
   `not_observable`. `false` means "observed and faulted" and nothing else. A
   stage whose latest outcome was a designed suppression or a designed recovery
   reports in its own bucket, named so a consumer cannot mistake it for health
   or for a fault.
2. **Which stages those are is a property of the build, not of the last
   request** — the same principle as D-004's fix. Expansion can suppress by
   design because ADR-0012/0013/0014 are in this build's code path; that is
   decided at import, not inferred from a counter. A stage joins the set by
   declaration, so adding a suppression branch without declaring it is a
   visible omission rather than a silent re-use of `false`.
3. **Derive both D-004's and this entry's buckets from the build/code path**,
   in one pass. They are the same defect in the data model — a boolean asked to
   carry more than two outcomes — and fixing one while leaving the other means
   the endpoint still has a value that means two things.

## Born-test

The test has to make the distinction the endpoint currently cannot:

- Record a request whose only non-nominal signal is `poisoned_manifest_suppressed`
  with **no** `expansion_error`, and assert `expansion` is **not** `false` and
  **not** `true` — it is in the suppression bucket, named.
- Record a genuine expansion fault and assert `expansion` **is** `false`.
- Record `anchored_manifest_trusted` and assert it lands in the suppression
  bucket too, not in `false`, because a recovery is not a fault.
- Assert the set of design-suppressing stages is **non-empty** and derived from
  the module, not from the request stream — a born-test that passes against an
  empty set has tested nothing, which is the same failure as a probe that
  misses and therefore passes on nothing.
- Assert the two buckets are **disjoint** and that no stage appears both in
  `stages` and in either bucket, the same KeyError-over-wrong-answer property
  `not_observable` already has.

## What this does NOT cover

- It does not change any retrieval behaviour. Whether discarding a successful
  expansion when the entity map comes back empty is the right default is an
  **answer-quality** question, carried into the paired gate run as a named
  measurement (how many questions hit that branch under each arm, with ids), not
  settled here. **No branch is being changed before that run**, by ruling.
- It does not fix D-003. `/health/stages` still cannot tell flaky transport from
  broken transport; that is a third conflation with its own entry, and a stage
  that succeeded after retries is a separate question from one that was
  suppressed by design.
- It does not make `answer` or `verifier` observable.
- **Until both this and D-004 are fixed, nothing alerts on `/health/stages`** —
  stated as a standing rule in `docs/releases/RELEASE_0.3.2.md` and in
  `docs/releases/0.3.3.md`, because an operator wiring a monitor does not read
  defect files.
