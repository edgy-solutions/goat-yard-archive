# Addendum — the `scapegoat_001` replicate retracts the temperature headline

> **VOID (2026-10-04)** -- every arm cited in this document ran with the query-expansion
> stage dead: `LITELLM_PROXY_URL` was unset at eval launch. It **is** set in the production API
> pod, so production runs that stage live and none of these arms measures production behavior.
> The numbers below are retired as evidence. Derivation and the full void list:
> [VOID_arms_without_expansion_laneA_20261004.md](VOID_arms_without_expansion_laneA_20261004.md).

Lane A, 2026-09-28. Addendum to `docs/audits/RESULT_temperature_check_laneA_20260928.md`.
Read them together. The result document keeps a pointer banner at the top and is otherwise not
edited -- no finding in it is changed -- and this file supersedes its headline.

## The ruling this run was ordered to answer

Chris, ruling 2: *"scapegoat_001: one replicate at t=0 N=6; returns to the gate set only if it
repeats 6/6."*

**It does not repeat. 0/6.** `scapegoat_001` stays out of the gate set. The non-gating set is
unchanged and I am not proposing a change to it.

My prediction, stated in chat before the run: *"scapegoat_001 repeats 6/6 ... if it comes back
mixed (1-5 of 6), the 'deterministic at t=0' reading is wrong and it stays out."* **FALSIFIED**,
and not in the way the escape clause anticipated — it came back 0 of 6, not mixed.

Arm hygiene: HEAD `9d10d678` at both ends, tree clean, `provisional: false`, corpus 7294 chunks
`6cbb33635352` / `dc7968e3290d` identical at both samples, pin `streamlake` no fallbacks, LM cache
off, `integrity.answer_temperature` = `{distinct: [0.0], runs_explicit: 6, runs_absent: 0,
runs_unrecorded: 0}`, 6 attempted, 0 degraded, 0 errored, `violations: []`.

## The headline is retracted

The result document said the two findings that survived its own reading rule were the pooled +7
and the `scapegoat_001` STABLE-FAIL -> STABLE-PASS flip. **Both were the same single question, and
that question now reproduces its failure at the pinned temperature.**

| | with `scapegoat_001` | without it |
|---|---|---|
| tu (unset) pooled | 55/78 | 55/72 |
| t0 (=0) pooled | 62/78 | 56/72 |
| delta | **+7** | **+1** |

A +1 of 72 is inside the measured OFF-vs-OFF null (14 of 78 total per-question movement at
identical config). So:

- **P6 no longer carries the claim.** The entire pooled delta is one question.
- **P7 is dissolved.** The flip it recorded is not a temperature effect, because the same question
  at the same temperature, same corpus and a byte-identical backend is now STABLE-FAIL again.
- **The reading rule published in the result document is itself falsified.** It said that at N=6
  "only the pooled total and an SP<->SF flip carry signal". An SP<->SF flip does **not** carry
  signal at N=6: two arms at identical config produced 6/6 and 0/6 on the same question. A
  6-of-6 swing is inside the null, which is wider than the one null replicate showed.

**Standing statement, replacing the headline: temperature 0 versus unset has no demonstrated
effect on the pass rate at N=6.** Not "no effect" — no *demonstrated* effect. The instrument that
would show one is a larger N, and this pair does not have it.

## Where the divergence actually is, measured stage by stage

The harness stores a retrieval trace, so this is not inferred from outcomes. For the one stored
response per arm:

| stage | t0 arm (6/6) | replicate (0/6) | tu arm (0/6) |
|---|---|---|---|
| `entity_lookup_mode` | `full` | `full` | `full` |
| `available_entities` | **scape-goat, antitypical scape-goat**, +3 spiritual\* | 5x spiritual\* | 5x spiritual\* |
| `enhanced_query` | question + scapegoat entities | question + spiritual\* | question + spiritual\* |
| `embedding_hash` | `74722c995d2fbfc3` | `82feaab0927e4e67` | `82feaab0927e4e67` |
| Leviticus 16 in `evidence` | **16:8, 16:10, 16:22, 16:26** | none | none |
| answer | cites LEV 16:10 / 16:22 | refusal: the indexed corpus does not contain it | same refusal |

The failing t=0 arm and the failing unset arm are **byte-identical** through this whole chain —
same 12 chunk ids, same 12 scores, same embedding hash. The divergence is entirely between the
passing arm and the two failing ones, and it is present in `available_entities`, which is computed
**before** the answer LM is called.

**Temperature cannot reach that stage.** `GILL_ANSWER_TEMPERATURE` sets `temperature` on `lm_auth`
and `lm_anon`, the DSPy answer LMs. `available_entities` comes from
`gill_search.get_relevant_entities`, a three-tier Weaviate lookup — near_vector on qwen3-embedding
(distance <= 0.25, cap 3), substring canonical-key match, BM25 — with no answer LM in it. This is
a structural fact about the code path, not an inference from the numbers.

**The refusals were honest.** In the failing runs the answer LM was never given Leviticus 16 and
said so, naming the nearest indexed material it did have. The system behaved correctly; the
retrieval in front of it did not.

