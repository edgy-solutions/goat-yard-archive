# Prediction — OFF vs ON, with query expansion LIVE and the answer provider PINNED

**Locked 2026-10-04, before the first scored request.** Answers the standing instruction: *"Pin the
answer-LM provider on OpenRouter and record it per call; it's the remaining churn source. Then OFF
vs ON at t=0, N=5, flip gate, predict first."*

**Correction, same day, before any run.** The first commit of this document said the run was
blocked on a local Weaviate and a port conflict. That was wrong, and wrong in an avoidable way: I
probed `localhost:8080` and reasoned from a dead local service, without checking what the previous
arms actually addressed. They used the **gya-test Weaviate at `192.168.1.54:80`**, recorded in the
handoff for the floor pair itself. It is up, and it holds the same corpus. **Nothing is blocked.**
The port conflict on `localhost:8080` is real and irrelevant — no arm here uses it. No number had
been seen when this correction was made; the predictions below are unchanged from the locked commit,
and the configuration table gained the rows it should have had from the start.

This pair is the first measurement in this lane taken with the query-expansion stage alive. Every
previous arm is void (`VOID_arms_without_expansion_laneA_20261004.md`), so **this pair re-measures
the floor as well as the flag.**

## Why the level is deliberately NOT predicted

There is no usable prior. 55/78, 63/78, the 8-of-78 floor and the 14-of-78 null were all measured
with expansion dead and a `dedup_only` fallback standing in for it, and they are retired. Inventing
a band from a retired number is the move the void ruling exists to stop.

So the locked predictions below are about **structure, health, recording and the decision gate** —
things whose correct values follow from the code and the configuration. The pooled **level** is
unpredicted, named as unpredicted, and will be reported as a new measurement, scored against
nothing.

With expansion live, three things happen in this lane for the first time: `search_text` exists, so
the **second-pass entity lookup executes** (`backend/main.py:585`); the BAML entity path and its
boost telemetry activate; and the embedding input can differ from the raw query. Any of those can
move retrieval. The direction is unknown and I am not guessing at it.

## Configuration, identical in both arms except the flag

| setting | value |
| --- | --- |
| `LITELLM_PROXY_URL` | `http://localhost:4000` — **set on the server process at launch**, `.env` untouched |
| `OPENROUTER_PROVIDER_ORDER` | `streamlake` (`allow_fallbacks: False`, via `degradation.provider_pin`) |
| `GILL_ANSWER_TEMPERATURE` | `0.0` |
| `GILL_DISABLE_LM_CACHE` | `1` |
| `RATE_LIMIT` | `100000/day` |
| `GILL_STRUCTURED_ANSWER` | **OFF** in arm 1, **ON** in arm 2 — the only difference |
| `--runs` | 5 (so 65 scored runs per arm over 13 questions) |
| `--timeout` | 200 |
| `WEAVIATE_URL` | `192.168.1.54:80` — the **gya-test** instance, the same one the floor pair used |
| corpus | verified 2026-10-04: Weaviate **1.38.1**, `CommentaryChunk` **7294**, `TheologicalEntity` **8433** — identical to the counts the handoff recorded for the floor pair, so the corpus is not a variable between that pair and this one |
| LiteLLM proxy | `localhost:4000`, model list `local-router` + `qwen3-embedding` (gya-test). Embedding traffic goes through the proxy own model_list, which is the pre-existing sanctioned path; nothing here addresses a GPU host directly |
| HEAD | clean and committed before the first request; `integrity.git.git_dirty` must read clean in both |

Question set, the same 13 stochastic ids as the void floor pair: `scapegoat_001`,
`real_imprecatory_psalms_001`, `sheep_001`, `real_covenant_grace_001`,
`real_covenant_monocovenantal_001`, `real_garden_genesis_3_24_misattribution_001`,
`day_of_atonement_001`, `real_singing_psalms_001`, `simons_count_001`, `john_baptist_001`,
`real_christophanies_001`, `real_election_001`, `real_ishmael_circumcision_001`.

**Why StreamLake:** measured 2026-09-27 from OpenRouter endpoint metadata, recorded in
`backend/degradation.py` — StreamLake ctx 128000, quant unknown, status 0, uptime 99.5%; DeepInfra
ctx 163840, quant **fp4**, status -2, uptime 94.4%. A deranked fp4 endpoint is the one to exclude.
**That choice is not itself measured.** Nothing here compares providers; the pin only stops them
mixing, which is the fault found in the floor arms (DeepInfra 61 / StreamLake 17, `violations: []`).

