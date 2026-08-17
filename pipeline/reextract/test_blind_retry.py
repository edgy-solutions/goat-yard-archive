"""blind_retry born tested — localization geometry, the independence guarantee (readers never see a
peer), script-aware convergence, and the architectural rule that hold/fold NEVER gates shipping.
Run: python test_blind_retry.py"""
from PIL import Image
import blind_retry as BR

def test_crop_note_localizes():
    strip = Image.new("L", (400, 1000), 255)
    starts = [100, 300, 700]
    c = BR.crop_note(strip, starts, 1, pad_frac=0.0)   # note 1 spans 300..700
    assert c.size[0] == 400 and c.size[1] == 400        # full width, y 300..700

def test_crop_last_note_runs_to_bottom():
    strip = Image.new("L", (400, 1000), 255)
    c = BR.crop_note(strip, [100, 300, 700], 2, pad_frac=0.0)
    assert c.size[1] == 300                              # 700..1000

def test_blind_retry_gives_readers_only_the_crop():
    # independence guarantee: a reader is called with ONE arg (the crop) and no peer channel exists
    seen = []
    def reader(crop): seen.append(crop); return "x"
    BR.blind_retry("CROP", [reader, reader])
    assert seen == ["CROP", "CROP"]                      # each saw only the crop, nothing else

def test_converged_when_readings_agree():
    assert BR.converged(["על אשר לי magistros", "על אשר לי magistros"]) is True

def test_dropped_lemma_is_not_convergence():
    # script-aware: one keeps Hebrew, one drops it -> NOT converged (would be, on naive text-only)
    assert BR.converged(["חום nigram", "nigram"]) is False

def test_resolve_converged_ships_with_provenance():
    r = BR.resolve(3, ["ac cor eorum", "ac cor eorum"])
    assert r["status"] == "converged" and r["provenance"] == "converged-on-blind-retry"

def test_resolve_diverged_escalates_with_gloss():
    r = BR.resolve(3, ["על לבם ad cor", "ad cor"], gloss="qui sunt mihi")
    assert r["status"] == "escalate" and r["gloss"] == "qui sunt mihi"
    assert r["candidates"] == ["על לבם ad cor", "ad cor"]

def test_holdfold_never_gates_shipping():
    # even if A "held", a diverged pair still escalates — hold/fold is metadata, not authority
    r = BR.resolve(3, ["אשדוד", "אשר לי"], holdfold=[{"model": 0, "verdict": "hold"}])
    assert r["status"] == "escalate"                    # NOT shipped despite the hold
    assert r["holdfold"] == [{"model": 0, "verdict": "hold"}]  # carried as metadata only

def test_challenge_round_hold_vs_fold():
    crop = "C"; originals = ["אשר לי", "אשדוד"]
    # model 0 re-reads and keeps its own -> hold; model 1 re-reads and adopts the peer -> fold
    peer_readers = [lambda c, peer: "אשר לי", lambda c, peer: "אשר לי"]
    hf = BR.challenge_round(crop, originals, peer_readers)
    assert hf[0]["verdict"] == "hold" and hf[1]["verdict"] == "fold"

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed"); raise SystemExit(1 if f else 0)
