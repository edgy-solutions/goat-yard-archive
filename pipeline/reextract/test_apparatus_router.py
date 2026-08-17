"""apparatus_router born tested — measured-signature dispatch (gemma-primary, qwen3.8 fallback on
collapse, queue if neither matches the CV count), and the guarantee the fallback isn't called when
the primary already matches. Run: python test_apparatus_router.py"""
import apparatus_router as R

def _reader(k):
    return lambda strip: [{"text": f"n{i}"} for i in range(k)]

def test_primary_kept_when_it_matches_cv():
    calls = []
    fb = lambda s: calls.append(1) or [{"text": "x"}]
    r = R.route("S", _reader(13), fb, cv_count=13)
    assert r["route"] == "primary" and calls == []          # fallback NOT called

def test_fallback_recovers_collapse():
    r = R.route("S", _reader(7), _reader(13), cv_count=13)   # gemma undershoots, qwen3.8 matches
    assert r["route"] == "fallback" and len(r["notes"]) == 13

def test_full_collapse_routes_to_better_match():
    r = R.route("S", _reader(1), _reader(13), cv_count=13)
    assert r["route"] == "fallback" and not r["queued"]

def test_queue_when_neither_matches():
    r = R.route("S", _reader(1), _reader(3), cv_count=13)    # both far below CV
    assert r["route"] == "queue" and r["queued"] is True

def test_low_cv_count_stays_primary():
    # cv_count < 3 -> not enough structure to arbitrate; trust primary, no fallback
    calls = []
    fb = lambda s: calls.append(1) or [{"text": "x"}]
    r = R.route("S", _reader(2), fb, cv_count=2)
    assert r["route"] == "primary" and calls == []

def test_picks_closer_to_cv_when_both_off():
    # primary=10, fallback=20, cv=13 -> primary (|10-13|=3) closer than fallback (|20-13|=7); but 3>tol
    r = R.route("S", _reader(10), _reader(20), cv_count=13)
    assert r["route"] == "primary" and len(r["notes"]) == 10   # closer wins; within tol(=3) so kept

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed"); raise SystemExit(1 if f else 0)
