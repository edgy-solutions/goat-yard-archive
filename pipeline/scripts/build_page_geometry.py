"""Writer: persists ONE page-geometry record per page, carrying tier/provenance fields from birth.

Wraps `presplit()` from cv_footnote_presplit.py. Never drops a page: every page that HAS an image
file gets exactly one record (a presplit() exception becomes an "error"-flagged record, not a
vanished page); a page whose image file is absent gets no record but IS printed and counted.
Flags are flags, never gates -- nothing here skips or filters a page because of a flag.

Output is private data (per-page geometry derived from a copyrighted scan corpus) and must never
land inside the public repo -- see FORBIDDEN_OUTPUT_ROOTS / validate_out_path().
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cv_footnote_presplit import presplit  # noqa: E402  (module-level name; tests monkeypatch it)

DEFAULT_VOLUME_DIR = "C:/Users/cnogr/git/dr-voluminous/commentary/volume1"
FILE_PAGE_OFFSET = 88          # printed_page = file_page - FILE_PAGE_OFFSET
TIER = "best_effort"

DEFAULT_UPSCALE = 2
DEFAULT_FULL_WIDTH_DEPTH = 0.30

# Repo roots this writer refuses to write inside, loudly. Both are checked as directory prefixes
# of the RESOLVED output path (case-insensitive, Windows-safe), never a substring match.
FORBIDDEN_OUTPUT_ROOTS = [
    Path("C:/Users/cnogr/git/goatyard-laneA"),
    Path("C:/Users/cnogr/git/goat-yard-archive"),
]

RECORD_KEY_ORDER = [
    "volume", "file_page", "printed_page", "image", "page", "coord", "xdiv",
    "rules", "mode", "fn_gutter", "body_regions", "tier", "flags", "config",
]

_PAGE_RE = re.compile(r"^page(\d+)_image1\.png$", re.IGNORECASE)


class OutputPathRefused(Exception):
    """Raised when the resolved --out path lands inside a forbidden repo root."""


# ---------------------------------------------------------------------------
# Output-path safety
# ---------------------------------------------------------------------------

def _is_within(path, root):
    p = os.path.normcase(os.path.normpath(str(path)))
    r = os.path.normcase(os.path.normpath(str(root)))
    return p == r or p.startswith(r + os.sep)


# The two known checkouts on this machine are listed above; this adds - durably - whatever
# repo this file is actually running from, so the guard travels with the file instead of with
# the machine. A second worktree, or a clone under another name, is covered without an edit.
_SELF_REPO_ROOT = Path(__file__).resolve().parents[2]
if all(not _is_within(_SELF_REPO_ROOT, r.resolve()) for r in FORBIDDEN_OUTPUT_ROOTS):
    FORBIDDEN_OUTPUT_ROOTS.append(_SELF_REPO_ROOT)


def validate_out_path(out_arg):
    """Resolve --out and refuse (raise OutputPathRefused) if it lands inside a forbidden repo
    root. Returns the resolved Path when allowed. Pure path logic -- never touches the filesystem
    beyond resolve(), so it is safe to call before any directory is created."""
    resolved = Path(out_arg).resolve()
    for root in FORBIDDEN_OUTPUT_ROOTS:
        root_resolved = root.resolve()
        if _is_within(resolved, root_resolved):
            raise OutputPathRefused(
                f"REFUSED: output path resolves inside forbidden repo root {root_resolved} "
                f"(resolved --out = {resolved}). This is private data; it must never land "
                f"inside a repo root. Pass an --out under dr-voluminous (or another path "
                f"outside both goatyard-laneA and goat-yard-archive)."
            )
    return resolved


# ---------------------------------------------------------------------------
# Config block + hash (step 8)
# ---------------------------------------------------------------------------

def config_hash(base_config):
    """sha256, first 16 hex chars, of the canonical JSON (sorted keys, no whitespace) of
    base_config -- which must NOT contain the "hash" key itself."""
    canonical = json.dumps(base_config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def build_config(upscale, full_width_depth, module_sha256, git_head, git_dirty):
    base = {
        "presplit": {"upscale": upscale, "full_width_depth": full_width_depth},
        "module_sha256": module_sha256,
        "git_head": git_head,
        "git_dirty": git_dirty,
    }
    cfg = dict(base)
    cfg["hash"] = config_hash(base)
    return cfg


def compute_module_sha256(module_path):
    return hashlib.sha256(Path(module_path).read_bytes()).hexdigest()


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
    """True/False from `git status --porcelain` (non-empty = dirty). Never hand-rolled -- git
    already accounts for autocrlf and line-ending noise. None if git itself is unavailable."""
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
# Flags (never gates)
# ---------------------------------------------------------------------------

def compute_flags(strip, info):
    flags = []
    rules = info.get("rules") or [None, None]
    rule_l, rule_r = rules[0], rules[1]
    if rule_l is None and rule_r is None:
        flags.append("no_rule")
    if strip is None:
        flags.append("no_strip")
    if (rule_l is None) != (rule_r is None):
        flags.append("single_column_rule")
    if info.get("mode") == "full_width":
        flags.append("full_width")
    body_regions = info.get("body_regions") or []
    if any(r.get("y1_source") == "page_bottom_no_rule" for r in body_regions):
        flags.append("y1_unknown")
    return flags


# ---------------------------------------------------------------------------
# Record construction
# ---------------------------------------------------------------------------

def build_record(volume, file_page, image_name, info, strip, tier, config):
    record = {
        "volume": volume,
        "file_page": file_page,
        "printed_page": file_page - FILE_PAGE_OFFSET,
        "image": image_name,
        "page": info.get("page"),
        "coord": info.get("coord"),
        "xdiv": info.get("xdiv"),
        "rules": info.get("rules"),
        "mode": info.get("mode"),
        "fn_gutter": info.get("fn_gutter"),
        "body_regions": info.get("body_regions"),
        "tier": tier,
        "flags": compute_flags(strip, info),
        "config": config,
    }
    assert list(record.keys()) == RECORD_KEY_ORDER
    return record


def build_error_record(volume, file_page, image_name, tier, config, exc):
    record = {
        "volume": volume,
        "file_page": file_page,
        "printed_page": file_page - FILE_PAGE_OFFSET,
        "image": image_name,
        "page": None,
        "coord": None,
        "xdiv": None,
        "rules": [None, None],
        "mode": None,
        "fn_gutter": None,
        "body_regions": None,
        "tier": tier,
        "flags": ["error"],
        "config": config,
        "error": {"type": type(exc).__name__, "message": str(exc)},
    }
    assert list(record.keys())[:len(RECORD_KEY_ORDER)] == RECORD_KEY_ORDER
    return record


def process_page(volume, file_page, image_path, image_name, tier, config,
                  upscale=DEFAULT_UPSCALE, full_width_depth=DEFAULT_FULL_WIDTH_DEPTH):
    """Returns (record_or_None, missing_bool). Never raises -- a presplit() exception is caught
    and turned into an ["error"]-flagged record so the pass keeps going."""
    if not image_path.exists():
        return None, True
    try:
        strip, info = presplit(str(image_path), upscale=upscale, full_width_depth=full_width_depth)
    except Exception as e:
        return build_error_record(volume, file_page, image_name, tier, config, e), False
    return build_record(volume, file_page, image_name, info, strip, tier, config), False


# ---------------------------------------------------------------------------
# Page discovery
# ---------------------------------------------------------------------------

def parse_volume_number(volume_dir):
    m = re.search(r"volume(\d+)", volume_dir.name, re.IGNORECASE)
    if not m:
        raise ValueError(f"cannot infer volume number from directory name: {volume_dir.name!r}")
    return int(m.group(1))


def discover_file_pages(volume_dir):
    pages = []
    for entry in os.listdir(volume_dir):
        m = _PAGE_RE.match(entry)
        if m:
            pages.append(int(m.group(1)))
    return sorted(set(pages))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--volume-dir", default=DEFAULT_VOLUME_DIR)
    ap.add_argument("--out", required=True, help="Output JSONL path. Must NOT resolve inside "
                     "goatyard-laneA or goat-yard-archive -- this is private data.")
    ap.add_argument("--pages", type=int, nargs="*", default=None,
                     help="Explicit file-page ints to process (for sampling). Default: "
                          "discover every pageNNN_image1.png in --volume-dir.")
    ap.add_argument("--limit", type=int, default=None,
                     help="Cap the (sorted) candidate list to the first N file-page numbers.")
    return ap


def main(argv=None):
    args = build_arg_parser().parse_args(argv)

    try:
        out_path = validate_out_path(args.out)
    except OutputPathRefused as e:
        print(str(e), file=sys.stderr)
        return 2

    volume_dir = Path(args.volume_dir).resolve()
    volume = parse_volume_number(volume_dir)

    if args.pages:
        candidates = sorted(set(args.pages))
    else:
        candidates = discover_file_pages(volume_dir)
    if args.limit is not None:
        candidates = candidates[:args.limit]

    module_path = Path(__file__).resolve().parent / "cv_footnote_presplit.py"
    module_sha256 = compute_module_sha256(module_path)
    repo_root = Path(__file__).resolve().parents[2]
    git_head = get_git_head(repo_root)
    git_dirty = get_git_dirty(repo_root)
    config = build_config(DEFAULT_UPSCALE, DEFAULT_FULL_WIDTH_DEPTH, module_sha256, git_head, git_dirty)

    records = []
    missing = []
    flag_counts = Counter()
    for file_page in candidates:
        image_name = f"page{file_page}_image1.png"
        image_path = volume_dir / image_name
        record, is_missing = process_page(volume, file_page, image_path, image_name, TIER, config)
        if is_missing:
            missing.append(image_name)
            print(f"MISSING: {image_name}")
            continue
        records.append(record)
        for flag in record["flags"]:
            flag_counts[flag] += 1

    records.sort(key=lambda r: r["file_page"])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")

    print("\n=== census ===")
    print(f"pages examined: {len(candidates)}")
    print(f"pages found (image present): {len(records)}")
    print(f"records written: {len(records)}")
    print(f"missing: {len(missing)}" + (f" ({', '.join(missing)})" if missing else ""))
    print("flags:")
    if flag_counts:
        for flag in sorted(flag_counts):
            print(f"  {flag}: {flag_counts[flag]}")
    else:
        print("  (none)")
    print(f"config hash: {config['hash']}")
    print(f"output: {out_path}")

    if not records:
        print("ERROR: zero records written", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
