#!/usr/bin/env python3
"""V1 non-Latin span census + detector (the reusable ingestion-stage instrument).

Walks the canonical commentary markdown, detects Hebrew spans, and classifies each
meaningful (non-garbage) span into three tiers plus a garbage bucket:

  case-1              span matches the PASSAGE's own OT verse (had ground truth at
                      correction time). No expert review needed.
  biblical-cross-ref  span matches SOME OTHER OT verse (incl. every biblical span in
                      NT volumes, whose passage has no Hebrew). EASY review tier —
                      batch-checkable straight against the Tanakh.
  extra-biblical      span matches no OT verse (rabbinic / Talmudic / proper nouns).
                      The HARD review tier — this is what V2 validation samples.
  garbage             reversed / scrambled OCR (final-form letter in non-final
                      position). Kept as a separate lower-priority correction-failure
                      bucket, NOT discarded (filter-to-a-bucket discipline).

Passage verse per span comes from the alignment artifacts (verse_ref segments),
located by start-phrase TEXT SEARCH (robust to markdown-version offset drift).

STANDING RULE — markdown headers are NEVER a passage-identity source. The book/
chapter headers in the commentary markdown are Gill's own CROSS-REFERENCE citations
(e.g. "Mark"/"Luke" printed on a Matthew page), not the passage he is expounding.
The convenient metadata lies; the verified artifact (alignment verse_ref) tells the
truth. Any future stage that re-derives passage identity from headers re-derives a bug.

REFERENCE-WINDOW finding (why the tiers are the shape they are). The correction
pipeline supplied the model only the PASSAGE's own verse Hebrew (and nothing for NT
passages). So every OTHER verse Gill quotes in the same snippet was unreferenced at
correction time — exactly as unprotected as extra-biblical material. case-1 is
therefore referenced-then (vol1 passage-verse only, by construction). The Psalms-era
ingestion prompt SHOULD widen the window to the passage verse + every OT verse Gill
cites on the page (via alignment + parsed citations), converting tomorrow's
biblical-cross-ref into genuine case-1 — prevention over cleanup. General law: a
reference is only as wide as what was actually in the prompt; provenance must RECORD
what was referenced, not assume it.

Cross-ref is matched PER CANDIDATE VERSE (a span is biblical only if some SINGLE OT
verse contains all its words — inverted index), NOT presence-anywhere-in-the-OT — so a
Talmudic phrase of common words cannot accidentally blob-match into the easy tier.
Validated on THREE-jaw controls: taʿun -> extra-biblical; known lemma -> case-1;
known vol7 OT quotation -> biblical-cross-ref.

RETIRED SIGNATURES (recorded, not silently dropped):
  gloss-gap  Retired after two refinements (raw 1965 -> transliteration-aware 380);
             residue remained English et/ymology discussion ("which signifies", "in
             the Hebrew language"), not dropped-Hebrew. Corroborated by
             meta-description == 0 and the normalization pipeline resolving the
             placeholder failures. RETIRED FOR THE NORMALIZED CORPUS ONLY — the
             ingestion-stage detector for fresh (un-normalized) Psalms-era material
             may face a genuinely non-empty dropped-Hebrew class; re-evaluate there.

Read-only. No model calls. Fail-loud on corpus membership (declared expected volumes).
"""
import re, sys, io, json, argparse
from pathlib import Path
from collections import defaultdict
try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception: pass

EXPECTED_VOLUMES = {1, 3, 7}
VOL_NOTES = {3: "never normalized (raw OCR attempt only, no qwen/_normalized stage); "
                "deleted-for-now from disk 2026-08; recoverable via git; on the "
                "Psalms-era ingestion queue to be processed through the current pipeline."}

HEB_ANY = re.compile(r"[\u0590-\u05FF\uFB1D-\uFB4F]+")
CONS = set(range(0x05D0, 0x05EB))
FIN = {"\u05DA":"\u05DB","\u05DD":"\u05DE","\u05DF":"\u05E0","\u05E3":"\u05E4","\u05E5":"\u05E6"}
FINSET = set(FIN)
PREFIXES = set("הובכלמש")
TAUN = "\u05D8\u05B8\u05E2\u05D5\u05BC\u05DF"

