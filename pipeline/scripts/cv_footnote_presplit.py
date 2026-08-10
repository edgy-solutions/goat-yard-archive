"""CV presplit (deterministic, numpy+PIL only) — the layout stage the pipeline never had.
Layout (verified): center vertical rule -> 2 columns; within each column a horizontal rule
separates body (above) from footnotes (below). Footnote strip = below-rule crop per column;
concat left-strip above right-strip -> linear reading order; 2x upscale for the model.
"""
import numpy as np
from PIL import Image

def _dark(im): return 255.0 - np.asarray(im.convert("L"), dtype=np.float32)

def find_vertical_divider(dark):
    H,W=dark.shape
    col=dark[int(H*0.15):int(H*0.6)].sum(axis=0)      # body band, avoid header/footnotes
    band=slice(int(W*0.40),int(W*0.60))
    x=int(np.argmin(col[band]))+int(W*0.40)           # gutter = min-darkness column near centre
    return x

def _max_dark_run(rowdark, thr=70):
    d=rowdark>thr; best=cur=0
    for v in d:
        cur=cur+1 if v else 0
        if cur>best: best=cur
    return best

def find_hrule(dark, x0, x1, floor=350):
    """Row index of the body/footnote separator rule within column [x0,x1).
    The rule is discriminated by a CONTINUOUS dark run far longer than any text run
    (text breaks at letter/word gaps ~<200px); footnote separators are often SHORT
    partial-width rules, so the test is an absolute run floor, not a column-width %.
    Returns the TOPMOST qualifying row in the lower band (= body/footnote boundary)."""
    H=dark.shape[0]; colw=x1-x0
    floor=max(floor, int(0.18*colw))            # scale-safe floor, still << column width
    for y in range(int(H*0.45), H):
        if _max_dark_run(dark[y, x0:x1])>floor:
            return y
    return None

def footnote_is_full_width(dark, xdiv, y_top):
    """Stage-1 REROUTE detector (FOSSIL: p546 `Pagnin nus`): a full-width footnote (spans both
    columns, as the 1766 printer occasionally sets) FILLS the gutter in the footnote region where a
    two-column page has a gap. Column-splitting such a page slices a note mid-word. Deterministic,
    image-level (no wasted transcription). Compares gutter darkness to the column-centre darkness in
    the footnote region only."""
    H, W = dark.shape
    if y_top is None or y_top >= H - 10: return False
    reg = dark[y_top:H]
    col = reg.sum(axis=0)
    gut = col[max(0, xdiv-20):xdiv+20].mean()
    left = col[int(W*0.18):int(W*0.34)].mean(); right = col[int(W*0.66):int(W*0.82)].mean()
    colmean = (left + right) / 2.0
    return colmean > 1.0 and gut > 0.45 * colmean     # gutter not a clear gap -> text crosses it

def _trim_strip(strip):
    sd=_dark(strip); rows=np.where(sd.sum(axis=1)>sd.shape[1]*3)[0]
    return strip.crop((0,0,strip.size[0],int(rows[-1])+8)) if len(rows) else strip

def presplit(path, upscale=2, allow_full_width=False):
    im=Image.open(path); W,H=im.size
    dark=_dark(im)
    xdiv=find_vertical_divider(dark)
    info={"xdiv":xdiv,"rules":[],"mode":"two_column"}
    # find the topmost rule across the two columns (= footnote region top)
    rule_l=find_hrule(dark, int(W*0.03), xdiv-int(W*0.02))
    rule_r=find_hrule(dark, xdiv+int(W*0.02), W-int(W*0.03))
    info["rules"]=[rule_l,rule_r]
    y_top=min([r for r in (rule_l,rule_r) if r is not None], default=None)
    # STAGE-1 REROUTE (GATED OFF by default): geometric full-width detection is UNSOUND — the
    # body-gutter isn't the footnote-gutter, so it false-positives (p692: two-column worked, full-width
    # regressed it 4->3 notes + γ). Needs the TEXT-SIGNAL detector (reroute only when two-column
    # produces a broken word at the seam). p692 is the guard fixture. See HANDOFF.
    if allow_full_width and y_top is not None and footnote_is_full_width(dark, xdiv, y_top):
        info["mode"]="full_width"
        strip=_trim_strip(im.crop((0, y_top+6, W, H)).convert("L"))
        if upscale and upscale!=1:
            strip=strip.resize((strip.size[0]*upscale, strip.size[1]*upscale), Image.LANCZOS)
        return strip, info
    cols=[(0,xdiv),(xdiv,W)]
    strips=[]
    for i,(x0,x1) in enumerate(cols):
        yr=(rule_l,rule_r)[i]
        if yr is None: continue                 # no footnotes in this column
        strip=_trim_strip(im.crop((x0, yr+6, x1, H)).convert("L"))
        strips.append(strip)
    if not strips: return None, info
    # vertical concat (left strip above right strip) = linear reading order
    tw=max(s.size[0] for s in strips); th=sum(s.size[1] for s in strips)+20*(len(strips)-1)
    canvas=Image.new("L",(tw,th),255); y=0
    for s in strips:
        canvas.paste(s,(0,y)); y+=s.size[1]+20
    if upscale and upscale!=1:
        canvas=canvas.resize((canvas.size[0]*upscale, canvas.size[1]*upscale), Image.LANCZOS)
    return canvas, info

if __name__=="__main__":
    import sys
    p=sys.argv[1] if len(sys.argv)>1 else r"c:/Users/cnogr/git/dr-voluminous/commentary/volume1/page100_image1.png"
    out=sys.argv[2] if len(sys.argv)>2 else r"C:/Users/cnogr/AppData/Local/Temp/claude/c--Users-cnogr-git-goat-yard-archive/512cb290-7e98-4592-b846-6c227fe581d1/scratchpad/p100_footnotes.png"
    strip,info=presplit(p, upscale=2)
    print("info:",info)
    if strip: strip.save(out); print("saved footnote strip",out,strip.size)
    else: print("no footnote strip detected")
