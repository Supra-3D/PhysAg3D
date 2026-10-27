from pathlib import Path
import json,math,bpy
from mathutils import Vector
R=Path(__file__).resolve().parent;P=json.loads((R/'asset_plan.json').read_text());bpy.ops.wm.read_factory_settings(use_empty=True)
def mat(n,c):
 m=bpy.data.materials.new(n);m.diffuse_color=(*c,1);return m
brass=mat('editable_scaffold',(.45,.36,.12));soft=mat('soft_region_hypothesis',(.04,.12,.26));green=mat('shade_hypothesis',(.12,.27,.04))
def box(n,d,p,m=brass):
 bpy.ops.mesh.primitive_cube_add(size=1,location=p);o=bpy.context.object;o.name=n;o.dimensions=d;o.data.materials.append(m);return o
def cyl(n,r,d,p,axis=(0,0,1),m=brass):
 bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=r,depth=d,location=p);o=bpy.context.object;o.name=n;o.rotation_euler=Vector(axis).to_track_quat('Z','Y').to_euler();o.data.materials.append(m);return o
def rod(n,a,b,r=.015):
 a,b=Vector(a),Vector(b);return cyl(n,r,(b-a).length,(a+b)/2,b-a)
def pin(n,p):
 o=bpy.data.objects.new(n,None);bpy.context.collection.objects.link(o);o.location=p;o.empty_display_type='ARROWS';o.empty_display_size=max(P['dimensions_m'])*.07;return o
cid=R.name
if cid=='03_lamp':
 cyl('base',.095,.025,(0,.05,.0125));rod('lower_stand',(0,.05,.04),(0,.12,.23),.012);rod('upper_stand',(0,.12,.23),(0,0,.42),.012)
 box('shade_envelope',(.28,.15,.085),(0,0,.455),green)
 for x in [-.15,.15]:rod('yoke',(0,.1,.4),(x,0,.42),.008)
 pin('shade_hinge_X',(0,0,.42))
elif cid=='06_excavator':
 for x in [-.95,.95]:box('track',(.45,3.8,.65),(x,1.7,.325))
 cyl('slew',.85,.35,(0,1.7,.8));box('upper_chassis',(2.2,2.9,.9),(0,2,1.2));box('cab',(.95,1,1.15),(.5,.65,1.7),soft)
 a=(0,.4,1.8);b=(0,-2.7,4.3);c=(0,-3.5,2.4)
 rod('boom_envelope',a,b,.2);rod('stick_envelope',b,c,.18);box('bucket_envelope',(.85,.7,.55),(0,-3.3,2.15))
 for n,p in [('boom_X',a),('stick_X',b),('bucket_X',c),('slew_Z',(0,1.7,.85))]:pin(n,p)
else:
 for s in [-1,1]:
  y=s*.33;cyl('rear_wheel',.31,.035,(-.25,y,.32),(0,1,0));cyl('front_wheel',.095,.04,(.34,s*.29,.10),(0,1,0))
  rod('back_frame',(-.28,s*.245,.34),(-.28,s*.245,.98));rod('seat_frame',(-.28,s*.245,.47),(.25,s*.245,.47));rod('front_leg',(.25,s*.245,.68),(.34,s*.29,.22))
  rod('foot_support',(.25,s*.245,.45),(.50,s*.26,.07));box('footplate',(.18,.17,.02),(.54,s*.16,.065));pin('fold_axis_'+str(s),(.50,s*.26,.07))
 box('seat',(.50,.49,.025),(-.02,0,.48),soft);box('back',(.025,.49,.50),(-.28,0,.73),soft)
bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene['editable_plan']=json.dumps(P);bpy.context.scene['stage']='pre-inference structural hypothesis; not final geometry'
bpy.ops.wm.save_as_mainfile(filepath=str(R/'asset/scaffold.blend'))
(R/'scaffold_report.json').write_text(json.dumps({'stage':'pre_inference','object_count':len(bpy.context.scene.objects),'constraints':P['mechanical_constraints'],'parameters':P['parameters'],'all_dimensions':'editable inferred SI values'},indent=2))
