"""Item 6(a): the context axes, strip on/off x text on/off, on the LOCAL D arms. 2026-10-04.

    python hebrew_context_axes.py plan
    python hebrew_context_axes.py run  --host 192.168.1.169:11435
    python hebrew_context_axes.py score

WHAT THIS MEASURES. Every Hebrew read in this lane has been given context in one of two channels: an
IMAGE of the surrounding footnote strip (the D arms, `hebrew_local_arms`) or the note's Latin as TEXT
with the Hebrew bulleted out (the frontier arms, `hebrew_frontier_or._ctx`). Neither channel has ever
been ablated. So no number in this lane separates "the model read the pixels" from "the model
reconstructed the verse from the context it was handed" -- and `p423:n3` proved that second path is
live, when three arms returned the canonical Masoretic reading from a crop containing NO INK AT ALL,
one of them matching the signed string exactly. Chris's law for the production path, 2026-10-04:
**a read is evidence only about a crop that passed the input guard.** This run begins to size how much
of the measured exact rate is a reading and how much is the context.

WHY THE D ARMS, AND NOT THE 26. The first design for 6(a) put the 2x2 on the frontier arms. That cell
set would have sent the context STRIP off the network -- a wider band of the note than the ratified A2
span box, a new class of pixels, 19 of them, unapproved. Chris re-specified: the strip axis runs on the
LOCAL arms, where nothing leaves the network, and the frontier gets the text axis only, on span crops
that are already approved and archived. This module is the local half. Page numbers are FILE pages
(printed = file - 88).

THE FIVE CELLS. A2 span box only; A1 is never built here.

    base        strip ON   text OFF    the recorded D config, bit-identical (see the assert below)
    base_rep    strip ON   text OFF    the WITHIN-RUN null, same config, run again
    strip_text  strip ON   text ON     both channels
    bare        strip OFF  text OFF    the crop alone -- no context of any kind
    text_only   strip OFF  text ON     the frontier's channel configuration, on this read path

THE NULL IS THE POINT, not the 2x2. Two identical arms pooled 55/78 twice and still moved 14 of 78 per
question, and one null replicate flipped 6/6 -> 0/6 at fixed config. So `base` vs `base_rep` is a
within-run null, and `base` vs the recorded 20260920 artifact is a CROSS-run null spanning two weeks
and a model reload. Every axis delta is read against those, never against zero. If the nulls move as
far as the axes do, the honest output of 6(a) is "unmeasured" and not a table.

THE CONFOUND THIS CANNOT REMOVE, stated up front. With the strip image absent, a prompt that says
"Image 1 is a full footnote strip ... image 2" is incoherent, so the strip axis necessarily moves the
PROMPT as well as the pixels: `strip ON` is "the strip plus the sentence that refers to it", `strip
OFF` is "neither". There is no cell that holds the wording fixed while removing the image, because a
prompt naming an image that was not sent is a worse confound than this one. Read the strip axis as a
channel-plus-its-instruction, and never as pixels alone.

WHAT IS BIT-IDENTICAL TO THE RECORDED RUN, and why it is asserted rather than claimed. `base` must
reproduce `hebrew_local_arms`' configuration exactly or the cross-run null is not a null: same native
`/api/chat`, `think` off, temperature 0, same `num_ctx`, same VRAM abort, same two images in the same
order, and the same prompt BYTES -- which is why HEAD_STRIP + TAIL is asserted equal to
`hebrew_recrop._RECROP_PROMPT` at import. If someone edits that prompt, this module refuses to run
rather than quietly reporting a cross-run delta that is a prompt change.
"""
import argparse
import io
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import httpx
from PIL import Image

import hebrew_aperture_diag as D
import hebrew_local_arms as L
import nikud_gate
import script_gate
from hebrew_frontier_or import _ctx, diag_sha
from hebrew_recrop import _RECROP_PROMPT
from run_header import build_header, endpoint_id, model_digest, normalize_hostport, _git_head, _git_dirty

