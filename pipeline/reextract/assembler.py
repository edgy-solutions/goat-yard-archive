"""Assembler — the deterministic core of the re-extraction pipeline. Owns every property a model
may NOT own (markers-by-position, furniture removal, letter-sequence scope, output format). Driven
entirely by book_profile.yaml; contains NO book-specific facts. Born with test_assembler.py.

Per-page job: raw transcribed footnote lines (model's letters unreliable) -> canonical notes with
[^N] markers assigned BY POSITION, page-furniture stripped, + a fail-loud two-signal stitch
assertion (the measured reality is 0 cross-page text-splits in Gill vol1; the assertion keeps that
true by STOPPING if a real split ever appears — fail-loud makes building-nothing safe).
"""
import re
from pathlib import Path

# non-Latin scripts in the apparatus (fossil: normalize_markdown.repair_non_latin_footnotes covered
# Hebrew+Greek+Syriac — LLMs corrupt all non-Latin, and a note ENDING in any of them is complete).
def _non_latin(ch):
    return ("֐" <= ch <= "׿" or   # Hebrew
            "Ͱ" <= ch <= "Ͽ" or   # Greek
            "܀" <= ch <= "ݏ" or   # Syriac
            "؀" <= ch <= "ۿ")     # Arabic
_hebrew = _non_latin   # back-compat alias

# word-break dashes (fossil: get_md.py normalizes "various dash characters to standard hyphen"
# BEFORE hyphen processing). em/en dash are punctuation, NOT word-breaks — excluded on purpose.
_WORDBREAK_DASH = ("-", "­", "‑", "‒")   # hyphen-minus, soft, non-breaking, figure

def load_profile(path):
    import yaml
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))

# --- marker handling: the model emits a leading letter (a/[^a]/^a^, maybe with , . )). It is
#     DISCARDABLE — position assigns the canonical marker. We keep it only for diagnostics. ---
_MARKER = re.compile(r"^\s*(?:\[\^)?([a-zA-Z])(?:\^?\])?[.,)]?\s+(.*\S)\s*$")
# superscript/symbol note markers (FOSSIL zoo): ¹²³⁰⁴-⁹, superscript-latin ᵃ-ᶻ, and * † ‡ §
_SUP = "¹²³⁰⁴⁵⁶⁷⁸⁹ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ*†‡§"
_LEADSUP = re.compile(r"^\s*[" + _SUP + r"]\s*(.*\S)\s*$")
# a mid-line marker that STARTS a new note (superscript/symbol/bracket/caret); used to split merged lines
_NOTE_MARKER = re.compile(r"\[\^[a-z]\]|\^\[[a-z]\]|\^[a-z]\^|[" + _SUP + r"]")

def strip_marker(line):
    m = _MARKER.match(line)
    if m: return m.group(1).lower(), m.group(2)
    m2 = _LEADSUP.match(line)                 # superscript/symbol marker -> letter unknown ("?"), text kept
    if m2: return "?", m2.group(1)
    return None, line.strip()

def split_note_line(line):
    """Split a line carrying MULTIPLE note markers into one segment per note (p343/p757: the model
    merged `² Nunc, Drusius. ᵃ Euterpe...` onto one line). Letter-marked notes have no _NOTE_MARKER
    hit and pass through unchanged, so this never touches the clean letter-marker pages."""
    pos = [m.start() for m in _NOTE_MARKER.finditer(line)]
    if len(pos) <= 1: return [line]
    segs = []
    pre = line[:pos[0]].strip()               # text before the first marker = continuation of prior note
    for i, p in enumerate(pos):
        end = pos[i + 1] if i + 1 < len(pos) else len(line)
        s = line[p:end].strip()
        if s: segs.append(s)
    if pre and segs: segs[0] = pre + " " + segs[0]
    return segs

# body/definition split — a def line is a LINE-LEADING marker in ANY zoo format ([^a]: | ^[a] |
# ^a^ | ^a text). Recognizing only bracket defs leaks caret-format def lines into "body" and
# double-counts anchors (surfaced by p150 in the truth-set run).
_DEF_LINE = re.compile(r"^\s*(?:\[\^[a-z]\]:|\^\[[a-z]\]|\^[a-z]\^?)(?=\s|:)")
def split_body_defs(md):
    lines = md.splitlines()
    for i, ln in enumerate(lines):
        if _DEF_LINE.match(ln):
            return "\n".join(lines[:i]), "\n".join(lines[i:])
    return md, ""

