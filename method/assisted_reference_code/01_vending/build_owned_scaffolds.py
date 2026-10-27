import bpy,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def box(name,sz,p,owner=None):
    bpy.ops.mesh.primitive_cube_add(size=1,location=p);o=bpy.context.object;o.name=name;o.dimensions=sz
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    if owner:
        o.parent=owner;o.matrix_parent_inverse=owner.matrix_world.inverted()
    return o
def pivot(name,pos,axis):
    o=bpy.data.objects.new(name,None);bpy.context.collection.objects.link(o);o.location=pos;o.empty_display_type='ARROWS';o.empty_display_size=.08;o['joint_axis']=axis;o['hypothesis']=True;return o
for cid in ['01_vending','02_gramophone','04_fridge','05_sink']:
    r=ROOT/cid;p=json.loads((r/'asset_plan.json').read_text(encoding='utf-8'));bpy.ops.wm.read_factory_settings(use_empty=True)
    if cid=='01_vending':
        for x in [-.44,.44]:box('cabinet_side',(.02,.70,1.7),(x,0,.95))
        for z in [.1,1.8]:box('cabinet_horizontal',(.88,.70,.02),(0,0,z))
        box('cabinet_back',(.88,.02,1.7),(0,.34,.95));door=pivot('service_door_hinge',(-.43,-.36,.15),'Z')
        box('front_service_panel',(.84,.028,1.63),(0,-.37,.985),door);flap=pivot('delivery_flap_hinge',(0,-.392,.55),'X');box('flap',(.53,.012,.20),(0,-.395,.45),flap)
    elif cid=='02_gramophone':
        box('case_floor',(.45,.4,.02),(0,0,.012))
        for x in [-.215,.215]:box('case_side',(.02,.40,.12),(x,0,.08))
        for y in [-.19,.19]:box('case_end',(.43,.02,.12),(0,y,.08))
        lid=pivot('lid_hinge',(0,.2,.14),'X');box('lid_shell',(.44,.025,.37),(0,.212,.325),lid)
        rec=pivot('record_spin',(-.04,-.04,.135),'Z');bpy.ops.mesh.primitive_cylinder_add(vertices=64,radius=.145,depth=.004,location=(-.04,-.04,.137));bpy.context.object.name='record';pivot('tonearm_yaw',(.1,.08,.14),'Z');pivot('crank_spin',(.23,0,.075),'X')
    elif cid=='04_fridge':
        for x in [-.315,.315]:box('cabinet_side',(.02,.60,1.63),(x,0,.835))
        box('cabinet_back',(.61,.025,1.63),(0,.29,.835))
        for z in [.03,1.16,1.64]:box('cabinet_divider',(.61,.59,.025),(0,0,z))
        for name,z,h in [('lower',.59,1.08),('upper',1.40,.44)]:
            piv=pivot(name+'_hinge',(.316,-.32,z),'Z');box(name+'_door',(.615,.038,h),(0,-.342,z),piv);piv.rotation_euler[2]=math.radians(17 if name=='lower' else 28)
    elif cid=='05_sink':
        for x in [-.21,.21]:
            box('basin_floor',(.375,.395,.018),(x,0,.015))
            for xx in [x-.19,x+.19]:box('basin_side',(.015,.4,.21),(xx,0,.12))
            for y in [-.2,.2]:box('basin_wall',(.375,.018,.21),(x,y,.12))
        for y in [-.235,.235]:box('outer_rim',(.84,.03,.025),(0,y,.235))
        for x in [-.405,0,.405]:box('rim_cross',(.03,.44,.025),(x,0,.235))
        pivot('faucet_swivel',(.02,.205,.25),'Z');pivot('valve_pitch',(.05,.205,.25),'X')
    scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene['asset_plan']=json.dumps(p,ensure_ascii=False);scene['stage']='provisional image-observed scaffold, before fresh native inference'
    bpy.ops.wm.save_as_mainfile(filepath=str(r/'asset/scaffold.blend'))
    (r/'SCAFFOLD_READY.json').write_text(json.dumps({'stage':'adjustable scaffold','saved':str(r/'asset/scaffold.blend'),'native_inference_already_used':False,'parts':len(scene.objects),'source_observed':True},indent=2),encoding='utf-8')
print('Four hollow and articulated provisional scaffolds saved')


