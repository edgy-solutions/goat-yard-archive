"""The ALIGNMENT GATE — replaces the count gate for note→region mapping (Chris, 2026-09-20).

Standing law recorded with this module: **sequence equality is sufficient, cancellation must fail.** The
count gate compared two totals, so a compensating error (one false note-start + one missed start) summed to
the right number and passed while every note after the first was mis-mapped — measured at 21 of 54 notes on
gated pages. Counting is retired as authority. What replaces it is correspondence: read each region on its
own crop, and require each region's text to correspond, one-to-one and in order, with a whole-band note.

  region crop --(BAML typed Note path)--> text born WITH its rectangle
  whole band  --(same path)------------> the v2 note sequence
  align on normalized LATIN tokens (Hebrew spans excluded from the key), one-to-one, monotone

Hebrew is excluded from the alignment key deliberately. The Hebrew is the least reliably transcribed part
of the page and the thing the geometry exists to locate; keying on it would make the gate's input depend on
what the gate is meant to protect. Latin tokens are the reliable things to count.

PER-REGION OUTCOMES — only `aligned` yields a mapping; everything else abstains at NOTE level, not page
level (a page is no longer all-or-nothing):

  aligned     exactly one whole-band note clears T_HIGH and the monotone assignment agrees
  spurious    no note is substantially contained in this region — a false note-start. Corroborated when the
              region's own read comes back `no_footnote_present`, which is the intake gate doing its job:
              a region with nothing in it must be able to SAY so rather than inventing a note.
  merged      the region's OWN read returned two or more notes, OR two or more whole-band notes are
              substantially contained in it — a missed start
  ambiguous   a candidate clears T_LOW but not T_HIGH, or best and runner-up are within MARGIN

THE `n_read` RULE, AND THE MEASUREMENT THAT FORCED IT (2026-09-20). The first scored run produced 7 wrong
mappings — 4 dev, 3 contaminated — and **every one of them was a region whose own read returned 2 or 3
notes.** The read had said, plainly, "there is more than one footnote in this crop." `read_page` then kept
`rn[0]` and threw the rest away, the surviving first note matched its band note at similarity 1.000, and
the gate reported a clean mapping while handing that note a rectangle containing its neighbour.

The component was honest and the harness discarded the honesty. That is the same defect as a system with no
"empty" channel: `no_footnote_present` is how a region says "nothing here", and `len(notes) >= 2` is how it
says "more than one here" — both are the read's own testimony about its input, and both must be able to
stop a mapping. A region that reports two notes is MERGED. This is a deterministic property of the read,
not a threshold: there is nothing to tune and nothing to fit.

The rule is derived from the failures it removes, so dev going to zero wrong proves nothing — that number
is circular and is reported as such. SEALED, scored once, is the only evidence for the zero.

SECONDARY CHECK on aligned notes: the marker sub-crop goes to the confusable-margin verifier expecting the
aligned note's letter. A REJECT demotes to abstain and logs; an ABSTAIN changes nothing. This is deliberately
one-directional — the verifier is known to have no competitor for 11 of 24 letters and to confirm those
unconditionally (see the p128 card), so it is trusted to REFUSE and never trusted to CONFIRM.

WHAT THIS GATE DOES NOT DO: it validates CORRESPONDENCE between two reads, not the truth of either. If the
whole-band read is fabricated (p403 returned a textbook a..j against a ratified x,y,z,a,b|c,d,e,f,a), a
region read that agrees with it aligns cleanly and the gate says nothing. Agreement of two reads through
the same model on the same pixels is not independent evidence. The ratified boxes are what test this gate;
the gate does not test itself."""
import json, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import note_line_region as NLR
import note_crop as NC
import cv_footnote_presplit as ps

IMG = Path("C:/Users/cnogr/git/dr-voluminous/commentary/volume1")

# thresholds — set on DEV + CONTAMINATED only, then frozen before sealed is scored
T_HIGH, T_LOW, T_CONT, MARGIN = 0.60, 0.30, 0.50, 0.15

_HEB = re.compile(r"[\u0590-\u05FF]")
_GRK = re.compile(r"[\u0370-\u03FF\u1F00-\u1FFF]")
_WORD = re.compile(r"[A-Za-z\u00C0-\u024F]+")


def tokens(text):
    """Normalized Latin token SET. Hebrew and Greek dropped — the alignment key must not depend on the
    scripts the geometry exists to locate. Single characters dropped: a stray marker letter or a piece of
    furniture is noise, not evidence of correspondence."""
    if not text:
        return set()
    t = _HEB.sub(" ", text)
    t = _GRK.sub(" ", t)
    return {w.lower() for w in _WORD.findall(t) if len(w) >= 2}


