"""Stratified acceptance truth set (ADR-0015 review-bandwidth spend — NOT exhaustive). Runs the
FROZEN re-extraction config on a stratified page sample and collects, per page: the re-extracted
apparatus, the anchor-match status + flagged (fail-loud) count, recrop changes, and the STORED
old-layer notes — everything the adjudication interface needs side-by-side. The result JSON doubles
as (1) V2's apparatus ground truth, (2) the re-extraction ADR's evidence section — written once.

The named strata are the known-hard classes; the random stratum licenses "the unremarkable pages
are fine too". The REST of vol1 is covered by the assertion suite, not by eyes. Fail-louds are
FINDINGS (flagged-and-documented is a PASS); a silent wrong answer in the adjudicated sample is the
only real failure.
"""
import sys, os, re, io, json, base64, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import assembler as A
from extract_apparatus import extract_page

STRATA = {
    "ground_truth":       [100, 473, 571],
    "whitelist_artifact": [336, 343, 433, 740, 757, 843, 692, 796],
    "collision":          [243, 264],
    "hebrew_dense":       [550, 702],
    "random":             [97, 150, 215, 269, 347, 419, 546, 602, 674, 733, 788, 874],
}
HEBREW = re.compile(r"[\u0590-\u05FF\u0370-\u03FF\u0700-\u074F]")

def stored_defs(body_md_path):
    """The old overloaded-layer note definitions, for side-by-side comparison."""
    if not Path(body_md_path).exists(): return []
    _, defs = A.split_body_defs(Path(body_md_path).read_text(encoding="utf-8", errors="replace"))
    out = []
    for m in re.finditer(r"^\s*(?:\[\^([a-z])\]:|\^([a-z])\^?)\s*(.+)$", defs, re.M):
        out.append({"letter": m.group(1) or m.group(2), "text": (m.group(3) or "").strip()})
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--img-dir", default="c:/Users/cnogr/git/dr-voluminous/commentary/volume1")
    ap.add_argument("--body-dir", default="c:/Users/cnogr/git/dr-voluminous/commentary/volume1/qwen_qwen3-vl-235b-a22b-thinking")
    ap.add_argument("--profile", default=str(Path(__file__).parent / "book_profile.gill.yaml"))
    ap.add_argument("--host", default=os.getenv("OLLAMA_HOST", "192.168.1.179"))
    ap.add_argument("--out", default=str(Path(__file__).parent / "truthset_out"))
    ap.add_argument("--strata-json", default="", help="override STRATA with a {stratum: [pages]} JSON file (leaves the canonical set untouched)")
    a = ap.parse_args()
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    except Exception: pass
    profile = A.load_profile(a.profile)
    out = Path(a.out); out.mkdir(exist_ok=True)
    strata = json.loads(Path(a.strata_json).read_text(encoding="utf-8")) if a.strata_json else STRATA
    page2stratum = {p: s for s, ps in strata.items() for p in ps}
    results = []
    for page in sorted(page2stratum):
        img = Path(a.img_dir) / f"page{page}_image1.png"
        if not img.exists(): print(f"p{page}: MISSING IMAGE", flush=True); continue
        body = str(Path(a.body_dir) / f"page{page}_image1.md")
        res = extract_page(str(img), profile, a.host, body_md=body)
        notes = res.get("notes", [])
        heb = any(HEBREW.search(n["text"]) for n in notes)
        m = res.get("anchor_match") or {}
        rec = {
            "page": page, "stratum": page2stratum[page], "status": res["status"],
            "n_notes": res.get("n_notes"), "hebrew": heb,
            "extracted": [{"marker": n["marker"], "text": n["text"]} for n in notes],
            "stored": stored_defs(body),
            "anchor": {"status": m.get("status"), "n_anchors": m.get("n_anchors"),
                       "unanchored": [{"marker": u.get("marker"), "expected": u.get("expected_letter"),
                                       "reason": u.get("reason")} for u in m.get("unanchored", [])]},
            "recrop_changes": res.get("recrop_changes", []),
            "dropped_furniture": res.get("dropped_furniture", []),
        }
        results.append(rec)
        # save the presplit strip for the interface; if presplit blanks (misdetected rule /
        # anomalous layout, e.g. p86), fall back to the FULL PAGE so the reviewer never sees white
        import cv_footnote_presplit as ps
        import numpy as np
        from PIL import Image
        strip, _ = ps.presplit(str(img), upscale=2)
        blank = strip is None or (np.asarray(strip.convert("L")) < 128).mean() < 0.002
        if blank:
            strip = Image.open(img)  # full page — anomalous geometry, show everything
            print(f"  p{page}: presplit strip blank -> full-page fallback", flush=True)
        strip.convert("L").save(out / f"strip_{page}.png")
        print(f"p{page} [{rec['stratum']}]: {rec['status']} notes={rec['n_notes']} heb={heb} "
              f"flagged={len(rec['anchor']['unanchored'])} recrop={len(rec['recrop_changes'])}", flush=True)
    (out / "truthset_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    # summary
    from collections import Counter
    st = Counter(r["status"] for r in results); fl = sum(len(r["anchor"]["unanchored"]) for r in results)
    print(f"\n=== {len(results)} pages | statuses: {dict(st)} | total flagged (fail-loud) anchors: {fl} ===")
    print(f"written -> {out/'truthset_results.json'}")

if __name__ == "__main__": main()
