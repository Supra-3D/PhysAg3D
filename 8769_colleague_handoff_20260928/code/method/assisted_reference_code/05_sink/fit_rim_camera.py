"""Use explicit observed rim corners to correct a misleading silhouette fit."""
from pathlib import Path
import json
import numpy as np
from scipy.optimize import least_squares
R=Path(__file__).resolve().parent
prior=json.loads((R/'camera.json').read_text());p=json.loads((R/'candidate_partition.json').read_text());z=p['rim_z']
points=np.array([[-.42,-.244,z],[-.42,.244,z],[.42,.244,z],[.42,-.244,z]])
pixels=np.array([[233,505],[447,447],[831,559],[631,674]],float)
def project(q,details=False):
 az,el,d,cx,cy,f=q;az,el=np.deg2rad([az,el]);eye=np.array([np.cos(el)*np.cos(az),np.cos(el)*np.sin(az),np.sin(el)])
 right=np.cross([0,0,1],eye);right/=np.linalg.norm(right);up=np.cross(eye,right);target=np.array([0,0,.21]);location=target+eye*d
 rel=points-location;depth=rel@(-eye);xy=np.column_stack([f*(rel@right)/depth+cx,-f*(rel@up)/depth+cy])
 return (xy,location,target,right,up) if details else xy
fit=least_squares(lambda q:(project(q)-pixels).ravel(),[-45,25,3,512,535,1900],bounds=([-75,5,.8,300,300,600],[-15,65,8,750,750,5000]),max_nfev=3000,x_scale='jac')
xy,loc,target,right,up=project(fit.x,True);az,el,d,cx,cy,f=fit.x
camera={'type':'PERSP','location':loc.tolist(),'target':target.tolist(),'right':right.tolist(),'up':up.tolist(),'lens_mm':float(f*36/1024),'sensor_width_mm':36,'ortho_scale':prior['ortho_scale'],'shift_x':float((512-cx)/1024),'shift_y':float((cy-512)/1024),'resolution':1024,
 'fit':{'method':'Four manually observed source rim corners; metric candidate width/depth are category assumptions','landmarks_px':pixels.tolist(),'projected_px':xy.tolist(),'rms_px':float(np.sqrt(np.mean((xy-pixels)**2))),'azimuth_deg':float(az),'elevation_deg':float(el)}}
(R/'camera_before_rim_fit.json').write_text(json.dumps(prior,indent=2));(R/'camera.json').write_text(json.dumps(camera,indent=2));print(json.dumps(camera))
