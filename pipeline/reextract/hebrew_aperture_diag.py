"""Lane B item 1 - crop-vs-model Hebrew diagnostic. NO pipeline changes: this module reads the frozen v2
read path and the human-ratified box files and writes its own audit outputs. It imports from the pipeline;
nothing in the pipeline imports it.

Question: is the measured Hebrew error caused by CROP QUALITY or by THE READER? Both apertures are cut from
HUMAN-ratified boxes, so CV geometry is out of the loop on the box axis (presplit still owns the coordinate
FRAME - the human drew on the strip presplit produced - which is a named limit, not a silent one).

  A1  ratified NOTE box        note_box_truth_20260906_FINAL.jsonl   (door human-note-box-ratify)
  A2  ratified HEBREW-SPAN box span_box_verdicts_20260906.jsonl      (door human-box-ratify, 30/30 adjusted)

The context image (image 1 of the v2 recrop prompt) is held CONSTANT across apertures, so the only variable
is image 2. Scored against SIGNED verdicts only. Page numbers are FILE pages (printed = file - 88).

Usage:  python hebrew_aperture_diag.py crops          # build + save crops, no model calls
        python hebrew_aperture_diag.py run            # read both models x both apertures
        python hebrew_aperture_diag.py score          # score what run wrote
"""
import base64, io, json, os, re, sys, time, unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from PIL import Image
import httpx
import cv_footnote_presplit as ps
from run_header import build_header, model_digests, normalize_hostport
import note_region, nikud_gate, script_gate
from hebrew_recrop import _RECROP_PROMPT

DATA = Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits")
IMG = Path("C:/Users/cnogr/git/dr-voluminous/commentary/volume1")
# The signed human sittings moved out of Downloads into the repo on 2026-09-20 (Chris's ruling 0):
# irreproducible human work must not live in a downloads folder. Same directory as DATA now.
DOWN = DATA
CROPDIR = DATA / "hebrew_aperture_crops_20260920"
OUT = DATA / "hebrew_aperture_reads_20260920.jsonl"
HOST = os.getenv("OLLAMA_HOST", "192.168.1.169")
MODELS = ["qwen3.6-16k:35b", "gemma4-32k:31b"]
NUM_CTX = 16384
PAD = 12                       # native px, applied AFTER the strip->native map so padding never straddles
                               # the 20px column gap

SEALED = {129, 206, 217, 293, 362, 423, 427, 478, 491, 543, 596, 726, 897, 912}
HEB = re.compile(r"[\u0590-\u05FF]")
NOT_HEBREW = "\x00NOT-HEBREW"  # sentinel: the correct answer is "there is no Hebrew here"

