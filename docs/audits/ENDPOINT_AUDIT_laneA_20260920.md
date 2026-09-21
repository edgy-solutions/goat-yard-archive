# Endpoint audit — every reference to 192.168.1.179 (E) and 192.168.1.188 (F)

Lane A, 2026-09-20. Prompted by Lane B finding shared-substrate scripts defaulting to endpoint E.
Authority: `C:\Users\cnogr\git\gpu-servers.md` — **E = 192.168.1.179:11434 and F = 192.168.1.188:11434
are CLOSED.** "No other project, agent, test, or ad hoc script may send requests to .179 or .188."

Scope: `goat-yard-archive` working tree, excluding `.git`, `node_modules`, `.venv`,
`__pycache__`, `baml_client` (generated). **19 hits.**

## Verdict first

| class | hits | action |
|---|---|---|
| A. Production / goatyardtest LiteLLM + cluster config — **carved out, leave alone** | 3 | none |
| B. **Script defaults and hardcodes — the defect** | 15 | remove default, require explicit, hard-refuse E/F, born-test |
| C. Inert (commented out) | 1 | delete the line |

**The in-flight ADR-0009 eval does not touch E or F.** Verified by tracing the backend's BAML
calls, not by assumption: `backend/` invokes exactly three BAML functions —
`b.OptimizeSearchQuery` and `b.RepairQuote` (both bound to `LocalRouter`, whose `base_url` is
`env.LITELLM_PROXY_URL`, set explicitly to endpoint D for this run) and `baml.GenerateGillAnswer`
(bound to `GillAnswerLM` → OpenRouter). The clients that hardcode `.188` — `Ollama`, `OllamaGPT` —
are bound only to `ValidateOCRMetadata`, `ValidateMetadataCore`, `ValidateMetadataVerses` and
`NormalizeGillMarkdown`, none of which the backend calls. The before-arm was therefore allowed to
finish rather than being discarded; the after-arm is held until class B is fixed.

---

## Class A — carved out (production / goatyardtest LiteLLM config)

| file:line | content |
|---|---|
| `charts/goat-yard-archive/values.yaml:160-161` | both E and F listed as LiteLLM proxy backends |
| `charts/weaviate-overrides/values-ollama-gpu.yaml:17` | `OLLAMA_API_ENDPOINT: "http://192.168.1.188:11434"` |

These are the deployment's own declaration of what the cluster's LiteLLM/Weaviate talk to. They
are the sanctioned path. **Not touched.**

One flag, not a change: `charts/weaviate-overrides/values-ollama-gpu.yaml` points Weaviate's
vectoriser straight at F rather than through the LiteLLM proxy, so it is a *direct* cluster→F
dependency rather than a proxied one. That is a question about the deployment's topology for
whoever owns it; it is not an ad hoc script and I have not altered it.

## Class B — the defect: 15 places that can reach a closed endpoint without anyone asking

### B1. `OLLAMA_HOST` defaulting to E — six shared-substrate scripts (Lane A's own directory)

| file:line | shape |
|---|---|
| `pipeline/reextract/build_truthset.py:42` | `ap.add_argument("--host", default=os.getenv("OLLAMA_HOST", "192.168.1.179"))` |
| `pipeline/reextract/extract_apparatus.py:180` | same |
| `pipeline/reextract/two_model_corpus.py:21` | same |
| `pipeline/reextract/nikud_audit_run.py:17` | `HOST = os.getenv("OLLAMA_HOST", "192.168.1.179")` |
| `pipeline/reextract/run_vol1.py:23` | same |
| `pipeline/reextract/vol7_run.py:19` | `host = os.getenv("OLLAMA_HOST", "192.168.1.179")` |

This is the worst shape in the list, and worth naming precisely: **the default is invisible at the
call site.** Anyone running `python run_vol1.py` with no arguments, on a clean shell, sends
traffic to a closed production endpoint and sees nothing to suggest otherwise. The failure is
silent, and it is the *convenient* path — which is why it survived.

### B2. Hardcoded F in BAML clients

| file:line | shape |
|---|---|
| `baml_src/main.baml:35` | `client Ollama`, `base_url "http://192.168.1.188:11434/v1"` |
| `baml_src/main.baml:51` | `client OllamaGPT`, same |
| `baml_src/main.baml:37` | commented alternative pointing at E |

**Lane B consumes `baml_src/`.** Changing these client definitions changes generated
`baml_client` for both lanes, so this one is coordinated, not unilateral.

### B3. Hardcoded endpoints in probes and tests

| file:line | shape |
|---|---|
| `evals/e6_entity_lookup_probe/e6b_post_fix_validation.py:24` | `OLLAMA_URL = "http://192.168.1.179:11434/api/embeddings"` |
| `evals/e6_entity_lookup_probe/e6_near_vector_probe.py:30` | same |
| `evals/e7_query_expansion_probe/e7_1_expansion_coverage.py:43` | same |
| `pipeline/scripts/normalize_markdown.py:151` | `api_base = "http://192.168.1.188:11434"` |
| `pipeline/scripts/normalize_markdown.py:1143` | same, as an `argparse` help string advertising it as the default |
| `test/test_litellm_proxy.py:9` | `api_base = "http://192.168.1.179:11434"` |

`normalize_markdown.py:1143` deserves its own mention: the help text *documents* a closed endpoint
as the default, so the CLI actively teaches the wrong thing.

## Class C — inert

| file:line | shape |
|---|---|
| `.env:41` | `#OLLAMA_URL=http://192.168.1.188:11434/api/embeddings` — commented out |

Harmless today; deleted so a future uncomment cannot resurrect it.

---

## The fix

A single guard rather than fifteen edits, because fifteen independent fixes decay independently
and the sixteenth script will not have one:

`pipeline/common/endpoint_guard.py` — `resolve_ollama_endpoint(explicit=None)`:

1. takes the endpoint from an explicit argument, else `OLLAMA_HOST`/`OLLAMA_BASE_URL`;
2. **no default** — absent endpoint raises, naming the env var and the allowed endpoints;
3. **hard-refuses** any host resolving to `192.168.1.179` or `192.168.1.188`, raising with the
   `gpu-servers.md` citation, regardless of how it was supplied — explicit argument included, so
   the refusal cannot be argued past on the command line.

Point 3 is the load-bearing one. Requiring an explicit endpoint only fixes the *accident*; the
hard refusal is what makes the closed endpoints unreachable from this repo whether or not someone
meant it. A guard that only fires on the default would still let `--host 192.168.1.179` through.

Born-tests cover: absent → raises; E → refuses; F → refuses; E/F passed explicitly → still
refuses; `http://192.168.1.179:11434/v1` in URL form → refuses (the check is on the resolved host,
not on string equality with a bare IP); D → passes.
