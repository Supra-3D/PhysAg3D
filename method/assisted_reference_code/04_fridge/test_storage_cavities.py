from pathlib import Path
import json,xml.etree.ElementTree as ET
import numpy as np,mujoco
from physics_common import load_model,write,f
r=Path(__file__).resolve().parent;p=json.loads((r/'candidate_partition.json').read_text());lo,hi=np.array(p['roof_bounds']);yf=p['front_y'];split=p['horizontal_split_z'];x=float(lo[0]+.22*(hi[0]-lo[0]));starts=[[x,yf-.16,split+.27],[x,yf-.16,split*.56]]
root=ET.fromstring((r/'asset/scene.xml').read_text());wb=root.find('worldbody');radius=.025
for i,pos in enumerate(starts):
    b=ET.SubElement(wb,'body',name='cavity_probe_'+str(i),pos=f(pos));ET.SubElement(b,'freejoint',name='probe_'+str(i));ET.SubElement(b,'geom',type='sphere',size=str(radius),mass='.06',rgba='.03 .25 .8 1',priority='1',solref='.002 1',solimp='.98 .999 .0005',friction='.65 .006 .0001')
write(root,r/'asset/cavity_test.xml');m=load_model(r,'cavity_test.xml');d=mujoco.MjData(m)
for i in range(2):
    j=m.joint('probe_'+str(i));d.qvel[j.dofadr[0]+1]=1.35
mujoco.mj_forward(m,d);states=[];minimum=0.;finite=True
for k in range(5000):
    mujoco.mj_step(m,d);finite &= bool(np.isfinite(d.qpos).all())
    if d.ncon:minimum=min(minimum,min(float(c.dist) for c in d.contact[:d.ncon]))
    if k%125==0:states.append({'time':float(d.time),'bodies':{m.body(i).name:{'pos':d.xpos[i].tolist(),'quat':d.xquat[i].tolist()} for i in range(1,m.nbody)}})
ends=[d.body('cavity_probe_'+str(i)).xpos.tolist() for i in range(2)];checks={'finite':finite,'no_solver_warnings':sum(int(w.number) for w in d.warning)==0,'penetration_below_3mm':minimum>-.003}
for i,pt in enumerate(ends):checks['probe_'+str(i)+'_inside_its_compartment']=bool(lo[0]+.03<pt[0]<hi[0]-.03 and yf+.02<pt[1]<hi[1]-.02 and (split+.02<pt[2]<hi[2]-.03 if i==0 else .03<pt[2]<split-.03))
report={'test':'two external spheres launched across the upper and lower cabinet apertures from the source-open door pose','starts':starts,'final_positions':ends,'sphere_radius_m':radius,'checks':checks,'passed':all(checks.values()),'actual_mj_step':True,'engine_version':mujoco.__version__,'simulation_seconds':float(d.time),'minimum_contact_distance_m':minimum,'limitations':['Category-prior shelves and wall thickness','Hard-probe contact parameters are test-fixture assumptions, not calibrated material truth']}
(r/'cavity_test_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');(r/'cavity_test_trajectory.json').write_text(json.dumps({'states':states,'radius':radius}),encoding='utf-8');print(json.dumps(report))