# Signed truth, span by span. Every string traces to a human verdict; `basis` says which and how.
# See audits/hebrew_aperture_prerun_20260920.md section 1 for the derivation of each.
TRUTH = {
    "p102:n0": ("\u05d1\u05e8\u05d0 - \u05dc\u05e2\u05e9\u05d5\u05ea", "signed-correct:candidate-verbatim"),
    "p124:n4": ("\u05dc\u05d0 \u05db\u05df", "signed-correction:partial-span"),
    "p138:n5": ("\u05dc\u05da", "signed-correct:candidate-verbatim"),
    # RULED 2026-09-27 by Chris: "those are not in the original". The pointing is NOT on the page.
    # The 2026-09-06 sitting showed him the candidate \u05d5\u05d9\u05d4\u05d9 \u05d4\u05e9\u05de\u05e9 \u05dc\u05b0\u05d1\u05b9\u05d0 -- pointed, and
    # with NO vav. His correction was \u05d5\u05d9\u05d4\u05d9 \u05d4\u05e9\u05de\u05e9 \u05dc\u05b0\u05d1\u05b9\u05d5\u05d0. The edit he made was
    # CONSONANTAL: he added the missing vav. The sheva and holam rode along from the candidate
    # string he was editing; they were never an assertion that the page is pointed. Corroborating:
    # p200:n2 measures the LOWEST nikud density of any span at BOTH apertures (0.179 / 0.227) and
    # never leaves `uncertain`. Independently, 18 of 30 arms read exactly these consonants.
    #
    # Derived by the same rule as p253:n2 -- strip_nikud(the signed correction) -- which makes the
    # table consistent: every entry is now the printed consonantal form. Pinned in
    # test_hebrew_sealed_truth.py so it cannot drift back.
    #
    # What the old entry cost: 18 of 30 arms scored `nikud-only` instead of `exact` on this span,
    # and two committed audits published it as having no correct candidate from any arm.
    "p200:n2": ("\u05d5\u05d9\u05d4\u05d9 \u05d4\u05e9\u05de\u05e9 \u05dc\u05d1\u05d5\u05d0",
                "signed-correction:vav-added-then-strip-nikud-ruled-20260927"),
    "p219:n0": ("\u05d4\u05d5\u05d0\u05dc\u05ea\u05d9 \u05dc\u05d3\u05d1\u05e8", "signed-correct:candidate-verbatim"),
    "p253:n2": ("\u05d4\u05e7\u05e8\u05d4 \u05e0\u05d0 \u05dc\u05e4\u05e0\u05d9",
                "signed-correction:derived-strip-nikud"),
    "p360:n0": ("\u05e9\u05d0\u05dc \u05e9\u05d0\u05dc", "signed-correct:candidate-verbatim"),
    "p895:n0": ("\u05d5\u05ea\u05e7\u05e2\u05e8 \u05e0\u05e4\u05e9", "signed-correction:disputes-agent-printed"),
    "p900:n4": (NOT_HEBREW, "signed-correction:not-hebrew-greek"),
    "p657:n0": ("\u05d1\u05d4\u05e8", "signed-residue-correction"),
}
UNSCORABLE = {"p138:n6": "signed wrong, correction field empty - no signed truth string"}

# ---------------------------------------------------------------------------------------------------
# The SEALED-page half of the same signed sitting. Chris's ruling 2 (2026-09-20) opens sealed pages for
# THIS HARNESS ONLY: a Hebrew READ on a sealed page does not touch the alignment gate's evidence, which
# is what "sealed" protects. Nothing here re-scores an alignment decision, and the gate stays frozen.
#
# These strings are DERIVED from the sitting file rather than retyped, and the derivation is asserted
# against the four hand-written candidate-verbatim entries above at import time (_assert_derivation).
# Retyping Hebrew by hand is exactly the plausible-word-substitution risk this lane measures at 35%.
#
#   chosen == "correct"                  -> truth is the candidate's Hebrew span, verbatim
#   chosen == "wrong" + correction       -> truth is the correction string
#   chosen == "wrong" + empty correction -> UNSCORABLE (same rule that excluded p138:n6)
SEALED_TRUTH = {
    "p217:n2": ("הימלא", "signed-correct:candidate-verbatim"),
    "p293:n0": ("יחמנה", "signed-correct:candidate-verbatim"),
    "p362:n1": ("להתגללעלינו",
                "signed-correction:verbatim"),
    "p423:n3": ("ותגע לרבליו",
                "signed-correction:verbatim"),
    "p427:n4": ("הבאשתם", "signed-correct:candidate-verbatim"),
    "p491:n1": ("בשמע", "signed-correct:candidate-verbatim"),
    # Chris marked this `wrong` but wrote "correct but should have no makers" - an adjudication about the
    # note's MARKERS, not about the Hebrew string, which he affirms. Truth is therefore the candidate
    # verbatim. This interpretation is load-bearing for n: the prerun's arithmetic ("n goes 10 -> 19")
    # counts this span as scorable and p596:n2 as not, which is only consistent with reading it this way.
    # Flagged in every report rather than buried; if Chris reads it otherwise, n is 18 and this span drops.
    "p726:n3": ("שְׁאָר אָבִיךְ",
                "signed-wrong:marker-defect-not-hebrew-defect"),
    "p897:n4": ("ענו לה", "signed-correction:verbatim"),
    "p912:n2": ("ביעקב בישראל",
                "signed-correct:candidate-verbatim"),
}
SEALED_UNSCORABLE = {"p596:n2": "signed wrong, correction field empty - no signed truth string"}