def is_furniture(line, profile):
    f = profile["furniture"]; s = line.strip()
    if not s: return True
    if any(re.match(rx, s) for rx in f.get("running_head_regexes", [])): return True
    if re.match(f["signature_mark_regex"], s): return True
    if re.match(f["page_number_regex"], s): return True
    return False

def canonicalize_page(raw_lines, profile):
    """raw_lines -> {'notes':[{marker,text,model_letter}], 'dropped_furniture':[...]}.
    Markers assigned [^1..N] BY POSITION; the model's letters are recorded, never trusted."""
    notes, dropped = [], []
    lines = [seg for line in raw_lines for seg in split_note_line(line)]   # split merged multi-marker lines
    for line in lines:
        if not line.strip(): continue
        if is_furniture(line, profile): dropped.append(line.strip()); continue
        letter, text = strip_marker(line)
        if not text: dropped.append(line.strip()); continue
        if letter is None and notes:
            # a marker-less line MID-page is an intra-strip line-WRAP of the previous note, not a
            # new note -> merge (hyphen-join if the prev line broke a word: "Va-" + "tablus" ->
            # "Vatablus"). A marker-less FIRST line is left as its own note so the stitch guard
            # sees the split-IN signal.
            prev = notes[-1]["text"]
            notes[-1]["text"] = (prev[:-1] + text) if prev.endswith(_WORDBREAK_DASH) else (prev + " " + text)
            continue
        notes.append({"model_letter": letter, "text": text})
    for i, n in enumerate(notes, 1):
        n["marker"] = f"[^{i}]"
    return {"notes": notes, "dropped_furniture": dropped}

# --- letter-sequence utilities (marker-scope: per-column restart; 1766 j-skip; u/v interchange) ---
def effective_skips(profile):
    lay = profile["layout"]
    sk = set(lay.get("marker_skips", []))
    if lay.get("uv_interchange"):
        sk.add("v")                      # observed: run goes ...u -> w (v skipped); see p100 q-u|w-z
    return sk

def advance_letter(ch, skips):
    nxt = chr(ord(ch) + 1)
    while nxt in skips: nxt = chr(ord(nxt) + 1)
    return nxt

def letter_run(start, count, profile):
    skips = effective_skips(profile); out = [start]; cur = start
    for _ in range(count - 1):
        cur = advance_letter(cur, skips); out.append(cur)
    return out

def _fill_run(anchors, profile):
    """The printer run from anchors[0] to anchors[-1] (j/v skipped) — fills the letters between."""
    skips = effective_skips(profile); out = [anchors[0]]; cur = anchors[0]
    while cur != anchors[-1] and len(out) < 60:
        cur = advance_letter(cur, skips); out.append(cur)
    return out

# --- stitch assertion: TWO signals, whitelist-gated. Returns [] when clean; violations => STOP ---
_TERMINAL = (".", "!", "?", ")", "]", "’", '"', ";")
def _ends_terminal(t): return t.rstrip().endswith(_TERMINAL)
def _ends_non_latin(t):
    t = t.rstrip(); return bool(t) and _non_latin(t[-1])
_ends_hebrew = _ends_non_latin   # whitelist key stays `hebrew_final`; now covers Greek/Syriac/Arabic too
def _citation_tail(t):
    t = t.rstrip().rstrip(".,")
    if re.search(r"\b(l|c|p|sect|fol|vol|ib|cap|v|tom|lib)\.?\s*[0-9ivxlcd]+$", t, re.I): return True
    if re.search(r"[0-9]$", t): return True                          # ends in a number (citation/signature)
    if re.search(r"[A-ZÀ-Þ][a-zß-ÿ]+$", t) and ("," in t or "&" in t):
        return True                                                  # authority-list tail: "...& Drusius"
    return False
def _opens_lower_latin(t):
    t = t.lstrip(); return bool(t) and t[0].isalpha() and t[0].islower() and ord(t[0]) < 0x400
def _latin_gloss(t):
    return _opens_lower_latin(t) and (("&" in t) or bool(re.search(r",\s*[A-ZÀ-Þ][a-z]+", t))
                                      or "version" in t.lower())

# --- body-anchor matching -------------------------------------------------------------------
# Link re-extracted NOTES (reading order) to the body's inline anchors. The letters on BOTH sides
# are unreliable (p100 re-lettered q-u→a-e; p571 right column re-lettered n-t→a-g → duplicate
# c/f/g), so POSITION wins when counts agree (same law as note markers). The glyph is a ZOO
# (FOSSIL #A): [^a] | ^[a] | ^a^ | ^a (caret-prefix). Fail-loud (Chris): a note with no confident
# anchor is FLAGGED unanchored, never guessed — a mis-anchored citation is worse than an orphaned one.
_ANCHOR_RE = re.compile(r"\[\^([a-z])\]|\^\[([a-z])\]|\^([a-z])\^|\^([a-z])")
_IBID_RE = re.compile(r"^\s*(ib|ibid|idem|id)\.?\b", re.I)

