# Pre-registration lock -- paired `GILL_STRUCTURED_ANSWER` gate run

- **Lane**: A1
- **Written**: 2026-10-25, **before any arm ran**. That is the point of the file.
- **Ruling it serves** (Chris, 2026-10-25, item 4): *"Paired gate run: proceed as
  ruled on the 18th. Predictions first, measured null, ratchet rule, both arms
  on the same gya-test digest, GILL_STRUCTURED_ANSWER the only variable."*
- **Target**: gya-test only. Production (`192.168.1.52`, namespace
  `gya-frontend`) is not addressable from the launcher and is hard-refused by a
  namespace whitelist, born-tested below.

This file is the lock. Anything decided after the first arm starts goes in a
separate section headed as such, dated, and does not get to look like a
prediction.

---

## 1. What is being decided

ADR-0009 added a typed `GillAnswer` via BAML behind `GILL_STRUCTURED_ANSWER`.
The flag is on in gya-test and has never been scored against off. The question
is whether the typed answer path changes answer quality on the reference set,
and specifically whether it **regresses** anything.

**The flag is the only variable.** Both arms run image digest
`sha256:2fce1e3467d5f53e4f0700cdd51530db86cc85c8ef7231f091c6e69509b11433`,
asserted on the pod in each arm's header rather than assumed.

## 2. Evidential population, named before looking

**All 28 questions in `evals/gill_reference_set.jsonl`.** Not a subset, not the
hard ones, not the ones that moved last time. 26 expect an answer, 2 expect a
refusal; 13 hard, 11 medium, 4 easy.

No question is added, dropped or re-labelled after an arm runs. A class
assigned because of the effect under test manufactures a yes, so every class
used in scoring (`category`, `expects`) is the one already in the file.

## 3. Arms

An **arm** is one pod boot at one flag value over all 28 questions with
`--runs 3`. The flag is read at container start, so an arm is defined by a
boot, not by a request; `evals/paired_gate_run.py` refuses to run if the
serving pod booted before the flag was last written.

Every arm gets a **fresh boot**, including the ones whose flag value did not
change. D-004 showed this process has warm-up state that a reader can mistake
for health; a warm pod against a cold pod is a second variable, and symmetry is
cheaper than arguing about it afterwards.

| # | arm | flag | role |
|---|---|---|---|
| 1 | `A1-off-null1` | 0 | measured null, half 1 |
| 2 | `A2-off-null2` | 0 | measured null, half 2 |
| 3 | `A3-off` | 0 | effect comparison, OFF |
| 4 | `A4-on` | 1 | effect comparison, ON |

**The null shares no arm with the effect comparison.** A null built from one of
the compared arms biases toward silence, which is the failure that made a
previous pair give opposite significance verdicts on the same question. Arms 1
and 2 are two identical configurations; whatever they differ by is noise, and
that is the yardstick.

**Order**: 1, 2, then 3, 4. The null runs and is **reported first**, before the
effect pair runs. It is the precondition for reading any delta, not a footnote
to one.

Cost, stated plainly because it is real spend on Chris's account: 4 arms x 28
questions x 3 draws = **336 live requests**, 4 pod boots, on the order of 2-3
hours sequential.

## 4. Predictions, before the run

Recorded to be wrong in public. Each is falsifiable by the arms as designed.

1. **The null will not be silent.** Arms 1 and 2 are identical and will still
   disagree on some questions. Predicted null flip count: **2 to 6 of 28**
   (FLAKY band), with at least 1 question flipping STABLE in one and not the
   other. If the null comes back at 0 I will distrust the run before I trust
   the cleanliness.
2. **The effect comparison will land inside the null band.** Predicted: the
   OFF-vs-ON STABLE-flip count will not exceed the null's flip count, i.e. **no
   detectable effect at n=28, runs=3**. ADR-0009 types the answer; it does not
   change retrieval.
3. **No `must_not_cite` violation under ON.** Predicted 0. This is the one
   prediction whose failure stops the run immediately.
4. **The discard branch is the common path, not the exceptional one.** Predicted
   `raw_query_no_entities` on **more than half** of the 28 questions in each
   arm, driven by the 5-key thesaurus. This is the item-3 measurement and it is
   a prediction, so it can fail.
5. **Both arms will show the same branch population.** Predicted: the
   `raw_query_no_entities` id set differs between OFF and ON by at most the
   null's own variation. `GILL_STRUCTURED_ANSWER` is downstream of retrieval; if
   it moves this set, something is wired differently from how I have described
   it, and that is a finding regardless of the quality numbers.

## 5. Decision rule, fixed before the data

**Hard fail, stops everything**: any `must_not_cite` violation in the ON arm.
Not a count to weigh -- the run stops, the flag stays off, and the question id
is the headline.

**Otherwise, the ratchet.** A regression is a **STABLE-PASS -> STABLE-FAIL
flip** on a question in the effect comparison that is **not** in the null's
flip set. Nothing else counts:

- The pass-rate total is **not** the estimator. `summary.passed` keeps one draw
  per question (the **last** run -- `results.append(last_r)`), and a
  one-draw-per-item estimator manufactures regressions out of flake.
- FLAKY (passes some draws, not all) is the noise band, not a regression.
- The ledger is recomputed from the per-question `<id>.json` `run_passes`
  arrays, not read from `summary.json`'s partial sets -- `stable_pass_ids` is
  not stored, only counted, and a count is not a set.