def _lines(p):
    return [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]


def _assert_derivation(sitting):
    """The sealed truths must fall out of the sitting file, not out of my typing. Checked at import."""
    for sid, (want, basis) in SEALED_TRUTH.items():
        rec = sitting.get(sid)
        if not rec:
            raise AssertionError(f"{sid}: not in the signed sitting")
        corr = (rec.get("disputed_span_correction") or "").strip()
        got = corr if (rec.get("chosen") == "wrong" and HEB.search(corr)) else _heb_span(
            rec["inputs"]["candidates"][0])
        if _norm(got) != _norm(want):
            raise AssertionError(f"{sid}: derived {got!r} != recorded {want!r}")


def _heb_span(text):
    """The maximal Hebrew run in a candidate line, separators kept. Validated against the hand-written
    entries in TRUTH (p102, p138:n5, p219, p360) by test_hebrew_sealed_truth.py."""
    toks = re.findall(r"[֐-׿][֐-׿]*", text or "")
    if not toks:
        return None
    i, j = text.index(toks[0]), text.rindex(toks[-1]) + len(toks[-1])
    seg = text[i:j]
    return seg if re.fullmatch(r"[֐-׿ \-]+", seg) else " ".join(toks)


def build_set(include_sealed=False):
    """The carried spans with their signed verdict, latin context, and both ratified boxes (strip coords).

    n=10 scorable by default. `include_sealed=True` adds the sealed half of the SAME signed sitting under
    Chris's ruling-2 carve-out -> n=19 scorable. A sealed page is opened here for a READ only; no
    alignment evidence is re-scored and the gate stays frozen."""
    sitting = {o["span_id"]: o for o in _lines(DOWN / "hebrew_sitting_chris_20260906.jsonl") if "span_id" in o}
    resid = {o["span_id"]: o for o in _lines(DATA / "chris_sitting_b_residue_20260823.jsonl") if "span_id" in o}
    spanbox = {o["span_id"]: o for o in _lines(DOWN / "span_box_verdicts_20260906.jsonl")}
    notebox = {o["page"]: o for o in _lines(DATA / "note_box_truth_20260906_FINAL.jsonl") if "page" in o}
    truth = dict(TRUTH)
    unscorable = dict(UNSCORABLE)
    if include_sealed:
        _assert_derivation(sitting)
        truth.update(SEALED_TRUTH)
        unscorable.update(SEALED_UNSCORABLE)
    out = []
    for sid in list(truth) + list(unscorable):
        pg, ni = int(sid.split(":")[0][1:]), int(sid.split(":")[1][1:])
        if not include_sealed:
            assert pg not in SEALED, f"{sid} is on a SEALED page"
        rec = sitting.get(sid) or resid.get(sid)
        cand = rec["inputs"]["candidates"][0] if rec else ""
        nb = notebox.get(pg)
        sb = spanbox.get(sid)
        sbox = (sb or {}).get("ratified_box")
        # The note index in the Hebrew sitting and the index into the ratified NOTE-BOX list are two
        # different human truth files and are NOT guaranteed to agree (p124: they differ by one, because
        # the note-box sitting split a missed start the sitting's numbering never saw). Resolve A1 by
        # maximum y-overlap with the ratified SPAN box - which is drawn on the Hebrew pixels themselves -
        # and fall back to the declared index only when no span box exists. Both sources stay human.
        used, ovf, clip = ni, None, None
        if nb and sbox:
            best, bestf = ni, -1.0
            for i, n in enumerate(nb["notes"]):
                b = n["strip_box"]
                ov = max(0, min(sbox[3], b[3]) - max(sbox[1], b[1])) / max(1, sbox[3] - sbox[1])
                if ov > bestf:
                    best, bestf = i, ov
            used, ovf = best, round(bestf, 3)
            clip = round(1.0 - bestf, 3)           # fraction of the span's height the note box clips
        nbox = nb["notes"][used]["strip_box"] if nb and used < len(nb["notes"]) else None
        out.append(dict(
            span_id=sid, page=pg, note_idx=ni,
            signed=(rec or {}).get("chosen"), latin_context=cand,
            truth=truth.get(sid, (None, None))[0], truth_basis=truth.get(sid, (None, None))[1],
            unscorable=unscorable.get(sid), sealed=(pg in SEALED),
            note_box=nbox, note_box_status=(nb["notes"][used]["status"] if nbox else None),
            a1_idx_declared=ni, a1_idx_used=used, a1_span_overlap=ovf, a1_clips_span_frac=clip,
            span_box=sbox, column_bands=(nb or {}).get("column_bands"),
            n_ratified=(nb or {}).get("n_ratified")))
    return out


