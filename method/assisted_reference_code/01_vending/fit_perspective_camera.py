from pathlib import Path
import numpy as np,json,math
from scipy.optimize import least_squares
r=Path(__file__).resolve().parent;a=np.load(r/'native_geometry.npz');v=a['vertices'];p=v[v[:,2]>.24];lo,hi=np.quantile(p,[.003,.997],axis=0);xl,xr=lo[0],hi[0];yl,yr=lo[1],hi[1];zt=hi[2];zb=.105
points=np.array([[xr,yl,zt],[xr,yr,zt],[xl,yr,zt],[xl,yl,zt],[xr,yl,zb],[xr,yr,zb],[xl,yr,zb]])
observed=np.array([[274,231],[575,273],[769,242],[470,213],[305,733],[562,855],[733,727]],float)/1024
center=np.array([0,0,.925])
def axes(a,e,roll):
 a,e=np.deg2rad([a,e]);eye=np.array([np.cos(e)*np.cos(a),np.cos(e)*np.sin(a),np.sin(e)]);right=np.cross([0,0,1],eye);right/=np.linalg.norm(right);up=np.cross(eye,right)
 return np.cos(roll)*right+np.sin(roll)*up,-np.sin(roll)*right+np.cos(roll)*up,eye
def project(q):
 right,up,eye=axes(q[0],q[1],q[6]);p=points-center;dep=q[2]-p@eye
 return np.column_stack([q[3]*(p@right)/dep+q[4],-q[3]*(p@up)/dep+q[5]])
fit=least_squares(lambda q:(project(q)-observed).ravel(),[45,15,5,1.5,.5,.55,0],bounds=([5,-5,2.6,.35,.25,.25,-.15],[85,45,30,8,.75,.75,.15]),max_nfev=3000)
q=fit.x;right,up,eye=axes(q[0],q[1],q[6]);c={'type':'PERSP','location':(center+eye*q[2]).tolist(),'target':center.tolist(),'right':right.tolist(),'up':up.tolist(),'lens_mm':float(q[3]*36),'sensor_width_mm':36,'shift_x':float(.5-q[4]),'shift_y':float(q[5]-.5),'ortho_scale':3.0,'resolution':1024,'fit':{'method':'perspective solve on manually observed cabinet corner correspondences','source_points_are_agent_hypotheses':True,'source_points':observed.tolist(),'new_candidate_points_m':points.tolist(),'rmse_px':float(np.sqrt(np.mean((project(q)-observed)**2))*1024),'parameters':q.tolist(),'replaces':'orthographic fit whose roof perspective mismatch was visually diagnosed'}}
(r/'camera_orthographic_rejected.json').write_text((r/'camera.json').read_text(),encoding='utf-8');(r/'camera.json').write_text(json.dumps(c,indent=2),encoding='utf-8');print(json.dumps(c))
