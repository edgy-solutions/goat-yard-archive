# Result — item (a): the noise floor, OFF vs OFF

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
> Affected here: lines 12, 66, 77, 89, 96. Run-level: nf1 **49/84 = 58.3%** (not 42.9%),
> nf2 **42/84 = 50.0%**, pf1 **55/84 = 65.5%** (not 75.0%).
>
> Two of this document's readings invert. (a) The opening comparison, pf1's 21/28
> against nf1's 12/28, is a 32.1 pp gap in the retired unit and **7.2 pp** over every
> run -- at or near the 4-8 pp the floor pairs put the instrument at. (b) The nf1 -> nf2
> move that this document reads as going **up** (12 -> 14) is **58.3% -> 50.0%**, i.e.
> DOWN, at run level. The pair stays RETIRED either way and neither number is a floor.


> **VOID (2026-10-04)** -- every arm cited in this document ran with the query-expansion
> stage dead: `LITELLM_PROXY_URL` was unset at eval launch. It **is** set in the production API
> pod, so production runs that stage live and none of these arms measures production behavior.
> The numbers below are retired as evidence. Derivation and the full void list:
> [VOID_arms_without_expansion_laneA_20261004.md](VOID_arms_without_expansion_laneA_20261004.md).

> **RETIRED AS A BASELINE — ruling 1, 2026-09-27.** Neither arm can state what it
> measured: both ran over a dirty tree, nf1 predates `integrity.git` and `answer_lm`, and
> neither recorded corpus state. pf1 — same day, same pin, same cache setting, same DSPy
> path — scored 21/28 against nf1's 12/28 with no scorer-semantics commit in the window, and
> that 9-question gap cannot be attributed. **Do not cite either arm as a baseline, a floor, or
> the comparison point for a later run.** Superseded by the pinned pair pf1/pf2 in
> `docs/audits/RESULT_pinned_floor_laneA_20260927.md`; the full withdrawal, including what
> remains citable, is `docs/audits/RETIRED_noise_floor_laneA_20260927.md`. What stands
> below: the prediction scorecard as calibration history, and the two harness faults this
> pair exposed.

Lane A, 2026-09-27/28. Prediction locked **before** the run at sha16 `5ab1cfe0ac2a6485`
(`evals/output/noise_floor/PREDICTION_noise_floor_20260927.md`, hash re-verified unedited after the
run). Chris's ordering item (a): *"Noise floor: run OFF vs OFF, identical settings, provider pinned
and recorded; report questions that flip between identical arms. No arm comparison is reportable as
a difference below that floor."*

Arms: `nf1_20260927` (finished 2026-09-27T23:52:13Z) and `nf2_20260927` (finished
2026-09-28T00:16:34Z). 28 questions × 3 runs × 2 arms = 168 runs, **84 scored / 0 degraded /
0 errored per arm**, 0 integrity violations, both pinned to `{"order": ["streamlake"],
"allow_fallbacks": false}`, LM cache disabled on both. Scoring:
`evals/output/noise_floor/prediction_scoring_20260927.json`; per-question diff:
`evals/output/noise_floor/arm_diff_nf1_nf2.json`.

## Two deviations from the run's own setup, stated before any result

**1. The tree was not clean, contrary to the prediction's own clause** (*"Tree must be clean at run
time or the result is provisional and cannot be cited (ruling 4)"*). Arm 1 ran entirely over a dirty
tree. Arm 2 ran over a dirty tree and then a clean one: I committed `dc573ca`, `40de485` and
`1dcd16f` at 19:05, 19:08 and 19:10 local, all **during** arm 2, which finished 19:16.

What bounds the consequence, measured rather than asserted: those three commits touch ten files, all
under `pipeline/` and `docs/`. `git diff --name-only HEAD~3..HEAD -- evals/ backend/ baml_src/
baml_client/` is **empty**, and `evals/run_eval.py` and `backend/` are both at `041decc` — the exact
commit the prediction names — unmodified in the working tree throughout both arms. So the run path
was byte-identical across the pair, and the run is reproducible from `041decc`.

By the letter of ruling 4 this pair is **provisional**. I am not going to quietly decide that
run-path disjointness satisfies a rule written about the tree; that is Chris's call. What I will say
is what the deviation can and cannot have caused: it cannot have changed the run path, and it does
not affect any number below.

