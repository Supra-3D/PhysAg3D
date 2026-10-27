import bpy,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parent
P=json.loads((ROOT/'parameters.json').read_text())
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
scene=bpy.context.scene;scene.unit_settings.system='METRIC'
def cube(name,location,scale):
    bpy.ops.mesh.primitive_cube_add(size=1,location=location);o=bpy.context.object;o.name=name;o.dimensions=scale
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    return o
base=cube('scaffold_base',(0,0,.010),(.36,P['depth_m'],.016))
bpy.ops.object.empty_add(location=(0,P['hinge_y'],P['hinge_z']));hinge=bpy.context.object;hinge.name='scaffold_lid_frame'
lid=cube('scaffold_lid',(0,0,0),(P['lid_width_m'],P['lid_height_m'],.008));lid.parent=hinge;lid.location=(0,-P['lid_height_m']/2,0)
hinge.rotation_euler[0]=-math.radians(P['opening_deg']);hinge['opening_deg']=P['opening_deg'];hinge['closure_front_gap_m']=.001
scene['editable_parameters']=json.dumps(P);scene['stage']='Provisional scaffold before native TRELLIS.2 generation'
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'asset/scaffold.blend'))