def sim(a, b):
    """Jaccard over Latin-token sets."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def contained(note_toks, region_toks):
    """Fraction of a whole-band note's tokens present in a region — asymmetric on purpose. A merged region
    CONTAINS several notes while having low Jaccard with each of them, so containment is what detects a
    missed start and Jaccard is what detects a clean one-to-one."""
    if not note_toks:
        return 0.0
    return len(note_toks & region_toks) / len(note_toks)


def monotone_assign(S, t_low):
    """Best one-to-one, order-preserving assignment of regions→notes maximizing total similarity. Classic
    DP: regions and notes are both in reading order, so a correspondence that crosses is not a
    correspondence — it is evidence the mapping is wrong. Returns {region_i: note_j}."""
    R, N = len(S), (len(S[0]) if S else 0)
    if not R or not N:
        return {}
    NEG = -1e9
    dp = [[0.0] * (N + 1) for _ in range(R + 1)]
    bk = [[None] * (N + 1) for _ in range(R + 1)]
    for i in range(1, R + 1):
        for j in range(1, N + 1):
            best, arg = dp[i - 1][j], ("skip_r", i - 1, j)          # region unmatched
            if dp[i][j - 1] > best:
                best, arg = dp[i][j - 1], ("skip_n", i, j - 1)      # note unmatched
            s = S[i - 1][j - 1]
            if s >= t_low and dp[i - 1][j - 1] + s > best:
                best, arg = dp[i - 1][j - 1] + s, ("match", i - 1, j - 1)
            dp[i][j], bk[i][j] = best, arg
    out, i, j = {}, R, N
    while i > 0 and j > 0:
        kind, pi, pj = bk[i][j]
        if kind == "match":
            out[pi] = pj
        i, j = pi, pj
    return out


def classify(region_reads, band_notes):
    """Per-region outcome. `region_reads` is [{text,status,marker_letter}] in reading order (one per
    detected region); `band_notes` is the whole-band v2 note list. Returns a list of dicts."""
    rtoks = [tokens(r.get("text")) for r in region_reads]
    ntoks = [tokens(n.get("text")) for n in band_notes]
    S = [[sim(rt, nt) for nt in ntoks] for rt in rtoks]
    assign = monotone_assign(S, T_LOW)

    out = []
    for i, rt in enumerate(rtoks):
        row = S[i] if ntoks else []
        order = sorted(range(len(row)), key=lambda j: row[j], reverse=True)
        best_j = order[0] if order else None
        best = row[best_j] if best_j is not None else 0.0
        second = row[order[1]] if len(order) > 1 else 0.0
        conts = [j for j in range(len(ntoks)) if contained(ntoks[j], rt) >= T_CONT]
        status = (region_reads[i].get("status") or "").lower()
        n_read = int(region_reads[i].get("n_read") or 1)

        # The region's OWN read is asked first. If it found two notes in this crop, the crop spans two
        # notes — no token arithmetic can overturn the read's own count of what it saw, and the alignment
        # key is built from only the FIRST of those notes, so containment is blind here by construction.
        if n_read >= 2:
            cls, mapped = "merged", None
        elif len(conts) >= 2:
            cls, mapped = "merged", None
        elif not conts and best < T_LOW:
            cls, mapped = "spurious", None
        elif best >= T_HIGH and (best - second) >= MARGIN and assign.get(i) == best_j:
            cls, mapped = "aligned", best_j
        else:
            cls, mapped = "ambiguous", None

        out.append({"i": i, "cls": cls, "note": mapped, "best_j": best_j, "n_read": n_read,
                    "merged_by": ("region-read" if n_read >= 2 else
                                  "containment" if len(conts) >= 2 else None),
                    "best": round(best, 3), "second": round(second, 3),
                    "contains": conts, "region_status": status,
                    "empty_self_report": status == "no_footnote_present",
                    "assigned": assign.get(i)})
    return out


def read_page(page, profile, model=None, host=None, want_band=True):
    """Read a page's whole band AND every detected region on its own crop. Returns a record; no alignment
    is done here so the expensive reads can be cached and re-classified as thresholds move."""
    from extract_apparatus import transcribe_baml
    img = IMG / f"page{page}_image1.png"
    if not img.exists():
        return {"page": page, "status": "no-image"}
    strip, info = ps.presplit(str(img), upscale=1)
    regions, stitched = NLR.detect_regions(strip, profile)
    rec = {"page": page, "status": "ok", "stitched": stitched, "n_regions": len(regions),
           "strip_size": list(strip.size), "regions": [], "t": time.strftime("%H:%M:%S")}

    if want_band:
        t0 = time.perf_counter()
        bn, why = transcribe_baml(strip, profile, model=model, host=host)
        rec["band_notes"] = bn
        rec["band_secs"] = round(time.perf_counter() - t0, 1)
        rec["band_reason"] = why

    for k, r in enumerate(regions):
        boxes = [NC._seg_box(s) for s in r["segments"]]
        t0 = time.perf_counter()
        # a stitched note is two rects; read the FIRST segment's crop — the marker and the note's opening
        # words live there, which is what the alignment key needs
        crop = strip.crop(tuple(boxes[0]))
        try:
            rn, why = transcribe_baml(crop, profile, model=model, host=host)
        except Exception as e:
            rn, why = [], f"error:{type(e).__name__}"
        first = rn[0] if rn else {"text": "", "status": "no_footnote_present", "marker_letter": None}
        rec["regions"].append({"k": k, "boxes": boxes, "stitched": len(boxes) > 1,
                               "n_read": len(rn), "text": first.get("text"),
                               "status": first.get("status"), "marker_letter": first.get("marker_letter"),
                               "reason": why, "secs": round(time.perf_counter() - t0, 1)})
    return rec