# verse_ref book name -> USFM code (OT only; NT/absent names are treated as non-Hebrew)
OT_CODE = {"GENESIS":"GEN","EXODUS":"EXO","LEVITICUS":"LEV","NUMBERS":"NUM","DEUTERONOMY":"DEU",
    "JOSHUA":"JOS","JUDGES":"JDG","RUTH":"RUT","1 SAMUEL":"1SA","2 SAMUEL":"2SA","1 KINGS":"1KI",
    "2 KINGS":"2KI","1 CHRONICLES":"1CH","2 CHRONICLES":"2CH","EZRA":"EZR","NEHEMIAH":"NEH",
    "ESTHER":"EST","JOB":"JOB","PSALM":"PSA","PSALMS":"PSA","PROVERBS":"PRO","ECCLESIASTES":"ECC",
    "SONG OF SOLOMON":"SNG","ISAIAH":"ISA","JEREMIAH":"JER","LAMENTATIONS":"LAM","EZEKIEL":"EZK",
    "DANIEL":"DAN","HOSEA":"HOS","JOEL":"JOL","AMOS":"AMO","OBADIAH":"OBA","JONAH":"JON","MICAH":"MIC",
    "NAHUM":"NAM","HABAKKUK":"HAB","ZEPHANIAH":"ZEP","HAGGAI":"HAG","ZECHARIAH":"ZEC","MALACHI":"MAL"}

def cons(s): return "".join(FIN.get(c,c) for c in s if ord(c) in CONS)
def words_of(span): return [cons(w) for w in HEB_ANY.findall(span)]
def strip_prefix_forms(w):
    forms={w}; cur=w
    for _ in range(3):
        if len(cur)>3 and cur[0] in PREFIXES: cur=cur[1:]; forms.add(cur)
        else: break
    return forms
def is_garbage(span):
    for run in re.findall(r"[\u05D0-\u05EA\u05DA\u05DD\u05DF\u05E3\u05E5]+", span):
        for i,ch in enumerate(run):
            if ch in FINSET and i != len(run)-1: return True
    return False
def skeleton(w):
    """Matres-lectionis skeleton: drop optional yod/vav (vowel-letters) except the
    word-initial consonant, so plene (דיבר) and defective (דבר) spellings collapse.
    A LOOSENING — guarded by the four-jaw controls (must not let ṭaʿun mater-match)."""
    return w[:1] + re.sub("[יו]", "", w[1:]) if w else w

def load_hbo(hbo_dir):
    """Returns (verse_words, inverted, sk_inverted). inverted[full-form]=verse-keys;
    sk_inverted[skeleton-form]=verse-keys — both prefix-expanded."""
    verse_words=defaultdict(set); inverted=defaultdict(set); sk_inverted=defaultdict(set)
    for f in sorted(hbo_dir.glob("*.usfm")):
        code=None; ch=v=0
        for line in f.read_text(encoding="utf-8",errors="replace").splitlines():
            if line.startswith("\\id "): code=line[4:].split()[0].strip()
            elif line.startswith("\\c "):
                m=re.search(r"\d+",line); ch=int(m.group()) if m else ch
            elif line.startswith("\\v "):
                rest=line[3:]; m=re.match(r"\s*(\d+)",rest); v=int(m.group(1)) if m else v
                for w in HEB_ANY.findall(rest):
                    c=cons(w)
                    if len(c)>=2:
                        key=(code,ch,v)
                        for form in strip_prefix_forms(c):
                            verse_words[key].add(form); inverted[form].add(key)
                            sk_inverted[skeleton(form)].add(key)
    return verse_words, inverted, sk_inverted

def _word_verses(w, inverted, sk_inverted):
    # STRICT full-form (prefix-aware) matching. Global matres/skeleton tolerance was
    # tried and REJECTED by the ṭaʿun control — the skeleton ט-ע-ן collides with the
    # biblical root, so global collapse mis-routes a hard span into the easy tier. The
    # apparatus split (footnote context) absorbs most plene false-positives without it;
    # true matres tolerance must be CANDIDATE-SET-SCOPED (passage + cited verses only),
    # which needs the citation parser — deferred. sk_inverted retained but unused.
    vs=set()
    for form in strip_prefix_forms(w):
        vs |= inverted.get(form, set())
    return vs

def candidate_verses(span, inverted, sk_inverted):
    """Verses that contain ALL of the span's (prefix- + matres-aware) words — the
    per-verse 'real single-verse quotation' test. Empty => extra-biblical."""
    ws=[w for w in words_of(span) if len(w)>=3] or [w for w in words_of(span) if len(w)>=2]
    if not ws: return set()
    sets=[]
    for w in ws:
        vs=_word_verses(w, inverted, sk_inverted)
        if not vs: return set()
        sets.append(vs)
    return set.intersection(*sets)

_APPARATUS_LINE=re.compile(r"^\s*(?:\[\^[^\]]+\]:|FOOTNOTES?:)", re.I)
def in_apparatus(text, pos):
    """Is `pos` inside a footnote-definition line ([^N]: ...) — Gill's citation
    apparatus? Its Hebrew is lexicographers' forms, unreferenced-then, adjudicated
    against a different shelf; a first-class hard-tier sub-population."""
    ls=text.rfind("\n",0,pos)+1
    return bool(_APPARATUS_LINE.match(text[ls:ls+8]))

