"""Lane B item 1(f) - frontier-model runner for the IDENTICAL crop-vs-model Hebrew set. BUILT, NOT CALLED.

It reads the crops `hebrew_aperture_diag.crops()` already wrote, sends the SAME two-image prompt
(`hebrew_recrop._RECROP_PROMPT`, context strip + aperture crop), and writes a JSONL that
`hebrew_aperture_diag.score()` scores with the same classifier. The only variable versus the local run is
the model, which is the point: if aperture is not the term that matters locally, this asks whether the
READER is - on the same pixels, the same prompt, the same signed truth.

Chris has Max, not API credits (see goatyard_advisor_handoff_20260920.md). This therefore ships with:
  - NO key in code and no key discovery: it reads one env var and refuses otherwise;
  - a `plan` mode that prints the exact request shape, the image byte counts and a cost estimate
    WITHOUT making a network call - run this first;
  - `run` gated behind an explicit --i-have-a-key flag so it cannot fire by accident.

Providers: `anthropic` (default) or `openrouter`. Which one is Chris's call, not made here.

Usage:  python hebrew_aperture_frontier.py plan
        python hebrew_aperture_frontier.py run --i-have-a-key        # needs FRONTIER_API_KEY
        python hebrew_aperture_frontier.py score
"""
import base64, io, json, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import httpx
from hebrew_recrop import _RECROP_PROMPT
import hebrew_aperture_diag as diag

OUT = diag.DATA / "hebrew_aperture_frontier_reads_20260920.jsonl"
KEY_ENV = "FRONTIER_API_KEY"

# Per-provider request shape. Model ids are defaults, overridable with --model; nothing here pins a
# commercial choice. Prices are USD per million tokens and are ESTIMATES for the plan output only -
# they are not authoritative and must be checked against the provider's current page before spending.
PROVIDERS = {
    "anthropic": dict(
        url="https://api.anthropic.com/v1/messages",
        model="claude-opus-5",
        headers=lambda k: {"x-api-key": k, "anthropic-version": "2023-06-01",
                           "content-type": "application/json"},
        est_in=5.0, est_out=25.0),
    "openrouter": dict(
        url="https://openrouter.ai/api/v1/chat/completions",
        model="anthropic/claude-opus-4.1",
        headers=lambda k: {"Authorization": f"Bearer {k}", "content-type": "application/json"},
        est_in=5.0, est_out=25.0),
}


def _b64_file(p):
    return base64.b64encode(Path(p).read_bytes()).decode()


def _body(prov, model, ctx_b64, crop_b64):
    """Two images then the instruction, in the same order the local /api/generate call sends them."""
    if prov == "anthropic":
        return {"model": model, "max_tokens": 256, "temperature": 0,
                "messages": [{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                 "data": ctx_b64}},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                 "data": crop_b64}},
                    {"type": "text", "text": _RECROP_PROMPT}]}]}
    return {"model": model, "max_tokens": 256, "temperature": 0,
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{ctx_b64}"}},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{crop_b64}"}},
                {"type": "text", "text": _RECROP_PROMPT}]}]}


def _text(prov, d):
    if prov == "anthropic":
        return "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text").strip()
    return (d["choices"][0]["message"]["content"] or "").strip()


def _cells():
    """(span, aperture, context_path, crop_path) for every cell the local run covers - same set, same order."""
    man = json.load(io.open(diag.CROPDIR / "manifest.json", encoding="utf-8"))
    for s in man:
        for ap in ("A1_notebox", "A2_spanbox"):
            if s.get(ap):
                yield s, ap, s["context_strip"], s[ap]["path"]


