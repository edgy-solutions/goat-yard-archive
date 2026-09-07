"""Score the Hebrew-span localizer against the 30 ratified boxes (the validation-set truth). For each span:
derive a column-bounded note-line crop from the ratified box's y-band (past the border rule), run
locate_hebrew, and classify LOCATED / ABSTAIN / MISLOCATE by CONTAINMENT (the ratified boxes loosely bound
the Hebrew, so tight IoU is wrong — a correct tight box scores low against a loose truth box). Reads the
exported verdicts JSONL. Run after any localizer change to re-measure."""
import sys,json; sys.path.insert(0,'pipeline/reextract'); sys.path.insert(0,'pipeline/scripts'); sys.stdout.reconfigure(encoding='utf-8')
from PIL import Image
import cv_footnote_presplit as ps
import word_box_align as W
A='C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits/'
verd={r['span_id']:r for r in (json.loads(l) for l in open('C:/Users/cnogr/Downloads/span_box_verdicts_20260906.jsonl',encoding='utf-8') if l.strip())}
spans={s['span_id']:s for s in json.load(open(A+'hebrew_sample_20260906.json',encoding='utf-8'))+json.load(open(A+'nikud_sample_10.json',encoding='utf-8'))}
props={p['span_id']:p for p in json.load(open(A+'span_box_proposals_20260906.json',encoding='utf-8'))}
def band(pg):
    strip,info=ps.presplit(f'C:/Users/cnogr/git/dr-voluminous/commentary/volume1/page{pg}_image1.png',upscale=1)
    return (strip if strip is not None else Image.open('..').convert('L')).convert('L')
OFF=50
res=[]
for sid,v in verd.items():
    pg=v['page']; rb=v['ratified_box']; b=band(pg); run=spans[sid]['run_text']
    flags=props[sid].get('flags',[])
    line=b.crop((OFF,rb[1]-2,v['gutter'],rb[3]+2))
    box,st=W.locate_hebrew(line,run)
    if box is None:
        verdict='ABSTAIN'; detail=st
    else:
        lx0,lx1=box[0]+OFF,box[2]+OFF; tw=rb[2]-rb[0]
        contained = lx0>=rb[0]-22 and lx1<=rb[2]+22
        cover=(min(lx1,rb[2])-max(lx0,rb[0]))/tw if tw>0 else 0
        if contained and cover>=0.5: verdict='LOCATED'
        elif cover>=0.5 and (lx1-lx0)<=tw*1.4: verdict='LOCATED'   # loose truth: slight overflow ok
        else: verdict='MISLOCATE'
        detail=f'loc[{lx0},{lx1}] truth[{rb[0]},{rb[2]}] cover={cover:.2f}'
    res.append((sid,verdict,detail,'|'.join(flags)))
from collections import Counter
cat=Counter(r[1] for r in res)
for sid,vd,detail,fl in res: print(f'{sid:10} {vd:10} {detail:44} {fl}')
print('---',dict(cat))
# non-contiguous should ABSTAIN (correct); drop-cases are partial-by-design
print('non-contig (should abstain):',[r[0] for r in res if 'non-contiguous' in r[3]],'->',[r[1] for r in res if 'non-contiguous' in r[3]])
