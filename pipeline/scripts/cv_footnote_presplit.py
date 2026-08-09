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

def presplit(path, upscale=2):
    im=Image.open(path); W,H=im.size
    dark=_dark(im)
    xdiv=find_vertical_divider(dark)
    cols=[(0,xdiv),(xdiv,W)]
    strips=[]
    info={"xdiv":xdiv,"rules":[]}
    for (x0,x1) in cols:
        yr=find_hrule(dark, x0+int((x1-x0)*0.03), x1-int((x1-x0)*0.03))
        info["rules"].append(yr)
        if yr is None: continue                 # no footnotes in this column
        # footnote strip: below the rule to the page bottom (trim a few px past the rule)
        strip=im.crop((x0, yr+6, x1, H)).convert("L")
        # trim trailing all-white rows
        sd=_dark(strip); rows=np.where(sd.sum(axis=1)>sd.shape[1]*3)[0]
        if len(rows): strip=strip.crop((0,0,strip.size[0],int(rows[-1])+8))
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