def _native_crop(page_img, strip_box, info, bands, pad=0):
    """Un-stack a strip box to native rects and cut them. A box straddling the column gap yields TWO rects;
    they are stacked vertically with the same 20px gap presplit uses, never merged into one spanning box."""
    rects = note_region.strip_to_native(strip_box, info, bands)
    W, H = page_img.size
    ims = []
    for r in rects:
        x0, y0, x1, y1 = r["box"]
        x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
        x1, y1 = min(W, x1 + pad), min(H, y1 + pad)
        if x1 - x0 > 4 and y1 - y0 > 4:
            ims.append(page_img.crop((x0, y0, x1, y1)))
    if not ims:
        return None, rects
    if len(ims) == 1:
        return ims[0], rects
    w = max(i.width for i in ims)
    h = sum(i.height for i in ims) + 20 * (len(ims) - 1)
    canv = Image.new("L", (w, h), 255)
    y = 0
    for i in ims:
        canv.paste(i, (0, y))
        y += i.height + 20
    return canv, rects


def crops(save=True, include_sealed=False):
    CROPDIR.mkdir(parents=True, exist_ok=True)
    built, page_cache = [], {}
    for s in build_set(include_sealed=include_sealed):
        pg = s["page"]
        if pg not in page_cache:
            strip, info = ps.presplit(str(IMG / f"page{pg}_image1.png"), upscale=1)
            page_cache[pg] = (Image.open(IMG / f"page{pg}_image1.png").convert("L"),
                              strip.convert("L"), info)
        native, strip, info = page_cache[pg]
        bands = s["column_bands"] or note_region._column_bands(strip)
        rec = dict(s)
        for ap, box, pad in (("A1_notebox", s["note_box"], 0), ("A2_spanbox", s["span_box"], PAD)):
            if not box:
                rec[ap] = None
                continue
            im, rects = _native_crop(native, box, info, bands, pad)
            if im is None:
                rec[ap] = None
                continue
            p = CROPDIR / f"{s['span_id'].replace(':', '_')}_{ap}.png"
            if save:
                im.save(p)
            rec[ap] = dict(path=str(p), size=list(im.size),
                           native_rects=[r["box"] for r in rects], n_rects=len(rects))
        ctxp = CROPDIR / f"p{pg}_context_strip.png"
        if save and not ctxp.exists():
            strip.save(ctxp)
        rec["context_strip"] = str(ctxp)
        built.append(rec)
    if save:
        io.open(CROPDIR / "manifest.json", "w", encoding="utf-8").write(
            json.dumps(built, ensure_ascii=False, indent=1))
    return built


def _b64(im):
    b = io.BytesIO()
    im.save(b, format="PNG")
    return base64.b64encode(b.getvalue()).decode()


def read_one(context_strip, crop, model):
    """The frozen v2 recrop read: same prompt, same two-image shape, same options. Only image 2 varies."""
    t0 = time.time()
    r = httpx.post(f"http://{HOST}:11434/api/generate",
                   json={"model": model, "prompt": _RECROP_PROMPT,
                         "images": [_b64(context_strip), _b64(crop)],
                         "think": False, "stream": False,
                         "options": {"num_ctx": NUM_CTX, "temperature": 0}}, timeout=900)
    d = r.json()
    return (d.get("response", "") or "").strip(), d.get("done_reason"), round(time.time() - t0, 1)


