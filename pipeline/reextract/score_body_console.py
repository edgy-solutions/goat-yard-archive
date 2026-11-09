"""score_body_console -- un-blinds a console export with key.json and counts verdicts per stratum.

Mapping (A and B are blinded sides; key.json says which one is the old text):
  "A matches page" with A = new -> old_wrong      "A matches page" with A = old -> new_wrong
  "B matches page" with B = new -> old_wrong      "B matches page" with B = old -> new_wrong
  "neither" -> both_differ_from_page    "both" -> equivalent    "can't tell" -> cant_tell
A card with no verdict in the export is counted `unanswered`, never dropped. An export row whose
card_id is not in the key, a repeated card_id, or an unknown verdict raises ValueError naming it.
Counts are a measurement of disagreement with the old text, not a body choice.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter

OUTCOMES = ("old_wrong", "new_wrong", "both_differ_from_page", "equivalent", "cant_tell", "unanswered")


def outcome(verdict, old_side):
    if verdict in ("A", "B"):
        return "new_wrong" if verdict == old_side else "old_wrong"
    if verdict == "neither":
        return "both_differ_from_page"
    if verdict == "both":
        return "equivalent"
    if verdict == "cant_tell":
        return "cant_tell"
    raise ValueError(f"unknown verdict {verdict!r}")


def score(rows, key):
    cards = key["cards"]
    seen = {}
    for r in rows:
        cid = r["card_id"]
        if cid not in cards:
            raise ValueError(f"export card_id {cid!r} is not in key.json")
        if cid in seen:
            raise ValueError(f"export repeats card_id {cid!r}")
        seen[cid] = r["verdict"]
    out = {}
    for cid, meta in cards.items():
        cnt = out.setdefault(meta["stratum"], Counter({k: 0 for k in OUTCOMES}))
        cnt["unanswered" if cid not in seen else outcome(seen[cid], meta["old_side"])] += 1
    return {s: dict(c) for s, c in out.items()}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--export", required=True)
    ap.add_argument("--key", required=True)
    args = ap.parse_args(argv)
    with open(args.export, encoding="utf-8") as f:
        rows = [json.loads(l) for l in f if l.strip()]
    with open(args.key, encoding="utf-8") as f:
        key = json.load(f)
    for stratum, counts in sorted(score(rows, key).items()):
        print(stratum, json.dumps(counts, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
