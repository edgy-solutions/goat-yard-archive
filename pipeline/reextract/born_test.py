"""Config-v2 Seam 1 born-test runner. Runs the 47-page adjudicated truthset (+ the reset fixtures p90, p403)
through the BAML typed-Note[] seam and writes a run jsonl reconcile_vol1_run.py can score for
reproduction-drift against the signed verdicts. This is the equivalence gate for the seam swap (NEXT_CONFIG
Seam 1): same weights (qwen3.6-16k:35b), same num_ctx (16384), so drift ~ 0 proves the typed seam reproduces
the frozen /api/generate config on the pages that were adjudicated.

Unlike the frozen run_vol1.py this PERSISTS the config-v2 contract fields (marker_letter, status, partial) —
the letter the chain-walk needs and the typed self-report — beside the canonical [^N]. Checkpointed/resumable.
Env: OLLAMA_HOST default 192.168.1.169 (the qwen3.6-16k host)."""
import sys, os, re, json, time, hashlib, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import assembler as A
from extract_apparatus import extract_page
from run_header import build_header
from data_config import data_path

IMGDIR = Path(os.getenv("VOL1_IMG", "c:/Users/cnogr/git/dr-voluminous/commentary/volume1"))
BODYDIR = IMGDIR / "qwen_qwen3-vl-235b-a22b-thinking"
OUT = Path(os.getenv("BORN_OUT", str(data_path("born_test_baml.jsonl"))))
HOST = os.getenv("OLLAMA_HOST", "192.168.1.169")
PROFILE = Path(__file__).parent / "book_profile.gill.yaml"
BAML_SRC = Path(__file__).resolve().parent.parent.parent / "baml_src" / "gill_apparatus.baml"
MANIFEST = data_path("audits", "sitting_manifest_span_adjudication.json")
FIXTURES = [90, 403]                                       # reset fixtures born-tested against resets_observed


def truthset_pages():
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    spans = man.get("disagreement", []) + man.get("agreed_sample", [])
    return sorted({s["page"] for s in spans})


def header(pages):
    try:
        head = subprocess.check_output(["git", "-C", str(Path(__file__).parent), "rev-parse", "HEAD"]).decode().strip()
    except Exception:
        head = "unknown"
    prof = hashlib.sha256(PROFILE.read_bytes()).hexdigest()[:16] if PROFILE.exists() else "missing"
    # config hash covers the WHOLE seam, not just the model: model tag + endpoint + think + the BAML file
    # (client def + prompt + output schema). If any of these move, the header changes and drift is re-provable.
    baml = hashlib.sha256(BAML_SRC.read_bytes()).hexdigest()[:16] if BAML_SRC.exists() else "missing"
    # The machine is part of the configuration (Chris's ruling, 2026-09-20): endpoint ID, host:port and
    # model digest go in the header AND into config_sha16. `git_head`/`profile_sha16` above are computed by
    # build_header; baml_sha16 stays IN the hash via identity_extra so the seam discipline is not flattened.
    return build_header(
        host=HOST, model="qwen3.6-16k:35b", profile_path=PROFILE,
        identity_extra={"seam": "baml", "api_path": "/api/chat", "think": False,
                        "baml_src": BAML_SRC.name, "baml_sha16": baml},
        extra={"profile": PROFILE.name, "extractor": "extract_apparatus.extract_page", "pages": pages})


def done_pages():
    if not OUT.exists(): return set()
    d = set()
    for line in OUT.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
            if r.get("kind") != "config_header": d.add(r["page"])
        except Exception: pass
    return d