**2. The server was restarted between the arms, deliberately.** OFF-vs-ON spans two server
processes, so an in-process floor would understate the noise this instrument actually has. That
decision was made *after* the prediction was locked, and it can only widen the floor, never narrow
it. Recorded here rather than presented as part of the design.

## The 16 predictions, scored

| # | Claim | Verdict | Observed |
|---|---|---|---|
| **P1** | class changes between identical arms **3–8** | **FALSIFIED** | **11 of 28** |
| **P2** | STABLE-PASS ↔ STABLE-FAIL flips **0–2** | **HELD** | **0** |
| P3 | both arms lm_cache off, pin recorded | HELD | pin identical and constant |
| P4 | 0 integrity violations | HELD | `[[], []]` |
| P5 | ≤ 6 degraded of 168 | HELD | 0 |
| P6 | 0 NO-DATA | HELD | none |
| P7 | each arm passes 14–19 of 28 | **FALSIFIED** | `summary.passed` 12 / 14; STABLE-PASS 9 / 7 |
| P8 | abs delta passes ≤ 3 | HELD | 2 |
| P9 | FLAKY 8–14 per arm | HELD | 12 / 11 |
| P10 | refusal-correct 26–28 per arm **and** set diff ≤ 1 | **FALSIFIED** | 26 / **25**; set diff 1 (`real_imprecatory_psalms_001`) |
| P11 | 0 `must_not_cite` | HELD | 0 / 0 |
| P12 | `zone3_notes` never non-empty on either OFF arm | HELD | 0 / 0 in the server logs — but see the probe defect below |
| P13 | `partial_match_sids` empty 28/28 both arms | HELD | none non-empty |
| P14 | Garden STABLE-FAIL 0/3 **both** arms | **FALSIFIED** | FLAKY 2/3 → STABLE-FAIL 0/3 |
| P15 | median answer length within ±15% | **FALSIFIED** | 856.5 → 695.0, **−18.9%** |
| P16 | both summaries record the identical pin | HELD | identical |

**11 held, 5 falsified.** P7 as I wrote it is ambiguous between `summary.passed` and the STABLE-PASS
count; both are scored above, because I wrote the prediction and cannot pick the flattering reading
afterwards. It is falsified under either.

## The floor, per metric

Nothing below this line is reportable as an arm difference:

| metric | floor measured between two identical arms |
|---|---|
| stability-class changes | **11 of 28** |
| STABLE-PASS ↔ STABLE-FAIL flips | **0** |
| `summary.passed` total | **2 questions** |
| STABLE-PASS count | **2 questions** |
| refusal-incorrect set | **1 question** |
| median answer length | **19%** |
| Zone-3 assertive-slant sweep firings | **3 per 84 runs** (5 on nf1, 2 on nf2) |

The class-change floor of 11 of 28 means a 2–4 question difference is invisible to this instrument,
exactly as the 36–43% FLAKY rate implied. Note that `summary.passed` went **up** 12 → 14 while the
STABLE-PASS count went **down** 9 → 7 on the same pair: the harness's headline pass rate and its
stability classes moved in *opposite directions* between identical arms, so neither is quotable
alone.

The 11 changes, none of them a direct flip:

```
logos_001                                    FLAKY       -> STABLE-PASS  2/3 -> 3/3
predestination_001                           STABLE-PASS -> FLAKY        3/3 -> 2/3
real_benjamin_type_001                       STABLE-PASS -> FLAKY        3/3 -> 2/3
real_christophanies_001                      FLAKY       -> STABLE-PASS  2/3 -> 3/3
real_covenant_monocovenantal_001             STABLE-PASS -> FLAKY        3/3 -> 2/3
real_garden_genesis_3_24_misattribution_001  FLAKY       -> STABLE-FAIL  2/3 -> 0/3
real_imprecatory_psalms_001                  FLAKY       -> STABLE-FAIL  1/3 -> 0/3
real_ishmael_circumcision_001                STABLE-PASS -> FLAKY        3/3 -> 2/3
real_justification_001                       FLAKY       -> STABLE-PASS  2/3 -> 3/3
real_matthew_28_17_period_001                STABLE-PASS -> FLAKY        3/3 -> 2/3
simons_count_001                             FLAKY       -> STABLE-FAIL  2/3 -> 0/3
```

