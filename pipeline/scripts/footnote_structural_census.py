#!/usr/bin/env python3
"""Structural census of the footnote apparatus — free text checks, NO model calls.

Pre-V2 gate artifact #1 (see HANDOFF_hebrew_census.md). Sizes the apparatus REPAIR
QUEUE and — per refinement C — estimates how much apparatus is missing / broken in the
text layer, which is the strongest input to the re-extract side of the gate.

LAYER: runs on the BASE VLM markdown (page{N}_image{V}.md), which preserves the
printer's LOWERCASE-LETTER footnote markers. `_normalized.md` renumbers them densely to
[^1..N], CLOSING the original gaps — so gap-detection there is meaningless. Verified.

CONSTRAINT D (duplicate letters): markers restart within a page (per column/paragraph),
so every check is PER ANCHOR-SCOPE, not per page. A scope = a maximal run of letters that
does not reset (a letter <= the previous one opens a new scope). Reported both ways.

Signals (per scope unless noted):
  orphan_ref   inline [^x] with no [^x]: definition  -> note TEXT dropped (lost note)
  orphan_def   [^x]: with no inline [^x] (excl. leading continuation) -> ANCHOR dropped
  continuation leading [^x]: before any ref, letter < first ref -> note carried from prev page (benign)
  count_mism   |refs| != |defs| on the page
  seq_gap      missing letter inside an increasing run (candidate dropped note); large
               gaps (>3) flagged separately as anomalies (likely mis-transcription, not a skip)
  restart      >1 scope on a page (per-column/paragraph renumber) — expected, counted for context
  dup_in_scope same letter twice inside one increasing run -> marker collision

Env: COMMENTARY_DATA_DIR / DR_VOLUMINOUS.
"""
import re, sys, io, json, os, argparse
from pathlib import Path
from collections import defaultdict, Counter
try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception: pass

EXPECTED_VOLUMES = [1, 7]     # vol3 never processed (see span-census handoff)
# HEADLINE STRUCTURAL FINDING: the overloaded VLM emits >=3 inconsistent footnote marker
# syntaxes, sometimes a DIFFERENT one for refs vs defs on the SAME page:
#   [^a]  /  [^a]:        (format 1, bracket)
#   ^a^   /  ^a^ text     (format 2, caret-wrapped, line-leading)
#   ^a^   /  [^a^]:       (format 3, hybrid: caret ref, bracket-caret def)
# Precise orphan counts are unreliable against this variety (every unhandled wrapper inflates
# orphans) — so the census is UNIVERSAL (any wrapper -> the letter) and reports the FORMAT
# INVENTORY as the primary signal. Format chaos is itself the argument for re-extract.
UNIVERSAL_MARKER = re.compile(r"\[\^([a-z])\^?\]|\^([a-z])\^")     # [^a] | [^a^] | ^a^
DEF_LEAD_RE      = re.compile(r"^\s*(?:\[\^([a-z])\^?\]:|\^([a-z])\^)(?=\s|:)")
# format-tag regexes, most-specific first, for the inventory
FMT_TAGS = [("bracket_caret", re.compile(r"\[\^[a-z]\^\]")),
            ("bracket",       re.compile(r"\[\^[a-z]\]")),
            ("caret",         re.compile(r"\^[a-z]\^"))]

def scopes(letters):
    """Split an ordered letter list into runs; a letter <= prev opens a new run."""
    runs=[]; cur=[]
    for L in letters:
        if cur and L <= cur[-1]:
            runs.append(cur); cur=[L]
        else:
            cur.append(L)
    if cur: runs.append(cur)
    return runs

def analyze_page(text):
    defs=[]; refs=[]; first_ref_seen=False; continuation=0
    lines=text.splitlines()
    for line in lines:
        dm=DEF_LEAD_RE.match(line)
        lead_letter=None; lead_end=0
        if dm:
            lead_letter=dm.group(1) or dm.group(2); lead_end=dm.end()
            defs.append(lead_letter)
            # a def before ANY inline ref, for a letter not yet referenced -> carried from prev page
            if not first_ref_seen: continuation+=1
        for mm in UNIVERSAL_MARKER.finditer(line):
            if lead_letter and mm.start()<lead_end: continue   # skip the leading def marker itself
            refs.append(mm.group(1) or mm.group(2)); first_ref_seen=True
    # format inventory: which marker syntaxes appear on this page
    fmts={name for name,rx in FMT_TAGS if rx.search(text)}
    mixed_format = 1 if len(fmts)>1 else 0
    # continuation count is provisional: only keep those whose letter never gets an inline ref
    r=Counter(refs); d=Counter(defs)
    continuation=min(continuation, sum(1 for L in d if r[L]==0))
    orphan_ref=sum((r-d).values())                 # refs with no def -> lost note text
    orphan_def=max(0, sum((d-r).values())-continuation)  # defs with no ref (excl continuation)
    count_mismatch = 1 if len(refs)!=len(defs) else 0

    # per-scope sequence analysis on DEF letters (defs are the note inventory)
    runs=scopes(defs)
    restart = 1 if len(runs)>1 else 0
    seq_gap=0; big_gap=0; dup_scope=0
    for run in runs:
        seen=set()
        for i in range(1,len(run)):
            a,b=ord(run[i-1]),ord(run[i])
            if run[i] in seen: dup_scope+=1
            gap=b-a-1
            if gap>0:
                if gap>3: big_gap+=1
                else: seq_gap+=gap
            seen.add(run[i-1]); seen.add(run[i])
    any_issue = bool(orphan_ref or orphan_def or count_mismatch or seq_gap or big_gap or dup_scope or mixed_format)
    return dict(n_ref=len(refs), n_def=len(defs), continuation=continuation,
                orphan_ref=orphan_ref, orphan_def=orphan_def, count_mismatch=count_mismatch,
                seq_gap=seq_gap, big_gap=big_gap, dup_scope=dup_scope, restart=restart,
                mixed_format=mixed_format, fmts=fmts, any_issue=any_issue)

