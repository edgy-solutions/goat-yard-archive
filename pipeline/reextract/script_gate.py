"""Script gate (config-v2 Hebrew layer) — the Greek-as-Hebrew catcher. Two witnesses, both deterministic:

  OUTPUT-SIDE   the codepoints betray the error directly. A span labelled Hebrew that carries Greek letters
                (or mixes scripts) is flagged without a model — Unicode ranges don't lie. This catches the
                reader that transliterated Greek into Hebrew-shaped output, or left the Greek in.
  CONTEXT-SIDE  the note's Latin cites a GREEK source (Sept./LXX/Aquila/Symmachus/Theodotion/Ο'). When Gill
                is quoting the Septuagint, the quoted word is GREEK, so a pure-Hebrew reading of that span is
                SUSPECT — the reader may have forced Greek glyphs into the nearest Hebrew letters. This is
                the measured 33-note "hard Greek-hint" signal. Not proof (Gill also gives the Hebrew beside
                the Greek), so it FLAGS to the second reader / a script-aware re-read, never rewrites.

The output-side is a hard flag (wrong script shipped); the context-side is a suspicion that routes. Both are
deterministic and cheap — run before the model witnesses, so a Greek span never enters the Hebrew ladder as
if it were Hebrew. A flag routes to the second reader, never a correction.

SPAN ISOLATION (integration caveat, measured on the frozen run): run `gate` on the ISOLATED Hebrew field
(the reader's claimed Hebrew reading) with the Latin passed as `latin_context` — NOT on the whole mixed
note. Gill's notes routinely carry Hebrew AND a Septuagint Greek quotation in one string; over the frozen
run's un-segmented note text the output-side flags 34 notes for Greek codepoints, most of them legitimately
bilingual, not errors. The context-side found 20 Greek-source cites there. Once v2 emits the Hebrew span
separately from its Latin, the output-side becomes exact (Greek in the HEBREW field is unambiguously wrong)."""
import re

HEB = r"֐-׿יִ-ﭏ"
GRK = r"Ͱ-Ͽἀ-῿"
_HEB_RE = re.compile(f"[{HEB}]")
_GRK_RE = re.compile(f"[{GRK}]")

# Gill's citations of the Greek versions — abbreviations and full forms, plus the Seventy siglum Ο'.
# trailing (?![A-Za-z]) not \b — abbreviations end in '.', where \b would fail (Aq., Sym., Theod.)
_GREEK_SOURCE = re.compile(
    r"\b(?:Sept(?:uagint)?|LXX|Aquila|Aq\.|Symmachus|Sym\.|Theodotion|Theod\.|"
    r"Greek\s+version)(?![A-Za-z])|Ο['ʹ΄']|οἱ\s+Ο", re.IGNORECASE)

def has_hebrew(text):
    return bool(_HEB_RE.search(text or ""))

def has_greek(text):
    return bool(_GRK_RE.search(text or ""))

def cites_greek_source(latin_context):
    """True if the note's non-Hebrew text cites a Greek version (Septuagint/Aquila/…)."""
    return bool(_GREEK_SOURCE.search(latin_context or ""))

def gate(hebrew_output, latin_context=""):
    """Classify a span. Returns (verdict, reason):
      'wrong-script'  output carries Greek (or Greek-only) where Hebrew was expected — HARD flag.
      'greek-suspect' output is pure Hebrew but the note cites a Greek source — routes to a script-aware read.
      'ok'            Hebrew output, no Greek signal.
    Empty/non-Hebrew output is 'ok' here (the reference/no-hebrew stages own that)."""
    heb, grk = has_hebrew(hebrew_output), has_greek(hebrew_output)
    if grk:
        return ("wrong-script", "greek-codepoints-in-hebrew-span")
    if heb and cites_greek_source(latin_context):
        return ("greek-suspect", "note-cites-greek-source")
    return ("ok", "")
