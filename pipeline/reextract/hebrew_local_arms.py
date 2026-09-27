"""Local vision arms for the Hebrew span diagnostic, on endpoint D. Chris's amendment, 2026-09-20.

    python hebrew_local_arms.py crops
    python hebrew_local_arms.py run --host 192.168.1.169:11435 --model glm-ocr:bf16
    python hebrew_local_arms.py score
    python hebrew_local_arms.py matrix

WHAT THIS ADDS. `hebrew_aperture_diag.py` ran two models on endpoint C over the 10 non-sealed signed spans.
This runs four more LOCAL models on endpoint D (`192.168.1.169:11435`, the Strix Halo iGPU) over **n=19** --
the same signed sitting with its sealed half restored under ruling 2's carve-out. Same crops, same two
apertures, scored against SIGNED verdicts only. **No data leaves the network.** Page numbers are FILE pages
(printed = file - 88).

WHY A SEPARATE MODULE. The n=10 result on C was produced by `hebrew_aperture_diag.read_one`, which posts to
`/api/generate` on a hardcoded `:11434`. That function produced a recorded artifact, so it is left byte-stable;
this module owns the D read path and every difference from it is explicit and in the header:

  - **`/api/chat` with `"think": false`, natively.** Ollama's OpenAI-compatible `/v1` route DROPS the think
    toggle, and prompting `/no_think` leaves qwen3 thinking about 20% of the time. Only the native route
    turns it off for certain. This is a DIFFERENT READ PATH from the C arms, which is why the two are never
    subtracted from each other below -- see the reporting rule in the scope note.
  - **host:PORT everywhere.** C and D are the same IP on different ports. A hardcoded `:11434` would have
    silently run every "D" arm on C and produced a result that looked fine and meant nothing.

THE VRAM GUARD, AND WHY IT IS AN ABORT AND NOT A WARNING. A model that does not fit spills to CPU and still
answers -- slowly, and with a different numeric path. That is a silent confound of exactly the kind this
lane keeps finding. So each arm loads its model with the real options, then reads `/api/ps`: if
`size_vram/size` is below VRAM_MIN the arm is ABORTED before a single span is read, and the abort is
recorded. One model at a time; the previous model is unloaded (`keep_alive: 0`) before the next loads.

SCOPE -- what this cannot tell you. It measures READS against signed verdicts on 19 spans. Cross-endpoint
and cross-read-path comparison is NOT scoring: the C arms and the D arms differ in device AND API route, and
Chris's device-noise rule (handoff section 11c) puts differences of ~3 spans or fewer inside the noise floor.
The agreement matrix is therefore reported as agreement -- do two models produce the same string -- and never
as one model beating another across endpoints. The frontier arm stays built and UNCALLED."""
import argparse
import base64
import io
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import httpx
from PIL import Image

import hebrew_aperture_diag as D
import nikud_gate
import script_gate
from endpoint_guard import resolve_host, EndpointMissing, EndpointRefused
from run_header import build_header, endpoint_id, model_digest, normalize_hostport
from hebrew_recrop import _RECROP_PROMPT

DATA = D.DATA
OUT = DATA / "hebrew_local_arms_reads_20260920.jsonl"
PRERUN = DATA / "hebrew_local_arms_prerun_20260920.md"
ARMS = [m for m in ["qwen3.5:122b", "glm-ocr:bf16", "nemotron3:33b", "qwen3.8:latest"]
        if m not in D.DROPPED_ARMS]        # glm-ocr dropped 2026-09-27, see D.DROPPED_ARMS
APERTURES = ("A1_notebox", "A2_spanbox")
NUM_CTX = D.NUM_CTX
VRAM_MIN = 0.98        # size_vram/size. Below this the model spilled to CPU and the arm is aborted.
KEEP_ALIVE = "30m"


def _b64(im, what=""):
    """GATED. The local arms are cheap, which is exactly why they were shown blank crops most often;
    cheap is not a reason to send a white rectangle to a model."""
    return D.b64_gated(im, what=what)


def _opts():
    return {"num_ctx": NUM_CTX, "temperature": 0}


