"""Stage-2 SCRIPT-CENSUS — deterministic witness that non-Latin script EXISTS, independent of the
VLM. Catches the one loss class nothing text-side can see: Hebrew/Greek/Arabic in the image the VLM
silently dropped. Per the FOSSIL (get_md.py ran Tesseract with heb+grc+ara), run Tesseract multi-lang
per footnote strip — it mangles the glyphs but reliably DETECTS that non-Latin is present — count
non-Latin lines, RECONCILE against the extraction's non-Latin-span count. census > extraction =
fail-loud candidate invisible loss.

Instrument caveats (VALIDATED against image-known pages — the instrument must itself be validated):
- **HEBREW-ONLY** with a ≥2-Hebrew-chars-per-line threshold is 7/8 correct: p100/p702 (no Hebrew)
  correctly clear; stray `γ` marker (1 char) ignored; false-NEGATIVE on one worn span (p550's שורש).
  So it's a CONSERVATIVE LOWER BOUND, not exact.
- Adding **grc+ara made it WORSE** — Tesseract hallucinates Greek/Arabic on the Latin-heavy apparatus
  (p100/p702/p243 false-positived). Greek/Arabic invisible-loss needs a BETTER witness (the noisy
  Tesseract grc/ara is not it). Hebrew is the reliable script here; grc/ara census = TODO.
"""
import sys, os, re, json, argparse
from collections import defaultdict
from pathlib import Path
import pytesseract
from PIL import Image
pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_CMD", r"C:/Program Files/Tesseract-OCR/tesseract.exe")

NONLATIN = re.compile(r"[\u0590-\u05FF]")   # HEBREW-ONLY (grc/ara Tesseract too noisy — see docstring)
MIN_CHARS = 2   # a Hebrew LINE needs >=2 Hebrew chars (ignores stray marker glyphs)

def census_strip(strip_path):
    d = pytesseract.image_to_data(Image.open(strip_path), lang="heb+eng",
                                  config="--psm 4", output_type=pytesseract.Output.DICT)
    lines = defaultdict(int)
    for i in range(len(d["text"])):
        n = len(NONLATIN.findall(d["text"][i] or ""))
        if n: lines[(d["block_num"][i], d["par_num"][i], d["line_num"][i])] += n
    return sum(1 for v in lines.values() if v >= MIN_CHARS)

def vlm_nonlatin_spans(rec):
    return sum(1 for note in rec.get("extracted", []) if NONLATIN.search(note["text"]))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results"); ap.add_argument("--strips", required=True)
    a = ap.parse_args()
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    results = {str(r["page"]): r for r in json.loads(Path(a.results).read_text(encoding="utf-8"))}
    sd = Path(a.strips); flagged = []
    print(f'{"page":>5} {"census(non-Latin lines)":>24} {"vlm(non-Latin notes)":>21}  status')
    for pg, rec in sorted(results.items(), key=lambda x: int(x[0])):
        strip = sd / f"strip_{pg}.png"
        if not strip.exists(): continue
        c = census_strip(strip); v = vlm_nonlatin_spans(rec)
        st = "OK" if c <= v else f"⚠ candidate loss (+{c-v})"
        if c > v: flagged.append((pg, c - v))
        print(f'{pg:>5} {c:>24} {v:>21}  {st}')
    print(f'\n{len(flagged)} pages flagged (conservative LOWER BOUND on invisible non-Latin loss).')
    if flagged: print("flagged:", [f"p{p}(+{d})" for p, d in flagged])

if __name__ == "__main__": main()