def main():
    dv=os.getenv("DR_VOLUMINOUS", r"c:/Users/cnogr/git/dr-voluminous")
    ap=argparse.ArgumentParser()
    ap.add_argument("--commentary", default=os.getenv("COMMENTARY_DATA_DIR", f"{dv}/commentary"))
    ap.add_argument("--out", default="")
    a=ap.parse_args(); COMM=Path(a.commentary)

    per=defaultdict(lambda: defaultdict(int)); queue=[]; fmt_pages=Counter()
    for vol in EXPECTED_VOLUMES:
        qdir=COMM/f"volume{vol}"/"qwen_qwen3-vl-235b-a22b-thinking"
        if not qdir.exists(): print(f"  ⚠️ volume{vol} absent"); continue
        # BASE layer = page{N}_image{V}.md (NOT _normalized, NOT _normalized_K)
        for p in qdir.glob("*_image*.md"):
            if "_normalized" in p.name: continue
            if not re.search(r"page\d+_image\d+\.md$", p.name): continue
            t=p.read_text(encoding="utf-8", errors="replace")
            res=analyze_page(t)
            pv=per[vol]
            pv["pages"]+=1
            has_app = bool(res["n_def"] or res["n_ref"])
            if has_app:
                pv["pages_with_apparatus"]+=1
                fmt_pages["+".join(sorted(res["fmts"])) or "none"]+=1   # format signature per page
                pv["mixed_format"]+=res["mixed_format"]
            for k in ("n_ref","n_def","continuation","orphan_ref","orphan_def","count_mismatch",
                      "seq_gap","big_gap","dup_scope","restart"):
                pv[k]+=res[k]
            if res["any_issue"]:
                pv["pages_with_issue"]+=1
                pg=re.search(r"page(\d+)",p.name)
                queue.append({"vol":vol,"page":pg.group(1) if pg else "?",
                    **{k:res[k] for k in ("orphan_ref","orphan_def","count_mismatch","seq_gap","big_gap","dup_scope")}})

    cols=["pages","pages_with_apparatus","pages_with_issue","mixed_format","n_ref","n_def","continuation",
          "orphan_ref","orphan_def","count_mismatch","seq_gap","big_gap","dup_scope","restart"]
    print("=== FOOTNOTE STRUCTURAL CENSUS (base letter layer) ===")
    print(f"{'metric':22}"+"".join(f"{('vol'+str(v)):>9}" for v in EXPECTED_VOLUMES)+f"{'TOTAL':>9}")
    tot={}
    for c in cols:
        tt=sum(per[v][c] for v in EXPECTED_VOLUMES); tot[c]=tt
        print(f"{c:22}"+"".join(f"{per[v][c]:>9}" for v in EXPECTED_VOLUMES)+f"{tt:>9}")

    apg=tot["pages_with_apparatus"] or 1
    print(f"\n=== HEADLINE: FOOTNOTE-FORMAT INVENTORY (per-page marker syntax) ===")
    for sig,c in fmt_pages.most_common():
        print(f"  {sig:26} {c:5} pages  ({100*c/apg:.0f}%)")
    print(f"  → mixed-format pages (ref-syntax != def-syntax etc.): {tot['mixed_format']} ({100*tot['mixed_format']/apg:.0f}%)")
    print(f"  The apparatus text layer has NO consistent marker convention — repair has no stable")
    print(f"  structure to target; this is the core argument for re-extraction over span-repair.")
    print(f"\n=== RATES (of pages carrying apparatus = {tot['pages_with_apparatus']}) ===")
    print(f"  structurally-broken pages: {tot['pages_with_issue']}  ({100*tot['pages_with_issue']/apg:.0f}%) = REPAIR QUEUE size")
    print(f"\n=== MISSING / BROKEN APPARATUS (refinement C — what repair cannot recover if absent) ===")
    print(f"  lost note TEXT (orphan_ref: anchor present, note dropped): {tot['orphan_ref']}")
    print(f"  lost ANCHOR (orphan_def: note present, in-text marker dropped): {tot['orphan_def']}")
    print(f"  small sequence gaps (candidate dropped notes): {tot['seq_gap']}")
    print(f"  large gaps / anomalies (likely mis-transcription): {tot['big_gap']}")
    print(f"  ref/def count mismatches (pages): {tot['count_mismatch']}   marker collisions: {tot['dup_scope']}")
    print(f"  (context) per-page renumber restarts: {tot['restart']}  continuation notes carried in: {tot['continuation']}")
    print("\n--- repair-queue sample (worst pages) ---")
    for q in sorted(queue, key=lambda x:-(x['orphan_ref']+x['orphan_def']+x['big_gap']+x['seq_gap']))[:12]:
        print(f"  vol{q['vol']} p{q['page']}: orphan_ref={q['orphan_ref']} orphan_def={q['orphan_def']} "
              f"gap={q['seq_gap']} big_gap={q['big_gap']} mism={q['count_mismatch']} dup={q['dup_scope']}")
    if a.out:
        Path(a.out).write_text(json.dumps({"per_volume":{v:dict(per[v]) for v in per},"repair_queue":queue},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nWritten -> {a.out}")

if __name__=="__main__": main()
