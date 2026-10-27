from pathlib import Path
import json,bpy,sys
R=Path(__file__).resolve().parent;sys.path.insert(0,str(R))
from blender_common import Builder
camera=json.loads((R/'camera.json').read_text())
class CameraOnly:pass
dummy=CameraOnly();dummy.L=.84
for kind in ['native','model']:
 bpy.ops.wm.open_mainfile(filepath=str(R/'asset'/(kind+'.blend')))
 Builder.set_camera(dummy,camera);bpy.context.scene.render.resolution_x=bpy.context.scene.render.resolution_y=1024
 if kind=='model':bpy.ops.wm.save_as_mainfile(filepath=str(R/'asset/model.blend'))
 bpy.context.scene.render.filepath=str(R/'renders'/('native.png' if kind=='native' else 'refined.png'));bpy.ops.render.render(write_still=True)
