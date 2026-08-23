"""vol7 apparatus measurement — run ~19 vol7 (NT) apparatus pages through the SAME re-extraction pipeline
and render for one console glance. vol7 ingests on MEASUREMENT, not architecture-similarity: its markers
differ (digit/symbol, not a-z), its front matter is shorter, its Hebrew density is its own. This run
shows what the vol1-tuned pipeline actually does on vol7 — where it holds, where vol7 needs its own
profile facts. Emits the same truthset_results.json the console renders."""
import sys, os, re, io, json, base64
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import assembler as A
from extract_apparatus import extract_page
import cv_footnote_presplit as ps

IMG7 = "c:/Users/cnogr/git/dr-voluminous/commentary/volume7"
GREEK = re.compile(r"[\u0370-\u03FF]")       # vol7 (NT) apparatus is mostly GREEK
HEBREW = re.compile(r"[\u0590-\u05FF]")       # + rabbinic Hebrew citations

def main():
    host = os.getenv("OLLAMA_HOST", "192.168.1.179")
    profile = A.load_profile(str(Path(__file__).parent / "book_profile.gill_vol7.yaml"))
    out = Path(__file__).parent / "vol7_out"; out.mkdir(exist_ok=True)
    pages = json.loads((Path(__file__).parent / "vol7_sample.json").read_text())
    results = []
    for pg in pages:
        img = f"{IMG7}/page{pg}_image1.png"
        if not Path(img).exists():
            print(f"p{pg}: MISSING IMAGE", flush=True); continue
        body = f"{IMG7}/page{pg}_image7.md"     # vol7 body OCR uses _image7.md (vol1 used _image1.md)
        res = extract_page(img, profile, host, body_md=body if Path(body).exists() else None)
        notes = res.get("notes", [])
        joined = " ".join(n["text"] for n in notes)
        grk = bool(GREEK.search(joined)); heb = bool(HEBREW.search(joined))
        m = res.get("anchor_match") or {}
        results.append({
            "page": pg, "stratum": "vol7_sample", "status": res["status"], "n_notes": res.get("n_notes"),
            "hebrew": heb, "greek": grk, "extracted": [{"marker": n["marker"], "text": n["text"]} for n in notes],
            "stored": [], "anchor": {"status": m.get("status"), "n_anchors": m.get("n_anchors"),
                                     "unanchored": [{"marker": u.get("marker"), "expected": u.get("expected_letter")}
                                                    for u in m.get("unanchored", [])]},
            "recrop_changes": res.get("recrop_changes", []), "dropped_furniture": res.get("dropped_furniture", []),
        })
        strip, _ = ps.presplit(img, upscale=2)
        if strip is not None:
            s = strip.convert("L")
            if s.size[0] > 1600: s = s.resize((1600, int(s.size[1]*1600/s.size[0])))
            s.save(out / f"strip_{pg}.png")
        print(f"p{pg}: {res['status']} notes={res.get('n_notes')} greek={grk} heb={heb} "
              f"reason={res.get('reason','-')}", flush=True)
    (out / "truthset_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    st = Counter(r["status"] for r in results)
    print(f"\n=== vol7 measurement: {len(results)} pages | statuses {dict(st)} | "
          f"greek {sum(1 for r in results if r['greek'])} | hebrew {sum(1 for r in results if r['hebrew'])} | "
          f"notes {sum(r['n_notes'] or 0 for r in results)} ===")
    print(f"written -> {out}/truthset_results.json")

if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    main()
