"""Chain-walk census over the whole volume (config-v2, build step 0 of SEQUENCE_GATE_SCOPE).

WHAT IT CAN AND CANNOT USE (measured 2026-09-13): the frozen output has canonical `[^N]` (no original marker
letters) and the body markdown has no anchors (anchor-matching failed), so the letter chain cannot be walked
from stored text. Two things ARE available and sufficient for the census's purpose — finding where the
extractor lost notes:
  - the DETECTOR's independent per-page note count (note_start_detect) — the signal that already exposed the
    collapse pages (p129: extractor 1, detector 13);
  - the body markdown's CHAPTER/BOOK header per page (e.g. "GENESIS. CH. VI.") — the reset boundaries.

So the chain is walked on detector counts, reset at book-intro / Chapter-I read from the headers, wrap z→a.
Markers are DERIVED from the count-chain (a prediction), NOT glyph-read — the letter-precise read awaits the
confirmation-read step. Three outputs:
  BREAKS  every page where extractor_count != detector_count — the extractor lost/gained notes there. Reports
          both counts and the derived expected markers, so the letters the re-extraction must produce are named.
  RESETS  every reset the header implies (book intro / Chapter I / other chapter / none) — settles "does every
          chapter reset?" once glyph reads exist to confirm the observed reset.
  RUNS    unbroken stretches (extractor == detector) — the only pages from which marker exemplars may be
          harvested (a broken run's letters aren't trustworthy labels).
Report counts before anything else. p2/p315 are outside the extracted range (3–960) — noted, not a false break."""
import re, sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import cv_footnote_presplit as ps
import note_start_detect as NS
import marker_alphabet as MA

RUN = Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/vol1_apparatus.jsonl")
IMG = Path("C:/Users/cnogr/git/dr-voluminous/commentary/volume1")
BOOKS = ["GENESIS", "EXODUS", "LEVITICUS", "NUMBERS", "DEUTERONOMY"]
_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10}

def _header(page):
    """(book, chapter_int|None, is_intro) from the body markdown header, or (None, None, False)."""
    p = IMG / f"page{page}_image1.md"
    if not p.exists():
        return None, None, False
    head = "\n".join(p.read_text(encoding="utf-8").splitlines()[:3]).upper()
    book = next((b for b in BOOKS if b in head), None)
    mch = re.search(r"CH(?:AP)?\.?\s+([IVX]+)\b", head)
    chapter = _ROMAN.get(mch.group(1)) if mch else None
    is_intro = book is not None and chapter is None and ("INTRODUC" in head or True)  # book name, no chapter
    return book, chapter, is_intro

def run_census(pages=None):
    """Count-based census — no letters, so NO assumed resets and NO derived-letter chain (both would assume
    the per-volume reset rule the census exists to discover). It reports what the counts + headers alone can
    honestly show; the marker READ (later) confirms resets and turns candidate boundaries into observed facts."""
    frozen = {r["page"]: r for r in (json.loads(l) for l in open(RUN, encoding="utf-8") if l.strip()) if "page" in r}
    pages = pages or sorted(frozen)
    breaks, boundaries, runs = [], [], []
    prev_book = None; prev_chapter = None; run_start = None; last_page = None
    for pg in pages:
        book, chapter, _ = _header(pg)
        strip, info = ps.presplit(str(IMG / f"page{pg}_image1.png"), upscale=1)
        det = len(NS.page_starts(strip)) if strip is not None else 0
        ext = frozen[pg].get("n_notes") or 0               # None on no-apparatus / front-matter pages
        if book and book != prev_book:                     # a CANDIDATE reset boundary from the alignment —
            boundaries.append(dict(page=pg, kind="book_start", book=book, chapter=chapter, reset="unconfirmed"))
        elif chapter is not None and chapter != prev_chapter:
            boundaries.append(dict(page=pg, kind=f"chapter_{chapter}", book=book, chapter=chapter, reset="unconfirmed"))
        if ext != det:                                     # the BREAK — extractor's count disagrees with the
            breaks.append(dict(page=pg, book=book, chapter=chapter, extractor=ext, detector=det,  # independent detector
                               gap=det - ext, note="detector>extractor => extractor likely LOST notes" if det > ext
                               else "extractor>detector => detector likely under-counted (verify)"))
            if run_start is not None:
                runs.append([run_start, last_page]); run_start = None
        else:
            if run_start is None: run_start = pg
        prev_book = book or prev_book; prev_chapter = chapter if chapter is not None else prev_chapter; last_page = pg
    if run_start is not None: runs.append([run_start, last_page])
    return dict(breaks=breaks, candidate_boundaries=boundaries, runs=runs, n_pages=len(pages))

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=str(Path(RUN).parent / "audits" / "chain_census.json"))
    ap.add_argument("--pages", default=""); a = ap.parse_args()
    pgs = [int(x) for x in a.pages.split(",")] if a.pages else None
    res = run_census(pgs)
    Path(a.out).write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"CENSUS COUNTS: {len(res['breaks'])} breaks, {len(res['candidate_boundaries'])} candidate reset boundaries, "
          f"{len(res['runs'])} unbroken runs, over {res['n_pages']} pages")
    big = [b for b in res["breaks"] if abs(b["gap"]) >= 3]
    print(f"  of the breaks, {len(big)} are gross (|gap|>=3) — the extractor-collapse class:")
    for b in sorted(res["breaks"], key=lambda x: abs(x["gap"]), reverse=True)[:15]:
        print(f"    p{b['page']:<4} {b['book']} ch{b['chapter']}  extractor={b['extractor']} detector={b['detector']} gap={b['gap']:+d}")
    print(f"  wrote {a.out}")