def read_one(hostport, model, context_strip, crop):
    """Native /api/chat, thinking off, temperature 0, two images: context strip then the aperture crop."""
    t0 = time.time()
    r = httpx.post(f"http://{hostport}/api/chat",
                   json={"model": model,
                         "messages": [{"role": "user", "content": _RECROP_PROMPT,
                                       "images": [_b64(context_strip), _b64(crop)]}],
                         "think": False, "stream": False, "keep_alive": KEEP_ALIVE,
                         "options": _opts()}, timeout=1800)
    r.raise_for_status()
    d = r.json()
    msg = d.get("message") or {}
    return ((msg.get("content") or "").strip(), d.get("done_reason"),
            (msg.get("thinking") or "").strip()[:200], round(time.time() - t0, 1))


def unload(hostport, model):
    try:
        httpx.post(f"http://{hostport}/api/chat",
                   json={"model": model, "messages": [], "keep_alive": 0}, timeout=120)
    except Exception:
        pass


def residents(hostport):
    """Who else is loaded on this endpoint. Recorded before AND after each load: this box is shared with
    Lane A, an 80 GB load evicts whatever is resident, and Lane A reports that an evicted eval does not
    fail cleanly - it just scores lower. If this run costs someone else their result, it says so."""
    try:
        return [{"name": m.get("name"), "vram_gb": round(float(m.get("size_vram") or 0) / 1e9, 2)}
                for m in httpx.get(f"http://{hostport}/api/ps", timeout=30).json().get("models", [])]
    except Exception as e:
        return [{"error": f"{type(e).__name__}"}]


def vram_check(hostport, model):
    """Load the model with the REAL options, then ask /api/ps whether it actually landed in VRAM.

    Returns (ok, report). A warm-up is required first: /api/ps reports nothing about a model that is not
    loaded, and loading with different options would measure an instance this run never uses."""
    t0 = time.time()
    try:
        httpx.post(f"http://{hostport}/api/chat",
                   json={"model": model, "messages": [{"role": "user", "content": "ping"}],
                         "think": False, "stream": False, "keep_alive": KEEP_ALIVE,
                         "options": _opts()}, timeout=1800).raise_for_status()
    except Exception as e:
        return False, {"stage": "load", "error": f"{type(e).__name__}: {e}"}
    load_s = round(time.time() - t0, 1)
    try:
        ps = httpx.get(f"http://{hostport}/api/ps", timeout=60).json().get("models", [])
    except Exception as e:
        return False, {"stage": "ps", "error": f"{type(e).__name__}: {e}"}
    me = [m for m in ps if m.get("name") == model or m.get("model") == model]
    if not me:
        return False, {"stage": "ps", "error": "model not listed in /api/ps after load",
                       "loaded": [m.get("name") for m in ps]}
    m = me[0]
    size, vram = float(m.get("size") or 0), float(m.get("size_vram") or 0)
    frac = round(vram / size, 4) if size else 0.0
    rep = {"stage": "ps", "size_gb": round(size / 1e9, 2), "size_vram_gb": round(vram / 1e9, 2),
           "vram_frac": frac, "vram_min": VRAM_MIN, "load_s": load_s,
           "others_loaded": [m2.get("name") for m2 in ps if m2 is not m]}
    return frac >= VRAM_MIN, rep


