from pathlib import Path
import sys,json,math,numpy as np,bpy
R=Path(__file__).resolve().parent;sys.path.insert(0,str(R))
from blender_common import Builder
from geometry_helpers import tube_between,lathe_y
P=json.loads((R/'semantic_parameters.json').read_text());B=Builder(R);c=B.c;v=B.v
rear=np.zeros(len(c),bool);front=np.zeros(len(c),bool);foot=np.zeros(len(c),bool);fork=np.zeros(len(c),bool)
for s in [-1,1]:
 w=P['rear'][str(s)];dxz=c[:,[0,2]]-np.array(w['center'])[[0,2]];dist=np.linalg.norm(dxz,axis=1)
 rear|=(c[:,1]*s>w['inner_y']*s if s==1 else c[:,1]*s>abs(w['inner_y']))&(dist<w['radius']*1.11)&(c[:,2]<w['center'][2]+w['radius']*1.05)
 q=P['front'][str(s)];front|=(np.abs(c[:,1]-q['center'][1])<.065)&(np.linalg.norm(c[:,[0,2]]-np.array(q['center'])[[0,2]],axis=1)<q['radius']*1.18)
 foot|=(c[:,0]>P['foot_min_x'])&(c[:,2]<P['foot_max_z'])
 fork|=(c[:,0]>q['center'][0]-.085)&(c[:,0]<q['center'][0]+.085)&(np.abs(c[:,1]-q['center'][1])<.055)&(c[:,2]<q['pivot'][2]+.01)&~front
front=((c[:,2]<.254)&(np.abs(c[:,1])>.225)&(c[:,0]>.13)&(c[:,0]<.395))&~foot;fork&=~foot
B.body('base',mass=9.7,kind='free');steel=B.material('brushed_frame_metal',(.48,.51,.50),.78,.30);rubber=B.material('wheel_rubber',(.018,.02,.018),0,.78);rim=B.material('wheel_rim_silver',(.38,.40,.39),.75,.28);dark=B.material('footplate_polymer',(.012,.015,.013),0,.53)
side_fringe=(np.abs(c[:,1])>.237)&(np.abs(c[:,1])<.294)&(c[:,0]>-.195)&(c[:,0]<.19)&(c[:,2]>.574)&(c[:,2]<.766)
remaining=~(rear|front|foot|fork|side_fringe);col=B.color;blue=(col[:,2]>col[:,0]*1.25)&(col[:,2]>col[:,1]*1.06)&(c[:,2]>.47)&(np.abs(c[:,1])<.279)&(c[:,0]<.29)
cloth_v=B.v.copy();ids=np.unique(B.f[remaining&blue]);x,y,z=cloth_v[ids].T
bk=(z>.586)&(x<-.13);sx=P['back_x']-.205*(z-P['seat_z'])-.008*(1-(y/.255)**2)*np.sin(np.clip((z-.55)/.44,0,1)*math.pi)
cloth_v[ids[bk],0]=sx[bk]+.12*np.clip(x[bk]-sx[bk],-.014,.014)
st=~bk;u=np.clip((x-P['back_x'])/(P['seat_front_x']-P['back_x']),0,1);sz=.537-.016*np.sin(math.pi*u)*(1-(y/.255)**2)
cloth_v[ids[st],2]=sz[st]+.18*np.clip(z[st]-sz[st],-.012,.012)
def cloth_uv(vv,which):
 uv=np.empty((len(vv),2));uv[:,0]=np.clip((vv[:,1]+.246)/.492,0,1)
 if which=='back':uv[:,1]=np.clip((vv[:,2]-P['seat_z'])/(P['back_top']-.014-P['seat_z']),0,1)
 else:uv[:,1]=1-np.clip((vv[:,0]-P['back_x'])/(P['seat_front_x']-P['back_x']),0,1)
 return uv
cloth_mats={}
for which in ['back','seat']:
 mat=B.material('source_projected_'+which,(1,1,1),0,.80);bs=mat.node_tree.nodes.get('Principled BSDF');tex=mat.node_tree.nodes.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(R/'asset'/('source_'+which+'_cloth.png')));mat.node_tree.links.new(tex.outputs['Color'],bs.inputs['Base Color']);mat['texture']='source_'+which+'_cloth.png';cloth_mats[which]=mat
 backpart=(c[:,2]>.586)&(c[:,0]<-.13);mask=remaining&blue&(backpart if which=='back' else ~backpart)
 ob=B.native('refined_neural_'+which+'_with_source_uv',mask,'base',mat,vertices=cloth_v)
 if ob:
  coords=np.array([v.co[:] for v in ob.data.vertices]);uvnew=cloth_uv(coords,which);layer=ob.data.uv_layers.active
  for loop in ob.data.loops:layer.data[loop.index].uv=uvnew[loop.vertex_index]
