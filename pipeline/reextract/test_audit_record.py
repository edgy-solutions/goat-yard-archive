"""audit_record born tested — the verdict-only law rides on the record (correction can't be a
re-transcription), the door is named, inputs are pinned by hash, freshness attested, and a diary
(unpinned) is rejected as not-observability. Run: python test_audit_record.py"""
import json, tempfile, os
import audit_record as AR

CROP = __file__  # any real file, for a real hash
NOTE = "על אשר לי magistros pecuariae super illos, qui sunt mihi, Junius & Tremellius"

def _rec(**kw):
    d = dict(span_id="p379:n2", chosen="A", correction="על אשר לי", rationale="cited qui sunt mihi",
             confidence=0.9, door="audited-by-agent-in-session", model="claude-in-session",
             date="2026-08-16", crop_path=CROP, candidates=["על אשר לי", "על אשדוד"], cold_context=True)
    d.update(kw); return AR.audit_record(**d)

def test_record_validates():
    assert AR.validate(_rec())

def test_verdict_only_rejects_retranscription():
    # a "correction" as long as the whole note would make the auditor a third witness -> rejected
    try:
        _rec(correction=NOTE, note_text=NOTE); raise SystemExit("re-transcription not rejected")
    except ValueError: pass

def test_inputs_pinned_by_hash():
    r = _rec()
    assert r["inputs"]["crop_sha16"] and len(r["inputs"]["crop_sha16"]) == 16
    assert r["inputs"]["candidates"] == ["על אשר לי", "על אשדוד"]        # verbatim, re-auditable

def test_door_named_and_freshness_attested():
    r = _rec()
    assert r["provenance"]["door"] == "audited-by-agent-in-session"
    assert r["provenance"]["session_freshness"] == "cold-context"
    warn = _rec(cold_context=False)
    assert warn["provenance"]["session_freshness"] == "in-context-WARN"   # the anchoring risk flagged

def test_api_and_agent_doors_structurally_identical():
    a = _rec(door="audited-by-agent-in-session"); b = _rec(door="adjudicated-by-frontier-via-api")
    assert set(a) == set(b) and set(a["provenance"]) == set(b["provenance"])  # can't tell doors apart by shape

def test_diary_rejected():
    # a record missing pinned inputs is a diary, not observability
    bad = _rec(); bad["inputs"]["crop_sha16"] = None
    try: AR.validate(bad); raise SystemExit("diary accepted")
    except ValueError: pass

def test_append_and_reload_roundtrip():
    fd, path = tempfile.mkstemp(suffix=".jsonl"); os.close(fd)
    try:
        AR.append_verdict(path, _rec(span_id="s1"))
        AR.append_verdict(path, _rec(span_id="s2", chosen="neither", correction=""))
        v = AR.load_verdicts(path)
        assert len(v) == 2 and v[1]["chosen"] == "neither"
    finally: os.remove(path)

def test_manifest_is_checkable_list():
    m = AR.sitting_manifest(["s1", "s2", "s3"], "random-200-agreed", "2026-08-16", "audited-by-agent-in-session")
    assert m["n_spans"] == 3 and m["span_ids"] == ["s1", "s2", "s3"]      # coverage is a list, not a sentence

def test_manifest_emits_keys_the_verifier_reads():
    # builder/reader agreement: verify_sitting_export.py's header reads `sitting` + `session_freshness`.
    # A live audit found the builder NOT emitting them (verifier printed `?`); lock it so it can't drift.
    m = AR.sitting_manifest(["s1"], "rule", "2026-08-23", "audited-by-agent-in-session",
                            sitting="span-adjudication / agreed-sample", session_freshness="cold-context")
    assert m["sitting"] == "span-adjudication / agreed-sample"
    assert m["session_freshness"] == "cold-context"

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed"); raise SystemExit(1 if f else 0)