def run(hostport, models, out=OUT, include_sealed=True):
    built = _built(include_sealed)
    done = set()
    if out.exists():
        done = {(o["span_id"], o["aperture"], o["model"]) for o in D._lines(out) if "span_id" in o}
    aborted = []
    with io.open(out, "a", encoding="utf-8") as f:
        for model in models:
            eid = endpoint_id(hostport)
            print(f"\n=== arm {model} on {eid} ({hostport}) ===", flush=True)
            before = residents(hostport)
            ok, rep = vram_check(hostport, model)
            after = residents(hostport)
            evicted = [r["name"] for r in before if r.get("name") not in
                       {a.get("name") for a in after} and r.get("name") != model]
            if evicted:
                print(f"  *** EVICTED another tenant's model: {evicted} ***", flush=True)
            digest = model_digest(hostport, model)
            f.write(json.dumps({"kind": "arm_header", "model": model, "endpoint_id": eid,
                                "endpoint_host": hostport, "model_digest16": digest,
                                "api_path": "/api/chat", "think": False, "temperature": 0,
                                "num_ctx": NUM_CTX, "vram": rep, "vram_ok": ok,
                                "residents_before": before, "residents_after": after,
                                "evicted_other_tenant": evicted,
                                "started": time.strftime("%Y-%m-%dT%H:%M:%S")},
                               ensure_ascii=False) + "\n")
            f.flush()
            print(f"  vram: {rep}", flush=True)
            if not ok:
                # An arm that spilled to CPU is not a slower arm, it is a different arm. Abort it.
                print(f"  ABORTED: spilled to CPU or failed to load -> no spans read", flush=True)
                aborted.append((model, rep))
                unload(hostport, model)
                continue
            n = 0
            for s in built:
                for ap in APERTURES:
                    if not s.get(ap) or (s["span_id"], ap, model) in done:
                        continue
                    crop = Image.open(s[ap]["path"]).convert("L")
                    ctx = Image.open(s["context_strip"]).convert("L")
                    try:
                        raw, dr, think, secs = read_one(hostport, model, ctx, crop)
                        refused = None
                    except D.CropRefused as e:
                        # See hebrew_frontier_or: a refused crop is unscorable, not an error, and it
                        # must not count toward any dead-item rule.
                        raw, dr, think, secs = "", f"REFUSED:{e.fault}", "", 0.0
                        refused = e.fault
                    except Exception as e:
                        raw, dr, think, secs = "", f"ERROR:{type(e).__name__}", "", 0.0
                        refused = None
                    gated, nik, dens = nikud_gate.gated_strip(raw, crop)
                    sv, sr = script_gate.gate(gated, s["latin_context"])
                    f.write(json.dumps({"span_id": s["span_id"], "aperture": ap, "model": model,
                                        "endpoint_id": eid, "endpoint_host": hostport,
                                        "model_digest16": digest, "sealed": s["sealed"],
                                        "raw": raw, "gated": gated, "nikud_verdict": nik,
                                        "crop_fault": refused,
                                        "unscorable": (f"crop-fault:{refused}" if refused else None),
                                        "reached_wire": refused is None,
                                        "nikud_density": round(float(dens), 3), "script_verdict": sv,
                                        "script_reason": sr, "done_reason": dr, "secs": secs,
                                        "thinking_leak": think, "crop_size": s[ap]["size"]},
                                       ensure_ascii=False) + "\n")
                    f.flush()
                    n += 1
                    print(f"  {s['span_id']:10s} {ap:11s} {secs:7.1f}s  {gated[:44]!r}", flush=True)
            print(f"  arm done: {n} reads", flush=True)
            unload(hostport, model)
    if aborted:
        print("\nABORTED ARMS (spilled to CPU / failed to load):")
        for m, rep in aborted:
            print(f"  {m}: {rep}")
    print("\nwrote", out)


def _built(include_sealed):
    """Crops for the run. Only spans with at least one aperture are read; p657:n0 has no ratified span box."""
    return [s for s in D.crops(save=True, include_sealed=include_sealed)
            if s.get("A1_notebox") or s.get("A2_spanbox")]


# ------------------------------------------------------------------ scoring


def score(out=OUT, include_sealed=True):
    sets = {s["span_id"]: s for s in D.build_set(include_sealed=include_sealed)}
    # The single choke point for D-lane scoring: a dropped arm never reaches a tally or the console.
    # Exact match on the model id, so `z-ai/glm-5.3-flash` -- a different arm that never loops -- stays.
    rows = [o for o in D._lines(out) if "span_id" in o and o.get("model") not in D.DROPPED_ARMS]
    for o in rows:
        s = sets.get(o["span_id"])
        if not s:
            o["cls"] = "OUT-OF-SET"
            continue
        o["cls"] = "UNSCORABLE" if s["unscorable"] else D.classify(o["gated"], s["truth"])
    return rows, sets


