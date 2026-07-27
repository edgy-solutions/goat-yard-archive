# E-12 — ADR-0009 structured-output compliance smoke

**Date:** 2026-07-26 · **Type:** read-only capability probe (no serving-path changes) ·
**Models:** `deepseek/deepseek-chat` (current prod), `deepseek/deepseek-v3.2`, `deepseek/deepseek-v4-pro` (latest) ·
**N:** 8 per shape per model (120 calls) · **Script:** [`run_smoke.py`](run_smoke.py) · **Raw:** [`results.json`](results.json)

Answers the go/no-go for the ADR-0009 typed-schema migration *before* the phase starts,
and checks whether the migration should carry a model bump (nearly free to test now).
Draft schema: typed `refusal` (`mode` + `gap_statement`), `zone1_bridge`, and `segments`
(`framing` + verbatim `gill_quote` + `sid`). Deliberately **no** field for characterizing
Gill's position (Zone 3) — Q4 watches whether the impulse leaks when the schema starves it.

## Verdict: **GO** on the migration — with two design inputs that must land in the schema, not after it.

The riskiest question (can DeepSeek hold the nested schema) is a clean pass. The two
"failures" are not blockers; they are the schema's design brief.

## Results

| shape | field-ok (chat / v3.2 / v4-pro) | schema-valid | verbatim | zone-3 leak |
|---|---|---|---|---|
| A multi-phrase answer | 8 / 8 / 8 | 8/8 all | 5 / **8** / 7 | **8 / 8 / 5** |
| B informative refusal | **0 / 0 / 0** | 8/8 all | n/a | 0 |
| C flat refusal | 8 / 8 / 8 | 8/8 all | n/a | 0 |
| D zone1-bridge | 0 / 0 / **1** | 8/8 all | 2/2 3/3 | 0 |
| E Hebrew-in-quote | 6 / 7 / 6 | 8/8 all | 8/8 7/7 7/7 | 0 |

## Q1 — schema compliance: **STRONG GO**
**120/120 parseable and schema-valid**, all three DeepSeek models, served via **enforced
`json_schema`**. The nested three-zone schema (nullable object, enum, array of objects) is
held perfectly. This was the phase's go/no-go and it clears with no margin concern. Raw
compliance is the conservative floor — BAML's retry/repair only raises it.
- Caveat: `deepseek-chat`'s `json_schema` support **routes inconsistently** on OpenRouter
  (one probe call 400'd "not supported," others served it). The migration should treat
  `json_object` + parse/repair (the BAML path) as the contract and not depend on enforced
  structured output for the current model.

## Q2 — verbatim fidelity inside `gill_quote`: **positive, model-dependent**
Quoting into a dedicated field yields high verbatim rates — **v3.2 8/8, v4-pro 7/8, chat 5/8**
on the multi-phrase body; Hebrew (`הַלֵּל טָעוּן`) preserved char-for-char 7–8/8 across all;
bridge segments 2–3/3. Supports the measurement-integrity hypothesis (field-quoting is more
verbatim than free prose) **and** a model bump — the newer models are cleaner, `chat` is the
weak point at 5/8.

## Q3 — fluency of reassembled output: **GO, no disqualifier**
A trivial assembler (framing + `"quote" [SID]`, joined) reads as natural Gill exposition, not
robotic quote-cards — see the covenant answer and v4-pro's psalmody answer in
[`rendered_samples.md`](rendered_samples.md). Full A/B against current prose is phase work; the
smoke's job was to catch a disqualifying result, and there isn't one.

## Q4 — Zone-3 leak: **the key design finding — the schema does NOT starve Zone 3**
On substantive answers the free-text `framing` field **absorbs** the characterization impulse
the schema gave no home: *"Gill distinguishes the covenant of grace from other covenants…"* —
**chat 8/8, v3.2 8/8, v4-pro 5/8** (see [`zone3_leaks.md`](zone3_leaks.md)). A typed schema
alone is insufficient for Zone-3 discipline. ADR-0009 must do one of: constrain `framing` to a
non-assertive shape, keep the post-assembly Zone-3 sweep, or ship the release-valve. This
**validates the release-valve forcing line** rather than retiring it. v4-pro leaks least but is
not clean.

## Cross-cutting behavioral finding (B + D): the slots don't carry the behavior — the field descriptions do
Under the deliberately-minimal schema prompt, all models **collapse informative→flat**: they
emit a good `gap_statement` but set `mode="flat"` and surface no adjacent material (B: 0/24).
For aquinas they even assert "the corpus does not contain Gill's commentary on Aquinas" — now
known false. Same for the bridge (D): only **v4-pro, 1/8**, produced the full
`zone1_bridge` + Hallel segment; everyone else bare-refused. The informative-refusal /
partial-match / bridge behavior lives in the **prompt and field descriptions**, not in the
existence of a typed slot. This scopes the "pre-draft the schema field descriptions during the
ingestion weeks" work as **load-bearing**: the schema must ship with strong descriptions and
likely few-shot, not bare fields.

## Model bump (current vs latest): **safe, mild-positive → recommend carrying v4-pro into the migration**
Per the pre-committed rule (newer wins only if ≥ current on compliance + fidelity, at worst
mildly different on fluency): all three hold the schema equally; v3.2/v4-pro beat chat on
verbatim fidelity; v4-pro leaks Zone-3 least and is the only model to produce the full bridge
unprompted. v4-pro (or v3.2) qualifies. Fold the bump into the same revalidation pass the
migration already requires — one migration, one recalibration.

## What this does NOT establish
- Post-BAML-repair compliance (only raw floor measured — repair can only raise it).
- Full John 6:37 fluency A/B (phase work; no disqualifier found here).
- Behavior under the *real* field descriptions (probe used minimal slots by design — that is
  itself the finding: descriptions carry the behavior).
- Manifest/retrieval health was not the variable here (chunks were pinned inputs).
