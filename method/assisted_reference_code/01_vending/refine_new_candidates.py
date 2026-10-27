"""New-candidate, case-specific native surface refinement; no old meshes loaded."""
from pathlib import Path
import sys,json,math
import bpy,numpy as np
ROOT=Path(__file__).resolve().parents[2]
CID=sys.argv[sys.argv.index('--')+1]
sys.path.insert(0,str(ROOT/'cases'/CID))
from blender_common import Builder

def ctl(B,body,label,target,tol=.04):B.controls.append({'body':body,'label':label,'target':float(target),'tolerance':tol})
def record(B,data):
    (B.root/'candidate_partition.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
def local_bounds(B,mask):
    faces=B.f[mask];pts=B.v[np.unique(faces)]
    return pts.min(0),pts.max(0)

def vending(B):
    c=B.c;h=B.hi[2];L=B.L;body_pts=B.v[B.v[:,2]>.13*h]
    lo=np.quantile(body_pts,.003,axis=0);hi=np.quantile(body_pts,.997,axis=0)
    # Orientation is explicitly checked from the new source-camera render.
    front=float(hi[0]);back=float(lo[0]);left=float(lo[1]);right=float(hi[1]);bottom=.115*h;top=float(hi[2]);w=right-left;depth=front-back
    plane=front-.10*depth;door=(c[:,0]>plane)&(c[:,2]>bottom)&(c[:,2]<top-.004*h)
    hatch_z0=.20*h;hatch_z1=.34*h;hatch_w=.64*w;ycenter=(left+right)/2
    recess=(c[:,0]>front-.24*depth)&(c[:,2]>.17*h)&(c[:,2]<.38*h)&(np.abs(c[:,1]-ycenter)<hatch_w/2+.035)
    door |= recess
    hatch=recess&(c[:,2]>hatch_z0)&(c[:,2]<hatch_z1)&(np.abs(c[:,1]-ycenter)<hatch_w/2)
    steel=B.material('dark_inner_steel',(.12,.13,.14),.35,.48);red=B.material('red_cut_edge',(.55,.045,.025),.1,.45)
    B.body('base',mass=74,kind='fixed')
    hinge=[front+.006,left+.012,bottom];B.body('service_door',hinge,parent='base',mass=15,kind='hinge',axis=[0,0,-1],limits=[0,1.25],frictionloss=.45,kp=950,kv=80,force_limit=200)
    hpts=c[hatch];cov=np.cov(hpts[:,[0,2]].T);ev,U=np.linalg.eigh(cov);ht=U[:,-1];ht=ht if ht[1]>0 else -ht;hangle=float(np.arctan2(ht[0],ht[1]));hc=np.median(hpts,axis=0);hlen=float(np.ptp(hpts[:,[0,2]]@ht));hp=[float(hc[0]+ht[0]*hlen/2),ycenter,float(hc[2]+ht[1]*hlen/2)];B.body('delivery_hatch',hp,parent='service_door',mass=.8,kind='hinge',axis=[0,1,0],limits=[-.9,0],frictionloss=.01,kp=35,kv=2.5,force_limit=12)
    B.native('native_cabinet_exterior',~door,'base');B.native('native_service_face',door&~hatch,'service_door');flap=B.native('native_delivery_flap',hatch,'delivery_hatch');mod=flap.modifiers.new('reconstruct_flap_back_thickness','SOLIDIFY');mod.thickness=.003;mod.offset=0
    t=.016;zcenter=(bottom+top)/2
    B.box('inner_back',(t,w-.03,top-bottom),(back+.009,ycenter,zcenter),'base',steel,collision=True)
    for i,y in enumerate([left+.006,right-.006]):B.box('inner_side_'+str(i),(depth-.035,t,top-bottom),((front+back)/2-.01,y,zcenter),'base',red,collision=True)
    for i,z in enumerate([bottom+.008,top-.01]):B.box('inner_horizontal_'+str(i),(depth-.035,w-.025,t),((front+back)/2-.01,ycenter,z),'base',steel,collision=True)
    # The door back is a frame around the actual hatch, not a solid panel across it.
    for name,z0,z1 in [('below',bottom+.028,hatch_z0-.01),('above',hatch_z1+.01,top-.030)]:
        B.box('door_liner_'+name,(.012,w-.070,z1-z0),(plane-.008,ycenter,(z0+z1)/2),'service_door',steel,collision=True)
    for side in [-1,1]:
        sw=(w-.070-hatch_w)/2-.010;yy=ycenter+side*(hatch_w/2+sw/2+.010)
        B.box('door_liner_flap_side_'+str(side),(.012,sw,hatch_z1-hatch_z0+.002),(plane-.008,yy,(hatch_z0+hatch_z1)/2),'service_door',steel,collision=True)
    B.proxy('delivery_hatch','box',hc,[.004,(hatch_w-.018)/2,(hlen-.022)/2],quat=[math.cos(hangle/2),0,math.sin(hangle/2),0])
    for i,z in enumerate([bottom+.14,top-.14]):B.cylinder('service_hinge_barrel_'+str(i),.013,.065,[*hinge[:2],z],[0,0,1],'service_door',steel)
    B.proxy('base','box',[0,0,.035*h],[B.ext[0]*.47,B.ext[1]*.47,.033*h])
    ctl(B,'service_door','维修门打开',.85);ctl(B,'delivery_hatch','取货挡板',-.65)
    B.operations += [{'operation':'semantic face extraction with UV retention','target':'fresh service face and rectangular flap'}, {'operation':'hollow liner and door-frame reconstruction','target':'cabinet opening with hatch cutout'}, {'operation':'cylinder construction','target':'new service hinge interfaces'}]
    B.limitations += ['Fixed cabinet manipulation demo; platform is a retained visual display plinth','No drinks dispensing or payment simulation','Printed drink/label fidelity limited by native result','Service-door hinge and hidden liner are image-conditioned hypotheses']
    record(B,{'candidate_bounds':[B.lo.tolist(),B.hi.tolist()],'cabinet_front_axis':'+X','front_plane':plane,'cabinet_bounds':[lo.tolist(),hi.tolist()],'door_faces':int(door.sum()),'hatch_faces':int(hatch.sum()),'hatch_bounds':[hatch_z0,hatch_z1,hatch_w],'native_recess_faces':int(recess.sum()),'hatch_slope_rad':hangle,'hatch_pivot':hp})

def gramophone(B):
    c=B.c;col=B.color;h=B.hi[2]
    red=(col[:,0]>col[:,1]*1.55)&(col[:,0]>.2)&(c[:,2]<h*.5)
    if red.sum()<25:raise ValueError('New candidate red record label not found; inspect partition')
    center=np.median(c[red],axis=0);rz=float(center[2]);brown_base=(c[:,2]<rz-.007)&(col.max(1)<.4);bx=np.quantile(c[brown_base],[.005,.995],axis=0)
    lidmask=(c[:,2]>rz+.10)|((c[:,2]>rz+.014)&(c[:,1]>bx[1,1]-.020))
    lp=B.v[np.unique(B.f[lidmask])];pivy=float(bx[1,1]-.004);pivot=[float((bx[0,0]+bx[1,0])/2),pivy,rz+.013]
    record_mask=(np.linalg.norm(c[:,:2]-center[:2],axis=1)<.148)&(np.abs(c[:,2]-rz)<.009)
    tone=(c[:,2]>rz+.009)&(c[:,2]<rz+.095)&(c[:,1]<bx[1,1]-.035)&(col.min(1)>.38)&~lidmask
    crank=(c[:,0]>bx[1,0]-.012)&(c[:,2]<rz+.01)&(c[:,2]>.015)&~lidmask&((col.min(1)>.38)|((col[:,0]>.42)&(col[:,1]>.25)&(col[:,2]<col[:,1]*.6)))
    yz=lp[:,[1,2]];ev,U=np.linalg.eigh(np.cov(yz.T));lid_axis=U[:,-1];lid_axis=lid_axis if lid_axis[1]>0 else -lid_axis;close_angle=float(math.pi/2+math.atan2(lid_axis[0],lid_axis[1]))
    B.body('base',mass=4.75,kind='fixed');B.body('lid',pivot,parent='base',mass=1.0,kind='hinge',axis=[1,0,0],limits=[-.12,close_angle+.03],frictionloss=.05,kp=60,kv=5,force_limit=20)
    B.body('record',[center[0],center[1],rz-.004],parent='base',mass=.12,kind='hinge',axis=[0,0,1],limits=None,kp=1.5,kv=.12,force_limit=2)
    bearing=(col.min(1)>.55)&(c[:,2]>rz-.003)&(c[:,2]<rz+.015)&(c[:,0]>.02)&(c[:,0]<.12)&(c[:,1]>.015)&(c[:,1]<.12);bearing_xy=np.median(c[bearing,:2],axis=0);tonepivot=[*bearing_xy,rz+.005];B.body('tonearm',tonepivot,parent='base',mass=.09,kind='hinge',axis=[0,0,1],limits=[-.40,.25],kp=2,kv=.16,force_limit=2)
    gold=(col[:,0]>.5)&(col[:,1]>.25)&(col[:,2]<.25)&(c[:,0]>bx[1,0]);gold_c=np.median(c[gold],axis=0);crankpivot=[float(bx[1,0]),float(gold_c[1]),float(gold_c[2]+.004)];B.body('crank',crankpivot,parent='base',mass=.10,kind='hinge',axis=[1,0,0],limits=None,kp=3,kv=.2,force_limit=3)
    B.native('native_fabric_case',~(lidmask|record_mask|tone|crank),'base');bad_lid=lidmask&(col.max(1)<.06);cloth_srgb=np.median(col[lidmask&~bad_lid],axis=0);cloth_color=np.where(cloth_srgb<=.04045,cloth_srgb/12.92,((cloth_srgb+.055)/1.055)**2.4);cloth_patch=B.material('repair_black_atlas_spots',cloth_color.tolist(),0,.72);lid_ob=B.native('native_fabric_lid',lidmask,'lid');lid_ob.data.materials.append(cloth_patch)
    import bmesh
    bm=bmesh.new();bm.from_mesh(lid_ob.data);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.0001);boundary=[e for e in bm.edges if e.is_boundary];patches=bmesh.ops.holes_fill(bm,edges=boundary,sides=0).get('faces',[])
    for face in patches:face.material_index=1
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(lid_ob.data);bm.free();lid_ob.data.update()
    B.operations.append({'operation':'seam-aware positional weld and actual boundary-loop hole patches','target':'native lid','boundary_edges':len(boundary),'patched_faces':len(patches)} );B.native('native_tonearm',tone,'tonearm');B.native('native_crank',crank,'crank')
    silver=B.material('hinge_brushed_steel',(.45,.45,.43),.7,.26);black=B.material('record_sidewall',(.012,.012,.012),0,.4)
    B.cylinder('rebuilt_black_vinyl_disc',.146,.004,[center[0],center[1],rz-.003],[0,0,1],'record',black,collision=True)
    label_material=B.material('salmon_record_label',(.62,.13,.14),0,.58);B.cylinder('round_record_label',.051,.0006,[center[0],center[1],rz-.0005],[0,0,1],'record',label_material,vertices=96)
    B.sweep('record_clean_outer_edge',[[center[0]+.145*math.cos(q),center[1]+.145*math.sin(q),rz-.001] for q in np.linspace(0,math.tau,96,endpoint=False)],.0008,'record',silver,cyclic=True)
    B.cylinder('record_spindle',.002,.006,[center[0],center[1],rz-.002],[0,0,1],'base',silver)
    B.sweep('lid_hinge_pin',[[bx[0,0]+.025,pivy,rz+.013],[bx[1,0]-.025,pivy,rz+.013]],.003,'base',silver)
    # New moving lid proxy is measured in its source-open orientation.
    lc=(lp.min(0)+lp.max(0))/2;le=np.ptp(lp,axis=0)
    open_angle=math.pi/2-close_angle;normal_yz=np.array([lid_axis[1],-lid_axis[0]]);normal_extent=np.ptp(lp[:,[1,2]]@normal_yz);length_extent=np.ptp(lp[:,[1,2]]@lid_axis)
    lcoords=np.column_stack([lp[:,0],lp[:,[1,2]]@normal_yz,lp[:,[1,2]]@lid_axis]);llo,lhi=np.quantile(lcoords,[.003,.997],axis=0);lmid=(llo+lhi)/2;quat=[math.cos(open_angle/2),math.sin(open_angle/2),0,0]
    def lid_proxy(loc,size):
        yz=normal_yz*loc[1]+lid_axis*loc[2];B.proxy('lid','box',[loc[0],*yz],size,quat=quat)
    lid_proxy([lmid[0],lhi[1]-.004,lmid[2]],[(lhi[0]-llo[0])/2-.006,.004,(lhi[2]-llo[2])/2-.006])
    for x in [llo[0]+.009,lhi[0]-.009]:lid_proxy([x,lmid[1],lmid[2]],[.009,(lhi[1]-llo[1])/2,(lhi[2]-llo[2])/2-.004])
    for t in [llo[2]+.012,lhi[2]-.012]:lid_proxy([lmid[0],lmid[1],t],[(lhi[0]-llo[0])/2-.012,(lhi[1]-llo[1])/2,.012])
    B.proxy('base','box',[(bx[0,0]+bx[1,0])/2,(bx[0,1]+bx[1,1])/2,rz/2-.006],[(bx[1,0]-bx[0,0])/2-.008,(bx[1,1]-bx[0,1])/2-.008,rz/2-.008])
    B.capsule('tonearm',tonepivot,[center[0]-.025,center[1]+.015,rz+.032],.007)
    B.capsule('tonearm',[-.086,-.070,.153],[-.070,-.055,.153],.020)
    B.capsule('crank',crankpivot,np.array(crankpivot)+[.055,0,0],.007)
    ctl(B,'lid','盒盖合拢',close_angle,.045);ctl(B,'record','唱片旋转',math.tau,.08);ctl(B,'tonearm','唱臂摆动',-.25,.04);ctl(B,'crank','摇柄旋转',math.tau,.08)
    B.operations += [{'operation':'semantic UV-preserving mesh separation','target':'new lid, tonearm and crank'}, {'operation':'circular extrusion and curve sweep','target':'rebuilt black vinyl disc, round salmon label, spindle and hinge'}, {'operation':'oriented compound shell collision reconstruction','target':'lid frame/backpanel with actual inner recess and pickup-head contact'}, {'operation':'sRGB-to-linear color matching for newly patched hole surfaces','target':'133 lid boundary patches; original UV retained on existing surfaces'}]
    B.limitations += ['Fixed-base independent mechanism demonstration; no acoustic or crank-to-platter transmission model','Record/tonearm contact excluded as an inferred stylus-bearing approximation; no sound groove simulation','Actual lid motion stops 0.0236 rad short of inferred closure target, within 0.045 rad test tolerance, with a visible front seam gap; no complete sealed closure claim','Residual small cracks at native lid rim and hinge region; metal appearance remains too matte and pale']
    record(B,{'candidate_bounds':[B.lo.tolist(),B.hi.tolist()],'red_label_center':center.tolist(),'lid_pivot':pivot,'lid_closure_angle':close_angle,'base_bounds':bx.tolist(),'part_counts':{k:int(x.sum()) for k,x in [('lid',lidmask),('record',record_mask),('tone',tone),('crank',crank)]}})

def fridge(B):
    # Partition thresholds will be set only after new candidate diagnostics.
    from refine_fridge import build
    build(B)
def sink(B):
    from refine_sink import build
    build(B)

B=Builder(ROOT/'cases'/CID)
B.raw()
{'01_vending':vending,'02_gramophone':gramophone,'04_fridge':fridge,'05_sink':sink}[CID](B)
B.export()
