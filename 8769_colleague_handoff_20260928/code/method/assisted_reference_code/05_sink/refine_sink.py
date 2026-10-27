"""Repair the observed perforated basin candidate into two real shells."""
import numpy as np,json,math,bpy

def ring(w,d,r,z,center):
    points=[]
    for cx,cy,start in [(w/2-r,d/2-r,0),(-w/2+r,d/2-r,90),(-w/2+r,-d/2+r,180),(w/2-r,-d/2+r,270)]:
        for a in np.linspace(start,start+90,9):
            a=math.radians(a);points.append([center[0]+cx+r*math.cos(a),center[1]+cy+r*math.sin(a),z])
    return points

def build(B):
    c=B.c;v=B.v
    zrim=float(np.median(c[(c[:,2]>.205)&(c[:,2]<.214),2]));floor=.025
    stem=c[(c[:,2]>.31)&(c[:,2]<.34)&(c[:,0]<.06)]
    xy=np.median(stem[:,:2],axis=0);pivot=[*xy,.294];lp=[.066,float(xy[1]),.266]
    lever=(c[:,2]>.233)&(c[:,2]<.307)&(c[:,0]>.063)
    spout=(c[:,2]>.294)&~lever;hub=(c[:,2]>zrim+.001)&~spout&~lever
    B.body('base',mass=13,kind='fixed')
    B.body('spout',pivot,parent='base',mass=.65,kind='hinge',axis=[0,0,1],limits=[-.7,.7],frictionloss=.018,kp=16,kv=1.2,force_limit=8)
    B.body('lever',lp,parent='base',mass=.13,kind='hinge',axis=[1,0,0],limits=[-.2,.55],frictionloss=.006,kp=4,kv=.3,force_limit=3)
    cream=B.material('observed_off_white_basin',(.56,.58,.46),.01,.48)
    faucet=B.material('observed_satin_faucet',(.66,.68,.62),.04,.35)
    B.native('native_faucet_hub',hub,'base',faucet);B.native('native_curved_spout',spout,'spout',faucet);B.native('native_valve_handle',lever,'lever',faucet)
    # Raw source render revealed open tears and noisy broad basin surfaces.
    width=float(np.ptp(v[:,0]));depth=float(np.ptp(v[:,1]));centers=[[-width/4,0],[width/4,0]]
    topw=width/2-.047;topd=depth-.057;botw=topw-.045;botd=topd-.054
    rim=B.box('continuous_top_rim',[width,depth,.008],[0,0,zrim-.004],'base',cream,bevel=.002)
    for mod in list(rim.modifiers):rim.modifiers.remove(mod)
    for i,center in enumerate(centers):
        cutter=B.box('temporary_bowl_opening_'+str(i),[topw,topd,.06],[*center,zrim],'base',cream,bevel=.008)
        bpy.context.view_layer.objects.active=rim
        mod=rim.modifiers.new('functional_opening_'+str(i),'BOOLEAN');mod.operation='DIFFERENCE';mod.solver='EXACT';mod.object=cutter
        bpy.ops.object.modifier_apply(modifier=mod.name);bpy.data.objects.remove(cutter,do_unlink=True)
        profiles=[(botw+.018,botd+.018,.016,.003),(topw+.018,topd+.018,.010,zrim-.006),(topw,topd,.008,zrim),(botw,botd,.019,floor)]
        verts=[p for w,d,r,z in profiles for p in ring(w,d,r,z,center)];n=len(verts)//4
        faces=[tuple(reversed(range(n))),tuple(range(3*n,4*n))]
        for layer in range(3):
            for j in range(n):faces.append((layer*n+j,layer*n+(j+1)%n,(layer+1)*n+(j+1)%n,(layer+1)*n+j))
        ob=B.mesh('tapered_continuous_bowl_'+str(i),verts,faces,'base',cream)
        for face in ob.data.polygons:
            if len(face.vertices)>4:face.use_smooth=False
        weighted=ob.modifiers.new('weighted_profile_normals','WEIGHTED_NORMAL');weighted.keep_sharp=True
        x,y=center;B.proxy('base','box',[x,y,floor-.006],[botw/2-.006,botd/2-.006,.006]);height=zrim-floor
        for side in [-1,1]:
            B.proxy('base','box',[x+side*(botw+topw)/4,y,(zrim+floor)/2],[.007,topd/2,height/2],axis=[side*(topw-botw)/2,0,height])
            B.proxy('base','box',[x,y+side*(botd+topd)/4,(zrim+floor)/2],[topw/2,.007,height/2],axis=[0,side*(topd-botd)/2,height])
    for x in [-width/2+.012,0,width/2-.012]:B.proxy('base','box',[x,0,zrim-.006],[.011,depth/2,.006])
    for y in [-depth/2+.011,depth/2-.011]:B.proxy('base','box',[0,y,zrim-.006],[width/2,.010,.006])
    B.cylinder('swivel_sleeve',.014,.014,[xy[0],xy[1],.293],[0,0,1],'base',faucet)
    B.cylinder('rotating_swivel_insert',.0115,.010,[xy[0],xy[1],.298],[0,0,1],'spout',faucet)
    B.cylinder('valve_axis_boss',.016,.022,[.072,xy[1],.266],[1,0,0],'base',faucet)
    chain=[pivot,[.034,.211,.345],[.021,.193,.411],[-.016,.163,.470],[-.068,.117,.492],[-.119,.071,.486],[-.141,.051,.467]]
    for a,b in zip(chain[:-1],chain[1:]):B.capsule('spout',a,b,.009)
    B.proxy('lever','box',[.088,xy[1]-.008,.266],[.015,.023,.016])
    B.controls += [{'body':'spout','label':'龙头旋转','target':.55,'tolerance':.04},{'body':'lever','label':'阀门转动','target':.35,'tolerance':.035}]
    B.operations += [{'operation':'native UV-preserving semantic split','target':'new curved spout, valve and hub'}, {'operation':'section loft with complete outer/inner walls and floors','target':'both perforated native basins','reason':'actual raw source render showed holes, tears and rough broad panels'}, {'operation':'Boolean difference','target':'two real openings in a continuous top rim'}, {'operation':'inclined compound wall contact shells','target':'open tapered basin collision cavities'}, {'operation':'cylindrical bearing interface reconstruction','target':'spout and valve cuts'}]
    B.limitations += ['Fixed installed basin; no plumbing or fluid simulation','Off-white response, scale and mass are image/category hypotheses','Native basin topology and noisy PBR were rejected after inspection; continuous basin surfaces follow measured candidate extents and inferred wall thickness','Contact wall boxes approximate tapered shell; rounded corners are simplified']
    report={'candidate_bounds':[B.lo.tolist(),B.hi.tolist()],'basin_bounds':[[-width/2,-depth/2,.003],[width/2,depth/2,zrim]],'rim_z':zrim,'floor_z':floor,'faucet_pivot':pivot,'valve_pivot':lp,'probe_drop_centers':[[x,y,floor+.12] for x,y in centers], 'part_faces':{'hub':int(hub.sum()),'spout':int(spout.sum()),'lever':int(lever.sum())},'basin_profile':{'top_inner_width':topw,'top_inner_depth':topd,'bottom_inner_width':botw,'bottom_inner_depth':botd}}
    (B.root/'candidate_partition.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