P2 holds only because no question was 3/3 on one arm and 0/3 on the other. Three questions did reach
STABLE-FAIL from FLAKY, two of them from 2/3. So "a question became STABLE-FAIL" has a floor of
**3 of 28** even though the strict SP↔SF flip floor is 0.

## What this does to ruling 1 — the stability gate does not survive, and the mechanism evidence shrank

P2 came back **0**, so the prediction's stated commitment (*"If P2 comes back ≥ 1 … the stability
argument for keeping the flag off does not survive"*) is not triggered by its own letter. Reporting
only that would be hiding behind a threshold. Three things this pair found that are worse than the
condition I set:

**1. The flipping question is STABLE-FAIL on OFF under the pinned provider.** Ruling 1's gate was
one SP→SF flip on `real_moses_death_001`:

| arm | `real_moses_death_001` | answer |
|---|---|---|
| `off_20260927d` (**unpinned**) | STABLE-PASS 3/3 | 244 ch, 1 SID, names the gap and cites Aaron's death |
| `on_20260927d` (**unpinned**) | STABLE-FAIL 0/3 | the 242-char template |
| `nf1` (OFF, **pinned**) | STABLE-FAIL 0/3 | **the same 242-char template** |
| `nf2` (OFF, **pinned**) | STABLE-FAIL 0/3 | **the same 242-char template** |

With the flag **off**, on a pinned provider, this question emits byte-for-byte the output that was
attributed to the flag. **The flip is not attributable to `GILL_STRUCTURED_ANSWER`.** Whether the
cause is the provider or sampling variance is unresolved, and I am not going to pick one — that
would be a causal story dressed as a finding.

**2. Both of ruling 1's arms were unpinned.** `off_20260927d` and `on_20260927d` both record
`openrouter_provider_pin: None`, in the summary and per response. `deepseek/deepseek-chat` has two
OpenRouter providers at different quantizations (StreamLake, and DeepInfra at **fp4**), and each of
those 336 requests could route independently. Ruling 1 compared an unpinned arm to an unpinned arm.
**A pinned OFF vs pinned ON comparison has never been run**, and cannot be until `GillAnswerLM` in
`baml_src/gill_answer.baml` is pinned too — it is a separate BAML client and is still unpinned.

**3. Three of the four "genuine over-refusal regressions" do not survive re-measurement on a pinned
OFF arm.** The prediction asserted *"That evidence is unaffected by this run either way."* **That
claim of mine is falsified.** Re-read against both pinned OFF arms:

| question | pinned OFF behavior | verdict |
|---|---|---|
| `real_christophanies_001` | answers substantively on both arms (592 ch / 3 SIDs, 635 ch / 2 SIDs) while ON gives the template | **survives** |
| `real_moses_death_001` | **emits the 242-char ON template on both OFF arms** | does not survive |
| `real_imprecatory_psalms_001` | answers on nf1 (769 ch, 3 SIDs), **emits the template on nf2** | inside the OFF-vs-OFF floor |
| `real_universal_atonement_001` | refuses on both arms with 0 SIDs, in its own words (117 ch, 237 ch) | a **wording** difference, not a behavior one |

So the over-refusal evidence goes from **four** questions to **one**, and the refusal-incorrect floor
measured on this pair is **one question**. The surviving case sits *at* the floor, not above it.

Ruling 1's conclusion (flag stays OFF) is not thereby reversed — nothing here shows ON is better —
but the evidence that was said to carry it no longer clears the instrument. The decision currently
rests on a mechanism reading of a single question.

A fourth thing, incidental but of a kind already on the register: on `real_universal_atonement_001`
both pinned OFF arms refuse in plain English with 0 SIDs and lexical `is_refusal = False`. That is
the `real_gill_aquinas_001` gate artifact appearing **twice more** — the two-string detector scoring
a refusal as an answer. Item (b)'s instrument fix is now needed for three known questions, not one.

## Correction to item (d) before it is recorded as a standing defect

