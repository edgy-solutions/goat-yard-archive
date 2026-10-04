# PREDICTION — OFF vs ON rerun pair, Lane A, 2026-10-04 (locked before launch)

Supersedes nothing: `PREDICTION_off_vs_on_expansion_live_laneA_20261004.md` stays as the record of
the arm that was voided. This is a fresh pair, both arms unrun at the time of writing.

**HEAD at lock: `c01ee3b`, tree clean.** Nothing will be committed in either repo from the moment
the first arm starts until the pair finishes. The first arm was voided because four documentation
commits of mine landed while it was scoring; that is the only fault the rerun has to fix.

## What is being measured

`GILL_STRUCTURED_ANSWER` 0 vs 1 (ADR-0009 typed `GillAnswer` via BAML), 13 question ids x 5 runs =
65 scored runs per arm, against a local uvicorn serving `goatyard-laneA` at `127.0.0.1:8000`,
retrieval from gya-test (`192.168.1.54`), answers from `deepseek/deepseek-chat` pinned to
`streamlake` with `allow_fallbacks: false`, temperature 0.0, LM cache disabled.

**Cross-process on purpose.** The server is killed and relaunched between arms. A same-process pair
is structurally blind to a per-process defect, which this lane has already been bitten by once.

**Endpoint note.** Query expansion routes through `LITELLM_PROXY_URL` = endpoint D
(`192.168.1.169:11435`), which Lane A2 now has priority on. Expansion is one small call per
question (~130 calls across the pair) and endpoint D was idle at launch (`/api/ps` reported no
loaded models). If A2 needs D exclusively, this pair yields to it and the arms are abandoned, not
spliced.

## Predictions

**P1 — validity before any score.** Expansion live on every scored run in both arms:
`stage_health.expansion` = `{"errored": 0, "healthy": 65, "distinct_fallback": ["<none>"]}`, and
`entity_lookup.distinct_mode == ["full"]`. If P1 fails, no score in that arm means anything and the
arm is reported as void regardless of what it scored. This is the arm's validity verdict and it is
reported first.

**P2 — the git axis is clean this time.** `integrity.git.changed_during_run is False`, dirty false
at both ends, in BOTH arms. This is the fault that voided the first arm and the one thing the rerun
exists to fix.

**P3 — the corpus axis comes back PROVISIONAL, not clean, and that is the new instrument working.**
`changed_during_run` is `None` with `violations == []` and `read_fault_uuids` naming 1-6 objects per
arm. Reasoning: the measured client-side corruption hits roughly 7 of 7294 vectors per full sample,
of which the two that preserve vector length survive the new dim re-fetch, and each arm takes two
samples. So I expect at least one undetectable-at-the-structural-level bad read per arm, named by
uuid, with `last_update_ms` identical on both sides — which is the exact signature that was
misread as a re-embedding this morning.
- `added`, `removed` and `rewritten` all empty in both arms.
- `dim_anomalies` empty in the accepted samples (the re-fetch resolves them) while
  `read_faults` records `dim_anomaly_retry` entries — i.e. the net fires and is counted.
- If `rewritten` is non-empty, something really did write to gya-test and the arm is void; the
  uuids are now named, so unlike this morning that claim will be checkable.

**P4 — and that makes the pair uncitable under the current severity rule, which is a DECISION, not
a result.** `provisional: True` follows from `changed_during_run is None`, and a provisional arm
cannot be cited. If the transport corrupts ~2 undetectable vectors per sample, every arm this lane
ever runs is provisional, forever, on a metadata probe that does not touch a single scored answer.
I am not quietly relaxing that rule to make my own numbers citable. The timestamp evidence does
establish something real — no object was added, removed or rewritten — and whether that is enough
to cite an arm is Chris's call. **The verdict is re-derivable after the fact** from
`corpus_objects_at_{start,end}.json`, which is why running now is not wasted either way.

**P5 — the scored-run preflight refuses nothing.** Both arms launch with
`conditions_enforced` = expansion_healthy / pin_honored / header_written all satisfied,
`overrides_in_force == []`, and `run_header.json` written before the first question. An exit 3 from
either arm means the gate caught a real fault and the arm did not score; that is a pass for the
gate, not a failure of the run.

**P6 — provider pin.** `openrouter_provider_pin` = `{"order": ["streamlake"],
"allow_fallbacks": false}` and `answer_lm.distinct` carries exactly one entry per arm, with
`model_returned` `deepseek/deepseek-chat` and `temperature_on_the_wire` 0.0 on all 65 runs.

**P7 — the scores themselves: no prediction of direction.** The first OFF arm scored 11/13 with 9
stable-pass, 4 flaky, 0 stable-fail, and those numbers are void. I predict the rerun OFF arm lands
within 9-13 of 13 on the same question set, and I predict NOTHING about whether
`GILL_STRUCTURED_ANSWER=1` moves the score in either direction. A measured delta on 13 questions
with 4 known-flaky is inside the noise this lane has already measured (14 of 78 moved between two
IDENTICAL arms), so unless the pair moves more than that, the honest reading is "no effect
detected", not "no effect".

**P8 — flakiness is the dominant term and will be reported as such.** At least 3 of the 13
questions come out flaky in at least one arm. Any per-question flip between arms is reported as
flakiness until a null replicate says otherwise; a pooled OFF-vs-ON delta is not evidence about a
question that flips on its own.

## What this pair cannot settle

- **The transport corruption.** Unfixed, root cause unidentified. The pair measures around it.
- **Whether the typed answer path is better.** 13 questions, 5 runs, one model, one corpus. This
  pair can detect a large effect and cannot detect a small one, and it says nothing about prod.
- **Prod behaviour.** Neither arm runs the deployed image; `0.3.1` is still unpushed.
- **The `baml_punt:<reason>` cause split**, deliberately deferred: `backend/stage_health.py` must
  stay byte-identical across the pair, so the instrument is not changed mid-measurement.
