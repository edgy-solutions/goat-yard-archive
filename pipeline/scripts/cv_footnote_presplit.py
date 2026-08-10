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

def find_footnote_gutter(dark, y_top):
    """The FOOTNOTE region's OWN gutter (NOT the body gutter — that was the stage-1 unsoundness).
    Returns (x, depth): x = deepest-gap column in the footnote region; depth = how empty it is vs the
    column centres (1=clean gap→two-column, <=0=filled/no gutter→full-width note spanning both cols).
    Measured separator: p546 full-width = -1.38; every two-column page = 0.57..0.94."""
    H, W = dark.shape
    reg = dark[y_top:H]; col = reg.sum(axis=0)
    b0, b1 = int(W*0.33), int(W*0.67)
    xg = int(np.argmin(col[b0:b1])) + b0
    gut = col[xg-15:xg+15].mean()
    left = col[int(W*0.12):int(W*0.40)].mean(); right = col[int(W*0.60):int(W*0.88)].mean()
    colmean = (left + right) / 2.0
    depth = 1.0 - gut / max(colmean, 1.0)
    return xg, depth

def _trim_strip(strip):
    sd=_dark(strip); rows=np.where(sd.sum(axis=1)>sd.shape[1]*3)[0]
    return strip.crop((0,0,strip.size[0],int(rows[-1])+8)) if len(rows) else strip

def presplit(path, upscale=2, full_width_depth=0.30):
    im=Image.open(path); W,H=im.size
    dark=_dark(im)
    xdiv=find_vertical_divider(dark)                  # body gutter — for rule finding only
    info={"xdiv":xdiv,"rules":[],"mode":"two_column"}
    rule_l=find_hrule(dark, int(W*0.03), xdiv-int(W*0.02))
    rule_r=find_hrule(dark, xdiv+int(W*0.02), W-int(W*0.03))
    info["rules"]=[rule_l,rule_r]
    y_top=min([r for r in (rule_l,rule_r) if r is not None], default=None)
    if y_top is None: return None, info
    # STAGE-1 REROUTE (sound): split at the FOOTNOTE region's own gutter; if it has no real gap
    # (depth < threshold) the footnotes are FULL-WIDTH -> crop UNCUT so a spanning note isn't sliced
    # (fixes p546 `Pagnin nus`); a real gutter -> two-column split AT xg (fixes the body!=footnote
    # gutter unsoundness that regressed p692).
    xg, depth = find_footnote_gutter(dark, y_top)
    info["fn_gutter"]=[xg, round(float(depth),2)]
    if depth < full_width_depth:
        info["mode"]="full_width"
        strip=_trim_strip(im.crop((0, y_top+6, W, H)).convert("L"))
        if upscale and upscale!=1:
            strip=strip.resize((strip.size[0]*upscale, strip.size[1]*upscale), Image.LANCZOS)
        return strip, info
    strips=[]
    for (x0,x1),yr in (((0,xg),rule_l),((xg,W),rule_r)):
        if yr is None: continue
        strips.append(_trim_strip(im.crop((x0, yr+6, x1, H)).convert("L")))
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
