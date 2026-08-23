"""Born-test for the export layer (task 3): the records the consoles actually SHIP must satisfy the
Build-2 contract. We parse the generated HTML, pull each card's data-* attributes, rebuild the exact
record the export JS emits, and run audit_record.validate() on it. If a card can't produce a
contract-valid verdict, this fails — before Chris or the agent ever opens the console."""
import sys, io, json, html, re
from pathlib import Path
from html.parser import HTMLParser
sys.path.insert(0, str(Path(__file__).parent))
from audit_record import validate

HERE = Path(__file__).parent

class CardParser(HTMLParser):
    def __init__(self): super().__init__(); self.cards = []
    def handle_starttag(self, tag, attrs):
        if tag == "article":
            a = dict(attrs)
            if "card" in (a.get("class") or ""):
                self.cards.append(a)

def cards_of(html_path):
    p = CardParser(); p.feed(io.open(html_path, encoding="utf-8").read()); return p.cards

def rec_sitting_a(a):
    return {"span_id": a["data-span-id"], "chosen": "valid", "disputed_span_correction": "",
            "rationale": "test", "confidence": None,
            "provenance": {"door": "audited-by-agent-in-session", "session_freshness": "cold-context",
                           "date": "2026-08-23"},
            "inputs": {"crop": a["data-crop"], "crop_sha16": a["data-crop-sha"],
                       "candidates": json.loads(html.unescape(a["data-candidates"]))}}

def rec_sitting_b(a):
    is_dis = "dis" in a.get("class", "")
    return {"span_id": a["data-span-id"], "chosen": "take-extracted" if is_dis else "confirm",
            "disputed_span_correction": "", "rationale": "test", "confidence": None,
            "provenance": {"door": "adjudicated-by-human-review" if is_dis else "audited-by-agent-in-session",
                           "session_freshness": "cold-context", "date": "2026-08-23"},
            "inputs": {"crop": a["data-crop"], "crop_sha16": a["data-crop-sha"],
                       "candidates": json.loads(html.unescape(a["data-candidates"])), "page": int(a["data-page"])}}

def run():
    fails = 0
    a_html = HERE / "audits" / "sitting_a_console.html"
    b_html = HERE / "audits" / "sitting_b_console.html"
    a_cards = cards_of(a_html)
    assert len(a_cards) == 25, f"Sitting A: expected 25 cards, got {len(a_cards)}"
    for c in a_cards:
        try: validate(rec_sitting_a(c))
        except Exception as e: fails += 1; print(f"  A FAIL [{c.get('data-span-id')}]: {e}")
    print(f"Sitting A: {len(a_cards)} cards, all records contract-valid" if not fails else f"Sitting A: {fails} FAILED")

    b_cards = cards_of(b_html)
    ndis = sum(1 for c in b_cards if "dis" in c.get("class", ""))
    nagr = sum(1 for c in b_cards if "agr" in c.get("class", ""))
    assert ndis + nagr == len(b_cards) and len(b_cards) > 0
    bf = 0
    for c in b_cards:
        try: validate(rec_sitting_b(c))
        except Exception as e: bf += 1; print(f"  B FAIL [{c.get('data-span-id')}]: {e}")
    fails += bf
    print(f"Sitting B: {ndis} disagreement + {nagr} agreed, all records contract-valid" if not bf
          else f"Sitting B: {bf} FAILED")

    # disjointness of the two Sitting-B sets (spec: explicitly disjoint)
    dids = {c["data-span-id"] for c in b_cards if "dis" in c.get("class", "")}
    aids = {c["data-span-id"] for c in b_cards if "agr" in c.get("class", "")}
    assert not (dids & aids), f"Sitting B sets NOT disjoint: {dids & aids}"
    print(f"Sitting B disjointness: OK ({len(dids)} ∩ {len(aids)} = 0)")

    print("\nPASS — every shipped card produces a Build-2-valid verdict" if not fails
          else f"\nFAIL — {fails} cards cannot produce a valid verdict")
    return 1 if fails else 0

if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    sys.exit(run())
