"""Frontier arm on OpenRouter: the 18 signed Hebrew spans, A2 aperture only (Chris's authorisation).

    python hebrew_frontier_or.py catalog          # resolve slugs + live pricing, no spend
    python hebrew_frontier_or.py plan             # what would be sent, byte counts, projected bill
    python hebrew_frontier_or.py probe --model X  # ONE call, to measure real tokens before the run
    python hebrew_frontier_or.py run              # all arms, resumable
    python hebrew_frontier_or.py score
    python hebrew_frontier_or.py cost
    python hebrew_frontier_or.py matrix

All page numbers here are FILE pages (printed = file - 88).

WHAT LEAVES THE NETWORK, AND WHAT MUST NOT. Chris's scope: A2 aperture only (ratified span box, +12px
native pad), and **no note-box crops leave the network**. A1_notebox is therefore not merely unused here --
`_cells()` cannot emit it, and the born-test asserts the outbound body contains exactly one image whose
path is the A2 entry. One image per request, plus text.

THE TEXT CONTEXT IS STRIPPED, AND THAT IS NOT A STYLE CHOICE. Chris asked for "the local extraction's
English/Latin for that note". The extraction's `latin_context` is the footnote's candidate line, and for
**11 of the 18 spans it contains the signed truth verbatim** -- p102:n0's line opens with the very word
being scored. Sending it raw would hand two thirds of the arms the answer and the run would measure
nothing. `_ctx()` replaces every Hebrew run with a bullet, so the model still learns how many Hebrew words
the note holds and what the Latin gloss says, and learns no Hebrew letter. `_no_hebrew_outbound()` is
called on every request body before it is sent, and raises rather than leaking.

THE BACK-TRANSLATION CONFOUND IS REAL AND IS NOT FIXED HERE. The Latin gloss is a *translation* of the
Hebrew: "tibi" for p138:n5 glosses the truth, and a model with Latin and Hebrew can reach the right
consonants without reading a pixel. That is partly the point -- escalation is aimed at spans whose own
note adjudicates them -- but it means a high `exact` count on this arm is not by itself evidence of
reading. `gloss_backtranslatable` is recorded per span and the report tallies split on it. The clean
control is a text-context-off arm, which this run does not include.

WHAT IS MISSING FROM CHRIS'S SPEC, SAID PLAINLY. Chris asked for "the cited verse reference" alongside the
Latin. **There is none to send.** These spans' note text is a terse gloss line of 32-121 characters;
verse attribution lives in the body path, which is Lane A's substrate. The prompt says so rather than
inventing a citation, and the pre-adjudication design names the dependency.

PRIVACY POSTURE -- VERIFIED VS ASSERTED. Chris asked that the no-retention/no-training filter be verified
via the account. `/api/v1/key` does not report that toggle, so it **cannot be verified from the API** and
this module does not claim it was. What it does instead is *enforceable and provable*: every request
carries `provider.data_collection = "deny"`, which restricts routing to providers that do not store or
train on prompts, and the provider OpenRouter actually served is recorded per call. The header records the
distinction under `privacy` with `account_toggle: "not-readable-via-api"`.

COMPARABILITY WITH THE D AND C ARMS. This arm differs from them on three axes at once -- one image instead
of two, text context instead of a context strip, and a different prompt (Chris's wording, JSON reply).
Cross-arm *differences* are therefore not interpretable as reader quality. The matrix uses these rows for
the agreement question only, and labels the C rows unrecorded-endpoint, which is what their header says.

Born-test: `test_hebrew_frontier_or.py`."""
import base64
import collections
import io
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))
import httpx
from PIL import Image

import hebrew_aperture_diag as diag
import hebrew_local_arms as L
from run_header import build_header, require_endpoint

URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS_URL = "https://openrouter.ai/api/v1/models"
HOST, PORT = "openrouter.ai", 443
KEY_ENV = "OPENROUTER_API_KEY"
APERTURE = "A2_spanbox"

OUT = diag.DATA / "hebrew_frontier_or_reads_20260927.jsonl"
CATALOG = diag.DATA / "hebrew_frontier_or_catalog_20260927.json"

ARMS = [
    "openai/gpt-6-astra", "openai/gpt-5.6-sol", "openai/gpt-5.6-terra", "openai/gpt-5.6-luna",
    "openai/gpt-6-luna", "openai/gpt-4o-mini",
    "anthropic/claude-opus-5.5", "anthropic/claude-sonnet-5", "anthropic/claude-haiku-4.5",
    "google/gemini-3.1-pro-preview", "google/gemini-3.8-flash",
    "qwen/qwen3.8-max-0902", "qwen/qwen3.8-max-prime", "qwen/qwen3.7-plus", "qwen/qwen3.8-flash",
    "qwen/qwen3.7-flash",
    "moonshotai/kimi-k3", "moonshotai/kimi-k2.6",
    "deepseek/deepseek-v4.1-flash", "deepseek/deepseek-v4-flash-vision-exp",
    "z-ai/glm-5.3-flash",
    "minimax/minimax-m3", "xiaomi/mimo-v2.6-flash", "x-ai/grok-4.7",
    "stepfun/step-3.7-flash", "inclusionai/ling-3.0-flash-vl",
]