The server is restarted between arms — the flag and the pin are read at process start — so this
pair is cross-process, as the floor pair was.

## Locked predictions, with the exact field each is read from

Eval-side paths are in the arm `summary.json`. The server-side path is the `/health/stages`
snapshot (release 0.3.2), read on the warmup and again after each arm.

| # | prediction | read from | falsifier |
| --- | --- | --- | --- |
| P1 | `errored == 0`, `healthy == 65`, `distinct_fallback == ["<none>"]` in **both** arms | `summary.integrity.stage_health.expansion` | any expansion error — **the pair is void, not failed**: relaunch, do not analyse |
| P2 | server-side `expansion.errored == 0` and `causes == {}` after each arm | `/health/stages` `expansion` | a non-empty `causes` — same void rule; this is the independent witness for P1 |
| P3 | `runs_pin_honored_false == 0` **and** `runs_pin_unchecked == 0` in both arms | `summary.answer_lm` | either non-zero. `runs_pin_unchecked` is the one the floor arms could not fail: unpinned, it was every run, and silent |
| P4 | `distinct_provider_served == ["StreamLake"]` — length exactly 1 — and **no** mixture violation | `summary.answer_lm` | a second served provider, or length 0 (nothing recorded) |
| P5 | `runs[].provider_served` non-null on all 130 runs | arm `runs[]` entries | any null → provider attribution is unavailable and the arm cannot be cited for provider claims, by the rule that voided the fourteen |
| P6 | `distinct == [0.0]`, `runs_explicit == 65`, `runs_absent == 0`, `runs_unrecorded == 0` in both arms | `summary.integrity.answer_temperature` | anything else |
| P7 | `violations == []` in both arms | `summary.integrity.violations` | any violation. First time an empty list asserts something: the expansion, temperature, pin and new mixture gates can all fire now |
| P8 | `entity_lookup.distinct_mode == ["full"]` in both arms | `summary.integrity.stage_health` | a non-`full` mode → the second-pass vector tier flaked. The pair stays readable; the manifest claim does not. Note `full` means "the tier did not raise", **not** "the manifest was stable" |
| P9 | **The decision gate: 0 STABLE-PASS ↔ STABLE-FAIL flips** in either direction | per-question verdicts across the two arms | 1+ flip. A flip either way means the flag moves a question that was stable, and the flag stays OFF |
| P10 | **pooled gap between the arms is 4 or fewer of 65** | pooled scores | a gap of 5+ |
| P11 | **total absolute per-question movement is 5–16 of 65**, and no single question moves more than 3 of 5 | per-question pass counts across the arms | movement under 5 (suspiciously still — look for a cache or a replay before believing it) or over 16 (the null widened; see below) |

**Where 65 appears above it means "every scored run".** `stage_health` and
`answer_temperature` count scored runs only, so an errored or degraded run lowers
`scored_runs` rather than creating a gap. The literal check is `healthy == scored_runs` and
`runs_explicit == scored_runs`; 65 is the value when nothing errors, which is itself expected
but not predicted — a transport error is not a measurement failure.

**P9, P10 and P11 are the only predictions about the flag.** P1–P8 are health and recording gates:
they say whether the pair is a measurement at all.

**Grounding for P10 and P11, and why it is borrowed.** The two same-config null pairs on this same
13-question set each had a **pooled gap of 0**, with **8 of 78** and **14 of 78** total absolute
per-question movement and no question moving more than 2 of 6
(`RESULT_off_vs_off_floor_laneA_20260928.md`). Those arms ran at N=6, so 78 scales to 65 as roughly
6.7 and 11.7 — hence the 5–16 band, widened at the top rather than centred, and a per-question cap
of 3 of 5 rather than 2.

**Those arms are void**, and the borrowing has to be named for what it is. What survives the void is
narrow: the churn *magnitude* is a property of answer-LM stochasticity, which the dead expansion
stage did not touch. What does not survive is the assumption that it is the same magnitude here,
because with expansion live a second stochastic input (`search_text`) now feeds retrieval. So
**movement may legitimately exceed 16 for reasons that have nothing to do with the flag.**

