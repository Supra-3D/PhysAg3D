"""Render this newly generated candidate before semantic edits."""
from pathlib import Path
import json, sys
import bpy
import numpy as np
from mathutils import Vector
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import blender_helpers as H
A=np.load(ROOT/'native_geometry_zup.npz');V=A['vertices'];F=A['faces'];UV=A['uv']
H.setup_scene();s=bpy.context.scene;s.cycles.samples=24;s.render.threads_mode='FIXED';s.render.threads=4
for ob in s.objects:
    if ob.type=='LIGHT':ob.data.energy*=.42
s.world.node_tree.nodes['Background'].inputs[1].default_value=.32
P=H.P
base=V[V[:,2]<-.28]
lo=np.quantile(base,.001,axis=0);hi=np.quantile(base,.999,axis=0)
scale=.36/(hi[0]-lo[0]);center=(lo+hi)/2
points=(V-[center[0],center[1],lo[2]])*scale+[0,0,.002]
mesh=bpy.data.meshes.new('new_raw_candidate');mesh.from_pydata(points.tolist(),[],F.tolist());mesh.update()
layer=mesh.uv_layers.new(name='NativeAtlas')
for loop in mesh.loops:layer.data[loop.index].uv=UV[loop.vertex_index]
for face in mesh.polygons:face.use_smooth=True
ob=bpy.data.objects.new('new_raw_candidate',mesh);s.collection.objects.link(ob)
m=H.material('native',(1,1,1));n=m.node_tree.nodes;l=m.node_tree.links;bs=n.get('Principled BSDF')
t=n.new('ShaderNodeTexImage');t.image=bpy.data.images.load(str(ROOT/'asset/baseColorTexture.png'));l.new(t.outputs['Color'],bs.inputs['Base Color'])
t=n.new('ShaderNodeTexImage');t.image=bpy.data.images.load(str(ROOT/'asset/metallicRoughnessTexture.png'));t.image.colorspace_settings.name='Non-Color'
sep=n.new('ShaderNodeSeparateColor');l.new(t.outputs['Color'],sep.inputs['Color']);l.new(sep.outputs['Green'],bs.inputs['Roughness']);l.new(sep.outputs['Blue'],bs.inputs['Metallic']);ob.data.materials.append(m)
def render(name):s.render.filepath=str(ROOT/'renders'/name);bpy.ops.render.render(write_still=True)
render('native_raw_source.png')
bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'asset/native_inspection.blend'))
cam=s.camera;cam.data.type='ORTHO';cam.data.shift_x=cam.data.shift_y=0;cam.data.ortho_scale=.40
for name,eye,target in [('native_top.png',(0,0,1),(0,0,0)),('native_side.png',(1,0,.1),(0,0,.1))]:
    cam.location=eye;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler();render(name)
(ROOT/'candidate_registration_initial.json').write_text(json.dumps({'source':'new candidate only','scale':scale,'native_base_bounds':[lo.tolist(),hi.tolist()],'native_center_xy':center[:2].tolist()},indent=2))
