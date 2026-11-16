# D-008 — the viewer opens on the page before the citation, and the caption can name a page the citation does not

**Status**: open. Scheduled for 0.3.4 by ruling (Chris, 2026-11-15), as
[§4 of the 0.3.4 scope](../releases/0.3.4.md), alongside
[D-009](D-009-every-user-visible-page-number-is-the-scan-file-page.md).
**Found**: 2026-11-15, from Chris's own use of the public site — the evidence
panel read `Vol 1, p. 106` for Genesis 2:15 beside a viewer labelled page
**105**.
**Affects**: 0.3.0, 0.3.2 and 0.3.3 identically. `frontend/` is byte-identical
from tag `0.3.0` to `release-0.3.3` (`git diff --stat 0.3.0 release-0.3.3 --
frontend/` is empty), so this is **pre-existing on production and is not a
0.3.3 regression**. It rode to prod unfixed with the 0.3.3 ship.
**User-visible**: yes, on the ordinary answer path, with no flag set and no
debug channel open. This is the defect a reader meets first.

## Two mechanisms produce the same symptom

The gallery always renders three pages, `[cited-1, cited, cited+1]`
(`App.tsx` `getGalleryPages`: `startPage = Math.max(1, minPage - 1)`), so the
**first page in the DOM is always the page before the cited one**. Which of the
two defects below is firing is decided by one observable: **was a highlight
rectangle drawn?**

### Branch A — NAVIGATION (the one witnessed)

With `pages.filter(p => p.boxes.length > 0)` empty, or the cited page's image
not yet loaded, the auto-scroll effect **returns before scrolling**. The
container stays at `scrollTop 0` — which is page `cited-1`. The viewer really
does open on the page before the citation.

**Witnessed**: Chris's screenshot, 2026-11-15 — the viewer showed page 105
(Gen 2:10-12) with **no highlight rectangle**, while the panel cited Gen 2:15.
On this branch the caption is telling the truth about where the viewer is; the
*scroll* is what is wrong.

### Branch B — LABEL (mechanism read from code, not witnessed)

`ScanGallery`'s auto-scroll centres the **highlight boxes** in the viewport,
not the top of the cited page, so with a box near the top of 106 a large part
of 105 is on screen. The label is `visiblePage`, chosen by
`IntersectionObserver` as the page with the highest `intersectionRatio`, and
hysteresis then **locks it**: a rival must beat the current page by `0.25`
*absolute ratio* (`maxRatio - currentRatio > 0.25`).

`intersectionRatio` is the fraction of the **element** that is visible, and a
page element is taller than the viewport, so the maximum ratio any page can
attain is `viewportH / pageH` — often under 0.5. The threshold is expressed in
element-fraction; the question being asked is share-of-viewport. **A control
scored in different units from the thing it gates has gated nothing.** Once 105
is current, 106 can lose while holding the highlight: the viewer is on the
cited content and the caption is not.

Both branches can be live at once. Chris can settle it by scrolling: if 106
carries a highlight that was simply off-screen, branch B is also firing.

## Why the two branches must not be collapsed into one fix

They fail in opposite directions. Branch A puts the viewport on a page the
system never claimed; branch B puts a correct viewport under a caption that
contradicts the citation. A fix that only re-centres the scroll leaves the unit
mismatch in place for every page that *does* have boxes, and a fix that only
pins the caption to the cited page leaves the no-boxes citation opening on the
wrong page in silence.

## What the fix has to satisfy (stated in the 0.3.4 scope, repeated here)

- The caption must name what it is computed from, or fall back to the cited
  page when the most-visible page is not the page carrying the highlight. **One
  record must not carry a true and a false statement about one citation.**
- The hysteresis threshold must be expressed in the same unit as the quantity
  it compares — share of the viewport, not fraction of the element.
- The no-boxes path must scroll to the cited page rather than return. A
  citation with no coordinates is still a citation; `scrollTop 0` is a page the
  system never claimed.
- A fixture for **each** branch, asserting the caption against the cited page.

## What this entry does NOT establish

- **Not** that branch B has ever fired in production. Its mechanism is read
  from the code; the screenshot shows branch A. A unit mismatch that is real in
  the source is not the same as an observed wrong caption, and this entry does
  not claim one.
- **Not** a frequency for branch A. How often a cited page arrives with no
  boxes — alignment gaps, a slow image — is unmeasured. The population is every
  citation whose highlight boxes are empty or late, which is wider than the one
  query witnessed.
- **Not** that the page *number* shown is correct once the viewer is on the
  right page. It is not: every number on this screen is a scan-file page, which
  is [D-009](D-009-every-user-visible-page-number-is-the-scan-file-page.md). A
  reader looking at the Genesis 2:15 panel today meets both defects at once,
  and fixing this one alone leaves them on the right scan under the wrong
  printed number.
