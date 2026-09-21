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

---

# Applied, 2026-09-20 — what actually changed

`pipeline/common/endpoint_guard.py` (new) + `pipeline/common/test_endpoint_guard.py`, **18/18
passing**. Three entry points: `assert_endpoint_allowed` (guard a value already in hand),
`resolve_ollama_host`, `resolve_ollama_base_url`, plus `resolve_ollama_bare_host` (below).

Call sites converted — all 15 class-B hits, and `.env`'s inert commented line deleted:

| file | before | after |
|---|---|---|
| `pipeline/reextract/build_truthset.py` | `--host` default E | `default=None`, resolved after `parse_args` |
| `pipeline/reextract/extract_apparatus.py` | same | same |
| `pipeline/reextract/two_model_corpus.py` | same | same |
| `pipeline/reextract/nikud_audit_run.py` | module-level `HOST = …E` | lazy `_host()` |
| `pipeline/reextract/run_vol1.py` | same | lazy `_host()` |
| `pipeline/reextract/vol7_run.py` | local `host = …E` | `resolve_ollama_bare_host` |
| `pipeline/scripts/normalize_markdown.py` ×2 | hardcoded F + help text advertising it | resolved; help says REQUIRED |
| `evals/e6…/e6b_post_fix_validation.py` | hardcoded E | `resolve_ollama_base_url` |
| `evals/e6…/e6_near_vector_probe.py` | hardcoded E | same |
| `evals/e7…/e7_1_expansion_coverage.py` | hardcoded E | same |
| `test/test_litellm_proxy.py` | hardcoded E | same |
| `baml_src/main.baml` `Ollama` | `base_url "http://192.168.1.188:11434/v1"` | `env.OLLAMA_VISION_URL` |
| `baml_src/main.baml` `OllamaGPT` | same | `env.OLLAMA_TEXT_URL` |

The two module-level `HOST` constants became lazy `_host()` calls rather than module-level
resolution. Fail-loud was the requirement, but raising at *import* would mean you cannot import
these modules for their helpers without an endpoint set — a cost with no safety benefit, since
importing sends no traffic. The raise now happens on the first call that would actually use it.

Verified, not assumed: `vol7_run.py` with `OLLAMA_HOST`/`OLLAMA_BASE_URL` unset raises
`MissingEndpointError` with the gpu-servers.md citation. `run_vol1.py` under the same conditions
completes without raising — correct, because all 958 pages were already done and it never reached
a model call. That is the lazy resolution behaving as intended, not a guard that failed to fire.

`baml_client/` regenerated (13 files). The only remaining `.188` strings in the generated client
are inside my own explanatory comments; no live `base_url` references E or F.

## Two further findings, flagged not fixed

**1. These scripts cannot reach endpoint D at all.** `pipeline/reextract/` builds its URLs as
`f"http://{host}:11434/..."` — the port is hardcoded. Endpoint D is `192.168.1.169:11435`, so
Lane A's own assigned endpoint is unreachable from the reextract path. `resolve_ollama_bare_host`
therefore **refuses a host:port pair loudly** instead of silently stripping the port, which would
have sent a run to `:11434` on a machine where `:11435` was requested and written a host into the
artifacts that nobody chose. Widening the port is a change to shared URL construction and wants a
go first.

**2. `baml_src/gill_apparatus.baml:45` hardcodes `http://192.168.1.169:11434/v1`** (endpoint C).
Not a safety violation — C is open — but it is the same shape as the defect just removed: an
endpoint baked into shared substrate where no one passing through sees it. It is Lane B's
apparatus client, so it is reported, not changed.

## What this does NOT solve

- **DNS-view hole.** The guard refuses a hostname that resolves to E or F *from this machine*.
  A name resolving to a closed IP only from another host's DNS view passes. Documented in
  `_closed_aliases`.
- **Nothing outside this repo.** `dr-voluminous` was scanned: its only `.179`/`.188` hits are
  documentation in `reextract_vol1/audits/endpoint_reproduction_20260920.md` (Lane B's report).
  No executable defaults there.
- **The cluster's own path to F is untouched** (`charts/weaviate-overrides`), as above.
- **It does not prove no run ever used E.** Lane B checked: every artifact that records a host
  records `.169`. Absence of evidence, and the guard is forward-looking only.
- **Divergence from Lane B's proposal**, recorded deliberately: Lane B proposed redirecting the
  four defaults to C. That would have left a default in place. A default pointing somewhere safe
  is still a value nobody at the call site sees, and the next endpoint reshuffle makes it wrong
  again silently. The guard removes the default instead.

## Second pass, 2026-09-20 — the reextract substrate

Lane B's guard (`pipeline/reextract/endpoint_guard.py`, cherry-picked as `02fbd50`) is now
wired into `extract_apparatus.py` and `run_vol1.py` (`00c4cbd`). Both previously defaulted
to `192.168.1.179`. Lane B's born-test prints GUARDED for both without needing an edit.

**Two guard modules now coexist, and should not.**

| module | covers | resolves DNS | returns |
|---|---|---|---|
| `pipeline/common/endpoint_guard.py` (mine) | evals, `normalize_markdown`, `test_litellm_proxy` | yes | bare-host variant refuses ports |
| `pipeline/reextract/endpoint_guard.py` (Lane B's) | the six reextract scripts | **no** | the value as given, port included |

Two behavioural differences that matter, neither fixed here because the module is Lane B's:

1. **No DNS resolution.** A hostname resolving to .179/.188 passes Lane B's guard. Mine
   refuses it. Low risk (nothing in this tree uses names) but it is a real difference.
2. **The port comes back as given.** `extract_apparatus.py:55` builds
   `f"http://{host}:11434/api/generate"`, so `OLLAMA_HOST=192.168.1.169:11435` — endpoint
   **D, Lane A's own assigned endpoint** — would have built
   `http://192.168.1.169:11435:11434/...`. Closed with a local shape check in the two
   scripts: refuse, never strip. Stripping would silently redirect the run to :11434 on
   that machine and record a host nobody chose.

**Consequence worth stating plainly: endpoint D is unreachable from the reextract tree.**
The `:11434` is hardcoded in shared URL construction. Widening it is a change Lane B also
depends on, so it is not made here; the refusal message says so rather than leaving an
operator to discover it as a connection error.

**Repo grep, after the change** — every remaining .179/.188 occurrence outside `.git`,
`baml_client`, `.venv`:

- guard modules + their tests (they name the pair in order to refuse it) — correct;
- `baml_src/main.baml:35,52` — comments recording removed defaults, not endpoints;
- `charts/goat-yard-archive/values.yaml:160-161` — the LiteLLM round-robin pair. This is
  the production config itself; in scope, leave alone.
- `charts/weaviate-overrides/values-ollama-gpu.yaml:17` — `OLLAMA_API_ENDPOINT` pointing
  Weaviate's embedder **directly at F, bypassing LiteLLM**. Outside the LiteLLM carve-out
  and outside my lane; flagged, not changed. Someone should confirm it is intentional.

No executable default anywhere now reaches a closed endpoint.

### What this second pass does NOT solve

- Doesn't collapse the two guard modules. Recommend one module, Lane B's location, with my
  DNS resolution folded in.
- Doesn't make D reachable from reextract.
- `two_model_corpus.py` and `vol7_run.py` still use my `common` guard, not Lane B's — safe,
  but the directory is now inconsistent.
- Still proves nothing about whether any past run reached E. It only makes future ones fail
  loud.
