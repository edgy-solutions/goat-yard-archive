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
MAX_TOKENS = 300
OUT_TOKEN_FLAG = 300          # flag, never abort, a model whose median output exceeds this

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
    for s in diag.build_set(include_sealed=True):
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


def _body(model, ctx, img_b64, structured):
    text = PROMPT_HEAD + (
        "Context from the surrounding footnote text. Hebrew has been removed; each • marks one "
        f"Hebrew word that stood there:\n  {ctx}\n"
        "No scripture citation is recorded for this note in the local extraction."
    ) + PROMPT_TAIL
    b = {
        "model": model,
        "temperature": 0,
        "max_tokens": MAX_TOKENS,
        "reasoning": {"enabled": False},
        "provider": {"data_collection": "deny"},
        "usage": {"include": True},
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
            {"type": "text", "text": text},
        ]}],
    }
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
    """One read. Returns the row that goes on disk, including what was applied and what it cost."""
    body = _body(model, ctx, base64.b64encode(Path(cpath).read_bytes()).decode(), structured)
    _no_hebrew_outbound(body)
    t0 = time.time()
    r = httpx.post(URL, headers={"Authorization": f"Bearer {_key()}",
                                 "content-type": "application/json"}, json=body, timeout=timeout)
    secs = round(time.time() - t0, 1)
    if r.status_code >= 400:
        return {"span_id": s["span_id"], "aperture": APERTURE, "model": model, "kind": "call_error",
                "http": r.status_code, "error": r.text[:400], "secs": secs}
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
        "applied": {"temperature": 0, "reasoning_requested": "enabled:false",
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
        done = {(o["span_id"], o["model"]) for o in diag._lines(OUT) if o.get("kind") == "read"}
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
            f.write(json.dumps({"kind": "arm_header", "model": model, "started": time.strftime("%H:%M:%S"),
                                "pricing": {k: c[k] for k in ("prompt_per_mtok", "completion_per_mtok",
                                                              "image_per_1k")},
                                "structured": c["structured"]}, ensure_ascii=False) + "\n")
            for s, cpath, ctx in cs:
                if (s["span_id"], model) in done:
                    continue
                try:
                    row = call(model, s, cpath, ctx, c["structured"])
                except Exception as e:
                    row = {"span_id": s["span_id"], "aperture": APERTURE, "model": model,
                           "kind": "call_error", "error": f"{type(e).__name__}: {e}"[:300]}
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
    out = []
    for o in diag._lines(OUT):
        if o.get("kind") != "read" or o.get("span_id") not in sets:
            continue
        s = sets[o["span_id"]]
        o["cls"] = "UNSCORABLE" if s["unscorable"] else diag.classify(o["gated"], s["truth"])
        o["gloss_backtranslatable"] = _backtranslatable(s["latin_context"], s["truth"])
        out.append(o)
    return out


def score():
    rs = rows()
    errs = [o for o in diag._lines(OUT) if o.get("kind") == "call_error"]
    print(f"A2 aperture only, n=18 scorable (FILE pages; printed = file - 88)\n")
    print(f"{'model':40s} {'exact':>5s} {'nik':>4s} {'wrong':>5s} {'abst':>4s} {'n':>3s}  "
          f"{'exact/bt':>8s} {'exact/no-bt':>11s}")
    for m in ARMS:
        mr = [o for o in rs if o["model"] == m]
        if not mr:
            continue
        t = {k: sum(1 for o in mr if o["cls"] == k) for k in ("exact", "nikud_only", "wrong", "abstain")}
        bt = sum(1 for o in mr if o["cls"] == "exact" and o["gloss_backtranslatable"])
        print(f"{m:40s} {t['exact']:5d} {t['nikud_only']:4d} {t['wrong']:5d} {t['abstain']:4d} "
              f"{len(mr):3d}  {bt:8d} {t['exact']-bt:11d}")
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


def matrix():
    """Agreement across the frontier arms, the D arms and the C arms, on A2. Agreement only — see docstring."""
    rs = [dict(o) for o in rows()]
    for o in rs:
        o["model"] = o["model"] + " (OR)"
    d = [o for o in L._built() if o.get("aperture") == APERTURE] if hasattr(L, "_built") else []
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
    elif cmd == "matrix":
        matrix()
    else:
        sys.exit(__doc__)
