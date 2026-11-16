"""new_side_norm: a code-owned, ADDITIVE derived layer over a body-read JSONL (the "new side").

The body read file is never edited. This module writes a SEPARATE derived JSONL; every change is
an edit record with `from` and `to`; a letter that was read is never replaced. The chain check
only flags and proposes.

Pure functions:
  canon_marks(text)      rule marker_format_v1          -> (out, edits)
  semicolon_space(text)  rule space_before_semicolon_v1 -> (out, edits)
  normalize(text)        both, in that order            -> (out, edits)   (each edit carries `step`)
  chain_check(pages)     rule marker_chain_v1           -> list of marker_chain_page records

CLI:  python new_side_norm.py --body BODY_JSONL --out OUT_JSONL
"""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import marker_alphabet as MA  # noqa: E402
import marker_ledger as ML  # noqa: E402
import marker_ledger_run as MLR  # noqa: E402

TIER = "best_effort"
RULE_MARKS = "marker_format_v1"
RULE_SEMI = "space_before_semicolon_v1"
RULE_CHAIN = "marker_chain_v1"
RULE_SIG = "signature_tail_v1"
RULES = {
    RULE_MARKS: "canonical ^x^ attached to the preceding token; letter never changed",
    RULE_SEMI: "exactly one space before every ';' not at the start of a line",
    RULE_CHAIN: "marker_ledger.reconcile over the body series only; flags and proposals, never edits",
    RULE_SIG: "last line of a column's lowest chunk is a printer's signature / gathering mark; flag only",
}

# Order matters: A (closed), B (unclosed single), C (bare caret before punctuation), D (any other ^).
_MARK_RE = re.compile(
    r"(?P<a>(?P<a_ws>[ \t]*)\^(?P<a_x>[A-Za-z0-9]{1,2})\^)"
    r"|(?P<b>(?P<b_ws>[ \t]*)\^(?P<b_x>[A-Za-z0-9])(?![A-Za-z0-9^]))"
    r"|(?P<c>(?P<c_ws>[ \t]*)\^(?=[^\sA-Za-z0-9^]))"
    r"|(?P<d>\^)"
)
_CANON_MARK_RE = re.compile(r"\^([A-Za-z0-9?]{1,2})\^")


def _letter_kind(x):
    if any(ch.isdigit() for ch in x):
        return "numeric"
    if any(ch.isupper() for ch in x):
        return "uppercase"
    return "format"


def canon_marks(text):
    """marker_format_v1. Returns (out, edits). The letter itself is never touched."""
    text = text or ""
    out, edits, pos = [], [], 0
    for m in _MARK_RE.finditer(text):
        if m.group("d"):
            edits.append({"rule": RULE_MARKS, "kind": "unrecognized", "at": m.start(),
                          "from": "^", "to": "^"})
            continue
        if m.group("a"):
            x = m.group("a_x")
            frm, to, kind = m.group("a"), f"^{x}^", _letter_kind(x)
        elif m.group("b"):
            x = m.group("b_x")
            frm, to, kind = m.group("b"), f"^{x}^", _letter_kind(x)
        else:
            frm, to, kind = m.group("c"), "^?^", "letter_missing"
        if frm == to:
            continue   # already canonical: no edit
        out.append(text[pos:m.start()])
        out.append(to)
        pos = m.end()
        edits.append({"rule": RULE_MARKS, "kind": kind, "at": m.start(), "from": frm, "to": to})
    out.append(text[pos:])
    return "".join(out), edits


_SEMI_RE = re.compile(r"([ \t]*);")


def semicolon_space(text):
    """space_before_semicolon_v1. Returns (out, edits)."""
    text = text or ""
    out, edits, pos = [], [], 0
    for m in _SEMI_RE.finditer(text):
        run = m.group(1)
        s = m.start()
        prev = text[s - 1] if s > 0 else None
        if prev is None or prev in "\r\n":
            continue                      # start of text / of a line: left alone
        if not run and prev.isspace():
            continue                      # preceded by other whitespace: already spaced
        if run == " ":
            continue
        out.append(text[pos:s])
        out.append(" ;")
        pos = m.end()
        edits.append({"rule": RULE_SEMI, "kind": "space", "at": s, "from": run + ";", "to": " ;"})
    out.append(text[pos:])
    return "".join(out), edits