HEB = re.compile(r"[֐-׿יִ-ﭏ]+")
# A cap must not manufacture an abstention. Six arms cannot have reasoning disabled at all (see the
# ladder), and at a 300-token cap `openai/gpt-6-astra` spent all 300 on reasoning for 4 of 18 spans and
# returned empty content with finish_reason "length" -- which `classify` would have scored `abstain`,
# reporting a budget artifact as a model declining to guess. 1200 leaves room for forced reasoning plus
# a one-word answer. Chris's reporting rule is unchanged: FLAG, never abort, a median output over 300.
MAX_TOKENS = 1200
OUT_TOKEN_FLAG = 300          # flag, never abort, a model whose median output exceeds this
RETRIES = 3                   # transient upstream 429/5xx only -- never a retry on a wrong answer
BACKOFF = 4.0

PROMPT_HEAD = (
    "The image is a magnified crop from a footnote in a 1766 English Bible commentary. It contains "
    "Hebrew as set by an eighteenth-century compositor. The source is UNPOINTED.\n\n"
    "Output the exact Hebrew as printed, in RTL Unicode, one line per printed line. Do not translate. "
    "Do not reorder characters. Do not add nikud. Do not modernise archaic orthography. If the crop is "
    "unreadable, return ABSTAIN rather than a guess.\n\n"
)
PROMPT_TAIL = (
    '\n\nReply with JSON only, no prose and no code fence: {"hebrew": "<the Hebrew exactly as printed, '
    'or the single word ABSTAIN>"}'
)


def _N(t):
    return unicodedata.normalize("NFC", (t or "").strip())


def _ctx(latin):
    """The note's Latin/English with every Hebrew run replaced by a bullet. See the module docstring.

    The bullet is deliberately informative: it tells the model how many Hebrew words the note contains
    and where they sit relative to the gloss, which is structural context, while carrying no letter."""
    return re.sub(r"\s{2,}", " ", HEB.sub("•", latin or "")).strip()


def _backtranslatable(latin, truth):
    """Did the note's own Latin gloss stand next to the scored Hebrew? Then a reading is not the only route.

    A coarse flag, not a measurement: true when the truth appeared verbatim in the note line, so the gloss
    beside it is a direct equivalent of the word being scored. Reported as a split, never used to discount
    a read."""
    return _N(truth) in _N(latin)


def cells():
    """(span, crop_path, ctx) for the 18 A2-scorable spans. A1 is unreachable from here, by construction."""
    man = {m["span_id"]: m for m in json.load(io.open(diag.CROPDIR / "manifest.json", encoding="utf-8"))}
    out = []
    pop = diag.build_set(include_sealed=True)
    # An unmeasured crop is not a sound crop. Without crop_faults.json every span looks scorable,
    # which is how a blank or clamped crop reaches the wire and gets charged to a model as a wrong
    # read. Refuse the whole population rather than send part of it.
    if any(s.get("crop_unmeasured") for s in pop):
        raise RuntimeError(
            "crop faults are UNMEASURED (no crop_faults.json) -- refusing to build a send "
            "population. Run the `faults` command first; an unmeasured crop is not a sound one.")
    for s in pop:
        if s["unscorable"] or not s["span_box"]:
            continue
        e = (man.get(s["span_id"]) or {}).get(APERTURE)
        if not e:
            continue
        out.append((s, e["path"], _ctx(s["latin_context"])))
    return out


def _no_hebrew_outbound(body):
    """Raise if any Hebrew character is anywhere in the request body. Called before every send.

    The leak this guards is not hypothetical: 11 of 18 spans carry the signed truth inside the note line
    the prompt is built from. A guard that ran only in the test would not have been on the wire."""
    blob = json.dumps(body, ensure_ascii=False)
    if HEB.search(blob):
        raise RuntimeError("REFUSING TO SEND: Hebrew found in the outbound body — the truth would leak")
    return True


REASONING_LADDER = [
    ({"enabled": False}, "enabled:false"),
    ({"effort": "minimal"}, "effort:minimal"),
    (None, "omitted"),
]


def _body(model, ctx, img_b64, structured, reasoning=None):
    text = PROMPT_HEAD + (
        "Context from the surrounding footnote text. Hebrew has been removed; each • marks one "
        f"Hebrew word that stood there:\n  {ctx}\n"
        "No scripture citation is recorded for this note in the local extraction."
    ) + PROMPT_TAIL
    b = {
        "model": model,
        "temperature": 0,
        "max_tokens": MAX_TOKENS,
        "provider": {"data_collection": "deny"},
        "usage": {"include": True},
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
            {"type": "text", "text": text},
        ]}],
    }
    if reasoning is None:
        reasoning = REASONING_LADDER[0][0]
    if reasoning:
        b["reasoning"] = reasoning
    if structured:
        b["response_format"] = {"type": "json_object"}
    return b


