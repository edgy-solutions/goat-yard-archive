"""Full-vol1 INSTRUMENTED dry-run — the first corpus-scale look (the answer to the two-volume dread:
the unknown-unknowns tail surfaces in ONE batch, not one dreaded page at a time). ~870-958 pages
through the CURRENT pipeline (gated recrop on), every assertion armed, accumulating per-page:
status, note count, Hebrew flag, anchor-match summary + fail-loud unanchored counts, recrop
accept/gated stats, presplit mode + footnote-gutter + rule geometry, furniture dropped.

CHECKPOINTED per-page (JSONL append): a crash RESUMES (skips pages already in the file), never
restarts. Re-running when stage-3 changes outputs is free. Summarize with summarize_vol1.py.
Env: OLLAMA_HOST -- required, no default (gpu-servers.md; E/.179 and F/.188 refused).
"""
import sys, os, re, json, time, hashlib, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from endpoint_guard import resolve_host, EndpointMissing, EndpointRefused
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import assembler as A
from extract_apparatus import extract_page
from data_config import data_path                      # the one data root (private dr-voluminous)

IMGDIR = Path(os.getenv("VOL1_IMG", "c:/Users/cnogr/git/dr-voluminous/commentary/volume1"))
BODYDIR = IMGDIR / "qwen_qwen3-vl-235b-a22b-thinking"
# output is DATA -> private root, never the code tree (default), overridable with VOL1_OUT
OUT = Path(os.getenv("VOL1_OUT", str(data_path("vol1_apparatus.jsonl"))))
PROFILE = Path(__file__).parent / "book_profile.gill.yaml"

def config_hash():
    """Answerable provenance: the code commit + the profile bytes this run extracts under. The full run
    must PROVE it is the same pipeline the 47-page truthset was adjudicated against — this hash is how."""
    try:
        head = subprocess.check_output(["git", "-C", str(Path(__file__).parent), "rev-parse", "HEAD"]).decode().strip()
    except Exception:
        head = "unknown"
    prof = hashlib.sha256(PROFILE.read_bytes()).hexdigest()[:16] if PROFILE.exists() else "missing"
    return {"kind": "config_header", "git_head": head, "profile_sha16": prof,
            "profile": PROFILE.name, "extractor": "extract_apparatus.extract_page",
            "started": time.strftime("%Y-%m-%dT%H:%M:%S")}

def refine_status(r):
    """Split the coarse 'no_apparatus' into WHY, for the next run's observability (this run reconciles
    as-is). Read from the fields extract_page already returns — no change to the frozen extractor:
      NO_BAND        — geometry found no footnote rule (presplit returned no band)
      CROP_REFUSED   — the crop gate declined (blank/near-blank crop went through the gate)
      READER_EMPTY   — a band was present but the reader returned nothing (incl. an honest refusal)
      FRONT_MATTER   — before commentary_start_page; a deliberate skip, not a detection
    Everything else (OK / ANCHOR_* / STITCH_VIOLATION / *_SUSPECT) passes through unchanged."""
    if r.get("status") != "no_apparatus":
        return r.get("status")
    reason = r.get("reason")
    if reason == "front_matter":   return "FRONT_MATTER"
    if reason == "model-refusal":  return "READER_EMPTY"
    if "crop_gate" in r:           return "CROP_REFUSED"
    if "info" in r and not r.get("notes"): return "NO_BAND"
    return "READER_EMPTY"

def done_pages():
    if not OUT.exists(): return set()
    d = set()
    for line in OUT.read_text(encoding="utf-8").splitlines():
        try: d.add(json.loads(line)["page"])
        except Exception: pass
    return d

