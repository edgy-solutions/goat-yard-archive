"""reference_hypothesis born-tested — three outcomes + the fabrication check, with the real sitting cases as
fixtures. Dependency-injected passage/biblical so no Tanakh load. Run: python test_reference_hypothesis.py"""
import reference_hypothesis as R

# a scoped passage (anchored verse + cited cross-refs) as consonantal word-forms
PASSAGE = {"סנה", "משה", "הר", "בער", "אש", "ברא", "עשה", "לעשות"}
BIBLICAL = {"היה", "לך", "לו", "סנה", "ברא", "עשה"}          # whole-Tanakh presence (for is_biblical)
is_biblical = lambda t: any(R._cons(w) in BIBLICAL for w in R._words(t))

def test_matches_passage_is_confirmed():
    o, hyp = R.classify("ברא לעשות", PASSAGE, is_biblical)
    assert o == "matches-passage" and hyp is not None   # all words in the passage -> confirmed, prior given

def test_p596_same_length_substitution_flagged():
    # the decisive case: היה (in 600+ verses) substituted for סנה (this passage). Whole-Bible passes it;
    # passage-scope rejects it because היה is not in THIS passage.
    o, hyp = R.classify("היה", PASSAGE, is_biblical)
    assert o == "reference-mismatch", (o, hyp)

def test_extra_biblical_is_no_reference_not_mismatch():
    # a lexicographer's form not in any OT verse -> pixels-only, NOT a flag (or the flag rate lies)
    o, hyp = R.classify("שרש", PASSAGE, lambda t: False)   # is_biblical False -> extra-biblical
    assert o == "no-reference", (o, hyp)

def test_garbage_is_flagged():
    o, hyp = R.classify("םרבד", PASSAGE, is_biblical)       # final-mem in non-final position = scrambled
    assert o == "reference-mismatch"

def test_no_hebrew():
    assert R.classify("Pagninus, Montanus", PASSAGE, is_biblical)[0] == "no-hebrew"

def test_parrot_check():
    _, hyp = R.classify("ברא לעשות", PASSAGE, is_biblical)
    assert R.is_parroted(hyp, hyp) is True                  # reader echoed the injected prior -> flag
    assert R.is_parroted("ברא לעשות", hyp) is False         # a real (different) reading -> not parroted
    assert R.is_parroted("anything", None) is False         # no hypothesis -> never "parroted"

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed"); raise SystemExit(1 if f else 0)
