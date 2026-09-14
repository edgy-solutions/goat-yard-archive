"""Config-v2 Hebrew layer — wires the four built-but-standalone Hebrew gates onto the typed notes (NEXT_CONFIG
Hebrew section). It ATTACHES a per-note `hebrew_verdict` and never mutates the note text: the deterministic
nikud strip is recorded as a proposed `stripped_text` beside the printed text, not applied in place — so this
pass can run in the reproduction born-test without confounding the drift measurement, and the correction lives
as an editorial standoff (the printed form is kept, the reading sits beside it).

The gates need the note's image crop; the whole-strip typed seam yields text, not per-note crops, so the
detector's note-regions (note_region) are aligned to the notes BY POSITION — region[k] <-> note[k] only when
the counts agree. On a count mismatch the crop gates ABSTAIN for the page (flagged), never crop blind. Two
gates are text-only and always run: script-consistency and (upstream) the reference check.

  script_gate   — Greek codepoints in a Hebrew span (Septuagint transcribed as Hebrew) => wrong-script HARD
                  flag; pure-Hebrew output whose note cites a Greek source => greek-suspect.
  locate_hebrew — count-located Hebrew span box on the note-line crop (abstains, never guesses).
  glyph_count   — connected-component glyph estimate vs letter count on the (located) span crop; gross
                  out-of-band => a dropped/added letter.
  nikud_gate    — per-span pointed-crop detector; proposes a nikud-stripped reading ONLY when the crop is
                  confidently unpointed (model added the points), else keeps.
A note is FLAGGED for the gemma dual-witness when script != ok OR the glyph tripwire fires."""
import re
import note_region as NR
import word_box_align as WBA
import glyph_count_tripwire as GCT
import nikud_gate as NG
import script_gate as SG

_HEB = re.compile(r"[֐-׿]")


def _has_hebrew(text):
    return bool(_HEB.search(text or ""))


def _hebrew_run_text(text):
    """The contiguous Hebrew run's surface text (for the glyph-count letter tally), via the localizer's own
    tokenizer so the run definition matches the box selection. '' if no clean contiguous run."""
    toks = WBA.tokenize(text)
    run = WBA._hebrew_run(toks)
    if not run or run == "split":
        return ""
    lo, hi = run
    return " ".join(w for _s, w in toks[lo:hi + 1])


def apply(strip, notes, profile=None):
    """Attach `hebrew_verdict` to every Hebrew-bearing note. Returns (notes, summary). Non-destructive."""
    heb_idx = [i for i, n in enumerate(notes) if _has_hebrew(n.get("text"))]
    if not heb_idx:
        return notes, {"hebrew_notes": 0, "flagged": 0, "aligned": None}
    regions, _meta = NR.propose_regions(strip)
    aligned = len(regions) == len(notes)
    flagged = 0
    for i in heb_idx:
        n = notes[i]
        text = n.get("text") or ""
        v = {"script": SG.gate(text, text)[0]}            # text-only, always available
        if aligned:
            try:
                line_crop = strip.crop(tuple(regions[i]["strip_box"]))
                box, st = WBA.locate_hebrew(line_crop, text)
                if box:
                    span_crop = line_crop.crop(box)
                    heb_text = _hebrew_run_text(text)
                    gl_flag, g, l = GCT.tripwire(span_crop, heb_text)
                    stripped, nikud_v, dens = NG.gated_strip(text, span_crop)
                    v.update({"span_box": list(box), "glyph_flag": bool(gl_flag), "glyphs": g, "letters": l,
                              "nikud": nikud_v, "nikud_density": round(dens, 3),
                              "stripped_text": stripped if stripped != text else None})
                else:
                    v["locate"] = st                      # localizer abstained (count mismatch etc.)
            except Exception as e:
                v["crop_error"] = str(e)[:80]
        else:
            v["align"] = "note-count-mismatch"            # crop gates abstain for the page
        v["flag"] = (v["script"] != "ok") or bool(v.get("glyph_flag"))
        v["escalate_gemma"] = v["flag"]                   # the dual-witness intake gate
        n["hebrew_verdict"] = v
        flagged += int(v["flag"])
    return notes, {"hebrew_notes": len(heb_idx), "flagged": flagged, "aligned": aligned,
                   "n_regions": len(regions), "n_notes": len(notes)}
