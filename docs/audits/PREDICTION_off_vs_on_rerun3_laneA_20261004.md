# PREDICTION — OFF vs ON pair (attempt 5), Lane A, 2026-10-04

> **MARKED (ruling 2, 2026-10-04): the pass figures quoted in this document are in the
> retired unit.** `summary.passed` counted ONE run per question -- the question's last
> scored run -- so a figure like 9/13 described 9 of the arm's 65 runs. The headline is
> now over scored RUNS. Nothing in this document is rewritten and no verdict in it is
> revised: the verdicts rest on the stability block and the integrity gates, which are
> untouched. Corrected figures for every arm, and what the same-config pairs say about
> the instrument, are in [RUNLEVEL_RATE_RESTATEMENT_laneA_20261004.md](RUNLEVEL_RATE_RESTATEMENT_laneA_20261004.md).
>
> The line numbers cited below are as of `56466e8`, i.e. BEFORE this marker was
> inserted and shifted them; every site is quoted as well, so it can be found either
> way.
>
> Affected here: lines 12, 20, 60 -- the priors 12/13 and 9/13 and the P6 band 11-13.
> **The prediction stands exactly as locked and was scored as written.** A locked
> prediction is not re-expressed after the fact; this marker only records that its
> priors are in the retired unit. Run-level for those priors: attempt-4 OFF **49/65 =
> 75.4%** (not 12/13), attempt-5 OFF **42/65 = 64.6%**, attempt-5 ON **38/65 = 58.5%**.


Written and committed **before** launch. Both arms run at one commit, `4702459`
(`fix(bot): the answer path is an input to the record, not an inference`), tree clean, HEAD
asserted identical at both ends of both arms.

Output: `evals/output/off_vs_on_rerun3_20261004/{off,on}` — a fresh directory, never spliced into
attempt 4.

## What changed since attempt 4, and what did not

Attempt 4 produced a citable OFF arm (12/13) and an ON arm **refused at exit 4**: one of 65 scored
runs could not be attributed, because three early returns on the structured path dropped
`answer_lm=` and the caller inferred the path from that absence. `4702459` fixes both halves. The
model, the prompts, the corpus, the retrieval and the scoring are **unchanged** — this is the same
pair, measured once the recorder stopped lying about who answered.

The attempt-4 OFF score is **superseded, not void**: it was a valid measurement at `75955dd`, and
`4702459` touches the OFF path only by routing the same DSPy-history lookup through a function.
It is a legitimate prior for P6 below. The attempt-4 ON score (9/13) is **refused and is not a
prior for anything**, including the direction of the delta.

## Predictions

**P1 — transport and stage validity, both arms.** `expansion`: `errored 0`, `fallbacks {}`.
`entity_lookup`: `{"full": …}` only, no degraded reason. Falsifier: any `errored > 0`, any
fallback, or any `entity_lookup` key other than `full`.

**P2 — retry counters, both arms.** `bound_exhausted 0`, `unobserved 0`, `total` in 0–4,
`max_observed ≤ 2`. I expect `total 0` again: nothing truncated in attempt 4 and nothing about the
transport has changed, so the bounded retry will most likely once more prevent nothing. If it does
fire, the counters must show it — a silent save is the same defect with a different name.
Falsifier: `unobserved > 0`, or `bound_exhausted > 0`, or `total > 4`.

**P3 — the fix, at the layer where it lands. This is the prediction that matters.** The ON arm's
answer-LM table shows **exactly one configuration**: all 65 scored runs `path=baml`, model
`GillAnswerLM`, a recorded temperature, `pin_honored=True`, `provider_served` present. `run_eval`
reports `0 scored run(s) with no recorded temperature at all`.

`answer_lm` is bound at `bot.py:1047` and filled from the Collector at `:1049`, before all three
early returns, so the refusal branches now carry the **real** record, not the backstop. The
resolver's `structured-path-returned-no-record` branch should therefore **never appear**.
Falsifier, and its meaning: if any run comes back with `provider_served_source` starting
`unavailable:`, the gate will refuse again at exit 4 — and that would be **a different defect from
the one fixed**, namely `structured_answer.generate` returning a no-call record because the
Collector saw no calls. I would report it as a new finding, not as this fix failing.

**P4 — exit 0 on BOTH arms, and a real OFF-vs-ON comparison exists for the first time.**
Preflight PASS and postflight PASS on both; `integrity.violations []` on both. Falsifier: any exit
other than 0. Two attempts have ended with no comparison; I am predicting the third does not.

**P5 — the branch that caused the refusal is exercised, or I say it was not.** I expect **at least
one** ON run with `verification_failure True` (attempt 4 had `scapegoat_001` 2 of 5), and every
such run to carry a full `baml` record with a provider and a temperature — the first *live*
evidence the fix works, as opposed to the source check and the code. Falsifier: zero
verification-failure runs. If that happens the fix is **unexercised in flight**, exactly as the
bounded retry still is, and the result document will say so in those words rather than claiming a
clean pair as proof. `bot.py:1185` and `:1202` will almost certainly stay unexercised either way.

**P6 — scores.** OFF in **11–13** (prior: 12/13 at `75955dd`, and the OFF path is unchanged in
substance). ON: **no citable prior exists**, so the honest band is wide — **7–13**.

**P7 — the delta is not readable from the totals, and I predict that in advance.** `|ON − OFF| ≤ 3`
is *noise*, not a finding: 7 of 13 questions were flaky at fixed config in the attempt-4 OFF arm
alone, and the ledger already records two identical arms moving 14 of 78 per question while
pooling to the same total. Whatever the totals are, the reported answer will be a **per-question
decomposition** over the citable pair, and a pooled gap inside ±3 will be reported as
indistinguishable from flake. Falsifier of the prediction itself: a gap of 4 or more, which would
be the first pooled signal worth decomposing for effect rather than for noise.

**P8 — flakiness persists.** `flaky ≥ 3` per arm. Falsifier: either arm with ≤ 2 flaky questions,
which would mean something about run-to-run variance changed and the whole prior set needs redoing.

**P9 — git and corpus axes.** Git: `changed False`, clean at all four samples, `4702459`
throughout. Corpus: 1–6 read-faulted uuids across the pair (measured rate: 3 across 2 arms),
each re-read **confirmed** against the `at_start` sample on `text+vec+dim+last_update_ms`, both
arms **non-provisional** with a named caveat. Falsifier: `provisional True`, a re-read that
differs, or `last_update_ms` moving — the last of which would mean something *wrote* to the test
corpus during the run.

## Endpoints

This pair uses the **gya-test** path only: corpus `192.168.1.54:80`, answer LM through the LiteLLM
proxy on `localhost:4000`. Production corpus `192.168.1.52` is not addressed. **Endpoint D
(`192.168.1.169:11435`) is not touched by this pair** — Lane A2 has priority on it and owns the
substrate. No extraction work is performed here.

## What this prediction does NOT cover

- **The truncation's root cause.** Still unlocalised; no packet capture taken. A clean P2 is not
  evidence about it.
- **The retry on the production path.** That is 0.3.2, with `GET /health/stages`.
- **ADR-0009's merits.** Even a citable pair measures one flag on 13 questions against one corpus
  at one temperature. It cannot say the structured path is better or worse in general.
- **`commit_sha=unknown`** from the server. The launcher's HEAD-freeze assertion is still the only
  guard that the running code is the code at HEAD.
- **The launcher itself**, which still lives in the session scratchpad rather than `evals/`.
- **Whether `scapegoat_001` cites out of context more often under the flag.** One or two runs
  cannot answer it, and the ledger records that question being explained wrongly three times
  already.