def main():
    # BEFORE the first page loads. Lane B's first patch to nikud_audit_run put the guard after a
    # module-level data load and died on a missing file instead of on the endpoint - a non-zero
    # exit for the wrong reason, which reads as a firing guard and is not one.
    try:
        host = resolve_host(os.getenv("OLLAMA_HOST"), who="run_vol1")
    except (EndpointMissing, EndpointRefused) as e:
        print("", file=sys.stderr); print(e, file=sys.stderr); return 2
    # This tree builds "http://<host>:11434/..." itself (extract_apparatus.py:55), so a host
    # carrying its own port or scheme silently produces a malformed URL that fails at connect
    # time with a confusing error. resolve_host returns the value as given, by design, so the
    # SHAPE check belongs here. Refuse rather than strip: stripping would send the run to
    # :11434 on a machine where a different port was asked for, and write a host nobody chose
    # into the artifacts. NOTE this means endpoint D (192.168.1.169:11435) is UNREACHABLE from
    # this script until the hardcoded :11434 is widened - shared URL construction, not changed here.
    if "://" in host or host.count(":") == 1:
        print("", file=sys.stderr)
        print("REFUSED: run_vol1 needs a BARE host. It builds http://<host>:11434/... itself,",
              file=sys.stderr)
        print("  so " + repr(host) + " would become a malformed URL.", file=sys.stderr)
        print("  Pass just the address, e.g. 192.168.1.169.", file=sys.stderr)
        print("  Note endpoint D (192.168.1.169:11435) cannot be reached from here: the",
              file=sys.stderr)
        print("  :11434 in the URL is hardcoded. See gpu-servers.md.", file=sys.stderr)
        return 2

    profile = A.load_profile(str(PROFILE))
    imgs = sorted(IMGDIR.glob("page*_image1.png"),
                  key=lambda p: int(re.search(r"page(\d+)", p.name).group(1)))
    done = done_pages()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fresh = not OUT.exists() or OUT.stat().st_size == 0
    print(f"vol1 -> {OUT}\n  {len(imgs)} images, {len(done)} already done, {len(imgs)-len(done)} to go", flush=True)
    with OUT.open("a", encoding="utf-8") as f:
        if fresh:                                        # pin provenance as the first line of a fresh run
            hdr = config_hash(); f.write(json.dumps(hdr, ensure_ascii=False) + "\n"); f.flush()
            print(f"  config: git {hdr['git_head'][:12]} profile {hdr['profile_sha16']}", flush=True)
        for i, img in enumerate(imgs):
            pg = int(re.search(r"page(\d+)", img.name).group(1))
            if pg in done: continue
            body = str(BODYDIR / f"{img.stem}.md")
            t0 = time.perf_counter()
            try:
                r = extract_page(str(img), profile, host, body_md=body if Path(body).exists() else None)
                rc = r.get("recrop_changes", []); m = r.get("anchor_match") or {}
                info = r.get("presplit_info") or {}
                rec = {"page": pg, "status": refine_status(r), "n_notes": r.get("n_notes"),
                       # THE INGESTABLE ARTIFACT: per-note marker + text, persisted (the 08-10 dry-run
                       # counted then discarded this — which is why it produced no ingest candidate).
                       "notes": [{"marker": n["marker"], "text": n["text"]} for n in r.get("notes", [])],
                       "hebrew": any(re.search(r"[֐-׿]", n["text"]) for n in r.get("notes", [])),
                       "anchor_status": m.get("status"), "n_anchors": m.get("n_anchors"),
                       "unanchored": len(m.get("unanchored", [])),
                       "recrop_accepted": sum(1 for c in rc if c.get("accepted")),
                       "recrop_gated": sum(1 for c in rc if not c.get("accepted")),
                       "presplit_mode": info.get("mode"), "fn_gutter": info.get("fn_gutter"),
                       "rules": info.get("rules"), "dropped_furniture": len(r.get("dropped_furniture", [])),
                       "secs": round(time.perf_counter() - t0, 1)}
            except Exception as e:
                rec = {"page": pg, "status": "ERROR", "error": str(e)[:200], "secs": round(time.perf_counter() - t0, 1)}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
            if i % 25 == 0:
                print(f"  ...{pg} [{rec['status']}] ({i+1}/{len(imgs)})", flush=True)
    print("DONE vol1 run", flush=True)

if __name__ == "__main__": sys.exit(main() or 0)
