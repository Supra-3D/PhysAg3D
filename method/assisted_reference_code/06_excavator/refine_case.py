from pathlib import Path
import sys,json,math,numpy as np,bpy
R=Path(__file__).resolve().parent;sys.path.insert(0,str(R))
from blender_common import Builder
from geometry_helpers import tube_between
P=json.loads((R/'semantic_parameters.json').read_text());B=Builder(R);B.raw();c=B.c;col=B.color
steel=B.material('machined_piston_steel',(.34,.38,.40),.82,.24);paint=B.material('hydraulic_barrel_dark',(.045,.055,.052),.3,.47);yellow=B.material('pivot_painted_metal',(.60,.25,.065),.25,.43)
B.body('base',mass=7500,kind='free');B.body('slew',P['slew'],parent='base',mass=3900,kind='hinge',axis=[0,0,1],limits=[-math.pi,math.pi],frictionloss=100)
for name,parent,mass,limit in [('boom','slew',1700,[-.35,.35]),('stick','boom',650,[-.55,.55]),('bucket','stick',250,[-.7,.8])]:
 B.body(name,P[name+'_pivot'],parent=parent,mass=mass,kind='hinge',axis=[1,0,0],limits=limit,frictionloss=30 if name!='boom' else 80,kp=4000000 if name=='boom' else (500000 if name=='stick' else 90000),force_limit=600000 if name=='boom' else 200000)
under=(c[:,2]<P['track_top'])&(c[:,1]>.25);arm=((c[:,1]<.25)&(np.abs(c[:,0])<.55)&(c[:,2]>P['arm_zmin'])|((c[:,1]<P['arm_ymax'])&(np.abs(c[:,0])<.29)&(c[:,2]>1.82)))&~under
bucket=arm&(((c[:,2]<P['bucket_zmax'])&(c[:,1]<P['bucket_ymax']))|((c[:,1]<-3.72)&(c[:,2]<1.94)))
stick=arm&(c[:,1]<P['stick_ymax'])&~bucket
boom=arm&~(bucket|stick);upper=~(under|arm)
# Delete the candidate's thin dark hydraulic surfaces so no hidden remnant follows only one end.
gray=(col.max(1)-col.min(1)<.17)&(col.mean(1)<.56)
rod=np.zeros(len(c),bool)
for spec in P['hydraulics']:
 a=np.array(spec['a']);b=np.array(spec['b']);ab=b-a;t=np.clip((c-a)@ab/(ab@ab),0,1);dist=np.linalg.norm(c-a-t[:,None]*ab,axis=1)
 rod|=arm&gray&(dist<spec.get('remove_radius',.22))
for name,mask,owner in [('native_tracks',under,'base'),('native_upper_chassis_and_cab',upper,'slew'),('native_boom',boom&~rod,'boom'),('native_stick',stick&~rod,'stick'),('native_bucket_shell',bucket&~rod,'bucket')]:B.native(name,mask,owner)
for name in ['boom','stick','bucket']:
 pivot=np.array(P[name+'_pivot']);B.cylinder(name+'_pin',.075 if name=='boom' else .055,P['arm_width']+.08,pivot,[1,0,0],name,steel)
 for s in [-1,1]:B.cylinder(name+'_bearing_cap_'+str(s),.095 if name=='boom' else .07,.018,pivot+[s*(P['arm_width']/2+.045),0,0],[1,0,0],name,yellow)
for s in [-1,1]:B.proxy('base','box',[s*P['track_center_x'],P['track_center_y'],P['track_top']/2],[P['track_halfwidth'],P['track_halflength'],P['track_top']/2-.01],friction=[.9,.008,.001])
B.proxy('slew','box',P['upper_center'],P['upper_halfsize'])
for name in ['boom','stick']:
 pts=P[name+'_line']
 for a,b in zip(pts[:-1],pts[1:]):B.capsule(name,a,b,.14 if name=='boom' else .12)
# Open compound bucket contact shell, rather than a hull filling its mouth.
bc=np.array(P['bucket_center']);bw=P['bucket_width'];bd=P['bucket_depth'];bh=P['bucket_height']
for s in [-1,1]:B.proxy('bucket','box',bc+[s*(bw/2-.025),0,0],[.025,bd/2,bh/2])
B.proxy('bucket','box',bc+[0,0,-bh/2+.025],[bw/2,.5*bd,.025]);B.proxy('bucket','box',bc+[0,-bd/2+.025,0],[bw/2,.025,bh/2])
B.connections=[];B.contact_exclusions=[]
for spec in P['hydraulics']:
 n=spec['name'];a=np.array(spec['a']);b=np.array(spec['b']);delta=b-a;length=np.linalg.norm(delta);u=delta/length;bar=n+'_barrel';rodname=n+'_rod'
 B.body(bar,a,parent=spec['body_a'],mass=28,kind='hinge',axis=[1,0,0],limits=[-1.3,1.3],actuated=False,damping=4)
 B.body(rodname,a,parent=bar,mass=12,kind='slide',axis=u,limits=[-length*.30,length*.45],actuated=False,damping=12)
 tube_between(B,bar+'_surface',a,a+delta*.62,.055,bar,paint,True)
 tube_between(B,rodname+'_surface',a+delta*.48,b,.028,rodname,steel,True)
 for owner,end in [(bar,a),(rodname,b)]:B.cylinder(owner+'_eye',.072,.11,end,[1,0,0],owner,paint)
 B.connections.append({'name':n+'_distal_connection','body1':rodname,'body2':spec['body_b'],'anchor_world':b.tolist()})
 B.contact_exclusions.extend([[bar,spec['body_b']],[rodname,spec['body_b']],[rodname,spec['body_a']]])
B.controls=[{'body':'slew','label':'upper slew','target':.32,'tolerance':.05},{'body':'boom','label':'raise boom','target':.17,'tolerance':.05},{'body':'stick','label':'stick articulation','target':-.28,'tolerance':.06},{'body':'bucket','label':'bucket curl','target':.36,'tolerance':.06}]
B.operations.extend([{'operation':'candidate-informed semantic region reconstruction','target':'tracks, cab, boom, stick and bucket with original atlas'}, {'operation':'local removal of native hydraulic fragments','target':'candidate rods','removed_faces':int(rod.sum())}, {'operation':'cylindrical profiles and constrained telescoping assemblies','target':'three hydraulic visual mechanisms with both endpoints connected in MuJoCo'}, {'operation':'compound open collision shell','target':'bucket'}])
B.limitations.extend(['Full-size dimensions/masses and hidden mounting points are inferred','Virtual joint torques; no hydraulic fluid or soil simulation','Tracks remain rigid, no belt articulation','Small bearing overlaps are excluded only at named attachment pairs; other simplified contacts remain'])
B.export()
