"""GLYPH-WITNESS jaw-set — the labeled validation set for the (daylight) CV Hebrew-presence witness,
the only instrument that can close the invisible-Hebrew-loss denominator (the Tesseract census was a
DEAD-END: mixed Heb+Latin lines defeat single AND dual OCR — see HANDOFF stage-2). Assembled BEFORE
the witness is designed so it opens against a ready test set, and its thresholds get committed only
after they pass these jaws.

Labels are IMAGE-VERIFIED (scans read directly): 1 = Hebrew SCRIPT present, 0 = none. The critical jaw
is p674 — its "Hebrew" is TRANSLITERATION in Latin letters (`Maacolot Asurot`, `Pirush`), the exact
false-positive that killed the Tesseract census. A witness must return 0 on it.
"""
# page -> (label, note). Grows as more pages are image-verified.
JAWS = {
    # KNOWN-POSITIVE (Hebrew script present, verified)
    473: (1, "סגר עליהם"), 546: (1, "כי יהיה"), 336: (1, "הקדשה / אנשי מקמה"),
    692: (1, "וכי / כהות"), 150: (1, "הניחח / אל לבו"), 550: (1, "שורש"),
    # KNOWN-NEGATIVE (no Hebrew script, verified)
    100: (0, "all Latin/English citations"), 702: (0, "all rabbinic-Latin"),
    343: (0, "Nunc / Euterpe — Latin"), 757: (0, "Var. Hist. / Pagninus — Latin"),
    # THE TRAP (named false-positive jaw): transliterated Hebrew in LATIN letters
    674: (0, "TRAP: Maacolot Asurot / Pirush are TRANSLITERATIONS in Latin letters, not Hebrew script"),
}
TRAP_PAGE = 674

def score(predictions):
    """predictions: {page: 0/1}. Returns precision/recall over the jaws + explicit trap verdict."""
    tp = fp = tn = fn = 0; misses = []
    for pg, (label, _note) in JAWS.items():
        pred = predictions.get(pg)
        if pred is None: continue
        if label == 1 and pred == 1: tp += 1
        elif label == 1 and pred == 0: fn += 1; misses.append((pg, "MISSED-Hebrew"))
        elif label == 0 and pred == 1: fp += 1; misses.append((pg, "FALSE-POSITIVE"))
        else: tn += 1
    P = tp/(tp+fp) if (tp+fp) else 1.0; R = tp/(tp+fn) if (tp+fn) else 1.0
    trap_ok = predictions.get(TRAP_PAGE) == 0
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn, "precision": round(P, 3), "recall": round(R, 3),
            "trap_p674_passed": trap_ok, "misses": misses,
            "verdict": "PASS" if (not misses and trap_ok) else "FAIL"}

if __name__ == "__main__":
    import sys
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    pos = sum(1 for l, _ in JAWS.values() if l == 1); neg = sum(1 for l, _ in JAWS.values() if l == 0)
    print(f"glyph-witness jaws: {len(JAWS)} labeled pages ({pos} Hebrew, {neg} none incl. the p674 trap)")
    # harness proof: a perfect oracle passes; a naive 'any-non-Latin-char' witness FAILS the trap
    print("  perfect oracle:", score({pg: l for pg, (l, _) in JAWS.items()})["verdict"], "(must PASS)")
    print("  trap check: a witness that says p674=1 (Hebrew) ->",
          score({**{pg: l for pg, (l, _) in JAWS.items()}, 674: 1})["verdict"], "(must FAIL)")
