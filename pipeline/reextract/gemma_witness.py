"""Overnight step 3 — gemma dual-witness via the same typed seam. Runs gemma4-32k:31b as a SECOND reader over
the truthset pages (native /api/chat, think:false, model override on the same BAML request), and runs the
agreement ladder against the STORED qwen reading (born_test_baml.jsonl) — so only gemma is re-read, not both.
Reports per-page ladder rung (count/script/text/agree), the disagreement-queue size, and, for the 20 Hebrew
sitting spans, qwen-vs-gemma per span. Build-and-measure only; checkpointed. Output to the private root.

NOTE: the CV count third-witness (adjudicate_count) is deliberately NOT used as referee here — tonight's
collapse run showed the note-start detector over-counts on body-heavy pages, so it is not a trustworthy
count yardstick right now (see MORNING_SUMMARY step 4)."""
import sys, os, re, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import assembler as A
from extract_apparatus import extract_page
import agreement_ladder as AL
from data_config import data_path

IMG = Path("c:/Users/cnogr/git/dr-voluminous/commentary/volume1")
QWEN = data_path("born_test_baml.jsonl")
OUT = Path(os.getenv("GEMMA_OUT", str(data_path("gemma_witness.jsonl"))))
HOST = os.getenv("OLLAMA_HOST", "192.168.1.169")
GEMMA = "gemma4-32k:31b"
PROFILE = Path(__file__).parent / "book_profile.gill.yaml"
HEB_SPANS = data_path("audits", "hebrew_sample_20260906.json")


def done_pages():
    if not OUT.exists(): return set()
    d = set()
    for l in OUT.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(l)
            if r.get("kind") != "config_header": d.add(r["page"])
        except Exception: pass
    return d


def main():
    profile = A.load_profile(str(PROFILE))
    qrows = [json.loads(l) for l in QWEN.read_text(encoding="utf-8").splitlines() if l.strip()]
    qpages = {r["page"]: r for r in qrows if r.get("kind") != "config_header"}
    targets = sorted(qpages)
    done = done_pages()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fresh = not OUT.exists() or OUT.stat().st_size == 0
    print(f"gemma witness -> {OUT}\n  {len(targets)} pages ({len(targets)-len(done)} to go), model {GEMMA}", flush=True)
    with OUT.open("a", encoding="utf-8") as f:
        if fresh:
            f.write(json.dumps({"kind": "config_header", "witness_model": GEMMA, "endpoint": "/api/chat",
                                "think": False, "primary": "qwen3.6-16k:35b", "host": HOST,
                                "started": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False) + "\n")
        for i, pg in enumerate(targets):
            if pg in done: continue
            img = IMG / f"page{pg}_image1.png"
            if not img.exists():
                f.write(json.dumps({"page": pg, "status": "NO_IMAGE"}) + "\n"); continue
            t0 = time.perf_counter()
            try:
                g = extract_page(str(img), profile, HOST, seam="baml", model=GEMMA)
                gnotes = [{"text": n["text"], "marker_letter": n.get("marker_letter")} for n in g.get("notes", [])]
                qnotes = [{"text": n["text"]} for n in qpages[pg].get("notes", [])]
                lad = AL.ladder(qnotes, gnotes)
                rec = {"page": pg, "rung": lad["rung"], "agree": lad["agree"], "count": lad["count"],
                       "script_diffs": lad["script_diffs"], "text_diffs": lad["text_diffs"],
                       "gemma_notes": gnotes, "secs": round(time.perf_counter() - t0, 1)}
            except Exception as e:
                rec = {"page": pg, "status": "ERROR", "error": str(e)[:200], "secs": round(time.perf_counter() - t0, 1)}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
            print(f"  p{pg} rung={rec.get('rung')} agree={rec.get('agree')} count={rec.get('count')} "
                  f"({i+1}/{len(targets)}) {rec.get('secs')}s", flush=True)
    print("DONE gemma witness", flush=True)
    # SUMMARY
    from collections import Counter
    rows = [json.loads(l) for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip()]
    pgs = [r for r in rows if r.get("kind") != "config_header" and "rung" in r]
    rung = Counter(r["rung"] for r in pgs)
    disagree = [r["page"] for r in pgs if not r.get("agree")]
    print(f"\n--- ladder rung distribution: {dict(rung)} of {len(pgs)} pages ---")
    print(f"--- disagreement queue ({len(disagree)} pages): {disagree}")
    # Hebrew-span dual-witness
    spans = json.loads(HEB_SPANS.read_text(encoding="utf-8"))
    gpages = {r["page"]: r for r in pgs}
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print(f"--- Hebrew sitting spans ({len(spans)}): qwen vs gemma ---")
    agree_h = 0
    for s in spans:
        pg, idx = s["page"], s["note_idx"]
        g = gpages.get(pg)
        if not g or idx >= len(g.get("gemma_notes", [])):
            print(f"  {s['span_id']}: gemma has no note[{idx}] (count/align)"); continue
        gtext = g["gemma_notes"][idx]["text"]
        ov = AL._tokens(s["run_text"]) & AL._tokens(gtext)
        tot = AL._tokens(s["run_text"]) | AL._tokens(gtext)
        j = len(ov) / max(1, len(tot))
        ok = j >= 0.6
        agree_h += int(ok)
        print(f"  {s['span_id']} overlap={j:.2f} {'AGREE' if ok else 'DISAGREE'}")
    print(f"--- Hebrew spans agree: {agree_h}/{len(spans)} (disagreements are the gemma-adjudication queue)")


if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    main()
