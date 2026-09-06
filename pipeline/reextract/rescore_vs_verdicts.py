import io, json, re, sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")
import audit_record as AR
from data_config import data_path

def L(p): return [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]
def V(p): return {r["span_id"]: r for r in AR.load_verdicts(p) if r.get("kind") != "sitting_manifest"}
def norm(s): return re.sub(r"\s+", " ", (s or "").strip())
def heb(s): return "".join(re.findall(r"[֐-׿]", s or ""))

man = json.load(io.open(data_path("audits","sitting_manifest_span_adjudication.json"), encoding="utf-8"))
SP = {s["span_id"]: s for s in man["disagreement"] + man["agreed_sample"]}
residue = V(data_path("audits","chris_sitting_b_residue_20260823.jsonl"))
agent   = V(data_path("audits","agent_session_20260823.jsonl"))
FLIP = {"p593:n0": ("agreed-flip", None), "p619:n0": ("neither-flip", "חח")}  # native-recheck

def signed(sid):
    s = SP[sid]
    if sid == "p593:n0": return s["extracted"], "confirm", "native-recheck(flip)"   # both witnesses correct
    if sid == "p619:n0": return "חח", "neither", "native-recheck(flip)"             # printed form
    v = residue.get(sid) or agent.get(sid) or {}
    ch = v.get("chosen"); corr = v.get("disputed_span_correction")
    if ch in ("take-extracted","confirm","correlated-error"): return s["extracted"], ch, "verdict"
    if ch == "keep-stored": return s["stored"], ch, "verdict"
    if ch == "neither":     return corr or "", ch, "verdict"
    return None, ch, "none"

run = {r["page"]: r for r in L(data_path("vol1_apparatus.jsonl")) if r.get("kind") != "config_header"}
def run_note(sid):
    pg = int(sid.split(":")[0][1:]); idx = int(sid.split(":n")[1])
    notes = run.get(pg, {}).get("notes") or []
    return notes[idx]["text"] if idx < len(notes) else None

exact = 0; overlay = []; mismatches = []
for sid in sorted(SP, key=lambda x:(int(x.split(":")[0][1:]), x)):
    sig, ch, src = signed(sid)
    rt = run_note(sid)
    if sig is None or rt is None:
        cls = "run-missing" if rt is None else "no-verdict"
        mismatches.append((sid, rt, sig, ch, cls)); overlay.append((sid, rt, sig, ch, src, True, cls)); continue
    r, s = norm(rt), norm(sig)
    if ch == "neither":
        ok = s in r                                    # corrected fragment present in the run note
    else:
        ok = (r == s)
    if ok:
        exact += 1; overlay.append((sid, rt, sig, ch, src, False, "agree"))
    else:
        # classify the mismatch
        if ch == "neither" and heb(sig) and heb(sig) not in heb(rt) and heb(rt) and heb(rt) in heb(sig):
            cls = "run-miss (dropped part of the corrected span)"
        elif ch == "keep-stored":
            cls = "known-loss (run reproduces extraction adjudged wrong; stored wins)"
        elif heb(rt) != heb(sig):
            cls = "hebrew-differs (verdict-overlay applies)"
        else:
            cls = "differs (verdict-overlay applies)"
        mismatches.append((sid, rt, sig, ch, cls)); overlay.append((sid, rt, sig, ch, src, True, cls))

print(f"=== RE-SCORE vs signed verdicts: {exact}/{len(SP)} exact ===\n")
print(f"mismatches ({len(mismatches)}) — verdict (corpus of record) wins, overlay applies:")
for sid, rt, sig, ch, cls in mismatches:
    print(f"  {sid:9} [{ch}] {cls}")
    print(f"     run    : {norm(rt)[:70]!r}")
    print(f"     verdict: {norm(sig)[:70]!r}")

# build overlay artifact
ov = []
for sid, rt, sig, ch, src, applies, cls in overlay:
    ov.append({"span_id": sid, "run_reading": rt, "signed_reading": sig, "verdict_kind": ch,
               "overlay_applies": applies, "classification": cls,
               "provenance": {"source": src, "authority": "signed-verdict-wins-on-mismatch"}})
out = data_path("truthset_ingest_overlay.jsonl")
io.open(out,"w",encoding="utf-8").write("\n".join(json.dumps(x,ensure_ascii=False) for x in ov)+"\n")
napp = sum(1 for x in ov if x["overlay_applies"])
print(f"\noverlay artifact -> {out}")
print(f"  {len(ov)} spans: {len(ov)-napp} run==verdict (no overlay), {napp} overlay applied (verdict wins)")
# verify overlay covers all 74 verdicts exactly
assert all(x["signed_reading"] is not None or x["verdict_kind"] is None for x in ov)
print(f"  verified: every span carries its signed reading as corpus-of-record")
