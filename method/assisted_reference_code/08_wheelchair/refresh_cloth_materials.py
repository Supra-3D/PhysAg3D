from pathlib import Path
import bpy,json
R=Path(__file__).resolve().parent;bpy.ops.wm.open_mainfile(filepath=str(R/'asset/model.blend'))
for which in ['back','seat']:
 m=bpy.data.materials['source_projected_'+which]
 for node in m.node_tree.nodes:
  if node.type=='TEX_IMAGE':node.image=bpy.data.images.load(str(R/'asset'/('source_'+which+'_cloth.png')),check_existing=False)
bpy.ops.object.select_all(action='DESELECT')
for o in bpy.context.scene.objects:
 if o.type=='EMPTY' or o.type=='MESH' and o.get('body') and not o.get('staging_only'):o.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(R/'asset/model.glb'),use_selection=True,export_format='GLB');bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(R/'asset/model.blend'))
# MuJoCo's referenced texture files must be refreshed with the same pixels.
import shutil
for which in ['back','seat']:shutil.copy2(R/'asset'/('source_'+which+'_cloth.png'),R/'asset/textures'/('source_'+which+'_cloth.png'))
print('Updated texture-only stage; geometry, MJCF, physical parameters and trajectory unchanged')