def detect_body_anchors(body_text):
    """Ordered list of inline-anchor letters in the body, covering the marker zoo (non-overlapping,
    most-specific alternative first)."""
    out = []
    for m in _ANCHOR_RE.finditer(body_text):
        out.append(next(g for g in m.groups() if g))
    return out

def _ibid_count(notes):
    return sum(1 for n in notes if _IBID_RE.match(n["text"]))

def match_notes_to_anchors(notes, body_text, profile, scope_start="a"):
    """Returns {links, unanchored, status, n_anchors, n_notes}. status OK only when every note is
    confidently anchored. FOSSIL #B: ibid refs may merge, so a count diff within the ibid count is
    tolerated for position-matching."""
    anchors = detect_body_anchors(body_text)
    na, nn = len(anchors), len(notes)
    ibid = _ibid_count(notes) if profile.get("layout", {}).get("ibid_merge") else 0
    links, unanchored = [], []
    if na == nn or abs(na - nn) <= ibid:
        # counts agree -> POSITION wins (dissolves p571's duplicate-letter collisions)
        for i in range(nn):
            if i < na:
                links.append({"marker": f"[^{i+1}]", "text": notes[i]["text"], "anchor_letter": anchors[i]})
            else:
                unanchored.append({"marker": f"[^{i+1}]", "text": notes[i]["text"], "reason": "ibid_overflow"})
        status = "OK" if not unanchored else "FLAGGED"
    else:
        # counts disagree. Derive the scope from the DETECTED anchors, not a hardcoded 'a' (that
        # false-flagged p97, whose anchors start at 'o'). ONLY pinpoint gaps when the anchors form a
        # clean strictly-increasing run whose filled span EXACTLY covers the note count — then the
        # missing letters are the notes that lost their body anchor. Otherwise the page can't be
        # reconciled without scope info: flag the whole page for review, no false per-note guesses.
        increasing = all(b > a for a, b in zip(anchors, anchors[1:])) if len(anchors) > 1 else bool(anchors)
        filled = _fill_run(anchors, profile) if anchors and increasing else None
        if filled and len(filled) == nn:
            aset = set(anchors)
            for i in range(nn):
                L = filled[i]
                if L in aset:
                    links.append({"marker": f"[^{i+1}]", "text": notes[i]["text"], "anchor_letter": L})
                else:
                    unanchored.append({"marker": f"[^{i+1}]", "text": notes[i]["text"],
                                       "reason": "anchor_missing_in_body", "expected_letter": L})
            return {"links": links, "unanchored": unanchored, "status": "FLAGGED", "n_anchors": na,
                    "n_notes": nn, "anchor_letters": anchors, "gap_letters": [u["expected_letter"] for u in unanchored]}
        # cannot reconcile (partial loss + unknown scope, e.g. p97 o,p,q vs 14 notes) -> page flag
        unanchored = [{"marker": f"[^{i+1}]", "text": notes[i]["text"], "reason": "page_reconciliation_failed"}
                      for i in range(nn)]
        return {"links": [], "unanchored": unanchored, "status": "FLAGGED", "n_anchors": na,
                "n_notes": nn, "anchor_letters": anchors, "gap_letters": []}
    return {"links": links, "unanchored": unanchored, "status": status, "n_anchors": na, "n_notes": nn}

def assert_no_text_split(notes, profile):
    """Fail-loud guard. Whitelist = the 6 artifact classes measured in measure_continuations.py
    (0 real splits / 871 vol1 pages). A signal NOT explained by the whitelist => a genuine split
    (or a new book's reality) => caller STOPS."""
    wl = profile.get("stitch_whitelist", {}); viol = []
    if not notes: return viol
    first, last = notes[0]["text"], notes[-1]["text"]
    if _opens_lower_latin(first) and not (wl.get("latin_gloss_lowercase_open") and _latin_gloss(first)):
        viol.append({"signal": "split_in", "text": first[:90]})
    if not _ends_terminal(last):
        explained = (wl.get("hebrew_final") and _ends_hebrew(last)) or \
                    (wl.get("citation_final_no_period") and _citation_tail(last))
        if not explained:
            viol.append({"signal": "split_out", "text": last[-90:]})
    return viol
