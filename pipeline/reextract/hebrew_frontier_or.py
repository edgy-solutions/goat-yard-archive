"""Frontier arm on OpenRouter: the signed Hebrew spans, A2 aperture only (Chris's authorisation).

The sendable population is 19 as of 2026-09-27 and is NOT a constant: it was 18 when the first run went
out, and the two figures differ by a membership turnover in both directions (p423:n3 and p726:n3 in
once their crops stopped cutting blank, p900:n4 out on a geometry fault), not by a net of one. Every
count printed here is derived from `cells()`; where a number is written down in prose below it belongs
to the run that measured it and keeps its own denominator.

    python hebrew_frontier_or.py catalog          # resolve slugs + live pricing, no spend
    python hebrew_frontier_or.py plan             # what would be sent, byte counts, projected bill
    python hebrew_frontier_or.py probe --model X  # ONE call, to measure real tokens before the run
    python hebrew_frontier_or.py run --approved   # all arms, resumable; REFUSES without the sheet
    python hebrew_frontier_or.py run --span p423:n3,p726:n3    # bound the spend to a named scope
    python hebrew_frontier_or.py plan --span p423:n3           # the same scope, priced, no spend
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
**11 of the spans it contains the signed truth verbatim** (11 of 18 when measured; 11 of 19 today,
because p726:n3 joined the population already leaking and p423:n3 joined not leaking) -- p102:n0's line
opens with the very word
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
from run_header import build_header, require_endpoint, RunWriter

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


def cells(only=None):
    """(span, crop_path, ctx) for the A2-scorable spans. A1 is unreachable from here, by construction.

    `only` is an explicit span-id scope: the run sends these and nothing else. It FAILS LOUD on an id
    that is not in the sendable population, because the failure mode it exists to prevent is a typo
    that silently sends zero cells and reports a clean run."""
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
    if only is not None:
        want = set(only)
        have = {s["span_id"] for s, _c, _x in out}
        missing = want - have
        if missing:
            # Name why each one is missing. "not in the population" is three different facts --
            # unknown id, unscorable span, refused crop -- and they call for three different actions.
            pop = {s["span_id"]: s for s in diag.build_set(include_sealed=True)}
            why = {sid: (pop[sid]["unscorable"] or "no span box" if sid in pop else "UNKNOWN span id")
                   for sid in sorted(missing)}
            raise RuntimeError("--span names %d span(s) that cannot be sent: %s"
                               % (len(missing), json.dumps(why, ensure_ascii=False)))
        out = [c for c in out if c[0]["span_id"] in want]
    return out


def crop_sha(cpath):
    """sha256[:16] of the exact file that will be b64-encoded into the request body."""
    return diag._sha(cpath)


def read_key(o):
    """The identity of a READ: which cell, and which pixels. `crop_sha16` is part of it, not metadata.

    Two reads can share a (span, model) cell and be about different rectangles -- that is precisely
    what happens when a box is re-ratified and the span is re-sent. A key without the hash cannot tell
    them apart, and every rule that used one treated the pair as the unit of evidence."""
    return (o.get("span_id"), o.get("model"), o.get("crop_sha16"))


def stale_reads():
    """(span_id, model, crop_sha16) -> why, for every read no longer about a crop we hold.

    A read is evidence about the pixels it was shown. When a crop is re-cut, the reads taken on the old
    one do not become wrong -- they become mute, and scoring them reports a model's opinion of a
    rectangle that no longer exists anywhere except the frozen archive.

    KEYED ON THE READ, and that is the whole correction. This returned `(span_id, model) -> why` until
    2026-09-27, and consumers muted the pair. After the 104-call send, p423:n3 and p726:n3 each held 26
    fresh reads at the approved hash beside 26 pre-hash reads on the retired crop; the pair key put the
    dead read's verdict over the live one, `rows()` scored neither span, and `run()`'s resume set would
    have re-sent all 52 cells. The void is a statement about pixels, so its key carries the hash."""
    sets = {s["span_id"] for s in diag.build_set(include_sealed=True)}
    changed = set(diag.crops_changed(APERTURE))
    cur = {sid: diag.crop_sha(sid, APERTURE) for sid in sets}
    out = {}
    for o in diag._lines(OUT):
        if o.get("kind") != "read" or o.get("span_id") not in sets:
            continue
        # The rule itself is `diag.stale_read_why` -- one copy, shared with hebrew_bind. It used to be
        # inline here, and being inline here is why bind never got the read-keyed version of it.
        why = diag.stale_read_why(o, changed, cur)
        if why:
            out[read_key(o)] = why
    return out


def live_reads():
    """Reads that still speak for a crop we hold -- the complement of `stale_reads()` over the artifact."""
    mute = stale_reads()
    sets = {s["span_id"] for s in diag.build_set(include_sealed=True)}
    return [o for o in diag._lines(OUT)
            if o.get("kind") == "read" and o.get("span_id") in sets and read_key(o) not in mute]


def stale_spans():
    """{span_id: n_void} for spans that lost their reads and have NOT got them back.

    Span-level "void" is not "appears in the mute set". A span whose crop was re-cut and then re-read
    has live evidence and no void problem; the contact sheet counted it as re-run scope anyway, which
    is how p423:n3 and p726:n3 would have appeared as unsent work the day after they were sent."""
    mute = stale_reads()
    alive = {o["span_id"] for o in live_reads()}
    n = {}
    for sid, _m, _h in mute:
        if sid not in alive:
            n[sid] = n.get(sid, 0) + 1
    return n


def _no_hebrew_outbound(body):
    """Raise if any Hebrew character is anywhere in the request body. Called before every send.

    The leak this guards is not hypothetical: 11 spans carry the signed truth inside the note line
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
    # offnet: these bytes go to openrouter.ai. The gate refuses anything that is not an A2 span-box
    # crop, so the A2-only rule no longer depends on `cells()` being the only caller.
    img = diag.b64_gated(cpath, what="frontier crop", offnet=True)
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
        # The pixels this read speaks for. Not the span id, not the fault table, not the date: the
        # bytes. Everything downstream that decides whether this row is still evidence reads this.
        "crop_sha16": crop_sha(cpath), "crop_path": str(cpath),
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


