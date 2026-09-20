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
import re, json
from pathlib import Path
import numpy as np
import note_region as NR
import note_start_detect as NS
import marker_harvest as MH
import sequence_gate as SEQ
import word_box_align as WBA
import glyph_count_tripwire as GCT
import nikud_gate as NG
import script_gate as SG
import reference_hypothesis as RH

_HEB = re.compile(r"[֐-׿]")
# Decision 4 (Chris 2026-09-14): the reference-hypothesis stage uses the SAME Bible text the reader's reference
# window already injects — the per-page `{page}_metadata.json` `hebrew_text` (verse -> pointed WLC verse). One
# source, so the hypothesis and the reader read from one Bible; pinned + hashed via REFERENCE_SOURCE below.
REFERENCE_SOURCE = {"kind": "page_metadata.hebrew_text", "file": "page{page}_image1_metadata.json"}


def _passage_words(page, img_dir):
    """Consonantal word-forms of the page's anchored verse(s), from the reference window's own source (the
    page metadata's hebrew_text). Returns a set, or None if the metadata is absent (reference stage abstains)."""
    if page is None or img_dir is None:
        return None
    p = Path(img_dir) / f"page{page}_image1_metadata.json"
    if not p.exists():
        return None
    ht = (json.loads(p.read_text(encoding="utf-8")) or {}).get("hebrew_text") or {}
    words = set()
    for v in ht.values():
        for w in RH._words(v):
            words.add(RH._cons(w))
    return words


def _marker_regions(strip, regions):
    """Decision 2 (Chris 2026-09-14): the note-start detector is retired as a counter — it over-counts (body
    lines fire as note-starts). Filter its proposed regions to those whose first line carries a real RAISED
    MARKER glyph (marker_harvest._marker_box), dropping the body-line false regions, so alignment keys on v2's
    validated notes rather than the detector's inflated count. Returns the marker-bearing regions in order."""
    arr = np.asarray(strip.convert("L"))
    keep = []
    for reg in regions:
        x0, y0, x1, y1 = reg["strip_box"]
        sub = NS.strip_vrules(arr[y0:y1, x0:x1] < NS.INK)
        lines = NS.text_lines(sub)
        if not lines:
            continue
        ly0, ly1 = lines[0]
        if MH._marker_box(sub[ly0:ly1]) is not None:
            keep.append(reg)
    return keep


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


def _script_verdict(text):
    """Decision 3 (Chris 2026-09-14): scope the script check to the Hebrew SPAN, not the whole note. Gill
    routinely cites Greek AND Hebrew in one note (e.g. `וְאֶת הַפֶּלֶט … τοτο απαξ, Symmachus`); the old
    whole-note check flagged any Greek codepoint as wrong-script — a false positive. Here wrong-script fires
    only when Greek intrudes INTO the Hebrew span (Greek transcribed where Hebrew was printed); a separate
    Greek citation elsewhere in the note is fine. Returns a script_gate verdict string.
      wrong-script   Greek sits inside the contiguous Hebrew run (the span itself is script-mixed with Greek).
      greek-suspect  clean Hebrew span, but the note cites a Greek source (routes to a script-aware read).
      ok             clean Hebrew span, no Greek-source signal.
      no-hebrew      no Hebrew tokens (the reference/no-hebrew stages own that; not a script flag here).
    Full "output-script vs crop-script at the span box" (the image side) waits on the located span box."""
    toks = WBA.tokenize(text)
    heb_idx = [i for i, (s, _) in enumerate(toks) if s == "hebrew"]
    if not heb_idx:
        return "no-hebrew"
    lo, hi = heb_idx[0], heb_idx[-1]
    if any(toks[i][0] == "greek" for i in range(lo, hi + 1)):   # Greek INSIDE the Hebrew span
        return "wrong-script"
    return SG.gate(_hebrew_run_text(text) or " ".join(toks[i][1] for i in heb_idx), text)[0]


def apply(strip, notes, profile=None, page=None, img_dir=None):
    """Attach `hebrew_verdict` to every Hebrew-bearing note. Returns (notes, summary). Non-destructive.
    When `page`+`img_dir` are given, the reference-hypothesis stage (decision 4) runs text-only against the
    page's anchored-verse Hebrew (the reference window's own source)."""
    heb_idx = [i for i, n in enumerate(notes) if _has_hebrew(n.get("text"))]
    if not heb_idx:
        return notes, {"hebrew_notes": 0, "flagged": 0, "aligned": None}
    passage = _passage_words(page, img_dir)               # decision 4 reference window; None -> stage abstains
    regions, _meta = NR.propose_regions(strip)
    mregions = _marker_regions(strip, regions)            # decision 2: detector as boxes, marker-filtered
    chain = SEQ.page_chain_status([n.get("marker_letter") for n in notes])
    # Align on the marker-filtered regions when they match the note count; fall back to the raw regions only on
    # an exact match; otherwise abstain the crop gates. The chain status travels as the count-trust signal.
    use_regions = mregions if len(mregions) == len(notes) else (regions if len(regions) == len(notes) else None)
    aligned = use_regions is not None
    flagged = 0
    for i in heb_idx:
        n = notes[i]
        text = n.get("text") or ""
        v = {"script": _script_verdict(text)}             # decision 3: scoped to the Hebrew span, not the note
        if passage is not None:                           # decision 4: reference-hypothesis (text-only)
            heb = _hebrew_run_text(text)
            if heb:
                # The Tanakh index is NOT BUILT. `is_biblical` is a stub that returns False for every token,
                # so every span is forced down the extra-biblical branch — an answer the evidence never
                # gave. Label it at the point of emission: `crossref_index: absent` travels with the
                # outcome so no consumer can read a forced classification as a measured mismatch. Remove
                # the label only when a real index backs the call.
                outcome, _hyp = RH.classify(heb, passage, is_biblical=lambda t: False)
                v["reference"] = outcome
                v["crossref_index"] = "absent"
        if aligned:
            try:
                line_crop = strip.crop(tuple(use_regions[i]["strip_box"]))
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
            v["align"] = f"unaligned(mregions={len(mregions)},regions={len(regions)},notes={len(notes)})"
        v["flag"] = (v["script"] not in ("ok", "no-hebrew")) or bool(v.get("glyph_flag"))
        v["escalate_gemma"] = v["flag"]                   # the dual-witness intake gate
        n["hebrew_verdict"] = v
        flagged += int(v["flag"])
    return notes, {"hebrew_notes": len(heb_idx), "flagged": flagged, "aligned": aligned,
                   "n_regions": len(regions), "n_marker_regions": len(mregions), "n_notes": len(notes),
                   "chain_status": chain["status"], "chain_confirmed": chain["confirmed"]}
