"""STANDOFF anchor layer — link re-extracted notes to the body WITHOUT mutating the body's bytes.
The body text is load-bearing (SIDs, chunk boundaries, verifier difflib targets, every eval assertion
hang off its exact bytes), so anchors live in a SEPARATE annotation layer: note N of page P attaches
at a body POSITION (char offset + a version-robust phrase anchor), never re-inserted inline. Visible
superscripts, if ever wanted, compose at DISPLAY time from these records.

Each record carries per-anchor PROVENANCE + CONFIDENCE:
  old-body-anchor   — the old body still has the in-text superscript (215 OK + partial pages): high
  placed-by-window  — inferred inside a letter-scope window (future: CV-detected candidate + constraint)
  unfound-flagged   — no anchor findable (the 609 anchor-barren pages, pending CV re-detection): 0
The CV superscript re-detection (the hard sub-piece) FEEDS this layer with candidate positions; this
module is the deterministic linkage + record model + fail-loud-unfound, testable now off the old body.
"""
import re
import assembler as A

_ANCHOR_RE = re.compile(r"\[\^([a-z])\]|\^\[([a-z])\]|\^([a-z])\^|\^([a-z])")

def detect_body_anchor_positions(body_text):
    """[(letter, char_offset)] for every inline anchor in the body (byte positions, read-only)."""
    return [(next(g for g in m.groups() if g), m.start()) for m in _ANCHOR_RE.finditer(body_text)]

def _phrase_anchor(body_text, offset, words=6):
    """A version-robust locator: the ~6 words preceding the anchor offset (survives minor re-edits
    better than a raw byte offset, like the alignment JSONs' start/end phrases)."""
    before = body_text[:offset].rstrip()
    return " ".join(before.split()[-words:])

def link_page(notes, body_text, profile, page):
    """Produce standoff records (body byte-identical). Uses the existing anchor-matcher for the linkage
    decision, then expresses each link as an annotation with position + provenance + confidence."""
    body = A.split_body_defs(body_text)[0]
    positions = detect_body_anchor_positions(body)
    match = A.match_notes_to_anchors(notes, body, profile)
    # map anchor-letter (in reading order) -> its char offset; the matcher's links are in note order
    linked_letters = [l["anchor_letter"] for l in match["links"]]
    pos_iter = iter(positions)
    records = []
    used = 0
    for l in match["links"]:
        # consume positions in reading order to get the offset for this linked anchor
        off = positions[used][1] if used < len(positions) else None
        used += 1
        records.append({"page": page, "note": l["marker"], "anchor_letter": l["anchor_letter"],
                        "body_char_offset": off,
                        "phrase_anchor": _phrase_anchor(body, off) if off is not None else None,
                        "provenance": "old-body-anchor", "confidence": 0.95})
    for u in match["unanchored"]:
        records.append({"page": page, "note": u["marker"], "anchor_letter": None,
                        "body_char_offset": None, "phrase_anchor": None,
                        "provenance": "unfound-flagged", "confidence": 0.0,
                        "reason": u.get("reason") or "anchor_missing_in_body",
                        "needs": "cv-superscript-redetection"})
    return {"page": page, "status": match["status"], "records": records,
            "n_linked": len(match["links"]), "n_unfound": len(match["unanchored"]),
            "body_bytes_touched": 0}   # invariant: the body is never edited

if __name__ == "__main__":
    import sys, json
    from pathlib import Path
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    profile = A.load_profile(str(Path(__file__).parent / "book_profile.gill.yaml"))
    D = Path("c:/Users/cnogr/git/dr-voluminous/commentary/volume1/qwen_qwen3-vl-235b-a22b-thinking")
    # NOTE: in production `notes` come from extract_apparatus (strip transcription). For this test we
    # parse the base-md DEF block (a different format canonicalize_page isn't for) into notes directly.
    def parse_defs(block):
        out = []
        for m in re.finditer(r"^\s*(?:\[\^([a-z])\]:|\^([a-z])\^?)\s*(.+)$", block, re.M):
            out.append({"marker": f"[^{len(out)+1}]", "text": (m.group(3) or "").strip()})
        return out
    for pg in (100, 550):   # 100 has old-body anchors; 550 is anchor-barren
        md = (D / f"page{pg}_image1.md").read_text(encoding="utf-8")
        notes = parse_defs(A.split_body_defs(md)[1])
        r = link_page(notes, md, profile, pg)
        print(f"p{pg}: {r['status']} linked={r['n_linked']} unfound={r['n_unfound']} body_bytes_touched={r['body_bytes_touched']}")
        for rec in r["records"][:3]:
            print(f"   {rec['note']} @off={rec['body_char_offset']} prov={rec['provenance']}"
                  + (f" phrase='...{rec['phrase_anchor']}'" if rec['phrase_anchor'] else ""))
