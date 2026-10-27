from pathlib import Path
import numpy as np,json
from PIL import Image,ImageDraw
from prepare_candidate import raster
R=Path(__file__).resolve().parent;a=np.load(R/'native_geometry.npz');v=a['vertices'];f=a['faces'];col=a['face_colors'];c=v[f].mean(1)
N=760;pad=60
summary={'bounds':[v.min(0).tolist(),v.max(0).tolist()],'face_count':len(f),'slabs':{}}
for view,axes in [('front_X',(1,2,0)),('side_Y',(0,2,1)),('top_Z',(0,1,2))]:
 xx,yy,zz=axes;lo=v[:,[xx,yy]].min(0);hi=v[:,[xx,yy]].max(0);scale=(N-2*pad)/max(hi-lo);cen=(lo+hi)/2
 pts=np.column_stack([(v[:,xx]-cen[0])*scale+N/2,-(v[:,yy]-cen[1])*scale+N/2,-v[:,zz]])
 mask,colors=raster(pts,f,col,N);im=Image.fromarray(np.uint8(np.clip(colors,0,1)*255));d=ImageDraw.Draw(im)
 for q in np.linspace(lo[0],hi[0],7):
  x=(q-cen[0])*scale+N/2;d.line([(x,30),(x,N-30)],fill=(50,50,50));d.text((x+2,N-27),f'{q:.3f}',fill='white')
 for q in np.linspace(lo[1],hi[1],9):
  y=-(q-cen[1])*scale+N/2;d.line([(30,y),(N-30,y)],fill=(50,50,50));d.text((2,y),f'{q:.3f}',fill='white')
 d.text((12,8),f'{view}: horizontal {"XYZ"[xx]}, vertical {"XYZ"[yy]} (metres)',fill='white');im.save(R/'renders'/('diagnostic_'+view+'.png'))
for ax in range(3):
 cuts=np.linspace(v[:,ax].min(),v[:,ax].max(),13);summary['slabs']['XYZ'[ax]]=[]
 for lo,hi in zip(cuts[:-1],cuts[1:]):
  sel=(c[:,ax]>=lo)&(c[:,ax]<hi)
  if sel.any():summary['slabs']['XYZ'[ax]].append({'range':[float(lo),float(hi)],'faces':int(sel.sum()),'center':c[sel].mean(0).tolist(),'color':col[sel].mean(0).tolist()})
(R/'candidate_diagnostic.json').write_text(json.dumps(summary,indent=2))
print(json.dumps({k:v for k,v in summary.items() if k!='slabs'},indent=2))
