# Spec — persist presplit paste origins; retire the ink-band inference

Lane A substrate work, answering Lane B's request of 2026-09-27
(`audits/hebrew_rulings_report_20260927.md`). Written before implementation.

## What I measured first (do not re-derive; do not trust the request's numbers over these)

`note_region._column_bands(strip)` recovers y-bands by finding blank runs of ≥ 16 rows of
**ink**. `strip_to_native` then filters `height > 10` and takes `bands[1][0]` as the right
column's start. Measured today at `upscale=1`, reproducing presplit's own paste arithmetic:

| page | rules (l, r) | xg | trimmed strip heights | **true paste origins** | ink bands after filter | `bands[1][0]` | error |
|---|---|---|---|---|---|---|---|
| 423 | 4515, 4524 | 1538 | [183, 233] | **[0, 203]** | (0,13), (35,177), (203,436) | 35 | **−168 px** |
| 726 | 4508, 4489 | 1960 | [188, 206] | **[0, 208]** | (0,15), (36,187), (208,414) | 36 | **−172 px** |

Three facts follow, and they matter more than the ones in the request:

1. **The index bug is confirmed.** Both pages yield **three** surviving bands, because a thin
   ink sliver at the very top of the left strip (13 px / 15 px tall — rule remnant or the first
   line's ascenders, separated from the text band by a blank run) clears the `> 10` filter. So
   `bands[1]` is the *left column's text*, and the right column is `bands[-1]`. "3-band strips"
   is not an exotic case; it is the ordinary case on these pages.
2. **The true right paste origin is exactly `left_trimmed_height + 20`** — 203 and 208 — and
   `bands[-1][0]` happens to equal it on both pages. It equals it *by luck*: it is the first ink
   row of the right strip, and it coincides only because the right strip's first line starts at
   its very top. Nothing guarantees that, which is why the origin must be **persisted, not
   inferred**, even though picking `bands[-1]` would score 2/2 here.
3. **The error's sign and size do not match the request.** The request reports a residual of
   **+62 / +105 px** after an index fix. The mechanism above is **−168 / −172 px** before any
   fix and **0 px** after. So the request's residual has a *different* cause and is not
   explained by this. Do not claim it is fixed. Record it as still open, with these numbers, for
   Lane B to reconcile against their own crop coordinates.

`_trim_strip` crops the **bottom only** (`crop((0, 0, w, rows[-1] + 8))`), so a band's top origin
is unaffected by trimming. Confirmed by reading it; state it in the docstring so nobody re-checks.

## The inference IS duplicated (Lane B's item 3: answer is yes, three copies)

- `pipeline/reextract/note_region.py:39` — inside `strip_to_native`.
- `pipeline/reextract/note_line_region.py:70` — its own `>10` filter, whose docstring says it is
  kept deliberately in sync: *"`strip_to_native` filters (height > 10) so a band index means the
  same thing on both sides."* The off-by-one therefore propagates identically here.
- `pipeline/reextract/measure_detector.py:31` — a third `>10` filter.

All three must read the persisted origins. "Kept in sync" is how one bug became three.

## Changes

### 1. `pipeline/scripts/cv_footnote_presplit.py` — persist what only presplit knows

`presplit()` computes each column strip, trims it, and pastes it at a running y. Record that
arithmetic in `info` instead of discarding it. Add, in **every** return path including the two
early ones:

```python
info["upscale"] = upscale
info["strip_size"] = list(canvas.size) if canvas is not None else None   # AFTER any resize
info["bands"] = [ ... ]      # see below; [] when no strip was produced
```

Each band, in **canvas coordinates before upscaling** (the loop's own `y`), is:

```python
{"band": 0, "col": "left",           # "left" | "right" | "full_width"
 "paste": [0, 0],                    # band top-left in the pre-upscale canvas
 "size": [w, h],                     # the TRIMMED strip's size
 "native": [0, rule_l + 6]}          # native page coords of this band's (0, 0)
```

- left column: `native = [0, rule_l + 6]`; right column: `native = [xg, rule_r + 6]`;
  `full_width` mode: one band, `col: "full_width"`, `native = [0, y_top + 6]`.
- `paste` y is the running `y` in the concat loop — i.e. `sum(previous trimmed heights) + 20 * i`.
  Take it from the loop, do not recompute it.
- Keep the existing keys byte-identical. `xdiv`, `rules`, `mode`, `fn_gutter`, `page`, `coord`,
  `body_regions` must not change.
- Add `"band_coord": "canvas_px_pre_upscale_topleft"` so the space is named in the data, matching
  how `coord` already names the native convention.

### 2. `pipeline/reextract/note_region.py` — one mapper, persisted origins, fail loud

Add the single point mapper Lane B asked for:

```python
def strip_to_native(info, x, y):
    """Map ONE strip point to native page coords using presplit's persisted paste origins."""
    -> {"x": int, "y": int, "col": str, "band": int}
```

This is a **new signature on the existing name**, so rename the current rectangle function to
`strip_box_to_native(strip_box, info, column_bands=None)` and update its four call sites. Do not
keep a same-named shim: two functions called `strip_to_native` with different meanings is the
condition that produced this bug.

Rules for both:

- Prefer `info["bands"]`. Select the band containing `y` by `paste[1] <= y < paste[1] + size[1]`,
  scaling `paste`/`size` by `info["upscale"]` when it is not 1.
- **A y in the 20 px gap between bands belongs to no band.** Raise `ValueError` naming the y and
  the two bands. It is not clamped to either neighbour — that is the silent mis-placement this
  work removes.
- **A y past the last band** likewise raises. So does a strip point when `info["bands"]` is `[]`.
- When `info` has no `"bands"` key at all (an older `info`), fall back to the ink-band inference
  **and** set `"native": False` on every returned rect, as the module docstring already promises.
  Never return an inferred position marked as native.
- Fix the index in the fallback path: the right column is the **last** surviving band, not
  `bands[1]`. Leave the `> 10` filter as it is — the sliver is real ink and dropping it by raising
  the threshold is a second guess layered on the first.
- **Lane B item 3 — clamping must fail loud.** `xg + x1` can exceed `info["page"][0]`. Today it is
  silently clamped. Instead raise `ValueError` naming the computed x, the page width, the band, and
  the source strip box. 5 of 6 clamped crops and 2 of 2 blank crops in Lane B's audit are
  right-column; a clamp that says nothing is why those looked like crop bugs rather than a
  coordinate bug.

### 3. `note_line_region.py:70` and `measure_detector.py:31` — read the origins

Replace each local `>10` filter with a call to a single exported helper in `note_region`:

```python
def column_bands(info, strip=None):
    """Band y-ranges for this strip, from info["bands"] when present. `strip` is required ONLY
    for the legacy inference path and its absence there is an error, not an empty list."""
```

Returns `[(y0, y1)]` in the strip's own (post-upscale) space so existing band-index logic keeps
working. `note_line_region`'s docstring claim about staying in sync with `strip_to_native`'s
filter becomes true by construction; rewrite that sentence to say so.

## Born-tests — `pipeline/reextract/test_note_region.py`

Every new test must fail on `HEAD` before the change. Demonstrate that, do not assert it.

Offline/synthetic (no page images needed):

1. `info["bands"]` present → a left-column point maps to `rule_l + 6 + y`, col `left`, band 0.
2. A right-column point maps to `xg + x`, `rule_r + 6 + (y - paste_y)`, col `right`.
3. **The regression this exists for:** an `info` whose bands are the p423 shape
   (`paste` 0 and 203, sliver band present) maps a right-column y to the **203**-based origin.
   Assert the native y explicitly, and assert it differs from the `bands[1][0]`-based answer by
   168 px, so the test names the defect rather than just the fix.
4. A y inside the 20 px gap raises `ValueError` mentioning both band indices.
5. A y past the last band raises.
6. `x` that maps past `info["page"][0]` raises, and the message contains the page width.
7. `upscale=2` bands: a point at strip y = 2 × paste_y maps to the same native y as upscale 1.
8. `full_width` mode: one band, col `full_width`, origin `y_top + 6`.
9. An `info` with **no** `"bands"` key returns rects with `native: False` and does not raise.
10. `column_bands(info)` with no strip works when bands are persisted, and raises when they are
    not and no strip was given.
11. The existing four `test_note_region.py` cases must still pass against
    `strip_box_to_native`, with their call sites renamed and nothing else about them changed.

Against real pages (`c:/Users/cnogr/git/dr-voluminous/commentary/volume1/page{423,726}_image1.png`,
`upscale=1`, guard with a skip when the private repo is absent):

12. `presplit` records `bands` whose `paste` y values are `[0, 203]` on p423 and `[0, 208]` on
    p726, and whose `native` y values are `[4521, 4530]` and `[4514, 4495]` respectively
    (`rule + 6`).
13. `strip_to_native(info, x, y)` for a y in the right band of each page returns a native y in
    `[rule_r + 6, rule_r + 6 + right_height]`, and for p423 the answer is **168 px** below what
    the pre-change code returned for the same input.

Use the main checkout's interpreter — `C:/Users/cnogr/git/goat-yard-archive/.venv/Scripts/python.exe`
— because the `goatyard-laneA` venv has no Pillow. Repo convention is a plain script with a
`__main__` runner; pytest is not in the venv.

## Constraints

- **No body bytes are touched.** This is navigation metadata only. Nothing here rewrites a `.md`
  or a stored transcription.
- No network, no model call, no GPU endpoint. If any instinct says to call a model, stop.
- Do not edit `evals/**` — an eval arm is running against that tree.
- Do not `git add -A`. Stage named paths only. Do not commit; leave the tree dirty and report.
- Do not change `presplit`'s existing `info` keys or its return contract `(strip, info)`.

## What this does NOT solve (carry into the commit message)

- It does not explain Lane B's **+62 / +105 px** residual. The mechanism fixed here is −168 / −172
  before and 0 after, on the same two pages. That residual is still open and needs Lane B's crop
  coordinates and the space they were measured in.
- It does not re-ratify anything. Existing ratified boxes were recorded through the defective
  mapper; whether any of them moved is a separate diff, not part of this change.
- It does not validate the right column's *x* origin against ratified positions — only that an
  out-of-page x now raises instead of clamping.
