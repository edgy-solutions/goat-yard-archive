"""score_body_console -- un-blinds a console export with key.json and counts verdicts per stratum.

Mapping (A and B are blinded sides; key.json says which one is the old text):
  "A matches page" with A = new -> old_wrong      "A matches page" with A = old -> new_wrong
  "B matches page" with B = new -> old_wrong      "B matches page" with B = old -> new_wrong
  "neither" -> both_differ_from_page    "both" -> equivalent    "can't tell" -> cant_tell
A card with no verdict in the export is counted `unanswered`, never dropped. An export row whose
card_id is not in the key, a repeated card_id, or an unknown verdict raises ValueError naming it.
With --crops crops.json, a card the console never rendered (not cardable) is `not_cardable`.
An extra `carried` field on an export row is ignored. Counts are a measurement of disagreement with the old text, not a body choice.
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


def score(rows, key, crops=None):
    """crops: optional crops.json dict; a card it marks not cardable is counted `not_cardable`
    (it was never shown), never `unanswered`. Without it, behaviour is unchanged."""
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
        if crops is not None and cid not in seen and not crops.get(cid, {}).get("cardable", True):
            cnt["not_cardable"] += 1
        else:
            cnt["unanswered" if cid not in seen else outcome(seen[cid], meta["old_side"])] += 1
    if crops is not None:
        for cnt in out.values():
            cnt.setdefault("not_cardable", 0)
    return {s: dict(c) for s, c in out.items()}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--export", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--crops", default=None, help="crops.json: report not-cardable cards separately")
    args = ap.parse_args(argv)
    with open(args.export, encoding="utf-8") as f:
        rows = [json.loads(l) for l in f if l.strip()]
    with open(args.key, encoding="utf-8") as f:
        key = json.load(f)
    crops = None
    if args.crops:
        with open(args.crops, encoding="utf-8") as f:
            crops = json.load(f)
    for stratum, counts in sorted(score(rows, key, crops).items()):
        print(stratum, json.dumps(counts, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