def main():
    profile = A.load_profile(str(PROFILE))
    pages = sorted(set(truthset_pages()) | set(FIXTURES))
    done = done_pages()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fresh = not OUT.exists() or OUT.stat().st_size == 0
    print(f"born-test seam=baml -> {OUT}\n  {len(pages)} pages ({len(pages)-len(done)} to go), host {HOST}", flush=True)
    with OUT.open("a", encoding="utf-8") as f:
        if fresh:
            f.write(json.dumps(header(pages), ensure_ascii=False) + "\n"); f.flush()
        for i, pg in enumerate(pages):
            if pg in done: continue
            img = IMGDIR / f"page{pg}_image1.png"
            if not img.exists():
                f.write(json.dumps({"page": pg, "status": "NO_IMAGE"}) + "\n"); f.flush(); continue
            body = BODYDIR / f"{img.stem}.md"
            t0 = time.perf_counter()
            try:
                r = extract_page(str(img), profile, HOST, body_md=str(body) if body.exists() else None, seam="baml")
                m = r.get("anchor_match") or {}
                rec = {"page": pg, "status": r.get("status"), "n_notes": r.get("n_notes"),
                       # config-v2 persistence: marker_letter + status + partial travel WITH the note.
                       "notes": [{"marker": n["marker"], "text": n["text"],
                                  "marker_letter": n.get("marker_letter"), "note_status": n.get("status"),
                                  "partial": n.get("partial")} for n in r.get("notes", [])],
                       "hebrew": any(re.search(r"[֐-׿]", n["text"]) for n in r.get("notes", [])),
                       "anchor_status": m.get("status"), "dropped_furniture": len(r.get("dropped_furniture", [])),
                       "marker_leaks": r.get("marker_leaks", 0), "secs": round(time.perf_counter() - t0, 1)}
            except Exception as e:
                rec = {"page": pg, "status": "ERROR", "error": str(e)[:200], "secs": round(time.perf_counter() - t0, 1)}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
            print(f"  p{pg} [{rec['status']}] notes={rec.get('n_notes')} ({i+1}/{len(pages)}) {rec.get('secs')}s", flush=True)
    print("DONE born-test", flush=True)
    # STATUS DISTRIBUTION — the enum's first live measurement. A meaningful fraction of truncated_*/
    # no_footnote_present is the geometry stage telling on itself through the reader (which crops to fix first).
    from collections import Counter
    rows = [json.loads(l) for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip()]
    note_stat = Counter(n.get("note_status") for r in rows if r.get("kind") != "config_header" for n in (r.get("notes") or []))
    page_stat = Counter(r.get("status") for r in rows if r.get("kind") != "config_header")
    total = sum(note_stat.values())
    npages = sum(1 for r in rows if r.get("kind") != "config_header")
    print(f"\n--- per-NOTE status distribution ({total} notes across {npages} pages) ---")
    for s, c in note_stat.most_common():
        print(f"  {s:20} {c:4}  ({100*c/max(1,total):.1f}%)")
    print(f"--- per-PAGE status: {dict(page_stat)}")
    leaks = sum(r.get("marker_leaks", 0) for r in rows if r.get("kind") != "config_header")
    print(f"--- marker-leak strips: {leaks} (of {total} notes; a rising rate = the prompt tightening isn't holding)")

    # FIXTURE LETTER ASSERTION — count and structure are not enough. A page can carry the right number of
    # notes in the right shape with every marker letter wrong, and since the chain IS the count authority a
    # wrong letter is a wrong authority, silently. Assert the persisted marker_letter against the ratified
    # reset records. EXPECTED-RED today (p90, p403); the per-note crop path is what turns it green.
    import fixture_assert as FA
    print("\n--- reset-fixture marker LETTERS vs ratified record ---")
    recs, _off = FA.load_records()
    for pg in FIXTURES:
        obs = FA.letters_from_run(OUT, pg)
        if obs is None:
            print(f"  p{pg}: not in run"); continue
        r = FA.check_page(pg, obs, recs)
        if r["ok"] is None:
            print(f"  p{pg}: UNASSERTABLE — {r['why']}"); continue
        print(f"  p{pg}: letters_ok={r['letters_ok']} series_ok={r['series_ok']} "
              f"count_ok={r['count_ok']}  expected={','.join(r['expected_flat'])} "
              f"observed={','.join(r['observed_flat'])}")
    print("  (run `python test_born_fixtures.py` for the full report; red is the correct state today)")


if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    main()
