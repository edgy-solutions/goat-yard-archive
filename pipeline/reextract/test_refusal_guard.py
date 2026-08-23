"""refusal_guard born tested — p4 (the real fixture) is honored as a refusal; real footnotes and
incidental mentions are not. Run: python test_refusal_guard.py"""
import refusal_guard as R

P4 = ("The provided image is not a strip of footnotes from an early Bible commentary. It is a title "
      "page or frontispiece for a work about John Gill, D.D. There are no footnotes present in this "
      "image. No output can be generated per the instructions since the input does not match the "
      "described content type.")

def test_p4_is_refusal():
    assert R.is_refusal(P4)
    ok, phrase = R.check_notes([{"text": P4}])
    assert ok and phrase

def test_real_footnotes_not_refusal():
    for t in ["סגר עליהם clausit viam illis, Pagninus, Vatablus.",
              "Nat. Hist. l. 36. c. 5.",
              "Vid. Universal History, vol. 2. p. 421, &c. See Egmont and Heyman's Travels.",
              "ראים percipiebant, Junius & Tremellius, intelligebant; so some in Drusius."]:
        assert not R.is_refusal(t), t

def test_incidental_mention_not_refusal():
    # a note that mentions a title page as CONTENT must not trip (needs the 'it is a' meta-frame)
    assert not R.is_refusal("as printed on the title page of Pagninus's edition")
    assert not R.is_refusal("see the frontispiece engraving by Chamberlin")

def test_check_notes_clean_page():
    ok, phrase = R.check_notes([{"text": "Nat. Hist. l. 36."}, {"text": "Ibid."}])
    assert not ok and phrase is None

def test_various_refusal_shapes():
    for t in ["There are no footnotes present in this crop.",
              "This image does not contain any footnote lines to transcribe.",
              "Unable to transcribe — the image is a portrait.",
              "No output can be generated."]:
        assert R.is_refusal(t), t

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed"); raise SystemExit(1 if f else 0)
