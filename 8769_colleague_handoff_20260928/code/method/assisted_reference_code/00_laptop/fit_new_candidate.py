"""Fit newly generated planes; express base in an explicit modeling reference frame."""
from pathlib import Path
import json
import numpy as np
from scipy.optimize import least_squares
R=Path(__file__).resolve().parent
a=np.load(R/'native_geometry_zup.npz');v=a['vertices'];f=a['faces'];c=v[f].mean(1)
n=np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]]);n/=np.maximum(np.linalg.norm(n,axis=1)[:,None],1e-12)
base=v[v[:,2]<-.28]
lo,hi=np.quantile(base,[.0005,.9995],axis=0)
deck=float(np.median(c[(abs(c[:,0])>.445)&(abs(c[:,0])<.48)&(c[:,1]<.18)&(c[:,1]>-.32)&(n[:,2]>.8),2]))
sel=(c[:,2]>-.21)&(c[:,2]<.28)&(abs(c[:,0])<.4)
x=c[sel];fit=least_squares(lambda p:x[:,1]-p[0]*x[:,2]-p[1],[.1,.3],loss='soft_l1',f_scale=.006)
k,b=fit.x;d=np.array([0,k,1]);d/=np.linalg.norm(d);normal=np.array([0,1,-k]);normal/=np.linalg.norm(normal)
lid=v[v[:,2]>-.251];u=lid@d
report={'new_input_geometry':'native_geometry_zup.npz','base_bounds':[lo.tolist(),hi.tolist()],
 'deck_z':deck,'lid_plane_y_equals_k_z_plus_b':[float(k),float(b)],'lid_u_range':np.quantile(u,[0,1]).tolist(),
 'lid_x_range':np.quantile(lid[:,0],[0,1]).tolist(),'lid_face_cut_z':-.251,
 'base_reference_frame':{'x':[-.5,.5],'y':[-.350343,.3118],'bottom_z':-.327612,'deck_z':-.2995},
 'method':'Bounds and deck plane fitted to current candidate; robust lid plane fitted to current candidate. Keyboard count/color zones are editable single-image structural hypotheses; irregular fused native key layout is deliberately regularized.'}
(R/'candidate_fit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
(R/'key_layout.json').write_text(json.dumps({'x_centers_native':np.linspace(-.398,.398,14).tolist(),'y_centers_native':np.linspace(.163,-.151,6).tolist(),'origin':'Single-image regularized 14-column / 6-row keyboard hypothesis, with one merged 5-unit spacebar. Not an exact semantic parse of the native mesh.'},indent=2),encoding='utf-8')
print(json.dumps(report))