def _parse(raw):
    """The model's Hebrew, from JSON if it obeyed and from the text if it did not. Records which."""
    t = (raw or "").strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    m = re.search(r"\{.*\}", t, flags=re.S)
    if m:
        try:
            d = json.loads(m.group(0))
            v = d.get("hebrew", d.get("Hebrew", ""))
            if isinstance(v, list):
                v = "\n".join(str(x) for x in v)
            return str(v).strip(), "json"
        except Exception:
            pass
    return t, "text"


def catalog(refresh=True):
    """Live slug resolution and pricing. A metadata call: no inference, no spend."""
    if refresh or not CATALOG.exists():
        r = httpx.get(MODELS_URL, headers={"Authorization": f"Bearer {_key()}"}, timeout=60)
        r.raise_for_status()
        cat = {m["id"]: m for m in r.json()["data"]}
        keep = {}
        for s in ARMS:
            m = cat.get(s)
            if not m:
                keep[s] = {"status": "ABSENT"}
                continue
            arch = m.get("architecture", {})
            p = m.get("pricing", {})
            keep[s] = {
                "status": "ok" if "image" in (arch.get("input_modalities") or []) else "NO-IMAGE",
                "prompt_per_mtok": float(p.get("prompt", 0) or 0) * 1e6,
                "completion_per_mtok": float(p.get("completion", 0) or 0) * 1e6,
                "image_per_1k": float(p.get("image", 0) or 0) * 1000,
                "structured": "response_format" in (m.get("supported_parameters") or []),
                "reasoning_param": "reasoning" in (m.get("supported_parameters") or []),
                "canonical_slug": m.get("canonical_slug"),
                "context_length": m.get("context_length"),
            }
        CATALOG.write_text(json.dumps(
            {"pulled": time.strftime("%Y-%m-%dT%H:%M:%S"), "source": MODELS_URL, "models": keep},
            ensure_ascii=False, indent=1), encoding="utf-8")
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def _key():
    k = os.getenv(KEY_ENV)
    if not k:
        sys.exit(f"refusing: env {KEY_ENV} is not set")
    return k


def _budget():
    r = httpx.get("https://openrouter.ai/api/v1/key",
                  headers={"Authorization": f"Bearer {_key()}"}, timeout=30)
    r.raise_for_status()
    d = r.json()["data"]
    return {"limit": d.get("limit"), "usage": d.get("usage"),
            "remaining": d.get("limit_remaining"), "expires_at": d.get("expires_at")}


def call(model, s, cpath, ctx, structured, timeout=300):
    """One read, walking the reasoning ladder. Records what was APPLIED, not what was asked for.

    Chris's setting is "reasoning off or minimum effort wherever the API allows, and record what was
    actually applied". Some endpoints refuse: `openai/gpt-6-astra` answers 400 "Reasoning is mandatory
    for this endpoint and cannot be disabled." Dropping that arm would report a capability gap that is
    really a routing rule, so the ladder steps down -- off, then minimal, then omitted -- and the row
    says which rung carried the read. A rung is never silently skipped: `reasoning_ladder` lists the
    refusals that got us there."""
    # GATED: a blank or clamped crop never reaches OpenRouter. p423:n3 and p726:n3 went out to 30
    # arms as pure white before this existed, and 7 of 8 answered with Hebrew anyway.
    img = diag.b64_gated(cpath, what="frontier crop")
    refusals, r, body, applied, secs = [], None, None, None, 0.0
    for spec, label in REASONING_LADDER:
        body = _body(model, ctx, img, structured, reasoning=spec)
        _no_hebrew_outbound(body)
        t0 = time.time()
        r = httpx.post(URL, headers={"Authorization": f"Bearer {_key()}",
                                     "content-type": "application/json"}, json=body, timeout=timeout)
        secs += round(time.time() - t0, 1)
        applied = label
        # Transient upstream limits are not a capability result. Bounded, and every wait is recorded.
        for attempt in range(RETRIES):
            if r.status_code not in (429, 500, 502, 503, 504):
                break
            wait = BACKOFF * (2 ** attempt)
            refusals.append({"rung": label, "http": r.status_code, "retry_in_s": wait,
                             "error": r.text[:120]})
            time.sleep(wait)
            t0 = time.time()
            r = httpx.post(URL, headers={"Authorization": f"Bearer {_key()}",
                                         "content-type": "application/json"}, json=body,
                           timeout=timeout)
            secs += round(time.time() - t0, 1)
        if not (r.status_code == 400 and "reasoning" in r.text.lower()):
            break
        refusals.append({"rung": label, "http": 400, "error": r.text[:160]})
    if r.status_code >= 400:
        return {"span_id": s["span_id"], "aperture": APERTURE, "model": model, "kind": "call_error",
                "http": r.status_code, "error": r.text[:400], "secs": secs,
                "reasoning_ladder": refusals, "reasoning_applied": applied}
    d = r.json()
    if "choices" not in d:
        return {"span_id": s["span_id"], "aperture": APERTURE, "model": model, "kind": "call_error",
                "http": r.status_code, "error": json.dumps(d)[:400], "secs": secs}
    raw = (d["choices"][0]["message"].get("content") or "").strip()
    heb, how = _parse(raw)
    crop = Image.open(cpath).convert("L")
    gated, nik, dens = diag.nikud_gate.gated_strip(heb, crop)
    sv, sr = diag.script_gate.gate(gated, s["latin_context"])
    u = d.get("usage") or {}
    det = u.get("completion_tokens_details") or {}
    return {
        "span_id": s["span_id"], "aperture": APERTURE, "model": model, "kind": "read",
        "endpoint_id": "UNREGISTERED:openrouter.ai:443", "provider_served": d.get("provider"),
        "gen_id": d.get("id"), "raw": raw, "hebrew": heb, "parsed_from": how,
        "gated": gated, "nikud_verdict": nik, "nikud_density": round(float(dens), 3),
        "script_verdict": sv, "script_reason": sr,
        "finish_reason": (d["choices"][0].get("finish_reason")),
        "tok_in": u.get("prompt_tokens"), "tok_out": u.get("completion_tokens"),
        "reasoning_tokens": det.get("reasoning_tokens"),
        "cost_usd": u.get("cost"), "is_byok": u.get("is_byok"),
        "reasoning_applied": applied, "reasoning_ladder": refusals,
        "applied": {"temperature": 0, "reasoning_requested": applied,
                    "structured_requested": bool(structured),
                    "data_collection": "deny", "max_tokens": MAX_TOKENS},
        "secs": secs,
    }


