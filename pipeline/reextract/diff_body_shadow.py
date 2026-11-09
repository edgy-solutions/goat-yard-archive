"""diff_body_shadow -- stage 3 of the 20-page body shadow run: offline, read-only, NO model.

Per FILE page: old = the body part of page{fp}_image1_normalized.md (assembler.split_body_defs);
new = that page's stage-2 chunk texts in run order. Both sides go through ONE tokeniser
(`tagged_tokens`: word-break join, then whitespace split). The diff is difflib with autojunk off;
every non-equal opcode is a hunk, and every hunk gets exactly one class in a fixed precedence:

  1 disputed_head  touches the first 4 tokens of a verse region whose head_status != "shipped"
  2 verse_boundary touches a token starting with "Ver" on either side, or its new span covers
                   tokens of 2 regions
  3 ws_punct       the two sides are equal after removing whitespace and every Unicode P* char
                   (case is NOT folded)
  4 content        everything else (adjudicated only by a human verdict; no code picks a winner)

Orthogonal flags, never classes: non_latin, marker (^x^), chunk_edge (the new span is within 1
token of a chunk boundary). "Differs from old" is a measurement, never "wrong": the old text is a
reference, not truth.

Per page also: the verse-number agreement record (stage-1 head read vs witness; the body reader's
in-text "Ver. N" at the region's chunk 0 vs witness). The body reader is the SAME model as the
head reader, so its agreement is a measurement, never a ship basis.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import assembler  # noqa: E402
import body_read as BR  # noqa: E402
import build_body_shadow as BSB  # noqa: E402
import build_verse_regions as BVR  # noqa: E402
import verse_regions as VR  # noqa: E402

HEAD_TOKENS = 4
CONTEXT_TOKENS = 6
CLASSES = ("disputed_head", "verse_boundary", "ws_punct", "content")
_MARKER_RE = re.compile(r"\^[A-Za-z]\^")
_NL = chr(10)


# ---- the one tokeniser ----------------------------------------------------------------------

def tagged_tokens(tagged_lines):
    """[(line, tag), ...] -> [(token, tag), ...]: word-break join, then whitespace split. The only
    tokenisation path, used for the old side and the new side alike."""
    out = []
    for line, tag in BR.join_wordbreaks_tagged(tagged_lines):
        out.extend((t, tag) for t in line.split())
    return out


def tokens(text):
    return [t for t, _ in tagged_tokens([(ln, None) for ln in text.split(_NL)])]


# ---- classification pieces ------------------------------------------------------------------

# A verse-head token: "Ver." / "Ver," / "Ver" (capital, punctuation optional) or "ver." / "ver,"
# (lowercase needs the punctuation, as in verse_head_read), optionally markdown-wrapped and
# optionally run into its number ("Ver.1."). NOT startswith("Ver"): "Verily"/"Very" are prose.
_VER_TOKEN_RE = re.compile(r"^[*_#]*(?:Ver[.,:]?|ver[.,:])(?:\d.*)?$")


def is_ver_token(t):
    return bool(_VER_TOKEN_RE.match(t))


def strip_ws_punct(s):
    return "".join(c for c in s if not c.isspace() and not unicodedata.category(c).startswith("P"))


def _touches(lo, hi, rlo, rhi):
    """Does the span [lo,hi) touch the range [rlo,rhi)? An empty span is a position: it touches
    when rlo <= pos <= rhi (conservative: more hunks go to the fully-sampled head stratum)."""
    if lo == hi:
        return rlo <= lo <= rhi
    return lo < rhi and rlo < hi


def _has_non_latin(s):
    return any(assembler._non_latin(c) for c in s)


def classify_hunk(old_toks, new_toks, new_tags, i1, i2, j1, j2, head_ranges_new, head_ranges_old):
    """Exactly one class, in the lock's precedence."""
    old_text = " ".join(old_toks[i1:i2])
    new_text = " ".join(new_toks[j1:j2])
    # CLASS-1 disputed_head
    if (any(_touches(j1, j2, a, b) for a, b in head_ranges_new)
            or any(_touches(i1, i2, a, b) for a, b in head_ranges_old)):
        return "disputed_head"
    # CLASS-2 verse_boundary
    if (any(is_ver_token(t) for t in old_toks[i1:i2])
            or any(is_ver_token(t) for t in new_toks[j1:j2])
            or len({new_tags[k][0] for k in range(j1, j2)}) >= 2):
        return "verse_boundary"
    # CLASS-3 ws_punct
    if strip_ws_punct(old_text) == strip_ws_punct(new_text):
        return "ws_punct"
    # CLASS-4 content
    return "content"


def _chunk_edge(new_tags, j1, j2):
    """The new span is within 1 token of a chunk boundary (a place where the (region, chunk) tag
    changes between adjacent new tokens)."""
    for b in range(1, len(new_tags)):
        if new_tags[b] != new_tags[b - 1] and j1 - 1 <= b <= j2 + 1:
            return True
    return False


