"""Geometric closure test on exported visible geometry, independent of target angles."""
from pathlib import Path
import json
import numpy as np
import trimesh
ROOT=Path(__file__).resolve().parent
manifest=json.loads((ROOT/'asset/visual_manifest.json').read_text(encoding='utf-8'))
P=json.loads((ROOT/'parameters.json').read_text())
bodies=manifest['bodies'];loaded={}
for p in manifest['parts']:loaded[p['name']]=trimesh.load(ROOT/'asset'/p['mesh'],force='mesh',process=False)
lid=[];base=[];samples=[]
for p in manifest['parts']:
    m=loaded[p['name']];owner=p['body'];pos=np.array(bodies[owner]['pos'])
    if owner=='lid':
        t=m.triangles.copy()+pos
        lid.append(t)
    elif p['name']=='native_chassis_refined':base.append(m.vertices)
    elif bodies[owner]['kind']=='key':
        bounds=m.bounds+pos
        if p['name'].endswith('_skirt') or owner=='trackpad' and p['name']=='touchpad_panel':
            low,high=bounds;center=(low+high)/2
            # Inside the rounded footprint, with conservative highest key height.
            for dx,dy in [(0,0),(-.35,-.35),(-.35,.35),(.35,-.35),(.35,.35)]:
                samples.append((owner,center[0]+dx*(high[0]-low[0]),center[1]+dy*(high[1]-low[1]),high[2]))
t=np.concatenate(lid);base=np.concatenate(base);n=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);front=t[n[:,2]<-1e-12]
a,b,c=front[:,0],front[:,1],front[:,2]
den=(b[:,1]-c[:,1])*(a[:,0]-c[:,0])+(c[:,0]-b[:,0])*(a[:,1]-c[:,1])
rows=[];uncovered=[]
for name,x,y,height in samples:
    u=((b[:,1]-c[:,1])*(x-c[:,0])+(c[:,0]-b[:,0])*(y-c[:,1]))/den
    v=((c[:,1]-a[:,1])*(x-c[:,0])+(a[:,0]-c[:,0])*(y-c[:,1]))/den
    w=1-u-v;inside=(u>=-1e-8)&(v>=-1e-8)&(w>=-1e-8)
    if not inside.any():uncovered.append(name);continue
    z=(u*a[:,2]+v*b[:,2]+w*c[:,2])[inside].min()
    rows.append({'body':name,'x':float(x),'y':float(y),'clearance_m':float(z-height)})
lv=t.reshape(-1,3)
front_gap=float(lv[:,1].min()-base[:,1].min());side_gap=float((np.ptp(base[:,0])-np.ptp(lv[:,0]))/2)
report={'closed_angle_deg':0,'tested_control_surface_samples':len(samples),'uncovered_samples':uncovered,
        'front_gap_m':front_gap,'side_gap_m':side_gap,'minimum_control_clearance_m':min(x['clearance_m'] for x in rows),
        'checks':{'front_coverage':abs(front_gap)<.003,'side_coverage':abs(side_gap)<.004,
                  'control_surfaces_covered':not uncovered,'lid_clears_controls':min(x['clearance_m'] for x in rows)>.0002},
        'method':'Barycentric intersection with actual exported closed-lid front triangles at five positions on each control; inferred metric scale',
        'samples':rows}
(ROOT/'closure_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='samples'},indent=2))
assert all(report['checks'].values()),'Closure geometry check failed'
