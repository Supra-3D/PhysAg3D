"""Analyze a generated GLB in metric-independent canonical axes; no asset edits."""
from pathlib import Path
import json
import numpy as np
import trimesh
ROOT=Path(__file__).resolve().parent
scene=trimesh.load(ROOT/'native-result/output/candidate_yup.glb',force='scene')
mesh=scene.to_geometry()
v=mesh.vertices.copy();v=v[:,[0,2,1]];v[:,1]*=-1
mesh.vertices=v
np.savez_compressed(ROOT/'native_geometry_zup.npz',vertices=v,faces=mesh.faces,uv=mesh.visual.uv)
report={'vertices':len(v),'faces':len(mesh.faces),'bounds_zup':mesh.bounds.tolist(),
        'quantiles':{str(a):np.quantile(v[:,a],[0,.01,.05,.1,.25,.5,.75,.9,.95,.99,1]).tolist() for a in range(3)}}
mat=mesh.visual.material
for field in ['baseColorTexture','metallicRoughnessTexture','normalTexture']:
    img=getattr(mat,field,None)
    if img is not None:img.save(ROOT/'asset'/(field+'.png'));report[field]=list(img.size)
(ROOT/'native_analysis.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