B.native('native_frame_and_armrests',remaining&~blue,'base',B.variant('native_metal_frame_response',.35,.40))
for s in [-1,1]:
 label='left' if s<0 else 'right';w=P['rear'][str(s)];o=np.array(w['center']);rad=w['radius'];body='rear_'+label
 B.body(body,o,parent='base',mass=2.2,kind='hinge',axis=[0,1,0],limits=None,damping=.012,kp=24,kv=9.0,force_limit=20)
 region=rear&(c[:,1]*s>0);rr=np.linalg.norm(c[:,[0,2]]-o[[0,2]],axis=1);outer=region&(rr>rad*.87)
 B.native('native_tyre_surface_'+label,outer,body,B.variant('native_tyre_material',.05,.72))
 lathe_y(B,'continuous_rim_'+label,o,[(rad*.90,-.010),(rad*.875,-.013),(rad*.875,.013),(rad*.90,.010)],body,rim)
 B.cylinder('wheel_hub_'+label,rad*.075,.078,o,[0,1,0],body,steel)
 for i in range(32):
  ang=i*math.tau/32;off=.023 if i%2 else -.023;anchor=o+np.array([rad*.065*math.cos(ang+.6),off,rad*.065*math.sin(ang+.6)])
  end=o+np.array([rad*.88*math.cos(ang),0,rad*.88*math.sin(ang)])
  tube_between(B,'crossed_spoke_'+label+'_'+str(i),anchor,end,.00125,body,steel)
 lathe_y(B,'pushrim_'+label,o+np.array([0,s*.047,0]),[(rad*.81+.008,0),(rad*.81,.008),(rad*.81-.008,0),(rad*.81,-.008)],body,rim)
 B.proxy(body,'cylinder',o,[rad,.019],axis=[0,1,0],friction=[.8,.005,.0001])
 # Explicit axle connects the wheel hub to the retained side frame.
 tube_between(B,'axle_to_frame_'+label,o,[o[0],s*P['frame_y'],o[2]],.014,'base',steel)
 q=P['front'][str(s)];fc=np.array(q['center']);fp=np.array(q['pivot']);cast='caster_'+label;fw='front_'+label
 B.body(cast,fp,parent='base',mass=.08,kind='hinge',axis=[0,0,1],limits=None,actuated=False,damping=.01)
 B.cylinder('caster_steerer_'+label,.012,.055,fp,[0,0,1],cast,steel)
 for dy in [-.031,.031]:tube_between(B,'fork_blade_'+label+str(dy),fp+np.array([0,dy,-.008]),fc+np.array([0,dy,0]),.010,cast,steel,True)
 B.body(fw,fc,parent=cast,mass=.42,kind='hinge',axis=[0,1,0],limits=None,actuated=False,damping=.004)
 # Fragmented native caster region is replaced by a complete open spoked wheel.
 lathe_y(B,'front_wheel_complete_'+label,fc,[(q['radius'],-.010),(q['radius'],.010),(q['radius']*.72,.022),(q['radius']*.72,-.022)],fw,rubber,64)
 
 for k in range(6):
  ang=k*math.tau/6;tube_between(B,'caster_spoke_'+label+'_'+str(k),fc,fc+np.array([math.cos(ang)*q['radius']*.80,0,math.sin(ang)*q['radius']*.80]),.009,fw,dark)
 B.cylinder('caster_hub_'+label,.023,.052,fc,[0,1,0],fw,steel);B.proxy(fw,'cylinder',fc,[q['radius'],.022],axis=[0,1,0])
 # A curve-swept fixed lower tube reaches each actual footplate hinge.
 h=np.array(P['foot'][str(s)]['hinge']);center=np.array(P['foot'][str(s)]['center']);fb='footrest_'+label
 support=np.array([P['seat_front_x'],s*P['frame_y'],P['seat_z']-.045])
 B.sweep('continuous_foot_support_'+label,[support,[support[0]+.035,s*(P['frame_y']+.016),.27],h],.012,'base',steel)
 B.capsule('base',support,h,.012)
 B.body(fb,h,parent='base',mass=.40,kind='hinge',axis=[-s,0,0],limits=[0,1.45],frictionloss=.012,kp=12,kv=.6,force_limit=12)
 B.native('native_footplate_top_'+label,foot&(c[:,1]*s>0),fb,B.variant('native_footplate_roughness',.04,.56))
 dims=P['foot'][str(s)]['dimensions'];B.box('footplate_structure_'+label,dims,center,fb,dark,.006,True)
 tube_between(B,'footplate_hinge_pin_'+label,h+[-.045,0,0],h+[.045,0,0],.010,'base',steel)
 B.controls.extend([{'body':body,'label':'rear wheel '+label,'target':1.4,'tolerance':.10},{'body':fb,'label':'fold footplate '+label,'target':1.0,'tolerance':.06}])