# ---- one page --------------------------------------------------------------------------------

def diff_page(file_page, old_text, units):
    """Pure. units: [{"key","stage1_line","stage1_kind","head_status","head_unit":bool,
    "chunks":[{"chunk_idx","rect_idx","col","box","text","usable":bool}, ...]}, ...] in run order.
    -> list of hunk dicts, one per non-equal opcode."""
    old_lines = [(ln, i) for i, ln in enumerate(old_text.split(_NL))]
    old_tt = tagged_tokens(old_lines)
    old_toks = [t for t, _ in old_tt]
    old_line_of = [g for _, g in old_tt]
    new_lines = []
    for ui, u in enumerate(units):
        for c in u["chunks"]:
            if not c.get("usable"):
                continue
            for ln in (c["text"] or "").split(_NL):
                new_lines.append((ln, (ui, c["chunk_idx"], c["rect_idx"])))
    new_tt = tagged_tokens(new_lines)
    new_toks = [t for t, _ in new_tt]
    new_tags = [g for _, g in new_tt]

    ops = difflib.SequenceMatcher(None, old_toks, new_toks, autojunk=False).get_opcodes()

    def old_pos_of(j):
        for tag, i1, i2, j1, j2 in ops:
            if tag == "equal" and j1 <= j < j2:
                return i1 + (j - j1)
        return None

    head_new, head_old = [], []
    for ui, u in enumerate(units):
        if u["stage1_kind"] != "verse" or u["head_status"] == "shipped" or not u["head_unit"]:
            continue
        idx = [k for k, g in enumerate(new_tags) if g[0] == ui]
        if not idx:
            continue
        a = idx[0]
        head_new.append((a, min(a + HEAD_TOKENS, idx[-1] + 1)))
        oa = old_pos_of(a)
        if oa is not None:
            line = [k for k, g in enumerate(old_line_of) if g == old_line_of[oa]]
            if any(is_ver_token(old_toks[k]) for k in line):
                head_old.append((line[0], line[-1] + 1))

    hunks = []
    for op_idx, (tag, i1, i2, j1, j2) in enumerate(ops):
        if tag == "equal":
            continue
        old_t, new_t = " ".join(old_toks[i1:i2]), " ".join(new_toks[j1:j2])
        cls = classify_hunk(old_toks, new_toks, new_tags, i1, i2, j1, j2, head_new, head_old)
        regions = sorted({new_tags[k][0] for k in range(j1, j2)})
        ref = None
        if new_tags:
            ui, ci, ri = new_tags[min(j1, len(new_tags) - 1)]
            ch = [c for c in units[ui]["chunks"] if c["chunk_idx"] == ci and c["rect_idx"] == ri][0]
            ref = {"key": units[ui]["key"], "stage1_line": units[ui]["stage1_line"],
                   "file_page": file_page, "col": ch["col"], "rect_idx": ri, "chunk_idx": ci,
                   "box": ch["box"]}
        hunks.append({
            "kind": "hunk", "file_page": file_page, "opcode_idx": op_idx, "op": tag,
            "old_span": [i1, i2], "new_span": [j1, j2], "old_text": old_t, "new_text": new_t,
            "class": cls,
            "flags": {"non_latin": _has_non_latin(old_t) or _has_non_latin(new_t),
                      "marker": bool(_MARKER_RE.search(old_t) or _MARKER_RE.search(new_t)),
                      "chunk_edge": _chunk_edge(new_tags, j1, j2)},
            "regions": [units[u]["key"] for u in regions], "chunk": ref,
            "old_before": " ".join(old_toks[max(0, i1 - CONTEXT_TOKENS):i1]),
            "old_after": " ".join(old_toks[i2:i2 + CONTEXT_TOKENS]),
            "new_before": " ".join(new_toks[max(0, j1 - CONTEXT_TOKENS):j1]),
            "new_after": " ".join(new_toks[j2:j2 + CONTEXT_TOKENS]),
        })
    return hunks


# ---- verse numbers ---------------------------------------------------------------------------

def verse_number_record(file_page, stage1_rec, stage1_line, unit):
    """One verse region's agreement record. body_read = parse_ver_head on the region's first
    chunk (chunk 0 of its first rect on its head page); None when that chunk has no usable text."""
    src = stage1_rec.get("number_sources") or {}
    body_numbers = body_status = None
    if unit is not None:
        first = [c for c in unit["chunks"] if c["chunk_idx"] == 0]
        first = sorted(first, key=lambda c: c["rect_idx"])
        if first and first[0].get("usable"):
            p = VR.parse_ver_head(first[0]["text"])
            body_numbers, body_status = p["numbers"], p["status"]
    head_read, witness = src.get("read"), src.get("witness")
    return {"kind": "verse_numbers", "file_page": file_page, "stage1_line": stage1_line,
            "head_status": stage1_rec.get("head_status"), "count": src.get("count"),
            "head_read": head_read, "witness": witness, "body_read": body_numbers,
            "body_parse_status": body_status,
            "head_read_eq_witness": head_read is not None and head_read == witness,
            "body_read_eq_witness": body_numbers is not None and body_numbers == witness}


