"""Stage-3 REVIEW QUEUE — the aggregation layer for everything that needs a human (or the frontier
tier) but NOT in the hot path. Collects, per page, the fail-loud flags and deterministic checks as
`pending` items with provenance; the frontier escalation tier is the async DISPOSITION path for the
Hebrew items that pass its precondition. Nothing here auto-corrects the corpus — items are proposals.

Inputs (all already produced by the pipeline / deterministic checks):
  unanchored notes (fail-loud anchor)  ·  gated-out recrop proposals  ·  citation near-misses
  (authority-list)  ·  stitch violations  ·  Hebrew spans (routed to the escalation tier IF the note
  self-glosses, else left as a plain review item — the intake-gate precondition).
"""
import re
import authority_list
import escalation_tier

_HEB = re.compile(r"[֐-׿][֐-׿ ]*")

def collect(page, profile):
    """Deterministic aggregation (no model calls). Returns review items with provenance."""
    pg = page.get("page"); items = []
    m = page.get("anchor_match") or {}
    for u in m.get("unanchored", []):
        items.append({"page": pg, "marker": u.get("marker"), "type": "unanchored",
                      "detail": u.get("reason") or u.get("expected_letter"), "provenance": "fail-loud-anchor"})
    for c in page.get("recrop_changes", []):
        if not c.get("accepted"):
            items.append({"page": pg, "marker": c.get("marker"), "type": "recrop-gated-out",
                          "detail": f"{c['old']} -> {c['new']} (gate rejected)", "provenance": "recrop-gate"})
    for v in page.get("violations", []):
        items.append({"page": pg, "marker": None, "type": "stitch-violation",
                      "detail": v.get("text"), "provenance": "stitch-guard"})
    for f in authority_list.check_page(page.get("notes", []), profile):
        items.append({"page": pg, "marker": f["marker"], "type": "citation-near-miss",
                      "detail": f"{f['token']} ~ {f['nearest']} ({f['ratio']})", "provenance": "authority-list"})
    for it in items: it["disposition"] = "pending"
    return items

def escalation_candidates(page):
    """Hebrew notes whose own text self-glosses (intake gate) -> eligible for the frontier tier."""
    out = []
    for n in page.get("notes", []):
        h = _HEB.search(n["text"])
        if h and escalation_tier.has_adjudicating_material(n["text"], h.group(0).strip()):
            out.append(n)
    return out

def feed_escalation(page, key, models=None):
    """ASYNC disposition path (costs money; run off the hot path, batched). Returns escalation
    proposals for the self-glossing Hebrew notes, each carrying provenance + cost."""
    out = []
    for n in escalation_candidates(page):
        span = _HEB.search(n["text"]).group(0).strip()
        p = escalation_tier.escalate_span(span, n["text"], key, models)
        p["marker"] = n["marker"]
        out.append(p)
    return out

if __name__ == "__main__":
    import sys, yaml
    from pathlib import Path
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    prof = yaml.safe_load((Path(__file__).parent / "book_profile.gill.yaml").read_text(encoding="utf-8"))
    page = {"page": 702, "notes": [
        {"marker": "[^5]", "text": "T. Bab. Eruvin. Misn. Negáim, c. 12. sect. 4. Gerson in loc."},
        {"marker": "[^13]", "text": "סגר עליה clausit viam illis, Pagninus."},
        {"marker": "[^9]", "text": "וכי"}],
        "anchor_match": {"unanchored": [{"marker": "[^7]", "reason": "anchor_missing_in_body", "expected_letter": "h"}]},
        "recrop_changes": [{"marker": "[^2]", "old": "כי", "new": "כִּי", "accepted": False}],
        "violations": []}
    print("REVIEW ITEMS (deterministic):")
    for it in collect(page, prof): print("  ", it)
    print("ESCALATION CANDIDATES (self-glossing Hebrew):",
          [n["marker"] for n in escalation_candidates(page)], "(note [^9] 'וכי' correctly excluded — no gloss)")
