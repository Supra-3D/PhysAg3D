"""Preserve neural surface/UVs, infer metric registration, fit a reference camera."""
from pathlib import Path
import sys,json,math
import numpy as np
from PIL import Image,ImageOps,ImageDraw
import trimesh
from scipy.optimize import minimize
from scipy.ndimage import distance_transform_edt
from numba import njit
ROOT=Path(__file__).resolve().parent

@njit(cache=True)
def raster(points,faces,colors,n):
    depth=np.full((n,n),1e10);out=np.zeros((n,n,3));mask=np.zeros((n,n),np.uint8)
    for i in range(len(faces)):
        a,b,c=faces[i];x0,y0,z0=points[a];x1,y1,z1=points[b];x2,y2,z2=points[c]
        den=(y1-y2)*(x0-x2)+(x2-x1)*(y0-y2)
        if abs(den)<1e-8:continue
        xmin=max(0,int(min(x0,x1,x2)));xmax=min(n-1,int(max(x0,x1,x2))+1)
        ymin=max(0,int(min(y0,y1,y2)));ymax=min(n-1,int(max(y0,y1,y2))+1)
        for y in range(ymin,ymax+1):
            for x in range(xmin,xmax+1):
                aa=((y1-y2)*(x+.5-x2)+(x2-x1)*(y+.5-y2))/den
                bb=((y2-y0)*(x+.5-x2)+(x0-x2)*(y+.5-y2))/den;cc=1-aa-bb
                if aa>=0 and bb>=0 and cc>=0:
                    z=aa*z0+bb*z1+cc*z2
                    if z<depth[y,x]:depth[y,x]=z;mask[y,x]=1;out[y,x]=colors[i]
    return mask,out

def axes(az,el,roll=0):
    a,e,r=np.deg2rad([az,el,roll]);eye=np.array([np.cos(e)*np.cos(a),np.cos(e)*np.sin(a),np.sin(e)])
    right=np.cross([0,0,1],eye);right/=np.linalg.norm(right);up=np.cross(eye,right)
    return np.cos(r)*right+np.sin(r)*up,-np.sin(r)*right+np.cos(r)*up,eye

