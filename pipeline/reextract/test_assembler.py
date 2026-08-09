"""The assembler is BORN TESTED — it concentrates the deterministic jobs (markers-by-position,
furniture removal, letter-scope, stitch guard), so it carries the most correctness weight and gets
its suite first (Chris, 2026-08-09). Fixtures are real probe cases: p100 renumbering, the furniture
classes, the 6 stitch-whitelist artifacts, j/u-v skips. Run: python -m pytest test_assembler.py
(or `python test_assembler.py` for a dependency-free run)."""
import os
from pathlib import Path
import assembler as A

PROFILE = A.load_profile(Path(__file__).parent / "book_profile.gill.yaml")

# --- FIXTURE: real qwen3.6 p100 transcription — TRUE printed letters are q-u | w-z, model
#     RENUMBERED to a-i. The assembler must discard the model letters and assign [^1..9] by POSITION.
P100 = [
    "a In Cosmopœiam, p. 2841",
    "b Hyde Hist. Relig. vet. Pers. p. 164, 166, 168, 483, 484.",
    "c Lib. Sad-der, port. 6. 94. apud Hyde, ib. p. 439, 483.",
    "d See Universal History, vol. 1. p. 64.",
    "e T, Bab. Sanhedrin, fol. 97. 1. Avoda Zara, fol. 9. 1.",
    "f Comment. in Gen. i. 1.",
    "g Shalshelet Hakabala, fol. 36. 1.",
    "h Comment. in Maimon. Hilch. Teshuva, c. 9. sect. 2.",
    "i Lib. Sad-der, port. 11. Vid. Hyde, ut supra, p. 481.",
]

def test_markers_by_position_not_model_letters():
    r = A.canonicalize_page(P100, PROFILE)
    assert len(r["notes"]) == 9
    assert [n["marker"] for n in r["notes"]] == [f"[^{i}]" for i in range(1, 10)]
    # text preserved verbatim after the model letter is stripped
    assert r["notes"][0]["text"].startswith("In Cosmop")
    assert r["notes"][4]["text"].startswith("T, Bab. Sanhedrin")
    # model letters recorded but NOT used for the canonical marker
    assert r["notes"][0]["model_letter"] == "a" and r["notes"][0]["marker"] == "[^1]"

def test_furniture_stripped():
    lines = ["VOL. I.—OLD TEST.", "GENESIS", "CH. I. V. 3", "90", "3 D", "Y y", "5 D 2", "3 Q 2",
             "a Real note, Drusius."]
    r = A.canonicalize_page(lines, PROFILE)
    assert len(r["notes"]) == 1                       # only the real note survives
    assert r["notes"][0]["text"] == "Real note, Drusius."
    assert "Y y" in r["dropped_furniture"] and "VOL. I.—OLD TEST." in r["dropped_furniture"]

def test_stitch_whitelist_passes_all_six_artifacts():
    # the 6 measured split-OUT/IN artifacts must NOT trip the guard. (Real notes open with a
    # capital/citation/Hebrew — a lowercase open is itself the split-IN signal, so fillers are capitalized.)
    cases = [
        ["a Foo.", "b נגזר הקדשה"],                                   # p336 hebrew-final
        ["a Foo.", "b Herodotus Euterpe sive, l. 2. c. 37,"],         # p343 citation-final (comma)
        ["a Foo.", "b Plin. Nat. Hist. l. 36. c. 5"],                # p740 citation-final (no period)
        ["a Foo.", "b Pagninus, Montanus, Junius & Tremellius, Piscator, Drusius"],  # p757 authority list
        ["b contracta, Junius & Tremellius, Piscator.", "z End."],   # p692 latin-gloss lowercase open
    ]
    for lines in cases:
        r = A.canonicalize_page(lines, PROFILE)
        assert A.assert_no_text_split(r["notes"], PROFILE) == [], f"false split on {lines}"

def test_intra_strip_linewrap_is_rejoined_not_a_new_note():
    # real p473 case: note n wrapped across two strip lines ("...Va-" / "tablus.") and the model
    # kept the wrap. The marker-less 2nd line must MERGE (hyphen-join) into the note, not become [^14].
    lines = ["a First, Drusius.",
             "b סגר עליהם clausit viam illis, Pagninus, præclusit sese illis, Va-",
             "tablus.",
             "c Last, p. 309."]
    r = A.canonicalize_page(lines, PROFILE)
    assert len(r["notes"]) == 3, [n["text"] for n in r["notes"]]
    assert r["notes"][1]["text"].endswith("Vatablus.")           # Va- + tablus -> Vatablus
    assert [n["marker"] for n in r["notes"]] == ["[^1]", "[^2]", "[^3]"]

def test_signature_final_line_is_furniture_not_a_split():
    # p433 "Y y" / p843 "5 D 2": a bare signature line is FURNITURE (dropped), so the last real
    # note stays terminal — it must not be parsed as a mid-sentence note.
    r = A.canonicalize_page(["a Real note, Drusius.", "Y y"], PROFILE)
    assert len(r["notes"]) == 1 and "Y y" in r["dropped_furniture"]
    assert A.assert_no_text_split(r["notes"], PROFILE) == []

def test_stitch_guard_FIRES_on_a_real_split():
    # synthetic genuine text-split: last note ends mid-English-sentence; next page opens mid-sentence
    out_page = A.canonicalize_page(["a Complete.", "b and being thus wholly overcome he was"], PROFILE)
    in_page  = A.canonicalize_page(["compelled to flee into the land of Nod.", "c Next, Drusius."], PROFILE)
    vout = A.assert_no_text_split(out_page["notes"], PROFILE)
    vin  = A.assert_no_text_split(in_page["notes"], PROFILE)
    assert any(v["signal"] == "split_out" for v in vout), "guard missed a real split-OUT"
    assert any(v["signal"] == "split_in" for v in vin), "guard missed a real split-IN"

def test_letter_run_honors_j_and_uv_skips():
    # 1766: j skipped (i -> k); u/v interchange -> v skipped (u -> w). Observed on p100 (q-u|w-z).
    assert A.letter_run("q", 6, PROFILE) == ["q", "r", "s", "t", "u", "w"]   # v skipped
    assert A.letter_run("h", 3, PROFILE) == ["h", "i", "k"]                  # j skipped
    assert A.advance_letter("i", A.effective_skips(PROFILE)) == "k"
    assert A.advance_letter("u", A.effective_skips(PROFILE)) == "w"

def test_hebrew_note_preserved_and_not_a_split():
    # a note whose text ends in Hebrew (p473 note n's antitype gloss) is complete, not a split-out
    lines = ["a Foo.", "b סגר עליהם clausit viam illis, Pagninus, præclusit sese illis, Vatablus."]
    r = A.canonicalize_page(lines, PROFILE)
    assert "סגר עליהם" in r["notes"][1]["text"]
    assert A.assert_no_text_split(r["notes"], PROFILE) == []

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try:
            fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception:
            f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed")
    raise SystemExit(1 if f else 0)
