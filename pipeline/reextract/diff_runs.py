"""STEP 3 — the diff that answers the open architectural question: does per-note pre-segmentation
dissolve the segmentation-collapse class and demote the router (gemma->qwen3.8 dispatch) from primary
defense to residual handler? Compares the router baseline (overnight_out.json failure rows) against the
per-note run (per_note_run_out.json) on the same failure set.

The decisive number: on the pages the ROUTER needed the qwen3.8 fallback for (p129/p146), does per-note
recover them with gemma alone? If yes, the pixels retired that part of the model race."""
import sys, json
from pathlib import Path
HERE = Path(__file__).parent

def load(p):
    d = json.loads((HERE / p).read_text()) if (HERE / p).exists() else None
    return d

def main(base_path, pn_path):
    base = {r["page"]: r for r in json.loads(Path(base_path).read_text())["failure"]}
    pn = {r["page"]: r for r in json.loads(Path(pn_path).read_text())}
    FAIL_EXPECT = {129: 13, 146: 13, 163: 18, 226: 20, 393: 8, 625: 3, 725: 9, 784: 7}
    print(f"{'page':>5} {'exp':>4} {'cv':>4} | {'router_n':>8} {'route':>9} | {'pernote_n':>9} {'mode':>11} | verdict")
    router_rec = pernote_rec = 0
    fallback_dissolved = []
    for pg, exp in sorted(FAIL_EXPECT.items()):
        b = base[pg]; p = pn[pg]
        rr = b["final_n"] >= 0.7 * exp; pr = p["final_n"] >= 0.7 * exp
        router_rec += rr; pernote_rec += pr
        verd = "per-note holds" if pr else "per-note MISS"
        if b["route"] == "fallback" and pr and p["mode"] == "per-note":
            fallback_dissolved.append(pg); verd = "DISSOLVED (gemma-per-note = qwen3.8-fallback)"
        print(f"{pg:>5} {exp:>4} {b['cv']:>4} | {b['final_n']:>8} {b['route']:>9} | "
              f"{p['final_n']:>9} {p['mode']:>11} | {verd}")
    seg = list(FAIL_EXPECT)
    print(f"\nsegmentation recovered: router {router_rec}/{len(seg)}  |  per-note {pernote_rec}/{len(seg)}")
    print(f"router fallback pages dissolved by per-note (gemma alone): {fallback_dissolved}")
    # Hebrew axis (what remains after segmentation is dissolved)
    hb = {r["page"]: r for r in json.loads(Path(pn_path).read_text())}
    heb_pages = [pg for pg, r in hb.items() if r.get("expect") is None]
    print(f"per-note Hebrew present on {sum(1 for pg in heb_pages if hb[pg]['hebrew'])}/{len(heb_pages)} hebrew/lemma pages")
    pn_mode = sum(1 for r in pn.values() if r["mode"] == "per-note")
    print(f"per-note mode engaged: {pn_mode}/{len(pn)} (rest fell back to whole-strip on low CV confidence)")
    if fallback_dissolved:
        print("\n-> Per-note dissolves the router's fallback need on those pages: the router is demoted")
        print("   to RESIDUAL handler for the low-CV-confidence pages per-note can't pre-segment.")

if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    main(sys.argv[1], sys.argv[2])