def run():
    built = crops(save=True)
    done = set()
    if OUT.exists():
        done = {(o["span_id"], o["aperture"], o["model"]) for o in _lines(OUT) if "span_id" in o}
    with io.open(OUT, "a", encoding="utf-8") as f:
        if not done:
            # Machine in the header and in the hash (ruling, 2026-09-20). This harness calls TWO models,
            # so there is no single set of weights: the per-model digest map goes into the hash, since
            # collapsing it to one model would let a run with a swapped witness hash alike.
            hp = normalize_hostport(HOST)
            hdr = build_header(host=HOST, model="+".join(MODELS),
                               identity_extra={"api_path": "/api/generate", "think": False,
                                               "temperature": 0, "num_ctx": NUM_CTX, "models": MODELS,
                                               "model_digests16": model_digests(hp, MODELS),
                                               "prompt_head": _RECROP_PROMPT[:40], "pad_native_px": PAD},
                               extra={"prerun": "hebrew_aperture_prerun_20260920.md"})
            f.write(json.dumps(hdr, ensure_ascii=False) + chr(10))
        for s in built:
            ctx = Image.open(s["context_strip"]).convert("L")
            for ap in ("A1_notebox", "A2_spanbox"):
                if not s.get(ap):
                    continue
                crop = Image.open(s[ap]["path"]).convert("L")
                for m in MODELS:
                    if (s["span_id"], ap, m) in done:
                        continue
                    raw, dr, secs = read_one(ctx, crop, m)
                    gated, nik_verdict, dens = nikud_gate.gated_strip(raw, crop)
                    sv, sr = script_gate.gate(gated, s["latin_context"])
                    f.write(json.dumps({"span_id": s["span_id"], "aperture": ap, "model": m,
                                        "raw": raw, "gated": gated, "nikud_verdict": nik_verdict,
                                        "nikud_density": round(float(dens), 3), "script_verdict": sv,
                                        "script_reason": sr, "done_reason": dr, "secs": secs,
                                        "crop_size": s[ap]["size"]}, ensure_ascii=False) + "\n")
                    f.flush()
                    print(f"  {s['span_id']:10s} {ap:11s} {m:18s} {secs:6.1f}s  {raw[:48]!r}", flush=True)
    print("wrote", OUT)


def _norm(t):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", t or "")).strip()


def _punct_fold(t):
    return _norm(t).replace("\u05be", "-").replace("\u2010", "-").replace("\u2011", "-")


def classify(read, truth):
    r, t = _norm(read), _norm(truth)
    if truth == NOT_HEBREW:
        return "exact" if not HEB.search(r) else "wrong"
    if not r or not HEB.search(r):
        return "abstain"
    if r == t:
        return "exact"
    if _punct_fold(r) == _punct_fold(t):
        return "punct-only"
    if nikud_gate.strip_nikud(r) == nikud_gate.strip_nikud(t):
        return "nikud-only"
    if t and t in r:
        return "contains"
    return "wrong"


def score():
    rows = [o for o in _lines(OUT) if "span_id" in o]
    sets = {s["span_id"]: s for s in build_set()}
    for o in rows:
        s = sets[o["span_id"]]
        o["cls"] = "UNSCORABLE" if s["unscorable"] else classify(o["gated"], s["truth"])
    return rows


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "crops"
    if cmd == "crops":
        for s in crops():
            a1 = s["A1_notebox"] and s["A1_notebox"]["size"]
            a2 = s["A2_spanbox"] and s["A2_spanbox"]["size"]
            print(f"{s['span_id']:10s} A1={a1} A2={a2} nb_status={s['note_box_status']}")
    elif cmd == "run":
        run()
    elif cmd == "score":
        for o in score():
            print(f"{o['span_id']:10s} {o['aperture']:11s} {o['model']:18s} {o['cls']:11s} "
                  f"{o['gated'][:40]!r}")