## I retracted a correct claim, which is its own error

Mid-check I wrote that the `scapegoat_001` refusal was "on the retrieval or gating path in the
backend ... not in sampling", at p~0.0002. The result document retracts that in a section titled
*"I was wrong about scapegoat_001, and said so too confidently"*, concluding **"It is sampling."**

The instrumented evidence above says it is not sampling, and that it is the retrieval path.
**That retraction was wrong and is itself retracted.**

This is not a rehabilitation of the original claim. When I made it I had a rejected coin
hypothesis and no retrieval evidence at all — I named a mechanism I had not looked at, and it
happened to land. Being right by luck is not being right, and the lesson stands unchanged. What is
new is the other half of it: **a retraction is a causal claim too.** I reversed a mechanism on one
N=6 arm with no more evidence than I had when I asserted it, and wrote the reversal with more
confidence than the assertion. Both statements were unjustified when made. Only the third one,
here, is built on the trace.

## A second confound, in the ADR-0009 arms and not caught by any gate

Every arm carries `baml_error: "LLM client 'LocalRouter' requires environment variable
'LITELLM_PROXY_URL' to be set"` and falls back to `dedup_only` for query expansion. It is not
uniform across arms, and the arms are not matched on it:

| arm | questions with the expansion path working |
|---|---|
| `adr0009_flag/rerun_off_20260927` | 25 of 28 |
| `adr0009_flag/off_20260927c` | 5 of 28 |
| `adr0009_flag/off_20260927d` | **0 of 28** |
| `adr0009_flag/on_20260927d` | **0 of 28** |
| `pinned_floor/pf1`, `pf2`; `noise_floor/nf1`, `nf2` | 0 of 28 |
| all temperature arms | 0 |

`off_20260927d` and `on_20260927d` are matched on this (both fully down), so it is not a confound
*within that pair* — but `rerun_off_20260927` is 25 of 28 and cannot be compared against either.
Nothing in `integrity` reports it, `violations` is empty in every arm, and no run was marked
degraded. The subsystem announces itself only in a per-question `stages.baml_error` string that
nothing reads.

Two gates cannot see their own failures here:

1. **`integrity` has no expansion-health block.** A run whose query expansion is entirely down
   scores clean.
2. **`entity_lookup_mode: full` does not mean the manifest was stable.** It means the vector tier
   executed without raising. Both the passing and the failing arms report `full` while returning
   different entity sets, so the ADR-0014 fail-loud mode signal is blind to exactly the divergence
   that decided this question.

## Consequence for the production ruling, which is Chris's to make

Ruling 3 was offered with a stated premise: *"the DSPy path sends no temperature ... That's where
the 14-of-78 per-question churn between two identical unset arms comes from, and users see the
same churn."*

**That premise is no longer supported.** At least one large churn source is upstream of the answer
LM, in entity lookup and retrieval, and pinning temperature to 0 did not remove it — the question
that churned hardest churned again with temperature pinned. Pinning production remains defensible
on its own terms (an unrecorded sampling parameter on the live path is worth removing regardless),
but it should not be expected to buy the user-facing stability the ruling was reaching for, and
`simons_count_001` going 3/6 -> 0/6 is still an unexplained cost on the other side.

Separately, and unchanged from the earlier report: it is **not** a one-line config change.
`charts/goat-yard-archive/templates/configmap.yaml` is an explicit per-key allow-list with zero
`GILL_` keys, so it needs a configmap stanza plus a values entry plus a redeploy.

Ruling 1 is untouched by all of this and stays. Pinning the temperature and recording it in
`integrity` is right because an unrecorded parameter is unrecorded, not because it moved a score.

## What this does NOT solve

- **The cause of the entity-lookup divergence is not identified, and I am not naming one.** The
  trace records the entity *names* the three tiers returned, not which tier returned them or at
  what distance. So "the vector tier returned different neighbours" and "the vector tier returned
  nothing above the 0.25 threshold and substring/BM25 filled the slots with spiritual\*" are both
  consistent with everything recorded, and they have different fixes. The next instrument is
  per-tier attribution and distances in `stages`, not another arm.
- **One stored response per arm.** The chain above is one sample from each of three arms. The
  per-run answer digests confirm the six replicate runs were not identical (4 distinct digests,
  the 242-char refusal three times), but per-run *retrieval* is still not persisted, so I cannot
  say all six failed the same way.
- **It does not clear temperature.** It removes the evidence that temperature moved the score; it
  does not show temperature is inert. Six of 13 were still stochastic at t=0.
- **It does not re-open OFF-vs-ON.** That comparison now has two known confounds, not one.
  Expansion health has to be matched, or measured and reported, before an OFF-vs-ON arm pair is
  worth its spend.
- **The `simons_count_001` 3/6 -> 0/6 move is unexplained** and was not traced here.

## Artifacts

- `evals/output/temperature_check/scapegoat_t0_replicate_20260928/` — the replicate, citable
- published by explicit path to `dr-voluminous/body_shadow_vol1/evals/`
