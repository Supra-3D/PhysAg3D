from pathlib import Path
import sys,json,xml.etree.ElementTree as ET
import numpy as np,mujoco
ROOT=Path(__file__).resolve().parents[2];cid=sys.argv[1];r=ROOT/'cases'/cid
sys.path.insert(0,str(r));from physics_common import load_model,write,f
p=json.loads((r/'candidate_partition.json').read_text());xml=ET.fromstring((r/'asset/scene.xml').read_text());wb=xml.find('worldbody')
if cid=='05_sink':
    centers=p['probe_drop_centers'];starts=[[x,y,p['rim_z']+.13] for x,y,_ in centers];radius=.030
else:
    lo,hi=np.array(p['cabinet_bounds']);starts=[[hi[0]+.14,(hi[1]+lo[1])/2,hi[2]*.65]];radius=.032
for i,pos in enumerate(starts):
    body=ET.SubElement(wb,'body',name='cavity_probe_'+str(i),pos=f(pos));ET.SubElement(body,'freejoint',name='probe_joint_'+str(i));ET.SubElement(body,'geom',name='probe_geom_'+str(i),type='sphere',size=str(radius),mass='.075',rgba='.04 .3 .9 1',friction='.65 .006 .0001',priority='1',solref='.002 1',solimp='.98 .999 .0005')
write(xml,r/'asset/cavity_test.xml');m=load_model(r,'cavity_test.xml');d=mujoco.MjData(m);mujoco.mj_forward(m,d)
if cid=='01_vending':
    d.ctrl[m.actuator('service_door_control').id]=.85
    for _ in range(5000):mujoco.mj_step(m,d)
    for i,pos in enumerate(starts):
        j=m.joint('probe_joint_'+str(i));d.qpos[j.qposadr[0]:j.qposadr[0]+7]=[*pos,1,0,0,0];d.qvel[j.dofadr[0]:j.dofadr[0]+6]=[-1.6,0,0,0,0,0]
    mujoco.mj_forward(m,d)
states=[];minimum=0.;finite=True
for step in range(5000):
    mujoco.mj_step(m,d);finite &= bool(np.isfinite(d.qpos).all())
    if d.ncon:minimum=min(minimum,float(min(x.dist for x in d.contact[:d.ncon])))
    if step%125==0:states.append({'time':float(d.time),'bodies':{m.body(i).name:{'pos':d.xpos[i].tolist(),'quat':d.xquat[i].tolist()} for i in range(1,m.nbody)}})
ends=[d.body('cavity_probe_'+str(i)).xpos.tolist() for i in range(len(starts))]
if cid=='05_sink':
    checks={str(i):np.linalg.norm(np.array(pos[:2])-np.array(starts[i][:2]))<.08 and p['floor_z']+radius-.004<pos[2]<p['rim_z']-.04 for i,pos in enumerate(ends)}
else:
    checks={'sphere_entered_cabinet':lo[0]-.02<ends[0][0]<hi[0]-.04 and lo[1]<ends[0][1]<hi[1] and hi[2]*.10<ends[0][2]<hi[2]*.25}
checks.update(finite=finite,no_solver_warnings=sum(int(x.number) for x in d.warning)==0,penetration_below_3mm=minimum>-.003)
checks={k:bool(v) for k,v in checks.items()}
report={'test':'independent sphere drop into each basin' if cid=='05_sink' else 'external sphere launched into physically opened cabinet','checks':checks,'passed':bool(all(checks.values())),'starts':starts,'final_positions':ends,'sphere_radius_m':radius,'minimum_contact_distance_m':minimum,'actual_mj_step':True,'engine_version':mujoco.__version__,'simulation_seconds':float(d.time),'limitations':['Compound-shell contact geometry is approximate','No fluid or dispensing simulation']}
(r/'cavity_test_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');(r/'cavity_test_trajectory.json').write_text(json.dumps({'states':states,'radius':radius}),encoding='utf-8');print(json.dumps(report))