def _tally(rows):
    """exact / nikud-only / wrong / abstain, with punct-only and contains folded where they belong.

    `punct-only` folds into exact: the signed verdict is about the LETTERS, and a maqaf-vs-hyphen
    difference is not a reading difference.

    `contains` NO LONGER folds into wrong, and neither do `clipped` or `degenerate`. The old rule read
    "extra material around the right letters is still not the printed span" -- true about the string,
    false about the cause. The extra material is in the CROP: p124:n4's ratified box holds two Hebrew
    runs and a Latin word, so an arm that transcribes what it was shown must return more than the
    signature. That is the box being wrong, not the reader. `clipped` is the same defect mirrored
    (p912:n2's box holds one of the signature's two words). `degenerate` is a generation loop and was
    never a reading at all. Charging any of the three to `wrong` grades geometry and decoding as
    misreads, which is exactly the confusion this lane exists to prevent."""
    t = {"exact": 0, "nikud-only": 0, "wrong": 0, "abstain": 0, "unscorable": 0,
         "contains": 0, "clipped": 0, "degenerate": 0}
    for o in rows:
        c = o["cls"]
        if c in ("exact", "punct-only"):
            t["exact"] += 1
        elif c in ("nikud-only", "contains", "clipped", "degenerate"):
            t[c] += 1
        elif c == "abstain":
            t["abstain"] += 1
        elif c == "UNSCORABLE":
            t["unscorable"] += 1
        else:
            t["wrong"] += 1
    return t


def load_c_arms(include_sealed=True):
    """The recorded endpoint-C reads, labelled by endpoint, for the AGREEMENT matrix only.

    These are a different device AND a different API route (/api/generate on C vs /api/chat on D). They are
    carried here so the matrix can answer "do independent readers produce the same string", which is a
    question about the printed page. They are NEVER differenced against the D arms: Chris's device-noise
    rule puts cross-run differences of ~3 spans or fewer inside the floor, and these differ on two axes."""
    if not D.OUT.exists():
        return []
    sets = {x["span_id"]: x for x in D.build_set(include_sealed=include_sealed)}
    out = []
    for o in D._lines(D.OUT):
        if "span_id" not in o or o["span_id"] not in sets:
            continue
        if o.get("model") in D.DROPPED_ARMS:
            continue
        o = dict(o)
        o["endpoint_id"], o["model"] = "C", o["model"] + " (C)"
        s = sets[o["span_id"]]
        o["cls"] = "UNSCORABLE" if s["unscorable"] else D.classify(o["gated"], s["truth"])
        out.append(o)
    return out


def agreement(rows, aperture):
    """Pairwise: over spans BOTH models read, how often is the gated string identical?

    Agreement is not correctness. Unanimity is confidence only over SHARED EVIDENCE, never over shared
    priors - every arm here reads the same two crops, so agreeing on a misread is exactly what they would
    do. The matrix is reported beside the signed verdict, never in place of it."""
    sub = [o for o in rows if o["aperture"] == aperture]
    models = sorted({o["model"] for o in sub})
    by = {}
    for o in sub:
        by.setdefault(o["model"], {})[o["span_id"]] = D._norm(o.get("gated") or "")
    pairs = {}
    for i, a in enumerate(models):
        for b in models[i + 1:]:
            shared = set(by.get(a, {})) & set(by.get(b, {}))
            if not shared:
                continue
            same = sum(1 for sid in shared if by[a][sid] == by[b][sid] and by[a][sid])
            pairs[(a, b)] = (same, len(shared))
    return models, by, pairs


