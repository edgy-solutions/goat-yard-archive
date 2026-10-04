# Prediction — the temperature check, N=6 on the 13 stochastic questions

> **VOID (2026-10-04)** -- every arm cited in this document ran with the query-expansion
> stage dead: `LITELLM_PROXY_URL` was unset at eval launch. It **is** set in the production API
> pod, so production runs that stage live and none of these arms measures production behavior.
> The numbers below are retired as evidence. Derivation and the full void list:
> [VOID_arms_without_expansion_laneA_20261004.md](VOID_arms_without_expansion_laneA_20261004.md).

Lane A, 2026-09-27. **Locked before the run.** Ruling from Chris: *"run the temperature check at
N=6 on the 13 stochastic questions before OFF-vs-ON, predict first."*

## What is being measured, and why it comes before OFF-vs-ON

The OFF (DSPy) answer path sends **no** `temperature` field. `dspy.LM(...)` leaves
`kwargs["temperature"] is None`, litellm omits it, and deepseek's own default applies — a value
this project has never recorded. The ON path's BAML client sends `temperature: 0`. So **every
OFF-vs-ON arm ever run varied the flag and the temperature together**, and no such arm can say
which one moved the answer. `GILL_ANSWER_TEMPERATURE` (commit `96a8d03`) makes the OFF path's
temperature explicit and recorded so the two can be separated.

The question this run answers is narrower than that confound, and it is the one the pinned floor
left open: **is sampling temperature the source of the 46% stochasticity?** The pinned floor pooled
6 runs per question across two identically-configured arms and found 13 of 28 questions stochastic,
8 of them at exactly 5/6.

## The 13, with their pooled pass counts (pf1+pf2, recomputed from the per-question artifacts)

| question | pooled |
|---|---|
| `real_garden_genesis_3_24_misattribution_001` | 1/6 |
| `simons_count_001` | 1/6 |
| `real_imprecatory_psalms_001` | 3/6 |
| `john_baptist_001` | 4/6 |
| `scapegoat_001` | 4/6 |
| `day_of_atonement_001` | 5/6 |
| `real_christophanies_001` | 5/6 |
| `real_covenant_grace_001` | 5/6 |
| `real_covenant_monocovenantal_001` | 5/6 |
| `real_election_001` | 5/6 |
| `real_ishmael_circumcision_001` | 5/6 |
| `real_singing_psalms_001` | 5/6 |
| `sheep_001` | 5/6 |

Pooled total on the 13: **53/78**. Nine questions are 6/6 and six are 0/6; those 19 are out of
scope and that is a real limit — see the bottom of this file.

## Design

Two arms, back to back, same server process, same pin (`streamlake`, no fallbacks), LM cache
disabled, N=6 on these 13 ids, `integrity.corpus` fingerprinted at both ends of each arm.

| arm | `GILL_ANSWER_TEMPERATURE` |
|---|---|
| `tu` | unset — today's behaviour, deepseek's own default |
| `t0` | `0` — explicit, on both LMs |

The control is run **fresh**, not taken from pf1+pf2. The pf pair is a valid N=6 unset measurement
of exactly these questions, and using it would halve the spend — but it predates
`integrity.corpus`, so it cannot say what corpus it read, and comparing a fresh arm against it
would fold temperature together with 12 hours of possible drift. That is the precise fault nf1/nf2
were retired for this morning; I am not going to reintroduce it to save 78 calls.

## Predictions

Numbered, falsifiable, scored after the run without editing this file.

**P1. Explicit temperature 0 does NOT collapse the stochasticity.** At least **8 of the 13** are
still stochastic (neither 0/6 nor 6/6) in the `t0` arm.

**P2. The 5/6 group does not go clean.** At least **4 of the 8** questions currently at 5/6 still
show at least one failing run in the `t0` arm. If temperature were the mechanism, this group —
one bad run in six — is where it would show first and most cleanly.

**P3. The answers still change.** Temperature 0 is not inert even if it is not the flakiness lever:
on at least **10 of the 13** questions, some `t0` run's answer text differs from every `tu` run's
answer text. The existing one-question probe saw exactly this (digests `0f31b7b7` vs `3e9aed0a`).

**P4. The arms differ ON THE WIRE (companion assertion — without it a null result means nothing).**
Every scored `t0` record has `answer_lm.temperature_on_the_wire == 0.0`; every scored `tu` record
has `"<absent from optional_params>"`. No record in either arm reads `<not recorded>`.

**P5. `compare_arms` raises its ANSWER-LM note on this pair, and that is correct.** The pair is
deliberately non-comparable on configuration. A silent comparison here would be the tool failing.

**P6. Pass counts move, but not much:** the `t0` arm's pooled pass count on the 13 is within **±6
of 78** of the `tu` arm's. Stated because the floor itself is ±5 on 28 questions between identical
arms, so anything inside that band is not a temperature effect at all.

**P7. No STABLE-PASS ↔ STABLE-FAIL flip between the two arms** on any of the 13, under the N=6
classification.

**P8. `integrity.corpus` comes back clean on all four samples** — `changed_during_run: false`,
`provisional: false`, both hashes present. This is the field's first use in a real run; if it
reports a moved corpus, the run is void and gets re-run, not interpreted.

**P9. Wall clock and spend:** 156 scored calls, 25–45 minutes total across both arms, no
degradations, no run-level fault. If a 429 arrives the run aborts and writes nothing.

## The thing most likely wrong

**P1 and P2, in the direction of "temperature is inert."** My reason for expecting the variance to
survive is that the earlier probe found the *unset* arm already byte-identical 3/3 — but that probe
is one question at N=3, which is precisely the power the pinned floor showed cannot discriminate a
p~0.83 question from a deterministic one. If deepseek's unrecorded default is meaningfully above 0,
temperature 0 could collapse most of the 13, P1 and P2 both fail, and the consequence is larger
than this run: **every OFF-vs-ON arm ever run would be confounded beyond repair**, and the
OFF-vs-ON comparison would have to be re-specified with temperature pinned to 0 on both paths
before it is worth spending anything on.

The second most likely wrong is P3 in the other direction — if `t0` and `tu` produce identical text
everywhere, then deepseek's default *is* 0 and the field genuinely changes nothing, which would
make the temperature half of the OFF-vs-ON confound a non-issue and is worth knowing.

## What this run does NOT decide

- **The 19 deterministic questions are not in it.** Temperature 0 could break a question that is
  currently 6/6 and this run would not see it. The ruling scopes the check to the 13; the full-28
  OFF-vs-ON run is where that would surface, and it should be watched for there.
- **If the variance survives, this run does not say where it lives.** The remaining suspects are
  retrieval order (embedding ties and gRPC result ordering are not temperature) and the scorer
  itself. Both need their own instrument; neither is measured here.
- **It does not make the three near-coin-flip questions gateable.** They stay out of the flip gate
  (ruling 1) whatever this run shows, unless it shows them deterministic at temperature 0.
- **One provider, one model.** `streamlake` serving `deepseek/deepseek-chat`. Nothing here
  generalises to another provider's default temperature, which is unrecorded for the same reason.
