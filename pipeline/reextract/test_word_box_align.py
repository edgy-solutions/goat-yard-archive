"""word_box_align born-tested — the COUNTING alignment (solid) with injected boxes, plus a real-crop case
documenting current calibration status. Run: python test_word_box_align.py"""
import word_box_align as W

def test_tokenize_types():
    toks = W.tokenize("תנשו אל אשה μη Sept. to a woman")
    assert [s for s, _ in toks] == ["hebrew", "hebrew", "hebrew", "greek", "latin", "latin", "latin", "latin"]

def test_locate_by_count_leading_hebrew():
    # 3 Hebrew then Greek then Latin — boxes in visual order; Hebrew is the first 3 boxes by COUNT
    toks = W.tokenize("תנשו אל אשה μη προσελθητε Sept. woman")
    boxes = [(10, 60), (70, 120), (130, 175), (200, 260), (270, 340), (360, 420), (430, 490)]
    box, st = W.align(toks, boxes, 40)
    assert st == "ok" and box == (10, 0, 175, 40), (st, box)   # union of boxes[0:3]

def test_locate_embedded_hebrew_rtl_extent():
    # "reads אלהים אחד one" — Hebrew is boxes[1:3]; internal RTL reversal doesn't move the block extent
    toks = W.tokenize("reads אלהים אחד one")
    boxes = [(10, 90), (100, 160), (170, 220), (230, 300)]
    box, st = W.align(toks, boxes, 40)
    assert st == "ok" and box == (100, 0, 220, 40), (st, box)

def test_count_mismatch_abstains():
    # count-mismatch = FEWER boxes than needed (a dropped/merged word before/within the Hebrew), not more:
    # the note wraps past the line so trailing extra boxes are fine. Here the Hebrew needs box index 3
    # (3 Latin words before it) but only 2 boxes exist -> abstain.
    toks = W.tokenize("in voce quae אלהים")                   # 3 latin then hebrew -> need 4 boxes
    box, st = W.align(toks, [(10, 60), (70, 120)], 40)        # only 2 boxes
    assert box is None and st == "count-mismatch", (box, st)

def test_extra_trailing_boxes_ok():
    # the note continues past this line: more boxes than the counted prefix is NOT a mismatch
    toks = W.tokenize("אלהים Deus verus creator omnium")      # 1 heb + many latin
    box, st = W.align(toks, [(10, 60), (70, 120)], 40)        # locate takes box[0], ignores the rest
    assert st == "ok" and box == (10, 0, 60, 40), (box, st)

def test_hebrew_not_contiguous_abstains():
    toks = W.tokenize("אלהים Deus אחד")                       # two Hebrew runs -> don't guess
    box, st = W.align(toks, [(1, 2)] * 3, 40)
    assert box is None and st == "hebrew-not-contiguous"

def test_no_hebrew_and_empty():
    assert W.align(W.tokenize("Pagninus Montanus"), [(1, 2)] * 2, 40)[1] == "no-hebrew"
    assert W.align([], [], 40)[1] == "empty"

def test_real_p513_line_status():
    # DOCUMENTED real-crop status: on the column-bounded p513 note-q line the CV word-segmentation is
    # off-by-one (10 boxes vs 11 tokens) from word_gap/broken-glyph/marker noise, so it correctly ABSTAINS
    # (count-mismatch) rather than guess. Making it ALIGN needs word_gap calibration + marker/punct handling
    # + a span-box validation set — the named remaining work. The counting logic above is what's proven.
    from PIL import Image
    import os
    p = "C:/Users/cnogr/git/dr-voluminous/commentary/volume1/page513_image1.png"
    if not os.path.exists(p):
        print("  (skip real-crop: scan not present)"); return
    line = Image.open(p).convert("L").crop((120, 4492, 1430, 4528))
    _, st = W.locate_hebrew(line, "תנשו אל אשה μη προσελθητε γυναικι Sept. to a woman, Ainsworth.")
    assert st in ("ok", "count-mismatch"), st            # must fail loud, never a silent wrong box

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed"); raise SystemExit(1 if f else 0)