- **The sign must repeat.** A single pair's verdict is not a verdict. If the
  effect comparison shows flips, the sign has to survive the null's own
  variation on the same question ids; a direction that appears in one pair and
  not in the null's two halves is not an effect.

**What a PASS asserts, stated so it cannot be oversold**: that at n=28 with 3
draws per question, this flag did not move any question from stably-passing to
stably-failing beyond what two identical configurations already move. It does
**not** assert the flag improves answers, and it does not assert an effect
smaller than this design can see is absent. With 28 questions a real effect
below roughly 15% of the set is invisible here. That bound goes in the report.

## 6. The named measurement (item 3)

Chris's words: *"carry it into the paired gate run as a named measurement (how
many questions in the set hit that branch under ON and under OFF, with the
question ids), not as a hypothesis. No change to the branch before the run."*

**No change to the branch.** `backend/main.py` is untouched by this run.

**Instrument**: `expansion_observation()` in `evals/run_eval.py`, computed from
the **plain** response -- no debug flag, no request change, no log correlation.
`expanded_query` in the response *is* the string retrieval ran on
(`backend/main.py:1132` sets it from `search_text`), and `mapped_entities` is
the entity anchor list. The discard branch sets `search_text = req.query` and
`mapped_entities = []`, so its signature is both fields together.

Recorded **per draw**, not once per question, in each `<id>.json` under
`expansion_observations`. The runner otherwise keeps only the last response,
which would have made this count the same one-draw estimator section 5 rejects.

Five states plus `unreported`. A response that does not report the field is
neither a hit nor a miss; a measurement with no "cannot tell" state turns a
silent exit into a claim. Born-tested in
`evals/test_expansion_observation.py`, 9/9, with a check-count assertion.

**What the number cannot say, and this is the important half.**
`raw_query_no_entities` is the **union of two causes**: BAML succeeded and its
output was discarded, *and* BAML errored and retrieval fell to the
deterministic floor. Both set `search_text = req.query`. Separating them needs
`baml_fallback`, which lives in `stages_capture` and is gated on `req.debug`
(`backend/main.py:420`), and the arms run the product path with debug off
because turning debug on for 336 requests changes the path under test
(`_debug_capture` is passed into retrieval at `:722`).

So attribution is a **separate, targeted pass**: after the arms, re-ask only
the ids this field named, once each, with `debug: true`, and read
`baml_fallback` and `baml_error`. That pass is a different request against a
stochastic path, so a question may take a different branch than it did in the
arm. The arm count is therefore the measurement; the debug pass is the
attribution, and the two are reported as separate numbers that may disagree.
If they disagree badly, the disagreement is the finding.

One further gap, found while writing this and not papered over:
`stages_capture["baml_fallback"]` is set at `:682` inside the `except` and at
`:705` for the vector-tier case, so the capture covers all four kinds -- but
the *plain* response covers none. That is the same shape as D-005: the channel
that could tell you which cause fired is not the channel anyone reads.

## 7. Instrument integrity, proven not assumed

`evals/paired_gate_run.py` asserts, per arm, each check able to fail:

1. the live `GILL_STRUCTURED_ANSWER` equals the arm's claim (read by jsonpath
   for that one named non-secret key -- never an env dump, operator-only by
   standing law);
2. exactly one api pod Running and Ready, under the selector **the deployment
   itself declares** (hardcoding one got it wrong on the first try and the
   symptom was a refusal with the wrong reason on it);
3. the pod booted **after** `--flag-written-at`, which is a required argument,
   not derived -- a value the script computed itself could not witness what it
   checks;
4. the pod's `imageID` matches the declared digest;
5. `restartCount` is 0;
6. the namespace is in a test whitelist.

Re-verified **after** the arm, and a pod change mid-arm marks the arm
unscorable rather than scoring it anyway.

Refusals proven by mutation, 2026-10-25, against the live cluster:

| probe | result |
|---|---|
| arm claims flag 0 while live reads 1 | REFUSED, exit 3 |
| wrong digest declared | REFUSED, exit 3 |
| pod booted before the flag was written | REFUSED, exit 3 |
| namespace `gya-frontend` | REFUSED, exit 3 |
| **valid state (liveness)** | **PASSED, exit 0, nothing written** |

The liveness row is not decoration: a probe that only ever refuses passes on
nothing, and four green refusals would have looked identical if the script
refused unconditionally.

## 8. Health is not readable during this run

`/health/stages` is **not** consulted as an acceptance signal for any arm.
Every arm starts cold by design, which is exactly the D-004 window, and
`false` also covers designed suppressions and designed recoveries (D-005).
Reading it here would be reading a known-broken instrument. The arm header
records the pod, digest, flag and boot time instead -- facts, not a flag.

## 9. What this run does NOT solve

- It does not score production. gya-test only.
- It does not fix D-002, D-003, D-004 or D-005, and does not lift the standing
  rule that nothing alerts on `/health/stages`.
- It does not change the discard branch. Whether discarding a successful
  expansion is the right default remains undecided after this run; the run
  produces the count and the ids, which is what was asked for, and the decision
  is a separate one with its own evidence.
- It cannot see an effect smaller than roughly 15% of a 28-question set.
- It says nothing about `ui.image` on gya-test, which is as-running and still
  not gate-verified.
- A run over a dirty tree is marked `provisional` in its own header and may not
  be cited in an ADR or a tier change. The tree is committed before arm 1.

---

## Addenda after the first arm starts

*(Nothing yet. Anything added here is dated and is not a prediction.)*