def plan():
    cat = catalog(refresh=False)["models"]
    cs = cells()
    px = sum((lambda wh: wh[0] * wh[1])(Image.open(c).size) for _s, c, _x in cs)
    img_tok = px / 750.0
    txt_tok = sum(len(PROMPT_HEAD + x + PROMPT_TAIL) for _s, _c, x in cs) / 4.0
    tin, tout = img_tok + txt_tok, len(cs) * 40
    print(f"spans (A2 only) : {len(cs)}   images per request: 1   note-box crops sent: 0")
    print(f"est tokens/arm  : in ~{tin:,.0f}  out ~{tout:,.0f}   (ESTIMATE — `probe` measures the truth)")
    tot = 0.0
    for m in ARMS:
        c = cat.get(m, {})
        if c.get("status") != "ok":
            print(f"  SKIP {m:40s} {c.get('status')}")
            continue
        est = tin / 1e6 * c["prompt_per_mtok"] + tout / 1e6 * c["completion_per_mtok"]
        tot += est
        print(f"  {m:40s} ~${est:6.3f}  struct={str(c['structured']):5s} reas={c['reasoning_param']}")
    print(f"\nprojected total : ~${tot:.2f}   budget: {_budget()}")
    print(f"writes          : {OUT}")


def probe(model):
    cat = catalog(refresh=False)["models"]
    s, cpath, ctx = cells()[0]
    row = call(model, s, cpath, ctx, cat.get(model, {}).get("structured", False))
    print(json.dumps({k: v for k, v in row.items() if k != "raw"}, ensure_ascii=False, indent=1))
    print("raw:", repr(row.get("raw", ""))[:200])
    if row.get("kind") == "read":
        ti, to = row.get("tok_in") or 0, row.get("tok_out") or 0
        print(f"\nMEASURED per call: in {ti} out {to}  cost ${row.get('cost_usd')}")
        for m in ARMS:
            c = cat.get(m, {})
            if c.get("status") != "ok":
                continue
            per = ti / 1e6 * c["prompt_per_mtok"] + to / 1e6 * c["completion_per_mtok"]
            print(f"  {m:40s} 18 spans ~${per*18:6.3f}   per 1000 spans ~${per*1000:8.2f}")