That is why pooled gap and movement are separate predictions. Pooled totals were the stable
statistic in both nulls (gap 0 twice) while per-question verdicts churned by 8 and 14; a single
number hiding both would be unfalsifiable. If P11 breaks while P10 holds, the honest reading is
**the null widened under live expansion**, not that the flag did something — and settling that needs
a same-config null pair at this configuration, which this pair does not include. Noting it here, in
advance, so that reading cannot be invented afterwards.

## The decision rule, stated before the numbers exist

- **Flag stays OFF** unless ON is at least as good as OFF on **every** question *and* P9 holds. A
  pooled improvement with one stable-question flip is a trade, not an improvement.
- **Any P1 or P2 failure voids the pair.** It does not get analysed with a caveat; it gets
  relaunched. That is the whole lesson of the fourteen void arms.
- **A pooled gap inside P10's band is "no effect measured", never "ON is better."**
- **A void or inconclusive pair does not promote the flag either way.** OFF stays the default by
  conservatism, exactly as it does today.

## What a result here can and cannot say

It can say: whether expansion is alive, whether the pin holds, what the pooled level is *with
expansion live*, and whether the typed-answer flag moves any question off a stable verdict.

It cannot say: that the flag is safe (one pair, 13 questions, one provider, one process each); that
the level is comparable to any published number (none of them is); that the provider choice was
right (unmeasured, deliberately); or that the second-pass entity manifest is stable — it is a
function of `(search_text, corpus)` and `search_text` is stochastic LM output, so variation there is
expected and is **not** a regression of `5c93b28`.

## Launch (blocked at lock time — see below)

```bash
# server, per arm; the flag and the pin are read at process start
LITELLM_PROXY_URL=http://localhost:4000 \
OPENROUTER_PROVIDER_ORDER=streamlake \
GILL_ANSWER_TEMPERATURE=0.0 GILL_DISABLE_LM_CACHE=1 RATE_LIMIT=100000/day \
GILL_STRUCTURED_ANSWER=0 \
  python -m uvicorn backend.main:app --port 8000

# preflight, BEFORE any scored question: expansion alive, recorder wired
python evals/acceptance_stage_health.py --base-url http://localhost:8000 --probe-search

# arm
python evals/run_eval.py --endpoint http://localhost:8000/api/search --runs 5 \
  --timeout 200 --output-dir evals/output/off_vs_on_20261004/off --ids <the 13 ids>
```

## Preconditions, verified 2026-10-04 before locking

| precondition | state |
| --- | --- |
| gya-test Weaviate `192.168.1.54:80` | **UP**, `/v1/meta` 200, version 1.38.1 |
| corpus counts | **7294 / 8433**, matching the floor pair exactly |
| LiteLLM proxy `localhost:4000` | **UP**, `/health/liveliness` 200, 2 models |
| Ollama `localhost:11434` | UP (not on this path; embedding goes through the proxy) |
| `localhost:8080` | held by an unrelated container and **not used by this run** |

The only thing left before the first request is launching the two servers with the environment in
the table above, and confirming on the warmup that `/health/stages` reports `expansion.errored == 0`
with empty `causes`. **If the warmup shows an expansion error, no scored question is sent** — that
is P1 and P2 acting as a preflight rather than a post-mortem, which is the one procedural change
this whole void episode earns.

If the configuration at launch differs from the table above in any row, **this document is void and
a new one is locked.** A prediction edited to match its run is not a prediction.

---

## P1 FAILED on the warmup. This pair is VOID. Written before the arm finished.

Timestamped by its commit, which lands while arm OFF is still running and before a single scored
result has been read. That ordering is the only thing that makes the rest of this section worth
anything.

**What happened.** The preflight probe passed clean (`expansion {ok: 1, errored: 0, causes: {}}`).
The very next request — the arm warmup — errored:

```
BAML output structurally punted: ['entities_given_none_returned']
fallback = poisoned_manifest_suppressed
```

and `/health/stages` counted it correctly: `expansion {ok: 1, errored: 1, causes: {"other": 1},
fallbacks: {"poisoned_manifest_suppressed": 1}}`.

**P1 as locked says `errored == 0` and `distinct_fallback == ["<none>"]`, and names the consequence:
the pair is void, not failed.** It is void. I am not going to reread my own rule into something
looser now that it has cost me something, because a prediction edited to match its run is not a
prediction, and this document says so three paragraphs above.

