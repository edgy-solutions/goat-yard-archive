"""Born-tests for the ADR-0009 structured answer path.

Every assertion here is about a DETERMINISTIC property of the schema-to-prose seam — no
model is called. These are the properties the typed schema is supposed to buy, so they
are tested at the layer where the value actually lands rather than inferred from an
eval score:

  - `zone3_notes` never reaches rendered prose (it is logged, and only logged)
  - a flat refusal renders the exact canonical wording the eval's `is_refusal` keys on,
    because code owns that string rather than trusting the model to echo it
  - Scripture never claims a Gill citation (the 2026-06-22 Garden of Eden class)
  - Scripture surfaced as adjacent refusal material is flagged (2026-07-12 GILL-ONLY)
  - a fabricated Sentence ID is caught by field comparison, not by scraping prose
  - the rendered prose pairs under `bot.QUOTE_WITH_CITE_RE`, so the existing quote
    verifier sees structured answers exactly as it sees DSPy ones
  - the flag defaults OFF

What these do NOT test: whether the model fills the schema well. That is the eval's
job, and no unit test can stand in for it.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from baml_client.types import GillAnswer, GillRefusal, Zone2Phrase  # noqa: E402
from backend import structured_answer as sa  # noqa: E402

VALID = {"[GENESIS_02_08_S01]", "[GENESIS_02_08_S02]"}
BOOKS = "Genesis, Matthew"


def _answer(**kw) -> GillAnswer:
    base = dict(reasoning="r", zone1_interpretation=None, phrases=[], refusal=None, zone3_notes=None)
    base.update(kw)
    return GillAnswer(**base)


def _phrase(**kw) -> Zone2Phrase:
    base = dict(framing="On this passage, Gill writes:", gill_quote=None,
                scripture_quote=None, sentence_id="[GENESIS_02_08_S01]")
    base.update(kw)
    return Zone2Phrase(**base)


# --------------------------------------------------------------------------
# The flag
# --------------------------------------------------------------------------

class _env:
    """Set/clear GILL_STRUCTURED_ANSWER and always put it back."""

    def __init__(self, val):
        self.val = val

    def __enter__(self):
        self.prev = os.environ.get("GILL_STRUCTURED_ANSWER")
        if self.val is None:
            os.environ.pop("GILL_STRUCTURED_ANSWER", None)
        else:
            os.environ["GILL_STRUCTURED_ANSWER"] = self.val

    def __exit__(self, *a):
        os.environ.pop("GILL_STRUCTURED_ANSWER", None)
        if self.prev is not None:
            os.environ["GILL_STRUCTURED_ANSWER"] = self.prev


def test_flag_defaults_off():
    with _env(None):
        assert sa.structured_enabled() is False


def test_flag_parsing():
    cases = [("1", True), ("true", True), ("TRUE", True), ("on", True), ("yes", True),
             ("0", False), ("false", False), ("", False), ("maybe", False)]
    for val, expected in cases:
        with _env(val):
            assert sa.structured_enabled() is expected, f"{val!r} -> expected {expected}"


# --------------------------------------------------------------------------
# zone3_notes — the whole point of the sinkhole
# --------------------------------------------------------------------------

def test_zone3_notes_never_rendered_but_always_logged():
    leak = "Gill takes the monocovenantal position throughout."
    ans = _answer(
        phrases=[_phrase(gill_quote="the garden of Eden was a real place")],
        zone3_notes=leak,
    )
    prose, _, meta = sa.render(ans, BOOKS)
    assert leak not in prose
    assert "monocovenantal" not in prose
    assert meta["zone3_notes"] == leak


def test_zone3_notes_absent_from_a_refusal_render_too():
    leak = "Gill would surely have argued against this."
    ans = _answer(
        refusal=GillRefusal(mode="flat", gap_statement="nothing on pizza", adjacent_phrases=[]),
        zone3_notes=leak,
    )
    prose, _, meta = sa.render(ans, BOOKS)
    assert leak not in prose
    assert meta["zone3_notes"] == leak


# --------------------------------------------------------------------------
# Flat refusal — deterministic wording, code-owned
# --------------------------------------------------------------------------

def test_flat_refusal_renders_canonical_wording_not_the_models():
    ans = _answer(refusal=GillRefusal(
        mode="flat",
        gap_statement="The corpus says nothing whatsoever about pizza.",
        adjacent_phrases=[],
    ))
    prose, cites, meta = sa.render(ans, BOOKS)
    assert prose == sa.FLAT_REFUSAL_TEMPLATE.format(available_books=BOOKS)
    # The model's own wording is logged, never shown.
    assert "pizza" not in prose
    assert meta["model_gap_statement"] == "The corpus says nothing whatsoever about pizza."
    assert cites == []


def test_flat_refusal_trips_the_eval_refusal_markers():
    """evals/run_eval.py keys `is_refusal` on these two substrings."""
    markers = ("regret that the provided extracts",
               "do not appear to address this specific inquiry")
    ans = _answer(refusal=GillRefusal(mode="flat", gap_statement="g", adjacent_phrases=[]))
    prose, _, _ = sa.render(ans, BOOKS)
    assert all(m in prose.lower() for m in markers)


def test_flat_refusal_string_matches_the_dspy_paths_constant():
    """If bot.py's fallback wording ever drifts from this module's, both must move."""
    from backend import bot
    import inspect
    src = inspect.getsource(bot.GroundedGillBot.forward)
    assert "I regret that the provided extracts from the Doctor's writings " in src
    assert "do not appear to address this specific inquiry. Could it be that " in src
    assert "I regret that the provided extracts from the Doctor's writings " in sa.FLAT_REFUSAL_TEMPLATE
    assert "do not appear to address this specific inquiry. Could it be that " in sa.FLAT_REFUSAL_TEMPLATE


# --------------------------------------------------------------------------
# Scripture vs Gill — the Garden of Eden class
# --------------------------------------------------------------------------

def test_scripture_quote_never_claims_a_gill_citation():
    ans = _answer(phrases=[_phrase(
        framing="The verse reads:",
        scripture_quote="And the LORD God planted a garden eastward in Eden",
    )])
    prose, cites, _ = sa.render(ans, BOOKS)
    assert cites == []                      # no Gill citation asserted
    assert "garden eastward in Eden" in prose  # but the reader still sees it


def test_a_phrase_cannot_be_both_gill_and_scripture():
    ans = _answer(phrases=[_phrase(gill_quote="g", scripture_quote="s")])
    viols = sa.check_structure(ans, VALID)
    assert any("both gill_quote and scripture_quote" in v for v in viols)


def test_a_phrase_must_carry_some_quote():
    ans = _answer(phrases=[_phrase()])
    viols = sa.check_structure(ans, VALID)
    assert any("neither gill_quote nor scripture_quote" in v for v in viols)


def test_scripture_as_adjacent_refusal_material_is_flagged():
    """The 2026-07-12 refusal-path fix, as a field check rather than a prose heuristic."""
    ans = _answer(refusal=GillRefusal(
        mode="informative", gap_statement="gap",
        adjacent_phrases=[_phrase(framing="the nearest indexed material is:",
                                  scripture_quote="For it is written",
                                  sentence_id="[GENESIS_02_08_S02]")],
    ))
    viols = sa.check_structure(ans, VALID)
    assert any("GILL-ONLY" in v for v in viols)


# --------------------------------------------------------------------------
# Sentence IDs
# --------------------------------------------------------------------------

def test_fabricated_sentence_id_is_caught_by_field_comparison():
    ans = _answer(phrases=[_phrase(gill_quote="q", sentence_id="[JOHN_99_99_S01]")])
    viols = sa.check_structure(ans, VALID)
    assert any("not in the retrieved context" in v for v in viols)


def test_sentence_id_is_normalized_to_bracketed_uppercase():
    ans = _answer(phrases=[_phrase(gill_quote="q", sentence_id="genesis_02_08_s01")])
    prose, cites, _ = sa.render(ans, BOOKS)
    assert cites == ["[GENESIS_02_08_S01]"]
    assert "[GENESIS_02_08_S01]" in prose
    assert sa.check_structure(ans, VALID) == []


def test_a_non_sentence_id_is_flagged():
    ans = _answer(phrases=[_phrase(gill_quote="q", sentence_id="Vol 1, p. 287")])
    viols = sa.check_structure(ans, VALID)
    assert any("is not a Sentence ID" in v for v in viols)


# --------------------------------------------------------------------------
# Exactly-one-of, and the shape of a refusal
# --------------------------------------------------------------------------

def test_phrases_and_refusal_are_mutually_exclusive():
    ans = _answer(
        phrases=[_phrase(gill_quote="q")],
        refusal=GillRefusal(mode="flat", gap_statement="g", adjacent_phrases=[]),
    )
    assert any("exactly one is allowed" in v for v in sa.check_structure(ans, VALID))


def test_an_empty_answer_is_flagged():
    assert any("neither phrases nor refusal" in v for v in sa.check_structure(_answer(), VALID))


def test_informative_refusal_with_no_adjacent_material_is_flagged():
    """An informative refusal surfacing nothing is a flat refusal that took longer."""
    ans = _answer(refusal=GillRefusal(mode="informative", gap_statement="g", adjacent_phrases=[]))
    assert any("no adjacent_phrases" in v for v in sa.check_structure(ans, VALID))


def test_flat_refusal_carrying_adjacent_material_is_flagged():
    ans = _answer(refusal=GillRefusal(
        mode="flat", gap_statement="g",
        adjacent_phrases=[_phrase(gill_quote="q", sentence_id="[GENESIS_02_08_S02]")]))
    assert any("'flat' with 1 adjacent_phrases" in v for v in sa.check_structure(ans, VALID))


def test_unknown_refusal_mode_is_flagged():
    ans = _answer(refusal=GillRefusal(mode="soft", gap_statement="g", adjacent_phrases=[]))
    assert any("neither 'flat' nor 'informative'" in v for v in sa.check_structure(ans, VALID))


def test_informative_refusal_renders_gap_then_adjacent_material():
    ans = _answer(refusal=GillRefusal(
        mode="informative",
        gap_statement="The indexed corpus does not contain Gill on exclusive psalmody.",
        adjacent_phrases=[_phrase(framing="the nearest indexed material is:",
                                  gill_quote="they sung an hymn",
                                  sentence_id="[GENESIS_02_08_S02]")]))
    prose, cites, meta = sa.render(ans, BOOKS)
    assert prose.startswith("The indexed corpus does not contain")
    assert '"they sung an hymn" [GENESIS_02_08_S02]' in prose
    assert cites == ["[GENESIS_02_08_S02]"]
    assert meta["refusal_mode"] == "informative"
    assert sa.check_structure(ans, VALID) == []


# --------------------------------------------------------------------------
# The seam with the existing verifier
# --------------------------------------------------------------------------

def test_rendered_prose_pairs_under_the_existing_quote_regex():
    """The downstream verifier is unchanged, so its regex must see structured output."""
    from backend.bot import QUOTE_WITH_CITE_RE
    ans = _answer(
        zone1_interpretation="Gill's material on the garden follows.",
        phrases=[
            _phrase(gill_quote="the garden of Eden was a real place"),
            _phrase(framing="Gill makes a related point:",
                    gill_quote="a delightful and pleasant place",
                    sentence_id="[GENESIS_02_08_S02]"),
        ])
    prose, cites, _ = sa.render(ans, BOOKS)
    pairs = QUOTE_WITH_CITE_RE.findall(prose)
    assert [sid for _, sid in pairs] == ["GENESIS_02_08_S01", "GENESIS_02_08_S02"]
    assert pairs[0][0] == "the garden of Eden was a real place"
    assert cites == ["[GENESIS_02_08_S01]", "[GENESIS_02_08_S02]"]


def test_model_supplied_quote_marks_are_not_doubled():
    ans = _answer(phrases=[_phrase(gill_quote='"the garden of Eden was a real place"')])
    prose, _, _ = sa.render(ans, BOOKS)
    assert '""' not in prose
    from backend.bot import QUOTE_WITH_CITE_RE
    assert QUOTE_WITH_CITE_RE.findall(prose)


def test_nothing_is_rendered_after_the_final_quote():
    """The BOOKEND rule, structurally: there is no slot for a closing synthesis."""
    ans = _answer(phrases=[_phrase(gill_quote="a delightful and pleasant place")])
    prose, _, _ = sa.render(ans, BOOKS)
    assert prose.rstrip().endswith("[GENESIS_02_08_S01]")


def test_payload_carries_zone3_for_the_trace():
    ans = _answer(phrases=[_phrase(gill_quote="q")], zone3_notes="a leak")
    payload = sa.to_payload(ans)
    assert payload["zone3_notes"] == "a leak"
    assert payload["phrases"][0]["sentence_id"] == "[GENESIS_02_08_S01]"
    assert payload["refusal"] is None


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in fns:
        try:
            fn()
            print(f"  ok   {name}")
        except Exception as e:
            print(f"  FAIL {name}: {type(e).__name__}: {e}")
            failed.append(name)
    print("")
    print(f"{len(fns) - len(failed)}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
