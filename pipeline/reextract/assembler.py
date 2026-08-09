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

def _hebrew(ch): return "֐" <= ch <= "׿"

def load_profile(path):
    import yaml
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))

# --- marker handling: the model emits a leading letter (a/[^a]/^a^, maybe with , . )). It is
#     DISCARDABLE — position assigns the canonical marker. We keep it only for diagnostics. ---
_MARKER = re.compile(r"^\s*(?:\[\^)?([a-zA-Z])(?:\^?\])?[.,)]?\s+(.*\S)\s*$")
def strip_marker(line):
    m = _MARKER.match(line)
    return (m.group(1).lower(), m.group(2)) if m else (None, line.strip())

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
    for line in raw_lines:
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
            notes[-1]["text"] = (prev[:-1] + text) if prev.endswith("-") else (prev + " " + text)
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

# --- stitch assertion: TWO signals, whitelist-gated. Returns [] when clean; violations => STOP ---
_TERMINAL = (".", "!", "?", ")", "]", "’", '"', ";")
def _ends_terminal(t): return t.rstrip().endswith(_TERMINAL)
def _ends_hebrew(t):
    t = t.rstrip(); return bool(t) and _hebrew(t[-1])
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