# ---- the run ----------------------------------------------------------------------------------

def load_body_units(body_path):
    """-> (header, {file_page: [unit, ...]} in run order, page order)."""
    header, by_page, order = None, {}, []
    with open(body_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec["kind"] == "run_header":
                header = rec
            elif rec["kind"] == "body_region":
                fp = rec["file_page"]
                if fp not in by_page:
                    by_page[fp] = []
                    order.append(fp)
                by_page[fp].append({
                    "key": rec["key"], "stage1_line": rec["stage1_line"],
                    "stage1_kind": rec["stage1_kind"], "head_status": rec["head_status"],
                    "head_unit": rec["key"][0] == fp,
                    "chunks": [{"chunk_idx": c["chunk_idx"], "rect_idx": c["rect_idx"],
                                "col": c["col"], "box": c["box"], "text": c["text"],
                                "usable": c["guard"] == "ok" and not c["error"]}
                               for c in rec["chunks"]]})
    return header, by_page, order


def load_old_body(witness_dir, file_page):
    path = Path(witness_dir) / f"page{file_page}_image1_normalized.md"
    if not path.exists():
        raise ValueError(f"witness md missing for file_page {file_page}: {path}")
    body, _defs = assembler.split_body_defs(path.read_text(encoding="utf-8"))
    return body


def summarize(hunks, vnums):
    out = {"kind": "diff_summary", "classes": Counter(), "per_page": {}, "flags_per_class": {},
           "verse_agreement": {"n": 0, "head_read_eq_witness": 0, "body_read_eq_witness": 0},
           "verse_agreement_per_page": {}}
    for h in hunks:
        fp = str(h["file_page"])
        out["classes"][h["class"]] += 1
        out["per_page"].setdefault(fp, Counter())[h["class"]] += 1
        fl = out["flags_per_class"].setdefault(h["class"], Counter())
        for k, v in h["flags"].items():
            if v:
                fl[k] += 1
    for v in vnums:
        for tgt in (out["verse_agreement"],
                    out["verse_agreement_per_page"].setdefault(
                        str(v["file_page"]),
                        {"n": 0, "head_read_eq_witness": 0, "body_read_eq_witness": 0})):
            tgt["n"] += 1
            tgt["head_read_eq_witness"] += int(v["head_read_eq_witness"])
            tgt["body_read_eq_witness"] += int(v["body_read_eq_witness"])
    out["classes"] = dict(out["classes"])
    out["per_page"] = {k: dict(v) for k, v in out["per_page"].items()}
    out["flags_per_class"] = {k: dict(v) for k, v in out["flags_per_class"].items()}
    return out


def build_arg_parser():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--body", required=True)
    ap.add_argument("--stage1", required=True)
    ap.add_argument("--witness-dir", required=True)
    ap.add_argument("--out", required=True)
    return ap


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    try:
        out_path = BVR.validate_out_path(args.out)
    except BVR.OutputPathRefused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    if out_path.exists():
        print(f"REFUSED: {out_path} exists; never clobbered", file=sys.stderr)
        return 2
    body_header, by_page, order = load_body_units(args.body)
    stage1 = BSB.read_stage1(args.stage1)
    repo_root = Path(__file__).resolve().parents[2]
    config = {
        "body_sha256": BSB.sha256_file(args.body),
        "stage1_sha256": BSB.sha256_file(args.stage1),
        "body_config_hash": (body_header or {}).get("config_hash"),
        "witness_sha256": {str(fp): BSB.sha256_file(
            Path(args.witness_dir) / f"page{fp}_image1_normalized.md") for fp in order},
        "pages": order, "head_tokens": HEAD_TOKENS, "context_tokens": CONTEXT_TOKENS,
        "git_head": BVR.get_git_head(repo_root), "git_dirty": BVR.get_git_dirty(repo_root),
        "module_sha256": BSB.sha256_file(__file__),
    }
    chash = BVR.config_hash(config)
    records = [{"kind": "diff_header", "tier": "best_effort", "config": config,
                "config_hash": chash}]
    hunks, vnums = [], []
    for fp in order:
        units = by_page[fp]
        for h in diff_page(fp, load_old_body(args.witness_dir, fp), units):
            h["config_hash"] = chash
            hunks.append(h)
        for line_no, rec in enumerate(stage1):
            if rec.get("kind") == "verse" and rec.get("file_page_first") == fp:
                unit = next((u for u in units if u["stage1_line"] == line_no and u["head_unit"]), None)
                vnums.append({**verse_number_record(fp, rec, line_no, unit), "config_hash": chash})
    records.extend(hunks)
    records.extend(vnums)
    records.append({**summarize(hunks, vnums), "tier": "best_effort", "config_hash": chash})
    tmp = Path(str(out_path) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + _NL)
    os.replace(tmp, out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
