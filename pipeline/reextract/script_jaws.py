"""Jaw set for the script-presence probe battery (Build 1) — per-script VERIFIED labels (from image
reads + the blind-validator pass). Positives = Hebrew-script present; negatives = Latin-only; the p674
TRAP = transliteration in Latin letters (must read hebrew=0); the WORN-glyph pages (חח-class) = Hebrew
present but transcription-hard, the case that decides everything: if presence-detection survives where
transcription dies, the correlated-omission tail shrinks; if it fails there too, the CV glyph-witness
stays irreplaceable. Grows as more pages are verified."""

# page -> labels. hebrew/arabic = script present (verified). worn = transcription failed the glyph.
JAWS = {
    # Hebrew-present (verified)
    473: {"hebrew": 1, "note": "סגר עליהם"}, 546: {"hebrew": 1}, 336: {"hebrew": 1},
    692: {"hebrew": 1}, 150: {"hebrew": 1}, 550: {"hebrew": 1}, 109: {"hebrew": 1},
    119: {"hebrew": 1}, 188: {"hebrew": 1}, 252: {"hebrew": 1}, 286: {"hebrew": 1},
    292: {"hebrew": 1}, 301: {"hebrew": 1}, 379: {"hebrew": 1}, 385: {"hebrew": 1},
    402: {"hebrew": 1}, 520: {"hebrew": 1}, 924: {"hebrew": 1},
    # worn-glyph: Hebrew present, transcription died on the glyph (the decisive case)
    619: {"hebrew": 1, "worn": True, "note": "חח"}, 831: {"hebrew": 1, "worn": True, "note": "לדרתיכם"},
    # Hebrew-absent (Latin-only, verified)
    100: {"hebrew": 0}, 702: {"hebrew": 0}, 343: {"hebrew": 0}, 757: {"hebrew": 0},
    # the TRAP: transliterated Hebrew in Latin letters -> hebrew MUST read 0
    674: {"hebrew": 0, "trap": True, "note": "Maacolot Asurot / Pirush — transliteration, not script"},
    # Arabic present, Hebrew absent
    458: {"hebrew": 0, "arabic": 1, "note": "Arabic word before 'cruda'"},
}
TRAP = [pg for pg, m in JAWS.items() if m.get("trap")]
WORN = [pg for pg, m in JAWS.items() if m.get("worn")]
