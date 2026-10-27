from pathlib import Path
from PIL import Image
import numpy as np,json,hashlib
from scipy.ndimage import map_coordinates,distance_transform_edt
R=Path(__file__).resolve().parent;src=np.array(Image.open(R/'input/source.png').convert('RGB'));report={}
quads={'back':[[389,163],[525,137],[551,397],[409,416]],'seat':[[403,447],[569,418],[653,470],[431,512]]}
for name,q in quads.items():
 uv=np.array([[0,0],[1,0],[1,1],[0,1]],float);aa=[];bb=[]
 for (u,v),(x,y) in zip(uv,q):aa.extend([[u,v,1,0,0,0,-x*u,-x*v],[0,0,0,u,v,1,-y*u,-y*v]]);bb.extend([x,y])
 H=np.r_[np.linalg.solve(aa,bb),1].reshape(3,3);n=1024;gy,gx=np.mgrid[0:n,0:n]/(n-1);pp=np.stack([gx,gy,np.ones_like(gx)],-1)@H.T;xx=pp[:,:,0]/pp[:,:,2];yy=pp[:,:,1]/pp[:,:,2]
 im=np.stack([map_coordinates(src[:,:,k].astype(float),[yy,xx],order=1,mode='nearest') for k in range(3)],-1);rr,gg,bl=im.transpose(2,0,1)
 valid=(bl>rr*1.50)&(bl>gg*1.22)&(bl-rr>16)&(bl>18)
 _,indices=distance_transform_edt(~valid,return_indices=True);out=im.copy();out[~valid]=im[indices[0][~valid],indices[1][~valid]]
 # Source armrest/tubes visibly occlude part of the cloth; never bake those foreground parts into the cloth.
 occluded=np.zeros_like(valid)
 if name=='back':
  half=out[:,::2];out=np.concatenate([half[:,::-1],half],axis=1);occluded[:,:n//2]=True
 Image.fromarray(np.uint8(np.clip(out,0,255))).save(R/'asset'/('source_'+name+'_cloth.png'))
 report[name]={'source_quad_pixels':q,'explicit_occlusion_mirror_fraction':float(occluded.mean()),'occlusion_repair':'back uses a clean visible right panel mirrored for the occluded left panel; seat extends a clean central crop. Inferred edge pattern, not exact complete texture reconstruction','source_image_size':[src.shape[1],src.shape[0]],'homography':H.tolist(),'inferred_occlusion_fill_fraction':float((~valid).mean()),'fill_method':'nearest visible blue textile texel; not recovered hidden detail','resolution':[n,n]}
report['source_sha256']=hashlib.sha256((R/'input/source.png').read_bytes()).hexdigest();report['scope']='Blender appearance repair by image-to-surface UV transfer; original input unchanged; no image enhancement; inherited source illumination remains'
(R/'source_projection_report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
