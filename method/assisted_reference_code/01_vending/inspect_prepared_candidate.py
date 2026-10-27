from pathlib import Path
import sys,json
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2]
r=ROOT/'cases'/sys.argv[1];a=np.load(r/'native_geometry.npz');v=a['vertices'];f=a['faces'];c=v[f].mean(1);rgb=a['face_colors']
out=Image.new('RGB',(1800,1200),'#eeeeee');draw=ImageDraw.Draw(out)
for k,(horizontal,vertical,depth,label) in enumerate([(0,2,1,'XZ front'),(1,2,0,'YZ side'),(0,1,2,'XY top'),(0,2,1,'XZ back'),(1,2,0,'YZ reverse'),(0,1,2,'XY bottom')]):
    x0=(k%3)*600;y0=(k//3)*600;lo=c[:,[horizontal,vertical]].min(0);hi=c[:,[horizontal,vertical]].max(0);scale=530/(hi-lo).max();xy=(c[:,[horizontal,vertical]]-lo)*scale
    order=np.argsort(c[:,depth]);order=order if k<3 else order[::-1]
    for i in order[::max(1,len(order)//180000)]:
        x=x0+35+xy[i,0];y=y0+565-xy[i,1];co=tuple(np.uint8(np.clip(rgb[i]*255,0,255)));draw.rectangle((x,y,x+2,y+2),fill=co)
    draw.text((x0+10,y0+10),label,fill='black')
out.save(r/'renders/orthographic_candidate_diagnostic.png')
d={'bounds':[v.min(0).tolist(),v.max(0).tolist()],'faces':len(f),'vertices':len(v),'face_centroid_quantiles':np.quantile(c,[.01,.1,.25,.5,.75,.9,.99],axis=0).tolist()}
for name,mask in [('red',(rgb[:,0]>rgb[:,1]*1.55)&(rgb[:,0]>.2)),('white',rgb.min(1)>.5),('dark',rgb.max(1)<.18)]:
    if mask.any():d[name]={'face_count':int(mask.sum()),'centroid':np.median(c[mask],axis=0).tolist(),'q005_995':np.quantile(c[mask],[.005,.995],axis=0).tolist()}
(r/'candidate_diagnostic.json').write_text(json.dumps(d,indent=2),encoding='utf-8');print(json.dumps(d))
