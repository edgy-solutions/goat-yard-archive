"""Copy an eval run's output into the PRIVATE repo, so a run is evidence and not a local file.

    python evals/publish_run.py evals/output/noise_floor/nf1_20260927 --also nf1_20260927.log

Ruling 3 (2026-09-27, Chris): every eval run copies its output to
`dr-voluminous/body_shadow_vol1/evals/<run_id>/`, committed by EXPLICIT PATH, before the report
is written. `evals/output/` is gitignored in the public repo, so an unpublished run is evidence
that exists on exactly one machine -- which is what the noise-floor pair was until this script.

Two things this script refuses to do, both deliberate:

  - It will not publish a directory with no `summary.json`. A run that did not write a summary
    is not a run, and copying its fragments would create an artifact that looks like evidence.
  - It will not overwrite an already-published run id without `--replace`. Re-running an arm
    under a name that is already published is how two different measurements become one.

`PUBLISHED.json` carries the sha256 of every copied file AND a verbatim echo of the run's
`integrity.git` block, so the copy states on its own whether the run was clean (ruling 1: clean
means git_state() at start and end both clean and identical). A published run whose
`provisional` is true cannot be cited in an ADR or a tier change no matter who quotes it later.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import sys
import time

DEST_ROOT_DEFAULT = "C:/Users/cnogr/git/dr-voluminous/body_shadow_vol1/evals"


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with io.open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def integrity_git_of(run_dir: str) -> dict:
    """The run's own statement about tree cleanliness, echoed into the published copy.

    Absent on runs written before `b7d82dc`; recorded as absent rather than as clean, because
    "no information" and "was clean" are different facts and only one of them is citable.
    """
    p = os.path.join(run_dir, "summary.json")
    try:
        s = json.load(io.open(p, "r", encoding="utf-8"))
    except Exception as exc:
        return {"unavailable": f"{type(exc).__name__}: {exc}"}
    git = (s.get("integrity") or {}).get("git")
    if git is None:
        return {"unavailable": "summary.json has no integrity.git block (run predates b7d82dc); "
                               "cleanliness of the tree at run time is UNKNOWN, not clean"}
    return git


def verify(published_dir: str) -> dict:
    """Recompute every sha256 in PUBLISHED.json against the files actually on disk.

    Exists because the first published pair did NOT verify: `core.autocrlf=input` stored LF
    blobs while the manifest hashed the CRLF working copy, so every recorded hash was wrong
    from a fresh checkout (nf1_20260927/summary.json: recorded 7dd7f4fd..., blob c1de313f...).
    A `.gitattributes` entry marking the evidence tree `-text` is the fix; this is the check
    that would have caught it, and it is the check that catches the next one.

    Returns a report; the caller decides whether to exit non-zero. `missing` and `mismatch` are
    kept separate because a deleted file and an altered file are different failures.
    """
    mpath = os.path.join(published_dir, "PUBLISHED.json")
    if not os.path.isfile(mpath):
        sys.exit(f"publish_run --verify: no PUBLISHED.json in {published_dir}")
    m = json.load(io.open(mpath, "r", encoding="utf-8"))
    ok, mismatch, missing = [], [], []
    for name, want in sorted(m.get("files", {}).items()):
        fp = os.path.join(published_dir, name)
        if not os.path.isfile(fp):
            missing.append(name)
            continue
        got = sha256_of(fp)
        (ok if got == want else mismatch).append(name if got == want else (name, want[:16], got[:16]))
    return {"run_id": m.get("run_id"), "checked": len(m.get("files", {})),
            "ok": len(ok), "mismatch": mismatch, "missing": missing,
            "verified": not mismatch and not missing}


def publish(run_dir: str, run_id: str, dest_root: str, also: list, replace: bool) -> str:
    run_dir = os.path.abspath(run_dir)
    if not os.path.isdir(run_dir):
        sys.exit(f"publish_run: not a directory: {run_dir}")
    if not os.path.isfile(os.path.join(run_dir, "summary.json")):
        sys.exit(f"publish_run: {run_dir} has no summary.json. A run that wrote no summary is "
                 f"not a run; refusing to publish its fragments as evidence.")
    dest = os.path.join(dest_root, run_id)
    if os.path.isdir(dest) and os.listdir(dest):
        if not replace:
            sys.exit(f"publish_run: {dest} is already published and non-empty. Pass --replace only "
                     f"if you mean to overwrite a PUBLISHED measurement with a different one.")
        shutil.rmtree(dest)
    os.makedirs(dest, exist_ok=True)

    copied = []
    for name in sorted(os.listdir(run_dir)):
        src = os.path.join(run_dir, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(dest, name))
            copied.append(name)
    for extra in also:
        src = extra if os.path.isabs(extra) else os.path.join(os.path.dirname(run_dir), extra)
        if not os.path.isfile(src):
            sys.exit(f"publish_run: --also {extra} does not exist at {src}. Named and missing is "
                     f"an error, not a skip.")
        base = os.path.basename(src)
        shutil.copy2(src, os.path.join(dest, base))
        copied.append(base)

    manifest = {
        "run_id": run_id,
        "published_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source_dir": run_dir,
        "files": {name: sha256_of(os.path.join(dest, name)) for name in copied},
        "integrity_git": integrity_git_of(run_dir),
        "ruling": "ruling 3, 2026-09-27: published before the report, committed by explicit path",
    }
    io.open(os.path.join(dest, "PUBLISHED.json"), "w", encoding="utf-8").write(
        json.dumps(manifest, indent=2, sort_keys=True))
    return dest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--run-id", default=None, help="defaults to the run directory's basename")
    ap.add_argument("--dest-root", default=DEST_ROOT_DEFAULT)
    ap.add_argument("--also", action="append", default=[],
                    help="extra file (log, prediction, arm diff) to publish beside the run")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--verify", action="store_true",
                    help="treat run_dir as an ALREADY-PUBLISHED dir and check its "
                         "recorded hashes against the bytes on disk")
    a = ap.parse_args()
    if a.verify:
        r = verify(a.run_dir)
        print(f"{r['run_id']}: {r['ok']}/{r['checked']} files verify")
        for row in r["mismatch"]:
            print(f"  MISMATCH {row[0]}: recorded {row[1]}... on disk {row[2]}...")
        for name in r["missing"]:
            print(f"  MISSING  {name}")
        sys.exit(0 if r["verified"] else 1)
    run_id = a.run_id or os.path.basename(os.path.normpath(a.run_dir))
    dest = publish(a.run_dir, run_id, a.dest_root, a.also, a.replace)
    n = len(json.load(io.open(os.path.join(dest, "PUBLISHED.json"), "r", encoding="utf-8"))["files"])
    print(f"published {n} files -> {dest}")
    rel = os.path.relpath(dest, os.path.dirname(os.path.dirname(a.dest_root.rstrip('/'))))
    print("")
    print("Now commit it, by explicit path, in dr-voluminous:")
    print(f"  git add {rel.replace(os.sep, '/')}")
    print("  git commit -m 'evidence(eval): publish run " + run_id + "'")


if __name__ == "__main__":
    main()