def plan(spans=None):
    cat = catalog(refresh=False)["models"]
    cs = cells(spans)
    px = sum((lambda wh: wh[0] * wh[1])(Image.open(c).size) for _s, c, _x in cs)
    img_tok = px / 750.0
    txt_tok = sum(len(PROMPT_HEAD + x + PROMPT_TAIL) for _s, _c, x in cs) / 4.0
    tin, tout = img_tok + txt_tok, len(cs) * 40
    print(f"spans (A2 only) : {len(cs)}   images per request: 1   note-box crops sent: 0")
    if spans:
        print(f"span scope      : {' '.join(sorted(spans))}   (--span; everything else is untouched)")
    for s, c, _x in cs:
        print(f"    {s['span_id']:10s} {str(Image.open(c).size):12s} sha {crop_sha(c)}")
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
        # The population probe() extrapolates over, measured now rather than written down: the
        # literal 18 it replaced priced a run that no longer exists.
        _n = len(cells())
        for m in ARMS:
            c = cat.get(m, {})
            if c.get("status") != "ok":
                continue
            per = ti / 1e6 * c["prompt_per_mtok"] + to / 1e6 * c["completion_per_mtok"]
            # Derived, never a literal: a hardcoded span count prices a run nobody is doing.
            print(f"  {m:40s} {_n} spans ~${per*_n:6.3f}   per 1000 spans ~${per*1000:8.2f}")


SHEET = diag.CROPDIR.parent / "contact_sheet_20260927.json"


