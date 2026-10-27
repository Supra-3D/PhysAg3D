"""Semantic material refinement on retained native geometry and color textures."""
import json,sys
from pathlib import Path
import bpy
import numpy as np
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
import blender_helpers as H
from refinement_tools import loft
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'asset/laptop.blend'))

def variant(original,name,rough,metal):
    mat=original.copy();mat.name=name;bs=mat.node_tree.nodes.get('Principled BSDF')
    for channel,value in [('Roughness',rough),('Metallic',metal)]:
        for link in list(bs.inputs[channel].links):mat.node_tree.links.remove(link)
        bs.inputs[channel].default_value=value
    return mat

original=bpy.data.materials['TRELLIS_native_PBR']
keyplastic=variant(original,'Native_color_key_plastic',.48,0)
for obj in bpy.context.scene.objects:
    if obj.type=='MESH' and obj.name.endswith('_native_top') and obj.data.materials[0].get('mujoco_texture'):
        obj.data.materials[0]=keyplastic
body=bpy.data.objects['native_chassis_refined'];base=variant(original,'Native_color_anodized_chassis',.46,.35);body.data.materials[0]=base
lid=bpy.data.objects['native_lid_refined'];lid.data.materials.clear()
# Actual closed-pose inspection revealed a white stripe in the hallucinated
# back/edge atlas. Retain its fitted geometry, apply the observed black housing.
housing=H.material('black_display_housing',(.008,.009,.010),.03,.43)
lid.data.materials.append(housing)
for face in lid.data.polygons:face.material_index=0
# Rebuild the smooth display cover as a local lofted patch. Selecting material by
# triangle centers left a jagged boundary; the new patch has an explicit outline.
glass=H.material('display_cover_glass',(.006,.007,.008),.03,.20)
bs=glass.node_tree.nodes.get('Principled BSDF');bs.inputs['Coat Weight'].default_value=.22;bs.inputs['Coat Roughness'].default_value=.12
h=H.P['lid_height_m'];count=0
if bpy.data.objects.get('display_cover'):bpy.data.objects.remove(bpy.data.objects['display_cover'],do_unlink=True)
loft('display_cover',[(.326,h-.025,.0065,-.0049),(.3256,h-.0254,.0065,-.0043)],glass,'lid',(0,-h/2,0),segments=12)
H.export_assets();bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'asset/laptop.blend'))
bpy.context.scene.render.filepath=str(ROOT/'renders/source_material_refined.png');bpy.ops.render.render(write_still=True)
root=bpy.data.objects['body_lid'];angle=root.rotation_euler.x;root.rotation_euler.x=0
bpy.context.scene.render.filepath=str(ROOT/'renders/closed_material_refined.png');bpy.ops.render.render(write_still=True);root.rotation_euler.x=angle
report=json.loads((ROOT/'refinement_report.json').read_text(encoding='utf-8'))
report['material_refinement']={'chassis':'native base color retained; category-inferred anodized metal response, roughness .46 / metallic .35',
    'display':'explicit lofted glass cover over native interior; native bezel/lid geometry retained with image-supported black material, correcting a white artifact exposed by the closed-pose inspection',
    'keys':'native color and surface retained; plastic response roughness .48 / metallic 0 to correct metallic glare revealed by environment lighting',
    'note':'Material response parameters are inferred, not recovered truth; remaining neural regions retain original PBR maps'}
(ROOT/'refinement_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('Semantic display faces',count)
