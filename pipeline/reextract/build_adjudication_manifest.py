"""Span-adjudication manifest — the two-witness comparison that MUST be signed off before the
re-extraction replaces the stored corpus. The two witnesses already coexist per span in the truthset run:

  witness A = STORED    (what is in Weaviate now — the old reading)
  witness B = EXTRACTED (the re-extraction pipeline's reading)

Every span where they disagree is a PROPOSED CHANGE Chris must approve (three-column: stored | extracted
| why). A sample of spans where they AGREE is the agent's correlated-error check — unanimity is
confidence only over shared evidence, so a fresh reader spot-checks that agreement isn't shared blindness.

The two sets are EXPLICITLY DISJOINT: a span is a proposed change XOR an agreement — never both. Alignment
is positional (stored carries letter markers a,b,c…; extracted carries [^1],[^2]… — same ordered notes);
when the two witnesses disagree even on COUNT, the page can't be aligned and every span on it is a
disagreement of kind 'count' (the structural gate from the ladder fires first)."""
import sys, io, json, hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from agreement_ladder import scripts_in, _tokens

HERE = Path(__file__).parent
TRUTHSET = HERE / "truthset_review" / "truthset_results.json"
STRIPS = HERE / "truthset_review"          # strip_{page}.png live here
OUT = HERE / "audits" / "sitting_manifest_span_adjudication.json"
AGREED_TARGET = 200
TEXT_OVERLAP_MIN = 0.5

def _load(p): return json.load(io.open(p, encoding="utf-8"))

def _sha16(s): return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]

def classify(a, b):
    """Rung-ordered witness comparison (same order as agreement_ladder): script diff dominates text diff."""
    sa, sb = scripts_in(a), scripts_in(b)
    if sa != sb:
        dropped = sorted((sa | sb) - (sa & sb))
        return "script", f"script set differs (dropped {', '.join(dropped)})"
    ta, tb = _tokens(a), _tokens(b)
    ov = len(ta & tb) / max(1, len(ta | tb))
    if ov < TEXT_OVERLAP_MIN:
        return "text", f"token overlap {ov:.2f} < {TEXT_OVERLAP_MIN}"
    if a.strip() != b.strip():
        return "minor", f"token overlap {ov:.2f} but not byte-identical"
    return "agree", None

def build():
    pages = _load(TRUTHSET)
    disagreement, agreed, count_reconcile = [], [], []
    seen = set()                                       # enforce disjointness by span_id
    for r in pages:
        pg = r["page"]
        strip = f"strip_{pg}.png" if (STRIPS / f"strip_{pg}.png").exists() else None
        st = [s for s in r.get("stored", []) if s and s.get("text")]
        ex = [s for s in r.get("extracted", []) if s and s.get("text")]
        if not st and not ex:
            continue
        if len(st) != len(ex):                          # RUNG 0: count mismatch — NOT a text adjudication.
            # The count rung is owned by the deterministic CV counter + Sitting A position jaws; recording
            # it here (not in the three-column text view) so nothing is silently dropped, but it is a
            # different sitting's question. One page-level row, both full lists, pointed at its real home.
            count_reconcile.append({
                "page": pg, "stored_n": len(st), "extracted_n": len(ex), "strip": strip,
                "home": "CV counter (rung 0) + Sitting A position jaws",
                "stored": [s["text"] for s in st], "extracted": [s["text"] for s in ex]})
            continue
        for i, (a, b) in enumerate(zip(st, ex)):         # aligned positionally
            sid = f"p{pg}:n{i}"
            if sid in seen: continue
            seen.add(sid)
            kind, why = classify(a["text"], b["text"])
            rec = {"span_id": sid, "page": pg, "stored": a["text"], "extracted": b["text"],
                   "strip": strip, "inputs_sha16": _sha16(a["text"] + "␟" + b["text"])}
            if kind == "agree":
                agreed.append({**rec, "witnesses": "stored==extracted"})
            else:
                disagreement.append({**rec, "kind": kind, "reason": why})
    # agreed sample: cap at target; deterministic stride so it spans pages, not just the first N
    sample = agreed
    truncated = False
    if len(agreed) > AGREED_TARGET:
        step = len(agreed) / AGREED_TARGET
        sample = [agreed[int(i * step)] for i in range(AGREED_TARGET)]
        truncated = True
    manifest = {
        "kind": "span_adjudication_manifest",
        "witnesses": {"A": "stored (current corpus)", "B": "extracted (re-extraction pipeline)"},
        "disjoint": True,
        "notes": (
            f"ROUTING: {len(count_reconcile)} pages where the two witnesses disagree on NOTE COUNT are "
            "NOT in the disagreement set below — a count change is not a text adjudication. They route to "
            "the count rung (deterministic CV counter + Sitting A position jaws) and are listed under "
            "'count_reconcile' so their absence from Sitting B is documented, not silent. Sitting B "
            "adjudicates only spans that align 1:1 and diverge in TEXT."),
        "counts": {"disagreement": len(disagreement), "agreed_total": len(agreed),
                   "agreed_sample": len(sample), "agreed_target": AGREED_TARGET,
                   "agreed_truncated": truncated, "count_reconcile_pages": len(count_reconcile)},
        "limit": (None if not truncated and len(agreed) >= AGREED_TARGET else
                  f"agreed sample is {len(sample)} (all available two-witness agreements); "
                  f"reaching {AGREED_TARGET} needs a two-witness run over more of the corpus than the "
                  f"{len(pages)}-page truthset provides"),
        "disagreement": sorted(disagreement, key=lambda d: (d["page"], d["span_id"])),
        "agreed_sample": sample,
        "count_reconcile": sorted(count_reconcile, key=lambda d: d["page"]),
    }
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    # disjointness assertion
    dids = {d["span_id"] for d in disagreement}; aids = {a["span_id"] for a in agreed}
    assert not (dids & aids), f"NOT DISJOINT: {dids & aids}"
    print(f"wrote {OUT}")
    print(f"  disagreement (text-level): {len(disagreement)}  (kinds: "
          f"{ {k: sum(1 for d in disagreement if d.get('kind')==k) for k in ('script','text','minor')} })")
    print(f"  agreed total: {len(agreed)}  sample: {len(sample)}  disjoint: OK")
    print(f"  count_reconcile pages (other sitting's question): {len(count_reconcile)}")
    if manifest["limit"]: print(f"  LIMIT: {manifest['limit']}")

if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    build()
