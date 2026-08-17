"""BLIND-RETRY disagreement protocol — how a note flagged by the agreement_ladder gets resolved.

The architecture (Chris's ruling, and the reason it's shaped this way):
  - On disagreement, re-run BOTH models BLIND on the LOCALIZED note-crop ("transcribe THIS note",
    cropped tight per the one-job law) — WITHOUT showing either the other's reading. Independence is
    the entire value of dual-witness; showing peers converts two witnesses into a committee that folds
    toward the more confident phrasing (LLMs measurably fold toward a presented anchor — the same
    reason peer-output-as-context was rejected for the recrop).
  - CONVERGE on blind retry -> ship, provenance 'converged-on-blind-retry' (two independent readings
    agreeing without contamination = genuinely strong).
  - DIVERGE -> the span was never going to self-resolve; queue to the escalation tier, where a stronger
    ADJUDICATOR (not a peer) weighs both candidates against the note's own gloss ("qui sunt mihi"
    settles אשר לי over אשדוד — cross-examination in front of a judge with evidence, done once at the top).
  - HOLD/FOLD challenge (show each model the other's reading, record who holds under pressure) is
    OPTIONAL METADATA inside the escalation package, never a shipping gate: persistence confounds
    pixel-conviction with prior-conviction (Gerson-over-Gersom was the model holding against the
    pixels), so it's evidence FOR the adjudicator, never authority over the output. Stochastic-never-
    authoritative; stochastic-as-evidence-for-the-judge is fine — that is what the tier is.

Readers are INJECTED (callables), so the protocol is deterministic-testable; the real reader is a VLM
crop->text adapter. crop_note uses hanging_indent's note-start y-positions to localize.
"""
import agreement_ladder as AL

def crop_note(strip, note_starts, k, pad_frac=0.15):
    """Sub-image of note k: from note_starts[k] to the next start (or strip bottom), full width, with
    a small vertical pad. note_starts = sorted y0 list from hanging_indent.count_notes."""
    W, H = strip.size
    ys = sorted(note_starts)
    if not ys or k >= len(ys): return strip
    y0 = ys[k]; y1 = ys[k + 1] if k + 1 < len(ys) else H
    pad = int((y1 - y0) * pad_frac)
    return strip.crop((0, max(0, y0 - pad), W, min(H, y1 + pad)))

def blind_retry(crop, readers):
    """Each reader sees ONLY the crop — never a peer's text. Returns [reading]. This function is the
    guarantee of independence: it has no channel to pass one reader's output to another."""
    return [r(crop) for r in readers]

def converged(readings):
    """True iff every pair of blind readings clears the agreement ladder (same scripts + text overlap).
    Uses the ladder so convergence is script-aware (a dropped-lemma re-run does NOT count as converged)."""
    if len(readings) < 2: return True
    return all(AL.ladder([readings[0]], [readings[i]])["rung"] == "agree" for i in range(1, len(readings)))

def resolve(note_idx, readings, gloss=None, holdfold=None):
    """Blind-retry outcome. CONVERGE -> ship with provenance. DIVERGE -> escalation package (candidates
    + gloss + optional hold/fold metadata). NOTE: holdfold is carried into the package but NEVER used
    here to decide what ships — that is the whole point."""
    if converged(readings):
        return {"status": "converged", "note": note_idx, "text": readings[0],
                "provenance": "converged-on-blind-retry"}
    return {"status": "escalate", "note": note_idx, "candidates": list(readings),
            "gloss": gloss, "holdfold": holdfold}   # metadata only; adjudicator weighs it

def challenge_round(crop, originals, peer_readers):
    """OPTIONAL, run only for an escalation package. peer_readers[i](crop, peer_text) re-reads note i
    AFTER seeing the other's reading. Classifies each: 'hold' (new == own original) or 'fold' (new ==
    peer's). Returns metadata for the adjudicator — never a gate."""
    out = []
    n = len(originals)
    for i, reader in enumerate(peer_readers):
        peer = originals[1 - i] if n == 2 else " | ".join(originals[j] for j in range(n) if j != i)
        new = reader(crop, peer)
        own_ok = AL.ladder([new], [originals[i]])["rung"] == "agree"
        peer_ok = AL.ladder([new], [peer])["rung"] == "agree"
        out.append({"model": i, "verdict": "hold" if own_ok and not peer_ok else
                    ("fold" if peer_ok and not own_ok else "shift")})
    return out

if __name__ == "__main__":
    import sys
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    # blind retry converges -> ship
    conv = blind_retry("CROP", [lambda c: "על אשר לי magistros", lambda c: "על אשר לי magistros"])
    print("converged ->", resolve(2, conv)["status"], resolve(2, conv)["provenance"])
    # blind retry still diverges (dropped lemma) -> escalate with gloss
    div = ["על אשר לי magistros", "magistros"]
    print("diverged  ->", resolve(2, div, gloss="qui sunt mihi")["status"],
          "| gloss carried:", resolve(2, div, gloss="qui sunt mihi")["gloss"])