def truth_digest():
    """One sha16 over both truth tables, strings AND bases, canonically ordered.

    Bases are in it on purpose. A basis that changes with the string unchanged is still a change of
    standard -- p726:n3 moved from "scorable because I read a prose verdict as being about markers" to
    "scorable because Chris signed the Hebrew" -- and a digest that ignored it would report two runs as
    scored against the same table when they were not."""
    tbl = {k: list(v) for k, v in list(diag.TRUTH.items()) + list(diag.SEALED_TRUTH.items())}
    return diag_sha(json.dumps(tbl, ensure_ascii=False, sort_keys=True))


def truth_sent(cs):
    """The signed string and basis for each span this run sends, so a score is answerable per span."""
    return {s["span_id"]: {"truth": s["truth"], "basis": s["truth_basis"]} for s, _c, _x in cs}


def clip_status(cs):
    """span_id -> the cut this run's crops carry, as the mapper recorded it at cut time.

    The crop hash makes a run answerable for its pixels and cannot see this: a clipped crop is a
    perfectly valid PNG and hashes like any other. So the one thing a hash cannot say about a crop --
    that part of the box was amputated before the pixels were cut -- gets its own field."""
    cut = {}
    for c in diag.clipped():
        if c["aperture"] == APERTURE:
            cut.setdefault(c["span_id"], []).append(
                {"rect_i": c["rect_i"], "edge": c["edge"], "over": c["over"]})
    return {s["span_id"]: cut[s["span_id"]] for s, _c, _x in cs if s["span_id"] in cut}


def clip_gate(cs, rec):
    """Refuse to send a crop whose amputation differs from the one the sheet showed.

    NOT a refusal to send a clipped crop. A box cut back to real page content may be the crop we want,
    and that is a box judgement -- Chris's, not a gate's. What the gate owns is that nobody is asked to
    approve pixels without being told they were cut, and that the answer cannot change afterwards. Both
    directions are refusals: a crop that STOPPED being clipped is also not the crop that was approved.

    Sheets built before this field existed have no answer to compare against, so they are let through
    with a console note rather than refused on a difference nobody could have recorded."""
    shown = rec.get("clipped")
    live = clip_status(cs)
    if shown is None:
        if live:
            raise RuntimeError(
                "the sheet predates the clip field and %d crop(s) in this scope ARE clipped: %s. "
                "Rebuild the sheet so the cut is on the page Chris approves."
                % (len(live), " ".join(sorted(live))))
        print("  note: this sheet predates the clip field; no crop in scope is clipped, so there is "
              "nothing it could have failed to show.")
        return live
    if {k: sorted(map(repr, v)) for k, v in shown.items()} != \
       {k: sorted(map(repr, v)) for k, v in live.items()}:
        raise RuntimeError(
            "clip gate REFUSED: the cut on these crops is not the cut the sheet showed. "
            "sheet=%s now=%s. A clipped crop hashes like any other, so the hash gate cannot catch "
            "this; rebuild the sheet and have it approved on what the crops now show."
            % (json.dumps(shown, ensure_ascii=False), json.dumps(live, ensure_ascii=False)))
    return live


def sheet_gate(cs, sheet=SHEET):
    """Refuse to send a crop the contact sheet did not show. Returns the sheet record for the header.

    Chris's rule is "produce a contact sheet ... Chris approves it, then spend". The approval itself is
    a human act and no check can stand in for it. What a check CAN do is guarantee that the pixels
    approved are the pixels sent -- including when a crop is re-cut in between, which is exactly the
    accident this week was spent cleaning up."""
    if not sheet.exists():
        raise RuntimeError(f"no contact sheet at {sheet.name} -- run hebrew_contact_sheet.py first. "
                           "Chris approves the sheet, then we spend; there is no path around it.")
    rec = json.loads(sheet.read_text(encoding="utf-8"))
    shown = rec.get("crop_sha16") or {}
    bad = {}
    for s, c, _x in cs:
        sid, h = s["span_id"], crop_sha(c)
        if sid not in shown:
            bad[sid] = "not on the contact sheet"
        elif shown[sid] != h:
            bad[sid] = f"crop changed since the sheet: shown {shown[sid]}, now {h}"
    if bad:
        raise RuntimeError("contact-sheet gate REFUSED %d span(s): %s"
                           % (len(bad), json.dumps(bad, ensure_ascii=False)))
    return rec


