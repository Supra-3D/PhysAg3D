from pathlib import Path
import sys,json
import bpy
from mathutils import Quaternion,Vector
ROOT=Path(__file__).resolve().parents[2];cid=sys.argv[sys.argv.index('--')+1];r=ROOT/'cases'/cid
bpy.ops.wm.open_mainfile(filepath=str(r/'asset/model.blend'));sc=bpy.context.scene;sc.render.threads_mode='FIXED';sc.render.threads=4;sc.cycles.samples=20;sc.render.resolution_x=sc.render.resolution_y=768
t=json.loads((r/'cavity_test_trajectory.json').read_text());states=t['states'];roots={o.name[5:]:o for o in sc.objects if o.name.startswith('body_')}
for o in roots.values():world=o.matrix_world.copy();o.parent=None;o.matrix_world=world
mat=bpy.data.materials.new('actual_test_probe_blue');mat.use_nodes=True;mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(.025,.20,.7,1)
cam=sc.camera;cam.location=(-.40,-2.7,1.25);target=Vector((0,0,.85));cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='ORTHO';cam.data.ortho_scale=2.02;cam.data.shift_x=cam.data.shift_y=0
probes={}
for name in states[0]['bodies']:
    if name.startswith('cavity_probe_'):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32,ring_count=16,radius=t['radius']);o=bpy.context.object;o.name=name;o.data.materials.append(mat);probes[name]=o
for label,s in [('entry',states[min(4,len(states)-1)]),('settled',states[-1])]:
    for name,p in s['bodies'].items():
        o=roots.get(name) or probes.get(name)
        if o is not None:o.location=p['pos'];o.rotation_mode='QUATERNION';o.rotation_quaternion=Quaternion(p['quat'])
    sc.render.filepath=str(r/'renders'/('cavity_'+label+'.png'));bpy.ops.render.render(write_still=True)
    if cid=='05_sink':
        cam=sc.camera;target=Vector((0,0,.12));cam.location=(.55,-.70,.85);cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.ortho_scale=1.0;cam.data.shift_x=cam.data.shift_y=0
        sc.render.filepath=str(r/'renders'/('cavity_overhead_'+label+'.png'));bpy.ops.render.render(write_still=True)
(r/'cavity_images.json').write_text(json.dumps({'source':'actual cavity_test_trajectory.json body poses','files':['renders/cavity_entry.png','renders/cavity_settled.png'],'sample_times':[states[min(4,len(states)-1)]['time'],states[-1]['time']]},indent=2),encoding='utf-8')