def normalize(text):
    """canon_marks then semicolon_space. Offsets refer to each step's own input; `step` says which."""
    t1, e1 = canon_marks(text)
    for e in e1:
        e["step"] = 1
    t2, e2 = semicolon_space(t1)
    for e in e2:
        e["step"] = 2
    return t2, e1 + e2


# ---------------------------------------------------------------------------
# signature tail (flag only)
# ---------------------------------------------------------------------------

_SIG_VOL_RE = re.compile(r"\bVOL\.?\s*[IVX]+\b", re.I)
_SIG_GATHERING_RE = re.compile(r"\d{0,2}\s?[A-Z]{1,2}(\s?\d{1,2})?")


def signature_line(text):
    """The last non-empty line of text, stripped, if it is a signature form, else None."""
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    if not lines:
        return None
    line = lines[-1]
    if _SIG_VOL_RE.search(line) and len(line) <= 40:
        return line
    if _SIG_GATHERING_RE.fullmatch(line):
        return line
    return None


def signature_tail_flags(entries):
    """signature_tail_v1. entries: [(derived_chunk_record, file_page, col, box_y1 | None)]. For each
    (file_page, col) the chunk with the largest box y1 (null box, refused and empty chunks ignored) is
    the column foot; a signature-form last line puts a flag on that record. Returns the hit list
    [[file_page, col], ...]. Flags only; text_out is never touched."""
    foot = {}
    for rec, fp, col, y1 in entries:
        if y1 is None or rec.get("text_out") is None:
            continue
        k = (fp, col)
        if k not in foot or y1 > foot[k][0]:
            foot[k] = (y1, rec)
    hits = []
    for (fp, col), (_y1, rec) in foot.items():
        line = signature_line(rec["text_out"])
        if line is not None:
            rec["flags"] = [{"rule": RULE_SIG, "line": line}]
            hits.append([fp, col])
    return hits


# ---------------------------------------------------------------------------
# chain check
# ---------------------------------------------------------------------------

def _sentinel_text(text):
    return _CANON_MARK_RE.sub(lambda m: "⟦" + m.group(1) + "⟧", text or "")


def chain_check(pages):
    """marker_chain_v1. `pages`: list of {"file_page", "text"} (text = the page's canonical text in
    reading order). Body series only (notes_series "absent"); no resets supplied. prev_last carries
    page to page while file pages are consecutive. Returns one marker_chain_page record per page.
    Never edits or mutates its input."""
    records = []
    prev_last, prev_fp = None, None
    for p in pages:
        fp = int(p["file_page"])
        series = ML.body_markers(_sentinel_text(p.get("text") or ""))
        carried = prev_last if (prev_fp is not None and fp == prev_fp + 1) else None
        res = ML.reconcile([{"file_page": fp, "body": series, "notes": None}],
                           resets=None, anomalies=None, prev_last=carried)
        flags = []
        for f in res["page_flags"].get(fp, []):
            if f not in flags:
                flags.append(f)
        proposals = []
        for s in res["slots"]:
            for f in s["flags"]:
                if f != "notes_not_captured" and f not in flags:
                    flags.append(f)
            read, ce = s["body_read"], s["chain_expects"]
            if read is None or "possible_reset" in s["flags"]:
                continue
            if ce is None and s["filled_from"] == "chain":
                ce = s["letter"]
            if ce is None or s["chain"] == "outside":
                continue
            if MA.normalize(read) == ce:
                continue
            proposals.append({"index_on_page": s["body_idx"], "read": read, "proposed": ce,
                              "basis": "sequence"})
        for b in res["breaks"]:
            if b.get("reason") and b["reason"] not in flags:
                flags.append(b["reason"])
        if res["slots"]:
            last = res["slots"][-1]
            prev_last = last["letter"] or last["chain_expects"] or prev_last
        records.append({"kind": "marker_chain_page", "rule": RULE_CHAIN, "file_page": fp,
                        "letters_read": list(series), "flags": flags, "proposals": proposals,
                        "notes_series": "absent", "resets": "not_supplied",
                        "prev_last_carried": carried})
        prev_fp = fp
    return records


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class Refused(Exception):
    pass


_LANE_RE = re.compile(r"^goatyard-lane[Aa]", re.IGNORECASE)