def run(only=None):
    cat = catalog(refresh=True)
    cs = cells()
    done = set()
    if OUT.exists():
        # A truncated or empty read is NOT done: it must be retried at the larger cap, or the artifact
        # keeps a budget artifact where a reading belongs.
        done = {(o["span_id"], o["model"]) for o in diag._lines(OUT)
                if o.get("kind") == "read" and o.get("finish_reason") != "length"
                and (o.get("hebrew") or "").strip()}
    first = not OUT.exists()
    with io.open(OUT, "a", encoding="utf-8") as f:
        if first:
            hdr = build_header(host=HOST, port=PORT, model="multi:26-openrouter-arms",
                               digest_fn=lambda hp, mo, t=None: "n/a:hosted-api",
                               identity_extra={"aperture": APERTURE, "n_scorable": len(cs),
                                               "arms": ARMS, "prompt_sha16": diag_sha(PROMPT_HEAD +
                                                                                     PROMPT_TAIL)},
                               extra={"privacy": {"request_filter": "provider.data_collection=deny",
                                                  "account_toggle": "not-readable-via-api",
                                                  "verified": "per-request filter only; "
                                                              "account toggle NOT verifiable via API"},
                                      "catalog_pulled": cat["pulled"],
                                      "budget_before": _budget(),
                                      "note_box_crops_sent": 0,
                                      "text_context": "latin_context with Hebrew runs replaced by U+2022",
                                      "pages": "FILE pages (printed = file - 88)"})
            require_endpoint(hdr, "frontier run")
            f.write(json.dumps(hdr, ensure_ascii=False) + "\n")
        for model in (only or ARMS):
            c = cat["models"].get(model, {})
            if c.get("status") != "ok":
                f.write(json.dumps({"kind": "arm_skipped", "model": model,
                                    "why": c.get("status", "ABSENT")}, ensure_ascii=False) + "\n")
                print(f"SKIP {model}: {c.get('status')}")
                continue
            print(f"\n== {model}")
            from run_header import _git_head, _git_dirty
            f.write(json.dumps({"kind": "arm_header", "model": model, "started": time.strftime("%H:%M:%S"),
                                "git_head": _git_head(), "git_dirty": _git_dirty(),
                                "pricing": {k: c[k] for k in ("prompt_per_mtok", "completion_per_mtok",
                                                              "image_per_1k")},
                                "structured": c["structured"]}, ensure_ascii=False) + "\n")
            for s, cpath, ctx in cs:
                if (s["span_id"], model) in done:
                    continue
                try:
                    row = call(model, s, cpath, ctx, c["structured"])
                except diag.CropRefused as e:
                    # Pre-send refusal: no request was made, no tokens were spent, and the span is
                    # UNSCORABLE rather than wrongly read. It is kept in the file because a silent
                    # skip would leave the span looking un-attempted.
                    row = {"span_id": s["span_id"], "aperture": APERTURE, "model": model,
                           "kind": "crop_refused", "unscorable": f"crop-fault:{e.fault}",
                           "crop_fault": e.fault, "what": e.what, "cost_usd": 0.0,
                           "reached_wire": False}
                except Exception as e:
                    row = {"span_id": s["span_id"], "aperture": APERTURE, "model": model,
                           "kind": "call_error", "error": f"{type(e).__name__}: {e}"[:300],
                           "reached_wire": True}
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                tag = row.get("kind")
                print(f"  {s['span_id']:10s} {tag:10s} {str(row.get('gated', row.get('error','')))[:44]!r}"
                      f" {row.get('provider_served') or ''}")
        f.write(json.dumps({"kind": "run_footer", "budget_after": _budget(),
                            "finished": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False) + "\n")
    print("\nwrote", OUT)


def diag_sha(t):
    import hashlib
    return hashlib.sha256(t.encode()).hexdigest()[:16]


def rows():
    """Scored read rows. Classification is diag.classify against the signed truth — nothing else."""
    sets = {s["span_id"]: s for s in diag.build_set(include_sealed=True)}
    # LAST row per (span, model) wins. A retried cell appends rather than overwriting, so without this
    # a retry would be counted twice -- once as the truncated artifact and once as the real read.
    keep = {}
    for o in diag._lines(OUT):
        if o.get("kind") != "read" or o.get("span_id") not in sets:
            continue
        keep[(o["span_id"], o["model"])] = o
    out = []
    for (sid, _m), o in keep.items():
        s = sets[sid]
        o["cls"] = "UNSCORABLE" if s["unscorable"] else diag.classify(o["gated"], s["truth"])
        o["gloss_backtranslatable"] = _backtranslatable(s["latin_context"], s["truth"])
        o["truncated"] = o.get("finish_reason") == "length" or not (o.get("hebrew") or "").strip()
        out.append(o)
    return out


# The gate table was published on 2026-09-27 from an ad-hoc script that is gone. Reproducing it took
# two tries: the cross-family cluster is astra + opus + qwen3.7-plus, NOT the cumulative 4-arm set,
# and read as cumulative it is unreproducible (14 agreeing spans for a 4-arm gate where the 3-arm
# gate agrees on 13, which no all-identical rule can produce). The clusters are therefore spelled out
# here and every published figure comes out of this function rather than out of a script that dies
# with its session.
#
#   a gate AGREES on a span when every arm in it returns the identical normalized string;
#   spans where every arm abstains are excluded (a pair of silences is not a consensus);
#   p900:n4 is NOT excluded -- its signed truth is "not Hebrew", so ABSTAIN there is the RIGHT
#   answer and classify() already scores it `exact`. Filtering on the literal text "ABSTAIN"
#   instead of on the class drops it and moves the numbers.
GATES = (("astra + opus", ("openai/gpt-6-astra", "anthropic/claude-opus-5.5")),
         ("astra + opus + gemini-3.1-pro", ("openai/gpt-6-astra", "anthropic/claude-opus-5.5",
                              "google/gemini-3.1-pro-preview")),
         ("astra + opus + qwen3.7-plus", ("openai/gpt-6-astra", "anthropic/claude-opus-5.5",
                                          "qwen/qwen3.7-plus")))
RIGHT = ("exact", "punct-only")


def gate():
    rs = rows()
    by = {(o["span_id"], o["model"]): o for o in rs}
    spans = sorted({o["span_id"] for o in rs if o["cls"] != "UNSCORABLE"})
    g = lambda a, sp: diag._norm((by.get((sp, a)) or {}).get("gated") or "")
    c = lambda a, sp: (by.get((sp, a)) or {}).get("cls")
    print(f"gate precision, A2, n={len(spans)} (FILE pages; printed = file - 88)\n")
    print(f"{'gate':32s} {'agrees':>7s} {'right':>6s} {'precision':>10s}")
    for name, arms in GATES:
        ag = [sp for sp in spans if g(arms[0], sp) and len({g(a, sp) for a in arms}) == 1
              and not all(c(a, sp) == "abstain" for a in arms)]
        ok = [sp for sp in ag if c(arms[0], sp) in RIGHT]
        print(f"{name:32s} {len(ag):3d}/{len(spans):<3d} {len(ok):6d} {len(ok) / len(ag):9.0%}")
    n = ok_ = 0
    for sp in spans:
        v = collections.Counter(g(a, sp) for a in {m for _s, m in by} if c(a, sp) not in (None, "abstain"))
        if not v:
            continue
        n += 1
        top = v.most_common(1)[0][0]
        ok_ += any(c(a, sp) in RIGHT for a in {m for _s, m in by} if g(a, sp) == top)
    print(f"{'plurality across every arm':32s} {n:3d}/{len(spans):<3d} {ok_:6d} {ok_ / n:9.0%}")
    cov = {sp for sp in spans if any(c(a, sp) in RIGHT for a in {m for _s, m in by})}
    print(f"\ncoverage: {len(cov)}/{len(spans)} spans read correctly by at least one arm in THIS file")
    print("never read here:", ", ".join(sorted(set(spans) - cov)) or "-")


def score():
    rs = rows()
    errs = [o for o in diag._lines(OUT) if o.get("kind") == "call_error"]
    print(f"A2 aperture only, n=18 scorable (FILE pages; printed = file - 88)\n")
    print(f"{'model':40s} {'exact':>5s} {'nik':>4s} {'wrong':>5s} {'abst':>4s} {'trunc':>5s} "
          f"{'n':>3s}  {'ex/bt':>6s} {'ex/no-bt':>8s}")
    print(f"{'':40s} {'':5s} {'':4s} {'':5s} {'':4s} {'':5s} {'':3s}  "
          f"bt = gloss back-translatable (11 spans); no-bt (7)")
    EX = ("exact", "punct-only")
    for m in ARMS:
        mr = [o for o in rs if o["model"] == m]
        if not mr:
            continue
        t = L._tally(mr)                      # the LOCAL arms' tally: same folding, nothing re-scored
        # TRUNCATED is reported as its own outcome, never folded into abstain. An empty reply that hit
        # the token cap is a budget artifact; an empty reply that finished is a model declining to
        # guess. Abstention-vs-guessing is the axis that separated the local arms, so collapsing the
        # two would corrupt the one comparison this tally is for.
        tc = sum(1 for o in mr if o["truncated"])
        ab = t["abstain"] - sum(1 for o in mr if o["truncated"] and o["cls"] == "abstain")
        bt = sum(1 for o in mr if o["cls"] in EX and o["gloss_backtranslatable"])
        nb = sum(1 for o in mr if o["cls"] in EX and not o["gloss_backtranslatable"])
        print(f"{m:40s} {t['exact']:5d} {t['nikud-only']:4d} {t['wrong']:5d} {ab:4d} {tc:5d} "
              f"{len(mr):3d}  {bt:6d} {nb:8d}")
    # P3: the back-translation channel, pooled. The gate on whether `exact` means reading.
    btr = [o for o in rs if o["gloss_backtranslatable"]]
    nbr = [o for o in rs if not o["gloss_backtranslatable"]]
    r1 = sum(1 for o in btr if o["cls"] in EX) / max(len(btr), 1)
    r2 = sum(1 for o in nbr if o["cls"] in EX) / max(len(nbr), 1)
    print(f"\npooled exact-rate  backtranslatable {r1:.3f} ({len(btr)} reads)   "
          f"NOT backtranslatable {r2:.3f} ({len(nbr)} reads)   ratio "
          f"{(r1 / r2) if r2 else float('inf'):.2f}x")
    print(f"parsed from prose (JSON ignored): "
          f"{sorted({o['model'] for o in rs if o.get('parsed_from') == 'text'})}")
    print(f"arms with nonzero reasoning tokens despite the toggle: "
          f"{sorted({o['model'] for o in rs if (o.get('reasoning_tokens') or 0) > 0})}")
    print(f"reasoning rung actually applied: "
          f"{sorted({(o['model'], o.get('reasoning_applied')) for o in rs}, key=str)[:0] or ''}")
    rung = {}
    for o in rs:
        rung.setdefault(o.get("reasoning_applied"), set()).add(o["model"])
    for k, v in rung.items():
        print(f"   {str(k):16s} {len(v):2d} arms")
    if errs:
        print(f"\ncall errors: {len(errs)}")
        seen = {}
        for e in errs:
            seen.setdefault(e["model"], 0)
            seen[e["model"]] += 1
        for m, n in sorted(seen.items(), key=lambda kv: -kv[1]):
            print(f"  {m:40s} {n:3d}")


def cost():
    rs = rows()
    cat = catalog(refresh=False)["models"]
    print(f"{'model':40s} {'calls':>5s} {'tok_in':>8s} {'tok_out':>7s} {'med_out':>7s} "
          f"{'reas':>5s} {'cost$':>8s} {'$/1k spans':>10s} provider")
    tot = 0.0
    for m in ARMS:
        mr = [o for o in rs if o["model"] == m]
        if not mr:
            continue
        ti = sum(o.get("tok_in") or 0 for o in mr)
        to = sum(o.get("tok_out") or 0 for o in mr)
        outs = sorted(o.get("tok_out") or 0 for o in mr)
        med = outs[len(outs) // 2]
        rt = sum(o.get("reasoning_tokens") or 0 for o in mr)
        cu = sum(float(o.get("cost_usd") or 0) for o in mr)
        tot += cu
        per1k = cu / len(mr) * 1000 if mr else 0
        provs = sorted({str(o.get("provider_served")) for o in mr})
        flag = " <-- OUT>300" if med > OUT_TOKEN_FLAG else ""
        print(f"{m:40s} {len(mr):5d} {ti:8d} {to:7d} {med:7d} {rt:5d} {cu:8.4f} {per1k:10.2f} "
              f"{','.join(provs)[:28]}{flag}")
    print(f"\nmeasured total: ${tot:.4f}   budget now: {_budget()}")


def _family(model):
    """Vendor family of an arm. Two arms from one vendor are not two witnesses."""
    return model.split("/")[0] if "/" in model else model.split(":")[0].rstrip("0123456789.")


def support():
    """Per span: how many arms READ it, how many agree on the top reading, and whether that reading
    agrees WITH the signature or AGAINST it. The card list Chris asked for comes out of here.

    Written because the first version of this table was an ad-hoc script -- the same mistake `gate()`
    already carries a comment about -- and it published two figures that are now known to be false.
    It counted the literal token "ABSTAIN" as a reading and therefore as AGREEMENT. 22 of 26 arms
    answered "ABSTAIN" on each of the two blank crops, so silence was tallied as a 75-76% cross-family
    consensus, and that non-finding was about to be written up as the lane's cleanest demonstration
    that agreement measures shared priors rather than shared evidence.

    It is the opposite. Shown an image with no ink, 22 of 26 frontier arms declined to read it and the
    4 that did disagreed with each other. The honest version of the claim is narrower and duller: back-
    translation from the Latin gloss is real but rare on the frontier (~15% of arms) and does not
    converge. The blank crops are a control for ABSTENTION behaviour, not a consensus exhibit.

    So: abstains are counted and reported, never scored; degenerate loops are excluded (see
    diag.DROPPED_ARMS); the share is over arms that actually produced a reading; and `families` is
    distinct vendors agreeing, because 4 OpenAI arms on one string is one witness with four voices."""
    sets = {s["span_id"]: s for s in diag.build_set(include_sealed=True)}
    keep = {}
    for o in diag._lines(OUT):
        if o.get("kind") != "read" or o.get("span_id") not in sets:
            continue
        if o.get("model") in diag.DROPPED_ARMS:
            continue
        keep.setdefault(o["span_id"], {})[o["model"]] = o
    tab = []
    for sid, per in keep.items():
        s_ = sets[sid]
        ab, live = 0, {}
        for m, o in per.items():
            cls = diag.classify(o.get("gated") or "", s_["truth"])
            if cls == "abstain":
                ab += 1
            elif cls != "degenerate":
                live[m] = (diag._norm(o.get("gated") or ""), cls)
        if not live:
            tab.append((0.0, sid, len(per), ab, 0, 0, 0, 0, "-", s_["unscorable"]))
            continue
        v = collections.Counter(t for t, _c in live.values())
        top, n = v.most_common(1)[0]
        cls = next(c for t, c in live.values() if t == top)
        fams = len({_family(m) for m, (t, _c) in live.items() if t == top})
        tab.append((n / len(live), sid, len(per), ab, len(live), len(v), n, fams, cls,
                    s_["unscorable"]))
    print(f"support for the TOP reading per span, A2, {len(tab)} spans "
          f"(FILE pages; printed = file - 88)\n")
    print(f"{'span':11s} {'arms':>4s} {'abst':>5s} {'read':>5s} {'distinct':>9s} {'top':>9s} "
          f"{'fams':>5s}  {'class':11s} verdict")
    cards = []
    for share, sid, arms, ab, nlive, ndist, n, fams, cls, unsc in sorted(tab, reverse=True):
        against = cls not in RIGHT
        v = "AGAINST signature" if against else "with signature"
        if unsc:
            v += f"   [{unsc[:34]}]"
        print(f"{sid:11s} {arms:4d} {ab:5d} {nlive:5d} {ndist:9d} {n:4d}={share:4.0%} {fams:5d}  "
              f"{cls:11s} {v}")
        if against and share >= CARD_AT and not unsc:
            cards.append((sid, share, fams, n, nlive))
    print(f"\ncards at >={CARD_AT:.0%} of reading arms AGAINST the signature:")
    for sid, share, fams, n, nlive in cards or []:
        print(f"    {sid}  {n}/{nlive} arms = {share:.0%} across {fams} families")
    if not cards:
        print("    none")
    print("\nblank-crop control (no ink was sent; these arms were shown nothing):")
    for share, sid, arms, ab, nlive, ndist, n, fams, cls, unsc in sorted(tab, reverse=True):
        if unsc and "crop-fault" in unsc:
            print(f"    {sid}  {ab}/{arms} abstained, {nlive} read, {ndist} distinct readings "
                  f"among them")


CARD_AT = 0.80


def matrix():
    """Agreement across the frontier arms, the D arms and the C arms, on A2. Agreement only — see docstring."""
    rs = [dict(o) for o in rows()]
    for o in rs:
        o["model"] = o["model"] + " (OR)"
    # L.score() returns SCORED D-arm reads. L._built() returns crops -- a different thing, and using
    # it here would have dropped the endpoint-D arms from the matrix Chris asked for.
    d = [dict(o) for o in L.score(include_sealed=True)[0] if o.get("aperture") == APERTURE]
    for o in d:
        o["model"] = o["model"] + " (D)"
    c = [o for o in L.load_c_arms(include_sealed=True) if o.get("aperture") == APERTURE]
    for o in c:
        o["model"] = o["model"].replace(" (C)", " (C:unrecorded-endpoint)")
    allrows = rs + [dict(o) for o in d] + c
    models = sorted({o["model"] for o in allrows})
    by = {(o["span_id"], o["model"]): o for o in allrows}
    spans = sorted({o["span_id"] for o in allrows})
    print(f"models: {len(models)}   spans: {len(spans)}   aperture {APERTURE}")
    print("\nper-span distinct readings")
    for sid in spans:
        vals = [_N((by.get((sid, m)) or {}).get("gated", "")) for m in models if (sid, m) in by]
        vals = [v for v in vals if v]
        u = len(set(vals))
        lab = "UNANIMOUS" if u == 1 and len(vals) > 1 else f"{u} distinct"
        print(f"  {sid:11s} {len(vals):2d} reads  {lab}")
    print("\npairwise agreement (same gated string), pairs agreeing on 4+ spans")
    pairs = []
    for i, x in enumerate(models):
        for y in models[i + 1:]:
            both = [sid for sid in spans if (sid, x) in by and (sid, y) in by]
            same = sum(1 for sid in both
                       if _N(by[(sid, x)].get("gated", "")) == _N(by[(sid, y)].get("gated", ""))
                       and _N(by[(sid, x)].get("gated", "")))
            if both:
                pairs.append((same, len(both), x, y))
    for same, n, x, y in sorted(pairs, reverse=True):
        if same >= 4:
            print(f"    {x[:34]:34s} vs {y[:34]:34s}  {same:2d}/{n:2d}")
    print(f"    ... {sum(1 for p in pairs if p[0] < 4)} of {len(pairs)} pairs agree on fewer than 4")


if __name__ == "__main__":
    a = sys.argv[1:]
    cmd = a[0] if a else "plan"
    mv = a[a.index("--model") + 1] if "--model" in a else None
    if cmd == "catalog":
        c = catalog(refresh=True)
        for k, v in c["models"].items():
            print(f"  {k:40s} {v['status']:9s} in {v.get('prompt_per_mtok', 0):8.3f} "
                  f"out {v.get('completion_per_mtok', 0):8.3f} struct={v.get('structured')}")
        print("pulled", c["pulled"], "->", CATALOG)
    elif cmd == "plan":
        plan()
    elif cmd == "probe":
        probe(mv or ARMS[-1])
    elif cmd == "run":
        run([mv] if mv else None)
    elif cmd == "score":
        score()
    elif cmd == "cost":
        cost()
    elif cmd == "support":
        support()
    elif cmd == "gate":
        gate()
    elif cmd == "matrix":
        matrix()
    else:
        sys.exit(__doc__)
