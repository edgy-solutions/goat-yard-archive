# Prediction — OFF-vs-OFF floor after the entity-lookup fix

> **VOID (2026-10-04)** -- every arm cited in this document ran with the query-expansion
> stage dead: `LITELLM_PROXY_URL` was unset at eval launch. It **is** set in the production API
> pod, so production runs that stage live and none of these arms measures production behavior.
> The numbers below are retired as evidence. Derivation and the full void list:
> [VOID_arms_without_expansion_laneA_20261004.md](VOID_arms_without_expansion_laneA_20261004.md).

**Locked 2026-09-28, before the first scored request.** Base `0545069`, tree clean.
Answers *"Then one OFF vs OFF; report the new floor."*

## The design choice, and why it is not the previous floor's design

The bug fixed in `5c93b28` was **per-process**. Two arms run against the *same* uvicorn process
could never have seen it: inside one process the broken lookup is perfectly reproducible. A
same-process pair is therefore blind to exactly the failure class I just fixed — the same defect as
a gate that cannot see the failure it was built for.

So this pair is deliberately **cross-process**: the server is restarted between arms, and the two
processes are given `PYTHONHASHSEED=1` (arm A) and `PYTHONHASHSEED=3` (arm B) — the two seeds that
pre-fix produced the *bad* and the *good* candidate order respectively, 0/10 and 10/10 on the
scapegoat manifest.

That makes this a **harder** floor than the 2026-09-27 pair (`tu_provisional` vs `tu`, 55/78 and
55/78, 14 of 78 movement), whose process discipline is not recorded. Pre-fix, this design would
have been the worst case. Post-fix it should be indistinguishable from a same-process pair. If the
numbers come back much worse than the old floor, the fix did not do what I claim.

## Configuration, identical in both arms

`GILL_STRUCTURED_ANSWER` OFF, `GILL_ANSWER_TEMPERATURE=0.0` (the pin stays; **no stability claim
is being made for it**), `GILL_DISABLE_LM_CACHE=1`, `RATE_LIMIT=100000/day`, `--runs 6`,
`--timeout 200`, the same 13 stochastic question ids as the temperature check. Nothing is committed
between the start of arm A and the end of arm B. `LITELLM_PROXY_URL` is **not** set and nothing in
`.env` is touched: BAML query expansion 404s on model routing, not on a missing URL, and pointing
that variable elsewhere would also move the embedding source and change retrieval wholesale. Both
arms carry that fault equally, and the new `integrity.stage_health` block is expected to say so.

## Locked predictions

| # | prediction | falsifier |
| --- | --- | --- |
| P1 | `scapegoat_001` is **6/6 in BOTH arms** | anything less than 6/6 in either arm |
| P2 | Pooled per arm in **57–66 of 78** (was 55/78 unset, 62/78 at t=0 with the lucky manifest) | either arm outside the band |
| P3 | The two pooled totals are **within 4 of each other** | a gap of 5+ |
| P4 | Total absolute per-question movement **6–18 of 78** (prior same-config null: 14) | outside the band |
| P5 | **At most 1** STABLE-PASS <-> STABLE-FAIL flip, and **not** `scapegoat_001` | 2+ flips, or `scapegoat_001` flips |
| P6 | `integrity.stage_health` present in both summaries, `expansion.errored > 0` in both, and the expansion violation string present — **both arms NOT clean** | a clean arm, or the block absent |
| P7 | `entity_lookup.distinct_mode == ["full"]` in both arms | any other mode appears |
| P8 | `integrity.violations` contains the expansion violation and **no** temperature violation | a temperature violation appears |

## What a result here can and cannot say

It can say how much run-to-run churn is left on the 13 stochastic questions with the entity
manifest now deterministic. It **cannot** say the fix caused any improvement over 55/78: the
comparison arms were run before the fix, under unrecorded process conditions, and with a different
temperature setting. A same-config pair measures a floor; it does not attribute a delta. If P2
lands high, the honest sentence is "the floor was measured at X" plus "the earlier arms are not a
usable control", not "the fix bought +N".

P1 is the one prediction that is genuinely about the fix, because `scapegoat_001` is the question
whose manifest was proven to swing on the process seed, and the two arms are being given the two
seeds that swung it.
