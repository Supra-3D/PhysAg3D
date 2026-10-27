"""Additional true MuJoCo trajectory snapshots, before each full revolution ends."""
from pathlib import Path
import json,math
import bpy
from mathutils import Quaternion
r=Path(__file__).resolve().parent
bpy.ops.wm.open_mainfile(filepath=str(r/'asset/model.blend'))
states=json.loads((r/'trajectory.json').read_text())['states']
manifest=json.loads((r/'motion_images.json').read_text())
roots={ob.name[5:]:ob for ob in bpy.context.scene.objects if ob.name.startswith('body_')}
for ob in roots.values():
    world=ob.matrix_world.copy();ob.parent=None;ob.matrix_world=world
sc=bpy.context.scene;sc.render.threads_mode='FIXED';sc.render.threads=4
sc.render.resolution_x=sc.render.resolution_y=640;sc.render.resolution_percentage=100;sc.cycles.samples=20
for phase,index in [('record_move',1),('crank_move',3)]:
    state=min((s for s in states if s['phase']==phase),key=lambda s:abs(s['qpos'][index]-math.pi/2))
    for name,pose in state['bodies'].items():
        if name in roots:
            ob=roots[name];ob.location=pose['pos'];ob.rotation_mode='QUATERNION';ob.rotation_quaternion=Quaternion(pose['quat'])
    name='renders/motion_'+phase+'_quarter.png';sc.render.filepath=str(r/name);bpy.ops.render.render(write_still=True)
    manifest.append({'phase':phase+'_quarter','simulation_time':state['time'],'qpos':state['qpos'],'file':name})
(r/'motion_images.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