OUT = D.DATA / "hebrew_context_axes_reads_20261004.jsonl"
APERTURE = "A2_spanbox"
DEAD_RUN_AT = 5          # consecutive dead items -> the RUN is faulted, not the items

# The prompt, split at the seam. HEAD_STRIP + TAIL is the recorded prompt, byte for byte.
HEAD_STRIP = (
    "Image 1 is a full footnote strip from a 1766 Bible commentary. Image 2 is a MAGNIFIED region "
    "from it containing a Hebrew word (usually followed by a Latin gloss). Using image 1 for full "
    "context, transcribe ONLY the Hebrew word shown magnified in image 2.")
HEAD_BARE = (
    "The image is a MAGNIFIED region from a footnote in a 1766 Bible commentary containing a Hebrew "
    "word (usually followed by a Latin gloss). Transcribe ONLY the Hebrew word shown.")
TAIL = (
    " Output the Hebrew CONSONANTS exactly as printed — the source is UNPOINTED, so do NOT add any "
    "vowel points (nikud). Output only the Hebrew word, nothing else.")
# The text channel, worded as the frontier words it, so the two harnesses differ in read path and not
# in what the text channel says.
TEXT_BLOCK = ("\n\nContext from the surrounding footnote text. Hebrew has been removed; each • marks "
              "one Hebrew word that stood there:\n  %s")

assert HEAD_STRIP + TAIL == _RECROP_PROMPT, (
    "the `base` cell is no longer bit-identical to the recorded D config -- the cross-run null would "
    "be measuring a prompt edit. Re-split HEAD_STRIP/TAIL against hebrew_recrop._RECROP_PROMPT.")

CELLS = [("base", True, False), ("base_rep", True, False), ("strip_text", True, True),
         ("bare", False, False), ("text_only", False, True)]


def prompt_for(strip, text, ctx):
    p = (HEAD_STRIP if strip else HEAD_BARE) + TAIL
    return p + (TEXT_BLOCK % ctx) if text else p


def built():
    """A2-scorable spans with a context strip. One population for all five cells, by construction.

    `unscorable` spans are EXCLUDED, and that is not a convenience. `L._built` returns 20 where
    `score()` tallies 19, because `p900:n4`'s ratified box leaves the strip -- the same 20-vs-19
    mismatch that was just fixed in `hebrew_frontier_or.support()`. A crop whose box is known wrong
    cannot be evidence about anything (Chris's law), so it is not sent, rather than sent and discarded
    at scoring time."""
    sets = {s["span_id"]: s for s in D.build_set(include_sealed=True)}
    out = []
    for s in L._built(include_sealed=True):
        if not s.get(APERTURE) or not s.get("context_strip"):
            continue
        if (sets.get(s["span_id"]) or {}).get("unscorable"):
            continue
        out.append(s)
    return out


def read_one(hostport, model, prompt, images):
    """Native /api/chat, thinking off, temperature 0. `images` is [] / [crop] / [strip, crop]."""
    t0 = time.time()
    r = httpx.post(f"http://{hostport}/api/chat",
                   json={"model": model,
                         "messages": [{"role": "user", "content": prompt, "images": images}],
                         "think": False, "stream": False, "keep_alive": L.KEEP_ALIVE,
                         "options": {"num_ctx": L.NUM_CTX, "temperature": 0}}, timeout=1800)
    r.raise_for_status()
    d = r.json()
    msg = d.get("message") or {}
    return ((msg.get("content") or "").strip(), d.get("done_reason"),
            (msg.get("thinking") or "").strip()[:200], round(time.time() - t0, 1))


def ink_state(im):
    """What the pixels being sent actually contain. Chris's law: a read is evidence only about a crop
    that passed the input guard -- so the state of EVERY channel is recorded beside the read, including
    the strip's. The strip is the shared channel that let a blank crop score, so it gets watched."""
    try:
        lo, hi = im.convert("L").getextrema()
    except Exception:
        return None
    return "BLANK" if lo == hi else "INK"


