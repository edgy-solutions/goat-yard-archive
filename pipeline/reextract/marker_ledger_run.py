"""CLI driver for marker_ledger.reconcile() (ADR two-series-marker-ledger). Reads a body series
per page from legacy .md files (bracket-style `[^N]` refs, NEVER definitions -- the old numbering
is purely positional and carries no letter information, so each becomes an unresolved '?'
placeholder) and a notes series per page from a notes-jsonl file, then writes one JSON-lines
artifact: a run_header line, one line per slot, then a final run_summary line.

Output is private (derived from a copyrighted scan corpus) -- --out must resolve OUTSIDE both the
goatyard-laneA2 and goat-yard-archive repo roots; validate_out_path() below mirrors the same-named
function in pipeline/scripts/build_page_geometry.py.

--check-legacy-identity DIR is a separate, read-only mode: runs project_legacy() (default 1..N
numbering) over every *.md file under DIR and reports how many come back byte-identical vs changed.
It touches nothing -- a "changed" file just means it still carries live sentinels that a renumbering
sweep would rewrite. Exits 1 if any file would change, so it can gate a migration step.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import marker_ledger as ML  # noqa: E402

TIER = "best_effort"

# Repo roots this writer refuses to write inside, loudly (mirrors build_page_geometry.py).
FORBIDDEN_OUTPUT_ROOTS = [
    Path("C:/Users/cnogr/git/goatyard-laneA"),
    Path("C:/Users/cnogr/git/goat-yard-archive"),
]


class OutputPathRefused(Exception):
    """Raised when the resolved --out path lands inside a forbidden repo root."""


def _is_within(path, root):
    p = os.path.normcase(os.path.normpath(str(path)))
    r = os.path.normcase(os.path.normpath(str(root)))
    return p == r or p.startswith(r + os.sep)


# Also forbid whatever repo THIS file actually lives in, so the guard travels with a worktree
# (e.g. goatyard-laneA2) that isn't literally named "goatyard-laneA".
_SELF_REPO_ROOT = Path(__file__).resolve().parents[2]
if all(not _is_within(_SELF_REPO_ROOT, r.resolve()) for r in FORBIDDEN_OUTPUT_ROOTS):
    FORBIDDEN_OUTPUT_ROOTS.append(_SELF_REPO_ROOT)


def validate_out_path(out_arg):
    """Resolve --out and refuse (raise OutputPathRefused) if it lands inside a forbidden repo
    root. Returns the resolved Path when allowed. Pure path logic -- safe to call before any
    directory is created."""
    resolved = Path(out_arg).resolve()
    for root in FORBIDDEN_OUTPUT_ROOTS:
        root_resolved = root.resolve()
        if _is_within(resolved, root_resolved):
            raise OutputPathRefused(
                f"REFUSED: output path resolves inside forbidden repo root {root_resolved} "
                f"(resolved --out = {resolved}). This is private data; it must never land "
                f"inside a repo root."
            )
    return resolved


# ---------------------------------------------------------------------------
# config / provenance (mirrors build_page_geometry.py's config_hash / git helpers)
# ---------------------------------------------------------------------------

def sha16(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def config_hash(base_config):
    """sha256, first 16 hex chars, of the canonical JSON (sorted keys, no whitespace) of
    base_config -- which must NOT contain the "hash"/"config_hash" key itself."""
    canonical = json.dumps(base_config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def get_git_head(repo_root):
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo_root), capture_output=True, text=True, timeout=30,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return None


def get_git_dirty(repo_root):
    """True/False from `git status --porcelain` (non-empty = dirty), never hand-rolled. None if
    git itself is unavailable."""
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo_root), capture_output=True, text=True, timeout=30,
        )
        if out.returncode == 0:
            return bool(out.stdout.strip())
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# body series: legacy `[^N]` refs (never a `[^N]:` definition line) -> '?' placeholders
# ---------------------------------------------------------------------------

_BODY_REF_RE = re.compile(r"\[\^[^\]]+\](?!:)")


def body_series_from_md(md_text):
    """One '?' placeholder per legacy bracket ref found in the body. The old numbering is purely
    positional (1, 2, 3, ...) and carries no letter information, so this is strictly a COUNT --
    never a guess at the letter underneath it."""
    return ["?" for _ in _BODY_REF_RE.finditer(md_text)]


def load_body_series(body_dir, file_page):
    """page{file_page}_image1_normalized.md -- the normalized legacy text that is the frozen vol.1
    body (898 pages; the raw page{N}_image1.md set is a smaller, earlier layer). Returns None
    (series never captured) if the file is absent -- distinct from an empty list (file present,
    zero refs)."""
    path = Path(body_dir) / f"page{file_page}_image1_normalized.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    return body_series_from_md(text)


# ---------------------------------------------------------------------------
# --notes-jsonl: the v2 reader output (born_test_baml.jsonl shape). One config_header line (no
# "page" key -- skipped), then one record per page: {"page": int, "notes": [{"marker_letter":
# str|None, ...}], ...}. A None marker_letter is an unread marker -> '?', never dropped.
# Optional per-record "notes_cols" (column block sizes) is honoured when present.
# ---------------------------------------------------------------------------

def load_notes(notes_jsonl_path):
    notes_by_page = {}
    cols_by_page = {}
    with open(notes_jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if "page" not in rec:
                continue   # run/config header
            fp = int(rec["page"])
            if fp in notes_by_page:
                raise ValueError(f"load_notes: file page {fp} appears twice in {notes_jsonl_path}")
            notes = rec.get("notes")
            if notes is None:
                raise ValueError(f"load_notes: file page {fp} record has no 'notes' list")
            notes_by_page[fp] = [n.get("marker_letter") or "?" for n in notes]
            if rec.get("notes_cols"):
                cols_by_page[fp] = list(rec["notes_cols"])
    return notes_by_page, cols_by_page


def load_resets(path):
    """--resets-json: {"pages": {"<file_page>": [in-page slot indices]}, ...}. A page present here
    is reset-COMPLETE (every reset on it is listed); absent pages are reset-unknown."""
    if not path:
        return {}
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if "pages" not in raw or not isinstance(raw["pages"], dict):
        raise ValueError(f"load_resets: {path} has no 'pages' object")
    return {int(k): list(v) for k, v in raw["pages"].items()}


def load_anomalies(path):
    """--anomalies-json: the human table (audits/marker_anomalies_observed.json): a top-level
    "pages" LIST of {file_page, kind, observed, ...}. Converted once, here, to
    {file_page: {kind, observed}}."""
    if not path:
        return {}
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = raw.get("pages")
    if not isinstance(rows, list):
        raise ValueError(f"load_anomalies: {path} has no 'pages' list")
    out = {}
    for r in rows:
        fp = int(r["file_page"])
        if fp in out:
            raise ValueError(f"load_anomalies: file page {fp} listed twice in {path}")
        out[fp] = {"kind": r.get("kind"), "observed": r.get("observed")}
    return out


# ---------------------------------------------------------------------------
# --check-legacy-identity
# ---------------------------------------------------------------------------

def check_legacy_identity(dir_path):
    n = n_identical = n_changed = 0
    changed_files = []
    for md_path in sorted(Path(dir_path).glob("*.md")):
        text = md_path.read_text(encoding="utf-8", errors="replace")
        n += 1
        renumbered = ML.project_legacy(text)
        if renumbered == text:
            n_identical += 1
        else:
            n_changed += 1
            changed_files.append(md_path.name)
    print(f"checked: {n}")
    print(f"identical: {n_identical}")
    print(f"changed: {n_changed}")
    for name in changed_files[:20]:
        print(f"  CHANGED: {name}")
    if len(changed_files) > 20:
        print(f"  ... and {len(changed_files) - 20} more")
    return 1 if n_changed else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--notes-jsonl", default=None,
                     help="v2 reader JSONL (born_test_baml.jsonl shape: page, notes[].marker_letter). "
                          "Required unless --check-legacy-identity is given.")
    ap.add_argument("--body-dir", default=None,
                     help="Directory of legacy page{file_page}_image1_normalized.md files (bracket [^N] "
                          "refs only -- counted, never read as letters). Required unless "
                          "--check-legacy-identity is given.")
    ap.add_argument("--pages", type=int, nargs="*", default=None,
                     help="Explicit file-page ints to process. Default: every page key present "
                          "in --notes-jsonl.")
    ap.add_argument("--resets-json", default=None,
                     help="JSON {\"pages\": {file_page: [in-page slot indices]}}.")
    ap.add_argument("--anomalies-json", default=None,
                     help="Human anomaly table: {\"pages\": [{file_page, kind, observed}, ...]}.")
    ap.add_argument("--prev-last", default=None,
                     help="Last confirmed marker letter immediately before this run's first "
                          "page (confirmed OUTSIDE the run itself).")
    ap.add_argument("--out", default=None,
                     help="Output JSON-lines path. Must NOT resolve inside goatyard-laneA2 or "
                          "goat-yard-archive -- this is private data. Required unless "
                          "--check-legacy-identity is given.")
    ap.add_argument("--check-legacy-identity", default=None, metavar="DIR",
                     help="Read-only mode: run project_legacy() over every *.md under DIR and "
                          "report identical/changed counts; exit 1 if any file would change. "
                          "Ignores every other argument.")
    return ap


def main(argv=None):
    args = build_arg_parser().parse_args(argv)

    if args.check_legacy_identity:
        return check_legacy_identity(args.check_legacy_identity)

    missing = [name for name, val in (
        ("--notes-jsonl", args.notes_jsonl), ("--body-dir", args.body_dir), ("--out", args.out),
    ) if not val]
    if missing:
        print(f"required (unless --check-legacy-identity): {', '.join(missing)}", file=sys.stderr)
        return 2

    try:
        out_path = validate_out_path(args.out)
    except OutputPathRefused as e:
        print(str(e), file=sys.stderr)
        return 2

    notes_by_page, cols_by_page = load_notes(args.notes_jsonl)
    resets = load_resets(args.resets_json)
    anomalies = load_anomalies(args.anomalies_json)

    file_pages = sorted(set(args.pages)) if args.pages else sorted(notes_by_page)

    pages = []
    for fp in file_pages:
        pages.append({
            "file_page": fp,
            "body": load_body_series(args.body_dir, fp),
            "notes": notes_by_page.get(fp),
            "body_cols": None,
            "notes_cols": cols_by_page.get(fp),
        })

    repo_root = Path(__file__).resolve().parents[2]
    git_head = get_git_head(repo_root)
    git_dirty = get_git_dirty(repo_root)
    module_sha16 = sha16(Path(__file__).resolve().parent / "marker_ledger.py")

    input_shas = {"notes_jsonl": sha16(args.notes_jsonl)}
    if args.resets_json:
        input_shas["resets_json"] = sha16(args.resets_json)
    if args.anomalies_json:
        input_shas["anomalies_json"] = sha16(args.anomalies_json)

    args_dict = {
        "notes_jsonl": args.notes_jsonl, "body_dir": args.body_dir, "pages": file_pages,
        "resets_json": args.resets_json, "anomalies_json": args.anomalies_json,
        "prev_last": args.prev_last, "out": str(out_path),
    }
    base_config = {
        "module_sha16": module_sha16, "git_head": git_head, "git_dirty": git_dirty,
        "input_shas": input_shas, "args": args_dict,
    }
    cfg_hash = config_hash(base_config)

    result = ML.reconcile(pages, resets=resets, anomalies=anomalies, prev_last=args.prev_last)

    header = {
        "kind": "run_header", "tier": TIER, "git_head": git_head, "git_dirty": git_dirty,
        "module_sha16": module_sha16, "input_shas": input_shas, "args": args_dict,
        "config_hash": cfg_hash, "endpoint": None,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(header) + "\n")
        for slot in result["slots"]:
            f.write(json.dumps(slot) + "\n")
        summary_line = dict(result["summary"])
        summary_line["kind"] = "run_summary"
        summary_line["n_breaks"] = len(result["breaks"])
        summary_line["n_suppressed_breaks"] = len(result["suppressed_breaks"])
        summary_line["n_anomaly_candidates"] = len(result["anomaly_candidates"])
        summary_line["page_flags"] = result["page_flags"]
        f.write(json.dumps(summary_line) + "\n")

    print(f"pages: {len(pages)}")
    print(f"slots: {result['summary']['n_slots']}")
    print(f"breaks: {len(result['breaks'])}  suppressed: {len(result['suppressed_breaks'])}  "
          f"anomaly_candidates: {len(result['anomaly_candidates'])}")
    print(f"config hash: {cfg_hash}")
    print(f"output: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
