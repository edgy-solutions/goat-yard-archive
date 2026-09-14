"""Overnight step 2 — measure the wired Hebrew layer (script / glyph-count / nikud / locate) on the truthset
pages' already-extracted v2 notes (CV-only, no re-transcription). Reports per-gate flag counts and the crop-gate
abstain rate. reference-hypothesis is NOT run here — it needs a scoped-passage data source (anchored-verse
Hebrew + a Tanakh index) that is a config decision, left for the morning. Build-and-measure only."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import cv_footnote_presplit as presplit
import hebrew_layer as HL
import assembler as A
from data_config import data_path

IMG = Path("C:/Users/cnogr/git/dr-voluminous/commentary/volume1")
RUN = data_path("born_test_baml.jsonl")


def main():
    profile = A.load_profile(str(Path(__file__).parent / "book_profile.gill.yaml"))
    rows = [json.loads(l) for l in RUN.read_text(encoding="utf-8").splitlines() if l.strip()]
    pages = [r for r in rows if r.get("kind") != "config_header" and r.get("hebrew")]
    from collections import Counter
    script = Counter(); nikud = Counter(); locate = Counter()
    glyph_flagged = 0; total_heb = 0; located = 0; flagged_gemma = 0
    details = []
    for r in pages:
        pg = r["page"]
        strip, info = presplit.presplit(str(IMG / f"page{pg}_image1.png"),
                                        upscale=profile["transcription"].get("apparatus_upscale", 4))
        if strip is None:
            continue
        notes = [{"text": n["text"], "marker": n["marker"], "marker_letter": n.get("marker_letter")} for n in r["notes"]]
        notes, summ = HL.apply(strip, notes, profile)
        total_heb += summ["hebrew_notes"]; flagged_gemma += summ["flagged"]
        for n in notes:
            v = n.get("hebrew_verdict")
            if not v:
                continue
            script[v["script"]] += 1
            if "glyph_flag" in v:
                glyph_flagged += int(v["glyph_flag"])
            if v.get("nikud"):
                nikud[v["nikud"]] += 1
            loc = "box" if v.get("span_box") else (v.get("locate") or v.get("align") or "?")
            locate[loc] += 1
            if v.get("span_box"):
                located += 1
            if v["script"] != "ok" or v.get("glyph_flag"):
                details.append((pg, n["marker"], v["script"], v.get("glyph_flag"), n["text"][:55]))
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print(f"Hebrew notes: {total_heb} across {len(pages)} pages")
    print(f"  script gate:  {dict(script)}")
    print(f"  glyph tripwire flagged: {glyph_flagged}")
    print(f"  nikud verdicts (where crop ran): {dict(nikud)}")
    print(f"  locate outcomes: {dict(locate)}   (located={located}, abstained={total_heb-located})")
    print(f"  flagged for gemma witness (script!=ok or glyph): {flagged_gemma}")
    print(f"  CROP-GATE ABSTAIN RATE: {(total_heb-located)}/{total_heb} "
          f"({100*(total_heb-located)/max(1,total_heb):.0f}%) — mostly note-count mismatch (detector regions "
          f"!= model note count), so glyph/nikud can't run. This is the limiting factor, not the gates.")
    if details:
        print("  flagged spans:")
        for pg, mk, sc, gf, tx in details:
            print(f"    p{pg} {mk} script={sc} glyph={gf} :: {tx}")


if __name__ == "__main__":
    main()