def run(only=None, spans=None, approved=False, sheet_path=None):
    cs = cells(spans)
    # Gate BEFORE the catalog pull, so a refusal costs nothing and cannot be mistaken for a run that
    # started. --approved records a human claim; the sheet gate verifies the pixels. Neither substitutes
    # for the other, and the header says which is which.
    sheet = sheet_gate(cs, sheet_path or SHEET)
    # Second gate, same principle, different property: the hash proves the pixels, this proves that
    # what was cut away from them was on the page Chris approved. Also before the catalog pull.
    _clip = clip_gate(cs, sheet)
    # Recorded, never enforced: the approval was about pixels, and the truth table is not a pixel.
    # A mismatch is a fact about the run, so it goes in the header and on the console; it is not a
    # reason to refuse a send Chris authorised on what the crops show.
    _td_sheet, _td_now = sheet.get("truth_digest"), truth_digest()
    if _td_sheet and _td_sheet != _td_now:
        print(f"  note: the truth table moved since the sheet was built ({_td_sheet} -> {_td_now}). "
              "The crops are unchanged, which is what the approval was about; both digests are "
              "recorded in the header.")
    if not approved:
        raise RuntimeError(
            "refusing to spend: pass --approved to record that Chris approved "
            f"{sheet['sheet']} ({len(cs)} span(s), {sheet.get('calls_if_approved')} calls). "
            "The flag is a RECORDED CLAIM, not a verification -- the sheet gate has already checked "
            "that the crops match; only a human can check that they are the right crops.")
    # THIRD GATE: archive the pixels before spending on them. Chris's ruling, 2026-09-28.
    #
    # The 26 calls on p912:n2 at 07:32 produced reads whose `crop_sha16` pointed at exactly one file,
    # the live crop, which the next re-cut of that span would have overwritten. The hash would have
    # survived in the header and stopped resolving to anything. A run is answerable for its pixels
    # only while the pixels exist.
    #
    # Before the catalog pull, with the other gates, so a failure to archive costs nothing; and before
    # the header, so the `crop_sha16` map the header records is a map of things already preserved
    # rather than a promise about them.
    _arch = {s_["span_id"]: diag.sent_archive_put(c_, s_["span_id"], APERTURE,
                                                  why="frontier run %s" % time.strftime("%Y-%m-%dT%H:%M:%S"))
             for s_, c_, _x in cs}
    print(f"  archived {len(_arch)} pixel state(s) under their hashes -> {diag.SENT_SHA.name}")

    cat = catalog(refresh=True)
    done = set()
    if OUT.exists():
        # A truncated or empty read is NOT done: it must be retried at the larger cap, or the artifact
        # keeps a budget artifact where a reading belongs.
        # Nor is a read on a crop we no longer hold: resume must not skip a cell on the strength of a
        # read taken off different pixels. This is what makes the scope self-correcting -- a plain
        # `run` after a re-cut re-takes exactly the spans whose crops moved, with or without --span.
        # PER READ, not per cell. A cell that holds a dead read from before a re-cut AND a live read
        # from after it is DONE -- the live read is evidence about the crop we hold. Testing the cell
        # instead put the dead read's staleness over the live read and would have re-sent 52 paid-for
        # cells on p423:n3 and p726:n3 the day after they were approved and sent.
        mute = set(stale_reads())
        done = {(o["span_id"], o["model"]) for o in diag._lines(OUT)
                if o.get("kind") == "read" and o.get("finish_reason") != "length"
                and (o.get("hebrew") or "").strip()
                and read_key(o) not in mute}
    # ONE HEADER PER RUN, not per file. `not OUT.exists()` made the header a property of the
    # artifact instead of the run, so the 23:17 send on 2026-09-27 appended 104 reads under the 12:25
    # run's header and its own identity -- git state, approval, truth digest, crop hashes, clip status
    # -- was never written. The per-read crop_sha16 kept the pixels answerable; nothing kept the RUN
    # answerable. A file holding several runs is a log of runs; each needs its own bracket.
    _reads_before = sum(1 for _o in diag._lines(OUT) if _o.get("kind") == "read") if OUT.exists() else 0
    # RunWriter is the guard behind the comment above: it refuses to write a row until a header has
    # been written, so `write_header` cannot be made conditional again by anybody, including me.
    with RunWriter(OUT) as f:
        hdr = build_header(host=HOST, port=PORT, model="multi:26-openrouter-arms",
                           digest_fn=lambda hp, mo, t=None: "n/a:hosted-api",
                           identity_extra={"aperture": APERTURE, "n_scorable": len(cs),
                                           "arms": ARMS, "prompt_sha16": diag_sha(PROMPT_HEAD +
                                                                                 PROMPT_TAIL),
                                           # Chris's rule: record the hash of every crop sent, in
                                           # the run header. A run is then answerable for exactly
                                           # the pixels it paid for.
                                           "crop_sha16": {s["span_id"]: crop_sha(c)
                                                          for s, c, _x in cs},
                                           # Each of those hashes resolves to a file in the by-sha archive, written BEFORE this
                                           # header. Recorded so a later reader need not take the directory on trust.
                                           "crops_archived": _arch,
                                           "crops_archive": diag.SENT_SHA.name,
                                           # Chris's rule, 2026-09-27: the header records the
                                           # truth in force AT SEND. The crop hash makes the run
                                           # answerable for its pixels; this makes it answerable
                                           # for the standard those pixels were scored against.
                                           # Both halves, or a run can be silently re-scored.
                                           "truth_digest": truth_digest(),
                                           "truth_digest_at_sheet": sheet.get("truth_digest"),
                                           # Where this run's reads begin in an artifact that
                                           # already held other runs' reads. A number, so the
                                           # boundary does not depend on reading footers in order.
                                           "appends_to_existing": _reads_before > 0,
                                           "reads_before": _reads_before,
                                           "truth_sent": truth_sent(cs),
                                           # {} means no crop in this run was amputated. Recorded
                                           # either way: absence of the field would be silence,
                                           # and silence is what the flag was already getting.
                                           "clipped_sent": _clip,
                                           "span_scope": sorted(spans) if spans else "ALL",
                                           "contact_sheet": sheet["sheet"],
                                           "contact_sheet_built": sheet.get("built"),
                                           "approval": "recorded claim via --approved; "
                                                       "human approval is NOT machine-verifiable"},
                           extra={"privacy": {"request_filter": "provider.data_collection=deny",
                                              "account_toggle": "not-readable-via-api",
                                              "verified": "per-request filter only; "
                                                          "account toggle NOT verifiable via API"},
                                  "catalog_pulled": cat["pulled"],
                                  "budget_before": _budget(),
                                  "note_box_crops_sent": 0,
                                  "text_context": "latin_context with Hebrew runs replaced by U+2022",
                                  "pages": "FILE pages (printed = file - 88)"})
        f.header(hdr, "frontier run")   # calls require_endpoint, then writes it FIRST
        for model in (only or ARMS):
            c = cat["models"].get(model, {})
            if c.get("status") != "ok":
                f.row({"kind": "arm_skipped", "model": model,
                                    "why": c.get("status", "ABSENT")})
                print(f"SKIP {model}: {c.get('status')}")
                continue
            print(f"\n== {model}")
            from run_header import _git_head, _git_dirty
            f.row({"kind": "arm_header", "model": model, "started": time.strftime("%H:%M:%S"),
                                "git_head": _git_head(), "git_dirty": _git_dirty(),
                                "pricing": {k: c[k] for k in ("prompt_per_mtok", "completion_per_mtok",
                                                              "image_per_1k")},
                                "structured": c["structured"]})
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
                f.row(row)          # RunWriter flushes every row itself
                tag = row.get("kind")
                print(f"  {s['span_id']:10s} {tag:10s} {str(row.get('gated', row.get('error','')))[:44]!r}"
                      f" {row.get('provider_served') or ''}")
        f.row({"kind": "run_footer", "budget_after": _budget(),
                            "finished": time.strftime("%Y-%m-%dT%H:%M:%S")})
    print("\nwrote", OUT)


