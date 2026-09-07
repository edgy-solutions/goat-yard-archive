"""Reference-hypothesis stage (config-v2 Hebrew layer) — the reference window applied to the Hebrew layer.
For each Hebrew span, the ANCHORED verse (from the alignment verse_ref) plus the verses the note CITES are
the reference. The span is classified into THREE outcomes — never a direct correction, only a hypothesis:

  matches-passage       every content word of the reading is in the passage → the reading is confirmed as
                        quotation; the passage text is handed to the second reader as an INFORMED PRIOR.
  reference-mismatch    the reading is biblical (matches some OT verse) but NOT this passage — the real
                        flag. Same-length substitutions the glyph-count tripwire can't see (סנה→היה) land
                        here, because the narrow question — "is it in THIS verse" — is the only one that
                        rejects a high-frequency word substituted for the right one.
  no-reference          extra-biblical (Kimchi's roots, Buxtorf's forms, Targum paraphrase) — not in any
                        passage BY CONSTRUCTION. NOT a mismatch: pixels-only, the second reader carries it.

The passage is SCOPED (anchored verse + cited cross-refs), never whole-Bible — presence is not correctness,
and the scope of the check must match the scope of the claim (the p596 / frontier-parroting / whole-Bible
lesson, three ways). A reference-mismatch is a HYPOTHESIS for the vision witness to re-read against, never a
correction; the FABRICATION CHECK guards the injection — if the reader's output is just the injected verse
verbatim, it parroted the prior and the span is flagged, not resolved. Complementary to the glyph-count
tripwire (length shortfalls) — each catches a class the other misses; run both."""
import re

def _cons(w):
    return re.sub(r"[^א-תךםןףץ]", "", w or "")

def _words(text):
    return [w for w in re.findall(r"[֐-׿]+", text or "") if len(_cons(w)) >= 2]

_FINSET = set("ךםןףץ")
def _is_garbage(text):
    for run in re.findall(r"[א-תךםןףץ]+", text or ""):
        for i, ch in enumerate(run):
            if ch in _FINSET and i != len(run) - 1:
                return True
    return False

def classify(hebrew_text, passage_words, is_biblical, in_passage=None, min_len=2):
    """Three-outcome classification of a Hebrew span against its scoped passage.
      passage_words : set of consonantal word-forms in the anchored verse + cited cross-refs
      is_biblical   : callable(text) -> bool, does the text match SOME OT verse (whole-Tanakh index)
      in_passage    : callable(word, passage_words) -> bool (prefix/matres aware); default = plain membership
    Returns (outcome, hypothesis) where hypothesis is the passage as an informed prior (or None)."""
    if in_passage is None:
        in_passage = lambda w, pw: _cons(w) in pw
    ws = [w for w in _words(hebrew_text) if len(_cons(w)) >= min_len]
    if not ws:
        return "no-hebrew", None
    if _is_garbage(hebrew_text):
        return "reference-mismatch", None                 # scrambled OCR is a real signal
    content = [w for w in ws if len(_cons(w)) >= 3] or ws
    if passage_words and all(in_passage(w, passage_words) for w in content):
        return "matches-passage", " ".join(sorted(passage_words))  # confirmed quotation; prior for the reader
    if is_biblical(hebrew_text):
        return "reference-mismatch", None                 # biblical but not THIS passage — the flag
    return "no-reference", None                            # extra-biblical -> pixels-only, second reader

def _norm(s):
    return re.sub(r"\s+", "", s or "")

def is_parroted(reader_output, injected_hypothesis):
    """Fabrication check for the reader re-read: True if the reader just echoed the injected hypothesis
    (verbatim, whitespace-insensitive) — it parroted the prior instead of reading the pixels, so the span
    is FLAGGED, not resolved. The p109/p593 rule: a hypothesis is a witness, never the answer."""
    return bool(injected_hypothesis) and _norm(reader_output) == _norm(injected_hypothesis)
