"""AUDIT OBSERVABILITY (Build 2 foundation) — door-independent per-verdict records. The API audit path
is observable by construction (request/response/usage.cost/timestamp); the agent-in-session path's
evidence otherwise scrolls away in session history — the adjudication-console failure shape again
(judgment in a medium with no durable output). So the agent path emits the SAME artifact the API gets
for free: one JSONL line per verdict, written AS the audit runs (never summarized after — the
end-summary is the rosy-Axis-1 pattern: a narrative about the evidence instead of the evidence).

Each record carries: the verdict in the ENFORCED schema (identical to the API path, so downstream can't
tell the doors apart structurally); the DOOR and its conditions (on the agent path, session_freshness
replaces usage.cost as the load-bearing attestation — cold-context is what makes it independent); and
the INPUTS PINNED BY HASH (crop path+sha, both candidates verbatim) so the verdict is re-auditable, not
a diary. Plus a per-sitting MANIFEST so coverage is itself checkable. The three-column console renders
straight from these records. Prose reports are derived-only, checkable against the JSONL.
"""
import hashlib, json
from pathlib import Path

DOORS = ("adjudicated-by-frontier-via-api", "audited-by-agent-in-session",
         # rung 5 of the dispute ladder — the human review queue. A real door, not a courtesy: when the
         # cheaper rungs leave a span disputed it lands on a person, and that verdict needs the same
         # pinned-input record as the other two. session_freshness is not load-bearing here (a human is
         # not a context window) but stays present so every record is structurally one shape.
         "adjudicated-by-human-review")
VERDICT_FIELDS = ("span_id", "chosen", "disputed_span_correction", "rationale", "confidence")

def _sha16(path):
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else None

def audit_record(span_id, chosen, correction, rationale, confidence, *, door, model, date,
                 crop_path, candidates, cold_context, note_text=None):
    """Build one audit verdict record. VERDICT-ONLY LAW rides along: `correction` is a disputed SPAN,
    never a re-transcription — a correction as long as the whole note would let the auditor become a
    third witness (the API path's born-test, re-asserted on what lands in the record)."""
    if door not in DOORS: raise ValueError(f"unknown door: {door}")
    if chosen not in ("A", "B", "neither"): raise ValueError(f"chosen must be A/B/neither: {chosen}")
    if note_text and correction and len(correction) > 0.6 * len(note_text):
        raise ValueError("correction too long — verdict must be a span, not a re-transcription")
    return {
        "span_id": span_id, "chosen": chosen, "disputed_span_correction": correction,
        "rationale": rationale, "confidence": confidence,
        "provenance": {"door": door, "model": model, "date": date,
                       # on the agent path this is the load-bearing claim (cost is on the API path)
                       "session_freshness": "cold-context" if cold_context else "in-context-WARN"},
        "inputs": {"crop": crop_path, "crop_sha16": _sha16(crop_path), "candidates": list(candidates)},
    }

def validate(record):
    """A record is observability (not a diary) iff: verdict schema present, door named, inputs pinned."""
    for f in VERDICT_FIELDS:
        if f not in record: raise ValueError(f"missing verdict field: {f}")
    pv = record.get("provenance", {})
    if pv.get("door") not in DOORS: raise ValueError("provenance.door missing/invalid")
    if "session_freshness" not in pv: raise ValueError("session_freshness attestation missing")
    inp = record.get("inputs", {})
    if not inp.get("crop") or inp.get("crop_sha16") is None: raise ValueError("inputs.crop not pinned by hash")
    if not inp.get("candidates"): raise ValueError("inputs.candidates not pinned verbatim")
    return True

def append_verdict(jsonl_path, record):
    """Append one validated verdict AS it's made (not batched at the end)."""
    validate(record)
    with open(jsonl_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record

def sitting_manifest(spans, sampling_rule, date, door, *, sitting=None, session_freshness="cold-context"):
    """Per-sitting batch manifest so coverage is auditable — 'sampled 200 agreed spans' is a checkable
    list, not a sentence. Emits `sitting` and `session_freshness` because `verify_sitting_export.py`
    reads them for its header — the builder and the reader must agree on the manifest's shape (a live
    audit found them disagreeing: the verifier printed `?` and the auditor had to hand-populate)."""
    return {"kind": "sitting_manifest", "sitting": sitting, "date": date, "door": door,
            "session_freshness": session_freshness, "sampling_rule": sampling_rule,
            "n_spans": len(spans), "span_ids": list(spans)}

def load_verdicts(jsonl_path):
    p = Path(jsonl_path)
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []
