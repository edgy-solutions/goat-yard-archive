"""Size the TEXT-SPLIT continuation population (the only case stitching would join), separately
from sequence-continuation (letter run spans pages; notes complete; handled by assembler scope).

This is the CITATION for book_profile.gill.yaml `cross_page_text_splits: none_observed` and for the
assembler's stitch-whitelist. Result on vol1 (871 pages, base letter layer): 0 real text-splits;
candidate split-OUT = 6 (all artifacts: signature marks, Hebrew-final, OCR-dropped periods);
candidate split-IN = 2 (both Latin lexicographer glosses); 0 adjacent OUT/IN pairs. The split-IN
signal fires on the RECEIVING page regardless of whether the sending page's tail was dropped, so
this is not an undercount of the lossy base layer.

Env: DR_VOLUMINOUS / COMMENTARY_DATA_DIR.
"""
import re, sys, io, os, argparse
from pathlib import Path
try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception: pass

DEF_LEAD_RE = re.compile(r"^\s*(?:\[\^([a-z])\^?\]:|\^([a-z])\^)\s*(.*)$")
TERMINAL = tuple(".!?)]\u2019\"")

def opens_lowercase(t):
    t = t.strip()
    return bool(t) and t[0].isalpha() and t[0].islower() and ord(t[0]) < 0x400

def page_defs(text):
    out = []
    for line in text.splitlines():
        m = DEF_LEAD_RE.match(line)
        if m: out.append((m.group(1) or m.group(2), (m.group(3) or "").strip()))
    return out

def main():
    dv = os.getenv("DR_VOLUMINOUS", r"c:/Users/cnogr/git/dr-voluminous")
    ap = argparse.ArgumentParser()
    ap.add_argument("--commentary", default=os.getenv("COMMENTARY_DATA_DIR", f"{dv}/commentary"))
    ap.add_argument("--volume", default="volume1")
    ap.add_argument("--subdir", default="qwen_qwen3-vl-235b-a22b-thinking")
    a = ap.parse_args()
    qdir = Path(a.commentary) / a.volume / a.subdir
    pages = []
    for p in qdir.glob("*_image*.md"):
        if "_normalized" in p.name: continue
        m = re.search(r"page(\d+)_image", p.name)
        if m: pages.append((int(m.group(1)), p))
    pages.sort()
    out_trunc, in_lower, joined = [], [], []
    prev = None
    for num, p in pages:
        defs = page_defs(p.read_text(encoding="utf-8", errors="replace"))
        first_low = bool(defs) and opens_lowercase(defs[0][1])
        last_trunc = bool(defs) and defs[-1][1] and not defs[-1][1].rstrip().endswith(TERMINAL)
        if first_low: in_lower.append((num, defs[0][1][:70]))
        if last_trunc: out_trunc.append((num, defs[-1][1][-70:]))
        if prev and prev[0] == num - 1 and prev[2] and first_low:
            joined.append((prev[0], num))
        prev = (num, p, last_trunc)
    print(f"{a.volume}: pages={len(pages)}")
    print(f"candidate split-OUT (last note not terminal-punctuated): {len(out_trunc)}")
    print(f"candidate split-IN  (first note opens lowercase)       : {len(in_lower)}")
    print(f"REAL text-split pairs (OUT(N) & IN(N+1) adjacent)      : {len(joined)}")
    print("\nsplit-OUT candidates (classify as artifacts):")
    for n, t in out_trunc: print(f"  p{n}: ...{t!r}")
    print("\nsplit-IN candidates:")
    for n, t in in_lower: print(f"  p{n}: {t!r}")

if __name__ == "__main__": main()
