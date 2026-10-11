"""The re-signing adjudication overlay: the human rulings on a resign-diff, and the gate on them.

ALL PAGE NUMBERS IN THE DATA THIS TOUCHES ARE FILE PAGES (printed = file - 88).

A re-signing round that opens a row with the previous round's verdicts must not silently take the newest
export as truth: where the newest export DISAGREES with the one before it over byte-identical pixels, a
human has to say which reading stands (keep = the prior reading, take = the current one, neither = neither,
leave it unanswered). This module holds the three pure steps, so the signer (a script that renders on
import) and the tests can share them:

  compute_diff      runs ingest_pass2.py --resign-diff (the gate that already exists) and returns its report
  check_coverage    REFUSES unless every disagreement has a ruling and no ruling is stray
  overlay_text      the current export's lines with the rulings applied; a `keep` tile or insertion carries
                    `restored_from` so the console can show that the restoration happened

It never chooses between readings. The rulings are the human's, or are labelled DERIVED in `authority`.
It does not touch pixels and it does not decide what the glyph is.
"""
import copy
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
VERDICTS = ("keep", "take", "neither")


class OverlayRefusal(Exception):
    pass


def sha16_bytes(b):
    return hashlib.sha256(b).hexdigest()[:16]


def compute_diff(current_path, prior_path, python=None):
    """The existing gate, run as a subprocess (ingest_pass2.py is a script and cannot be imported)."""
    out = os.path.join(tempfile.mkdtemp(prefix="resign_diff_"), "diff.json")
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.run([python or sys.executable, os.path.join(HERE, "ingest_pass2.py"), "--resign-diff",
                        str(current_path), str(prior_path), out], capture_output=True, env=env)
    if p.returncode != 0 or not os.path.exists(out):
        raise OverlayRefusal("the resign-diff gate failed (exit %s): %s"
                             % (p.returncode, p.stderr.decode("utf-8", "replace")[-400:]))
    return json.loads(io.open(out, encoding="utf-8").read())


def d_key(d):
    return (d["span_id"], d["what"], d["i"] if d["what"] == "tile" else d["seq"])


def r_key(r):
    return (r.get("span_id"), r.get("what"), r.get("tile_i") if r.get("what") == "tile" else r.get("seq"))


def check_coverage(diff, adj):
    """Raise OverlayRefusal unless every disagreement in `diff` is covered by exactly one well-formed ruling
    and every ruling matches a disagreement. An uncovered disagreement is a build failure, not a warning."""
    if adj.get("diff_sha16") != diff["diff_sha16"]:
        raise OverlayRefusal("the adjudication file rules on diff %s, but the diff computed from the two "
                             "pinned exports is %s" % (adj.get("diff_sha16"), diff["diff_sha16"]))
    rulings = adj.get("rulings") or []
    keys = [r_key(r) for r in rulings]
    if len(set(keys)) != len(keys):
        raise OverlayRefusal("the adjudication file rules twice on one item")
    for r in rulings:
        if r.get("verdict") not in VERDICTS:
            raise OverlayRefusal("ruling %r has verdict %r, not one of %r" % (r_key(r), r.get("verdict"), VERDICTS))
        if not (r.get("authority") or "").strip() or not (r.get("basis") or "").strip():
            raise OverlayRefusal("ruling %r carries no authority/basis -- a ruling says who said it" % (r_key(r),))
    want = [d_key(d) for d in diff["disagreements"]]
    uncovered = [k for k in want if k not in set(keys)]
    stray = [k for k in keys if k not in set(want)]
    if uncovered:
        raise OverlayRefusal("%d of %d disagreement(s) in diff %s have NO ruling -- refusing to build: %s"
                             % (len(uncovered), len(want), diff["diff_sha16"], uncovered))
    if stray:
        raise OverlayRefusal("%d ruling(s) match no disagreement in the diff: %s" % (len(stray), stray))
    return len(want)


def _ikey(x):
    return (x.get("seq"), x.get("after_i"), x.get("kind"))


def overlay_text(current_lines, prior_rows, adj, restored_label):
    """Apply the rulings to the current export's rows and return (text, tallies). keep restores the prior
    reading and marks it `restored_from`; take leaves the current reading; neither leaves the item
    unanswered. Rows with no ruling are passed through byte-for-byte (their original line)."""
    by_sid = {}
    for r in adj["rulings"]:
        by_sid.setdefault(r["span_id"], []).append(r)
    prior = {r["span_id"]: r for r in prior_rows}
    tally = {"keep": 0, "take": 0, "neither": 0}
    out = []
    for line in current_lines:
        d = json.loads(line)
        rs = by_sid.get(d["span_id"])
        if not rs:
            out.append(line)
            continue
        p = prior[d["span_id"]]
        d = copy.deepcopy(d)
        tiles = {t["i"]: t for t in d["tiles"]}
        ptiles = {t["i"]: t for t in p["tiles"]}
        ins = {_ikey(x): x for x in d["insertions"]}
        pins = {_ikey(x): x for x in p["insertions"]}
        for r in rs:
            v = r["verdict"]
            tally[v] += 1
            if r["what"] == "tile":
                t = tiles[r["tile_i"]]
                if v == "keep":
                    pt = ptiles[r["tile_i"]]
                    for f in ("verdict", "chose", "expected", "reason", "basis"):
                        t[f] = pt.get(f, "")
                    t["restored_from"] = restored_label
                elif v == "neither":
                    for f in ("verdict", "chose", "expected", "reason", "basis"):
                        t[f] = ""
            else:
                k = next(k for k in set(ins) | set(pins) if k[0] == r["seq"])
                if v == "keep":
                    if k in pins:
                        if k in ins:
                            ins[k]["verdict"] = pins[k].get("verdict", "")
                            ins[k]["chose"] = pins[k].get("chose", "")
                            ins[k]["restored_from"] = restored_label
                        else:
                            n = copy.deepcopy(pins[k])
                            n["restored_from"] = restored_label
                            d["insertions"].append(n)
                            ins[k] = n
                    else:
                        d["insertions"] = [x for x in d["insertions"] if _ikey(x) != k]
                        del ins[k]
                elif v == "neither" and k in ins:
                    ins[k]["verdict"] = ""
        out.append(json.dumps(d, ensure_ascii=True))
    return "\n".join(out) + "\n", tally
