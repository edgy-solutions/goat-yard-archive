"""Span isolation (config-v2 Hebrew layer) — the connective tissue the three gates converge on. A Gill note
is one mixed string: Hebrew reading + Latin gloss + sometimes a Greek quotation (`תנשו אל אשה μη προσελθητε
Sept. to a woman, Ainsworth.`). The gates need the HEBREW alone, not the mixed note:
  - the script gate over-flags on the mixed note (34 legitimately-bilingual notes on the frozen run) but is
    exact on the isolated Hebrew field (Greek codepoints there are unambiguously wrong);
  - the reference-hypothesis stage matches the Hebrew reading against its passage, not the Latin;
  - the nikud gate and glyph-count tripwire need a tight crop of the Hebrew (bleed inflates both).

TWO LEVELS, and this module builds only the first:
  TEXT LEVEL (here, deterministic): segment the note by Unicode script into ordered runs; isolate each
    Hebrew run with the note's non-Hebrew text as its `latin_context`. Feeds the script gate + reference
    stage TODAY, no box required.
  PIXEL LEVEL (NOT here): the tight bounding `box` of the Hebrew in the strip. This is the cross-modal
    correspondence problem — memory's standing rule is to produce positions AT EXTRACTION TIME with spatial
    invariants and fail-loud gaps, NEVER by post-hoc alignment of two transcriptions. So `box` is a typed
    field, `None` until the v2 extractor emits it; the nikud gate and glyph-count tripwire consume a span
    ONLY when `box is not None` (no box → those two abstain, they don't guess a crop)."""
import re

_HEB = re.compile(r"[֐-׿יִ-ﭏ]")
_GRK = re.compile(r"[Ͱ-Ͽἀ-῿]")

def _script_of(ch):
    if _HEB.match(ch): return "hebrew"
    if _GRK.match(ch): return "greek"
    return "latin"                                     # everything else (Latin letters, digits, punct, space)

def segment(note_text):
    """Ordered runs of the note typed by script. Returns [{script, text, start, end}]. Whitespace attaches
    to the preceding run so run boundaries fall on real script changes, not spaces."""
    if not note_text:
        return []
    runs = []
    for i, ch in enumerate(note_text):
        s = _script_of(ch)
        if ch.isspace() and runs:                      # keep spaces with the current run
            runs[-1]["text"] += ch; runs[-1]["end"] = i + 1; continue
        if runs and runs[-1]["script"] == s:
            runs[-1]["text"] += ch; runs[-1]["end"] = i + 1
        else:
            runs.append({"script": s, "text": ch, "start": i, "end": i + 1})
    for r in runs:
        r["text"] = r["text"].strip()
    return [r for r in runs if r["text"]]

def hebrew_spans(note_text):
    """Isolate each Hebrew run as a span with its context. Returns [{hebrew, latin_context, greek_present,
    start, end, box}]. `latin_context` is the note's non-Hebrew text (the gloss/citation the reading
    belongs to); `greek_present` flags that the note also carries Greek (a script-gate hint). `box` is None
    — pixel isolation is the extractor's job (see module docstring)."""
    runs = segment(note_text)
    context = " ".join(r["text"] for r in runs if r["script"] == "latin").strip()
    greek = any(r["script"] == "greek" for r in runs)
    out = []
    for r in runs:
        if r["script"] == "hebrew":
            out.append({"hebrew": r["text"], "latin_context": context, "greek_present": greek,
                        "start": r["start"], "end": r["end"], "box": None})
    return out
