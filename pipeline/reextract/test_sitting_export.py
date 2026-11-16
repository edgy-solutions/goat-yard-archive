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

class Skip(Exception):
    pass

def run(here=HERE):
    fails = 0
    a_html = here / "audits" / "sitting_a_console.html"
    b_html = here / "audits" / "sitting_b_console.html"
    for path in (a_html, b_html):
        if not path.exists():
            raise Skip(f"SKIP test_sitting_export: {path} absent (the shipped Sitting A/B consoles' "
                       f"cards must each produce a Build-2-valid verdict record)")
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

def selfcheck_skip_is_conditional():
    """The skip depends on exactly the two named paths: with neither, or only one, it skips; with both
    present (empty pages, fake dir) the checks RUN and fail on the card count, they are not skipped."""
    import shutil, tempfile
    d = Path(tempfile.mkdtemp(prefix="sit_skip_"))
    try:
        for setup in ([], ["sitting_a_console.html"], ["sitting_b_console.html"]):
            (d / "audits").mkdir(exist_ok=True)
            for f in (d / "audits").iterdir(): f.unlink()
            for n in setup: (d / "audits" / n).write_text("<html></html>", encoding="utf-8")
            try: run(d); raise AssertionError("did not skip")
            except Skip: pass
        for n in ("sitting_a_console.html", "sitting_b_console.html"):
            (d / "audits" / n).write_text("<html></html>", encoding="utf-8")
        try: run(d); raise AssertionError("ran without failing on empty pages")
        except Skip: raise AssertionError("both paths exist yet it skipped")
        except AssertionError as e: assert "expected 25 cards" in str(e), str(e)
    finally: shutil.rmtree(d, ignore_errors=True)

if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    selfcheck_skip_is_conditional()
    try:
        rc = run()
    except Skip as e:
        print(f"  {e}")
        print("\n0 passed, 0 failed, 1 skipped")
        sys.exit(0)
    print(f"\n{1 - rc} passed, {rc} failed, 0 skipped")
    sys.exit(rc)
