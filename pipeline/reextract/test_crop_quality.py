"""crop_quality born tested — the two free deterministic checks (positions >= one line-height; crop >=
one line of ink) and reconcile's law (strip is the floor; agreement -> per-note; DISAGREEMENT -> ladder,
never preference). p219 is the permanent fixture that taught the invariant. Run: python test_crop_quality.py"""
import numpy as np
from PIL import Image
import crop_quality as CQ

def _line_crop(H=120, ink_rows=40):
    a = np.full((H, 400), 255, np.uint8); a[20:20 + ink_rows, 20:380] = 0  # a real line of text
    return Image.fromarray(a)

def _sliver_crop(H=208):
    a = np.full((H, 400), 255, np.uint8); a[4:10, :] = 0; a[12:16, 20:60] = 0  # rule + a few letter-tops
    return Image.fromarray(a)

def test_positions_valid_basics():
    assert CQ.positions_valid([100, 300, 700], 120) is True    # ample gaps
    assert CQ.positions_valid([100], 120) is True              # single note ok

def test_positions_valid_catches_collapsed_starts():
    assert CQ.positions_valid([100, 130], 120) is False        # 30px gap, 120 line-height -> impossible

def test_p219_is_a_crop_check_catch_not_position():
    # DIVISION OF LABOR: p219's gap (160) vs line-height (181) is 0.88 lh — BORDERLINE, so the position
    # check does NOT fire; p219's starved sliver is caught by the CROP-content check instead. The two
    # checks cover different failure shapes; this pins that p219 belongs to the crop check.
    assert CQ.positions_valid([656, 816], 181) is True         # position check silent on borderline gap

def test_crop_has_line_separates_sliver_from_note():
    assert CQ.crop_has_line(_line_crop()) is True
    assert CQ.crop_has_line(_sliver_crop()) is False       # rule + tops -> starved, don't send

def test_reconcile_starved_takes_strip_floor():
    strip = [{"text": "הואלתי לדבר cœpi loquar"}, {"text": "Gestio, volo, cupio"}]
    per = [{"text": "", "starved": True}, {"text": "Gestio, volo, cupio"}]
    notes, disputes = CQ.reconcile(strip, per, starved_idx={0})
    assert notes[0]["text"] == "הואלתי לדבר cœpi loquar" and notes[0]["provenance"] == "strip-floor"
    assert not disputes                                    # note 1 agreed -> per-note, no ladder

def test_reconcile_disagreement_routes_to_ladder_not_preference():
    # both crops usable, readings DIFFER -> dispute for the ladder; strip floor holds meanwhile
    strip = [{"text": "על אשר לי magistros"}]
    per = [{"text": "על אשדוד magistros"}]
    notes, disputes = CQ.reconcile(strip, per, starved_idx=set())
    assert len(disputes) == 1 and disputes[0][0] == 0
    assert notes[0]["provenance"] == "strip-floor-pending-ladder"   # NOT resolved by preference

def test_reconcile_agreement_takes_per_note():
    strip = [{"text": "Nat. Hist. l. 36."}]; per = [{"text": "Nat. Hist. l. 36."}]
    notes, disputes = CQ.reconcile(strip, per, starved_idx=set())
    assert notes[0]["provenance"] == "per-note" and not disputes

def test_p219_fixture_sliver_gated():
    """p219 — the PERMANENT fixture that taught the invariant (Build 3). If the scan is present, its
    first per-note crop is a starved rule+tops sliver and MUST be gated (crop_has_line False) so per-note
    never hands it to a model; the second crop (a real note) passes. This is the regression that guards
    against the p219-class silently returning."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    img = Path("c:/Users/cnogr/git/dr-voluminous/commentary/volume1/page219_image1.png")
    if not img.exists(): return
    import cv_footnote_presplit as ps, hanging_indent as hi, blind_retry as BR
    strip, _ = ps.presplit(str(img), upscale=4)
    _cv, starts, _conf = hi.count_notes(strip, upscale=4)
    assert CQ.crop_has_line(BR.crop_note(strip, starts, 0)) is False   # the starved sliver -> gated
    assert CQ.crop_has_line(BR.crop_note(strip, starts, 1)) is True    # the real note -> kept

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed"); raise SystemExit(1 if f else 0)
