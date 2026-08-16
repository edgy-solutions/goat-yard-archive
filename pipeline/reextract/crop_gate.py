"""CROP GATE — the fail-loud net against apparatus FABRICATION on blank crops.

Discovered on p86 (front matter: the Latin tomb-inscription "MEMOIR OF DR. GILL", zero
footnotes). presplit misdetected a rule and produced a BLANK crop; handed blank pixels, the
VLM confabulated 18 Genesis footnotes. The stitch guard caught it only by luck (the
hallucination repeated 3-10 as 11-18) — a NON-repeating hallucination would have shipped as a
clean-looking apparatus. Corpus scan: exactly 1/958 pages shows this signature, so it's a rare
front-matter edge, but a silent-fabrication edge, and the guard is cheap.

"A blank crop cannot contain an apparatus" is a DETERMINISTIC property of the pixels
(deterministic-property-not-a-model), so CODE decides it, the model is never the last word on
whether it 'read' something off blank paper. And it's FAIL-LOUD, not silent:

  dark >= floor                -> 'ok'                  (trust the crop; the model read real ink)
  dark <  floor AND notes>0    -> 'fabrication_suspect' (blank crop but model returned notes:
                                    DROP the notes, FLAG — do NOT emit hallucinated apparatus)
  dark <  floor AND notes==0   -> 'no_apparatus'        (blank crop, model agrees: correctly empty)

Note the middle verdict does NOT silently become 'no_apparatus': a blank crop can also mean
presplit cropped the WRONG region on a page that DOES have apparatus elsewhere. Flagging (not
emptying) keeps that case lossless — it routes to review/re-crop instead of dropping real notes.

floor is book-scoped (book_profile transcription.crop_content_floor); default 0.01 cleanly
separates p86 (0.000) from the sparsest real note-bearing crop in vol1 (~0.025).
"""
import numpy as np

DEFAULT_FLOOR = 0.01

def crop_darkness(strip):
    """Fraction of ink pixels (<128 on L) in the crop the VLM is about to read. None -> 0.0 (blank)."""
    if strip is None:
        return 0.0
    a = np.asarray(strip.convert("L"))
    return float((a < 128).mean())

def check(strip, n_notes, floor=DEFAULT_FLOOR):
    """(verdict, dark). verdict in {'ok','fabrication_suspect','no_apparatus'}. See module doc."""
    dark = crop_darkness(strip)
    if dark >= floor:
        return "ok", dark
    return ("fabrication_suspect" if (n_notes or 0) > 0 else "no_apparatus"), dark

def gate_notes(strip, notes, floor=DEFAULT_FLOOR):
    """Apply the gate to an extracted-notes list. Returns (kept_notes, status, flag_or_None).
    On a fabrication_suspect the notes are DROPPED and a flag record is returned for the queue."""
    verdict, dark = check(strip, len(notes or []), floor)
    if verdict == "fabrication_suspect":
        return [], "FABRICATION_SUSPECT", {
            "reason": "blank crop, model returned notes — apparatus fabricated or presplit mis-cropped",
            "cropdark": round(dark, 4), "n_dropped": len(notes or [])}
    if verdict == "no_apparatus":
        return [], "no_apparatus", None
    return notes, "ok", None

if __name__ == "__main__":
    import sys
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    from PIL import Image
    blank = Image.new("L", (400, 300), 255)                     # pure white crop (p86-like)
    inked = Image.new("L", (400, 300), 255)
    import numpy as _np
    arr = _np.asarray(inked).copy(); arr[50:120, 20:380] = 0    # a band of ink (~5% dark)
    inked = Image.fromarray(arr)
    print("blank+18notes ->", check(blank, 18), "(want fabrication_suspect)")
    print("blank+0notes  ->", check(blank, 0),  "(want no_apparatus)")
    print("inked+18notes ->", check(inked, 18), "(want ok)")
    kept, st, flag = gate_notes(blank, [{"marker": f"[^{i}]"} for i in range(1, 19)])
    print("gate p86-like:", st, "| kept", len(kept), "| flag:", flag)