def diag_sha(t):
    import hashlib
    return hashlib.sha256(t.encode()).hexdigest()[:16]


def rows():
    """Scored read rows. Classification is diag.classify against the signed truth — nothing else."""
    sets = {s["span_id"]: s for s in diag.build_set(include_sealed=True)}
    # LAST row per (span, model) wins. A retried cell appends rather than overwriting, so without this
    # a retry would be counted twice -- once as the truncated artifact and once as the real read.
    # A read that is no longer about a crop we hold is dropped from scoring entirely. Dropping it is
    # not a silent loss: `score` prints the tally, and a span with stale reads and no fresh ones is
    # reported as RE-RUN SCOPE rather than as a span no arm read.
    mute = stale_reads()
    keep = {}
    for o in diag._lines(OUT):
        if o.get("kind") != "read" or o.get("span_id") not in sets:
            continue
        # The read is dropped for ITS OWN pixels. Dropping the whole cell discarded 52 reads that had
        # been approved, sent and paid for, because an older read on the retired crop shared the cell.
        if read_key(o) in mute:
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
    n = len({s["span_id"] for s, _c, _x in cells()})
    print(f"A2 aperture only, n={n} scorable (FILE pages; printed = file - 88)")
    mute = stale_reads()
    if mute:
        by = {}
        for (sid, _m, _h), why in mute.items():
            by.setdefault(sid, []).append(why)
        scored = {o["span_id"] for o in rs}
        sendable = {s["span_id"] for s, _c, _x in cells()}
        print(f"  {len(mute)} read(s) VOID on {len(by)} span(s): the crop was re-cut after the read.")
        for sid in sorted(by):
            # Three different states, and only one of them is a task. A span whose crop is REFUSED
            # cannot be re-run at all: its reads are gone and there is no route back until the box is
            # redrawn. Printing that as "re-run scope" would file a permanent debt as a queued job.
            tag = ("re-scored on fresh reads" if sid in scored else
                   "RE-RUN SCOPE, currently unscored" if sid in sendable else
                   "DEBT: crop refused, cannot be re-run until the box is redrawn")
            print(f"    {sid:10s} {len(by[sid]):3d} void  {tag}")
    print()
    print(f"{'model':40s} {'exact':>5s} {'nik':>4s} {'wrong':>5s} {'abst':>4s} {'trunc':>5s} "
          f"{'n':>3s}  {'ex/bt':>6s} {'ex/no-bt':>8s}")
    _sc = {o["span_id"]: o for o in rs}
    _bt = sum(1 for o in _sc.values() if o["gloss_backtranslatable"])
    print(f"{'':40s} {'':5s} {'':4s} {'':5s} {'':4s} {'':5s} {'':3s}  "
          f"bt = gloss back-translatable ({_bt} spans); no-bt ({len(_sc) - _bt})")
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