**What this failure is NOT.** It is not the fault that voided the fourteen. That was
`missing_env_var:LITELLM_PROXY_URL` on every request — the stage was dead and nothing noticed. Here
the stage is **alive**: the proxy answers, one request expanded fine, and the failing one was caught
by a suppression gate doing exactly its job (`poisoned_manifest_suppressed`) and reported by a
recorder shipped for this purpose. Dead-stage and bad-output are different faults, and P1 as written
cannot tell them apart. **That is a defect in P1, not a reason to excuse the result.**

**The honest consequence: P1 is the wrong rule, and I do not yet know the right one.** A
one-in-N structural punt with a working suppression gate may be normal operation. If it is, then
`errored == 0` makes an OFF-vs-ON comparison impossible by construction, and I would be refusing to
measure a system that works. If it is not normal, the rate will say so. Either way the threshold has
to come from the measured punt rate, by the rule in [[thresholds-from-empty-bands]] — derive it from
a gap in the data, never from how much I want the run to survive.

**So arm OFF is being allowed to finish, reclassified in advance:**

- **Void for the flag.** P9, P10 and P11 are abandoned for this pair. No pooled number from this arm
  may be compared with any other arm, cited in an ADR, or used to move the flag.
- **Kept as the punt-rate diagnostic.** It will report how many of 65 scored runs punt, with which
  causes and fallbacks, whether the recorder catches every one, and whether the pin held throughout
  (`pin_honored` already reads True with `served_by=StreamLake`, so P3/P4 are working).
- **Arm ON is NOT launched.** Spending a second arm's LM budget on a comparison already declared
  void would be waste. The pair resumes from a new locked document once the punt rate is known.

This is a reclassification of a running arm, and the reason it is not a rescue is that it **gives up
the comparison**, which is the thing I wanted, and keeps only the diagnostic, which is the thing the
failure made available. The spend is mine to account for: one arm of LM calls bought a punt rate
instead of a floor.

**What this does NOT solve.** It does not say whether the punt is frequent, random, or
question-specific; whether `causes: {"other"}` is hiding several distinct faults behind one
allowlist bucket (it is a single bucket by design, and that may now be too coarse); or whether the
suppressed manifest changes the answer the user gets. Those are results, and no result has been read
yet.

---

## Retraction: "P1 FAILED" was wrong. P1 is undetermined, and a rule I wrote does not exist.

The section above declares the pair void because P1 failed. **P1 did not fail. It has not been
evaluated yet.** The retraction is held to the same bar as the claim, because a retraction is a
causal claim too.

**What P1 actually measures.** `summary.integrity.stage_health.expansion` is computed at
`evals/run_eval.py:932` over `scored` runs only — `[r for runs in run_ledger.values() for r in runs
if not r.error and not r.degraded]`. **The warmup is not in `run_ledger`.** It is returned
separately as `warmup_info` and never enters the tally. So the punt that I called a P1 failure is
not in P1's domain at all, and P1's value will not be known until the arm finishes.

The first question's scored runs, already on disk, expanded clean: `scapegoat_001` ×5 with
`expansion_error: False`, `expansion_fallback: None`, `entity_lookup_mode: full`,
`provider_served: StreamLake`, `pin_honored: True`. One question is not an arm, and I am not
reading P1 off it.

**What did fail is a rule I wrote that is enforced nowhere.** This document says "If the warmup
shows an expansion error, no scored question is sent." The harness does not do that. It has the
mechanism — `_warmup` returns `(warmup_info, exit_code)` and the docstring says "A nonzero exit_code
means: do not score anything" — and for a BAML punt it deliberately prints a WARNING and returns
zero, which is why the arm proceeded. I asserted a preflight behaviour, did not check whether it
existed, and then read its absence as a measurement failure. **Recording a rule is not enforcing
it** ([[recording-a-flag-is-not-acting-on-it]]).

**So the void declaration is withdrawn as premature**, and the withdrawal rests on the field
definition at `run_eval.py:932`, which is objective and checkable — not on the early runs looking
clean. If P1 fails on the finished tally, the pair is void and the reclassification above applies
exactly as written. If P1 holds, the arm is a valid OFF measurement whose warmup punted, and the
punt belongs in the result as a named hazard.

**Still true from that section, and not withdrawn:**