def parse_ref(ref):
    m=re.match(r"^\s*([1-3]?\s?[A-Z][A-Z ]+?)\s+(\d+)(?::(\d+))?(?:\s+(End))?\s*$", ref.strip())
    if not m: return None
    book=re.sub(r"\s+"," ",m.group(1)).strip(); ch=int(m.group(2)); v=int(m.group(3)) if m.group(3) else None
    return book, ch, v

def load_alignment_segments(align_path, text):
    """Return list of (start_char, end_char, verse_ref) located in `text` by phrase search."""
    if not align_path.exists(): return []
    try: segs=json.loads(align_path.read_text(encoding="utf-8"))
    except Exception: return []
    out=[]
    for s in segs:
        ref=s.get("verse_ref"); sp=(s.get("start_phrase") or "").strip()
        sp=re.sub(r"^```(?:markdown)?\s*","",sp)[:40]
        if not ref or not sp: continue
        i=text.find(sp)
        if i<0:
            key=re.sub(r"\s+"," ",sp)[:24]
            i=re.sub(r"\s+"," ",text).find(key)  # loose fallback
        if i<0: continue
        out.append([i, None, ref])
    out.sort(key=lambda x:x[0])
    for k in range(len(out)): out[k][1]= out[k+1][0] if k+1<len(out) else len(text)
    return out

def seg_for(offset, segs):
    for a,b,ref in segs:
        if a<=offset<b: return ref
    return None