Chris ordered: *"Record the zone3 result as the standing production defect: slant sentences captured
57/84 ON, 0/84 OFF, so they currently reach users."* The two numbers are right, and
`ADR0009_FLAG_RESULT` states honestly that OFF's zero is a structural absence — the field does not
exist there. **The clause that does not survive measurement is "so they currently reach users."**

ADR-0008's lexical excision sweep (`_suppress_zone3`, `backend/bot.py:450`) fires on the OFF arms:

| log | arm | assertive-slant actions | trailing-prose excisions |
|---|---|---|---|
| `server_nf1.log` | OFF pinned | **5** | 10 |
| `serve_nf2.log` | OFF pinned | **2** | 7 |
| `server_off_d.log` | OFF unpinned | 4 | 8 |
| `server_on_d.log` | ON unpinned | 5 | 0 |

So OFF is not a path where that material has *nowhere to go but the rendered answer*: some of it is
excised or template-replaced before rendering. And the two counts are **not one population measured
two ways** — 57 is "material the model placed in a structured slot", 2–5 is "material a lexical scan
recognized in prose". They cannot be subtracted, so `57 − 0` is not a quantity of slant reaching
users.

What the pair *does* establish: the lexical scan recognizes far less than the structured slot
absorbs, which is ADR-0008's under-detection thesis and is **consistent** with slant reaching users
on OFF. What it does not establish is that it does, or how often. That needs reading OFF answers for
slant the sweep did not catch — a new measurement, not a re-reading of this one.

Item (d) is recorded as ordered, with this correction attached, rather than entering the inference
into the defect register as measured fact.

## Item (e): Garden is not a standing 0/3

`real_garden_genesis_3_24_misattribution_001` is **FLAKY 2/3 on nf1 and STABLE-FAIL 0/3 on nf2**,
identical settings. P14 falsified. It remains worth its own item — 2 of 6 across the pair is bad —
but it is a flaky question, not a deterministic retrieval failure, and a fix cannot be gated on
0/3 → 3/3 at N=3.

## A probe defect caught by its own companion assertion

P12 as worded is **not checkable from the arm directories at all**. `zone3_notes` lives in the
server's `structured_meta`; `backend/bot.py:1059-1063` prints it as DEBUG and explicitly does **not**
render it, so it never enters the HTTP response. My first probe looked for it in the response keys
and returned a clean **0 of 56** — from a probe that could not have seen the field anywhere. The
companion assertion is what caught it: the same probe found **0** occurrences on the ON arm, where
the behavior is known to exist. Re-scored against the server logs, with the assertion now passing
(313 occurrences on the ON log), P12 holds at 0 / 0.

This is the third time in two days that a clean-looking zero came from a probe comparing the wrong
strings or looking in the wrong place: the bracketed-SID re-score, this, and `partial_match_sids`.
The companion assertion is the only reason two of the three were caught.

## What this does NOT solve

- **It does not decide the flag.** It removes most of the evidence that was cited for the decision,
  which is not the same as evidence for the other side. A pinned OFF vs pinned ON pair is the run
  that would decide it, and it requires pinning `GillAnswerLM` first — which belongs with item (b).
- **It does not explain the flake rate.** Knowing the floor is not knowing its cause. Six samples per
  question across the pair is still far too few to estimate p per question, and a class-change floor
  of 11 is consistent with p near 0.5 on a third of the set.
- **It does not separate provider variance from sampling variance**, on `real_moses_death_001` or
  anywhere else. Both arms used one provider, so the pair measures within-provider variance only;
  the `off_d` → pinned difference confounds the two and this run cannot decompose it.
- **It does not measure StreamLake's own build stability** between the two arms.
- **It does not clear ruling 4.** The pair is provisional on the letter of the clean-tree rule.
- **It does not measure how much slant reaches users on OFF**, only that the guard fires and that the
  two zone-3 numbers are not commensurable.
- **It does not re-run the set at a higher N**, which is the only way to shrink this floor rather
  than merely know it. At N=3 the floor is a property of the instrument, not of the code under test.
- **It does not add `git_head` / `git_dirty` to the harness summary.** That gap is why deviation 1
  had to be reconstructed from commit timestamps instead of read off the run. It is the next change
  to `run_eval.py`, now that the pair is finished and nothing else is mid-run.
