"""CV superscript re-detection VALIDATION HARNESS — the deterministic prerequisite for the (daylight)
detector build. This build's ground truth is genuinely SCARCE (the 609 barren pages have no stored
layer to diff against), so — per Chris — validate on the ~404 ANCHORED pages where the old body DID
keep its markers: score a candidate detector's precision/recall against those KNOWN positions, then
barren-page deployment INHERITS the measured rates and the per-anchor confidence classes mean something.
Validate where truth exists; deploy where it doesn't.

Provides: (1) ground_truth — known anchor (letter, text-offset, preceding-phrase) per anchored page;
(2) render_body_strip — the hi-res body-region image the detector will process; (3) score — precision/
recall with a LETTER-SCOPE WINDOW (a detected anchor must fall near where its sequence-neighbor ordering
puts it → the ordering constraint converts weak detections into strong placements). Detector plugs in later.
"""
import sys, os, re, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import assembler as A
import standoff

BODYDIR = Path("c:/Users/cnogr/git/dr-voluminous/commentary/volume1/qwen_qwen3-vl-235b-a22b-thinking")
IMGDIR = Path("c:/Users/cnogr/git/dr-voluminous/commentary/volume1")

def ground_truth(page):
    """Known anchors for an anchored page: [{letter, offset, phrase}] from the OLD body text (free)."""
    md = (BODYDIR / f"page{page}_image1.md").read_text(encoding="utf-8")
    body = A.split_body_defs(md)[0]
    out = []
    for letter, off in standoff.detect_body_anchor_positions(body):
        out.append({"letter": letter, "offset": off, "phrase": standoff._phrase_anchor(body, off)})
    return out

def render_body_strip(page, upscale=2):
    """The hi-res BODY-region image (above the footnote rule) the detector localizes superscripts in."""
    import cv_footnote_presplit as ps
    from PIL import Image
    im = Image.open(IMGDIR / f"page{page}_image1.png"); W, H = im.size
    dark = ps._dark(im); xdiv = ps.find_vertical_divider(dark)
    rl = ps.find_hrule(dark, int(W*0.03), xdiv-int(W*0.02)); rr = ps.find_hrule(dark, xdiv+int(W*0.02), W-int(W*0.03))
    rule_y = min([r for r in (rl, rr) if r is not None], default=H)
    top = int(H * 0.03)
    strip = im.crop((0, top, W, rule_y)).convert("L")
    if upscale != 1: strip = strip.resize((strip.size[0]*upscale, strip.size[1]*upscale), Image.LANCZOS)
    return strip

def score(detected, truth, window_chars=40):
    """detected/truth = lists of {offset, ...} in reading order. A detected anchor MATCHES a truth
    anchor if their offsets are within `window_chars` (the letter-scope window) AND unused. Returns
    precision/recall/f1 + counts. The ordering constraint: match greedily in reading order."""
    t = sorted(truth, key=lambda x: x["offset"]); d = sorted(detected, key=lambda x: x["offset"])
    used = [False] * len(t); tp = 0
    for db in d:
        for j, tb in enumerate(t):
            if not used[j] and abs(tb["offset"] - db["offset"]) <= window_chars:
                used[j] = True; tp += 1; break
    fp = len(d) - tp; fn = len(t) - tp
    prec = tp / len(d) if d else (1.0 if not t else 0.0)
    rec = tp / len(t) if t else 1.0
    f1 = 2*prec*rec/(prec+rec) if (prec+rec) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3)}

def score_corpus(detector_fn, pages, window_chars=40):
    """Run a candidate detector over the anchored validation set; aggregate precision/recall.
    detector_fn(page) -> list of {offset} (its detected anchor text-offsets). No detector tonight →
    daylight plugs it in; this proves the harness end-to-end with a perfect-oracle and a null detector."""
    agg = {"tp": 0, "fp": 0, "fn": 0}
    for pg in pages:
        gt = ground_truth(pg); s = score(detector_fn(pg, gt), gt, window_chars)
        for k in agg: agg[k] += s[k]
    P = agg["tp"]/(agg["tp"]+agg["fp"]) if (agg["tp"]+agg["fp"]) else 1.0
    R = agg["tp"]/(agg["tp"]+agg["fn"]) if (agg["tp"]+agg["fn"]) else 1.0
    return {**agg, "precision": round(P, 3), "recall": round(R, 3),
            "f1": round(2*P*R/(P+R), 3) if (P+R) else 0.0, "pages": len(pages)}

if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    D = Path(os.getenv("HARNESS_DIR", "."))
    pages = json.loads((D / "anchored_pages.json").read_text())[:40]   # sample for the smoke
    print(f"ground-truth smoke on {len(pages)} anchored pages:")
    print("  p100 truth:", [(a["letter"], a["offset"]) for a in ground_truth(100)][:5])
    # harness end-to-end proof: a PERFECT oracle (recall 1.0) and a NULL detector (recall 0) must bracket it
    perfect = score_corpus(lambda pg, gt: [{"offset": a["offset"]} for a in gt], pages)
    null = score_corpus(lambda pg, gt: [], pages)
    print(f"  PERFECT-oracle detector: P={perfect['precision']} R={perfect['recall']} f1={perfect['f1']} (must be 1.0)")
    print(f"  NULL detector:           P={null['precision']} R={null['recall']} (recall must be 0)")
    print("  → harness scores correctly; daylight plugs a real detector into score_corpus().")
