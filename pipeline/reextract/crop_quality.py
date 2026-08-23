"""CROP-QUALITY GUARD (Build 3's guard) — two DETERMINISTIC, FREE checks that gate per-note crops
BEFORE any model call (gate, not filter: a starved sliver produces fluent invention, not blank output —
never ask the model about it, p219). Both are layout invariants the pixels can refuse with no VLM:

  positions_valid(starts, line_height) — two note-starts cannot sit within ~one line-height of each
    other (a layout impossibility; on p219 the CV positions came back 40px apart). If violated, the
    whole page's position set is unreliable -> fall back to the strip-pass for the page.
  crop_has_line(crop) — a crop must contain >= one line of ink; a rule-line + letter-tops sliver does
    not. If violated, that note falls back to the strip-pass (the floor).

Strip is always the floor; per-note only PROPOSES where its crop passes both gates. Residual case
(both crops usable, readings differ) is NOT resolved by preference — it routes to the dual-witness
ladder like any other witness disagreement (reconcile()).
"""
import numpy as np
import hanging_indent as hi

def line_height(strip, ink_thresh=110):
    """Median text-line height (px in strip space) — the layout unit both checks measure against."""
    a = np.asarray(strip.convert("L")) < ink_thresh
    hs = sorted(y1 - y0 for y0, y1 in hi._text_lines(a))
    return hs[len(hs) // 2] if hs else 0

def positions_valid(starts, lh, tol=0.6):
    """False iff any two adjacent note-starts are closer than ~one line-height (impossible layout ->
    the position set is unreliable). tol<1 gives slack for tight leading."""
    s = sorted(starts)
    if len(s) < 2 or lh <= 0:
        return True
    return all(s[i + 1] - s[i] >= tol * lh for i in range(len(s) - 1))

def crop_has_line(crop, ink_thresh=110, min_dark_rows_frac=0.08, min_ink=0.008):
    """False iff the crop is mostly rule/whitespace (a starved sliver — the p219 mis-crop: a rule line +
    letter-tops) rather than >= one line of text. Discriminator (measured): a sliver's inked rows are a
    tiny fraction of its height (p219 crop_0 = 6%), a real note's are more (even a short note ~10%+).
    Calibrated on p219 crop_0 (reject) vs p226 crops incl. the short first note (keep). This gate is a
    CHEAP first filter — the real correctness net is reconcile()'s disagreement->ladder->strip-floor, so
    a sliver that slips the gate still can't ship: its hallucination will differ from strip and route out."""
    a = np.asarray(crop.convert("L")) < ink_thresh
    if a.size == 0:
        return False
    rowink = a.sum(axis=1)
    if rowink.max() == 0:
        return False
    dark_rows = int((rowink > rowink.max() * 0.15).sum())
    return bool(dark_rows / a.shape[0] >= min_dark_rows_frac and a.mean() >= min_ink)

def reconcile(strip_notes, per_note_notes, starved_idx):
    """Combine the two passes under the law. STRIP is the floor. For each note index: if per-note's crop
    was starved -> take strip (no judgment). If both present: agree -> per-note; DIFFER -> route to the
    ladder (returned as a 'dispute' for agreement_ladder/blind_retry, NEVER resolved by preference here).
    Returns (notes, disputes) where disputes are (idx, strip_text, per_note_text) for the ladder."""
    import agreement_ladder as AL
    out, disputes = [], []
    n = max(len(strip_notes), len(per_note_notes))
    for i in range(n):
        s = strip_notes[i] if i < len(strip_notes) else None
        p = per_note_notes[i] if i < len(per_note_notes) else None
        if i in starved_idx or p is None:
            if s is not None: out.append({**s, "provenance": "strip-floor"})
            continue
        if s is None:
            out.append({**p, "provenance": "per-note"}); continue
        if AL.ladder([s["text"]], [p["text"]])["rung"] == "agree":
            out.append({**p, "provenance": "per-note"})
        else:
            disputes.append((i, s["text"], p["text"]))
            out.append({**s, "provenance": "strip-floor-pending-ladder"})   # floor holds until adjudicated
    return out, disputes