if __name__ == "__main__":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["crops", "run", "score", "matrix"])
    ap.add_argument("--host", default=None,
                    help="REQUIRED for run: endpoint host:PORT, e.g. 192.168.1.169:11435 (D). No default.")
    ap.add_argument("--model", action="append", default=None, help="one arm; repeatable. Default: all four.")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--no-sealed", action="store_true")
    ap.add_argument("--with-c", action="store_true",
                    help="carry the recorded endpoint-C reads into the AGREEMENT matrix (never differenced)")
    a = ap.parse_args()
    include_sealed = not a.no_sealed
    out = Path(a.out)

    if a.cmd == "crops":
        n = 0
        for s in D.crops(save=True, include_sealed=include_sealed):
            a1 = s["A1_notebox"] and s["A1_notebox"]["size"]
            a2 = s["A2_spanbox"] and s["A2_spanbox"]["size"]
            print(f"{s['span_id']:10s} sealed={int(s['sealed'])} A1={a1} A2={a2}")
            n += 1
        print(f"{n} spans")
    elif a.cmd == "run":
        try:
            host = resolve_host(a.host, who="hebrew_local_arms")
        except (EndpointMissing, EndpointRefused) as e:
            print("", file=sys.stderr); print(e, file=sys.stderr); print("", file=sys.stderr); sys.exit(2)
        hostport = normalize_hostport(host)
        models = a.model or ARMS
        if not out.exists():
            io.open(out, "w", encoding="utf-8").write(json.dumps(build_header(
                host=hostport, model="+".join(models),
                identity_extra={"api_path": "/api/chat", "think": False, "temperature": 0,
                                "num_ctx": NUM_CTX, "models": models, "apertures": list(APERTURES),
                                "prompt_head": _RECROP_PROMPT[:40], "pad_native_px": D.PAD,
                                "include_sealed": include_sealed, "vram_min": VRAM_MIN},
                extra={"prerun": PRERUN.name, "amendment": "Chris 2026-09-20: local arms on D, n=19"}),
                ensure_ascii=False) + "\n")
        run(hostport, models, out=out, include_sealed=include_sealed)
    elif a.cmd == "score":
        rows, _ = score(out, include_sealed)
        for m in sorted({o["model"] for o in rows}):
            for apn in APERTURES:
                sub = [o for o in rows if o["model"] == m and o["aperture"] == apn]
                if sub:
                    print(f"{m:16s} {apn:11s} n={len(sub):3d}  {_tally(sub)}")
    elif a.cmd == "matrix":
        rows, sets = score(out, include_sealed)
        if a.with_c:
            rows = rows + [o for o in load_c_arms(include_sealed) if o["span_id"] in sets]
        for apn in APERTURES:
            print(f"\n=== {apn} ===")
            models = sorted({o["model"] for o in rows if o["aperture"] == apn})
            by = {(o["span_id"], o["model"]): o for o in rows if o["aperture"] == apn}
            print(f"{'span':11s} {'seal':4s} " + " ".join(f"{m[:20]:20s}" for m in models))
            for sid in sorted(sets, key=lambda x: int(x.split(':')[0][1:])):
                cells = [(by.get((sid, m)) or {}).get("cls", "-")[:20] for m in models]
                print(f"{sid:11s} {int(sets[sid]['sealed']):<4d} " + " ".join(f"{c:20s}" for c in cells))
            ms, bys, pairs = agreement(rows, apn)
            print(f"\n  pairwise string agreement - agreement, NOT correctness:")
            for (x, y), (same, n) in sorted(pairs.items()):
                print(f"    {x[:22]:22s} vs {y[:22]:22s}  {same:2d}/{n:2d}")
            print(f"\n  per-span unanimity:")
            for sid in sorted(sets, key=lambda z: int(z.split(':')[0][1:])):
                vals = [bys[m][sid] for m in ms if bys.get(m, {}).get(sid)]
                if not vals:
                    continue
                uniq = len(set(vals))
                tr = sets[sid]["truth"]
                # One read is not unanimity. Say how many agreed, and only call it unanimous at 2+.
                label = (str(uniq) + " readings" if uniq > 1
                         else ("UNANIMOUS" if len(vals) > 1 else "single read"))
                mark = ""
                if uniq == 1 and tr and len(vals) > 1:
                    hit = (not D.HEB.search(vals[0])) if tr == D.NOT_HEBREW else (vals[0] == D._norm(tr))
                    mark = "  = signed" if hit else "  != signed  (agreed misread)"
                print(f"    {sid:11s} {len(vals):2d} read{'s' if len(vals) != 1 else ' '}  {label:12s}{mark}")