def crop_ink_state(sha16, span_id=None):
    """What the pixels a read was SHOWN actually contained: "BLANK", "INK", or None for unknowable.

    Chris's law for the production path, 2026-10-04: *a read is evidence only about a crop that passed
    the input guard.* The proof is on `p423:n3` -- one arm returned the exact signed string
    `ותגע לרגליו` from a crop containing no ink at all, so a correct-looking answer is not evidence that
    anything was read. No output-side check can catch that, which is why the guard has to be on the
    input and why this function exists on the pixel side of the question.

    The third state is the point. `None` means UNKNOWABLE -- a read taken before `crop_sha16` was
    stamped cannot be tied to any pixels, so "blank" and "inked" are both unavailable claims about it,
    and reporting it as either is the fabrication this whole file is about. The previous version of the
    control had no such state: it selected on `"crop-fault" in unscorable`, which is a tag about a BOX,
    and then printed "no ink was sent; these arms were shown nothing" over it. Its one member was
    `p900:n4`, whose fault is `out-of-strip` and whose crop is 238x86 with extrema (0, 255) -- ink. The
    control assserted what 26 arms were shown and was wrong about it, which is
    [[a-blank-channel-is-not-an-absent-input]] running in reverse."""
    p = None
    if sha16:
        q = diag.SENT_SHA / (sha16 + ".png")
        if q.exists():
            p = q
    if p is None:
        # No hash on the read -- but that is not automatically unknowable. `stale_read_why` keeps a
        # pre-hash read LIVE only when its span's crop was never re-cut, and for such a span the crop
        # on disk IS the crop that read was shown. Resolving it here is what separates "we cannot say"
        # from "we never wrote it down", and only the first deserves to suppress a finding.
        if span_id is None or span_id in set(diag.crops_changed(APERTURE)):
            return None
        q = diag.CROPDIR / ("%s_%s.png" % (span_id.replace(":", "_"), APERTURE))
        if not q.exists():
            return None
        p = q
    try:
        lo, hi = Image.open(p).convert("L").getextrema()
    except Exception:
        return None
    return "BLANK" if lo == hi else "INK"


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
    # VOID READS ARE DROPPED HERE. This table ignored `stale_read_why` until 2026-10-04 and therefore
    # tallied 20 spans where `score()` tallied 19: all 26 of `p900:n4`'s reads are about a rectangle
    # that no longer exists, and they were being published as that span's support distribution. Same
    # defect as `contains_counts()`, found the same way -- by two counters disagreeing about n.
    mute = stale_reads()
    keep, voided = {}, {}
    for o in diag._lines(OUT):
        if o.get("kind") != "read" or o.get("span_id") not in sets:
            continue
        if o.get("model") in diag.DROPPED_ARMS:
            continue
        if read_key(o) in mute:
            voided[o["span_id"]] = voided.get(o["span_id"], 0) + 1
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
    if voided:
        print(f"\n{sum(voided.values())} read(s) VOID and excluded from the table above "
              f"(the crop was re-cut after the read):")
        for sid in sorted(voided):
            tail = "" if sid in keep else "   -- this span has NO live read, so it is absent above"
            print(f"    {sid:10s} {voided[sid]:3d} void{tail}")

    # The control, derived from the pixels each read recorded rather than from a tag about its box.
    print("\ninput-guard control -- what the PIXELS were, taken from the by-sha archive:")
    rows_ = []
    for sid in sorted(keep):
        st = collections.Counter()
        for _m, o in keep[sid].items():
            st[crop_ink_state(o.get("crop_sha16"), sid) or "UNKNOWABLE"] += 1
        if "BLANK" in st or "UNKNOWABLE" in st:
            rows_.append((sid, st))
    if not rows_:
        print("    none: every live read names an archived crop that carries ink")
    for sid, st in rows_:
        per = keep[sid]
        ab = sum(1 for _m, o in per.items()
                 if diag.classify(o.get("gated") or "", sets[sid]["truth"]) == "abstain")
        ex = sum(1 for _m, o in per.items()
                 if diag.classify(o.get("gated") or "", sets[sid]["truth"]) in ("exact", "punct-only"))
        print(f"    {sid:10s} {dict(st)}  {ab}/{len(per)} abstained, {ex} EXACT")
        if st.get("BLANK") and ex:
            print(f"      ^^ {ex} exact read(s) on a crop with NO INK. A correct string is not "
                  f"evidence that anything was read -- gate the INPUT.")

    # THE PROOF, over every read in the artifact including the void ones. It has to be stated here and
    # not left to a report, because the reads that carry it are void -- their crop was re-cut after the
    # blank was sent -- and a control that only looks at live reads would lose the one measurement that
    # establishes why an input guard is not optional. Chris's law, 2026-10-04: a read is evidence only
    # about a crop that passed the input guard.
    blank_sha = {}
    for p_ in sorted(diag.SENT_SHA.glob("*.png")):
        try:
            lo, hi = Image.open(p_).convert("L").getextrema()
        except Exception:
            continue
        if lo == hi:
            blank_sha[p_.stem] = Image.open(p_).size
    print("\nblank crops EVER sent, and what the arms did with nothing (void reads included):")
    if not blank_sha:
        print("    none archived")
    for sha, size in blank_sha.items():
        hits = [o for o in diag._lines(OUT)
                if o.get("kind") == "read" and o.get("crop_sha16") == sha]
        sid = hits[0].get("span_id") if hits else None
        if not hits:
            # The blank sends predate `crop_sha16`, so no read names them by hash. The archive index
            # does record which span each archived state came from, and `stale_read_why` records which
            # reads are about a retired crop -- so the attribution is recoverable from two things the
            # tree already holds, and the proof does not have to live in a report. A span may only be
            # attributed this way when the blank is its ONLY retired state; otherwise the pre-hash reads
            # cannot be apportioned between two retired crops and the honest answer is to say so.
            sid = next((r.get("span_id") for r in diag.sent_archive_index()
                        if r.get("sha16") == sha), None)
            retired = {r["sha16"] for r in diag.sent_archive_index()
                       if r.get("span_id") == sid} - {diag.crop_sha(sid, APERTURE)} if sid else set()
            hits = [o for o in diag._lines(OUT)
                    if o.get("kind") == "read" and o.get("span_id") == sid
                    and not o.get("crop_sha16") and read_key(o) in mute]
            if not sid or len(retired) != 1 or not hits:
                print(f"    {sha[:16]} {size}  attribution unavailable "
                      f"({len(retired)} retired states for {sid}, {len(hits)} pre-hash void reads)")
                continue
        t = sets[sid]["truth"] if sid in sets else ""
        ab = sum(1 for o in hits if diag.classify(o.get("gated") or "", t) == "abstain")
        ex = sum(1 for o in hits if diag.classify(o.get("gated") or "", t) in ("exact", "punct-only"))
        print(f"    {sha[:16]} {size} {sid}: {len(hits)} reads, {ab} ABSTAIN, {ex} EXACT on no ink")


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
    # --span p423:n3,p726:n3   or   --span p423:n3 --span p726:n3
    sv = [x for i, t in enumerate(a) if t == "--span" for x in a[i + 1].split(",") if x] or None
    if cmd == "catalog":
        c = catalog(refresh=True)
        for k, v in c["models"].items():
            print(f"  {k:40s} {v['status']:9s} in {v.get('prompt_per_mtok', 0):8.3f} "
                  f"out {v.get('completion_per_mtok', 0):8.3f} struct={v.get('structured')}")
        print("pulled", c["pulled"], "->", CATALOG)
    elif cmd == "plan":
        plan(sv)
    elif cmd == "probe":
        probe(mv or ARMS[-1])
    elif cmd == "run":
        # --sheet: the contact sheet this send was approved against. A sheet is an approval
        # record, not a scratch file -- the header stores its name, so an earlier run's header must
        # keep pointing at the scope that was actually approved for it.
        shv = Path(a[a.index("--sheet") + 1]) if "--sheet" in a else None
        run([mv] if mv else None, sv, approved="--approved" in a, sheet_path=shv)
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