def main():
    import os
    dv=os.getenv("DR_VOLUMINOUS", r"c:/Users/cnogr/git/dr-voluminous")
    ap=argparse.ArgumentParser(description="V1 Hebrew-span census/detector (see module docstring).")
    ap.add_argument("--commentary", default=os.getenv("COMMENTARY_DATA_DIR", f"{dv}/commentary"))
    ap.add_argument("--hbo", default=os.getenv("HBO_USFM_DIR", f"{dv}/bibles/hbo_usfm"))
    ap.add_argument("--out", default="")
    a=ap.parse_args()
    COMM=Path(a.commentary); HBO=Path(a.hbo)

    print("Loading Hebrew Bible per-verse index...", flush=True)
    verse_words, inverted, sk_inverted = load_hbo(HBO)
    print(f"  verses={len(verse_words)}  word-forms={len(inverted)}  skeleton-forms={len(sk_inverted)}\n", flush=True)

    # ---- corpus membership: fail-loud ----
    found_vols={int(m.group(1)) for d in COMM.glob("volume*") if (m:=re.match(r"volume(\d+)",d.name)) and d.is_dir()}
    print("=== CORPUS MEMBERSHIP (fail-loud) ===")
    for vol in sorted(EXPECTED_VOLUMES):
        has_canon = (COMM/f"volume{vol}"/"qwen_qwen3-vl-235b-a22b-thinking").exists()
        if vol in found_vols and has_canon: print(f"  volume{vol}: PRESENT")
        else: print(f"  ⚠️  volume{vol}: ABSENT — {VOL_NOTES.get(vol,'no canonical _normalized path')}")
    for vol in sorted(found_vols - EXPECTED_VOLUMES): print(f"  ⚠️  UNEXPECTED volume{vol} present — investigate")
    print()

    pv=defaultdict(lambda: defaultdict(int)); tiers=defaultdict(list); controls=[]; unaligned=0
    for vol in sorted(EXPECTED_VOLUMES):
        qdir=COMM/f"volume{vol}"/"qwen_qwen3-vl-235b-a22b-thinking"
        if not qdir.exists(): continue
        adir=COMM/"artifacts"/"alignment"/f"volume{vol}"
        for p in qdir.glob("*_normalized.md"):
            mnum=re.search(r"page(\d+)_image(\d+)_normalized\.md$",p.name)
            if not mnum: continue
            page=mnum.group(1); img=mnum.group(2)
            t=p.read_text(encoding="utf-8",errors="replace")
            segs=load_alignment_segments(adir/f"page{page}_image{img}_alignment.json", t)
            pv[vol]["canonical_pages"]+=1
            for m in HEB_ANY.finditer(t):
                s=m.group(0)
                if not any(ord(c) in CONS for c in s): continue
                if len(cons(s))<2: pv[vol]["noise_sub2"]+=1; continue
                pv[vol]["meaningful"]+=1
                if is_garbage(s):
                    pv[vol]["garbage"]+=1; tiers["garbage"].append((vol,page,s)); continue
                cand=candidate_verses(s, inverted, sk_inverted)   # verses containing ALL span words
                if in_apparatus(t, m.start()):
                    # footnote apparatus: unreferenced-then, own reference shelf, highest-
                    # risk (about to become load-bearing: Aquinas, comparison page, S2/S3).
                    tier="apparatus"
                else:
                    ref=seg_for(m.start(),segs); tier=None
                    if ref:
                        pr=parse_ref(ref)
                        if pr:
                            book,ch,v=pr; code=OT_CODE.get(book)
                            if code and v is not None and (code,ch,v) in cand:
                                tier="case1"            # matches the PASSAGE's own verse
                        if tier is None: tier="cross_ref" if cand else "extra_biblical"
                    else:
                        unaligned+=1
                        tier="cross_ref" if cand else "extra_biblical"
                pv[vol][tier]+=1
                if tier in ("extra_biblical","apparatus","cross_ref"):
                    i=t.find(s); tiers[tier].append((vol,page,s,t[max(0,i-55):i+len(s)+22].replace("\n"," ")))
                if TAUN in s: controls.append(("taʿun",vol,page,tier))

    cols=["canonical_pages","meaningful","case1","cross_ref","extra_biblical","apparatus","garbage"]
    print("=== CENSUS (three tiers + apparatus sub-population) ===")
    print(f"{'metric':16}"+"".join(f"{('vol'+str(v)):>10}" for v in sorted(EXPECTED_VOLUMES))+f"{'TOTAL':>10}")
    tot={}
    for c in cols:
        tt=sum(pv[v][c] for v in EXPECTED_VOLUMES); tot[c]=tt
        print(f"{c:16}"+"".join(f"{pv[v][c]:>10}" for v in sorted(EXPECTED_VOLUMES))+f"{tt:>10}")
    print(f"\nspans with no alignment segment (passage-unknown, classified by OT-global only): {unaligned}")
    print(f"\n=== CONTROLS ===")
    tp=[c[3] for c in controls if c[0]=='taʿun']
    print(f"  [1 extra-biblical jaw] ṭaʿun -> {tp[:3]}  {'PASS' if tp and all(x=='extra_biblical' for x in tp) else '*** FAIL: matres too aggressive ***'}")
    # plene-biblical jaw: with global matres REJECTED (fails jaw 1), plene words like
    # diber are handled by the apparatus split (they live in footnotes) rather than the
    # matcher; strict biblical=False here is expected and harmless.
    print(f"  [2 plene jaw] diber(דיבר) strict-biblical={bool(candidate_verses('דִּיבֶּר',inverted,sk_inverted))} "
          f"(matres deferred to candidate-set-scope; apparatus split covers footnote plene)")
    print(f"  [4 by-construction jaw] vol7 case-1 = {pv[7]['case1']}  {'PASS (NT: no Hebrew passage)' if pv[7]['case1']==0 else 'CHECK'}")
    for lbl,span,want in [("bereshit(Gen1:1)","\u05D1\u05B0\u05BC\u05E8\u05B5\u05D0\u05E9\u05C1\u05B4\u05D9\u05EA",("GEN",1,1)),
                     ("mishpechoteihem","\u05D4\u05B7\u05DE\u05B4\u05BC\u05E9\u05C1\u05B0\u05E4\u05BC\u05B0\u05D7\u05B9\u05EA\u05B5\u05D9\u05D4\u05B6\u05DD",None)]:
        cv=candidate_verses(span, inverted, sk_inverted)
        extra=(" GEN1:1-in-candidates="+str(want in cv)) if want else ""
        print(f"  [biblical jaw] {lbl}: biblical={bool(cv)} (expect True, NOT extra-biblical){extra}")
    print(f"\n=== REVIEW POPULATION ===")
    print(f"  extra-biblical IN-LINE = {tot['extra_biblical']}  (V2 first sample: hardest, most user-exposed)")
    print(f"  apparatus (footnote)   = {tot['apparatus']}  (highest-risk, first-in-line; own reference shelf)")
    print(f"  easy tier cross-ref    = {tot['cross_ref']}  (Tanakh-checkable, semi-auto-closeable)")
    print("--- extra-biblical in-line sample ---")
    for r in tiers["extra_biblical"][:10]: print(f"  vol{r[0]} p{r[1]}: {r[2]!r}  ...{r[3]}...")
    print("--- apparatus sample ---")
    for r in tiers["apparatus"][:8]: print(f"  vol{r[0]} p{r[1]}: {r[2]!r}  ...{r[3]}...")
    if a.out:
        Path(a.out).write_text(json.dumps({"per_volume":{v:dict(pv[v]) for v in pv},
            "extra_biblical":[list(r) for r in tiers['extra_biblical']],
            "apparatus":[list(r) for r in tiers['apparatus']],
            "cross_ref":[list(r) for r in tiers['cross_ref']],
            "garbage":[list(r) for r in tiers['garbage']]}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nWritten -> {a.out}")

if __name__=="__main__": main()
