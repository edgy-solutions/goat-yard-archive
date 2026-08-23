"""per_note_extract born tested — pre-segmentation makes collapse structurally impossible (one crop per
note-start -> exactly count notes), and falls back to whole-strip when the CV geometry isn't confident.
Reader injected (no VLM). Run: python test_per_note.py"""
import numpy as np
from PIL import Image
import per_note_extract as PN
import assembler as A

PROFILE = A.load_profile  # placeholder; tests use a minimal dict

def _confident_strip():
    # 3 note-starts (narrow marker + gap + text), 2 continuations — the test_hanging_indent synthetic
    H, W = 300, 400
    a = np.full((H, W), 255, np.uint8)
    def tb(y, x0, x1): a[y+8:y+34, x0:x1] = 0
    def mk(y, x): a[y+2:y+18, x:x+12] = 0
    for r in (12, 128, 244): mk(r, 12); tb(r, 60, 380)
    for r in (70, 186): tb(r, 12, 380)
    return Image.fromarray(a)

def _flat_strip():
    a = np.full((120, 400), 255, np.uint8); a[20:46, 12:380] = 0; a[70:96, 12:380] = 0  # flowing, no markers
    return Image.fromarray(a)

MINI = {"transcription": {"model": "gemma4:31b", "num_ctx": 4096}}

def test_per_note_cannot_collapse():
    # a stub reader that returns text for each crop -> exactly one note per CV note-start (=3)
    notes, mode = PN.per_note_read(_confident_strip(), "x", MINI, "gemma4:31b",
                                   reader=lambda crop: "some footnote text")
    assert mode == "per-note" and len(notes) == 3        # structurally one-per-start; no fold possible

def test_per_note_markers_are_canonical_sequence():
    notes, _ = PN.per_note_read(_confident_strip(), "x", MINI, "gemma4:31b", reader=lambda c: "t")
    assert [n["marker"] for n in notes] == ["[^1]", "[^2]", "[^3]"]

def test_empty_crop_flagged_starved_for_strip_floor():
    # a reader that returns "" -> that note is FLAGGED starved (kept, index-aligned with strip), NOT
    # dropped — reconcile() takes the strip-floor reading for it. (Guard change: never lose the slot.)
    seq = iter(["note a", "", "note c"])
    notes, mode = PN.per_note_read(_confident_strip(), "x", MINI, "gemma4:31b", reader=lambda c: next(seq))
    assert len(notes) == 3                                        # slot preserved for reconcile alignment
    assert notes[1]["starved"] is True and notes[1]["text"] == ""
    assert mode == "per-note-guarded"

def test_whitespace_normalized():
    notes, _ = PN.per_note_read(_confident_strip(), "x", MINI, "gemma4:31b",
                                reader=lambda c: "  a  Palestina\n illustrata  ")
    assert notes[0]["text"] == "a Palestina illustrata"

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed"); raise SystemExit(1 if f else 0)