# Sparse physical frame proxies keep the open under-seat region usable.
for s in [-1,1]:
 y=s*P['frame_y'];B.capsule('base',[P['back_x'],y,P['seat_z']-.08],[P['back_x'],y,P['back_top']],.012);B.capsule('base',[P['back_x'],y,P['seat_z']],[P['seat_front_x'],y,P['seat_z']],.012)
B.proxy('base','box',[(P['back_x']+P['seat_front_x'])/2,0,P['seat_z']],[abs(P['seat_front_x']-P['back_x'])/2,P['frame_y'],.012])
B.proxy('base','box',[P['back_x'],0,(P['seat_z']+P['back_top'])/2],[.014,P['frame_y'],(P['back_top']-P['seat_z'])/2])
# Back a perforated reconstructed textile with a thin curved surface while retaining the textured native layer.
cloth=B.material('inferred_cloth_hole_backing',(.014,.039,.083),0,.87)
for which in ['seat','back']:
 vv=[];ff=[];nx=22;ny=24
 for i in range(nx+1):
  u=i/nx
  for j in range(ny+1):
   y=(j/ny*2-1)*.246
   if which=='seat':
    x=P['back_x']+u*(P['seat_front_x']-P['back_x']);z=.537-.016*math.sin(math.pi*u)*(1-(y/.255)**2)-.004
   else:
    z=P['seat_z']+u*(P['back_top']-.014-P['seat_z']);x=P['back_x']-.205*(z-P['seat_z'])-.008*(1-(y/.255)**2)*math.sin(np.clip((z-.55)/.44,0,1)*math.pi)-.004
   vv.append([x,y,z])
 for i in range(nx):
  for j in range(ny):a=i*(ny+1)+j;ff.append([a,a+1,a+ny+2,a+ny+1])
 B.mesh('curved_'+which+'_backing',np.array(vv),np.array(ff),'base',cloth_mats[which],cloth_uv(np.array(vv),which))
for sgn in [-1,1]:B.box('reconstructed_side_guard_'+str(sgn),[.37,.004,.17],[-.005,sgn*.255,.665],'base',dark,.012)
B.operations.append({'operation':'UV-preserving controlled surface deformation','target':'native seat and back; remove oversized ridges while retaining low-amplitude folds','max_movement_m':float(np.linalg.norm(cloth_v-B.v,axis=1).max())})
B.operations.append({'operation':'remove hanging strips and reconstruct thin side guards','target':'under armrests','removed_candidate_faces':int(side_fringe.sum())})
B.operations.append({'operation':'curved thin-surface reconstruction','target':'backing behind visible holes in native cloth; detailed atlas retained on original surface'})
B.operations.extend([{'operation':'candidate-informed semantic assignment and removal of fused spokes/forks','target':'new native wheel and foot regions; source atlas retained elsewhere'}, {'operation':'annular profile loft and crossed spoke construction','target':'two complete rear wheel rims, push rims and 64 spokes'}, {'operation':'curve sweeps and local hidden support reconstruction','target':'continuous footplate supports and caster forks'}])
B.limitations.extend(['Seat/back cloth are rigid in this wheel/footplate mechanism experiment','No braking or frame folding; masses, dimensions and spoke count are inferred','Visual/collision surfaces remain approximations; image text is not recovered ground truth'])
B.operations.append({'operation':'source-image UV projection on controlled surfaces','target':'visible back and seat; new native geometry retained and refined','record':'source_projection_report.json','limitation':'occluded texels filled from nearest observed blue textile; source illumination remains baked'})
B.export()