def plan(prov, model):
    """No network call. Prints what would be sent and a rough bill."""
    cells = list(_cells())
    px = 0
    for _s, _ap, c, k in cells:
        for p in (c, k):
            from PIL import Image
            w, h = Image.open(p).size
            px += w * h
    # ~750 px per image token is the common rule of thumb; deliberately labelled an estimate.
    img_tok = px / 750.0
    txt_tok = len(cells) * len(_RECROP_PROMPT) / 4.0
    tin = img_tok + txt_tok
    tout = len(cells) * 40
    cfg = PROVIDERS[prov]
    cost = tin / 1e6 * cfg["est_in"] + tout / 1e6 * cfg["est_out"]
    print(f"provider   : {prov}\nmodel      : {model}\nendpoint   : {cfg['url']}")
    print(f"cells      : {len(cells)}  ({len({s['span_id'] for s, *_ in cells})} spans x apertures)")
    print(f"images     : {2 * len(cells)} (context strip re-sent per cell, as the local run does)")
    print(f"est tokens : in ~{tin:,.0f}  out ~{tout:,.0f}")
    print(f"est cost   : ~${cost:,.2f}  <-- ESTIMATE ONLY; verify current prices before spending")
    print(f"key        : env {KEY_ENV} {'SET' if os.getenv(KEY_ENV) else 'NOT set'}")
    print(f"writes     : {OUT}")
    print("\nfirst cell request skeleton (images elided):")
    s, ap, c, k = cells[0]
    b = _body(prov, model, "<ctx-b64>", "<crop-b64>")
    print(json.dumps(b, ensure_ascii=False, indent=1)[:700])
    print(f"\n  span {s['span_id']} aperture {ap}\n  ctx  {c}\n  crop {k}")


def run(prov, model):
    key = os.getenv(KEY_ENV)
    if not key:
        sys.exit(f"refusing to run: env {KEY_ENV} is not set")
    cfg = PROVIDERS[prov]
    done = set()
    if OUT.exists():
        done = {(o["span_id"], o["aperture"]) for o in diag._lines(OUT) if "span_id" in o}
    with io.open(OUT, "a", encoding="utf-8") as f:
        if not done:
            f.write(json.dumps({"kind": "config_header", "provider": prov, "model": model,
                                "endpoint": cfg["url"], "temperature": 0, "max_tokens": 256,
                                "prompt_head": _RECROP_PROMPT[:40],
                                "prerun": "hebrew_aperture_prerun_20260920.md",
                                "date": time.strftime("%Y-%m-%d")}, ensure_ascii=False) + "\n")
        for s, ap, cpath, kpath in _cells():
            if (s["span_id"], ap) in done:
                continue
            t0 = time.time()
            r = httpx.post(cfg["url"], headers=cfg["headers"](key),
                           json=_body(prov, model, _b64_file(cpath), _b64_file(kpath)), timeout=300)
            r.raise_for_status()
            raw = _text(prov, r.json())
            from PIL import Image
            crop = Image.open(kpath).convert("L")
            gated, nik, dens = diag.nikud_gate.gated_strip(raw, crop)
            sv, sr = diag.script_gate.gate(gated, s["latin_context"])
            f.write(json.dumps({"span_id": s["span_id"], "aperture": ap, "model": f"{prov}:{model}",
                                "raw": raw, "gated": gated, "nikud_verdict": nik,
                                "nikud_density": round(float(dens), 3), "script_verdict": sv,
                                "script_reason": sr, "secs": round(time.time() - t0, 1)},
                               ensure_ascii=False) + "\n")
            f.flush()
            print(f"  {s['span_id']:10s} {ap:11s} {raw[:48]!r}", flush=True)
    print("wrote", OUT)


def score():
    rows = [o for o in diag._lines(OUT) if "span_id" in o]
    sets = {s["span_id"]: s for s in diag.build_set()}
    for o in rows:
        s = sets[o["span_id"]]
        o["cls"] = "UNSCORABLE" if s["unscorable"] else diag.classify(o["gated"], s["truth"])
    return rows


if __name__ == "__main__":
    a = sys.argv[1:]
    cmd = a[0] if a else "plan"
    prov = a[a.index("--provider") + 1] if "--provider" in a else "anthropic"
    model = a[a.index("--model") + 1] if "--model" in a else PROVIDERS[prov]["model"]
    if cmd == "plan":
        plan(prov, model)
    elif cmd == "run":
        if "--i-have-a-key" not in a:
            sys.exit("refusing to run without --i-have-a-key (this spends money). Run `plan` first.")
        run(prov, model)
    elif cmd == "score":
        for o in score():
            print(f"{o['span_id']:10s} {o['aperture']:11s} {o['cls']:11s} {o['gated'][:40]!r}")