- The warmup punt is real, and `/health/stages` counted it correctly (`errored: 1`, `causes:
  {"other": 1}`, `fallbacks: {"poisoned_manifest_suppressed": 1}`). The recorder works.
- `entities_given_none_returned` is a documented stochastic punt, not a stage fault: the ADR-0013
  Part D comment at `backend/main.py:673` calls it "a gemma coin-flip, not reliable evidence about
  manifest quality."
- On the punt path `search_text = req.query`, so a punted run feeds the **raw query** to the
  second-pass lookup. The punt rate is therefore the fraction of an arm effectively running without
  expansion, which is why it has to be measured rather than assumed either way.
- **Arm ON is still not launched.** The reason is now different and weaker: not "the pair is void"
  but "P1 is unevaluated." Spending the second arm before the first arm's health is known is the
  same mistake in a smaller size.

**Three defects to fix in the next round, none of them mid-flight:**

1. **Decide whether a warmup expansion punt is a gate, then make the code say so.** Either `_warmup`
   returns nonzero for it, or this document stops claiming it does. A rule that lives only in prose
   is decoration.
2. **Split the `other` cause bucket.** A documented coin-flip punt and an unrecognised real fault
   both land in `other`, so the counter cannot distinguish them. `baml_punt:<reason>` is the fix.
   Deferred because `backend/stage_health.py` is byte-identical in `release-0.3.2` and the
   instrument must not change mid-arm.
3. **P1 needs to name its population.** "`errored == 0`" without "over scored runs, warmup excluded"
   is what let me misread my own prediction within an hour of locking it.

---

## Outcome: P1 HELD. The arm is VOID anyway, on two counts P1 cannot see. 2026-10-04

**P1, first, because it is the arm's validity verdict** — `off/summary.json`,
`integrity.stage_health`:

```
scored_runs 65
expansion   {"errored": 0, "healthy": 65, "distinct_fallback": ["<none>"]}
```

65 of 65 scored runs ran query expansion live, no fallback on any of them. This is the first arm
in this lane with verified-live expansion on every scored run — the condition whose absence voided
fourteen arms and 266 questions
(`docs/audits/VOID_arms_without_expansion_laneA_20261004.md`). The population is the one the
retraction above named: scored runs, warmup excluded.

**And the arm is still void, on two faults neither P1 nor the new gate is able to see.**

1. **CORPUS CHANGED MID-RUN** (`integrity.violations`). Vector sha `a1e37d2f12c7 → 0b903608df60`,
   with `chunks` 7294 and text sha `6cbb33635352` identical at both ends, and 7294/7294 vectors
   hashed in both samples. Read before assuming an instrument artifact: `content_hash` is an
   XOR-fold of per-object digests (`backend/corpus_fingerprint.py:46-53`), so it is
   order-independent, and `_vec_digest` rounds to 6 decimals (lines 39-44), so it is float-tolerant.
   A text sha that holds while the vector sha moves is a **re-embedding** of the gya-test corpus
   between 10:23 and ~11:30. **The source is unattributed** and must be found before the arm is
   rerun. Only `--corpus-fingerprint vectors` (~80s/sample) can see this.
2. **HEAD moved mid-run** (`integrity.git`: `changed_during_run: true, provisional: true`),
   `25c6f78 → c89b69b`. Four documentation commits of mine, landed while the arm was scoring. The
   rule was already written down — "commit before anything else touches a JSONL", runs over a
   moving tree are provisional — and I broke it myself. `git_at_start` is captured at
   `run_eval.py:1181` and compared at `:1379`.

**The lesson, against my own framing.** The directive asked for P1's tally as the arm's validity
verdict, and P1 passed. One gate is not a verdict: an arm is valid only if every axis held, and
two did not. Reporting P1 alone would have been a true number in service of a false conclusion.
Related: a gate names a direction, and passing means "the failure I imagined didn't happen".

**Figures that exist but are NOT citable** (provisional on two axes): 11/13 pass, 9 stable-pass,
4 flaky, 0 stable-fail. Other predictions that held: P3 (`runs_pin_honored_false 0`,
`runs_pin_unchecked 0`), P4 (`distinct_provider_served ["StreamLake"]`), P5 (65/65 runs carry an
answer_lm record), P6 (temperature `distinct [0.0]`, `runs_explicit 65`), P8
(`entity_lookup.distinct_mode ["full"]`), verifier failures 0.

