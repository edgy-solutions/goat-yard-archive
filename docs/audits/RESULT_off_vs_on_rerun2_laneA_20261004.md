# RESULT — OFF vs ON pair (attempt 4), Lane A, 2026-10-04

Prediction: [`PREDICTION_off_vs_on_rerun2_laneA_20261004.md`](PREDICTION_off_vs_on_rerun2_laneA_20261004.md),
committed in `75955dd` **before** launch. Both arms ran at that commit, tree clean, HEAD frozen
and verified identical at both ends of both arms.

Output: `evals/output/off_vs_on_rerun2_20261004/{off,on}`. Pair start 20:14:06Z.
OFF 15:14:40–15:42:11 (27.5 min). ON 15:43:06–16:17:51 (34.8 min).

## Headline

**There is still no OFF-vs-ON comparison.** The OFF arm is complete and citable. The ON arm ran to
completion and was **refused at `run_eval` exit 4**: one of its 65 scored runs carries no record of
which model answered it, at what temperature, or whether the provider pin was honoured. One
unchecked run makes the arm a mixture rather than a sample, and the gate refused it.

**The retry fix held, and it was never exercised.** Both arms: `errored 0`, `bound_exhausted 0`,
`unobserved 0`, `retries.total 0`. No request truncated this time, so the bounded retry prevented
nothing — it is still verified only by its born test, not by a live save. Named so the next
document does not treat a clean pair as evidence the retry works in flight.

## Validity first, before any score

| | OFF | ON |
|---|---|---|
| `run_eval` exit | **0** | **4** (post-run integrity violation) |
| preflight / postflight | PASS / PASS | PASS / not reached (aborted first) |
| `expansion` | `ok 67, errored 0, fallbacks {}` | `ok 67, errored 0, fallbacks {}` |
| `expansion.retries` | `total 0, calls_with_retries 0, max_observed 0, bound_exhausted 0, unobserved 0` | same |
| `entity_lookup` | `{"full": …}` only | `{"full": …}` only |
| git axis | `changed False`, clean both ends, `75955dd` → `75955dd` | same |
| corpus axis | `changed None`, re-read **confirmed**, `provisional False`, 1 caveat (2 uuids) | `changed None`, re-read **confirmed**, `provisional False`, 1 caveat (1 uuid) |
| runs | 65 total / 65 scored / 0 degraded / 0 errored | 65 / 65 / 0 / 0 |
| `integrity.violations` | `[]` | **1** (see below) |

`ok 67` is the server's cumulative per-process counter: 65 scored + the eval's own warmup + the
preflight probe. It is not a 67-run arm.

**P3 is resolved live and in the affirmative.** `unobserved 0` over all 67 requests in each arm, in
two separate server processes, is the first real evidence that the per-request `baml_py.Collector`
reaches the recorder inside the running server. The counters are speaking, not defaulting.

**P4 is the cleanest pass in this pair, and it is the ruling working as designed.** Read faults
appeared in *both* arms — 2 objects in OFF, 1 in ON — and in both the post-run re-read matched the
`at_start` sample on `text+vec+dim+last_update_ms`, so both arms are **non-provisional** and carry
a named caveat instead. Under the old rule both arms would have been uncitable on the corpus axis
for a fault that never touched the data. The read-fault rate is now measured at **3 objects across
2 arms**, consistent with the ~7-in-7294 client-side corruption.

## The ON arm's violation, and its cause

> `0 scored run(s) sent no explicit temperature and 1 scored run(s) have no recorded temperature at
> all` — and, in the answer-LM table: `64 run(s) baml/GillAnswerLM … pin_honored=True` plus
> `1 run(s) dspy/None model=None temperature=<not recorded> pin_honored=None
> provider_served_source=unavailable:no-dspy-call-added-to-history-during-this-request`.

The run is **`scapegoat_001` run 2 of 5**: `verification_failure True`, 170-char answer, 10.66s of
generation, `entity_lookup full`, no expansion error.

**The cause is established by a digest and the code, not by a story.** The answer is byte-identical
to `degradation.VERIFICATION_FAILURE_ANSWER` — `sha256[:16] = 8b3621053b5aea2e`, 170 chars, equal
to the run's recorded `answer_sha16` and `answer_chars`. That string is returned from exactly one
place, `backend/bot.py:1260`, the `cited_sources_not_in_context` branch. So:

1. The BAML answer call **did happen** (10.66s, and the structured-path debug line printed): the
   model cited a sentence id that was not in the retrieved context.
2. `bot.py` returned the typed verification-failure refusal. **Three early returns on that path
   (`bot.py:1178`, `:1194`, `:1260`) construct a `dspy.Prediction` without `answer_lm=`** — only
   the final return at `:1327` carries it.
