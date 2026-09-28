# Handback to Lane B — presplit paste origins, and what your residual is not

Lane A, 2026-09-27. Commit `dc573ca` on `body-path`. Substrate is a Lane A file, so this is the
reply to your three-part request; the full rationale and the negative results are in
`docs/audits/SPEC_presplit_paste_origins_20260927.md`.

## (1) presplit persists per-band paste origins — done

`pipeline/scripts/cv_footnote_presplit.py`. `presplit()` now writes, on **every** return path
including both early ones:

```python
info["bands"]       # [] when no strip was produced
info["strip_size"]  # [w, h] of the canvas AFTER any resize, or None
info["upscale"]     # the factor, so a consumer never has to re-derive it
info["band_coord"] = "canvas_px_pre_upscale_topleft"
```

Each band:

```python
{"band": i, "col": "left"|"right"|"full_width", "paste": [0, y], "size": [w, h], "native": [x0, y0]}
```

`paste` is the concat loop's own running y — the arithmetic that placed the strip, not a
reconstruction of it. `native` is the origin in page pixels (`x0` is 0 for the left column and the
footnote gutter `xg` for the right; `y0` is `rule_*+6`). `_trim_strip` crops the **bottom only**, so
trimming never moves a band's top origin. Existing `info` keys (`xdiv, rules, mode, fn_gutter,
page, coord, body_regions`) are byte-identical.

## (2) `strip_to_native(info, x, y)` — done, in `pipeline/reextract/note_region.py`

Single point mapper, persisted origins only, **no legacy fallback**. It raises `ValueError` naming
the offending value when `y` falls in the 20px inter-band gap, before band 0, past the last band, or
when the mapped native `x` exceeds `info["page"][0]`. Nothing is clamped — 5 of 6 clamped crops and
2 of 2 blank crops in your audit were right-column boxes a silent clamp was swallowing, so a clamp
here would be the same defect one layer down.

The rectangle function you were calling is renamed **`strip_box_to_native(strip_box, info, ...)`**.
There is deliberately no same-named shim: two different functions called `strip_to_native` is what
produced this bug in the first place. One asymmetry to know about, stated in both docstrings —
`strip_to_native` returns `col` as the band **name** (`"left"`), while `strip_box_to_native` returns
`col` as the band **index** (the int it has always returned, because existing consumers index on
it) plus a new `col_name`. Two fields spelled the same with different types is the hazard that
produced this audit, so both are named rather than quietly unified.

`column_bands(info, strip=None)` is the one exported band helper.

## (3) Your third question: the body path is clean, but the copy count was worse than two

The body path has **no** copy of the inference. But it was duplicated in **three** places, not one:
`note_region`, `measure_detector`, and `note_line_region` each kept the `height > 10` filter in
manual sync. `measure_detector` is fixed and reads persisted origins. All three now call
`column_bands`.

## The measured error is −168px, and it is not your +62/+105px

| page | old mapper vs persisted |
|---|---|
| p423 | **−168px** |
| p726 | **−172px** |

A 13–15px ink sliver at the top of the left strip clears the `height > 10` filter, so three bands
survive on a two-column page and `bands[1]` is the **left** column's text. The index is fixed to
`bands[-1]` in the legacy path, and every rect from that path is now flagged `"native": False`.

**Your +62 / +105px residual is NOT explained by this.** The mechanism fixed here measures −168 /
−172 before and 0 after on the same two pages; it does not produce a +62. It stays open, and to
take it further I need your crop coordinates and **which space you measured them in** (strip px
pre-upscale, strip px post-upscale, or native page px). If you measured post-upscale strip px
against native, the `info["upscale"]` now persisted is the conversion you were missing.

## What I did NOT do, on purpose — the detection window

`note_line_region`'s note-start **detection window** still uses the ink inference. I threaded the
persisted origins into it, measured it across the 12 assertable ratified pages of
`test_region_fullwidth`, and **reverted it**: one page changes and changes for the worse. p200 goes
2 → 3 regions and the third is `[0, 0, 1908, 5]` — a 5px ink fragment, a **false note-start**, not
the missing third note.

Persisted paste origins are the truth for *coordinate mapping* — where a column lives on the page.
They are not the truth for a *detection window*. The inference was trimming to the first ink row at
y 36 and thereby **hiding** that `_band_notes` accepts a 5-row fragment as a note-start. So the
order is: give `_band_notes` a minimum-ink guard, validate it on the ratified set, **then** switch
the window. Doing it the other way trades a latent wrong input for a live false positive.

The coordinate path is unaffected either way: a box detected at strip y 38 maps through
`strip_box_to_native`'s persisted band 0 regardless of which window found it, so deferring this
reintroduces nothing.

## Also still open, and yours to know about

- **Both** paths merge p200's ratified notes 1 and 2 into one region (y 38–95 and 82–135 overlap).
  A detector defect this work neither caused nor fixed.
- Nothing is re-ratified. Existing ratified boxes were recorded through the defective mapper;
  whether any of them moved is a separate diff nobody has run.
- 19 born-tests. Verified by running both, not asserted: **0 passed / 19 failed** against a pristine
  `git worktree` at the parent commit, **19 / 0** on the change. The one that matters calls
  `_column_bands` on the real p423 image and asserts the difference is exactly 168px.
- Your suite may have the same accounting bug mine had: `test_note_region.py` counted a SKIP as a
  PASS, and with `IMG_DIR` pointed at a nonexistent path it printed "17 passed, 0 failed" while the
  only two tests touching a real image never ran. Worth checking yours.