def run(hostport, models, out=OUT, cells=None):
    cells = cells or CELLS
    pop = built()
    if not pop:
        raise RuntimeError("empty send population -- refusing to report a clean run over zero spans")
    hp = normalize_hostport(hostport)
    if hp.split(":")[0] in ("192.168.1.179", "192.168.1.188"):
        raise RuntimeError(f"{hp} is the RESERVED production pair -- never send to it")
    eid = endpoint_id(hp)
    g0 = {"git_head": _git_head(), "git_dirty": _git_dirty()}
    done = set()
    if out.exists():
        done = {(o["cell"], o["span_id"], o["model"]) for o in D._lines(out) if "span_id" in o}
    aborted, dead, faulted = [], 0, None

    with io.open(out, "a", encoding="utf-8") as f:
        f.write(json.dumps(
            build_header(hp.split(":")[0], models[0], port=hp.split(":")[1],
                         kind="axes_run_header",
                         identity_extra={"aperture": APERTURE, "arms": models,
                                         "cells": [[c, s, t] for c, s, t in cells],
                                         "api_path": "/api/chat", "think": False, "temperature": 0,
                                         "num_ctx": L.NUM_CTX,
                                         "prompt_strip_sha16": diag_sha(HEAD_STRIP + TAIL),
                                         "prompt_bare_sha16": diag_sha(HEAD_BARE + TAIL),
                                         "text_block_sha16": diag_sha(TEXT_BLOCK),
                                         "base_is_recorded_config": True},
                         extra={"n_spans": len(pop), "spans": [s["span_id"] for s in pop],
                                "git_at_start": g0, "dead_run_at": DEAD_RUN_AT}),
            ensure_ascii=False) + "\n")
        f.flush()

        for model in models:
            print(f"\n=== arm {model} on {eid} ({hp}) ===", flush=True)
            ok, rep = L.vram_check(hp, model)
            digest = model_digest(hp, model)
            print(f"  vram: {rep}", flush=True)
            if not ok:
                # An arm that spilled to CPU is not a slower arm, it is a different arm.
                print("  ABORTED: spilled to CPU or failed to load -> no spans read", flush=True)
                aborted.append((model, rep))
                f.write(json.dumps({"kind": "arm_abort", "model": model, "vram": rep},
                                   ensure_ascii=False) + "\n")
                L.unload(hp, model)
                continue
            for cell, strip, text in cells:
                n = 0
                for s in pop:
                    if (cell, s["span_id"], model) in done:
                        continue
                    crop = Image.open(s[APERTURE]["path"]).convert("L")
                    ctx = _ctx(s["latin_context"])
                    states = {"crop_ink": ink_state(crop)}
                    imgs, refused = [], None
                    try:
                        if strip:
                            st = Image.open(s["context_strip"]).convert("L")
                            states["strip_ink"] = ink_state(st)
                            imgs.append(L._b64(st, what=f"{s['span_id']}:strip"))
                        imgs.append(L._b64(crop, what=f"{s['span_id']}:{APERTURE}"))
                    except D.CropRefused as e:
                        # Which CHANNEL was refused is the finding, not just that one was.
                        refused = f"{e.fault}@{'strip' if strip and not imgs else 'crop'}"
                    if refused:
                        raw, dr, think, secs = "", f"REFUSED:{refused}", "", 0.0
                    else:
                        try:
                            raw, dr, think, secs = read_one(hp, model,
                                                            prompt_for(strip, text, ctx), imgs)
                            dead = 0
                        except Exception as e:
                            raw, dr, think, secs = "", f"ERROR:{type(e).__name__}", "", 0.0
                            dead += 1
                    gated, nik, dens = nikud_gate.gated_strip(raw, crop)
                    sv, sr = script_gate.gate(gated, s["latin_context"])
                    f.write(json.dumps(
                        {"span_id": s["span_id"], "aperture": APERTURE, "model": model, "cell": cell,
                         "strip": strip, "text": text, "endpoint_id": eid, "endpoint_host": hp,
                         "model_digest16": digest, "sealed": s["sealed"], "raw": raw, "gated": gated,
                         "nikud_verdict": nik, "nikud_density": round(float(dens), 3),
                         "crop_fault": refused,
                         "unscorable": (f"crop-fault:{refused}" if refused else None),
                         "reached_wire": refused is None, "n_images": len(imgs),
                         "script_verdict": sv, "script_reason": sr, "done_reason": dr, "secs": secs,
                         "thinking_leak": think, "crop_size": s[APERTURE]["size"],
                         "ctx_chars": len(ctx) if text else 0, **states},
                        ensure_ascii=False) + "\n")
                    f.flush()
                    n += 1
                    if dead >= DEAD_RUN_AT:
                        # run-level fault vs item error: N consecutive dead items invalidates the RUN.
                        faulted = f"{dead} consecutive dead items at {model}/{cell}/{s['span_id']}"
                        break
                print(f"  {cell:11s} strip={int(strip)} text={int(text)}  {n} reads", flush=True)
                if faulted:
                    break
            L.unload(hp, model)
            if faulted:
                break

        g1 = {"git_head": _git_head(), "git_dirty": _git_dirty()}
        clean = (g0 == g1 and g0["git_dirty"].get("state") == "clean")
        f.write(json.dumps({"kind": "axes_run_footer", "git_at_end": g1, "git_at_start": g0,
                            "clean_run": clean, "run_faulted": faulted,
                            "aborted_arms": [list(a) for a in aborted],
                            "ended": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False) + "\n")
    if faulted:
        print(f"\n*** RUN FAULTED: {faulted} -- this artifact cannot be scored or cited. "
              f"Rerun from the top; never splice. ***")
    if not clean:
        print(f"\n*** PROVISIONAL: git moved or the tree was dirty. start={g0} end={g1} ***")
    print(f"\nwrote {out}")


# ------------------------------------------------------------------ scoring


def score(out=OUT):
    sets = {s["span_id"]: s for s in D.build_set(include_sealed=True)}
    foot = [o for o in D._lines(out) if o.get("kind") == "axes_run_footer"]
    if any(o.get("run_faulted") for o in foot):
        raise RuntimeError("this artifact carries a run_faulted footer -- it cannot be scored")
    rows = [o for o in D._lines(out)
            if "span_id" in o and o.get("model") not in D.DROPPED_ARMS]
    for o in rows:
        s = sets.get(o["span_id"])
        if not s:
            o["cls"] = "OUT-OF-SET"
        elif s["unscorable"] or o.get("unscorable"):
            o["cls"] = "UNSCORABLE"
        else:
            o["cls"] = D.classify(o["gated"], s["truth"])
    return rows, sets, (foot[-1] if foot else None)


def report(out=OUT):
    rows, sets, foot = score(out)
    by = defaultdict(list)
    for o in rows:
        by[o["cell"]].append(o)
    order = [c for c, _s, _t in CELLS if c in by]

    print("item 6(a) -- context axes on the local D arms. FILE pages (printed = file - 88).")
    if foot:
        print(f"clean_run={foot.get('clean_run')}  git_at_end={foot['git_at_end']['git_head'][:8]} "
              f"{foot['git_at_end']['git_dirty'].get('state')}")
    print(f"\n{'cell':12s} {'strip':>5s} {'text':>4s} {'n':>4s} {'exact':>6s} {'contains':>8s} "
          f"{'clipped':>7s} {'wrong':>6s} {'abstain':>7s} {'nikud':>5s}")
    tal = {}
    for c in order:
        t = L._tally(by[c])
        tal[c] = t
        s, x = next((s, x) for cc, s, x in CELLS if cc == c)
        print(f"{c:12s} {int(s):>5d} {int(x):>4d} {len(by[c]):>4d} {t['exact']:>6d} "
              f"{t['contains']:>8d} {t['clipped']:>7d} {t['wrong']:>6d} {t['abstain']:>7d} "
              f"{t['nikud-only']:>5d}")

    # The nulls, printed before any axis delta, because they bound what a delta can mean.
    if "base" in tal and "base_rep" in tal:
        d = tal["base_rep"]["exact"] - tal["base"]["exact"]
        print(f"\nWITHIN-RUN NULL  base vs base_rep, identical config: exact {tal['base']['exact']} "
              f"-> {tal['base_rep']['exact']}  (delta {d:+d} of {len(by['base'])})")
        flip = 0
        key = lambda o: (o["span_id"], o["model"])
        a = {key(o): o["cls"] for o in by["base"]}
        b = {key(o): o["cls"] for o in by["base_rep"]}
        for k in set(a) & set(b):
            if a[k] != b[k]:
                flip += 1
        print(f"                 per-read class flips at FIXED config: {flip} of {len(set(a) & set(b))}"
              f"  <- any axis delta smaller than this is unmeasured")

    cross = [o for o in D._lines(L.OUT) if o.get("aperture") == APERTURE
             and o.get("model") not in D.DROPPED_ARMS]
    if cross and "base" in by:
        for o in cross:
            s = sets.get(o["span_id"])
            o["cls"] = ("UNSCORABLE" if (not s or s["unscorable"] or o.get("unscorable"))
                        else D.classify(o["gated"], s["truth"]))
        arms = {o["model"] for o in by["base"]}
        c2 = [o for o in cross if o["model"] in arms]
        if c2:
            print(f"CROSS-RUN NULL   20260920 artifact, same config, same arms: "
                  f"exact {L._tally(c2)['exact']} of {len(c2)}  vs base "
                  f"{tal['base']['exact']} of {len(by['base'])}")

    print("\nper-span exact, by cell (19 spans x arms):")
    spans = sorted({o["span_id"] for o in rows}, key=lambda x: int(x.split(":")[0][1:]))
    print(f"{'span':10s} {'truth':>14s} " + " ".join(f"{c[:9]:>9s}" for c in order))
    for sp in spans:
        t = (sets.get(sp) or {}).get("truth") or ""
        cs = []
        for c in order:
            r = [o for o in by[c] if o["span_id"] == sp]
            e = sum(1 for o in r if o["cls"] in ("exact", "punct-only"))
            cs.append(f"{e:>4d}/{len(r):<4d}")
        print(f"{sp:10s} {t[:14]:>14s} " + " ".join(cs))


def plan():
    pop = built()
    print(f"spans {len(pop)}  arms {L.ARMS}  cells {[c for c, _s, _t in CELLS]}")
    print(f"reads = {len(pop)} x {len(L.ARMS)} x {len(CELLS)} = "
          f"{len(pop) * len(L.ARMS) * len(CELLS)}  (local, no cost, nothing leaves the network)")
    print(f"base prompt is the recorded config: {HEAD_STRIP + TAIL == _RECROP_PROMPT}")
    print(f"git: {_git_head()[:8]} {_git_dirty().get('state')}")
    for s in pop[:3]:
        print(f"  e.g. {s['span_id']:10s} crop={s[APERTURE]['size']} "
              f"strip={Path(s['context_strip']).name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["plan", "run", "score"])
    ap.add_argument("--host", default="192.168.1.169:11435")
    ap.add_argument("--model", action="append", default=None)
    ap.add_argument("--cell", action="append", default=None)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    out = Path(a.out)
    if a.cmd == "plan":
        plan()
    elif a.cmd == "run":
        cells = [c for c in CELLS if c[0] in set(a.cell)] if a.cell else CELLS
        run(a.host, a.model or L.ARMS, out=out, cells=cells)
    else:
        report(out)


if __name__ == "__main__":
    main()