def run(cid):
    r=ROOT;p=json.loads((r/'asset_plan.json').read_text(encoding='utf-8'))
    src=r/'native-result/output/candidate_yup.glb';scene=trimesh.load(src,force='scene',process=False)
    mesh=scene.to_geometry();raw=np.asarray(mesh.vertices).copy();v=raw[:,[0,2,1]];v[:,1]*=-1
    rot=np.array([[1,0,0],[0,0,-1],[0,1,0]],float)
    if cid=='07_cushion':
        small=int(np.argmin(np.ptp(v,axis=0)))
        if small==1:
            extra=np.array([[1,0,0],[0,0,-1],[0,1,0]],float);v=v@extra.T;rot=extra@rot
        elif small==0:
            extra=np.array([[0,0,-1],[0,1,0],[1,0,0]],float);v=v@extra.T;rot=extra@rot
    ext=np.ptp(v,axis=0)
    if cid in ['01_vending','03_lamp','04_fridge','08_wheelchair']:scale=p['dimensions_m_prior'][2]/ext[2]
    elif cid=='06_excavator':scale=7.4/ext.max()
    else:scale=p['dimensions_m_prior'][0]/ext[0]
    offset=np.array([-(v[:,0].min()+v[:,0].max())/2,-(v[:,1].min()+v[:,1].max())/2,-v[:,2].min()])
    v=(v+offset)*scale;f=np.asarray(mesh.faces,dtype=np.int32);uv=np.asarray(mesh.visual.uv)
    mat=mesh.visual.material
    for field in ['baseColorTexture','metallicRoughnessTexture','normalTexture']:
        im=getattr(mat,field,None)
        if im is not None:im.save(r/'asset'/(field+'.png'))
    tex=np.array(mat.baseColorTexture.convert('RGB'))/255.
    tuv=uv[f].mean(axis=1);x=np.clip(tuv[:,0]*tex.shape[1],0,tex.shape[1]-1).astype(int);y=np.clip((1-tuv[:,1])*tex.shape[0],0,tex.shape[0]-1).astype(int)
    colors=tex[y,x]
    np.savez_compressed(r/'native_geometry.npz',vertices=v,faces=f,uv=uv,face_colors=colors.astype(np.float32))
    transform=np.eye(4);transform[:3,:3]=rot*scale;transform[:3,3]=offset*scale
    (r/'registration.json').write_text(json.dumps({'T_metric_zup_from_native_yup':transform.tolist(),'scale_source':'category prior, not measured','bounds_m':[v.min(0).tolist(),v.max(0).tolist()],'faces':len(f),'vertices':len(v)},indent=2),encoding='utf-8')
    image=Image.open(r/'input/source.png').convert('RGBA');alpha=np.array(image)[:,:,3]
    reliable=bool((alpha<128).any())
    if not reliable:
        if cid=='07_cushion':
            mask=Image.new('L',image.size);draw=ImageDraw.Draw(mask)
            pts=np.array([[128,86],[325,97],[510,121],[619,147],[646,203],[663,330],[673,434],[133,423],[113,365],[123,211]])*np.array(image.size)/[800,533]
            draw.polygon([tuple(a) for a in pts],fill=255);image.putalpha(mask)
        else:
            rgb=np.array(image)[:,:,:3].astype(float);bg=np.median(np.concatenate([rgb[:8].reshape(-1,3),rgb[-8:].reshape(-1,3)]),axis=0)
            image.putalpha(Image.fromarray((np.linalg.norm(rgb-bg,axis=2)>40).astype(np.uint8)*255))
    padded=ImageOps.pad(image,(1024,1024),color=(0,0,0,0));padded.save(r/'input/reference_square.png')
    n=96;small=np.array(padded.resize((n,n),Image.Resampling.LANCZOS));target=small[:,:,3]>127;rgb=small[:,:,:3]/255
    dist=distance_transform_edt(~target)/n;center=(v.min(0)+v.max(0))/2;length=np.ptp(v,axis=0).max()
    # Camera fitting uses a voxel-clustered surface at finer than pixel spacing.
    # The actual exported candidate stays unchanged at its original resolution.
    _,ix,inv=np.unique(np.round((v-center)/length*128).astype(np.int32),axis=0,return_index=True,return_inverse=True)
    fit_faces=inv[f].astype(np.int32);keep=(fit_faces[:,0]!=fit_faces[:,1])&(fit_faces[:,1]!=fit_faces[:,2])&(fit_faces[:,0]!=fit_faces[:,2])
    fi=np.flatnonzero(keep);_,unique=np.unique(np.sort(fit_faces[keep],axis=1),axis=0,return_index=True);fi=fi[unique]
    fit_faces=fit_faces[fi];fit_colors=colors[fi];points=(v[ix]-center)/length
    def evaluate(par,return_image=False):
        right,up,eye=axes(par[0],par[1],par[5]);proj=np.column_stack([(points@right/par[2]+par[3])*n,(-points@up/par[2]+par[4])*n,-points@eye])
        mask,col=raster(proj,fit_faces,fit_colors,n);fg=mask>0;inter=fg&target;union=fg|target
        iou=inter.sum()/max(union.sum(),1);colorloss=np.abs(col[inter]-rgb[inter]).mean() if inter.any() else 1.
        loss=1-iou+.28*colorloss+.2*dist[fg].mean() if fg.any() else 3.
        return (mask,col,iou) if return_image else loss
    candidates=[]
    hintfile=ROOT/'camera_hints.json';hint=json.loads(hintfile.read_text()).get(cid) if hintfile.exists() else None
    azimuths=np.linspace(*hint['azimuth'],3) if hint else (range(-75,76,30) if cid=='01_vending' else range(-180,180,45))
    for az in azimuths:
        for el in (np.linspace(*hint['elevation'],3) if hint else [15,35,60]):
            q=np.array([az,el,1.35,.5,.52,0.]);candidates.append((evaluate(q),q))
    best=None
    for initial_loss,q in sorted(candidates,key=lambda a:a[0])[:5]:
        ab=hint['azimuth'] if hint else (q[0]-35,q[0]+35);eb=hint['elevation'] if hint else (max(0,q[1]-20),min(85,q[1]+20))
        opt=minimize(evaluate,q,method='Powell',bounds=[ab,eb,(.75,2.6),(.30,.70),(.30,.70),(-10,10)],options={'maxiter':15,'ftol':.0003,'xtol':.001})
        if opt.fun>initial_loss:opt.fun=initial_loss;opt.x=q
        if best is None or opt.fun<best.fun:best=opt
    mask,col,iou=evaluate(best.x,True);right,up,eye=axes(best.x[0],best.x[1],best.x[5])
    camera={'type':'ORTHO','location':(center+eye*length*3).tolist(),'target':center.tolist(),'right':right.tolist(),'up':up.tolist(),
        'ortho_scale':float(best.x[2]*length),'shift_x':float(.5-best.x[3]),'shift_y':float(best.x[4]-.5),'resolution':1024,
        'fit':{'low_resolution_mask_iou':float(iou),'source_mask_reliable_alpha':reliable,'resolution':n,'loss':float(best.fun),'semantic_view_constraint':hint,'method':'orthographic camera optimization against triangle-rasterized native silhouette and coarse texture color'}}
    (r/'camera.json').write_text(json.dumps(camera,indent=2),encoding='utf-8')
    Image.fromarray(np.uint8(np.clip(col,0,1)*255)).resize((576,576)).save(r/'renders/camera_fit_diagnostic.png')
    print(cid,'prepared',len(f),'faces','camera IoU',round(iou,4),flush=True)
if __name__=='__main__':run(sys.argv[1])
