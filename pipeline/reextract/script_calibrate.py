"""Calibrate the script-presence probe battery against the jaws (Build 1). Runs all three probes on
every jaw page, computes a confusion matrix per probe for HEBREW presence, and reports the decisive
cases: the p674 transliteration trap (must read hebrew=0) and the worn-glyph pages (does presence-
detection survive where transcription died?). Confusion matrices written as the committed calibration
artifact. Tests the prediction: script-list >= yes/no >= counts."""
import sys, os, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import cv_footnote_presplit as ps
import script_probe as SP
from script_jaws import JAWS, TRAP, WORN

IMG = "c:/Users/cnogr/git/dr-voluminous/commentary/volume1"

def confusion(pred, truth):
    tp = sum(1 for p, t in zip(pred, truth) if p and t); tn = sum(1 for p, t in zip(pred, truth) if not p and not t)
    fp = sum(1 for p, t in zip(pred, truth) if p and not t); fn = sum(1 for p, t in zip(pred, truth) if not p and t)
    n = len(pred); P = tp/(tp+fp) if tp+fp else 1.0; R = tp/(tp+fn) if tp+fn else 1.0
    return {"tp": tp, "tn": tn, "fp": fp, "fn": fn, "precision": round(P, 3), "recall": round(R, 3),
            "accuracy": round((tp+tn)/n, 3) if n else 0}

def main():
    host = os.getenv("OLLAMA_HOST", "192.168.1.169"); model = os.getenv("PROBE_MODEL", "gemma4:31b")
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "script_calibration.json"
    pages = sorted(JAWS); rows = []; t0 = time.time()
    print(f"calibrating on {len(pages)} jaw pages, model={model}", flush=True)
    for pg in pages:
        strip, _ = ps.presplit(f"{IMG}/page{pg}_image1.png", upscale=2)
        b = SP.run_battery(strip, host, model)
        rows.append({"page": pg, "truth_hebrew": JAWS[pg]["hebrew"], "trap": JAWS[pg].get("trap", False),
                     "worn": JAWS[pg].get("worn", False),
                     "yesno": b["yesno"]["hebrew"], "list": b["scriptlist"]["hebrew"],
                     "counts": b["counts"]["hebrew"], "n_counts": b["counts"]["n_hebrew"],
                     "list_raw": b["scriptlist"]["raw"]})
        print(f"  p{pg}: truth={JAWS[pg]['hebrew']} yn={b['yesno']['hebrew']} "
              f"list={b['scriptlist']['hebrew']} cnt={b['counts']['n_hebrew']}", flush=True)
    truth = [r["truth_hebrew"] == 1 for r in rows]
    matrices = {probe: confusion([r[probe] for r in rows], truth) for probe in ("yesno", "list", "counts")}
    trap = {pg: {p: [r for r in rows if r["page"] == pg][0][p] for p in ("yesno", "list", "counts")} for pg in TRAP}
    worn = {pg: {p: [r for r in rows if r["page"] == pg][0][p] for p in ("yesno", "list", "counts")} for pg in WORN}
    result = {"model": model, "n_pages": len(pages), "matrices": matrices, "trap": trap, "worn": worn, "rows": rows}
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n=== CALIBRATION ({time.time()-t0:.0f}s) ===")
    for probe in ("yesno", "list", "counts"):
        m = matrices[probe]; print(f"  {probe:>10}: acc={m['accuracy']} P={m['precision']} R={m['recall']} "
                                   f"(fp={m['fp']} fn={m['fn']})")
    print(f"  TRAP p674 (must be all-False): {trap}")
    print(f"  WORN (Hebrew present, transcription died — does detection survive?): {worn}")
    print(f"written -> {out}")

if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    main()