3. `main.py:997-1005` sees a falsy `pred.answer_lm` and **infers the DSPy path from its absence**.
   It consults the DSPy LM history, finds no new call (correctly — there wasn't one), and writes
   `no_call_record("dspy", "no-dspy-call-added-to-history-during-this-request")`.
4. So a real BAML call, whose provider and temperature were sitting in the collector, was recorded
   as an **unchecked DSPy non-call**. The eval saw two configurations, called the arm a mixture,
   and refused it.

**This is a recording defect, not an answering defect.** The refusal at step 2 is the product being
honest: it would not repeat a reference it could not show. What turned that honesty into a false
record was a `return` statement with one missing keyword argument, and an inference — *falsy means
DSPy* — that is simply not sound on the structured path. Same family as the p4 footnote fabrication
in the ledger: a correct "nothing here" from a component became a wrong positive claim downstream
because the channel for it was missing.

**The gate was right to refuse, and it refused for the right reason.** It did not notice a score
change; it noticed that one run could not be attributed. That is what P6 asked of it.

## Scores — OFF only

| | OFF (citable) | ON (**refused, not citable**) |
|---|---|---|
| pass rate | **12/13 (92.3%)** | 9/13 (69.2%) |
| refusal correctness | 13/13 | 13/13 |
| `must_not_cite` violations | 0 | 0 |
| answer LM | 65 runs, one config: `dspy/dspy.LM`, `deepseek/deepseek-chat`, temp **0.0**, served by **StreamLake**, `pin_honored True` | 64 runs `baml/GillAnswerLM` pinned + **1 unchecked** |
| STABLE-PASS / FLAKY / STABLE-FAIL | 6 / **7** / 0 | 6 / 5 / 2 |

OFF flaky detail: `simons_count_001` 1/5, `john_baptist_001` 2/5,
`real_garden_genesis_3_24_misattribution_001` 2/5, `real_imprecatory_psalms_001` 3/5,
`real_singing_psalms_001` 3/5, `real_covenant_grace_001` 4/5, `sheep_001` 4/5.

**The 12-vs-9 gap is not a finding and is not reported as one.** The ON arm is refused, so its
number is not a measurement. Even if it were, **7 of 13 questions are flaky at fixed config in the
OFF arm alone** — a 3-question gap sits inside that band. Any OFF-vs-ON claim needs the per-question
decomposition over a citable pair, not a difference of totals.

## Prediction scored

| | predicted | observed | verdict |
|---|---|---|---|
| P1 | `errored 0`, no fallbacks, `entity_lookup full` only, both arms | exactly that | **PASS** |
| P2 | `bound_exhausted 0`, `unobserved 0`, `total` 0–4, `max_observed ≤ 2` | `0 / 0 / 0 / 0` | **PASS** (at the bottom of the band; the retry was never needed) |
| P3 | `unobserved` is the risk; 65 would mean broken wiring | `0` over 67 requests × 2 processes | **PASS** |
| P4 | 1–6 read faults, `reread confirmed`, `provisional False`, one caveat | 2 (OFF) and 1 (ON), confirmed, non-provisional, one caveat each | **PASS** |
| P5 | git clean, HEAD frozen at the prediction's commit | `75955dd` at all four samples | **PASS** |
| P6 | preflight and postflight PASS on both arms, exit 0 on both | gates passed; **exit 4 on ON** | **FAIL on the exit code** — and the gate was right |
| P7 | one distinct `answer_lm` per arm, `pin_honored true` | true in OFF; **two configurations in ON**, one unchecked | **FAIL (ON)** |
| P8 | OFF in 7–13; `\|ON − OFF\| ≤ 2` | OFF **12**; the delta is unscoreable | **PASS on OFF**; the delta half is unanswered |
| P9 | `flaky ≥ 3` per arm | OFF 7, ON 5 | **PASS** |

P7 is the one that matters: it was written as a provider-pin prediction and it failed for a reason
that has nothing to do with providers. The prediction assumed one answer path per arm, and the
structured path has a branch that answers without saying who answered.

## What this result does NOT establish

- **Nothing about ADR-0009.** Two attempts have now produced an OFF arm and no ON arm. The flag's
  effect on the pass rate is still unmeasured.
- **Nothing about the retry in flight.** `total 0` means it never fired. A clean pair is not
  evidence that the retry rescues a truncated body; only the born test speaks to that.
- **Nothing about the truncation's root cause**, which is still not localised. No packet capture
  has been taken.
- **Nothing about the other two early returns.** `bot.py:1178` and `:1194` have the same missing
  argument, and no run in this pair hit them, so their behaviour is inferred from the code rather
  than observed.
- **Whether `scapegoat_001` cites out of context more often under the flag.** It is 2/5 in ON and
  flaky in OFF too; one run is one run. The ledger already records this question being explained
  wrongly three times, and this document does not add a fourth explanation of its *scores* — only
  a proven account of how one of its runs was *recorded*.
- **`commit_sha=unknown`** from the server in both arms, so the HEAD-freeze assertion in the
  launcher remains the only guard that the running code is the code at HEAD.