**Arm ON was never launched** and stays unlaunched. The OFF arm must be rerun from the top — never
spliced — after the re-embedding source is identified and with HEAD frozen for the whole run.

### Defect 1 is closed in code

`953b94a feat(evals): scored-run preflight is a launcher refusal, not a doc rule`. The ruling was
the first option, not the second: `preflight()` now returns 3 on a warmup expansion error instead
of printing a warning, so this exact arm would have been refused at launch. Two conditions joined
it — pin honored (`pin_honored is not True`, because unchecked is not honored) and header written
(`run_header.json`, before the first scored question, so a partial arm is not anonymous). Each
health condition has one named override and an override in force is recorded in the header and in
`summary.integrity.preflight`; waiving the launch refusal does not silence `check_run_integrity`,
which still exits 4. Born-tested: 23 of the 26 new tests fail against the parent commit, including
`test_main_scores_NOTHING_when_the_warmup_expansion_is_broken`.

Defects 2 and 3 remain open and deliberately deferred: the `baml_punt:<reason>` split waits on
`release-0.3.2` deploying, because `backend/stage_health.py` is byte-identical there and the
instrument must not change mid-arm; P1 naming its population belongs in the next locked document,
not in a patch to this one.

---

## Retraction 2: the corpus violation was a FALSE POSITIVE. 2026-10-04, later the same day

The section above says the vector-sha change was "a **re-embedding** of the gya-test corpus" and
defends that by saying I read the hashing code instead of assuming an instrument artifact. **That
is retracted.** Nothing wrote to gya-test. Full evidence in
`docs/audits/READFAULT_corpus_vector_sha_false_positive_20261004.md`; the three findings:

1. Max `_lastUpdateTimeUnix` over both collections is **2026-05-25T01:47:38Z**, 132 days before the
   run. Zero objects written on 2026-10-04. The cursor scan also returns unique ids equal to the
   aggregate count, so pagination neither skips nor duplicates; `pq`/`bq`/`sq` are all disabled and
   `vectorizer: none`, so there is no quantized cache and the server cannot re-embed on read.
2. Two fresh samples, identical id set and order, **7 of 7294 vector digests differ — with vector
   lengths of 4094, 4097 and 4099 for a 4096-dim embedding.** Those are malformed arrays, not
   different embeddings. (Two of the seven had the correct length and wrong contents, so a length
   check alone would not have caught them.)
3. A single-object GET is stable 10/10. The 1.1 MB page body returns two distinct raw-body SHAs in
   10 fetches at identical byte length, one of them failing to parse 207 bytes past 64 KiB, while
   `curl` returns the same bytes 50/50. A captured mutation is a verbatim copy of the same body
   from offset 55027 re-emitted at offset 585293, total length preserved.

**What I got wrong, precisely.** I verified that the fold is order-independent and float-tolerant.
Both are true, and neither is a statement about whether the bytes reaching the fold are the bytes
the server sent. I checked the arithmetic and never checked the input, then presented "text sha and
counts identical, 7294/7294 hashed both times" as discriminating evidence when it is equally
consistent with a handful of corrupted reads. This is the causal-story failure in its usual
shape — the detector fired correctly and my explanation of why was invented.

Worse: `fingerprint_rest.py`'s 5-attempt retry loop catches the corruption that breaks the JSON and
silently re-fetches, so only the **undetectable** form of it ever reached the fingerprint. The
visible half was being suppressed by a retry nobody counted.

**P1 is unaffected.** Expansion was healthy on 65/65 scored runs; that stands.

**The arm's status changes from void-on-two-axes to void-on-one.** The corpus axis is clean. HEAD
moving mid-run — my four doc commits — is the whole of what voids it. The rerun needs HEAD frozen
and nothing else; there is no re-embedding to find and no mystery writer.

**Defect 4, now queued and specified:** a fingerprint difference must be attributable to named
objects, not a fold. `classify_change` sorts a difference into added / removed / rewritten /
read_fault using the discriminator the database already owns — a stored object cannot change
without its `last_update_ms` changing. A read fault is provisional and names its uuids; a real
change stays a violation; an unknowable timestamp counts as a rewrite, because unknowable is not
benign. Spec in `scratchpad/SPEC_fingerprint_attribution.md`.