def check_out(body, out):
    body_p, out_p = Path(body).resolve(), Path(out).resolve()
    for part in out_p.parts:
        if _LANE_RE.match(part):
            raise Refused(f"REFUSED: --out resolves inside a lane tree ({part}): {out_p}")
    if os.path.normcase(str(out_p)) == os.path.normcase(str(body_p)):
        raise Refused(f"REFUSED: --out equals --body: {out_p}")
    if out_p.exists():
        raise Refused(f"REFUSED: --out already exists: {out_p}")
    return out_p


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_text(t):
    return hashlib.sha256((t or "").encode("utf-8")).hexdigest()


def module_sha256():
    return sha256_bytes(Path(__file__).read_bytes())


def config_hash():
    base = {"rules": RULES, "module_sha256": module_sha256()}
    return hashlib.sha256(json.dumps(base, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:16]


def derive(body_path):
    """Read the body file (read-only); return (records_without_header, summary_counts). Pure."""
    raw = Path(body_path).read_bytes()
    recs = [json.loads(l) for l in raw.decode("utf-8").splitlines() if l.strip()]
    header = next((r for r in recs if r.get("kind") == "run_header"), {})
    chunk_recs, page_text, page_order, sig_entries = [], {}, [], []
    by_rule = {}
    n_changed = n_refused = 0
    for r in recs:
        if r.get("kind") != "body_region":
            continue
        for ch in r.get("chunks") or []:
            fp = ch.get("file_page", r.get("file_page"))
            rec = {"kind": "derived_chunk", "key": r.get("key"), "chunk_idx": ch.get("chunk_idx"),
                   "rect_idx": ch.get("rect_idx"), "file_page": fp,
                   "text_in_sha256": sha256_text(ch.get("text"))}
            text = ch.get("text")
            reason = None
            if ch.get("error"):
                reason = f"error:{ch.get('error')}"
            elif ch.get("guard") not in (None, "ok"):
                reason = f"guard:{ch.get('guard')}"
            elif not text or not text.strip():
                reason = "empty"
            if reason:
                rec.update({"text_out": None, "reason": reason, "edits": []})
                n_refused += 1
            else:
                out, edits = normalize(text)
                rec.update({"text_out": out, "edits": edits})
                if out != text:
                    n_changed += 1
                for e in edits:
                    by_rule.setdefault(e["rule"], {}).setdefault(e["kind"], 0)
                    by_rule[e["rule"]][e["kind"]] += 1
                ifp = int(fp)
                if ifp not in page_text:
                    page_text[ifp] = []
                    page_order.append(ifp)
                page_text[ifp].append(out)
            chunk_recs.append(rec)
            bx = ch.get("box")
            sig_entries.append((rec, fp, ch.get("col"), bx[3] if bx else None))
    sig_hits = signature_tail_flags(sig_entries)
    chain = chain_check([{"file_page": fp, "text": "\n".join(page_text[fp])} for fp in page_order])
    summary = {"kind": "derived_summary", "tier": TIER, "chunks_total": len(chunk_recs),
               "chunks_changed": n_changed, "chunks_refused_or_empty": n_refused,
               "edits_by_rule_kind": by_rule,
               "unrecognized": by_rule.get(RULE_MARKS, {}).get("unrecognized", 0),
               "pages_checked": len(chain),
               "pages_with_chain_flags": sum(1 for c in chain if c["flags"]),
               "proposals": sum(len(c["proposals"]) for c in chain),
               "resets": "not_supplied", "notes_series": "absent",
               "signature_tail_flags": len(sig_hits), "signature_tail_hits": sig_hits}
    return raw, header, chunk_recs, chain, summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--body", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    try:
        out_p = check_out(args.body, args.out)
    except Refused as e:
        print(str(e), file=sys.stderr)
        return 2
    raw, bhead, chunk_recs, chain, summary = derive(args.body)
    repo_root = Path(__file__).resolve().parents[2]
    header = {"kind": "derived_header", "tier": TIER, "config_hash": config_hash(),
              "rules": RULES, "body_path": str(Path(args.body).resolve()),
              "body_sha256": sha256_bytes(raw), "body_config_hash": bhead.get("config_hash"),
              "git_head": MLR.get_git_head(repo_root), "git_dirty": MLR.get_git_dirty(repo_root)}
    lines = [header] + chunk_recs + chain + [summary]
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "x", encoding="utf-8") as f:   # "x": never clobbers
        for r in lines:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    if summary["unrecognized"]:
        print(f"WARNING: {summary['unrecognized']} unrecognized '^' left unchanged", file=sys.stderr)
    print(json.dumps(summary, ensure_ascii=False))
    print(f"output: {out_p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
